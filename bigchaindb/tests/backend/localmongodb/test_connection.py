# Copyright © 2020 Interplanetary Database Association e.V.,
# BigchainDB and IPDB software contributors.
# SPDX-License-Identifier: (Apache-2.0 AND CC-BY-4.0)
# Code is Apache-2.0 and docs are CC-BY-4.0
# Modified by thematerials-network contributors, 2026; see NOTICE at the repository root.

from unittest import mock

import pytest
import pymongo
from pymongo import MongoClient


pytestmark = pytest.mark.bdb


@pytest.fixture
def mock_cmd_line_opts():
    return {'argv': ['mongod', '--dbpath=/data'],
            'ok': 1.0,
            'parsed': {'replication': {'replSet': None},
                       'storage': {'dbPath': '/data'}}}


@pytest.fixture
def mock_config_opts():
    return {'argv': ['mongod', '--dbpath=/data'],
            'ok': 1.0,
            'parsed': {'replication': {'replSetName': None},
                       'storage': {'dbPath': '/data'}}}


@pytest.fixture
def mongodb_connection():
    import bigchaindb
    return MongoClient(host=bigchaindb.config['database']['host'],
                       port=bigchaindb.config['database']['port'])


def test_get_connection_returns_the_correct_instance(db_host, db_port):
    from bigchaindb.backend import connect
    from bigchaindb.backend.connection import Connection
    from bigchaindb.backend.localmongodb.connection import LocalMongoDBConnection

    config = {
        'backend': 'localmongodb',
        'host': db_host,
        'port': db_port,
        'name': 'test',
        'replicaset': None,
    }

    conn = connect(**config)
    assert isinstance(conn, Connection)
    assert isinstance(conn, LocalMongoDBConnection)
    assert conn.conn._topology_settings.replica_set_name == config['replicaset']


@mock.patch('pymongo.MongoClient.__init__')
def test_connection_error(mock_client):
    from bigchaindb.backend import connect
    from bigchaindb.backend.exceptions import ConnectionError

    # force the driver to throw ConnectionFailure
    # the mock on time.sleep is to prevent the actual sleep when running
    # the tests
    mock_client.side_effect = pymongo.errors.ConnectionFailure()

    with pytest.raises(ConnectionError):
        conn = connect()
        conn.db

    assert mock_client.call_count == 3


def test_connection_run_errors():
    from bigchaindb.backend import connect
    from bigchaindb.backend.exceptions import (DuplicateKeyError,
                                               OperationError,
                                               ConnectionError)

    conn = connect()

    query = mock.Mock()
    query.run.side_effect = pymongo.errors.AutoReconnect('foo')
    with pytest.raises(ConnectionError):
        conn.run(query)
    assert query.run.call_count == 2

    query = mock.Mock()
    query.run.side_effect = pymongo.errors.DuplicateKeyError('foo')
    with pytest.raises(DuplicateKeyError):
        conn.run(query)
    assert query.run.call_count == 1

    query = mock.Mock()
    query.run.side_effect = pymongo.errors.OperationFailure('foo')
    with pytest.raises(OperationError):
        conn.run(query)
    assert query.run.call_count == 1


@mock.patch('pymongo.MongoClient')
def test_connection_with_credentials(mock_client):
    import bigchaindb
    from bigchaindb.backend.localmongodb.connection import LocalMongoDBConnection
    conn = LocalMongoDBConnection(host=bigchaindb.config['database']['host'],
                                  port=bigchaindb.config['database']['port'],
                                  login='theplague',
                                  password='secret')
    conn.connect()
    assert mock_client.call_count == 1
    assert mock_client.call_args.kwargs['username'] == 'theplague'
    assert mock_client.call_args.kwargs['password'] == 'secret'
    assert mock_client.call_args.kwargs['authSource'] == conn.dbname


@mock.patch('pymongo.MongoClient')
def test_connection_with_tls_certificates(mock_client):
    from bigchaindb.backend import connect

    conn = connect(ca_cert='/certs/ca.pem', certfile='/certs/client.pem', keyfile='/certs/client.pem',
                   keyfile_passphrase='pass', crlfile='/certs/crl.pem', login='CN=node', password=None)
    conn.conn

    assert mock_client.call_count == 1
    kwargs = mock_client.call_args.kwargs
    assert kwargs['tls'] is True
    assert kwargs['tlsCAFile'] == '/certs/ca.pem'
    assert kwargs['tlsCertificateKeyFile'] == '/certs/client.pem'
    assert kwargs['tlsCertificateKeyFilePassword'] == 'pass'
    assert kwargs['tlsCRLFile'] == '/certs/crl.pem'
    assert kwargs['authMechanism'] == 'MONGODB-X509'
    assert kwargs['username'] == 'CN=node'
    assert 'ssl_ca_certs' not in kwargs


@mock.patch('pymongo.MongoClient')
def test_connection_with_tls_certificates_without_login(mock_client):
    from bigchaindb.backend import connect

    conn = connect(ca_cert='/certs/ca.pem', certfile='/certs/client.pem', keyfile='/certs/client.pem',
                   crlfile='/certs/crl.pem')
    conn.conn

    kwargs = mock_client.call_args.kwargs
    assert kwargs['tls'] is True
    assert 'authMechanism' not in kwargs
    assert 'username' not in kwargs


def test_connection_with_separate_key_file_is_a_configuration_error():
    from bigchaindb.backend import connect
    from bigchaindb.common.exceptions import ConfigurationError

    conn = connect(ca_cert='/certs/ca.pem', certfile='/certs/client.crt', keyfile='/certs/client.key',
                   crlfile='/certs/crl.pem')
    with pytest.raises(ConfigurationError):
        conn.conn

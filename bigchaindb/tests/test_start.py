# Copyright © 2020 Interplanetary Database Association e.V.,
# BigchainDB and IPDB software contributors.
# SPDX-License-Identifier: (Apache-2.0 AND CC-BY-4.0)
# Code is Apache-2.0 and docs are CC-BY-4.0

from argparse import Namespace
from unittest.mock import patch


@patch('bigchaindb.start.setproctitle')
@patch('bigchaindb.start.Exchange')
@patch('bigchaindb.start.Process')
@patch('bigchaindb.start.server')
@patch('abci.server.ABCIServer')
def test_start__abci_server_listens_on_configured_host(abci_server, server, process, exchange, setproctitle,
                                                       monkeypatch):
    import bigchaindb
    from bigchaindb.start import start

    monkeypatch.setitem(bigchaindb.config['abci'], 'host', '192.0.2.1')
    start(Namespace(experimental_parallel_validation=False))
    assert abci_server.call_args.kwargs['host'] == '192.0.2.1'


def test_abci_server__listens_on_the_given_host():
    from abci import types_v0_31_5
    from abci.application import BaseApplication
    from abci.server import ABCIServer

    app = BaseApplication(types_v0_31_5)
    assert ABCIServer(app=app, host='127.0.0.1').server.address == ('127.0.0.1', 26658)

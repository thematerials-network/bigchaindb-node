# Copyright © 2020 Interplanetary Database Association e.V.,
# BigchainDB and IPDB software contributors.
# SPDX-License-Identifier: (Apache-2.0 AND CC-BY-4.0)
# Code is Apache-2.0 and docs are CC-BY-4.0

"""CheckTx answers Tendermint 0.31.5 with a code instead of killing the ABCI connection."""

import base64
import json
import time
from uuid import uuid4

import pytest
import requests

from bigchaindb.core import CodeTypeOk, CodeTypeError, CodeTypeInternalError
from tests.tendermint.test_core import (malformed_fulfillment_tx_bytes, rapidjson_rejected_tx_bytes,
                                        RAPIDJSON_ONLY_REJECTS, UNDECODABLE_INPUTS)

# Not `bdb`: its per-test flush empties `blocks`, which the running ABCI server reads in EndBlock.
pytestmark = pytest.mark.abci


def signed_create(metadata=None):
    from bigchaindb.models import Transaction
    from bigchaindb.common.crypto import generate_key_pair

    alice = generate_key_pair()
    return Transaction.create([alice.public_key], [([alice.public_key], 1)], metadata=metadata)\
                      .sign([alice.private_key])


def tx_bytes(tx):
    return json.dumps(tx.to_dict()).encode('utf8')


def broadcast(b, raw, method='broadcast_tx_sync'):
    payload = {'method': method, 'jsonrpc': '2.0', 'id': str(uuid4()),
               'params': [base64.b64encode(raw).decode('utf8')]}
    return requests.post(b.endpoint, json=payload).json()


def broadcast_code(b, raw):
    response = broadcast(b, raw)
    assert 'error' not in response, response
    return response['result']['code']


def wait_committed(b, transaction_id, timeout=60):
    for _ in range(timeout * 4):
        if b.get_transaction(transaction_id) is not None:
            return
        time.sleep(0.25)
    raise AssertionError('transaction {} was not committed within {}s'.format(transaction_id, timeout))


def wait_mempool_empty(b, timeout=60):
    for _ in range(timeout * 4):
        unconfirmed = requests.get(b.endpoint + 'unconfirmed_txs').json()['result']
        if unconfirmed['n_txs'] in (0, '0'):
            return
        time.sleep(0.25)
    raise AssertionError('mempool not empty within {}s'.format(timeout))


def test_a_backend_error_is_rejected_and_the_connection_survives(b, abci_failure):
    failing_tx, next_tx = signed_create(), signed_create()
    abci_failure.fail()
    assert broadcast_code(b, tx_bytes(failing_tx)) == CodeTypeInternalError
    abci_failure.clear()
    assert broadcast_code(b, tx_bytes(next_tx)) == CodeTypeOk
    wait_committed(b, next_tx.id)
    assert b.get_transaction(failing_tx.id) is None


def test_b_same_transaction_is_accepted_once_the_backend_recovers(b, abci_failure):
    tx = signed_create()
    abci_failure.fail()
    assert broadcast_code(b, tx_bytes(tx)) == CodeTypeInternalError
    abci_failure.clear()
    assert broadcast_code(b, tx_bytes(tx)) == CodeTypeOk
    wait_committed(b, tx.id)


def test_c_recheck_rejection_evicts_the_transaction_and_allows_resubmission(b, abci_failure):
    # Each fills a block (genesis max_bytes 64 kB), so the second is rechecked after the first commits.
    first, second = signed_create({'pad': 'x' * 40000}), signed_create({'pad': 'y' * 40000})
    abci_failure.fail(second.id, after_calls=1)
    assert broadcast_code(b, tx_bytes(first)) == CodeTypeOk
    assert broadcast_code(b, tx_bytes(second)) == CodeTypeOk
    wait_committed(b, first.id)
    wait_mempool_empty(b)
    assert abci_failure.hits() == [second.id], 'the second transaction was not rejected by a recheck'
    assert b.get_transaction(second.id) is None
    abci_failure.clear()
    assert broadcast_code(b, tx_bytes(second)) == CodeTypeOk
    wait_committed(b, second.id)


def bad_output_index_tx_bytes(b):
    from bigchaindb.models import Transaction

    create_tx = signed_create()
    assert broadcast_code(b, tx_bytes(create_tx)) == CodeTypeOk
    wait_committed(b, create_tx.id)
    owner = create_tx.outputs[0].public_keys[0]
    transfer = Transaction.transfer(create_tx.to_inputs(), [([owner], 1)], asset_id=create_tx.id).to_dict()
    transfer['inputs'][0]['fulfills']['output_index'] = 5
    transfer['id'] = None
    transfer['id'] = Transaction._to_hash(Transaction._to_str(transfer))
    return json.dumps(transfer).encode('utf8')


def test_d_malformed_inputs_are_rejected_and_valid_ones_still_commit(b):
    assert broadcast_code(b, malformed_fulfillment_tx_bytes()) == CodeTypeError
    for field, value in RAPIDJSON_ONLY_REJECTS:
        assert broadcast_code(b, rapidjson_rejected_tx_bytes(field, value)) == CodeTypeError
    for param in UNDECODABLE_INPUTS:
        assert broadcast_code(b, param.values[0]) == CodeTypeInternalError, param.id
    assert broadcast_code(b, bad_output_index_tx_bytes(b)) in (CodeTypeError, CodeTypeInternalError)
    valid = signed_create()
    assert broadcast_code(b, tx_bytes(valid)) == CodeTypeOk
    wait_committed(b, valid.id)
    wrong_signature = signed_create().to_dict()
    wrong_signature['inputs'][0]['fulfillment'] = signed_create().to_dict()['inputs'][0]['fulfillment']
    assert broadcast_code(b, json.dumps(wrong_signature).encode('utf8')) == CodeTypeError

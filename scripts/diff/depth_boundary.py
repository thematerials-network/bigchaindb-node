"""Nesting-depth sweep: at which metadata depth does validation stop accepting and start raising?

Usage: python depth_boundary.py <first> <last> <out.json>   (needs MongoDB, as run_corpus.py)
Records, per depth, the tx id and the outcome of Transaction.from_dict and BigchainDB.is_valid_transaction
(as CheckTx calls them) at the default recursion limit.
"""
import json
import sys

from bigchaindb import config_utils

config_utils.autoconfigure(force=True)

from bigchaindb import BigchainDB  # noqa: E402
from bigchaindb.backend import schema  # noqa: E402
from bigchaindb.common.crypto import key_pair_from_ed25519_key  # noqa: E402
from bigchaindb.models import Transaction  # noqa: E402

alice = key_pair_from_ed25519_key('11' * 32)
bigchain = BigchainDB()
bigchain.connection.conn.drop_database('bigchain')
schema.init_database(bigchain.connection)
default_limit = sys.getrecursionlimit()


def outcome(function):
    try:
        value = function()
        return 'ok' if value else repr(value)
    except RecursionError:
        return 'RecursionError'
    except Exception as error:  # noqa: B902
        return type(error).__name__


results = {}
for depth in range(int(sys.argv[1]), int(sys.argv[2]) + 1):
    metadata = 'leaf'
    for _ in range(depth):
        metadata = {'n': metadata}
    sys.setrecursionlimit(50000)
    raw = json.dumps(Transaction.create([alice.public_key], [([alice.public_key], 1)], metadata=metadata,
                                        asset={'depth': depth}).sign([alice.private_key]).to_dict())
    sys.setrecursionlimit(default_limit)
    results[depth] = {'raw_sha_prefix': raw[-80:],
                      'from_dict': outcome(lambda: Transaction.from_dict(json.loads(raw))),
                      'is_valid_transaction': outcome(lambda: bigchain.is_valid_transaction(json.loads(raw)))}
json.dump(results, open(sys.argv[3], 'w'), indent=1, sort_keys=True)
transitions = [(depth, value) for depth, value in sorted(results.items())
               if depth == min(results) or value['from_dict'] != results[depth - 1]['from_dict']
               or value['is_valid_transaction'] != results[depth - 1]['is_valid_transaction']]
for depth, value in transitions:
    print(depth, value['from_dict'], value['is_valid_transaction'])

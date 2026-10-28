"""Runs the differential corpus through one BigchainDB environment and writes everything observable.

Usage: python run_corpus.py <corpus.json> <out.json>
Env: BIGCHAINDB_DATABASE_HOST / _PORT / _NAME (the database is dropped and re-created).

Per case, offline: JSON decode, Transaction.from_dict (schema + id), tx id, serialized bytes.
Chain: InitChain, then per block CheckTx of every tx against committed state, BeginBlock, DeliverTx in
order (same-block transactions visible), EndBlock, Commit; app hash per block. ABCI calls run on
bigchaindb.core.App directly (no Tendermint), so a crash is recorded instead of killing a connection.
Final: validate_transaction and CheckTx of every case against the final state, every committed tx read
back, every MongoDB collection (without _id) and its indexes.
"""
import base64
import hashlib
import json
import logging
import platform
import sys

import bigchaindb
from bigchaindb import config_utils

config_utils.autoconfigure(force=True)

import abci.server  # noqa: E402,F401 - the ABCI process imports it (gevent); gevent 20.6.2 sets flush-to-zero
from abci import types_v0_31_5 as types  # noqa: E402
from bson import json_util  # noqa: E402

from bigchaindb import App, BigchainDB  # noqa: E402
from bigchaindb.backend import schema  # noqa: E402
from bigchaindb.common import memoize  # noqa: E402
from bigchaindb.common.utils import serialize  # noqa: E402
from bigchaindb.models import Transaction  # noqa: E402

VALIDATOR_PUBLIC_KEY = bytes(range(32))


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        if record.name.startswith('bigchaindb') and record.levelno >= logging.INFO:
            self.records.append('%s %s %s' % (record.levelname, record.name, record.getMessage()))


capture = Capture()
logging.getLogger().addHandler(capture)
logging.getLogger().setLevel(logging.DEBUG)


def describe_exception(error):
    message = str(error)
    return {'exception': '%s.%s' % (type(error).__module__, type(error).__name__),
            'message': message if len(message) <= 2000 else message[:2000] + '…(%d chars)' % len(message)}


def observe(function, *args):
    capture.records = []
    try:
        result = {'result': function(*args)}
    except BaseException as error:  # noqa: B902 - crashes are what we compare
        if isinstance(error, KeyboardInterrupt):
            raise
        result = describe_exception(error)
    result['logs'] = capture.records
    return result


def digest(text):
    data = text.encode('utf8', 'surrogatepass')
    return {'sha256': hashlib.sha256(data).hexdigest(), 'length': len(data), 'head': text[:120]}


def offline(raw):
    out = {}
    decoded = observe(lambda: json.loads(raw.decode('utf8')))
    out['decode'] = {key: value for key, value in decoded.items() if key != 'result'}
    if 'result' not in decoded:
        return out
    tx_dict = decoded['result']
    out['decode']['type'] = type(tx_dict).__name__

    def from_dict():
        tx = Transaction.from_dict(tx_dict)
        return {'id': tx.id, 'serialized': digest(tx.serialized),
                'to_dict_equal_input': tx.to_dict() == tx_dict}
    out['from_dict'] = observe(from_dict)
    out['serialize'] = observe(lambda: digest(serialize(tx_dict)))
    return out


def code(response):
    return {'code': response.code}


def main():
    corpus = json.load(open(sys.argv[1]))
    raws = {case['name']: base64.b64decode(case['raw_b64']) for case in corpus['cases']}
    result = {'environment': {'python': sys.version, 'machine': platform.machine(),
                              'bigchaindb': bigchaindb.__version__, 'subnormal_5e-324': 5e-324 * 1.0}}

    bigchain = BigchainDB()
    bigchain.connection.conn.drop_database(bigchaindb.config['database']['name'])
    schema.init_database(bigchain.connection)

    result['offline'] = {name: offline(raw) for name, raw in raws.items()}

    app = App(types, bigchain)
    validator = types.ValidatorUpdate(power=10, pub_key=types.PubKey(type='ed25519', data=VALIDATOR_PUBLIC_KEY))
    result['init_chain'] = observe(lambda: str(app.init_chain(
        types.RequestInitChain(validators=[validator], chain_id='diff-chain'))))

    blocks = []
    for height, names in enumerate(corpus['blocks'], start=1):
        block = {'height': height, 'check_tx': {}, 'deliver_tx': []}
        for name in names:
            block['check_tx'][name] = observe(lambda: code(app.check_tx(raws[name])))
        block['begin_block'] = observe(lambda: str(app.begin_block(types.RequestBeginBlock())))
        for name in names:
            block['deliver_tx'].append([name, observe(lambda: code(app.deliver_tx(raws[name])))])
        block['end_block'] = observe(lambda: str(app.end_block(types.RequestEndBlock(height=height))))
        block['commit'] = observe(lambda: app.commit().data.decode())
        block['accepted'] = list(app.block_txn_ids)
        blocks.append(block)
    result['blocks'] = blocks

    def validate(name):
        tx_dict = json.loads(raws[name].decode('utf8'))
        valid = bigchain.validate_transaction(tx_dict)
        return valid if valid is False else valid.id
    result['final'] = {name: {'validate_transaction': observe(validate, name),
                              'check_tx': observe(lambda: code(app.check_tx(raws[name])))}
                       for name in raws}

    # store_bulk_transactions mutates the memoized dicts in place (pops asset/metadata, pymongo adds `_id`);
    # the API process has its own caches, so read back without these.
    memoize.from_dict.cache_clear()
    memoize.to_dict.cache_clear()
    committed = [txid for block in blocks for txid in block['accepted']]
    result['read_back'] = {txid: observe(lambda: serialize(bigchain.get_transaction(txid).to_dict()))
                           for txid in committed}

    database = bigchain.connection.conn[bigchaindb.config['database']['name']]
    dump = {}
    for collection_name in sorted(database.list_collection_names()):
        collection = database[collection_name]
        documents = [json_util.dumps(document, json_options=json_util.CANONICAL_JSON_OPTIONS)
                     for document in collection.find({}, {'_id': False})]
        indexes = {name: json_util.dumps(info, json_options=json_util.CANONICAL_JSON_OPTIONS, sort_keys=True)
                   for name, info in collection.index_information().items()}
        dump[collection_name] = {'documents': sorted(documents), 'indexes': indexes}
    result['mongodb'] = dump

    with open(sys.argv[2], 'w') as out:
        json.dump(result, out, indent=1, sort_keys=True, default=repr)
        out.write('\n')
    print('done:', len(raws), 'cases,', len(blocks), 'blocks, app hashes',
          [block['commit'].get('result') for block in blocks])


if __name__ == '__main__':
    main()

"""Builds the differential transaction corpus (deterministic: fixed keys, ed25519 signatures are deterministic).

Usage: python make_corpus.py <out.json>
Runs under both the old (2.2.2 / Python 3.9) and the new environment; the two outputs must be byte-identical.

Output: {"keys": {name: public_key}, "cases": [{"name", "raw_b64", "note"}], "blocks": [[case name, ...], ...]}
Cases not listed in any block are only run offline and against the final state.
"raw_b64" is the exact transaction bytes as Tendermint hands them to CheckTx/DeliverTx.
"""
import base64
import copy
import hashlib
import json
import sys

import base58
from cryptoconditions import Ed25519Sha256

from bigchaindb.common.crypto import key_pair_from_ed25519_key
from bigchaindb.models import Transaction

KEYS = {name: key_pair_from_ed25519_key(hashlib.sha256(name.encode()).hexdigest())
        for name in ('alice', 'bob', 'carol', 'dave', 'eve')}
PUB = {name: pair.public_key for name, pair in KEYS.items()}
PRIV = {name: pair.private_key for name, pair in KEYS.items()}
sys.setrecursionlimit(20000)  # only so the generator can build the 2000-deep case

cases = []
blocks = []


def add(name, raw, note=''):
    if isinstance(raw, dict):
        raw = json.dumps(raw)
    if isinstance(raw, str):
        raw = raw.encode('utf8')
    cases.append({'name': name, 'raw_b64': base64.b64encode(raw).decode(), 'note': note})
    return name


def rehash(tx):
    body = copy.deepcopy(tx)
    body['id'] = None
    tx['id'] = Transaction._to_hash(Transaction._to_str(body))
    return tx


def create(signers, recipients, metadata=None, asset=None):
    tx = Transaction.create([PUB[s] for s in signers],
                            [([PUB[r] if isinstance(r, str) else [PUB[x] for x in r] for r in keys], amount)
                             for keys, amount in recipients],
                            metadata=metadata, asset=asset)
    return tx.sign([PRIV[s] for s in signers]).to_dict()


def transfer(spends, recipients, asset_id, signers, metadata=None):
    inputs = []
    for tx, index in spends:
        inputs.extend(Transaction.from_dict(tx).to_inputs([index]))
    tx = Transaction.transfer(inputs,
                              [([PUB[r] if isinstance(r, str) else [PUB[x] for x in r] for r in keys], amount)
                               for keys, amount in recipients],
                              asset_id, metadata=metadata)
    return tx.sign([PRIV[s] for s in signers]).to_dict()


def nested(depth):
    value = 'leaf'
    for _ in range(depth):
        value = {'n': value}
    return value


# Block 1: valid CREATEs and invalid transactions with a fresh state.
c_simple = create(['alice'], [(['alice'], 1)], metadata={'case': 'simple'}, asset={'kind': 'simple'})
c_multi = create(['alice'], [(['alice'], 3), (['bob'], 2)], asset={'kind': 'multi-output'})
c_thresh = create(['alice'], [(['bob', 'carol'], 1)], asset={'kind': 'threshold 2-of-2'})
# Nested public_keys lists fail the output schema (strings only), so this CREATE is expected invalid.
c_nested = create(['alice'], [(['bob', ['carol', 'dave']], 1)], asset={'kind': 'nested threshold'})
c_multisig = create(['alice', 'bob'], [(['alice'], 1)], asset={'kind': 'two signers'})
c_unicode = create(['alice'], [(['alice'], 1)],
                   metadata={'text': 'Grüße 漢字 العربية 🚀 é ​', 'emoji_key_🔑': '✓'},
                   asset={'name': 'ünïcödé', 'cjk': '钢材证书', 'rtl': 'שלום'})
c_large = create(['alice'], [(['alice'], 1)],
                 metadata={'blob': 'x' * 200000, 'list': list(range(5000))},
                 asset={'rows': [{'i': i, 'v': 'value-%d' % i} for i in range(2000)]})
c_floats = create(['alice'], [(['alice'], 1)],
                  metadata={'f': 0.1, 'g': 1e-7, 'h': 1.5e300, 'i': -0.0, 'j': 100.0, 'k': 1.7976931348623157e308,
                            'l': 4.9e-300, 'm': 123456789012345678, 'n': 2 ** 63 - 1, 'o': -2 ** 63, 'p': 0.30000000000000004},
                  asset={'nested': {'a': [1, [2, [3, {'b': None, 'c': True, 'd': False}]]], 'e': {}}})
c_deep = create(['alice'], [(['alice'], 1)], metadata=nested(150), asset={'kind': 'deep metadata 150'})
c_maxamount = create(['alice'], [(['alice'], 9 * 10 ** 18)], asset={'kind': 'max amount'})
c_nullasset = create(['alice'], [(['alice'], 1)], metadata=None, asset=None)
c_emptyasset = create(['alice'], [(['alice'], 1)], metadata={}, asset={})
c_order = create(['alice'], [(['alice'], 1)], metadata={'z': 1, 'a': 2, 'm': {'y': 1, 'b': 2}}, asset={'kind': 'key order'})

add('create_simple', c_simple)
add('create_multi_output', c_multi)
add('create_threshold', c_thresh)
add('create_nested_threshold', c_nested)
add('create_two_signers', c_multisig)
add('create_unicode', c_unicode)
add('create_large', c_large)
add('create_floats_nested', c_floats)
add('create_deep_150', c_deep)
add('create_max_amount', c_maxamount)
add('create_null_asset_metadata', c_nullasset)
add('create_empty_asset_metadata', c_emptyasset)
# Same transaction, keys in reverse order and compact separators: id must still match.
reordered = json.loads(json.dumps(c_order), object_pairs_hook=lambda pairs: dict(reversed(pairs)))
add('create_key_order_reversed', json.dumps(reordered, separators=(',', ':')))
# ensure_ascii=False raw (UTF-8 bytes on the wire instead of \u escapes).
c_utf8 = create(['alice'], [(['alice'], 1)], metadata={'raw': 'Grüße 🚀'}, asset={'kind': 'raw utf8'})
add('create_raw_utf8', json.dumps(c_utf8, ensure_ascii=False))
# Duplicate key, last one wins in json.loads: the first "metadata" is junk, the second is the signed one.
c_dup = create(['alice'], [(['alice'], 1)], metadata={'dup': 'real'}, asset={'kind': 'duplicate key'})
dup_raw = json.dumps(c_dup)
add('create_duplicate_key_last_valid', dup_raw.replace('"metadata": ', '"metadata": {"dup": "junk"}, "metadata": ', 1))
add('create_duplicate_key_last_invalid', dup_raw[:-1] + ', "metadata": {"dup": "junk"}}')

# Amount edge cases (outputs[].amount is a string of digits, 1 .. 9e18).
for label, amount in [('zero', '0'), ('negative', '-1'), ('too_large', '9000000000000000001'), ('leading_zero', '01'),
                      ('float', '1.0'), ('space', ' 1'), ('int_type', 1), ('empty', ''), ('huge', '9' * 40)]:
    tx = create(['alice'], [(['alice'], 1)], asset={'kind': 'amount ' + label})
    tx['outputs'][0]['amount'] = amount
    add('create_amount_' + label, rehash(tx))

# Schema and id violations.
bad = copy.deepcopy(c_simple)
bad['id'] = '0' * 64
add('invalid_hash', bad)
bad = copy.deepcopy(c_simple)
del bad['id']
add('missing_id', bad)
bad = copy.deepcopy(c_simple)
bad['version'] = '1.0'
add('wrong_version', rehash(bad))
bad = copy.deepcopy(c_simple)
bad['operation'] = 'DESTROY'
add('unknown_operation', rehash(bad))
bad = copy.deepcopy(c_simple)
del bad['metadata']
add('missing_metadata', rehash(bad))
bad = copy.deepcopy(c_simple)
bad['extra'] = 1
add('extra_top_level_field', rehash(bad))
bad = copy.deepcopy(c_simple)
bad['outputs'] = []
add('no_outputs', rehash(bad))
bad = copy.deepcopy(c_simple)
bad['inputs'][0]['owners_before'] = []
add('no_owners_before', rehash(bad))
for label, key in [('dollar', '$where'), ('dot', 'a.b'), ('null_char', 'a\u0000b')]:
    tx = create(['alice'], [(['alice'], 1)], metadata={'ok': {key: 1}}, asset={'kind': 'bad key ' + label})
    add('create_metadata_key_' + label, tx)
tx = create(['alice'], [(['alice'], 1)], asset={'data_key': {'$set': 1}})
add('create_asset_key_dollar', tx)
add('create_deep_2000', create(['alice'], [(['alice'], 1)], metadata=nested(2000), asset={'kind': 'deep 2000'}))
tx = create(['alice'], [(['alice'], 1)], asset={'kind': 'nan'})
tx['metadata'] = {'nan': float('nan')}
add('create_metadata_nan', json.dumps(rehash(tx)))
tx = create(['alice'], [(['alice'], 1)], asset={'kind': 'infinity'})
tx['metadata'] = {'inf': float('inf')}
add('create_metadata_infinity', json.dumps(rehash(tx)))
tx = create(['alice'], [(['alice'], 1)], asset={'kind': 'lone surrogate'})
raw = json.dumps(tx).replace('"lone surrogate"', '"lone \\ud800 surrogate"')
add('create_lone_surrogate_unsigned', raw, 'id/signature over the original text, so expected invalid')

# Signatures and fulfillments.
bad = copy.deepcopy(c_simple)
other = create(['eve'], [(['eve'], 1)], metadata={'case': 'simple'}, asset={'kind': 'simple'})
bad['inputs'][0]['fulfillment'] = other['inputs'][0]['fulfillment']
add('invalid_signature_wrong_key', rehash(bad))
bad = copy.deepcopy(c_simple)
fulfillment = bad['inputs'][0]['fulfillment']
bad['inputs'][0]['fulfillment'] = fulfillment[:-4] + ('AAAA' if fulfillment[-4:] != 'AAAA' else 'BBBB')
add('invalid_signature_flipped_bytes', rehash(bad))
for label, value in [('zeros_64', '0' * 64), ('empty', ''), ('not_base64', '!!!!'), ('truncated', fulfillment[:20]),
                     ('random_b64', 'pGSAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'), ('null', None), ('int', 7)]:
    bad = copy.deepcopy(c_simple)
    bad['inputs'][0]['fulfillment'] = value
    add('malformed_fulfillment_' + label, rehash(bad))

# Not a transaction at all (decode_transaction runs before validation).
add('raw_not_json', b'this is not json')
add('raw_invalid_utf8', b'\xff\xfe{"id": 1}')
add('raw_json_array', b'[1, 2, 3]')
add('raw_json_string', b'"tx"')
add('raw_empty', b'')

blocks.append([c['name'] for c in cases])

# Block 2: TRANSFERs against block 1, plus same-block dependencies and conflicts.
t_simple = transfer([(c_simple, 0)], [(['bob'], 1)], c_simple['id'], ['alice'], metadata={'step': 'alice->bob'})
t_simple_conflict = transfer([(c_simple, 0)], [(['carol'], 1)], c_simple['id'], ['alice'], metadata={'step': 'conflict'})
t_chain = transfer([(t_simple, 0)], [(['carol'], 1)], c_simple['id'], ['bob'], metadata={'step': 'same-block child'})
t_multi_in = transfer([(c_multi, 0)], [(['carol'], 2), (['dave'], 1)], c_multi['id'], ['alice'])
t_thresh = transfer([(c_thresh, 0)], [(['alice'], 1)], c_thresh['id'], ['bob', 'carol'])
t_thresh_tampered = copy.deepcopy(t_thresh)
t_thresh_tampered['metadata'] = {'tampered': True}
# eve claims alice's output: owners_before and fulfillment are eve's, the spent condition is alice's.
wrong_inputs = Transaction.from_dict(c_multisig).to_inputs([0])
wrong_inputs[0].owners_before = [PUB['eve']]
wrong_inputs[0].fulfillment = Ed25519Sha256(public_key=base58.b58decode(PUB['eve']))
t_wrong_signer = Transaction.transfer(wrong_inputs, [([PUB['eve']], 1)], c_multisig['id']).sign([PRIV['eve']]).to_dict()
t_amount_mismatch = transfer([(c_maxamount, 0)], [(['bob'], 1)], c_maxamount['id'], ['alice'])
t_split = transfer([(c_maxamount, 0)], [(['bob'], 4 * 10 ** 18), (['carol'], 5 * 10 ** 18)], c_maxamount['id'], ['alice'])
t_wrong_asset = transfer([(c_unicode, 0)], [(['bob'], 1)], c_large['id'], ['alice'])
c_twice = create(['alice'], [(['alice'], 1)], asset={'kind': 'twice in one block'})
t_missing_input_tx = copy.deepcopy(t_simple)
t_missing_input_tx['inputs'][0]['fulfills']['transaction_id'] = 'f' * 64
t_bad_output_index = copy.deepcopy(t_simple)
t_bad_output_index['inputs'][0]['fulfills']['output_index'] = 5
block2 = [
    add('transfer_simple', t_simple),
    add('transfer_conflict_same_block', t_simple_conflict),
    add('transfer_child_same_block', t_chain),
    add('transfer_multi_output_spend', t_multi_in),
    add('transfer_threshold_both', t_thresh),
    add('transfer_threshold_tampered', rehash(t_thresh_tampered)),
    add('transfer_wrong_signer', t_wrong_signer),
    add('transfer_amount_mismatch', t_amount_mismatch),
    add('transfer_split_max_amount', t_split),
    add('transfer_wrong_asset_id', t_wrong_asset),
    add('transfer_unknown_input_tx', rehash(t_missing_input_tx)),
    add('transfer_bad_output_index', rehash(t_bad_output_index)),
    add('create_twice_same_block_1', c_twice),
    add('create_twice_same_block_2', copy.deepcopy(c_twice)),
]
blocks.append(block2)

# Block 3: resubmission and double spends against committed state; multi-input transfer.
t_double = transfer([(c_simple, 0)], [(['dave'], 1)], c_simple['id'], ['alice'], metadata={'step': 'double spend'})
t_two_inputs = transfer([(t_split, 0), (t_split, 1)], [(['dave'], 9 * 10 ** 18)], c_maxamount['id'], ['bob', 'carol'])
block3 = [
    add('create_simple_resubmitted', copy.deepcopy(c_simple)),
    add('transfer_double_spend_committed', t_double),
    add('transfer_simple_resubmitted', copy.deepcopy(t_simple)),
    add('transfer_two_inputs', t_two_inputs),
]
blocks.append(block3)

# Block 4: empty block (app hash must carry over unchanged).
blocks.append([])

# Block 5: subnormal floats. gevent 20.6.2 (old ABCI process) flushes them to 0.0, so the recomputed id differs.
blocks.append([
    add('create_subnormal_metadata', create(['alice'], [(['alice'], 1)], metadata={'x': 5e-324},
                                            asset={'kind': 'subnormal metadata'})),
    add('create_subnormal_asset', create(['alice'], [(['alice'], 1)], asset={'kind': 'subnormal asset', 'x': 1e-310})),
    add('create_smallest_normal', create(['alice'], [(['alice'], 1)], metadata={'x': 2.2250738585072014e-308},
                                         asset={'kind': 'smallest normal'})),
    add('create_after_subnormals', create(['alice'], [(['alice'], 1)], asset={'kind': 'after subnormals'})),
])

# Blocks 6 and 7: valid transactions MongoDB cannot store (integer beyond int64; nesting beyond MongoDB's
# limit). Validation accepts them and Commit crashes, so each goes last, alone.
c_bigint = create(['alice'], [(['alice'], 1)], metadata={'n': 2 ** 63}, asset={'kind': 'int beyond int64'})
blocks.append([add('create_int_beyond_int64', c_bigint)])
c_deep_mongo = create(['alice'], [(['alice'], 1)], metadata=nested(200), asset={'kind': 'deep metadata 200'})
blocks.append([add('create_deep_200', c_deep_mongo)])

# Not in any block (validated against the final state only): nesting-depth sweep for parser/recursion limits.
for depth in (170, 175, 180, 185, 190, 250, 500, 900, 950, 970, 980, 985, 990, 995, 1000, 1100, 1500):
    add('depth_sweep_%d' % depth, create(['alice'], [(['alice'], 1)], metadata=nested(depth),
                                          asset={'kind': 'depth sweep %d' % depth}))

# Not in any block: rapidjson's pattern rejects a trailing newline, jsonschema's re.search accepts it.
tx = create(['alice'], [(['alice'], 1)], asset={'kind': 'version newline'})
tx['version'] = '2.0\n'
add('create_version_newline', rehash(tx))

names = [c['name'] for c in cases]
assert len(names) == len(set(names)), 'duplicate case names'
with open(sys.argv[1], 'w') as out:
    json.dump({'keys': PUB, 'cases': cases, 'blocks': blocks}, out, indent=1, sort_keys=True)
    out.write('\n')

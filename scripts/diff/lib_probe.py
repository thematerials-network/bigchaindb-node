"""Library probes for the consensus-path jumps (platform docs/specs/2026-10-27-bcdb-consensus-library-audit.md
§1.2.A, §1.2.B, §2.2.1, §2.2.3, §4.3), plus the libsodium version PyNaCl links.

Usage:
  python lib_probe.py make <fixed.json>             transactions built once (on the fork), evaluated on both sides
  python lib_probe.py run <fixed.json> <out.json>   everything else, plus Transaction.from_dict of the fixed txs
No database needed. Compare two outputs with compare.py.
"""
import copy
import glob
import hashlib
import json
import os
import subprocess
import sys
import warnings

import abci.server  # noqa: F401 - as in the ABCI process
import base58
import jsonschema
import nacl
import nacl.bindings
import rapidjson
import yaml

from bigchaindb.common import schema as tx_schema
from bigchaindb.common.crypto import key_pair_from_ed25519_key
from bigchaindb.common.utils import serialize
from bigchaindb.models import Transaction

alice = key_pair_from_ed25519_key(hashlib.sha256(b'alice').hexdigest())


def outcome(function, *args):
    try:
        value = function(*args)
    except BaseException as error:  # noqa: B902
        if isinstance(error, KeyboardInterrupt):
            raise
        return {'exception': '%s.%s' % (type(error).__module__, type(error).__name__), 'message': str(error)[:200]}
    if isinstance(value, (bytes, bytearray)):
        value = 'bytes:' + bytes(value).hex()
    return {'result': value}


def create(metadata=None, asset=None):
    return Transaction.create([alice.public_key], [([alice.public_key], 1)], metadata=metadata,
                              asset=asset).sign([alice.private_key]).to_dict()


def make(path):
    fixed = {
        'nul_keys_ab_first': json.dumps(create(metadata={'a\u0000b': 1, 'a\u0000a': 2})),
        'nul_keys_aa_first': json.dumps(create(metadata={'a\u0000a': 2, 'a\u0000b': 1})),
        'nul_keys_in_asset': json.dumps(create(asset={'k': {'a\u0000b': 1, 'a\u0000a': 2}})),
        'nul_key_single': json.dumps(create(metadata={'a\u0000b': 1})),
    }
    json.dump(fixed, open(path, 'w'), indent=1, sort_keys=True)


def libsodium():
    info = {'pynacl': getattr(nacl, '__version__', None)}
    for name in ('sodium_version_string',):
        function = getattr(nacl.bindings, name, None) or getattr(getattr(nacl.bindings, 'lib', None), name, None)
        if function is not None:
            value = function()
            info[name] = value.decode() if isinstance(value, bytes) else value
    try:
        from nacl._sodium import ffi, lib
        info['lib.sodium_version_string'] = ffi.string(lib.sodium_version_string()).decode()
    except Exception as error:  # noqa: B902
        info['lib.sodium_version_string'] = repr(error)
    so = glob.glob(os.path.join(os.path.dirname(nacl.__file__), '_sodium*.so'))
    if so:
        ldd = subprocess.run(['ldd', so[0]], capture_output=True, text=True).stdout
        info['ldd_libsodium'] = [line.strip() for line in ldd.splitlines() if 'sodium' in line] or 'statically bundled'
    return info


def check_schemas():
    results = {}
    for path in sorted(glob.glob(os.path.join(os.path.dirname(tx_schema.__file__), '*.yaml'))):
        schema = yaml.safe_load(open(path))
        validator = jsonschema.validators.validator_for(schema)
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            results[os.path.basename(path)] = {
                'validator': validator.__name__,
                'check_schema': outcome(validator.check_schema, schema),
                'rapidjson_validator': outcome(lambda: type(rapidjson.Validator(rapidjson.dumps(schema))).__name__),
            }
    return results


def nul_keys(fixed):
    out = {}
    for label, value in [('ab_first', {'a\u0000b': 1, 'a\u0000a': 2}), ('aa_first', {'a\u0000a': 2, 'a\u0000b': 1}),
                         ('nested', {'m': {'a\u0000b': 1, 'a\u0000a': 2}}), ('three', {'x\u0000c': 3, 'x\u0000a': 1,
                                                                                         'x\u0000b': 2})]:
        text = serialize(value)
        out['serialize_' + label] = {'text': text, 'sha3': hashlib.sha3_256(text.encode()).hexdigest()}
    for name, raw in sorted(fixed.items()):
        tx = json.loads(raw)
        out['from_dict_' + name] = outcome(lambda: Transaction.from_dict(copy.deepcopy(tx)).id)
        out['validate_id_' + name] = outcome(Transaction.validate_id, copy.deepcopy(tx))
    return out


def first_failure(function, low, high):
    """Smallest n in [low, high] for which function(n) raises (assumes monotone), with its exception."""
    if 'exception' not in outcome(function, high):
        return {'none_up_to': high}
    while low < high:
        middle = (low + high) // 2
        if 'exception' in outcome(function, middle):
            high = middle
        else:
            low = middle + 1
    return {'first_failing_depth': low, 'exception': outcome(function, low)['exception']}


def nested_dict(depth):
    value = 1
    for _ in range(depth):
        value = {'k': value}
    return value


def depth_sweep():
    return {
        'recursion_limit': sys.getrecursionlimit(),
        'rapidjson_loads_lists': first_failure(lambda n: rapidjson.loads('[' * n + ']' * n), 1, 20000),
        'rapidjson_loads_dicts': first_failure(lambda n: rapidjson.loads('{"k":' * n + '1' + '}' * n), 1, 20000),
        'rapidjson_dumps_dicts': first_failure(lambda n: rapidjson.dumps(nested_dict(n)), 1, 20000),
        'rapidjson_loads_of_dumps': first_failure(lambda n: rapidjson.loads(rapidjson.dumps(nested_dict(n))), 1, 20000),
        'json_loads_dicts': first_failure(lambda n: json.loads('{"k":' * n + '1' + '}' * n), 1, 20000),
    }


def threshold_sweep():
    tx = create()
    out = {}
    for depth in (20, 50, 100, 150, 250, 400, 1000):
        details = {'type': 'ed25519-sha-256', 'public_key': 'x'}
        for _ in range(depth):
            details = {'type': 'threshold-sha-256', 'threshold': 1, 'subconditions': [details]}
        body = copy.deepcopy(tx)
        body['outputs'][0]['condition']['details'] = details
        out[depth] = outcome(tx_schema.validate_transaction_schema, body)
    return out


def base58_probe():
    key = base58.b58encode(bytes(range(32))).decode()
    inputs = {
        'valid_key': key, 'space_suffix': key + ' ', 'newline_suffix': key + '\n', 'tab_suffix': key + '\t',
        'nbsp_suffix': key + ' ', 'emspace_suffix': key + ' ', 'leading_space': ' ' + key,
        'inner_space': key[:10] + ' ' + key[10:], 'char_0': key[:-1] + '0', 'char_O': key[:-1] + 'O',
        'char_I': key[:-1] + 'I', 'char_l': key[:-1] + 'l', 'non_ascii': key[:-1] + 'é', 'empty': '',
        'ones_5': '11111', 'bytes_input': key.encode(),
    }
    out = {'decode_' + name: outcome(base58.b58decode, value) for name, value in inputs.items()}
    for name, value in {'empty': b'', 'zeros_3': b'\0' * 3, 'zeros_payload': b'\0\0' + bytes(range(1, 31)),
                        'key_33': bytes(range(33)), 'random_32': hashlib.sha256(b'seed').digest()}.items():
        out['encode_' + name] = outcome(base58.b58encode, value)
        out['roundtrip_' + name] = outcome(lambda: base58.b58decode(base58.b58encode(value)) == value)
    return out


def run(fixed_path, out_path):
    fixed = json.load(open(fixed_path))
    result = {
        'environment': {'python': sys.version.split()[0], 'rapidjson': rapidjson.__version__,
                        'jsonschema': getattr(jsonschema, '__version__', None), 'base58': getattr(base58, '__version__', None),
                        'libsodium': libsodium()},
        'check_schema': check_schemas(),
        'nul_keys': nul_keys(fixed),
        'depth': depth_sweep(),
        'threshold_nesting': threshold_sweep(),
        'base58': base58_probe(),
    }
    json.dump(result, open(out_path, 'w'), indent=1, sort_keys=True)
    print('done')


if __name__ == '__main__':
    sys.setrecursionlimit(sys.getrecursionlimit())
    if sys.argv[1] == 'make':
        make(sys.argv[2])
    else:
        run(sys.argv[2], sys.argv[3])

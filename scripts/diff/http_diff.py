"""Step 5: the same HTTP requests against a running node (scripts/diff/node.sh); writes status, relevant headers
and body per request. Compare two outputs with compare.py.

Usage: python3 http_diff.py <corpus.json> <api port> <rpc port> <out.json> [--crash]
--crash additionally posts the int-beyond-int64 CREATE last (expected to stop the node) and records the aftermath.
Standard library only (runs on the host). Ports in bodies are normalised to <port> so old and new compare.
"""
import base64
import json
import re
import sys
import time
import urllib.error
import urllib.request

corpus = json.load(open(sys.argv[1]))
raws = {case['name']: base64.b64decode(case['raw_b64']) for case in corpus['cases']}
txs = {}
for name, raw in raws.items():
    try:
        txs[name] = json.loads(raw)
    except (ValueError, RecursionError):
        pass
api, rpc, out_path = sys.argv[2], sys.argv[3], sys.argv[4]
base = 'http://127.0.0.1:%s' % api
HEADERS = ('content-type', 'content-length', 'access-control-allow-origin', 'access-control-allow-methods',
           'access-control-allow-headers', 'allow', 'location', 'vary')
results = {}


def call(name, method, path, body=None, headers=None, timeout=60):
    request = urllib.request.Request(base + path, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, raw_headers, data = response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        status, raw_headers, data = error.code, error.headers, error.read()
    except Exception as error:  # noqa: B902
        results[name] = {'request': [method, path], 'error': repr(error)}
        return None
    text = re.sub(r':\d{5}\b', ':<port>', data.decode('utf8', 'replace'))
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    results[name] = {
        'request': [method, path, (body or b'')[:80].decode('utf8', 'replace'), headers or {}],
        'status': status,
        'headers': {key: re.sub(r':\d{5}\b', ':<port>', value) for key, value in raw_headers.items()
                    if key.lower() in HEADERS and not (key.lower() == 'content-length' and parsed is not None)},
        'json': parsed,
        'raw_body': text if len(text) < 4000 else text[:4000] + '…(%d chars)' % len(text),
    }
    return parsed


JSON = {'Content-Type': 'application/json'}


def post_tx(name, case, mode=None, headers=JSON, body=None):
    query = '' if mode is None else '?mode=' + mode
    return call(name, 'POST', '/api/v1/transactions' + query, raws[case] if body is None else body, headers)


def wait_committed(txid):
    for _ in range(60):
        request = urllib.request.Request(base + '/api/v1/transactions/' + txid)
        try:
            with urllib.request.urlopen(request, timeout=10):
                return
        except urllib.error.HTTPError:
            time.sleep(1)


# Tendermint makes an empty block 1 shortly after start; wait for it so tx heights match on both nodes.
for _ in range(60):
    try:
        with urllib.request.urlopen('http://127.0.0.1:%s/status' % rpc, timeout=5) as response:
            if int(json.load(response)['result']['sync_info']['latest_block_height']) >= 1:
                break
    except Exception:  # noqa: B902
        pass
    time.sleep(1)

# State: the same committed transactions, in the same order, on both nodes.
for case in ('create_simple', 'create_multi_output', 'create_threshold', 'create_unicode', 'create_floats_nested',
             'create_max_amount', 'create_null_asset_metadata', 'create_large'):
    post_tx('setup_commit_' + case, case, 'commit')
post_tx('setup_async_transfer_simple', 'transfer_simple', 'async')
wait_committed(txs['transfer_simple']['id'])
post_tx('setup_sync_transfer_threshold', 'transfer_threshold_both', 'sync')
wait_committed(txs['transfer_threshold_both']['id'])
post_tx('setup_default_mode_split', 'transfer_split_max_amount')
wait_committed(txs['transfer_split_max_amount']['id'])

simple, multi = txs['create_simple']['id'], txs['create_multi_output']['id']
alice, bob = corpus['keys']['alice'], corpus['keys']['bob']

# Info
call('root', 'GET', '/')
call('api_v1', 'GET', '/api/v1/')
call('api_v1_no_slash', 'GET', '/api/v1')
call('unknown_path', 'GET', '/api/v1/nope')
call('head_root', 'HEAD', '/')
call('cors_preflight', 'OPTIONS', '/api/v1/transactions',
     headers={'Origin': 'https://example.com', 'Access-Control-Request-Method': 'POST'})
call('cors_get', 'GET', '/api/v1/', headers={'Origin': 'https://example.com'})
call('validators', 'GET', '/api/v1/validators')

# Transactions
call('tx_get_create', 'GET', '/api/v1/transactions/' + simple)
call('tx_get_transfer', 'GET', '/api/v1/transactions/' + txs['transfer_simple']['id'])
call('tx_get_unicode', 'GET', '/api/v1/transactions/' + txs['create_unicode']['id'])
call('tx_get_floats', 'GET', '/api/v1/transactions/' + txs['create_floats_nested']['id'])
call('tx_get_null_asset', 'GET', '/api/v1/transactions/' + txs['create_null_asset_metadata']['id'])
call('tx_get_unknown', 'GET', '/api/v1/transactions/' + 'f' * 64)
call('tx_get_not_hex', 'GET', '/api/v1/transactions/xyz')
call('tx_get_trailing_slash', 'GET', '/api/v1/transactions/' + simple + '/')
call('tx_list', 'GET', '/api/v1/transactions?asset_id=' + simple)
call('tx_list_trailing_slash', 'GET', '/api/v1/transactions/?asset_id=' + simple)
call('tx_list_create', 'GET', '/api/v1/transactions?asset_id=%s&operation=CREATE' % simple)
call('tx_list_transfer_lower', 'GET', '/api/v1/transactions?asset_id=%s&operation=transfer' % simple)
call('tx_list_bad_operation', 'GET', '/api/v1/transactions?asset_id=%s&operation=BURN' % simple)
call('tx_list_last_tx', 'GET', '/api/v1/transactions?asset_id=%s&last_tx=true' % simple)
call('tx_list_last_tx_bad', 'GET', '/api/v1/transactions?asset_id=%s&last_tx=True' % simple)
call('tx_list_last_tx_ignored_case', 'GET', '/api/v1/transactions?asset_id=%s&last_tx=FALSE' % simple)
call('tx_list_missing_asset_id', 'GET', '/api/v1/transactions')
call('tx_list_bad_asset_id', 'GET', '/api/v1/transactions?asset_id=xyz')
call('tx_list_upper_asset_id', 'GET', '/api/v1/transactions?asset_id=' + simple.upper())
call('tx_list_unknown_param', 'GET', '/api/v1/transactions?asset_id=%s&foo=1' % simple)
call('tx_list_repeated_param', 'GET', '/api/v1/transactions?asset_id=%s&asset_id=%s' % (multi, simple))
call('tx_list_json_content_type_no_body', 'GET', '/api/v1/transactions?asset_id=' + simple, headers=JSON)
call('tx_list_asset_id_in_form_body', 'GET', '/api/v1/transactions', ('asset_id=' + simple).encode(),
     {'Content-Type': 'application/x-www-form-urlencoded'})
call('tx_list_asset_id_in_json_body', 'GET', '/api/v1/transactions', json.dumps({'asset_id': simple}).encode(), JSON)
call('tx_list_asset_id_in_text_body', 'GET', '/api/v1/transactions', json.dumps({'asset_id': simple}).encode(),
     {'Content-Type': 'text/plain'})
call('tx_delete', 'DELETE', '/api/v1/transactions/' + simple)
call('tx_put', 'PUT', '/api/v1/transactions', b'{}', JSON)

# POST errors (none of these reach Tendermint)
post_tx('post_duplicate', 'create_simple', 'commit')
post_tx('post_double_spend', 'transfer_double_spend_committed', 'commit')
post_tx('post_invalid_hash', 'invalid_hash')
post_tx('post_missing_id', 'missing_id')
post_tx('post_schema_amount_zero', 'create_amount_zero')
post_tx('post_schema_empty_asset', 'create_empty_asset_metadata')
post_tx('post_schema_extra_field', 'extra_top_level_field')
post_tx('post_bad_key_dollar', 'create_metadata_key_dollar')
post_tx('post_invalid_signature', 'invalid_signature_wrong_key')
post_tx('post_malformed_fulfillment_zeros', 'malformed_fulfillment_zeros_64')
post_tx('post_malformed_fulfillment_null', 'malformed_fulfillment_null')
post_tx('post_wrong_signer', 'transfer_wrong_signer')
post_tx('post_amount_mismatch', 'transfer_amount_mismatch')
post_tx('post_unknown_input', 'transfer_unknown_input_tx')
post_tx('post_bad_mode', 'create_simple', 'bogus')
post_tx('post_nan', 'create_metadata_nan')
post_tx('post_deep_2000', 'create_deep_2000')
post_tx('post_lone_surrogate', 'create_lone_surrogate_unsigned')
post_tx('post_not_json', 'raw_not_json')
post_tx('post_invalid_utf8', 'raw_invalid_utf8')
post_tx('post_json_array', 'raw_json_array')
post_tx('post_empty_body', 'raw_empty')
post_tx('post_no_content_type_duplicate', 'create_simple', headers={})
post_tx('post_text_plain_duplicate', 'create_simple', headers={'Content-Type': 'text/plain'})
mode_in_body = dict(txs['create_twice_same_block_1'], mode='bogus')
post_tx('post_mode_in_json_body', None, body=json.dumps(mode_in_body).encode())
post_tx('post_mode_in_json_body_with_query', None, 'commit', body=json.dumps(mode_in_body).encode())

# Outputs
call('outputs', 'GET', '/api/v1/outputs?public_key=' + alice)
call('outputs_no_slash', 'GET', '/api/v1/outputs?public_key=' + bob)
call('outputs_spent_true', 'GET', '/api/v1/outputs/?public_key=%s&spent=true' % alice)
call('outputs_spent_false', 'GET', '/api/v1/outputs/?public_key=%s&spent=false' % alice)
call('outputs_spent_bad', 'GET', '/api/v1/outputs/?public_key=%s&spent=yes' % alice)
call('outputs_bad_key', 'GET', '/api/v1/outputs/?public_key=0OIl')
call('outputs_missing_key', 'GET', '/api/v1/outputs/')
call('outputs_unknown_param', 'GET', '/api/v1/outputs/?public_key=%s&x=1' % alice)
call('outputs_key_in_json_body', 'GET', '/api/v1/outputs/', json.dumps({'public_key': alice}).encode(), JSON)

# Assets and metadata search
for kind in ('assets', 'metadata'):
    call(kind + '_search', 'GET', '/api/v1/%s/?search=simple' % kind)
    call(kind + '_search_limit', 'GET', '/api/v1/%s/?search=kind&limit=2' % kind)
    call(kind + '_search_limit_zero', 'GET', '/api/v1/%s/?search=kind&limit=0' % kind)
    call(kind + '_search_limit_bad', 'GET', '/api/v1/%s/?search=kind&limit=abc' % kind)
    call(kind + '_search_unicode', 'GET', '/api/v1/%s/?search=%%C3%%BCn%%C3%%AFc%%C3%%B6d%%C3%%A9' % kind)
    call(kind + '_search_phrase', 'GET', '/api/v1/%s/?search=%%22multi-output%%22' % kind)
    call(kind + '_search_negation', 'GET', '/api/v1/%s/?search=kind%%20-simple' % kind)
    call(kind + '_search_all_words', 'GET', '/api/v1/%s/?search=kind%%20max%%20amount%%20value' % kind)
    call(kind + '_search_empty', 'GET', '/api/v1/%s/?search=' % kind)
    call(kind + '_search_missing', 'GET', '/api/v1/%s/' % kind)
    call(kind + '_search_in_json_body', 'GET', '/api/v1/%s/' % kind, json.dumps({'search': 'simple'}).encode(), JSON)

# Blocks
call('block_1', 'GET', '/api/v1/blocks/1')
call('block_unknown', 'GET', '/api/v1/blocks/999999')
call('block_not_int', 'GET', '/api/v1/blocks/abc')
call('block_negative', 'GET', '/api/v1/blocks/-1')
call('blocks_by_tx', 'GET', '/api/v1/blocks?transaction_id=' + simple)
call('blocks_by_tx_slash', 'GET', '/api/v1/blocks/?transaction_id=' + simple)
call('blocks_by_unknown_tx', 'GET', '/api/v1/blocks?transaction_id=' + 'f' * 64)
call('blocks_missing_param', 'GET', '/api/v1/blocks')
call('blocks_unknown_param', 'GET', '/api/v1/blocks?transaction_id=%s&status=valid' % simple)
call('blocks_param_in_json_body', 'GET', '/api/v1/blocks', json.dumps({'transaction_id': simple}).encode(), JSON)
call('blocks_param_in_form_body', 'GET', '/api/v1/blocks', ('transaction_id=' + simple).encode(),
     {'Content-Type': 'application/x-www-form-urlencoded'})

# Changes state on a node that accepts it, so it runs after every read.
post_tx('post_subnormal_float_commit', 'create_subnormal_metadata', 'commit')

if '--crash' in sys.argv:
    post_tx('crash_post_int_beyond_int64', 'create_int_beyond_int64', 'commit')
    time.sleep(5)
    post_tx('crash_after_valid_post', 'create_two_signers', 'commit')
    call('crash_after_get', 'GET', '/api/v1/transactions/' + simple)
    status = urllib.request.Request('http://127.0.0.1:%s/status' % rpc)
    try:
        urllib.request.urlopen(status, timeout=10)
        results['crash_after_tendermint_rpc'] = 'reachable'
    except Exception as error:  # noqa: B902
        results['crash_after_tendermint_rpc'] = repr(error)

with open(out_path, 'w') as out:
    json.dump(results, out, indent=1, sort_keys=True, ensure_ascii=False)
    out.write('\n')
print(len(results), 'requests')

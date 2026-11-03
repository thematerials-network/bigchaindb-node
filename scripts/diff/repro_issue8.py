"""Issue #8 end to end against a running node (scripts/diff/node.sh): valid tx, malformed fulfillment straight into
the mempool via Tendermint RPC broadcast_tx_sync, then a valid tx again.

Usage: python3 repro_issue8.py <corpus.json> <api port> <rpc port> [case name, default malformed_fulfillment_zeros_64]
Uses only the standard library (runs on the host).
"""
import base64
import json
import sys
import urllib.error
import urllib.request

corpus = json.load(open(sys.argv[1]))
raws = {case['name']: base64.b64decode(case['raw_b64']) for case in corpus['cases']}
api, rpc = sys.argv[2], sys.argv[3]
case = sys.argv[4] if len(sys.argv) > 4 else 'malformed_fulfillment_zeros_64'


def request(url, data=None, timeout=30):
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode()[:300]
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()[:300]
    except Exception as error:  # noqa: B902
        return 'no response', repr(error)


def post(name, mode='commit'):
    return request('http://127.0.0.1:%s/api/v1/transactions?mode=%s' % (api, mode), raws[name])


def broadcast(name):
    tx = base64.b64encode(raws[name]).decode()
    body = json.dumps({'jsonrpc': '2.0', 'id': 'issue8', 'method': 'broadcast_tx_sync', 'params': {'tx': tx}})
    return request('http://127.0.0.1:%s/' % rpc, body.encode(), timeout=20)


print('1 valid tx via HTTP (commit):       ', post('create_simple'))
print('2 %s via HTTP:' % case, post(case))
print('3 %s via broadcast_tx_sync:' % case, broadcast(case))
print('4 valid tx via HTTP (commit):       ', post('create_unicode'))
print('5 Tendermint RPC /status reachable: ', request('http://127.0.0.1:%s/status' % rpc)[0])

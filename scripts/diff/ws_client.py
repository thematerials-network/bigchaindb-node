"""Step 6 client: subscribes to the valid_transactions stream, commits transactions over HTTP, records the events.

Usage (inside a container on the node's network, aiohttp available):
  python ws_client.py <corpus.json> <out.json>    talks to bigchaindb:9984 / bigchaindb:9985
"""
import asyncio
import base64
import json
import sys

import aiohttp

CASES = ['create_simple', 'create_multi_output', 'create_unicode', 'transfer_simple', 'transfer_multi_output_spend',
         'create_large', 'transfer_child_same_block', 'create_duplicate_key_last_valid', 'invalid_signature_wrong_key',
         'create_threshold', 'transfer_threshold_both']


async def main():
    corpus = json.load(open(sys.argv[1]))
    raws = {case['name']: base64.b64decode(case['raw_b64']) for case in corpus['cases']}
    result = {'events': [], 'posts': []}
    async with aiohttp.ClientSession() as session:
        try:
            ws = await session.ws_connect('ws://bigchaindb:9985/api/v1/streams/valid_transactions', timeout=10)
        except Exception as error:  # noqa: B902
            result['connect_error'] = '%s: %s' % (type(error).__name__, error)
            json.dump(result, open(sys.argv[2], 'w'), indent=1, sort_keys=True)
            return
        result['handshake_headers'] = {key: value for key, value in ws._response.headers.items()
                                       if key.lower() in ('upgrade', 'connection', 'sec-websocket-protocol',
                                                          'content-type')}

        async def receive():
            async for message in ws:
                result['events'].append({'type': message.type.name, 'data': json.loads(message.data)
                                         if message.type == aiohttp.WSMsgType.TEXT else repr(message.data)})
        reader = asyncio.create_task(receive())
        for name in CASES:
            async with session.post('http://bigchaindb:9984/api/v1/transactions?mode=commit', data=raws[name],
                                    headers={'Content-Type': 'application/json'}) as response:
                result['posts'].append([name, response.status])
        await asyncio.sleep(5)
        await ws.close()
        await asyncio.wait_for(reader, 10)
    json.dump(result, open(sys.argv[2], 'w'), indent=1, sort_keys=True)
    print(len(result['events']), 'events')


asyncio.run(main())

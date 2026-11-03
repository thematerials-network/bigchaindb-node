# Copyright © 2020 Interplanetary Database Association e.V.,
# BigchainDB and IPDB software contributors.
# SPDX-License-Identifier: (Apache-2.0 AND CC-BY-4.0)
# Code is Apache-2.0 and docs are CC-BY-4.0

import asyncio
import json
import queue
import threading
from unittest.mock import patch

import pytest


class MockWebSocket:
    def __init__(self):
        self.received = []

    def send_str(self, s):
        self.received.append(s)


def test_eventify_block_works_with_any_transaction():
    from bigchaindb.web.websocket_server import eventify_block
    from bigchaindb.common.crypto import generate_key_pair
    from bigchaindb.lib import Transaction

    alice = generate_key_pair()

    tx = Transaction.create([alice.public_key],
                            [([alice.public_key], 1)])\
                    .sign([alice.private_key])
    tx_transfer = Transaction.transfer(tx.to_inputs(),
                                       [([alice.public_key], 1)],
                                       asset_id=tx.id)\
                             .sign([alice.private_key])

    block = {'height': 1,
             'transactions': [tx, tx_transfer]}

    expected_events = [{
            'height': 1,
            'asset_id': tx.id,
            'transaction_id': tx.id
        }, {
            'height': 1,
            'asset_id': tx_transfer.asset['id'],
            'transaction_id': tx_transfer.id
        }]

    for event, expected in zip(eventify_block(block), expected_events):
        assert event == expected


@pytest.mark.asyncio
async def test_bridge_sync_async_queue():
    from bigchaindb.web.websocket_server import _multiprocessing_to_asyncio

    loop = asyncio.get_running_loop()
    sync_queue = queue.Queue()
    async_queue = asyncio.Queue()

    bridge = threading.Thread(target=_multiprocessing_to_asyncio,
                              args=(sync_queue, async_queue, loop),
                              daemon=True)
    bridge.start()

    sync_queue.put('fahren')
    sync_queue.put('auf')
    sync_queue.put('der')
    sync_queue.put('Autobahn')

    result = await async_queue.get()
    assert result == 'fahren'

    result = await async_queue.get()
    assert result == 'auf'

    result = await async_queue.get()
    assert result == 'der'

    result = await async_queue.get()
    assert result == 'Autobahn'

    assert async_queue.qsize() == 0


@patch('threading.Thread')
@patch('aiohttp.web.run_app')
@patch('bigchaindb.web.websocket_server.init_app')
@patch('asyncio.get_event_loop', return_value='event-loop')
@patch('asyncio.Queue', return_value='event-queue')
def test_start_creates_an_event_loop(queue_mock, get_event_loop_mock,
                                     init_app_mock, run_app_mock,
                                     thread_mock):
    from bigchaindb import config
    from bigchaindb.web.websocket_server import start, _multiprocessing_to_asyncio

    start(None)
    thread_mock.assert_called_once_with(
        target=_multiprocessing_to_asyncio,
        args=(None, queue_mock.return_value, get_event_loop_mock.return_value),
        daemon=True,
    )
    thread_mock.return_value.start.assert_called_once_with()
    init_app_mock.assert_called_with('event-queue', loop='event-loop')
    run_app_mock.assert_called_once_with(
        init_app_mock.return_value,
        host=config['wsserver']['host'],
        port=config['wsserver']['port'],
        loop=get_event_loop_mock.return_value,
    )


def test_start_serves_events_when_run_as_a_process(monkeypatch):
    import multiprocessing
    import socket
    import aiohttp
    from bigchaindb.utils import Process
    from bigchaindb.web import websocket_server

    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    monkeypatch.setitem(websocket_server.config['wsserver'], 'host', '127.0.0.1')
    monkeypatch.setitem(websocket_server.config['wsserver'], 'port', port)

    # Started the way `bigchaindb start` does it (bigchaindb/start.py).
    event_queue = multiprocessing.Queue()
    process = Process(name='bigchaindb_ws', target=websocket_server.start,
                      args=(event_queue,), daemon=True)
    process.start()

    async def receive_event():
        url = f'http://127.0.0.1:{port}{websocket_server.EVENTS_ENDPOINT}'
        async with aiohttp.ClientSession() as session:
            for _ in range(100):
                assert process.is_alive(), f'websocket server exited with code {process.exitcode}'
                try:
                    websocket = await session.ws_connect(url)
                    break
                except aiohttp.ClientConnectorError:
                    await asyncio.sleep(0.1)
            else:
                pytest.fail('websocket server did not accept connections')
            event_queue.put('hello')
            message = await websocket.receive(timeout=10)
            await websocket.close()
            return message.data

    try:
        assert asyncio.run(receive_event()) == 'hello'
    finally:
        process.terminate()
        process.join()


@pytest.mark.asyncio
async def test_websocket_string_event(aiohttp_client):
    from bigchaindb.web.websocket_server import init_app, POISON_PILL, EVENTS_ENDPOINT

    loop = asyncio.get_running_loop()
    event_source = asyncio.Queue()
    app = init_app(event_source, loop=loop)
    client = await aiohttp_client(app)
    ws = await client.ws_connect(EVENTS_ENDPOINT)

    await event_source.put('hack')
    await event_source.put('the')
    await event_source.put('planet!')

    result = await ws.receive()
    assert result.data == 'hack'

    result = await ws.receive()
    assert result.data == 'the'

    result = await ws.receive()
    assert result.data == 'planet!'

    await event_source.put(POISON_PILL)


@pytest.mark.asyncio
async def test_websocket_block_event(b, aiohttp_client):
    from bigchaindb import events
    from bigchaindb.web.websocket_server import init_app, POISON_PILL, EVENTS_ENDPOINT
    from bigchaindb.models import Transaction
    from bigchaindb.common import crypto

    user_priv, user_pub = crypto.generate_key_pair()
    tx = Transaction.create([user_pub], [([user_pub], 1)])
    tx = tx.sign([user_priv])

    loop = asyncio.get_running_loop()
    event_source = asyncio.Queue()
    app = init_app(event_source, loop=loop)
    client = await aiohttp_client(app)
    ws = await client.ws_connect(EVENTS_ENDPOINT)
    block = {'height': 1, 'transactions': [tx]}
    block_event = events.Event(events.EventTypes.BLOCK_VALID, block)

    await event_source.put(block_event)

    for tx in block['transactions']:
        result = await ws.receive()
        json_result = json.loads(result.data)
        assert json_result['transaction_id'] == tx.id
        # Since the transactions are all CREATEs, asset id == transaction id
        assert json_result['asset_id'] == tx.id
        assert json_result['height'] == block['height']

    await event_source.put(POISON_PILL)


@pytest.mark.skip('Processes are not stopping properly, and the whole test suite would hang')
def test_integration_from_webapi_to_websocket(monkeypatch, client, loop):
    # XXX: I think that the `pytest-aiohttp` plugin is sparkling too much
    # magic in the `asyncio` module: running this test without monkey-patching
    # `asycio.get_event_loop` (and without the `loop` fixture) raises a:
    #     RuntimeError: There is no current event loop in thread 'MainThread'.
    #
    # That's pretty weird because this test doesn't use the pytest-aiohttp
    # plugin explicitely.
    monkeypatch.setattr('asyncio.get_event_loop', lambda: loop)

    import json
    import random
    import aiohttp

    from bigchaindb.common import crypto
    # TODO processes does not exist anymore, when reactivating this test it
    # will fail because of this
    from bigchaindb import processes
    from bigchaindb.models import Transaction

    # Start BigchainDB
    processes.start()

    loop = asyncio.get_event_loop()

    import time
    time.sleep(1)

    ws_url = client.get('http://localhost:9984/api/v1/').json['_links']['streams_v1']

    # Connect to the WebSocket endpoint
    session = aiohttp.ClientSession()
    ws = loop.run_until_complete(session.ws_connect(ws_url))

    # Create a keypair and generate a new asset
    user_priv, user_pub = crypto.generate_key_pair()
    asset = {'random': random.random()}
    tx = Transaction.create([user_pub], [([user_pub], 1)], asset=asset)
    tx = tx.sign([user_priv])
    # Post the transaction to the BigchainDB Web API
    client.post('/api/v1/transactions/', data=json.dumps(tx.to_dict()))

    result = loop.run_until_complete(ws.receive())
    json_result = json.loads(result.data)
    assert json_result['transaction_id'] == tx.id

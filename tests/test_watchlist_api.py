"""ASGI route checks without a running server, external services or trading."""
import json
import unittest
from unittest.mock import Mock, patch

import server


async def request(path, method='GET', payload=None, query=b''):
    messages = []
    body = json.dumps(payload).encode() if payload is not None else b''
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {'type': 'http.disconnect'}
        delivered = True
        return {'type': 'http.request', 'body': body, 'more_body': False}

    async def send(message):
        messages.append(message)

    await server.app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                      'scheme': 'http', 'server': ('test', 80), 'client': ('127.0.0.1', 1),
                      'root_path': '', 'path': path, 'raw_path': path.encode(),
                      'query_string': query, 'method': method,
                      'headers': [(b'content-type', b'application/json')]}, receive, send)
    status = next(m['status'] for m in messages if m['type'] == 'http.response.start')
    response = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
    return status, response


class WatchlistAPITests(unittest.IsolatedAsyncioTestCase):
    async def test_watchlist_route_and_query_validation(self):
        with patch('server.build_watchlists', return_value={'test': True}) as build:
            status, body = await request('/api/watchlists', query=b'min_delivery=60&volume_multiplier=2&live=true')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), {'test': True})
            build.assert_called_once_with(min_delivery=60, volume_multiplier=2, fetch_quotes=True)
        self.assertEqual((await request('/api/watchlists', query=b'volume_multiplier=0'))[0], 422)

    async def test_new_ui_assets_served(self):
        status, body = await request('/')
        self.assertEqual(status, 200)
        self.assertIn(b'id="tab-watchlists"', body)
        self.assertEqual((await request('/static/js/watchlists.js'))[0], 200)

    async def test_order_does_not_substitute_a_historical_price(self):
        manager = Mock(active_broker_name='openalgo')
        manager.get_active_broker.return_value.place_order.return_value = {'status': 'success', 'orderid': 'test'}
        with patch.object(server.engine, 'broker_mgr', manager):
            status, _ = await request('/api/order', 'POST', {'symbol': 'ABC', 'quantity': 1, 'price': 0})
            self.assertEqual(status, 200)
            self.assertEqual(manager.get_active_broker.return_value.place_order.call_args.args[4], 0)

    async def test_unsupported_protection_and_test_webhook_blocked(self):
        manager = Mock(active_broker_name='openalgo')
        with patch.object(server.engine, 'broker_mgr', manager):
            status, _ = await request('/api/order', 'POST', {'symbol': 'ABC', 'quantity': 1, 'stop_loss': 90})
            self.assertEqual(status, 400)
            status, _ = await request('/api/broker/webhook', 'POST', {'symbol': 'ABC', 'action': 'BUY'})
            self.assertEqual(status, 403)
            manager.get_active_broker.return_value.place_order.assert_not_called()


if __name__ == '__main__':
    unittest.main()

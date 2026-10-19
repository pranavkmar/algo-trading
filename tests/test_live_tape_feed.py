#!/usr/bin/env python3
"""
tests/test_live_tape_feed.py - Automated Test Suite for Live Time & Sales WebSocket Feed
"""

import unittest
import json
import websockets
from server import engine, is_nse_market_open

class TestLiveTapeWebSocketFeed(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        engine.load_cache()

    def test_engine_live_quote_and_candle(self):
        """Test FastMarketEngine live quote and forming candle methods."""
        quote = engine.get_live_market_quote("KOTAKBANK")
        self.assertIsInstance(quote, dict)
        self.assertEqual(quote["symbol"], "KOTAKBANK")
        self.assertGreater(quote["price"], 0.0)

        candle = engine.get_live_forming_candle("KOTAKBANK")
        self.assertIsInstance(candle, dict)
        self.assertEqual(candle["symbol"], "KOTAKBANK")
        self.assertGreater(candle["close"], 0.0)

        ticks = engine.get_live_or_eod_ticks("KOTAKBANK", limit=10)
        self.assertIsInstance(ticks, list)
        if len(ticks) > 0:
            self.assertEqual(ticks[0]["symbol"], "KOTAKBANK")
            self.assertIn(ticks[0]["side"], ["BUY", "SELL"])

    async def test_live_tape_ws_stream(self):
        """Test live websocket handshake, subscribe, and tick streaming."""
        uri = "ws://127.0.0.1:8000/ws/live"
        async with websockets.connect(uri) as ws:
            # 1. Connection established
            handshake = json.loads(await ws.recv())
            self.assertEqual(handshake["type"], "CONNECTION_ESTABLISHED")
            self.assertIn("market_open", handshake)
            self.assertIn("feed_mode", handshake)
            self.assertIn("last_eod_candle", handshake)
            self.assertIn("recent_eod_ticks", handshake)

            # 2. Subscribe to MOTHERSON
            await ws.send(json.dumps({"action": "SUBSCRIBE", "symbol": "MOTHERSON"}))
            snap = json.loads(await ws.recv())
            self.assertEqual(snap["type"], "SYMBOL_SNAPSHOT")
            self.assertEqual(snap["symbol"], "MOTHERSON")
            self.assertIn("market_open", snap)
            self.assertIn("feed_mode", snap)
            self.assertIn("last_eod_candle", snap)
            self.assertIn("recent_eod_ticks", snap)

            # 3. Toggle simulator
            await ws.send(json.dumps({"action": "TOGGLE_SIMULATOR", "enabled": True}))
            sim_state = json.loads(await ws.recv())
            self.assertEqual(sim_state["type"], "SIMULATOR_STATE")
            self.assertTrue(sim_state["enabled"])

            # 4. Receive streaming tick
            tick_msg = json.loads(await ws.recv())
            self.assertEqual(tick_msg["type"], "TICK")
            self.assertIn("tick", tick_msg)
            self.assertEqual(tick_msg["tick"]["symbol"], "MOTHERSON")
            self.assertGreater(tick_msg["tick"]["price"], 0.0)

if __name__ == "__main__":
    unittest.main()

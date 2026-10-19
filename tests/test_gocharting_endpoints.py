#!/usr/bin/env python3
"""
tests/test_gocharting_endpoints.py - Automated Test Suite for GoCharting SDK & UDF Integration
"""

import unittest
import time
from fastapi import HTTPException

import server
from server import (
    gocharting_config,
    gocharting_time,
    gocharting_symbols,
    gocharting_history,
    gocharting_search,
    gocharting_save_chart,
    gocharting_get_chart,
    gocharting_list_charts,
    gocharting_delete_chart,
    place_order,
    SaveChartRequest,
    OrderRequest,
    engine
)

class TestGoChartingEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure cache and DB are initialized
        engine.load_cache()

    def test_gocharting_config(self):
        """Test UDF handshake configuration endpoint."""
        config = gocharting_config()
        self.assertIsInstance(config, dict)
        self.assertTrue(config.get("supports_search"))
        self.assertTrue(config.get("supports_time"))
        self.assertIn("1", config.get("supported_resolutions", []))
        self.assertIn("D", config.get("supported_resolutions", []))

    def test_gocharting_time(self):
        """Test UDF server time synchronization."""
        t = gocharting_time()
        self.assertIsInstance(t, int)
        self.assertGreater(t, 1700000000)
        self.assertLessEqual(t, int(time.time()) + 5)

    def test_gocharting_symbols(self):
        """Test GoCharting SymbolInfo resolution with footprint eligibility."""
        sym_info = gocharting_symbols("KOTAKBANK")
        self.assertEqual(sym_info["name"], "KOTAKBANK")
        self.assertEqual(sym_info["ticker"], "NSE:KOTAKBANK")
        self.assertEqual(sym_info["exchange"], "NSE")
        self.assertEqual(sym_info["session"], "0915-1530")
        self.assertEqual(sym_info["timezone"], "Asia/Kolkata")
        self.assertEqual(sym_info["currency_code"], "INR")
        self.assertTrue(sym_info["supports"]["footprint"])
        self.assertTrue(sym_info["supports"]["volume_profile"])

    def test_gocharting_symbols_prefix(self):
        """Test symbol resolution with NSE: prefix."""
        sym_info = gocharting_symbols("NSE:KOTAKBANK")
        self.assertEqual(sym_info["name"], "KOTAKBANK")
        self.assertEqual(sym_info["ticker"], "NSE:KOTAKBANK")

    def test_gocharting_symbols_not_found(self):
        """Test that invalid symbol raises 404."""
        with self.assertRaises(HTTPException) as ctx:
            gocharting_symbols("NONEXISTENT_TICKER_XYZ")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_gocharting_history_intraday(self):
        """Test historical 1-minute orderflow bar retrieval from amibroker.db."""
        hist = gocharting_history("KOTAKBANK", resolution="1")
        self.assertEqual(hist.get("s"), "ok")
        self.assertIn("t", hist)
        self.assertIn("o", hist)
        self.assertIn("h", hist)
        self.assertIn("l", hist)
        self.assertIn("c", hist)
        self.assertIn("v", hist)
        self.assertIn("buy_volume", hist)
        self.assertIn("sell_volume", hist)
        self.assertIn("delta", hist)
        self.assertGreater(len(hist["t"]), 0)
        self.assertEqual(len(hist["t"]), len(hist["c"]))
        self.assertEqual(len(hist["t"]), len(hist["buy_volume"]))

    def test_gocharting_history_daily(self):
        """Test historical daily bar retrieval."""
        hist = gocharting_history("KOTAKBANK", resolution="D")
        self.assertEqual(hist.get("s"), "ok")
        self.assertGreater(len(hist["t"]), 0)
        self.assertEqual(len(hist["t"]), len(hist["c"]))

    def test_gocharting_search(self):
        """Test symbol search autocomplete."""
        results = gocharting_search("KOTAK", limit=10)
        self.assertIsInstance(results, list)
        self.assertGreaterEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item["symbol"], "KOTAKBANK")
        self.assertEqual(item["ticker"], "NSE:KOTAKBANK")
        self.assertEqual(item["exchange"], "NSE")

    def test_gocharting_chart_persistence(self):
        """Test complete CRUD cycle for chart layouts and drawings."""
        req = SaveChartRequest(
            name="Unit Test Layout",
            symbol="KOTAKBANK",
            resolution="1",
            layout={
                "panes": [
                    {"indicators": ["Footprint", "Volume Profile", "CVD"]},
                    {"drawings": [{"type": "horizontal_line", "price": 415.50}]}
                ]
            }
        )
        # 1. Create
        save_res = gocharting_save_chart(req)
        self.assertEqual(save_res["status"], "SUCCESS")
        cid = save_res["id"]

        # 2. Read
        chart = gocharting_get_chart(cid)
        self.assertEqual(chart["name"], "Unit Test Layout")
        self.assertEqual(chart["symbol"], "KOTAKBANK")
        self.assertEqual(chart["resolution"], "1")
        self.assertEqual(len(chart["layout"]["panes"]), 2)

        # 3. List
        chart_list = gocharting_list_charts(symbol="KOTAKBANK")
        self.assertTrue(any(c["id"] == cid for c in chart_list))

        # 4. Delete
        del_res = gocharting_delete_chart(cid)
        self.assertEqual(del_res["status"], "SUCCESS")

        # 5. Verify deletion
        with self.assertRaises(HTTPException) as ctx:
            gocharting_get_chart(cid)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_trade_from_chart_order_execution(self):
        """Test trade execution triggered by GoCharting Trade-from-Chart appCallback."""
        order = OrderRequest(
            symbol="KOTAKBANK",
            quantity=25,
            transaction_type="BUY",
            order_type="MARKET",
            price=415.00,
            tag="GOCHARTING_SDK_TRADE"
        )
        res = place_order(order)
        self.assertEqual(res.get("status"), "SUCCESS")
        self.assertTrue(res.get("order_id", "").startswith("PAPER_"))
        self.assertEqual(res.get("filled_qty"), 25)
        self.assertEqual(res.get("filled_price"), 415.00)


if __name__ == "__main__":
    unittest.main()

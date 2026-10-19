"""Small OpenAlgo REST gateway. Credentials stay on the server."""
import math
import os
import re
from urllib.parse import urlparse

import requests


class OpenAlgoError(RuntimeError):
    pass


class OpenAlgoClient:
    def __init__(self, host=None, api_key=None, session=None):
        self.host = (host or os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")).rstrip("/")
        parsed = urlparse(self.host)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.query:
            raise ValueError("OPENALGO_HOST must be an HTTP(S) base URL")
        self.api_key = api_key if api_key is not None else os.getenv("OPENALGO_API_KEY", "")
        self.session = session or requests.Session()

    def call(self, endpoint, **payload):
        if not self.api_key:
            raise OpenAlgoError("Set OPENALGO_API_KEY on the server")
        try:
            response = self.session.post(
                f"{self.host}/api/v1/{endpoint}",
                json={**payload, "apikey": self.api_key}, timeout=(3, 15),
                allow_redirects=False,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            # An order may have reached the broker even if its response was lost.
            # Do not retry order submissions automatically or expose request bodies.
            raise OpenAlgoError("OpenAlgo request failed; check OpenAlgo order book before retrying an order") from None
        if not isinstance(data, dict) or data.get("status") != "success":
            raise OpenAlgoError("OpenAlgo rejected the request; inspect its dashboard for details")
        return data

    def quotes(self, symbols):
        results = []
        # Bounded batches; the server's broker adapter may fall back to individual quotes.
        for start in range(0, len(symbols), 50):
            result = self.call("multiquotes", symbols=[
                {"symbol": s, "exchange": "NSE"} for s in symbols[start:start + 50]
            ])
            results.extend(result.get("results", []))
        return results

    def place_order(self, symbol, quantity, action, order_type="MARKET", price=0.0,
                    trigger_price=0.0, strategy="IntradayWatchlist"):
        symbol, action, order_type = symbol.upper().strip(), action.upper(), order_type.upper()
        if not re.fullmatch(r"[A-Z0-9&_-]{1,40}", symbol):
            raise ValueError("Invalid NSE equity symbol")
        if type(quantity) is not int or quantity <= 0:
            raise ValueError("Quantity must be a positive integer")
        if action not in {"BUY", "SELL"} or order_type not in {"MARKET", "LIMIT", "SL", "SL-M"}:
            raise ValueError("Invalid side or order type")
        if not all(math.isfinite(v) and v >= 0 for v in (price, trigger_price)):
            raise ValueError("Prices must be finite and non-negative")
        if order_type in {"LIMIT", "SL"} and price <= 0:
            raise ValueError("Limit orders require a price")
        if order_type in {"SL", "SL-M"} and trigger_price <= 0:
            raise ValueError("Stop orders require a trigger price")
        return self.call("placeorder", strategy=strategy, symbol=symbol, exchange="NSE",
                         action=action, quantity=quantity, product="MIS", pricetype=order_type,
                         price=price if order_type in {"LIMIT", "SL"} else 0,
                         trigger_price=trigger_price)

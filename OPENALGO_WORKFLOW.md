# OpenAlgo intraday workflow

The custom project owns screening and watchlists. The sibling `openalgo/` project owns broker login, quote retrieval and order execution. No changes to OpenAlgo's source are required.

## Watchlists

Open the **Daily & Intraday Watchlists** tab in the existing terminal.

- Daily delivery list: delivery **strictly above 60%** and volume **at least 1.5×** the mean of the preceding **20 completed sessions**, excluding the signal session. Change the multiplier to 2 for the stricter screen. Full lookback history is required.
- Daily news/results list: dated, explicitly attributed headlines with source links from the preceding seven calendar days. News and delivery candidates are combined, without requiring news stocks to pass the delivery filter.
- Intraday lists: candidates whose OpenAlgo last price is strictly above the reference session's high or strictly below its low. Equality stays within range. These are current price conditions, not remembered crossing events or entry signals.
- The reference is the latest locally available completed session strictly before the requested session. Stocks missing that common reference date are excluded. Refresh local data first using `data_sync.py`. The date is displayed so you can verify it against the last exchange session; the weekday/hour guard does not know exchange holidays or special sessions. Data over four calendar days old blocks intraday scans, conservatively including long holiday breaks.
- Quotes refresh on demand or every 30 seconds while the tab is visible and its refresh checkbox is enabled. The REST gateway uses batches of 50 symbols. This is an initial watchlist scanner; a full-universe, high-frequency scanner should use OpenAlgo's WebSocket feed with broker subscription limits.
- Retrieval time is displayed; some brokers do not supply an exchange timestamp in MultiQuotes. A retrieved quote is not a guarantee of exchange freshness. The new scanner never consumes the old terminal's generated tape.

CLI examples (run inside `algo-trading/`):

```sh
.venv/bin/python watchlists.py --session 2026-10-19 --delivery 60 --volume 1.5
.venv/bin/python watchlists.py --live --volume 2
```

Read-only API: `GET /api/watchlists?min_delivery=60&volume_multiplier=1.5&live=true`. CLI output is JSON and can be saved as a dated snapshot; the UI reads current inputs each refresh.

## News inputs

No news subscription or automatic company attribution has been assumed. Until configured, the UI explicitly reports that news is unavailable. Create `data/news_watchlist.json` as a JSON array, for example:

```json
[
  {
    "symbol": "RELIANCE",
    "headline": "Replace with a verified announcement headline",
    "category": "results",
    "published_at": "2026-10-19T08:30:00+05:30",
    "url": "https://example.com/replace-with-actual-announcement"
  }
]
```

Use `news` or `results` for category. Dates must include a timezone; undated items are skipped. Only symbols in local history are included. The example is a format illustration, not actual company news.

To refresh automatically from **company-specific** RSS/Atom feeds, create `data/news_feeds.json`, an array of `{"symbol":"RELIANCE","url":"https://YOUR-PROVIDER/COMPANY-FEED","category":"news"}`, then run:

```sh
.venv/bin/python news_import.py data/news_feeds.json
```

Every item in each feed is attributed to its configured symbol. Do not map a broad market feed to one symbol. The importer preserves published dates and source links, deduplicates by symbol/link, and retains prior data if a feed fails. It never manufactures a headline or assigns today's date to an undated item. This command can be added to your existing EOD/pre-market routine after choosing a source; no scheduler was installed or changed.

## OpenAlgo connection and intraday orders

Start and authenticate the broker in the sibling OpenAlgo installation using its existing setup. Use the same host reachability from the custom project's process (Windows and WSL loopback may differ).

```sh
export OPENALGO_HOST=http://127.0.0.1:5000
export OPENALGO_API_KEY='your-openalgo-api-key'
export ALGO_BROKER=openalgo
# Leave this unset while validating read-only lists.
# Enable submissions only when ready; OpenAlgo Analyzer Mode is useful for testing.
export OPENALGO_ORDERS_ENABLED=true
.venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Keep credentials in server environment variables, not browser code or committed files. Alternatively select `"active_broker":"openalgo"` in the existing ignored `data/broker_config.json`. With no selection, the existing paper broker remains active. No real orders were submitted during development.

The existing manual order endpoint now routes to `POST /api/v1/placeorder` with `exchange=NSE`, `product=MIS`, and the requested side/quantity/type. MARKET orders send price zero; LIMIT requires a positive price; SL and SL-M require a trigger. API clients can provide `trigger_price`. The existing quick order buttons do not expose limit or trigger inputs, so use MARKET there or enter other order types directly in OpenAlgo.

OpenAlgo acceptance or a queued semi-auto order is not a confirmed fill. Inspect fills, positions, funds and exits in OpenAlgo; the custom portfolio panel points there instead of displaying simulated balances. Submissions are never retried automatically after network failure because the order may already exist. Check the order book before retrying.

`MIS` selects the intraday product; it is not an application square-off service. Automatic end-of-day exits, protective stops/targets, risk sizing, maximum daily loss, exchange holiday awareness, reconciliation and unattended trade automation are **not implemented** by this integration. Manage exits in OpenAlgo/broker. Attached stop/target fields are rejected rather than silently treated as protection. The legacy webhook tester cannot place OpenAlgo orders; the generated-tick CLI can auto-trade only against the paper broker. Keep the existing unauthenticated custom terminal bound to loopback.

## Verification

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_watchlist*.py' -v
```

Tests use isolated histories and mocked OpenAlgo responses; they never contact a broker or place an order. OpenAlgo itself remains unchanged. End-to-end broker connectivity still requires your running, authenticated OpenAlgo instance and API key.

The gateway follows the local OpenAlgo schemas and its official [PlaceOrder documentation](https://docs.openalgo.in/developers/design-documentation/19-placeorder-call-flow).

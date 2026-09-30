# AGENTS.md: Institutional Trading & Screening Engine Agent Guide

This document defines the operational procedures, architecture, command interfaces, and multi-persona committee protocols for autonomous agents working within this repository.

---

## 1. Daily Core Workflow Commands

Agents and operators should execute the following 5-step routine for daily EOD screening, stock evaluation, and 1-minute database loading:

```bash
# 1. Run the daily smart delta sync (or let the cron job do it automatically at 20:00 IST)
./.venv/bin/python data_sync.py

# 2. Screen for institutional accumulation (Delivery >= 70% AND Volume >= 2x)
./.venv/bin/python delivery_filter.py --mode both -d 70.0 -v 2.0 --top 20

# 3. Convene the committee on any stock (e.g. MOTHERSON, KOTAKBANK, WIPRO)
./.venv/bin/python analyst_committee.py --symbol KOTAKBANK

# 4. Convene the committee on today's top screened stocks
./.venv/bin/python analyst_committee.py --top-screened --top 3

# 5. Sync & query 1-minute orderflow bars in amibroker.db
./.venv/bin/python intraday_sync.py
./.venv/bin/python intraday_sync.py --query KOTAKBANK --days 10
```

---

## 2. System Architecture & Components

```
algo-trading/
├── .agents/                      # Agent customizations, skills, and MCP configuration
│   ├── mcp_config.json           # Local screener-mcp registration
│   ├── rules/                    # Behavioral instructions (trading_committee.md)
│   └── skills/trading-committee/ # Committee execution skill definition
├── data/
│   ├── fno_symbols.json          # 213 active NSE F&O underlying symbols
│   ├── historical/               # Local CSV candles per symbol (2026-01-01 to present)
│   ├── fundamentals/             # Cached Screener.in JSON files (24h TTL)
│   ├── amibroker.db              # SQLite database storing 1-minute intraday OHLCV + Order Flow bars
│   ├── amibroker_export/         # Standard AmiBroker ASCII CSV exports (with BuyVol/SellVol/Delta)
│   └── institutional_signals.csv # Latest screened institutional setups
├── logs/
│   └── cron_bhavcopy.log         # Automated cron EOD ingestion logs
├── scripts/
│   └── cron_bhavcopy_sync.sh     # Daily cron execution script (Bhavcopy + Screen + 1m DB)
├── analyst_committee.py          # Multi-persona committee decision engine
├── broker_client.py              # Multi-broker adapter gateway (Dhan, Fyers, Paper, Webhooks)
├── data_sync.py                  # Incremental delta & historical ingestion engine
├── delivery_filter.py            # High-speed disk-based screening engine
├── intraday_sync.py              # 1-minute order flow ingestion & AmiBroker DB engine
├── screener_client.py            # Screener.in extraction client with JSON caching
└── AGENTS.md                     # This file
```

---

## 3. Data Ingestion & Delta Sync Rules

1. **Incremental Updates Only**:
   - Never re-download 9 months of historical data for daily updates.
   - The EOD Deliverable Bhavcopy (`sec_bhavdata_full_ddmmyyyy.csv`, ~400 KB) contains all NSE stocks in a single payload.
   - `data_sync.py` downloads this single file and appends delta rows to all 213 local CSVs in $<1$s.
   - Idempotent: checks each symbol's latest date to prevent duplicate rows.

2. **1-Minute Intraday & Order Flow Bars (`amibroker.db`)**:
   - Stores 1-minute candles (`symbol`, `datetime`, `open`, `high`, `low`, `close`, `volume`, `buy_volume`, `sell_volume`, `delta`) in SQLite format.
   - Computes intra-candle aggressor volume:
     - `buy_volume`: Aggressive market buy orders lifting the Ask.
     - `sell_volume`: Aggressive market sell orders hitting the Bid.
     - `delta`: `buy_volume - sell_volume`.
   - Upserted idempotently (`INSERT OR REPLACE`) so nightly runs accumulate continuous history across 10+ days without gaps or duplicates.
   - Supports export to AmiBroker standard ASCII format via `--export-amibroker <SYMBOL>`.

3. **Bhavcopy Timing**:
   - Market closes: 15:30 IST (10:00 UTC).
   - Deliverable Bhavcopy published: 18:00 – 19:30 IST (occasionally up to 20:00 IST on high-volume/expiry Thursdays).
   - Optimal sync window: **20:00 IST (14:30 UTC)**.

4. **Cron Automation**:
   - Automated via `crontab -l`: runs `scripts/cron_bhavcopy_sync.sh` at 14:30 UTC (20:00 IST) and 15:00 UTC (20:30 IST) Monday through Friday.
   - The cron script executes: (1) `data_sync.py`, (2) `delivery_filter.py`, (3) `intraday_sync.py`.

---

## 4. Multi-Persona Trading & Investment Committee

When evaluating stocks or responding to user queries about trade feasibility, convene the 5 committee personas:

### 1. Momentum & Breakout Trader
- **Metrics**: 20D/50D SMA trend alignment, breakout structure, volume multiplier vs 20-day baseline.
- **Output**: Tactical entry zone, ATR stop-loss (1.5x ATR), Target 1 & Target 2 (minimum 1:1.5 Risk-to-Reward).

### 2. Institutional Delivery Tracker (Smart Money)
- **Metrics**: Cash delivery volume, delivery percentage (>70% institutional accumulation threshold), historical delivery percentile, and QoQ FII/DII shareholding changes.
- **Output**: Assessment of genuine institutional accumulation vs intraday retail churning.

### 3. Fundamental Value Investor
- **Powered by**: Screener.in / `screener-mcp`.
- **Metrics**: Market Cap, P/E vs Industry, Price-to-Book, ROCE (>15%), ROE (>15%), 5-Year Profit CAGR, debt profile, and Screener pros/cons.
- **Output**: Margin of safety, structural business durability, and 1–3 year holding horizon.

### 4. Quantitative Risk & Research Analyst
- **Metrics**: Volume Z-Score ($\sigma$), Average True Range (ATR %), Screener red-flag penalties, and fractional portfolio risk sizing (1% risk model).
- **Output**: Volatility regime categorization and max allowable share allocation.

### 5. Chief Investment Officer (CIO) Consensus
- **Score Scale**: Weighted composite score from **-10.0 to +10.0**.
- **Action Verdicts**:
  - `STRONG BUY / HIGH CONVICTION`: Composite Score $\ge +4.0$
  - `ACCUMULATE ON PULLBACKS`: Composite Score $+1.5$ to $+4.0$
  - `NEUTRAL / WATCHLIST`: Composite Score $-1.5$ to $+1.5$
  - `AVOID / TAKE PROFIT`: Composite Score $< -1.5$

---

## 5. Screener MCP Server (`screener-mcp`) Integration

Registered in `.agents/mcp_config.json` and `~/.gemini/config/mcp_config.json`:
- **Server Name**: `screener`
- **Command**: `uvx screener-mcp`

### Key Tools Available:
- `get_company_overview(symbol)`: Valuation multiples, ROCE, ROE, 52W range, pros/cons.
- `get_financials(symbol)`: P&L, Balance Sheet, Cash Flow.
- `get_quarterly_results(symbol)`: Last 8 quarters revenue & net profit.
- `get_shareholding_pattern(symbol)`: Promoter, FII, DII, and Public quarterly trends.
- `analyze_red_flags(symbol)`: Automated audit red flags.
- `compare_companies(symbols)`: Peer comparison and industry benchmarks.

---

## 6. GoCharting Charting Library Standard for Web Applications

When implementing web visualization dashboards:
- **Mandate**: Use the **GoCharting Library / SDK (`@gocharting/chart-sdk`)** or **GoCharting embed widgets** instead of TradingView.
- **Advantages**: Native orderflow support, Indian market (NSE) compatibility, footprint and volume profile capabilities.
- **1-Minute Bar Feed**: Pipe 1-minute intraday bars from `data/amibroker.db` into the chart container or embed with the `NSE:<SYMBOL>` ticker reference.

---

## 7. Multi-Broker Integration & Order Flow Standard

When connecting broker APIs for execution or live market depth:
1. **Dhan (DhanHQ)**: Preferred broker partner for GoCharting. Connects directly to GoCharting terminals and provides 200-level market depth feeds.
2. **Fyers (v3)**: Specialized for Order Flow with 50-level depth and Tick-by-Tick (TBT) feeds.
3. **Paper Trading Simulator**: Default active execution engine in `broker_client.py` allowing risk-free validation of signals and GoCharting webhooks with ₹10,00,000 virtual capital.
4. **GoCharting Webhooks**: Router in `broker_client.py` receives alert webhooks from GoCharting charts and automatically routes order dispatch.

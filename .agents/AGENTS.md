# AGENTS.md: Institutional Trading & Screening Engine Agent Guide

This document defines the operational procedures, architecture, command interfaces, and multi-persona committee protocols for autonomous agents working within this repository.

---

## 1. Daily Core Workflow Commands

Agents and operators should execute the following 4-step routine for daily EOD screening and stock evaluation:

```bash
# 1. Run the daily smart delta sync (or let the cron job do it automatically at 20:00 IST)
./.venv/bin/python data_sync.py

# 2. Screen for institutional accumulation (Delivery >= 70% AND Volume >= 2x)
./.venv/bin/python delivery_filter.py --mode both -d 70.0 -v 2.0 --top 20

# 3. Convene the committee on any stock (e.g. MOTHERSON, KOTAKBANK, WIPRO)
./.venv/bin/python analyst_committee.py --symbol KOTAKBANK

# 4. Convene the committee on today's top screened stocks
./.venv/bin/python analyst_committee.py --top-screened --top 3
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
│   └── institutional_signals.csv # Latest screened institutional setups
├── logs/
│   └── cron_bhavcopy.log         # Automated cron EOD ingestion logs
├── scripts/
│   └── cron_bhavcopy_sync.sh     # Daily cron execution script
├── analyst_committee.py          # Multi-persona committee decision engine
├── data_sync.py                  # Incremental delta & historical ingestion engine
├── delivery_filter.py            # High-speed disk-based screening engine
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

2. **Bhavcopy Timing**:
   - Market closes: 15:30 IST (10:00 UTC).
   - Deliverable Bhavcopy published: 18:00 – 19:30 IST (occasionally up to 20:00 IST on high-volume/expiry Thursdays).
   - Optimal sync window: **20:00 IST (14:30 UTC)**.

3. **Cron Automation**:
   - Automated via `crontab -l`: runs `scripts/cron_bhavcopy_sync.sh` at 14:30 UTC (20:00 IST) and 15:00 UTC (20:30 IST) Monday through Friday.

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

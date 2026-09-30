# NSE F&O Delivery & Volume Spike Screening Engine

A high-performance quantitative research and screening engine for all 213 active National Stock Exchange (NSE) Futures & Options (F&O) underlying equities.

All historical data (OHLCV, trades, turnover, deliverable quantity, and delivery percentage) is downloaded and cached locally on your machine as standardized CSV files. This enables sub-second parameter tuning, offline screening, and volume spike detection across hundreds of stocks without incurring network latency or hitting exchange rate limits.

---

## Table of Contents
1. [Architecture & Project Structure](#architecture--project-structure)
2. [Quick Start](#quick-start)
3. [Bhavcopy Update Timetable & Delta Sync](#bhavcopy-update-timetable--delta-sync)
4. [Data Synchronization CLI (`data_sync.py`)](#data-synchronization-cli-data_syncpy)
5. [Screening & Filtering CLI (`delivery_filter.py`)](#screening--filtering-cli-delivery_filterpy)
6. [Comprehensive Terminal Command Reference](#comprehensive-terminal-command-reference)
7. [Key Market Findings & Institutional Footprints](#key-market-findings--institutional-footprints)
8. [Local Dataset Schema](#local-dataset-schema)
9. [Scheduled Automation](#scheduled-automation)

---

## Architecture & Project Structure

```
algo-trading/
├── .agents/                      # Antigravity Rules & Skills for the Trading Committee
├── data/
│   ├── fno_symbols.json          # 213 F&O underlying symbols and company names
│   ├── historical/               # Standardized CSV datasets per symbol
│   │   ├── MOTHERSON.csv
│   │   ├── RELIANCE.csv
│   │   ├── KOTAKBANK.csv
│   │   ├── WIPRO.csv
│   │   └── ... (213 files)
│   └── institutional_signals.csv # Pre-screened institutional signals
├── logs/
│   └── cron_bhavcopy.log         # Automatic cron sync and screener logs
├── scripts/
│   └── cron_bhavcopy_sync.sh     # Executable cron task runner
├── analyst_committee.py          # Multi-Persona Trading & Investment Committee Simulator
├── data_sync.py                  # Incremental Delta & Historical Ingestion Engine
├── delivery_filter.py            # High-speed Multi-Symbol Screening & Analysis Engine
├── requirements.txt              # Project dependencies (pandas, nselib, requests, tqdm)
└── README.md                     # Documentation & Command Manual
```

### Core Design Principles:
1. **Local-First Speed**: Scans all 213 stocks (~39,000 candles) directly from disk in **under 1.5 seconds**.
2. **Single-Request Smart Delta Sync**: Daily updates download only the consolidated EOD Deliverable Bhavcopy (~400 KB) in one HTTP request, updating all 213 stocks in **under 1 second**.
3. **Institutional Signal Detection**: Combines delivery percentage with rolling volume moving averages (SMA) to differentiate genuine institutional cash accumulation from intraday churn.

---

## Quick Start: Daily Institutional Workflow

Activate the virtual environment or run directly via `./.venv/bin/python`:

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

## Bhavcopy Update Timetable & Delta Sync

The National Stock Exchange updates daily reports in distinct stages after the trading session closes:

| Stage | Time (IST) | Description & Availability |
|---|---|---|
| **Market Close** | **15:30 (3:30 PM)** | Normal market trading ceases. Closing auction & post-close sessions run until 16:00. |
| **Provisional Bhavcopy** | **16:30 – 17:15 (4:30 – 5:15 PM)** | Closing prices, high/low, and traded volume (OHLCV). **No deliverable volume** is present at this stage. |
| **Full Deliverable Bhavcopy** | **18:00 – 19:30 (6:00 – 7:30 PM)** | **Final Deliverable Volume & Delivery %** are published (`sec_bhavdata_full_ddmmyyyy.csv`). Clearing corporations (NSDL, CDSL, NSCCL) finish client margin and clearing settlement. |
| **Expiry / High-Volume Days** | **Up to 20:00 (8:00 PM)** | On monthly/weekly expiry days (Thursdays) or heavy volume days, final files can be delayed up to 8:00 PM. |

> **Recommended Daily Sync Window**: Any time **after 19:30 or 20:00 IST (7:30 PM – 8:00 PM)**.

### Why Delta Updates?
You do **NOT** re-download the entire 9-month dataset every day:
- **Fast**: Pulls a single consolidated 400 KB file for the entire market instead of making 213 individual stock queries.
- **Idempotent**: Automatically checks whether a date already exists in each symbol's CSV. Running the command multiple times will not insert duplicates.
- **Auto-Backfill**: If you missed days (e.g. over a weekend or holiday), running `data_sync.py` detects missing trading dates and backfills only those days.

---

## Data Synchronization CLI (`data_sync.py`)

Handles both daily incremental delta updates and full multi-threaded historical backfills.

### Command-Line Arguments:

| Argument | Type | Default | Description |
|---|---|---|---|
| *(no args)* | Flag | - | Runs **Smart Incremental Delta Sync** (detects missing days & appends). |
| `--delta` | Flag | - | Explicitly triggers the smart delta sync. |
| `--date` | String | `None` | Syncs a specific historical date's Bhavcopy delta (`DD-MM-YYYY` or `YYYY-MM-DD`). |
| `--full` | Flag | - | Forces a full re-download of all 213 stocks from `--from-date` to `--to-date`. |
| `--symbol` | String | `None` | Downloads/refreshes a single stock only (e.g., `--symbol MOTHERSON`). |
| `--from-date` | String | `01-01-2026` | Start date for full backfill (`DD-MM-YYYY`). |
| `--to-date` | String | `30-09-2026` | End date for full backfill (`DD-MM-YYYY`). |

---

## Screening & Filtering CLI (`delivery_filter.py`)

Scans all locally stored CSV files (or a specified stock) with configurable parameters.

### Command-Line Arguments:

| Argument | Short | Default | Description |
|---|---|---|---|
| `--symbol` | `-s` | `None` (All) | Target symbol (e.g. `MOTHERSON`). Scans all 213 stocks if omitted. |
| `--min-delivery` | `-d` | `70.0` | Minimum delivery percentage threshold. |
| `--volume-spike` | `-v` | `2.0` | Minimum volume multiplier vs rolling SMA (e.g., `2.0` = 2x average volume). |
| `--window` | `-w` | `20` | Rolling lookback window for average volume calculation (default: 20 trading days). |
| `--mode` | `-m` | `both` | `both` (high delivery AND volume spike), `delivery` (delivery only), `spike` (volume spike only), `either` (either condition). |
| `--min-volume` | - | `50,000` | Minimum traded quantity threshold to filter out illiquid days. |
| `--from-date` | - | `None` | Start date filter (`YYYY-MM-DD` or `DD-MM-YYYY`). |
| `--to-date` | - | `None` | End date filter (`YYYY-MM-DD` or `DD-MM-YYYY`). |
| `--sort-by` | - | `date` | Sort results by `date`, `spike`, `delivery`, `volume`, or `symbol`. |
| `--top` | - | `None` | Limit number of displayed rows (e.g., `--top 20`). |
| `--export` | `-o` | `None` | Export matched results to a CSV file (e.g., `data/screened_results.csv`). |
| `--sync` | - | `False` | Trigger smart delta sync before scanning. |

---

## Comprehensive Terminal Command Reference

### 1. Data Ingestion & Syncing Commands

```bash
# 1. Daily Smart Delta Sync (Standard EOD command after 7:30 PM IST)
./.venv/bin/python data_sync.py

# 2. Sync delta for a specific date (e.g. if you missed a specific trading session)
./.venv/bin/python data_sync.py --date 30-09-2026

# 3. Refresh a single stock from scratch
./.venv/bin/python data_sync.py --symbol MOTHERSON

# 4. Force full historical backfill for all 213 symbols
./.venv/bin/python data_sync.py --full

# 5. Full backfill with a custom date range
./.venv/bin/python data_sync.py --full --from-date 01-03-2026 --to-date 30-09-2026
```

---

### 2. Combined Institutional Signal Commands (High Delivery + Volume Spike)

When institutional investors aggressively accumulate or offload large positions in the cash market, trading volume surges significantly above normal and delivery percentages spike above 70%.

```bash
# Standard institutional accumulation screen (Delivery >= 70% AND Volume >= 2.0x 20D SMA)
./.venv/bin/python delivery_filter.py --mode both -d 70.0 -v 2.0 --top 20

# Extreme institutional footprint (Delivery >= 75% AND Volume >= 3.0x 20D SMA)
./.venv/bin/python delivery_filter.py --mode both -d 75.0 -v 3.0

# Sort combined signals by highest volume spike ratio first
./.venv/bin/python delivery_filter.py --mode both -d 70.0 -v 2.0 --sort-by spike --top 25

# Sort combined signals by highest delivery percentage first
./.venv/bin/python delivery_filter.py --mode both -d 70.0 -v 2.0 --sort-by delivery --top 25

# Use a longer 50-day volume baseline to detect macro spikes
./.venv/bin/python delivery_filter.py --mode both -d 70.0 -v 2.0 -w 50 --top 20
```

---

### 3. Volume Spike Only Commands

Detect unusual surges in trading activity regardless of delivery % (identifies momentum, breakouts, block deals, or volatility triggers).

```bash
# Find trading days where volume was at least 3.0x the 20-day moving average
./.venv/bin/python delivery_filter.py --mode spike -v 3.0 --top 20

# Find top 15 extreme volume explosions (sorted by highest spike multiplier)
./.venv/bin/python delivery_filter.py --mode spike -v 5.0 --sort-by spike --top 15

# Find volume spikes with a minimum liquidity floor (e.g. at least 500,000 shares traded)
./.venv/bin/python delivery_filter.py --mode spike -v 2.5 --min-volume 500000 --top 20
```

---

### 4. High Delivery Only Commands

Detect days where retail speculation was low and delivery absorption was exceptionally high.

```bash
# Scan for all trading days with Delivery >= 70%
./.venv/bin/python delivery_filter.py --mode delivery -d 70.0 --top 25

# Ultra-high delivery days (Delivery >= 80%)
./.venv/bin/python delivery_filter.py --mode delivery -d 80.0 --sort-by delivery --top 20

# High delivery days sorted by total traded volume
./.venv/bin/python delivery_filter.py --mode delivery -d 70.0 --sort-by volume --top 20
```

---

### 5. Single Stock Deep-Dive Commands

```bash
# Check MOTHERSON for high delivery days (Delivery >= 70%)
./.venv/bin/python delivery_filter.py --symbol MOTHERSON --mode delivery -d 70.0

# Check RELIANCE for combined signals (Delivery >= 65% and Volume >= 1.5x)
./.venv/bin/python delivery_filter.py --symbol RELIANCE --mode both -d 65.0 -v 1.5

# Check KOTAKBANK for all volume spikes >= 2x
./.venv/bin/python delivery_filter.py --symbol KOTAKBANK --mode spike -v 2.0

# Check WIPRO across all historical days meeting either condition
./.venv/bin/python delivery_filter.py --symbol WIPRO --mode either -d 75.0 -v 3.0
```

---

### 6. Date Range Filtering & Export Commands

```bash
# Scan only September 2026 for combined signals
./.venv/bin/python delivery_filter.py --mode both -d 70.0 -v 2.0 --from-date 2026-09-01 --to-date 2026-09-30

# Export institutional signals to a CSV file for Excel / Pandas analysis
./.venv/bin/python delivery_filter.py --mode both -d 70.0 -v 2.0 --export data/institutional_signals.csv

# Automatically update local data before running the screen
./.venv/bin/python delivery_filter.py --sync --mode both -d 70.0 -v 2.0 --top 20
```

### 7. Multi-Persona Trading & Investment Committee Commands

Simulate a full institutional debate across 4 specialized personas equipped with **Screener.in fundamental data** and **NSE delivery analytics**:
- **Momentum Trader**: Price action, 20D/50D SMAs, volume expansion, ATR-based entries & stop-losses.
- **Delivery Tracker**: Depository delivery absorption, volume spikes, and **FII/DII QoQ shareholding changes**.
- **Value Investor**: Powered by Screener.in (Market Cap, P/E, P/B, ROCE, ROE, 5Y Profit CAGR, Strengths & Red Flags).
- **Quantitative Risk Analyst**: Volume Z-Scores, ATR volatility %, fundamental red-flag analysis, and position sizing.
- **Chief Investment Officer (CIO)**: Weighted composite score (-10 to +10) and final consensus action plan.

```bash
# Convene committee for a specific stock (e.g. MOTHERSON, KOTAKBANK, WIPRO)
./.venv/bin/python analyst_committee.py --symbol MOTHERSON
./.venv/bin/python analyst_committee.py --symbol KOTAKBANK
./.venv/bin/python analyst_committee.py --symbol WIPRO

# Automatically evaluate the top 3 institutional screened candidates from today's screen
./.venv/bin/python analyst_committee.py --top-screened --top 3

# Fetch raw Screener.in fundamental metrics directly
./.venv/bin/python screener_client.py MOTHERSON
```

### 8. Screener MCP Server (`screener-mcp`) Integration

Configured in `.agents/mcp_config.json` and `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "screener": {
      "command": "/home/beast/.local/bin/uvx",
      "args": ["screener-mcp"]
    }
  }
}
```

This equips the AI agent with 30 fundamental analysis tools from Screener.in:
- `get_company_overview`: Key financial ratios, P/E, ROCE, ROE, and Screener pros/cons.
- `get_financials`: Detailed P&L, Balance Sheet, Cash Flow, and financial ratios.
- `get_quarterly_results`: Revenue, operating profit, and net profit for the last 8 quarters.
- `get_shareholding_pattern`: Institutional ownership trends (FIIs, DIIs, Promoters, Public).
- `analyze_red_flags`: Rule-based audit red flags over the company's full operating history.
- `compare_companies`: Side-by-side comparative analysis of peer stocks.

---

## Key Market Findings & Institutional Footprints

Sample signals uncovered by running the screening engine across our 2026 F&O dataset:

1. **WIPRO (29-Sep-2026)**:
   - Traded Quantity: `164,453,787` (vs 20D SMA of `18,092,148` $\rightarrow$ **9.09x Volume Spike**)
   - Deliverable Quantity: `144,035,654` (**87.58% Delivery**)
   - *Interpretation*: Enormous cash delivery buying with over 144 million shares locked in demat accounts.

2. **BSE (29-Sep-2026)**:
   - Traded Quantity: `30,101,047` (vs 20D SMA of `5,495,980` $\rightarrow$ **5.48x Volume Spike**)
   - Delivery %: **75.21%** (`22,637,963` shares delivered)

3. **KOTAKBANK (30-Sep-2026)**:
   - Traded Quantity: `32,537,029` (vs 20D SMA of `13,155,095` $\rightarrow$ **2.47x Volume Spike**)
   - Deliverable Quantity: `24,934,520` (**76.63% Delivery**, 97.3th percentile)
   - *Committee Verdict*: **STRONG BUY / HIGH CONVICTION** (+7.10/10)

4. **VMM (27-Feb-2026)**:
   - Traded Quantity: `786,031,801` (vs 20D SMA of `47,343,777` $\rightarrow$ **16.60x Volume Spike**)
   - Deliverable Quantity: `675,298,112` (**85.91% Delivery**)

5. **MOTHERSON (18-Sep-2026)**:
   - Traded Quantity: `19,068,300` (vs 20D SMA of `11,044,574` $\rightarrow$ **1.73x Volume**)
   - Delivery %: **76.17%** (`14,523,618` shares delivered)

---

## Local Dataset Schema

Every CSV in `data/historical/<SYMBOL>.csv` contains 15 standardized columns:

| Column Name | Type | Description |
|---|---|---|
| `Symbol` | String | NSE Ticker Symbol (e.g. `MOTHERSON`) |
| `Series` | String | Security Series (Standard equity: `EQ`) |
| `Date` | String | ISO Format Date (`YYYY-MM-DD`) |
| `PrevClose` | Float | Previous trading day's closing price (₹) |
| `Open` | Float | Session opening price (₹) |
| `High` | Float | Session high price (₹) |
| `Low` | Float | Session low price (₹) |
| `Last` | Float | Last traded price at close (₹) |
| `Close` | Float | Final weighted closing price (₹) |
| `VWAP` | Float | Volume Weighted Average Price (Average Price) |
| `TradedQty` | Integer | Total traded shares in the session |
| `Turnover` | Float | Total traded value in ₹ |
| `Trades` | Integer | Number of trades executed |
| `DeliverableQty` | Float | Quantity of shares marked for actual delivery |
| `DeliveryPercent` | Float | Percentage of traded quantity delivered (`DELIV_PER`) |

---

## Scheduled Automation (Active on System)

The automated cron task is **installed and active** on your system crontab (`crontab -l`):

```cron
# NSE Daily Bhavcopy Delta Sync and Screening (20:00 IST / 14:30 UTC Mon-Fri)
30 14 * * 1-5 /home/beast/algo-trading/scripts/cron_bhavcopy_sync.sh
# Catch-up run at 20:30 IST / 15:00 UTC Mon-Fri
00 15 * * 1-5 /home/beast/algo-trading/scripts/cron_bhavcopy_sync.sh
```

### What the Cron Task Does Daily:
1. Runs at 20:00 IST and 20:30 IST (14:30 & 15:00 UTC) Monday through Friday.
2. Executes `scripts/cron_bhavcopy_sync.sh`.
3. Downloads the day's consolidated delivery Bhavcopy (`sec_bhavdata_full_ddmmyyyy.csv`) from NSE.
4. Appends the delta row to each of the 213 local CSV files in `data/historical/`.
5. Automatically runs the screener (`delivery_filter.py`) and refreshes `data/institutional_signals.csv`.
6. Logs the complete execution output with timestamps to `logs/cron_bhavcopy.log`.

### Manual Testing of the Cron Task:
To test the exact cron runner anytime:
```bash
./scripts/cron_bhavcopy_sync.sh
cat logs/cron_bhavcopy.log
```

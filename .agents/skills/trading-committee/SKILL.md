---
name: trading-committee
description: >-
  Convenes the Multi-Persona Institutional Trading & Investment Committee
  (Momentum Trader, Delivery Tracker, Value Investor, Risk Analyst, and CIO)
  equipped with Screener.in fundamental analysis and NSE quantitative datasets.
---

# Trading & Investment Committee Skill

This skill equips the agent to conduct institutional equity research combining:
1. **Quantitative NSE Cash & Delivery Datasets**: Historical candle analysis, delivery percentages, volume spikes, and ATR.
2. **Screener.in Fundamental Engine (`screener-mcp`)**: Valuation multiples (P/E, P/B), capital efficiency (ROCE, ROE), shareholding pattern (Promoter/FII/DII QoQ trends), and Screener pros/cons & red flags.

## Team Member Skillsets & Roles

### 1. Momentum & Breakout Trader
- **Tools**: Historical price action, 20D/50D SMAs, volume expansion multipliers.
- **Output**: Tactical entry zone, ATR-based stop-loss (1.5x ATR), Target 1 & 2 (1:1.5+ Risk-Reward).

### 2. Institutional Delivery Tracker (Smart Money)
- **Tools**: Depository deliverable quantities (`DELIV_PER`), cash absorption index, and **Screener.in FII/DII shareholding trends**.
- **Output**: Evaluation of real institutional accumulation vs retail churning.

### 3. Fundamental Value Investor (Powered by Screener.in / `screener-mcp`)
- **Tools**: `get_company_overview`, `get_financials`, `get_quarterly_results`, `analyze_red_flags`.
- **Ratios Analyzed**:
  - Valuation: Stock P/E, Price to Book (P/B), Market Cap.
  - Return Ratios: ROCE (>15% benchmark), ROE (>15% benchmark).
  - Growth: 5-Year Profit CAGR, 3-Year ROE.
  - Screener.in Strengths (Pros) & Red Flags (Cons).
- **Output**: Intrinsic value assessment, margin of safety, and recommended 1–3 year holding horizon.

### 4. Quantitative Risk & Research Analyst
- **Tools**: Statistical Volume Z-Score ($\sigma$), Average True Range (ATR %), Screener red-flag weighting.
- **Output**: Volatility regime identification and fractional portfolio position sizing (1% risk model).

### 5. Chief Investment Officer (CIO) Synthesis
- **Output**: Composite weighted score (-10 to +10) and final actionable consensus verdict:
  - `STRONG BUY / HIGH CONVICTION` (Score ≥ +4.0)
  - `ACCUMULATE ON PULLBACKS` (Score +1.5 to +4.0)
  - `NEUTRAL / WATCHLIST` (Score -1.5 to +1.5)
  - `AVOID / TAKE PROFIT` (Score < -1.5)

---

## Execution Methods

### CLI Execution
```bash
# Evaluate any stock with full fundamental & quantitative committee
./.venv/bin/python analyst_committee.py --symbol <SYMBOL>

# Evaluate top screened institutional stocks
./.venv/bin/python analyst_committee.py --top-screened --top 3
```

### Screener MCP Tools Available to the Agent:
- `search_company(query)`: Lookup symbol and metadata.
- `get_company_overview(symbol)`: Key ratios, P/E, ROCE, ROE, 52W range, pros/cons.
- `get_financials(symbol)`: P&L, Balance Sheet, Cash Flow statements.
- `get_quarterly_results(symbol)`: Last 8 quarters revenue & net profit.
- `get_shareholding_pattern(symbol)`: Promoter, FII, DII holding trends.
- `analyze_red_flags(symbol)`: Rule-based red-flag detection.
- `get_peer_comparison(symbol)`: Industry valuation benchmark.

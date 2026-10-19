---
name: gocharting-sdk
description: >-
  Expert instructions and reference patterns for the GoCharting Charting SDK (@gocharting/chart-sdk),
  including custom datafeed integration, UDF endpoints, Order Flow & Footprint setup,
  Trade-from-Chart host execution via appCallback, and TradingView-to-GoCharting migration.
---

# GoCharting SDK Skill

This skill equips autonomous agents with authoritative expertise on integrating, configuring, and extending the **GoCharting SDK (`@gocharting/chart-sdk`)** and its Universal Data Feed (UDF) HTTP / WebSocket protocols.

All rules and patterns in this skill are grounded in the official GoCharting SDK specification and knowledge file located at `references/gocharting-sdk-context.txt`.

---

## 1. Core Principles & Ground Truth Rules

When generating code or designing architectures for GoCharting SDK:

1. **Host-Driven Trading via `appCallback`**:
   - **NEVER** invent or import a TradingView `Broker API` or `broker_factory`.
   - GoCharting trading is entirely host-driven:
     - Configure `trading: { enableTrading: true, showOpenOrders: true, showPositions: true, showExecutions: true }`.
     - Listen to trading actions via `appCallback({ eventType, message, onClose })`.
     - Update broker status on chart instance using `chartInstance.setBrokerAccounts({ accountList, orderBook, tradeBook, positions })` and `chartInstance.updatePositions(positions)`.

2. **Real-time Streaming Exclusivity**:
   - Implement **either** `subscribeTicks` (tick-level; SDK aggregates into bars) **OR** `subscribeBars` (host pushes complete OHLCV bars) — **never both**.
   - For order flow / 1-minute aggregations where the host has pre-formed bars, prefer `subscribeBars`.

3. **Footprint & Order Flow Eligibility**:
   - To enable footprint and order flow volume tools for a symbol, the `SymbolInfo` returned by `resolveSymbol` must specify:
     ```javascript
     supports: {
       footprint: true
     }
     ```
   - OI profile metrics can be toggled via `chartInstance.setOIProfile('volume' | 'delta' | 'oi')`.

4. **Chart Layout & State Persistence**:
   - While `save_load_adapter` is supported for simple TV-like embeds, production GoCharting persistence uses `appCallback`:
     - Events: `SAVE_CHART`, `UPDATE_CHART`, `DELETE_CHART`, `LOAD_CHART`, `LIST_CHARTS`.
     - Payloads contain: `layout`, `chartComponentList`, and `layoutState`.

5. **Indian Market (NSE) Specifications**:
   - Trading Hours: `0915-1530` (Monday–Friday).
   - Timezone: `Asia/Kolkata`.
   - Currency: `INR`.
   - Pricescale: `100` (for 2 decimal places, minmov: `5` for 0.05 tick size).

---

## 2. Basic Initialization Pattern

```javascript
import { createChart } from "@gocharting/chart-sdk";

const chart = createChart("#chart-container", {
  symbol: "NSE:KOTAKBANK",
  interval: "1", // 1-minute bars
  datafeed: customDatafeed, // or new UDFCompatibleDatafeed("/api/gocharting")
  licenseKey: process.env.GOCHARTING_LICENSE_KEY || "YOUR_LICENSE_KEY",
  theme: "dark",
  responsive: true,
  autoFit: true,

  trading: {
    enableTrading: true,
    showOpenOrders: true,
    showPositions: true,
    showExecutions: true,
  },

  appCallback: ({ eventType, message, onClose }) => {
    switch (eventType) {
      case "PLACE_ORDER":
        handleBrokerOrder(message.order);
        if (onClose) onClose();
        break;
      case "CANCEL_ORDER":
        handleBrokerCancel(message.orderId);
        break;
      case "CLOSE_POSITION":
        handleBrokerSquareOff(message.symbol);
        break;
      case "SAVE_CHART":
        saveChartToServer(message);
        break;
    }
  },

  onReady: (chartInstance) => {
    // Populate broker account data on chart
    chartInstance.setBrokerAccounts({
      accountList: [{
        id: "PAPER_ACCOUNT",
        name: "Paper Trading Engine",
        currency: "INR",
        balance: 950000,
        equity: 1000000
      }],
      orderBook: [],
      tradeBook: [],
      positions: []
    });
  }
});
```

---

## 3. Datafeed Specification

### Required Datafeed Methods:
- `getBars(symbolInfo, resolution, periodParams): Promise<BarsResult>`
  - Fetches historical bars between `periodParams.from` and `periodParams.to` (Unix epoch seconds).
  - Returns `{ bars: [{ time: ms, open, high, low, close, volume }], meta: { noData: boolean } }`.
- `resolveSymbol(symbolName, onResolve, onError): void`
  - Resolves ticker metadata, session hours, price scale, and feature flags (`supports: { footprint: true }`).

### Optional Real-Time Methods:
- `subscribeBars(symbolInfo, resolution, onRealtimeCallback, subscriberUID)`:
  - Registers a listener. When a new 1-minute candle arrives, calls `onRealtimeCallback({ time: ms, open, high, low, close, volume })`.
- `unsubscribeBars(subscriberUID)`:
  - Cleans up subscription.

---

## 4. Standard UDF HTTP Endpoints (Backend Server)

A GoCharting-compliant server exposes:

1. `GET /api/gocharting/config`
   - Returns `{ supported_resolutions: ["1", "3", "5", "15", "30", "60", "D"], supports_search: true, supports_group_request: false, supports_marks: false, supports_timescale_marks: false }`
2. `GET /api/gocharting/time`
   - Returns current integer unix epoch seconds.
3. `GET /api/gocharting/symbols?symbol=<TICKER>`
   - Returns JSON `SymbolInfo` object.
4. `GET /api/gocharting/history?symbol=<TICKER>&resolution=<RES>&from=<FROM>&to=<TO>`
   - Returns `{ s: "ok", t: [...], o: [...], h: [...], l: [...], c: [...], v: [...] }` or `{ s: "no_data" }`.
5. `GET /api/gocharting/search?query=<QUERY>&exchange=NSE&type=stock&limit=30`
   - Returns array of matching symbols: `[{ symbol, full_name, description, exchange, type, ticker }]`.

---

## 5. TradingView to GoCharting Migration Cheatsheet

| TradingView Pattern | GoCharting Equivalent |
| :--- | :--- |
| `broker_factory` / Broker API | `trading: { enableTrading: true }` + `appCallback` (`PLACE_ORDER`, `CANCEL_ORDER`) |
| `broker.setPositions()` | `chartInstance.setBrokerAccounts(...)` or `chartInstance.updatePositions(...)` |
| `widget.activeChart().createStudy(...)` | `chartInstance.addIndicator(name, options)` |
| `widget.activeChart().setSymbol(...)` | `chartInstance.setSymbol(symbol, interval)` |
| `widget.activeChart().setVisibleRange(...)` | `chartInstance.setVisibleRange({ from, to })` |
| `widget.activeChart().exportData()` | Built-in CSV export or `chartInstance.getBars()` |
| `save_load_adapter` (exclusive) | Supported, but production apps also use `appCallback` (`SAVE_CHART`, `LOAD_CHART`) |

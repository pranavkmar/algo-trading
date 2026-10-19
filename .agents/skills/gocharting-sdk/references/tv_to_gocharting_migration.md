# TradingView to GoCharting SDK Migration Guide

This reference provides a direct mapping for developers and AI agents migrating host applications from TradingView Charting Library to the **GoCharting SDK (`@gocharting/chart-sdk`)**.

---

## 1. Architectural Differences

| Concept | TradingView Library | GoCharting SDK |
| :--- | :--- | :--- |
| **Package** | Proprietary static bundle (`charting_library/`) | NPM package `@gocharting/chart-sdk` |
| **Broker Integration** | Custom `broker_factory` implementing `IBrokerTerminal` interface | Direct `trading` config + `appCallback` event listener |
| **Broker Updates** | Polling via callbacks on `host` object | Push updates via `chartInstance.setBrokerAccounts()` & `chartInstance.updatePositions()` |
| **Order Flow / Footprint** | External Pine scripts or custom canvas overlays | Native footprint engine (`supports: { footprint: true }`, `setOIProfile`) |
| **Datafeed Interface** | `JSDatafeed` / `IBasicDataListener` | `Datafeed` (clean async/await Promises for `getBars`) |
| **Chart Persistence** | Required `save_load_adapter` | Supported via `save_load_adapter` OR `appCallback` (`SAVE_CHART`, `LOAD_CHART`, etc.) |

---

## 2. API Method Translation Table

| TV Charting Library Method | GoCharting SDK Equivalent Method |
| :--- | :--- |
| `new TradingView.widget(options)` | `createChart(container, options)` |
| `widget.onChartReady(callback)` | `onReady: (chartInstance) => ...` (in options) |
| `widget.activeChart().setSymbol(sym, tf)` | `chartInstance.setSymbol(sym, tf)` |
| `widget.activeChart().createStudy(name, ...)` | `chartInstance.addIndicator(name, options)` |
| `widget.activeChart().removeEntity(id)` | `chartInstance.removeIndicator(id)` |
| `widget.activeChart().setVisibleRange({from, to})`| `chartInstance.setVisibleRange({from, to})` |
| `widget.activeChart().executeActionById(...)` | `chartInstance.executeAction(actionId)` |
| `widget.applyOverrides(overrides)` | `chartInstance.applyTheme(themeOptions)` |
| `widget.subscribe("onAutoSaveNeeded", fn)` | Handled via `auto_save_delay` or `appCallback("SAVE_CHART")` |

---

## 3. Datafeed Mapping

```javascript
// TradingView:
datafeed.getBars(symbolInfo, resolution, periodParams, onHistoryCallback, onErrorCallback);

// GoCharting SDK:
async getBars(symbolInfo, resolution, periodParams) {
  const { from, to, countBack } = periodParams;
  const res = await fetch(`/api/gocharting/history?symbol=${symbolInfo.name}&resolution=${resolution}&from=${from}&to=${to}`);
  const data = await res.json();
  if (data.s === "no_data") {
    return { bars: [], meta: { noData: true } };
  }
  const bars = data.t.map((time, i) => ({
    time: time * 1000,
    open: data.o[i],
    high: data.h[i],
    low: data.l[i],
    close: data.c[i],
    volume: data.v[i]
  }));
  return { bars, meta: { noData: false } };
}
```

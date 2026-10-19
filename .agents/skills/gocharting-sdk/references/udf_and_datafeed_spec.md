# GoCharting UDF & Custom Datafeed Specification

This reference outlines the exact data contracts, types, and endpoint schemas for implementing a GoCharting-compatible datafeed.

---

## 1. Universal Data Feed (UDF) HTTP Endpoints

### 1.1 GET /api/gocharting/config
Server capability handshake.
```json
{
  "supports_search": true,
  "supports_group_request": false,
  "supports_marks": false,
  "supports_timescale_marks": false,
  "supports_time": true,
  "supported_resolutions": ["1", "3", "5", "15", "30", "60", "D", "W", "M"]
}
```

### 1.2 GET /api/gocharting/time
Server time synchronization.
- **Response**: Integer Unix timestamp in seconds, e.g. `1790856000` or plain text.

### 1.3 GET /api/gocharting/symbols?symbol=<SYMBOL>
Resolves symbol metadata.
```json
{
  "name": "KOTAKBANK",
  "ticker": "NSE:KOTAKBANK",
  "description": "Kotak Mahindra Bank Limited",
  "type": "stock",
  "session": "0915-1530",
  "exchange": "NSE",
  "listed_exchange": "NSE",
  "timezone": "Asia/Kolkata",
  "minmov": 5,
  "pricescale": 100,
  "minmove2": 0,
  "fractional": false,
  "has_intraday": true,
  "has_daily": true,
  "has_weekly_and_monthly": true,
  "supported_resolutions": ["1", "3", "5", "15", "30", "60", "D"],
  "intraday_multipliers": ["1", "3", "5", "15", "30", "60"],
  "currency_code": "INR",
  "volume_precision": 0,
  "supports": {
    "footprint": true,
    "volume_profile": true
  }
}
```

### 1.4 GET /api/gocharting/history?symbol=<SYMBOL>&resolution=<RES>&from=<FROM>&to=<TO>
Fetches historical bars between `from` and `to` (Unix epoch seconds).
- `resolution`: `"1"`, `"5"`, `"15"`, `"60"`, `"D"`
- **Response on Success (`s: "ok"`):**
```json
{
  "s": "ok",
  "t": [1790826900, 1790826960, 1790827020],
  "o": [415.20, 415.50, 415.40],
  "h": [416.00, 415.80, 416.10],
  "l": [415.10, 415.30, 415.35],
  "c": [415.50, 415.40, 416.00],
  "v": [14200, 11500, 18900],
  "buy_volume": [8500, 6200, 12400],
  "sell_volume": [5700, 5300, 6500],
  "delta": [2800, 900, 5900]
}
```
- **Response when no data exists:**
```json
{
  "s": "no_data",
  "nextTime": null
}
```

### 1.5 GET /api/gocharting/search?query=<QUERY>&type=<TYPE>&exchange=<EXCHANGE>&limit=<LIMIT>
Symbol lookup / autocomplete.
```json
[
  {
    "symbol": "KOTAKBANK",
    "full_name": "NSE:KOTAKBANK",
    "description": "Kotak Mahindra Bank Limited",
    "exchange": "NSE",
    "type": "stock",
    "ticker": "NSE:KOTAKBANK"
  }
]
```

---

## 2. JavaScript Custom Datafeed Interface

```typescript
interface Datafeed {
  onReady(callback: (config: DatafeedConfiguration) => void): void;
  resolveSymbol(symbolName: string, onResolve: (info: SymbolInfo) => void, onError: (err: string) => void): void;
  getBars(symbolInfo: SymbolInfo, resolution: string, periodParams: PeriodParams): Promise<BarsResult>;
  searchSymbols(userInput: string, exchange: string, symbolType: string, onResult: (res: { searchInProgress: boolean; items: SearchResult[] }) => void): void;
  subscribeBars(symbolInfo: SymbolInfo, resolution: string, onRealtimeCallback: (bar: Bar) => void, subscriberUID: string): void;
  unsubscribeBars(subscriberUID: string): void;
}
```

# GoCharting Trade-from-Chart & appCallback Specification

GoCharting SDK provides a host-driven trading architecture. Unlike libraries that require external adapter classes, GoCharting surfaces trading events directly through `appCallback` and provides instance methods to update broker and position state.

---

## 1. Trading Configuration Options

To activate Trade from Chart, pass `trading` and `appCallback` into `createChart()`:

```javascript
createChart("#chart", {
  // ... core config ...
  trading: {
    enableTrading: true,         // Enable trading panel & order lines
    showOpenOrders: true,        // Display working order lines
    showPositions: true,         // Display position line & P&L badge
    showExecutions: true,        // Display fill arrows on bars
    showReverseButton: true,     // Allow one-click position reversal
    showNotifications: true,     // Desktop/in-chart toast notifications
    beep: true,                  // Audio sound on execution
    quickTradeMode: false,       // Skip confirmation dialog
  },

  appCallback: ({ eventType, message, onClose }) => {
    // Process event
  }
});
```

---

## 2. Event Types & Payloads

### 2.1 PLACE_ORDER
Dispatched when the user clicks Buy/Sell in the chart header, places a limit/stop order line, or submits the order ticket.
- **Payload (`message.order`)**:
  ```javascript
  {
    symbol: "NSE:KOTAKBANK",
    side: "BUY",            // "BUY" | "SELL"
    type: "LIMIT",          // "MARKET" | "LIMIT" | "STOP" | "STOP_LIMIT"
    qty: 50,
    price: 415.50,          // Required for LIMIT / STOP_LIMIT
    stopPrice: 410.00,      // Required for STOP / STOP_LIMIT
    timeInForce: "DAY",     // "DAY" | "GTC" | "IOC"
    takeProfit: 425.00,     // Optional bracket target
    stopLoss: 408.00        // Optional bracket stop
  }
  ```
- **Handler**: Call `/api/order` with the payload, then call `if (onClose) onClose();`.

### 2.2 CANCEL_ORDER
Dispatched when the user cancels an order line on the chart.
- **Payload (`message`)**: `{ orderId: "ORD_12345" }`

### 2.3 CLOSE_POSITION
Dispatched when the user clicks the "X" button on the active position line.
- **Payload (`message`)**: `{ symbol: "NSE:KOTAKBANK" }`

### 2.4 MODIFY_ORDER / MODIFY_POSITION
Dispatched when dragging an order line or SL/TP handle to a new price level.
- **Payload (`message`)**: `{ orderId: "ORD_12345", price: 417.00, stopLoss: 411.00 }`

---

## 3. Synchronizing Broker Accounts & Positions

When the chart is ready (`onReady: (chartInstance) => ...`) or when order execution changes equity, push the updated state to the chart:

```javascript
chartInstance.setBrokerAccounts({
  accountList: [
    {
      id: "PAPER_01",
      name: "Institutional Paper Engine",
      currency: "INR",
      balance: 950707.00,
      equity: 1000000.00
    }
  ],
  orderBook: [
    {
      id: "ORD_01",
      symbol: "NSE:KOTAKBANK",
      side: "BUY",
      type: "LIMIT",
      qty: 100,
      price: 412.00,
      status: "OPEN"
    }
  ],
  tradeBook: [],
  positions: [
    {
      symbol: "NSE:KOTAKBANK",
      qty: 100,
      avgPrice: 415.00,
      currentPrice: 417.00,
      unrealizedPnl: 200.00,
      side: "LONG"
    }
  ]
});
```

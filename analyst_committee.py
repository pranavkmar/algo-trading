"""
analyst_committee.py - Multi-Persona Investment Committee & Trading Floor Simulator
Integrated with Screener.in Fundamental Data and NSE Quantitative Deliveries

Simulates an institutional quantitative committee composed of 4 specialized personas:
1. Momentum & Breakout Trader (Price action, volume surge, stop-loss, 1:2+ R:R)
2. Institutional Delivery Tracker (Smart money accumulation, FII/DII institutional trend)
3. Fundamental Value Investor (Screener.in P/E, ROCE, ROE, 5Y Profit CAGR, Red Flags)
4. Quantitative Risk Analyst (Volume Z-scores, ATR volatility, red flag risk, position sizing)
5. Chief Investment Officer (CIO) (Synthesizes the debate into a final consensus verdict)
"""

import os
import glob
import argparse
import numpy as np
import pandas as pd
from screener_client import fetch_screener_fundamentals

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HISTORICAL_DIR = os.path.join(DATA_DIR, "historical")


def load_symbol_history(symbol: str) -> pd.DataFrame:
    """Load and parse historical dataset for a symbol."""
    path = os.path.join(HISTORICAL_DIR, f"{symbol.upper().strip()}.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    if df.empty or 'Date' not in df.columns:
        return pd.DataFrame()
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
    return df


def calculate_quant_metrics(df: pd.DataFrame, symbol: str) -> dict:
    """Compute mathematical, technical, and delivery metrics on historical candles."""
    if len(df) < 20:
        return {}

    cols = ['Open', 'High', 'Low', 'Close', 'VWAP', 'TradedQty', 'DeliverableQty', 'DeliveryPercent']
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    # Price Moving Averages
    df['SMA20'] = df['Close'].rolling(20, min_periods=10).mean()
    df['SMA50'] = df['Close'].rolling(50, min_periods=20).mean()

    # Volume Statistics & Z-Score
    df['Vol_SMA20'] = df['TradedQty'].rolling(20, min_periods=10).mean()
    df['Vol_STD20'] = df['TradedQty'].rolling(20, min_periods=10).std()
    
    vol_sma20 = df['Vol_SMA20'].iloc[-1]
    vol_std20 = df['Vol_STD20'].iloc[-1] if df['Vol_STD20'].iloc[-1] > 0 else 1
    current_vol = latest['TradedQty']
    vol_spike_ratio = current_vol / vol_sma20 if vol_sma20 > 0 else 1.0
    vol_zscore = (current_vol - vol_sma20) / vol_std20 if vol_std20 > 0 else 0.0

    # Delivery Percentiles
    delivery_series = df['DeliveryPercent'].dropna()
    current_delivery = latest['DeliveryPercent']
    delivery_percentile = (delivery_series < current_delivery).mean() * 100 if len(delivery_series) > 0 else 50.0
    delivery_sma20 = delivery_series.rolling(20, min_periods=5).mean().iloc[-1]

    # Returns
    close_now = latest['Close']
    p5_close = df['Close'].iloc[-6] if len(df) >= 6 else df['Close'].iloc[0]
    p20_close = df['Close'].iloc[-21] if len(df) >= 21 else df['Close'].iloc[0]
    ret_1d = ((close_now - prev['Close']) / prev['Close']) * 100
    ret_5d = ((close_now - p5_close) / p5_close) * 100
    ret_20d = ((close_now - p20_close) / p20_close) * 100

    # 52-Week / Dataset Range
    high_all = df['High'].max()
    low_all = df['Low'].min()
    pct_from_high = ((close_now - high_all) / high_all) * 100
    pct_from_low = ((close_now - low_all) / low_all) * 100

    # ATR (Average True Range)
    tr1 = df['High'] - df['Low']
    tr2 = (df['High'] - df['Close'].shift(1)).abs()
    tr3 = (df['Low'] - df['Close'].shift(1)).abs()
    df['TR'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['ATR14'] = df['TR'].rolling(14, min_periods=5).mean()
    atr = df['ATR14'].iloc[-1] if pd.notnull(df['ATR14'].iloc[-1]) else (close_now * 0.02)

    # Fetch Screener.in Fundamentals
    fundamentals = fetch_screener_fundamentals(symbol)

    return {
        'symbol': symbol.upper(),
        'date': latest['Date'].strftime('%d-%b-%Y'),
        'close': close_now,
        'prev_close': prev['Close'],
        'vwap': latest.get('VWAP', close_now),
        'ret_1d': ret_1d,
        'ret_5d': ret_5d,
        'ret_20d': ret_20d,
        'sma20': df['SMA20'].iloc[-1],
        'sma50': df['SMA50'].iloc[-1] if pd.notnull(df['SMA50'].iloc[-1]) else df['SMA20'].iloc[-1],
        'volume': current_vol,
        'vol_sma20': vol_sma20,
        'vol_spike_ratio': vol_spike_ratio,
        'vol_zscore': vol_zscore,
        'delivery_pct': current_delivery,
        'delivery_sma20': delivery_sma20,
        'delivery_percentile': delivery_percentile,
        'deliv_qty': latest.get('DeliverableQty', 0),
        'atr': atr,
        'high_all': high_all,
        'low_all': low_all,
        'pct_from_high': pct_from_high,
        'pct_from_low': pct_from_low,
        'fundamentals': fundamentals
    }


def evaluate_momentum_trader(m: dict) -> dict:
    """Persona 1: Momentum & Breakout Trader."""
    score = 0
    signals = []
    
    if m['close'] > m['sma20']:
        score += 2
        signals.append("Price trading above 20D SMA (Short-term trend bullish)")
    else:
        score -= 2
        signals.append("Price trading below 20D SMA (Short-term trend sluggish)")

    if m['close'] > m['sma50']:
        score += 2
        signals.append("Price trading above 50D SMA (Medium-term trend intact)")

    if m['vol_spike_ratio'] >= 3.0:
        score += 4
        signals.append(f"Massive volume surge ({m['vol_spike_ratio']:.2f}x 20D avg) - Breakout ignition")
    elif m['vol_spike_ratio'] >= 1.8:
        score += 2
        signals.append(f"Above-average volume expansion ({m['vol_spike_ratio']:.2f}x 20D avg)")
    elif m['vol_spike_ratio'] < 0.8:
        score -= 2
        signals.append(f"Volume contraction ({m['vol_spike_ratio']:.2f}x avg) - Lacks momentum fuel")

    if m['ret_5d'] > 3.0:
        score += 2
        signals.append(f"Strong 5-day momentum (+{m['ret_5d']:.2f}%)")
    elif m['ret_5d'] < -3.0:
        score -= 2
        signals.append(f"Negative 5-day pressure ({m['ret_5d']:.2f}%)")

    stop_loss = round(m['close'] - (1.5 * m['atr']), 2)
    target_1 = round(m['close'] + (2.0 * m['atr']), 2)
    target_2 = round(m['close'] + (3.5 * m['atr']), 2)
    risk = m['close'] - stop_loss
    reward = target_1 - m['close']
    rr_ratio = round(reward / risk, 2) if risk > 0 else 1.0

    verdict = "BULLISH BREAKOUT" if score >= 4 else ("BEARISH / AVOID" if score <= -2 else "NEUTRAL / RANGEBOUND")

    return {
        'persona': 'Momentum Trader',
        'score': max(-10, min(10, score)),
        'verdict': verdict,
        'signals': signals,
        'entry': m['close'],
        'stop_loss': stop_loss,
        'target_1': target_1,
        'target_2': target_2,
        'rr_ratio': f"1:{rr_ratio}"
    }


def evaluate_delivery_tracker(m: dict) -> dict:
    """Persona 2: Institutional Accumulation / Delivery Tracker."""
    score = 0
    signals = []

    if m['delivery_pct'] >= 75.0:
        score += 5
        signals.append(f"Very high delivery ({m['delivery_pct']:.2f}%) - Heavy cash market absorption")
    elif m['delivery_pct'] >= 65.0:
        score += 3
        signals.append(f"Elevated delivery ({m['delivery_pct']:.2f}%) - Above institutional threshold")
    elif m['delivery_pct'] < 30.0:
        score -= 3
        signals.append(f"Low delivery ({m['delivery_pct']:.2f}%) - Dominated by intraday retail churn")

    if m['delivery_percentile'] >= 85.0:
        score += 3
        signals.append(f"Top-tier delivery percentile ({m['delivery_percentile']:.1f}% of historical sessions)")

    if m['delivery_pct'] >= 70.0 and m['vol_spike_ratio'] >= 2.0:
        score += 3
        signals.append("High Delivery % coupled with Volume Spike: High conviction institutional accumulation")

    # Corroborate with Screener FII/DII shareholding data
    funds = m.get('fundamentals', {})
    sh = funds.get('shareholding', {})
    fii_info = sh.get('FIIs', {})
    dii_info = sh.get('DIIs', {})

    if fii_info.get('change_qoq', 0) > 0.3:
        score += 2
        signals.append(f"FIIs expanding stake by +{fii_info['change_qoq']}% QoQ (Current: {fii_info['latest']}%)")
    elif fii_info.get('change_qoq', 0) < -0.5:
        score -= 2
        signals.append(f"FIIs trimming stake by {fii_info['change_qoq']}% QoQ (Current: {fii_info['latest']}%)")

    if dii_info.get('change_qoq', 0) > 0.3:
        score += 1
        signals.append(f"Domestic funds (DII) accumulating +{dii_info['change_qoq']}% QoQ (Current: {dii_info['latest']}%)")

    verdict = "STRONG ACCUMULATION" if score >= 5 else ("POSSIBLE DISTRIBUTION" if score <= -2 else "NORMAL FLOW")

    return {
        'persona': 'Institutional Delivery Tracker',
        'score': max(-10, min(10, score)),
        'verdict': verdict,
        'signals': signals,
        'deliv_qty': f"{int(m['deliv_qty']):,}",
        'deliv_pct': f"{m['delivery_pct']:.2f}%",
        'deliv_percentile': f"{m['delivery_percentile']:.1f}%"
    }


def evaluate_value_investor(m: dict) -> dict:
    """Persona 3: Fundamental Value Investor (Powered by Screener.in)."""
    score = 0
    signals = []
    funds = m.get('fundamentals', {})

    # Fundamental Ratios from Screener
    pe = funds.get('pe')
    pb = funds.get('pb')
    roce = funds.get('roce')
    roe = funds.get('roe')
    mcap = funds.get('market_cap_cr')
    pros = funds.get('pros', [])
    cons = funds.get('cons', [])

    if mcap:
        signals.append(f"Market Cap: ₹{mcap:,.0f} Cr | P/E: {pe or '-'} | P/B: {pb or '-'}")

    # Capital efficiency (ROCE / ROE)
    if roce and roce >= 18.0:
        score += 3
        signals.append(f"High Return on Capital (ROCE: {roce}%) - Strong economic moat")
    elif roce and roce >= 12.0:
        score += 1
        signals.append(f"Moderate Return on Capital (ROCE: {roce}%)")
    elif roce and roce < 10.0:
        score -= 2
        signals.append(f"Sub-par capital efficiency (ROCE: {roce}%)")

    if roe and roe >= 15.0:
        score += 2
        signals.append(f"Healthy Return on Equity (ROE: {roe}%)")

    # Valuation check
    if pe and pe < 20.0:
        score += 2
        signals.append(f"Attractive valuation multiple (P/E {pe}x)")
    elif pe and pe > 60.0:
        score -= 2
        signals.append(f"Elevated valuation multiple (P/E {pe}x) - Priced to perfection")

    # Drawdown from peak
    if m['pct_from_high'] < -25.0:
        score += 2
        signals.append(f"Margin of safety: Trading at {m['pct_from_high']:.1f}% discount from peak")
    elif m['pct_from_high'] > -4.0:
        score -= 1
        signals.append(f"Trading near all-time peak ({m['pct_from_high']:.1f}% from top)")

    # Screener pros & cons highlights
    if pros:
        top_pro = pros[0]
        signals.append(f"Screener Strength: {top_pro}")
        score += 1

    if cons:
        top_con = cons[0]
        signals.append(f"Screener Red Flag: {top_con}")
        score -= 1

    verdict = "STRONG VALUE ACCUMULATE" if score >= 4 else ("HOLD / WAIT FOR VALUE" if score >= 0 else "OVERVALUED / UNATTRACTIVE")

    return {
        'persona': 'Value Investor (Screener.in)',
        'score': max(-10, min(10, score)),
        'verdict': verdict,
        'signals': signals,
        'pe': pe,
        'roce': roce,
        'roe': roe,
        'mcap_cr': mcap,
        'horizon': "1 to 3 Years"
    }


def evaluate_risk_analyst(m: dict) -> dict:
    """Persona 4: Quantitative Risk & Research Analyst."""
    score = 0
    warnings = []
    observations = []
    funds = m.get('fundamentals', {})
    cons = funds.get('cons', [])

    # Volume Z-score
    z = m['vol_zscore']
    observations.append(f"Volume Z-Score: {z:+.2f}σ vs 20-day distribution")
    if abs(z) > 3.0:
        warnings.append("Statistical volume anomaly (>3σ) - Expect elevated short-term volatility")
        score -= 1
    else:
        score += 1

    # Volatility / ATR
    atr_pct = (m['atr'] / m['close']) * 100
    observations.append(f"Average True Range (ATR): ₹{m['atr']:.2f} ({atr_pct:.2f}% of price)")
    if atr_pct > 3.5:
        warnings.append("Elevated price volatility - Reduce position sizing")
        score -= 2
    else:
        score += 2

    # Screener Red Flags
    if cons:
        for c in cons[:2]:
            warnings.append(f"Fundamental Risk: {c}")
            score -= 1

    # Position sizing
    stop_distance = (1.5 * m['atr'])
    shares_per_100k = int(1000 / stop_distance) if stop_distance > 0 else 0

    verdict = "CONTROLLED RISK REGIME" if score >= 0 else "ELEVATED RISK REGIME"

    return {
        'persona': 'Quantitative Risk Analyst',
        'score': max(-10, min(10, score)),
        'verdict': verdict,
        'z_score': f"{z:+.2f}σ",
        'atr_pct': f"{atr_pct:.2f}%",
        'observations': observations,
        'warnings': warnings,
        'recommended_sizing': f"{shares_per_100k} shares per ₹1,00,000 portfolio (max 1% risk)"
    }


def convene_committee(symbol: str) -> dict:
    """Convene all 4 personas and generate CIO synthesis."""
    df = load_symbol_history(symbol)
    if df.empty:
        return {'error': f"No historical dataset found for {symbol}."}

    m = calculate_quant_metrics(df, symbol)
    if not m:
        return {'error': f"Insufficient data candles for {symbol}."}

    p_momentum = evaluate_momentum_trader(m)
    p_delivery = evaluate_delivery_tracker(m)
    p_value = evaluate_value_investor(m)
    p_risk = evaluate_risk_analyst(m)

    weights = {
        'momentum': 0.30,
        'delivery': 0.30,
        'value': 0.25,
        'risk': 0.15
    }
    composite_score = (
        (p_momentum['score'] * weights['momentum']) +
        (p_delivery['score'] * weights['delivery']) +
        (p_value['score'] * weights['value']) +
        (p_risk['score'] * weights['risk'])
    )

    if composite_score >= 4.0:
        consensus = "STRONG BUY / HIGH CONVICTION"
        action = "Initiate long position with defined invalidation stop"
    elif composite_score >= 1.5:
        consensus = "ACCUMULATE ON PULLBACKS"
        action = "Scale into position on dips towards 20-day SMA"
    elif composite_score >= -1.5:
        consensus = "NEUTRAL / WATCHLIST"
        action = "Hold existing positions; await clearer catalyst confirmation"
    else:
        consensus = "AVOID / TAKE PROFIT"
        action = "Capital preservation recommended; fundamental or distribution headwind"

    return {
        'metrics': m,
        'momentum': p_momentum,
        'delivery': p_delivery,
        'value': p_value,
        'risk': p_risk,
        'composite_score': round(composite_score, 2),
        'consensus': consensus,
        'action': action
    }


def print_committee_report(report: dict):
    """Render a visual terminal output of the committee debate and verdict."""
    if 'error' in report:
        print(f"\n[!] Error: {report['error']}\n")
        return

    m = report['metrics']
    funds = m.get('fundamentals', {})
    p1 = report['momentum']
    p2 = report['delivery']
    p3 = report['value']
    p4 = report['risk']

    company_name = funds.get('company_name', m['symbol'])

    print("\n" + "=" * 85)
    print(f" INSTITUTIONAL INVESTMENT COMMITTEE REPORT: {m['symbol']} ({company_name})")
    print(f" Date: {m['date']} | Close: ₹{m['close']:,.2f} ({m['ret_1d']:+.2f}%) | VWAP: ₹{m['vwap']:,.2f}")
    print("=" * 85)

    # Fundamental & Technical Header
    mcap_str = f"₹{funds['market_cap_cr']:,.0f} Cr" if funds.get('market_cap_cr') else "-"
    pe_str = f"{funds['pe']}x" if funds.get('pe') else "-"
    roce_str = f"{funds['roce']}%" if funds.get('roce') else "-"
    print(f"\n[+] FUNDAMENTAL & TECHNICAL SNAPSHOT:")
    print(f"    • Screener Ratios:  Market Cap: {mcap_str} | P/E: {pe_str} | P/B: {funds.get('pb') or '-'} | ROCE: {roce_str} | ROE: {funds.get('roe') or '-'}%")
    print(f"    • Traded Volume:    {int(m['volume']):,} ({m['vol_spike_ratio']:.2f}x 20D SMA, Z: {m['vol_zscore']:+.2f}σ)")
    print(f"    • Deliverable Qty:  {int(m['deliv_qty']):,} ({m['delivery_pct']:.2f}%, {m['delivery_percentile']:.1f}th percentile)")
    print(f"    • Trend Context:    20D SMA: ₹{m['sma20']:,.2f} | 50D SMA: ₹{m['sma50']:,.2f}")

    # Persona Debates
    print("\n" + "-" * 85)
    print(f" 1. MOMENTUM TRADER (Vote: {p1['score']:+d}/10 | {p1['verdict']})")
    for s in p1['signals']:
        print(f"    ▶ {s}")
    print(f"    ⚡ Setup: Entry: ₹{p1['entry']:,.2f} | SL: ₹{p1['stop_loss']:,.2f} | T1: ₹{p1['target_1']:,.2f} | T2: ₹{p1['target_2']:,.2f} (R:R {p1['rr_ratio']})")

    print("\n" + "-" * 85)
    print(f" 2. INSTITUTIONAL DELIVERY TRACKER (Vote: {p2['score']:+d}/10 | {p2['verdict']})")
    for s in p2['signals']:
        print(f"    ▶ {s}")
    print(f"    📊 Cash Absorption: {p2['deliv_pct']} delivered ({p2['deliv_qty']} shares, {p2['deliv_percentile']} percentile)")

    print("\n" + "-" * 85)
    print(f" 3. VALUE INVESTOR (Powered by Screener.in) (Vote: {p3['score']:+d}/10 | {p3['verdict']})")
    for s in p3['signals']:
        print(f"    ▶ {s}")
    print(f"    ⏳ Recommended Horizon: {p3['horizon']}")

    print("\n" + "-" * 85)
    print(f" 4. QUANTITATIVE RISK ANALYST (Vote: {p4['score']:+d}/10 | {p4['verdict']})")
    for s in p4['observations']:
        print(f"    ▶ {s}")
    for w in p4['warnings']:
        print(f"    ⚠️  {w}")
    print(f"    🛡️  Sizing Guide: {p4['recommended_sizing']}")

    # CIO Final Synthesis
    print("\n" + "=" * 85)
    print(f" CHIEF INVESTMENT OFFICER (CIO) CONSENSUS VERDICT: {report['consensus']}")
    print(f" Composite Committee Score: {report['composite_score']:+.2f} / 10.0")
    print(f" Actionable Guidance:       {report['action']}")
    print("=" * 85 + "\n")


def analyze_top_screened_stocks(top_n: int = 3):
    """Convene the committee on today's top institutional delivery & volume spike candidates."""
    signals_file = os.path.join(DATA_DIR, "institutional_signals.csv")
    if not os.path.exists(signals_file):
        print("[!] No pre-screened institutional signals found. Run delivery_filter.py first.")
        return

    df = pd.read_csv(signals_file)
    if df.empty or 'Symbol' not in df.columns:
        print("[!] Pre-screened file is empty.")
        return

    symbols = df['Symbol'].drop_duplicates().head(top_n).tolist()
    print(f"\nConvening Committee for Top {len(symbols)} Screened Candidates: {', '.join(symbols)}...")
    for sym in symbols:
        rep = convene_committee(sym)
        print_committee_report(rep)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Persona Quantitative & Fundamental Committee (Screener.in + NSE)")
    parser.add_argument("--symbol", "-s", default="MOTHERSON", help="Target stock symbol (default: MOTHERSON)")
    parser.add_argument("--top-screened", action="store_true", help="Convene committee for top recent screened stocks")
    parser.add_argument("--top", type=int, default=3, help="Number of top screened stocks to evaluate")

    args = parser.parse_args()

    if args.top_screened:
        analyze_top_screened_stocks(top_n=args.top)
    else:
        report = convene_committee(args.symbol)
        print_committee_report(report)

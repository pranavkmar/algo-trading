"""
delivery_filter.py - Professional Delivery & Volume Spike Screening Engine

Scans local historical datasets across all NSE Futures & Options (F&O) underlying symbols
to detect institutional accumulation/distribution patterns:
1. High Delivery Percentage (e.g. > 70%)
2. Unusual Volume Spikes (e.g. > 2.0x 20-day moving average)
3. Combined Signals (High Delivery + Massive Volume Spike)
"""

import os
import sys
import glob
import argparse
import pandas as pd
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HISTORICAL_DIR = os.path.join(DATA_DIR, "historical")


def load_local_symbol_data(symbol: str) -> pd.DataFrame:
    """Load local CSV for a specific symbol."""
    file_path = os.path.join(HISTORICAL_DIR, f"{symbol.upper()}.csv")
    if not os.path.exists(file_path):
        return pd.DataFrame()
    try:
        df = pd.read_csv(file_path)
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        return df
    except Exception:
        return pd.DataFrame()


def load_all_local_datasets() -> dict[str, pd.DataFrame]:
    """Load all cached F&O historical CSVs from data/historical/."""
    csv_files = glob.glob(os.path.join(HISTORICAL_DIR, "*.csv"))
    datasets = {}
    for f in csv_files:
        symbol = os.path.splitext(os.path.basename(f))[0]
        try:
            df = pd.read_csv(f)
            if not df.empty and 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
                df = df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)
                datasets[symbol] = df
        except Exception:
            continue
    return datasets


def analyze_symbol(
    df: pd.DataFrame,
    min_delivery: float = 70.0,
    volume_spike_multiplier: float = 2.0,
    window: int = 20,
    min_volume: int = 50000,
    mode: str = "both"
) -> pd.DataFrame:
    """
    Analyze a symbol dataframe to identify high delivery and volume spike trading days.
    
    Modes:
      - 'both': delivery >= min_delivery AND volume >= volume_spike_multiplier * SMA
      - 'delivery': delivery >= min_delivery
      - 'spike': volume >= volume_spike_multiplier * SMA
    """
    if df.empty or len(df) < 5:
        return pd.DataFrame()

    df = df.copy()

    # Ensure numeric columns
    for col in ['TradedQty', 'DeliverableQty', 'DeliveryPercent', 'Close']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Calculate rolling volume average (SMA)
    df['Vol_SMA'] = df['TradedQty'].rolling(window=window, min_periods=max(5, window // 4)).mean()
    df['Vol_Spike_Ratio'] = (df['TradedQty'] / df['Vol_SMA']).round(2)

    # Condition 1: Minimum volume threshold
    cond_vol = df['TradedQty'] >= min_volume

    # Condition 2: Delivery %
    cond_delivery = df['DeliveryPercent'] >= min_delivery

    # Condition 3: Volume Spike
    cond_spike = (df['Vol_Spike_Ratio'] >= volume_spike_multiplier)

    if mode == "both":
        matched = df[cond_vol & cond_delivery & cond_spike].copy()
    elif mode == "delivery":
        matched = df[cond_vol & cond_delivery].copy()
    elif mode == "spike":
        matched = df[cond_vol & cond_spike].copy()
    else:
        matched = df[cond_vol & (cond_delivery | cond_spike)].copy()

    if matched.empty:
        return pd.DataFrame()

    # Select and format output columns
    matched['Date_Str'] = matched['Date'].dt.strftime('%d-%b-%Y')
    return matched


def scan_datasets(
    symbols: list[str] = None,
    min_delivery: float = 70.0,
    volume_spike: float = 2.0,
    window: int = 20,
    min_volume: int = 50000,
    mode: str = "both",
    from_date: str = None,
    to_date: str = None,
    sort_by: str = "date",
    ascending: bool = False,
    limit: int = None
) -> pd.DataFrame:
    """Scan across all or specified symbols and return aggregated results."""
    all_data = load_all_local_datasets()

    if not all_data:
        print("\n[!] No local datasets found in data/historical/.")
        print("    Run 'python data_sync.py' first to download all F&O stock data.\n")
        return pd.DataFrame()

    if symbols:
        target_symbols = [s.upper().strip() for s in symbols if s.upper().strip() in all_data]
        missing = [s for s in symbols if s.upper().strip() not in all_data]
        if missing:
            print(f"[!] Warning: No local data for symbols: {', '.join(missing)}")
    else:
        target_symbols = list(all_data.keys())

    results_list = []
    for sym in target_symbols:
        df = all_data[sym]
        
        # Optional date filtering
        if from_date:
            df = df[df['Date'] >= pd.to_datetime(from_date)]
        if to_date:
            df = df[df['Date'] <= pd.to_datetime(to_date)]

        matched = analyze_symbol(
            df,
            min_delivery=min_delivery,
            volume_spike_multiplier=volume_spike,
            window=window,
            min_volume=min_volume,
            mode=mode
        )
        if not matched.empty:
            results_list.append(matched)

    if not results_list:
        return pd.DataFrame()

    res_df = pd.concat(results_list, ignore_index=True)

    # Sorting
    sort_cols_map = {
        'date': 'Date',
        'spike': 'Vol_Spike_Ratio',
        'delivery': 'DeliveryPercent',
        'volume': 'TradedQty',
        'symbol': 'Symbol'
    }
    target_sort_col = sort_cols_map.get(sort_by.lower(), 'Date')
    res_df = res_df.sort_values(by=target_sort_col, ascending=ascending).reset_index(drop=True)

    if limit and limit > 0:
        res_df = res_df.head(limit)

    return res_df


def format_and_print_results(df: pd.DataFrame, title: str = "Scan Results"):
    """Format and print tabulated results to console."""
    if df.empty:
        print("\n[-] No trading days matched your filter criteria.")
        return

    print(f"\n{'='*95}")
    print(f" {title.upper()} (Found: {len(df)} occurrences)")
    print(f"{'='*95}")

    # Prepare view columns
    view_df = pd.DataFrame()
    view_df['Symbol'] = df['Symbol']
    view_df['Date'] = df['Date_Str']
    view_df['Close (₹)'] = df['Close'].map(lambda x: f"{x:,.2f}" if pd.notnull(x) else "-")
    view_df['Traded Qty'] = df['TradedQty'].map(lambda x: f"{int(x):,}" if pd.notnull(x) else "-")
    view_df['20D Avg Vol'] = df['Vol_SMA'].map(lambda x: f"{int(x):,}" if pd.notnull(x) else "-")
    view_df['Spike (x)'] = df['Vol_Spike_Ratio'].map(lambda x: f"{x:.2f}x" if pd.notnull(x) else "-")
    view_df['Delivery Qty'] = df['DeliverableQty'].map(lambda x: f"{int(x):,}" if pd.notnull(x) else "-")
    view_df['Delivery %'] = df['DeliveryPercent'].map(lambda x: f"{x:.2f}%" if pd.notnull(x) else "-")

    print(view_df.to_string(index=False))
    print(f"{'='*95}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Filter NSE F&O stocks by Delivery Percentage and Volume Spikes."
    )
    parser.add_argument(
        "--symbol", "-s",
        default=None,
        help="Target stock symbol (e.g. MOTHERSON, RELIANCE). Default: all F&O symbols"
    )
    parser.add_argument(
        "--min-delivery", "-d",
        type=float,
        default=70.0,
        help="Minimum delivery percentage (default: 70.0)"
    )
    parser.add_argument(
        "--volume-spike", "-v",
        type=float,
        default=2.0,
        help="Minimum volume spike ratio vs rolling average (e.g. 2.0 = 2x average volume, default: 2.0)"
    )
    parser.add_argument(
        "--window", "-w",
        type=int,
        default=20,
        help="Rolling lookback window for average volume calculation (default: 20 days)"
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["both", "delivery", "spike", "either"],
        default="both",
        help="Filtering mode: 'both' (high delivery AND volume spike), 'delivery' (delivery only), 'spike' (volume spike only), 'either' (either condition)"
    )
    parser.add_argument(
        "--min-volume",
        type=int,
        default=50000,
        help="Minimum traded quantity threshold to filter noise (default: 50,000)"
    )
    parser.add_argument(
        "--from-date",
        default=None,
        help="Filter start date (YYYY-MM-DD or DD-MM-YYYY)"
    )
    parser.add_argument(
        "--to-date",
        default=None,
        help="Filter end date (YYYY-MM-DD or DD-MM-YYYY)"
    )
    parser.add_argument(
        "--sort-by",
        choices=["date", "spike", "delivery", "volume", "symbol"],
        default="date",
        help="Sort results by metric (default: date)"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Limit number of output rows"
    )
    parser.add_argument(
        "--export", "-o",
        default=None,
        help="Optional path to export filtered results as CSV (e.g. data/results.csv)"
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Trigger data sync first to refresh local historical datasets"
    )

    args = parser.parse_args()

    # Optional sync
    if args.sync:
        from data_sync import sync_all_symbols
        sync_all_symbols()

    symbols = [args.symbol] if args.symbol else None

    # Title description
    mode_desc = {
        'both': f"Delivery ≥ {args.min_delivery}% AND Volume Spike ≥ {args.volume_spike}x ({args.window}D SMA)",
        'delivery': f"Delivery ≥ {args.min_delivery}%",
        'spike': f"Volume Spike ≥ {args.volume_spike}x ({args.window}D SMA)",
        'either': f"Delivery ≥ {args.min_delivery}% OR Volume Spike ≥ {args.volume_spike}x"
    }

    sym_desc = args.symbol.upper() if args.symbol else "All F&O Underlying Symbols"
    title = f"{sym_desc} | {mode_desc.get(args.mode, '')}"

    results = scan_datasets(
        symbols=symbols,
        min_delivery=args.min_delivery,
        volume_spike=args.volume_spike,
        window=args.window,
        min_volume=args.min_volume,
        mode=args.mode,
        from_date=args.from_date,
        to_date=args.to_date,
        sort_by=args.sort_by,
        ascending=False,
        limit=args.top
    )

    format_and_print_results(results, title=title)

    if args.export and not results.empty:
        export_path = args.export
        os.makedirs(os.path.dirname(os.path.abspath(export_path)), exist_ok=True)
        results.to_csv(export_path, index=False)
        print(f"[+] Saved results to: {export_path}")


if __name__ == "__main__":
    main()
"""
data_sync.py - Incremental Delta & Historical Ingestion Engine for NSE F&O Datasets

Features:
1. Smart Delta Sync: Only downloads missing trading days using the daily EOD
   Deliverable Bhavcopy (sec_bhavdata_full_ddmmyyyy.csv). Updates all 213 stocks in < 1 second!
2. Historical Backfill: Multi-threaded historical downloader for initial setup or custom ranges.
3. Automated Deduplication: Appends new daily records cleanly without duplicates.
"""

import os
import io
import glob
import json
import time
import logging
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import pandas as pd
from tqdm import tqdm
from nselib import capital_market

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HISTORICAL_DIR = os.path.join(DATA_DIR, "historical")
SYMBOLS_FILE = os.path.join(DATA_DIR, "fno_symbols.json")

os.makedirs(HISTORICAL_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


def create_nse_session() -> requests.Session:
    """Create a requests session initialized with required NSE headers and cookies."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "*/*",
    })
    try:
        session.get("https://nsewebsite-staging.nseindia.com/report-detail/eq_security", timeout=10)
    except Exception as exc:
        logger.debug(f"Initial cookie handshake warning: {exc}")
    return session


def clean_nse_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and standardize raw NSE historical CSV dataframe."""
    if df.empty:
        return df

    clean_cols = {}
    for col in df.columns:
        clean_name = str(col).replace('ï»¿', '').replace('"', '').strip()
        clean_cols[col] = clean_name
    df = df.rename(columns=clean_cols)

    standard_map = {
        'Symbol': 'Symbol',
        'Series': 'Series',
        'Date': 'Date',
        'Prev Close': 'PrevClose',
        'Open Price': 'Open',
        'High Price': 'High',
        'Low Price': 'Low',
        'Last Price': 'Last',
        'Close Price': 'Close',
        'Average Price': 'VWAP',
        'Total Traded Quantity': 'TradedQty',
        'No. of Trades': 'Trades',
        'Deliverable Qty': 'DeliverableQty',
    }
    for c in df.columns:
        if 'Turnover' in c:
            standard_map[c] = 'Turnover'
        elif 'Dly' in c or 'Delivery' in c or '%' in c:
            standard_map[c] = 'DeliveryPercent'

    df = df.rename(columns=standard_map)

    for str_col in ['Symbol', 'Series', 'Date']:
        if str_col in df.columns:
            df[str_col] = df[str_col].astype(str).str.strip()

    num_cols = [
        'PrevClose', 'Open', 'High', 'Low', 'Last', 'Close', 'VWAP',
        'TradedQty', 'Turnover', 'Trades', 'DeliverableQty', 'DeliveryPercent'
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(',', '', regex=False)
                .str.replace('-', '', regex=False)
                .str.strip()
            )
            df[col] = pd.to_numeric(df[col], errors='coerce')

    if 'Series' in df.columns and (df['Series'] == 'EQ').any():
        df = df[df['Series'] == 'EQ'].copy()

    if 'Date' in df.columns:
        df['ParsedDate'] = pd.to_datetime(df['Date'], format='%d-%b-%Y', errors='coerce')
        df = df.dropna(subset=['ParsedDate']).sort_values(by='ParsedDate', ascending=True).reset_index(drop=True)
        df['Date'] = df['ParsedDate'].dt.strftime('%Y-%m-%d')
        df = df.drop(columns=['ParsedDate'])

    return df


def get_fno_symbols_list(force_refresh: bool = False) -> list[dict]:
    """Fetch and cache list of all active F&O underlying symbols."""
    if not force_refresh and os.path.exists(SYMBOLS_FILE):
        try:
            with open(SYMBOLS_FILE, 'r') as f:
                data = json.load(f)
                if data:
                    return data
        except Exception:
            pass

    logger.info("Fetching active F&O underlying stock list from NSE...")
    fno_df = capital_market.fno_equity_list()
    symbols_list = []
    for _, row in fno_df.iterrows():
        sym = str(row['symbol']).strip()
        comp = str(row.get('underlying', sym)).strip()
        symbols_list.append({'symbol': sym, 'company': comp})

    with open(SYMBOLS_FILE, 'w') as f:
        json.dump(symbols_list, f, indent=2)

    logger.info(f"Retrieved and cached {len(symbols_list)} F&O underlying symbols.")
    return symbols_list


def get_latest_cached_date() -> date | None:
    """Scan existing historical CSVs and return the most recent date recorded."""
    sample_files = glob.glob(os.path.join(HISTORICAL_DIR, "*.csv"))[:10]
    if not sample_files:
        return None

    latest_dates = []
    for f in sample_files:
        try:
            df = pd.read_csv(f)
            if not df.empty and 'Date' in df.columns:
                max_d = pd.to_datetime(df['Date']).max()
                if pd.notnull(max_d):
                    latest_dates.append(max_d.date())
        except Exception:
            continue

    if latest_dates:
        return max(latest_dates)
    return None


def sync_daily_bhavcopy_delta(target_date: date, session: requests.Session = None) -> tuple[bool, str]:
    """
    Download a single day's deliverable Bhavcopy and append delta rows across all 213 F&O stocks.
    
    URL: https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv
    """
    if session is None:
        session = create_nse_session()

    date_str_dmy = target_date.strftime("%d%m%Y")
    date_str_iso = target_date.strftime("%Y-%m-%d")
    date_str_display = target_date.strftime("%d-%b-%Y")

    url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date_str_dmy}.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.nseindia.com/"
    }

    try:
        resp = session.get(url, headers=headers, timeout=10)
    except Exception as exc:
        return False, f"Network error fetching Bhavcopy for {date_str_display}: {exc}"

    if resp.status_code == 404 or resp.status_code == 403:
        return False, f"Bhavcopy for {date_str_display} not available (market holiday or not yet published)."

    if resp.status_code != 200 or len(resp.content) < 1000:
        return False, f"Bhavcopy for {date_str_display} returned status {resp.status_code}."

    try:
        bhav_df = pd.read_csv(io.BytesIO(resp.content))
    except Exception as exc:
        return False, f"Failed parsing Bhavcopy CSV: {exc}"

    # Clean columns & strings
    bhav_df.columns = [c.strip() for c in bhav_df.columns]
    bhav_df['SYMBOL'] = bhav_df['SYMBOL'].astype(str).str.strip()
    bhav_df['SERIES'] = bhav_df['SERIES'].astype(str).str.strip()

    # Filter to Equity (EQ) series
    eq_bhav = bhav_df[bhav_df['SERIES'] == 'EQ'].copy()

    fno_symbols = {item['symbol'] for item in get_fno_symbols_list()}
    fno_bhav = eq_bhav[eq_bhav['SYMBOL'].isin(fno_symbols)].copy()

    if fno_bhav.empty:
        return False, f"No F&O equity records found in Bhavcopy for {date_str_display}."

    updated_count = 0
    for _, row in fno_bhav.iterrows():
        sym = row['SYMBOL']
        file_path = os.path.join(HISTORICAL_DIR, f"{sym}.csv")

        # Map to standard record
        try:
            prev_close = float(row.get('PREV_CLOSE', 0))
            open_p = float(row.get('OPEN_PRICE', 0))
            high_p = float(row.get('HIGH_PRICE', 0))
            low_p = float(row.get('LOW_PRICE', 0))
            last_p = float(row.get('LAST_PRICE', 0))
            close_p = float(row.get('CLOSE_PRICE', 0))
            vwap = float(row.get('AVG_PRICE', 0))
            traded_qty = int(str(row.get('TTL_TRD_QNTY', 0)).replace(',', '').strip() or 0)
            turnover = float(str(row.get('TURNOVER_LACS', 0)).replace(',', '').strip() or 0) * 100000.0
            trades = int(str(row.get('NO_OF_TRADES', 0)).replace(',', '').strip() or 0)
            deliv_qty = float(str(row.get('DELIV_QTY', 0)).replace(',', '').replace('-', '').strip() or 0)
            deliv_per = float(str(row.get('DELIV_PER', 0)).replace(',', '').replace('-', '').strip() or 0)
        except Exception:
            continue

        new_row_df = pd.DataFrame([{
            'Symbol': sym,
            'Series': 'EQ',
            'Date': date_str_iso,
            'PrevClose': prev_close,
            'Open': open_p,
            'High': high_p,
            'Low': low_p,
            'Last': last_p,
            'Close': close_p,
            'VWAP': vwap,
            'TradedQty': traded_qty,
            'Turnover': turnover,
            'Trades': trades,
            'DeliverableQty': deliv_qty,
            'DeliveryPercent': deliv_per
        }])

        if os.path.exists(file_path):
            existing_df = pd.read_csv(file_path)
            # Avoid duplicate dates
            if (existing_df['Date'] == date_str_iso).any():
                continue
            combined_df = pd.concat([existing_df, new_row_df], ignore_index=True)
            combined_df.to_csv(file_path, index=False)
            updated_count += 1
        else:
            new_row_df.to_csv(file_path, index=False)
            updated_count += 1

    return True, f"Successfully appended delta for {date_str_display} ({updated_count} symbols updated)."


def fetch_symbol_historical_data(
    symbol: str,
    from_date: str = "01-01-2026",
    to_date: str = "30-09-2026",
    session: requests.Session = None,
    max_retries: int = 3
) -> pd.DataFrame:
    """Fetch historical delivery & price dataframe for a symbol."""
    if session is None:
        session = create_nse_session()

    clean_symbol = symbol.replace("&", "%26").strip().upper()
    url = (
        f"https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData?"
        f"from={from_date}&to={to_date}&symbol={clean_symbol}&type=priceVolumeDeliverable&series=ALL&csv=true"
    )
    headers = {
        "referer": "https://www.nseindia.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, headers=headers, timeout=12)
            if resp.status_code == 200:
                raw_text = resp.text.strip()
                if not raw_text or "No Data Found" in raw_text:
                    return pd.DataFrame()
                raw_df = pd.read_csv(io.StringIO(raw_text))
                return clean_nse_dataframe(raw_df)
            elif resp.status_code == 429:
                time.sleep(2 * attempt)
            else:
                time.sleep(0.5 * attempt)
        except Exception:
            time.sleep(1 * attempt)

    return pd.DataFrame()


def download_and_save_symbol(
    sym_info: dict,
    from_date: str,
    to_date: str,
    session: requests.Session,
    force: bool = False
) -> tuple[str, bool, int]:
    """Download single symbol data and write to data/historical/<SYMBOL>.csv."""
    symbol = sym_info['symbol']
    file_path = os.path.join(HISTORICAL_DIR, f"{symbol}.csv")

    if not force and os.path.exists(file_path):
        try:
            existing_df = pd.read_csv(file_path)
            if not existing_df.empty:
                return symbol, True, len(existing_df)
        except Exception:
            pass

    df = fetch_symbol_historical_data(symbol, from_date=from_date, to_date=to_date, session=session)
    if not df.empty:
        df.to_csv(file_path, index=False)
        return symbol, True, len(df)
    return symbol, False, 0


def full_historical_backfill(
    from_date: str = "01-01-2026",
    to_date: str = "30-09-2026",
    max_workers: int = 6,
    force: bool = False
):
    """Run full historical download across all 213 F&O symbols."""
    symbols = get_fno_symbols_list()
    print(f"\n========================================================")
    print(f" FULL HISTORICAL BACKFILL: {len(symbols)} F&O Symbols")
    print(f" Date Range: {from_date} to {to_date}")
    print(f" Target Directory: {HISTORICAL_DIR}")
    print(f"========================================================\n")

    session = create_nse_session()
    success_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                download_and_save_symbol,
                sym_info,
                from_date,
                to_date,
                session,
                force
            ): sym_info['symbol']
            for sym_info in symbols
        }

        with tqdm(total=len(symbols), desc="Backfilling F&O data", unit="symbol") as pbar:
            for future in as_completed(futures):
                try:
                    _, ok, rows = future.result()
                    if ok and rows > 0:
                        success_count += 1
                except Exception:
                    pass
                finally:
                    pbar.update(1)

    print(f"\n[+] Backfill completed: {success_count}/{len(symbols)} symbols saved.\n")


def smart_sync(
    from_date: str = "01-01-2026",
    to_date: str = "30-09-2026",
    force_full: bool = False
):
    """
    Intelligent sync:
    1. If no local data exists (or force_full requested): Does full backfill.
    2. If local data exists: Identifies missing trading dates between latest cached date
       and today, and downloads ONLY the daily Bhavcopy delta.
    """
    symbols = get_fno_symbols_list()
    existing_files = glob.glob(os.path.join(HISTORICAL_DIR, "*.csv"))

    if force_full or len(existing_files) < (len(symbols) * 0.8):
        full_historical_backfill(from_date=from_date, to_date=to_date, force=force_full)
        return

    latest_date = get_latest_cached_date()
    today = date.today()

    print(f"\n{'='*65}")
    print(f" SMART DELTA SYNC (EOD Deliverable Bhavcopy)")
    print(f" Local Cache: {len(existing_files)} stocks | Latest Date: {latest_date}")
    print(f" Target Date: {today}")
    print(f"{'='*65}\n")

    if latest_date is None:
        full_historical_backfill(from_date=from_date, to_date=to_date)
        return

    if latest_date >= today:
        print(f"[✓] All {len(existing_files)} datasets are already up to date with {latest_date}.")
        print("    No delta updates required!\n")
        return

    # Find missing days
    missing_days = []
    curr = latest_date + timedelta(days=1)
    while curr <= today:
        # Exclude weekends (Saturday=5, Sunday=6)
        if curr.weekday() < 5:
            missing_days.append(curr)
        curr += timedelta(days=1)

    if not missing_days:
        print(f"[✓] All {len(existing_files)} datasets are already up to date with {latest_date}.")
        print("    (No intervening trading days found).\n")
        return

    print(f"[*] Found {len(missing_days)} missing trading day(s): {[d.strftime('%d-%b-%Y') for d in missing_days]}")
    session = create_nse_session()

    for d in missing_days:
        print(f"[*] Fetching deliverable Bhavcopy delta for {d.strftime('%d-%b-%Y')}...")
        ok, msg = sync_daily_bhavcopy_delta(d, session=session)
        if ok:
            print(f"    [+] {msg}")
        else:
            print(f"    [-] {msg}")

    print(f"\n[✓] Smart Delta Sync complete!\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="NSE F&O Data Sync (Smart Incremental Delta & Historical Backfill)")
    parser.add_argument("--delta", action="store_true", help="Run smart incremental delta sync (default)")
    parser.add_argument("--date", default=None, help="Sync single trading day delta (format: DD-MM-YYYY or YYYY-MM-DD)")
    parser.add_argument("--full", action="store_true", help="Force full historical backfill from start date")
    parser.add_argument("--symbol", default=None, help="Download / refresh a specific symbol only")
    parser.add_argument("--from-date", default="01-01-2026", help="Start date for backfill (dd-mm-yyyy)")
    parser.add_argument("--to-date", default="30-09-2026", help="End date for backfill (dd-mm-yyyy)")

    args = parser.parse_args()

    if args.symbol:
        sym = args.symbol.upper().strip()
        print(f"Downloading historical data for {sym}...")
        sess = create_nse_session()
        _, ok, count = download_and_save_symbol({'symbol': sym}, args.from_date, args.to_date, sess, force=True)
        if ok:
            print(f"[+] Successfully saved {count} records to {HISTORICAL_DIR}/{sym}.csv")
        else:
            print(f"[-] Failed to retrieve data for {sym}.")
    elif args.date:
        try:
            if "-" in args.date and len(args.date.split("-")[0]) == 4:
                parsed_d = datetime.strptime(args.date, "%Y-%m-%d").date()
            else:
                parsed_d = datetime.strptime(args.date, "%d-%m-%Y").date()
        except Exception:
            print("[!] Invalid date format. Use DD-MM-YYYY or YYYY-MM-DD.")
            exit(1)
        ok, msg = sync_daily_bhavcopy_delta(parsed_d)
        print(msg)
    elif args.full:
        full_historical_backfill(from_date=args.from_date, to_date=args.to_date, force=True)
    else:
        smart_sync(from_date=args.from_date, to_date=args.to_date, force_full=False)

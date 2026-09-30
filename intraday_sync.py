#!/usr/bin/env python3
"""
intraday_sync.py - 1-Minute Intraday Data Ingestion & AmiBroker Database Engine

Fetches 1-minute OHLCV bars for NSE F&O underlying equities and stores them into
an SQLite database (amibroker.db). Enables nightly automated updates, rapid sub-millisecond
queries for quantitative analysis, and standard AmiBroker ASCII export.

Author: Antigravity AI Team
"""

import os
import sys
import json
import sqlite3
import argparse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import yfinance as yf
from tqdm import tqdm

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DEFAULT_DB_PATH = os.path.join(DATA_DIR, "amibroker.db")
FNO_SYMBOLS_PATH = os.path.join(DATA_DIR, "fno_symbols.json")
EXPORT_DIR = os.path.join(DATA_DIR, "amibroker_export")


def init_database(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Initialize the SQLite database schema for AmiBroker 1-minute intraday bars."""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()

    # Enable Write-Ahead Logging (WAL) for high concurrency and speed
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = NORMAL;")

    # Table for 1-minute OHLCV bars
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bars_1m (
            symbol TEXT NOT NULL,
            datetime TEXT NOT NULL,  -- 'YYYY-MM-DD HH:MM:SS' in IST
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume INTEGER NOT NULL,
            PRIMARY KEY (symbol, datetime)
        );
    """)

    # Fast indices for time-series range queries and symbol lookups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bars_symbol_dt ON bars_1m(symbol, datetime);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bars_dt ON bars_1m(datetime);")

    # Table for sync metadata tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_log (
            symbol TEXT PRIMARY KEY,
            last_synced TEXT,
            bar_count INTEGER,
            earliest_dt TEXT,
            latest_dt TEXT
        );
    """)

    conn.commit()
    return conn


def load_symbols():
    """Load the 213 active NSE F&O underlying symbols."""
    if not os.path.exists(FNO_SYMBOLS_PATH):
        raise FileNotFoundError(f"Symbols file not found: {FNO_SYMBOLS_PATH}")
    with open(FNO_SYMBOLS_PATH, "r") as f:
        data = json.load(f)
    return [item["symbol"] if isinstance(item, dict) else item for item in data]


def fetch_symbol_intraday(symbol: str, period: str = "7d") -> list:
    """
    Fetch 1-minute OHLCV bars for a given symbol using Yahoo Finance.
    Yahoo Finance allows up to 7-8 calendar days per 1m granularity request.
    Continuous nightly runs accumulate full history in amibroker.db without gaps.
    """
    ticker = f"{symbol}.NS"
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval="1m", auto_adjust=False)
        if df.empty or len(df) == 0:
            return []

        # Ensure datetime index is formatted in IST string
        if df.index.tz is not None:
            df.index = df.index.tz_convert("Asia/Kolkata")
        
        rows = []
        for dt, row in df.iterrows():
            dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            o = round(float(row["Open"]), 2)
            h = round(float(row["High"]), 2)
            l = round(float(row["Low"]), 2)
            c = round(float(row["Close"]), 2)
            v = int(row.get("Volume", 0))
            if v > 0 or (o > 0 and c > 0):  # Filter empty zero-volume candles if any
                rows.append((symbol, dt_str, o, h, l, c, v))
        return rows
    except Exception as e:
        # print(f"Error fetching {symbol}: {e}")
        return []


def save_bars_to_db(conn: sqlite3.Connection, symbol: str, rows: list) -> int:
    """Save 1-minute bars to SQLite amibroker.db with idempotent upsert."""
    if not rows:
        return 0

    cursor = conn.cursor()
    cursor.executemany("""
        INSERT OR REPLACE INTO bars_1m (symbol, datetime, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, rows)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT OR REPLACE INTO sync_log (symbol, last_synced, bar_count, earliest_dt, latest_dt)
        SELECT 
            symbol,
            ?,
            COUNT(*),
            MIN(datetime),
            MAX(datetime)
        FROM bars_1m
        WHERE symbol = ?
        GROUP BY symbol;
    """, (now_str, symbol))

    conn.commit()
    return len(rows)


def sync_intraday(symbols: list, db_path: str = DEFAULT_DB_PATH, workers: int = 8, period: str = "7d"):
    """Multi-threaded sync of 1-minute intraday bars into amibroker.db."""
    conn = init_database(db_path)
    total = len(symbols)
    print(f"\n[+] Starting 1-Minute Intraday Ingestion into {os.path.basename(db_path)}")
    print(f"    • Symbols: {total} F&O Underlyings")
    print(f"    • Timeframe: 1-Minute Granularity (Past {period})")
    print(f"    • Workers: {workers} Threads")
    print(f"    • Destination: {db_path}\n")

    results = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_sym = {executor.submit(fetch_symbol_intraday, sym, period): sym for sym in symbols}
        
        with tqdm(total=total, desc="Syncing 1m Bars", unit="sym") as pbar:
            for future in as_completed(future_to_sym):
                sym = future_to_sym[future]
                try:
                    rows = future.result()
                    if rows:
                        count = save_bars_to_db(conn, sym, rows)
                        results[sym] = count
                    else:
                        results[sym] = 0
                except Exception as e:
                    results[sym] = 0
                pbar.update(1)

    successful = [s for s, count in results.items() if count > 0]
    total_bars = sum(results.values())
    print(f"\n[✓] Ingestion Complete!")
    print(f"    • Successfully Synced: {len(successful)}/{total} symbols")
    print(f"    • Total 1-Minute Bars Staged: {total_bars:,}")

    # Print summary of database
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT symbol), COUNT(*), MIN(datetime), MAX(datetime) FROM bars_1m;")
    sym_count, total_count, min_dt, max_dt = cursor.fetchone()
    print(f"    • Total Bars in Database: {total_count:,} across {sym_count} symbols")
    print(f"    • Historical Range in DB: {min_dt} to {max_dt}\n")
    conn.close()


def query_intraday_bars(symbol: str, days: int = 10, db_path: str = DEFAULT_DB_PATH) -> pd.DataFrame:
    """
    Load 1-minute bars from amibroker.db for analysis for the past N trading days.
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}. Run sync first.")

    conn = sqlite3.connect(db_path)
    
    # Identify the last N distinct trading dates for this symbol
    date_query = f"""
        SELECT DISTINCT substr(datetime, 1, 10) as dt
        FROM bars_1m
        WHERE symbol = ?
        ORDER BY dt DESC
        LIMIT ?;
    """
    dates_df = pd.read_sql_query(date_query, conn, params=(symbol, days))
    if dates_df.empty:
        conn.close()
        return pd.DataFrame()

    min_date = dates_df["dt"].min()
    
    # Query all 1-minute bars since the cutoff date
    bars_query = f"""
        SELECT datetime, open, high, low, close, volume
        FROM bars_1m
        WHERE symbol = ? AND datetime >= ?
        ORDER BY datetime ASC;
    """
    df = pd.read_sql_query(bars_query, conn, params=(symbol, f"{min_date} 00:00:00"))
    conn.close()
    
    df["datetime"] = pd.to_datetime(df["datetime"])
    df.set_index("datetime", inplace=True)
    return df


def export_to_amibroker_ascii(symbol: str, output_dir: str = EXPORT_DIR, db_path: str = DEFAULT_DB_PATH):
    """
    Export 1-minute bars from amibroker.db into AmiBroker standard ASCII format:
    TICKER,YYYYMMDD,HHMMSS,Open,High,Low,Close,Volume
    """
    os.makedirs(output_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
        SELECT symbol, datetime, open, high, low, close, volume
        FROM bars_1m
        WHERE symbol = ?
        ORDER BY datetime ASC;
    """
    cursor.execute(query, (symbol,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print(f"[-] No bars found in database for {symbol}")
        return

    out_file = os.path.join(output_dir, f"{symbol}_1m.csv")
    with open(out_file, "w") as f:
        # Standard AmiBroker format header
        f.write("$FORMAT Ticker, Date_YMD, Time, Open, High, Low, Close, Volume\n")
        f.write("$SEPARATOR ,\n")
        f.write("$CONT 1\n")
        f.write("$AUTOADD 1\n")
        f.write("$OVERWRITE 1\n")
        for sym, dt_str, o, h, l, c, v in rows:
            # dt_str format: 'YYYY-MM-DD HH:MM:SS'
            dt_part, tm_part = dt_str.split(" ")
            ymd = dt_part.replace("-", "")
            hms = tm_part.replace(":", "")
            f.write(f"{sym},{ymd},{hms},{o:.2f},{h:.2f},{l:.2f},{c:.2f},{v}\n")

    print(f"[✓] Exported {len(rows):,} 1-minute bars for {symbol} to:")
    print(f"    {out_file}")


def print_database_stats(db_path: str = DEFAULT_DB_PATH):
    """Display high-level statistics of amibroker.db."""
    if not os.path.exists(db_path):
        print(f"[-] Database file does not exist at: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(DISTINCT symbol), COUNT(*), MIN(datetime), MAX(datetime) FROM bars_1m;")
    syms, bars, min_dt, max_dt = cursor.fetchone()

    cursor.execute("""
        SELECT symbol, bar_count, earliest_dt, latest_dt, last_synced
        FROM sync_log
        ORDER BY bar_count DESC
        LIMIT 10;
    """)
    top_records = cursor.fetchall()
    conn.close()

    size_mb = os.path.getsize(db_path) / (1024 * 1024)
    print("\n" + "=" * 75)
    print(f" AMIBROKER DATABASE STATISTICS ({os.path.basename(db_path)})")
    print("=" * 75)
    print(f" • Database File:     {db_path} ({size_mb:.2f} MB)")
    print(f" • Total Symbols:     {syms}")
    print(f" • Total 1m Bars:     {bars:,}")
    print(f" • Earliest Bar:      {min_dt}")
    print(f" • Latest Bar:        {max_dt}")
    print("\n Top 10 Symbols by 1-Minute Bar Count:")
    print(f" {'Symbol':<15} {'Bars':<10} {'Earliest':<20} {'Latest':<20}")
    print(" " + "-" * 70)
    for s, c, edt, ldt, lsync in top_records:
        print(f" {s:<15} {c:<10,} {edt:<20} {ldt:<20}")
    print("=" * 75 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Ingest 1-minute OHLCV bars into amibroker.db for NSE F&O equities."
    )
    parser.add_argument("--symbol", "-s", type=str, help="Single stock symbol (e.g. MOTHERSON, KOTAKBANK)")
    parser.add_argument("--all", action="store_true", help="Sync all 213 F&O underlying equities")
    parser.add_argument("--days", type=int, default=10, help="Days of history to query for analysis (default: 10)")
    parser.add_argument("--query", "-q", type=str, help="Query and print 1-minute bars for a symbol")
    parser.add_argument("--export-amibroker", type=str, help="Export 1m bars for a symbol to AmiBroker ASCII CSV")
    parser.add_argument("--stats", action="store_true", help="Display amibroker.db statistics")
    parser.add_argument("--db", type=str, default=DEFAULT_DB_PATH, help=f"Path to SQLite DB (default: {DEFAULT_DB_PATH})")
    parser.add_argument("--workers", "-w", type=int, default=8, help="Number of concurrent download threads (default: 8)")

    args = parser.parse_args()

    if args.stats:
        print_database_stats(args.db)
        return

    if args.query:
        df = query_intraday_bars(args.query.upper(), days=args.days, db_path=args.db)
        if df.empty:
            print(f"[-] No 1-minute bars found for {args.query.upper()} in {args.db}")
        else:
            print(f"\n[+] 1-Minute Intraday Bars for {args.query.upper()} (Past {args.days} trading days):")
            print(f"    • Total Bars: {len(df):,}")
            print(f"    • Range: {df.index.min()} to {df.index.max()}\n")
            print(df.tail(15))
        return

    if args.export_amibroker:
        export_to_amibroker_ascii(args.export_amibroker.upper(), db_path=args.db)
        return

    # Ingestion flow
    if args.symbol:
        symbols = [args.symbol.upper()]
    else:
        symbols = load_symbols()

    sync_intraday(symbols, db_path=args.db, workers=args.workers)


if __name__ == "__main__":
    main()

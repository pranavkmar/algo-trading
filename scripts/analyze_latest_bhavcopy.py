#!/usr/bin/env python3
"""
analyze_latest_bhavcopy.py - Analyze latest NSE Deliverable Bhavcopy
Computes:
1. Top Delivery Percentage (Equities with Turnover > ₹5 Cr)
2. Top Delivery Percentage in F&O Underlyings
3. Top Deliverable Value / Turnover (Institutional Delivery ₹ Cr)
4. Top Delivery Quantity
5. Volume & Delivery Spikes vs 20-Day Rolling Average
"""

import os
import glob
import json
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BHAVCOPY_PATH = os.path.join(BASE_DIR, "data", "sec_bhavdata_full_06112026.csv")
HISTORICAL_DIR = os.path.join(BASE_DIR, "data", "historical")
FNO_SYMBOLS_PATH = os.path.join(BASE_DIR, "data", "fno_symbols.json")

def load_bhavcopy(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    
    # Filter to EQ series
    df = df[df['SERIES'].astype(str).str.strip() == 'EQ'].copy()
    
    # Clean symbol and dates
    df['SYMBOL'] = df['SYMBOL'].astype(str).str.strip()
    df['DATE'] = df['DATE1'].astype(str).str.strip()
    
    # Numeric conversions
    numeric_cols = [
        'PREV_CLOSE', 'OPEN_PRICE', 'HIGH_PRICE', 'LOW_PRICE', 'LAST_PRICE',
        'CLOSE_PRICE', 'AVG_PRICE', 'TTL_TRD_QNTY', 'TURNOVER_LACS',
        'NO_OF_TRADES', 'DELIV_QTY', 'DELIV_PER'
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(',', '', regex=False)
                .str.replace('-', '', regex=False)
                .str.strip()
            )
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Calculate delivery turnover in Crores
    # TURNOVER_LACS is total turnover in lacs (1 lac = 100,000)
    # Deliverable Turnover (₹ Cr) = (DELIV_QTY * AVG_PRICE) / 10,000,000 or (TURNOVER_LACS * (DELIV_PER / 100)) / 100
    df['Turnover_Cr'] = df['TURNOVER_LACS'] / 100.0
    df['Deliv_Turnover_Cr'] = (df['DELIV_QTY'] * df['AVG_PRICE']) / 10000000.0
    
    # Price change %
    df['Pct_Change'] = ((df['CLOSE_PRICE'] - df['PREV_CLOSE']) / df['PREV_CLOSE']) * 100.0
    
    return df

def get_fno_symbols() -> set:
    if os.path.exists(FNO_SYMBOLS_PATH):
        try:
            with open(FNO_SYMBOLS_PATH, 'r') as f:
                data = json.load(f)
                return {item['symbol'].strip() for item in data}
        except Exception:
            pass
    return set()

def get_20d_historical_stats() -> dict:
    stats = {}
    csv_files = glob.glob(os.path.join(HISTORICAL_DIR, "*.csv"))
    for f in csv_files:
        sym = os.path.splitext(os.path.basename(f))[0]
        try:
            hdf = pd.read_csv(f)
            if len(hdf) >= 20 and 'TradedQty' in hdf.columns:
                # 20 trading days prior to latest
                vol_sma = hdf['TradedQty'].iloc[-21:-1].mean() if len(hdf) > 20 else hdf['TradedQty'].iloc[:-1].mean()
                stats[sym] = vol_sma
        except Exception:
            continue
    return stats

def main():
    df = load_bhavcopy(BHAVCOPY_PATH)
    fno_syms = get_fno_symbols()
    vol_stats = get_20d_historical_stats()
    
    df['Is_FNO'] = df['SYMBOL'].isin(fno_syms)
    df['Vol_SMA_20D'] = df['SYMBOL'].map(vol_stats)
    df['Vol_Spike_Ratio'] = df['TTL_TRD_QNTY'] / df['Vol_SMA_20D']
    
    date_val = df['DATE'].iloc[0] if not df.empty else "Latest"
    print(f"Bhavcopy Date: {date_val} | Total Equities (EQ): {len(df)}")
    
    # 1. Top Delivery % (Min Turnover ₹5 Cr to ensure liquidity)
    liquid_eq = df[df['Turnover_Cr'] >= 5.0].copy()
    top_deliv_pct = liquid_eq.sort_values(by='DELIV_PER', ascending=False).head(20)
    
    print("\n" + "="*80)
    print("TOP 20 HIGH DELIVERY % (EQUITIES with Turnover >= ₹5 Cr)")
    print("="*80)
    cols = ['SYMBOL', 'CLOSE_PRICE', 'Pct_Change', 'DELIV_PER', 'DELIV_QTY', 'Deliv_Turnover_Cr', 'Turnover_Cr', 'Is_FNO']
    print(top_deliv_pct[cols].to_string(index=False))
    
    # 2. Top Delivery % among F&O Underlyings
    fno_df = df[df['Is_FNO']].copy()
    top_fno_deliv = fno_df.sort_values(by='DELIV_PER', ascending=False).head(20)
    print("\n" + "="*80)
    print("TOP 20 HIGH DELIVERY % (F&O UNDERLYING STOCKS)")
    print("="*80)
    fno_cols = ['SYMBOL', 'CLOSE_PRICE', 'Pct_Change', 'DELIV_PER', 'DELIV_QTY', 'Deliv_Turnover_Cr', 'Vol_Spike_Ratio']
    print(top_fno_deliv[fno_cols].to_string(index=False))
    
    # 3. Top Institutional Deliverable Value / Turnover (₹ Crores)
    top_deliv_val = df.sort_values(by='Deliv_Turnover_Cr', ascending=False).head(20)
    print("\n" + "="*80)
    print("TOP 20 INSTITUTIONAL DELIVERY TURNOVER (Highest Deliverable Value in ₹ Cr)")
    print("="*80)
    print(top_deliv_val[cols].to_string(index=False))
    
    # 4. Volume Spikes with High Delivery (Delivery % >= 50% & Volume Spike >= 1.5x)
    spikes = df[(df['DELIV_PER'] >= 50.0) & (df['Vol_Spike_Ratio'] >= 1.5)].copy()
    spikes = spikes.sort_values(by='Vol_Spike_Ratio', ascending=False).head(20)
    print("\n" + "="*80)
    print("HIGH DELIVERY (>=50%) + VOLUME SPIKE (>=1.5x 20D SMA)")
    print("="*80)
    spike_cols = ['SYMBOL', 'CLOSE_PRICE', 'Pct_Change', 'DELIV_PER', 'Vol_Spike_Ratio', 'Deliv_Turnover_Cr', 'TTL_TRD_QNTY']
    print(spikes[spike_cols].to_string(index=False))

if __name__ == "__main__":
    main()

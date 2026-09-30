"""
screener_client.py - Screener.in Fundamental Data Extractor & Local Cache

Fetches institutional-grade fundamental data directly from Screener.in:
- Key Ratios: Market Cap, Stock P/E, Book Value, ROCE, ROE, Dividend Yield
- Quality & Growth: 5-Year Profit CAGR, 3-Year ROE
- Shareholding Pattern: Promoter, FII, DII, Public holdings & QoQ delta
- Screener Strengths & Red Flags (Pros & Cons)
- Local caching to data/fundamentals/<SYMBOL>.json to minimize network lookups
"""

import os
import re
import json
import time
import logging
import requests
import bs4

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
FUNDAMENTALS_DIR = os.path.join(DATA_DIR, "fundamentals")
os.makedirs(FUNDAMENTALS_DIR, exist_ok=True)

logger = logging.getLogger(__name__)


def clean_num(val_str: str) -> float | None:
    """Helper to convert formatted string with commas/percentages to float."""
    if not val_str:
        return None
    cleaned = re.sub(r'[^\d.-]', '', str(val_str).strip())
    try:
        return float(cleaned)
    except Exception:
        return None


def fetch_screener_fundamentals(symbol: str, force_refresh: bool = False) -> dict:
    """
    Fetch comprehensive fundamentals from Screener.in for a given stock symbol.
    Caches results locally in data/fundamentals/<SYMBOL>.json for 24 hours.
    """
    sym = symbol.strip().upper()
    cache_file = os.path.join(FUNDAMENTALS_DIR, f"{sym}.json")

    # Check local cache (fresh if < 24 hours old)
    if not force_refresh and os.path.exists(cache_file):
        try:
            mtime = os.path.getmtime(cache_file)
            if (time.time() - mtime) < 86400:  # 24 hours
                with open(cache_file, "r") as f:
                    data = json.load(f)
                    if data and not data.get("error"):
                        return data
        except Exception:
            pass

    urls_to_try = [
        f"https://www.screener.in/company/{sym}/consolidated/",
        f"https://www.screener.in/company/{sym}/",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.screener.in/"
    }

    resp = None
    for url in urls_to_try:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                resp = r
                break
        except Exception:
            continue

    if resp is None or resp.status_code != 200:
        return {
            "symbol": sym,
            "error": f"Could not retrieve Screener.in page for {sym} (HTTP status: {resp.status_code if resp else 'failed'})"
        }

    soup = bs4.BeautifulSoup(resp.text, "html.parser")

    # 1. Company Name & About
    name_el = soup.find("h1")
    company_name = name_el.text.strip() if name_el else sym
    about_el = soup.select_one(".about p")
    about = about_el.text.strip() if about_el else ""

    # 2. Key Valuation & Profitability Ratios
    ratios_raw = {}
    for li in soup.find_all("li", class_="flex flex-space-between"):
        name_tag = li.find("span", class_="name")
        val_tag = li.find("span", class_="number") or li.find("span", class_="nowrap value")
        if name_tag and val_tag:
            ratios_raw[name_tag.text.strip()] = val_tag.text.strip()

    market_cap_cr = clean_num(ratios_raw.get("Market Cap"))
    current_price = clean_num(ratios_raw.get("Current Price"))
    stock_pe = clean_num(ratios_raw.get("Stock P/E"))
    book_value = clean_num(ratios_raw.get("Book Value"))
    dividend_yield = clean_num(ratios_raw.get("Dividend Yield"))
    roce = clean_num(ratios_raw.get("ROCE"))
    roe = clean_num(ratios_raw.get("ROE"))
    face_value = clean_num(ratios_raw.get("Face Value"))

    pb_ratio = round(current_price / book_value, 2) if (current_price and book_value and book_value > 0) else None

    # 3. Pros and Cons (Strengths & Red Flags)
    pros = [li.text.strip() for li in soup.select(".pros ul li")]
    cons = [li.text.strip() for li in soup.select(".cons ul li")]

    # 4. Shareholding Pattern (Promoter, FII, DII, Public)
    shareholding = {}
    sh_section = soup.find("section", id="shareholding")
    if sh_section:
        for tr in sh_section.find_all("tr"):
            cols = [td.text.strip() for td in tr.find_all(["th", "td"])]
            if len(cols) >= 3:
                label = cols[0].replace("+", "").replace("-", "").strip()
                latest_val = clean_num(cols[-1])
                prev_val = clean_num(cols[-2]) if len(cols) >= 3 else latest_val
                delta = round(latest_val - prev_val, 2) if (latest_val is not None and prev_val is not None) else 0.0

                if any(k in label.lower() for k in ["promoter", "fii", "dii", "public", "government"]):
                    shareholding[label] = {
                        "latest": latest_val,
                        "previous": prev_val,
                        "change_qoq": delta
                    }

    result = {
        "symbol": sym,
        "company_name": company_name,
        "about": about[:300] + ("..." if len(about) > 300 else ""),
        "market_cap_cr": market_cap_cr,
        "current_price": current_price,
        "pe": stock_pe,
        "book_value": book_value,
        "pb": pb_ratio,
        "roce": roce,
        "roe": roe,
        "dividend_yield": dividend_yield,
        "face_value": face_value,
        "pros": pros,
        "cons": cons,
        "shareholding": shareholding,
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    # Save to local cache
    try:
        with open(cache_file, "w") as f:
            json.dump(result, f, indent=2)
    except Exception:
        pass

    return result


if __name__ == "__main__":
    import sys
    test_sym = sys.argv[1] if len(sys.argv) > 1 else "MOTHERSON"
    print(f"Fetching fundamentals for {test_sym} from Screener.in...")
    data = fetch_screener_fundamentals(test_sym, force_refresh=True)
    print(json.dumps(data, indent=2))

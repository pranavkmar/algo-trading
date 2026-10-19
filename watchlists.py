"""Daily candidates and intraday price-level lists; never submits orders."""
import csv
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from openalgo_client import OpenAlgoClient, OpenAlgoError

IST = timezone(timedelta(hours=5, minutes=30))
DATA = Path(__file__).resolve().parent / "data"


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def read_history(directory, session):
    histories, errors = {}, []
    for path in sorted(Path(directory).glob("*.csv")):
        try:
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = {date.fromisoformat(r["Date"][:10]): r for r in csv.DictReader(stream)
                        if date.fromisoformat(r["Date"][:10]) < session and r.get("Series", "EQ") == "EQ"}
            if rows:
                histories[path.stem.upper()] = sorted(rows.items())
        except (ValueError, KeyError, OSError) as exc:
            errors.append(f"{path.stem}: invalid history ({type(exc).__name__})")
    return histories, errors


def load_news(path, session, symbols):
    """Explicit symbol attribution avoids treating a headline as a trade direction."""
    if not Path(path).exists():
        return [], ["News not configured: import dated, sourced items into data/news_watchlist.json"]
    try:
        items = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(items, list):
            raise ValueError("expected a list")
    except (ValueError, OSError):
        return [], ["News input is invalid; expected a JSON array"]
    selected, errors, seen = [], [], set()
    for item in items:
        try:
            published = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
            if published.tzinfo is None:
                raise ValueError("timezone required")
            symbol = item["symbol"].upper().strip()
            title, url = item["headline"].strip(), item["url"].strip()
            category = item.get("category", "news")
            if not title or not url.startswith(("https://", "http://")) or category not in {"news", "results"}:
                raise ValueError("invalid news fields")
            # Include the preceding calendar week to cover weekends and holidays.
            age = (session - published.astimezone(IST).date()).days
            key = (symbol, url)
            if symbol in symbols and 0 <= age <= 7 and key not in seen:
                selected.append({"symbol": symbol, "headline": title, "url": url,
                                 "category": category, "published_at": published.isoformat()})
                seen.add(key)
        except (ValueError, KeyError, TypeError, AttributeError):
            errors.append("Skipped news item with invalid symbol, date, category or source URL")
    return sorted(selected, key=lambda n: n["published_at"], reverse=True), errors


def build_watchlists(history_dir=None, news_path=None, session=None, min_delivery=60,
                     volume_multiplier=1.5, window=20, now=None, client=None, fetch_quotes=False):
    now = now or datetime.now(IST)
    session = session or now.astimezone(IST).date()
    if not 0 <= min_delivery <= 100 or not math.isfinite(volume_multiplier) or volume_multiplier <= 0 or window < 1:
        raise ValueError("Invalid delivery, volume or lookback threshold")
    histories, warnings = read_history(history_dir or DATA / "historical", session)
    reference = max((rows[-1][0] for rows in histories.values()), default=None)
    levels, delivery = {}, []
    for symbol, rows in histories.items():
        day, row = rows[-1]
        # A symbol missing the common latest session must not use an older high/low.
        if day != reference:
            warnings.append(f"{symbol}: missing reference session {reference}; excluded")
            continue
        high, low = number(row.get("High")), number(row.get("Low"))
        if high is not None and low is not None and high >= low > 0:
            levels[symbol] = {"symbol": symbol, "previous_high": high, "previous_low": low,
                              "reference_date": str(day)}
        prior = [number(r.get("TradedQty")) for _, r in rows[-window - 1:-1]]
        volume, percent = number(row.get("TradedQty")), number(row.get("DeliveryPercent"))
        if len(prior) != window or any(v is None or v < 0 for v in prior):
            continue
        average = sum(prior) / window
        if average > 0 and volume is not None and percent is not None:
            ratio = volume / average
            if min_delivery < percent <= 100 and ratio >= volume_multiplier:
                delivery.append({"symbol": symbol, "reference_date": str(day), "delivery_pct": percent,
                                 "volume": volume, "average_volume": average, "volume_ratio": ratio})
    news, news_errors = load_news(news_path or DATA / "news_watchlist.json", session, set(histories))
    warnings.extend(news_errors)
    candidates = sorted({r["symbol"] for r in delivery + news} & levels.keys())
    snapshot = {"session_date": str(session), "reference_date": str(reference) if reference else None,
                "generated_at": now.isoformat(), "thresholds": {"delivery_above": min_delivery,
                "volume_at_least": volume_multiplier, "lookback_sessions": window},
                "daily": {"delivery_volume": sorted(delivery, key=lambda r: r["volume_ratio"], reverse=True),
                          "news_results": news},
                "intraday": {"above_previous_high": [], "below_previous_low": [],
                             "within_range": [], "unavailable": []},
                "candidate_symbols": candidates, "quote_source": "OpenAlgo", "quotes_retrieved_at": None,
                "warnings": warnings}
    if reference is None:
        warnings.append("No completed session data available; run data_sync.py")
    elif (session - reference).days > 4:
        warnings.append("Historical data is old; sync and verify the reference session before trading")
    if not fetch_quotes:
        snapshot["quote_status"] = "not_requested"
        return snapshot
    local = now.astimezone(IST)
    if session != local.date() or local.weekday() >= 5 or not ("09:15" <= local.strftime("%H:%M") < "15:30"):
        snapshot["quote_status"] = "outside_regular_session"
        warnings.append("Intraday lists refresh only during regular weekday market hours; exchange holidays must be verified")
        return snapshot
    if reference is None or (session - reference).days > 4:
        snapshot["quote_status"] = "history_stale"
        return snapshot
    try:
        quotes = (client or OpenAlgoClient()).quotes(candidates)
    except OpenAlgoError as exc:
        snapshot["quote_status"] = "unavailable"
        warnings.append(str(exc))
        snapshot["intraday"]["unavailable"] = candidates
        return snapshot
    snapshot["quote_status"] = "received"
    snapshot["quotes_retrieved_at"] = datetime.now(IST).isoformat()
    warnings.append("Quote time is retrieval time; the broker may return delayed prices. Verify exchange freshness before placing orders")
    received = set()
    for quote in quotes:
        symbol = quote.get("symbol")
        if symbol not in candidates or symbol in received or quote.get("error") or quote.get("exchange", "NSE") != "NSE":
            continue
        price = number((quote.get("data") or {}).get("ltp"))
        if price is None or price <= 0:
            continue
        received.add(symbol)
        row = {**levels[symbol], "ltp": price}
        group = ("above_previous_high" if price > row["previous_high"] else
                 "below_previous_low" if price < row["previous_low"] else "within_range")
        snapshot["intraday"][group].append(row)
    snapshot["intraday"]["unavailable"] = sorted(set(candidates) - received)
    return snapshot


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=date.fromisoformat)
    parser.add_argument("--delivery", type=float, default=60)
    parser.add_argument("--volume", type=float, default=1.5)
    parser.add_argument("--live", action="store_true", help="Fetch OpenAlgo quotes (never place orders)")
    args = parser.parse_args()
    print(json.dumps(build_watchlists(session=args.session, min_delivery=args.delivery,
                                     volume_multiplier=args.volume, fetch_quotes=args.live), indent=2))

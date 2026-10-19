"""Import RSS/Atom feeds explicitly mapped to NSE symbols, preserving source and dates."""
import argparse
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

from watchlists import DATA, IST


def parse_feed(content, symbol, category="news"):
    root = ET.fromstring(content)
    records = []
    atom = "{http://www.w3.org/2005/Atom}"
    entries = root.findall("./channel/item") + root.findall(f"{atom}entry")
    for entry in entries:
        title = entry.findtext("title") or entry.findtext(f"{atom}title")
        link = entry.findtext("link")
        if not link:
            for child in entry.findall(f"{atom}link"):
                if child.get("rel", "alternate") == "alternate":
                    link = child.get("href")
                    break
        stamp = (entry.findtext("pubDate") or entry.findtext(f"{atom}published")
                 or entry.findtext(f"{atom}updated"))
        try:
            if not stamp:
                continue
            try:
                published = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            except ValueError:
                published = parsedate_to_datetime(stamp)
            if not title or not link or not link.startswith(("http://", "https://")) or published.tzinfo is None:
                continue
            records.append({"symbol": symbol.upper(), "headline": title.strip(), "url": link,
                            "category": category, "published_at": published.isoformat()})
        except (ValueError, TypeError):
            continue
    return records


def import_feeds(config_path, output=DATA / "news_watchlist.json"):
    sources = json.loads(Path(config_path).read_text(encoding="utf-8"))
    output = Path(output)
    existing = json.loads(output.read_text(encoding="utf-8")) if output.exists() else []
    merged = {(r["symbol"], r["url"]): r for r in existing}
    errors, imported = [], 0
    for source in sources:
        try:
            if source.get("category", "news") not in {"news", "results"}:
                raise ValueError("invalid category")
            response = requests.get(source["url"], timeout=(3, 15))
            response.raise_for_status()
            for row in parse_feed(response.content, source["symbol"], source.get("category", "news")):
                merged[(row["symbol"], row["url"])] = row
                imported += 1
        except (requests.RequestException, ET.ParseError, KeyError, ValueError):
            errors.append(f"Feed unavailable or invalid for {source.get('symbol', 'unknown symbol')}")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement prevents a web request from reading a half-written news file.
    fd, temporary = tempfile.mkstemp(dir=output.parent, suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(list(merged.values()), stream, indent=2)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"imported": imported, "errors": errors, "updated_at": datetime.now(IST).isoformat()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="JSON array of {symbol, url, category}; each feed must be company-specific")
    result = import_feeds(parser.parse_args().config)
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["errors"] else 0)

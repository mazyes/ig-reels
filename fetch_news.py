"""Print fresh AI news stories as JSON, skipping ones already posted.

Usage: python fetch_news.py [--hours 36]
Stdlib only.
"""
import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

FEEDS = {
    "TechCrunch": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "The Verge": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "VentureBeat": "https://venturebeat.com/category/ai/feed/",
    "OpenAI": "https://openai.com/news/rss.xml",
    "Google": "https://blog.google/technology/ai/rss/",
}
HERE = Path(__file__).parent
ATOM = "{http://www.w3.org/2005/Atom}"


def parse_date(text):
    if not text:
        return None
    try:
        d = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def clean(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()[:600]


def parse_feed(source, xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = root.findall(".//item") or root.findall(f".//{ATOM}entry")
    for it in items:
        def get(*tags):
            for t in tags:
                el = it.find(t)
                if el is not None:
                    return el.get("href") or (el.text or "")
            return ""
        yield {
            "source": source,
            "title": clean(get("title", f"{ATOM}title")),
            "link": get("link", f"{ATOM}link").strip(),
            "summary": clean(get("description", f"{ATOM}summary", f"{ATOM}content")),
            "published": parse_date(get("pubDate", f"{ATOM}published", f"{ATOM}updated")),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=36)
    args = ap.parse_args()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    posted_file = HERE / "posted.json"
    posted = {p["link"] for p in json.loads(posted_file.read_text("utf-8"))} if posted_file.exists() else set()

    stories = []
    for source, url in FEEDS.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ig-content-bot/1.0"})
            data = urllib.request.urlopen(req, timeout=20).read()
            stories += [s for s in parse_feed(source, data)
                        if s["link"] and s["link"] not in posted and s["published"] and s["published"] >= cutoff]
        except Exception as e:  # one dead feed must not kill the run
            print(f"warn: {source}: {e}", file=sys.stderr)

    stories.sort(key=lambda s: s["published"], reverse=True)
    for s in stories:
        s["published"] = s["published"].isoformat()
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252
    json.dump(stories, sys.stdout, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()

"""Log every alert to a Notion database.

Requires NOTION_TOKEN + NOTION_DB_ID in .env. Skips silently if missing.

Expected DB schema (create in Notion, copy DB ID from URL):
  Title       (title)        — alert label
  Hex         (rich_text)
  Callsign    (rich_text)
  Registration(rich_text)
  Type        (rich_text)
  Owner       (rich_text)
  Country     (rich_text)
  Route       (rich_text)
  Position    (rich_text)
  Altitude    (rich_text)
  Speed       (rich_text)
  Squawk      (rich_text)
  Category    (select)
  Macro Tag   (select)
  Photo       (url)
  Globe URL   (url)
  Timestamp   (date)

You can omit any of the optional properties — the logger only sets ones
that exist in your DB (best-effort: it sends a generous payload, Notion
will ignore properties not in the schema if you use type-safe helpers).
This script writes ALL listed properties; if your DB lacks one, Notion
returns 400. Create the full schema for cleanest behaviour.
"""
import os
from datetime import datetime, timezone

import requests

from config import ROOT
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_DB_ID = os.getenv("NOTION_DB_ID", "")
NOTION_VERSION = "2022-06-28"
NOTION_API = "https://api.notion.com/v1"


def _rt(text):
    return {"rich_text": [{"text": {"content": (text or "")[:1900]}}]}


def _title(text):
    return {"title": [{"text": {"content": (text or "")[:1900]}}]}


def _select(name):
    if not name:
        return {"select": None}
    return {"select": {"name": name[:100]}}


def _url(u):
    if not u:
        return {"url": None}
    return {"url": u}


def log_alert(summary, macro_tag):
    if not NOTION_TOKEN or not NOTION_DB_ID:
        return False

    globe_url = f"https://globe.airplanes.live/?icao={summary['hex'].lower()}"

    owner_str = summary["owner"]
    if summary["owner"] != "Unknown" and not summary.get("owner_verified"):
        owner_str = f"{summary['owner']} (unverified)"

    props = {
        "Title":        _title(summary["label"]),
        "Hex":          _rt(summary["hex"]),
        "Callsign":     _rt(summary["callsign"]),
        "Registration": _rt(summary["registration"]),
        "Type":         _rt(summary["type"]),
        "Owner":        _rt(owner_str),
        "Country":      _rt(summary.get("owner_country") or ""),
        "Route":        _rt(summary.get("route") or ""),
        "Position":     _rt(summary["position"]),
        "Altitude":     _rt(summary["altitude"]),
        "Speed":        _rt(summary["speed"]),
        "Squawk":       _rt(summary["squawk"]),
        "Category":     _select(summary.get("category")),
        "Macro Tag":    _select(macro_tag),
        "Photo":        _url(summary.get("photo_url")),
        "Globe URL":    _url(globe_url),
        "Timestamp":    {"date": {"start": datetime.now(timezone.utc).isoformat()}},
    }

    payload = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": props,
    }

    try:
        r = requests.post(
            f"{NOTION_API}/pages",
            headers={
                "Authorization": f"Bearer {NOTION_TOKEN}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        if not r.ok:
            print(f"[notion] {r.status_code}: {r.text[:300]}")
            return False
        return True
    except Exception as e:
        print(f"[notion] exception: {e}")
        return False

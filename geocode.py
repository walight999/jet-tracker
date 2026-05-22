"""Coarse reverse-geocoding via OpenStreetMap Nominatim.

Lat/lon → country / sea name. Cached aggressively (1° × 1° grid = ~110km
cells) to stay well under Nominatim's 1 req/sec public policy.
"""
import json
import sqlite3
import time
from datetime import datetime, timezone

import requests

from config import DATA_DIR

CACHE_DB = DATA_DIR / "geocode_cache.sqlite"
USER_AGENT = "jet-tracker/0.1 (personal; reverse geocode for flight alerts)"
TTL_DAYS = 90

_last_call = [0.0]
_MIN_GAP = 1.1


def _conn():
    return sqlite3.connect(CACHE_DB)


def init():
    with _conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS geocode (
            cell TEXT PRIMARY KEY,
            place TEXT,
            fetched_ts INTEGER NOT NULL
        )""")


def _throttle():
    elapsed = time.time() - _last_call[0]
    if elapsed < _MIN_GAP:
        time.sleep(_MIN_GAP - elapsed)
    _last_call[0] = time.time()


def _grid_cell(lat, lon):
    return f"{round(lat):.0f},{round(lon):.0f}"


def _cached(cell):
    cutoff = int((datetime.now(timezone.utc).timestamp())) - TTL_DAYS * 86400
    with _conn() as c:
        row = c.execute(
            "SELECT place FROM geocode WHERE cell=? AND fetched_ts>=?",
            (cell, cutoff),
        ).fetchone()
    if row:
        return row[0] or None
    return "MISS"


def _save(cell, place):
    ts = int(datetime.now(timezone.utc).timestamp())
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO geocode (cell, place, fetched_ts) VALUES (?, ?, ?)",
            (cell, place, ts),
        )


def reverse(lat, lon):
    """Return coarse place name (country, sea, region) or None."""
    if lat is None or lon is None:
        return None
    cell = _grid_cell(lat, lon)
    cached = _cached(cell)
    if cached != "MISS":
        return cached

    _throttle()
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 5,
                    "accept-language": "en"},
            headers={"User-Agent": USER_AGENT},
            timeout=12,
        )
        if not r.ok:
            _save(cell, None)
            return None
        data = r.json()
        addr = data.get("address", {})
        place = (
            addr.get("country")
            or addr.get("state")
            or addr.get("region")
            or addr.get("ocean")
            or addr.get("sea")
            or addr.get("body_of_water")
        )
        if not place:
            display = data.get("display_name", "")
            place = display.split(",")[0].strip() if display else None
        _save(cell, place)
        return place
    except Exception as e:
        print(f"[geocode] failed for {lat},{lon}: {e}")
        return None

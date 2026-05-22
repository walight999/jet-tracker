"""Fetch position history (trace) from globe.airplanes.live.

The tar1090 backend at globe.airplanes.live exposes per-aircraft trace
JSON files publicly. From the trace we can derive:
- Where the flight started (first point's lat/lon + altitude)
- Where it currently is or landed (last point)

This fills the gap for aircraft not covered by adsbdb's scheduled-route
database (state aircraft, private jets, celebrities, military ops).
"""
import json
import sqlite3
import time
from datetime import datetime, timezone

import requests

from config import DATA_DIR

CACHE_DB = DATA_DIR / "trace_cache.sqlite"
USER_AGENT = "Mozilla/5.0 (jet-tracker/0.1 personal)"
REFERER = "https://globe.airplanes.live/"
TTL_SECONDS = 1800  # 30 min — origin point is stable, current pos comes from live feed

_last_call = [0.0]
_MIN_GAP = 1.5


def _conn():
    return sqlite3.connect(CACHE_DB)


def init():
    with _conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS trace (
            hex TEXT PRIMARY KEY,
            origin_lat REAL,
            origin_lon REAL,
            origin_alt INTEGER,
            current_lat REAL,
            current_lon REAL,
            current_alt INTEGER,
            duration_secs INTEGER,
            point_count INTEGER,
            fetched_ts INTEGER NOT NULL
        )""")


def _throttle():
    elapsed = time.time() - _last_call[0]
    if elapsed < _MIN_GAP:
        time.sleep(_MIN_GAP - elapsed)
    _last_call[0] = time.time()


def _alt_int(alt):
    if alt is None:
        return None
    if isinstance(alt, str) and alt.lower() == "ground":
        return 0
    try:
        return int(alt)
    except (ValueError, TypeError):
        return None


def fetch(hex_code):
    """Return dict of derived trace summary, or None on failure.

    Cached in sqlite for TTL_SECONDS.
    Fields: origin_lat/lon/alt, current_lat/lon/alt, duration_secs, point_count
    """
    if not hex_code or len(hex_code) < 2:
        return None
    hex_l = hex_code.lower()
    cutoff = int(time.time()) - TTL_SECONDS

    with _conn() as c:
        row = c.execute(
            "SELECT origin_lat, origin_lon, origin_alt, current_lat, current_lon, current_alt, duration_secs, point_count FROM trace WHERE hex=? AND fetched_ts>=?",
            (hex_l, cutoff),
        ).fetchone()
    if row:
        return {
            "origin_lat": row[0],
            "origin_lon": row[1],
            "origin_alt": row[2],
            "current_lat": row[3],
            "current_lon": row[4],
            "current_alt": row[5],
            "duration_secs": row[6],
            "point_count": row[7],
        }

    _throttle()
    last2 = hex_l[-2:]
    url = f"https://globe.airplanes.live/data/traces/{last2}/trace_full_{hex_l}.json"
    try:
        r = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Referer": REFERER},
            timeout=20,
        )
        if not r.ok:
            return None
        data = r.json()
    except Exception as e:
        print(f"[trace] {hex_code} failed: {e}")
        return None

    points = data.get("trace") or []
    if not points:
        return None

    first = points[0]
    last = points[-1]
    # Each point: [time_offset, lat, lon, altitude, gs, track, flags, vert_rate, ...]
    summary = {
        "origin_lat": first[1],
        "origin_lon": first[2],
        "origin_alt": _alt_int(first[3]),
        "current_lat": last[1],
        "current_lon": last[2],
        "current_alt": _alt_int(last[3]),
        "duration_secs": int(last[0] - first[0]) if len(last) > 0 and len(first) > 0 else None,
        "point_count": len(points),
    }

    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO trace (hex, origin_lat, origin_lon, origin_alt, current_lat, current_lon, current_alt, duration_secs, point_count, fetched_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                hex_l,
                summary["origin_lat"],
                summary["origin_lon"],
                summary["origin_alt"],
                summary["current_lat"],
                summary["current_lon"],
                summary["current_alt"],
                summary["duration_secs"],
                summary["point_count"],
                int(time.time()),
            ),
        )
    return summary

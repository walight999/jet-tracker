"""adsbdb.com client — enrich aircraft and callsign data.

Free public API, no auth. Rate limit ~60 req/min — we throttle to be safe
and cache aggressively (aircraft data is static, route data changes slowly).
"""
import json
import sqlite3
import time
from datetime import datetime, timezone

import requests

from config import DATA_DIR

ADSBDB_BASE = "https://api.adsbdb.com/v0"
USER_AGENT = "jet-tracker/0.1 (personal use)"

CACHE_DB = DATA_DIR / "adsbdb_cache.sqlite"
AIRCRAFT_TTL_DAYS = 30
CALLSIGN_TTL_DAYS = 7

_last_call = [0.0]
_MIN_GAP = 1.05


def _throttle():
    elapsed = time.time() - _last_call[0]
    if elapsed < _MIN_GAP:
        time.sleep(_MIN_GAP - elapsed)
    _last_call[0] = time.time()


def _conn():
    return sqlite3.connect(CACHE_DB)


def init():
    with _conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS aircraft (
            hex TEXT PRIMARY KEY,
            payload TEXT,
            fetched_ts INTEGER NOT NULL
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS callsign (
            callsign TEXT PRIMARY KEY,
            payload TEXT,
            fetched_ts INTEGER NOT NULL
        )""")


def _now_ts():
    return int(datetime.now(timezone.utc).timestamp())


_TABLE_KEY = {"aircraft": "hex", "callsign": "callsign"}


def _get_cached(table, key, ttl_days):
    key_col = _TABLE_KEY[table]
    cutoff = _now_ts() - ttl_days * 86400
    with _conn() as c:
        row = c.execute(
            f"SELECT payload FROM {table} WHERE {key_col}=? AND fetched_ts>=?",
            (key, cutoff),
        ).fetchone()
    if row:
        try:
            return json.loads(row[0]) if row[0] else None
        except Exception:
            return None
    return "MISS"


def _set_cached(table, key, payload):
    key_col = _TABLE_KEY[table]
    with _conn() as c:
        c.execute(
            f"INSERT OR REPLACE INTO {table} ({key_col}, payload, fetched_ts) VALUES (?, ?, ?)",
            (key, json.dumps(payload) if payload is not None else None, _now_ts()),
        )


def _fetch(path):
    _throttle()
    url = f"{ADSBDB_BASE}{path}"
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        if r.status_code == 404:
            return None
        if not r.ok:
            print(f"[adsbdb] {path} -> {r.status_code}")
            return None
        data = r.json()
        resp = data.get("response")
        if isinstance(resp, str):
            # e.g. "unknown callsign"
            return None
        return resp
    except Exception as e:
        print(f"[adsbdb] {path} failed: {e}")
        return None


def get_aircraft(hex_code):
    """Returns aircraft dict (owner, type, country, registration, photo) or None."""
    if not hex_code:
        return None
    key = hex_code.upper()
    cached = _get_cached("aircraft", key, AIRCRAFT_TTL_DAYS)
    if cached != "MISS":
        return cached
    resp = _fetch(f"/aircraft/{hex_code.lower()}")
    payload = resp.get("aircraft") if resp else None
    _set_cached("aircraft", key, payload)
    return payload


def get_route(callsign):
    """Returns flightroute dict (airline, origin, destination) or None."""
    if not callsign:
        return None
    cs = callsign.strip().upper()
    if not cs:
        return None
    cached = _get_cached("callsign", cs, CALLSIGN_TTL_DAYS)
    if cached != "MISS":
        return cached
    resp = _fetch(f"/callsign/{cs}")
    payload = resp.get("flightroute") if resp else None
    _set_cached("callsign", cs, payload)
    return payload

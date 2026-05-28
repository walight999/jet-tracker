import sqlite3
from datetime import datetime, timedelta, timezone
from config import DB_PATH, ALERT_COOLDOWN_HOURS, ALERT_COOLDOWN_MIN


def _conn():
    return sqlite3.connect(DB_PATH)


def init():
    with _conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            hex TEXT NOT NULL,
            callsign TEXT,
            ts INTEGER NOT NULL,
            label TEXT,
            PRIMARY KEY (hex, ts)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_hex_ts ON alerts(hex, ts DESC)")
        c.execute("""
        CREATE TABLE IF NOT EXISTS aircraft_state (
            hex TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            since_ts INTEGER NOT NULL,
            last_seen_ts INTEGER NOT NULL,
            last_lat REAL,
            last_lon REAL,
            last_alt INTEGER,
            last_callsign TEXT
        )""")


def get_state(hex_code):
    with _conn() as c:
        row = c.execute(
            "SELECT state, since_ts, last_seen_ts, last_lat, last_lon, last_alt, last_callsign FROM aircraft_state WHERE hex=?",
            (hex_code.upper(),),
        ).fetchone()
    if not row:
        return None
    return {
        "state": row[0],
        "since_ts": row[1],
        "last_seen_ts": row[2],
        "last_lat": row[3],
        "last_lon": row[4],
        "last_alt": row[5],
        "last_callsign": row[6],
    }


def set_state(hex_code, state, ac=None):
    ts = int(datetime.now(timezone.utc).timestamp())
    lat = lon = alt = None
    cs = None
    if ac:
        lat = ac.get("lat")
        lon = ac.get("lon")
        alt_raw = ac.get("alt_baro")
        if isinstance(alt_raw, (int, float)):
            alt = int(alt_raw)
        elif isinstance(alt_raw, str) and alt_raw.lower() == "ground":
            alt = 0
        cs = (ac.get("flight") or "").strip() or None

    prev = get_state(hex_code)
    if prev and prev["state"] == state:
        with _conn() as c:
            c.execute(
                "UPDATE aircraft_state SET last_seen_ts=?, last_lat=COALESCE(?, last_lat), last_lon=COALESCE(?, last_lon), last_alt=COALESCE(?, last_alt), last_callsign=COALESCE(?, last_callsign) WHERE hex=?",
                (ts, lat, lon, alt, cs, hex_code.upper()),
            )
    else:
        with _conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO aircraft_state (hex, state, since_ts, last_seen_ts, last_lat, last_lon, last_alt, last_callsign) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (hex_code.upper(), state, ts, ts, lat, lon, alt, cs),
            )


def recently_alerted(hex_code):
    minutes = ALERT_COOLDOWN_MIN if ALERT_COOLDOWN_MIN else ALERT_COOLDOWN_HOURS * 60
    cutoff = int((datetime.now(timezone.utc) - timedelta(minutes=minutes)).timestamp())
    with _conn() as c:
        cur = c.execute(
            "SELECT 1 FROM alerts WHERE hex=? AND ts>=? LIMIT 1",
            (hex_code.upper(), cutoff),
        )
        return cur.fetchone() is not None


def recent_alert_count(window_minutes=60):
    cutoff = int((datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).timestamp())
    with _conn() as c:
        cur = c.execute("SELECT COUNT(*) FROM alerts WHERE ts >= ?", (cutoff,))
        return cur.fetchone()[0]


def recent_event_count(window_minutes=60):
    """Count all qualifying events (both Telegram-fired alerts AND digest-queued)
    in the last window. cluster_factor uses this — the previous source
    (recent_alert_count) only counted Telegram-fired alerts, which created a
    chicken-and-egg deadlock: cluster can't grow without Telegram alerts, but
    score can't reach Telegram threshold without cluster. digest_queue holds
    everything that passes the watchlist filter, so it is the correct base.
    """
    cutoff = int((datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).timestamp())
    with _conn() as c:
        a = c.execute("SELECT COUNT(*) FROM alerts WHERE ts >= ?", (cutoff,)).fetchone()[0]
        # digest_queue table is created lazily by digest.init() — guard against
        # the table-missing case (first ever run before digest.init ran).
        try:
            d = c.execute("SELECT COUNT(*) FROM digest_queue WHERE ts >= ?", (cutoff,)).fetchone()[0]
        except Exception:
            d = 0
    return a + d


def mark_alerted(hex_code, callsign, label):
    with _conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO alerts (hex, callsign, ts, label) VALUES (?, ?, ?, ?)",
            (hex_code.upper(), callsign, int(datetime.now(timezone.utc).timestamp()), label),
        )

"""Digest queue — Low/Medium impact events accumulate here instead of
push-spamming Telegram. A sender will read this table and emit a
periodic summary in Phase 1B; v1 just persists.
"""
import json
import sqlite3
from datetime import datetime, timezone

from config import DB_PATH


def _conn():
    return sqlite3.connect(DB_PATH)


def init():
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS digest_queue (
                ts INTEGER NOT NULL,
                hex TEXT NOT NULL,
                level TEXT NOT NULL,
                score INTEGER NOT NULL,
                label TEXT,
                phase TEXT,
                category TEXT,
                market_relevance TEXT,
                payload TEXT
            )
            """
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_digest_ts ON digest_queue(ts)")


def enqueue(summary, scoring_result):
    ts = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "components": scoring_result["components"],
        "callsign": summary.get("callsign"),
        "type": summary.get("type"),
        "owner": summary.get("owner"),
        "route": summary.get("route"),
        "started_over": summary.get("started_over"),
        "currently_over": summary.get("currently_over"),
        "why": summary.get("why_it_matters"),
        "data_confidence": summary.get("data_confidence"),
    }
    with _conn() as c:
        c.execute(
            "INSERT INTO digest_queue (ts, hex, level, score, label, phase, category, market_relevance, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                summary.get("hex"),
                scoring_result["level"],
                scoring_result["score"],
                summary.get("label"),
                summary.get("phase_label", ""),
                summary.get("category"),
                summary.get("market_relevance"),
                json.dumps(payload, ensure_ascii=False),
            ),
        )

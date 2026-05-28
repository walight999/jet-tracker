"""Daily digest sender — Phase 1B per digest.py docstring.

Reads digest_queue for the last LOOKBACK_HOURS (default 24) and pushes a
single Telegram summary so the user has a daily heartbeat even when no
event crosses PUSH_MIN_SCORE.

Behaviour:
  - One Telegram message per run.
  - Always sends (including a "quiet 24h" line if zero events) so the user
    can distinguish "tracker is silent because nothing happened" from
    "tracker is silent because it died."
  - No state mutation — purely a read + send. Re-runs are idempotent up to
    the LOOKBACK window.

Wire via .github/workflows/digest_daily.yml — restore the same data cache
poll.yml uses, then `python digest_send.py`.
"""
import json
import sqlite3
import sys
import traceback
from collections import Counter
from datetime import datetime, timezone, timedelta

import config
import alert


LOOKBACK_HOURS = 24
TOP_N = 5
LEVEL_ORDER = ["Critical", "High", "Medium", "Low"]
LEVEL_EMOJI = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "⚪"}


def _conn():
    return sqlite3.connect(config.DB_PATH)


def _fetch_recent(hours: int):
    cutoff = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp())
    with _conn() as c:
        try:
            rows = c.execute(
                """SELECT ts, hex, level, score, label, phase, category, market_relevance, payload
                   FROM digest_queue WHERE ts >= ?
                   ORDER BY score DESC, ts DESC""",
                (cutoff,),
            ).fetchall()
        except sqlite3.OperationalError:
            # digest_queue table not yet created — first-ever digest run before any poll.
            return []
    return rows


def _format_event(row):
    ts, hex_, level, score, label, phase, category, mr, payload = row
    icon = LEVEL_EMOJI.get(level, "·")
    label_clean = (label or "Unknown")[:60]
    phase_part = f" [{phase}]" if phase else ""
    cat_part = f" / {category}" if category else ""
    return f"  {icon} {score}/9 {label_clean}{phase_part}{cat_part}"


def build_digest_message(rows, lookback_hours: int):
    when = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=7)))
    when_str = when.strftime("%Y-%m-%d %H:%M ICT")

    if not rows:
        return (
            f"📋 jet-tracker daily digest — {when_str}\n"
            f"\n"
            f"Quiet {lookback_hours}h — 0 qualifying events logged.\n"
            f"Tracker is alive; nothing on the watchlist transitioned in this window."
        )

    by_level = Counter(r[2] for r in rows)
    level_summary = " · ".join(
        f"{LEVEL_EMOJI.get(lvl,'·')} {lvl}={by_level[lvl]}"
        for lvl in LEVEL_ORDER if by_level[lvl]
    )

    top = rows[:TOP_N]
    top_lines = "\n".join(_format_event(r) for r in top)

    return (
        f"📋 jet-tracker daily digest — {when_str}\n"
        f"\n"
        f"Last {lookback_hours}h: {len(rows)} events logged\n"
        f"{level_summary}\n"
        f"\n"
        f"Top {len(top)} by score:\n"
        f"{top_lines}\n"
        f"\n"
        f"All events <{config.PUSH_MIN_SCORE}/9 stayed in the digest queue (no per-event push)."
    )


def main():
    rows = _fetch_recent(LOOKBACK_HOURS)
    msg = build_digest_message(rows, LOOKBACK_HOURS)
    sent = alert.send_telegram(msg)
    print(f"[digest-send] events={len(rows)} tg={'ok' if sent else 'fail'}")
    return 0 if sent else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)

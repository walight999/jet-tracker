import os
import sys
from pathlib import Path
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

AIRPLANES_LIVE_BASE = "https://api.airplanes.live/v2"

POLL_INTERVAL_MIN = int(os.getenv("POLL_INTERVAL_MIN", "5"))
ALERT_COOLDOWN_HOURS = int(os.getenv("ALERT_COOLDOWN_HOURS", "6"))
# v0.9 Strategic Impact Alert System: dedup per aircraft is now per-minute (45-60min)
# per the v2 design brief. Falls back to ALERT_COOLDOWN_HOURS * 60 if not set.
ALERT_COOLDOWN_MIN = int(os.getenv("ALERT_COOLDOWN_MIN", "45"))
# Minimum impact score that triggers a push. Scores below this go to digest queue.
PUSH_MIN_SCORE = int(os.getenv("PUSH_MIN_SCORE", "6"))

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "seen.sqlite"
WATCHLIST_PATH = ROOT / "watchlist.json"

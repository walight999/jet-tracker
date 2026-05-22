"""Forward XAU-relevant alerts to the GoldBot pipeline.

Only fires for alerts whose macro_tag is in GOLD_TAGS. POSTs a compact
JSON payload to GOLD_SIGNAL_WEBHOOK (configurable in .env).

Skips silently if GOLD_SIGNAL_WEBHOOK is empty.

Suggested wiring on the GoldBot side:
  - Use the existing Make scenario (5656446) or create a new webhook.
  - Make module: Webhook -> custom branch tagged "jet_signal" -> LINE
    text + Notion row in gold-analyst macro events DB.
"""
import os
from datetime import datetime, timezone

import requests

from config import ROOT
from dotenv import load_dotenv
from macro_signal import GOLD_TAGS

load_dotenv(ROOT / ".env")

GOLD_SIGNAL_WEBHOOK = os.getenv("GOLD_SIGNAL_WEBHOOK", "")


def forward(summary, macro_tag):
    if not GOLD_SIGNAL_WEBHOOK:
        return False
    if macro_tag not in GOLD_TAGS:
        return False

    payload = {
        "source": "jet-tracker",
        "ts": datetime.now(timezone.utc).isoformat(),
        "macro_tag": macro_tag,
        "label": summary["label"],
        "callsign": summary["callsign"],
        "registration": summary["registration"],
        "hex": summary["hex"],
        "type": summary["type"],
        "owner": summary["owner"],
        "owner_verified": summary.get("owner_verified", False),
        "owner_country": summary.get("owner_country"),
        "route": summary.get("route"),
        "position": summary["position"],
        "altitude": summary["altitude"],
        "speed": summary["speed"],
        "category": summary.get("category"),
        "globe_url": f"https://globe.airplanes.live/?icao={summary['hex'].lower()}",
    }

    try:
        r = requests.post(GOLD_SIGNAL_WEBHOOK, json=payload, timeout=15)
        if not r.ok:
            print(f"[gold-export] {r.status_code}: {r.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"[gold-export] exception: {e}")
        return False

import time
import requests
from config import AIRPLANES_LIVE_BASE

USER_AGENT = "jet-tracker/0.1 (personal use)"
_last_call = [0.0]
_MIN_GAP = 1.5


def _throttle():
    elapsed = time.time() - _last_call[0]
    if elapsed < _MIN_GAP:
        time.sleep(_MIN_GAP - elapsed)
    _last_call[0] = time.time()


def _get(path):
    _throttle()
    url = f"{AIRPLANES_LIVE_BASE}{path}"
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    return r.json()


def get_aircraft_by_hex(hex_code):
    data = _get(f"/hex/{hex_code.lower()}")
    return data.get("ac", []) or []


def get_military():
    data = _get("/mil")
    return data.get("ac", []) or []


def get_pia():
    data = _get("/pia")
    return data.get("ac", []) or []

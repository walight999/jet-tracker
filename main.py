import base64
import gzip
import json
import os
import sys
import traceback

import config
import airplanes_api as api
import storage
import enrich
import alert
import adsbdb
import airports
import digest
import geocode
import trace as tracelib
import notion_log
import gold_signal_export


def load_watchlist():
    """Load the curated watchlist.

    Priority:
      1. WATCHLIST_GZ_B64 env (base64-encoded gzip of watchlist.json) — used in CI
         where the watchlist is kept out of the public repo.
      2. config.WATCHLIST_PATH file — local development fallback.
    """
    encoded = os.getenv("WATCHLIST_GZ_B64")
    if encoded:
        # Strip BOM + any whitespace that pipe-based secret upload may add.
        encoded = encoded.lstrip("﻿").strip()
        raw = gzip.decompress(base64.b64decode(encoded))
        return json.loads(raw.decode("utf-8"))
    return json.loads(config.WATCHLIST_PATH.read_text(encoding="utf-8"))


def match_callsign(callsign, patterns):
    if not callsign:
        return None
    cs = callsign.strip().upper()
    if not cs:
        return None
    best = None
    for prefix, meta in patterns.items():
        p = prefix.upper()
        if cs.startswith(p):
            if best is None or len(p) > len(best[0]):
                best = (p, meta)
    return best[1] if best else None


def in_region(ac, region):
    lat = ac.get("lat")
    lon = ac.get("lon")
    if lat is None or lon is None:
        return False
    return (
        region["min_lat"] <= lat <= region["max_lat"]
        and region["min_lon"] <= lon <= region["max_lon"]
    )


def is_interesting_mil(ac, interesting_types):
    t = (ac.get("t") or "").upper()
    if not t:
        return False
    return any(it.upper() in t for it in interesting_types)


def _emit(summary, meta, phase_label=None):
    """Run scoring + market relevance, then route to push or digest based on action."""
    if phase_label:
        summary["phase_label"] = phase_label
    summary["attribution"] = meta.get("attribution", summary.get("attribution", "registered"))
    if meta.get("owner"):
        summary["watchlist_owner"] = meta.get("owner")

    # cluster_factor counts ALL recent qualifying events (alerts + digest),
    # not just Telegram-fired ones — see storage.recent_event_count rationale.
    recent = storage.recent_event_count(60)
    summary, sc = enrich.add_intel(summary, meta, recent)

    hex_code = summary["hex"]
    action = summary["action"]
    score = summary["impact_score"]
    level = summary["impact_level"]
    label_short = meta.get("label") or summary.get("label")

    # Below the push threshold → digest queue, no Telegram.
    if score < config.PUSH_MIN_SCORE:
        digest.enqueue(summary, sc)
        print(
            f"[digest] {action} {level} score={score} "
            f"{label_short} / {summary['callsign']} / {hex_code}"
        )
        return False

    # High/Critical → cooldown applies for High; Escalate (Critical) overrides.
    if action != "Escalate" and storage.recently_alerted(hex_code):
        digest.enqueue(summary, sc)
        print(
            f"[skip-cooldown] {level} score={score} {label_short} / {hex_code}"
        )
        return False

    msg = alert.build_message(summary)
    sent = alert.send_telegram(msg)
    notion_log.log_alert(summary, None)
    gold_signal_export.forward(summary, None)
    storage.mark_alerted(hex_code, summary["callsign"], label_short)
    print(
        f"[alert] {action} {level} score={score} "
        f"{label_short} / {summary['callsign']} / {hex_code} "
        f"tg={'ok' if sent else 'fail'}"
    )
    return True


def alert_aircraft(ac, label, owner, category, macro_tag=None):
    """Compatibility wrapper for callsign / PIA flows.

    `macro_tag` is accepted but ignored — kept for signature stability while we
    refactor callers. Watchlist's macro_tag is no longer auto-injected; the
    new scoring/market-relevance pipeline decides what to surface.
    """
    hex_code = (ac.get("hex") or "").upper()
    if not hex_code:
        return False
    summary = enrich.aircraft_summary(ac, label, owner, category)
    meta = {"label": label, "owner": owner, "category": category}
    return _emit(summary, meta)


def determine_state(ac):
    """Classify aircraft as 'airborne', 'ground', or 'missing'."""
    if not ac:
        return "missing"
    alt = ac.get("alt_baro")
    gs = ac.get("gs") or 0
    if isinstance(alt, str) and alt.lower() == "ground":
        return "ground"
    if isinstance(alt, (int, float)) and alt < 500 and gs < 30:
        return "ground"
    return "airborne"


def _phase_transition_label(prev_state, new_state, prev_alt):
    """Return (phase_label, should_alert, override_state).
    override_state lets us mark LIKELY LANDED → 'ground'."""
    if prev_state in (None, "never"):
        if new_state == "airborne":
            return ("IN FLIGHT", True, new_state)
        return (None, False, new_state)
    if prev_state == "ground" and new_state == "airborne":
        return ("TAKEOFF", True, new_state)
    if prev_state == "airborne" and new_state == "ground":
        return ("LANDED", True, new_state)
    if prev_state == "airborne" and new_state == "missing":
        if prev_alt is not None and prev_alt < 10000:
            return ("LIKELY LANDED", True, "ground")
        return (None, False, new_state)
    if prev_state == "missing" and new_state == "airborne":
        return ("IN FLIGHT", True, new_state)
    return (None, False, new_state)


def fire_phase_alert(ac, meta, phase_label):
    summary = enrich.aircraft_summary(
        ac,
        meta.get("label", "?"),
        meta.get("owner") or meta.get("label", "?"),
        meta.get("category", "?"),
    )
    _emit(summary, meta, phase_label=phase_label)


def _should_poll_this_cycle(hex_code, priority):
    """Priority-based polling. high = every cycle, low = every 4 cycles."""
    if priority != "low":
        return True
    import time as _t
    cycle = int(_t.time() // (config.POLL_INTERVAL_MIN * 60))
    bucket = int(hex_code, 16) % 4
    return cycle % 4 == bucket


def poll_by_hex(wl):
    fired = 0
    polled = 0
    skipped = 0
    for hex_code, meta in wl.get("by_hex", {}).items():
        priority = meta.get("poll_priority", "high")
        if not _should_poll_this_cycle(hex_code, priority):
            skipped += 1
            continue
        polled += 1
        try:
            data = api.get_aircraft_by_hex(hex_code)
            ac = data[0] if data else None
        except Exception as e:
            print(f"[poll] hex {hex_code} failed: {e}")
            continue

        new_state = determine_state(ac)
        prev = storage.get_state(hex_code)
        prev_state = prev["state"] if prev else "never"
        prev_alt = prev["last_alt"] if prev else None

        phase_label, should_alert, final_state = _phase_transition_label(
            prev_state, new_state, prev_alt
        )

        if should_alert:
            alert_ac = ac
            if phase_label == "LIKELY LANDED":
                # Synthesize ac from last known state
                alert_ac = {
                    "hex": hex_code.lower(),
                    "lat": prev.get("last_lat"),
                    "lon": prev.get("last_lon"),
                    "alt_baro": "ground",
                    "gs": 0,
                    "flight": prev.get("last_callsign") or "",
                    "r": "?",
                    "t": "?",
                    "desc": "(broadcast ended)",
                    "baro_rate": 0,
                }
            fire_phase_alert(alert_ac, meta, phase_label)
            fired += 1

        storage.set_state(hex_code, final_state, ac)
    print(f"[poll] by_hex: polled {polled}, skipped {skipped} (low-priority rotation), alerts {fired}")
    return fired


def poll_military(wl):
    fired = 0
    if not wl.get("feeds", {}).get("military"):
        return 0
    try:
        mil = api.get_military()
    except Exception as e:
        print(f"[poll] mil failed: {e}")
        return 0

    callsign_patterns = wl.get("by_callsign_pattern", {})
    interesting_types = wl.get("interesting_mil_types", [])
    print(f"[poll] military airborne: {len(mil)}")

    for ac in mil:
        # 1. Callsign pattern hit (strategic ops only)
        meta = match_callsign(ac.get("flight"), callsign_patterns)
        if meta:
            if alert_aircraft(
                ac,
                meta["label"],
                meta["label"],
                meta.get("category", "military"),
                meta.get("macro_tag"),
            ):
                fired += 1
            continue

        # 2. Strategic aircraft type (E-4, B-2, RC-135 — always interesting worldwide)
        if is_interesting_mil(ac, interesting_types):
            type_part = ac.get("t") or "Unknown type"
            label = f"Strategic aircraft: {type_part}"
            if alert_aircraft(
                ac,
                label,
                None,
                "us_mil_isr",
                "geopolitical",
            ):
                fired += 1
    return fired


def poll_pia(wl):
    fired = 0
    if not wl.get("feeds", {}).get("pia"):
        return 0
    try:
        pia = api.get_pia()
    except Exception as e:
        print(f"[poll] pia failed: {e}")
        return 0

    regions = wl.get("watch_regions", {})
    print(f"[poll] PIA airborne: {len(pia)}")

    for ac in pia:
        hit_region = None
        for region_name, region in regions.items():
            if in_region(ac, region):
                hit_region = (region_name, region.get("macro_tag"))
                break
        if hit_region:
            label = f"PIA Aircraft in {hit_region[0]}"
            if alert_aircraft(
                ac,
                label,
                "Privacy ICAO (operator hidden)",
                "pia",
                hit_region[1],
            ):
                fired += 1
    return fired


def run_once():
    storage.init()
    digest.init()
    adsbdb.init()
    geocode.init()
    tracelib.init()
    airports.init()
    wl = load_watchlist()
    print("[poll] start")
    total = 0
    total += poll_by_hex(wl)
    total += poll_military(wl)
    total += poll_pia(wl)
    print(f"[poll] done — {total} alerts fired")


def diagnostic():
    """Sanity check API + Telegram without firing watchlist logic."""
    print("=== DIAGNOSTIC ===")
    try:
        mil = api.get_military()
        print(f"[diag] /mil OK — {len(mil)} airborne military aircraft")
        if mil:
            sample = mil[0]
            print(f"[diag] sample: hex={sample.get('hex')} flight={sample.get('flight')} type={sample.get('t')} desc={sample.get('desc')}")
    except Exception as e:
        print(f"[diag] /mil failed: {e}")

    try:
        pia = api.get_pia()
        print(f"[diag] /pia OK — {len(pia)} airborne PIA aircraft")
    except Exception as e:
        print(f"[diag] /pia failed: {e}")

    test_msg = "✈️ jet-tracker diagnostic — Telegram OK"
    sent = alert.send_telegram(test_msg)
    print(f"[diag] telegram test: {'sent' if sent else 'NOT sent (check token/chat_id)'}")


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "diag":
            diagnostic()
        else:
            run_once()
    except Exception:
        traceback.print_exc()
        sys.exit(1)

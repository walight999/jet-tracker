"""Telegram notification builder for the Strategic Impact Alert System.

The old `macro_note` auto-XAU tag is gone. Market relevance is now an
earned field carried on the summary (`market_relevance`, `market_reason`).
"""
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


LEVEL_HEADER = {
    "Critical": "🔴 CRITICAL IMPACT WATCH",
    "High": "🟠 HIGH IMPACT WATCH",
    "Medium": "🟡 IMPACT MONITOR",
    "Low": "⚪ IMPACT LOG",
}

FRIENDLY_CATEGORY = {
    "head_of_state": "Head of State",
    "politician": "Politician",
    "billionaire": "Billionaire",
    "celebrity": "Celebrity",
    "us_strategic": "US Strategic Command",
    "us_mil_isr": "US Military ISR",
    "sanctioned": "Sanctions / Logistics",
    "pia": "Privacy ICAO",
}


def _owner_lines(summary):
    attribution = summary.get("attribution") or "registered"
    watchlist_owner = summary.get("watchlist_owner")
    if watchlist_owner and attribution == "journalism":
        owner_line = f"{watchlist_owner} ℹ️ public attribution"
        registry_owner = summary.get("owner")
        registry_line = None
        if registry_owner and registry_owner != "Unknown":
            registry_country = summary.get("owner_country")
            rs = registry_owner + (f" ({registry_country})" if registry_country else "")
            registry_line = f"  Registry: {rs}"
        return owner_line, registry_line

    owner_line = summary.get("owner") or "Unknown"
    if summary.get("owner_country"):
        owner_line = f"{owner_line} ({summary['owner_country']})"
    if not summary.get("owner_verified") and owner_line != "Unknown":
        owner_line = f"{owner_line} ⚠ unverified"
    return owner_line, None


def _route_line(summary):
    if summary.get("route"):
        return f"  Route: {summary['route']}"
    s = summary.get("started_over")
    c = summary.get("currently_over")
    status = summary.get("trace_status")
    if s and c:
        verb = "Departed" if status == "takeoff" else "Tracked from"
        return f"  {verb}: {s} → currently over {c}"
    if c:
        return f"  Currently over: {c}"
    if s:
        verb = "Departed" if status == "takeoff" else "Tracked from"
        return f"  {verb}: {s}"
    return "  Route: not published — see live map"


def _status_line(summary):
    phase_label = summary.get("phase_label")
    phase_text = summary.get("phase_text")
    phase_emoji = summary.get("phase_emoji") or "✈️"
    if phase_label and phase_label not in ("LANDED", "LIKELY LANDED"):
        if phase_text:
            return f"  Status: {phase_emoji} {phase_label} — {phase_text}"
        return f"  Status: {phase_emoji} {phase_label}"
    if phase_label:
        return f"  Status: {phase_emoji} {phase_label}"
    if phase_text:
        return f"  Status: {phase_emoji} {phase_text}"
    return None


def build_message(summary):
    """Build a strategic impact alert message.

    Required fields on summary (added by enrich.add_intel):
      impact_score, impact_level, action, market_relevance, market_reason,
      why_it_matters, data_confidence
    """
    header = LEVEL_HEADER.get(summary.get("impact_level"), "✈️ JET INTEL")
    label = summary.get("label", "Unknown aircraft")
    owner_line, registry_line = _owner_lines(summary)

    lines = [
        header,
        "",
        f"Aircraft: {label}",
        f"  Callsign: {summary.get('callsign')}  ({summary.get('registration')})",
        f"  Type: {summary.get('type')}",
        f"  Owner: {owner_line}",
        registry_line,
        _status_line(summary),
        _route_line(summary),
        "",
        f"Impact Score: {summary.get('impact_score')}/9 ({summary.get('impact_level')})",
        f"Category: {FRIENDLY_CATEGORY.get(summary.get('category'), summary.get('category') or 'Aviation')}",
        f"Market Relevance: {summary.get('market_relevance', 'None')}",
        f"Why it matters: {summary.get('why_it_matters')}",
        f"Data Confidence: {summary.get('data_confidence')}",
        f"Action: {summary.get('action')}",
        "",
        f"🌐 https://globe.airplanes.live/?icao={summary['hex'].lower()}",
    ]
    return "\n".join([ln for ln in lines if ln is not None])


def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[alert] TELEGRAM_BOT_TOKEN/CHAT_ID not set — printing instead:\n" + text + "\n")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": "true"},
            timeout=15,
        )
        if not r.ok:
            print(f"[alert] Telegram failed: {r.status_code} {r.text}")
            return False
        return True
    except Exception as e:
        print(f"[alert] Telegram exception: {e}")
        return False

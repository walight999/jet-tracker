import adsbdb
import airports
import geocode
import market_relevance
import scoring
import trace as tracelib


def detect_phase(ac):
    """Return (phase_emoji, phase_text) tuple.

    Phases:
      🚏 On ground   — alt=ground or very low+slow
      🛻 Taxiing     — on ground, moving
      🛫 Taking off  — low alt, fast climb
      📈 Climbing    — mid alt, climbing
      🛬 On approach — low alt, descending
      📉 Descending  — mid alt, descending
      ✈️ Cruising    — high alt, level
      ❔ Unknown
    """
    alt = ac.get("alt_baro")
    gs = ac.get("gs") or 0
    vr = ac.get("baro_rate") or 0

    on_ground = (isinstance(alt, str) and alt.lower() == "ground")
    if on_ground:
        if gs > 30:
            return ("🛻", "Taxiing")
        return ("🚏", "On ground")

    if alt is None:
        return ("❔", "Position unknown")

    try:
        alt_int = int(alt)
    except (ValueError, TypeError):
        return ("❔", "Altitude unknown")

    if alt_int < 1500:
        if vr > 500:
            return ("🛫", "Taking off")
        if vr < -500:
            return ("🛬", "On approach")
        return ("🛬", "Low altitude")
    if alt_int < 10000:
        if vr > 500:
            return ("📈", "Climbing")
        if vr < -500:
            return ("📉", "Descending")
        return ("✈️", f"Level at FL{alt_int//100:03d}")
    # Cruise band
    if vr > 1000:
        return ("📈", f"Climbing to cruise (FL{alt_int//100:03d})")
    if vr < -1000:
        return ("📉", f"Descending from cruise (FL{alt_int//100:03d})")
    return ("✈️", f"Cruising at FL{alt_int//100:03d}")


COUNTRY_SHORT = {
    "United States": "USA",
    "United States of America": "USA",
    "United Kingdom": "UK",
    "United Kingdom of Great Britain and Northern Ireland": "UK",
    "United Arab Emirates": "UAE",
    "Russian Federation": "Russia",
    "Korea, Republic of": "South Korea",
    "Republic of Korea": "South Korea",
    "Korea, Democratic People's Republic of": "North Korea",
    "Iran, Islamic Republic of": "Iran",
    "Iran (Islamic Republic of)": "Iran",
    "Syrian Arab Republic": "Syria",
    "Lao People's Democratic Republic": "Laos",
    "Viet Nam": "Vietnam",
    "Czechia": "Czech Republic",
    "Taiwan, Province of China": "Taiwan",
    "Hong Kong, Special Administrative Region of China": "Hong Kong",
    "Macao, Special Administrative Region of China": "Macao",
    "Venezuela (Bolivarian Republic of)": "Venezuela",
    "Bolivia (Plurinational State of)": "Bolivia",
    "Tanzania, United Republic of": "Tanzania",
    "Moldova, Republic of": "Moldova",
    "Saudi Arabia": "KSA",
    "Democratic Republic of the Congo": "DR Congo",
}


def short_country(name):
    if not name:
        return None
    return COUNTRY_SHORT.get(name, name)


def fmt_altitude(alt):
    if alt is None:
        return "—"
    if isinstance(alt, str) and alt.lower() == "ground":
        return "GROUND"
    try:
        return f"FL{int(alt) // 100:03d}"
    except (ValueError, TypeError):
        return str(alt)


def fmt_position(ac):
    lat = ac.get("lat")
    lon = ac.get("lon")
    if lat is None or lon is None:
        return "—"
    return f"{lat:.2f}, {lon:.2f}"


def fmt_speed(gs):
    if gs is None:
        return "—"
    try:
        return f"{int(gs)} kts"
    except (ValueError, TypeError):
        return str(gs)


def fmt_airport(ap):
    if not ap:
        return None
    name = ap.get("name") or ap.get("municipality")
    if not name:
        return None
    country = short_country(ap.get("country_name")) or ap.get("country_iso_name")
    if country:
        return f"{name} ({country})"
    return name


def fmt_route(route):
    """Build 'JFK New York US → LHR London GB' or None."""
    if not route:
        return None
    o = fmt_airport(route.get("origin"))
    d = fmt_airport(route.get("destination"))
    if not o and not d:
        return None
    return f"{o or '?'} → {d or '?'}"


def aircraft_summary(ac, label, fallback_owner, category):
    hex_code = (ac.get("hex") or "").upper()
    callsign_raw = (ac.get("flight") or "").strip()

    real_owner = None
    owner_verified = False
    real_type = ac.get("desc") or "—"
    owner_country = None
    photo_url = None

    enriched_ac = adsbdb.get_aircraft(hex_code) if hex_code else None
    if enriched_ac:
        ro = enriched_ac.get("registered_owner")
        if ro:
            real_owner = ro
            owner_verified = True
        manuf = enriched_ac.get("manufacturer")
        typ = enriched_ac.get("type")
        if manuf and typ:
            real_type = f"{manuf} {typ}"
        country_full = enriched_ac.get("registered_owner_country_name") or enriched_ac.get("registered_owner_country_iso_name")
        owner_country = short_country(country_full)
        photo_url = enriched_ac.get("url_photo_thumbnail") or enriched_ac.get("url_photo")

    if not real_owner:
        real_owner = fallback_owner if fallback_owner else "Unknown"

    route = adsbdb.get_route(callsign_raw) if callsign_raw else None
    route_str = fmt_route(route)
    airline = None
    if route and route.get("airline"):
        airline = route["airline"].get("name")

    currently_over = None
    started_over = None
    trace_status = None
    if not route_str:
        cur_lat, cur_lon = ac.get("lat"), ac.get("lon")
        cur_alt = ac.get("alt_baro")
        cur_low = (
            isinstance(cur_alt, str) and cur_alt.lower() == "ground"
        ) or (isinstance(cur_alt, (int, float)) and cur_alt < 3000)

        if cur_low and cur_lat is not None and cur_lon is not None:
            # Low altitude / on ground → identify the airport
            ap = airports.nearest(cur_lat, cur_lon, max_km=30)
            currently_over = airports.fmt_airport(ap) if ap else None
        if not currently_over:
            # Mid/high altitude → coarse country/region via Nominatim
            currently_over = geocode.reverse(cur_lat, cur_lon)
            if currently_over:
                currently_over = short_country(currently_over) or currently_over

        # Where did this trace start (origin region or actual takeoff airport)
        tr = tracelib.fetch(hex_code) if hex_code else None
        if tr:
            origin_alt = tr.get("origin_alt")
            origin_lat, origin_lon = tr.get("origin_lat"), tr.get("origin_lon")
            origin_place = None
            if origin_alt is not None and origin_alt < 3000:
                # Real takeoff observed in trace → nearest airport
                ap = airports.nearest(origin_lat, origin_lon, max_km=30)
                origin_place = airports.fmt_airport(ap) if ap else None
                trace_status = "takeoff"
            if not origin_place:
                origin_place = geocode.reverse(origin_lat, origin_lon)
                if origin_place:
                    origin_place = short_country(origin_place) or origin_place
                trace_status = trace_status or "cruise_start"
            started_over = origin_place

            # Sanity: drop origin if same as current
            if started_over and currently_over and started_over == currently_over:
                started_over = None

    phase_emoji, phase_text = detect_phase(ac)

    return {
        "hex": hex_code or "?",
        "callsign": callsign_raw or "—",
        "registration": ac.get("r") or "—",
        "type": real_type,
        "altitude": fmt_altitude(ac.get("alt_baro")),
        "speed": fmt_speed(ac.get("gs")),
        "position": fmt_position(ac),
        "squawk": ac.get("squawk") or "—",
        "desc": ac.get("desc") or "—",
        "label": label,
        "owner": real_owner or "Unknown",
        "owner_verified": owner_verified,
        "owner_country": owner_country,
        "airline": airline,
        "route": route_str,
        "currently_over": currently_over,
        "started_over": started_over,
        "trace_status": trace_status,
        "phase_emoji": phase_emoji,
        "phase_text": phase_text,
        "photo_url": photo_url,
        "category": category,
    }


def _data_confidence(summary):
    has_callsign = summary.get("callsign") and summary["callsign"] != "—"
    has_position = summary.get("position") and summary["position"] != "—"
    has_route = bool(summary.get("route"))
    has_currently = bool(summary.get("currently_over"))
    if has_callsign and has_route:
        return "High"
    if has_callsign and (has_position or has_currently):
        return "Medium"
    if has_position or has_currently:
        return "Medium"
    return "Low"


_CATEGORY_REASON = {
    "head_of_state": "Head-of-state aircraft movement.",
    "politician": "Political-figure aircraft movement.",
    "us_strategic": "US strategic-command aircraft (nuclear / SecState fleet) active.",
    "us_mil_isr": "US military ISR / strategic asset active.",
    "billionaire": "Billionaire-tied aircraft movement.",
    "celebrity": "Celebrity-tied aircraft movement.",
    "sanctioned": "Sanctioned entity active.",
    "pia": "Privacy-ICAO aircraft active in a watched region.",
}


def _why(summary, meta, scoring_result, market):
    parts = []
    cat = meta.get("category", "")
    base = _CATEGORY_REASON.get(cat)
    if base:
        parts.append(base)
    if market.get("reason"):
        parts.append(market["reason"])
    if scoring_result["components"]["cluster_factor"] >= 2:
        parts.append("Activity above recent baseline.")
    if not parts:
        parts.append(f"{summary.get('label')} state change.")
    return " ".join(parts)


def add_intel(summary, meta, recent_alert_count):
    """Inject impact score, market relevance, action, data confidence,
    why-it-matters into the summary. Pure-ish — no network, just sqlite count
    that is already passed in by the caller.
    """
    sc = scoring.compute(meta, summary, recent_alert_count)
    summary["impact_score"] = sc["score"]
    summary["impact_level"] = sc["level"]
    summary["action"] = sc["action"]
    summary["impact_components"] = sc["components"]

    mr = market_relevance.classify(sc, summary, meta)
    summary["market_relevance"] = mr["relevance"]
    summary["market_reason"] = mr["reason"]

    summary["data_confidence"] = _data_confidence(summary)
    summary["why_it_matters"] = _why(summary, meta, sc, mr)
    return summary, sc

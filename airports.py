"""Nearest-airport lookup using the OurAirports public CSV.

OurAirports is a CC0 public-domain airport database (~80k entries).
We filter to large + medium airports (~10k) for fast in-memory lookup.

First run downloads the CSV (~5 MB) to data/airports.csv.
Subsequent calls load the parsed slice from memory.
"""
import csv
import math
import time
from pathlib import Path

import requests

from config import DATA_DIR

CSV_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
CSV_PATH = DATA_DIR / "airports.csv"
USER_AGENT = "jet-tracker/0.1 (personal)"

_AIRPORTS = None  # list of dicts: ident, name, lat, lon, iata, country, municipality, type


ISO_SHORT = {
    "US": "USA", "GB": "UK", "AE": "UAE", "SA": "Saudi Arabia",
    "KR": "South Korea", "KP": "North Korea", "RU": "Russia",
    "CN": "China", "JP": "Japan", "IN": "India", "TH": "Thailand",
    "DE": "Germany", "FR": "France", "IT": "Italy", "ES": "Spain",
    "CA": "Canada", "AU": "Australia", "NZ": "New Zealand",
    "BR": "Brazil", "MX": "Mexico", "AR": "Argentina",
    "NL": "Netherlands", "BE": "Belgium", "CH": "Switzerland",
    "AT": "Austria", "SE": "Sweden", "NO": "Norway", "DK": "Denmark",
    "FI": "Finland", "PL": "Poland", "CZ": "Czechia", "PT": "Portugal",
    "GR": "Greece", "TR": "Turkey", "IL": "Israel", "EG": "Egypt",
    "QA": "Qatar", "KW": "Kuwait", "BH": "Bahrain", "OM": "Oman",
    "IR": "Iran", "IQ": "Iraq", "JO": "Jordan", "LB": "Lebanon",
    "PK": "Pakistan", "BD": "Bangladesh", "LK": "Sri Lanka",
    "MY": "Malaysia", "SG": "Singapore", "ID": "Indonesia",
    "PH": "Philippines", "VN": "Vietnam", "TW": "Taiwan", "HK": "Hong Kong",
    "ZA": "South Africa", "NG": "Nigeria", "KE": "Kenya", "MA": "Morocco",
    "UA": "Ukraine", "RO": "Romania", "BY": "Belarus",
}


def _download():
    print(f"[airports] downloading {CSV_URL}...")
    r = requests.get(CSV_URL, headers={"User-Agent": USER_AGENT}, timeout=60)
    r.raise_for_status()
    CSV_PATH.write_bytes(r.content)
    print(f"[airports] saved {len(r.content)//1024} KB to {CSV_PATH}")


def _load():
    global _AIRPORTS
    if _AIRPORTS is not None:
        return _AIRPORTS
    if not CSV_PATH.exists():
        _download()

    out = []
    KEEP_TYPES = {"large_airport", "medium_airport"}
    with CSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = row.get("type", "")
            if t not in KEEP_TYPES:
                continue
            try:
                lat = float(row["latitude_deg"])
                lon = float(row["longitude_deg"])
            except (KeyError, ValueError):
                continue
            out.append({
                "ident": row.get("ident", ""),  # ICAO code
                "iata": row.get("iata_code", ""),
                "name": row.get("name", ""),
                "lat": lat,
                "lon": lon,
                "country": row.get("iso_country", ""),
                "municipality": row.get("municipality", ""),
                "type": t,
            })
    _AIRPORTS = out
    print(f"[airports] loaded {len(out)} large/medium airports")
    return out


def init():
    _load()


def _approx_dist_sq(lat1, lon1, lat2, lon2):
    """Squared planar distance in degrees, longitude scaled by cos(lat).
    Fast and monotonic with true distance — fine for nearest-neighbor."""
    dlat = lat1 - lat2
    dlon = (lon1 - lon2) * math.cos(math.radians(lat1))
    return dlat * dlat + dlon * dlon


def _deg_to_km(dist_deg):
    return dist_deg * 111.0


def nearest(lat, lon, max_km=50):
    """Return the nearest airport within max_km, or None.

    Returns dict: {ident, iata, name, country, municipality, distance_km}
    """
    if lat is None or lon is None:
        return None
    airports = _load()

    best = None
    best_d2 = float("inf")
    max_d2 = (max_km / 111.0) ** 2
    for ap in airports:
        d2 = _approx_dist_sq(lat, lon, ap["lat"], ap["lon"])
        if d2 < best_d2 and d2 < max_d2:
            best_d2 = d2
            best = ap

    if not best:
        return None
    return {
        **best,
        "distance_km": round(_deg_to_km(math.sqrt(best_d2)), 1),
    }


def fmt_airport(ap):
    """Format airport dict as a human label: 'Name (IATA, Country)'."""
    if not ap:
        return None
    code = ap.get("iata") or ap.get("ident")
    name = ap.get("name", "")
    country_iso = ap.get("country", "")
    country = ISO_SHORT.get(country_iso, country_iso)
    parts = [name]
    bracket = []
    if code:
        bracket.append(code)
    if country:
        bracket.append(country)
    if bracket:
        parts.append(f"({', '.join(bracket)})")
    return " ".join(parts).strip()

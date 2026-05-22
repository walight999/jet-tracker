"""Import OFAC-sanctioned aircraft into watchlist.

Pulls the SDN.CSV from US Treasury OFAC, extracts the ~340 aircraft entries,
resolves each tail number to an ICAO hex via adsbdb, and appends to
watchlist.json with attribution=ofac_sanctioned and category=sanctioned.

Re-run periodically (e.g. weekly) — OFAC updates the SDN list frequently.

Usage:
    python sanctioned_import.py            # full sync
    python sanctioned_import.py --dry-run  # just show what would be added
"""
import csv
import json
import re
import sys
from pathlib import Path

import requests

import adsbdb
import config

SDN_URL = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV"
SDN_LOCAL = config.DATA_DIR / "ofac_sdn.csv"
USER_AGENT = "jet-tracker/0.1 (personal use)"


def download_sdn():
    print(f"[ofac] downloading {SDN_URL}...")
    r = requests.get(SDN_URL, headers={"User-Agent": USER_AGENT}, timeout=60)
    r.raise_for_status()
    SDN_LOCAL.write_bytes(r.content)
    print(f"[ofac] saved {len(r.content)//1024} KB to {SDN_LOCAL}")


def parse_remarks(remarks):
    """Extract aircraft model, operator, linked entity from OFAC remarks."""
    info = {}
    m = re.search(r"Aircraft Model ([^;]+);", remarks)
    if m:
        info["model"] = m.group(1).strip()
    m = re.search(r"Aircraft Operator ([^;]+);", remarks)
    if m:
        info["operator"] = m.group(1).strip()
    m = re.search(r"Linked To: ([^.\"]+)", remarks)
    if m:
        info["linked_to"] = m.group(1).strip().rstrip(".")
    return info


def extract_aircraft_rows():
    """Yield (tail, program, remarks) for each aircraft row in SDN.CSV."""
    if not SDN_LOCAL.exists():
        download_sdn()
    with SDN_LOCAL.open(encoding="latin-1") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 12:
                continue
            sdn_type = row[2].strip().strip('"').lower()
            if sdn_type != "aircraft":
                continue
            tail = row[1].strip().strip('"')
            program = row[3].strip().strip('"')
            remarks = row[11].strip().strip('"')
            if tail and tail != "-0-":
                yield tail, program, remarks


def main(dry_run=False):
    adsbdb.init()
    wl_path = config.WATCHLIST_PATH
    wl = json.loads(wl_path.read_text(encoding="utf-8"))
    by_hex = wl.setdefault("by_hex", {})

    download_sdn()

    aircraft = list(extract_aircraft_rows())
    print(f"[ofac] {len(aircraft)} aircraft entries in SDN list")

    added = 0
    already = 0
    failed = []
    for tail, program, remarks in aircraft:
        # Skip if tail looks like internal serial number (no proper registration prefix)
        if not re.match(r"^[A-Z0-9][A-Z0-9\-]+$", tail):
            continue
        info = parse_remarks(remarks)
        operator = info.get("operator", "?")
        model = info.get("model", "?")
        linked = info.get("linked_to", "?")
        programs = program.replace("] [", "/").strip("[]")

        ac = adsbdb.get_aircraft(tail)
        if not ac:
            failed.append(tail)
            continue
        hex_code = (ac.get("mode_s") or "").upper()
        if not hex_code or hex_code in by_hex:
            already += 1
            continue

        label = f"SANCTIONED: {tail} ({model})"
        if linked != "?":
            label = f"SANCTIONED: {linked} — {tail}"

        entry = {
            "label": label,
            "owner": f"{operator} (OFAC {programs})",
            "category": "sanctioned",
            "macro_tag": "geopolitical",
            "attribution": "ofac_sanctioned",
            "poll_priority": "low",
            "notes": f"seeded from OFAC SDN: tail={tail} program={programs} linked={linked} model={model}",
        }
        if dry_run:
            print(f"  + would add {hex_code}  {label}")
        else:
            by_hex[hex_code] = entry
            print(f"  ✓ {hex_code}  {label}")
        added += 1

    if not dry_run:
        wl_path.write_text(json.dumps(wl, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[ofac] done — added {added}, already in watchlist {already}, not in adsbdb {len(failed)}")
    if failed[:10]:
        print(f"[ofac] sample failed tails: {', '.join(failed[:10])}")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    main(dry_run=dry)

# jet-tracker

Strategic Impact Alert System — personal OSINT bot tracking ~275 globally-significant aircraft (heads of state, US strategic command, sanctioned entities, billionaires, celebrities). Polls airplanes.live, scores each state transition on a deterministic impact rubric, and routes High/Critical events to Telegram while shelving Low/Medium ones in a digest queue.

## How it works

- **Sources** — airplanes.live `/v2/hex/<x>` and `/mil`; adsbdb for ownership; OurAirports for airport precision; OFAC SDN.CSV for sanctioned entities.
- **Scoring (v1, score /9)** — `aircraft_sensitivity (0-3) + route_anomaly (0-3) + cluster_factor (0-3)`.
- **Action gate** — score `<6` → digest queue only (no push); score `≥6` → push Telegram with 45-min per-aircraft cooldown; Critical (`≥8`) bypasses cooldown.
- **Market relevance** — `None / Indirect`. Defaults to None; only earned when sensitive aircraft hit sensitive routes or cluster above baseline. `Direct` reserved for v2 (needs a news/event source).
- **State machine** — per-hex transitions tracked in `data/seen.sqlite`: never→airborne, ground→airborne (TAKEOFF), airborne→ground (LANDED), airborne→missing<10k ft (LIKELY LANDED).

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env  # fill TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
python main.py
```

`python main.py diag` is a sanity check that hits the API and Telegram without firing watchlist logic.

## Running on GitHub Actions (24/7)

`.github/workflows/poll.yml` runs every 5 minutes via cron. Required repo secrets:

| Secret | Required |
|---|---|
| `TELEGRAM_BOT_TOKEN` | yes |
| `TELEGRAM_CHAT_ID` | yes |
| `NOTION_TOKEN`, `NOTION_DB_ID` | optional (silently skipped if absent) |
| `GOLD_SIGNAL_WEBHOOK` | optional |

State (`data/*.sqlite`, `data/airports.csv`) is cached between runs via `actions/cache@v4`. First run downloads OurAirports CSV and starts a fresh state DB; subsequent runs restore.

## Watchlist

`watchlist.json` has three layers:

1. **`by_hex`** — verified ICAO24 hex codes (seeded via `seed_watchlist.py`, then enriched with OFAC SDN sanctioned entries via `sanctioned_import.py`).
2. **`by_callsign_pattern`** — prefix match (`AF1`, `SAM`, `RCH`, `NIGHTWATCH`, etc.).
3. **Feeds** — `/mil` (all global military, filtered by interesting types or regions) and `/pia` (Privacy ICAO inside watch regions).

Attribution is tracked per entry so alerts can show whether the ownership claim is registry-direct (`registered`), a named LLC documented in journalism (`named_shell`), a generic management company (`journalism`), or an OFAC designation (`ofac_sanctioned`).

## Files

| File | Purpose |
|---|---|
| `main.py` | Entry — one polling cycle per invocation |
| `airplanes_api.py` | airplanes.live REST client (1 req/sec) |
| `adsbdb.py` | adsbdb.com enrichment + local cache |
| `airports.py` | OurAirports nearest-airport lookup |
| `geocode.py` | Nominatim reverse-geocode fallback |
| `trace.py` | globe.airplanes.live trace fetcher |
| `enrich.py` | Build alert payload + inject intel (`add_intel`) |
| `scoring.py` | Impact score v1 (pure) |
| `market_relevance.py` | None / Indirect classifier (pure) |
| `digest.py` | sqlite-backed queue for Low/Medium |
| `alert.py` | Telegram sender + template builder |
| `notion_log.py` | Optional: log High/Critical alerts to Notion |
| `gold_signal_export.py` | Optional: forward macro-relevant alerts |
| `storage.py` | seen.sqlite — aircraft_state + alerts + cooldown |
| `seed_watchlist.py` | Resolve tail numbers → ICAO hex via adsbdb |
| `sanctioned_import.py` | Pull OFAC SDN, enrich, append to watchlist |

## Design brief

Reframe from "flight notification bot" → Strategic Impact Alert System, with deterministic scoring and earned market relevance. The auto-XAU tag that the v0.1-v0.8 alerts carried has been retired. Key principles:

1. Market relevance must EARN — no auto-tag for every government movement.
2. Impact is deterministic, not vibes.
3. Build for extraction; do not build a platform before source #2 exists.

## License

Personal project. Watchlist curation draws from public registries (FAA, planespotters.net, OFAC SDN). Not for commercial use.

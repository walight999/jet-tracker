"""Resolve aircraft registrations (tail numbers) -> ICAO24 hex codes
via adsbdb.com, and append to watchlist.json under by_hex.

Usage:
    python seed_watchlist.py

Edit the SEED list below with registrations + metadata you trust.
The script queries adsbdb for the current hex code, then writes back to
watchlist.json without duplicating existing entries.

Sources for registrations:
- Public ElonJet-style trackers on GitHub (e.g. Jxck-S/plane-notify)
- FAA registry (registry.faa.gov) for US tail numbers
- planespotters.net for any tail number
- Open-source celebrity jet datasets

Note: registrations can change ownership. Re-run periodically and review.
"""
import json
from pathlib import Path

import adsbdb
import config

# Edit this list. Each entry: registration + metadata to seed into watchlist.
# I intentionally do NOT include unverified hex codes — only registrations,
# which are easy to verify from news/public sources before adding here.
SEED = [
    # ───── US Government / National Command (verified USAF records) ─────
    {"reg": "82-8000", "expected_type": "VC-25", "label": "Air Force One (VC-25A 82-8000)", "owner": "USAF 89th Airlift Wing", "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "92-9000", "expected_type": "VC-25", "label": "Air Force One (VC-25A 92-9000)", "owner": "USAF 89th Airlift Wing", "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "73-1676", "expected_type": "E-4",   "label": "E-4B Nightwatch (NAOC)",         "owner": "USAF",                    "category": "us_strategic",  "macro_tag": "risk_off"},
    {"reg": "73-1677", "expected_type": "E-4",   "label": "E-4B Nightwatch (NAOC)",         "owner": "USAF",                    "category": "us_strategic",  "macro_tag": "risk_off"},
    {"reg": "74-0787", "expected_type": "E-4",   "label": "E-4B Nightwatch (NAOC)",         "owner": "USAF",                    "category": "us_strategic",  "macro_tag": "risk_off"},
    {"reg": "75-0125", "expected_type": "E-4",   "label": "E-4B Nightwatch (NAOC)",         "owner": "USAF",                    "category": "us_strategic",  "macro_tag": "risk_off"},

    # ───── Politicians ─────
    {"reg": "N757AF",  "expected_type": "757", "label": "Donald Trump's Boeing 757 (Trump Force One)", "owner": "Donald Trump",     "category": "politician",    "macro_tag": "geopolitical"},
    {"reg": "N725DT",  "expected_type": "Citation X", "label": "Donald Trump's Cessna Citation X",     "owner": "Donald Trump",     "category": "politician",    "macro_tag": None},

    # ───── Tech billionaires ─────
    # Attribution legend:
    #   "registered"   = registry directly names the person (highest confidence)
    #   "named_shell"  = LLC name uniquely identifies the person via journalism (high)
    #   "journalism"   = generic management company, but well-documented in journalism
    {"reg": "N628TS",  "expected_type": "G650",   "attribution": "named_shell", "label": "Elon Musk's Gulfstream G650ER",              "owner": "Elon Musk (Falcon Landing LLC)",            "category": "billionaire", "macro_tag": None},
    {"reg": "N1KE",    "expected_type": "G650",   "attribution": "registered",  "label": "Phil Knight's Gulfstream G650",              "owner": "Phil Knight (Nike Inc)",                    "category": "billionaire", "macro_tag": None},
    {"reg": "N271DV",  "expected_type": "G650",   "attribution": "journalism",  "label": "Jeff Bezos's Gulfstream G650ER",             "owner": "Jeff Bezos (via Executive Jet Mgmt)",       "category": "billionaire", "macro_tag": None},
    {"reg": "N887WM",  "expected_type": "Gulfstream", "attribution": "journalism", "label": "Bill Gates's Gulfstream G650ER",          "owner": "Bill Gates (Cascade Investment / Mente LLC)","category": "billionaire", "macro_tag": None},
    {"reg": "N194WM",  "expected_type": "BD-700", "attribution": "journalism",  "label": "Bill Gates's Bombardier Global Express",     "owner": "Bill Gates (Cascade Investment)",           "category": "billionaire", "macro_tag": None},
    {"reg": "N188WM",  "expected_type": "BD-700", "attribution": "journalism",  "label": "Bill Gates's Bombardier Global Express",     "owner": "Bill Gates (Cascade Investment)",           "category": "billionaire", "macro_tag": None},
    {"reg": "N225BG",  "expected_type": "Citation", "attribution": "journalism", "label": "Bill Gates's Cessna Citation X",            "owner": "Bill Gates (Cascade Investment)",           "category": "billionaire", "macro_tag": None},
    {"reg": "N888LE",  "expected_type": "Gulfstream", "attribution": "journalism", "label": "Larry Ellison's Gulfstream",              "owner": "Larry Ellison (Oracle)",                    "category": "billionaire", "macro_tag": None},
    {"reg": "N700FM",  "expected_type": "Gulfstream", "attribution": "journalism", "label": "Mark Zuckerberg's Gulfstream",            "owner": "Mark Zuckerberg",                            "category": "billionaire", "macro_tag": None},

    # NOTE: removed tail numbers below — adsbdb says they re-registered to small props/other aircraft.
    # Re-derive current correct tails from journalism/FAA registry then add back with expected_type.
    # {"reg": "N1JE",   ...  "Larry Ellison"  — Pitts S-1 now (wrong aircraft)
    # {"reg": "N400LV", ...  "Bernard Arnault" — Cessna XLS now
    # {"reg": "N17MS",  ...  "Michael Bloomberg" — Piper now
    # {"reg": "N350MC", ...  "Tom Cruise"     — King Air now
    # {"reg": "N7884B", ...  "Bezos secondary" — not in adsbdb
    # {"reg": "N68R",   ...  "Zuckerberg"     — not in adsbdb
    # {"reg": "N888GG", ...  "David Geffen"   — not in adsbdb
    # {"reg": "N521DS", ...  "Mark Cuban"     — not in adsbdb
    # {"reg": "N111ME", ...  "Mark Wahlberg"  — not in adsbdb
    # {"reg": "N28JL",  ...  "Jerry Jones"    — not in adsbdb

    # ───── Celebrities / Entertainment (each verified) ─────
    {"reg": "N898TS",  "expected_type": "Falcon", "label": "Taylor Swift's Falcon",                    "owner": "Taylor Swift",     "category": "celebrity",     "macro_tag": None},
    {"reg": "N621MM",  "expected_type": "Falcon", "label": "Taylor Swift's Falcon (secondary)",        "owner": "Taylor Swift",     "category": "celebrity",     "macro_tag": None},
    {"reg": "N767CJ",  "expected_type": "767",  "label": "Drake's Boeing 767-200 (Air Drake)",         "owner": "Drake",            "category": "celebrity",     "macro_tag": None},
    {"reg": "N1980K",  "expected_type": "G650", "label": "Kim Kardashian's Gulfstream G650ER",         "owner": "Kim Kardashian",   "category": "celebrity",     "macro_tag": None},
    # Re-added with attribution=journalism — generic management LLCs but well-documented in public reporting
    {"reg": "N1SF",    "expected_type": "Gulfstream", "attribution": "journalism", "label": "Steven Spielberg's Gulfstream",          "owner": "Steven Spielberg (via TVPX Trustee)",        "category": "celebrity", "macro_tag": None},
    {"reg": "N162JC",  "expected_type": "GV",       "attribution": "journalism",   "label": "Jim Carrey's Gulfstream V",              "owner": "Jim Carrey (via Trans-Exec Air Service)",    "category": "celebrity", "macro_tag": None},
    {"reg": "N777YJ",  "expected_type": "G550",     "attribution": "journalism",   "label": "Floyd Mayweather's Gulfstream G550",     "owner": "Floyd Mayweather (via L J Aviation)",        "category": "celebrity", "macro_tag": None},
    {"reg": "N713TS",  "expected_type": "Embraer",  "attribution": "named_shell",  "label": "Travis Scott's Embraer Lineage 1000",    "owner": "Travis Scott (Cactus Jack Airlines)",        "category": "celebrity", "macro_tag": None},
    {"reg": "N225TH",  "expected_type": "Citation", "attribution": "journalism",   "label": "Tom Hanks's Cessna Citation",            "owner": "Tom Hanks",                                  "category": "celebrity", "macro_tag": None},
    {"reg": "N521TP",  "expected_type": "Global",   "attribution": "journalism",   "label": "Tyler Perry's Bombardier Global 7500",   "owner": "Tyler Perry",                                "category": "celebrity", "macro_tag": None},
    {"reg": "N313MJ",  "expected_type": "Challenger","attribution": "journalism",  "label": "Jay-Z / Beyoncé Bombardier Challenger 850","owner": "Jay-Z & Beyoncé",                          "category": "celebrity", "macro_tag": None},
    {"reg": "N350TC",  "expected_type": "Gulfstream","attribution": "journalism",  "label": "Tom Cruise's Gulfstream",                 "owner": "Tom Cruise",                                 "category": "celebrity", "macro_tag": None},

    # ───── Heads of state / foreign ─────
    {"reg": "HZ-MF1",   "expected_type": "Boeing", "label": "Saudi King Boeing 737 BBJ",          "owner": "Saudi Government",      "category": "head_of_state", "macro_tag": "oil_gold"},
    {"reg": "A6-MMM",   "expected_type": "747",    "label": "UAE President's Boeing 747",         "owner": "UAE Presidential Flight","category": "head_of_state", "macro_tag": "oil_gold"},
    {"reg": "A7-HBJ",   "expected_type": "747",    "label": "Qatar Amiri Flight Boeing 747-8",    "owner": "Qatar Amiri Flight",    "category": "head_of_state", "macro_tag": "geopolitical"},

    # ───── Major G20 leader aircraft (publicly tracked, when they broadcast) ─────
    {"reg": "F-RARF",   "expected_type": "A330",   "label": "France Presidential A330 (Macron)",  "owner": "Armée de l'Air et de l'Espace", "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "10+01",    "expected_type": "A350",   "label": "German Chancellor A350-900 'Konrad Adenauer'", "owner": "German Air Force", "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "10+03",    "expected_type": "A350",   "label": "German Chancellor A350-900 (backup)", "owner": "German Air Force",      "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "ZZ336",    "expected_type": "Voyager","label": "RAF Vespina (UK PM/Royal Voyager)",  "owner": "Royal Air Force UK",    "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "80-1111",  "expected_type": "777",    "label": "Japan PM Boeing 777-300ER",          "owner": "Japan ASDF",             "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "80-1112",  "expected_type": "777",    "label": "Japan PM Boeing 777-300ER (backup)", "owner": "Japan ASDF",             "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "K7066",    "expected_type": "777",    "label": "India PM Boeing 777 'Air India One'","owner": "Indian Air Force",      "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "K7067",    "expected_type": "777",    "label": "India PM Boeing 777 (backup)",       "owner": "Indian Air Force",      "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "4X-ISR",   "expected_type": "767",    "label": "Israel PM Boeing 767 'Wing of Zion'","owner": "Israeli Air Force",     "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "TC-TUR",   "expected_type": "A330",   "label": "Turkey Presidential A330",           "owner": "Turkish Government",    "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "A39-001",  "expected_type": "A330",   "label": "Australia PM KC-30A (A330MRTT)",     "owner": "Royal Australian Air Force", "category": "head_of_state", "macro_tag": None},
    {"reg": "A39-005",  "expected_type": "BBJ",    "label": "Australia VIP Boeing 737 BBJ",        "owner": "Royal Australian Air Force", "category": "head_of_state", "macro_tag": None},
    # France presidential — alternative tail numbers
    {"reg": "F-RBPN",   "expected_type": "A330",   "label": "France Presidential A330",            "owner": "Armée de l'Air et de l'Espace", "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "F-UJCS",   "expected_type": "Falcon", "label": "France Presidential Falcon (COTAM)",  "owner": "Armée de l'Air et de l'Espace", "category": "head_of_state", "macro_tag": "geopolitical"},
    # UK Royal Family / RAF Voyager VIP
    {"reg": "G-XLEC",   "expected_type": "A321",   "label": "RAF UK Royal Airbus A321NX",          "owner": "Royal Air Force UK",    "category": "head_of_state", "macro_tag": "geopolitical"},
    # Vatican / Pope (uses ITA Airways flights, no fixed jet)
    # Mexico — sold the Dreamliner, but old reg
    {"reg": "TP-01",    "expected_type": "787",    "label": "Mexico Presidential B787 (TP-01)",   "owner": "Government of Mexico",  "category": "head_of_state", "macro_tag": None},

    # ───── Asian heads of state ─────
    {"reg": "10001",    "expected_type": "747",    "label": "South Korea Code One (B747-8 VIP)",  "owner": "Republic of Korea Air Force", "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "22001",    "expected_type": "737",    "label": "South Korea VIP B737",               "owner": "Republic of Korea Air Force", "category": "head_of_state", "macro_tag": None},
    {"reg": "A-001",    "expected_type": "BBJ",    "label": "Indonesia Presidential B737 BBJ",    "owner": "Indonesian Air Force",  "category": "head_of_state", "macro_tag": None},
    {"reg": "AP-BMS",   "expected_type": "737",    "label": "Pakistan PM B737 VIP",               "owner": "Pakistan Government",   "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "9V-SKA",   "expected_type": "777",    "label": "Singapore PM Boeing 777",            "owner": "Singapore Air Force",   "category": "head_of_state", "macro_tag": None},

    # ───── Middle East royals (separate from kings already seeded) ─────
    {"reg": "HZ-HM1",   "expected_type": "Boeing", "label": "Saudi Royal Boeing (older King)",    "owner": "Saudi Royal Flight",    "category": "head_of_state", "macro_tag": "oil_gold"},
    {"reg": "HZ-MS1",   "expected_type": "Gulfstream", "label": "Saudi MbS Crown Prince jet (alleged)", "owner": "Saudi Royal Court","category": "head_of_state", "macro_tag": "oil_gold"},
    {"reg": "A6-AUH",   "expected_type": "777",    "label": "UAE Abu Dhabi B777 (Crown Prince)",  "owner": "UAE Royal Flight",      "category": "head_of_state", "macro_tag": "oil_gold"},
    {"reg": "A6-COM",   "expected_type": "747",    "label": "Dubai Royal Boeing 747 (Sheikh Mohammed)", "owner": "Dubai Air Wing", "category": "head_of_state", "macro_tag": "oil_gold"},
    {"reg": "A6-DFR",   "expected_type": "Airbus", "label": "Dubai Royal A380 / ACJ",             "owner": "Dubai Air Wing",        "category": "head_of_state", "macro_tag": "oil_gold"},
    {"reg": "A7-HHM",   "expected_type": "Boeing", "label": "Qatar Emir Boeing 747-8 (Tamim)",    "owner": "Qatar Amiri Flight",    "category": "head_of_state", "macro_tag": "geopolitical"},

    # ───── Pope / Vatican (charter callsign Shepherd) ─────
    # Pope flies ITA Airways charter — no fixed tail. Track via callsign instead.

    # ───── Finance / Hedge fund managers ─────
    {"reg": "N757ES",  "expected_type": "757", "attribution": "journalism",  "label": "Eric Schmidt's Boeing 757",                 "owner": "Eric Schmidt (Google co-founder)",      "category": "billionaire", "macro_tag": None},
    {"reg": "N221SF",  "expected_type": "767", "attribution": "journalism",  "label": "Larry Page's Boeing 767",                   "owner": "Larry Page (Google co-founder)",        "category": "billionaire", "macro_tag": None},
    {"reg": "N20RZ",   "expected_type": "Gulfstream", "attribution": "journalism", "label": "George Soros's Gulfstream",           "owner": "George Soros (Soros Fund Mgmt)",        "category": "billionaire", "macro_tag": "geopolitical"},
    {"reg": "N318KG",  "expected_type": "Gulfstream", "attribution": "journalism", "label": "Ken Griffin's Gulfstream (Citadel)",  "owner": "Ken Griffin (Citadel)",                 "category": "billionaire", "macro_tag": None},
    {"reg": "N1NV",    "expected_type": "Gulfstream", "attribution": "journalism", "label": "Jensen Huang's Gulfstream (NVIDIA)",  "owner": "Jensen Huang (NVIDIA)",                 "category": "billionaire", "macro_tag": None},
    {"reg": "N777UP",  "expected_type": "Bombardier", "attribution": "journalism", "label": "Sergey Brin's Bombardier",            "owner": "Sergey Brin (Google co-founder)",       "category": "billionaire", "macro_tag": None},
    {"reg": "N86RP",   "expected_type": "Gulfstream", "attribution": "journalism", "label": "Ray Dalio's Gulfstream (Bridgewater)","owner": "Ray Dalio (Bridgewater Associates)",    "category": "billionaire", "macro_tag": "geopolitical"},

    # ───── International billionaires ─────
    {"reg": "VT-EVA",  "expected_type": "Falcon", "attribution": "journalism", "label": "Mukesh Ambani's Falcon (Reliance)",       "owner": "Mukesh Ambani (Reliance Industries)",  "category": "billionaire", "macro_tag": None},
    {"reg": "VP-BIG",  "expected_type": "Falcon", "attribution": "journalism", "label": "Indian billionaire Falcon (verify)",       "owner": "Indian billionaire",                    "category": "billionaire", "macro_tag": None},
    {"reg": "15001",    "expected_type": "CC-150", "label": "Canada PM CC-150 Polaris",           "owner": "Royal Canadian Air Force", "category": "head_of_state", "macro_tag": None},
    {"reg": "FAB2101",  "expected_type": "A319",   "label": "Brazil Presidential 'Aerolula'",     "owner": "Brazilian Air Force",   "category": "head_of_state", "macro_tag": None},

    # ───── Russia / China / Iran (rarely broadcast — try) ─────
    {"reg": "RA-96012", "expected_type": "Il-96",  "label": "Russian Presidential Il-96 (Putin transport)", "owner": "Special Flight Detachment Russia", "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "RA-96017", "expected_type": "Il-96",  "label": "Russian Presidential Il-96",         "owner": "Special Flight Detachment Russia", "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "B-2479",   "expected_type": "747",    "label": "China VIP Boeing 747",               "owner": "China Government",      "category": "head_of_state", "macro_tag": "geopolitical"},

    # ───── Thailand Royal/Government ─────
    {"reg": "HS-MVS",   "expected_type": "737",    "label": "Royal Thai B737-800 (VIP transport)","owner": "Royal Thai Air Force",  "category": "head_of_state", "macro_tag": None},
    {"reg": "HS-CMV",   "expected_type": "Airbus", "label": "Royal Thai Airbus ACJ (VIP)",        "owner": "Royal Thai Air Force",  "category": "head_of_state", "macro_tag": None},

    # ───── International billionaires ─────
    {"reg": "VT-RIL",   "expected_type": "Falcon", "label": "Mukesh Ambani's Falcon (Reliance)",  "owner": "Reliance Industries",   "category": "billionaire",   "macro_tag": None},
    {"reg": "VT-AMB",   "expected_type": "Falcon", "label": "Ambani family Falcon",               "owner": "Reliance Industries",   "category": "billionaire",   "macro_tag": None},
    {"reg": "M-KATE",   "expected_type": "Global", "label": "Abramovich's Bombardier (sanctioned)","owner": "Roman Abramovich",     "category": "sanctioned",    "macro_tag": "geopolitical"},
    {"reg": "VP-CRB",   "expected_type": "Falcon", "label": "Richard Branson's Falcon 900",       "owner": "Richard Branson (Virgin)", "category": "billionaire", "macro_tag": None},

    # ───── More celebrities (verified registrations) ─────
    {"reg": "N707JT",   "expected_type": "707",    "label": "John Travolta's Boeing 707",         "owner": "John Travolta",         "category": "celebrity",     "macro_tag": None},
    {"reg": "N728T",    "expected_type": "747",    "label": "John Travolta's Boeing 747",         "owner": "John Travolta",         "category": "celebrity",     "macro_tag": None},
    {"reg": "N521TP",   "expected_type": "Global", "label": "Tyler Perry's Bombardier Global 7500","owner": "Tyler Perry",          "category": "celebrity",     "macro_tag": None},
    {"reg": "N313MJ",   "expected_type": "Challenger", "label": "Jay-Z/Beyoncé Bombardier Challenger 850", "owner": "Jay-Z & Beyoncé", "category": "celebrity",   "macro_tag": None},

    # ───── 2026-05-22 expansion: gold-relevant gaps ─────
    # US Navy E-6B Mercury TACAMO — Navy doomsday plane, pairs with E-4B for nuclear command.
    # 16 airframes built (BuNo 162782-164410); active fleet ~14. Hex range usually AE0xxx.
    {"reg": "162782", "expected_type": "E-6", "label": "E-6B Mercury TACAMO (Navy doomsday)", "owner": "US Navy",                       "category": "us_strategic", "macro_tag": "risk_off"},
    {"reg": "162783", "expected_type": "E-6", "label": "E-6B Mercury TACAMO",                  "owner": "US Navy",                       "category": "us_strategic", "macro_tag": "risk_off"},
    {"reg": "162784", "expected_type": "E-6", "label": "E-6B Mercury TACAMO",                  "owner": "US Navy",                       "category": "us_strategic", "macro_tag": "risk_off"},
    {"reg": "163918", "expected_type": "E-6", "label": "E-6B Mercury TACAMO",                  "owner": "US Navy",                       "category": "us_strategic", "macro_tag": "risk_off"},
    {"reg": "163919", "expected_type": "E-6", "label": "E-6B Mercury TACAMO",                  "owner": "US Navy",                       "category": "us_strategic", "macro_tag": "risk_off"},
    {"reg": "164386", "expected_type": "E-6", "label": "E-6B Mercury TACAMO",                  "owner": "US Navy",                       "category": "us_strategic", "macro_tag": "risk_off"},
    {"reg": "164387", "expected_type": "E-6", "label": "E-6B Mercury TACAMO",                  "owner": "US Navy",                       "category": "us_strategic", "macro_tag": "risk_off"},
    {"reg": "164388", "expected_type": "E-6", "label": "E-6B Mercury TACAMO",                  "owner": "US Navy",                       "category": "us_strategic", "macro_tag": "risk_off"},
    {"reg": "164404", "expected_type": "E-6", "label": "E-6B Mercury TACAMO",                  "owner": "US Navy",                       "category": "us_strategic", "macro_tag": "risk_off"},
    {"reg": "164405", "expected_type": "E-6", "label": "E-6B Mercury TACAMO",                  "owner": "US Navy",                       "category": "us_strategic", "macro_tag": "risk_off"},
    {"reg": "164406", "expected_type": "E-6", "label": "E-6B Mercury TACAMO",                  "owner": "US Navy",                       "category": "us_strategic", "macro_tag": "risk_off"},
    {"reg": "164407", "expected_type": "E-6", "label": "E-6B Mercury TACAMO",                  "owner": "US Navy",                       "category": "us_strategic", "macro_tag": "risk_off"},
    {"reg": "164408", "expected_type": "E-6", "label": "E-6B Mercury TACAMO",                  "owner": "US Navy",                       "category": "us_strategic", "macro_tag": "risk_off"},
    {"reg": "164409", "expected_type": "E-6", "label": "E-6B Mercury TACAMO",                  "owner": "US Navy",                       "category": "us_strategic", "macro_tag": "risk_off"},
    {"reg": "164410", "expected_type": "E-6", "label": "E-6B Mercury TACAMO",                  "owner": "US Navy",                       "category": "us_strategic", "macro_tag": "risk_off"},

    # US C-32A (Secretary of State / VP transport) — 89th Airlift Wing
    {"reg": "98-0001", "expected_type": "C-32", "label": "C-32A SecState/VP (98-0001)",         "owner": "USAF 89th Airlift Wing",        "category": "us_strategic", "macro_tag": "geopolitical"},
    {"reg": "98-0002", "expected_type": "C-32", "label": "C-32A SecState/VP (98-0002)",         "owner": "USAF 89th Airlift Wing",        "category": "us_strategic", "macro_tag": "geopolitical"},
    {"reg": "99-0003", "expected_type": "C-32", "label": "C-32A SecState/VP (99-0003)",         "owner": "USAF 89th Airlift Wing",        "category": "us_strategic", "macro_tag": "geopolitical"},
    {"reg": "99-0004", "expected_type": "C-32", "label": "C-32A SecState/VP (99-0004)",         "owner": "USAF 89th Airlift Wing",        "category": "us_strategic", "macro_tag": "geopolitical"},

    # North Korea — Kim Jong Un Chammae-1 (rare broadcasts = major event)
    {"reg": "P-885",   "expected_type": "Il-62", "label": "Kim Jong Un's Chammae-1 (Il-62M)",  "owner": "DPRK Air Koryo",                "category": "head_of_state", "macro_tag": "geopolitical"},

    # Iran government — ASL Airlines / Iran Air Tour A321
    {"reg": "EP-IGD",  "expected_type": "A321",  "label": "Iran Government A321",              "owner": "Iran Government",               "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "EP-IGC",  "expected_type": "A321",  "label": "Iran Government A321 (backup)",     "owner": "Iran Government",               "category": "head_of_state", "macro_tag": "geopolitical"},

    # Russia — Putin backup jets (Falcon 7X / Il-96 variants beyond what we have)
    {"reg": "RA-96018","expected_type": "Il-96", "label": "Russian Presidential Il-96 (backup)","owner": "Special Flight Detachment Russia", "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "RA-96019","expected_type": "Il-96", "label": "Russian Presidential Il-96 (backup)","owner": "Special Flight Detachment Russia", "category": "head_of_state", "macro_tag": "geopolitical"},

    # China VIP — Xi Jinping aircraft (additional 747s)
    {"reg": "B-2472",  "expected_type": "747",   "label": "China VIP Boeing 747-400",          "owner": "Air China VIP / PLAAF",         "category": "head_of_state", "macro_tag": "geopolitical"},
    {"reg": "B-2473",  "expected_type": "747",   "label": "China VIP Boeing 747-400",          "owner": "Air China VIP / PLAAF",         "category": "head_of_state", "macro_tag": "geopolitical"},

    # Saudi Aramco corporate jets (oil → gold signal)
    {"reg": "HZ-AP1",  "expected_type": "BBJ",   "label": "Saudi Aramco BBJ corporate",        "owner": "Saudi Aramco",                  "category": "billionaire",   "macro_tag": "oil_gold"},
    {"reg": "HZ-AP2",  "expected_type": "BBJ",   "label": "Saudi Aramco BBJ corporate",        "owner": "Saudi Aramco",                  "category": "billionaire",   "macro_tag": "oil_gold"},
    {"reg": "HZ-AP3",  "expected_type": "BBJ",   "label": "Saudi Aramco BBJ corporate",        "owner": "Saudi Aramco",                  "category": "billionaire",   "macro_tag": "oil_gold"},

    # Finance — Blackstone Schwarzman, BlackRock Fink
    {"reg": "N100SS",  "expected_type": "Gulfstream", "attribution": "journalism", "label": "Stephen Schwarzman's Gulfstream",  "owner": "Stephen Schwarzman (Blackstone)", "category": "billionaire", "macro_tag": None},
    {"reg": "N500LF",  "expected_type": "Gulfstream", "attribution": "journalism", "label": "Larry Fink's Gulfstream (BlackRock)", "owner": "Larry Fink (BlackRock)",       "category": "billionaire", "macro_tag": None},
]


def main():
    adsbdb.init()
    wl_path = config.WATCHLIST_PATH
    wl = json.loads(wl_path.read_text(encoding="utf-8"))
    by_hex = wl.setdefault("by_hex", {})

    added = 0
    skipped_existing = 0
    failed = []

    type_mismatches = []
    for entry in SEED:
        reg = entry["reg"]
        expected_type = entry.get("expected_type", "")
        print(f"[seed] resolving {reg}...")
        ac = adsbdb.get_aircraft(reg)
        if not ac:
            print(f"  ✗ not found in adsbdb")
            failed.append(reg)
            continue
        hex_code = (ac.get("mode_s") or "").upper()
        if not hex_code:
            print(f"  ✗ no mode_s/hex returned")
            failed.append(reg)
            continue
        actual_type = f"{ac.get('manufacturer','')} {ac.get('type','')}".strip()
        if expected_type and expected_type.lower() not in actual_type.lower():
            print(f"  ⚠ TYPE MISMATCH: expected '{expected_type}', got '{actual_type}' — SKIPPING (likely re-registered to different aircraft)")
            type_mismatches.append((reg, expected_type, actual_type))
            continue
        if hex_code in by_hex:
            print(f"  · {hex_code} already in watchlist — skip")
            skipped_existing += 1
            continue
        by_hex[hex_code] = {
            "label": entry["label"],
            "owner": entry.get("owner", ac.get("registered_owner", "?")),
            "category": entry["category"],
            "macro_tag": entry.get("macro_tag"),
            "attribution": entry.get("attribution", "registered"),
            "notes": f"seeded from reg={reg} via adsbdb (verified type={actual_type}, registry_owner={ac.get('registered_owner','?')})",
        }
        print(f"  ✓ {hex_code} added ({actual_type})")
        added += 1

    wl_path.write_text(json.dumps(wl, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDone — added {added}, skipped {skipped_existing}, failed {len(failed)}, type-mismatches {len(type_mismatches)}")
    if failed:
        print("Failed:", ", ".join(failed))
    if type_mismatches:
        print("Type mismatches (review SEED entries):")
        for reg, exp, got in type_mismatches:
            print(f"  {reg}: expected={exp!r} got={got!r}")


if __name__ == "__main__":
    main()

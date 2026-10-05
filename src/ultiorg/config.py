"""Configuration constants for the Otso scraper."""

from pathlib import Path

# URL configuration
BASE_URL = "https://ultimate.fi/pelikone"

# Directory configuration
DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CACHE_FILE = DATA_DIR / "cache_manifest.json"
STORE_PATH = DATA_DIR / "store.sqlite"

# Human-asserted identity merges (canonical name -> canonical name). The library
# never merges two spellings on its own; this file is the only place a merge is
# asserted. See src/ultiorg/aliases.py.
ALIASES_PATH = Path("config") / "aliases.json"

# Request configuration
REQUEST_DELAY = 1.5  # seconds between requests to be respectful

# User agent for polite scraping
USER_AGENT = "Otso20v-Gaala-DataBot/1.0 (educational project, please be gentle)"

# Otso club-family team name patterns. Akatemia is a separate club, not Otso.
# Measured against the 795-game corpus: the gala site has always also counted
# "Hukka" and "Karhuvaarit" (Otso's other squad names). A pattern list without
# them silently drops those games — 13 players and their defense points move
# depending on which list is used. Phase 8 replaces this constant with the
# `teams.yaml` focus-team config; until then the two must stay equal.
OTSO_PATTERNS = [
    "otso",
    "grizzly",
    "polar",
    "hukka",
    "karhuvaarit",
]

# Division filter — only scrape Avoin/miehet division
OTSO_DIVISIONS = [
    "avoin",
    "miehet",
]

# Season classification
SEASON_TYPES = {
    "Kesä": "summer",
    "Talvi": "winter",
    "Tour 1": "tour",
    "Tour 2": "tour",
    "Tour 3": "tour",
    "Finaalit": "finals",
    "Finaali": "finals",
    "Ranta": "beach",
}

"""Configuration constants for the Otso scraper."""

from pathlib import Path

# URL configuration
BASE_URL = "https://ultimate.fi/pelikone"

# Directory configuration
DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CACHE_FILE = DATA_DIR / "cache_manifest.json"

# Request configuration
REQUEST_DELAY = 1.5  # seconds between requests to be respectful

# User agent for polite scraping
USER_AGENT = "Otso20v-Gaala-DataBot/1.0 (educational project, please be gentle)"

# Otso-specific team name patterns (Akatemia is a separate club, not Otso)
OTSO_PATTERNS = [
    "otso",
    "grizzly",
    "polar",
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

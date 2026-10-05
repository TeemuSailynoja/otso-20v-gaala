"""Where the data lives, and how politely to ask the server for it.

Nothing here names a club: which team the analytics are about comes from
`teams.yaml` in the consuming repo (`ultiorg.teams.load_focus_team`).
"""

from pathlib import Path

# URL configuration
BASE_URL = "https://ultimate.fi/pelikone"

# Directory configuration
DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
STORE_PATH = DATA_DIR / "store.sqlite"

# Human-asserted identity merges (canonical name -> canonical name). The library
# never merges two spellings on its own; this file is the only place a merge is
# asserted. See src/ultiorg/aliases.py.
ALIASES_PATH = Path("config") / "aliases.json"

# Request configuration
REQUEST_DELAY = 1.5  # seconds between requests to be respectful

# Identify yourself. A generic default so a library consumer is not pretending
# to be the gala project; the gala CLI overrides it.
USER_AGENT = "ultiorg/0.1 (polite data fetch for a Finnish ultimate database)"

# The instance is multi-lingual; season names are Finnish. Classification lives
# in `ultiorg.seasons`, not here.

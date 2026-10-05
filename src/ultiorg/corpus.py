"""The corpus: `data/processed/match_results.json`, recomposed instead of overwritten.

Why this is a verb and not a script. The old `--season X --gameplay` run wrote the
games it had just fetched straight over `match_results.json`, so fetching one
season replaced the 795-game corpus with that season's 24 games. Here a fetch adds
to the archive and the corpus is **recomposed** from every source that knows about
a game, so no fetch can clobber another season's work.

Three sources, newest wins for metadata, union for the set of games:

1. the corpus already on disk — the only place the 794 older `game_id → season_id`
   pairs survive, because the gameplay page's own `season=` menu link names the
   *current* season, not the game's (measured: `game_3418.html`, a 2019 game, links
   `season=KESA2026`);
2. `data/raw/<SEASON>.json` season parses — one file per season, so fetches do not
   collide;
3. every cached `view=games` page, parsed — what a re-fetch adds.

Gameplay is **re-parsed** from `data/raw/game_<id>.html` (or the page cache)
whenever that HTML is archived: the season files were written by older scrapers
whose point rows were doubled and whose passer/scorer fields were swapped, the
archived HTML is the source of truth, and `parse_gameplay` is the only parser with
the column order right. Re-parsing is offline, deterministic, idempotent.

When the HTML is **not** archived — which is the normal state of a fresh clone,
because `data/raw/` is gitignored and only the corpus is tracked — the corpus's own
point-by-point is carried forward rather than dropped. Without that rule
`ultiorg merge` on a fresh clone would erase 18,681 points, i.e. the only record of
them. `CorpusStats.gameplay_carried` says how much came from re-parsing and how
much was inherited.

The corpus is what `build_site_data.py` reads, so this module is what makes "a
fresh clone can regenerate everything" true.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .cache import Cache
from .config import BASE_URL
from .parsers import parse_gameplay, parse_games_list

#: metadata a games-list row carries; carried through to the corpus
GAME_METADATA_KEYS = ("time", "date", "venue", "division", "pool", "field")

#: key order written to disk, so a rebuild is byte-stable run to run
CANONICAL_KEYS = (
    "game_id", "season_id", "time", "date", "venue", "division", "pool", "field",
    "home_team", "away_team", "home_score", "away_score", "gameplay",
)


@dataclass
class CorpusStats:
    games: int = 0
    duplicates_dropped: int = 0
    gameplay_attached: int = 0
    gameplay_carried: int = 0
    gameplay_missing: int = 0
    points: int = 0
    points_expected: int = 0
    seasons: int = 0
    skipped_unarchived: int = 0
    sources: Dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"{self.games} games / {self.seasons} seasons "
            f"({self.duplicates_dropped} duplicate entries collapsed, "
            f"{self.skipped_unarchived} listed but not archived); "
            f"{self.gameplay_attached} re-parsed + {self.gameplay_carried} carried, "
            f"{self.points} points of {self.points_expected} expected, "
            f"{self.gameplay_missing} without gameplay"
        )


def _game_id_of(entry: Dict) -> str:
    return str(entry.get("game_id") or entry.get("id") or "").strip()


def _record(entry: Dict, season_id: str) -> Dict:
    # keep empty strings as-is: the corpus has `"division": ""` on hundreds of rows,
    # and dropping them would make a faithful rebuild look like a data change
    record = {k: entry.get(k) for k in GAME_METADATA_KEYS if entry.get(k) is not None}
    record["game_id"] = _game_id_of(entry)
    record["season_id"] = str(entry.get("season_id") or season_id or "")
    record["home_team"] = entry.get("home_team", "")
    record["away_team"] = entry.get("away_team", "")
    record["home_score"] = entry.get("home_score")
    record["away_score"] = entry.get("away_score")
    return record


def _merge_into(target: Dict, incoming: Dict) -> None:
    """Fill what `target` does not know; a newer scrape wins on conflicts."""
    for key, value in incoming.items():
        if key in ("game_id", "gameplay"):
            continue
        if value not in (None, ""):
            target[key] = value


def _from_corpus(path: Path) -> Dict[str, Dict]:
    if not path.exists():
        return {}
    out: Dict[str, Dict] = {}
    for entry in json.loads(path.read_text(encoding="utf-8")):
        game_id = _game_id_of(entry)
        if not game_id:
            continue
        record = _record(entry, entry.get("season_id", ""))
        # the corpus may hold fields a games-list row does not (e.g. a scraped date)
        for key, value in entry.items():
            if key not in ("gameplay", "game_id") and value not in (None, ""):
                record.setdefault(key, value)
        # carried forward only when no HTML is archived for this game (see below)
        gameplay = entry.get("gameplay")
        if isinstance(gameplay, dict):
            record["gameplay"] = gameplay
        out.setdefault(game_id, record)
    return out


def _from_season_files(raw_dir: Path) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    for path in sorted(raw_dir.glob("*.json")):
        try:
            season = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(season, dict):
            continue
        season_id = season.get("id", path.stem)
        for entry in season.get("games") or []:
            game_id = _game_id_of(entry)
            if game_id:
                out.setdefault(game_id, _record(entry, season_id))
    return out


def _from_cached_games_pages(cache: Cache) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    for entry in cache.entries():
        url = entry.get("url", "")
        if "view=games" not in url:
            continue
        season_id = ""
        for part in url.split("?", 1)[-1].split("&"):
            if part.startswith("season="):
                season_id = part.split("=", 1)[1]
        path = Path(entry["path"])
        if not path.exists():
            continue
        for game in parse_games_list(path.read_text(encoding="utf-8", errors="replace"), season_id):
            out.setdefault(_game_id_of(game), _record(game, season_id))
    return out


def gameplay_source(raw_dir: Path, data_dir: Path, game_id: str) -> Optional[Path]:
    """Where the archived HTML for one game lives: raw copy first, then cache."""
    raw = raw_dir / f"game_{game_id}.html"
    if raw.exists():
        return raw
    page = Cache(data_dir).stored(f"{BASE_URL}/?view=gameplay&game={game_id}")
    return page.path if page else None


def build_corpus(
    data_dir: Path = Path("data"),
    *,
    require_gameplay: bool = True,
) -> Tuple[List[Dict], CorpusStats]:
    """Recompose the game corpus from every source that knows about a game.

    `require_gameplay` keeps the corpus the *point-by-point* corpus: a game listed
    on a games page but not archived does not enter it, so fetching a season's
    games page cannot fill the corpus with games nobody scraped. A game already in
    the corpus is kept even with no archived HTML — never lose a recorded game.

    Point-by-point comes from the archived HTML when it exists, and from the corpus
    row when it does not. The corpus is tracked in git and `data/raw/` is not, so
    that second rule is what makes `merge` safe on a fresh clone.

    Deterministic: games are sorted by season ID then game ID, so two runs over the
    same archive produce byte-identical output.
    """
    raw_dir = data_dir / "raw"
    stats = CorpusStats()

    corpus_records = _from_corpus(data_dir / "processed" / "match_results.json")
    oldest_first = (
        ("corpus", corpus_records),
        ("season files", _from_season_files(raw_dir)),
        ("cached games pages", _from_cached_games_pages(Cache(data_dir))),
    )
    merged: Dict[str, Dict] = {}
    for name, source in oldest_first:
        stats.sources[name] = len(source)
        for game_id, record in source.items():
            if game_id in merged:
                stats.duplicates_dropped += 1
                _merge_into(merged[game_id], record)
            else:
                merged[game_id] = record

    games: List[Dict] = []
    for game_id in sorted(merged, key=lambda g: (merged[g]["season_id"] or "", int(g) if g.isdigit() else 0)):
        record = merged[game_id]
        source = gameplay_source(raw_dir, data_dir, game_id)
        carried = record.get("gameplay") if isinstance(record.get("gameplay"), dict) else None
        if source is None:
            if carried is not None:
                stats.gameplay_carried += 1
                stats.points += len([p for p in carried.get("points", []) if p.get("type") == "point"])
                stats.points_expected += int(carried.get("home_score") or 0) + int(carried.get("away_score") or 0)
            elif require_gameplay and game_id not in corpus_records:
                stats.skipped_unarchived += 1
                continue
            else:
                stats.gameplay_missing += 1
        else:
            gameplay = parse_gameplay(source.read_text(encoding="utf-8", errors="replace"))
            record["gameplay"] = gameplay
            stats.gameplay_attached += 1
            stats.points += len([p for p in gameplay.get("points", []) if p.get("type") == "point"])
            stats.points_expected += int(gameplay.get("home_score") or 0) + int(gameplay.get("away_score") or 0)
        games.append(record)
        stats.games += 1
        if record["season_id"]:
            stats.seasons += 1
    stats.seasons = len({g["season_id"] for g in games if g["season_id"]})
    return games, stats


def write_corpus(path: Path, games: List[Dict]) -> None:
    ordered = [
        {k: g[k] for k in CANONICAL_KEYS if k in g}
        | {k: v for k, v in g.items() if k not in CANONICAL_KEYS}
        for g in games
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False), encoding="utf-8")

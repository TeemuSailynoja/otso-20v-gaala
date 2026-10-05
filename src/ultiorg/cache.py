"""Per-URL page cache with a freshness policy per kind of page.

Layout (gitignored):

    data/cache/pages/<sha1(url)>.html   one file per fetched page
    data/cache/index.jsonl              append-only index: one JSON line per store

Why not the old shape: `data/cache_manifest.json` held every page's HTML in a
single 29 MB JSON document, and `fetch_url` rewrote that whole document after
**every** request — O(corpus) per request, unreadable by hand, and one corrupt
write loses the entire corpus. Here a hit is one file read and a store is one
file write plus one appended line.

Freshness is per kind of page, because the pages are not equally mutable:

| kind        | TTL              | why |
|-------------|------------------|-----|
| `immutable` | never expires    | finished games, past seasons, career cards |
| `live`      | 6 h              | the season currently being played |
| `index`     | 7 d              | season/player/team indexes: new rows only |

`--refresh` bypasses expiry for a single call.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, Optional

from .config import BASE_URL, DATA_DIR

POLICY_SECONDS: dict[str, Optional[float]] = {
    "immutable": None,
    "live": 6 * 3600,
    "index": 7 * 24 * 3600,
}

_YEAR_RE = re.compile(r"(19|20)\d{2}")


def cache_key(url: str) -> str:
    """Stable key for a URL (sha1; the old md5 keys are re-derived on import)."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def season_id_of(url: str) -> str:
    match = re.search(r"[?&]season=([^&]+)", url)
    return match.group(1) if match else ""


def is_current_season_id(season_id: str, today: Optional[datetime] = None) -> bool:
    """True if a season ID names the calendar year we are in.

    Season IDs are heterogeneous (`2018.1`, `KESA2026`, `Talvi2016`, `*JSM2018`),
    so the only robust signal is the four-digit year inside the ID. A season from
    the current year may still gain results, so it is `live`; anything older is
    history.
    """
    if not season_id:
        return False
    year = _YEAR_RE.search(season_id)
    if not year:
        return False
    return int(year.group(0)) >= (today or datetime.now()).year


def kind_for_url(url: str, today: Optional[datetime] = None) -> str:
    """Classify a page so its TTL matches how mutable it actually is."""
    if "view=ext/" in url:
        return "live"
    if any(v in url for v in ("view=allplayers", "view=seasonlist", "view=allteams", "view=allclubs")):
        return "index"
    if "view=gameplay" in url or "view=playercard" in url:
        return "immutable"
    season = season_id_of(url)
    if season:
        return "live" if is_current_season_id(season, today) else "immutable"
    return "index"


@dataclass
class CachedPage:
    url: str
    kind: str
    fetched_at: str
    expires: Optional[str]
    path: Path

    def is_fresh(self, now: Optional[datetime] = None) -> bool:
        if self.expires is None:
            return True
        now = now or datetime.now()
        try:
            return datetime.fromisoformat(self.expires) > now
        except ValueError:
            return False


class Cache:
    """Content-addressed page cache: one file per URL, append-only index."""

    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self.cache_dir = self.data_dir / "cache"
        self.pages_dir = self.cache_dir / "pages"
        self.index_path = self.cache_dir / "index.jsonl"
        self._index: dict[str, dict] = {}
        self._loaded = False

    # -- loading ------------------------------------------------------------

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.index_path.exists():
            return
        for line in self.index_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue  # a torn append must not lose the rest of the index
            self._index[entry["key"]] = entry

    # -- lookup / store -----------------------------------------------------

    def path_for(self, url: str) -> Path:
        return self.pages_dir / f"{cache_key(url)}.html"

    def lookup(self, url: str, refresh: bool = False, now: Optional[datetime] = None) -> Optional[CachedPage]:
        """Return a fresh cached page, or None if it must be fetched."""
        self.load()
        key = cache_key(url)
        entry = self._index.get(key)
        if not entry:
            return None
        path = Path(entry["path"])
        if not path.exists():
            return None
        page = CachedPage(
            url=entry["url"],
            kind=entry["kind"],
            fetched_at=entry["fetched_at"],
            expires=entry.get("expires"),
            path=path,
        )
        if refresh:
            return None
        if not page.is_fresh(now):
            return None
        return page

    def read(self, url: str, refresh: bool = False) -> Optional[str]:
        page = self.lookup(url, refresh=refresh)
        return page.path.read_text(encoding="utf-8", errors="replace") if page else None

    def store(
        self,
        url: str,
        content: str,
        kind: Optional[str] = None,
        fetched_at: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> CachedPage:
        self.load()
        kind = kind or kind_for_url(url, now)
        fetched_at = fetched_at or now or datetime.now()
        ttl = POLICY_SECONDS.get(kind, POLICY_SECONDS["index"])
        expires = (fetched_at + timedelta(seconds=ttl)).isoformat() if ttl else None

        self.pages_dir.mkdir(parents=True, exist_ok=True)
        path = self.path_for(url)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)

        entry = {
            "key": cache_key(url),
            "url": url,
            "kind": kind,
            "fetched_at": fetched_at.isoformat(),
            "expires": expires,
            "path": str(path),
            "bytes": len(content.encode("utf-8")),
        }
        self._index[entry["key"]] = entry
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return CachedPage(url=url, kind=kind, fetched_at=entry["fetched_at"], expires=expires, path=path)

    # -- inspection ---------------------------------------------------------

    def entries(self) -> Iterator[dict]:
        self.load()
        yield from self._index.values()

    def counts(self) -> dict:
        kinds: dict[str, int] = {}
        total_bytes = 0
        for entry in self.entries():
            kinds[entry["kind"]] = kinds.get(entry["kind"], 0) + 1
            total_bytes += entry.get("bytes", 0)
        return {"pages": len(self._index), "bytes": total_bytes, "by_kind": kinds}

    def compact(self) -> int:
        """Rewrite the index keeping only the newest entry per key."""
        self.load()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("w", encoding="utf-8") as fh:
            for entry in self._index.values():
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return len(self._index)

    # -- one-time migration -------------------------------------------------

    def import_manifest(self, manifest_path: Optional[Path] = None, dry_run: bool = False) -> dict:
        """Import the legacy `data/cache_manifest.json` into per-URL files.

        The manifest's pages are re-classified by URL rather than trusting its
        `expires` values: importing must not mark a stale page fresh, and must
        not expire history that is in fact immutable. Re-running is a no-op for
        pages already present.
        """
        manifest_path = manifest_path or (self.data_dir / "cache_manifest.json")
        if not manifest_path.exists():
            return {"imported": 0, "skipped": 0, "error": f"no manifest at {manifest_path}"}

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        urls = manifest.get("urls", {})
        imported = skipped = 0
        self.load()
        for key, entry in urls.items():
            url = entry.get("url")
            content = entry.get("content")
            if not url or content is None:
                skipped += 1
                continue
            if cache_key(url) in self._index and self.path_for(url).exists():
                skipped += 1
                continue
            if dry_run:
                imported += 1
                continue
            kind = kind_for_url(url)
            self.store(url, content, kind=kind)
            imported += 1
        return {"imported": imported, "skipped": skipped, "manifest_urls": len(urls)}

    def import_raw_html(self, raw_dir: Optional[Path] = None, base_url: str = BASE_URL, dry_run: bool = False) -> dict:
        """Import `data/raw/game_<id>.html` files as cached gameplay pages.

        Some archived game pages predate the manifest and exist only as files, so
        without this a rebuild would re-request them. The URL is derived from the
        filename, which is exactly how the scraper named them.
        """
        raw_dir = Path(raw_dir or (self.data_dir / "raw"))
        imported = skipped = 0
        self.load()
        for path in sorted(raw_dir.glob("game_*.html")):
            game_id = path.stem.replace("game_", "")
            url = f"{base_url}/?view=gameplay&game={game_id}"
            if cache_key(url) in self._index and self.path_for(url).exists():
                skipped += 1
                continue
            if dry_run:
                imported += 1
                continue
            self.store(url, path.read_text(encoding="utf-8", errors="replace"), kind="immutable")
            imported += 1
        return {"imported": imported, "skipped": skipped}


def setup_dirs(data_dir: Path = DATA_DIR) -> None:
    """Create the data directories the pipeline writes into."""
    data_dir.mkdir(exist_ok=True)
    (data_dir / "raw").mkdir(exist_ok=True)
    (data_dir / "processed").mkdir(exist_ok=True)
    (data_dir / "cache" / "pages").mkdir(parents=True, exist_ok=True)

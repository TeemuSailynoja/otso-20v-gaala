"""Cache: per-URL files, per-kind freshness, and the one-time imports.

The corpus gate lives here: after importing, every URL the pipeline would ask
for must already be on disk, so a rebuild costs zero requests.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ultiorg import cache as cachemod
from ultiorg.cache import Cache, cache_key, kind_for_url, is_current_season_id
from ultiorg.config import BASE_URL, DATA_DIR

PELIKONE = "https://ultimate.fi/pelikone"


# --- freshness policy -------------------------------------------------------


@pytest.mark.parametrize(
    "url,kind",
    [
        (f"{PELIKONE}/?view=gameplay&game=11049", "immutable"),
        (f"{PELIKONE}/?view=playercard&series=0&player=27441", "immutable"),
        (f"{PELIKONE}/?view=teams&season=2018.1&list=allteams", "immutable"),
        (f"{PELIKONE}/?view=games&season=KESA2025&filter=tournaments&group=all", "immutable"),
        (f"{PELIKONE}/?view=teams&season=KESA2026&list=allteams", "live"),
        (f"{PELIKONE}/?view=allplayers", "index"),
        (f"{PELIKONE}/?view=seasonlist", "index"),
        (f"{PELIKONE}/?view=allclubs", "index"),
        (f"{PELIKONE}/?view=ext/playerscsv.php&season=KESA2026", "live"),
        (f"{PELIKONE}/?view=teamcard&team=3130", "index"),
    ],
)
def test_kind_for_url(url, kind):
    assert kind_for_url(url) == kind


def test_current_season_uses_the_year_inside_a_heterogeneous_id():
    today = datetime(2026, 10, 5)
    assert is_current_season_id("KESA2026", today)
    assert is_current_season_id("2026.3", today)
    assert not is_current_season_id("KESA2025", today)
    assert not is_current_season_id("Talvi2016", today)
    assert not is_current_season_id("*JSM2018", today)
    assert not is_current_season_id("", today)


def test_immutable_pages_never_expire(tmp_path):
    cache = Cache(tmp_path)
    url = f"{PELIKONE}/?view=gameplay&game=1"
    cache.store(url, "<html>x</html>")
    far_future = datetime.now() + timedelta(days=3650)
    page = cache.lookup(url, now=far_future)
    assert page is not None and page.kind == "immutable" and page.expires is None


def test_live_pages_expire_and_refresh_bypasses_the_cache(tmp_path):
    cache = Cache(tmp_path)
    url = f"{PELIKONE}/?view=teams&season=KESA2026&list=allteams"
    cache.store(url, "old", fetched_at=datetime.now() - timedelta(hours=7))
    assert cache.lookup(url) is None  # 6h TTL has passed
    assert cache.read(url) is None
    assert cache.lookup(url, refresh=True) is None


def test_index_pages_survive_six_hours_but_not_a_month(tmp_path):
    cache = Cache(tmp_path)
    url = f"{PELIKONE}/?view=allplayers"
    cache.store(url, "index", fetched_at=datetime.now() - timedelta(hours=6, minutes=1))
    assert cache.lookup(url) is not None
    stale = Cache(tmp_path)
    stale.store(url, "index", fetched_at=datetime.now() - timedelta(days=30))
    assert stale.lookup(url) is None


# --- storage shape ----------------------------------------------------------


def test_one_file_per_url_and_an_append_only_index(tmp_path):
    cache = Cache(tmp_path)
    url_a = f"{PELIKONE}/?view=gameplay&game=1"
    url_b = f"{PELIKONE}/?view=gameplay&game=2"
    cache.store(url_a, "A")
    cache.store(url_b, "B")
    cache.store(url_a, "A2")  # re-fetch: newest wins

    assert cache.path_for(url_a).read_text() == "A2"
    lines = cache.index_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3, "stores append; they do not rewrite the index"
    reloaded = Cache(tmp_path)
    assert reloaded.read(url_a) == "A2"
    assert reloaded.counts()["pages"] == 2


def test_a_torn_index_line_does_not_lose_the_rest(tmp_path):
    cache = Cache(tmp_path)
    url = f"{PELIKONE}/?view=gameplay&game=1"
    cache.store(url, "A")
    with cache.index_path.open("a", encoding="utf-8") as fh:
        fh.write('{"key": "trunc')
    assert Cache(tmp_path).read(url) == "A"


def test_compaction_keeps_the_newest_entry(tmp_path):
    cache = Cache(tmp_path)
    url = f"{PELIKONE}/?view=gameplay&game=1"
    cache.store(url, "A")
    cache.store(url, "B")
    assert cache.compact() == 1
    assert len(cache.index_path.read_text(encoding="utf-8").splitlines()) == 1
    assert Cache(tmp_path).read(url) == "B"


# --- one-time imports -------------------------------------------------------


def test_import_manifest_is_idempotent_and_reclassifies(tmp_path):
    manifest = tmp_path / "cache_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "urls": {
                    "k1": {
                        "url": f"{PELIKONE}/?view=gameplay&game=7",
                        "content": "<html>game</html>",
                        "expires": "2020-01-01T00:00:00",  # stale in the old shape
                    },
                    "k2": {"url": f"{PELIKONE}/?view=allplayers", "content": "<html>idx</html>"},
                    "k3": {"url": "no-content-here"},
                }
            }
        ),
        encoding="utf-8",
    )
    cache = Cache(tmp_path / "data")
    result = cache.import_manifest(manifest)
    assert result == {"imported": 2, "skipped": 1, "manifest_urls": 3}
    # an old `expires` must not make history look stale
    assert cache.read(f"{PELIKONE}/?view=gameplay&game=7") == "<html>game</html>"
    assert cache.read(f"{PELIKONE}/?view=allplayers") == "<html>idx</html>"
    assert cache.import_manifest(manifest) == {"imported": 0, "skipped": 3, "manifest_urls": 3}


def test_import_manifest_dry_run_writes_nothing(tmp_path):
    manifest = tmp_path / "cache_manifest.json"
    manifest.write_text(json.dumps({"urls": {"k": {"url": f"{PELIKONE}/?view=allplayers", "content": "x"}}}), encoding="utf-8")
    cache = Cache(tmp_path / "data")
    assert cache.import_manifest(manifest, dry_run=True)["imported"] == 1
    assert not cache.index_path.exists()


def test_import_raw_html_derives_the_gameplay_url(tmp_path):
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    (raw / "game_42.html").write_text("<html>42</html>", encoding="utf-8")
    cache = Cache(tmp_path / "data")
    assert cache.import_raw_html()["imported"] == 1
    url = f"{BASE_URL}/?view=gameplay&game=42"
    assert cache.read(url) == "<html>42</html>"
    assert cache.lookup(url).kind == "immutable"
    assert cache.import_raw_html()["skipped"] == 1


# --- the corpus gate --------------------------------------------------------

REAL_INDEX = DATA_DIR / "cache" / "index.jsonl"


@pytest.mark.skipif(not REAL_INDEX.exists(), reason="cache not imported yet")
def test_every_archived_game_page_is_a_cache_hit():
    """The Phase 3 gate: rebuilding the site must cost zero requests.

    Every `data/raw/game_<id>.html` and every URL in the legacy manifest resolves
    to a fresh cached file, so `fetch_gameplay` for any archived game is a hit.
    """
    cache = Cache(DATA_DIR)
    game_ids = {p.stem.replace("game_", "") for p in (DATA_DIR / "raw").glob("game_*.html")}
    assert game_ids, "no archived game pages"
    misses = [gid for gid in game_ids if cache.read(f"{BASE_URL}/?view=gameplay&game={gid}") is None]
    assert misses == [], f"{len(misses)} of {len(game_ids)} game pages would be re-fetched"

    manifest = DATA_DIR / "cache_manifest.json"
    if manifest.exists():
        urls = [e["url"] for e in json.loads(manifest.read_text(encoding="utf-8"))["urls"].values() if e.get("content")]
        stale = [u for u in urls if cache.read(u) is None]
        assert stale == [], f"{len(stale)} of {len(urls)} manifest pages would be re-fetched"


@pytest.mark.skipif(not REAL_INDEX.exists(), reason="cache not imported yet")
def test_cache_holds_the_corpus_in_per_url_files():
    counts = Cache(DATA_DIR).counts()
    assert counts["pages"] >= 967
    assert counts["by_kind"]["immutable"] >= 790

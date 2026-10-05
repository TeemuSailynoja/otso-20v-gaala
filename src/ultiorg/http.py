"""HTTP for pelikone: one politeness budget per instance, and a request counter.

The site is a small self-hosted PHP app (`Ultiorganizer`) serving an entire
national league. Everything here exists to keep the crawl boring: a minimum
spacing between network requests, bounded retries with backoff, no retry on a
403 (that is a policy answer, not a transient one), and a counter so every
command can say how much traffic it actually caused.

Cache hits cost nothing and never sleep — politeness is about requests, not
about loops.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from .cache import Cache, setup_dirs
from .config import BASE_URL, DATA_DIR, REQUEST_DELAY, USER_AGENT


@dataclass
class FetchStats:
    cache_hits: int = 0
    requests: int = 0
    errors: int = 0
    dry_run: int = 0
    retried: int = 0

    def as_dict(self) -> dict:
        return {
            "cache_hits": self.cache_hits,
            "requests": self.requests,
            "errors": self.errors,
            "dry_run": self.dry_run,
            "retried": self.retried,
        }

    def summary(self) -> str:
        return (
            f"cache hits {self.cache_hits} | network requests {self.requests} | "
            f"retried {self.retried} | errors {self.errors} | dry-run skips {self.dry_run}"
        )


@dataclass
class Fetcher:
    """Cache-aware fetcher with a single delay budget per instance."""

    base_url: str = BASE_URL
    data_dir: Path = DATA_DIR
    delay: float = REQUEST_DELAY
    refresh: bool = False
    dry_run: bool = False
    verbose: bool = True
    timeout: float = 30.0
    max_attempts: int = 3
    user_agent: str = USER_AGENT
    cache: Cache = field(init=False)
    stats: FetchStats = field(default_factory=FetchStats)

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        setup_dirs(self.data_dir)
        self.cache = Cache(self.data_dir)
        self._last_request: float = 0.0
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self.user_agent})

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message)

    def _space_out_requests(self) -> None:
        """Sleep only the time still needed to keep `delay` between requests."""
        wait = self.delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)

    def get(self, url: str, kind: Optional[str] = None) -> Optional[str]:
        """Return page HTML from cache, or fetch it; None if unavailable."""
        cached = self.cache.read(url, refresh=self.refresh)
        if cached is not None:
            self.stats.cache_hits += 1
            self._log(f"  [CACHE] {url[:80]}")
            return cached

        if self.dry_run:
            self.stats.dry_run += 1
            self._log(f"  [DRY-RUN] would fetch {url}")
            return None

        self._log(f"  [FETCH] {url[:80]}")
        for attempt in range(1, self.max_attempts + 1):
            self._space_out_requests()
            self._last_request = time.monotonic()
            try:
                response = self._session.get(url, timeout=self.timeout)
                self.stats.requests += 1
                if response.status_code == 403:
                    # "Event is not available for external access" — permanent.
                    self.stats.errors += 1
                    self._log(f"  [403] {url}")
                    return None
                response.raise_for_status()
                self.cache.store(url, response.text, kind=kind)
                return response.text
            except requests.RequestException as exc:
                if attempt < self.max_attempts:
                    self.stats.retried += 1
                    backoff = 2.0**attempt
                    self._log(f"  [RETRY {attempt}] {url}: {exc} (sleep {backoff:.0f}s)")
                    time.sleep(backoff)
                else:
                    self.stats.errors += 1
                    self._log(f"  [ERROR] {url}: {exc}")
                    return None
        return None


_DEFAULT: Optional[Fetcher] = None


def configure(**kwargs) -> Fetcher:
    """Set the process-wide fetcher (data dir, refresh, dry-run, delay)."""
    global _DEFAULT
    _DEFAULT = Fetcher(**kwargs)
    return _DEFAULT


def get_fetcher(**kwargs) -> Fetcher:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Fetcher(**kwargs)
    return _DEFAULT


def fetch_url(url: str, kind: Optional[str] = None, fetcher: Optional[Fetcher] = None) -> Optional[str]:
    return (fetcher or get_fetcher()).get(url, kind=kind)

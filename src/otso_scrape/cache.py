"""Caching logic for scraped data."""

import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

from .config import CACHE_FILE


def get_cache(data_dir: Path = CACHE_FILE.parent) -> dict:
    """Load the cache manifest.
    
    Args:
        data_dir: Directory containing the cache file.
        
    Returns:
        Cache dictionary with URLs and metadata.
    """
    cache_file = data_dir / "cache_manifest.json"
    if cache_file.exists():
        with open(cache_file, "r") as f:
            return json.load(f)
    return {"last_updated": None, "seasons": {}, "teams": {}, "players": {}}


def save_cache(cache: dict, data_dir: Path = CACHE_FILE.parent) -> None:
    """Save the cache manifest.
    
    Args:
        cache: Cache dictionary to save.
        data_dir: Directory to save the cache file to.
    """
    cache_file = data_dir / "cache_manifest.json"
    cache["last_updated"] = datetime.now().isoformat()
    with open(cache_file, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def cache_key(url: str) -> str:
    """Generate a cache key from a URL.
    
    Args:
        url: URL to generate a cache key for.
        
    Returns:
        MD5 hash of the URL.
    """
    return hashlib.md5(url.encode()).hexdigest()


def is_cache_valid(cached_entry: dict) -> bool:
    """Check if a cached entry is still valid.
    
    Args:
        cached_entry: Cached entry with 'expires' field.
        
    Returns:
        True if the cache entry is still valid.
    """
    expires = cached_entry.get("expires", "")
    return expires > datetime.now().isoformat()


def setup_dirs(data_dir: Path = CACHE_FILE.parent) -> None:
    """Create necessary directories.
    
    Args:
        data_dir: Root data directory.
    """
    data_dir.mkdir(exist_ok=True)
    (data_dir / "raw").mkdir(exist_ok=True)
    (data_dir / "processed").mkdir(exist_ok=True)

#!/usr/bin/env python3
"""Scrape all Otso game HTML pages from pelikone.

Usage:
    python scrape_all_games.py          # Scrape all missing games (uses cache)
    python scrape_all_games.py --force  # Force re-download all games
    python scrape_all_games.py --list   # List games to be scraped

Respects the page: 1.5s delay between requests, polite user-agent, caching.
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from otso_scrape.fetcher import fetch_gameplay
from otso_scrape.config import BASE_URL, RAW_DIR


def get_all_game_ids():
    """Get all game IDs from match_results.json."""
    match_results = json.load(open(Path("data/processed/match_results.json")))
    return sorted(set(
        str(g.get("game_id", ""))
        for g in match_results
        if g.get("game_id")
    ))


def get_existing_html_ids():
    """Get game IDs that already have HTML files."""
    return {
        f.stem.replace("game_", "")
        for f in RAW_DIR.glob("game_*.html")
    }


def scrape_game(game_id: str, force: bool = False) -> bool:
    """Scrape a single game's HTML page.
    
    Returns True if successful.
    """
    html = fetch_gameplay(game_id, data_dir=Path("data"))
    
    if html is None:
        print(f"  [FAILED] {game_id}")
        return False
    
    # Save HTML file
    html_file = RAW_DIR / f"game_{game_id}.html"
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"  [OK] {game_id} ({len(html)} bytes)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Scrape all Otso game HTML pages")
    parser.add_argument("--force", action="store_true", help="Force re-download all games")
    parser.add_argument("--list", action="store_true", help="List games to be scraped")
    args = parser.parse_args()
    
    # Ensure data/raw exists
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    # Get all game IDs
    all_ids = get_all_game_ids()
    existing_ids = get_existing_html_ids()
    missing_ids = sorted(set(all_ids) - existing_ids)
    
    print(f"Total games in match_results.json: {len(all_ids)}")
    print(f"Existing HTML files: {len(existing_ids)}")
    print(f"Missing HTML files: {len(missing_ids)}")
    
    if args.list:
        print(f"\nGames to scrape ({len(missing_ids)}):")
        for gid in missing_ids:
            print(f"  {gid}")
        return
    
    if not missing_ids:
        print("All games already scraped!")
        return
    
    # Scrape missing games
    print(f"\nScraping {len(missing_ids)} games...")
    print(f"Rate limit: 1.5s between requests (~{len(missing_ids) * 1.5 / 60:.1f} min total)")
    print(f"User-Agent: Otso20v-Gaala-DataBot/1.0 (educational project, please be gentle)")
    print()
    
    success = 0
    failed = 0
    
    for i, game_id in enumerate(missing_ids, 1):
        if i % 50 == 0:
            print(f"\n  Progress: {i}/{len(missing_ids)} ({success} ok, {failed} failed)")
        
        if scrape_game(game_id, force=args.force):
            success += 1
        else:
            failed += 1
    
    print(f"\n{'='*60}")
    print(f"Done! {success} games scraped, {failed} failed")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

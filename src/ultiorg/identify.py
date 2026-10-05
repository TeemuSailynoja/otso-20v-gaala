"""Names are not keys. This module turns names into player IDs — and records
every place it had to guess or failed.

Why this exists: point-by-point rows carry **no player IDs**. A goal is the
plain text `"Potrykus Patrick -> Arola Matias"`, i.e. `Last First`, while
rosters and the player index are `First Last` separated by U+00A0. The only
join between a point and a player is a name, so the name rule has to be
explicit, order-insensitive, and honest about ambiguity.

The rule is the one `refresh_game_rosters.py` used in production: fold NBSP to
a space, drop captain markers, lowercase, and sort the name parts — which makes
`Last First` and `First Last` the same key.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .parsers import parse_gameplay

_CAPTION_RE = re.compile(r"\((?:c|C)\)")


def canon(name: str) -> str:
    """Canonical name key: NBSP folded, captain marks dropped, parts sorted.

    Sorting the parts is what makes the rule order-insensitive: point rows write
    `Last First`, rosters and the player index write `First Last`.
    """
    if not name:
        return ""
    cleaned = _CAPTION_RE.sub(" ", name.replace("\xa0", " "))
    parts = [p.lower() for p in cleaned.split() if p]
    return " ".join(sorted(parts))


def pseudo_key(name: str) -> str:
    """Key for a name that never resolved to a player ID.

    Points keyed this way are still counted — they just are not attributable to
    a person. They show up in `data_quality.json` instead of vanishing.
    """
    return f"name:{canon(name)}"


@dataclass
class Resolution:
    name: str
    player_id: Optional[str]
    via: str  # canon | ambiguous | blank-index | none
    candidates: List[str] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.player_id is not None


class PlayerIndex:
    """The name -> player_id map, built from `?view=allplayers&list=all`."""

    def __init__(self, players: Iterable[Dict]):
        self.byId: Dict[str, str] = {}
        self._by_canon: Dict[str, List[str]] = defaultdict(list)
        self.blank_ids: List[str] = []
        for row in players:
            player_id = str(row.get("id", ""))
            name = row.get("name", "") or ""
            if not player_id:
                continue
            self.byId[player_id] = name
            if not name.strip():
                self.blank_ids.append(player_id)
                continue
            key = canon(name)
            if player_id not in self._by_canon[key]:
                self._by_canon[key].append(player_id)

    @property
    def size(self) -> int:
        return len(self.byId)

    def ambiguous(self) -> Dict[str, List[str]]:
        """Canonical names that map to more than one player ID."""
        return {key: ids for key, ids in self._by_canon.items() if len(ids) > 1}

    def name_of(self, player_id: str) -> str:
        return self.byId.get(str(player_id), "")

    def resolve(self, name: str) -> Resolution:
        key = canon(name)
        if not key:
            return Resolution(name=name, player_id=None, via="none")
        ids = self._by_canon.get(key, [])
        if len(ids) == 1:
            return Resolution(name=name, player_id=ids[0], via="canon")
        if len(ids) > 1:
            return Resolution(name=name, player_id=None, via="ambiguous", candidates=list(ids))
        return Resolution(name=name, player_id=None, via="none")

    def resolve_all(self, names: Iterable[str]) -> Dict[str, Resolution]:
        return {name: self.resolve(name) for name in names}


@dataclass
class DataQuality:
    """What the pipeline could not attribute, counted rather than hidden."""

    unresolved_names: Counter = field(default_factory=Counter)
    ambiguous_names: Dict[str, List[str]] = field(default_factory=dict)
    index_blank_names: List[str] = field(default_factory=list)
    roster_ids_not_in_index: Counter = field(default_factory=Counter)

    def as_dict(self) -> dict:
        return {
            "unresolved_names": dict(self.unresolved_names.most_common()),
            "unresolved_distinct_names": len(self.unresolved_names),
            "unresolved_points": sum(self.unresolved_names.values()),
            "ambiguous_names": self.ambiguous_names,
            "index_blank_names": self.index_blank_names,
            "roster_ids_not_in_index": dict(self.roster_ids_not_in_index.most_common()),
        }


def recover_rosters(raw_dir: Path, index: Optional[PlayerIndex] = None) -> dict:
    """Recover per-game rosters with player IDs from archived HTML — no requests.

    Every archived gameplay page carries `playercard&...&player=<id>` links for
    its roster (measured: 795 of 795), so the whole corpus can be re-keyed to
    player IDs offline. Returns `{game_id: {home_team, away_team, home, away}}`
    plus coverage counts.
    """
    rosters: Dict[str, dict] = {}
    quality = DataQuality()
    if index is not None:
        quality.index_blank_names = list(index.blank_ids)
        quality.ambiguous_names = index.ambiguous()

    players_with_ids = players_without_ids = 0
    for path in sorted(Path(raw_dir).glob("game_*.html")):
        game_id = path.stem.replace("game_", "")
        gameplay = parse_gameplay(path.read_text(encoding="utf-8", errors="replace"))
        sides = {}
        for side_key, players in (("home", gameplay["home_players"]), ("away", gameplay["away_players"])):
            entries = []
            for player in players:
                player_id = player.get("id", "")
                if player_id:
                    players_with_ids += 1
                    if index is not None and not index.name_of(player_id):
                        # A real ID that the player index does not list: keep the
                        # entry, report the gap.
                        quality.roster_ids_not_in_index[player["name"]] += 1
                else:
                    players_without_ids += 1
                entries.append({"id": player_id, "name": player["name"]})
            sides[side_key] = entries
        rosters[game_id] = {
            "home_team": gameplay["home_team"],
            "away_team": gameplay["away_team"],
            "home": sides["home"],
            "away": sides["away"],
        }

    return {
        "rosters": rosters,
        "games": len(rosters),
        "roster_entries_with_ids": players_with_ids,
        "roster_entries_without_ids": players_without_ids,
        "quality": quality,
    }

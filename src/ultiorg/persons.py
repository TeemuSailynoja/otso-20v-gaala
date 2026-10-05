"""Stable site keys for people.

pelikone mints a **new player id for every registration**, so a person is a
cluster of ids, not an id: measured on the archived corpus, 904 distinct roster
names carry 6,175 distinct roster ids, and one long-career player holds 69.

That makes "key the site data by player id" a statement about clusters. The key
this module mints is:

* the **lowest pelikone id** in the person's cluster when one is known — a real
  id, clickable through to a pelikone player card, and stable across rebuilds
  because a new scrape can only add ids above it (a smaller id appearing later
  means the cluster grew, which is a fact worth seeing in `data_quality.json`);
* otherwise `name:<canon>` — the pseudo-key the store already uses, so a point
  whose name joins no roster still has a place to be counted and is *listed* in
  the quality report instead of vanishing from the totals.

Two things this deliberately does not do: it does not merge people (only
`config/aliases.json` asserts that a spelling is a known person), and it does not
invent ids for names pelikone never registered.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from .aliases import PersonKeys
from .identify import canon

#: Prefix on a key minted from a name rather than a pelikone id.
PSEUDO_PREFIX = "name:"

#: Values that appear in a point row's passer cell but name nobody.
#:
#: "Callahan-maali" is pelikone's label for a Callahan — an interception caught
#: in the offensive end zone, which scores. The scorer cell names the player; the
#: passer cell names the *event*. Treating it as a person would invent a player
#: with 67 assists.
NON_PERSON_MARKERS = frozenset({"callahan-maali"})


def is_person(name: str) -> bool:
    """Is this cell a person, or a label the scrape copied out of the table?"""
    text = canon(name)
    return bool(text) and text not in NON_PERSON_MARKERS


def _id_sort(player_id: str) -> Tuple[int, int, str]:
    """Numeric ids sort numerically: `999` is older (lower) than `1000`."""
    text = str(player_id)
    return (0, int(text), "") if text.isdigit() else (1, 0, text)


def collect_id_clusters(
    games: Iterable[Mapping],
    seasons: Iterable[Mapping] = (),
    persons: Optional[PersonKeys] = None,
) -> Dict[str, set]:
    """person key -> the pelikone player ids that roster cell ever used for them.

    Roster cells are the only place pelikone writes an id: season cards
    (`season["teams"][i]["players"]`) and a game's `home_players` /
    `away_players`. Point rows carry plain text names, which is why identity has
    to be built from rosters and then applied to points.
    """
    resolve = (persons or PersonKeys()).resolve
    clusters: Dict[str, set] = defaultdict(set)

    for game in games:
        gameplay = game.get("gameplay") or {}
        for cell in ("home_players", "away_players"):
            for row in gameplay.get(cell, []) or []:
                player_id = str(row.get("id") or "")
                person = resolve(row.get("name", ""))
                if person and player_id:
                    clusters[person].add(player_id)

    for season in seasons:
        for team in season.get("teams", []) or []:
            for row in team.get("players", []) or []:
                player_id = str(row.get("id") or "")
                person = resolve(row.get("name", ""))
                if person and player_id:
                    clusters[person].add(player_id)

    return dict(clusters)


@dataclass(frozen=True)
class PersonIds:
    """One key per person, plus the display name that key renders as."""

    #: person key -> every pelikone id known for that person, lowest first
    clusters: Mapping[str, Tuple[str, ...]]
    #: person key -> the site key (lowest id, or `name:<canon>`)
    key_of: Mapping[str, str]
    #: site key -> display name, for `names.json`
    display_of: Mapping[str, str]

    @classmethod
    def build(
        cls,
        clusters: Mapping[str, Iterable[str]],
        displays: Mapping[str, str],
    ) -> "PersonIds":
        frozen = {
            person: tuple(sorted(set(ids), key=_id_sort))
            for person, ids in clusters.items()
        }
        keys = {
            person: (ids[0] if ids else PSEUDO_PREFIX + person)
            for person, ids in frozen.items()
        }
        display_of: Dict[str, str] = {}
        for person, site_key in keys.items():
            name = displays.get(person) or ""
            if name:
                display_of[site_key] = name
        return cls(clusters=frozen, key_of=keys, display_of=display_of)

    def site_key(self, person_key: str) -> str:
        """The key for a person, minting a pseudo-key if they are unknown.

        Minting rather than dropping is the rule: a name that appears in the
        point table has to be countable somewhere, and `name:` says out loud that
        it is not a pelikone id.
        """
        if not person_key:
            return ""
        return self.key_of.get(person_key) or PSEUDO_PREFIX + person_key

    def rekey(self, rows: Mapping[str, object]) -> Dict[str, object]:
        """Re-key a person-keyed mapping (a builder's output) to site keys."""
        return {self.site_key(person): value for person, value in rows.items()}

    @property
    def pseudo(self) -> Dict[str, str]:
        """site key -> person key, for every key that is a name and not an id."""
        return {
            site_key: person
            for person, site_key in self.key_of.items()
            if site_key.startswith(PSEUDO_PREFIX)
        }

    @property
    def multi_id(self) -> Dict[str, List[str]]:
        """Persons whose cluster holds more than one pelikone id.

        Not an error — one id per season of registration — but the reason a
        person-keyed view cannot be joined on a single id, and the reason
        `names.json` exists.
        """
        return {
            self.key_of[person]: list(ids)
            for person, ids in self.clusters.items()
            if len(ids) > 1
        }

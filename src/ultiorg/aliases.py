"""Person keys: the layer between a pelikone player ID and a human being.

Measured over the 795 archived games: 904 distinct roster names carry **6,175
distinct player IDs** — pelikone mints a new player ID per registration, so a
single person (Touko Väänänen) holds ~45 of them across seasons. Keying facts
by player ID alone therefore fragments every career, and "who are X's strongest
connections" would answer with one season at a time.

The person key is the canonical name, optionally redirected through
`aliases.json`. Aliases are **human-asserted merges only** — nothing here
auto-merges two names, because a wrong merge is invisible downstream. The file
maps one canonical name to another:

    {
      "aukusti touko väänänen": "touko väänänen"
    }

Name variants that differ by a middle name are the common case, and they are
reported rather than merged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from .names import canon


def load_aliases(path: Path | None) -> Dict[str, str]:
    """Read `aliases.json` (canonical name -> canonical name to merge into).

    Missing file is normal, not an error: the default is no merges.
    """
    if not path or not Path(path).exists():
        return {}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {canon(src): canon(dst) for src, dst in raw.items()}


class PersonKeys:
    """Map a name to the key of the person it belongs to."""

    def __init__(self, aliases: Dict[str, str] | None = None):
        self.aliases = aliases or {}

    @classmethod
    def from_file(cls, path: Path | None) -> "PersonKeys":
        return cls(load_aliases(path))

    def resolve(self, name: str) -> str:
        key = canon(name)
        if not key:
            return ""
        seen = set()
        # Aliases may chain (a -> b -> c); follow to the terminal key and stop
        # on a cycle instead of looping forever.
        while key in self.aliases and key not in seen:
            seen.add(key)
            key = self.aliases[key]
        return key

    def merged(self) -> Dict[str, str]:
        """The alias pairs actually in effect, for the data-quality report."""
        return dict(self.aliases)

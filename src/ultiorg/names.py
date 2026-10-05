"""The one name rule. Point rows, rosters and the player index all meet here.

Point-by-point rows write `"Potrykus Patrick"` (Last First); rosters and the
`allplayers` index write `"Patrick Potrykus"` separated by U+00A0. Folding NBSP
and sorting the lowercased parts makes both orders produce the same key, which
is the rule the roster repair used in production (now `ultiorg repair rosters`)
and the rule `build_site_data.canonicalize_name` implements. It lives here so the parser,
the identity layer and the store cannot drift apart.
"""

from __future__ import annotations

import re

_CAPTION_RE = re.compile(r"\((?:c|C)\)")


def canon(name: str) -> str:
    """Canonical name key: NBSP folded, captain marks dropped, parts sorted.

    Sorting the parts is what makes the rule order-insensitive. The sorted form
    is alphabetical, so `"Potrykus Patrick"` and `"Patrick Potrykus"` both become
    `"patrick potrykus"`.
    """
    if not name:
        return ""
    cleaned = _CAPTION_RE.sub(" ", name.replace("\xa0", " "))
    parts = [p.lower() for p in cleaned.split() if p]
    return " ".join(sorted(parts))


def plain(name: str) -> str:
    """Display form of a scraped name: NBSP folded, captain marks dropped.

    Roster cells write `"Patrick\xa0Potrykus"` and point cells write
    `"Potrykus Patrick (c)"`. This keeps the order and the spelling — it only
    makes the string safe to print and to compare.
    """
    return " ".join(_CAPTION_RE.sub(" ", (name or "").replace("\xa0", " ")).split())


def pseudo_key(name: str) -> str:
    """Key for a name that never resolved to a player ID.

    Facts keyed this way are still counted — they just are not attributable to a
    person. They show up in `data_quality.json` instead of vanishing.
    """
    return f"name:{canon(name)}"

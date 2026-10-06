"""The focus team: which squads are "ours", and what to call them.

Nothing in the library knows that Otso exists. Every analytics view takes a
`FocusTeam`, and `teams.yaml` in the consuming repo says which club it is:

    focus:
      name: Otso
      include: [otso, grizzly, polar, hukka, karhuvaarit]
      exclude: [akatemia]

Three predicates, because the site needs three different scopes and using one
for all three is how a development squad ends up in the wrong table:

- `matches()`   — any squad of the club, its development squad included: Otso,
  Otso 2, Grizzly, Hukka, Otso Akatemia. Membership is the club substring, which
  is why "Otso Akatemia" is ours and "UFO Akatemia" is somebody else's.
- `is_main()`   — the flagship squad(s) only; what the year-by-year view counts.
- `is_akatemia()` — the club's development squad, and only that club's. Still
  needed to label it and to hold it out of the flagship scope.

`canonical_name()` folds scraped variants onto one label: the same squad shows
up as "OTSO 2", "Otso2" and — a scrape artifact — "Terror - Otso 2".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Sequence, Tuple

_CONFIG_KEY = "focus"


def _squash(name: str) -> str:
    """Compare form of a team name: no spaces, no dashes, no case."""
    return re.sub(r"[\s\-]+", "", (name or "").strip().lower())


@dataclass(frozen=True)
class FocusTeam:
    """Which team names belong to the club the analytics are about."""

    name: str
    include: Tuple[str, ...] = ()
    exclude: Tuple[str, ...] = ()
    akatemia: Tuple[str, ...] = ()
    main: frozenset = frozenset()
    canonical: Mapping[str, str] = field(default_factory=dict)
    canonical_substring: Mapping[str, str] = field(default_factory=dict)
    artifact: str = " - otso"

    # --- predicates -------------------------------------------------------
    def matches(self, team_name: str) -> bool:
        """Any squad of the club, its development squad included.

        Membership is decided by the club substring alone: "Otso Akatemia" is
        ours, "UFO Akatemia" is not, because it names no squad of ours. Do not
        put "akatemia" in `exclude` to keep another club's team out — that only
        ever removes our own development squad from the stats.
        """
        low = (team_name or "").lower()
        if any(x in low for x in self.exclude):
            return False
        return any(x in low for x in self.include)

    def is_akatemia(self, team_name: str) -> bool:
        """The club's development squad, and only that club's.

        "Otso Akatemia" is ours; "UFO Akatemia" is not, so the club name has to
        appear as well as the word Akatemia.
        """
        low = (team_name or "").lower()
        return "akatemia" in low and any(c in low for c in self.akatemia)

    def is_family(self, team_name: str) -> bool:
        """A squad of the club. Kept distinct from `matches()` for consumers
        whose `include` is broad enough to catch another club's development
        squad; for the gala's config the two agree.
        """
        return self.matches(team_name) or self.is_akatemia(team_name)

    def is_main(self, team_name: str) -> bool:
        """The flagship squad(s): what `years_otso.json` counts.

        Compared in squashed form, so "Otso 1", "Otso-1" and "Otso1" are one
        squad. Otso 2, Otso 3, Hukka, Karhuvaarit and Akatemia are not main.
        """
        return _squash(team_name) in self.main

    # --- labelling --------------------------------------------------------
    def canonical_name(self, team_name: str) -> str:
        """Fold scraped variants of one squad onto a single printed label.

        Unknown teams — every opponent — come back unchanged: this is not a
        normaliser for other clubs' names.
        """
        raw = (team_name or "").strip()
        low = raw.lower()

        # Scrape artifact: "Terror - Otso 2" is the away squad, not a merged name.
        if self.artifact in low:
            rest = low.split(self.artifact, 1)[1].strip()
            # " - Otso 2" -> "otso" + "2" -> the `otso2` key of `canonical`.
            club = self.artifact.split()[-1]
            key = club + rest
            if key in self.canonical:
                return self.canonical[key]
            return self.canonical.get(_squash(self.name), self.name)

        key = _squash(low)
        if key in self.canonical:
            return self.canonical[key]
        for needle, label in self.canonical_substring.items():
            if needle in low:
                return label
        if self.is_akatemia(low):
            return self.canonical.get(_squash(self.name) + "akatemia", raw)
        return raw


def load_focus_team(path: Path | None) -> FocusTeam | None:
    """Read `teams.yaml`; `None` when the file is absent.

    Absent is a real answer: a library consumer that has no focus team gets
    unfiltered, club-agnostic views rather than a guess.
    """
    if not path:
        return None
    path = Path(path)
    if not path.exists():
        return None
    import yaml  # imported here so the library works without it until needed

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg: Dict = raw.get(_CONFIG_KEY) or {}
    akatemia = cfg.get("akatemia")
    if akatemia is None:
        akatemia = [str(cfg.get("name", "")).lower()]
    return FocusTeam(
        name=str(cfg.get("name", "")),
        include=_lower_tuple(cfg.get("include")),
        exclude=_lower_tuple(cfg.get("exclude")),
        akatemia=_lower_tuple(akatemia),
        main=frozenset(_squash(m) for m in _as_sequence(cfg.get("main"))),
        canonical={_squash(k): str(v) for k, v in (cfg.get("canonical") or {}).items()},
        canonical_substring={
            _squash(k): str(v)
            for k, v in (cfg.get("canonical_substring") or {}).items()
        },
        artifact=str(cfg.get("name_artifact") or " - otso").lower(),
    )


def _as_sequence(value: Sequence | str | None) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _lower_tuple(value: Sequence | str | None) -> Tuple[str, ...]:
    return tuple(str(v).lower() for v in _as_sequence(value))

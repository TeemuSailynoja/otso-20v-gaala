"""Characterization cases: one parser, one archived page, one golden output.

These tests do not assert what the parsers *should* produce — they assert that
the parsers keep producing what they produce today. Every later phase of
`plans/pelikone-library-refactor.md` is allowed to change a golden only with an
explicit, stated reason; an unexplained golden diff is a regression.

Regenerate after an intentional change:

    uv run python tests/regenerate_golden.py
"""

from ultiorg import parsers

# (golden name, parser function, fixture file, extra positional args)
CASES = [
    ("seasons", parsers.parse_season_list, "seasonlist.html", ()),
    ("teams_current", parsers.parse_teams_page, "teams_KESA2026.html", ("KESA2026",)),
    ("teams_multi", parsers.parse_teams_page, "teams_2025.3.html", ("2025.3",)),
    ("standings", parsers.parse_standings_page, "standings_2018.1.html", ("2018.1",)),
    ("teamcard", parsers.parse_team_card, "teamcard_3130.html", ("3130",)),
    ("playerlist", parsers.parse_player_list, "playerlist_2405.html", ("2405",)),
    ("games_list", parsers.parse_games_list, "games_KESA2026.html", ("KESA2026",)),
    ("gameplay_modern", parsers.parse_gameplay, "gameplay_11049_modern.html", ()),
    ("gameplay_pre2015", parsers.parse_gameplay, "gameplay_2980_pre2015.html", ()),
    # Otso 2 vs Otso: the case that broke the old caption-matching rule.
    ("gameplay_otso_derby", parsers.parse_gameplay, "gameplay_6215_otso_derby.html", ()),
    # "SOS-Terror - Otso 2": a hyphen inside a team name.
    ("gameplay_hyphen", parsers.parse_gameplay, "gameplay_6923_hyphen.html", ()),
    ("allplayers", parsers.parse_allplayers, "allplayers_all.html", ()),
    ("playercard", parsers.parse_playercard, "playercard_27441.html", ("27441",)),
]


def to_jsonable(value):
    """Normalize a parse result for golden comparison.

    Sets appear in some parser outputs (e.g. season name variants). They become
    sorted lists so the golden is stable; everything else must already be JSON.
    """
    if isinstance(value, (set, frozenset)):
        return {"__set__": sorted(to_jsonable(v) for v in value)}
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"not JSON-native, add a rule for it: {type(value).__name__}: {value!r}")

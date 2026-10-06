"""Team analytics over the corpus, parameterised by focus team.

These are the views the gala page shows — career tables, defense, the pass
network, who played with whom, the rivals, the year-by-year line, the trophy
cabinet. They are **not** Otso-specific: each takes a `FocusTeam` loaded from
`teams.yaml`, so the coaching staff can run the same views for another club or a
national team. Nothing in this module knows the word "Otso".

Two rules hold throughout:

- **People are person keys.** `canon(name)` plus the merges in `aliases.json`,
  so "Touko aukusti Väänänen" and "Touko Väänänen" are one career. Point rows
  write `Last First`, rosters write `First Last`; the key is order-insensitive.
- **Games are filtered by team, points by roster.** A point is credited to the
  focus team only when the player is on that team's roster *in that game* —
  counting by team name alone credited goals scored against us.

Personal data never enters here: `build_years` returns roster names, and the
gala script adds the average age from the gitignored birthdays file.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from .aliases import PersonKeys
from .seasons import season_type, season_year
from .teams import FocusTeam

# How many rivals the frenemies view returns; the page shows a 21-wide wall.
DEFAULT_FRENEMIES = 21


def _keyer(persons: PersonKeys | None):
    """Name -> person key. Without aliases this is plain `canon`."""
    if persons is None:
        from .names import canon

        return canon
    return persons.resolve


def _season_names(seasons: Iterable[Dict]) -> Dict[str, str]:
    """{season_id: season name} from parsed season records.

    The name is what classifies a season as summer or winter — the numeric id
    does not encode it (`2018.1` winter, `2020.1` summer).
    """
    return {
        s["id"]: s.get("name", "")
        for s in seasons
        if isinstance(s, dict) and s.get("id")
    }


# --- career table -----------------------------------------------------------
def _career_sources(
    seasons: Iterable[Dict],
    games: Iterable[Dict],
    focus: FocusTeam,
    persons: PersonKeys | None = None,
    season_names: Mapping[str, str] | None = None,
) -> tuple:
    """Collect the three career sources per person; decide nothing.

    Returns `(players, season_names)`. Each player row carries
    `card_games_by_season`, `gp_games_by_season`, `card_stats_by_season` and
    `pbp_by_season` — the sources side by side, so the caller can both combine
    them (`build_career_stats`) and report where they disagree
    (`career_source_report`). One pass, one set of filters: the report and the
    table cannot drift apart.
    """
    key = _keyer(persons)
    seasons = list(seasons)
    names = dict(season_names or {})
    names.update(_season_names(seasons))

    players: Dict[str, Dict] = {}

    def new_player(year: Optional[int]) -> Dict:
        return {
            "seasons": [],
            "years": set(),
            "season_types": {"summer": set(), "winter": set(), "other": set()},
            "first_year": year,
            "last_year": year,
            "teams": set(),
            "card_games_by_season": {},
            "gp_games_by_season": {},
            "card_stats_by_season": {},
            "pbp_by_season": {},
            "_season_seen": set(),
        }

    def note_season(p: Dict, season_id: str, year: Optional[int], stype: str) -> None:
        if season_id and season_id not in p["_season_seen"]:
            p["_season_seen"].add(season_id)
            p["seasons"].append(season_id)
        if year is None:
            return
        p["years"].add(year)
        if p["first_year"] is None or year < p["first_year"]:
            p["first_year"] = year
        if p["last_year"] is None or year > p["last_year"]:
            p["last_year"] = year
        p["season_types"].setdefault(stype if stype in ("summer", "winter") else "other", set()).add(year)

    # 1 — season cards, every squad of the club including its development
    # squad. A player who turned out for two squads played two sets of games,
    # and both belong in his career. Other clubs' cards are not in the corpus at
    # all: the scrape only walked our own team pages.
    for season in seasons:
        season_id = season.get("id", "")
        year = season_year(season_id, names.get(season_id, ""))
        if not year:
            continue
        stype = season_type(season_id, names.get(season_id, ""))
        for team in season.get("teams", []):
            if not focus.matches(team.get("name", "")):
                continue
            team_label = focus.canonical_name(team.get("name", ""))
            for row in team.get("players", []):
                person = key(row.get("name", ""))
                if not person:
                    continue
                try:
                    games_n = int(row.get("games", 0))
                    goals = int(row.get("goals", 0))
                    assists = int(row.get("assists", 0))
                except (ValueError, TypeError):
                    games_n, goals, assists = 0, 0, 0
                p = players.setdefault(person, new_player(year))
                note_season(p, season_id, year, stype)
                p["teams"].add(team_label)
                p["card_games_by_season"][season_id] = (
                    p["card_games_by_season"].get(season_id, 0) + games_n
                )
                card = p["card_stats_by_season"].setdefault(
                    season_id, {"goals": 0, "assists": 0}
                )
                card["goals"] += goals
                card["assists"] += assists

    # 2 — gameplay rosters. Akatemia counts here: an Akatemia game is still an
    # appearance, and the roster is the only record of it.
    for game in games:
        gp = game.get("gameplay")
        if not gp:
            continue
        season_id = game.get("season_id", "")
        year = season_year(season_id, names.get(season_id, ""))
        stype = season_type(season_id, names.get(season_id, ""))
        home_is = focus.is_family(gp.get("home_team", ""))
        away_is = focus.is_family(gp.get("away_team", ""))
        if not home_is and not away_is:
            continue
        # The label is the canonical name of the squad that played, so an
        # Akatemia appearance puts "Otso Akatemia" in the player's team list
        # rather than folding it onto the flagship squad.
        label = ""
        if focus.matches(gp.get("home_team", "")):
            label = focus.canonical_name(gp.get("home_team", ""))
        elif focus.matches(gp.get("away_team", "")):
            label = focus.canonical_name(gp.get("away_team", ""))
        roster = []
        if home_is:
            roster += gp.get("home_players", [])
        if away_is:
            roster += gp.get("away_players", [])
        for row in roster:
            person = key(row.get("name", ""))
            if not person:
                continue
            p = players.setdefault(person, new_player(year))
            note_season(p, season_id, year, stype)
            if label:
                p["teams"].add(label)
            by_season = p["gp_games_by_season"]
            by_season[season_id] = by_season.get(season_id, 0) + 1

    # 3 — play-by-play goals and assists, credited only to players on the focus
    # team's roster in that game.
    pbp: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"goals": 0, "assists": 0})
    )
    for game in games:
        gp = game.get("gameplay")
        if not gp:
            continue
        season_id = game.get("season_id", "")
        if not season_id:
            continue
        home_is = focus.matches(gp.get("home_team", ""))
        away_is = focus.matches(gp.get("away_team", ""))
        if not home_is and not away_is:
            continue
        in_game = set()
        for side, is_focus in (("home_players", home_is), ("away_players", away_is)):
            if not is_focus:
                continue
            for row in gp.get(side, []):
                person = key(row.get("name", ""))
                if person:
                    in_game.add(person)
        for point in gp.get("points", []):
            if point.get("type") != "point":
                continue
            scorer = key(point.get("scorer", ""))
            passer = key(point.get("passer", ""))
            if scorer and scorer in in_game:
                pbp[scorer][season_id]["goals"] += 1
            if passer and passer in in_game:
                pbp[passer][season_id]["assists"] += 1

    for person, by_season in pbp.items():
        p = players.get(person)
        if p is None:
            continue
        for season_id, stats in by_season.items():
            dst = p["pbp_by_season"].setdefault(season_id, {"goals": 0, "assists": 0})
            dst["goals"] += stats["goals"]
            dst["assists"] += stats["assists"]

    return players, names


def build_career_stats(
    seasons: Iterable[Dict],
    games: Iterable[Dict],
    focus: FocusTeam,
    persons: PersonKeys | None = None,
    season_names: Mapping[str, str] | None = None,
) -> Dict[str, Dict]:
    """Per-player career stats for the focus club, keyed by person key.

    Three sources, deliberately not summed:

    1. the season **card** (a player's games/goals/assists for that season's team),
    2. **gameplay rosters** (who actually appeared in a scraped game),
    3. **play-by-play points** (goals and assists from the point table).

    Games are taken per season as `max(card, rosters)`, never the sum: a player
    on a roster is also on that season's card, and adding both counted most
    careers twice (16,424 site-wide against 9,061 card games).

    Goals and assists follow the same rule, `max(card, play-by-play)` per
    (person, season). The two sources measure the same goals: of the 1,302
    (person, season) pairs that carry stats from both, **1,123 agree exactly** in
    goals and assists, the card is higher on 173 (games the scrape never got — 9
    seasons are short of full coverage) and the play-by-play is higher on 6.
    Adding them counted most careers twice: 21,799 published goals against 10,414
    scored in the games themselves, which `summary.json` reports correctly at
    game level. The larger source wins rather than the play-by-play always
    winning, because the card is a complete season total while the play-by-play
    is complete only where every game was scraped — 351 pairs are card-only (6
    single-game seasons have no scraped games at all) and 51 are play-by-play
    only; those pass through untouched.

    Measured consequence of the rule: goals 21,799 -> 11,177, assists 21,613 ->
    11,081. Taking the max per field and picking one whole source per
    (person, season) were measured to agree on all 1,302 pairs — where the two
    sources differ the higher one is higher in both fields — so the simpler
    per-field rule is used. `career_source_report` publishes the per-season
    comparison so the table's thin spots are visible next to the numbers.
    """
    players, names = _career_sources(seasons, games, focus, persons, season_names)

    # Finalise: per season, games and points each take the larger source.
    result: Dict[str, Dict] = {}
    for person, p in sorted(players.items()):
        card_games, play_games = p["card_games_by_season"], p["gp_games_by_season"]
        card_stats, play_stats = p["card_stats_by_season"], p["pbp_by_season"]
        total_games = summer_games = winter_games = 0
        goals = assists = 0
        summer_goals = winter_goals = summer_assists = winter_assists = 0
        season_ids = (set(card_games) | set(play_games)
                      | set(card_stats) | set(play_stats))
        for sid in season_ids:
            count = max(card_games.get(sid, 0), play_games.get(sid, 0))
            total_games += count
            card = card_stats.get(sid, {"goals": 0, "assists": 0})
            play = play_stats.get(sid, {"goals": 0, "assists": 0})
            season_goals = max(card["goals"], play["goals"])
            season_assists = max(card["assists"], play["assists"])
            goals += season_goals
            assists += season_assists
            stype = season_type(sid, names.get(sid, ""))
            if stype == "summer":
                summer_games += count
                summer_goals += season_goals
                summer_assists += season_assists
            elif stype == "winter":
                winter_games += count
                winter_goals += season_goals
                winter_assists += season_assists
        result[person] = {
            "seasons": sorted(p["seasons"]),
            "season_count": len(p["season_types"]["summer"]) + len(p["season_types"]["winter"]),
            "years": sorted(p["years"]),
            "year_count": len(p["years"]),
            "first_year": p["first_year"],
            "last_year": p["last_year"],
            "games": total_games,
            "goals": goals,
            "assists": assists,
            "total": goals + assists,
            "teams": sorted(p["teams"]),
            "season_types": {
                "summer": sorted(p["season_types"]["summer"]),
                "winter": sorted(p["season_types"]["winter"]),
                "other": sorted(p["season_types"]["other"]),
            },
            "summer_games": summer_games,
            "summer_goals": summer_goals,
            "summer_assists": summer_assists,
            "winter_games": winter_games,
            "winter_goals": winter_goals,
            "winter_assists": winter_assists,
            # Defense is a separate view; the caller merges it in.
            "defense_points": 0,
            "offense_points": 0,
            "total_points": 0,
        }
    return result


def career_source_report(
    seasons: Iterable[Dict],
    games: Iterable[Dict],
    focus: FocusTeam,
    persons: PersonKeys | None = None,
    season_names: Mapping[str, str] | None = None,
) -> Dict:
    """Where the season card and the play-by-play disagree, season by season.

    `build_career_stats` takes the larger source per (person, season); this says
    which source won and by how much, so a season whose numbers rest on the card
    alone — because no game was ever scraped — is visible next to the totals it
    produced. It reads the same collection pass as the table, so the two cannot
    drift apart.

    `card_only_*` is what the published table has that the point table does not:
    goals from games the scrape never got. `play_only_*` is the mirror image.
    Both are residuals of an incomplete archive, not of the rule.
    """
    players, names = _career_sources(seasons, games, focus, persons, season_names)
    per_season: Dict[str, Dict[str, int]] = {}
    pairs = {"both": 0, "agree": 0, "card_higher": 0, "play_higher": 0,
             "card_only": 0, "play_only": 0}
    published_goals = published_assists = 0
    card_only_goals = card_only_assists = play_only_goals = play_only_assists = 0
    for person, p in players.items():
        card_by, play_by = p["card_stats_by_season"], p["pbp_by_season"]
        for sid in set(card_by) | set(play_by):
            card = card_by.get(sid, {"goals": 0, "assists": 0})
            play = play_by.get(sid, {"goals": 0, "assists": 0})
            goals = max(card["goals"], play["goals"])
            assists = max(card["assists"], play["assists"])
            published_goals += goals
            published_assists += assists
            card_only_goals += goals - play["goals"]
            card_only_assists += assists - play["assists"]
            play_only_goals += goals - card["goals"]
            play_only_assists += assists - card["assists"]
            if sid in card_by and sid in play_by:
                pairs["both"] += 1
                if card == play:
                    pairs["agree"] += 1
                elif (card["goals"] + card["assists"]) > (play["goals"] + play["assists"]):
                    pairs["card_higher"] += 1
                else:
                    pairs["play_higher"] += 1
            elif sid in card_by:
                pairs["card_only"] += 1
            else:
                pairs["play_only"] += 1
            row = per_season.setdefault(sid, {
                "card_goals": 0, "card_assists": 0, "play_goals": 0,
                "play_assists": 0, "published_goals": 0, "published_assists": 0,
                "people": 0,
            })
            row["card_goals"] += card["goals"]
            row["card_assists"] += card["assists"]
            row["play_goals"] += play["goals"]
            row["play_assists"] += play["assists"]
            row["published_goals"] += goals
            row["published_assists"] += assists
            row["people"] += 1
    seasons_out = []
    for sid, row in per_season.items():
        gap = abs(row["card_goals"] - row["play_goals"]) + abs(row["card_assists"] - row["play_assists"])
        if not gap:
            continue
        seasons_out.append({"season": sid, "name": names.get(sid, ""), **row, "gap": gap})
    seasons_out.sort(key=lambda r: (-r["gap"], r["season"]))
    return {
        "rule": "goals and assists per person-season take max(season card, "
                "play-by-play); never the sum",
        "pairs": pairs,
        "published": {"goals": published_goals, "assists": published_assists},
        "card_only": {"goals": card_only_goals, "assists": card_only_assists,
                      "note": "in the table but not in the point table: games the "
                              "scrape never got, or a scorer whose name joined no roster"},
        "play_only": {"goals": play_only_goals, "assists": play_only_assists,
                      "note": "in the point table but not on the card"},
        "seasons": seasons_out,
    }


# --- defense ----------------------------------------------------------------
def build_defense_stats(
    games: Iterable[Dict],
    focus: FocusTeam,
    persons: PersonKeys | None = None,
) -> Dict[str, Dict]:
    """Points scored while the focus team was on defense, per player.

    Possession is a fact about the game, not about the focus team, and
    `parse_gameplay` already decided it: the Hyökkäys marker starts a half, then
    the scorer of a point starts the next point on defense, reset at halftime.
    This view reads `possession` / `possession_known` off each point. It used to
    re-derive them by re-reading the archived HTML — a second implementation
    that could, and did, disagree with the parser.

    A point whose half-opening possession is unknown counts as offense, because
    that is what the site has always published; the store keeps
    `possession_known` so the honest variant stays computable. Measured: 287 of
    18,770 points, 1.5%.

    Keyed by person key, not by the spelling the point table happened to write.
    """
    key = _keyer(persons)
    stats: Dict[str, Dict] = defaultdict(lambda: {
        "defense_points": 0,
        "defense_goals": 0,
        "defense_assists": 0,
        "offense_points": 0,
        "offense_goals": 0,
        "offense_assists": 0,
        "total_points": 0,
    })

    for game in games:
        gp = game.get("gameplay")
        if not gp:
            continue
        points = gp.get("points", [])
        if not points:
            continue

        # One row per score line. The double scrape left some games with every
        # point twice; `ultiorg repair dedupe-points` collapses them in the
        # corpus, and this keeps an un-repaired file from doubling here too.
        seen_scores = set()
        entries = []
        for point in points:
            if point.get("type") != "point":
                continue
            score = re.sub(r"\s*", "", point.get("score") or "")
            if score and score in seen_scores:
                continue
            if score:
                seen_scores.add(score)
            entries.append(point)
        if not entries:
            continue

        home_is = focus.is_family(gp.get("home_team", ""))
        away_is = focus.is_family(gp.get("away_team", ""))
        if home_is:
            side = "home"
        elif away_is:
            side = "guest"
        else:
            continue

        # The point's `side` is the scoring cell's class, which does not reliably
        # identify the scorer's team; the roster does.
        roster = {}
        for cells, cell_side in (("home_players", "home"), ("away_players", "guest")):
            for row in gp.get(cells, []):
                person = key(row.get("name", ""))
                if person:
                    roster[person] = cell_side

        for point in entries:
            scorer = point.get("scorer", "")
            if not scorer:
                continue
            person = key(scorer)
            if roster.get(person) != side:
                continue
            is_defense = bool(point.get("possession_known")) and point.get("possession") == side
            bucket = "defense" if is_defense else "offense"
            row = stats[person]
            row[f"{bucket}_points"] += 1
            row[f"{bucket}_goals"] += 1
            row["total_points"] += 1
            if key(point.get("passer", "")):
                row[f"{bucket}_assists"] += 1

    return dict(stats)


# --- pass network -----------------------------------------------------------
def build_pass_network(
    games: Iterable[Dict],
    focus: FocusTeam,
    only: Optional[Iterable[str]] = None,
    persons: PersonKeys | None = None,
) -> Dict[str, Dict]:
    """Directed pass edges: `received[scorer][passer] = times passer fed scorer`.

    A point's `passer` is the pelikone column *Syöttäjä* and `scorer` is *Maali*.
    Assists are counted for games involving a focus-team squad, credited when the
    passer is on that team's roster — the same *attribution* rule as the career
    table's play-by-play pass.

    Two invariants tie this graph to `build_career_stats`:

      sum(received[p].values()) == the player's goals
      sum(given[p].values())    == the player's assists

    They hold exactly for **113 of 171** and **127 of 171** players, and never
    overshoot. Where they fall short (58 and 44 players) the season card recorded
    points the point table does not have — games the scrape never got, or a
    scorer whose name joined no roster — and this graph is play-by-play only.
    Before the career table stopped adding the card to the play-by-play, the same
    check read equal for 26 and 35 players and *exactly half* for 74 and 77: that
    halving was the double count, and it is why this check is worth running.
    `given` can never exceed the play-by-play assists: an edge is dropped when
    the *scorer* is not in the table, while the career pass credits the passer
    whoever scored.

    Keys are **person keys**, not display names: the library never prints a name,
    it identifies a person, and the caller decides how to render them (the site
    maps person key -> site key via `persons.PersonIds` and keeps the names in
    `names.json`). `only` restricts the graph to a set of person keys — the site
    passes its career table, so an opponent who was fed by our passer appears in
    the pass graph only if he is one of ours.
    """
    key = _keyer(persons)
    keep = None if only is None else {key(name) for name in only}

    network = defaultdict(lambda: defaultdict(int))
    for game in games:
        gp = game.get("gameplay")
        if not gp:
            continue
        home_is = focus.matches(gp.get("home_team", ""))
        away_is = focus.matches(gp.get("away_team", ""))
        if not home_is and not away_is:
            continue
        in_game = set()
        for cells, is_focus in (("home_players", home_is), ("away_players", away_is)):
            if not is_focus:
                continue
            for row in gp.get(cells, []):
                person = key(row.get("name", ""))
                if person:
                    in_game.add(person)
        for point in gp.get("points", []):
            if point.get("type") != "point":
                continue
            passer = key(point.get("passer", ""))
            if passer in in_game:
                network[key(point.get("scorer", ""))][passer] += 1

    received: Dict[str, Dict[str, int]] = defaultdict(dict)
    given: Dict[str, Dict[str, int]] = defaultdict(dict)
    for person, partners in network.items():
        if keep is not None and person not in keep:
            continue
        for other, count in partners.items():
            if keep is not None and other not in keep:
                continue
            received[person][other] = received[person].get(other, 0) + count
            given[other][person] = given[other].get(person, 0) + count

    # Sorted on write: the adjacency dicts are built in corpus order, so an
    # unsorted file reorders wholesale whenever the corpus is recomposed —
    # thousands of lines of churn that is not a data change.
    def by_name(d: Dict) -> Dict:
        return {k: {o: c for o, c in sorted(v.items())} for k, v in sorted(d.items())}

    return {"received": by_name(received), "given": by_name(given)}


# --- who played with whom ---------------------------------------------------
def build_cooccurrence(
    games: Iterable[Dict],
    focus: FocusTeam,
    only: Optional[Iterable[str]] = None,
    persons: PersonKeys | None = None,
) -> Dict[str, Dict[str, int]]:
    """Undirected teammate counts: every pair on a focus-team roster in a game.

    Person keys in, person keys out — see `build_pass_network`.
    """
    key = _keyer(persons)
    keep = None if only is None else {key(name) for name in only}

    cooc = defaultdict(lambda: defaultdict(int))
    for game in games:
        gp = game.get("gameplay")
        if not gp:
            continue
        people = set()
        for cells, is_focus in (
            ("home_players", focus.matches(gp.get("home_team", ""))),
            ("away_players", focus.matches(gp.get("away_team", ""))),
        ):
            if not is_focus:
                continue
            for row in gp.get(cells, []):
                person = key(row.get("name", ""))
                if not person or (keep is not None and person not in keep):
                    continue
                people.add(person)
        ordered = sorted(people)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                cooc[a][b] += 1
                cooc[b][a] += 1

    result: Dict[str, Dict[str, int]] = {}
    for person, partners in sorted(cooc.items()):
        if keep is not None and person not in keep:
            continue
        inner = {
            other: count
            for other, count in partners.items()
            if keep is None or other in keep
        }
        if inner:
            result[person] = dict(sorted(inner.items(), key=lambda kv: (-kv[1], kv[0])))
    return result


# --- rivals -----------------------------------------------------------------
def build_frenemies(
    games: Iterable[Dict],
    focus: FocusTeam,
    top_n: int = DEFAULT_FRENEMIES,
    persons: PersonKeys | None = None,
) -> List[Dict]:
    """The opponents who hurt us most: career points scored against the focus team.

    Goals and assists come from the point table, not roster totals, which the
    scrape writes unreliably. Intra-club games are skipped — there is no
    external opponent when both sides are ours.
    """
    key = _keyer(persons)
    players = defaultdict(
        lambda: {"name": "", "games": 0, "wins": 0, "goals": 0, "assists": 0, "teams": Counter()}
    )

    for game in games:
        gp = game.get("gameplay")
        if not gp:
            continue
        home, away = gp.get("home_team", ""), gp.get("away_team", "")
        home_score = gp.get("home_score", 0)
        away_score = gp.get("away_score", 0)
        home_is = focus.is_family(home)
        away_is = focus.is_family(away)
        if not home_is and not away_is:
            continue
        if home_is and away_is:
            continue

        everyone = {}
        for row in gp.get("home_players", []) + gp.get("away_players", []):
            person = key(row.get("name", ""))
            if person:
                everyone.setdefault(person, row.get("name", ""))
        ours = set()
        for cells, is_focus in (("home_players", home_is), ("away_players", away_is)):
            if not is_focus:
                continue
            for row in gp.get(cells, []):
                person = key(row.get("name", ""))
                if person:
                    ours.add(person)

        if home_is:
            our_score, opp_score, opp_team = home_score, away_score, away
        else:
            our_score, opp_score, opp_team = away_score, home_score, home

        for person in set(everyone) - ours:
            entry = players[person]
            # First spelling seen wins; the display name is the caller's business.
            entry["name"] = entry["name"] or everyone[person]
            entry["games"] += 1
            if opp_score > our_score:
                entry["wins"] += 1
            entry["teams"][opp_team] += 1

        for point in gp.get("points", []):
            if point.get("type") != "point":
                continue
            for field in ("scorer", "passer"):
                person = key(point.get(field, ""))
                if person in everyone and person not in ours:
                    players[person]["goals" if field == "scorer" else "assists"] += 1

    scored = []
    for person, p in players.items():
        total = p["goals"] + p["assists"]
        if total <= 0:
            continue
        scored.append({
            # Person key, not the spelling: the same opponent registered under
            # two spellings used to be counted as two rivals.
            "id": person,
            "name": p["name"],
            "games": p["games"],
            "wins": p["wins"],
            "losses": p["games"] - p["wins"],
            "goals": p["goals"],
            "assists": p["assists"],
            "total": total,
            "ppg": round(total / p["games"], 2) if p["games"] else 0,
            "teams": [t for t, _ in sorted(p["teams"].items(), key=lambda kv: (-kv[1], kv[0]))],
        })

    # Ties broken by name: a stable sort over insertion order made rank 15/16
    # swap when the corpus was re-sorted, which is churn, not a data change.
    scored.sort(key=lambda x: (-x["total"], x["name"]))
    for rank, entry in enumerate(scored[:top_n], 1):
        entry["rank"] = rank
    return scored[:top_n]


# --- year by year -----------------------------------------------------------
def build_years(
    games: Iterable[Dict],
    focus: FocusTeam,
    scope: str = "main",
    season_type_filter: Optional[str] = None,
    season_names: Mapping[str, str] | None = None,
    persons: PersonKeys | None = None,
) -> Dict[str, Dict]:
    """One row per year: matches, result, goals for/against, roster size.

    `scope="main"` counts only the flagship squad(s) (`teams.yaml: main`);
    `scope="all"` counts every squad of the club, development teams included.
    `season_type_filter` restricts the row to summer or winter seasons.

    Returns person keys in `roster`; the gala script turns those into site keys
    and display names, and adds the average age from the private birthdays file.
    """
    names = dict(season_names or {})
    key = _keyer(persons)
    years = defaultdict(lambda: {
        "matches": 0, "wins": 0, "losses": 0,
        "goals_for": 0, "goals_against": 0,
        "roster": set(),
    })

    for game in games:
        gp = game.get("gameplay")
        if not gp:
            continue
        season_id = game.get("season_id", "")
        name = names.get(season_id, "")
        year = season_year(season_id, name)
        if not year:
            continue
        if season_type_filter and season_type(season_id, name) != season_type_filter:
            continue

        home, away = gp.get("home_team", ""), gp.get("away_team", "")
        if scope == "all":
            home_is, away_is = focus.is_family(home), focus.is_family(away)
        else:
            home_is, away_is = focus.is_main(home), focus.is_main(away)
        if not home_is and not away_is:
            continue

        row = years[year]
        row["matches"] += 1
        our_score = gp["away_score"] if away_is else gp["home_score"]
        opp_score = gp["home_score"] if away_is else gp["away_score"]
        row["goals_for"] += our_score
        row["goals_against"] += opp_score
        if our_score > opp_score:
            row["wins"] += 1
        elif our_score < opp_score:
            row["losses"] += 1

        for cells, is_focus in (("home_players", home_is), ("away_players", away_is)):
            if not is_focus:
                continue
            for player in gp.get(cells, []):
                person = key(player.get("name", ""))
                if person:
                    row["roster"].add(person)

    result = {}
    for year in sorted(years):
        row = years[year]
        roster = sorted(row["roster"])
        result[str(year)] = {
            "matches": row["matches"],
            "wins": row["wins"],
            "losses": row["losses"],
            "goals_for": row["goals_for"],
            "goals_against": row["goals_against"],
            "roster_players": len(roster),
            # The timeline HUD cloud is seeded from exactly this roster, so it
            # must match roster_players rather than the career table's years.
            "roster": roster,
        }
    return result


# --- trophy cabinet ---------------------------------------------------------
#
# The pelikone format changed three times, so which file decides a season's medals
# is stated explicitly rather than inferred from filenames — filename inference is
# what would silently count a Tour stop as a finale.
#   2006-2010  the season file itself (no separate finale existed)
#   2011-2019  summer = the Finaalit file; winter = the winter season file
#   2020+      one championship event per season, in the season file itself
#              (Kesä 2026 keeps Tour 1 / Tour 2 / Finaalit as sub-tournaments inside
#              the single KESA2026 season id; its placements are the final standings)
# Winter never had a separate finale file.
CHAMPIONSHIP_EVENTS: Dict[str, tuple] = {
    # summer (Kesä)
    "2006.1": (2006, "summer"), "2007.1": (2007, "summer"), "2008.1": (2008, "summer"),
    "2009.1": (2009, "summer"), "2010.1": (2010, "summer"), "2011.4": (2011, "summer"),
    "2012.T4": (2012, "summer"), "2013.1": (2013, "summer"), "2014.1F": (2014, "summer"),
    "2015.1F": (2015, "summer"), "2016.1.F": (2016, "summer"), "2017F": (2017, "summer"),
    "2018.F": (2018, "summer"), "2019.Finaa": (2019, "summer"), "2020.1": (2020, "summer"),
    "2021.1": (2021, "summer"), "SM2022K": (2022, "summer"), "2023.1": (2023, "summer"),
    "2024.1": (2024, "summer"), "2025.1": (2025, "summer"), "KESA2026": (2026, "summer"),
    # winter (Talvi)
    "2006.2": (2006, "winter"), "2007.2": (2007, "winter"), "2008.2": (2008, "winter"),
    "2009.2": (2009, "winter"), "2010.2": (2010, "winter"), "2011.2": (2011, "winter"),
    "2012.2": (2012, "winter"), "2013.2": (2013, "winter"), "Hallitour2": (2014, "winter"),
    "2015.4": (2015, "winter"), "Talvi2016": (2016, "winter"), "2017.1": (2017, "winter"),
    "2018.1": (2018, "winter"), "2019.1": (2019, "winter"), "2020.2": (2020, "winter"),
    "2021.2": (2021, "winter"), "2022.3": (2022, "winter"), "2023.2": (2023, "winter"),
    "2024.2": (2024, "winter"), "2025.3": (2025, "winter"),
}

MEDAL_PLACEMENTS = {"Kulta": "gold", "Hopea": "silver", "Pronssi": "bronze"}
MEDAL_RANK = {"gold": 0, "silver": 1, "bronze": 2}
MEDAL_PLACEMENTS_INV = {v: k for k, v in MEDAL_PLACEMENTS.items()}

# Talvi 2020 was never played — cancelled because of the covid pandemic. It is
# not a missing scrape and must not count as a season contested.
SEASONS_NOT_PLAYED = {"2020.2"}

# Only the open/flagship division counts towards the cabinet. Juniorit, Naiset,
# Mixed, Master Mixed and SM Ranta results live in other divisions. The label is
# written two ways in the raw data — "Avoin" and "Avoin SM" (Kesä 2010).
CHAMPIONSHIP_DIVISION = "avoin"


def _placement_rank(placement: str, medal: Optional[str]) -> int:
    """Sort key for a placement: medals first, then numeric rank, unknown last."""
    if medal:
        return MEDAL_RANK[medal]
    match = re.match(r"^(\d+)\.$", placement or "")
    return 3 + int(match.group(1)) if match else 999


def build_trophies(
    seasons: Iterable[Dict],
    focus: FocusTeam,
    events: Mapping[str, tuple] = CHAMPIONSHIP_EVENTS,
    division: str = CHAMPIONSHIP_DIVISION,
    not_played: Sequence[str] = tuple(sorted(SEASONS_NOT_PLAYED)),
) -> Dict:
    """Season-by-season medal record for the focus club.

    A trophy is a Kulta/Hopea/Pronssi placement in the open division by a focus
    squad (never the development squad) in a season-deciding event. Tour stops
    are regular-season events and are deliberately not counted.

    Each season keeps its single best result — what the cabinet counts — and
    lists every focus squad that finished in the division under `entries`: in
    2013 winter the club won it, the second squad was 7th and the third 10th,
    and the timeline shows all three.
    """
    by_id = {s["id"]: s for s in seasons if isinstance(s, dict) and s.get("id")}
    skipped = set(not_played)

    records = []
    for season_id, (year, kind) in sorted(events.items(), key=lambda kv: (kv[1][0], kv[1][1], kv[0])):
        record = {
            "year": year,
            "season": kind,
            "event": season_id,
            "medal": None,
            "team": None,
            "placement": None,
            "played": season_id not in skipped,
            "entries": [],
        }
        season = by_id.get(season_id)
        if season is None:
            records.append(record)
            continue

        best_medal = best_team = best_numeric = None
        by_team: Dict[str, Dict] = {}
        for place in season.get("placements") or []:
            if not (place.get("division") or "").strip().lower().startswith(division):
                continue
            team = place.get("team_name", "")
            if not focus.matches(team):
                continue
            placement = place.get("placement", "")
            medal = MEDAL_PLACEMENTS.get(placement)
            if medal is not None:
                if best_medal is None or MEDAL_RANK[medal] < MEDAL_RANK[best_medal]:
                    best_medal, best_team = medal, team
            else:
                match = re.match(r"^(\d+)\.$", placement)
                if match and (best_numeric is None or int(match.group(1)) < best_numeric[0]):
                    best_numeric = (int(match.group(1)), placement, team)

            if placement:
                previous = by_team.get(team)
                if previous is None or _placement_rank(placement, medal) < _placement_rank(
                    previous["placement"], previous["medal"]
                ):
                    by_team[team] = {"team": team, "placement": placement, "medal": medal}

        record["entries"] = sorted(
            by_team.values(), key=lambda e: _placement_rank(e["placement"], e["medal"])
        )
        if best_medal is not None:
            record["medal"] = best_medal
            record["team"] = best_team
            record["placement"] = MEDAL_PLACEMENTS_INV[best_medal]
        elif best_numeric is not None:
            record["placement"] = best_numeric[1]
            record["team"] = best_numeric[2]
        records.append(record)

    def totals(rows: List[Dict]) -> Dict:
        out = {"gold": 0, "silver": 0, "bronze": 0, "podiums": 0, "contested": 0}
        for row in rows:
            if row["played"]:
                out["contested"] += 1
            if row["medal"]:
                out[row["medal"]] += 1
                out["podiums"] += 1
        return out

    summer = [r for r in records if r["season"] == "summer"]
    winter = [r for r in records if r["season"] == "winter"]
    return {
        "seasons": records,
        "totals": {"summer": totals(summer), "winter": totals(winter), "all": totals(summer + winter)},
    }

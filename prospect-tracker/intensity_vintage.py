# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""intensity_vintage.py - the dark builder of the game-intensity vintage columns.

REGISTERED BEFORE THIS CODE. docs/diamond-betting.md, the section "Game intensity:
stakes, matchup quality and the postseason" (owner ask 8 of 2026-09-30; plan Part 8,
P8.9, item IX-D1), froze the construction `ix_v1` (intensity_core.py) and the columns
this module captures. Its dated "### Builder landed" amendment names the schema number
the capture rides and the construction hash below. Sections are named by title, never
by letter.

WHAT IT CAPTURES, once a night, inside leaderboard_vintages.reduce_current, and only on
tonight's live snapshot:

- four team columns per club: `ix_elo` (the literature Elo after every final dated
  strictly before the vintage date), `ix_po_pct` and `ix_ws_pct` (postseason and World
  Series probability from the same rest-of-season and bracket simulation the stakes
  use, 20,000 simulations at seed 12345, or exact from the bracket once the regular
  season is over) and `ix_proj_wins` (that simulation's mean final wins; the final
  wins once the regular season is over);
- one game block, `ix_games`, keyed by game_pk, for every game scheduled on the three
  dates after the vintage date: the date, the game type, the series state, dpo_h,
  dpo_a, dws_h, dws_a, G with its Monte Carlo standard error, S, Q, A with the
  capture-time probable ids, D, R and ii;
- one basis block per record, `ix_basis`: the simulations, the seed, the schedule
  source (live or fallback), the remaining pairs, the standings games read, the
  postseason format, G_REF and the construction hash.

THE SECTION'S RULES, and where each one lives.
(1) Old records return None for every ix_ column: leaderboard_vintages.team_row,
    ix_games_block and ix_game read the record's own column list and keys.
(2) inputs_as_of never fills one from live files: betting_model's live path has no
    builder for these columns, so each reads None there.
(3) A game whose game_pk is not in its pricing vintage's block is a stated null, never
    computed late: leaderboard_vintages.ix_game.
(4) N1 never reconstructs an ix_ column: leaderboard_vintages.snapshot asks for this
    capture only on the live clock and only for today's date; a backfill, a forced
    rewrite of another date and a direct reduce_current call store stated nulls.
(5) A construction change is recorded in the section the same day: construction_hash()
    covers intensity_core.py, and test_intensity_vintage.py fails until the section
    names the hash the code carries.
(6) Postseason nights accrue: the builder runs through the postseason on the exact
    bracket, and postseason games are captured like any other.

STRICTLY BEFORE. Every result this module reads is dated strictly before the vintage
date: regular-season finals from the results cache, postseason finals from one
StatsAPI schedule request. Every final dated on or after the vintage date is dropped
before anything is computed, so a capture written late in the day, or rewritten later,
holds the same values as one written before the first pitch. The remaining schedule is
every scheduled regular-season game that is not a final read here, whatever its live
status says, so no status written after the cutoff reaches a value.

DARK MEANS DARK. Nothing served imports this module or reads an ix_ key: no price,
edge, expected value, Kelly figure, slot, badge, record row, chip or page.
test_intensity_vintage.py asserts it by AST and by string. Any number relating a
column, the index, a component or a close variant to a game outcome or a price before
that stage's look disqualifies the stage (the section's disqualification paragraph).

Literals live in intensity_core (copied there, never imported from a served module).
This module adds only the capture window and the names.
"""
from __future__ import annotations

import hashlib
import math
import time
from datetime import date, timedelta
from pathlib import Path

import intensity_core as ic

ROOT = Path(__file__).parent

#: The team columns, in their on-disk order. leaderboard_vintages carries its own copy
#: (IX_TEAM_COLUMNS) and betting_model a third (DARK_IX_TEAM_COLUMNS); a test pins all
#: three equal.
TEAM_COLUMNS = ("ix_elo", "ix_po_pct", "ix_ws_pct", "ix_proj_wins")
GAMES_KEY = "ix_games"
BASIS_KEY = "ix_basis"

#: The fields of one ix_games entry, the section's list plus the clubs and the reason
#: a component is null.
GAME_FIELDS = ("game_pk", "date", "game_type", "home", "away", "series_state",
               "dpo_h", "dpo_a", "dws_h", "dws_a", "G", "G_se", "S", "Q", "A",
               "home_sp", "away_sp", "D", "R", "ii", "a_note", "null_reason")

#: The capture window: the three dates after the vintage date.
DAYS_AHEAD = 3

POSTSEASON_TYPES = ("F", "D", "L", "W")
LISTED_TYPES = "R,F,D,L,W"
SKIPPED_STATES = ("Postponed", "Cancelled")
FINAL_CODES = ("F", "O")
STATSAPI_LEAGUE = {103: "AL", 104: "NL"}
SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
FINALS_NAME = "completed_games.json"                      # under .cache/betting/
STANDINGS_TEMPLATE = "statsapi_standings_{season}.json"   # under .cache/
POSTSEASON_FROM = "{season}-09-01"
SEASON_SPAN = ("{season}-03-01", "{season}-11-05")        # proj_current's season span

PROVENANCE = "live"
SOURCE_LIVE = "live"
SOURCE_FALLBACK = "fallback"
MODE_REGULAR = "regular season"
MODE_POSTSEASON = "postseason"

# Why a value is null. Each is a stated fact written into the record.
NO_INPUTS = "ABSENT: the game-intensity inputs could not be read tonight"
NO_FIELD = "the thirty-club field could not be built"
NO_FORMAT = "no registered postseason format for this season"
NO_SCHEDULE = "the season schedule could not be read"
NOT_ON_SCHEDULE = "this game is not on the remaining regular-season schedule"
POST_IN_REGULAR = "a postseason game while regular-season games remain"
REGULAR_IN_POST = "a regular-season game after the regular season ended"
NO_SEEDS = "the postseason seeds could not be read from the standings"
NOT_IN_BRACKET = "this game does not fit the bracket recorded before the vintage date"
NO_BRACKET = "the postseason bracket could not be evaluated"
A_UNANNOUNCED = "probables not posted at capture"
A_OFF_BOARD = "a probable is not a qualified starter on the vintage's starter board"
R_NOTE = ("R is a label with weight 0 (INT-A4) and no rivalry table is frozen, so it "
          "is null on every game")


# ---------------------------------------------------------------------------
# The construction hash (rule 5)
# ---------------------------------------------------------------------------
def construction_hash(path: Path | None = None) -> str:
    """The first 16 hex digits of the sha256 of intensity_core.py with its line
    endings normalized to LF, so a checkout's line-ending setting cannot move it and
    any edit to the construction does."""
    p = Path(path) if path is not None else ROOT / "intensity_core.py"
    raw = p.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _r(x, nd: int = 6):
    if x is None:
        return None
    v = float(x)
    if math.isnan(v):
        return None
    return round(v, nd)


def window(on_date: str) -> list[str]:
    """The three dates after the vintage date, as ISO strings."""
    d0 = date.fromisoformat(str(on_date)[:10])
    return [(d0 + timedelta(days=k)).isoformat() for k in range(1, DAYS_AHEAD + 1)]


def _fmt(season: int) -> str | None:
    try:
        return ic.format_for_season(int(season))
    except ValueError:
        return None


def starter_board(starter_blob: dict | None) -> dict:
    """{mlbam: SEM+} over the qualified starters of the vintage's own starter board,
    the pool the percentile behind A is taken over."""
    out = {}
    for s in (starter_blob or {}).get("starters") or []:
        pid = _int(s.get("mlbam"))
        if pid is not None and s.get("qualified") and s.get("sem_plus") is not None:
            out[pid] = float(s["sem_plus"])
    return out


# ---------------------------------------------------------------------------
# The one read (network and disk). Tests replace load_inputs; build_from_inputs is pure.
# ---------------------------------------------------------------------------
def _get_json(url: str, params: dict) -> dict | None:
    try:
        import feed_cache
        resp = feed_cache.SESSION.get(url, params=params, timeout=30)
        resp.raise_for_status()
        out = resp.json()
        return out if isinstance(out, dict) else None
    except Exception:                                          # noqa: BLE001
        return None


def _read_json(p: Path):
    import json
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _club(side: dict) -> str | None:
    from trades import canonical_org_from_id
    team = (side or {}).get("team") or {}
    org = canonical_org_from_id(team.get("id"), team.get("name") or "")
    return org if org and len(org) <= 3 else None


def schedule_games(raw: dict | None, *, probables: bool = False) -> list[dict]:
    """The games of a raw /schedule response: game_pk, date (the official date),
    game_type, home, away, state (detailedState), coded (codedGameState) and, with
    probables=True, the two listed probable ids. No score is read here."""
    out = []
    for d in (raw or {}).get("dates") or []:
        for g in d.get("games") or []:
            teams = g.get("teams") or {}
            home, away = _club(teams.get("home")), _club(teams.get("away"))
            pk = _int(g.get("gamePk"))
            if pk is None or not home or not away:
                continue
            st = g.get("status") or {}
            row = {"game_pk": pk, "date": str(g.get("officialDate") or d.get("date") or "")[:10],
                   "game_type": g.get("gameType") or "R", "home": home, "away": away,
                   "state": st.get("detailedState") or "", "coded": st.get("codedGameState") or ""}
            if probables:
                for side, key in (("home", "home_sp"), ("away", "away_sp")):
                    pp = (teams.get(side) or {}).get("probablePitcher") or {}
                    row[key] = _int(pp.get("id"))
            out.append(row)
    return out


def postseason_finals(raw: dict | None) -> list[dict]:
    """The final postseason games of a raw /schedule response: game_pk, date, the two
    clubs and the winner. A game counts only when its codedGameState is F or O (the
    postseason module's rule)."""
    out = []
    for d in (raw or {}).get("dates") or []:
        for g in d.get("games") or []:
            if (g.get("gameType") or "") not in POSTSEASON_TYPES:
                continue
            if ((g.get("status") or {}).get("codedGameState") or "") not in FINAL_CODES:
                continue
            teams = g.get("teams") or {}
            home, away = _club(teams.get("home")), _club(teams.get("away"))
            pk = _int(g.get("gamePk"))
            if pk is None or not home or not away:
                continue
            hw = (teams.get("home") or {}).get("isWinner")
            aw = (teams.get("away") or {}).get("isWinner")
            if hw is True and aw is not True:
                winner = home
            elif aw is True and hw is not True:
                winner = away
            else:
                continue
            out.append({"game_pk": pk,
                        "date": str(g.get("officialDate") or d.get("date") or "")[:10],
                        "home": home, "away": away, "winner": winner})
    return out


def load_inputs(on_date: str, *, cache_dir: Path | None = None) -> dict | None:
    """Everything the builder reads, in one place: the results cache, the season's
    regular-season schedule (proj_current's cached /schedule read), one /schedule
    request for the three dates after the vintage with the probables, one /schedule
    request for the postseason finals before the vintage date when the window or the
    calendar calls for it, and the standings cache. None when the field cannot be
    built at all. Nothing here filters by date; build_from_inputs does."""
    V = str(on_date)[:10]
    season = int(V[:4])
    cache = Path(cache_dir) if cache_dir is not None else ROOT / ".cache"
    import proj_current as pc
    divisions = {o: (dv.split("_")[0], dv) for dv, members in pc._DIVISIONS.items()
                 for o in members}
    finals = _read_json(cache / "betting" / FINALS_NAME)
    finals = [r for r in (finals or []) if isinstance(r, dict)
              and str(r.get("season") or str(r.get("date") or "")[:4]) == str(season)]
    span = tuple(s.format(season=season) for s in SEASON_SPAN)
    raw_season = pc._fetch_schedule_raw(*span)
    season_schedule = (schedule_games(raw_season) if raw_season and "dates" in raw_season
                       else None)
    win = window(V)
    raw_listed = _get_json(SCHEDULE_URL, {"sportId": 1, "startDate": win[0],
                                          "endDate": win[-1], "gameType": LISTED_TYPES,
                                          "hydrate": "probablePitcher"})
    if raw_listed is not None and "dates" in raw_listed:
        listed, source = schedule_games(raw_listed, probables=True), SOURCE_LIVE
    elif season_schedule is not None:
        listed = [dict(g, home_sp=None, away_sp=None) for g in season_schedule
                  if g["date"] in win]
        source = SOURCE_FALLBACK
    else:
        listed, source = None, None
    post = None
    start = POSTSEASON_FROM.format(season=season)
    prev = (date.fromisoformat(V) - timedelta(days=1)).isoformat()
    wants_post = (any(g["game_type"] in POSTSEASON_TYPES for g in listed or [])
                  or (season_schedule is not None
                      and not any(g["date"] >= V for g in season_schedule)))
    if wants_post and prev >= start:
        raw_post = _get_json(SCHEDULE_URL, {"sportId": 1, "startDate": start,
                                            "endDate": prev, "gameType": "F,D,L,W"})
        post = postseason_finals(raw_post) if raw_post is not None else None
    standings = (_read_json(cache / STANDINGS_TEMPLATE.format(season=season)) or {})
    return {"season": season, "divisions": divisions, "finals": finals,
            "season_schedule": season_schedule, "listed": listed,
            "schedule_source": source, "post_finals": post,
            "standings": standings.get("records") or []}


# ---------------------------------------------------------------------------
# The pure build
# ---------------------------------------------------------------------------
def _final_before(r: dict, V: str, divisions: dict) -> bool:
    return (isinstance(r, dict) and r.get("home_org") in divisions
            and r.get("away_org") in divisions
            and r.get("home_runs") is not None and r.get("away_runs") is not None
            and bool(r.get("date")) and str(r["date"])[:10] < V)


def _remaining(schedule: list, booked: set, V: str, divisions: dict) -> tuple[list, int]:
    """[(game_pk, date, home, away)] in schedule order: every scheduled
    regular-season game between two clubs of the field that is not a final read here,
    one row per game_pk; a listing postponed or cancelled at capture is skipped (its
    rescheduled listing, when there is one, counts). Also the count of rows dated
    before V, games the results cache had not booked by the vintage date."""
    seen, rows = set(), []
    for g in sorted(schedule, key=lambda r: (r["date"], r["game_pk"])):
        pk = g["game_pk"]
        if (pk in seen or pk in booked or g.get("game_type", "R") != "R"
                or g.get("state") in SKIPPED_STATES
                or g["home"] not in divisions or g["away"] not in divisions):
            continue
        seen.add(pk)
        rows.append((pk, g["date"], g["home"], g["away"]))
    return rows, sum(1 for r in rows if r[1] < V)


def _standings_flags(records: list) -> dict:
    """{org: {'league', 'division_rank', 'league_rank', 'wild_card_rank'}}."""
    from trades import canonical_org_from_id
    out = {}
    for rec in records or []:
        lg = STATSAPI_LEAGUE.get(_int((rec.get("league") or {}).get("id")))
        for tr in rec.get("teamRecords") or []:
            team = tr.get("team") or {}
            org = canonical_org_from_id(team.get("id"), team.get("name"))
            if not org:
                continue
            out[org] = {"league": lg, "division_rank": _int(tr.get("divisionRank")),
                        "league_rank": _int(tr.get("leagueRank")),
                        "wild_card_rank": _int(tr.get("wildCardRank"))}
    return out


def seeds_from_standings(records: list, divisions: dict, fmt: str) -> dict | None:
    """{league: (seed 1, ...)}: the three division winners by league rank, then the
    wild cards by wild-card rank. None unless every league reads exactly the format's
    count."""
    n = 5 if fmt == "five" else 6
    flags = _standings_flags(records)
    out = {}
    for lg in ("AL", "NL"):
        clubs = [o for o in divisions if divisions[o][0] == lg and o in flags]

        def rank(o, key):
            v = flags[o].get(key)
            return 99 if v is None else v
        champs = sorted((o for o in clubs if flags[o].get("division_rank") == 1),
                        key=lambda o: (rank(o, "league_rank"), o))
        rest = sorted((o for o in clubs if o not in champs
                       and flags[o].get("wild_card_rank") is not None),
                      key=lambda o: (rank(o, "wild_card_rank"), rank(o, "league_rank"), o))
        if len(champs) != 3 or len(rest) < n - 3:
            return None
        out[lg] = tuple(champs + rest[:n - 3])
    return out


def _series_state(finals: list) -> dict:
    state: dict = {}
    seen = set()
    for f in sorted(finals, key=lambda r: (r["date"], r["game_pk"])):
        if f["game_pk"] in seen:
            continue
        seen.add(f["game_pk"])
        key = frozenset((f["home"], f["away"]))
        st = state.setdefault(key, {f["home"]: 0, f["away"]: 0})
        st[f["winner"]] = st.get(f["winner"], 0) + 1
    return state


def _null_entry(g: dict, why: str) -> dict:
    e = {k: None for k in GAME_FIELDS}
    e.update({"game_pk": g["game_pk"], "date": g.get("date"),
              "game_type": g.get("game_type"), "home": g.get("home"),
              "away": g.get("away"), "home_sp": g.get("home_sp"),
              "away_sp": g.get("away_sp"), "null_reason": why})
    return e


def _entry(g: dict, st: dict, Q: float, board: dict, divisions: dict,
           series_state: dict | None) -> dict:
    S = ic.stakes_score(st["G"])
    A = ic.starters_score(g.get("home_sp"), g.get("away_sp"), board)
    D = ic.division_flag((divisions.get(g["home"]) or (None, None))[1],
                         (divisions.get(g["away"]) or (None, None))[1])
    a_note = None
    if A is None:
        a_note = (A_UNANNOUNCED if g.get("home_sp") is None or g.get("away_sp") is None
                  else A_OFF_BOARD)
    return {
        "game_pk": g["game_pk"], "date": g["date"], "game_type": g["game_type"],
        "home": g["home"], "away": g["away"], "series_state": series_state,
        "dpo_h": _r(st.get("dpo_h")), "dpo_a": _r(st.get("dpo_a")),
        "dws_h": _r(st["dws_h"]), "dws_a": _r(st["dws_a"]),
        "G": _r(st["G"]), "G_se": _r(st.get("G_se")),
        "S": _r(S), "Q": _r(Q), "A": _r(A),
        "home_sp": g.get("home_sp"), "away_sp": g.get("away_sp"),
        "D": D, "R": None, "ii": ic.index_value(S, Q, A, D),
        "a_note": a_note, "null_reason": None,
    }


def build_from_inputs(inputs: dict, on_date: str, board: dict, *,
                      n_sims: int = ic.SIMS, seed: int = ic.SEED) -> dict:
    """The capture for one vintage date from already-read inputs, deterministic at a
    seed. Returns {'values': {column: {org: value}}, 'notes': {column: basis},
    'games': {str(game_pk): entry}, 'basis': {...}}."""
    V = str(on_date)[:10]
    season = int(V[:4])
    win = window(V)
    divisions = inputs.get("divisions") or {}
    orgs = sorted(divisions)
    fmt = _fmt(season)
    finals = [r for r in inputs.get("finals") or [] if _final_before(r, V, divisions)]
    finals_seen, uniq = set(), []
    for r in sorted(finals, key=lambda r: (str(r["date"]), r.get("game_pk") or 0)):
        if r.get("game_pk") in finals_seen:
            continue
        finals_seen.add(r.get("game_pk"))
        uniq.append(r)
    finals = uniq
    through = max((str(r["date"])[:10] for r in finals), default=None)
    post_all = inputs.get("post_finals")
    post = ([f for f in post_all if str(f.get("date") or "") < V
             and f.get("home") in divisions and f.get("away") in divisions]
            if post_all is not None else None)
    listed_all = inputs.get("listed")
    listed, seen = [], set()
    for g in sorted(listed_all or [], key=lambda r: (r["date"], r["game_pk"])):
        if (g["date"] in win and g["game_pk"] not in seen
                and g["home"] in divisions and g["away"] in divisions
                and g.get("state") not in SKIPPED_STATES):
            seen.add(g["game_pk"])
            listed.append(g)
    basis = {
        "construction": ic.CONSTRUCTION, "construction_hash": construction_hash(),
        "provenance": PROVENANCE, "status": "built", "mode": None,
        "simulations": int(n_sims), "seed": int(seed), "home_edge": ic.HOME_EDGE,
        "g_ref": ic.G_REF, "window": [win[0], win[-1]],
        "schedule_source": inputs.get("schedule_source"),
        "listed_games": len(listed), "computed_games": 0, "stated_null_games": 0,
        "remaining_pairs": None, "unbooked_before_vintage": None,
        "season_shortfall_clubs": None, "standings_games_read": len(finals),
        "finals_through": through, "postseason_format": fmt,
        "postseason_finals_read": None if post is None else len(post),
        "starters_on_board": len(board),
    }
    values = {c: {} for c in TEAM_COLUMNS}
    notes = {}
    games: dict = {}

    def null_all(why: str):
        for g in listed:
            games[str(g["game_pk"])] = _null_entry(g, why)

    if len(orgs) != 30:
        basis["status"] = "unavailable"
        for c in TEAM_COLUMNS:
            notes[c] = f"ABSENT: {NO_FIELD}"
        null_all(NO_FIELD)
        return _finish(values, notes, games, basis)

    wins = {o: 0 for o in orgs}
    losses = {o: 0 for o in orgs}
    for r in finals:
        hw = int(r["home_runs"]) > int(r["away_runs"])
        wins[r["home_org"] if hw else r["away_org"]] += 1
        losses[r["away_org"] if hw else r["home_org"]] += 1
    ratings = ic.elo_ratings_before(finals, V)
    talent = ic.talent_from_ratings(ratings, orgs)
    values["ix_elo"] = {o: _r(ratings.get(o, ic.ELO_BASE), 2) for o in orgs}
    notes["ix_elo"] = (f"game-intensity builder ({ic.CONSTRUCTION}, construction "
                       f"{basis['construction_hash']}): literature Elo (base "
                       f"{ic.ELO_BASE:g}, K {ic.ELO_K:g}, {ic.ELO_HOME_POINTS:g} points of "
                       f"home field, flat start each season) after {len(finals)} "
                       f"regular-season finals dated before {V}"
                       + (f" (through {through})" if through else ""))
    if fmt is None:
        basis["status"] = "unavailable"
        for c in TEAM_COLUMNS[1:]:
            notes[c] = f"ABSENT: {NO_FORMAT}"
        null_all(NO_FORMAT)
        return _finish(values, notes, games, basis)

    schedule = inputs.get("season_schedule")
    remaining, unbooked = ([], 0) if schedule is None else _remaining(
        schedule, finals_seen, V, divisions)
    if schedule is not None:
        left = {o: 0 for o in orgs}
        for _, _, h, a in remaining:
            left[h] += 1
            left[a] += 1
        basis.update({"remaining_pairs": len(remaining), "unbooked_before_vintage": unbooked,
                      "season_shortfall_clubs": sum(
                          1 for o in orgs if wins[o] + losses[o] + left[o] != 162)})
    if remaining:
        mode = MODE_REGULAR
    elif schedule is not None or any(g["game_type"] in POSTSEASON_TYPES for g in listed):
        mode = MODE_POSTSEASON
    else:
        mode = None
    basis["mode"] = mode

    if mode is None:
        basis["status"] = "unavailable"
        for c in TEAM_COLUMNS[1:]:
            notes[c] = f"ABSENT: {NO_SCHEDULE}"
        null_all(NO_SCHEDULE)
        return _finish(values, notes, games, basis)

    if mode == MODE_REGULAR:
        _build_regular(remaining, listed, wins, talent, divisions, orgs, fmt, board,
                       values, notes, games, basis, n_sims=n_sims, seed=seed)
    else:
        _build_postseason(inputs.get("standings") or [], post, listed, wins, talent,
                          divisions, orgs, fmt, board, values, notes, games, basis)
    return _finish(values, notes, games, basis)


def _build_regular(remaining, listed, wins, talent, divisions, orgs, fmt, board,
                   values, notes, games, basis, *, n_sims, seed):
    pairs = [(h, a) for _, _, h, a in remaining]
    index = {pk: k for k, (pk, _, _, _) in enumerate(remaining)}
    teams = {o: {"wins": wins[o], "p": talent[o], "league": divisions[o][0],
                 "div": divisions[o][1]} for o in orgs}
    base = ic.simulate_forced(teams, pairs, forced=None, fmt=fmt, n_sims=n_sims, seed=seed)
    n = base["n_sims"]
    proj = {o: base["win_sum"][o] / n for o in orgs}
    values["ix_po_pct"] = {o: _r(base["playoff"][o] / n) for o in orgs}
    values["ix_ws_pct"] = {o: _r(base["ws"][o] / n) for o in orgs}
    values["ix_proj_wins"] = {o: _r(proj[o], 3) for o in orgs}
    sim_note = (f"game-intensity builder ({ic.CONSTRUCTION}, construction "
                f"{basis['construction_hash']}): the rest-of-season and bracket "
                f"simulation ({fmt}-club format, home edge {ic.HOME_EDGE}) over "
                f"{len(pairs)} remaining regular-season games, {n:,} simulations at "
                f"seed {seed}, Elo talent after {basis['standings_games_read']} finals")
    notes["ix_po_pct"] = sim_note + "; the share of simulations reaching the postseason"
    notes["ix_ws_pct"] = sim_note + "; the share of simulations winning the World Series"
    notes["ix_proj_wins"] = sim_note + "; mean final wins"
    found = []
    for g in listed:
        if g["game_type"] in POSTSEASON_TYPES:
            games[str(g["game_pk"])] = _null_entry(g, POST_IN_REGULAR)
        elif g["game_pk"] not in index:
            games[str(g["game_pk"])] = _null_entry(g, NOT_ON_SCHEDULE)
        else:
            found.append(g)
    if found:
        res = ic.regular_season_stakes(teams, pairs, [index[g["game_pk"]] for g in found],
                                       fmt=fmt, n_sims=n_sims, seed=seed)
        for g, st in zip(found, res["games"]):
            Q = ic.matchup_quality(proj, g["home"], g["away"])
            games[str(g["game_pk"])] = _entry(g, st, Q, board, divisions, None)


def _build_postseason(standings, post, listed, wins, talent, divisions, orgs, fmt,
                      board, values, notes, games, basis):
    values["ix_proj_wins"] = {o: float(wins[o]) for o in orgs}
    notes["ix_proj_wins"] = (f"game-intensity builder ({ic.CONSTRUCTION}): the regular "
                             f"season is over; final wins from "
                             f"{basis['standings_games_read']} finals")
    seeds = seeds_from_standings(standings, divisions, fmt)
    if seeds is None or post is None:
        why = NO_SEEDS if seeds is None else "the postseason finals could not be read"
        for c in ("ix_po_pct", "ix_ws_pct"):
            notes[c] = f"ABSENT: {why}"
        for g in listed:
            games[str(g["game_pk"])] = _null_entry(g, why)
        return
    seeded = {o for s in seeds.values() for o in s}
    state = _series_state(post)
    values["ix_po_pct"] = {o: (1.0 if o in seeded else 0.0) for o in orgs}
    notes["ix_po_pct"] = (f"game-intensity builder ({ic.CONSTRUCTION}): the regular season "
                          f"is over; 1 for the {len(seeded)} seeded clubs of the final "
                          f"standings, 0 for the rest")
    try:
        wsp = ic.world_series_probs(seeds, wins, talent, fmt=fmt, series_state=state)
        values["ix_ws_pct"] = {o: _r(wsp.get(o, 0.0)) for o in orgs}
        notes["ix_ws_pct"] = (f"game-intensity builder ({ic.CONSTRUCTION}, construction "
                              f"{basis['construction_hash']}): the exact bracket "
                              f"({fmt}-club format, home edge {ic.HOME_EDGE}) under the "
                              f"series states of {len(post)} postseason finals dated "
                              f"before the vintage date, Elo talent")
    except (ValueError, KeyError) as exc:
        notes["ix_ws_pct"] = f"ABSENT: {NO_BRACKET} ({type(exc).__name__})"
    q = ic.percentile_ranks({o: wins[o] for o in orgs})
    for g in listed:
        pk = str(g["game_pk"])
        if g["game_type"] not in POSTSEASON_TYPES:
            games[pk] = _null_entry(g, REGULAR_IN_POST)
            continue
        try:
            st = ic.postseason_stakes(seeds, wins, talent, g["home"], g["away"], fmt=fmt,
                                      series_state=state)
        except (ValueError, KeyError):
            games[pk] = _null_entry(g, NOT_IN_BRACKET)
            continue
        series = {"round": st["game_type"], "best_of": st["best_of"],
                  "game_number": st["game_number"], "wins": dict(st["state"])}
        games[pk] = _entry(g, st, min(q[g["home"]], q[g["away"]]), board, divisions,
                           series)


def _finish(values, notes, games, basis) -> dict:
    basis["computed_games"] = sum(1 for e in games.values() if e.get("null_reason") is None)
    basis["stated_null_games"] = sum(1 for e in games.values()
                                     if e.get("null_reason") is not None)
    return {"values": values, "notes": notes, "games": games, "basis": basis}


# ---------------------------------------------------------------------------
# The entry point leaderboard_vintages calls
# ---------------------------------------------------------------------------
def unavailable(why: str) -> dict:
    """The block for a night the capture cannot run: every column a stated null."""
    return {"columns": {c: {"values": {}, "basis": why} for c in TEAM_COLUMNS},
            "games": None,
            "basis": {"construction": ic.CONSTRUCTION, "provenance": PROVENANCE,
                      "status": "unavailable", "reason": why}}


def build_columns(*, on_date: str, starter_blob: dict | None = None,
                  inputs: dict | None = None, n_sims: int = ic.SIMS,
                  seed: int = ic.SEED) -> dict:
    """{'columns': {column: {'values': {org: v}, 'basis': str}}, 'games': {...} | None,
    'basis': {...}}. Never raises: a failure is a stated null for every column."""
    t0 = time.monotonic()
    board = starter_board(starter_blob)
    if inputs is None:
        try:
            inputs = load_inputs(on_date)
        except Exception as exc:                               # noqa: BLE001
            return unavailable(f"{NO_INPUTS} ({type(exc).__name__}: {exc})")
    if not inputs:
        return unavailable(NO_INPUTS)
    try:
        got = build_from_inputs(inputs, on_date, board, n_sims=n_sims, seed=seed)
    except Exception as exc:                                   # noqa: BLE001
        return unavailable(f"ABSENT: the game-intensity builder raised "
                           f"{type(exc).__name__}: {exc}")
    cols = {}
    for c in TEAM_COLUMNS:
        vals = {o: v for o, v in (got["values"].get(c) or {}).items() if v is not None}
        cols[c] = {"values": vals,
                   "basis": got["notes"].get(c) or "ABSENT: no value captured"}
    got["basis"]["seconds"] = round(time.monotonic() - t0, 1)
    return {"columns": cols, "games": got["games"], "basis": got["basis"]}

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Dugout context for /betting/: In-Game Management club-season figures rendered
BESIDE a price and read into none of it. Reads data/management_board.json only,
never a per-club decision ledger file. Imports no betting module (the seam is one
way).

THE WALL. `build_block` reads exactly three things off each bet (game_pk, away.org,
home.org), copies nothing else, mutates nothing, and returns a block that carries no
probability, edge, expected value, Kelly figure, slot, badge or record row. Every
sentence in the block is either a board string copied verbatim or a constant below;
every figure is the board's value unchanged (no rescaling, no rounding beyond what the
board did, no 100+10z, no rank, no plus suffix). Realized values are per family and
never summed; the board's not-summed family is not carried. No key at any depth
contains "dv" or "decision" (the management gate's rule). betting_export reads this
module through one seam and passes the result to nothing; test_betting_mgmt_fence.py
and test_betting_dugout.py pin all of it.

This module has NO write target and NO module-level Path that resolves onto a served
artifact: the board's file name is a string constant and the directory is a parameter,
so test_betting_sidecar_isolation's census imports it cleanly.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent
BOARD_NAME = "management_board.json"          # a name, not a Path; never a ledger file
SOURCE_MODULE = "In-Game Management"
BOARD_PUBLIC_PATH = "/data/management_board.json"

HEAD = "Dugout context, not priced"
NOT_PRICED_SENTENCE = (
    "Dugout context sits beside the price and enters none of it. No probability, "
    "edge, expected value, Kelly figure, slot, badge or record row on this page "
    "reads anything from In-Game Management, and no In-Game Management figure is "
    "a pricer input.")
SOURCE_TEMPLATE = ("Source: In-Game Management, club-season {season} through {through}, "
                   "corpus built {corpus_built_at}, read from data/management_board.json.")
STYLE_HEAD = "Style this season"
RATES_HEAD = "On its own scale"
SHAPE_HEAD = "Bullpen shape"
SHAPE_DARK_SENTENCE = (
    "Entries by leverage at entry and inherited runners scored live in the per-club "
    "decision ledger files, which this page never reads; the club page draws them.")
REALIZED_HEAD = "Realized value this season, per family, never summed"
BELOW_FLOOR_TEMPLATE = "below the floor of {floor} ({n} this season)"
LINK_TEMPLATE = "Open {club} on In-Game Management"
NO_ROW_TEMPLATE = "No {season} club-season row for {club} on the management board."
BOARD_ABSENT = ("data/management_board.json is not on this build; the In-Game "
                "Management board step (6b7c) writes it.")
CLUBS_NOT_BUILT = "The management board's clubs block is not built ({status})."
SEASON_ABSENT = ("The management board carries no {season} club-season rows yet; "
                 "the corpus is rebuilt by hand and the board follows it.")
CLUB_LINK_TEMPLATE = "/management/#section=clubs&team={club}&season={season}"
CLUB_LINK_NO_SEASON_TEMPLATE = "/management/#section=clubs&team={club}"
DRILL_LINK_TEMPLATE = ("/management/#section=decisions&team={club}&season={season}"
                       "&family={{family}}")

STYLE_COLUMNS = (   # key on the board row, label, basis sentence (the only typed copy)
    ("z_hook", "Hook z", "starter pitch count at removal; a negative z is an earlier hook"),
    ("z_pen", "Pen z", "pitching changes per game"),
    ("z_bench", "Bench z", "pinch hitters plus pinch runners per game"),
    ("z_ibb", "IBB z", "intentional walks per game"),
    ("z_visit", "Visit z", "mound visits per game"),
)
RATE_COLUMNS = (
    ("hook_median_pitches", "Hook, median pitches", "pitches", 0),
    ("pen_per_game", "Pitching changes per game", "per game", 2),
    ("bench_per_game", "Bench moves per game", "per game", 2),
    ("ibb_per_game", "Intentional walks per game", "per game", 2),
    ("visit_per_game", "Mound visits per game", "per game", 2),
)
REALIZED_FAMILIES = ("pitching_change", "pinch_hit", "pinch_run",
                     "intentional_walk", "bunt", "steal")   # the board's summed set
UNITS_COPIED = ("mwpa", "z")        # the two board.decisions.units the block prints;
                                    # "li" is not printed and "dvs" is a forbidden key
FORBIDDEN_KEY_SUBSTRINGS = ("dv", "decision")               # the management gate rule
PRICED_KEYS = ("model_prob", "market_fair_prob", "edge", "ev_per_unit",
               "ev_per_unit_if_no_push", "kelly_full", "kelly_quarter", "odds",
               "fair_odds", "implied_prob", "p_home", "p_away", "lam_home",
               "lam_away", "fair_total", "stake_units", "suggested_units")


def load_board(data_dir: Path | None = None) -> dict | None:
    """The board, or None when it is absent or unreadable. Opens `data_dir / BOARD_NAME`
    and nothing else."""
    base = Path(data_dir) if data_dir is not None else ROOT / "data"
    try:
        return json.loads((base / BOARD_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def club_row(board: dict, club: str, season: int) -> dict | None:
    """The clubs.rows entry whose club code and season match exactly. Codes are site
    canonical on both sides (the board's 2026 rows carry ATH, not OAK)."""
    rows = (((board or {}).get("clubs") or {}).get("rows")) or []
    for r in rows:
        if r.get("club") == club and r.get("season") == season:
            return r
    return None


def _games_map(bets: list) -> dict:
    """{game_pk: {away, home}} for every slate game, reading only the three keys the
    block needs. Never touches a priced key; never mutates a bet."""
    games: dict = {}
    for b in bets or []:
        if not isinstance(b, dict):
            continue
        pk = b.get("game_pk")
        away = (b.get("away") or {}).get("org") if isinstance(b.get("away"), dict) else None
        home = (b.get("home") or {}).get("org") if isinstance(b.get("home"), dict) else None
        if pk is None or not away or not home:
            continue
        games[str(pk)] = {"away": str(away), "home": str(home)}
    return games


def _season_of(slate_date) -> int | None:
    try:
        return int(str(slate_date)[:4])
    except (TypeError, ValueError):
        return None


def _base(season: int | None, games: dict) -> dict:
    """The constants every block carries, built or dark, so the client always has the
    head and the not-priced sentence to print."""
    return {
        "status": "unavailable",
        "blocker": None,
        "source_module": SOURCE_MODULE,
        "source": BOARD_PUBLIC_PATH,
        "board_generated_at": None,
        "corpus_built_at": None,
        "season": season,
        "through": None,
        "season_rows_present": False,
        "season_note": None,
        "head": HEAD,
        "not_priced_sentence": NOT_PRICED_SENTENCE,
        "source_label": None,
        "style_head": STYLE_HEAD,
        "style_sentence": None,
        "style_columns": [{"key": k, "label": lab, "basis": basis}
                          for k, lab, basis in STYLE_COLUMNS],
        "rates_head": RATES_HEAD,
        "rate_columns": [{"key": k, "label": lab, "unit": unit, "decimals": dec}
                         for k, lab, unit, dec in RATE_COLUMNS],
        "shape_head": SHAPE_HEAD,
        "shape_dark_sentence": SHAPE_DARK_SENTENCE,
        "league": None,
        "realized_head": REALIZED_HEAD,
        "realized_sentence": None,
        "agent_sentence": None,
        "overlap_note": None,
        "units": {},
        "realized_families": [],
        "floors": {},
        "games_floor": None,
        "plus_metric": False,
        "no_cross_family_total": True,
        "below_floor_template": BELOW_FLOOR_TEMPLATE,
        "games": games,
        "clubs": {},
    }


def _dark(season: int | None, games: dict, blocker: str) -> dict:
    out = _base(season, games)
    out["blocker"] = blocker
    return out


def _club_entry(org: str, season: int | None, row: dict | None, *, codes: dict,
                league_hook_median) -> dict:
    link_label = LINK_TEMPLATE.format(club=org)
    if row is None:
        return {
            "club": org,
            "statsapi_code": codes.get(org),
            "season": season,
            "row_note": NO_ROW_TEMPLATE.format(season=season, club=org),
            "style": None, "rates": None, "shape": None, "counts": None,
            "realized": None,
            "link": CLUB_LINK_NO_SEASON_TEMPLATE.format(club=org),
            "drill_link": None,
            "link_label": link_label,
        }
    return {
        "club": org,
        "statsapi_code": codes.get(org, org),
        "season": season,
        "games": row.get("games"),
        "partial": row.get("partial"),
        "n_all": row.get("n_all"),
        "mean_li": row.get("mean_li"),
        "share_li_high": row.get("share_li_high"),
        "style": {k: row.get(k) for k, _lab, _basis in STYLE_COLUMNS},
        "rates": {k: row.get(k) for k, _lab, _unit, _dec in RATE_COLUMNS},
        "shape": {
            "hook_median_pitches": row.get("hook_median_pitches"),
            "pen_per_game": row.get("pen_per_game"),
            "league_hook_median_pitches": league_hook_median,
            "li_at_entry": None,
            "li_at_entry_blocker": SHAPE_DARK_SENTENCE,
        },
        "counts": {f"n_{f}": row.get(f"n_{f}") for f in REALIZED_FAMILIES},
        "realized": {f"mwpa_{f}": row.get(f"mwpa_{f}") for f in REALIZED_FAMILIES},
        "link": CLUB_LINK_TEMPLATE.format(club=org, season=season),
        "drill_link": DRILL_LINK_TEMPLATE.format(club=org, season=season),
        "link_label": link_label,
        "row_note": None,
    }


def forbidden_keys(obj, path: str = "") -> list[str]:
    """Every key at any depth that carries a FORBIDDEN_KEY_SUBSTRINGS entry or a
    PRICED_KEYS name. Values are not scanned (deep links live in values)."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            ks = str(k)
            here = f"{path}.{ks}" if path else ks
            if any(s in ks for s in FORBIDDEN_KEY_SUBSTRINGS) or ks in PRICED_KEYS:
                hits.append(here)
            hits.extend(forbidden_keys(v, here))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(forbidden_keys(v, f"{path}[{i}]"))
    return hits


def build_block(bets: list, slate_date: str, *, data_dir: Path | None = None,
                board: dict | None = None) -> dict:
    """The `dugout_context` block for one slate. Never raises into the exporter: a
    missing board, an unbuilt clubs block or a season without rows each return a
    block whose status and blocker say so, with `games` still populated."""
    games = _games_map(bets)
    season = _season_of(slate_date)
    try:
        return _build(games, season, data_dir=data_dir, board=board)
    except Exception as exc:                                   # noqa: BLE001
        return _dark(season, games,
                     f"betting_dugout could not build the block ({type(exc).__name__}: {exc})")


def _build(games: dict, season: int | None, *, data_dir, board) -> dict:
    if board is None:
        board = load_board(data_dir)
    if not isinstance(board, dict):
        return _dark(season, games, BOARD_ABSENT)
    clubs = board.get("clubs") or {}
    if clubs.get("status") != "built":
        return _dark(season, games, CLUBS_NOT_BUILT.format(status=clubs.get("status")))
    decisions = board.get("decisions") or {}
    families = decisions.get("families") or {}
    floors_all = clubs.get("floors") or {}
    codes = clubs.get("statsapi_codes") or {}
    hook = ((families.get("pitching_change") or {}).get("hook_pitch_count")) or {}
    league_hook_median = hook.get("median")
    rows = clubs.get("rows") or []
    present = any(r.get("season") == season for r in rows)
    through = (decisions.get("through_by_season") or {}).get(str(season))
    units_all = decisions.get("units") or {}

    out = _base(season, games)
    out.update({
        "status": "built",
        "blocker": None,
        "board_generated_at": board.get("generated_at"),
        "corpus_built_at": decisions.get("corpus_built_at"),
        "through": through,
        "season_rows_present": present,
        "season_note": None if present else SEASON_ABSENT.format(season=season),
        "source_label": SOURCE_TEMPLATE.format(
            season=season, through=through or "an unrecorded date",
            corpus_built_at=decisions.get("corpus_built_at") or "an unrecorded time"),
        "style_sentence": clubs.get("style_sentence"),
        "league": {
            "hook_median_pitches": league_hook_median,
            "hook_p10": hook.get("p10"),
            "hook_p90": hook.get("p90"),
            "hook_n": hook.get("n"),
        },
        "realized_sentence": decisions.get("realized_sentence"),
        "agent_sentence": clubs.get("agent_sentence"),
        "overlap_note": decisions.get("overlap_note"),
        "units": {u: units_all.get(u) for u in UNITS_COPIED if u in units_all},
        "realized_families": [
            {"key": f, "label": (families.get(f) or {}).get("label") or f,
             "floor": floors_all.get(f)} for f in REALIZED_FAMILIES],
        # The six summed families only: the board's not-summed family never appears
        # on this surface, not even as a floor.
        "floors": {f: floors_all.get(f) for f in REALIZED_FAMILIES if f in floors_all},
        "games_floor": clubs.get("games_floor"),
        "plus_metric": bool(clubs.get("plus_metric", False)),
        "no_cross_family_total": bool(decisions.get("no_cross_family_total", True)),
    })
    orgs: list[str] = []
    for g in games.values():
        for side in ("away", "home"):
            if g[side] not in orgs:
                orgs.append(g[side])
    out["clubs"] = {
        org: _club_entry(org, season, club_row(board, org, season), codes=codes,
                         league_hook_median=league_hook_median)
        for org in orgs}
    bad = forbidden_keys(out)
    if bad:                                    # the fence, applied to our own output
        return _dark(season, games,
                     "betting_dugout refused its own block: forbidden key " + ", ".join(bad))
    return out

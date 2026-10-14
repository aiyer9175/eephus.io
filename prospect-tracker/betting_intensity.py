# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Game intensity for /betting/ and the DFS slate: a descriptive chip rendered BESIDE
a price and read into none of it (owner ask 8 of 2026-09-30; plan Part 8, P8.9, item
IX-S1; the betting section "Game intensity: stakes, matchup quality and the
postseason", which says the chip on a game not yet started is not a relation).

THE FLAG. `SHOW_INTENSITY_CHIP` is False. While it is False betting_export and
dfs_export add no key and call nothing here, so every served file is byte-identical to
a build without this module. It flips in its own commit, after the fWAR label epoch's
step Z, with the glossary entries "Game intensity" and "Stakes multiple" and the
registry row `betting_intensity_index` (descriptive: provisional, measurement only,
no eval artifact).

THE WALL (the betting_dugout idiom). `build_block` reads a handful of keys off each
slate game (game_pk, game_type, status, start, the two clubs and their listed
probables), copies nothing else, mutates nothing, and returns a block that carries no
probability, edge, expected value, Kelly figure, slot, badge or record field. Every
sentence in it is a constant below or one of them filled with a club, a date or a
count. betting_export reads this module through one seam and passes the result to
nothing; test_betting_intensity_fence.py pins that, and that no pricer module imports
this module or names its payload key.

WHAT IT COMPUTES. Construction `ix_v1` through intensity_core and nothing else: the
stakes multiple (each club's World Series swing between a win and a loss, as a multiple
of an average Opening Day game), matchup quality Q, starters A, the division flag D,
the index and its band. The literals live in intensity_core; this module imports no
served constant into the construction. Labels (season phase, clinched, eliminated,
elimination game, the playoff odds swing) carry weight 0. Rivalry is a label only
(owner answer INT-A4) and no rivalry table is frozen, so no game carries one yet.

WHAT IT READS, through `load_inputs` only: this season's regular-season finals dated
strictly before the slate date (.cache/betting/completed_games.json, the results
cache), the remaining regular-season schedule (proj_current.remaining_pairs, the
Futures board's own read), the StatsAPI standings cache (clinched and eliminated
labels, postseason seeds), the postseason bracket (postseason.load) and the starter
board's SEM+ for qualified starters (data/starter_leaderboards.json).

Games not yet started only: a game whose status is not a pregame status, or whose
first pitch is at or before the build clock, is left out of `games` and listed in
`excluded`. The page applies the same rule on the reader's clock.

This module has NO write target and NO module-level Path that resolves onto a served
artifact: file names are string constants and the directories are parameters.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import intensity_core as ic

ROOT = Path(__file__).parent

#: Class 2 (plan Part 8): a new served block, off until its own flip commit.
SHOW_INTENSITY_CHIP = False

PAYLOAD_KEY = "intensity"
SURFACES = ("betting", "dfs")

FINALS_NAME = "completed_games.json"                 # under .cache/betting/, a name
STANDINGS_TEMPLATE = "statsapi_standings_{season}.json"   # under .cache/, a name
STARTER_BOARD_NAME = "starter_leaderboards.json"      # under data/, a name

#: StatsAPI detailed states before first pitch. Anything else has started, ended, or
#: was postponed, and gets no chip.
PREGAME_STATUSES = ("Preview", "Scheduled", "Pre-Game")
POSTSEASON_TYPES = ("F", "D", "L", "W")
STATSAPI_LEAGUE = {103: "AL", 104: "NL"}

# ---------------------------------------------------------------------------
# Copy. The lane's section 4.1 draft (Part 8 bundle, intensity_index.md), verbatim
# where it drafted a string; the rest is glue that names a club, a date or a count.
# ---------------------------------------------------------------------------
CHIP_TEMPLATE = "Intensity {ii} · {band}"
CHIP_NO_INDEX_TEMPLATE = "Stakes x{mult} · {why}"
SUMMARY = "Game intensity, not priced"
DFS_SUMMARY = "Game intensity"
BODY = ("How much rides on this game: the change in each club's World Series odds "
        "between a win and a loss, as a multiple of an average Opening Day game, plus "
        "how strong both clubs and both listed starters are and whether it is a "
        "division game. It describes the game.")
NOT_PRICED_SENTENCE = ("No probability, edge, expected value, Kelly figure, slot, "
                       "badge or record row on this page reads it.")
DFS_BODY = ("How much rides on this game for both clubs, how strong they are, and both "
            "listed starters. A club that has clinched or been eliminated is labelled; "
            "check posted lineups before lock.")
STAKES_LINE_TEMPLATE = "Stakes x{mult} (an average Opening Day game is x1)"
TALENT_NOTE_TEMPLATE = ("Club strength is a literature Elo walked over this season's "
                        "finals through {through}, not the Futures board's talent prior.")
TALENT_NOTE_NO_FINALS = ("Club strength is a literature Elo, and no final of this "
                         "season was read, so every club starts level.")

LABEL_DIVISION = "division"
LABEL_ELIMINATION = "elimination game"
LABEL_ACES = "both starters in the top fifth"
LABEL_CLINCHED = "clinched: {club}"
LABEL_ELIMINATED = "eliminated: {club}"
LABEL_SWING = "playoff odds swing {pts} pts ({club})"
LABEL_SWING_ONE = "playoff odds swing 1 pt ({club})"
PHASE_OPENING = "Opening week"
PHASE_SUMMER = "Summer"
PHASE_SEPTEMBER = "September"
PHASE_FINAL_WEEK = "Final week"
PHASE_ROUND = {"F": "Wild Card", "D": "Division Series",
               "L": "League Championship Series", "W": "World Series"}

WHY_UNANNOUNCED = "probables not posted"
WHY_OFF_BOARD = "starter not on the board"
NO_SCHEDULE = "the remaining schedule could not be read"
NOT_ON_SCHEDULE = "this game is not on the remaining schedule"
NO_FIELD = "the thirty-club field could not be built"
NO_BRACKET = "the postseason bracket could not be read"
NO_SEEDS = "the postseason seeds could not be read from the standings"
NOT_IN_BRACKET = "this game does not fit the recorded bracket"

#: The thresholds behind the labels. Policy, weight 0, never fitted.
ACES_PERCENTILE = 0.80          # "the top fifth"
FINAL_WEEK_GAMES = 7            # either club with 7 or fewer games left
OPENING_WEEK_DAYS = 7
SWING_MIN_PTS = 1

#: The wall, applied to our own output: no key at any depth carries one of these.
FORBIDDEN_KEY_SUBSTRINGS = ("prob", "edge", "kelly", "slot", "badge", "record",
                            "odds", "price", "ev_per", "stake_units")
#: The one key that names pricing in order to deny it (the dugout block's key name).
ALLOWED_KEYS = ("not_priced_sentence",)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _read_json(p: Path):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _aware(ts) -> datetime | None:
    if not ts:
        return None
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def mult_text(L: float) -> str:
    """The stakes multiple as printed: nearest whole number from 10 up (the lane's
    "x11" for 10.9), one decimal below 10 with a trailing .0 dropped."""
    if L >= 10:
        return str(int(math.floor(L + 0.5)))
    s = f"{math.floor(L * 10 + 0.5) / 10:.1f}"
    return s[:-2] if s.endswith(".0") else s


def forbidden_keys(obj, path: str = "") -> list[str]:
    """Every key at any depth that carries a FORBIDDEN_KEY_SUBSTRINGS entry. Values
    are not scanned (the copy names World Series odds in words)."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            ks = str(k)
            here = f"{path}.{ks}" if path else ks
            if ks not in ALLOWED_KEYS and any(s in ks.lower()
                                              for s in FORBIDDEN_KEY_SUBSTRINGS):
                hits.append(here)
            hits.extend(forbidden_keys(v, here))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(forbidden_keys(v, f"{path}[{i}]"))
    return hits


# ---------------------------------------------------------------------------
# The slate: the keys we read off each game, and nothing else
# ---------------------------------------------------------------------------
def _probable_id(side) -> int | None:
    if not isinstance(side, dict):
        return None
    pp = side.get("probable")
    return _int(pp.get("mlbam")) if isinstance(pp, dict) else None


def slate_games(games: list, now: datetime | None = None) -> tuple[list, dict]:
    """([game], {game_pk: why excluded}). A game: game_pk, date, start, game_type,
    home, away, home_sp, away_sp. Never touches a priced key; never mutates a game."""
    clock = now if now is not None else datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    out, excluded = [], {}
    for g in games or []:
        if not isinstance(g, dict):
            continue
        pk = g.get("game_pk")
        home = (g.get("home") or {}).get("org") if isinstance(g.get("home"), dict) else None
        away = (g.get("away") or {}).get("org") if isinstance(g.get("away"), dict) else None
        if pk is None or not home or not away:
            continue
        status = g.get("status")
        start = g.get("start") or g.get("datetime")
        t = None if g.get("start_time_tbd") else _aware(start)
        if status is not None and status not in PREGAME_STATUSES:
            excluded[str(pk)] = f"status {status}"
            continue
        if t is not None and t <= clock:
            excluded[str(pk)] = "first pitch at or before the build"
            continue
        out.append({"game_pk": pk, "date": g.get("date"), "start": start,
                    "game_type": g.get("game_type") or "R",
                    "home": str(home), "away": str(away),
                    "home_sp": _probable_id(g.get("home")),
                    "away_sp": _probable_id(g.get("away"))})
    out.sort(key=lambda r: (str(r["start"] or ""), str(r["game_pk"])))
    return out, excluded


# ---------------------------------------------------------------------------
# The one read
# ---------------------------------------------------------------------------
def load_inputs(slate_date: str, *, data_dir: Path | None = None,
                cache_dir: Path | None = None) -> dict:
    """Everything the block reads, in one place. Opens the results cache, the
    standings cache, the starter board, the postseason bracket and the remaining
    schedule, and nothing else."""
    season = int(str(slate_date)[:4])
    data = Path(data_dir) if data_dir is not None else ROOT / "data"
    cache = Path(cache_dir) if cache_dir is not None else ROOT / ".cache"
    import proj_current as pc
    divisions = {o: (dv.split("_")[0], dv) for dv, members in pc._DIVISIONS.items()
                 for o in members}
    finals = _read_json(cache / "betting" / FINALS_NAME)
    rows = [r for r in (finals or []) if isinstance(r, dict)
            and str(r.get("season") or str(r.get("date") or "")[:4]) == str(season)
            and str(r.get("date") or "") < str(slate_date)]
    standings = _read_json(cache / STANDINGS_TEMPLATE.format(season=season)) or {}
    board_doc = _read_json(data / STARTER_BOARD_NAME) or {}
    board = {}
    for s in board_doc.get("starters") or []:
        pid = _int(s.get("mlbam"))
        if pid is not None and s.get("qualified") and s.get("sem_plus") is not None:
            board[pid] = float(s["sem_plus"])
    try:
        pairs = pc.remaining_pairs(season, today=date.fromisoformat(str(slate_date)[:10]))
    except Exception:                                          # noqa: BLE001
        pairs = []
    post = None
    try:
        import postseason
        post = postseason.load(season)
    except Exception:                                          # noqa: BLE001
        post = None
    return {"season": season, "slate_date": str(slate_date)[:10], "finals": rows,
            "remaining_pairs": [tuple(p) for p in pairs or []],
            "standings": standings.get("records") or [],
            "starter_board": board, "starter_board_as_of": board_doc.get("as_of"),
            "postseason": ({"series": post.get("series") or []} if isinstance(post, dict)
                           else None),
            "divisions": divisions}


# ---------------------------------------------------------------------------
# The block
# ---------------------------------------------------------------------------
def _base(surface: str, slate_date, season) -> dict:
    dfs = surface == "dfs"
    return {
        "status": "unavailable",
        "blocker": None,
        "construction": ic.CONSTRUCTION,
        "surface": surface,
        "season": season,
        "slate_date": slate_date,
        "through": None,
        "sims": ic.SIMS,
        "seed": ic.SEED,
        "g_ref": ic.G_REF,
        "summary": DFS_SUMMARY if dfs else SUMMARY,
        "body": DFS_BODY if dfs else BODY,
        "not_priced_sentence": None if dfs else NOT_PRICED_SENTENCE,
        "talent_note": None,
        "games": {},
        "missing_games": {},
        "excluded": {},
    }


def build_block(games: list, slate_date: str, *, surface: str = "betting",
                inputs: dict | None = None, now: datetime | None = None,
                n_sims: int = ic.SIMS, seed: int = ic.SEED) -> dict:
    """The `intensity` block for one slate. Never raises into the exporter: an input
    that cannot be read returns a block whose status and blocker say so."""
    if surface not in SURFACES:
        raise ValueError(f"unknown surface {surface!r}")
    season = _int(str(slate_date)[:4])
    try:
        listed, excluded = slate_games(games, now)
        if inputs is None:
            inputs = load_inputs(slate_date)
        out = _build(listed, str(slate_date)[:10], season, surface, inputs,
                     n_sims=int(n_sims), seed=int(seed))
        out["excluded"] = excluded
    except Exception as exc:                                   # noqa: BLE001
        out = _base(surface, slate_date, season)
        out["blocker"] = (f"betting_intensity could not build the block "
                          f"({type(exc).__name__}: {exc})")
        return out
    bad = forbidden_keys(out)
    if bad:                                    # the wall, applied to our own output
        dark = _base(surface, slate_date, season)
        dark["blocker"] = "betting_intensity refused its own block: key " + ", ".join(bad)
        return dark
    return out


def _standings_flags(records: list) -> dict:
    """{org: {'clinched', 'eliminated', 'division_rank', 'league_rank',
    'wild_card_rank', 'league'}} from the StatsAPI standings records."""
    from trades import canonical_org_from_id
    out = {}
    for rec in records or []:
        lg = STATSAPI_LEAGUE.get(_int(((rec.get("league") or {}).get("id"))))
        for tr in rec.get("teamRecords") or []:
            team = tr.get("team") or {}
            org = canonical_org_from_id(team.get("id"), team.get("name"))
            if not org:
                continue
            out[org] = {
                "clinched": tr.get("clinched") is True,
                "eliminated": (str(tr.get("eliminationNumber")) == "E"
                               and str(tr.get("wildCardEliminationNumber")) == "E"),
                "division_rank": _int(tr.get("divisionRank")),
                "league_rank": _int(tr.get("leagueRank")),
                "wild_card_rank": _int(tr.get("wildCardRank")),
                "league": lg,
            }
    return out


def _seeds(flags: dict, divisions: dict, bracket_clubs: set) -> dict | None:
    """{league: (seed 1, ..., seed 6)}: the division winners in the bracket by league
    rank, then the wild cards by wild-card rank. None unless every league reads 3 + 3."""
    out = {}
    for lg in ("AL", "NL"):
        clubs = [o for o in bracket_clubs if divisions.get(o, (None,))[0] == lg]
        champs = [o for o in clubs if (flags.get(o) or {}).get("division_rank") == 1]
        wcs = [o for o in clubs if o not in champs]
        if len(champs) != 3 or len(wcs) != 3:
            return None

        def rank(o, key):
            v = (flags.get(o) or {}).get(key)
            return 99 if v is None else v
        champs.sort(key=lambda o: (rank(o, "league_rank"), o))
        wcs.sort(key=lambda o: (rank(o, "wild_card_rank"), rank(o, "league_rank"), o))
        out[lg] = tuple(champs + wcs)
    return out


def _phase(g: dict, D: str, season_start: str | None, left: dict) -> str:
    gt = g["game_type"]
    if gt in PHASE_ROUND:
        return PHASE_ROUND[gt]
    if min(left.get(g["home"], 99), left.get(g["away"], 99)) <= FINAL_WEEK_GAMES:
        return PHASE_FINAL_WEEK
    start = season_start or D
    if date.fromisoformat(D) < date.fromisoformat(start) + timedelta(days=OPENING_WEEK_DAYS):
        return PHASE_OPENING
    if int(D[5:7]) >= 9:
        return PHASE_SEPTEMBER
    return PHASE_SUMMER


def _build(listed: list, D: str, season, surface: str, inputs: dict, *,
           n_sims: int, seed: int) -> dict:
    out = _base(surface, D, season)
    divisions = inputs.get("divisions") or {}
    orgs = sorted(divisions)
    finals = [r for r in inputs.get("finals") or []
              if r.get("home_org") in divisions and r.get("away_org") in divisions
              and r.get("home_runs") is not None and r.get("away_runs") is not None
              and str(r.get("date") or "") < D]
    through = max((str(r["date"])[:10] for r in finals), default=None)
    season_start = min((str(r["date"])[:10] for r in finals), default=None)
    wins = {o: 0 for o in orgs}
    for r in finals:
        wins[r["home_org"] if int(r["home_runs"]) > int(r["away_runs"]) else r["away_org"]] += 1
    talent = ic.talent_from_ratings(ic.elo_ratings_before(finals, D), orgs)
    flags = _standings_flags(inputs.get("standings") or [])
    board = inputs.get("starter_board") or {}
    out.update({
        "status": "built",
        "through": through,
        "talent_note": (TALENT_NOTE_TEMPLATE.format(through=through) if through
                        else TALENT_NOTE_NO_FINALS),
        "basis": {"finals_read": len(finals),
                  "remaining_games": len(inputs.get("remaining_pairs") or []),
                  "starters_on_board": len(board),
                  "starter_board_as_of": inputs.get("starter_board_as_of"),
                  "postseason_format": ic.format_for_season(season) if season else None},
    })
    if len(orgs) != 30:
        out["missing_games"] = {str(g["game_pk"]): NO_FIELD for g in listed}
        return out

    rows = {}
    reg = [g for g in listed if g["game_type"] not in POSTSEASON_TYPES]
    post = [g for g in listed if g["game_type"] in POSTSEASON_TYPES]

    # Regular season: one conditioning pass for every listed game.
    if reg:
        pairs = [tuple(p) for p in inputs.get("remaining_pairs") or []
                 if p[0] in divisions and p[1] in divisions]
        used, index = set(), {}
        for g in reg:
            for k, (h, a) in enumerate(pairs):
                if k not in used and (h, a) == (g["home"], g["away"]):
                    used.add(k)
                    index[str(g["game_pk"])] = k
                    break
        for g in reg:
            if not pairs:
                out["missing_games"][str(g["game_pk"])] = NO_SCHEDULE
            elif str(g["game_pk"]) not in index:
                out["missing_games"][str(g["game_pk"])] = NOT_ON_SCHEDULE
        found = [g for g in reg if str(g["game_pk"]) in index]
        if found:
            teams = {o: {"wins": wins[o], "p": talent[o], "league": divisions[o][0],
                         "div": divisions[o][1]} for o in orgs}
            res = ic.regular_season_stakes(
                teams, pairs, [index[str(g["game_pk"])] for g in found],
                fmt=ic.format_for_season(season), n_sims=n_sims, seed=seed)
            left = {o: 0 for o in orgs}
            for h, a in pairs:
                left[h] += 1
                left[a] += 1
            for g, st in zip(found, res["games"]):
                Q = ic.matchup_quality(res["proj_wins"], g["home"], g["away"])
                labels = []
                for club in (g["away"], g["home"]):
                    f = flags.get(club) or {}
                    if f.get("clinched"):
                        labels.append(LABEL_CLINCHED.format(club=club))
                    elif f.get("eliminated"):
                        labels.append(LABEL_ELIMINATED.format(club=club))
                big_h = abs(st["dpo_h"]) >= abs(st["dpo_a"])
                sw_club = g["home"] if big_h else g["away"]
                sw = abs(st["dpo_h"] if big_h else st["dpo_a"])
                pts = int(math.floor(100.0 * sw + 0.5))
                swing = {"pts": pts, "club": sw_club}
                if pts >= SWING_MIN_PTS:
                    labels.append(LABEL_SWING_ONE.format(club=sw_club) if pts == 1
                                  else LABEL_SWING.format(pts=pts, club=sw_club))
                rows[str(g["game_pk"])] = _row(g, st["G"], Q, board, labels,
                                               _phase(g, D, season_start, left), swing,
                                               divisions)

    # Postseason: the exact series recursion times the bracket.
    if post:
        series = (inputs.get("postseason") or {}).get("series")
        if series is None:
            for g in post:
                out["missing_games"][str(g["game_pk"])] = NO_BRACKET
        else:
            state, clubs = {}, set()
            for r in series:
                a, b = r[3], r[4]
                for c in (a, b):
                    if c:
                        clubs.add(c)
                if a and b:
                    state[frozenset((a, b))] = {a: int(r[5]), b: int(r[6])}
            seeds = _seeds(flags, divisions, clubs)
            q = ic.percentile_ranks({o: wins[o] for o in orgs})
            for g in post:
                pk = str(g["game_pk"])
                if seeds is None:
                    out["missing_games"][pk] = NO_SEEDS
                    continue
                try:
                    st = ic.postseason_stakes(seeds, wins, talent, g["home"], g["away"],
                                              fmt=ic.format_for_season(season),
                                              series_state=state)
                except (ValueError, KeyError):
                    out["missing_games"][pk] = NOT_IN_BRACKET
                    continue
                need = st["best_of"] // 2 + 1
                labels = []
                if any(w == need - 1 for w in st["state"].values()):
                    labels.append(LABEL_ELIMINATION)
                Q = min(q[g["home"]], q[g["away"]])
                rows[pk] = _row(g, st["G"], Q, board, labels,
                                _phase(g, D, season_start, {}), None, divisions)

    out["games"] = {pk: rows[pk] for pk in (str(g["game_pk"]) for g in listed) if pk in rows}
    return out


def _row(g: dict, G: float, Q: float, board: dict, labels: list, phase: str,
         swing: dict | None, divisions: dict) -> dict:
    """One game's entry: the components, the index and the strings the page prints."""
    S = ic.stakes_score(G)
    L = ic.stakes_multiple(G)
    A = ic.starters_score(g["home_sp"], g["away_sp"], board)
    D = ic.division_flag((divisions.get(g["home"]) or (None, None))[1],
                         (divisions.get(g["away"]) or (None, None))[1])
    ii = ic.index_value(S, Q, A, D)
    band = ic.band_of(ii)
    missing = []
    if A is None:
        missing.append(WHY_UNANNOUNCED if (g["home_sp"] is None or g["away_sp"] is None)
                       else WHY_OFF_BOARD)
    lab = ([LABEL_DIVISION] if D else []) + list(labels)
    if A is not None and A >= ACES_PERCENTILE:
        lab.append(LABEL_ACES)
    lab.append(phase)
    m = mult_text(L)
    chip = (CHIP_TEMPLATE.format(ii=ii, band=band) if ii is not None
            else CHIP_NO_INDEX_TEMPLATE.format(mult=m, why=missing[0]))
    return {
        "game_pk": g["game_pk"],
        "game_type": g["game_type"],
        "away": g["away"],
        "home": g["home"],
        "ii": ii,
        "band": band,
        "chip": chip,
        "stakes_multiple": round(L, 1),
        "stakes_line": STAKES_LINE_TEMPLATE.format(mult=m),
        "S": round(S, 3),
        "Q": round(Q, 3),
        "A": None if A is None else round(A, 3),
        "D": D,
        "labels": lab,
        "playoff_swing": swing,
        "missing": missing,
    }

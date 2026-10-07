# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Awards race strip's data, mode wpa_order (AWARDS_5_RACE; AWARDS_PLAN 4.6 'The race
(data/_labs/awards/race_<S>.json, copied into awards.json)', 5.4 'The race strip', 6 row I5;
LANE_DATA 6 'The race strip's data').

WHAT IT WRITES. One tracked, unpublished file per season, data/_labs/awards/race_<S>.json,
for 2018, 2019 and 2021 to 2026 (data/_labs/ ships in neither deploy consumer). The file
holds one block per award and league, keyed "MVP_AL" ... "MOY_NL", in the shape
awards_export._race copies into the payload's race block:

  {"mode": "wpa_order", "metric_label", "producer", "registry", "weeks", "record_starts",
   "missing", "finalists", "places": {<id>: [...]}, "values": {<id>: [...]}}

THE THREE. Each block's three rows are the season's final Top 3 by the rule: awards_core's
ballot on that season's inputs, through awards_export's own context and ballot call (the
display WAR provider passed explicitly, the stint frames read once per side), so the 2026
rows are the exporter's rows. Ids are the exporter's row keys as strings: the MLBAM id for
a player, "c" plus the club code in lower case for a club.

THE ORDER. Per ISO week that holds a game day, the week's point is its last game day, and
each row's value is the cumulative realized win probability added through that day, from
the play corpus .cache/pbp_corpus/plays/<S>/plays-<S>.parquet: batter WPA is sign(half) x
wpa_home / 100 (plus in the bottom half, minus in the top), pitcher WPA its negative. MVP
and Rookie sum both sides; Cy Young reads the pitching side. The places are the order
among the three on those values (ties go to the better final rule place), so every week
is a permutation of 1 to 3. Manager orders the three clubs by games over .500 through the
week, from each game's final score (the corpus's last play). The values ride beside the
places for the page's numbers twin. The WPA sums are taken in integer tenths of a win
percentage point (wpa_home carries one decimal), so they are exact.

THE DATES. A game's day is its officialDate in .cache/game_feeds/<gamePk>.json where that
feed is on disk (2026); for a season without feeds it is .cache/mgmt_game_dates.json, the
date of the game's first play in New York time (mgmt_decisions.game_dates). The two agree
on every 2026 corpus game (measured 2026-10-07: 2,429 of 2,429). A doubleheader day is
one day holding two games; each game is counted once. Club identity per game comes from
the feed's teams where the feed exists, else from mgmt_teams.build_map (the batters' modal
club per half inning).

RECONCILIATION (I5). The last point equals the boards' season wpa: the leverage board's
batters[] (exact) and starters[] (exact, start games: the pitcher's first play of the game
in the 1st inning, mlb_leverage's rule) and the bullpen board's relievers[] (to 0.01, the
board prints two decimals), on data/leverage_leaderboards.json and
data/bullpen_leaderboards.json for the board season and data/leverage_history.json and
data/bullpen_history.json for 2021 to 2025. 2018 and 2019 have no board, so they are not
reconciled. A Manager block reconciles each club's final wins and losses with the StatsAPI
standings cache. The counts are written into the file's reconciliation block and printed.

WRITE-ONCE. A closed season's file is written once and never rewritten: the tool skips a
season whose file exists when the season is closed (before the board season, or the board
season once the regular season is complete). The deploy box has no play corpus, so this
runs on the dev box only and the nightly only reads the files.

FROM 2027 (mode rule_place). For a season from awards_export.RULE_PLACE_FIRST on, the
nightly exporter keeps one vintage a date and builds the race block itself; once the
season closes this tool writes the tracked race_<S>.json once from those vintages
(awards_export.rule_place_race), on the dev box that holds them.

THE ONE NETWORK READ is awards_export's: war_source.stint_frame for each side, once per
process. Everything else is read from disk.

CLI:
  python tools/awards_race.py                 every season not yet on file
  python tools/awards_race.py --season 2026   one season
  python tools/awards_race.py --dry-run       build and print, write nothing
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import awards_core as A  # noqa: E402
import awards_export as E  # noqa: E402

CORPUS = ROOT / ".cache" / "pbp_corpus" / "plays"
FEEDS = ROOT / ".cache" / "game_feeds"
DATES_FALLBACK = ROOT / ".cache" / "mgmt_game_dates.json"
LABS = E.LABS

SEASONS = (2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)
#: Seasons whose boards carry a season wpa to reconcile against (the history boards
#: start in 2021; the board season reads the current boards).
BOARD_FIRST = 2021

MODE = "wpa_order"
SCHEMA = 1
PRODUCED_BY = "tools/awards_race.py"
METRIC_LABEL = "Order among the three on win probability added, week by week. Not the selection metric."
METRIC_LABEL_CLUB = "Order among the three clubs on games over .500, week by week. Not the selection metric."
REGISTRY = "leverage_board"
#: The bullpen board prints two decimals, so a reliever's part reconciles to 0.01.
RELIEVER_TOL = 0.01
PLAY_COLS = ("game_pk", "half", "inning", "at_bat_index", "batter_id", "pitcher_id",
             "wpa_home", "home_score", "away_score")
#: wpa_home carries one decimal of a percentage point; the sums run in these units.
UNITS_PER_WIN = 1000


# --- inputs -------------------------------------------------------------------------------

def load_plays(season: int, corpus_dir: Path | None = None):
    """The season's plays (PLAY_COLS) from the play corpus."""
    import pandas as pd
    p = Path(corpus_dir or CORPUS) / str(int(season)) / f"plays-{int(season)}.parquet"
    if not p.exists():
        raise FileNotFoundError(f"{p} is not on disk; the race is built on the dev box only")
    return pd.read_parquet(p, columns=list(PLAY_COLS))


def plays_from_columns(cols: dict):
    """The test seam: a DataFrame from a columnar dict (PLAY_COLS keys)."""
    import pandas as pd
    return pd.DataFrame({k: cols[k] for k in PLAY_COLS if k in cols})


def _feed_meta(path: Path, abbrev: dict) -> dict | None:
    try:
        doc = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError):
        return None
    gd = doc.get("gameData") or {}
    teams = gd.get("teams") or {}
    ls = ((doc.get("liveData") or {}).get("linescore") or {}).get("teams") or {}

    def club(side):
        tid = (teams.get(side) or {}).get("id")
        raw = abbrev.get(int(tid)) if tid is not None else None
        return E._club(raw) if raw else None

    return {"date": (gd.get("datetime") or {}).get("officialDate"),
            "type": (gd.get("game") or {}).get("type"),
            "home": club("home"), "away": club("away"),
            "home_runs": (ls.get("home") or {}).get("runs"),
            "away_runs": (ls.get("away") or {}).get("runs"),
            "source": "feed"}


def game_meta(pks, *, feeds_dir: Path | None = None, dates_path: Path | None = None,
              abbrev: dict | None = None, team_map: dict | None = None) -> dict:
    """{game_pk: {"date", "type", "home", "away", "home_runs", "away_runs", "source"}}.
    The feed where it is on disk; else the first-play date from dates_path and the clubs
    from team_map ({pk: {"home", "away"}}, mgmt_teams.build_map's shape)."""
    feeds = Path(feeds_dir or FEEDS)
    abbrev = abbrev or {}
    fallback = None
    out = {}
    for pk in pks:
        pk = int(pk)
        m = _feed_meta(feeds / f"{pk}.json", abbrev) if (feeds / f"{pk}.json").exists() else None
        if m is None or not m.get("date"):
            if fallback is None:
                p = Path(dates_path or DATES_FALLBACK)
                fallback = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
            tm = (team_map or {}).get(pk) or {}
            m = {"date": fallback.get(str(pk)), "type": None,
                 "home": E._club(tm.get("home")) if tm.get("home") else None,
                 "away": E._club(tm.get("away")) if tm.get("away") else None,
                 "home_runs": None, "away_runs": None, "source": "first_play_date"}
        out[pk] = m
    return out


# --- the fold -----------------------------------------------------------------------------

def fold(plays) -> dict:
    """Per player and game, the WPA parts in integer units (UNITS_PER_WIN to a win):
    {"bat": {mlbam: {pk: u}}, "start": {mlbam: {pk: u}}, "relief": {mlbam: {pk: u}},
     "final": {pk: (home_score, away_score)}}. A pitcher's game is a start when his first
    play of the game (at_bat_index order) is in the 1st inning, mlb_leverage's rule."""
    import numpy as np
    df = plays.sort_values(["game_pk", "at_bat_index"], kind="mergesort").reset_index(drop=True)
    u = np.rint(df["wpa_home"].fillna(0.0).to_numpy() * 10.0).astype("int64")
    bottom = (df["half"].to_numpy() == "bottom")
    bu = np.where(bottom, u, -u)
    df = df.assign(bu=bu, pu=-bu)
    out = {"bat": {}, "start": {}, "relief": {}, "final": {}}
    bat = df[df["batter_id"] > 0].groupby(["batter_id", "game_pk"], sort=False)["bu"].sum()
    for (mid, pk), v in bat.items():
        out["bat"].setdefault(int(mid), {})[int(pk)] = int(v)
    pit_rows = df[df["pitcher_id"] > 0]
    g = pit_rows.groupby(["pitcher_id", "game_pk"], sort=False)
    pit = g["pu"].sum()
    first_inning = g["inning"].first()
    for (mid, pk), v in pit.items():
        part = "start" if int(first_inning[(mid, pk)]) == 1 else "relief"
        out[part].setdefault(int(mid), {})[int(pk)] = int(v)
    last = df.groupby("game_pk", sort=False).tail(1)
    for pk, hs, as_ in zip(last["game_pk"], last["home_score"], last["away_score"]):
        out["final"][int(pk)] = (int(hs), int(as_))
    return out


def week_ends(dates) -> list:
    """The last game day of every ISO week that holds one, in order."""
    by_week = {}
    for d in dates:
        if not d:
            continue
        k = _dt.date.fromisoformat(d).isocalendar()[:2]
        if k not in by_week or d > by_week[k]:
            by_week[k] = d
    return sorted(by_week.values())


def _week_index(weeks: list, d: str) -> int:
    for i, w in enumerate(weeks):
        if d <= w:
            return i
    return len(weeks) - 1


def cumulative(per_game: dict, meta: dict, weeks: list) -> list:
    """Cumulative units through each week end from {pk: units}; each game counted once."""
    per_week = [0] * len(weeks)
    for pk, v in per_game.items():
        d = (meta.get(int(pk)) or {}).get("date")
        if not d or d > weeks[-1]:
            continue
        per_week[_week_index(weeks, d)] += int(v)
    out, run = [], 0
    for v in per_week:
        run += v
        out.append(run)
    return out


def club_cumulative(club: str, fold_final: dict, meta: dict, weeks: list) -> tuple:
    """(games over .500 through each week, wins, losses) for one club."""
    per_week = [0] * len(weeks)
    w = l = 0
    for pk, (hs, as_) in fold_final.items():
        m = meta.get(int(pk)) or {}
        if club not in (m.get("home"), m.get("away")) or not m.get("date") or m["date"] > weeks[-1]:
            continue
        home = m.get("home") == club
        won = (hs > as_) if home else (as_ > hs)
        per_week[_week_index(weeks, m["date"])] += 1 if won else -1
        w += 1 if won else 0
        l += 0 if won else 1
    out, run = [], 0
    for v in per_week:
        run += v
        out.append(run)
    return out, w, l


def places_of(order: list, series: dict) -> dict:
    """{id: [place per week]}: the order among the ids by value, highest first, ties to the
    earlier id in `order` (the final rule place)."""
    n = len(next(iter(series.values()))) if series else 0
    places = {i: [] for i in order}
    for k in range(n):
        ranked = sorted(order, key=lambda i: (-series[i][k], order.index(i)))
        for p, i in enumerate(ranked, start=1):
            places[i].append(p)
    return places


def player_series(award: str, mlbam: int, folded: dict) -> dict:
    """{pk: units} for one candidate: MVP and Rookie both sides, Cy Young pitching."""
    out: dict = {}
    parts = ("start", "relief") if award == "CY" else ("bat", "start", "relief")
    for part in parts:
        for pk, v in (folded[part].get(int(mlbam)) or {}).items():
            out[pk] = out.get(pk, 0) + v
    return out


def _producer(season: int, meta_sources: dict, club: bool) -> str:
    corpus = f".cache/pbp_corpus/plays/{season}/plays-{season}.parquet"
    if meta_sources.get("feed") and not meta_sources.get("first_play_date"):
        dates = ".cache/game_feeds/<gamePk>.json officialDate"
    elif meta_sources.get("first_play_date") and not meta_sources.get("feed"):
        dates = ".cache/mgmt_game_dates.json first-play date (New York)"
    else:
        dates = (".cache/game_feeds/<gamePk>.json officialDate, else "
                 ".cache/mgmt_game_dates.json first-play date (New York)")
    if club:
        return f"{corpus} final score of each game (last play) x {dates}; games over .500"
    return f"{corpus} wpa_home, batter sign(half) and pitcher the negative, x {dates}"


def build_block(award: str, finalists: list, folded: dict, meta: dict, weeks: list,
                season: int, meta_sources: dict) -> dict:
    """One race block. finalists: [{"id", "name", "rule_place"}] in final rule order."""
    order = [f["id"] for f in finalists]
    club = award == "MOY"
    series, values = {}, {}
    for f in finalists:
        if club:
            s, _w, _l = club_cumulative(f["club"], folded["final"], meta, weeks)
            series[f["id"]] = s
            values[f["id"]] = list(s)
        else:
            s = cumulative(player_series(award, int(f["id"]), folded), meta, weeks)
            series[f["id"]] = s
            values[f["id"]] = [x / UNITS_PER_WIN for x in s]
    return {
        "mode": MODE,
        "metric_label": METRIC_LABEL_CLUB if club else METRIC_LABEL,
        "producer": _producer(season, meta_sources, club),
        "registry": None if club else REGISTRY,
        "weeks": list(weeks),
        "record_starts": min(m["date"] for m in meta.values() if m.get("date")),
        "missing": [],
        "finalists": [{k: f[k] for k in ("id", "name", "rule_place")} for f in finalists],
        "places": places_of(order, series),
        "values": values,
    }


# --- the three ------------------------------------------------------------------------------

def finalists_for(ctx, season: int) -> dict:
    """{"MVP_AL": [{"id", "name", "rule_place", "club"?}] x 3, ...}: the exporter's ballot
    call, top three rows (awards_export._card reads the same call)."""
    w = ctx.world(season)
    out = {}
    for award in A.AWARDS:
        for lg in A.LEAGUES:
            b = E._ballots(ctx, w, award, lg)
            if b is None:
                continue
            rows = []
            for r in (b.get("top") or [])[:3]:
                k = E._row_key(r)
                f = {"id": str(k), "name": r.get("name") or r.get("club"), "rule_place": int(r["rank"])}
                if award == "MOY":
                    f["club"] = r.get("club")
                rows.append(f)
            if len(rows) == 3:
                out[f"{award}_{lg}"] = rows
    return out


# --- reconciliation (I5) --------------------------------------------------------------------

def board_wpa(inp, season: int, board_season: int) -> dict | None:
    """{"bat": {mlbam: wpa}, "start": {...}, "relief": {...}} from the boards, or None for a
    season with no board."""
    if season == board_season:
        lev = inp.data_json("leverage_leaderboards.json", required=False) or {}
        pen = inp.data_json("bullpen_leaderboards.json", required=False) or {}
        bat, sp, rp = lev.get("batters"), lev.get("starters"), pen.get("relievers")
    elif season >= BOARD_FIRST:
        key = str(season)
        lev = ((inp.data_json("leverage_history.json", required=False) or {}).get("history") or {}).get(key) or {}
        pen = ((inp.data_json("bullpen_history.json", required=False) or {}).get("history") or {}).get(key) or {}
        bat, sp, rp = lev.get("batters"), lev.get("starters"), pen.get("relievers")
    else:
        return None
    if not bat and not sp and not rp:
        return None

    def idx(rows):
        return {int(r["mlbam"]): float(r["wpa"]) for r in rows or []
                if r.get("mlbam") is not None and r.get("wpa") is not None}

    return {"bat": idx(bat), "start": idx(sp), "relief": idx(rp)}


def reconcile_player(award: str, mlbam: int, folded: dict, board: dict) -> dict:
    """The I5 check for one candidate: every part of his last point against its board
    row. status "exact" (every part on a board, all equal), "within_0.01" (a reliever part
    inside the bullpen board's two decimals), "miss", or "part_off_board" (every part with
    a board row agrees, and one part has no board row: a pitcher's batting before the
    universal DH, a two-way player's pitching, a starter's few relief games)."""
    parts = ("start", "relief") if award == "CY" else ("bat", "start", "relief")
    status = "exact"
    detail = {}
    for part in parts:
        u = sum((folded[part].get(int(mlbam)) or {}).values())
        have = (folded[part].get(int(mlbam)) or {})
        b = board[part].get(int(mlbam))
        if not have and b is None:
            continue
        mine = u / UNITS_PER_WIN
        detail[part] = {"race": mine, "board": b}
        if b is None:
            status = "part_off_board" if status != "miss" else status
            continue
        diff = abs(mine - b)
        if part == "relief":
            if diff > RELIEVER_TOL + 1e-9:
                status = "miss"
            elif diff > 1e-9 and status == "exact":
                status = "within_0.01"
        elif diff > 1e-9:
            status = "miss"
    return {"status": status, "parts": detail}


def reconcile_boards(folded: dict, board: dict) -> dict:
    """The whole-board check: every board row against the fold (batters and starters exact,
    relievers to 0.01). Counts only."""
    out = {}
    for part in ("bat", "start", "relief"):
        n = ok = 0
        for mid, b in board[part].items():
            n += 1
            mine = sum((folded[part].get(mid) or {}).values()) / UNITS_PER_WIN
            tol = RELIEVER_TOL + 1e-9 if part == "relief" else 1e-9
            ok += 1 if abs(mine - b) <= tol else 0
        out[part] = {"rows": n, "agree": ok}
    return out


def standings_wl(ctx, season: int) -> dict:
    st = E._standings(ctx, season)
    return {E._club(c["club"]): (c.get("w"), c.get("l")) for c in st["clubs"] if c.get("club")}


# --- the season -----------------------------------------------------------------------------

def build_season(ctx, season: int, *, plays=None, corpus_dir=None, feeds_dir=None,
                 dates_path=None, team_map=None, log=print) -> dict:
    """The race_<S>.json document for one season."""
    S = int(season)
    plays = load_plays(S, corpus_dir) if plays is None else plays
    folded = fold(plays)
    pks = sorted(folded["final"])
    if team_map is None and not all((Path(feeds_dir or FEEDS) / f"{pk}.json").exists() for pk in pks):
        import mgmt_teams
        team_map = mgmt_teams.build_map()
    meta = game_meta(pks, feeds_dir=feeds_dir, dates_path=dates_path, abbrev=ctx.abbrev,
                     team_map=team_map)
    dropped = [pk for pk, m in meta.items() if m.get("type") not in (None, "R")]
    for pk in dropped:
        meta.pop(pk)
        folded["final"].pop(pk, None)
        for part in ("bat", "start", "relief"):
            for games in folded[part].values():
                games.pop(pk, None)
    sources = {}
    for m in meta.values():
        sources[m["source"]] = sources.get(m["source"], 0) + 1
    undated = sorted(pk for pk, m in meta.items() if not m.get("date"))
    weeks = week_ends(m.get("date") for m in meta.values())
    fin = finalists_for(ctx, S)
    doc = {"schema": SCHEMA, "produced_by": PRODUCED_BY,
           "generated_at": E._now_iso(), "season": S, "mode": MODE,
           "war_provider": ctx.provider,
           "games": {"corpus": len(meta), "dropped_not_regular_season": len(dropped),
                     "undated": len(undated), "date_sources": dict(sorted(sources.items()))}}
    for key, rows in fin.items():
        doc[key] = build_block(key.split("_")[0], rows, folded, meta, weeks, S, sources)
    doc["reconciliation"] = _reconciliation(ctx, S, fin, folded, meta, weeks)
    return doc


def _reconciliation(ctx, S: int, fin: dict, folded: dict, meta: dict, weeks: list) -> dict:
    board = board_wpa(ctx.inp, S, ctx.board_season)
    rec = {"board": None, "finalists": None, "boards": None, "clubs": None, "finals": None}
    if board is not None:
        rec["board"] = ("leverage_leaderboards.json and bullpen_leaderboards.json" if S == ctx.board_season
                        else f"leverage_history.json and bullpen_history.json history[{S}]")
        counts = {"exact": 0, "within_0.01": 0, "miss": 0, "part_off_board": 0}
        rows = []
        for key, fl in fin.items():
            award = key.split("_")[0]
            if award == "MOY":
                continue
            for f in fl:
                r = reconcile_player(award, int(f["id"]), folded, board)
                counts[r["status"]] += 1
                if r["status"] in ("miss", "part_off_board"):
                    rows.append({"block": key, "id": f["id"], "name": f["name"], **r})
        rec["finalists"] = {"counts": counts, "not_exact": rows}
        rec["boards"] = reconcile_boards(folded, board)
    wl = standings_wl(ctx, S)
    if wl:
        n = ok = 0
        miss = []
        for key, fl in fin.items():
            if not key.startswith("MOY_"):
                continue
            for f in fl:
                n += 1
                _s, w, l = club_cumulative(f["club"], folded["final"], meta, weeks)
                want = wl.get(f["club"])
                if want is not None and (w, l) == (want[0], want[1]):
                    ok += 1
                else:
                    miss.append({"club": f["club"], "race": [w, l], "standings": list(want or [])})
        rec["clubs"] = {"checked": n, "agree": ok, "misses": miss}
    with_runs = [(pk, m) for pk, m in meta.items() if m.get("home_runs") is not None]
    if with_runs:
        agree = sum(1 for pk, m in with_runs
                    if folded["final"].get(pk) == (int(m["home_runs"]), int(m["away_runs"])))
        rec["finals"] = {"checked": len(with_runs), "agree": agree,
                         "against": ".cache/game_feeds/<gamePk>.json liveData.linescore runs"}
    return rec


def is_closed(ctx, season: int) -> bool:
    return int(season) < ctx.board_season or not E._in_season(ctx)


def dumps(doc: dict) -> bytes:
    return (json.dumps(doc, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def rule_place_season(S: int, vdir: Path | None = None) -> dict:
    """The tracked race_<S>.json for a season from E.RULE_PLACE_FIRST on: the rule_place
    blocks built from the season's nightly vintages (awards_export.rule_place_race)."""
    vdir = Path(vdir) if vdir is not None else E.vintage_dir()
    vints = E.load_vintages(vdir, S)
    doc = {"schema": SCHEMA, "produced_by": PRODUCED_BY, "generated_at": E._now_iso(),
           "season": int(S), "mode": "rule_place", "vintages": len(vints)}
    doc.update(E.rule_place_race(vints))
    doc["reconciliation"] = None
    return doc


def run(seasons, *, dry_run=False, labs_dir=None, log=print) -> dict:
    labs = Path(labs_dir or LABS)
    ctx, _labs = E._context()
    out = {}
    for S in seasons:
        path = labs / f"race_{S}.json"
        closed = is_closed(ctx, S)
        if path.exists() and closed:
            log(f"race_{S}.json exists and {S} is closed; the file is write-once, skipped")
            out[S] = {"written": False, "reason": "write-once"}
            continue
        if S >= E.RULE_PLACE_FIRST:
            if not closed:
                log(f"{S} is in progress: the nightly builds its rule_place block from the "
                    f"vintages; the tracked file is written once after the season closes")
                out[S] = {"written": False, "reason": "season in progress"}
                continue
            doc = rule_place_season(S)
            raw = dumps(doc)
            log(f"{S}: rule_place from {doc['vintages']} vintages")
            if not dry_run:
                E._write_bytes(path, raw)
                log(f"wrote {path} ({len(raw):,} bytes)")
            out[S] = {"written": not dry_run, "bytes": len(raw), "reconciliation": None}
            continue
        doc = build_season(ctx, S, log=log)
        raw = dumps(doc)
        _summary(doc, log)
        if not dry_run:
            E._write_bytes(path, raw)
            log(f"wrote {path} ({len(raw):,} bytes)")
        out[S] = {"written": not dry_run, "bytes": len(raw), "reconciliation": doc["reconciliation"]}
    return out


def _summary(doc: dict, log) -> None:
    S = doc["season"]
    rec = doc["reconciliation"]
    keys = [f"{a}_{lg}" for a in A.AWARDS for lg in A.LEAGUES if f"{a}_{lg}" in doc]
    first = doc[keys[0]] if keys else {}
    log(f"{S}: {doc['games']['corpus']} games, {len(first.get('weeks') or [])} weeks, "
        f"{len(keys)} blocks, dates {doc['games']['date_sources']}")
    if rec["finalists"]:
        log(f"  I5 finalists {rec['finalists']['counts']}; boards {rec['boards']}")
    if rec["clubs"]:
        log(f"  clubs W-L against standings {rec['clubs']['agree']} of {rec['clubs']['checked']}")
    if rec["finals"]:
        log(f"  final scores against the feeds {rec['finals']['agree']} of {rec['finals']['checked']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build data/_labs/awards/race_<S>.json (wpa_order).")
    ap.add_argument("--season", type=int, action="append", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    seasons = a.season or list(SEASONS)
    run(seasons, dry_run=a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())

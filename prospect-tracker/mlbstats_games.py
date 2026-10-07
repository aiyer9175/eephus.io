# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""mlbstats_games - the per-game player frame (PUBLIC; plan Part 8 8.E).

THE PUBLIC FUNCTION. ``player_game_frame(season)`` returns one season's game
lines, one row per (game, player), for hitters and pitchers, in game order. It
is the one frame the rolling-window exporter (mlbstats_rolling_export.py)
reads and the one the League Trends plan imports (trend_frames.py); League
Trends never edits this module (its ruling R6). The signature, the column
names and the game order are the contract:

    frame = player_game_frame(2026)
    frame.hit    pandas DataFrame, HIT_KEYS + HIT_COLS
    frame.pit    pandas DataFrame, PIT_KEYS + PIT_COLS
    frame.meta   dict: season, source ("corpus" or "payload"), games,
                 games_without_payload, first_game, covers_through,
                 corpus_built_at

THE GAME ORDER. Games are ordered by the first play's ``about.startTime`` in
``.cache/win_prob/<pk>.json`` (then by game_pk), and ``game_seq`` numbers them
0, 1, 2 ... within the season. ``date`` is that start time on the US Eastern
calendar, so a 10 pm Pacific start keeps its own date instead of the UTC one.
``covers_through`` is the latest ``date`` in the frame.

TWO PATHS, ONE RESULT.
  corpus   when ``.cache/pbp_corpus/plays/<season>/`` holds the season's table:
           the plays table (event type, outs, Leverage Index, half) and the
           pitches table (pitches per play).
  payload  when the corpus holds no table for the season (the deploy box
           carries .cache/win_prob but no corpus): the same play rows are
           rebuilt from the payloads by tools/build_pbp_corpus's own pure row
           builders (reconstruct_plays, pitch_rows), so the two paths share
           every column and the aggregation below.
Both paths then read one SCORING LAYER per game from the payload (memoised
under .cache/mlbstats_games/), because three things the official line needs
are not in the corpus:
  1. WHO IS CHARGED WITH THE PLATE APPEARANCE. The play's ``credits`` (b_pa,
     p_pa) name the batter and pitcher the official scorer charged, which
     differs from ``matchup`` when a pinch hitter enters with two strikes and
     the strikeout is charged to the first batter (rule 9.15), or a reliever
     enters on a ball-heavy count and the walk is charged to the first pitcher
     (rule 9.16). Measured on 2026: matchup attribution missed the StatsAPI
     plate appearances of 8 of 662 hitters and the batters faced of 19 of 868
     pitchers by one; the credits miss none.
  2. WHO THREW AND SAW EACH PITCH. Each pitch event names its pitcher and
     batter, so a mid-plate-appearance change splits the pitch count the way
     the official line does (matchup attribution missed 85 pitchers' counts).
  3. EARNED AND TOTAL RUNS, by each scoring runner's responsible pitcher.
Outs, the start (the first pitcher of each half's first play) and the entry
Leverage Index (mlb_leverage._game_pitcher_dict's rule: the first non-missing
leverageIndex of the pitcher's plays) follow the pitcher on the mound.

WHAT IS NOT RECONCILED. A payload is cached once, the night of the game, so an
official scoring change made after that (a hit changed to an error and back,
the earned runs that follow it) is not in the frame. On 2026 that is the hit
count of 51 of 662 hitters and the earned runs of 35 of 868 pitchers, each by
one or two; plate appearances, at bats, home runs, strikeouts, batters faced,
starts, outs and runs agree with the season lines exactly.

Nothing here is a model, a rate or a forecast: every column is a count.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, NamedTuple, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache"
CORPUS_DIR = CACHE_DIR / "pbp_corpus"
WIN_PROB_DIR = CACHE_DIR / "win_prob"
MEMO_DIR = CACHE_DIR / "mlbstats_games"

#: Bumped whenever the scoring layer or the memoised play rows change shape,
#: which discards every memoised game instead of mixing two rules.
MEMO_VERSION = 1

HIT_KEYS = ["season", "game_pk", "game_seq", "start_time", "date", "mlbam", "home"]
HIT_COLS = ["pa", "ab", "h", "d", "t", "hr", "bb", "ibb", "hbp", "sf", "sh", "so", "pit"]
PIT_KEYS = list(HIT_KEYS)
PIT_COLS = ["gs", "bf", "outs", "h", "hr", "bb", "ibb", "hbp", "so", "r", "er", "pit", "li"]

#: Terminal events that end a play without a plate appearance, by eventType
#: prefix, plus the exact type "error" (betting_usage.NON_PA_PREFIX, the list
#: the corpus measurement behind diamond-betting 5f used).
NON_PA_PREFIX = ("caught_stealing", "pickoff", "stolen_base", "wild_pitch",
                 "passed_ball", "balk", "other_advance", "game_advisory",
                 "runner_double_play", "other_out", "defensive_indiff",
                 "forced_balk")
HITS = ("single", "double", "triple", "home_run")
STRIKEOUTS = ("strikeout", "strikeout_double_play", "strikeout_triple_play")
WALKS = ("walk", "intent_walk")
SAC_FLIES = ("sac_fly", "sac_fly_double_play")
SAC_BUNTS = ("sac_bunt", "sac_bunt_double_play")

_START_RE = re.compile(rb'"startTime"\s*:\s*"((\d{4})-[^"]*)"')
_SNIFF_BYTES = 4096

try:                                        # the box and this tree both carry tzdata
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:                           # noqa: BLE001 - fixed offset fallback
    _ET = None


class GameFrame(NamedTuple):
    """The frame player_game_frame returns (see the module docstring)."""
    hit: pd.DataFrame
    pit: pd.DataFrame
    meta: dict


def _nolog(*_a, **_k):
    return None


def game_date(start_time: Optional[str]) -> Optional[str]:
    """The US Eastern calendar date of an ISO UTC start time, or None."""
    if not start_time:
        return None
    try:
        dt = datetime.fromisoformat(str(start_time).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if _ET is not None:
        return dt.astimezone(_ET).date().isoformat()
    return (dt.astimezone(timezone.utc) - timedelta(hours=4)).date().isoformat()


def is_pa_event(event_type) -> bool:
    """True when a play's eventType closes a plate appearance."""
    et = str(event_type or "")
    if not et or et == "error":
        return False
    return not et.startswith(NON_PA_PREFIX)


# --------------------------------------------------------------------------- #
# the scoring layer, one game at a time (pure)
# --------------------------------------------------------------------------- #
def _pid(block) -> Optional[int]:
    v = (block or {}).get("id") if isinstance(block, dict) else None
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def game_layer(plays: list) -> dict:
    """What the official line needs and the corpus does not carry, for one game.

    {"start": first play's startTime, "bat": {abi: batter} and "pit": {abi:
    pitcher} where the credits charge someone other than matchup, "pitches":
    {abi: [[pitcher, batter, n], ...]} where a pitch was thrown or seen by
    someone other than matchup, "er" / "r": {pitcher: n}, "n_pitches": total}.
    Keys are strings so the memo round-trips through JSON unchanged."""
    out = {"start": None, "bat": {}, "pit": {}, "pitches": {}, "er": {}, "r": {},
           "n_pitches": 0}
    er: dict = {}
    runs: dict = {}
    for play in plays or ():
        about = play.get("about") or {}
        if out["start"] is None and about.get("startTime"):
            out["start"] = about.get("startTime")
        abi = play.get("atBatIndex", about.get("atBatIndex"))
        m = play.get("matchup") or {}
        mb, mp = _pid(m.get("batter")), _pid(m.get("pitcher"))
        cb = cp = None
        for c in play.get("credits") or ():
            if c.get("credit") == "b_pa":
                cb = _pid(c.get("player"))
            elif c.get("credit") == "p_pa":
                cp = _pid(c.get("player"))
        if abi is not None:
            if cb is not None and cb != mb:
                out["bat"][str(abi)] = cb
            if cp is not None and cp != mp:
                out["pit"][str(abi)] = cp
        split: dict = {}
        moved = False
        for ev in play.get("playEvents") or ():
            if not ev.get("isPitch"):
                continue
            out["n_pitches"] += 1
            dp = _pid((ev.get("defense") or {}).get("pitcher")) or mp
            ob = _pid((ev.get("offense") or {}).get("batter")) or mb
            if dp != mp or ob != mb:
                moved = True
            split[(dp, ob)] = split.get((dp, ob), 0) + 1
        if moved and abi is not None:
            out["pitches"][str(abi)] = [[p, b, n] for (p, b), n in split.items()]
        for r in play.get("runners") or ():
            d = r.get("details") or {}
            if not d.get("isScoringEvent"):
                continue
            rp = _pid(d.get("responsiblePitcher")) or mp
            if rp is None:
                continue
            runs[rp] = runs.get(rp, 0) + 1
            if d.get("earned"):
                er[rp] = er.get(rp, 0) + 1
    out["er"] = {str(k): v for k, v in er.items()}
    out["r"] = {str(k): v for k, v in runs.items()}
    return out


#: The play columns the aggregation reads, in the memo's positional order.
ROW_COLS = ["half", "at_bat_index", "batter_id", "pitcher_id", "event_type",
            "outs_before", "outs_after", "leverage_index", "np"]


def payload_rows(plays: list, game_pk: int, season: int) -> list:
    """Corpus-shaped play rows for one game, built by tools/build_pbp_corpus's
    own pure row builders so the payload path and the corpus path share every
    column. Positional, in ROW_COLS order."""
    from tools import build_pbp_corpus as bpc
    rows = bpc.reconstruct_plays(plays, game_pk, season)
    npc: dict = {}
    for p in bpc.pitch_rows(plays, game_pk, season):
        npc[p["at_bat_index"]] = npc.get(p["at_bat_index"], 0) + 1
    out = []
    for r in rows:
        li = r.get("leverage_index")
        out.append([r.get("half"), r.get("at_bat_index"), r.get("batter_id"),
                    r.get("pitcher_id"), r.get("event_type"), r.get("outs_before"),
                    r.get("outs_after"), li, npc.get(r.get("at_bat_index"), 0)])
    return out


# --------------------------------------------------------------------------- #
# the memo (.cache/mlbstats_games/)
# --------------------------------------------------------------------------- #
def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def _sig(path: Path) -> Optional[list]:
    try:
        st = path.stat()
    except OSError:
        return None
    return [st.st_size, st.st_mtime_ns]


def sniff_start(path: Path) -> tuple[Optional[int], Optional[str]]:
    """(season, first startTime) off the first 4 KB of a payload: the first
    startTime in the file is the first play's ``about.startTime``. Falls back to
    a full parse when the head does not carry one."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(_SNIFF_BYTES)
    except OSError:
        return None, None
    m = _START_RE.search(head)
    if m:
        return int(m.group(2)), m.group(1).decode("ascii", "replace")
    try:
        plays = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    for p in plays if isinstance(plays, list) else ():
        st = (p.get("about") or {}).get("startTime")
        if st:
            return int(st[:4]), st
    return None, None


def season_index(win_prob_dir: Optional[Path] = None, memo_dir: Optional[Path] = None,
                 log: Callable = _nolog) -> dict:
    """{game_pk: (season, startTime)} for every cached payload, memoised by
    (size, mtime) so a night re-sniffs only the files that moved (the first
    build reads 4 KB of each file, about 85 s over 19,000 files)."""
    wp = Path(win_prob_dir or WIN_PROB_DIR)
    md = Path(memo_dir or MEMO_DIR)
    path = md / "win_prob_index.json"
    memo = _read_json(path) or {}
    known = memo.get("files") if memo.get("version") == MEMO_VERSION else None
    known = known or {}
    files: dict = {}
    moved = 0
    if wp.is_dir():
        for p in wp.glob("*.json"):
            try:
                int(p.stem)
            except ValueError:
                continue
            sig = _sig(p)
            if sig is None:
                continue
            prev = known.get(p.name)
            if prev and prev[0] == sig[0] and prev[1] == sig[1]:
                files[p.name] = prev
                continue
            s, st = sniff_start(p)
            files[p.name] = [sig[0], sig[1], s, st]
            moved += 1
    if moved or set(files) != set(known):
        _write_json(path, {"version": MEMO_VERSION, "files": files})
        log(f"  games: payload index {len(files):,} files ({moved:,} sniffed)")
    return {int(Path(n).stem): (v[2], v[3]) for n, v in files.items()
            if v[2] is not None}


def season_game_dates(season: int, win_prob_dir: Optional[Path] = None,
                      memo_dir: Optional[Path] = None) -> list:
    """Every cached payload date of one season (US Eastern), sorted."""
    idx = season_index(win_prob_dir, memo_dir)
    return sorted({game_date(st) for s, st in idx.values()
                   if s == int(season) and game_date(st)})


def _layers(season: int, pks, *, win_prob_dir: Path, memo_dir: Path,
            with_rows: bool, log: Callable) -> dict:
    """{pk: layer} for the requested games, from the memo when a payload's
    (size, mtime) still matches and by parsing it otherwise. A game whose
    payload is gone keeps its memoised layer (the disk preflight prunes the
    cache); a game with neither is left out and counted by the caller."""
    path = memo_dir / f"layers_{int(season)}.json"
    memo = _read_json(path) or {}
    games = memo.get("games") if (memo.get("version") == MEMO_VERSION
                                  and memo.get("season") == int(season)) else None
    games = games or {}
    out: dict = {}
    parsed = 0
    t0 = time.time()
    for pk in pks:
        key = str(int(pk))
        f = win_prob_dir / f"{int(pk)}.json"
        sig = _sig(f)
        hit = games.get(key)
        if hit is not None and (sig is None or hit.get("sig") == sig) \
                and (not with_rows or "rows" in hit):
            out[int(pk)] = hit
            continue
        if sig is None:
            continue
        try:
            plays = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(plays, dict):
            plays = plays.get("winProbability") or []
        lay = game_layer(plays)
        lay["sig"] = sig
        if with_rows:
            lay["rows"] = payload_rows(plays, int(pk), int(season))
        elif hit is not None and "rows" in hit and hit.get("sig") == sig:
            lay["rows"] = hit["rows"]
        games[key] = lay
        out[int(pk)] = lay
        parsed += 1
    if parsed:
        _write_json(path, {"version": MEMO_VERSION, "season": int(season), "games": games})
        log(f"  games: {season} scoring layer, {parsed:,} payloads parsed in "
            f"{round(time.time() - t0, 1)}s ({len(out):,} games)")
    return out


# --------------------------------------------------------------------------- #
# the aggregation (shared by both paths)
# --------------------------------------------------------------------------- #
def _corpus_table(corpus_dir: Path, table: str, season: int) -> Path:
    return corpus_dir / table / str(int(season)) / f"{table}-{int(season)}.parquet"


def has_corpus(season: int, corpus_dir: Optional[Path] = None) -> bool:
    """True when the corpus holds the season's plays and pitches tables."""
    cd = Path(corpus_dir or CORPUS_DIR)
    return (_corpus_table(cd, "plays", season).exists()
            and _corpus_table(cd, "pitches", season).exists())


def corpus_built_at(corpus_dir: Optional[Path] = None) -> Optional[str]:
    man = _read_json(Path(corpus_dir or CORPUS_DIR) / "manifest.json") or {}
    return man.get("built_at")


def _corpus_plays(season: int, corpus_dir: Path) -> pd.DataFrame:
    cols = ["game_pk", "half", "at_bat_index", "batter_id", "pitcher_id",
            "event_type", "outs_before", "outs_after", "leverage_index"]
    plays = pd.read_parquet(_corpus_table(corpus_dir, "plays", season), columns=cols)
    pitches = pd.read_parquet(_corpus_table(corpus_dir, "pitches", season),
                              columns=["game_pk", "at_bat_index", "is_pitch"])
    pitches = pitches[pitches["is_pitch"].astype(bool)]
    npc = pitches.groupby(["game_pk", "at_bat_index"]).size().rename("np")
    plays = plays.join(npc, on=["game_pk", "at_bat_index"])
    plays["np"] = plays["np"].fillna(0).astype("int64")
    return plays


def _empty(keys: list, cols: list) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="float64" if c == "li" else "int64")
                         for c in keys + cols})


def aggregate(plays: pd.DataFrame, layers: dict, season: int) -> tuple:
    """(hit, pit) game lines from corpus-shaped play rows and the per-game
    scoring layers. Pure; both paths call it."""
    P = plays[plays["game_pk"].isin(list(layers))].copy()
    if P.empty:
        return _empty(HIT_KEYS, HIT_COLS), _empty(PIT_KEYS, PIT_COLS)
    P = P.sort_values(["game_pk", "at_bat_index"], kind="mergesort").reset_index(drop=True)
    P["game_pk"] = P["game_pk"].astype("int64")
    P["at_bat_index"] = P["at_bat_index"].astype("int64")
    P["home_bat"] = (P["half"] == "bottom")
    key = list(zip(P["game_pk"].tolist(), P["at_bat_index"].tolist()))

    bat_over, pit_over, pitch_over = {}, {}, {}
    for pk, lay in layers.items():
        for abi, b in (lay.get("bat") or {}).items():
            bat_over[(int(pk), int(abi))] = int(b)
        for abi, p in (lay.get("pit") or {}).items():
            pit_over[(int(pk), int(abi))] = int(p)
        for abi, rows in (lay.get("pitches") or {}).items():
            pitch_over[(int(pk), int(abi))] = rows
    P["cb"] = [bat_over.get(k, b) for k, b in zip(key, P["batter_id"].tolist())]
    P["cp"] = [pit_over.get(k, p) for k, p in zip(key, P["pitcher_id"].tolist())]

    et = P["event_type"].fillna("").astype(str)
    P["pa"] = [int(is_pa_event(e)) for e in et]
    P["h"] = et.isin(HITS).astype(int)
    P["d"] = (et == "double").astype(int)
    P["t"] = (et == "triple").astype(int)
    P["hr"] = (et == "home_run").astype(int)
    P["bb"] = et.isin(WALKS).astype(int)
    P["ibb"] = (et == "intent_walk").astype(int)
    P["hbp"] = (et == "hit_by_pitch").astype(int)
    P["sf"] = et.isin(SAC_FLIES).astype(int)
    P["sh"] = et.isin(SAC_BUNTS).astype(int)
    P["so"] = et.isin(STRIKEOUTS).astype(int)
    P["ci"] = (et == "catcher_interf").astype(int)
    P["ab"] = (P["pa"] - P["bb"] - P["hbp"] - P["sf"] - P["sh"] - P["ci"]).clip(lower=0)
    ob = pd.to_numeric(P["outs_before"], errors="coerce").fillna(0)
    oa = pd.to_numeric(P["outs_after"], errors="coerce").fillna(0)
    P["outs"] = (oa - ob).clip(lower=0).astype(int)

    # hitters: plate-appearance events by the charged batter
    hev = ["pa", "ab", "h", "d", "t", "hr", "bb", "ibb", "hbp", "sf", "sh", "so"]
    hb = P[P["cb"].notna()]
    hit = hb.groupby(["game_pk", "cb"])[hev].sum()
    hit.index.names = ["game_pk", "mlbam"]
    # pitchers: plate-appearance events by the charged pitcher, outs and the
    # entry Leverage Index by the pitcher on the mound
    pev = ["pa", "h", "hr", "bb", "ibb", "hbp", "so"]
    pb = P[P["cp"].notna()]
    pit = pb.groupby(["game_pk", "cp"])[pev].sum().rename(columns={"pa": "bf"})
    pit.index.names = ["game_pk", "mlbam"]
    pm = P[P["pitcher_id"].notna()]
    outs = pm.groupby(["game_pk", "pitcher_id"])["outs"].sum()
    outs.index.names = ["game_pk", "mlbam"]
    li = pd.to_numeric(pm["leverage_index"], errors="coerce").groupby(
        [pm["game_pk"], pm["pitcher_id"]]).first()
    li.index.names = ["game_pk", "mlbam"]
    first = pm.groupby(["game_pk", "half"], sort=False).head(1)
    gs = first.groupby(["game_pk", "pitcher_id"]).size()
    gs.index.names = ["game_pk", "mlbam"]

    # pitches: by the pitch's own pitcher and batter where the layer says so
    plain = [k not in pitch_over for k in key]
    pr = P.loc[plain, ["game_pk", "batter_id", "pitcher_id", "np", "half"]].rename(
        columns={"batter_id": "b", "pitcher_id": "p", "np": "n"})
    half_of = dict(zip(key, P["half"].tolist()))
    extra = [(pk, int(b) if b is not None else None, int(p) if p is not None else None,
              int(n), half_of.get((pk, abi)))
             for (pk, abi), rows in pitch_over.items() if (pk, abi) in half_of
             for p, b, n in rows]
    if extra:
        pr = pd.concat([pr, pd.DataFrame(extra, columns=["game_pk", "b", "p", "n", "half"])],
                       ignore_index=True)
    hpit = pr[pr["b"].notna()].groupby(["game_pk", "b"])["n"].sum()
    hpit.index = hpit.index.set_names(["game_pk", "mlbam"])
    ppit = pr[pr["p"].notna()].groupby(["game_pk", "p"])["n"].sum()
    ppit.index = ppit.index.set_names(["game_pk", "mlbam"])

    # which side each player was on (the half he batted or pitched in)
    hside = pd.concat([
        pd.DataFrame({"game_pk": P["game_pk"], "mlbam": P["cb"], "home": P["half"] == "bottom"}),
        pd.DataFrame({"game_pk": P["game_pk"], "mlbam": P["batter_id"], "home": P["half"] == "bottom"}),
        pd.DataFrame({"game_pk": pr["game_pk"], "mlbam": pr["b"], "home": pr["half"] == "bottom"}),
    ]).dropna().drop_duplicates(["game_pk", "mlbam"]).set_index(["game_pk", "mlbam"])["home"]
    pside = pd.concat([
        pd.DataFrame({"game_pk": P["game_pk"], "mlbam": P["pitcher_id"], "home": P["half"] == "top"}),
        pd.DataFrame({"game_pk": P["game_pk"], "mlbam": P["cp"], "home": P["half"] == "top"}),
        pd.DataFrame({"game_pk": pr["game_pk"], "mlbam": pr["p"], "home": pr["half"] == "top"}),
    ]).dropna().drop_duplicates(["game_pk", "mlbam"]).set_index(["game_pk", "mlbam"])["home"]

    runs_rows = []
    for pk, lay in layers.items():
        rr, ee = lay.get("r") or {}, lay.get("er") or {}
        for pid in set(rr) | set(ee):
            runs_rows.append((int(pk), int(pid), int(rr.get(pid, 0)), int(ee.get(pid, 0))))
    runs = (pd.DataFrame(runs_rows, columns=["game_pk", "mlbam", "r", "er"])
            .set_index(["game_pk", "mlbam"]))

    hit = hit.join(hpit.rename("pit"), how="outer")
    pit = (pit.join(outs.rename("outs"), how="outer")
           .join(gs.rename("gs"), how="outer")
           .join(ppit.rename("pit"), how="outer")
           .join(runs, how="outer"))
    pit = pit.join(li.rename("li"), how="left")

    # A player named on a play who threw or saw no pitch and was charged with
    # nothing did not appear: the matchup can name a pitcher whose every pitch
    # the payload gives to someone else (one 2026 reliever, one phantom game).
    hit = hit[(hit[["pa", "pit"]].fillna(0).sum(axis=1) > 0)]
    pit = pit[(pit[["bf", "outs", "pit", "gs", "r"]].fillna(0).sum(axis=1) > 0)]

    starts = {int(pk): lay.get("start") for pk, lay in layers.items() if lay.get("start")}
    order = sorted(starts, key=lambda pk: (starts[pk], pk))
    seq = {pk: i for i, pk in enumerate(order)}

    def finish(df: pd.DataFrame, side: pd.Series, cols: list) -> pd.DataFrame:
        df = df.reset_index()
        df["game_pk"] = df["game_pk"].astype("int64")
        df["mlbam"] = df["mlbam"].astype("int64")
        df = df[df["game_pk"].isin(seq)].copy()
        for c in cols:
            if c not in df.columns:
                df[c] = 0
            if c != "li":
                df[c] = df[c].fillna(0).astype("int64")
        if "li" in cols:
            df["li"] = pd.to_numeric(df["li"], errors="coerce").round(2)
        hm = side.reindex(pd.MultiIndex.from_arrays([df["game_pk"], df["mlbam"]]))
        df["home"] = hm.fillna(False).astype(bool).to_numpy()
        df["season"] = int(season)
        df["game_seq"] = df["game_pk"].map(seq).astype("int64")
        df["start_time"] = df["game_pk"].map(starts)
        df["date"] = df["start_time"].map(game_date)
        df = df.sort_values(["game_seq", "mlbam"], kind="mergesort").reset_index(drop=True)
        return df[HIT_KEYS + cols]

    return finish(hit, hside, HIT_COLS), finish(pit, pside, PIT_COLS)


# --------------------------------------------------------------------------- #
# the public frame
# --------------------------------------------------------------------------- #
def player_game_frame(season: int, *, corpus_dir: Optional[Path] = None,
                      win_prob_dir: Optional[Path] = None,
                      memo_dir: Optional[Path] = None,
                      log: Callable = _nolog) -> GameFrame:
    """One season's hitter and pitcher game lines in game order (PUBLIC; the
    module docstring is the contract). The corpus path runs when the corpus
    holds the season's tables, the payload path otherwise; both return the
    same columns, the same order and the same counts."""
    season = int(season)
    cd = Path(corpus_dir or CORPUS_DIR)
    wp = Path(win_prob_dir or WIN_PROB_DIR)
    md = Path(memo_dir or MEMO_DIR)
    t0 = time.time()
    if has_corpus(season, cd):
        source = "corpus"
        plays = _corpus_plays(season, cd)
        pks = sorted(int(v) for v in plays["game_pk"].unique())
        layers = _layers(season, pks, win_prob_dir=wp, memo_dir=md, with_rows=False, log=log)
        built_at = corpus_built_at(cd)
    else:
        source = "payload"
        idx = season_index(wp, md, log=log)
        pks = sorted(pk for pk, (s, _st) in idx.items() if s == season)
        layers = _layers(season, pks, win_prob_dir=wp, memo_dir=md, with_rows=True, log=log)
        rows = [[pk] + r for pk, lay in layers.items() for r in (lay.get("rows") or [])]
        plays = pd.DataFrame(rows, columns=["game_pk"] + ROW_COLS)
        built_at = None
    layers = {pk: lay for pk, lay in layers.items() if lay.get("start")}
    hit, pit = aggregate(plays, layers, season)
    dates = sorted(set(hit["date"].dropna()) | set(pit["date"].dropna()))
    meta = {
        "season": season, "source": source, "games": len(layers),
        "games_without_payload": len(pks) - len(layers),
        "first_game": dates[0] if dates else None,
        "covers_through": dates[-1] if dates else None,
        "corpus_built_at": built_at,
        "seconds": round(time.time() - t0, 1),
    }
    log(f"  games: {season} frame from the {source}, {meta['games']:,} games through "
        f"{meta['covers_through']}, {len(hit):,} hitter and {len(pit):,} pitcher lines "
        f"in {meta['seconds']}s")
    return GameFrame(hit, pit, meta)


def main(argv=None) -> int:                 # pragma: no cover - a quick look
    import argparse
    ap = argparse.ArgumentParser(description="Build one season's per-game player frame.")
    ap.add_argument("--season", type=int, default=datetime.now().year)
    a = ap.parse_args(argv)
    f = player_game_frame(a.season, log=print)
    print(json.dumps(f.meta))
    return 0


if __name__ == "__main__":                  # pragma: no cover
    raise SystemExit(main())

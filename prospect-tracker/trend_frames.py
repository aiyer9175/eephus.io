# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""trend_frames - the frames League Trends reads (League Trends plan 5.1).

League Trends owns this module (ruling R6); it never edits P8.2's
mlbstats_games. It reads the payload-direct pitch sidecar that
tools/build_pitch_physics.py writes under ``.cache/pbp_physics/`` and the
daily WAR frame ``.cache/war_daily/bat.parquet``, so everything here builds
where the play corpus is absent (the deploy box, plan 5.5).

CLUB IDENTITY, ``club_by_game(season)`` (ruling T5). The payloads carry no
team block, so a game's clubs are recovered by a vote: every plate appearance
of a half inning votes for its batter's clubs, weighted by his share of that
season's plate appearances with each club (``mgmt_teams.player_team_weights``,
imported, never copied; a traded batter votes for both clubs and is outvoted
by his teammates). The bottom half bats at home, so the bottom half's winning
club is the home club and the top half's the away club. A game is left
unresolved when the two halves vote for one club, when a half has no
attributable batter, or when a half's top two clubs tie exactly. A season whose
resolved share of the sidecar's games falls below
``mgmt_teams.MIN_RESOLVED_SHARE`` is refused, never returned partial, because a
partial map drops games in a way correlated with roster churn.

What it never does: call mgmt_teams' corpus map builder (it reads the corpus
and, validated, the betting results cache), open any betting cache or a
lineup, vintage, odds, weather or game-feed cache, or relate a club to a game
result or a price. Club identity labels cards and Teams rows only; it enters
no bar (plan 3.5 item 6).

THE TREND FRAME, ``pitch_game_frame(season)`` (plan 5.1, ruling R6; League
Trends owns it and P8.2's module is only imported, for its game lines). One
season's per-game aggregates, every one a count, a sum or a copied value:

  games    one row per game: game_seq (start-time order), start_time, date,
           home and away club (the vote above), final score, sb, cs.
  pit      one row per pitcher-game: club, start, entry Leverage Index (li),
           bf, so, bb, hbp and outs from mlbstats_games.player_game_frame, and
           from the sidecar the pitches, swings, whiffs, out-of-zone pitches
           and chases.
  arsenal  one row per (pitcher, game, pitch type, batter side): pitches, and
           for each of start_speed, ivb, hb, spin and ext the tracked count,
           sum and sum of squares, so a game's mean and within-game variance
           of any pitch type (the primary fastball among them) follow exactly.
  bat      one row per batter-game: club, started (one of his club's first
           nine batters of the game), pa, ab, h, bb, hbp, sf and so from the
           game lines, and from the sidecar the pitches seen, swings, whiffs,
           out-of-zone pitches, chases and batted-ball launch sums.
  swings   one row per tracked swing that is not a bunt: bat speed, swing
           length and attack angle, from the swing source below.
  prior_cut  the previous season's competitive-swing cut per hitter (the 10th
           percentile of his bat speed over that whole completed season), the
           cut trend_detect uses until a hitter has 100 swings this season.

Nothing in the frame depends on an evaluation date: the competitive-swing cut
of the current season, the role, the primary fastball and every sigma are
computed as of D by trend_detect from these rows (plan 3.1).

THE SWING SOURCE (plan 3.4, ruling R1). Owner answer TR-Q3 (a), 2026-10-01:
the Savant day files under ``.cache/league_trends/savant_days/`` for every
season (``SWING_SOURCE``). The TR-Q3 (b) reader of ``.cache/swing_pitches/``
(``<batter>_<season>.csv``, written by swing_plus_ingest) is kept beside it.
Either source is opened read-only; nothing here writes it.

THE RECEIPTS CHECK. A cache can be pruned, so every read counts, per season it
needs (the season and, from 2025, the season before it), the hitters with one
or more tracked swings and the tracked swings. A season is missing when it has
no such file, or when a season with a pinned receipt counts fewer hitters or
swings than the receipt; ``SwingSeasonsMissing`` then names every missing
season and nothing is returned.

MEMO. The frame is memoised under ``.cache/league_trends/frames/<season>/``,
keyed by the size and mtime of every input file, so a night with no new game
reads parquet only.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable, Iterable, NamedTuple, Optional

import numpy as np
import pandas as pd

from mgmt_teams import MIN_RESOLVED_SHARE, WAR_BAT, player_team_weights

ROOT = Path(__file__).resolve().parent
PHYSICS_DIR = ROOT / ".cache" / "pbp_physics"
MEMO_DIR = ROOT / ".cache" / "league_trends" / "frames"
FRAME_VERSION = 1

# The swing source, owner answer TR-Q3 (a) of 2026-10-01 (DECISIONS_FOR_OWNER.md).
SWING_SOURCE = "savant_days"
SWING_DIRS = {
    "savant_days": ROOT / ".cache" / "league_trends" / "savant_days",
    "swing_pitches": ROOT / ".cache" / "swing_pitches",
}
FIRST_SWING_SEASON = 2024                  # MLB bat tracking begins
# Pinned receipts per completed season. savant_days: the one-time backfill's own
# counts (TR_1_FRAMES_DARK, 9c2ec0d0). swing_pitches: the lane's calibration
# pool (plan 3.4: at least 195 hitters in 2024 and 281 in 2025).
SWING_RECEIPTS = {
    "savant_days": {2024: {"hitters": 650, "swings": 316997},
                    2025: {"hitters": 672, "swings": 330422},
                    2026: {"hitters": 661, "swings": 331816}},
    "swing_pitches": {2024: {"hitters": 195}, 2025: {"hitters": 281}},
}

# Pitch outcome codes (MLB call codes, as the lane's probes count them).
SWING_CODES = frozenset({"S", "W", "T", "F", "L", "M", "O", "Q", "X", "D", "E"})
WHIFF_CODES = frozenset({"S", "W", "M", "Q"})
OUT_OF_ZONE = (11, 12, 13, 14)
HARD_HIT_MPH = 95.0
LINEUP_SLOTS = 9
PHYSICS = ("start_speed", "ivb", "hb", "spin", "ext")

# Competitive swings (the Savant convention the lane used, p11_hitters.py): no
# bunts, bat speed 50 mph or more, and at or above the hitter's 10th percentile
# of bat speed. trend_detect takes the cut as of D; the frame carries only the
# previous completed season's cut.
COMPETITIVE_MIN_MPH = 50.0
COMPETITIVE_QUANTILE = 0.10


class ClubMap(NamedTuple):
    """{game_pk: {"home", "away", "season"}} and the season's counts."""
    games: dict
    meta: dict


def _table(physics_dir: Path, table: str, season: int) -> Path:
    return Path(physics_dir) / str(int(season)) / f"{table}-{int(season)}.parquet"


def resolve_clubs(season: int, *, physics_dir: Optional[Path] = None,
                  war_daily: Optional[Path] = None,
                  weights: Optional[pd.DataFrame] = None) -> ClubMap:
    """The half-inning batter vote for one season, with its counts. Raises
    ValueError below the resolved-share floor and FileNotFoundError when the
    sidecar holds no table for the season."""
    season = int(season)
    pdir = Path(physics_dir or PHYSICS_DIR)
    pit_p, gam_p = _table(pdir, "pitches", season), _table(pdir, "games", season)
    if not (pit_p.exists() and gam_p.exists()):
        raise FileNotFoundError(
            f"the pitch sidecar holds no {season} table under {pdir}; run "
            "tools/build_pitch_physics.py first")
    games = pd.read_parquet(gam_p, columns=["game_pk"])
    pas = (pd.read_parquet(pit_p, columns=["game_pk", "half", "at_bat_index", "batter"])
           .dropna(subset=["batter", "half"])
           .drop_duplicates(["game_pk", "half", "at_bat_index", "batter"]))
    pas["batter"] = pas["batter"].astype("int64")
    w = weights if weights is not None else player_team_weights(war_daily)
    wy = w[w["year_ID"] == season][["mlb_ID", "team_ID", "w"]]
    j = pas.merge(wy, left_on="batter", right_on="mlb_ID", how="inner")
    votes = j.groupby(["game_pk", "half", "team_ID"], as_index=False)["w"].sum()
    votes = votes.sort_values(["game_pk", "half", "w", "team_ID"],
                              ascending=[True, True, False, True], kind="mergesort")
    votes["rank"] = votes.groupby(["game_pk", "half"]).cumcount()
    top = votes[votes["rank"] == 0].set_index(["game_pk", "half"])
    second = votes[votes["rank"] == 1].set_index(["game_pk", "half"])["w"]
    top = top.join(second.rename("w2"))
    tied = top["w2"].notna() & (top["w"] == top["w2"])
    top.loc[tied, "team_ID"] = None
    win = top["team_ID"].unstack("half")
    out: dict = {}
    same = no_half = 0
    for gp, row in win.iterrows():
        home, away = row.get("bottom"), row.get("top")
        if not (isinstance(home, str) and isinstance(away, str)):
            no_half += 1
            continue
        if home == away:
            same += 1
            continue
        out[int(gp)] = {"home": home, "away": away, "season": season}
    ties = int(tied.sum())
    n_games = int(games["game_pk"].nunique())
    share = len(out) / n_games if n_games else 0.0
    meta = {"season": season, "games": n_games, "resolved": len(out),
            "share": round(share, 6), "same_club": same,
            "missing_or_tied_half": no_half, "tied_halves": ties,
            "floor": MIN_RESOLVED_SHARE}
    if share < MIN_RESOLVED_SHARE:
        raise ValueError(
            f"club identity resolved only {len(out):,} of {n_games:,} {season} games "
            f"({share:.4f}), below the {MIN_RESOLVED_SHARE} floor "
            f"(mgmt_teams.MIN_RESOLVED_SHARE); refused rather than returned partial")
    return ClubMap(out, meta)


def club_by_game(season: int, *, physics_dir: Optional[Path] = None,
                 war_daily: Optional[Path] = None) -> dict:
    """{game_pk: {"home": club, "away": club, "season": int}} for one season
    (see the module docstring). Refuses below the resolved-share floor."""
    return resolve_clubs(season, physics_dir=physics_dir, war_daily=war_daily).games


# --------------------------------------------------------------------------- #
# the swing source and its receipts
# --------------------------------------------------------------------------- #
class SwingSeasonsMissing(RuntimeError):
    """A needed season of the swing source is absent or below its receipt."""

    def __init__(self, seasons: list, source: str, detail: dict):
        self.seasons = sorted(int(s) for s in seasons)
        self.source = source
        self.detail = detail
        names = " ".join(str(s) for s in self.seasons)
        super().__init__(
            f"{source} seasons {names} missing: " + "; ".join(
                f"{s} {detail.get(s, '')}".strip() for s in self.seasons))


_SWING_COLS = ("game_date", "game_pk", "batter", "description",
               "bat_speed", "swing_length", "attack_angle")


def swing_dir_for(source: str, swing_dir: Optional[Path] = None) -> Path:
    if source not in SWING_DIRS:
        raise ValueError(f"unknown swing source {source!r}; one of {sorted(SWING_DIRS)}")
    return Path(swing_dir or SWING_DIRS[source])


def swing_files(season: int, *, source: str = SWING_SOURCE,
                swing_dir: Optional[Path] = None) -> list:
    """The source's files for one season, sorted by name."""
    d = swing_dir_for(source, swing_dir)
    pat = f"{int(season)}-*.csv" if source == "savant_days" else f"*_{int(season)}.csv"
    return sorted(d.glob(pat)) if d.exists() else []


def read_swings(season: int, *, source: str = SWING_SOURCE,
                swing_dir: Optional[Path] = None) -> pd.DataFrame:
    """Every tracked swing (a row with a bat speed) of one season, read-only:
    game_date, game_pk, batter, bunt, bat_speed, swing_length, attack_angle."""
    season = int(season)
    parts = []
    for f in swing_files(season, source=source, swing_dir=swing_dir):
        try:
            d = pd.read_csv(f, usecols=lambda c: c in _SWING_COLS)
        except (OSError, ValueError, pd.errors.EmptyDataError):
            continue
        if d.empty or "bat_speed" not in d.columns:
            continue
        parts.append(d)
    cols = ["game_date", "game_pk", "batter", "bunt", "bat_speed", "swing_length",
            "attack_angle"]
    if not parts:
        return pd.DataFrame({c: pd.Series(dtype="float64") for c in cols})
    df = pd.concat(parts, ignore_index=True)
    for c in _SWING_COLS:
        if c not in df.columns:
            df[c] = np.nan
    df = df[pd.to_numeric(df["bat_speed"], errors="coerce").notna()].copy()
    df["game_date"] = df["game_date"].astype(str).str[:10]
    df = df[df["game_date"].str[:4] == str(season)]
    if source == "swing_pitches":
        df = df.drop_duplicates()
    df["game_pk"] = pd.to_numeric(df["game_pk"], errors="coerce").astype("Int64")
    df["batter"] = pd.to_numeric(df["batter"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["game_pk", "batter"])
    df["bunt"] = df["description"].astype(str).str.contains("bunt", case=False, na=False)
    for c in ("bat_speed", "swing_length", "attack_angle"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    df = df.sort_values(["game_date", "game_pk", "batter"], kind="mergesort")
    return df[cols].reset_index(drop=True)


def swing_counts(swings: pd.DataFrame) -> dict:
    """{hitters, swings, max_game_date}: hitters with one or more tracked swings."""
    if swings is None or swings.empty:
        return {"hitters": 0, "swings": 0, "max_game_date": None}
    return {"hitters": int(swings["batter"].nunique()), "swings": int(len(swings)),
            "max_game_date": str(swings["game_date"].max())}


def missing_swing_seasons(counts: dict, *, source: str = SWING_SOURCE,
                          receipts: Optional[dict] = None) -> dict:
    """{season: reason} for every season in ``counts`` that is missing: no
    tracked swing at all, or below its pinned receipt."""
    rec = SWING_RECEIPTS.get(source, {}) if receipts is None else receipts
    out: dict = {}
    for s, c in sorted(counts.items()):
        s = int(s)
        if not c.get("swings"):
            out[s] = "(no file with a tracked swing)"
            continue
        r = rec.get(s) or rec.get(str(s)) or {}
        short = [f"{k} {c.get(k, 0):,} under the receipt's {int(v):,}"
                 for k, v in r.items() if k in ("hitters", "swings") and c.get(k, 0) < int(v)]
        if short:
            out[s] = "(" + ", ".join(short) + ")"
    return out


def check_swing_seasons(seasons: Iterable[int], *, source: str = SWING_SOURCE,
                        swing_dir: Optional[Path] = None,
                        receipts: Optional[dict] = None) -> dict:
    """Count each needed season and raise SwingSeasonsMissing naming every
    missing one. Returns {season: counts}. Reads only."""
    counts = {int(s): swing_counts(read_swings(s, source=source, swing_dir=swing_dir))
              for s in seasons}
    miss = missing_swing_seasons(counts, source=source, receipts=receipts)
    if miss:
        raise SwingSeasonsMissing(list(miss), source, miss)
    return counts


def needed_swing_seasons(season: int) -> list:
    """The swing seasons a frame of ``season`` reads: the season and the one
    before it (the prior-season cut and baseline), from 2024 on."""
    return [s for s in (int(season) - 1, int(season)) if s >= FIRST_SWING_SEASON]


def competitive_cut(swings: pd.DataFrame) -> pd.Series:
    """Per hitter, the 10th percentile of bat speed over the given non-bunt
    swings of 50 mph or more (the rows passed in are the whole sample used)."""
    s = swings[(~swings["bunt"].astype(bool)) & (swings["bat_speed"] >= COMPETITIVE_MIN_MPH)]
    if s.empty:
        return pd.Series(dtype="float64", name="cut")
    return s.groupby("batter")["bat_speed"].quantile(COMPETITIVE_QUANTILE).rename("cut")


# --------------------------------------------------------------------------- #
# the trend frame
# --------------------------------------------------------------------------- #
class TrendFrame(NamedTuple):
    """One season's per-game aggregates (see the module docstring)."""
    season: int
    games: pd.DataFrame
    pit: pd.DataFrame
    arsenal: pd.DataFrame
    bat: pd.DataFrame
    swings: pd.DataFrame
    prior_cut: dict
    meta: dict


_TABLES = ("games", "pit", "arsenal", "bat", "swings")


def _stat(p: Path) -> Optional[list]:
    try:
        st = Path(p).stat()
    except OSError:
        return None
    return [st.st_size, st.st_mtime_ns]


def _files_sig(files: list) -> list:
    sizes = [(_stat(f) or [0, 0]) for f in files]
    return [len(files), sum(s[0] for s in sizes), max((s[1] for s in sizes), default=0)]


def _nolog(*_a, **_k) -> None:
    return None


def _empty_frame_tables() -> dict:
    return {t: pd.DataFrame() for t in _TABLES}


def _aggregate(season: int, games: pd.DataFrame, pitches: pd.DataFrame,
               clubs: dict, lines, swings: pd.DataFrame) -> dict:
    """The frame's tables from the sidecar, the club map, P8.2's game lines and
    the season's swings. Pure."""
    g = games.sort_values(["start_time", "game_pk"], kind="mergesort").reset_index(drop=True)
    g["game_seq"] = np.arange(len(g), dtype="int64")
    g["home"] = g["game_pk"].map(lambda pk: (clubs.get(int(pk)) or {}).get("home"))
    g["away"] = g["game_pk"].map(lambda pk: (clubs.get(int(pk)) or {}).get("away"))
    g["season"] = int(season)
    gcols = ["season", "game_pk", "game_seq", "start_time", "date", "home", "away",
             "home_score", "away_score", "sb", "cs"]
    g = g[gcols]
    key = g.set_index("game_pk")[["game_seq", "start_time", "date", "home", "away"]]

    P = pitches.copy()
    P["swing"] = P["call_code"].isin(SWING_CODES)
    P["whiff"] = P["call_code"].isin(WHIFF_CODES)
    P["ooz"] = P["zone"].isin(OUT_OF_ZONE)
    P["chase"] = P["ooz"] & P["swing"]
    P["bbe"] = (P["call_code"] == "X") & P["launch_speed"].notna()
    ls = P["launch_speed"].astype("float64").where(P["bbe"], 0.0)
    la = P["launch_angle"].astype("float64").where(P["bbe"] & P["launch_angle"].notna(), 0.0)
    P["ls_sum"], P["ls_sq"], P["la_sum"] = ls, ls * ls, la
    P["hard"] = P["bbe"] & (P["launch_speed"] >= HARD_HIT_MPH)

    def club_of(df: pd.DataFrame, side_home: pd.Series) -> pd.Series:
        k = key.reindex(df["game_pk"].to_numpy())
        return pd.Series(np.where(side_home.to_numpy(), k["home"].to_numpy(),
                                  k["away"].to_numpy()), index=df.index)

    def stamp(df: pd.DataFrame) -> pd.DataFrame:
        k = key.reindex(df["game_pk"].to_numpy())
        df["season"] = int(season)
        df["game_seq"] = k["game_seq"].to_numpy()
        df["start_time"] = k["start_time"].to_numpy()
        df["date"] = k["date"].to_numpy()
        return df

    # pitchers
    pp = P[P["pitcher"].notna()]
    gp = pp.groupby(["game_pk", "pitcher"], sort=True)
    pit = pd.DataFrame({"np": gp.size(), "swings": gp["swing"].sum(),
                        "whiffs": gp["whiff"].sum(), "ooz": gp["ooz"].sum(),
                        "chases": gp["chase"].sum(),
                        "half": gp["half"].first()}).reset_index()
    pit["club"] = club_of(pit, pit["half"] == "top")
    pl = lines.pit.rename(columns={"mlbam": "pitcher"})[
        ["game_pk", "pitcher", "gs", "bf", "so", "bb", "hbp", "outs", "li"]]
    pit["pitcher"] = pit["pitcher"].astype("int64")
    pit = pit.merge(pl, on=["game_pk", "pitcher"], how="left")
    pit["start"] = pit["gs"].fillna(0).astype("int64") > 0
    for c in ("bf", "so", "bb", "hbp", "outs"):
        pit[c] = pit[c].fillna(0).astype("int64")
    pit = stamp(pit)
    pit = pit[["season", "game_pk", "game_seq", "start_time", "date", "pitcher", "club",
               "start", "li", "bf", "so", "bb", "hbp", "outs", "np", "swings", "whiffs",
               "ooz", "chases"]]

    # arsenal: pitch type by batter side, with the physics sums
    A = pp.copy()
    A["pitch_type"] = A["pitch_type"].fillna("UN").astype(str)
    A["bat_side"] = A["bat_side"].fillna("").astype(str)
    agg = {"n": ("game_pk", "size")}
    for v in PHYSICS:
        x = A[v].astype("float64")
        A[f"n_{v}"] = x.notna().astype("int64")
        A[f"s_{v}"] = x.fillna(0.0)
        A[f"q_{v}"] = (x * x).fillna(0.0)
        agg.update({f"n_{v}": (f"n_{v}", "sum"), f"s_{v}": (f"s_{v}", "sum"),
                    f"q_{v}": (f"q_{v}", "sum")})
    ars = A.groupby(["game_pk", "pitcher", "pitch_type", "bat_side"], sort=True).agg(**agg)
    ars = ars.reset_index()
    ars["pitcher"] = ars["pitcher"].astype("int64")
    ars = stamp(ars)
    ars = ars[["season", "game_pk", "game_seq", "date", "pitcher", "pitch_type", "bat_side", "n"]
              + [f"{p}_{v}" for v in PHYSICS for p in ("n", "s", "q")]]

    # batters
    bp = P[P["batter"].notna()]
    gb = bp.groupby(["game_pk", "batter"], sort=True)
    bat = pd.DataFrame({"seen": gb.size(), "swings": gb["swing"].sum(),
                        "whiffs": gb["whiff"].sum(), "ooz": gb["ooz"].sum(),
                        "chases": gb["chase"].sum(), "bbe": gb["bbe"].sum(),
                        "ls_sum": gb["ls_sum"].sum(), "ls_sq": gb["ls_sq"].sum(),
                        "la_sum": gb["la_sum"].sum(), "hard": gb["hard"].sum(),
                        "half": gb["half"].first()}).reset_index()
    bat["batter"] = bat["batter"].astype("int64")
    bat["club"] = club_of(bat, bat["half"] == "bottom")
    order = (bp.sort_values(["game_pk", "half", "at_bat_index", "pitch_number"], kind="mergesort")
             .drop_duplicates(["game_pk", "half", "batter"])[["game_pk", "half", "batter"]])
    order["slot"] = order.groupby(["game_pk", "half"]).cumcount()
    first9 = order[order["slot"] < LINEUP_SLOTS][["game_pk", "batter"]].drop_duplicates()
    first9 = first9.assign(started=True)
    first9["batter"] = first9["batter"].astype("int64")
    bat = bat.merge(first9, on=["game_pk", "batter"], how="left")
    bat["started"] = bat["started"].astype("boolean").fillna(False).astype(bool)
    hl = lines.hit.rename(columns={"mlbam": "batter"})[
        ["game_pk", "batter", "pa", "ab", "h", "bb", "hbp", "sf", "so"]]
    bat = bat.merge(hl, on=["game_pk", "batter"], how="left")
    for c in ("pa", "ab", "h", "bb", "hbp", "sf", "so"):
        bat[c] = bat[c].fillna(0).astype("int64")
    for c in ("swings", "whiffs", "ooz", "chases", "bbe", "hard"):
        bat[c] = bat[c].astype("int64")
    bat = stamp(bat)
    bat = bat[["season", "game_pk", "game_seq", "start_time", "date", "batter", "club",
               "started", "pa", "ab", "h", "bb", "hbp", "sf", "so", "seen", "swings",
               "whiffs", "ooz", "chases", "bbe", "ls_sum", "ls_sq", "la_sum", "hard"]]
    for df in (pit, bat):
        for c in ("swings", "whiffs", "ooz", "chases", "np"):
            if c in df.columns:
                df[c] = df[c].astype("int64")

    # swings: non-bunt tracked swings in sidecar games
    sw = swings[~swings["bunt"].astype(bool)].copy() if len(swings) else swings.copy()
    if len(sw):
        sw["game_pk"] = sw["game_pk"].astype("int64")
        sw = sw[sw["game_pk"].isin(key.index)].copy()
        sw["batter"] = sw["batter"].astype("int64")
        sw = stamp(sw)
        sw = sw.sort_values(["game_seq", "batter"], kind="mergesort")
        sw = sw[["season", "game_pk", "game_seq", "date", "batter", "bat_speed",
                 "swing_length", "attack_angle"]].reset_index(drop=True)
    else:
        sw = pd.DataFrame({c: pd.Series(dtype="float64") for c in
                           ("season", "game_pk", "game_seq", "date", "batter", "bat_speed",
                            "swing_length", "attack_angle")})
    return {"games": g, "pit": pit.reset_index(drop=True), "arsenal": ars,
            "bat": bat.reset_index(drop=True), "swings": sw}


def _memo_paths(memo_dir: Path, season: int) -> dict:
    d = Path(memo_dir) / str(int(season))
    out = {t: d / f"{t}.parquet" for t in _TABLES}
    out["prior_cut"] = d / "prior_cut.parquet"
    out["meta"] = d / "meta.json"
    return out


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def pitch_game_frame(season: int, *, physics_dir: Optional[Path] = None,
                     swing_source: str = SWING_SOURCE, swing_dir: Optional[Path] = None,
                     war_daily: Optional[Path] = None, corpus_dir: Optional[Path] = None,
                     win_prob_dir: Optional[Path] = None, games_memo_dir: Optional[Path] = None,
                     memo_dir: Optional[Path] = None, receipts: Optional[dict] = None,
                     refresh: bool = False, log: Callable = _nolog) -> TrendFrame:
    """One season's trend frame (module docstring). Raises FileNotFoundError
    when the sidecar holds no table for the season, SwingSeasonsMissing when a
    needed swing season is missing, and ValueError when club identity falls
    below the resolved-share floor. Writes only its memo."""
    import mlbstats_games as G                    # P8.2's public game lines, read only

    season = int(season)
    pdir = Path(physics_dir or PHYSICS_DIR)
    sdir = swing_dir_for(swing_source, swing_dir)
    mdir = Path(memo_dir or MEMO_DIR)
    pit_p, gam_p = _table(pdir, "pitches", season), _table(pdir, "games", season)
    if not (pit_p.exists() and gam_p.exists()):
        raise FileNotFoundError(
            f"the pitch sidecar holds no {season} table under {pdir}; run "
            "tools/build_pitch_physics.py first")
    need = needed_swing_seasons(season)
    files = {s: swing_files(s, source=swing_source, swing_dir=sdir) for s in need}
    cdir = Path(corpus_dir or G.CORPUS_DIR)
    war_p = Path(war_daily or WAR_BAT)
    sig = {
        "version": FRAME_VERSION, "season": season, "source": swing_source,
        "sidecar": [_stat(pit_p), _stat(gam_p)],
        "swings": {str(s): _files_sig(f) for s, f in files.items()},
        "war_daily": _stat(war_p),
        "corpus": _stat(cdir / "plays" / str(season) / f"plays-{season}.parquet"),
    }
    key = hashlib.sha256(json.dumps(sig, sort_keys=True).encode("ascii")).hexdigest()[:20]
    mp = _memo_paths(mdir, season)

    meta = None
    if not refresh and mp["meta"].exists():
        try:
            meta = json.loads(mp["meta"].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = None
        if not meta or meta.get("key") != key or not all(mp[t].exists() for t in _TABLES):
            meta = None
    if meta is not None:
        counts = {int(s): c for s, c in (meta.get("swing", {}).get("counts") or {}).items()}
        miss = missing_swing_seasons(counts, source=swing_source, receipts=receipts)
        if miss:
            raise SwingSeasonsMissing(list(miss), swing_source, miss)
        tabs = {t: pd.read_parquet(mp[t]) for t in _TABLES}
        pc = pd.read_parquet(mp["prior_cut"]) if mp["prior_cut"].exists() else None
        prior = ({int(b): float(c) for b, c in zip(pc["batter"], pc["cut"])}
                 if pc is not None and len(pc) else {})
        log(f"  trend frame: {season} from the memo ({key})")
        return TrendFrame(season, tabs["games"], tabs["pit"], tabs["arsenal"], tabs["bat"],
                          tabs["swings"], prior, meta)

    # the swing seasons first: a missing season stops before any other work
    sw_by = {s: read_swings(s, source=swing_source, swing_dir=sdir) for s in need}
    counts = {s: swing_counts(df) for s, df in sw_by.items()}
    miss = missing_swing_seasons(counts, source=swing_source, receipts=receipts)
    if miss:
        raise SwingSeasonsMissing(list(miss), swing_source, miss)

    cm = resolve_clubs(season, physics_dir=pdir, war_daily=war_p)
    games = pd.read_parquet(gam_p)
    pcols = ["game_pk", "at_bat_index", "pitch_number", "half", "batter", "pitcher",
             "bat_side", "pitch_type", "zone", "call_code", "launch_speed", "launch_angle"]
    pitches = pd.read_parquet(pit_p, columns=pcols + list(PHYSICS))
    lines = G.player_game_frame(season, corpus_dir=cdir, win_prob_dir=win_prob_dir,
                                memo_dir=games_memo_dir, log=log)
    empty_sw = pd.DataFrame({c: pd.Series(dtype="float64") for c in
                             ("game_date", "game_pk", "batter", "bunt", "bat_speed",
                              "swing_length", "attack_angle")})
    tabs = _aggregate(season, games, pitches, cm.games, lines, sw_by.get(season, empty_sw))
    prior: dict = {}
    if season - 1 in sw_by:
        cut = competitive_cut(sw_by[season - 1])
        prior = {int(b): float(c) for b, c in cut.items()}

    meta = {
        "key": key, "version": FRAME_VERSION, "season": season,
        "covers_through": (str(tabs["games"]["date"].max()) if len(tabs["games"]) else None),
        "games": int(len(tabs["games"])),
        "clubs": cm.meta,
        "game_lines": {k: lines.meta.get(k) for k in ("source", "games", "covers_through")},
        "swing": {"source": swing_source, "seasons": need,
                  "counts": {str(s): c for s, c in counts.items()},
                  "as_of": counts.get(season, {}).get("max_game_date"),
                  "in_frame": int(len(tabs["swings"])),
                  "prior_cut_hitters": len(prior)},
    }
    for t in _TABLES:
        _write_parquet(tabs[t], mp[t])
    _write_parquet(pd.DataFrame({"batter": list(prior), "cut": list(prior.values())},
                                columns=["batter", "cut"]).astype({"batter": "int64", "cut": "float64"}),
                   mp["prior_cut"])
    tmp = mp["meta"].with_suffix(".json.tmp")
    tmp.write_text(json.dumps(meta, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, mp["meta"])
    log(f"  trend frame: {season} built, {meta['games']:,} games, {len(tabs['pit']):,} "
        f"pitcher and {len(tabs['bat']):,} batter games, {len(tabs['swings']):,} swings")
    return TrendFrame(season, tabs["games"], tabs["pit"], tabs["arsenal"], tabs["bat"],
                      tabs["swings"], prior, meta)


__all__ = ["ClubMap", "club_by_game", "resolve_clubs", "PHYSICS_DIR", "TrendFrame",
           "pitch_game_frame", "read_swings", "swing_counts", "check_swing_seasons",
           "missing_swing_seasons", "needed_swing_seasons", "competitive_cut",
           "SwingSeasonsMissing", "SWING_SOURCE", "SWING_RECEIPTS"]

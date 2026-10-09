# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""trend_detect - League Trends' detector (plan 3.1, 3.6, 3.7 and 3.8). Pure.

No file, cache or network is read or written here: every function takes a
trend frame (trend_frames.TrendFrame, or any object with its tables) and an
evaluation date D, and returns a table. Production (the exporter) and the
build's calibration (the lab) share this one code path.

THE STATISTIC (plan 3.1). For player p, family F and date D: the window W is
his last k games (a starter's last 3 starts, a reliever's last 6 outings, or
last 8 for mix and entry leverage) or his games in the last 30 days (swing
mechanics); the baseline B is his earlier games of the same season. Each game
is one unit with one value (the primary fastball's mean in that game, the
game's family shares, the game's mean over competitive swings).

    z = (mean(W) - mean(B) - drift) / (sigma * sqrt(1/n_W + 1/n_B))

and the bar applies to z / phi, phi the placebo SD of z (FAMILIES carries a
provisional phi of 1.0; the lab measures it). Drift is the mean
window-minus-baseline change over every eligible player of the same role on
the same date, subtracted for every family except entry leverage, which was
calibrated without it. Starters: a start counts with 15 or more primary
fastballs and its variance is s_b^2 + s_w^2 / n (probe P13).

AS OF D, ALWAYS (ruling T3). Only rows dated on or before D are read. Sigma is
the pooled within-player game-to-game SD over the season's games on or before
D; the competitive-swing cut is the hitter's 10th percentile of bat speed over
his swings on or before D (his previous season's cut, from the frame, until he
has 100 swings this season); the role and the primary fastball come from games
on or before D (the primary fastball from the baseline, the appearances before
his last k); the placebo permutes each player's games on or before D only.
Adding games after D changes nothing at D.

THE PLACEBO. Each player's game values are permuted across his own games on
or before D (dates and order fixed; for mix, whole game lines move between
dates), R times. The permutation of a row is fixed by a hash of (seed,
repetition, player, game), so it never depends on rows outside the player's
own games on or before D.

SHRINKAGE (plan 3.6, ruling T7). A two-group prior per family, a point mass
at no change with weight pi0 and a normal spread tau:
    shrunk = (1 - lfdr) * d * tau^2 / (tau^2 + se^2)
The fit for season S takes only completed seasons before S (shrink_fit raises
otherwise); with no earlier season the size floor applies to the raw change.
Mix is fitted against the placebo's own distribution of the SELECTED change
(the max of three), and when pi0 is 0 or tau is not identified on that null no
shrunk value exists for mix.

THE RULES (plan 3.7): the rotation switch (PAL's segment constants, read from
pal_gamelogs at call time), the new pitch (a cross-group relabel with the old
group's physics is not new), and playing time with the availability guard.

PRIOR-SEASON MODE (plan 3.8, lane 2.8): until a player clears the baseline
floor, his window is measured against all of his previous season, at bar
6.0; mix and new pitch are excluded, and the swing families enter only when the
build's 2025-against-2024 calibration meets the strict policy.

Nothing here reads a game result, a price, a ledger row or a later value of a
trait, and nothing here ranks or grades a player.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping, Optional, Sequence

import numpy as np
import pandas as pd
from scipy import optimize
from scipy import stats as sst

import pal_gamelogs as PAL
from trend_frames import COMPETITIVE_MIN_MPH, COMPETITIVE_QUANTILE

# --------------------------------------------------------------------------- #
# constants
# --------------------------------------------------------------------------- #
FB_TYPES = ("FF", "SI", "FC")                 # primary fastball candidates, tie order
MIX_FAMILY = {"FF": "FB", "SI": "FB", "FC": "FB",
              "SL": "BR", "ST": "BR", "SV": "BR", "CU": "BR", "KC": "BR", "CS": "BR",
              "CH": "OS", "FS": "OS", "FO": "OS", "SC": "OS", "KN": "OS", "EP": "OS"}
MIX_FAMS = ("FB", "BR", "OS")
MIX_LABEL = {"FB": "fastballs", "BR": "breaking balls", "OS": "changeups and splitters"}
# new-pitch groups: a relabel inside a group (SL/ST/SV, CU/KC/CS, CH/FS/FO/SC)
# is never a new pitch
NEW_PITCH_GROUP = {"FF": "FF", "FA": "FF", "SI": "SI", "FC": "FC",
                   "SL": "SL", "ST": "SL", "SV": "SL", "CU": "CU", "KC": "CU", "CS": "CU",
                   "CH": "CH", "FS": "CH", "FO": "CH", "SC": "CH", "KN": "KN", "EP": "EP"}

ACTIVE_DAYS = 14                 # a player is tested only with a game in the last 14 days
ROLE_START_SHARE = 0.5           # SP when half or more of his appearances to D are starts
MIN_SIGMA_GAMES = 5              # a player enters the pooled SD with 5 or more games
LI_FLOOR = 0.05                  # log(LI) is taken at 0.05 or more
CUT_MIN_SWINGS = 100             # own competitive cut from 100 swings on
MIX_SIDE_MIN = 30                # baseline pitches to a batter side for a side share
MIX_NU = 8.0                     # pseudo-games pulling a pitcher's residual SD to his role's
MIX_TESTS = 3                    # the three families, Bonferroni
BAR_GRID = (2.5, 3.0, 3.25, 3.5, 3.75, 4.0, 4.25, 4.5, 4.75, 5.0, 5.5, 6.0)
PLACEBO_R = 20
PLACEBO_SEED = 20261001

# the new-pitch rule (lane 2.6)
NEW_PITCH_MIN_SHARE = 0.08
NEW_PITCH_MIN_N = 15
NEW_PITCH_MAX_BASE_SHARE = 0.01
NEW_PITCH_MIN_BASE_N = 300
NEW_PITCH_MPH = 2.0
NEW_PITCH_INCHES = 3.0

# the rotation rule: the window lengths are the lane's; every segment share and
# count is PAL's own (pal_gamelogs, read at call time, never copied)
ROTATION_IN_LAST = 3
ROTATION_OUT_LAST = 4

# playing time with the availability guard (lane 2.6, probe P15)
PT_WINDOW = 14
PT_ABSENCE_RUN = 10
PT_MIN_TENURE = 20
PT_IN_STARTS, PT_IN_MAX_SHARE, PT_IN_MIN_AVAIL = 13, 0.40, 30
PT_OUT_STARTS, PT_OUT_MIN_SHARE, PT_OUT_MIN_AVAIL = 3, 0.85, 40

# prior-season mode (lane 2.8)
PRIOR_SEASON_BAR = 6.0
PRIOR_BASELINE_MIN = 8


@dataclass(frozen=True)
class Family:
    key: str
    label: str
    unit: str
    kind: str                      # "game_mean", "mix" or "swing"
    value: str                     # the frame column the game value is taken from
    roles: tuple
    window: dict                   # role -> ("count", k) or ("days", w)
    min_window: int                # window games (a count window needs all k)
    min_baseline: int              # earlier games (also the prior-season floor)
    min_per_game: int              # pitches, swings or tracked values a game needs
    size_floor: Optional[float]    # on the shrunk change (the raw change with no fit)
    drift: bool
    two_component: bool = False
    pool: Optional[str] = None     # swing families: the hitters tested
    log_value: bool = False
    phi: float = 1.0               # provisional placebo SD of z; the lab measures it


_POOL = "all tracked"              # owner answer TR-Q3 (a): every tracked hitter

FAMILIES = {f.key: f for f in (
    Family("sp_velo", "Fastball velocity, last 3 starts", "mph", "game_mean", "start_speed",
           ("SP",), {"SP": ("count", 3)}, 3, 5, 15, 1.0, True, two_component=True),
    Family("rp_velo", "Fastball velocity, last 6 outings", "mph", "game_mean", "start_speed",
           ("RP",), {"RP": ("count", 6)}, 6, 5, 5, 1.0, True),
    Family("rp_ivb", "Fastball induced vertical break, last 6 outings", "in", "game_mean", "ivb",
           ("RP",), {"RP": ("count", 6)}, 6, 5, 5, 1.5, True),
    Family("rp_hb", "Fastball horizontal break, last 6 outings", "in", "game_mean", "hb",
           ("RP",), {"RP": ("count", 6)}, 6, 5, 5, 1.5, True),
    Family("rp_spin", "Fastball spin, last 6 outings", "rpm", "game_mean", "spin",
           ("RP",), {"RP": ("count", 6)}, 6, 5, 5, 100.0, True),
    # the plan names no extension floor; this family is on the looser list only
    Family("rp_ext", "Fastball extension, last 6 outings", "ft", "game_mean", "ext",
           ("RP",), {"RP": ("count", 6)}, 6, 5, 5, None, True),
    Family("mix", "Pitch-family mix, last 3 starts or 8 outings", "share", "mix", "n",
           ("SP", "RP"), {"SP": ("count", 3), "RP": ("count", 8)}, 3, 6, 12, 0.08, True),
    Family("rp_entry_li", "Entry Leverage Index, last 8 outings", "log LI", "game_mean", "li",
           ("RP",), {"RP": ("count", 8)}, 8, 8, 0, float(np.log(1.5)), False, log_value=True),
    Family("bat_speed", "Bat speed, last 30 days", "mph", "swing", "bat_speed",
           ("H",), {"H": ("days", 30)}, 8, 15, 3, 1.0, True, pool=_POOL),
    Family("swing_length", "Swing length, last 30 days", "ft", "swing", "swing_length",
           ("H",), {"H": ("days", 30)}, 8, 15, 3, 0.2, True, pool=_POOL),
    Family("attack_angle", "Attack angle, last 30 days", "deg", "swing", "attack_angle",
           ("H",), {"H": ("days", 30)}, 8, 15, 3, 2.0, True, pool=_POOL),
)}

# Provisional bars (plan 3.3), pinned to the eval artifact by TR_2B's test.
# strict: TR-Q1 (a), the owner's answer; the swing bars at the production pool
# of TR-Q3 (a). looser: TR-Q1 (b), the same pool.
BAR_POLICY = "strict"
BARS_PROVISIONAL = True
BARS = {
    "strict": {"sp_velo": 4.5, "rp_velo": 4.5, "rp_ivb": 5.0, "rp_hb": 4.5, "mix": 6.0,
               "rp_entry_li": 4.0, "bat_speed": 4.25, "swing_length": 4.25,
               "attack_angle": 4.25},
    "looser": {"sp_velo": 4.0, "rp_velo": 4.25, "rp_ivb": 4.5, "rp_hb": 4.25,
               "rp_spin": 4.75, "rp_ext": 4.5, "mix": 5.5, "rp_entry_li": 3.75,
               "bat_speed": 4.0, "swing_length": 4.0, "attack_angle": 4.0},
}
PRIOR_EXCLUDED = frozenset({"mix"})          # and the new-pitch rule


def bar_for(key: str, policy: str = BAR_POLICY) -> Optional[float]:
    """The family's bar under a policy, or None when the family is off that list."""
    return BARS[policy].get(key)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _day(D) -> str:
    return str(D)[:10]


def _minus(D: str, days: int) -> str:
    return (date.fromisoformat(D) - timedelta(days=int(days))).isoformat()


def eval_dates(season: int, last_date: str) -> list:
    """The calibration's evaluation dates: every Sunday from the third Sunday
    of May to the season's last game date."""
    d = date(int(season), 5, 15)
    while d.weekday() != 6:
        d += timedelta(days=1)
    out, end = [], date.fromisoformat(_day(last_date))
    while d <= end:
        out.append(d.isoformat())
        d += timedelta(days=7)
    return out


def _fam(family) -> Family:
    return family if isinstance(family, Family) else FAMILIES[family]


_TEST_COLS = ["family", "pid", "D", "role", "nW", "nB", "mean_w", "mean_b", "raw", "drift",
              "d", "se", "z", "z_adj", "w_first", "w_last"]


def _empty_tests(extra=()) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="float64") for c in _TEST_COLS + list(extra)})


def _keys(seed: int, rep: int, pid, game_pk) -> np.ndarray:
    """A splitmix64 hash of (seed, repetition, player, game): the placebo's
    permutation key for one row, independent of every other row."""
    with np.errstate(over="ignore"):
        x = (np.asarray(pid, dtype="int64").astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15))
        x ^= np.asarray(game_pk, dtype="int64").astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F)
        x ^= np.uint64((int(seed) * 1000003 + int(rep) * 7919 + 1) & 0xFFFFFFFFFFFFFFFF)
        x ^= x >> np.uint64(30)
        x *= np.uint64(0xBF58476D1CE4E5B9)
        x ^= x >> np.uint64(27)
        x *= np.uint64(0x94D049BB133111EB)
        x ^= x >> np.uint64(31)
    return x


def _permute(vt: pd.DataFrame, cols: Sequence[str], seed: int, rep: int) -> pd.DataFrame:
    """Each player's ``cols`` permuted across his own rows (dates fixed)."""
    if vt.empty:
        return vt.copy()
    pid = vt["pid"].to_numpy()
    by_seq = np.lexsort((vt["game_seq"].to_numpy(), pid))
    by_key = np.lexsort((_keys(seed, rep, pid, vt["game_pk"].to_numpy()), pid))
    out = vt.copy()
    for c in cols:
        arr = vt[c].to_numpy()
        new = arr.copy()
        new[by_seq] = arr[by_key]
        out[c] = new
    return out


def roles_as_of(frame, D) -> pd.Series:
    """pitcher -> "SP" or "RP" from his appearances on or before D."""
    D = _day(D)
    p = frame.pit[frame.pit["date"] <= D]
    share = p.groupby("pitcher")["start"].mean()
    return pd.Series(np.where(share >= ROLE_START_SHARE, "SP", "RP"), index=share.index)


def _pooled_sd(u: pd.DataFrame) -> float:
    n_i = u.groupby("pid")["value"].transform("count")
    m = u[n_i >= MIN_SIGMA_GAMES]
    if m.empty:
        return float("nan")
    dev = m["value"] - m.groupby("pid")["value"].transform("mean")
    df = len(m) - m["pid"].nunique()
    return float(np.sqrt((dev ** 2).sum() / df)) if df > 0 else float("nan")


# --------------------------------------------------------------------------- #
# game values, as of D
# --------------------------------------------------------------------------- #
def _fb_values(frame, D: str, fam: Family) -> pd.DataFrame:
    """Per qualifying game: the primary fastball's mean of ``fam.value``, its
    tracked count and within-game variance. Role and primary fastball as of D."""
    cols = ["pid", "game_pk", "game_seq", "date", "role", "value", "n", "wvar"]
    pit = frame.pit.loc[frame.pit["date"] <= D, ["pitcher", "game_pk", "game_seq", "date", "start"]]
    if pit.empty:
        return pd.DataFrame(columns=cols)
    pit = pit.assign(role=pit["pitcher"].map(roles_as_of(frame, D)))
    role = fam.roles[0]
    apps = pit[(pit["role"] == "SP") & pit["start"]] if role == "SP" else pit[pit["role"] == "RP"]
    k = fam.window[role][1]
    apps = apps.sort_values(["pitcher", "game_seq"], kind="mergesort")
    apps = apps.assign(rk=apps.groupby("pitcher").cumcount(ascending=False).to_numpy())
    v = fam.value
    a = frame.arsenal
    a = a[(a["date"] <= D) & a["pitch_type"].isin(FB_TYPES)]
    a = (a.groupby(["pitcher", "game_pk", "pitch_type"], as_index=False)
         [["n", f"n_{v}", f"s_{v}", f"q_{v}"]].sum())
    a = a.merge(apps[["pitcher", "game_pk", "game_seq", "date", "rk", "role"]],
                on=["pitcher", "game_pk"], how="inner")
    base = a[a["rk"] >= k].groupby(["pitcher", "pitch_type"], as_index=False)["n"].sum()
    base = base[base["n"] > 0]
    base["tie"] = base["pitch_type"].map({t: i for i, t in enumerate(FB_TYPES)})
    prim = (base.sort_values(["pitcher", "n", "tie"], ascending=[True, False, True], kind="mergesort")
            .drop_duplicates("pitcher")[["pitcher", "pitch_type"]])
    a = a.merge(prim, on=["pitcher", "pitch_type"], how="inner")
    nv = a[f"n_{v}"].astype("float64")
    a = a[nv >= max(fam.min_per_game, 1)].copy()
    if a.empty:
        return pd.DataFrame(columns=cols)
    n = a[f"n_{v}"].astype("float64")
    s, q = a[f"s_{v}"].astype("float64"), a[f"q_{v}"].astype("float64")
    a["value"] = s / n
    a["wvar"] = np.where(n > 1, ((q - s * s / n) / (n - 1).clip(lower=1)).clip(lower=0.0), np.nan)
    a["n"] = n
    return a.rename(columns={"pitcher": "pid"})[cols].reset_index(drop=True)


def _li_values(frame, D: str, fam: Family) -> pd.DataFrame:
    """Relief outings of relievers: log of the first batter's Leverage Index."""
    pit = frame.pit[(frame.pit["date"] <= D)]
    pit = pit.assign(role=pit["pitcher"].map(roles_as_of(frame, D)))
    u = pit[(pit["role"] == "RP") & (~pit["start"].astype(bool)) & pit["li"].notna()]
    out = pd.DataFrame({"pid": u["pitcher"].to_numpy(), "game_pk": u["game_pk"].to_numpy(),
                        "game_seq": u["game_seq"].to_numpy(), "date": u["date"].to_numpy(),
                        "role": "RP",
                        "value": np.log(np.clip(u["li"].astype("float64").to_numpy(), LI_FLOOR, None)),
                        "n": 1.0, "wvar": np.nan})
    return out


def competitive_cut_as_of(frame, D) -> pd.Series:
    """batter -> competitive-swing cut as of D: the 10th percentile of his bat
    speed over his swings of 50 mph or more on or before D once he has 100
    swings, his previous season's cut before that (no cut, no test)."""
    D = _day(D)
    s = frame.swings[frame.swings["date"] <= D]
    nsw = s.groupby("batter").size()
    s50 = s[s["bat_speed"] >= COMPETITIVE_MIN_MPH]
    own = s50.groupby("batter")["bat_speed"].quantile(COMPETITIVE_QUANTILE)
    own = own[nsw.reindex(own.index).fillna(0) >= CUT_MIN_SWINGS]
    prior = pd.Series(frame.prior_cut or {}, dtype="float64")
    prior = prior[prior.index.isin(nsw.index)]
    cut = own.combine_first(prior) if len(prior) else own
    cut.index = cut.index.astype("int64")
    return cut.rename("cut").sort_index()


def _swing_values(frame, D: str, fam: Family) -> pd.DataFrame:
    cols = ["pid", "game_pk", "game_seq", "date", "role", "value", "n", "wvar"]
    s = frame.swings[frame.swings["date"] <= D]
    if s.empty:
        return pd.DataFrame(columns=cols)
    cut = competitive_cut_as_of(frame, D)
    s = s[s["batter"].isin(cut.index)]
    floor = np.maximum(s["batter"].map(cut).to_numpy(dtype="float64"), COMPETITIVE_MIN_MPH)
    s = s[(s["bat_speed"].to_numpy() >= floor) & s[fam.value].notna().to_numpy()]
    g = (s.groupby(["batter", "game_pk", "game_seq", "date"])[fam.value]
         .agg(["mean", "count"]).reset_index())
    g = g[g["count"] >= fam.min_per_game]
    return pd.DataFrame({"pid": g["batter"].astype("int64").to_numpy(),
                         "game_pk": g["game_pk"].to_numpy(), "game_seq": g["game_seq"].to_numpy(),
                         "date": g["date"].to_numpy(), "role": "H",
                         "value": g["mean"].astype("float64").to_numpy(),
                         "n": g["count"].astype("float64").to_numpy(), "wvar": np.nan})


def game_values(frame, D, family) -> pd.DataFrame:
    """The family's per-game value table as of D (not for mix)."""
    fam, D = _fam(family), _day(D)
    if fam.kind == "swing":
        return _swing_values(frame, D, fam)
    if fam.log_value:
        return _li_values(frame, D, fam)
    if fam.kind == "game_mean":
        return _fb_values(frame, D, fam)
    raise ValueError(f"{fam.key} has no per-game value table (mix uses mix_values)")


def sigma(frame, D, family) -> dict:
    """role -> the pooled within-player game-to-game SD as of D."""
    fam = _fam(family)
    vt = game_values(frame, D, fam)
    return {r: _pooled_sd(vt[vt["role"] == r]) for r in fam.roles}


# --------------------------------------------------------------------------- #
# the statistic
# --------------------------------------------------------------------------- #
def _stat_game_mean(vt: pd.DataFrame, D: str, fam: Family, phi: float) -> pd.DataFrame:
    rows = []
    for role in fam.roles:
        u = vt[vt["role"] == role]
        if u.empty:
            continue
        sg = _pooled_sd(u)
        if not np.isfinite(sg) or sg <= 0:
            continue
        last = u.groupby("pid")["date"].transform("max")
        u = u[last >= _minus(D, ACTIVE_DAYS - 1)].sort_values(["pid", "game_seq"], kind="mergesort")
        if u.empty:
            continue
        mode, size = fam.window[role]
        if mode == "count":
            inwin = u.groupby("pid").cumcount(ascending=False).to_numpy() < size
        else:
            inwin = (u["date"] >= _minus(D, size - 1)).to_numpy()
        u = u.assign(inwin=inwin)
        if fam.two_component:
            vv = vt[vt["role"] == role]
            wv = vv["wvar"].astype("float64")
            wv = wv.fillna(wv.median() if wv.notna().any() else 0.0)
            sw2 = float(np.average(wv, weights=vv["n"])) if vv["n"].sum() > 0 else 0.0
            tot = sg * sg
            sb2 = max(tot - sw2 / float(vv["n"].median()), 0.05 * tot)
            u = u.assign(w=1.0 / (sb2 + sw2 / u["n"].astype("float64")))
            u = u.assign(wv=u["w"] * u["value"])
            g = u.groupby(["pid", "inwin"]).agg(sw=("w", "sum"), swv=("wv", "sum"),
                                                cnt=("value", "size"))
            g["m"] = g["swv"] / g["sw"]
            g["v"] = 1.0 / g["sw"]
        else:
            g = u.groupby(["pid", "inwin"]).agg(m=("value", "mean"), cnt=("value", "size"))
            g["v"] = np.nan
        g = g.unstack("inwin")
        if (True not in g["cnt"].columns) or (False not in g["cnt"].columns):
            continue
        t = pd.DataFrame({"nW": g["cnt"][True], "nB": g["cnt"][False],
                          "mean_w": g["m"][True], "mean_b": g["m"][False],
                          "v_w": g["v"][True], "v_b": g["v"][False]}).dropna(subset=["nW", "nB"])
        t = t[(t["nW"] == size) if mode == "count" else (t["nW"] >= fam.min_window)]
        t = t[t["nB"] >= fam.min_baseline]
        if t.empty:
            continue
        wdates = u[u["inwin"]].groupby("pid")["date"].agg(["min", "max"])
        t["raw"] = t["mean_w"] - t["mean_b"]
        t["drift"] = float(t["raw"].mean()) if fam.drift else 0.0
        t["d"] = t["raw"] - t["drift"]
        if fam.two_component:
            t["se"] = np.sqrt(t["v_w"] + t["v_b"])
        else:
            t["se"] = sg * np.sqrt(1.0 / t["nW"] + 1.0 / t["nB"])
        t["z"] = t["d"] / t["se"]
        t["z_adj"] = t["z"] / phi
        t["w_first"] = wdates["min"].reindex(t.index)
        t["w_last"] = wdates["max"].reindex(t.index)
        t["role"] = role
        t["sigma"] = sg
        rows.append(t.reset_index())
    if not rows:
        return _empty_tests(["sigma"])
    out = pd.concat(rows, ignore_index=True)
    out["family"], out["D"] = fam.key, D
    out["pid"] = out["pid"].astype("int64")
    for c in ("nW", "nB"):
        out[c] = out[c].astype("int64")
    return out[_TEST_COLS + ["sigma"]].sort_values(["role", "pid"], kind="mergesort").reset_index(drop=True)


def mix_values(frame, D) -> pd.DataFrame:
    """One row per (pitcher, game, batter side) on or before D: the family
    counts and the side's pitches, for games of 12 or more pitches to left- and
    right-handed batters; role as of D."""
    D = _day(D)
    fam = FAMILIES["mix"]
    a = frame.arsenal
    a = a[(a["date"] <= D) & a["bat_side"].isin(["L", "R"])]
    cols = ["pid", "game_pk", "game_seq", "date", "role", "side", *MIX_FAMS, "tot"]
    if a.empty:
        return pd.DataFrame(columns=cols)
    grp = a["pitch_type"].map(MIX_FAMILY).fillna("OT")
    w = (a.assign(grp=grp).pivot_table(index=["pitcher", "game_pk", "bat_side"], columns="grp",
                                         values="n", aggfunc="sum", fill_value=0))
    for c in MIX_FAMS:
        if c not in w.columns:
            w[c] = 0
    w["tot"] = w.sum(axis=1)
    w = w[list(MIX_FAMS) + ["tot"]].reset_index()
    gt = w.groupby(["pitcher", "game_pk"])["tot"].transform("sum")
    w = w[gt >= fam.min_per_game]
    pit = frame.pit.loc[frame.pit["date"] <= D, ["pitcher", "game_pk", "game_seq", "date"]]
    w = w.merge(pit, on=["pitcher", "game_pk"], how="inner")
    w["role"] = w["pitcher"].map(roles_as_of(frame, D))
    w = w.rename(columns={"pitcher": "pid", "bat_side": "side"})
    return w[cols].reset_index(drop=True)


def _stat_mix(w: pd.DataFrame, D: str, phi: float) -> pd.DataFrame:
    fam = FAMILIES["mix"]
    extra = ["fam_sel", "t", "share_w", "share_b", "expected_w"]
    if w.empty:
        return _empty_tests(extra)
    last = w.groupby("pid")["date"].transform("max")
    w = w[last >= _minus(D, ACTIVE_DAYS - 1)]
    if w.empty:
        return _empty_tests(extra)
    games = (w[["pid", "game_pk", "game_seq", "date", "role"]].drop_duplicates(["pid", "game_pk"])
             .sort_values(["pid", "game_seq"], kind="mergesort"))
    k = np.where(games["role"] == "SP", fam.window["SP"][1], fam.window["RP"][1])
    games = games.assign(inwin=games.groupby("pid").cumcount(ascending=False).to_numpy() < k, k=k)
    w = w.merge(games[["pid", "game_pk", "inwin", "k"]], on=["pid", "game_pk"])
    base = w[~w["inwin"]]
    bh = base.groupby(["pid", "side"])[list(MIX_FAMS) + ["tot"]].sum()
    bt = base.groupby("pid")[list(MIX_FAMS) + ["tot"]].sum()
    bh = bh[bh["tot"] >= MIX_SIDE_MIN]
    for c in MIX_FAMS:
        bh[f"p_{c}"] = bh[c] / bh["tot"]
        bt[f"q_{c}"] = bt[c] / bt["tot"].where(bt["tot"] > 0)
    w = w.merge(bh[[f"p_{c}" for c in MIX_FAMS]].reset_index(), on=["pid", "side"], how="left")
    w = w.merge(bt[[f"q_{c}" for c in MIX_FAMS]].reset_index(), on="pid", how="left")
    for c in MIX_FAMS:
        w[f"e_{c}"] = w["tot"] * w[f"p_{c}"].fillna(w[f"q_{c}"])
    w = w[w[[f"e_{c}" for c in MIX_FAMS]].notna().all(axis=1)]
    gg = (w.groupby(["pid", "game_pk", "game_seq", "date", "inwin", "role", "k"])
          [list(MIX_FAMS) + [f"e_{c}" for c in MIX_FAMS] + ["tot"]].sum().reset_index())
    for c in MIX_FAMS:
        gg[f"r_{c}"] = (gg[c] - gg[f"e_{c}"]) / gg["tot"]
    b, wn = gg[~gg["inwin"]], gg[gg["inwin"]]
    nb, nw = b.groupby("pid").size(), wn.groupby("pid").size()
    kk = gg.groupby("pid")["k"].first()
    role = gg.groupby("pid")["role"].first()
    ok = nw.index[(nw == kk.reindex(nw.index)).to_numpy()]
    ok = ok.intersection(nb.index[(nb >= fam.min_baseline).to_numpy()])
    if not len(ok):
        return _empty_tests(extra)
    ok = pd.Index(sorted(ok))
    Z, Dd, SE, RAW, DR = [], [], [], [], []
    for c in MIX_FAMS:
        pooled = b.groupby("role")[f"r_{c}"].apply(lambda x: float(np.mean(x ** 2)))
        own = b.groupby("pid")[f"r_{c}"].agg(lambda x: float(np.sum(x ** 2)))
        s2 = ((MIX_NU * role.loc[ok].map(pooled) + own.reindex(ok).fillna(0.0))
              / (MIX_NU + nb.reindex(ok).fillna(0.0)))
        mw = wn.groupby("pid")[f"r_{c}"].mean().reindex(ok)
        rk = role.loc[ok]
        dr = mw.groupby(rk).transform("mean") if fam.drift else mw * 0.0
        dd = mw - dr
        se = np.sqrt(s2 * (1.0 / nw.reindex(ok) + 1.0 / nb.reindex(ok)))
        Z.append((dd / se).to_numpy(dtype="float64"))
        Dd.append(dd.to_numpy(dtype="float64"))
        SE.append(se.to_numpy(dtype="float64"))
        RAW.append(mw.to_numpy(dtype="float64"))
        DR.append(dr.to_numpy(dtype="float64"))
    Z, Dd, SE = np.column_stack(Z), np.column_stack(Dd), np.column_stack(SE)
    RAW, DR = np.column_stack(RAW), np.column_stack(DR)
    Zf = np.where(np.isfinite(Z), Z, 0.0)
    j = np.argmax(np.abs(Zf), axis=1)
    ar = np.arange(len(j))
    t = Zf[ar, j]
    pv = np.minimum(1.0, MIX_TESTS * 2.0 * sst.norm.sf(np.abs(t)))
    zb = np.where(pv < 1.0, sst.norm.isf(np.maximum(pv, 1e-300) / 2.0), 0.0) * np.sign(t)
    sel = [MIX_FAMS[x] for x in j]
    wsum = wn.groupby("pid")[list(MIX_FAMS) + [f"e_{c}" for c in MIX_FAMS] + ["tot"]].sum().reindex(ok)
    bsum = b.groupby("pid")[list(MIX_FAMS) + ["tot"]].sum().reindex(ok)
    share_w = np.array([wsum[c].iloc[i] / wsum["tot"].iloc[i] for i, c in enumerate(sel)])
    share_b = np.array([bsum[c].iloc[i] / bsum["tot"].iloc[i] for i, c in enumerate(sel)])
    exp_w = np.array([wsum[f"e_{c}"].iloc[i] / wsum["tot"].iloc[i] for i, c in enumerate(sel)])
    wdates = wn.groupby("pid")["date"].agg(["min", "max"]).reindex(ok)
    out = pd.DataFrame({
        "family": "mix", "pid": ok.astype("int64"), "D": D, "role": role.loc[ok].to_numpy(),
        "nW": nw.reindex(ok).astype("int64").to_numpy(), "nB": nb.reindex(ok).astype("int64").to_numpy(),
        "mean_w": share_w, "mean_b": share_b, "raw": RAW[ar, j], "drift": DR[ar, j],
        "d": Dd[ar, j], "se": SE[ar, j], "z": zb, "z_adj": zb / phi,
        "w_first": wdates["min"].to_numpy(), "w_last": wdates["max"].to_numpy(),
        "fam_sel": sel, "t": t, "share_w": share_w, "share_b": share_b, "expected_w": exp_w})
    return out.sort_values(["role", "pid"], kind="mergesort").reset_index(drop=True)


def _phi(fam: Family, phi: Optional[float]) -> float:
    return float(fam.phi if phi is None else phi)


def detect(frame, D, family, *, phi: Optional[float] = None) -> pd.DataFrame:
    """Every eligible player's test for one family at D (as of D). Columns:
    family, pid, D, role, nW, nB, mean_w, mean_b, raw (window minus
    baseline), drift, d (raw minus drift), se, z, z_adj (z / phi), w_first,
    w_last; mix adds fam_sel, t (the selected family's unadjusted z), share_w,
    share_b and expected_w (the share his baseline gives for the window's
    batter sides). No flag is set here: see flag()."""
    fam, D = _fam(family), _day(D)
    if fam.kind == "mix":
        return _stat_mix(mix_values(frame, D), D, _phi(fam, phi))
    return _stat_game_mean(game_values(frame, D, fam), D, fam, _phi(fam, phi))


def placebo(frame, D, family, R: int = PLACEBO_R, seed: int = PLACEBO_SEED, *,
            phi: Optional[float] = None) -> pd.DataFrame:
    """The same statistic after each player's games on or before D are
    permuted across his own game dates, R times; a column ``rep`` numbers the
    repetitions. Role, primary fastball and the competitive cut are taken from
    the real games on or before D before the permutation."""
    fam, D = _fam(family), _day(D)
    out = []
    if fam.kind == "mix":
        w = mix_values(frame, D)
        g = w[["pid", "game_pk", "game_seq", "date"]].drop_duplicates(["pid", "game_pk"])
        for r in range(int(R)):
            pg = _permute(g, ["game_seq", "date"], seed, r)
            ww = w.drop(columns=["game_seq", "date"]).merge(pg, on=["pid", "game_pk"])
            t = _stat_mix(ww, D, _phi(fam, phi))
            out.append(t.assign(rep=r))
    else:
        vt = game_values(frame, D, fam)
        for r in range(int(R)):
            t = _stat_game_mean(_permute(vt, ["value", "n", "wvar"], seed, r), D, fam,
                                _phi(fam, phi))
            out.append(t.assign(rep=r))
    return pd.concat(out, ignore_index=True) if out else _empty_tests(["rep"])


# --------------------------------------------------------------------------- #
# shrinkage
# --------------------------------------------------------------------------- #
def two_group_fit(d, se) -> tuple:
    """(pi0, tau) by maximum likelihood: d ~ pi0 N(0, se^2) + (1 - pi0) N(0, tau^2 + se^2)."""
    d = np.asarray(d, dtype="float64")
    se = np.asarray(se, dtype="float64")
    keep = np.isfinite(d) & np.isfinite(se) & (se > 0)
    d, se = d[keep], se[keep]
    if len(d) < 10:
        raise ValueError(f"a shrink fit needs 10 or more tests, got {len(d)}")

    def nll(th):
        pi0 = 1.0 / (1.0 + np.exp(-th[0]))
        t1 = np.exp(th[1])
        f0 = sst.norm.pdf(d, 0, se)
        f1 = sst.norm.pdf(d, 0, np.sqrt(t1 ** 2 + se ** 2))
        return -np.sum(np.log(pi0 * f0 + (1 - pi0) * f1 + 1e-300))

    sd = float(np.std(d)) + 1e-9
    best = None
    for x0 in ([2.0, np.log(sd)], [0.0, np.log(sd)], [3.0, np.log(3 * sd)]):
        r = optimize.minimize(nll, x0=x0, method="Nelder-Mead", options={"maxiter": 4000})
        if best is None or r.fun < best.fun:
            best = r
    return float(1.0 / (1.0 + np.exp(-best.x[0]))), float(np.exp(best.x[1]))


def _fit_seasons(scored_season: int, fit_seasons: Sequence[int], have) -> list:
    fs = sorted({int(s) for s in fit_seasons})
    late = [s for s in fs if s >= int(scored_season)]
    if late:
        raise ValueError(f"the shrink fit for {int(scored_season)} may use only completed seasons "
                         f"before it; got {late}")
    missing = [s for s in fs if s not in have]
    if missing:
        raise ValueError(f"no tests passed for fit seasons {missing}")
    return fs


def shrink_fit(tests_by_season: Mapping[int, pd.DataFrame], scored_season: int,
               fit_seasons: Sequence[int], *, phi: float = 1.0) -> Optional[dict]:
    """The two-group fit for scoring ``scored_season``, on the tests of
    ``fit_seasons`` only, every one before the scored season (raises
    otherwise). None when no earlier season exists: the size floor then
    applies to the raw change."""
    tbs = {int(s): t for s, t in tests_by_season.items()}
    fs = _fit_seasons(scored_season, fit_seasons, set(tbs))
    if not fs:
        return None
    t = pd.concat([tbs[s] for s in fs], ignore_index=True)
    pi0, tau = two_group_fit(t["d"], t["se"] * phi)
    return {"kind": "normal", "pi0": pi0, "tau": tau, "phi": float(phi), "seasons": fs,
            "scored_season": int(scored_season), "n_tests": int(len(t)), "identified": True}


def _silverman(x: np.ndarray) -> float:
    sd = float(np.std(x))
    iqr = float(np.subtract(*np.percentile(x, [75, 25])))
    a = min(sd, iqr / 1.349) if iqr > 0 else sd
    return float(0.9 * max(a, 1e-3) * len(x) ** (-0.2))


MIX_NULL_MAX = 1000


def mix_null(placebo_tests: pd.DataFrame) -> np.ndarray:
    """The null sample for mix shrinkage: the placebo's SELECTED t (the
    largest of the three family z's, signed), symmetrised, at most 1,000 points
    taken evenly in sorted order (deterministic)."""
    t = placebo_tests["t"].to_numpy(dtype="float64")
    t = t[np.isfinite(t)]
    if not len(t):
        return t
    t = np.sort(np.concatenate([t, -t]))
    if len(t) > MIX_NULL_MAX:
        t = t[np.linspace(0, len(t) - 1, MIX_NULL_MAX).round().astype(int)]
    return t


def _mix_dens(t: np.ndarray, s: np.ndarray, null: np.ndarray, h: float) -> np.ndarray:
    """mean_j N(t - null_j; 0, h^2 + s^2), row-wise for each t with its own s."""
    var = h * h + s * s
    diff = t[:, None] - null[None, :]
    return np.mean(np.exp(-0.5 * diff * diff / var[:, None]), axis=1) / np.sqrt(2 * np.pi * var)


def shrink_fit_mix(tests_by_season: Mapping[int, pd.DataFrame],
                   placebo_by_season: Mapping[int, pd.DataFrame], scored_season: int,
                   fit_seasons: Sequence[int]) -> Optional[dict]:
    """The mix fit against the placebo's own null of the selected change.
    In t units (t = d / se): the null density f0 is a Gaussian kernel density
    of the placebo's selected t; a real change x = delta / se with delta ~ N(0,
    tau^2) widens it, f1 = f0 convolved with N(0, (tau / se)^2). pi0 and tau
    by maximum likelihood. identified is False when pi0 is under 0.001 or tau
    sits on a bound; no shrunk value exists for mix then."""
    tbs = {int(s): t for s, t in tests_by_season.items()}
    pbs = {int(s): t for s, t in placebo_by_season.items()}
    fs = _fit_seasons(scored_season, fit_seasons, set(tbs) & set(pbs))
    if not fs:
        return None
    real = pd.concat([tbs[s] for s in fs], ignore_index=True)
    null = mix_null(pd.concat([pbs[s] for s in fs], ignore_index=True))
    real = real[np.isfinite(real["t"]) & (real["se"] > 0)]
    if len(real) < 10 or len(null) < 50:
        raise ValueError("a mix shrink fit needs 10 or more tests and 50 or more null draws")
    t = real["t"].to_numpy(dtype="float64")
    se = real["se"].to_numpy(dtype="float64")
    h = _silverman(null)
    lo, hi = np.log(1e-4 * np.median(se)), np.log(50.0 * np.median(se))
    f0 = _mix_dens(t, np.zeros_like(t), null, h)

    def nll(th):
        pi0 = 1.0 / (1.0 + np.exp(-th[0]))
        tau = np.exp(np.clip(th[1], lo, hi))
        f1 = _mix_dens(t, tau / se, null, h)
        return -np.sum(np.log(pi0 * f0 + (1 - pi0) * f1 + 1e-300))

    best = None
    for x0 in ([2.0, np.log(np.median(se))], [0.0, np.log(2 * np.median(se))],
               [-1.0, np.log(0.5 * np.median(se))]):
        r = optimize.minimize(nll, x0=x0, method="Nelder-Mead", options={"maxiter": 4000})
        if best is None or r.fun < best.fun:
            best = r
    pi0 = float(1.0 / (1.0 + np.exp(-best.x[0])))
    lt = float(best.x[1])
    tau = float(np.exp(np.clip(lt, lo, hi)))
    on_bound = lt <= lo + 0.05 or lt >= hi - 0.05
    identified = bool(best.success or best.status == 0) and pi0 >= 1e-3 and not on_bound
    return {"kind": "mix_selected_null", "pi0": pi0, "tau": tau, "seasons": fs,
            "scored_season": int(scored_season), "n_tests": int(len(real)),
            "identified": identified,
            "null": {"source": "placebo selected max of three", "h": h, "t": null}}


def shrink_apply(tests: pd.DataFrame, fit: Optional[dict], *, phi: float = 1.0) -> pd.DataFrame:
    """Columns shrunk and lfdr for a test table; NaN when there is no fit, or
    for mix when the fit is not identified."""
    out = tests.copy()
    if fit is None or out.empty or not fit.get("identified", False):
        out["shrunk"], out["lfdr"] = np.nan, np.nan
        return out
    pi0, tau = float(fit["pi0"]), float(fit["tau"])
    d = out["d"].to_numpy(dtype="float64")
    if fit["kind"] == "mix_selected_null":
        null, h = np.asarray(fit["null"]["t"], dtype="float64"), float(fit["null"]["h"])
        se = out["se"].to_numpy(dtype="float64")
        t = out["t"].to_numpy(dtype="float64")
        s = tau / se
        f0 = _mix_dens(t, np.zeros_like(t), null, h)
        var = h * h + s * s
        diff = t[:, None] - null[None, :]
        k = np.exp(-0.5 * diff * diff / var[:, None]) / np.sqrt(2 * np.pi * var[:, None])
        f1 = k.mean(axis=1)
        lfdr = pi0 * f0 / (pi0 * f0 + (1 - pi0) * f1 + 1e-300)
        wts = k / (k.sum(axis=1, keepdims=True) + 1e-300)
        ex = (wts * diff).sum(axis=1) * (s * s / var)          # E[x | t, a real change]
        out["shrunk"] = (1 - lfdr) * se * ex
        out["lfdr"] = lfdr
        return out
    se = out["se"].to_numpy(dtype="float64") * phi
    f0 = sst.norm.pdf(d, 0, se)
    f1 = sst.norm.pdf(d, 0, np.sqrt(tau ** 2 + se ** 2))
    lfdr = pi0 * f0 / (pi0 * f0 + (1 - pi0) * f1 + 1e-300)
    out["shrunk"] = (1 - lfdr) * d * tau ** 2 / (tau ** 2 + se ** 2)
    out["lfdr"] = lfdr
    return out


def flag(tests: pd.DataFrame, family, bar: float, fit: Optional[dict] = None, *,
         phi: float = 1.0) -> pd.DataFrame:
    """Adds shrunk, lfdr, size (the shrunk change, or the raw change net of
    drift when there is no shrunk value), floor_ok and flag (|z_adj| at or
    above the bar and the size at or above the family's size floor)."""
    fam = _fam(family)
    out = shrink_apply(tests, fit, phi=phi)
    if out.empty:
        for c in ("size", "floor_ok", "flag"):
            out[c] = pd.Series(dtype="float64" if c == "size" else "bool")
        return out
    size = out["shrunk"].where(out["shrunk"].notna(), out["d"])
    out["size"] = size
    out["floor_ok"] = True if fam.size_floor is None else (size.abs() >= fam.size_floor)
    out["flag"] = (out["z_adj"].abs() >= float(bar)) & out["floor_ok"].astype(bool)
    return out


def episodes(flags: pd.DataFrame, step_days: int = 1) -> pd.DataFrame:
    """Runs of flagged dates per (family, pid), consecutive when ``step_days``
    apart: first (first flagged), last and dates."""
    if flags.empty:
        return pd.DataFrame(columns=["family", "pid", "first", "last", "dates"])
    f = flags[["family", "pid", "D"]].drop_duplicates().sort_values(["family", "pid", "D"])
    d = pd.to_datetime(f["D"])
    gap = d.groupby([f["family"], f["pid"]]).diff().dt.days
    run = (gap.isna() | (gap != step_days)).cumsum()
    g = f.assign(run=run.to_numpy()).groupby(["family", "pid", "run"])["D"]
    out = g.agg(first="min", last="max", dates="count").reset_index().drop(columns="run")
    return out


# --------------------------------------------------------------------------- #
# the three rules (plan 3.7)
# --------------------------------------------------------------------------- #
def rotation_switch(frame, D) -> pd.DataFrame:
    """Into the rotation: his last 3 appearances all starts after
    PAL.MIN_PRE_RELIEF or more earlier relief outings with a start share of
    PAL.RELIEF_SEG_START_SHARE_MAX or less. Out of it: his last 4 all relief
    after PAL.MIN_PRE_STARTS or more earlier starts with a start share of
    PAL.START_SEG_START_SHARE_MIN or more."""
    D = _day(D)
    cols = ["rule", "pid", "D", "direction", "window", "earlier", "earlier_starts",
            "earlier_relief"]
    u = frame.pit.loc[frame.pit["date"] <= D, ["pitcher", "game_seq", "date", "start"]]
    if u.empty:
        return pd.DataFrame(columns=cols)
    u = u.sort_values(["pitcher", "game_seq"], kind="mergesort")
    last = u.groupby("pitcher")["date"].transform("max")
    u = u[last >= _minus(D, ACTIVE_DAYS - 1)]
    u = u.assign(rk=u.groupby("pitcher").cumcount(ascending=False).to_numpy(),
                 st=u["start"].astype(int))
    out = []
    for n_last, direction in ((ROTATION_IN_LAST, "into"), (ROTATION_OUT_LAST, "out of")):
        w = u[u["rk"] < n_last].groupby("pitcher")["st"].agg(["sum", "count"])
        b = u[u["rk"] >= n_last].groupby("pitcher")["st"].agg(["sum", "count"])
        j = w.join(b, lsuffix="_w", rsuffix="_b", how="inner")
        share = j["sum_b"] / j["count_b"]
        if direction == "into":
            hit = j[(j["count_w"] == n_last) & (j["sum_w"] == n_last)
                    & ((j["count_b"] - j["sum_b"]) >= PAL.MIN_PRE_RELIEF)
                    & (share <= PAL.RELIEF_SEG_START_SHARE_MAX)]
        else:
            hit = j[(j["count_w"] == n_last) & (j["sum_w"] == 0)
                    & (j["sum_b"] >= PAL.MIN_PRE_STARTS)
                    & (share >= PAL.START_SEG_START_SHARE_MIN)]
        for pid, r in hit.iterrows():
            out.append({"rule": "rotation", "pid": int(pid), "D": D, "direction": direction,
                        "window": int(r["count_w"]), "earlier": int(r["count_b"]),
                        "earlier_starts": int(r["sum_b"]),
                        "earlier_relief": int(r["count_b"] - r["sum_b"])})
    return pd.DataFrame(out, columns=cols)


def new_pitch(frame, D) -> pd.DataFrame:
    """A pitch group at 8 percent or more and 15 or more pitches over the window
    (SP last 3 starts, RP last 8 outings) after 1 percent or less of a baseline
    of 300 or more pitches, whose window mean velocity differs by 2 mph or more,
    or its IVB or HB by 3 in or more, from every established baseline group (a
    relabel carries the old group's physics and is not new)."""
    D = _day(D)
    cols = ["rule", "pid", "D", "group", "share_w", "n_w", "share_b", "n_b_tot",
            "speed_w", "ivb_w", "hb_w"]
    a = frame.arsenal
    a = a[(a["date"] <= D)]
    if a.empty:
        return pd.DataFrame(columns=cols)
    a = a.assign(grp=a["pitch_type"].map(NEW_PITCH_GROUP))
    a = a[a["grp"].notna()]
    pit = frame.pit.loc[frame.pit["date"] <= D, ["pitcher", "game_pk", "game_seq", "date"]]
    pit = pit.assign(role=pit["pitcher"].map(roles_as_of(frame, D)))
    last = pit.groupby("pitcher")["date"].transform("max")
    pit = pit[last >= _minus(D, ACTIVE_DAYS - 1)].sort_values(["pitcher", "game_seq"],
                                                               kind="mergesort")
    k = np.where(pit["role"] == "SP", FAMILIES["mix"].window["SP"][1],
                 FAMILIES["mix"].window["RP"][1])
    pit = pit.assign(inwin=pit.groupby("pitcher").cumcount(ascending=False).to_numpy() < k)
    a = a.merge(pit[["pitcher", "game_pk", "inwin"]], on=["pitcher", "game_pk"], how="inner")
    agg = {"n": ("n", "sum")}
    for v in ("start_speed", "ivb", "hb"):
        agg[f"n_{v}"], agg[f"s_{v}"] = (f"n_{v}", "sum"), (f"s_{v}", "sum")
    g = a.groupby(["pitcher", "inwin", "grp"]).agg(**agg).reset_index()
    for v in ("start_speed", "ivb", "hb"):
        g[f"m_{v}"] = g[f"s_{v}"] / g[f"n_{v}"].where(g[f"n_{v}"] > 0)
    tot = g.groupby(["pitcher", "inwin"])["n"].transform("sum")
    g["share"] = g["n"] / tot
    g["tot"] = tot
    W, B = g[g["inwin"]], g[~g["inwin"]]
    btot = B.groupby("pitcher")["n"].sum()
    out = []
    for _, r in W.iterrows():
        pid = r["pitcher"]
        if btot.get(pid, 0) < NEW_PITCH_MIN_BASE_N:
            continue
        if r["share"] < NEW_PITCH_MIN_SHARE or r["n"] < NEW_PITCH_MIN_N:
            continue
        mine = B[B["pitcher"] == pid]
        own = mine[mine["grp"] == r["grp"]]
        share_b = float(own["n"].sum() / btot[pid]) if len(own) else 0.0
        if share_b > NEW_PITCH_MAX_BASE_SHARE:
            continue
        est = mine[(mine["grp"] != r["grp"]) & (mine["share"] > NEW_PITCH_MAX_BASE_SHARE)]
        if not np.isfinite(r["m_start_speed"]):
            continue
        distinct = True
        for _, q in est.iterrows():
            dv = abs(r["m_start_speed"] - q["m_start_speed"])
            di = abs(r["m_ivb"] - q["m_ivb"])
            dh = abs(r["m_hb"] - q["m_hb"])
            if not (dv >= NEW_PITCH_MPH or di >= NEW_PITCH_INCHES or dh >= NEW_PITCH_INCHES):
                distinct = False
                break
        if not distinct:
            continue
        out.append({"rule": "new_pitch", "pid": int(pid), "D": D, "group": r["grp"],
                    "share_w": float(r["share"]), "n_w": int(r["n"]), "share_b": share_b,
                    "n_b_tot": int(btot[pid]), "speed_w": float(r["m_start_speed"]),
                    "ivb_w": float(r["m_ivb"]), "hb_w": float(r["m_hb"])})
    return pd.DataFrame(out, columns=cols)


def available(appeared: np.ndarray, run: int = PT_ABSENCE_RUN) -> np.ndarray:
    """False on every club game inside a run of ``run`` or more straight club
    games without an appearance (the injured list, the minors or a leave; the
    page never says which); True elsewhere."""
    appeared = np.asarray(appeared, dtype=bool)
    ok = np.ones(len(appeared), dtype=bool)
    start = None
    for i, ap in enumerate(list(appeared) + [True]):
        if not ap and start is None:
            start = i
        elif ap and start is not None:
            if i - start >= run:
                ok[start:i] = False
            start = None
    return ok


def playing_time(frame, D) -> pd.DataFrame:
    """In the lineup: started 13 or more of his club's last 14 games after
    starting 40 percent or less of 30 or more available earlier games. Out of
    the lineup: started 3 or fewer of the last 14 while appearing in one or
    more of them, after starting 85 percent or more of 40 or more available
    earlier games. Available games are his current club's games from his first
    appearance for it, less every absence of 10 or more straight club games."""
    D = _day(D)
    cols = ["rule", "pid", "D", "club", "direction", "started_w", "appeared_w",
            "share_b", "available_b"]
    g = frame.games[frame.games["date"] <= D]
    b = frame.bat[(frame.bat["date"] <= D) & frame.bat["club"].notna()]
    if g.empty or b.empty:
        return pd.DataFrame(columns=cols)
    club_games = pd.concat([g[["game_pk", "game_seq", "home"]].rename(columns={"home": "club"}),
                            g[["game_pk", "game_seq", "away"]].rename(columns={"away": "club"})])
    club_games = club_games.dropna().sort_values(["club", "game_seq"], kind="mergesort")
    by_club = {c: grp["game_pk"].to_numpy() for c, grp in club_games.groupby("club")}
    b = b.sort_values(["batter", "game_seq"], kind="mergesort")
    out = []
    for pid, mine_all in b.groupby("batter"):
        club = mine_all["club"].iloc[-1]
        mine = mine_all[mine_all["club"] == club]
        cg = by_club.get(club)
        if cg is None:
            continue
        seq_first = int(mine["game_seq"].iloc[0])
        cgs = club_games[(club_games["club"] == club) & (club_games["game_seq"] >= seq_first)]
        cg = cgs["game_pk"].to_numpy()
        if len(cg) < PT_MIN_TENURE:
            continue
        app_set = set(mine["game_pk"])
        st_set = set(mine.loc[mine["started"].astype(bool), "game_pk"])
        appeared = np.fromiter((x in app_set for x in cg), dtype=bool, count=len(cg))
        started = np.fromiter((x in st_set for x in cg), dtype=bool, count=len(cg))
        avail = available(appeared)
        base = np.arange(len(cg)) < len(cg) - PT_WINDOW
        nb = int((base & avail).sum())
        sb = int((base & avail & started).sum())
        sw = int(started[~base].sum())
        aw = int(appeared[~base].sum())
        share = sb / nb if nb else float("nan")
        direction = None
        if nb >= PT_IN_MIN_AVAIL and share <= PT_IN_MAX_SHARE and sw >= PT_IN_STARTS:
            direction = "in"
        elif nb >= PT_OUT_MIN_AVAIL and share >= PT_OUT_MIN_SHARE and sw <= PT_OUT_STARTS \
                and aw >= 1:
            direction = "out"
        if direction:
            out.append({"rule": "playing_time", "pid": int(pid), "D": D, "club": club,
                        "direction": direction, "started_w": sw, "appeared_w": aw,
                        "share_b": share, "available_b": nb})
    return pd.DataFrame(out, columns=cols)


# --------------------------------------------------------------------------- #
# prior-season mode (plan 3.8)
# --------------------------------------------------------------------------- #
def _prior_values(frame, prior, D: str, fam: Family) -> tuple:
    """(window rows this season, baseline rows from all of last season) for
    players below the in-season baseline floor."""
    if fam.kind == "swing":
        cur = _swing_values(frame, D, fam)
        pD = str(prior.games["date"].max()) if len(prior.games) else D
        old = _swing_values(prior, pD, fam)
    elif fam.log_value:
        cur = _li_values(frame, D, fam)
        pD = str(prior.pit["date"].max())
        old = _li_values(prior, pD, fam)
    else:
        # the primary fastball from the previous season (the baseline)
        pD = str(prior.pit["date"].max())
        old = _fb_values_all(prior, pD, fam)
        prim = old.attrs.get("primary", {})
        cur = _fb_values_all(frame, D, fam, primary=prim)
    return cur, old


def _fb_values_all(frame, D: str, fam: Family, primary: Optional[dict] = None) -> pd.DataFrame:
    """Every qualifying game's primary-fastball value to D, the primary fastball
    the most-thrown of FF, SI and FC over all of the given games (or ``primary``)."""
    cols = ["pid", "game_pk", "game_seq", "date", "role", "value", "n", "wvar"]
    pit = frame.pit.loc[frame.pit["date"] <= D, ["pitcher", "game_pk", "game_seq", "date", "start"]]
    pit = pit.assign(role=pit["pitcher"].map(roles_as_of(frame, D)))
    role = fam.roles[0]
    apps = pit[(pit["role"] == "SP") & pit["start"]] if role == "SP" else pit[pit["role"] == "RP"]
    v = fam.value
    a = frame.arsenal
    a = a[(a["date"] <= D) & a["pitch_type"].isin(FB_TYPES)]
    a = (a.groupby(["pitcher", "game_pk", "pitch_type"], as_index=False)
         [["n", f"n_{v}", f"s_{v}", f"q_{v}"]].sum())
    a = a.merge(apps[["pitcher", "game_pk", "game_seq", "date", "role"]], on=["pitcher", "game_pk"])
    if primary is None:
        base = a.groupby(["pitcher", "pitch_type"], as_index=False)["n"].sum()
        base["tie"] = base["pitch_type"].map({t: i for i, t in enumerate(FB_TYPES)})
        pr = (base.sort_values(["pitcher", "n", "tie"], ascending=[True, False, True],
                               kind="mergesort").drop_duplicates("pitcher"))
        primary = dict(zip(pr["pitcher"].astype("int64"), pr["pitch_type"]))
    a = a[a["pitch_type"].to_numpy() == a["pitcher"].map(primary).to_numpy()]
    a = a[a[f"n_{v}"] >= max(fam.min_per_game, 1)].copy()
    n = a[f"n_{v}"].astype("float64")
    a["value"] = a[f"s_{v}"].astype("float64") / n
    a["wvar"] = np.nan
    a["n"] = n
    out = a.rename(columns={"pitcher": "pid"})[cols].reset_index(drop=True)
    out.attrs["primary"] = primary
    return out


def _stat_prior(cur: pd.DataFrame, old: pd.DataFrame, D: str, fam: Family, phi: float,
                sg_by_role: dict) -> pd.DataFrame:
    rows = []
    for role in fam.roles:
        u = cur[cur["role"] == role]
        if u.empty:
            continue
        last = u.groupby("pid")["date"].transform("max")
        u = u[last >= _minus(D, ACTIVE_DAYS - 1)].sort_values(["pid", "game_seq"], kind="mergesort")
        mode, size = fam.window[role]
        if mode == "count":
            inwin = u.groupby("pid").cumcount(ascending=False).to_numpy() < size
        else:
            inwin = (u["date"] >= _minus(D, size - 1)).to_numpy()
        u = u.assign(inwin=inwin)
        nwin = u[u["inwin"]].groupby("pid")["value"].agg(["mean", "size"])
        nbase = u[~u["inwin"]].groupby("pid").size().reindex(nwin.index).fillna(0)
        ok = nwin[((nwin["size"] == size) if mode == "count" else (nwin["size"] >= fam.min_window))
                  & (nbase < fam.min_baseline)]
        o = old[old["pid"].isin(ok.index)].groupby("pid")["value"].agg(["mean", "size"])
        o = o[o["size"] >= PRIOR_BASELINE_MIN]
        ok = ok.loc[ok.index.intersection(o.index)]
        sg = sg_by_role.get(role, float("nan"))
        if ok.empty or not np.isfinite(sg):
            continue
        t = pd.DataFrame({"nW": ok["size"], "nB": o["size"].reindex(ok.index),
                          "mean_w": ok["mean"], "mean_b": o["mean"].reindex(ok.index)})
        t["raw"] = t["mean_w"] - t["mean_b"]
        t["drift"] = float(t["raw"].mean()) if fam.drift else 0.0
        t["d"] = t["raw"] - t["drift"]
        t["se"] = sg * np.sqrt(1.0 / t["nW"] + 1.0 / t["nB"])
        t["z"] = t["d"] / t["se"]
        t["z_adj"] = t["z"] / phi
        wd = u[u["inwin"]].groupby("pid")["date"].agg(["min", "max"])
        t["w_first"], t["w_last"] = wd["min"].reindex(t.index), wd["max"].reindex(t.index)
        t["role"] = role
        rows.append(t.reset_index())
    if not rows:
        return _empty_tests(["mode"])
    out = pd.concat(rows, ignore_index=True)
    out["family"], out["D"], out["mode"] = fam.key, D, "prior_season"
    out["pid"] = out["pid"].astype("int64")
    return out[_TEST_COLS + ["mode"]].sort_values(["role", "pid"], kind="mergesort").reset_index(drop=True)


def _prior_check(fam: Family, swing_ok: bool) -> bool:
    if fam.key in PRIOR_EXCLUDED or fam.kind == "mix":
        raise ValueError(f"{fam.key} is excluded from prior-season mode (pitch labels move "
                         "between seasons)")
    return not (fam.kind == "swing" and not swing_ok)


def _prior_roles(frame, old: pd.DataFrame, fam: Family) -> dict:
    """sigma by role from the previous season's games (a completed season)."""
    return {r: _pooled_sd(old[old["role"] == r]) for r in fam.roles}


def detect_prior(frame, prior, D, family, *, phi: Optional[float] = None,
                 swing_ok: bool = False) -> pd.DataFrame:
    """Prior-season mode at D: players with a full window this season but fewer
    earlier games than the family's baseline floor, against all of their
    previous season (8 or more qualifying games), drift the league-wide window
    minus previous-season change by role, sigma from the previous season. The
    bar is PRIOR_SEASON_BAR. Swing families only with ``swing_ok`` (the build's
    2025-against-2024 calibration meeting the strict policy); mix raises."""
    fam, D = _fam(family), _day(D)
    if not _prior_check(fam, swing_ok):
        return _empty_tests(["mode"])
    cur, old = _prior_values(frame, prior, D, fam)
    return _stat_prior(cur, old, D, fam, _phi(fam, phi), _prior_roles(frame, old, fam))


def placebo_prior(frame, prior, D, family, R: int = PLACEBO_R, seed: int = PLACEBO_SEED, *,
                  phi: Optional[float] = None, swing_ok: bool = False) -> pd.DataFrame:
    """Prior-season mode's placebo: each tested player's window games and
    previous-season games pooled and re-split at random (the window keeps its
    size), R times."""
    fam, D = _fam(family), _day(D)
    if not _prior_check(fam, swing_ok):
        return _empty_tests(["mode", "rep"])
    real = detect_prior(frame, prior, D, fam, phi=phi, swing_ok=swing_ok)
    if real.empty:
        return _empty_tests(["mode", "rep"])
    cur, old = _prior_values(frame, prior, D, fam)
    sg = _prior_roles(frame, old, fam)
    out = []
    for role in fam.roles:
        rr = real[real["role"] == role].set_index("pid")
        if rr.empty:
            continue
        mode, size = fam.window[role]
        u = cur[(cur["role"] == role) & cur["pid"].isin(rr.index)].sort_values(
            ["pid", "game_seq"], kind="mergesort")
        if mode == "count":
            u = u[u.groupby("pid").cumcount(ascending=False).to_numpy() < size]
        else:
            u = u[(u["date"] >= _minus(D, size - 1)).to_numpy()]
        o = old[old["pid"].isin(rr.index)]
        pool = pd.concat([u[["pid", "game_pk", "value"]].assign(src=1),
                          o[["pid", "game_pk", "value"]].assign(src=0)], ignore_index=True)
        pool["game_pk"] = pool["game_pk"].astype("int64")
        nw = rr["nW"]
        for r in range(int(R)):
            key = _keys(seed, r, pool["pid"].to_numpy(), pool["game_pk"].to_numpy())
            p = pool.assign(key=key).sort_values(["pid", "key"], kind="mergesort")
            p = p.assign(rk=p.groupby("pid").cumcount().to_numpy())
            p = p.assign(inwin=p["rk"].to_numpy() < p["pid"].map(nw).to_numpy())
            m = p.groupby(["pid", "inwin"])["value"].agg(["mean", "size"]).unstack("inwin")
            t = pd.DataFrame({"nW": m["size"][True], "nB": m["size"][False],
                              "mean_w": m["mean"][True], "mean_b": m["mean"][False]}).dropna()
            t["raw"] = t["mean_w"] - t["mean_b"]
            t["drift"] = float(t["raw"].mean()) if fam.drift else 0.0
            t["d"] = t["raw"] - t["drift"]
            t["se"] = sg[role] * np.sqrt(1.0 / t["nW"] + 1.0 / t["nB"])
            t["z"] = t["d"] / t["se"]
            t["z_adj"] = t["z"] / _phi(fam, phi)
            t["role"], t["rep"] = role, r
            out.append(t.reset_index())
    if not out:
        return _empty_tests(["mode", "rep"])
    res = pd.concat(out, ignore_index=True)
    res["family"], res["D"], res["mode"] = fam.key, D, "prior_season"
    return res


__all__ = ["FAMILIES", "Family", "BARS", "BAR_POLICY", "BAR_GRID", "PRIOR_SEASON_BAR",
           "bar_for", "eval_dates", "detect", "placebo", "sigma", "game_values",
           "mix_values", "competitive_cut_as_of", "roles_as_of", "two_group_fit",
           "shrink_fit", "shrink_fit_mix", "mix_null", "shrink_apply", "flag", "episodes",
           "rotation_switch", "new_pitch", "playing_time", "available", "detect_prior",
           "placebo_prior"]

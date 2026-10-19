#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""league_trends_persistence - League Trends' one registered persistence read
(docs/LEAGUE_TRENDS_PERSISTENCE_GATE.md; LEAGUE_TRENDS_PLAN.md section 8; task
TR_P2_PERSISTENCE_LOOK).

THE QUESTION (gate section 1). Of the changes League Trends lists in a player's
own measured trait (a recent window against his earlier games of the same
season, at the family's frozen bar), what share is still at least half as
large 30 days later, against matched players with no listed change.

THE FAMILIES (gate section 2): attack_angle, bat_speed, mix, rp_ext, rp_hb and
rp_spin at the bars the registration froze. The velocity families and entry
Leverage Index are excluded; so are every club and league series and the
rotation, new-pitch and lineup rules. The look takes its families and bars
from REGISTERED below and checks them against the gate document's own table,
against trend_detect.BARS and against the eval artifact on the look's day,
printing any difference, before any outcome is read.

THE FRAME (gate section 3). Completed seasons 2021 to 2025 (swing families 2024
and 2025), the calibration's weekly Sundays from the third Sunday of May
through the last one at least 30 days before the season's last game. Flags
come from trend_detect at HEAD, as of each date D, with the season's shrink fit
and placebo SD taken from the calibration lab's memoised tables exactly as
tools/league_trends_calibrate.py takes them (earlier seasons only). A run of
consecutive weekly flags of one player in one family is one episode, dated at
its first flag.

HIT (gate section 4). Over the 30 days after the flag date, the same trait
(for mix, the plain pooled share of the pitch family the flag selected), net of
the league drift over those days (the mean change of every eligible player of
the same role from his flag-date baseline to those 30 days), differs from the
flag-date baseline in the flagged direction (the sign of d, the change net of
drift) by at least half the flagged raw change (|raw|, window minus baseline).
A player with no eligible game in those 30 days is no hit, on both sides, and
the count is printed per family.

CONTROL. 5 unflagged eligible players of the same family, role, date and
baseline game-SD tercile (terciles over the date's eligible players of that
role, and for mix of that pitch family), drawn without replacement with a seed
per flag, scored with the flag's threshold in the flag's direction against
their own flag-date baseline.

METRIC AND VERDICT (gate sections 4 and 5). The hit rate of the episodes
against the hit rate of their controls; the gap and its 95 percent interval
with players resampled whole, 2,000 reps; the one-sided p is the share of reps
whose gap is at or below zero. Holm across the registered families at 0.05
one-sided (a family with no episode enters at p = 1). PASS: the gap clears Holm
and the hit rate is 0.5 or more; FAIL: 40 or more episodes and not PASS;
INDETERMINATE: under 40 episodes.

WHAT IT NEVER DOES. It reads the trend frames and the calibration lab's memo
only (and refuses, before scoring, a memo whose signature does not match the
frame; it never re-measures). It opens no betting, odds, lineup, vintage,
weather or game-feed cache, imports no betting module, writes nothing under
data/ (the served artifact belongs to the flip the orchestrator queues on a
PASS, gate section 5's honesty guard) and relates no trait to a game result, a
price or a ledger row. The only later value it reads is the trait itself over
the 30 days after a flag, which is this registered read's whole purpose.

Run:
    python tools/league_trends_persistence.py --dry-run [--out PATH]
    python tools/league_trends_persistence.py --look --out docs/league-trends-<date>/persistence_eval.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import league_trends_calibrate as L  # noqa: E402
import trend_detect as TD  # noqa: E402
import trend_frames as TF  # noqa: E402

GATE_DOC = ROOT / "docs" / "LEAGUE_TRENDS_PERSISTENCE_GATE.md"
EVAL_PREVIEW = L.EVAL_PREVIEW
LAB_DIR = L.LAB_DIR
DATA_DIR = ROOT / "data"
SCHEMA = 1

# The registration (gate section 2), frozen. The look checks this table against
# the document before scoring and never takes a bar from a later artifact.
REGISTERED = {"attack_angle": 4.25, "bat_speed": 4.0, "mix": 6.0, "rp_ext": 5.0,
              "rp_hb": 4.25, "rp_spin": 5.0}
EXCLUDED = ("sp_velo", "rp_velo", "rp_entry_li")
EVAL_SHA256_REGISTERED = "3ab21b3195850503c979ce4d6368b2f5566899c510829d9c7a0173cf0d911b90"
SEASONS = {"pitch": (2021, 2022, 2023, 2024, 2025), "swing": (2024, 2025)}

OUTCOME_DAYS = 30
HALF = 0.5
CONTROLS_PER_FLAG = 5
REPS = 2000
EPISODE_FLOOR = 40
ALPHA = 0.05
HIT_RATE_MIN = 0.5
EPISODE_STEP_DAYS = 7
SEED = 20261015
TERCILES = 3

_FAM_INDEX = {k: i for i, k in enumerate(sorted(REGISTERED))}


def _nolog(*_a, **_k) -> None:
    return None


def _r(x, n: int = 6):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(x) else round(x, n)


def _clean(o):
    """JSON-safe: numpy scalars to Python, NaN and inf to None."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    return o


# --------------------------------------------------------------------------- #
# the registration
# --------------------------------------------------------------------------- #
def parse_registration(text: str) -> dict:
    """The registered families and bars from the gate document's section 2
    table ('Registered families') and the excluded keys from the table below
    it. {"families": {key: bar}, "excluded": [keys]}."""
    fams, excl = {}, []
    block = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("Registered families"):
            block = "reg"
            continue
        if s.startswith("Served families excluded"):
            block = "excl"
            continue
        if s.startswith("## "):
            block = None
            continue
        m = re.match(r"^\|\s*`([a-z_]+)`\s*\|(.*)$", s)
        if not m or block is None:
            continue
        key, rest = m.group(1), [c.strip() for c in m.group(2).split("|")]
        if block == "reg":
            fams[key] = float(rest[3])
        else:
            excl.append(key)
    return {"families": fams, "excluded": excl}


def sha256_of(path: Path) -> Optional[str]:
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def look_dates(season: int, covers_through: str) -> list:
    """The calibration's Sundays through the last one at least OUTCOME_DAYS
    before the season's last game, so every outcome window closes inside it."""
    last = (date.fromisoformat(str(covers_through)[:10]) - timedelta(days=OUTCOME_DAYS)).isoformat()
    return TD.eval_dates(int(season), last)


def family_seasons(fam: TD.Family) -> tuple:
    return SEASONS[L.calib_group(fam)]


# --------------------------------------------------------------------------- #
# the season's fit and phi, from the lab's tables (earlier seasons only)
# --------------------------------------------------------------------------- #
def season_fit(key: str, tables: dict, season: int) -> dict:
    """phi and the shrink fit for scoring ``season``, exactly as the lab's
    fits_and_counts takes them: the lab's fit seasons present in ``tables``,
    every one before the scored season (trend_detect raises otherwise)."""
    fam = TD.FAMILIES[key]
    fs = [x for x in L.lab_fit_seasons(fam, int(season)) if x in tables]
    if any(int(x) >= int(season) for x in fs):
        raise ValueError(f"{key}: a fit season of {season} is not before it: {fs}")
    real_by = {s: t[t["rep"] < 0] for s, t in tables.items()}
    pl_by = {s: t[t["rep"] >= 0] for s, t in tables.items()}
    phi = L._pooled_placebo_sd(tables, fs) if fs else None
    phi = float(phi) if phi else 1.0
    fit = None
    if fam.size_floor is not None and fs:
        if fam.kind == "mix":
            fit = TD.shrink_fit_mix(real_by, pl_by, int(season), fs)
        else:
            fit = TD.shrink_fit(real_by, int(season), fs, phi=phi)
    return {"phi": phi, "fit": fit, "fit_seasons": [int(x) for x in fs]}


def flags_at(frame, D: str, fam: TD.Family, bar: float, fit: Optional[dict],
             phi: float) -> pd.DataFrame:
    """Every eligible player's test at D with trend_detect.flag's columns."""
    tests = TD.detect(frame, D, fam, phi=phi)
    if tests.empty:
        return tests.assign(flag=pd.Series(dtype="bool"), size=np.nan, floor_ok=True)
    return TD.flag(tests, fam, float(bar), fit, phi=phi)


# --------------------------------------------------------------------------- #
# baselines and outcomes, labels as of D
# --------------------------------------------------------------------------- #
def primary_as_of(frame, D: str, fam: TD.Family) -> dict:
    """pitcher -> his primary fastball as of D: the most-thrown of FF, SI and
    FC over his baseline games (the appearances before his last k), as
    trend_detect's game values take it."""
    D = TD._day(D)
    pit = frame.pit.loc[frame.pit["date"] <= D, ["pitcher", "game_pk", "game_seq", "start"]]
    if pit.empty:
        return {}
    pit = pit.assign(role=pit["pitcher"].map(TD.roles_as_of(frame, D)))
    role = fam.roles[0]
    apps = pit[(pit["role"] == "SP") & pit["start"]] if role == "SP" else pit[pit["role"] == "RP"]
    k = fam.window[role][1]
    apps = apps.sort_values(["pitcher", "game_seq"], kind="mergesort")
    apps = apps.assign(rk=apps.groupby("pitcher").cumcount(ascending=False).to_numpy())
    a = frame.arsenal
    a = a[(a["date"] <= D) & a["pitch_type"].isin(TD.FB_TYPES)]
    a = a.groupby(["pitcher", "game_pk", "pitch_type"], as_index=False)["n"].sum()
    a = a.merge(apps[["pitcher", "game_pk", "rk"]], on=["pitcher", "game_pk"], how="inner")
    base = a[a["rk"] >= k].groupby(["pitcher", "pitch_type"], as_index=False)["n"].sum()
    base = base[base["n"] > 0]
    if base.empty:
        return {}
    base["tie"] = base["pitch_type"].map({t: i for i, t in enumerate(TD.FB_TYPES)})
    prim = (base.sort_values(["pitcher", "n", "tie"], ascending=[True, False, True], kind="mergesort")
            .drop_duplicates("pitcher"))
    return dict(zip(prim["pitcher"].astype("int64"), prim["pitch_type"]))


def _split_window(u: pd.DataFrame, D: str, fam: TD.Family, role: str) -> pd.DataFrame:
    """The detector's window split on a per-game table of one role."""
    u = u.sort_values(["pid", "game_seq"], kind="mergesort")
    mode, size = fam.window[role]
    if mode == "count":
        inwin = u.groupby("pid").cumcount(ascending=False).to_numpy() < size
    else:
        inwin = (u["date"] >= TD._minus(D, size - 1)).to_numpy()
    return u.assign(inwin=inwin)


_BASE_COLS = ["pid", "trait", "mean_b", "sd_b", "n_b"]
_OUT_COLS = ["pid", "trait", "out_mean", "n_out"]


def _mix_games(a: pd.DataFrame) -> pd.DataFrame:
    """Per (pitcher, game): the three family counts and the total over left-
    and right-handed batters, games of 12 or more such pitches."""
    fam = TD.FAMILIES["mix"]
    a = a[a["bat_side"].isin(["L", "R"])]
    if a.empty:
        return pd.DataFrame(columns=["pid", "game_pk", *TD.MIX_FAMS, "tot"])
    grp = a["pitch_type"].map(TD.MIX_FAMILY).fillna("OT")
    w = (a.assign(grp=grp).pivot_table(index=["pitcher", "game_pk"], columns="grp", values="n",
                                        aggfunc="sum", fill_value=0))
    for c in TD.MIX_FAMS:
        if c not in w.columns:
            w[c] = 0
    w["tot"] = w.sum(axis=1)
    w = w[list(TD.MIX_FAMS) + ["tot"]].reset_index().rename(columns={"pitcher": "pid"})
    return w[w["tot"] >= fam.min_per_game]


def baseline_stats(frame, D: str, fam: TD.Family) -> pd.DataFrame:
    """Per eligible-side player at D (and per pitch family for mix): the
    flag-date baseline mean, the baseline game-SD and the baseline game count,
    from the detector's own window split as of D."""
    D = TD._day(D)
    if fam.kind == "mix":
        w = TD.mix_values(frame, D)
        if w.empty:
            return pd.DataFrame(columns=_BASE_COLS)
        games = (w[["pid", "game_pk", "game_seq", "date", "role"]].drop_duplicates(["pid", "game_pk"])
                 .sort_values(["pid", "game_seq"], kind="mergesort"))
        k = np.where(games["role"] == "SP", fam.window["SP"][1], fam.window["RP"][1])
        games = games.assign(inwin=games.groupby("pid").cumcount(ascending=False).to_numpy() < k)
        g = w.groupby(["pid", "game_pk"])[list(TD.MIX_FAMS) + ["tot"]].sum().reset_index()
        g = g.merge(games[["pid", "game_pk", "inwin"]], on=["pid", "game_pk"])
        b = g[~g["inwin"]]
        rows = []
        for c in TD.MIX_FAMS:
            share = b[c] / b["tot"]
            agg = pd.DataFrame({"pid": b["pid"], "c": b[c], "tot": b["tot"], "share": share})
            s = agg.groupby("pid").agg(cs=("c", "sum"), ts=("tot", "sum"), sd_b=("share", "std"),
                                       n_b=("share", "size")).reset_index()
            s["mean_b"] = s["cs"] / s["ts"].where(s["ts"] > 0)
            s["trait"] = c
            rows.append(s[_BASE_COLS])
        return pd.concat(rows, ignore_index=True)
    vt = TD.game_values(frame, D, fam)
    if vt.empty:
        return pd.DataFrame(columns=_BASE_COLS)
    rows = []
    for role in fam.roles:
        u = vt[vt["role"] == role]
        if u.empty:
            continue
        u = _split_window(u, D, fam, role)
        b = u[~u["inwin"]]
        s = b.groupby("pid")["value"].agg(mean_b="mean", sd_b="std", n_b="size").reset_index()
        s["trait"] = fam.key
        rows.append(s[_BASE_COLS])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=_BASE_COLS)


def outcome_stats(frame, D: str, fam: TD.Family) -> pd.DataFrame:
    """Per player with an eligible game in the OUTCOME_DAYS after D (and per
    pitch family for mix): the trait over those games and the game count. The
    primary fastball, the role and the competitive-swing cut are as of D."""
    D = TD._day(D)
    D_end = (date.fromisoformat(D) + timedelta(days=OUTCOME_DAYS)).isoformat()
    if fam.kind == "mix":
        a = frame.arsenal
        a = a[(a["date"] > D) & (a["date"] <= D_end)]
        g = _mix_games(a)
        if g.empty:
            return pd.DataFrame(columns=_OUT_COLS)
        rows = []
        for c in TD.MIX_FAMS:
            s = g.groupby("pid").agg(cs=(c, "sum"), ts=("tot", "sum"), n_out=("tot", "size")).reset_index()
            s["out_mean"] = s["cs"] / s["ts"].where(s["ts"] > 0)
            s["trait"] = c
            rows.append(s[_OUT_COLS])
        return pd.concat(rows, ignore_index=True)
    if fam.kind == "swing":
        s = frame.swings
        s = s[(s["date"] > D) & (s["date"] <= D_end)]
        if s.empty:
            return pd.DataFrame(columns=_OUT_COLS)
        cut = TD.competitive_cut_as_of(frame, D)
        s = s[s["batter"].isin(cut.index)]
        if s.empty:
            return pd.DataFrame(columns=_OUT_COLS)
        floor = np.maximum(s["batter"].map(cut).to_numpy(dtype="float64"), TF.COMPETITIVE_MIN_MPH)
        s = s[(s["bat_speed"].to_numpy() >= floor) & s[fam.value].notna().to_numpy()]
        g = s.groupby(["batter", "game_pk"])[fam.value].agg(["mean", "count"]).reset_index()
        g = g[g["count"] >= fam.min_per_game]
        o = g.groupby("batter")["mean"].agg(out_mean="mean", n_out="size").reset_index()
        o = o.rename(columns={"batter": "pid"})
        o["pid"] = o["pid"].astype("int64")
        o["trait"] = fam.key
        return o[_OUT_COLS]
    if fam.kind != "game_mean" or fam.log_value:
        raise ValueError(f"{fam.key} is not a registered family kind")
    prim = primary_as_of(frame, D, fam)
    role = fam.roles[0]
    pit = frame.pit.loc[(frame.pit["date"] > D) & (frame.pit["date"] <= D_end),
                        ["pitcher", "game_pk", "start"]]
    if role == "SP":
        pit = pit[pit["start"].astype(bool)]
    a = frame.arsenal
    a = a[(a["date"] > D) & (a["date"] <= D_end) & a["pitch_type"].isin(TD.FB_TYPES)]
    if a.empty or pit.empty or not prim:
        return pd.DataFrame(columns=_OUT_COLS)
    v = fam.value
    a = a.groupby(["pitcher", "game_pk", "pitch_type"], as_index=False)[["n", f"n_{v}", f"s_{v}"]].sum()
    a = a[a["pitch_type"].to_numpy() == a["pitcher"].map(prim).fillna("").to_numpy()]
    a = a.merge(pit[["pitcher", "game_pk"]].drop_duplicates(), on=["pitcher", "game_pk"], how="inner")
    n = a[f"n_{v}"].astype("float64")
    a = a[n >= max(fam.min_per_game, 1)].copy()
    if a.empty:
        return pd.DataFrame(columns=_OUT_COLS)
    a["value"] = a[f"s_{v}"].astype("float64") / a[f"n_{v}"].astype("float64")
    o = a.groupby("pitcher")["value"].agg(out_mean="mean", n_out="size").reset_index()
    o = o.rename(columns={"pitcher": "pid"})
    o["pid"] = o["pid"].astype("int64")
    o["trait"] = fam.key
    return o[_OUT_COLS]


# --------------------------------------------------------------------------- #
# scoring one date
# --------------------------------------------------------------------------- #
def _rng_for(key: str, pid: int, D: str) -> np.random.Generator:
    return np.random.default_rng([SEED, _FAM_INDEX.get(key, 99), int(pid),
                                  int(str(D)[:10].replace("-", ""))])


def _tercile(sd: pd.Series) -> pd.Series:
    """0, 1 or 2 by the terciles of the finite values; NaN where sd is not."""
    v = sd.to_numpy(dtype="float64")
    ok = np.isfinite(v)
    out = np.full(len(v), np.nan)
    if ok.sum() == 0:
        return pd.Series(out, index=sd.index)
    q = np.quantile(v[ok], [1.0 / TERCILES, 2.0 / TERCILES])
    out[ok] = np.searchsorted(q, v[ok], side="right")
    return pd.Series(out, index=sd.index)


def eligible_table(frame, D: str, fam: TD.Family, fl: pd.DataFrame) -> pd.DataFrame:
    """The date's eligible players (one row per player, or per player and
    pitch family for mix) with flag, baseline, outcome, drift and tercile."""
    el = fl[["pid", "role", "flag"]].drop_duplicates("pid").copy()
    el["pid"] = el["pid"].astype("int64")
    if fam.kind == "mix":
        el = el.merge(pd.DataFrame({"trait": list(TD.MIX_FAMS)}), how="cross")
    else:
        el["trait"] = fam.key
    base = baseline_stats(frame, D, fam)
    out = outcome_stats(frame, D, fam)
    for t in (base, out):
        if len(t):
            t["pid"] = t["pid"].astype("int64")
    tab = el.merge(base, on=["pid", "trait"], how="left").merge(out, on=["pid", "trait"], how="left")
    tab["n_out"] = tab["n_out"].fillna(0).astype("int64")
    tab["change"] = tab["out_mean"] - tab["mean_b"]
    has = tab["n_out"] > 0
    drift = tab[has].groupby(["role", "trait"])["change"].mean().rename("drift")
    tab = tab.merge(drift.reset_index(), on=["role", "trait"], how="left")
    tab["change_net"] = tab["change"] - tab["drift"]
    tab["tercile"] = tab.groupby(["role", "trait"])["sd_b"].transform(_tercile)
    return tab


def _hit(row, direction: float, mag: float) -> bool:
    if int(row["n_out"]) <= 0:
        return False
    cn = row["change_net"]
    return bool(np.isfinite(cn) and direction * cn >= mag)


def score_date(frame, D: str, fam: TD.Family, fl: pd.DataFrame, first_pids,
               log: Callable = _nolog) -> list:
    """Episode records for the flags at D whose episode starts at D, each
    with its matched controls. Pure given the frame and the flag table."""
    D = TD._day(D)
    first = set(int(p) for p in first_pids)
    if not first:
        return []
    tab = eligible_table(frame, D, fam, fl)
    flagged_pids = set(fl.loc[fl["flag"].astype(bool), "pid"].astype("int64"))
    idx = tab.set_index(["pid", "trait"])
    out = []
    for _, f in fl[fl["flag"].astype(bool)].iterrows():
        pid = int(f["pid"])
        if pid not in first:
            continue
        trait = str(f["fam_sel"]) if fam.kind == "mix" else fam.key
        d = float(f["d"])
        direction = 1.0 if d >= 0 else -1.0
        mag = HALF * abs(float(f["raw"]))
        try:
            me = idx.loc[(pid, trait)]
        except KeyError:
            me = None
        rec = {"pid": pid, "D": D, "role": str(f["role"]), "trait": trait,
               "direction": "up" if direction > 0 else "down",
               "raw": _r(f["raw"]), "d": _r(d), "size": _r(f.get("size")),
               "z_adj": _r(f["z_adj"]), "nW": int(f["nW"]), "nB": int(f["nB"]),
               "mean_w": _r(f["mean_w"]), "mean_b_test": _r(f["mean_b"]),
               "threshold": _r(mag)}
        if me is None:
            rec.update({"mean_b": None, "sd_b": None, "out_mean": None, "n_out": 0, "drift": None,
                        "change_net": None, "hit": False, "tercile": None, "candidates": 0,
                        "controls": []})
            out.append(rec)
            continue
        hit = _hit(me, direction, mag)
        terc = me["tercile"]
        rec.update({"mean_b": _r(me["mean_b"]), "sd_b": _r(me["sd_b"]), "out_mean": _r(me["out_mean"]),
                    "n_out": int(me["n_out"]), "drift": _r(me["drift"]),
                    "change_net": _r(me["change_net"]), "hit": bool(hit),
                    "tercile": None if not np.isfinite(terc) else int(terc)})
        cand = tab[(tab["role"] == rec["role"]) & (tab["trait"] == trait)
                   & (~tab["flag"].astype(bool)) & (~tab["pid"].isin(flagged_pids))
                   & (tab["pid"] != pid)]
        if np.isfinite(terc):
            cand = cand[cand["tercile"] == terc]
        else:
            cand = cand.iloc[0:0]
        cand = cand.sort_values("pid", kind="mergesort").reset_index(drop=True)
        rec["candidates"] = int(len(cand))
        rng = _rng_for(fam.key, pid, D)
        take = min(CONTROLS_PER_FLAG, len(cand))
        pick = np.sort(rng.choice(len(cand), size=take, replace=False)) if take else np.array([], dtype=int)
        ctrls = []
        for i in pick:
            c = cand.iloc[int(i)]
            ctrls.append({"pid": int(c["pid"]), "mean_b": _r(c["mean_b"]), "sd_b": _r(c["sd_b"]),
                          "out_mean": _r(c["out_mean"]), "n_out": int(c["n_out"]),
                          "change_net": _r(c["change_net"]), "hit": _hit(c, direction, mag)})
        rec["controls"] = ctrls
        out.append(rec)
    log(f"    {fam.key} {D}: {len(out)} episode(s) scored, "
        f"{sum(r['hit'] for r in out)} hit, {sum(len(r['controls']) for r in out)} controls")
    return out


# --------------------------------------------------------------------------- #
# the metric and the verdict
# --------------------------------------------------------------------------- #
def family_rates(records: list) -> dict:
    """Counts and rates of one family from its episode records."""
    n_ep = len(records)
    hits = int(sum(bool(r["hit"]) for r in records))
    n_ctrl = int(sum(len(r["controls"]) for r in records))
    c_hits = int(sum(bool(c["hit"]) for r in records for c in r["controls"]))
    no_game = int(sum(int(r["n_out"]) <= 0 for r in records))
    c_no_game = int(sum(int(c["n_out"]) <= 0 for r in records for c in r["controls"]))
    short = int(sum(len(r["controls"]) < CONTROLS_PER_FLAG for r in records))
    hr = hits / n_ep if n_ep else None
    cr = c_hits / n_ctrl if n_ctrl else None
    return {"episodes": n_ep, "players": len({r["pid"] for r in records}), "hits": hits,
            "hit_rate": _r(hr), "flags_no_game": no_game, "controls": n_ctrl,
            "control_hits": c_hits, "control_rate": _r(cr), "controls_no_game": c_no_game,
            "episodes_short_of_controls": short,
            "gap": _r(hr - cr) if hr is not None and cr is not None else None}


def bootstrap_gap(records: list, key: str, reps: int = REPS) -> dict:
    """The gap's 95 percent interval and one-sided p with players resampled
    whole: each replicate draws the flagged players with replacement and
    carries every episode and control of a drawn player."""
    if not records:
        return {"reps": 0, "ci95": [None, None], "p_one_sided": None, "finite_reps": 0}
    pids = sorted({r["pid"] for r in records})
    pos = {p: i for i, p in enumerate(pids)}
    P = len(pids)
    n_ep = np.zeros(P)
    hits = np.zeros(P)
    n_c = np.zeros(P)
    c_hits = np.zeros(P)
    for r in records:
        i = pos[r["pid"]]
        n_ep[i] += 1
        hits[i] += bool(r["hit"])
        n_c[i] += len(r["controls"])
        c_hits[i] += sum(bool(c["hit"]) for c in r["controls"])
    rng = np.random.default_rng([SEED, _FAM_INDEX.get(key, 99), 7])
    draws = rng.integers(0, P, size=(int(reps), P))
    W = np.zeros((int(reps), P))
    for j in range(P):
        W[:, j] = (draws == j).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        hr = (W @ hits) / (W @ n_ep)
        cr = (W @ c_hits) / (W @ n_c)
        gap = hr - cr
    ok = np.isfinite(gap)
    g = gap[ok]
    if len(g) == 0:
        return {"reps": int(reps), "ci95": [None, None], "p_one_sided": None, "finite_reps": 0}
    lo, hi = np.percentile(g, [2.5, 97.5])
    return {"reps": int(reps), "ci95": [_r(lo), _r(hi)], "p_one_sided": _r(float(np.mean(g <= 0.0))),
            "finite_reps": int(len(g))}


def holm(pvalues: dict, alpha: float = ALPHA) -> dict:
    """Holm's step-down at ``alpha`` one-sided over every key given (a None
    p counts as 1). {key: {rank, p, threshold, pass}} plus m and alpha."""
    items = sorted(((1.0 if p is None else float(p)), k) for k, p in pvalues.items())
    m = len(items)
    out, failed = {}, False
    for i, (p, k) in enumerate(items):
        thr = alpha / (m - i)
        ok = (not failed) and p <= thr
        if not ok:
            failed = True
        out[k] = {"rank": i + 1, "p": None if pvalues[k] is None else _r(p), "threshold": _r(thr, 8),
                  "pass": bool(ok)}
    return {"alpha": alpha, "m": m, "families": out}


def verdict_for(rates: dict, hm: dict) -> str:
    if rates["episodes"] < EPISODE_FLOOR:
        return "INDETERMINATE"
    if hm["pass"] and rates["hit_rate"] is not None and rates["hit_rate"] >= HIT_RATE_MIN:
        return "PASS"
    return "FAIL"


def line_for(rates: dict) -> str:
    p = int(round(100.0 * rates["hit_rate"]))
    q = int(round(100.0 * rates["control_rate"])) if rates["control_rate"] is not None else None
    return (f"Of the changes like this listed in 2021 to 2025, {p} percent were still at least "
            f"half as large 30 days later (players with no listed change: {q} percent)")


# --------------------------------------------------------------------------- #
# the look
# --------------------------------------------------------------------------- #
def score_family(key: str, bar: float, frames: dict, tables: dict, dates_by: dict,
                 log: Callable = _nolog) -> dict:
    """One family over its seasons: the flags at every date, the episodes,
    their scoring with controls, and the per-season fit records."""
    fam = TD.FAMILIES[key]
    seasons = [s for s in family_seasons(fam) if s in frames]
    fits, flag_rows, records = {}, [], []
    flags_total = 0
    for s in seasons:
        sf = season_fit(key, tables, s)
        fits[s] = {"phi": _r(sf["phi"], 6), "fit_seasons": sf["fit_seasons"],
                   "fit": L._fit_record(sf["fit"])}
        frame = frames[s]
        fl_by = {}
        for D in dates_by[s]:
            fl = flags_at(frame, D, fam, bar, sf["fit"], sf["phi"])
            fl_by[D] = fl
            n = int(fl["flag"].astype(bool).sum()) if len(fl) else 0
            flags_total += n
            if n:
                f = fl[fl["flag"].astype(bool)][["family", "pid", "D"]].copy()
                f["season"] = s
                flag_rows.append(f)
        if not flag_rows:
            continue
        flags = pd.concat(flag_rows, ignore_index=True)
        flags = flags[flags["season"] == s]
        if flags.empty:
            continue
        ep = TD.episodes(flags[["family", "pid", "D"]], step_days=EPISODE_STEP_DAYS)
        for D, grp in ep.groupby("first"):
            recs = score_date(frame, D, fam, fl_by[D], grp["pid"].tolist(), log=log)
            for r in recs:
                r["season"] = int(s)
                run = grp[grp["pid"] == r["pid"]].iloc[0]
                r["episode_dates"] = int(run["dates"])
                r["episode_last"] = str(run["last"])
            records.extend(recs)
    records.sort(key=lambda r: (r["season"], r["D"], r["pid"]))
    rates = family_rates(records)
    boot = bootstrap_gap(records, key)
    by_season = {}
    for s in seasons:
        rs = [r for r in records if r["season"] == s]
        by_season[str(s)] = {"dates": len(dates_by[s]), "episodes": len(rs),
                             "hits": int(sum(r["hit"] for r in rs)),
                             "controls": int(sum(len(r["controls"]) for r in rs)),
                             "control_hits": int(sum(c["hit"] for r in rs for c in r["controls"]))}
    return {"label": fam.label, "unit": fam.unit, "kind": fam.kind, "group": L.calib_group(fam),
            "bar": float(bar), "size_floor": _r(fam.size_floor), "seasons": seasons,
            "fits": {str(s): v for s, v in fits.items()}, "flag_player_dates": int(flags_total),
            **rates, "bootstrap": boot, "by_season": by_season, "episode_records": records}


def run_look(frames: dict, tables_by_key: dict, dates_by: dict, registered: dict, *,
             mode: str, checks: dict, log: Callable = _nolog) -> dict:
    """Score every registered family and assemble the artifact. ``frames``:
    season -> TrendFrame; ``tables_by_key``: key -> {season: lab table};
    ``dates_by``: season -> look dates."""
    t0 = time.time()
    fams = {}
    for key in sorted(registered):
        t1 = time.time()
        log(f"  {key} at {registered[key]:g}")
        fams[key] = score_family(key, registered[key], frames, tables_by_key[key], dates_by, log=log)
        log(f"  {key}: {fams[key]['episodes']} episodes, hit rate {fams[key]['hit_rate']}, "
            f"control rate {fams[key]['control_rate']}, gap {fams[key]['gap']}, "
            f"p {fams[key]['bootstrap']['p_one_sided']} ({time.time() - t1:.0f} s)")
    hm = holm({k: v["bootstrap"]["p_one_sided"] if v["episodes"] else None for k, v in fams.items()})
    verdicts, lines = {}, {}
    for k, v in fams.items():
        v["holm"] = hm["families"][k]
        v["verdict"] = verdict_for(v, v["holm"])
        verdicts[k] = v["verdict"]
        if v["verdict"] == "PASS":
            lines[k] = line_for(v)
    art = {
        "schema": SCHEMA,
        "generated_at": None,
        "mode": mode,
        "what": ("League Trends' registered persistence read: per family at its frozen bar, the "
                 "share of listed changes (episodes) whose trait, net of league drift, is still at "
                 "least half as large over the 30 days after the flag, against 5 matched unflagged "
                 "players per flag; the gap with players resampled whole and Holm across families."),
        "verdict": verdicts,
        "lines": lines,
        "registration": checks,
        "design": {
            "outcome_days": OUTCOME_DAYS, "half": HALF, "controls_per_flag": CONTROLS_PER_FLAG,
            "reps": REPS, "episode_floor": EPISODE_FLOOR, "alpha": ALPHA, "one_sided": True,
            "hit_rate_min": HIT_RATE_MIN, "episode_step_days": EPISODE_STEP_DAYS, "seed": SEED,
            "dates": "the calibration's Sundays from the third Sunday of May through the last one "
                     "at least 30 days before the season's last game",
            "flag": "trend_detect at HEAD as of D at the frozen bar and the family's floor, the "
                    "season's shrink fit and placebo SD from the lab's earlier-season tables",
            "hit": "the trait over the 30 days after the flag date, net of the league drift of "
                   "every eligible player of the same role over those days, differs from the "
                   "flag-date baseline in the flagged direction (sign of d) by at least half the "
                   "flagged raw change (|raw|); no eligible game in those days is no hit",
            "mix_trait": "the plain pooled share of the pitch family the flag selected, against the "
                         "baseline's pooled share",
            "control": "5 unflagged eligible players of the same family, role, date and baseline "
                       "game-SD tercile, drawn without replacement with a seed per flag, scored "
                       "with the flag's threshold in the flag's direction against their own "
                       "flag-date baseline",
            "metric": "hit rate of the episodes against the hit rate of their controls; the gap's "
                      "95 percent interval with players resampled whole; one-sided p the share of "
                      "replicates with a gap at or below zero",
            "verdict": "Holm across the registered families at 0.05 one-sided (a family with no "
                       "episode at p = 1); PASS when the gap clears Holm and the hit rate is 0.5 "
                       "or more; FAIL at 40 or more episodes otherwise; INDETERMINATE under 40",
        },
        "frame": {str(s): {"covers_through": str(fr.meta.get("covers_through")),
                           "games": int(fr.meta.get("games") or 0),
                           "content_key": checks.get("frames", {}).get(str(s), {}).get("content_key"),
                           "dates": list(dates_by[s])}
                  for s, fr in sorted(frames.items())},
        "holm": {"alpha": hm["alpha"], "m": hm["m"]},
        "families": fams,
        "wall_seconds": _r(time.time() - t0, 1),
    }
    return _clean(art)


def write_artifact(art: dict, path: Path) -> None:
    path = Path(path)
    try:
        if path.resolve().is_relative_to(DATA_DIR.resolve()):
            raise ValueError(f"refused: {path} is under data/ (the served artifact belongs to the flip)")
    except AttributeError:
        if str(path.resolve()).startswith(str(DATA_DIR.resolve())):
            raise ValueError(f"refused: {path} is under data/ (the served artifact belongs to the flip)")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(_clean(art), indent=1, sort_keys=True, allow_nan=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# the checks before scoring (the look has not run if any fails)
# --------------------------------------------------------------------------- #
def lab_signature(season: int, frame, R_: int = L.R, seed: int = L.SEED) -> dict:
    return {"lab_version": L.LAB_VERSION, "content_key": L.frame_content_key(frame), "R": int(R_),
            "seed": int(seed), "dates": TD.eval_dates(int(season), str(frame.meta.get("covers_through")))}


def pre_checks(frames: dict, *, gate_doc: Path = GATE_DOC, eval_path: Path = EVAL_PREVIEW,
               lab_dir: Path = LAB_DIR, log: Callable = _nolog) -> tuple:
    """(checks record, problems). Families and bars against the gate document,
    trend_detect and the eval artifact; the lab memo signatures against the
    frames; every registered family's seasons present and complete."""
    problems = []
    reg = parse_registration(Path(gate_doc).read_text(encoding="utf-8"))
    if reg["families"] != REGISTERED:
        problems.append(f"the gate document's table {reg['families']} differs from REGISTERED {REGISTERED}")
    if sorted(reg["excluded"]) != sorted(EXCLUDED):
        problems.append(f"the gate document excludes {reg['excluded']}, the module {list(EXCLUDED)}")
    td_diff = {k: (TD.BARS["strict"].get(k), b) for k, b in REGISTERED.items()
               if TD.BARS["strict"].get(k) != b}
    if td_diff:
        log(f"  trend_detect.BARS['strict'] differs from the registration: {td_diff}")
    sha_now = sha256_of(eval_path)
    art_bars, art_gen = None, None
    if sha_now is not None:
        try:
            a = json.loads(Path(eval_path).read_text(encoding="utf-8"))
            art_bars = {k: a.get("bars", {}).get("strict", {}).get(k) for k in REGISTERED}
            art_gen = a.get("generated_at")
        except (OSError, ValueError):
            pass
    art_diff = {k: (art_bars.get(k), b) for k, b in REGISTERED.items()
                if art_bars is not None and art_bars.get(k) != b}
    if art_diff:
        log(f"  the eval artifact on the look's day differs from the registration: {art_diff}")
    fr_rec, sigs = {}, {}
    for s, fr in sorted(frames.items()):
        sig = lab_signature(s, fr)
        sigs[s] = sig
        ct = str(fr.meta.get("covers_through") or "")
        fr_rec[str(s)] = {"content_key": sig["content_key"], "covers_through": ct,
                          "games": int(fr.meta.get("games") or 0)}
        if ct < f"{s}-{L.SEASON_END_MIN}":
            problems.append(f"{s}: the frame covers through {ct or 'nothing'}")
    lab_rec = {}
    for key in sorted(REGISTERED):
        fam = TD.FAMILIES[key]
        need = sorted(set(family_seasons(fam)) | {x for s in family_seasons(fam)
                                                  for x in L.lab_fit_seasons(fam, s)})
        for s in need:
            if s not in frames:
                problems.append(f"{key}: no frame for {s}")
                continue
            mp = Path(lab_dir) / str(s) / f"{key}.json"
            pq = Path(lab_dir) / str(s) / f"{key}.parquet"
            if not (mp.exists() and pq.exists()):
                problems.append(f"{key} {s}: no lab memo")
                continue
            try:
                have = json.loads(mp.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                have = None
            if have != sigs[s]:
                problems.append(f"{key} {s}: the lab memo's signature does not match the frame")
            lab_rec[f"{key}:{s}"] = {"content_key": (have or {}).get("content_key"), "ok": have == sigs[s]}
    checks = {
        "document": "docs/LEAGUE_TRENDS_PERSISTENCE_GATE.md",
        "families": dict(REGISTERED), "excluded": list(EXCLUDED),
        "document_table": reg,
        "trend_detect_bars": {k: TD.BARS["strict"].get(k) for k in sorted(REGISTERED)},
        "trend_detect_differs": td_diff,
        "eval_artifact": {"path": str(Path(eval_path).relative_to(ROOT)) if str(eval_path).startswith(str(ROOT)) else str(eval_path),
                          "registered_sha256": EVAL_SHA256_REGISTERED,
                          "sha256_on_look_day": sha_now, "equal": sha_now == EVAL_SHA256_REGISTERED,
                          "generated_at": art_gen, "bars_on_look_day": art_bars,
                          "bars_differ": art_diff},
        "frames": fr_rec, "lab_memo": lab_rec,
    }
    return checks, problems


def load_inputs(seasons=None, *, log: Callable = _nolog) -> dict:
    """season -> TrendFrame for every season a registered family needs (its
    own seasons and the lab's fit seasons), from the frames' memo."""
    need = set()
    for key in REGISTERED:
        fam = TD.FAMILIES[key]
        need |= set(family_seasons(fam))
        for s in family_seasons(fam):
            need |= set(L.lab_fit_seasons(fam, s))
    seasons = sorted(need if seasons is None else set(seasons))
    frames = {}
    for s in seasons:
        frames[s] = TF.pitch_game_frame(s, log=log)
    return frames


def load_tables(frames: dict, lab_dir: Path = LAB_DIR) -> dict:
    out = {}
    for key in sorted(REGISTERED):
        fam = TD.FAMILIES[key]
        need = sorted(set(family_seasons(fam)) | {x for s in family_seasons(fam)
                                                  for x in L.lab_fit_seasons(fam, s)})
        out[key] = {s: pd.read_parquet(Path(lab_dir) / str(s) / f"{key}.parquet")
                    for s in need if s in frames}
    return out


def look(out: Path, *, log: Callable = print) -> int:
    """The one look. Exit 0 on a written artifact, 3 when a check before
    scoring fails (nothing scored), 4 on an exception after scoring began."""
    t0 = time.time()
    log(f"league_trends_persistence look, {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    out = Path(out)
    try:
        if out.resolve().is_relative_to(DATA_DIR.resolve()):
            log(f"refused: --out {out} is under data/; nothing scored")
            return 3
    except AttributeError:
        pass
    frames = load_inputs(log=log)
    checks, problems = pre_checks(frames, log=log)
    log(f"  eval artifact sha256 on the look's day {checks['eval_artifact']['sha256_on_look_day']} "
        f"(registered {EVAL_SHA256_REGISTERED}; equal {checks['eval_artifact']['equal']})")
    log(f"  document table {checks['document_table']['families']}; trend_detect "
        f"{checks['trend_detect_bars']}")
    if problems:
        for p in problems:
            log(f"  CHECK FAILED: {p}")
        log("the look has not run: a check before scoring failed; nothing was read or written")
        return 3
    tables = load_tables(frames)
    dates_by = {s: look_dates(s, fr.meta.get("covers_through")) for s, fr in frames.items()}
    for s in sorted(dates_by):
        log(f"  {s}: {len(dates_by[s])} dates {dates_by[s][0]} to {dates_by[s][-1]} "
            f"(covers through {frames[s].meta.get('covers_through')})")
    log("SCORING BEGINS")
    try:
        art = run_look(frames, tables, dates_by, REGISTERED, mode="look", checks=checks, log=log)
        art["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        art["wall_seconds"] = _r(time.time() - t0, 1)
        write_artifact(art, out)
    except Exception:  # noqa: BLE001 - the crash protocol records any exception
        log("EXCEPTION AFTER SCORING BEGAN (the look is INDETERMINATE; not rerun)")
        log(traceback.format_exc())
        return 4
    log(f"wrote {out} in {time.time() - t0:.0f} s")
    log(json.dumps({"verdict": art["verdict"], "lines": art["lines"],
                    **{k: {"episodes": v["episodes"], "hit_rate": v["hit_rate"],
                           "control_rate": v["control_rate"], "gap": v["gap"],
                           "ci95": v["bootstrap"]["ci95"], "p": v["bootstrap"]["p_one_sided"],
                           "holm": v["holm"]} for k, v in art["families"].items()}}, indent=1))
    return 0


# --------------------------------------------------------------------------- #
# the dry run: the whole reporting path on fixtures with nulls
# --------------------------------------------------------------------------- #
class _Fixture:
    """A small synthetic trend frame with the producer's column names."""

    def __init__(self, season: int):
        self.season = int(season)
        self.pit, self.ars, self.sw, self.games = [], [], [], {}
        self.prior_cut = {}

    def dt(self, d: int) -> str:
        return (date(self.season, 3, 27) + timedelta(days=int(d))).isoformat()

    def _key(self, d: int, slot: int) -> int:
        return self.season * 10 ** 7 + d * 10 ** 4 + slot

    def appear(self, pid: int, d: int, *, hb=-8.0, spin=2300.0, ext=6.5, n_fb=10,
               mix=None, nan_physics=False, li=1.0):
        pk = self._key(d, pid)
        self.games.setdefault(pk, (pk, d))
        self.pit.append({"season": self.season, "game_pk": pk, "game_seq": pk,
                         "start_time": self.dt(d) + "T23:05:00Z", "date": self.dt(d),
                         "pitcher": pid, "club": None, "start": False, "li": li, "bf": 5,
                         "so": 1, "bb": 0, "hbp": 0, "outs": 3, "np": n_fb, "swings": 5,
                         "whiffs": 1, "ooz": 3, "chases": 1})
        mix = mix or {"FF": (n_fb, n_fb)}
        for ptype, (nl, nr) in mix.items():
            for side, n in (("L", nl), ("R", nr)):
                if n <= 0:
                    continue
                row = {"season": self.season, "game_pk": pk, "game_seq": pk, "date": self.dt(d),
                       "pitcher": pid, "pitch_type": ptype, "bat_side": side, "n": int(n)}
                vals = {"start_speed": 95.0, "ivb": 16.0, "hb": hb, "spin": spin, "ext": ext}
                for v, m in vals.items():
                    tracked = 0 if nan_physics else int(n)
                    row[f"n_{v}"] = tracked
                    row[f"s_{v}"] = float(tracked * m)
                    row[f"q_{v}"] = float(tracked * m * m + max(tracked - 1, 0) * 0.25)
                self.ars.append(row)

    def swings(self, pid: int, d: int, speeds, angle=10.0, nan_angle=False):
        pk = self._key(d, 9000 + pid % 1000)
        self.games.setdefault(pk, (pk, d))
        for v in speeds:
            self.sw.append({"season": self.season, "game_pk": pk, "game_seq": pk, "date": self.dt(d),
                            "batter": pid, "bat_speed": float(v), "swing_length": 7.3,
                            "attack_angle": np.nan if nan_angle else float(angle)})

    def frame(self) -> TF.TrendFrame:
        g = pd.DataFrame([{"season": self.season, "game_pk": pk, "game_seq": pk,
                           "start_time": self.dt(d) + "T23:05:00Z", "date": self.dt(d), "home": None,
                           "away": None, "home_score": 0, "away_score": 0, "sb": 0, "cs": 0}
                          for pk, (_s, d) in sorted(self.games.items())])
        ars_cols = (["season", "game_pk", "game_seq", "date", "pitcher", "pitch_type", "bat_side", "n"]
                    + [f"{p}_{v}" for v in TF.PHYSICS for p in ("n", "s", "q")])
        pit = pd.DataFrame(self.pit)
        ars = pd.DataFrame(self.ars, columns=ars_cols)
        sw = pd.DataFrame(self.sw, columns=["season", "game_pk", "game_seq", "date", "batter",
                                            "bat_speed", "swing_length", "attack_angle"])
        bat = pd.DataFrame(columns=["season", "game_pk", "game_seq", "date", "batter", "club", "started"])
        covers = str(g["date"].max()) if len(g) else None
        return TF.TrendFrame(self.season, g, pit, ars, bat, sw, dict(self.prior_cut),
                             {"season": self.season, "covers_through": covers, "games": int(len(g)),
                              "key": f"fixture-{self.season}"})


def fixture_frames(seed: int = 3) -> dict:
    """Two synthetic seasons (2024, 2025) with nulls: untracked physics games,
    a swing with no attack angle, a planted lasting change, a planted change
    that reverts, a flagged player with no game after the flag, and a family
    (rp_spin) nobody changes in."""
    rng = np.random.default_rng(seed)
    frames = {}
    for season in (2024, 2025):
        b = _Fixture(season)
        last = 190
        for pid in range(1, 41):
            mu_hb = rng.uniform(-12.0, -4.0)
            fb = {"FF": (10, 10), "SL": (6, 6), "CH": (4, 4)}
            for d in range(pid % 2, last + 1, 2):
                hb = mu_hb + rng.normal(0, 1.0)
                mix = dict(fb)
                if pid == 1 and d >= 80:                  # a lasting shift in HB and in mix
                    hb += 4.0
                    mix = {"FF": (18, 18), "SL": (1, 1), "CH": (1, 1)}
                if pid == 2 and 80 <= d < 92:             # a shift that reverts
                    hb += 4.0
                if pid == 3 and d >= 80:                  # a shift, then no games at all
                    if d >= 92:
                        continue
                    hb += 4.0
                nan_ph = pid == 4 and d % 20 == 0          # untracked physics now and then
                b.appear(pid, d, hb=hb, spin=2300.0 + rng.normal(0, 40), ext=6.5 + rng.normal(0, 0.1),
                         mix=mix, nan_physics=nan_ph, li=np.nan if d % 7 == 0 else 1.0)
        for pid in range(101, 131):
            b.prior_cut[pid] = 60.0
            mu_a = rng.uniform(5.0, 15.0)
            for d in range(pid % 2, last + 1, 2):
                speeds = rng.normal(72.0, 3.0, size=8)
                angle = mu_a + rng.normal(0, 1.0)
                if pid == 101 and d >= 80:
                    angle += 8.0
                b.swings(pid, d, speeds, angle=angle, nan_angle=(pid == 102 and d % 10 == 0))
        frames[season] = b.frame()
    return frames


def dry_run(out: Optional[Path] = None, *, log: Callable = print) -> dict:
    """The whole reporting path on fixtures with nulls, written to ``out`` (a
    temporary file when none is given). Reads nothing from the repository
    beyond the gate document."""
    t0 = time.time()
    frames = fixture_frames()
    dates_by = {s: look_dates(s, fr.meta["covers_through"]) for s, fr in frames.items()}
    tables = {}
    for key in sorted(REGISTERED):
        fam = TD.FAMILIES[key]
        tables[key] = {s: L.measure_family(fr, fam, TD.eval_dates(s, fr.meta["covers_through"]), R_=2)
                       for s, fr in frames.items()}
    reg = parse_registration(GATE_DOC.read_text(encoding="utf-8")) if GATE_DOC.exists() else None
    checks = {"document": "fixture", "families": dict(REGISTERED), "excluded": list(EXCLUDED),
              "document_table": reg, "frames": {str(s): {"content_key": "fixture"} for s in frames},
              "eval_artifact": {"registered_sha256": EVAL_SHA256_REGISTERED,
                                "sha256_on_look_day": None, "equal": None}}
    art = run_look(frames, tables, dates_by, REGISTERED, mode="dry_run", checks=checks, log=log)
    art["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = Path(out) if out else Path(tempfile.mkdtemp(prefix="lt_persistence_")) / "persistence_eval.json"
    write_artifact(art, path)
    log(f"dry run wrote {path} in {time.time() - t0:.0f} s: "
        + json.dumps({k: (v["episodes"], v["hit_rate"], v["control_rate"], v["verdict"])
                      for k, v in art["families"].items()}))
    return art


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="fixtures with nulls through the whole path")
    ap.add_argument("--look", action="store_true", help="the one registered look")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    if a.dry_run == a.look:
        ap.error("one of --dry-run or --look")
    if a.dry_run:
        dry_run(a.out)
        return 0
    if a.out is None:
        ap.error("--look needs --out (never under data/)")
    return look(a.out)


if __name__ == "__main__":
    sys.exit(main())

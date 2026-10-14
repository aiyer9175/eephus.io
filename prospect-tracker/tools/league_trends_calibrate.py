#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""league_trends_calibrate - League Trends' calibration lab (plan 3.2 to 3.6,
4.3, 4.4 and 5.3; task TR_2B_CALIBRATE_DARK).

WHAT IT MEASURES. For every family of plan 3.3's tables and the families
plan 3.9 left off (for the record), on the weekly Sundays from the third
Sunday of May (trend_detect.eval_dates), the real test of every eligible
player and R = 20 seeded placebo shuffles, all through trend_detect and all
AS OF D (rulings T3 and R2): only games on or before D are read, the placebo
permutes each player's games on or before D, and the role, the primary
fastball, the competitive cut and every sigma are taken as of D.

  calibration seasons   pitcher-side and results families 2023, 2024 and 2025;
                        swing families 2024 and 2025 (bat tracking starts 2024)
  the live season       2026, scored only for a family with a bar, for the
                        held-out rule
  fit seasons           2021 and 2022 (and every calibration season before the
                        scored one), never the scored season or a later one

THE SHRINK FIT AND THE PLACEBO SD, FROM EARLIER SEASONS ONLY. The shrink fit
for season S takes the completed seasons before S: in the lab 2021 and 2022
for 2023, 2021 to 2023 for 2024 and 2021 to 2024 for 2025 (pitcher-side), and
2024 for 2025 (swings); the first swing season, 2024, has no earlier season and
is scored with the size floor on the raw change. The placebo SD of z (phi, the
scale the bar applies to, z / phi) is pooled over the same fit seasons, and is
1.0 (z unscaled) where no earlier season exists. Production in season Y uses
the pinned seasons in shrink.seasons (2023 to 2025 for pitchers, 2024 and 2025
for swings), all before Y, so no bar carries information from after D.

A FLAG. |z / phi| at or above the bar and the size (the shrunk change, or the
change net of drift with no fit) at or above the family's floor, real and
placebo alike (trend_detect.flag). Results families carry no floor.

THE POLICY (plan 3.2), per family on the pooled calibration seasons: the
smallest bar on trend_detect.BAR_GRID at which
  strict  false a day (placebo count over dates) 0.05 or fewer, share of flags
          above the placebo 0.90 or more, 20 or more pooled flags, and a share
          real of 0.75 or more in every season with 5 or more flags;
  looser  0.10 a day and 0.85, the same floors.
A family with no bar meeting every rule is left off.

THE HELD-OUT RULE (plan 3.2, ruling R7). At the chosen bar, the live season's
placebo exceedances summed over the R shuffles (O) against the quasi-Poisson
99th percentile phi_d x Poisson.ppf(0.99, lam / phi_d), lam = tail x tests x R
(tests summed over the live season's dates), phi_d = max(1, X2 / df) pooled
over the policy's families between the calibration seasons, X2 the sum over
seasons of (O_s - E_s)^2 / E_s on each season's summed placebo count against
the pooled tail's expectation. A family with O above the bound is left off the
served list and reported; no bar is raised on held-out data. The per-shuffle
counts are recorded for the record only.

ALSO WRITTEN. league_env (plan 4.4, ruling R4): four-seam mean velocity and the
sweeper (ST) and splitter (FS) shares of typed pitches, as labelled in MLB's
feed, and stolen-base attempts per club game, (SB + CS) / (2 x games), for 2018,
2019 and 2021 to 2025, from the pitch sidecar. rd_band (plan 4.3) only when
docs/diamond-betting.md records the 5c-A look or its closure and the 5d and 5k
reads or their closures; otherwise null with the reason. pool (plan 3.4): the
swing source and its receipts per season. prior_season (plan 3.8, lane 2.8):
prior-season mode at its fixed bar on the Sundays from April 6 to May 18, each
season against all of the one before it (pitcher families 2023 to 2025, swing
families 2025 against 2024), with that season's in-season fit and phi; a swing
family enters the mode only when it meets the strict policy's rules there.

WHERE. ``.cache/league_trends/preview/league_trends_eval.json`` while
League Trends is dark (``data/league_trends_eval.json`` only in the flip); the
per-season test tables are memoised under ``.cache/league_trends/lab/`` keyed
by the frame tables' content (frame_content_key), so a re-run on the same
inputs reads them back and writes the same artifact. Nothing here relates a trend, a club series or a
league series to a game result, a price, a ledger row or a later value of the
same trait.

Run:
    python tools/league_trends_calibrate.py [--refresh] [--jobs 3] [--out PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats as sst  # noqa: E402

import trend_detect as TD  # noqa: E402
import trend_frames as TF  # noqa: E402

CACHE_DIR = ROOT / ".cache"
PREVIEW_DIR = CACHE_DIR / "league_trends" / "preview"
EVAL_PREVIEW = PREVIEW_DIR / "league_trends_eval.json"
EVAL_DATA = ROOT / "data" / "league_trends_eval.json"
LAB_DIR = CACHE_DIR / "league_trends" / "lab"
BETTING_DOC = ROOT / "docs" / "diamond-betting.md"
LAB_VERSION = 2
SCHEMA = 1

R = TD.PLACEBO_R
SEED = TD.PLACEBO_SEED
GRID = tuple(float(b) for b in TD.BAR_GRID)

FIRST_FIT_SEASON = 2021
CAL_SEASONS = {"pitch": (2023, 2024, 2025), "swing": (2024, 2025)}
LIVE_SEASON = 2026
PROD_SHRINK_SEASONS = {"pitch": [2023, 2024, 2025], "swing": [2024, 2025]}

POLICIES = {
    "strict": {"false_per_day_max": 0.05, "real_min": 0.90},
    "looser": {"false_per_day_max": 0.10, "real_min": 0.85},
}
COUNT_FLOOR = 20                 # pooled flagged player-dates
SEASON_FLOOR = 5                 # a season is judged with 5 or more flags
SEASON_REAL_MIN = 0.75
HELD_OUT_Q = 0.99

LEAGUE_ENV_SEASONS = (2018, 2019, 2021, 2022, 2023, 2024, 2025)
RD_BAND_SEASONS = (2021, 2022, 2023, 2024, 2025)
SEASON_END_MIN = "09-25"         # a season's frame is complete through this date or later
# Prior-season mode (plan 3.8, lane 2.8): measured at its fixed bar on the
# early Sundays, each season against all of the one before it; the swing
# families against 2024 only (bat tracking starts 2024).
PRIOR_FIRST, PRIOR_LAST = (4, 6), (5, 18)
PRIOR_SEASONS = {"pitch": (2023, 2024, 2025), "swing": (2025,)}

# The provisional bars of plan 3.3 (the lane's saved tables, rulings T1, T2
# and R7), kept here as the record the re-measure is reported against.
PROVISIONAL = {
    "strict": {"sp_velo": 4.5, "rp_velo": 4.5, "rp_ivb": 5.0, "rp_hb": 4.5, "mix": 6.0,
               "rp_entry_li": 4.0, "bat_speed": 4.25, "swing_length": 4.25,
               "attack_angle": 4.25},
    "looser": {"sp_velo": 4.0, "rp_velo": 4.25, "rp_ivb": 4.5, "rp_hb": 4.25,
               "rp_spin": 4.75, "rp_ext": 4.5, "mix": 5.5, "rp_entry_li": 3.75,
               "bat_speed": 4.0, "swing_length": 4.0, "attack_angle": 4.0},
}


def _nolog(*_a, **_k) -> None:
    return None


# --------------------------------------------------------------------------- #
# the families
# --------------------------------------------------------------------------- #
# Starter physics families plan 3.3 and 3.9 left off (SP IVB, SP spin) or
# measured and left off (SP horizontal break, SP extension): the same
# statistic as sp_velo on another physics column, the floors of the reliever
# families. They live in trend_detect.FAMILIES so the policy can list them.
SP_RECORD = {k: TD.FAMILIES[k] for k in ("sp_ivb", "sp_hb", "sp_spin", "sp_ext")}

# Results families (plan 3.9, the lane's 2.3 second table), for the record:
# (key, label, side, kind, x, n, mode, size, min_w, min_b, role)
_RESULTS = (
    ("p_k_30d", "Pitcher strikeouts per batter faced, 30 days", "P", "rate", "so", "bf",
     "days", 30, 40, 150, None),
    ("p_bb_30d", "Pitcher walks per batter faced, 30 days", "P", "rate", "bb", "bf",
     "days", 30, 40, 150, None),
    ("p_whiff_sp3", "Pitcher whiffs per swing, last 3 starts", "P", "rate", "whiffs", "swings",
     "count", 3, 30, 150, "SP"),
    ("p_whiff_rp6", "Pitcher whiffs per swing, last 6 outings", "P", "rate", "whiffs", "swings",
     "count", 6, 30, 150, "RP"),
    ("p_chase_30d", "Pitcher chases per out-of-zone pitch, 30 days", "P", "rate", "chases", "ooz",
     "days", 30, 80, 250, None),
    ("h_chase_30d", "Hitter chases per out-of-zone pitch, 30 days", "H", "rate", "chases", "ooz",
     "days", 30, 80, 250, None),
    ("h_whiff_60d", "Hitter whiffs per swing, 60 days", "H", "rate", "whiffs", "swings",
     "days", 60, 120, 120, None),
    ("h_k_30d", "Hitter strikeouts per PA, 30 days", "H", "rate", "so", "pa",
     "days", 30, 50, 150, None),
    ("h_bb_30d", "Hitter walks per PA, 30 days", "H", "rate", "bb", "pa",
     "days", 30, 50, 150, None),
    ("h_ev_30d", "Hitter mean exit velocity per batted ball, 30 days", "H", "unit", "ls_sum",
     "bbe", "days", 30, 25, 60, None),
    ("h_hard_30d", "Hitter hard-hit (95+ mph) per batted ball, 30 days", "H", "rate", "hard",
     "bbe", "days", 30, 25, 60, None),
    ("h_woba_30d", "Hitter wOBA, 30 days", "H", "woba", "wnum", "wden",
     "days", 30, 50, 150, None),
)
RESULTS = {r[0]: dict(zip(("key", "label", "side", "kind", "x", "n", "mode", "size", "min_w",
                           "min_b", "role"), r)) for r in _RESULTS}
# the families as trend_detect.flag reads them: no size floor, no shrink fit
_RESULT_UNIT = {"rate": "share", "unit": "mph", "woba": "wOBA"}
RESULTS_FAM = {k: TD.Family(k, r["label"], _RESULT_UNIT[r["kind"]], r["kind"], r["x"],
                            (r["role"] or ("H" if r["side"] == "H" else "P"),),
                            {"any": (r["mode"], r["size"])}, r["min_w"], r["min_b"], 0,
                            None, True)
               for k, r in RESULTS.items()}
# the lane's fixed linear weights (p7_calibrate.py WW), for the record family only
WOBA_W = {"ubb": 0.69, "hbp": 0.72, "s1": 0.89, "s2": 1.27, "s3": 1.62, "hr": 2.10}
UNIT_NU = 30.0
UNIT_VAR_FLOOR = 1.0
RATE_ACTIVE_DAYS = {"days": 7, "count": TD.ACTIVE_DAYS}


def all_families() -> dict:
    """key -> Family for every measured family, trend_detect's first."""
    out = dict(TD.FAMILIES)
    out.update(RESULTS_FAM)
    return out


def calib_group(fam: TD.Family) -> str:
    return "swing" if fam.kind == "swing" else "pitch"


def lab_fit_seasons(fam: TD.Family, season: int) -> list:
    """The seasons the lab fits on (shrink and placebo SD) for a scored season."""
    g = calib_group(fam)
    if int(season) == LIVE_SEASON:
        return list(PROD_SHRINK_SEASONS[g])
    first = TF.FIRST_SWING_SEASON if g == "swing" else FIRST_FIT_SEASON
    return list(range(first, int(season)))


def needed_seasons(fam: TD.Family) -> list:
    g = calib_group(fam)
    first = TF.FIRST_SWING_SEASON if g == "swing" else FIRST_FIT_SEASON
    return list(range(first, max(CAL_SEASONS[g]) + 1))


# --------------------------------------------------------------------------- #
# results families, as of D (lab only; the lane's statistics, p7_calibrate.py)
# --------------------------------------------------------------------------- #
def results_rows(frame, lines_hit: Optional[pd.DataFrame], spec: dict) -> pd.DataFrame:
    """One row per player-game with the family's count columns."""
    if spec["side"] == "P":
        p = frame.pit
        out = pd.DataFrame({"pid": p["pitcher"].astype("int64"), "game_pk": p["game_pk"],
                            "game_seq": p["game_seq"], "date": p["date"],
                            "start": p["start"].astype(bool)})
        out["x"], out["n"] = p[spec["x"]].astype("float64"), p[spec["n"]].astype("float64")
        out["s2"] = 0.0
        return out.reset_index(drop=True)
    b = frame.bat
    out = pd.DataFrame({"pid": b["batter"].astype("int64"), "game_pk": b["game_pk"],
                        "game_seq": b["game_seq"], "date": b["date"], "start": False})
    if spec["kind"] == "unit":
        out["x"], out["n"] = b["ls_sum"].astype("float64"), b["bbe"].astype("float64")
        out["s2"] = b["ls_sq"].astype("float64")
    elif spec["kind"] == "woba":
        h = lines_hit.rename(columns={"mlbam": "batter"})[
            ["game_pk", "batter", "d", "t", "hr", "ibb"]]
        m = b[["game_pk", "batter", "pa", "ab", "h", "bb", "hbp", "sf"]].merge(
            h, on=["game_pk", "batter"], how="left").fillna(0)
        s1 = m["h"] - m["d"] - m["t"] - m["hr"]
        ubb = m["bb"] - m["ibb"]
        w = WOBA_W
        out["x"] = (w["ubb"] * ubb + w["hbp"] * m["hbp"] + w["s1"] * s1 + w["s2"] * m["d"]
                    + w["s3"] * m["t"] + w["hr"] * m["hr"]).to_numpy(dtype="float64")
        out["s2"] = (w["ubb"] ** 2 * ubb + w["hbp"] ** 2 * m["hbp"] + w["s1"] ** 2 * s1
                     + w["s2"] ** 2 * m["d"] + w["s3"] ** 2 * m["t"]
                     + w["hr"] ** 2 * m["hr"]).to_numpy(dtype="float64")
        out["n"] = (m["ab"] + ubb + m["sf"] + m["hbp"]).to_numpy(dtype="float64")
    else:
        out["x"], out["n"] = b[spec["x"]].astype("float64"), b[spec["n"]].astype("float64")
        out["s2"] = 0.0
    return out.reset_index(drop=True)


def _results_stat(u: pd.DataFrame, D: str, spec: dict) -> pd.DataFrame:
    """The lane's rate, unit-mean and wOBA statistics on rows on or before D."""
    cols = ["pid", "D", "role", "nW", "nB", "raw", "drift", "d", "se", "z"]
    if u.empty:
        return pd.DataFrame(columns=cols)
    last = u.groupby("pid")["date"].transform("max")
    u = u[last >= TD._minus(D, RATE_ACTIVE_DAYS[spec["mode"]] - 1)]
    if u.empty:
        return pd.DataFrame(columns=cols)
    if spec["mode"] == "count":
        u = u.sort_values(["pid", "game_seq"], kind="mergesort")
        inwin = u.groupby("pid").cumcount(ascending=False).to_numpy() < spec["size"]
    else:
        inwin = (u["date"] >= TD._minus(D, spec["size"] - 1)).to_numpy()
    u = u.assign(inwin=inwin)
    s = u.groupby(["pid", "inwin"])[["x", "n", "s2"]].sum().unstack("inwin").fillna(0.0)
    if (("n", True) not in s.columns) or (("n", False) not in s.columns):
        return pd.DataFrame(columns=cols)
    xw, nw, qw = s[("x", True)], s[("n", True)], s[("s2", True)]
    xb, nb, qb = s[("x", False)], s[("n", False)], s[("s2", False)]
    keep = (nw >= spec["min_w"]) & (nb >= spec["min_b"])
    if spec["kind"] == "rate":
        keep &= xb > 0
    xw, nw, qw, xb, nb, qb = (v[keep] for v in (xw, nw, qw, xb, nb, qb))
    if not len(nw):
        return pd.DataFrame(columns=cols)
    mb, mw = xb / nb, xw / nw
    if spec["kind"] == "rate":
        var = np.clip(mb * (1 - mb), 1e-9, None)
    elif spec["kind"] == "unit":
        vb = (qb / nb - mb ** 2).clip(lower=UNIT_VAR_FLOOR)
        pooled = float(np.average(vb, weights=nb))
        var = (UNIT_NU * pooled + nb * vb) / (UNIT_NU + nb)
    else:
        var = (qb / nb - mb ** 2).clip(lower=1e-4)
    raw = mw - mb
    dr = float(raw.mean())
    se = np.sqrt(var * (1.0 / nw + 1.0 / nb))
    d = raw - dr
    out = pd.DataFrame({"pid": raw.index.astype("int64"), "D": D,
                        "role": spec["role"] or spec["side"], "nW": nw.to_numpy(),
                        "nB": nb.to_numpy(), "raw": raw.to_numpy(), "drift": dr,
                        "d": d.to_numpy(), "se": se.to_numpy(), "z": (d / se).to_numpy()})
    return out.sort_values("pid", kind="mergesort").reset_index(drop=True)


def results_tests(frame, rows: pd.DataFrame, D: str, spec: dict, R_: int, seed: int) -> tuple:
    """(real, placebo) tests at D; the placebo permutes each player's count
    columns across his own games on or before D (trend_detect._permute)."""
    u = rows[rows["date"] <= D]
    if spec["role"]:
        role = u["pid"].map(TD.roles_as_of(frame, D))
        u = u[(role == spec["role"]).to_numpy()]
        if spec["role"] == "SP":
            u = u[u["start"].to_numpy()]
    real = _results_stat(u, D, spec)
    pls = []
    for r in range(int(R_)):
        pu = TD._permute(u, ["x", "n", "s2"], seed, r)
        pls.append(_results_stat(pu, D, spec).assign(rep=r))
    pls = [x for x in pls if len(x)]
    pl = pd.concat(pls, ignore_index=True) if pls else pd.DataFrame()
    return real, pl


# --------------------------------------------------------------------------- #
# measuring one season (the slow part; memoised)
# --------------------------------------------------------------------------- #
_KEEP = ["pid", "D", "role", "nW", "nB", "raw", "drift", "d", "se", "z", "t", "rep"]


def _norm(t: pd.DataFrame, rep: int) -> pd.DataFrame:
    t = t.copy()
    if "rep" not in t.columns:
        t["rep"] = rep
    if "t" not in t.columns:
        t["t"] = np.nan
    for c in _KEEP:
        if c not in t.columns:
            t[c] = np.nan
    t = t[_KEEP]
    t["pid"] = t["pid"].astype("int64")
    t["rep"] = t["rep"].astype("int64")
    for c in ("nW", "nB", "raw", "drift", "d", "se", "z", "t"):
        t[c] = t[c].astype("float64")
    t["D"] = t["D"].astype(str)
    t["role"] = t["role"].astype(str)
    return t


def measure_family(frame, fam: TD.Family, dates: list, *, rows=None, R_: int = R,
                   seed: int = SEED) -> pd.DataFrame:
    """Every real test (rep -1) and every placebo test (rep 0 to R-1) of one
    family over the dates, phi 1 (z unscaled)."""
    parts = []
    for D in dates:
        if fam.key in RESULTS:
            real, pl = results_tests(frame, rows, D, RESULTS[fam.key], R_, seed)
        else:
            real = TD.detect(frame, D, fam, phi=1.0)
            pl = TD.placebo(frame, D, fam, R=R_, seed=seed, phi=1.0)
        if len(real):
            parts.append(_norm(real.assign(D=D), -1))
        if len(pl):
            parts.append(_norm(pl.assign(D=D), 0))
    if not parts:
        return _norm(pd.DataFrame(columns=_KEEP), -1)
    out = pd.concat(parts, ignore_index=True)
    return out.sort_values(["rep", "D", "role", "pid"], kind="mergesort").reset_index(drop=True)


def _frame_ok(frame, manifest: dict) -> Optional[str]:
    """None when the season's frame is complete, else the reason."""
    s = str(int(frame.season))
    m = (manifest.get("seasons") or {}).get(s) or {}
    if not m:
        return f"{s}: the pitch sidecar manifest has no season"
    if int(frame.meta.get("games") or 0) != int(m.get("games") or -1):
        return f"{s}: the frame holds {frame.meta.get('games')} games, the sidecar {m.get('games')}"
    ct = str(frame.meta.get("covers_through") or "")
    if ct < f"{s}-{SEASON_END_MIN}":
        return f"{s}: the frame covers through {ct or 'nothing'}"
    return None


def _memo_dir(lab_dir: Path, season: int) -> Path:
    return Path(lab_dir) / str(int(season))


_CLUB_COLS = ("club", "home", "away")


def frame_content_key(frame) -> str:
    """A hash of the frame's tables by content (rows in any order), the club
    columns left out: they label cards and never enter a test. The frame's own
    key follows the size and mtime of every input, so a rebuild on an
    unchanged sidecar and swing source (war_daily restamped by another job)
    would re-measure every season for the same tables; this key does not."""
    h = hashlib.sha256()
    for name in TF._TABLES:
        t = getattr(frame, name)
        t = t.drop(columns=[c for c in t.columns if c in _CLUB_COLS])
        t = t.reindex(sorted(t.columns), axis=1)
        h.update(name.encode("ascii"))
        h.update(",".join(f"{c}:{t[c].dtype}" for c in t.columns).encode("ascii"))
        hv = pd.util.hash_pandas_object(t, index=False).to_numpy(dtype="uint64")
        h.update(np.sort(hv).tobytes())
    pc = frame.prior_cut or {}
    h.update(json.dumps({str(k): round(float(v), 6) for k, v in pc.items()},
                        sort_keys=True).encode("ascii"))
    return h.hexdigest()[:20]


def measure_season(season: int, keys: list, *, lab_dir: Path = LAB_DIR, refresh: bool = False,
                   frame_loader: Callable = None, lines_loader: Callable = None,
                   R_: int = R, seed: int = SEED, log: Callable = _nolog) -> dict:
    """Measure the families ``keys`` on one season (memoised by the frame's
    key). Returns {key: test table} and writes the memo."""
    fams = all_families()
    loader = frame_loader or (lambda s: TF.pitch_game_frame(s))
    frame = loader(int(season))
    dates = TD.eval_dates(int(season), str(frame.meta.get("covers_through")))
    fkey = str(frame.meta.get("key") or "")
    ckey = frame_content_key(frame)
    md = _memo_dir(lab_dir, season)
    out = {}
    lines_hit = None
    rows_by = {}
    for k in keys:
        fam = fams[k]
        p = md / f"{k}.parquet"
        mp = md / f"{k}.json"
        sig = {"lab_version": LAB_VERSION, "content_key": ckey, "R": int(R_), "seed": int(seed),
               "dates": dates}
        if not refresh and p.exists() and mp.exists():
            try:
                if json.loads(mp.read_text(encoding="utf-8")) == sig:
                    out[k] = pd.read_parquet(p)
                    continue
            except (OSError, ValueError):
                pass
        t0 = time.time()
        rows = None
        if k in RESULTS:
            spec = RESULTS[k]
            if spec["kind"] == "woba" and lines_hit is None:
                lines_hit = (lines_loader or _lines_hit)(int(season))
            ck = (spec["side"], spec["kind"], spec["x"], spec["n"])
            if ck not in rows_by:
                rows_by[ck] = results_rows(frame, lines_hit, spec)
            rows = rows_by[ck]
        t = measure_family(frame, fam, dates, rows=rows, R_=R_, seed=seed)
        md.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".parquet.tmp")
        t.to_parquet(tmp, index=False)
        os.replace(tmp, p)
        mp.write_text(json.dumps(sig), encoding="utf-8")
        out[k] = pd.read_parquet(p)
        log(f"  {season} {k}: {int((t['rep'] < 0).sum()):,} tests over {len(dates)} dates "
            f"({time.time() - t0:.1f} s)")
    return {"tables": out, "dates": dates, "frame_key": fkey, "content_key": ckey,
            "covers_through": str(frame.meta.get("covers_through")),
            "games": int(frame.meta.get("games") or 0)}


def prior_dates(season: int) -> list:
    """Prior-season mode's evaluation dates (lane 2.8, probe P9): every Sunday
    from the first Sunday on or after April 6 to May 18."""
    from datetime import date, timedelta
    d = date(int(season), *PRIOR_FIRST)
    while d.weekday() != 6:
        d += timedelta(days=1)
    out, end = [], date(int(season), *PRIOR_LAST)
    while d <= end:
        out.append(d.isoformat())
        d += timedelta(days=7)
    return out


def measure_prior(frame, prior, fam: TD.Family, dates: list, *, R_: int = R,
                  seed: int = SEED) -> pd.DataFrame:
    """Prior-season mode's real tests (rep -1) and placebo tests (rep 0 to R-1)
    over the dates, through trend_detect.detect_prior and placebo_prior, phi 1."""
    parts = []
    for D in dates:
        real = TD.detect_prior(frame, prior, D, fam, phi=1.0, swing_ok=True)
        pl = TD.placebo_prior(frame, prior, D, fam, R=R_, seed=seed, phi=1.0, swing_ok=True)
        if len(real):
            parts.append(_norm(real.assign(D=D), -1))
        if len(pl):
            parts.append(_norm(pl.assign(D=D), 0))
    if not parts:
        return _norm(pd.DataFrame(columns=_KEEP), -1)
    out = pd.concat(parts, ignore_index=True)
    return out.sort_values(["rep", "D", "role", "pid"], kind="mergesort").reset_index(drop=True)


def measure_prior_season(season: int, keys: list, *, lab_dir: Path = LAB_DIR,
                         refresh: bool = False, frame_loader: Callable = None, R_: int = R,
                         seed: int = SEED, log: Callable = _nolog) -> dict:
    """Prior-season mode on ``season`` against all of ``season - 1`` (memoised
    as prior_<key>.parquet beside the in-season tables)."""
    loader = frame_loader or (lambda s: TF.pitch_game_frame(s))
    frame, prior = loader(int(season)), loader(int(season) - 1)
    dates = prior_dates(int(season))
    sig = {"lab_version": LAB_VERSION, "content_key": frame_content_key(frame),
           "prior_content_key": frame_content_key(prior), "R": int(R_), "seed": int(seed),
           "dates": dates, "mode": "prior_season"}
    md = _memo_dir(lab_dir, season)
    out = {}
    for k in keys:
        fam = TD.FAMILIES[k]
        p, mp = md / f"prior_{k}.parquet", md / f"prior_{k}.json"
        if not refresh and p.exists() and mp.exists():
            try:
                if json.loads(mp.read_text(encoding="utf-8")) == sig:
                    out[k] = pd.read_parquet(p)
                    continue
            except (OSError, ValueError):
                pass
        t0 = time.time()
        t = measure_prior(frame, prior, fam, dates, R_=R_, seed=seed)
        md.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".parquet.tmp")
        t.to_parquet(tmp, index=False)
        os.replace(tmp, p)
        mp.write_text(json.dumps(sig), encoding="utf-8")
        out[k] = pd.read_parquet(p)
        log(f"  {season} prior-season {k}: {int((t['rep'] < 0).sum()):,} tests over "
            f"{len(dates)} dates ({time.time() - t0:.1f} s)")
    return {"tables": out, "dates": dates}


def prior_block(tables: dict, dates: dict, per_family: dict, R_: int = R) -> dict:
    """Prior-season mode at its fixed bar (PRIOR_SEASON_BAR), per family and
    season, with each season's in-season fit and phi (earlier seasons only);
    swing_ok when a swing family meets the strict policy's rules at that bar on
    its prior-season seasons (plan 3.8)."""
    bar = f"{float(TD.PRIOR_SEASON_BAR):g}"
    fams, swing_ok = {}, {}
    for k in sorted({k for by in tables.values() for k in by}):
        fam = TD.FAMILIES[k]
        seasons = sorted(s for s in tables if k in tables[s])
        per = {}
        blk = {"label": fam.label, "group": calib_group(fam), "seasons": {}}
        for s in seasons:
            fit = per_family[k]["fits"].get(s)
            phi = per_family[k]["phi_used"].get(s, 1.0)
            c = season_counts(tables[s][k], fam, fit, phi, dates[s], R_)
            per[s] = c
            sb = season_block(c, R_)
            blk["seasons"][str(s)] = {"dates": sb["dates"], "tests": sb["tests"],
                                      "phi_used": _r(phi, 4), "real_sd_z": sb["real_sd_z"],
                                      "placebo_sd_z": sb["phi"], "at_bar": sb["by_bar"][bar]}
        p = pooled(per, seasons, bar, R_)
        blk["pooled"] = p
        blk["meets_strict"] = passes(p, "strict")
        if fam.kind == "swing":
            swing_ok[k] = blk["meets_strict"]
        fams[k] = blk
    return {"bar": float(TD.PRIOR_SEASON_BAR),
            "dates": "every Sunday from the first Sunday on or after April 6 to May 18",
            "seasons": {g: list(v) for g, v in PRIOR_SEASONS.items()},
            "against": "all of the previous season", "families": fams, "swing_ok": swing_ok}


def _lines_hit(season: int) -> pd.DataFrame:
    import mlbstats_games as G                       # P8.2's public game lines, read only
    return G.player_game_frame(int(season)).hit


# --------------------------------------------------------------------------- #
# the arithmetic (pure: tables in, artifact blocks out)
# --------------------------------------------------------------------------- #
def _r(x, n: int = 6):
    if x is None:
        return None
    x = float(x)
    return None if not np.isfinite(x) else round(x, n)


def _pooled_placebo_sd(tables: dict, seasons: list) -> Optional[float]:
    z = [t.loc[t["rep"] >= 0, "z"].to_numpy(dtype="float64") for s, t in tables.items()
         if s in seasons]
    z = np.concatenate(z) if z else np.array([])
    z = z[np.isfinite(z)]
    return float(np.std(z, ddof=1)) if len(z) > 1 else None


def _fit_record(fit: Optional[dict]) -> Optional[dict]:
    if fit is None:
        return None
    out = {"kind": fit["kind"], "pi0": _r(fit["pi0"]), "tau": _r(fit["tau"]),
           "seasons": list(fit["seasons"]), "scored_season": int(fit["scored_season"]),
           "n_tests": int(fit["n_tests"]), "identified": bool(fit["identified"])}
    if "phi" in fit:
        out["phi"] = _r(fit["phi"])
    if fit["kind"] == "mix_selected_null":
        out["null"] = {"source": fit["null"]["source"], "h": _r(fit["null"]["h"]),
                       "n": int(len(fit["null"]["t"]))}
    return out


def _flag_frame(tests: pd.DataFrame, fam: TD.Family, fit: Optional[dict], phi: float) -> pd.DataFrame:
    """Columns rep, D, az (|z / phi|) and floor_ok through trend_detect.flag."""
    t = tests.copy()
    t["z_adj"] = t["z"] / phi
    if fam.kind == "mix" and fit is not None and fit.get("identified") and len(t) > 4000:
        parts = [TD.flag(t.iloc[i:i + 4000], fam, GRID[0], fit, phi=phi)
                 for i in range(0, len(t), 4000)]
        fl = pd.concat(parts)
    else:
        fl = TD.flag(t, fam, GRID[0], fit, phi=phi)
    return pd.DataFrame({"rep": fl["rep"].to_numpy(), "D": fl["D"].to_numpy(),
                         "az": fl["z_adj"].abs().to_numpy(dtype="float64"),
                         "floor_ok": fl["floor_ok"].astype(bool).to_numpy()})


def season_counts(tests: pd.DataFrame, fam: TD.Family, fit: Optional[dict], phi: float,
                  dates: list, R_: int = R) -> dict:
    """Per bar: real flags, placebo false (summed over shuffles / R) and the
    per-shuffle counts; tests and dates."""
    fl = _flag_frame(tests, fam, fit, phi) if len(tests) else pd.DataFrame(
        columns=["rep", "D", "az", "floor_ok"])
    real = fl[fl["rep"] < 0]
    pl = fl[fl["rep"] >= 0]
    n_tests = int(len(real))
    by = {}
    for b in GRID:
        rf = int(((real["az"] >= b) & real["floor_ok"]).sum())
        hit = (pl["az"] >= b) & pl["floor_ok"]
        per = pl.loc[hit.to_numpy(), "rep"].value_counts().reindex(range(R_), fill_value=0)
        by[f"{b:g}"] = {"flags": rf, "placebo_sum": int(per.sum()),
                        "per_shuffle": [int(x) for x in per.to_numpy()]}
    zr = tests.loc[tests["rep"] < 0, "z"].to_numpy(dtype="float64")
    zp = tests.loc[tests["rep"] >= 0, "z"].to_numpy(dtype="float64")
    zr, zp = zr[np.isfinite(zr)], zp[np.isfinite(zp)]
    return {"dates": len(dates), "tests": n_tests,
            "real_sd_z": _r(np.std(zr, ddof=1), 4) if len(zr) > 1 else None,
            "placebo_sd_z": _r(np.std(zp, ddof=1), 4) if len(zp) > 1 else None,
            "by_bar": by}


def season_block(c: dict, R_: int = R) -> dict:
    """The per-season record of plan 5.3 from the counts."""
    nd, nt = c["dates"], c["tests"]
    bars = {}
    for b, v in c["by_bar"].items():
        false = v["placebo_sum"] / R_
        bars[b] = {"flags": v["flags"], "false": _r(false, 4),
                   "flags_per_day": _r(v["flags"] / nd, 4) if nd else None,
                   "false_per_day": _r(false / nd, 5) if nd else None,
                   "tail_per_test": _r(false / nt, 8) if nt else None,
                   "placebo_sum": v["placebo_sum"]}
    return {"dates": nd, "tests": nt, "tests_per_date": _r(nt / nd, 2) if nd else None,
            "phi": c["placebo_sd_z"], "real_sd_z": c["real_sd_z"], "by_bar": bars}


def pooled(per_season: dict, seasons: list, bar: str, R_: int = R) -> dict:
    rows = [(s, per_season[s]) for s in seasons if s in per_season]
    nd = sum(c["dates"] for _, c in rows)
    nt = sum(c["tests"] for _, c in rows)
    fl = sum(c["by_bar"][bar]["flags"] for _, c in rows)
    fa = sum(c["by_bar"][bar]["placebo_sum"] for _, c in rows) / R_
    judged, not_judged, worst = [], [], None
    for s, c in rows:
        f_s = c["by_bar"][bar]["flags"]
        if f_s >= SEASON_FLOOR:
            judged.append(int(s))
            share = 1.0 - (c["by_bar"][bar]["placebo_sum"] / R_) / f_s
            worst = share if worst is None else min(worst, share)
        else:
            not_judged.append(int(s))
    return {"bar": float(bar), "dates": nd, "tests": nt,
            "tests_per_day": _r(nt / nd, 2) if nd else None,
            "flag_count": int(fl), "false_count": _r(fa, 4),
            "flags_per_day": _r(fl / nd, 4) if nd else None,
            "false_per_day": _r(fa / nd, 5) if nd else None,
            "real": _r(1.0 - fa / fl, 4) if fl > 0 else None,
            "worst_judged": _r(worst, 4), "seasons_judged": judged,
            "seasons_not_judged": not_judged,
            "tail_per_test": _r(fa / nt, 8) if nt else None}


def passes(p: dict, policy: str) -> bool:
    rule = POLICIES[policy]
    if p["real"] is None or p["false_per_day"] is None:
        return False
    return bool(p["false_per_day"] <= rule["false_per_day_max"]
                and p["real"] >= rule["real_min"]
                and p["flag_count"] >= COUNT_FLOOR
                and (p["worst_judged"] is None or p["worst_judged"] >= SEASON_REAL_MIN))


def choose(per_season: dict, seasons: list, policy: str, R_: int = R) -> Optional[dict]:
    """The smallest bar on the grid that meets every rule of the policy."""
    for b in GRID:
        p = pooled(per_season, seasons, f"{b:g}", R_)
        if passes(p, policy):
            return p
    return None


def dispersion(items: list, R_: int = R) -> dict:
    """phi_d = max(1, X2 / df) over the families' calibration seasons at their
    chosen bars. items: (key, per_season, seasons, bar, tail)."""
    x2, df, parts = 0.0, 0, []
    for key, per, seasons, bar, tail in items:
        fx2, k = 0.0, 0
        for s in seasons:
            c = per[s]
            o = c["by_bar"][bar]["placebo_sum"]
            e = tail * c["tests"] * R_
            if e > 0:
                fx2 += (o - e) ** 2 / e
            k += 1
        x2 += fx2
        df += max(k - 1, 0)
        parts.append({"family": key, "bar": float(bar), "x2": _r(fx2, 4), "df": max(k - 1, 0)})
    phi = max(1.0, x2 / df) if df > 0 else 1.0
    return {"phi": _r(phi, 4), "x2": _r(x2, 4), "df": int(df), "bound": "quasi-Poisson 99th",
            "q": HELD_OUT_Q, "families": parts}


def quasi_bound(lam: float, phi: float) -> float:
    return float(phi * sst.poisson.ppf(HELD_OUT_Q, lam / phi)) if lam > 0 else 0.0


def held_out(c: dict, tail: float, phi_d: float, bar: str, R_: int = R) -> dict:
    v = c["by_bar"][bar]
    lam = tail * c["tests"] * R_
    bound = quasi_bound(lam, phi_d)
    o = v["placebo_sum"]
    nd = c["dates"]
    false = o / R_
    return {"season": LIVE_SEASON, "bar": float(bar), "dates": nd, "tests": c["tests"],
            "flags": v["flags"], "flags_per_day": _r(v["flags"] / nd, 4) if nd else None,
            "false_per_day": _r(false / nd, 5) if nd else None,
            "real": _r(1.0 - false / v["flags"], 4) if v["flags"] else None,
            "placebo_sum": int(o), "lam": _r(lam, 4), "phi": _r(phi_d, 4),
            "bound": _r(bound, 4), "poisson_99": int(sst.poisson.ppf(HELD_OUT_Q, lam)),
            "per_shuffle": list(v.get("per_shuffle") or []),
            "verdict": "left off" if o > bound else "kept"}


def betting_records(text: str) -> dict:
    """Whether docs/diamond-betting.md records the 5c-A look or its closure,
    and the 5d and 5k reads or their closures (plan 4.3)."""
    c5a = bool(re.search(r"#### Closure, recorded 2026-10-02: the pair closes for 2026", text)
               or re.search(r"### Result \(run [0-9-]+, once\)[^\n]*xwoba", text, re.I))
    k5 = bool(re.search(r"### Result \(run [0-9-]+, once\): 5k", text))
    d5_head = re.search(r"### Decisions recorded [0-9-]+: 5d-C[^\n]*", text)
    d5_open = bool(re.search(r"\*\*5d-A, 5d-B, 5d-D and 5d-E: not read\.\*\*", text))
    d5 = bool(re.search(r"### Result \(run [0-9-]+, once\)[^\n]*5d", text)) or (
        bool(d5_head) and not d5_open)
    return {"5c-A": c5a, "5d": d5, "5k": k5,
            "5d_note": ("5d-C decided at p = 1 without a read; 5d-A, 5d-B, 5d-D and 5d-E "
                        "recorded as not read, with no last day and no closure")
            if (d5_head and d5_open) else None}


def summarize(per_family: dict, *, live: dict, env: dict, pool: dict, rd_band,
              inputs: dict, prior: Optional[dict] = None, R_: int = R) -> dict:
    """The eval artifact from the measured counts. per_family: key ->
    {"fam", "seasons": {season: counts}, "phi_used", "phi_seasons", "fits"};
    live: key -> counts of the live season (only for a family with a bar)."""
    fams = all_families()
    out_f = {}
    chosen = {"strict": {}, "looser": {}}
    for key, rec in per_family.items():
        fam = rec["fam"]
        g = calib_group(fam)
        cal = [s for s in CAL_SEASONS[g] if s in rec["seasons"]]
        blk = {"label": fam.label, "unit": fam.unit, "kind": fam.kind, "group": g,
               "in_trend_detect": key in TD.FAMILIES, "drift": bool(fam.drift),
               "size_floor": _r(fam.size_floor), "calibration_seasons": cal,
               "seasons": {}, "pooled": {}, "chosen": {}}
        for s, c in sorted(rec["seasons"].items()):
            sb = season_block(c, R_)
            sb["phi_used"] = _r(rec["phi_used"].get(s, 1.0), 4)
            sb["phi_seasons"] = rec["phi_seasons"].get(s, [])
            sb["fit"] = _fit_record(rec["fits"].get(s))
            sb["calibration"] = s in cal
            blk["seasons"][str(s)] = sb
        blk["pooled"] = {f"{b:g}": pooled(rec["seasons"], cal, f"{b:g}", R_) for b in GRID}
        for pol in POLICIES:
            ch = choose(rec["seasons"], cal, pol, R_)
            blk["chosen"][pol] = ch
            if ch is not None:
                chosen[pol][key] = ch
        out_f[key] = blk

    held = {}
    for pol in POLICIES:
        items = [(k, per_family[k]["seasons"], out_f[k]["calibration_seasons"],
                  f"{ch['bar']:g}", ch["tail_per_test"]) for k, ch in sorted(chosen[pol].items())]
        disp = dispersion(items, R_)
        verdicts = {}
        for k, ch in sorted(chosen[pol].items()):
            b = f"{ch['bar']:g}"
            if k in live:
                verdicts[k] = held_out(live[k], ch["tail_per_test"], disp["phi"], b, R_)
            else:
                verdicts[k] = {"season": LIVE_SEASON, "bar": ch["bar"], "verdict": "not scored"}
            # per-shuffle counts at the chosen bar, for the record
            for s in out_f[k]["calibration_seasons"]:
                out_f[k]["seasons"][str(s)].setdefault("per_shuffle", {})[pol] = \
                    per_family[k]["seasons"][s]["by_bar"][b]["per_shuffle"]
            out_f[k].setdefault("held_out", {})[pol] = verdicts[k]
        held[pol] = {**disp, "verdicts": {k: v["verdict"] for k, v in verdicts.items()}}

    bars = {pol: {k: ch["bar"] for k, ch in sorted(chosen[pol].items())
                  if held[pol]["verdicts"].get(k) == "kept"} for pol in POLICIES}
    served = sorted(bars["strict"])
    placebo_sd = {}
    for k in sorted(set(bars["strict"]) | set(bars["looser"])):
        placebo_sd[k] = _r(per_family[k]["phi_used"].get(LIVE_SEASON), 4)

    totals = {}
    for pol in POLICIES:
        fl = fa = 0.0
        hfl = hfa = 0.0
        for k in bars[pol]:
            ch = chosen[pol][k]
            fl += ch["flags_per_day"]
            fa += ch["tail_per_test"] * ch["tests_per_day"]
            h = out_f[k]["held_out"][pol]
            if h.get("flags_per_day") is not None:
                hfl += h["flags_per_day"]
                hfa += h["false_per_day"]
        totals[pol] = {"families": len(bars[pol]), "flags_per_day": _r(fl, 4),
                       "false_per_day": _r(fa, 5), "real": _r(1 - fa / fl, 4) if fl else None,
                       "live": {"flags_per_day": _r(hfl, 4), "false_per_day": _r(hfa, 5)}}

    prov = PROVISIONAL
    changes = {}
    for pol in POLICIES:
        joins = sorted(set(bars[pol]) - set(prov[pol]))
        leaves = sorted(set(prov[pol]) - set(bars[pol]))
        moved = {k: [prov[pol][k], bars[pol][k]] for k in sorted(set(prov[pol]) & set(bars[pol]))
                 if float(prov[pol][k]) != float(bars[pol][k])}
        changes[pol] = {"joins": joins, "leaves": leaves, "moved": moved,
                        "provisional": prov[pol]}

    fits_prod = {}
    mix_null = None
    for k in sorted(set(bars["strict"]) | set(bars["looser"])):
        f = per_family[k]["fits"].get(LIVE_SEASON)
        fits_prod[k] = _fit_record(f)
        if f is not None and f["kind"] == "mix_selected_null":
            mix_null = {"source": f["null"]["source"], "seasons": list(f["seasons"]),
                        "h": _r(f["null"]["h"], 8),
                        "t": [round(float(x), 6) for x in f["null"]["t"]]}
    lab_seasons = {k: {str(s): per_family[k]["phi_seasons"].get(s, [])
                       for s in sorted(per_family[k]["seasons"])
                       if s in out_f[k]["calibration_seasons"] or s == LIVE_SEASON}
                   for k in sorted(per_family)}
    if prior is None:
        prior = {"bar": float(TD.PRIOR_SEASON_BAR), "families": {},
                 "swing_ok": {k: False for k, f in fams.items() if f.kind == "swing"}}

    return {
        "schema": SCHEMA,
        "generated_at": None,
        "verdict": "descriptive",
        "what": ("League Trends' false-trend calibration: per family, the real tests and R "
                 "seeded placebo shuffles at every weekly Sunday from the third Sunday of May, "
                 "as of each date, the bar chosen in code by the stated policy, and the live "
                 "season's held-out check."),
        "inputs": inputs,
        "policy": {
            "grid": list(GRID), "R": int(R_), "seed": int(SEED),
            "dates": "every Sunday from the third Sunday of May to the season's last game",
            "calibration_seasons": {g: list(v) for g, v in CAL_SEASONS.items()},
            "live_season": LIVE_SEASON,
            "count_floor": COUNT_FLOOR, "season_floor": SEASON_FLOOR,
            "season_real_min": SEASON_REAL_MIN,
            "strict": dict(POLICIES["strict"]), "looser": dict(POLICIES["looser"]),
            "held_out": {k: v for k, v in held["strict"].items()},
            "held_out_looser": {k: v for k, v in held["looser"].items()},
            "flag": ("|z / phi| at or above the bar and the size (the shrunk change, or the "
                     "change net of drift with no fit) at or above the family's floor"),
        },
        "bars": bars,
        "served": served,
        "placebo_sd": placebo_sd,
        "totals": totals,
        "false_per_day": totals["strict"]["false_per_day"],
        "changes": changes,
        "families": out_f,
        "shrink": {"seasons": {g: list(v) for g, v in PROD_SHRINK_SEASONS.items()},
                   "lab_seasons": lab_seasons, "fits": fits_prod,
                   "method": ("two-group prior: a point mass at no change with weight pi0 and "
                              "a normal spread tau; mix against the placebo's own selected "
                              "max-of-three null")},
        "mix_null": mix_null,
        "prior_season": prior,
        "pool": pool,
        "rd_band": rd_band,
        "league_env": env,
        "live_check": {"season": LIVE_SEASON, "as_of": live.get("_as_of"),
                       "families": dict(held["strict"].get("verdicts") or {})},
    }


# --------------------------------------------------------------------------- #
# league_env and the swing pool
# --------------------------------------------------------------------------- #
def league_env(seasons=LEAGUE_ENV_SEASONS, physics_dir: Optional[Path] = None) -> dict:
    """Four-seam mean velocity, ST and FS shares of typed pitches, as labelled
    in MLB's feed, and stolen-base attempts per club game, per completed
    season, from the pitch sidecar."""
    pdir = Path(physics_dir or TF.PHYSICS_DIR)
    out = {}
    for y in seasons:
        p = pd.read_parquet(TF._table(pdir, "pitches", y), columns=["pitch_type", "start_speed"])
        g = pd.read_parquet(TF._table(pdir, "games", y), columns=["game_pk", "sb", "cs"])
        pt = p["pitch_type"].astype("string")
        typed = pt.notna() & (pt.str.len() > 0)
        n_typed = int(typed.sum())
        ff = p.loc[(pt == "FF").fillna(False).to_numpy(), "start_speed"].astype("float64").dropna()
        st = int((pt == "ST").fillna(False).sum())
        fs = int((pt == "FS").fillna(False).sum())
        games = int(g["game_pk"].nunique())
        sb, cs = int(g["sb"].sum()), int(g["cs"].sum())
        out[str(y)] = {"ff_mph": _r(ff.mean(), 4), "ff_pitches": int(len(ff)),
                       "st_pct": _r(100.0 * st / n_typed, 4), "fs_pct": _r(100.0 * fs / n_typed, 4),
                       "typed_pitches": n_typed, "pitches": int(len(p)),
                       "games": games, "sb": sb, "cs": cs,
                       "sba_per_club_game": _r((sb + cs) / (2.0 * games), 5)}
    return {"source": "the pitch sidecar (.cache/pbp_physics), as labelled in MLB's feed",
            "attempts": "(SB + CS) / (2 x games), stolen_base_* as SB, caught_stealing_* and "
                        "pickoff_caught_stealing_* as CS, one count per runner event",
            "seasons": out}


def swing_pool(seasons=(2024, 2025, LIVE_SEASON)) -> dict:
    """The swing source and its receipts; raises SwingSeasonsMissing."""
    counts = TF.check_swing_seasons(seasons, source=TF.SWING_SOURCE)
    return {"source": TF.SWING_SOURCE, "label": TD.FAMILIES["bat_speed"].pool,
            "receipts": {str(s): c for s, c in sorted(counts.items())},
            "pinned": {str(s): v for s, v in TF.SWING_RECEIPTS[TF.SWING_SOURCE].items()}}


# --------------------------------------------------------------------------- #
# the run
# --------------------------------------------------------------------------- #
def fits_and_counts(key: str, tables: dict, dates: dict, scored: list, *,
                    R_: int = R) -> dict:
    """phi, shrink fits and counts for each scored season of one family, from
    its measured tables (season -> table) only."""
    fam = all_families()[key]
    real_by = {s: t[t["rep"] < 0] for s, t in tables.items()}
    pl_by = {s: t[t["rep"] >= 0] for s, t in tables.items()}
    rec = {"fam": fam, "seasons": {}, "phi_used": {}, "phi_seasons": {}, "fits": {}}
    for s in scored:
        if s not in tables:
            continue
        fs = [x for x in lab_fit_seasons(fam, s) if x in tables]
        if any(x >= s for x in fs):
            raise ValueError(f"{key}: a fit season of {s} is not before it: {fs}")
        phi = _pooled_placebo_sd(tables, fs) if fs else None
        phi = float(phi) if phi else 1.0
        fit = None
        if fam.size_floor is not None and fs:
            if fam.kind == "mix":
                fit = TD.shrink_fit_mix(real_by, pl_by, s, fs)
            else:
                fit = TD.shrink_fit(real_by, s, fs, phi=phi)
        rec["phi_used"][s], rec["phi_seasons"][s], rec["fits"][s] = phi, fs, fit
        rec["seasons"][s] = season_counts(tables[s], fam, fit, phi, dates[s], R_)
    return rec


def _sidecar_manifest(physics_dir: Optional[Path] = None) -> dict:
    p = Path(physics_dir or TF.PHYSICS_DIR) / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _measure_job(args) -> tuple:
    season, keys, lab_dir, refresh = args[:4]
    prior_keys = args[4] if len(args) > 4 else []
    meta = {}
    if keys:
        m = measure_season(season, keys, lab_dir=Path(lab_dir), refresh=refresh, log=print)
        meta = {k: v for k, v in m.items() if k != "tables"}
    if prior_keys:
        pm = measure_prior_season(season, prior_keys, lab_dir=Path(lab_dir), refresh=refresh,
                                  log=print)
        meta["prior_dates"] = pm["dates"]
    return season, {k: None for k in keys}, meta


def run(*, refresh: bool = False, jobs: int = 1, out: Optional[Path] = None,
        lab_dir: Path = LAB_DIR, log: Callable = print) -> dict:
    t_all = time.time()
    fams = all_families()
    # the swing source first: a missing season stops before any other work
    pool = swing_pool()
    log(f"  swing receipts: {pool['receipts']}")
    manifest = _sidecar_manifest()
    need = {}
    for k, f in fams.items():
        for s in needed_seasons(f):
            need.setdefault(s, []).append(k)

    # frames complete (plan precondition): the frame equals the sidecar season
    bad = []
    for s in sorted(set(need) | {LIVE_SEASON}):
        fr = TF.pitch_game_frame(s)
        why = _frame_ok(fr, manifest)
        if why:
            bad.append(why)
        del fr
    if bad:
        raise RuntimeError("calibration frames incomplete: " + "; ".join(bad))

    prior_plan = {}
    for k, f in TD.FAMILIES.items():
        if k in TD.PRIOR_EXCLUDED or f.kind == "mix":
            continue
        for s in PRIOR_SEASONS[calib_group(f)]:
            prior_plan.setdefault(s, []).append(k)

    def measure_all(plan: dict, pplan: Optional[dict] = None) -> dict:
        meta = {}
        pplan = pplan or {}
        work = [(s, sorted(plan.get(s, [])), str(lab_dir), refresh, sorted(pplan.get(s, [])))
                for s in sorted(set(plan) | set(pplan)) if plan.get(s) or pplan.get(s)]
        if jobs > 1 and len(work) > 1:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=int(jobs)) as ex:
                for s, _k, m in ex.map(_measure_job, work):
                    meta[s] = m
        else:
            for w in work:
                s, _k, m = _measure_job(w)
                meta[s] = m
        return meta

    meta = measure_all(need, prior_plan)
    tables = _load_tables(lab_dir, need)
    prior_tables = _load_tables(lab_dir, prior_plan, prefix="prior_")
    prior_dates_by = {s: meta[s]["prior_dates"] for s in prior_plan}
    for m in meta.values():
        m.pop("prior_dates", None)
    dates = {s: m["dates"] for s, m in meta.items()}

    # pass 1: choose bars on the calibration seasons
    per_family = {}
    for k, f in fams.items():
        g = calib_group(f)
        tb = {s: tables[s][k] for s in needed_seasons(f)}
        per_family[k] = fits_and_counts(k, tb, dates, list(CAL_SEASONS[g]))
    barred = sorted({k for k, rec in per_family.items() for pol in POLICIES
                     if choose(rec["seasons"], list(CAL_SEASONS[calib_group(rec["fam"])]),
                               pol) is not None})
    log(f"  families with a bar under a policy: {barred}")
    prior = prior_block(prior_tables, prior_dates_by, per_family)
    log(f"  prior-season mode, swing families meeting the strict policy at "
        f"{TD.PRIOR_SEASON_BAR:g}: {prior['swing_ok']}")

    # pass 2: the live season, for a family with a bar
    live_meta = measure_all({LIVE_SEASON: barred})
    meta.update(live_meta)
    live_tables = _load_tables(lab_dir, {LIVE_SEASON: barred})[LIVE_SEASON] if barred else {}
    dates[LIVE_SEASON] = live_meta[LIVE_SEASON]["dates"] if barred else []
    live = {"_as_of": live_meta.get(LIVE_SEASON, {}).get("covers_through")}
    for k in barred:
        f = fams[k]
        tb = {s: tables[s][k] for s in needed_seasons(f)}
        tb[LIVE_SEASON] = live_tables[k]
        rec = fits_and_counts(k, tb, dates, [LIVE_SEASON])
        live[k] = rec["seasons"][LIVE_SEASON]
        for fld in ("phi_used", "phi_seasons", "fits"):
            per_family[k][fld][LIVE_SEASON] = rec[fld][LIVE_SEASON]
    live_counts = {k: v for k, v in live.items() if not k.startswith("_")}

    recs = betting_records(BETTING_DOC.read_text(encoding="utf-8")) if BETTING_DOC.exists() \
        else {"5c-A": False, "5d": False, "5k": False, "5d_note": None}
    if recs["5c-A"] and recs["5d"] and recs["5k"]:
        rd = rd_band_measure()
    else:
        missing = [k for k in ("5c-A", "5d", "5k") if not recs[k]]
        rd = None
        log(f"  rd_band stays null: docs/diamond-betting.md lacks the {', '.join(missing)} "
            f"record or closure ({recs.get('5d_note') or 'see plan 4.3'})")
    inputs = {
        "frames": {str(s): {"content_key": m["content_key"], "games": m["games"],
                            "covers_through": m["covers_through"]}
                   for s, m in sorted(meta.items())},
        "sidecar_covers_through": manifest.get("covers_through"),
        "betting_records": recs,
        "lab_version": LAB_VERSION,
    }
    art = summarize({k: v for k, v in per_family.items()}, live=dict(live_counts, _as_of=live["_as_of"]),
                    env=league_env(), pool=pool, rd_band=rd, inputs=inputs, prior=prior)
    if rd is None:
        have = [k for k in ("5c-A", "5d", "5k") if recs[k]]
        lack = [k for k in ("5c-A", "5d", "5k") if not recs[k]]
        art["rd_band_note"] = (
            "null: docs/diamond-betting.md records " + (", ".join(have) or "none of the three")
            + " but not the " + ", ".join(lack) + " read or closure"
            + (f" ({recs['5d_note']})" if recs.get("5d_note") and "5d" in lack else "")
            + "; plan 4.3")
    art["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = Path(out or eval_path())
    write_artifact(art, path)
    log(f"  wrote {path} in {time.time() - t_all:.0f} s")
    return art


def rd_band_measure(seasons=RD_BAND_SEASONS) -> dict:
    """sigma_m: the pooled within-club-season SD of the per-game run margin
    over completed seasons, from the sidecar's final scores and club_by_game."""
    ss, n, k = 0.0, 0, 0
    for y in seasons:
        g = pd.read_parquet(TF._table(TF.PHYSICS_DIR, "games", y),
                            columns=["game_pk", "home_score", "away_score"])
        cm = TF.club_by_game(y)
        g = g[g["game_pk"].isin(list(cm))]
        home = g["game_pk"].map(lambda pk: cm[int(pk)]["home"])
        away = g["game_pk"].map(lambda pk: cm[int(pk)]["away"])
        m = (g["home_score"] - g["away_score"]).astype("float64")
        rows = pd.concat([pd.DataFrame({"club": home, "m": m}),
                          pd.DataFrame({"club": away, "m": -m})])
        dev = rows["m"] - rows.groupby("club")["m"].transform("mean")
        ss += float((dev ** 2).sum())
        n += len(rows)
        k += rows["club"].nunique()
    return {"sigma_m": _r(np.sqrt(ss / (n - k)), 5), "seasons": list(seasons), "n": n,
            "club_seasons": k}


def _load_tables(lab_dir: Path, plan: dict, prefix: str = "") -> dict:
    out = {}
    for s, keys in plan.items():
        md = _memo_dir(lab_dir, s)
        out[s] = {k: pd.read_parquet(md / f"{prefix}{k}.parquet") for k in keys}
    return out


def live_flag() -> bool:
    try:
        import importlib
        mod = importlib.import_module("league_trends_export")
        return bool(getattr(mod, "MLBSTATS_TRENDS_LIVE", False))
    except ImportError:
        return False


def eval_path() -> Path:
    """The preview path while League Trends is dark, data/ after the flip."""
    return EVAL_DATA if live_flag() else EVAL_PREVIEW


def write_artifact(art: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(art, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def artifact_digest(art: dict) -> str:
    """sha256 of the artifact without generated_at (the reproducibility key)."""
    a = {k: v for k, v in art.items() if k != "generated_at"}
    return hashlib.sha256(json.dumps(a, sort_keys=True).encode("utf-8")).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--refresh", action="store_true", help="re-measure, ignoring the memo")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--lab-dir", type=Path, default=LAB_DIR)
    a = ap.parse_args(argv)
    try:
        art = run(refresh=a.refresh, jobs=a.jobs, out=a.out, lab_dir=a.lab_dir)
    except TF.SwingSeasonsMissing as e:
        print(f"BLOCKER: other swing_pitches seasons {' '.join(str(s) for s in e.seasons)} ({e})")
        return 2
    except RuntimeError as e:
        print(f"refused, nothing written: {e}")
        return 2
    print(json.dumps({"served": art["served"], "bars": art["bars"],
                      "held_out": art["policy"]["held_out"]["verdicts"],
                      "phi": art["policy"]["held_out"]["phi"],
                      "digest": artifact_digest(art)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

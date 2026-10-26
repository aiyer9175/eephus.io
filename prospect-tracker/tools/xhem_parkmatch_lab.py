# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The one read of the park-matched xHEM+ part (docs/ebr-2026-09-30/EBR_GATE.md 11.12).

    python tools/xhem_parkmatch_lab.py --dry-run          # fixtures with nulls and planted
                                                          # signals, a temp dir only
    python -u tools/xhem_parkmatch_lab.py --run --out P   # THE READ, once (owner EW3-52)

Registered in 11.12 (owner decision EW3-52), committed alone before any number of the
part existed. It reads the swar preview (.cache/swar/preview/swar.json) the skill
look read, fWAR's park term per hitter-season (tools/xhem_park_terms.py), the frozen
shares b (xhem_parkmatch.B_FROZEN, equal to docs/ebr-2026-09-30/xhem_parkmatch_fit.json)
and, for the team guard, the cached stint exposures, standings and bWAR the look read
(tools/swar_lab.LabInputs). It scores, in this order:

  1. the read's cells (11.12.3): PM-rate and PM-total on the skill look's primary
     frame, base and target park-neutral batting runs (wRAA + P), the test value the
     base plus LAMBDA 0.5 times d_pm; every cell's floors print before any gap;
  2. the null and planted checks (11.12.5): N0, N1 (the twin), PL1, PL2;
  3. the park-pattern check and its controls (11.12.4): K0, K1, K2;
  4. what is reported beside with no weight: the as-built half part, the contrast,
     LAMBDA 1, 11.2.1's unadjusted frame, per-season gaps, the 2016 to 2018 block;
  5. the team guard (11.2.4), recorded, outside the flip condition.

WRITES only its record (--out, never under data/). The 2025 to 2026 holdout is never
read (11.12.7). A crash after scoring began is a STOP: no rerun, an owner question.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional

import numpy as np

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for _p in (str(ROOT), str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ewar_v3 as V3                     # noqa: E402
import swar_lab as L                     # noqa: E402
import swar_targets as T                 # noqa: E402
import xhem_park_terms as XP             # noqa: E402
import xhem_parkmatch as PM              # noqa: E402

LAB_VERSION = "xhem_parkmatch_lab/1"
REGISTRATION = "docs/ebr-2026-09-30/EBR_GATE.md 11.12 (owner decision EW3-52)"
DEFAULT_RECORD = ROOT / "docs" / "ebr-2026-09-30" / "xhem_parkmatch_eval.json"
LAMBDA = V3.XHEM_LAMBDA
SEED = L.SEED                    # 20261008, part 9.5's
PLANT_SEED = 20261026
DECIDING = L.PREDICTOR_SEASONS   # 2021 to 2024
EARLY = L.TRANSPORT_EARLY_SEASONS
PART_SEASONS = tuple(range(2016, 2027))
MARGIN = PM.NONINF_MARGIN
K_B1 = 537.0                     # B1 is not part of 11.12; the frozen batting k fills the slot
GUARD_KEY = "xpm"
DESCRIPTIVE = "descriptive: no verdict weight; claims nothing (part 8)"


def _p(log: Callable, *a) -> None:
    log(*a)


def _f(v, nd=4) -> str:
    return "None" if v is None or (isinstance(v, float) and not math.isfinite(v)) else f"{float(v):+.{nd}f}"


class LabInputs(L.LabInputs):
    """The look's inputs plus the park terms and the frozen shares."""

    def __init__(self):
        self._park = XP.ParkInputs()

    def park_rows(self, season: int) -> dict:
        return self._park.park_rows(int(season))

    def shares(self) -> Optional[dict]:
        return None if PM.B_FROZEN is None else dict(PM.B_FROZEN)

    def fit_record(self) -> Optional[dict]:
        return json.loads(XP.FIT_PATH.read_text(encoding="utf-8")) if XP.FIT_PATH.exists() else None


# --------------------------------------------------------------------------
# assembly (before scoring begins; a failure here is a STOP)
# --------------------------------------------------------------------------

def assemble(payload: dict, rows: dict, inputs, b: dict, log: Callable) -> dict:
    """Adds, in place, P, d_pm and the series departures to every hitter row of the
    part's seasons and returns {season: park_rows}. Same-season quantities only."""
    arms = {int(s): {int(h["mlbam"]): ((h.get("parts") or {}).get("batx") or {}).get("arm")
                     for h in blk.get("hitters") or []}
            for s, blk in (payload.get("seasons") or {}).items()}
    parks = {}
    for y in PART_SEASONS:
        if y not in rows:
            continue
        hit = rows[y][L.HIT]
        pr = inputs.park_rows(y)
        parks[y] = pr
        src = {m: {"d": r["d"].get("batx"), "pa": r.get("pa"), "arm": arms.get(y, {}).get(m),
                   "pb": r.get("pitcher_batter")}
               for m, r in hit.items() if r["d"].get("batx") is not None}
        dpm = PM.pm_deltas(src, pr["P"], b)
        for m, r in hit.items():
            r["P"] = pr["P"].get(m)
            d = dpm.get(m)
            r["d"]["pm"] = d
            r["d"][GUARD_KEY] = None if d is None else LAMBDA * d
            r["arm"] = arms.get(y, {}).get(m)
        s = sum(v for v in dpm.values())
        _p(log, f"  assembled {y}: {len(hit)} hitters, {len(dpm)} with the part, park terms {len(pr['P'])}, "
                f"sum d_pm {s:+.2e} runs")
        if abs(s) > 1e-6:
            raise L.LabStop(f"{y}: d_pm sums to {s}, not 0")
    return parks


def pairs(rows: dict, seasons, frame: str) -> list[dict]:
    """(Y, Y+1) pairs at 200 PA in both seasons (2020 out on both sides). frame
    "pn": base and target park-neutral batting runs (wRAA + P); "raw": 11.2.1's
    unadjusted wRAA. Tests: pm (LAMBDA d_pm), asb (LAMBDA d_batx), pm1 (d_pm),
    zero (the base)."""
    out = []
    for y in seasons:
        y = int(y)
        if y == L.EXCLUDED_SEASON or y + 1 == L.EXCLUDED_SEASON:
            continue
        a, b = (rows.get(y) or {}).get(L.HIT) or {}, (rows.get(y + 1) or {}).get(L.HIT) or {}
        for m in sorted(a):
            if m not in b:
                continue
            r0, r1 = a[m], b[m]
            if r0.get("pitcher_batter") or r1.get("pitcher_batter"):
                continue
            n0, n1 = r0.get("pa"), r1.get("pa")
            if not (L._at_floor(n0, L.HIT) and L._at_floor(n1, L.HIT)):
                continue
            w0, w1, dpm, dbx = r0.get("wraa"), r1.get("wraa"), r0["d"].get("pm"), r0["d"].get("batx")
            if w0 is None or w1 is None or dpm is None or dbx is None:
                continue
            if frame == "pn":
                if r0.get("P") is None or r1.get("P") is None:
                    continue
                b0, tgt = w0 + r0["P"], w1 + r1["P"]
            else:
                b0, tgt = w0, w1
            out.append({"mlbam": m, "y": y, "n0": float(n0), "n1": float(n1), "b0": float(b0),
                        "tgt": float(tgt), "b0r": None, "m": 0.0, "d_pm": float(dpm),
                        "tests": {"pm": b0 + LAMBDA * dpm, "asb": b0 + LAMBDA * dbx,
                                  "pm1": b0 + dpm, "zero": b0}})
    return out


def plant(prs: list[dict]) -> None:
    """PL1 and PL2 (11.12.5) in place: u = sd(d_pm) * (z + e) / sd(z + e), z the
    within-outcome-season z of (target rate - base rate), e standard normal noise."""
    if not prs:
        return
    resid = [p["tgt"] / p["n1"] - p["b0"] / p["n0"] for p in prs]
    z = L.zscore_within([p["y"] + 1 for p in prs], resid)
    e = np.random.default_rng(PLANT_SEED).standard_normal(len(prs))
    v = z + e
    sd_v = float(np.std(v, ddof=1)) or 1.0
    sd_d = float(np.std([p["d_pm"] for p in prs], ddof=1))
    u = sd_d * v / sd_v
    for p, ui in zip(prs, u):
        p["tests"]["pl1"] = p["b0"] + LAMBDA * float(ui)
        p["tests"]["pl2"] = p["b0"] - LAMBDA * float(ui)


def _cell_record(rec: dict) -> dict:
    keep = ("part", "cell", "kind", "n_pairs", "n_players", "floors", "rho_test", "rho_b0", "gap", "lo95",
            "hi95", "lo90", "hi90", "p_one_sided", "twin_gap", "twin_lo95", "twin_hi95", "v1_gap", "v1_lo95",
            "v1_hi95", "v1_sign_agrees", "pearson_gap_v2", "per_system")
    out = {k: rec.get(k) for k in keep}
    out["lower_bound"] = rec.get("lo90")
    out["non_inferior"] = bool(rec.get("lo90") is not None and rec["lo90"] > -MARGIN)
    return out


def score_cells(spec: list[tuple], boot: int, log: Callable, label: str) -> dict:
    """spec [(name, kind, pairs, key)]: every cell prepared (floors printed), then
    finished (gaps printed)."""
    prepped = {}
    for name, kind, prs, key in spec:
        prepped[name] = L.prep_primary("batting (park-matched)", name, [("park-neutral", prs, key)], kind,
                                       K_B1, boot, SEED, SEED + 1)
    _p(log, f"[{label}] FLOORS (convention v2, B = {boot}; MDE95 = 1.645 sd; no gap is printed here)")
    for name, rec in prepped.items():
        fl = rec.get("floors") or {}
        _p(log, f"  {name:14s} n {rec.get('n_pairs', 0):5d}  sd {_f(fl.get('sd'))}  half-width "
                f"{_f(fl.get('half_width95'))}  MDE95 {_f(fl.get('mde95'))}")
    out = {}
    for name, rec in prepped.items():
        fin = L.finish_primary(rec)
        cell = _cell_record(fin)
        d2 = fin.get("_draws", {}).get("v2") if isinstance(fin.get("_draws"), dict) else None
        if d2 is not None:
            g = L.gap_summary(d2["test"], d2["twin"])
            cell["over_twin"] = {"gap": (None if fin.get("rho_test") is None or fin.get("rho_twin") is None
                                         else fin["rho_test"] - fin["rho_twin"]),
                                 "lo95": g["lo95"], "hi95": g["hi95"]}
        out[name] = cell
        _p(log, f"  {name:14s} gap {_f(cell['gap'])} [95: {_f(cell['lo95'])} to {_f(cell['hi95'])}] lower bound "
                f"(5th pct) {_f(cell['lower_bound'])} => {'NON-INFERIOR' if cell['non_inferior'] else 'not non-inferior'}"
                f"; v1 gap {_f(cell['v1_gap'])}; twin gap {_f(cell['twin_gap'])}")
    return out


# --------------------------------------------------------------------------
# the park-pattern check (11.12.4)
# --------------------------------------------------------------------------

def club_rows(rows: dict, parks: dict, value: Callable) -> list[dict]:
    """[{season, club, pf_pts, c}] for every club-season of the part's seasons,
    c the club total of value(row) (wins) by stint PA."""
    out = []
    for y, pr in sorted(parks.items()):
        hit = rows[y][L.HIT]
        x = {}
        for m, r in hit.items():
            v = value(r)
            if v is not None:
                x[m] = v
        for club, c in PM.club_changes(x, pr["stints"]).items():
            if club in pr["pf"]:
                out.append({"season": int(y), "club": club, "pf_pts": 100.0 * (pr["pf"][club] - 1.0), "c": c})
    return out


def slope_interval(clubs: list[dict], boot: int = PM.SLOPE_BOOT, seed: int = PM.SLOPE_SEED) -> dict:
    """The slope's 95 percent interval, franchises (clubs) drawn with all their club-seasons."""
    by: dict = {}
    for r in clubs:
        by.setdefault(r["club"], []).append(r)
    keys = sorted(by)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(boot):
        pick = rng.integers(0, len(keys), len(keys))
        rs = [r for k in pick for r in by[keys[k]]]
        s = PM.ols_slope([r["pf_pts"] for r in rs], [r["c"] for r in rs])
        if s is not None:
            draws.append(s)
    if len(draws) < 10:
        return {"lo95": None, "hi95": None, "n_draws": len(draws)}
    a = np.sort(np.asarray(draws))
    return {"lo95": float(a[int(0.025 * len(a))]), "hi95": float(a[max(0, int(0.975 * len(a)) - 1)]),
            "n_draws": len(a)}


def park_check(rows: dict, parks: dict, log: Callable) -> dict:
    def rpw(r):
        return float(r.get("rpw") or 0.0) or None

    series = {
        "part": lambda r: (None if r["d"].get("pm") is None or not rpw(r) else LAMBDA * r["d"]["pm"] / rpw(r)),
        "K0_zero": lambda r: 0.0,
        "K1_as_built": lambda r: (None if r["d"].get("batx") is None or not rpw(r)
                                  else LAMBDA * r["d"]["batx"] / rpw(r)),
        "K2_park_planted_back": lambda r: (None if r["d"].get("pm") is None or not rpw(r)
                                           else LAMBDA * (r["d"]["pm"] + float(r.get("P") or 0.0)) / rpw(r)),
    }
    out = {}
    for name, fn in series.items():
        allc = club_rows(rows, parks, fn)
        deciding = [r for r in allc if r["season"] in PM.CHECK_SEASONS]
        res = PM.park_pattern(deciding)
        res["slope_interval95"] = slope_interval(deciding) if name == "part" else None
        early = [r for r in allc if r["season"] not in PM.CHECK_SEASONS]
        res["beside_2016_to_2020"] = {"n_club_seasons": len(early),
                                      "slope": PM.ols_slope([r["pf_pts"] for r in early], [r["c"] for r in early]),
                                      "label": "in-fit (2016 to 2019) and short (2020) seasons; no weight"}
        if name == "part":
            res["club_seasons"] = [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()}
                                   for r in allc]
        out[name] = res
        _p(log, f"  {name:22s} slope {_f(res['slope'])} wins per PF point on {res['n_club_seasons']} club-seasons "
                f"(tolerance {PM.SLOPE_TOL}); "
                + "; ".join(f"{p['park']} mean {_f(p['mean'], 3)} band {_f(p['band'], 3)} n {p['n']}"
                            for p in res["named"])
                + f"; PASS {res['pass']}")
    ok = out["part"]
    controls = {
        "K0": bool(out["K0_zero"]["slope"] == 0.0),
        "K1": bool(out["K1_as_built"]["slope"] is not None and not out["K1_as_built"]["slope_inside"]),
        "K2": bool(out["K2_park_planted_back"]["slope"] is not None
                   and not out["K2_park_planted_back"]["slope_inside"]),
    }
    _p(log, f"  part slope 95 percent interval (club-clustered, reported): {_f(ok['slope_interval95']['lo95'])} "
            f"to {_f(ok['slope_interval95']['hi95'])}; controls {controls}")
    return {"series": out, "controls": controls, "pass": bool(ok["pass"]), "controls_hold": all(controls.values())}


# --------------------------------------------------------------------------
# the read
# --------------------------------------------------------------------------

def run(inputs, boot: int = L.BOOT, log: Callable = print, fail_after_scoring: bool = False) -> dict:
    today = _dt.date.today()
    b = inputs.shares()
    fit = inputs.fit_record()
    if b is None or fit is None:
        raise L.LabStop("the shares b are not frozen with their fit log (11.12.2): run tools/xhem_park_terms.py --fit")
    if {k: round(float(v), 6) for k, v in b.items()} != {k: round(float(v), 6) for k, v in (fit.get("b") or {}).items()}:
        raise L.LabStop(f"xhem_parkmatch.B_FROZEN {b} is not the fit log's {fit.get('b')}")
    payload = inputs.preview()
    L.check_preview(payload, list(PART_SEASONS), inputs.vintage_id())
    rows = L.season_rows(payload)
    _p(log, f"xhem_parkmatch_lab {LAB_VERSION} on {today.isoformat()}: preview vintage "
            f"{payload.get('fwar_vintage_id')}, generated {payload.get('generated_at')}; b {json.dumps(b, sort_keys=True)}; "
            f"LAMBDA {LAMBDA}; seed {SEED}, B {boot}")
    parks = assemble(payload, rows, inputs, b, log)
    prs = pairs(rows, DECIDING, "pn")
    raw = pairs(rows, DECIDING, "raw")
    early = pairs(rows, EARLY, "pn")
    plant(prs)
    team_exp = inputs.team_exposure()
    standings = inputs.standings(range(min(DECIDING), max(DECIDING) + 2))
    bwar = inputs.bwar()
    meta = inputs.input_meta() if hasattr(inputs, "input_meta") else {}
    _p(log, f"inputs (read only, never fetched): {json.dumps(meta, sort_keys=True, default=str)[:4000]}")
    _p(log, f"[read] frame: deciding pairs {len(prs)} (Y 2021 to 2024), unadjusted frame {len(raw)}, "
            f"2016 to 2018 block {len(early)}")
    started = False
    try:
        started = True
        cells = score_cells([("PM-rate", L.RATE, prs, "pm"), ("PM-total", L.CUM, prs, "pm")], boot, log, "read")
        if fail_after_scoring:
            raise RuntimeError("injected failure after scoring began (dry run)")
        checks_c = score_cells([("N0-rate", L.RATE, prs, "zero"), ("N0-total", L.CUM, prs, "zero"),
                                ("PL1-rate", L.RATE, prs, "pl1"), ("PL2-rate", L.RATE, prs, "pl2")],
                               boot, log, "null and planted")
        n0 = bool(checks_c["N0-rate"]["gap"] == 0.0 and checks_c["N0-total"]["gap"] == 0.0)
        ot = cells["PM-rate"].get("over_twin") or {}
        n1 = bool(ot.get("lo95") is not None and ot["lo95"] > 0)
        pl1 = bool(checks_c["PL1-rate"]["lower_bound"] is not None and checks_c["PL1-rate"]["lower_bound"] > 0)
        pl2 = bool(not checks_c["PL2-rate"]["non_inferior"])
        checks = {"N0": n0, "N1": n1, "PL1": pl1, "PL2": pl2}
        _p(log, f"[null and planted] N0 {n0}; N1 (PM over its twin, rate) gap {_f(ot.get('gap'))} lo95 "
                f"{_f(ot.get('lo95'))} => {n1}; PL1 {pl1}; PL2 {pl2}")
        _p(log, "[park pattern] (11.12.4; deciding seasons 2021 to 2026, out of the fit)")
        park = park_check(rows, parks, log)
        _p(log, f"[beside] {DESCRIPTIVE}")
        beside = score_cells([("as-built-rate", L.RATE, prs, "asb"), ("as-built-total", L.CUM, prs, "asb"),
                              ("PM-rate-L1", L.RATE, prs, "pm1"), ("PM-total-L1", L.CUM, prs, "pm1"),
                              ("raw-PM-rate", L.RATE, raw, "pm"), ("raw-as-built-rate", L.RATE, raw, "asb"),
                              ("early-PM-rate", L.RATE, early, "pm"), ("early-PM-total", L.CUM, early, "pm")],
                             boot, log, "beside")
        contrast = L.contrast_frames([("park-neutral", prs, "pm")], "asb", boot, SEED, K_B1)
        _p(log, f"  contrast PM minus as-built (rate, same draws): {_f(contrast.get('gap'))} "
                f"[{_f(contrast.get('lo95'))} to {_f(contrast.get('hi95'))}]")
        per_season = {}
        for y in DECIDING:
            sub = [p for p in prs if p["y"] == y]
            per_season[str(y)] = {"n_pairs": len(sub),
                                  "pm_rate": L.point_gap_frames([("pn", sub, "pm")], L.RATE, K_B1),
                                  "as_built_rate": L.point_gap_frames([("pn", sub, "asb")], L.RATE, K_B1)}
        _p(log, "  per-season rate gaps (point): " + "; ".join(
            f"{y} n {v['n_pairs']} PM {_f(v['pm_rate'])} as-built {_f(v['as_built_rate'])}" for y, v in per_season.items()))
        L.GUARD_SERIES[GUARD_KEY] = (L.HIT, GUARD_KEY, T.OUTCOMES_HIT)
        guards = L.team_guards(rows, DECIDING, "hr_fwar", team_exp, standings, bwar, (GUARD_KEY,), boot, log,
                               "guard (recorded; not in the flip condition)")
    except Exception as exc:  # noqa: BLE001
        if started:
            _p(log, f"VOID: an exception after scoring began ({type(exc).__name__}: {exc}); STOP, no rerun "
                    "(11.12.5), an owner question")
            return {"status": "VOID", "error": f"{type(exc).__name__}: {exc}", "lab_version": LAB_VERSION,
                    "registration": REGISTRATION, "run_on": today.isoformat()}
        raise
    noninf = bool(cells["PM-rate"]["non_inferior"] and cells["PM-total"]["non_inferior"])
    valid = all(checks.values()) and park["controls_hold"]
    if not valid:
        result = "INVALID"
    elif noninf and park["pass"]:
        result = "PASS"
    else:
        result = "NOT PASS"
    g = guards.get(GUARD_KEY) or {}
    _p(log, f"[result] PM-rate {'NON-INFERIOR' if cells['PM-rate']['non_inferior'] else 'not non-inferior'}, "
            f"PM-total {'NON-INFERIOR' if cells['PM-total']['non_inferior'] else 'not non-inferior'}; park pattern "
            f"{'PASS' if park['pass'] else 'FAIL'}; checks {checks}; controls {park['controls']}; team guard "
            f"{'NON-INFERIOR' if g.get('non_inferior') else 'NOT NON-INFERIOR'} (recorded, not in the flip "
            f"condition) => {result} (11.12.7)")
    return {
        "status": "SCORED", "result": result, "lab_version": LAB_VERSION, "registration": REGISTRATION,
        "run_on": today.isoformat(), "lambda": LAMBDA, "b": b, "seed": SEED, "boot": boot,
        "fit": {"path": "docs/ebr-2026-09-30/xhem_parkmatch_fit.json", "b": fit.get("b"),
                "fitted_at": fit.get("fitted_at")},
        "preview": {"generated_at": payload.get("generated_at"), "fwar_vintage_id": payload.get("fwar_vintage_id"),
                    "sha256": T.sha256_of(L.PREVIEW_PATH) if hasattr(T, "sha256_of") else None},
        "frame": {"deciding": list(DECIDING), "pairs": len(prs), "floor_pa": L.MIN_PA,
                  "base_target": "park-neutral batting runs, wRAA + P (11.12.3)"},
        "cells": cells, "non_inferior": noninf,
        "null_and_planted": {"checks": checks, "cells": checks_c},
        "park_pattern": park,
        "beside": {"weight": DESCRIPTIVE, "cells": beside, "contrast_pm_minus_as_built_rate": contrast,
                   "per_season_rate_gaps": per_season},
        "team_guard": {"weight": "recorded; not in EW3-52's flip condition (11.12.3)",
                       "non_inferior": bool(g.get("non_inferior")), "underpowered": bool(g.get("underpowered")),
                       "outcomes": {k: {kk: vv for kk, vv in v.items() if kk in ("n_club_seasons", "dT", "non_inferior")}
                                    | {"player_lower": (v.get("player") or {}).get("lower"),
                                       "club_lower": (v.get("club") or {}).get("lower"),
                                       "player_half_width95": (v.get("player") or {}).get("half_width95"),
                                       "club_half_width95": (v.get("club") or {}).get("half_width95")}
                                    for k, v in (g.get("outcomes") or {}).items()}},
        "holdout": "not read (11.12.7): S1x's 2025 to 2026 holdout stands as S1x's",
    }


def _clean(v):
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items() if not str(k).startswith("_")}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, (np.floating,)):
        v = float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, float):
        return None if not math.isfinite(v) else round(v, 6)
    return v


def write_record(rec: dict, path: Path) -> Path:
    L._refuse_out(path)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_clean(rec), indent=1, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# the dry run: fixtures with nulls and planted signals, a temporary directory only
# --------------------------------------------------------------------------

FIX_CLUBS = tuple(range(108, 122)) + tuple(range(133, 149))
FIX_SHARE = 0.44


class FixtureInputs(L.FixtureLabInputs):
    """swar_lab's synthetic league (nulls included) with park terms: 30 clubs, two of
    them the named parks, every hitter on one club; the as-built arm carries a
    planted double charge FIX_SHARE * P so the fit, K1 and the part can be checked."""

    def __init__(self, seed: int = 7):
        super().__init__(seed=seed)
        rng = np.random.default_rng(seed + 100)
        self._pf = {}
        self._parks = {}
        for y in range(2016, 2027):
            pf = {c: float(1.0 + rng.normal(0, 0.06)) for c in FIX_CLUBS}
            pf[115] = 1.13
            if y >= 2025:
                pf[133] = 1.075
            self._pf[y] = pf
        for s, blk in self._payload["seasons"].items():
            y = int(s)
            stints, P = {}, {}
            for k, h in enumerate(blk["hitters"]):
                club = FIX_CLUBS[k % len(FIX_CLUBS)]
                bx = h["parts"]["batx"]
                bx["arm"] = "xhem" if h["pa"] >= 200 else "hem"
                p_i = PM.park_term([(float(h["pa"]), self._pf[y][club])], 0.12)
                if not (k == 17 and y == 2019):   # else a hitter with no stint: no park term (a null)
                    stints[h["mlbam"]] = [(club, float(h["pa"]))]
                    P[h["mlbam"]] = p_i
                if bx.get("d") is not None and not h.get("pitcher_batter"):
                    bx["g"] = float(bx["d"]) + FIX_SHARE * p_i
                    bx["d"] = bx["g"]
            # re-centre the planted as-built d per season, as the preview stores it
            hs = [h for h in blk["hitters"] if h["parts"]["batx"].get("d") is not None and not h.get("pitcher_batter")]
            tot_pa = sum(h["pa"] for h in hs)
            c = sum(h["parts"]["batx"]["d"] for h in hs) / tot_pa
            for h in hs:
                h["parts"]["batx"]["d"] -= h["pa"] * c
            self._parks[y] = {"pf": self._pf[y], "stints": stints, "P": P, "no_factor": [], "lg_r_pa": 0.12}
        self._b = None

    def park_rows(self, season):
        return self._parks[int(season)]

    def shares(self):
        return self._b

    def fit_record(self):
        return None if self._b is None else {"b": self._b, "fitted_at": "fixture"}


def dry_run(log: Callable = print, boot: int = 200, tmp_dir: Optional[Path] = None) -> dict:
    """Every path on fixtures with nulls and planted signals: the fit recovers the
    planted share, the read scores, the checks and controls hold, a crash after
    scoring began reads VOID, and the record is written to a temp dir only."""
    tmp = Path(tmp_dir) if tmp_dir else Path(tempfile.mkdtemp(prefix="xhem_pm_dry_"))
    _p(log, f"DRY RUN in {tmp} (fixtures with nulls; nothing real is scored)")
    inp = FixtureInputs()
    # a fixture row with PA and no park term stops the fit (the registered stop)
    try:
        XP.fit(_FitAdapter(inp), log=lambda *a: None)
        raise AssertionError("a hitter with PA and no park term must stop the fit")
    except PM.ParkMatchStop:
        pass
    inp._parks[2019]["P"][inp._payload["seasons"]["2019"]["hitters"][17]["mlbam"]] = 0.0
    inp._parks[2019]["stints"][inp._payload["seasons"]["2019"]["hitters"][17]["mlbam"]] = []
    fit = XP.fit(_FitAdapter(inp), log=log)
    assert abs(fit["b"]["xhem"] - FIX_SHARE) < 0.15, fit["b"]
    inp._b = dict(fit["b"])
    rec = run(inp, boot=boot, log=log)
    assert rec["status"] == "SCORED", rec
    assert rec["null_and_planted"]["checks"]["N0"] and rec["null_and_planted"]["checks"]["PL1"]
    assert rec["null_and_planted"]["checks"]["PL2"], rec["null_and_planted"]
    assert rec["park_pattern"]["controls"]["K0"] and rec["park_pattern"]["controls"]["K2"]
    assert rec["result"] in ("PASS", "NOT PASS", "INVALID")
    out = write_record(rec, tmp / "xhem_parkmatch_eval.json")
    void = run(_with_b(FixtureInputs(), fit["b"], inp), boot=50, log=lambda *a: None, fail_after_scoring=True)
    assert void["status"] == "VOID", void
    _p(log, f"DRY RUN OK: result {rec['result']} on fixtures; VOID path OK; record {out}")
    return rec


def _with_b(fx: "FixtureInputs", b: dict, like: "FixtureInputs") -> "FixtureInputs":
    fx._parks = like._parks
    fx._payload = like._payload
    fx._b = dict(b)
    return fx


class _FitAdapter:
    """tools/xhem_park_terms.fit's inputs off a fixture."""

    def __init__(self, fx: FixtureInputs):
        self.fx = fx

    def preview(self):
        return self.fx.preview()

    def park_rows(self, season):
        return self.fx.park_rows(season)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--out", default=str(DEFAULT_RECORD))
    a = ap.parse_args(argv)
    if a.dry_run:
        dry_run()
        return 0
    if a.run:
        out = Path(a.out)
        if out.exists():
            print(f"REFUSED: {out} exists; the read runs once (11.12.7)")
            return 2
        try:
            rec = run(LabInputs())
        except (L.LabStop, PM.ParkMatchStop) as e:
            print(f"STOP before scoring: {e}")
            return 2
        write_record(rec, out)
        print(f"wrote {out}")
        return 0 if rec.get("status") == "SCORED" else 3
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

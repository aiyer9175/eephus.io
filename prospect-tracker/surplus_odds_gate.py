# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""SURPLUS-ODDS GATE: the one registered read (docs/efv-2026-09-25/SURPLUS_ODDS_GATE.md).

Question: should the eFV surplus fan and mean at the three Platt seams be drawn from the
row's SERVED (calibrated) outcome odds, so P(bust) and the dollar range are one object
(candidate), instead of from the raw curve at the display grade (incumbent)?

Frame (gate section 3): the eFV resolved matrix, forward-chained over test decision years
2016-2019 exactly as efv_score.run prices a row, with the realized surplus built by
surplus_backtest_real's rules and valued at the live flat $/WAR (the served unit).

PROSPECT_ANCHOR guard: every statistic is POOLED. Nothing here is computed by consensus-FV
cell, band or tier, and backtest.run_backtest (which always builds by_fv_tier) is never
called. The scorer is calibration_metrics(); test_surplus_odds_gate.py pins that neither
it nor the artifact carries an FV or tier stratum.

Writes one block, `surplus_odds_gate`, inside the parent artifact
data/surplus_backtest_real.json (the prospect_surplus row's eval; a failed challenger is
a block in its parent, never a standalone *_eval.json). Moves no served number:
the flag it adjudicates, efv_score.SURPLUS_FROM_SERVED_ODDS_DEFAULT, is flipped by hand
only on a pass inside the landing rule.

Run once: python surplus_odds_gate.py
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

import value_framework as vf

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "surplus_backtest_real.json"   # the parent artifact
BLOCK_KEY = "surplus_odds_gate"
GATE_DOC = "docs/efv-2026-09-25/SURPLUS_ODDS_GATE.md"

# Registered constants (gate sections 3 to 5). Not arguments: the read takes none.
GATE_YEARS = (2016, 2017, 2018, 2019)
MIN_TRAIN, MIN_TEST = 60, 10          # efv_reliability's chain floors
PRICE_ETA = 1.0                       # efv_score.run's re-price timing
N_DRAWS = 4000
BOOT_B = 2000
SEED = 20260930
COVERAGE_TARGET = 0.80
PIT_LO, PIT_HI = 0.10, 0.90
MIN_FRAME_N = 200
LANDING_BEFORE = date(2026, 10, 4)


# ---------------------------------------------------------------------------
# reserved-frame guard
# ---------------------------------------------------------------------------

def assert_reserved_frames_untouched(years=GATE_YEARS) -> None:
    """No decision year inside or after the reserved list vintages is read."""
    import efv_vintage_frame as vfr
    for y in years:
        vfr.guard_score_request(int(y), purpose="surplus odds gate")
        if int(y) >= min(vfr.RESERVED_LV):
            raise AssertionError(f"decision year {y} reaches the reserved vintages")


# ---------------------------------------------------------------------------
# the served dollar map, vectorized (identical to vf.apply_calibration)
# ---------------------------------------------------------------------------

def calibrate_mm(x_mm):
    """vf.apply_calibration over an array, in the map's own unit (VAL_1 scale s)."""
    x = np.asarray(x_mm, dtype=float)
    cal = vf._config().get("calibration", {})
    if not cal.get("enabled"):
        return x
    s = vf.calibration_level_scale()
    if str(cal.get("method", "linear")).lower() == "isotonic":
        iso = cal.get("isotonic", {})
        xs = [float(v) for v in iso.get("x_mm", [])]
        ys = [float(v) for v in iso.get("y_mm", [])]
        if len(xs) >= 2 and len(xs) == len(ys):
            return np.interp(x / s, xs, ys) * s
        return x
    lin = cal.get("linear", {})
    return (float(lin.get("slope", 1.0)) * (x / s) + float(lin.get("intercept_mm", 0.0))) * s


# ---------------------------------------------------------------------------
# the scorer: pooled, no strata
# ---------------------------------------------------------------------------

def randomized_pit(draws_mm, y_mm: float, u: float, floor_mm: float) -> float:
    """Randomized PIT of one realized value under the arm's calibrated draws.

    The served map sends the raw bust atom to floor_mm, so a realized value at or below
    it is the bust event: PIT = u * F(floor). Otherwise F(y-) + u * (F(y) - F(y-))."""
    d = np.asarray(draws_mm, dtype=float)
    n = float(len(d))
    if y_mm <= floor_mm + 1e-9:
        return float(u * (d <= floor_mm + 1e-9).sum() / n)
    below = float((d < y_mm).sum()) / n
    at = float((d <= y_mm).sum()) / n
    return below + u * (at - below)


def _ols(x, y) -> tuple[float, float]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    vx = float(((x - x.mean()) ** 2).sum())
    if len(x) < 2 or vx <= 0:
        return float("nan"), float("nan")
    b = float(((x - x.mean()) * (y - y.mean())).sum()) / vx
    return b, float(y.mean() - b * x.mean())


def calibration_metrics(pred_mm, realized_mm, pit) -> dict:
    """Pooled bias, OLS slope and intercept of realized on predicted, PIT coverage of the
    registered band and the PIT KS statistic. One pooled block, never stratified."""
    from scipy import stats
    p = np.asarray(pred_mm, dtype=float)
    r = np.asarray(realized_mm, dtype=float)
    q = np.asarray(pit, dtype=float)
    slope, intercept = _ols(p, r)
    return {
        "n": int(len(p)),
        "bias_mm": float((r - p).mean()) if len(p) else float("nan"),
        "slope": slope,
        "intercept_mm": intercept,
        "pit_coverage": float(((q >= PIT_LO) & (q <= PIT_HI)).mean()) if len(q) else float("nan"),
        "pit_ks_stat": float(stats.kstest(q, "uniform").statistic) if len(q) >= 3 else float("nan"),
    }


def _gaps(inc: dict, cand: dict) -> dict:
    return {
        "D_cov": abs(inc["pit_coverage"] - COVERAGE_TARGET) - abs(cand["pit_coverage"] - COVERAGE_TARGET),
        "H_bias": abs(cand["bias_mm"]) - abs(inc["bias_mm"]),
        "H_slope": abs(cand["slope"] - 1.0) - abs(inc["slope"] - 1.0),
    }


def paired_bootstrap(keys, realized, pred_inc, pit_inc, pred_cand, pit_cand,
                     *, b: int = BOOT_B, seed: int = SEED) -> dict:
    """Player-clustered paired bootstrap of the three registered gaps (percentile CI95)."""
    realized = np.asarray(realized, dtype=float)
    arrs = [np.asarray(a, dtype=float) for a in (pred_inc, pit_inc, pred_cand, pit_cand)]
    groups: dict[str, list[int]] = {}
    for i, k in enumerate(keys):
        groups.setdefault(k, []).append(i)
    members = list(groups.values())
    rng = np.random.RandomState(seed)
    draws = {"D_cov": [], "H_bias": [], "H_slope": []}
    for _ in range(int(b)):
        pick = rng.randint(0, len(members), len(members))
        idx = np.fromiter((j for g in pick for j in members[g]), dtype=int)
        inc = calibration_metrics(arrs[0][idx], realized[idx], arrs[1][idx])
        cand = calibration_metrics(arrs[2][idx], realized[idx], arrs[3][idx])
        for k, v in _gaps(inc, cand).items():
            draws[k].append(v)
    out = {}
    for k, v in draws.items():
        a = np.asarray(v, dtype=float)
        out[k] = {"ci95": [float(np.quantile(a, 0.025)), float(np.quantile(a, 0.975))],
                  "boot_mean": float(a.mean())}
    out["B"] = int(b)
    out["seed"] = int(seed)
    out["clusters"] = len(members)
    return out


def verdict(inc: dict, cand: dict, boot: dict, *, one_object_ok: bool, n: int) -> dict:
    """The registered pass rule (gate section 5)."""
    if not one_object_ok:
        return {"verdict": "STOPPED", "reason": "G1 one-object check failed (a bug, not a result)"}
    if n < MIN_FRAME_N:
        return {"verdict": "UNPOWERED", "reason": f"frame n {n} < {MIN_FRAME_N}"}
    g = _gaps(inc, cand)
    clauses = {
        "G1_one_object": True,
        "G2_coverage": bool(g["D_cov"] > 0 and boot["D_cov"]["ci95"][0] > 0),
        "G3_bias_no_harm": bool(boot["H_bias"]["ci95"][0] <= 0),
        "G4_slope_no_harm": bool(boot["H_slope"]["ci95"][0] <= 0),
    }
    return {"verdict": "PASS" if all(clauses.values()) else "FAIL", "clauses": clauses,
            "point": g}


# ---------------------------------------------------------------------------
# the frame (gate section 3)
# ---------------------------------------------------------------------------

def _side_rows(side: str) -> tuple[list[dict], list[dict]]:
    """Forward-chained test rows for one side, priced as efv_score.run prices them."""
    import efv_odds_calibration as oc
    from efv_dataset import matrix_path, TARGET_SEASONS
    from efv_model import (_prep, _feature_spec, _fit_ridge, _predict, _fit_ols_fv,
                           _pred_ols, blend_lambda)
    from efv_score import _age_at, _grade_map_age, apply_dispersion_correction
    from prospect_path import _fit_linear_calibration

    is_pit = side == "pit"
    keys, _mono = _feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    data = _prep(pool, "target_censored", side)
    by_key = {r["player_key"]: r for r in pool}
    lam = float(blend_lambda(side))
    out, folds = [], []
    for yr in GATE_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        fold = {"side": side, "decision_year": yr, "n_train": len(tr), "n_test": len(te)}
        if len(te) < MIN_TEST or len(tr) < MIN_TRAIN:
            fold["skipped"] = "below chain floor"
            folds.append(fold)
            continue
        ridge = _fit_ridge(tr, keys)
        if not ridge:
            fold["skipped"] = "ridge fit failed"
            folds.append(fold)
            continue
        cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        ols = _fit_ols_fv(tr)
        priced = []
        for r in te:
            pk = r["player_key"]
            src = by_key[pk]
            model_war = max(-2.0, a + b * _predict(ridge, r["feats"]))
            pos = src.get("position")
            dyear = src.get("debut_year") or 2020
            age = _age_at(src.get("birth_date"), dyear)
            war_c = apply_dispersion_correction(model_war, is_pit)
            if vf.outcome_implied_fv(war_c, exposure_seasons=TARGET_SEASONS) is None:
                continue
            g_odds = vf.realized_implied_fv(war_c, is_pit, age=_grade_map_age(age, 0.0),
                                            position=pos, exposure_seasons=TARGET_SEASONS)
            cons_fv = src.get("consensus_fv_raw")
            if g_odds is None or cons_fv is None:
                continue
            cons_war = max(0.0, _pred_ols(ols, cons_fv)) if ols else model_war
            rank_war = (1 - lam) * cons_war + lam * model_war
            probs = vf.p_bucket_given_fv(g_odds, is_pit) or []
            if len(probs) != 5:
                continue
            odds = oc.recalibrate_bucket(probs, is_pit, provisional=not src.get("milb"))
            priced.append({"player_key": pk, "side": side, "is_pitcher": is_pit,
                           "decision_year": yr, "position": pos, "age": age,
                           "cons_grade": round(float(cons_fv), 1), "rank_war": rank_war,
                           "odds": [float(p) for p in odds],
                           "provisional_guard": not src.get("milb")})
        # run()'s rank-preserving quantile map of rank_war onto the consensus grade
        # distribution, applied within this (side, test year) fold. No outcome enters.
        target = sorted(p["cons_grade"] for p in priced)
        order = sorted(range(len(priced)),
                       key=lambda i: (priced[i]["rank_war"], priced[i]["player_key"]))
        m = len(priced)
        for rank_pos, i in enumerate(order):
            q = (rank_pos / (m - 1)) if m > 1 else 0.0
            x = q * (m - 1)
            lo = int(x)
            hi = min(m - 1, lo + 1)
            frac = x - lo
            priced[i]["display_grade"] = round(target[lo] * (1 - frac) + target[hi] * frac, 1)
        for p in priced:
            p.pop("cons_grade", None)
        fold["n_priced"] = len(priced)
        folds.append(fold)
        out.extend(priced)
    return out, folds


def _load_outcomes() -> tuple[dict, dict]:
    import storage
    cw, cs = {}, {}
    with storage.connect() as con:
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            try:
                cw[r["player_key"]] = json.loads(r["payload_json"])
            except ValueError:
                continue
        for r in con.execute("SELECT player_key, payload_json FROM career_stats"):
            try:
                cs[r["player_key"]] = json.loads(r["payload_json"])
            except ValueError:
                continue
    return cw, cs


def realized_surplus(pk: str, decision_year: int, cw: dict, cs: dict) -> tuple[str, float | None, int | None]:
    """(class, realized $M or None, debut year) by surplus_backtest_real's rules, valued
    at the live flat $/WAR and discounted to the decision year."""
    import surplus_backtest_real as sbr
    from backtest import RealizedRecord, realized_sv_pv
    stats_rows = cs.get(pk) or []
    war_seasons = (cw.get(pk) or {}).get("seasons") or {}
    mlb_seen = sbr._mlb_seasons_from_stats(stats_rows) | {int(y) for y in war_seasons}
    if any(s < decision_year for s in mlb_seen):
        return "excluded_mlb_before_asof", None, None
    if war_seasons:
        debut = min(int(y) for y in war_seasons)
        if debut + sbr.CONTROL_YEARS - 1 > sbr.LAST_FULL_SEASON:
            return "excluded_unresolved_debut", None, debut
        seasons = sbr._impute_seasons(war_seasons, debut)
        flat = vf.dollars_per_war_flat()
        dpw = {y: {"overall": flat} for y in range(2000, 2040)}
        rsv = realized_sv_pv(RealizedRecord(pk, debut, seasons), decision_year,
                             discount_rate=float(vf._config()["discount_rate"]),
                             dpw_by_year=dpw)
        return "resolved_debuted", float(rsv), debut
    if mlb_seen:
        return "excluded_no_war", None, None
    last = sbr._last_activity(stats_rows)
    if last is not None and last >= sbr.WASHED_BEFORE:
        return "excluded_censored_active", None, None
    return "resolved_washed", 0.0, None


def price_arms(row: dict, *, n_draws: int = N_DRAWS) -> dict:
    """Both arms for one frame row: calibrated mean and calibrated draws (served $M)."""
    g, ip, pos, age = row["display_grade"], row["is_pitcher"], row["position"], row["age"]
    kw = {"age": age, "eta_years": PRICE_ETA}
    inc_raw, _, inc_mean = vf._sv_draws_mm(g, ip, pos, n_draws, **kw)
    cand_raw, cand_w, cand_mean = vf._sv_draws_mm(g, ip, pos, n_draws, bucket_probs=row["odds"], **kw)
    if inc_raw is None or cand_raw is None:
        return {}
    return {
        "inc_mean": float(calibrate_mm(inc_mean / 1e6)),
        "inc_draws": calibrate_mm(inc_raw),
        "cand_mean": float(calibrate_mm(cand_mean / 1e6)),
        "cand_draws": calibrate_mm(cand_raw),
        "one_object": bool(abs(float(cand_w[0]) - float(row["odds"][0])
                               / max(1e-12, sum(row["odds"]))) < 1e-9),
    }


def _git(*args) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def run(persist: bool = True) -> dict:
    assert_reserved_frames_untouched()
    import efv_vintage_frame as vfr
    frame, folds = [], []
    for side in ("hit", "pit"):
        rows, f = _side_rows(side)
        frame.extend(rows)
        folds.extend(f)
    cw, cs = _load_outcomes()
    accounting: dict[str, int] = {}
    kept = []
    for row in frame:
        cls, rsv, debut = realized_surplus(row["player_key"], row["decision_year"], cw, cs)
        accounting[cls] = accounting.get(cls, 0) + 1
        if rsv is None:
            continue
        if debut is not None and debut >= vfr.R_VM_FIRST_DEBUT_YEAR:
            raise AssertionError(f"{row['player_key']}: debut {debut} is in the reserved R-VM cohorts")
        row["realized_mm"] = rsv
        kept.append(row)
    floor_mm = float(vf.apply_calibration(0.0))
    rng = np.random.RandomState(SEED)
    keys, realized, p_inc, pit_inc, p_cand, pit_cand = [], [], [], [], [], []
    one_object_ok = True
    n_moved = 0
    for row in kept:
        pr = price_arms(row)
        if not pr:
            accounting["excluded_unpriceable"] = accounting.get("excluded_unpriceable", 0) + 1
            continue
        u = float(rng.uniform())
        one_object_ok = one_object_ok and pr["one_object"]
        keys.append(row["player_key"])
        realized.append(row["realized_mm"])
        p_inc.append(pr["inc_mean"])
        p_cand.append(pr["cand_mean"])
        pit_inc.append(randomized_pit(pr["inc_draws"], row["realized_mm"], u, floor_mm))
        pit_cand.append(randomized_pit(pr["cand_draws"], row["realized_mm"], u, floor_mm))
        if abs(pr["cand_mean"] - pr["inc_mean"]) >= 0.05:
            n_moved += 1
    inc = calibration_metrics(p_inc, realized, pit_inc)
    cand = calibration_metrics(p_cand, realized, pit_cand)
    boot = paired_bootstrap(keys, realized, p_inc, pit_inc, p_cand, pit_cand)
    v = verdict(inc, cand, boot, one_object_ok=one_object_ok, n=len(keys))
    today = date.today()
    landing = {"rule": "only before 2026-10-04, or after the fWAR label epoch's step Z "
                       "(FWAR_LABEL_EPOCH_GATE.md part 9)",
               "read_date": today.isoformat(),
               "before_2026_10_04": today < LANDING_BEFORE,
               "holds": today < LANDING_BEFORE}
    n_side = {"hit": sum(1 for r in kept if r["side"] == "hit"),
              "pit": sum(1 for r in kept if r["side"] == "pit")}
    out = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "produced_by": "surplus_odds_gate.py",
        "gate_doc": GATE_DOC,
        "registration_commit": _git("log", "--diff-filter=A", "--format=%H", "--", GATE_DOC),
        "gate_doc_commit_at_read": _git("log", "-1", "--format=%H", "--", GATE_DOC),
        "code_commit": _git("rev-parse", "HEAD"),
        "scope": ("one registered read; pooled statistics only; no statistic by consensus "
                  "grade cell, band or stratum; backtest.run_backtest never called"),
        "frame": {"decision_years": list(GATE_YEARS), "folds": folds,
                  "accounting": accounting, "n": len(keys), "n_by_side": n_side,
                  "n_players": len(set(keys)),
                  "n_mean_moved_5c_or_more": n_moved,
                  "served_bust_floor_mm": round(floor_mm, 4),
                  "price_eta_years": PRICE_ETA, "n_draws": N_DRAWS,
                  "realized_unit": ("live flat $/WAR %.4fM, discount %.2f to the decision year"
                                    % (vf.dollars_per_war_flat(),
                                       float(vf._config()["discount_rate"])))},
        "incumbent": inc,
        "candidate": cand,
        "bootstrap": boot,
        "one_object_ok": one_object_ok,
        "decision": v,
        "landing": landing,
        "ships": bool(v.get("verdict") == "PASS" and landing["holds"]),
    }
    if persist:
        persist_block(out)
    return out


def persist_block(block: dict, path: Path | None = None) -> None:
    """Write the read as the BLOCK_KEY block of the parent artifact, leaving every other
    key as it is (surplus_backtest_real.run carries this block over when it rewrites)."""
    p = OUT_PATH if path is None else Path(path)
    doc = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    doc[BLOCK_KEY] = block
    p.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    log.info("wrote %s [%s]", p, BLOCK_KEY)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    print(json.dumps({k: rep[k] for k in ("incumbent", "candidate", "decision",
                                           "landing", "ships")}, indent=1))
    print("frame:", json.dumps(rep["frame"]["accounting"]), "n", rep["frame"]["n"])

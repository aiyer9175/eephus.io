# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""W-PROXY2 gate lab: xfv_proxy v2 expanded-feature arm (docs/efv-2026-07-24/GATES.md).

FROZEN PROTOCOL (registered in this header BEFORE any fit; one attempt per side):

  Harness: identical to efv_proxy.py -- same pair universe (2024-2026 debut cohorts,
  MIN_PA 50 Savant targets, as-of-debut profile), same forward chain (train on cohorts
  < test year, test 2025 then 2026, pool OOS predictions), same estimator
  (StandardScaler + Ridge alpha=3.0). Baseline = SAME-RUN refit of the shipped
  feature set (efv_model._feature_spec keys via _vec). V2 = shipped set + the frozen
  Statcast block below. Pair universes are IDENTICAL between arms (missing Statcast
  is imputed, never dropped), so the OOS pools are paired row-for-row.

  FROZEN V2 FEATURES -- hitters (source .cache/savant_minors tracked-park
  season aggregates; join = latest season s in {debut_year-1, debut_year-2},
  s >= 2023, row pa >= 50):
    sc_whiff      = swing_miss_percent
    sc_barrel     = barrels_per_bbe_percent
    sc_hardhit    = hardhit_percent
    sc_ev_topend  = hyper_speed (Savant adjusted EV -- the aggregate's top-end EV
                    measure, realizing the ev90/maxev intent; per-BBE percentiles
                    are ABSENT from the cached aggregate, recorded)
    sc_xwobacon   = (xwoba*pa - 0.69*bb) / bip, clipped to [0, 1.2] (fixed-weight
                    derivation; HBP not in the aggregate, absorbed; frozen constant
                    0.69 = standard wBB linear weight)
    sc_missing    = 1.0 row-level absence indicator
  ABSENT AND RECORDED (no cached batter-side per-pitch substrate; the feeds-derived
  statcast_alevel_signals sidecar is season-2026-only so it cannot enter the forward
  protocol): chase, z-contact, pull-air.

  FROZEN V2 FEATURES -- pitchers (source data/aaa_physics.json per-season rows;
  join = latest season s in {debut_year-1, debut_year-2}, s >= 2023,
  n_pitches >= 150 -- the W-SCREEN-SUB qualification convention):
    sc_velo, sc_ivb, sc_hb_abs, sc_spin, sc_ext, sc_rel_ht, sc_mix_entropy
                  = the season-level physics profile
    sc_astuff_pool = pooled aStuff+ (astuff_pool)
    sc_astuff_fb   = usage-weighted mean per-type aStuff+ over {FF, SI, FC}
    sc_astuff_sec  = max per-type aStuff+ over non-fastball types
    sc_spread      = stuff_spread (per-type aStuff+ SD)
    sc_missing     = 1.0 row-level absence indicator
  (arm_angle and velo_adj_ivb are in the sidecar but NOT in this lane's registered
  profile -- deliberately excluded. Per-type aStuff+ values in aaa_physics.json
  by_type are the stuff_plus_aaa model's scores, properly per-season.)

  Imputation (the _TOOL_IMPUTE lesson): every sc_ field is imputed at the
  TRAIN-FOLD OBSERVED MEAN (never zero); field-level gaps inside a covered row
  impute the same way; sc_missing carries row-level absence. Live projection
  join = latest season in {2026, 2025} (the live matrix's own as-of convention).

  Metric + bar (per side, judged independently): pooled OOS Pearson r improvement
  v2 minus baseline; paired bootstrap on the pooled OOS rows (each row = one
  player, so row resampling IS player-clustered), 2000 reps, seed 20260724;
  PASS iff lo95 (2.5th percentile of the delta) > 0. Spearman rho reported,
  never gating. Marginal = FAIL.

Writes the v2 block of data/xfv_proxy_eval.json (this lane owns that block; the
rest of the artifact -- shipped sides/projections -- is preserved byte-for-byte).
Run: python tools/efv_proxy2_lab.py
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from efv_proxy import _pull_targets, _spearman, COHORT_YEARS, DATA_DIR, MIN_PA  # noqa: E402
from efv_dataset import (_asof_point, _prior_features, _milb_features, _side_match,  # noqa: E402
                         _f, live_matrix_path)
from efv_model import _vec, _feature_spec  # noqa: E402

SEED = 20260724
N_BOOT = 2000
SC_YEAR_FLOOR = 2023          # first tracked-park season
HIT_PA_FLOOR = 50
PIT_PITCH_FLOOR = 150
FB_TYPES = {"FF", "SI", "FC"}

HIT_SC_KEYS = ["sc_whiff", "sc_barrel", "sc_hardhit", "sc_ev_topend", "sc_xwobacon"]
PIT_SC_KEYS = ["sc_velo", "sc_ivb", "sc_hb_abs", "sc_spin", "sc_ext", "sc_rel_ht",
               "sc_mix_entropy", "sc_astuff_pool", "sc_astuff_fb", "sc_astuff_sec",
               "sc_spread"]
ABSENT_RECORDED = {"hit": ["chase", "z_contact", "pull_air"],
                   "pit": []}


# ---------------------------------------------------------------------------
# Statcast sidecar joins
# ---------------------------------------------------------------------------

def _load_savant_minors() -> dict:
    """(season -> {mlbam(str): row}) for batters from the tracked-park aggregate."""
    out = {}
    for y in (2023, 2024, 2025, 2026):
        p = ROOT / ".cache" / "savant_minors" / f"batter_{y}.csv"
        if not p.exists():
            out[y] = {}
            continue
        with p.open(encoding="utf-8-sig") as f:
            out[y] = {r["player_id"]: r for r in csv.DictReader(f)}
    return out


def _hit_sc(sv: dict, mlbam, seasons: tuple) -> dict:
    """Frozen hitter Statcast block for the latest qualifying season; None = missing."""
    blank = {k: None for k in HIT_SC_KEYS}
    blank["sc_missing"] = 1.0
    for s in seasons:
        if s < SC_YEAR_FLOOR:
            continue
        row = (sv.get(s) or {}).get(str(mlbam))
        if not row:
            continue
        pa = _f(row.get("pa"))
        if pa is None or pa < HIT_PA_FLOOR:
            continue
        xwoba, bb, bip = _f(row.get("xwoba")), _f(row.get("bb")), _f(row.get("bip"))
        xwobacon = None
        if xwoba is not None and bb is not None and bip:
            xwobacon = float(np.clip((xwoba * pa - 0.69 * bb) / bip, 0.0, 1.2))
        return {"sc_whiff": _f(row.get("swing_miss_percent")),
                "sc_barrel": _f(row.get("barrels_per_bbe_percent")),
                "sc_hardhit": _f(row.get("hardhit_percent")),
                "sc_ev_topend": _f(row.get("hyper_speed")),
                "sc_xwobacon": xwobacon,
                "sc_missing": 0.0}
    return blank


def _pit_sc(phys: dict, mlbam, seasons: tuple) -> dict:
    """Frozen pitcher physics block for the latest qualifying season; None = missing."""
    blank = {k: None for k in PIT_SC_KEYS}
    blank["sc_missing"] = 1.0
    for s in seasons:
        if s < SC_YEAR_FLOOR:
            continue
        row = (phys.get(str(mlbam)) or {}).get(str(s))
        if not row or (row.get("n_pitches") or 0) < PIT_PITCH_FLOOR:
            continue
        bt = row.get("by_type") or {}
        fb_w = fb_wsum = 0.0
        sec = []
        for t, tr in bt.items():
            a = _f(tr.get("astuff"))
            if a is None:
                continue
            if t in FB_TYPES:
                w = _f(tr.get("usage")) or _f(tr.get("n_pitches")) or 0.0
                fb_w += w
                fb_wsum += w * a
            else:
                sec.append(a)
        return {"sc_velo": _f(row.get("velo")), "sc_ivb": _f(row.get("ivb")),
                "sc_hb_abs": _f(row.get("hb_abs")), "sc_spin": _f(row.get("spin")),
                "sc_ext": _f(row.get("ext")), "sc_rel_ht": _f(row.get("rel_ht")),
                "sc_mix_entropy": _f(row.get("mix_entropy")),
                "sc_astuff_pool": _f(row.get("astuff_pool")),
                "sc_astuff_fb": (fb_wsum / fb_w) if fb_w else None,
                "sc_astuff_sec": max(sec) if sec else None,
                "sc_spread": _f(row.get("stuff_spread")),
                "sc_missing": 0.0}
    return blank


# ---------------------------------------------------------------------------
# pairs (mirror of efv_proxy._build_pairs + mlbam + sc block)
# ---------------------------------------------------------------------------

def _build_pairs2(side: str, sv: dict, phys: dict) -> list[dict]:
    debuts = json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8"))
    if isinstance(debuts, dict):
        debuts = debuts.get("players") or []
    targets = {y: _pull_targets(y, side) for y in COHORT_YEARS}
    keys, _m = _feature_spec(side)
    pairs = []
    for rec in debuts:
        if not _side_match(rec, side):
            continue
        dd = rec.get("debut_date") or ""
        y = int(dd[:4]) if dd[:4].isdigit() else None
        mlbam = rec.get("mlbam_id")
        if y not in COHORT_YEARS or not mlbam:
            continue
        tgt = targets.get(y, {}).get(str(mlbam))
        if tgt is None:
            continue
        pt = _asof_point(rec, dd)
        if pt is None or _f(pt.get("consensus_fv_raw")) is None:
            continue
        row = {"consensus_fv_raw": _f(pt.get("consensus_fv_raw")),
               "position": rec.get("position"), "birth_date": rec.get("birth_date")}
        row.update(_prior_features(rec, pt, side))
        row["milb"] = _milb_features(mlbam, y, rec.get("birth_date"), side)
        sc = _hit_sc(sv, mlbam, (y - 1, y - 2)) if side == "hit" \
            else _pit_sc(phys, mlbam, (y - 1, y - 2))
        pairs.append({"key": rec.get("player_key"), "year": y, "mlbam": mlbam,
                      "x": [float(_vec(row, side)[k]) for k in keys],
                      "sc": sc, "y": float(tgt)})
    return pairs


# ---------------------------------------------------------------------------
# fitting (train-mean imputation inside each fold)
# ---------------------------------------------------------------------------

def _sc_matrix(rows: list[dict], sc_keys: list[str], means: dict) -> np.ndarray:
    out = []
    for p in rows:
        sc = p["sc"]
        vec = [sc[k] if sc[k] is not None else means[k] for k in sc_keys]
        vec.append(sc["sc_missing"])
        out.append(vec)
    return np.array(out, dtype=float)


def _train_means(rows: list[dict], sc_keys: list[str]) -> dict:
    means = {}
    for k in sc_keys:
        obs = [p["sc"][k] for p in rows if p["sc"][k] is not None]
        means[k] = float(np.mean(obs)) if obs else 0.0
    return means


def _fit_predict(tr: list[dict], te: list[dict], sc_keys: list[str] | None) -> np.ndarray:
    """Ridge alpha 3.0 on scaled features; sc_keys None = baseline (shipped set)."""
    Xtr = np.array([p["x"] for p in tr], dtype=float)
    Xte = np.array([p["x"] for p in te], dtype=float)
    if sc_keys is not None:
        means = _train_means(tr, sc_keys)
        Xtr = np.hstack([Xtr, _sc_matrix(tr, sc_keys, means)])
        Xte = np.hstack([Xte, _sc_matrix(te, sc_keys, means)])
    ytr = np.array([p["y"] for p in tr], dtype=float)
    sc = StandardScaler().fit(Xtr)
    rg = Ridge(alpha=3.0).fit(sc.transform(Xtr), ytr)
    return rg.predict(sc.transform(Xte))


def _forward(pairs: list[dict], sc_keys: list[str] | None) -> tuple[list, list, dict]:
    """Pooled OOS predictions, forward-chained exactly like efv_proxy._eval_forward."""
    yhat, ytrue, per_fold = [], [], {}
    for test_y in (2025, 2026):
        tr = [p for p in pairs if p["year"] < test_y]
        te = [p for p in pairs if p["year"] == test_y]
        if len(tr) < 25 or len(te) < 10:
            continue
        pred = _fit_predict(tr, te, sc_keys)
        yt = [p["y"] for p in te]
        per_fold[test_y] = {"n": len(te),
                            "r": round(float(np.corrcoef(pred, yt)[0, 1]), 4)}
        yhat.extend(pred.tolist())
        ytrue.extend(yt)
    return yhat, ytrue, per_fold


def _r(a, b) -> float | None:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if len(a) < 3 or a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def _boot_delta(yb, yv, yt) -> dict:
    rng = np.random.default_rng(SEED)
    yb, yv, yt = (np.asarray(v, dtype=float) for v in (yb, yv, yt))
    n = len(yt)
    deltas = []
    degen = 0
    for _ in range(N_BOOT):
        idx = rng.integers(0, n, n)
        rb, rv = _r(yb[idx], yt[idx]), _r(yv[idx], yt[idx])
        if rb is None or rv is None:
            degen += 1
            continue
        deltas.append(rv - rb)
    d = np.array(deltas)
    return {"reps": N_BOOT, "degenerate": degen, "seed": SEED,
            "delta_mean": round(float(d.mean()), 4),
            "lo95": round(float(np.percentile(d, 2.5)), 4),
            "hi95": round(float(np.percentile(d, 97.5)), 4)}


# ---------------------------------------------------------------------------
# full-fit: importances + live movers
# ---------------------------------------------------------------------------

def _full_fit(pairs: list[dict], sc_keys: list[str] | None):
    X = np.array([p["x"] for p in pairs], dtype=float)
    names = list(_BASE_KEYS)
    means = None
    if sc_keys is not None:
        means = _train_means(pairs, sc_keys)
        X = np.hstack([X, _sc_matrix(pairs, sc_keys, means)])
        names = names + sc_keys + ["sc_missing"]
    y = np.array([p["y"] for p in pairs], dtype=float)
    sc = StandardScaler().fit(X)
    rg = Ridge(alpha=3.0).fit(sc.transform(X), y)
    return rg, sc, names, means


def _live_movers(side: str, pairs: list[dict], sv: dict, phys: dict,
                 sc_keys: list[str]) -> list[dict]:
    """Project actives under base + v2 full fits; return top |delta| movers."""
    global _BASE_KEYS
    keys, _m = _feature_spec(side)
    _BASE_KEYS = keys
    rg_b, scaler_b, _, _ = _full_fit(pairs, None)
    rg_v, scaler_v, _, means = _full_fit(pairs, sc_keys)
    try:
        live = json.loads(live_matrix_path(side).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    movers = []
    for r in live:
        if r.get("consensus_fv_raw") is None:
            continue
        try:
            xb = np.array([[float(_vec(r, side)[k]) for k in keys]])
        except Exception:
            continue
        mlbam = r.get("mlbam_id")
        sc = _hit_sc(sv, mlbam, (2026, 2025)) if side == "hit" \
            else _pit_sc(phys, mlbam, (2026, 2025))
        scv = [[sc[k] if sc[k] is not None else means[k] for k in sc_keys] + [sc["sc_missing"]]]
        xv = np.hstack([xb, np.array(scv, dtype=float)])
        pb = float(rg_b.predict(scaler_b.transform(xb))[0])
        pv = float(rg_v.predict(scaler_v.transform(xv))[0])
        movers.append({"player_key": r.get("player_key"), "fv": r.get("consensus_fv_raw"),
                       "sc_covered": sc["sc_missing"] == 0.0,
                       "proxy_base": round(pb, 3), "proxy_v2": round(pv, 3),
                       "delta": round(pv - pb, 3)})
    movers.sort(key=lambda m: -abs(m["delta"]))
    return movers


_BASE_KEYS: list[str] = []


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------

def run() -> dict:
    global _BASE_KEYS
    sv = _load_savant_minors()
    phys = json.load(open(ROOT / "data" / "aaa_physics.json", encoding="utf-8"))["players"]
    block = {"registration": "docs/efv-2026-07-24/GATES.md W-PROXY2",
             "generated_at": date.today().isoformat(),
             "protocol": {"seed": SEED, "boot_reps": N_BOOT,
                          "estimator": "StandardScaler + Ridge(alpha=3.0), forward-chained "
                                       "train < test year, test 2025+2026, pooled OOS",
                          "baseline": "same-run refit of the shipped feature set",
                          "bar": "pooled OOS Pearson r delta lo95 > 0 per side",
                          "join": {"train": "latest season in {debut_year-1, debut_year-2}, >= 2023",
                                   "live": "latest season in {2026, 2025}",
                                   "hit_floor_pa": HIT_PA_FLOOR,
                                   "pit_floor_pitches": PIT_PITCH_FLOOR},
                          "imputation": "train-fold observed means (never zero) + sc_missing",
                          "absent_recorded": ABSENT_RECORDED},
             "features": {"hit": HIT_SC_KEYS + ["sc_missing"],
                          "pit": PIT_SC_KEYS + ["sc_missing"]},
             "sides": {}}
    for side in ("hit", "pit"):
        keys, _m = _feature_spec(side)
        _BASE_KEYS = keys
        sc_keys = HIT_SC_KEYS if side == "hit" else PIT_SC_KEYS
        pairs = _build_pairs2(side, sv, phys)
        covered = sum(1 for p in pairs if p["sc"]["sc_missing"] == 0.0)
        yb, yt, folds_b = _forward(pairs, None)
        yv, yt2, folds_v = _forward(pairs, sc_keys)
        assert yt == yt2, "paired OOS pools diverged"
        r_b, r_v = _r(yb, yt), _r(yv, yt)
        boot = _boot_delta(yb, yv, yt)
        verdict = "PASS" if boot["lo95"] > 0 else "FAIL"
        rg, scaler, names, _means = _full_fit(pairs, sc_keys)
        imp = sorted(((names[i], round(float(rg.coef_[i]), 5))
                      for i in range(len(names)) if names[i].startswith("sc_")),
                     key=lambda t: -abs(t[1]))
        movers = _live_movers(side, pairs, sv, phys, sc_keys)
        block["sides"][side] = {
            "pairs": len(pairs), "sc_covered": covered,
            "coverage": round(covered / max(len(pairs), 1), 3),
            "n_oos": len(yt),
            "r_base": round(r_b, 4), "r_v2": round(r_v, 4),
            "delta_r": round(r_v - r_b, 4),
            "rho_base": round(_spearman(yb, yt), 4),
            "rho_v2": round(_spearman(yv, yt), 4),
            "per_fold": {"base": folds_b, "v2": folds_v},
            "bootstrap": boot,
            "new_feature_coefs_std": imp,
            "top_movers": movers[:5],
            "verdict": verdict,
        }
        print(f"{side}: pairs={len(pairs)} covered={covered} | "
              f"r {r_b:.4f} -> {r_v:.4f} (delta {r_v - r_b:+.4f}, "
              f"lo95 {boot['lo95']:+.4f}, hi95 {boot['hi95']:+.4f}) | {verdict}")
    # v2 block write: preserve every other key of the shipped artifact byte-for-byte
    path = DATA_DIR / "xfv_proxy_eval.json"
    art = json.loads(path.read_text(encoding="utf-8"))
    art["v2"] = block
    path.write_text(json.dumps(art, separators=(",", ":")), encoding="utf-8")
    print("v2 block written to", path)
    return block


if __name__ == "__main__":
    run()

# SCRATCH (not shipped): STAGE G -- can the surplus CALIBRATION LAYER's shape be
# improved? Shipped = one global floored-linear map on raw $M. Candidates add a
# side split and/or an FV term. Same B1 protocol (LOyO by listing year, refit
# inside every fold), player-clustered paired bootstrap, zero-information null.
# Also: L1 oracle re-run with the LISTING eta so the "multiset cost" comparison
# in stage E is apples-to-apples.
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import value_framework as vf                                        # noqa: E402
from surplus_backtest_real import build_cohorts, _resolved_only     # noqa: E402
from backtest import realized_sv_pv                                 # noqa: E402

OUT = ROOT / "tools" / "_frontier_out"
OUT.mkdir(exist_ok=True)
SEED = 20260724
B = 2000


def lin0_fit(x, y):
    if len(x) < 5 or np.std(x) == 0:
        return (1.0, 0.0)
    lr = stats.linregress(x, y)
    return (float(lr.slope), float(lr.intercept))


def main():
    t0 = time.time()
    records, _ = build_cohorts()
    resolved = _resolved_only(records)
    cfg = vf._config()
    disc = float(cfg["discount_rate"])
    flat_mm = vf.dollars_per_war_flat()
    dpw = {y: {"overall": flat_mm} for y in range(2014, 2035)}

    rows = []
    for rec in resolved:
        lv, rz = rec.listing, rec.realized
        truth = realized_sv_pv(rz, lv.listing_year, discount_rate=disc, dpw_by_year=dpw)
        raw = (vf.expected_surplus_usd(lv.fv, lv.is_pitcher, lv.position,
                                       age=lv.age_at_listing, eta_years=lv.eta_years) or 0.0) / 1e6
        wars = [float(s.fwar) for s in sorted(rz.seasons, key=lambda s: s.year)]
        rows.append({"pid": lv.player_id, "y": int(lv.listing_year), "fv": float(lv.fv),
                     "pit": bool(lv.is_pitcher), "pos": lv.position, "age": lv.age_at_listing,
                     "eta": lv.eta_years, "raw": raw, "truth": float(truth),
                     "real6": float(sum(wars)), "wars": wars})

    RAW = np.array([r["raw"] for r in rows]); T = np.array([r["truth"] for r in rows])
    FV = np.array([r["fv"] for r in rows]); PIT = np.array([r["pit"] for r in rows])
    Y = np.array([r["y"] for r in rows]); PID = np.array([r["pid"] for r in rows])
    years = sorted(set(Y.tolist())); n = len(rows)
    rngg = np.random.default_rng(SEED + 99)
    GRP = rngg.integers(0, 2, n).astype(bool)          # zero-information 2-group split
    TIER = np.clip(np.round(FV / 5) * 5, 40, 60)

    # ---------------- calibration arms (all fit on train fold) ----------------
    def cal_global(tri, tei):
        s, b = lin0_fit(RAW[tri], T[tri])
        return np.maximum(0.0, s * RAW[tei] + b)

    def _by_mask(tri, tei, mask):
        out = np.empty(len(tei))
        for val in (False, True):
            trm = tri[mask[tri] == val]; tem = np.flatnonzero(mask[tei] == val)
            if len(trm) < 30:
                s, b = lin0_fit(RAW[tri], T[tri])
            else:
                s, b = lin0_fit(RAW[trm], T[trm])
            out[tem] = np.maximum(0.0, s * RAW[tei[tem]] + b)
        return out

    def cal_side(tri, tei):
        return _by_mask(tri, tei, PIT)

    def cal_placebo_group(tri, tei):
        return _by_mask(tri, tei, GRP)

    def cal_fvterm(tri, tei):
        X = np.column_stack([RAW[tri], FV[tri], np.ones(len(tri))])
        coef, *_ = np.linalg.lstsq(X, T[tri], rcond=None)
        Xe = np.column_stack([RAW[tei], FV[tei], np.ones(len(tei))])
        return np.maximum(0.0, Xe @ coef)

    def cal_tier_bias(tri, tei):
        s, b = lin0_fit(RAW[tri], T[tri])
        base_tr = np.maximum(0.0, s * RAW[tri] + b)
        out = np.maximum(0.0, s * RAW[tei] + b)
        for tv in (40, 45, 50, 55, 60):
            mtr = tri[TIER[tri] == tv]
            mte = np.flatnonzero(TIER[tei] == tv)
            if len(mtr) >= 40 and len(mte):
                adj = float((T[mtr] - base_tr[TIER[tri] == tv]).mean())
                out[mte] = np.maximum(0.0, out[mte] + adj)
        return out

    def cal_side_fv(tri, tei):
        out = np.empty(len(tei))
        for val in (False, True):
            trm = tri[PIT[tri] == val]; tem = np.flatnonzero(PIT[tei] == val)
            if len(trm) < 40:
                trm = tri
            X = np.column_stack([RAW[trm], FV[trm], np.ones(len(trm))])
            coef, *_ = np.linalg.lstsq(X, T[trm], rcond=None)
            Xe = np.column_stack([RAW[tei[tem]], FV[tei[tem]], np.ones(len(tem))])
            out[tem] = np.maximum(0.0, Xe @ coef)
        return out

    ARMS = {"global(shipped)": cal_global, "per_side": cal_side, "fv_term": cal_fvterm,
            "tier_bias": cal_tier_bias, "per_side+fv": cal_side_fv,
            "PLACEBO_random_2group": cal_placebo_group}

    def loyo(fn, idx=None):
        if idx is None:
            idx = np.arange(n)
        hp, hr, hf, hpit = [], [], [], []
        for yy in years:
            tri = idx[Y[idx] != yy]; tei = idx[Y[idx] == yy]
            if len(tri) < 50 or len(tei) < 5:
                continue
            p = fn(tri, tei)
            hp.append(p); hr.append(T[tei]); hf.append(FV[tei]); hpit.append(PIT[tei])
        if not hp:
            return None
        hp = np.concatenate(hp); hr = np.concatenate(hr)
        return {"n": len(hp), "mae": float(np.abs(hp - hr).mean()),
                "rmse": float(np.sqrt(((hp - hr) ** 2).mean())),
                "bias": float((hp - hr).mean()),
                "slope": float(stats.linregress(hp, hr).slope),
                "fv": np.concatenate(hf), "pit": np.concatenate(hpit),
                "err": hp - hr}

    res = {"n": n, "years": years, "seed": SEED, "boot": B}
    base = loyo(cal_global)
    arms = {}
    for nm, fn in ARMS.items():
        r = loyo(fn)
        tb = []
        for tv in (40, 45, 50, 55, 60):
            m = np.clip(np.round(r["fv"] / 5) * 5, 40, 60) == tv
            if m.sum() >= 20:
                tb.append({"fv": int(tv), "n": int(m.sum()),
                           "bias_mm": round(float(r["err"][m].mean()), 3),
                           "mae_mm": round(float(np.abs(r["err"][m]).mean()), 3)})
        arms[nm] = {"mae": round(r["mae"], 4), "rmse": round(r["rmse"], 3),
                    "bias": round(r["bias"], 4), "slope": round(r["slope"], 4),
                    "d_mae_vs_shipped": round(r["mae"] - base["mae"], 4),
                    "heldout_tier_bias": tb}
        print("%-22s MAE %8.4f (d %+.4f) slope %.4f bias %+.3f" % (
            nm, r["mae"], r["mae"] - base["mae"], r["slope"], r["bias"]))
    res["arms"] = arms

    # paired player-clustered bootstrap, refit LOyO every replicate
    rng = np.random.default_rng(SEED)
    upid = np.unique(PID); idx_by = {p: np.flatnonzero(PID == p) for p in upid}
    d = {k: [] for k in ARMS if k != "global(shipped)"}
    for _ in range(B):
        s = rng.integers(0, len(upid), len(upid))
        idx = np.concatenate([idx_by[upid[j]] for j in s])
        b0 = loyo(cal_global, idx)
        if b0 is None:
            continue
        for k in d:
            a = loyo(ARMS[k], idx)
            if a is not None:
                d[k].append(a["mae"] - b0["mae"])
    q = lambda a, p: float(np.percentile(a, p))
    res["bootstrap_vs_shipped"] = {
        k: {"reps": len(v), "d_mae_mean": round(float(np.mean(v)), 4),
            "ci95": [round(q(v, 2.5), 4), round(q(v, 97.5), 4)],
            "P(better)": round(float((np.array(v) < 0).mean()), 4)}
        for k, v in d.items() if v}

    # ---------------- L1 oracle with the LISTING eta (apples-to-apples) -------
    L1b, L1c = [], []
    for r in rows:
        fvh = vf.realized_implied_fv(r["real6"], r["pit"], position=r["pos"], exposure_seasons=6)
        if fvh is None:
            L1b.append(0.0); L1c.append(0.0); continue
        raw = (vf.expected_surplus_usd(fvh, r["pit"], r["pos"], age=r["age"],
                                       eta_years=r["eta"]) or 0.0) / 1e6
        L1b.append(raw); L1c.append(fvh)
    L1b = np.array(L1b)
    s, b = lin0_fit(L1b, T)                     # in-sample calibration for the oracle bound
    L1cal = np.maximum(0.0, s * L1b + b)
    res["oracle_listing_eta"] = {
        "note": ("perfect 6yr-WAR foresight -> realized_implied_fv -> engine, priced at the "
                 "LISTING eta (same timing info the production path has); calibration refit "
                 "in-sample so this is a BOUND, not a held-out figure"),
        "mae": round(float(np.abs(L1cal - T).mean()), 3),
        "bias": round(float((L1cal - T).mean()), 3),
        "shipped_heldout_mae": round(base["mae"], 3),
        "oracle_fv_mean": round(float(np.mean(L1c)), 2),
        "listed_fv_mean": round(float(FV.mean()), 2),
    }

    (OUT / "_surplus_stageG.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "arms"}, indent=1))
    for k, v in arms.items():
        print(k, v["heldout_tier_bias"])
    print("done %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()

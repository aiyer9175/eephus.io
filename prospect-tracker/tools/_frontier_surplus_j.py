# SCRATCH (not shipped): STAGE J -- does the SPREAD of the served grade
# distribution matter for dollar accuracy, at fixed ranking? This is the
# actionable form of the "$2.1M multiset-constraint cost": the eFV display map
# pins the served grade multiset to the consensus FV multiset (b=1.0). Sweep a
# monotone affine re-spread of that multiset, rank held fixed, $ calibration
# refit LOyO inside every fold.
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import value_framework as vf                                        # noqa: E402
from surplus_backtest_real import build_cohorts, _resolved_only     # noqa: E402
from backtest import realized_sv_pv                                 # noqa: E402

OUT = ROOT / "tools" / "_frontier_out"
SEED = 20260724
B = 1000


def main():
    records, _ = build_cohorts()
    resolved = _resolved_only(records)
    cfg = vf._config()
    disc = float(cfg["discount_rate"])
    dpw = {y: {"overall": vf.dollars_per_war_flat()} for y in range(2014, 2035)}
    rows = [{"pid": r.listing.player_id, "y": int(r.listing.listing_year),
             "fv": float(r.listing.fv), "pit": bool(r.listing.is_pitcher),
             "pos": r.listing.position, "age": r.listing.age_at_listing,
             "eta": r.listing.eta_years,
             "truth": float(realized_sv_pv(r.realized, r.listing.listing_year,
                                           discount_rate=disc, dpw_by_year=dpw))}
            for r in resolved]
    n = len(rows)
    T = np.array([r["truth"] for r in rows]); FV = np.array([r["fv"] for r in rows])
    Y = np.array([r["y"] for r in rows]); PID = np.array([r["pid"] for r in rows])
    years = sorted(set(Y.tolist()))
    mu = float(FV.mean())

    def raw_at(fvs):
        return np.array([(vf.expected_surplus_usd(float(fvs[i]), rows[i]["pit"], rows[i]["pos"],
                                                  age=rows[i]["age"], eta_years=rows[i]["eta"])
                          or 0.0) / 1e6 for i in range(n)])

    def loyo(P, idx=None):
        if idx is None:
            idx = np.arange(n)
        hp, hr = [], []
        for yy in years:
            tri = idx[Y[idx] != yy]; tei = idx[Y[idx] == yy]
            if len(tri) < 50 or len(tei) < 5:
                continue
            lr = stats.linregress(P[tri], T[tri])
            hp.append(np.maximum(0.0, lr.slope * P[tei] + lr.intercept)); hr.append(T[tei])
        if not hp:
            return None
        hp = np.concatenate(hp); hr = np.concatenate(hr)
        return float(np.abs(hp - hr).mean())

    spreads = [0.6, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0, 2.5]
    Pc = {}
    res = {"n": n, "seed": SEED, "boot": B, "served_fv_mean": round(mu, 2),
           "served_fv_sd": round(float(FV.std()), 2), "arms": {}}
    for b in spreads:
        fvb = np.clip(mu + b * (FV - mu), 20.0, 80.0)
        Pc[b] = raw_at(fvb)
        m = loyo(Pc[b])
        res["arms"][f"spread={b}"] = {"heldout_mae": round(m, 4),
                                      "served_fv_sd": round(float(fvb.std()), 2),
                                      "served_fv_min": round(float(fvb.min()), 1),
                                      "served_fv_max": round(float(fvb.max()), 1)}
        print("spread %.2f  MAE %.4f  fv sd %.2f" % (b, m, fvb.std()))

    rng = np.random.default_rng(SEED)
    upid = np.unique(PID); idx_by = {p: np.flatnonzero(PID == p) for p in upid}
    d = {b: [] for b in spreads if b != 1.0}
    for _ in range(B):
        s = rng.integers(0, len(upid), len(upid))
        idx = np.concatenate([idx_by[upid[j]] for j in s])
        m0 = loyo(Pc[1.0], idx)
        if m0 is None:
            continue
        for b in d:
            m = loyo(Pc[b], idx)
            if m is not None:
                d[b].append(m - m0)
    q = lambda a, p: round(float(np.percentile(a, p)), 4)
    res["bootstrap_vs_spread_1.0"] = {
        f"spread={b}": {"reps": len(v), "d_mae_mean": round(float(np.mean(v)), 4),
                        "ci95": [q(v, 2.5), q(v, 97.5)],
                        "P(better)": round(float((np.array(v) < 0).mean()), 4)}
        for b, v in d.items() if v}
    (OUT / "_surplus_stageJ.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res["bootstrap_vs_spread_1.0"], indent=1))


if __name__ == "__main__":
    main()

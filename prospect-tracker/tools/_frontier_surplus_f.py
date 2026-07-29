# SCRATCH (not shipped): STAGE F -- the FV->WAR anchor blend weight as a surplus
# accuracy lever, under the EXACT B1 protocol (LOyO by listing year, linear0
# calibration refit inside every fold), with a player-clustered paired bootstrap
# and a placebo null band.
#
# anchor(w) = w * public_reference + (1-w) * empirical_realized   (shipped w=0.5)
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
from backtest import realized_sv_pv, fit_linear_correction          # noqa: E402

OUT = ROOT / "tools" / "_frontier_out"
OUT.mkdir(exist_ok=True)
SEED = 20260724
B = 2000


def _clear_derived():
    for c in (vf._bucket_sv_usd, vf._calibrated_midpoints, vf._fv_war_scale,
              vf._prime_war_scale, vf._pchip_bucket_interpolators, vf._bayes_theta_draws):
        try:
            c.cache_clear()
        except Exception:
            pass


def loyo(P, R, Yr, years, floor=0.0):
    hp, hr = [], []
    for y in years:
        trm = Yr != y
        tem = Yr == y
        if trm.sum() < 20 or tem.sum() < 1:
            continue
        c = fit_linear_correction(P[trm], R[trm])
        for i in np.flatnonzero(tem):
            hp.append(max(floor, c["slope"] * P[i] + c["intercept_mm"]))
            hr.append(R[i])
    hp, hr = np.array(hp), np.array(hr)
    if len(hp) < 5:
        return None
    return {"n": len(hp), "mae": float(np.abs(hr - hp).mean()),
            "rmse": float(np.sqrt(((hr - hp) ** 2).mean())),
            "slope": float(stats.linregress(hp, hr).slope),
            "bias": float((hp - hr).mean())}


def main():
    t0 = time.time()
    records, _ = build_cohorts()
    resolved = _resolved_only(records)
    cfg = vf._config()
    disc = float(cfg["discount_rate"])
    flat_mm = vf.dollars_per_war_flat()
    dpw = {y: {"overall": flat_mm} for y in range(2014, 2035)}

    meta = [(r.listing,
             realized_sv_pv(r.realized, r.listing.listing_year,
                            discount_rate=disc, dpw_by_year=dpw),
             float(sum(s.fwar for s in r.realized.seasons)))
            for r in resolved]
    Yr = np.array([lv.listing_year for lv, _, _ in meta])
    R = np.array([t for _, t, _ in meta])
    W6 = np.array([w for _, _, w in meta])
    FV = np.array([lv.fv for lv, _, _ in meta])
    PID = np.array([lv.player_id for lv, _, _ in meta])
    years = sorted(set(Yr.tolist()))
    n = len(meta)
    print("pool n=%d years=%s (%.1fs)" % (n, years, time.time() - t0))

    base_fitted = json.loads(json.dumps(vf._fitted()))
    diag = base_fitted["empirical_anchors"]["diagnostics"]
    ref = {int(k): float(v) for k, v in cfg["anchor_calibration"]["public_reference"].items()}
    shipped = {int(k): float(v) for k, v in base_fitted["empirical_anchors"]["anchors"].items()}
    emp = {int(k): float(d["empirical_war_yr"]) for k, d in diag.items()
           if d.get("empirical_war_yr") is not None}
    print("shipped anchors ", shipped)
    print("empirical (realized) ", emp)
    print("public reference ", {k: ref[k] for k in shipped if k in ref})

    def anchors_at(w):
        out = {}
        for k, v in shipped.items():
            if k in emp and k in ref:
                out[str(k)] = round(w * ref[k] + (1 - w) * emp[k], 4)
            else:
                out[str(k)] = v          # thin tiers keep the shipped value
        return out

    def install(anch):
        f = json.loads(json.dumps(base_fitted))
        f["empirical_anchors"]["anchors"] = anch
        try:
            vf._fitted.cache_clear()
        except AttributeError:
            pass
        vf._fitted = (lambda _f=f: _f)   # scratch-process monkeypatch only
        _clear_derived()

    def preds():
        return np.array([(vf.expected_surplus_usd(lv.fv, lv.is_pitcher, lv.position,
                                                  age=lv.age_at_listing, eta_years=lv.eta_years)
                          or 0.0) / 1e6 for lv, _, _ in meta])

    res = {"n": n, "years": years, "seed": SEED, "boot": B,
           "shipped_anchors": shipped, "empirical_war_yr": emp,
           "public_reference": {k: ref[k] for k in shipped if k in ref},
           "anchor_reconstruction_check": {
               str(k): [round(0.5 * ref[k] + 0.5 * emp[k], 4), shipped[k]]
               for k in sorted(emp) if k in ref}}

    arms, Pcache = {}, {}
    for w in (0.0, 0.25, 0.5, 0.75, 1.0):
        install(anchors_at(w))
        P = preds()
        Pcache[w] = P
        r = loyo(P, R, Yr, years)
        r["raw_slope_vs_truth"] = float(stats.linregress(P, R).slope)
        r["raw_pred_mean"] = float(P.mean())
        r["anchors"] = anchors_at(w)
        # WAR-level calibration of this anchor set
        wp = np.array([(vf.fv_to_6yr_avg_war(f) or 0.0) * 6 for f in FV])
        r["war_bias_pooled"] = float((wp - W6).mean())
        r["war_mae"] = float(np.abs(wp - W6).mean())
        tb = {}
        for tv in (40, 45, 50, 55, 60):
            m = np.abs(np.round(FV / 5) * 5 - tv) < 0.1
            if m.sum() >= 20:
                tb[tv] = {"n": int(m.sum()), "war_bias": round(float((wp[m] - W6[m]).mean()), 3)}
        r["war_bias_by_tier"] = tb
        arms[f"w={w}"] = r
        print("  w=%.2f  heldout MAE %.4f  slope %.4f  bias %+.3f | WAR bias %+.3f" % (
            w, r["mae"], r["slope"], r["bias"], r["war_bias_pooled"]))
    res["arms"] = arms

    # ---- dollar bias by FV tier under w=0.5 (shipped) and the best arm -----
    def tier_bias(P):
        c_all = fit_linear_correction(P, R)
        hp = np.maximum(0.0, c_all["slope"] * P + c_all["intercept_mm"])
        out = []
        for tv in (40, 45, 50, 55, 60):
            m = np.abs(np.round(FV / 5) * 5 - tv) < 0.1
            if m.sum() >= 20:
                out.append({"fv": tv, "n": int(m.sum()),
                            "bias_mm": round(float((hp[m] - R[m]).mean()), 3),
                            "mae_mm": round(float(np.abs(hp[m] - R[m]).mean()), 3)})
        return out
    res["insample_tier_bias"] = {f"w={w}": tier_bias(Pcache[w]) for w in (0.0, 0.5)}

    # ---- paired player-clustered bootstrap, refit LOyO in every replicate ---
    rng = np.random.default_rng(SEED)
    upid = np.unique(PID)
    idx_by = {p: np.flatnonzero(PID == p) for p in upid}
    deltas = {w: [] for w in (0.0, 0.25, 0.75, 1.0)}
    for _ in range(B):
        s = rng.integers(0, len(upid), len(upid))
        idx = np.concatenate([idx_by[upid[j]] for j in s])
        base = loyo(Pcache[0.5][idx], R[idx], Yr[idx], years)
        if base is None:
            continue
        for w in deltas:
            a = loyo(Pcache[w][idx], R[idx], Yr[idx], years)
            if a is not None:
                deltas[w].append(a["mae"] - base["mae"])
    q = lambda a, p: float(np.percentile(a, p))
    res["bootstrap_vs_shipped_w0.5"] = {
        f"w={w}": {"reps": len(v), "d_mae_mean": round(float(np.mean(v)), 4),
                   "ci95": [round(q(v, 2.5), 4), round(q(v, 97.5), 4)],
                   "P(better than shipped)": round(float((np.array(v) < 0).mean()), 4)}
        for w, v in deltas.items() if v}

    # ---- PLACEBO NULL: random monotone anchor jitter of comparable size ----
    # Same pipeline, same refit; anchors perturbed by a random smooth multiplicative
    # factor with the same average |log| move as the w=0.5 -> w=0.0 change.
    a0, a5 = anchors_at(0.0), anchors_at(0.5)
    keys = [k for k in a5 if float(a5[k]) > 0 and float(a0[k]) > 0]
    move = float(np.mean([abs(np.log(float(a0[k]) / float(a5[k]))) for k in keys]))
    rngp = np.random.default_rng(SEED + 7)
    null = []
    for _ in range(40):
        while True:
            f = np.exp(rngp.normal(0.0, move, size=len(keys)))
            cand = {k: float(a5[k]) * fi for k, fi in zip(keys, f)}
            vals = [cand[k] for k in sorted(cand, key=lambda z: int(z))]
            if all(b > a for a, b in zip(vals, vals[1:])):     # keep monotone in FV
                break
        anch = dict(a5)
        anch.update({k: round(v, 4) for k, v in cand.items()})
        install(anch)
        r = loyo(preds(), R, Yr, years)
        if r:
            null.append(r["mae"])
    base_mae = arms["w=0.5"]["mae"]
    res["placebo_null_band"] = {
        "reps": len(null), "mean_log_move_matched": round(move, 4),
        "d_mae_mean": round(float(np.mean(null) - base_mae), 4),
        "d_mae_sd": round(float(np.std(null)), 4),
        "d_mae_min": round(float(np.min(null) - base_mae), 4),
        "d_mae_p05": round(float(np.percentile(null, 5) - base_mae), 4),
        "note": "random monotone anchor jitter, same average |log| move as w=0.5->0.0",
    }

    install(shipped and {str(k): v for k, v in shipped.items()})   # restore
    (OUT / "_surplus_stageF.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "arms"}, indent=1))
    print("done %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()

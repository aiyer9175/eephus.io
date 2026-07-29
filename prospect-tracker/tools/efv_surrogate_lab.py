# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Gated validation of the surrogate-label program (production-mirroring sim).

Forward-chaining forbids using the 2021-2023 surrogate rows to predict any RESOLVED
cohort (there is none later), so we validate one cutoff earlier where the answer is
now known. Map fit on 2011-2015 (deep, resolved); 2016-2018 stand in for the
"recently censored" cohorts; test on the now-resolved 2019-2020 cohorts' TRUE
first-6yr WAR. All temporally ordered = leakage-clean.

  Arm A pre-surrogate : train {2011-2015 true}                      (drop recent)
  Arm B surrogate     : train {2011-2015 true} + {2016-2018 3yr-surrogate}
  Arm C oracle        : train {2011-2015 true} + {2016-2018 true}   (upper bound)
  test (all arms)     : {2019-2020} vs TRUE first-6yr WAR

GATE (owner: recent-win + old-hold): B beats A on the 2019-2020 test (surrogate ADDS
value) AND B recovers most of C (surrogate label is faithful, not noise). Run:
  python tools/efv_surrogate_lab.py [--pit]
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import efv_surrogate as surr
from efv_model import _vec, _fit_ols_fv, _pred_ols
from prospect_path import _fit_ridge, _predict, _score
import storage

SIDE = "pit" if "--pit" in sys.argv else "hit"
DATA = Path(__file__).resolve().parents[1] / "data"
LAM = 0.63 if SIDE == "pit" else 0.85          # shipped-ish blend weight (same both arms)


def _cw():
    out = {}
    with storage.connect() as con:
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            try:
                out[r["player_key"]] = {int(y): float(w) for y, w
                                        in (json.loads(r["payload_json"]) or {}).get("seasons", {}).items()}
            except ValueError:
                pass
    return out


def _erow(r):
    return {"feats": _vec(r, SIDE), "fv": float(r["consensus_fv_raw"]),
            "pk": r["player_key"], "dy": r["debut_year"]}


def _fit(train_rows, targets):
    keys = None
    from efv_model import _feature_spec
    keys, _m = _feature_spec(SIDE)
    data = [{"feats": tr["feats"], "target": t, "fv": tr["fv"], "player_key": tr["pk"]}
            for tr, t in zip(train_rows, targets) if t is not None]
    ridge = _fit_ridge(data, keys)
    ols = _fit_ols_fv(data)
    return ridge, ols, keys


def _pred(ridge, ols, keys, r):
    rp = _predict(ridge, r["feats"])
    bp = (1 - LAM) * max(0.0, _pred_ols(ols, r["fv"])) + LAM * rp
    return rp, bp


def main():
    m = json.load(open(DATA / f"xfv_{'pitcher' if SIDE=='pit' else 'hitter'}_matrix.json"))
    cw = _cw()
    deb = [r for r in m if r["kind"] == "debuted" and r.get("consensus_fv_raw") is not None
           and r.get("debut_year") is not None]

    def grp(lo, hi, resolved_only=False):
        return [r for r in deb if lo <= r["debut_year"] <= hi
                and (not resolved_only or (not r.get("censored") and r.get("target_resolved") is not None))]

    early = grp(2011, 2015, resolved_only=True)      # map + base train (true)
    mid = grp(2016, 2018, resolved_only=True)        # "recently censored" stand-in (true known)
    test = grp(2019, 2020, resolved_only=True)       # now-resolved test
    print(f"[{SIDE}] early(2011-15)={len(early)} mid(2016-18)={len(mid)} test(2019-20)={len(test)}")
    if len(test) < 20 or len(mid) < 20 or len(early) < 40:
        print("  insufficient sample for the simulation"); return

    maps = surr.fit_maps(early, cw)
    print(f"  Stage-1 map fit on n={maps['n']} early rows; resid_var3={maps['resid_var3']:.2f}")

    # surrogate label for the mid cohorts: force the 3yr map (they play the censored role)
    def surrogate_label(r):
        s = cw.get(r["player_key"]); dy = r["debut_year"]
        if not s: return None
        span = surr._observed_span(s, dy)
        if span >= 3: return maps["war3"](surr._war_through(s, dy, 3))
        if span >= 2: return maps["war2"](surr._war_through(s, dy, 2))
        return None

    early_e = [_erow(r) for r in early]; early_t = [r["target_resolved"] for r in early]
    mid_e = [_erow(r) for r in mid]
    mid_true = [r["target_resolved"] for r in mid]
    mid_surr = [surrogate_label(r) for r in mid]

    # KM label = current production censoring: obs_sum * (6/n_obs). As-of-3-seasons
    # that is war3 * 2. This is what the shipped model uses for a censored row.
    def km_label(r):
        s = cw.get(r["player_key"]); dy = r["debut_year"]
        if not s: return None
        span = surr._observed_span(s, dy)
        if span < 2: return None
        span = min(span, 3)
        return surr._war_through(s, dy, span) * (6.0 / span)
    mid_km = [km_label(r) for r in mid]
    test_e = [_erow(r) for r in test]; test_t = [r["target_resolved"] for r in test]

    # LABEL FIDELITY on the mid cohorts: which training label is closest to true 6yr?
    from prospect_path import _spearman
    def _fidelity(lbls, name):
        fid = [(s, t) for s, t in zip(lbls, mid_true) if s is not None]
        rho = _spearman([s for s, _ in fid], [t for _, t in fid])
        mae = sum(abs(s - t) for s, t in fid) / len(fid)
        print(f"  mid {name:10} vs true: Spearman={rho:.3f}  MAE={mae:.2f}")
        return mae
    mae_surr = _fidelity(mid_surr, "surrogate")
    mae_km = _fidelity(mid_km, "KM(x6/n)")

    arms = {
        "A_KM_baseline": (early_e + mid_e, early_t + mid_km),      # current production label
        "B_surrogate": (early_e + mid_e, early_t + mid_surr),
        "C_oracle": (early_e + mid_e, early_t + mid_true),
    }
    print(f"\n  {'arm':18} {'ridge_rho':>9} {'blend_rho':>9} {'blend_mae':>9}  (test on 2019-20 TRUE WAR, n={len(test)})")
    res = {}
    for name, (tr_rows, tr_t) in arms.items():
        ridge, ols, keys = _fit(tr_rows, tr_t)
        rp = [(_pred(ridge, ols, keys, r)[0], t) for r, t in zip(test_e, test_t)]
        bp = [(_pred(ridge, ols, keys, r)[1], t) for r, t in zip(test_e, test_t)]
        sr, sb = _score(rp), _score(bp)
        res[name] = (sr["spearman"], sb["spearman"], sb["mae"])
        print(f"  {name:18} {sr['spearman']:>9.4f} {sb['spearman']:>9.4f} {sb['mae']:>9.3f}")

    a, b, c = res["A_KM_baseline"], res["B_surrogate"], res["C_oracle"]
    # win = surrogate beats the CURRENT KM censoring on either rank or WAR-magnitude MAE
    recent_win = (b[1] > a[1] + 0.002) or (b[2] < a[2] - 0.05)
    recovers = b[1] >= c[1] - 0.010             # surrogate recovers the oracle (label is faithful)
    oracle_beats_km = (c[1] > a[1] + 0.002) or (c[2] < a[2] - 0.05)   # does ANY better label help?
    print(f"\n  GATE  surrogate beats KM (rho or mae): {recent_win}  (B rho {b[1]:.4f}/mae {b[2]:.3f} vs A rho {a[1]:.4f}/mae {a[2]:.3f})")
    print(f"        surrogate recovers oracle: {recovers}  (B {b[1]:.4f} vs C {c[1]:.4f})")
    print(f"        DIAGNOSTIC oracle(true) beats KM: {oracle_beats_km}  (even perfect labels {'help' if oracle_beats_km else 'DO NOT help'})")
    print(f"  VERDICT: {'SHIP' if (recent_win and recovers) else 'NO-SHIP / ledger'}")
    json.dump({"side": SIDE, "n_test": len(test), "arms": res,
               "recent_win": recent_win, "recovers_oracle": recovers,
               "map_n": maps["n"], "resid_var3": maps["resid_var3"]},
              open(DATA / f"xfv_surrogate_eval{'_pit' if SIDE=='pit' else ''}.json", "w"), indent=1)


if __name__ == "__main__":
    main()

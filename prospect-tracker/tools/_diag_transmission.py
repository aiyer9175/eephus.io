# scratch diagnostic: label -> model transmission channel (pitcher label instrument)
from __future__ import annotations

import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from efv_pitcher_label_harness import (  # noqa: E402
    build_pool, window, km_label, run_gate, _split, _model_arm, _spearman,
)

SPAN = 3


# --------------------------------------------------------------------------
# univariate isotonic (PAVA) on 3-season WAR -> true6, fit on EARLY
# --------------------------------------------------------------------------
def _pava(xs, ys):
    pts = sorted(zip(xs, ys))
    lev = [[y, 1.0, x] for x, y in pts]          # [mean, weight, x_right]
    out = []
    for b in lev:
        out.append(b)
        while len(out) > 1 and out[-2][0] > out[-1][0]:
            b2 = out.pop()
            b1 = out.pop()
            w = b1[1] + b2[1]
            out.append([(b1[0] * b1[1] + b2[0] * b2[1]) / w, w, b2[2]])
    return [(b[2], b[0]) for b in out]           # (x_right, fitted_y) step fn


def _iso_fit(early):
    xs = [window(r, SPAN)["war"] for r in early]
    ys = [r["true6"] for r in early]
    return _pava(xs, ys)


def _iso_pred(state, rec, span):
    x = window(rec, span)["war"]
    for xr, y in state:
        if x <= xr:
            return y
    return state[-1][1]


def dist(name, vals):
    v = sorted(vals)
    n = len(v)
    q = lambda p: v[min(n - 1, int(p * n))]      # noqa: E731
    print(f"    {name:22} n={n:4d} mean={statistics.mean(v):7.3f} sd={statistics.pstdev(v):6.3f} "
          f"min={v[0]:7.2f} p10={q(.10):6.2f} p25={q(.25):6.2f} med={q(.50):6.2f} "
          f"p75={q(.75):6.2f} p90={q(.90):6.2f} max={v[-1]:7.2f}")


def main():
    pool = build_pool("pit")
    early, mid, test = _split(pool)
    print(f"pool={len(pool)} early={len(early)} mid={len(mid)} test={len(test)} span={SPAN}")

    iso_state = _iso_fit(early)
    true_mid = [r["true6"] for r in mid]
    km_mid = [km_label(r, SPAN) for r in mid]
    iso_mid = [_iso_pred(iso_state, r, SPAN) for r in mid]
    obs_mid = [window(r, SPAN)["war"] for r in mid]
    true_early = [r["true6"] for r in early]

    # ---------------- (a) MAGNITUDE / SCALE -------------------------------
    print("\n(a) LABEL DISTRIBUTIONS on the mid cohorts (2016-2018, n=%d)" % len(mid))
    dist("TRUE 6yr WAR", true_mid)
    dist("KM (obs*6/3)", km_mid)
    dist("ISOTONIC(war3)", iso_mid)
    dist("raw obs 3yr WAR", obs_mid)
    print("    ---- for reference, the EARLY half of the training set ----")
    dist("TRUE early (train)", true_early)
    print(f"    KM   / TRUE  mean ratio {statistics.mean(km_mid)/statistics.mean(true_mid):.3f}  "
          f"sd ratio {statistics.pstdev(km_mid)/statistics.pstdev(true_mid):.3f}")
    print(f"    ISO  / TRUE  mean ratio {statistics.mean(iso_mid)/statistics.mean(true_mid):.3f}  "
          f"sd ratio {statistics.pstdev(iso_mid)/statistics.pstdev(true_mid):.3f}")
    print(f"    mean(mid TRUE) {statistics.mean(true_mid):.3f} vs mean(early TRUE) "
          f"{statistics.mean(true_early):.3f}  |  mean(mid KM) {statistics.mean(km_mid):.3f}")
    print(f"    rho  KM  vs TRUE {_spearman(km_mid, true_mid)}   "
          f"ISO vs TRUE {_spearman(iso_mid, true_mid)}")
    print(f"    MAE  KM  {sum(abs(a-b) for a,b in zip(km_mid,true_mid))/len(mid):.3f}   "
          f"ISO {sum(abs(a-b) for a,b in zip(iso_mid,true_mid))/len(mid):.3f}")

    # ---------------- (b) WHICH ROWS DISAGREE ------------------------------
    print("\n(b) WHERE THE LABEL ERROR LIVES")
    recs = []
    for r, km, iso in zip(mid, km_mid, iso_mid):
        w = window(r, SPAN)
        recs.append({"pk": r["pk"], "true": r["true6"], "km": km, "iso": iso,
                     "war3": w["war"], "ip": w["ip"], "gs_ratio": w["gs_ratio"],
                     "seasons": w["seasons_pitched"], "miss": w["lines_missing"]})

    def bucket_report(label, groups):
        print(f"\n    -- by {label} --")
        print(f"    {'group':26} {'n':>4} {'mean_true':>9} {'mean_KM':>8} {'mean_ISO':>9} "
              f"{'MAE_KM':>7} {'MAE_ISO':>8} {'bias_KM':>8}")
        for gname, gs in groups:
            if not gs:
                continue
            n = len(gs)
            mt = statistics.mean(g["true"] for g in gs)
            mk = statistics.mean(g["km"] for g in gs)
            mi = statistics.mean(g["iso"] for g in gs)
            ek = sum(abs(g["km"] - g["true"]) for g in gs) / n
            ei = sum(abs(g["iso"] - g["true"]) for g in gs) / n
            bk = sum(g["km"] - g["true"] for g in gs) / n
            print(f"    {gname:26} {n:>4} {mt:>9.2f} {mk:>8.2f} {mi:>9.2f} "
                  f"{ek:>7.2f} {ei:>8.2f} {bk:>+8.2f}")

    srt = sorted(recs, key=lambda d: d["true"])
    n3 = len(srt) // 3
    bucket_report("TRUE-6yr-WAR tercile", [
        ("T1 low true", srt[:n3]), ("T2 mid true", srt[n3:2 * n3]), ("T3 high true", srt[2 * n3:])])
    bucket_report("role (3yr GS/G)", [
        ("reliever gs_ratio<.2", [d for d in recs if d["gs_ratio"] < 0.2 and d["ip"] > 0]),
        ("swing .2-.7", [d for d in recs if 0.2 <= d["gs_ratio"] < 0.7]),
        ("starter >=.7", [d for d in recs if d["gs_ratio"] >= 0.7]),
        ("no MLB line in window", [d for d in recs if d["miss"] > 0])])
    bucket_report("3yr exposure (IP)", [
        ("IP=0 / vanished", [d for d in recs if d["ip"] <= 0]),
        ("IP 0-50", [d for d in recs if 0 < d["ip"] <= 50]),
        ("IP 50-150", [d for d in recs if 50 < d["ip"] <= 150]),
        ("IP 150-350", [d for d in recs if 150 < d["ip"] <= 350]),
        ("IP >350", [d for d in recs if d["ip"] > 350])])

    print("\n    -- 12 largest |KM - TRUE| rows --")
    print(f"    {'player_key':26} {'true':>7} {'KM':>7} {'ISO':>7} {'war3':>6} {'IP':>7} {'gsR':>5}")
    for d in sorted(recs, key=lambda d: -abs(d["km"] - d["true"]))[:12]:
        print(f"    {d['pk'][:26]:26} {d['true']:>7.2f} {d['km']:>7.2f} {d['iso']:>7.2f} "
              f"{d['war3']:>6.2f} {d['ip']:>7.1f} {d['gs_ratio']:>5.2f}")

    # sum of squared label error contribution (ridge is L2 -> influence ~ err^2)
    tot_km = sum((d["km"] - d["true"]) ** 2 for d in recs)
    top10 = sorted(recs, key=lambda d: -abs(d["km"] - d["true"]))[:13]
    print(f"\n    KM squared-label-error total {tot_km:.1f}; top 10% of rows (n={len(top10)}) "
          f"carry {sum((d['km']-d['true'])**2 for d in top10)/tot_km:.1%} of it")
    hi = [d for d in recs if d["true"] >= 5]
    print(f"    rows with TRUE>=5 WAR: n={len(hi)} = {len(hi)/len(recs):.1%} of mid; "
          f"they carry {sum((d['km']-d['true'])**2 for d in hi)/tot_km:.1%} of KM squared error")

    # ---------------- (c) RANK vs MAGNITUDE synthetic labels ---------------
    # quantile transport: give rows the ordering of A and the marginal values of B
    def transport(rank_src, mag_src):
        order = sorted(range(len(mid)), key=lambda i: rank_src[i])
        vals = sorted(mag_src)
        lab = [0.0] * len(mid)
        for pos, i in enumerate(order):
            lab[i] = vals[pos]
        return lab

    d_true_rank_km_mag = transport(true_mid, km_mid)     # TRUE ranks, KM magnitudes
    e_km_rank_true_mag = transport(km_mid, true_mid)     # KM ranks, TRUE magnitudes
    f_iso_rank_true_mag = transport(iso_mid, true_mid)   # ISO ranks, TRUE magnitudes
    g_true_rank_iso_mag = transport(true_mid, iso_mid)   # TRUE ranks, ISO magnitudes
    # pure moment perturbations of the ORACLE (rank is perfect in all of these)
    mu_t, sd_t = statistics.mean(true_mid), statistics.pstdev(true_mid)
    mu_k, sd_k = statistics.mean(km_mid), statistics.pstdev(km_mid)
    h_true_shift = [t + (mu_k - mu_t) for t in true_mid]                 # KM's mean only
    i_true_scale = [mu_t + (t - mu_t) * (sd_k / sd_t) for t in true_mid]  # KM's sd only
    j_true_affine = [mu_k + (t - mu_t) * (sd_k / sd_t) for t in true_mid]  # both

    synth = {
        "D_TRUErank_KMmag": d_true_rank_km_mag,
        "E_KMrank_TRUEmag": e_km_rank_true_mag,
        "F_ISOrank_TRUEmag": f_iso_rank_true_mag,
        "G_TRUErank_ISOmag": g_true_rank_iso_mag,
        "H_TRUE_shift_toKMmean": h_true_shift,
        "I_TRUE_scale_toKMsd": i_true_scale,
        "J_TRUE_affine_toKM": j_true_affine,
    }
    for k, v in synth.items():
        print(f"    synth {k:24} mean={statistics.mean(v):6.3f} sd={statistics.pstdev(v):6.3f} "
              f"rho_vs_true={_spearman(v, true_mid)}")

    cands = {}
    for name, labs in synth.items():
        m = {r["pk"]: l for r, l in zip(mid, labs)}
        cands[name] = ((lambda e, _m=m: _m), (lambda st, rec, span: st.get(rec["pk"])))
    cands["B_isotonic_war3"] = (_iso_fit, _iso_pred)

    print("\n(c) DECISIVE GATE RUN (rank vs magnitude)")
    out = run_gate(cands, span=SPAN, side="pit")

    # ---------------- extra: is the mid block even influential? ------------
    print("\n(d) CONTROL ARMS")
    base = _model_arm([(r, r["true6"]) for r in early] + [(r, km_label(r, SPAN)) for r in mid],
                      test, "pit")
    early_only = _model_arm([(r, r["true6"]) for r in early], test, "pit")
    orac = _model_arm([(r, r["true6"]) for r in early] + [(r, r["true6"]) for r in mid],
                      test, "pit")
    for nm, v in (("early_only_drop_mid", early_only), ("KM_baseline", base), ("oracle", orac)):
        if v:
            print(f"    {nm:22} ridge {v['ridge']['spearman']:.4f}  blend {v['blend']['spearman']:.4f}"
                  f"  blend_mae {v['blend']['mae']:.3f}")
    return out


def _ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    for pos, i in enumerate(order):
        r[i] = float(pos)
    return r


def phase2():
    """How much rank fidelity is required, and which rows' ranks matter?"""
    pool = build_pool("pit")
    early, mid, test = _split(pool)
    true_mid = [r["true6"] for r in mid]
    km_mid = [km_label(r, SPAN) for r in mid]
    n = len(mid)

    def transport(rank_src, mag_src):
        order = sorted(range(n), key=lambda i: rank_src[i])
        vals = sorted(mag_src)
        lab = [0.0] * n
        for pos, i in enumerate(order):
            lab[i] = vals[pos]
        return lab

    rk_t, rk_k = _ranks(true_mid), _ranks(km_mid)

    cands, meta = {}, {}
    # --- 1. rank-fidelity sweep: blend KM ranks toward TRUE ranks, KM magnitudes kept
    for a in (0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 0.9, 1.0):
        mix = [a * rk_t[i] + (1 - a) * rk_k[i] for i in range(n)]
        labs = transport(mix, km_mid)
        meta[f"S_rankmix_{a:.1f}"] = labs
    # --- 2. partial oracle: give TRUE labels to a SUBSET, keep KM elsewhere
    idx_by_true = sorted(range(n), key=lambda i: -true_mid[i])
    idx_by_err = sorted(range(n), key=lambda i: -abs(km_mid[i] - true_mid[i]))
    import random
    rnd = random.Random(11)
    rand_idx = list(range(n))
    rnd.shuffle(rand_idx)
    k25 = n // 4
    subsets = {
        "P_true_topQ_by_TRUE": set(idx_by_true[:k25]),
        "P_true_botQ_by_TRUE": set(idx_by_true[-k25:]),
        "P_true_random25": set(rand_idx[:k25]),
        "P_true_worst10pct_err": set(idx_by_err[:max(1, n // 10)]),
        "P_true_all_but_topQ": set(idx_by_true[k25:]),
    }
    for nm, S in subsets.items():
        meta[nm] = [true_mid[i] if i in S else km_mid[i] for i in range(n)]
    # --- 3. drop-the-mid-block reference is run separately (control arm d)

    for nm, labs in meta.items():
        m = {r["pk"]: l for r, l in zip(mid, labs)}
        cands[nm] = ((lambda e, _m=m: _m), (lambda st, rec, span: st.get(rec["pk"])))

    print("phase2: rank-fidelity sweep + partial-oracle subsets")
    for nm, labs in meta.items():
        print(f"    {nm:24} rho_vs_true={_spearman(labs, true_mid):.4f} "
              f"mean={statistics.mean(labs):6.3f} sd={statistics.pstdev(labs):6.3f}")
    run_gate(cands, span=SPAN, side="pit")

    # top-tail recall of the KM label (what the rank error actually is)
    for q, lbl in ((0.10, "top 10%"), (0.20, "top 20%"), (0.25, "top 25%")):
        k = max(1, int(n * q))
        st = set(sorted(range(n), key=lambda i: -true_mid[i])[:k])
        sk = set(sorted(range(n), key=lambda i: -km_mid[i])[:k])
        print(f"    KM {lbl} overlap with TRUE {lbl}: {len(st & sk)}/{k} = {len(st&sk)/k:.0%}")
    hi = [i for i in range(n) if true_mid[i] >= 3]
    print(f"    rho KM vs TRUE within TRUE>=3 WAR subset (n={len(hi)}): "
          f"{_spearman([km_mid[i] for i in hi], [true_mid[i] for i in hi])}")
    lo = [i for i in range(n) if true_mid[i] < 3]
    print(f"    rho KM vs TRUE within TRUE<3 WAR subset (n={len(lo)}): "
          f"{_spearman([km_mid[i] for i in lo], [true_mid[i] for i in lo])}")


def phase3():
    """(i) does DOWN-WEIGHTING the KM-labeled block recover the free gain?
       (ii) does the rank-vs-magnitude verdict hold at other spans?"""
    from efv_pitcher_label_harness import LAM_PIT
    from prospect_path import _score, _fit_ridge, _predict
    from efv_model import _vec, _fit_ols_fv, _pred_ols, _feature_spec

    pool = build_pool("pit")
    early, mid, test = _split(pool)

    def arm(pairs):
        keys, _m = _feature_spec("pit")
        data = [{"feats": _vec(r["row"], "pit"), "target": float(t),
                 "fv": float(r["row"]["consensus_fv_raw"]), "player_key": r["pk"], "weight": w}
                for r, t, w in pairs if t is not None]
        ridge, ols = _fit_ridge(data, keys), _fit_ols_fv(data)
        if not ridge or not ols:
            return None
        bp = [((1 - LAM_PIT) * max(0.0, _pred_ols(ols, float(r["row"]["consensus_fv_raw"])))
               + LAM_PIT * _predict(ridge, _vec(r["row"], "pit")), r["true6"]) for r in test]
        rp = [(_predict(ridge, _vec(r["row"], "pit")), r["true6"]) for r in test]
        return {"ridge": _score(rp), "blend": _score(bp)}

    print("(i) SAMPLE-WEIGHT SWEEP on the KM-labeled mid block (label held = KM)")
    ref_km = arm([(r, r["true6"], 1.0) for r in early] + [(r, km_label(r, SPAN), 1.0) for r in mid])
    ref_or = arm([(r, r["true6"], 1.0) for r in early] + [(r, r["true6"], 1.0) for r in mid])
    hr = ref_or["blend"]["spearman"] - ref_km["blend"]["spearman"]
    print(f"    KM w=1.00 blend {ref_km['blend']['spearman']:.4f} | oracle blend "
          f"{ref_or['blend']['spearman']:.4f} | headroom {hr:+.4f}")
    for w in (0.75, 0.50, 0.25, 0.10, 0.001):
        v = arm([(r, r["true6"], 1.0) for r in early] + [(r, km_label(r, SPAN), w) for r in mid])
        g = v["blend"]["spearman"] - ref_km["blend"]["spearman"]
        print(f"    KM w={w:<5} ridge {v['ridge']['spearman']:.4f} blend "
              f"{v['blend']['spearman']:.4f}  gain {g:+.4f} = {g/hr*100:5.1f}% of headroom")
    v = arm([(r, r["true6"], 1.0) for r in early])
    g = v["blend"]["spearman"] - ref_km["blend"]["spearman"]
    print(f"    mid DROPPED  ridge {v['ridge']['spearman']:.4f} blend "
          f"{v['blend']['spearman']:.4f}  gain {g:+.4f} = {g/hr*100:5.1f}% of headroom")
    # and: oracle labels but down-weighted, to show the block itself carries signal
    for w in (0.5, 0.25):
        v = arm([(r, r["true6"], 1.0) for r in early] + [(r, r["true6"], w) for r in mid])
        g = v["blend"]["spearman"] - ref_km["blend"]["spearman"]
        print(f"    ORACLE w={w:<4} blend {v['blend']['spearman']:.4f}  gain {g:+.4f} = "
              f"{g/hr*100:5.1f}% of headroom")

    print("\n(ii) RANK-vs-MAGNITUDE at other spans")
    for span in (2, 4):
        true_mid = [r["true6"] for r in mid]
        km_mid = [km_label(r, span) for r in mid]
        n = len(mid)

        def transport(rank_src, mag_src, _n=n):
            order = sorted(range(_n), key=lambda i: rank_src[i])
            vals = sorted(mag_src)
            lab = [0.0] * _n
            for pos, i in enumerate(order):
                lab[i] = vals[pos]
            return lab

        labs = {"D_TRUErank_KMmag": transport(true_mid, km_mid),
                "E_KMrank_TRUEmag": transport(km_mid, true_mid)}
        cands = {}
        for nm, L in labs.items():
            m = {r["pk"]: l for r, l in zip(mid, L)}
            cands[nm] = ((lambda e, _m=m: _m), (lambda st, rec, sp: st.get(rec["pk"])))
        print(f"\n  --- span={span} ---")
        run_gate(cands, span=span, side="pit")


def phase4():
    """Noise floor: bootstrap the 180-row test set for the four key arms."""
    import random
    from efv_pitcher_label_harness import LAM_PIT
    from prospect_path import _fit_ridge, _predict, _spearman as sp
    from efv_model import _vec, _fit_ols_fv, _pred_ols, _feature_spec

    pool = build_pool("pit")
    early, mid, test = _split(pool)
    true_mid = [r["true6"] for r in mid]
    km_mid = [km_label(r, SPAN) for r in mid]
    n = len(mid)

    def transport(rank_src, mag_src):
        order = sorted(range(n), key=lambda i: rank_src[i])
        vals = sorted(mag_src)
        lab = [0.0] * n
        for pos, i in enumerate(order):
            lab[i] = vals[pos]
        return lab

    arms = {"A_KM": km_mid, "C_oracle": true_mid,
            "D_TRUErank_KMmag": transport(true_mid, km_mid),
            "E_KMrank_TRUEmag": transport(km_mid, true_mid)}
    keys, _m = _feature_spec("pit")
    preds = {}
    for nm, labs in arms.items():
        pairs = [(r, r["true6"]) for r in early] + list(zip(mid, labs))
        data = [{"feats": _vec(r["row"], "pit"), "target": float(t),
                 "fv": float(r["row"]["consensus_fv_raw"]), "player_key": r["pk"]}
                for r, t in pairs]
        ridge, ols = _fit_ridge(data, keys), _fit_ols_fv(data)
        preds[nm] = [(1 - LAM_PIT) * max(0.0, _pred_ols(ols, float(r["row"]["consensus_fv_raw"])))
                     + LAM_PIT * _predict(ridge, _vec(r["row"], "pit")) for r in test]
    obs = [r["true6"] for r in test]
    rnd = random.Random(2026)
    B = 2000
    boot = {nm: [] for nm in arms}
    diffs = {"D-A": [], "E-A": [], "C-A": [], "D-E": []}
    for _ in range(B):
        idx = [rnd.randrange(len(test)) for _ in range(len(test))]
        o = [obs[i] for i in idx]
        cur = {}
        for nm in arms:
            v = sp([preds[nm][i] for i in idx], o)
            cur[nm] = v
            if v is not None:
                boot[nm].append(v)
        if all(cur[k] is not None for k in arms):
            diffs["D-A"].append(cur["D_TRUErank_KMmag"] - cur["A_KM"])
            diffs["E-A"].append(cur["E_KMrank_TRUEmag"] - cur["A_KM"])
            diffs["C-A"].append(cur["C_oracle"] - cur["A_KM"])
            diffs["D-E"].append(cur["D_TRUErank_KMmag"] - cur["E_KMrank_TRUEmag"])
    print(f"bootstrap B={B} over the {len(test)}-row test set (blend spearman)")
    for nm in arms:
        v = sorted(boot[nm])
        print(f"    {nm:20} point={sp(preds[nm], obs):.4f} boot_sd={statistics.pstdev(v):.4f} "
              f"CI95=[{v[int(.025*len(v))]:.4f}, {v[int(.975*len(v))]:.4f}]")
    for k, v in diffs.items():
        v = sorted(v)
        print(f"    delta {k:6} mean={statistics.mean(v):+.4f} sd={statistics.pstdev(v):.4f} "
              f"CI95=[{v[int(.025*len(v))]:+.4f}, {v[int(.975*len(v))]:+.4f}]  "
              f"P(>0)={sum(1 for x in v if x>0)/len(v):.3f}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "4":
        phase4()
    elif len(sys.argv) > 1 and sys.argv[1] == "3":
        phase3()
    elif len(sys.argv) > 1 and sys.argv[1] == "2":
        phase2()
    else:
        main()

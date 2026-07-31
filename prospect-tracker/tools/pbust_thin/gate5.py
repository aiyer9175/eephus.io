# pbust thin-sample lane -- SCRATCH GATE LAB, FULL BATTERY on the SELECTED head
# (lane: pbust).   HEAD D:  logit p_bust = a + b*(grade - 30) + d_level
#   one shared grade slope (so p_bust is nonincreasing in grade INSIDE every level
#   by construction, b < 0) + a per-level intercept (levels are CATEGORICAL: the
#   realized level->bust relation is NOT monotone - ungraded AAA is org-filler and
#   busts MORE than ungraded AA - so a linear level_rank term, head B, is
#   misspecified exactly where it would move served numbers most).
#
# Controls, all on the SAME paired-bootstrap draws (TRAIN matrix rows AND TEST
# cohort rows resampled, the provisional ridge REFIT every draw so the grade
# column carries its own sampling variability -- docs/EFV_GATE_STANDARD.md sec.2):
#   incumbent   vf.p_bucket_given_fv(grade, is_pit)[0]   (what the card serves today)
#   constant    covariate-free training-fold bust rate    (the BUCKET-AGE-HEAD ablation)
#   headA       grade only                                (prices what level buys)
#   perm_grade  head D with the GRADE column row-permuted (train + test)
#   perm_level  head D with the LEVEL column row-permuted (train + test)
# Folds: leave-one-cohort-year-out over 4 independent cohort years.
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gate as G                                          # noqa: E402

LVLS = ("DSL", "CPX", "A", "A+", "AA", "AAA")
EPS = 1e-6


def logit_fit(X, y, l2=1e-3, iters=50):
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    w = np.zeros(X.shape[1])
    for _ in range(iters):
        z = np.clip(X @ w, -30, 30)
        p = 1.0 / (1.0 + np.exp(-z))
        g = X.T @ (p - y) + l2 * w
        s = np.clip(p * (1 - p), 1e-9, None)
        H = (X * s[:, None]).T @ X + l2 * np.eye(X.shape[1])
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            break
        w -= step
        if np.max(np.abs(step)) < 1e-9:
            break
    return w


def predict(w, X):
    return 1.0 / (1.0 + np.exp(-np.clip(np.asarray(X, dtype=float) @ w, -30, 30)))


def logloss(p, y):
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    y = np.asarray(y, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(p, y):
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


def design(gr, lv, kind):
    """gr: 1-D grade array. lv: level index array (0..5). kind: 'A' | 'D'."""
    n = len(gr)
    if kind == "A":
        return np.column_stack([np.ones(n), gr - 30.0])
    M = np.zeros((n, 5))
    for j in range(1, 6):                    # DSL (index 0) is the reference cell
        M[:, j - 1] = (lv == j).astype(float)
    return np.column_stack([np.ones(n), gr - 30.0, M])


def main():
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    rng = random.Random(20260725)
    nrng = np.random.default_rng(20260725)
    rows = [r for r in G.load() if r["year"] in G.PRIMARY_YEARS]
    tr = {s: G.train_rows(s) for s in ("hit", "pit")}
    base = {s: G.fit_from(tr[s], s) for s in ("hit", "pit")}
    for r, g in zip(rows, G.regrade(rows, base)):
        r["g"] = g
        r["y"] = G.label_variant(r, G.PRIMARY_VARIANT)
        r["lv"] = LVLS.index(r["level"])

    cells = {}
    for i, r in enumerate(rows):
        cells.setdefault((r["side"], r["year"]), []).append(i)

    keys = ["incumbent", "headA", "headD", "constant", "perm_grade", "perm_level"]
    boot = {k: [] for k in keys}
    boot_b = {k: [] for k in keys}
    gap = {"hit": [], "pit": []}          # G1: empirical - incumbent, grade >= 35
    for draw in range(B):
        fits = {}
        for s in ("hit", "pit"):
            samp = [tr[s][rng.randrange(len(tr[s]))] for _ in range(len(tr[s]))]
            try:
                fits[s] = G.fit_from(samp, s)
            except Exception:
                fits[s] = base[s]
        idx = []
        for ii in cells.values():
            idx += [ii[rng.randrange(len(ii))] for _ in range(len(ii))]
        sub = [rows[i] for i in idx]
        gs = np.array(G.regrade(sub, fits))
        yy = np.array([r["y"] for r in sub])
        lv = np.array([r["lv"] for r in sub])
        side = np.array([r["side"] for r in sub])
        year = np.array([r["year"] for r in sub])
        inc_p = np.array([G.inc(g, r["side"] == "pit") for g, r in zip(gs, sub)])
        for s in ("hit", "pit"):
            m = (side == s) & (gs >= 35.0)
            if m.sum() >= 20:
                gap[s].append(float(yy[m].mean() - inc_p[m].mean()))
        acc = {k: [] for k in keys}
        accb = {k: [] for k in keys}
        for s in ("hit", "pit"):
            sm = side == s
            for hold in G.PRIMARY_YEARS:
                trm = sm & (year != hold)
                tem = sm & (year == hold)
                if trm.sum() < 200 or tem.sum() < 50:
                    continue
                ytr, yte = yy[trm], yy[tem]
                P = {}
                P["incumbent"] = inc_p[tem]
                w = logit_fit(design(gs[trm], lv[trm], "A"), ytr)
                P["headA"] = predict(w, design(gs[tem], lv[tem], "A"))
                w = logit_fit(design(gs[trm], lv[trm], "D"), ytr)
                P["headD"] = predict(w, design(gs[tem], lv[tem], "D"))
                P["constant"] = np.full(tem.sum(), ytr.mean())
                gp = nrng.permutation(gs[trm])
                w = logit_fit(design(gp, lv[trm], "D"), ytr)
                P["perm_grade"] = predict(w, design(nrng.permutation(gs[tem]), lv[tem], "D"))
                lp = nrng.permutation(lv[trm])
                w = logit_fit(design(gs[trm], lp, "D"), ytr)
                P["perm_level"] = predict(w, design(gs[tem], nrng.permutation(lv[tem]), "D"))
                for k in keys:
                    acc[k].append(logloss(P[k], yte))
                    accb[k].append(brier(P[k], yte))
        for k in keys:
            if acc[k]:
                boot[k].append(float(np.mean(acc[k])))
                boot_b[k].append(float(np.mean(accb[k])))
        if (draw + 1) % 100 == 0:
            print(f"  boot {draw+1}/{B}", flush=True)

    def ci(v):
        v = np.sort(np.asarray(v))
        return {"mean": round(float(v.mean()), 5), "lo95": round(float(np.quantile(v, .025)), 5),
                "hi95": round(float(np.quantile(v, .975)), 5), "n": len(v)}

    def dci(a, b):
        v = np.sort(np.asarray(boot[a]) - np.asarray(boot[b]))
        return {"mean": round(float(v.mean()), 5), "lo95": round(float(np.quantile(v, .025)), 5),
                "hi95": round(float(np.quantile(v, .975)), 5),
                "P(>0)": round(float((v > 0).mean()), 4)}

    rep = {"B": B, "head": "D (grade slope + per-level intercept)", "label_variant": G.PRIMARY_VARIANT,
           "primary_years": list(G.PRIMARY_YEARS),
           "g1_gap_emp_minus_incumbent_grade_ge35": {s: ci(gap[s]) for s in gap},
           "logloss": {k: ci(boot[k]) for k in keys},
           "brier": {k: ci(boot_b[k]) for k in keys},
           "deltas_logloss_positive_means_first_is_worse": {
               "incumbent - headD": dci("incumbent", "headD"),
               "incumbent - headA": dci("incumbent", "headA"),
               "headA - headD": dci("headA", "headD"),
               "constant - headD": dci("constant", "headD"),
               "perm_grade - headD": dci("perm_grade", "headD"),
               "perm_level - headD": dci("perm_level", "headD"),
               "incumbent - constant": dci("incumbent", "constant"),
               "incumbent - perm_grade": dci("incumbent", "perm_grade"),
               "incumbent - perm_level": dci("incumbent", "perm_level"),
           }}

    # ---- label-permutation null on (constant - headD) ------------------------
    gs0 = np.array([r["g"] for r in rows])
    y0 = np.array([r["y"] for r in rows])
    lv0 = np.array([r["lv"] for r in rows])
    sd0 = np.array([r["side"] for r in rows])
    yr0 = np.array([r["year"] for r in rows])
    null = []
    for _ in range(500):
        per = []
        for s in ("hit", "pit"):
            sm = sd0 == s
            yp = y0.copy()
            yp[sm] = nrng.permutation(y0[sm])
            for hold in G.PRIMARY_YEARS:
                trm = sm & (yr0 != hold)
                tem = sm & (yr0 == hold)
                w = logit_fit(design(gs0[trm], lv0[trm], "D"), yp[trm])
                p = predict(w, design(gs0[tem], lv0[tem], "D"))
                per.append(logloss(np.full(tem.sum(), yp[trm].mean()), yp[tem]) - logloss(p, yp[tem]))
        null.append(float(np.mean(per)))
    null = np.sort(np.asarray(null))
    rep["label_permutation_null_constant_minus_headD"] = {
        "p50": round(float(np.quantile(null, .50)), 5),
        "p95": round(float(np.quantile(null, .95)), 5),
        "p99": round(float(np.quantile(null, .99)), 5), "n": len(null)}

    # ---- final point head + monotone sanity + OOF calibration ----------------
    head, cal = {}, {}
    for s in ("hit", "pit"):
        sm = sd0 == s
        w = logit_fit(design(gs0[sm], lv0[sm], "D"), y0[sm])
        head[s] = {"a": round(float(w[0]), 6), "b_grade": round(float(w[1]), 6),
                   "level_offsets": {LVLS[0]: 0.0,
                                     **{LVLS[j]: round(float(w[1 + j]), 6) for j in range(1, 6)}},
                   "n": int(sm.sum()), "n_bust": int(y0[sm].sum()),
                   "monotone_in_grade_within_level": bool(w[1] < 0)}
        bands, lvls = {}, {}
        for hold in G.PRIMARY_YEARS:
            trm = sm & (yr0 != hold)
            tem = sm & (yr0 == hold)
            ww = logit_fit(design(gs0[trm], lv0[trm], "D"), y0[trm])
            p = predict(ww, design(gs0[tem], lv0[tem], "D"))
            for g, lvi, yv, pv in zip(gs0[tem], lv0[tem], y0[tem], p):
                bk = ("20-30" if g < 30 else "30-35" if g < 35 else "35-40" if g < 40
                      else "40-45" if g < 45 else "45+")
                for store, key in ((bands, bk), (lvls, LVLS[lvi])):
                    d = store.setdefault(key, {"n": 0, "obs": 0.0, "inc": 0.0, "cand": 0.0})
                    d["n"] += 1
                    d["obs"] += float(yv)
                    d["inc"] += G.inc(float(g), s == "pit")
                    d["cand"] += float(pv)
        fmt = lambda st: {k: {"n": v["n"], "observed": round(v["obs"] / v["n"], 4),
                              "incumbent": round(v["inc"] / v["n"], 4),
                              "headD_oof": round(v["cand"] / v["n"], 4)}
                          for k, v in st.items()}
        cal[s] = {"by_grade_band": fmt(bands), "by_level": fmt(lvls)}
    rep["head_point_fit"] = head
    rep["oof_calibration"] = cal

    # ---- sensitivity: the 2019 (censored) cohort, and the label variants -----
    sens = {}
    allrows = G.load()
    for yrs, tag in ((G.PRIMARY_YEARS, "primary_2015_2018"), ((2019,), "sensitivity_2019_censored")):
        sub = [r for r in allrows if r["year"] in yrs]
        for r, g in zip(sub, G.regrade(sub, base)):
            r["g"] = g
        for s in ("hit", "pit"):
            sel = [r for r in sub if r["side"] == s and r["g"] >= 35.0]
            if len(sel) < 20:
                continue
            for variant in ("conservative", "pt_rule", "upper"):
                ys = [G.label_variant(r, variant) for r in sel]
                sens[f"{tag}/{s}/grade>=35/{variant}"] = {
                    "n": len(sel), "observed": round(sum(ys) / len(ys), 4),
                    "incumbent": round(sum(G.inc(r["g"], s == "pit") for r in sel) / len(sel), 4)}
    rep["sensitivity"] = sens

    (HERE / f"gate5_report_{G.PRIMARY_VARIANT}.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in
                      ("g1_gap_emp_minus_incumbent_grade_ge35", "logloss",
                       "deltas_logloss_positive_means_first_is_worse",
                       "label_permutation_null_constant_minus_headD",
                       "head_point_fit")}, indent=1))


if __name__ == "__main__":
    main()

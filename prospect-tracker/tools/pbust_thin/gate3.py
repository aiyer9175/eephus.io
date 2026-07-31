# pbust thin-sample lane -- SCRATCH GATE LAB, FULL BATTERY on the selected head
# (lane: pbust).  Head B:  logit p_bust = a + b*(grade-30) + c*(level_rank-2)
#
# Controls run on the SAME paired-bootstrap draws (train AND test resampled, the
# provisional ridge refit every draw so the grade column carries its own sampling
# variability, per docs/EFV_GATE_STANDARD.md sec.2):
#   incumbent      vf.p_bucket_given_fv(grade, is_pit)[0]  (what the card serves today)
#   constant       covariate-free training-fold bust rate  (the BUCKET-AGE-HEAD ablation)
#   perm_grade     head B with the GRADE column row-permuted (train + test)
#   perm_level     head B with the LEVEL column row-permuted (train + test) -- the
#                  zero-information twin of the covariate this head ADDS over head A
#   headA          grade only, to price what level buys
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gate as G                                          # noqa: E402
from gate2 import fit_logistic2, predict2, LR             # noqa: E402


def xB(g, lvl):
    return [g - 30.0, LR.get(lvl, 2.0) - 2.0]


def xA(g, lvl):
    return [g - 30.0]


def main():
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    rng = random.Random(20260725)
    rows = [r for r in G.load() if r["year"] in G.PRIMARY_YEARS]
    tr = {s: G.train_rows(s) for s in ("hit", "pit")}
    base = {s: G.fit_from(tr[s], s) for s in ("hit", "pit")}
    for r, g in zip(rows, G.regrade(rows, base)):
        r["g"] = g
        r["y"] = G.label_variant(r, "conservative")

    by_cell = {}
    for i, r in enumerate(rows):
        by_cell.setdefault((r["side"], r["year"]), []).append(i)

    keys = ["incumbent", "headA", "headB", "constant", "perm_grade", "perm_level"]
    boot = {k: [] for k in keys}
    boot_brier = {k: [] for k in keys}
    for d in range(B):
        fits = {}
        for s in ("hit", "pit"):
            samp = [tr[s][rng.randrange(len(tr[s]))] for _ in range(len(tr[s]))]
            try:
                fits[s] = G.fit_from(samp, s)
            except Exception:
                fits[s] = base[s]
        idx = []
        for ii in by_cell.values():
            idx += [ii[rng.randrange(len(ii))] for _ in range(len(ii))]
        sub = [dict(rows[i]) for i in idx]
        for r, g in zip(sub, G.regrade(sub, fits)):
            r["g"] = g
        acc = {k: [] for k in keys}
        accb = {k: [] for k in keys}
        for s in ("hit", "pit"):
            side_rows = [r for r in sub if r["side"] == s]
            for hold in G.PRIMARY_YEARS:
                trn = [r for r in side_rows if r["year"] != hold]
                tst = [r for r in side_rows if r["year"] == hold]
                if len(trn) < 200 or len(tst) < 50:
                    continue
                ytr = [r["y"] for r in trn]
                yte = [r["y"] for r in tst]
                preds = {}
                preds["incumbent"] = [G.inc(r["g"], s == "pit") for r in tst]
                w = fit_logistic2([xA(r["g"], r["level"]) for r in trn], ytr)
                preds["headA"] = [predict2(w, xA(r["g"], r["level"])) for r in tst]
                w = fit_logistic2([xB(r["g"], r["level"]) for r in trn], ytr)
                preds["headB"] = [predict2(w, xB(r["g"], r["level"])) for r in tst]
                preds["constant"] = [sum(ytr) / len(ytr)] * len(tst)
                # zero-information twin of the GRADE column
                gp = [r["g"] for r in trn]
                rng.shuffle(gp)
                w = fit_logistic2([xB(g, r["level"]) for g, r in zip(gp, trn)], ytr)
                gpt = [r["g"] for r in tst]
                rng.shuffle(gpt)
                preds["perm_grade"] = [predict2(w, xB(g, r["level"])) for g, r in zip(gpt, tst)]
                # zero-information twin of the LEVEL column (what head B adds over A)
                lp = [r["level"] for r in trn]
                rng.shuffle(lp)
                w = fit_logistic2([xB(r["g"], l) for l, r in zip(lp, trn)], ytr)
                lpt = [r["level"] for r in tst]
                rng.shuffle(lpt)
                preds["perm_level"] = [predict2(w, xB(r["g"], l)) for l, r in zip(lpt, tst)]
                for k in keys:
                    acc[k].append(G.logloss(preds[k], yte))
                    accb[k].append(G.brier(preds[k], yte))
        for k in keys:
            if acc[k]:
                boot[k].append(sum(acc[k]) / len(acc[k]))
                boot_brier[k].append(sum(accb[k]) / len(accb[k]))
        if (d + 1) % 50 == 0:
            print(f"  boot {d+1}/{B}", flush=True)

    def ci(v):
        v = sorted(v)
        return {"mean": round(sum(v) / len(v), 5),
                "lo95": round(v[int(0.025 * (len(v) - 1))], 5),
                "hi95": round(v[int(0.975 * (len(v) - 1))], 5), "B": len(v)}

    def dci(a, b):
        v = sorted(x - y for x, y in zip(boot[a], boot[b]))
        return {"mean": round(sum(v) / len(v), 5),
                "lo95": round(v[int(0.025 * (len(v) - 1))], 5),
                "hi95": round(v[int(0.975 * (len(v) - 1))], 5),
                "P(>0)": round(sum(1 for x in v if x > 0) / len(v), 4)}

    rep = {"B": B, "logloss": {k: ci(boot[k]) for k in keys},
           "brier": {k: ci(boot_brier[k]) for k in keys},
           "deltas_logloss": {
               "incumbent - headB": dci("incumbent", "headB"),
               "incumbent - headA": dci("incumbent", "headA"),
               "headA - headB": dci("headA", "headB"),
               "constant - headB": dci("constant", "headB"),
               "perm_grade - headB": dci("perm_grade", "headB"),
               "perm_level - headB": dci("perm_level", "headB"),
               "incumbent - constant": dci("incumbent", "constant"),
               "incumbent - perm_grade": dci("incumbent", "perm_grade"),
               "incumbent - perm_level": dci("incumbent", "perm_level"),
           }}

    # ---- label-permutation null on (constant - headB) ------------------------
    null = []
    for _ in range(500):
        per = []
        for s in ("hit", "pit"):
            side_rows = [r for r in rows if r["side"] == s]
            ys = [r["y"] for r in side_rows]
            rng.shuffle(ys)
            for r, y in zip(side_rows, ys):
                r["_yp"] = y
            for hold in G.PRIMARY_YEARS:
                trn = [r for r in side_rows if r["year"] != hold]
                tst = [r for r in side_rows if r["year"] == hold]
                ytr = [r["_yp"] for r in trn]
                yte = [r["_yp"] for r in tst]
                w = fit_logistic2([xB(r["g"], r["level"]) for r in trn], ytr)
                pb = [predict2(w, xB(r["g"], r["level"])) for r in tst]
                k = sum(ytr) / len(ytr)
                per.append(G.logloss([k] * len(tst), yte) - G.logloss(pb, yte))
        null.append(sum(per) / len(per))
    null.sort()
    rep["label_permutation_null_constant_minus_headB"] = {
        "p50": round(null[len(null) // 2], 5), "p95": round(null[int(0.95 * (len(null) - 1))], 5),
        "p99": round(null[int(0.99 * (len(null) - 1))], 5), "n": len(null)}

    # ---- final point head ----------------------------------------------------
    head = {}
    for s in ("hit", "pit"):
        side_rows = [r for r in rows if r["side"] == s]
        w = fit_logistic2([xB(r["g"], r["level"]) for r in side_rows], [r["y"] for r in side_rows])
        head[s] = {"a": round(w[0], 6), "b_grade": round(w[1], 6), "c_level": round(w[2], 6),
                   "n": len(side_rows), "n_bust": sum(r["y"] for r in side_rows),
                   "monotone_grade_down": w[1] < 0, "monotone_level_down": w[2] < 0}
    rep["head"] = head

    # ---- OOF calibration by grade band and by level ---------------------------
    cal = {}
    for s in ("hit", "pit"):
        side_rows = [r for r in rows if r["side"] == s]
        bands, lvls = {}, {}
        for hold in G.PRIMARY_YEARS:
            trn = [r for r in side_rows if r["year"] != hold]
            tst = [r for r in side_rows if r["year"] == hold]
            w = fit_logistic2([xB(r["g"], r["level"]) for r in trn], [r["y"] for r in trn])
            for r in tst:
                p = predict2(w, xB(r["g"], r["level"]))
                g = r["g"]
                bk = ("20-30" if g < 30 else "30-35" if g < 35 else "35-40" if g < 40
                      else "40-45" if g < 45 else "45+")
                for store, key in ((bands, bk), (lvls, r["level"])):
                    d = store.setdefault(key, {"n": 0, "obs": 0, "inc": 0.0, "cand": 0.0})
                    d["n"] += 1
                    d["obs"] += r["y"]
                    d["inc"] += G.inc(g, s == "pit")
                    d["cand"] += p
        fmt = lambda st: {k: {"n": v["n"], "observed": round(v["obs"] / v["n"], 4),
                              "incumbent": round(v["inc"] / v["n"], 4),
                              "headB_oof": round(v["cand"] / v["n"], 4)}
                          for k, v in sorted(st.items())}
        cal[s] = {"by_grade_band": fmt(bands), "by_level": fmt(lvls)}
    rep["oof_calibration_headB"] = cal

    (HERE / "gate3_report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()

# SCRATCH LAB (combinatorial-archetype lane, SWEEP sub-lane). READ-ONLY.
# Closing analysis: named ad-hoc hypotheses (the owner's Bradfield stratum), selection
# stability across nested folds, and the descriptive archetype table that is the only
# part of this sweep with any product value.
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from _comb_sweep import (OUT, ARMS, build, crossfit, populations,          # noqa: E402
                         residual_arms, welch_t)


def named(D, idx, R, mask, label):
    m = mask.astype(float)
    out = {"label": label, "n": int(m.sum())}
    if m.sum() < 5:
        return out
    for a in ARMS:
        t, m1, m2, n, se = welch_t(m[:, None], R[a])
        sd = float(np.std(R[a][m > 0], ddof=1))
        out[a] = {"mean": round(float(m1[0]), 4), "rest": round(float(m2[0]), 4),
                  "t": round(float(t[0]), 3),
                  "ci95": [round(float(m1[0] - 1.96 * sd / np.sqrt(m.sum())), 4),
                           round(float(m1[0] + 1.96 * sd / np.sqrt(m.sum())), 4)]}
    sub = idx[mask]
    comp = sub[D["complete"][sub]]
    if len(comp):
        ys = np.sort(D["res"][comp])
        out["complete"] = {"n": int(len(comp)), "mean_war": round(float(ys.mean()), 3),
                           "median_war": round(float(np.median(ys)), 3),
                           "bust_rate": round(float((~D["deb"][comp]).mean()), 3),
                           "war_mean_ci95": [
                               round(float(ys.mean() - 1.96 * ys.std(ddof=1)
                                           / np.sqrt(len(ys))), 3),
                               round(float(ys.mean() + 1.96 * ys.std(ddof=1)
                                           / np.sqrt(len(ys))), 3)]}
    return out


def main():
    D = build("hit")
    A = D["axes"]
    mask, _ = populations(D)["TRACK"]
    idx = np.flatnonzero(mask)
    pred = crossfit(D)
    R = residual_arms(D, idx, pred)
    rows = D["rows"]

    def ax(name):
        return np.array([A[name][i] for i in idx])

    def mb(key):
        return np.array([(rows[i].get("milb") or {}).get(key) for i in idx], dtype=object)

    ops = np.array([float((rows[i].get("milb") or {}).get("ops_rel") or 0.0) for i in idx])
    age = np.array([float((rows[i].get("milb") or {}).get("age") or 0.0) for i in idx])
    lvl = ax("level")
    spd = np.array([rows[i].get("tool_speed") for i in idx], dtype=object)

    out = {"named_hypotheses": [], "note":
           "These are NAMED ad-hoc hypotheses evaluated AFTER the pre-registered sweep. "
           "They are not part of the 46,820-hypothesis family and carry no correction of "
           "their own; they are reported because the owner asked about this exact case."}
    tests = [
        ("BRADFIELD exact: AAA & age>=23.5 & ops_rel<0",
         (lvl == "AAA") & (age >= 23.5) & (ops < 0)),
        ("AAA & age>=23.5", (lvl == "AAA") & (age >= 23.5)),
        ("AAA & ops_rel<0", (lvl == "AAA") & (ops < 0)),
        ("age>=23.5 & ops_rel<0", (age >= 23.5) & (ops < 0)),
        ("speed 70+ (burner)", np.array([s is not None and float(s) >= 67.5
                                         for s in spd])),
        ("burner & ops_rel<0", np.array([s is not None and float(s) >= 67.5
                                         for s in spd]) & (ops < 0)),
        ("burner & AAA", np.array([s is not None and float(s) >= 67.5
                                   for s in spd]) & (lvl == "AAA")),
        ("burner & age>=23.5", np.array([s is not None and float(s) >= 67.5
                                         for s in spd]) & (age >= 23.5)),
    ]
    for label, m in tests:
        out["named_hypotheses"].append(named(D, idx, R, m, label))
        r = out["named_hypotheses"][-1]
        if r["n"] >= 5:
            c = r.get("complete", {})
            print("%-46s n=%3d  complete n=%3d meanWAR %s ci %s med %s bust %s"
                  % (label, r["n"], c.get("n", 0), c.get("mean_war"),
                     c.get("war_mean_ci95"), c.get("median_war"), c.get("bust_rate")))
            print("%48s R_cal t%+6.2f mean%+7.3f ci %s | R_flr t%+6.2f | R_rkcal t%+6.2f"
                  % ("", r["R_cal"]["t"], r["R_cal"]["mean"], r["R_cal"]["ci95"],
                     r["R_flr"]["t"], r["R_rkcal"]["t"]))
        else:
            print("%-46s n=%3d  BELOW REPORTING FLOOR" % (label, r["n"]))

    # ---- selection stability across the nested folds
    print("\nSELECTION STABILITY (nested folds, k=1):")
    for f in sorted(OUT.glob("nested_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        ids = [x["k1_id"] for x in d["per_fold"]["real"]]
        axes = [set(p.split("=")[0] for p in i.split("|")) for i in ids]
        pair = [len(a & b) / len(a | b) for i, a in enumerate(axes)
                for b in axes[i + 1:]]
        print("  %-34s %d folds, %d distinct picks, mean pairwise axis Jaccard %.3f"
              % (f.stem, len(ids), len(set(ids)), float(np.mean(pair)) if pair else 0.0))
        d["selection_stability"] = {"distinct": len(set(ids)), "folds": len(ids),
                                    "axis_jaccard": float(np.mean(pair)) if pair else None}
        f.write_text(json.dumps(d, indent=1), encoding="utf-8")

    (OUT / "named_hypotheses_hit.json").write_text(json.dumps(out, indent=1),
                                                   encoding="utf-8")


if __name__ == "__main__":
    main()

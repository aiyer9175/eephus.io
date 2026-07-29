"""ADVERSARIAL VERIFY of the crossmodel lane's N1 (typical-age-table unification).

Independent harness. Differences from tools/_am_crossmodel_lab.py:
  1. Rebuilds age_rel_level from RAW age and level and RE-APPLIES the shipped
     +/-3.5 cap (efv_dataset.py:412-414). The lane's lab added a per-level DELTA
     to the already-capped stored value and never re-clipped, so its "site" arm
     is not the arm Patch 1 would actually ship.
  2. Bootstraps the constant-zero arm too (the lane only had a point estimate).
  3. Adds a POWER probe: how large a synthetic per-level shift would have to be
     before this evaluator could see it at all.
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import efv_model as em  # noqa: E402

EFV = {"DSL": 18.0, "CPX": 19.0, "A": 20.0, "A+": 21.0, "AA": 22.5, "AAA": 24.0}
SITE = {"DSL": 18.0, "CPX": 18.5, "A": 21.0, "A+": 22.0, "AA": 23.0, "AAA": 24.0}
CAP = 3.5


def load(side):
    p = ROOT / "data" / ("xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json")
    return json.loads(p.read_text(encoding="utf-8"))


def rebuild(rows, table=None, mode="table", rng=None, scale=1.0):
    """mode: 'table' (recompute from raw age with cap) | 'perm' | 'zero'"""
    vals = [(r.get("milb") or {}).get("age_rel_level") for r in rows]
    idx = list(range(len(rows)))
    if mode == "perm":
        rng.shuffle(idx)
    out = []
    for i, r in enumerate(rows):
        m = dict(r.get("milb") or {})
        lv, ag = m.get("milb_level"), m.get("age")
        if mode == "perm":
            m["age_rel_level"] = vals[idx[i]]
        elif mode == "zero":
            m["age_rel_level"] = 0.0
        else:
            if lv in table and ag is not None:
                base = EFV[lv] + scale * (table[lv] - EFV[lv])
                m["age_rel_level"] = max(-CAP, min(CAP, ag - base))
        r2 = dict(r)
        r2["milb"] = m
        out.append(r2)
    return out


def fwd(rows, side, lam):
    is_pit = side == "pit"
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    keys, _m = em._feature_spec(side)
    data = em._prep(pool, "target_censored", side)
    pairs = []
    for yr in em.SCORED_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = em._fit_ols_fv(tr)
        ridge = em._fit_ridge(tr, keys)
        if not (ols and ridge):
            continue
        for r in te:
            p = (1 - lam) * max(0.0, em._pred_ols(ols, r["fv"])) + lam * em._predict(ridge, r["feats"])
            pairs.append((p, r["target"], yr))
    return pairs


def rho(pairs):
    if len(pairs) < 8:
        return None
    return em._spearman([p for p, _, _ in pairs], [t for _, t, _ in pairs])


def summ(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return {"mean": round(sum(xs) / n, 5),
            "ci95": [round(xs[int(.025 * n)], 5), round(xs[min(n - 1, int(.975 * n))], 5)],
            "abs_p95": round(sorted(abs(x) for x in xs)[int(.95 * n)], 5), "n": n}


def main():
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    rng = random.Random(4242)
    raw = {"hit": load("hit"), "pit": load("pit")}
    lam = {"hit": em.blend_lambda("hit"), "pit": em.blend_lambda("pit")}
    print("lambdas", lam)

    # sanity: rebuilding with the eFV table must reproduce the shipped column exactly
    for s in ("hit", "pit"):
        rb = rebuild(raw[s], EFV)
        d = max(abs(((a.get("milb") or {}).get("age_rel_level") or 0.0)
                    - ((b.get("milb") or {}).get("age_rel_level") or 0.0))
                for a, b in zip(rb, raw[s]))
        print(f"  self-reconstruction max abs diff {s}: {d:.2e}")

    arms = {}
    arms["base"] = {s: rebuild(raw[s], EFV) for s in ("hit", "pit")}
    arms["site"] = {s: rebuild(raw[s], SITE) for s in ("hit", "pit")}
    arms["perm"] = {s: rebuild(raw[s], EFV, mode="perm", rng=rng) for s in ("hit", "pit")}
    arms["zero"] = {s: rebuild(raw[s], EFV, mode="zero") for s in ("hit", "pit")}
    # POWER probe: 4x the real table divergence
    arms["site4x"] = {s: rebuild(raw[s], SITE, scale=4.0) for s in ("hit", "pit")}

    # how many rows actually move, and by how much
    for s in ("hit", "pit"):
        moved = [abs(((a.get("milb") or {}).get("age_rel_level") or 0.0)
                     - ((b.get("milb") or {}).get("age_rel_level") or 0.0))
                 for a, b in zip(arms["site"][s], arms["base"][s])]
        nz = [m for m in moved if m > 1e-9]
        print(f"  {s}: rows changed by SITE table = {len(nz)}/{len(moved)} "
              f"({100*len(nz)/len(moved):.1f}%), mean |shift| among changed {st.mean(nz):.3f}")

    print("\n--- POINT (forward-chained shipped blend) ---")
    point = {}
    for k, vv in arms.items():
        ph = fwd(vv["hit"], "hit", lam["hit"])
        pp = fwd(vv["pit"], "pit", lam["pit"])
        point[k] = {"hit": rho(ph), "pit": rho(pp), "n_hit": len(ph), "n_pit": len(pp)}
        print(f"  {k:8s} hit {point[k]['hit']:.5f}  pit {point[k]['pit']:.5f} "
              f"(n {len(ph)}/{len(pp)})")

    print(f"\n--- PAIRED BOOTSTRAP B={B} (whole-pool resample, refit per draw) ---")
    keys = ["site", "perm", "zero", "site4x"]
    d = {k: {"hit": [], "pit": []} for k in keys}
    nh, np_ = len(raw["hit"]), len(raw["pit"])
    for b in range(B):
        ih = [rng.randrange(nh) for _ in range(nh)]
        ip = [rng.randrange(np_) for _ in range(np_)]
        res = {}
        for k in ["base"] + keys:
            res[k] = (rho(fwd([arms[k]["hit"][i] for i in ih], "hit", lam["hit"])),
                      rho(fwd([arms[k]["pit"][i] for i in ip], "pit", lam["pit"])))
        for k in keys:
            for j, s in ((0, "hit"), (1, "pit")):
                if res[k][j] is not None and res["base"][j] is not None:
                    d[k][s].append(res[k][j] - res["base"][j])
        if (b + 1) % 25 == 0:
            print(f"   ... {b+1}")

    out = {"point": point, "delta_vs_base": {k: {s: summ(v[s]) for s in ("hit", "pit")}
                                             for k, v in d.items()},
           "lambdas": lam, "B": B}
    print(json.dumps(out["delta_vs_base"], indent=1))
    (ROOT / "data" / "_av_agelevel_verify.json").write_text(json.dumps(out, indent=1),
                                                            encoding="utf-8")
    print("wrote data/_av_agelevel_verify.json")


if __name__ == "__main__":
    main()

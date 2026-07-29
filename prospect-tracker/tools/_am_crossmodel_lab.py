"""CROSSMODEL LANE lab. READ-ONLY on shipped modules (imports only).

Tests the accuracy cost of unifying the duplicated "typical age at level" table.
efv_dataset._TYPICAL_LEVEL_AGE disagrees with the four other live copies
(level_norms.FALLBACK_AGE_BASELINE, age_level.LEVEL_BASELINES, eta.EXPECTED_AGES,
spotlights._SPOTLIGHT_AGE_BASELINES), which all agree with each other.

age_rel_level = age - TABLE[level], so switching tables is an additive per-level
shift of an existing column: no refeed of the dataset builder needed.

Protocol per docs/EFV_GATE_STANDARD.md:
  - forward-chained folds (SCORED_YEARS), shipped blend leg
  - paired bootstrap resampling the WHOLE pool with a refit per draw
  - zero-information control: the SAME column, row-permuted
  - permutation null band
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_model as em  # noqa: E402

EFV_TABLE = {"DSL": 18.0, "CPX": 19.0, "A": 20.0, "A+": 21.0, "AA": 22.5, "AAA": 24.0}
SITE_TABLE = {"DSL": 18.0, "CPX": 18.5, "A": 21.0, "A+": 22.0, "AA": 23.0, "AAA": 24.0}
DELTA = {k: EFV_TABLE[k] - SITE_TABLE[k] for k in EFV_TABLE}   # add to age_rel to convert


def load(side):
    p = ROOT / "data" / ("xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json")
    return json.loads(p.read_text(encoding="utf-8"))


def variant(rows, mode, rng=None):
    """mode: 'base' | 'site' | 'perm' | 'zero'"""
    out = []
    vals = []
    for r in rows:
        mb = dict(r.get("milb") or {})
        vals.append(mb.get("age_rel_level"))
    if mode == "perm":
        idx = list(range(len(rows)))
        rng.shuffle(idx)
    for i, r in enumerate(rows):
        r2 = dict(r)
        mb = dict(r.get("milb") or {})
        lv = mb.get("milb_level")
        cur = mb.get("age_rel_level")
        if mode == "site":
            if cur is not None and lv in DELTA:
                mb["age_rel_level"] = float(cur) + DELTA[lv]
        elif mode == "perm":
            mb["age_rel_level"] = vals[idx[i]]
        elif mode == "zero":
            mb["age_rel_level"] = 0.0
        r2["milb"] = mb
        out.append(r2)
    return out


def fwd_blend_pairs(rows, side, lam):
    """Forward-chained shipped-blend (pred, target) pairs over SCORED_YEARS."""
    is_pit = side == "pit"
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    keys, _m = em._feature_spec(side)
    data = em._prep(pool, "target_censored", side)
    pairs = []
    for yr in em.SCORED_YEARS:
        train = [r for r in data if r["decision_year"] < yr]
        test = [r for r in data if r["decision_year"] == yr]
        if len(test) < 15 or len(train) < 60:
            continue
        ols = em._fit_ols_fv(train)
        ridge = em._fit_ridge(train, keys)
        if not (ols and ridge):
            continue
        for r in test:
            p = (1 - lam) * max(0.0, em._pred_ols(ols, r["fv"])) + lam * em._predict(ridge, r["feats"])
            pairs.append((p, r["target"], yr))
    return pairs


def spearman(pairs):
    if len(pairs) < 8:
        return None
    return em._score([(p, t) for p, t, _ in pairs]).get("spearman")


def block_rho(pairs_h, pairs_p):
    """(side x cohort-year) block-normalised pooled Spearman, both sides pooled."""
    import statistics as st
    rows = []
    for side, pr in (("hit", pairs_h), ("pit", pairs_p)):
        by = {}
        for p, t, yr in pr:
            by.setdefault((side, yr), []).append((p, t))
        for k, v in by.items():
            if len(v) < 5:
                continue
            pr_ = [x[0] for x in v]
            tr_ = [x[1] for x in v]
            for arr in (pr_, tr_):
                pass
            rp = _rank(pr_)
            rt = _rank(tr_)
            mp, sp = st.mean(rp), (st.pstdev(rp) or 1.0)
            mt, sd = st.mean(rt), (st.pstdev(rt) or 1.0)
            for a, b in zip(rp, rt):
                rows.append(((a - mp) / sp, (b - mt) / sd))
    if len(rows) < 20:
        return None
    return _pearson([r[0] for r in rows], [r[1] for r in rows])


def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    rk = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            rk[order[k]] = avg
        i = j + 1
    return rk


def _pearson(a, b):
    n = len(a)
    ma = sum(a) / n
    mb = sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((y - mb) ** 2 for y in b) ** 0.5
    return num / (da * db) if da and db else None


def main():
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    rng = random.Random(20260725)
    raw = {"hit": load("hit"), "pit": load("pit")}
    lam = {"hit": em.blend_lambda("hit"), "pit": em.blend_lambda("pit")}
    print("lambda", lam)
    print("DELTA (add to age_rel_level to go eFV-table -> site-table):", DELTA)

    # level distribution of the eFV pool
    from collections import Counter
    for side in ("hit", "pit"):
        c = Counter((r.get("milb") or {}).get("milb_level") for r in raw[side])
        print(side, "level mix:", dict(c))

    variants = {}
    for mode in ("base", "site", "perm", "zero"):
        variants[mode] = {s: variant(raw[s], mode, rng) for s in ("hit", "pit")}

    point = {}
    for mode, vv in variants.items():
        ph = fwd_blend_pairs(vv["hit"], "hit", lam["hit"])
        pp = fwd_blend_pairs(vv["pit"], "pit", lam["pit"])
        point[mode] = {"hit_rho": spearman(ph), "pit_rho": spearman(pp),
                       "block_rho": block_rho(ph, pp),
                       "n_hit": len(ph), "n_pit": len(pp)}
    print("\n--- POINT ESTIMATES (forward-chained shipped blend) ---")
    for m, v in point.items():
        print("  %-5s hit_rho %.5f  pit_rho %.5f  block_rho %.5f  (n %d/%d)"
              % (m, v["hit_rho"] or 0, v["pit_rho"] or 0, v["block_rho"] or 0,
                 v["n_hit"], v["n_pit"]))

    # paired bootstrap: resample WHOLE pool (train+test), refit each draw
    print("\n--- PAIRED BOOTSTRAP (B=%d, whole-pool resample, refit per draw) ---" % B)
    deltas = {"site": {"hit": [], "pit": [], "block": []},
              "perm": {"hit": [], "pit": [], "block": []}}
    nh, np_ = len(raw["hit"]), len(raw["pit"])
    for b in range(B):
        ih = [rng.randrange(nh) for _ in range(nh)]
        ip = [rng.randrange(np_) for _ in range(np_)]
        res = {}
        for mode in ("base", "site", "perm"):
            rh = [variants[mode]["hit"][i] for i in ih]
            rp = [variants[mode]["pit"][i] for i in ip]
            ph = fwd_blend_pairs(rh, "hit", lam["hit"])
            pp = fwd_blend_pairs(rp, "pit", lam["pit"])
            res[mode] = (spearman(ph), spearman(pp), block_rho(ph, pp))
        for mode in ("site", "perm"):
            for k, i in (("hit", 0), ("pit", 1), ("block", 2)):
                if res[mode][i] is not None and res["base"][i] is not None:
                    deltas[mode][k].append(res[mode][i] - res["base"][i])
        if (b + 1) % 50 == 0:
            print("   ... %d draws" % (b + 1))

    def summ(xs):
        xs = sorted(x for x in xs if x is not None)
        if not xs:
            return None
        n = len(xs)
        mean = sum(xs) / n
        lo = xs[int(0.025 * n)]
        hi = xs[min(n - 1, int(0.975 * n))]
        p_pos = sum(1 for x in xs if x > 0) / n
        mde95 = sorted(abs(x) for x in xs)[int(0.95 * n)]
        return {"mean": round(mean, 5), "ci95": [round(lo, 5), round(hi, 5)],
                "P_improves": round(p_pos, 3), "abs_p95": round(mde95, 5), "n": n}

    out = {"point": point, "delta_vs_base": {}}
    for mode in ("site", "perm"):
        out["delta_vs_base"][mode] = {k: summ(v) for k, v in deltas[mode].items()}
    print(json.dumps(out["delta_vs_base"], indent=1))
    (ROOT / "data" / "_am_crossmodel_agelevel_eval.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    print("\nwrote data/_am_crossmodel_agelevel_eval.json")


if __name__ == "__main__":
    main()

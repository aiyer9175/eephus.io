"""Phase C age-pipeline gate lab (docs/efv-2026-07-30/EFV_LANE_GATES.md).

Independent harness in the shape of tools/_av_agelevel_verify.py, extended for the
arms that verify actually needs:

  base        reproduce the shipped milb.age / milb.age_rel_level columns EXACTLY
              (integer StatsAPI age, static _TYPICAL_LEVEL_AGE, hard +/-3.5 clip).
              Self-reconstruction is asserted before anything else runs.
  c1          C1: DECIMAL season-midpoint age from birth_date, everywhere (the dead
              branch at efv_dataset.py:396-401 made live). age_rel_level rebuilt off it.
  c1_permfrac ZERO-INFORMATION CONTROL for C1: integer age plus a ROW-PERMUTED
              fractional part. Identical marginal to c1, zero information about the row.
              This is the control the earlier decimal probe never had.
  c2          C2: the prospect-filtered decimal per-level norm table (tools/_c_agenorms.py)
              in place of _TYPICAL_LEVEL_AGE. Integer age, so C2 is measured alone.
  c2_perm     zero-info control for C2 (age_rel_level row-permuted).
  c2_zero     age_rel_level identically 0 (the _av zero arm; kills the feature).
  c1c2        the coupled ship candidate.
  c3clip      C3: SOFT saturation in place of the hard +/-3.5 clip, same effective range.
  c1c2c3      everything.
  c4a_pitdrop C4(a): drop `age` from the PITCHER feature set (pit arms only).

Metrics: forward-chained pooled Spearman of the shipped guarded blend, over a WIDE
chain (>= 4 independent time splits, gate standard section 2.4) and over SCORED_YEARS
for comparability with the shipped evals; per-fold breakdown; FV45-fringe t45; paired
bootstrap resampling the WHOLE pool with a refit per draw; permutation null band.

Offline, read-only unless --write.
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_model as em                                     # noqa: E402
from efv_dataset import _TYPICAL_LEVEL_AGE, AGE_CONFLICT_MAX_YR   # noqa: E402

DATA = ROOT / "data"
CAP = 3.5
WIDE_FOLDS = (2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024)

# C2 candidate table: prospect-filtered DECIMAL per-level medians,
# tools/_c_agenorms.py (32,616 qualified prospect-season-level rows, 2014-2026).
C2_NORMS = {"DSL": 18.10, "CPX": 19.58, "A": 21.45, "A+": 22.77, "AA": 24.08, "AAA": 25.86}


def load(side):
    p = DATA / ("xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json")
    return json.loads(p.read_text(encoding="utf-8"))


def _decimal_age(birth_date, season):
    if not birth_date or season is None:
        return None
    try:
        b = date.fromisoformat(str(birth_date)[:10])
    except (TypeError, ValueError):
        return None
    return round((date(int(season), 6, 30) - b).days / 365.25, 1)


def _soft(x, cap=CAP):
    """Smooth saturation with the same effective range as the hard clip: odd,
    monotone, identity-to-first-order near 0, asymptotic to +/-cap.
    tanh scaled so d/dx = 1 at x = 0 -> small age gaps are untouched and only the
    extremes bend, instead of 489 old-for-level rows piling onto one pinned value."""
    import math
    return cap * math.tanh(x / cap)


def rebuild(rows, *, decimal=False, norms=None, soft=False, mode="table", rng=None):
    """Recompute milb.age / milb.age_rel_level for every row. mode:
    'table' | 'permfrac' | 'perm_arl' | 'zero_arl'."""
    tbl = norms or _TYPICAL_LEVEL_AGE
    fracs, arls = [], []
    if mode == "permfrac":
        for r in rows:
            m = r.get("milb") or {}
            d = _decimal_age(r.get("birth_date"), m.get("milb_season"))
            fracs.append(0.0 if d is None else d - int(d))
        rng.shuffle(fracs)
    out = []
    for i, r in enumerate(rows):
        m = dict(r.get("milb") or {})
        lv = m.get("milb_level")
        age = m.get("age")
        if mode == "permfrac":
            age = None if age is None else float(int(float(age))) + fracs[i]
        elif decimal:
            # mirror the SHIPPED precedence + conflict guard (efv_dataset C1)
            d = _decimal_age(r.get("birth_date"), m.get("milb_season"))
            if d is not None and (age is None
                                  or abs(d - float(age)) <= AGE_CONFLICT_MAX_YR):
                age = d
        if age is not None:
            m["age"] = age
            if lv in tbl:
                arl = float(age) - tbl[lv]
                m["age_rel_level"] = _soft(arl) if soft else max(-CAP, min(CAP, arl))
        arls.append(m.get("age_rel_level"))
        r2 = dict(r)
        r2["milb"] = m
        out.append(r2)
    if mode in ("perm_arl", "zero_arl"):
        idx = list(range(len(out)))
        if mode == "perm_arl":
            rng.shuffle(idx)
        for i, r2 in enumerate(out):
            m = dict(r2["milb"])
            m["age_rel_level"] = 0.0 if mode == "zero_arl" else arls[idx[i]]
            r2["milb"] = m
    return out


def fwd(rows, side, lam, folds, keys=None):
    """Forward-chained shipped blend. Returns [(pred, target, year, fv)]."""
    is_pit = side == "pit"
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    if keys is None:
        keys, _m = em._feature_spec(side)
    data = em._prep(pool, "target_censored", side)
    pairs = []
    for yr in folds:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = em._fit_ols_fv(tr)
        ridge = em._fit_ridge(tr, keys)
        if not (ols and ridge):
            continue
        for r in te:
            p = ((1 - lam) * max(0.0, em._pred_ols(ols, r["fv"]))
                 + lam * em._predict(ridge, r["feats"]))
            pairs.append((p, r["target"], yr, r["fv"]))
    return pairs


def rho(pairs):
    if len(pairs) < 8:
        return None
    return em._spearman([p for p, _, _, _ in pairs], [t for _, t, _, _ in pairs])


def t45(pairs):
    """FV45-fringe cut: rows with consensus FV in [42.5, 47.5)."""
    sub = [p for p in pairs if 42.5 <= p[3] < 47.5]
    return rho(sub)


def block_rho(pairs):
    """Fold-block-normalized pooled Spearman: rank within each fold, then pool."""
    from collections import defaultdict
    by = defaultdict(list)
    for i, p in enumerate(pairs):
        by[p[2]].append(i)
    xs, ys = [], []

    def _ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        out = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0
            for k in range(i, j + 1):
                out[order[k]] = avg
            i = j + 1
        n = max(1, len(v) - 1)
        return [r / n for r in out]

    for _yr, idxs in by.items():
        if len(idxs) < 5:
            continue
        xs += _ranks([pairs[i][0] for i in idxs])
        ys += _ranks([pairs[i][1] for i in idxs])
    if len(xs) < 8:
        return None
    return em._spearman(xs, ys)


def summ(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return {"mean": round(sum(xs) / n, 5),
            "ci95": [round(xs[int(.025 * n)], 5), round(xs[min(n - 1, int(.975 * n))], 5)],
            "p_positive": round(sum(1 for x in xs if x > 0) / n, 3), "n": n}


def build_arms(raw, rng):
    arms = {}
    arms["base"] = {s: rebuild(raw[s]) for s in ("hit", "pit")}
    arms["c1"] = {s: rebuild(raw[s], decimal=True) for s in ("hit", "pit")}
    arms["c1_permfrac"] = {s: rebuild(raw[s], mode="permfrac", rng=rng) for s in ("hit", "pit")}
    arms["c2"] = {s: rebuild(raw[s], norms=C2_NORMS) for s in ("hit", "pit")}
    arms["c2_perm"] = {s: rebuild(raw[s], norms=C2_NORMS, mode="perm_arl", rng=rng)
                       for s in ("hit", "pit")}
    arms["c2_zero"] = {s: rebuild(raw[s], mode="zero_arl") for s in ("hit", "pit")}
    arms["c1c2"] = {s: rebuild(raw[s], decimal=True, norms=C2_NORMS) for s in ("hit", "pit")}
    arms["c3clip"] = {s: rebuild(raw[s], soft=True) for s in ("hit", "pit")}
    arms["c1c2c3"] = {s: rebuild(raw[s], decimal=True, norms=C2_NORMS, soft=True)
                      for s in ("hit", "pit")}
    return arms


def main():
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    rng = random.Random(20260730)
    raw = {"hit": load("hit"), "pit": load("pit")}
    lam = {"hit": em.blend_lambda("hit"), "pit": em.blend_lambda("pit")}
    print("lambdas", lam, "| rows", {s: len(raw[s]) for s in raw})

    arms = build_arms(raw, rng)

    # ---- self-reconstruction: base MUST equal the shipped columns -----------
    for s in ("hit", "pit"):
        da = max(abs(float((a.get("milb") or {}).get("age") or 0)
                     - float((b.get("milb") or {}).get("age") or 0))
                 for a, b in zip(arms["base"][s], raw[s]))
        dr = max(abs(float((a.get("milb") or {}).get("age_rel_level") or 0)
                     - float((b.get("milb") or {}).get("age_rel_level") or 0))
                 for a, b in zip(arms["base"][s], raw[s]))
        print(f"  self-reconstruction {s}: max|d age| {da:.2e}  max|d age_rel_level| {dr:.2e}")
        assert da < 1e-9 and dr < 1e-9, "base arm does not reproduce the shipped columns"

    # ---- descriptive: what each arm actually moves --------------------------
    desc = {}
    for k in ("c1", "c2", "c1c2", "c3clip"):
        desc[k] = {}
        for s in ("hit", "pit"):
            b, a = arms["base"][s], arms[k][s]
            dage = [abs(float((x.get("milb") or {}).get("age") or 0)
                        - float((y.get("milb") or {}).get("age") or 0)) for x, y in zip(b, a)]
            darl = [abs(float((x.get("milb") or {}).get("age_rel_level") or 0)
                        - float((y.get("milb") or {}).get("age_rel_level") or 0))
                    for x, y in zip(b, a)]
            nz_age = [d for d in dage if d > 1e-9]
            nz_arl = [d for d in darl if d > 1e-9]
            desc[k][s] = {"rows": len(b),
                          "age_moved": len(nz_age),
                          "age_mean_abs": round(st.mean(nz_age), 3) if nz_age else 0.0,
                          "age_max_abs": round(max(nz_age), 3) if nz_age else 0.0,
                          "arl_moved": len(nz_arl),
                          "arl_mean_abs": round(st.mean(nz_arl), 3) if nz_arl else 0.0,
                          "arl_max_abs": round(max(nz_arl), 3) if nz_arl else 0.0}
            print(f"  {k:8s} {s}: age moved {desc[k][s]['age_moved']}/{len(b)} "
                  f"(mean {desc[k][s]['age_mean_abs']}, max {desc[k][s]['age_max_abs']})  "
                  f"age_rel_level moved {desc[k][s]['arl_moved']} "
                  f"(mean {desc[k][s]['arl_mean_abs']}, max {desc[k][s]['arl_max_abs']})")
    # clip census (the C3 argument)
    for s in ("hit", "pit"):
        for k in ("base", "c2"):
            v = [float((r.get("milb") or {}).get("age_rel_level") or 0.0) for r in arms[k][s]]
            print(f"  clip census {k} {s}: pinned +{CAP} = {sum(1 for x in v if x >= CAP - 1e-9)}"
                  f"   pinned -{CAP} = {sum(1 for x in v if x <= -CAP + 1e-9)}"
                  f"   exactly 0.0 = {sum(1 for x in v if abs(x) < 1e-12)}")

    # ---- point estimates ---------------------------------------------------
    print("\n--- POINT (forward-chained, WIDE folds 2017-2024) ---")
    point = {}
    for k, vv in arms.items():
        row = {}
        for s in ("hit", "pit"):
            pr = fwd(vv[s], s, lam[s], WIDE_FOLDS)
            row[s] = {"rho": rho(pr), "block_rho": block_rho(pr), "t45": t45(pr), "n": len(pr)}
        point[k] = row
        print(f"  {k:12s} hit rho {row['hit']['rho']:+.5f} block {row['hit']['block_rho']:+.5f} "
              f"t45 {row['hit']['t45'] if row['hit']['t45'] is None else round(row['hit']['t45'], 4)}"
              f"  |  pit rho {row['pit']['rho']:+.5f} block {row['pit']['block_rho']:+.5f} "
              f"t45 {row['pit']['t45'] if row['pit']['t45'] is None else round(row['pit']['t45'], 4)}")

    print("\n--- POINT (SCORED_YEARS 2020-2023, shipped-eval comparability) ---")
    point_sy = {}
    for k, vv in arms.items():
        row = {s: {"rho": rho(fwd(vv[s], s, lam[s], em.SCORED_YEARS))} for s in ("hit", "pit")}
        point_sy[k] = row
        print(f"  {k:12s} hit {row['hit']['rho']:+.5f}   pit {row['pit']['rho']:+.5f}")

    # ---- C4(a): drop pit `age` --------------------------------------------
    pit_keys_full, _m = em._feature_spec("pit")
    pit_keys_drop = [k for k in pit_keys_full if k != "age"]
    c4 = {}
    for base_arm in ("base", "c2"):
        pr = fwd(arms[base_arm]["pit"], "pit", lam["pit"], WIDE_FOLDS, keys=pit_keys_drop)
        c4[base_arm] = {"rho": rho(pr), "block_rho": block_rho(pr), "t45": t45(pr)}
    print("\n--- C4(a) drop pit `age` (independent re-measure) ---")
    for k, v in c4.items():
        d = v["rho"] - point[k]["pit"]["rho"]
        print(f"  on {k:5s}: rho {v['rho']:+.5f} vs keep {point[k]['pit']['rho']:+.5f} "
              f"-> drop delta {d:+.5f} (pit MDE95 0.016)")

    # ---- per-fold breakdown for the ship candidates ------------------------
    print("\n--- PER-FOLD delta vs base (rho within fold) ---")
    perfold = {}
    for k in ("c1", "c1_permfrac", "c2", "c1c2", "c3clip", "c1c2c3"):
        perfold[k] = {}
        for s in ("hit", "pit"):
            pb = fwd(arms["base"][s], s, lam[s], WIDE_FOLDS)
            pk = fwd(arms[k][s], s, lam[s], WIDE_FOLDS)
            ds = []
            for yr in WIDE_FOLDS:
                a = rho([p for p in pb if p[2] == yr])
                b = rho([p for p in pk if p[2] == yr])
                ds.append(None if (a is None or b is None) else round(b - a, 4))
            perfold[k][s] = ds
            pos = sum(1 for d in ds if d is not None and d > 0)
            tot = sum(1 for d in ds if d is not None)
            print(f"  {k:12s} {s}: {ds}  positive {pos}/{tot}")

    # ---- paired bootstrap (whole pool, refit per draw) ---------------------
    print(f"\n--- PAIRED BOOTSTRAP B={B} (resample TRAIN+TEST, refit each draw) ---")
    keys = [k for k in arms if k != "base"]
    d = {k: {"hit": [], "pit": []} for k in keys}
    nh, npt = len(raw["hit"]), len(raw["pit"])
    for b in range(B):
        ih = [rng.randrange(nh) for _ in range(nh)]
        ip = [rng.randrange(npt) for _ in range(npt)]
        res = {}
        for k in ["base"] + keys:
            res[k] = (rho(fwd([arms[k]["hit"][i] for i in ih], "hit", lam["hit"], WIDE_FOLDS)),
                      rho(fwd([arms[k]["pit"][i] for i in ip], "pit", lam["pit"], WIDE_FOLDS)))
        for k in keys:
            for j, s in ((0, "hit"), (1, "pit")):
                if res[k][j] is not None and res["base"][j] is not None:
                    d[k][s].append(res[k][j] - res["base"][j])
        if (b + 1) % 25 == 0:
            print(f"   ... {b+1}/{B}")
    boot = {k: {s: summ(v[s]) for s in ("hit", "pit")} for k, v in d.items()}
    print(json.dumps(boot, indent=1))

    out = {"generated_at": date.today().isoformat(),
           "harness": "tools/_c_agepipe_lab.py",
           "mde95": {"incremental_feature": {"hit": 0.017, "pit": 0.016},
                     "t45": {"hit": 0.055, "pit": 0.10}},
           "lambdas": lam, "folds_wide": list(WIDE_FOLDS),
           "folds_scored_years": list(em.SCORED_YEARS),
           "c2_norms": C2_NORMS, "static_norms": _TYPICAL_LEVEL_AGE,
           "descriptive": desc, "point_wide": point, "point_scored_years": point_sy,
           "c4a_drop_pit_age": c4, "per_fold_delta": perfold,
           "paired_bootstrap": boot, "B": B}
    if "--write" in sys.argv:
        (DATA / "xfv_agepipe_eval.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("\nwrote data/xfv_agepipe_eval.json")
    else:
        print("\n(dry run; pass --write to persist)")


if __name__ == "__main__":
    main()

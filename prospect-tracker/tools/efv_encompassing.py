"""A-CLAIM-6: forecast encompassing. Does the model leg add anything to consensus?

    y = a + b1*cons_war + b2*model_war + fold fixed effects

fitted OUT OF FOLD on target_censored, per side, on the debuted_km cut. b2 is the whole
question: if the consensus anchor already contains everything the model knows, b2 is zero
and the model leg is decoration on the blend.

REGRESSORS ARE WAR-SCALE OBJECTS ONLY, never the 20-80 grade, and never the blend beside
its own components: blend = (1-lam)*cons + lam*model is an exact linear combination of the
two regressors, so including it is perfect collinearity, not a third opinion.

    cons_war   max(0, ols(consensus_fv))          the consensus anchor
    model_war  max(-2, a + b*ridge(feats))        the SERVED leg (calibrated per fold,
                                                  clamped), which is what oos_grades
                                                  blends and therefore what the board
                                                  is actually carrying

TWO NULLS, both pre-specified.

  1. WITHIN-FOLD PERMUTATION OF THE MODEL RESIDUAL ON CONS. Regress model on cons inside
     each fold, permute the residual within that fold, rebuild model = fit + permuted
     residual. This destroys the model's row-level information while preserving its
     marginal AND its correlation with cons, so the null b2 is what "the model adds
     nothing beyond consensus" looks like at this sample size.
  2. ZERO-INFORMATION TWIN. A Gaussian covariate with the model leg's own mean and sd,
     independent of everything. The estimator must return ~0 on it; if it does not, the
     harness is broken and the real number means nothing.

VERDICT DISCIPLINE, fixed before the run: a player-clustered bootstrap CI covering zero
prints UNDECIDED. Not "small but positive", not "trending". UNDECIDED.
"""
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import efv_model as em                    # noqa: E402
from efv_dataset import matrix_path       # noqa: E402

B_BOOT = 2000
B_NULL = 500
SEED = 20260906


def build(side):
    """Out-of-fold (cons_war, model_war, y, fold, player_key, weight) on debuted_km."""
    keys, _m = em._feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    data = em._prep([r for r in rows if r["kind"] == "debuted"], "target_censored", side)
    out = []
    for yr in em.SCORED_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = em._fit_ols_fv(tr)
        ridge = em._fit_ridge(tr, keys)
        if not (ols and ridge):
            continue
        cal = em._fit_linear_calibration(
            [(em._predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        for r in te:
            out.append({
                "cons": max(0.0, em._pred_ols(ols, r["fv"])),
                "model": max(-2.0, a + b * em._predict(ridge, r["feats"])),
                "y": r["target"],
                "fold": yr,
                "pk": r["player_key"],
                "w": float(r.get("weight") or 1.0),
            })
    return out


def fit_b2(rows):
    """WLS of y on [1, cons, model, fold dummies]; returns (b1, b2) or None.

    Fold fixed effects absorb the level shift between cohort years, so b2 is a
    WITHIN-fold statement and cannot be bought by the model tracking a cohort
    trend the consensus anchor misses.
    """
    if len(rows) < 30:
        return None
    folds = sorted({r["fold"] for r in rows})
    if len(folds) < 2:
        return None
    idx = {f: i for i, f in enumerate(folds[1:])}          # first fold is the base level
    n, k = len(rows), 3 + len(idx)
    X = np.zeros((n, k))
    y = np.empty(n)
    w = np.empty(n)
    for i, r in enumerate(rows):
        X[i, 0] = 1.0
        X[i, 1] = r["cons"]
        X[i, 2] = r["model"]
        j = idx.get(r["fold"])
        if j is not None:
            X[i, 3 + j] = 1.0
        y[i] = r["y"]
        w[i] = r["w"]
    sw = np.sqrt(w)
    try:
        beta, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
    except np.linalg.LinAlgError:
        return None
    return float(beta[1]), float(beta[2])


def permute_model_within_fold(rows, rng):
    """Null 1: keep the model's marginal AND its relation to cons, destroy the row."""
    out = []
    by = defaultdict(list)
    for r in rows:
        by[r["fold"]].append(r)
    for _f, rs in by.items():
        c = np.array([r["cons"] for r in rs])
        m = np.array([r["model"] for r in rs])
        if len(rs) > 2 and c.std() > 0:
            A = np.column_stack([np.ones(len(rs)), c])
            beta, *_ = np.linalg.lstsq(A, m, rcond=None)
            fit = A @ beta
            resid = m - fit
        else:
            fit, resid = m.copy(), np.zeros(len(rs))
        perm = list(resid)
        rng.shuffle(perm)
        for r, f_, e in zip(rs, fit, perm):
            out.append({**r, "model": float(f_ + e)})
    return out


def zero_information_twin(rows, rng):
    """Null 2: the estimator must return ~0 on a covariate that knows nothing."""
    m = np.array([r["model"] for r in rows])
    mu, sd = float(m.mean()), float(m.std()) or 1.0
    return [{**r, "model": rng.gauss(mu, sd)} for r in rows]


def cluster_boot(rows, rng, B):
    """Player-clustered resample. A player can appear on more than one decision
    year, so resampling rows would treat one career as independent evidence
    twice and shrink the interval it has no right to shrink."""
    by = defaultdict(list)
    for r in rows:
        by[r["pk"]].append(r)
    pks = list(by)
    out = []
    for _ in range(B):
        draw = []
        for _ in range(len(pks)):
            draw.extend(by[pks[rng.randrange(len(pks))]])
        got = fit_b2(draw)
        if got:
            out.append(got[1])
    return sorted(out)


def main():
    import datetime as _dt
    report = {"generated_at": _dt.date.today().isoformat(),
              "produced_by": "tools/efv_encompassing.py",
              "frame": "debuted_km, out of fold, fold fixed effects",
              "estimand": "b2 in y = a + b1*cons_war + b2*model_war + fold FE",
              "regressors": {"cons_war": "max(0, ols(consensus_fv))",
                             "model_war": "max(-2, calibrated ridge) = the SERVED leg"},
              "verdict_rule": "a player-clustered CI95 covering zero prints UNDECIDED",
              "B_bootstrap": B_BOOT, "B_null": B_NULL, "sides": {}}
    for side in ("hit", "pit"):
        rows = build(side)
        got = fit_b2(rows)
        if not got:
            continue
        b1, b2 = got
        rng = random.Random(SEED)
        boot = cluster_boot(rows, rng, B_BOOT)
        lo, hi = boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot))]

        rng2 = random.Random(SEED + 1)
        null1 = []
        for _ in range(B_NULL):
            got_n = fit_b2(permute_model_within_fold(rows, rng2))
            if got_n:
                null1.append(got_n[1])
        null1.sort()
        rng3 = random.Random(SEED + 2)
        null2 = []
        for _ in range(B_NULL):
            got_n = fit_b2(zero_information_twin(rows, rng3))
            if got_n:
                null2.append(got_n[1])
        null2.sort()

        n_players = len({r["pk"] for r in rows})
        p_null1 = sum(1 for v in null1 if abs(v) >= abs(b2)) / len(null1) if null1 else None
        verdict = ("UNDECIDED" if lo <= 0.0 <= hi
                   else ("ADDS" if b2 > 0 else "SUBTRACTS"))
        report["sides"][side] = {
            "n_rows": len(rows), "n_players": n_players,
            "b1_consensus": round(b1, 4), "b2_model": round(b2, 4),
            "ci95": [round(lo, 4), round(hi, 4)],
            "null_permuted_model_residual": {
                "mean": round(float(np.mean(null1)), 4) if null1 else None,
                "band95": [round(null1[int(0.025 * len(null1))], 4),
                           round(null1[int(0.975 * len(null1))], 4)] if null1 else None,
                "p_two_sided": round(p_null1, 4) if p_null1 is not None else None,
            },
            "null_zero_information_twin": {
                "mean": round(float(np.mean(null2)), 4) if null2 else None,
                "band95": [round(null2[int(0.025 * len(null2))], 4),
                           round(null2[int(0.975 * len(null2))], 4)] if null2 else None,
            },
            "verdict": verdict,
        }
        print(f"\n{side}  n={len(rows)} rows / {n_players} players")
        print(f"   b1 (consensus) {b1:+.4f}")
        print(f"   b2 (model)     {b2:+.4f}   CI95 [{lo:+.4f}, {hi:+.4f}]   -> {verdict}")
        if null1:
            print(f"   null 1, permuted model residual within fold: mean "
                  f"{np.mean(null1):+.4f}  band95 "
                  f"[{null1[int(.025*len(null1))]:+.4f}, {null1[int(.975*len(null1))]:+.4f}]"
                  f"  p(two-sided) {p_null1:.4f}")
        if null2:
            print(f"   null 2, zero-information twin:               mean "
                  f"{np.mean(null2):+.4f}  band95 "
                  f"[{null2[int(.025*len(null2))]:+.4f}, {null2[int(.975*len(null2))]:+.4f}]")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if out:
        out.write_text(json.dumps(report, indent=1), encoding="utf-8")
        print("\nwrote", out)


if __name__ == "__main__":
    main()

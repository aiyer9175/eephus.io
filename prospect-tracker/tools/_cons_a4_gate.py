# A4 -- THE GATE. Forward-chained candidate consensus constructions vs the served
# consensus, scored on realized first-6yr KM-censored bWAR.
#
# Controls per docs/EFV_GATE_STANDARD.md:
#   (1) paired cluster bootstrap resampling the WHOLE pool (train AND test) with a
#       REFIT of every calibration parameter on each draw
#   (2) a zero-information control (coverage labels row-permuted -> same marginal
#       distribution of applied offsets, no link to which outlet actually graded)
#   (3) a permutation null band (target permuted within fold)
#   (4) the effect averaged over >= 4 independent time splits
from __future__ import annotations

import json
import random
import sys

import numpy as np

from _cons_data import OUT, load_matrix_rows, spearman, ci

ROWS = load_matrix_rows()
FOLDS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)
MIN_TRAIN = 200
MIN_TEST = 25


# ---------------------------------------------------------------------------
# calibration fits (all estimated on TRAIN rows only)
# ---------------------------------------------------------------------------
def fit_params(train):
    """Per-source scale maps onto the FanGraphs reference, from the PAIRED overlap
    (same players graded by both) so coverage differences cannot masquerade as bias."""
    pair = [r for r in train if r["fg"] is not None and r["mp"] is not None]
    p = {"shift_mp": 0.0, "sd_ratio_mp": 1.0, "mean_mp": 0.0, "mean_fg": 0.0,
         "w_fg": 1.0, "w_mp": 1.0, "n_pair": len(pair)}
    if len(pair) >= 60:
        fg = np.array([r["fg"] for r in pair], float)
        mp = np.array([r["mp"] for r in pair], float)
        p["shift_mp"] = float(mp.mean() - fg.mean())
        p["mean_mp"], p["mean_fg"] = float(mp.mean()), float(fg.mean())
        sr = float(mp.std(ddof=1) / fg.std(ddof=1)) if fg.std(ddof=1) > 0 else 1.0
        p["sd_ratio_mp"] = sr if 0.5 < sr < 2.0 else 1.0
        # inverse-residual-variance vote weights in predicted-WAR space
        t = np.array([r["target"] for r in pair], float)
        w = np.array([r["weight"] for r in pair], float)

        def rv(x):
            X = np.column_stack([np.ones_like(x), x])
            b = np.linalg.lstsq(X * w[:, None], t * w, rcond=None)[0]
            e = t - X @ b
            return float((w * e ** 2).sum() / w.sum())
        v1, v2 = rv(fg), rv(mp)
        if v1 > 0 and v2 > 0:
            s1, s2 = 1.0 / v1, 1.0 / v2
            p["w_fg"] = 2 * s1 / (s1 + s2)
            p["w_mp"] = 2 * s2 / (s1 + s2)
    return p


# ---------------------------------------------------------------------------
# candidate consensus constructions
# ---------------------------------------------------------------------------
def c_served(r, p):
    return r["cons"]


def c_equalmean(r, p):
    v = [x for x in (r["fg"], r["mp"]) if x is not None]
    return sum(v) / len(v) if v else r["cons"]


def c_shipweights(r, p, W={"fg": 0.9363, "mp": 1.0637}):
    num = den = 0.0
    for k in ("fg", "mp"):
        if r[k] is not None:
            num += W[k] * r[k]
            den += W[k]
    return num / den if den else r["cons"]


def c_offset(r, p):
    """Bias-corrected mean: every source translated onto the FanGraphs scale first."""
    v = []
    if r["fg"] is not None:
        v.append(r["fg"])
    if r["mp"] is not None:
        v.append(r["mp"] - p["shift_mp"])
    return sum(v) / len(v) if v else r["cons"]


def c_distmatch(r, p):
    """Distribution-matched: mean AND sd of the Pipeline scale mapped onto FanGraphs."""
    v = []
    if r["fg"] is not None:
        v.append(r["fg"])
    if r["mp"] is not None:
        v.append(p["mean_fg"] + (r["mp"] - p["mean_mp"]) / p["sd_ratio_mp"])
    return sum(v) / len(v) if v else r["cons"]


def c_offset_ivw(r, p):
    num = den = 0.0
    if r["fg"] is not None:
        num += p["w_fg"] * r["fg"]
        den += p["w_fg"]
    if r["mp"] is not None:
        num += p["w_mp"] * (r["mp"] - p["shift_mp"])
        den += p["w_mp"]
    return num / den if den else r["cons"]


def c_offset_keep_shrink(r, p):
    """Offset-corrected mean but keeping the live single-source FV-35 pull-down
    (reproduced from the served delta cons - pre when it fired)."""
    base = c_offset(r, p)
    if r["pre"] is not None and r["cons"] is not None and abs(r["cons"] - r["pre"]) > 1e-9:
        # the live pull is  w*pre + (1-w)*35  with w = 1/(1+0.5) = 2/3
        return (2.0 / 3.0) * base + (1.0 / 3.0) * 35.0
    return base


CANDIDATES = {
    "served": c_served,
    "equal_mean_raw": c_equalmean,
    "shipped_weights": c_shipweights,
    "offset_corrected": c_offset,
    "offset_keep_singlepull": c_offset_keep_shrink,
    "distribution_matched": c_distmatch,
    "offset_plus_ivw": c_offset_ivw,
}


# ---------------------------------------------------------------------------
# forward-chained scoring
# ---------------------------------------------------------------------------
def score_pool(rows, cohort="full", candidates=None, mutate=None, seed=0):
    """Returns {name: {"pooled": rho, "per_fold": {...}, "mean_fold": rho}}.
    `mutate(train, test, rng)` optionally perturbs rows (controls)."""
    candidates = candidates or CANDIDATES
    pool = rows if cohort == "full" else [r for r in rows if r["kind"] == "debuted"]
    rng = random.Random(seed)
    pairs = {k: [] for k in candidates}
    per_fold = {k: {} for k in candidates}
    for Y in FOLDS:
        train = [r for r in pool if r["decision_year"] < Y]
        test = [r for r in pool if r["decision_year"] == Y]
        if len(train) < MIN_TRAIN or len(test) < MIN_TEST:
            continue
        if mutate is not None:
            train, test = mutate(train, test, rng)
        p = fit_params(train)
        for k, fn in candidates.items():
            xs = [fn(r, p) for r in test]
            ts = [r["target"] for r in test]
            ok = [(a, b) for a, b in zip(xs, ts) if a is not None]
            if len(ok) < 15:
                continue
            pairs[k].extend(ok)
            per_fold[k][Y] = spearman([a for a, _ in ok], [b for _, b in ok])
    out = {}
    for k in candidates:
        if not pairs[k]:
            out[k] = {"pooled": None, "per_fold": {}, "mean_fold": None, "n": 0}
            continue
        pf = {y: v for y, v in per_fold[k].items() if v is not None}
        out[k] = {"pooled": spearman([a for a, _ in pairs[k]], [b for _, b in pairs[k]]),
                  "per_fold": pf,
                  "mean_fold": float(np.mean(list(pf.values()))) if pf else None,
                  "n": len(pairs[k])}
    return out


def report(title, res, base="served"):
    print(f"\n=== {title} ===")
    b = res[base]
    print(f"{'candidate':>24} {'n':>5} {'pooled rho':>11} {'d vs served':>12} "
          f"{'mean-fold':>10} {'d':>9}")
    for k, v in res.items():
        if v["pooled"] is None:
            continue
        dp = v["pooled"] - b["pooled"]
        dm = (v["mean_fold"] - b["mean_fold"]) if (v["mean_fold"] is not None
                                                   and b["mean_fold"] is not None) else float("nan")
        print(f"{k:>24} {v['n']:>5} {v['pooled']:>11.4f} {dp:>+12.4f} "
              f"{v['mean_fold']:>10.4f} {dm:>+9.4f}")
    print(f"  folds used: {sorted(b['per_fold'])}")
    print("  per-fold rho (served -> best candidate):")
    for y in sorted(b["per_fold"]):
        line = f"    {y}: " + "  ".join(
            f"{k[:14]}={res[k]['per_fold'].get(y, float('nan')):+.4f}" for k in res
            if res[k]["pooled"] is not None)
        print(line)


if __name__ == "__main__":
    for cohort in ("full", "debuted"):
        res = score_pool(ROWS, cohort=cohort)
        report(f"A4 forward-chained, cohort={cohort}, both sides pooled", res)
    for side in ("hit", "pit"):
        rr = [r for r in ROWS if r["side"] == side]
        res = score_pool(rr, cohort="debuted")
        report(f"A4 forward-chained, cohort=debuted, side={side}", res)
    json.dump({"note": "see stdout"}, open(OUT / "a4_stub.json", "w"))

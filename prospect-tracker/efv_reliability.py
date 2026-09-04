# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""C1 — forward-chained reliability/ECE regen for the SHIPPED eFV outcome
distribution, with a drift tripwire.

THE MONITOR WAS GRADING THE WRONG DISTRIBUTION (fixed 2026-08-03). This module
reproduces efv_score's path up to the grade inversion and then read the raw
`p_bucket_given_fv` curve, while the scorer applies the odds-dispersion Platt
map at all three seams (wired 07-31). The public "model grading itself" card
was therefore reporting a pre-fix miscalibration the site no longer serves,
and its tripwire threshold had been tuned to that same pre-fix band - so it
reported "within the documented standing miscalibration band" about a defect
that had already been corrected. Both curve sets are emitted now (`after` =
served, `before` = drift reference) and the tripwire judges `after`.

Background (audit 2026-07-19): `regen_all` refreshes every eFV artifact EXCEPT
the reliability curves — `data/xfv_reliability.json` was last written by the
one-off isotonic lab (`tools/efv_isotonic_lab.py`, a failed pre-registered gate)
and had gone stale (2026-07-01), while showing a real bust-bucket miscalibration
(the low-probability bin predicts ~0.06 but realizes ~0.31). This module makes
the "before"/shipped reliability curves a first-class, nightly-refreshed
artifact and adds a tripwire so a widening calibration gap surfaces.

SAFE / rank-neutral by construction: the reliability curves are a DIAGNOSTIC of
the already-shipped 5-bucket distribution `p_bucket_given_fv`. Nothing here feeds
back into any served eFV/WAR/grade/surplus number — it only measures them. So
this refresh cannot move a published number; it changes only the diagnostic
artifact (which the box regenerates canonically — never commit a locally
regenerated copy, per the degraded-local-data rule).

The heavy OOF machinery is shared with the isotonic lab, but that module does an
`os.chdir(ROOT)` at import time, so we import the underlying pieces directly here
rather than importing the lab (no CWD side effect in the production pipeline)."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

import efv_odds_calibration as _odds_cal

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "xfv_reliability.json"

BUCKETS = ("bust", "bench", "regular", "good", "star")
CHAIN_YEARS = tuple(range(2016, 2024))   # OOF chain (2016-19 seed the calibrators)
MIN_TRAIN, MIN_TEST = 60, 10
MIN_TIER_N = 15
# Realized-outcome bucketing — MUST match tools/efv_isotonic_lab.py exactly, so
# the curves measure the shipped distribution. The bucket is the 6yr-average
# ANNUAL WAR (target_war_6yr / TARGET_SEASONS) binned by the config band edges.
BUCKET_EDGES = (0.5, 1.5, 2.5, 4.0)      # 6yr-avg annual WAR band edges
TARGET_SEASONS = 6.0

# Tripwire: the pooled bust-bucket ECE at which the reliability regen flags a
# miscalibration for review. Judged on the SERVED (post-Platt) curve.
#
# RE-DERIVED 2026-08-03. The old 0.14 was set just above a ~0.12 PRE-Platt
# baseline. Once the map is applied the served bust ECE is 0.0754, so 0.14 was
# 1.9x the value it watched and could not fire for any plausible drift.
#
# Measured on the current tree (forward-chained OOF, pooled n=2825) - the map
# improves every bucket, which is the first confirmation of it on this frame:
#     bucket    after     before
#     bust      0.07540   0.12809
#     bench     0.01603   0.02714
#     regular   0.03298   0.04917
#     good      0.02328   0.04048
#     star      0.00677   0.00939
#
# 0.10 is chosen to sit ~33% above the served baseline (room for fold-to-fold
# drift) AND BELOW the 0.1281 pre-recalibration value. That second property is
# the point: if the Platt map is ever silently dropped from the scoring seams,
# the served curve reverts to ~0.128 and this wire TRIPS. The tripwire now
# regression-tests the calibration it reports on. Rank-neutral: only a flag.
#
# RE-MEASURED 2026-08-07b (plan lane C1, data/xfv_dist_calibration_eval.json).
#
# THE BAR IS NOT STRUCTURALLY BLIND, which corrects the plan's D3 write-up.
# Injecting a top-of-board defect (flipping realized non-bust outcomes to bust
# among tier-50-and-above rows) drives pooled bust ECE to 0.09235 at a +0.148
# signed in-band bust residual and to 0.10794 at +0.285, which TRIPS 0.10. Read
# +0.285 as an UPPER BOUND on the trip point, not the trip point: the injection
# takes the first k eligible rows in list order with no seed and no repetition,
# and the residual grid is coarse.
#
# A 0.09 BAR WAS PROPOSED AND IS WITHDRAWN. Recorded because the withdrawal is
# the more useful result. The lane pre-registered the ESTIMATOR, not just the
# ceiling: a false-positive rate on HELD-OUT FOLDS, leave-one-chain-year-out,
# with any bar above a 0.25 alarm rate not proposable. Under that estimator 0.09
# scores 0.500 and is therefore not proposable. The 0.199 that would have
# licensed it came from a block bootstrap substituted after the pre-registered
# number came back unfavourable, and a block bootstrap over 8 chain-year blocks
# measures the dispersion of today's estimate, not the rate at which a future
# regeneration crosses the bar.
#
# The contrapositive settles it, and it was not reported by the lane: under the
# same pre-registered estimator the INCUMBENT 0.10 also fails (0.375), and only
# 0.11 and 0.12 clear 0.25. A procedure that would loosen the wire cannot be
# used to tighten it. The honest reading is that an 8-fold held-out FPR test is
# uninformative at this sample size and neither bar can be defended by it. 0.10
# stays because nothing has displaced it, not because it was re-validated.
#
# STILL OPEN, and unaffected by any of the above: no bar on a POOLED statistic
# can be sensitive to a top-of-board defect at an acceptable alarm rate. Tiers
# 50 and above are 306 of 2,822 rows, 10.84 percent, so they cannot move a
# pooled figure far. (The 295 / 10.5 percent quoted in an earlier draft of this
# block counted tiers 50-60 only, the MIN_TIER_N survivors, which is not the
# frame the pooled bust ECE uses; the lane's own injection code reports
# n_eligible on the 306 basis.) The wire wants a second, tier-located statistic.
BUST_ECE_TRIPWIRE = 0.10


def _tier(fv: float) -> int:
    """Consensus-FV tier = FV rounded to the nearest 5 (matches the isotonic lab)."""
    return int(round(float(fv) / 5) * 5)


def _realized_bucket(target_war_6yr: float) -> int:
    """The shipped 5-bucket realized-outcome map (matches the isotonic lab):
    bin the 6yr-AVERAGE annual WAR by the config band edges.

    THE DIVISOR IS A CONSTANT 6 ON A RIGHT-CENSORED LABEL, AND THAT WAS MEASURED
    (plan 2026-08-07b D4/C1, docs/efv-2026-08-07b/DISTRIBUTION_CALIBRATION_GATE.md,
    data/xfv_dist_calibration_eval.json). The pool below is
    `_prep(pool, "target_censored", side)`, whose censored rows carry a flat-rate tail
    projection that Lane B1 showed is biased pessimistic. A pessimistic label inflates
    realized bust and deflates realized good/star, which is the sign of the
    miscalibration this module reports, so the obvious worry was that the diagnostic
    was grading the model against its own label error. IT IS NOT. Re-running this chain
    with the realized bucket recomputed on a season-share-corrected label, on an
    IDENTICAL pool with predictions held fixed, moves pooled bust ECE 0.07908 -> 0.07660
    (3.1 percent) and the n-weighted per-tier gap 0.04068 -> 0.03883 (4.5 percent).
    Three reasons, all measured: the worst-biased span (observed_seasons = 2) has no row
    in CHAIN_YEARS at all (the 623 censored eval rows are n_obs 3/4/5); only 35 of 2,822
    rows change bucket; and tiers 35 and 40, which are 78 percent of the pool, are 83 and
    67 percent never-debuted `kind == "bust"` rows whose label is exactly 0.0 and
    uncensored. Reaching a 50 percent reduction would need a label error 10x to 25x the
    one B1 measured. DO NOT REOPEN THIS. The remaining miscalibration is real and belongs
    to the distribution (plan lane C2), not to the label."""
    import bisect
    return bisect.bisect_right(BUCKET_EDGES, float(target_war_6yr) / TARGET_SEASONS)


def _oof_rows(side: str) -> list[dict]:
    """Forward-chained out-of-fold rows for one side: the shipped pipeline's
    predicted 5-bucket distribution (uncalibrated) + realized bucket + fv/weight.
    Mirrors tools/efv_isotonic_lab.oof_rows but with no chdir side effect."""
    import numpy as np
    import value_framework as vf
    # TARGET_SEASONS = the model's exposure window (efv_dataset, =6). Imported from
    # efv_dataset (not the module-level 6.0 above, which is the realized-bucket
    # divisor pinned to the isotonic lab) so the grade-map inversion below tracks
    # whatever window efv_score ships. Shadows the module global inside this
    # function only; _realized_bucket keeps its own module-level divisor.
    from efv_dataset import matrix_path, TARGET_SEASONS
    from efv_model import _prep, _feature_spec
    from efv_score import _age_at, _grade_map_age
    from prospect_path import _fit_linear_calibration
    # Same rule as efv_score: this module reproduces the scorer's path up to the
    # grade inversion, so it must fit through efv_model's wrappers or the monitor
    # would grade a distribution the site does not serve under ARM A2.
    from efv_model import _fit_ridge, _predict

    is_pit = side == "pit"
    keys, _mono = _feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r["kind"] == "bust" and r.get("bust_recent"))]
    data = _prep(pool, "target_censored", side)
    by_key = {r["player_key"]: r for r in pool}

    out: list[dict] = []
    for yr in CHAIN_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < MIN_TEST or len(tr) < MIN_TRAIN:
            continue
        ridge = _fit_ridge(tr, keys)
        if not ridge:
            continue
        cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        for r in te:
            src = by_key[r["player_key"]]
            xfv_war = max(-2.0, a + b * _predict(ridge, r["feats"]))
            dyear = src.get("debut_year") or 2020
            age = _age_at(src.get("birth_date"), dyear)
            # exposure_seasons=TARGET_SEASONS so these reliability/ECE curves measure
            # the SHIPPED 6yr-window grade (efv_score.run/run_live/run_backgrade all
            # pass it); omitting it defaulted to control_years=7 and the diagnostic
            # described a bucket distribution the site never shows (2026-07-19 fix).
            # Age placement via _grade_map_age (bughunt F5, 2026-07-23): mirror the
            # scorer - `age` is measured at the debut year, so eta_to_debut = 0.0;
            # the raw pre-debut age placed the inversion's curve at debut_age =
            # age - 6, a curve the site never prices.
            pos = src.get("position")
            _gm_age = _grade_map_age(age, 0.0)
            grade = vf.realized_implied_fv(xfv_war, is_pit, age=_gm_age, position=pos,
                                           exposure_seasons=TARGET_SEASONS)
            if grade is None:
                continue
            probs = vf.p_bucket_given_fv(grade, is_pit)
            if not probs or len(probs) != len(BUCKETS):
                continue
            # THE SERVED DISTRIBUTION IS THE RECALIBRATED ONE (fix 2026-08-03).
            # This diagnostic mirrored efv_score.run() up to the grade inversion
            # and then stopped one line short: the scorer applies the odds
            # dispersion Platt map at all three seams (efv_score 1292/1812/2191,
            # wired 07-31) and this module never did. So the public "model
            # grading itself" card was reporting the PRE-fix curve and its
            # tripwire was tuned to a miscalibration that had already been
            # corrected. Both curve sets are emitted now: `after` is what the
            # site serves and what the tripwire judges, `before` is retained as
            # the drift reference the tripwire was originally written against.
            # `provisional` mirrors the resolved seam exactly - rows with no
            # milb block belong to the thin-sample lane, which owns its own
            # p_bust replacement, and stacking the two would undo that fix.
            probs_after = _odds_cal.recalibrate_bucket(
                probs, is_pit, provisional=not src.get("milb"))
            out.append({
                "player_key": r["player_key"], "side": side,
                "decision_year": yr, "fv": r["fv"],
                "p_before": np.asarray(probs, dtype=float),
                "p_after": np.asarray(probs_after, dtype=float),
                "y": _realized_bucket(r["target"]),
                "weight": float(r["weight"]),
            })
    return out


def _reliability_bins(rows, n_bins: int = 10, key: str = "p_after") -> dict:
    """Pooled per-bucket reliability curve (equal-width prob bins) + ECE.
    Identical binning to the isotonic lab. `key` selects the distribution:
    `p_after` is what the site serves, `p_before` the pre-Platt reference."""
    import numpy as np
    out = {}
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    for bi, name in enumerate(BUCKETS):
        p = np.array([r[key][bi] for r in rows])
        y = np.array([1.0 if r["y"] == bi else 0.0 for r in rows])
        curve, ece = [], 0.0
        for i in range(n_bins):
            m = (p >= edges[i]) & (p < edges[i + 1] if i < n_bins - 1 else p <= 1.0)
            if m.sum() < 5:
                continue
            mp, fr = float(p[m].mean()), float(y[m].mean())
            curve.append({"bin": [round(float(edges[i]), 2), round(float(edges[i + 1]), 2)],
                          "n": int(m.sum()), "mean_p": round(mp, 4), "freq": round(fr, 4)})
            ece += (m.sum() / len(p)) * abs(mp - fr)
        out[name] = {"ece": round(float(ece), 5), "curve": curve}
    return out


def _tier_reliability(rows, key: str = "p_after") -> dict:
    """Per consensus-FV tier: mean |mean predicted p_b - realized freq_b| gap,
    over the served distribution by default (see _reliability_bins)."""
    import numpy as np

    def _onehot(k: int):
        v = np.zeros(len(BUCKETS)); v[k] = 1.0; return v

    by_tier = defaultdict(list)
    for r in rows:
        by_tier[_tier(r["fv"])].append(r)
    out = {}
    for tk in sorted(by_tier):
        grp = by_tier[tk]
        if len(grp) < MIN_TIER_N:
            continue
        freq = np.mean([_onehot(r["y"]) for r in grp], axis=0)
        mb = np.mean([r[key] for r in grp], axis=0)
        gap = float(np.mean(np.abs(mb - freq)))
        out[str(tk)] = {
            "n": len(grp), "gap": round(gap, 5),
            "realized_freq": {BUCKETS[i]: round(float(freq[i]), 4) for i in range(len(BUCKETS))},
            "mean_p": {BUCKETS[i]: round(float(mb[i]), 4) for i in range(len(BUCKETS))},
        }
    return out


def build(persist: bool = True) -> dict:
    """Regenerate the shipped-distribution reliability curves + tripwire. Returns
    the payload; writes data/xfv_reliability.json when persist. Best-effort: on
    any failure (matrix absent, degraded local build) it logs and returns {},
    leaving the existing artifact untouched — the box produces the canonical one."""
    from datetime import date
    try:
        rows = {s: _oof_rows(s) for s in ("hit", "pit")}
    except Exception:                                          # noqa: BLE001
        log.exception("efv_reliability: OOF build failed — skipping regen")
        return {}
    pooled = [r for side_rows in rows.values() for r in side_rows]
    if not pooled:
        log.warning("efv_reliability: no OOF rows — skipping regen")
        return {}
    curves_after = _reliability_bins(pooled, key="p_after")
    curves_before = _reliability_bins(pooled, key="p_before")
    tiers = _tier_reliability(pooled, key="p_after")
    bust_ece = curves_after.get("bust", {}).get("ece", 0.0)
    bust_ece_before = curves_before.get("bust", {}).get("ece", 0.0)
    tripwire = {
        "bust_ece": bust_ece,
        "bust_ece_before_recalibration": bust_ece_before,
        "threshold": BUST_ECE_TRIPWIRE,
        "basis": "after",
        "tripped": bool(bust_ece > BUST_ECE_TRIPWIRE),
        "note": ("bust-bucket ECE on the SERVED (recalibrated) distribution "
                 "exceeded the drift threshold; review calibration"
                 if bust_ece > BUST_ECE_TRIPWIRE else
                 "served bust-bucket calibration within the post-recalibration band"),
    }
    payload = {
        "generated_at": date.today().isoformat(),
        "note": ("Reliability curves for the eFV 5-bucket outcome distribution "
                 "(forward-chained out-of-fold). `after` is the SERVED "
                 "distribution: it carries the odds-dispersion Platt map that "
                 "efv_score applies at all three scoring seams. `before` is the "
                 "pre-map reference kept for drift comparison - it is NOT what "
                 "the site shows. Regenerated by efv_reliability.build (C1); "
                 "diagnostic only, no served number depends on these curves. "
                 "tripwire.tripped judges the served curve."),
        "reliability_curves_pooled": {"after": curves_after, "before": curves_before},
        "per_tier_reliability": tiers,
        "tripwire": tripwire,
        "pooled_n": len(pooled),
        "n_by_side": {s: len(v) for s, v in rows.items()},
    }
    if tripwire["tripped"]:
        log.warning("efv_reliability TRIPWIRE: bust ECE %.4f > %.4f",
                    bust_ece, BUST_ECE_TRIPWIRE)
    if persist:
        OUT_PATH.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        log.info("efv_reliability: wrote %s (pooled n=%d, bust ECE %.4f)",
                 OUT_PATH.name, len(pooled), bust_ece)
    return payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = build(persist="--no-persist" not in __import__("sys").argv)
    if rep:
        pooled = rep["reliability_curves_pooled"]
        print(f"reliability regen: pooled n={rep['pooled_n']}")
        for name in BUCKETS:
            print(f"  {name:<8} ECE  after={pooled['after'][name]['ece']:.5f}  "
                  f"before={pooled['before'][name]['ece']:.5f}")
        print(f"  tripwire ({rep['tripwire']['basis']} basis, thr "
              f"{rep['tripwire']['threshold']}): "
              f"{'TRIPPED' if rep['tripwire']['tripped'] else 'ok'}")

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Forward-chained A/B gate for the proj_ml DEFENSIVE PRIOR (HIT side).

Question: does separating a reliability-shrunk, position-anchored defensive read out
of the total-WAR lags improve the WAR-PATH projection out-of-sample? The total-WAR
lags already carry defense; the hypothesis is that a STABLE, regressed defensive read
beats the noisy single-season defensive component buried in those lags.

Protocol (mirrors proj_eval / the gates):
  * One training frame per feature variant (schema-tagged cache).
  * For each eval base B, train a q50 head per (side, horizon) on frame rows whose
    LABEL season <= B-1 (forward-chained), build inference vectors as-of B (history
    <= B-1), predict the median path, score |pred-actual| vs realized bWAR (absent
    season = 0, both sides), pooled and on the star slice (base-year WAR >= 4).
  * q50 only -- the central projection is what MAE measures and the cleanest probe of
    whether the feature adds signal; the quantile bands / star-mean blend are an
    orthogonal post-hoc step.
  * DEV bases 2017-2021 are the dev loop; HOLDOUT bases 2022-2024 are touched once for
    the ship decision. Hitters only (defense is ~irrelevant to the pitcher WAR target).

GATE (hit): a variant ships only if it REDUCES pooled MAE on the HOLDOUT bases without
regressing the dev bases or the star slice. Loser is committed as a documented
rejection. Writes data/proj_def_feature_eval.json.

VERDICT 2026-06-29 -- SHIPPED `pos_adj_prior` ALONE (proj_ml.DEF_FEATURE_KEYS), i.e.
the `pos_only` variant. HOLDOUT deltas vs baseline (pooled 0.5581 / star 1.7718):
  pos_only   HOLDOUT pooled -0.0027 / star -0.0285   <- SHIPPED (dev also improves)
  miss_only  HOLDOUT pooled  0.0000 / star  0.0000   (inert -- redundant with war_l*_missing)
  +pos_adj   HOLDOUT pooled -0.0027 / star -0.0285   (pos_only + def_missing == pos_only)
  +def_war   HOLDOUT pooled -0.0029 / star -0.0234   (collinear alt; ~tied)
  +both      HOLDOUT pooled -0.0015 / star -0.0055   (worse -- the two priors are collinear)
So def_missing is dropped (inert) and only ONE prior ships (not stacked). The gain
concentrates in established regulars (the star slice) -- the mechanism the hypothesis
predicted: a stable, position-anchored defensive read the noisy single-season WAR lags
don't isolate.

RE-MEASURED 2026-10-28 (task STALE_EVALS_REMEASURE): the same bases, variants and
gate rule re-run on the current corpus; per the protocol a horizon target is scored
once its season is complete, so the 2024 base now scores further out than it could
on 2026-06-29. The live numbers are in the artifact (evaluated_at, scored_through);
the figures above are the 2026-06-29 ship record and are not restated here.

Run: python tools/def_feature_backtest.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os
os.chdir(ROOT)

import fa_projection as fp          # noqa: E402
import proj_ml as PM                # noqa: E402
from lightgbm import LGBMRegressor  # noqa: E402

SIDE = "hit"
DEV_BASES = [2017, 2018, 2019, 2021]
HOLDOUT_BASES = [2022, 2023, 2024]
FRAME_MAX_LABEL = 2024              # frame labels through 2024 (covers holdout training)
FIRST_BASE = 2003

VARIANTS = {
    "baseline":  (),
    "pos_only":  ("pos_adj_prior",),                  # SHIPPED -- positional-adjustment prior alone
    "miss_only": ("def_missing",),                    # ablation: track-record flag alone (inert)
    "+pos_adj":  ("pos_adj_prior", "def_missing"),    # ablation: == pos_only (def_missing adds 0)
    "+def_war":  ("def_war_prior", "def_missing"),    # collinear alt; gains similarly
    "+both":     ("def_war_prior", "pos_adj_prior", "def_missing"),  # worse (collinear priors)
}


def _set_variant(keys):
    """Toggle the proj_ml def-feature set + refresh the schema tag so the frame cache
    key is unique per variant (the tag is otherwise frozen at import)."""
    PM.DEF_FEATURE_KEYS = tuple(keys)
    PM._SCHEMA_TAG = hashlib.sha256(
        json.dumps({s: PM.feature_names(s) for s in ("hit", "pit")},
                   sort_keys=True).encode()).hexdigest()[:8]


def _eval_rows(corpus, by_player, war_actual, base):
    """Inference (feats, mlbam) at `base` for the hit side -- mirrors proj_eval."""
    league = corpus["league"]
    curves, war_map = fp.fitted_models(corpus, base - 1)
    out = []
    for mlbam, seasons in by_player.items():
        hist = [seasons[t] for t in (base - 1, base - 2, base - 3) if t in seasons]
        if not hist:
            continue
        age_prev = next((h.get("age") for h in hist if h.get("age")), None)
        if age_prev is None:
            continue
        age = age_prev + (base - hist[0]["season"])
        feats = PM.build_features(hist, SIDE, base, age, curves, war_map, league)
        if feats is None:
            continue
        out.append((np.asarray(feats, dtype=float), mlbam))
    return out


def run():
    corpus = fp.build_corpus()
    last_complete = corpus["last"] - 1
    by_player: dict = {}
    war_actual = fp.war_actual_map(corpus)  # the ONE label (809902c6); never sum r['war'] across sides
    for r in corpus[SIDE]:
        if r.get("mlbam"):
            by_player.setdefault(r["mlbam"], {})[r["season"]] = r

    results = {}
    for vname, keys in VARIANTS.items():
        _set_variant(keys)
        frame = PM.build_training_frame(corpus, FIRST_BASE, FRAME_MAX_LABEL)[SIDE]
        X, yh, rowsh, lsh = frame["X"], frame["y"], frame["rows"], frame["label_season"]

        # per (cohort, horizon): list of (pred, actual, is_star)
        agg = {c: {h: [] for h in range(1, PM.HORIZONS + 1)}
               for c in ("dev", "holdout")}
        for cohort, bases in (("dev", DEV_BASES), ("holdout", HOLDOUT_BASES)):
            for B in bases:
                # forward-chained per-horizon q50 heads trained on labels <= B-1
                heads = {}
                for h in range(1, PM.HORIZONS + 1):
                    ls = lsh[h]
                    sel = ls <= (B - 1)
                    if sel.sum() < 500:
                        continue
                    ridx = rowsh[h][sel]
                    m = LGBMRegressor(alpha=0.5, **PM._params_for(h))
                    m.fit(X[ridx], yh[h][sel])
                    heads[h] = m
                if not heads:
                    continue
                ev = _eval_rows(corpus, by_player, war_actual, B)
                if not ev:
                    continue
                Xev = np.vstack([f for f, _ in ev])
                for h, m in heads.items():
                    target = B + h - 1
                    if target > last_complete:
                        continue
                    pred = m.predict(Xev)
                    for (f, mlbam), p in zip(ev, pred):
                        base_war = war_actual.get((mlbam, B - 1))
                        is_star = base_war is not None and base_war >= 4.0
                        act = war_actual.get((mlbam, target), 0.0)
                        agg[cohort][h].append((float(p), float(act), is_star))

        # summarize
        summary = {}
        for cohort in ("dev", "holdout"):
            per_h = {}
            all_pairs, star_pairs = [], []
            for h in range(1, PM.HORIZONS + 1):
                pairs = agg[cohort][h]
                if not pairs:
                    continue
                mae = sum(abs(p - a) for p, a, _ in pairs) / len(pairs)
                sp = [(p, a) for p, a, s in pairs if s]
                smae = (sum(abs(p - a) for p, a in sp) / len(sp)) if sp else None
                per_h[h] = {"n": len(pairs), "mae": round(mae, 4),
                            "n_star": len(sp),
                            "mae_star": round(smae, 4) if smae is not None else None}
                all_pairs += [(p, a) for p, a, _ in pairs]
                star_pairs += sp
            pooled = (sum(abs(p - a) for p, a in all_pairs) / len(all_pairs)
                      if all_pairs else None)
            pooled_star = (sum(abs(p - a) for p, a in star_pairs) / len(star_pairs)
                           if star_pairs else None)
            summary[cohort] = {
                "per_h": per_h,
                "pooled_mae": round(pooled, 4) if pooled is not None else None,
                "pooled_n": len(all_pairs),
                "pooled_star_mae": round(pooled_star, 4) if pooled_star is not None else None,
                "pooled_star_n": len(star_pairs),
            }
        results[vname] = summary
        print(f"[{vname:>9}] "
              f"dev pooled MAE {summary['dev']['pooled_mae']} (n={summary['dev']['pooled_n']}) "
              f"star {summary['dev']['pooled_star_mae']} | "
              f"HOLDOUT pooled MAE {summary['holdout']['pooled_mae']} "
              f"(n={summary['holdout']['pooled_n']}) star {summary['holdout']['pooled_star_mae']}")

    # deltas vs baseline
    base = results["baseline"]
    print("\n=== delta vs baseline (negative = better) ===")
    deltas = {}
    for v in VARIANTS:
        if v == "baseline":
            continue
        d = {
            "dev_pooled": round(results[v]["dev"]["pooled_mae"] - base["dev"]["pooled_mae"], 4),
            "dev_star": round((results[v]["dev"]["pooled_star_mae"] or 0)
                              - (base["dev"]["pooled_star_mae"] or 0), 4),
            "holdout_pooled": round(results[v]["holdout"]["pooled_mae"] - base["holdout"]["pooled_mae"], 4),
            "holdout_star": round((results[v]["holdout"]["pooled_star_mae"] or 0)
                                  - (base["holdout"]["pooled_star_mae"] or 0), 4),
        }
        deltas[v] = d
        print(f"  {v:>9}: dev {d['dev_pooled']:+.4f} (star {d['dev_star']:+.4f}) | "
              f"HOLDOUT {d['holdout_pooled']:+.4f} (star {d['holdout_star']:+.4f})")

    out = {"evaluated_at": datetime.now().isoformat(timespec="seconds"),
           "scored_through": last_complete,
           "side": SIDE, "dev_bases": DEV_BASES, "holdout_bases": HOLDOUT_BASES,
           "variants": results, "deltas_vs_baseline": deltas,
           "shrink_pa": PM._DEF_SHRINK_PA}
    (ROOT / "data" / "proj_def_feature_eval.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    print("\nwrote data/proj_def_feature_eval.json")
    _set_variant(())   # leave the module dormant
    return out


if __name__ == "__main__":
    run()

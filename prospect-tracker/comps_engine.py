# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Historical COMPS for live prospects -- a PRESENTATIONAL surface, not a grade.

WHAT THIS IS
    For each served prospect, the k historical prospects whose PRE-DECISION line looked
    most like his does now, together with what those players actually went on to do
    (realized first-6yr summed bWAR). It answers "who did this guy look like, and what
    happened to them", which is a legitimate analytical and editorial tool.

WHAT THIS IS NOT
    It is NOT a competing grade and it must never be presented as one. Measured under the
    program gate (docs/EFV_GATE_STANDARD.md) on 5 forward-chained folds, 744 scored hitter
    rows, the comp-implied outcome ranks WORSE than the shipped eFV blend:

        shipped eFV blend        pooled OOS Spearman  0.2798
        consensus-OLS baseline                        0.2696
        comps, model-space metric                     0.2580   (delta -0.0327,
                                                                 CI95 [-0.0805, +0.0221])
        comps, archetype metric                       0.2568
        random-comp control                           0.0440

    A 320-config combinatorial search over comp metrics was run with a pre-registered
    candidate list; its BEST config reached 0.2796, still not beating the blend, and the
    best incremental (partial) signal over the shipped model was +0.1153 against a
    permutation max-statistic null whose 95th percentile is 0.1310 -- i.e. LESS than what
    the same search finds on pure noise. Nested CV put the search procedure at 0.2215 vs
    the shipped model's 0.2582 on untouched outer folds. So when a comp list disagrees
    with eFV, that is INFORMATION FOR THE READER, not evidence the model is wrong.

WHY IT IS STILL WORTH SHIPPING
    It is well calibrated as a descriptive device on the hitter side: regression slope of
    realized on comp-implied is 0.993 and the bust rate falls monotonically across
    comp-implied quintiles (96.0% -> 89.3% -> 73.0% -> 63.8% -> 30.2%). Readers get a real
    outcome distribution attached to a familiar name, which no single number provides.

SCOPE LIMITS (all measured, all enforced below)
    - HITTERS ONLY. The pitcher engine is not calibrated enough to display: pooled rho
      0.0940, and realized WAR across comp-implied quintiles is non-monotone
      (0.77, 0.66, 0.49, 0.88, 3.05). Set include_pitchers=True only for research.
    - TRACK-RECORD SUBJECTS ONLY. A prospect with no MiLB block (a just-drafted amateur)
      is NOT comp-able here: 97% of the no-MiLB donor rows carry milb_unavailable=True,
      meaning their record was never ingested rather than never existed, so "no track
      record" cannot be told apart from "record missing". On that pool the comp-implied
      grade for one subject swings from FV 20.0 to FV 59.6 on the donor gate alone.
    - COMPLETED OUTCOMES ONLY as donors. A player still inside his 6-year window would
      understate his realized WAR, which is exactly the bias that makes an outcome-based
      comp list look more bearish than the truth.

Read-only. Emits data/comps.json.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import efv_model as EM
import value_framework as vf

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "comps.json"

K = 20
LEVEL_BAND = 1.0          # donors within +/-1 level_rank: the career-stage gate
MIN_DONORS = 5
N_SHOWN = 8

# The two displayed metrics. Both are members of the pre-registered 320-config family, so
# both have a measured out-of-fold rho (quoted above). NEITHER is the sweep winner --
# selecting the sweep winner would be choosing a config on the rows it is scored against,
# and the nested-CV arm shows that procedure is worth nothing out of sample.
#   MODEL_SPACE  - neighbours in the feature space eFV itself uses, weighted by the
#                  model's own ridge coefficients. Comps that EXPLAIN the grade.
#   ARCHETYPE    - stage x production x tools, equal weight, no consensus anchor. The
#                  reader-facing "what kind of player is this" view, deliberately blind
#                  to the scouting grade so it can disagree with it.
ARCHETYPE_AXES = ["age", "level_rank", "age_rel_level", "n_milb_seasons",
                  "ops_rel", "obp_rel", "iso_rel", "k_rel", "bb_rel", "prod_trend",
                  "tool_hit", "tool_game_pwr", "tool_raw_pwr", "tool_speed",
                  "tool_field", "tool_throw"]

COMP_FIELDS = ["player_key", "realized_war_6yr", "similarity",
               "decision_year", "level", "age", "consensus_fv", "reached_mlb"]

MEASURED = {
    "protocol": "5 forward-chained folds on decision_year (2020-2024), 744 scored hitter "
                "rows, donors/standardization/weights fit on train folds only",
    "shipped_efv_blend_rho": 0.2798,
    "consensus_ols_rho": 0.2696,
    "comps_model_space_rho": 0.2580,
    "comps_archetype_rho": 0.2568,
    "random_comp_control_rho": 0.0440,
    "paired_bootstrap_delta_vs_blend": {"model_space": -0.0327,
                                        "ci95": [-0.0805, 0.0221],
                                        "p_beats_blend": 0.120},
    "search": {"n_hypotheses_pre_registered": 320,
               "best_config_rho": 0.2796,
               "best_partial_rho_over_shipped": 0.1153,
               "permutation_max_partial_null_p95": 0.1310,
               "verdict": "best incremental signal is BELOW the noise bar"},
    "nested_cv": {"search_selected": 0.2215, "fixed_default": 0.1841,
                  "shipped_blend": 0.2582},
    "calibration_hit": {"slope_realized_on_predicted": 0.993,
                        "bust_rate_by_comp_quintile": [0.960, 0.893, 0.730, 0.638, 0.302]},
    "disclaimer": "Presentational. A comp list is a distribution of what happened to "
                  "similar-looking players, not a grade. It ranks worse than eFV out of "
                  "sample; disagreement with eFV is information for the reader, not "
                  "evidence the model is wrong.",
}


def _axis(r, key):
    m = r.get("milb") or {}
    if key in m:
        v = m.get(key)
        return float(v) if isinstance(v, (int, float)) else None
    v = r.get(key)
    return float(v) if isinstance(v, (int, float)) else None


def _matrix(rows, keys, imp=None, shipped=False, side="hit"):
    X = np.full((len(rows), len(keys)), np.nan)
    for i, r in enumerate(rows):
        fv = EM._vec(r, side) if shipped else None
        for j, k in enumerate(keys):
            v = fv.get(k) if shipped else _axis(r, k)
            if isinstance(v, (int, float)) and math.isfinite(float(v)):
                X[i, j] = float(v)
    if imp is None:
        imp = np.nanmean(X, axis=0)
        imp = np.where(np.isfinite(imp), imp, 0.0)
    idx = np.where(np.isnan(X))
    X[idx] = np.take(imp, idx[1])
    return X, imp


def _donors(side="hit"):
    """Historical prospects with a COMPLETED outcome and a real pre-decision MiLB line."""
    mp = "xfv_hitter_matrix.json" if side == "hit" else "xfv_pitcher_matrix.json"
    rows = json.loads((DATA_DIR / mp).read_text(encoding="utf-8"))
    is_pit = side == "pit"
    out = []
    for r in rows:
        if bool(r.get("is_pitcher")) != is_pit:
            continue
        if r.get("kind") == "bust" and r.get("bust_recent"):
            continue
        if r.get("censored") or not r.get("milb"):
            continue
        if r.get("target_resolved") is None or r.get("consensus_fv_raw") is None:
            continue
        r = dict(r)
        r["_y"] = float(r["target_resolved"])
        out.append(r)
    return out


def _implied_fv(war6):
    lo, hi = 20.0, 80.0
    for _ in range(80):
        mid = (lo + hi) / 2
        v = vf.fv_to_6yr_avg_war(mid)
        if v is None:
            return None
        if 6.0 * v < war6:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 1)


def _neighbours(Zd, yd, zs, w, lvl_d, lvl_s):
    sw = np.sqrt(np.maximum(w, 0.0))
    d = np.sqrt(np.maximum(((Zd * sw - zs * sw) ** 2).sum(1), 0.0))
    if lvl_d is not None:
        bad = np.abs(lvl_d - lvl_s) > LEVEL_BAND
        if (~bad).sum() >= MIN_DONORS:
            d = np.where(bad, np.inf, d)
    idx = np.argsort(d)[:K]
    return idx, d[idx]


def _block(donors, Zd, yd, lvl_d, zs, lvl_s, w):
    idx, dist = _neighbours(Zd, yd, zs, w, lvl_d, lvl_s)
    ys = yd[idx]
    mean = float(ys.mean())
    inv = 1.0 / (dist + 1e-6)
    # compact records (short keys): this artifact carries ~2k players x 2 metrics, so the
    # per-comp key names dominate the payload. Schema is documented in COMP_FIELDS.
    comps = []
    for i, dd in list(zip(idx, dist))[:N_SHOWN]:
        r = donors[int(i)]
        m = r.get("milb") or {}
        comps.append([r["player_key"], round(r["_y"], 2),
                      round(float(1.0 / (1.0 + dd)), 3),
                      EM._decision_year(r), m.get("milb_level"), m.get("age"),
                      r.get("consensus_fv_raw"), 1 if r["kind"] == "debuted" else 0])
    return {
        "k": int(K),
        "comp_implied_war_6yr": round(float((inv * ys).sum() / inv.sum()), 2),
        "comp_mean_war_6yr": round(mean, 2),
        "comp_median_war_6yr": round(float(np.median(ys)), 2),
        "comp_bust_rate": round(float((ys < 0.5).mean()), 3),
        "comp_p10_war_6yr": round(float(np.percentile(ys, 10)), 2),
        "comp_p90_war_6yr": round(float(np.percentile(ys, 90)), 2),
        "comp_implied_fv": _implied_fv(mean),
        "comps": comps,
    }


def build(side: str = "hit") -> dict:
    donors = _donors(side)
    if len(donors) < 60:
        return {}
    lp = "xfv_live_hitter_matrix.json" if side == "hit" else "xfv_live_pitcher_matrix.json"
    live = json.loads((DATA_DIR / lp).read_text(encoding="utf-8"))
    yd = np.array([r["_y"] for r in donors])
    lvl_d = np.array([(r.get("milb") or {}).get("level_rank", 0.0) or 0.0 for r in donors])

    skeys, _m = EM._feature_spec(side)
    specs = {}
    for label, keys, shipped in (("model_space", skeys, True),
                                 ("archetype", ARCHETYPE_AXES, False)):
        Xd, imp = _matrix(donors, keys, shipped=shipped, side=side)
        mu, sd = Xd.mean(0), Xd.std(0)
        sd = np.where(sd > 1e-9, sd, 1.0)
        Zd = (Xd - mu) / sd
        if label == "model_space":
            # the model's own ridge coefficients as axis relevance
            d = EM._prep(donors, "target_resolved", side)
            ridge = EM._fit_ridge(d, keys)
            w = np.abs(np.array([dict(zip(ridge["keys"], ridge["w"]))[k] for k in keys])) \
                if ridge else np.ones(len(keys))
            s = w.sum()
            w = w * (len(keys) / s) if s > 1e-12 else np.ones(len(keys))
        else:
            w = np.ones(len(keys))
        specs[label] = {"keys": keys, "shipped": shipped, "imp": imp,
                        "mu": mu, "sd": sd, "Zd": Zd, "w": w}

    out, skipped = {}, {"no_track_record": 0, "no_consensus": 0}
    for r in live:
        try:
            float(r.get("consensus_fv_raw"))
        except (TypeError, ValueError):
            skipped["no_consensus"] += 1
            continue
        if not r.get("milb"):
            skipped["no_track_record"] += 1
            continue
        m = r["milb"]
        ent = {"as_of": {"milb_season": m.get("milb_season"),
                         "level": m.get("milb_level"), "age": m.get("age"),
                         "age_rel_level": m.get("age_rel_level"),
                         "n_milb_seasons": m.get("n_milb_seasons")}}
        lvl_s = float(m.get("level_rank") or 0.0)
        for label, sp in specs.items():
            Xs, _ = _matrix([r], sp["keys"], imp=sp["imp"], shipped=sp["shipped"], side=side)
            zs = (Xs[0] - sp["mu"]) / sp["sd"]
            ent[label] = _block(donors, sp["Zd"], yd, lvl_d, zs, lvl_s, sp["w"])
        out[r["player_key"]] = ent
    return {"donor_pool": len(donors), "skipped": skipped, "by_player": out}


def run(persist: bool = True, include_pitchers: bool = False) -> dict:
    doc = {"generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
           "model": "comps_engine",
           "comp_fields": COMP_FIELDS,
           "scope": "hitters only" if not include_pitchers else "hitters + pitchers (RESEARCH)",
           "measured": MEASURED,
           "hit": build("hit")}
    if include_pitchers:
        doc["pit"] = build("pit")
        doc["pitcher_warning"] = ("Pitcher comps are NOT display-grade: pooled OOS rho "
                                  "0.0940 and realized WAR is non-monotone across "
                                  "comp-implied quintiles. Research use only.")
    if persist:
        OUT_PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return doc


if __name__ == "__main__":
    d = run()
    h = d["hit"]
    print(f"comps.json: donor pool {h['donor_pool']}, "
          f"{len(h['by_player'])} hitters comped, skipped {h['skipped']}")

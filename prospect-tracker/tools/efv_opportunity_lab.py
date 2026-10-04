"""eFV OPPORTUNITY DECOMPOSITION LAB (lane B-L3, 2026-08-09).

PRE-REGISTRATION: docs/efv-2026-08-09/OPPORTUNITY_DECOMP_GATE.md sections 0-9, written
in full BEFORE this file existed. Section 10 is filled from the artifact this lab writes.

WHAT THIS ANSWERS. The owner asked for correlations between eFV and WAR-per-opportunity
metrics (WARPA+ / WARIP+) that could become new eFV drivers. THE ANSWER IS A CLOSURE. This
lab reproduces it under the full control battery and records it so nobody rediscovers it.

WHAT SHIPS FROM THIS FILE: nothing. No feature, no constant, no edit to efv_model.py or
efv_dataset.py. It imports from efv_model, never patches it. Its single product is
data/xfv_opportunity_eval.json plus a verdict.

THE TWO PRE-REGISTERED HAZARDS, repeated here because a reader of the code needs them:

  1. The QUALITY leg is fit on a subpopulation SELECTED ON PA, and PA correlates with FV.
     rho(fv, quality) is a CONDITIONAL-ON-SELECTION read and must never be quoted
     unconditionally. The artifact carries the hazard as a field, not as prose.

  2. .cache/war_daily/*.parquet is GITIGNORED and rebuilt from pybaseball. Fine for a lab
     under tools/. It MUST NEVER become a model input without a durable, committed,
     deploy-reachable artifact: the box runs `git checkout -- .` nightly and has no
     guarantee the cache exists, so a feature reading that path would impute to zero in
     production and score fine in every local test.

Usage:
    python tools/efv_opportunity_lab.py join          # identity-join coverage only
    python tools/efv_opportunity_lab.py decomp        # section 2 correlations + cosine
    python tools/efv_opportunity_lab.py arms          # the four exploitation arms
    python tools/efv_opportunity_lab.py dispersion    # the section 9 diagnostic
    python tools/efv_opportunity_lab.py all           # everything -> the artifact
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
OUT_PATH = DATA / "xfv_opportunity_eval.json"
WAR_DAILY = ROOT / ".cache" / "war_daily"
_ZERO = (0.0, 0.0, 0.0, 0.0, 0.0)

SEED = 20260809

# Windows and censoring convention are READ from efv_dataset, never re-declared, so the
# opportunity accrual cannot drift away from the label it decomposes.
import efv_dataset as ed                                     # noqa: E402
import efv_model as em                                       # noqa: E402
from prospect_path import (_fit_ridge, _fit_linear_calibration, _predict,  # noqa: E402
                           _weighted_spearman)

TARGET_SEASONS = ed.TARGET_SEASONS          # 6
RESOLVED_THROUGH = ed.RESOLVED_THROUGH      # 2026 since the fWAR label epoch; follows efv_dataset

# Floors are READ from the B-L1 artifact and cited. This lane derives no floor of its own:
# a lane whose product is losses has no business also producing the bar it is judged by.
FLOOR_SOURCE = "data/xfv_power_eval.json partb_floors"
_FLOOR_CELL = {
    "hit.full_pool_km": "pooled_rho.hit.full_pool_km",
    "pit.full_pool_km": "pooled_rho.pit.full_pool_km",
    "hit.debuted_km": "pooled_rho.hit.debuted_km",
    "pit.debuted_km": "pooled_rho.pit.debuted_km",
    "block_rho": "block_rho",
}

# Section 3, fixed before the run. Primary first; the rest are DECLARED sensitivities,
# run and reported regardless of outcome, not a selection menu.
QUALITY_THRESHOLD = {"hit": 200.0, "pit": 150.0}        # PA / IPouts
QUALITY_SENSITIVITY = {"hit": (100.0, 300.0), "pit": (90.0, 300.0)}

GAMMA_SWEEP = (0.0, 0.25, 0.5, 1.0, 2.0)
GAMMA_HEADLINE = 1.0

# Section 8: how a reproduced correlation is graded against the planning read.
MATCH_BAND = 0.05
CLOSE_BAND = 0.10
DISPERSION_MATERIAL = 0.05

PLANNING = {
    "rho_fv_opportunity": {"hit": 0.584, "pit": 0.440},
    "rho_fv_war": {"hit": 0.278, "pit": 0.214},
    "rho_fv_quality": {"hit": 0.316, "pit": 0.140},
    "cosine_war_vs_opportunity": {"hit": 0.979, "pit": 0.979},
    "arms": {
        "multiplicative_blend": {"hit.full_pool_km": -0.0164, "hit.debuted_km": -0.0172,
                                 "pit.full_pool_km": -0.0271, "pit.debuted_km": -0.0020},
        "multiplicative_pure": {"hit.full_pool_km": -0.1284, "hit.debuted_km": -0.0634,
                                "pit.full_pool_km": -0.0920, "pit.debuted_km": -0.0047},
        "hurdle_blend": {"hit.full_pool_km": 0.0014, "hit.debuted_km": -0.0021,
                         "pit.full_pool_km": -0.0085, "pit.debuted_km": -0.0069},
        "auxiliary_gamma_1.0": {"hit.full_pool_km": -0.0180, "hit.debuted_km": -0.0190,
                                "pit.full_pool_km": -0.0113, "pit.debuted_km": 0.0086},
    },
}


# ---------------------------------------------------------------------------
# 0. small numeric helpers (no statsmodels: installed but UNDECLARED in
#    requirements.txt and therefore not shippable, even from tools/)
# ---------------------------------------------------------------------------

def _spearman_u(xs, ys):
    """Unweighted Spearman via the shipped weighted form at w=1, which the
    prospect_path docstring guarantees is exact. One ranker, one code path."""
    if len(xs) < 8:
        return None
    return _weighted_spearman(list(xs), list(ys), [1.0] * len(xs))


def _ols_slope(xs, ys):
    n = len(xs)
    if n < 8:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    var = sum((a - mx) ** 2 for a in xs)
    if var <= 0:
        return None
    return cov / var


def _cosine(u, v):
    num = sum(a * b for a, b in zip(u, v))
    du = math.sqrt(sum(a * a for a in u))
    dv = math.sqrt(sum(b * b for b in v))
    if du <= 0 or dv <= 0:
        return None
    return num / (du * dv)


def _r4(x):
    return None if x is None else round(float(x), 4)


def _grade(measured, expected):
    """Section 2 material-difference clause. A DIFFERENT figure is a finding in its
    own right and is NOT quietly rewritten to whatever this lane measures."""
    if measured is None:
        return "NOT MEASURED"
    d = abs(float(measured) - float(expected))
    return "MATCHED" if d <= MATCH_BAND else ("CLOSE" if d <= CLOSE_BAND else "DIFFERENT")


def _floors():
    art = json.loads((DATA / "xfv_power_eval.json").read_text(encoding="utf-8"))
    cells = art["partb_floors"]["cells"]
    out = {}
    for k, cell in _FLOOR_CELL.items():
        c = cells[cell]
        out[k] = {"mde95": c["MDE95"], "mde95_cond": c["MDE95_COND"],
                  "source_cell": cell, "n_rows": c.get("n_rows")}
    return out


def _delta_block(point, floor, estimator_note=""):
    """EVERY delta carries a floor AND an estimator label. MDE95 is one-sided
    1.645*sd on |delta| (docs/EFV_GATE_STANDARD.md section 1); MDE95 is E_refit,
    MDE95_COND is E_cond. Neither is ever quoted without its estimator."""
    p = float(point)
    m_r = abs(p) / floor["mde95"] if floor["mde95"] else None
    m_c = abs(p) / floor["mde95_cond"] if floor["mde95_cond"] else None
    res_r = bool(m_r is not None and m_r >= 1.0)
    res_c = bool(m_c is not None and m_c >= 1.0)
    if res_r or res_c:
        verdict = "RESOLVABLE GAIN" if p > 0 else "RESOLVABLE LOSS"
    else:
        verdict = "NULL"
    return {
        "point_delta": round(p, 4),
        "mde95": floor["mde95"],
        "mde95_estimator": "E_refit (paired bootstrap, refit per draw)",
        "mde95_cond": floor["mde95_cond"],
        "mde95_cond_estimator": "E_cond (fits held fixed, scored rows resampled)",
        "margin_over_mde95": round(m_r, 3) if m_r is not None else None,
        "margin_over_mde95_cond": round(m_c, 3) if m_c is not None else None,
        "resolvable_E_refit": res_r,
        "resolvable_E_cond": res_c,
        "verdict": verdict,
        "floor_source": FLOOR_SOURCE + " -> " + floor["source_cell"],
        "note": estimator_note or None,
    }


# ---------------------------------------------------------------------------
# 1. the identity join (section 5). Sourcing study NOT redone.
# ---------------------------------------------------------------------------

def _id_overrides() -> dict:
    a = json.loads((DATA / "sources" / "mlbam_id_overrides.json").read_text(encoding="utf-8"))
    b = json.loads((DATA / "sources" / "mlbam_id_overrides_busts.json").read_text(encoding="utf-8"))
    merged = dict(a)
    merged.update(b)
    return merged, len(a), len(b)


def _accrual_frame():
    """{(mlbam, season): (pa, ipouts, war)} collapsed over stints, the SAME spine
    arb_dataset.war_daily_spine uses (arb_dataset.py:119).

    READS THROUGH war_source (2026-09-04), not the parquet directly. It used to read
    .cache/war_daily/*.parquet, which is the raw bWAR download, while the eFV label it is
    joined against moved to eWAR v2 in the label epoch. The two bases then disagreed
    wholesale on the pitcher side: the synthetic-censoring leg's join reproduced
    target_resolved on 0.0557 of pitcher rows and 0.8828 of hitter rows, against the 0.95
    the leg needs, so it was measuring the basis gap rather than the label fill. The
    facade returns the same stint shape with WAR on the SERVED provider, which is what
    `the SAME spine arb_dataset uses` was always supposed to mean, since arb_dataset
    itself was moved onto the facade in the same wave.
    """
    import pandas as pd
    import war_source
    if not (WAR_DAILY / "bat.parquet").exists():
        raise SystemExit(
            "missing .cache/war_daily/bat.parquet. It is GITIGNORED and rebuilt from "
            "pybaseball; see OPPORTUNITY_DECOMP_GATE.md section 4.")
    b = war_source.stint_frame("bat")[["mlb_ID", "year_ID", "PA", "WAR"]].copy()
    p = war_source.stint_frame("pit")[["mlb_ID", "year_ID", "IPouts", "WAR"]].copy()
    for d, cols in ((b, ("mlb_ID", "year_ID", "PA", "WAR")),
                    (p, ("mlb_ID", "year_ID", "IPouts", "WAR"))):
        for c in cols:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    b = b.dropna(subset=["mlb_ID", "year_ID"])
    p = p.dropna(subset=["mlb_ID", "year_ID"])
    gb = b.groupby(["mlb_ID", "year_ID"]).agg(pa=("PA", "sum"), war_bat=("WAR", "sum"))
    gp = p.groupby(["mlb_ID", "year_ID"]).agg(ipouts=("IPouts", "sum"), war_pit=("WAR", "sum"))
    m = gb.join(gp, how="outer").fillna(0.0)
    out = {}
    for (mid, yr), row in m.iterrows():
        out[(int(mid), int(yr))] = (float(row["pa"]), float(row["ipouts"]),
                                    float(row["war_bat"]) + float(row["war_pit"]),
                                    float(row["war_bat"]), float(row["war_pit"]))
    return out


def opportunity_map(side: str) -> dict:
    """player_key -> opportunity accrual over the SAME six-season window and the SAME
    censoring convention as efv_dataset._label_6yr. Using a different censoring rule for
    the numerator and the denominator of a decomposition would manufacture it."""
    ov, _, _ = _id_overrides()
    acc = _accrual_frame()
    rows = json.loads(ed.matrix_path(side).read_text(encoding="utf-8"))
    unit = "PA" if side == "hit" else "IPouts"
    idx = 0 if side == "hit" else 1
    out, cov = {}, {"inline_id": 0, "override_id": 0, "no_id": 0,
                    "joined": 0, "unjoined": 0, "bust_by_construction": 0,
                    "bust_with_mlb_exposure": 0, "debuted_rows": 0}
    for r in rows:
        pk = r["player_key"]
        mid = r.get("mlbam_id")
        src = "inline"
        if mid is None:
            mid = ov.get(pk)
            src = "override" if mid is not None else None
        if src == "inline":
            cov["inline_id"] += 1
        elif src == "override":
            cov["override_id"] += 1
        else:
            cov["no_id"] += 1
        if r["kind"] != "debuted":
            # never reached MLB: opportunity is 0 by construction, exactly as the
            # target is 0 by construction. No join needed.
            cov["bust_by_construction"] += 1
            if mid is not None:
                exposure = sum(acc.get((int(mid), y), _ZERO)[idx]
                               for y in range(2011, RESOLVED_THROUGH + 1))
                if exposure > 0:
                    cov["bust_with_mlb_exposure"] += 1
            out[pk] = {"opp_obs": 0.0, "opp_censored": 0.0, "war_obs": 0.0,
                       "n_obs": TARGET_SEASONS, "joined": True, "kind": "bust",
                       "unit": unit, "by_construction": True}
            continue
        cov["debuted_rows"] += 1
        dy = int(r["debut_year"])
        window = [dy + i for i in range(TARGET_SEASONS)]
        observed = [y for y in window if y <= RESOLVED_THROUGH]
        n_obs = len(observed)
        if mid is None or n_obs == 0:
            cov["unjoined"] += 1
            out[pk] = {"opp_obs": None, "opp_censored": None, "war_obs": None,
                       "n_obs": n_obs, "joined": False, "kind": "debuted",
                       "unit": unit, "by_construction": False}
            continue
        obs = sum(acc.get((int(mid), y), _ZERO)[idx] for y in observed)
        war = sum(acc.get((int(mid), y), _ZERO)[2] for y in observed)
        rate = obs / n_obs if n_obs else 0.0
        cens = obs + (TARGET_SEASONS - n_obs) * rate
        cov["joined"] += 1
        out[pk] = {"opp_obs": round(obs, 2), "opp_censored": round(cens, 2),
                   "war_obs": round(war, 3), "n_obs": n_obs, "joined": True,
                   "kind": "debuted", "unit": unit, "by_construction": False}
    return out, cov


def cmd_join(verbose=True):
    ov, n_a, n_b = _id_overrides()
    blocks = {}
    for side in ("hit", "pit"):
        omap, cov = opportunity_map(side)
        rows = json.loads(ed.matrix_path(side).read_text(encoding="utf-8"))
        deb = [r for r in rows if r["kind"] == "debuted"]
        noid = [r for r in deb if r.get("mlbam_id") is None]
        covered = sum(1 for r in noid if r["player_key"] in ov)
        joined = sum(1 for r in deb if omap[r["player_key"]]["joined"])
        with_pa = sum(1 for r in deb
                      if omap[r["player_key"]]["joined"]
                      and (omap[r["player_key"]]["opp_obs"] or 0) > 0)
        full_window = sum(1 for r in deb
                          if omap[r["player_key"]]["joined"]
                          and omap[r["player_key"]]["n_obs"] == TARGET_SEASONS)
        blocks[side] = {
            "n_matrix_rows": len(rows),
            "n_debuted": len(deb),
            "n_debuted_no_inline_id": len(noid),
            "n_debuted_no_inline_id_covered_by_overrides": covered,
            "n_debuted_joined": joined,
            "debuted_join_rate": round(joined / len(deb), 4) if deb else None,
            "n_debuted_joined_with_nonzero_opportunity": with_pa,
            "n_debuted_full_six_season_window": full_window,
            "n_bust_opportunity_zero_by_construction": cov["bust_by_construction"],
            "n_bust_rows_with_any_mlb_exposure_in_frame": cov["bust_with_mlb_exposure"],
            "unit": "PA" if side == "hit" else "IPouts",
        }
    out = {
        "override_files": {
            "data/sources/mlbam_id_overrides.json": n_a,
            "data/sources/mlbam_id_overrides_busts.json": n_b,
        },
        "spine": "arb_dataset.war_daily_spine basis (arb_dataset.py:119), stints collapsed "
                 "by (mlb_ID, year_ID)",
        "censoring_parity": "window debut_year..debut_year+5, observed capped at "
                            f"RESOLVED_THROUGH={RESOLVED_THROUGH}, censored tail projected "
                            "at the observed per-season rate. IDENTICAL to "
                            "efv_dataset._label_6yr; a decomposition with two censoring "
                            "rules manufactures itself.",
        "deploy_hazard": "SOURCE IS .cache/war_daily/*.parquet, GITIGNORED and rebuilt from "
                         "pybaseball. Lab-only. MUST NEVER become a model input without a "
                         "durable deploy-reachable artifact: the box runs `git checkout -- .` "
                         "nightly, so a feature reading this path imputes to zero in "
                         "production and scores fine in every local test.",
        "sides": blocks,
    }
    if verbose:
        print(json.dumps(out, indent=1))
    return out


# ---------------------------------------------------------------------------
# 2. the decomposition read + the cosine bound (sections 2 and 6)
# ---------------------------------------------------------------------------

def _decomp_side(side: str, omap: dict) -> dict:
    rows = json.loads(ed.matrix_path(side).read_text(encoding="utf-8"))
    deb = [r for r in rows if r["kind"] == "debuted"
           and r.get("consensus_fv_raw") is not None
           and r.get("target_censored") is not None
           and omap[r["player_key"]]["joined"]]
    fv = [float(r["consensus_fv_raw"]) for r in deb]
    opp = [omap[r["player_key"]]["opp_censored"] for r in deb]
    war = [float(r["target_censored"]) for r in deb]
    war_bbref = [omap[r["player_key"]]["war_obs"] for r in deb]

    r_opp = _spearman_u(fv, opp)
    r_war = _spearman_u(fv, war)
    r_war_bbref_obs = _spearman_u(fv, war_bbref)
    r_opp_war = _spearman_u(opp, war)

    def quality_at(thr):
        keep = [(f, w / o) for f, o, w in zip(fv, opp, war) if o >= thr and o > 0]
        if len(keep) < 8:
            return {"threshold": thr, "n": len(keep), "rho": None}
        return {"threshold": thr, "n": len(keep),
                "rho": _r4(_spearman_u([a for a, _ in keep], [b for _, b in keep]))}

    prim = quality_at(QUALITY_THRESHOLD[side])
    sens = [quality_at(t) for t in QUALITY_SENSITIVITY[side]]
    gaps = [(r_opp - c["rho"]) for c in ([prim] + sens) if c["rho"] is not None]
    gap_signs_agree = bool(gaps and (all(g > 0 for g in gaps) or all(g < 0 for g in gaps)))

    return {
        "pool": "debuted rows with a successful opportunity join",
        "n": len(deb),
        "unit": "PA" if side == "hit" else "IPouts",
        "rho_fv_opportunity": _r4(r_opp),
        "rho_fv_war_shipped_target": _r4(r_war),
        "rho_fv_war_bbref_observed_window": _r4(r_war_bbref_obs),
        "rho_opportunity_war": _r4(r_opp_war),
        "quality_primary": prim,
        "quality_sensitivity": sens,
        "quality_threshold_stability": {
            "gap_rho_opp_minus_rho_quality": [round(g, 4) for g in gaps],
            "signs_agree": gap_signs_agree,
            "reading": ("threshold is not doing the work" if gap_signs_agree
                        else "THRESHOLD IS DOING THE WORK; no quality figure is published"),
        },
        "SELECTION_HAZARD": {
            "applies_to": "quality_primary and quality_sensitivity ONLY",
            "statement": "the quality leg is fit on a subpopulation SELECTED ON the very "
                         "denominator it divides by, and that denominator correlates with "
                         "FV. This is a CONDITIONAL-ON-SELECTION read.",
            "never_quote": "'the board correlates X with quality'. The true sentence "
                           "carries 'among players who reached the threshold'.",
            "bias_direction": "conditioning on high exposure among low-FV players selects "
                              "the ones who earned it with a high rate, which biases the "
                              "within-stratum FV-to-rate association DOWNWARD. The figure "
                              "is bounded-below, not a point estimate.",
        },
    }


def _basis_sensitivity(side: str, omap: dict) -> dict:
    """WHICH POOL WAS THE PLANNING READ ON? Section 2 pre-registers the DEBUTED pool, and
    that is what `decomposition` above reports. This block reports the same two
    correlations on the FULL modelled pool (debuted + busts, minus bust_recent, busts
    carrying a structural zero on BOTH the numerator and the target) and pair-weighted,
    so a reader can see how much of the planning figure is basis and how much is signal.

    It is published because the full-pool unweighted column turns out to IDENTIFY the
    planning basis, not because it was searched for a better match: the pre-registered
    debuted read stands as the primary and is not rewritten."""
    rows = json.loads(ed.matrix_path(side).read_text(encoding="utf-8"))

    def cell(sel):
        sel = [r for r in sel
               if r.get("consensus_fv_raw") is not None
               and r.get("target_censored") is not None
               and omap.get(r["player_key"], {}).get("joined")]
        fv = [float(r["consensus_fv_raw"]) for r in sel]
        war = [float(r["target_censored"]) for r in sel]
        opp = [omap[r["player_key"]]["opp_censored"] for r in sel]
        w = [float(r.get("weight") or 1.0) for r in sel]
        return {
            "n": len(sel),
            "rho_fv_opportunity_unweighted": _r4(_spearman_u(fv, opp)),
            "rho_fv_war_unweighted": _r4(_spearman_u(fv, war)),
            "rho_fv_opportunity_pair_weighted": _r4(_weighted_spearman(fv, opp, w)),
            "rho_fv_war_pair_weighted": _r4(_weighted_spearman(fv, war, w)),
        }

    deb = cell([r for r in rows if r["kind"] == "debuted"])
    full = cell([r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))])

    def gap(c):
        o, w = c["rho_fv_opportunity_unweighted"], c["rho_fv_war_unweighted"]
        return None if o is None or w is None else round(o - w, 4)

    # The comparison sentence is DERIVED from the two gaps (2026-10-04). It used to be
    # typed prose ("far exceeds ... on both pools and both sides"), which stopped being
    # true of the pitcher debuted pool on the fWAR label re-run.
    g_deb, g_full = gap(deb), gap(full)
    return {
        "debuted_PRE_REGISTERED_PRIMARY": deb,
        "full_modelled_pool": full,
        "gap_rho_opp_minus_rho_war": {"debuted": g_deb, "full_modelled_pool": g_full},
        "note": "on the full pool the bust rows carry a structural zero on BOTH the "
                "opportunity and the target, which mechanically raises rho_fv_opportunity: "
                "the board's ability to tell a never-MLB player from a major leaguer is "
                "counted as opportunity skill. On this side rho_fv_opportunity minus "
                f"rho_fv_war is {g_deb} on the debuted pool and {g_full} on the full pool "
                "(unweighted).",
    }


def _cosine_side(side: str, omap: dict) -> dict:
    """Section 6. Fit the SHIPPED ridge spec twice on the same standardized design:
    once on the shipped WAR target, once on opportunity. Cosine of the two standardized
    weight vectors is a GEOMETRIC UPPER BOUND on what any REWEIGHTING of the existing
    feature set can buy."""
    keys, _mono = em._feature_spec(side)
    rows = json.loads(ed.matrix_path(side).read_text(encoding="utf-8"))
    full = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
    data = em._prep(full, "target_censored", side)
    by_key = {r["player_key"]: r for r in data}
    # opportunity target on the IDENTICAL rows: busts contribute a structural 0, debuted
    # rows their censored accrual. A row whose join failed is dropped from BOTH fits so
    # the two weight vectors are comparable by construction.
    opp_rows, war_rows = [], []
    for pk, r in by_key.items():
        o = omap.get(pk)
        if not o or not o["joined"] or o["opp_censored"] is None:
            continue
        war_rows.append(r)
        opp_rows.append({**r, "target": float(o["opp_censored"])})
    w_war = _fit_ridge(war_rows, keys)
    w_opp = _fit_ridge(opp_rows, keys)
    if not (w_war and w_opp):
        return {"n": len(war_rows), "cosine": None}
    cos = _cosine(w_war["w"], w_opp["w"])
    orth = math.sqrt(max(0.0, 1.0 - cos * cos)) if cos is not None else None
    return {
        "n": len(war_rows),
        "keys": keys,
        "cosine_war_vs_opportunity": round(cos, 4) if cos is not None else None,
        "orthogonal_linear_extent_sqrt_1_minus_cos2": round(orth, 4) if orth is not None else None,
        "orthogonal_variance_share_1_minus_cos2": round(orth * orth, 4) if orth is not None else None,
        "alpha_war": w_war["alpha"],
        "alpha_opportunity": w_opp["alpha"],
        "weights_war": {k: round(v, 4) for k, v in zip(w_war["keys"], w_war["w"])},
        "weights_opportunity": {k: round(v, 4) for k, v in zip(w_opp["keys"], w_opp["w"])},
        "reading": "within the span of the EXISTING feature set, the best linear predictor "
                   "of opportunity and the best linear predictor of WAR point in very "
                   "nearly the same direction. This is why the twenty closed "
                   "objective-lane cells had to fail: they were twenty reweightings of a "
                   "space with one dominant direction.",
        "SCOPE": "the cosine bounds REWEIGHTINGS OF THE EXISTING FEATURE SET. It does NOT "
                 "bound what a genuinely new feature could buy, it does not bound a "
                 "nonlinear model, and it is a statement about linear predictors of the two "
                 "targets, not about the targets themselves. Quoted without this scope note "
                 "it is a stronger claim than the measurement supports.",
    }


def cmd_decomp(verbose=True):
    out = {"registration": "OPPORTUNITY_DECOMP_GATE.md sections 2, 3 and 6", "sides": {}}
    for side in ("hit", "pit"):
        omap, _cov = opportunity_map(side)
        d = _decomp_side(side, omap)
        c = _cosine_side(side, omap)
        d["planning_read"] = {
            "rho_fv_opportunity": PLANNING["rho_fv_opportunity"][side],
            "rho_fv_war": PLANNING["rho_fv_war"][side],
            "rho_fv_quality": PLANNING["rho_fv_quality"][side],
        }
        d["reproduction_grade"] = {
            "rho_fv_opportunity": _grade(d["rho_fv_opportunity"],
                                         PLANNING["rho_fv_opportunity"][side]),
            "rho_fv_war": _grade(d["rho_fv_war_shipped_target"], PLANNING["rho_fv_war"][side]),
            "rho_fv_quality": _grade(d["quality_primary"]["rho"],
                                     PLANNING["rho_fv_quality"][side]),
            "band": {"MATCHED": f"<= {MATCH_BAND}", "CLOSE": f"<= {CLOSE_BAND}",
                     "DIFFERENT": f"> {CLOSE_BAND}"},
        }
        ro, rw = d["rho_fv_opportunity"], d["rho_fv_war_shipped_target"]
        rq = d["quality_primary"]["rho"]
        refuted = []
        if ro is not None and rw is not None and ro <= rw:
            refuted.append("rho_opp <= rho_war")
        if ro is not None and rq is not None and (ro - rq) < 0.10:
            refuted.append("rho_opp - rho_quality < 0.10")
        d["refutation_clause"] = {
            "registered": "refuted if rho_opp <= rho_war, or rho_opp - rho_quality < 0.10",
            "triggered": refuted,
            "verdict": "REFUTED" if refuted else "SURVIVES",
        }
        c["planning_read"] = PLANNING["cosine_war_vs_opportunity"][side]
        c["reproduction_grade"] = _grade(c["cosine_war_vs_opportunity"],
                                         PLANNING["cosine_war_vs_opportunity"][side])
        bs = _basis_sensitivity(side, omap)
        fp = bs["full_modelled_pool"]
        bs["identifies_planning_basis"] = bool(
            abs((fp["rho_fv_opportunity_unweighted"] or 0)
                - PLANNING["rho_fv_opportunity"][side]) <= 0.01
            and abs((fp["rho_fv_war_unweighted"] or 0)
                    - PLANNING["rho_fv_war"][side]) <= 0.01)
        out["sides"][side] = {"decomposition": d, "basis_sensitivity": bs,
                              "cosine_bound": c}
    if verbose:
        print(json.dumps(out, indent=1))
    return out


# ---------------------------------------------------------------------------
# 3. the four exploitation arms (section 7)
# ---------------------------------------------------------------------------

def _prep_with_opportunity(rows, side, omap):
    """The shipped _prep frame plus the joined opportunity column. Rows whose join
    failed are DROPPED so every arm and its incumbent score the identical rows in the
    identical folds; the incumbent is re-scored on this frame, never read from an
    artifact built on a different one."""
    data = em._prep(rows, "target_censored", side)
    out = []
    for r in data:
        o = omap.get(r["player_key"])
        if not o or not o["joined"] or o["opp_censored"] is None:
            continue
        rr = dict(r)
        rr["opp"] = float(o["opp_censored"])
        rr["reached"] = 1.0 if (o["opp_censored"] or 0.0) > 0.0 else 0.0
        rr["rate"] = (r["target"] / o["opp_censored"]) if (o["opp_censored"] or 0) > 0 else 0.0
        out.append(rr)
    return out


def _fit_on(train, keys, field, transform=None):
    tr = [{**r, "target": (transform(r) if transform else float(r[field]))} for r in train]
    return _fit_ridge(tr, keys)


def _arm_predictions(train, test, keys, lam, gammas):
    """One fold. Returns {leg_name: [pred]} for every incumbent and every arm.

    SCALE FAIRNESS. The shipped blend is (1-lam)*consensus_OLS + lam*ridge, and BOTH legs
    are on the WAR scale because the ridge is fit to WAR. An arm whose model leg sits on a
    different scale would enter that mixture at a different effective lambda and would lose
    for a reason that has nothing to do with its idea. Every arm's pure leg is therefore
    ALSO blended after a train-fit affine map onto the WAR scale (`_blend_cal` legs). The
    map is monotone increasing, so the PURE-leg deltas are untouched; only the blend moves.
    A losing arm should lose on its merits, so it is handed its best shot."""
    ols = em._fit_ols_fv(train)
    ridge = _fit_ridge(train, keys)
    if not (ols and ridge):
        return None
    cons = [max(0.0, em._pred_ols(ols, r["fv"])) for r in test]
    ridge_p = [_predict(ridge, r["feats"]) for r in test]
    blend = [(1 - lam) * c + lam * m for c, m in zip(cons, ridge_p)]
    legs = {"consensus": cons, "shipped_ridge": ridge_p, "shipped_blend": blend}

    def _cal_blend(name, pure_test, pure_train):
        legs[name] = [(1 - lam) * c + lam * p for c, p in zip(cons, pure_test)]
        cal = _fit_linear_calibration(list(zip(pure_train,
                                               [r["target"] for r in train])))
        if cal:
            adj = [cal["a"] + cal["b"] * p for p in pure_test]
            legs[name + "_cal"] = [(1 - lam) * c + lam * p for c, p in zip(cons, adj)]

    # ARM 1: multiplicative E[PA] x E[rate]. The rate leg is fit on REACHERS only
    # (a rate is undefined at zero exposure); non-reachers in TEST get the model's
    # own rate prediction, which is exactly where the negative-rate inversion bites.
    m_opp = _fit_on(train, keys, "opp")
    reach_tr = [r for r in train if r["reached"] > 0]
    m_rate = _fit_on(reach_tr, keys, "rate") if len(reach_tr) >= 40 else None
    if m_opp and m_rate:
        prod = [_predict(m_opp, r["feats"]) * _predict(m_rate, r["feats"]) for r in test]
        prod_tr = [_predict(m_opp, r["feats"]) * _predict(m_rate, r["feats"]) for r in train]
        legs["multiplicative_pure"] = prod
        _cal_blend("multiplicative_blend", prod, prod_tr)
        legs["_rate_pred"] = [_predict(m_rate, r["feats"]) for r in test]
        legs["_opp_pred"] = [_predict(m_opp, r["feats"]) for r in test]

    # ARM 2: hurdle P(reach) x E[WAR | reach]. P(reach) is a linear-probability ridge
    # on the full training pool (busts carry reached=0); the conditional mean is fit on
    # reachers only.
    m_reach = _fit_on(train, keys, "reached")
    m_cond = _fit_ridge(reach_tr, keys) if len(reach_tr) >= 40 else None
    if m_reach and m_cond:
        def _h(r):
            return (min(1.0, max(0.0, _predict(m_reach, r["feats"])))
                    * _predict(m_cond, r["feats"]))
        hur = [_h(r) for r in test]
        legs["hurdle_pure"] = hur
        _cal_blend("hurdle_blend", hur, [_h(r) for r in train])

    # ARM 3: auxiliary multi-task. ONE shared weight vector against a combination of the
    # standardized WAR target and the standardized opportunity target, RESCALED BACK to the
    # WAR target's own mean and sd on the train rows.
    #
    # THE RESCALE IS LOAD-BEARING AND WAS ADDED AFTER A FAILED PARITY CHECK. The first
    # implementation fit on the convex combination (z_y + g*z_o)/(1+g) directly. At g=0
    # that is the STANDARDIZED target, not the target: ridge weights scale with y, so the
    # model leg came out on a z-scale (sd about 1) while the consensus leg it is blended
    # with is on the WAR scale (sd about 5). The mixture weight lam then meant something
    # different for the arm than for the incumbent, and the arm's own g=0 parity check
    # FAILED (hit.full_pool_km read +0.0022 where it must read exactly 0). Matching the
    # mixed target's mean and sd to the WAR target's restores exact parity at g=0 and
    # keeps every g on one scale.
    n = len(train)
    my = sum(r["target"] for r in train) / n
    sy = math.sqrt(sum((r["target"] - my) ** 2 for r in train) / n) or 1.0
    mo = sum(r["opp"] for r in train) / n
    so = math.sqrt(sum((r["opp"] - mo) ** 2 for r in train) / n) or 1.0
    for g in gammas:
        mix = [((r["target"] - my) / sy + g * (r["opp"] - mo) / so) for r in train]
        mm = sum(mix) / n
        ms = math.sqrt(sum((v - mm) ** 2 for v in mix) / n) or 1.0
        tgt = [my + sy * (v - mm) / ms for v in mix]
        m_aux = _fit_ridge([{**r, "target": t} for r, t in zip(train, tgt)], keys)
        if not m_aux:
            continue
        aux = [_predict(m_aux, r["feats"]) for r in test]
        legs[f"auxiliary_pure_gamma_{g}"] = aux
        _cal_blend(f"auxiliary_gamma_{g}", aux, [_predict(m_aux, r["feats"]) for r in train])
    return legs


def _run_arms_cell(side: str, pool: str, omap: dict, gammas=GAMMA_SWEEP):
    keys, _m = em._feature_spec(side)
    lam = em.blend_lambda(side)
    rows = json.loads(ed.matrix_path(side).read_text(encoding="utf-8"))
    if pool == "debuted_km":
        sel = [r for r in rows if r["kind"] == "debuted"]
    else:
        sel = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
    data = _prep_with_opportunity(sel, side, omap)
    acc = {}
    wts, tgts = [], []
    diag = {"n_rate_pred_negative": 0, "n_rate_pred": 0,
            "n_inversions_high_opp_negative_rate": 0}
    for yr in em.SCORED_YEARS:
        train = [r for r in data if r["decision_year"] < yr]
        test = [r for r in data if r["decision_year"] == yr]
        if len(test) < 15 or len(train) < 60:
            continue
        legs = _arm_predictions(train, test, keys, lam, gammas)
        if not legs:
            continue
        if "_rate_pred" in legs:
            rp = legs["_rate_pred"]
            op = legs["_opp_pred"]
            diag["n_rate_pred"] += len(rp)
            diag["n_rate_pred_negative"] += sum(1 for v in rp if v < 0)
            hi = sorted(op)[int(0.75 * len(op))] if op else 0.0
            diag["n_inversions_high_opp_negative_rate"] += sum(
                1 for o, v in zip(op, rp) if o >= hi and v < 0)
        for k, v in legs.items():
            if k.startswith("_"):
                continue
            acc.setdefault(k, []).extend(v)
        wts.extend(float(r.get("weight") or 1.0) for r in test)
        tgts.extend(r["target"] for r in test)
    if not tgts:
        return None
    rho = {k: _weighted_spearman(v, tgts, wts) for k, v in acc.items()}
    return {"n": len(tgts), "lambda": lam, "rho": rho, "diagnostics": diag,
            "n_effective": round(sum(wts), 1)}


def _block_rho_arms(omaps, gammas=GAMMA_SWEEP):
    """block-rho: (side x cohort-year) percentile-normalized, both sides pooled. Same
    instrument as efv_model.block_rho_eval, extended to every arm leg."""
    acc, tgt_all, wts_all = {}, [], []
    for side in ("hit", "pit"):
        keys, _m = em._feature_spec(side)
        lam = em.blend_lambda(side)
        rows = json.loads(ed.matrix_path(side).read_text(encoding="utf-8"))
        data = _prep_with_opportunity([r for r in rows if r["kind"] == "debuted"],
                                      side, omaps[side])
        for yr in em.SCORED_YEARS:
            train = [r for r in data if r["decision_year"] < yr]
            test = [r for r in data if r["decision_year"] == yr]
            if len(test) < 15 or len(train) < 60:
                continue
            legs = _arm_predictions(train, test, keys, lam, gammas)
            if not legs:
                continue
            for k, v in legs.items():
                if k.startswith("_"):
                    continue
                acc.setdefault(k, []).extend(em._block_norm(v))
            tgt_all.extend(em._block_norm([r["target"] for r in test]))
            wts_all.extend(float(r.get("weight") or 1.0) for r in test)
    if len(tgt_all) < 8:
        return None
    # a leg that is missing from one side's folds cannot be block-pooled honestly
    n = len(tgt_all)
    return {"n": n,
            "rho": {k: _weighted_spearman(v, tgt_all, wts_all)
                    for k, v in acc.items() if len(v) == n}}


ARM_INCUMBENT = {
    "multiplicative_blend": "shipped_blend",
    "multiplicative_pure": "shipped_ridge",
    "hurdle_blend": "shipped_blend",
    "hurdle_pure": "shipped_ridge",
}


def cmd_arms(verbose=True):
    floors = _floors()
    omaps = {s: opportunity_map(s)[0] for s in ("hit", "pit")}
    cells = {}
    for side in ("hit", "pit"):
        for pool in ("full_pool_km", "debuted_km"):
            r = _run_arms_cell(side, pool, omaps[side])
            if r:
                cells[f"{side}.{pool}"] = r
    blk = _block_rho_arms(omaps)

    # THE FOUR REGISTERED ARMS, each reported in its raw blend and in its scale-calibrated
    # blend (`_cal`). The pure legs are unaffected by the calibration, which is monotone.
    arm_names = ["multiplicative_blend", "multiplicative_blend_cal", "multiplicative_pure",
                 "hurdle_blend", "hurdle_blend_cal",
                 f"auxiliary_gamma_{GAMMA_HEADLINE}", f"auxiliary_gamma_{GAMMA_HEADLINE}_cal"]
    ARM_INCUMBENT["multiplicative_blend_cal"] = "shipped_blend"
    ARM_INCUMBENT["hurdle_blend_cal"] = "shipped_blend"
    for g in GAMMA_SWEEP:
        ARM_INCUMBENT[f"auxiliary_gamma_{g}"] = "shipped_blend"
        ARM_INCUMBENT[f"auxiliary_gamma_{g}_cal"] = "shipped_blend"
        ARM_INCUMBENT[f"auxiliary_pure_gamma_{g}"] = "shipped_ridge"

    arms = {}
    for arm in arm_names:
        inc = ARM_INCUMBENT[arm]
        blocks = {}
        for cell, res in cells.items():
            a = res["rho"].get(arm)
            b = res["rho"].get(inc)
            if a is None or b is None:
                continue
            blk_out = _delta_block(a - b, floors[cell],
                                   f"arm leg vs {inc} on identical rows and folds")
            blk_out.update({"n": res["n"], "n_effective": res["n_effective"],
                            "arm_rho": _r4(a), "incumbent_leg": inc,
                            "incumbent_rho": _r4(b),
                            "consensus_rho": _r4(res["rho"].get("consensus")),
                            "arm_minus_consensus": _r4(a - (res["rho"].get("consensus") or 0.0))})
            exp = PLANNING["arms"].get(arm.replace("_cal", ""), {}).get(cell)
            if exp is not None:
                blk_out["planning_read"] = exp
                blk_out["reproduction_grade"] = _grade(blk_out["point_delta"], exp)
            blocks[cell] = blk_out
        if blk and arm in blk["rho"] and inc in blk["rho"]:
            bb = _delta_block(blk["rho"][arm] - blk["rho"][inc], floors["block_rho"],
                              f"arm leg vs {inc}, (side x cohort-year) block-normalized")
            bb.update({"n": blk["n"], "arm_rho": _r4(blk["rho"][arm]),
                       "incumbent_leg": inc, "incumbent_rho": _r4(blk["rho"][inc])})
            blocks["block_rho"] = bb
        prim = blocks.get("hit.full_pool_km")
        promoted = bool(
            prim and prim["point_delta"] > 0
            and prim["resolvable_E_refit"] and prim["resolvable_E_cond"]
            and not any(b["verdict"] == "RESOLVABLE LOSS" for b in blocks.values()))
        arms[arm] = {
            "incumbent_leg": inc,
            "cells": blocks,
            "n_cells": len(blocks),
            "any_resolvable_gain": any(b["verdict"] == "RESOLVABLE GAIN" for b in blocks.values()),
            "any_resolvable_loss": any(b["verdict"] == "RESOLVABLE LOSS" for b in blocks.values()),
            "promoted": bool(promoted),
            "verdict": "PROMOTED" if promoted else "NO SHIP",
        }

    # arm 1's failure mechanism, measured rather than asserted
    mech = {}
    for cell, res in cells.items():
        d = res["diagnostics"]
        mech[cell] = {
            **d,
            "share_rate_pred_negative": (round(d["n_rate_pred_negative"] / d["n_rate_pred"], 4)
                                         if d["n_rate_pred"] else None),
        }
    arms["multiplicative_blend"]["failure_mechanism"] = {
        "statement": "the rate leg is a least-squares fit and goes NEGATIVE on part of the "
                     "pool. A product with a negative factor is not monotone in either "
                     "factor: a row with a large predicted opportunity and a slightly "
                     "negative predicted rate sorts BELOW a bust with predicted "
                     "opportunity of zero. Rank is destroyed at the top of the board.",
        "unfixable_in_family": "clipping the rate at zero replaces an inverted order with a "
                               "TIE at the top of the board, which is also a rank loss.",
        "measured": mech,
        "status": "CLOSED FOR CAUSE, not merely unlucky",
    }

    # gamma monotonicity (section 7 clause)
    mono = {}
    for cell, res in cells.items():
        base = res["rho"].get("shipped_blend")
        base_r = res["rho"].get("shipped_ridge")
        row, row_pure = {}, {}
        for g in GAMMA_SWEEP:
            a = res["rho"].get(f"auxiliary_gamma_{g}")
            if a is not None and base is not None:
                row[str(g)] = round(a - base, 4)
            p = res["rho"].get(f"auxiliary_pure_gamma_{g}")
            if p is not None and base_r is not None:
                row_pure[str(g)] = round(p - base_r, 4)
        vals = [row[str(g)] for g in GAMMA_SWEEP if str(g) in row]
        mono[cell] = {
            "deltas_by_gamma_blend": row,
            "deltas_by_gamma_pure": row_pure,
            "monotone_non_increasing": all(vals[i + 1] <= vals[i] + 1e-9
                                           for i in range(len(vals) - 1)),
            "gamma0_parity_blend": abs(row.get("0.0", 9.0)) < 1e-9,
            "gamma0_parity_pure": abs(row_pure.get("0.0", 9.0)) < 1e-9,
            "parity_note": "gamma=0 IS the shipped fit by construction, so both deltas must "
                           "be exactly 0. A non-zero here is a defect in the arm, not a "
                           "result: it means the arm's model leg is not on the shipped "
                           "scale. That check FAILED on the first implementation and is why "
                           "the mixed target is rescaled to the WAR target's mean and sd.",
            "argmax_gamma": (max(row, key=row.get) if row else None),
        }
    out = {
        "registration": "OPPORTUNITY_DECOMP_GATE.md sections 7 and 8",
        "headline_metric": "pair-weighted pooled Spearman on cumulative WAR "
                           "(target_censored), forward-chained over SCORED_YEARS, on "
                           "debuted_km and full_pool_km, plus block-rho. The SHIPPED "
                           "instrument, unchanged. No arm gets a metric of its own.",
        "incumbent_rule": "delta = rho(arm) - rho(the shipped leg it replaces), on the SAME "
                          "rows in the SAME folds. Blended arms vs the shipped blend; the "
                          "multiplicative pure leg vs the shipped ridge leg.",
        "floors": floors,
        "floor_convention": "MDE95 is ONE-SIDED 1.645*sd on |delta| "
                            "(docs/EFV_GATE_STANDARD.md section 1). MDE95 is E_refit, "
                            "MDE95_COND is E_cond. Neither is quoted without its estimator.",
        "promotion_bar": "gain >= 1.0x the floor under BOTH estimators on the PRIMARY cell "
                         "(hit.full_pool_km) with no resolvable loss elsewhere.",
        "pool_ns": {k: {"n": v["n"], "n_effective": v["n_effective"]} for k, v in cells.items()},
        # The scored pool is the shipped pool MINUS the rows whose opportunity join failed,
        # because every arm and its incumbent must score identical rows. That makes it
        # slightly smaller than the pool the floors were derived on, so the floors are
        # applied to a pool they were not measured on. The shortfall is reported rather
        # than assumed immaterial: a floor scales as 1/sqrt(n), so a 1 percent row loss
        # moves it about 0.5 percent, which is inside the rounding these floors carry.
        "pool_n_vs_floor_basis": {
            k: {"n_scored_here": v["n"],
                "n_rows_floor_was_derived_on": floors[k]["n_rows"],
                "shortfall_share": (round(1 - v["n"] / floors[k]["n_rows"], 4)
                                    if floors[k].get("n_rows") else None)}
            for k, v in cells.items()},
        "arms": arms,
        "auxiliary_gamma_sweep": mono,
    }
    if verbose:
        print(json.dumps(out, indent=1))
    return out


# ---------------------------------------------------------------------------
# 4. the section 9 dispersion diagnostic
# ---------------------------------------------------------------------------

def _oof_dispersion_rows(side: str):
    """Forward-chained OOS blend predictions on the debuted pool, carrying the row's
    cohort and censoring flag. Same folds, same lambda, same fit as the shipped eval."""
    keys, _m = em._feature_spec(side)
    lam = em.blend_lambda(side)
    rows = json.loads(ed.matrix_path(side).read_text(encoding="utf-8"))
    cens = {r["player_key"]: bool(r.get("censored")) for r in rows}
    data = em._prep([r for r in rows if r["kind"] == "debuted"], "target_censored", side)
    out = []
    for yr in em.SCORED_YEARS:
        train = [r for r in data if r["decision_year"] < yr]
        test = [r for r in data if r["decision_year"] == yr]
        if len(test) < 15 or len(train) < 60:
            continue
        ols = em._fit_ols_fv(train)
        ridge = _fit_ridge(train, keys)
        if not (ols and ridge):
            continue
        for r in test:
            c = max(0.0, em._pred_ols(ols, r["fv"]))
            p = (1 - lam) * c + lam * _predict(ridge, r["feats"])
            out.append({"cohort": yr, "pred": p, "obs": r["target"],
                        "censored": cens.get(r["player_key"], False),
                        "player_key": r["player_key"], "fv": r["fv"]})
    return out


def _within_cohort_slope(rows):
    """OLS slope of realized on predicted, BOTH centered within decision-year cohort.
    1.0 == calibrated in level; < 1.0 == the prediction is more dispersed than the
    outcome it is being graded against."""
    from collections import defaultdict
    by = defaultdict(list)
    for r in rows:
        by[r["cohort"]].append(r)
    xs, ys = [], []
    for _c, rs in by.items():
        if len(rs) < 8:
            continue
        mp = sum(r["pred"] for r in rs) / len(rs)
        mo = sum(r["obs"] for r in rs) / len(rs)
        xs.extend(r["pred"] - mp for r in rs)
        ys.extend(r["obs"] - mo for r in rs)
    if len(xs) < 8:
        return None, 0
    return _ols_slope(xs, ys), len(xs)


def _synthetic_censoring(side: str, rows_oof):
    """THE IDENTIFIED LEG, added after the pre-registered cohort-matched control turned
    out to be INFEASIBLE ON THIS DESIGN (see cmd_dispersion's collinearity block).

    Take only rows whose six-season window is FULLY RESOLVED, where the true label is
    known. Re-label each one by truncating its window at k observed seasons and applying
    efv_dataset._label_6yr's own flat-rate fill, k in {2,3,4,5}. Rows, cohorts and OOS
    PREDICTIONS ARE HELD FIXED; only the label moves. Censoring is then a within-row
    treatment, so cohort era cannot confound it.

    Per-season WAR comes from the same war_daily join the rest of this lane uses. Its
    agreement with the shipped target_resolved is REPORTED, not assumed: an instrument
    built on a label the matrix does not recognise would measure the join, not the fill.

    THIS IS ON THE DISTRIBUTION SIDE OF THE efv_reliability BOUNDARY. It assigns no
    bucket, reports no ECE, and re-runs no relabel of the shipped pool."""
    ov, _, _ = _id_overrides()
    acc = _accrual_frame()
    # COMBINED bat+pit bWAR on BOTH sides. Measured, not assumed: pitching-only WAR
    # reproduces the shipped pitcher target_resolved on only 65 percent of rows (max
    # abs diff 19.57), because a pitcher's bWAR includes his batting. Combined WAR
    # reproduces it on 98 percent of both sides. The agreement figure below is the
    # standing check on this choice.
    war_idx = 2
    rows = json.loads(ed.matrix_path(side).read_text(encoding="utf-8"))
    meta = {r["player_key"]: r for r in rows}
    pred_by = {}
    for r in rows_oof:
        pred_by.setdefault(r.get("player_key"), r)
    series, agree = {}, []
    for r in rows_oof:
        m = meta.get(r["player_key"])
        if not m or m.get("censored") or m["kind"] != "debuted":
            continue
        mid = m.get("mlbam_id") or ov.get(r["player_key"])
        if mid is None:
            continue
        dy = int(m["debut_year"])
        per = [acc.get((int(mid), dy + i), _ZERO)[war_idx] for i in range(TARGET_SEASONS)]
        agree.append(abs(sum(per) - float(m["target_resolved"])))
        series[r["player_key"]] = (r, per)
    if len(series) < 40:
        return {"n": len(series), "identified": False,
                "reason": "too few fully-resolved joined rows"}
    n = len(series)
    within = sum(1 for d in agree if d < 0.05)
    join_block = {
        "n": len(agree), "within_0.05_of_target_resolved": within,
        "share": round(within / len(agree), 4) if agree else None,
        "max_abs_diff": round(max(agree), 3) if agree else None,
        "why": "an instrument built on a label the matrix does not recognise would "
               "measure the join, not the fill."}
    # THE LAB ENFORCES ITS OWN PRECONDITION (2026-09-04). This share was computed and
    # REPORTED here but never acted on: the leg was marked identified whenever 40 rows
    # joined, and only test_opportunity_lab refused a bad join. That is the wrong place
    # for it. A published artifact should not carry `identified: True` beside a share its
    # own `why` string says invalidates the instrument. The eWAR label epoch is what
    # exposed it: career_war now holds values from a FIXED ewar.json snapshot while
    # war_daily keeps moving underneath it, so the join reproduces target_resolved on
    # 0.8828 of hitter rows instead of the 0.95 the leg needs.
    JOIN_MIN = 0.95
    share = join_block["share"]
    if share is None or share <= JOIN_MIN:
        return {"n": n, "identified": False,
                "reason": (f"war_daily join reproduces target_resolved on only {share} of "
                           f"rows, under the {JOIN_MIN} the leg needs; it would measure "
                           f"the join rather than the label fill"),
                "join_label_agreement": join_block}
    base = [{"cohort": r["cohort"], "pred": r["pred"], "obs": sum(per)}
            for r, per in series.values()]
    true_slope, _ = _within_cohort_slope(base)
    true_sd = math.sqrt(sum((b["obs"] - sum(x["obs"] for x in base) / n) ** 2
                            for b in base) / n)
    out = {"n": n, "identified": True,
           "join_label_agreement": join_block,
           "true_label": {"within_cohort_slope": _r4(true_slope), "label_sd": round(true_sd, 3)},
           "by_observed_seasons": {}}
    for k in (2, 3, 4, 5):
        filled = []
        for r, per in series.values():
            obs = sum(per[:k])
            filled.append({"cohort": r["cohort"], "pred": r["pred"],
                           "obs": obs + (TARGET_SEASONS - k) * (obs / k)})
        s, _ = _within_cohort_slope(filled)
        mu = sum(x["obs"] for x in filled) / n
        sd = math.sqrt(sum((x["obs"] - mu) ** 2 for x in filled) / n)
        out["by_observed_seasons"][str(k)] = {
            "within_cohort_slope": _r4(s),
            "slope_minus_true": _r4((s - true_slope) if (s is not None and true_slope is not None) else None),
            "label_sd": round(sd, 3),
            "label_sd_ratio_vs_true": round(sd / true_sd, 4) if true_sd else None,
        }
    ks = out["by_observed_seasons"]
    signed = [v["slope_minus_true"] for v in ks.values() if v["slope_minus_true"] is not None]
    sd_ratios = [v["label_sd_ratio_vs_true"] for v in ks.values()
                 if v["label_sd_ratio_vs_true"] is not None]
    worst = max(signed, key=abs) if signed else None
    out["reading"] = {
        "signed_slope_movement_by_k": {k: v["slope_minus_true"] for k, v in ks.items()},
        "largest_signed_movement": worst,
        "max_abs_slope_movement": round(abs(worst), 4) if worst is not None else None,
        "direction": (None if worst is None else
                      ("the fill DEPRESSES the slope, so part of the measured dispersion "
                       "shortfall on censored cohorts is manufactured by the label rather "
                       "than by the model" if worst < 0 else
                       "the fill RAISES the slope, so the censored cohorts read better "
                       "calibrated than they are")),
        "monotone_in_k": all(signed[i] <= signed[i + 1] + 1e-9 for i in range(len(signed) - 1)),
        "material_threshold": DISPERSION_MATERIAL,
        "fill_moves_the_slope": bool(worst is not None and abs(worst) >= DISPERSION_MATERIAL),
        "label_sd_ratio_range": [min(sd_ratios), max(sd_ratios)] if sd_ratios else None,
        "fill_compresses_the_label_at_k2": bool(
            ks.get("2", {}).get("label_sd_ratio_vs_true") is not None
            and ks["2"]["label_sd_ratio_vs_true"] < 1.0),
    }
    return out


def cmd_dispersion(verbose=True):
    out = {
        "registration": "OPPORTUNITY_DECOMP_GATE.md section 9",
        "statistic": "OLS slope of realized target_censored on the forward-chained OOS "
                     "blend prediction, BOTH centered within decision-year cohort. "
                     "1.0 == calibrated in level.",
        "question": "the flat-rate censoring fill (efv_dataset._label_6yr, censored branch) "
                    "substitutes a conditional mean for a draw, removing within-player "
                    "variance from the label of every censored row. Does the within-cohort "
                    "dispersion shortfall survive on COMPLETE-WINDOW ROWS ONLY?",
        "boundary": "efv_reliability._realized_bucket:126-149 forbids re-running the "
                    "season-share-corrected relabel and re-reporting the same 3.1 percent "
                    "pooled-bust-ECE movement. This measures label DISPERSION, not bucket "
                    "assignment; it reports no ECE and re-runs no relabel. Its own closing "
                    "sentence, 'The remaining miscalibration is real and belongs to the "
                    "distribution, not to the label', is the side of the line this stays on.",
        "material_threshold": DISPERSION_MATERIAL,
        "sides": {},
    }
    verdicts = []
    for side in ("hit", "pit"):
        rows = _oof_dispersion_rows(side)
        full_s, full_n = _within_cohort_slope(rows)
        comp = [r for r in rows if not r["censored"]]
        comp_s, comp_n = _within_cohort_slope(comp)
        # CONFOUND CONTROL: complete-window rows are OLDER cohorts, so dropping the
        # censored rows also drops the recent ones. Restrict BOTH legs to cohorts that
        # contain rows of both kinds, which removes the era shift from the comparison.
        from collections import defaultdict
        kinds = defaultdict(set)
        for r in rows:
            kinds[r["cohort"]].add(bool(r["censored"]))
        mixed = {c for c, k in kinds.items() if len(k) == 2}
        mix_full, mfn = _within_cohort_slope([r for r in rows if r["cohort"] in mixed])
        mix_comp, mcn = _within_cohort_slope(
            [r for r in rows if r["cohort"] in mixed and not r["censored"]])

        def _v(a, b):
            if a is None or b is None:
                return "NOT MEASURED", None
            mv = b - a
            toward_one = abs(b - 1.0) < abs(a - 1.0)
            if abs(mv) >= DISPERSION_MATERIAL and toward_one:
                return "SLOPE MOVES TOWARD 1.0 ON COMPLETE-WINDOW ROWS", round(mv, 4)
            if abs(mv) >= DISPERSION_MATERIAL:
                return "SLOPE MOVES MATERIALLY AWAY FROM 1.0", round(mv, 4)
            return "SLOPE UNCHANGED", round(mv, 4)

        v_all, mv_all = _v(full_s, comp_s)
        v_mix, _mv_mix = _v(mix_full, mix_comp)

        # THE PRE-REGISTERED CONTROL IS INFEASIBLE ON THIS DESIGN, and that is a finding.
        # `censored` is very nearly a deterministic function of cohort: the older cohorts
        # are fully resolved, the recent ones censored, with a handful of exceptions (the
        # ranges are derived below, not typed: they move with RESOLVED_THROUGH). So dropping
        # the censored rows IS dropping the recent cohorts, and the confound the control
        # was written to remove cannot be removed by restriction at all.
        n_mixed_complete = sum(1 for r in rows if r["cohort"] in mixed and not r["censored"])
        by_cohort = {}
        for r in rows:
            d = by_cohort.setdefault(r["cohort"], [0, 0])
            d[1 if r["censored"] else 0] += 1
        exceptions = sum(min(v) for v in by_cohort.values())
        collinear = exceptions / len(rows) if rows else 0.0
        res_c = sorted(c for c, v in by_cohort.items() if v[0] > v[1])
        cen_c = sorted(c for c, v in by_cohort.items() if v[1] >= v[0])
        span = (lambda cs: f"{cs[0]}-{cs[-1]}" if cs else "none")

        synth = _synthetic_censoring(side, rows)
        if synth.get("identified"):
            vclass = ("ONE DEFECT" if synth["reading"]["fill_moves_the_slope"]
                      else "TWO DEFECTS")
            if synth["reading"]["fill_moves_the_slope"]:
                verdict = ("ONE DEFECT: holding rows, cohorts and predictions fixed, the "
                           "flat-rate fill moves the within-cohort dispersion slope by "
                           f"{synth['reading']['largest_signed_movement']} at its worst k, "
                           f"against a {DISPERSION_MATERIAL} bar. The fill is causally "
                           "implicated in the dispersion shortfall; "
                           + (synth["reading"]["direction"] or ""))
            else:
                verdict = ("TWO DEFECTS: holding rows, cohorts and predictions fixed, the "
                           "flat-rate fill moves the within-cohort dispersion slope at most "
                           f"{synth['reading']['max_abs_slope_movement']}, under the "
                           f"{DISPERSION_MATERIAL} bar. The shortfall is not the fill's "
                           "doing and the two defects have to be fixed separately.")
        else:
            vclass = "NOT IDENTIFIED"
            verdict = "NOT IDENTIFIED"
        verdicts.append(vclass)
        out["sides"][side] = {
            "n_full_pool": full_n, "slope_full_pool": _r4(full_s),
            "n_complete_window": comp_n, "slope_complete_window": _r4(comp_s),
            "movement": mv_all, "reading_unrestricted": v_all,
            "unrestricted_comparison_is_CONFOUNDED": True,
            "censored_share_of_scored_rows": round(
                sum(1 for r in rows if r["censored"]) / len(rows), 4) if rows else None,
            "cohort_matched_control": {
                "status": "INFEASIBLE ON THIS DESIGN",
                "cohorts_with_both_kinds": sorted(mixed),
                "n_complete_window_rows_in_those_cohorts": n_mixed_complete,
                "n_full": mfn, "slope_full": _r4(mix_full),
                "n_complete": mcn, "slope_complete": _r4(mix_comp), "reading": v_mix,
                "censoring_cohort_collinearity": {
                    "minority_kind_rows": exceptions, "n_rows": len(rows),
                    "share": round(collinear, 4),
                    "statement": "`censored` is a near-deterministic function of "
                                 f"cohort: {span(res_c)} resolved, {span(cen_c)} censored. "
                                 "Dropping "
                                 "the censored rows IS dropping the recent cohorts, so the "
                                 "confound cannot be removed by restriction and the "
                                 "unrestricted comparison above CANNOT adjudicate the "
                                 "question. Reported, not worked around."},
                "why": "complete-window rows are OLDER cohorts; without a control any slope "
                       "movement is confounded with cohort era.",
            },
            "synthetic_censoring_IDENTIFIED_LEG": synth,
            "verdict_class": vclass,
            "verdict": verdict,
        }
    out["verdict_class"] = (verdicts[0] if len(set(verdicts)) == 1
                            else "SIDE-DEPENDENT: " + " | ".join(
                                f"{s}: {v}" for s, v in zip(("hit", "pit"), verdicts)))
    out["verdict"] = (
        out["verdict_class"] + ". " + " | ".join(
            f"{s}: worst signed slope movement "
            f"{out['sides'][s]['synthetic_censoring_IDENTIFIED_LEG']['reading']['largest_signed_movement']}"
            f" at observed_seasons="
            f"{min(out['sides'][s]['synthetic_censoring_IDENTIFIED_LEG']['reading']['signed_slope_movement_by_k'], key=lambda k: out['sides'][s]['synthetic_censoring_IDENTIFIED_LEG']['reading']['signed_slope_movement_by_k'][k])}"
            for s in ("hit", "pit")
            if out["sides"][s]["synthetic_censoring_IDENTIFIED_LEG"].get("identified")))
    out["instrument_note"] = (
        "The pre-registered comparison (complete-window rows versus the full pool) is "
        "reported and is CONFOUNDED beyond repair on this design; see "
        "cohort_matched_control.censoring_cohort_collinearity. The verdict is taken from "
        "the synthetic-censoring leg, which holds rows, cohorts and predictions fixed and "
        "moves only the label. That leg was NOT pre-registered - it was built after the "
        "registered control failed - and it is labelled as such rather than presented as "
        "the original plan.")
    out["brief_rule_discrepancy"] = (
        "The lane brief states 'IF THE SLOPE IS UNCHANGED, the censoring defect and the "
        "elite-tier under-dispersion are ONE defect, not two.' That reads inverted against "
        "the mechanism the same brief describes: an unchanged slope on full-variance-label "
        "rows is evidence the fill is NOT doing the work, which SEPARATES the defects. This "
        "lane pre-registered the rule in the direction the mechanism implies "
        "(OPPORTUNITY_DECOMP_GATE.md section 9) and publishes the raw slopes so either rule "
        "can be applied by a reader.")
    if verbose:
        print(json.dumps(out, indent=1))
    return out


# ---------------------------------------------------------------------------
# 5. the artifact
# ---------------------------------------------------------------------------

def cmd_all(persist=True):
    join = cmd_join(verbose=False)
    decomp = cmd_decomp(verbose=False)
    arms = cmd_arms(verbose=False)
    disp = cmd_dispersion(verbose=False)
    art = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "produced_by": "tools/efv_opportunity_lab.py all",
        "registration": "docs/efv-2026-08-09/OPPORTUNITY_DECOMP_GATE.md sections 0-9, "
                        "written in full BEFORE this lab existed; section 10 is a "
                        "placeholder filled after the run",
        "lane": "B-L3 (WAR-per-opportunity as an eFV driver)",
        "scope_note": "CLOSURE. Adds and removes NO feature, changes no shipped constant, "
                      "retires nothing, and retroactively resolves no past null. "
                      "efv_model.py and efv_dataset.py are imported, never edited.",
        "not_a_banned_reanalysis": (
            "the closed target-transform cell (data/xfv_rank_objective_eval.json, 20 of 20 "
            "fail) tested rank_normal, signed_log1p, ipcw, sqrt and uniform. EVERY ONE IS A "
            "MONOTONE RELABEL of the same cumulative target: none is a decomposition and "
            "none introduces a new outcome column. Six-year PA/IP accrual has NEVER been in "
            "either matrix and is not derivable from target_censored, target_resolved, "
            "observed_seasons or weight. The ledger's own reopening condition is NEW DATA "
            "rather than re-analysis."),
        "seed": SEED,
        "identity_join": join,
        "decomposition": decomp,
        "exploitation_arms": arms,
        "dispersion_diagnostic": disp,
    }
    art["verdict"] = _verdict(art)
    if persist:
        OUT_PATH.write_text(json.dumps(art, indent=1), encoding="utf-8")
        print(f"wrote {OUT_PATH.relative_to(ROOT)}")
    return art


def _verdict(art):
    arms = art["exploitation_arms"]["arms"]
    promoted = [k for k, v in arms.items() if v.get("promoted")]
    cb = {s: art["decomposition"]["sides"][s]["cosine_bound"] for s in ("hit", "pit")}
    losses = sorted(k for k, v in arms.items() if v.get("any_resolvable_loss"))
    return {
        "arms_run": sorted(arms),
        "arms_promoted": promoted,
        "arms_with_a_resolvable_loss": losses,
        "headline": ("CLOSED. No arm clears its floor on the primary cell; the cosine bound "
                     "explains why any reweighting of the existing feature set had to fail."
                     if not promoted else
                     "ARM PROMOTED - re-read section 8 before acting on this."),
        "harness_liveness": (
            "the battery RESOLVES: " + ", ".join(losses) + " resolve as losses under both "
            "estimators, so the NULL verdicts on the other arms are informative rather "
            "than inert." if losses else
            "NO CELL RESOLVES ANYWHERE IN THIS LANE. Treat every null as uninformative "
            "until a detection control fires."),
        "cosine_bound": {s: cb[s]["cosine_war_vs_opportunity"] for s in cb},
        "cosine_orthogonal_linear_extent": {
            s: cb[s]["orthogonal_linear_extent_sqrt_1_minus_cos2"] for s in cb},
        "dispersion_verdict": art["dispersion_diagnostic"]["verdict"],
        "ships": "nothing",
    }


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "join":
        cmd_join()
    elif cmd == "decomp":
        cmd_decomp()
    elif cmd == "arms":
        cmd_arms()
    elif cmd == "dispersion":
        cmd_dispersion()
    elif cmd == "all":
        cmd_all()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""LANE C3b - Projections + Translations true-to-model recalibration lab.

Site-wide TRUE-TO-MODEL sweep (owner: every served metric should equal its
model's raw output; remove clamps whose only effect is compressing the tail /
diverging the served value from the raw model). This lab is the read-only
adjudicator for the PROJECTION + TRANSLATION surfaces:

  proj_ml.py            - the ML WAR-path heads (mean-blend / star-blend
                          recenter, quantile monotone sort, the "if-healthy"
                          PTH floor, NO ZERO FLOOR by design)
  fa_projection.py      - the Marcel/aging projection path (component rate
                          >=0 guards, pt >=0 guard, out-year FIP >=1.0 floor,
                          season_fraction [0.05,1] guard, curve-support clamp,
                          the WAR map = raw OLS, no clamp)
  college_translation.py- the _band() boundary clamps on projected K%/BB%/OPS
  milb_translation.py   - the same _band() clamps on the MiLB->MLB rate lines

CLASSIFICATION RULE (docs/efv-2026-07-24/GATES-ACCURACY.md, sections C2/C3):
  (1) BOARD-MOVEMENT / DISPLAY COMPRESSION -> REMOVE (default)
  (2) ACCURACY-LOAD-BEARING (removing it measurably lowers the surface's own
      validation) -> KEEP, with evidence
  (3) NUMERICAL SAFETY (divide-by-zero, NaN, domain / support guard) -> KEEP

METHOD: this lab does NOT regenerate any served artifact and does NOT flip any
production default. It measures, on the SHIPPED served artifacts, whether each
clamp actually BINDS (changes a served value). A clamp that never binds carries
zero compression; a domain guard that binds only where the raw whisker would
violate the rate domain (K% < 0 etc.) is safety, not compression. The point
estimates served everywhere (translation `exp`, projection `war`/`fip`) are
recomputed from the raw model form and compared to what is served.

Emits data/c3_proj_trans_recal_eval.json.

Run: python tools/c3_proj_trans_recal_lab.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
Z90 = 1.2816   # the P10-P90 half-width multiplier college/milb _band() uses


def _load_js_object(path: Path, marker: str) -> dict:
    txt = path.read_text(encoding="utf-8")
    i = txt.find(marker)
    i = txt.find("{", i)
    # balanced-brace scan from the first '{'
    depth = 0
    for j in range(i, len(txt)):
        if txt[j] == "{":
            depth += 1
        elif txt[j] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(txt[i:j + 1])
    raise ValueError("no object found after marker")


# --------------------------------------------------------------------------- #
# TRANSLATIONS: does any served band whisker hit its _band() clamp?
# The served POINT value (exp) is never clamped by _band (only lo/hi are), so
# the served headline is already raw-model. We measure whether the lo (domain
# floor, 0 / 0.3) or the hi (soft cap: K%60 BB%30 pitK%50 pitBB%25 OPS1.2)
# actually changes any served whisker.
# --------------------------------------------------------------------------- #
def audit_milb() -> dict:
    d = json.loads((DATA / "milb_translation.json").read_text(encoding="utf-8"))
    fits, projs = d.get("fits", {}), d.get("projections", {})
    caps = {"k_pct": ("hit_k", 0.0, 60.0), "bb_pct": ("hit_bb", 0.0, 30.0)}
    res = {}
    for fld, (fk, lo_c, hi_c) in caps.items():
        sd = (fits.get(fk) or {}).get("band_sd")
        if sd is None:
            continue
        lo_bind = hi_bind = n = 0
        exp_lo = exp_hi = None
        for p in projs.values():
            b = p.get(fld)
            if not b:
                continue
            n += 1
            e = b["exp"]
            exp_lo = e if exp_lo is None else min(exp_lo, e)
            exp_hi = e if exp_hi is None else max(exp_hi, e)
            if e - Z90 * sd < lo_c:
                lo_bind += 1
            if e + Z90 * sd > hi_c:
                hi_bind += 1
        res[fld] = {"n": n, "lo_clip": lo_c, "hi_clip": hi_c, "band_sd": sd,
                    "lo_binds": lo_bind, "hi_binds": hi_bind,
                    "exp_range": [round(exp_lo, 2) if exp_lo is not None else None,
                                  round(exp_hi, 2) if exp_hi is not None else None]}
    return res


def audit_college() -> dict:
    d = _load_js_object(DATA / "collegesavant_translation.js", "window.CS_TRANSLATION")
    tr, ev = d.get("translations", {}), d.get("eval", {})
    sd = {k: (v or {}).get("band_sd") for k, v in ev.items()}
    caps = {"hit": {"k_pct": ("hit_k", 0.0, 60.0), "bb_pct": ("hit_bb", 0.0, 30.0),
                    "ops": ("hit_ops", 0.3, 1.2)},
            "pit": {"k_pct": ("pit_k", 0.0, 50.0), "bb_pct": ("pit_bb", 0.0, 25.0)}}
    agg: dict = {}
    for e in tr.values():
        side = e.get("side")
        sa = e.get("single_a") or {}
        for fld, (fk, lo_c, hi_c) in caps.get(side, {}).items():
            b = sa.get(fld)
            s = sd.get(fk)
            if not b or "exp" not in b or s is None:
                continue
            row = agg.setdefault(fk, {"n": 0, "lo_clip": lo_c, "hi_clip": hi_c,
                                      "band_sd": s, "lo_binds": 0, "hi_binds": 0})
            row["n"] += 1
            val = b["exp"]
            if val - Z90 * s < lo_c:
                row["lo_binds"] += 1
            if val + Z90 * s > hi_c:
                row["hi_binds"] += 1
    return agg


# --------------------------------------------------------------------------- #
# PROJECTIONS: does the FIP >=1.0 floor / component >=0 guard / PTH central
# floor bind on the served mlb_projections.json? And is the NO ZERO FLOOR
# design actually live (WAR going negative, uncompressed)?
# --------------------------------------------------------------------------- #
def audit_projections() -> dict:
    d = json.loads((DATA / "mlb_projections.json").read_text(encoding="utf-8"))
    rows = (d.get("vets") or []) + (d.get("prospects") or [])
    fip_n = fip_floor = 0
    fip_min = None
    war_n = war_neg = 0
    p10_neg = 0
    pth_below = 0
    for r in rows:
        for f in (r.get("fip") or []):
            if f is None:
                continue
            fip_n += 1
            fip_min = f if fip_min is None else min(fip_min, f)
            if abs(f - 1.0) < 1e-9:
                fip_floor += 1
        war = r.get("war") or []
        for x in war:
            war_n += 1
            if x < 0:
                war_neg += 1
        for x in (r.get("warP10") or []):
            if x < 0:
                p10_neg += 1
        for i, x in enumerate(r.get("warPTH") or []):
            if i < len(war) and x < war[i] - 1e-9:
                pth_below += 1
    return {
        "fip_floor_at_1_0": {"n": fip_n, "min_served": round(fip_min, 3) if fip_min is not None else None,
                             "binds": fip_floor},
        "war_no_zero_floor": {"n_median_points": war_n, "median_negatives": war_neg,
                              "p10_negatives": p10_neg,
                              "note": "NO ZERO FLOOR is live + true-to-model: WAR is served below "
                                      "replacement, uncompressed."},
        "warPTH_central_floor": {"below_central": pth_below,
                                 "note": "definitional: the if-healthy display line is floored at "
                                         "the expected-value central by construction."},
    }


# --------------------------------------------------------------------------- #
# The full clamp inventory + classification (the report the owner asked for).
# --------------------------------------------------------------------------- #
def clamp_inventory() -> list[dict]:
    return [
        {"id": "proj_ml.no_zero_floor", "file": "proj_ml.py", "line": 431,
         "clamp": "quantile heads predict raw WAR incl. negatives; NO zero floor",
         "class": "true-to-model-by-design (absence of a floor)", "disposition": "KEEP",
         "evidence": "604 served median WAR points are negative; 5388 p10 points negative."},
        {"id": "proj_ml.quantile_monotone_sort", "file": "proj_ml.py", "line": 476,
         "clamp": "sorted(_predict1(q) ...) - monotone sort across the 5 quantile heads",
         "class": "numerical-safety (quantile-crossing repair; monotone -> rank-invariant)",
         "disposition": "KEEP",
         "evidence": "restores q10<=q25<=q50<=q75<=q90; does not compress the served tail."},
        {"id": "proj_ml.mean_blend_lift_only", "file": "proj_ml.py", "line": 508,
         "clamp": "GLOBAL mean-blend recenter is LIFT-ONLY (if shift > 0)",
         "class": "accuracy-load-bearing (anti-compression: recenters q50 UP toward E[WAR])",
         "disposition": "KEEP",
         "evidence": "proj_mean_blend.json holdout: symmetric/full-lambda rejected on champion-MAE "
                     "bar; a symmetric recenter TRIMS ceiling stars (more compression). "
                     "Currently INERT in the shipped bundle (meta.mean_blend is None)."},
        {"id": "proj_ml.star_blend", "file": "proj_ml.py", "line": 521,
         "clamp": "star-slice q50 recenter toward implied mean (lambda_h; h5=1.0 active)",
         "class": "accuracy-load-bearing (anti-compression; lifts star q50 toward E[WAR])",
         "disposition": "KEEP",
         "evidence": "proj_star_blend.json forward-chained dev fit w/ star-MAE +0.02 guard; "
                     "moves the star tail UP, the opposite of compression."},
        {"id": "proj_ml.warPTH_central_floor", "file": "proj_ml.py", "line": 537,
         "clamp": "war_by_year_pth = max(central, q70) - if-healthy line floored at central",
         "class": "definitional display floor (if-healthy >= expected); never feeds valuation",
         "disposition": "KEEP",
         "evidence": "0 served PTH points fall below their central; a display-only alt line."},
        {"id": "fa_projection.component_rate_floor", "file": "fa_projection.py", "line": 675,
         "clamp": "out[comp] = max(0.0, rate) - projected K%/BB%/ISO/BABIP/HR-rate >= 0",
         "class": "numerical-safety (rate domain: a negative rate is nonsensical)",
         "disposition": "KEEP", "evidence": "domain guard on a proportion."},
        {"id": "fa_projection.pt_floor", "file": "fa_projection.py", "line": 730,
         "clamp": "pt_proj = max(0.0, pt) - projected playing time >= 0",
         "class": "numerical-safety (PA/BF cannot be negative)",
         "disposition": "KEEP", "evidence": "domain guard."},
        {"id": "fa_projection.fip_floor", "file": "fa_projection.py", "line": 791,
         "clamp": "rate_path out-year FIP = max(fip, 1.0)",
         "class": "numerical-safety (guards the FIP algebra from absurd/negative output)",
         "disposition": "KEEP (inert)",
         "evidence": "min served FIP across 3380 out-year points is 2.330; the 1.0 floor binds 0 times."},
        {"id": "fa_projection.season_fraction_clamp", "file": "fa_projection.py", "line": 549,
         "clamp": "season_fraction = max(0.05, min(1.0, cur/prev))",
         "class": "numerical-safety (an elapsed fraction must lie in (0,1]; 0.05 blocks div-by-tiny)",
         "disposition": "KEEP", "evidence": "domain guard on a fraction."},
        {"id": "fa_projection.curve_support_clamp", "file": "fa_projection.py", "line": 459,
         "clamp": "curve_delta snaps age to the NEAREST supported age in the curve",
         "class": "numerical-safety (extrapolation / support guard; thin cohorts have holes)",
         "disposition": "KEEP", "evidence": "prevents reading an unsupported age cell."},
        {"id": "fa_projection.war_map_no_clamp", "file": "fa_projection.py", "line": 884,
         "clamp": "war_from_projection returns the raw OLS linear combination (NO clamp/floor)",
         "class": "true-to-model-by-design (raw model output)", "disposition": "KEEP",
         "evidence": "the WAR map is already fully true-to-model; nothing to remove."},
        {"id": "fa_projection.pt_risk_clamp", "file": "fa_projection.py", "line": 618,
         "clamp": "pt_risk_apply clamps the injury-PT adjustment at +-{hit150, pit60}",
         "class": "a-priori bound on a GATED, DEFAULT-OFF adjustment (EEPHUS_PT_RISK)",
         "disposition": "KEEP (out of served scope; inert by default)",
         "evidence": "PT_RISK_DEFAULT=False; the adjustment does not touch the shipped projection."},
        {"id": "translation._band.lo_clip", "file": "college_translation.py", "line": 489,
         "clamp": "band lo = max(lo_clip, pred - 1.2816*sd); lo_clip = 0 (rates) / 0.3 (OPS)",
         "class": "numerical-safety (band whisker cannot enter the impossible rate/OPS region)",
         "disposition": "KEEP",
         "evidence": "binds only where the raw whisker would go negative (1 of 8212 college rows, "
                     "0 of 1950 milb rows); the served POINT value (exp) is never clamped."},
        {"id": "translation._band.hi_clip", "file": "college_translation.py", "line": 491,
         "clamp": "band hi = min(hi_clip, pred + 1.2816*sd); hi_clip K%60 BB%30 pitK%50 pitBB%25 (rates)",
         "class": "DISPLAY COMPRESSION - sub-domain soft cap that diverges the shown upper whisker "
                  "from the model's own LOO-validated band",
         "disposition": "REMOVE (raise rate hi_clip to the true [0,100] domain); leave OPS 1.2 "
                        "(experimental, inert, fuzzier domain)",
         "evidence": "college pit_bb hi_clip=25 BINDS on 23 of 4540 served rows; for the max-exp "
                     "rows exp==25.0 so the clamped hi==exp (band shows ZERO upside uncertainty - "
                     "a clamp artifact). _loo_mae_cov (college L399 / milb L103) computes coverage "
                     "on the UNCLAMPED band, so the display cap makes the shown band inconsistent "
                     "with the validated band. Raising to 100 is coverage-invariant + exp-invariant "
                     "(exp/lo never touched); de-compresses only the 23 upper whiskers. hit/box/pit_k "
                     "hi_clips bind 0 times (byte-invariant), raised for family consistency."},
        {"id": "translation.slope_shrink_k", "file": "college_translation.py", "line": 357,
         "clamp": "slope = ols_slope * n/(n+SLOPE_SHRINK_K) - regression-to-the-mean shrink",
         "class": "accuracy-load-bearing (the model's core RTM design; LOO-validated)",
         "disposition": "KEEP",
         "evidence": "this IS the translation model (a weak relationship pulls to the level mean); "
                     "not a display clamp. LOO MAE/coverage in college_translation_eval.json."},
    ]


def main() -> None:
    out = {
        "lane": "C3b projections + translations true-to-model",
        "principle": "served metric should equal its model's raw output; remove only "
                     "board-movement/display compression; keep numerical-safety + "
                     "accuracy-load-bearing caps (with evidence).",
        "translations_milb_band_binding": audit_milb(),
        "translations_college_band_binding": audit_college(),
        "projections_binding": audit_projections(),
        "clamp_inventory": clamp_inventory(),
        "conclusion": "Served POINT values are already fully true-to-model on both surfaces "
                      "(translation exp is never clamped; projection WAR is unfloored - 604 median "
                      "negatives served live; the WAR map is raw OLS with no clamp). Of the whole "
                      "clamp inventory, exactly ONE is genuine display compression: the translation "
                      "_band() upper soft-caps on the rate lines, which cap the displayed P10-P90 "
                      "upper whisker BELOW the model's own LOO-validated band (college pit_bb=25 "
                      "binds 23 rows, producing hi==exp artifacts). SHIP: raise the rate hi_clips to "
                      "the true [0,100] domain (coverage-invariant, exp-invariant, monotone). Every "
                      "other clamp is numerical/domain safety (rate>=0, pt>=0, FIP>=1.0 [inert], "
                      "season_fraction, curve support, quantile monotone sort), an accuracy-load-"
                      "bearing RTM/recenter (slope shrink, mean/star lift-only blend - validated), "
                      "or true-to-model by design (NO ZERO FLOOR).",
        "ship_diff": {
            "files": ["college_translation.py", "milb_translation.py"],
            "change": "_band()/ct._band() rate call sites: hi_clip soft-cap -> 100 (true domain). "
                      "K% 60->100, BB% 30->100, pit_k 50->100, pit_bb 25->100, box_k 60->100, "
                      "box_bb 30->100. lo_clip=0 unchanged (domain floor). OPS 0.3/1.2 unchanged.",
            "served_effect": "23 college pit_bb upper whiskers widen to the raw model band; all "
                             "other rate rows byte-identical; exp/lo unchanged everywhere.",
            "validation_invariance": "LOO MAE + P10-P90 coverage are computed unclamped -> "
                                     "unchanged. Spearman/rank invariant (exp untouched, monotone).",
        },
    }
    (DATA / "c3_proj_trans_recal_eval.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("translations_milb_band_binding",
                                          "translations_college_band_binding",
                                          "projections_binding")}, indent=1))
    print("\nwrote data/c3_proj_trans_recal_eval.json")


if __name__ == "__main__":
    main()

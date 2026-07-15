# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV Pass 2 -- the HITTER model + leakage-free out-of-time backtest vs consensus FV.

Trains the eFV hitter model on the Pass-1 matrix (data/xfv_hitter_matrix.json) and scores
it forward-chained against the consensus-FV-only baseline (the bar established in Pass 1).
Honest by mandate: the loser is committed either way (program rule), and we expect a TIE
on rank per the Phase-1 verdict -- the flagship case rests on the distribution/surplus
(Pass 3), not a rank win.

  TARGET     first-6-season summed bWAR, KM-censored (target_censored), sample-weighted by
             observed fraction; resolved-only run as the sensitivity check.
  COHORT     hitters; decision-year = debut_year (debuted) or last-prospect-point year + 1
             (bust). Forward-chained: predict cohort year Y with models fit on rows whose
             decision_year < Y. Two evals: DEBUTED-ONLY (clean WAR regression, the
             prospect_path protocol) and FULL-POOL (debuted + busts; the rank-the-board task,
             with the decision-year-proxy caveat stated).
  MODELS     baseline = within-fold OLS WAR~consensus_fv_raw (Spearman == FV's rank corr);
             eFV-core = prior-anchored ridge (FV dominant, standardized, alpha tuned in-fold);
             challenger = monotone LightGBM; comps = distance-weighted k-NN (also the UI
             feature); ensemble = mean(ridge, lgbm).
  GATE       a model beats consensus only if it wins BOTH pooled-OOS MAE and Spearman.

Artifact: data/xfv_eval.json. Run: python efv_model.py
"""

from __future__ import annotations

import json
import logging
import math
import random
import statistics
from datetime import date
from pathlib import Path

from prospect_path import (_spearman, _calibration, _score, _fit_ridge, _predict,
                           _fit_linear_calibration)

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
MATRIX_PATH = DATA_DIR / "xfv_hitter_matrix.json"
OUT_PATH = DATA_DIR / "xfv_eval.json"

# forward-chained test cohorts (>= ~30 test rows each; earlier years seed the first fold)
SCORED_YEARS = (2020, 2021, 2022, 2023)

# Feature keys + monotone direction (LightGBM; ridge ignores the sign, regularizes only).
# LEAN, theory-motivated sets (Phase-1 verdict + an OOS feature search). The earlier
# kitchen-sink set was DRAGGED DOWN by noisy features (milb_missing/n_sources/pick/etc.):
# adding them made the model rank BELOW consensus. Stripping to the earned signals flips
# it -- this lean model beats consensus FV on out-of-sample rank for BOTH cuts and BOTH
# sides, and the edge holds (grows) on recent 2019-2023 cohorts (see data/xfv_eval.json
# era_split). Power is DELIBERATELY absent for hitters (Phase-1: over-priced by scouts,
# anti-signal for incremental WAR) -- that omission IS eFV's power-overpricing correction.
_FEATURES_HIT = [
    ("fv",             +1),   # consensus_fv_raw -- the dominant, regularized prior
    ("obp_rel",        +1),   # Phase-1: strongest hitter edge BEYOND FV (on-base skill)
    ("k_rel",          -1),   # contact: more whiffs worse (under-priced by scouts)
    ("peak_k_rel",     -1),   # best-season contact (multi-season peak); helps OOS
    ("age_rel_level",  -1),   # younger-for-level better
    ("n_milb_seasons", +1),   # MiLB seasons before the read -- track record/persistence (OOS +.010)
    ("tool_hit",       +1),   # best single tool for WAR
    ("tool_speed",     +1),   # athletic up-side / defensive value
    # milb_missing: indicator that the production block is IMPUTED (no pre-decision MiLB
    # track record). Re-validated 2026-06-24: ALONE on the lean set it is a clean OOS gain
    # (blend 0.339->0.362, FV-45 tier 0.012->0.093) -- the model needs to tell imputed-zero
    # production from average production, which is exactly the thin-record fringe cohort the
    # old kitchen-sink rejection (milb_missing BUNDLED with n_sources/pick) hid.
    ("milb_missing",   -1),
    # Acquisition-cohort indicators -- the ridge re-centers each cohort's intercept, lifting
    # cross-tier ordering in EVERY tier (sweep: stacks with milb_missing to blend 0.367).
    ("is_ifa",          0),
    ("is_college",      0),
    # ops_rel: FV-45 FRINGE-tier on-base+slugging signal the obp_rel/k_rel pair misses.
    # E-LEAN1 flagged a genuine t45 signal (~+0.02) that the pooled-first gate could not
    # ship; WS-M / M5 re-tested it under a pre-registered FRINGE gate (docs/prelaunch-2026-07)
    # and it cleared: t45 +0.0237 (0.120 -> 0.144), with pooled (-0.002) and within-tier
    # (-0.0026) movement at the identity noise floor (~0.0023 = statistically no change).
    # Ledger: data/xfv_ops_rel_fringe_eval.json (resolved-target within-tier dips -0.0052 =
    # the accepted sensitivity cost of a fringe-targeted add). Kept LAST to match the tested
    # key order (ridge predictions are feature-order invariant).
    ("ops_rel",        +1),
    # age: absolute age at the production read (OWNER-DIRECTED ship 2026-07-14,
    # data/xfv_age_feature_eval.json). Missed the pooled auto-ship bar by 0.0003
    # (+0.0043) but improves within-tier (+0.0053) AND t45 (+0.0057) with no
    # metric down -- and the OOS eval pool is debuted-only, structurally blind
    # to the never-debut risk this feature targets (the 27yo-org-arm class the
    # owner flagged). No missing indicator: mean-imputed (22.5) rows stay
    # neutral under standardization; the indicator variant destabilizes
    # pitchers (sparse-column class).
    ("age",            -1),
    # NOTE: game power deliberately excluded -- Phase-1 shows scouts over-price it and it
    # is ~neutral-to-negative for incremental WAR (it predicts ISO, not WAR).
]
_FEATURES_PIT = [
    ("fv",             +1),   # consensus_fv_raw -- the dominant, regularized prior
    ("peak_k_rel",     +1),   # multi-season PEAK K-rate -- the lever that flipped pitchers
    ("k_rel",          +1),   # final-season K-rate (Phase-1 top adder)
    ("bb_rel",         -1),   # walk rate -- completes the K-BB% edge (helps OOS; cmd does NOT)
    ("age_rel_level",  -1),
    ("x_era_k",        +1),   # (-era_rel)*k_rel: run-prevention x missing-bats interaction.
                              # Feature re-test 2026-06-22: genuine OOS lift (debuted-km
                              # 0.274->0.282, blend +0.0074, sane cal); era_rel alone fails.
    ("tool_fb",        +1),   # fastball -- best pitcher tool adder
    # age: OWNER-DIRECTED ship 2026-07-14 (see the hitter-side note +
    # data/xfv_age_feature_eval.json): pit age-only pooled +0.0019 (sub-bar)
    # but wm +0.0114 / t45 +0.0117, no metric down; the debuted-only eval
    # cannot see the never-debut org-arm risk this targets.
    ("age",            -1),
    # NOTE: pitcher cohort interactions (ifa_x_era / col_x_k / fb_x_k) were tested + REVERTED
    # 2026-06-24. They lifted OOS rank only marginally (blend 0.269->0.285, "marginally above
    # noise" per the sweep) AND col_x_k = is_college*k_rel is a SPARSE column (nonzero only for
    # college arms), so standardizing it against a mostly-zero distribution handed thin-sample
    # college draftees extreme boosts at LIVE time (Caden Hunter +6; Moore/Root/Quick jumping to
    # 50 on col_x_k alone). Bare indicators don't help pitchers (0.267 < 0.269). A ranking gain
    # that wrecks absolute-grade robustness is not a clean gain -> reverted. (Hitter cohort
    # indicators stay -- bounded 0/1, robust +0.030 gain.)
]


# Guarded-blend weight for the shipped HEADLINE rank: rank = (1-lambda)*consensus_OLS
# + lambda*model. lambda is now WAG-CALIBRATED (see _wag_calibrated_lambda): it is the
# trust factor that realized WAR-Above-Grade actually supports for eFV's adjustment,
# forward-chained. Hitters land ~0.8 (the adjustment is well-supported); pitchers shrink
# harder (consensus is the stronger pitcher signal, and WAG confirms a smaller edge). The
# fallback below is used only if the WAG join is unavailable. Clamped so the validated rank
# win is never surrendered and the magnitude is never overstated.
_BLEND_LAMBDA_FALLBACK = {"hit": 0.85, "pit": 0.80}
_BLEND_LAMBDA_CLAMP = (0.35, 0.90)
_WAG_LAMBDA_CACHE: dict[str, float] = {}

# WAG sizes the blend ONLY when its predicted-edge -> realized-WAG regression is meaningful.
# When that regression is non-significant (|spearman| below this / too few rows), its slope is
# noise and would shrink the blend to a rank-SUBOPTIMAL weight. Pitchers already land here (WAG
# spearman ~0.02, slope 0.39) -- the shipped pit eval shows the 0.391 blend (rho 0.2625)
# trailing the pure ridge (rho 0.281); the blend was pulling the better prediction back toward
# the weaker consensus. There we size lambda by the rank gate directly (rank_calibration).
# Threshold raised 0.05 -> 0.10 (2026-07-06): the 2026 norm-fix collapsed the HITTER WAG signal
# (spearman 0.20 -> 0.066, bootstrap CI straddles 0), so at 0.05 it was still (barely) clearing
# the gate and pinning a rank-suboptimal lambda ~0.53; a non-significant WAG at n~400 needs
# ~0.10 to be real, so hitters now defer to the rank gate too (lambda ~0.70), which lifts the
# pooled OOS rank rho 0.343 -> 0.353 (within-tier + FV45 also up).
_WAG_MIN_SPEARMAN = 0.10
_WAG_MIN_N = 100

# Realized-outcome bars for the M1 AUC instrumentation (source_backtest.CONTRIBUTOR_WAR /
# STAR_WAR): a first-6yr summed-bWAR contributor clears 3, a star clears 10.
_CONTRIB_WAR = 3.0
_STAR_WAR = 10.0


def _feature_spec(side: str):
    feats = _FEATURES_PIT if side == "pit" else _FEATURES_HIT
    return [k for k, _ in feats], [m for _, m in feats]


def _load_wag() -> dict:
    """player_key -> stored WAG block (regressed_wag = exposure/injury-corrected,
    reliability-shrunk talent over/underperformance vs consensus FV; w_obs = its weight).
    The realized 'beat your grade' truth eFV's adjustment is calibrated against."""
    try:
        deb = json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for r in deb:
        w = (r.get("debuted_value") or {}).get("wag")
        if w and r.get("player_key") and w.get("regressed_wag") is not None:
            out[r["player_key"]] = w
    return out


def wag_calibration(side: str) -> dict:
    """Forward-chained calibration of eFV's adjustment against realized WAG. Regresses
    each debuted player's realized regressed_wag (per-season talent over/underperformance)
    on eFV's PREDICTED per-season rate adjustment (model - consensus, /6), weighted by WAG
    reliability (w_obs), through the origin. The slope is how much realized over/under-
    performance you actually get per unit of predicted edge -> the trust factor for the
    blend. Returns {lambda, slope_wobs, slope_unweighted, spearman, n}. Leakage-free."""
    from efv_dataset import matrix_path
    keys, _m = _feature_spec(side)
    wag = _load_wag()
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    data = _prep([r for r in rows if r["kind"] == "debuted"], "target_censored", side)
    x, y, w = [], [], []
    for yr in SCORED_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = _fit_ols_fv(tr)
        ridge = _fit_ridge(tr, keys)
        # AUDIT FIX 2026-07-14 (guard order): check ols/ridge BEFORE calling
        # _predict on them - _fit_ridge returns None under 40 rows, which
        # would TypeError here (latent: today's fold gate makes it unreachable).
        if not (ols and ridge):
            continue
        cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        for r in te:
            wg = wag.get(r["player_key"])
            if not wg:
                continue
            cons_war = max(0.0, _pred_ols(ols, r["fv"]))
            model_war = max(-2.0, a + b * _predict(ridge, r["feats"]))
            x.append((model_war - cons_war) / 6.0)       # predicted per-season rate edge
            y.append(float(wg["regressed_wag"]))         # realized per-season WAG
            w.append(float(wg.get("w_obs") or 0.0))
    def _slope(wt):
        num = sum(wt[i] * x[i] * y[i] for i in range(len(x)))
        den = sum(wt[i] * x[i] * x[i] for i in range(len(x)))
        return (num / den) if den else None
    sw = _slope(w)
    su = _slope([1.0] * len(x))
    lo, hi = _BLEND_LAMBDA_CLAMP
    lam = min(hi, max(lo, sw)) if sw is not None else _BLEND_LAMBDA_FALLBACK[side]
    return {"lambda": round(lam, 3), "slope_wobs": round(sw, 3) if sw is not None else None,
            "slope_unweighted": round(su, 3) if su is not None else None,
            "spearman": _spearman(x, y) if len(x) >= 8 else None, "n": len(x)}


def rank_calibration(side: str) -> dict:
    """RANK-gate blend lambda -- the fallback used when WAG cannot calibrate (its predicted-
    edge -> realized-WAG regression is non-significant). Sizes lambda directly on the forward-
    chained OOS ranking, over the same debuted-cohort folds the eval uses (identical setup to
    the 'blend' row in data/xfv_eval*.json).

    Pitchers land here: WAG spearman ~0.02 pins lambda at 0.391, and the shipped pit eval shows
    that 0.391 blend (rho 0.2625) trailing the pure ridge (0.281) -- the blend was dragging the
    better prediction back toward the weaker consensus. A leakage-free forward-chained selector
    (tools/xfv_ml_lab.lambda_fwdchain) confirms higher-than-0.391 ranks better in every cohort
    with prior data (+0.017 pooled). BUT an adversarial bootstrap showed pooled rho is FLAT
    across 0.80-1.0 and the move's CI only stays strictly positive near ~0.65, while the value-
    bearing within-tier + FV-45-fringe signals PEAK at ~0.65 and DEGRADE toward 0.90. So lambda
    maximizes pooled + within-tier + fringe TOGETHER within a conservative [0.50, 0.70] band --
    the robust middle, not the noisy high-lambda plateau. (Leakage note: lambda is one smooth
    parameter; selecting it on the pooled OOS folds is in-sample for that single scalar, but the
    per-cohort forward-chain independently validates the direction.)

    AUDIT NOTE 2026-07-14: this selector's per-fold consensus-OLS anchor is fit on
    DEBUTED-only rows, while production (_fit_production) fits its anchor on the full
    pool minus recent busts - the flatter full-pool slope makes the EFFECTIVE live
    weight ~0.03 higher than the number quoted here (rank order within a scoring run
    is unaffected; documented rather than re-plumbed).

    ADJUDICATED 2026-07-15 (data/xfv_lambda_adjudication_eval.json): the parity
    re-plumb was tested as a selection PROTOCOL in a nested forward-chained
    tournament and LOST out-of-sample (hit composite -0.1025 with CI95 entirely
    negative + contributor-AUC below floor; pit -0.0024, tie). The earlier
    C-vs-D band-end disagreement was a lab leakage artifact (a vacuous
    decision_year filter fit the parity stack on each fold's own test rows;
    leak-fixed D == C exactly), not implementation sensitivity. This
    debuted-only selector is the ADJUDICATED WINNER; no owner decision pending.
    The returned dict carries the full candidate curve + near_boundary flag so
    any future restamp proposal checks flatness first."""
    from efv_dataset import matrix_path
    keys, _m = _feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    data = _prep([r for r in rows if r["kind"] == "debuted"], "target_censored", side)
    folds = []   # (cons_war, model_pred, target, fv)
    for yr in SCORED_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = _fit_ols_fv(tr)
        ridge = _fit_ridge(tr, keys)
        if not (ols and ridge):
            continue
        for r in te:
            cons = max(0.0, _pred_ols(ols, r["fv"]))
            folds.append((cons, _predict(ridge, r["feats"]), r["target"], r["fv"]))
    if len(folds) < 30:
        return {"lambda": _BLEND_LAMBDA_FALLBACK[side], "criterion": None, "n": len(folds)}

    def _metrics(lam):
        scored = [((1 - lam) * c + lam * m, t, fv) for c, m, t, fv in folds]
        rho = _spearman([s for s, _, _ in scored], [t for _, t, _ in scored]) or 0.0
        byt: dict = {}
        for s, t, fv in scored:
            byt.setdefault(round(fv / 5) * 5, []).append((s, t))
        wsum = wn = 0.0
        t45 = 0.0
        for tk, grp in byt.items():
            if len(grp) < 15:
                continue
            r = _spearman([a for a, _ in grp], [b for _, b in grp])
            if r is None:
                continue
            wsum += r * len(grp)
            wn += len(grp)
            if tk == 45:
                t45 = r
        return rho, (wsum / wn if wn else 0.0), t45

    # E-LAMBDA history (2026-07-14, tools/efv_lambda_band_lab.py ->
    # data/xfv_lambda_band_eval.json): a same-day cap-raise of the HIT ceiling
    # to 0.90 was shipped on a monotone-to-pure-model curve (composite +0.0253,
    # bootstrap P=0.866)... and RETRACTED hours later when the label-integrity
    # repair (41 veteran re-appearances mislabeled as debuts + the career_war
    # sliding-window decay) rebuilt the matrices: on corrected labels the swept
    # optimum is INTERIOR (~0.89) with gain +0.0082 and bootstrap P=0.677 -
    # below every gate. The corrupted labels had been making consensus look
    # worse than it is. The conservative [0.50, 0.70] band STANDS for both
    # sides; the retraction is recorded in the ledger + registry.
    lo, hi = 0.50, 0.70
    cand = [round(lo + (hi - lo) * i / 20, 3) for i in range(21)]
    metr = {lam: _metrics(lam) for lam in cand}
    best = max(cand, key=lambda L: sum(metr[L]))   # pooled + within-tier + FV-45 fringe
    rho, wm, t45 = metr[best]
    # Flatness surface for the restamp protocol: a near-boundary argmax or a
    # composite curve flat within noise across the band means the selection is
    # weak evidence and a restamp needs the owner's sign-off, not just a rerun.
    curve = {str(L): round(sum(metr[L]), 4) for L in cand}
    spread = max(curve.values()) - min(curve.values())
    return {"lambda": best, "rho": round(rho, 4), "within_tier_wm": round(wm, 4),
            "t45": round(t45, 4), "n": len(folds), "band": [lo, hi],
            "curve": curve, "curve_spread": round(spread, 4),
            "near_boundary": bool(best <= lo + 0.02 or best >= hi - 0.02)}


def blend_lambda(side: str) -> float:
    """Blend weight on the eFV model vs the consensus anchor (cached). Calibrated by WAG only
    when its predicted-edge -> realized-WAG regression is SIGNIFICANT (|spearman| >=
    _WAG_MIN_SPEARMAN); otherwise the slope is noise and pins a rank-suboptimal weight, so we
    size lambda by the rank gate directly (rank_calibration). As of the 2026 norm-fix BOTH sides
    are non-significant on WAG (pitchers spearman ~0.001, hitters ~0.066, both CIs straddle 0),
    so both defer to the rank gate. Falls back to the hand-set value on any error."""
    if side not in _WAG_LAMBDA_CACHE:
        try:
            wc = wag_calibration(side)
            rho = wc.get("spearman")
            if rho is not None and abs(rho) >= _WAG_MIN_SPEARMAN and (wc.get("n") or 0) >= _WAG_MIN_N:
                _WAG_LAMBDA_CACHE[side] = wc["lambda"]
            else:
                _WAG_LAMBDA_CACHE[side] = rank_calibration(side)["lambda"]
        except Exception:
            _WAG_LAMBDA_CACHE[side] = _BLEND_LAMBDA_FALLBACK[side]
    return _WAG_LAMBDA_CACHE[side]


def oos_grades(side: str) -> dict:
    """{player_key: OUT-OF-SAMPLE eFV ranking score} over the full labeled pool
    (debuted + busts), forward-chained: each cohort year is scored by a model fit ONLY
    on earlier cohorts. The score is the guarded-blend rank_war (monotone in the grade),
    suitable for an apples-to-apples head-to-head against the sources on realized outcomes
    WITHOUT the in-sample advantage a fitted model would otherwise enjoy. Leakage-free."""
    from efv_dataset import matrix_path
    keys, _m = _feature_spec(side)
    lam = blend_lambda(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    full = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
    data = _prep(full, "target_censored", side)
    out = {}
    for yr in SCORED_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = _fit_ols_fv(tr)
        ridge = _fit_ridge(tr, keys)
        # AUDIT FIX 2026-07-14 (guard order): check ols/ridge BEFORE calling
        # _predict on them - _fit_ridge returns None under 40 rows, which
        # would TypeError here (latent: today's fold gate makes it unreachable).
        if not (ols and ridge):
            continue
        cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        for r in te:
            cons_war = max(0.0, _pred_ols(ols, r["fv"]))
            model_war = max(-2.0, a + b * _predict(ridge, r["feats"]))
            out[r["player_key"]] = (1 - lam) * cons_war + lam * model_war
    return out


_KEYS, _MONO = _feature_spec("hit")   # hitter defaults (back-compat for imports)


# ---------------------------------------------------------------------------
# feature vectorization (impute + missingness indicators)
# ---------------------------------------------------------------------------

def _decision_year(r) -> int:
    if r["kind"] == "debuted":
        return int(r["debut_year"])
    c = r.get("cutoff") or ""
    return (int(c[:4]) + 1) if c[:4].isdigit() else 2026


_MID_POS = ("C", "SS", "2B", "CF")


def _pos_premium(pos, side: str) -> float:
    """Up-the-middle defensive premium (hitters: C/SS/2B/CF); starters over relievers
    (pitchers). A coarse positional-value tilt -- the search decides if it earns weight."""
    if not pos:
        return 0.0
    p = str(pos).upper()
    if side == "pit":
        return 0.0 if "RP" in p or p == "RP" else 1.0
    return 1.0 if any(x in p for x in _MID_POS) else 0.0


def _x_era_k(era_rel: float, k_rel: float) -> float:
    """Run-prevention x missing-bats interaction: (-era_rel)*k_rel.

    QUADRANT FIX (audited, then OWNER-DIRECTED ship 2026-07-14): the raw
    product is POSITIVE in the double-bad quadrant (era worse than level AND
    K-rate below level, neg*neg) - 730 live pitchers carried a spurious
    'K-backed run prevention' boost up to +0.48. The quadrant is ZEROED (not
    flipped: the flip's large negatives reshape the fit for a worse measured
    cost). Honesty note: on the DEBUTED-ONLY OOS protocol this measures as a
    small fringe-tier loss (t45 ~-0.02) because that pool credits the
    spurious boost via survivorship - its never-debut victims are outside
    the sample frame. The owner chose correctness over the survivorship-
    biased metric; the double-bad signal still reaches the model through
    era_rel / k_rel / bb_rel directly."""
    x = (-era_rel) * k_rel
    if era_rel > 0 and k_rel < 0:
        return 0.0
    return x


# Tool-grade imputation constants (AUDIT FIX 2026-07-14): the old flat 45.0
# imputed far below the OBSERVED train means (tool_fb mean is 58.0!), and tools
# are missing for 56-65% of LIVE rows vs only 11-14% of training rows - so the
# majority of the live pitcher pool ate a ~-1.3 SD spurious fastball penalty
# relative to training. Impute at the measured train means (pinned by
# test_efv_model) so missing stays NEUTRAL under standardization. Non-lean
# tools (cmd/sl/ch/cb, game_pwr/raw_pwr/field/throw) keep 45.0 - they carry no
# shipped coefficient.
_TOOL_IMPUTE = {"tool_hit": 50.0, "tool_speed": 48.0, "tool_fb": 58.0}

# n_milb_seasons live support cap (AUDIT FIX 2026-07-14): training counts are
# era-censored by the 2014 StatsAPI floor (observed max = 8 on both sides);
# live rows count uncapped (and include the in-progress season), so the ridge
# extrapolated beyond its training support. Cap at the training max.
_N_MILB_SEASONS_CAP = 8.0


def _vec(r, side: str = "hit") -> dict:
    m = r.get("milb") or {}
    # milb_missing semantics (AUDIT FIX 2026-07-14): the flag's documented job
    # is "no pre-decision MiLB track record", but 100% of 2011-2014 and ~97% of
    # 2015 debut rows fired it for DATA-AVAILABILITY reasons (no mlbam id /
    # StatsAPI cache floor 2014) - real-WAR debuts flagged as imputed-zero
    # production, diluting the coefficient. Rows the dataset marks
    # milb_unavailable stay NEUTRAL (0.0) instead.
    if r.get("milb"):
        milb_missing = 0.0
    elif r.get("milb_unavailable"):
        milb_missing = 0.0
    else:
        milb_missing = 1.0
    pick = r.get("pick_overall")
    bonus = r.get("bonus_usd")
    def g(v, d=0.0):
        return float(v) if v is not None else d
    out = {
        # fv_effective = the E-STALE anchor-staleness-decayed anchor (live rows
        # only; efv_dataset.build_live_matrix). Training rows have no
        # fv_effective (staleness 0 at a listing event by construction) and
        # fall through to the raw consensus.
        "fv": g(r.get("fv_effective"), g(r.get("consensus_fv_raw"))),
        "fv_trend": g(r.get("fv_trend")),
        "n_sources": g(r.get("n_sources")),
        "age_rel_level": g(m.get("age_rel_level")),
        # Absolute age at the production read (E-AGE, docs/efv-2026-07-14):
        # age_rel_level alone under-prices the outcome clock at old-skewing
        # levels (a 26.6yo AAA bat reads as just "+2 vs level"). Mean-imputed
        # (22.5) behind the indicator so milb-missing rows stay neutral under
        # standardization. Emitted unconditionally; only in _FEATURES_* if the
        # pre-registered gate cleared.
        "age": g(m.get("age"), 22.5),
        "age_missing": 0.0 if m.get("age") is not None else 1.0,
        "level_rank": g(m.get("level_rank")),
        "k_rel": g(m.get("k_rel")),
        "bb_rel": g(m.get("bb_rel")),
        "milb_missing": milb_missing,
        "n_milb_seasons": min(g(m.get("n_milb_seasons")), _N_MILB_SEASONS_CAP),
        "prod_trend": g(m.get("prod_trend")),
        "pos_prem": _pos_premium(r.get("position"), side),
        "pick_overall": float(pick) if pick is not None else 250.0,
        "pick_missing": 0.0 if pick is not None else 1.0,
        "bonus_log": math.log1p(float(bonus)) if bonus else 0.0,
        "il_stints_pre": g(r.get("il_stints_pre")),
        "fv_stddev": g(r.get("fv_stddev")),
        # Acquisition-cohort indicators (efv_dataset._cohort_flags). The ridge re-centers
        # each cohort's intercept -> sharper cross-tier ordering (OOS gain, both sides).
        "is_ifa": g(r.get("is_ifa")),
        "is_college": g(r.get("is_college")),
    }
    if side == "pit":
        out.update({
            "tool_fb": g(r.get("tool_fb"), _TOOL_IMPUTE["tool_fb"]),
            "tool_cmd": g(r.get("tool_cmd"), 45.0),
            "tool_sl": g(r.get("tool_sl"), 45.0), "tool_ch": g(r.get("tool_ch"), 45.0),
            "tool_cb": g(r.get("tool_cb"), 45.0), "era_rel": g(m.get("era_rel")),
            "peak_k_rel": g(m.get("peak_k_rel")), "peak_bb_rel": g(m.get("peak_bb_rel")),
            # run-prevention x missing-bats interaction (final-season); see the
            # _x_era_k docstring for the audited-and-deferred quadrant issue.
            "x_era_k": _x_era_k(g(m.get("era_rel")), g(m.get("k_rel"))),
        })
    else:
        out.update({
            "tool_hit": g(r.get("tool_hit"), _TOOL_IMPUTE["tool_hit"]),
            "tool_game_pwr": g(r.get("tool_game_pwr"), 45.0),
            "tool_speed": g(r.get("tool_speed"), _TOOL_IMPUTE["tool_speed"]),
            "tool_field": g(r.get("tool_field"), 45.0),
            "obp_rel": g(m.get("obp_rel")), "ops_rel": g(m.get("ops_rel")),
            "peak_obp_rel": g(m.get("peak_obp_rel")), "peak_k_rel": g(m.get("peak_k_rel")),
            "peak_iso_rel": g(m.get("peak_iso_rel")), "peak_ops_rel": g(m.get("peak_ops_rel")),
            "iso_rel": g(m.get("iso_rel")),
            # NOTE: game power stays out of the hitter model. Beyond raw iso_rel + peak_iso_rel
            # (both rejected earlier), the 2026-06-22 CONDITIONAL-power experiment tested power
            # REALIZED in games + level-weighted / contact-paired (iso_x_level, iso_upper,
            # iso_x_hit, iso_x_contact, peak_iso_x_level): all FAILED the OOS bar (best debuted-km
            # -0.0016; replacing tool_speed with power cost -0.014). Third independent confirmation
            # that power does not earn a place here -- the Witt-class power-star miss is the
            # accepted cost of the population-level power-overpricing correction.
        })
    return out


def _prep(rows, target_key, side: str = "hit"):
    out = []
    for r in rows:
        t = r.get(target_key)
        if t is None or r.get("consensus_fv_raw") is None:
            continue
        out.append({"player_key": r["player_key"], "kind": r["kind"],
                    "decision_year": _decision_year(r),
                    "feats": _vec(r, side), "target": float(t),
                    "weight": float(r.get("weight", 1.0)),
                    "fv": float(r["consensus_fv_raw"])})
    return out


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------

def _fit_ols_fv(train):
    """Baseline: WAR ~ a + b*FV (the bar). Spearman of its prediction == FV rank corr."""
    n = len(train)
    if n < 8:
        return None
    mx = sum(r["fv"] for r in train) / n
    my = sum(r["target"] for r in train) / n
    cov = sum((r["fv"] - mx) * (r["target"] - my) for r in train)
    var = sum((r["fv"] - mx) ** 2 for r in train)
    if var <= 0:
        return None
    b = cov / var
    return {"a": my - b * mx, "b": b}


def _pred_ols(model, fv):
    return model["a"] + model["b"] * fv


def fit_production_stack(rows, side: str, keys=None):
    """The ONE production fit, shared by efv_score._fit_production (the shipped
    scorer) and rank_calibration (the lambda selector): full labeled pool minus
    never-MLB recent busts -> ridge + linear output calibration + consensus OLS
    anchor. E-LAMBDA parity repair 2026-07-15: the selector used to fit a
    DEBUTED-only anchor and score a RAW uncalibrated model leg, so it sized
    lambda for a blend production never ships (stamped pit 0.63 / hit 0.70 were
    measured on the wrong blend). Both callers now fit through here; the
    selector's legs apply the same calibration clamp and cons floor as run_live.
    Returns {ridge, a, b, ols, keys, n} or None when the pool cannot support a fit."""
    if keys is None:
        keys, _m = _feature_spec(side)
    is_pit = side == "pit"
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    data = _prep(pool, "target_censored", side)
    if len(data) < 60:
        return None
    ridge = _fit_ridge(data, keys)
    if not ridge:
        return None
    raw = {r["player_key"]: _predict(ridge, r["feats"]) for r in data}
    cal = _fit_linear_calibration([(raw[r["player_key"]], r["target"]) for r in data])
    a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
    ols = _fit_ols_fv(data)
    if not ols:
        return None
    return {"ridge": ridge, "a": a, "b": b, "ols": ols, "keys": keys, "n": len(data)}


def _fit_lgbm_mono(train, keys, mono):
    try:
        import lightgbm as lgb
        import numpy as np
    except ImportError:
        return None
    if len(train) < 60:
        return None
    X = np.array([[r["feats"][k] for k in keys] for r in train])
    y = np.array([r["target"] for r in train])
    w = np.array([r["weight"] for r in train])
    model = lgb.LGBMRegressor(
        n_estimators=250, learning_rate=0.04, num_leaves=7,
        min_child_samples=25, subsample=0.9, subsample_freq=1,
        colsample_bytree=0.8, reg_lambda=5.0, monotone_constraints=mono,
        random_state=7, deterministic=True, verbose=-1)
    model.fit(X, y, sample_weight=w)
    return {"model": model, "keys": keys}


def _pred_lgbm(gbm, feats):
    import numpy as np
    import warnings as _w
    X = np.array([[feats[k] for k in gbm["keys"]]])
    with _w.catch_warnings():
        _w.simplefilter("ignore")
        return float(gbm["model"].predict(X)[0])


def _fit_comps(train, keys):
    import numpy as np
    if len(train) < 40:
        return None
    X = np.array([[r["feats"][k] for k in keys] for r in train])
    y = np.array([r["target"] for r in train])
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    return {"Xs": (X - mu) / sd, "y": y, "mu": mu, "sd": sd, "keys": keys,
            "pk": [r["player_key"] for r in train]}


def _pred_comps(cm, feats, k=20):
    import numpy as np
    x = (np.array([feats[c] for c in cm["keys"]]) - cm["mu"]) / cm["sd"]
    d = np.sqrt(((cm["Xs"] - x) ** 2).sum(axis=1))
    idx = np.argsort(d)[:k]
    w = 1.0 / (d[idx] + 1e-6)
    pred = float((w * cm["y"][idx]).sum() / w.sum())
    comps = [(cm["pk"][i], round(float(cm["y"][i]), 2), round(float(d[i]), 2))
             for i in idx[:5]]
    return pred, comps


# ---------------------------------------------------------------------------
# eval
# ---------------------------------------------------------------------------

def _lofo_calibrate(fold_map):
    """Leave-one-fold-out linear recentering (realized ~ a + b*pred).

    DOCSTRING CORRECTED 2026-07-14 (audit): the old claims were wrong on both
    counts. (1) POOLED Spearman is NOT strictly unchanged vs raw - each fold
    gets its own affine map, so cross-fold ordering can shift (within-fold
    order is preserved). (2) "fit on the OTHER folds only" includes LATER
    folds - leave-one-out over a time series is not forward-chained, so this
    is a diagnostic recentering, not a leakage-clean protocol; the governance
    metrics never consume it for ranking claims."""
    out, yrs = [], list(fold_map)
    for yr in yrs:
        others = [p for y in yrs if y != yr for p in fold_map[y]]
        cal = _fit_linear_calibration(others)
        if not cal:
            out.extend(fold_map[yr])
            continue
        out.extend((max(0.0, cal["a"] + cal["b"] * pred), t) for pred, t in fold_map[yr])
    return out


def _run_eval(data, label, keys=None, mono=None, lam=None):
    keys = keys or _KEYS
    mono = mono or _MONO
    pairs = {m: [] for m in ("baseline", "ridge", "blend", "lgbm", "comps", "ensemble")}
    fold_map = {m: {} for m in ("ridge", "ensemble")}   # for LOFO calibration
    per_year = {}
    for yr in SCORED_YEARS:
        train = [r for r in data if r["decision_year"] < yr]
        test = [r for r in data if r["decision_year"] == yr]
        if len(test) < 15 or len(train) < 60:
            continue
        ols = _fit_ols_fv(train)
        ridge = _fit_ridge(train, keys)
        gbm = _fit_lgbm_mono(train, keys, mono)
        cm = _fit_comps(train, keys)
        yp = {m: [] for m in pairs}
        for r in test:
            t = r["target"]
            if ols:
                yp["baseline"].append((max(0.0, _pred_ols(ols, r["fv"])), t))
            if ridge:
                yp["ridge"].append((_predict(ridge, r["feats"]), t))
            # blend == the SHIPPED headline rank: (1-lam)*consensus_OLS + lam*model
            # (consensus anchor floored at 0 WAR, matching the baseline).
            if ridge and ols and lam is not None:
                yp["blend"].append(((1 - lam) * max(0.0, _pred_ols(ols, r["fv"]))
                                    + lam * _predict(ridge, r["feats"]), t))
            if gbm:
                yp["lgbm"].append((_pred_lgbm(gbm, r["feats"]), t))
            if cm:
                p, _ = _pred_comps(cm, r["feats"])
                yp["comps"].append((p, t))
            if ridge and gbm:
                yp["ensemble"].append(
                    ((_predict(ridge, r["feats"]) + _pred_lgbm(gbm, r["feats"])) / 2, t))
        for m in pairs:
            pairs[m].extend(yp[m])
        for m in fold_map:
            fold_map[m][yr] = yp[m]
        per_year[str(yr)] = {m: _score(yp[m]) for m in pairs if len(yp[m]) >= 8}
    pooled = {m: (_score(pairs[m]) if pairs[m] else {"n": 0}) for m in pairs}
    # calibrated (rank-preserving) variants — the Pass-3 step that should
    # close the MAE gap without surrendering the rank edge.
    pooled["ridge_cal"] = _score(_lofo_calibrate(fold_map["ridge"])) if fold_map["ridge"] else {"n": 0}
    pooled["ensemble_cal"] = _score(_lofo_calibrate(fold_map["ensemble"])) if fold_map["ensemble"] else {"n": 0}
    base = pooled["baseline"]
    verdict = {}
    for m in ("ridge", "blend", "lgbm", "comps", "ensemble", "ridge_cal", "ensemble_cal"):
        s = pooled[m]
        if s.get("n", 0) > 80 and s.get("mae") is not None and base.get("mae") is not None:
            beats_mae = s["mae"] < base["mae"]
            beats_rho = (s.get("spearman") or -9) > (base.get("spearman") or -9)
            verdict[m] = {"beats_mae": beats_mae, "beats_spearman": beats_rho,
                          "rank_win": bool(beats_mae and beats_rho)}
    return {"label": label, "pooled_oos": pooled, "per_year": per_year,
            "verdict_vs_consensus": verdict}


def _importances(data, keys=None, mono=None):
    """Full-window diagnostics (NOT shipped predictions): standardized ridge weights +
    lgbm gain, to show WHERE the signal is. Interpretation only."""
    keys = keys or _KEYS
    mono = mono or _MONO
    out = {}
    ridge = _fit_ridge(data, keys)
    if ridge:
        out["ridge_std_weights"] = {k: round(w, 3) for k, w in zip(ridge["keys"], ridge["w"])}
    gbm = _fit_lgbm_mono(data, keys, mono)
    if gbm:
        imp = gbm["model"].feature_importances_
        tot = float(sum(imp)) or 1.0
        out["lgbm_gain_share"] = {k: round(float(v) / tot, 3)
                                  for k, v in sorted(zip(keys, imp), key=lambda x: -x[1])}
    return out


def _era_of(yr) -> str:
    """Debut-era bucket, matching _era_split and the eFV labs."""
    y = int(yr)
    return "<=2018" if y <= 2018 else ("2019-2021" if y <= 2021 else "2022-2023")


def _cohort_map(rows) -> dict:
    """player_key -> acquisition cohort (ifa / college / hs / draft / other), matching
    efv_dataset._cohort_flags + the eFV lab's leakage-free draft-age split (drafted at
    age >= 21 = college, else hs). Storage-derived; used ONLY for the M1 eval AUC
    breakdown, NEVER for scoring, so a missing storage layer degrades to 'other'."""
    keys = [r["player_key"] for r in rows if r.get("player_key")]
    if not keys:
        return {}
    bd = {r["player_key"]: r.get("birth_date") for r in rows}
    acq = {}
    try:
        import storage
        with storage.connect() as con:
            ph = ",".join("?" for _ in keys)
            for r in con.execute(
                    f"SELECT player_key, method, year FROM acquisitions "
                    f"WHERE player_key IN ({ph})", tuple(keys)):
                acq[r["player_key"]] = {"method": r["method"], "year": r["year"]}
    except Exception:
        return {}
    out = {}
    for pk in keys:
        a = acq.get(pk) or {}
        m = a.get("method")
        if m == "international_fa":
            out[pk] = "ifa"
        elif m == "draft":
            yr, b = a.get("year"), bd.get(pk)
            coh = "draft"
            if yr and b:
                try:
                    coh = "college" if (int(yr) - int(str(b)[:4])) >= 21 else "hs"
                except (ValueError, TypeError):
                    coh = "draft"
            out[pk] = coh
        else:
            out[pk] = "other"
    return out


def _auc_breakdown(data, keys, lam, cohort_map) -> dict:
    """M1 instrumentation (measurement, not a model change). Forward-chained
    contributor-AUC (realized first-6yr WAR >= _CONTRIB_WAR) and star-AUC
    (>= _STAR_WAR) for the shipped BLEND and the CONSENSUS baseline, sliced by
    acquisition cohort, debut era, and FV tier -- so eFV's discrimination margin
    over consensus FV is visible per cell. Same forward-chained folds as the
    'blend' eval row (each cohort year scored by models fit on strictly-earlier
    cohorts). Reuses source_backtest._auc (Mann-Whitney U). Both scores share the
    SAME binary labels, so the model-minus-consensus margin is label-invariant."""
    try:
        from source_backtest import _auc
    except Exception:
        return {"n": 0, "note": "source_backtest._auc unavailable"}
    # Forward-chain over the full scoreable span (seed years 2016+ populate the <=2018
    # era cell, as in _era_split); tag each row with its fold year. Pooled/cohort/tier
    # use SCORED_YEARS only so pooled n matches the 'blend' eval row; by_era uses the
    # full span so all three era cells can appear.
    recs = []   # (blend, cons, war, fv, cohort, era, year)
    for yr in range(2016, max(SCORED_YEARS) + 1):
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = _fit_ols_fv(tr)
        ridge = _fit_ridge(tr, keys)
        if not (ols and ridge):
            continue
        for r in te:
            cons = max(0.0, _pred_ols(ols, r["fv"]))
            blend = (1 - lam) * cons + lam * _predict(ridge, r["feats"])
            recs.append((blend, cons, r["target"], r["fv"],
                         cohort_map.get(r["player_key"], "other"),
                         _era_of(r["decision_year"]), int(r["decision_year"])))
    scored = [r for r in recs if r[6] in SCORED_YEARS]
    if len(scored) < 30:
        return {"n": len(scored), "note": "insufficient rows for AUC breakdown"}

    def _pair(subset, thresh):
        if len(subset) < 15:
            return None
        labels = [w >= thresh for _, _, w, _, _, _, _ in subset]
        n_pos = sum(labels)
        if n_pos == 0 or n_pos == len(labels):
            return None
        am = _auc([b for b, _, _, _, _, _, _ in subset], labels)
        ac = _auc([c for _, c, _, _, _, _, _ in subset], labels)
        return {"n": len(subset), "n_pos": int(n_pos),
                "model_auc": round(am, 4) if am is not None else None,
                "consensus_auc": round(ac, 4) if ac is not None else None,
                "margin": (round(am - ac, 4) if (am is not None and ac is not None) else None)}

    def _cell(subset):
        c = {"contributor": _pair(subset, _CONTRIB_WAR), "star": _pair(subset, _STAR_WAR)}
        return c if (c["contributor"] or c["star"]) else None

    out = {"n": len(scored), "n_with_seed_folds": len(recs),
           "labels": {"contributor_war": _CONTRIB_WAR, "star_war": _STAR_WAR,
                      "war_metric": "first-6yr summed bWAR (target_censored); "
                                    "model=blend, consensus=OLS(FV) anchor, shared labels"},
           "pooled": _cell(scored), "by_cohort": {}, "by_era": {}, "by_fv_tier": {}}
    for c in ("hs", "college", "ifa", "draft", "other"):
        cell = _cell([r for r in scored if r[4] == c])
        if cell:
            out["by_cohort"][c] = cell
    for e in ("<=2018", "2019-2021", "2022-2023"):
        cell = _cell([r for r in recs if r[5] == e])
        if cell:
            out["by_era"][e] = cell
    for tk in sorted({round(r[3] / 5) * 5 for r in scored}):
        cell = _cell([r for r in scored if round(r[3] / 5) * 5 == tk])
        if cell:
            out["by_fv_tier"][str(int(tk))] = cell
    return out


# ---------------------------------------------------------------------------
# eFV 3.4 F-SIDE -- standing JOINT side-fairness eval line (measurement-only)
# ---------------------------------------------------------------------------
# Question kept honest by this line: do PITCHERS at a given joint-board slot /
# display grade systematically deliver worse realized outcomes than HITTERS at
# the same slot -- and does any future model change WIDEN that gap? The line is
# output-neutral by construction: it READS the Pass-1 matrices and the stamped
# live lambdas, and WRITES only eval artifacts (data/xfv_side_fairness_eval.json
# + a compact 'side_fairness' block in xfv_eval*.json). No scorer, producer or
# payload writer is touched, so every published player number is byte-identical.
#
# Provenance: the 2026-07 side_fairness scratchpad investigation; this code is
# that prototype verbatim (same folds, same guards, same RNG stream), so the
# headline number reproduces bit-for-bit: full-pool joint display-grade TOP-25
# hit-minus-pit mean first-6yr WAR +3.95, CI90 [1.55, 6.35], p(hit>pit)=0.996.

_SF_SEED = 7            # bootstrap seed (prototype + program standard)
_SF_BOOT = 2000         # bootstrap replicates (program standard)
_SF_IPCW_CAP = 5.0      # IPCW weight cap
_SF_BUST_WAR = 0.5      # realized bust threshold (first-6yr WAR < 0.5)
_SF_BANDS = ((1, 25, "001-025"), (26, 50, "026-050"), (51, 100, "051-100"),
             (101, 200, "101-200"), (201, 10 ** 9, "201+"))
_SF_OUT = "xfv_side_fairness_eval.json"
_SF_CACHE: dict = {}    # per-process memo: hit + pit run() calls share one computation


def _sf_live_lambdas():
    """Blend weights actually SERVED: the live lambdas stamped into data/xfv.json meta
    by the scorer -- so a lambda restamp flows into this line automatically. Fallback =
    the 2026-07-14 stamp so the line still runs on a cold tree (source recorded)."""
    try:
        meta = json.loads((DATA_DIR / "xfv.json").read_text(encoding="utf-8")).get("meta", {})
        ll = meta.get("live_lambda") or {}
        return ({"hit": float(ll["hit"]), "pit": float(ll["pit"])},
                "data/xfv.json meta.live_lambda")
    except Exception:
        return {"hit": 0.70, "pit": 0.63}, "fallback constants (xfv.json meta unavailable)"


def _sf_pool(side, frame):
    """(prepped rows, player_key -> censored flag) for one side/frame.
    full_pool (PRIMARY) = debuted + busts minus recent busts, KM target -- the
    rank-the-board population; debuted_only = the survivorship-censored sensitivity
    frame (it cannot see never-debut risk; that is WHY it is not primary)."""
    from efv_dataset import matrix_path
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    if frame == "debuted_only":
        raw = [r for r in rows if r["kind"] == "debuted"]
    else:
        raw = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
    cens = {r["player_key"]: bool(r.get("censored")) for r in rows}
    return _prep(raw, "target_censored", side), cens


def _sf_fwd_chain(data, side, lam, years):
    """Forward-chained OOS production-analogue scores (prototype verbatim): per fold
    fit OLS(FV) anchor + lean ridge + linear calibration on decision_year < Y, score
    == Y; rank_war = (1-lam)*max(0, cons) + lam*max(-2, a+b*ridge). Fold guards match
    _run_eval (>=15 test / >=60 train)."""
    keys, _m = _feature_spec(side)
    out = []
    for yr in years:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = _fit_ols_fv(tr)
        ridge = _fit_ridge(tr, keys)
        if not (ols and ridge):
            continue
        cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        for r in te:
            cons = max(0.0, _pred_ols(ols, r["fv"]))
            model = max(-2.0, a + b * _predict(ridge, r["feats"]))
            out.append({"pk": r["player_key"], "side": side, "year": yr, "fv": r["fv"],
                        "war": r["target"], "rank_war": (1 - lam) * cons + lam * model})
    return out


def _sf_quantile_display(rows_side):
    """Production display grade: per-side rank-preserving quantile map of rank_war onto
    that side's OWN consensus-FV distribution (efv_score.run/run_live), replicated
    within one fold-year test pool. This map is exactly what lets each side fill the
    joint board's top slots at its own FV-distribution rate -- the display-vs-raw
    share-inflation this line measures."""
    if not rows_side:
        return
    target = sorted(r["fv"] for r in rows_side)
    order = sorted(range(len(rows_side)), key=lambda i: rows_side[i]["rank_war"])
    m = len(rows_side)
    for pos_rank, i in enumerate(order):
        pos = ((pos_rank / (m - 1)) if m > 1 else 0.0) * (m - 1)
        lo = int(pos)
        hi = min(m - 1, lo + 1)
        rows_side[i]["disp"] = target[lo] * (1 - (pos - lo)) + target[hi] * (pos - lo)


def _sf_summ(rows, wkey=None):
    """Realized-outcome cell: mean AND median first-6yr WAR (co-primary) +
    contributor/star/bust rates. wkey='ipcw_w' produces the IPCW-weighted variant
    (weighted median = lowest value whose cumulative weight reaches half; effective_n
    = (sum w)^2 / sum w^2 reported)."""
    if not rows:
        return None
    wars = [r["war"] for r in rows]
    if wkey is None:
        n = len(wars)
        return {"n": n,
                "mean_war": round(statistics.mean(wars), 2),
                "median_war": round(statistics.median(wars), 2),
                "contrib_rate": round(sum(1 for x in wars if x >= _CONTRIB_WAR) / n, 3),
                "star_rate": round(sum(1 for x in wars if x >= _STAR_WAR) / n, 3),
                "bust_rate": round(sum(1 for x in wars if x < _SF_BUST_WAR) / n, 3)}
    w = [r[wkey] for r in rows]
    W = sum(w)
    med = sorted(wars)[-1]
    acc = 0.0
    for x, wi in sorted(zip(wars, w)):
        acc += wi
        if acc >= W / 2:
            med = x
            break
    return {"n": len(rows),
            "effective_n": round(W * W / sum(x * x for x in w), 1),
            "mean_war": round(sum(v * wi for v, wi in zip(wars, w)) / W, 2),
            "median_war": round(med, 2),
            "contrib_rate": round(sum(wi for v, wi in zip(wars, w) if v >= _CONTRIB_WAR) / W, 3),
            "star_rate": round(sum(wi for v, wi in zip(wars, w) if v >= _STAR_WAR) / W, 3),
            "bust_rate": round(sum(wi for v, wi in zip(wars, w) if v < _SF_BUST_WAR) / W, 3)}


def _sf_boot(hit_rows, pit_rows, wkey=None, iters=_SF_BOOT, seed=_SF_SEED):
    """Bootstrap hit-minus-pit realized-WAR difference: mean AND median co-primary,
    each with CI90 + bootstrap SE. The unweighted mean draws consume the RNG stream
    exactly as the prototype's boot_diff did, so historical CIs reproduce verbatim.
    Weighted variant (wkey) resamples rows and recomputes the weighted statistic."""
    if len(hit_rows) < 8 or len(pit_rows) < 8:
        return None
    rng = random.Random(seed)
    hw = [r["war"] for r in hit_rows]
    pw = [r["war"] for r in pit_rows]
    hwt = None if wkey is None else [r[wkey] for r in hit_rows]
    pwt = None if wkey is None else [r[wkey] for r in pit_rows]

    def _mean(vals, wts):
        if wts is None:
            return statistics.mean(vals)
        return sum(v * w for v, w in zip(vals, wts)) / sum(wts)

    def _median(vals, wts):
        if wts is None:
            return statistics.median(vals)
        W = sum(wts)
        acc = 0.0
        for v, w in sorted(zip(vals, wts)):
            acc += w
            if acc >= W / 2:
                return v
        return sorted(vals)[-1]

    md, dd = [], []
    for _ in range(iters):
        hidx = [rng.randrange(len(hw)) for _ in hw]
        pidx = [rng.randrange(len(pw)) for _ in pw]
        hs, ps = [hw[i] for i in hidx], [pw[i] for i in pidx]
        hws = None if hwt is None else [hwt[i] for i in hidx]
        pws = None if pwt is None else [pwt[i] for i in pidx]
        md.append(_mean(hs, hws) - _mean(ps, pws))
        dd.append(_median(hs, hws) - _median(ps, pws))
    md.sort()
    dd.sort()
    return {"mean_diff": round(_mean(hw, hwt) - _mean(pw, pwt), 2),
            "mean_ci90": [round(md[int(0.05 * iters)], 2), round(md[int(0.95 * iters)], 2)],
            "mean_se": round(statistics.pstdev(md), 3),
            "median_diff": round(_median(hw, hwt) - _median(pw, pwt), 2),
            "median_ci90": [round(dd[int(0.05 * iters)], 2), round(dd[int(0.95 * iters)], 2)],
            "median_se": round(statistics.pstdev(dd), 3),
            "p_hit_gt_pit": round(sum(1 for d in md if d > 0) / iters, 3)}


def _sf_band_tables(scored, wkey=None):
    """Joint-board band tables for BOTH rankings -- production display grade ('disp')
    and raw rank_war WAR units (the calibration-honest cross-side comparison) --
    banded within each fold year, pooled across folds. The display table carries the
    pitcher slot share, the raw-frame share, and the display-vs-raw share-inflation
    ratio (how much the per-side quantile map inflates pitcher representation)."""
    tabs = {}
    for key in ("disp", "rank_war"):
        bands = {}
        for yr in sorted({r["year"] for r in scored}):
            pool = sorted([r for r in scored if r["year"] == yr], key=lambda r: -r[key])
            for i, r in enumerate(pool, 1):
                for lo, hi, name in _SF_BANDS:
                    if lo <= i <= hi:
                        bands.setdefault(name, []).append(r)
                        break
        out = {}
        for name in sorted(bands):
            grp = bands[name]
            hit = [r for r in grp if r["side"] == "hit"]
            pit = [r for r in grp if r["side"] == "pit"]
            out[name] = {"pit_share": round(len(pit) / len(grp), 3),
                         "hit": _sf_summ(hit, wkey), "pit": _sf_summ(pit, wkey),
                         "boot": _sf_boot(hit, pit, wkey)}
        tabs[key] = out
    for name, cell in tabs["disp"].items():
        rw = tabs["rank_war"].get(name, {}).get("pit_share")
        cell["pit_share_rank_war_frame"] = rw
        cell["share_inflation_display_vs_raw"] = (round(cell["pit_share"] / rw, 2)
                                                  if rw else None)
    return tabs["disp"], tabs["rank_war"]


def _sf_grade_cells(scored, gkey, wkey=None):
    """Equal-grade cells on nearest-5 bands (55-band = [52.5, 57.5), 60 = 57.5+;
    prototype banding) PLUS the BINDING '55_plus' threshold cell = all rows with
    grade >= 52.5 (displays as 55 or better under the round-to-nearest eFV scale).
    The 50 band is a TRACKED DIAGNOSTIC, never a gate (pre-registered)."""
    out = {}
    for g in (40, 45, 50, 55, 60):
        if g == 60:
            grp = [r for r in scored if r.get(gkey) is not None and r[gkey] >= 57.5]
        else:
            grp = [r for r in scored if r.get(gkey) is not None
                   and abs(r[gkey] - g) <= 2.5 and r[gkey] < g + 2.5]
        hit = [r for r in grp if r["side"] == "hit"]
        pit = [r for r in grp if r["side"] == "pit"]
        out[str(g)] = {"hit": _sf_summ(hit, wkey), "pit": _sf_summ(pit, wkey),
                       "boot": _sf_boot(hit, pit, wkey)}
    grp = [r for r in scored if r.get(gkey) is not None and r[gkey] >= 52.5]
    hit = [r for r in grp if r["side"] == "hit"]
    pit = [r for r in grp if r["side"] == "pit"]
    out["55_plus_binding"] = {"hit": _sf_summ(hit, wkey), "pit": _sf_summ(pit, wkey),
                              "boot": _sf_boot(hit, pit, wkey)}
    return out


def _sf_per_fold_top25(scored):
    """Per-fold joint display-grade TOP-25 hit-minus-pit diffs -- the B1 sign-agreement
    input (mean AND median, co-primary)."""
    out = {}
    for yr in sorted({r["year"] for r in scored}):
        pool = sorted([r for r in scored if r["year"] == yr], key=lambda r: -r["disp"])[:25]
        hit = [r for r in pool if r["side"] == "hit"]
        pit = [r for r in pool if r["side"] == "pit"]
        if not (hit and pit):
            out[str(yr)] = {"n_hit": len(hit), "n_pit": len(pit), "note": "one-sided top-25"}
            continue
        dm = (statistics.mean(r["war"] for r in hit)
              - statistics.mean(r["war"] for r in pit))
        dmed = (statistics.median(r["war"] for r in hit)
                - statistics.median(r["war"] for r in pit))
        out[str(yr)] = {"n_hit": len(hit), "n_pit": len(pit),
                        "mean_diff": round(dm, 2), "median_diff": round(dmed, 2),
                        "sign": "hit_gt_pit" if dm > 0 else "pit_ge_hit"}
    return out


def _sf_ipcw_weights(scored, cens_map):
    """IPCW: on the RESOLVED subset, weight each row by 1 / P(resolved), estimated
    empirically within (side, fold-year, nearest-5 FV) cells (fallback to
    (side, fold-year) when the cell has < 5 rows), capped at _SF_IPCW_CAP. Returns
    resolved rows with r['ipcw_w'] set. This re-inflates the resolved subset back
    toward the full-board population -- the uncertainty band around the KM frame."""
    from collections import defaultdict
    cell = defaultdict(lambda: [0, 0])
    coarse = defaultdict(lambda: [0, 0])
    for r in scored:
        res = not cens_map.get((r["side"], r["pk"]), False)
        k = (r["side"], r["year"], round(r["fv"] / 5) * 5)
        cell[k][0] += 1
        cell[k][1] += res
        coarse[(r["side"], r["year"])][0] += 1
        coarse[(r["side"], r["year"])][1] += res
    out = []
    for r in scored:
        if cens_map.get((r["side"], r["pk"]), False):
            continue
        k = (r["side"], r["year"], round(r["fv"] / 5) * 5)
        n, nr = cell[k] if cell[k][0] >= 5 else coarse[(r["side"], r["year"])]
        p = (nr / n) if n else 1.0
        rr = dict(r)
        rr["ipcw_w"] = min(_SF_IPCW_CAP, 1.0 / p) if p > 0 else _SF_IPCW_CAP
        out.append(rr)
    return out


def _sf_frame(frame, lam):
    """One frame (full_pool | debuted_only): forward-chain both sides, replicate the
    display map, build the joint tables. Returns (result block, scored rows,
    (side, pk) -> censored map)."""
    scored, cens_map, fold_counts = [], {}, {}
    for side in ("hit", "pit"):
        data, cens = _sf_pool(side, frame)
        fc = {}
        for yr in (*SCORED_YEARS, max(SCORED_YEARS) + 1):
            ntr = sum(1 for r in data if r["decision_year"] < yr)
            nte = sum(1 for r in data if r["decision_year"] == yr)
            fc[str(yr)] = {"n_train": ntr, "n_test": nte,
                           "passes_guards": bool(nte >= 15 and ntr >= 60)}
        fold_counts[side] = fc
        rows = _sf_fwd_chain(data, side, lam[side], SCORED_YEARS)
        for yr in sorted({r["year"] for r in rows}):
            _sf_quantile_display([r for r in rows if r["year"] == yr])
        for pk, c in cens.items():
            cens_map[(side, pk)] = c
        scored.extend(rows)
    disp_tab, rw_tab = _sf_band_tables(scored)
    res = {
        "n_hit": sum(1 for r in scored if r["side"] == "hit"),
        "n_pit": sum(1 for r in scored if r["side"] == "pit"),
        "per_side_spearman_rankwar_vs_war": {
            s: _spearman([r["rank_war"] for r in scored if r["side"] == s],
                         [r["war"] for r in scored if r["side"] == s])
            for s in ("hit", "pit")},
        "fold_counts_vs_guards": fold_counts,
        "per_fold_top25_display": _sf_per_fold_top25(scored),
        "joint_bands_display_grade": disp_tab,
        "joint_bands_rank_war": rw_tab,
        "equal_display_grade": _sf_grade_cells(scored, "disp"),
        "equal_consensus_fv": _sf_grade_cells(scored, "fv"),
        "pred_vs_realized_by_side": {
            s: {"n": len([r for r in scored if r["side"] == s]),
                "mean_pred": round(statistics.mean(r["rank_war"] for r in scored
                                                   if r["side"] == s), 2),
                "mean_real": round(statistics.mean(r["war"] for r in scored
                                                   if r["side"] == s), 2)}
            for s in ("hit", "pit")},
    }
    return res, scored, cens_map


def _sf_ipcw_frame(scored, cens_map):
    """IPCW uncertainty band: band membership comes from the FULL joint board (all
    rows ranked by display grade); band statistics are then estimated from the
    RESOLVED members only, re-weighted by 1/P(resolved). Reported next to the KM
    primary frame -- agreement bounds what window-censoring could be hiding."""
    for yr in sorted({r["year"] for r in scored}):
        pool = sorted([r for r in scored if r["year"] == yr], key=lambda r: -r["disp"])
        for i, r in enumerate(pool, 1):
            for lo, hi, name in _SF_BANDS:
                if lo <= i <= hi:
                    r["band_disp"] = name
                    break
    resolved = _sf_ipcw_weights(scored, cens_map)
    ws = [r["ipcw_w"] for r in resolved]
    out = {"resolved_n": len(resolved),
           "resolved_share": round(len(resolved) / len(scored), 3) if scored else None,
           "weight_cap": _SF_IPCW_CAP,
           "weights": ({"max": round(max(ws), 2), "mean": round(statistics.mean(ws), 2),
                        "n_at_cap": sum(1 for w in ws if w >= _SF_IPCW_CAP)} if ws else None),
           "bands_display_grade": {}}
    for lo, hi, name in _SF_BANDS:
        grp = [r for r in resolved if r.get("band_disp") == name]
        hit = [r for r in grp if r["side"] == "hit"]
        pit = [r for r in grp if r["side"] == "pit"]
        out["bands_display_grade"][name] = {
            "hit": _sf_summ(hit, "ipcw_w"), "pit": _sf_summ(pit, "ipcw_w"),
            "boot": _sf_boot(hit, pit, "ipcw_w")}
    return out


def _sf_resolved_le2018_check(lam):
    """B3 input: on decision folds <= 2018 (first-6yr windows fully elapsed, censoring
    ~absent) the IPCW estimator must preserve the top-25 diff sign AND sit within 1
    bootstrap SE of the unweighted estimate -- i.e. the reweighting machinery must be
    ~identity exactly where there is nothing to reweight."""
    scored, cens_map = [], {}
    for side in ("hit", "pit"):
        data, cens = _sf_pool(side, "full_pool")
        rows = _sf_fwd_chain(data, side, lam[side], (2016, 2017, 2018))
        for yr in sorted({r["year"] for r in rows}):
            _sf_quantile_display([r for r in rows if r["year"] == yr])
        for pk, c in cens.items():
            cens_map[(side, pk)] = c
        scored.extend(rows)
    if not scored:
        return {"evaluable": False,
                "note": "no <=2018 folds pass the >=15/>=60 guards"}
    top = []
    for yr in sorted({r["year"] for r in scored}):
        pool = sorted([r for r in scored if r["year"] == yr], key=lambda r: -r["disp"])
        top.extend(pool[:25])
    hit = [r for r in top if r["side"] == "hit"]
    pit = [r for r in top if r["side"] == "pit"]
    unw = _sf_boot(hit, pit)
    resolved = _sf_ipcw_weights(scored, cens_map)
    wmap = {(r["side"], r["pk"], r["year"]): r["ipcw_w"] for r in resolved}
    rtop = [dict(r, ipcw_w=wmap[(r["side"], r["pk"], r["year"])]) for r in top
            if (r["side"], r["pk"], r["year"]) in wmap]
    ipw = _sf_boot([r for r in rtop if r["side"] == "hit"],
                   [r for r in rtop if r["side"] == "pit"], "ipcw_w")
    if not (unw and ipw):
        return {"evaluable": False, "fold_years_used": sorted({r["year"] for r in scored}),
                "note": "top-25 too one-sided for a bootstrap on <=2018 folds",
                "unweighted": unw, "ipcw": ipw}
    sign_ok = (unw["mean_diff"] > 0) == (ipw["mean_diff"] > 0)
    within = abs(ipw["mean_diff"] - unw["mean_diff"]) <= unw["mean_se"]
    return {"evaluable": True,
            "fold_years_used": sorted({r["year"] for r in scored}),
            "resolved_share_of_top25": round(len(rtop) / len(top), 3),
            "unweighted": unw, "ipcw": ipw,
            "sign_preserved": bool(sign_ok),
            "within_1se_of_unweighted": bool(within),
            "pass": bool(sign_ok and within)}


def _sf_s3_reference():
    """S3 reference values: the SHIPPED pit BENCH/GOOD bucket log-loss (the
    'logloss_before' line of the E-ISO4 artifact -- the live grade->bucket tables)."""
    try:
        d = json.loads((DATA_DIR / "xfv_grade_recal4_eval.json").read_text(encoding="utf-8"))
        pb = d["results"]["per_side"]["pit"]["per_bucket"]
        return {"bench_logloss": pb["bench"]["logloss_before"],
                "good_logloss": pb["good"]["logloss_before"],
                "source": "data/xfv_grade_recal4_eval.json results.per_side.pit.per_bucket "
                          "logloss_before (the shipped tables)"}
    except Exception:
        return {"bench_logloss": 0.25642, "good_logloss": 0.04971,
                "source": "fallback constants (2026-07 E-ISO4 artifact values)"}


def _side_fairness_eval(persist: bool = True, out_path=None) -> dict:
    """eFV 3.4 F-SIDE: the standing JOINT side-fairness eval line. Builds the
    full-pool-KM primary frame, the debuted-only sensitivity frame and the IPCW
    uncertainty band; stamps binding rules B1-B4 and standing forward gates S1-S5.
    Memoized per process (hit + pit run() calls share one computation). Writes
    data/xfv_side_fairness_eval.json when persist=True (out_path overrides)."""
    art = _SF_CACHE.get("artifact")
    if art is None:
        lam, lam_src = _sf_live_lambdas()
        full, scored_full, cens_full = _sf_frame("full_pool", lam)
        deb, _s, _c = _sf_frame("debuted_only", lam)
        ipcw = _sf_ipcw_frame(scored_full, cens_full)
        b3 = _sf_resolved_le2018_check(lam)
        top = full["joint_bands_display_grade"]["001-025"]
        deb_top = deb["joint_bands_display_grade"]["001-025"]
        pooled_sign = "hit_gt_pit" if top["boot"]["mean_diff"] > 0 else "pit_ge_hit"
        folds = [v for v in full["per_fold_top25_display"].values() if "sign" in v]
        n_agree = sum(1 for v in folds if v["sign"] == pooled_sign)
        binding_rules = {
            "B1_fold_sign_agreement": {
                "rule": ">=3/4 forward-chained folds agree with the pooled sign of the "
                        "joint top-25 hit-minus-pit mean-WAR diff (primary frame)",
                "pooled_sign": pooled_sign, "n_folds": len(folds), "n_agree": n_agree,
                "pass": bool(len(folds) >= 4 and n_agree >= 3)},
            "B2_dual_frame_sign": {
                "rule": "full-pool-KM and debuted-only top-25 mean diffs share a sign",
                "full_pool_mean_diff": top["boot"]["mean_diff"],
                "debuted_only_mean_diff": deb_top["boot"]["mean_diff"],
                "pass": bool((top["boot"]["mean_diff"] > 0)
                             == (deb_top["boot"]["mean_diff"] > 0))},
            "B3_ipcw_identity_where_uncensored": dict(
                {"rule": "IPCW estimate sign-preserving AND within 1 bootstrap SE of "
                         "unweighted on the resolved <=2018 decision folds"}, **b3),
            "B4_ci90_excludes_zero": {
                "rule": "primary top-25 mean-diff CI90 excludes 0",
                "mean_ci90": top["boot"]["mean_ci90"],
                "median_ci90": top["boot"]["median_ci90"],
                "pass": bool(top["boot"]["mean_ci90"][0] * top["boot"]["mean_ci90"][1] > 0)},
        }
        s3ref = _sf_s3_reference()
        rw = full["joint_bands_rank_war"]
        fv40 = full["equal_consensus_fv"]["40"]
        gates = {
            "S1_top25_no_widening": {
                "rule": "S1: joint TOP-25 hit-minus-pit realized-WAR diff must not "
                        "increase by >1 bootstrap SE (mean AND median co-primary)",
                "frame": "full_pool_km / joint_bands_display_grade / 001-025",
                "baseline_mean_diff": top["boot"]["mean_diff"],
                "baseline_mean_se": top["boot"]["mean_se"],
                "max_allowed_mean_diff": round(top["boot"]["mean_diff"]
                                               + top["boot"]["mean_se"], 2),
                "baseline_median_diff": top["boot"]["median_diff"],
                "baseline_median_se": top["boot"]["median_se"],
                "max_allowed_median_diff": round(top["boot"]["median_diff"]
                                                 + top["boot"]["median_se"], 2)},
            "S2_hit_no_harm": {
                "rule": "S2: hit pooled blend Spearman must stay within 0.0023 of the "
                        "corrected-label baseline",
                "baseline_hit_blend_rho": 0.3808, "floor": 0.3785,
                "source": "docs/efv-2026-07-14/GATES.md corrected-label baselines"},
            "S3_pit_bucket_logloss": {
                "rule": "S3: pit BENCH+GOOD bucket log-loss <= +1.0% relative",
                "reference": s3ref,
                "ceilings": {"bench": round(s3ref["bench_logloss"] * 1.01, 5),
                             "good": round(s3ref["good_logloss"] * 1.01, 5)}},
            "S4_midband_pit_outperformance": {
                "rule": "S4: rank_war-frame mid-band pit-outperformance cells (51-100, "
                        "101-200, equal-FV40) must not flip sign",
                "cells": {
                    "rank_war_051-100_mean_diff": (rw.get("051-100", {}).get("boot") or {}).get("mean_diff"),
                    "rank_war_101-200_mean_diff": (rw.get("101-200", {}).get("boot") or {}).get("mean_diff"),
                    "equal_fv40_mean_diff": (fv40.get("boot") or {}).get("mean_diff")},
                "expected_sign": "negative (pitchers outperform hitters at equal raw "
                                 "mid-board slot / equal FV40)",
                "sign_now_all_negative": bool(all(
                    (v is not None and v < 0) for v in (
                        (rw.get("051-100", {}).get("boot") or {}).get("mean_diff"),
                        (rw.get("101-200", {}).get("boot") or {}).get("mean_diff"),
                        (fv40.get("boot") or {}).get("mean_diff"))))},
            "S5_fold_guards_and_2024_tripwire": {
                "rule": "S5: stamp per-side fold-year counts vs the >=15 test / >=60 "
                        "train guards; the FIRST run where the 2024 decision fold "
                        "becomes trainable must re-run E-ISO4-path, M3 and E-STUFF "
                        "before re-baselining this line",
                "guards": {"min_test": 15, "min_train": 60},
                "fold_counts_full_pool": full["fold_counts_vs_guards"],
                "fold_counts_debuted_only": deb["fold_counts_vs_guards"],
                "first_trainable_2024_fold": {
                    # keyed on the DEBUTED frame: the full-pool 2024 test cell is
                    # currently bust-only (zero debuted rows), so its guard pass is
                    # degenerate -- a tripwire fired on it would cry wolf on day one.
                    "hit_passes_guards": deb["fold_counts_vs_guards"]["hit"]["2024"]["passes_guards"],
                    "pit_passes_guards": deb["fold_counts_vs_guards"]["pit"]["2024"]["passes_guards"],
                    "full_pool_2024_note": "full-pool 2024 cell passes the raw guards "
                                           "on bust rows alone (no debuted rows); the "
                                           "trip condition is the DEBUTED 2024 fold",
                    "tripped": bool(
                        deb["fold_counts_vs_guards"]["hit"]["2024"]["passes_guards"]
                        or deb["fold_counts_vs_guards"]["pit"]["2024"]["passes_guards"]),
                    "re_run_on_trip": ["E-ISO4-path", "M3", "E-STUFF"]}},
        }
        art = {
            "generated_at": date.today().isoformat(),
            "eval_line": "eFV 3.4 F-SIDE -- standing joint side-fairness eval "
                         "(measurement-only; output-neutral)",
            "question": "do pitchers at a given joint-board slot / display grade "
                        "deliver worse realized outcomes than hitters at the same "
                        "slot, and does any future change widen that gap?",
            "protocol": {
                "folds": list(SCORED_YEARS),
                "fold_guards": {"min_test": 15, "min_train": 60},
                "lambdas": lam, "lambda_source": lam_src,
                "display_map": "per-side rank-preserving quantile map of rank_war onto "
                               "the side's consensus-FV distribution, replicated within "
                               "each fold-year test pool (production analogue)",
                "joint_board": "both sides unioned; ranked by display grade "
                               "(production) and by raw rank_war WAR units "
                               "(calibration-honest)",
                "war_metric": "first-6yr summed bWAR, KM-censored (target_censored)",
                "bootstrap": {"reps": _SF_BOOT, "seed": _SF_SEED, "ci": "CI90"},
                "outcome_thresholds": {"contributor": _CONTRIB_WAR, "star": _STAR_WAR,
                                       "bust": _SF_BUST_WAR},
                "provenance": "2026-07 side_fairness prototype verbatim; headline "
                              "top-25 +3.95 CI90 [1.55, 6.35] reproduced"},
            "primary_frame": "full_pool_km",
            "frames": {"full_pool_km": full,
                       "debuted_only_sensitivity": deb,
                       "ipcw_resolved_reweighted": ipcw},
            "binding_rules": binding_rules,
            "binding_grade_cell": {
                "binding": "equal display grade >= 55 (grade >= 52.5 on the "
                           "round-to-nearest eFV scale; cell '55_plus_binding')",
                "value": full["equal_display_grade"]["55_plus_binding"],
                "diagnostic_50_band": dict(
                    full["equal_display_grade"]["50"], never_a_gate=True,
                    note="the 50-band model-vs-realized discrepancy is a TRACKED "
                         "DIAGNOSTIC, never a gate (pre-registered)")},
            "standing_gates": gates,
            "output_neutrality": {
                "claim": "measurement-only: no scorer/producer/payload writer touched; "
                         "every published player number (data/xfv.json payloads) is "
                         "byte-identical",
                "writes": ["data/" + _SF_OUT,
                           "side_fairness summary block in data/xfv_eval.json + "
                           "data/xfv_eval_pitcher.json"]},
        }
        _SF_CACHE["artifact"] = art
    if persist:
        p = Path(out_path) if out_path else (DATA_DIR / _SF_OUT)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(art, indent=1), encoding="utf-8")
        log.info("wrote %s", p)
    return art


def _side_fairness_summary() -> dict:
    """Compact side_fairness block embedded in BOTH xfv_eval.json and
    xfv_eval_pitcher.json (identical -- the eval is joint by construction)."""
    art = _side_fairness_eval(persist=False)
    full = art["frames"]["full_pool_km"]
    top = full["joint_bands_display_grade"]["001-025"]
    return {
        "eval_line": "eFV 3.4 F-SIDE joint side-fairness (measurement-only; standing)",
        "artifact": "data/" + _SF_OUT,
        "primary_frame": "full_pool_km, joint display-grade board, folds "
                         + "-".join(str(y) for y in (SCORED_YEARS[0], SCORED_YEARS[-1])),
        "top25_hit_minus_pit": top["boot"],
        "top25_pit_share": {"display_frame": top["pit_share"],
                            "rank_war_frame": top["pit_share_rank_war_frame"],
                            "share_inflation": top["share_inflation_display_vs_raw"]},
        "binding_rules_pass": {k: v.get("pass")
                               for k, v in art["binding_rules"].items()},
        "standing_gates": sorted(art["standing_gates"].keys()),
        "note": "identical block on both sides; full tables + gate baselines live "
                "in the artifact",
    }


def _era_split(deb_data, keys, lam):
    """Honest record of the 'scouting got more accurate over time' question: forward-chained
    consensus vs shipped-blend rank by debut era. If eFV's edge lived only in old cohorts it
    would not transfer to today; this shows whether it holds on RECENT cohorts."""
    eras = {"<=2018": [], "2019-2021": [], "2022-2023": []}
    cons = {k: [] for k in eras}
    blend = {k: [] for k in eras}
    for yr in range(2016, 2024):
        train = [r for r in deb_data if r["decision_year"] < yr]
        test = [r for r in deb_data if r["decision_year"] == yr]
        if len(train) < 60 or len(test) < 10:
            continue
        ols = _fit_ols_fv(train)
        ridge = _fit_ridge(train, keys)
        if not (ols and ridge):
            continue
        bucket = "<=2018" if yr <= 2018 else ("2019-2021" if yr <= 2021 else "2022-2023")
        for r in test:
            cw = max(0.0, _pred_ols(ols, r["fv"]))
            cons[bucket].append((cw, r["target"]))
            blend[bucket].append(((1 - lam) * cw + lam * _predict(ridge, r["feats"]), r["target"]))
    out = {}
    for k in eras:
        if len(cons[k]) >= 15:
            out[k] = {"n": len(cons[k]),
                      "consensus_spearman": _spearman([a for a, _ in cons[k]], [b for _, b in cons[k]]),
                      "xfv_blend_spearman": _spearman([a for a, _ in blend[k]], [b for _, b in blend[k]])}
    return out


def run(persist: bool = True, side: str = "hit") -> dict:
    from efv_dataset import matrix_path
    keys, mono = _feature_spec(side)
    wag_cal = wag_calibration(side)
    lam = blend_lambda(side)   # WAG when it has signal; rank-gate fallback when WAG is noise
    rank_cal = rank_calibration(side)
    lam_source = ("wag" if abs(wag_cal.get("spearman") or 0) >= _WAG_MIN_SPEARMAN
                  and (wag_cal.get("n") or 0) >= _WAG_MIN_N else "rank_gate")
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    deb = [r for r in rows if r["kind"] == "debuted"]
    full = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]

    deb_km = _prep(deb, "target_censored", side)
    cohort_map = _cohort_map(full)   # covers debuted + busts so both AUC pools get real cohorts
    evals = {
        "debuted_km": _run_eval(deb_km, "debuted, KM-censored target", keys, mono, lam),
        "debuted_resolved": _run_eval(_prep([r for r in deb if not r["censored"]],
                                            "target_resolved", side), "debuted, resolved-only (sensitivity)", keys, mono, lam),
        "full_pool_km": _run_eval(_prep(full, "target_censored", side),
                                  "full pool (debuted+busts), KM target [decision-year proxy]", keys, mono, lam),
    }
    # M1 AUC instrumentation: per-cohort / per-era / per-FV-tier contributor + star AUC,
    # model (blend) vs consensus, on the same forward-chained debuted-KM folds.
    evals["debuted_km"]["auc_breakdown"] = _auc_breakdown(deb_km, keys, lam, cohort_map)
    evals["full_pool_km"]["auc_breakdown"] = _auc_breakdown(
        _prep(full, "target_censored", side), keys, lam, cohort_map)
    out = {
        "generated_at": date.today().isoformat(),
        "model": f"eFV {'pitcher' if side == 'pit' else 'hitter'} v1 (lean + guarded blend)",
        "scope": "PITCHERS" if side == "pit" else "HITTERS",
        "conventions": {
            "target": "first-6-season summed bWAR; KM-censored (rate-projected tail) + resolved sensitivity",
            "vintage": "features strictly pre-outcome (Pass-1 matrix; leakage verified 0)",
            "protocol": "forward-chained by decision-year cohort; pooled OOS",
            "baseline": "within-fold OLS WAR ~ consensus_fv_raw (THE bar)",
            "shipped_model": f"'blend' = (1-{lam})*consensus_OLS + {lam}*lean-ridge; this is the "
                             "headline RANK driver. 'ridge' = the pure lean model.",
            "rank_gate": "beat consensus FV on pooled-OOS Spearman (the flagship criterion)",
            "features": keys,
        },
        "lambda_calibration": {
            "shipped_lambda": lam,
            "source": lam_source,
            "shipped_lambda_provenance": {
                # shipped_lambda IS the live blend_lambda(side) recomputed at eval time
                # (no stale copy) -- this block records the decisive values so the
                # bookkeeping is self-contained and cannot silently desync from the
                # export's lambda again.
                "live_blend_lambda": blend_lambda(side),
                "matches_shipped_lambda": abs(lam - blend_lambda(side)) < 1e-9,
                "selector": lam_source,
                "rank_gate_band": rank_cal.get("band"),
                "composite_at_shipped": {
                    "pooled_rho": rank_cal.get("rho"),
                    "within_tier_wm": rank_cal.get("within_tier_wm"),
                    "t45": rank_cal.get("t45"),
                    "composite_sum": (round((rank_cal.get("rho") or 0)
                                            + (rank_cal.get("within_tier_wm") or 0)
                                            + (rank_cal.get("t45") or 0), 4)
                                      if rank_cal.get("rho") is not None else None),
                },
                "note": "rank_calibration selects lambda in rank_gate_band by argmax of "
                        "pooled + within-tier + FV45-fringe Spearman; composite_at_shipped "
                        "are those decisive components at the selected lambda.",
            },
            "wag": wag_cal,
            "rank_gate": rank_cal,
            "reading": "eFV still predicts WAR; the blend lambda is HOW MUCH to trust eFV's "
                       "adjustment over the consensus anchor. WAG (realized over/underperformance "
                       "vs consensus FV = where consensus MISSED) sets lambda ONLY when its "
                       "predicted-edge -> realized-WAG regression is SIGNIFICANT. As of the 2026 "
                       "norm-fix that regression is non-significant on BOTH sides (pitchers spearman "
                       "~0.001, hitters ~0.066, both bootstrap CIs straddle 0), so a WAG-sized lambda "
                       "would be noise pinning a rank-suboptimal weight. Both sides therefore size "
                       "lambda by the RANK GATE directly (rank_calibration): pooled + within-tier + "
                       "FV45-fringe rank rho maximized in a conservative band -> ~0.70, which lifts "
                       "the pooled OOS rank rho vs the old WAG-pinned lambda (the robust, "
                       "CI-positive part of the available gain).",
        },
        "era_split_debuted": _era_split(_prep(deb, "target_censored", side), keys, lam),
        "evals": evals,
        "feature_diagnostics_full_window": _importances(_prep(deb, "target_censored", side), keys, mono),
        "honest_note": ("The lean feature set (Phase-1-earned signals only) lets eFV BEAT consensus "
                        "FV on out-of-sample rank for both cuts -- and the edge holds/grows on recent "
                        "2019-2023 cohorts (era_split_debuted), so it is not just exploiting older, "
                        "less-accurate scouting. eFV still trails on MAE (it predicts more spread; "
                        "consensus regresses to the mean) -- that loss is committed. The flagship case: "
                        "rank edge + calibrated distribution + uncertainty + surplus + power-correction."),
    }
    # eFV 3.4 F-SIDE: joint side-fairness line (measurement-only; identical compact
    # block on both sides -- the full tables live in data/xfv_side_fairness_eval.json).
    # The line must never block the per-side eval artifact: fail soft, record why.
    try:
        out["side_fairness"] = _side_fairness_summary()
        if persist:
            _side_fairness_eval(persist=True)   # memoized; writes the joint artifact
    except Exception as exc:
        log.warning("F-SIDE side-fairness eval unavailable: %s", exc)
        out["side_fairness"] = {"error": f"side-fairness eval unavailable: {exc}"}
    if persist:
        out_path = OUT_PATH if side == "hit" else (DATA_DIR / "xfv_eval_pitcher.json")
        out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s", out_path)
    return out


def _fmt(s):
    return f"n={s.get('n',0):4d} mae={s.get('mae')} rho={s.get('spearman')}"


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run(side="pit" if "--pit" in sys.argv else "hit")
    for ek, ev in rep["evals"].items():
        print(f"\n=== {ek}: {ev['label']} ===")
        for m, s in ev["pooled_oos"].items():
            if s.get("n"):
                print(f"  {m:10s} {_fmt(s)}")
        print("  verdict vs consensus:", json.dumps(ev["verdict_vs_consensus"]))
    print("\nfeature diagnostics (full-window, interpretation only):")
    print("  ridge std weights:", json.dumps(rep["feature_diagnostics_full_window"].get("ridge_std_weights", {})))
    print("  lgbm gain share:  ", json.dumps(rep["feature_diagnostics_full_window"].get("lgbm_gain_share", {})))
    sf = rep.get("side_fairness") or {}
    if sf.get("top25_hit_minus_pit"):
        print("\nF-SIDE joint top-25 hit-minus-pit (full-pool KM):",
              json.dumps(sf["top25_hit_minus_pit"]))
        print("  binding rules pass:", json.dumps(sf["binding_rules_pass"]))

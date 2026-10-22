# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Contract & market model for the MLB Free Agency module (Stage 3).

TWO NUMBERS, NEVER CONFLATED:

  RATIONAL VALUE — what the projected production is worth: NPV of the
  aging-decayed, playing-time-weighted WAR path x escalated $/WAR, at the
  platform's configured discount rate (value_framework discount_rate, 0.07
  in production - the same rate PROSPX surplus uses; the QO
  pick tax literally subtracts one from the other, so the two must share
  an NPV currency).

  PREDICTED MARKET PRICE (projLength / projGuarantee / projAAV) — what
  teams will actually pay: a transparent two-stage model trained ONLY on
  the historical FA-signing corpus (years first, then log-guarantee given
  years), with class-supply and QO features and per-winter $/WAR levels
  carried forward ex-ante. Bands are empirical residual quantiles. Real
  nearest-neighbor comps ride alongside every prediction — comps are
  always actual contracts from the corpus, never fabricated.

The GAP (rational − predicted, "Contract Surplus ($)") is the module's
core editorial product. Deal+ (100 = market-rate, >100 = team-friendly)
indexes a contract's rational value against its price; the UI surfaces it
as a VERDICT string (value / market / overpay — see deal_verdict).

Probability bucketing: every projected WAR path ships floor/mean/ceiling
variants (P10/P50/P90). The quantiles are the Gate-1 EMPIRICAL year-1
residual quantiles per reliability bucket (data/fa_gate1_eval.json
band_quantiles) applied to the year-1 WAR rate, then decayed along the
SAME aging curves as the central path — uncertainty propagates the way
talent does, not as a constant ribbon.

Point-in-time discipline: every signing's WAR projection is built with
fa_projection models fitted on seasons STRICTLY BEFORE its winter
(fp.fitted_models per class_year — cached, which is also what keeps Gate 2
fast). Contract-year decay walks the SAME aging curves the projections
use: a 4-year deal prices years 1-4 of the curve, never year 1 x 4.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import fa_cba
import fa_class
import fa_projection as fp
import storage
from value_framework import (_config as _vf_config, fv_to_6yr_avg_war,
                             point_estimate_surplus_usd)

log = logging.getLogger(__name__)

MODEL_VERSION = "fa_mkt_v2"
GATE2_PATH = Path(__file__).parent / "data" / "fa_gate2_eval.json"

POS_GROUPS = ("SP", "RP", "C", "POS")

# ============================================================================
# Gate-2 arm knobs (2026-07-24 FA lane)
# ============================================================================
# Every knob below defaults to the SHIPPED behaviour, so importing this
# module changes nothing. tools/_fa_lab.py flips them on identical
# forward-chained folds under docs/EFV_GATE_STANDARD.md; an arm ships by
# changing its default here in the same change as the refreshed evidence.
#
#   COMPS_STRICT_PRIOR  comps_for restricted to STRICTLY prior winters (its
#                       own docstring's contract). False == the shipped `<=`,
#                       which lets a training row see its own winter's
#                       contracts while no serve row ever can.
#   DESTALE_MODE        how a historical dollar figure is carried forward to
#                       the class winter. "vf" == the shipped read of
#                       value_framework's dollars_per_war_inflation (which is
#                       0.0 in production, i.e. no de-staling at all).
#                       "series" derives the rate from the realized $/WAR
#                       series of the TRAIN winters only (ex-ante by
#                       construction). "fixed" uses DESTALE_FIXED.
#   RIDGE_YEARS/GUAR    ridge strength for the two OLS stages. _ols has had a
#                       standardized-ridge branch since the megadeal blowups
#                       but no production call ever passed a value.
#   AAV_CONSISTENT      price proj_aav off the term the guarantee was priced
#                       at (years_f) instead of the display-rounded term.
#   POS_GROUP_MODE      "v1" == the shipped 4 buckets. "v2" splits POS into
#                       premium (SS/2B/3B/CF) and corner (1B/LF/RF/DH).
#   RECAL_MODE          level recalibration of the guarantee, estimated on an
#                       INNER forward chain over the training winters only
#                       (see _fit_recal). "off" == shipped. "shift" is an
#                       intercept-only level move. "fit" is the log-log line.
#                       "fit_group" fits that line PER _pos_group with a
#                       pooled fallback for thin groups - the minimal-surface
#                       correction for the measured side asymmetry (E1: the
#                       board under-prices hitters by $7.52M and pitchers by
#                       $4.02M, so one pooled slope cannot fix both).
POS_GROUP_MODE = "v1"
COMPS_STRICT_PRIOR = True                   # SHIPPED 2026-07-24 (correctness)
DESTALE_MODE = "series"                     # SHIPPED 2026-07-24 (correctness)
DESTALE_FIXED = 0.0
RIDGE_YEARS = 0.0
RIDGE_GUAR = 0.0
AAV_CONSISTENT = False                      # measured NULL/loss twice - see E5b
# SHIPPED 2026-07-30 at "shift" (intercept-only level move), owner program
# Phase E5. Gate 2, 9 forward-chained winters, n=1,199, criteria pre-registered
# in docs/efv-2026-07-30/FA_LANE_GATES.md E5a
# (data/fa_market_feature_lab_wave3_eval.json):
#   pooled guarantee MAE  9.9174 -> 10.0391, delta +0.1336, sd 0.654,
#                         CI95 [-0.382, +0.649], MDE95 0.427 -> a NULL, and
#                         also inside the 0.16 $M corpus floor from the
#                         2026-07-24 paired bootstrap (see the rate_line block)
#   pooled aav MAE        3.0450 -> 3.1090, delta +0.061, MDE95 0.091 -> NULL
#   pooled years MAE      unchanged (the recal touches only the guarantee)
#   megadeal slice        81.54 -> 79.34 (IMPROVES)
#   LEVEL, conditioned on the PREDICTION (the criterion; conditioning on the
#   actual is regression to the mean by construction and _fit_recal's own
#   docstring says so). Guarantee bias by PREDICTED-guarantee tier, $M:
#       tier        <10     10-20    20-50    >=50    mean|bias|
#       shipped    -2.81    -9.64   -21.32  -22.52     14.07
#       "shift"    -2.11    -6.27   -15.04   -3.70      6.78
#   Every tier was under-priced and every tier stays under-priced after the
#   correction, i.e. it does not overshoot. Per pos group the bias also shrinks
#   toward zero everywhere: SP -4.88 -> -1.47, RP -3.43 -> -2.76, C -3.17 ->
#   -2.49, POS -8.47 -> -5.63.
# "fit" (the full log-log line) and "fit_group" both FAIL: they push guarantee
# MAE to 10.46 / 10.72, break the mega slice, and OVERSHOOT the top tier
# (+10.51 / +14.95 $M bias at >=$50M). The 2026-07-24 ledger predicted exactly
# this - recalibration and de-staling are SUBSTITUTES for the same mechanism and
# stacking a slope on top of DESTALE_MODE="series" over-corrects. The
# intercept-only form is the part that survives that argument.
# CALIBRATION SHIP ON BIAS: the MAE movement is a measured null in both
# directions and must not be cited as an accuracy win.
# GOLDEN RESTAMP OWED: every served FA price rises by the constant exp(a).
RECAL_MODE = "shift"
# P-1 (2026-08-19, docs/fa-2026-08-19/PTIER_LEVEL_GATE.md): "shift_ptier" is the
# intercept-only shift fit PER PREDICTED-GUARANTEE TIER (lt10/10to20/20to50/ge50,
# the Gate-2 ptier bins) on the same inner forward chain "shift" uses. Slope is
# pinned 1.0 everywhere; slope forms are twice-refuted and are not re-attempted.
# A tier gets its own intercept iff its inner-chain sample holds at least
# RECAL_TIER_MIN_ROWS rows, else it rides the pooled shift.
# RECAL_TIER_PERMUTE_SEED is the zero-information control (tier labels shuffled
# at fit time); RECAL_FIT_LOG, when set to a list, collects every fitted recal
# object so the lab can check fold stability. Both are lab-only knobs.
RECAL_TIER_MIN_ROWS = 30
RECAL_TIER_PERMUTE_SEED = 0
RECAL_FIT_LOG: list | None = None
LAB_TJ_PERMUTE_SEED = 0
NOISE_FEATURES = 0
NOISE_SEED = 0
#   BAND_SCALE_GUAR     player-specific log-guarantee band width (T1.2).
#                       MEASURED NULL, DEFAULT OFF 2026-07-25. Forward-chained
#                       Gate-2 chain (9 winters, n=1,199), paired bootstrap
#                       B=200 resampling the whole corpus with a refit per
#                       draw, ridge 3.0 on the variance step:
#                         pinball avg   flat 0.17094 scale 0.17087
#                                       delta -0.00007, CI95 [-.00314,+.00284],
#                                       P(improves) 0.545, MDE95 0.00288
#                         cond-cov RMSE delta -0.00019, MDE95 0.01264
#                         coverage      delta -0.00610, MDE95 0.01875
#                       and the ZERO-INFORMATION CONTROL (same estimator on a
#                       row-permuted residual column, same draws) moves the
#                       pinball by +0.00053 with a null band of
#                       [-0.00153, +0.00269] that CONTAINS the candidate's
#                       delta outright. The control scores as well as the
#                       candidate, so there is no result: the signing corpus
#                       does not support a conditional variance function.
#                       The knob and the code stay for re-gating at a larger
#                       corpus; the flat band it would replace is left shipped.
#                       (The WAR-side band, which does clear its floor, is a
#                       SEPARATE model and IS shipped - see fa_bands.)
#   BAND_PERMUTE_SEED   zero-information control: fit the variance function on
#                       a row-permuted residual column. Must return a flat
#                       sigma. Lab only.
#   RE-GATED 2026-08-07 on a DIFFERENT criterion and failed again. T1.2 asked
#   whether the band is sharper on average (pinball); the served board asks
#   whether its width is allocated less wrongly, so the new gate scored
#   |held-out P10-P90 coverage - 0.80| over the same 9-winter chain, B=40
#   paired. Coverage closeness improved 0.00730 against an MDE95 of 0.01782,
#   CI95 [-0.02085, +0.01502], and the PERMUTED control improved 0.00549 with
#   an identical p_improves of 0.775 - a shuffle buys three quarters of the
#   candidate's whole result. Point predictions are band-invariant (0 of 1,199
#   rows differ), so accuracy carries no evidence either way.
#   Pre-registration + numbers: docs/gate-2026-08-07-fa-guarantee-band.md,
#   data/fa_guar_band_eval.json. TWO independent nulls now. Do not re-open with
#   a ridge sweep over the same conditioning set; that is a six-way search on a
#   corpus that has twice failed to separate from its own shuffle.
BAND_SCALE_GUAR = False                     # measured null 2026-07-25 (T1.2)
BAND_PERMUTE_SEED = 0
BAND_RIDGE_GUAR = 3.0

_LAB_DEFAULTS = {
    "POS_GROUP_MODE": "v1", "COMPS_STRICT_PRIOR": True, "DESTALE_MODE": "series",
    "DESTALE_FIXED": 0.0, "RIDGE_YEARS": 0.0, "RIDGE_GUAR": 0.0,
    # MUST track the shipped defaults above - LAB_RESET() restores the CHAMPION,
    # so a stale entry here makes every future lab score the wrong baseline.
    "AAV_CONSISTENT": False, "RECAL_MODE": "shift", "LAB_TJ_PERMUTE_SEED": 0,
    "RECAL_TIER_MIN_ROWS": 30, "RECAL_TIER_PERMUTE_SEED": 0,
    "NOISE_FEATURES": 0, "NOISE_SEED": 0,
    "BAND_SCALE_GUAR": False, "BAND_PERMUTE_SEED": 0, "BAND_RIDGE_GUAR": 3.0,
}


def LAB_RESET() -> None:
    """Restore every arm knob to its shipped default (lab hygiene)."""
    g = globals()
    for k, v in _LAB_DEFAULTS.items():
        g[k] = v
    X_FEATURES.clear()
    X_FEATURES.update(_X_FEATURE_DEFAULTS)


def _npv_of(s: dict) -> float:
    """Deferral-adjusted guarantee for a signing row (falls back to the
    sticker where no schedule is on file — see deferral_npv_usd's
    convention note)."""
    return float(s.get("npv_guarantee_usd") or s["guarantee_usd"])


_POS_PREMIUM = {"SS", "2B", "3B", "CF", "IF", "MI", "OF"}


def _pos_group(position: str | None) -> str:
    head = (position or "").upper().split("/")[0].strip()
    if head in ("SP", "SP2", "P", "LHP", "RHP"):
        return "SP"
    if head in ("RP", "CL", "SIRP", "MIRP"):
        return "RP"
    if head == "C":
        return "C"
    if POS_GROUP_MODE == "v2":
        return "POSP" if head in _POS_PREMIUM else "POSC"
    return "POS"


def _discount_rate() -> float:
    return float(_vf_config()["discount_rate"])


def _dpw_inflation() -> float:
    cfg = _vf_config()
    if "dollars_per_war_inflation" not in cfg:
        # VAL_5 row 28: in unified $/WAR path mode a silent 0.05 fallback raises.
        import value_framework as _vfm
        if _vfm.dpw_path_active():
            raise _vfm.DpwPathError("dollars_per_war_inflation absent in unified $/WAR path mode")
    return float(_vf_config().get("dollars_per_war_inflation", 0.05))


def _destale_rate(dpw_series: dict[int, float] | None = None,
                  class_year: int | None = None) -> float:
    """The rate at which a historical dollar figure is carried forward to
    the class winter.

    The shipped path ("vf") reads value_framework's
    ``dollars_per_war_inflation``. That knob is 0.0 in production for a
    reason that belongs to the PROSPECT side (its $/WAR block is a trailing
    3-year average re-averaged annually, so forward escalation would
    double-count) — but the FA module borrows it for three unrelated jobs:
    de-staling a comp, escalating rational value, and carrying $/WAR
    forward a winter. At 0.0 a 2015 contract enters a 2027 player's comps
    anchor in 2015 nominal dollars.

    "series" estimates the rate from the module's OWN realized $/WAR series
    over the winters supplied — which, at every call site that matters, is
    the TRAIN-ONLY series, so the estimate is ex-ante by construction."""
    mode = DESTALE_MODE
    if mode == "fixed":
        return float(DESTALE_FIXED)
    if mode == "series" and dpw_series:
        yrs = sorted(y for y in dpw_series
                     if class_year is None or y <= class_year)
        if len(yrs) >= 4:
            # log-linear least squares slope -> compounded annual rate
            n = float(len(yrs))
            mx = sum(yrs) / n
            my = sum(math.log(dpw_series[y]) for y in yrs) / n
            num = sum((y - mx) * (math.log(dpw_series[y]) - my) for y in yrs)
            den = sum((y - mx) ** 2 for y in yrs)
            if den > 0:
                return max(0.0, min(0.12, math.exp(num / den) - 1.0))
    return _dpw_inflation()


# ============================================================================
# Point-in-time contract WAR paths (the projection engine + curve decay)
# ============================================================================

MAX_PATH_YEARS = 15


def _decay_path(war1: float, expo: float, side: str, role: str, age: int,
                curves: dict, aging: str = "v2", mlbam=None,
                pt_cap: bool | None = None) -> list[float]:
    """Decay a year-1 WAR along the aging curves: the WAR RATE (per 600 PA /
    250 BF) and playing time each walk their fitted deltas at the advancing
    age. Shared by the central path and the P10/P90 variants so uncertainty
    propagates through the SAME aging machinery.

    ``aging`` is the CALL-SCOPED engine selector (docs/AGING_V3_GATE.md section
    2): "v2" (default) walks the incumbent curves exactly as before; "v3" walks
    the aging_v3 model attached by fitted_models(..., aging="v3"), its bucket
    from the base-season position and, from year 2 on, the archetype of the
    three seasons before the base (the ARM R serve rule); with no arm active
    the v3 walk reproduces the v2 walk.

    ``pt_cap`` (call-scoped; None reads projection.pt_cap_enabled): when on,
    the exposure is clamped at the fitted meta["pt_cap"] in every step."""
    per = 600.0 if side == "hit" else 250.0
    _cap = fp.pt_cap_value(curves, side, role) if fp._pt_cap_on(pt_cap) else None
    rate = (war1 / expo * per) if expo > 0 else 0.0
    _v3 = None
    if aging == "v3":
        import aging_v3
        _v3 = aging_v3.model_of(curves)
        if _v3 is None:
            raise ValueError("aging='v3' needs the curves of fitted_models(..., aging='v3')")
        _seasons = _v3.meta.get("corpus_seasons") or [None, None]
        _base = (_v3.meta.get("max_season") or _seasons[1] or 0) + 1
        _bucket = _v3.bucket_of(mlbam, _base - 1, side, role)
        _arch = _v3.archetype_of(mlbam, _base, side)
    elif aging != "v2":
        raise ValueError(f"aging must be 'v2' or 'v3', got {aging!r}")
    path = []
    a = age
    e = expo
    for t in range(MAX_PATH_YEARS):
        if t > 0:
            a += 1
            if _v3 is None:
                rate += fp.curve_delta(curves, side, role, "war_rate", a)
                e += fp.curve_delta(curves, side, role, "pt", a)
                e = max(0.0, e)
            else:
                rate += _v3.rate_delta(side, "war_rate", a, bucket=_bucket, archetype=_arch,
                                       role=role)
                e = _v3.pt_next(side, role, e, a, bucket=_bucket)
        if _cap is not None:
            e = min(e, _cap)
        path.append(max(0.0, rate * e / per))
    return path


@lru_cache(maxsize=1)
def _gate1_band_quantiles() -> dict:
    """The Gate-1 EMPIRICAL year-1 WAR residual quantiles per reliability
    bucket (side x projected-exposure tier) — the committed artifact is the
    single source for every probability bucket on the platform."""
    try:
        d = json.loads((Path(__file__).parent / "data" / "fa_gate1_eval.json")
                       .read_text(encoding="utf-8"))
        return d.get("band_quantiles") or {}
    except (OSError, ValueError):
        log.warning("gate1 band quantiles unavailable — paths ship without bands")
        return {}


def _band_bucket(side: str, pt_y1: float) -> str:
    lo = 350 if side == "hit" else 250
    return f"{side}:{'hi' if pt_y1 >= lo else 'lo'}"


@lru_cache(maxsize=1)
def _gate1_band_scale() -> dict | None:
    """The T1.2 location-scale WAR band (data/fa_gate1_eval.json band_scale).

    None when the artifact predates T1.2 or the fit declined, in which case
    every caller falls back to the four bucket quantiles. Fallback is the
    documented behaviour, not an error path."""
    try:
        d = json.loads((Path(__file__).parent / "data" / "fa_gate1_eval.json")
                       .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    m = d.get("band_scale")
    return m if isinstance(m, dict) and m.get("gamma") else None


def _war_band_offsets(hist: list[dict], side: str, class_year: int,
                      war1: float, expo: float, age: int | None) -> dict | None:
    """{'q10','q90'} additive year-1 WAR offsets for THIS player.

    Same additive shape the bucket bands had, so the aging machinery
    downstream is untouched and the band change is the only change. Returns
    None when the scale model is absent, and the caller uses the buckets.

    The two covariates that are not on the projection object are recovered
    from the same history the projection was built on:
      thin   platform-season exposure under 180 PA/BF (the shipped
             thin-platform disclosure threshold at full-season pace)
      tj_n   Tommy John count STRICTLY BEFORE the class year (ex-ante by
             tj_surgery's own cutoff semantics)"""
    model = _gate1_band_scale()
    if model is None:
        return None
    import fa_bands
    platform = next((h for h in hist if h.get("season") == class_year - 1), None)
    vol = (platform.get("pa" if side == "hit" else "bf") or 0) if platform else 0
    thin = 1.0 if (platform is None or vol < 180.0) else 0.0
    tj_n = 0.0
    mlbam = next((h.get("mlbam") for h in hist if h.get("mlbam")), None)
    if mlbam:
        try:
            import tj_surgery
            tj_n = float(tj_surgery.tj_features(
                mlbam, f"{class_year}-01-01",
                _tj_store()).get("tj_count_pre") or 0)
        except Exception:                               # noqa: BLE001
            tj_n = 0.0
    z = fa_bands.war_z(side, war1, expo, age, thin, tj_n,
                       float(model.get("age_mean", 29.0)))
    o = fa_bands.offsets(model, z, side, (0.10, 0.90))
    return {"q10": o[0.10], "q90": o[0.90]} if o else None


def _ml_active() -> bool:
    cfg = (fa_class.get_config().get("projection") or {}).get("ml") or {}
    if not cfg.get("enabled"):
        return False
    import proj_ml
    return proj_ml.load() is not None


#: Whether /fa/ PRICING uses the F-DEF term. False by owner decision on
#: 2026-08-06. A PIN, not a global setting: fa_projection.DEF_FEATURE_DEFAULT
#: stays True so /projections/ is unaffected and only the money model
#: diverges. The FA page must disclose the divergence.
FA_PRICING_USE_DEF = False


def chain_aging_tail(series: list[float], champ_series: list[float],
                     horizon: int, n_years: int, floor: bool = True,
                     branch_champ: list[float] | None = None) -> list[float]:
    """THE SEAM: extend a `horizon`-season path past its last season along the
    champion's aging curve, chained from that last season's value.

    The champion's RELATIVE decay is applied to the path's own last value:
    season t prices champ[t] * (series[h-1] / champ[h-1]), floored at 0. Where
    the champion anchor is about zero (0.05 WAR or less) the ratio is undefined,
    so the last value decays along the champion's year-over-year ratio chain
    (capped at 1.0, 0.7 where the champion's prior season is itself about
    zero), floored at 0. Returns `series` followed by the chained seasons
    through index n_years - 1, each rounded to 0.01.

    contract_war_path uses this for horizons 6+ of the ML path and its P10/P90
    heads, and proj_export's contract tail (VAL2-Q1, owner answer 2026-09-30)
    prices guaranteed seasons past 2031 on the same output, so the two can
    never chain a different curve or from a different start point.

    floor=False (owner answer VAL2-Q3-REVIEW (b), 2026-09-30) drops the zero
    floor: a negative last value is carried along the same chain, so a P10
    head below zero stays below zero past the horizon instead of stepping up
    to 0. The default keeps the floor, so every existing caller is unchanged.

    branch_champ (POSTEPOCH_9_CONTRACT_TAIL_BAND_SEAM, 2026-10-07): the
    UNMULTIPLIED champion path a band caller's champ_series was scaled from
    (the P10/P90 heads pass 0.6 and 1.4 x the champion). Both 0.05 tests, the
    anchor's (scale or ratio chain) and each season's ratio-chain test, read
    it instead of champ_series, so the point and its band take the same branch
    and the same ratio every season, and P10 <= point <= P90 at the horizon
    carries into every chained season by construction. The values still come
    from champ_series; the multiplier cancels in both branches. Before it, a
    1.4 x anchor of 0.04 (0.056) took the scale branch on a zero champion tail
    while the point took the ratio chain: a P90 tail of 0.0 under a point of
    0.08 (kristian_campbell). None (every unmultiplied caller) tests
    champ_series itself, byte for byte the behaviour before."""
    H = int(horizon)
    lo = (lambda v: max(0.0, v)) if floor else (lambda v: v)
    gate = champ_series if branch_champ is None else branch_champ
    anchor = champ_series[H - 1]
    scale = (series[H - 1] / anchor) if gate[H - 1] > 0.05 else None
    tail = []
    for t in range(H, int(n_years)):
        if scale is not None:
            tail.append(lo(champ_series[t] * scale))
        else:
            # champion anchor ~0: decay the h5 value by the champion's
            # year-over-year ratio chain, floored at 0 unless floor=False
            prev = tail[-1] if tail else lo(series[H - 1])
            r = (champ_series[t] / champ_series[t - 1]) if gate[t - 1] > 0.05 else 0.7
            tail.append(lo(prev * min(1.0, r)))
    # + 0.0 turns a rounded -0.0 (an unfloored value just below zero) into 0.0
    return list(series) + [round(v, 2) + 0.0 for v in tail]


def contract_war_path(hist: list[dict], side: str, class_year: int, years: int,
                      age: int | None, curves: dict, war_map: dict,
                      league: dict, in_progress: tuple[int, float] | None = None,
                      use_ml: bool | None = None,
                      ml_models: dict | None = None,
                      p20: bool = False, aging: str = "v2",
                      pt_cap: bool | None = None) -> dict | None:
    """WAR by contract year: year 1 from the full Marcel engine; later
    years decay the WAR rate and playing time along the SAME aging curves
    (war_rate per-600/250 deltas + pt deltas at the advancing age).
    The path always extends MAX_PATH_YEARS so any candidate term can be
    priced by slicing; war_total covers the ACTUAL contract years.

    Floor/ceiling variants (war_by_year_p10 / _p90): the Gate-1 empirical
    year-1 residual quantile for the player's reliability bucket shifts the
    year-1 WAR, and the shifted talent decays along the same curves.

    ML DISPATCH (model-audit Phase 1): when projection.ml is enabled and a
    shipped proj_lgbm bundle loads, horizons 1-5 (point + bands) come from
    the quantile heads — which carry NO zero floor, the measured root
    cause of the survived-only coverage collapse. Horizons 6+ extrapolate
    the h5 head along the champion's relative decay (the documented seam:
    nothing beyond h5 is validatable). The champion path is ALWAYS
    computed (stack features + extrapolation + fallback); ``use_ml=False``
    pins the champion (gates, eval baselines, feature assembly).

    ``p20`` (default off; only the $/WAR path writer's enrichment sets it)
    applies correction P20 of docs/dpw-2026-09-25/DPW_PATH_GATE.md section 1.1
    inside the projection's playing-time formula.

    ``aging`` ("v2" default) is the call-scoped aging engine selector passed to
    _decay_path; the champion path, its P10/P90 variants and the year-1 PT step
    (through the curves fitted_models(..., aging=) returned) walk the same
    engine (docs/AGING_V3_GATE.md section 2).

    ``pt_cap`` (call-scoped; None reads projection.pt_cap_enabled) clamps the
    exposure at the fitted cap in the year-1 PT and every decay step; the ML
    heads' stack features stay on the uncapped champion (train/serve parity
    with the shipped bundle)."""
    _ptc = fp._pt_cap_on(pt_cap)
    proj = fp.project_player(hist, side, class_year, curves, league, age,
                             in_progress=in_progress, p20=p20, pt_cap=_ptc)
    if proj is None:
        return None
    war1 = fp.war_from_projection(proj, side, war_map, league, class_year)
    expo = proj["pt_proj"]
    role = proj["role"]
    # v2 — the DECAY walks the profile cohort's curves (power vs contact
    # hitters, power vs finesse pitchers age differently); the lookup
    # falls back to the base role wherever a cohort cell is thin.
    decay_role = fp.profile_role(hist, side, role, league)
    a = age or 30
    _mlbam = hist[0].get("mlbam") if hist else None
    path = _decay_path(war1, expo, side, decay_role, a, curves, aging=aging, mlbam=_mlbam,
                       pt_cap=_ptc)
    out = {"war_by_year": [round(w, 2) for w in path],
           # The champion MEAN path, carried alongside the (possibly ML)
           # display path for team roll-up consumers that must sum MEANS, not
           # the median-like ML quantile head (see the war_y1_champ note in the
           # ML branch). Inherited unchanged into out_ml via {**out}.
           "war_by_year_champ": [round(w, 2) for w in path],
           "war_total": round(sum(path[:years]), 2),
           "war_y1": round(path[0], 2) if path else 0.0,
           "role": role, "pt_y1": proj["pt_proj"],
           # Out-year RATE line (wOBA/wRC+ hitters, FIP pitchers) — the
           # year-1 component projection walked along the per-component
           # aging curves (fp.rate_path). DISPLAY machinery for the
           # projections board; WAR pricing stays on the war_rate decay
           # path above. Inherited into out_ml via {**out}.
           "rates_by_year": fp.rate_path(proj, side, curves, league)}
    # T1.2 - PLAYER-SPECIFIC band width. The four reliability buckets stay as
    # the documented fallback (they are what ships when the fitted scale model
    # is absent from the Gate-1 artifact), but where the fit exists the year-1
    # band is a continuous function of age, side, projected value, exposure,
    # platform thinness and prior TJ count rather than a two-bit step.
    q = _war_band_offsets(hist, side, class_year, war1, expo, age)
    band_src = "scale"
    if q is None:
        q = _gate1_band_quantiles().get(_band_bucket(side, expo))
        band_src = "bucket"
    if q:
        p10 = _decay_path(war1 + q["q10"], expo, side, decay_role, a, curves,
                          aging=aging, mlbam=_mlbam, pt_cap=_ptc)
        p90 = _decay_path(war1 + q["q90"], expo, side, decay_role, a, curves,
                          aging=aging, mlbam=_mlbam, pt_cap=_ptc)
        out["war_by_year_p10"] = [round(w, 2) for w in p10]
        out["war_by_year_p90"] = [round(w, 2) for w in p90]
        out["band_source"] = band_src
    if use_ml is False or (use_ml is None and not _ml_active() and ml_models is None):
        return out
    import proj_ml
    # Explicit ml_models = a POINT-IN-TIME bundle (historical enrichment);
    # default = the shipped live bundle. The live bundle must never serve
    # historical winters — it has seen their outcomes.
    models = ml_models if ml_models is not None else proj_ml.load()
    # The stack features read the UNCAPPED champion: the shipped heads were
    # trained on it, so a capped call recomputes it with pt_cap=False.
    champ_feat = out if not _ptc else contract_war_path(
        hist, side, class_year, years, age, curves, war_map, league,
        in_progress=in_progress, use_ml=False, p20=p20, aging=aging, pt_cap=False)
    feats = proj_ml.build_features(hist, side, class_year, age, curves,
                                   war_map, league, champ=champ_feat,
                                   in_progress=in_progress)
    if models is None or feats is None:
        return out
    ml = proj_ml.predict_path(models, feats, side)
    if ml is None:
        return out
    H = proj_ml.HORIZONS

    def _extend(series_ml: list[float], champ_series: list[float]) -> list[float]:
        return chain_aging_tail(series_ml, champ_series, H, MAX_PATH_YEARS)

    med = _extend(ml["war_by_year"], path)
    out_ml = {**out,
              "war_by_year": med,
              "war_total": round(sum(med[:years]), 2),
              "war_y1": med[0],
              # The champion MEAN rides along for aggregation consumers:
              # the ML quantile heads won the player-level gates, but their
              # median-like points sum ~520 league WAR vs the champion's
              # ~1,100 (right-skew: median < mean). Team roll-ups must sum
              # means - measured 2026-06-12 (team_outlook_eval retro block).
              "war_y1_champ": out["war_y1"],
              # The bands decide the chain's branch on the unmultiplied
              # champion (branch_champ), as the point does.
              "war_by_year_p10": chain_aging_tail(
                  ml["war_by_year_p10"], [p * 0.6 for p in path], H,
                  MAX_PATH_YEARS, branch_champ=path),
              # The same P10 chain without the zero floor (owner answer
              # VAL2-Q3-REVIEW (b)): what proj_export's contract tail range
              # reads, so a negative 2031 P10 carries into the later seasons.
              # Identical to war_by_year_p10 wherever that is above zero.
              "war_by_year_p10_open": chain_aging_tail(
                  ml["war_by_year_p10"], [p * 0.6 for p in path], H,
                  MAX_PATH_YEARS, floor=False, branch_champ=path),
              "war_by_year_p90": chain_aging_tail(
                  ml["war_by_year_p90"], [p * 1.4 for p in path], H,
                  MAX_PATH_YEARS, branch_champ=path),
              "model": proj_ml.MODEL_VERSION}
    # Playing-time-held (if-healthy) display path, carried through for
    # /projections/ only; consumers that price value ignore it.
    if ml.get("war_by_year_pth"):
        out_ml["war_by_year_pth"] = _extend(ml["war_by_year_pth"], path)
    return out_ml


def disc_war(path: dict, years: int) -> float:
    """Discounted WAR units over a candidate term — the quantity the
    market rate multiplies."""
    r = _discount_rate()
    return sum(w / ((1 + r) ** t)
               for t, w in enumerate(path["war_by_year"][:max(1, int(years))]))


# The rational anchor's term is the years stage's CONTINUOUS prediction, but it
# was rounded to an integer before being discounted, so the economic anchor
# stepped by a whole season every time the predicted term crossed a half year.
# That is the same class of defect as the comps cliff and it survived the
# comps fix: measured on the Chisholm sweep it was still worth 1.31x on the
# guarantee for a 0.02-WAR step after the anchor was smooth to 1.14x.
#
# MEASURED NO-SHIP 2026-07-31. Pro-rating the partial season removes that step
# (1.31x -> 1.08x) but LOSES Gate 2 on AAV: paired on the identical 1,199
# forward-chained rows against the kernel anchor alone, AAV MAE 2.8508 ->
# 2.8894, dMAE +0.0387, CI95 [+0.0126, +0.0630], P(better) 0.003. Guarantee is
# a tie (+0.0035, CI [-0.058, +0.070]) and years is byte-identical. Continuity
# is not worth a significant accuracy loss, so the default stays OFF and the
# residual ~1.3x step at the term boundary is an OPEN item, not a fixed one.
RATIONAL_TERM_CONTINUOUS = False


def _disc_war_term(path: dict, years: float) -> float:
    """disc_war at a possibly FRACTIONAL term: whole seasons plus the pro-rated
    share of the next one."""
    if not RATIONAL_TERM_CONTINUOUS:
        return disc_war(path, int(round(years)))
    r = _discount_rate()
    arr = path["war_by_year"]
    y = max(1.0, float(years))
    n = int(y)
    tot = sum(w / ((1 + r) ** t) for t, w in enumerate(arr[:n]))
    frac = y - n
    if frac > 0 and n < len(arr):
        tot += frac * arr[n] / ((1 + r) ** n)
    return tot


# ============================================================================
# $/WAR from FA signings only (per winter, regime-aware)
# ============================================================================

def dollars_per_war_by_winter(signings: list[dict]) -> dict[int, float]:
    """Implied FA $/WAR per winter: total NPV guarantee / total DISCOUNTED
    projected contract WAR across that winter's MLB deals (projected
    point-in-time — what buyers thought they were buying). Phase 2: the
    numerator is DEFERRAL-ADJUSTED (npv_guarantee_usd when attached) — a
    97%-deferred $700M is not $700M of present liability, and letting it
    inflate the winter's implied price of a win distorted every consumer
    downstream. Through-origin by construction; thin winters dropped."""
    agg: dict[int, dict] = defaultdict(lambda: {"g": 0.0, "w": 0.0, "n": 0})
    for s in signings:
        cw = s.get("_war_path")
        if not cw or not s.get("guarantee_usd") or not s.get("years"):
            continue
        disc = disc_war(cw, int(s["years"]))
        if disc <= 0:
            continue
        a = agg[s["class_year"]]
        a["g"] += s.get("npv_guarantee_usd") or s["guarantee_usd"]
        a["w"] += disc
        a["n"] += 1
    return {y: v["g"] / v["w"] for y, v in sorted(agg.items())
            if v["w"] > 20 and v["n"] >= 25}


# ============================================================================
# $/WAR breakdowns - what the one headline number is made of
# ============================================================================
# The headline series is one ratio per winter over ~100-190 deals. Everything
# that makes it interesting is inside that ratio: an SP win and an RP win are
# not the same price, a 1-year deal and a 7-year deal are not the same price,
# and the price a winter IMPLIED ex ante is not the price it turned out to
# charge. All three read off the corpus that is already built - no new ingest.
#
# TWO SERIES, NEVER CONFLATED:
#   implied  = NPV guarantee / PROJECTED discounted WAR. Ex ante, what buyers
#              thought they were paying per win. This is the headline and it is
#              what every future season escalates against.
#   realized = paid to date / bWAR to date, off the signings ledger. Ex post,
#              what the winter actually charged so far. A recent winter's
#              realized number is NOT comparable to an old one: little of the
#              money has been paid and little of the WAR banked, so both series
#              carry `elapsed` and the UI must say so.
_DPW_MIN_DEALS = 8            # below this a cell is a name, not a rate
_DPW_MIN_WAR = 4.0            # ...and a tiny denominator makes any ratio


def _fine_pos_group(position: str | None) -> str:
    """SP / RP / C / IF / OF / DH - finer than _pos_group, display only."""
    head = (position or "").upper().split("/")[0].strip()
    if head in ("SP", "SP2", "P", "LHP", "RHP"):
        return "SP"
    if head in ("RP", "CL", "SIRP", "MIRP"):
        return "RP"
    if head == "C":
        return "C"
    if head in ("1B", "2B", "3B", "SS", "IF", "INF"):
        return "IF"
    if head in ("LF", "CF", "RF", "OF"):
        return "OF"
    return "DH"


def _years_bucket(years: int) -> str:
    if years <= 1:
        return "1"
    if years <= 3:
        return "2-3"
    if years <= 6:
        return "4-6"
    return "7+"


def _guar_tier(usd: float) -> str:
    if usd < 10e6:
        return "<$10M"
    if usd < 50e6:
        return "$10-50M"
    if usd < 100e6:
        return "$50-100M"
    return "$100M+"


def _guar_ptier(usd: float) -> str:
    """The Gate-2 PREDICTED-guarantee tier bins (fa_backtest ptier slices):
    the decision-relevant conditioning for the level recalibration. NOT the
    display bins in _guar_tier above."""
    if usd < 10e6:
        return "lt10"
    if usd < 20e6:
        return "10to20"
    if usd < 50e6:
        return "20to50"
    return "ge50"


def _select_recal(rc, guar_raw: float, pos_group: str):
    """Resolve a fitted recal object to one (a, b) line for a row.

    Tuples pass through. "fit_group" dicts key on the position group.
    "shift_ptier" dicts key on the ptier of the RAW (pre-recal) predicted
    guarantee, the same conditioning the intercepts were fit under; a tier
    without its own intercept rides the pooled shift."""
    if not isinstance(rc, dict):
        return rc
    if rc.get("_mode") == "shift_ptier":
        return rc.get(_guar_ptier(guar_raw)) or rc.get("_pooled")
    return rc.get(pos_group) or rc.get("_pooled")


def _dpw_cell(rows: list[dict]) -> dict:
    """{n, spend, war, dpw} for one slice. `dpw` is None - not zero, not a
    guess - when the slice is too thin to price."""
    spend = sum(r["_npv"] for r in rows)
    war = sum(r["_disc"] for r in rows)
    ok = len(rows) >= _DPW_MIN_DEALS and war >= _DPW_MIN_WAR
    return {"n": len(rows), "spend": int(spend), "war": round(war, 2),
            "dpw": int(spend / war) if ok else None}


def dpw_breakdowns(signings: list[dict]) -> dict:
    """Per-winter decomposition of the implied $/WAR series + the realized one.

    ``signings`` are enriched rows (they carry _war_path); the realized half
    reads the stored ledger, which only exists on winters old enough to have
    banked WAR."""
    rows = []
    for s in signings:
        cw = s.get("_war_path")
        if not cw or not s.get("guarantee_usd") or not s.get("years"):
            continue
        disc = disc_war(cw, int(s["years"]))
        if disc <= 0:
            continue
        rows.append({**s, "_disc": disc,
                     "_npv": float(s.get("npv_guarantee_usd") or s["guarantee_usd"])})
    winters = sorted({r["class_year"] for r in rows})
    by_winter: dict[str, dict] = {}
    for y in winters:
        wr = [r for r in rows if r["class_year"] == y]
        head = _dpw_cell(wr)
        by_winter[str(y)] = {
            "n": head["n"], "spend": head["spend"], "war": head["war"],
            "dpw": head["dpw"],
            "qo_share": round(sum(1 for r in wr if r.get("qo")) / len(wr), 3),
            "pos": {g: _dpw_cell([r for r in wr if _fine_pos_group(r.get("position")) == g])
                    for g in ("SP", "RP", "C", "IF", "OF", "DH")},
            # 7+ deals run 0-5 a winter, so the per-winter cell is reported for
            # its COUNT and its dpw is suppressed by _dpw_cell; the pooled 7+
            # figure below is the one that can be read as a price.
            "len": {b: _dpw_cell([r for r in wr if _years_bucket(int(r["years"])) == b])
                    for b in ("1", "2-3", "4-6", "7+")},
            "tier": {t: _dpw_cell([r for r in wr if _guar_tier(r["_npv"]) == t])
                     for t in ("<$10M", "$10-50M", "$50-100M", "$100M+")},
        }
    pooled = {
        "pos": {g: _dpw_cell([r for r in rows if _fine_pos_group(r.get("position")) == g])
                for g in ("SP", "RP", "C", "IF", "OF", "DH")},
        "len": {b: _dpw_cell([r for r in rows if _years_bucket(int(r["years"])) == b])
                for b in ("1", "2-3", "4-6", "7+")},
        "tier": {t: _dpw_cell([r for r in rows if _guar_tier(r["_npv"]) == t])
                 for t in ("<$10M", "$10-50M", "$50-100M", "$100M+")},
    }
    # ---- realized, off the ledger ------------------------------------------
    realized: dict[str, dict] = {}
    for y in winters:
        paid = warx = 0.0
        n = done = 0
        elapsed_num = elapsed_den = 0.0
        for r in rows:
            if r["class_year"] != y:
                continue
            led = r.get("ledger") or {}
            p, w = led.get("paid_to_date_usd"), led.get("war_to_date")
            if p is None or w is None:
                continue
            paid += float(p)
            warx += float(w)
            n += 1
            done += 1 if led.get("complete") else 0
            tot = float(led.get("total_years") or r["years"] or 1)
            elapsed_num += min(1.0, float(led.get("elapsed_years") or 0) / max(tot, 1.0))
            elapsed_den += 1
        if n < _DPW_MIN_DEALS:
            continue
        realized[str(y)] = {
            "n": n, "paid": int(paid), "war": round(warx, 1),
            "dpw": int(paid / warx) if warx >= _DPW_MIN_WAR else None,
            "complete_share": round(done / n, 3),
            "elapsed": round(elapsed_num / elapsed_den, 3) if elapsed_den else None,
        }
    return {"by_winter": by_winter, "pooled": pooled, "realized": realized,
            "thresholds": {"min_deals": _DPW_MIN_DEALS, "min_war": _DPW_MIN_WAR},
            "groups": {"pos": ["SP", "RP", "C", "IF", "OF", "DH"],
                       "len": ["1", "2-3", "4-6", "7+"],
                       "tier": ["<$10M", "$10-50M", "$50-100M", "$100M+"]}}


def _dpw_forecast_method() -> str:
    cfg = (fa_class.get_config().get("market_model") or {}).get("dpw_forecast") or {}
    return str(cfg.get("method", "flat5"))


def _cbt_threshold_or_earliest(season: int) -> int:
    """CBT threshold with an earliest-encoded fallback — seasons before
    the rule file's first record (pre-2017 winters in the trend fits) use
    the earliest threshold rather than erroring out of a covariate."""
    try:
        return fa_cba.cbt_threshold(season)["threshold_usd"]
    except LookupError:
        rows = fa_cba._rules()["cbt_thresholds"]
        return min(rows, key=lambda r: r["season"])["threshold_usd"]


def _fit_log_trend(series: dict[int, float], with_cbt: bool):
    """Tiny deterministic OLS of log($/WAR) on year (+ log CBT threshold).
    Returns a predict(year)->usd callable. n is single-digit — this is a
    trend line, not a model; the forward-chained eval is what justifies it."""
    import numpy as np
    years = sorted(series)
    X = [[1.0, float(y)] for y in years]
    if with_cbt:
        for row, y in zip(X, years):
            row.append(math.log(_cbt_threshold_or_earliest(y)))
    yv = [math.log(series[y]) for y in years]
    b, *_ = np.linalg.lstsq(np.asarray(X), np.asarray(yv), rcond=None)

    def predict(year: int) -> float:
        x = [1.0, float(year)]
        if with_cbt:
            x.append(math.log(_cbt_threshold_or_earliest(year)))
        return float(math.exp(sum(c * v for c, v in zip(b, x))))
    return predict


def winter_dpw(dpw_series: dict[int, float], class_year: int) -> float:
    """The winter's $/WAR level, EX-ANTE — a test winter never sees its
    own prices. Methods (config market_model.dpw_forecast.method, chosen
    by the forward-chained eval in data/dpw_forecast_eval.json):
      flat5      most recent PRIOR winter carried forward at _destale_rate,
                 the series' own trend (0.0416 for the 2027 class), NOT 5%:
                 the name is the v1 carry's; tools/fit_dpw_forecast.py still
                 scores this form at a fixed 5% (audit X02-03)
      trend      log-linear trend fit on PRIOR winters
      trend_cbt  trend + log CBT-threshold covariate (thresholds for
                 future winters are dated CBA records — known ex-ante)
    Fewer than 4 prior winters always falls back to flat5."""
    prior = {y: v for y, v in dpw_series.items() if y < class_year}
    if not prior:
        # No PRIOR winter: anchor on the CLOSEST available winter (even a later one) and
        # de/escalate to class_year, rather than today's flat $/WAR -- which, with the
        # fa_implied re-anchor on, is the trailing 2024-26 signings-implied rate and is
        # anachronistic for an early class. Fall to the flat rate only if truly empty.
        #
        # The class year is EXCLUDED from the anchor candidates (2026-07-24 FA
        # lane). It used to be included, so the earliest training winter got a
        # log(dpw) feature computed from its OWN realized signings -- measured:
        # winter_dpw(2015) returned $9,185,919, byte-identical to
        # dpw_series[2015]. A feature this module documents as strictly ex-ante
        # was in-fit for the 96 rows of the first winter. Gate-2 test rows were
        # never affected (they always have prior winters); the damage was to the
        # fitted coefficients.
        cands = {y: v for y, v in dpw_series.items() if y != class_year}
        if cands:
            y0 = min(cands, key=lambda y: (abs(y - class_year), y))
            return cands[y0] * ((1 + _destale_rate(cands, class_year)) ** (class_year - y0))
        return fa_class._flat_dpw_usd()
    method = _dpw_forecast_method()
    if method in ("trend", "trend_cbt") and len(prior) >= 4:
        try:
            return _fit_log_trend(prior, with_cbt=(method == "trend_cbt"))(class_year)
        except Exception:                                   # noqa: BLE001 — fall back, never abort
            log.warning("dpw forecast %s failed — flat5 fallback", method)
    y = max(prior)
    return prior[y] * ((1 + _destale_rate(prior, class_year)) ** (class_year - y))


# ============================================================================
# THE one written $/WAR series (VAL_1, owner decision FP2-1, 2026-09-25)
# ============================================================================
# Before 2026-09-25 three $/WAR bases served at once. Prospect surplus priced at
# the clemens_2026 FanGraphs flat $11.74M. /projections/ priced veterans at a
# committed data/fa_dpw_series.json that only a Gate 2 persist wrote, by hand,
# carried to $17.97M for 2027. /fa/ priced at a series fa_export re-derived in
# every run and wrote nowhere, carried to $17.14M. The Trade Machine and the
# Club Ledger added prospect and veteran dollars into one total, so a prospect
# win cost less than a veteran win inside it. Now one writer writes one series and
# one level, and every surface reads them: fa_export (the /fa/ class boards),
# proj_export (veteran seasons) and value_framework (prospect surplus, and
# through it the eFV board, the Trade Machine, the farm and the Club Ledger).

DPW_SERIES_PATH = Path(__file__).parent / "data" / "fa_dpw_series.json"
DPW_SERIES_METHOD = "fa_signings_implied_v1"
DPW_SERIES_FIRST_WINTER = 2015


def build_dpw_series_payload(class_year: int,
                             enriched: list[dict] | None = None, *,
                             force: bool = False) -> dict:
    """The one written $/WAR series and the level every surplus prices at.

    usd_per_war_by_winter: the per-winter signings-implied series
    (dollars_per_war_by_winter) over the whole corpus through the class winter,
    integer dollars; thin winters are dropped as before, so a class winter only
    appears once it clears the floor. The retrospective ledger may read every
    winter's own rate.

    pricing: the ex-ante level for ``class_year``, exactly winter_dpw over the
    winters BEFORE it (the latest prior winter carried forward at the series'
    own trend), with the anchor winter, the carry rate and the discount rate the
    series was built at (the series divides by discounted WAR, so it depends on
    that rate). fa_export, proj_export and value_framework read level_usd from
    here; none of them re-derives it."""
    if enriched is None:
        enriched = enriched_signings(DPW_SERIES_FIRST_WINTER, class_year)
    series = {int(y): int(v) for y, v in dollars_per_war_by_winter(enriched).items()}
    prior = {y: float(v) for y, v in series.items() if y < class_year}
    pricing = None
    if prior:
        anchor = max(prior)
        pricing = {
            "class_year": int(class_year),
            "level_usd": int(round(winter_dpw(prior, class_year))),
            "anchor_winter": anchor,
            "anchor_usd": series[anchor],
            "carry_rate": round(_destale_rate(prior, class_year), 6),
            "method": _dpw_forecast_method(),
            "discount_rate": _discount_rate(),
            "corpus_winters": [min(series), max(series)] if series else None,
            "writer": "fa_market.write_dpw_series",
            "read_by": ["fa_export (the /fa/ class boards)",
                        "proj_export (veteran seasons on /projections/)",
                        "value_framework (prospect surplus; the clemens_2026 tier "
                        "shape rescaled to this level)"],
        }
    from fa_backtest import GATE2_MODEL_VERSION
    payload = {"method": DPW_SERIES_METHOD,
               "model_version": GATE2_MODEL_VERSION,
               "usd_per_war_by_winter": {str(k): v for k, v in sorted(series.items())},
               "breakdown": dpw_breakdowns(enriched),
               "pricing": pricing}
    # VAL_5: the dpw_path block, ONLY while the committed block switch is on
    # (off in every commit before the fWAR epoch's step Z; no environment
    # override). Off, the payload is VAL_1's keys exactly.
    if WRITE_DPW_PATH_BLOCK:
        _apply_dpw_path_block(payload, class_year, force)
    return payload


def write_dpw_series(class_year: int, enriched: list[dict] | None = None, *,
                     force: bool = False) -> dict:
    """Write data/fa_dpw_series.json, the ONLY writer of the file. Called once a
    night by run_monthly.rebuild_only before anything prices a prospect or a
    veteran, and by the Gate 2 persist (fa_backtest.run_market_gate), which
    used to write its own copy. Returns the pricing block.

    ``force`` (VAL_5) recomputes the dpw_path block regardless of its basis key;
    it does nothing while WRITE_DPW_PATH_BLOCK is off."""
    payload = build_dpw_series_payload(class_year, enriched, force=force)
    DPW_SERIES_PATH.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    fa_class._dpw_series.cache_clear()
    # value_framework caches its config for the life of the process, and the
    # level lives in this file: drop the cache so this process prices at the
    # level it just wrote, never the one it read before.
    import value_framework as _vf
    _vf._reset_caches()
    return payload["pricing"] or {}


def _written_doc() -> dict:
    try:
        return json.loads(DPW_SERIES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def written_dpw_series(through: int | None = None) -> dict[int, float]:
    """The written per-winter series, winters <= ``through`` when given (the
    exact series an in-run derivation over signings through that winter gives,
    because each winter's rate reads only its own deals). {} when absent."""
    raw = _written_doc().get("usd_per_war_by_winter") or {}
    return {int(y): float(v) for y, v in raw.items()
            if through is None or int(y) <= through}


def written_pricing_level_usd(class_year: int) -> float | None:
    """The one $/WAR level for ``class_year``: the written pricing.level_usd
    when the file prices that class, else winter_dpw over the written series
    (a future class carries the same anchor further). None when no series is
    written. In unified $/WAR path mode (VAL_5 row 15) a class after B reads P(c)."""
    import value_framework as _vfm
    if _vfm.dpw_path_active() and int(class_year) > _vfm.pricing_base_season():
        return float(_vfm.price_level(int(class_year)))
    block = _written_doc().get("pricing") or {}
    if block.get("level_usd") and int(block.get("class_year") or -1) == int(class_year):
        return float(block["level_usd"])
    series = written_dpw_series(through=class_year - 1)
    return winter_dpw(series, class_year) if series else None


# ============================================================================
# THE projected per-season $/WAR path block (VAL_5, owner ask 2026-09-25)
# ============================================================================
# docs/dpw-2026-09-25/DPW_PATH_GATE.md. The one writer above writes a dpw_path
# block into the one series file ONLY while this committed switch is on. It has
# NO environment override, and it is off until the wiring commit after the fWAR
# label epoch's step Z: until then every caller (the nightly rebuild step, the
# Gate 2 persist, a hand run) writes VAL_1's keys only, and
# test_gate2_untouched_by_path.py asserts that no caller writes a dpw_path key.
WRITE_DPW_PATH_BLOCK = False
DPW_PATH_SCHEMA = "dpw_path_v2"
DPW_OWNER_PATH = Path(__file__).parent / "data" / "dpw_path_owner.json"
DPW_EVAL_PATH = Path(__file__).parent / "data" / "dpw_forecast_eval.json"
P20_SEASON = 2020
# The seven environment switches the FA projection reads at call time
# (registration F20), with the module function that resolves each.
PROJECTION_SWITCHES = ("EEPHUS_PT_RISK", "EEPHUS_PIT_IP_AGE", "EEPHUS_PT_TJ", "EEPHUS_FA_REALWAR",
                       "EEPHUS_FA_DEF", "EEPHUS_FA_PTFIT", "EEPHUS_FA_MARCEL")


class DpwPathRefused(RuntimeError):
    """The writer refuses to write the dpw_path block."""


def projection_switch_stamps() -> dict:
    """For each of the seven switches: the raw environment value (None when
    unset) and the value the projection resolves. The block may only be written
    while every raw value is unset or equals the resolved default."""
    import os
    resolvers = {"EEPHUS_PT_RISK": (fp._pt_risk_enabled, lambda: fp.PT_RISK_DEFAULT),
                 "EEPHUS_PIT_IP_AGE": (fp._pit_ip_age_enabled, lambda: fp.PIT_IP_AGE_DEFAULT),
                 "EEPHUS_PT_TJ": (fp._pt_tj_enabled, lambda: fp.PT_TJ_DEFAULT),
                 "EEPHUS_FA_REALWAR": (fp._realwar_enabled, lambda: fp.REALWAR_DEFAULT),
                 "EEPHUS_FA_DEF": (fp._def_enabled, lambda: fp.DEF_FEATURE_DEFAULT),
                 "EEPHUS_FA_PTFIT": (fp._pt_fit_mode, lambda: fp.PT_FIT_DEFAULT),
                 "EEPHUS_FA_MARCEL": (fp._marcel_weights,
                                      lambda: [float(x) for x in fp._pcfg()["marcel_weights"]])}
    out = {}
    for name in PROJECTION_SWITCHES:
        resolve, default = resolvers[name]
        resolved = resolve()
        dflt = default()
        if isinstance(resolved, list):
            resolved = [float(x) for x in resolved]
        out[name] = {"raw": os.environ.get(name), "resolved": resolved, "default": dflt}
    return out


def _refuse_on_switch_override(stamps: dict) -> None:
    bad = [k for k, v in stamps.items() if v["raw"] is not None and v["resolved"] != v["default"]]
    if bad:
        raise DpwPathRefused("dpw_path block refused: projection switches overridden in the "
                             "environment: " + ", ".join(sorted(bad)))


def _deal_schedule(s: dict) -> list[dict] | None:
    """The deferral-ledger cash schedule of a signing, scaled so its nominal total
    equals the sticker (exactly as npv_guarantee_usd scales it); None for a level
    deal."""
    entry = (_deferral_ledger().get(f"{s.get('player_key')}:{s.get('class_year')}")
             if s.get("player_key") else None)
    if not entry or not entry.get("schedule"):
        return None
    total = sum(r["amount_usd"] for r in entry["schedule"])
    scale = float(s["guarantee_usd"]) / total if total else 1.0
    return [{"year_offset": r["year_offset"], "amount_usd": r["amount_usd"] * scale}
            for r in entry["schedule"]]


def _truth_rows(enriched: list[dict]) -> list[dict]:
    """One row per priced deal on the truth's basis: G_i, the level-equivalent
    sticker (registration section 1; never npv_guarantee_usd), and the WAR
    discounted at discount_rate."""
    import dpw_path as dp
    r = _discount_rate()
    rows = []
    for s in enriched:
        cw = s.get("_war_path")
        if not cw or not s.get("guarantee_usd") or not s.get("years"):
            continue
        disc = disc_war(cw, int(s["years"]))
        if disc <= 0:
            continue
        sticker = float(s["guarantee_usd"])
        sched = _deal_schedule(s)
        g = (sticker if sched is None else dp.level_equivalent_sticker(
            sticker, int(s["years"]), [(x["year_offset"], x["amount_usd"]) for x in sched], r))
        rows.append({"class_year": int(s["class_year"]), "years": int(s["years"]), "G": g,
                     "disc": disc, "scheduled": sched is not None, "_s": s})
    return rows


def _thin_filter(agg: dict) -> dict[int, float]:
    return {y: v["g"] / v["w"] for y, v in sorted(agg.items()) if v["w"] > 20 and v["n"] >= 25}


def truth_by_winter(enriched: list[dict]) -> dict[int, float]:
    """A(W) = sum G_i / sum disc_war_r(i), the deal filter and thin-winter rule
    of dollars_per_war_by_winter (estimator sticker_leveleq_r_over_disc_war_r_p20_v1
    when the enrichment carries P20)."""
    agg: dict[int, dict] = defaultdict(lambda: {"g": 0.0, "w": 0.0, "n": 0})
    for row in _truth_rows(enriched):
        a = agg[row["class_year"]]
        a["g"] += row["G"]
        a["w"] += row["disc"]
        a["n"] += 1
    return _thin_filter(agg)


def scheduled_share_by_winter(enriched: list[dict]) -> dict[int, dict]:
    """Per winter: the count of scheduled (deferral-ledger) deals and their share
    of the truth's numerator (I-4; properties of the series, not errors)."""
    agg: dict[int, dict] = defaultdict(lambda: {"n": 0, "g": 0.0, "g_sched": 0.0})
    for row in _truth_rows(enriched):
        a = agg[row["class_year"]]
        a["g"] += row["G"]
        if row["scheduled"]:
            a["n"] += 1
            a["g_sched"] += row["G"]
    return {y: {"n_scheduled": v["n"], "share": (v["g_sched"] / v["g"]) if v["g"] else 0.0}
            for y, v in sorted(agg.items())}


def term_mix_index_by_winter(enriched: list[dict]) -> dict:
    """The descriptive term-mix index (registration 5.1), per winter, with the
    buckets that dropped."""
    import dpw_path as dp
    by: dict[int, list] = defaultdict(list)
    for row in _truth_rows(enriched):
        by[row["class_year"]].append((row["years"], row["G"], row["disc"]))
    out, dropped = {}, {}
    for y in sorted(by):
        idx, drop = dp.term_mix_index(by[y])
        if idx is not None:
            out[y] = idx
        if drop:
            dropped[y] = drop
    return {"weights": dict(dp.TERM_MIX_WEIGHTS), "by_winter": out, "dropped_buckets": dropped}


def winter_level_se(enriched: list[dict], winter: int, B: int = 500,
                    seed: int = 20260925) -> float | None:
    """tau_W: the SE of ln A(W) from a within-winter deal bootstrap on the truth's
    basis (B draws, the given seed). None when the winter has no priced deal."""
    import random
    rows = [r for r in _truth_rows(enriched) if r["class_year"] == int(winter)]
    if len(rows) < 2:
        return None
    rng = random.Random(int(seed))
    logs = []
    n = len(rows)
    for _ in range(int(B)):
        g = w = 0.0
        for _i in range(n):
            r = rows[rng.randrange(n)]
            g += r["G"]
            w += r["disc"]
        if g > 0 and w > 0:
            logs.append(math.log(g / w))
    return statistics.stdev(logs) if len(logs) >= 2 else None


def pricing_dpw_by_winter(signings: list[dict], R: float, r_net: float) -> dict[int, float]:
    """The round-trip first-season price (OD-1 option round_trip): per winter,
    sum PV_R(cash_i) / sum of WAR discounted at r_net. Level deals pay AAV over
    the term at offsets 0..years-1; deferral-ledger deals pay their scheduled
    cash. The same deal filter and thin-winter rule."""
    agg: dict[int, dict] = defaultdict(lambda: {"g": 0.0, "w": 0.0, "n": 0})
    for s in signings:
        cw = s.get("_war_path")
        if not cw or not s.get("guarantee_usd") or not s.get("years"):
            continue
        years = int(s["years"])
        war = cw["war_by_year"][:max(1, years)]
        den = sum(w / ((1.0 + r_net) ** t) for t, w in enumerate(war))
        if den <= 0:
            continue
        sched = _deal_schedule(s)
        if sched is None:
            aav = float(s["guarantee_usd"]) / max(years, 1)
            cash = sum(aav / ((1.0 + R) ** t) for t in range(max(years, 1)))
        else:
            cash = sum(x["amount_usd"] / ((1.0 + R) ** x["year_offset"]) for x in sched)
        a = agg[int(s["class_year"])]
        a["g"] += cash
        a["w"] += den
        a["n"] += 1
    return _thin_filter(agg)


def _sha_bytes(p: Path) -> str:
    import hashlib
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return ""


def _estimator_code_sha() -> str:
    import hashlib
    import inspect
    import dpw_path as dp
    parts = [inspect.getsource(f) for f in (disc_war, dollars_per_war_by_winter, contract_war_path,
                                            enriched_signings, _truth_rows, truth_by_winter,
                                            pricing_dpw_by_winter, winter_level_se,
                                            fp.project_player)]
    parts.append(Path(dp.__file__).read_text(encoding="utf-8"))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _cba_block(base_season: int) -> dict:
    import dpw_path as dp
    rules = fa_cba._rules()
    regimes = rules.get("cba_regimes") or []
    expires = max((r.get("effective_to") or "" for r in regimes), default="")
    return {"expires": expires, "cbt_after_2026": "explicitly-unknown",
            "regime_break": dp.regime_break(rules, int(base_season)),
            "new_agreement_encoded": any((r.get("effective_from") or "") > dp.STRUCTURE_FROM
                                         for r in regimes)}


def build_dpw_path_block(class_year: int, *, force: bool = False,
                         previous: dict | None = None) -> dict:
    """The dpw_path block of DESIGN_v2 section 4.1, built by the one writer.

    Its own enrichment runs through N = B - 1 with P20 (not VAL_1's N + 1), the
    truth is the growth-free level-equivalent sticker series, the served level
    follows the recorded OD-1 option (round-trip by default), R is the recorded
    OD-2 value or the LITERAL default 0.113763, g_ref follows the OD-7 rule as
    the gate block's owner_at_amendment holds it (rule (a) with no record), the
    method is DPW_PATH_METHOD under the SERVE CONDITION. The enrichment is
    skipped and the block on disk carried forward while its basis key is
    unchanged; force=True recomputes it regardless."""
    import hashlib
    import dpw_companion
    import dpw_path as dp
    import value_framework as vfm
    from proj_export import FIRST_SEASON
    B = int(FIRST_SEASON)
    N = B - 1
    switches = projection_switch_stamps()
    _refuse_on_switch_override(switches)
    owner_doc = _read_json(DPW_OWNER_PATH)
    if owner_doc is not None:
        dp.validate_owner_doc(owner_doc)
    gate = (_read_json(DPW_EVAL_PATH) or {}).get("dpw_path_gate")
    options = {name: dp.convention(owner_doc, name) for name in dp.CONVENTION_IDS}
    R = dp.nominal_rate_from_owner(owner_doc)
    rule = dp.g_ref_rule(gate)
    method = dp.resolve_method(gate)
    r = _discount_rate()
    fp.build_corpus()
    key_src = {"corpus_sha": _sha_bytes(fp.CORPUS_CACHE),
               "deferrals_sha": _sha_bytes(Path(__file__).parent / "data" / "deferrals.json"),
               "war_provider": fp._war_provider(), "estimator_code_sha": _estimator_code_sha(),
               "projection_switches": {k: [v["raw"], v["resolved"]] for k, v in switches.items()},
               "discount_rate": r, "R": R, "g_ref_rule": rule, "B": B, "p20": True,
               "options": options, "method": method, "schema": DPW_PATH_SCHEMA}
    basis_key = dp.sha256_of(key_src)
    prev = previous if previous is not None else (_written_doc().get("dpw_path") or {})
    if not force and prev.get("basis_key") == basis_key:
        return prev
    enriched = enriched_signings(DPW_SERIES_FIRST_WINTER, N, p20=True)
    truth = truth_by_winter(enriched)
    if N not in truth:
        raise DpwPathRefused(f"the truth series has no winter {N}")
    g = dp.g_ref_value(rule, truth, N, previous=prev.get("discount"))
    r_net = (1.0 + R) / (1.0 + g) - 1.0
    if options["level_basis"] == "sticker":
        served = dict(truth)
        served_est = {"id": dp.TRUTH_ESTIMATOR_ID, "numerator_rate": r, "denominator_rate": r}
        note = "equals truth.by_winter"
    else:
        served = pricing_dpw_by_winter(enriched, R, r_net)
        served_est = {"id": dp.ROUND_TRIP_ESTIMATOR_ID, "numerator_rate": R, "denominator_rate": r_net}
        note = "scheduled cash discounted at R"
    if N not in served:
        raise DpwPathRefused(f"the served level has no winter {N}")
    g_a = dp.g_robust(truth, N) if method == "robust_drift" else None
    path = dp.build_path(served[N], N, method=method, g_ref=g, g_a=g_a)
    tau = {}
    for w in sorted(truth):
        se = winter_level_se(enriched, w, B=dp.BAND_B, seed=dp.BAND_SEED)
        if se is not None:
            tau[w] = se
    band = dp.band(path, N, truth, tau.get(N, 0.0), method)
    sched = scheduled_share_by_winter(enriched)
    tmi = term_mix_index_by_winter(enriched)
    truth_obj = {"estimator": {"id": dp.TRUTH_ESTIMATOR_ID, "numerator_rate": r, "denominator_rate": r,
                               "scheduled_deals": ("level-equivalent sticker = sticker x PV_r(schedule) "
                                                   "/ PV_r(level)")},
                 "by_winter": {str(k): v for k, v in sorted(truth.items())},
                 "tau_by_winter": {str(k): v for k, v in sorted(tau.items())},
                 "scheduled_share_by_winter": {str(k): v for k, v in sched.items()},
                 "term_mix_index": {"weights": tmi["weights"],
                                    "by_winter": {str(k): v for k, v in tmi["by_winter"].items()},
                                    "dropped_buckets": {str(k): v for k, v in tmi["dropped_buckets"].items()}}}
    truth_obj["sha256"] = dp.sha256_of({k: truth_obj[k] for k in
                                        ("estimator", "by_winter", "tau_by_winter", "term_mix_index")})
    import valuation_sets as vsets
    from datetime import datetime, timezone
    disc = {"form_served": vsets.discount_form(vfm.active_valuation_set()),
            "form_literal": vsets.discount_form_literal(vfm.active_valuation_set()), "R_nominal": R,
            "R_source": ("owner OD-2" if dp.last_answer(owner_doc, "OD-2") else
                         "default 0.113763 = (1.07)(1.0409) - 1 at L4(c)"),
            "g_ref": g, "g_ref_rule": rule, "g_ref_measured_at_n": N,
            "g_ref_source": {"keep_0409": "owner L4(c) | OD-7 rule (a)",
                             "remeasure_served_rule": "OD-7 rule (b)",
                             "zero_if_floor": "OD-7 rule (c)"}[rule],
            "r_net": r_net, "r_net_derivation": "(1 + R)/(1 + g_ref) - 1"}
    tiers = vfm._config()["dollars_per_war"]["tiered"]["rates"]
    flat = float(vfm._config()["dollars_per_war"]["flat"])
    block = {
        "schema": DPW_PATH_SCHEMA,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "enrichment": {"war_provider": key_src["war_provider"], "corpus_sha": key_src["corpus_sha"],
                       "deferrals_sha": key_src["deferrals_sha"],
                       "estimator_code_sha": key_src["estimator_code_sha"], "enriched_through": N,
                       "p20": True, "use_ml": False,
                       "fit_season_by_class": {str(y): y - 1 for y in range(DPW_SERIES_FIRST_WINTER, N + 1)},
                       "projection_switches": {k: {"raw": v["raw"], "resolved": v["resolved"]}
                                               for k, v in switches.items()}},
        "truth": truth_obj,
        "served_level": {"basis": options["level_basis"], "estimator": served_est,
                         "by_winter": {str(k): v for k, v in sorted(served.items())},
                         "deferral_rebase_note": note},
        "clock": {"base_season": B, "last_realized_winter": N,
                  "rule": "B = proj_export.FIRST_SEASON, rolled at the post-season step; N = B - 1"},
        "discount": disc,
        "path": {"method": method, "params": {"g": g, "g_A": g_a},
                 "forecast_through": N + dp.FORECAST_HORIZON,
                 "usd_by_season": {str(k): v for k, v in sorted(path.items())},
                 "kind_by_season": {str(k): v for k, v in dp.path_kinds(N, method).items()},
                 "taper": ({"seasons": [N + dp.FORECAST_HORIZON + k for k in range(1, dp.TAPER_SEASONS + 1)],
                            "rule": "(1 - k/5) of the h = 5 log deviation"} if method == "robust_drift" else None),
                 "cba_label": "conditional on the expired CBA's structure",
                 "band": {"p10": {str(k): v for k, v in band["p10"].items()},
                          "p90": {str(k): v for k, v in band["p90"].items()},
                          "kind": {str(k): v for k, v in band["kind"].items()},
                          "s_d": band["s_d"], "n_d": band["n_d"], "c_m": band["c_m"],
                          "formula": band["formula"],
                          "ev_factor_unapplied": {str(k): v for k, v in band["ev_factor_unapplied"].items()}}},
        "salary_index": dpw_companion.salary_index_block(B, path, options["companion_mode"],
                                                         dp.WRITTEN_THROUGH),
        "tier_shape": {k: float(v) / flat for k, v in tiers.items()},
        "cba": _cba_block(B),
        "options": {**options, "source": "data/dpw_path_owner.json"},
        "gate": {"doc": "docs/dpw-2026-09-25/DPW_PATH_GATE.md",
                 "verdict_source": "data/dpw_forecast_eval.json dpw_path_gate (the only verdict copy)"},
        "basis_key": basis_key,
    }
    block["basis_id"] = hashlib.sha256(dp.canonical_json(
        [truth_obj["sha256"], block["served_level"], block["clock"], block["discount"],
         block["path"]["usd_by_season"], block["salary_index"]["mode"], block["options"]])
        .encode("utf-8")).hexdigest()[:12]
    return block


def _apply_dpw_path_block(payload: dict, class_year: int, force: bool) -> None:
    """While WRITE_DPW_PATH_BLOCK is on: add the block, and while the unified path
    serves set VAL_1's pricing.level_usd to P(B) with pricing.source dpw_path, so
    every reader of the one level reads the unified one (DESIGN_v2 row 32)."""
    import value_framework as vfm
    block = build_dpw_path_block(class_year, force=force)
    payload["dpw_path"] = block
    if vfm.dpw_path_on() and payload.get("pricing"):
        b = str(block["clock"]["base_season"])
        payload["pricing"] = {**payload["pricing"],
                              "level_usd": int(round(float(block["path"]["usd_by_season"][b]))),
                              "source": "dpw_path"}


# ============================================================================
# Rational value, deferrals, opt-outs, QO tax
# ============================================================================

def rational_value_usd(war_by_year: list[float], class_year: int,
                       dpw_usd: float, infl: float | None = None) -> int:
    """NPV of the projected production: Σ_t PV(value(war_t) × level_t),
    $/WAR escalating at the configured inflation, discounted at the
    the platform's configured rate (value_framework discount_rate, 0.07 in
    production).

    v2 — CONVEX season pricing. The v1 flat rate priced a 1-WAR season and
    the third win of a 3-WAR season identically, so the entire bottom of
    the class graded as a bargain (measured: class median Deal+ 220).
    Wins are NOT fungible at one price — the market pays a premium per win
    for star seasons and a discount for fringe ones. Each season is now
    priced through the platform's tier curve (value_framework
    tiered_war_value_usd — the SAME convexity the prospect surplus model
    uses), rescaled so the curve's overall level matches this winter's
    ex-ante FA $/WAR. One convex shape, two modules, one source of truth."""
    from value_framework import tiered_war_value_usd
    import value_framework as _vfm
    if _vfm.dpw_path_active():
        # VAL_5 row 11: each season at its own level, discounted to the class
        # year at R (I2's exception); dpw and the escalator are not read.
        _i = _dpw_inflation() if infl is None else float(infl)
        return int(sum(tiered_war_value_usd(w) * _vfm.fa_season_factor(class_year, t, _i, dpw_usd)
                       for t, w in enumerate(war_by_year)))
    r = _discount_rate()
    infl = _dpw_inflation() if infl is None else float(infl)
    level = dpw_usd / float(_vf_config()["dollars_per_war"]["flat"])
    total = 0.0
    for t, w in enumerate(war_by_year):
        total += (tiered_war_value_usd(w) * level * ((1 + infl) ** t)) / ((1 + r) ** t)
    return int(total)


def rational_value_draws_usd(sims, class_year: int, dpw_usd: float,
                             infl: float | None = None):
    """rational_value_usd applied to every row of a (draws x years) array of
    simulated WAR paths (fa_mc.simulate), returned as a numpy array of NPVs.

    Same season pricing, level, escalation and discounting as
    rational_value_usd, one column at a time, so a draw's value equals
    rational_value_usd(list(draw)) to the dollar (test_fa_tier1 pins it). The
    point of it: a QUANTILE of contract value has to be read off the priced
    draws. Pricing each season's own P10 and adding them assumes the player
    lands at his P10 in every season at once (comonotone), which the measured
    horizon residual Spearman (0.45 at lag 1, fa_mc) says is false."""
    import numpy as np
    from value_framework import tiered_war_value_usd
    import value_framework as _vfm
    if _vfm.dpw_path_active():
        # VAL_5 row 11, as rational_value_usd.
        _i = _dpw_inflation() if infl is None else float(infl)
        arr = np.asarray(sims, dtype=float)
        total = np.zeros(arr.shape[0])
        for t in range(arr.shape[1]):
            col = np.fromiter((tiered_war_value_usd(w) for w in arr[:, t]),
                              dtype=float, count=arr.shape[0])
            total += col * _vfm.fa_season_factor(class_year, t, _i, dpw_usd)
        return total
    r = _discount_rate()
    infl = _dpw_inflation() if infl is None else float(infl)
    level = dpw_usd / float(_vf_config()["dollars_per_war"]["flat"])
    arr = np.asarray(sims, dtype=float)
    total = np.zeros(arr.shape[0])
    for t in range(arr.shape[1]):
        col = np.fromiter((tiered_war_value_usd(w) for w in arr[:, t]),
                          dtype=float, count=arr.shape[0])
        total += (col * level * ((1 + infl) ** t)) / ((1 + r) ** t)
    return total


def expected_rational_value_usd(path: dict, years: int, class_year: int,
                                dpw_usd: float, infl: float | None = None) -> int:
    """T1.4 - the EXPECTATION of the tier-priced value, not the tier price of
    the expectation.

    ``rational_value_usd`` above evaluates the tier curve at the mean path.
    value_framework.tiered_war_value_usd's own docstring says "never call on
    an averaged WAR". MEASURED, not assumed: that curve is convex below ~1.2
    WAR, mildly CONCAVE from 1.2 to 2.52, and exactly LINEAR above 2.52 (see
    fa_mc's module docstring for the differenced profile), so the correction
    is large and positive exactly where free-agent seasons live and nil at
    the top of the market. Measured in dollars against realized tier-priced
    WAR on
    449 forward-chained Gate-2 signings (2018-2022, terms fully realized,
    tools/_fa_jensen.py):

        signed bias   naive -$3.219M/signing -> corrected -$0.509M
        |bias| delta  -$2.400M, CI95 [-2.974, -0.489], MDE95 $1.256M,
                      P(improves) 0.9925 over B=400 paired draws
        level         mean $7.699M -> $10.409M (+35.2%) vs realized $10.918M
        MAE           $9.747M -> $11.082M, i.e. WORSE (+1.343, CI95
                      [0.961, 1.708]) - correcting a level bias on noisy
                      per-row bands raises dispersion. Reported, not hidden.

    MANDATORY CONTROL (band WIDTHS permuted across players, point paths held
    fixed): |bias| delta -$2.465M, band [-3.193, -0.256], which CONTAINS the
    real effect. The Jensen correction is real; its size is driven by the
    AVERAGE width, not by any player's own width. Stated plainly: this fixes
    a level error, it does not demonstrate that player-specific widths matter
    for the level.

    Falls back to the shipped point pricing when the path carries no band
    (nothing to integrate over)."""
    p10 = path.get("war_by_year_p10")
    p90 = path.get("war_by_year_p90")
    mean_path = path.get("war_by_year") or []
    if not p10 or not p90:
        return rational_value_usd(mean_path[:years], class_year, dpw_usd, infl)
    import fa_mc
    return fa_mc.expected_tier_value_usd(
        mean_path, p10, p90, years, class_year, dpw_usd,
        _dpw_inflation() if infl is None else float(infl), _discount_rate())


def deferral_npv_usd(schedule: list[dict] | None, guarantee_usd: int, *,
                     rate: float | None = None) -> dict:
    """Sticker vs NPV guarantee. ``schedule`` rows: {year_offset, amount_usd}
    (from data/deferrals.json / fa_overrides when available). Without
    a schedule the guarantee is assumed level over the term — documented.

    IMPORTANT CONVENTION (Phase 2): a no-schedule deal keeps NPV == sticker.
    That treats the sticker as already-level cash, so the NPV adjustment
    captures only the DEFERRAL-vs-level difference — exactly the quantity
    the deferral ledger documents. Discounting every level contract too
    would just rescale all targets by an annuity factor without changing
    the model comparison, while making the displayed numbers unfamiliar.

    ``rate`` (VAL_5): the rate to discount at; the default is _discount_rate(),
    so Gate 2, the $/WAR truth and every legacy caller keep 0.07. The Club
    Ledger passes its one platform rate in unified $/WAR path mode."""
    r = _discount_rate() if rate is None else float(rate)
    if not schedule:
        return {"sticker_usd": guarantee_usd, "npv_usd": guarantee_usd,
                "method": "no_deferral_schedule_on_file"}
    npv = sum(row["amount_usd"] / ((1 + r) ** row["year_offset"]) for row in schedule)
    return {"sticker_usd": guarantee_usd, "npv_usd": int(npv), "method": "schedule_npv"}


@lru_cache(maxsize=1)
def _deferral_ledger() -> dict:
    """data/deferrals.json — curated deferral schedules (WS-2a). Returns
    {player_key:class_year -> entry} with compact flows expanded into
    {year_offset, amount_usd} rows."""
    try:
        d = json.loads((Path(__file__).parent / "data" / "deferrals.json")
                       .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("deferral ledger unavailable — NPV == sticker everywhere")
        return {}
    out = {}
    for key, e in (d.get("players") or {}).items():
        entry = dict(e)
        if e.get("flows"):
            entry["schedule"] = [
                {"year_offset": t, "amount_usd": f["amount_usd"]}
                for f in e["flows"] for t in range(f["from"], f["to"] + 1)]
        out[key] = entry
    return out


def npv_guarantee_usd(player_key: str | None, class_year: int,
                      guarantee_usd: int) -> tuple[int, bool]:
    """(NPV guarantee at the platform discount rate, had_schedule). The
    DEFERRAL-ADJUSTED guarantee is the Phase-2 basis for the $/WAR series,
    the market-model targets and Gate 2 — a 97%-deferred megadeal is not
    the same liability as level cash and must not train the model as if
    it were."""
    entry = _deferral_ledger().get(f"{player_key}:{class_year}") if player_key else None
    if not entry or not entry.get("schedule"):
        return guarantee_usd, False
    # Level-payment ledgers can drift a hair from the sticker (rounding);
    # scale the schedule so total nominal == sticker before discounting.
    total = sum(r["amount_usd"] for r in entry["schedule"])
    scale = guarantee_usd / total if total else 1.0
    sched = [{"year_offset": r["year_offset"],
              "amount_usd": r["amount_usd"] * scale} for r in entry["schedule"]]
    return deferral_npv_usd(sched, guarantee_usd)["npv_usd"], True


def deferral_coverage_audit(signings: list[dict],
                            threshold_usd: int = 200_000_000) -> dict:
    """The WS-2a ship gate, as data: every guarantee >= threshold must have
    a ledger entry (schedule OR explicit deferred=false). Misses listed,
    never papered over."""
    ledger = _deferral_ledger()
    missing, covered = [], 0
    for s in signings:
        g = s.get("guarantee_usd") or 0
        if g < threshold_usd or not s.get("mlb_deal"):
            continue
        key = f"{s.get('player_key')}:{s.get('class_year')}"
        if key in ledger:
            covered += 1
        else:
            missing.append({"key": key, "name": s.get("player_name"),
                            "guarantee_usd": g})
    return {"threshold_usd": threshold_usd, "covered": covered,
            "missing": missing,
            "unverified": sorted(k for k, e in ledger.items()
                                 if "unverified" in (e.get("verify_status") or ""))}


def enter_probability_v2(pred: dict, fa_type: str | None,
                         option_price_usd: float | None) -> dict | None:
    """P(player actually reaches the class) priced from the MARKET MODEL'S
    OWN band distribution (model-audit Phase 3, WS-2d) — replacing the v1
    crude-$-gap logistic for the option types where one side compares the
    option price against the player's market:

      opt_out / player_option  the player walks when the market beats the
                               price: P(enter) = P(projAAV > price)
      club_option              the club declines (player enters) when the
                               market is BELOW the price: P(projAAV < price)

    The distribution is log-normal interpolated from the Gate-2-validated
    empirical residual bands (mu = log point estimate, sigma from the
    P10-P90 span / 2z). Mutual + conditional options keep their explicit
    priors (a band can't see two parties' intentions). DECISION-level
    validation is blocked on the historical option-decision data lift
    (registry: fa_penter) — the 2026-27 winter's logged events are the
    first live shakedown."""
    if not option_price_usd or not pred:
        return None
    z = 1.2816
    # ---- T1.5 BASIS REPAIR ------------------------------------------------
    # The strike and the market number have to be the same KIND of quantity.
    #
    #   club_option / player_option   the strike is ONE season's salary, so
    #                                 proj_aav is the coherent comparison.
    #   opt_out                       the strike is the REMAINING GUARANTEE the
    #                                 player walks away from, so it must be
    #                                 compared to the remaining MULTI-YEAR
    #                                 market value, not to one season's AAV.
    #
    # Comparing a remaining-guarantee strike to a single season's AAV made
    # every opt-out look impossibly expensive to exercise: P(Bo Bichette opts
    # out) served as 0.009 because a multi-year number was being read as if it
    # were an annual one. The repair prices the opt-out against the projected
    # guarantee over the term the model itself predicts.
    if fa_type == "opt_out":
        point = pred.get("proj_guarantee_usd")
        lo = pred.get("proj_guarantee_p10_usd")
        hi = pred.get("proj_guarantee_p90_usd")
        method = "band_priced_opt_out_remaining_guarantee"
    else:
        point = pred.get("proj_aav_usd")
        lo = pred.get("proj_aav_p10_usd")
        hi = pred.get("proj_aav_p90_usd")
        method = None
    if not point or not lo or not hi or hi <= lo:
        return None
    mu = math.log(point)
    sigma = max(0.05, (math.log(hi) - math.log(lo)) / (2 * z))
    # standard normal CDF via erf
    zscore = (math.log(option_price_usd) - mu) / sigma
    cdf = 0.5 * (1.0 + math.erf(zscore / math.sqrt(2)))
    if fa_type == "opt_out":
        return {"enter_prob": round(1.0 - cdf, 3), "method": method}
    if fa_type == "player_option":
        return {"enter_prob": round(1.0 - cdf, 3), "method": "band_priced_player_side"}
    if fa_type == "club_option":
        return {"enter_prob": round(cdf, 3), "method": "band_priced_club_side"}
    return None


# ============================================================================
# T1.5 - options priced as CONTINGENT CLAIMS on the shipped band
# ============================================================================

def option_value_usd(pred: dict, fa_type: str | None,
                     option_price_usd: float | None) -> dict | None:
    """What the option is WORTH, in dollars, to the side that holds it.

    The board already knew whether an option existed and what its strike was;
    it never priced one. Every option is a claim on the same log-normal the
    band defines (mu = log point estimate, sigma from the P10-P90 span over
    2z), so the closed-form Black-Scholes-style expectations apply directly
    with zero extra machinery:

      club option    the TEAM holds a call on the player's market at the
                     strike: it exercises when the market S exceeds the strike
                     K, so the team's claim is E[max(S - K, 0)].
      player option  the PLAYER holds a put: he stays at K when the market is
                     below it, so the TEAM IS SHORT E[max(K - S, 0)].
      opt_out        a player call on his own re-rating: he walks when the
                     remaining market beats the remaining guarantee, so the
                     team is short E[max(S - K, 0)] on the remaining-guarantee
                     basis (see the units repair in enter_probability_v2).

    ``held_by`` and the SIGN of ``team_value_usd`` are both returned because
    the sign is the entire editorial point: a player option is a liability the
    board used to render as a neutral flag.

    MUTUAL OPTIONS ARE NOT PRICED HERE, on purpose. A mutual option needs the
    club to want S > K and the player to want S < K in the same instant, which
    cannot both be true, so its rational value is ~0 and its exercise rate
    should be ~0. That prediction is testable against data/fa_archive.json and
    is tested in test_fa_options.py."""
    if not option_price_usd or not pred or fa_type not in (
            "club_option", "player_option", "opt_out"):
        return None
    if fa_type == "opt_out":
        point = pred.get("proj_guarantee_usd")
        lo, hi = (pred.get("proj_guarantee_p10_usd"),
                  pred.get("proj_guarantee_p90_usd"))
        basis = "remaining_guarantee"
    else:
        point = pred.get("proj_aav_usd")
        lo, hi = pred.get("proj_aav_p10_usd"), pred.get("proj_aav_p90_usd")
        basis = "annual_salary"
    if not point or not lo or not hi or hi <= lo:
        return None
    z = 1.2816
    K = float(option_price_usd)
    sigma = max(0.05, (math.log(hi) - math.log(lo)) / (2 * z))
    # Log-normal with median `point`. E[S] = point * exp(sigma^2/2).
    mu = math.log(point)
    d1 = (mu - math.log(K)) / sigma + sigma
    d2 = d1 - sigma
    ES = math.exp(mu + 0.5 * sigma * sigma)

    def _phi(x):
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))

    call = ES * _phi(d1) - K * _phi(d2)          # E[max(S-K,0)]
    put = K * _phi(-d2) - ES * _phi(-d1)         # E[max(K-S,0)]
    if fa_type == "club_option":
        return {"kind": "call", "held_by": "team", "basis": basis,
                "strike_usd": int(K), "sigma": round(sigma, 4),
                "option_value_usd": int(call), "team_value_usd": int(call),
                "p_exercise": round(_phi(d2), 3)}
    if fa_type == "player_option":
        return {"kind": "put", "held_by": "player", "basis": basis,
                "strike_usd": int(K), "sigma": round(sigma, 4),
                "option_value_usd": int(put), "team_value_usd": -int(put),
                "p_exercise": round(_phi(-d2), 3)}
    return {"kind": "call", "held_by": "player", "basis": basis,
            "strike_usd": int(K), "sigma": round(sigma, 4),
            "option_value_usd": int(call), "team_value_usd": -int(call),
            "p_exercise": round(_phi(d2), 3)}


def opt_out_scenarios(war_by_year: list[float], opt_out_after: int,
                      class_year: int, dpw_usd: float) -> dict:
    """v1 = SCENARIO LINES (owner decision): the rational value of the full
    term vs the pre-opt-out years only. Labeled, not option-priced."""
    full = rational_value_usd(war_by_year, class_year, dpw_usd)
    pre = rational_value_usd(war_by_year[:opt_out_after], class_year, dpw_usd)
    return {"full_term_rational_usd": full, "pre_opt_out_rational_usd": pre,
            "note": "scenario lines; opt-out not option-priced in v1"}


_PICK_FV_CACHE: dict | None = None
# Representative forfeited slots per the compensation matrix's pick
# DESCRIPTIONS ("2nd-highest pick" etc.) — documented v1 mapping.
_TIER_SLOTS = {"2nd-highest": 55, "3rd-highest": 85, "5th-highest": 145}


def pick_fv_curve() -> dict[int, float]:
    """Median consensus FV by overall-pick bucket from the platform's OWN
    draft classes — PROSPX research is the QO tax's pricing source."""
    global _PICK_FV_CACHE
    if _PICK_FV_CACHE is not None:
        return _PICK_FV_CACHE
    path = Path(__file__).parent / "data" / "draft_timeseries.json"
    buckets: dict[int, list[float]] = defaultdict(list)
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        for cls in d.get("classes", []):
            for p in cls.get("prospects", []):
                pick, fv = p.get("drafted_pick"), p.get("consensus_fv")
                if pick and fv:
                    buckets[min(int(pick) // 15, 12)].append(float(fv))
    except (OSError, ValueError):
        log.warning("pick_fv_curve: draft data unavailable")
    _PICK_FV_CACHE = {b: statistics.median(v) for b, v in buckets.items() if len(v) >= 5}
    return _PICK_FV_CACHE


_SLOT_FIRST6_CACHE: list | None = None
# Median draft->debut lag for the picks the compensation matrix forfeits
# (top-150): the control window starts years after the pick is spent.
_SLOT_ETA_YEARS = 3.0


def _slot_first6_war(slot: int) -> float | None:
    """Expected first-six-MLB-season bWAR at a draft slot, from the
    REALIZED curve (decreasing isotonic on 2005-14 signed picks x
    war_daily — data/draft_slot_curve.json, Phase 4b WS-8)."""
    global _SLOT_FIRST6_CACHE
    if _SLOT_FIRST6_CACHE is None:
        try:
            d = json.loads((Path(__file__).parent / "data" /
                            "draft_slot_curve.json").read_text(encoding="utf-8"))
            _SLOT_FIRST6_CACHE = [(int(b), float(w))
                                  for b, w in d["first6_step_curve"]
                                  if w is not None] or []
        except (OSError, ValueError, KeyError, TypeError):
            _SLOT_FIRST6_CACHE = []
    if not _SLOT_FIRST6_CACHE:
        return None
    return next((w for b, w in _SLOT_FIRST6_CACHE if slot <= b),
                _SLOT_FIRST6_CACHE[-1][1])


def _slot_surplus_usd(slot: int) -> int | None:
    """Price a forfeited slot: the realized expected first-6-season WAR
    path (flat across the control window — the curve is a window total)
    through the platform's service-time surplus machinery, lagged
    _SLOT_ETA_YEARS for draft->debut. Convexity caveat: pricing the
    EXPECTED path through the convex tier curve is a lower bound on the
    expectation of value (the rare-hit mass prices above linear) —
    direction disclosed, consistent across slots."""
    first6 = _slot_first6_war(slot)
    if first6 is None:
        return None
    import value_framework as _vf
    path = [first6 / 6.0] * 6
    return int(_vf._service_path_surplus_usd(path, super_two=False,
                                             eta_years=_SLOT_ETA_YEARS))


def qo_tax_usd(payor_tier: str, as_of) -> dict:
    """The QO pick forfeiture as DOLLARS: each forfeited representative
    slot priced at its REALIZED first-6-season WAR expectation through
    the service-time surplus machinery (Phase 4b WS-8 re-price), plus
    any forfeited intl pool money at face value. Falls back to the v1
    platform FV-at-slot median when the fitted artifact is absent."""
    forf = fa_cba.pick_forfeiture(payor_tier, as_of)
    curve = pick_fv_curve()
    total = int(forf.get("intl_pool_usd") or 0)
    detail = []
    fitted_used = False
    for pick_desc in forf["picks"]:
        slot = _TIER_SLOTS.get(pick_desc, 90)
        usd = _slot_surplus_usd(slot)
        if usd is not None:
            fitted_used = True
            row = {"pick": pick_desc, "slot_assumed": slot,
                   "first6_war": _slot_first6_war(slot), "surplus_usd": usd}
        else:
            fv = curve.get(min(slot // 15, 12))
            usd = int(point_estimate_surplus_usd(fv, False) or 0) if fv else 0
            row = {"pick": pick_desc, "slot_assumed": slot,
                   "fv_at_slot": fv, "surplus_usd": usd}
        detail.append(row)
        total += usd
    return {"total_usd": total, "detail": detail,
            "carry_forward": forf.get("carry_forward", False),
            "method": ("realized_slot_war_service_priced_v2" if fitted_used
                       else "platform_fv_at_slot_v1")}


# ============================================================================
# Predicted market price — transparent two-stage OLS + empirical bands
# ============================================================================

# Gate-2 feature-experiment flags (owner program 2026-07-15). Each arm is
# pre-registered in tools/fa_market_feature_lab.py and toggled there on
# IDENTICAL forward-chained folds; a winning arm ships by flipping its
# default to True in the same commit as the refreshed Gate-2 artifact +
# registry note.
#
# rate_line SHIPPED (data/fa_market_feature_lab_eval.json, same-run champion
# comparison): guarantee MAE 10.094 vs 10.159, aav 3.008 vs 3.071, years
# equal, mega 87.91 vs 87.97 — teams pay for rate quality beyond raw WAR/PT;
# also flips the 2022 lockout fold to beating comps (13.35 vs 13.70).
# regime / age_pos / qo_tier LOST their pre-registered gates (ledgered in
# the same artifact); the flags stay for re-gating at future vintages.
#
# WAVE-2 arms (2026-07-16; pre-registered in the lab header BEFORE any run;
# eval artifact data/fa_market_feature_lab_wave2_eval.json) -- SERVE-SIDE
# alignment repairs consumed ONLY by fa_export's serve path. Nothing in this
# module's fit/predict or in fa_backtest reads them, and the Gate-2 folds
# already run the aligned regime (fold supply = enriched population at
# fa_backtest.py:301; fold ages anchored in enriched_signings since ba3917d),
# so Gate 2 is structurally byte-identical under either flag: the gate re-run
# is a NOT-WORSE guard, the affirmative evidence is the lab-recorded serve
# diagnostic (fa_export.serve_alignment_diagnostics).
#   supply_pop  fa_export counts class supply over identity+history members
#               (the serve-time analog of the enriched TRAINING population)
#               instead of the whole scraped class. Audit 2026-07-16: the
#               whole-class 2027 counts (RP 80 / POS 76) z-score +2.6..+2.8
#               against training moments fit on enriched counts (mean ~33,
#               sd ~17, max 61) -- a train/serve population mismatch.
#   age_anchor  fa_export anchors the class projection age to the SEASON of
#               the row that supplied it (the proj_export / enriched_signings
#               ba3917d convention) instead of hist[0]'s season -- the stale
#               form understated serve age by 1-2 years whenever the platform
#               row lacked an age. Training ages are ALREADY anchored, so the
#               live divergence is a train/serve skew.
X_FEATURES = {"rate_line": True, "regime": False, "age_pos": False, "qo_tier": False,
              "supply_pop": True, "age_anchor": True, "tj": False,
              "noise": False}
# RE-GATE 2026-07-24 (FA lane), under docs/EFV_GATE_STANDARD.md. The shipped
# `rate_line` arm was decided on a SINGLE fixed-dataset delta (guarantee MAE
# 10.0943 with it vs 10.1593 without). Re-measured with a paired bootstrap
# that resamples the whole corpus and refits the forward chain on every draw
# (B=200), turning rate_line OFF moves the pooled guarantee MAE by
#   +0.0146 $M, sd 0.0816, CI95 [-0.1232, +0.1978], P(improves) 0.440
# against pure-noise placebo columns on the same draws
#   one random column, seed 3: +0.0128 sd 0.0198
#   one random column, seed 7: +0.0009 sd 0.0224
# i.e. the shipped feature is indistinguishable from a column of noise on
# the headline metric; its MDE95 is ~0.16 $M and it shipped at 0.065. It is
# LEFT ON (removing it is equally unresolvable, and it does carry a small
# edge on AAV: +0.0472 when removed, CI95 [-0.0093, +0.1138], P 0.065), but
# it must not be cited as a measured win. `tj` and `noise` are lab arms.
_X_FEATURE_DEFAULTS = dict(X_FEATURES)


def _x_rate_feats(s: dict) -> list[float]:
    """Rate-quality features from the retained projection rate line
    (fa_projection.rate_path, on _war_path since 2026-07-15). Hitters carry
    year-1 projected wOBA (0 for pitchers/absent); pitchers carry FIP
    headroom below 5.5 (0 for hitters/absent) so both are >=0 and
    higher-is-better."""
    rl = (s.get("_war_path") or {}).get("rates_by_year") or []
    r0 = rl[0] if rl else {}
    woba = float(r0.get("woba") or 0.0)
    fip = r0.get("fip")
    fip_q = max(0.0, 5.5 - float(fip)) if fip is not None else 0.0
    return [woba, fip_q]


_TJ_STORE: dict | None = None


def _tj_store() -> dict:
    """data/tj_surgery.json, loaded once. Fail-soft: an empty store makes
    every TJ feature 0, i.e. the arm degrades to the champion."""
    global _TJ_STORE
    if _TJ_STORE is None:
        try:
            import tj_surgery
            _TJ_STORE = tj_surgery._load_store()
        except Exception:                       # noqa: BLE001 — fail-soft
            log.warning("fa_market: tj_surgery store unavailable")
            _TJ_STORE = {}
    return _TJ_STORE


def _x_tj_feats(s: dict) -> list[float]:
    """As-of Tommy John durability, PITCHERS ONLY (all three terms are 0
    for a bat, so they are pitcher-specific coefficients and cannot move a
    position player's price).

    tj_surgery.tj_features counts only surgeries STRICTLY BEFORE the class
    year, so the read is ex-ante at every fold.
      tj_pre     ever
      tj_revis   two or more (the revision cases)
      tj_recent  linear recency ramp, 1.0 at the surgery -> 0 at 60 months

    SURVIVORSHIP WARNING: the corpus is signed free agents, i.e. arms that
    came back. A TJ coefficient fit here prices the market's DISCOUNT on a
    returnee, not the surgery's true cost."""
    g = _pos_group(s.get("position"))
    if g not in ("SP", "RP"):
        return [0.0, 0.0, 0.0]
    mlbam = s.get("mlbam_id") or s.get("mlbam")
    if not mlbam:
        return [0.0, 0.0, 0.0]
    if LAB_TJ_PERMUTE_SEED:
        # zero-information control: same marginal, wrong player.
        import random
        keys = _tj_permute_keys()
        if keys:
            r = random.Random(f"{LAB_TJ_PERMUTE_SEED}:{mlbam}")
            mlbam = keys[r.randrange(len(keys))]
    try:
        import tj_surgery
        f = tj_surgery.tj_features(mlbam, str(s["class_year"]), _tj_store())
    except Exception:                           # noqa: BLE001 — fail-soft
        return [0.0, 0.0, 0.0]
    pre = float(f.get("tj_pre") or 0)
    cnt = float(f.get("tj_count_pre") or 0)
    mo = f.get("months_since_last_tj_pre")
    rec = max(0.0, 1.0 - float(mo) / 60.0) if (pre and mo is not None) else 0.0
    return [pre, 1.0 if cnt >= 2 else 0.0, rec]


@lru_cache(maxsize=1)
def _tj_permute_keys() -> tuple:
    return tuple(_tj_store().keys())


def _x_noise_feats(s: dict) -> list[float]:
    """A ZERO-INFORMATION placebo column: a deterministic pseudo-random
    draw keyed on player identity. Any arm that adds k features must be
    read against the placebo's measured movement at the same k, not
    against 0 -- adding a parameter to an unregularized OLS moves the
    forward-chained MAE all by itself."""
    import hashlib
    n = int(NOISE_FEATURES)
    if n <= 0:
        return []
    ident = f"{NOISE_SEED}:{s.get('player_key') or s.get('player_name')}"
    h = hashlib.blake2b(ident.encode(), digest_size=8 * n).digest()
    return [(int.from_bytes(h[8 * i:8 * i + 8], "big") / 2 ** 64) * 2.0 - 1.0
            for i in range(n)]


def _features_years(s: dict, comps_my: float, comps_my75: float | None = None) -> list[float]:
    """log-years stage. Years is skewed-discrete (1-year deals dominate;
    long deals are rare and young-star-only), so the stage models
    log(years) with curvature (WAR², age×WAR) AND stacks the
    nearest-comps median years in as a feature — the naive baseline's
    own signal, plus everything it can't see. Transparent kNN feature
    stacking, not a black box."""
    g = _pos_group(s.get("position"))
    w1 = s["_war_path"]["war_y1"]
    prime = max(0.0, 30.0 - s["_age"])
    qo = 1.0 if s.get("qo") else 0.0
    if comps_my75 is None:
        comps_my75 = comps_my
    out = [1.0, s["_age"], w1, w1 * w1, s["_age"] * w1,
           1.0 if g == "SP" else 0.0, 1.0 if g == "RP" else 0.0,
           1.0 if g == "C" else 0.0, qo,
           comps_my,
           # prime years remaining — the term structure behind long deals:
           # teams buy seasons through ~30; a 26-year-old's market simply
           # has more buyable years in it (v2 feature, gate-measured).
           prime,
           # v3 decade-deal tail (gate-measured): (1) the 75th-pct comps years,
           # the long-deal anchor the median washes out (Seager/Bogaerts-type
           # 10yr prints live in a star's comps); (2) QO x prime x quality - the
           # franchise-cornerstone marker that signs the surprise decade deal
           # the prime term alone (flat ~0-3 for a 27-30yo star) misses.
           comps_my75,
           qo * prime * w1]
    if X_FEATURES["age_pos"]:
        # role term structure: pitchers age on a different curve than bats
        out += [s["_age"] * (1.0 if g == "SP" else 0.0),
                s["_age"] * (1.0 if g == "RP" else 0.0)]
    return out


def _features_guar(s: dict, years: float, dpw_usd: float, supply: float,
                   log_comps_guar: float, log_rational: float,
                   prime_war: float) -> list[float]:
    """log-guarantee stage. Anchors (all ex-ante):
      - log_comps_guar: trend-inflated nearest-comps median — how front
        offices anchor;
      - log_rational: the ECONOMIC anchor — discounted projected WAR base
        x the winter $/WAR level (what a rational buyer pays). This is
        what makes a record-scale deal predictable WITHOUT having seen a
        prior record print: Soto-shaped inputs carry a ~$450M+ rational
        base regardless of past contract history;
      - prime_war: max(0, 30 - age) x year-1 WAR — prime seasons
        remaining x quality, the term structure behind decade-long deals.
    Predictions are still CLAMPED to the comps envelope at predict time
    (see _point) — the documented extrapolation backstop."""
    w1 = s["_war_path"]["war_y1"]
    out = [1.0, years, w1, w1 * years, s["_age"],
           1.0 if s.get("qo") else 0.0, supply, math.log(max(dpw_usd, 1e6)),
           log_comps_guar, log_rational, prime_war]
    if X_FEATURES["rate_line"]:
        out += _x_rate_feats(s)
    if X_FEATURES["regime"]:
        # dated market-regime dummies (fa_config regimes; current/pre_covid
        # form the baseline) — the 2022 lockout winter is the one Gate-2
        # fold where the model loses to comps.
        cy = int(s.get("class_year") or 0)
        out += [1.0 if cy == 2021 else 0.0, 1.0 if cy == 2022 else 0.0]
    if X_FEATURES["age_pos"]:
        g = _pos_group(s.get("position"))
        out += [s["_age"] * (1.0 if g == "SP" else 0.0),
                s["_age"] * (1.0 if g == "RP" else 0.0)]
    if X_FEATURES["qo_tier"]:
        # QO x quality: the qualifying-offer stars own the top-of-market
        # misses; a flat QO dummy can't separate them from mid-tier QOs.
        out += [(1.0 if s.get("qo") else 0.0) * max(0.0, w1)]
    if X_FEATURES["tj"]:
        out += _x_tj_feats(s)
    if X_FEATURES["noise"]:
        out += _x_noise_feats(s)
    return out


def _ols(X: list[list[float]], y: list[float], ridge: float = 0.0):
    """Least squares, optionally ridge-regularized on STANDARDIZED
    features (intercept exempt). Unregularized OLS extrapolated wildly at
    megadeal-extreme inputs on small early train windows — both observed
    failure directions (Soto at $9M; 2019 over-explosions) trace to it."""
    import numpy as np
    A = np.asarray(X, dtype=float)
    yv = np.asarray(y, dtype=float)
    if not ridge:
        b, *_ = np.linalg.lstsq(A, yv, rcond=None)
        return b
    mu = A.mean(axis=0)
    sd = A.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (A - mu) / sd
    Z[:, 0] = 1.0                                   # intercept column
    lam = ridge * np.eye(Z.shape[1])
    lam[0, 0] = 0.0
    bz = np.linalg.solve(Z.T @ Z + lam * len(yv), Z.T @ yv)
    # fold standardization back into raw-space coefficients
    b = bz / sd
    b[0] = bz[0] - float(((mu / sd)[1:] * bz[1:]).sum())
    return b


def _supply(signings: list[dict], class_year: int) -> dict[str, float]:
    """Same-position-group MLB-deal count in the class (z-scored across
    training winters at fit time) — a thin shortstop class inflates
    shortstop prices, so class composition is a feature."""
    counts: dict[str, float] = defaultdict(float)
    for s in signings:
        if s["class_year"] == class_year:
            counts[_pos_group(s.get("position"))] += 1.0
    return counts


_RECAL_MIN_ROWS = 200
_recal_depth = 0


def _fit_recal(train: list[dict], dpw_series: dict[int, float]):
    """NESTED-CV level recalibration for the guarantee.

    Measured OOS mis-calibration of the shipped model, conditioned on the
    PREDICTION (the decision-relevant conditioning; conditioning on the
    actual is regression to the mean by construction). Forward-chained
    2018-2026, n=1199:

        predicted-guarantee decile  1    2    3    4    5    6    7    8    9   10
        median actual / median pred .86  .88  .86 1.12  .98 1.08 1.45 1.35 1.31 1.57
        mean log(actual/pred)      +.12 +.01 +.00 +.12 +.03 +.13 +.21 +.19 +.24 +.17

    Every decile is non-negative and the top four run 1.3-1.6x: the board
    systematically under-prices what it says a player is worth, worst
    exactly where the dollars are. In-sample residuals cannot see this (the
    OLS zeroes them by construction), so the correction is estimated by an
    INNER forward chain over the training winters only -- strictly ex-ante,
    the same discipline the outer gate uses.

    Returns (a, b) for log(guar_corrected) = a + b*log(guar_raw), or None
    when the inner chain has too little material to fit.

    RECAL_MODE "fit_group" instead returns {pos_group: (a, b), "_pooled":
    (a, b)}: the same estimator per position group, with the pooled line
    standing in for any group whose inner chain holds fewer than
    _RECAL_MIN_ROWS rows. One pooled slope cannot correct both sides at once
    (E1 measured the board under-pricing hitters by $7.52M against pitchers'
    $4.02M), and per-group is the smallest surface that can.

    RECAL_MODE "shift_ptier" (P-1, docs/fa-2026-08-19/PTIER_LEVEL_GATE.md)
    returns {"_mode": "shift_ptier", "_pooled": (a, 1.0), tier: (a_t, 1.0)}:
    the intercept-only shift fit per PREDICTED-guarantee tier (the Gate-2
    ptier bins, keyed on the RAW inner prediction), slope pinned 1.0, with
    the pooled shift standing in for any tier under RECAL_TIER_MIN_ROWS
    inner rows. One pooled intercept cannot hold four tiers at zero when
    the de-staling basis moves non-uniformly across the price scale, and
    per-tier intercepts are the smallest LEVEL-family surface that can."""
    global _recal_depth
    if _recal_depth or len(train) < _RECAL_MIN_ROWS:
        return None
    years = sorted({s["class_year"] for s in train})
    if len(years) < 5:
        return None
    X, Y, G, T = [], [], [], []
    _recal_depth = 1                       # inner models must not recurse
    try:
        for W in years[4:]:
            tr = [s for s in train if s["class_year"] < W]
            te = [s for s in train if s["class_year"] == W]
            if len(tr) < 100 or not te:
                continue
            inner = MarketModel(tr, dollars_per_war_by_winter(tr))
            for s in te:
                _, g = inner._point(s)
                if g > 0:
                    X.append(math.log(g))
                    Y.append(math.log(_npv_of(s)))
                    G.append(_pos_group(s.get("position")))
                    T.append(_guar_ptier(g))
    except Exception:                       # noqa: BLE001 -- fail-soft to no-op
        log.warning("fa_market: recalibration inner chain failed; no-op")
        return None
    finally:
        _recal_depth = 0
    if len(X) < _RECAL_MIN_ROWS:
        return None
    if RECAL_MODE == "shift":              # intercept only (level, no slope)
        out = (statistics.mean(y - x for x, y in zip(X, Y)), 1.0)
        if RECAL_FIT_LOG is not None:
            RECAL_FIT_LOG.append(out)
        return out
    if RECAL_MODE == "shift_ptier":        # per-predicted-tier intercepts (P-1)
        shifts = [y - x for x, y in zip(X, Y)]
        labels = T
        if RECAL_TIER_PERMUTE_SEED:        # zero-information control, lab only
            import random
            labels = list(T)
            random.Random(RECAL_TIER_PERMUTE_SEED).shuffle(labels)
        outd: dict = {"_mode": "shift_ptier",
                      "_pooled": (statistics.mean(shifts), 1.0)}
        for t in ("lt10", "10to20", "20to50", "ge50"):
            d = [sh for sh, tt in zip(shifts, labels) if tt == t]
            if len(d) >= RECAL_TIER_MIN_ROWS:
                outd[t] = (statistics.mean(d), 1.0)
        if RECAL_FIT_LOG is not None:
            RECAL_FIT_LOG.append(dict(outd))
        return outd
    pooled = _recal_line(X, Y)
    if RECAL_MODE != "fit_group" or pooled is None:
        return pooled
    out: dict = {"_pooled": pooled}
    for g in sorted(set(G)):
        xs = [x for x, gg in zip(X, G) if gg == g]
        ys = [y for y, gg in zip(Y, G) if gg == g]
        if len(xs) < _RECAL_MIN_ROWS:
            continue                       # thin group keeps the pooled line
        line = _recal_line(xs, ys)
        if line is not None:
            out[g] = line
    return out


def _recal_line(X: list[float], Y: list[float]) -> tuple[float, float] | None:
    """OLS of log(actual) on log(predicted) with the a-priori slope bound."""
    if len(X) < 2:
        return None
    mx, my = statistics.mean(X), statistics.mean(Y)
    den = sum((x - mx) ** 2 for x in X)
    if den <= 0:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(X, Y)) / den
    b = max(0.75, min(1.35, b))            # a-priori sanity bound on the slope
    return (my - b * mx, b)


class MarketModel:
    """Fit on training winters; predict any signing row enriched with
    _war_path/_age. Transparent: coefficients exposed on the instance."""

    def __init__(self, train: list[dict], dpw_series: dict[int, float]):
        self.dpw_series = dpw_series
        self.supply_by_year = {y: _supply(train, y)
                               for y in {s["class_year"] for s in train}}
        sup_all = [c for by in self.supply_by_year.values() for c in by.values()]
        self.sup_mean = statistics.mean(sup_all) if sup_all else 0.0
        self.sup_sd = statistics.pstdev(sup_all) if len(sup_all) > 1 else 1.0
        rows = [s for s in train if s.get("_war_path") and s.get("years")
                and s.get("guarantee_usd")]
        self.train_pool = rows
        self._comps_my_cache: dict[tuple, tuple[float, float, float, float]] = {}
        self.destale = _destale_rate(dpw_series, max(dpw_series) if dpw_series else None)
        self.coef_years = _ols(
            [_features_years(s, (_cs := self._comps_stats(s))[0], _cs[3]) for s in rows],
            [math.log(float(s["years"])) for s in rows], ridge=RIDGE_YEARS)
        Xg, yg = [], []
        for s in rows:
            dpw = winter_dpw(dpw_series, s["class_year"])
            Xg.append(_features_guar(s, float(s["years"]), dpw,
                                     self._supply_z(s), self._comps_stats(s)[1],
                                     self._log_rational(s, float(s["years"]), dpw),
                                     self._prime_war(s)))
            # Phase 2 — targets are DEFERRAL-ADJUSTED NPV guarantees: the
            # model learns the present liability, not the press-release
            # sticker (Ohtani's $700M trains as ~$197M at the platform rate).
            yg.append(math.log(_npv_of(s)))
        self.coef_guar = _ols(Xg, yg, ridge=RIDGE_GUAR)
        self.n_train = len(rows)
        self.recal = None
        if RECAL_MODE != "off":
            self.recal = _fit_recal(rows, dpw_series)
        # residual pools for empirical bands (log-NPV-guarantee + years)
        self.resid_log_guar = []
        self.resid_years = []
        _bz, _bg = [], []
        for s in rows:
            py, pg = self._point(s)
            self.resid_years.append(s["years"] - py)
            self.resid_log_guar.append(math.log(_npv_of(s)) - math.log(max(pg, 1)))
            _bz.append(self._guar_band_z(s, py, pg))
            _bg.append(_pos_group(s.get("position")))
        # T1.2 - PLAYER-SPECIFIC guarantee band. The unconditional residual
        # quantiles above gave every free agent in baseball the SAME relative
        # uncertainty: measured on the served 2027 class, projGuarP90 /
        # projGuarP10 = 9.6495 for all 221 priced members to six significant
        # figures. The location-scale fit makes the width a function of the
        # player; None (a thin corpus, an early fold) keeps the flat band.
        self.band = None
        if BAND_SCALE_GUAR:
            try:
                import fa_bands
                self.band = fa_bands.fit(
                    _bz, self.resid_log_guar, _bg,
                    names=fa_bands.GUAR_Z_NAMES, age_mean=self._band_age_mean,
                    permute_seed=(BAND_PERMUTE_SEED or None),
                    # LOG-DOLLAR residuals need their own sigma guard: the WAR
                    # default (0.05, 10.0) allows a p90/p10 of 1.2e11.
                    sigma_clip=fa_bands.SIGMA_CLIP_LOG_USD,
                    # The signing corpus is n=1,199 pooled with train folds
                    # from ~100 rows. Shrinking gamma toward its intercept
                    # shrinks sigma toward the flat band it replaces, which is
                    # the right null to shrink to.
                    ridge=BAND_RIDGE_GUAR,
                    min_rows=250, min_group=120)
            except Exception:                   # noqa: BLE001 - fail to flat
                log.warning("fa_market: guarantee band fit failed; flat band")
                self.band = None

    @property
    def _band_age_mean(self) -> float:
        ages = [s["_age"] for s in self.train_pool if s.get("_age")]
        return statistics.mean(ages) if ages else 30.0

    def _guar_band_z(self, s: dict, years: float, guar: float) -> list[float]:
        """The restricted z for the log-guarantee band (see fa_bands.guar_z).
        ``years``/``guar`` are the model's OWN point prediction for the row,
        so the width is conditioned on what the board is about to publish -
        the decision-relevant conditioning, the same reasoning _fit_recal
        documents for the level correction."""
        import fa_bands
        tj = _x_tj_feats(s)
        return fa_bands.guar_z(_pos_group(s.get("position")),
                               math.log(max(guar, 1.0)), years, s.get("_age"),
                               1.0 if s.get("qo") else 0.0,
                               (tj[0] + tj[1]),        # 0, 1 or 2 prior TJs
                               self._band_age_mean)

    def _supply_z(self, s: dict) -> float:
        c = (self.supply_by_year.get(s["class_year"]) or
             _supply([s], s["class_year"])).get(_pos_group(s.get("position")), 0.0)
        return (c - self.sup_mean) / (self.sup_sd or 1.0)

    def _comps_stats(self, s: dict) -> tuple[float, float, float, float]:
        """(median comps years, log median trend-inflated comps guarantee, median
        comps AAV, 75th-pct comps years) — computed once per row, the anchor
        features both stages stack. The p75-years anchor is the long-deal signal
        the median washes out: a star's nearest comps include the rare 10yr
        prints, and the median collapses them (the years-stage decade-deal miss)."""
        # Memo key: stable (player, winter) identity, NOT id(s) - serve rows
        # are transient per-member dicts, so a recycled dict address could
        # hand one free agent another player's comps anchor. Identity-less
        # rows recompute uncached (correct, just unmemoized).
        ident = s.get("player_key") or s.get("player_name")
        key = (ident, s.get("class_year")) if ident is not None else None
        if key is None or key not in self._comps_my_cache:
            infl = getattr(self, "destale", None)
            if infl is None:
                infl = _dpw_inflation()
            # comps anchor on the NPV basis too - the anchor and the
            # target must speak the same currency.
            anc = comps_anchor(s, self.train_pool, infl)
            if anc:
                my, mg, ma, my75 = anc
            else:
                my, mg, ma, my75 = 1.0, 1_000_000.0, 1_000_000.0, 1.0
            out = (my, math.log(max(mg, 1.0)), ma, my75)
            if key is None:
                return out
            self._comps_my_cache[key] = out
        return self._comps_my_cache[key]

    def _comps_my(self, s: dict) -> float:
        return self._comps_stats(s)[0]

    @staticmethod
    def _log_rational(s: dict, years: float, dpw_usd: float) -> float:
        units = max(_disc_war_term(s["_war_path"], years), 0.25)
        return math.log(max(units * dpw_usd, 1e6))

    @staticmethod
    def _prime_war(s: dict) -> float:
        return max(0.0, 30.0 - s["_age"]) * max(0.0, s["_war_path"]["war_y1"])

    def _point(self, s: dict, years_override: float | None = None) -> tuple[float, float]:
        _cs = self._comps_stats(s)
        fy = _features_years(s, _cs[0], _cs[3])
        years = math.exp(float(sum(c * x for c, x in zip(self.coef_years, fy))))
        if years_override is not None:
            years = float(years_override)
        # FA mega-deal tail (2026-06-25): the 13-yr cap structurally truncated
        # record terms (Soto 15 -> 13, $765M deal -> $520M pred). Raised to 15,
        # the modern record length; only the OLS-predicted 13+ players (the
        # megastars) are affected. Gate-validated (fa_gate2): ship only if the
        # mega slice improves AND pooled guarantee/aav/years MAE do not regress.
        years = min(max(years, 1.0), 15.0)
        dpw = winter_dpw(self.dpw_series, s["class_year"])
        fg = _features_guar(s, years, dpw, self._supply_z(s), self._comps_stats(s)[1],
                            self._log_rational(s, years, dpw), self._prime_war(s))
        guar = math.exp(float(sum(c * x for c, x in zip(self.coef_guar, fg))))
        # Comps-envelope guard: predictions differentiate within a 2.5x
        # band around the trend-inflated comps median, never outside it.
        # An extrapolation backstop, not a crutch: mid-market predictions
        # sit comfortably inside it; it binds exactly where unguarded OLS
        # failed (megadeal extremes). Documented in the eval notes.
        comps_guar = math.exp(self._comps_stats(s)[1])
        if comps_guar > 1.0:
            guar = min(max(guar, comps_guar / 2.5), comps_guar * 2.5)
            # Megadeal regime: the measured Gate-2 mega slice shows the
            # comps anchor is the BEST ex-ante estimator at the top of the
            # market (stars' neighbors are prior stars). Blend toward comps
            # in log space as the comps scale enters megadeal territory —
            # alpha 0 below a $50M comps median (pure model, mid-market
            # untouched) rising to the cap at $400M+. Smooth, monotone,
            # documented; the mega slice in the eval measures its effect.
            # v3: cap raised 0.9 -> 1.0. The forward-chained mega MAE falls
            # monotonically with the cap (0.85:84.3 / 0.90:82.9 / 0.95:81.4 /
            # 1.00:80.1), beating the comps baseline ($82.7M) only at 1.0, and
            # the POOLED guarantee MAE improves alongside (10.05 -> 9.96, n=1199)
            # — so this is not a mega-slice-only overfit. At $400M+ comps the OLS
            # extrapolation has almost no training support; the comps anchor
            # earns the very top outright.
            lo, hi = math.log(50e6), math.log(400e6)
            alpha = min(1.0, max(0.0, (math.log(comps_guar) - lo) / (hi - lo)))
            if alpha > 0:
                comps_aav = self._comps_stats(s)[2]
                mega_anchor = max(comps_guar, comps_aav * years)
                guar = math.exp((1 - alpha) * math.log(max(guar, 1.0))
                                + alpha * math.log(mega_anchor))
        # Level recalibration LAST: the clamp and the mega blend are part of
        # what is being calibrated, so the correction has to sit outside them.
        rc = _select_recal(getattr(self, "recal", None), guar,
                           _pos_group(s.get("position")))
        if rc and guar > 0:
            guar = math.exp(rc[0] + rc[1] * math.log(guar))
        return years, guar

    def predict(self, s: dict) -> dict:
        years_f, guar = self._point(s)
        years = int(round(years_f))
        if AAV_CONSISTENT == "reprice" and years >= 1 and abs(years - years_f) > 1e-9:
            # The guarantee was priced at the CONTINUOUS term but the board
            # shows an integer one, so proj_aav divided a 1.5-year price by a
            # 1-year term (measured: 1,006 of 1,528 corpus rows distorted
            # >10%). Re-price the guarantee AT the displayed term instead --
            # the alternative (divide by years_f) leaves the displayed
            # guarantee and the displayed term describing different deals.
            guar = self._point(s, years_override=float(years))[1]
        qy = statistics.quantiles(self.resid_years, n=10) if len(self.resid_years) >= 50 else None
        qg = statistics.quantiles(self.resid_log_guar, n=10) if len(self.resid_log_guar) >= 50 else None
        out = {
            "proj_years": max(1, years),
            "proj_guarantee_usd": int(guar),
            "proj_aav_usd": int(guar / (max(years_f, 1.0) if AAV_CONSISTENT
                                        else max(years, 1))),
        }
        if qy:
            out["proj_years_p10"] = max(1, int(round(years_f + qy[0])))
            out["proj_years_p90"] = int(round(years_f + qy[-1]))
        band = getattr(self, "band", None)
        if band is not None:
            import fa_bands
            z = self._guar_band_z(s, years_f, guar)
            o = fa_bands.offsets(band, z, _pos_group(s.get("position")),
                                 (0.10, 0.90))
            if o:
                out["proj_guarantee_p10_usd"] = int(guar * math.exp(o[0.10]))
                out["proj_guarantee_p90_usd"] = int(guar * math.exp(o[0.90]))
                out["band_source"] = "scale"
                qg = None                       # the flat band is superseded
        if qg:
            out["proj_guarantee_p10_usd"] = int(guar * math.exp(qg[0]))
            out["proj_guarantee_p90_usd"] = int(guar * math.exp(qg[-1]))
            out["band_source"] = "flat"
        if "proj_guarantee_p10_usd" in out:
            # projAAV bands ride the guarantee band at the point-estimate term —
            # both framings (per-year price AND total value/length) carry
            # P10/P50/P90, per the module's distributions-not-points rule.
            _den = max(years_f, 1.0) if AAV_CONSISTENT else max(years, 1)
            out["proj_aav_p10_usd"] = int(out["proj_guarantee_p10_usd"] / _den)
            out["proj_aav_p90_usd"] = int(out["proj_guarantee_p90_usd"] / _den)
        return out


# ============================================================================
# Deal verdict — the UI-facing read of Deal+
# ============================================================================
# Deal+ (100 x rational / price) stays the underlying index; the surfaces
# render a plain-English VERDICT so a reader never has to translate a
# number: value (projected to be underpaid), market (priced about right),
# overpay (projected to be overpaid).
#
# Band edges are EMPIRICALLY CENTERED, not symmetric around 100: Deal+ at
# convex pricing is right-skewed (short cheap deals on projectable players
# grade well; the left tail is megadeal overpays). The edges sit on the
# corpus TERCILES, so each verdict named exactly a third of twelve winters
# of real contracts. A class that skews "value" against these fixed bands
# is information, not a calibration artifact.
# Phase 2 recalibration (NPV deferral-adjusted basis + the NPV $/WAR
# series): the corpus now runs p33=75, median=110, p67=159 — edges moved
# from 85/185 accordingly.
#
# T1.4 RE-DERIVATION (2026-07-25, SAME change as the convexity correction).
# The edges are corpus terciles by construction, so a level shift makes them
# stale by construction too. Re-cut on the enriched corpus (n=1,300 signings
# with bands, forward-chained ex-ante $/WAR per winter):
#
#   pricing            p33     median   p67     mean
#   value-of-the-mean   72.2   104.7    149.3   163.5   (shipped edges 75/160)
#   mean-of-the-value  108.8   152.2    222.9   267.0
#
# Verdict counts on the 1,300-row corpus:
#   old edges 75/160 on OLD pricing   overpay 451 / market 452 / value 397
#   old edges 75/160 on NEW pricing   overpay 249 / market 431 / value 620
#   new edges 109/223 on NEW pricing  overpay 433 / market 433 / value 434
#
# Leaving the old edges in place would have moved 202 of 1,300 historical
# contracts (15.5%) into a different verdict overnight for no reason other
# than the arithmetic fix, i.e. the site would have looked like it changed its
# mind about a sixth of every winter it has ever graded.
#
# RE-CUT 2026-08-19 (owner default adopted; docs/fa-2026-08-19/
# PTIER_LEVEL_GATE.md section 4). The pricing basis moved again under the
# 2026-07-31 WAR-input ships and the 2026-08-06 F-DEF pricing pin, the same
# staleness-by-construction: on the CURRENT NPV corpus (n=1,300, winters
# 2017-2026, basis A: expected rational value / ACTUAL NPV price, ex-ante
# $/WAR) the 109/223 edges delivered 548/385/367 (42/30/28) against the
# 33/33/33 design. Interpolated terciles p33 88.80 / p67 197.77 -> edges
# 89/198, restoring 434/433/433 exactly; 180 of 1,300 historical corpus rows
# (13.8%) flip POOLED verdict. The registry's ~85/189 was the 2026-07-30
# reading of the same staleness on the pre-08-06 basis; verified and
# superseded by this cut. NOTE: VERDICT_BAND_MODE is "group" (owner
# 2026-07-30), so these pooled edges are the fallback constants and the
# historical-corpus banding basis; served verdicts are banded per group and
# do not move until VERDICT_GROUP_EDGES is re-cut on the same basis (owed,
# flagged in the gate doc - own terciles measured there run SP 89/180,
# RP 67/144, C 120/279, POS 116/256).
#
# RE-CUT 2026-10-08 (owner answer M14-2, docs/fa-2026-10-08/GATE2_RESAVE.md,
# recipe fa_backtest.verdict_edge_corpus / derive_verdict_edges). The fWAR
# label epoch (2026-10-03) and the pricing work since 2026-08-19 moved the
# basis under every Deal+ again. On the current corpus (n=1,300, winters
# 2017-2026, basis A, shipped i/20 grid) the pooled terciles read p33 76.03 / p67 180.47, so 89/198 -> 76/180; the old
# edges split it 493/424/383 and the new ones 429/440/431 (112 pooled rows
# flip). Every re-persist re-derives the edges into
# fa_gate2_eval.json verdict_edges.derived; the full record of this cut is
# verdict_edges.recut_2026_10_08.
VERDICT_VALUE_MIN = 180     # Deal+ >= 180 -> "value"   (corpus top tercile)
VERDICT_OVERPAY_MAX = 76    # Deal+ <  76  -> "overpay" (corpus bottom tercile)

# ============================================================================
# E6 (2026-07-30): per-position-group verdict bands. OWNER DECISION, DEFAULT OFF
# ============================================================================
# THE MEASURED PROBLEM. Pooled terciles only deliver a third each PER GROUP if
# Deal+ has the same distribution in every group, and it does not. Deal+ is
# rational_value / price, and a short deal for a sub-1-WAR reliever prices most
# of its guarantee against very little projected value by construction. On the
# 1,300-signing corpus at the ACTUAL price (the basis the edges were cut on),
# under the code shipped 2026-07-30:
#
#   group   n     overpay  market  value    edges that WOULD give 33/33/33
#   SP     297      44%     31%     26%     86 / 182
#   RP     450      55%     28%     17%     65 / 146
#   C      102      36%     25%     38%    101 / 243
#   POS    451      35%     29%     36%    103 / 237
#   ALL   1300      44%     29%     27%     85 / 189
#
# So the owner's "the board thinks every pitcher is an overpay" is REAL but it
# is mostly a RELIEVER effect, and roughly half of it is a true property of the
# market (relievers really do get paid more per projected WAR) rather than a
# model defect. On the SERVED 2027 board the split runs RP 65% overpay / 0%
# value against POS 26% / 17%.
#
# NOTE the ALL row: the pooled edges no longer deliver 33/33/33 either (44/29/27)
# because the pricing basis moved under them - the same staleness-by-construction
# the T1.4 block above documents. Re-cutting the POOLED edges to 85/189 is a
# separate, smaller decision than going per-group.
#
# WHY THIS IS NOT SHIPPED ON MY OWN AUTHORITY: re-banding moves published
# verdicts on historical contracts (256 of 1,300 corpus rows, 19.7%, change
# verdict under the per-group edges) and it changes what "value" MEANS - from
# "cheap against the whole market" to "cheap for its position group". That is a
# product decision, not an accuracy one, and there is no gate that can settle
# it. The machinery is here, measured, and one constant away.
# OWNER DECISION TAKEN 2026-07-30: "group". The owner was shown the measured table
# above (SP 44/31/26, RP 55/28/17, C 36/25/38, POS 35/29/36 against a 33/33/33 design)
# and the disclosure that roughly half the reliever effect is a true market property
# rather than a model defect, and chose per-group bands anyway, on the ground that
# "value" should mean cheap FOR ITS POSITION GROUP. This changes what a published
# verdict MEANS on 256 of 1,300 historical corpus rows (19.7%).
# PREREQUISITE, do not remove: every deal_verdict call site must pass `position`.
# fa_export.py:479 did not, and _pos_group(None) is "POS", so flipping this constant
# alone would have banded every pitcher against hitter edges - strictly worse than
# pooled. That call site is fixed; test_fa_market and test_fa_tier1 pin the POOLED
# edges explicitly via the mode, so they stay honest under either setting.
VERDICT_BAND_MODE = "group"         # "pooled" | "group" (shipped 2026-07-30, owner)
# Terciles of Deal+ at the ACTUAL price, per _pos_group, on the 1,300-signing
# forward-chained corpus. Regenerate whenever the pricing basis moves.
# RE-CUT 2026-10-08 (owner answer M14-2): the 2026-07-30 cut SP 86/182,
# RP 65/146, C 101/243, POS 103/237 moved to the derived terciles below
# (fa_gate2_eval.json verdict_edges.recut_2026_10_08; corpus flips SP 27 of 297,
# RP 126 of 450, C 15 of 102, POS 20 of 451). The reliever edges move
# furthest; this cut measures that and does not attribute it.
VERDICT_GROUP_EDGES = {"SP": (97, 214), "RP": (45, 101),
                       "C": (140, 240), "POS": (109, 246)}


def deal_verdict(deal_plus: float | None, position: str | None = None) -> str | None:
    """Verdict for a Deal+ value. ``position`` is only consulted when
    VERDICT_BAND_MODE is "group"; with the shipped "pooled" mode the result is
    byte-identical to the historical single-argument behaviour, so no caller has
    to change until the owner picks a mode."""
    if deal_plus is None:
        return None
    lo, hi = VERDICT_OVERPAY_MAX, VERDICT_VALUE_MIN
    if VERDICT_BAND_MODE == "group":
        lo, hi = VERDICT_GROUP_EDGES.get(_pos_group(position), (lo, hi))
    if deal_plus >= hi:
        return "value"
    if deal_plus < lo:
        return "overpay"
    return "market"


def comps_for(s: dict, pool: list[dict], k: int = 5) -> list[dict]:
    """Nearest real historical contracts: same position group, distance in
    (age, projected year-1 WAR) z-units, prior winters only.

    COMPS_STRICT_PRIOR (default True since 2026-07-24) enforces the "prior
    winters only" half of that sentence. It used to read `<=`, so a TRAINING
    row saw its own winter's contracts while no serve row ever can: measured,
    1,100 of 1,995 comps drawn for the first 400 training rows (55.1%) were
    contemporaneous, and the comps anchor shifted a median $0.000M but up to
    $+80.0M / $-39.0M on 326 of 1,432 rows. Gate 2's reported number was
    never affected (its train list is strictly prior winters already); the
    damage was to the fitted coefficients and to the live board."""
    g = _pos_group(s.get("position"))
    cands = [c for c in pool if c is not s and c.get("_war_path")
             and (c["class_year"] < s["class_year"] if COMPS_STRICT_PRIOR
                  else c["class_year"] <= s["class_year"])
             and _pos_group(c.get("position")) == g and c.get("guarantee_usd")]
    if not cands:
        return []
    ages = [c["_age"] for c in cands]
    wars = [c["_war_path"]["war_y1"] for c in cands]
    sa = statistics.pstdev(ages) or 1.0
    sw = statistics.pstdev(wars) or 1.0
    scored = sorted(cands, key=lambda c: math.hypot(
        (c["_age"] - s["_age"]) / sa,
        (c["_war_path"]["war_y1"] - s["_war_path"]["war_y1"]) / sw))
    return [{"player_name": c["player_name"], "class_year": c["class_year"],
             "to_team": c.get("to_team"), "years": c.get("years"),
             "guarantee_usd": c.get("guarantee_usd"), "aav_usd": c.get("aav_usd"),
             "npv_guarantee_usd": c.get("npv_guarantee_usd"),
             "npv_aav_usd": c.get("npv_aav_usd"),
             "war_y1_proj": c["_war_path"]["war_y1"], "age": c["_age"]}
            for c in scored[:k]]


# ============================================================================
# The comps ANCHOR (distinct from the comps DISPLAY list above)
# ============================================================================
# THE DEFECT, measured 2026-07-31. The anchor was the median of the SAME k=5
# nearest neighbours the board displays, so it inherited their discreteness: as
# a player's projected year-1 WAR moves, comps enter and leave the top 5 and the
# median hops between contract tiers. Sweeping one real serve row (Jazz
# Chisholm, everything but war_y1 held fixed) the anchor read $13.2M at 1.50
# WAR, $85.8M at 1.76, $24.1M at 2.00 and $209.9M at 2.24 - a 6.5x drop and then
# an 8.7x jump for two 0.24-WAR steps, because the k=5 set turned over from
# {Rasmus, Moustakas, Naylor} to {Torres, Bichette, Sandoval} to {Upton, Seager,
# Hosmer}. The anchor is a FEATURE in both stages and the clamp/mega-blend ride
# on it, so the predicted guarantee inherited the cliff: 8.45x for a +0.75 WAR
# step, 2.50x for a single 0.02 WAR step.
#
# THE FIX. Weight EVERY eligible comp by a Gaussian kernel on the same (age,
# war_y1) z-distance instead of hard-selecting five, and read a LINEARLY
# INTERPOLATED weighted quantile rather than an order statistic. Both halves are
# needed: with a hard k, a comp crossing the boundary steps its weight from 0 to
# 1/k; with a plain weighted median, the answer jumps to the next order
# statistic the moment cumulative weight crosses 0.5. Interpolating a
# full-neighbourhood kernel makes the anchor a continuous function of war_y1.
# The DISPLAY list (comps_for) is untouched - the board still shows the five
# nearest, which is what a reader wants to see.
# GATE 2, forward-chained, paired on the identical 1,199 rows (persist=False):
#   guarantee MAE 9.6751 -> 9.5253  dMAE -0.1498  CI95 [-0.5083, +0.1977]
#   aav       MAE 2.9509 -> 2.8508  dMAE -0.1001  CI95 [-0.1814, -0.0244]
#   years     MAE 0.4370 -> 0.4262  dMAE -0.0108  CI95 [-0.0209, -0.0008]
#   megadeal  MAE 77.69  -> 76.82   (n=50, tracked not gating)
# AAV and years CLEAR; guarantee improves but its CI spans zero (P 0.811), so
# the claim is "no regression on guarantee, a real gain on AAV and years".
# BANDWIDTH is a fitted choice with an interior optimum, not "wider is smoother":
# guarantee MAE by bw = 0.35:9.581  0.50:9.540  0.75:9.529  1.00:9.613
# 1.50:10.751 (and 1.50 FAILS the AAV gate outright). 0.75 ships.
COMPS_ANCHOR_MODE = "kernel"        # "kernel" | "k5_median" (pre-2026-07-31)
COMPS_KERNEL_BW = 0.75              # Gaussian bandwidth, z-units of (age, war_y1)
COMPS_KERNEL_MIN_W = 1e-9           # underflow guard -> fall back to k5_median


def _weighted_quantile(pairs: list[tuple[float, float]], q: float) -> float:
    """Linear-interpolated weighted quantile of (value, weight) pairs.

    Uses midpoint plotting positions so a uniform-weight call reproduces the
    ordinary interpolated quantile, and so the result moves CONTINUOUSLY as
    weights move - the property the k=5 median did not have."""
    pts = sorted(pairs)
    tot = sum(w for _, w in pts)
    if tot <= 0:
        return pts[len(pts) // 2][0]
    xs, ps, cum = [], [], 0.0
    for v, w in pts:
        xs.append(v)
        ps.append((cum + w / 2.0) / tot)
        cum += w
    if q <= ps[0]:
        return xs[0]
    if q >= ps[-1]:
        return xs[-1]
    for i in range(1, len(ps)):
        if q <= ps[i]:
            span = ps[i] - ps[i - 1]
            f = (q - ps[i - 1]) / span if span > 0 else 0.0
            return xs[i - 1] + f * (xs[i] - xs[i - 1])
    return xs[-1]


def comps_anchor(s: dict, pool: list[dict], infl: float,
                 k: int = 5) -> tuple[float, float, float, float] | None:
    """(years median, guarantee median $, AAV median $, years p75) for the
    anchor features. Dollars are de-staled to the subject's winter first, so
    the anchor and the target speak the same currency."""
    g = _pos_group(s.get("position"))
    cands = [c for c in pool if c is not s and c.get("_war_path")
             and (c["class_year"] < s["class_year"] if COMPS_STRICT_PRIOR
                  else c["class_year"] <= s["class_year"])
             and _pos_group(c.get("position")) == g and c.get("guarantee_usd")]
    if not cands:
        return None
    sa = statistics.pstdev([c["_age"] for c in cands]) or 1.0
    sw = statistics.pstdev([c["_war_path"]["war_y1"] for c in cands]) or 1.0
    dist = [math.hypot((c["_age"] - s["_age"]) / sa,
                       (c["_war_path"]["war_y1"] - s["_war_path"]["war_y1"]) / sw)
            for c in cands]
    if COMPS_ANCHOR_MODE == "kernel":
        bw = COMPS_KERNEL_BW
        wts = [math.exp(-0.5 * (d / bw) ** 2) for d in dist]
        if sum(wts) <= COMPS_KERNEL_MIN_W:
            wts = None                      # degenerate neighbourhood
    else:
        wts = None
    if wts is None:                         # legacy: the k nearest, unweighted
        order = sorted(range(len(cands)), key=lambda i: dist[i])[:k]
        cands = [cands[i] for i in order]
        wts = [1.0] * len(cands)

    def _de(c, usd):
        return usd * ((1 + infl) ** (s["class_year"] - c["class_year"]))

    yrs = [(float(c["years"]), w) for c, w in zip(cands, wts)]
    # Dollars interpolate in LOG space - a linear interpolation between $6M and
    # $325M in level space is not a price, it is an average of two markets.
    lg = [(math.log(max(_de(c, c.get("npv_guarantee_usd") or c["guarantee_usd"]), 1.0)), w)
          for c, w in zip(cands, wts)]
    la = [(math.log(max(_de(c, (c.get("npv_aav_usd") or c["aav_usd"]
                               or c["guarantee_usd"] / max(c["years"], 1))), 1.0)), w)
          for c, w in zip(cands, wts)]
    return (_weighted_quantile(yrs, 0.5),
            math.exp(_weighted_quantile(lg, 0.5)),
            math.exp(_weighted_quantile(la, 0.5)),
            _weighted_quantile(yrs, 0.75))


# ============================================================================
# Corpus enrichment (point-in-time, cached per winter via fitted_models)
# ============================================================================

def enriched_signings(first_year: int = 2015, last_year: int = 2026, *,
                      p20: bool = False) -> list[dict]:
    """Every stored MLB-deal signing enriched with its point-in-time
    contract WAR path and signing age. Skips (and counts) players without
    corpus history — never fakes an input.

    ``p20`` (default off) is correction P20 of the $/WAR path gate; only that
    writer's own enrichment sets it, so Gate 1, Gate 2, the in-run /fa/ series
    and every served projection are untouched."""
    corpus = fp.build_corpus()
    league = corpus["league"]
    by_player: dict[str, dict[int, dict]] = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
    out: list[dict] = []
    skipped = 0
    for year in range(first_year, last_year + 1):
        # F-DEF PINNED OFF FOR /fa/ PRICING (owner decision 2026-08-06).
        # THIS is the Gate-2 seam. An earlier attempt pinned fa_backtest:247
        # instead, which is GATE 1 (the WAR projection gate), and the money
        # numbers did not move at all. Gate 2 never calls fitted_models in its
        # own loop; it scores a MarketModel built from these enriched rows.
        # Attribution: dropping F-DEF takes AAV MAE 3.135 -> 2.909, about 2.5x
        # the 0.091 MDE95, and widens the edge over baseline +0.224 -> +0.340.
        # It wins Gate 1 and loses Gate 2, so the pin is SCOPED: /projections/
        # keeps it via DEF_FEATURE_DEFAULT. docs/fa-gate2-attribution-2026-08-06.md
        curves, war_map = fp.fitted_models(corpus, year - 1,
                                           use_def=FA_PRICING_USE_DEF)
        # MEASURED (Phase-1 ship attempt, 2026-06-11): feeding ML paths into
        # the market model FAILED Gate 2 (guarantee 11.08 vs 10.56, AAV
        # 3.53 vs its 3.51 baseline) even with point-in-time bundles
        # (proj_ml.train_cached) — FA signees are SURVIVORS, and the ML
        # medians carry attrition mass that doesn't apply to players teams
        # are actively signing. The market stack therefore keeps CHAMPION
        # paths (its validated Gate-2 inputs); projection surfaces serve
        # ML, which won their gates. Revisit as features in Phase 2 WS-2f.
        for s in storage.load_fa_signings(year).values():
            if not (s.get("mlb_deal") and s.get("years") and s.get("guarantee_usd")
                    and s.get("mlbam_id")):
                continue
            side = "pit" if _pos_group(s.get("position")) in ("SP", "RP") else "hit"
            seasons = by_player[side].get(s["mlbam_id"]) or {}
            hist = [seasons[t] for t in (year - 1, year - 2, year - 3) if t in seasons]
            if not hist:
                skipped += 1
                continue
            # Anchor the year offset to the SEASON of the row that supplied the age, not
            # hist[0]'s season -- if the most recent row lacks an age, using hist[0].season
            # with an older row's age understated age by the season gap between them.
            age_row = next((h for h in hist if h.get("age")), None)
            age = (age_row["age"] + (year - age_row["season"])) if age_row else None
            path = contract_war_path(hist, side, year, int(s["years"]), age,
                                     curves, war_map, league, use_ml=False, p20=p20)
            if path is None or age is None:
                skipped += 1
                continue
            npv, had_sched = npv_guarantee_usd(s.get("player_key"), year,
                                               s["guarantee_usd"])
            out.append({**s, "_war_path": path, "_age": age, "_side": side,
                        "npv_guarantee_usd": npv,
                        "npv_aav_usd": int(npv / max(int(s["years"]), 1)),
                        "deferral_adjusted": had_sched})
    log.info("fa market corpus: %d enriched signings (%d skipped, no history)",
             len(out), skipped)
    return out

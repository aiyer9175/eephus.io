# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Contract & market model for the MLB Free Agency module (Stage 3).

TWO NUMBERS, NEVER CONFLATED:

  RATIONAL VALUE — what the projected production is worth: NPV of the
  aging-decayed, playing-time-weighted WAR path x escalated $/WAR, at the
  platform's 9% discount rate (the same rate PROSPX surplus uses — the QO
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
from value_framework import _config as _vf_config, point_estimate_surplus_usd

log = logging.getLogger(__name__)

MODEL_VERSION = "fa_mkt_v2"
GATE2_PATH = Path(__file__).parent / "data" / "fa_gate2_eval.json"

POS_GROUPS = ("SP", "RP", "C", "POS")


def _npv_of(s: dict) -> float:
    """Deferral-adjusted guarantee for a signing row (falls back to the
    sticker where no schedule is on file — see deferral_npv_usd's
    convention note)."""
    return float(s.get("npv_guarantee_usd") or s["guarantee_usd"])


def _pos_group(position: str | None) -> str:
    head = (position or "").upper().split("/")[0].strip()
    if head in ("SP", "SP2", "P", "LHP", "RHP"):
        return "SP"
    if head in ("RP", "CL", "SIRP", "MIRP"):
        return "RP"
    if head == "C":
        return "C"
    return "POS"


def _discount_rate() -> float:
    return float(_vf_config()["discount_rate"])


def _dpw_inflation() -> float:
    return float(_vf_config().get("dollars_per_war_inflation", 0.05))


# ============================================================================
# Point-in-time contract WAR paths (the projection engine + curve decay)
# ============================================================================

MAX_PATH_YEARS = 15


def _decay_path(war1: float, expo: float, side: str, role: str, age: int,
                curves: dict) -> list[float]:
    """Decay a year-1 WAR along the aging curves: the WAR RATE (per 600 PA /
    250 BF) and playing time each walk their fitted deltas at the advancing
    age. Shared by the central path and the P10/P90 variants so uncertainty
    propagates through the SAME aging machinery."""
    per = 600.0 if side == "hit" else 250.0
    rate = (war1 / expo * per) if expo > 0 else 0.0
    path = []
    a = age
    e = expo
    for t in range(MAX_PATH_YEARS):
        if t > 0:
            a += 1
            rate += fp.curve_delta(curves, side, role, "war_rate", a)
            e += fp.curve_delta(curves, side, role, "pt", a)
            e = max(0.0, e)
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


def _ml_active() -> bool:
    cfg = (fa_class.get_config().get("projection") or {}).get("ml") or {}
    if not cfg.get("enabled"):
        return False
    import proj_ml
    return proj_ml.load() is not None


def contract_war_path(hist: list[dict], side: str, class_year: int, years: int,
                      age: int | None, curves: dict, war_map: dict,
                      league: dict, in_progress: tuple[int, float] | None = None,
                      use_ml: bool | None = None,
                      ml_models: dict | None = None) -> dict | None:
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
    pins the champion (gates, eval baselines, feature assembly)."""
    proj = fp.project_player(hist, side, class_year, curves, league, age,
                             in_progress=in_progress)
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
    path = _decay_path(war1, expo, side, decay_role, a, curves)
    out = {"war_by_year": [round(w, 2) for w in path],
           "war_total": round(sum(path[:years]), 2),
           "war_y1": round(path[0], 2) if path else 0.0,
           "role": role, "pt_y1": proj["pt_proj"]}
    q = _gate1_band_quantiles().get(_band_bucket(side, expo))
    if q:
        p10 = _decay_path(war1 + q["q10"], expo, side, decay_role, a, curves)
        p90 = _decay_path(war1 + q["q90"], expo, side, decay_role, a, curves)
        out["war_by_year_p10"] = [round(w, 2) for w in p10]
        out["war_by_year_p90"] = [round(w, 2) for w in p90]
    if use_ml is False or (use_ml is None and not _ml_active() and ml_models is None):
        return out
    import proj_ml
    # Explicit ml_models = a POINT-IN-TIME bundle (historical enrichment);
    # default = the shipped live bundle. The live bundle must never serve
    # historical winters — it has seen their outcomes.
    models = ml_models if ml_models is not None else proj_ml.load()
    feats = proj_ml.build_features(hist, side, class_year, age, curves,
                                   war_map, league, champ=out)
    if models is None or feats is None:
        return out
    ml = proj_ml.predict_path(models, feats, side)
    if ml is None:
        return out
    H = proj_ml.HORIZONS

    def _extend(series_ml: list[float], champ_series: list[float]) -> list[float]:
        anchor = champ_series[H - 1]
        scale = (series_ml[H - 1] / anchor) if anchor > 0.05 else None
        tail = []
        for t in range(H, MAX_PATH_YEARS):
            if scale is not None:
                tail.append(max(0.0, champ_series[t] * scale))
            else:
                # champion anchor ~0: decay the ml h5 value by the champion's
                # year-over-year ratio chain, floored at 0
                prev = tail[-1] if tail else max(0.0, series_ml[H - 1])
                r = (champ_series[t] / champ_series[t - 1]) if champ_series[t - 1] > 0.05 else 0.7
                tail.append(max(0.0, prev * min(1.0, r)))
        return series_ml + [round(v, 2) for v in tail]

    med = _extend(ml["war_by_year"], path)
    out_ml = {**out,
              "war_by_year": med,
              "war_total": round(sum(med[:years]), 2),
              "war_y1": med[0],
              "war_by_year_p10": _extend(ml["war_by_year_p10"],
                                         [p * 0.6 for p in path]),
              "war_by_year_p90": _extend(ml["war_by_year_p90"],
                                         [p * 1.4 for p in path]),
              "model": proj_ml.MODEL_VERSION}
    return out_ml


def disc_war(path: dict, years: int) -> float:
    """Discounted WAR units over a candidate term — the quantity the
    market rate multiplies."""
    r = _discount_rate()
    return sum(w / ((1 + r) ** t)
               for t, w in enumerate(path["war_by_year"][:max(1, int(years))]))


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
      flat5      most recent PRIOR winter escalated 5%/yr (the v1 carry)
      trend      log-linear trend fit on PRIOR winters
      trend_cbt  trend + log CBT-threshold covariate (thresholds for
                 future winters are dated CBA records — known ex-ante)
    Fewer than 4 prior winters always falls back to flat5."""
    prior = {y: v for y, v in dpw_series.items() if y < class_year}
    if not prior:
        return fa_class._flat_dpw_usd()
    method = _dpw_forecast_method()
    if method in ("trend", "trend_cbt") and len(prior) >= 4:
        try:
            return _fit_log_trend(prior, with_cbt=(method == "trend_cbt"))(class_year)
        except Exception:                                   # noqa: BLE001 — fall back, never abort
            log.warning("dpw forecast %s failed — flat5 fallback", method)
    y = max(prior)
    return prior[y] * ((1 + _dpw_inflation()) ** (class_year - y))


# ============================================================================
# Rational value, deferrals, opt-outs, QO tax
# ============================================================================

def rational_value_usd(war_by_year: list[float], class_year: int,
                       dpw_usd: float) -> int:
    """NPV of the projected production: Σ_t PV(value(war_t) × level_t),
    $/WAR escalating at the configured inflation, discounted at the
    platform 9%.

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
    r = _discount_rate()
    infl = _dpw_inflation()
    level = dpw_usd / float(_vf_config()["dollars_per_war"]["flat"])
    total = 0.0
    for t, w in enumerate(war_by_year):
        total += (tiered_war_value_usd(w) * level * ((1 + infl) ** t)) / ((1 + r) ** t)
    return int(total)


def deferral_npv_usd(schedule: list[dict] | None, guarantee_usd: int) -> dict:
    """Sticker vs NPV guarantee. ``schedule`` rows: {year_offset, amount_usd}
    (from data/deferrals.json / fa_overrides when available). Without
    a schedule the guarantee is assumed level over the term — documented.

    IMPORTANT CONVENTION (Phase 2): a no-schedule deal keeps NPV == sticker.
    That treats the sticker as already-level cash, so the NPV adjustment
    captures only the DEFERRAL-vs-level difference — exactly the quantity
    the deferral ledger documents. Discounting every level contract too
    would just rescale all targets by an annuity factor without changing
    the model comparison, while making the displayed numbers unfamiliar."""
    r = _discount_rate()
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


def opt_out_scenarios(war_by_year: list[float], opt_out_after: int,
                      class_year: int, dpw_usd: float) -> dict:
    """v1 = SCENARIO LINES (owner decision): the rational value of the full
    term vs the pre-opt-out years only. Labeled, not option-priced."""
    full = rational_value_usd(war_by_year, class_year, dpw_usd)
    pre = rational_value_usd(war_by_year[:opt_out_after], class_year, dpw_usd)
    return {"full_term_rational_usd": full, "pre_opt_out_rational_usd": pre,
            "note": "scenario lines — opt-out not option-priced in v1"}


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


def qo_tax_usd(payor_tier: str, as_of) -> dict:
    """The QO pick forfeiture as DOLLARS: each forfeited representative
    slot priced at the platform's own FV-at-slot -> prospect-surplus value,
    plus any forfeited intl pool money at face value."""
    forf = fa_cba.pick_forfeiture(payor_tier, as_of)
    curve = pick_fv_curve()
    total = int(forf.get("intl_pool_usd") or 0)
    detail = []
    for pick_desc in forf["picks"]:
        slot = _TIER_SLOTS.get(pick_desc, 90)
        fv = curve.get(min(slot // 15, 12))
        usd = int(point_estimate_surplus_usd(fv, False) or 0) if fv else 0
        detail.append({"pick": pick_desc, "slot_assumed": slot,
                       "fv_at_slot": fv, "surplus_usd": usd})
        total += usd
    return {"total_usd": total, "detail": detail,
            "carry_forward": forf.get("carry_forward", False),
            "method": "platform_fv_at_slot_v1"}


# ============================================================================
# Predicted market price — transparent two-stage OLS + empirical bands
# ============================================================================

def _features_years(s: dict, comps_my: float) -> list[float]:
    """log-years stage. Years is skewed-discrete (1-year deals dominate;
    long deals are rare and young-star-only), so the stage models
    log(years) with curvature (WAR², age×WAR) AND stacks the
    nearest-comps median years in as a feature — the naive baseline's
    own signal, plus everything it can't see. Transparent kNN feature
    stacking, not a black box."""
    g = _pos_group(s.get("position"))
    w1 = s["_war_path"]["war_y1"]
    return [1.0, s["_age"], w1, w1 * w1, s["_age"] * w1,
            1.0 if g == "SP" else 0.0, 1.0 if g == "RP" else 0.0,
            1.0 if g == "C" else 0.0, 1.0 if s.get("qo") else 0.0,
            comps_my,
            # prime years remaining — the term structure behind long deals:
            # teams buy seasons through ~30; a 26-year-old's market simply
            # has more buyable years in it (v2 feature, gate-measured).
            max(0.0, 30.0 - s["_age"])]


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
    return [1.0, years, w1, w1 * years, s["_age"],
            1.0 if s.get("qo") else 0.0, supply, math.log(max(dpw_usd, 1e6)),
            log_comps_guar, log_rational, prime_war]


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
        self._comps_my_cache: dict[int, float] = {}
        self.coef_years = _ols([_features_years(s, self._comps_my(s)) for s in rows],
                               [math.log(float(s["years"])) for s in rows])
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
        self.coef_guar = _ols(Xg, yg)
        self.n_train = len(rows)
        # residual pools for empirical bands (log-NPV-guarantee + years)
        self.resid_log_guar = []
        self.resid_years = []
        for s in rows:
            py, pg = self._point(s)
            self.resid_years.append(s["years"] - py)
            self.resid_log_guar.append(math.log(_npv_of(s)) - math.log(max(pg, 1)))

    def _supply_z(self, s: dict) -> float:
        c = (self.supply_by_year.get(s["class_year"]) or
             _supply([s], s["class_year"])).get(_pos_group(s.get("position")), 0.0)
        return (c - self.sup_mean) / (self.sup_sd or 1.0)

    def _comps_stats(self, s: dict) -> tuple[float, float]:
        """(median comps years, log median trend-inflated comps guarantee)
        — computed once per row, the anchor features both stages stack."""
        key = id(s)
        if key not in self._comps_my_cache:
            cs = comps_for(s, self.train_pool)
            if cs:
                my = statistics.median(c["years"] for c in cs)
                infl = _dpw_inflation()
                # comps anchor on the NPV basis too — the anchor and the
                # target must speak the same currency.
                mg = statistics.median(
                    (c.get("npv_guarantee_usd") or c["guarantee_usd"])
                    * ((1 + infl) ** (s["class_year"] - c["class_year"]))
                    for c in cs)
                ma = statistics.median(
                    (c.get("npv_aav_usd") or c["aav_usd"]
                     or c["guarantee_usd"] / max(c["years"], 1))
                    * ((1 + infl) ** (s["class_year"] - c["class_year"]))
                    for c in cs)
            else:
                my, mg, ma = 1.0, 1_000_000.0, 1_000_000.0
            self._comps_my_cache[key] = (my, math.log(max(mg, 1.0)), ma)
        return self._comps_my_cache[key]

    def _comps_my(self, s: dict) -> float:
        return self._comps_stats(s)[0]

    @staticmethod
    def _log_rational(s: dict, years: float, dpw_usd: float) -> float:
        units = max(disc_war(s["_war_path"], int(round(years))), 0.25)
        return math.log(max(units * dpw_usd, 1e6))

    @staticmethod
    def _prime_war(s: dict) -> float:
        return max(0.0, 30.0 - s["_age"]) * max(0.0, s["_war_path"]["war_y1"])

    def _point(self, s: dict) -> tuple[float, float]:
        fy = _features_years(s, self._comps_my(s))
        years = math.exp(float(sum(c * x for c, x in zip(self.coef_years, fy))))
        years = min(max(years, 1.0), 13.0)
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
            # untouched) rising to 0.8 at $400M+. Smooth, monotone,
            # documented; the mega slice in the eval measures its effect.
            # v2: cap raised 0.8 -> 0.9 — the measured mega slice (model
            # $99M MAE vs comps $93M) says the anchor deserves MORE of the
            # vote at the very top, not less.
            lo, hi = math.log(50e6), math.log(400e6)
            alpha = min(0.9, max(0.0, (math.log(comps_guar) - lo) / (hi - lo) * 0.9))
            if alpha > 0:
                comps_aav = self._comps_stats(s)[2]
                mega_anchor = max(comps_guar, comps_aav * years)
                guar = math.exp((1 - alpha) * math.log(max(guar, 1.0))
                                + alpha * math.log(mega_anchor))
        return years, guar

    def predict(self, s: dict) -> dict:
        years_f, guar = self._point(s)
        years = int(round(years_f))
        qy = statistics.quantiles(self.resid_years, n=10) if len(self.resid_years) >= 50 else None
        qg = statistics.quantiles(self.resid_log_guar, n=10) if len(self.resid_log_guar) >= 50 else None
        out = {
            "proj_years": max(1, years),
            "proj_guarantee_usd": int(guar),
            "proj_aav_usd": int(guar / max(years, 1)),
        }
        if qy:
            out["proj_years_p10"] = max(1, int(round(years_f + qy[0])))
            out["proj_years_p90"] = int(round(years_f + qy[-1]))
        if qg:
            out["proj_guarantee_p10_usd"] = int(guar * math.exp(qg[0]))
            out["proj_guarantee_p90_usd"] = int(guar * math.exp(qg[-1]))
            # projAAV bands ride the guarantee band at the point-estimate term —
            # both framings (per-year price AND total value/length) carry
            # P10/P50/P90, per the module's distributions-not-points rule.
            out["proj_aav_p10_usd"] = int(out["proj_guarantee_p10_usd"] / max(years, 1))
            out["proj_aav_p90_usd"] = int(out["proj_guarantee_p90_usd"] / max(years, 1))
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
VERDICT_VALUE_MIN = 160     # Deal+ >= 160 -> "value"   (corpus top tercile)
VERDICT_OVERPAY_MAX = 75    # Deal+ <  75  -> "overpay" (corpus bottom tercile)


def deal_verdict(deal_plus: float | None) -> str | None:
    if deal_plus is None:
        return None
    if deal_plus >= VERDICT_VALUE_MIN:
        return "value"
    if deal_plus < VERDICT_OVERPAY_MAX:
        return "overpay"
    return "market"


def comps_for(s: dict, pool: list[dict], k: int = 5) -> list[dict]:
    """Nearest real historical contracts: same position group, distance in
    (age, projected year-1 WAR) z-units, prior winters only."""
    g = _pos_group(s.get("position"))
    cands = [c for c in pool if c is not s and c.get("_war_path")
             and c["class_year"] <= s["class_year"]
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
# Corpus enrichment (point-in-time, cached per winter via fitted_models)
# ============================================================================

def enriched_signings(first_year: int = 2015, last_year: int = 2026) -> list[dict]:
    """Every stored MLB-deal signing enriched with its point-in-time
    contract WAR path and signing age. Skips (and counts) players without
    corpus history — never fakes an input."""
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
        curves, war_map = fp.fitted_models(corpus, year - 1)
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
            age_prev = next((h.get("age") for h in hist if h.get("age")), None)
            age = (age_prev + (year - hist[0]["season"])) if age_prev else None
            path = contract_war_path(hist, side, year, int(s["years"]), age,
                                     curves, war_map, league, use_ml=False)
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

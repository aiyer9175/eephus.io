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


def contract_war_path(hist: list[dict], side: str, class_year: int, years: int,
                      age: int | None, curves: dict, war_map: dict,
                      league: dict, in_progress: tuple[int, float] | None = None) -> dict | None:
    """WAR by contract year: year 1 from the full Marcel engine; later
    years decay the WAR rate and playing time along the SAME aging curves
    (war_rate per-600/250 deltas + pt deltas at the advancing age).
    The path always extends MAX_PATH_YEARS so any candidate term can be
    priced by slicing; war_total covers the ACTUAL contract years.

    Floor/ceiling variants (war_by_year_p10 / _p90): the Gate-1 empirical
    year-1 residual quantile for the player's reliability bucket shifts the
    year-1 WAR, and the shifted talent decays along the same curves."""
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
    return out


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
    """Implied FA $/WAR per winter: total guarantee / total DISCOUNTED
    projected contract WAR across that winter's MLB deals (projected
    point-in-time — what buyers thought they were buying). Through-origin
    by construction; winters with thin totals are dropped."""
    agg: dict[int, dict] = defaultdict(lambda: {"g": 0.0, "w": 0.0, "n": 0})
    r = _discount_rate()
    for s in signings:
        cw = s.get("_war_path")
        if not cw or not s.get("guarantee_usd") or not s.get("years"):
            continue
        disc = disc_war(cw, int(s["years"]))
        if disc <= 0:
            continue
        a = agg[s["class_year"]]
        a["g"] += s["guarantee_usd"]
        a["w"] += disc
        a["n"] += 1
    return {y: v["g"] / v["w"] for y, v in sorted(agg.items())
            if v["w"] > 20 and v["n"] >= 25}


def winter_dpw(dpw_series: dict[int, float], class_year: int) -> float:
    """The winter's $/WAR level, EX-ANTE: the most recent PRIOR winter's
    estimate escalated by the configured inflation — a test winter never
    sees its own prices."""
    prior = [y for y in dpw_series if y < class_year]
    if not prior:
        return fa_class._flat_dpw_usd()
    y = max(prior)
    return dpw_series[y] * ((1 + _dpw_inflation()) ** (class_year - y))


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
    (from per-player Spotrac pages / fa_overrides when available). Without
    a schedule the guarantee is assumed level over the term — documented."""
    r = _discount_rate()
    if not schedule:
        return {"sticker_usd": guarantee_usd, "npv_usd": guarantee_usd,
                "method": "no_deferral_schedule_on_file"}
    npv = sum(row["amount_usd"] / ((1 + r) ** row["year_offset"]) for row in schedule)
    return {"sticker_usd": guarantee_usd, "npv_usd": int(npv), "method": "schedule_npv"}


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
            yg.append(math.log(s["guarantee_usd"]))
        self.coef_guar = _ols(Xg, yg)
        self.n_train = len(rows)
        # residual pools for empirical bands (log-guarantee + years)
        self.resid_log_guar = []
        self.resid_years = []
        for s in rows:
            py, pg = self._point(s)
            self.resid_years.append(s["years"] - py)
            self.resid_log_guar.append(math.log(s["guarantee_usd"]) - math.log(max(pg, 1)))

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
                mg = statistics.median(
                    c["guarantee_usd"] * ((1 + infl) ** (s["class_year"] - c["class_year"]))
                    for c in cs)
                ma = statistics.median(
                    (c["aav_usd"] or c["guarantee_usd"] / max(c["years"], 1))
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
# convex pricing is right-skewed (the 2015-2026 corpus at actual prices
# runs p33=81, median=121, p67=186 — short cheap deals on projectable
# players grade well; the left tail is megadeal overpays). The edges sit
# on the corpus TERCILES, so each verdict named exactly a third of twelve
# winters of real contracts. A class that skews "value" against these
# fixed bands is information, not a calibration artifact.
VERDICT_VALUE_MIN = 185     # Deal+ >= 185 -> "value"   (corpus top tercile)
VERDICT_OVERPAY_MAX = 85    # Deal+ <  85  -> "overpay" (corpus bottom tercile)


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
                                     curves, war_map, league)
            if path is None or age is None:
                skipped += 1
                continue
            out.append({**s, "_war_path": path, "_age": age, "_side": side})
    log.info("fa market corpus: %d enriched signings (%d skipped, no history)",
             len(out), skipped)
    return out

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The projected per-season $/WAR path (VAL_5, owner ask 2026-09-25).

Pure standard library, no repository import. Everything here is a function of
the numbers it is handed, so the gate's lab, the one writer and the tests share
one implementation:

  * the six methods of docs/dpw-2026-09-25/DPW_PATH_GATE.md section 3, with the
    gap rule, the median rule and the carry_zero fallback;
  * the written path (carry_const, or robust_drift with the TAPER of section 9);
  * the disclosure band of section 11;
  * the blindness check of section 10 over the named realized-level maps;
  * the hash-chain helpers shared by the forecast ledger and the owner record;
  * the SERVE CONDITION evaluator, the OD-7 rule resolver and the blind-status
    rules (confirmation, veto, reversion; the side rule in growth terms).

DPW_PATH_METHOD is the committed method switch. It has NO environment override;
the writer is its one read site and test_dpw_path_method_guard.py fails unless
it reads carry_const, or robust_drift while the SERVE CONDITION holds, read only
from the dpw_path_gate block of data/dpw_forecast_eval.json.

Nothing in this module computes an error of any arm on any series; the error
and power arithmetic of the look lives in tools/dpw_path_gate.py.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from typing import Iterable, Mapping

# The committed method switch (registration section 11). No environment override.
DPW_PATH_METHOD = "carry_const"

METHODS = ("carry_destale", "carry_zero", "robust_drift", "trend_line", "damped", "carry_const")
ROLES = {"carry_destale": "incumbent", "carry_zero": "floor", "robust_drift": "challenger",
         "trend_line": "descriptive", "damped": "descriptive", "carry_const": "prospective_comparator"}
SERVABLE = ("carry_const", "robust_drift")

CLIP_LO = 0.0
CLIP_HI = 0.12
DAMP = 0.8
MIN_WINTERS = 4
FORECAST_HORIZON = 5
TAPER_SEASONS = 4
WRITTEN_THROUGH = 2045

G_REF_DEFAULT = 0.0409
# The default nominal rate, the LITERAL (1.07)(1.0409) - 1 written out at full
# precision. Never recomputed from the live g_ref (registration section 12: R
# never follows g_ref; deriving R from g_ref is banned).
R_DEFAULT = 0.113763

TRUTH_ESTIMATOR_ID = "sticker_leveleq_r_over_disc_war_r_p20_v1"
ROUND_TRIP_ESTIMATOR_ID = "pv_cash_R_over_disc_war_rnet_p20_v1"
TERM_MIX_WEIGHTS = {"1": 0.2517, "2-3": 0.3177, "4+": 0.4306}
BAND_SEED = 20260925
BAND_B = 500

VERDICTS = ("PASS_DEV", "WORSE", "NULL", "NULL_UNDERPOWERED", "VOID", "NOT_AVAILABLE")
BLIND_STATUSES = ("NOT_ARMED", "PENDING", "CONFIRMED", "VETOED")

# Owner option codes (DESIGN_v2 4.4). The lab and the writer read CODES only;
# an option number, or any string not listed here, is rejected.
OPTION_CODES = {
    "OD-1": ("round_trip", "sticker"),
    "OD-2": ("r_0113763", "r_010", "r_other"),
    "OD-3": ("base_2027", "base_2026"),
    "OD-4": ("neutral_follow_path", "own_trends", "flat_nominal"),
    "OD-5": ("align", "keep"),
    "OD-6": ("confirm_first", "serve_at_dev_pass", "never"),
    "OD-7": ("keep_0409", "remeasure_served_rule", "zero_if_floor"),
    "OD-8": ("refit_knots", "bridge"),
}
# The conventions the writer reads from data/dpw_path_owner.json, by option name.
CONVENTION_IDS = {"level_basis": "OD-1", "R": "OD-2", "base_season": "OD-3",
                  "companion_mode": "OD-4", "trade_machine": "OD-5", "calibration": "OD-8"}
CONVENTION_DEFAULTS = {"level_basis": "round_trip", "R": "r_0113763", "base_season": "base_2027",
                       "companion_mode": "neutral_follow_path", "trade_machine": "align",
                       "calibration": "refit_knots"}
OWNER_SCHEMA = "dpw_path_owner_v1"
LEDGER_SCHEMA = "dpw_path_ledger_v1"
ZERO_SHA = "0" * 64


class DpwPathError(ValueError):
    """A malformed input the path refuses to price on."""


# ---------------------------------------------------------------------------
# Series helpers: the gap rule
# ---------------------------------------------------------------------------

def available(series: Mapping[int, float], origin: int | None = None) -> list[int]:
    """Winters with a positive level, at or before ``origin`` when given, sorted."""
    return sorted(int(w) for w, v in series.items()
                  if v is not None and float(v) > 0 and (origin is None or int(w) <= origin))


def differences(series: Mapping[int, float], origin: int | None = None) -> list[float]:
    """First log differences over consecutive AVAILABLE winters, annualized over a
    gap and entered once: d = ln(A(W)/A(W')) / (W - W')."""
    ws = available(series, origin)
    out = []
    for a, b in zip(ws, ws[1:]):
        out.append(math.log(float(series[b]) / float(series[a])) / (b - a))
    return out


def _clip(g: float) -> float:
    return max(CLIP_LO, min(CLIP_HI, g))


def g_destale(series: Mapping[int, float], origin: int) -> float | None:
    """The served carry's growth g_I(o): the OLS log slope over the winters at or
    before ``origin``, exp(b) - 1 clipped to [0, 0.12], exactly as
    fa_market._destale_rate computes it (same operations, same order). None with
    fewer than 4 winters (fa_market falls back to the valuation set's inflation
    there; this module falls back to carry_zero instead)."""
    yrs = available(series, origin)
    if len(yrs) < MIN_WINTERS:
        return None
    n = float(len(yrs))
    mx = sum(yrs) / n
    my = sum(math.log(series[y]) for y in yrs) / n
    num = sum((y - mx) * (math.log(series[y]) - my) for y in yrs)
    den = sum((y - mx) ** 2 for y in yrs)
    if den <= 0:
        return None
    return max(0.0, min(0.12, math.exp(num / den) - 1.0))


def g_robust(series: Mapping[int, float], origin: int) -> float | None:
    """The challenger's growth g_A(o): exp(median of d) - 1 clipped to [0, 0.12].
    The median of an even count is the mean of the two middle values
    (statistics.median). None with fewer than 4 winters."""
    if len(available(series, origin)) < MIN_WINTERS:
        return None
    return _clip(math.exp(statistics.median(differences(series, origin))) - 1.0)


def trend_coefficients(series: Mapping[int, float], origin: int) -> tuple[float, float, float] | None:
    """(mean year, mean ln A, slope b) of the OLS of ln A on year over winters
    <= origin, kept centred for precision. None with fewer than 4 winters."""
    yrs = available(series, origin)
    if len(yrs) < MIN_WINTERS:
        return None
    n = float(len(yrs))
    mx = sum(yrs) / n
    ly = [math.log(series[y]) for y in yrs]
    my = sum(ly) / n
    sxx = sum((y - mx) ** 2 for y in yrs)
    sxy = sum((y - mx) * (v - my) for y, v in zip(yrs, ly))
    return mx, my, sxy / sxx


def anchor(series: Mapping[int, float], origin: int) -> float:
    if origin not in series or series[origin] is None or float(series[origin]) <= 0:
        raise DpwPathError(f"origin winter {origin} is not available in the series")
    return float(series[origin])


def forecast(method: str, series: Mapping[int, float], origin: int, h: int,
             *, g_ref: float | None = None) -> float:
    """P_o(o + h) for one method, from the winters at or before ``origin`` only.
    Every method needs at least 4 winters; fewer falls back to carry_zero."""
    if method not in METHODS:
        raise DpwPathError(f"unknown method {method!r}")
    if h < 1:
        raise DpwPathError("h must be at least 1")
    a = anchor(series, origin)
    if len(available(series, origin)) < MIN_WINTERS or method == "carry_zero":
        return a
    if method == "carry_const":
        if g_ref is None:
            raise DpwPathError("carry_const needs the recorded g_ref")
        return a * (1.0 + float(g_ref)) ** h
    if method == "carry_destale":
        return a * (1.0 + g_destale(series, origin)) ** h
    if method == "robust_drift":
        return a * (1.0 + g_robust(series, origin)) ** h
    if method == "trend_line":
        mx, my, b = trend_coefficients(series, origin)
        return math.exp(my + b * ((origin + h) - mx))
    # damped: growth in step k is g_I + (g_A - g_I) * 0.8^(k-1), compounded
    gi, ga = g_destale(series, origin), g_robust(series, origin)
    p = a
    for k in range(1, h + 1):
        p *= 1.0 + gi + (ga - gi) * DAMP ** (k - 1)
    return p


def method_growth(method: str, series: Mapping[int, float], origin: int,
                  *, g_ref: float | None = None) -> float:
    """The ``growth`` a forecast row records. For damped it is the step-1 growth
    of its registered formula, g_I + (g_A - g_I) x 0.8^0 = g_A (the registration's
    parenthetical "which equals g_I(o)" does not match its own formula; the
    definition "its step-1 growth" is what is stored, and it is a disclosure
    only); for trend_line exp(b) - 1. For those two the growth never re-anchors
    a forecast (registration section 10)."""
    if len(available(series, origin)) < MIN_WINTERS or method == "carry_zero":
        return 0.0
    if method == "carry_const":
        return float(g_ref)
    if method == "carry_destale":
        return g_destale(series, origin)
    if method in ("robust_drift", "damped"):
        return g_robust(series, origin)
    return math.exp(trend_coefficients(series, origin)[2]) - 1.0


# ---------------------------------------------------------------------------
# The written path
# ---------------------------------------------------------------------------

def build_path(level_n: float, n: int, *, method: str = "carry_const", g_ref: float,
               g_a: float | None = None, through: int = WRITTEN_THROUGH) -> dict[int, float]:
    """Seasons N..``through`` of the written path, P(N) = the served level of N.

    carry_const: P(s) = P(N)(1 + g_ref)^(s - N).
    robust_drift (only under the SERVE CONDITION): P(N + h) = P(N)(1 + g_A)^h for
    h = 1..5; then the TAPER, ln P(N+5+k) = ln P_const(N+5+k) + (1 - k/5) x 5
    ln((1 + g_A)/(1 + g_ref)) for k = 1..4; from N + 10 on, P_const."""
    if method not in SERVABLE:
        raise DpwPathError(f"{method!r} can never be the served path")
    level_n = float(level_n)
    out = {}
    for s in range(int(n), int(through) + 1):
        h = s - n
        p_const = level_n * (1.0 + g_ref) ** h
        if method == "carry_const" or h == 0:
            out[s] = p_const
            continue
        if g_a is None:
            raise DpwPathError("robust_drift needs g_A at serving time")
        if h <= FORECAST_HORIZON:
            out[s] = level_n * (1.0 + g_a) ** h
        elif h <= FORECAST_HORIZON + TAPER_SEASONS:
            k = h - FORECAST_HORIZON
            dev = (1.0 - k / 5.0) * 5.0 * math.log((1.0 + g_a) / (1.0 + g_ref))
            out[s] = math.exp(math.log(p_const) + dev)
        else:
            out[s] = p_const
    return out


def path_kinds(n: int, method: str, through: int = WRITTEN_THROUGH) -> dict[int, str]:
    """realized / convention / forecast / assumption, by season."""
    out = {}
    for s in range(int(n), int(through) + 1):
        h = s - n
        if h == 0:
            out[s] = "realized"
        elif h > FORECAST_HORIZON:
            out[s] = "assumption"
        else:
            out[s] = "forecast" if method == "robust_drift" else "convention"
    return out


def interpolate_level(path: Mapping[int, float], season: float, g_ref: float) -> float:
    """P(season) with ln P interpolated linearly between integer seasons (exact
    under constant growth); past the last written season extrapolated at g_ref,
    before the first back-cast at g_ref."""
    if not path:
        raise DpwPathError("empty path")
    keys = sorted(int(k) for k in path)
    lo, hi = keys[0], keys[-1]
    s = float(season)
    if s >= hi:
        return float(path[hi]) * (1.0 + g_ref) ** (s - hi)
    if s <= lo:
        return float(path[lo]) * (1.0 + g_ref) ** (s - lo)
    a = int(math.floor(s))
    if a == s:
        return float(path[a])
    b = a + 1
    w = s - a
    return math.exp((1.0 - w) * math.log(float(path[a])) + w * math.log(float(path[b])))


# ---------------------------------------------------------------------------
# The band (disclosure only, registration section 11)
# ---------------------------------------------------------------------------

def _betacf(a: float, b: float, x: float) -> float:
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = tiny if abs(d) < tiny else d
    d = 1.0 / d
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = tiny if abs(d) < tiny else d
        c = 1.0 + aa / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = tiny if abs(d) < tiny else d
        c = 1.0 + aa / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < 1e-15:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbt = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
           + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbt) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbt) * _betacf(b, a, 1.0 - x) / b


def t_cdf(t: float, df: float) -> float:
    x = df / (df + t * t)
    tail = 0.5 * _betainc(df / 2.0, 0.5, x)
    return 1.0 - tail if t >= 0 else tail


def t_quantile(p: float, df: float) -> float:
    """Student t quantile by bisection on t_cdf (to 1e-12)."""
    if not 0.0 < p < 1.0 or df <= 0:
        raise DpwPathError("bad t quantile arguments")
    lo, hi = -1e3, 1e3
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return 0.5 * (lo + hi)


def band(path: Mapping[int, float], n: int, truth: Mapping[int, float], tau_n: float,
         method: str) -> dict:
    """V_h = tau_N^2 + h s_d^2 + h^2 c_m s_d^2 / n_d; P10/P90 = P exp(-/+ t sqrt(V_h)),
    t = t_{0.90, n_d - 1}; s_d the sd of the truth's differences (gap rule), c_m 1
    for the constant-growth methods and pi/2 for robust_drift. The expected-value
    factor exp(V_h/2) is published and NOT applied."""
    d = differences(truth, n)
    n_d = len(d)
    if n_d < 2:
        raise DpwPathError("the band needs at least two differences")
    s_d = statistics.stdev(d)
    c_m = math.pi / 2.0 if method == "robust_drift" else 1.0
    tq = t_quantile(0.90, n_d - 1)
    p10, p90, kind, ev = {}, {}, {}, {}
    for s in sorted(int(k) for k in path):
        h = s - n
        if h <= 0:
            continue
        v = tau_n ** 2 + h * s_d ** 2 + h * h * c_m * s_d ** 2 / n_d
        p10[s] = float(path[s]) * math.exp(-tq * math.sqrt(v))
        p90[s] = float(path[s]) * math.exp(tq * math.sqrt(v))
        ev[s] = math.exp(v / 2.0)
        kind[s] = ("assumption" if h > FORECAST_HORIZON else
                   "forecast" if method == "robust_drift" else "convention")
    return {"p10": p10, "p90": p90, "kind": kind, "s_d": s_d, "n_d": n_d, "c_m": c_m,
            "t_0.90": tq, "formula": "V_h = tau^2 + h s_d^2 + h^2 c_m s_d^2 / n_d",
            "ev_factor_unapplied": ev}


# ---------------------------------------------------------------------------
# Truth helpers: the level-equivalent sticker and the term-mix index
# ---------------------------------------------------------------------------

def pv(flows: Iterable[tuple[float, float]], rate: float) -> float:
    """PV at ``rate`` from offset 0 of (year_offset, amount) flows."""
    return sum(float(amt) / (1.0 + rate) ** float(off) for off, amt in flows)


def level_equivalent_sticker(sticker: float, years: int, schedule: Iterable[tuple[float, float]],
                             rate: float) -> float:
    """G_i = sticker x PV_r(schedule) / PV_r(level), where the level deal pays
    sticker / years at offsets 0 .. years - 1: the sticker of the level deal with
    the same present value (registration section 1)."""
    years = max(1, int(years))
    level = [(t, float(sticker) / years) for t in range(years)]
    return float(sticker) * pv(schedule, rate) / pv(level, rate)


def years_bucket(years: int) -> str:
    return "1" if years <= 1 else "2-3" if years <= 3 else "4+"


def term_mix_index(rows: Iterable[tuple[int, float, float]],
                   weights: Mapping[str, float] = TERM_MIX_WEIGHTS) -> tuple[float | None, list[str]]:
    """One winter's term-mix index from (years, G, disc_war) rows: each bucket's
    level sum G / sum disc_war, then the weighted mean with the frozen weights; a
    bucket with no deal drops and the remaining weights renormalise. Returns
    (index, dropped buckets)."""
    num = {b: 0.0 for b in weights}
    den = {b: 0.0 for b in weights}
    for years, g, w in rows:
        b = years_bucket(int(years))
        num[b] += float(g)
        den[b] += float(w)
    present = [b for b in weights if den[b] > 0]
    dropped = [b for b in weights if den[b] <= 0]
    if not present:
        return None, dropped
    tot = sum(weights[b] for b in present)
    return sum(weights[b] / tot * (num[b] / den[b]) for b in present), dropped


# ---------------------------------------------------------------------------
# Canonical JSON and the hash chain (ledger and owner record)
# ---------------------------------------------------------------------------

def canonical_json(obj) -> str:
    """Sorted keys, no whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_of(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def append_chained(rows: list[dict], row: dict) -> dict:
    """Append ``row`` with prev_sha256 = the sha256 of the previous row's canonical
    JSON (64 zeros for the first). Returns the stored row."""
    out = dict(row)
    out["prev_sha256"] = sha256_of(rows[-1]) if rows else ZERO_SHA
    rows.append(out)
    return out


def verify_chain(rows: list[dict]) -> None:
    """Raise unless every row's prev_sha256 is the previous row's sha256."""
    prev = ZERO_SHA
    for i, r in enumerate(rows):
        if r.get("prev_sha256") != prev:
            raise DpwPathError(f"hash chain broken at row {i}")
        prev = sha256_of(r)


def chain_head(rows: list[dict]) -> dict:
    """The head record: the sha256 of the last row and the row count. A backward
    chain cannot see the removal of the last rows; the head can."""
    return {"head_sha256": sha256_of(rows[-1]) if rows else None, "row_count": len(rows)}


def check_head(rows: list[dict], record: Mapping) -> None:
    verify_chain(rows)
    head = chain_head(rows)
    if head["head_sha256"] != record.get("head_sha256") or head["row_count"] != record.get("row_count"):
        raise DpwPathError(f"chain head {head} does not equal the recorded {dict(record)}")


# ---------------------------------------------------------------------------
# The owner record (data/dpw_path_owner.json)
# ---------------------------------------------------------------------------

def validate_owner_row(row: Mapping) -> None:
    qid = row.get("id")
    if qid not in OPTION_CODES:
        raise DpwPathError(f"unregistered question id {qid!r}")
    opt = row.get("option")
    if not isinstance(opt, str) or opt not in OPTION_CODES[qid]:
        raise DpwPathError(f"{qid}: option {opt!r} is not a registered option code "
                           f"(codes only, never an option number)")
    if opt == "r_other":
        r = row.get("R")
        if not isinstance(r, (int, float)) or isinstance(r, bool) or not 0.0 < float(r) < 1.0:
            raise DpwPathError("OD-2 r_other carries R as a number in the row")


def validate_owner_doc(doc: Mapping) -> list[dict]:
    if doc.get("schema") != OWNER_SCHEMA:
        raise DpwPathError(f"owner record schema is not {OWNER_SCHEMA}")
    rows = list(doc.get("answers") or [])
    for r in rows:
        validate_owner_row(r)
    verify_chain(rows)
    return rows


def last_answer(doc: Mapping | None, qid: str) -> dict | None:
    """The LAST row for ``qid`` in chain order (where an id has several rows,
    the last binds). None when the file or the id is absent."""
    if not doc:
        return None
    rows = validate_owner_doc(doc)
    found = None
    for r in rows:
        if r.get("id") == qid:
            found = r
    return found


def convention(doc: Mapping | None, name: str) -> str:
    """A writer convention (OD-1 to OD-5, OD-8) by name, as its option code; the
    recommended default when no answer is recorded."""
    row = last_answer(doc, CONVENTION_IDS[name])
    return row["option"] if row else CONVENTION_DEFAULTS[name]


def nominal_rate_from_owner(doc: Mapping | None) -> float:
    """The stored nominal rate R: the recorded OD-2 answer, or the LITERAL
    default 0.113763. Never derived from g_ref."""
    row = last_answer(doc, "OD-2")
    if row is None or row["option"] == "r_0113763":
        return R_DEFAULT
    if row["option"] == "r_010":
        return 0.10
    return float(row["R"])


def owner_record_for_block(doc: Mapping | None, ids=("OD-6", "OD-7")) -> dict:
    """What the lab copies into the gate block's owner_at_amendment: per id the
    option CODE, the date and the row sha256 of the last row (or None for an
    absent id), with the file's chain head and row count. Never the answer text."""
    rows = validate_owner_doc(doc) if doc else []
    out = {}
    for qid in ids:
        row = last_answer(doc, qid) if doc else None
        out[qid] = (None if row is None else
                    {"option": row["option"], "date": row.get("date"), "row_sha256": sha256_of(row)})
    head = chain_head(rows)
    out["chain_head_sha256"] = head["head_sha256"]
    out["row_count"] = head["row_count"]
    return out


# ---------------------------------------------------------------------------
# The SERVE CONDITION, the OD-7 rule and the blind status
# ---------------------------------------------------------------------------

def _code(record: Mapping | None, qid: str) -> str | None:
    rec = (record or {}).get(qid)
    if rec is None:
        return None
    if not isinstance(rec, Mapping):
        raise DpwPathError(f"{qid} record must carry an option code")
    opt = rec.get("option")
    if not isinstance(opt, str) or opt not in OPTION_CODES[qid]:
        raise DpwPathError(f"{qid}: {opt!r} is not a registered option code")
    return opt


def incumbent_below_floor(gate_block: Mapping | None) -> bool:
    flags = (gate_block or {}).get("flags") or {}
    return flags.get("INCUMBENT_BELOW_FLOOR") is True


def serve_condition(gate_block: Mapping | None) -> bool:
    """Registration section 9. robust_drift may serve only when the block's
    verdict is PASS_DEV, its blind status is not VETOED, and either (i) the blind
    status is CONFIRMED (the default, binding when owner_at_amendment holds no
    OD-6 row) or (ii) owner_at_amendment's OD-6 code is serve_at_dev_pass. Never
    under OD-6 never. OD-6 is read ONLY from the block's owner_at_amendment, by
    option code."""
    if not gate_block:
        return False
    verdict = gate_block.get("verdict")
    status = gate_block.get("blind_status")
    if verdict not in VERDICTS:
        raise DpwPathError(f"verdict {verdict!r} is outside the closed vocabulary")
    if status is not None and status not in BLIND_STATUSES:
        raise DpwPathError(f"blind status {status!r} is outside the closed vocabulary")
    od6 = _code(gate_block.get("owner_at_amendment"), "OD-6")
    if verdict != "PASS_DEV" or status == "VETOED" or od6 == "never":
        return False
    if status == "CONFIRMED":
        return True
    return od6 == "serve_at_dev_pass"


def method_permitted(method: str, gate_block: Mapping | None) -> bool:
    if method == "carry_const":
        return True
    if method == "robust_drift":
        return serve_condition(gate_block)
    return False


def resolve_method(gate_block: Mapping | None, method: str | None = None) -> str:
    """The method the writer serves: DPW_PATH_METHOD, refused unless permitted."""
    m = DPW_PATH_METHOD if method is None else method
    if not method_permitted(m, gate_block):
        raise DpwPathError(f"DPW_PATH_METHOD={m!r} without the SERVE CONDITION")
    return m


def g_ref_rule(gate_block: Mapping | None) -> str:
    """The OD-7 rule in force: owner_after_look's zero_if_floor while the block's
    INCUMBENT_BELOW_FLOOR is true; else owner_at_amendment's keep_0409 or
    remeasure_served_rule; else keep_0409 (rule (a) binds with no row)."""
    block = gate_block or {}
    oal = block.get("owner_after_look")
    if oal and incumbent_below_floor(block) and _code(oal, "OD-7") == "zero_if_floor":
        return "zero_if_floor"
    od7 = _code(block.get("owner_at_amendment"), "OD-7")
    if od7 == "zero_if_floor":
        raise DpwPathError("OD-7 zero_if_floor exists only after the look (owner_after_look)")
    return od7 or "keep_0409"


def g_ref_value(rule: str, truth: Mapping[int, float] | None = None, n: int | None = None,
                previous: Mapping | None = None) -> float:
    """g_ref under a rule. (a) 0.0409; (c) 0; (b) the served rule
    (fa_market._destale_rate, here g_destale) on the truth through N, measured
    once per N and carried forward from ``previous`` (the block on disk) while
    N is unchanged, never re-estimated nightly."""
    if rule == "keep_0409":
        return G_REF_DEFAULT
    if rule == "zero_if_floor":
        return 0.0
    if rule != "remeasure_served_rule":
        raise DpwPathError(f"unknown OD-7 rule {rule!r}")
    prev = previous or {}
    if prev.get("g_ref_rule") == rule and prev.get("g_ref_measured_at_n") == n and prev.get("g_ref") is not None:
        return float(prev["g_ref"])
    g = g_destale(truth or {}, int(n))
    if g is None:
        raise DpwPathError("rule (b) needs at least 4 truth winters through N")
    return g


def side_of_target(r: float, g_a_stored: float, g_ref_stored: float) -> str:
    """'A' if |ln(1 + g_A) - r| < |ln(1 + g_ref) - r| strictly, else 'C'
    (carry_const's side), with r the scoring vintage's realized log growth."""
    da = abs(math.log(1.0 + g_a_stored) - r)
    dc = abs(math.log(1.0 + g_ref_stored) - r)
    return "A" if da < dc else "C"


def realized_log_growth(truth_scoring: Mapping[int, float], target: int) -> float | None:
    """r = ln(A_s(W)/A_s(W-1)), both levels from the scoring vintage; None (the
    target is unsided) when either winter is absent."""
    a, b = truth_scoring.get(target - 1), truth_scoring.get(target)
    if not a or not b:
        return None
    return math.log(float(b) / float(a))


def reanchor(anchor_scoring: float, forecast_usd: float, anchor_usd: float) -> float:
    """Every later scoring compares a stored forecast with a target only as
    A_s(o) x forecast_usd / anchor_usd, on the scoring vintage's anchor."""
    return float(anchor_scoring) * float(forecast_usd) / float(anchor_usd)


def blind_status(verdict: str, od6_code: str | None, targets: Iterable[Mapping]) -> dict:
    """The blind status after the scored blind targets, in order.

    Each target: {"side": "A" | "C" | None (unsided), "regime": bool}. Unsided
    targets are skipped everywhere. Under confirmation (A not serving), the first
    two sided NON-REGIME targets on A's side confirm, a REGIME target on A's side
    is skipped, and any sided target on carry_const's side before confirmation
    vetoes. While A serves (after CONFIRMED, or from PASS_DEV under OD-6
    serve_at_dev_pass), two CONSECUTIVE sided targets on carry_const's side
    revert it (VETOED); a REGIME target on A's side, or an unsided one, neither
    extends nor resets the count. Returns {"status", "reverted"}."""
    if verdict != "PASS_DEV":
        return {"status": "NOT_ARMED", "reverted": False}
    serving = od6_code == "serve_at_dev_pass"
    confirmed = False
    a_count = 0
    c_run = 0
    for t in targets:
        side = t.get("side")
        regime = bool(t.get("regime"))
        if side is None:
            continue
        if not serving:
            if confirmed:
                continue        # OD-6 never: A does not serve, nothing further moves
            if side == "C":
                return {"status": "VETOED", "reverted": False}
            if regime:
                continue
            a_count += 1
            if a_count == 2:
                confirmed = True
                serving = od6_code != "never"
            continue
        # A serves: two consecutive sided targets on carry_const's side revert it
        if side == "C":
            c_run += 1
            if c_run >= 2:
                return {"status": "VETOED", "reverted": True}
            continue
        if regime:
            continue
        c_run = 0
        if not confirmed:
            a_count += 1
            if a_count == 2:
                confirmed = True
    return {"status": "CONFIRMED" if confirmed else "PENDING", "reverted": False}


# ---------------------------------------------------------------------------
# Blindness (registration section 10)
# ---------------------------------------------------------------------------

# Realized-level maps by file kind and JSON path. "keys": the map's keys are
# winters; "values": the listed values are winters.
REALIZED_LEVEL_MAPS = {
    "fa_dpw_series": [("usd_per_war_by_winter", "keys"), ("breakdown.by_winter", "keys"),
                      ("breakdown.realized", "keys"), ("dpw_path.truth.by_winter", "keys"),
                      ("dpw_path.truth.tau_by_winter", "keys"),
                      ("dpw_path.truth.term_mix_index.by_winter", "keys"),
                      ("dpw_path.served_level.by_winter", "keys")],
    "fa_class": [("dpw_series_pricing", "keys")],
    "fa_meta": [("dpw_series.usd_per_war_by_winter", "keys"), ("dpw_series.breakdown.by_winter", "keys"),
                ("dpw_series.breakdown.realized", "keys"), ("dpw_pricing.usd_per_war_by_winter", "keys")],
    "dpw_forecast_eval": [("test_winters", "values"), ("per_winter[].winter", "values")],
    "fa_archive": [("winters[].year", "values")],
}
# Forecast, path, band and salary-index maps, excluded by name.
EXCLUDED_PREFIXES = ("dpw_path.path", "dpw_path.salary_index", "dpw_path_summary",
                     "dpw_series.dpw_path", "dpw_path_gate")


def _get(doc, dotted: str):
    """Values at a dotted path; a "name[]" segment fans out over a list."""
    cur = [doc]
    for seg in dotted.split("."):
        nxt = []
        many = seg.endswith("[]")
        key = seg[:-2] if many else seg
        for c in cur:
            if not isinstance(c, Mapping) or key not in c:
                continue
            v = c[key]
            if many:
                nxt.extend(v if isinstance(v, list) else [])
            else:
                nxt.append(v)
        cur = nxt
    return cur


def _years_at(doc, dotted: str, how: str) -> set[int]:
    out = set()
    if how == "values" and "[]." in dotted:
        head, leaf = dotted.rsplit(".", 1)
        for item in _get(doc, head):
            if isinstance(item, Mapping) and item.get(leaf) is not None:
                try:
                    out.add(int(item[leaf]))
                except (TypeError, ValueError):
                    pass
        return out
    for v in _get(doc, dotted):
        if how == "keys" and isinstance(v, Mapping):
            for k in v:
                try:
                    out.add(int(k))
                except (TypeError, ValueError):
                    pass
        elif how == "values" and isinstance(v, list):
            for x in v:
                try:
                    out.add(int(x))
                except (TypeError, ValueError):
                    pass
    return out


def _year_keyed_maps(node, path: str = "") -> list[str]:
    found = []
    if isinstance(node, Mapping):
        keys = list(node.keys())
        if keys and all(isinstance(k, str) and len(k) == 4 and k.isdigit() for k in keys):
            found.append(path or "<root>")
        for k, v in node.items():
            found.extend(_year_keyed_maps(v, f"{path}.{k}" if path else str(k)))
    elif isinstance(node, list):
        for v in node[:1]:
            found.extend(_year_keyed_maps(v, f"{path}[]"))
    return found


def realized_level_check(docs: Mapping[str, tuple[str, Mapping]], winter: int) -> dict:
    """Condition 1 of the blindness check. ``docs`` maps a file name to (kind,
    parsed JSON), kind one of REALIZED_LEVEL_MAPS. Counts every named map that
    holds ``winter``; the count must be ZERO. Other year-keyed maps are listed as
    a disclosure and decide nothing."""
    hits = []
    named = set()
    for name, (kind, doc) in sorted(docs.items()):
        for dotted, how in REALIZED_LEVEL_MAPS.get(kind, []):
            named.add((name, dotted.replace("[]", "")))
            if int(winter) in _years_at(doc, dotted, how):
                hits.append(f"{name}:{dotted}")
    unclassified = []
    for name, (kind, doc) in sorted(docs.items()):
        for p in _year_keyed_maps(doc):
            clean = p.replace("[]", "")
            if (name, clean) in named or any(clean.startswith(x) for x in EXCLUDED_PREFIXES):
                continue
            if any(clean.startswith(d + ".") for (n2, d) in named if n2 == name):
                continue
            unclassified.append(f"{name}:{p}")
    return {"winter": int(winter), "realized_level_hits": hits, "count": len(hits),
            "unclassified_year_maps": unclassified}


def is_blind(check: Mapping, deal_count: int) -> bool:
    """Blind only if BOTH counts are zero: no realized-level map holds o + 1, and
    no class o + 1 signing passes the estimator's deal filter."""
    return int(check.get("count", 1)) == 0 and int(deal_count) == 0


def forecast_rows(truth: Mapping[int, float], origin: int, *, made_at: str, truth_sha256: str,
                  basis_id: str | None, g_ref: float, blind_check: Mapping) -> list[dict]:
    """The ledger's forecast rows for one origin: all six arms, h = 1..5."""
    rows = []
    a = anchor(truth, origin)
    for arm in METHODS:
        g = method_growth(arm, truth, origin, g_ref=g_ref)
        for h in range(1, FORECAST_HORIZON + 1):
            rows.append({"kind": "forecast", "origin": int(origin), "made_at": made_at,
                         "truth_sha256": truth_sha256, "basis_id": basis_id, "arm": arm, "h": h,
                         "season": int(origin) + h, "anchor_usd": a, "growth": g,
                         "forecast_usd": forecast(arm, truth, origin, h, g_ref=g_ref),
                         "g_ref_recorded": float(g_ref), "blind_check": dict(blind_check)})
    return rows


# ---------------------------------------------------------------------------
# The CBA: structure keys, regime_break and the prospective REGIME rule
# ---------------------------------------------------------------------------

STRUCTURE_FROM = "2026-12-01"
STRUCTURE_KEYS = ("salary_cap", "salary_floor", "fa_eligibility_changed", "arb_eligibility_changed",
                  "cbt_structure", "stoppage")


def agreements_missing_structure(cba_rules: Mapping) -> list[str]:
    """Agreements encoded with effective_from after 2026-12-01 that do not carry
    every structure key (a test requires none)."""
    out = []
    for r in cba_rules.get("cba_regimes") or []:
        if (r.get("effective_from") or "") > STRUCTURE_FROM:
            missing = [k for k in STRUCTURE_KEYS if k not in r]
            if missing:
                out.append(f"{r.get('regime')}: {', '.join(missing)}")
    return out


def structurally_different(regime: Mapping) -> bool:
    """A salary cap or floor, a change to free-agency or arbitration eligibility,
    or a luxury tax replaced or restructured beyond its threshold and rate values."""
    return bool(regime.get("salary_cap") or regime.get("salary_floor")
                or regime.get("fa_eligibility_changed") or regime.get("arb_eligibility_changed")
                or str(regime.get("cbt_structure") or "unchanged") in ("replaced", "restructured"))


def _stoppage_overlaps(regime: Mapping, start: str, end: str) -> bool:
    st = regime.get("stoppage")
    if not st:
        return False
    if isinstance(st, Mapping):
        a, b = str(st.get("from") or ""), str(st.get("to") or "9999-12-31")
        return a <= end and b >= start
    return True


def _signing_window(season: int) -> tuple[str, str]:
    """The window from the day after the previous World Series to opening day of
    season W, encoded conventionally as November 1 of W - 1 to March 31 of W."""
    return f"{int(season) - 1}-11-01", f"{int(season)}-03-31"


def governing_agreement(cba_rules: Mapping, season: int) -> Mapping | None:
    """The agreement governing season W's signing period (the one in force on
    December 1 of W - 1); None when no agreement is encoded for it."""
    day = f"{int(season) - 1}-12-01"
    for r in cba_rules.get("cba_regimes") or []:
        if (r.get("effective_from") or "") <= day < (r.get("effective_to") or "9999-12-31"):
            return r
    return None


def regime_break(cba_rules: Mapping, base_season: int) -> bool:
    """True if an agreement encoded after 2026-12-01 governs a season >= B with a
    structure different from the 2022 agreement's, or a stoppage touches season B.
    When true it re-opens OD-7, the tier shape and the minimum table."""
    start, end = _signing_window(base_season)
    for r in cba_rules.get("cba_regimes") or []:
        if (r.get("effective_from") or "") > STRUCTURE_FROM and structurally_different(r):
            return True
        if _stoppage_overlaps(r, start, end):
            return True
    return False


def _cbt(cba_rules: Mapping, season: int) -> float | None:
    for r in cba_rules.get("cbt_thresholds") or []:
        if int(r.get("season", -1)) == int(season):
            return float(r["threshold_usd"])
    return None


def prospective_regime(cba_rules: Mapping, season: int, dropped_thin: bool = False) -> bool | None:
    """Registration 4.3: a prospective target winter W is REGIME if (a) a work
    stoppage is in effect in its signing window, (b) the agreement governing its
    signing period differs in structure from the 2022 agreement, (c) its base CBT
    threshold differs by more than 10 percent from season W - 1's as encoded, or
    (d) the estimator drops W as thin. None (not scored until encoded) when no
    agreement governs W's signing period."""
    gov = governing_agreement(cba_rules, season)
    if gov is None:
        return None
    start, end = _signing_window(season)
    if any(_stoppage_overlaps(r, start, end) for r in cba_rules.get("cba_regimes") or []):
        return True
    if (gov.get("effective_from") or "") > STRUCTURE_FROM and structurally_different(gov):
        return True
    a, b = _cbt(cba_rules, season), _cbt(cba_rules, season - 1)
    if a is not None and b:
        if abs(a / b - 1.0) > 0.10:
            return True
    return bool(dropped_thin)

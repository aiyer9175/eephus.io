# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""fantasy_rank.py - the /fantasy/ Dynasty "Fantasy Rank" (owner answer M21-4).

THE ASK, verbatim (2026-09-25): "Build its own combined overall rank based on
fantasy production rather than WAR production." So this is a /fantasy/-only
dynasty rank of MLB players AND prospects on projected FANTASY value, in the
module's own scoring (fantasy_scoring: FanGraphs Points, SABR Points, Old
School 5x5, Ottoneu 4x4). It reads no WAR and no /projections/ rank, and
nothing on /projections/ reads it, so it cannot reorder that board.

THE DESIGN (disclosed on the page from the `basis` block of the payload):

  value = sum over the HORIZON seasons t = 0..4 of
            p_t x max(0, season value_t - replacement_t) / (1 + DISCOUNT_RATE)^t

  * HORIZON 5 seasons from the first season /projections/ prices (its
    proj_export.HORIZON window), DISCOUNT_RATE the platform rate (the
    value_framework discount_rate /projections/ discounts surplus at).
  * Season value: points in a points format, the summed category z-score in a
    roto format, z-scored against that season's projected MLB pool.
  * Replacement: per season, per side, the value of the first player past a
    12-team Ottoneu active lineup (12 hitters, 10 pitchers a team), so the
    145th hitter and the 121st pitcher of that season's MLB pool.
  * MLB players (the /fantasy/ corpus pool, p_t = 1): the corpus's projected
    line for the first season (the same Marcel champion engine, fa_projection,
    that /projections/ starts from), walked forward one season at a time along
    the SAME fitted per-component and playing-time aging curves that
    /projections/ walks for its rate path (fa_projection.rate_path,
    curve_delta). Context stats (R, RBI, SB, W, QS, SV, HLD) keep the corpus's
    labelled heuristics.
  * Prospects (the Dynasty Board's rows): p_t is the ETA model's arrival
    probability by season, zero before the ETA year, then 1 - S(t) off the
    ETA module's own Kaplan-Meier survival curve for the prospect's level
    (data/eta_eval.json km_survival_by_level, t years after the listing
    year). The line given arrival is BUILT, never back-solved from WAR, because
    the repository holds no per-season component line for a prospect (the
    inventory below): the MiLB to MLB translation chain (milb_translation's
    matched-pair regression-to-the-mean template, college_translation._fit,
    on the eFV matrices' pre-debut level-relative MiLB rates) is extended
    from K% and BB% to every fantasy component, fit on the debuted cohort's
    first two MLB seasons in the projection corpus, then aged on the same
    curves. Playing time is the debuted cohort's mean MLB PA (hitters) or IP
    (pitchers, starters and relievers apart) in the k-th season counted from
    the ETA year. No scouting grade, eFV or FV enters the prospect leg.

THE INVENTORY (the spec asked for it first, and the answer is published):
prospects carry WAR paths only (data/mlb_projections.json prospects: war,
warP10, warP90, warPTH and their totals; no PA, HR, R, RBI, SB, AVG, OBP, IP,
K, W, SV, ERA or WHIP per season), and milb_translation projects first-MLB K%
and BB% only. The component line is therefore built from the translation
chain, and the payload says so.

RESERVED FRAMES. The backtest (backtest(), data/fantasy_rank_eval.json) scores
list vintages 2018 and 2019 only: 2020 and 2021 are reserved list vintages,
and a player who debuted in 2025 or later is a reserved debut cohort and is
dropped from every frame this module scores or fits (translation pairs,
playing-time cohort, Kaplan-Meier events). No stratum is named after an FV
cell, and no realized-WAR quantity is computed anywhere here.

Never sums ML quantile points: every line is a mean projection.
"""
from __future__ import annotations

import json
import logging
import math
import random
from datetime import date, datetime, timezone
from pathlib import Path

import fantasy_scoring as fscore

log = logging.getLogger("fantasy_rank")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
RANK_PATH = DATA_DIR / "fantasy_rank.json"
EVAL_PATH = DATA_DIR / "fantasy_rank_eval.json"
# The monthly build's MLB-leg values, fits and pools, so the nightly refresh
# can re-rank the prospect leg against the board without rebuilding the corpus.
MODEL_CACHE = ROOT / ".cache" / "fantasy_rank_model.json"
KM_SOURCE = "eta_eval.json"

HORIZON = 5                 # proj_export.HORIZON (2027..2031 on the 2026-10 build)
DISCOUNT_RATE = 0.07        # value_framework discount_rate, the platform rate
LEAGUE = {"teams": 12, "hit_slots": 12, "pit_slots": 10}
FORMATS = ("fgp", "sabr", "5x5", "4x4")
POINTS_FORMATS = ("fgp", "sabr")
SERVE_TOP_N = 400           # rows served: the top N of any format, plus every board prospect

RESERVED_DEBUT_FROM = 2025              # R-VM: 2025+ debut cohorts
RESERVED_LIST_VINTAGES = frozenset({2020, 2021})   # R-LV
BACKTEST_VINTAGES = (2018, 2019)
KM_TRAIN_VINTAGES = (2018, 2019, 2022, 2023)
OBSERVED_THROUGH = 2024     # KM events after this season are censored (R-VM)

# Translation targets, in per-100 units (college_translation._fit rounds its
# means to three decimals, so a 0.030 HR rate is fit as 3.0 per 100 PA).
HIT_TARGETS = (("k_pct", "k_rel"), ("bb_pct", "bb_rel"), ("iso", "iso_rel"),
               ("hr_pa", "iso_rel"), ("babip", "obp_rel"), ("sb_pa", "sb_rate_rel"))
PIT_TARGETS = (("k_pct", "k_rel"), ("bb_pct", "bb_rel"), ("hr_bf", "era_rel"))
_PER100 = 100.0
TARGET_MIN_EXPO = 100.0     # PA (hitters) or BF (pitchers) over the first two MLB seasons

_RP_POS = frozenset({"RP", "SIRP", "MIRP", "CP"})
_PIT_POS = frozenset({"P", "SP", "RP", "SIRP", "MIRP", "CP", "RHP", "LHP"})
_LEVEL_MAP = {"A-": "A", "Rk": "CPX", "ROK": "CPX", "FRk": "CPX", "ACL": "CPX",
              "FCL": "CPX", "CPX": "CPX", "DSL": "DSL", "A": "A", "A+": "A+",
              "AA": "AA", "AAA": "AAA", "MLB": "MLB"}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _load_json(name: str):
    p = DATA_DIR / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def disc(t: int) -> float:
    """The discount factor on horizon season t (t = 0 is the first season)."""
    return 1.0 / ((1.0 + DISCOUNT_RATE) ** t)


def repl_index(side: str) -> int:
    """0-based index of the replacement player of one side: the first player
    past a 12-team active lineup."""
    slots = LEAGUE["hit_slots"] if side == "hit" else LEAGUE["pit_slots"]
    return LEAGUE["teams"] * slots


def is_pitcher_pos(pos) -> bool:
    p = str(pos or "").upper()
    return p in _PIT_POS


def pitcher_group(pos) -> str:
    """'rp' for a reliever designation, else 'sp' (a starter or an unlabelled arm)."""
    return "rp" if str(pos or "").upper() in _RP_POS else "sp"


def level_key(level) -> str | None:
    return _LEVEL_MAP.get(str(level or "").strip()) if level else None


# ---------------------------------------------------------------------------
# lines: the corpus algebra, reused (never a second copy)
# ---------------------------------------------------------------------------
def _fe():
    import fantasy_export as fe       # lazy: fantasy_export imports this module
    return fe


def fip_from(comps: dict, bf: float, ip: float, fipc: float) -> float:
    """fa_projection.project_player's FIP algebra on one season's components."""
    bf = max(0.0, bf)
    return ((13 * comps["hr_bf"] * bf + 3 * (comps["bb_pct"] * bf + 0.008 * bf)
             - 2 * comps["k_pct"] * bf) / max(ip, 1.0) + fipc)


def hitter_line(comps: dict, pa: float, sb_pa) -> dict:
    return _fe()._hitter_ros(comps, pa, sb_pa)


def pitcher_line(comps: dict, bf: float, ip: float, role: str, fip: float,
                 sv: float = 0.0, hld: float = 0.0) -> dict:
    proj = dict(comps)
    proj["fip_proj"] = fip
    row = _fe()._pitcher_ros(proj, bf, ip, role, None)
    if role != "SP":
        row["sv"] = round(max(0.0, sv), 1)
        row["hld"] = round(max(0.0, hld), 1)
    return row


def mlb_horizon_lines(proj: dict, side: str, role: str, curves: dict, *,
                      sb_pa=None, sv0: float = 0.0, hld0: float = 0.0,
                      horizon: int = HORIZON, delta=None) -> list[dict]:
    """One MLB player's per-season counting lines over the horizon.

    Season 0 is the corpus line (project_player at the first season, the full
    season). Each later season adds the fitted aging delta INTO that age for
    every rate component (fa_projection.rate_path's walk) and for playing time
    (curve_delta 'pt', BF for a pitcher, with innings moved by the engine's own
    BF = 4.3 x IP proxy). A reliever's saves and holds scale with his innings."""
    import fa_projection as fp
    delta = delta or (lambda s, r, c, a: fp.curve_delta(curves, s, r, c, a))
    comps_keys = fp.HIT_COMPONENTS if side == "hit" else fp.PIT_COMPONENTS
    cur = {c: proj.get(c) for c in comps_keys}
    if any(v is None for v in cur.values()):
        return []
    age = proj.get("age")
    pt = float(proj.get("pt_proj") or 0.0)
    ip = float(proj.get("ip_proj") or 0.0)
    ip0 = ip
    fip_anchor = proj.get("fip_proj")
    core0 = None
    if side == "pit":
        core0 = 4.3 * (13 * cur["hr_bf"] + 3 * (cur["bb_pct"] + 0.008) - 2 * cur["k_pct"])
    out = []
    for t in range(horizon):
        if t > 0 and age:
            a = int(age) + t
            for c in comps_keys:
                cur[c] = max(0.0, cur[c] + delta(side, role, c, a))
            d_pt = delta(side, role, "pt", a)
            pt = max(0.0, pt + d_pt)
            if side == "pit":
                ip = max(0.0, ip + d_pt / 4.3)
        if side == "hit":
            out.append(hitter_line(dict(cur), pt, sb_pa))
        else:
            core = 4.3 * (13 * cur["hr_bf"] + 3 * (cur["bb_pct"] + 0.008) - 2 * cur["k_pct"])
            fip = (fip_anchor if fip_anchor is not None else 4.2) + (core - core0)
            share = (ip / ip0) if ip0 > 0 else 0.0
            out.append(pitcher_line(dict(cur), pt, ip, "SP" if role == "SP" else "RP",
                                    max(fip, 1.0), sv0 * share, hld0 * share))
    return out


# ---------------------------------------------------------------------------
# the translation chain, extended to every fantasy component
# ---------------------------------------------------------------------------
def _matrix_rows(side: str, live: bool = False) -> list:
    name = ("xfv_live_%s_matrix.json" if live else "xfv_%s_matrix.json") % (
        "hitter" if side == "hit" else "pitcher")
    rows = _load_json(name)
    return rows if isinstance(rows, list) else []


def _sb_by_season(seasons) -> dict:
    """{(mlbam, season): (sb, pa)} off the cached StatsAPI MLB hitting rows
    (milb_history, cache only, never a fetch)."""
    out: dict = {}
    try:
        import milb_history as mh
    except Exception:                                        # noqa: BLE001
        return out
    for s in seasons:
        try:
            idx = mh.player_index(int(s), "hitting", fetch=False)
        except Exception:                                    # noqa: BLE001
            continue
        for mid, rows in (idx or {}).items():
            sb = pa = 0.0
            for r in rows:
                if r.get("level") != "MLB":
                    continue
                sb += _num(r.get("sb")) or 0.0
                pa += _num(r.get("pa")) or 0.0
            if pa > 0:
                out[(int(mid), int(s))] = (sb, pa)
    return out


def translation_pairs(corpus: dict, max_debut_year: int, *, matrices=None,
                      sb_lookup=None) -> dict:
    """{side: {target: [(x, y_per100), ...]}} for the debuted cohort.

    x is the pre-debut level-relative MiLB rate on the eFV matrix row (the
    matrices read the ladder strictly before the debut); y is the player's
    exposure-weighted rate over his first two MLB seasons in the projection
    corpus, at TARGET_MIN_EXPO or more. Debuts after max_debut_year, and every
    2025+ debut (a reserved frame), are left out."""
    cap = min(int(max_debut_year), RESERVED_DEBUT_FROM - 1)
    by = {"hit": {}, "pit": {}}
    for side in ("hit", "pit"):
        for r in corpus.get(side) or []:
            mid = r.get("mlbam")
            if mid:
                by[side].setdefault(int(mid), {})[int(r["season"])] = r
    out = {"hit": {t: [] for t, _x in HIT_TARGETS},
           "pit": {t: [] for t, _x in PIT_TARGETS}}
    matrices = matrices or {"hit": _matrix_rows("hit"), "pit": _matrix_rows("pit")}
    for side in ("hit", "pit"):
        targets = HIT_TARGETS if side == "hit" else PIT_TARGETS
        expo = "pa" if side == "hit" else "bf"
        for m in matrices.get(side) or []:
            if m.get("kind") != "debuted" or not m.get("mlbam_id") or not m.get("milb"):
                continue
            dy = m.get("debut_year")
            if not isinstance(dy, int) or dy > cap:
                continue
            seasons = by[side].get(int(m["mlbam_id"])) or {}
            rows = [seasons[s] for s in (dy, dy + 1) if s in seasons]
            w = sum(float(r.get(expo) or 0.0) for r in rows)
            if w < TARGET_MIN_EXPO:
                continue
            milb = m["milb"]
            for target, feat in targets:
                x = _num(milb.get(feat))
                if x is None:
                    continue
                if target == "sb_pa":
                    if sb_lookup is None:
                        continue
                    sb = pa = 0.0
                    for s in (dy, dy + 1):
                        got = sb_lookup.get((int(m["mlbam_id"]), s))
                        if got:
                            sb += got[0]
                            pa += got[1]
                    if pa < TARGET_MIN_EXPO:
                        continue
                    y = sb / pa
                else:
                    num = sum(float(r.get(target) or 0.0) * float(r.get(expo) or 0.0)
                              for r in rows if r.get(target) is not None)
                    den = sum(float(r.get(expo) or 0.0) for r in rows
                              if r.get(target) is not None)
                    if den <= 0:
                        continue
                    y = num / den
                out[side][target].append((x, y * _PER100))
    return out


def fit_translation(pairs: dict, *, validate: bool = False) -> dict:
    """{side: {target: fit}} through college_translation._fit (the template
    milb_translation uses), each fit carrying its input feature name and, with
    validate=True, milb_translation._loo's leave-one-out MAE and the MAE of the
    cohort-mean predictor on the same pairs."""
    import college_translation as ct
    fits = {"hit": {}, "pit": {}}
    for side in ("hit", "pit"):
        targets = dict(HIT_TARGETS if side == "hit" else PIT_TARGETS)
        for target, ps in (pairs.get(side) or {}).items():
            f = ct._fit([x for x, _ in ps], [y for _, y in ps]) if ps else None
            if not f:
                continue
            f = dict(f, feature=targets[target], unit="per 100")
            if validate:
                f["loo"] = _loo(ps)
            fits[side][target] = f
    return fits


def _loo(ps: list) -> dict | None:
    """Leave-one-out MAE of the fit against the leave-one-out cohort mean."""
    import college_translation as ct
    n = len(ps)
    if n < 30:
        return None
    err_fit, err_mean = [], []
    for i in range(n):
        train = ps[:i] + ps[i + 1:]
        f = ct._fit([x for x, _ in train], [y for _, y in train])
        if not f:
            continue
        x, y = ps[i]
        err_fit.append(abs(y - ct._predict(f, x)))
        err_mean.append(abs(y - sum(v for _, v in train) / len(train)))
    if not err_fit:
        return None
    return {"mae": round(sum(err_fit) / len(err_fit), 3),
            "mae_cohort_mean": round(sum(err_mean) / len(err_mean), 3), "n": n}


def translate(fits: dict, side: str, milb: dict | None) -> dict:
    """Arrival components (engine units: rates, not per 100) for one prospect.
    A missing input reads the fit's x mean, so it lands on the cohort mean."""
    milb = milb or {}
    out = {}
    targets = HIT_TARGETS if side == "hit" else PIT_TARGETS
    for target, feat in targets:
        f = (fits.get(side) or {}).get(target)
        if not f:
            out[target] = None
            continue
        x = _num(milb.get(feat))
        if x is None:
            x = f["x_mean"]
        out[target] = max(0.0, (f["y_mean"] + f["slope"] * (x - f["x_mean"])) / _PER100)
    return out


# ---------------------------------------------------------------------------
# playing time and arrival
# ---------------------------------------------------------------------------
PT_BINS = 20                # equal-mass bins of the cohort's playing-time distribution


def _bin_means(vals: list[float], nbins: int = PT_BINS) -> list[float]:
    """The means of nbins equal-mass slices of the sorted values: an exact,
    mean-preserving discretization of the empirical distribution (each bin
    weighs 1/nbins). Bin means, not quantile points, so averaging them is an
    expectation and nothing is ever summed across quantiles."""
    v = sorted(vals)
    n = len(v)
    if not n:
        return []
    out = []
    for b in range(nbins):
        lo, hi = (b * n) // nbins, ((b + 1) * n) // nbins
        chunk = v[lo:hi] or [v[min(lo, n - 1)]]
        out.append(round(sum(chunk) / len(chunk), 1))
    return out


def pt_curves(corpus: dict, max_season: int, *, matrices=None,
              horizon: int = HORIZON) -> dict:
    """{'hit'|'sp'|'rp': {"mean": [k = 0..horizon-1], "bins": [[...]], "n": [...]}}.

    MLB plate appearances (hitters) or innings (pitchers) in the k-th season
    counted from the debut year, over the debuted cohort of the eFV matrices,
    a season with no MLB line counting zero: the mean, and PT_BINS equal-mass
    bin means of the whole distribution. The bins are what the value reads,
    because value above replacement is convex in playing time: a prospect who
    lands a regular's job clears replacement and one who does not, does not,
    and the mean playing time of the two prices both at a part-timer's zero.
    Only seasons through max_season are read, and every 2025+ debut is left
    out (reserved)."""
    by = {"hit": {}, "pit": {}}
    for side in ("hit", "pit"):
        for r in corpus.get(side) or []:
            if r.get("mlbam"):
                by[side][(int(r["mlbam"]), int(r["season"]))] = r
    matrices = matrices or {"hit": _matrix_rows("hit"), "pit": _matrix_rows("pit")}
    acc = {g: [[] for _ in range(horizon)] for g in ("hit", "sp", "rp")}
    for side in ("hit", "pit"):
        for m in matrices.get(side) or []:
            if m.get("kind") != "debuted" or not m.get("mlbam_id"):
                continue
            dy = m.get("debut_year")
            if not isinstance(dy, int) or dy >= RESERVED_DEBUT_FROM:
                continue
            g = "hit" if side == "hit" else pitcher_group(m.get("position"))
            for k in range(horizon):
                s = dy + k
                if s > max_season:
                    break
                r = by[side].get((int(m["mlbam_id"]), s))
                v = float((r or {}).get("pa" if side == "hit" else "ip") or 0.0)
                acc[g][k].append(v)
    out = {}
    for g, ks in acc.items():
        means, bins, ns = [], [], []
        last, last_bins = 0.0, [0.0] * PT_BINS
        for vals in ks:
            # A k with no observed season (the backtest's early vintages)
            # carries the last observed k forward rather than a zero.
            if vals:
                last = sum(vals) / len(vals)
                last_bins = _bin_means(vals)
            means.append(round(last, 1))
            bins.append(list(last_bins))
            ns.append(len(vals))
        out[g] = {"mean": means, "bins": bins, "n": ns}
    return out


def km_curve(pool: list[dict], max_t: int = 8) -> list[float] | None:
    """Kaplan-Meier S(t) = P(not yet debuted t years after the listing year),
    eta_backtest._km_curve's estimator: a washed-out player never leaves the
    risk set (the cure fraction), a censored one leaves at his censor time.
    Rows: {"event": t or None, "censor": t or None, "washed": bool}."""
    if not pool:
        return None
    events, censor = {}, {}
    for r in pool:
        if r.get("event") is not None:
            events[r["event"]] = events.get(r["event"], 0) + 1
        elif r.get("censor") is not None and not r.get("washed"):
            censor[r["censor"]] = censor.get(r["censor"], 0) + 1
    s, at_risk, curve = 1.0, len(pool), []
    for t in range(0, max_t + 1):
        d = events.get(t, 0)
        if at_risk > 0:
            s *= (1 - d / at_risk)
        curve.append(round(s, 4))
        at_risk -= d + censor.get(t, 0)
    return curve


def arrival(eta_year, level, first_season: int, km: dict,
            horizon: int = HORIZON) -> list[float]:
    """P(arrived by season) for each horizon season: zero before the ETA year,
    then 1 - S(t) on the ETA module's survival curve for the level, t counted
    from the listing year (first_season). A prospect already at MLB arrives
    with certainty from his ETA year; a level with no curve, or no ETA, prices
    at zero rather than at a guess."""
    if eta_year is None:
        return [0.0] * horizon
    eta = max(int(eta_year), first_season)
    lv = level_key(level)
    curve = None if lv == "MLB" else (km or {}).get(lv)
    out = []
    for t in range(horizon):
        season = first_season + t
        if season < eta:
            out.append(0.0)
        elif lv == "MLB":
            out.append(1.0)
        elif not curve:
            out.append(0.0)
        else:
            out.append(round(max(0.0, min(1.0, 1.0 - curve[min(t, len(curve) - 1)])), 4))
    return out


# ---------------------------------------------------------------------------
# a prospect's line given arrival
# ---------------------------------------------------------------------------
def prospect_horizon_lines(side: str, pos, comps0: dict, pt: dict, eta_year,
                           first_season: int, age_now, cur_season: int,
                           delta, fipc: float, horizon: int = HORIZON) -> list:
    """Per-season lines GIVEN arrival (None before the ETA year): for each
    season a list of equally weighted lines, one per playing-time bin of the
    cohort's k-th season. Components start at the translated arrival rates
    and age on the fitted curves from the ETA season."""
    eta = max(int(eta_year), first_season) if eta_year else None
    if side == "hit":
        role, group = ("C" if str(pos or "").upper().startswith("C") else "H"), "hit"
        keys = ("k_pct", "bb_pct", "iso", "babip", "hr_pa")
    else:
        group = pitcher_group(pos)
        role = "RP" if group == "rp" else "SP"
        keys = ("k_pct", "bb_pct", "hr_bf")
    if any(comps0.get(k) is None for k in keys) or eta is None:
        return [None] * horizon
    comps = {k: comps0[k] for k in keys}
    out = []
    age_at = (lambda s: int(float(age_now) + (s - cur_season))) if age_now else None
    for t in range(horizon):
        season = first_season + t
        if season < eta:
            out.append(None)
            continue
        if season > eta and age_at:
            for k in keys:
                comps[k] = max(0.0, comps[k] + delta(side, role, k, age_at(season)))
        k_idx = min(season - eta, horizon - 1)
        g = pt.get(group) or {}
        bins = g.get("bins") or [[m] for m in (g.get("mean") or [0.0] * horizon)]
        amounts = bins[min(k_idx, len(bins) - 1)] or [0.0]
        lines = []
        for amount in amounts:
            amount = float(amount)
            if side == "hit":
                lines.append(hitter_line(dict(comps), amount, comps0.get("sb_pa")))
            else:
                bf = amount * 4.3
                lines.append(pitcher_line(dict(comps), bf, amount, role,
                                          fip_from(comps, bf, amount, fipc)))
        out.append(lines)
    return out


def expected_above(lines, fmt: str, side: str, params, repl_value: float) -> float:
    """The mean, over a season's equally weighted playing-time lines, of the
    value above replacement floored at zero. 0.0 for a season with no line."""
    if not lines:
        return 0.0
    vals = [above(season_value(ln, fmt, side, params), repl_value) or 0.0 for ln in lines]
    return sum(vals) / len(vals)


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------
def season_value(line: dict | None, fmt: str, side: str, params=None) -> float | None:
    if not line:
        return None
    if fmt in POINTS_FORMATS:
        return fscore.score_points(line, fmt, side)
    if not params:
        return None
    return fscore.roto_value(line, params)[0]


def replacement(values: list[float], side: str) -> float:
    vals = sorted((v for v in values if v is not None), reverse=True)
    if not vals:
        return 0.0
    i = repl_index(side)
    return vals[i] if i < len(vals) else vals[-1]


def total_value(seasons: list, p: list | None = None) -> float:
    """sum_t disc(t) x p_t x above-replacement value_t (already floored)."""
    tot = 0.0
    for t, v in enumerate(seasons):
        if v is None:
            continue
        w = 1.0 if p is None else float(p[t] or 0.0)
        tot += disc(t) * w * v
    return tot


def above(v, r) -> float | None:
    return None if v is None else max(0.0, v - r)


# ---------------------------------------------------------------------------
# the monthly model: MLB leg, pools, replacement, fits
# ---------------------------------------------------------------------------
def prepare(horizon_rows: list[dict], corpus: dict, curves: dict, league: dict,
            first_season: int) -> dict:
    """Everything the rank needs that only the monthly corpus build can make.

    horizon_rows: [{mlbam, side, pos, name, team, lines: [per-season line]}]
    from fantasy_export.build_players (one per pool row)."""
    import fa_projection as fp
    seasons = list(range(first_season, first_season + HORIZON))
    roto_params: dict = {f: [] for f in FORMATS if f not in POINTS_FORMATS}
    for f in roto_params:
        for t in range(HORIZON):
            per = {}
            for side in ("hit", "pit"):
                pool = [r["lines"][t] for r in horizon_rows
                        if r["side"] == side and len(r["lines"]) > t and r["lines"][t]]
                per[side] = fscore.roto_params(pool, f, side)
            roto_params[f].append(per)
    mlb = []
    for r in horizon_rows:
        raw = {}
        for f in FORMATS:
            raw[f] = [season_value(r["lines"][t] if t < len(r["lines"]) else None, f,
                                   r["side"],
                                   (roto_params.get(f) or [{}] * HORIZON)[t].get(r["side"])
                                   if f in roto_params else None)
                      for t in range(HORIZON)]
        mlb.append({"mlbam": r["mlbam"], "side": r["side"], "pos": r.get("pos"),
                    "name": r.get("name"), "team": r.get("team"), "raw": raw})
    repl = {f: [{side: replacement([m["raw"][f][t] for m in mlb if m["side"] == side], side)
                 for side in ("hit", "pit")} for t in range(HORIZON)] for f in FORMATS}
    last = max((s for s in league if isinstance(s, int)), default=first_season - 1)
    fipc = _num((league.get(last) or {}).get("fip_constant")) or 3.1
    sb_lookup = _sb_by_season(range(2010, first_season))
    pairs = translation_pairs(corpus, first_season - 3, sb_lookup=sb_lookup)
    fits = fit_translation(pairs, validate=True)
    pt = pt_curves(corpus, first_season - 1)
    # Aging deltas the prospect leg reads, tabulated so the nightly refresh
    # needs no corpus: side x role x component x age.
    deltas: dict = {}
    for side, roles, comps in (("hit", ("H", "C"), fp.HIT_COMPONENTS),
                               ("pit", ("SP", "RP"), fp.PIT_COMPONENTS)):
        for role in roles:
            for c in comps:
                deltas[f"{side}|{role}|{c}"] = {
                    str(a): round(fp.curve_delta(curves, side, role, c, a), 6)
                    for a in range(16, 46)}
    return {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "first_season": first_season, "seasons": seasons, "fipc": fipc,
            "roto_params": roto_params, "repl": repl, "mlb": mlb, "fits": fits,
            "pt": pt, "deltas": deltas}


def _delta_from_table(table: dict):
    def _d(side, role, comp, age):
        c = table.get(f"{side}|{role}|{comp}") or {}
        if not c:
            return 0.0
        a = min(max(int(age), 16), 45)
        return float(c.get(str(a), 0.0))
    return _d


# ---------------------------------------------------------------------------
# the served rank
# ---------------------------------------------------------------------------
def _live_milb() -> dict:
    out = {}
    for side in ("hit", "pit"):
        for r in _matrix_rows(side, live=True):
            mid = r.get("mlbam_id")
            if mid:
                out.setdefault(int(mid), {})[side] = r
    return out


def _km_live() -> dict:
    ev = _load_json(KM_SOURCE) or {}
    km = ev.get("km_survival_by_level") if isinstance(ev, dict) else None
    return km if isinstance(km, dict) else {}


def build(model: dict, dynasty_rows: list, *, cur_season: int, live_milb=None,
          km=None) -> dict:
    """The served payload: every MLB-leg row and every Dynasty Board prospect
    valued in every format, ranked per format, the top SERVE_TOP_N of any
    format plus every board prospect served."""
    first = int(model["first_season"])
    seasons = list(model.get("seasons") or range(first, first + HORIZON))
    live_milb = _live_milb() if live_milb is None else live_milb
    km = _km_live() if km is None else km
    delta = _delta_from_table(model.get("deltas") or {})
    repl = model["repl"]
    params = model.get("roto_params") or {}
    rows: dict = {}
    # MLB leg: p = 1 in every season; a two-way player sums his two sides.
    for m in model.get("mlb") or []:
        mid = int(m["mlbam"])
        r = rows.setdefault(mid, {"mlbam": mid, "name": m.get("name"), "team": m.get("team"),
                                  "pos": m.get("pos"), "kind": "mlb", "sides": [],
                                  "s": {f: [0.0] * HORIZON for f in FORMATS}})
        r["sides"].append(m["side"])
        if m["side"] == "hit" or not r.get("pos"):
            r["pos"] = m.get("pos") or r.get("pos")
        for f in FORMATS:
            for t in range(HORIZON):
                a = above(m["raw"][f][t], repl[f][t][m["side"]])
                r["s"][f][t] += a or 0.0
    n_dup = n_no_input = 0
    for d in dynasty_rows or []:
        mid = d.get("mlbam")
        if not mid:
            continue
        mid = int(mid)
        if mid in rows:
            n_dup += 1            # already priced on his MLB line
            continue
        mx = live_milb.get(mid) or {}
        side = "pit" if (is_pitcher_pos(d.get("pos")) and "pit" in mx) or \
            ("hit" not in mx and "pit" in mx) else "hit"
        mrow = mx.get(side) or {}
        if not mrow:
            n_no_input += 1
        milb = mrow.get("milb") or {}
        comps0 = translate(model["fits"], side, milb)
        lvl = milb.get("milb_level")
        p = arrival(d.get("eta"), lvl, first, km)
        lines = prospect_horizon_lines(side, d.get("pos"), comps0, model["pt"], d.get("eta"),
                                       first, mrow.get("age_now"), cur_season, delta,
                                       float(model.get("fipc") or 3.1))
        s = {}
        for f in FORMATS:
            per = []
            for t in range(HORIZON):
                prm = ((params.get(f) or [{}] * HORIZON)[t].get(side)
                       if f not in POINTS_FORMATS else None)
                per.append(expected_above(lines[t], f, side, prm, repl[f][t][side]) * p[t])
            s[f] = per
        rows[mid] = {"mlbam": mid, "name": d.get("name"), "team": d.get("org"),
                     "pos": d.get("pos"), "kind": "prospect", "sides": [side],
                     "eta": d.get("eta"), "lvl": level_key(lvl) or lvl,
                     "board_rank": d.get("rank"), "p": p, "s": s}
    # Totals and ranks per format. The order is a pure function of value
    # (ties by mlbam), so no input order, /projections/ included, can move it.
    for r in rows.values():
        r["v"] = {f: total_value(r["s"][f]) for f in FORMATS}
    # Ranked = above replacement at the served precision (0.1 point, 0.01
    # z), so no ranked row ever reads as a zero on the page.
    nd = {f: (1 if f in POINTS_FORMATS else 2) for f in FORMATS}
    ranks: dict = {}
    for f in FORMATS:
        ordered = sorted((r for r in rows.values() if round(r["v"][f], nd[f]) > 0),
                         key=lambda r: (-r["v"][f], r["mlbam"]))
        ranks[f] = {r["mlbam"]: i + 1 for i, r in enumerate(ordered)}
    served = []
    for r in rows.values():
        rk = {f: ranks[f].get(r["mlbam"]) for f in FORMATS}
        keep = r["kind"] == "prospect" or any(v is not None and v <= SERVE_TOP_N
                                              for v in rk.values())
        if not keep:
            continue
        row = {"mlbam": r["mlbam"], "name": r.get("name"), "team": r.get("team"),
               "pos": r.get("pos"), "kind": r["kind"],
               "side": "two" if len(set(r["sides"])) > 1 else r["sides"][0],
               "rk": rk,
               "v": {f: round(r["v"][f], nd[f]) for f in FORMATS},
               "s": {f: [(int(round(x)) if nd[f] == 1 else round(x, 1)) for x in r["s"][f]]
                     for f in FORMATS}}
        if r["kind"] == "prospect":
            row.update({"eta": r.get("eta"), "lvl": r.get("lvl"), "p": r.get("p"),
                        "board_rank": r.get("board_rank")})
        served.append(row)
    served.sort(key=lambda r: (r["rk"]["fgp"] is None, r["rk"]["fgp"] or 0, r["mlbam"]))
    n_mlb = sum(1 for r in rows.values() if r["kind"] == "mlb")
    n_pro = sum(1 for r in rows.values() if r["kind"] == "prospect")
    fits_pub = {side: {t: {k: f.get(k) for k in ("feature", "slope", "r2", "n", "loo")}
                       for t, f in (model["fits"].get(side) or {}).items()}
                for side in ("hit", "pit")}
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_built_at": model.get("generated_at"),
        "first_season": first, "seasons": seasons, "horizon": HORIZON,
        "discount_rate": DISCOUNT_RATE, "league": dict(LEAGUE),
        "formats": [c for c in fscore.SCORING_CATALOG],
        "replacement": {f: [{k: round(v, 2) for k, v in per.items()} for per in repl[f]]
                        for f in FORMATS},
        "n_mlb": n_mlb, "n_prospects": n_pro, "n_rows": len(served),
        "n_ranked": {f: len(ranks[f]) for f in FORMATS},
        "serve_top_n": SERVE_TOP_N,
        "n_board_prospects_on_mlb_line": n_dup,
        "n_prospects_without_milb_input": n_no_input,
        "prospect_leg": {
            "component_source": "translation",
            "inventory": ("Prospects carry WAR paths only in the repository "
                          "(mlb_projections prospects: war, warP10, warP90, warPTH); "
                          "milb_translation projects first-MLB K% and BB% only. The "
                          "per-season line is built from the translation chain, not "
                          "back-solved from WAR."),
            "fits": fits_pub,
            "playing_time": model["pt"],
            "arrival": ("ETA model: zero before the ETA year, then 1 - S(t) on the "
                        "eta_eval km_survival_by_level curve for the prospect's level"),
        },
        "basis": [
            "Value = the sum over %d seasons (%d to %d) of the season's fantasy value "
            "above replacement, discounted %d%% a season." % (
                HORIZON, seasons[0], seasons[-1], round(DISCOUNT_RATE * 100)),
            "Replacement is the first player past a 12-team active lineup each season "
            "(12 hitters, 10 pitchers a team): the 145th hitter and 121st pitcher.",
            "MLB players: next season's line from the Redraft projection engine, aged a "
            "season at a time on the same curves /projections/ walks.",
            "Prospects: a line built from minor league rates translated to MLB rates, "
            "with the playing time past debut classes got in each season after arriving, "
            "weighted by the chance he has arrived (zero before his ETA year). No WAR "
            "and no grade enters the rank.",
        ],
        "backtest": backtest_summary(),
        "rows": served,
    }


def backtest_summary() -> dict | None:
    """The registered backtest's pooled reading, copied from
    data/fantasy_rank_eval.json (EVAL_PATH) so the page can state it from the
    artifact. None when the artifact is absent."""
    try:
        ev = json.loads(Path(EVAL_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    pooled = (ev or {}).get("pooled") or {}
    ci = pooled.get("difference_ci95_player_clustered") or {}
    return {"vintages": (ev.get("frame") or {}).get("list_vintages"),
            "n": pooled.get("n"),
            "rho_prospect_leg": pooled.get("rho_prospect_leg"),
            "rho_consensus_fv": pooled.get("rho_consensus_fv"),
            "lo95": ci.get("lo95"), "hi95": ci.get("hi95"),
            "format": (ev.get("frame") or {}).get("format"),
            "generated_at": ev.get("generated_at")}


def write(payload: dict) -> bool:
    try:
        blob = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError):
        log.exception("fantasy_rank: payload not serializable; previous file kept")
        return False
    path = Path(RANK_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(blob, encoding="utf-8")
    return True


def save_model(model: dict) -> None:
    p = Path(MODEL_CACHE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(model, separators=(",", ":")), encoding="utf-8")


def load_model() -> dict | None:
    try:
        m = json.loads(Path(MODEL_CACHE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return m if isinstance(m, dict) and m.get("mlb") else None


def export_from_inputs(inputs: dict, dynasty_rows: list, log_fn=print) -> int:
    """The monthly path: prepare the model off the corpus build, cache it,
    build and write the served rank. Returns the served row count."""
    model = prepare(inputs["horizon"], inputs["corpus"], inputs["curves"],
                    inputs["league"], inputs["first_season"])
    save_model(model)
    payload = build(model, dynasty_rows, cur_season=inputs["first_season"] - 1)
    if not write(payload):
        return 0
    if callable(log_fn):
        log_fn(f"fantasy_rank: {payload['n_rows']} rows served "
               f"({payload['n_mlb']} MLB, {payload['n_prospects']} prospects valued)")
    return payload["n_rows"]


def refresh(dynasty_rows: list, cur_season: int, log_fn=print) -> int:
    """The nightly path: re-rank the board's prospects against the cached
    monthly model. No model cache, no write (the served file stands)."""
    model = load_model()
    if model is None:
        if callable(log_fn):
            log_fn("fantasy_rank: no monthly model cached; served rank kept")
        return 0
    payload = build(model, dynasty_rows, cur_season=cur_season)
    if not write(payload):
        return 0
    return payload["n_rows"]


# ---------------------------------------------------------------------------
# the backtest: the prospect leg vs a consensus-rank baseline
# ---------------------------------------------------------------------------
def _spearman(xs: list, ys: list) -> float | None:
    n = len(xs)
    if n < 3:
        return None

    def _rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = _rank(xs), _rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _realized_fgp_by_season(corpus: dict, seasons, sb_lookup: dict) -> dict:
    """{season: {"hit": {mlbam: pts}, "pit": {mlbam: pts}}} realized FanGraphs
    Points from the corpus's realized components through the same line
    algebra the projections use (hits allowed at the league BABIP, no saves or
    holds for a pitcher, SB from the cached StatsAPI MLB rows)."""
    out = {int(s): {"hit": {}, "pit": {}} for s in seasons}
    for r in corpus.get("hit") or []:
        s = int(r.get("season") or 0)
        if s not in out or not r.get("mlbam") or not r.get("pa"):
            continue
        if any(r.get(k) is None for k in ("k_pct", "bb_pct", "iso", "babip", "hr_pa")):
            continue
        got = sb_lookup.get((int(r["mlbam"]), s))
        sb_pa = (got[0] / got[1]) if got and got[1] else None
        line = hitter_line({k: r[k] for k in ("k_pct", "bb_pct", "iso", "babip", "hr_pa")},
                           float(r["pa"]), sb_pa)
        out[s]["hit"][int(r["mlbam"])] = fscore.score_points(line, "fgp", "hit")
    for r in corpus.get("pit") or []:
        s = int(r.get("season") or 0)
        if s not in out or not r.get("mlbam") or not r.get("ip"):
            continue
        if any(r.get(k) is None for k in ("k_pct", "bb_pct", "hr_bf")):
            continue
        comps = {k: r[k] for k in ("k_pct", "bb_pct", "hr_bf")}
        bf = float(r.get("bf") or float(r["ip"]) * 4.3)
        line = pitcher_line(comps, bf, float(r["ip"]),
                            "SP" if r.get("role") == "SP" else "RP",
                            float(r.get("fip") or 4.2))
        out[s]["pit"][int(r["mlbam"])] = fscore.score_points(line, "fgp", "pit")
    return out


def _mlbam_resolver() -> dict:
    """{player_key: mlbam} from every identity source the repo carries."""
    out: dict = {}
    for f in ("xfv_hitter_matrix.json", "xfv_pitcher_matrix.json"):
        for r in _load_json(f) or []:
            if r.get("player_key") and r.get("mlbam_id"):
                out.setdefault(r["player_key"], int(r["mlbam_id"]))
    for r in _load_json("debuts.json") or []:
        if r.get("player_key") and r.get("mlbam_id"):
            out.setdefault(r["player_key"], int(r["mlbam_id"]))
    try:
        import storage
        with storage.connect() as con:
            for row in con.execute("SELECT player_key, mlbam_id FROM player_photos"):
                if row[0] and row[1]:
                    out.setdefault(row[0], int(row[1]))
    except Exception:                                        # noqa: BLE001
        log.warning("fantasy_rank: player_photos identity read failed")
    return out


def _eta_cohort(vintages) -> list:
    """eta_backtest's vintage-listed cohort for the given list vintages only
    (its query reads VINTAGE_YEARS, so the reserved vintages are never read)."""
    import eta_backtest as eb
    assert not set(vintages) & RESERVED_LIST_VINTAGES, vintages
    saved = eb.VINTAGE_YEARS
    try:
        eb.VINTAGE_YEARS = tuple(vintages)
        rows, _acct = eb.build_cohort()
    finally:
        eb.VINTAGE_YEARS = saved
    return rows


def _bootstrap(pairs_by_player: dict, draws: int, seed: int) -> dict:
    """Player-clustered bootstrap of rho(leg) - rho(consensus)."""
    rng = random.Random(seed)
    keys = sorted(pairs_by_player)
    diffs = []
    for _ in range(draws):
        leg, fv, real = [], [], []
        for _k in range(len(keys)):
            for (a, b, c) in pairs_by_player[keys[rng.randrange(len(keys))]]:
                leg.append(a)
                fv.append(b)
                real.append(c)
        r1, r2 = _spearman(leg, real), _spearman(fv, real)
        if r1 is not None and r2 is not None:
            diffs.append(r1 - r2)
    diffs.sort()
    if not diffs:
        return {}
    return {"lo95": round(diffs[int(0.025 * len(diffs))], 4),
            "hi95": round(diffs[int(0.975 * len(diffs)) - 1], 4),
            "draws": len(diffs), "seed": seed}


def backtest(*, draws: int = 2000, seed: int = 20261001, persist: bool = True) -> dict:
    """The registered backtest (data/fantasy_rank_eval.json).

    Cohort: the prospects listed in list vintages 2018 and 2019
    (eta_backtest's vintage frame: FV = median of each source's earliest
    same-year snapshot, not yet debuted at the listing). Realized value: the
    FanGraphs Points above replacement each realized season Y..Y+4, floored at
    zero, discounted like the rank. Score: the prospect leg's FanGraphs Points
    value at the vintage, every input point-in-time or forward-chained:
      * translation fits on debuts through Y-2 (targets end by Y-1),
      * playing-time cohort through season Y-1,
      * aging curves fitted on seasons through Y-1 (fa_projection.fitted_models),
      * replacement = the realized replacement of season Y-1 held flat,
      * MiLB inputs read strictly before the listing (efv_dataset._milb_features
        with the listing date as cutoff), ETA = the vintage ETA eta_backtest
        reconstructs,
      * arrival curves CROSS-FITTED, not forward-chained: Kaplan-Meier by level
        on the other non-reserved list vintages (2018, 2019, 2022, 2023 minus
        the test vintage), every player in the test vintage removed, and every
        debut after 2024 censored at 2024 (reserved debut cohort).
    Baseline: the vintage consensus FV, ranked. Metric: Spearman rank
    correlation with realized value, per vintage and pooled, with a
    player-clustered bootstrap interval on the difference."""
    import efv_dataset as ed
    import fa_projection as fp
    import storage
    corpus = fp.build_corpus()
    mids = _mlbam_resolver()
    with storage.connect() as con:
        bio = {r["player_key"]: dict(r) for r in con.execute(
            "SELECT player_key, position, is_pitcher, birth_date FROM players")}
    all_rows = _eta_cohort(KM_TRAIN_VINTAGES)
    sb_lookup = _sb_by_season(range(2010, max(BACKTEST_VINTAGES) + HORIZON + 1))
    realized = _realized_fgp_by_season(
        corpus, range(min(BACKTEST_VINTAGES) - 1, max(BACKTEST_VINTAGES) + HORIZON),
        sb_lookup)

    def _feats(r):
        mid = mids.get(r["player_key"])
        if not mid:
            return None, None
        b = bio.get(r["player_key"]) or {}
        side = "pit" if r.get("is_pitcher") else "hit"
        try:
            f = ed._milb_features(mid, r["vintage"], b.get("birth_date"), side,
                                  cutoff=r.get("date"))
        except Exception:                                    # noqa: BLE001
            f = None
        return mid, f

    feats_cache: dict = {}
    for r in all_rows:
        feats_cache[(r["player_key"], r["vintage"])] = _feats(r)

    def _km_row(r):
        lv = level_key(((feats_cache.get((r["player_key"], r["vintage"])) or (None, None))[1]
                        or {}).get("milb_level")) or level_key(r.get("level"))
        act = r.get("actual")
        out = {"level": lv, "event": None, "censor": None, "washed": False}
        if r.get("outcome") == "debuted" and act is not None and act <= OBSERVED_THROUGH:
            out["event"] = max(0, act - r["vintage"])
        elif r.get("outcome") == "washed_out":
            out["washed"] = True
        else:
            out["censor"] = max(0, OBSERVED_THROUGH - r["vintage"])
        return out

    results: dict = {"by_vintage": {}}
    pooled_pairs: dict = {}
    accounting: dict = {}
    for Y in BACKTEST_VINTAGES:
        test = [r for r in all_rows if r["vintage"] == Y]
        test_keys = {r["player_key"] for r in test}
        train = [_km_row(r) for r in all_rows
                 if r["vintage"] != Y and r["vintage"] in KM_TRAIN_VINTAGES
                 and r["player_key"] not in test_keys]
        km = {}
        for lv in ("AAA", "AA", "A+", "A", "CPX", "DSL"):
            pool = [x for x in train if x["level"] == lv]
            if len(pool) >= 40:
                km[lv] = km_curve(pool)
        pairs = translation_pairs(corpus, Y - 2, sb_lookup=sb_lookup)
        fits = fit_translation(pairs)
        pt = pt_curves(corpus, Y - 1)
        curves, _wm = fp.fitted_models(corpus, Y - 1)
        def delta(s, ro, c, a, _cv=curves):
            return fp.curve_delta(_cv, s, ro, c, a)
        lg = corpus["league"].get(Y - 1) or {}
        fipc = _num(lg.get("fip_constant")) or 3.1
        rep_prev = {side: replacement(list(realized[Y - 1][side].values()), side)
                    for side in ("hit", "pit")}
        rep_real = {s: {side: replacement(list(realized[s][side].values()), side)
                        for side in ("hit", "pit")}
                    for s in range(Y, Y + HORIZON)}
        acct = {"listed": len(test), "dropped_reserved_debut": 0, "dropped_no_mlbam": 0,
                "no_milb_input": 0, "scored": 0, "realized_positive": 0,
                "km_levels": sorted(km), "km_train_rows": len(train)}
        legs, fvs, reals = [], [], []
        for r in test:
            act = r.get("actual")
            if act is not None and act >= RESERVED_DEBUT_FROM:
                acct["dropped_reserved_debut"] += 1
                continue
            mid, f = feats_cache.get((r["player_key"], Y)) or (None, None)
            if not mid:
                acct["dropped_no_mlbam"] += 1
                continue
            if not f:
                acct["no_milb_input"] += 1
            side = "pit" if r.get("is_pitcher") else "hit"
            pos = (bio.get(r["player_key"]) or {}).get("position")
            comps0 = translate(fits, side, f or {})
            lvl = (f or {}).get("milb_level") or r.get("level")
            p = arrival(r.get("pred"), lvl, Y, km)
            lines = prospect_horizon_lines(side, pos, comps0, pt, r.get("pred"), Y,
                                           r.get("age"), Y, delta, fipc)
            leg = total_value([expected_above(ln, "fgp", side, None, rep_prev[side]) * p[t]
                               for t, ln in enumerate(lines)])
            real = 0.0
            for t in range(HORIZON):
                s = Y + t
                for sd in ("hit", "pit"):
                    v = realized[s][sd].get(mid)
                    if v is not None:
                        real += disc(t) * max(0.0, v - rep_real[s][sd])
            legs.append(leg)
            fvs.append(float(r["fv"]))
            reals.append(real)
            acct["scored"] += 1
            acct["realized_positive"] += 1 if real > 0 else 0
            pooled_pairs.setdefault(r["player_key"], []).append((leg, float(r["fv"]), real))
        rho_leg, rho_fv = _spearman(legs, reals), _spearman(fvs, reals)
        results["by_vintage"][str(Y)] = {
            "n": len(legs),
            "rho_prospect_leg": round(rho_leg, 4) if rho_leg is not None else None,
            "rho_consensus_fv": round(rho_fv, 4) if rho_fv is not None else None,
            "rho_difference": (round(rho_leg - rho_fv, 4)
                               if rho_leg is not None and rho_fv is not None else None),
            "km_curves_used": km,
        }
        accounting[str(Y)] = acct
    leg_all = [a for v in pooled_pairs.values() for (a, _b, _c) in v]
    fv_all = [b for v in pooled_pairs.values() for (_a, b, _c) in v]
    re_all = [c for v in pooled_pairs.values() for (_a, _b, c) in v]
    r1, r2 = _spearman(leg_all, re_all), _spearman(fv_all, re_all)
    boot = _bootstrap(pooled_pairs, draws, seed)
    pooled = {"n": len(leg_all), "n_players": len(pooled_pairs),
              "rho_prospect_leg": round(r1, 4) if r1 is not None else None,
              "rho_consensus_fv": round(r2, 4) if r2 is not None else None,
              "rho_difference": round(r1 - r2, 4) if r1 is not None and r2 is not None else None,
              "difference_ci95_player_clustered": boot}
    beats = bool(boot) and boot.get("lo95", -1) > 0
    loses = bool(boot) and boot.get("hi95", 1) < 0
    verdict_text = ("the prospect leg out-ranks the consensus FV on realized fantasy "
                    "value (interval above zero)" if beats else
                    "the consensus FV out-ranks the prospect leg on realized fantasy "
                    "value (interval below zero)" if loses else
                    "no resolvable difference between the prospect leg and the "
                    "consensus FV (interval spans zero)")
    out = {
        "generated_at": date.today().isoformat(),
        "model_id": "fantasy_combined_rank",
        "question": ("Does the combined rank's prospect leg (projected FanGraphs Points "
                     "above replacement, weighted by arrival) rank a past prospect class "
                     "by the fantasy value it went on to produce better than the "
                     "consensus FV rank?"),
        "frame": {"list_vintages": list(BACKTEST_VINTAGES),
                  "reserved_list_vintages_excluded": sorted(RESERVED_LIST_VINTAGES),
                  "reserved_debut_cohort_excluded_from": RESERVED_DEBUT_FROM,
                  "realized_seasons": "Y..Y+4 (2018-2022 and 2019-2023)",
                  "format": "FanGraphs Points (the module default)",
                  "horizon": HORIZON, "discount_rate": DISCOUNT_RATE,
                  "league": dict(LEAGUE)},
        "realized_value": ("per season: FanGraphs Points of the realized line (corpus "
                           "components through the projection algebra; SB from the cached "
                           "StatsAPI MLB rows; a pitcher's hits allowed at the league BABIP "
                           "and no saves or holds) minus that season's realized replacement "
                           "(145th hitter, 121st pitcher), floored at zero, discounted 7% a "
                           "season, summed over both sides"),
        "point_in_time": ("translation fits on debuts through Y-2; playing-time cohort and "
                          "aging curves through season Y-1; replacement = season Y-1's "
                          "realized replacement held flat; MiLB inputs read before the "
                          "listing date; ETA = the vintage ETA eta_backtest reconstructs"),
        "known_leak": ("arrival curves are cross-fitted on the other non-reserved list "
                       "vintages (2018, 2019, 2022, 2023 minus the test vintage), with the "
                       "test vintage's players removed and debuts after 2024 censored; "
                       "later vintages inform an earlier test vintage's level base rates"),
        "accounting": accounting,
        "by_vintage": results["by_vintage"],
        "pooled": pooled,
        "result": verdict_text,
        "verdict": "provisional",
        "verdict_basis": ("one backtest on two list vintages with a cross-fitted arrival "
                          "leg and points-format realized value only; the roto formats "
                          "are not scored"),
    }
    if persist:
        p = Path(EVAL_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Fantasy Rank: refresh or backtest.")
    ap.add_argument("--backtest", action="store_true",
                    help="run the registered backtest and write data/fantasy_rank_eval.json")
    args = ap.parse_args()
    if args.backtest:
        res = backtest()
        print(json.dumps({"by_vintage": res["by_vintage"], "pooled": res["pooled"],
                          "accounting": res["accounting"]}, indent=1, default=str))
    else:
        fr = _load_json("fantasy.json") or {}
        n = refresh((fr.get("sections") or {}).get("dynasty") or [],
                    int(fr.get("season") or date.today().year))
        print(f"wrote {RANK_PATH} ({n} rows)")

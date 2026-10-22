# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
SQLite storage for the prospect tracker (v3).

Schema is append-only for snapshots; stat lines are upserted monthly.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import bisect
import copy
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone


def _utcnow_iso(timespec: str = "seconds") -> str:
    """Timezone-aware UTC 'now' ISO string, naive-style.

    datetime.utcnow() was deprecated in 3.12 / removed in 3.14. The
    aware-then-naive shape preserves the legacy string form ("YYYY-MM-DD
    HH:MM:SS") that downstream parsers + the DB schema expect.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec=timespec)
from pathlib import Path
from typing import Iterable

log = logging.getLogger(__name__)

from scrapers import (
    Snapshot, canonical_player_key, strip_name_markers,
    HITTER_TOOL_KEYS, PITCHER_TOOL_KEYS, ALL_TOOL_KEYS,
)
from consensus import PlayerTimeseries, stock_movement
from stats import PitchArsenal, Sabermetrics, StatLine
from rate_stabilization import K_AB, K_IP


# ---------------------------------------------------------------------------
# wRC+ vs level (Phase D2). Level-anchored PUBLISHED-SHAPE wOBA index, computed
# alongside ops_plus_level so the two can be compared before either is retired.
# ---------------------------------------------------------------------------
# Two things change against ops_plus_level, and they are separable on purpose:
#
#   METRIC   OPS -> wOBA-lite. Fixed FanGraphs 2013 linear-weight SHAPE, rescaled
#            per sport-season so the pool's mean wOBA equals its OBP. wrc_rates.py
#            owns that machinery and has since the W-WRC lane.
#   BASELINE level_norms.avg_ops is an UNWEIGHTED mean of TRACKED-PROSPECT rates
#            over a two-season window; the wrc_rates league pool is a PA-WEIGHTED
#            single-season pool of the WHOLE league. Measured, the AA and A+
#            prospect baselines run 7-8% low against the true league (.703 vs .752,
#            .708 vs .767), so the old chip flattered every hitter at those levels.
#
# The baseline change is the bigger mover of the printed number but carries NO
# ordering information: measured over 1,760 common rows it produced ZERO upward
# moves, Spearman 0.9720 and 0 of 13,218 discordant pairs. It is a per-level
# recentering. The METRIC change is the one that reorders.
#
# SHRINK: same strength as today, re-expressed in PA. K_AB is 170 AB and the
# measured PA/AB median is 1.1776, so K_WRC_PA = 200 PA holds the EB pull constant
# rather than quietly retuning it inside a metric swap.
K_WRC_PA = 200.0
_WRC_INDEX = None


def _wrc_index():
    """(index, leagues) from wrc_rates, loaded once. Empty on any failure: the
    chip is display-only, so a missing components cache must degrade to "no chip"
    and never to a wrong one."""
    global _WRC_INDEX
    if _WRC_INDEX is None:
        try:
            import wrc_rates
            _WRC_INDEX = wrc_rates.build_index()
        except Exception:
            log.exception("wrc_rates index unavailable; wrc_plus_level will be absent")
            _WRC_INDEX = ({}, {})
    return _WRC_INDEX


def _wrc_plus_level(mlbam, season, level):
    """Level-anchored wRC+ for one player-season-level, or None.

    None rather than a fallback on purpose. Silently substituting the OPS chip
    would make two different metrics share one field name, which is exactly the
    confusion this lane exists to remove.
    """
    if mlbam is None or season is None or not level:
        return None
    idx, leagues = _wrc_index()
    if not idx:
        return None
    rec = idx.get((int(mlbam), int(season), level))
    lg = leagues.get((int(season), level))
    if not rec:
        # LEVEL-LABEL FALLBACK. The board and the StatsAPI league name disagree on
        # the complex leagues: 124 served rows are labelled CPX here while the feed
        # puts the same player-seasons in the DSL. Measured 2026-07-31, that single
        # disagreement was the ENTIRE coverage gap (122 of 122 misses were CPX 2026).
        #
        # Fall back to the same (player, season) at whatever level the FEED has, but
        # only when that is unambiguous. The league pool then matches the league the
        # player actually appeared in, which is the more defensible anchor of the
        # two, and it is strictly better than printing no chip. An ambiguous case
        # (two levels in one season) is left absent rather than guessed.
        alt = [k for k in idx if k[0] == int(mlbam) and k[1] == int(season)]
        if len(alt) != 1:
            return None
        rec = idx.get(alt[0])
        lg = leagues.get((int(season), alt[0][2]))
    if not rec or not lg:
        return None
    w, lw, pa = rec.get("woba"), lg.get("woba"), rec.get("pa") or 0.0
    if w is None or not lw or lw <= 0:
        return None
    adj = (pa * w + K_WRC_PA * lw) / (pa + K_WRC_PA)
    return round(adj / lw * 100)

DB_PATH = Path(__file__).parent / "prospects.db"
_LEVEL_SORT_ORDER = {"MLB": 0, "AAA": 1, "AA": 2, "A+": 3, "A": 4, "CPX": 5, "DSL": 6}

# Prospects whose most recent ranking update is older than this many months are
# classified as "inactive" rather than "active". They fell off prospect lists
# without ever being marked graduated — think Wander Franco (suspended) or
# players who quietly aged out of prospect status.
INACTIVE_MONTHS = 18

# After this many days since a source's most recent tool publication,
# we flag that source as "stale" in tools.source_recency. The UI uses
# the flag to visually de-emphasize the source in the history dropdown
# without removing it from the Tool composite (Tool always uses each
# source's latest publication regardless of age).
TOOL_FRESHNESS_DAYS = 365


def _index_plus(value: float | None, mean: float | None, stdev: float | None) -> int | None:
    """Generic 'X+' normalization shared by RPS+, DvM+, Stuff+, Cmd+.

    Returns `100 + 10 * (value - mean) / stdev`, rounded to int and
    clamped to [0, 250] so a perverse one-prospect cohort never produces
    a nonsense ±400 reading. Returns None when any input is missing or
    when stdev is zero (no variance → every prospect plots at 100, which
    is informationally useless but not wrong).
    """
    if value is None or mean is None or stdev is None or stdev <= 0:
        return None
    plus = round(100 + 10 * (value - mean) / stdev)
    return max(0, min(250, plus))


def _round_half(grade: float | None) -> float | None:
    """Snap a 20-80 grade to the nearest 0.5 — matches FG's published tool grid."""
    if grade is None:
        return None
    return round(grade * 2) / 2


_TOOLS_POWER_MEAN_P = 3.0  # >1 biases composite toward outliers


def _compute_peripheral_stf_plus(sl: dict | None,
                                 norms_perf: dict | None) -> int | None:
    """Z-score composite of K%, BB%, and HR/9 vs the level mean.

    Workload-stable peripheral STF+. Per-batter K%/BB% replace per-9 rates
    so a starter and a reliever can be compared on the same footing.

      stf = 100 + 10 · (0.55·z_K − 0.30·z_BB − 0.15·z_HR9)

    where z scores are (value − μ) / σ and σ is approximated as 15% of
    the level mean (the level_norms blocks don't ship a real stdev; the
    15%-of-mean rule of thumb matches the spread observed across
    pitchers at every level on this site). Walks and HRs are subtracted
    so a low rate (good) raises the composite.

    Returns None when:
      - The pitcher's sample is below the gate (<20 IP and <30 BF).
      - K%, BB%, and HR/9 are all missing.
      - The level baselines aren't available.
    """
    if not sl or not norms_perf or not sl.get("is_pitcher"):
        return None
    try:
        ip = float(sl.get("ip") or 0)
    except (TypeError, ValueError):
        ip = 0
    try:
        bf = float(sl.get("batters_faced") or sl.get("tbf") or 0)
    except (TypeError, ValueError):
        bf = 0
    if ip < 20 and bf < 30:
        return None
    def _z(val_key, mu_key, std_key, invert=False):
        # Phase A3 — prefer the level's empirical sigma when level_norms
        # has enough samples to compute it; fall back to the 0.15×mu
        # rule of thumb otherwise. The empirical sigma is meaningfully
        # tighter for K%/BB% (the real per-level distribution is
        # narrower than 15% of the mean) and looser for HR/9 (real
        # spread is wider) — so the z-scores get more honest at both ends.
        try:
            v = sl.get(val_key)
            mu = norms_perf.get(mu_key)
            if v is None or mu is None or mu == 0:
                return None
            v = float(v)
            empirical_sigma = norms_perf.get(std_key)
            if empirical_sigma is not None and float(empirical_sigma) > 0:
                sigma = float(empirical_sigma)
            else:
                sigma = 0.15 * float(mu)
            if sigma <= 0:
                return None
            z = (v - mu) / sigma
            return -z if invert else z
        except (TypeError, ValueError):
            return None
    z_k  = _z("k_pct",     "avg_pitcher_k_pct",  "std_pitcher_k_pct")
    z_bb = _z("bb_pct",    "avg_pitcher_bb_pct", "std_pitcher_bb_pct", invert=True)
    z_hr = _z("hr_per_9",  "avg_hr_per_9",       "std_hr_per_9",       invert=True)
    parts = [(0.55, z_k), (0.30, z_bb), (0.15, z_hr)]
    parts = [(w, z) for w, z in parts if z is not None]
    if not parts:
        return None
    weight_sum = sum(w for w, _ in parts)
    composite = sum(w * z for w, z in parts) / weight_sum
    stf = round(100 + 10 * composite)
    return max(0, min(250, stf))


def _power_mean(vals: list[float], p: float = _TOOLS_POWER_MEAN_P) -> float | None:
    """Lₚ power mean — biases the composite toward outliers when p > 1.

    p=1 reduces to arithmetic mean; p→∞ approaches max. p=3 is a
    moderate "rewards a standout tool" bias: a 70+50+50+50 hitter
    goes from 55 (arith mean) to ~57.6 (power-3). A uniform 50/50/50/50
    profile stays at 50. Operates in the FV-grade space (20-80) and
    returns a value in the same band.
    """
    if not vals:
        return None
    n = len(vals)
    return (sum(v ** p for v in vals) / n) ** (1.0 / p)


def _fg_pm_to_fv(pm: int | float | None) -> float | None:
    # FG publishes Frame / Athl / Delivery on a -2..+2 plus/minus scale.
    # Map to 20-80 FV space: -2→30, -1→40, 0→50, +1→60, +2→70.
    if pm is None:
        return None
    try:
        v = int(pm)
    except (TypeError, ValueError):
        return None
    if v < -2 or v > 2:
        return None
    return 50.0 + 10.0 * v


# Order matters: catcher first, then infield slots, then OF, then DH/UT.
# Mirrors the JS positionBucket() priority used in the UI.
_POS_BUCKET_C  = frozenset({"C"})
_POS_BUCKET_IF = frozenset({"SS", "2B", "3B", "1B"})
_POS_BUCKET_OF = frozenset({"LF", "CF", "RF", "OF"})


_IS_PITCHER_TOKENS = frozenset({
    "P", "SP", "RP", "LHP", "RHP", "LHRP", "RHRP", "SIRP", "MIRP",
    "LHSP", "RHSP", "PITCHER",
})
_IS_HITTER_TOKENS = frozenset({
    "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF", "IF", "DH",
    "INF", "UTIL", "UT", "CIF", "MIF", "CATCHER",
})


def _is_pitcher_flag(position_str: str | None) -> int | None:
    """1 / 0 for a determinate position label, None when it says nothing.

    players.is_pitcher used to be written by a code path that no longer
    exists: both INSERT INTO players statements below omitted the column
    (DEFAULT 0), so every row minted since then carried 0 regardless of
    position and every position change left the old flag frozen. Measured
    2026-07-25 before the repair: 1,748 of 10,347 rows carried a pitcher
    position with is_pitcher = 0. This keeps the column in step with the
    label from here on; TWP (two-way) and slash labels stay indeterminate
    and preserve whatever the row already had.
    """
    if not position_str:
        return None
    tok = str(position_str).strip().upper()
    if tok in _IS_PITCHER_TOKENS:
        return 1
    if tok in _IS_HITTER_TOKENS:
        return 0
    return None


def _position_bucket(position_str: str | None) -> str | None:
    if not position_str:
        return None
    tokens = [t.strip().upper() for t in str(position_str).split("/") if t.strip()]
    if any(t in _POS_BUCKET_C  for t in tokens): return "C"
    if any(t in _POS_BUCKET_IF for t in tokens): return "IF"
    if any(t in _POS_BUCKET_OF for t in tokens): return "OF"
    if "DH" in tokens: return "DH"
    return "UT"


def _extract_player_extras(latest_point) -> dict:
    # Consolidate per-source `tools._extras` into a single player-level dict.
    # FG is the canonical publisher of frame/athl/delivery so we prefer its
    # values when multiple sources publish (they basically never do for
    # these keys, but the FG-first preference future-proofs the merge).
    out: dict = {}
    if not latest_point or not getattr(latest_point, "per_source", None):
        return out
    per_src = latest_point.per_source or {}
    source_order = list(per_src.keys())
    if "fangraphs" in source_order:
        source_order.remove("fangraphs")
        source_order.insert(0, "fangraphs")
    for src in source_order:
        info = per_src.get(src) or {}
        tools = info.get("tools") or {}
        extras = tools.get("_extras") if isinstance(tools, dict) else None
        if not isinstance(extras, dict):
            continue
        for k, v in extras.items():
            if k not in out and v is not None and v != "":
                out[k] = v
    return out


def _compute_tool_composites(grades: dict[str, float] | None,
                              is_pitcher: bool,
                              player_extras: dict | None = None,
                              position_bucket: str | None = None) -> dict | None:
    """Build the raw 20-80 tools sub-object from per-tool consensus grades.

    Returns a dict with `grades` (the input, copied + rounded to 0.5),
    the composites (off/def for hitters, stuff/cmd for pitchers, and
    overall in both cases), or None when no tools are graded.
    Composites are computed only over the grades that are present —
    a hitter with hit + power but no field/throw still gets a
    `composite_off` but no `composite_def`. The off/def composites use
    a power mean (p=3) so a single standout tool lifts the composite
    more than balanced average tools — better captures "toolsy".
    """
    if not grades:
        return None
    cleaned: dict[str, float] = {}
    for k, v in grades.items():
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f < 20 or f > 80:
            continue
        cleaned[k] = _round_half(f)
    if not cleaned:
        return None

    def _avg(keys):
        # Outlier-biased power mean (Lₚ, p=3). Falls back to None when
        # none of the keys are present in `cleaned`.
        vals = [cleaned[k] for k in keys if k in cleaned]
        if not vals:
            return None
        result = _power_mean(vals)
        return round(result, 2) if result is not None else None

    extras = player_extras or {}
    frame_fv    = _fg_pm_to_fv(extras.get("frame"))
    athl_fv     = _fg_pm_to_fv(extras.get("athl"))
    delivery_fv = _fg_pm_to_fv(extras.get("delivery"))

    out: dict = {"grades": cleaned}
    if is_pitcher:
        # v14 — Frame/Athl/Delivery FG plus-minus grades enter the stuff
        # power-mean (p=3) as equal-weight inputs alongside fb/sl/cb/ch.
        # A +2 delivery prospect now out-stuffs an identical pitch
        # arsenal with a 0/5 (neutral) delivery, capturing the
        # mechanics-quality axis of pitcher development.
        stuff_inputs = [cleaned[k] for k in ("fb", "sl", "cb", "ch") if k in cleaned]
        for fv in (frame_fv, athl_fv, delivery_fv):
            if fv is not None:
                stuff_inputs.append(fv)
        stuff = _power_mean(stuff_inputs) if stuff_inputs else None
        if stuff is not None:
            stuff = round(stuff, 2)
        cmd = cleaned.get("cmd")
        out["composite_stuff"] = stuff
        out["composite_cmd"] = cmd
        # Overall = 0.65 stuff + 0.35 cmd; fall back to whichever side
        # is present so a "stuff-only" prospect still gets an overall.
        if stuff is not None and cmd is not None:
            out["composite_overall"] = round(0.65 * stuff + 0.35 * cmd, 2)
        else:
            out["composite_overall"] = stuff if stuff is not None else cmd
        out["composite_off"] = None
    else:
        # O-Tool weighted blend: HIT 40 / PWR 40 / BCTRL 10 / PSEL 6 /
        # SPD 4. Heavy "bats matter most" tilt — speed is a tiebreaker
        # contributor, plate discipline rounds out the offense profile.
        # PWR uses the consolidated `pwr` key if present, else falls
        # back to the mean of game_pwr + raw_pwr. Output is the raw
        # weighted mean on the 20-80 scouting scale (50 = average).
        def _pwr_value():
            if "pwr" in cleaned:
                return cleaned["pwr"]
            g = cleaned.get("game_pwr")
            r = cleaned.get("raw_pwr")
            if g is not None and r is not None:
                return (g + r) / 2.0
            if g is not None:
                return g
            return r  # may be None
        OFF_WEIGHTS = {
            "hit":       0.40,
            "pwr":       0.40,
            "bat_ctrl":  0.10,
            "pitch_sel": 0.06,
            "speed":     0.04,
        }
        off_inputs = {
            "hit":       cleaned.get("hit"),
            "pwr":       _pwr_value(),
            "bat_ctrl":  cleaned.get("bat_ctrl"),
            "pitch_sel": cleaned.get("pitch_sel"),
            "speed":     cleaned.get("speed"),
        }
        present = {k: v for k, v in off_inputs.items() if v is not None}
        if present:
            total_w = sum(OFF_WEIGHTS[k] for k in present)
            off = sum(OFF_WEIGHTS[k] * v for k, v in present.items()) / total_w
            out["composite_off"] = round(off, 2)
        else:
            out["composite_off"] = None
        # Tool (overall) is the EQUALLY-WEIGHTED power-mean (p=4) of
        # every tool the prospect carries, including DEF/Field + Frame/
        # Athl FG physical grades (mapped from -2..+2 to 30..70). The
        # p=4 power-mean rewards extreme tools more sharply than the
        # p=3 used elsewhere — a 70 PWR + 45 HIT prospect (arithmetic
        # mean 57.5) scores ~58 here. Captures "elite-tool ceiling"
        # profiles cleanly. A neutral 0/5 physical sits at FV 50 and
        # pulls the mean toward 50, which is the right behavior.
        # Output is on the raw 20-80 scouting scale (50 = average).
        TOOL_KEYS = ("hit", "speed", "field", "throw",
                     "pitch_sel", "bat_ctrl")
        tool_vals = [cleaned[k] for k in TOOL_KEYS if k in cleaned]
        pwr_for_overall = _pwr_value()  # same consolidated PWR as O-Tool
        if pwr_for_overall is not None:
            tool_vals.append(pwr_for_overall)
        for fv in (frame_fv, athl_fv):
            if fv is not None:
                tool_vals.append(fv)
        if tool_vals:
            out["composite_overall"] = round(
                _power_mean(tool_vals, p=4), 2
            )
        else:
            out["composite_overall"] = None
        out["composite_stuff"] = None
        out["composite_cmd"] = None

        # D-Tool (composite_def): weighted power-mean (p=3) of
        # defensive tools. Catchers drop speed (irrelevant) and bump
        # field — receiving/framing/blocking lives inside the field
        # grade already. Non-catchers use field 60 / arm 30 / run 10.
        # Output is on the raw 20-80 scouting scale (50 = average).
        if position_bucket == "C":
            DEF_WEIGHTS = {"field": 0.70, "throw": 0.30}
        else:
            DEF_WEIGHTS = {"field": 0.60, "throw": 0.30, "speed": 0.10}
        def_inputs = {k: cleaned.get(k) for k in DEF_WEIGHTS}
        def_present = {k: v for k, v in def_inputs.items() if v is not None}
        if def_present:
            total_w = sum(DEF_WEIGHTS[k] for k in def_present)
            # Weighted power-mean (p=3) — outlier-biased so an
            # elite-glove 70 DEF jumps off the page.
            weighted_cube = sum(DEF_WEIGHTS[k] * (v ** 3)
                                for k, v in def_present.items())
            out["composite_def"] = round(
                (weighted_cube / total_w) ** (1.0 / 3.0), 2
            )
        else:
            out["composite_def"] = None
    return out


def _attach_tool_plus_indices(payloads: list[dict]) -> None:
    """Second-pass population normalization for tool composites.

    Two jobs:
      1. Expose Tool / O-Tool / D-Tool at the top level of each payload
         (sourced directly from the raw 20-80 power-mean composites; the
         frontend reads `pl["tool"]` for row pills and sorting).
      2. Compute Stuff+ / Cmd+ cohort-relative indices on the tools dict
         (these stay z-scored at 100±10σ — only the Tool family migrated
         off the +/- scale).
      3. Emit composite-driven green/red tool flags using the new 20-80
         thresholds (≥60 = elite, ≤40 = below).
    """
    # Tool / O-Tool / D-Tool now ship as raw 20-80 power-means — no
    # cohort z-scoring. Stuff+ / Cmd+ keep the +/- treatment because
    # they're a separate pitcher-only family that the user did not
    # migrate in this pass.
    plus_keys = ("composite_stuff", "composite_cmd")
    samples: dict[str, list[float]] = {k: [] for k in plus_keys}
    for pl in payloads:
        t = pl.get("tools")
        if not t:
            continue
        for k in plus_keys:
            v = t.get(k)
            if v is not None:
                samples[k].append(float(v))
    cohort_stats: dict[str, tuple[float, float]] = {}
    for k, vals in samples.items():
        if len(vals) < 2:
            cohort_stats[k] = (None, None)
            continue
        m = sum(vals) / len(vals)
        var = sum((x - m) ** 2 for x in vals) / len(vals)
        cohort_stats[k] = (m, var ** 0.5 if var > 0 else None)
    # ETOOLS_ALL_CALCS: the indices above are on the served (eTool) composites.
    # The consensus ones are kept under composite_cons, z-scored against the
    # consensus cohort, so a reader that stays on consensus (the trade-value
    # policy, until its re-read R-TV) reads exactly the number it read before.
    # Absent when the flag is off (no payload carries composite_cons).
    cons_stats: dict[str, tuple[float, float]] = {}
    if any(isinstance((pl.get("tools") or {}).get("composite_cons"), dict) for pl in payloads):
        cons_samples: dict[str, list[float]] = {k: [] for k in plus_keys}
        for pl in payloads:
            t = pl.get("tools")
            if not t:
                continue
            src = t.get("composite_cons") if isinstance(t.get("composite_cons"), dict) else t
            for k in plus_keys:
                v = src.get(k)
                if v is not None:
                    cons_samples[k].append(float(v))
        for k, vals in cons_samples.items():
            if len(vals) < 2:
                cons_stats[k] = (None, None)
                continue
            m = sum(vals) / len(vals)
            var = sum((x - m) ** 2 for x in vals) / len(vals)
            cons_stats[k] = (m, var ** 0.5 if var > 0 else None)
    for pl in payloads:
        t = pl.get("tools")
        if not t:
            continue
        for k in plus_keys:
            mean, stdev = cohort_stats[k]
            t[f"{k}_plus"] = _index_plus(t.get(k), mean, stdev)
        for _holder in (t, t.get("hitter_payload"), t.get("pitcher_payload")):
            _cc = (_holder or {}).get("composite_cons")
            if cons_stats and isinstance(_cc, dict):
                for k in plus_keys:
                    mean, stdev = cons_stats[k]
                    _cc[f"{k}_plus"] = _index_plus(_cc.get(k), mean, stdev)
        # Top-level convenience field for row pills + sort. Sourced
        # from the raw 20-80 composite_overall power-mean, rounded to
        # an integer (the row pill renders with no decimal).
        overall_raw = t.get("composite_overall")
        pl["tool"] = round(overall_raw) if overall_raw is not None else None
        # Two-way players: stamp Stuff+ / Cmd+ on hitter_payload /
        # pitcher_payload sub-dicts using the shared cohort norms.
        for sub_key in ("hitter_payload", "pitcher_payload"):
            sub = t.get(sub_key)
            if not sub:
                continue
            for k in plus_keys:
                mean, stdev = cohort_stats[k]
                sub[f"{k}_plus"] = _index_plus(sub.get(k), mean, stdev)
        # Composite-driven green/red flags use the new 20-80 thresholds:
        # ≥60 (Plus tier) earns a green flag; ≤40 (Below-Average) earns
        # a red flag. Stuff+ stays on its +/- scale (≥115 / ≤85).
        overall_raw = t.get("composite_overall")
        off_raw = t.get("composite_off")
        def_raw = t.get("composite_def")
        stuff_plus = t.get("composite_stuff_plus")
        tool_flags = pl.setdefault("tool_flags", [])
        for raw_val, label, slug in (
            (overall_raw, "Tool",   "Tool"),
            (off_raw,     "O-Tool", "O-Tool"),
            (def_raw,     "D-Tool", "D-Tool"),
        ):
            if raw_val is None:
                continue
            if raw_val >= 60:
                tool_flags.append({
                    "stat": label,
                    "direction": "green",
                    "value": raw_val,
                    "value_display": f"{label} {raw_val:.1f}",
                    "level": None,
                    "level_avg": 50,
                    "delta": round(raw_val - 50, 1),
                    "delta_display": f"{raw_val - 50:+.1f}",
                    "category": "composite",
                    "polarity": "above_good",
                    "note": f"{label} {raw_val:.1f} - Plus tier (60+) composite toolset.",
                })
        if stuff_plus is not None and stuff_plus >= 115:
            tool_flags.append({
                "stat": "Stuff",
                "direction": "green",
                "value": stuff_plus,
                "value_display": f"Stuff {stuff_plus:+d}",
                "level": None,
                "level_avg": 100,
                "delta": stuff_plus - 100,
                "delta_display": f"{stuff_plus - 100:+d}",
                "category": "composite",
                "polarity": "above_good",
                "note": f"Stuff index {stuff_plus} - above-cohort arsenal.",
            })
        if overall_raw is not None and overall_raw <= 40:
            tool_flags.append({
                "stat": "Tool",
                "direction": "red",
                "value": overall_raw,
                "value_display": f"Tool {overall_raw:.1f}",
                "level": None,
                "level_avg": 50,
                "delta": round(overall_raw - 50, 1),
                "delta_display": f"{overall_raw - 50:+.1f}",
                "category": "composite",
                "polarity": "below_good",
                "note": f"Tool {overall_raw:.1f} - Below-Average tier composite toolset.",
            })


# v14 — Breakout indicator constants.
_BREAKOUT_WINDOW_DAYS = 180          # 6 months
_BREAKOUT_WINDOW_MIN_UPDATES = 4     # at least 4 consensus points
_BREAKOUT_FV_UPGRADE_THRESHOLD = 5.0
_BREAKOUT_TOOL_VELOCITY_THRESHOLD = 3.0  # avg tool grade improvement
# RETIRED 2026-07-29 (kept as a tombstone, deliberately not deleted so a
# future reader does not re-add the gate): _BREAKOUT_HITTER_RPS_PLUS_GATE = 110
# fed a `statline.rps_plus` leg of the breakout perf gate. That leg was a
# dead read (nothing writes rps_plus into a timeseries statline; 0 of 4,505
# players carry the field) and was removed. Re-adding an RPS+ gate here
# requires a producer for statline.rps_plus FIRST.
# v15: hitter wRC+ proxy for graduated-statline hitters (>=130 wRC+).
_BREAKOUT_HITTER_WRC_PLUS_GATE = 130
_BREAKOUT_PITCHER_STF_PLUS_GATE = 105
_BREAKOUT_PITCHER_FIP_MINUS_GATE = 90
# v29: Statcast+ as a perf gate. It picks up prospects whose
# contact-quality + zone discipline (or pitch-quality + induced whiffs) is
# elite even when the scout-published indices (Stuff+, wRC+, RPS+) haven't
# been computed yet. Same gate for hitters and pitchers since Statcast+ is
# already side-aware.
# RE-MAPPED 2026-08-07 from 115: SC+ was re-standardized to a true 10 points
# per sigma, so these numbers move to hold the POPULATION they gate on rather
# than their appearance. 122 selects 40 players where 115 selected 43; leaving
# it at 115 would have taken it to 589. docs/SC_PLUS_RECALIBRATION_GATE.md.
_BREAKOUT_STATCAST_PLUS_GATE = 122
# v29: Stat-only Statcast+ bar. Higher than the perf-gate since the stat-only
# path bypasses the tool/FV velocity requirement: only elite-tier Statcast
# composites should trigger breakout without ANY scout-side movement signal.
# RE-MAPPED 2026-08-07 from 130 (same reason); 143 selects the same 1 player.
_BREAKOUT_STAT_STATCAST_PLUS_GATE = 143
# v15 — Age caps. Breakouts are forward-looking signals; aging relievers
# putting up a hot 90-day stretch aren't really "breaking out" in the
# prospect-development sense. Caps below align with typical prospect-window
# age boundaries: SP / position-player prospects through age 24; relievers
# (RP / MIRP / SIRP / CL) through age 25 since they typically peak younger.
_BREAKOUT_MAX_AGE_STARTER = 24.0
_BREAKOUT_MAX_AGE_RELIEVER = 25.0
_BREAKOUT_RELIEVER_POSITIONS = {"RP", "MIRP", "SIRP", "CL", "CP"}

# v17 — Stat-only gate: a young hitter posting elite wRC+ or a young
# pitcher posting elite peripheral stuff qualifies as Breakout even
# without tool/FV velocity (scouts often lag the underlying performance
# by 1-2 cycles, so this lets statistically-emerging prospects break
# out before the consensus catches up). Age caps are tighter for the
# stat-only path: hitter ≤22, pitcher ≤23.
_BREAKOUT_STAT_WRC_PLUS_GATE = 130
_BREAKOUT_STAT_STF_PLUS_GATE = 115
_BREAKOUT_STAT_HITTER_MAX_AGE = 22.0
_BREAKOUT_STAT_PITCHER_MAX_AGE = 23.0
# v17 — Active-prospect cohort (most don't carry wRC+/RPS+; we use
# ops_plus_level instead). This is a level-anchored OPS+ where 100 = level
# mean. The threshold is higher than the wRC+/RPS+ gate because level-
# anchored stats compress harder (rare to clear +50% of level mean).
_BREAKOUT_STAT_OPS_PLUS_LEVEL_GATE = 150


def _detect_upside_added_events(points: list[dict]) -> list[dict]:
    """v27 — Walk points chronologically; return events where a source
    INTRODUCED a "+" upside marker that it didn't have on its prior
    snapshot. Pairs with the hot-pink chart dots: each event is the
    "first +" transition for that source in this player's history.

    Returns: list of {date, source, fv_label} dicts, ordered by date.
    Dedup is per-source per-run (a source dropping "+" then re-adding
    later produces a second event).
    """
    if not points:
        return []
    out: list[dict] = []
    seen_plus: dict[str, bool] = {}
    for pt in points:
        ps = pt.get("per_source") or {}
        if not isinstance(ps, dict):
            continue
        for src, info in ps.items():
            if not isinstance(info, dict):
                continue
            cur = bool(info.get("fv_plus"))
            prev = seen_plus.get(src)
            if cur and prev is not True:
                out.append({
                    "date":      pt.get("snapshot_date"),
                    "source":    src,
                    "fv_label":  pt.get("consensus_fv_label"),
                })
            seen_plus[src] = cur
    return out


def _compute_breakout_flag(payload: dict) -> dict | None:
    """v14 — Active-prospect Breakout indicator.

    A prospect flags as Breakout when:
      - Window: at least 4 consensus points spanning ≥6 months (whichever
        is longer in time).
      - Tool signal: EITHER consensus FV climbed ≥ +5 over the window
        OR mean tool-grade composite climbed ≥ +3.
      - Perf gate: hitters need RPS+ ≥ 120; pitchers need
        stf_plus_periph ≥ 105 OR fip_minus ≤ 90 (lower better). Two-way
        prospects pass if either gate passes.

    Returns a dict {flag, reason, perf_gate} suitable for stamping on
    the payload, or None if the prospect doesn't qualify.
    Graduated / inactive players are skipped (Breakout is an
    active-prospect signal only).
    """
    if payload.get("status") != "active":
        return None
    # A prospect on the 60-day IL is shelved for an extended stretch (often the
    # season) — a stale FV / tool / upside signal must not surface a live
    # "Breakout" badge over a long-term injury. (Jarlin Susana: 60-day IL since
    # March, consensus FV actually -2, was flagging via the upside path.)
    _il = payload.get("il_status") or {}
    if _il.get("is_on_il") and "60" in str(_il.get("type") or ""):
        return None
    # v30.7 — Breakout / Faller mutual-exclusion gate. A prospect whose
    # CURRENT stock movement is a faller (or strong faller) is, by
    # definition, not breaking out — even if a stale FV/tool jump in
    # the breakout window would otherwise qualify them. The Mejia case
    # (FV up 5 over the year + ERA 7.71 / K% -7.9 right now) was
    # flagging as both breakout AND faller. Stock is already attached
    # to the payload by compute_movement before _attach_breakout_flags
    # runs, so we can read it directly here.
    stock = payload.get("stock") or {}
    if stock.get("bucket") == "faller":
        return None
    if stock.get("direction") in ("down", "down_strong"):
        return None
    # v15 — Age cap: position players + SPs through 24; relievers (RP /
    # MIRP / SIRP / CL) through 25.
    try:
        age = float(payload.get("age")) if payload.get("age") is not None else None
    except (TypeError, ValueError):
        age = None
    if age is not None:
        pos_head = (payload.get("position") or "").split("/")[0].upper().strip()
        is_reliever = pos_head in _BREAKOUT_RELIEVER_POSITIONS
        cap = _BREAKOUT_MAX_AGE_RELIEVER if is_reliever else _BREAKOUT_MAX_AGE_STARTER
        if age > cap:
            return None

    # v17 — Stat-only gate (NEW). A young hitter posting elite wRC+ or a
    # young pitcher posting elite peripheral stuff qualifies as Breakout
    # without ANY tool/FV velocity. Scouts often lag the underlying
    # statistical breakout by 1-2 cycles, so this path lets statistically-
    # emerging prospects flag before the consensus catches up. Stat-only
    # gate has tighter age caps (hitter ≤22, pitcher ≤23) than the
    # velocity path's caps so it stays exclusive.
    statline = payload.get("statline") or {}
    saberm = payload.get("sabermetrics") or {}
    is_pitcher_ctx = bool(statline.get("is_pitcher")
                          or saberm.get("is_pitcher"))
    if age is not None:
        if not is_pitcher_ctx and age <= _BREAKOUT_STAT_HITTER_MAX_AGE:
            # v17: wRC+ (MLB-experienced cohort) is the first hitter
            # stat-only signal. wRC+ lives on graduates / MLB-experienced
            # players only.
            wrc = saberm.get("wrc_plus")
            try:
                if wrc is not None and float(wrc) >= _BREAKOUT_STAT_WRC_PLUS_GATE:
                    return {
                        "flag": True,
                        "reason": "stats",
                        "perf_gate": "wrc_plus",
                        "fv_upgrade": None,
                        "tool_velocity": None,
                        "window_anchor_date": None,
                    }
            except (TypeError, ValueError):
                pass
            # DEAD-READ REMOVED 2026-07-29: a `statline.rps_plus` leg used to sit
            # here at the wRC+ threshold. `statline` NEVER carries `rps_plus`:
            # the only producers are draft_export.py and overseas_export.py, and
            # both stamp it at the TOP LEVEL of their own payloads (draft board /
            # overseas board), not into the timeseries statline this function
            # reads. Verified against the served artifact: `statline.rps_plus` is
            # present on 0 of 4,505 players in data/timeseries.json. The branch
            # was unreachable, so removing it is behaviour-identical. It is NOT
            # repointed at ops_plus_level because the ops_plus_level leg already
            # sits directly below at its OWN calibrated threshold
            # (_BREAKOUT_STAT_OPS_PLUS_LEVEL_GATE); repointing would have added a
            # second, looser gate on the same field and changed which players
            # earn a Breakout badge.
            # v17: Active-prospect MiLB hitters mostly don't carry wRC+;
            # their level-anchored equivalent is `statline.ops_plus_level`
            # (100 = level mean). Threshold is _BREAKOUT_STAT_OPS_PLUS_LEVEL_GATE
            # (150), set higher than the wRC+ gate because level-anchored stats
            # compress harder; see the constant's own comment.
            # PHASE D2: reads the wRC+ chip, falling back to the retired OPS one.
            # This gate is DEAD either way and has been for a while: measured
            # 2026-07-31, 0 of 1,972 served rows reach 150 under ANY of the
            # candidates (OPS+ max 127, wRC+ max 119). Repointed for consistency
            # rather than for effect, so the flag cannot start describing one metric
            # while the card shows another.
            ops_plus = statline.get("wrc_plus_level")
            if ops_plus is None:
                ops_plus = statline.get("ops_plus_level")
            try:
                if ops_plus is not None and float(ops_plus) >= _BREAKOUT_STAT_OPS_PLUS_LEVEL_GATE:
                    return {
                        "flag": True,
                        "reason": "stats",
                        "perf_gate": "wrc_plus_level",
                        "fv_upgrade": None,
                        "tool_velocity": None,
                        "window_anchor_date": None,
                    }
            except (TypeError, ValueError):
                pass
        if is_pitcher_ctx and age <= _BREAKOUT_STAT_PITCHER_MAX_AGE:
            stf = statline.get("stf_plus_periph")
            try:
                if stf is not None and float(stf) >= _BREAKOUT_STAT_STF_PLUS_GATE:
                    return {
                        "flag": True,
                        "reason": "stats",
                        "perf_gate": "stf_plus_periph",
                        "fv_upgrade": None,
                        "tool_velocity": None,
                        "window_anchor_date": None,
                    }
            except (TypeError, ValueError):
                pass
        # v29 — Statcast+ stat-only path (both sides, same age caps).
        # Elite Statcast composite triggers breakout without ANY scout-
        # side movement signal — useful for the under-tracked-by-scouts
        # prospects (low-A, indy-league lifers, NPB transitions) whose
        # game feeds DO carry Statcast but whose RPS+/wRC+/Stuff+ aren't
        # yet on file.
        sc_plus = payload.get("statcast_plus")
        sc_age_cap = (_BREAKOUT_STAT_PITCHER_MAX_AGE if is_pitcher_ctx
                      else _BREAKOUT_STAT_HITTER_MAX_AGE)
        try:
            if (sc_plus is not None
                    and float(sc_plus) >= _BREAKOUT_STAT_STATCAST_PLUS_GATE
                    and age <= sc_age_cap):
                return {
                    "flag": True,
                    "reason": "stats",
                    "perf_gate": "statcast_plus",
                    "fv_upgrade": None,
                    "tool_velocity": None,
                    "window_anchor_date": None,
                }
        except (TypeError, ValueError):
            pass

    points = payload.get("points") or []
    if len(points) < _BREAKOUT_WINDOW_MIN_UPDATES:
        return None
    # Window start = the older of (today - 180d, the 4th-most-recent point's
    # date). Both shrinking points yield "the older anchor wins."
    try:
        latest_date = date.fromisoformat(points[-1]["snapshot_date"])
    except (ValueError, TypeError, KeyError):
        return None
    earliest_allowed = latest_date - timedelta(days=_BREAKOUT_WINDOW_DAYS)
    fourth_recent_idx = len(points) - _BREAKOUT_WINDOW_MIN_UPDATES
    try:
        fourth_recent_date = date.fromisoformat(
            points[fourth_recent_idx]["snapshot_date"])
    except (ValueError, TypeError, KeyError):
        return None
    window_anchor_date = min(earliest_allowed, fourth_recent_date)

    # Find the consensus point closest to (but not after) the window anchor.
    # The earliest qualifying point is points[fourth_recent_idx] at worst.
    anchor_pt = None
    for pt in points:
        try:
            d = date.fromisoformat(pt["snapshot_date"])
        except (ValueError, TypeError, KeyError):
            continue
        if d <= window_anchor_date:
            anchor_pt = pt
        else:
            break
    if anchor_pt is None:
        anchor_pt = points[0]
    latest_pt = points[-1]

    # FV upgrade signal
    fv_upgrade = None
    try:
        anchor_fv = float(anchor_pt.get("consensus_fv"))
        latest_fv = float(latest_pt.get("consensus_fv"))
        fv_upgrade = latest_fv - anchor_fv
    except (TypeError, ValueError):
        pass

    # Tool-velocity signal — mean tool-grade composite delta. Iterate
    # tool_consensus on the latest and anchor points; for each tool present
    # at BOTH, compute (latest_grade - anchor_grade); average across tools.
    anchor_tools = anchor_pt.get("tools_consensus") or {}
    latest_tools = latest_pt.get("tools_consensus") or {}
    shared = [k for k in latest_tools.keys()
              if k in anchor_tools and isinstance(anchor_tools[k], (int, float))
              and isinstance(latest_tools[k], (int, float))]
    tool_velocity = None
    if shared:
        deltas = [float(latest_tools[k]) - float(anchor_tools[k]) for k in shared]
        tool_velocity = sum(deltas) / len(deltas)

    fv_signal = fv_upgrade is not None and fv_upgrade >= _BREAKOUT_FV_UPGRADE_THRESHOLD
    tool_signal = tool_velocity is not None and tool_velocity >= _BREAKOUT_TOOL_VELOCITY_THRESHOLD

    # v27 — '+' upside signal: any source ADDED a '+' upside marker
    # within the breakout window (anchor date → latest). A source
    # changing a 50 → 50+ grade is a real "scout-noted upside" event,
    # qualitatively similar to a 50 → 55 FV upgrade even though the
    # numeric FV didn't move. Counts as a third path to the perf-gated
    # breakout classification.
    upside_events = _detect_upside_added_events(points)
    upside_in_window = [
        e for e in upside_events
        if e.get("date") and e["date"] >= window_anchor_date.isoformat()
    ]
    upside_signal = bool(upside_in_window)
    upside_sources = sorted({e["source"] for e in upside_in_window})

    if not (fv_signal or tool_signal or upside_signal):
        return None

    # Performance gate: check hitter wRC+, then pitcher stf_plus_periph
    # or fip_minus. Two-way passes if either side passes. `statline` and
    # `saberm` already defined above for the stat-only gate path.
    #
    # DEAD-READ REMOVED 2026-07-29: a `statline.rps_plus` leg (gated at
    # _BREAKOUT_HITTER_RPS_PLUS_GATE) used to run first here. Same finding as the
    # stat-only path above: nothing writes `rps_plus` into a timeseries statline
    # (draft_export.py / overseas_export.py stamp it top-level on their OWN
    # payloads), so the field is present on 0 of 4,505 players in the served
    # data/timeseries.json and the leg could never fire. Removal is
    # behaviour-identical: all 32 currently-flagged breakouts pass on
    # stf_plus_periph (29) or statcast_plus (3).
    perf_gate_passed = None

    # v15: wRC+ leg for hitters (graduates / MLB-experienced prospects
    # who carry wRC+ in sabermetrics).
    if perf_gate_passed is None:
        wrc = saberm.get("wrc_plus")
        try:
            if wrc is not None and float(wrc) >= _BREAKOUT_HITTER_WRC_PLUS_GATE:
                perf_gate_passed = "wrc_plus"
        except (TypeError, ValueError):
            pass

    if perf_gate_passed is None:
        stf = statline.get("stf_plus_periph")
        try:
            if stf is not None and float(stf) >= _BREAKOUT_PITCHER_STF_PLUS_GATE:
                perf_gate_passed = "stf_plus_periph"
        except (TypeError, ValueError):
            pass

    if perf_gate_passed is None:
        fipm = saberm.get("fip_minus")
        try:
            if fipm is not None and float(fipm) <= _BREAKOUT_PITCHER_FIP_MINUS_GATE:
                perf_gate_passed = "fip_minus"
        except (TypeError, ValueError):
            pass

    # v29 — Statcast+ perf gate. Catches prospects whose tracked
    # Statcast / zone signals indicate elite performance even when the
    # scout-published indices (RPS+, Stuff+, wRC+, FIP-) aren't on
    # file — common for under-tracked MiLB venues with partial Statcast
    # coverage but full game feeds. Side-agnostic since the composite
    # is built per-side already.
    if perf_gate_passed is None:
        sc_plus = payload.get("statcast_plus")
        try:
            if sc_plus is not None and float(sc_plus) >= _BREAKOUT_STATCAST_PLUS_GATE:
                perf_gate_passed = "statcast_plus"
        except (TypeError, ValueError):
            pass

    if perf_gate_passed is None:
        return None

    # v27 — Reason priority: FV upgrade > upside ("+ added") > tools.
    # The FV upgrade is the loudest scout signal; "+ added" is a direct
    # qualitative upside statement; tool velocity is the quietest of the
    # three (a half-point average bump across multiple tools).
    if fv_signal:
        reason = "fv"
    elif upside_signal:
        reason = "upside"
    else:
        reason = "tools"
    return {
        "flag": True,
        "reason": reason,
        "perf_gate": perf_gate_passed,
        "fv_upgrade": round(fv_upgrade, 2) if fv_upgrade is not None else None,
        "tool_velocity": round(tool_velocity, 2) if tool_velocity is not None else None,
        "upside_sources": upside_sources or None,
        "window_anchor_date": window_anchor_date.isoformat(),
    }


def _attach_breakout_flags(payloads: list[dict]) -> None:
    """Stamp `breakout_flag` (bool) + `breakout_meta` (dict) on each active
    payload after _attach_tool_plus_indices has populated everything else."""
    for pl in payloads:
        meta = _compute_breakout_flag(pl)
        if meta is None:
            pl["breakout_flag"] = False
        else:
            pl["breakout_flag"] = True
            pl["breakout_meta"] = meta


def _inactive_cutoff() -> date:
    """Return the date before which a player's last update makes them inactive."""
    today = date.today()
    m = today.month - INACTIVE_MONTHS % 12
    y = today.year - INACTIVE_MONTHS // 12
    if m <= 0:
        m += 12
        y -= 1
    try:
        return date(y, m, today.day)
    except ValueError:
        return date(y, m, 28)  # handle short months

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    snapshot_date   TEXT NOT NULL,
    interval_label  TEXT NOT NULL,
    player_key      TEXT NOT NULL,
    player_name     TEXT NOT NULL,
    position        TEXT,
    org             TEXT,
    rank            INTEGER,
    fv              REAL,
    status          TEXT NOT NULL,
    inserted_at     TEXT NOT NULL DEFAULT (datetime('now')),
    -- v26 — '+' upside marker. 1 when the source string carried a trailing
    -- '+' (e.g., "55+"). Numeric `fv` is the bare tier; this column lets
    -- consensus carry the upside flag forward without inflating numbers.
    fv_plus         INTEGER NOT NULL DEFAULT 0,
    UNIQUE(source, interval_label, player_key)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_player ON snapshots(player_key);
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON snapshots(snapshot_date);

CREATE TABLE IF NOT EXISTS players (
    player_key   TEXT PRIMARY KEY,
    player_name  TEXT NOT NULL,
    position     TEXT,
    org          TEXT,
    birth_date   TEXT,                  -- ISO date 'YYYY-MM-DD'; immutable once known
    is_pitcher   INTEGER DEFAULT 0,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS statlines (
    player_key   TEXT PRIMARY KEY,
    season       INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pitch_arsenals (
    player_key   TEXT PRIMARY KEY,
    season       INTEGER NOT NULL,
    payload_json TEXT NOT NULL,       -- serialized PitchArsenal dataclass
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sabermetrics (
    player_key   TEXT PRIMARY KEY,
    season       INTEGER NOT NULL,
    payload_json TEXT NOT NULL,       -- serialized Sabermetrics dataclass
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS zone_metrics (
    player_key   TEXT PRIMARY KEY,
    season       INTEGER NOT NULL,
    payload_json TEXT NOT NULL,       -- serialized ZoneMetricRow dataclass
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS statcast_metrics (
    player_key   TEXT PRIMARY KEY,
    season       INTEGER NOT NULL,
    payload_json TEXT NOT NULL,       -- serialized StatcastMetricRow dataclass
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS source_events (
    event_key     TEXT PRIMARY KEY,
    player_key    TEXT NOT NULL,
    player_name   TEXT NOT NULL,
    source        TEXT NOT NULL,
    event_date    TEXT NOT NULL,
    event_type    TEXT NOT NULL,
    rank_before   INTEGER,
    rank_after    INTEGER,
    confidence    REAL NOT NULL DEFAULT 0.5,
    payload_json  TEXT NOT NULL DEFAULT '{}',
    excerpt       TEXT,
    inserted_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_source_events_player ON source_events(player_key);
CREATE INDEX IF NOT EXISTS idx_source_events_date ON source_events(event_date);

CREATE TABLE IF NOT EXISTS career_stats (
    player_key   TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,       -- list of per-season stat rows (most recent first)
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Per-graduate career WAR, aggregated from BASEBALL-REFERENCE via
-- pybaseball.bwar_bat / bwar_pitch (the static war_daily tables).
--
-- This comment used to say FanGraphs, describing a bulk batting_stats /
-- pitching_stats pull that no longer exists: FG 403s pybaseball's endpoint
-- (see stats.fetch_career_war_bulk), so the site moved to bWAR and the
-- comment did not follow. Corrected 2026-08-03. The site is bWAR end to end,
-- which is also why the full B-Ref run-value decomposition (runs_bat,
-- runs_field, runs_position, ...) is available to prospect_def_value and
-- mlb_def_history for free.
-- payload_json is a dict:
--   {"seasons": {"2023": 1.5, "2024": 2.8, ...},
--    "career_war": 4.3,
--    "war_per_yr": 2.15,
--    "war_seasons_count": 2,
--    "source": "bbref"}
-- Only populated for graduates / inactives that have at least one MLB
-- season on file; actives skip this fetch entirely (no value-add yet).
CREATE TABLE IF NOT EXISTS career_war (
    player_key   TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS acquisitions (
    player_key   TEXT PRIMARY KEY,
    method       TEXT NOT NULL,       -- 'draft' | 'international_fa' | 'unknown'
    year         INTEGER,             -- draft year or IFA signing year
    round_label  TEXT,                -- '1', '2', 'CBA', 'CBB', etc.
    pick_round   INTEGER,             -- pick within the round
    pick_overall INTEGER,             -- overall pick number
    bonus_usd    INTEGER,             -- signing bonus in dollars
    team_name    TEXT,                -- drafting / signing team
    school       TEXT,                -- HS/college for draftees
    signing_date TEXT,                -- ISO date when known
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS il_status (
    player_key   TEXT PRIMARY KEY,
    is_on_il     INTEGER NOT NULL,    -- 0/1
    since        TEXT,                 -- ISO date of placement (retroactive when known)
    type         TEXT,                 -- '10-day', '15-day', '60-day', etc.
    description  TEXT,                 -- full transaction text from API
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Per-player raw transactions cache (MLB Stats API /transactions?playerId=).
-- Drives within-season promotion/demotion detection AND the options /
-- service-time heuristics. One row per player; payload_json is the list
-- of {date, type_code, description, from_team_id, from_team_name,
-- to_team_id, to_team_name} dicts sorted ascending by date.
CREATE TABLE IF NOT EXISTS player_transactions (
    player_key   TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Derived MLB roster timeline per player. Computed from the transactions
-- cache + career_stats: {debut_date, options_used, on_40_man, service_days,
-- service_years_decimal, arb_year (0=pre-arb, 1-3=arb, 4+=post-arb)}.
CREATE TABLE IF NOT EXISTS roster_status (
    player_key      TEXT PRIMARY KEY,
    payload_json    TEXT NOT NULL,
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trades (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    player_key       TEXT NOT NULL,
    trade_date       TEXT NOT NULL,
    from_org         TEXT,
    to_org           TEXT,
    source           TEXT NOT NULL,             -- 'mlb_api' | 'inferred'
    description      TEXT,
    date_range_start TEXT,
    date_range_end   TEXT,
    inserted_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(player_key, trade_date, source)
);
CREATE INDEX IF NOT EXISTS idx_trades_player ON trades(player_key);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    new_snapshots INTEGER DEFAULT 0,
    stat_lines    INTEGER DEFAULT 0,
    notes         TEXT
);

-- ===========================================================================
-- Forward-looking history tables (added 2026-06). The per-source `snapshots`
-- table already retains grade/rank history per published list, but the
-- DERIVED state — the PROSPX consensus board rank and the Arkmetric family
-- (DvM+/SC+/$DvM+/Tool/live composite) — was only ever stored as the CURRENT
-- value (keyed by player_key, overwritten each run). These two tables capture
-- that derived state over time so the time-travel board (Part 2) and the
-- Arkmetric-vs-outcome backtest (Part 4) compound going forward. They cannot
-- be back-filled — the track record begins the first run after this lands.
-- ===========================================================================

-- One row per (player, snapshot calendar date): the full DERIVED board state.
-- Written at the end of every full run_monthly (and standalone --rebuild-only).
-- Upsert-by-date is idempotent: re-running on the same day overwrites that
-- day's row, so cadence is governed entirely by how often run_monthly runs
-- (monthly via the scheduled job → one row per player per month).
CREATE TABLE IF NOT EXISTS metric_snapshots (
    player_key    TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,        -- 'YYYY-MM-DD' of the run
    overall_rank  INTEGER,              -- PROSPX board rank as-of. Ranked on the RAW eFV
                                        -- grade (BOARD_GRADE_FIELD) from
                                        -- BOARD_RANK_BASIS_EPOCH on; earlier rows are on
                                        -- the retired quantile basis and are filtered out
                                        -- by load_rank_history (see the epoch constant).
    consensus_fv  REAL,                 -- headline consensus FV (fv_close)
    fv_plus       INTEGER NOT NULL DEFAULT 0,
    fv_tier       TEXT,                 -- bucket label ('60','55',… ) for cohorting
    org           TEXT,
    position      TEXT,
    status        TEXT,                 -- active | debuted | inactive
    is_pitcher    INTEGER NOT NULL DEFAULT 0,
    age           REAL,
    payload_json  TEXT NOT NULL,        -- {dollar_dvm_plus, statcast_plus, tool,
                                        --  consensus_live_score, surplus_mm, …} — the
                                        --  Arkmetric family
    inserted_at   TEXT NOT NULL DEFAULT (datetime('now')),
    -- Source coverage (owner answer B4SP-2, 2026-10-01), recorded from
    -- METRIC_SNAPSHOT_COVERAGE_START on, forward only; NULL source_n = not
    -- recorded. Definitions: consensus.point_source_coverage.
    source_n          INTEGER,          -- outlets whose FV entered the consensus FV
    source_keys       TEXT,             -- those outlets, sorted, comma-joined
    best_rank         INTEGER,          -- smallest league-wide rank >= 1 counted
    best_rank_source  TEXT,             -- outlet of best_rank
    best_rank_date    TEXT,             -- list date of best_rank
    PRIMARY KEY (player_key, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_metric_snap_date ON metric_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_metric_snap_player ON metric_snapshots(player_key);

-- One row per (player_key, snapshot date): the Trade Machine board surplus
-- value as-of. Enables a TRUE forward backtest of the board ordering (the
-- trade_machine_surplus eval is currently rank-only/hindsight because
-- trade_values.json was never snapshotted). Cannot be back-filled - the track
-- record begins the first run after this lands. Idempotent upsert-by-date.
CREATE TABLE IF NOT EXISTS trade_value_history (
    player_key        TEXT NOT NULL,
    snapshot_date     TEXT NOT NULL,
    trade_value_mm    REAL,
    surplus_source    TEXT,               -- xfv | projection | xfv_backgrade
    trade_value_tier  TEXT,
    trade_value_grade TEXT,
    xfv_grade         REAL,
    status            TEXT,               -- active | debuted | graduated
    age               REAL,
    position          TEXT,
    org               TEXT,
    inserted_at       TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (player_key, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_tradeval_date ON trade_value_history(snapshot_date);

-- M04-05 (2026-09-25). One row per (class_year, player_key, snapshot date):
-- the P(enter) the /fa/ board SERVED that night for every pending_option
-- member, read back from the fa_class.json the export just wrote. The frozen
-- docs/fa-2026-08-19/PENTER_DECISION_EVAL_PREREG.md scores "the LAST served
-- value before" each decision, "read from artifact snapshots", and nothing
-- kept them: the file is rewritten nightly and the box's nightly checkout
-- reverts the tracked copy. Cannot be back-filled; the record begins the
-- first night this runs on the serving box. Upsert-by-date, last write wins
-- (the night's final export is the served one). host and git_sha say which
-- machine and code wrote a row, so a dev-to-box DB re-seed cannot pass dev
-- rows off as served ones.
CREATE TABLE IF NOT EXISTS fa_penter_served_history (
    class_year            INTEGER NOT NULL,
    player_key            TEXT NOT NULL,
    snapshot_date         TEXT NOT NULL,
    fa_type               TEXT,
    status                TEXT,
    opt_price_usd         REAL,
    enter_prob            REAL,
    enter_prob_src        TEXT,
    proj_aav_usd          REAL,
    proj_aav_p10_usd      REAL,
    proj_aav_p90_usd      REAL,
    fa_class_generated_at TEXT,
    host                  TEXT,
    git_sha               TEXT,
    inserted_at           TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (class_year, player_key, snapshot_date)
);

-- One row per (org, snapshot calendar date): the composite farm-system rank
-- and the farm_score it sorts on. Sibling to metric_snapshots, but at the ORG
-- grain rather than the player grain — metric_snapshots never stored the
-- derived org farm_rank over time, so farm-rank movement (an org climbing /
-- falling in the 30-team rankings) had no history input. The de-noised farm
-- movement engine (movement.compute_farm_movement) reads this. Like its
-- sibling it cannot be back-filled: the track record begins the first run
-- after this lands. Upsert-by-(org, date) is idempotent.
CREATE TABLE IF NOT EXISTS farm_rank_history (
    org           TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,        -- 'YYYY-MM-DD' of the run
    farm_rank     INTEGER,              -- composite farm-system rank (1 = best of 30)
    farm_score    REAL,                 -- composite score the rank sorts on
    inserted_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (org, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_farm_rank_hist_date ON farm_rank_history(snapshot_date);

-- One row per (org, snapshot calendar date): the composite farm LETTER grade
-- as displayed on the PROSPX farm systems view (letter_by_window at the
-- principal 7y window, falling back to the canonical grades.overall) plus the
-- numeric composite the letter's rank bucket sorts on and the window setting
-- that produced it. Sibling to farm_rank_history at the same org grain. The
-- letter was previously derived at export and never persisted, which is why
-- the farm_grades registry row is provisional (no letter history means no
-- forward validation; review-queue item 10). Cannot be back-filled: history
-- begins 2026-07-02. Upsert by (org, date) is idempotent within a day; rows
-- for prior dates are never rewritten or deleted (append-only).
CREATE TABLE IF NOT EXISTS farm_grade_history (
    org           TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,        -- 'YYYY-MM-DD' of the run
    letter        TEXT NOT NULL,        -- composite letter, 'A+' through 'F'
    farm_score    REAL,                 -- numeric composite behind the letter
    grade_window  TEXT,                 -- '7y' principal; 'canonical' on fallback
    inserted_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (org, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_farm_grade_hist_date ON farm_grade_history(snapshot_date);

-- Append-only IL stint timeline. The il_status table is current-state only
-- (overwritten each run); this records each placement once (keyed by the
-- placement `since` date) and stamps the activation date when the player
-- next appears OFF the IL. Built by the daily job so IL track record accrues.
CREATE TABLE IF NOT EXISTS il_history (
    player_key     TEXT NOT NULL,
    since          TEXT NOT NULL,       -- IL placement date per the API (stint id)
    il_type        TEXT,                -- '7-day' | '10-day' | '60-day' | …
    description    TEXT,
    placed_seen    TEXT NOT NULL,       -- first run-date we observed this stint
    activated_seen TEXT,                -- first run-date we observed them OFF it (NULL while ongoing)
    inserted_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (player_key, since)
);
CREATE INDEX IF NOT EXISTS idx_il_history_player ON il_history(player_key);

-- Resolved+validated headshot context per MLBAM id (added 2026-06). The MLB
-- CDN serves headshots keyed by player id under a context segment: '67' is the
-- MLB roster set (empty for many prospects → silhouette), 'milb' is the MiLB
-- set (fills most of those gaps). We HEAD-probe both (no generic fallback so a
-- missing photo 404s) and cache the first that returns a real image; 'none'
-- means neither resolved. Keyed by mlbam_id because the photo follows the id
-- (a player keeps it across the active→debuted transition).
CREATE TABLE IF NOT EXISTS player_photos (
    mlbam_id     INTEGER PRIMARY KEY,
    headshot_ctx TEXT NOT NULL,            -- '67' | 'milb' | 'none'
    player_key   TEXT,                     -- last-seen key (for reference/reporting)
    checked_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ===========================================================================
-- Draft prospects (amateurs — HS/college players in upcoming MLB drafts)
-- ===========================================================================
-- Parallel track to the snapshots/players tables. Column-level firewall:
-- no draft player ever appears in `snapshots`, `players`, `statlines`,
-- `sabermetrics`, etc. until they're DRAFTED (see draft_promotion.py),
-- at which point a single MiLB snapshot row is created in the standard
-- tables. RPS+ and other MiLB-cohort metrics are structurally excluded.

CREATE TABLE IF NOT EXISTS draft_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,        -- 'fangraphs' | 'espn_draft' | 'mlb_pipeline_draft' | 'manual'
    snapshot_date   TEXT NOT NULL,
    interval_label  TEXT NOT NULL,
    player_key      TEXT NOT NULL,        -- draft_<year>_<name_slug>
    player_name     TEXT NOT NULL,
    position        TEXT,
    school          TEXT,                 -- HS or college name
    college_commit  TEXT,                 -- HS commits (NULL for college players)
    player_type     TEXT,                 -- 'HSh'|'HSp'|'COLh'|'COLp'
    draft_year      INTEGER NOT NULL,
    rank            INTEGER,              -- per-source rank within the class
    fv              REAL,
    risk            TEXT,
    status          TEXT NOT NULL,        -- 'draft_active' | 'drafted' | 'unsigned' | 'transferred'
    tools_json      TEXT,                 -- {tools_future, tools_present, report, video, ...}
    fv_plus         INTEGER NOT NULL DEFAULT 0,  -- v26 — '+' upside marker
    inserted_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, interval_label, player_key)
);
CREATE INDEX IF NOT EXISTS idx_draft_snap_year   ON draft_snapshots(draft_year);
CREATE INDEX IF NOT EXISTS idx_draft_snap_player ON draft_snapshots(player_key);
CREATE INDEX IF NOT EXISTS idx_draft_snap_date   ON draft_snapshots(snapshot_date);

CREATE TABLE IF NOT EXISTS draft_players (
    player_key      TEXT PRIMARY KEY,
    player_name     TEXT NOT NULL,
    position        TEXT,
    school          TEXT,
    college_commit  TEXT,
    player_type     TEXT,
    draft_year      INTEGER NOT NULL,
    birth_date      TEXT,
    bats            TEXT,
    throws          TEXT,
    height          TEXT,
    weight          INTEGER,
    fg_player_id    TEXT,
    mlbam_id        INTEGER,
    promoted_key    TEXT,                  -- canonical MiLB player_key after draft (NULL until drafted)
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Post-draft picks + signing bonuses. One row per (year, pick_overall).
CREATE TABLE IF NOT EXISTS draft_results (
    draft_year     INTEGER NOT NULL,
    pick_overall   INTEGER NOT NULL,
    round_label    TEXT,                  -- '1', '2', 'CBA', 'CBB', 'PPI', etc.
    pick_in_round  INTEGER,
    team           TEXT NOT NULL,         -- canonical org code
    player_key     TEXT,                  -- draft_<year>_<name_slug> when matched
    player_name    TEXT NOT NULL,
    school         TEXT,
    slot_usd       INTEGER,
    bonus_usd      INTEGER,
    signed         INTEGER NOT NULL DEFAULT 0,
    source         TEXT,                  -- 'fg_draft_csv' | 'mlb_draft_tracker' | 'manual'
    inserted_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (draft_year, pick_overall)
);
CREATE INDEX IF NOT EXISTS idx_draft_results_team   ON draft_results(team);
CREATE INDEX IF NOT EXISTS idx_draft_results_player ON draft_results(player_key);

-- Draft order — the assigned pick sequence (1-30 first round + comp picks)
-- for a given year. Pre-draft this drives the "Draft Order & Slots" panel;
-- post-draft it's redundant with draft_results.team but we keep it so the
-- mock-draft view can show team logos before draft day.
CREATE TABLE IF NOT EXISTS draft_order (
    draft_year     INTEGER NOT NULL,
    pick_overall   INTEGER NOT NULL,
    round_label    TEXT,
    pick_in_round  INTEGER,
    team           TEXT NOT NULL,
    slot_usd       INTEGER,
    source         TEXT NOT NULL,         -- 'mlb_draft_pool' | 'manual'
    inserted_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (draft_year, pick_overall)
);

-- Maps draft_<year>_<name> player_keys to canonical MiLB keys after
-- promotion. Read at promotion time + by the Draft UI to surface a
-- "DRAFTED — see MiLB profile" link.
CREATE TABLE IF NOT EXISTS draft_canonical_keys (
    draft_key      TEXT PRIMARY KEY,
    milb_key       TEXT NOT NULL,
    promoted_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_draft_canonical_milb ON draft_canonical_keys(milb_key);

-- Draft lottery + projected order (Tankathon). Originally stored just
-- lottery odds for the top-6 picks; now stores the FULL projected
-- first-round order (slots 1-30 + comp picks). `odds_pct` is nullable
-- for deterministic slots (picks 7+). `round_label` distinguishes
-- regular ("1") from competitive-balance ("1A" / "1B") picks.
-- `odds_pct` is the % chance at the #1 overall pick; `odds_top6_pct` is the
-- % chance of landing anywhere in the 6-pick lottery. Both are NULL for
-- deterministic slots, for lottery-INELIGIBLE non-playoff teams, and for
-- comp picks. `wins`/`losses` are the team's record at scrape time (NULL on
-- comp picks, which come from a sidebar with no standings columns, and on
-- every row written before 2026-07-31).
CREATE TABLE IF NOT EXISTS draft_lottery_odds (
    draft_year      INTEGER NOT NULL,
    team            TEXT NOT NULL,
    pick_pos        INTEGER NOT NULL,
    odds_pct        REAL,
    odds_top6_pct   REAL,
    wins            INTEGER,
    losses          INTEGER,
    round_label     TEXT NOT NULL DEFAULT '1',
    snapshot_date   TEXT NOT NULL,
    source          TEXT NOT NULL,
    inserted_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (draft_year, team, pick_pos, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_draft_lottery_year ON draft_lottery_odds(draft_year);

-- ===========================================================================
-- Overseas prospects (established KBO/NPB/CPBL pros)
-- ===========================================================================
-- Parallel cohort to draft amateurs and MiLB prospects. NPB / KBO players
-- are established pros in foreign top leagues, eligible for MLB through
-- the posting system or international FA. Status journey:
--   overseas_active  →  posted  →  signed  →  mlb_promoted
-- RPS+ and other MiLB-cohort metrics are structurally excluded: overseas
-- prospects live in their own tables, never touching `snapshots` /
-- `players` / `statlines` until promotion to MLB.

CREATE TABLE IF NOT EXISTS overseas_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,           -- 'fangraphs' | 'manual'
    snapshot_date   TEXT NOT NULL,
    interval_label  TEXT NOT NULL,
    player_key      TEXT NOT NULL,           -- 'overseas_<league>_<name_slug>'
    player_name     TEXT NOT NULL,
    position        TEXT,
    league          TEXT,                    -- 'NPB' | 'KBO' | 'CPBL' | 'CUBA' | 'NPBF'
    country         TEXT,
    current_team    TEXT,                    -- foreign club they currently play for
    proj_team       TEXT,                    -- projected MLB destination (when FG guesses)
    proj_bonus_usd  INTEGER,
    eta_year        INTEGER,
    fv              REAL,
    risk            TEXT,
    status          TEXT NOT NULL,           -- 'overseas_active'|'posted'|'signed'|'mlb_promoted'
    tools_json      TEXT,
    fv_plus         INTEGER NOT NULL DEFAULT 0,  -- v26 — '+' upside marker
    inserted_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, interval_label, player_key)
);
CREATE INDEX IF NOT EXISTS idx_overseas_snap_league ON overseas_snapshots(league);
CREATE INDEX IF NOT EXISTS idx_overseas_snap_player ON overseas_snapshots(player_key);
CREATE INDEX IF NOT EXISTS idx_overseas_snap_date   ON overseas_snapshots(snapshot_date);

-- TJStats (Thomas Nestico) per-(MLBAM id, snapshot) point-in-time sidecar.
-- The consensus-relevant rank/FV/tools ALSO land in the generic `snapshots`
-- table (source='tjstats', name-slug player_key) so TJStats merges into
-- consensus like every other source; THIS table is the authoritative MLBAM-keyed
-- grain that carries the full provenance + writeup + raw grades for Time Machine
-- + Source Comparison, without bloating the shared snapshots row. captured_at is
-- the real UTC scrape moment (the source of truth for "when we saw this");
-- effective_date is TJStats's own pushed_at for named snapshots, or the capture
-- date for the Live board. Upsert grain = (mlbam_id, snapshot_label): a same-day
-- Live re-run (same date-stamped label) updates in place; a new day or a new
-- named snapshot creates a new row.
CREATE TABLE IF NOT EXISTS tjstats_snapshots (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    mlbam_id           TEXT NOT NULL,
    player_key         TEXT,                    -- resolved eephus key (name-slug)
    snapshot_label     TEXT NOT NULL,           -- verbatim: 'May 2026' | 'Live 2026-06-08'
    snapshot_kind      TEXT NOT NULL,           -- 'live' | 'named'
    snapshot_id        TEXT,                    -- TJStats major-snapshot id (named only)
    effective_date     TEXT,                    -- TJStats pushed_at date | Live capture date
    captured_at        TEXT NOT NULL,           -- UTC ISO 8601 — actual scrape moment
    source_modified_at TEXT,                    -- page article:modified_time (cross-check)
    source_url         TEXT,
    name               TEXT,
    position           TEXT,
    org                TEXT,                    -- eephus org key
    type               TEXT,                    -- 'batter' | 'pitcher'
    rank               INTEGER,
    prev_rank          INTEGER,
    fv                 REAL,                    -- NULL on snapshots older than current scout grades
    eta                TEXT,
    risk               TEXT,
    grades_json        TEXT,                    -- raw TJStats 20-80 pv/fv grades
    tools_json         TEXT,                    -- eephus-keyed tool grades
    writeup            TEXT,                    -- TJStats scouting report (attributed)
    with_fv            INTEGER NOT NULL DEFAULT 0,
    inserted_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(mlbam_id, snapshot_label)
);
CREATE INDEX IF NOT EXISTS idx_tjstats_snap_label ON tjstats_snapshots(snapshot_label);
CREATE INDEX IF NOT EXISTS idx_tjstats_snap_key   ON tjstats_snapshots(player_key);
CREATE INDEX IF NOT EXISTS idx_tjstats_snap_date  ON tjstats_snapshots(effective_date);

CREATE TABLE IF NOT EXISTS overseas_players (
    player_key       TEXT PRIMARY KEY,
    player_name      TEXT NOT NULL,
    position         TEXT,
    league           TEXT,
    country          TEXT,
    current_team     TEXT,
    proj_team        TEXT,
    proj_bonus_usd   INTEGER,
    eta_year         INTEGER,
    birth_date       TEXT,
    bats             TEXT,
    throws           TEXT,
    height           TEXT,
    weight           INTEGER,
    fg_player_id     TEXT,
    mlbam_id         INTEGER,
    promoted_key     TEXT,                   -- canonical MiLB key after signing
    posted_date      TEXT,                   -- ISO date of posting (when known)
    signed_date      TEXT,
    signed_team      TEXT,
    signed_bonus_usd INTEGER,
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Per-player season stats from FG player pages. Mirrors the `statlines`
-- table shape but scoped to KBO/NPB/CPBL leagues.
CREATE TABLE IF NOT EXISTS overseas_statlines (
    player_key   TEXT NOT NULL,
    season       INTEGER NOT NULL,
    league       TEXT NOT NULL,              -- 'NPB' | 'KBO' | 'NPBF' (NPB farm) | 'CPBL'
    team         TEXT,
    payload_json TEXT NOT NULL,              -- {pa, ip, avg, obp, slg, era, k_pct, bb_pct, wrc_plus, fip, ...}
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (player_key, season, league)
);
CREATE INDEX IF NOT EXISTS idx_overseas_stats_player ON overseas_statlines(player_key);

-- v31.8 — Cache of non-prospect MLB players that show up in trade
-- descriptions but aren't in our actives/grads/inactives database.
-- Lets the trade audit value them via career WAR × $/WAR. Populated
-- on demand by `mlb_trade_lookup.refresh_mlb_trade_players()` which
-- parses trade descriptions, resolves names via the MLB Stats API,
-- and caches career WAR aggregates.
CREATE TABLE IF NOT EXISTS mlb_trade_players (
    -- Lowercase, punctuation-stripped name slug. Used as the lookup
    -- key from the frontend trade audit when description-parsed names
    -- don't match a tracked prospect.
    name_slug      TEXT PRIMARY KEY,
    player_name    TEXT NOT NULL,
    mlbam_id       INTEGER,
    primary_position TEXT,           -- C / 1B / 2B / SS / 3B / OF / SP / RP
    career_war     REAL,             -- accumulated bWAR across MLB seasons
    war_seasons    INTEGER,          -- MLB seasons that contributed
    last_team      TEXT,             -- current / last MLB team abbrev
    is_pitcher     INTEGER NOT NULL DEFAULT 0,
    fetched_at     TEXT NOT NULL DEFAULT (datetime('now')),
    resolve_status TEXT,             -- "resolved" | "ambiguous" | "not_found"
    -- v31.9c — Contract-based surplus columns. When a Spotrac match
    -- is on file, current_aav_usd + years_remaining + projected_war
    -- combine into surplus_mm via the projected-remaining-WAR × $8M
    -- minus sum-of-remaining-AAV formula. Surplus_mm trumps the
    -- naive career_war × $8M valuation on the frontend trade audit
    -- (more accurate when a team is acquiring future value, not
    -- realized historical value). NULL when no contract data found.
    current_aav_usd     INTEGER,
    years_remaining     INTEGER,
    contract_total_usd  INTEGER,
    age                 INTEGER,
    projected_war_remaining REAL,    -- aging-curve adjusted future WAR
    surplus_mm          REAL         -- (projected_war × $8M) − (aav × yrs) in $M
);
CREATE INDEX IF NOT EXISTS idx_mlb_trade_players_status ON mlb_trade_players(resolve_status);

-- =========================================================================
-- MLB Free Agency module (additive — fa_* tables only; nothing here is
-- read by the prospect pool, farm grades, or surplus aggregates).
-- payload_json pattern throughout, matching career_war / mlb_trade_players.
-- =========================================================================
-- One row per (player, FA class winter); payload is the POINT-IN-TIME
-- class-construction record (age, from_team, option flags, enter_prob,
-- QO status) — frozen at build, never backfilled from current state.
CREATE TABLE IF NOT EXISTS fa_class_players (
    player_key   TEXT NOT NULL,
    class_year   INTEGER NOT NULL,        -- 2027 = the 2026-27 offseason
    mlbam_id     INTEGER,
    position     TEXT,
    status       TEXT,                    -- locked | pending_option | signed | ...
    payload_json TEXT NOT NULL,
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (player_key, class_year)
);
CREATE INDEX IF NOT EXISTS idx_fa_class_status ON fa_class_players(class_year, status);

-- Historical + live signings ledger (2014-15 winter onward). payload
-- carries terms (years/guarantee/aav), from/to teams, qo flags, the
-- mlb_deal flag, and — once elapsed seasons exist — the retrospective
-- ledger block (realized WAR x per-season $/WAR vs paid).
CREATE TABLE IF NOT EXISTS fa_signings (
    player_key   TEXT NOT NULL,
    class_year   INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (player_key, class_year)
);
CREATE INDEX IF NOT EXISTS idx_fa_signings_year ON fa_signings(class_year);

-- Out-of-row "we successfully checked this source" ledger. A row-level
-- fetched_at can only record that something CHANGED, so a source that is
-- healthy but quiet (no new signings all summer, an empty class year) is
-- indistinguishable from a source that is broken. Only successful checks
-- are recorded here, so a parser that silently returns 0 rows leaves the
-- stamp behind rather than refreshing it.
CREATE TABLE IF NOT EXISTS source_checks (
    source     TEXT NOT NULL,
    scope      TEXT NOT NULL DEFAULT '',
    checked_at TEXT NOT NULL DEFAULT (datetime('now')),
    n_rows     INTEGER,
    PRIMARY KEY (source, scope)
);

-- Spotrac CBT/payroll ledgers per (team, season).
CREATE TABLE IF NOT EXISTS fa_team_payroll (
    team         TEXT NOT NULL,
    season       INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (team, season)
);

-- Editorial flags logged AT EMIT TIME (model-audit WS-0c): spotlights /
-- movement-engine buckets persisted with matched-control sampling keys
-- (FV band x level x age band) so 30/60-day forward hit rates can be
-- scored once cohorts mature. Append-only per (player, flag, run date);
-- monthly cadence (rides the monthly export, never the daily job).
CREATE TABLE IF NOT EXISTS editorial_flags (
    player_key  TEXT NOT NULL,
    flag_type   TEXT NOT NULL,          -- riser | rebound | faller
    emitted_at  TEXT NOT NULL,          -- run date (YYYY-MM-DD)
    score       REAL,
    fv          REAL,                   -- consensus FV at emit time
    fv_band     TEXT,
    level       TEXT,
    age_band    TEXT,
    inserted_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (player_key, flag_type, emitted_at)
);

-- Stage-2+ artifacts: projections / market predictions / gate evals are
-- versioned by model_version so backtests and live runs never collide.
CREATE TABLE IF NOT EXISTS fa_projections (
    player_key    TEXT NOT NULL,
    class_year    INTEGER NOT NULL,
    model_version TEXT NOT NULL,
    payload_json  TEXT NOT NULL,
    computed_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (player_key, class_year, model_version)
);
CREATE TABLE IF NOT EXISTS fa_market_preds (
    player_key    TEXT NOT NULL,
    class_year    INTEGER NOT NULL,
    model_version TEXT NOT NULL,
    payload_json  TEXT NOT NULL,
    computed_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (player_key, class_year, model_version)
);
CREATE TABLE IF NOT EXISTS fa_model_eval (
    model_version TEXT NOT NULL,
    gate          TEXT NOT NULL,          -- 'projection' | 'market'
    payload_json  TEXT NOT NULL,
    computed_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (model_version, gate)
);
CREATE TABLE IF NOT EXISTS fa_park_factors (
    venue        TEXT NOT NULL,
    season       INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (venue, season)
);

-- Append-only winter event ledger. event_date is the FIRST-SEEN date —
-- Spotrac publishes no per-signing dates, so the pipeline stamps each
-- transition when it observes it (ex-ante, consistent with the module's
-- no-lookahead rule) and never updates it afterward. Feeds the homepage
-- WIRE and the /fa/ Signing Tracker.
CREATE TABLE IF NOT EXISTS fa_events (
    class_year   INTEGER NOT NULL,
    player_key   TEXT NOT NULL,
    event_type   TEXT NOT NULL,            -- 'signing' | 'option_exercised' | 'option_declined' | 'qo_offered'
    event_date   TEXT NOT NULL,            -- first observed (yyyy-mm-dd)
    payload_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (class_year, player_key, event_type)
);
CREATE INDEX IF NOT EXISTS idx_fa_events_year ON fa_events(class_year, event_date);

-- v31.7 — Per-player season stats from FG player pages for DRAFT
-- prospects (college + HS). FG hosts amateur stats at the same
-- /players/<slug>/<playerId>/stats URL as overseas players; the
-- difference is the LEVEL column carries college conference codes
-- (SEC / ACC / Big 12 / etc.) or HS / Summer-league codes instead
-- of NPB/KBO/CPBL. Same payload shape so the scraper can reuse the
-- overseas parser with minor filtering.
CREATE TABLE IF NOT EXISTS draft_statlines (
    player_key   TEXT NOT NULL,
    season       INTEGER NOT NULL,
    league       TEXT NOT NULL,              -- conf code (SEC, ACC, B12, ...) or "HS", "Summer", "Cape Cod", etc.
    team         TEXT,                       -- college team or HS / showcase team
    payload_json TEXT NOT NULL,
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (player_key, season, league)
);
CREATE INDEX IF NOT EXISTS idx_draft_stats_player ON draft_statlines(player_key);

-- College box scores for CollegeSavant's tracked universe (the reverse of
-- draft_statlines: keyed by the CS frontend slug, not a draft player_key), so
-- tracked players who are NOT draft prospects can still carry a real college
-- line. Populated by college_stats.refresh_collegesavant_stats from NCAA D-I.
CREATE TABLE IF NOT EXISTS collegesavant_box_scores (
    player_slug  TEXT NOT NULL,           -- slugify_cs(name): the CS frontend key
    season       INTEGER NOT NULL,
    side         TEXT NOT NULL,           -- 'batting' | 'pitching'
    school       TEXT,
    payload_json TEXT NOT NULL,
    fetched_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (player_slug, season, side)
);

CREATE TABLE IF NOT EXISTS overseas_canonical_keys (
    overseas_key   TEXT PRIMARY KEY,
    milb_key       TEXT NOT NULL,
    signed_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_overseas_canon_milb ON overseas_canonical_keys(milb_key);
"""


@contextmanager
def connect():
    # timeout=30s: the monthly run executes draft + overseas + milb pipelines
    # CONCURRENTLY (ThreadPoolExecutor, run_monthly._run_*_pipeline) against this
    # one SQLite file. A reader that lands while another thread holds the write
    # lock must WAIT it out, not fail. The Python-level `timeout` plus the
    # matching PRAGMA busy_timeout below give a hard 30s budget before SQLITE_BUSY
    # is raised — long enough to ride out any single batch write in the pipeline.
    con = sqlite3.connect(DB_PATH, timeout=30.0)
    con.row_factory = sqlite3.Row
    # v19 — Performance pragmas. WAL mode gives 2-5x faster writes plus
    # concurrent readers (the prior rollback-journal mode serialized
    # every reader/writer). synchronous=NORMAL keeps durability against
    # process crashes (full data integrity) while letting OS-level
    # fsync batch — saves a per-statement fsync on every commit. These
    # pragmas only need to fire once per connection; they persist on
    # the DB file (journal_mode) or just the connection (synchronous).
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA temp_store=MEMORY")
        con.execute("PRAGMA cache_size=-65536")  # 64 MB page cache (negative = KB)
        con.execute("PRAGMA busy_timeout=30000")  # wait up to 30s on a locked DB (concurrent pipeline) instead of erroring
    except sqlite3.OperationalError:
        # Pragmas can fail on a corrupt / read-only DB; that's surfaced
        # downstream by the actual query. Don't block connection here.
        pass
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _checkpoint_and_maybe_vacuum() -> None:
    """End-of-run DB maintenance (finding [21]).

    prospects.db runs in WAL mode. Row deletes (leak-row purges, eFV-pool
    churn, snapshot re-dates, monthly re-inserts) leave free pages SQLite never
    reclaims without VACUUM, and the -wal sidecar can sit at its full-monthly
    high-water mark, so the file grows and every daily `.backup` copy inherits
    the slack.

      * PRAGMA wal_checkpoint(TRUNCATE) - always run: flush the WAL into the
        main DB and truncate the -wal back to 0 bytes. Cheap, and returns
        `busy` (no error) if another connection is mid-write.
      * VACUUM - OPT-IN ONLY, via env PROSPECTS_DB_VACUUM=1. It needs ~2x
        transient disk + an exclusive lock, so it must NEVER run on the daily
        hot path; enable it only on the canonical box's monthly branch, and
        schedule it BEFORE the daily backup so the backup captures the
        compacted file.

    Best-effort: any failure here is swallowed so it can never fail a run. Runs
    on a dedicated autocommit connection because wal_checkpoint / VACUUM must
    not execute inside an open transaction."""
    try:
        con = sqlite3.connect(DB_PATH, timeout=30.0, isolation_level=None)
    except sqlite3.Error:
        return
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        if os.environ.get("PROSPECTS_DB_VACUUM") == "1":
            con.execute("VACUUM")
    except sqlite3.Error:
        pass
    finally:
        con.close()


def init_db():
    with connect() as con:
        con.executescript(SCHEMA)
        # Migration: add birth_date column to existing players tables.
        # ALTER TABLE ADD COLUMN is a no-op on fresh DBs (column already
        # exists from the CREATE TABLE), but we catch the error if so.
        try:
            con.execute("ALTER TABLE players ADD COLUMN birth_date TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        # Migration: add tools_json column to snapshots for per-source
        # 20-80 tool grades. Older snapshots keep NULL — consensus + the
        # serializer treat NULL identically to "source didn't publish tools".
        try:
            con.execute("ALTER TABLE snapshots ADD COLUMN tools_json TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
        # v26 — Migration: add fv_plus column to snapshots / draft_snapshots
        # / overseas_snapshots. Older rows default to 0 (no '+' on file).
        # Rows whose .5 fv values came from a "+" parse were back-filled by
        # the one-shot tools/migrate_fv_plus_from_decimal.py, since removed;
        # it stays in git history at commit 3d9426b3.
        for tbl in ("snapshots", "draft_snapshots", "overseas_snapshots"):
            try:
                con.execute(f"ALTER TABLE {tbl} ADD COLUMN fv_plus INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # column already exists
        # Migration: add round_label to draft_lottery_odds so the table
        # can store comp picks (1A / 1B) alongside the regular first-round
        # projection. Old rows default to '1'.
        try:
            con.execute("ALTER TABLE draft_lottery_odds ADD COLUMN round_label TEXT NOT NULL DEFAULT '1'")
        except sqlite3.OperationalError:
            pass  # column already exists
        # v31.9c — Migration: add contract-based surplus columns to
        # mlb_trade_players. Existing rows default to NULL.
        for _col, _ddl in (
            ("current_aav_usd",          "INTEGER"),
            ("years_remaining",          "INTEGER"),
            ("contract_total_usd",       "INTEGER"),
            ("age",                      "INTEGER"),
            ("projected_war_remaining",  "REAL"),
            ("surplus_mm",               "REAL"),
        ):
            try:
                con.execute(f"ALTER TABLE mlb_trade_players ADD COLUMN {_col} {_ddl}")
            except sqlite3.OperationalError:
                pass  # column already exists
        # Migration: relax odds_pct NOT NULL constraint so picks 7+ on
        # the projected order (no published odds) can be stored. SQLite
        # doesn't support ALTER COLUMN — rebuild the table preserving
        # existing rows. Only triggers when the schema is the old one.
        try:
            cols = {r[1]: r for r in con.execute("PRAGMA table_info(draft_lottery_odds)").fetchall()}
            # The PRAGMA row format is (cid, name, type, notnull, dflt_value, pk).
            if cols.get("odds_pct") and cols["odds_pct"][3] == 1:  # notnull flag
                con.executescript("""
                    CREATE TABLE draft_lottery_odds_new (
                        draft_year      INTEGER NOT NULL,
                        team            TEXT NOT NULL,
                        pick_pos        INTEGER NOT NULL,
                        odds_pct        REAL,
                        round_label     TEXT NOT NULL DEFAULT '1',
                        snapshot_date   TEXT NOT NULL,
                        source          TEXT NOT NULL,
                        inserted_at     TEXT NOT NULL DEFAULT (datetime('now')),
                        PRIMARY KEY (draft_year, team, pick_pos, snapshot_date)
                    );
                    INSERT INTO draft_lottery_odds_new
                      (draft_year, team, pick_pos, odds_pct, round_label,
                       snapshot_date, source, inserted_at)
                    SELECT draft_year, team, pick_pos, odds_pct, round_label,
                           snapshot_date, source, inserted_at
                    FROM draft_lottery_odds;
                    DROP TABLE draft_lottery_odds;
                    ALTER TABLE draft_lottery_odds_new RENAME TO draft_lottery_odds;
                    CREATE INDEX IF NOT EXISTS idx_draft_lottery_year
                      ON draft_lottery_odds(draft_year);
                """)
        except sqlite3.OperationalError:
            pass
        # 2026-07-31 — Migration: widen draft_lottery_odds beyond the single
        # "% at #1" number. Tankathon's table already published a "Top 6"
        # column (lottery-entry odds) and a "Record" column next to it; the
        # scraper was throwing both away. Historical rows keep NULL, which is
        # the honest value: we never captured those numbers for those dates.
        #
        # MUST run AFTER the NOT NULL rebuild above - that block recreates the
        # table from the OLD column list, so adding these first would drop them.
        for _col, _ddl in (
            ("odds_top6_pct", "REAL"),
            ("wins",          "INTEGER"),
            ("losses",        "INTEGER"),
        ):
            try:
                con.execute(f"ALTER TABLE draft_lottery_odds ADD COLUMN {_col} {_ddl}")
            except sqlite3.OperationalError:
                pass  # column already exists
        # 2026-10-01 - Migration: source coverage on metric_snapshots (owner
        # answer B4SP-2). Nullable, no default and NEVER back-filled: rows
        # written before METRIC_SNAPSHOT_COVERAGE_START keep NULL, the honest
        # value, because the board's source list on those nights was not kept.
        for _col, _ddl in METRIC_SNAPSHOT_COVERAGE_COLUMNS:
            try:
                con.execute(f"ALTER TABLE metric_snapshots ADD COLUMN {_col} {_ddl}")
            except sqlite3.OperationalError:
                pass  # column already exists


def insert_snapshots(snapshots: Iterable[Snapshot]) -> int:
    # UPSERT — re-ingest of a (source, interval_label, player_key) tuple
    # overwrites the prior row's FV / rank / status / name. This is the
    # only way to correct stale snapshots (e.g. a wrong FV written by an
    # earlier buggy ingest path); the previous INSERT OR IGNORE silently
    # skipped re-runs and let bad data persist forever.
    #
    # position / org preserve the prior non-null value because some
    # sources don't republish them on every refresh; tools_json behaves
    # the same so a re-run with no tools doesn't wipe ones we already had.
    count = 0
    with connect() as con:
        for s in snapshots:
            tools_json = json.dumps(s.tools) if s.tools else None
            cur = con.execute(
                """INSERT INTO snapshots
                   (source, snapshot_date, interval_label, player_key,
                    player_name, position, org, rank, fv, status, tools_json, fv_plus)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source, interval_label, player_key) DO UPDATE SET
                       snapshot_date = excluded.snapshot_date,
                       player_name   = excluded.player_name,
                       position      = COALESCE(excluded.position, snapshots.position),
                       org           = COALESCE(excluded.org,      snapshots.org),
                       rank          = excluded.rank,
                       fv            = excluded.fv,
                       status        = excluded.status,
                       tools_json    = COALESCE(excluded.tools_json, snapshots.tools_json),
                       fv_plus       = excluded.fv_plus""",
                (s.source, s.snapshot_date, s.interval_label, s.player_key,
                 s.player_name, s.position, s.org, s.rank, s.fv, s.status,
                 tools_json, 1 if getattr(s, "fv_plus", False) else 0),
            )
            count += cur.rowcount
            con.execute(
                """INSERT INTO players (player_key, player_name, position, org,
                                       is_pitcher)
                   VALUES (?, ?, ?, ?, COALESCE(?, 0))
                   ON CONFLICT(player_key) DO UPDATE SET
                       player_name = excluded.player_name,
                       position    = COALESCE(excluded.position, players.position),
                       org         = COALESCE(excluded.org, players.org),
                       is_pitcher  = COALESCE(?, players.is_pitcher),
                       updated_at  = datetime('now')""",
                (s.player_key, s.player_name, s.position, s.org,
                 _is_pitcher_flag(s.position), _is_pitcher_flag(s.position)),
            )
    return count


def revalidate_auto_graduations(qualified_keys: set[str]) -> int:
    """Delete `auto_detect` 'debuted' snapshots for players who don't
    currently meet the rookie-eligibility rules.

    Earlier versions of the pipeline auto-graduated any prospect with an
    MLB debut date, regardless of whether they'd crossed the 130-AB /
    50-IP / options-exhausted threshold. Those over-eager rows persist
    in the DB across runs and `consensus.build_timeseries` reads them as
    canonical graduations — so a cup-of-coffee prospect from a prior run
    still shows as a graduate even after we tightened the rules.

    `qualified_keys` is the set of player_keys that DO meet the current
    rules (passed in by run_monthly from roster_status). Any auto_detect
    grad snapshot whose key is NOT in that set is removed. FanGraphs-
    sourced graduated snapshots are left alone — those are external
    authority.

    Returns the number of rows deleted.
    """
    with connect() as con:
        rows = con.execute(
            """SELECT player_key FROM snapshots
               WHERE source = 'auto_detect' AND status = 'debuted'"""
        ).fetchall()
        if not rows:
            return 0
        to_delete = [r["player_key"] for r in rows
                     if r["player_key"] not in qualified_keys]
        if not to_delete:
            return 0
        # Use executemany with a single-key clause so SQLite's parameter
        # list cap (~999) doesn't become a footgun when a lot of legacy
        # rows need to clear.
        con.executemany(
            """DELETE FROM snapshots
               WHERE source = 'auto_detect' AND status = 'debuted'
                 AND player_key = ?""",
            [(k,) for k in to_delete],
        )
        return len(to_delete)


def auto_debut_player(player_key: str, debut_date: str | None = None) -> None:
    """
    Mark a player as debuted by inserting a synthetic snapshot.

    debut_date — ISO date string for the MLB debut (mlbDebutDate from
                 the API). When not supplied, falls back to the player's
                 earliest MLB-level career-stats season as
                 {season}-04-01 (Opening Day, the closest signal to
                 "first MLB game" we can derive without a per-game
                 lookup). Today's date is NEVER used as the fallback —
                 that creates a flood of synthetic "debuted today"
                 entries every pipeline run for players whose actual
                 first MLB game was years ago.

    The pipeline uses the EARLIEST debut snapshot it finds, so a
    fallback grounded in the player's first MLB season prevents
    spurious "debuted on rebuild date" entries across runs.
    """
    snap_date = debut_date or _resolve_first_mlb_game_date(player_key)
    if not snap_date:
        # No debut date and no MLB career row to anchor to. Skip rather
        # than stamping today() — the caller can retry once data lands.
        return
    with connect() as con:
        # RE-FIRE GUARD (audit residue 2026-07-15): a player with ANY debuted
        # snapshot on file is already debuted — a later auto-detect pass must
        # not fire again (ryan_vilade: a veteran re-appearance re-fired
        # 2026-05-17 against a true 2021-09-18 debut; the snapshots UNIQUE
        # key excludes the date, so the first fire's date wins forever and a
        # re-fire with a different date is silently ignored — this makes the
        # suppression explicit). Deliberately NOT keyed on
        # roster_status.mlb_debut_date being set: the daily pipeline derives
        # roster status minutes before auto-detection fires in the same run,
        # which would suppress every legitimate first fire.
        if con.execute(
            "SELECT 1 FROM snapshots WHERE player_key = ? AND status = 'debuted' LIMIT 1",
            (player_key,),
        ).fetchone():
            return
        # DATE CLAMP: never stamp a debut later than the known true debut —
        # when roster_status already carries an earlier mlb_debut_date, the
        # detected date is a re-appearance artifact, not the debut.
        rs = con.execute(
            "SELECT payload_json FROM roster_status WHERE player_key = ? LIMIT 1",
            (player_key,),
        ).fetchone()
        if rs:
            try:
                rs_debut = (json.loads(rs["payload_json"]) or {}).get("mlb_debut_date")
            except (TypeError, ValueError):
                rs_debut = None
            if rs_debut and str(rs_debut) < snap_date:
                snap_date = str(rs_debut)
        # Pull most recent metadata for this player
        row = con.execute(
            """SELECT player_name, position, org FROM snapshots
               WHERE player_key = ?
               ORDER BY snapshot_date DESC LIMIT 1""",
            (player_key,),
        ).fetchone()
        if not row:
            return
        # Insert the debut snapshot; ignore if this exact row exists.
        # status='debuted' is kept as the internal enum (renaming it
        # would invalidate every cached DB row + force a schema migration);
        # the user-facing label is "Debuted" wherever this surfaces.
        con.execute(
            """INSERT OR IGNORE INTO snapshots
               (player_key, player_name, source, snapshot_date, interval_label,
                position, org, rank, fv, status)
               VALUES (?, ?, 'auto_detect', ?, 'Auto-detected MLB debut',
                       ?, ?, NULL, NULL, 'debuted')""",
            (player_key, row["player_name"], snap_date,
             row["position"], row["org"]),
        )


def _resolve_first_mlb_game_date(player_key: str) -> str | None:
    """Look up the player's earliest MLB season in career_stats and
    return `{season}-04-01` (Opening Day) as the best stand-in for
    "first MLB game date" when the API hasn't supplied an mlbDebutDate.
    Returns None when the player has no MLB-level career rows on file.
    """
    try:
        with connect() as con:
            row = con.execute(
                """SELECT payload_json FROM career_stats
                   WHERE player_key = ? LIMIT 1""",
                (player_key,),
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    try:
        rows = json.loads(row["payload_json"])
    except (TypeError, ValueError):
        return None
    mlb_seasons = [
        int(r["season"]) for r in rows
        if isinstance(r, dict) and r.get("level") == "MLB" and r.get("season")
    ]
    if not mlb_seasons:
        return None
    return f"{min(mlb_seasons)}-04-01"


# Back-compat alias — keeps old callers (and any external scripts)
# working. New code should use `auto_debut_player`. The keyword arg
# `grad_date` is also accepted for symmetry with the old signature.
def auto_graduate_player(player_key: str, grad_date: str | None = None) -> None:
    return auto_debut_player(player_key, debut_date=grad_date)


def upsert_unranked_active_player(
    player_key: str,
    player_name: str,
    position: str | None,
    org: str | None,
    birth_date: str | None,
    mlbam_id: int | None,
    *,
    source_label: str = "performance_ingest",
    provisional_fv: float = 35.0,
    season: int | None = None,
    as_of: str | None = None,
) -> bool:
    """Insert a player discovered via the MLB Stats API who has no FV snapshot.

    Creates both a `players` row (the master record) and a minimal
    `snapshots` row marked `source='performance_ingest'` so the consensus
    engine can anchor on it.  Prospects without any grading source now enter
    the DB once they accumulate qualifying PA/IP, rather than waiting for a
    publication cycle.

    Returns True if a new player row was created, False if already present.
    """
    # ANCHOR FIX (2026-07-25): the stamp date is the date the qualifying-
    # production claim was OBSERVED, not January 1 of the season. The old
    # `f"{season}-01-01"` froze every auto-tracked player's anchor at a date
    # that can never advance, and because (source, interval_label, player_key)
    # is the upsert key the same row was rewritten with the same date on every
    # run. Downstream that anchor feeds efv_dataset._stale_anchor_discount,
    # whose ramp starts at 18 months: a Jan-1 stamp begins decaying the whole
    # cohort's model anchor ~18 months later and reaches the full -10 FV
    # terminal at 30 months, purely as an artifact of the frozen date.
    # `as_of` lets a caller pin an explicit observation date; default = today.
    import datetime as _dt
    snap_date = as_of or _dt.date.today().isoformat()
    interval  = f"{season}_performance" if season else "performance"

    with connect() as con:
        # Check if player already exists
        existing = con.execute(
            "SELECT 1 FROM players WHERE player_key = ?", (player_key,)
        ).fetchone()

        # Create / update the master players record
        con.execute(
            """INSERT INTO players (player_key, player_name, position, org,
                                   is_pitcher)
               VALUES (?, ?, ?, ?, COALESCE(?, 0))
               ON CONFLICT(player_key) DO UPDATE SET
                 player_name = excluded.player_name,
                 position    = COALESCE(excluded.position, players.position),
                 org         = COALESCE(excluded.org,      players.org),
                 is_pitcher  = COALESCE(?, players.is_pitcher),
                 updated_at  = datetime('now')""",
            (player_key, player_name, position, org,
             _is_pitcher_flag(position), _is_pitcher_flag(position)),
        )

        # Anchor a lightweight snapshot so consensus has something to work with.
        # FV = provisional_fv (default 35 = "unranked but active").
        #
        # CORRECTION (2026-07-25): the previous comment here claimed this row
        # "never displaces a real FV from a scouting source because
        # source='performance_ingest' is excluded from the consensus weights".
        # That is NOT true. consensus.load_source_weights() reads
        # data/source_weights.json, whose weights object is {} (reverted to
        # equal on 2026-07-25), and sources absent from that file vote at 1.0 --
        # so this row votes exactly like FanGraphs. It does not DISPLACE a real
        # grade (it averages with one), but for a player no outlet has ever
        # graded it IS the consensus: measured 2026-07-25, 2,575 of the 4,477
        # active board players serve consensus_fv == 35.0 sourced from nothing
        # but this constant, and 2,214 of them sit pinned at the served eFV
        # floor. The single-instance shrinkage does not help: it pulls toward
        # SINGLE_SOURCE_PRIOR = 35, which is a no-op on 35.
        # See docs/identity-2026-08-04/PATCH_consensus_synthetic_anchor.md for the
        # consensus-side patch (that file is owned by another lane).
        con.execute(
            """INSERT INTO snapshots
               (source, snapshot_date, interval_label, player_key,
                player_name, position, org, rank, fv, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, 'active')
               ON CONFLICT(source, interval_label, player_key) DO UPDATE SET
                 snapshot_date = excluded.snapshot_date,
                 player_name   = excluded.player_name,
                 position      = COALESCE(excluded.position, snapshots.position),
                 org           = COALESCE(excluded.org, snapshots.org)""",
            (source_label, snap_date, interval,
             player_key, player_name, position, org, provisional_fv),
        )

        # Store birth_date if available
        if birth_date:
            con.execute(
                """UPDATE players SET birth_date = ?
                   WHERE player_key = ? AND birth_date IS NULL""",
                (birth_date, player_key),
            )
        # Register MLBAM ID in player_photos so the pipeline resolves this player
        # on subsequent runs (headshots, statcast, transactions).
        if mlbam_id:
            con.execute(
                """INSERT INTO player_photos (mlbam_id, headshot_ctx, player_key)
                   VALUES (?, 'milb', ?)
                   ON CONFLICT(mlbam_id) DO UPDATE SET
                     player_key = COALESCE(excluded.player_key, player_photos.player_key)""",
                (mlbam_id, player_key),
            )

    return existing is None   # True = newly created


def upsert_birth_date(player_key: str, birth_date: str,
                      overwrite: bool = False) -> None:
    """
    Set a player's birth_date.

    By default this is idempotent (only writes when currently NULL) so a
    one-time fetch wins and we never re-fetch unnecessarily. Pass
    overwrite=True when the caller has authoritative new data (e.g. the
    PlayerIndex just resolved a different MLBAM ID, making any existing
    birth date potentially stale).
    """
    if not birth_date:
        return
    with connect() as con:
        if overwrite:
            con.execute(
                """UPDATE players SET birth_date = ?, updated_at = datetime('now')
                   WHERE player_key = ?""",
                (birth_date, player_key),
            )
        else:
            con.execute(
                """UPDATE players SET birth_date = ?, updated_at = datetime('now')
                   WHERE player_key = ? AND (birth_date IS NULL OR birth_date = '')""",
                (birth_date, player_key),
            )


_BIRTH_DATE_UPDATE_OVERWRITE = (
    "UPDATE players SET birth_date = ?, updated_at = datetime('now') "
    "WHERE player_key = ?")
_BIRTH_DATE_UPDATE_FILL = (
    "UPDATE players SET birth_date = ?, updated_at = datetime('now') "
    "WHERE player_key = ? AND (birth_date IS NULL OR birth_date = '')")


def upsert_birth_dates(pairs, overwrite: bool = False) -> int:
    """
    Batched upsert_birth_date: the same UPDATE (same WHERE, same overwrite
    semantics, same updated_at stamp) for every (player_key, birth_date)
    pair, run through executemany on ONE connection and ONE commit.

    `pairs` is a {player_key: birth_date} mapping or an iterable of
    (player_key, birth_date) tuples. Pairs with an empty birth_date are
    skipped, exactly as upsert_birth_date returns early on them. Returns the
    number of player rows the UPDATE touched.

    Why: the monthly resolve step (run_monthly 2a) upserted ~6,600 dates by
    calling upsert_birth_date per row, and each call opened a connection, ran
    the five connect() pragmas and committed, which cost about 55 s of the
    step's 101 s. One connection carries the same rows in under a second.
    upsert_birth_date stays for single-row callers.
    """
    items = pairs.items() if isinstance(pairs, dict) else pairs
    params = [(bd, key) for key, bd in items if bd]
    if not params:
        return 0
    sql = _BIRTH_DATE_UPDATE_OVERWRITE if overwrite else _BIRTH_DATE_UPDATE_FILL
    with connect() as con:
        cur = con.executemany(sql, params)
        return int(cur.rowcount or 0)


def load_birth_dates() -> dict[str, str]:
    """Return {player_key: 'YYYY-MM-DD'} for every player whose DOB we know."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, birth_date FROM players WHERE birth_date IS NOT NULL"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: r["birth_date"] for r in rows}


def upsert_statlines(statlines: dict[str, StatLine], season: int) -> int:
    n = 0
    with connect() as con:
        for key, sl in statlines.items():
            con.execute(
                """INSERT INTO statlines (player_key, season, payload_json, fetched_at)
                   VALUES (?, ?, ?, datetime('now'))
                   ON CONFLICT(player_key) DO UPDATE SET
                       season       = excluded.season,
                       payload_json = excluded.payload_json,
                       fetched_at   = excluded.fetched_at""",
                (key, season, json.dumps(asdict(sl))),
            )
            n += 1
    return n


def insert_trades(trades) -> int:
    """Append-only insert; the UNIQUE constraint dedupes re-runs.

    An inferred move is idempotent on (player_key, from_org, to_org,
    date_range_start) as well (census M02-05): a player whose newest snapshot is the
    rolling performance_ingest row re-fires the same move with a new trade_date on
    every run, which UNIQUE(player_key, trade_date, source) never collapsed (45 rows
    for one move). Rows already on file are left alone; readers de-duplicate."""
    from trades import Trade
    n = 0
    with connect() as con:
        for t in trades:
            if t.source == "inferred" and con.execute(
                    """SELECT 1 FROM trades WHERE source = 'inferred' AND player_key = ?
                       AND from_org IS ? AND to_org IS ? AND date_range_start IS ?
                       LIMIT 1""",
                    (t.player_key, t.from_org, t.to_org, t.date_range_start)).fetchone():
                continue
            cur = con.execute(
                """INSERT OR IGNORE INTO trades
                   (player_key, trade_date, from_org, to_org, source,
                    description, date_range_start, date_range_end)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (t.player_key, t.trade_date, t.from_org, t.to_org,
                 t.source, t.description, t.date_range_start, t.date_range_end),
            )
            n += cur.rowcount
    return n


def load_trades() -> dict[str, list[dict]]:
    """{player_key: [trade_dict, ...]} sorted by trade_date asc."""
    by_player: dict[str, list[dict]] = {}
    with connect() as con:
        rows = con.execute(
            """SELECT player_key, trade_date, from_org, to_org, source,
                      description, date_range_start, date_range_end
               FROM trades ORDER BY player_key, trade_date"""
        ).fetchall()
    for r in rows:
        d = dict(r)
        by_player.setdefault(d["player_key"], []).append(d)
    return by_player


def load_all_snapshots() -> list[Snapshot]:
    with connect() as con:
        rows = con.execute(
            """SELECT source, snapshot_date, interval_label, player_key,
                      player_name, position, org, rank, fv, status, tools_json,
                      fv_plus
               FROM snapshots ORDER BY snapshot_date, source"""
        ).fetchall()
    snapshots: list[Snapshot] = []
    for r in rows:
        d = dict(r)
        d["player_key"] = canonical_player_key(d["player_key"])
        # Same idea as the player_key canonicalization above, one field over.
        # FanGraphs ships draft-eligibility markers inside the Name column
        # ("Derek Curiel*" = sophomore, "**Noah Song" = senior) and the CSV
        # paths only run fix_mojibake, which does not know about them. Doing
        # it HERE rather than at ingest fixes every downstream surface at once
        # (board, timeseries, exports) with no re-ingest, and stays fixed when
        # the next FanGraphs drop re-mints a dirty row.
        if d.get("player_name"):
            d["player_name"] = strip_name_markers(d["player_name"])
        d["fv_plus"] = bool(d.pop("fv_plus", 0) or 0)
        tools_json = d.pop("tools_json", None)
        tools = None
        if tools_json:
            try:
                parsed = json.loads(tools_json)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, dict) and parsed:
                tools = {}
                for k, v in parsed.items():
                    if v is None:
                        continue
                    # `_extras` is a nested dict of source-specific
                    # non-grade metadata (FG ships height, weight, sits,
                    # tops, fb_type, tj_date, frame, athl, perf, levers,
                    # arm, delivery, contact_style, hard_hit_pct, etc.).
                    # Pass it through verbatim so per_source.tools._extras
                    # reaches the UI.
                    if k == "_extras" and isinstance(v, dict):
                        tools["_extras"] = v
                        continue
                    try:
                        tools[k] = float(v)
                    except (TypeError, ValueError):
                        continue
                # Backwards-compat lift: pitch_sel and bat_ctrl were
                # historically stored under _extras; they are now
                # canonical hitter tools. Pull them up so legacy DB rows
                # don't need a re-ingest to participate in consensus
                # aggregation and composite_off / Tool composites.
                extras = tools.get("_extras") if isinstance(tools.get("_extras"), dict) else None
                if extras:
                    for lifted_key in ("pitch_sel", "bat_ctrl"):
                        if lifted_key in tools:
                            continue
                        raw = extras.get(lifted_key)
                        if raw is None:
                            continue
                        try:
                            f = float(raw)
                        except (TypeError, ValueError):
                            continue
                        if 20 <= f <= 80:
                            tools[lifted_key] = f
                if not tools:
                    tools = None
        d["tools"] = tools
        snapshots.append(Snapshot(**d))
    return snapshots


def load_statlines() -> dict[str, dict]:
    with connect() as con:
        rows = con.execute("SELECT player_key, payload_json FROM statlines").fetchall()
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


def upsert_pitch_arsenals(arsenals: dict[str, "PitchArsenal"], season: int) -> int:
    """Upsert pitch arsenal data. One row per player (most recent season wins)."""
    n = 0
    with connect() as con:
        for key, pa in arsenals.items():
            con.execute(
                """INSERT INTO pitch_arsenals (player_key, season, payload_json, fetched_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(player_key) DO UPDATE SET
                     season=excluded.season,
                     payload_json=excluded.payload_json,
                     fetched_at=excluded.fetched_at""",
                (key, season, json.dumps(asdict(pa)), pa.fetched_at),
            )
            n += 1
    return n


def load_pitch_arsenals() -> dict[str, dict]:
    """Return {player_key: arsenal_dict} for all stored arsenals."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, payload_json FROM pitch_arsenals"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


def upsert_zone_metrics(metrics: dict[str, object], season: int) -> int:
    """Upsert approximate zone-discipline metrics. One row per hitter."""
    n = 0
    with connect() as con:
        for key, metric in metrics.items():
            payload = asdict(metric) if hasattr(metric, "__dataclass_fields__") else dict(metric)
            fetched_at = payload.get("fetched_at") or _utcnow_iso()
            con.execute(
                """INSERT INTO zone_metrics (player_key, season, payload_json, fetched_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(player_key) DO UPDATE SET
                     season=excluded.season,
                     payload_json=excluded.payload_json,
                     fetched_at=excluded.fetched_at""",
                (key, season, json.dumps(payload), fetched_at),
            )
            n += 1
    return n


def load_zone_metrics() -> dict[str, dict]:
    """Return {player_key: zone_metric_dict} for all stored zone metrics."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, payload_json FROM zone_metrics"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


def load_zone_metrics_meta() -> dict[str, str]:
    """Return {player_key: fetched_at_iso} for zone metric freshness checks.
    Mirrors load_career_stats_meta — caller skips per-player refetch when
    the cached row is recent enough."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, fetched_at FROM zone_metrics"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: r["fetched_at"] for r in rows if r["fetched_at"]}


def upsert_statcast_metrics(metrics: dict[str, object], season: int) -> int:
    """Upsert opportunistic pitch-movement/contact-quality metrics."""
    n = 0
    with connect() as con:
        for key, metric in metrics.items():
            payload = asdict(metric) if hasattr(metric, "__dataclass_fields__") else dict(metric)
            fetched_at = payload.get("fetched_at") or _utcnow_iso()
            con.execute(
                """INSERT INTO statcast_metrics (player_key, season, payload_json, fetched_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(player_key) DO UPDATE SET
                     season=excluded.season,
                     payload_json=excluded.payload_json,
                     fetched_at=excluded.fetched_at""",
                (key, season, json.dumps(payload), fetched_at),
            )
            n += 1
    return n


def load_statcast_metrics() -> dict[str, dict]:
    """Return {player_key: statcast_metric_dict} for stored metric rows."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, payload_json FROM statcast_metrics"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


def load_statcast_metrics_meta() -> dict[str, str]:
    """Return {player_key: fetched_at_iso} for statcast metric freshness."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, fetched_at FROM statcast_metrics"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: r["fetched_at"] for r in rows if r["fetched_at"]}


def upsert_source_events(events: list[dict]) -> int:
    """Upsert manually/article-derived source events.

    Events are non-consensus annotations: BA movement, article statcast
    callouts, injury notes, and similar fast-moving signals.
    """
    if not events:
        return 0
    n = 0
    with connect() as con:
        for event in events:
            payload = event.get("payload") or event.get("payload_json") or {}
            if isinstance(payload, str):
                payload_json = payload
            else:
                payload_json = json.dumps(payload)
            con.execute(
                """INSERT INTO source_events
                   (event_key, player_key, player_name, source, event_date, event_type,
                    rank_before, rank_after, confidence, payload_json, excerpt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(event_key) DO UPDATE SET
                     player_key=excluded.player_key,
                     player_name=excluded.player_name,
                     source=excluded.source,
                     event_date=excluded.event_date,
                     event_type=excluded.event_type,
                     rank_before=excluded.rank_before,
                     rank_after=excluded.rank_after,
                     confidence=excluded.confidence,
                     payload_json=excluded.payload_json,
                     excerpt=excluded.excerpt""",
                (
                    event["event_key"],
                    event["player_key"],
                    event.get("player_name") or event["player_key"],
                    event.get("source") or "manual",
                    event.get("event_date") or date.today().isoformat(),
                    event.get("event_type") or "note",
                    event.get("rank_before"),
                    event.get("rank_after"),
                    float(event.get("confidence") if event.get("confidence") is not None else 0.5),
                    payload_json,
                    event.get("excerpt") or "",
                ),
            )
            n += 1
    return n


def load_source_events() -> dict[str, list[dict]]:
    """Return article/list source events grouped by player_key."""
    try:
        with connect() as con:
            rows = con.execute(
                """SELECT event_key, player_key, player_name, source, event_date,
                          event_type, rank_before, rank_after, confidence,
                          payload_json, excerpt
                   FROM source_events
                   ORDER BY event_date DESC, source, event_type"""
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    out: dict[str, list[dict]] = {}
    for r in rows:
        try:
            payload = json.loads(r["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        event = {
            "event_key": r["event_key"],
            "player_key": r["player_key"],
            "player_name": r["player_name"],
            "source": r["source"],
            "event_date": r["event_date"],
            "event_type": r["event_type"],
            "rank_before": r["rank_before"],
            "rank_after": r["rank_after"],
            "confidence": r["confidence"],
            "payload": payload,
            "excerpt": r["excerpt"],
        }
        out.setdefault(r["player_key"], []).append(event)
    return out


def load_player_news() -> dict[str, list[dict]]:
    """Return optional static news sidecar rows grouped by player_key."""
    path = Path(__file__).parent / "data" / "player_news.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[dict]] = {}
    for key, rows in raw.items():
        if not isinstance(rows, list):
            continue
        clean = [r for r in rows if isinstance(r, dict)]
        clean.sort(key=lambda r: str(r.get("published_at") or r.get("date") or ""), reverse=True)
        out[str(key)] = clean[:8]
    return out


def upsert_sabermetrics(metrics: dict[str, "Sabermetrics"], season: int) -> int:
    """Upsert sabermetrics (wRC+, xFIP, wOBA, FIP, ...). One row per player."""
    n = 0
    with connect() as con:
        for key, sm in metrics.items():
            con.execute(
                """INSERT INTO sabermetrics (player_key, season, payload_json, fetched_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(player_key) DO UPDATE SET
                     season=excluded.season,
                     payload_json=excluded.payload_json,
                     fetched_at=excluded.fetched_at""",
                (key, season, json.dumps(asdict(sm)), sm.fetched_at),
            )
            n += 1
    return n


def load_sabermetrics() -> dict[str, dict]:
    """Return {player_key: metrics_dict} for all stored sabermetrics."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, payload_json FROM sabermetrics"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


def upsert_career_stats(career_by_player: dict[str, list[dict]]) -> int:
    """Upsert year-by-year career stats. One row per player."""
    # v19 — executemany() with a pre-materialized payload list. Saves
    # the per-row Python/C round-trip; ~3000 players collapses from 3000
    # discrete .execute() calls to a single C-level batch insert.
    payload = [
        (key, json.dumps(rows))
        for key, rows in career_by_player.items()
        if rows
    ]
    if not payload:
        return 0
    with connect() as con:
        con.executemany(
            """INSERT INTO career_stats (player_key, payload_json, fetched_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(player_key) DO UPDATE SET
                 payload_json=excluded.payload_json,
                 fetched_at=excluded.fetched_at""",
            payload,
        )
    return len(payload)


def load_career_stats() -> dict[str, list[dict]]:
    """Return {player_key: [season_rows]} for every stored career history."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, payload_json FROM career_stats"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


def _career_pa_id_candidates(keys) -> dict[str, list[int]]:
    """{player_key: [mlbam ids]} for the measured-PA backfill, in the order the
    export binds a row to its id: the statline's mlbam_id, then the durable
    player_photos binding (a key bound to two ids is left out, as the export
    does), then the resolver's id cache, read raw so its TTL never clears it
    here. The backfill's AB match is the identity check on top of this."""
    keys = set(keys)
    cands: dict[str, list[int]] = {k: [] for k in keys}

    def _add(k, mid):
        if k not in cands or mid in (None, ""):
            return
        try:
            mid = int(mid)
        except (TypeError, ValueError):
            return
        if mid not in cands[k]:
            cands[k].append(mid)

    try:
        for k, sl in load_statlines().items():
            _add(k, (sl or {}).get("mlbam_id"))
    except sqlite3.OperationalError:
        pass
    durable: dict[str, int] = {}
    multi: set[str] = set()
    for mid_s, pk in load_mlbam_player_keys().items():
        try:
            mid = int(mid_s)
        except (TypeError, ValueError):
            continue
        if pk in durable and durable[pk] != mid:
            multi.add(pk)
        durable[pk] = mid
    for pk, mid in durable.items():
        if pk not in multi:
            _add(pk, mid)
    try:
        from stats import ID_CACHE_FILE
        raw = json.loads(ID_CACHE_FILE.read_text(encoding="utf-8")) if ID_CACHE_FILE.exists() else {}
    except (OSError, ValueError):
        raw = {}
    for k, mid in (raw or {}).items():
        _add(k, mid)
    return cands


def backfill_career_pa_measured(cache_dir: Path | None = None) -> dict:
    """Idempotent migration of the stored career_stats rows (owner answer M7M8-2
    (c), 2026-10-01): write measured plate appearances (stats.MEASURED_PA_FIELD)
    onto every stored MLB hitter row the cached StatsAPI season lines can match
    (same id, same season, same AB). A row keeps no measured PA where nothing
    matches, so its readers keep the AB x 1.1 estimate. Rewrites payload_json
    only: fetched_at drives the monthly freshness skip and must not move. Forward
    only and safe to run every night; a second run changes nothing."""
    from stats import fill_measured_pa, load_statsapi_hitting_pa
    career = load_career_stats()
    lines = load_statsapi_hitting_pa(cache_dir)
    res = fill_measured_pa(career, _career_pa_id_candidates(career.keys()), lines)
    changed = res["changed"]
    if changed:
        with connect() as con:
            con.executemany(
                "UPDATE career_stats SET payload_json = ? WHERE player_key = ?",
                [(json.dumps(rows), key) for key, rows in changed.items()],
            )
    counts = dict(res["counts"])
    counts["players_updated"] = len(changed)
    counts["cached_seasons"] = sorted(lines)
    return counts


def upsert_career_war(by_key: dict[str, dict]) -> int:
    """Upsert one career-WAR aggregate per graduate. Skips empty payloads.

    Payload shape (the war_source.career_war_bulk / stats.fetch_career_war_bulk
    contract; "fangraphs" was never a real source here, the feed has been
    Baseball-Reference war_daily since FG 403'd pybaseball):
      {"seasons": {"2023": 1.5, "2024": 2.8, ...},   # the SERVED series
       "career_war": 4.3,                             # sum(seasons)
       "war_per_yr": 2.15,                            # career_war / n
       "war_seasons_count": 2,
       "source": "bbref" | "ewar_v2" | "fwar",
       # fWAR label epoch (E3): an fwar row keeps the incumbent beside it,
       # "seasons_ewar_v2": {...}, plus its "fwar_coverage" receipt
       # eWAR epoch (2026-09-03) only, written by the ewar_v2 provider and by
       # tools/rebase_career_war_to_ewar.py:
       "seasons_bwar": {"2023": 1.4, "2024": 2.9, ...},   # the bWAR frame
       "ewar_coverage": {...},                             # transform receipt
       # measured MLB exposure on the same stints (2026-09-11, decision 14c):
       "seasons_pa": {"2023": 512, ...}, "seasons_ip": {"2023": 0.0, ...}}
    `seasons` is the series every reader prices off (labels, WAG, anchors,
    surplus). `seasons_bwar` is the input frame kept beside it so the transform
    can be re-derived (rebase idempotency) and audited. For position players
    the two are equal season by season until the SDR defense drop lands; for
    pitchers eWAR re-prices runs on FIP within role (ewar.py).

    MERGE RULES. `seasons` unions old-then-new (new wins per year), and so do
    `seasons_bwar`, `seasons_ewar_v2`, `seasons_pa` and `seasons_ip` when either side carries
    them; the aggregates are recomputed over the merged `seasons`. A legacy
    payload (none of those) merges as it always did and drops nothing: an old
    map on file survives the merge untouched (so a rebase, which writes no
    exposure, keeps the exposure a fetch stored). `source` and `ewar_coverage`
    come from the NEW payload, never from the stored row.
    """
    n = 0
    with connect() as con:
        stored = {r["player_key"]: r["payload_json"] for r in con.execute(
            "SELECT player_key, payload_json FROM career_war")}
        for key, rec in by_key.items():
            if not rec:
                continue
            # AUDIT FIX 2026-07-14: MERGE seasons instead of replacing the
            # payload. A refetch with a narrower year window used to DELETE
            # early-career seasons (the sliding start_year=season-10 bug),
            # progressively decaying the eFV outcome labels. Seasons already
            # on file that the new fetch does not cover are preserved; the
            # aggregates are recomputed over the union.
            try:
                old = json.loads(stored.get(key) or "{}") or {}
                old_seasons = old.get("seasons") or {}
                old_bwar = old.get("seasons_bwar") or {}
            except ValueError:
                old = {}
                old_seasons = {}
                old_bwar = {}
            # the payload's own served series, before the union below rewrites it
            _payload_seasons = dict(rec.get("seasons") or {})
            if old_seasons:
                merged = dict(old_seasons)
                merged.update(rec.get("seasons") or {})
                if merged != (rec.get("seasons") or {}):
                    rec = dict(rec)
                    rec["seasons"] = merged
                    vals = [float(v) for v in merged.values()]
                    rec["career_war"] = round(sum(vals), 2)
                    rec["war_seasons_count"] = len(vals)
                    rec["war_per_yr"] = round(sum(vals) / len(vals), 3) if vals else 0.0
            # eWAR epoch: the bWAR frame merges by the same union rule, so a
            # narrow-window refetch cannot delete an early-career bWAR season
            # any more than it can delete the served one. A legacy payload
            # (no seasons_bwar) on a row that already carries a frame: its
            # `seasons` ARE bWAR (source bbref), so they refresh the frame
            # too, and tools/rebase_career_war_to_ewar.py --reapply can
            # re-derive the served series from it. A legacy payload on a
            # legacy row touches nothing here (byte-identical to the
            # pre-epoch behaviour).
            new_bwar = rec.get("seasons_bwar") or {}
            if not new_bwar and old_bwar and rec.get("source") == "bbref":
                new_bwar = rec.get("seasons") or {}
            if old_bwar or new_bwar:
                merged_bwar = dict(old_bwar)
                merged_bwar.update(new_bwar)
                if merged_bwar != (rec.get("seasons_bwar") or {}):
                    rec = dict(rec)
                    rec["seasons_bwar"] = merged_bwar
            # fWAR label epoch (E3): the incumbent eWAR v2 series an fwar row keeps
            # (gate part 4.1 note 2) merges by the same union rule, so a narrow
            # refetch cannot delete it. A payload from the incumbent's provider
            # ('ewar_v2', or 'bbref' on a row it never rebased) carries no map of
            # its own: its seasons ARE the incumbent, so on a row that already
            # keeps one they refresh it, exactly as a bbref payload refreshes
            # seasons_bwar. A row and a payload with no map: nothing changes.
            _old_inc = old.get("seasons_ewar_v2") if isinstance(old.get("seasons_ewar_v2"), dict) else {}
            _new_inc = rec.get("seasons_ewar_v2") or {}
            if not _new_inc and _old_inc and rec.get("source") in ("ewar_v2", "bbref"):
                _new_inc = _payload_seasons
            if _old_inc or _new_inc:
                _merged_inc = dict(_old_inc)
                _merged_inc.update(_new_inc)
                if _merged_inc != (rec.get("seasons_ewar_v2") or {}):
                    rec = dict(rec)
                    rec["seasons_ewar_v2"] = _merged_inc
            # Measured exposure (decision 14c) merges by the same union rule, so a
            # narrow-window refetch or a rebase keeps the exposure of the seasons it
            # did not touch. A payload and a row with neither map: nothing changes.
            for _xf in ("seasons_pa", "seasons_ip"):
                _old_x = old.get(_xf) if isinstance(old.get(_xf), dict) else {}
                _new_x = rec.get(_xf) or {}
                if _old_x or _new_x:
                    _merged_x = dict(_old_x)
                    _merged_x.update(_new_x)
                    if _merged_x != _new_x:
                        rec = dict(rec)
                        rec[_xf] = _merged_x
            con.execute(
                """INSERT INTO career_war (player_key, payload_json, fetched_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(player_key) DO UPDATE SET
                     payload_json=excluded.payload_json,
                     fetched_at=excluded.fetched_at""",
                (key, json.dumps(rec)),
            )
            n += 1
    return n


def load_career_war() -> dict[str, dict]:
    """Return {player_key: war_aggregate_dict} for every cached graduate."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, payload_json FROM career_war"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


def load_career_war_meta() -> dict[str, str]:
    """Return {player_key: fetched_at_iso} so the pipeline can decide
    whether the cached WAR aggregate is fresh enough to skip refetching."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, fetched_at FROM career_war"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: r["fetched_at"] for r in rows}


def upsert_acquisitions(by_key: dict[str, dict]) -> int:
    """Upsert acquisition rows. Each dict carries:
      method, year, round_label, pick_round, pick_overall, bonus_usd,
      team_name, school, signing_date (all optional except method).

    overwrite is the default — IFA inference + draft fetches both produce
    authoritative records that should replace any prior guess."""
    n = 0
    with connect() as con:
        for key, rec in by_key.items():
            con.execute(
                """INSERT INTO acquisitions
                     (player_key, method, year, round_label, pick_round,
                      pick_overall, bonus_usd, team_name, school, signing_date,
                      fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(player_key) DO UPDATE SET
                     method=excluded.method,
                     year=excluded.year,
                     round_label=excluded.round_label,
                     pick_round=excluded.pick_round,
                     pick_overall=excluded.pick_overall,
                     bonus_usd=excluded.bonus_usd,
                     team_name=excluded.team_name,
                     school=excluded.school,
                     signing_date=excluded.signing_date,
                     fetched_at=excluded.fetched_at""",
                (key, rec.get("method"), rec.get("year"),
                 rec.get("round_label"), rec.get("pick_round"),
                 rec.get("pick_overall"), rec.get("bonus_usd"),
                 rec.get("team_name"), rec.get("school"),
                 rec.get("signing_date")),
            )
            n += 1
    return n


def load_acquisitions() -> dict[str, dict]:
    """Return {player_key: acquisition_dict} for every prospect with one."""
    try:
        with connect() as con:
            rows = con.execute(
                """SELECT player_key, method, year, round_label, pick_round,
                          pick_overall, bonus_usd, team_name, school, signing_date
                   FROM acquisitions"""
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: dict(r) for r in rows}


# ===========================================================================
# Draft prospects (amateurs) — parallel track to snapshots/players
# ===========================================================================

def insert_draft_snapshots(snapshots: Iterable) -> int:
    """Upsert draft prospect snapshots. Accepts any iterable of objects
    with the standard Snapshot field set plus draft-specific extras
    (school, college_commit, player_type, draft_year). Either a
    `DraftSnapshot` dataclass instance or a plain dict works."""
    count = 0
    with connect() as con:
        for s in snapshots:
            if hasattr(s, "__dict__"):
                d = s.__dict__
            elif hasattr(s, "_asdict"):
                d = s._asdict()
            else:
                d = dict(s)
            tools = d.get("tools")
            tools_json = json.dumps(tools) if tools else None
            cur = con.execute(
                """INSERT INTO draft_snapshots
                     (source, snapshot_date, interval_label, player_key,
                      player_name, position, school, college_commit, player_type,
                      draft_year, rank, fv, risk, status, tools_json, fv_plus)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source, interval_label, player_key) DO UPDATE SET
                       snapshot_date  = excluded.snapshot_date,
                       player_name    = excluded.player_name,
                       position       = COALESCE(excluded.position, draft_snapshots.position),
                       school         = COALESCE(excluded.school, draft_snapshots.school),
                       college_commit = COALESCE(excluded.college_commit, draft_snapshots.college_commit),
                       player_type    = COALESCE(excluded.player_type, draft_snapshots.player_type),
                       draft_year     = excluded.draft_year,
                       rank           = excluded.rank,
                       fv             = excluded.fv,
                       risk           = COALESCE(excluded.risk, draft_snapshots.risk),
                       status         = excluded.status,
                       tools_json     = COALESCE(excluded.tools_json, draft_snapshots.tools_json),
                       fv_plus        = excluded.fv_plus""",
                (d.get("source"), d.get("snapshot_date"), d.get("interval_label"),
                 d.get("player_key"), d.get("player_name"), d.get("position"),
                 d.get("school"), d.get("college_commit"), d.get("player_type"),
                 d.get("draft_year"), d.get("rank"), d.get("fv"),
                 d.get("risk"), d.get("status", "draft_active"), tools_json,
                 1 if d.get("fv_plus") else 0),
            )
            count += cur.rowcount
            con.execute(
                """INSERT INTO draft_players
                     (player_key, player_name, position, school, college_commit,
                      player_type, draft_year, birth_date, bats, throws,
                      height, weight, fg_player_id, mlbam_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(player_key) DO UPDATE SET
                       player_name    = excluded.player_name,
                       position       = COALESCE(excluded.position, draft_players.position),
                       school         = COALESCE(excluded.school, draft_players.school),
                       college_commit = COALESCE(excluded.college_commit, draft_players.college_commit),
                       player_type    = COALESCE(excluded.player_type, draft_players.player_type),
                       draft_year     = excluded.draft_year,
                       birth_date     = COALESCE(excluded.birth_date, draft_players.birth_date),
                       bats           = COALESCE(excluded.bats, draft_players.bats),
                       throws         = COALESCE(excluded.throws, draft_players.throws),
                       height         = COALESCE(excluded.height, draft_players.height),
                       weight         = COALESCE(excluded.weight, draft_players.weight),
                       fg_player_id   = COALESCE(excluded.fg_player_id, draft_players.fg_player_id),
                       mlbam_id       = COALESCE(excluded.mlbam_id, draft_players.mlbam_id),
                       updated_at     = datetime('now')""",
                (d.get("player_key"), d.get("player_name"), d.get("position"),
                 d.get("school"), d.get("college_commit"), d.get("player_type"),
                 d.get("draft_year"), d.get("birth_date"),
                 d.get("bats"), d.get("throws"),
                 d.get("height"), d.get("weight"),
                 d.get("fg_player_id"), d.get("mlbam_id")),
            )
    return count


def load_draft_snapshots(draft_year: int | None = None) -> list[dict]:
    """Return draft_snapshots rows. Filter by draft_year if given."""
    q = """SELECT id, source, snapshot_date, interval_label, player_key,
                  player_name, position, school, college_commit, player_type,
                  draft_year, rank, fv, risk, status, tools_json, fv_plus,
                  inserted_at
           FROM draft_snapshots"""
    params: tuple = ()
    if draft_year is not None:
        q += " WHERE draft_year = ?"
        params = (draft_year,)
    q += " ORDER BY draft_year DESC, snapshot_date DESC, rank ASC"
    try:
        with connect() as con:
            rows = con.execute(q, params).fetchall()
    except sqlite3.OperationalError:
        return []
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        # draft_timeseries.json is built off THIS loader, not
        # load_all_snapshots, so it needs its own copy of the
        # asterisk-marker strip. The draft board is where the markers are
        # densest: the FanGraphs draft CSV writes a leading "**" for a
        # senior and a trailing "*" for a draft-eligible sophomore, and 47
        # distinct names in draft_snapshots carried one (2018-2020 classes).
        if d.get("player_name"):
            d["player_name"] = strip_name_markers(d["player_name"])
        if d.get("tools_json"):
            try:
                d["tools"] = json.loads(d["tools_json"])
            except (ValueError, TypeError):
                d["tools"] = None
        else:
            d["tools"] = None
        out.append(d)
    return out


def load_draft_players(draft_year: int | None = None) -> dict[str, dict]:
    """Return {player_key: draft_player_dict} for the named draft year
    (or every year when draft_year is None)."""
    q = """SELECT player_key, player_name, position, school, college_commit,
                  player_type, draft_year, birth_date, bats, throws,
                  height, weight, fg_player_id, mlbam_id, promoted_key
           FROM draft_players"""
    params: tuple = ()
    if draft_year is not None:
        q += " WHERE draft_year = ?"
        params = (draft_year,)
    try:
        with connect() as con:
            rows = con.execute(q, params).fetchall()
    except sqlite3.OperationalError:
        return {}
    out: dict[str, dict] = {}
    for r in rows:
        d = dict(r)
        # Identity table for the draft board. Same marker strip as the
        # snapshot loader above: several draft pages fall back to this
        # row's player_name when a class has no snapshot for the player.
        if d.get("player_name"):
            d["player_name"] = strip_name_markers(d["player_name"])
        out[d["player_key"]] = d
    return out


def upsert_draft_results(rows: Iterable[dict]) -> int:
    """Upsert post-draft pick rows. Each dict carries:
      draft_year, pick_overall, round_label, pick_in_round, team,
      player_key (optional), player_name, school, slot_usd, bonus_usd,
      signed, source.
    UNIQUE on (draft_year, pick_overall) — re-runs overwrite."""
    n = 0
    with connect() as con:
        for r in rows:
            con.execute(
                """INSERT INTO draft_results
                     (draft_year, pick_overall, round_label, pick_in_round,
                      team, player_key, player_name, school,
                      slot_usd, bonus_usd, signed, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(draft_year, pick_overall) DO UPDATE SET
                     round_label   = COALESCE(excluded.round_label, draft_results.round_label),
                     pick_in_round = COALESCE(excluded.pick_in_round, draft_results.pick_in_round),
                     team          = excluded.team,
                     player_key    = COALESCE(excluded.player_key, draft_results.player_key),
                     player_name   = excluded.player_name,
                     school        = COALESCE(excluded.school, draft_results.school),
                     slot_usd      = COALESCE(excluded.slot_usd, draft_results.slot_usd),
                     bonus_usd     = COALESCE(excluded.bonus_usd, draft_results.bonus_usd),
                     signed        = excluded.signed,
                     source        = excluded.source,
                     inserted_at   = datetime('now')""",
                (r.get("draft_year"), r.get("pick_overall"),
                 r.get("round_label"), r.get("pick_in_round"),
                 r.get("team"), r.get("player_key"),
                 r.get("player_name"), r.get("school"),
                 r.get("slot_usd"), r.get("bonus_usd"),
                 1 if r.get("signed") else 0, r.get("source")),
            )
            n += 1
    return n


def load_draft_results(draft_year: int | None = None) -> list[dict]:
    q = """SELECT draft_year, pick_overall, round_label, pick_in_round,
                  team, player_key, player_name, school,
                  slot_usd, bonus_usd, signed, source
           FROM draft_results"""
    params: tuple = ()
    if draft_year is not None:
        q += " WHERE draft_year = ?"
        params = (draft_year,)
    q += " ORDER BY draft_year DESC, pick_overall ASC"
    try:
        with connect() as con:
            rows = con.execute(q, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def upsert_draft_order(rows: Iterable[dict]) -> int:
    n = 0
    with connect() as con:
        for r in rows:
            con.execute(
                """INSERT INTO draft_order
                     (draft_year, pick_overall, round_label, pick_in_round,
                      team, slot_usd, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(draft_year, pick_overall) DO UPDATE SET
                     round_label   = COALESCE(excluded.round_label, draft_order.round_label),
                     pick_in_round = COALESCE(excluded.pick_in_round, draft_order.pick_in_round),
                     team          = excluded.team,
                     slot_usd      = COALESCE(excluded.slot_usd, draft_order.slot_usd),
                     source        = excluded.source,
                     inserted_at   = datetime('now')""",
                (r.get("draft_year"), r.get("pick_overall"),
                 r.get("round_label"), r.get("pick_in_round"),
                 r.get("team"), r.get("slot_usd"), r.get("source")),
            )
            n += 1
    return n


def load_draft_order(draft_year: int | None = None) -> list[dict]:
    q = """SELECT draft_year, pick_overall, round_label, pick_in_round,
                  team, slot_usd, source
           FROM draft_order"""
    params: tuple = ()
    if draft_year is not None:
        q += " WHERE draft_year = ?"
        params = (draft_year,)
    q += " ORDER BY draft_year DESC, pick_overall ASC"
    try:
        with connect() as con:
            rows = con.execute(q, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def link_draft_to_milb(draft_key: str, milb_key: str) -> None:
    """Record a promotion: draft prospect -> MiLB player_key."""
    with connect() as con:
        con.execute(
            """INSERT INTO draft_canonical_keys (draft_key, milb_key)
               VALUES (?, ?)
               ON CONFLICT(draft_key) DO UPDATE SET
                 milb_key    = excluded.milb_key,
                 promoted_at = datetime('now')""",
            (draft_key, milb_key),
        )
        con.execute(
            """UPDATE draft_players SET promoted_key = ?, updated_at = datetime('now')
               WHERE player_key = ?""",
            (milb_key, draft_key),
        )


def backfill_draft_player_fields(rows: Iterable[dict]) -> int:
    """COALESCE-merge identity fields onto existing draft_players rows
    (used by the MLB-API identity backfill). Each row needs player_key plus
    any of mlbam_id / fg_player_id / school; existing non-null values win.
    Returns the number of rows touched."""
    n = 0
    with connect() as con:
        for r in rows:
            pk = r.get("player_key")
            if not pk:
                continue
            cur = con.execute(
                """UPDATE draft_players SET
                     mlbam_id     = COALESCE(mlbam_id, ?),
                     fg_player_id = COALESCE(fg_player_id, ?),
                     school       = COALESCE(school, ?),
                     updated_at   = datetime('now')
                   WHERE player_key = ?""",
                (r.get("mlbam_id"), r.get("fg_player_id"), r.get("school"), pk),
            )
            n += cur.rowcount or 0
    return n


def load_draft_canonical_keys() -> dict[str, str]:
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT draft_key, milb_key FROM draft_canonical_keys"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["draft_key"]: r["milb_key"] for r in rows}


def upsert_draft_lottery_odds(rows: Iterable[dict]) -> int:
    """Upsert lottery + projected-order rows. Each row: draft_year, team,
    pick_pos, odds_pct (% at #1, nullable), odds_top6_pct (% of landing in the
    top-6 lottery, nullable), wins / losses (record at scrape time, nullable),
    round_label (default '1'; '1A' / '1B' for competitive-balance picks),
    snapshot_date, source.

    The new columns use COALESCE(excluded, existing) so a re-run of an OLDER
    scraper build (which emits no top6/record keys) cannot blank values a
    newer build already stored for the same day."""
    n = 0
    with connect() as con:
        for r in rows:
            con.execute(
                """INSERT INTO draft_lottery_odds
                     (draft_year, team, pick_pos, odds_pct, odds_top6_pct,
                      wins, losses, round_label, snapshot_date, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(draft_year, team, pick_pos, snapshot_date) DO UPDATE SET
                     odds_pct      = excluded.odds_pct,
                     odds_top6_pct = COALESCE(excluded.odds_top6_pct,
                                              draft_lottery_odds.odds_top6_pct),
                     wins          = COALESCE(excluded.wins,
                                              draft_lottery_odds.wins),
                     losses        = COALESCE(excluded.losses,
                                              draft_lottery_odds.losses),
                     round_label   = excluded.round_label,
                     source        = excluded.source,
                     inserted_at   = datetime('now')""",
                (r["draft_year"], r["team"], r["pick_pos"], r.get("odds_pct"),
                 r.get("odds_top6_pct"), r.get("wins"), r.get("losses"),
                 r.get("round_label", "1"), r["snapshot_date"], r["source"]),
            )
            n += 1
    return n


def load_draft_lottery_odds(draft_year: int | None = None,
                            latest_only: bool = True) -> list[dict]:
    """Return lottery odds rows. When latest_only=True, restrict to the single
    most recent snapshot_date per draft_year (one full scrape).

    The dedup key is the latest snapshot for the whole draft_year, NOT per
    (team, pick_pos): teams move between projected slots from scrape to scrape,
    so keying on (team, pick_pos) would keep a team's stale old slot AND its new
    one - returning two rows at the same pick and self-contradictory odds."""
    _cols = ("draft_year, team, pick_pos, odds_pct, odds_top6_pct, wins, losses, "
             "round_label, snapshot_date, source")
    if latest_only:
        q = f"""SELECT {_cols}
               FROM draft_lottery_odds o
               WHERE snapshot_date = (
                 SELECT MAX(snapshot_date) FROM draft_lottery_odds
                 WHERE draft_year = o.draft_year
               )"""
    else:
        q = f"""SELECT {_cols}
               FROM draft_lottery_odds"""
    params: tuple = ()
    if draft_year is not None:
        q += " AND draft_year = ?" if "WHERE" in q else " WHERE draft_year = ?"
        params = (draft_year,)
    q += " ORDER BY draft_year DESC, odds_pct DESC, pick_pos ASC"
    try:
        with connect() as con:
            return [dict(r) for r in con.execute(q, params).fetchall()]
    except sqlite3.OperationalError:
        return []


# ===========================================================================
# Overseas prospects (KBO/NPB/CPBL) — parallel track to snapshots/players.
# Same firewall pattern as the draft tables.
# ===========================================================================

def insert_overseas_snapshots(snapshots: Iterable) -> int:
    """Upsert overseas prospect snapshots. Accepts iterables of objects
    with __dict__ (e.g. dataclass instances) or plain dicts."""
    count = 0
    with connect() as con:
        for s in snapshots:
            if hasattr(s, "__dict__"):
                d = s.__dict__
            elif hasattr(s, "_asdict"):
                d = s._asdict()
            else:
                d = dict(s)
            tools = d.get("tools")
            tools_json = json.dumps(tools) if tools else None
            cur = con.execute(
                """INSERT INTO overseas_snapshots
                     (source, snapshot_date, interval_label, player_key,
                      player_name, position, league, country, current_team,
                      proj_team, proj_bonus_usd, eta_year, fv, risk,
                      status, tools_json, fv_plus)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source, interval_label, player_key) DO UPDATE SET
                     snapshot_date  = excluded.snapshot_date,
                     player_name    = excluded.player_name,
                     position       = COALESCE(excluded.position, overseas_snapshots.position),
                     league         = COALESCE(excluded.league, overseas_snapshots.league),
                     country        = COALESCE(excluded.country, overseas_snapshots.country),
                     current_team   = COALESCE(excluded.current_team, overseas_snapshots.current_team),
                     proj_team      = COALESCE(excluded.proj_team, overseas_snapshots.proj_team),
                     proj_bonus_usd = COALESCE(excluded.proj_bonus_usd, overseas_snapshots.proj_bonus_usd),
                     eta_year       = COALESCE(excluded.eta_year, overseas_snapshots.eta_year),
                     fv             = excluded.fv,
                     risk           = COALESCE(excluded.risk, overseas_snapshots.risk),
                     status         = excluded.status,
                     tools_json     = COALESCE(excluded.tools_json, overseas_snapshots.tools_json),
                     fv_plus        = excluded.fv_plus""",
                (d.get("source"), d.get("snapshot_date"), d.get("interval_label"),
                 d.get("player_key"), d.get("player_name"), d.get("position"),
                 d.get("league"), d.get("country"), d.get("current_team"),
                 d.get("proj_team"), d.get("proj_bonus_usd"), d.get("eta_year"),
                 d.get("fv"), d.get("risk"), d.get("status", "overseas_active"),
                 tools_json, 1 if d.get("fv_plus") else 0),
            )
            count += cur.rowcount
            con.execute(
                """INSERT INTO overseas_players
                     (player_key, player_name, position, league, country,
                      current_team, proj_team, proj_bonus_usd, eta_year,
                      birth_date, bats, throws, height, weight,
                      fg_player_id, mlbam_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(player_key) DO UPDATE SET
                     player_name    = excluded.player_name,
                     position       = COALESCE(excluded.position, overseas_players.position),
                     league         = COALESCE(excluded.league, overseas_players.league),
                     country        = COALESCE(excluded.country, overseas_players.country),
                     current_team   = COALESCE(excluded.current_team, overseas_players.current_team),
                     proj_team      = COALESCE(excluded.proj_team, overseas_players.proj_team),
                     proj_bonus_usd = COALESCE(excluded.proj_bonus_usd, overseas_players.proj_bonus_usd),
                     eta_year       = COALESCE(excluded.eta_year, overseas_players.eta_year),
                     birth_date     = COALESCE(excluded.birth_date, overseas_players.birth_date),
                     bats           = COALESCE(excluded.bats, overseas_players.bats),
                     throws         = COALESCE(excluded.throws, overseas_players.throws),
                     height         = COALESCE(excluded.height, overseas_players.height),
                     weight         = COALESCE(excluded.weight, overseas_players.weight),
                     fg_player_id   = COALESCE(excluded.fg_player_id, overseas_players.fg_player_id),
                     mlbam_id       = COALESCE(excluded.mlbam_id, overseas_players.mlbam_id),
                     updated_at     = datetime('now')""",
                (d.get("player_key"), d.get("player_name"), d.get("position"),
                 d.get("league"), d.get("country"), d.get("current_team"),
                 d.get("proj_team"), d.get("proj_bonus_usd"), d.get("eta_year"),
                 d.get("birth_date"), d.get("bats"), d.get("throws"),
                 d.get("height"), d.get("weight"),
                 d.get("fg_player_id"), d.get("mlbam_id")),
            )
    return count


def load_overseas_snapshots(league: str | None = None) -> list[dict]:
    q = """SELECT id, source, snapshot_date, interval_label, player_key,
                  player_name, position, league, country, current_team,
                  proj_team, proj_bonus_usd, eta_year, fv, risk, status,
                  tools_json, fv_plus, inserted_at
           FROM overseas_snapshots"""
    params: tuple = ()
    if league is not None:
        q += " WHERE league = ?"
        params = (league,)
    q += " ORDER BY league ASC, snapshot_date DESC, fv DESC"
    try:
        with connect() as con:
            rows = con.execute(q, params).fetchall()
    except sqlite3.OperationalError as e:
        # A MISSING TABLE on a fresh DB is a legitimate empty result. Any other
        # operational error — notably "database is locked" under the concurrent
        # monthly pipeline — must NOT be swallowed into []: that turns a transient
        # lock into a permanently-empty overseas export (the 2026-06 leagues:[]
        # regression). Re-raise so the caller aborts instead of clobbering a good
        # sidecar; the export floor in export_overseas_json then preserves it.
        if "no such table" in str(e).lower():
            return []
        raise
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        if d.get("tools_json"):
            try:
                d["tools"] = json.loads(d["tools_json"])
            except (ValueError, TypeError):
                d["tools"] = None
        else:
            d["tools"] = None
        out.append(d)
    return out


def overseas_snapshot_count() -> int:
    """Row count of the overseas_snapshots table (0 if the table is missing).
    Used by export_overseas_json's floor guard to tell a genuinely-empty source
    apart from a transient read that returned nothing — so a 0-prospect export
    can never silently overwrite a known-good sidecar."""
    try:
        with connect() as con:
            return int(con.execute("SELECT COUNT(*) FROM overseas_snapshots").fetchone()[0])
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            return 0
        raise


# ── TJStats per-(MLBAM id, snapshot) sidecar ─────────────────────────────────
def upsert_tjstats_snapshots(rows: Iterable[dict]) -> int:
    """Upsert TJStats point-in-time rows. Grain = (mlbam_id, snapshot_label) so a
    same-label re-run (the date-stamped Live label gives per-day idempotency)
    updates in place, while a new day or named snapshot inserts. fv/grades/writeup
    use COALESCE so a re-run that lacks them (e.g. a historical board with FV NULL)
    never wipes values already on file."""
    con_rows = list(rows)
    if not con_rows:
        return 0
    n = 0
    with connect() as con:
        for r in con_rows:
            cur = con.execute(
                """INSERT INTO tjstats_snapshots
                   (mlbam_id, player_key, snapshot_label, snapshot_kind, snapshot_id,
                    effective_date, captured_at, source_modified_at, source_url,
                    name, position, org, type, rank, prev_rank, fv, eta, risk,
                    grades_json, tools_json, writeup, with_fv)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(mlbam_id, snapshot_label) DO UPDATE SET
                       player_key=excluded.player_key, snapshot_kind=excluded.snapshot_kind,
                       snapshot_id=excluded.snapshot_id, effective_date=excluded.effective_date,
                       captured_at=excluded.captured_at,
                       source_modified_at=excluded.source_modified_at,
                       source_url=excluded.source_url, name=excluded.name,
                       position=COALESCE(excluded.position, tjstats_snapshots.position),
                       org=COALESCE(excluded.org, tjstats_snapshots.org),
                       type=excluded.type, rank=excluded.rank, prev_rank=excluded.prev_rank,
                       fv=COALESCE(excluded.fv, tjstats_snapshots.fv),
                       eta=COALESCE(excluded.eta, tjstats_snapshots.eta),
                       risk=COALESCE(excluded.risk, tjstats_snapshots.risk),
                       grades_json=COALESCE(excluded.grades_json, tjstats_snapshots.grades_json),
                       tools_json=COALESCE(excluded.tools_json, tjstats_snapshots.tools_json),
                       writeup=COALESCE(excluded.writeup, tjstats_snapshots.writeup),
                       with_fv=excluded.with_fv""",
                (str(r["mlbam_id"]), r.get("player_key"), r["snapshot_label"],
                 r["snapshot_kind"], r.get("snapshot_id"), r.get("effective_date"),
                 r["captured_at"], r.get("source_modified_at"), r.get("source_url"),
                 r.get("name"), r.get("position"), r.get("org"), r.get("type"),
                 r.get("rank"), r.get("prev_rank"), r.get("fv"), r.get("eta"),
                 r.get("risk"), r.get("grades_json"), r.get("tools_json"),
                 r.get("writeup"), 1 if r.get("with_fv") else 0),
            )
            n += cur.rowcount
    return n


def load_tjstats_snapshots(snapshot_label: str | None = None) -> list[dict]:
    q = "SELECT * FROM tjstats_snapshots"
    params: tuple = ()
    if snapshot_label is not None:
        q += " WHERE snapshot_label = ?"
        params = (snapshot_label,)
    q += " ORDER BY snapshot_label DESC, rank ASC"
    try:
        with connect() as con:
            return [dict(r) for r in con.execute(q, params).fetchall()]
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            return []
        raise


def tjstats_snapshot_labels() -> list[dict]:
    """Distinct snapshot labels with kind, effective date, latest capture, and
    count — for Time Machine wiring and the scraper health check."""
    try:
        with connect() as con:
            return [dict(r) for r in con.execute(
                "SELECT snapshot_label, snapshot_kind, effective_date, "
                "       MAX(captured_at) AS captured_at, COUNT(*) AS n "
                "FROM tjstats_snapshots GROUP BY snapshot_label "
                # captured_at is the deterministic tiebreak when a named monthly and
                # a live board share an effective_date (a drop day): without it the
                # within-date order is undefined. Selection logic in export_movers
                # keys off snapshot_kind explicitly and does not rely on this order.
                "ORDER BY effective_date DESC, captured_at DESC").fetchall()]
    except sqlite3.OperationalError:
        return []


def load_overseas_players(league: str | None = None) -> dict[str, dict]:
    q = """SELECT player_key, player_name, position, league, country,
                  current_team, proj_team, proj_bonus_usd, eta_year,
                  birth_date, bats, throws, height, weight,
                  fg_player_id, mlbam_id, promoted_key,
                  posted_date, signed_date, signed_team, signed_bonus_usd
           FROM overseas_players"""
    params: tuple = ()
    if league is not None:
        q += " WHERE league = ?"
        params = (league,)
    try:
        with connect() as con:
            rows = con.execute(q, params).fetchall()
    except sqlite3.OperationalError as e:
        # See load_overseas_snapshots: only a missing table is a legit empty;
        # a transient lock must propagate, not silently zero the overseas pool.
        if "no such table" in str(e).lower():
            return {}
        raise
    return {r["player_key"]: dict(r) for r in rows}


def upsert_overseas_statlines(rows: Iterable[dict]) -> int:
    """Upsert per-season overseas stat lines. Each row carries
    player_key, season, league, team, payload (dict)."""
    n = 0
    with connect() as con:
        for r in rows:
            payload = r.get("payload") or {k: v for k, v in r.items()
                                           if k not in {"player_key", "season",
                                                        "league", "team"}}
            con.execute(
                """INSERT INTO overseas_statlines
                     (player_key, season, league, team, payload_json)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(player_key, season, league) DO UPDATE SET
                     team         = COALESCE(excluded.team, overseas_statlines.team),
                     payload_json = excluded.payload_json,
                     fetched_at   = datetime('now')""",
                (r["player_key"], r["season"], r["league"], r.get("team"),
                 json.dumps(payload, default=str)),
            )
            n += 1
    return n


def load_overseas_statlines(player_key: str | None = None) -> list[dict]:
    q = """SELECT player_key, season, league, team, payload_json
           FROM overseas_statlines"""
    params: tuple = ()
    if player_key is not None:
        q += " WHERE player_key = ?"
        params = (player_key,)
    q += " ORDER BY player_key ASC, season ASC"
    try:
        with connect() as con:
            rows = con.execute(q, params).fetchall()
    except sqlite3.OperationalError:
        return []
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        if d.get("payload_json"):
            try:
                d["payload"] = json.loads(d["payload_json"])
            except (ValueError, TypeError):
                d["payload"] = {}
        out.append(d)
    return out


# v31.8 — MLB trade player cache helpers. Lookup keyed by name slug
# (lowercase + punctuation-stripped) so frontend description parsers
# can resolve "Brendan Donovan" → "brendan_donovan" → cached row.
import re as _re_mlb_slug
def _name_slug(name: str | None) -> str:
    if not name:
        return ""
    return _re_mlb_slug.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def upsert_mlb_trade_player(row: dict) -> int:
    """Upsert one MLB trade player. Returns 1 on insert/update.
    v31.9c — Accepts contract + surplus fields."""
    slug = _name_slug(row.get("player_name"))
    if not slug:
        return 0
    with connect() as con:
        con.execute(
            """INSERT INTO mlb_trade_players
                 (name_slug, player_name, mlbam_id, primary_position,
                  career_war, war_seasons, last_team, is_pitcher,
                  resolve_status,
                  current_aav_usd, years_remaining, contract_total_usd,
                  age, projected_war_remaining, surplus_mm)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name_slug) DO UPDATE SET
                 player_name             = excluded.player_name,
                 mlbam_id                = COALESCE(excluded.mlbam_id, mlb_trade_players.mlbam_id),
                 primary_position        = COALESCE(excluded.primary_position, mlb_trade_players.primary_position),
                 career_war              = COALESCE(excluded.career_war, mlb_trade_players.career_war),
                 war_seasons             = COALESCE(excluded.war_seasons, mlb_trade_players.war_seasons),
                 last_team               = COALESCE(excluded.last_team, mlb_trade_players.last_team),
                 is_pitcher              = excluded.is_pitcher,
                 resolve_status          = excluded.resolve_status,
                 current_aav_usd         = COALESCE(excluded.current_aav_usd, mlb_trade_players.current_aav_usd),
                 years_remaining         = COALESCE(excluded.years_remaining, mlb_trade_players.years_remaining),
                 contract_total_usd      = COALESCE(excluded.contract_total_usd, mlb_trade_players.contract_total_usd),
                 age                     = COALESCE(excluded.age, mlb_trade_players.age),
                 projected_war_remaining = COALESCE(excluded.projected_war_remaining, mlb_trade_players.projected_war_remaining),
                 surplus_mm              = COALESCE(excluded.surplus_mm, mlb_trade_players.surplus_mm),
                 fetched_at              = datetime('now')""",
            (slug, row["player_name"], row.get("mlbam_id"),
             row.get("primary_position"), row.get("career_war"),
             row.get("war_seasons"), row.get("last_team"),
             1 if row.get("is_pitcher") else 0,
             row.get("resolve_status") or "resolved",
             row.get("current_aav_usd"), row.get("years_remaining"),
             row.get("contract_total_usd"), row.get("age"),
             row.get("projected_war_remaining"), row.get("surplus_mm")),
        )
    return 1


def load_mlb_trade_players() -> dict[str, dict]:
    """Return {name_slug: row} for every cached MLB trade player."""
    try:
        with connect() as con:
            rows = con.execute(
                """SELECT name_slug, player_name, mlbam_id, primary_position,
                          career_war, war_seasons, last_team, is_pitcher,
                          resolve_status, fetched_at,
                          current_aav_usd, years_remaining,
                          contract_total_usd, age,
                          projected_war_remaining, surplus_mm
                   FROM mlb_trade_players"""
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["name_slug"]: dict(r) for r in rows}


# v31.7 — Draft statlines mirror the overseas helpers.
def upsert_draft_statlines(rows: Iterable[dict]) -> int:
    """Upsert per-season draft prospect stat lines. Each row carries
    player_key, season, league (conference / level code), team, payload."""
    n = 0
    with connect() as con:
        for r in rows:
            payload = r.get("payload") or {k: v for k, v in r.items()
                                           if k not in {"player_key", "season",
                                                        "league", "team"}}
            con.execute(
                """INSERT INTO draft_statlines
                     (player_key, season, league, team, payload_json)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(player_key, season, league) DO UPDATE SET
                     team         = COALESCE(excluded.team, draft_statlines.team),
                     payload_json = excluded.payload_json,
                     fetched_at   = datetime('now')""",
                (r["player_key"], r["season"], r["league"], r.get("team"),
                 json.dumps(payload, default=str)),
            )
            n += 1
    return n


def load_draft_statlines(player_key: str | None = None) -> list[dict]:
    q = """SELECT player_key, season, league, team, payload_json
           FROM draft_statlines"""
    params: tuple = ()
    if player_key is not None:
        q += " WHERE player_key = ?"
        params = (player_key,)
    q += " ORDER BY player_key ASC, season DESC"
    try:
        with connect() as con:
            rows = con.execute(q, params).fetchall()
    except sqlite3.OperationalError:
        return []
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        if d.get("payload_json"):
            try:
                d["payload"] = json.loads(d["payload_json"])
            except (ValueError, TypeError):
                d["payload"] = {}
        out.append(d)
    return out


def upsert_collegesavant_box_scores(rows: Iterable[dict]) -> int:
    """Upsert NCAA box scores for CollegeSavant's tracked players, keyed by the
    CS frontend slug. Each row: player_slug, season, side ('batting'|'pitching'),
    school, payload."""
    n = 0
    with connect() as con:
        for r in rows:
            con.execute(
                """INSERT INTO collegesavant_box_scores
                     (player_slug, season, side, school, payload_json)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(player_slug, season, side) DO UPDATE SET
                     school       = COALESCE(excluded.school, collegesavant_box_scores.school),
                     payload_json = excluded.payload_json,
                     fetched_at   = datetime('now')""",
                (r["player_slug"], r["season"], r["side"], r.get("school"),
                 json.dumps(r.get("payload") or {}, default=str)),
            )
            n += 1
    return n


def load_collegesavant_box_scores() -> list[dict]:
    """All CollegeSavant box scores (latest season per player surfaces in the
    frontend join). Empty list if the table does not exist yet."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_slug, season, side, school, payload_json "
                "FROM collegesavant_box_scores ORDER BY player_slug ASC, season DESC"
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        try:
            d["payload"] = json.loads(d["payload_json"]) if d.get("payload_json") else {}
        except (ValueError, TypeError):
            d["payload"] = {}
        out.append(d)
    return out


def link_overseas_to_milb(overseas_key: str, milb_key: str,
                          signed_team: str | None = None,
                          signed_bonus_usd: int | None = None,
                          signed_date: str | None = None) -> None:
    """Record a signing: overseas → MiLB. Also stamps the player row
    with the signing metadata for the UI."""
    with connect() as con:
        con.execute(
            """INSERT INTO overseas_canonical_keys (overseas_key, milb_key)
               VALUES (?, ?)
               ON CONFLICT(overseas_key) DO UPDATE SET
                 milb_key   = excluded.milb_key,
                 signed_at  = datetime('now')""",
            (overseas_key, milb_key),
        )
        con.execute(
            """UPDATE overseas_players
               SET promoted_key = ?,
                   signed_team = COALESCE(?, signed_team),
                   signed_bonus_usd = COALESCE(?, signed_bonus_usd),
                   signed_date = COALESCE(?, signed_date),
                   updated_at = datetime('now')
               WHERE player_key = ?""",
            (milb_key, signed_team, signed_bonus_usd, signed_date, overseas_key),
        )


def load_overseas_canonical_keys() -> dict[str, str]:
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT overseas_key, milb_key FROM overseas_canonical_keys"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["overseas_key"]: r["milb_key"] for r in rows}


def upsert_overseas_posting(player_key: str, posted_date: str | None = None) -> None:
    """Mark a prospect as posted (NPB/KBO posting system)."""
    with connect() as con:
        con.execute(
            """UPDATE overseas_players SET posted_date = ?, updated_at = datetime('now')
               WHERE player_key = ?""",
            (posted_date, player_key),
        )
        con.execute(
            """UPDATE overseas_snapshots SET status = 'posted'
               WHERE player_key = ? AND status = 'overseas_active'""",
            (player_key,),
        )


# ===========================================================================
# IL status (existing functionality below)
# ===========================================================================

def upsert_il_status(by_key: dict[str, dict | None]) -> int:
    """Upsert IL status. Pass None as the value to clear a prior IL row
    (player came off IL since the previous run).

    Each non-None dict carries: is_on_il, since, type, description.
    """
    n = 0
    with connect() as con:
        for key, rec in by_key.items():
            if rec is None or not rec.get("is_on_il"):
                # Drop any prior row so a stale "on IL" badge doesn't
                # linger after activation.
                con.execute("DELETE FROM il_status WHERE player_key = ?", (key,))
                continue
            con.execute(
                """INSERT INTO il_status
                     (player_key, is_on_il, since, type, description, fetched_at)
                   VALUES (?, 1, ?, ?, ?, datetime('now'))
                   ON CONFLICT(player_key) DO UPDATE SET
                     is_on_il=1,
                     since=excluded.since,
                     type=excluded.type,
                     description=excluded.description,
                     fetched_at=excluded.fetched_at""",
                (key, rec.get("since"), rec.get("type"), rec.get("description")),
            )
            n += 1
    return n


def load_il_status() -> dict[str, dict]:
    """Return {player_key: il_dict} for every prospect currently on IL."""
    try:
        with connect() as con:
            rows = con.execute(
                """SELECT player_key, is_on_il, since, type, description
                   FROM il_status WHERE is_on_il = 1"""
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: dict(r) for r in rows}


def upsert_player_transactions(by_player: dict[str, list[dict]]) -> int:
    """Upsert per-player transaction lists. One row per player.

    Each list value is the full payload from the MLB Stats API per-player
    transactions endpoint, normalized to {date, type_code, description,
    from_team_id, from_team_name, to_team_id, to_team_name}. Pass an empty
    list to record "we asked, nothing was returned" without rewriting a
    prior populated row (we keep the old payload in that case).
    """
    n = 0
    with connect() as con:
        for key, rows in by_player.items():
            if not rows:
                # Touch fetched_at only — keeps TTL skip working without
                # erasing a previously-populated payload.
                con.execute(
                    """UPDATE player_transactions
                       SET fetched_at = datetime('now')
                       WHERE player_key = ?""",
                    (key,),
                )
                continue
            con.execute(
                """INSERT INTO player_transactions
                     (player_key, payload_json, fetched_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(player_key) DO UPDATE SET
                     payload_json=excluded.payload_json,
                     fetched_at=excluded.fetched_at""",
                (key, json.dumps(rows)),
            )
            n += 1
    return n


def load_player_transactions() -> dict[str, list[dict]]:
    """Return {player_key: [tx_rows]} for every stored player transaction history."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, payload_json FROM player_transactions"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


def load_player_transactions_meta() -> dict[str, str]:
    """Return {player_key: fetched_at_iso} for every stored player_transactions row."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, fetched_at FROM player_transactions"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: r["fetched_at"] for r in rows}


def upsert_roster_status(by_player: dict[str, dict]) -> int:
    """Upsert derived roster-status dicts (debut/options/service time)."""
    n = 0
    with connect() as con:
        for key, rec in by_player.items():
            if not rec:
                continue
            con.execute(
                """INSERT INTO roster_status
                     (player_key, payload_json, fetched_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(player_key) DO UPDATE SET
                     payload_json=excluded.payload_json,
                     fetched_at=excluded.fetched_at""",
                (key, json.dumps(rec)),
            )
            n += 1
    return n


def load_roster_status() -> dict[str, dict]:
    """Return {player_key: roster_status_dict} for every stored row."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, payload_json FROM roster_status"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: json.loads(r["payload_json"]) for r in rows}


# ---------------------------------------------------------------------------
# Derived-state history (metric_snapshots + il_history) — added 2026-06.
# ---------------------------------------------------------------------------
# Fields pulled from each serialized timeseries player into the snapshot
# payload. These are the Arkmetric family + value signals that are reliably
# present at the player top level (raw dvm_plus/rps_plus live on graduate/org
# records, not the active board, so we capture the surfaced "+" versions).
_METRIC_SNAPSHOT_PAYLOAD_FIELDS = (
    "dollar_dvm_plus",           # $DvM+
    "statcast_plus",             # SC+
    "tool",                      # tool composite (ToolDvM+ base)
    # Consensus-side live form / external-list movement (consensus FV + live_signal
    # delta). NOT an eFV output and not the board ordering — see the block that builds
    # it in export_timeseries_json. Renamed 2026-07-25 from live_score/live_overall_rank;
    # rows written before then carry the old keys in payload_json.
    "consensus_live_score",
    "consensus_live_rank",
)

# Source coverage beside each metric_snapshots row (owner answer B4SP-2,
# 2026-10-01): written by snapshot_board_metrics from
# consensus.point_source_coverage, which holds the exact definitions. The
# recorder landed on METRIC_SNAPSHOT_COVERAGE_START; no row dated earlier
# carries coverage and none is ever back-filled. A row records coverage iff
# source_n IS NOT NULL; the first recorded night is
# metric_snapshot_coverage_start().
METRIC_SNAPSHOT_COVERAGE_START = "2026-10-01"
METRIC_SNAPSHOT_COVERAGE_COLUMNS = (
    ("source_n",         "INTEGER"),
    ("source_keys",      "TEXT"),
    ("best_rank",        "INTEGER"),
    ("best_rank_source", "TEXT"),
    ("best_rank_date",   "TEXT"),
)


def _fv_tier_label(fv, fv_plus) -> str | None:
    """Coarse FV-tier bucket label used for cohorting ('60','55','50'…).

    Mirrors the 5-point grade ladder; the trailing '+' upside marker is kept
    so a 55+ cohort can be split from a flat 55 if desired downstream.
    """
    if fv is None:
        return None
    base = int(round(float(fv) / 5.0) * 5)
    return f"{base}+" if fv_plus else str(base)


def snapshot_board_metrics(players: Iterable[dict], snapshot_date: str | None = None,
                           source_coverage: dict[str, dict] | None = None) -> int:
    """Capture the DERIVED board state (consensus rank/FV + Arkmetric family)
    for every player in a built timeseries, one row per player per calendar
    date. Idempotent: re-running on the same date overwrites that date's rows.

    `players` is the list of serialized player dicts from timeseries.json
    (or the in-memory equivalent). Players with no consensus FV and no rank
    are skipped (nothing meaningful to snapshot).

    `source_coverage` is consensus.source_coverage_by_player over the same
    build ({player_key: {source_n, source_keys, best_rank, best_rank_source,
    best_rank_date}}). When it is given, every row written records its
    player's coverage; a board player missing from it (a key the build did not
    produce) records NULL, never a made-up 0. When it is None the coverage
    columns are left as they are: NULL on a new row, the recorded values on a
    same-date re-run.
    """
    snapshot_date = snapshot_date or date.today().isoformat()
    n = 0
    cov_cols = [c for c, _ddl in METRIC_SNAPSHOT_COVERAGE_COLUMNS]
    if source_coverage is not None:
        cov_update = "".join(f",\n                     {c}=excluded.{c}" for c in cov_cols)
    else:
        cov_update = ""
    sql = (
        """INSERT INTO metric_snapshots
                     (player_key, snapshot_date, overall_rank, consensus_fv,
                      fv_plus, fv_tier, org, position, status, is_pitcher,
                      age, payload_json, inserted_at, """ + ", ".join(cov_cols) + """)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), """
        + ", ".join("?" for _c in cov_cols) + """)
                   ON CONFLICT(player_key, snapshot_date) DO UPDATE SET
                     overall_rank=excluded.overall_rank,
                     consensus_fv=excluded.consensus_fv,
                     fv_plus=excluded.fv_plus,
                     fv_tier=excluded.fv_tier,
                     org=excluded.org,
                     position=excluded.position,
                     status=excluded.status,
                     is_pitcher=excluded.is_pitcher,
                     age=excluded.age,
                     payload_json=excluded.payload_json,
                     inserted_at=excluded.inserted_at""" + cov_update)
    with connect() as con:
        for p in players:
            if not isinstance(p, dict):
                continue
            key = p.get("player_key")
            if not key:
                continue
            fv = p.get("fv_close")
            rank = p.get("overall_rank")
            if fv is None and rank is None:
                continue
            fv_plus = 1 if p.get("fv_close_plus") else 0
            surplus = p.get("surplus") or {}
            payload = {f: p.get(f) for f in _METRIC_SNAPSHOT_PAYLOAD_FIELDS
                       if p.get(f) is not None}
            if surplus.get("value_mm") is not None:
                payload["surplus_mm"] = surplus.get("value_mm")
            cov = (source_coverage or {}).get(key)
            if cov is not None:
                cov_vals = tuple(cov.get(c) for c in cov_cols)
            else:
                cov_vals = (None,) * len(cov_cols)
            con.execute(
                sql,
                (key, snapshot_date, rank, fv, fv_plus,
                 _fv_tier_label(fv, fv_plus), p.get("org"), p.get("position"),
                 p.get("status"),
                 1 if (p.get("position") or "").upper() in ("SP", "RP", "P", "SIRP", "MIRP", "RHP", "LHP") else 0,
                 p.get("age"), json.dumps(payload)) + cov_vals,
            )
            n += 1
    return n


def metric_snapshot_coverage_start() -> str | None:
    """The first snapshot date whose rows record source coverage (source_n
    not NULL), or None before the first recording night."""
    try:
        with connect() as con:
            row = con.execute(
                "SELECT MIN(snapshot_date) FROM metric_snapshots "
                "WHERE source_n IS NOT NULL").fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def snapshot_fa_penter(class_year: int, rows: Iterable[dict], *,
                       generated_at: str | None, host: str | None,
                       git_sha: str | None) -> int:
    """Write tonight's served P(enter) rows (M04-05). The date is TODAY and is
    not a parameter: a served value can only be recorded on the night it was
    served, so there is no way to back-fill a past date from a current file.
    Idempotent within a date (the last write of the night wins)."""
    snapshot_date = date.today().isoformat()
    n = 0
    with connect() as con:
        for r in rows:
            key = r.get("key")
            if not key:
                continue
            con.execute(
                """INSERT INTO fa_penter_served_history
                     (class_year, player_key, snapshot_date, fa_type, status,
                      opt_price_usd, enter_prob, enter_prob_src, proj_aav_usd,
                      proj_aav_p10_usd, proj_aav_p90_usd, fa_class_generated_at,
                      host, git_sha, inserted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(class_year, player_key, snapshot_date) DO UPDATE SET
                     fa_type=excluded.fa_type, status=excluded.status,
                     opt_price_usd=excluded.opt_price_usd,
                     enter_prob=excluded.enter_prob,
                     enter_prob_src=excluded.enter_prob_src,
                     proj_aav_usd=excluded.proj_aav_usd,
                     proj_aav_p10_usd=excluded.proj_aav_p10_usd,
                     proj_aav_p90_usd=excluded.proj_aav_p90_usd,
                     fa_class_generated_at=excluded.fa_class_generated_at,
                     host=excluded.host, git_sha=excluded.git_sha,
                     inserted_at=excluded.inserted_at""",
                (int(class_year), key, snapshot_date, r.get("type"), r.get("status"),
                 r.get("optPrice"), r.get("enterProb"), r.get("enterProbSrc"),
                 r.get("projAav"), r.get("projAavP10"), r.get("projAavP90"),
                 generated_at, host, git_sha),
            )
            n += 1
    return n


def snapshot_trade_values(players: Iterable[dict], snapshot_date: str | None = None) -> int:
    """Capture each Trade Machine board record's surplus value as-of date, one
    row per player per calendar date. This is the INSTRUMENT that enables a true
    FORWARD backtest of the board ordering (the trade_machine_surplus eval is
    currently rank-only / hindsight because trade_values.json was never
    snapshotted). Cannot be back-filled - the track record begins the first run
    after this lands. Idempotent: re-running on a date overwrites that date.

    `players` is the trade_values.json `players` list (post apply_platform_surplus).
    Players with no trade_value_mm are skipped (nothing to snapshot)."""
    snapshot_date = snapshot_date or date.today().isoformat()
    n = 0
    with connect() as con:
        for p in players:
            if not isinstance(p, dict):
                continue
            key = p.get("player_key")
            if not key or p.get("trade_value_mm") is None:
                continue
            con.execute(
                """INSERT INTO trade_value_history
                     (player_key, snapshot_date, trade_value_mm, surplus_source,
                      trade_value_tier, trade_value_grade, xfv_grade, status,
                      age, position, org, inserted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(player_key, snapshot_date) DO UPDATE SET
                     trade_value_mm=excluded.trade_value_mm,
                     surplus_source=excluded.surplus_source,
                     trade_value_tier=excluded.trade_value_tier,
                     trade_value_grade=excluded.trade_value_grade,
                     xfv_grade=excluded.xfv_grade,
                     status=excluded.status, age=excluded.age,
                     position=excluded.position, org=excluded.org,
                     inserted_at=excluded.inserted_at""",
                (key, snapshot_date, p.get("trade_value_mm"), p.get("surplus_source"),
                 p.get("trade_value_tier"), p.get("trade_value_grade"), p.get("xfv_grade"),
                 p.get("status"), p.get("age"), p.get("position"), p.get("org")),
            )
            n += 1
    return n


def metric_snapshot_dates() -> list[str]:
    """Return the distinct snapshot dates present in metric_snapshots, ascending."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT DISTINCT snapshot_date FROM metric_snapshots ORDER BY snapshot_date"
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r[0] for r in rows]


def load_metric_snapshots(player_key: str | None = None,
                          snapshot_date: str | None = None) -> list[dict]:
    """Load metric_snapshots rows, optionally filtered by player and/or date.

    Returns a list of flat dicts with the board columns plus the unpacked
    Arkmetric payload (dollar_dvm_plus, statcast_plus, …).
    """
    where, params = [], []
    if player_key is not None:
        where.append("player_key = ?"); params.append(player_key)
    if snapshot_date is not None:
        where.append("snapshot_date = ?"); params.append(snapshot_date)
    sql = ("SELECT player_key, snapshot_date, overall_rank, consensus_fv, fv_plus, "
           "fv_tier, org, position, status, is_pitcher, age, payload_json "
           "FROM metric_snapshots")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY snapshot_date, overall_rank"
    try:
        with connect() as con:
            rows = con.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for r in rows:
        d = dict(r)
        payload = d.pop("payload_json", None)
        if payload:
            try:
                d.update(json.loads(payload))
            except (TypeError, ValueError):
                pass
        out.append(d)
    return out


def load_rank_history() -> dict[str, list[dict]]:
    """Per-player overall board-rank history from metric_snapshots, grouped by
    player_key and ordered oldest-first: {player_key: [{snapshot_date, rank}, ...]}.
    The input layer for movement.compute_rank_movement AND for prev_overall_rank,
    so both read one field on one basis. One query for the whole board (per-player
    queries in the export loop would be ~4,500 round-trips).

    BASIS GATE: rows dated before BOARD_RANK_BASIS_EPOCH were ranked on the retired
    quantile basis. The 2026-07-25 flip to the raw eFV grade moved ~4.46k of 4.47k
    board rows (median |move| ~417 spots, largest ~3.5k), so feeding pre-epoch ranks
    into the movement engine would publish a basis change as player movement. They are
    dropped at the source: rank movement and the rank-trend arrow report nothing until
    two post-epoch snapshots exist, which is the disclosed one-time discontinuity."""
    out: dict[str, list[dict]] = {}
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, snapshot_date, overall_rank FROM metric_snapshots "
                "WHERE overall_rank IS NOT NULL AND snapshot_date > ? "
                "ORDER BY player_key, snapshot_date",
                (BOARD_RANK_BASIS_EPOCH,),
            ).fetchall()
    except sqlite3.OperationalError:
        return out
    for r in rows:
        out.setdefault(r["player_key"], []).append(
            {"snapshot_date": r["snapshot_date"], "rank": r["overall_rank"]})
    return out


def snapshot_farm_ranks(org_summary: Iterable[dict],
                        snapshot_date: str | None = None) -> int:
    """Capture the composite farm-system rank (+ farm_score) for every org,
    one row per org per calendar date. Idempotent: re-running on the same date
    overwrites that date's rows.

    `org_summary` is the list of org dicts from the exported boot payload (each
    carries `org`, `farm_rank`, `farm_score`). Entries with no org code or no
    farm_rank are skipped (nothing to snapshot). This is the missing input
    layer for movement.compute_farm_movement — it cannot be back-filled, so the
    track record starts the first run after it lands.
    """
    snapshot_date = snapshot_date or date.today().isoformat()
    n = 0
    with connect() as con:
        for e in org_summary:
            if not isinstance(e, dict):
                continue
            org = e.get("org")
            rank = e.get("farm_rank")
            if not org or rank is None:
                continue
            con.execute(
                """INSERT INTO farm_rank_history
                     (org, snapshot_date, farm_rank, farm_score, inserted_at)
                   VALUES (?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(org, snapshot_date) DO UPDATE SET
                     farm_rank=excluded.farm_rank,
                     farm_score=excluded.farm_score,
                     inserted_at=excluded.inserted_at""",
                (org, snapshot_date, rank, e.get("farm_score")),
            )
            n += 1
    return n


def load_farm_rank_history(org: str | None = None) -> list[dict]:
    """Load farm_rank_history rows, optionally filtered to one org.

    Returns flat dicts ordered by (org, snapshot_date ascending) so a caller can
    group by org and read each org's series oldest-first (the order the movement
    engine expects)."""
    where, params = [], []
    if org is not None:
        where.append("org = ?"); params.append(org)
    sql = ("SELECT org, snapshot_date, farm_rank, farm_score "
           "FROM farm_rank_history")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY org, snapshot_date"
    try:
        with connect() as con:
            rows = con.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def farm_rank_history_dates() -> list[str]:
    """Return the distinct snapshot dates present in farm_rank_history, ascending."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT DISTINCT snapshot_date FROM farm_rank_history ORDER BY snapshot_date"
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r[0] for r in rows]


# The full set of letters _letter_grade can emit. Anything else on an org
# entry (the sparse dash sentinel, None, junk) means the grade could not be
# computed and the org is skipped rather than written.
_FARM_GRADE_LETTERS = frozenset(
    ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "D-", "F"])


def snapshot_farm_grades(org_summary: Iterable[dict],
                         snapshot_date: str | None = None) -> int:
    """Capture the composite farm LETTER grade for every org, one row per org
    per calendar date. Sibling to snapshot_farm_ranks (which records only the
    rank), letter-grade edition: records the letter the PROSPX farm systems
    view displays, the numeric composite it sorts on, and the window setting.

    `org_summary` is the list of org dicts from the exported boot payload.
    The displayed letter is letter_by_window[FARM_PRINCIPAL_WINDOW] (the
    board default); if the windowed letter is absent the canonical
    grades.overall / farm_score pair is recorded with grade_window
    'canonical' (the same fallback order the frontend uses). Orgs whose
    grade cannot be resolved to a real letter are skipped, so a payload
    with no computable grades no-ops cleanly and returns 0.

    Idempotent within a day (re-running on the same date overwrites that
    date's rows, never duplicating them); rows for prior dates are never
    touched, so the table is append-only over time. Cannot be back-filled:
    the letter track record begins 2026-07-02.
    """
    snapshot_date = snapshot_date or date.today().isoformat()
    n = 0
    with connect() as con:
        try:
            con.execute("SELECT 1 FROM farm_grade_history LIMIT 1")
        except sqlite3.OperationalError:
            con.executescript(SCHEMA)
        for e in org_summary or []:
            if not isinstance(e, dict):
                continue
            org = e.get("org")
            if not org:
                continue
            win = FARM_PRINCIPAL_WINDOW
            letter = (e.get("letter_by_window") or {}).get(win)
            score = (e.get("farm_score_by_window") or {}).get(win)
            if letter not in _FARM_GRADE_LETTERS:
                letter = (e.get("grades") or {}).get("overall")
                score = e.get("farm_score")
                win = "canonical"
            if letter not in _FARM_GRADE_LETTERS:
                continue
            con.execute(
                """INSERT INTO farm_grade_history
                     (org, snapshot_date, letter, farm_score, grade_window, inserted_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(org, snapshot_date) DO UPDATE SET
                     letter=excluded.letter,
                     farm_score=excluded.farm_score,
                     grade_window=excluded.grade_window,
                     inserted_at=excluded.inserted_at""",
                (org, snapshot_date, letter, score, win),
            )
            n += 1
    return n


def load_farm_grade_history(org: str | None = None) -> list[dict]:
    """Load farm_grade_history rows, optionally filtered to one org.

    Returns flat dicts ordered by (org, snapshot_date ascending) so a caller
    can group by org and read each org's letter series oldest-first (the
    shape the future forward letter backtest will consume)."""
    where, params = [], []
    if org is not None:
        where.append("org = ?"); params.append(org)
    sql = ("SELECT org, snapshot_date, letter, farm_score, grade_window "
           "FROM farm_grade_history")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY org, snapshot_date"
    try:
        with connect() as con:
            rows = con.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def farm_grade_history_dates() -> list[str]:
    """Return the distinct snapshot dates present in farm_grade_history, ascending."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT DISTINCT snapshot_date FROM farm_grade_history ORDER BY snapshot_date"
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r[0] for r in rows]


def record_il_observation(current_il_by_key: dict[str, dict],
                          observed_date: str | None = None) -> dict[str, int]:
    """Append-only IL stint timeline update. Call after refreshing IL status.

    `current_il_by_key` is the {player_key: il_dict} of everyone CURRENTLY on
    the IL (i.e. the output of load_il_status()). For each, record the stint
    once keyed by its placement `since` date; for any previously-open stint
    whose player is no longer on the IL, stamp the activation date.

    Idempotent within a day. Returns {placed, activated} counts.
    """
    observed_date = observed_date or date.today().isoformat()
    placed = activated = 0
    with connect() as con:
        try:
            con.execute("SELECT 1 FROM il_history LIMIT 1")
        except sqlite3.OperationalError:
            con.executescript(SCHEMA)
        # 1. Record / refresh currently-open stints.
        for key, rec in (current_il_by_key or {}).items():
            since = (rec or {}).get("since")
            if not since:
                # No placement date from the API — fall back to first-observed
                # date so the stint still gets a stable key.
                since = observed_date
            cur = con.execute(
                """INSERT INTO il_history
                     (player_key, since, il_type, description, placed_seen, activated_seen)
                   VALUES (?, ?, ?, ?, ?, NULL)
                   ON CONFLICT(player_key, since) DO UPDATE SET
                     il_type=excluded.il_type,
                     description=excluded.description,
                     -- a player reappearing on a stint we'd marked activated
                     -- means it never really ended; clear the activation.
                     activated_seen=NULL""",
                (key, since, (rec or {}).get("type"), (rec or {}).get("description"),
                 observed_date),
            )
            if cur.rowcount:
                placed += 1
        # 2. Close out stints whose player is no longer on the IL.
        current_keys = set(current_il_by_key or {})
        open_rows = con.execute(
            "SELECT player_key, since FROM il_history WHERE activated_seen IS NULL"
        ).fetchall()
        for r in open_rows:
            if r["player_key"] not in current_keys:
                con.execute(
                    "UPDATE il_history SET activated_seen = ? "
                    "WHERE player_key = ? AND since = ? AND activated_seen IS NULL",
                    (observed_date, r["player_key"], r["since"]),
                )
                activated += 1
    return {"placed": placed, "activated": activated}


def load_il_history(player_key: str | None = None) -> list[dict]:
    """Return IL stint rows (placement + activation timeline), newest first."""
    sql = ("SELECT player_key, since, il_type, description, placed_seen, "
           "activated_seen FROM il_history")
    params: list = []
    if player_key is not None:
        sql += " WHERE player_key = ?"; params.append(player_key)
    sql += " ORDER BY since DESC"
    try:
        with connect() as con:
            rows = con.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Headshot context cache (player_photos) — added 2026-06.
# ---------------------------------------------------------------------------
def load_photo_ctx() -> dict[int, str]:
    """Return {mlbam_id: headshot_ctx} for every resolved photo."""
    try:
        with connect() as con:
            rows = con.execute("SELECT mlbam_id, headshot_ctx FROM player_photos").fetchall()
    except sqlite3.OperationalError:
        return {}
    return {int(r["mlbam_id"]): r["headshot_ctx"] for r in rows}


def load_photo_meta() -> dict[int, str]:
    """Return {mlbam_id: checked_at_iso} so the resolver can TTL-skip fresh rows."""
    try:
        with connect() as con:
            rows = con.execute("SELECT mlbam_id, checked_at FROM player_photos").fetchall()
    except sqlite3.OperationalError:
        return {}
    return {int(r["mlbam_id"]): r["checked_at"] for r in rows}


def load_mlbam_player_keys() -> dict[str, str]:
    """Return {mlbam_id(str): player_key} from player_photos — the available
    MLBAM->eephus-key index. Used by the TJStats ingest for the exact-id join
    (name-slug is the fallback). Keys are strings to match scraped payloads."""
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT mlbam_id, player_key FROM player_photos "
                "WHERE player_key IS NOT NULL AND player_key <> ''"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {str(r["mlbam_id"]): r["player_key"] for r in rows}


def known_player_keys() -> set[str]:
    """Every player_key eephus already knows (the players table). The TJStats
    ingest logs any scraped player whose resolved key is NOT in here as a
    fall-through for manual review."""
    try:
        with connect() as con:
            return {r[0] for r in con.execute("SELECT player_key FROM players").fetchall()}
    except sqlite3.OperationalError:
        return set()


def upsert_photo_ctx(by_id: dict[int, dict]) -> int:
    """Upsert resolved headshot contexts. by_id = {mlbam_id: {ctx, player_key}}."""
    n = 0
    with connect() as con:
        for mid, rec in by_id.items():
            if mid is None or not rec or not rec.get("ctx"):
                continue
            con.execute(
                """INSERT INTO player_photos (mlbam_id, headshot_ctx, player_key, checked_at)
                   VALUES (?, ?, ?, datetime('now'))
                   ON CONFLICT(mlbam_id) DO UPDATE SET
                     headshot_ctx = excluded.headshot_ctx,
                     player_key   = COALESCE(excluded.player_key, player_photos.player_key),
                     checked_at   = excluded.checked_at""",
                (int(mid), rec["ctx"], rec.get("player_key")),
            )
            n += 1
    return n


def bind_player_ids(ids_by_key: dict[str, int]) -> int:
    """Persist freshly-resolved {player_key: mlbam_id} into player_photos.

    player_photos is the canonical, durable mlbam_id <-> player_key table, and
    the export's LAST-RESORT id source (see the note in the timeseries builder).
    Resolution previously lived only in the .cache id map, which the export
    cannot see: `--rebuild-only` passes an empty player_ids map, so a row with
    no current-season statline and no photo binding published `mlbam_id: null`
    even though the pipeline had just resolved it.

    That is what left the 2026 draft class unidentifiable on the board after
    their ids were recovered - they had no statline yet and no binding, so the
    id evaporated between the resolve step and the export. Binding here makes
    the resolution outlive the cache.

    The binding is guarded in BOTH directions, because a binding is a pair and
    either half can already be spoken for:

      * a KEY already bound to a different id is the ambiguous C2 class in
        identity_audit, and guessing there is how two people get fused;
      * an ID already bound to a different key is the same error mirrored, and
        it used to get through. The key-side guard passed for an unseen key,
        and then `ON CONFLICT(mlbam_id) DO UPDATE SET player_key = COALESCE(
        excluded.player_key, ...)` repointed the id, because excluded.player_key
        is never null here so the COALESCE could only ever choose the incoming
        key. Measured live while wiring the draft-time id seeding: MLBAM 814385
        belongs to `jackson_natili`, the draft feed spells the same pick
        `jack_natili`, and an unguarded harvest MOVED the id onto the draft
        slug - silently taking the identity away from the row that had it.

    The SQL now refuses the repoint on its own (the DO UPDATE only fires on a
    row whose player_key IS NULL, i.e. a photo-context row with no owner yet),
    so a future caller that forgets the python guard still cannot corrupt an
    existing binding. Both halves are deliberate: the python guard makes the
    skip observable and countable, the SQL guard makes it impossible.
    """
    if not ids_by_key:
        return 0
    n = 0
    with connect() as con:
        rows = con.execute(
            "SELECT player_key, mlbam_id FROM player_photos "
            "WHERE player_key IS NOT NULL").fetchall()
        existing = {r[0]: r[1] for r in rows}          # key -> id
        owner_of = {int(r[1]): r[0] for r in rows if r[1] is not None}   # id -> key
        for key, mid in ids_by_key.items():
            if not key or mid is None:
                continue
            prior = existing.get(key)
            if prior is not None:
                continue                      # key already bound (same id or ambiguous)
            owner = owner_of.get(int(mid))
            if owner is not None and owner != key:
                continue                      # id belongs to another key, do not steal it
            # headshot_ctx is NOT NULL, and 'milb' is the provisional default
            # the snapshot path already uses when it binds a prospect id. The
            # real context is resolved later by headshots.resolve_ctx and
            # written through upsert_photo_ctx; this row only has to carry the
            # id<->key binding until then.
            con.execute(
                """INSERT INTO player_photos (mlbam_id, headshot_ctx, player_key)
                   VALUES (?, 'milb', ?)
                   ON CONFLICT(mlbam_id) DO UPDATE SET
                     player_key = excluded.player_key
                   WHERE player_photos.player_key IS NULL""",
                (int(mid), key),
            )
            n += 1
    return n


def load_career_stats_meta() -> dict[str, str]:
    """Return {player_key: fetched_at_iso} for every stored career_stats row.

    Used by the monthly pipeline to TTL-skip refetching career stats for
    prospects whose cached row is still fresh.
    """
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, fetched_at FROM career_stats"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["player_key"]: r["fetched_at"] for r in rows}


def start_run() -> int:
    with connect() as con:
        cur = con.execute(
            "INSERT INTO runs (started_at) VALUES (?)",
            (_utcnow_iso(),),
        )
        return cur.lastrowid


def finish_run(run_id: int, new_snapshots: int, stat_lines: int, notes: str = ""):
    with connect() as con:
        con.execute(
            """UPDATE runs SET finished_at = ?, new_snapshots = ?, stat_lines = ?, notes = ?
               WHERE id = ?""",
            (_utcnow_iso(),
             new_snapshots, stat_lines, notes, run_id),
        )
    # End-of-run maintenance (finding [21]): truncate the WAL (always) and,
    # only when explicitly opted in via PROSPECTS_DB_VACUUM=1, VACUUM to reclaim
    # deleted-row slack. Run AFTER the writer connection above has closed so the
    # checkpoint has no open transaction to contend with. Best-effort.
    _checkpoint_and_maybe_vacuum()


def latest_run_summary() -> dict | None:
    try:
        with connect() as con:
            row = con.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        # Table doesn't exist yet — fine for first run or test isolation.
        return None


def data_freshness() -> dict:
    """Return the two-track freshness stamps the site uses for data-aware
    'as of' labels:

      • grades_updated_at  — finish time of the last MONTHLY run (full
        pipeline: grades, tool evals, Arkmetrics, farm grades, rankings).
      • transactions_updated_at — finish time of the last run of ANY kind
        (a daily run refreshes transactions/IL/roster; a monthly run does
        both, so the latest run always reflects the freshest fast-moving
        data).
      • last_run_kind — 'daily' | 'monthly' for the most recent run.

    Daily runs are tagged with a notes prefix of 'DAILY:' by run_daily();
    everything else is treated as a monthly/full run.
    """
    out = {"grades_updated_at": None, "transactions_updated_at": None,
           "last_run_kind": None}
    try:
        with connect() as con:
            latest = con.execute(
                "SELECT finished_at, started_at, notes FROM runs "
                "WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
            monthly = con.execute(
                "SELECT finished_at, started_at FROM runs "
                "WHERE finished_at IS NOT NULL "
                "AND COALESCE(notes,'') NOT LIKE 'DAILY:%' "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
    except sqlite3.OperationalError:
        return out
    if latest:
        out["transactions_updated_at"] = latest["finished_at"] or latest["started_at"]
        out["last_run_kind"] = ("daily" if (latest["notes"] or "").startswith("DAILY:")
                                else "monthly")
    if monthly:
        out["grades_updated_at"] = monthly["finished_at"] or monthly["started_at"]
    return out


# ---------------------------------------------------------------------------
# Farm-system grading
# ---------------------------------------------------------------------------
# Ingest health: "we successfully checked this source" (NOT FA-specific)
# ---------------------------------------------------------------------------
# Deliberately ABOVE the FA section: source_checks is general ingestion
# infrastructure that the scraper lane also writes, and the FA block is
# pinned by test_fa_readonly_prospx to touch fa_* tables ONLY. Leaving these
# two inside it broke that isolation guard, which is exactly what the guard
# is for.
def record_source_check(source: str, scope: str = "", n_rows: int | None = None) -> None:
    """Record that `source` was successfully checked just now.

    Call this ONLY on a verified-good check. A parse that returned nothing
    because the upstream layout changed must NOT call it - leaving the old
    stamp in place is exactly how the UI notices."""
    with connect() as con:
        con.execute(
            "INSERT INTO source_checks (source, scope, checked_at, n_rows) "
            "VALUES (?, ?, datetime('now'), ?) "
            "ON CONFLICT(source, scope) DO UPDATE SET "
            "checked_at = excluded.checked_at, n_rows = excluded.n_rows",
            (source, scope or "", n_rows))


def load_source_checks() -> dict[tuple[str, str], dict]:
    """{(source, scope): {checked_at, n_rows}}. Empty on a fresh DB."""
    out: dict[tuple[str, str], dict] = {}
    try:
        with connect() as con:
            for src, scope, at, n in con.execute(
                    "SELECT source, scope, checked_at, n_rows FROM source_checks"):
                out[(src, scope or "")] = {"checked_at": at, "n_rows": n}
    except Exception:                                    # noqa: BLE001 - best effort
        pass
    return out


# ---------------------------------------------------------------------------
# Each org gets a report card with four component scores plus an overall
# letter grade. The previous system (60% total_fv + 30% 90-day delta + 10%
# grad count) had three problems we explicitly fix here:
#
#   1. Raw total_fv treats a 35 FV org-filler the same as a real prospect.
#      → Replaced with tiered FV-to-points (an 80 is worth ~100x a 40).
#
#   2. 90-day delta was dominated by whichever single source happened to
#      update inside the window — a noisy proxy for "trajectory".
#      → Replaced with a smoothed mean-of-recent vs mean-near-cutoff
#        comparison that survives any one source's swing.
#
#   3. Recent grad count was binary — graduating Roki Sasaki counted the
#      same as graduating a 40 FV bench bat.
#      → Replaced with FV-weighted grads in the last 12 months.
#
# Component scores (each rescaled to a 0-100 scale across the 30 orgs):
#   * top_end_points — sum of tiered points for the org's top 5 prospects
#                      (45% weight, the dominant signal)
#   * depth_points   — sum of tiered points for prospects #6-25  (25%)
#   * trajectory     — smoothed change in cumulative FV           (15%)
#   * grad_pipeline  — FV-weighted graduations in trailing 12 mo  (15%)
#
# The four 0-100 scores blend linearly into a `farm_score`; the overall
# letter grade is the bucket that score lands in among the 30 orgs.

FARM_TRAJECTORY_LOOKBACK_DAYS = 365
FARM_TRAJECTORY_SMOOTH_WINDOW = 3   # avg last 3 fv_history points vs 3 near cutoff
FARM_GRAD_PIPELINE_MONTHS     = 12

# Multi-window trajectories. The farm pages let the user toggle between these
# to ask "who's been developing prospects best over the last X?". Every window
# here is baked per-org (DvM+ + the per-window composite farm_score), so the
# frontend selector can switch the WHOLE grade tree to any of these windows.
# Empirically validated: a 7-year trailing window predicts realized graduate
# output best (beats 6y in all 4 backtest vintages; 8y regresses) — see the
# window-sweep analysis. 7y is therefore the principal (default) window.
FARM_TRAJECTORY_WINDOWS = {
    "1y": 365,
    "2y": 365 * 2,
    "3y": 365 * 3,
    "4y": 365 * 4,
    "5y": 365 * 5,
    "6y": 365 * 6,
    "7y": 365 * 7,
    "8y": 365 * 8,
}

# The principal (default) trailing window — the empirically-optimal window the
# farm grade tree anchors on (composite letter, DvM+ headline, tiebreaker). The
# user-facing window selector defaults here and can switch to any baked window.
# ONE constant so every windowed grade/subgrade shares the same default.
FARM_PRINCIPAL_WINDOW = "7y"
# Windows offered in the frontend selector (subset of FARM_TRAJECTORY_WINDOWS).
FARM_SELECTABLE_WINDOWS = ["3y", "4y", "5y", "6y", "7y", "8y"]

# DvM+ weighted by development difficulty (owner ask 6, 2026-09-30; DVM-5 of the Part 8
# dvm_difficulty lane; gate docs/dvm-difficulty-2026-09-30/DVM_DIFFICULTY_GATE.md).
# None (every build until the owner's flip, DVM-6) leaves every DvM+ field byte-identical
# to the FV-trajectory method above: nothing below runs, nothing is imported and
# data/dvm_difficulty.json is never read. "value" serves DV (each step's expected-WAR value
# growth minus what players with the same origin, starting grade, age, level and source
# usually gain; owner answer Q-DVM-2 A) and "difficulty" serves D0 (the same growth in
# units of its starting rung's spread). The flip needs the look's pass, the fWAR epoch's
# step Z and the owner; test_dvm_flag_identity.py pins None.
DVM_DIFFICULTY_ARM: str | None = None
DVM_DIFFICULTY_ARMS = ("value", "difficulty")
# Gate section 7: a club-window cell is shown only with a Kish effective n of 10 or more;
# below that the page prints " - " (the value still enters the farm grade, shrunk).
DVM_DIFFICULTY_MIN_PUBLISH_N = 10.0
# Gate section 9: the player index reads the last 3 annual steps, shrunk n / (n + 2).
DVM_DIFFICULTY_PLAYER_STEPS = 3
DVM_DIFFICULTY_PLAYER_SHRINK_K = 2.0
_DVM_DIFF_BUCKETS = ("C", "INF", "OF", "SP", "RP")


def _dvm_round_nearest(x: float) -> int:
    """Plus stats round to nearest, halves up (the lab's round_nearest)."""
    import math as _m
    return int(_m.floor(float(x) + 0.5))


def _dvm_window_end_years(as_of: str, windows: dict) -> dict[str, list[int]]:
    """The preseason step years each trailing window holds (Q-DVM-5 A, annual steps): a
    step ends with its end list's preseason window, which closes May 1, so the last
    closed step is this year's on or after May 1 and last year's before it. A W-year
    window holds the last W closed steps."""
    d = date.fromisoformat(str(as_of)[:10])
    last = d.year if d >= date(d.year, 5, 1) else d.year - 1
    out = {}
    for key, days in windows.items():
        n = max(1, int(round(int(days) / 365)))
        out[key] = list(range(last - n + 1, last + 1))
    return out


def _dvm_club_aggregate(rows: list[dict], credit: str, k_org: float,
                        clubs: Iterable[str]) -> dict[str, dict]:
    """Gate section 7 per club: D_o, the tau x omega weighted mean credit; N_o, its Kish
    effective n; D~_o = D_o N_o / (N_o + k_org). A club with no step enters at 0, N 0."""
    acc: dict[str, list[tuple[float, float, dict]]] = {}
    for r in rows:
        for club, t in (r.get("tau") or {}).items():
            if t and t > 0:
                acc.setdefault(club, []).append((float(t) * float(r["omega"]),
                                                 float(r[credit]), r))
    out: dict[str, dict] = {}
    for club in sorted(set(clubs) | set(acc)):
        items = acc.get(club) or []
        sa = sum(a for a, _x, _r in items)
        sa2 = sum(a * a for a, _x, _r in items)
        D = (sum(a * x for a, x, _r in items) / sa) if sa > 0 else 0.0
        N = (sa * sa / sa2) if sa2 > 0 else 0.0
        out[club] = {"D": D, "N": N, "D_shrunk": (D * N / (N + k_org)) if N > 0 else 0.0,
                     "sum_a": sa, "items": items}
    return out


def _dvm_plus_of(values: dict[str, float]) -> dict[str, int]:
    """100 + 10 (x - mean) / sd across the given clubs (population sd, as the served
    DvM+), unclamped, rounded to nearest; a flat field reads 100."""
    if not values:
        return {}
    xs = list(values.values())
    mu = sum(xs) / len(xs)
    sd = (sum((x - mu) ** 2 for x in xs) / len(xs)) ** 0.5
    return {k: _dvm_round_nearest(100 + 10 * ((v - mu) / sd if sd > 1e-12 else 0.0))
            for k, v in values.items()}


def _dvm_mix(items: list[tuple[float, float, dict]]) -> dict:
    """The farm's mix in a window, weighted tau x omega: origin, starting rung and level
    shares and the mean age for level (the inputs the expectation conditions on)."""
    tot = sum(a for a, _x, _r in items)
    if tot <= 0:
        return {"origin": {}, "rung": {}, "level": {}, "mean_age_rel": None}
    shares: dict[str, dict[str, float]] = {"origin": {}, "rung": {}, "level": {}}
    age_num = age_den = 0.0
    for a, _x, r in items:
        for k in shares:
            lab = str(r.get(k) or "unknown")
            shares[k][lab] = shares[k].get(lab, 0.0) + a
        if r.get("age_rel") is not None:
            age_num += a * float(r["age_rel"])
            age_den += a
    return {k: {lab: round(v / tot, 3) for lab, v in sorted(m.items())}
            for k, m in shares.items()} | {
        "mean_age_rel": round(age_num / age_den, 2) if age_den > 0 else None}


def _build_org_dev_residuals(fv_rows: list[dict], tool_rows: dict[str, list[dict]], *,
                             table: dict, arm: str, as_of: str, clubs: Iterable[str],
                             bucket_of: dict[str, str | None], actives: Iterable[str],
                             windows: dict | None = None,
                             tool_group_traits: dict | None = None) -> dict:
    """The difficulty-adjusted DvM+ family from the scored steps (dvm_difficulty_serve.
    score) and the frozen table: per club and window dvm_plus, delta_above_mean (now
    growth above expected), the hitter and pitcher and C / INF / OF / SP / RP versions,
    a dev_expectation block (actual, expected for this farm's mix, the gap, n, the mix);
    per club the per-tool DvM+ and its bucket cells (principal window, tool residuals in
    spread units, no FV-to-WAR transform, no level weight, no stretch: gate section 8);
    and the player index that replaces $DvM+ (section 9). Pure: reads only its inputs."""
    if arm not in DVM_DIFFICULTY_ARMS:
        raise ValueError(f"unknown DVM_DIFFICULTY_ARM {arm!r}")
    windows = windows or FARM_TRAJECTORY_WINDOWS
    clubs = sorted(clubs)
    credit = "v" if arm == "value" else "z"
    k_tab = (table.get("k_org") or {})
    k_org = float(((k_tab.get("DV" if arm == "value" else "D0")) or {}).get("k_org") or 50.0)
    end_years = _dvm_window_end_years(as_of, windows)
    by_org: dict[str, dict] = {c: {"dvm_plus": {}, "delta_above_mean": {},
                                   "hitter_dvm_plus": {}, "pitcher_dvm_plus": {},
                                   "hitter_delta_above_mean": {},
                                   "pitcher_delta_above_mean": {},
                                   "pos_bucket_fv_dvm_plus": {b: {} for b in _DVM_DIFF_BUCKETS},
                                   "dev_expectation": {}} for c in clubs}

    def _stamp(rows, val_key, delta_key):
        agg = _dvm_club_aggregate(rows, credit, k_org, clubs)
        vals = {c: agg[c]["D_shrunk"] for c in clubs}
        plus = _dvm_plus_of(vals)
        mu = sum(vals.values()) / len(vals) if vals else 0.0
        for c in clubs:
            by_org[c][val_key][win] = plus.get(c, 100)
            if delta_key:
                by_org[c][delta_key][win] = round(vals[c] - mu, 4)
        return agg

    for win in windows:
        yrs = set(end_years[win])
        rows_w = [r for r in fv_rows if int(r["step_end"]) in yrs]
        agg = _stamp(rows_w, "dvm_plus", "delta_above_mean")
        _stamp([r for r in rows_w if r["side"] == "hit"], "hitter_dvm_plus",
               "hitter_delta_above_mean")
        _stamp([r for r in rows_w if r["side"] == "pit"], "pitcher_dvm_plus",
               "pitcher_delta_above_mean")
        for b in _DVM_DIFF_BUCKETS:
            sub = [r for r in rows_w if bucket_of.get(r["pk"]) == b]
            ab = _dvm_club_aggregate(sub, credit, k_org, ())
            present = {c: ab[c]["D_shrunk"] for c in clubs if c in ab and ab[c]["N"] > 0}
            plus = _dvm_plus_of(present)
            for c in clubs:
                by_org[c]["pos_bucket_fv_dvm_plus"][b][win] = plus.get(c)
        for c in clubs:
            a = agg[c]
            items = a["items"]
            sa = a["sum_a"]
            if arm == "value":
                actual = (sum(t * float(r["w"]) for t, _x, r in items) / sa) if sa > 0 else None
                gap = a["D"] if sa > 0 else None
            else:
                actual = (sum(t * float(r["y"]) for t, _x, r in items) / sa) if sa > 0 else None
                gap = ((sum(t * float(r["z"]) * float(r["s_hat"]) for t, _x, r in items) / sa)
                       if sa > 0 else None)
            by_org[c]["dev_expectation"][win] = {
                "actual": None if actual is None else round(actual, 3),
                "expected": None if actual is None else round(actual - gap, 3),
                "residual": None if gap is None else round(gap, 3),
                "credit": round(a["D"], 4), "credit_shrunk": round(a["D_shrunk"], 4),
                "n_eff": round(a["N"], 1), "pairs": len(items),
                "publish": a["N"] >= DVM_DIFFICULTY_MIN_PUBLISH_N,
                "step_years": sorted(yrs),
                "mix": _dvm_mix(items),
            }

    # Per-tool pass: the principal window's tool residuals (gate section 8).
    groups = tool_group_traits or {}
    pyrs = set(end_years[FARM_PRINCIPAL_WINDOW])
    per_tool: dict[str, dict] = {c: {} for c in clubs}
    per_tool_b: dict[str, dict] = {c: {b: {} for b in _DVM_DIFF_BUCKETS} for c in clubs}

    def _tool_plus(rows, k):
        ag = _dvm_club_aggregate(rows, "z", k, ())
        present = {c: ag[c]["D_shrunk"] for c in clubs if c in ag and ag[c]["N"] > 0}
        return _dvm_plus_of(present) if len(present) >= 2 else {}

    for grp in TOOL_GROUPS:
        traits = groups.get(grp) or ()
        rows = [r for t in traits for r in (tool_rows.get(t) or [])
                if int(r["step_end"]) in pyrs]
        ks = [float(((k_tab.get(f"tool|{r_side}|{t}")) or {}).get("k_org") or 50.0)
              for t in traits for r_side in ("hit", "pit")
              if f"tool|{r_side}|{t}" in k_tab]
        k = sum(ks) / len(ks) if ks else 50.0
        plus = _tool_plus(rows, k) if rows else {}
        for c in clubs:
            per_tool[c][grp] = plus.get(c)
        for b in _DVM_DIFF_BUCKETS:
            pb = _tool_plus([r for r in rows if bucket_of.get(r["pk"]) == b], k) if rows else {}
            for c in clubs:
                per_tool_b[c][b][grp] = pb.get(c)

    # The player index (gate section 9): the player's own credits over his last 3 annual
    # steps, each step's sources weighted by omega, shrunk n / (n + 2), 100 + 10 x value
    # / sd across actives.
    steps: dict[str, dict[int, list[tuple[float, float]]]] = {}
    for r in fv_rows:
        steps.setdefault(r["pk"], {}).setdefault(int(r["step_end"]), []).append(
            (float(r["omega"]), float(r[credit])))
    shrunk = {}
    for pk, by_year in steps.items():
        last = sorted(by_year)[-DVM_DIFFICULTY_PLAYER_STEPS:]
        vals = []
        for yr in last:
            om = sum(o for o, _x in by_year[yr])
            vals.append(sum(o * x for o, x in by_year[yr]) / om if om > 0 else 0.0)
        n = len(vals)
        shrunk[pk] = (sum(vals) / n) * n / (n + DVM_DIFFICULTY_PLAYER_SHRINK_K) if n else 0.0
    act = [k for k in dict.fromkeys(actives) if k in shrunk]
    sd = 0.0
    if act:
        mu0 = sum(shrunk[k] for k in act) / len(act)
        sd = (sum((shrunk[k] - mu0) ** 2 for k in act) / len(act)) ** 0.5
    player_index = {k: _dvm_round_nearest(100 + 10 * (shrunk[k] / sd if sd > 0 else 0.0))
                    for k in act}

    for c in clubs:
        by_org[c]["per_tool_dvm_plus"] = per_tool[c]
        by_org[c]["per_tool_dvm_plus_by_bucket"] = per_tool_b[c]
    return {"arm": arm, "credit": credit, "k_org": k_org, "window_step_years": end_years,
            "by_org": by_org, "player_index": player_index,
            "n_steps": len(fv_rows), "n_tool_steps": {t: len(v) for t, v in tool_rows.items()}}


def _dvm_difficulty_result(*, attribution, as_of: str,
                           bucket_of: dict[str, str | None], actives: Iterable[str],
                           arm: str | None = None, con=None) -> dict | None:
    """The served arm's result, or None while DVM_DIFFICULTY_ARM is None (then nothing
    is imported and no artifact is read). With the arm on, the look's frozen table is
    required; a failure is logged and the FV-trajectory DvM+ stays served."""
    arm = DVM_DIFFICULTY_ARM if arm is None else arm
    if arm is None:
        return None
    try:
        import dvm_difficulty_serve as _dds
        table, ev = _dds.load_table()
        _dds.require_look_table(table)

        def _cal(pk):
            return attribution.calendar(pk) if attribution is not None else []
        own = con is None
        if own:
            con = sqlite3.connect(f"file:{Path(DB_PATH).as_posix()}?mode=ro", uri=True,
                                  timeout=30.0)
        try:
            pairs, census = _dds.serve_pairs(con, calendar_of=_cal, clubs=MLB_30_ORGS,
                                             player_keys=list(actives))
        finally:
            if own:
                con.close()
        fv_rows, tool_rows = _dds.score(pairs, table, arm)
        res = _build_org_dev_residuals(
            fv_rows, tool_rows, table=table, arm=arm, as_of=as_of, clubs=MLB_30_ORGS,
            bucket_of=bucket_of, actives=actives,
            tool_group_traits=_dds.TOOL_GROUP_TRAITS)
        res["census"] = census
        res["spec"] = _dds.spec_block(table, ev, arm, FARM_PRINCIPAL_WINDOW)
        log.info("DvM+ difficulty arm %s: %d steps, %d clubs", arm, len(fv_rows),
                 len(res["by_org"]))
        return res
    except Exception:
        log.exception("DvM+ difficulty arm %s failed; the FV-trajectory DvM+ stays served",
                      arm)
        return None


def _apply_dvm_difficulty_fv(org_summary: list[dict], res: dict | None) -> None:
    """Writes the arm's FV family over the trajectory method's, key for key, so the
    Development leaves, the 3-way blend, the tiebreaker and the windowed composite read it
    through their unchanged wiring; adds dev_expectation (the arm's own block). With no
    result (the arm None) it touches nothing."""
    if res is None:
        return
    for entry in org_summary:
        o = (res.get("by_org") or {}).get(entry.get("org"))
        if not o:
            continue
        for key in ("dvm_plus", "delta_above_mean", "hitter_dvm_plus", "pitcher_dvm_plus",
                    "hitter_delta_above_mean", "pitcher_delta_above_mean"):
            entry[key] = dict(o[key])
        entry["_pos_bucket_fv_dvm_plus"] = {b: dict(v) for b, v in o["pos_bucket_fv_dvm_plus"].items()}
        entry["dev_expectation"] = {"arm": res["arm"], "windows": o["dev_expectation"]}


def _apply_dvm_difficulty_tools(org_summary: list[dict], res: dict | None) -> None:
    """Writes the arm's per-tool DvM+ and its bucket cells over the league pass's, keys
    kept (per_tool_dvm_plus, per_tool_dvm_plus_by_bucket), before the composite
    ToolDvM+ (tools_dvm_plus) is formed from them as today. With no result it touches
    nothing."""
    if res is None:
        return
    for entry in org_summary:
        o = (res.get("by_org") or {}).get(entry.get("org"))
        if not o:
            continue
        td = entry.setdefault("tool_dev", {})
        td["per_tool_dvm_plus"] = {g: o["per_tool_dvm_plus"].get(g) for g in TOOL_GROUPS}
        td["per_tool_dvm_plus_by_bucket"] = {
            b: {g: cell.get(g) for g in TOOL_GROUPS}
            for b, cell in o["per_tool_dvm_plus_by_bucket"].items()}

# The per-bucket DvM+ development blend (_blend_dvm_3way inside
# export_timeseries_json). FV-DvM+ and Tool-DvM+ share one slice, Statcast
# DvM+ takes the rest. Inside the slice Tool takes the baseline share; when
# FV-DvM+ leads Tool-DvM+ by PENALTY_GAP_START points or more the Tool share
# ramps from PENALTY_START (1 point of share per point of gap) to PENALTY_CAP
# at PENALTY_GAP_CAP. Named here so the payload (farm_dev_spec) and the
# PROSPX copy read the same numbers the blend runs on.
FARM_DVM_FV_TOOL_SHARE            = 0.75
FARM_DVM_STATCAST_SHARE           = 0.25
FARM_DVM_TOOL_SHARE_IN_SLICE      = 0.30
FARM_DVM_TOOL_PENALTY_GAP_START   = 15
FARM_DVM_TOOL_PENALTY_GAP_CAP     = 35
FARM_DVM_TOOL_SHARE_PENALTY_START = 0.40
FARM_DVM_TOOL_SHARE_PENALTY_CAP   = 0.60


def farm_dev_spec(dvm_difficulty: dict | None = None) -> dict:
    """The constants behind the farm Development copy, served in the PROSPX boot
    payload as `farm_dev_spec` so the Development tab names the principal window
    and the blend weights from the code instead of typing them. Nothing here is a
    measured number; changing a constant above changes the copy with it.
    `dvm_difficulty` is the arm's explainer block (dvm_difficulty_serve.spec_block),
    added only while DVM_DIFFICULTY_ARM is on; with None the payload is unchanged."""
    spec = {
        "principal_window": FARM_PRINCIPAL_WINDOW,
        "dvm_blend": {
            "fv_tool_share":            FARM_DVM_FV_TOOL_SHARE,
            "statcast_share":           FARM_DVM_STATCAST_SHARE,
            "tool_share_in_slice":      FARM_DVM_TOOL_SHARE_IN_SLICE,
            "penalty_gap_start":        FARM_DVM_TOOL_PENALTY_GAP_START,
            "penalty_gap_cap":          FARM_DVM_TOOL_PENALTY_GAP_CAP,
            "tool_share_penalty_start": FARM_DVM_TOOL_SHARE_PENALTY_START,
            "tool_share_penalty_cap":   FARM_DVM_TOOL_SHARE_PENALTY_CAP,
        },
    }
    if dvm_difficulty:
        spec["dvm_difficulty"] = dvm_difficulty
    return spec

FARM_TOP_END_COUNT  = 5             # top N prospects feeding the "stars" score
FARM_DEPTH_START    = 5             # prospects #6 ...
FARM_DEPTH_END      = 25            # ... through #25 feed the "depth" score

# Farm-score blend weights — 10 components, sum to 1.0. The "big-4"
# (Top-End + Depth + DvM+ + Grad Pipeline) still control ~70%; WAG and
# Financial ROI add the MLB-impact lens (~18%); the three "Profile"
# components (Tool Quality / IFA depth / Readiness / Health) provide
# secondary signal worth a combined ~12%. DvM+ REPLACED the raw
# Trajectory weight (DvM+ is the z-scored, league-mean-anchored
# version of the same delta — strictly more informative).
# v16 — Heavy upside tilt. Top-end FV pyramid + 6yDvM+ + MLB Production
# carry 70% of the score. The principle: tail-end outcomes (stars,
# elite tools) drive farm-system value far more than the median
# prospect's quality. An org that develops one Skenes/Caminero/Crews-
# tier ceiling matters more than an org that has the deepest pool of
# FV-40 org soldiers. Depth still matters (10%) but no longer dominates.
FARM_WEIGHT_TOP_END             = 0.32   # v16 — was 0.24
FARM_WEIGHT_DVM_PLUS            = 0.20   # v16 — was 0.18 (heavily 6y-anchored
                                         # inside the dev score)
FARM_WEIGHT_TALENT_TRANSLATION  = 0.18   # v16 — was 0.10 (MLB production
                                         # rolls in here via per-grad WAG mean)
FARM_WEIGHT_DEPTH               = 0.10   # v16 — was 0.16
FARM_WEIGHT_GRAD                = 0.10   # v16 — was 0.12
FARM_WEIGHT_FINANCIAL_ROI       = 0.05   # v16 — was 0.08
FARM_WEIGHT_TOOLS_QUALITY       = 0.03   # v16 — was 0.06
FARM_WEIGHT_INTL_DEPTH          = 0.01   # v16 — was 0.03
FARM_WEIGHT_READINESS           = 0.005  # v16 — was 0.02
FARM_WEIGHT_HEALTH              = 0.005  # v16 — was 0.01
# Back-compat alias — kept so external imports don't break. The blend
# no longer uses FARM_WEIGHT_TRAJECTORY directly; DvM+ took its slot.
FARM_WEIGHT_TRAJECTORY  = FARM_WEIGHT_DVM_PLUS

# ────────────────────────────────────────────────────────────────────────
# Farm Grade Tree (v2 composite — replaces the flat 10-component blend)
#
# Five main grades, each composed of 2 sub-grades, rolling into one
# composite. Weighted by signal strength: Development (controllable
# skill) and MLB Production (outcome proof) carry the most weight;
# Transactions is intentionally light because trade-acumen signal is
# real but small-sample. See `farm_report_card` glossary entry for the
# full tree shape.
# ────────────────────────────────────────────────────────────────────────

# Canonical 30-MLB-org allowlist. Anything outside this set is dropped
# from org_summary at export time. Phantom orgs like "Office of the
# Commissioner", null/empty orgs, or stray minor-league affiliate codes
# that leak through transactions/rosters get filtered so the farm page
# always shows exactly 30 orgs. Keep alphabetical so visual diff is
# easy when MLB ever adds an expansion team.
MLB_30_ORGS: set[str] = {
    "ARI", "ATH", "ATL", "BAL", "BOS",
    "CHC", "CHW", "CIN", "CLE", "COL",
    "DET", "HOU", "KCR", "LAA", "LAD",
    "MIA", "MIL", "MIN", "NYM", "NYY",
    "PHI", "PIT", "SDP", "SEA", "SFG",
    "STL", "TBR", "TEX", "TOR", "WSN",
}
# v9 weights — Development promoted to clear majority (55%); MLB
# Production trimmed (20% → 15%) to free that room. Per-user: a strong
# 6yDvM+ + Tool DvM+ profile should win the rank even when an org has
# weaker realized MLB production. The Rays' 6yDvM+ 129 + 120.3 dev
# branch score wasn't beating the Mariners' 100.6 dev + 114.8 mlb-prod
# at the old 45/20 split — flipping that requires shifting weight TO
# the axis the org controls and AWAY from the lagging-indicator axis.
# Financial drops 25% → 20% to absorb the rest of the shift;
# Acquisition Strategy unchanged.
# Weights sum to 1.00.
# v40 — VALUE-TRACKING REWEIGHT. The grade is now PRIMARILY driven by aggregate
# risk-adjusted controlled surplus (the Financial branch, reframed as "Value" in the
# UI). The prior split (Development 0.50, Financial 0.18) made the grade a per-prospect
# tool-development index decoupled from aggregate value: a farm could be 3rd in total
# surplus (TBR, $264M) yet grade 15th, below a 25th-in-surplus farm (NYM). Aggregate
# surplus already prices elite ceiling non-linearly (the recalibrated value_framework),
# so it captures top-end-vs-depth on its own — no opaque top-heavy weighting. MLB
# Production rises (realized graduate WAR proof); Development drops to a secondary
# controllable-skill signal. Sum = 1.00.
FARM_TREE_WEIGHT_ACQUISITION_STRATEGY = 0.08    # v40: 0.12 → 0.08
FARM_TREE_WEIGHT_DEVELOPMENT          = 0.09    # v40: 0.50 → 0.09 (secondary skill signal)
FARM_TREE_WEIGHT_FINANCIAL            = 0.65    # v40: 0.18 → 0.65 (the Value branch — DOMINANT)
FARM_TREE_WEIGHT_MLB_PRODUCTION       = 0.18    # v40: 0.20 → 0.18 (raw graduate WAR — secondary check)
# Back-compat aliases — anything that imported the v2 constants still
# works. The composite blend below uses the v3 names exclusively.
FARM_TREE_WEIGHT_ACQUISITIONS = FARM_TREE_WEIGHT_ACQUISITION_STRATEGY
FARM_TREE_WEIGHT_TRANSACTIONS = 0.0   # rolled into Acquisition Strategy
# Sub-grades inside each parent — 50/50 for all parents in v1.
FARM_TREE_SUB_WEIGHT_EQUAL = 0.5

# v32.1 — Per-leaf weights for the Financial branch. active_surplus
# promoted 0.35 → 0.40 now that it's the most defensible signal on the
# axis (re-derived through value_framework's transparent FV→WAR×$/WAR
# formula, with fast-cycle surplus_per_fv_pt_mm joining as a graded
# sub-input). contract_surplus trimmed 0.25 → 0.20 in exchange. The
# pure-ROI leaves (war_per_m, draft_pool, IFA) hold the lower weights;
# draft_pool itself now blends war_per_m_pool + fv_per_m_pool internally
# so it's denser per-leaf without changing the leaf weight. Weights
# normalize to 1.0 across present leaves at compute time, so a sparse-
# data org just weighted-means whatever leaves it has.
FARM_LEAF_WEIGHTS = {
    # v38 — Item-7 reweight. Now that surplus value is re-derived through the
    # transparent value_framework FV→WAR×$/WAR core AND $DvM+ adds a
    # development-trajectory lens, the surplus grades carry more of the
    # financial axis and the simpler per-$ ROI leaves (war_per_m,
    # draft_pool_efficiency, ifa_roi) — which $DvM+ now partly supersedes as a
    # forward "are these prospects appreciating?" signal — are trimmed.
    #   fin_active_surplus   0.40 → 0.42   (↑ surplus)
    #   fin_dollar_dvm       NEW    0.18   (surplus-dev vs FV-tier mean)
    #   fin_contract_surplus 0.20 → 0.18
    #   fin_war_per_m        0.10 → 0.07   (↓ superseded ROI)
    #   fin_draft_pool_eff   0.15 → 0.08   (↓ superseded ROI)
    #   fin_ifa_roi          0.15 → 0.07   (↓ superseded ROI)
    # Sum = 1.00. (Weights renormalize across present leaves at compute time,
    # so a sparse-data org just weighted-means whatever leaves it has.)
    # v40 — Value branch leaf weights. fin_active_surplus (now AGGREGATE controlled
    # surplus, not per-prospect) is the dominant leaf; the value-development +
    # per-$ ROI leaves provide secondary texture. Sum = 1.00.
    "financial": {
        "fin_active_surplus":        0.68,   # v40: AGGREGATE controlled value — dominant
        "fin_dollar_dvm":            0.10,
        "fin_contract_surplus":      0.10,
        "fin_war_per_m":             0.04,
        "fin_draft_pool_efficiency": 0.04,
        "fin_ifa_roi":               0.04,
    },
}

# Tiered FV → points. v4 (2026-05) steepened curve — each tier above 50
# is ~1.7-2× the previous, so an 80 is worth ~250 org-fillers and a 70
# is worth ~120. The old curve was too flat at the top (a 70 was only
# 3× a 50) and didn't properly reward orgs producing star-tier
# prospects relative to depth-only systems. The bottom tail (35-45)
# flattens further so a single 35-FV org-filler contributes near zero.
# `_fv_to_points` linearly interpolates within tiers so a 57.5 still
# maps cleanly between the 55 and 60 anchors.
FV_POINTS = {
    80: 250.0,    # franchise piece — Skenes / Trout tier
    75: 160.0,
    70: 120.0,    # bona fide All-Star
    65:  75.0,
    60:  35.0,    # everyday regular
    55:  18.0,
    50:   8.0,    # MLB average
    45:   3.5,
    40:   1.0,    # org-filler
    35:   0.3,
    30:   0.1, 25: 0.05, 20: 0.0,
}


def _fv_to_points(fv: float | int | None) -> float:
    """Tiered FV → points. Interpolates linearly between tier boundaries so
    a 57.5 (between 55 and 60) returns the midpoint between FV_POINTS[55]
    and FV_POINTS[60]. Returns 0.0 for None / sub-20 inputs."""
    if fv is None:
        return 0.0
    try:
        v = float(fv)
    except (TypeError, ValueError):
        return 0.0
    if v <= 20:
        return 0.0
    if v >= 80:
        return FV_POINTS[80]
    lo = int(v // 5) * 5
    hi = lo + 5
    lo_pts = FV_POINTS.get(lo, 0.0)
    hi_pts = FV_POINTS.get(hi, lo_pts)
    frac = (v - lo) / 5.0
    return round(lo_pts + (hi_pts - lo_pts) * frac, 3)


# ═══════════════════════════════════════════════════════════════════════════
# THE BOARD NUMBER — single definition. Do not add a second one.
# ═══════════════════════════════════════════════════════════════════════════
# The PROSPX board has exactly ONE number: the RAW eFV grade, data/xfv.json
# `xfv_grade`. It is simultaneously (a) the value displayed on the board, (b)
# the sort key, and (c) the basis of `overall_rank` / `org_rank`. Because the
# displayed value IS the sort key, the visible grade column is monotonic by
# construction and the rendered row position can never disagree with the
# `overall_rank` field.
#
# PROVENANCE / why this constant exists
#   2026-07-06  the DISPLAY flipped to xfv_grade_quantile but overall_rank was
#               left on another key.
#   2026-07-15  a unification pass moved the SORT onto the quantile too and
#               again left the rank field behind, so three orderings coexisted:
#               rendered order (quantile), timeseries overall_rank, and
#               live_overall_rank. The owner hit it twice ("why is Arias no
#               longer #1", "why is Cholowsky #4").
#   2026-07-25  owner decision: RAW xfv_grade is the single number, everywhere.
#               p50 = 20.0 (~3.1k of ~4.5k board rows sit on the 20.0 floor) is
#               ACCEPTED, not a bug: the board carries a very large provisional
#               cohort, so a floor-heavy median is the honest distribution.
#
# Every board-ordering call site must go through `_board_grade` (python) /
# `efvBoardValue` (prospx/index.html). If you find yourself resolving
# xfv_grade_quantile / xfv_grade_realized for an ORDERING or a DISPLAYED board
# grade, that is the bug this constant exists to prevent. The quantile remains
# a legitimate input to other models (surplus pricing, fantasy dynasty ranks);
# it is simply not the board.
#
#   2026-07-25  W-SIDESCALE. The raw grade is not cross-side comparable at the top:
#               the model's best pitcher grades 59.2 against a hitter p99 of 63.3,
#               so pitchers cannot reach the joint top 25 at all (25H/0P). The SCALE
#               of this field is now owned by efv_board_scale.py, which applies a
#               per-side affine outcome calibration at the artifact seam and keeps
#               the pre-calibration value at `xfv_grade_model_raw`. The FIELD NAME
#               below is unchanged on purpose: one field, one number, every reader
#               already pointed at it. Default OFF (see that module's gate record --
#               the primary specification is a measured NULL); when off, this
#               resolves to exactly the raw grade and nothing moves.
BOARD_GRADE_FIELD = "xfv_grade"
#   2026-09-25  DS-02 (docs/efv-v2/DRIVER_SYSTEM_V2.md, owner answer DS-Q1). The FIELD
#               is unchanged and every reader keeps reading it; what it HOLDS moved:
#               on every consensus-graded active row it is now eFV V2 (efv_v2_serve),
#               the consensus FV value of the row's (side, list year) group at the rank
#               of V2's order index, and board_sort_key carries that order index. The
#               board order, the displayed grade, the pricing grade, the odds grade and
#               the Source Comparison scored object are one number. The epoch moved to
#               2026-09-25 and the fingerprint gained the served= term in the same
#               commit.

#: DS-12 (docs/efv-v2/DRIVER_SYSTEM_V2.md, bug B7): debut-date bases that are a
#: synthesized day rather than a game date. "rule5_rollforward_placeholder" is the
#: {year}-07-01 anchor _safe_in_year_placeholder puts on an offseason 40-man add;
#: "opening_day_placeholder" is {first MLB season}-04-01 when nothing else is known.
PLACEHOLDER_DEBUT_BASES = frozenset({"rule5_rollforward_placeholder",
                                     "opening_day_placeholder"})

# The SUB-DECIMAL tiebreak that orders rows INSIDE an exact board-grade tie (see
# _board_sort_key in the serializer). Order-only, never displayed, never a grade.
# The sentinel is the value a row with no key sorts at: it must be lower than any
# real predicted WAR so a keyless row lands at the BACK of its tie block, and it must
# be the same number prospx uses (_NO_SORT_KEY there) or the two orderings diverge.
BOARD_SORT_KEY_FIELD = "board_sort_key"
_NO_BOARD_SORT_KEY = -1e9

# The board re-ranked once when the basis moved to BOARD_GRADE_FIELD. Board-rank
# history written BEFORE this date is on the old quantile basis, so comparing it
# to a post-epoch rank would report the one-time re-rank as real player movement.
# Every reader of metric_snapshots.overall_rank filters on this date; rank
# movement and the rank-trend arrow read empty until post-epoch history accrues.
BOARD_RANK_BASIS_EPOCH = "2026-10-15"   # STRICTLY-AFTER gate: see load_rank_history.
# Bumped 2026-10-19 for the 2026-10-15 served-model moves (owner EW3-10 eFV v5 COMBINED and
# EFV-REFIT-1 variant RT, flag 8ae40518): the served= term began hashing the re-fit weights
# (2bf83f80) and moved efv_v2@bcc9b0dd -> efv_v2@22ec625f, but neither flip restamped the pin
# or bumped this epoch. metric_snapshots held no rank row dated after 2026-10-02, so the bump
# drops no rank history and no served movement chip changes; xfv_history.json was already
# rebuilt on the new basis (2026-10-15 regen).
# Bumped 2026-10-04 for the fWAR epoch's owed P5 re-derivation (owner answer B7-P5, option A;
# commit c40c0dd0): eFV v2's DS-08 weights were re-fit once on the frozen fWAR label, so the
# served= term's hash moved (efv_v2@f903b813 -> efv_v2@bcc9b0dd) and every V2-served grade
# and rank may re-order once for a reason that is not player movement. metric_snapshots held
# no rank row dated after 2026-10-03 at the bump, so no served movement chip changes.
# Bumped 2026-10-03 for the fWAR LABEL EPOCH (docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md,
# step D + U; runbook docs/efv-2026-09-03/WAR_BASIS_RUNBOOK.md U). career_war was rebased
# from eWAR v2 to published fWAR at step C (2,686 of 2,698 rows; the 12 unresolved stay on
# their incumbent), which re-labels the eFV training target for every debuted row, so the
# board re-ranks once for a reason that is not player movement. The displayed WAR did not
# move (owner answer EPOCH-Q4, "Keep eWAR v2 shown"): only the label did.
# Bumped 2026-10-02 for PV-07 (owner answers PG-Q1 / PG-Q2, 2026-09-25): the board rank
# now counts only rows that carry a label-source opinion. The 2,701 board actives with no
# such opinion (the performance-anchor and draft-signing rows) leave the shared rank for
# the PROSPX section "Not yet graded by any source" (PROV_SECTION_ON below), so every
# graded row below the first of them re-ranks once for a reason that is not player
# movement. Grades did not move; the fingerprint gained the section= term with it.
# Bumped 2026-09-25 for DS-02: eFV V2 became the board number (the consensus value at
# V2's order rank inside each side) and board_sort_key became V2's order index, so every
# consensus-graded row re-ranks once for a reason that is not player movement. Landed
# before the fWAR label epoch's step A (FWAR_LABEL_EPOCH_GATE.md clause (l)).
# Bumped 2026-09-04 for the eWAR LABEL EPOCH. career_war was rebased from bWAR to
# eWAR v2, which re-labels the eFV training target for every debuted row, so the
# board re-ranks once for a reason that is not player movement. That is the only
# job this constant has. Gate docs/efv-2026-09-03/EWAR_LABEL_EPOCH_GATE.md.
# Bumped 2026-08-12 with the rookie-window unlock, which re-anchors every
# still-eligible graduate onto his latest board point. Rank history from
# before this date is on the debut-anchored basis and must not be differenced
# against history after it; the epoch is what makes that refusal automatic.
# 2026-08-07 BUMP (omnibus-3 Lane F, the floor routing going live). TWO board inputs
# moved in one commit and the epoch applies to both, which is the judgement the
# 2026-08-04 note below deliberately declined to make for a declaration-only change.
#   the routing   2,434 constant-anchor rows stop serving the outcome curve's floor knot
#                 and serve efv_ungraded's grade instead (median 27.1, p90 33.3, max
#                 46.7; 624 land above FV30). Those rows re-rank the 100-1000 band
#                 wholesale. No routed row reaches the top 100 (best rank 182), so the
#                 part of the board anyone screenshots is untouched, but "the top is
#                 stable" is not the epoch's test - "did ranks re-base" is, and they did.
#   the sort key  board_sort_key enters the tiebreak chain on BOTH readers, which
#                 re-orders the residual floor block (924 genuinely-graded rows whose
#                 single tie block the key cuts to 180) by the model instead of by the
#                 '+'/TBS/name proxies. Every one of those moves is a re-base, and the
#                 movement engine would otherwise publish them as player movement.
# This is the mirror of the STALE_ANCHOR flip, which correctly did NOT bump: that one
# measured zero movers, so there was no re-rank to mistake for movement. Here there are
# thousands, so the suppression is the point.
# F1 repair 2026-07-25: metric_snapshots already holds 4,467 rows STAMPED 2026-07-25 that were
# ranked on the RETIRED quantile basis (they were written before the flip landed the same day).
# A ">=" gate let those through, so the first post-flip export would have published 1,185 phantom
# rank moves (36 inside the new top 100, max 3,178 spots) as real player movement - precisely what
# the epoch exists to prevent. The comparison is now strictly-after, so a same-day pre-flip row is
# excluded and the first post-flip snapshot is the first row the movement engine can ever see.
#
# 2026-07-30 BUMP (LANE-P2, the pooled outcome refit). xfv_grade stopped being the inverse of
# value_framework's own forward map and became the inverse of the EMPIRICAL pooled outcome
# curve (vf.outcome_implied_fv / data/fv_outcome_curves_pooled.json). The FIELD did not move
# and the scale flag did not move, so the 07-25 fingerprint would not have noticed -- which
# is exactly why the fingerprint below now names the curve hash as well. Measured re-rank on
# identical inputs: 1,060 of 4,264 board rows change rank, median |move| 4, max |move| 27,
# top-100 membership 100 held / 0 entered / 0 left, top-25 2 in / 2 out. Small next to the
# 07-25 flip (median 417, max ~3.5k), but not zero, and the eFV delta is the owner's primary
# movement signal, so it is an epoch. Blast radius, byte-identity proof and the movement
# question: docs/efv-2026-07-30/POOLED_OUTCOME_REFIT.md.
#
# 2026-07-30, SECOND board input on the same date (LANE-SHIP, the pitcher role flip).
# role_usage.USAGE_ROLE_BOTH_DIRECTIONS -> True lets MiLB usage overwrite a published
# pitcher label in both directions; 871 rows enter efv_score._RP_DESIGNATIONS and become
# eligible for the reliever-ceiling haircut. The DATE does not need to move (it is already
# 2026-07-30 and this lands the same day), but the FINGERPRINT does, and it is extended
# below with a roles= term for exactly the reason the grademap term was added. Measured
# re-rank exposure: of the 871, ZERO sit inside the board top 300 (best rank 304) and only
# 3 clear the ceiling's age+WAR trigger, upper-bounded at 0.8 FV of grade movement each,
# so PINNED_MIX in test_board_basis_coherence is NOT re-recorded - the top-100 side mix
# provably cannot move on this input. docs/efv-2026-07-30/POSITION_ROLE_GATE.md PART 3.

# ── BASIS FINGERPRINT (A3, added 2026-07-30) ────────────────────────────────
# BOARD_RANK_BASIS_EPOCH above is hand-maintained, and NOTHING forced it to be bumped
# when the basis actually moved. It was not bumped on 2026-07-29 when efv_board_scale
# was disabled, and the board duly re-ranked: the served top-100 pitcher count went 16
# -> 8 and four arms moved 39->148 / 8->15 / 12->50 / 48->143 with zero grade changes,
# which the movement engine then published as real player movement (Seth Hernandez's
# card reads "down 33, confidence high" for a change no player caused).
#
# This fingerprint names every input that defines the board ORDERING. The suite pins it
# (test_board_basis_coherence), so changing any of them fails until the epoch is bumped
# and the fingerprint restamped in the SAME commit. It is a coordination device, not a
# calculation: it never touches a served number.
#
# EXTENDED 2026-07-30 (LANE-P2) with the GRADE MAP. The first version named the field and
# the side-scale flag only, which was enough for the two defects it was built from -- both
# were flips of one of those two things. It was NOT enough for this one: the pooled outcome
# refit re-ranked 1,051 board rows while leaving BOTH named inputs identical, so the
# fingerprint would have reported "no change" through a real re-rank. The board number is
# the inverse of a fitted curve, so the CURVE is part of the board's identity; the third
# term is that curve's content hash (value_framework.outcome_curve_identity, a SHA-1 over
# the knot/value pairs). Refit the curve, change the prior, change the pool -- the hash
# moves, the suite fails, and a human decides whether the board really did re-rank.
#
# EXTENDED AGAIN 2026-07-30 (LANE-SHIP) with the PITCHER ROLE-RESOLUTION MODE. Same
# lesson, third instance: role_usage.USAGE_ROLE_BOTH_DIRECTIONS decides whether MiLB
# usage may overwrite a published pitcher label in BOTH directions, and an "RP" label
# is what puts a row in efv_score._RP_DESIGNATIONS, which is what exposes its model WAR
# leg to the reliever-ceiling haircut, which is the board number. Turning that switch
# on moved 1,269 labels and 871 RP-set memberships while leaving all three existing
# fingerprint terms identical -- i.e. the fingerprint would again have reported "no
# change" through a real board input flipping. Role mode is a board-ordering input, so
# it is named.
# 2026-07-30 (second restamp today): the E1 repeat-level ship added seasons_at_level to
# the PITCHER feature set, which moves every pitcher's model WAR and therefore the board
# order, while leaving all four prior terms identical. That is the same failure mode the
# roles note above describes, one layer deeper, so the feature spec itself is now hashed
# into the fingerprint and named here.
# EXTENDED 2026-08-07 (omnibus-3 Lane B) with TWO terms, and the reason is the same
# lesson for the fifth and sixth time: a fingerprint only guards what it NAMES.
#
#   stale=       efv_dataset.STALE_ANCHOR_DATE_BASIS. Which date the staleness ramp
#                measures from decides anchor_stale_discount, which decides
#                fv_effective, which is the eFV model's DOMINANT feature. It has been
#                a board-ordering input since 2026-07-14 and the fingerprint has
#                never named it. The 2026-08-07 flip point -> source moves 0 rows
#                today (docs/efv-2026-08-07/STALE_ANCHOR_MOVER_TABLE.json), so it
#                would have slipped past this device unnoticed - which is precisely
#                the case where an unnamed input is most dangerous, because the next
#                change to it inherits a fingerprint that already lied once.
#   floorroute=  efv_score.SERVE_PROVISIONAL_FOR_CONSTANT_COHORT plus the identity of
#                the PROVISIONAL grade map it routes onto. The plan called the missing
#                provisional-scale term a registered gap and it is closed here. Naming
#                the switch alone would not have been enough: the routed grade is
#                efv_ungraded._GRADE_MAP's output, so a change to BASE / SLOPE / KNEE /
#                CEIL / SOFT re-grades and re-ranks every routed row while the switch
#                stays True. The term hashes the map itself for the same reason the
#                grademap term hashes the outcome curve.
#
# The switch is False today, so the term reads floorroute=off and the map hash is
# still carried: a provisional-map edit trips the check whether or not the routing is
# live, which is what stops the map drifting under a gate that was measured against it.
#
# THE PRICE OF EXTENDING THIS STRING, paid knowingly. data/xfv_history.json carries
# the fingerprint it was built under, and xfv_history_is_on_board_basis() gates the
# eFV-delta MOVEMENT signal on an exact match. The committed history artifact matched
# the pre-2026-08-07 string exactly, so extending the fingerprint flips that gate to
# False and the eFV movement chips read empty until score_history restamps the
# artifact on the next nightly regen. One cycle, and it is the suppression working as
# designed rather than a side effect: neither new term moves a grade today (the stale
# flip measured 0 movers, the routing is off), but a coordination device that only
# fires when it is convenient is not one. The alternative - leaving the two inputs
# unnamed to protect one night of chips - is the exact trade that produced the
# 2026-07-29 incident.
BOARD_BASIS_FINGERPRINT = ("xfv_grade|scale=off|grademap=outcome_pooled@baa9676f90a6"
                           "|roles=usage_both|feats=b747e1d3|stale=source"
                           "|floorroute=on@ff60a349|gradanchor=rookie_window"
                           "|disp=hit:0.000000/1.000000|pit:0.000000/1.000000"
                           "|gradenorm=asof@ref2017"
                           "|label=fwar@2026-10-02-a020cf64844a"
                           "|injsides=pit|served=efv_v2@22ec625f"
                           "|section=label_graded")
# label fwar@2026-10-02-57bf90f7143e -> fwar@2026-10-02-a020cf64844a on 2026-10-19: the
# innings amendment of the frozen vintage (EWAR_P0B_VINTAGE_IP, the EW3-19 precedent "a new
# vintage id"; FWAR_LABEL_EPOCH_GATE.md part 9, the 2026-10-19 entry). Four columns
# (inningsPitched, outs, gamesPitched, gamesStarted) were appended to the pitching rows by
# tools/amend_fwar_vintage_ip.py, which proved every earlier value of every row unchanged and
# war_source's maps EQUAL before and after. Value-identical label, so, as on 2026-10-15,
# BOARD_RANK_BASIS_EPOCH is NOT bumped and xfv_history.json's stamp refreshes at the next
# score_history run.
# label fwar@2026-10-02-0341299c20ec -> fwar@2026-10-02-57bf90f7143e on 2026-10-15: the
# plate-appearance amendment of the frozen vintage (EWAR_P0_VINTAGE_PA, owner answer EW3-19
# "a new vintage id"; FWAR_LABEL_EPOCH_GATE.md part 9, the 2026-10-15 entry). Only the
# hitting rows' plateAppearances column was filled (tools/amend_fwar_vintage_pa.py), so the
# hashes and the id moved while every published value stayed: the tool proved every row
# unchanged outside that column and war_source's maps (side_targets both sides,
# season_totals) EQUAL before and after, and no label reader reads the PA column. The
# training label is therefore value-identical, no grade or rank can move, and
# BOARD_RANK_BASIS_EPOCH is deliberately NOT bumped (the feats and C-4 precedent below:
# a bump would drop a day of genuine rank history to hide a re-rank that did not happen).
# The one cost, paid knowingly: data/xfv_history.json carries the old string as its basis
# stamp, so xfv_history_is_on_board_basis reads False and the eFV-delta movement override
# is withheld until the next score_history run restamps it.
# served efv_v2@f903b813 -> efv_v2@bcc9b0dd on 2026-10-04: the P5 re-derivation of
# data/efv_v2_assembly.json on the frozen fWAR label (c40c0dd0; FWAR_LABEL_EPOCH_GATE.md part 9,
# the 2026-10-04 entry). The term hashes the registered weights, which moved; restamped with
# the BOARD_RANK_BASIS_EPOCH bump to 2026-10-04.
# grademap 1f3fa0a970bd -> baa9676f90a6 on 2026-10-03: THE fWAR LABEL EPOCH, step I. The
# pooled FV outcome curve (tools/fv_outcome_curve_pooled.py, 3,213 resolved rows) was refit
# on the fWAR training label at RESOLVED_THROUGH 2026, so its content hash moved; this is the
# restamp the step D + U commit deferred to step I (the 2026-09-04 precedent). The curve's
# pool (xfv_scored*.json) was regenerated by efv_score.py on the step F matrices first, so
# its identity checks read 0 target, 0 censored-flag and 0 FV mismatches on both sides.
# label ewar_v2@2026-09-03T12:35:09 -> fwar@2026-10-02-0341299c20ec on 2026-10-03: THE fWAR
# LABEL EPOCH, step D + U (gate docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md part 7 row D + U
# and part 8; orchestrator ruling EPOCH-Q4-IMPL R1a). The term names the TRAINING LABEL
# BUILD: war_source.DEFAULT_PROVIDER moved to 'fwar' and the build identity is the frozen
# vintage's vintage_id (data/fwar_vintage.json, EPOCH_D9_FREEZE 7e34799f), so a re-freeze
# moves it as a rebuild of ewar.json used to. The displayed WAR stays eWAR v2 (owner answer
# EPOCH-Q4) and is not what this term names. The grademap= term is restamped separately
# after step I refits the pooled curve on the new label (the 2026-09-04 precedent).
# section= added 2026-10-02 with PV-07 and the epoch bump. Every earlier term names how a
# grade is made; none of them can see WHICH rows the rank counts. Moving the rows with no
# label-source opinion out of the shared rank re-numbers every graded row below the first
# of them while all thirteen earlier terms stay byte-identical. "label_graded" while
# PROV_SECTION_ON holds, "all" if the section is ever folded back in.
# served= added 2026-09-25 with DS-02 and the epoch bump. Every term before it names how
# eFV v1 turns a prediction into a grade; none of them can see WHICH eFV serves. Serving
# V2 moves every consensus-graded grade and rank while all eleven earlier terms stay
# byte-identical, so the device names the served model and, for V2, a hash of the
# registered weights and the serving constants (efv_v2_serve.fingerprint_term).
# injsides added 2026-09-04: THE INJURY HAIRCUT WENT PITCHER-ONLY, on the owner's decision
# and on measured outcomes (efv_score.INJURY_PENALTY_SIDES carries the numbers). It lifts
# the haircut off 225 served hitters at a median x0.738 and leaves 360 pitchers untouched,
# so grades, ranks and surplus all move on the hitter side. Rides the SAME
# BOARD_RANK_BASIS_EPOCH 2026-09-04 as the label epoch: both are one-time basis moves on
# one day, and the movement engine's strictly-after gate covers them together.
# grademap 6dbe8353f3bb -> 1f3fa0a970bd and the NEW label= term, both on 2026-09-04:
# THE eWAR LABEL EPOCH. Gate docs/efv-2026-09-03/EWAR_LABEL_EPOCH_GATE.md, runbook
# docs/efv-2026-09-03/WAR_BASIS_RUNBOOK.md step U. career_war was rebased from bWAR to
# eWAR v2 (2,531 of 2,666 rows; the other 135 resolve to no mlbam and stay on bWAR), so
# the first-6yr label moved, the pooled FV outcome curve was refit on the new label and
# its hash moved with it. The label= term is what makes the SECOND of those visible: the
# curve hash would have moved on any refit, but nothing in this string could see that the
# training target itself changed basis.
# disp 0.470359/0.663929 -> 0.000000/1.000000 on 2026-08-14: THE C-7 REVERT, on the
# owner's decision. Gate docs/efv-2026-08-13/DISPERSION_REVERT_GATE.md. The identity
# map is written as coefficients rather than as the word "identity" on purpose: the
# term must stay comparable across a re-introduction, and 0.000000/1.000000 says
# exactly which map is serving without a reader having to trust a label.
#
# BOARD_RANK_BASIS_EPOCH deliberately NOT bumped, and this time it is MEASURED rather
# than argued. The epoch has one job, stopping the movement engine differencing RANKS
# across a basis change, and the C-7 diff found rank_war and board_sort_key
# BYTE-IDENTICAL on all 4,489 served rows, because the blend leg reads the uncorrected
# model leg. There is no rank basis change to suppress, and a bump would drop another
# day of history for no protection. The GRADES did move (1,511 rows), and that path is
# already covered: xfv_history carries this fingerprint as its basis stamp, so
# xfv_history_is_on_board_basis withholds the eFV-delta movement override for one
# cycle on its own.
#
# gradenorm off@ref2017 -> asof@ref2017 on 2026-08-14: THE C-4 FLIP.
#
# The term was added three commits earlier, deliberately BEFORE the change it
# guards, and it did the job it was added for: the moment the flag flipped, the
# pinned-fingerprint test failed and demanded this restamp. Every other term on
# this device was added AFTER something moved every served grade invisibly, so this
# is the first time the sequence ran the right way round.
#
# The epoch is NOT bumped with it, and that is a judgement rather than an omission.
# BOARD_RANK_BASIS_EPOCH exists for ONE job: stop the movement engine differencing
# ranks across a basis change. It was already moved to 2026-08-13 for the
# dispersion epoch, and no board row dated after that has been served on the
# pre-C-4 basis, so the gate it controls is already closed over exactly the right
# window. Bumping it again would drop a second day of history for no additional
# protection.
#
# Coefficients deliberately NOT re-fitted for this flip; see the pinning rule in
# efv_score._DISPERSION_CORRECTION. A re-fit would have re-graded 48.5% of the
# non-routed board to chase an a_c shift of 0.0115, well inside its own +/-0.06
# fold noise, and drowned C-4's actual -0.24 FV effect.
# disp added 2026-08-14 WITH an epoch bump, which is the case this pin is for. The
# dispersion correction (Defect A) is an affine level fix on xfv_war fitted out of fold
# on the production frame, and it moves 4,585 of 4,664 served grades. Gate:
# docs/efv-2026-08-13/GRADE_BASIS_EPOCH_GATE.md.
#
# Unlike the floorroute and feats restamps below, this one DOES take the epoch with it.
# The test that caught the omission said so in its own failure message, and it was right:
# every displayed grade moves, so pre-change ranks and post-change ranks are not
# comparable and the movement engine must not difference across the boundary.
# floorroute off -> on 2026-08-07: efv_score.SERVE_PROVISIONAL_FOR_CONSTANT_COHORT was
# flipped once the prospx dedupe and the two-scale disclosure landed. Ship record and
# re-run gates: docs/efv-2026-08-07/BOARD_FLOOR_ROUTING_SHIP.md. The map hash is
# unchanged because efv_ungraded._GRADE_MAP was not touched; only the switch moved.
# feats dbb1bc2a -> b747e1d3 on 2026-08-04: the hitter `age` SIGN DECLARATION moved
# -1 -> 0 (docs/efv-2026-08-04/HIT_AGE_SIGN_GATE.md). The hash covers declared signs
# ON PURPOSE, so this trip is the coordination check working as designed.
#
# BOARD_RANK_BASIS_EPOCH is deliberately NOT bumped with it, and that is the whole
# judgement here. The epoch exists for ONE job: tell the movement engine that ranks
# were re-based so it does not publish a one-time re-rank as player movement. A
# declaration is documentation for the EVAL-ONLY monotone LightGBM challenger -
# _feature_spec hands the signs to _fit_lgbm_mono and hands only the NAMES to
# _fit_ridge, which is the served model - so no served grade and no rank moved
# because of this. Bumping the epoch would suppress a night of GENUINE movement to
# hide a re-rank that did not happen, which is the mirror of the 2026-07-29 mistake
# rather than a repeat of it. The fingerprint's job (a change happened, a human
# looked) applies; the epoch's job (ranks re-based) does not.


def board_basis_fingerprint() -> str:
    """Identity of the board ordering: which field is the board number, whether the
    per-side outcome scale is applied on top of it (and if so, which coefficients),
    WHICH FITTED CURVE the grade itself inverts, and HOW PITCHER ROLES ARE RESOLVED.

    Deliberately cheap and import-safe: efv_board_scale, value_framework and role_usage
    are imported lazily here exactly as efv_board_scale is in _board_grade, so importing
    storage never hard-depends on any of them. Every term degrades to a literal
    'unavailable' rather than raising -- a coordination device must never be the thing
    that takes the site down; it just has to differ from the pin, which 'unavailable'
    does."""
    try:
        import efv_board_scale as _bs
        if _bs.enabled():
            coeffs = ",".join(f"{s}:{a:.6f}/{b:.6f}"
                              for s, (a, b) in sorted(_bs.COEFFS.items()))
            scale = f"on[{coeffs}]"
        else:
            scale = "off"
    except Exception:
        scale = "unavailable"
    try:
        import value_framework as _vf
        grademap = f"outcome_pooled@{_vf.outcome_curve_identity()}"
    except Exception:
        grademap = "unavailable"
    try:
        import role_usage as _ru
        roles = _ru.role_resolution_mode()
    except Exception:
        roles = "unavailable"
    # FEATURE-SET term, added 2026-07-30. Until now this device could not see a MODEL
    # change at all: it encoded the grade field, the display scale, the grade map and the
    # role resolver, so shipping a new eFV feature moved every pitcher's grade and the
    # board order while the fingerprint stayed byte-identical to its pin. The E1
    # repeat-level ship is exactly that case and is what exposed it. Hashing the declared
    # feature specs makes any future add, removal or sign re-declaration trip the
    # coordination check the way a grade-map change already does.
    try:
        import hashlib as _hashlib
        import efv_model as _em
        _spec = "".join(f"{s}:" + ",".join(f"{k}{m:+d}" for k, m in
                                           (_em._FEATURES_HIT if s == "hit" else _em._FEATURES_PIT))
                        for s in ("hit", "pit"))
        feats = _hashlib.sha256(_spec.encode()).hexdigest()[:8]
    except Exception:
        feats = "unavailable"
    # STALE-ANCHOR DATE BASIS, added 2026-08-07. See the note above the constant.
    try:
        import efv_dataset as _ed
        stale = str(_ed.STALE_ANCHOR_DATE_BASIS)
    except Exception:
        stale = "unavailable"
    # FLOOR ROUTING + the provisional grade map it routes onto, added 2026-08-07.
    # Imported lazily and hashed the same way the feature spec is: the map is a plain
    # constant dict, so a stable repr over sorted keys is the whole identity.
    try:
        import hashlib as _hashlib
        import efv_score as _es
        import efv_ungraded as _eu
        _map = "".join(
            f"{s}:" + ",".join(f"{k}={_eu._GRADE_MAP[s][k]:g}"
                               for k in sorted(_eu._GRADE_MAP[s]))
            for s in sorted(_eu._GRADE_MAP))
        _map += f"|uncapped={bool(_eu.UNCAPPED_GRADE)}|subfloor={_eu._SUBFLOOR_GRADE:g}"
        _mh = _hashlib.sha256(_map.encode()).hexdigest()[:8]
        _on = "on" if _es.SERVE_PROVISIONAL_FOR_CONSTANT_COHORT else "off"
        floorroute = f"{_on}@{_mh}"
    except Exception:
        floorroute = "unavailable"
    # GRADUATE ANCHOR RULE, added 2026-08-12 with the rookie-window unlock, and
    # it closes the same class of hole the feature-set term closed in July. The
    # device encoded the grade field, the scale, the map, the roles, the feature
    # spec, the stale basis and the floor routing, and NONE of them sees which
    # snapshot a graduate is scored at. Flipping that rule moves the served
    # grade for every still-eligible graduate (920 of them) while the
    # fingerprint stayed byte-identical to its pin, so the movement-suppression
    # gate would have waved the transition run straight through.
    try:
        import efv_score as _es2
        anchor = "rookie_window" if getattr(_es2, "GRADUATE_ROOKIE_WINDOW", True) else "at_debut"
    except Exception:
        anchor = "unavailable"
    # DISPERSION CORRECTION, added 2026-08-14 with the grade-basis epoch, and it is the
    # same hole again in a new place. Every term above identifies WHICH map produced the
    # grade; none of them can see an affine level correction applied to that map's INPUT.
    # Shipping it moves 4,585 of 4,664 served grades, and without this term the
    # fingerprint would have stayed byte-identical to its pin while it happened, so the
    # movement-suppression gate would have waved the transition run through and published
    # a basis change as player movement. A fingerprint only guards what it names.
    try:
        import efv_score as _es3
        disp = "|".join(f"{s}:{_a:.6f}/{_b:.6f}"
                        for s, (_a, _b) in sorted(_es3._DISPERSION_CORRECTION.items()))
    except Exception:
        disp = "unavailable"
    # GRADE-NORMALIZATION BASIS, added 2026-08-14, and it is the FIFTH term this
    # device has needed for the same reason. The pattern is now unmistakable: every
    # term here was added AFTER something moved every served grade while the
    # fingerprint stayed byte-identical to its pin (feats 2026-07-30, floorroute
    # 2026-08-07, gradanchor 2026-08-12, disp 2026-08-14, this one now).
    #
    # consensus.GRADE_NORM_AS_OF caps the grade-normalization pool at each cell's
    # own year and, since the era-floor reachability fix earlier today, floors
    # pre-2017 cells at the reference's first year. Flipping it moves
    # consensus_fv_raw, which is simultaneously eFV's dominant FEATURE and its
    # BASELINE, so it moves every served grade. Measured: 3,577 served units, mean
    # -0.2396 FV on the 3,478 pre-2017 rows and +2.1004 on the 99 in-window ones.
    #
    # Added BEFORE the flip rather than after it, which is the whole point. A
    # fingerprint that gains its term in the same commit as the change it guards
    # has never guarded anything.
    try:
        import consensus as _cn
        import grade_normalization as _gn
        gradenorm = ("asof" if getattr(_cn, "GRADE_NORM_AS_OF", False) else "off")
        gradenorm += f"@ref{getattr(_gn, '_REFERENCE_FIRST_YEAR', '?')}"
    except Exception:
        gradenorm = "unavailable"
    # LABEL BASIS, added 2026-09-04 with the eWAR label epoch, and it is the same hole
    # one more time. Every term above identifies how a PREDICTION is turned into a served
    # grade; not one of them can see which WAR series the model was TRAINED on. Rebasing
    # career_war from bWAR to eWAR v2 re-labels the training target for every debuted row
    # and moves the served grade, and without this term the fingerprint would have stayed
    # byte-identical to its pin while it happened. The term names the provider and the
    # BUILD identity of the label series, so a rebuild of ewar.json moves it too: a
    # provider name alone would go stale the first time the artifact was refit.
    # fWAR label epoch (2026-10-03, step D + U): the provider is 'fwar' and the build
    # identity is the frozen vintage's id (fwar_vintage.vintage_id), so the term reads
    # fwar@<vintage id>; a re-freeze moves it. Under 'ewar_v2' the build identity stays
    # the eWAR artifact's generated_at, so the term is comparable across the flip.
    try:
        import war_source as _ws
        # eFV's label (war_source.EFV_LABEL_PROVIDER): DEFAULT_PROVIDER unless the headline
        # eWAR label check's switch is on (EWAR_HEADLINE_LABEL_GATE.md part 3), when the
        # term reads ewar_headline@<frozen label vintage id>
        label = str(getattr(_ws, "EFV_LABEL_PROVIDER", getattr(_ws, "DEFAULT_PROVIDER", "unknown")))
        if label == "fwar":
            import fwar_vintage as _fv
            label += f"@{str(_fv.load().get('vintage_id') or 'nobuild')}"
        elif label == "ewar_core":
            # the core eWAR label epoch (docs/efv-2026-10-22/EWAR_CORE_LABEL_EPOCH_GATE.md
            # part 3): the frozen label vintage's id, ewar-core-<fWAR vintage id>-<sha12>
            import ewar_core_label as _ecl
            label += f"@{_ecl.vintage_id() or 'nobuild'}"
        elif label == "ewar_headline":
            import ewar_headline_label as _ehl
            label += f"@{_ehl.vintage_id() or 'nobuild'}"
        elif label != "bwar":
            import ewar as _ew
            _p = _ew.load()
            label += f"@{str(_p.get('generated_at') or 'nobuild')[:19]}"
    except Exception:
        label = "unavailable"
    # INJURY-PENALTY SIDES, added 2026-09-04 when the haircut went pitcher-only. Same hole
    # as every term above it: the device could see which map produced a grade and which
    # label trained it, but not the multiplicative live OVERLAYS applied on top. Restricting
    # the injury haircut to pitchers lifts it off 225 served hitters at a median x0.738, and
    # without this term the fingerprint would have stayed byte-identical while their grades,
    # ranks and dollars all moved. Sorted so the string is order-stable.
    try:
        import efv_score as _es4
        injsides = ",".join(sorted(_es4.INJURY_PENALTY_SIDES)) or "none"
    except Exception:
        injsides = "unavailable"
    # SERVED MODEL, added 2026-09-25 with DS-02 (see the note at the pinned constant).
    try:
        import efv_v2_serve as _v2s
        served = _v2s.fingerprint_term()
    except Exception:
        served = "unavailable"
    # RANKED POOL, added 2026-10-02 with PV-07 (see the note at the pinned constant).
    section = "label_graded" if PROV_SECTION_ON else "all"
    return (f"{BOARD_GRADE_FIELD}|scale={scale}|grademap={grademap}|roles={roles}"
            f"|feats={feats}|stale={stale}|floorroute={floorroute}|gradanchor={anchor}"
            f"|disp={disp}|gradenorm={gradenorm}|label={label}|injsides={injsides}"
            f"|served={served}|section={section}")


# ── THE "NOT YET GRADED BY ANY SOURCE" SECTION (PV-07, 2026-10-02) ──────────────
# Owner answers PG-Q1 and PG-Q2 (2026-09-25, DECISIONS_FOR_OWNER.md; spec
# _finalpass_2026-09-24/provisional/PROVISIONAL_V2.md section 3): the provisional grade
# has no level skill against the first source grade (Spearman 0.017, MAE 6.21 against a
# constant's 4.54, data/provisional_track_eval.json served_backdated leg), so a row that
# no label source has ever graded does not sit in the shared board rank. The
# provisional-only rows (client-side, from xfv_ungraded.json) and the board actives with
# no label-source opinion form their own PROSPX section, ordered there by the chance of a
# first grade (data/provisional_v2.json). Trade values and farm points keep their inputs
# (PG-Q2): nothing here touches a grade, a surplus or the farm pool.
#
# The rows rejoin the shared rank ONLY on a frozen level win: a closed prospective window
# whose level claim on the frozen expected first grade holds (provisional_track claims
# level.fv_fg_pred). That is a necessary condition, not an automatic switch: flipping
# PROV_SECTION_ON to False is a reviewed change, and test_prospx_prov_section refuses it
# while prov_section_state() reports no such win.
PROV_SECTION_ON = True
#: The label sources, the same set provisional_track.SETS["ANY"] scores first grades on
#: (pinned equal by test_prospx_prov_section). tjstats, performance_ingest and
#: draft_signing are not label sources: the last two are the fabricated performance
#: anchor and the signing-bonus anchor.
PROV_SECTION_LABEL_SOURCES = ("fangraphs", "mlb_pipeline", "mlb_pipeline_international",
                              "baseballamerica", "espn", "just_baseball")
PROV_SECTION_TITLE = "Not yet graded by any source"

# EFV_DISPLAY_SWAPS (owner ask 5, 2026-09-30; owner answer Q-E1; Part 8 lane
# links_efv_display, B.1): the ONE switch for the PROSPX eFV display swaps. Off, PROSPX
# behaves as before apart from labels: a consensus grade printed where eFV abstains wears
# a C mark and a dashed border and its tooltip says so. On, the Rank-by and Debuted
# toggles order the lists only and every printed grade stays eFV, with a labelled
# consensus chip beside it while a list is ordered by consensus; the FV sparkline's H and
# L chips and the FV-history tooltip read the eFV series; the headshot ring keys on the
# eFV rarity grade; a grade waiting on the eFV file paints a neutral placeholder. Served
# to the page as flags.efv_display_swaps on the boot payload (written below), the only
# place prospx/index.html reads it. proj_export imports this name; test_efv_display_helpers
# fails if it is assigned anywhere else. Flipped on in its own commit (Q9_15, 2026-10-14,
# after the fWAR label epoch's step Z entry).
EFV_DISPLAY_SWAPS = True


def _point_sources(pt) -> set:
    """Every source a consensus point names: its per_source keys plus
    sources_contributing. Works on a PlayerTimeseries point or a served point dict."""
    if isinstance(pt, dict):
        ps, sc = pt.get("per_source"), pt.get("sources_contributing")
    else:
        ps, sc = getattr(pt, "per_source", None), getattr(pt, "sources_contributing", None)
    out = set((ps or {}).keys()) if isinstance(ps, dict) else set()
    out.update(s for s in (sc or []) if isinstance(s, str))
    return out


def has_label_source_opinion(points) -> bool:
    """True when any point of the series names a label source (an opinion ever given,
    the PG3 probe-7 definition). An empty series answers False."""
    lab = set(PROV_SECTION_LABEL_SOURCES)
    return any(_point_sources(pt) & lab for pt in (points or []))


def row_in_prov_section(p: dict) -> bool:
    """Does this served active row leave the shared rank? Reads the export's
    `source_graded` flag; a payload from before the flag falls back to the row's points,
    and a row with neither (a synthetic or pre-flag payload) stays ranked."""
    if not PROV_SECTION_ON or not isinstance(p, dict):
        return False
    flag = p.get("source_graded")
    if flag is None:
        pts = p.get("points")
        if not pts:
            return False
        flag = has_label_source_opinion(pts)
    return not bool(flag)


def prov_section_state(path: Path | None = None) -> dict:
    """The served description of the section, derived from data/provisional_track_eval.json:
    whether a frozen window has shown the level win the rejoin rule needs, and the next
    window end. Written to the payload top level as `prov_section`."""
    p = Path(path) if path is not None else Path(__file__).parent / "data" / "provisional_track_eval.json"
    level_win, closed, open_until = False, [], []
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    latest = set((doc.get("latest") or {}).values())
    for r in doc.get("rows") or []:
        if r.get("leg") != "prospective" or (latest and r.get("run_id") not in latest):
            continue
        if r.get("verdict_readable"):
            closed.append(r.get("window_end"))
            lv = ((r.get("claims") or {}).get("level") or {}).get("fv_fg_pred") or {}
            if lv.get("claim") is True:
                level_win = True
        elif r.get("window_end"):
            open_until.append(r.get("window_end"))
    return {
        "on": bool(PROV_SECTION_ON),
        "title": PROV_SECTION_TITLE,
        "label_sources": list(PROV_SECTION_LABEL_SOURCES),
        "order": "chance of a first grade by the W12 window end (data/provisional_v2.json p_any_w12)",
        "rejoin_rule": ("rows rejoin the shared rank only after a closed prospective window shows "
                        "the frozen expected first grade beating the constant (level claim, "
                        "paired CI95 clear of 0)"),
        "level_win": level_win,
        "windows_closed": sorted(w for w in closed if w),
        "next_window_end": min(open_until) if open_until else None,
        "read_from": "data/provisional_track_eval.json",
    }


# ── eFV join: the site's primary grade replaces consensus FV across the farm / DvM+ /
# movement metrics (owner directive). Reads the PRIOR run's committed data/xfv.json
# (per-player xfv_grade + surplus_mm + tool_xfv) and data/xfv_history.json (per-snapshot
# eFV series, for the appreciation + movement signals). ONE-RUN LAG is intentional and
# unavoidable: export_timeseries_json runs BEFORE efv_export.regen_all in run_monthly, and
# efv_export reads timeseries.json — reordering would be circular. This mirrors the frontend,
# which already consumes xfv.json with a consensus fallback. Where eFV abstains (no pro track
# record), every consumer falls back to consensus FV so nothing goes null.
def _load_xfv_join() -> tuple[dict, dict]:
    base = Path(__file__).parent / "data"
    def _read(name):
        try:
            return (json.loads((base / name).read_text(encoding="utf-8")).get("by_player") or {})
        except Exception:
            return {}
    return _read("xfv.json"), _read("xfv_history.json")


#: A player whose exact board grade is shared with more than this many others is ranked by
#: the TIEBREAK chain, not by his grade (export_timeseries_json._rank_meaningful and
#: rebake_board_ranks both read this). Module scope so the two cannot disagree.
RANK_TIE_BLOCK_MAX = 50


def board_rank_key(grade, sort_key, upside, tbs_proxy, rank_key) -> tuple:
    """THE board ordering tuple. export_timeseries_json._active_key and rebake_board_ranks
    both build it HERE, so the baked rank and the re-baked rank cannot drift: a term that
    one reader applies and the other does not is the rendered-order-vs-baked-rank
    divergence BOARD_GRADE_FIELD exists to prevent. Mirrors prospx fvCmpDesc term for term:
    board grade desc (decimal) -> board_sort_key desc (the model's sub-decimal order inside
    an exact tie; the sentinel sorts LAST) -> '+' flag -> Tiebreaker Score (the proxy here,
    the JS TBS on the client) -> avg_rank asc."""
    return (
        -float(grade if grade is not None else 0.0),
        -float(sort_key if sort_key is not None else _NO_BOARD_SORT_KEY),
        -int(1 if upside else 0),
        -float(tbs_proxy if tbs_proxy is not None else 0.0),
        float(rank_key) if rank_key is not None else 999.0,
    )


def _payload_bytes(obj) -> bytes:
    """Compact JSON bytes in the export's own format (orjson when installed)."""
    try:
        import orjson as _orjson
        return _orjson.dumps(obj, option=_orjson.OPT_NON_STR_KEYS)
    except ImportError:
        return json.dumps(obj, separators=(",", ":")).encode("utf-8")


def rebake_board_ranks(out_path: Path, *, xfv_by_key: dict | None = None,
                       rank_history: dict | None = None, write: bool = True,
                       update_metric_snapshots: bool = True, log=None) -> dict:
    """Re-rank the served board on the CURRENT data/xfv.json and rewrite the rank fields
    (overall_rank, org_rank, org_rank_total, prev_overall_rank, rank_movement) in place.

    WHY THIS EXISTS (2026-09-05). run_monthly.rebuild_only exports timeseries.json, which
    bakes overall_rank off the eFV file ON DISK, and only THEN runs efv_export.regen_all,
    which rewrites that file from the just-exported timeseries (the eFV live matrix needs
    the fresh stats, so the order cannot flip). The baked rank was therefore always ONE
    RUN STALE against the grades the board displays and sorts on, and every surface that
    reads the baked number (the homepage Top Prospects module, org ranks, the news
    tooltip, the GFX eyebrow) could disagree with the board. Measured 2026-09-05: Josue
    De Paula and Theo Gillen sat on an exact 58.3 tie with board_sort_key 9.617 vs 9.670;
    the previous file had them 58.2 vs 58.1, so the homepage said #4 / #5 and the board
    said #5 / #4. Three earlier incidents of the same class are recorded at
    BOARD_GRADE_FIELD; this was the fourth, by a different route.

    HOW. Every NON-MODEL term of the ordering (consensus fallback grade, '+' flag, the
    TBS proxy, avg_rank, the org key) is serialized per active row as `board_key_tail`
    at export time. This function re-applies THE ordering (board_rank_key) with only the
    two model terms refreshed from the eFV file: the board grade through
    efv_board_scale.board_value (consensus fallback where eFV abstains, as the export
    does) and board_sort_key (sentinel where absent). It is a pure function of the two
    files, so it can run standalone (tools/rebake_board_ranks.py) and be tested on a
    synthetic payload.

    Rows without a tail (an export that predates this field) are left untouched and
    counted in `n_without_tail`. `rank_movement` and `prev_overall_rank` are recomputed on
    the same rules the export uses (RANK_TIE_BLOCK_MAX gating, post-epoch history only).
    When today's metric_snapshots rows exist (the monthly snapshot is taken from the
    intermediate export, before the chained rebuild) their overall_rank is updated so the
    rank history stays on the served basis. Writes go through _atomic_replace.
    """
    import logging as _logging
    lg = log or _logging.getLogger("storage.rebake")
    out_path = Path(out_path)
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    players = payload.get("players") or []
    xfv = xfv_by_key if xfv_by_key is not None else _load_xfv_join()[0]
    try:
        from efv_board_scale import board_value as _board_value
    except Exception:                                       # pragma: no cover
        def _board_value(rec):
            return (rec or {}).get(BOARD_GRADE_FIELD)

    rows: list[tuple] = []
    n_without_tail = 0
    # PV-07: a row with no label-source opinion carries no shared rank (see
    # PROV_SECTION_ON). Its rank fields are cleared here, so a payload exported before the
    # section re-bakes onto it, and a cleared row that had a rank counts as moved.
    section_rows: list[dict] = []
    for p in players:
        tail = p.get("board_key_tail")
        if tail is None:
            if p.get("overall_rank") is not None:
                n_without_tail += 1
            continue
        if p.get("source_graded") is None and p.get("points"):
            p["source_graded"] = has_label_source_opinion(p["points"])
        if row_in_prov_section(p):
            section_rows.append(p)
            continue
        fallback_fv, upside, tbs, rank_key, org_key = (list(tail) + [None] * 5)[:5]
        rec = xfv.get(p.get("player_key")) or {}
        g = _board_value(rec)
        grade = float(g) if g is not None else float(fallback_fv or 0.0)
        sk = rec.get("board_sort_key")
        try:
            sk = float(sk) if sk is not None else _NO_BOARD_SORT_KEY
        except (TypeError, ValueError):
            sk = _NO_BOARD_SORT_KEY
        rows.append((board_rank_key(grade, sk, upside, tbs, rank_key), p, grade,
                     str(org_key or "?")))
    if not rows:
        msg = ("no active row carries board_key_tail (the export predates 2026-09-05); "
               "nothing re-baked")
        lg.warning("rebake_board_ranks: %s", msg)
        return {"written": False, "n_active": 0, "n_moved": 0,
                "n_without_tail": n_without_tail, "message": msg, "top": []}
    rows.sort(key=lambda t: t[0])

    tie_count: dict[float, int] = {}
    org_totals: dict[str, int] = {}
    for _, _, grade, org in rows:
        tie_count[grade] = tie_count.get(grade, 0) + 1
        org_totals[org] = org_totals.get(org, 0) + 1
    hist = rank_history if rank_history is not None else load_rank_history()
    today = date.today().isoformat()
    from movement import compute_rank_movement
    org_counters: dict[str, int] = {}
    moved = 0
    top: list = []
    for i, (_, p, grade, org) in enumerate(rows, start=1):
        if p.get("overall_rank") != i:
            moved += 1
        p["overall_rank"] = i
        org_counters[org] = org_counters.get(org, 0) + 1
        p["org_rank"] = org_counters[org]
        p["org_rank_total"] = org_totals[org]
        meaningful = tie_count.get(grade, 0) <= RANK_TIE_BLOCK_MAX
        pk = p.get("player_key")
        prior = sorted((h for h in (hist.get(pk) or [])
                        if h.get("rank") is not None and h.get("snapshot_date") != today),
                       key=lambda h: str(h.get("snapshot_date") or ""))
        p["prev_overall_rank"] = int(prior[-1]["rank"]) if (prior and meaningful) else None
        mv = None
        if meaningful and prior:
            m = compute_rank_movement(list(prior) + [{"snapshot_date": today, "rank": i}])
            mv = m if m.get("basis") == "rank_step" else None
        p["rank_movement"] = mv
        if i <= 10:
            top.append((i, pk, grade))
    for p in section_rows:
        if p.get("overall_rank") is not None:
            moved += 1
        tail = p.get("board_key_tail") or []
        org = str((list(tail) + [None] * 5)[4] or "?")
        p["overall_rank"] = None
        p["org_rank"] = None
        p["org_rank_total"] = org_totals.get(org, 0)
        p["prev_overall_rank"] = None
        p["rank_movement"] = None
    payload["prov_section"] = dict(prov_section_state(), n_board_rows=len(section_rows))

    # Every other top-level block (run, data_freshness, generated_at) passes through
    # untouched: this rewrites rank fields only, and a re-bake that dropped the
    # freshness stamps would blank the PROSPX tab "as of" lines (RPR09).
    from datetime import datetime as _dt, timezone as _tz
    payload["board_rank_rebake"] = {
        "at": _dt.now(_tz.utc).isoformat(timespec="seconds"),
        "n_active": len(rows), "n_moved": moved, "n_without_tail": n_without_tail,
        "basis": board_basis_fingerprint(),
        "what": ("overall_rank / org_rank re-baked on the eFV file current at this stamp "
                 "(storage.rebake_board_ranks); before this stamp the baked rank reflected "
                 "the previous run's eFV file"),
    }
    written = False
    if write:
        tmp = out_path.with_name(out_path.name + f".rebake{os.getpid()}")
        try:
            tmp.write_bytes(_payload_bytes(payload))
            _atomic_replace(tmp, out_path)
            written = True
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
        if update_metric_snapshots:
            try:
                with connect() as con:
                    n_today = con.execute(
                        "SELECT COUNT(*) FROM metric_snapshots WHERE snapshot_date = ?",
                        (today,)).fetchone()[0]
                    if n_today:
                        con.executemany(
                            "UPDATE metric_snapshots SET overall_rank = ? "
                            "WHERE player_key = ? AND snapshot_date = ?",
                            [(p["overall_rank"], p["player_key"], today)
                             for _, p, _, _ in rows if p.get("player_key")]
                            + [(None, p["player_key"], today)
                               for p in section_rows if p.get("player_key")])
                        lg.info("rebake_board_ranks: refreshed overall_rank on %d "
                                "metric_snapshots rows dated %s", n_today, today)
            except sqlite3.OperationalError as e:           # pragma: no cover
                lg.warning("rebake_board_ranks: metric_snapshots not updated (%s)", e)
    msg = (f"{len(rows)} active rows re-ranked on the current eFV file, {moved} moved"
           + (f", {len(section_rows)} rows in the not-yet-graded section carry no shared rank"
              if section_rows else "")
           + (f", {n_without_tail} rows without a tail left alone" if n_without_tail else ""))
    lg.info("rebake_board_ranks: %s", msg)
    return {"written": written, "n_active": len(rows), "n_moved": moved,
            "n_section": len(section_rows),
            "n_without_tail": n_without_tail, "message": msg, "top": top}


def xfv_history_basis() -> str | None:
    """The board basis data/xfv_history.json was BUILT on, or None if it is unstamped.

    efv_score.score_history stamps it (2026-07-30). An unstamped file is by definition
    pre-stamp, i.e. the retired per-side quantile series, and is treated as foreign."""
    base = Path(__file__).parent / "data"
    try:
        doc = json.loads((base / "xfv_history.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    b = doc.get("basis") if isinstance(doc, dict) else None
    return str(b) if b else None


def xfv_history_is_on_board_basis() -> bool:
    """THE MOVEMENT-SUPPRESSION GATE for the eFV delta (A2 / Phase 3.2, 2026-07-30).

    BOARD_RANK_BASIS_EPOCH's strictly-after gate in load_rank_history covers the RANK
    movement signal, because rank history lives in metric_snapshots as append-only rows
    that can be dated and filtered. It does NOT cover the owner's PRIMARY movement signal,
    the eFV delta: movement.xfv_movement reads data/xfv_history.json, which
    efv_score.score_history REBUILDS in full on every run and which carries no per-point
    basis. Nothing in the epoch machinery can see that file, so bumping the epoch alone
    would have left the eFV delta unguarded through this grade-scale change -- the same
    hole that let the 2026-07-29 re-rank reach Seth Hernandez's card as real movement.

    The gate: publish the eFV-delta override only when the series on disk was built on the
    basis the board is serving right now. The two go out of step for exactly the runs
    between a basis change landing in code and the next production regen writing a series
    on it -- the one-run lag _load_xfv_join documents. In that window the eFV override is
    withheld and movement falls back to compute_genuine_movement's consensus same-source
    step, which is the documented fallback for a player with no eFV series at all, not a
    new code path. It clears itself: the next regen stamps the current basis and the
    override returns.

    SCOPE, stated because the narrower choice was deliberate. This gates the MOVEMENT
    override only. The $DvM+ appreciation RATE also reads the series (via _xfv_series) and
    is NOT gated: it is a within-series first-point-to-last-point rate, so a foreign-basis
    series still gives it an internally consistent number, and withholding it would swing
    $DvM+ for the whole board for one run to fix a coherence problem that predates this
    change. Registered as an owner call in POOLED_OUTCOME_REFIT.md, not silently taken."""
    b = xfv_history_basis()
    return bool(b) and b == board_basis_fingerprint()


def _load_ungraded_by_org() -> dict[str, list[dict]]:
    """Provisional (source-UNGRADED) prospects grouped by org, as lightweight prospect-dicts
    for the farm depth/top-end pool (xfv_ungraded.json, one-run lag like the eFV join). Each
    carries an xfv_grade so _eff_grade ranks it alongside graded prospects; filler (FV 20-30)
    ranks out of the top-25 (FV_POINTS ~0) and the genuine breakouts add bounded depth. We do
    NOT add these to any raw-sum / DvM+ / surplus accumulator -- only the rank-and-tier pool."""
    base = Path(__file__).parent / "data"
    out: dict[str, list[dict]] = {}
    try:
        by_player = json.loads((base / "xfv_ungraded.json").read_text(encoding="utf-8")).get("by_player") or {}
    except Exception:
        return out
    for e in by_player.values():
        org = e.get("org")
        g = e.get("xfv_grade")
        if not org or g is None:
            continue
        out.setdefault(org, []).append({
            "name": e.get("name"), "player_key": e.get("player_key"), "pos": e.get("position"),
            "age": e.get("age"), "fv_raw": None, "xfv_grade": float(g), "provisional": True,
        })
    return out


# Hardcoded industry-standard FV → expected career WAR mapping.
# Anchored to FanGraphs / public research:
# https://blogs.fangraphs.com/the-new-fangraphs-scouting-primer/
# Each FV tier maps to a typical career WAR projection at MLB retirement.
# Used by _grad_wag() to compute WAR Above Grade per graduate, which then
# rolls up to the per-org Talent Translation report-card grade.
FV_EXPECTED_WAR = {
    80: 60.0,   # HOF-tier (10+ year stars)
    75: 40.0,
    70: 25.0,   # Perennial All-Star
    65: 17.0,
    60: 12.0,   # Strong everyday regular
    55:  6.0,
    50:  3.0,   # Average regular
    45:  1.5,
    40:  0.5,
    35:  0.1,
    30:  0.0,
    25:  0.0,
    20:  0.0,
}


def _fv_to_expected_war(fv: float | int | None) -> float | None:
    """Linear-interpolate FV (20-80) → expected career WAR via FV_EXPECTED_WAR.
    Returns None for None / out-of-range inputs so the caller can distinguish
    'no projection' from 'projected 0 WAR' (which is a valid 35-FV projection)."""
    if fv is None:
        return None
    try:
        v = float(fv)
    except (TypeError, ValueError):
        return None
    if v < 20 or v > 80:
        return None
    keys = sorted(FV_EXPECTED_WAR.keys())
    if v <= keys[0]:
        return FV_EXPECTED_WAR[keys[0]]
    if v >= keys[-1]:
        return FV_EXPECTED_WAR[keys[-1]]
    for i in range(len(keys) - 1):
        lo, hi = keys[i], keys[i + 1]
        if lo <= v <= hi:
            t = (v - lo) / (hi - lo) if hi > lo else 0
            return round(FV_EXPECTED_WAR[lo] + t * (FV_EXPECTED_WAR[hi] - FV_EXPECTED_WAR[lo]), 2)
    return None


# FV → expected WAR-per-year — the SURVIVOR expectation WAG measures graduates
# against. v-arkmetric-audit: this is now DERIVED from value_framework's
# `survivor_expected_war` (the same calibrated bucket model the surplus uses,
# conditioned on non-bust), so WAG and the surplus model can no longer drift onto
# inconsistent FV->WAR assumptions. The tables below are a STALE FanGraphs-primer
# fallback used only if the engine is unavailable; they ran ~2-3x over realized
# graduate outcomes (mean 0.34/0.77/0.94/1.23 WAR/yr at FV 45/50/55/60), which is
# exactly why graduates read as systematically negative-WAG before this fix. The
# frontend `FV_WAR_ANCHORS` mirror is synced to the derived survivor curve.
FV_EXPECTED_WAR_PER_YR_HITTER = {
    30: -0.1, 40: 0.0, 45: 0.8, 50: 1.6, 55: 2.5, 60: 3.4, 70: 5.0, 80: 7.0,
}

# ONE WAG DEFINITION (design audit F25, audit L13-03). ON since 2026-09-11: the owner
# chose to flip it now rather than at the eWAR label epoch (decision 14b).
#
# True (served): the engine WAG (value_framework.wag) on the eFV grade at debut is THE
# WAG. It is baked once per graduate (the _debuted_block_for memo in
# export_timeseries_json) and every surface reads that block: the payload's top-level
# boom_label, the farm rollup's graded Boom/Bust leaves and its Talent Translation
# display leaf, and PROSPX, which the `wag_definition` stamp on timeseries.json switches
# over. Folded in: the legacy survivor read is clamped to the fit support (L13-01) and
# the legacy positive branch loses its level term (L13-06), so what survives of the
# legacy path for a direct caller is a monotone residual. One direct caller remains:
# overseas_export's signing column still calls _grad_wag (7 of its 14 served values
# move with the flip, 2026-09-11 reading).
#
# False rolls back decision 14b ONLY: the list, the farm rollup and the client go back
# to the legacy transform (three computations on three baselines and three grades).
# It does NOT roll back decision 14c: the measured career-WAR exposure the engine gate
# reads (_career_war_exposure, WAG_EXPOSURE_STINTS_FIRST) is independent of this flag,
# so with the flag off the card's engine block, the surplus cell and the engine sort
# still gate on it and still carry the exposure_source / _load / _unit keys.
WAG_UNIFIED = True
WAG_DEFINITION = "engine_at_debut"


def _farm_grad_wag_and_label(wag_payload: dict, label_payload: dict,
                             block: dict | None) -> tuple[float | None, str]:
    """(WAG, boom/bust label) for one graduate in the org rollup.

    WAG_UNIFIED False: the two legacy reads exactly as the rollup always made them, the
    display WAG on `wag_payload` (eFV grade) and the GRADED label on `label_payload`
    (consensus FV). True: both from the baked engine `block` (debuted_value), the WAG
    only where the card shows one (measured exposure past the gate)."""
    if WAG_UNIFIED:
        w = (block or {}).get("wag") or {}
        wag = (float(w["regressed_wag"])
               if w.get("regressed_wag") is not None and not w.get("below_meaningful_exposure")
               else None)
        return wag, (w.get("boom_label") or "unsettled")
    return _grad_wag(wag_payload), _compute_boom_bust(label_payload)
FV_EXPECTED_WAR_PER_YR_PITCHER = {
    30: -0.1, 40: 0.0, 45: 1.0, 50: 1.8, 55: 2.6, 60: 3.5, 70: 5.0, 80: 7.0,
}


def _fv_to_expected_war_per_yr(fv, is_pitcher: bool = False) -> float | None:
    """FV → SURVIVOR expected WAR/yr, derived from the surplus model
    (value_framework.survivor_expected_war) so WAG is measured on the SAME FV->WAR
    calibration as the surplus. Falls back to the legacy primer table only if the
    engine can't price it. None for None / out-of-range."""
    if fv is None:
        return None
    try:
        v = float(fv)
    except (TypeError, ValueError):
        return None
    # BELOW THE SCALE FLOOR IS "NO GRADE", NOT A GRADE (audit L15-F2, 2026-09-11).
    # FV lives on the 20-80 scale and the board serves 20.0 as its floor, so nothing
    # below 20 is a real grade. 152 graduate rows carry an FV-0 SENTINEL, and
    # survivor_expected_war extrapolates that to 11.84 WAR per year for a hitter,
    # so every one of them was measured against an expectation no real player meets
    # and 136 were labelled 'bust'. Returning None here makes WAG None, which
    # _compute_boom_bust already reads as 'unsettled', the honest label for a player
    # with no grade to be measured against. Contained by verification: this has one
    # caller (_grad_wag), no graduate with points sits below FV 30, and the sentinel
    # rows carry no points, so no org bucket, farm grade or rendered pill moves.
    if v < 20.0:
        return None
    if WAG_UNIFIED:
        # L13-01: under the fit support the survivor curve runs BACKWARDS (FV 20 reads
        # 0.36 WAR/season, FV 35 reads 0.05, FV 40 0.24), so a lower grade was held to a
        # higher bar. Read it at the support edge instead; above it the curve is monotone.
        try:
            import value_framework as _vf
            v = max(v, float(_vf._config()["fit"]["support_fv"][0]))
        except Exception:
            pass
    try:
        import value_framework as _vf
        derived = _vf.survivor_expected_war(v, is_pitcher)
        if derived is not None:
            return round(float(derived), 3)
    except Exception:
        pass
    table = FV_EXPECTED_WAR_PER_YR_PITCHER if is_pitcher else FV_EXPECTED_WAR_PER_YR_HITTER
    keys = sorted(table.keys())
    if v <= keys[0]:
        return table[keys[0]]
    if v >= keys[-1]:
        return table[keys[-1]]
    for i in range(len(keys) - 1):
        lo, hi = keys[i], keys[i + 1]
        if lo <= v <= hi:
            t = (v - lo) / (hi - lo) if hi > lo else 0
            return round(table[lo] + t * (table[hi] - table[lo]), 3)
    return None


# FALLBACK draft pick-slot value table (hand-set, career-WAR basis,
# "industry research" provenance). Model-audit Phase 4b measured it
# against realized outcomes (data/draft_slot_curve.json): it UNDERSHOOTS
# realized career means ~3x at every slot (e.g. pick 1: realized 28.4
# vs 9.0 here on resolved 2005-14 cohorts). The live lookup now uses
# the fitted first-six-season curve (_fitted_slot_curve); this table
# only serves when the committed artifact is missing. Consumer:
# "draft pick value above expectation" = actual_war − slot_expected_war,
# which credits orgs that beat the market at each pick slot (e.g., a
# 28th-rounder making the majors counts more than a #1 overall reaching
# the same outcome).
_PICK_SLOT_EXPECTED_WAR: list[tuple[int, float]] = [
    (1,    9.00),   # 1st overall — historical Trout-tier ceiling
    (5,    6.00),   # top 5 — All-Star floor
    (10,   4.00),   # top 10 — regular floor
    (20,   2.50),   # 1st round
    (35,   1.80),   # supplemental / late 1st
    (50,   1.20),   # mid-2nd
    (75,   0.80),   # late 2nd / 3rd
    (100,  0.55),   # 3rd-4th
    (150,  0.35),   # 4th-5th
    (200,  0.22),   # mid-rounds
    (300,  0.13),   # 6th-10th
    (500,  0.07),   # late rounds
    (10_000, 0.03), # undrafted / non-tracked tail
]


_FITTED_SLOT_CURVE: list[tuple[int, float]] | None = None
_FITTED_SLOT_LOADED = False


def _fitted_slot_curve() -> list[tuple[int, float]] | None:
    """The REALIZED slot curve (model-audit Phase 4b, WS-8): expected
    FIRST-SIX-MLB-SEASON bWAR by pick, fitted by decreasing isotonic on
    StatsAPI draft history 2005-2014 x war_daily (signed picks; never-MLB
    scores 0). Committed in data/draft_slot_curve.json by
    tools/fit_draft_slot_curve.py. The first-6 window matches how the
    leaf consumes it (graduates' career-to-date WAR, almost always <= 6
    MLB seasons) and the QO tax's control-window basis. The hand-set
    table below remains the fallback when the artifact is absent."""
    global _FITTED_SLOT_CURVE, _FITTED_SLOT_LOADED
    if not _FITTED_SLOT_LOADED:
        _FITTED_SLOT_LOADED = True
        try:
            d = json.loads((Path(__file__).parent / "data" /
                            "draft_slot_curve.json").read_text(encoding="utf-8"))
            steps = [(int(b), float(w)) for b, w in d["first6_step_curve"]
                     if w is not None]
            _FITTED_SLOT_CURVE = steps or None
        except (OSError, ValueError, KeyError, TypeError):
            _FITTED_SLOT_CURVE = None
    return _FITTED_SLOT_CURVE


def _pick_slot_expected_war(pick_overall) -> float | None:
    """Step-lookup the expected first-six-season bWAR for a draft slot
    (fitted realized curve; hand-set career-WAR steps as fallback).
    Returns None when the pick number is missing/invalid (e.g., IFA
    signing with no overall pick). The step function is a deliberate
    simplification over the smooth power curve — pick slots already
    quantize into round groupings, and the step boundaries align with
    common round breakpoints (top-5, top-10, 1st round, 2nd, etc.)."""
    if pick_overall is None:
        return None
    try:
        p = int(pick_overall)
    except (TypeError, ValueError):
        return None
    if p < 1:
        return None
    table = _fitted_slot_curve() or _PICK_SLOT_EXPECTED_WAR
    for threshold, war in table:
        if p <= threshold:
            return war
    return table[-1][1]


def _grad_wag_cumulative(graduate_payload: dict) -> float | None:
    """Legacy career-cumulative WAG: actual career WAR minus FV-implied
    CAREER WAR. Biased against mid-career grads who haven't accumulated
    yet (a 2-yr Yamamoto with 4 WAR vs FV 65/17 expected reads as −13).
    Kept for any consumer that needs the long-horizon view.

    The CURRENT default is `_grad_wag` (below), which is rate-based and
    matches the frontend WAG pill."""
    cw = graduate_payload.get("career_war") or {}
    total_war = cw.get("career_war")
    fv_close = graduate_payload.get("fv_close_raw")
    if fv_close is None:
        fv_close = graduate_payload.get("fv_close")
    if total_war is None or fv_close is None:
        return None
    expected = _fv_to_expected_war(fv_close)
    if expected is None:
        return None
    return round(float(total_war) - expected, 2)


# v14 — Role-typical full-season workload targets. Loaded once on module
# import; the JSON file is a static lookup refreshed annually from the
# offline aggregator. Falls back to hardcoded MLB qualifier defaults if
# the file is missing or malformed.
_ROLE_BASELINE_DEFAULTS = {
    "hitter_pa_target": 612.0,
    "sp_ip_target":     175.0,
    "mirp_ip_target":    65.0,
    "sirp_ip_target":    50.0,
    "cl_ip_target":      60.0,
}


def _load_role_full_season_baselines() -> dict[str, float]:
    path = Path(__file__).parent / "data" / "role_full_season_baselines.json"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_ROLE_BASELINE_DEFAULTS)
    out = dict(_ROLE_BASELINE_DEFAULTS)
    for k in _ROLE_BASELINE_DEFAULTS:
        v = raw.get(k)
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f > 0:
            out[k] = f
    return out


_ROLE_BASELINES = _load_role_full_season_baselines()


def _pitcher_role(graduate_payload: dict) -> str:
    """Bucket a pitcher into SP / MIRP / SIRP / CL using the position
    string, then apply the usage mirror: the position-string signal is
    FG-driven consensus (which breaks out SP/MIRP/SIRP/CL when it can),
    and games-started isn't on the payload stats, so a relief bucket is
    cross-checked against the milb_history cache via role_usage (rule
    D: current-season MiLB GS-share >= 0.50, IP/G >= 3.0, IP >= 20
    upgrades mirp/sirp to sp). Falls back to MIRP when the position is
    just RHP/LHP/P/RP without role detail."""
    pos = (graduate_payload.get("position") or "").upper()
    # Split on "/" — a "MIRP/SIRP" prospect leans MIRP.
    tokens = [t.strip() for t in pos.split("/") if t.strip()]
    if any(t in ("CL", "CP") for t in tokens):
        return "cl"
    if any(t == "SP" for t in tokens):
        return "sp"
    if any(t == "SIRP" for t in tokens):
        role = "sirp"
    elif any(t == "MIRP" for t in tokens):
        role = "mirp"
    else:
        # Generic RP / RHP / LHP / P → assume multi-inning fallback.
        role = "mirp"
    # Usage mirror (rule D, role_usage.py). Import-guarded so storage
    # never hard-fails when role_usage or the milb_stats cache is
    # absent; the cache read itself is offline (fetch=False) and any
    # missing data leaves the position-string bucket unchanged.
    try:
        from role_usage import current_season_pitching, starter_by_usage
    except ImportError:
        return role
    line = current_season_pitching(graduate_payload.get("mlbam_id"),
                                   date.today().year)
    if line and starter_by_usage(line.get("g"), line.get("gs"), line.get("ip")):
        return "sp"
    return role


def _is_pitcher_graduate(graduate_payload: dict) -> bool:
    from stat_flags import is_pitcher
    if is_pitcher(graduate_payload.get("position")):
        return True
    saberm = graduate_payload.get("sabermetrics") or {}
    return saberm.get("is_pitcher") is True


def _career_pa_ip(graduate_payload: dict) -> tuple[int, float]:
    """Sum career_stats rows for total MLB PA + IP.

    v15 — Restricts to MLB-level rows only (was: all levels, which
    inflated the denominator and broke per-graduate WAG calc for orgs
    whose grads have lots of MiLB time). Also falls back to AB×1.13
    (typical PA:AB ratio) when PA is missing — the public stats payload
    sometimes ships AB without PA, especially for graduate exports.
    Used by both the WAG sample floor and the full-season-rate denom.
    """
    rows = graduate_payload.get("career_stats") or []
    total_pa = 0
    total_ip = 0.0
    for s in rows:
        # Only MLB rows count toward the MLB-rate-based WAG.
        if s.get("level") != "MLB":
            continue
        try:
            pa = int(s["pa"]) if s.get("pa") is not None else None
        except (TypeError, ValueError):
            pa = None
        if pa is None:
            # Fall back to AB × ~1.13 (league-wide PA:AB ratio is ~1.135 —
            # walks + HBP + sacrifices push PA above AB). Better than
            # dropping the row entirely when PA isn't on file.
            # Only when PA is ABSENT (audit L13-05, 2026-09-11): a recorded PA of 0
            # is a measured zero and stays zero, never replaced by a conversion.
            pa = 0
            try:
                ab = int(s.get("ab") or 0)
            except (TypeError, ValueError):
                ab = 0
            if ab > 0:
                pa = int(round(ab * 1.13))
        total_pa += pa
        try:
            total_ip += float(s.get("ip") or 0)
        except (TypeError, ValueError):
            pass
    return total_pa, total_ip


def _graduate_outcome_penalty(graduate_payload: dict) -> float:
    """Dampen positive WAG for older churn profiles.

    WAG is meant to surface genuinely surprising MLB outcomes, not simply
    low-FV players who briefly banked WAR and then fell into the DFA/outright
    loop. This only affects positive WAG; underperformance is not softened.
    """

    txs = graduate_payload.get("transactions") or []
    churn_kinds = {"dfa", "outrighted", "released"}
    churn_count = sum(1 for tx in txs if (tx.get("kind") or "").lower() in churn_kinds)
    age = graduate_payload.get("age")
    try:
        age = float(age) if age is not None else None
    except (TypeError, ValueError):
        age = None
    current_level = (graduate_payload.get("current_level")
                     or graduate_payload.get("level")
                     or "").upper()
    in_minors_now = current_level and current_level != "MLB"
    penalty = 1.0
    if churn_count >= 2:
        penalty *= 0.45
    elif churn_count == 1:
        penalty *= 0.72
    if age is not None and age >= 26.0:
        penalty *= 0.85
    if in_minors_now:
        penalty *= 0.85
    return max(0.25, min(1.0, penalty))


def _grad_wag(graduate_payload: dict) -> float | None:
    """v14 WAG (WAR Above Grade) — role-adjusted full-season-equivalent.

    Computes WAR-per-(PA|IP) from career totals, projects to a
    full-season workload baseline for the player's role, then subtracts
    the FV-implied per-season WAR. The full-season projection corrects
    the cycle-13 bug where mid-career grads with elite rates (e.g.
    Junior Caminero, 4.6 WAR over ~510 PA at FV 55) read as negative
    WAG simply because they hadn't accumulated a full season yet.

    Sample-size floor:
      - Hitters: career_pa ≥ 150
      - Pitchers: career_ip ≥ 50
    Below the floor, returns None (avoids cup-of-coffee noise driving
    BOOM/BUST pills).

    Full-season targets come from `data/role_full_season_baselines.json`
    (MLB qualifier medians, refreshed annually).
    """
    cw = graduate_payload.get("career_war") or {}
    total_war = cw.get("career_war")
    fv_close = graduate_payload.get("fv_close_raw")
    if fv_close is None:
        fv_close = graduate_payload.get("fv_close")
    if total_war is None or fv_close is None:
        return None
    try:
        career_war = float(total_war)
    except (TypeError, ValueError):
        return None

    is_pitcher = _is_pitcher_graduate(graduate_payload)
    total_pa, total_ip = _career_pa_ip(graduate_payload)

    # v15 — When the MLB PA/IP denominator is below the sample floor (e.g.
    # because the public stats payload didn't surface PA for this graduate,
    # or because the player has only a partial cup-of-coffee), fall back to
    # the cached `war_per_yr` rate. That field uses the same WAR pool and
    # the per-graduate season count, so it produces a clean rate-based
    # comparison. The fallback still gates on having war_per_yr available.
    war_per_yr = None
    try:
        if cw.get("war_per_yr") is not None:
            war_per_yr = float(cw.get("war_per_yr"))
    except (TypeError, ValueError):
        war_per_yr = None

    # v16 — WAG matched to SEASONS, not PA / rate of production: the per-season WAR
    # (career WAR over the number of MLB seasons) vs the FV-implied WAR/season. An
    # injury-shortened season still counts as a season, so WAG reflects accumulation
    # over time rather than a small-sample rate projected up to a full season (which
    # over-credited injury-limited / partial-season grads like Evan Carter). The
    # PA/IP floor still gates cup-of-coffee samples below the sample minimum.
    season_count = (cw.get("war_seasons_count")
                    or len(cw.get("seasons") or {})
                    or len({s.get("season")
                            for s in (graduate_payload.get("career_stats") or [])
                            if s.get("level") == "MLB" and s.get("season") is not None}))
    floor_ok = (total_ip >= 50.0) if is_pitcher else (total_pa >= 150)
    full_season_war: float | None = None
    if season_count and floor_ok:
        full_season_war = career_war / season_count
    elif war_per_yr is not None:
        full_season_war = war_per_yr

    if full_season_war is None:
        return None

    expected = _fv_to_expected_war_per_yr(fv_close, is_pitcher=is_pitcher)
    if expected is None:
        return None
    delta = full_season_war - expected
    # L13-06: under WAG_UNIFIED the residual stays a residual. The transform below adds a
    # level term (0.30 x WAR/season at delta 0+), so E[WAG | on grade] is not zero, and
    # its penalty reads CURRENT age and level to modify PAST production.
    if delta > 0 and not WAG_UNIFIED:
        # Positive surprise should still require current MLB production.
        # Blend WAG with actual WAR/yr, then dampen churn/older-minors
        # profiles so DFA-circus players do not top the leaderboard.
        delta = (delta * 0.70 + full_season_war * 0.30)
        delta *= _graduate_outcome_penalty(graduate_payload)
    return round(delta, 2)


def _compute_boom_bust(graduate_payload: dict) -> str:
    """Categorize a graduate as boom / bust / settled / unsettled,
    anchored on the v14 full-season-equivalent WAG.

    Returns one of:
      "boom"      — WAG ≥ +2.5, meets sample floor
      "bust"      — WAG ≤ −1.5, meets sample floor
      "settled"   — meets sample floor but landed in the middle band
      "unsettled" — no WAG, or sample too small to call

    Sample-size floor: ≥2 MLB seasons OR ≥800 career PA OR ≥200 career IP.
    Cup-of-coffee debuts stay 'unsettled' so we don't mislabel them on
    light samples.

    Thresholds re-tuned for the v14 full-season-equivalent WAG (which
    has a wider spread than the v13 per-year rate, because mid-career
    grads' rates project up to a full season instead of being penalized
    for partial accumulation). BOOM at +2.5 ≈ "outperformed FV by half
    a tier across a projected full season"; BUST at −1.5 ≈ "fell short
    by similar magnitude". Matches the frontend boomBustPillHTML
    threshold."""
    wag = _grad_wag(graduate_payload)
    cw = graduate_payload.get("career_war") or {}
    seasons = cw.get("war_seasons_count") or 0
    total_pa, total_ip = _career_pa_ip(graduate_payload)
    meets_floor = (seasons >= 2) or (total_pa >= 800) or (total_ip >= 200)
    if wag is None or not meets_floor:
        return "unsettled"
    if wag >= 2.5:
        return "boom"
    if wag <= -1.5:
        return "bust"
    return "settled"


# ── v4 farm-tree leaves: top-end / Conviction / spend ROI ──────────────
# These four helpers feed the new MLB Production + Financial leaves
# (`mlb_production_top_grads`, `mlb_production_conviction`,
# `fin_draft_pool_efficiency`, `fin_ifa_roi`). Each consumes the per-org
# `grad_agg` bucket the upstream pass already accumulated (specifically
# `_top_grads` / `_draft_pool_grads` / `_ifa_grads`) plus the relevant
# spend table.

# Conviction threshold: a "star-tier grad" is one with WAR/yr ≥ 4.0 in the
# trailing 6 years OR career WAR ≥ 12 ever. The OR cuts both ways — a
# Skenes-style burst (huge WAR/yr, only 1-2 seasons) registers via the
# WAR/yr branch; a long-career All-Star (Trout-tier, several 5+ WAR
# seasons) registers via the career WAR branch. Bumped 5→6yr in v6 so
# the recency window aligns with the org-level 6y DvM+ framing — every
# "principal window" metric on the site lives on the same horizon.
_CONVICTION_WAR_PER_YR_THRESHOLD = 4.0   # legacy — superseded by STAR_*
_CONVICTION_CAREER_WAR_THRESHOLD = 12.0  # legacy — superseded by STAR_*
_CONVICTION_RECENCY_YEARS        = 7   # was 6 — unified to FARM_PRINCIPAL_WINDOW (7y)
# v30.7 — Conviction reframed as "star count." A graduate the org
# developed qualifies as a STAR when EITHER:
#   * career WAR/yr ≥ 3.0 (sustained above-average MLB regular), OR
#   * any single season recorded WAR ≥ 3.5 (one-year breakout / peak)
# The leaf score becomes the COUNT of qualifying stars (capped to a
# reasonable ceiling at the leaf-100 normalization layer), not the
# binary 0/1 it used to be. More stars = stronger conviction signal.
_STAR_WAR_PER_YR_THRESHOLD = 3.0
_STAR_SEASON_WAR_THRESHOLD = 3.5

# v30.8 — Level-confidence weights for the per-prospect Tool DvM+
# aggregation. Each prospect's tool delta is multiplied by their
# current level's weight before contributing to the org's per-tool
# mean. AA peaks because that's the real-prospect filter; DSL/CPX
# deflate because grades at those levels are heavy projection vs
# realized signal. Unknown levels default to 1.0 (no effect).
_TOOL_DEV_LEVEL_WEIGHTS: dict[str, float] = {
    "DSL": 0.50,
    "CPX": 0.60,
    "A":   0.80,
    "A+":  0.95,
    "AA":  1.20,
    "AAA": 1.10,
    "MLB": 1.00,
}


def _compute_top_grads_leaf(gagg: dict) -> dict:
    """Top-3 grad WAR/yr mean — uses only grads that cleared the boom-
    bust sample floor (already filtered into `_top_grads` upstream).
    Gates at ≥3 qualifying grads or returns None (`top3_war_per_yr`)."""
    grads = gagg.get("_top_grads") or []
    # VAL_4: each record carries the club's development share `w`; the leaf reads
    # the WAR/yr credited to the club (share x WAR/yr). w is 1.0 for a graduate one
    # club developed alone, and absent on records built before VAL_4.
    yvals = [g.get("w", 1.0) * g["war_per_yr"] for g in grads
             if g.get("war_per_yr") is not None]
    yvals.sort(reverse=True)
    top3 = yvals[:3]
    return {
        "top3_war_per_yr": (round(sum(top3) / len(top3), 2)
                            if len(top3) >= 3 else None),
        "grad_count_qualifying": round(sum(g.get("w", 1.0) for g in grads), 2),
        # Also expose top-3 career WAR for the swapped mlb_*_wag input.
        "top3_career_war": _top3_career_war(grads, is_pitcher=None),
    }


def _top3_career_war(grads: list[dict], is_pitcher: bool | None) -> float | None:
    """Top-3 career WAR mean across a subset of grads. When is_pitcher
    is None, uses every grad in the list; when True/False, filters to
    that side. Returns None when fewer than 3 grads qualify."""
    if is_pitcher is None:
        pool = list(grads)
    else:
        pool = [g for g in grads if bool(g.get("is_pitcher")) == is_pitcher]
    cwars = sorted([g.get("w", 1.0) * g["career_war"] for g in pool
                    if g.get("career_war") is not None], reverse=True)[:3]
    return round(sum(cwars) / len(cwars), 2) if len(cwars) >= 3 else None


def _compute_conviction_leaf(gagg: dict, today: date | None = None) -> dict:
    """v30.7 — Star-count conviction leaf. Counts the org's developed
    grads who hit EITHER:
      * career WAR/yr ≥ 3.0 (sustained above-average MLB regular), OR
      * any single season recorded WAR ≥ 3.5 (one-year peak)
    Returns {star_count, star_names, conviction, ...} where
    `star_count` is the leaf-scoring metric and `star_names` (top 5
    by peak signal) drives the tooltip readout. The legacy `conviction`
    field stays on the payload as a back-compat binary so older
    cached frontends keep rendering, but the leaf scores on
    star_count exclusively (see LEAF_SPECS)."""
    grads = gagg.get("_top_grads") or []

    stars: list[dict] = []
    for g in grads:
        wpy = g.get("war_per_yr") or 0.0
        cwa = g.get("career_war") or 0.0
        # Per-season peak — `seasons` may be either a {year: war} dict
        # (FanGraphs career_war shape) or a list/scalar depending on
        # the upstream aggregator. Be defensive: extract the maximum
        # single-season value when present, else fall back to 0.
        season_peak = 0.0
        seasons = g.get("seasons")
        try:
            if isinstance(seasons, dict):
                vals = [float(v) for v in seasons.values()
                        if v is not None and float(v) == float(v)]
                if vals:
                    season_peak = max(vals)
            elif isinstance(seasons, (list, tuple)):
                vals = [float(v) for v in seasons
                        if v is not None and float(v) == float(v)]
                if vals:
                    season_peak = max(vals)
            elif isinstance(seasons, (int, float)):
                # Legacy shape — a scalar season-count, not a per-year map.
                # Can't extract peak; leave at 0 so only WAR/yr can fire.
                season_peak = 0.0
        except (TypeError, ValueError):
            season_peak = 0.0
        is_career_star = wpy >= _STAR_WAR_PER_YR_THRESHOLD
        is_season_star = season_peak >= _STAR_SEASON_WAR_THRESHOLD
        if is_career_star or is_season_star:
            stars.append({
                "name":         g.get("player_name"),
                "war_per_yr":   round(wpy, 2),
                "career_war":   round(cwa, 2),
                "season_peak":  round(season_peak, 2),
                "reason":       "career" if is_career_star else "season",
                "w":            g.get("w", 1.0),
            })

    # Order stars by descending signal magnitude so the top 5 tooltip
    # surfaces the most-impressive contributors.
    stars.sort(key=lambda s: max(s["war_per_yr"], s["season_peak"]),
               reverse=True)
    # VAL_4: a star counts by the club's development share (graduate-equivalents).
    star_count = round(sum(s.get("w", 1.0) for s in stars), 2)
    peak_war_per_yr = max((s["war_per_yr"] for s in stars), default=None)
    peak_career_war = max((s["career_war"] for s in stars), default=None)
    peak_season_war = max((s["season_peak"] for s in stars), default=None)
    return {
        # NEW — leaf-scoring metric
        "star_count":       star_count,
        # Top 5 contributors for the tooltip (name + WAR/yr + season peak)
        "star_names":       [s["name"] for s in stars[:5] if s.get("name")],
        "stars":            stars[:5],
        # Aggregate peak signals (back-compat + tooltip context)
        "peak_war_per_yr":  round(peak_war_per_yr, 2) if peak_war_per_yr is not None else None,
        "peak_career_war": round(peak_career_war, 2) if peak_career_war is not None else None,
        "peak_season_war": round(peak_season_war, 2) if peak_season_war is not None else None,
        # Legacy binary conviction — kept so cached frontends keep
        # rendering. New leaf scoring keys on star_count instead.
        "conviction":      1 if stars else 0,
        "grad_count_qualifying": round(sum(g.get("w", 1.0) for g in grads), 2),
    }


# v31 — Ceiling threshold for HOF-track count. A graduate counts when
# any single season recorded WAR ≥ 5.0 (the standard "All-Star season"
# threshold; a 5-WAR season puts a player in roughly the top 25 of
# position players or top 15 of pitchers MLB-wide for that year).
# Stronger ceiling signal than Conviction's stars (which fires at
# career WAR/yr ≥ 3.0 OR season ≥ 3.5).
_HOF_TRACK_SEASON_WAR_THRESHOLD = 5.0


def _compute_hof_track_leaf(gagg: dict) -> dict:
    """v31 — HOF-track count. Counts grads whose peak single season
    recorded WAR ≥ 5.0. Sibling to Conviction (the broader star count
    leaf) — surfaces the "did this org develop legitimate All-Star-
    ceiling players, not just useful regulars" signal.

    Reads the same `_top_grads` per-grad records `_compute_conviction
    _leaf` uses; the peak-season extraction is identical (handles the
    {year: war} dict + list + scalar shapes defensively).
    """
    grads = gagg.get("_top_grads") or []
    hof_grads: list[dict] = []
    for g in grads:
        season_peak = 0.0
        seasons = g.get("seasons")
        try:
            if isinstance(seasons, dict):
                vals = [float(v) for v in seasons.values()
                        if v is not None and float(v) == float(v)]
                if vals:
                    season_peak = max(vals)
            elif isinstance(seasons, (list, tuple)):
                vals = [float(v) for v in seasons
                        if v is not None and float(v) == float(v)]
                if vals:
                    season_peak = max(vals)
        except (TypeError, ValueError):
            season_peak = 0.0
        if season_peak >= _HOF_TRACK_SEASON_WAR_THRESHOLD:
            hof_grads.append({
                "name":        g.get("player_name"),
                "season_peak": round(season_peak, 2),
                "career_war":  round(g.get("career_war") or 0.0, 2),
                "w":           g.get("w", 1.0),
            })
    hof_grads.sort(key=lambda s: s["season_peak"], reverse=True)
    return {
        # VAL_4: counted by the club's development share (graduate-equivalents)
        "hof_count":         round(sum(h.get("w", 1.0) for h in hof_grads), 2),
        "hof_names":         [h["name"] for h in hof_grads[:5] if h.get("name")],
        "hof_grads":         hof_grads[:5],
        "peak_season_war":   max((h["season_peak"] for h in hof_grads), default=None),
        "threshold":         _HOF_TRACK_SEASON_WAR_THRESHOLD,
        "grad_count_qualifying": round(sum(g.get("w", 1.0) for g in grads), 2),
    }


# v31 — Sub-leaf payload emitter. Walks the org's tree after every
# leaf has been stamped + scored and attaches a `sub_leaves` list to
# each leaf node that has a meaningful breakdown. The list is purely
# INFORMATIONAL — it doesn't feed back into the leaf score (the leaf
# score is already locked in by LEAF_SPECS). Renderer consumes the
# list to populate the third tree column ("what this leaf is made
# of"). Items are dicts of the form:
#   {label, kind, value, raw?, n?, weight?, sparse?}
# - label : human-readable sub-leaf name
# - kind  : "dvm" | "war" | "pct" | "usd" | "count" | "warpm" — drives
#           renderer formatting (e.g. "108" vs "32%" vs "+1.4 WAR")
# - value : the headline numeric (formatted by the renderer)
# - raw   : optional raw signal for tooltip use (e.g. underlying $)
# - n     : sample size (active count / grad count / etc.)
# - weight: optional bucket weight when the sub-leaf is one of N
#           weighted parts of the parent (e.g. C bucket = 0.35 of
#           hitter DvM+)
# - sparse: optional True when the sub-leaf is below sample floor
#           (renderer dims accordingly)
def _attach_sub_leaves(entry: dict) -> None:
    """Attach a `sub_leaves` array onto each tree node that has a
    natural breakdown. Idempotent — safe to call multiple times; the
    list is rebuilt from current tree state on every call."""
    tree = entry.get("tree") or {}

    # ── Development → Hitter / Pitcher DvM+ — pos-bucket sub-leaves ──
    # Pulled straight from the existing pos_buckets payload so the
    # sub-leaf values match the by-position-bucket grid that the
    # Dev tab already renders. Renderer treats "kind=dvm" as a
    # 100-anchored value (centered at league mean).
    # v31.5 — Hitter/Pitcher tool group sets feed the per-tool sub-
    # leaves alongside the position-bucket sub-leaves. Hitter tools:
    # HIT/PWR/SPD/FLD/ARM/PSEL/BCT. Pitcher pitches: FB/SL/CB/CH/CMD/CT.
    _HIT_TOOLS = [
        ("hit",       "HIT"),
        ("pwr",       "PWR"),
        ("speed",     "SPD"),
        ("field",     "FLD"),
        ("arm",       "ARM"),
        ("pitch_sel", "PSEL"),
        ("bat_ctrl",  "BCT"),
    ]
    _PIT_TOOLS = [
        ("fb",  "FB"),
        ("sl",  "SL"),
        ("cb",  "CB"),
        ("ch",  "CH"),
        ("cmd", "CMD"),
        ("ct",  "CT"),
    ]
    _PER_TOOL_BY_DEV = {
        "dev_hitter":  _HIT_TOOLS,
        "dev_pitcher": _PIT_TOOLS,
    }
    for dev_key in ("dev_hitter", "dev_pitcher"):
        node = tree.get(dev_key) or {}
        subs = []
        # Pos-bucket sub-leaves (existing behavior).
        pb = node.get("pos_buckets") or {}
        if pb:
            for bucket, v in pb.items():
                blend = (v.get("blend_by_window") or {}).get(FARM_PRINCIPAL_WINDOW)
                n     = v.get("active_count") or 0
                subs.append({
                    "label":  f"{bucket} bucket",
                    "kind":   "dvm",
                    "value":  blend,
                    "n":      n,
                    "weight": v.get("weight"),
                    "sparse": (n < 3),
                })
        # v31.5 — Per-tool DvM+ sub-leaves. Pulled from the org's
        # `tool_dev.per_tool_dvm_plus` map (computed in the league
        # pass earlier). Each tool's value is already 100-anchored
        # (Bayesian-shrunk + composite-stretched), so the renderer's
        # dvm tone (>100 green, <100 red) applies cleanly. Letter
        # grading happens in the post-attach league pass.
        tool_dev_per = ((entry.get("tool_dev") or {}).get("per_tool_dvm_plus") or {})
        for tool_key, tool_lbl in _PER_TOOL_BY_DEV[dev_key]:
            v = tool_dev_per.get(tool_key)
            subs.append({
                "label":  tool_lbl,
                "kind":   "dvm",
                "value":  v,
                "tier":   "per_tool",
                "sparse": v is None,
            })
        if subs:
            node["sub_leaves"] = subs

    # ── Acquisition → Draft Performance — round-tier WAR/yr breakdown ──
    # Sub-leaves now lead with the round-tier split (1st rd / Day 1 /
    # Late) so the user sees WHERE the org's draft value comes from.
    # Pick value + ceiling hits stay as supplementary signal lines.
    draft = tree.get("acq_draft") or {}
    if draft:
        subs = []
        rt = draft.get("round_tiers") or {}
        for tier_label, tier_data in rt.items():
            v = tier_data.get("war_per_yr_mean")
            n = tier_data.get("grad_count") or 0
            sparse = n < 3
            subs.append({
                "label":  tier_label,
                "kind":   "war",
                "value":  round(v, 2) if v is not None else None,
                "n":      n,
                "sparse": sparse,
                # Tier-style sub-leaf so the league pass can identify
                # it for letter grading.
                "tier":   "draft_round",
            })
        pv = draft.get("pick_value_mean") if draft.get("pick_value_mean") is not None \
             else draft.get("wag_mean")
        ch = draft.get("ceiling_hits_pct")
        if pv is not None:
            subs.append({
                "label": "Pick value vs slot",
                "kind":  "war",
                "value": round(pv, 2),
                "n":     draft.get("pick_value_count") or draft.get("grad_count"),
            })
        if ch is not None:
            subs.append({
                "label": "Ceiling hits",
                "kind":  "pct",
                "value": round(ch, 3),
                "n":     draft.get("draft_actives_count"),
                "raw":   f"{draft.get('ceiling_hits_count', 0)} of {draft.get('draft_actives_count', 0)} at FV ≥60",
            })
        if draft.get("sleeper_hit_rate") is not None:
            subs.append({
                "label": "Sleeper hit rate",
                "kind":  "pct",
                "value": round(draft["sleeper_hit_rate"], 3),
                "n":     draft.get("sleeper_low_fv_count"),
                "raw":   f"{draft.get('sleeper_hit_count', 0)} of {draft.get('sleeper_low_fv_count', 0)} low-FV (≤45 fv_open) draft grads cleared ≥2 WAR/yr",
            })
        if subs:
            draft["sub_leaves"] = subs

    # ── Acquisition → IFA Performance — bonus-tier WAR/yr breakdown ──
    # Same shape as draft round-tiers: tier sub-leaves first (Top / Mid
    # / Lower bonus bands), then the aggregate WAR/yr + Career WAR
    # mean as supplementary signal lines.
    ifa = tree.get("acq_ifa") or {}
    if ifa:
        subs = []
        bt = ifa.get("bonus_tiers") or {}
        for tier_label, tier_data in bt.items():
            v = tier_data.get("war_per_yr_mean")
            n = tier_data.get("grad_count") or 0
            sparse = n < 3
            subs.append({
                "label":  tier_label,
                "kind":   "war",
                "value":  round(v, 2) if v is not None else None,
                "n":      n,
                "sparse": sparse,
                "tier":   "ifa_bonus",
            })
        if ifa.get("war_per_yr_mean") is not None:
            subs.append({
                "label": "WAR/yr mean",
                "kind":  "war",
                "value": round(ifa["war_per_yr_mean"], 2),
                "n":     ifa.get("grad_count"),
            })
        if ifa.get("career_war_mean") is not None:
            subs.append({
                "label": "Career WAR mean",
                "kind":  "war",
                "value": round(ifa["career_war_mean"], 1),
                "n":     ifa.get("grad_count"),
            })
        if ifa.get("sleeper_hit_rate") is not None:
            subs.append({
                "label": "Sleeper hit rate",
                "kind":  "pct",
                "value": round(ifa["sleeper_hit_rate"], 3),
                "n":     ifa.get("sleeper_low_fv_count"),
                "raw":   f"{ifa.get('sleeper_hit_count', 0)} of {ifa.get('sleeper_low_fv_count', 0)} low-FV (≤45 fv_open) IFA grads cleared ≥2 WAR/yr",
            })
        if subs:
            ifa["sub_leaves"] = subs

    # ── Acquisition → Trade Acumen — inbound/outbound WAR + surplus splits ──
    tx = tree.get("tx_trades") or {}
    if tx:
        subs = []
        if tx.get("war_in") is not None:
            subs.append({
                "label": "Inbound WAR",
                "kind":  "war",
                "value": round(tx["war_in"], 1),
                "n":     tx.get("in_count") or 0,
            })
        if tx.get("war_out") is not None:
            subs.append({
                "label": "Outbound WAR",
                "kind":  "war",
                "value": round(tx["war_out"], 1),
                "n":     tx.get("out_count") or 0,
            })
        if tx.get("war_delta_unweighted") is not None:
            subs.append({
                "label": "Unweighted WAR Δ",
                "kind":  "war",
                "value": round(tx["war_delta_unweighted"], 1),
                "raw":   "Net WAR delta without recency decay",
            })
        # v31.8 — Surplus deltas (parallel signal to WAR, captures
        # uncrystallized prospect trades alongside debuted players).
        if tx.get("surplus_in") is not None:
            subs.append({
                "label": "Inbound surplus",
                "kind":  "usd",
                "value": round(tx["surplus_in"], 1),
                "n":     tx.get("surplus_in_count") or 0,
                "raw":   "Debuted players: career WAR × $8M/WAR · Prospects: FV-anchored surplus",
            })
        if tx.get("surplus_out") is not None:
            subs.append({
                "label": "Outbound surplus",
                "kind":  "usd",
                "value": round(tx["surplus_out"], 1),
                "n":     tx.get("surplus_out_count") or 0,
                "raw":   "Talent given up - same valuation as inbound side",
            })
        if tx.get("surplus_delta") is not None:
            subs.append({
                "label": "Surplus Δ",
                "kind":  "usd",
                "value": round(tx["surplus_delta"], 1),
                "raw":   "Recency-weighted net surplus delta (v31.8 co-scoring signal)",
            })
        if subs:
            tx["sub_leaves"] = subs

    # ── Acquisition → Waiver Claims — hit rate + volume context ──
    wv = tree.get("tx_waivers") or {}
    if wv:
        subs = []
        if wv.get("hit_rate") is not None:
            subs.append({
                "label": "Hit rate",
                "kind":  "pct",
                "value": round(wv["hit_rate"], 3),
                "n":     wv.get("claims_total") or 0,
                "raw":   f"{wv.get('claims_with_mlb', 0)} of {wv.get('claims_total', 0)} reached MLB",
            })
        if subs:
            wv["sub_leaves"] = subs

    # ── Development → Statcast Quality — org-wide + side split ──
    scq = tree.get("dev_statcast_quality") or {}
    if scq and scq.get("mean") is not None:
        subs = []
        if scq.get("hitter_mean") is not None:
            subs.append({
                "label": "Hitter SC+ mean",
                "kind":  "dvm",
                "value": round(scq["hitter_mean"], 0),
                "n":     scq.get("hitter_count"),
            })
        if scq.get("pitcher_mean") is not None:
            subs.append({
                "label": "Pitcher SC+ mean",
                "kind":  "dvm",
                "value": round(scq["pitcher_mean"], 0),
                "n":     scq.get("pitcher_count"),
            })
        subs.append({
            "label": "All graded actives",
            "kind":  "dvm",
            "value": round(scq["mean"], 0),
            "n":     scq.get("graded_count"),
        })
        scq["sub_leaves"] = subs

    # ── Development → Health Mgmt — IL signals (graded) + post-TJ
    # context (info-only as of v31.6). The org-wide + pitcher-side
    # post-TJ sub-leaves are emitted with `info_only: True` so the
    # renderer can skip letter-grading and show them as neutral-toned
    # context rows. Hitter post-TJ was removed entirely (hitter TJ
    # isn't a real metric). Pitcher IL share + Hitter IL share remain
    # letter-graded (lower = better) as side-specific injury exposure.
    hm = tree.get("dev_health_mgmt") or {}
    if hm and hm.get("active_count"):
        subs = []
        if hm.get("il_pct_current") is not None:
            subs.append({
                "label": "Currently on IL",
                "kind":  "pct",
                "value": round(hm["il_pct_current"], 3),
                "n":     hm.get("active_count"),
                "raw":   f"{hm.get('il_current_count', 0)} of {hm.get('active_count', 0)} sidelined",
            })
        if hm.get("il_days_mean") is not None:
            subs.append({
                "label": "Avg IL days / active (12mo)",
                "kind":  "count",
                "value": round(hm["il_days_mean"], 1),
                "n":     hm.get("active_count"),
            })
        # Per-side IL splits — graded (lower = better).
        if hm.get("il_pct_current_pit") is not None:
            subs.append({
                "label":  "Pitcher IL share",
                "kind":   "pct",
                "value":  round(hm["il_pct_current_pit"], 3),
                "n":      hm.get("actives_pit_count"),
                "tier":   "health_split",
            })
        if hm.get("il_pct_current_hit") is not None:
            subs.append({
                "label":  "Hitter IL share",
                "kind":   "pct",
                "value":  round(hm["il_pct_current_hit"], 3),
                "n":      hm.get("actives_hit_count"),
                "tier":   "health_split",
            })
        # v31.6 — Post-TJ rows are INFORMATIONAL ONLY. Both the org-
        # wide and pitcher-side post-TJ shares are emitted with
        # `info_only: True` so the renderer skips letter grading and
        # treats them as neutral context. Hitter post-TJ removed.
        if hm.get("post_tj_pct") is not None:
            subs.append({
                "label":    "Post-TJ share (info)",
                "kind":     "pct",
                "value":    round(hm["post_tj_pct"], 3),
                "n":        hm.get("active_count"),
                "raw":      f"{hm.get('post_tj_count', 0)} of {hm.get('active_count', 0)} with prior TJ - informational only, not graded",
                "info_only": True,
            })
        if hm.get("post_tj_pct_pit") is not None:
            subs.append({
                "label":     "Pitcher post-TJ % (info)",
                "kind":      "pct",
                "value":     round(hm["post_tj_pct_pit"], 3),
                "n":         hm.get("actives_pit_count"),
                "raw":       "informational only - post-surgery grace period often correlates with above-avg outcomes",
                "info_only": True,
            })
        if subs:
            hm["sub_leaves"] = subs

    # ── MLB Production → Hitter / Pitcher Production — bucket splits
    # + aggregate inputs. v31.5 — leads with per-position-bucket WAR/yr
    # (C/INF/OF for hitters, SP/RP for pitchers) so the user sees
    # WHICH bucket carries the org's production, then surfaces the
    # aggregate WAR/yr / Top-3 cum / WAG mean as supplementary
    # signal lines.
    _PROD_BUCKETS = {
        "mlb_hitter_production":  ("C", "INF", "OF"),
        "mlb_pitcher_production": ("SP", "RP"),
    }
    for prod_key in ("mlb_hitter_production", "mlb_pitcher_production"):
        prod = tree.get(prod_key) or {}
        if not prod:
            continue
        subs = []
        # Per-bucket sub-leaves (production split by position type).
        pb = prod.get("pos_buckets") or {}
        for bucket in _PROD_BUCKETS[prod_key]:
            cell = pb.get(bucket) or {}
            v = cell.get("war_per_yr_mean")
            n = cell.get("grad_count") or 0
            subs.append({
                "label":  f"{bucket} grads",
                "kind":   "war",
                "value":  round(v, 2) if v is not None else None,
                "n":      n,
                "sparse": (n < 3) or v is None,
                "tier":   "prod_bucket",
            })
        # Aggregate inputs (existing).
        if prod.get("war_per_yr_mean") is not None:
            subs.append({
                "label": "WAR/yr mean",
                "kind":  "war",
                "value": round(prod["war_per_yr_mean"], 2),
                "n":     prod.get("grad_count"),
            })
        if prod.get("top3_career_war") is not None:
            subs.append({
                "label": "Top-3 cum WAR",
                "kind":  "war",
                "value": round(prod["top3_career_war"], 1),
            })
        if prod.get("wag_mean") is not None:
            subs.append({
                "label": "WAG mean",
                "kind":  "war",
                "value": round(prod["wag_mean"], 2),
                "raw":   "vs FV-implied baseline",
                "n":     prod.get("grad_count"),
            })
        if subs:
            prod["sub_leaves"] = subs

    # ── MLB Production → Top Grads — top 3 names + WAR/yr ──
    top_grads = tree.get("mlb_production_top_grads") or {}
    if top_grads and top_grads.get("top3_war_per_yr") is not None:
        subs = [{
            "label": "Top-3 mean WAR/yr",
            "kind":  "war",
            "value": round(top_grads["top3_war_per_yr"], 2),
            "n":     top_grads.get("grad_count_qualifying"),
        }]
        top_grads["sub_leaves"] = subs

    # ── MLB Production → Conviction — star count + top star names ──
    conv = tree.get("mlb_production_conviction") or {}
    if conv and conv.get("star_count") is not None:
        subs = [{
            "label": "Star count",
            "kind":  "count",
            "value": conv["star_count"],
            "raw":   (", ".join(conv.get("star_names") or [])) or "no stars yet",
        }]
        peak = conv.get("peak_war_per_yr")
        if peak is not None:
            subs.append({
                "label": "Peak career WAR/yr",
                "kind":  "war",
                "value": round(peak, 2),
            })
        conv["sub_leaves"] = subs

    # ── MLB Production → HOF-track — count + top names ──
    hof = tree.get("mlb_production_hof_track") or {}
    if hof and hof.get("hof_count") is not None:
        subs = [{
            "label": f"Seasons ≥{int(hof.get('threshold', 5))} WAR",
            "kind":  "count",
            "value": hof["hof_count"],
            "raw":   (", ".join(hof.get("hof_names") or [])) or "none yet",
        }]
        peak = hof.get("peak_season_war")
        if peak is not None:
            subs.append({
                "label": "Peak season WAR",
                "kind":  "war",
                "value": round(peak, 1),
            })
        hof["sub_leaves"] = subs

    # ── Financial → Active Surplus — per-prospect + per-side splits ──
    asurp = tree.get("fin_active_surplus") or {}
    if asurp and asurp.get("surplus_per_prospect_mm") is not None:
        subs = [{
            "label": "$ / prospect",
            "kind":  "usd",
            "value": round(asurp["surplus_per_prospect_mm"], 2),
            "n":     asurp.get("active_count"),
        }]
        # v31.5 — Per-side splits (Hitter $/prospect vs Pitcher
        # $/prospect). Pitcher surplus typically trails because
        # of higher attrition / injury cost; surfacing the split
        # makes the asymmetry visible.
        if asurp.get("per_prospect_hit_mm") is not None:
            subs.append({
                "label":  "Hitter $/prospect",
                "kind":   "usd",
                "value":  round(asurp["per_prospect_hit_mm"], 2),
                "n":      asurp.get("active_count_hit"),
                "tier":   "surplus_side",
            })
        if asurp.get("per_prospect_pit_mm") is not None:
            subs.append({
                "label":  "Pitcher $/prospect",
                "kind":   "usd",
                "value":  round(asurp["per_prospect_pit_mm"], 2),
                "n":      asurp.get("active_count_pit"),
                "tier":   "surplus_side",
            })
        if asurp.get("cost_basis_mm") is not None:
            subs.append({
                "label": "Cost basis",
                "kind":  "usd",
                "value": round(asurp["cost_basis_mm"], 1),
                "raw":   "total bonus $ paid for actives",
            })
        asurp["sub_leaves"] = subs

    # ── Financial → WAR per $M — channel split (Draft / IFA / Other) ──
    fwpm = tree.get("fin_war_per_m") or {}
    if fwpm and (fwpm.get("value") is not None or fwpm.get("channels")):
        subs = []
        channels = fwpm.get("channels") or {}
        for chan_label, chan_data in channels.items():
            wpm = chan_data.get("war_per_million")
            n = chan_data.get("grad_count") or 0
            subs.append({
                "label":  chan_label,
                "kind":   "warpm",
                "value":  wpm,
                "n":      n,
                "sparse": (wpm is None),
                "tier":   "channel",
                "raw":    f"${(chan_data.get('bonus_usd') or 0) / 1_000_000:.1f}M paid · {chan_data.get('war_sum', 0):.1f} WAR",
            })
        if subs:
            fwpm["sub_leaves"] = subs


def _compute_draft_pool_efficiency(gagg: dict,
                                   draft_pools: dict | None,
                                   org_code: str) -> dict:
    """Per-org draft-pool efficiency over a 3-year rolling window.

    Two signals on the same denominator (pool $ spent in T-5..T-2):
      * war_per_m_pool — sum of grad career WAR / pool $M. Lagging
        but realized: WAR only accrues after the prospect debuts.
      * fv_per_m_pool  — sum of CURRENT FV across drafted-actives /
        pool $M. v32.0 fast-cycle companion: doesn't wait for WAR
        maturation, so the signal is responsive within ~2yr of draft.

    Gates: war_per_m_pool requires ≥3 grads; fv_per_m_pool requires
    pool_total > 0 (active count gating happens upstream)."""
    draft_pools = draft_pools or {}
    grads = gagg.get("_draft_pool_grads") or []
    today_year = date.today().year
    start_year = today_year - 5
    end_year   = today_year - 2

    relevant = [g for g in grads
                if start_year <= g["draft_year"] <= end_year]
    # VAL_4: the WAR credited to the drafting club (share x WAR); the pool is its own.
    war_total = sum(g.get("w", 1.0) * g["career_war"] for g in relevant) if relevant else 0.0
    n_rel = sum(g.get("w", 1.0) for g in relevant)
    pool_total = 0
    for y in range(start_year, end_year + 1):
        pools_y = (draft_pools.get(y) or {}).get("team_pools") or {}
        pool_total += int(pools_y.get(org_code) or 0)
    # FV-side (v32.0) — active prospects' current FV, accumulated in
    # the main per-prospect loop (see _draft_pool_active_fv_total).
    fv_total_active = float(gagg.get("_draft_pool_active_fv_total") or 0.0)

    war_per_m = None
    fv_per_m  = None
    if pool_total > 0:
        pool_total_mm = pool_total / 1_000_000.0
        if n_rel >= 3:
            war_per_m = round(war_total / pool_total_mm, 3)
        if fv_total_active > 0:
            fv_per_m = round(fv_total_active / pool_total_mm, 3)

    return {
        "war_per_m_pool":   war_per_m,
        "fv_per_m_pool":    fv_per_m,
        "grad_count":       round(n_rel, 2),
        "war_total":        round(war_total, 2),
        "fv_total_active":  round(fv_total_active, 1),
        "pool_total_usd":   pool_total,
    }


def _compute_ifa_roi(gagg: dict, ifa_org_spending: dict) -> dict:
    """Per-org WAR-per-$M-IFA over a rolling window.

    v9 — Window settled at **8yr** (today−8…today−2). Tradeoff vs
    coverage: 6yr left ~4 orgs without IFA debuts in window; 10yr+
    started picking up older signings whose ROI no longer reflects
    current scouting decisions. 8yr gives 30 of 31 orgs a value while
    keeping the window responsive to recent signing cycles.

    v8 lineage: dropped per-grad `bonus_usd` gate (was the real
    bottleneck — only 23 of 492 debuted IFAs sitewide had bonus on
    file), switched denominator to `ifa_org_spending` (org-level
    Spotrac bonus pool sum).

    Numerator: career WAR sum across IFA-signed grads in the window
    (no per-grad bonus required — career WAR alone qualifies).
    Denominator: org's IFA bonus spend across the same window from
    `ifa_org_spending` (Spotrac).
    Gates at ≥1 contributing grad AND ≥$1M IFA spend in window."""
    grads = gagg.get("_ifa_grads") or []
    today_year = date.today().year
    start_year = today_year - 8    # v9 — was -7
    end_year   = today_year - 2

    relevant = [g for g in grads
                if start_year <= g["signed_year"] <= end_year]
    if not relevant:
        return {"war_per_m_ifa": None, "grad_count": 0,
                "war_total": 0.0, "ifa_total_usd": 0}
    # VAL_4: the WAR credited to the signing club (share x WAR).
    war_total = sum(g.get("w", 1.0) * g["career_war"] for g in relevant)
    n_rel = round(sum(g.get("w", 1.0) for g in relevant), 2)
    # v8 — Sum the org's TOTAL IFA spend across the same year window
    # from Spotrac. Falls back to per-grad bonus sum when org-level
    # data is missing.
    ifa_total = 0
    by_year = (ifa_org_spending or {})
    for yr in range(start_year, end_year + 1):
        ifa_total += int((by_year.get(yr) or {}).get("total_usd") or 0)
    if ifa_total <= 0:
        ifa_total = sum(int(g.get("bonus_usd") or 0) for g in relevant)
    if ifa_total <= 0:
        return {"war_per_m_ifa": None, "grad_count": n_rel,
                "war_total": round(war_total, 2), "ifa_total_usd": 0}
    war_per_m = round(war_total / (ifa_total / 1_000_000.0), 3)
    return {
        "war_per_m_ifa": war_per_m,
        "grad_count":    n_rel,
        "war_total":     round(war_total, 2),
        "ifa_total_usd": ifa_total,
    }


# v32.0 — Surplus value now comes from value_framework, a single source
# of truth anchored to the 2026 FanGraphs scouting primer (FV->WAR ranges)
# and the 2026 $/WAR FA-market article (non-linear 3-tier model, rolling
# 3yr avg). Formula is now transparent: WAR_peak * 6 * ramp * p_success
# * $/WAR_tier minus cost basis, all factors auditable in
# value_framework.py. Position multipliers ALSO live there (resolving
# a prior backend/frontend divergence bug where the two had different
# values for SS / CF / RP etc).
from value_framework import (
    surplus_value_mm as _estimate_surplus_mm,
    position_multiplier as _surplus_position_mult,
    is_pitcher_position as _vf_is_pitcher_position,
    dollars_per_war_flat as _dollars_per_war_flat,
    dollars_per_war as _dollars_per_war,
    # v34 — richer per-prospect engine outputs baked into the export so the
    # frontend shows the SAME timing/uncertainty the engine computes (Prompts
    # H/G/I) and a per-org system rollup (Prompt K), rather than a timing-naive
    # client-side curve lookup.
    sv_distribution as _sv_distribution,
    sv_credible_interval as _sv_credible_interval,
    system_surplus_distribution as _system_surplus_distribution,
    # v35 — full per-prospect contract: outcome-bucket probabilities, the
    # debuted-player split (trade vs total vs realized), and the engine WAG, so
    # the frontend reads EVERY new engine output rather than recomputing any of
    # it in JS (single source of truth).
    p_bucket_given_fv as _p_bucket_given_fv,
    debuted_player_value as _debuted_player_value,
    wag as _engine_wag,
    wag_boom_bust as _engine_wag_boom_bust,
    realized_consumed_seasons as _realized_consumed_seasons,
    active_valuation_set as _active_valuation_set,
    star_odds as _star_odds,
    dpw_path_active as _vf_dpw_path_active,
    published_star_odds as _published_star_odds,
    published_opt_pct as _published_opt_pct,
    _BUCKETS as _SV_BUCKET_ORDER,
)

# Per-prospect Monte-Carlo draw counts for the baked surplus enrichment
# (`_build_surplus_payload`). These were referenced but never defined, so the
# `ci`/`dist` enrichment threw NameError and was silently swallowed by its
# `except: pass` — every player shipped with `surplus` but no distribution
# (no P10-P90 fan, no P(bust)). Modest counts keep the ~2k-player export fast
# while giving stable percentiles + P(bust); the engine's config defaults
# (10000 dist / 4000 CI) are reserved for one-off analysis. Pass None to fall
# back to those config defaults instead.
_SURPLUS_DIST_DRAWS = 4000   # outcome distribution (percentiles, P(bust), risk-adj)
_SURPLUS_CI_DRAWS   = 2000   # epistemic credible interval on expected SV


# Shared no-ETA fallback timing for PROSPECT surplus pricing (bughunt F3,
# 2026-07-23): when a prospect has no resolvable ETA, BOTH surplus writers (this
# module's consensus surplus payload and efv_score's eFV surplus) price at this
# assumed years-to-debut, so the two adjacent dollar columns can never assume
# different debut timing on the same row. efv_score imports this constant.
PROSPECT_ETA_FALLBACK_YEARS = 1.0


def _eta_years_from(eta, today_year):
    """Years from now to projected debut, from the ETA estimate (half-season
    aware). None when no ETA year is known -> the engine uses its config default."""
    yr = getattr(eta, "eta_year", None) if eta is not None else None
    if yr is None:
        return None
    yrs = float(yr) - float(today_year)
    if getattr(eta, "eta_half", None) == "late":
        yrs += 0.5
    return max(0.0, yrs)


def _build_surplus_payload(fv, is_pitcher, position, *, age=None, eta_years=None,
                           fv_dispersion=None, n_sources=None, eta_origin=None):
    """Bake value_framework's per-prospect engine outputs into the export so the
    frontend renders the SAME numbers the engine computes -- not a timing-naive
    client-side curve lookup:
      * value_mm -- the TIMING-aware expected surplus (Prompt H: age + ETA shape
        the aging curve and discount the control window from projected debut);
      * ci       -- the epistemic CREDIBLE INTERVAL on expected surplus (Prompt G);
      * dist     -- the SOURCE-DISAGREEMENT-widened outcome distribution (Prompt I:
        fv_dispersion = the across-source FV stddev widens the spread, same mean).
    Returns None when FV is missing/invalid. The ci/dist enrichment is wrapped so a
    numerical hiccup degrades to the bare point value rather than sinking the export."""
    if fv is None:
        return None
    # VAL_5 (I6): eta_years is measured from the calendar year; the engine is told
    # so, and prices the season from it in unified $/WAR path mode. eta_years,
    # the odds placement and debut_age are unchanged in both modes.
    if eta_origin is None:
        eta_origin = date.today().year
    point = _estimate_surplus_mm(fv, is_pitcher, position, age=age, eta_years=eta_years,
                                 eta_origin=eta_origin)
    if point is None:
        return None
    # Store the is_pitcher the value was actually baked with, so the K rollup
    # reuses the EXACT same classification (no re-derivation drift -> the system
    # figure reconciles with the per-player headline). `fv_used` is the EXACT
    # continuous FV the engine priced, so the frontend can show "FV the engine
    # used" with zero drift (validation: displayed FV == engine FV).
    out = {
        "value_mm": point,
        "is_pitcher": bool(is_pitcher),
        "fv_used": round(float(fv), 2),
        "fv_continuous": round(float(fv), 2),
        "valuation_set": _active_valuation_set(),
    }
    # Phase 4: Star Odds = P(>= 2 control seasons of >= 4 WAR). The DISPLAYED value
    # is the FanGraphs (2026) published tier odds (table mode -- the credible,
    # industry-anchored number); `star_odds_model` is the engine's per-player odds
    # (timing-aware diagnostic, calibrated toward the published targets in P5).
    # Degrades to omission on any hiccup rather than sinking the export.
    try:
        _so_pub = _published_star_odds(fv, is_pitcher)
        if _so_pub is not None:
            out["star_odds"] = round(float(_so_pub), 4)
        _so_model = _star_odds(fv, is_pitcher, position, age=age, eta_years=eta_years,
                               eta_origin=eta_origin)
        if _so_model is not None:
            out["star_odds_model"] = round(float(_so_model), 4)
    except Exception:
        pass
    # `opt_pct` (upgrade-option layer): the share of the grade's value that comes
    # from the chance of upgrading before graduating. Snapped by FV tier; NEGATIVE
    # at high grades (top-end downgrade risk). Own try so it degrades independently.
    try:
        _op = _published_opt_pct(fv, is_pitcher)
        if _op is not None:
            out["opt_pct"] = round(float(_op), 4)
    except Exception:
        pass
    if eta_years is not None:
        out["eta_years"] = round(float(eta_years), 2)
        if _vf_dpw_path_active():
            # VAL_5 (I6): the origin beside eta_years, ON only (absent OFF).
            out["eta_origin_year"] = int(eta_origin)
    # Outcome-bucket probabilities P(bucket|FV) over the five career buckets
    # (bust/bench/regular/good/star) -- the prior shown as the stacked bar for a
    # prospect (debuted players override this with the Bayes posterior).
    try:
        probs = _p_bucket_given_fv(float(fv), is_pitcher)
        if probs is not None:
            out["buckets"] = {b: round(float(pp), 4)
                              for b, pp in zip(_SV_BUCKET_ORDER, probs)}
    except Exception:
        pass
    try:
        ci = _sv_credible_interval(fv, is_pitcher, position, age=age,
                                   eta_years=eta_years, draws=_SURPLUS_CI_DRAWS,
                                   eta_origin=eta_origin)
        if ci and ci.get("point_mm") is not None:
            out["ci"] = {"lo_mm": ci["lo_mm"], "median_mm": ci["median_mm"],
                         "hi_mm": ci["hi_mm"], "cred": ci["cred"], "regime": ci.get("regime")}
        dist = _sv_distribution(fv, is_pitcher, position, age=age, eta_years=eta_years,
                                fv_dispersion=fv_dispersion, n_sources=n_sources,
                                draws=_SURPLUS_DIST_DRAWS, eta_origin=eta_origin)
        if dist:
            pcts = dist.get("percentiles", {})
            # Carry the FULL percentile set the engine emits (p10/p25/p50/p75/p90
            # at the shipped config) so the frontend can draw a percentile fan,
            # plus the mean, spread, downside CVaR and the risk-adjusted score
            # (mean - lambda*(mean - downside)) at the configured risk-aversion
            # lambda. The frontend reads these directly -- it never re-runs MC.
            out["dist"] = {
                "p10_mm": pcts.get("p10"), "p25_mm": pcts.get("p25"),
                "p50_mm": pcts.get("p50"), "p75_mm": pcts.get("p75"),
                "p90_mm": pcts.get("p90"),
                "percentiles": {k: round(float(v), 2) for k, v in pcts.items()},
                "mean_mm": dist.get("mean"),
                "std_mm": dist.get("std"),
                "p_bust": dist.get("p_bust"), "downside_mm": dist.get("downside_metric"),
                "risk_adjusted_mm": dist.get("risk_adjusted_score"),
                "risk_lambda": dist.get("risk_aversion_lambda"),
                "p_above_threshold": dist.get("p_above_threshold"),
                "threshold_mm": dist.get("threshold_mm"),
                "fv_dispersion": dist.get("fv_dispersion"),
            }
    except Exception:
        pass   # enrichment only -- never let a MC/numerical hiccup sink the build
    return out


def _mlb_exposure_pa_ip(career_stats) -> tuple[float, float]:
    """Sum MLB-level PA / IP across a player's career_stats rows -> a WAG exposure
    fallback when no service-time decimal is on file."""
    pa = ip = 0.0
    for row in (career_stats or []):
        if str(row.get("level") or "").upper() != "MLB":
            continue
        try:
            p = row.get("pa")
            pa += float(p) if p is not None else (float(row.get("ab") or 0) * 1.1)
        except (TypeError, ValueError):
            pass
        try:
            ip += float(row.get("ip") or 0)
        except (TypeError, ValueError):
            pass
    return pa, ip


def _mlb_exposure_measured(career_stats) -> tuple[float | None, float | None]:
    """MLB PA / IP as MEASURED, with None where nothing is on file (audit L13-05).

    PA is a row's `pa`, else its `ab` x 1.1 (the served MLB rows carry `ab`, never
    `pa`), so a row with ab == 0 is a measured zero. IP is a row's `ip`. A field no
    MLB row carries is MISSING, which is a different fact from a measured 0: 620
    graduates have no career_stats rows at all (Mike Trout among them), and a 0
    there would claim a thin sample nobody measured."""
    pa = ip = None
    for row in (career_stats or []):
        if str(row.get("level") or "").upper() != "MLB":
            continue
        try:
            if row.get("pa") is not None:
                pa = (pa or 0.0) + float(row["pa"])
            elif row.get("ab") is not None:
                pa = (pa or 0.0) + float(row["ab"]) * 1.1
        except (TypeError, ValueError):
            pass
        try:
            if row.get("ip") is not None:
                ip = (ip or 0.0) + float(row["ip"])
        except (TypeError, ValueError):
            pass
    return pa, ip


def _career_war_exposure(career_war) -> tuple[float | None, float | None]:
    """MLB PA / IP MEASURED ON THE CAREER-WAR STINTS (owner decision 14c, 2026-09-11).

    The career_war row's `seasons_pa` / `seasons_ip` are the war_daily PA and
    IPouts / 3 of exactly the stints whose WAR `seasons` sums, so this is the
    exposure the observed WAR was earned over. They are PERSISTED on the row: the WAR
    funnel writes them with the WAR (stats.fetch_career_war_bulk) and
    persist_career_war_exposure backfills rows stored before 2026-09-11. Nothing here
    reads a cache. A side is None unless its map carries EVERY season in `seasons`:
    a partial map would understate the load and close a gate the player cleared."""
    seasons = (career_war or {}).get("seasons") or {}
    if not seasons:
        return None, None

    def _sum(field):
        m = career_war.get(field)
        if not isinstance(m, dict):
            return None
        tot = 0.0
        for yr in seasons:
            v = m.get(yr)
            if v is None:
                return None
            try:
                tot += float(v)
            except (TypeError, ValueError):
                return None
        return tot

    return _sum("seasons_pa"), _sum("seasons_ip")


_CAREER_WAR_EXPOSURE_FIELDS = ("seasons_pa", "seasons_ip")

# DECISION 14c, AS ANSWERED (owner, 2026-09-11: "641 missing-exposure graduates: wire
# war_daily PA/IP NOW"). False, served: the career-WAR stints stand in ONLY where
# career_stats has no measured load for the player's role, which is exactly the
# population the question named. True would read the stints FIRST for every graduate,
# including the ones already measured on career_stats (AB x 1.1, capped at
# CAREER_SEASONS_KEPT seasons, lagging the season). That extension moves more engine
# labels than the 641 (measured in the L3_wag lane report) and is the owner's own
# line, not taken here.
WAG_EXPOSURE_STINTS_FIRST = False

# The stored bWAR of a season must equal the war_daily cache's bWAR for it (summed
# over the same WAR-bearing stints, 2dp) before the cache's PA / IP are written beside
# it; see _career_war_exposure_fill.
_EXPOSURE_VINTAGE_TOL = 0.011


def _bwar_reference(row: dict, yr: str):
    """The bWAR a stored row carries for one season: `seasons_bwar` (eWAR rows), else
    `seasons` on a bWAR row (source bbref). None when the row cannot say."""
    frame = row.get("seasons_bwar")
    if isinstance(frame, dict):
        v = frame.get(yr)
    elif row.get("source") == "bbref":
        v = (row.get("seasons") or {}).get(yr)
    else:
        v = None
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


_SPOTRAC_PITCHER_POS = frozenset({"P", "SP", "RP", "RHP", "LHP", "CL"})


def _pos_is_pitcher(pos) -> bool | None:
    """True / False for a pitcher / position-player token, None when the token
    cannot say (missing, two-way). Used only to tell two same-named players apart."""
    tok = str(pos or "").strip().upper().split("/")[0]
    if not tok or tok in {"TWP", "TW", "UT"}:
        return None
    return tok in _SPOTRAC_PITCHER_POS


def resolve_contracts_to_ids(contracts_by_key: dict, humans: dict,
                             rivals: list | tuple = ()) -> tuple[dict, dict]:
    """Bind Spotrac contracts to players by mlbam id instead of by name slug.

    Spotrac rows carry no mlbam id, only a name slug, a club and a position, so a
    slug join hands one player another's contract whenever two share a name: the
    ATH Max Muncy (691777) served the LAD Max Muncy's $10.0M, and a CPX pitcher
    keyed jose_ramirez (802064) served the CLE third baseman's $20.8M through 2032.

    humans:  {player_key: (mlbam, club, is_pitcher)} for the rows being exported.
    rivals:  [(slug, mlbam, club, is_pitcher), ...] for other MLB players known to
             hold a slug (the /projections/ veterans), so a contract can go to a
             player who is not on this board.
    Every Spotrac row of the slug (the kept row plus its "same_slug_rows") is given
    to the ONE claimant it fits. A player alone on his slug takes every row (the
    pitcher / hitter tag on a prospect row is too often a pre-conversion position
    to veto a contract on its own). When several claim the slug, claimants of the
    wrong side (pitcher vs hitter) are ruled out first, then the row's club breaks
    the tie; a row still shared is given to nobody. A player who is handed several
    rows keeps the one on his own club, then the highest AAV. A manual override
    (source != spotrac) is left alone.

    Returns ({player_key: contract or None}, receipt) for the keys it resolved. A
    key absent from the result keeps the slug join (no mlbam, or no Spotrac row)."""
    by_slug_rivals: dict[str, dict] = {}
    for slug, mid, club, isp in rivals or ():
        if slug and mid:
            by_slug_rivals.setdefault(slug, {})[int(mid)] = (club, isp)
    try:
        from spotrac import _SPOTRAC_TEAM_SLUGS as _slugs
        team_of = {v: k for k, v in _slugs.items()}
    except Exception:                                        # pragma: no cover
        team_of = {}
    out: dict[str, dict | None] = {}
    receipt = {"resolved": 0, "kept": 0, "moved": 0, "dropped": 0}
    for key, (mid, club, isp) in humans.items():
        ct = contracts_by_key.get(key)
        if not ct or not mid:
            continue
        if (ct.get("source") or "spotrac") != "spotrac":
            continue
        mid = int(mid)
        rows_all = [ct] + [r for r in (ct.get("same_slug_rows") or []) if isinstance(r, dict)]
        # One Spotrac id is one person: a player traded mid-season sits on both
        # clubs' pages (the new club's row is the prorated remainder), and the
        # highest-AAV row stands for him, as build_contracts_by_key has always done.
        by_sid: dict = {}
        for r in rows_all:
            sid = r.get("spotrac_id") or id(r)
            if sid not in by_sid or (r.get("aav_usd") or 0) > (by_sid[sid].get("aav_usd") or 0):
                by_sid[sid] = r
        rows = list(by_sid.values())
        claimants = dict(by_slug_rivals.get(key) or {})
        claimants[mid] = (club, isp)
        mine = []
        for row in rows:
            rp = _pos_is_pitcher(row.get("position"))
            rclub = team_of.get(row.get("team_slug")) or row.get("team_code")
            fit = list(claimants)
            if len(fit) > 1:
                fit = [m for m in fit
                       if rp is None or claimants[m][1] is None or claimants[m][1] == rp]
            if len(fit) > 1:
                fit = [m for m in fit if rclub and claimants[m][0] == rclub]
            if fit == [mid]:
                mine.append((row, rclub))
        chosen = None
        if mine:
            chosen = max(mine, key=lambda t: (bool(club) and t[1] == club,
                                              t[0].get("aav_usd") or 0))[0]
            chosen = {k: v for k, v in chosen.items() if k != "same_slug_rows"}
        receipt["resolved"] += 1
        if chosen is None:
            receipt["dropped"] += 1
        elif chosen.get("spotrac_id") == ct.get("spotrac_id"):
            receipt["kept"] += 1
        else:
            receipt["moved"] += 1
        out[key] = chosen
    return out, receipt


def screen_career_war_to_ids(career_war: dict, ids_by_key: dict,
                             by_id: dict | None = None) -> tuple[dict, dict]:
    """Drop the career-WAR seasons a player's own mlbam id never played.

    The career_war table is keyed by name slug and its season map merges across
    refetches, so a slug that once resolved to another player keeps that player's
    seasons: jose_ramirez (802064, a CPX pitcher born 2004) served 2014-2018 WAR,
    and the export back-filled those years into his roster_status mlb_seasons.
    The war_daily frame is keyed by mlb_ID, so a COMPLETED season with no stint for
    the row's id is another player's. The season in progress (the frame's latest
    year) is kept, as in _career_war_exposure_fill. `by_id` is
    stats.war_daily_exposure's output (read here when None); with no cache the rows
    pass through unchanged, so an offline build serves what it served before.

    Returns (career_war with the foreign seasons removed, receipt). A row left with
    no season is removed. The input dict is not mutated. receipt["foreign_by_key"]
    names each screened key's id and the seasons it lost; the export serves it as
    the record's `identity_screen`, so the trade board can still see that the key's
    MLB history belonged to someone else."""
    receipt = {"rows_checked": 0, "rows_screened": 0, "rows_removed": 0,
               "seasons_dropped": 0, "cache_ok": None, "foreign_by_key": {}}
    need: dict[str, int] = {}
    for key, row in (career_war or {}).items():
        if not (row or {}).get("seasons"):
            continue
        mid = (ids_by_key or {}).get(key)
        try:
            need[key] = int(mid)
        except (TypeError, ValueError):
            continue
    if not need:
        return career_war, receipt
    if by_id is None:
        try:
            import stats as _stats
            by_id = _stats.war_daily_exposure(need.values())
        except Exception:
            log.debug("career_war identity screen: war_daily_exposure raised",
                      exc_info=True)
            by_id = {}
    receipt["cache_ok"] = bool(by_id)
    if not by_id:
        return career_war, receipt
    latest = max((int(y) for yrs in by_id.values() for y in yrs), default=None)
    out = dict(career_war)
    for key, mid in need.items():
        row = career_war[key]
        receipt["rows_checked"] += 1
        played = {int(y) for y in (by_id.get(mid) or {})}
        foreign = []
        for yr in row["seasons"]:
            try:
                y = int(yr)
            except (TypeError, ValueError):
                continue
            if latest is not None and y < latest and y not in played:
                foreign.append(yr)
        if not foreign:
            continue
        receipt["rows_screened"] += 1
        receipt["seasons_dropped"] += len(foreign)
        receipt["foreign_by_key"][key] = {"mlbam": mid,
                                          "foreign_mlb_seasons": sorted(int(y) for y in foreign)}
        keep = {y: v for y, v in row["seasons"].items() if y not in foreign}
        if not keep:
            out.pop(key, None)
            receipt["rows_removed"] += 1
            continue
        new = dict(row)
        new["seasons"] = keep
        for fld in ("seasons_bwar", "seasons_pa", "seasons_ip"):
            if isinstance(row.get(fld), dict):
                new[fld] = {y: v for y, v in row[fld].items() if y not in foreign}
        vals = [float(v) for v in keep.values()]
        new["career_war"] = round(sum(vals), 2)
        new["war_seasons_count"] = len(vals)
        new["war_per_yr"] = round(sum(vals) / len(vals), 3)
        out[key] = new
    return out, receipt


def _career_war_exposure_fill(career_war: dict, *id_maps: dict) -> tuple[dict, dict]:
    """The measured exposure to write into career_war rows that lack it, read OFFLINE
    from the war_daily last-good cache (stats.war_daily_exposure). Returns
    ({player_key: {"seasons_pa": {...}, "seasons_ip": {...}}}, receipt).

    THE SAME STINTS. The id is the one the row's WAR was built on (ewar_coverage.mlbam,
    the rebase receipt), and only then the id maps. A season is filled when the
    cache's bWAR for (id, season) equals the row's stored bWAR for it, so the PA / IP
    are those of the stints the stored WAR summed. A completed season that fails the
    check, or that the cache does not hold (an id with no stint that year: an
    identity collision), stays missing, so that side stays unmeasured and the gate
    falls back.

    THE ONE EXCEPTION IS THE SEASON IN PROGRESS (the cache's latest year). The cache
    is refreshed nightly; the WAR of a graduate outside the monthly career-WAR cohort
    (which needs an MLB career_stats row, so the 641 are outside it) is not, so its
    current-season WAR can predate the cache by months. That season is filled anyway
    and counted in `seasons_current_newer`: its PA / IP run ahead of the WAR beside
    them. Leaving it out would leave Trout, Betts, Machado and Harper on a season-implied
    load, the case decision 14c named. Measured 2026-09-11, no engine label depends on it
    (the L3_wag lane report). The repair is to refresh those rows' WAR, not to drop
    their exposure. Only seasons a row does not already carry are returned: a stored
    value always wins."""
    receipt = {"rows": 0, "incomplete": 0, "no_id": 0, "cache_ok": None,
               "rows_filled": 0, "rows_completed": 0, "seasons_filled": 0,
               "seasons_current_newer": 0, "seasons_vintage_mismatch": 0,
               "seasons_no_stint": 0}
    need: dict[str, int] = {}
    for key, row in (career_war or {}).items():
        seasons = (row or {}).get("seasons") or {}
        if not seasons:
            continue
        receipt["rows"] += 1
        if all(isinstance(row.get(f), dict) and all(y in row[f] for y in seasons)
               for f in _CAREER_WAR_EXPOSURE_FIELDS):
            continue
        receipt["incomplete"] += 1
        mid = (row.get("ewar_coverage") or {}).get("mlbam")
        for m in id_maps:
            if mid:
                break
            mid = (m or {}).get(key)
        try:
            need[key] = int(mid)
        except (TypeError, ValueError):
            receipt["no_id"] += 1
    if not need:
        return {}, receipt
    try:
        import stats as _stats
        by_id = _stats.war_daily_exposure(need.values())
    except Exception:
        log.debug("career_war exposure: war_daily_exposure raised", exc_info=True)
        by_id = {}
    receipt["cache_ok"] = bool(by_id)
    if not by_id:
        log.warning("career_war exposure: the war_daily cache (.cache/war_daily/"
                    "{bat,pit}.parquet) returned nothing; %d rows without measured "
                    "exposure stay unmeasured", len(need))
        return {}, receipt
    latest = max((yr for yrs in by_id.values() for yr in yrs), default=None)
    out: dict[str, dict] = {}
    for key, mid in need.items():
        row = career_war[key]
        yrs = by_id.get(mid) or {}
        old_pa = row.get("seasons_pa") if isinstance(row.get("seasons_pa"), dict) else {}
        old_ip = row.get("seasons_ip") if isinstance(row.get("seasons_ip"), dict) else {}
        add_pa: dict[str, float] = {}
        add_ip: dict[str, float] = {}
        for yr in row["seasons"]:
            if yr in old_pa and yr in old_ip:
                continue
            try:
                rec = yrs.get(int(yr))
            except (TypeError, ValueError):
                rec = None
            if rec is None:
                receipt["seasons_no_stint"] += 1
                continue
            ref = _bwar_reference(row, yr)
            if ref is None:
                receipt["seasons_vintage_mismatch"] += 1
                continue
            if abs(float(rec["war"]) - ref) > _EXPOSURE_VINTAGE_TOL:
                if int(yr) != latest:
                    receipt["seasons_vintage_mismatch"] += 1
                    continue
                # The season still in progress: the stored WAR predates the cache, so
                # this PA / IP runs ahead of the WAR it sits beside. Filled, counted
                # and disclosed (glossary wag, registry wag); see the docstring.
                receipt["seasons_current_newer"] += 1
            if yr not in old_pa:
                add_pa[yr] = rec["pa"]
            if yr not in old_ip:
                add_ip[yr] = rec["ip"]
            receipt["seasons_filled"] += 1
        if not add_pa and not add_ip:
            continue
        out[key] = {"seasons_pa": add_pa, "seasons_ip": add_ip}
        receipt["rows_filled"] += 1
        merged = dict(row, seasons_pa={**add_pa, **old_pa}, seasons_ip={**add_ip, **old_ip})
        if None not in _career_war_exposure(merged):
            receipt["rows_completed"] += 1
    return out, receipt


def store_career_war_exposure(by_key: dict[str, dict]) -> int:
    """Write measured exposure maps into EXISTING career_war rows, and nothing else.

    Only `seasons_pa` / `seasons_ip` change, merged per season with the stored value
    winning, so a funnel-measured season is never overwritten by a backfill. The WAR,
    the aggregates, `source`, `ewar_coverage` and `fetched_at` are left as they are:
    a backfill must not make a row look freshly fetched, or the monthly WAR refresh
    would skip it (load_career_war_meta). A key with no stored row is skipped."""
    n = 0
    with connect() as con:
        for key, maps in (by_key or {}).items():
            got = con.execute("SELECT payload_json FROM career_war WHERE player_key = ?",
                              (key,)).fetchone()
            if got is None:
                continue
            try:
                rec = json.loads(got["payload_json"] or "{}") or {}
            except ValueError:
                continue
            changed = False
            for f in _CAREER_WAR_EXPOSURE_FIELDS:
                add = (maps or {}).get(f) or {}
                if not add:
                    continue
                old = rec.get(f) if isinstance(rec.get(f), dict) else {}
                merged = {**add, **old}
                if merged != old:
                    rec[f] = merged
                    changed = True
            if changed:
                con.execute("UPDATE career_war SET payload_json = ? WHERE player_key = ?",
                            (json.dumps(rec), key))
                n += 1
    return n


def _durable_mlbam_by_key() -> dict[str, int]:
    """{player_key: mlbam} from player_photos, keys bound to two ids excluded (the
    same rule as export_timeseries_json's durable fallback)."""
    out: dict[str, int] = {}
    multi: set[str] = set()
    for mid_s, pk in load_mlbam_player_keys().items():
        if not pk:
            continue
        try:
            mid = int(mid_s)
        except (TypeError, ValueError):
            continue
        if out.get(pk) not in (None, mid):
            multi.add(pk)
        out[pk] = mid
    for pk in multi:
        out.pop(pk, None)
    return out


def persist_career_war_exposure(*, dry_run: bool = False) -> dict:
    """Backfill measured MLB exposure into the career_war table (decision 14c).

    ONE-SHOT AND IDEMPOTENT: run it once after this lands, locally and on the box (the
    box keeps its own DB and its own .cache/war_daily). After that the WAG gate reads
    the stored maps and never the cache, so the served labels do not depend on a
    gitignored file being present on the night of the export. Rows the WAR funnel
    writes carry the maps already. A re-run fills only what is still missing (a row
    whose current-season WAR is refreshed later, for instance). Returns the receipt of
    _career_war_exposure_fill plus `persisted` (rows written; 0 on a dry run)."""
    table = load_career_war()
    maps, receipt = _career_war_exposure_fill(table, _durable_mlbam_by_key())
    receipt["persisted"] = 0 if dry_run else store_career_war_exposure(maps)
    log.info("career_war exposure backfill: %s", receipt)
    if receipt["cache_ok"] is False:
        _file_ingest_if_pipeline(
            "career_war_exposure", ok=False, n_rows=0,
            message=(f"the war_daily cache returned nothing; {receipt['incomplete']} "
                     "career_war rows without measured exposure stay unmeasured"))
    return receipt


def _career_war_exposure_census(career_war: dict) -> dict:
    """How many career_war rows carry measured exposure for every season (both sides),
    for the export's receipt."""
    rows = [r for r in (career_war or {}).values() if (r or {}).get("seasons")]
    complete = sum(1 for r in rows if None not in _career_war_exposure(r))
    return {"rows": len(rows), "complete": complete}


def _file_ingest_if_pipeline(source: str, *, ok: bool, n_rows: int, message: str) -> None:
    """File one row into the running pipeline's ingest-health ledger, never raising and
    never importing run_monthly (the same live-module rule as
    bullpen_export._live_pipeline_module). Outside a pipeline run it does nothing. The
    callers here file only ok=False: an ok=True row also stamps the durable
    source_checks table, which a test calling the export must not write."""
    try:
        import sys as _sys
        for mod in (_sys.modules.get("run_monthly"), _sys.modules.get("__main__")):
            if (mod is not None and hasattr(mod, "_record_ingest")
                    and hasattr(mod, "write_ingest_health")):
                mod._record_ingest(source, ok=ok, n_rows=n_rows, message=message)
                return
    except Exception:
        log.debug("ingest health: could not file %s", source, exc_info=True)


def _strip_exposure(row: dict | None) -> dict:
    row = row or {}
    if not any(f in row for f in _CAREER_WAR_EXPOSURE_FIELDS):
        return row
    return {k: v for k, v in row.items() if k not in _CAREER_WAR_EXPOSURE_FIELDS}


def _served_career_war(row: dict | None) -> dict:
    """The `career_war` block a payload serves: the DISPLAYED WAR, eWAR v2 (owner
    answer EPOCH-Q4 "Keep eWAR v2 shown", 2026-09-30; fWAR label epoch step D + U,
    2026-10-03), without the exposure maps, which only the WAG gate reads.

    The stored row serves the LABEL series (`seasons` is fWAR since the epoch's
    step C) and keeps `seasons_ewar_v2` beside it, so this block re-expresses the
    row on provider "ewar_v2" through war_source.row_on_provider: the PROSPX
    card's career WAR line, the debuted sort, the graduate tooltip, build_site's
    grad strings, the Club Ledger's graduate career_war column, draft_export's
    record career WAR and efv_score's realized_war all keep showing eWAR v2. The
    label consumers of the payload read `career_war_label` (below) instead.

    A row with nothing to re-express (not an fwar row carrying `seasons_ewar_v2`)
    goes straight to _strip_exposure, so a bare row is served as the same object,
    the no-copy contract test_wag_career_exposure pins (row_on_provider always
    copies)."""
    r = row or {}
    if str(r.get("source") or "") != "fwar" or not isinstance(r.get("seasons_ewar_v2"), dict):
        return _strip_exposure(row)
    import war_source
    return _strip_exposure(war_source.row_on_provider(row, war_source.DISPLAY_PROVIDER))


def _label_career_war(row: dict | None) -> dict:
    """The `career_war_label` block: the stored row (the LABEL series, fWAR since
    the epoch's step C) without the exposure maps. Read by the payload consumers
    that price or train on WAR (bayes_trade_value's debuted prior, grpo_prospect's
    reward, source_backtest's outcomes, draft_source_backtest), never by a display.
    Empty when the player has no career_war row."""
    return _strip_exposure(row)


def _engine_wag_result(fv, is_pitcher, position, observed_war, *, age=None,
                       service_years=None, career_stats=None, career_war=None):
    """The ONE engine-WAG computation path (value_framework.wag, Prompt M).
    Resolves exposure from the service-time decimal (preferred) or summed MLB
    PA/IP. Returns the full wag dict or None. Shared by the baked
    debuted_value.wag, the boom/bust label, and the farm-grade WAG rollup so every
    WAG figure on the site agrees (single source of truth -- replaces _grad_wag)."""
    if fv is None or observed_war is None:
        return None
    try:
        ow = float(observed_war)
    except (TypeError, ValueError):
        return None
    try:
        # Expected baseline matched to MLB SEASONS (service_years); the gate +
        # reliability use the REAL accumulated MLB PA/IP (passed alongside so a
        # thin multi-season sample is still gated + regressed).
        #
        # A MEASURED ZERO IS PASSED AS ZERO (audit L13-05, 2026-09-11). This used to
        # pass `pa or None`, which turns a recorded 0 into "unknown", and the engine
        # then gates an unknown load on len(seasons) full seasons, so a graduate with
        # a 0-AB MLB line opened the 200 PA gate on a load nobody measured. The
        # role's own exposure now goes in as measured (0 stays 0: gate closed, no
        # reliability weight); a MISSING one stays None and keeps the engine's
        # season-implied load, flagged on the result as exposure_measured False so
        # the served block says which it was. The off-role figure keeps the old
        # `or None` read, so nothing but the measured-zero case moves.
        #
        # THE CAREER-WAR STINTS FILL THE GAP (owner decision 14c, 2026-09-11). Where
        # career_stats has no measured load for the role (641 graduates, Mike Trout
        # among them, have no MLB career_stats row at all), the gate reads the PA /
        # IPouts of the war_daily stints the observed WAR was summed over
        # (_career_war_exposure, persisted on the row) instead of a season-implied
        # load. A row already measured on career_stats keeps it unless
        # WAG_EXPOSURE_STINTS_FIRST is set (off: that extension is its own decision).
        # `exposure_source` on the result says which load the gate read.
        pa, ip = _mlb_exposure_pa_ip(career_stats)
        mpa, mip = _mlb_exposure_measured(career_stats)
        wpa, wip = _career_war_exposure(career_war)
        cs_load = mip if is_pitcher else mpa
        if (wip if is_pitcher else wpa) is not None and (WAG_EXPOSURE_STINTS_FIRST
                                                        or cs_load is None):
            source = "war_daily"
            if is_pitcher:
                exp_pa, exp_ip = (wpa or None), wip
            else:
                exp_pa, exp_ip = wpa, (wip or None)
        else:
            if is_pitcher:
                exp_pa, exp_ip = (pa or None), mip
            else:
                exp_pa, exp_ip = mpa, (ip or None)
            source = "career_stats" if cs_load is not None else None
        if service_years is not None:
            w = _engine_wag(fv, is_pitcher, ow, position=position,
                            service_years=float(service_years),
                            exposure_pa=exp_pa, exposure_ip=exp_ip, age=age)
        else:
            w = _engine_wag(fv, is_pitcher, ow, position=position,
                            exposure_pa=exp_pa, exposure_ip=exp_ip, age=age)
        if w is not None:
            _load = exp_ip if is_pitcher else exp_pa
            w["exposure_measured"] = _load is not None
            # Where the gate's load came from, and the load itself in the role's
            # unit (PA for a hitter, IP for a pitcher); None when not measured.
            w["exposure_source"] = source
            w["exposure_load"] = round(float(_load), 1) if _load is not None else None
            w["exposure_unit"] = "IP" if is_pitcher else "PA"
        return w
    except Exception:
        return None


# M10_SERVICE_TIME_ENGINE (owner answer 2026-09-25). roster_status.service_years_decimal
# was read below but never written, so debuted_player_value priced every graduate on the
# full control window (Ohtani's remaining value read $751.8M on 7 of 7 control years).
# True: export_timeseries_json writes the service fields from service_time.py (the CBA
# day count off the transaction history, validated against published service time in
# data/service_time_eval.json, registry row service_time) onto each row's roster_status
# before the debuted block is built. False: the fields are not written and every
# graduate prices at service 0 again.
DEBUTED_SERVICE_TIME = True


def _build_debuted_payload(fv, is_pitcher, position, *, age=None,
                           career_war=None, roster_status=None,
                           contract=None, career_stats=None, wag_fv=None):
    """Bake the engine's DEBUTED-player split + WAG for a player who has reached the
    majors (Prompts D + M). REALIZED (consumed control years, sunk) + REMAINING
    (projected) trade value + their sum (total value), the Bayes-updated outcome
    posterior, and the FV-vs-realized WAG. Every figure comes straight from
    value_framework, so the frontend renders these directly -- this RETIRES the
    prior JS realized-surplus salary model + grad-WAG recompute. Returns None when
    there is no usable MLB WAR record (so a 0-MLB prospect carries no debuted block
    and the UI hides every debuted-only field)."""
    if fv is None:
        return None
    cw = career_war or {}
    seasons = cw.get("seasons") or {}
    observed_war = cw.get("career_war")
    if observed_war is None or not seasons:
        return None
    rs = roster_status or {}
    sy = rs.get("service_years_decimal")
    service_years = float(sy) if sy is not None else None
    salary_by_year = (contract or {}).get("salary_by_year") or {}
    # Observed MLB exposure (the Bayes-update SAMPLE for Prompt D + WAG). Without
    # it the bucket posterior would never move off the FV prior.
    _obs_pa, _obs_ip = _mlb_exposure_pa_ip(career_stats)
    out = {}
    try:
        consumed = _realized_consumed_seasons(seasons, salary_by_year=salary_by_year)
        dv = _debuted_player_value(
            fv, is_pitcher, position, observed_war=float(observed_war),
            observed_pa=(_obs_pa or None), observed_ip=(_obs_ip or None),
            service_time=(service_years if service_years is not None else 0.0),
            age=age, consumed_seasons=consumed)
        if dv:
            rem = dv.get("remaining") or {}
            rpct = rem.get("percentiles", {})
            out.update({
                "trade_value_mm": dv.get("trade_value_mm"),    # remaining control yrs (consumed = sunk)
                "total_value_mm": dv.get("total_value_mm"),    # realized banked + remaining
                "realized_mm": dv.get("realized_mm"),          # market value of consumed WAR - salary paid
                "true_talent_war": dv.get("true_talent_war"),
                "consumed_control_years": dv.get("consumed_control_years"),
                "remaining_control_years": dv.get("remaining_control_years"),
                # Bayes-updated outcome distribution -- the stacked bucket bar for a
                # debuted player uses this posterior (vs the FV prior for prospects).
                "posterior": dv.get("posterior"),
                "prior": dv.get("prior"),
                "remaining_dist": {
                    "p10_mm": rpct.get("p10"), "p50_mm": rpct.get("p50"),
                    "p90_mm": rpct.get("p90"), "p_bust": rem.get("p_bust"),
                },
            })
    except Exception:
        pass   # enrichment only -- a numerical hiccup must not sink the export
    try:
        # WAG is matched to the number of MLB SEASONS the player has been in the
        # majors (not PA / rate of production): an injury-shortened season still
        # counts as a season, so WAR-above-grade reflects accumulation over time.
        # (service_years_decimal still feeds the realized/consumed-control value
        # above; it's None for many players and would otherwise fall this WAG call
        # back to PA-matching, inflating injury-limited rates.)
        season_count = len(seasons)
        # WAG is "WAR Above GRADE" — the grade baseline is now eFV (our outcome-grounded
        # grade) where available, falling back to the consensus `fv` only where eFV
        # abstains. Only the WAG baseline uses wag_fv; the debuted VALUE model above keeps
        # the `fv` passed in (its surplus is priced from the consensus/eFV value pipeline).
        _wag_baseline = wag_fv if wag_fv is not None else fv
        w = _engine_wag_result(_wag_baseline, is_pitcher, position, observed_war,
                               age=age,
                               service_years=(float(season_count) if season_count else None),
                               career_stats=career_stats, career_war=cw)
        if w:
            out["wag"] = {
                "regressed_wag": w.get("regressed_wag"),
                "regressed_lo": w.get("regressed_lo"),
                "regressed_hi": w.get("regressed_hi"),
                "counting_wag": w.get("counting_wag"),
                "rate_wag": w.get("rate_wag"),
                "percentile": w.get("percentile"),
                "z": w.get("z"),
                "expected_war": w.get("expected_war"),
                "observed_war": w.get("observed_war"),
                "true_talent_war": w.get("true_talent_war"),
                "w_obs": w.get("w_obs"),
                "below_meaningful_exposure": w.get("below_meaningful_exposure"),
                # False = no MLB PA/IP on file, so the gate read the season-implied
                # load (audit L13-05); True = measured, a recorded 0 included.
                "exposure_measured": w.get("exposure_measured"),
                # "career_stats" (the MLB Stats API rows, read first), "war_daily" (the
                # career-WAR stints, where career_stats measures nothing: decision 14c)
                # or None (season-implied); the load in PA / IP.
                "exposure_source": w.get("exposure_source"),
                "exposure_load": w.get("exposure_load"),
                "exposure_unit": w.get("exposure_unit"),
                # Standardized boom/bust label (percentile-keyed) -- the canonical
                # categorical grade signal, replacing the legacy _compute_boom_bust.
                "boom_label": _engine_wag_boom_bust(w),
            }
            if WAG_UNIFIED:
                # The per-season baseline the client's WAG chart and summary draw
                # against, and the definition stamp, so the block alone says what it is.
                out["wag"]["expected_rate"] = w.get("expected_rate")
                out["wag"]["definition"] = WAG_DEFINITION
    except Exception:
        pass
    return out or None


_PITCHER_POS_RE = re.compile(r"^(RHP|LHP|SP|RP|MIRP|SIRP|P)")


def _finalize_active_surplus_leaf(m: dict) -> dict:
    """v18 - New financial leaf: sum of the eFV expected surplus across
    the org's active prospects (graduates excluded — they belong to the
    existing fin_contract_surplus / mlb_production_* family) minus the
    FULL acquisition bonus paid (not amortized). surplus_total_mm is
    therefore NET of the bonus and cost_basis_mm is the bonus total, so
    gross = surplus_total_mm + cost_basis_mm; a reader must not subtract
    the cost again. Result = surplus_total_mm, surplus_per_prospect_mm, and a
    contributor count so a Cleveland-style depth org doesn't look the
    same as a top-loaded LAD without per-head normalization. Gates at
    ≥5 contributing actives so a tiny system doesn't anchor on a single
    70-FV signing.

    Reads the per-org `_active_surplus_*` accumulators populated in the
    per-prospect loop (see the build_org_summary main pass).
    """
    n = m.get("_active_surplus_count") or 0
    total_surplus = m.get("_active_surplus_net_mm") or 0.0
    cost_basis = m.get("_active_surplus_cost_mm") or 0.0
    fv_total = m.get("_active_surplus_fv_total") or 0.0
    # v31.5 — Per-side stats. Each side gates at ≥3 contributing
    # prospects (looser than the parent's ≥5 since splitting a small
    # cohort 50/50 makes ≥5 unrealistic on one side).
    n_hit = m.get("_active_surplus_count_hit") or 0
    n_pit = m.get("_active_surplus_count_pit") or 0
    surplus_hit = m.get("_active_surplus_net_mm_hit") or 0.0
    surplus_pit = m.get("_active_surplus_net_mm_pit") or 0.0
    fv_total_hit = m.get("_active_surplus_fv_total_hit") or 0.0
    fv_total_pit = m.get("_active_surplus_fv_total_pit") or 0.0
    per_prospect_hit = round(surplus_hit / n_hit, 2) if n_hit >= 3 else None
    per_prospect_pit = round(surplus_pit / n_pit, 2) if n_pit >= 3 else None
    # v32.0 — $ surplus per FV-point. Higher = star/premium-position
    # loaded; lower = depth-heavy. Gated at ≥5 prospects AND fv_total>0.
    surplus_per_fv_pt = (round(total_surplus / fv_total, 3)
                         if n >= 5 and fv_total > 0 else None)
    # v32.1 — Per-side $/FV-pt asymmetry: orgs with strong-bats-thin-arms
    # (or vice versa) read very differently when split by side. Gated
    # ≥3 per side AND positive fv_total on that side.
    per_fv_pt_hit_mm = (round(surplus_hit / fv_total_hit, 3)
                       if n_hit >= 3 and fv_total_hit > 0 else None)
    per_fv_pt_pit_mm = (round(surplus_pit / fv_total_pit, 3)
                       if n_pit >= 3 and fv_total_pit > 0 else None)
    if n < 5:
        return {
            "surplus_total_mm":        None,
            "surplus_per_prospect_mm": None,
            "active_count":            n,
            "cost_basis_mm":           round(cost_basis, 1) if n else None,
            "per_prospect_hit_mm":     per_prospect_hit,
            "per_prospect_pit_mm":     per_prospect_pit,
            "active_count_hit":        n_hit,
            "active_count_pit":        n_pit,
            "surplus_per_fv_pt_mm":    None,
            "per_fv_pt_hit_mm":        per_fv_pt_hit_mm,
            "per_fv_pt_pit_mm":        per_fv_pt_pit_mm,
            "fv_total":                round(fv_total, 1) if fv_total else None,
            "fv_total_hit":            round(fv_total_hit, 1) if fv_total_hit else None,
            "fv_total_pit":            round(fv_total_pit, 1) if fv_total_pit else None,
        }
    # v32.1 — Per-acquisition-method $/FV efficiency. Buckets accumulated
    # in the per-prospect loop; we compute the per-method ratios here.
    # Gated at ≥3 contributing actives per method (small-sample channels
    # render '—' rather than a misleading single-prospect ratio).
    method_eff: dict[str, dict] = {}
    for label, bucket in (m.get("_method_surplus") or {}).items():
        bn = bucket.get("count") or 0
        bfv = bucket.get("fv_total") or 0.0
        bnet = bucket.get("net_mm") or 0.0
        bcost = bucket.get("cost_mm") or 0.0
        if bn >= 3 and bfv > 0:
            method_eff[label] = {
                "surplus_per_fv_pt_mm": round(bnet / bfv, 3),
                "surplus_total_mm":    round(bnet, 1),
                "fv_total":            round(bfv, 1),
                "count":               bn,
                "cost_basis_mm":       round(bcost, 1),
                "surplus_per_prospect_mm": round(bnet / bn, 2),
            }
        else:
            method_eff[label] = {
                "surplus_per_fv_pt_mm": None,
                "surplus_total_mm":    round(bnet, 1) if bn else None,
                "fv_total":            round(bfv, 1) if bn else None,
                "count":               bn,
                "cost_basis_mm":       round(bcost, 1) if bn else None,
                "surplus_per_prospect_mm": None,
            }

    return {
        "surplus_total_mm":        round(total_surplus, 1),
        "surplus_per_prospect_mm": round(total_surplus / n, 2),
        "active_count":            n,
        "cost_basis_mm":           round(cost_basis, 1),
        "per_prospect_hit_mm":     per_prospect_hit,
        "per_prospect_pit_mm":     per_prospect_pit,
        "active_count_hit":        n_hit,
        "active_count_pit":        n_pit,
        "surplus_per_fv_pt_mm":    surplus_per_fv_pt,
        "per_fv_pt_hit_mm":        per_fv_pt_hit_mm,
        "per_fv_pt_pit_mm":        per_fv_pt_pit_mm,
        "fv_total":                round(fv_total, 1),
        "fv_total_hit":            round(fv_total_hit, 1),
        "fv_total_pit":            round(fv_total_pit, 1),
        # v32.1 — Per-channel $/FV efficiency (draft / IFA / trade).
        # Helps identify which acquisition pathway is best for an org.
        "method_efficiency":       method_eff,
    }


# REMOVED 2026-05: `_compute_breakout_score` was an active-prospect
# composite that conflated "rising" with "high-FV" and rendered as a
# vague BREAKOUT pill. Replaced by the WAG-anchored BOOM / BUST graduate
# labels (`_compute_boom_bust` above) and the per-org boom_pct/bust_pct
# rollups. The "wide FV spread" filter chip stays — it's a different
# concept (source variance, not trajectory).


# Per-tool DvM+ window — earliest tool observation feeding the
# (latest − earliest) delta is re-resolved to the oldest snapshot still
# inside this window from `as_of`. Keeps per-tool dev signal consistent
# with the org-level principal DvM+ window (7y). Tunable in one place; tests
# pin the constant value.
FARM_TOOL_DELTA_LOOKBACK_DAYS = 365 * 7


def _compute_tool_deltas(player_points: list[dict],
                         as_of: str | None = None,
                         lookback_days: int | None = None) -> dict[str, dict]:
    """Per-tool delta for one prospect within a lookback window.

    Walks `player_points[i].tools_consensus` across the prospect's
    history; for each tool with ≥2 observations IN-WINDOW, returns
    first/last grade, delta (latest − earliest), the dates that bracket
    the window, and the observation count. Tools with <2 in-window
    snapshots are skipped (no delta computable).

    Args:
      player_points: time-ordered (or not) snapshot list with each entry
        carrying a `snapshot_date` (ISO `YYYY-MM-DD`) and a
        `tools_consensus` dict.
      as_of: ISO date anchor for the window (defaults to `today`).
      lookback_days: window length. Defaults to
        `FARM_TOOL_DELTA_LOOKBACK_DAYS` (6y). Pass `None` AND override
        with a sentinel like 10_000 to opt out (callers that legitimately
        need lifetime deltas — e.g. the per-prospect detail tooltip).

    Used downstream by:
      * `export_timeseries_json` → enrich each player payload with
        `tool_deltas`; the UI shows a +N / -N chip next to each tool
        grade on the prospect-detail page.
      * `_per_org_tool_dev_aggregates` → feed the per-org DvM+ rollup
        (HitDvM+, PowerDvM+, …, ToolsDvM+).
    """
    from datetime import date as _date, timedelta as _td
    if lookback_days is None:
        lookback_days = FARM_TOOL_DELTA_LOOKBACK_DAYS
    try:
        anchor = (_date.fromisoformat(as_of[:10]) if as_of
                  else _date.today())
    except (ValueError, TypeError):
        anchor = _date.today()
    cutoff = anchor - _td(days=lookback_days)
    cutoff_iso = cutoff.isoformat()
    by_tool: dict[str, list[tuple[str, float]]] = {}
    for pt in player_points or []:
        tc = pt.get("tools_consensus") or {}
        date = pt.get("snapshot_date")
        # Drop snapshots older than the window. Snapshots without a
        # date sit at the very start of any sort order and would skew
        # the earliest-grade pick, so they're also dropped here.
        if not date or str(date)[:10] < cutoff_iso:
            continue
        for k, v in tc.items():
            if v is None:
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            by_tool.setdefault(k, []).append((date, fv))
    out: dict[str, dict] = {}
    for k, obs in by_tool.items():
        if len(obs) < 2:
            continue
        obs.sort(key=lambda x: (x[0] or ""))
        first_date, first_v = obs[0]
        last_date, last_v = obs[-1]
        out[k] = {
            "delta":      round(last_v - first_v, 2),
            "first":      first_v,
            "last":       last_v,
            "first_date": first_date,
            "last_date":  last_date,
            "n_obs":      len(obs),
        }
    return out


# Per-tool DvM+ grouping. Most keys are 1:1 to a canonical tool from
# scrapers.HITTER_TOOL_KEYS / PITCHER_TOOL_KEYS. v14 — `pwr` reads the
# pre-consolidated `pwr` key (mean of game_pwr + raw_pwr at consensus
# time, from cycle 12). The legacy `power` key remains as an alias so
# pre-rebuild payloads still resolve, but new payloads only carry pwr.
TOOL_GROUPS: dict[str, list[str]] = {
    "hit":       ["hit"],
    "pwr":       ["pwr"],
    "speed":     ["speed"],
    "field":     ["field"],
    "arm":       ["throw"],
    "pitch_sel": ["pitch_sel"],
    "bat_ctrl":  ["bat_ctrl"],
    "fb":        ["fb"],
    "sl":        ["sl"],
    "cb":        ["cb"],
    "ch":        ["ch"],
    "cmd":       ["cmd"],
    "ct":        ["ct"],
}


# Position-bucket tool-importance matrix for the composite ToolDvM+. Within
# each bucket the tools that *define* the position carry more weight (a
# catcher's Field/Arm matter more than its Speed; a starter's FB/Command
# more than a fourth pitch). Buckets mirror the tool-dev pass's
# _ALL_BUCKETS (C / INF / OF / SP / RP); 1B/2B/3B/SS roll into INF. Weights
# are relative WITHIN a bucket and are tunable.
_BUCKET_TOOL_IMPORTANCE: dict[str, dict[str, float]] = {
    "C":   {"field": 3.0, "arm": 3.0, "hit": 2.0, "bat_ctrl": 1.0,
            "pitch_sel": 1.0, "pwr": 1.0, "speed": 0.5},
    "INF": {"field": 3.0, "arm": 2.0, "hit": 2.0, "speed": 1.5,
            "pwr": 1.5, "bat_ctrl": 1.0, "pitch_sel": 1.0},
    "OF":  {"speed": 2.5, "hit": 2.0, "pwr": 2.0, "field": 2.0,
            "arm": 1.5, "bat_ctrl": 1.0, "pitch_sel": 1.0},
    "SP":  {"fb": 3.0, "cmd": 3.0, "sl": 1.5, "cb": 1.5, "ch": 1.5, "ct": 1.0},
    "RP":  {"fb": 3.0, "cmd": 2.0, "sl": 2.0, "cb": 1.0, "ch": 1.0, "ct": 1.0},
}


def _bucket_weighted_tool_dvm(per_grp: dict, by_bucket: dict,
                              counts_by_bucket: dict) -> int | None:
    """Composite ToolDvM+ for one org: a position-bucket importance-weighted
    blend of per-tool DvM+ values.

    For each bucket (C/INF/OF/SP/RP) we take a weighted mean of that bucket's
    own per-tool DvM+ (``by_bucket[bucket]``), weighting each tool by its
    position importance and falling back to the org-wide value
    (``per_grp[tool]``) when a bucket cell is sparse/None. The per-bucket
    composites are then blended by how many prospects the org develops in
    each bucket (``counts_by_bucket[bucket][tool]["n_prospects"]``), so the
    org's composite leans toward the positions it actually has.

    Falls back to the legacy unweighted org-wide mean when no bucket data
    exists (tiny / sparse orgs). Returns ``None`` when the org has no
    per-tool DvM+ at all.

    Args:
        per_grp: org-wide ``per_tool_dvm_plus`` {tool_group: dvm_plus|None}.
        by_bucket: ``per_tool_dvm_plus_by_bucket`` {bucket: {tool: dvm|None}}.
        counts_by_bucket: ``per_tool_by_bucket`` {bucket: {tool: {n_prospects}}}.
    """
    per_grp = per_grp or {}
    by_bucket = by_bucket or {}
    counts_by_bucket = counts_by_bucket or {}

    bucket_blend: list[tuple[float, float]] = []  # (composite, blend weight)
    for bucket, weights in _BUCKET_TOOL_IMPORTANCE.items():
        # Only blend buckets the org actually develops prospects in. The
        # per-tool hybrid fallback below fills sparse cells WITHIN an
        # existing bucket from the org-wide value, but a bucket with no
        # data at all is skipped (not synthesized from org-wide grades) so
        # the legacy unweighted-mean fallback stays reachable.
        if bucket not in by_bucket:
            continue
        cell = by_bucket.get(bucket) or {}
        num = den = 0.0
        for tk, w in weights.items():
            if w <= 0:
                continue
            v = cell.get(tk)
            if v is None:                  # hybrid fallback to org-wide
                v = per_grp.get(tk)
            if v is None:
                continue
            num += w * v
            den += w
        if den <= 0:
            continue
        bucket_comp = num / den
        cnt_cell = counts_by_bucket.get(bucket) or {}
        bw = sum((cnt_cell.get(tk) or {}).get("n_prospects", 0) for tk in weights)
        bucket_blend.append((bucket_comp, float(max(bw, 1))))

    if bucket_blend:
        tot_w = sum(w for _, w in bucket_blend)
        return int(round(sum(c * w for c, w in bucket_blend) / tot_w))

    # Legacy unweighted org-wide mean fallback (tiny / sparse orgs).
    vs = [v for v in per_grp.values() if v is not None]
    return int(round(sum(vs) / len(vs))) if vs else None


# Statcast pitch-type code → TOOL_GROUPS pitcher-tool key. Used by the
# league-pitch-usage aggregator to roll per-prospect arsenal usage_pct
# rows into a single per-tool weight. Pitch codes that don't have a
# scouting analog (knuckle, sweeper variants) are mapped to the closest
# tool group; anything still unmapped is silently dropped (it doesn't
# affect the weighted mean since its weight ends up 0).
_PITCH_TYPE_TO_TOOL = {
    # Fastball family
    "FF": "fb", "FT": "fb", "SI": "fb", "FA": "fb",
    # Slider family (incl. sweeper)
    "SL": "sl", "ST": "sl", "SV": "sl",
    # Curveball family
    "CU": "cb", "KC": "cb", "CS": "cb",
    # Changeup
    "CH": "ch",
    # Cutter
    "FC": "ct",
}


def _league_pitch_usage(pitch_arsenals: dict[str, dict]) -> dict[str, float]:
    """Aggregate per-prospect pitch_arsenal usage_pct into a league-wide
    {tool_key: usage_share} map. Used to weight the pitcher-side
    Development composite so a heavily-thrown pitch's DvM+ counts more
    than a sparse pitch's DvM+ in the rollup.

    Input shape: `{player_key: {pitches: [{pitch_type, usage_pct, ...}], ...}}`
    Output: normalized weights summing to 1.0 across the mapped tool
    keys. Pitch codes not in `_PITCH_TYPE_TO_TOOL` are skipped.
    """
    if not pitch_arsenals:
        return {}
    raw: dict[str, float] = {}
    for arsenal in pitch_arsenals.values():
        for px in (arsenal.get("pitches") or []):
            code = (px.get("pitch_type") or "").upper()
            tool = _PITCH_TYPE_TO_TOOL.get(code)
            if not tool:
                continue
            try:
                usage = float(px.get("usage_pct") or 0.0)
            except (TypeError, ValueError):
                continue
            raw[tool] = raw.get(tool, 0.0) + usage
    total = sum(raw.values())
    if total <= 0:
        return {}
    return {k: round(v / total, 4) for k, v in raw.items()}


def _eff_grade(p: dict):
    """The org-ranking grade for a prospect dict: eFV where rated, consensus FV otherwise."""
    g = p.get("xfv_grade")
    return g if g is not None else p.get("fv_raw")


def _top_end_points(prospects: list[dict], n: int = FARM_TOP_END_COUNT) -> float:
    """Sum of tiered points for the org's top N prospects, ranked by eFV (consensus fallback)."""
    ranked = sorted(prospects, key=lambda p: (_eff_grade(p) or 0), reverse=True)
    return round(sum(_fv_to_points(_eff_grade(p)) for p in ranked[:n]), 2)


def _depth_points(prospects: list[dict],
                  start: int = FARM_DEPTH_START,
                  end: int = FARM_DEPTH_END) -> float:
    """Sum of tiered points for prospects ranked `start+1` through `end`, by eFV (fallback FV)."""
    ranked = sorted(prospects, key=lambda p: (_eff_grade(p) or 0), reverse=True)
    return round(sum(_fv_to_points(_eff_grade(p)) for p in ranked[start:end]), 2)


def _trajectory_score(fv_history: list[dict],
                      lookback_days: int = FARM_TRAJECTORY_LOOKBACK_DAYS,
                      smooth_window: int = FARM_TRAJECTORY_SMOOTH_WINDOW,
                      as_of: "date | None" = None) -> float:
    """Smoothed FV trajectory: mean of last `smooth_window` history points
    minus mean of `smooth_window` points ending at/near the lookback cutoff.

    Smoothing on both ends dilutes any single source's update — the user
    complaint about the old `_rolling_fv_delta` was that one swing from
    one source dominated the signal. Averaging 3 points on each end
    reduces that to ~33% of the result."""
    if not fv_history or len(fv_history) < 2:
        return 0.0
    today = as_of or date.today()
    cutoff = (today - timedelta(days=lookback_days)).isoformat()

    k = min(smooth_window, len(fv_history))
    recent_mean = sum(p["total_fv"] for p in fv_history[-k:]) / k

    baseline_candidates = [p for p in fv_history if p["date"] <= cutoff]
    if not baseline_candidates:
        # Whole history is inside the window — baseline against the earliest
        # points so we still report a directionally-correct change.
        baseline_candidates = fv_history[:k]
    bk = min(smooth_window, len(baseline_candidates))
    baseline_mean = sum(p["total_fv"] for p in baseline_candidates[-bk:]) / bk

    return round(recent_mean - baseline_mean, 1)


def _grad_pipeline_score(fv_events: list[dict],
                         months: int = FARM_GRAD_PIPELINE_MONTHS,
                         as_of: "date | None" = None) -> float:
    """FV-weighted graduations in the trailing window. Each grad's FV at
    graduation time contributes its tiered point value — so promoting a
    60 FV is worth ~18 points and a 40 FV is worth 1."""
    if not fv_events:
        return 0.0
    today = as_of or date.today()
    cutoff = (today - timedelta(days=months * 30)).isoformat()
    total = 0.0
    for e in fv_events:
        if e.get("kind") != "debut_marker":
            continue
        if (e.get("date") or "") < cutoff:
            continue
        total += _fv_to_points(e.get("fv"))
    return round(total, 2)


def _grad_pace_score(fv_events: list[dict],
                     window_years: int = 7,
                     fv_floor: float = 50.0,
                     as_of: "date | None" = None) -> "float | None":
    """Sustained graduation PACE: FV>=`fv_floor` debuts per YEAR over the trailing
    `window_years`. Complements `_grad_pipeline_score` (FV-weighted POINTS in the
    trailing 12mo) by measuring the RHYTHM of quality graduations — a steady stream
    of MLB-quality grads vs. one lumpy class. Returns grads/yr (0.0 when the org has
    events but no qualifying grads); None only when there are no events at all."""
    if not fv_events:
        return None
    today = as_of or date.today()
    cutoff = (today - timedelta(days=window_years * 365)).isoformat()
    n = 0
    for e in fv_events:
        if e.get("kind") != "debut_marker":
            continue
        if (e.get("date") or "") < cutoff:
            continue
        fv = e.get("fv")
        if fv is not None and fv >= fv_floor:
            n += 1
    return round(n / window_years, 3) if window_years else None


def _rank_percentile(values: list[float]) -> list[float]:
    """Convert a list of scores to rank percentiles in [0, 1] where 1.0 is
    the best (highest input). Ties get the average percentile of the tied
    rank block so two identical farms don't fight over a tiebreaker that
    isn't really there.
    """
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [1.0]
    indexed = sorted(range(n), key=lambda i: values[i], reverse=True)
    pct = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[indexed[j + 1]] == values[indexed[i]]:
            j += 1
        # tied block covers ranks [i+1 .. j+1]; assign the average percentile
        avg_rank = (i + j) / 2 + 1  # 1-based midpoint
        share = (n - avg_rank) / (n - 1)
        for k in range(i, j + 1):
            pct[indexed[k]] = share
        i = j + 1
    return pct


def _normalize_to_100(values: list[float]) -> list[float]:
    """Map values to a 0-100 scale anchored at the 5th/95th percentile of
    the input list. Values outside that range clamp to 0 or 100. Percentile
    anchors (instead of min/max) keep one outlier from flattening the rest
    of the distribution into a tiny band."""
    if not values:
        return []
    if len(values) == 1:
        return [100.0]
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    lo_idx = max(0, int(round(n * 0.05)) - 1)
    hi_idx = min(n - 1, int(round(n * 0.95)) - 1)
    if hi_idx <= lo_idx:
        lo_idx, hi_idx = 0, n - 1
    lo = sorted_vals[lo_idx]
    hi = sorted_vals[hi_idx]
    rng = hi - lo
    if rng <= 0:
        return [50.0] * len(values)
    return [round(max(0.0, min(100.0, (v - lo) / rng * 100.0)), 1) for v in values]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.strip().replace("%", "")
            if not value or value == "—":
                return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _live_signal_for_player(
    *,
    statline: dict | None,
    statcast: dict | None,
    zone: dict | None,
    health: dict | None,
    il_row: dict | None,
    source_events: list[dict],
) -> dict | None:
    """Fast-moving overlay separate from source consensus."""
    drivers: list[dict] = []
    raw = 0.0
    sample_weight = 0.0
    sl = statline or {}
    is_pitcher = bool(sl.get("is_pitcher"))
    if sl:
        if is_pitcher:
            bf = _safe_float(sl.get("tbf"))
            ip = _safe_float(sl.get("ip"))
            if bf is None and ip is not None:
                bf = ip * 4.25
            sample_weight = (bf or 0.0) / ((bf or 0.0) + 180.0) if bf else 0.0
            level_plus = _safe_float(sl.get("level_plus_pct"))
            stf = _safe_float(sl.get("stf_plus_periph"))
            if level_plus is not None:
                v = _clamp(level_plus / 18.0, -3.0, 3.0)
                raw += 0.8 * v
                if abs(v) >= 0.8:
                    drivers.append({"label": "level run prevention", "value": round(level_plus, 1), "impact": round(0.8 * v, 2)})
            if stf is not None:
                v = _clamp((stf - 100.0) / 12.0, -2.0, 2.0)
                raw += 0.5 * v
                if abs(v) >= 0.7:
                    drivers.append({"label": "peripheral stuff", "value": round(stf, 1), "impact": round(0.5 * v, 2)})
        else:
            pa = _safe_float(sl.get("pa"))
            if pa is None:
                ab = _safe_float(sl.get("ab"))
                games = _safe_float(sl.get("games"))
                pa = ab if ab is not None else (games * 4.1 if games is not None else None)
            sample_weight = (pa or 0.0) / ((pa or 0.0) + 120.0) if pa else 0.0
            ops_plus = _safe_float(sl.get("ops_plus_level"))
            if ops_plus is not None:
                v = _clamp((ops_plus - 100.0) / 18.0, -3.0, 3.0)
                raw += 0.9 * v
                if abs(v) >= 0.8:
                    drivers.append({"label": "level-adjusted offense", "value": round(ops_plus, 1), "impact": round(0.9 * v, 2)})
    cq = ((statcast or {}).get("contact_quality") or {})
    if cq and not is_pitcher:
        bbe = _safe_float(cq.get("batted_balls"))
        bbe_w = (bbe or 0.0) / ((bbe or 0.0) + 75.0) if bbe else 0.0
        xwoba = _safe_float(cq.get("xwoba_est"))
        xwobacon = _safe_float(cq.get("xwobacon_est"))
        p90 = _safe_float(cq.get("p90_ev"))
        sc_raw = 0.0
        if xwoba is not None:
            sc_raw += _clamp((xwoba - 0.330) / 0.035, -2.5, 2.5)
        if xwobacon is not None:
            sc_raw += 0.6 * _clamp((xwobacon - 0.390) / 0.045, -2.0, 2.0)
        if p90 is not None:
            sc_raw += 0.4 * _clamp((p90 - 104.0) / 4.0, -2.0, 2.0)
        if sc_raw:
            impact = 0.75 * bbe_w * sc_raw
            raw += impact
            sample_weight = max(sample_weight, bbe_w)
            if abs(impact) >= 0.6:
                drivers.append({"label": "contact quality", "value": round(sc_raw, 2), "impact": round(impact, 2)})
    z = zone or {}
    if z and not is_pitcher:
        pitches = _safe_float(z.get("pitches"))
        zone_w = (pitches or 0.0) / ((pitches or 0.0) + 250.0) if pitches else 0.0
        zc = _safe_float(z.get("z_contact_pct"))
        chase = _safe_float(z.get("o_swing_pct"))
        zone_raw = 0.0
        if zc is not None:
            zone_raw += _clamp((zc - 82.0) / 7.0, -2.0, 2.0)
        if chase is not None:
            zone_raw += _clamp((27.0 - chase) / 6.0, -2.0, 2.0)
        if zone_raw:
            impact = 0.45 * zone_w * zone_raw
            raw += impact
            sample_weight = max(sample_weight, zone_w)
            if abs(impact) >= 0.5:
                drivers.append({"label": "zone discipline", "value": round(zone_raw, 2), "impact": round(impact, 2)})
    source_raw = 0.0
    latest_rank = None
    for ev in source_events or []:
        et = ev.get("event_type")
        conf = float(ev.get("confidence") or 0.5)
        payload = ev.get("payload") or {}
        if et == "top100_rank" and ev.get("rank_after"):
            latest_rank = ev.get("rank_after") if latest_rank is None else min(latest_rank, ev.get("rank_after"))
            source_raw += conf * _clamp((101 - float(ev["rank_after"])) / 30.0, 0.4, 3.2)
        elif et == "top100_joined":
            source_raw += 4.0 * conf
        elif et == "top100_dropped":
            source_raw -= 4.0 * conf
        elif et == "top100_movement":
            diff = _safe_float(payload.get("june_diff"))
            token = payload.get("june_token")
            if token == "Dr.":
                source_raw -= 4.0 * conf
            elif diff is not None:
                source_raw += conf * _clamp(diff / 8.0, -4.0, 4.0)
        elif et == "statcast_by_age_standout":
            source_raw += 1.5 * conf
        elif et == "injury_note":
            source_raw -= 1.0 * conf
    if source_raw:
        source_impact = _clamp(source_raw, -7.0, 7.0)
        raw += source_impact
        label = "BA/source movement"
        if latest_rank is not None:
            label = f"BA Top 100 #{latest_rank}"
        drivers.append({"label": label, "impact": round(source_impact, 2)})
    h = health or {}
    il = il_row or {}
    injury_penalty = 0.0
    if il.get("is_on_il"):
        injury_penalty -= 1.5
        if str(il.get("type") or "").startswith("60"):
            injury_penalty -= 1.0
    days = _safe_float(h.get("il_days_12mo"))
    stints = _safe_float(h.get("il_stints_12mo"))
    if days and days >= 60:
        injury_penalty -= 1.0
    if stints and stints >= 2:
        injury_penalty -= 1.25
    if injury_penalty:
        raw += injury_penalty
        drivers.append({"label": "injury drag", "value": round(days or 0), "impact": round(injury_penalty, 2)})
    if not drivers:
        return None
    final = _clamp(raw * max(0.45, min(1.0, 0.55 + sample_weight)), -8.0, 8.0)
    if abs(final) < 0.35:
        return None
    return {
        "delta": round(final, 2),
        "sample_weight": round(sample_weight, 3),
        "rank_pressure": round(-final * 8),
        "tier": "up" if final >= 2.0 else "down" if final <= -2.0 else "watch",
        "drivers": sorted(drivers, key=lambda d: abs(d.get("impact") or 0), reverse=True)[:5],
    }


# Letter-grade buckets calibrated for ~30 orgs (v6 — harsher curve).
# A+ is reserved for the #1 farm. The top of the scale is steeper
# (A = top 7% vs the old top 10%) so an "A-tier" reads as genuinely
# elite, not "above-average". The bottom adds a D- tier and an F at the
# very floor — the user explicitly wants weak orgs to read as poor, not
# just "below average". F lands at ~bottom 3% (~1 org in a 30-team
# league); D- at ~bottom 10%. Combined with the `_stretch_composite`
# remap below, weak orgs sit further below the mean BEFORE being
# ranked, so the F isn't just a label — it reflects a real distance
# from the league mean.
def _letter_grade(rank: int, n: int) -> str:
    if n <= 0 or rank is None:
        return "—"
    if rank == 1:
        return "A+"
    if n == 1:
        return "A+"
    pct = (rank - 1) / (n - 1)
    if pct < 0.07: return "A"      # top 7%   (was 10%)
    if pct < 0.14: return "A-"     # 7-14%    (was 10-20%)
    if pct < 0.24: return "B+"     # 14-24%   (was 20-30%)
    if pct < 0.36: return "B"      # 24-36%   (was 30-45%)
    if pct < 0.50: return "B-"     # 36-50%   (was 45-60%)
    if pct < 0.62: return "C+"     # 50-62%   (was 60-72%)
    if pct < 0.74: return "C"      # 62-74%   (was 72-85%)
    if pct < 0.86: return "C-"     # 74-86%   (was 85-95%)
    if pct < 0.93: return "D"      # 86-93%   (was bottom catch-all)
    if pct < 0.97: return "D-"     # NEW — 93-97%
    return "F"                     # NEW — bottom ~3% (~1 org in 30)


def _stretch_composite(score: float, mean: float = 100.0,
                       factor: float = 1.35) -> float:
    """Linear remap that magnifies distance from the league mean.

    `factor=1.35` widens the spread ~35% — strong orgs pull further
    above the mean, weak orgs drop further below. Mean defaults to 100
    because the farm-tree composite lives on the DvM+-style
    100-anchored scale (each main branch z-rescaled to mean=100,
    +10pts=1σ). Output is clamped only at 0 (composite can't be
    negative) — the upper end is unbounded so a truly elite farm can
    score >120, matching the pre-stretch headroom.

    Math: stretched = mean + (score - mean) * factor

    Rank order is preserved (monotonic) and the mean is a fixed point.
    Pairs with `_letter_grade`: stretch increases the composite distance
    between farms, then the steeper percentile cutoffs convert that into
    an F at the bottom and a more selective A at the top.

    CALL SITES AND WHY THEY DO NOT COMPOUND (documented 2026-07-29).
    Four sites apply this: per-tool DvM+ (1.35), per-bucket per-tool DvM+
    (1.35), farm_score (1.20) and farm_score_by_window (1.20). The per-tool
    values do flow toward farm_score, but every path from them to farm_score
    passes through `_zscore_to_100`, an affine re-standardization across the
    30 orgs, and z-scoring annihilates any affine map applied to its input.
    So 1.35 and 1.20 act on DISJOINT display surfaces; they never multiply,
    and there is no 1.62x net widening on the DvM+ axis. Measured published
    spread on the served 30-org run: per-tool DvM+ sd 11.2-12.6, ToolDvM+
    composite sd 2.9, farm_score sd 6.4. None of those is the nominal 10
    points per sigma; each site now states its own scale next to the call.
    The one place a stretch is NOT purely presentational is the per-bucket
    pass, whose stretched output enters `_blend_dvm_3way` alongside unstretched
    FV and Statcast legs; that is documented at that call site.
    """
    if score is None:
        return score
    stretched = mean + (score - mean) * factor
    return max(0.0, round(stretched, 1))


def _rank_descending(values: list[float]) -> list[int]:
    """Return 1-based ranks where the largest input gets rank 1. Ties get
    the same rank (their shared best-of-block rank — `[5, 5, 3]` →
    `[1, 1, 3]`)."""
    n = len(values)
    if n == 0:
        return []
    indexed = sorted(range(n), key=lambda i: values[i], reverse=True)
    ranks = [0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[indexed[j + 1]] == values[indexed[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[indexed[k]] = i + 1
        i = j + 1
    return ranks


def _build_org_fv_history(
    players: list[PlayerTimeseries],
    filter_real_trades,
    trades_by_player: dict[str, list[dict]],
    xfv_hist_by_key: dict | None = None,
    calendar=None,
) -> dict[str, dict]:
    """
    Build per-org cumulative **development** FV time series + events.

    The series tracks how each org's prospects grow ABOVE their baseline
    FV at the time they entered the org — so incoming acquisitions
    (trades, draft, IFA) contribute zero on the day they arrive; only
    subsequent FV growth (or decline) shows up on the line.

    Algorithm:
      1. Walk each player's chronological stream (snapshots + trades +
         graduations).
      2. On the FIRST snapshot we see while a player is in a given org,
         record that org's entry baseline for the player (no contribution
         to the running total on that date — just plant a marker).
      3. On subsequent snapshots in the same org, contribute the delta
         from the prior snapshot (`new_fv - prev_fv`). This is the org's
         development credit for that player.
      4. On a trade, the source org's accumulated development credit
         stays in their cumulative chart (development credit is
         permanent — an org doesn't lose past credit for trading a
         developed prospect away). The receiving org records a new
         entry baseline at the player's current FV and only future
         snapshots in that org count.
      5. Graduations don't subtract — the org keeps credit for whatever
         development happened before the player exited the system.

    Returns:
      {
        "ATL": {
          "series": [{"date": "2024-01-04", "total_fv": 0.0}, ...],
          "events": [{"date": "2024-07-30", "kind": "trade", "player_name":
                      "Drew Jones", "fv": 50.0, "other_org": "MIA"},
                     {"date": "2025-04-01", "kind": "debut_marker",
                      "player_name": "Spencer Schwellenbach", "fv": 55.0},
                      ...],
        },
        ...
      }

    `series.total_fv` here is interpreted as "cumulative DEVELOPMENT-FV"
    rather than "cumulative roster FV". Event markers (trade in/out,
    graduation) still annotate the chart even though they don't move
    the line.

    VAL_4 (2026-10-08): `calendar(player_key)` returns the player's org
    tenures (dev_attribution). With one, the club on each date comes from the
    calendar, not from trades alone (a waiver claim, Rule 5 move, release or
    signing elsewhere also changes the club, and a graduate who left by free
    agency no longer sits at his new club for his whole history), and a
    snapshot-to-snapshot step that spans a club change is split by days
    between the clubs; an unaffiliated stretch credits nobody. Players the
    calendar does not cover keep the trade rule above.
    """
    from trades import canonical_org
    from collections import defaultdict

    # contribs[(org, date)] = signed FV delta applied that day
    contribs: dict[tuple[str, str], float] = defaultdict(float)
    # events_by_org: list of (date, kind, player_name, fv, other_org)
    events_by_org: dict[str, list[dict]] = defaultdict(list)
    # Track every date any org sees a change so the time series isn't
    # collapsed to only dates where a player was added — graduations and
    # trades show up too.
    dates_by_org: dict[str, set[str]] = defaultdict(set)

    for p in players:
        if not p.points:
            continue
        sorted_points = sorted(p.points, key=lambda pt: pt.snapshot_date)

        # Pre-filter trades to the ones our chart actually surfaces (the
        # same set the prospect transaction history shows). Canonicalize
        # team codes so trade-attribution lines up with org_summary keys.
        raw_trades = trades_by_player.get(p.player_key, []) or []
        real_trades = filter_real_trades(raw_trades)
        trades = []
        for t in real_trades:
            d = t.get("trade_date")
            cf = canonical_org(t.get("from_org"))
            ct = canonical_org(t.get("to_org"))
            if not (d and cf and ct):
                continue
            trades.append({"date": d, "from": cf, "to": ct})
        trades.sort(key=lambda t: t["date"])

        _cal = calendar(p.player_key) if calendar is not None else None
        if _cal:
            _cal_player_history(p, sorted_points, trades, _cal, xfv_hist_by_key,
                                contribs, events_by_org, dates_by_org)
            continue

        # Initial org: pre-first-trade owner if any trade exists, else
        # the player's current org. Canonicalized to align with the keys
        # used in org_summary.
        current_org = canonical_org(p.org) if p.org else None
        initial_org = trades[0]["from"] if trades else current_org
        if not initial_org:
            continue

        # Merge snapshots + trades into one chronological stream. On a
        # date with both, apply snapshot first (the FV update reflects
        # the source's view as of the publication date), then the trade.
        # Each entry: (date, "snapshot", fv) | (date, "trade", from, to)
        stream: list[tuple] = []
        # eFV development credit: use the eFV grade at each snapshot (joined by date),
        # consensus FV fallback where eFV has no value for that snapshot. Dates match because
        # xfv_history is built from the same points[].snapshot_date.
        _xmap = {pt.get("d"): pt.get("x")
                 for pt in ((xfv_hist_by_key or {}).get(p.player_key) or [])
                 if pt.get("d") and pt.get("x") is not None}
        for pt in sorted_points:
            _fv = _xmap.get(pt.snapshot_date, pt.consensus_fv_raw)
            stream.append((pt.snapshot_date, "snapshot", _fv))
        for t in trades:
            stream.append((t["date"], "trade", t["from"], t["to"]))
        if p.status == "debuted" and p.debut_date:
            stream.append((p.debut_date, "debut_marker"))
        # Stable sort: ties resolved by index in `stream` (snapshots first
        # because they're appended before trades).
        stream.sort(key=lambda x: x[0])

        org_now = initial_org
        fv_now = 0.0
        # Per-org "have we set the baseline yet?" flag. The first
        # snapshot we see for the player in a given org plants the
        # baseline (no contribution); subsequent snapshots credit the
        # delta. Trades-in reset this for the receiving org so the
        # acquisition itself contributes nothing — only future
        # development credits the new org.
        baselined: set[str] = set()
        for ev in stream:
            d = ev[0]
            kind = ev[1]
            if kind == "snapshot":
                new_fv = ev[2]
                if org_now not in baselined:
                    # First snapshot for this player while in this org —
                    # plant the entry baseline. Add the date to the org's
                    # series so the chart has a starting point on the day
                    # the org first "saw" the player, but contribute 0.
                    baselined.add(org_now)
                    dates_by_org[org_now].add(d)
                else:
                    # WAR-tail-weighted trajectory: rather than raw FV
                    # delta (which credits a 40→45 jump the same as a
                    # 70→75 jump), credit the FV-implied WAR delta from
                    # the FV_EXPECTED_WAR curve. A 70→75 lift contributes
                    # ~15 WAR; a 40→45 lift contributes ~1 WAR — exactly
                    # the tail weighting users expect.
                    war_before = _fv_to_expected_war(fv_now) or 0.0
                    war_after  = _fv_to_expected_war(new_fv) or 0.0
                    delta_war = war_after - war_before
                    if delta_war != 0:
                        contribs[(org_now, d)] += delta_war
                        dates_by_org[org_now].add(d)
                fv_now = new_fv
            elif kind == "trade":
                from_org, to_org = ev[2], ev[3]
                # If from_org doesn't match our tracked org_now (rare,
                # e.g. stale inference), trust the API record.
                source_org = org_now if org_now == from_org else from_org
                # Development credit is PERMANENT — the source org keeps
                # whatever development they earned before the trade. The
                # receiving org records a baseline at the player's current
                # FV and only future snapshots count. Both sides get an
                # event marker for chart annotation; neither side moves
                # the cumulative line on this date.
                dates_by_org[source_org].add(d)
                dates_by_org[to_org].add(d)
                events_by_org[source_org].append({
                    "date": d, "kind": "trade", "player_name": p.player_name,
                    "player_key": p.player_key, "fv": round(fv_now, 1),
                    "other_org": to_org, "direction": "out",
                })
                events_by_org[to_org].append({
                    "date": d, "kind": "trade", "player_name": p.player_name,
                    "player_key": p.player_key, "fv": round(fv_now, 1),
                    "other_org": source_org, "direction": "in",
                })
                org_now = to_org
                # Treat the receiving org as "baselined" immediately —
                # the trade itself sets the baseline (fv_now), and the
                # next snapshot will credit only growth above it.
                baselined.add(to_org)
            elif kind == "debut_marker":
                # Graduation is a successful exit — the org keeps the
                # development credit they earned, the line stays flat
                # through the event. Marker is annotated for the chart.
                events_by_org[org_now].append({
                    "date": d, "kind": "debut_marker",
                    "player_name": p.player_name,
                    "player_key": p.player_key, "fv": round(fv_now, 1),
                })

    # Convert per-org contribs to running-sum series.
    # Under the development-only model the line legitimately starts at
    # 0 (no development credit yet) and may stay flat for stretches —
    # so we keep every recorded date, including leading zeroes, rather
    # than skipping ahead to the first non-zero point.
    result: dict[str, dict] = {}
    for org, dates in dates_by_org.items():
        running = 0.0
        series = []
        for d in sorted(dates):
            running += contribs[(org, d)]
            series.append({"date": d, "total_fv": round(running, 1)})
        events = sorted(events_by_org.get(org, []),
                        key=lambda e: (e["date"], e["kind"]))
        result[org] = {"series": series, "events": events}
    return result


def _cal_player_history(p, sorted_points, trades, cal, xfv_hist_by_key,
                        contribs, events_by_org, dates_by_org) -> None:
    """One player's development credit on an org calendar (VAL_4).

    Same rule as the trade path of _build_org_fv_history: the first snapshot
    plants a baseline and credits nothing; each later snapshot credits the
    expected-WAR delta from the previous one. The club comes from the calendar,
    and a step that spans a club change is split by days across the tenures it
    spans (dev_attribution.split_pair); an earlier club's part is dated at its
    tenure's end. Trade and debut markers annotate the chart as before."""
    import dev_attribution as _da
    _xmap = {pt.get("d"): pt.get("x")
             for pt in ((xfv_hist_by_key or {}).get(p.player_key) or [])
             if pt.get("d") and pt.get("x") is not None}
    stream: list[tuple] = []
    for pt in sorted_points:
        stream.append((pt.snapshot_date, "snapshot", _xmap.get(pt.snapshot_date, pt.consensus_fv_raw)))
    for t in trades:
        stream.append((t["date"], "trade", t["from"], t["to"]))
    if p.status == "debuted" and p.debut_date:
        stream.append((p.debut_date, "debut_marker"))
    stream.sort(key=lambda x: x[0])
    prev = None                     # (date, fv) of the last snapshot
    fv_now = 0.0
    for ev in stream:
        d, kind = ev[0], ev[1]
        if kind == "snapshot":
            new_fv = ev[2]
            if prev is None:
                o = _da.org_on(cal, d)
                if o:
                    dates_by_org[o].add(d)
            else:
                war_before = _fv_to_expected_war(prev[1]) or 0.0
                war_after = _fv_to_expected_war(new_fv) or 0.0
                delta_war = war_after - war_before
                if delta_war != 0:
                    for i, f in _da.split_pair(prev[0], d, cal):
                        o = cal[i].org
                        if not o:
                            continue
                        cd = d if cal[i].end > d else cal[i].end
                        contribs[(o, cd)] += delta_war * f
                        dates_by_org[o].add(cd)
            prev = (d, new_fv)
            fv_now = new_fv if new_fv is not None else fv_now
        elif kind == "trade":
            from_org, to_org = ev[2], ev[3]
            dates_by_org[from_org].add(d)
            dates_by_org[to_org].add(d)
            events_by_org[from_org].append({
                "date": d, "kind": "trade", "player_name": p.player_name,
                "player_key": p.player_key, "fv": round(fv_now or 0.0, 1),
                "other_org": to_org, "direction": "out",
            })
            events_by_org[to_org].append({
                "date": d, "kind": "trade", "player_name": p.player_name,
                "player_key": p.player_key, "fv": round(fv_now or 0.0, 1),
                "other_org": from_org, "direction": "in",
            })
        elif kind == "debut_marker":
            o = _da.org_on(cal, d)
            if o:
                events_by_org[o].append({
                    "date": d, "kind": "debut_marker",
                    "player_name": p.player_name,
                    "player_key": p.player_key, "fv": round(fv_now or 0.0, 1),
                })


def _build_dev_attribution(players, trades_by_player, acquisitions, filter_real_trades):
    """VAL_4: the development attribution for the export's player pools, or None
    (logged) when it cannot be built, in which case every consumer keeps the
    current-club credit."""
    try:
        import dev_attribution as _da
        from trades import canonical_org as _co
        infos = []
        for p in players:
            if not p.player_key:
                continue
            debut = p.debut_date if p.status == "debuted" else None
            listed = None
            for pt in reversed(p.points or []):
                if pt.org and (not debut or (pt.snapshot_date or "") <= debut):
                    listed = _co(pt.org)
                    break
            status = ("debuted" if p.status == "debuted"
                      else "active" if p.status == "active" else "inactive")
            infos.append(_da.PlayerInfo(p.player_key, _co(p.org) if p.org else None,
                                        status, debut, listed))
        trades = {k: filter_real_trades(v or []) for k, v in (trades_by_player or {}).items()}
        since = (date.today() - timedelta(days=FARM_TOOL_DELTA_LOOKBACK_DAYS)).isoformat()
        with connect() as con:
            return _da.build(infos, trades_by_player=trades, acquisitions=acquisitions or {},
                             con=con, tool_since=since)
    except Exception:                                   # noqa: BLE001 - degrade, never abort
        log.exception("dev_attribution: build failed; graduates and ToolDvM+ keep the current club")
        return None


def _file_equals_bytes(path: Path, data: bytes, chunk: int = 1 << 20) -> bool:
    """Return True iff `path`'s on-disk bytes equal `data`, comparing in
    `chunk`-sized reads so the whole file is never loaded into a SECOND full
    buffer alongside `data`.

    This backs the export compare-before-write (finding [19]): the naive
    `path.read_bytes() == data` doubles the transient footprint at the export
    peak for the large monolithic sidecars (debuts.json ~60MB, scout_reports
    ~29MB, inactive ~22MB) - `data` and the whole-file read are both live at
    once. Streaming holds only one chunk (+ a zero-copy memoryview slice of
    `data`) beyond `data` itself, preserving byte-identical compare semantics
    (and therefore the rsync/gzip mtime-stability skip)."""
    n = len(data)
    mv = memoryview(data)
    try:
        with open(path, "rb") as fh:
            pos = 0
            while pos < n:
                block = fh.read(chunk)
                if not block:
                    return False  # on-disk file is shorter than `data`
                blen = len(block)
                if block != mv[pos:pos + blen]:
                    return False
                pos += blen
            # `data` fully matched; the file must not carry extra trailing bytes.
            return not fh.read(1)
    finally:
        mv.release()


def _roster_status_with_derived_seasons(rs: dict | None,
                                        cw: dict | None) -> dict:
    """Return the exported `roster_status` block with `mlb_seasons` filled in
    from the career-WAR season map when the roster feed did not supply it.

    WHY (R5.3, 2026-08-04). `mlb_seasons` is derived in stats.derive_roster_status
    from career_stats rows at level == 'MLB'. When the identity behind a key never
    resolved to MLB career rows, that list comes out EMPTY - 782 of 2,681
    debuts.json rows on the 2026-08-04 build. Empty is indistinguishable from
    "never played in MLB", so the trade board's inactive-drop rule
    (bayes_trade_value._roster_seasons_index) could not see those rows at all, and
    three of them - one a FUSED IDENTITY, a live DSL arm born 2007 welded to a
    2011 debut - reached the board at a published price. The career_war table
    stores an independent per-season map from bbref for the same key (see the
    career_war schema comment near the top of this module), so it answers "when
    did the MLB career attached to this key last appear" for exactly the rows the
    roster feed left blank.

    Provenance stays distinguishable rather than fused:
      * a roster-fed list is returned untouched, with NO source marker;
      * a derived list is stamped `mlb_seasons_source = "career_war"` so any
        consumer can tell the two apart (and so an audit can count them).
    A non-empty roster-fed value is NEVER overwritten - this only fills holes.

    Returns the input dict itself when there is nothing to add (no copy, so the
    common path costs one dict lookup on a ~2,700-row export)."""
    if not isinstance(rs, dict):
        return {}
    if rs.get("mlb_seasons"):
        return rs
    seasons_map = (cw or {}).get("seasons")
    if not isinstance(seasons_map, dict) or not seasons_map:
        return rs
    years: list[int] = []
    for y in seasons_map:
        try:
            yi = int(y)
        except (TypeError, ValueError):
            continue
        # Guard against a junk key ("career", "total") reaching the season list.
        if 1870 <= yi <= date.today().year + 1:
            years.append(yi)
    if not years:
        return rs
    out = dict(rs)
    out["mlb_seasons"] = sorted(set(years))
    out["mlb_seasons_source"] = "career_war"
    return out


def authoritative_org_map(
    keys: set[str] | None = None,
) -> dict[str, tuple[str, str]]:
    """player_key -> (canonical_org, event_date) from MLB's OWN transaction feed.

    WHY THIS EXISTS (2026-08-05, owner-reported: Alexander Frias shown as a
    Brewers prospect days after St. Louis traded for him).

    `consensus._latest_meta` resolves org as "the org on the newest snapshot
    that carries one", and its comment states the assumption plainly: "no
    source has a meaningful claim to be more authoritative on org/name." That
    is true among the SCOUTING sources, and false against MLB itself. A
    prospect list's org is a byproduct of which page a player was printed on,
    and those lists are refreshed on their publisher's schedule, not the
    transaction wire. So for the day or three after a trade, the losing club's
    Top-30 page still carries the player, and because it is scraped fresh it
    outranks the correct org and re-stamps it.

    Frias is the worked example: MLB's feed carried the trade on 2026-08-03
    ("St. Louis Cardinals traded RHP Dustin May and LHP JoJo Romero to
    Milwaukee Brewers for OF Alexander Frias and OF Josiah Ragsdale"), he was
    assigned to Palm Beach (STL) the same day and activated there on 08-05 -
    while our newest snapshot was MLB Pipeline's 08-04 *Brewers* Top 30, which
    had not dropped him yet. Measured blast radius at the time of the fix: 178
    players whose latest inferred trade contradicted their latest authoritative
    one.

    The rule is deliberately conservative, and only ever moves a player TOWARD
    MLB's record: take the newest transaction whose destination resolves to a
    parent club, and let the caller apply it only when that event is NEWER than
    every snapshot it would override. Affiliates whose nickname does not carry
    the parent's (Somerset Patriots, Wilson Warbirds) do not resolve and are
    skipped rather than guessed at, so a player who cannot be placed keeps the
    scouting org rather than acquiring a wrong one.
    """
    import json as _json
    from trades import ORG_ALIASES as _ALIASES
    from trades import canonical_org as _canon
    # The 30 parent clubs. The feed also carries national-team events (a WBC
    # roster resolves to "Cuba", four characters, so the length guard below let
    # it through) and those are not a club: five players were placed on "Cuba".
    _clubs = frozenset(_ALIASES.values())

    out: dict[str, tuple[str, str]] = {}
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, payload_json FROM player_transactions"
            ).fetchall()
    except sqlite3.OperationalError:
        return out          # table absent on a fresh DB; nothing to reconcile

    for player_key, payload in rows:
        if keys is not None and player_key not in keys:
            continue
        try:
            events = _json.loads(payload) or []
        except (TypeError, ValueError):
            continue
        best: tuple[str, str] | None = None      # (date, org)
        for ev in events:
            when = (ev.get("date") or "").strip()
            if not when:
                continue
            # A trade names both MLB clubs outright, so it is the cleanest
            # signal; assignments/status changes name the affiliate, which
            # resolves only when it carries the parent's nickname.
            org = _canon(ev.get("to_team_name"))
            if not org or org not in _clubs:
                continue                          # unresolvable affiliate / not a club
            if best is None or when >= best[0]:
                best = (when, org)
        if best is not None:
            out[player_key] = (best[1], best[0])
    return out


def authoritative_org_by_mlbam() -> dict[int, tuple[str, str]]:
    """mlbam id -> (canonical_org, event_date), same source as
    authoritative_org_map but keyed for the MLB leaderboards, which join on
    mlbam rather than on our player_key slug."""
    by_key = authoritative_org_map()
    if not by_key:
        return {}
    out: dict[int, tuple[str, str]] = {}
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT mlbam_id, player_key FROM player_photos "
                "WHERE mlbam_id IS NOT NULL AND player_key IS NOT NULL"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    for mlbam, key in rows:
        rec = by_key.get(key)
        if rec:
            try:
                out[int(mlbam)] = rec
            except (TypeError, ValueError):
                continue
    return out


def _atomic_replace(tmp: Path, path: Path, *, timeout: float = 30.0,
                    delay: float = 0.01, max_delay: float = 0.25) -> None:
    """os.replace(tmp, path), retried against the Windows open-file case until
    a deadline.

    POSIX rename replaces an open target happily. WINDOWS DOES NOT: if any
    reader has the target open, MoveFileEx fails with PermissionError
    (WinError 5), and a naive atomic write therefore RAISES exactly where the
    old in-place write used to succeed. That would trade a rare corruption for
    a routine export failure, which is a worse deal. Found by
    test_atomic_artifact_write's concurrent-reader test on the first run of the
    fix, which is the entire reason that test drives real writes instead of
    asserting on the source.

    WHY THIS IS A DEADLINE AND NOT AN ATTEMPT COUNT. The first version was 50
    attempts at a flat 50ms and its docstring reasoned that "readers hold a file
    only for the length of one read, so a short retry covers it". That reasoning
    is wrong under load and the full suite proved it: the same concurrent-reader
    test that passed alone exhausted all 2.5s on a busy box and raised. The
    quantity that matters is not how long ONE read takes, it is whether reads
    ever stop overlapping, and on a file being polled continuously they may not
    for a while. 30 seconds of patience against an export that already took
    minutes is cheap; a failed nightly is not.

    The backoff starts at 10ms and grows to 250ms rather than sitting at a flat
    50ms, so a brief collision is resolved almost immediately while a long one
    stops spinning the CPU.

    On expiry it RAISES rather than falling back to an in-place write. That is
    deliberate and it is the whole point: an in-place fallback would reintroduce
    the truncation under precisely the conditions that cause it. A loud export
    failure leaves the previous good artifact in place and is recoverable on the
    next run. A truncated 74MB file served to readers is not."""
    import time
    deadline = time.monotonic() + timeout
    wait, tries = delay, 0
    while True:
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            tries += 1
            if time.monotonic() >= deadline:
                raise PermissionError(
                    f"could not atomically replace {path.name} after {tries} "
                    f"attempts over {timeout:.0f}s: a reader has held it open "
                    f"the whole time. The previous file is intact and was NOT "
                    f"overwritten; rerun the export.") from None
            time.sleep(wait)
            wait = min(wait * 1.6, max_delay)


# ---------------------------------------------------------------------------
# Export-time Statcast contact-quality percentiles. Module-level (not closures
# of export_timeseries_json) so test_export_percentile_peers.py can pin the
# normalizer against its recorded cohort; the zone twin keeps its constants
# inside the export and shares the two rank helpers.
# ---------------------------------------------------------------------------

_STATCAST_CONTACT_MIN_BBE = 10
_STATCAST_HITTER_CONTACT_PERCENTILE_METRICS = {
    "xwoba_est": True,
    "xwobacon_est": True,
    "avg_ev": True,
    "p90_ev": True,
    "max_ev": True,
    "hard_hit_pct": True,
    "barrel_pct": True,
    "pull_air_pct": True,
}
_STATCAST_PITCHER_CONTACT_PERCENTILE_METRICS = {
    "xwoba_est": False,
    "xwobacon_est": False,
    "avg_ev": False,
    "p90_ev": False,
    "max_ev": False,
    "hard_hit_pct": False,
    "barrel_pct": False,
}


def _export_num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _sorted_peers(values: list[float]) -> list[float] | None:
    """A sorted copy of a cohort's peer values for _percentile_rank_100, or None
    when a NaN is among them (its order is undefined, so the linear count stays
    the source of truth for that cohort)."""
    if any(v != v for v in values):
        return None
    return sorted(values)


def _percentile_rank_100(value: float, values: list[float], higher_is_better: bool,
                         sorted_values: list[float] | None = None) -> float:
    """Share of peers at or below the value (higher is better) or at or above it,
    in percent to one decimal. With `sorted_values` (from _sorted_peers) the count
    comes from bisect instead of a pass over the list: bisect_right counts the
    peers <= value and n - bisect_left the peers >= value, the same integers the
    pass produced, so the same rounded number."""
    n = len(values)
    if not n:
        return 0.0
    if sorted_values is not None and value == value:
        if higher_is_better:
            count = bisect.bisect_right(sorted_values, value)
        else:
            count = n - bisect.bisect_left(sorted_values, value)
    elif higher_is_better:
        count = sum(1 for v in values if v <= value)
    else:
        count = sum(1 for v in values if v >= value)
    return round(100.0 * count / n, 1)


def _statcast_contact_metric(cq: dict, metric: str) -> float | None:
    if metric == "pull_air_pct":
        return _export_num((cq.get("spray") or {}).get("pull_air_pct"))
    return _export_num(cq.get(metric))


def _shallow_statcast_payload(payload):
    """A statcast payload whose containers the export writes into are fresh: the
    payload dict, its contact_quality dict, the level_splits list, each split dict
    and its contact_quality dict. Everything else (pitch_plot, pitch_movement,
    hit_locations, recent_games, spray ...) is shared with the input by reference.
    The export only ever reassigns keys on those containers (percentiles, the
    xwOBA PA adjustment, the pitch_plot and hit_locations strip), so the input is
    never written. This replaces copy.deepcopy, which walked 1.46 GB of pitch
    coordinates on every export to protect a few dicts."""
    if not isinstance(payload, dict):
        return copy.deepcopy(payload)
    out = dict(payload)
    cq = out.get("contact_quality")
    if isinstance(cq, dict):
        out["contact_quality"] = dict(cq)
    splits = out.get("level_splits")
    if isinstance(splits, list):
        fresh = []
        for row in splits:
            if isinstance(row, dict):
                row = dict(row)
                rcq = row.get("contact_quality")
                if isinstance(rcq, dict):
                    row["contact_quality"] = dict(rcq)
            fresh.append(row)
        out["level_splits"] = fresh
    return out


def _normalize_statcast_contact_percentiles_for_export(scm_by_key: dict[str, dict]) -> dict[str, dict]:
    """Attach level/side contact-quality percentiles from stored rows.

    This is export-only and uses already-fetched Statcast contact_quality
    payloads, so it does not require another MLB API pass. Returns new payloads
    built by _shallow_statcast_payload (the input is never written). The peer
    list of each (level, side, metric) cohort is built once rather than once per
    row, and ranked by bisect; test_export_percentile_peers.py pins this equal
    to the deepcopy and row-loop version on a recorded cohort.
    """
    out = {key: _shallow_statcast_payload(payload) for key, payload in (scm_by_key or {}).items()}
    rows_by_level_side: dict[tuple[str, bool], list[dict]] = {}
    seen: set[tuple[str, str, bool]] = set()
    for key, payload in out.items():
        if not isinstance(payload, dict):
            continue
        rows = payload.get("level_splits") or [payload]
        for row in rows:
            if not isinstance(row, dict):
                continue
            level = row.get("level")
            if not level:
                continue
            is_pitcher = bool(row.get("is_pitcher"))
            dedupe_key = (key, level, is_pitcher)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            cq = row.get("contact_quality") or {}
            bbe = int(cq.get("batted_balls") or 0)
            cq["qualified"] = bool(bbe >= _STATCAST_CONTACT_MIN_BBE)
            cq["qualifier_min_bbe"] = _STATCAST_CONTACT_MIN_BBE
            cq["percentile_sample_size"] = None
            cq["percentiles"] = {}
            if cq["qualified"]:
                rows_by_level_side.setdefault((level, is_pitcher), []).append(row)

    for (_level, is_pitcher), level_rows in rows_by_level_side.items():
        metric_directions = (
            _STATCAST_PITCHER_CONTACT_PERCENTILE_METRICS
            if is_pitcher else _STATCAST_HITTER_CONTACT_PERCENTILE_METRICS
        )
        n = len(level_rows)
        # The peer list depends on (cohort, metric) only, never on the row being
        # ranked, so it is built once per cohort instead of once per row.
        peers: dict[str, tuple[list[float], list[float] | None]] = {}
        for metric in metric_directions:
            vals = [v for v in (_statcast_contact_metric(peer.get("contact_quality") or {}, metric)
                                for peer in level_rows) if v is not None]
            peers[metric] = (vals, _sorted_peers(vals))
        for row in level_rows:
            cq = row.get("contact_quality") or {}
            cq["percentile_sample_size"] = n
            for metric, higher_is_better in metric_directions.items():
                value = _statcast_contact_metric(cq, metric)
                if value is None:
                    continue
                vals, sorted_vals = peers[metric]
                if len(vals) < 5:
                    continue
                cq["percentiles"][metric] = _percentile_rank_100(value, vals, higher_is_better, sorted_vals)

    for payload in out.values():
        if not isinstance(payload, dict):
            continue
        split_map = {
            (row.get("level"), bool(row.get("is_pitcher"))): row
            for row in payload.get("level_splits") or []
            if isinstance(row, dict)
        }
        own_key = (payload.get("level"), bool(payload.get("is_pitcher")))
        normalized_primary = split_map.get(own_key)
        if normalized_primary:
            # The top-level block mirrors its primary split; its own dict and its
            # own percentiles dict, the rest by reference.
            primary_cq = dict(normalized_primary.get("contact_quality") or {})
            if isinstance(primary_cq.get("percentiles"), dict):
                primary_cq["percentiles"] = dict(primary_cq["percentiles"])
            payload["contact_quality"] = primary_cq
    return out


# --------------------------------------------------------------------------- #
# PROSPX pitch rates: P/PA (hitters), P/IP and P/BF (pitchers) and PAR against the
# same level and season (owner ask 19 of 2026-09-30; plan Part 8, lane design
# pitch_metrics.md section 5.4). Every number comes from pitch_rates, the one
# definition: the rate from pitch_rates.player_lines joined on (mlbam, season,
# level), the anchor from pitch_rates.league_rates for the same level-season (and,
# for a pitcher, his majority role there, the rate and the anchor both from that
# role's line). A DISPLAY index: no eFV, ETA or value input reads these keys.
#
# Written only while pitch_rates.SERVE_PITCH_RATES is True; off, nothing is added
# and the statline passes through as the very same object, so every file is
# byte-identical. On, the headline statline carries the keys in the boot file and
# the career rows' keys ride the player_detail shard (the boot budget). A row in a
# usable level-season at or above the display floor gets the rate keys; every
# other row gets par_basis alone (untracked, partial, below_floor, no_line), so a
# consumer prints a blank with its reason and never a rate the feed did not log.
# --------------------------------------------------------------------------- #
PITCH_RATE_MIN_PA = 50      # hitter rows: PA on the joined line
PITCH_RATE_MIN_OUTS = 30    # pitcher rows: outs on the joined role line (10 innings)


def make_pitch_rate_lookup():
    """(season, level) -> (league_rates, player_lines) or None, cache-only (no
    network) and memoized for one export. None when the flag is off."""
    import pitch_rates as _pr
    if not _pr.SERVE_PITCH_RATES:
        return None
    memo: dict = {}

    def lookup(season, level):
        try:
            key = (int(season), str(level or ""))
        except (TypeError, ValueError):
            return None
        if key not in memo:
            try:
                memo[key] = (_pr.league_rates(key[1], key[0], fetch=False),
                             _pr.player_lines(key[0], key[1], fetch=False))
            except Exception:                                # noqa: BLE001
                log.exception("pitch rates: lookup failed for %s %s", key[1], key[0])
                memo[key] = None
        return memo[key]
    return lookup


def pitch_rate_fields(row: dict, mlbam, lookup) -> dict:
    """The pitch-rate keys for one career row or statline (see the block above)."""
    import pitch_rates as _pr
    got = lookup(row.get("season"), row.get("level")) if lookup else None
    if not got:
        return {"par_basis": "untracked"}
    lr, lines = got
    is_p = bool(row.get("is_pitcher"))
    status = lr.get("pitching_status") if is_p else lr.get("tracking")
    if status != "usable":
        return {"par_basis": status if status in ("partial", "untracked") else "untracked"}
    try:
        line = (lines or {}).get(int(mlbam)) if mlbam is not None else None
    except (TypeError, ValueError):
        line = None
    if not is_p:
        h = (line or {}).get("hit") or {}
        rate, anchor = h.get("p_pa"), (lr.get("hit") or {}).get("p_pa")
        if rate is None or anchor is None:
            return {"par_basis": "no_line"}
        pa = int(h.get("pa") or 0)
        if pa < PITCH_RATE_MIN_PA:
            return {"par_basis": "below_floor"}
        return {"p_pa": round(rate, 3), "par": _pr.par(rate, anchor),
                "par_anchor": round(anchor, 3), "par_basis": "season_line", "par_n": pa}
    pit = (line or {}).get("pit") or {}
    role, basis = pit.get("role"), pit.get("basis")
    if basis == _pr.BASIS_ROLE:
        src = pit.get("sp" if role == "SP" else "rp") or {}
    else:
        src = pit.get("season_line") or {}
    rate = pit.get("p_ip")
    anchor = (lr.get("sp" if role == "SP" else "rp") or {}).get("p_ip")
    if rate is None or anchor is None or role not in ("SP", "RP"):
        return {"par_basis": "no_line"}
    outs = int(src.get("outs") or 0)
    if outs < PITCH_RATE_MIN_OUTS:
        return {"par_basis": "below_floor"}
    out = {"p_ip": round(rate, 2)}
    if pit.get("p_bf") is not None:
        out["p_bf"] = round(pit["p_bf"], 2)
    out.update({"par": _pr.par(rate, anchor), "par_anchor": round(anchor, 2),
                "par_basis": basis, "par_role": role, "par_n": outs})
    return out


def career_pitch_rate_shard(rows, mlbam, lookup) -> list:
    """One {season, level, ...keys} entry per career row, in row order, for the
    player_detail shard (the card merges it onto the row with the same season
    and level). [] while the flag is off (lookup None) or without rows."""
    if lookup is None or not rows:
        return []
    return [{"season": r.get("season"), "level": r.get("level"),
             **pitch_rate_fields(r, mlbam, lookup)}
            for r in rows if isinstance(r, dict)]


def attach_pitch_rate_statline(sl, mlbam, lookup):
    """The headline statline with its row's keys (par_n aside, which only the
    card's by-level pooling reads). lookup None returns `sl` itself."""
    if lookup is None or not isinstance(sl, dict) or not sl.get("level"):
        return sl
    keys = pitch_rate_fields(sl, mlbam or sl.get("mlbam_id"), lookup)
    keys.pop("par_n", None)
    return {**sl, **keys}


def export_timeseries_json(timeseries: list[PlayerTimeseries], out_path: Path,
                          statlines: dict[str, dict] | None = None,
                          pitch_arsenals: dict[str, dict] | None = None,
                          zone_metrics: dict[str, dict] | None = None,
                          statcast_metrics: dict[str, dict] | None = None,
                          sabermetrics: dict[str, dict] | None = None,
                          trades_by_player: dict[str, list[dict]] | None = None,
                          transactions_by_player: dict[str, list[dict]] | None = None,
                          career_stats: dict[str, list[dict]] | None = None,
                          career_war: dict[str, dict] | None = None,
                          acquisitions: dict[str, dict] | None = None,
                          il_status: dict[str, dict] | None = None,
                          rosters_by_org: dict[str, dict[str, list[dict]]] | None = None,
                          level_changes: dict[str, list[dict]] | None = None,
                          roster_status: dict[str, dict] | None = None,
                          ifa_spending_by_org: dict[str, dict[int, dict]] | None = None,
                          contracts_by_key: dict[str, dict] | None = None,
                          draft_pools: dict | None = None,
                          player_ids: dict[str, int] | None = None,
                          top_n_active: int | None = None,
                          intermediate: bool = False):
    """
    Serialize for the front-end widget.

    `intermediate=True` is passed ONLY by run_monthly.main() step 5 (the
    mid-monthly export): it writes boot + debuts.json + rosters_by_org.json
    and skips every frontend-only sidecar (debuts_lite, inactive,
    scout_reports + chunks, mlb_trade_players, and the pitch_plots/,
    player_detail/, debuts_full/ per-player dirs), because the chained
    daily's d9 full export rewrites all of them minutes later. Daily, d9,
    and rebuild paths must always run the full (default) export.

    Each player now carries:
      - statline      : slash line / ERA at the highest level this season
      - pitch_arsenal : pitch mix and velo for pitchers (may be None)
      - sabermetrics  : wRC+ / wOBA (hitters), xFIP / FIP / FIP- / ERA-
                        (pitchers). MLB-only coverage from the MLB Stats
                        API sabermetrics endpoint; None for prospects who
                        have not yet appeared in the majors. The UI falls
                        back to OPS+ (vs level) and ERA- (vs level) — the
                        `ops_plus_level` / `era_minus_level` fields on
                        `statline` — when sabermetrics aren't available.
      - trades        : list of trade events
      - career_stats  : year-by-year stats (most recent first), capped at
                        CAREER_SEASONS_KEPT and collapsed to highest level
                        per season. Drives the prospect detail page.
      - birth_date + age + age_vs_level
    """
    # PERF_9 (2026-10-03): phase timers. Log lines only, so the daily step table's
    # one d9 row can be broken down to the stretch of this export that costs the
    # time; nothing here reaches the payload or any file this function writes.
    import time as _time_phase
    _phase_t0 = _phase_last = _time_phase.monotonic()

    def _phase_done(label: str) -> None:
        nonlocal _phase_last
        _now = _time_phase.monotonic()
        log.info("export phase %s: %.1fs (%.1fs into the export)",
                 label, _now - _phase_last, _now - _phase_t0)
        _phase_last = _now

    statlines = statlines or {}
    pitch_arsenals = pitch_arsenals or {}
    zone_metrics = zone_metrics or {}
    statcast_metrics = statcast_metrics or {}
    sabermetrics = sabermetrics or {}
    trades_by_player = trades_by_player or {}
    transactions_by_player = transactions_by_player or {}
    career_stats = career_stats or {}
    # Pitch rates on the served career rows and statline (None while
    # pitch_rates.SERVE_PITCH_RATES is False: the rows pass through untouched).
    _pitch_rate_lookup = make_pitch_rate_lookup()
    career_war = career_war or {}
    acquisitions = acquisitions or {}
    il_status = il_status or {}
    rosters_by_org = rosters_by_org or {}
    level_changes = level_changes or {}
    roster_status = roster_status or {}
    ifa_spending_by_org = ifa_spending_by_org or {}
    contracts_by_key = dict(contracts_by_key or {})
    source_events_by_key = load_source_events()
    player_news_by_key = load_player_news()

    # ── OBSERVED position (2026-07-30, owner decision). The served `position` string comes
    # from consensus._latest_meta, which prefers FanGraphs because FG FORWARD-PROJECTS where
    # a prospect ends up rather than reporting today's roster slot. That stays: measured over
    # 1,957 comparable rows, FG projects a move DOWN the defensive spectrum 318 times against
    # 184 up (24.3% hard disagreement, 1.73:1 skew), so repointing `position` would hand 318
    # players a premium-position label the industry says they will not hold - and the
    # positional scarcity dollars, the org depth chart and the farm positional need all price
    # exactly that. This is the SECOND field: what he has actually been playing in the minors,
    # most games at a non-DH position, from data/positions_played.json.
    #
    # It is a MiLB observation, not a display position, and it is DELIBERATELY absent rather
    # than guessed: fielding_positions.load_observed_positions omits any player whose census is
    # empty, all-DH, or under the shipped versa exposure floor, and pitchers are absent by
    # construction. Coverage on the current build: 1,956 of 2,104 served non-pitcher rows.
    # Graduates carry a FROZEN pre-debut census (the builder filters to players with no
    # debut_date), which is why nothing downstream of a debut reads this.
    try:
        from fielding_positions import load_observed_positions as _load_obs_pos
        _observed_pos = _load_obs_pos(Path(__file__).parent / "data" / "positions_played.json")
    except Exception:
        log.debug("export: observed-position sidecar unavailable", exc_info=True)
        _observed_pos = {}

    _phase_done("inputs")
    # ── eFV join (one-run lag): the site's PRIMARY grade replaces consensus FV across the
    # farm / DvM+ / movement metrics. Loaded once here so every consumer below (the per-player
    # movement `stock`, the $DvM+ pre-pass, the org dev-FV history) reads one consistent value.
    # See _load_xfv_join for the one-run-lag rationale. Closures fall back to consensus FV
    # wherever eFV abstains, so nothing goes null.
    _xfv_by_key, _xfv_hist_by_key = _load_xfv_join()
    # Is the eFV series on disk on the basis the board is serving? Resolved ONCE (it reads
    # a file and a fingerprint) and consumed by the movement override below. False across a
    # grade-scale transition, which is the one-run suppression window.
    _xfv_hist_ok = xfv_history_is_on_board_basis()
    if not _xfv_hist_ok:
        log.warning("eFV history basis %r != board basis %r - eFV-delta movement suppressed "
                    "for this run; movement falls back to the consensus same-source step",
                    xfv_history_basis(), board_basis_fingerprint())

    # W-SIDESCALE: the board grade SCALE lives in efv_board_scale, resolved once here
    # (not per player) so _board_grade stays a cheap closure. Falls back to reading
    # BOARD_GRADE_FIELD straight off the record if the module is unavailable.
    try:
        from efv_board_scale import board_value as _board_scale_value
    except Exception:                                       # pragma: no cover
        def _board_scale_value(rec):
            return (rec or {}).get(BOARD_GRADE_FIELD)

    # Per-player overall board-RANK history (metric_snapshots). Drives the
    # de-noised rank_movement chip (movement.compute_rank_movement). overall_rank
    # is computed below (after the _active_key sort), so the closure appends
    # today's rank at serialize time; reads flat until rank history accrues.
    _rank_hist_by_key = load_rank_history()
    _today_iso = date.today().isoformat()

    # Provisional (source-ungraded) prospects grouped by org -- folded into the farm
    # top-end/depth ranking pool below (one-run lag). Filler ranks out; breakouts add
    # bounded depth. NOT added to any raw-sum / DvM+ / surplus accumulator.
    _prov_by_org = _load_ungraded_by_org()

    # A player whose exact board grade is shared with more than this many others is
    # ranked by the TIEBREAK chain, not by his grade. movement.compute_rank_movement's
    # 25-spot dead-band was sized for neighbour re-grade churn on a board with few ties;
    # it cannot absorb a 3,100-player block, where a 0.1 grade nudge vaults a player
    # thousands of spots. Rank movement is withheld for those players rather than
    # published as a marquee move that no grade change supports.
    _RANK_TIE_BLOCK_MAX = RANK_TIE_BLOCK_MAX
    _board_grade_tie_count: dict[float, int] = {}

    def _rank_meaningful(grade) -> bool:
        """False when the player sits inside a deep tie block (see _RANK_TIE_BLOCK_MAX),
        i.e. his rank NUMBER carries no grade information."""
        if grade is None:
            return True
        return _board_grade_tie_count.get(float(grade), 0) <= _RANK_TIE_BLOCK_MAX

    def _rank_movement(pk, today_rank, grade=None):
        if not _rank_meaningful(grade):
            return None
        from movement import compute_rank_movement
        hist = list(_rank_hist_by_key.get(pk) or [])
        if today_rank is not None:
            hist = [h for h in hist if h.get("snapshot_date") != _today_iso]
            hist.append({"snapshot_date": _today_iso, "rank": int(today_rank)})
        if len(hist) < 2:
            return None
        mv = compute_rank_movement(hist)
        return mv if mv.get("basis") == "rank_step" else None

    def _board_grade(pk, cons):
        """THE board number for a player_key: the eFV grade (BOARD_GRADE_FIELD) on the
        W-SIDESCALE board scale, with consensus FV as the fallback wherever eFV
        abstains so no-track-record players still place instead of vanishing.

        This ONE function is the board's display value, its sort key AND the basis of
        overall_rank / org_rank. It mirrors efvBoardValue() in prospx/index.html, so a
        baked rank and the live board order cannot drift apart. See BOARD_GRADE_FIELD
        at module scope for why a second resolution chain must never be added here.

        The scale itself is NOT defined here -- efv_board_scale.board_value owns it
        (per-side affine, order-preserving within side). Going through that call means
        this is correct whether or not data/xfv.json has been stamped yet: the module
        re-derives from `xfv_grade_model_raw` when present, so it cannot double-apply.
        If the module is unavailable, fall back to the field as written."""
        g = _board_scale_value(_xfv_by_key.get(pk) or {})
        if g is not None:
            return float(g)
        return float(cons) if cons is not None else None

    def _board_sort_key(pk):
        """ORDER-ONLY sub-decimal tiebreak INSIDE a board-grade tie block. Never a
        displayed number and never a grade.

        vf.outcome_implied_fv maps every non-positive predicted WAR to exactly the
        outcome curve's first knot, so the floor is one enormous exact-decimal tie
        (3,358 of 4,586 actives on the 2026-08-06 board) that the '+' / TBS / avg_rank
        chain then orders by proxies that carry no model information. board_sort_key is
        the model's own UNROUNDED PRE-CLAMP predicted WAR (efv_score, emitted per live
        row), so those rows can order by the model instead. Pre-clamp on purpose: the
        -2.0 guard would re-tie the largest block the key exists to break.

        MUST STAY IDENTICAL TO prospx fvCmpDesc's sort-key term. A key that only one of
        the two readers applies re-creates the rendered-order-vs-baked-rank divergence
        BOARD_GRADE_FIELD was introduced to prevent (three prior incidents). The missing
        value is a fixed sentinel rather than a skip so the Python tuple sort and the JS
        comparator agree by construction: a row with no key sorts LAST within its tie
        block on both sides. Measured 2026-08-07: zero actives lack an xfv.json active
        entry, so the sentinel branch is unreachable on the live board today and the two
        rules cannot disagree even in principle until that changes."""
        v = (_xfv_by_key.get(pk) or {}).get("board_sort_key")
        if v is None:
            return _NO_BOARD_SORT_KEY
        try:
            return float(v)
        except (TypeError, ValueError):
            return _NO_BOARD_SORT_KEY

    # Model-input alias. Farm score, $DvM+ and the movement `stock` have always read
    # the raw grade; now that the board reads the same field, they are the same call.
    # Kept as a name so those call sites stay self-documenting.
    _xg = _board_grade

    def _xsurplus(pk, cons_mm):
        """eFV expected surplus ($M); consensus-surplus fallback where eFV abstains.
        BASIS NOTE (bughunt F6, 2026-07-23): both legs are on the CALIBRATED engine
        basis (eFV surplus_mm prices through vf.apply_calibration at the efv_score
        seam; surplus_value_mm is calibrated by construction). Callers must pass a
        timing-aware fallback (age + the shared eta fallback) so a coverage gap
        cannot mix debut-now dollars into a timing-aware sum. Latent today: eFV
        covers every ts active, so the fallback leg never fires."""
        s = (_xfv_by_key.get(pk) or {}).get("surplus_mm")
        return float(s) if s is not None else cons_mm

    def _xfv_series(pk):
        """[(date, eFV grade)] from xfv_history for appreciation/movement; None when absent
        (callers then fall back to the consensus snapshot stream)."""
        h = _xfv_hist_by_key.get(pk)
        if not h or len(h) < 2:
            return None
        out = [(pt.get("d"), pt.get("x")) for pt in h if pt.get("d") and pt.get("x") is not None]
        return out if len(out) >= 2 else None

    # REMOVED 2026-07-25 (_xfv_at): the prior-rank re-sort it fed was a SECOND board
    # ordering (its own key: rounded prior grade -> tools -> IL -> avg_rank), so a player
    # whose grade never moved could still show a rank-delta arrow. It also read
    # xfv_history.x, which is the QUANTILE-scale series (efv_score.score_history maps
    # through the live grade map) and is therefore not comparable to the raw-grade board.
    # prev_overall_rank now comes from the player's OWN stored overall_rank at the previous
    # post-epoch snapshot, which is basis-consistent with the current rank by construction.

    # v17 — Merge in manual contract overrides from
    # data/contract_overrides.json. These take precedence over Spotrac
    # when both exist (Spotrac coverage lags for recent extensions). The
    # file is keyed by player_key and supports the same shape as the
    # Spotrac-derived dict plus an `extension_signed` ISO date.
    try:
        _overrides_path = Path(__file__).parent / "data" / "contract_overrides.json"
        if _overrides_path.exists():
            with open(_overrides_path, "r", encoding="utf-8") as _fh:
                _overrides = json.load(_fh) or {}
            for _ok, _ov in _overrides.items():
                if _ok.startswith("_"):  # skip _note metadata
                    continue
                if not isinstance(_ov, dict):
                    continue
                # Merge over the Spotrac entry (or seed if absent).
                base = dict(contracts_by_key.get(_ok) or {})
                base.update(_ov)
                base.setdefault("source", "manual")
                contracts_by_key[_ok] = base
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        # Silently no-op if the override file is missing or unparseable —
        # Spotrac coverage remains the fallback.
        pass
    draft_pools = draft_pools or {}
    player_ids = player_ids or {}

    # LAST-RESORT id source: the durable player_photos binding.
    #
    # `player_ids` is the freshly-resolved {key: mlbam} map, but the
    # rebuild-only entry point passes {} (see run_monthly's rebuild path),
    # so on that run EVERY board row falls back to the statline's embedded
    # id - and a player with no current-season statline serves mlbam_id
    # null even when the DB has always known his id. That is how six placed,
    # identified prospects (jesus_flores, omar_calcurian, michael_braswell_
    # iii, neomar_urbina, carlos_gonzalez, michael_oliveto__sa3069256) were
    # published as unidentifiable rows. player_photos is the canonical
    # mlbam_id<->player_key table, so it is the correct floor.
    #
    # A key bound to TWO ids is AMBIGUOUS by definition (the C2 class in
    # identity_audit) and is deliberately excluded: guessing there is how
    # two humans get fused. Measured 2026-07-25: 15 of 4467 active rows
    # gain an id from this fallback, 2 of them excluded as ambiguous until
    # the double binding is repaired.
    _durable_ids_by_key: dict[str, int] = {}
    try:
        _multi: set[str] = set()
        for _mid_s, _pk in load_mlbam_player_keys().items():
            if not _pk:
                continue
            try:
                _mid = int(_mid_s)
            except (TypeError, ValueError):
                continue
            _prior = _durable_ids_by_key.get(_pk)
            if _prior is not None and _prior != _mid:
                _multi.add(_pk)
            _durable_ids_by_key[_pk] = _mid
        for _pk in _multi:
            _durable_ids_by_key.pop(_pk, None)
        if _multi:
            log.warning("export: %d player_key(s) bound to more than one mlbam "
                        "id in player_photos - excluded from the durable id "
                        "fallback (see identity_audit C2): %s",
                        len(_multi), ", ".join(sorted(_multi)[:10]))
    except Exception:
        log.debug("export: durable player_photos id map unavailable", exc_info=True)
        _durable_ids_by_key = {}

    # IDENTITY JOINS (X03-01, 2026-09-25). career_war and the Spotrac contracts are
    # keyed by name slug, so a slug two players share handed one of them the other's
    # WAR seasons and contract (jose_ramirez 802064, a CPX pitcher, served the CLE
    # third baseman's $20.8M and a 2014-2018 pitcher's WAR; the ATH Max Muncy served
    # the LAD Max Muncy's $10.0M). Each row is now bound to the mlbam id the row
    # serves (the same player_ids -> statline -> durable order as `mlbam_id` below);
    # the slug join stays only for a row with no id.
    _ids_for_identity: dict[str, int] = {}
    for _p_id in timeseries:
        _k_id = _p_id.player_key
        _m_id = (player_ids.get(_k_id)
                 or (statlines.get(_k_id) or {}).get("mlbam_id")
                 or _durable_ids_by_key.get(_k_id))
        if _m_id:
            try:
                _ids_for_identity[_k_id] = int(_m_id)
            except (TypeError, ValueError):
                pass
    if DEBUTED_SERVICE_TIME:
        # Service time on the same id the row serves (DEBUTED_SERVICE_TIME above).
        try:
            from service_time import overlay_roster_status, store_from_rows
            roster_status, _svc_receipt = overlay_roster_status(
                roster_status, _ids_for_identity,
                store_from_rows(load_player_transactions(), load_player_transactions_meta()))
            log.info("export: service time written %s", _svc_receipt)
        except Exception:
            log.exception("export: service time overlay failed, graduates price at service 0")
    career_war, _cw_screen = screen_career_war_to_ids(career_war, _ids_for_identity)
    _cw_foreign = _cw_screen.pop("foreign_by_key", {})
    log.info("export: career_war identity screen %s", _cw_screen)
    try:
        _rivals = []
        _proj_path = Path(__file__).parent / "data" / "mlb_projections.json"
        if _proj_path.exists():
            with open(_proj_path, encoding="utf-8") as _fh:
                for _v in (json.load(_fh).get("vets") or []):
                    if _v.get("key") and _v.get("mlbam"):
                        _rivals.append((str(_v["key"]).split("__")[0], _v["mlbam"],
                                        _v.get("team"), _pos_is_pitcher(_v.get("pos"))))
        def _side_of(_p):
            # The statline's is_pitcher is measured on the player's own id; the
            # consensus position can predate a conversion (Lucas Erceg reads 3B/1B).
            _sp = (statlines.get(_p.player_key) or {}).get("is_pitcher")
            return bool(_sp) if _sp is not None else _vf_is_pitcher_position(_p.position)
        _humans = {
            _p_id.player_key: (_ids_for_identity[_p_id.player_key],
                               _p_id.org if len(str(_p_id.org or "")) == 3 else None,
                               _side_of(_p_id))
            for _p_id in timeseries if _p_id.player_key in _ids_for_identity}
        _ct_by_id, _ct_receipt = resolve_contracts_to_ids(contracts_by_key, _humans, _rivals)
        for _k_id, _ct_id in _ct_by_id.items():
            if _ct_id is None:
                contracts_by_key.pop(_k_id, None)
            else:
                contracts_by_key[_k_id] = _ct_id
        log.info("export: contract identity join %s (%d rival veterans)",
                 _ct_receipt, len(_rivals))
    except Exception:
        log.warning("export: contract identity join failed; slug join kept", exc_info=True)

    # Measured MLB exposure on the career-WAR stints (owner decision 14c, 2026-09-11)
    # is read from the stored rows only (the identity screen above reads only which
    # seasons the war_daily cache holds for an id, never its PA / IP).
    # A table with no measured row means persist_career_war_exposure has not run on
    # this DB, so the 641 still gate on a season-implied load: say so, loudly.
    _xcen = _career_war_exposure_census(career_war)
    if _xcen["rows"] and not _xcen["complete"]:
        _xmsg = (f"no career_war row of {_xcen['rows']} carries measured MLB exposure; "
                 "run storage.persist_career_war_exposure() (decision 14c)")
        log.warning("export: %s", _xmsg)
        _file_ingest_if_pipeline("career_war_exposure", ok=False, n_rows=0, message=_xmsg)
    else:
        log.info("export: career_war measured exposure on %d of %d rows",
                 _xcen["complete"], _xcen["rows"])

    # Usage-based role correction (rule D, role_usage.py): a MIRP/SIRP
    # consensus label (FanGraphs forward-projection via
    # consensus._latest_meta) flips to SP when the player's
    # CURRENT-season MiLB usage is starter-shaped (GS-share >= 0.50,
    # IP/G >= 3.0, IP >= 20; stretched starters like Clemmey 19 G /
    # 19 GS / 87 IP flip, openers like 28 G / 5 GS / 32 IP stay).
    # Applied HERE rather than in consensus.build_timeseries because
    # this is the first seam where BOTH the finalized consensus label
    # and the player's mlbam id are in hand (Snapshot/PlayerTimeseries
    # never carry an mlbam; consensus.py cannot import storage). The
    # pre-pass mutates p.position before any consumer below reads it,
    # so the payload position, pitcher-vs-hitter valuation split, and
    # farm cohort math all see one consistent label. Cache-only read
    # (milb_history fetch=False): never networks, missing data no-ops.
    try:
        from role_usage import usage_position_override as _usage_pos_override
    except ImportError:
        _usage_pos_override = None
    if _usage_pos_override is not None:
        _usage_season = date.today().year
        for _p_ru in timeseries:
            if _p_ru.status == "debuted":
                # Graduates' labels come from depth-chart sources (see
                # _latest_meta); MiLB usage must not overwrite them.
                continue
            _ru_mlbam = player_ids.get(_p_ru.player_key)
            if _ru_mlbam is None:
                _ru_mlbam = (statlines.get(_p_ru.player_key) or {}).get("mlbam_id")
            if _ru_mlbam is None:
                continue
            _ru_pos = _usage_pos_override(_p_ru.position, _ru_mlbam, _usage_season)
            if _ru_pos != _p_ru.position:
                _p_ru.position = _ru_pos

    # ORG RECONCILIATION against MLB's own transaction feed. Same seam and same
    # reasoning as the position override above: consensus cannot do it (it has
    # no DB access, and storage imports consensus, not the other way round), so
    # the correction lands here, on the way out.
    # The guard is the whole design: an authoritative event only wins when it is
    # NEWER than every snapshot behind the current org. A stale prospect list
    # can therefore no longer re-stamp a traded player back onto the club that
    # traded him, while a genuinely fresher scouting org is still preferred over
    # an old transaction. See authoritative_org_map for the worked example.
    try:
        _auth_orgs = authoritative_org_map({p.player_key for p in timeseries})
    except Exception:                                   # never fail an export on it
        log.exception("authoritative org reconciliation failed; serving scraped orgs")
        _auth_orgs = {}
    _org_fixed = 0
    for _p_org in timeseries:
        _rec = _auth_orgs.get(_p_org.player_key)
        if not _rec:
            continue
        _new_org, _when = _rec
        if not _new_org or _new_org == _p_org.org:
            continue
        _newest_snap = max((pt.snapshot_date for pt in _p_org.points), default="")
        # >= not >, deliberately. Both sides are DAY-resolution, so a strict
        # comparison hands same-day ties to the scraped list, which is exactly
        # the case that produced the bug: MLB recorded the Frias trade and his
        # new-affiliate activation, a prospect list published the losing club on
        # one of those same dates, and the tie let the list win. Within a single
        # day MLB's own transaction record is the better authority, so ties go
        # to it. A genuinely fresher list still wins on a LATER date.
        if _when >= _newest_snap:
            _p_org.org = _new_org
            _org_fixed += 1
    if _org_fixed:
        log.info("org reconciliation: %d player(s) moved to the org MLB's "
                 "transaction feed reports", _org_fixed)

    birth_dates = load_birth_dates()
    from stats import compute_age_decimal
    from age_level import score_age_vs_level
    from eta import (estimate_eta, LEVEL_BIAS_ADJ as ETA_LEVEL_BIAS_ADJ,
                     FORTYMAN_ADJ as ETA_FORTYMAN_ADJ, apply_fg_blend,
                     fg_eta_year_from_per_source, live_floor_year)
    import eta as _eta_mod
    # MLB regular-season end for this year (StatsAPI /seasons, cached a week, disk
    # fallback). Past it, eta.estimate_eta rolls a current-year ETA to next year's
    # early window (census M01-05). Unknown -> None -> only Nov/Dec roll, as before.
    try:
        import fantasy_schedule as _fsched
        _eta_season_end = ((_fsched.regular_season_dates(date.today().year) or {})
                           .get("end"))
    except Exception:                                      # noqa: BLE001
        _eta_season_end = None
    from trades import canonical_org
    from level_norms import (
        compute_level_norms,
        age_baselines_from_norms,
        ops_norms_from_norms,
        era_norms_from_norms,
    )
    from stat_flags import compute_stat_flags, compute_tool_flags
    # ETOOLS_ALL_CALCS (owner decision EW3-30; docs/tools-2026-10/ETOOLS_ALL_CALCS.md):
    # the composites, the tool flags, the board tiebreak and the farm Tool Quality read
    # the SHOWN grades, the eTool where one passed and consensus otherwise, matched by
    # player key then by the id the row serves. Reloaded per export. Flag off
    # (etool_composite.ETOOLS_COMPOSITE_ON False): every record is None and every
    # number below is the consensus one, byte for byte.
    import etool_composite as _ETC
    _ETC.load_payload(refresh=True)

    def _etc_rec(player_key):
        return _ETC.etool_record(player_key, _ids_for_identity.get(player_key))

    _ZONE_PERCENTILE_MIN_PITCHES = 100
    _ZONE_HITTER_PERCENTILE_METRICS = {
        "zone_rate": True,
        "z_swing_pct": True,
        "o_swing_pct": False,
        "z_contact_pct": True,
        "o_contact_pct": True,
        "overall_contact_pct": True,
        "whiff_pct": False,
    }
    _ZONE_PITCHER_PERCENTILE_METRICS = {
        "zone_rate": True,
        "z_swing_pct": False,
        "o_swing_pct": True,
        "z_contact_pct": False,
        "o_contact_pct": False,
        "overall_contact_pct": False,
        "whiff_pct": True,
    }
    def _zone_num(v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def _normalize_zone_percentiles_for_export(zm_by_key: dict[str, dict]) -> dict[str, dict]:
        """Recompute zone percentiles from the full stored level cohort.

        Stored zone payloads carry embedded percentiles from the fetch batch.
        Promotion-only refreshes can make an old-level split compare against a
        tiny batch, e.g. one A-level promoted player. The export should always
        compare each level split against every qualified stored peer at that
        same level.
        """
        out = copy.deepcopy(zm_by_key or {})
        rows_by_level_side: dict[tuple[str, bool], list[dict]] = {}
        row_refs: list[dict] = []
        seen: set[tuple[str, str, bool]] = set()
        for key, payload in out.items():
            if not isinstance(payload, dict):
                continue
            rows = payload.get("level_splits") or [payload]
            for row in rows:
                if not isinstance(row, dict):
                    continue
                level = row.get("level")
                if not level:
                    continue
                is_pitcher = bool(row.get("is_pitcher"))
                dedupe_key = (key, level, is_pitcher)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                row_refs.append(row)
                row["qualified"] = bool((row.get("pitches") or 0) >= _ZONE_PERCENTILE_MIN_PITCHES)
                row["qualifier_min_pitches"] = _ZONE_PERCENTILE_MIN_PITCHES
                row["percentile_sample_size"] = None
                row["percentiles"] = {}
                if row["qualified"]:
                    rows_by_level_side.setdefault((level, is_pitcher), []).append(row)

        for (_level, is_pitcher), level_rows in rows_by_level_side.items():
            metric_directions = (
                _ZONE_PITCHER_PERCENTILE_METRICS
                if is_pitcher else _ZONE_HITTER_PERCENTILE_METRICS
            )
            n = len(level_rows)
            # Hoist the per-metric peer-value lists out of the row loop: `vals` depends only on
            # (level_rows, metric), not the current row, so building it once per cohort drops this
            # from O(rows^2 * metrics) to O(rows * metrics) (one _zone_num pass per peer per metric).
            vals_by_metric = {
                metric: [v for v in (_zone_num(r.get(metric)) for r in level_rows) if v is not None]
                for metric in metric_directions
            }
            sorted_by_metric = {metric: _sorted_peers(vals) for metric, vals in vals_by_metric.items()}
            for row in level_rows:
                row["qualified"] = True
                row["percentile_sample_size"] = n
                for metric, higher_is_better in metric_directions.items():
                    value = _zone_num(row.get(metric))
                    if value is None:
                        continue
                    row["percentiles"][metric] = _percentile_rank_100(
                        value, vals_by_metric[metric], higher_is_better, sorted_by_metric[metric])

        for payload in out.values():
            if not isinstance(payload, dict):
                continue
            split_map = {
                (row.get("level"), bool(row.get("is_pitcher"))): row
                for row in payload.get("level_splits") or []
                if isinstance(row, dict)
            }
            own_key = (payload.get("level"), bool(payload.get("is_pitcher")))
            normalized_primary = split_map.get(own_key)
            if normalized_primary:
                for field in (
                    "qualified",
                    "percentile_sample_size",
                    "qualifier_min_pitches",
                    "percentiles",
                ):
                    payload[field] = copy.deepcopy(normalized_primary.get(field))
        return out

    zone_metrics = _normalize_zone_percentiles_for_export(zone_metrics)

    def _num(v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def _pa_adjust_xwoba_from_rates(xwobacon: float | None, stat_row: dict | None) -> float | None:
        """Convert contact-only xwOBAcon to PA-level xwOBA when BB/K exist."""
        if xwobacon is None or not stat_row:
            return xwobacon
        bb_pct = _num(stat_row.get("bb_pct"))
        k_pct = _num(stat_row.get("k_pct"))
        if bb_pct is None or k_pct is None:
            return xwobacon
        bb_rate = max(0.0, min(0.45, bb_pct / 100.0))
        k_rate = max(0.0, min(0.55, k_pct / 100.0))
        bip_rate = max(0.0, min(1.0, 1.0 - bb_rate - k_rate))
        # 2023 unintentional BB weight was ~0.69; HBP is unavailable in
        # several MiLB statline rows, so leave it out instead of guessing.
        est = bb_rate * 0.69 + bip_rate * xwobacon
        return round(max(0.02, min(1.20, est)), 3)

    def _adjust_statcast_xwoba_for_export(scm: dict | None, sl: dict | None, season_rows: list[dict]) -> dict | None:
        if not scm:
            return scm
        out = _shallow_statcast_payload(scm)
        rows_by_level = {
            r.get("level"): r for r in (season_rows or [])
            if isinstance(r, dict) and r.get("level")
        }

        def _apply(block: dict | None, stat_row: dict | None) -> None:
            cq = (block or {}).get("contact_quality") or {}
            if not cq:
                return
            raw = _num(cq.get("xwobacon_est"))
            if raw is None:
                raw = _num(cq.get("xwoba_est"))
            if raw is None:
                return
            cq["xwobacon_est"] = round(raw, 3)
            cq["xwoba_est"] = _pa_adjust_xwoba_from_rates(raw, stat_row)
            if cq.get("xwoba_est") != cq.get("xwobacon_est"):
                cq["xwoba_model"] = "knn_ev_la_pa_adjusted"

        _apply(out, sl)
        for split in out.get("level_splits") or []:
            if not isinstance(split, dict):
                continue
            stat_row = rows_by_level.get(split.get("level")) or sl
            _apply(split, stat_row)
        return out

    statcast_metrics = _normalize_statcast_contact_percentiles_for_export(statcast_metrics)

    def _prefer_metric_current_level(metric: dict | None, current_level: str | None) -> dict | None:
        if not metric or not current_level:
            return metric
        splits = metric.get("level_splits") or []
        match = next(
            (row for row in splits
             if isinstance(row, dict) and row.get("level") == current_level),
            None,
        )
        if not match:
            return metric
        # Shallow on purpose: the promoted fields point at the split's own values, and
        # the statcast block is copied again by _adjust_statcast_xwoba_for_export
        # before anything writes into it; nothing downstream writes into a zone block.
        # The deep copy here walked every pitch_plot once per player.
        out = dict(metric)
        keep_splits = out.get("level_splits") or []
        out.update(match)
        out["level_splits"] = keep_splits
        return out

    # Empirical level baselines computed from the career_stats payload we
    # already have. age_baselines / ops_norms / era_norms feed into the
    # per-player ETA + age-vs-level calls below.
    level_norms = compute_level_norms(career_stats, birth_dates)
    age_baselines = age_baselines_from_norms(level_norms)
    ops_norms = ops_norms_from_norms(level_norms)
    era_norms = era_norms_from_norms(level_norms)

    PITCHER_POS_SET = {"RHP", "LHP", "SP", "RP", "MIRP", "SIRP"}

    graduate_mlb_org_by_key: dict[str, str] = {}
    for org_code, levels in rosters_by_org.items():
        for rec in levels.get("MLB", []) or []:
            key = rec.get("player_key")
            if key:
                graduate_mlb_org_by_key[key] = org_code

    roster_org_by_key: dict[str, str] = {}
    roster_level_by_key: dict[str, str] = {}
    for org_code, levels in rosters_by_org.items():
        for level_name, recs in levels.items():
            for rec in recs or []:
                key = rec.get("player_key")
                if key and key not in roster_org_by_key:
                    roster_org_by_key[key] = org_code
                if key and key not in roster_level_by_key:
                    roster_level_by_key[key] = level_name

    # THE FOURTH PRECEDENCE LAYER (2026-08-05). The org reconciliation above
    # corrects `p.org`, and _active_display_org's trade branch now prefers MLB's
    # own record over an inferred one, but BOTH are overridden by this roster map
    # in the resolver's final fallback: `roster_org_by_key.get(key) or p.org`.
    # rosters_by_org is itself a build artifact, so a player whose roster entry
    # predates his trade keeps the old club no matter how many upstream layers
    # were fixed. That is why 5 players survived every earlier fix: their
    # snapshots are old enough that the 365-day trade window excludes them, so
    # the resolver falls all the way through to here.
    # Applying the SAME authority here keeps one answer across all four layers
    # rather than leaving the last one to contradict the other three. Only moves
    # a player when MLB's feed names a different club, never invents one.
    _roster_fixed = 0
    for _k, _rec in (_auth_orgs or {}).items():
        _new = _rec[0] if _rec else None
        if _new and roster_org_by_key.get(_k) and roster_org_by_key[_k] != _new:
            roster_org_by_key[_k] = _new
            _roster_fixed += 1
    if _roster_fixed:
        log.info("org reconciliation: corrected %d roster-map entr%s that would "
                 "otherwise have overridden the reconciled org",
                 _roster_fixed, "y" if _roster_fixed == 1 else "ies")

    # Per-org promotion-phase tendency: NOT computed for the served ETA since
    # 2026-09-30. The one registered look of docs/eta-2026-09-25/ETA_FG_BLEND_GATE.md
    # (section 7, data/eta_eval.json org_timing_gate_2026_09_25) found the KEEP and
    # REMOVE arms give the same debut year on all 1,394 rows, verdict REMOVE, and the
    # owner answered REMOVE (ETA-3). estimate_eta's served call below passes
    # org_promotion_tendency=None. eta.org_promotion_tendencies stays for the gate lab;
    # the Org Tendencies page computes its own display in org_tendencies.py.

    def _derived_graduation_date(p: PlayerTimeseries) -> str | None:
        """The debut date alone; see _derived_graduation_date_with_basis."""
        return _derived_graduation_date_with_basis(p)[0]

    def _derived_graduation_date_with_basis(
            p: PlayerTimeseries) -> tuple[str | None, str | None]:
        """
        Resolve a player's debut date (formerly "graduation_date") and the
        basis it rests on (DS-12, bug B7 in docs/efv-v2/DRIVER_SYSTEM_V2.md).
        A basis in PLACEHOLDER_DEBUT_BASES is a synthesized day, not a game
        date: the export flags it `debut_date_is_placeholder` so no consumer
        that reads the DAY (the eFV matrix input cutoff, a service-window
        arm) takes it for a debut.

        v24 — Restores the fallback chain that v21 ripped out (which
        had collapsed to mlb_debut_date-only and left 48 FG-flagged
        debuts with null debut_date). The cascade is anchored to
        "first MLB game" at every step — today() is NEVER used.

        Priority:
          1. roster_status.mlb_debut_date (with Nov/Dec Rule-5-
             protection-day rollforward to mid-season of the actual
             first MLB season — Chase DeLauter case)
          2. Earliest outright-transaction date (player off the 40-man
             cleared waivers; treated as a debut-equivalent per the
             v23 outright-→-debut rule)
          3. consensus.py's p.debut_date (the snapshot-date that
             triggered the FG "graduates" status flag — close enough
             to the actual debut for legacy grads)
          4. Earliest MLB-season Opening Day from career_stats
             ({earliest_mlb_season}-04-01)
          5. None — player should not be in the debuted bucket
        """
        rs = roster_status.get(p.player_key) or {}
        api_debut = rs.get("mlb_debut_date")
        rows = career_stats.get(p.player_key, []) or []
        mlb_years = sorted(
            int(r["season"]) for r in rows
            if r.get("level") == "MLB" and r.get("season")
        )

        # 1. Trust mlbDebutDate, with the Rule 5 protection rollforward.
        src = rs.get("mlb_debut_date_source") or "roster_status"
        if api_debut:
            try:
                api_d = date.fromisoformat(api_debut)
            except ValueError:
                return api_debut, src
            if (api_d.month >= 11
                    and mlb_years and mlb_years[0] > api_d.year):
                return (_safe_in_year_placeholder(p.player_key, mlb_years[0], rows),
                        "rule5_rollforward_placeholder")
            return api_debut, src

        # 2. Earliest outright transaction date.
        _tx_rows = (transactions_by_player or {}).get(p.player_key) or []
        _outrights = sorted([
            tx.get("date") for tx in _tx_rows
            if (tx.get("kind") or "").lower() == "outrighted"
            and tx.get("date")
        ])
        if _outrights:
            return _outrights[0], "outright"

        # 3. consensus.py's snapshot-derived debut_date (FG-flagged path).
        if getattr(p, "debut_date", None):
            return p.debut_date, "snapshot"

        # 4. Opening Day of the earliest MLB season we have on file.
        if mlb_years:
            return f"{min(mlb_years)}-04-01", "opening_day_placeholder"

        return None, None

    def _safe_in_year_placeholder(player_key: str, year: int,
                                  rows: list[dict]) -> str:
        """v14 — pick a graduation-date placeholder that NEVER lands in
        the future. The cycle-11 fix returned `{year}-07-01` for
        current-year debuts; that broke on May rebuilds (DeLauter
        showed July 1 as his grad date despite already debuting in
        April). Now we clamp the placeholder to TODAY when {year}-07-01
        would be in the future.

        Priority chain:
          1. Non-current year → `{year}-07-01` (mid-season anchor —
             always in the past for prior years).
          2. Current year + MLB activity + today >= {year}-07-01 →
             `{year}-07-01` (debut happened earlier this season,
             July-1 marker reads as "during the season" not "next
             month").
          3. Current year + MLB activity + today < {year}-07-01 →
             TODAY (the debut already happened recently; pinning to
             today is the safest non-future guess we can make).
          4. Current year + zero MLB activity → TODAY + warning (the
             player technically shouldn't be in this codepath; log so
             we surface the data inconsistency).
        """
        if year != date.today().year:
            return f"{year}-07-01"
        mlb_row = next(
            (r for r in rows
             if r.get("level") == "MLB" and r.get("season") == year),
            None,
        )
        today_iso = date.today().isoformat()
        midyear_iso = f"{year}-07-01"
        if mlb_row:
            try:
                pa = float(mlb_row.get("pa") or mlb_row.get("ab") or 0)
            except (TypeError, ValueError):
                pa = 0.0
            try:
                ip = float(mlb_row.get("ip") or 0)
            except (TypeError, ValueError):
                ip = 0.0
            if pa >= 1 or ip >= 0.1:
                # v14 — clamp to today when {year}-07-01 lands in the
                # future. Picks the EARLIER of mid-year and today, so
                # we never claim a graduate's debut date is tomorrow.
                return midyear_iso if midyear_iso <= today_iso else today_iso
        # v21 — Fallback when the current-year MLB row has zero PA/IP.
        # The user requested debut date NEVER fall back to today; use
        # the season's Opening Day approximation ({year}-04-01) instead
        # so the date at least lands inside the player's first MLB
        # season window rather than the rebuild timestamp.
        log.warning(
            "_safe_in_year_placeholder: %s using Opening Day %s "
            "(no PA/IP detected for %d MLB row); investigate API "
            "debut date.", player_key, f"{year}-04-01", year,
        )
        opening_day = f"{year}-04-01"
        return opening_day if opening_day <= today_iso else today_iso

    def _display_graduation_date(p: PlayerTimeseries) -> str | None:
        """
        v20 — Thin wrapper around _derived_graduation_date now that the
        chain has been collapsed to mlb_debut_date-only. Kept as a
        named hook so future display-side normalization (e.g.
        humanized "Sept 2023") has a single insertion point.
        """
        return _derived_graduation_date(p)

    def _display_graduation_basis(p: PlayerTimeseries) -> str | None:
        return _derived_graduation_date_with_basis(p)[1]

    # Org rebrand pairs that look like cross-org trades but aren't —
    # the Athletics dropped their "Oakland" prefix mid-2024, which made
    # every prospect's snapshots flip OAK↔ATH and the inferred path
    # registered a fake trade for each.
    _REBRAND_PAIRS = {
        ("OAK", "ATH"),
        ("ATH", "OAK"),
    }

    # Verbs that signal a real inter-org player movement. Trades, waiver
    # claims, contract purchases, Rule 5 selections and free-agent signings
    # all qualify. Description must contain at least one to count as
    # "verified". Without this check we'd accept the API's affiliate
    # assignments (e.g. "Toronto Blue Jays optioned RHP Thomas Hatch to
    # Buffalo Bisons.") whenever Toronto's parent-org name happened to
    # canonicalize cleanly — those are intra-org moves, not trades.
    _REAL_TRADE_VERB_PATTERNS = (
        "traded ",                     # X traded ... — definitive
        " off waivers",                # waiver claim ("claimed Y off waivers from X")
        " on waivers",                 # claimed/awarded on waivers (rarer wording)
        "purchased the contract",      # contract purchase between orgs
        "purchased contract",          # Rule 5 wording omits "the"
        "signed as a free agent",      # FA signing (cross-org by definition)
        "returned to ",                # Rule 5 return
    )
    # Verbs that signal a non-trade event. Reject these even when from/to
    # canonicalize to different MLB codes, because the "to" team is usually
    # an affiliate or the player's movement is intra-org.
    _NON_TRADE_VERB_PATTERNS = (
        "optioned",
        "recalled",
        "designated for assignment",
        "selected the contract",       # MiLB→MLB promotion (intra-org)
        "sent outright",
        "sent on a rehab",
        "sent on a development",
        "assigned to",                 # affiliate move
        "activated",
        "reinstated",
        "placed on the",
    )

    def _is_real_trade(t: dict) -> bool:
        """
        True only for VERIFIED inter-org trades.

        Strict rules:
          - source='inferred': always False. Inferred org-changes are
            kept in the DB as a fallback but never displayed; we only
            surface trades the MLB transactions API confirms.
          - source='mlb_api':
              * Both from_org and to_org must canonicalize to distinct
                3-letter MLB codes (filters out affiliate ↔ parent moves).
              * Reject the OAK ↔ ATH rebrand pair.
              * Description (when present) must contain a real-trade verb
                pattern AND not contain any non-trade verb pattern.
        """
        if t.get("source") != "mlb_api":
            return False
        cf = canonical_org(t.get("from_org"))
        ct = canonical_org(t.get("to_org"))
        if not (cf and ct and cf != ct and len(cf) == 3 and len(ct) == 3):
            return False
        if (cf, ct) in _REBRAND_PAIRS:
            return False
        desc = (t.get("description") or "").lower()
        if not desc:
            # No description — accept the cross-org movement on its face,
            # though this path is rare (API normally provides text).
            return True
        if any(v in desc for v in _NON_TRADE_VERB_PATTERNS):
            return False
        return any(v in desc for v in _REAL_TRADE_VERB_PATTERNS)

    def _trade_pref_score(t: dict) -> int:
        """Higher = preferred when collapsing duplicates. Prefer mlb_api
        rows with a description (richest record), then any mlb_api,
        then inferred."""
        if t.get("source") == "mlb_api":
            return 2 if (t.get("description") or "") else 1
        return 0

    def _filter_real_trades(trades: list[dict]) -> list[dict]:
        """
        Collapse duplicate trade records to one entry per real trade event.

        Rule 1: When an API trade exists for a (canonical_from,
                canonical_to) pair, it supersedes any inferred trade with
                the same pair. API records carry the precise transaction
                date plus a description; the inferred path is a fallback
                that can produce stale entries from older snapshot
                evolutions and shouldn't compete once the real record
                arrives. (A genuine re-trade between the same orgs within
                the same season is extremely rare for prospects.)

        Rule 2: API records with identical (date, canonical_from,
                canonical_to) collapse to the richest entry — the one
                with a description, falling back to the earliest date.

        Rule 3: Inferred-only events within a (canonical_from, canonical_to)
                pair collapse on date-range overlap (the snapshot path
                often re-fires across pipeline runs as the snapshot
                history grows). Pick the EARLIEST trade_date in each
                cluster so the marker sits close to when the trade
                actually happened.
        """
        from datetime import date as _date
        from collections import defaultdict

        # Step 1: parse + filter to real trades.
        candidates: list[dict] = []
        for t in trades:
            if not _is_real_trade(t):
                continue
            try:
                td = _date.fromisoformat(t.get("trade_date", ""))
            except (TypeError, ValueError):
                continue
            try:
                rs = _date.fromisoformat(t.get("date_range_start") or "")
            except (TypeError, ValueError):
                rs = td
            try:
                re_ = _date.fromisoformat(t.get("date_range_end") or "")
            except (TypeError, ValueError):
                re_ = td
            candidates.append({
                "_t": t, "td": td, "rs": rs, "re": re_,
                "cf": canonical_org(t.get("from_org")),
                "ct": canonical_org(t.get("to_org")),
            })

        # Step 2: separate API and inferred per (cf, ct).
        api_by_pair: dict[tuple, list[dict]] = defaultdict(list)
        inferred_by_pair: dict[tuple, list[dict]] = defaultdict(list)
        for c in candidates:
            pair = (c["cf"], c["ct"])
            if c["_t"].get("source") == "mlb_api":
                api_by_pair[pair].append(c)
            else:
                inferred_by_pair[pair].append(c)

        chosen: list[dict] = []

        # Rule 1+2: per pair, if there are any API records, keep the best
        # one PER trade-date (API trade-dates are accurate, so distinct
        # dates within the same pair are distinct events).
        for pair, api_list in api_by_pair.items():
            by_date: dict[_date, dict] = {}
            for c in api_list:
                existing = by_date.get(c["td"])
                if existing is None:
                    by_date[c["td"]] = c
                else:
                    if _trade_pref_score(c["_t"]) > _trade_pref_score(existing["_t"]):
                        by_date[c["td"]] = c
            chosen.extend(by_date.values())

        # Rule 3: inferred-only events. Skip any (cf, ct) pair that
        # already has an API record (the API record wins outright).
        for pair, inf_list in inferred_by_pair.items():
            if pair in api_by_pair:
                continue
            # Interval-merge clusters on date_range overlap.
            inf_list.sort(key=lambda x: x["rs"])
            current: list[dict] = []
            current_end: _date | None = None
            clusters: list[list[dict]] = []
            for c in inf_list:
                if current and c["rs"] <= current_end:
                    current.append(c)
                    if c["re"] > current_end:
                        current_end = c["re"]
                else:
                    if current:
                        clusters.append(current)
                    current = [c]
                    current_end = c["re"]
            if current:
                clusters.append(current)
            for cluster in clusters:
                # Earliest trade_date wins.
                cluster.sort(key=lambda x: x["td"])
                chosen.append(cluster[0])

        chosen.sort(key=lambda x: x["td"])
        # Canonicalize from_org / to_org to 3-letter codes for display + the
        # farm-page filter on the front-end. Keep the full original strings
        # in `from_org_full` / `to_org_full` for the description context, and
        # leave the description text alone.
        out: list[dict] = []
        for c in chosen:
            t = dict(c["_t"])
            from_full = t.get("from_org")
            to_full = t.get("to_org")
            t["from_org_full"] = from_full
            t["to_org_full"] = to_full
            t["from_org"] = canonical_org(from_full)
            t["to_org"] = canonical_org(to_full)
            out.append(t)
        return out

    # Verb patterns that classify a trade-table entry into the discrete
    # acquisition methods the front-end filter offers. Order matters —
    # the first pattern that matches wins, so "off waivers" must beat
    # "traded" for waiver-claim transactions that include both verbs in
    # the description.
    _ACQUISITION_VERB_RULES = (
        (("off waivers", " on waivers", "claimed off waivers"),       "waiver"),
        (("purchased the contract", "purchased contract",
          "purchase of the contract"),                                "contract_purchase"),
        (("returned to ",),                                           "rule_5"),
        (("selected by",),                                            "rule_5"),
        (("signed as a free agent",),                                 "free_agent"),
        (("traded ",),                                                "trade"),
    )

    def _classify_current_acquisition(filtered_trades: list[dict],
                                      acquisition: dict | None) -> str:
        """How the player's CURRENT org acquired them.

        Returns one of: 'draft', 'international_fa', 'trade', 'waiver',
        'rule_5', 'free_agent', 'contract_purchase', 'unknown'.

        If there are no cross-org events, the answer is the player's
        original acquisition method (draft or IFA). Otherwise the most
        recent inter-org event's verb wins — that's what brought them to
        their current org. Trade description text drives the verb match
        because typeCode alone collapses too many move types onto "TR".
        """
        if not filtered_trades:
            if acquisition:
                m = acquisition.get("method")
                if m in ("draft", "international_fa"):
                    return m
            return "unknown"
        latest = max(filtered_trades, key=lambda t: t.get("trade_date") or "")
        desc = (latest.get("description") or "").lower()
        for patterns, kind in _ACQUISITION_VERB_RULES:
            if any(pat in desc for pat in patterns):
                return kind
        # Cross-org event with no recognized verb — fall back to "trade"
        # (typeCode TR is the dominant unclassified case).
        return "trade"

    def _latest_post_graduation_org(p: PlayerTimeseries,
                                    filtered_trades: list[dict]) -> str | None:
        """Pick the org a graduate is currently on by walking every
        post-graduation move on record.

        Today's bug surfaced via Otto Lopez: he was traded TOR → SFG on
        2024-02-13 (a real bilateral trade), then DFA'd by SFG on
        2024-04-01, then claimed off waivers by MIA on 2024-04-04. The
        waiver claim is on `p.transactions[]`, NOT `filtered_trades`
        (which only carries bilateral trades). Looking at trades alone
        returned SFG — leaving Otto on the Giants in the UI when he was
        actually a Marlin.

        Fix: union the post-grad cross-org events from BOTH sources,
        sort by date, take the latest. Then collapse short bounce chains
        — if the latest event came from an intermediate org the player
        only briefly belonged to (< 90 days), surface the stable origin
        instead. Otto's chain becomes TOR → MIA rather than SFG → MIA.
        """
        grad = _display_graduation_date(p) or p.debut_date
        if not grad:
            return None
        events: list[tuple[str, str, str]] = []  # (date, from_org, to_org)
        for t in filtered_trades or []:
            d = t.get("trade_date") or ""
            if d > grad and t.get("to_org"):
                events.append((d, t.get("from_org") or "", t.get("to_org")))
        cross_org_kinds = ("rule_5_return", "waiver_claim",
                           "contract_purchase", "signed_free_agent",
                           "rule_5", "waiver")
        tx_rows = (transactions_by_player or {}).get(p.player_key) or []
        for tx in tx_rows:
            kind = tx.get("kind")
            if kind not in cross_org_kinds:
                continue
            d = tx.get("date") or ""
            if d <= grad:
                continue
            to_code = (canonical_org(tx.get("to_team_name"))
                       or canonical_org(tx.get("to_team")))
            from_code = (canonical_org(tx.get("from_team_name"))
                         or canonical_org(tx.get("from_team")))
            if not to_code or to_code == from_code:
                continue
            if to_code not in _MLB_ORG_CODES_FOR_OVERRIDE:
                continue
            events.append((d, from_code or "", to_code))
        if not events:
            return None
        events.sort()  # latest is last
        return events[-1][2]

    # Bounce-chain collapse window — when a player passes through a
    # short-tenure intermediate org en route to their current home, we
    # roll the org-change message up to the stable prior org. 90 days
    # captures DFA→trade→DFA→waiver chains without lumping in a real
    # half-season stint at the intermediate club.
    _BOUNCE_WINDOW_DAYS = 90

    def _collapse_bounce_chain(latest_event: dict | None,
                               all_events: list[dict]) -> dict | None:
        """Walk backward from `latest_event` through events where the
        chosen `from_org` was itself acquired by that org within
        _BOUNCE_WINDOW_DAYS earlier. Returns a copy of `latest_event`
        with `from_org` replaced by the stable origin (and a
        `bounce_via` list recording the skipped intermediaries with
        their durations) — or the original event if no collapse fires.
        """
        from datetime import date as _date
        if not latest_event:
            return latest_event
        events = sorted(
            [e for e in (all_events or []) if e.get("date") and e.get("to_org")],
            key=lambda e: e["date"],
        )
        cur = dict(latest_event)
        bounce_via: list[dict] = []
        max_loops = 5  # cheap safety against pathological data
        while max_loops:
            max_loops -= 1
            from_org = cur.get("from_org")
            if not from_org:
                break
            # Find the most recent earlier event where the player ARRIVED
            # at `from_org`. If that arrival date is < window days before
            # `cur.date`, the from_org was a brief stopover — collapse.
            cur_d = cur.get("date") or ""
            try:
                cur_dt = _date.fromisoformat(cur_d)
            except (TypeError, ValueError):
                break
            prior = None
            for e in events:
                if (e.get("to_org") == from_org
                        and e.get("date") and e["date"] < cur_d):
                    prior = e  # iterate forward so last match wins
            if not prior:
                break
            try:
                prior_dt = _date.fromisoformat(prior["date"])
            except (TypeError, ValueError):
                break
            gap_days = (cur_dt - prior_dt).days
            if gap_days >= _BOUNCE_WINDOW_DAYS:
                break  # this from_org was a real tenure, stop walking
            bounce_via.append({
                "org": from_org,
                "days": gap_days,
                "arrived": prior["date"],
            })
            cur["from_org"] = prior.get("from_org") or ""
        if bounce_via:
            cur["bounce_via"] = bounce_via
        return cur

    # Static allowlist of MLB 3-letter org codes used to gate the
    # transaction-based org override. `canonical_org()` passes through
    # affiliate names it can't resolve (e.g. "Sugar Land Space Cowboys"
    # stays as that string), so we whitelist by the known MLB codes
    # rather than trusting the canonicalization output blind.
    _MLB_ORG_CODES_FOR_OVERRIDE = frozenset({
        "ARI", "ATH", "ATL", "BAL", "BOS", "CHC", "CHW", "CIN", "CLE",
        "COL", "DET", "HOU", "KCR", "LAA", "LAD", "MIA", "MIL", "MIN",
        "NYM", "NYY", "PHI", "PIT", "SDP", "SEA", "SFG", "STL", "TBR",
        "TEX", "TOR", "WSN",
    })

    def _latest_cross_org_transaction(p: PlayerTimeseries) -> str | None:
        """Return the to_org of the player's most-recent cross-org
        transaction (Rule 5 return, waiver claim, contract purchase
        across teams, FA signing) IF that transaction post-dates every
        snapshot we have on file AND resolves to a known MLB-org code.

        The snapshot-derived `p.org` lags reality for events the
        ranking sources haven't refreshed against yet — most commonly
        Rule 5 returns mid-season, where a player gets shipped back to
        his original org but the FV-ranking sites still show him with
        the team that drafted him. We bridge the gap by trusting the
        MLB Stats API transaction record. The MLB-code gate prevents
        accidentally writing an affiliate name (e.g. a Triple-A team
        name from a contract-purchase to Sugar Land) into the org
        field."""
        tx_rows = (transactions_by_player or {}).get(p.player_key) or []
        if not tx_rows:
            return None
        cross_org_kinds = ("rule_5_return", "waiver_claim", "contract_purchase",
                           "signed_free_agent")
        relevant = []
        for tx in tx_rows:
            if tx.get("kind") not in cross_org_kinds:
                continue
            from_code = canonical_org(tx.get("from_team_name"))
            to_code = canonical_org(tx.get("to_team_name"))
            if not from_code or not to_code:
                continue
            if from_code == to_code:
                continue
            # Both endpoints must resolve to known MLB codes — affiliate
            # names that canonical_org passes through get rejected here.
            if to_code not in _MLB_ORG_CODES_FOR_OVERRIDE:
                continue
            relevant.append((tx, to_code))
        if not relevant:
            return None
        latest_tx, latest_code = max(relevant, key=lambda x: x[0].get("date") or "")
        latest_date = latest_tx.get("date") or ""
        if not latest_date:
            return None
        # v19 — Relaxed override window. The previous "only override
        # when tx is newer than every snapshot" gate was too restrictive
        # — Rule 5 Draft picks (RJ Petit → Rockies, Dec 2025) were
        # losing the override when a stale-cached snapshot post-dated
        # the transaction. The MLB transactions feed is the
        # authoritative source of truth for cross-org moves; the
        # ranking sources are weeks-to-months behind on team changes.
        # Trust the latest cross-org tx within the past 365 days
        # unconditionally; only skip when the tx is older than that
        # (stale move that the rankings have had ample time to catch).
        try:
            tx_dt = date.fromisoformat(latest_date)
            tx_age_days = (date.today() - tx_dt).days
        except (ValueError, TypeError):
            tx_age_days = 9999
        if tx_age_days > 365:
            return None
        return latest_code

    # Phrases that flag the underlying surgery in an IL stint's
    # description / reason text. Matched case-insensitively; substring
    # match is fine because the API descriptions are verbose ("recovery
    # from Tommy John surgery", "Left UCL surgery", etc.). "UCL sprain"
    # is intentionally NOT in this set — a sprain isn't a confirmed TJ.
    # v17 — Expanded TJ phrase list. The original 5 phrases missed many
    # IL descriptions like "elbow surgery" or "flexor tendon repair" that
    # in practice indicate TJ-class procedures. We accept some false
    # positives (a generic "elbow surgery" might be a non-TJ cleanup) in
    # exchange for catching the long tail of TJ pitchers the prior list
    # missed entirely. Combined with the FG `_extras.tj_date` integration
    # below this should flag the vast majority of post-TJ prospects.
    _TJ_PHRASES = (
        "tommy john",
        "ucl",                     # catches "UCL surgery", "UCL reconstruction",
                                   # "ulnar collateral ligament" all
        "ulnar collateral",
        "internal brace",          # modern hybrid UCL repair
        "elbow surgery",
        "elbow reconstruction",
        "flexor tendon",
        "ucl reconstruction",
    )

    def _derive_health_profile(injury_history: list[dict],
                                today: "date | None" = None) -> dict:
        """Derive aggregate injury signals used by the UI + ETA model.

        Looks at:
          * Number of distinct IL stints in the trailing 12 months —
            anything >= 3 indicates a chronic injury pattern.
          * Total IL days in the trailing 12 months — separate signal
            from stint count so a single multi-month IL still counts.
          * Whether the player has had Tommy-John-class elbow surgery
            on record (any stint description matches _TJ_PHRASES). The
            chip on the prospect page surfaces this prominently, and
            ETA can be padded for the typical 12-18 month recovery.

        Open stints (active === True) count toward both metrics
        because an actively-injured player is currently lost playing
        time — but the days for an open stint reflect what's elapsed
        so far, not the full eventual stint length.
        """
        from datetime import date as _date, timedelta as _td
        today = today or _date.today()
        cutoff = today - _td(days=365)
        recent_stints = 0
        recent_days = 0
        tj_dates: list[str] = []
        for stint in injury_history or []:
            since_str = stint.get("since") or ""
            try:
                since = _date.fromisoformat(since_str)
            except (TypeError, ValueError):
                continue
            if since >= cutoff:
                recent_stints += 1
                days = stint.get("days") or 0
                if not days and stint.get("active"):
                    # Open stint without a closed-stint days field — estimate
                    # as (today - since). Cap at the trailing-window length
                    # (~365d) so a stale open stint whose activation row
                    # never landed in the API can't blow the total up.
                    days = max(0, (today - since).days)
                # Cap any single stint at the 12-month window length to
                # prevent old data anomalies from inflating the headline.
                _MAX_PER_STINT_DAYS = 365
                if days > _MAX_PER_STINT_DAYS:
                    days = _MAX_PER_STINT_DAYS
                recent_days += int(days or 0)
            desc = " ".join([
                str(stint.get("description") or ""),
                str(stint.get("reason") or ""),
            ]).lower()
            if any(p in desc for p in _TJ_PHRASES):
                tj_dates.append(since_str)
        tj_latest = max(tj_dates) if tj_dates else None
        # Final aggregate cap: the trailing-12-month window is itself ~365
        # days long, so the SUM of IL days within that window can't
        # exceed 365. Multiple overlapping stints (rare but possible from
        # transferred 15→60 day rows) could otherwise double-count.
        if recent_days > 365:
            recent_days = 365
        return {
            "il_stints_12mo": recent_stints,
            "il_days_12mo":   recent_days,
            "is_post_tj":     bool(tj_dates),
            # Latest TJ-class surgery date. The UI uses it to label the
            # chip ("Post-TJ · 2024-09-03"); the ETA helper checks it
            # against today to decide whether to apply a recovery delay.
            "tj_surgery_date": tj_latest,
        }

    def _active_display_org(p: PlayerTimeseries) -> str | None:
        # Canonicalize at the display layer so historical snapshots with
        # pre-rename codes (e.g. "OAK" before the Athletics dropped Oakland)
        # collapse onto the current canonical key ("ATH") rather than
        # showing up as a second farm-page entry.
        #
        # A recent cross-org transaction (Rule 5 return, waiver claim,
        # contract purchase across teams) overrides the snapshot-derived
        # org because the FV-ranking sources usually lag those moves by
        # weeks; trusting the MLB transactions record keeps the team
        # logo on the player card pointing at where they actually play.
        # v12 — the tx override can return non-MLB-30 strings (Office
        # of the Commissioner = released to FA). Only use it when it
        # resolves to one of the 30 canonical orgs; otherwise fall
        # through to the roster/snapshot org.
        tx_override = _latest_cross_org_transaction(p)
        if tx_override and tx_override in MLB_30_ORGS:
            return tx_override
        # v19 — Trade-based override. _latest_cross_org_transaction only
        # looks at the MLB transactions feed (waiver/rule-5/etc.) and
        # excludes plain trades. Walk p's recorded trades; trust the
        # most-recent trade within the past 365 days as the canonical
        # current org. Stale trades >1yr old fall through to the
        # snapshot/roster org.
        trades = (trades_by_player or {}).get(p.player_key) or []
        if trades:
            sorted_trades = sorted(
                (t for t in trades if t.get("trade_date") and t.get("to_org")),
                key=lambda t: t["trade_date"],
            )
            # SOURCE OUTRANKS RECENCY (2026-08-05, the Alexander Frias bug).
            # `trades` holds two different KINDS of row. `mlb_api` rows are
            # parsed from MLB's own transaction feed and state a trade that
            # happened. `inferred` rows are DEDUCED from a player appearing
            # under a different org across two prospect-list snapshots, so a
            # publisher that is slow to drop a traded player manufactures a
            # phantom trade BACK to the club that traded him, dated later than
            # the real one. Taking the newest row by date therefore let the
            # fabrication win: Frias was traded to St. Louis on 08-03 (mlb_api,
            # with the full description), MLB Pipeline's Brewers Top 30 still
            # listed him on 08-04, an `inferred` STL->MIL row was written from
            # that, and he was served as the Brewers' 5th-best prospect. 178
            # players were in that state.
            # So: if MLB's own feed has ever recorded a trade for this player,
            # the latest of THOSE is the answer, and an inference cannot
            # overrule it. Inferred rows still decide the case where the feed
            # never saw the move at all, which is what they were added for.
            api_trades = [t for t in sorted_trades
                          if (t.get("source") or "") == "mlb_api"]
            if api_trades:
                sorted_trades = api_trades
            if sorted_trades:
                latest_trade = sorted_trades[-1]
                trade_to = canonical_org(latest_trade.get("to_org"))
                trade_date = latest_trade.get("trade_date") or ""
                try:
                    trade_age_days = (date.today() - date.fromisoformat(trade_date)).days
                except (ValueError, TypeError):
                    trade_age_days = 9999
                if (trade_to and trade_to in MLB_30_ORGS
                        and trade_age_days <= 365):
                    return trade_to
        return canonical_org(roster_org_by_key.get(p.player_key) or p.org)

    def _display_org(p: PlayerTimeseries,
                     filtered_trades: list[dict]) -> str | None:
        if p.status == "debuted":
            return canonical_org(
                _latest_post_graduation_org(p, filtered_trades)
                or graduate_mlb_org_by_key.get(p.player_key)
                or roster_org_by_key.get(p.player_key)
                or p.org
            )
        return _active_display_org(p)

    def _level_changes_with_debut(player_key: str) -> list[dict]:
        """Return the player's level_changes with a `kind: "debut"` row
        pointing at the prospect's actual MLB debut date.

        We gate on `roster_status.mlb_debut_date` being set — that field
        is sourced from the MLB API's authoritative `mlbDebutDate` and
        falls back to the first contract-selection date only when the
        career rows confirm real MLB activity. A 40-man-only Rule 5
        protection will NOT have a debut date, so no debut row gets
        rendered even though the SE transaction may have produced a
        spurious MiLB→MLB promotion in level_changes.
        """
        rows = list(level_changes.get(player_key, []) or [])
        rs = roster_status.get(player_key) or {}
        debut_date = rs.get("mlb_debut_date")
        if not debut_date:
            return rows

        # Find the level_changes row dated closest to the debut date —
        # usually the contract-selection row will match exactly. If we
        # find one within a few days of the authoritative debut date,
        # convert it in place. Otherwise prepend a synthetic row.
        from datetime import date as _date
        try:
            debut_d = _date.fromisoformat(debut_date)
        except ValueError:
            debut_d = None
        match_idx = None
        if debut_d is not None:
            best_diff = 8  # days
            for i, r in enumerate(rows):
                if r.get("to_level") != "MLB":
                    continue
                try:
                    d = _date.fromisoformat(r.get("date") or "")
                except ValueError:
                    continue
                diff = abs((d - debut_d).days)
                if diff <= best_diff:
                    best_diff = diff
                    match_idx = i

        if match_idx is not None:
            marked = dict(rows[match_idx])
            marked["kind"] = "debut"
            marked["is_debut"] = True
            marked["date"] = debut_date  # snap to the authoritative date
            rows[match_idx] = marked
        else:
            rows.append({
                "date": debut_date,
                "kind": "debut",
                "is_debut": True,
                "from_level": None,
                "to_level": "MLB",
                "from_team": None,
                "to_team": None,
            })
        return rows

    def _serialize(p: PlayerTimeseries) -> dict:
        bd = birth_dates.get(p.player_key)
        age = compute_age_decimal(bd)
        sl = statlines.get(p.player_key)
        # v7 — statline freshness gate for MLB graduates. The statline
        # dict carries the player's latest single row (typically MiLB);
        # for a player who graduated mid-season, that row sits stale
        # while their actual current-season stats live on the MLB row
        # in career_stats. Swap to the MLB row when present so Colt
        # Emerson-style "displayed as AAA despite being on MLB roster"
        # bugs stop. Only swaps if the MLB row has real activity
        # (PA≥1 or IP≥0.1) — a 0-PA call-up doesn't beat the AAA
        # workload row.
        _cy = date.today().year
        _rows_for_p = (career_stats or {}).get(p.player_key, []) or []
        _mlb_row = next(
            (r for r in _rows_for_p
             if r.get("season") == _cy and r.get("level") == "MLB"),
            None,
        )
        if _mlb_row:
            try:
                _pa = float(_mlb_row.get("pa") or _mlb_row.get("ab") or 0)
            except (TypeError, ValueError):
                _pa = 0.0
            try:
                _ip = float(_mlb_row.get("ip") or 0)
            except (TypeError, ValueError):
                _ip = 0.0
            if _pa >= 1 or _ip >= 0.1:
                # Build a statline-shaped dict from the career_stats
                # MLB row, falling back through existing fields so all
                # downstream consumers (ETA, level-plus, RPS+) keep
                # working. Carry forward mlbam_id + is_pitcher from
                # the original statline since those don't change.
                _sl_existing = sl or {}
                sl = {
                    **_sl_existing,
                    **_mlb_row,
                    "level": "MLB",
                    "season": _cy,
                    "is_prior_season": False,
                    # Preserve mlbam_id / is_pitcher from the prior
                    # statline if the career row lacks them.
                    "mlbam_id": _mlb_row.get("mlbam_id") or _sl_existing.get("mlbam_id"),
                    "is_pitcher": _mlb_row.get("is_pitcher")
                                  if "is_pitcher" in _mlb_row
                                  else _sl_existing.get("is_pitcher"),
                }
        _scm_pre = statcast_metrics.get(p.player_key)
        _latest_played_level_pre = None
        for _g in ((_scm_pre or {}).get("recent_games") or []):
            _lvl = str((_g or {}).get("level") or "").strip()
            if _lvl:
                _latest_played_level_pre = _lvl
                break
        _level_changes_pre = _level_changes_with_debut(p.player_key)
        _latest_level_event_pre = None
        for _lc in _level_changes_pre:
            _lc_date = _lc.get("date") or ""
            if _lc_date and _lc_date > date.today().isoformat():
                continue
            if _lc.get("to_level"):
                _latest_level_event_pre = _lc
        _statline_level_pre = sl.get("level") if sl else None
        _current_level_pre = None
        if p.status == "debuted" or (roster_status.get(p.player_key) or {}).get("mlb_debut_date"):
            _rs_pre = roster_status.get(p.player_key) or {}
            _debut_date_pre = _rs_pre.get("mlb_debut_date") or p.debut_date or ""
            _post_debut_move_pre = None
            _debut_event_pre = None
            for _lc in reversed(_level_changes_pre):
                _lc_date = _lc.get("date") or ""
                if (
                    _lc.get("kind") in {"promotion", "demotion"}
                    and _lc.get("to_level")
                    and _debut_date_pre
                    and _lc_date > _debut_date_pre
                ):
                    _post_debut_move_pre = _lc
                    break
                if _debut_event_pre is None and _lc.get("kind") == "debut" and _lc.get("to_level"):
                    _debut_event_pre = _lc
            _current_level_pre = (
                _latest_played_level_pre
                or ((_post_debut_move_pre or {}).get("to_level"))
                or ((_debut_event_pre or {}).get("to_level"))
                or "MLB"
            )
        else:
            _current_level_pre = (
                _latest_played_level_pre
                or roster_level_by_key.get(p.player_key)
                or ((_latest_level_event_pre or {}).get("to_level"))
                or _statline_level_pre
            )
        # If a player has multiple same-season level rows, use the current
        # assignment's row for the headline statline when it exists. The
        # full set is exported below as current_season_statlines so the UI
        # can show AA + AAA instead of implying one slash covers both.
        _cy_pre = date.today().year
        _rows_for_p_pre = (career_stats or {}).get(p.player_key, []) or []
        _current_level_row_pre = next(
            (r for r in _rows_for_p_pre
             if r.get("season") == _cy_pre and r.get("level") == _current_level_pre),
            None,
        )
        if _current_level_row_pre and sl:
            sl = {
                **sl,
                **_current_level_row_pre,
                "level": _current_level_pre,
                "season": _cy_pre,
                "is_prior_season": False,
                "mlbam_id": _current_level_row_pre.get("mlbam_id") or sl.get("mlbam_id"),
                "is_pitcher": _current_level_row_pre.get("is_pitcher")
                              if "is_pitcher" in _current_level_row_pre
                              else sl.get("is_pitcher"),
            }
        level = sl.get("level") if sl else _current_level_pre
        avl = score_age_vs_level(age, level, baselines=age_baselines)
        pa = pitch_arsenals.get(p.player_key)
        zm = zone_metrics.get(p.player_key)
        scm = _scm_pre
        zm = _prefer_metric_current_level(zm, _current_level_pre)
        scm = _prefer_metric_current_level(scm, _current_level_pre)
        sm = sabermetrics.get(p.player_key)
        is_pitcher = bool(p.position and p.position.split("/")[0] in PITCHER_POS_SET)
        latest_fv = p.points[-1].consensus_fv_raw if p.points else None
        # Health profile: 12-month IL stints + days + Tommy-John flag.
        # Computed once from the cached injury_history so the rest of
        # the pipeline (ETA model, stat_flags injury-prone rule, UI
        # chip) can pull from one dict instead of re-parsing dates.
        rs = roster_status.get(p.player_key) or {}
        health = _derive_health_profile(rs.get("injury_history") or [])
        # v17 — Integrate FG `_extras.tj_date` from any per-source snapshot.
        # Amateur prospects (pre-MLB) often have no IL transactions but
        # FanGraphs publishes a tj_date in their amateur scouting blob.
        # Set is_post_tj from FG's date even when the transactions log is
        # silent. Prefer the existing IL-derived date when present (more
        # authoritative for current-pro prospects).
        if not health.get("is_post_tj"):
            _fg_tj_date = None
            for _pt in (p.points or []):
                _fg = ((_pt.per_source or {}).get("fangraphs") or {})
                _ex = ((_fg.get("tools") or {}).get("_extras") or {})
                _td = _ex.get("tj_date")
                if _td:
                    if _fg_tj_date is None or str(_td) > _fg_tj_date:
                        _fg_tj_date = str(_td)
            if _fg_tj_date:
                health["is_post_tj"] = True
                health["tj_surgery_date"] = _fg_tj_date
                health["tj_source"] = "fangraphs_extras"
        eta = estimate_eta(
            level, age, is_pitcher, latest_fv, sl,
            expected_ages=age_baselines,
            ops_norm=ops_norms,
            era_norm=era_norms,
            health=health,
            # v29 — Statcast+ ETA modifier. None when the player has no
            # tracked Statcast / zone data; estimate_eta then leaves
            # statcast_plus_adj at 0.0 (no signal).
            statcast_plus=_sc_plus_map.get(p.player_key),
            # Pipe through today's date so estimate_eta resolves the
            # season_phase (pre-break / post-break / offseason) and
            # applies the half-season-elapsed adjustment when the
            # snapshot lands after the All-Star break.
            snapshot_date=date.today(),
            # Org promotion multipliers removed (owner answer ETA-3, 2026-09-30,
            # after the section 7 keep-or-remove gate of ETA_FG_BLEND_GATE.md read
            # REMOVE: 0 of 1,394 rows moved). None leaves the half-season term at
            # the league baseline, the pull-in floor unscaled and eta_half free of
            # the org nudge.
            org_promotion_tendency=None,
            # v12 — current IL status pushes ETA out. Season-ending
            # injury (or 60+ days on IL) adds +1.0y; 30-59 days adds
            # +0.5y. Fixes "Sebastian Walcott ETA 2026 despite being
            # out for the year" — without this, the ETA model only
            # tracked rolling-12mo health signals, not active IL.
            il_status=il_status.get(p.player_key) or {},
            # Per-level bias shave (forward-chained, gate-validated): the
            # heuristic ran ~1yr LATE on debuted players; LEVEL_BIAS_ADJ pulls
            # minor-level ETAs earlier (eta_backtest MAE 1.44->1.23).
            level_bias_adj=ETA_LEVEL_BIAS_ADJ,
            # S2 eta-hazard-lite (flipped 2026-07-29): a player already on the
            # 40-man is nearer the majors than his level alone implies. Only
            # 40-man rows get a shave; everyone else passes None and is
            # byte-identical. See eta.FORTYMAN_ADJ for why the table is the
            # production-frame refit and why AAA is deliberately 0.0.
            fortyman_adj=(ETA_FORTYMAN_ADJ.get(level)
                          if rs.get("on_40_man") else None),
            # Live caller only: eta_backtest never passes it, so eta_eval is unmoved.
            regular_season_end=_eta_season_end,
        )
        # FanGraphs-blend arm (eta.ETA_FG_BLEND_ARM, default None = champion served
        # unchanged; apply_fg_blend returns the same object). Registered gate:
        # docs/eta-2026-09-25/ETA_FG_BLEND_GATE.md; flipping it is the owner's call.
        if _eta_mod.ETA_FG_BLEND_ARM is not None:
            eta = apply_fg_blend(
                eta,
                fg_eta_year_from_per_source(
                    p.points[-1].per_source if p.points else None,
                    list_year=date.today().year),
                arm=_eta_mod.ETA_FG_BLEND_ARM,
                on40=bool(rs.get("on_40_man")),
                floor_year=live_floor_year(date.today(), _eta_season_end,
                                           date.today().year),
            )
        # Performance-vs-level-median enrichment. wRC+/xFIP aren't on the
        # MLB Stats API, so we compute their conceptual cousins from the
        # per-level baselines we already have:
        #   hitter : OPS+ = round(OPS / level_avg_ops * 100). >100 better.
        #   pitcher: ERA- = round(ERA / level_avg_era * 100). <100 better.
        # `level_plus_pct` is the same number expressed as a signed delta
        # (positive = good for either type) so the UI can drive color +
        # direction without re-branching on stat type.
        sl_out = dict(sl) if sl else None
        if sl_out:
            lvl = sl_out.get("level")
            norms_perf = (level_norms.get(lvl) or {}).get("perf") or {} if lvl else {}
            try:
                if sl_out.get("is_pitcher"):
                    # `is None` (not truthiness): a genuine 0.00 ERA is a REAL
                    # value, not a missing one. The old guard
                    # (`if era and avg_era and era > 0`) dropped every scoreless
                    # pitcher, and the drop cascaded: no era_minus_level means no
                    # level_plus_pct, which means no computeRelProd and therefore
                    # no RPS+ pill on the card. Same rule the acq_draft leaf spec
                    # states further down this function. avg_era keeps a
                    # truthiness guard because it is a DIVISOR (0 would raise).
                    era = _safe_float(sl_out.get("era"))
                    avg_era = norms_perf.get("avg_era")
                    if era is not None and era >= 0 and avg_era:
                        # Empirical-Bayes shrinkage toward the level mean by
                        # sample size before indexing — a few-IP line no longer
                        # reads as an extreme ERA-. K_IP (ERA stabilization,
                        # IP units): rate_stabilization.py has the provenance.
                        ip = float(sl_out.get("ip") or 0)
                        era_adj = (ip * era + K_IP * avg_era) / (ip + K_IP)
                        era_minus = round(era_adj / avg_era * 100)
                        sl_out["era_minus_level"] = era_minus
                        sl_out["level_plus_pct"] = round((avg_era - era_adj) / avg_era * 100)
                    # Peripheral STF+ (K%, BB%, HR/9 vs level mean). Replaces
                    # the scouting-grade composite as the headline STF+ chip;
                    # the scouting composite is still computed in tools.* but
                    # gets relabeled "Stuff grade+" in the UI.
                    stf_periph = _compute_peripheral_stf_plus(sl_out, norms_perf)
                    if stf_periph is not None:
                        sl_out["stf_plus_periph"] = stf_periph
                else:
                    # Same `is None` rule as the ERA branch above: a genuine
                    # .000 OPS is a real (bad) line, not a missing one, and it
                    # must still index to an ops_plus_level / level_plus_pct.
                    ops = _safe_float(sl_out.get("ops"))
                    avg_ops = norms_perf.get("avg_ops")
                    if ops is not None and ops >= 0 and avg_ops and avg_ops > 0:
                        # Empirical-Bayes shrinkage toward the level mean by
                        # sample size before indexing — a 4-AB line no longer
                        # reads OPS+ 374. K_AB (OPS stabilization, AB units):
                        # rate_stabilization.py has the provenance.
                        ab = float(sl_out.get("ab") or 0)
                        ops_adj = (ab * ops + K_AB * avg_ops) / (ab + K_AB)
                        ops_plus = round(ops_adj / avg_ops * 100)
                        sl_out["ops_plus_level"] = ops_plus
                        sl_out["level_plus_pct"] = round((ops_adj - avg_ops) / avg_ops * 100)
                    # wRC+ vs level, stamped ALONGSIDE the OPS chip (Phase D2). See
                    # _wrc_plus_level: different metric AND different baseline, so the
                    # two are carried together while the swap is measured rather than
                    # one silently replacing the other under a shared name.
                    _w = _wrc_plus_level(sl_out.get("mlbam_id"), sl_out.get("season"),
                                         sl_out.get("level"))
                    if _w is not None:
                        sl_out["wrc_plus_level"] = _w
            except (TypeError, ValueError, ZeroDivisionError):
                pass

        _current_season_statlines = []
        for _r in (career_stats or {}).get(p.player_key, []) or []:
            if _r.get("season") != date.today().year:
                continue
            _rr = dict(_r)
            _lvl = _rr.get("level")
            _norms_perf = (level_norms.get(_lvl) or {}).get("perf") or {} if _lvl else {}
            try:
                if _rr.get("is_pitcher"):
                    # Same `is None` rule as the headline statline above. Kept in
                    # lockstep deliberately: if the per-season row used the old
                    # truthiness guard a scoreless pitcher would show an ERA- chip
                    # on his headline line and NO chip on the per-season row for
                    # the same outing, which is a silent divergence between two
                    # display surfaces of one number.
                    _era = _safe_float(_rr.get("era"))
                    _avg_era = _norms_perf.get("avg_era")
                    if _era is not None and _era >= 0 and _avg_era:
                        # Same empirical-Bayes shrink toward the level mean as the
                        # headline statline (storage.py ~L8473). Without it, a
                        # few-IP per-season row re-enabled the extreme ERA- the
                        # headline guard was added to kill. K_IP has the provenance.
                        _ip = float(_rr.get("ip") or 0)
                        _era_adj = (_ip * _era + K_IP * _avg_era) / (_ip + K_IP)
                        _rr["era_minus_level"] = round(_era_adj / _avg_era * 100)
                else:
                    # `is None`, matching the headline statline (see above).
                    _ops = _safe_float(_rr.get("ops"))
                    _avg_ops = _norms_perf.get("avg_ops")
                    if _ops is not None and _ops >= 0 and _avg_ops and _avg_ops > 0:
                        # Same empirical-Bayes shrink as the headline statline
                        # (storage.py ~L8494): a 4-AB line no longer reads
                        # OPS+ 374. K_AB has the provenance.
                        _ab = float(_rr.get("ab") or 0)
                        _ops_adj = (_ab * _ops + K_AB * _avg_ops) / (_ab + K_AB)
                        _rr["ops_plus_level"] = round(_ops_adj / _avg_ops * 100)
                    # career_stats rows carry no mlbam_id (measured: 0 of 2,794),
                    # so fall back to the headline statline's, which is the same
                    # player by construction.
                    _w = _wrc_plus_level(
                        _rr.get("mlbam_id") or (sl_out or {}).get("mlbam_id"),
                        _rr.get("season"), _rr.get("level"))
                    if _w is not None:
                        _rr["wrc_plus_level"] = _w
            except (TypeError, ValueError, ZeroDivisionError):
                pass
            _current_season_statlines.append(_rr)
        _current_season_statlines.sort(
            key=lambda r: (
                0 if r.get("level") == _current_level_pre else 1,
                _LEVEL_SORT_ORDER.get(r.get("level"), 99),
            )
        )
        scm = _adjust_statcast_xwoba_for_export(scm, sl_out, _current_season_statlines)

        # Scouting flags — green/red rate-stat indicators driven by the
        # current statline + the level norms we already built. Skipped for
        # players whose statline didn't pass the sample-size gate (see
        # stat_flags.MIN_GAMES_HITTER / MIN_IP_PITCHER); the function
        # returns [] in that case so the field is safe to render
        # unconditionally on the prospect detail page.
        flags = compute_stat_flags(sl_out, level_norms, health=health)

        # Tool grades — consensus across sources at the latest point.
        # `tools.grades` carries the per-tool 20-80 consensus; `tools.
        # composite_*` are derived in _compute_tool_composites. The X+
        # indices are stamped in a second pass once cohort norms are
        # known (see _attach_tool_plus_indices at the end of this
        # function). `tool_flags` mirror stat_flags shape and ride the
        # same green/red renderer in the UI.
        latest_point = p.points[-1] if p.points else None
        # THE board number for this player (see BOARD_GRADE_FIELD). Resolved once here so
        # the rank-movement / prev-rank tie-block guard below reads exactly the value
        # _active_key ordered on -- no second resolution, no drift.
        _ser_board_grade = _board_grade(
            p.player_key,
            latest_point.consensus_fv_raw if latest_point else None)
        tool_consensus_grades = (
            dict(latest_point.tools_consensus)
            if latest_point and latest_point.tools_consensus
            else None
        )
        # extras (frame/athl/delivery FG -2..+2 grades) and the
        # position bucket (catcher vs non-catcher) both feed the Tool /
        # D-Tool composite math, so consolidate once and pass through.
        _player_extras = _extract_player_extras(latest_point)
        # OBSERVATION, not projection (2026-07-30 owner decision). The ONLY thing
        # this bucket decides in _compute_tool_composites is whether the D-Tool
        # weights drop speed and bump field, i.e. "is this man a catcher". A player
        # who has caught 400 minor-league games IS a catcher for the purpose of
        # weighting his defensive tools, whatever the long-term projection says he
        # becomes. Falls back to the projection wherever there is no observation
        # (pitchers, and 148 served non-pitcher rows under the exposure floor), so
        # coverage never regresses.
        #
        # Blast radius, measured on the 2026-07-30 tree: 156 covered rows change
        # bucket, of which 44 cross the catcher boundary - the only crossing that
        # changes a weight - and only 9 of those 44 have a composite_def to move at
        # all (the rest carry no graded defensive tools). Best-ranked is
        # josue_briceno (served 1B, observed C, rank 65), the case this was raised
        # on. composite_def is a DISPLAY composite: it feeds the D-Tool pill and the
        # green/red tool flag and nothing else - not the board grade, not surplus -
        # so this is not board movement.
        _pos_bucket = _position_bucket(_observed_pos.get(p.player_key) or p.position)
        # v47 - Top-100 pedigree flag; set from the tool-history labels
        # below (tools.history itself is no longer shipped) and baked on
        # the player payload for bayes_trade_value._has_top100_pedigree.
        _top100_pedigree = False
        # ETOOLS_ALL_CALCS: the served composites are the eTool composites (the same
        # formula on the shown grades); the consensus ones ride under composite_cons.
        # A record whose side is not this payload's side substitutes nothing.
        _etc_rec_all = _etc_rec(p.player_key)

        def _side_rec(_is_p):
            _side = "pit" if _is_p else "hit"
            if _etc_rec_all and _etc_rec_all.get("side") in (None, _side):
                return _etc_rec_all
            return None

        def _shown_tool_payload(_is_p):
            _cons = _compute_tool_composites(
                tool_consensus_grades, _is_p,
                player_extras=_player_extras,
                position_bucket=_pos_bucket,
            )
            if not _ETC.ETOOLS_COMPOSITE_ON:
                return _cons
            _shown, _used = _ETC.shown_grades(tool_consensus_grades, _side_rec(_is_p))
            _et = (_compute_tool_composites(_shown, _is_p, player_extras=_player_extras,
                                            position_bucket=_pos_bucket)
                   if _used else None)
            return _ETC.with_consensus_reference(_et, _cons, _used)

        tools_payload = _shown_tool_payload(is_pitcher)
        if tools_payload is not None:
            publishing = []
            if latest_point:
                for src, info in (latest_point.per_source or {}).items():
                    if info and info.get("tools"):
                        publishing.append(src)
            tools_payload["publishing_sources"] = sorted(publishing)
            if latest_point and latest_point.tools_spread:
                tools_payload["spread"] = dict(latest_point.tools_spread)
            else:
                tools_payload["spread"] = {}
            # Two-way player detection: when both hitter AND pitcher
            # canonical tool keys appear in the consensus grades, emit
            # both payloads so the UI can render two Tools cards stacked
            # (e.g., Reggie Crawford, Ohtani). The position-inferred
            # default payload (above) stays populated for legacy UI paths.
            if tool_consensus_grades:
                has_hitter = any(k in tool_consensus_grades for k in HITTER_TOOL_KEYS)
                has_pitcher = any(k in tool_consensus_grades for k in PITCHER_TOOL_KEYS)
                if has_hitter and has_pitcher:
                    hitter_payload = _shown_tool_payload(False)
                    pitcher_payload = _shown_tool_payload(True)
                    if hitter_payload is not None:
                        tools_payload["hitter_payload"] = hitter_payload
                    if pitcher_payload is not None:
                        tools_payload["pitcher_payload"] = pitcher_payload
            # Time-series + per-source history. The UI uses these to
            # render the "Source-by-source tool history" dropdown and to
            # disclose that the Tool composite uses each source's most
            # recent publication (older rows are kept for context, not math).
            #
            # `history`: consensus tool grades at each snapshot date.
            # `source_history`: per-source publication timeline.
            # `source_recency`: latest publication date + stale flag per source.
            history_entries: list[dict] = []
            source_history: dict[str, list[dict]] = {}
            for pt in (p.points or []):
                pt_per_src = pt.per_source or {}
                pt_consensus = pt.tools_consensus or {}
                # Walk each source's published tools at this point.
                for src, info in pt_per_src.items():
                    if not info:
                        continue
                    # v10 — Walk primary + extras (same-date same-source
                    # supplementary publications, e.g. MLB Pipeline Top
                    # 100 + Org Top 30 both dated 2026-01-22). Each
                    # surfaces as a distinct source_history row, deduped
                    # downstream by (date, interval_label).
                    publications = [info] + (info.get("extras") or [])
                    for pub in publications:
                        src_tools = pub.get("tools") or {}
                        if not isinstance(src_tools, dict):
                            continue
                        numeric = {k: v for k, v in src_tools.items()
                                   if k != "_extras" and isinstance(v, (int, float))}
                        if not numeric:
                            continue
                        # Use the SOURCE's actual publication date (pub.snapshot_date),
                        # not the consensus-point date (pt.snapshot_date). Forward-fill
                        # carries each source's latest snapshot into every later
                        # consensus point — without this, a stale source would appear
                        # to have published at every consensus date after its last
                        # real update, corrupting the LATEST/STALE logic.
                        src_snapshot_date = pub.get("snapshot_date") or pt.snapshot_date
                        source_history.setdefault(src, []).append({
                            "snapshot_date": src_snapshot_date,
                            "interval_label": pub.get("interval_label")
                                              or pt.interval_label,
                            "grades": numeric,
                            "extras_present": bool(
                                isinstance(src_tools.get("_extras"), dict)
                                and src_tools["_extras"]
                            ),
                        })
                # Consensus snapshot — append once per point that produced
                # any tool consensus.
                if pt_consensus:
                    contributing = [src for src, info in pt_per_src.items()
                                    if info and info.get("tools")]
                    history_entries.append({
                        "snapshot_date": pt.snapshot_date,
                        "interval_label": pt.interval_label,
                        "consensus": dict(pt_consensus),
                        "sources": sorted(contributing),
                    })
            # Dedupe source_history per source by (date, interval_label) —
            # forward-fill carries the same snapshot forward many times.
            for src in list(source_history.keys()):
                seen = set()
                deduped = []
                for entry in source_history[src]:
                    key = (entry["snapshot_date"], entry["interval_label"])
                    if key in seen:
                        continue
                    seen.add(key)
                    deduped.append(entry)
                # Newest-first so the latest row sits at the top of the
                # rendered table.
                deduped.sort(key=lambda e: e["snapshot_date"], reverse=True)
                source_history[src] = deduped
            # v47 payload-slim - the consensus `history` timeline is no
            # longer shipped (no frontend reader; the per-source dropdown
            # reads source_history + source_recency, which stay). Its only
            # downstream consumer was bayes _has_top100_pedigree, which ORs
            # Top-100 labels across BOTH tools.history AND
            # tools.source_history; that OR is reproduced here and baked as
            # the `top100_pedigree` player flag (run_monthly re-reads this
            # artifact from disk for the bayes pass, so the flag must ride
            # the shipped payload for the early-debut / recent-top100
            # floors to keep firing identically).
            _ped_labels = [str(e.get("interval_label") or "")
                           for e in history_entries]
            for _ped_rows in source_history.values():
                for _ped_row in _ped_rows:
                    _ped_labels.append(str(_ped_row.get("interval_label") or ""))
            _top100_pedigree = any(
                "top 100" in _pl.lower() or "top100" in _pl.lower()
                for _pl in _ped_labels)
            if source_history:
                tools_payload["source_history"] = source_history
                # Recency: latest publication per source + stale flag.
                today_iso = date.today().isoformat()
                source_recency: dict[str, dict] = {}
                for src, entries in source_history.items():
                    if not entries:
                        continue
                    latest = entries[0]["snapshot_date"]
                    try:
                        d_latest = date.fromisoformat(latest)
                        stale_days = (date.fromisoformat(today_iso) - d_latest).days
                    except ValueError:
                        stale_days = None
                    source_recency[src] = {
                        "latest_date": latest,
                        "stale_days": stale_days,
                        "is_stale": (stale_days is not None
                                     and stale_days > TOOL_FRESHNESS_DAYS),
                    }
                tools_payload["source_recency"] = source_recency
        # The per-tool flags print the SHOWN grade (ETOOLS_ALL_CALCS): the eTool's whole
        # grade where one passed, the consensus grade otherwise.
        _flag_grades = None
        if tools_payload is not None and _ETC.ETOOLS_COMPOSITE_ON:
            _flag_grades, _ = _ETC.shown_grades(tools_payload.get("grades") or {},
                                                _side_rec(is_pitcher), value="shown")
        tool_flags = compute_tool_flags(tools_payload, is_pitcher, grades=_flag_grades)

        filtered_trades = _filter_real_trades(trades_by_player.get(p.player_key, []))
        acq = acquisitions.get(p.player_key)
        # Build the unified post-acquisition event list: real trades +
        # cross-org transactions (waivers, Rule 5, contract purchases,
        # FA signings). Sorted by date so [-1] is the latest. Each entry
        # carries a `kind` so the method classifier can prefer the
        # transaction-derived label over verb-matching the trade
        # description when there's a more recent non-trade event.
        _all_acq_events: list[dict] = []
        for t in filtered_trades:
            _all_acq_events.append({
                "kind": "trade",
                "date": t.get("trade_date"),
                "from_org": t.get("from_org"),
                "to_org": t.get("to_org"),
                "description": t.get("description"),
            })
        _cross_org_tx_kinds = ("rule_5_return", "waiver_claim",
                               "contract_purchase", "signed_free_agent",
                               "rule_5", "waiver")
        _tx_method_map = {
            "waiver_claim": "waiver", "waiver": "waiver",
            "rule_5": "rule_5", "rule_5_return": "rule_5",
            "contract_purchase": "contract_purchase",
            "signed_free_agent": "free_agent",
        }
        # Original draft/IFA team — used to suppress the post-draft
        # contract-signing transaction (which MLB's feed emits as the same
        # SFA/SGN typeCode used for genuine FA signings). Thomas White was
        # drafted by MIA in 2023 and got an SFA row two weeks later signing
        # WITH MIA; without this gate that row promotes to
        # current_acquisition.method = "free_agent" and the detail page
        # renders a redundant "Current org · Free-agent signing" panel.
        _acq_method = (acq or {}).get("method")
        _acq_team_code = canonical_org((acq or {}).get("team_name"))
        for tx in (transactions_by_player or {}).get(p.player_key, []):
            kind = tx.get("kind")
            if kind not in _cross_org_tx_kinds:
                continue
            to_code = (canonical_org(tx.get("to_team_name"))
                       or canonical_org(tx.get("to_team")))
            from_code = (canonical_org(tx.get("from_team_name"))
                         or canonical_org(tx.get("from_team")))
            if not to_code or to_code == from_code:
                continue
            if to_code not in _MLB_ORG_CODES_FOR_OVERRIDE:
                continue
            # Suppress the post-draft / post-IFA contract signing — the
            # original acquisition record already captures it.
            if (kind == "signed_free_agent"
                    and _acq_method in ("draft", "international_fa")
                    and _acq_team_code is not None
                    and to_code == _acq_team_code):
                continue
            _all_acq_events.append({
                "kind": _tx_method_map.get(kind, "trade"),
                "date": tx.get("date"),
                "from_org": from_code,
                "to_org": to_code,
                "description": tx.get("description"),
            })
        _all_acq_events.sort(key=lambda e: e.get("date") or "")

        # Classify method from the latest unified event when available
        # (catches waiver-then-no-trade cases like Otto Lopez), otherwise
        # fall back to the original trade-only classifier for backwards
        # compatibility with the rest of the pipeline.
        if _all_acq_events:
            latest_acq = _all_acq_events[-1]
            if latest_acq["kind"] != "trade":
                current_acq_method = latest_acq["kind"]
            else:
                current_acq_method = _classify_current_acquisition(filtered_trades, acq)
        else:
            current_acq_method = _classify_current_acquisition(filtered_trades, acq)

        display_org = _display_org(p, filtered_trades)
        # Surface the specific event that brought them to their current
        # org. Picks the latest from the unified events list (trade or
        # transaction), then runs the result through _collapse_bounce_chain
        # so short-tenure intermediates (e.g., Otto Lopez's 51-day SFG
        # stopover en route from TOR to MIA) get rolled up to the
        # stable prior org. The full bounce path is preserved on
        # `bounce_via` for the detail-page tooltip.
        current_acq_event = None
        if current_acq_method not in ("draft", "international_fa", "unknown") and _all_acq_events:
            latest_event = _all_acq_events[-1]
            collapsed = _collapse_bounce_chain(latest_event, _all_acq_events)
            current_acq_event = {
                "date":        collapsed.get("date"),
                "from_org":    collapsed.get("from_org"),
                "to_org":      collapsed.get("to_org"),
                "description": collapsed.get("description"),
            }
            if collapsed.get("bounce_via"):
                current_acq_event["bounce_via"] = collapsed["bounce_via"]
        # mlbam_id at top-level so every consumer (UI headshot, link to
        # MLB.com, etc.) can read it without digging into the statline —
        # graduates / inactives sometimes lack a current-season statline
        # but still need their MLB headshot to render.
        _mlbam = player_ids.get(p.player_key)
        if _mlbam is None and sl_out:
            _mlbam = sl_out.get("mlbam_id")
        if _mlbam is None:
            # Durable player_photos binding (see _durable_ids_by_key above).
            _mlbam = _durable_ids_by_key.get(p.player_key)
        _latest_played_level = None
        for _g in ((scm or {}).get("recent_games") or []):
            _lvl = str((_g or {}).get("level") or "").strip()
            if _lvl:
                _latest_played_level = _lvl
                break
        _level_changes = _level_changes_with_debut(p.player_key)
        _latest_level_event = None
        for _lc in _level_changes:
            _lc_date = _lc.get("date") or ""
            if _lc_date and _lc_date > date.today().isoformat():
                continue
            if _lc.get("to_level"):
                _latest_level_event = _lc
        _statline_level = sl_out.get("level") if sl_out else None
        _current_level = None
        if p.status == "debuted" or (rs.get("mlb_debut_date")):
            _debut_date_current = rs.get("mlb_debut_date") or p.debut_date or ""
            _post_debut_move = None
            _debut_event = None
            for _lc in reversed(_level_changes):
                _lc_date = _lc.get("date") or ""
                if (
                    _lc.get("kind") in {"promotion", "demotion"}
                    and _lc.get("to_level")
                    and _debut_date_current
                    and _lc_date > _debut_date_current
                ):
                    _post_debut_move = _lc
                    break
                if _debut_event is None and _lc.get("kind") == "debut" and _lc.get("to_level"):
                    _debut_event = _lc
            _current_level = (
                _latest_played_level
                or ((_post_debut_move or {}).get("to_level"))
                or ((_debut_event or {}).get("to_level"))
                or "MLB"
            )
        else:
            _current_level = (
                _latest_played_level
                or roster_level_by_key.get(p.player_key)
                or ((_latest_level_event or {}).get("to_level"))
                or _statline_level
            )
        _live_signal = _live_signal_for_player(
            statline=sl_out,
            statcast=scm,
            zone=zm,
            health=health,
            il_row=il_status.get(p.player_key) or {},
            source_events=source_events_by_key.get(p.player_key, []),
        )
        _source_events = source_events_by_key.get(p.player_key, [])
        _event_priority = {
            "statcast_by_age_standout": 0,
            "injury_note": 1,
            "top100_rank": 2,
            "top100_movement": 3,
            "top100_joined": 4,
            "top100_dropped": 5,
        }
        def _event_date_sort(ev: dict) -> int:
            raw = str(ev.get("event_date") or "").replace("-", "")
            try:
                return -int(raw)
            except ValueError:
                return 0
        _source_events_export = sorted(
            _source_events,
            key=lambda ev: (
                _event_priority.get(ev.get("event_type"), 9),
                _event_date_sort(ev),
            ),
        )[:10]
        # v34/v35 — baked engine surplus: timing-aware expected SV ($M) + the
        # outcome-bucket probabilities + the disagreement-widened distribution +
        # (for debuted players) the trade/total/realized split + WAG. The frontend
        # reads this block directly instead of recomputing a timing-naive curve.
        _is_pitcher_vf = _vf_is_pitcher_position(p.position)
        # bughunt F3 (2026-07-23): a no-ETA prospect used to fall through to the
        # engine's default_eta_years (0.0 = debut-now pricing) here while
        # efv_score priced the SAME row's eFV surplus at 1.0 - two adjacent
        # dollar columns on different assumed timing (237 live rows). Both
        # writers now share PROSPECT_ETA_FALLBACK_YEARS.
        _eta_yrs = _eta_years_from(eta, date.today().year)
        if _eta_yrs is None:
            _eta_yrs = PROSPECT_ETA_FALLBACK_YEARS
        _surplus = _build_surplus_payload(
            latest_fv, _is_pitcher_vf, p.position,
            age=age, eta_years=_eta_yrs,
            fv_dispersion=(p.points[-1].fv_stddev if p.points else None))
        # WAG baseline = the player's eFV grade AT DEBUT, and from 2026-08-12 that
        # is literal rather than incidental.
        #
        # It used to read whatever xfv_grade the join happened to serve, which was
        # the debut-anchored grade only because run_backgrade could not produce
        # anything else. The rookie-window unlock lets a graduate's served grade
        # move on new source grades, and WAG must NOT follow it: efv_model's
        # wag_calibration regresses on this block, its regressand already sees the
        # future, and the only thing containing that leak is the pinned lambdas.
        # Letting the unlock feed it would put a moving target inside the one
        # coupling nobody has re-derived.
        #
        # `xfv_grade_at_debut` is emitted by run_backgrade for exactly this; the
        # served grade is the fallback for rows written before it existed (and for
        # every non-graduate, where the two are the same number anyway).
        _xrow = _xfv_by_key.get(p.player_key) or {}
        _wag_fv = _xrow.get("xfv_grade_at_debut", _xrow.get("xfv_grade"))
        if WAG_UNIFIED and p.player_key in _debuted_memo:
            # Baked ONCE: the farm rollup already built this block and graded the org
            # on it, so the card serves that same object (audit F25).
            _debuted_value = _debuted_memo[p.player_key]
        else:
            _debuted_value = (
                _build_debuted_payload(
                    latest_fv, _is_pitcher_vf, p.position, age=age,
                    career_war=career_war.get(p.player_key),
                    roster_status=roster_status.get(p.player_key),
                    contract=contracts_by_key.get(p.player_key),
                    career_stats=career_stats.get(p.player_key),
                    wag_fv=_wag_fv)
                if p.status == "debuted" else None)
        payload = {
            "player_key": p.player_key,
            "player_name": p.player_name,
            "mlbam_id": _mlbam,
            "position": p.position,
            "org": display_org,
            "status": p.status,
            # Current roster/assignment level for display context. Kept
            # separate from statline.level, which remains the level where
            # the exported season stat row was accumulated. This avoids
            # showing a promoted player as "AA" when their latest stats are
            # AA but their current affiliate is AAA.
            "current_level": _current_level,
            "statline_level": _statline_level,
            # v20 — Consolidated to a single `debut_date` field. Was a
            # pair (graduation_date + mlb_debut_date) under the old
            # threshold-based graduation model. With debut_date now
            # sourced entirely from mlb_debut_date (per the v20
            # simplification), the two fields carried the same value
            # for every player, so the second one is gone. Frontend
            # reads `debut_date` exclusively.
            "debut_date": _display_graduation_date(p) if p.status == "debuted" else p.debut_date,
            "birth_date": bd,
            "age": age,
            # THE board rank: position in the _active_key ordering, which sorts on the
            # RAW eFV grade (BOARD_GRADE_FIELD) — the same number the board displays.
            # Plus the player's position within their org under that same ordering.
            # None for graduated/inactive (the maps below only carry actives).
            "overall_rank": overall_rank_by_key.get(p.player_key),
            # De-noised "since last real change" board-rank movement over the raw-eFV
            # rank. None until POST-EPOCH rank history accrues (BOARD_RANK_BASIS_EPOCH),
            # when the move is within the dead-band, or when the player sits in a deep
            # tie block (_rank_meaningful); the eFV grade move on `stock` carries the
            # immediate signal. Best-effort.
            "rank_movement": (_rank_movement(p.player_key,
                                             overall_rank_by_key.get(p.player_key),
                                             _ser_board_grade)
                              if p.player_key in overall_rank_by_key else None),
            # This player's own overall_rank at the previous post-epoch snapshot (same
            # field, one run back — never a re-sort on a different key). Drives the
            # rank-trend arrow. None for players new to the board, for every player until
            # two post-epoch snapshots exist, and for tie-block players whose rank number
            # is tiebreak order rather than grade order.
            "prev_overall_rank": (prev_overall_rank_by_key.get(p.player_key)
                                  if (_rank_meaningful(_ser_board_grade)
                                      and p.player_key in overall_rank_by_key) else None),
            "org_rank": org_rank_by_key.get(p.player_key),
            "org_rank_total": org_size_by_key.get(p.player_key),
            # PV-07: has any label source (storage.PROV_SECTION_LABEL_SOURCES) ever given
            # this active row an opinion? False puts it in the PROSPX section "Not yet
            # graded by any source" with no shared rank. None off the active list.
            "source_graded": _source_graded_by_key.get(p.player_key),
            # The non-model terms of THE board ordering for this row (consensus fallback
            # grade, '+' flag, TBS proxy, avg_rank, org key). Read by storage.rebake_board_ranks
            # only, never displayed; None for graduated / inactive rows.
            "board_key_tail": board_key_tail_by_key.get(p.player_key),
            "age_vs_level": {"tier": avl.tier, "diff": avl.diff},
            "fv_high": p.fv_high,
            "fv_high_label": p.fv_high_label,
            "fv_high_date": p.fv_high_date,
            "fv_low": p.fv_low,
            "fv_low_label": p.fv_low_label,
            "fv_low_date": p.fv_low_date,
            "fv_open": p.fv_open,
            "fv_close": p.fv_close,
            "surplus": _surplus,
            "debuted_value": _debuted_value,
            # v26 — '+' upside flag on the latest observation. Used by
            # frontend sort comparators (42+ ranks above 42 < 43) and
            # for rendering "42+" on aggregate displays anchored on fv_close.
            "fv_close_plus": bool(getattr(p, "fv_close_plus", False)),
            # Unsnapped post-shrinkage FV at the latest snapshot. Lets the
            # UI distinguish a "high 40" (e.g. 42.3) from a "low 40"
            # (e.g. 37.8) — both round to the 40 tier label but the raw
            # value clarifies how much the shrinkage moved them.
            "fv_close_raw": (round(p.points[-1].consensus_fv_raw, 2)
                             if p.points else None),
            # Total (source, snapshot_date) instances where a published FV
            # exists across the player's full history. When 1, the FV
            # consensus is pulled toward FV 35 (Bayesian shrinkage); when
            # ≥2 the player is "well-observed" and escapes the pull —
            # including single-source players who've been re-graded over
            # multiple snapshots. Frontend `is-single-source` outline +
            # corner mark read off this field.
            "fv_total_instances": getattr(p, "fv_total_instances", 0),
            # `stock` is stamped below by the movement engine (compute_movement),
            # with consensus.stock_movement as the exception-path fallback.
            # CONSENSUS-SIDE live form / external-list movement (see the
            # consensus_live_score block in export_timeseries_json). Its `delta` is
            # dominated by scouting-list events (BA Top 100 moves), NOT by the eFV
            # model. It is a sidecar signal only: it never enters overall_rank.
            "live_signal": _live_signal,
            "source_events": _source_events_export,
            "player_news": player_news_by_key.get(p.player_key, []),
            "statline": attach_pitch_rate_statline(sl_out, _mlbam, _pitch_rate_lookup),
            "current_season_statlines": _current_season_statlines,
            "stat_flags": flags,
            # Scouting tool grades — consensus per-tool 20-80 grades,
            # three composites (offensive/defensive/overall for hitters;
            # stuff/command/overall for pitchers), and X+ indices (100 =
            # cohort mean, 10 pts = 1 stdev). `publishing_sources` lists
            # the sources that contributed grades. Empty/None when no
            # source has published tools for this player.
            "tools": tools_payload,
            # Green/red callouts for plus-plus or well-below-average
            # tools. Same {direction, stat, value, ...} shape as
            # stat_flags so one frontend renderer handles both.
            "tool_flags": tool_flags,
            # 12-month injury aggregate + Tommy-John flag. Drives the
            # IL-section roster, the "Post-TJ" chip on the prospect
            # header, the Injury-prone red flag, and the ETA-delay
            # adjustment in eta.estimate_eta.
            "health_profile": health,
            # Non-trade transactions: waiver claims, releases, DFAs,
            # contract purchases, Rule 5 selections/returns, FA signings.
            # Trades stay in their own `trades` field with stricter
            # cross-org dedup logic (see trades.py + reconcile_trades).
            # Each row is decorated with from_org / to_org (canonical
            # 3-letter codes) so farm-page consumers can filter events
            # that touch a given org without re-resolving team names.
            "transactions": [
                {**tx,
                 "from_org": canonical_org(tx.get("from_team")) if tx.get("from_team") else None,
                 "to_org":   canonical_org(tx.get("to_team"))   if tx.get("to_team")   else None}
                for tx in transactions_by_player.get(p.player_key, [])
            ],
            "pitch_arsenal": pa,
            "zone_metrics": zm,
            "statcast_metrics": scm,
            "sabermetrics": sm,
            "trades": filtered_trades,
            "career_stats": career_stats.get(p.player_key, []),
            # Aggregated FanGraphs WAR for everyone who's touched MLB —
            # populated by the bulk career-WAR fetch in run_monthly. Carries
            # {seasons: {year: war}, career_war, war_per_yr,
            # war_seasons_count, source}. Empty dict when no MLB time on
            # file (every active prospect who hasn't debuted). The per-season
            # exposure maps stay server-side (_served_career_war). Since the fWAR
            # label epoch (2026-10-03) this block is the DISPLAYED series, eWAR v2
            # (owner answer EPOCH-Q4); the stored LABEL series rides beside it as
            # `career_war_label` for the consumers that price or train on WAR.
            "career_war": _served_career_war(career_war.get(p.player_key, {})),
            "career_war_label": _label_career_war(career_war.get(p.player_key, {})),
            # Present only where the identity screen removed career-WAR seasons the
            # row's own mlbam id never played (another player's history on this slug).
            **({"identity_screen": _cw_foreign[p.player_key]}
               if p.player_key in _cw_foreign else {}),
            # Within-season + cross-season level changes derived from the
            # MLB Stats API per-player transactions endpoint. One record
            # per real level transition (lateral affiliate swaps filtered
            # out). The earliest MLB promotion is tagged as the MLB debut
            # (kind == "debut") so the transaction-history block can
            # render it distinctly. Drives promotion/demotion markers on
            # the FV chart.
            "level_changes": _level_changes,
            # MLB roster status: debut, options used, 40-man state,
            # accumulated service time, arb cycle bucket. Empty dict if
            # the player has not yet appeared in the majors.
            # R5.3 (2026-08-04): `mlb_seasons` is backfilled from the
            # career_war season map when the roster feed left it empty
            # (782 of 2,681 debuts rows), stamped
            # mlb_seasons_source = "career_war" so the derived list stays
            # distinguishable from a roster-fed one. This is what makes the
            # trade board's inactive-drop rule structurally able to see a
            # retired-plus-current fused key instead of needing a guard to
            # rescue it after the fact. See
            # _roster_status_with_derived_seasons.
            "roster_status": _roster_status_with_derived_seasons(
                roster_status.get(p.player_key), career_war.get(p.player_key)),
            "acquisition": acq,
            # How the player's CURRENT org acquired them. Powers the
            # acquisition filter on the main prospect list + farm
            # detail roster, and the "Acquired by <ORG>" line on the
            # prospect detail page when distinct from the original
            # acquisition.
            # v14 — Hoist event fields (date, from_org, to_org) up to
            # current_acquisition top-level so the Acquisitions PAGE
            # rendering doesn't have to dig through `.event` to find
            # them. Fixes the Perales/Bennett bug where one side's
            # trade rendered correctly but the other (whose fields
            # only existed under `.event`) showed "?".
            "current_acquisition": {
                "method":      current_acq_method,
                "event":       current_acq_event,
                "date":        (current_acq_event or {}).get("date"),
                "from_org":    (current_acq_event or {}).get("from_org"),
                "to_org":      (current_acq_event or {}).get("to_org"),
                "description": (current_acq_event or {}).get("description"),
            },
            # Spotrac-sourced active contract. Populated only when the
            # player has a current MLB contract on file (active roster /
            # IL / dead-money tables on Spotrac's yearly team page).
            # Absent for prospects still in MiLB or anyone Spotrac
            # doesn't list. Drives the realized-surplus calc on
            # graduate detail pages — current-year salary slot reads
            # from `aav_usd` when present; prior seasons still use the
            # league-min + arb-fraction model.
            **({"current_contract": {
                "aav_usd":         _ct.get("aav_usd"),
                "salary_usd":      _ct.get("salary_usd"),
                "total_usd":       _ct.get("total_usd"),
                "salary_by_year":  _ct.get("salary_by_year"),
                "years":           _ct.get("years"),
                "years_remaining": _ct.get("years_remaining"),
                "signed_through":  _ct.get("signed_through"),
                "spotrac_id":      _ct.get("spotrac_id"),
                # v17 — new fields supporting the detail-page Contract panel.
                "extension_signed": _ct.get("extension_signed"),
                "source":          _ct.get("source") or "spotrac",
            }} if (_ct := contracts_by_key.get(p.player_key)) else {}),
            # Current IL stint, if any. Powers the IL badge on prospect
            # cards + the injury duration line on the detail page.
            # Empty dict (not None) when the player is healthy — the UI
            # treats `is_on_il` falsy as healthy regardless.
            "il_status": il_status.get(p.player_key, {}),
            "eta": {
                "year": eta.eta_year,
                "confidence": eta.confidence,
                "base_years": eta.base_years,
                "perf_adj": eta.perf_adj,
                "age_adj": eta.age_adj,
                "fv_adj": eta.fv_adj,
                "health_adj": eta.health_adj,
                # H1/H2 split — `season_phase` is one of "pre_break",
                # "post_break", "offseason"; `half_season_adj` is the
                # actual year-adjustment applied (the league-baseline -0.25
                # in post_break; the org scaling was removed 2026-09-30).
                # All surface on the ETA panel.
                "half_season_adj": eta.half_season_adj,
                "season_phase": eta.season_phase,
                # Per-org promotion-phase tendency context. Since the
                # multipliers left the served call (owner answer ETA-3,
                # 2026-09-30) the rates are None and the weight is 1.0 on
                # every row; the keys stay so older readers keep their shape.
                "org_promo_h1_rate": eta.org_promo_h1_rate,
                "org_promo_h2_rate": eta.org_promo_h2_rate,
                "org_promo_weight":  eta.org_promo_weight,
                # v31.8 — Half-year bucket ("early" = Apr-Jun debut window
                # within eta_year; "late" = Jul-Sep). Combines fractional
                # ETA distance + current-level bias.
                "half":              eta.eta_half,
                # True when the calendar floor rolled a current-year ETA to next
                # year's early window because the regular season is over.
                "season_end_roll":   bool(getattr(eta, "season_end_roll", False)),
                # FanGraphs-blend arm, present ONLY when eta.ETA_FG_BLEND_ARM served a
                # blend for this prospect (absent while the flag is off).
                **({"fg_blend_arm": eta.fg_blend_arm,
                    "fg_eta_year": eta.fg_eta_year,
                    "champion_year": eta.champion_eta_year}
                   if getattr(eta, "fg_blend_arm", None) else {}),
            },
            # Per-tool lifetime delta map (first observation → latest).
            # `{hit: {delta, first, last, first_date, last_date, n_obs}, ...}`
            # Tools with <2 consensus observations are omitted. Powers the
            # +N / -N delta chips in the prospect-detail Tools section and
            # the "Tool development" wide card.
            "tool_deltas": _compute_tool_deltas([
                {"snapshot_date": pt.snapshot_date,
                 "tools_consensus": pt.tools_consensus}
                for pt in p.points
            ]),
            # `breakout_score` removed 2026-05 — replaced with WAG-anchored
            # BOOM / BUST graduate labels (see boom_label below for grads).
            # Active prospects no longer get a trajectory composite; the
            # "Wide FV spread" filter chip remains for cross-source variance.
            "points": [
                {
                    "snapshot_date": pt.snapshot_date,
                    "interval_label": pt.interval_label,
                    "consensus_fv": pt.consensus_fv,
                    "consensus_fv_label": pt.consensus_fv_label,
                    "consensus_fv_raw": pt.consensus_fv_raw,
                    "consensus_fv_pre_shrinkage": pt.consensus_fv_pre_shrinkage,
                    # v26 — '+' upside flag for this point. consensus_fv_label
                    # already includes a "+" suffix when this is True; the
                    # separate boolean lets sort comparators tie-break.
                    "consensus_fv_plus": bool(getattr(pt, "consensus_fv_plus", False)),
                    # Point-in-time org for the Time Machine (the org as of this
                    # snapshot, not "now"). None on a gap → neutral placeholder.
                    "org": getattr(pt, "org", None),
                    "shrinkage_weight": pt.shrinkage_weight,
                    "avg_rank": pt.avg_rank,
                    "avg_fv": pt.avg_fv,
                    "avg_fv_n": pt.avg_fv_n,
                    "rank_implied_fv": pt.rank_implied_fv,
                    "sources_contributing": pt.sources_contributing,
                    "per_source": pt.per_source,
                    "fv_min": pt.fv_min,
                    "fv_max": pt.fv_max,
                    "fv_spread": pt.fv_spread,
                    "fv_stddev": pt.fv_stddev,
                    # Per-tool consensus + per-tool spread on this point.
                    # `per_source[src].tools` is already carried inside
                    # per_source above, so the UI can show "Pipeline says
                    # 60 hit / FanGraphs says 55 hit" without joining.
                    "tools_consensus": dict(pt.tools_consensus) if pt.tools_consensus else {},
                    "tools_spread": dict(pt.tools_spread) if pt.tools_spread else {},
                }
                for pt in p.points
            ],
        }

        # v47 - baked Top-100 pedigree boolean (omitted when False so the
        # key set stays lean). Computed above from the exact label walk
        # bayes_trade_value._has_top100_pedigree performed against
        # tools.history + tools.source_history; bayes now prefers this
        # flag and keeps the walk only as a fallback for pre-v47 artifacts.
        if _top100_pedigree:
            payload["top100_pedigree"] = True

        # DS-12 (bug B7): a graduate's debut-date basis, and whether the day is
        # a synthesized placeholder rather than a game date. Graduates only.
        if p.status == "debuted":
            _dd_basis = _display_graduation_basis(p)
            payload["debut_date_basis"] = _dd_basis
            payload["debut_date_is_placeholder"] = _dd_basis in PLACEHOLDER_DEBUT_BASES

        # ── position_observed (2026-07-30, owner decision). The most-played non-DH
        # MiLB position, published BESIDE `position` and never instead of it. See the
        # sidecar load at the top of this function for why `position` stays on the
        # FanGraphs forward-projection.
        #
        # OMITTED, not null, when there is no observation - 148 served non-pitcher
        # rows plus every pitcher. A reader's `.get("position_observed")` returns None
        # either way, and omitting keeps ~2,500 null keys out of the payload.
        #
        # This field is now the intended input for the consumers that are asking an
        # OBSERVED question ("who else has played this position at this age", "is this
        # man a catcher") rather than a forecast one ("what will he be worth on the
        # trade market"). Backend consumers already repointed: the D-Tool catcher
        # weighting above. Still on the projection ON PURPOSE: positional scarcity
        # dollars, the org depth chart, farm positional need, and `position` itself.
        # The frontend cohorts (archetype comps, similar prospects, peer percentile,
        # RPS+ cell) are owed follow-ups recorded in
        # docs/efv-2026-07-30/POSITION_ROLE_GATE.md - including the reconciliation of
        # prospx displayPosition(), which today MUTATES p.position in place from this
        # same sidecar for outfield slots and so can already disagree with the backend.
        _obs_pos = _observed_pos.get(p.player_key)
        if _obs_pos:
            payload["position_observed"] = _obs_pos

        # Boom / Bust label — graduates only. Computed post-payload-build
        # since _compute_boom_bust reads career_war + career_stats fields
        # that were just stamped on the dict. Active prospects get None
        # (label only meaningful after the prospect has graduated AND
        # cleared the sample floor).
        if p.status == "debuted":
            try:
                if WAG_UNIFIED:
                    payload["boom_label"] = (((_debuted_value or {}).get("wag") or {})
                                             .get("boom_label") or "unsettled")
                else:
                    payload["boom_label"] = _compute_boom_bust(payload)
            except Exception:
                payload["boom_label"] = "unsettled"
        else:
            payload["boom_label"] = None

        # De-noised movement engine. compute_genuine_movement measures the
        # most-recent SAME-SOURCE consensus step (only sources grading the
        # player at both endpoints count), so panel-composition changes and
        # lone-outlier re-grades no longer masquerade as movement; on-field
        # performance is the backup. Reads points[].per_source /
        # sources_contributing / fv_spread / shrinkage_weight + statline /
        # career_stats — all stamped on the payload above. Output is a
        # backward-compatible superset of compute_movement's `stock` shape.
        # Fallback chain on failure: compute_genuine_movement →
        # compute_movement (bucket engine) → stock_movement (legacy FV delta).
        try:
            from movement import compute_genuine_movement, xfv_movement
            _stock = compute_genuine_movement(payload)
            # Owner: movement is the eFV delta where eFV has a trajectory. Override the
            # headline move (direction/delta/basis/endpoints) with the eFV "since last real
            # change" step; keep the consensus perf/skills drivers as supporting context.
            # Falls back to the consensus same-source step when eFV has no history.
            # BASIS GATE (2026-07-30): and also when the series on disk was built on a
            # different board basis than the one being served, which is a grade-scale
            # transition publishing itself as player movement. See
            # storage.xfv_history_is_on_board_basis for why the BOARD_RANK_BASIS_EPOCH gate
            # cannot reach this signal. Resolved once per export, not per player.
            _xm = xfv_movement(_xfv_series(p.player_key)) if _xfv_hist_ok else None
            if _xm:
                _stock.update(_xm)
            payload["stock"] = _stock
        except Exception:
            log.exception("compute_genuine_movement failed for %s — falling "
                          "back to the bucket / legacy stock signal", p.player_key)
            try:
                from spotlights import compute_movement
                payload["stock"] = compute_movement(payload)
            except Exception:
                payload["stock"] = stock_movement(p)

        return payload

    cutoff = _inactive_cutoff()

    # Reclassification rules:
    #   1. Status='debuted' from snapshots or auto-graduation → grads.
    #   2. On IL right now → stays active (badge tells the story).
    #   3. Both signals stale (FV cutoff + no games in current/previous
    #      calendar year):
    #        - any MLB game in current/previous year → grads (effective
    #          graduation we missed because rookie-threshold rule hasn't
    #          fired yet)
    #        - otherwise → inactives
    #   4. Anything else → active.
    # Without (2), legitimately-stale-due-to-injury prospects (Painter,
    # for example) would tumble into inactive — defeating the IL badge.
    today = date.today()
    play_cutoff_year = today.year - 1  # must have played current OR last year
    # v19 — Two-season stale-play threshold. Independent of FV staleness:
    # any prospect who has played professionally before AND hasn't
    # appeared in a stat line for 2+ calendar seasons is inactive
    # REGARDLESS of whether a ranking source updated their FV recently.
    # Single-source rankers continuing to grade an effectively-retired
    # 2023 prospect won't keep them in the active pool.
    TWO_SEASON_INACTIVE_YEARS = 2
    # v19 — Stale-IL threshold. The MLB API sometimes leaves
    # `is_on_il=true` after a quiet reinstatement; an IL placement older
    # than ~18 months is presumed stale and forces inactive regardless
    # of the IL flag. 540 days is conservative — even the longest
    # legitimate chained 60-day stints rarely cross that.
    STALE_IL_DAYS = 540
    # v19 — Minimum-FV floor for the active pool. Wilmer Flores et al.
    # were leaking through with FV 21 (likely upstream data noise from
    # a single ranking source). Real prospects publish at FV ≥ 35; we
    # set the floor at 30 to give a small buffer for grade-rounding /
    # source-noise but still excise the obvious garbage. Players below
    # this floor fall into `inactives` and stay out of farm rollups.
    MIN_PROSPECT_FV = 30

    _phase_done("joins")
    # ── HISTORICAL-LEAK FIX (active-prospect recency ceiling) ─────────────
    # A player not ranked by ANY prospect source in HARD_FV_STALE_YEARS years
    # has aged out of prospect status → INACTIVE regardless of whether they're
    # still grinding in the minors or sitting on an IL. The fv_stale gate below
    # only deactivates stale players who ALSO stopped playing (`fv_stale AND
    # play_stale`), which let players who keep playing affiliated ball linger in
    # the active pool indefinitely with a years-old grade. The 2017-2020
    # historical backfill exposed this: it introduced players whose ENTIRE
    # ranking history is 5+ years old (still active in MiLB, never debuted) →
    # they defaulted to "active" and leaked into current farm pools, shifting
    # farm rankings. This ceiling makes the current pool independent of any
    # historical ingestion (past OR future) — a purely-historical cohort can
    # never enter the current active pool. (Time Machine / backtest read the
    # full snapshot history directly and are unaffected.)
    # Calendar-year basis (not a rolling day cutoff): a grade dated in the
    # current year OR within HARD_FV_STALE_YEARS prior calendar years keeps a
    # prospect active; anything older = aged out. Calendar years match how
    # prospect sources actually publish (annual preseason + midseason cycles),
    # and the rolling cutoff had a boundary artifact - an Aug-2023 grade
    # survived a "3 years ago" test that a Jan-2023 grade failed. Lowered 5 -> 2
    # (2026-06): the old 5y ceiling only caught the obvious 2017-2020 historical
    # backfill and let still-grinding prospects linger on a years-old grade
    # (e.g. Cristopher Larez, last NYM grade 2023-08). Sources re-grade every
    # prospect of note at least annually, so 2+ idle calendar years = the
    # industry has dropped them.
    HARD_FV_STALE_YEARS = int(os.environ.get("HARD_FV_STALE_YEARS", "2"))
    hard_fv_min_year = today.year - HARD_FV_STALE_YEARS
    _audit_aged_out = 0

    actives: list[PlayerTimeseries] = []
    inactives: list[PlayerTimeseries] = []
    grads: list[PlayerTimeseries] = []
    # v19 — Audit counters surfaced via a one-line summary log after the
    # cascade completes so each rebuild reports cleanup magnitude.
    _audit_play2yr = 0
    _audit_stale_il = 0
    _audit_fv_play_stale = 0
    _audit_low_fv = 0

    for p in timeseries:
        # v20 — Definitive debut detection. If the MLB API has stamped
        # an mlbDebutDate on the player's roster_status, they're treated
        # as debuted regardless of whether any consensus snapshot has
        # flagged status='debuted'. This was the Waldschmidt bug —
        # he debuted 2026-05-08 (career_mlb_ab=0 because he was a
        # pinch-runner / late-inning sub) but no FG snapshot had marked
        # him as a graduate, so the actives pool kept him. mlb_debut_date
        # is the authoritative signal; AB/IP/active-roster-day thresholds
        # are no longer used.
        _rs_for_debut = (roster_status.get(p.player_key) or {})
        _api_debut = _rs_for_debut.get("mlb_debut_date")
        if _api_debut and p.status != "debuted":
            p.status = "debuted"
            p.debut_date = _api_debut
        # v23 — Outrighted prospects are also marked debuted (per user
        # directive). An outright requires the player to have been on
        # the 40-man roster, which makes them a non-prospect even if
        # they never played an MLB game. The debut_date falls back to
        # the outright date when no mlbDebutDate is on file.
        if p.status != "debuted":
            _tx_rows = (transactions_by_player or {}).get(p.player_key) or []
            _outright_dates = [tx.get("date") for tx in _tx_rows
                               if (tx.get("kind") or "").lower() == "outrighted"
                               and tx.get("date")]
            if _outright_dates:
                p.status = "debuted"
                # Use the EARLIEST outright (when player first cleared
                # waivers off the 40-man) as the debut-equivalent date.
                p.debut_date = p.debut_date or min(_outright_dates)
        if p.status == "debuted":
            grads.append(p)
            continue
        if not p.points:
            inactives.append(p)
            continue
        try:
            latest_date = date.fromisoformat(p.points[-1].snapshot_date)
        except ValueError:
            inactives.append(p)
            continue

        # v12 — MLB-affiliation gate applies to EVERY active candidate,
        # including IL'd players. Without this, "Office of the
        # Commissioner"-bucket players bypass the filter via the IL
        # short-circuit below. Uses the same resolver the display layer
        # uses so a player whose displayed org would be "Office of the
        # Commissioner" can't sneak through.
        _resolved_org = _active_display_org(p)
        if _resolved_org not in MLB_30_ORGS:
            inactives.append(p)
            continue

        # ── Active-prospect recency ceiling ────────────────────────────────
        # No source has graded this player in HARD_FV_STALE_YEARS+ calendar
        # years → aged out of prospect status → INACTIVE, even if still playing
        # affiliated ball or sitting on an IL. This is the ONE FV-staleness gate
        # that fires regardless of play: the softer fv_stale gate below requires
        # play-staleness too, which let still-grinding prospects linger forever
        # on a years-old grade (the Cristopher Larez case - last graded 2023,
        # still in the minors). Takes precedence over the IL bypass + the softer
        # gates, and also subsumes the 2017-2020 historical-backfill leak this
        # ceiling first fixed. (Time Machine / backtest read the full snapshot
        # history directly and are unaffected.)
        if latest_date.year < hard_fv_min_year:
            inactives.append(p)
            _audit_aged_out += 1
            continue

        # v19 — Compute play-staleness up front so the new gates can use
        # it (was previously computed AFTER the IL bypass, which let
        # 2-year-inactive IL holdouts slip through).
        career = (career_stats or {}).get(p.player_key, []) or []
        last_played_year = max(
            (int(row.get("season") or 0) for row in career),
            default=0,
        )
        play_stale = last_played_year < play_cutoff_year
        play_2yr_stale = (
            last_played_year > 0
            and (today.year - last_played_year) >= TWO_SEASON_INACTIVE_YEARS
        )

        # v19 — Minimum-FV floor. Anything below MIN_PROSPECT_FV is
        # almost certainly upstream data noise (single ranking source
        # mis-parsing a non-prospect like Wilmer Flores at FV 21).
        # The latest snapshot's consensus_fv_raw is the canonical
        # current grade. Players below the floor are inactives.
        try:
            latest_fv = float(p.points[-1].consensus_fv_raw or 0)
        except (AttributeError, TypeError, ValueError):
            latest_fv = 0.0
        if latest_fv > 0 and latest_fv < MIN_PROSPECT_FV:
            inactives.append(p)
            _audit_low_fv += 1
            continue

        # v23 — Age-cap gate. A player aged ≥30 with sub-prospect FV
        # (<45) is almost always a same-name MLB-veteran shadow or a
        # AAA journeyman whose stale FG snapshot keeps surviving the
        # other gates. Cayne Ueckert / Julian Garcia / Curtis Taylor /
        # Tanner Kiest were the canaries — all FV 38-39, age 30-32, no
        # current MLB time → quad-A depth, not prospects. The 45-FV
        # threshold is high enough to preserve legitimate aged
        # late-bloomers (KBO transfers etc.) since those typically
        # publish at FV 45-50.
        _bd_for_age = birth_dates.get(p.player_key)
        _age_for_gate = compute_age_decimal(_bd_for_age) if _bd_for_age else None
        if (_age_for_gate is not None and _age_for_gate >= 30
                and latest_fv > 0 and latest_fv < 45):
            inactives.append(p)
            _audit_low_fv += 1   # roll into low-FV bucket
            continue

        # v19 — Stale-IL force-inactive. Don't trust `is_on_il=true` when
        # the placement date is ancient (Scott Moss-style ghosts).
        _il = il_status.get(p.player_key) or {}
        il_force_inactive = False
        if _il.get("is_on_il") and _il.get("since"):
            try:
                since_dt = datetime.fromisoformat(_il["since"]).date()
                if (today - since_dt).days > STALE_IL_DAYS:
                    il_force_inactive = True
            except (ValueError, TypeError):
                pass
        if il_force_inactive:
            inactives.append(p)
            _audit_stale_il += 1
            continue

        # v19 — Two-season stale-play gate. Fires BEFORE the IL bypass:
        # a player who hasn't appeared in a box score in 2+ years is
        # effectively retired regardless of an "active IL" badge.
        if play_2yr_stale:
            inactives.append(p)
            _audit_play2yr += 1
            continue

        # On IL → stay active no matter how stale the FV is. The IL badge
        # on the player card explains the absence of recent updates and
        # avoids dumping injured-but-real prospects into the inactive bin.
        if _il.get("is_on_il"):
            actives.append(p)
            continue

        fv_stale = latest_date < cutoff

        # Stale + not playing → inactive. We do NOT treat "any MLB time
        # this year" as automatic graduation anymore — that flipped
        # cup-of-coffee players (sub-130-AB / sub-50-IP) to graduates as
        # soon as their FV reporters lost interest, which is wrong by
        # both MLB rookie-eligibility rules and the user-facing semantics.
        # The real graduation paths run earlier:
        #   * derive_roster_status sets rookie_exhausted when career MLB
        #     totals cross 130 AB / 50 IP OR when minor-league options
        #     are used up.
        #   * detect_graduations_from_career checks the same thresholds
        #     against the cached career payload.
        # Both feed auto_graduate_player in run_monthly, so by the time
        # we get here a legitimately graduated player already has
        # p.status == "debuted" and was peeled off above.
        if fv_stale and play_stale:
            inactives.append(p)
            _audit_fv_play_stale += 1
            continue
        actives.append(p)

    # v19 — Active-pool cleanup audit summary. Surfaces in the rebuild
    # log so the magnitude of each gate's contribution is visible at a
    # glance. Pre-dedup counts (mlbam_id dedup runs below).
    log.info(
        "active-pool cleanup: %d low-FV (<%d), %d aged-out (no grade in %d+ cal-yr), %d play-2yr-stale, "
        "%d stale-IL, %d FV+play stale -> actives=%d, debuts=%d, inactives=%d (pre-dedup)",
        _audit_low_fv, MIN_PROSPECT_FV, _audit_aged_out, HARD_FV_STALE_YEARS, _audit_play2yr,
        _audit_stale_il, _audit_fv_play_stale,
        len(actives), len(grads), len(inactives),
    )

    # v19 — mlbam_id dedup pass. The pipeline never deduped on
    # canonical id, so prospects with spelling-variant player_keys
    # (e.g. accent vs no-accent, "Jr." sometimes present) could occupy
    # two slots in the active pool. Collapse any pair sharing an
    # mlbam_id; tiebreaker = most-recent snapshot date wins. Players
    # without an mlbam_id (rare — pre-debut IFAs, scout-only entries)
    # bypass dedup via a unique sentinel key. mlbam_id lookup comes
    # from the player_ids dict (caller-supplied) since PlayerTimeseries
    # itself doesn't carry the id.
    def _dedup_by_mlbam(bucket: list[PlayerTimeseries], label: str) -> list[PlayerTimeseries]:
        by_mlbid: dict = {}
        drop_count = 0
        for cand in bucket:
            # Resolve the MLBAM id the SAME way _serialize does — fall back to the
            # statline's mlbam_id when player_ids lacks the key. Without this,
            # name-only "__noid" variant records (whose id is resolved later, at
            # serialization) bypass the dedup and the same player is double-counted
            # in the pool, org counts, rankings, and surplus.
            mid = (player_ids.get(cand.player_key) if player_ids else None) \
                  or ((statlines or {}).get(cand.player_key) or {}).get("mlbam_id")
            if not mid:
                by_mlbid[("nokey", cand.player_key)] = cand
                continue
            existing = by_mlbid.get(mid)
            if existing is None:
                by_mlbid[mid] = cand
                continue
            # Keep the RICHER record (more snapshots), tie-broken by recency, so
            # the fuller multi-source entry wins over a sparse variant.
            ex_score = (len(existing.points or []),
                        max((s.snapshot_date for s in (existing.points or [])), default=""))
            new_score = (len(cand.points or []),
                         max((s.snapshot_date for s in (cand.points or [])), default=""))
            if new_score > ex_score:
                keep, drop = cand, existing
            else:
                keep, drop = existing, cand
            by_mlbid[mid] = keep
            log.info(
                "dedup[%s]: mlbam_id=%s — keep %s (latest %s), drop %s (latest %s)",
                label, mid, keep.player_key,
                max((s.snapshot_date for s in (keep.points or [])), default=""),
                drop.player_key,
                max((s.snapshot_date for s in (drop.points or [])), default=""),
            )
            drop_count += 1
        if drop_count:
            log.info("dedup[%s]: dropped %d duplicate entries", label, drop_count)
        return list(by_mlbid.values())

    actives = _dedup_by_mlbam(actives, "actives")
    grads = _dedup_by_mlbam(grads, "graduates")
    inactives = _dedup_by_mlbam(inactives, "inactives")

    _phase_done("classify")
    # VAL_4 (owner answer FP2-4, 2026-09-25): development attribution. One org
    # calendar per player (dev_attribution.py; design in
    # docs/farm-attribution-2026-09-25/DEVELOPMENT_ATTRIBUTION.md) feeds the
    # graduate leaves, ToolDvM+ and DvM+ below and the dev_credit block on every
    # graduate row. None (a build failure, logged) keeps the current-club credit.
    _dev_attr = _build_dev_attribution(actives + grads + inactives, trades_by_player,
                                       acquisitions, _filter_real_trades)
    _tenure_tool_sums: dict[str, dict[str, list]] = {}
    _tenure_tool_sums_by_bucket: dict[str, dict[str, dict[str, list]]] = {}
    _phase_done("dev_attribution")
    # ── DATA-INTEGRITY GUARD (historical-leak tripwire) ───────────────────
    # The active pool must contain only current prospects: none graduated, none
    # FV-stale beyond the aged-out ceiling. This catches regressions if a future
    # change weakens the cascade or a new historical ingestion sneaks players in.
    # Non-fatal: log loudly so the rebuild surfaces it (the pipeline still runs).
    _leak_graduated = [p.player_key for p in actives if p.status == "debuted"]
    _leak_aged_out = [
        p.player_key for p in actives
        if p.points and p.points[-1].snapshot_date
        and int(p.points[-1].snapshot_date[:4]) < hard_fv_min_year
    ]
    if _leak_graduated or _leak_aged_out:
        log.error(
            "INTEGRITY GUARD: active pool leak detected — %d graduated, %d aged-out "
            "(no grade in %d+ cal-yr). Examples: %s",
            len(_leak_graduated), len(_leak_aged_out), HARD_FV_STALE_YEARS,
            (_leak_graduated + _leak_aged_out)[:5],
        )
    else:
        log.info("integrity guard: active pool clean (0 graduated, 0 aged-out).")

    # v29 — Statcast+ map: per-player composite indexed by player_key,
    # populated from the active prospect set (the side-aware pool). Has
    # to land here (post-dedup, pre-org-aggregation, pre-_serialize) so
    # downstream readers all see the same value:
    #   - estimate_eta inside _serialize → +/- 0.25y ETA nudge
    #   - _compute_breakout_flag: SC+ perf gate / stat-only gate, thresholds
    #     at _BREAKOUT_STATCAST_PLUS_GATE and _BREAKOUT_STAT_STATCAST_PLUS_GATE
    #   - org_map per-prospect loop → per-org SC+ aggregate (+ indicator
    #     counts) for the new farm-grade leaf
    # Players without tracked Statcast data are absent from the map →
    # .get() returns None, which downstream consumers treat as "no
    # signal" (no gate pass, no nudge).
    from statcast_plus import (
        build_pool as _sc_build_pool,
        compute_statcast_plus as _sc_compute,
    )
    def _sc_mini(p):
        return {
            "statline":         statlines.get(p.player_key),
            "zone_metrics":     zone_metrics.get(p.player_key),
            "statcast_metrics": statcast_metrics.get(p.player_key),
            "sabermetrics":     sabermetrics.get(p.player_key),
        }
    _sc_pool = _sc_build_pool(_sc_mini(p) for p in actives)
    _sc_plus_map: dict[str, int | None] = {}
    for _p in actives:
        _sc_plus_map[_p.player_key] = _sc_compute(_sc_mini(_p), _sc_pool)
    for _p in grads:
        _sc_plus_map[_p.player_key] = _sc_compute(_sc_mini(_p), _sc_pool)

    # #1 RE-SOURCE: for AAA prospects, OVERRIDE the opportunistic MLB-game-feed SC+ with the
    # cleaner Savant-MINORS AAA aggregate (full 2023+ coverage, park-consistent, is..tracked-
    # gated). The Savant pool is AAA-gated by construction, so this only touches players whose
    # highest MiLB level was AAA; everyone else keeps the game-feed value (or None). Best-effort
    # + cached -- a Savant outage leaves SC+ untouched. (A/FSL 2021+ is a future extension.)
    try:
        import arkmetric_forward_eval as _afe
        _cur_yr = date.today().year
        _aaa_analog: dict[tuple[int, str], float] = {}
        for _yr in range(_cur_yr, 2022, -1):                 # AAA Statcast tracking begins 2023
            for _sd in ("batter", "pitcher"):
                for _mid, _v in _afe.sc_analog_index(_yr, _sd).items():
                    _aaa_analog.setdefault((_mid, _sd), _v)  # most-recent AAA season wins
        if _aaa_analog:
            _n_resourced = 0
            for _p in actives + grads:
                _mid = player_ids.get(_p.player_key)
                if _mid is None:
                    _mid = (statlines.get(_p.player_key) or {}).get("mlbam_id")
                if _mid is None:
                    continue
                _sd = ("pitcher" if (_p.position and _p.position.split("/")[0] in PITCHER_POS_SET)
                       else "batter")
                _ov = _aaa_analog.get((int(_mid), _sd))
                if _ov is not None:
                    _sc_plus_map[_p.player_key] = int(round(_ov))
                    _n_resourced += 1
            log.info("SC+ re-sourced from Savant-minors AAA aggregate for %d prospects", _n_resourced)
    except Exception:
        log.exception("Savant-minors SC+ re-source failed — keeping game-feed SC+")

    # Sort actives by latest consensus_fv_raw (smoother than the snapped
    # value for tiebreaking). When two prospects are literally identical
    # on consensus FV (down to the decimal — happens with single-source
    # shrinkage clusters and the Bayesian pull-to-35), tiebreak first
    # by consensus Tools composite_overall (DESC), then by avg_rank
    # (ASC) as the final separator. Tools-grade tiebreak: a 40/40 FV
    # cluster with one player carrying a 55 composite_overall and
    # another carrying a 45 ranks the toolsier player higher — a more
    # informative answer than alphabetical or arbitrary order.
    def _tool_overall(p: PlayerTimeseries) -> float:
        latest = p.points[-1]
        tools = getattr(latest, "tools_consensus", None) or {}
        is_pitcher = bool(p.position
                          and p.position.split("/")[0] in PITCHER_POS_SET)
        # ETOOLS_ALL_CALCS: the shown grades (eTool where one passed).
        tools, _ = _ETC.shown_grades(dict(tools), _etc_rec(p.player_key))
        comp = _compute_tool_composites(dict(tools), is_pitcher)
        if comp and comp.get("composite_overall") is not None:
            return float(comp["composite_overall"])
        return 0.0  # ungraded sinks below any graded tiebreaker

    # v38 — Item-5: server-side Tiebreaker-Score proxy. Mirrors the front-end
    # tiebreakerScore intent (talent/performance base from Tool composite + SC+,
    # LIFTED by the upside "+" flag, DRAGGED sharply by current injury) and is
    # used ONLY to order prospects who share the same SURFACED (rounded)
    # consensus FV. The raw decimal no longer decides the rank.
    def _tbs_proxy(p: PlayerTimeseries) -> float:
        latest = p.points[-1]
        tool = _tool_overall(p)                                   # 20-80
        tool_n = max(0.0, min(1.0, (tool - 40.0) / 30.0)) if tool else None
        sc = _sc_plus_map.get(p.player_key)                       # 100 = pool avg
        sc_n = (max(0.0, min(1.0, (float(sc) - 80.0) / 50.0))
                if sc is not None else None)
        s = w = 0.0
        for v, wt in ((tool_n, 0.6), (sc_n, 0.4)):                # perf-weighted base
            if v is not None:
                s += v * wt; w += wt
        score = (s / w) if w else 0.0
        if getattr(latest, "consensus_fv_plus", False):
            score *= 1.06                                         # upside (+) lift
        if (il_status.get(p.player_key) or {}).get("is_on_il"):
            score *= 0.70                                         # currently injured — sharp drag
        return score

    def _active_key(p: PlayerTimeseries):
        latest = p.points[-1]
        rank_key = latest.avg_rank if latest.avg_rank is not None else 999
        # THE board ordering. Primary term is _board_grade — the RAW eFV grade
        # (BOARD_GRADE_FIELD), which is also the number the board DISPLAYS, so the
        # visible grade column is monotonic by construction. The '+' upside flag and
        # the Tiebreaker-Score proxy arbitrate only EXACT decimal ties. Ties are the
        # common case, not the edge case: ~3.1k of ~4.5k board rows sit on the 20.0
        # provisional floor (accepted, see BOARD_GRADE_FIELD), so the tiebreak chain
        # below is what gives the floor block a stable, meaningful internal order.
        _bg = _board_grade(p.player_key, latest.consensus_fv_raw)
        _fallback_fv = (latest.consensus_fv if latest.consensus_fv is not None
                        else (latest.consensus_fv_raw
                              if latest.consensus_fv_raw is not None else 0))
        surfaced_fv = _bg if _bg is not None else _fallback_fv
        upside = 1 if getattr(latest, "consensus_fv_plus", False) else 0
        _tbs = _tbs_proxy(p)
        # THE NON-MODEL TAIL OF THE ORDERING, kept per row (serialized as `board_key_tail`)
        # so rebake_board_ranks can re-apply this exact chain after efv_export.regen_all
        # rewrites data/xfv.json, refreshing only the two model terms. Without it the
        # baked rank is one run stale against the board (2026-09-05, De Paula / Gillen).
        board_key_tail_by_key[p.player_key] = [
            float(_fallback_fv), upside, round(float(_tbs), 6),
            (float(rank_key) if rank_key is not None else 999.0),
            _active_display_org(p) or "?",
        ]
        # ONE ordering: board_rank_key is the tuple the re-bake builds too.
        #   grade desc -> board_sort_key desc (sub-decimal model order INSIDE a tie block)
        #   -> '+' upside flag -> Tiebreaker Score proxy -> avg_rank asc
        return board_rank_key(surfaced_fv, _board_sort_key(p.player_key), upside,
                              _tbs, rank_key)
    board_key_tail_by_key: dict[str, list] = {}
    actives.sort(key=_active_key)
    if top_n_active is not None:
        actives = actives[:top_n_active]

    # TIE-BLOCK census over the board number. ~3.1k of ~4.5k rows share the 20.0
    # provisional floor exactly, so for those players the rank NUMBER is produced by the
    # tiebreak chain rather than by the grade. _rank_meaningful reads this to withhold
    # rank movement / rank deltas that are tie-order churn, not player movement.
    # PV-07: the shared rank counts only rows with a label-source opinion (PROV_SECTION_ON);
    # the rest keep their place in the payload order and carry no overall/org rank.
    _source_graded_by_key: dict[str, bool] = {
        _p.player_key: has_label_source_opinion(_p.points) for _p in actives}
    _ranked_actives = [_p for _p in actives
                       if not PROV_SECTION_ON or _source_graded_by_key.get(_p.player_key)]
    _board_grade_tie_count.clear()
    for _p in _ranked_actives:
        _g = _board_grade(_p.player_key,
                          _p.points[-1].consensus_fv_raw if _p.points else None)
        if _g is not None:
            _board_grade_tie_count[float(_g)] = _board_grade_tie_count.get(float(_g), 0) + 1

    # Pre-compute overall_rank (position in the FV-sorted active list) and
    # org_rank (position within the player's org by the same ordering).
    # `_serialize` reads these out of the maps below so we don't have to
    # re-sort in the front-end.
    overall_rank_by_key: dict[str, int] = {}
    org_rank_by_key: dict[str, int] = {}
    org_size_by_key: dict[str, int] = {}
    org_counters: dict[str, int] = {}
    org_totals: dict[str, int] = {}
    for p in _ranked_actives:
        org_key = _active_display_org(p) or "?"
        org_totals[org_key] = org_totals.get(org_key, 0) + 1
    for p in actives:
        org_size_by_key[p.player_key] = org_totals.get(_active_display_org(p) or "?", 0)
    for i, p in enumerate(_ranked_actives, start=1):
        overall_rank_by_key[p.player_key] = i
        org_key = _active_display_org(p) or "?"
        org_counters[org_key] = org_counters.get(org_key, 0) + 1
        org_rank_by_key[p.player_key] = org_counters[org_key]
        org_size_by_key[p.player_key] = org_totals[org_key]

    # prev_overall_rank: the player's OWN overall_rank at the previous board
    # snapshot, read straight out of metric_snapshots (the same field, the same
    # basis, one run earlier). It feeds the rank-delta arrow (▲ +12 / ▼ -7 / flat)
    # under the rank diamond on the consensus-toggled board.
    #
    # 2026-07-25 — this REPLACED a re-sort of the active list on a prior-snapshot key
    # of its own. That re-sort was a second board ordering (rounded prior grade ->
    # tool composite -> IL -> avg_rank, over a POOL restricted to players with >= 2
    # points), so it disagreed with _active_key even when nothing had moved and
    # manufactured rank deltas out of nothing. Reading back the stored rank cannot
    # drift from the current rank because it IS the current rank, one snapshot ago.
    #
    # BASIS EPOCH: pre-epoch snapshots are on the retired quantile basis, so they are
    # filtered out (load_rank_history applies the same gate). Until a second post-epoch
    # snapshot lands, every player's prior rank is None and the arrow renders nothing.
    # That is the disclosed one-time discontinuity for the raw-grade re-rank: no arrow
    # is correct, a 3,000-spot arrow off a basis change would not be.
    prev_overall_rank_by_key: dict[str, int] = {}
    for _pk, _hist in _rank_hist_by_key.items():
        _prior = [h for h in (_hist or [])
                  if h.get("rank") is not None and h.get("snapshot_date") != _today_iso]
        if _prior:
            prev_overall_rank_by_key[_pk] = int(_prior[-1]["rank"])

    # Inactives: most recently seen first
    inactives.sort(key=lambda p: p.points[-1].snapshot_date if p.points else "", reverse=True)

    # Sort debuts by debut_date desc (most recent first)
    grads.sort(key=lambda p: p.debut_date or "", reverse=True)

    _phase_done("rank")
    # ── Org farm summary ────────────────────────────────────────────────────
    # Build per-org aggregate stats from the active list only (not graduates).
    # Position groups: C, INF (1B/2B/SS/3B/UTIL), OF, P (SP/RP).
    # v9 — 1B folded into INF. The standalone 1B bucket was a holdover
    # from when first-base depth was treated as a distinct positional
    # archetype, but in practice it produced a noisy 5-chip strip on
    # the farm list with 1B = INF for every scouting purpose. INF now
    # covers every non-pitcher non-catcher non-outfielder.
    PITCHER_POS = {"RHP", "LHP", "SP", "RP", "MIRP", "SIRP"}

    def _pos_group(pos: str | None) -> str:
        if not pos:
            return "?"
        p0 = pos.split("/")[0]
        if p0 in PITCHER_POS:
            return "P"
        if p0 == "C":
            return "C"
        if p0 in {"OF", "CF", "LF", "RF"}:
            return "OF"
        # 1B, SS, 2B, 3B, UTIL, MI, IF, DH
        return "INF"

    # v30.7 — Finer 5-bucket pos grouping for the position-bucketed
    # DvM+ pass. Splits pitchers into SP / RP and surfaces C / INF /
    # OF for hitters. SP bucket includes RHP/LHP (most unassigned-
    # role arms are SP-track draftees / lower-minors before the role
    # is set); RP bucket includes RP / MIRP / SIRP / CL / CP.
    _HIT_POS_TO_BUCKET_V2 = {
        "C": "C",
        "1B": "INF", "2B": "INF", "3B": "INF", "SS": "INF",
        "INF": "INF", "MI": "INF", "UTIL": "INF", "DH": "INF",
        "OF": "OF", "LF": "OF", "CF": "OF", "RF": "OF",
    }
    _PIT_POS_TO_BUCKET_V2 = {
        "SP": "SP", "RHP": "SP", "LHP": "SP",
        "RP": "RP", "MIRP": "RP", "SIRP": "RP", "CL": "RP", "CP": "RP",
    }
    def _pos_bucket_v2(pos: str | None) -> str | None:
        if not pos:
            return None
        first = pos.upper().split("/")[0].strip()
        return _HIT_POS_TO_BUCKET_V2.get(first) or _PIT_POS_TO_BUCKET_V2.get(first)

    # ── FARM-GRADE INPUT POOL CONTRACT (v20) ────────────────────────────
    # The org_map below is fed exclusively from `actives` — the list that
    # excludes any player with `status == "debuted"`, which under the
    # v20 definitive-debut rule means any player whose roster_status has
    # an mlb_debut_date. Every grade derived from `m["prospects"]` or
    # its accumulators (top_end / depth / tools_quality / international_
    # depth / readiness / health_burden / tool_dev / draft_ceiling_hits
    # / active_surplus) therefore sees CURRENT-FARM prospects only.
    #
    # The grad_agg loop further down handles the inverse pool — it walks
    # `grads` to feed talent_translation / financial_roi / boom/bust %.
    # Together these two passes implement the user's rule:
    #   "development / current farm system EXCLUDES debuted players;
    #    talent_translation / MLB production / WAG / WAR-per-year ONLY
    #    counts debuted players."
    # ────────────────────────────────────────────────────────────────────
    # ── $DvM+ (Surplus Development vs Mean) — item-6 league pre-pass ─────────
    # Per-prospect SURPLUS-VALUE DEVELOPMENT TRAJECTORY, indexed against the
    # mean prospect at the SAME FV tier (100 = tier mean, +10 = 1σ better).
    # Surplus value is a monotonic function of FV, so the trajectory is built
    # from the RATE of FV movement over the tracked history (the dominant
    # signal — stat/tool breakouts manifest as FV jumps and are captured here)
    # plus the age-relative-to-level standing (younger-for-level = developing
    # ahead of peers). Computed once here so BOTH the org financial grade
    # (fin_dollar_dvm, below) and the per-prospect payload (stamped after
    # serialization) read one consistent value. Z-scored WITHIN FV tier; tiers
    # with <4 members borrow the global spread so a sparse tier can't manufacture
    # extreme scores.
    # eFV join + closures (_xg / _xsurplus / _xfv_series) were loaded once at the top of
    # export_timeseries_json; reused here for the $DvM+ trajectory + tier.
    _ddvm_raw_by_key: dict[str, float] = {}
    _ddvm_tier_by_key: dict[str, int] = {}
    for p in actives:
        pts = p.points or []
        if not pts or pts[-1].consensus_fv_raw is None:
            continue
        cons_close = float(pts[-1].consensus_fv_raw)
        cons_open = float(pts[0].consensus_fv_raw) if pts[0].consensus_fv_raw is not None else cons_close
        # Appreciation RATE on eFV (owner: everything eFV). eFV's trajectory is the xfv_history
        # series (a current-model retrospective); consensus history is the fallback where eFV
        # has no series. The peer TIER is the eFV grade.
        _xs = _xfv_series(p.player_key)
        if _xs:
            fv_close, fv_open = float(_xs[-1][1]), float(_xs[0][1])
            try:
                _d0 = date.fromisoformat(_xs[0][0]); _d1 = date.fromisoformat(_xs[-1][0])
                _yrs = max(0.5, (_d1 - _d0).days / 365.0)
            except Exception:
                _yrs = 1.0
        else:
            fv_close, fv_open = cons_close, cons_open
            try:
                _d0 = date.fromisoformat(pts[0].snapshot_date)
                _d1 = date.fromisoformat(pts[-1].snapshot_date)
                _yrs = max(0.5, (_d1 - _d0).days / 365.0)
            except Exception:
                _yrs = 1.0
        fv_move_rate = (fv_close - fv_open) / _yrs              # grade-pts / yr (eFV where rated)
        _bd = birth_dates.get(p.player_key)
        _age = compute_age_decimal(_bd)
        _sl = statlines.get(p.player_key)
        _lvl = _sl.get("level") if _sl else None
        _avl = score_age_vs_level(_age, _lvl, baselines=age_baselines)
        age_term = (-float(_avl.diff)) if (_avl and _avl.diff is not None) else 0.0
        # trajectory = grade-movement rate (primary) + 0.5 × age-for-level standing
        _ddvm_raw_by_key[p.player_key] = fv_move_rate + 0.5 * age_term
        _tier_grade = _xg(p.player_key, cons_close)
        _ddvm_tier_by_key[p.player_key] = int(round((_tier_grade if _tier_grade is not None else cons_close) / 5.0) * 5)
    import statistics as _stats
    _all_traj = list(_ddvm_raw_by_key.values())
    _g_mu = _stats.fmean(_all_traj) if _all_traj else 0.0
    _g_sd = (_stats.pstdev(_all_traj) if len(_all_traj) > 1 else 0.0) or 1.0
    _ddvm_by_tier: dict[int, list[float]] = {}
    for _k, _t in _ddvm_tier_by_key.items():
        _ddvm_by_tier.setdefault(_t, []).append(_ddvm_raw_by_key[_k])
    _tier_stats: dict[int, tuple[float, float]] = {}
    for _t, _vals in _ddvm_by_tier.items():
        if len(_vals) >= 4:
            _mu = _stats.fmean(_vals)
            _sd = (_stats.pstdev(_vals) or _g_sd) or 1.0
        else:
            _mu, _sd = _g_mu, _g_sd
        _tier_stats[_t] = (_mu, _sd)
    # TRUE-TO-MODEL 2026-07-29: the published $DvM+ is the raw 100 + 10z, with no
    # display clamp. A `max(40, min(160, ...))` used to sit here; it is the same
    # display-compression class the C2 lane removed from KRP+ (precedent +
    # classification rule: data/plus_metric_recal_eval.json), and the owner has
    # chosen full true-to-model, so a prospect whose development trajectory really
    # is 6 sigma below his FV tier now reads as such instead of being parked on the
    # floor next to everyone else down there. The clamp was NOT rank-preserving:
    # it collapsed a whole tail into one displayed value.
    _dollar_dvm_by_key: dict[str, float] = {}
    for _k, _traj in _ddvm_raw_by_key.items():
        _mu, _sd = _tier_stats.get(_ddvm_tier_by_key[_k], (_g_mu, _g_sd))
        _z = (_traj - _mu) / (_sd or 1.0)
        _dollar_dvm_by_key[_k] = round(100.0 + 10.0 * _z, 1)
    # DvM+ difficulty arm (DVM_DIFFICULTY_ARM; None until the owner's flip, and then this
    # pass is skipped entirely). The result feeds three points: the player index here,
    # the per-tool pass and the FV-DvM+ family below (_apply_dvm_difficulty_*).
    _dvm_diff = (_dvm_difficulty_result(
        attribution=_dev_attr, as_of=date.today().isoformat(),
        bucket_of={_p.player_key: _pos_bucket_v2(_p.position)
                   for _p in actives + grads + inactives},
        actives=[_p.player_key for _p in actives])
        if DVM_DIFFICULTY_ARM is not None else None)
    if _dvm_diff is not None:
        # Gate section 9 (Q-DVM-6 A): the player index replaces the tier z; key kept.
        _dollar_dvm_by_key = {_k: float(_v) for _k, _v in _dvm_diff["player_index"].items()}

    org_map: dict[str, dict] = {}
    for idx, p in enumerate(actives):
        # Skip prospects with no resolved org — they fall through every source
        # without a team label (rare; usually a name-aliasing bug where the
        # prospect is double-counted under a different canonical key with an
        # org). Including them creates a phantom 31st "team" on the farm page.
        org = _active_display_org(p)
        if not org:
            continue
        bd = birth_dates.get(p.player_key)
        age = compute_age_decimal(bd)
        latest = p.points[-1]
        fv_raw = latest.consensus_fv_raw
        fv_lab = latest.consensus_fv_label
        stock_dir = p.points[-1].consensus_fv_raw - p.points[0].consensus_fv_raw if len(p.points) > 1 else 0.0
        sl = statlines.get(p.player_key)
        level = sl.get("level") if sl else None
        avl = score_age_vs_level(age, level, baselines=age_baselines)
        pos_grp = _pos_group(p.position)

        if org not in org_map:
            org_map[org] = {
                "org": org,
                "prospects": [],
                "total_fv": 0.0,
                "tier_60_plus": 0,
                "tier_55": 0,
                "tier_50": 0,
                "ages": [],
                "pos_groups": {},
                "stock_up": 0,
                "stock_down": 0,
                "stock_flat": 0,
                "very_young_count": 0,
                # Companion of very_young_count — drives the Readiness
                # report-card grade. Net (very_young - very_old) per org.
                "very_old_count": 0,
                # Accumulators for the extended report-card grades
                # added in the Farm System Overhaul. Populated below and
                # finalized in the second pass after the actives loop.
                "_active_keys": [],
                "_ifa_years":  [],
                "_ifa_count":  0,
                "_post_tj_count": 0,
                "_il_days_sum":   0,
                "_il_days_count": 0,
                # Currently-on-IL counter. Increments once per active
                # whose il_status.is_on_il is true at export time;
                # finalized into health_burden.il_pct_current (count /
                # active total) so the farm card can flag orgs with a
                # high share of the org sidelined right now.
                "_il_current_count": 0,
                # v31.1 — Per-side health splits (Hitter vs Pitcher).
                # Surfaces side-specific injury exposure under the
                # Health Mgmt leaf's sub-leaves so the user can see,
                # e.g., a pitcher-heavy IL share even when the overall
                # IL rate is moderate (pitcher arms are the main injury
                # risk; the side split makes that asymmetry visible).
                # v31.6 — Hitter post-TJ removed (TJ for hitters isn't
                # a real thing — the metric was misleading). Pitcher
                # post-TJ kept but as informational only (no longer
                # affects the Health Mgmt grade).
                "_post_tj_count_pit":  0,
                "_il_current_count_pit": 0,
                "_il_current_count_hit": 0,
                "_actives_pit_count":  0,
                "_actives_hit_count":  0,
                # Per-org tool-development accumulator (Step 3 of the
                # ToolsDvM+ plan). Keyed by canonical tool name (hit,
                # game_pwr, etc.) — each entry holds the per-prospect
                # lifetime delta (latest − first consensus grade) for
                # every active prospect with ≥2 observations of that
                # tool. Finalized in the second pass into mean_delta per
                # tool, then league-normalized into HitDvM+ / PowerDvM+
                # / etc. in `_attach_per_tool_dvm_plus`.
                "_tool_dev_sums": {},
                # v30.8 — Per-position-bucket tool-development accumulator.
                # Parallel structure to _tool_dev_sums above, keyed by
                # pos bucket (C / INF / OF / SP / RP) then tool. Powers
                # the per-bucket Tool DvM+ that replaces the org-side-
                # wide tool value previously applied uniformly to every
                # bucket. Cells with <3 contributing prospects fall
                # back to the org-side-wide tool DvM+ (hybrid policy).
                "_tool_dev_sums_by_bucket": {},
                # Tree v3 — Draft Ceiling Hits accumulator. Counter of
                # drafted actives whose FV ≥ 60 within 3yr of draft.
                # Pulled into the Draft Pick Performance leaf's 2nd
                # sub-input (50/50 z-blend with pick-slot-adjusted WAR).
                "_draft_actives_count": 0,
                "_draft_ceiling_hits":  0,
                # v18 — Active-surplus accumulators feeding the new
                # `fin_active_surplus` leaf. _net = sum of (FV-implied
                # surplus $M over the valuation set's own window, 7 seasons
                # under clemens_2026 - NOT the 6 the comment read until
                # 2026-09-17, and NOT the club control window the MLB
                # Projections board prices) − (acquisition bonus $M, NOT amortized
                # since we want full cost basis vs the full window
                # surplus). _cost tracks the bonus dollars alone for
                # tooltip / debug.
                "_active_surplus_net_mm":  0.0,
                "_active_surplus_cost_mm": 0.0,
                "_active_surplus_count":   0,
                # v31.5 — Per-side splits (hitter vs pitcher) so the
                # Active Surplus leaf can surface a sub-leaf breakdown.
                # Pitcher surplus per prospect typically trails hitter
                # surplus due to higher injury / bust risk; the split
                # makes that asymmetry visible.
                "_active_surplus_net_mm_hit":  0.0,
                "_active_surplus_count_hit":   0,
                "_active_surplus_net_mm_pit":  0.0,
                "_active_surplus_count_pit":   0,
                # v32.0 — FV-points-spent accumulator. Sums fv_raw across
                # the same set of prospects contributing to surplus_net_mm,
                # enabling the surplus_per_fv_pt_mm efficiency metric
                # (how much $ surplus this org is generating per FV point
                # of active prospect capital). High = star-loaded /
                # premium-position; low = depth-heavy but flat.
                "_active_surplus_fv_total":  0.0,
                # v32.1 — Per-side FV totals so the leaf can surface
                # hitter $/FV-pt vs pitcher $/FV-pt. Pairs with the
                # existing per-side surplus_net_mm_{hit,pit} totals.
                "_active_surplus_fv_total_hit":  0.0,
                "_active_surplus_fv_total_pit":  0.0,
                # v32.1 — Per-acquisition-method buckets feeding the
                # new acquisition_method_efficiency sub-leaf. Tracks
                # which channel (draft / IFA / trade) is the most $-efficient
                # at producing FV. Keyed by method label; each holds
                # net surplus ($M), fv-pts, count, and cost basis ($M).
                "_method_surplus": {
                    "draft":             {"net_mm": 0.0, "fv_total": 0.0, "count": 0, "cost_mm": 0.0},
                    "international_fa":  {"net_mm": 0.0, "fv_total": 0.0, "count": 0, "cost_mm": 0.0},
                    "trade":             {"net_mm": 0.0, "fv_total": 0.0, "count": 0, "cost_mm": 0.0},
                },
                # v29 — Statcast+ + indicator-count accumulators feeding
                # the new `statcast_quality` farm-grade leaf. _sc_plus
                # collects every active prospect's SC+ when tracked;
                # _upside_count / _breakout_count tally indicator-flagged
                # prospects (computed inline below since the per-payload
                # breakout pass runs after this loop, so we recompute the
                # upside boolean from points + cap the breakout count
                # against `breakout_flag` after serialization in the
                # second pass).
                "_sc_plus":         [],
                # v30.5 — Per-side SC+ buckets so the farm leaf can
                # surface hitter vs pitcher tracked-data quality
                # separately. Useful for the strong-bats-thin-arms
                # (or vice versa) case where the org-wide mean blurs
                # the diagnostic signal.
                "_sc_plus_hit":     [],
                "_sc_plus_pit":     [],
                "_upside_count":     0,
                "_breakout_count":   0,
                # v38 — Item-6: per-prospect $DvM+ values for this org. Org
                # $DvM+ = mean of these; feeds the fin_dollar_dvm financial leaf.
                "_ddvm_vals":        [],
            }
        m = org_map[org]
        _pdvm = _dollar_dvm_by_key.get(p.player_key)
        if _pdvm is not None:
            m["_ddvm_vals"].append(_pdvm)
        # eFV is the org composite + tier-count + top-end basis (consensus fallback). Carried
        # on the prospect dict so _top_end_points sums eFV grade-points.
        _xfvg = _xg(p.player_key, fv_raw)
        _xfvg_eff = _xfvg if _xfvg is not None else fv_raw
        m["prospects"].append({
            "name": p.player_name,
            "player_key": p.player_key,
            "pos": p.position,
            "age": age,
            "fv_label": fv_lab,
            "fv_raw": round(fv_raw, 1),
            "xfv_grade": round(_xfvg, 1) if _xfvg is not None else None,
            "rank": idx + 1,
        })
        m["total_fv"] += _xfvg_eff
        fv_int = int(_xfvg_eff)
        if fv_int >= 60:
            m["tier_60_plus"] += 1
        elif fv_int >= 55:
            m["tier_55"] += 1
        else:
            m["tier_50"] += 1
        if age is not None:
            m["ages"].append(age)
        m["pos_groups"][pos_grp] = m["pos_groups"].get(pos_grp, 0) + 1
        if stock_dir > 2:
            m["stock_up"] += 1
        elif stock_dir < -2:
            m["stock_down"] += 1
        else:
            m["stock_flat"] += 1
        if avl.tier == "very-young":
            m["very_young_count"] += 1
        elif avl.tier == "too-old":
            # 2026-07-30: was "very-old", a tier age_level has NEVER emitted (its
            # vocabulary is very-young / young / neutral / old / too-old, declared at
            # age_level.py:73). So this branch was unreachable, very_old_count was
            # permanently 0, and the Readiness net below - (very_young - very_old) /
            # actives - could only ever be POSITIVE. Every org's readiness signal was
            # measuring half of a two-sided statistic. "too-old" (diff >= +2.0) is the
            # correct mirror of "very-young" (diff <= -2.0).
            m["very_old_count"] += 1

        # Tool Quality accumulator — composite_overall (raw 20-80
        # power-mean of per-tool grades, same value as the prospect's
        # Tool composite). Computed directly from the latest consensus
        # tools dict so it's available even if a future re-ordering
        # moves the post-serialization passes around.
        is_pitcher_p = bool(p.position and p.position.split("/")[0] in PITCHER_POS_SET)
        _farm_extras = _extract_player_extras(p.points[-1] if p.points else None)
        _farm_pos_bucket = _position_bucket(p.position)
        # ETOOLS_ALL_CALCS: the same eTool composite the prospect's card shows.
        _farm_grades, _ = _ETC.shown_grades(
            dict(p.points[-1].tools_consensus) if p.points[-1].tools_consensus else None,
            _etc_rec(p.player_key))
        _comp = _compute_tool_composites(
            _farm_grades,
            is_pitcher_p,
            player_extras=_farm_extras,
            position_bucket=_farm_pos_bucket,
        )
        if _comp and _comp.get("composite_overall") is not None:
            m.setdefault("_tools_comp_overall", []).append(float(_comp["composite_overall"]))

        # Per-prospect tool deltas (latest − first consensus grade for each
        # tool with ≥2 observations). Sum into the org bucket so the
        # second pass can produce mean-delta-per-tool and the league
        # normalization can produce HitDvM+ / PowerDvM+ / etc.
        # WAR-tail-weighted: store the FV→WAR-converted delta rather
        # than the raw FV grade delta, so a 70→75 hit-tool lift counts
        # ~10x a 40→45 hit-tool lift in the per-tool DvM+ math.
        # VAL_4 (2026-10-08): with a development attribution the deltas are the
        # prospect's TENURE tool growth (same-source pairs, split by days across
        # the clubs that held him, inside the same trailing window), each credited
        # to the club where it happened, gathered in _tenure_tool_sums and merged
        # into each club's accumulator in the second pass. The lifetime consensus
        # delta credited to the current club stays only as the fallback for a
        # prospect the attribution does not cover.
        _pa_tools = _dev_attr.get(p.player_key) if _dev_attr is not None else None
        if _pa_tools is not None and _pa_tools.basis == "none":
            _pa_tools = None
        _td = {} if _pa_tools is not None else _compute_tool_deltas([
            {"snapshot_date": pt.snapshot_date,
             "tools_consensus": pt.tools_consensus}
            for pt in p.points
        ])
        # v30.8 — Compute the prospect's pos bucket ONCE outside the
        # per-tool loop. We route each tool's delta into both the
        # org-wide accumulator (existing) AND the bucket-specific
        # accumulator (new) so per-bucket Tool DvM+ can be computed
        # without re-walking the per-prospect data.
        _prospect_bucket = _pos_bucket_v2(p.position)
        # v30.8 — Level confidence weight. AA peaks (the real-prospect
        # filter); DSL/CPX deflate (grades there are heavy projection
        # vs realized signal); AAA slightly above MLB-grad cohort. The
        # weight scales every per-prospect tool delta so an org loaded
        # with high-tool DSL kids gets less credit than an org with
        # similar tool grades at AA. Unknown level = 1.0 (no effect).
        # `level` is already in scope from the statline lookup above.
        _level_weight = _TOOL_DEV_LEVEL_WEIGHTS.get(level, 1.0)
        for _tk, _info in _td.items():
            first_war = _fv_to_expected_war(_info.get("first")) or 0.0
            last_war  = _fv_to_expected_war(_info.get("last"))  or 0.0
            delta_war = (last_war - first_war) * _level_weight
            m["_tool_dev_sums"].setdefault(_tk, []).append(delta_war)
            if _prospect_bucket is not None:
                m["_tool_dev_sums_by_bucket"] \
                    .setdefault(_prospect_bucket, {}) \
                    .setdefault(_tk, []) \
                    .append(delta_war)
        if _pa_tools is not None:
            for _t_org, _t_tools in _pa_tools.tool_growth.items():
                for _tk, _g in _t_tools.items():
                    delta_war = _g * _level_weight
                    _tenure_tool_sums.setdefault(_t_org, {}).setdefault(_tk, []).append(delta_war)
                    if _prospect_bucket is not None:
                        _tenure_tool_sums_by_bucket.setdefault(_t_org, {}) \
                            .setdefault(_prospect_bucket, {}) \
                            .setdefault(_tk, []) \
                            .append(delta_war)

        # Extended report-card accumulators (Farm Overhaul Step 5/6/7).
        m["_active_keys"].append(p.player_key)
        acq_rec = (acquisitions or {}).get(p.player_key) or {}
        if acq_rec.get("method") == "international_fa":
            m["_ifa_count"] += 1
            y = acq_rec.get("year")
            if y is not None:
                m["_ifa_years"].append(y)
        # v18 — Active-surplus contribution. Each active prospect's
        # FV-implied 6yr surplus value ($M) minus their acquisition
        # bonus (full amount, since the 6yr surplus is the gross figure).
        # Feeds the new fin_active_surplus leaf. Skip players without a
        # usable FV or position (the table requires both).
        # eFV is the primary grade for the farm Value core: surplus is the eFV expected
        # surplus (consensus-surplus fallback). _xfvg (the player's eFV grade, consensus
        # fallback) was computed at the prospect-dict build above and is reused here + for
        # draft-ceiling + method buckets, so the FV-pt totals stay consistent with the surplus.
        # bughunt F6 (2026-07-23): the abstain-fallback used to price timing-NAIVE
        # (no age/eta -> debut-now dollars) inside a sum whose eFV leg is
        # timing-aware. Pass the row's age + the shared no-ETA fallback so the
        # (currently never-firing) fallback stays on the same basis.
        _surplus_mm = _xsurplus(p.player_key, _estimate_surplus_mm(
            fv_raw, is_pitcher_p, p.position,
            age=age, eta_years=PROSPECT_ETA_FALLBACK_YEARS, eta_origin=date.today().year))
        if _surplus_mm is not None:
            _bonus_mm = (float(acq_rec.get("bonus_usd") or 0) / 1_000_000.0)
            _net_mm = _surplus_mm - _bonus_mm
            m["_active_surplus_net_mm"]  += _net_mm
            m["_active_surplus_cost_mm"] += _bonus_mm
            m["_active_surplus_count"]   += 1
            # v32.0 — Track FV-pts (eFV) contributing to surplus_net so
            # surplus_per_fv_pt_mm can be computed in finalize.
            # v32.1 — Per-side FV totals (hit / pit) for the asymmetry
            # display in the active_surplus leaf.
            if _xfvg is not None:
                m["_active_surplus_fv_total"] += float(_xfvg)
                if is_pitcher_p:
                    m["_active_surplus_fv_total_pit"] += float(_xfvg)
                else:
                    m["_active_surplus_fv_total_hit"] += float(_xfvg)
            # v31.5 — Per-side split.
            if is_pitcher_p:
                m["_active_surplus_net_mm_pit"] += _net_mm
                m["_active_surplus_count_pit"]  += 1
            else:
                m["_active_surplus_net_mm_hit"] += _net_mm
                m["_active_surplus_count_hit"]  += 1
            # v32.1 — Per-acquisition-method tracking. `method` is one of
            # "draft" / "international_fa" / "trade" / "rule_5" / "waiver"
            # / "purchase" / "free_agent" / None. We only bucket the
            # three major channels — the rest aggregate as 'other'.
            _method = acq_rec.get("method")
            _method_bucket = (_method if _method in ("draft", "international_fa", "trade")
                              else None)
            if _method_bucket is not None and _xfvg is not None:
                _mb = m["_method_surplus"][_method_bucket]
                _mb["net_mm"]    += _net_mm
                _mb["cost_mm"]   += _bonus_mm
                _mb["fv_total"]  += float(_xfvg)
                _mb["count"]     += 1
        # Tree v3 — Draft Ceiling Hits: count drafted actives whose
        # current eFV ≥ 60 and whose draft year is within the last 3 years.
        # Captures whether the org's recent draft classes produced high-ceiling
        # prospects (not just whether grads beat the slot in retrospect).
        # Denominator: all drafted actives.
        if acq_rec.get("method") == "draft":
            m["_draft_actives_count"] = m.get("_draft_actives_count", 0) + 1
            draft_yr = acq_rec.get("year")
            today_yr = date.today().year
            if (draft_yr is not None
                    and today_yr - int(draft_yr) <= 3
                    and _xfvg is not None
                    and _xfvg >= 60.0):
                m["_draft_ceiling_hits"] = m.get("_draft_ceiling_hits", 0) + 1
            # v32.0 — Track FV-pts (eFV) produced by active drafted prospects
            # in the same 3yr (T-5..T-2) window the war_per_m_pool leaf
            # uses for grads. This feeds the new fv_per_m_pool metric,
            # which gives a fast-cycle (no 5yr WAR maturation needed)
            # signal of draft-spending efficiency.
            if (draft_yr is not None
                    and today_yr - 5 <= int(draft_yr) <= today_yr - 2
                    and _xfvg is not None):
                m.setdefault("_draft_pool_active_fv_total", 0.0)
                m["_draft_pool_active_fv_total"] += float(_xfvg)
        # Health profile (reuse the same helper the per-prospect path uses).
        rs_player = (roster_status or {}).get(p.player_key) or {}
        hp = _derive_health_profile(rs_player.get("injury_history") or [])
        # v31.1 — Determine side once so per-side health counters can
        # increment alongside the org-wide ones.
        _is_pit_active = bool(p.position and p.position.split("/")[0] in PITCHER_POS)
        if _is_pit_active:
            m["_actives_pit_count"] += 1
        else:
            m["_actives_hit_count"] += 1
        # v31.6 — Post-TJ tracking limited to PITCHERS only. Hitter
        # TJ isn't a real signal (the surgery is overwhelmingly a
        # pitcher procedure) and the metric was misleading when
        # surfaced for hitters. Post-TJ still counted at the org-
        # wide level as informational context but no longer affects
        # the Health Mgmt grade.
        if hp.get("is_post_tj") and _is_pit_active:
            m["_post_tj_count"] += 1
            m["_post_tj_count_pit"] += 1
        il_days = int(hp.get("il_days_12mo") or 0)
        m["_il_days_sum"]   += il_days
        m["_il_days_count"] += 1
        # Currently-on-IL: il_status table is the source of truth for
        # "on IL right now". il_status was loaded above and attached as
        # `il_status` (dict keyed by player_key).
        if (il_status or {}).get(p.player_key, {}).get("is_on_il"):
            m["_il_current_count"] = m.get("_il_current_count", 0) + 1
            if _is_pit_active:
                m["_il_current_count_pit"] += 1
            else:
                m["_il_current_count_hit"] += 1

        # v29 — Statcast+ contribution. None values are skipped (the
        # prospect has no tracked Statcast / zone data).
        # v30.5 — Also route into the per-side bucket so the farm
        # leaf can surface hitter vs pitcher SC+ separately.
        # v30.7 — Also route into the per-position-bucket dict so the
        # downstream per-bucket StatcastDvM+ can compute mean SC+ for
        # each C/INF/OF/SP/RP bucket independently.
        _sc_p = _sc_plus_map.get(p.player_key)
        if _sc_p is not None:
            m["_sc_plus"].append(int(_sc_p))
            if is_pitcher_p:
                m["_sc_plus_pit"].append(int(_sc_p))
            else:
                m["_sc_plus_hit"].append(int(_sc_p))
            _pb = _pos_group(p.position)  # legacy 4-way grouping
            # Use the finer 5-bucket helper (C / INF / OF / SP / RP)
            # for the new per-bucket DvM+. Falls back silently when
            # the position doesn't map (rare: DH-only stragglers etc.).
            _pb_v2 = _pos_bucket_v2(p.position) if _pb is not None else None
            if _pb_v2 is not None:
                m.setdefault("_sc_plus_by_bucket", {}).setdefault(_pb_v2, []).append(int(_sc_p))
        # v29 — Upside-indicator count. Uses consensus_fv_plus on the
        # latest point AND honors the same FV ≤ 50 cap the UI applies
        # (sub-50 grades are the canonical upside surface; 55+/60+ are
        # ignored because those tiers have already realized their upside).
        _latest_pt = p.points[-1] if p.points else None
        if (_latest_pt
                and getattr(_latest_pt, "consensus_fv_plus", False)
                and fv_raw is not None and float(fv_raw) <= 50.0):
            m["_upside_count"] += 1

    _phase_done("org_rollup")
    # ── Per-org graduate aggregates (Farm Overhaul Steps 2 & 3) ──
    # Walk graduates ONCE to compute:
    #   - WAG sum + count (per-grad WAG via _grad_wag)
    #   - Total career WAR (across grads with a value)
    #   - Total bonus USD (across grads with bonus on file)
    # All grouped by graduate's CURRENT org (per user's choice).
    #
    # WAG_UNIFIED: the debuted block (engine WAG included) is baked ONCE per graduate
    # here, memoised, and _serialize serves the same object on the card, so the WAG an
    # org is graded on is the WAG its graduates' cards show. Same inputs, same call as
    # _serialize's own. Unused while the flag is False.
    _debuted_memo: dict[str, dict | None] = {}

    def _debuted_block_for(pt: PlayerTimeseries) -> dict | None:
        if pt.player_key not in _debuted_memo:
            _xr = _xfv_by_key.get(pt.player_key) or {}
            _debuted_memo[pt.player_key] = (
                _build_debuted_payload(
                    (pt.points[-1].consensus_fv_raw if pt.points else None),
                    _vf_is_pitcher_position(pt.position), pt.position,
                    age=compute_age_decimal(birth_dates.get(pt.player_key)),
                    career_war=career_war.get(pt.player_key),
                    roster_status=roster_status.get(pt.player_key),
                    contract=contracts_by_key.get(pt.player_key),
                    career_stats=career_stats.get(pt.player_key),
                    wag_fv=_xr.get("xfv_grade_at_debut", _xr.get("xfv_grade")))
                if pt.status == "debuted" else None)
        return _debuted_memo[pt.player_key]

    def _new_grad_bucket() -> dict:
        # One graduate pool per club. VAL_4: a graduate enters each pool by his
        # development share (dev_attribution), so every count below is a
        # share-weighted count (graduate-equivalents) and every sum a
        # share-weighted sum.
        return {
                "wag_sum": 0.0, "wag_count": 0,
                "war_sum": 0.0, "war_count": 0,
                "bonus_sum": 0, "bonus_count": 0,
                # Tree v2 splits — same WAG but partitioned by acquisition
                # method (IFA vs Draft) and position type (Hitter vs Pitcher)
                # so the grade tree's Acquisitions and MLB Production
                # branches can each grade their own sub-axis.
                "ifa_wag_sum": 0.0,   "ifa_wag_count":   0,
                "draft_wag_sum": 0.0, "draft_wag_count": 0,
                "hit_wag_sum": 0.0,   "hit_wag_count":   0,
                "pit_wag_sum": 0.0,   "pit_wag_count":   0,
                # Grad-Contract Surplus — current AAV − (bonus amortized over
                # 6 years, the rough cost-controlled window before the player
                # would have hit arb/FA). Positive = grad's MLB salary value
                # exceeds the org's signing-bonus outlay.
                "contract_surplus_sum": 0.0, "contract_surplus_count": 0,
                # Pick-slot-adjusted draft performance (v2 of Draft Pick
                # Performance). actual_war − slot_expected_war per drafted
                # grad. Credits orgs that beat the market at each pick slot;
                # strictly more informative than raw WAG for the "did this
                # org draft well?" question.
                "draft_pick_value_sum": 0.0, "draft_pick_value_count": 0,
                # Tree v3 splits — supplemental WAR/yr + cumulative WAR
                # aggregators per IFA / hitter / pitcher subset. The 3-input
                # composite (WAG + WAR/yr + cumulative WAR) is the v3 leaf
                # score for IFA Performance + Hitter MLB Production + Pitcher
                # MLB Production. Captures peak rate (WAR/yr) and total
                # impact (cumulative WAR), not just the WAG expectation delta.
                "ifa_war_per_yr_sum":  0.0, "ifa_war_per_yr_count":  0,
                "ifa_career_war_sum":  0.0, "ifa_career_war_count":  0,
                "hit_war_per_yr_sum":  0.0, "hit_war_per_yr_count":  0,
                "hit_career_war_sum":  0.0, "hit_career_war_count":  0,
                "pit_war_per_yr_sum":  0.0, "pit_war_per_yr_count":  0,
                "pit_career_war_sum":  0.0, "pit_career_war_count":  0,
                # BOOM / BUST counters — populated below from
                # _compute_boom_bust. boom_pct / bust_pct rollups use these
                # to surface per-org "developmental tail" rates on farm cards.
                "boom_count":      0,
                "bust_count":      0,
                "settled_count":   0,   # boom + bust + settled (i.e. excluded "unsettled")
                # v4 top-end / financial inputs.
                # _top_grads:  list of (career_war, war_per_yr, season_count, is_pitcher, last_mlb_year) for grads
                #              that clear the boom-bust sample floor. Used for
                #              top-3 grad WAR + Conviction leaf.
                # _draft_pool_grads:  list of (draft_year, career_war) — fuels
                #                     fin_draft_pool_efficiency leaf.
                # _ifa_grads:         list of (signed_year, bonus_usd, career_war)
                #                     — fuels fin_ifa_roi leaf.
                "_top_grads":         [],
                "_draft_pool_grads":  [],
                "_ifa_grads":         [],
                # v30.8 — Per-method star/grad counters for the Acquisition
                # Deviation league pass. Keyed by method (draft, international_fa,
                # trade, waiver, rule_5, contract_purchase, free_agent). A "star"
                # grad is one whose career WAR/yr ≥ 3.0 OR any single MLB
                # season ≥ 3.5 WAR (mirrors the Conviction leaf's star
                # thresholds, so the two grade signals stay aligned).
                "_method_grad_counts": {},
                "_method_star_counts": {},
                # v31.5 — Per-channel WAR + bonus accumulators for the
                # Financial WAR per $M leaf's sub-leaf split. Lets the
                # tree show "this org's $/WAR came from draft signings vs
                # IFA bonuses" instead of one aggregate number. Each grad
                # with both a bonus AND career WAR routes into exactly one
                # channel based on their acquisition method.
                "war_sum_draft":      0.0, "bonus_sum_draft": 0,
                "war_sum_ifa":        0.0, "bonus_sum_ifa":   0,
                "war_sum_other":      0.0, "bonus_sum_other": 0,
                "grad_count_draft":   0,
                "grad_count_ifa":     0,
                "grad_count_other":   0,
                # v31.5 — Sleeper development counters per acquisition
                # method. A "sleeper" grad is one whose FV-at-acquisition
                # (fv_open on the PlayerTimeseries) was ≤45 AND who went
                # on to clear ≥2.0 WAR/yr in MLB. Sleeper hit rate =
                # sleepers / low-FV-acquisitions per method. Higher =
                # better at finding talent that wasn't obvious upfront.
                "sleeper_low_fv_draft": 0, "sleeper_hit_draft": 0,
                "sleeper_low_fv_ifa":   0, "sleeper_hit_ifa":   0,
                # v31.5 — Per-position-bucket Production accumulators.
                # Splits the existing hit_war_per_yr_* + pit_war_per_yr_*
                # totals by position bucket (C/INF/OF for hitters,
                # SP/RP for pitchers) so MLB Hitter/Pitcher Production
                # can surface per-bucket sub-leaves. Each grad lands in
                # exactly one bucket based on their position.
                "hit_war_per_yr_sum_C":   0.0, "hit_war_per_yr_count_C":   0,
                "hit_war_per_yr_sum_INF": 0.0, "hit_war_per_yr_count_INF": 0,
                "hit_war_per_yr_sum_OF":  0.0, "hit_war_per_yr_count_OF":  0,
                "pit_war_per_yr_sum_SP":  0.0, "pit_war_per_yr_count_SP":  0,
                "pit_war_per_yr_sum_RP":  0.0, "pit_war_per_yr_count_RP":  0,
                # v31.1 — Draft round-tier + IFA bonus-tier accumulators.
                # Feed the new sub-leaf league pass that letter-grades each
                # tier's WAR/yr mean across the league. Tiers:
                #   draft_r1     : pick_round == 1
                #   draft_day1   : pick_round in 2..10 (Day 1 + early Day 2)
                #   draft_late   : pick_round >= 11
                #   ifa_top      : bonus_usd ≥ $2M
                #   ifa_mid      : $500K ≤ bonus_usd < $2M
                #   ifa_lower    : bonus_usd < $500K OR missing
                # WAR/yr sums (and counts) are aggregated per grad whose
                # acquisition method + tier criteria match. WAR/yr ≥ 0
                # required so unsigned grads don't slip in.
                "draft_r1_war_per_yr_sum":     0.0, "draft_r1_war_per_yr_count":     0,
                "draft_day1_war_per_yr_sum":   0.0, "draft_day1_war_per_yr_count":   0,
                "draft_late_war_per_yr_sum":   0.0, "draft_late_war_per_yr_count":   0,
                "ifa_top_war_per_yr_sum":      0.0, "ifa_top_war_per_yr_count":      0,
                "ifa_mid_war_per_yr_sum":      0.0, "ifa_mid_war_per_yr_count":      0,
                "ifa_lower_war_per_yr_sum":    0.0, "ifa_lower_war_per_yr_count":    0,
        }

    grad_agg: dict[str, dict] = {}
    for gp in grads:
        if not gp.points:
            continue
        # Resolve graduate's display org via the same helper actives use,
        # falling back to the player's source org if needed.
        gp_org = canonical_org(
            _latest_post_graduation_org(gp, []) or
            graduate_mlb_org_by_key.get(gp.player_key) or
            roster_org_by_key.get(gp.player_key) or
            gp.org
        )
        if not gp_org and (_dev_attr is None or _dev_attr.get(gp.player_key) is None):
            continue
        # Build a minimal payload that _grad_wag can read. Pass through
        # the player's position so the rate-based WAG picks the right
        # pitcher/hitter expected-WAR-per-yr table.
        cw = (career_war or {}).get(gp.player_key) or {}
        fv_close_raw = (round(gp.points[-1].consensus_fv_raw, 2)
                        if gp.points else None)
        # WAG baseline = eFV (WAR Above GRADE; the grade is now eFV), falling back to
        # consensus where eFV abstains. _grad_wag reads fv_close_raw -> fv_close.
        _gp_xfv = (_xfv_by_key.get(gp.player_key) or {}).get("xfv_grade")
        _wag_fv_raw = _gp_xfv if _gp_xfv is not None else fv_close_raw
        gp_bd = birth_dates.get(gp.player_key)
        gp_age = compute_age_decimal(gp_bd)
        gp_current_level = roster_level_by_key.get(gp.player_key)
        # One helper returns BOTH the display WAG and the GRADED boom/bust label
        # (audit L13-04: they used to read two different grades thirty lines apart).
        # Flag off: the two legacy calls, unchanged. Flag on: the baked engine block.
        wag, boom_label = _farm_grad_wag_and_label(
            {
                "career_war":   cw,
                "fv_close_raw": _wag_fv_raw,
                "fv_close":     (_gp_xfv if _gp_xfv is not None else gp.fv_close),
                "position":     gp.position,
                "career_stats": career_stats.get(gp.player_key, []),
                "transactions": transactions_by_player.get(gp.player_key, []),
                "age":          gp_age,
                "current_level": gp_current_level,
            },
            {
                "career_war":   cw,
                "fv_close_raw": fv_close_raw,
                "fv_close":     gp.fv_close,
                "career_stats": (career_stats or {}).get(gp.player_key, []) or [],
            },
            (_debuted_block_for(gp) if WAG_UNIFIED else None))
        career_war_val = cw.get("career_war")
        gp_acq = (acquisitions or {}).get(gp.player_key, {}) or {}
        bonus_usd = gp_acq.get("bonus_usd")
        gp_method = gp_acq.get("method")  # "draft" | "international_fa" | "unknown"
        gp_is_pitcher = bool(gp.position
                             and gp.position.split("/")[0] in PITCHER_POS)
        gp_contract = (contracts_by_key or {}).get(gp.player_key) or {}
        gp_aav = gp_contract.get("aav_usd")

        # VAL_4 (owner answer FP2-4, 2026-09-25): the graduate is credited to the
        # clubs that developed him, not the club he plays for now. dev_attribution
        # cuts his pre-debut history into org tenures and gives each club its share
        # (acquisition value to the signing club, tenure growth to each developing
        # club; docs/farm-attribution-2026-09-25/DEVELOPMENT_ATTRIBUTION.md). He
        # enters each club pool with weight _w. Acquisition-channel accumulators
        # (draft and IFA splits, bonus, slot, pools, method counts) read _acq_method
        # and _acq_bonus, which are set only at the signing club. Without an
        # attribution the current club takes the whole share, as before.
        _credit = (_dev_attr.graduate_credit(gp.player_key, gp_org)
                   if _dev_attr is not None else [(gp_org, 1.0, True)])
        for _c_org, _w, _is_sign in _credit:
            if not _c_org or _w <= 0:
                continue
            _acq_method = gp_method if _is_sign else None
            _acq_bonus = bonus_usd if _is_sign else None
            bucket = grad_agg.setdefault(_c_org, _new_grad_bucket())
            # Boom/Bust classification for this graduate (computed above with the WAG).
            career_rows = (career_stats or {}).get(gp.player_key, []) or []
            if boom_label == "boom":
                bucket["boom_count"] += _w
                bucket["settled_count"] += _w
            elif boom_label == "bust":
                bucket["bust_count"] += _w
                bucket["settled_count"] += _w
            elif boom_label == "settled":
                bucket["settled_count"] += _w
            if wag is not None:
                bucket["wag_sum"] += _w * (wag)
                bucket["wag_count"] += _w
                # Acquisition-method split
                if _acq_method == "international_fa":
                    bucket["ifa_wag_sum"] += _w * (wag)
                    bucket["ifa_wag_count"] += _w
                elif _acq_method == "draft":
                    bucket["draft_wag_sum"] += _w * (wag)
                    bucket["draft_wag_count"] += _w
                # Position split for MLB Production branch
                if gp_is_pitcher:
                    bucket["pit_wag_sum"] += _w * (wag)
                    bucket["pit_wag_count"] += _w
                else:
                    bucket["hit_wag_sum"] += _w * (wag)
                    bucket["hit_wag_count"] += _w
            if career_war_val is not None:
                bucket["war_sum"] += _w * (float(career_war_val))
                bucket["war_count"] += _w
            # Tree v3 — cumulative WAR + WAR-per-year splits for IFA /
            # Hitter / Pitcher subsets. Per `career_war` payload shape:
            # `career_war` (total) + `war_per_yr` (career_war /
            # war_seasons_count). The 3-input composite at the leaf level
            # blends WAG + WAR/yr + cumulative WAR equally.
            war_per_yr = cw.get("war_per_yr")
            if career_war_val is not None or war_per_yr is not None:
                cval = float(career_war_val) if career_war_val is not None else None
                yval = float(war_per_yr)     if war_per_yr     is not None else None
                if _acq_method == "international_fa":
                    if cval is not None:
                        bucket["ifa_career_war_sum"]  += _w * (cval)
                        bucket["ifa_career_war_count"] += _w
                    if yval is not None:
                        bucket["ifa_war_per_yr_sum"]   += _w * (yval)
                        bucket["ifa_war_per_yr_count"] += _w
                if gp_is_pitcher:
                    if cval is not None:
                        bucket["pit_career_war_sum"]  += _w * (cval)
                        bucket["pit_career_war_count"] += _w
                    if yval is not None:
                        bucket["pit_war_per_yr_sum"]   += _w * (yval)
                        bucket["pit_war_per_yr_count"] += _w
                else:
                    if cval is not None:
                        bucket["hit_career_war_sum"]  += _w * (cval)
                        bucket["hit_career_war_count"] += _w
                    if yval is not None:
                        bucket["hit_war_per_yr_sum"]   += _w * (yval)
                        bucket["hit_war_per_yr_count"] += _w
                # v31.5 — Sleeper development tracking. Grades each org's
                # ability to find ≥2 WAR/yr graduates from low-FV
                # (≤45 fv_open) acquisitions. Only fires for draft / IFA
                # method grads; trade / waiver acquisitions are excluded
                # since the org isn't doing initial scouting on those.
                _fv_open = getattr(gp, "fv_open", None)
                if _fv_open is not None and float(_fv_open) <= 45.0:
                    if _acq_method == "draft":
                        bucket["sleeper_low_fv_draft"] += _w
                        if yval is not None and float(yval) >= 2.0:
                            bucket["sleeper_hit_draft"] += _w
                    elif _acq_method == "international_fa":
                        bucket["sleeper_low_fv_ifa"] += _w
                        if yval is not None and float(yval) >= 2.0:
                            bucket["sleeper_hit_ifa"] += _w
                # v31.5 — Per-position-bucket production split. Routes
                # this grad's WAR/yr into the right C/INF/OF (hitter) or
                # SP/RP (pitcher) bucket so the Production leaves can
                # break their grade out by position type.
                if yval is not None:
                    _grad_bucket = _pos_bucket_v2(gp.position)
                    if _grad_bucket in ("C", "INF", "OF"):
                        bucket[f"hit_war_per_yr_sum_{_grad_bucket}"]   += _w * (yval)
                        bucket[f"hit_war_per_yr_count_{_grad_bucket}"] += _w
                    elif _grad_bucket in ("SP", "RP"):
                        bucket[f"pit_war_per_yr_sum_{_grad_bucket}"]   += _w * (yval)
                        bucket[f"pit_war_per_yr_count_{_grad_bucket}"] += _w
                # v31.1 — Draft round-tier + IFA bonus-tier per-grad WAR/yr
                # accumulators. Only fires when WAR/yr is on file (graduate
                # has a non-empty MLB career). Tiers are mutually exclusive
                # within method, so a grad lands in exactly one tier bucket.
                if yval is not None and _acq_method == "draft":
                    _round = gp_acq.get("pick_round")
                    if isinstance(_round, int) and _round >= 1:
                        if _round == 1:
                            bucket["draft_r1_war_per_yr_sum"]   += _w * (yval)
                            bucket["draft_r1_war_per_yr_count"] += _w
                        elif _round <= 10:
                            bucket["draft_day1_war_per_yr_sum"]   += _w * (yval)
                            bucket["draft_day1_war_per_yr_count"] += _w
                        else:
                            bucket["draft_late_war_per_yr_sum"]   += _w * (yval)
                            bucket["draft_late_war_per_yr_count"] += _w
                if yval is not None and _acq_method == "international_fa":
                    _bonus = gp_acq.get("bonus_usd")
                    _bonus_n = float(_bonus) if _bonus else 0.0
                    if _bonus_n >= 2_000_000:
                        bucket["ifa_top_war_per_yr_sum"]   += _w * (yval)
                        bucket["ifa_top_war_per_yr_count"] += _w
                    elif _bonus_n >= 500_000:
                        bucket["ifa_mid_war_per_yr_sum"]   += _w * (yval)
                        bucket["ifa_mid_war_per_yr_count"] += _w
                    else:
                        bucket["ifa_lower_war_per_yr_sum"]   += _w * (yval)
                        bucket["ifa_lower_war_per_yr_count"] += _w
            if _acq_bonus is not None:
                bucket["bonus_sum"] += int(_acq_bonus)
                bucket["bonus_count"] += 1
                # v31.5 — Channel split: route this grad's bonus + WAR
                # into the right channel bucket so the WAR/$M leaf can
                # surface a per-channel sub-leaf breakdown (Draft / IFA /
                # Other). career_war_val may be None — handled below by
                # checking before incrementing the WAR sum.
                _chan = "other"
                if _acq_method == "draft":
                    _chan = "draft"
                elif _acq_method == "international_fa":
                    _chan = "ifa"
                bucket[f"bonus_sum_{_chan}"] += int(_acq_bonus)
                bucket[f"grad_count_{_chan}"] += _w
                if career_war_val is not None:
                    bucket[f"war_sum_{_chan}"] += _w * (float(career_war_val))
            # Grad-Contract Surplus accumulator. 6-year amortization mirrors
            # the typical pre-FA cost-controlled window for a graduate; longer
            # extensions get credited yearly via aav_usd, not the bonus.
            if gp_aav and bonus_usd:
                try:
                    surplus_yr = float(gp_aav) - (float(bonus_usd) / 6.0)
                    bucket["contract_surplus_sum"]   += _w * (surplus_yr)
                    bucket["contract_surplus_count"] += _w
                except (TypeError, ValueError):
                    pass
            # Pick-slot-adjusted draft value (v2 of Acquisitions/Draft).
            # Requires both a draft method AND a numeric pick_overall AND a
            # career_war on file. The delta is positive when the org
            # extracted more MLB value from that pick slot than the league
            # historically gets — credits late-round hits more than #1
            # overalls reaching the majors. Falls back silently when any
            # piece is missing (Spotrac-only graduates, IFA signings, etc.)
            if _acq_method == "draft" and career_war_val is not None:
                slot_exp = _pick_slot_expected_war(gp_acq.get("pick_overall"))
                if slot_exp is not None:
                    bucket["draft_pick_value_sum"]   += _w * (float(career_war_val) - slot_exp)
                    bucket["draft_pick_value_count"] += _w

            # v4 — top-end / financial lists.
            # Top-3 grad list: only grads that clear the boom_bust sample
            # v15 — Relax the gate. Previously required boom/bust/settled label
            # (which itself requires 800 PA / 200 IP / 2 seasons floor — most
            # recent graduates won't clear that). Now any graduate with a
            # populated career_war qualifies for _top_grads; the leaf still
            # gates on ≥3 grads to produce a meaningful top-3 statistic.
            if career_war_val is not None:
                yval = cw.get("war_per_yr")
                seasons = cw.get("war_seasons_count") or 0
                # Find last MLB year for Conviction's 6-year recency window.
                mlb_seasons = [int(r.get("season") or 0)
                               for r in career_rows
                               if (r.get("level") == "MLB" and r.get("season"))]
                last_mlb_year = max(mlb_seasons) if mlb_seasons else None
                # v30.8 — Peak single-season WAR for the star-evaluation
                # path (Conviction + Acq Deviation use ≥3.5 single-season
                # WAR as a star threshold). seasons may be a {year: war}
                # dict (FanGraphs career_war shape) or sparser.
                season_peak = 0.0
                _seasons_dict = cw.get("seasons")
                try:
                    if isinstance(_seasons_dict, dict):
                        _vals = [float(v) for v in _seasons_dict.values()
                                 if v is not None and float(v) == float(v)]
                        if _vals:
                            season_peak = max(_vals)
                except (TypeError, ValueError):
                    pass
                bucket["_top_grads"].append({
                    "w":            _w,
                    "player_name": gp.player_name,
                    "player_key":  gp.player_key,
                    "career_war":   float(career_war_val),
                    "war_per_yr":   float(yval) if yval is not None else None,
                    "seasons":      _seasons_dict if isinstance(_seasons_dict, dict) else int(seasons),
                    "season_peak":  round(season_peak, 2),
                    "is_pitcher":   gp_is_pitcher,
                    "last_mlb_year": last_mlb_year,
                    # v30.8 — Acquisition method for per-method star-rate
                    # aggregation in the Acq Deviation league pass.
                    "method":       gp_method,
                })
                # v30.8 — Per-method counters for Acquisition Deviation.
                # Every grad with WAR data counts toward the method's
                # grad_count denominator; grads who hit the star threshold
                # add to the numerator.
                if _acq_method:
                    bucket["_method_grad_counts"][_acq_method] = \
                        bucket["_method_grad_counts"].get(_acq_method, 0) + _w
                    _is_star = ((yval is not None and float(yval) >= _STAR_WAR_PER_YR_THRESHOLD)
                                or (season_peak >= _STAR_SEASON_WAR_THRESHOLD))
                    if _is_star:
                        bucket["_method_star_counts"][_acq_method] = \
                            bucket["_method_star_counts"].get(_acq_method, 0) + _w
            # Draft-pool efficiency: grads drafted via the draft method,
            # tagged with their draft year + career WAR. The leaf-level
            # computation joins these to the per-year draft pool spend.
            if _acq_method == "draft" and career_war_val is not None:
                dy = gp_acq.get("year")
                if dy is not None:
                    bucket["_draft_pool_grads"].append({
                        "w":            _w,
                        "draft_year": int(dy),
                        "career_war": float(career_war_val),
                    })
            # IFA ROI: grads signed via IFA, tagged with their signing year
            # + (optional) bonus + career WAR.
            # v22 — Dropped the per-grad `bonus_usd` requirement. The
            # downstream `_compute_ifa_roi` uses org-level IFA spend from
            # `ifa_org_spending` as the denominator (Spotrac), not per-grad
            # bonus sums. Filtering grads out for missing bonus_usd was the
            # real bottleneck — only 23 of 492 debuted IFAs had bonus on
            # file, leaving 18 orgs with zero contributors. Now every IFA
            # debut with career WAR + signing year counts toward the
            # numerator.
            if _acq_method == "international_fa" and career_war_val is not None:
                sy = gp_acq.get("year")
                if sy is not None:
                    bucket["_ifa_grads"].append({
                        "w":            _w,
                        "signed_year": int(sy),
                        "bonus_usd":   int(bonus_usd) if bonus_usd else 0,
                        "career_war":  float(career_war_val),
                    })

    # VAL_4: share-weighted counts are graduate-equivalents. A whole count stays an
    # int (a club that developed its graduates alone serves the same integers as
    # before); a fractional one is kept to 4 decimals.
    def _tidy_count(v):
        if isinstance(v, float):
            return int(v) if v.is_integer() else round(v, 4)
        return v
    for _gb in grad_agg.values():
        for _k, _v in list(_gb.items()):
            if _k.endswith("_count") or _k.startswith(("sleeper_", "grad_count_")):
                _gb[_k] = _tidy_count(_v)
            elif _k in ("_method_grad_counts", "_method_star_counts"):
                _gb[_k] = {mk: _tidy_count(mv) for mk, mv in _v.items()}

    # Finalize each org entry
    org_summary = []
    for org, m in sorted(org_map.items()):
        ages = m.pop("ages")
        m["count"] = len(m["prospects"])
        m["total_fv"] = round(m["total_fv"], 1)
        m["avg_age"] = round(sum(ages) / len(ages), 1) if ages else None
        m["top_prospect"] = m["prospects"][0] if m["prospects"] else None
        m["youngest"] = min(m["prospects"], key=lambda x: x["age"] if x["age"] else 99) if m["prospects"] else None

        # ── Farm Overhaul: per-org extended report-card aggregates ──
        # Talent Translation (WAG) — mean of grad WAG values. Orgs with
        # fewer than 3 graduates with valid WAG get None so they grade
        # as "—" rather than D (no data isn't the same as bad data).
        gagg = grad_agg.get(org) or {}
        wag_count = gagg.get("wag_count") or 0
        # BOOM / BUST per-org rates. Settled count = booms + busts +
        # settled (i.e. graduates that cleared the 800-PA/200-IP/2-season
        # sample floor). Min 5 settled grads or None — small-sample orgs
        # get "—" rather than a noisy %.
        settled_count = gagg.get("settled_count") or 0
        if settled_count >= 5:
            boom_pct = round(100.0 * (gagg.get("boom_count") or 0) / settled_count, 1)
            bust_pct = round(100.0 * (gagg.get("bust_count") or 0) / settled_count, 1)
        else:
            boom_pct = None
            bust_pct = None
        m["talent_translation"] = {
            "wag_mean": (round(gagg["wag_sum"] / wag_count, 2)
                         if wag_count >= 3 else None),
            "wag_sum":  round(gagg.get("wag_sum") or 0.0, 2),
            "grad_count": wag_count,
            "boom_pct":      boom_pct,
            "bust_pct":      bust_pct,
            "boom_count":    gagg.get("boom_count") or 0,
            "bust_count":    gagg.get("bust_count") or 0,
            "settled_count": settled_count,
        }
        # Financial ROI — WAR per million USD spent on the grads who
        # have both signing bonus AND career WAR on file. The numerator
        # MUST be paired with the denominator: summing ALL grads' WAR
        # over only the bonus-covered dollars inflated the ratio by up
        # to ~34x for orgs whose stars predate bonus coverage (LAD read
        # 21.1 WAR/$M on a true paired ~0.61) and ranked orgs by data
        # coverage, not ROI. The per-channel sums (war_sum_draft/ifa/
        # other) accumulate only inside the bonus-covered branch, so
        # their total IS the paired numerator.
        bonus_sum = gagg.get("bonus_sum") or 0
        war_sum = gagg.get("war_sum") or 0.0
        paired_war = sum(gagg.get(f"war_sum_{c}") or 0.0
                         for c in ("draft", "ifa", "other"))
        # v40 — total realized graduate WAR (raw MLB production) exposed for the
        # farm tiebreaker score. Sum of career bWAR across ALL the org's
        # graduates (deliberately NOT bonus-paired: realized output, not ROI).
        m["_grad_war_total"] = round(war_sum, 2)
        m["financial_roi"] = {
            "war_per_million": (round(paired_war / (bonus_sum / 1_000_000), 3)
                                if bonus_sum >= 1_000_000 else None),
            "total_career_war":  round(paired_war, 2),
            "total_career_war_all_grads": round(war_sum, 2),
            "total_bonus_usd":   bonus_sum,
            "grad_count_with_bonus": gagg.get("bonus_count") or 0,
        }
        # Tool Quality — top-10 mean of raw composite_overall (the
        # 20-80 power-mean of per-tool grades, identical to the per-
        # prospect Tool composite). Top-10 (not all) so a top-heavy
        # farm with raw-tools stars isn't dragged down by un-graded
        # depth. The value is on the 20-80 scale — see Tool Quality
        # glossary entry for why this beats a z-scored aggregate.
        _comp_overalls = sorted(m.pop("_tools_comp_overall", []) or [], reverse=True)
        m["tools_quality"] = {
            "top10_mean":  round(sum(_comp_overalls[:10]) / len(_comp_overalls[:10]), 2)
                            if _comp_overalls else None,
            "mean":        round(sum(_comp_overalls) / len(_comp_overalls), 2)
                            if _comp_overalls else None,
            "graded_count": len(_comp_overalls),
        }
        # v29 — Statcast Quality leaf. Mean Statcast+ across the farm's
        # active prospects who have tracked Statcast/zone data, plus
        # raw counts (graded_count = how many contributed to the mean;
        # min 5 graded prospects required before the org-mean shows so
        # tiny samples don't surface as outliers). The accompanying
        # upside / breakout counts ride alongside so the UI can sort or
        # tooltip on indicator depth without re-deriving from the
        # active payload.
        _sc_vals = m.pop("_sc_plus", []) or []
        _sc_hit_vals = m.pop("_sc_plus_hit", []) or []
        _sc_pit_vals = m.pop("_sc_plus_pit", []) or []
        # v30.7 — Per-bucket SC+ values for the position-bucketed
        # StatcastDvM+. Pop here so the bucket dict makes the
        # round-trip from m → entry. Min-3 gate on the bucket means
        # before it gets a value (vs the ≥5 gate on the org-wide
        # mean) — buckets are smaller cohorts so a tighter floor is
        # appropriate, especially for catcher / RP slivers.
        _sc_by_bucket = m.pop("_sc_plus_by_bucket", {}) or {}
        m["_pos_bucket_sc_means"] = {
            bucket: (round(sum(vals) / len(vals), 2) if len(vals) >= 3 else None)
            for bucket, vals in _sc_by_bucket.items()
        }
        m["_pos_bucket_sc_counts"] = {bucket: len(vals) for bucket, vals in _sc_by_bucket.items()}
        _scq_graded = len(_sc_vals)
        # v30.5 — Per-side aggregates ride alongside the all-prospects
        # mean. Same ≥5 graded-prospects gate per side so a 1-pitcher
        # outlier doesn't dominate the pitcher mean (gate is per-side,
        # not org-wide). hitter_count / pitcher_count expose the
        # sample size so the UI can dim a side with thin coverage.
        _scq_hit = len(_sc_hit_vals)
        _scq_pit = len(_sc_pit_vals)
        m["statcast_quality"] = {
            "mean":          round(sum(_sc_vals) / _scq_graded, 2) if _scq_graded >= 5 else None,
            "graded_count":  _scq_graded,
            "hitter_mean":   round(sum(_sc_hit_vals) / _scq_hit, 2) if _scq_hit >= 5 else None,
            "hitter_count":  _scq_hit,
            "pitcher_mean":  round(sum(_sc_pit_vals) / _scq_pit, 2) if _scq_pit >= 5 else None,
            "pitcher_count": _scq_pit,
            "upside_count":  m.pop("_upside_count", 0),
            # breakout_count gets filled in the post-serialization
            # second pass below (the flag is computed there).
            "breakout_count": 0,
        }
        # International Depth — IFA % and year-span across actives.
        n_actives = len(m["prospects"]) or 1
        ifa_year_span = len(set(m.pop("_ifa_years") or []))
        ifa_count = m.pop("_ifa_count") or 0
        m["international_depth"] = {
            "ifa_pct":  round(ifa_count / n_actives, 3) if n_actives else 0,
            "ifa_count": ifa_count,
            "year_span": ifa_year_span,
        }
        # Readiness — (very_young - very_old) / total actives. Can go
        # negative for organizationally over-age systems.
        m["readiness"] = {
            "pct_signal":       round((m["very_young_count"] - m["very_old_count"]) / n_actives, 3),
            "very_young_count": m["very_young_count"],
            "very_old_count":   m["very_old_count"],
        }
        # Health burden (LOWER IS BETTER on the scoring inputs).
        # v31.6 — Post-TJ removed from the scoring composite (it's
        # now informational only — post-surgery grace period often
        # leads to above-avg outcomes for pitchers, and the rate is
        # mostly a function of past-injury exposure rather than
        # current development quality). The `score` field still
        # mixes post-TJ for back-compat with older payloads but the
        # Health Mgmt LEAF_SPECS no longer reads it.
        post_tj_count = m.pop("_post_tj_count") or 0
        il_days_sum = m.pop("_il_days_sum") or 0
        il_days_count = m.pop("_il_days_count") or 0
        il_current_count = m.pop("_il_current_count") or 0
        # v31.1 — Per-side health counters. v31.6 — Hitter post-TJ
        # tracking removed (hitter TJ isn't a real signal). Pitcher
        # post-TJ retained as informational context only.
        post_tj_count_pit = m.pop("_post_tj_count_pit") or 0
        il_current_count_pit = m.pop("_il_current_count_pit") or 0
        il_current_count_hit = m.pop("_il_current_count_hit") or 0
        actives_pit_count = m.pop("_actives_pit_count") or 0
        actives_hit_count = m.pop("_actives_hit_count") or 0
        post_tj_pct = post_tj_count / n_actives if n_actives else 0
        il_days_mean = (il_days_sum / il_days_count) if il_days_count else 0
        il_pct_current = (il_current_count / n_actives) if n_actives else 0
        post_tj_pct_pit = (post_tj_count_pit / actives_pit_count) if actives_pit_count else None
        il_pct_current_pit = (il_current_count_pit / actives_pit_count) if actives_pit_count else None
        il_pct_current_hit = (il_current_count_hit / actives_hit_count) if actives_hit_count else None
        m["health_burden"] = {
            "score":       round(100 * post_tj_pct + il_days_mean, 2),
            "post_tj_pct": round(post_tj_pct, 3),
            "il_days_mean": round(il_days_mean, 1),
            "post_tj_count": post_tj_count,
            "il_pct_current": round(il_pct_current, 3),
            "il_current_count": il_current_count,
            "active_count": n_actives,
            # Per-side splits (None when that side has zero actives).
            "post_tj_pct_pit":    round(post_tj_pct_pit, 3) if post_tj_pct_pit is not None else None,
            "il_pct_current_pit": round(il_pct_current_pit, 3) if il_pct_current_pit is not None else None,
            "il_pct_current_hit": round(il_pct_current_hit, 3) if il_pct_current_hit is not None else None,
            "actives_pit_count":  actives_pit_count,
            "actives_hit_count":  actives_hit_count,
        }
        # Per-tool development — mean lifetime delta across actives that
        # have ≥2 consensus observations of each tool. Sparse-data gate:
        # tools with fewer than 3 contributing prospects are dropped (a
        # 1-prospect mean is too noisy to compare across orgs). The
        # per-tool DvM+ + composite ToolsDvM+ are computed in a second
        # league-wide pass below, once every org's mean_delta is known.
        _tool_sums = m.pop("_tool_dev_sums") or {}
        # VAL_4: tenure tool growth credited to this club (by any prospect it
        # held, including one it has since traded away).
        for _tk, _vals in (_tenure_tool_sums.get(org) or {}).items():
            _tool_sums.setdefault(_tk, []).extend(_vals)
        per_tool: dict[str, dict] = {}
        for _tk, _deltas in _tool_sums.items():
            if len(_deltas) < 3:
                continue
            per_tool[_tk] = {
                "mean_delta":  round(sum(_deltas) / len(_deltas), 2),
                "n_prospects": len(_deltas),
            }
        # v30.8 — Per-bucket per-tool aggregates. Same n≥3 gate as the
        # org-wide aggregator above so sparse cells stay None (the
        # downstream hybrid policy falls back to org-side-wide tool
        # DvM+ for those cells, so dropping a noisy bucket here doesn't
        # leave the UI blank).
        _tool_sums_by_bucket = m.pop("_tool_dev_sums_by_bucket") or {}
        for _bk, _tdict in (_tenure_tool_sums_by_bucket.get(org) or {}).items():
            for _tk, _vals in _tdict.items():
                _tool_sums_by_bucket.setdefault(_bk, {}).setdefault(_tk, []).extend(_vals)
        per_tool_by_bucket: dict[str, dict[str, dict]] = {}
        for _bucket, _tool_dict in _tool_sums_by_bucket.items():
            _bucket_pertool: dict[str, dict] = {}
            for _tk, _deltas in _tool_dict.items():
                if len(_deltas) < 3:
                    continue
                _bucket_pertool[_tk] = {
                    "mean_delta":  round(sum(_deltas) / len(_deltas), 2),
                    "n_prospects": len(_deltas),
                }
            if _bucket_pertool:
                per_tool_by_bucket[_bucket] = _bucket_pertool
        m["tool_dev"] = {
            "per_tool":          per_tool,
            "per_tool_dvm_plus": {},   # filled in the league pass below
            "tools_dvm_plus":    None,
            # v30.8 — Per-bucket structures populated in a parallel
            # league pass below; the bucket Tool DvM+ aggregate lands
            # on the dev_hitter / dev_pitcher pos_buckets node.
            "per_tool_by_bucket":         per_tool_by_bucket,
            "per_tool_dvm_plus_by_bucket": {},  # filled in the league pass below
        }

        # ── Farm Grade Tree v2 sub-grades — leaf-level metrics ──
        # All grade-tree leaves get their underlying values stamped here.
        # The 100-anchored league-normalized versions + composites are
        # computed in a separate pass below (once league mean+stdev are
        # known across every org's leaf values). Sparse-data gates apply
        # at the leaf level (count threshold per leaf).
        _wag_sum = gagg.get("wag_sum") or 0.0
        # Helper: gated mean per (sum_key, count_key, min_count).
        def _gated_mean(sk, ck, gate=3, prec=2):
            n = gagg.get(ck) or 0
            return round(gagg[sk] / n, prec) if n >= gate else None
        # Draft Ceiling Hits — % of recent (≤3yr) drafted actives with FV ≥ 60.
        _draft_actives_n = m.pop("_draft_actives_count", 0) or 0
        _draft_ceiling_n = m.pop("_draft_ceiling_hits",  0) or 0
        _draft_ceiling_pct = (round(_draft_ceiling_n / _draft_actives_n, 3)
                              if _draft_actives_n >= 3 else None)
        # v30.8 — Per-method star rate for the Acquisition Deviation
        # league pass. Stamped on each acq leaf below; the deviation
        # vs league median is computed once all orgs are in hand.
        _method_grad_cts = gagg.get("_method_grad_counts") or {}
        _method_star_cts = gagg.get("_method_star_counts") or {}
        def _method_star_rate(method: str) -> tuple[float | None, int, int]:
            """Returns (star_rate, star_count, grad_count) for a method.
            Returns (None, 0, 0) when the method has fewer than 3 grads
            (below that the rate is too noisy to compare to peers)."""
            gc = _method_grad_cts.get(method, 0)
            sc = _method_star_cts.get(method, 0)
            if gc < 3:
                return (None, sc, gc)
            return (round(sc / gc, 3), sc, gc)
        _ifa_star_rate, _ifa_star_n, _ifa_grad_n = _method_star_rate("international_fa")
        _draft_star_rate, _draft_star_n, _draft_grad_n = _method_star_rate("draft")
        m["tree"] = {
            # ACQUISITION STRATEGY branch (v3 — merged Acquisitions + Transactions).
            # IFA Performance — 3-input composite. WAG + WAR-per-year +
            # cumulative WAR over IFA-method graduates. Captures expectation
            # delta, peak rate, and total impact.
            "acq_ifa": {
                "wag_mean":         _gated_mean("ifa_wag_sum",        "ifa_wag_count"),
                "war_per_yr_mean":  _gated_mean("ifa_war_per_yr_sum", "ifa_war_per_yr_count"),
                "career_war_mean":  _gated_mean("ifa_career_war_sum", "ifa_career_war_count"),
                "wag_sum":   round(gagg.get("ifa_wag_sum") or 0.0, 2),
                "grad_count": gagg.get("ifa_wag_count") or 0,
                # v30.8 — Acquisition Deviation: per-method star rate +
                # deviation from league median (populated in the league
                # pass below once every org's star_rate is known).
                "star_rate":           _ifa_star_rate,
                "star_count":          _ifa_star_n,
                "star_grad_count":     _ifa_grad_n,
                "star_rate_deviation": None,   # filled in league pass
                "star_rate_league_median": None,
                # v31.5 — Sleeper development signal (IFA side).
                # Same shape as acq_draft.sleeper_*; surfaces orgs
                # that find ≥2 WAR/yr grads from lower-bonus / low-
                # FV IFA signings.
                "sleeper_hit_rate": (
                    round(gagg.get("sleeper_hit_ifa") / gagg.get("sleeper_low_fv_ifa"), 3)
                    if (gagg.get("sleeper_low_fv_ifa") or 0) >= 3 else None
                ),
                "sleeper_hit_count":     gagg.get("sleeper_hit_ifa") or 0,
                "sleeper_low_fv_count":  gagg.get("sleeper_low_fv_ifa") or 0,
                # v31.1 — Bonus-tier breakdown. Same shape as
                # acq_draft.round_tiers — per-tier WAR/yr mean grades
                # the org's hit rate inside each bonus band. Letter-
                # graded in the league pass. Note: Spotrac IFA bonus
                # coverage starts in 2021, so most pre-2021 IFA grads
                # fall into the "Lower / unknown" catchall regardless
                # of their actual bonus. Top and Mid tiers reflect the
                # subset with confirmed bonus dollars.
                "bonus_tiers": {
                    "Top (≥$2M)":               {
                        "war_per_yr_mean": _gated_mean("ifa_top_war_per_yr_sum",   "ifa_top_war_per_yr_count"),
                        "grad_count":      gagg.get("ifa_top_war_per_yr_count") or 0,
                    },
                    "Mid ($500K-$2M)":          {
                        "war_per_yr_mean": _gated_mean("ifa_mid_war_per_yr_sum",   "ifa_mid_war_per_yr_count"),
                        "grad_count":      gagg.get("ifa_mid_war_per_yr_count") or 0,
                    },
                    "Lower / unknown bonus":    {
                        "war_per_yr_mean": _gated_mean("ifa_lower_war_per_yr_sum", "ifa_lower_war_per_yr_count"),
                        "grad_count":      gagg.get("ifa_lower_war_per_yr_count") or 0,
                    },
                },
            },
            # Draft Performance — pick-slot-adjusted WAR (existing) + Draft
            # Ceiling Hits (new sub-input).
            "acq_draft": {
                "wag_mean": _gated_mean("draft_wag_sum", "draft_wag_count"),
                "wag_sum":  round(gagg.get("draft_wag_sum") or 0.0, 2),
                "pick_value_mean":  _gated_mean("draft_pick_value_sum", "draft_pick_value_count"),
                "pick_value_count": gagg.get("draft_pick_value_count") or 0,
                # New v3 sub-input — recent draft ceiling hits as a %
                # of recent drafted actives. Z-blended 50/50 with the
                # pick-slot-adjusted value at the leaf-scoring layer.
                "ceiling_hits_pct":   _draft_ceiling_pct,
                "ceiling_hits_count": _draft_ceiling_n,
                "draft_actives_count": _draft_actives_n,
                "grad_count": gagg.get("draft_wag_count") or 0,
                # v30.8 — Acquisition Deviation: per-method star rate +
                # deviation from league median (populated in the league
                # pass below once every org's star_rate is known).
                "star_rate":           _draft_star_rate,
                "star_count":          _draft_star_n,
                "star_grad_count":     _draft_grad_n,
                "star_rate_deviation": None,   # filled in league pass
                "star_rate_league_median": None,
                # v31.5 — Sleeper development signal. Hit rate on
                # low-FV (≤45 fv_open) drafted grads — captures the
                # org's ability to find ≥2 WAR/yr graduates from
                # lower-ranked picks. Gated at ≥3 low-FV grads.
                "sleeper_hit_rate": (
                    round(gagg.get("sleeper_hit_draft") / gagg.get("sleeper_low_fv_draft"), 3)
                    if (gagg.get("sleeper_low_fv_draft") or 0) >= 3 else None
                ),
                "sleeper_hit_count":   gagg.get("sleeper_hit_draft") or 0,
                "sleeper_low_fv_count": gagg.get("sleeper_low_fv_draft") or 0,
                # v31.1 — Round-tier breakdown. Each tier carries the
                # per-org WAR/yr mean across grads acquired via that
                # tier. Letter-graded in the league pass.
                "round_tiers": {
                    "1st round (R1)":      {
                        "war_per_yr_mean": _gated_mean("draft_r1_war_per_yr_sum",   "draft_r1_war_per_yr_count"),
                        "grad_count":      gagg.get("draft_r1_war_per_yr_count") or 0,
                    },
                    "Day 1 (R2-R10)":      {
                        "war_per_yr_mean": _gated_mean("draft_day1_war_per_yr_sum", "draft_day1_war_per_yr_count"),
                        "grad_count":      gagg.get("draft_day1_war_per_yr_count") or 0,
                    },
                    "Late (R11+)":         {
                        "war_per_yr_mean": _gated_mean("draft_late_war_per_yr_sum", "draft_late_war_per_yr_count"),
                        "grad_count":      gagg.get("draft_late_war_per_yr_count") or 0,
                    },
                },
            },
            # DEVELOPMENT branch — hitter/pitcher composites filled by
            # the per-tool DvM+ league pass below.
            "dev_hitter": {"dvm_plus": None, "n_groups": 0},
            "dev_pitcher": {"dvm_plus": None, "n_groups": 0},
            # Trade + Waiver scoreboards (filled by the v2 pass below).
            # In v3 these are leaves under Acquisition Strategy.
            "tx_trades":  {"net_fv": None, "fv_in": 0.0, "fv_out": 0.0,
                           "in_count": 0, "out_count": 0,
                           # v3 enhancer — fills in the WAR-delta pass below.
                           "war_delta": None, "war_in": 0.0, "war_out": 0.0},
            "tx_waivers": {"net_fv": None, "fv_in": 0.0, "fv_out": 0.0,
                           "in_count": 0, "out_count": 0,
                           # v3 enhancer — fills in the hit-rate pass below.
                           "hit_rate": None, "claims_total": 0, "claims_with_mlb": 0},
            # FINANCIAL branch — war_per_million reused from financial_roi;
            # grad-contract surplus mean computed here.
            "fin_war_per_m": (lambda _chan=lambda c: (lambda _ws=(gagg.get(f"war_sum_{c}") or 0.0),
                                                              _bs=(gagg.get(f"bonus_sum_{c}") or 0),
                                                              _n=(gagg.get(f"grad_count_{c}") or 0):
                {
                    "war_per_million": (round(_ws / (_bs / 1_000_000), 3)
                                         if _bs >= 1_000_000 and _n >= 3 else None),
                    "war_sum":         round(_ws, 2),
                    "bonus_usd":       int(_bs),
                    "grad_count":      _n,
                })(): {
                "value": m["financial_roi"]["war_per_million"],
                "grad_count": m["financial_roi"]["grad_count_with_bonus"],
                # v31.5 — Channel split sub-data. WAR/$M computed
                # per channel (Draft / IFA / Other). Gated at ≥$1M
                # AND ≥3 contributing grads so a single big bonus
                # doesn't dominate.
                "channels": {
                    "Draft $": _chan("draft"),
                    "IFA $":   _chan("ifa"),
                    "Other $": _chan("other"),
                },
            })(),
            "fin_contract_surplus": {
                "mean_usd_per_yr": (round(gagg["contract_surplus_sum"] / gagg["contract_surplus_count"], 0)
                                    if (gagg.get("contract_surplus_count") or 0) >= 3 else None),
                "grad_count": gagg.get("contract_surplus_count") or 0,
            },
            # MLB PRODUCTION branch — 3-input composites per position.
            # Hitter MLB Production blends Hitter WAG + Hitter WAR/yr +
            # v17 — Renamed mlb_hitter_wag → mlb_hitter_production and
            # mlb_pitcher_wag → mlb_pitcher_production. Primary surfaced
            # stat is now WAR/yr (was WAG). WAG moves out to a separate
            # talent_translation leaf under the same MLB Production parent.
            "mlb_hitter_production": {
                "war_per_yr_mean": _gated_mean("hit_war_per_yr_sum", "hit_war_per_yr_count"),
                "career_war_mean": _gated_mean("hit_career_war_sum", "hit_career_war_count"),
                "top3_career_war": _top3_career_war(gagg.get("_top_grads") or [], is_pitcher=False),
                # v31.5 — Per-position-bucket Hitter Production split.
                # Same WAR/yr mean as the parent leaf, just bucketed
                # so the user can see WHICH position group drove the
                # grade (e.g. an org's hitter production might be
                # carried by INF grads while C and OF lag).
                "pos_buckets": {
                    "C":   {"war_per_yr_mean": _gated_mean("hit_war_per_yr_sum_C",   "hit_war_per_yr_count_C"),
                            "grad_count":      gagg.get("hit_war_per_yr_count_C") or 0},
                    "INF": {"war_per_yr_mean": _gated_mean("hit_war_per_yr_sum_INF", "hit_war_per_yr_count_INF"),
                            "grad_count":      gagg.get("hit_war_per_yr_count_INF") or 0},
                    "OF":  {"war_per_yr_mean": _gated_mean("hit_war_per_yr_sum_OF",  "hit_war_per_yr_count_OF"),
                            "grad_count":      gagg.get("hit_war_per_yr_count_OF") or 0},
                },
                # WAG kept on the leaf for tooltip / back-compat consumers
                # but NO longer the headline stat.
                "wag_mean":        _gated_mean("hit_wag_sum",        "hit_wag_count"),
                "wag_sum":  round(gagg.get("hit_wag_sum") or 0.0, 2),
                "grad_count": gagg.get("hit_wag_count") or 0,
            },
            "mlb_pitcher_production": {
                "war_per_yr_mean": _gated_mean("pit_war_per_yr_sum", "pit_war_per_yr_count"),
                "career_war_mean": _gated_mean("pit_career_war_sum", "pit_career_war_count"),
                "top3_career_war": _top3_career_war(gagg.get("_top_grads") or [], is_pitcher=True),
                # v31.5 — Per-role Pitcher Production split (SP vs RP).
                # Same WAR/yr mean as parent, bucketed by role so the
                # user can see whether the org's pitcher production is
                # rotation-driven or bullpen-driven.
                "pos_buckets": {
                    "SP": {"war_per_yr_mean": _gated_mean("pit_war_per_yr_sum_SP", "pit_war_per_yr_count_SP"),
                           "grad_count":      gagg.get("pit_war_per_yr_count_SP") or 0},
                    "RP": {"war_per_yr_mean": _gated_mean("pit_war_per_yr_sum_RP", "pit_war_per_yr_count_RP"),
                           "grad_count":      gagg.get("pit_war_per_yr_count_RP") or 0},
                },
                "wag_mean":        _gated_mean("pit_wag_sum",        "pit_wag_count"),
                "wag_sum":  round(gagg.get("pit_wag_sum") or 0.0, 2),
                "grad_count": gagg.get("pit_wag_count") or 0,
            },
            # Back-compat aliases (one rebuild cycle) — frontends + tests
            # reading the old key names still resolve to the same data.
            "mlb_hitter_wag":  None,  # filled below from mlb_hitter_production
            "mlb_pitcher_wag": None,  # filled below from mlb_pitcher_production
            # v17 — NEW Talent Translation leaf under MLB Production. WAG-
            # based — measures how a graduate's actual MLB output compares
            # to their FV-implied baseline. Separate from raw production
            # (WAR/yr) so the two signals don't blur.
            "talent_translation": {
                "wag_mean":   _gated_mean("wag_sum",   "wag_count"),
                "wag_sum":    round(gagg.get("wag_sum") or 0.0, 2),
                "grad_count": gagg.get("wag_count") or 0,
            },
            # ── v4 new leaves ────────────────────────────────────────
            # MLB Production: top-end grads, boom%, Conviction.
            "mlb_production_boom_pct": {
                "boom_pct":      boom_pct,
                "settled_count": settled_count,
            },
            # v7 — bust_pct leaf parallel to boom_pct. Enters the MLB
            # Production composite as a NEGATIVE input (the LEAF_SPECS
            # getter below negates the value so higher bust% pulls the
            # composite DOWN). bust_count already computed by
            # _compute_boom_bust at the per-grad level.
            "mlb_production_bust_pct": {
                "bust_pct":      bust_pct,
                "settled_count": settled_count,
            },
            "mlb_production_top_grads":  _compute_top_grads_leaf(gagg),
            "mlb_production_conviction": _compute_conviction_leaf(gagg),
            # Financial: draft-pool efficiency + IFA ROI. Both pull the
            # per-year spend tables from the kwargs and join against
            # the bucket's per-grad signing-year + career_war records.
            "fin_draft_pool_efficiency": _compute_draft_pool_efficiency(
                gagg, draft_pools, org),
            "fin_ifa_roi": _compute_ifa_roi(
                gagg, ifa_spending_by_org.get(org) or {}),
            # v18 — Active-surplus leaf. Sum of FV-implied 6yr surplus
            # value across the org's actives, minus the acquisition
            # bonus paid. Surfaces orgs whose current crop projects to
            # generate more cost-controlled WAR than they spent.
            "fin_active_surplus": _finalize_active_surplus_leaf(m),
            # v38 — Item-6/7: org $DvM+ leaf. Mean of member prospects'
            # surplus-development indices (100 = league mean prospect at the
            # same FV tier). Surfaces alongside surplus on the financial detail
            # page and feeds the reweighted financial grade as fin_dollar_dvm.
            "fin_dollar_dvm": (lambda _v=m["_ddvm_vals"]: {
                "dollar_dvm_plus": (round(sum(_v) / len(_v), 1) if _v else None),
                "n": len(_v),
            })(),
            # v31 — Health Management leaf under Development. Captures
            # how well the org keeps prospects healthy / available —
            # composite of IL%-current (share of actives sidelined
            # right now), avg 12-month IL days per active, and post-
            # TJ rate (share of actives with a Tommy John in their
            # history). All three are inverted in LEAF_SPECS so a
            # LOWER burden produces a HIGHER score. Data sourced
            # straight off the org's existing health_burden roll-up
            # (computed above in the actives loop). Sparse-gated to
            # orgs with ≥10 actives so a thin-system org's single
            # IL stint doesn't dominate.
            "dev_health_mgmt": (lambda hb=m.get("health_burden") or {}: {
                "il_pct_current": hb.get("il_pct_current"),
                "post_tj_pct":    hb.get("post_tj_pct"),
                "il_days_mean":   hb.get("il_days_mean"),
                "active_count":   hb.get("active_count"),
                "il_current_count": hb.get("il_current_count"),
                "post_tj_count":    hb.get("post_tj_count"),
                # v31.1 — Per-side health splits surfaced as sub-leaves
                # of the Health Mgmt leaf. v31.6 — Hitter post-TJ
                # removed (TJ for hitters isn't a real signal); only
                # pitcher post-TJ remains, and it's INFORMATIONAL only
                # now (no longer a scoring input or letter-graded sub-
                # leaf — post-surgery grace period often produces
                # above-avg outcomes, so a higher post-TJ share doesn't
                # cleanly map to "worse development").
                "post_tj_pct_pit":    hb.get("post_tj_pct_pit"),
                "il_pct_current_pit": hb.get("il_pct_current_pit"),
                "il_pct_current_hit": hb.get("il_pct_current_hit"),
                "actives_pit_count":  hb.get("actives_pit_count"),
                "actives_hit_count":  hb.get("actives_hit_count"),
                # Composite burden score (higher = worse) preserved
                # for back-compat; the leaf score uses the inverted
                # individual signals below.
                "burden_score":   hb.get("score"),
            })(),
            # v31 — HOF-track count leaf. Sibling of Conviction; counts
            # graduates whose PEAK single season WAR ≥5 (the loose
            # threshold for "MVP-track" / "Cy Young-track" season).
            # Stronger ceiling signal than Conviction's 3/3.5 star
            # threshold — an org with 2 HOF-track grads has more
            # demonstrated ceiling than one with 6 mere "stars".
            "mlb_production_hof_track": _compute_hof_track_leaf(gagg),
            # v31 — Standalone Statcast Quality leaf under Development.
            # The Hitter/Pitcher DvM+ leaves ALREADY include Statcast+
            # as their 20% input (per-bucket SC+ from the bucket's
            # prospects). This leaf adds a SEPARATE signal voice —
            # the org's aggregate Statcast+ across all graded actives —
            # so orgs with SC+-strong pipelines get distinct credit
            # in the tree instead of having that signal compressed
            # into the DvM+ leaves only. The two surfaces complement:
            # DvM+ measures Statcast in development context (per
            # position bucket); this leaf measures Statcast as a
            # pure quality signal (org-wide pool).
            "dev_statcast_quality": (lambda scq=m.get("statcast_quality") or {}: {
                "mean":         scq.get("mean"),
                "hitter_mean":  scq.get("hitter_mean"),
                "pitcher_mean": scq.get("pitcher_mean"),
                "graded_count": scq.get("graded_count"),
                "hitter_count": scq.get("hitter_count"),
                "pitcher_count": scq.get("pitcher_count"),
            })(),
        }

        # v17 — Back-compat aliases for the rename. Old code paths that
        # read `tree["mlb_hitter_wag"]` / `tree["mlb_pitcher_wag"]` get
        # the same dict as the new production leaves.
        m["tree"]["mlb_hitter_wag"]  = m["tree"]["mlb_hitter_production"]
        m["tree"]["mlb_pitcher_wag"] = m["tree"]["mlb_pitcher_production"]

        # v32.1 — Lift the active-roster $/FV-pt efficiency to the org
        # top level so it's sortable on the farm leaderboard alongside
        # `total_fv` / `surplus_total_mm`. Sourced from the active
        # surplus leaf (gated at ≥5 contributing actives upstream).
        # Reads as a portfolio-quality dial: high = star/premium-position
        # loaded; low = depth-heavy but flat.
        _asl = m["tree"].get("fin_active_surplus") or {}
        m["dollars_per_fv_active"] = _asl.get("surplus_per_fv_pt_mm")
        m["surplus_per_fv_pt_hit_mm"] = _asl.get("per_fv_pt_hit_mm")
        m["surplus_per_fv_pt_pit_mm"] = _asl.get("per_fv_pt_pit_mm")

        # v17 — IFA ROI fallback. When the leaf's primary metric
        # (`war_per_m_ifa`, requires bonus dollars on file) is None, fall
        # back to the IFA acq leaf's WAR/yr signal so the cell still
        # produces a score in LEAF_SPECS instead of rendering "—".
        _ifa_leaf = m["tree"].get("fin_ifa_roi") or {}
        if _ifa_leaf.get("war_per_m_ifa") is None:
            _ifa_acq = m["tree"].get("acq_ifa") or {}
            _wp = _ifa_acq.get("war_per_yr_mean")
            if _wp is not None:
                # Stamp the fallback inline so LEAF_SPECS can read it.
                _ifa_leaf["war_per_yr_fallback"] = _wp

        # v31.5 — Stash raw grad lists on entry so the per-window
        # MLB Production / Acquisition aggregator (downstream league
        # pass) can re-walk them per window. Copies the lists (don't
        # pop) so the existing leaf computations remain intact.
        m["_top_grads_raw"]        = list(gagg.get("_top_grads") or [])
        m["_draft_pool_grads_raw"] = list(gagg.get("_draft_pool_grads") or [])
        m["_ifa_grads_raw"]        = list(gagg.get("_ifa_grads") or [])

        # _active_keys stays for the second-pass index attachment; popped later.
        org_summary.append(m)

    # v7 — drop any phantom orgs (canonical 30-MLB allowlist). Without
    # this filter, prospects with no resolved org (or with strings like
    # "Office of the Commissioner" coming through trades/transactions)
    # land in their own bucket and show up as a 31st phantom org on
    # the farm page. The filter happens BEFORE every downstream
    # tree-grade / DvM+ pass so the math anchors on exactly 30 orgs.
    org_summary = [m for m in org_summary if m.get("org") in MLB_30_ORGS]

    # v30.8 — Acquisition Deviation league pass. For each method (IFA,
    # Draft), compute the league MEDIAN star_rate across orgs that
    # have a value (≥3 grads in that method), then stamp each org's
    # deviation from that median onto the acq leaf. Surfaces "this
    # org's IFA pipeline produces stars at 1.4× the league median
    # rate" as a context signal. Independent of the existing
    # wag_mean / war_per_yr_mean / pick_value_mean scoring inputs —
    # this is a NEW orthogonal signal, not a replacement.
    def _median(vals: list[float]) -> float | None:
        if not vals:
            return None
        s = sorted(vals)
        mid = len(s) // 2
        return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
    for _leaf_key, _method_label in (("acq_ifa", "international_fa"),
                                     ("acq_draft", "draft")):
        _present_rates = []
        for e in org_summary:
            r = ((e["tree"].get(_leaf_key) or {}).get("star_rate"))
            if r is not None and isinstance(r, (int, float)):
                _present_rates.append(float(r))
        _league_median = _median(_present_rates)
        for e in org_summary:
            _leaf = e["tree"].get(_leaf_key) or {}
            _rate = _leaf.get("star_rate")
            _leaf["star_rate_league_median"] = (
                round(_league_median, 3) if _league_median is not None else None
            )
            if _rate is not None and _league_median is not None:
                _leaf["star_rate_deviation"] = round(_rate - _league_median, 3)
            else:
                _leaf["star_rate_deviation"] = None
            e["tree"][_leaf_key] = _leaf

    # Stable sort by total_fv for the moment — the composite farm_rank
    # below overwrites this ordering once the rolling-window signals are
    # available. We do it here so downstream code that wants the raw
    # FV-only rank (e.g. the "Total FV" sort chip on the front-end) can
    # still recover it by re-sorting on total_fv directly.
    org_summary.sort(key=lambda x: -x["total_fv"])

    _phase_done("grad_aggregates")
    # ── Per-tool DvM+ league pass (HitDvM+, PowerDvM+, …, ToolsDvM+) ──
    # For each TOOL_GROUP, gather every org's mean_delta on the tools in
    # that group (averaged for multi-tool groups like Power = mean of
    # game_pwr + raw_pwr). Compute league mean μ + stdev σ across orgs
    # that have data; convert each org's value to a 100-anchored index
    # via 100 + 10·z. Mirrors the wRC+-style anchoring used by `dvm_plus`
    # elsewhere in the report card. Orgs without data for a given group
    # get None; tool groups with fewer than 3 orgs reporting are dropped
    # entirely (no statistical anchor possible).
    def _group_mean_delta_for_org(per_tool: dict, keys: list[str]) -> tuple[float | None, int]:
        """Returns (group mean_delta, total prospects contributing).
        The n is the prospect count used to shrink small-sample orgs
        toward the league mean (Phase A4)."""
        vals_n = [(per_tool[k]["mean_delta"], per_tool[k].get("n_prospects", 0))
                  for k in keys
                  if k in per_tool and per_tool[k].get("mean_delta") is not None]
        if not vals_n:
            return (None, 0)
        return (sum(v for v, _ in vals_n) / len(vals_n),
                sum(n for _, n in vals_n))

    # Bayesian shrinkage strength. k=2 means an org with n=3 prospects
    # gets 60% weight on its own mean_delta + 40% on the league mean.
    # n=10 → 83% own + 17% mean. n=30 → 94% own + 6% mean. Tuned so
    # small samples don't get dragged out of contention by one outlier
    # but big samples retain their actual signal.
    _DVM_SHRINK_K = 2

    for grp_name, tool_keys in TOOL_GROUPS.items():
        org_vals: list[tuple[str, float | None, int]] = []
        for e in org_summary:
            v, n = _group_mean_delta_for_org(e["tool_dev"]["per_tool"], tool_keys)
            org_vals.append((e["org"], v, n))
        populated = [v for _, v, _ in org_vals if v is not None]
        # Lowered gate from <3 → <2 (Phase A4). With just 2 orgs
        # reporting we can still anchor a (low-confidence) mean +
        # surface a DvM+ for both; the per-org shrinkage below
        # protects against single-prospect noise.
        if len(populated) < 2:
            for org_code, _, _ in org_vals:
                _entry = next(e for e in org_summary if e["org"] == org_code)
                _entry["tool_dev"]["per_tool_dvm_plus"][grp_name] = None
            continue
        mu = sum(populated) / len(populated)
        var = sum((v - mu) ** 2 for v in populated) / len(populated)
        sd = var ** 0.5
        for org_code, v, n in org_vals:
            _entry = next(e for e in org_summary if e["org"] == org_code)
            if v is None or sd < 1e-6:
                _entry["tool_dev"]["per_tool_dvm_plus"][grp_name] = None
            else:
                # Bayesian shrinkage toward the league mean before
                # z-scoring. shrunk = (n/(n+k))·v + (k/(n+k))·μ
                weight = n / (n + _DVM_SHRINK_K) if n > 0 else 0.0
                shrunk_v = weight * v + (1 - weight) * mu
                z = (shrunk_v - mu) / sd
                # v7 — apply the composite stretch (factor=1.35) per-tool
                # too. Same monotonic remap as the org-level composite:
                # widens the spread so a 60→80 PowerDvM+ jump is worth
                # more than a 40→60 jump, matching the user's
                # exponential-FV-value ask.
                #
                # SCALE OF RECORD (documented 2026-07-29, see _stretch_composite
                # for the full chain). This chip is NOT on the nominal
                # "100-anchored, +10 = 1 sigma" DvM+ scale that the rest of this
                # file describes. Two things move it, in this order:
                #   1. the z above is computed from the SHRUNK value against the
                #      UNSHRUNK pool sd, so |z| < 1 sigma of the pool by design;
                #   2. the 1.35 stretch then widens what is left.
                # Measured on the served 30-org run the two roughly cancel to
                # ~11.2-12.6 published points per sigma per tool group (not 10,
                # not 13.5). Deliberate presentation, not a bug, but the number
                # is stated here so nobody reads a per-tool DvM+ gap as if it
                # were on the 10-point scale.
                raw = 100 + 10 * z
                stretched = _stretch_composite(raw)
                _entry["tool_dev"]["per_tool_dvm_plus"][grp_name] = int(round(stretched))

    # v30.8 — Per-bucket per-tool DvM+ league pass. Same Bayesian
    # shrinkage + composite stretch as the org-wide pass above, but
    # the population for each (bucket × tool_group) is restricted to
    # the prospects that play in that bucket. Cells with <2 orgs
    # reporting are skipped (no statistical anchor); cells with
    # <3 prospects in this org's bucket were already dropped at the
    # per-tool aggregation step above. The downstream consumer
    # falls back to org-side-wide tool DvM+ when a bucket cell is
    # None (hybrid policy per user direction).
    _ALL_BUCKETS = ("C", "INF", "OF", "SP", "RP")
    for bucket in _ALL_BUCKETS:
        for grp_name, tool_keys in TOOL_GROUPS.items():
            # Gather every org's (bucket, tool_group) mean_delta. Reuses
            # the same _group_mean_delta_for_org helper but reads from
            # per_tool_by_bucket[bucket] instead of per_tool.
            org_vals: list[tuple[str, float | None, int]] = []
            for e in org_summary:
                bucket_pertool = (e["tool_dev"].get("per_tool_by_bucket") or {}).get(bucket) or {}
                v, n = _group_mean_delta_for_org(bucket_pertool, tool_keys)
                org_vals.append((e["org"], v, n))
            populated = [v for _, v, _ in org_vals if v is not None]
            # Same ≥2-org floor as the org-wide pass.
            if len(populated) < 2:
                for org_code, _, _ in org_vals:
                    _entry = next(e for e in org_summary if e["org"] == org_code)
                    _entry["tool_dev"]["per_tool_dvm_plus_by_bucket"] \
                        .setdefault(bucket, {})[grp_name] = None
                continue
            mu_b = sum(populated) / len(populated)
            var_b = sum((v - mu_b) ** 2 for v in populated) / len(populated)
            sd_b = var_b ** 0.5
            for org_code, v, n in org_vals:
                _entry = next(e for e in org_summary if e["org"] == org_code)
                if v is None or sd_b < 1e-6:
                    _entry["tool_dev"]["per_tool_dvm_plus_by_bucket"] \
                        .setdefault(bucket, {})[grp_name] = None
                else:
                    weight = n / (n + _DVM_SHRINK_K) if n > 0 else 0.0
                    shrunk_v = weight * v + (1 - weight) * mu_b
                    z_b = (shrunk_v - mu_b) / sd_b
                    # Same 1.35 stretch, same scale caveat as the org-wide pass
                    # above (shrink-then-z compresses, stretch re-widens; net is
                    # neither 10 nor 13.5 points per sigma).
                    #
                    # NOT PURELY PRESENTATIONAL HERE: unlike the org-wide chip,
                    # these per-bucket values are consumed downstream, by
                    # _bucket_tool_dvm_plus -> _blend_dvm_3way, where the tool leg
                    # is mixed with an FV leg and an SC leg that were NOT
                    # stretched. Mixing a wider-scaled leg into a fixed-weight
                    # blend raises that leg's effective influence in proportion to
                    # the stretch. The v7 note above justifies the DISPLAY
                    # widening only and says nothing about the blend, so intent
                    # could not be established and nothing was changed here; this
                    # comment exists so the next reader does not mistake the
                    # blend-weight side effect for a deliberate weighting choice.
                    raw_b = 100 + 10 * z_b
                    stretched_b = _stretch_composite(raw_b)
                    _entry["tool_dev"]["per_tool_dvm_plus_by_bucket"] \
                        .setdefault(bucket, {})[grp_name] = int(round(stretched_b))

    # Composite ToolDvM+ — position-bucket importance-weighted blend of the
    # per-tool DvM+ values (see `_bucket_weighted_tool_dvm`). Rewards orgs
    # that develop the tools that MATTER for a position over ones that pad
    # the average with off-position gains. The internal storage key stays
    # `tools_dvm_plus`; the front-end label is "ToolDvM+".
    #
    # SCALE OF RECORD (documented 2026-07-29): this composite is a WEIGHTED MEAN
    # of legs that each already sit at ~12 published points per sigma, and a
    # weighted mean of imperfectly-correlated legs has a much smaller sd than its
    # legs do. Measured on the served 30-org run the composite's own sd is 2.9
    # points (full range 94 to 107) while every leg it averages spans roughly
    # 11 to 13. So ToolDvM+ is NOT on the "+10 = 1 sigma" DvM+ scale its name and
    # its 100 anchor imply; it is roughly 2.9 points per sigma, i.e. COMPRESSED,
    # which is the opposite direction from the 1.35 stretch applied to its inputs.
    # The two effects do not compound into one net widening. Left as-is on the
    # conservative rule (documented, not changed): re-standardizing this composite
    # the way the farm tiebreaker now is would move every displayed ToolDvM+
    # number and its rank ordering is already correct, so it is a presentation
    # decision for the owner, not a correctness fix. See also _stretch_composite.
    _apply_dvm_difficulty_tools(org_summary, _dvm_diff)     # no-op while the arm is None
    _composite_vals: list[tuple[str, int | None]] = []
    for entry in org_summary:
        td = entry["tool_dev"]
        composite = _bucket_weighted_tool_dvm(
            td.get("per_tool_dvm_plus"),
            td.get("per_tool_dvm_plus_by_bucket"),
            td.get("per_tool_by_bucket"),
        )
        td["tools_dvm_plus"] = composite
        _composite_vals.append((entry["org"], composite))

    # Rank for the composite — descending (higher composite = rank 1).
    # `_rank_descending` doesn't take None; do the present-filter inline
    # (mirrors the `_rank_with_none` helper defined later inside the
    # same parent function).
    _present_idx = [i for i, (_, v) in enumerate(_composite_vals) if v is not None]
    _present_vals = [_composite_vals[i][1] for i in _present_idx]
    _sub_ranks = _rank_descending(_present_vals)
    _ranks: list[int | None] = [None] * len(_composite_vals)
    for i, r in zip(_present_idx, _sub_ranks):
        _ranks[i] = r
    for (org_code, _), r in zip(_composite_vals, _ranks):
        _entry = next(e for e in org_summary if e["org"] == org_code)
        _entry["tool_dev"]["tools_dvm_plus_rank"] = r

    # ── Tree v2: Hitter / Pitcher Tools DvM+ composites ──
    # Filter the per_tool_dvm_plus dict (just computed) into hitter-only
    # and pitcher-only groupings, average within each. These feed the
    # Development branch of the grade tree.
    # v14 — `power` → `pwr` to match TOOL_GROUPS consolidation. The
    # consensus layer (consensus.py) writes a unified `pwr` value per
    # snapshot; the per-tool DvM+ aggregator reads it through this set.
    _HITTER_TOOL_DVM_KEYS = {"hit", "pwr", "speed", "field", "arm",
                             "pitch_sel", "bat_ctrl"}
    _PITCHER_TOOL_DVM_KEYS = {"fb", "sl", "cb", "ch", "cmd", "ct"}

    # v7 — league-avg pitch usage weights. Aggregate across every
    # pitcher's pitch_arsenal so a heavily-thrown pitch's DvM+ counts
    # more than a sparse pitch's DvM+ when rolling up the pitcher
    # composite. `cmd` (command, not a thrown pitch) keeps its default
    # weight via the unweighted fallback. Returns {fb, sl, cb, ch, ct,
    # sp: usage_share}.
    pitch_usage_weights = _league_pitch_usage(pitch_arsenals)

    def _weighted_pitcher_dvm(per_grp: dict) -> float | None:
        """Usage-weighted mean of present pitcher tool DvM+ values.
        Each tool weighted by league-wide usage share; unknown-weight
        tools (like `cmd`) get the cohort-average weight so they're
        not zeroed out. Falls back to plain unweighted mean when no
        usage data is on file."""
        present = [(k, v) for k, v in per_grp.items()
                   if k in _PITCHER_TOOL_DVM_KEYS and v is not None]
        if not present:
            return None
        if not pitch_usage_weights:
            return sum(v for _, v in present) / len(present)
        # Default weight for tools without a pitch-usage anchor (cmd):
        # the mean usage across known-pitch tools, so cmd contributes
        # proportionally rather than being silently dropped.
        known_ws = [w for w in pitch_usage_weights.values() if w > 0]
        default_w = (sum(known_ws) / len(known_ws)) if known_ws else 1.0
        num = 0.0
        denom = 0.0
        for k, v in present:
            w = pitch_usage_weights.get(k, default_w)
            num += w * v
            denom += w
        return num / denom if denom > 0 else None

    # v28 — Tool-based DvM+ pass. Writes the cohort-mean tool DvM+
    # values onto the dev_hitter / dev_pitcher leaves. The final
    # `dvm_plus` headline blends these with the cohort-restricted
    # Overall DvM+ in a later pass once the league-wide cohort means
    # / stdevs are known.
    for entry in org_summary:
        per_grp = entry["tool_dev"].get("per_tool_dvm_plus") or {}
        h_vals = [v for k, v in per_grp.items()
                  if k in _HITTER_TOOL_DVM_KEYS and v is not None]
        p_vals = [v for k, v in per_grp.items()
                  if k in _PITCHER_TOOL_DVM_KEYS and v is not None]
        tool_hit = (sum(h_vals) / len(h_vals)) if h_vals else None
        _pitcher_wm = _weighted_pitcher_dvm(per_grp)
        tool_pit = _pitcher_wm if _pitcher_wm is not None else None
        entry["tree"]["dev_hitter"]["tool_dvm_plus"]  = int(round(tool_hit)) if tool_hit is not None else None
        entry["tree"]["dev_hitter"]["n_groups"]       = len(h_vals)
        entry["tree"]["dev_pitcher"]["tool_dvm_plus"] = int(round(tool_pit)) if tool_pit is not None else None
        entry["tree"]["dev_pitcher"]["n_groups"]      = len(p_vals)
        # Stash raw floats so the later blend pass can use the full
        # precision rather than the rounded int.
        entry["_tool_hit_raw"] = tool_hit
        entry["_tool_pit_raw"] = tool_pit

    # Per-level graded prospect counts, sourced from the affiliate-roster
    # map. Drives both the "sort farms by depth at level X" chips on the
    # farm list page and the "graded prospects by level" section on each
    # farm detail page. Only includes prospects with a FV grade — un-graded
    # org filler in the rosters isn't a prospect for our purposes.
    FARM_LEVELS = ("MLB", "AAA", "AA", "A+", "A", "CPX", "DSL")
    for entry in org_summary:
        org_rosters = rosters_by_org.get(entry["org"], {})
        entry["level_counts"] = {
            lvl: sum(1 for r in (org_rosters.get(lvl) or []) if r.get("fv_label"))
            for lvl in FARM_LEVELS
        }

    # Per-org cumulative FV history — running sum of prospect FVs over time,
    # attributed to whichever org owned the prospect on each snapshot date.
    # Drives the farm-system stock chart on the farm list + farm detail
    # pages. Trades show as +/- moves between orgs; graduations are
    # graduation-neutral — the cumulative line stays flat through them so
    # a productive farm isn't punished for promoting its top prospects.
    _dev_calendar = _dev_attr.calendar if _dev_attr is not None else None
    org_fv_history = _build_org_fv_history(
        actives + grads + inactives, _filter_real_trades, trades_by_player,
        xfv_hist_by_key=_xfv_hist_by_key, calendar=_dev_calendar,
    )
    for entry in org_summary:
        hist = org_fv_history.get(entry["org"], {})
        entry["fv_history"] = hist.get("series", [])
        entry["fv_events"]  = hist.get("events", [])

    # v28 — Cohort-restricted dev-FV series for the Hitter / Pitcher
    # Development sub-grades. Splits the active+grad+inactive pool by
    # the player's primary position (`position.split('/')[0]` — strict
    # first-token, mirrors `_is_pitcher_graduate`'s two-way handling),
    # then runs the same dev-FV aggregator over each subset. The result
    # is a per-cohort cumulative dev-FV series we can score against the
    # league's cohort-mean at any window. Pairs with the tool-based
    # Tools DvM+ for a 70/30 blend on the parent leaf.
    _PITCHER_POS_SET_COHORT = {"RHP", "LHP", "SP", "RP", "MIRP", "SIRP"}
    def _primary_is_pitcher(pos: str | None) -> bool:
        if not pos:
            return False
        return pos.upper().split("/")[0].strip() in _PITCHER_POS_SET_COHORT
    all_players_for_cohort = actives + grads + inactives
    hitter_players  = [p for p in all_players_for_cohort if not _primary_is_pitcher(p.position)]
    pitcher_players = [p for p in all_players_for_cohort if     _primary_is_pitcher(p.position)]
    hitter_fv_history  = _build_org_fv_history(hitter_players,  _filter_real_trades, trades_by_player, xfv_hist_by_key=_xfv_hist_by_key, calendar=_dev_calendar)
    pitcher_fv_history = _build_org_fv_history(pitcher_players, _filter_real_trades, trades_by_player, xfv_hist_by_key=_xfv_hist_by_key, calendar=_dev_calendar)
    for entry in org_summary:
        entry["hitter_fv_history"]  = hitter_fv_history.get(entry["org"],  {}).get("series", [])
        entry["pitcher_fv_history"] = pitcher_fv_history.get(entry["org"], {}).get("series", [])

    # v30.7 — Position-bucketed cohort DvM+. Same _build_org_fv_history
    # / _trajectory_score machinery as the hitter/pitcher cohort split
    # above, but with finer pos-bucket subsets so we can score each org
    # at the C / INF / OF / SP / RP level. Bucket conventions:
    #   C   = pure catchers (premium defensive pos)
    #   INF = 1B, 2B, 3B, SS, INF, MI, UTIL, DH (corner + middle infield)
    #   OF  = OF, LF, CF, RF
    #   SP  = SP, RHP, LHP (unassigned-role arms default to SP track —
    #         most are draftees / lower-minors before role is set)
    #   RP  = RP, MIRP, SIRP, CL, CP (any reliever variant)
    # User-confirmed bucket weights (WAR positional adjustment / SP-
    # dominant) get applied at blend time below.
    _HIT_BUCKETS = ("C", "INF", "OF")
    _PIT_BUCKETS = ("SP", "RP")
    _HIT_POS_TO_BUCKET = {
        "C": "C",
        "1B": "INF", "2B": "INF", "3B": "INF", "SS": "INF",
        "INF": "INF", "MI": "INF", "UTIL": "INF", "DH": "INF",
        "OF": "OF", "LF": "OF", "CF": "OF", "RF": "OF",
    }
    _PIT_POS_TO_BUCKET = {
        "SP": "SP", "RHP": "SP", "LHP": "SP",  # unassigned-role arms → SP track
        "RP": "RP", "MIRP": "RP", "SIRP": "RP", "CL": "RP", "CP": "RP",
    }
    def _pos_bucket_for(pos: str | None) -> str | None:
        if not pos:
            return None
        first = pos.upper().split("/")[0].strip()
        return _HIT_POS_TO_BUCKET.get(first) or _PIT_POS_TO_BUCKET.get(first)

    _bucket_fv_history: dict[str, dict[str, dict]] = {}
    for bucket in _HIT_BUCKETS + _PIT_BUCKETS:
        sub = [p for p in all_players_for_cohort
               if _pos_bucket_for(p.position) == bucket]
        _bucket_fv_history[bucket] = _build_org_fv_history(
            sub, _filter_real_trades, trades_by_player,
            xfv_hist_by_key=_xfv_hist_by_key, calendar=_dev_calendar,
        )
    for entry in org_summary:
        # Per-bucket series stays on the entry so the trajectory pass
        # below can read it from the same shape as hitter_fv_history.
        entry["_pos_bucket_fv_history"] = {
            bucket: _bucket_fv_history[bucket].get(entry["org"], {}).get("series", [])
            for bucket in _HIT_BUCKETS + _PIT_BUCKETS
        }
        # NOTE: prospect dicts use `pos` (not `position`) — see the
        # m["prospects"].append() call further up. Reading the wrong
        # field silently floors every count to 0.
        entry["_pos_bucket_active_count"] = {
            bucket: sum(1 for p in entry["prospects"]
                        if _pos_bucket_for(p.get("pos")) == bucket)
            for bucket in _HIT_BUCKETS + _PIT_BUCKETS
        }

    # ── Tree v3: Trade Acumen scoreboard (FV + WAR delta) ──
    # Two co-equal sub-inputs feed this leaf:
    #   1. Net FV (sum of incoming FV − outgoing FV at trade date)
    #   2. Trade WAR Delta (career WAR of acquired grads − career WAR
    #      of traded-away grads). Captures retrospective trade value,
    #      not just the league's FV consensus at the trade moment.
    #
    # v30.8 — Trade WAR Delta is now RECENCY-WEIGHTED. Recent trades
    # speak to the CURRENT front office's acumen; a 2015 trade that
    # blew up tells you about a regime two GMs ago. Weight schedule:
    #   ≤ 3 years old:    1.0× (full credit, current FO)
    #   linear decay to:  0.2× at 13+ years (long-tail floor)
    # The legacy unweighted `war_delta_unweighted` is preserved on the
    # tree node for transparency / users who want the raw signal.
    _today = date.today()
    def _trade_recency_weight(trade_date_iso: str | None) -> float:
        """Linear decay: 1.0 for trades ≤3 years old, fading to 0.2
        at ≥13 years old. Floor of 0.2 — old trades still count, just
        much less."""
        if not trade_date_iso:
            return 0.5  # unknown date — moderate weight (don't drop, don't dominate)
        try:
            d = date.fromisoformat(trade_date_iso[:10])
        except (ValueError, TypeError):
            return 0.5
        years = (_today - d).days / 365.25
        if years <= 3.0:
            return 1.0
        if years >= 13.0:
            return 0.2
        # Linear from (3yr, 1.0) → (13yr, 0.2): slope -0.08/yr
        return max(0.2, 1.0 - 0.08 * (years - 3.0))

    # v31.8 — Per-trade SURPLUS evaluator. Parallel to the existing
    # WAR delta computation. For each trade event:
    #   * If the player is debuted → value = career_war × $/WAR_overall
    #     (the FA market WAR price; overall rate, not tier, since
    #     career WAR aggregates multi-season output at varying tiers)
    #   * Else (still a prospect) → value = _estimate_surplus_mm(
    #     fv_at_trade, is_pitcher, position) — same FV-anchored
    #     surplus estimator the active_surplus leaf uses, now sourced
    #     from value_framework with the 2026-anchored non-linear tiers.
    # Recency-weighted same as war_delta. Drives the new
    # surplus_delta sub-input on the Trade Acumen leaf.
    _WAR_DOLLAR_VALUE_M = _dollars_per_war_flat()
    # Build a small lookup of player_key → position so we can
    # estimate surplus when career WAR isn't on file.
    _player_pos_by_key: dict[str, tuple[bool, str | None]] = {}
    for _src in (actives, grads, inactives):
        for _p in (_src or []):
            if _p and getattr(_p, "player_key", None):
                _pos = getattr(_p, "position", None)
                _is_pit = bool(_pos and _pos.split("/")[0] in PITCHER_POS)
                _player_pos_by_key[_p.player_key] = (_is_pit, _pos)

    def _trade_player_value(pkey: str, fv: float | None) -> tuple[float | None, str | None]:
        """Surplus $M value of one player in one trade, plus the kind.

        v32.1 — Returns (value, kind) where kind is:
          * "vet"      — debuted player, value = career_war × $/WAR_overall
          * "prospect" — pre-debut, value = FV-anchored surplus from value_framework
          * None       — no usable signal (returns (None, None))

        Honors the project-wide principle: prospects flow through FV→
        projected WAR→projected $, debutants/MLB players flow through
        actual WAR→actual $.
        """
        cw = ((career_war or {}).get(pkey) or {}).get("career_war")
        if cw is not None and float(cw) > 0:
            return (round(float(cw) * _WAR_DOLLAR_VALUE_M, 2), "vet")
        is_pit, pos = _player_pos_by_key.get(pkey, (False, None))
        v = _estimate_surplus_mm(fv, is_pit, pos)
        return (v, "prospect" if v is not None else None)

    for entry in org_summary:
        in_fv = 0.0;  out_fv = 0.0
        in_n  = 0;    out_n  = 0
        # Unweighted (legacy) sums kept for transparency on the tree.
        in_war_raw = 0.0;  out_war_raw = 0.0
        in_war_n = 0;      out_war_n = 0
        # Recency-weighted sums (drive leaf scoring).
        in_war_w  = 0.0;   out_war_w   = 0.0
        # v31.8 — Recency-weighted SURPLUS sums (parallel signal).
        # Includes BOTH vet (career_war × $/WAR) AND prospect (FV→$)
        # contributors — feeds the headline surplus_delta input.
        in_surplus_w  = 0.0;  out_surplus_w  = 0.0
        in_surplus_n  = 0;    out_surplus_n  = 0
        # v32.1 — Prospect-only and vet-only surplus splits. Honors the
        # site-wide principle that FV-projected $ (prospects) and
        # realized-WAR $ (debutants/MLB) are different measurements
        # and shouldn't be mixed in a $/FV-pt ratio. Prospect-side
        # surplus pairs with prospect-side FV (which is meaningful);
        # vet-side surplus is just realized $-value (no FV-pt rate).
        in_surplus_w_prospect  = 0.0;  out_surplus_w_prospect  = 0.0
        in_surplus_n_prospect  = 0;    out_surplus_n_prospect  = 0
        in_fv_prospect = 0.0;          out_fv_prospect = 0.0
        in_surplus_w_vet  = 0.0;       out_surplus_w_vet  = 0.0
        in_surplus_n_vet  = 0;         out_surplus_n_vet  = 0
        # Top weighted-contributor trades for the tooltip story.
        weighted_trades: list[dict] = []
        # Count each player's participation in a given trade ONCE per org.
        # `fv_events` is built from actives+grads+inactives, so a player who
        # appears in more than one bucket (e.g. a debuted prospect still
        # listed as active) would otherwise have the same trade summed twice
        # into this org's inbound/outbound totals. The (player, date,
        # counterparty, direction) tuple uniquely identifies one player's
        # leg of one trade — mirrors the frontend trade-audit dedup key.
        _seen_trade_legs: set = set()
        for ev in (entry["fv_events"] or []):
            if ev.get("kind") != "trade":
                continue
            fv = ev.get("fv") or 0.0
            pkey = ev.get("player_key")
            _leg = (pkey, ev.get("date"), ev.get("other_org"), ev.get("direction"))
            if _leg in _seen_trade_legs:
                continue
            _seen_trade_legs.add(_leg)
            cw = ((career_war or {}).get(pkey) or {}).get("career_war")
            w = _trade_recency_weight(ev.get("date"))
            # v32.1 — Per-player surplus value + kind ("vet" / "prospect").
            psurplus, ptype = _trade_player_value(pkey, fv)
            if ev.get("direction") == "in":
                in_fv += fv; in_n += 1
                if cw is not None:
                    in_war_raw += float(cw); in_war_n += 1
                    in_war_w   += float(cw) * w
                    weighted_trades.append({
                        "player_key": pkey, "direction": "in",
                        "date": ev.get("date"), "weight": round(w, 2),
                        "career_war": float(cw),
                        "weighted_war": round(float(cw) * w, 2),
                    })
                if psurplus is not None:
                    in_surplus_w += psurplus * w
                    in_surplus_n += 1
                    if ptype == "prospect":
                        in_surplus_w_prospect += psurplus * w
                        in_surplus_n_prospect += 1
                        in_fv_prospect += fv
                    elif ptype == "vet":
                        in_surplus_w_vet += psurplus * w
                        in_surplus_n_vet += 1
            elif ev.get("direction") == "out":
                out_fv += fv; out_n += 1
                if cw is not None:
                    out_war_raw += float(cw); out_war_n += 1
                    out_war_w   += float(cw) * w
                    weighted_trades.append({
                        "player_key": pkey, "direction": "out",
                        "date": ev.get("date"), "weight": round(w, 2),
                        "career_war": float(cw),
                        "weighted_war": round(float(cw) * w, 2),
                    })
                if psurplus is not None:
                    out_surplus_w += psurplus * w
                    out_surplus_n += 1
                    if ptype == "prospect":
                        out_surplus_w_prospect += psurplus * w
                        out_surplus_n_prospect += 1
                        out_fv_prospect += fv
                    elif ptype == "vet":
                        out_surplus_w_vet += psurplus * w
                        out_surplus_n_vet += 1
        entry["tree"]["tx_trades"] = {
            "net_fv":    round(in_fv - out_fv, 1) if (in_n + out_n) else None,
            "fv_in":     round(in_fv, 1),
            "fv_out":    round(out_fv, 1),
            "in_count":  in_n,
            "out_count": out_n,
            # Recency-weighted WAR delta drives leaf scoring (≥3 grads
            # combined to anchor; mirrors the prior gate).
            "war_delta": round(in_war_w - out_war_w, 2) if (in_war_n + out_war_n) >= 3 else None,
            "war_in":    round(in_war_w, 2),
            "war_out":   round(out_war_w, 2),
            # Unweighted figures kept on tree for transparency.
            "war_delta_unweighted": round(in_war_raw - out_war_raw, 2) if (in_war_n + out_war_n) >= 3 else None,
            "war_in_unweighted":    round(in_war_raw, 2),
            "war_out_unweighted":   round(out_war_raw, 2),
            # v31.8 — Recency-weighted SURPLUS delta. Co-signal alongside
            # war_delta. Captures both debuted players (WAR×$M/WAR) AND
            # current prospects (FV-anchored surplus), giving Trade
            # Acumen credit for trades whose outcomes haven't fully
            # crystallized yet (vs war_delta which only counts debuted).
            # Gate: ≥3 valued trades total (in + out combined).
            "surplus_delta": round(in_surplus_w - out_surplus_w, 2)
                             if (in_surplus_n + out_surplus_n) >= 3 else None,
            "surplus_in":    round(in_surplus_w, 2),
            "surplus_out":   round(out_surplus_w, 2),
            "surplus_in_count":  in_surplus_n,
            "surplus_out_count": out_surplus_n,
            # v32.1 — Per-side $/FV-pt, PROSPECT-ONLY. Honors the
            # principle that FV-projected $ (prospects) and realized-WAR
            # $ (vets) can't share a $/FV-pt ratio: FV is a prospect-time
            # grade with no direct vet analog. The ratio uses only the
            # prospect contributors on each side. Vet $ is exposed
            # separately as in_vet_value_mm / out_vet_value_mm so the
            # trade audit can show both signals side-by-side.
            "in_per_fv_mm":  (round(in_surplus_w_prospect  / in_fv_prospect, 3)
                              if in_fv_prospect  > 0 and in_surplus_n_prospect  > 0 else None),
            "out_per_fv_mm": (round(out_surplus_w_prospect / out_fv_prospect, 3)
                              if out_fv_prospect > 0 and out_surplus_n_prospect > 0 else None),
            "per_fv_delta_mm": (
                round((in_surplus_w_prospect / in_fv_prospect if in_fv_prospect > 0 else 0)
                      - (out_surplus_w_prospect / out_fv_prospect if out_fv_prospect > 0 else 0), 3)
                if (in_fv_prospect > 0 and out_fv_prospect > 0
                    and in_surplus_n_prospect > 0 and out_surplus_n_prospect > 0) else None),
            # v32.1 — Prospect-side vs vet-side surplus splits exposed
            # so the trade audit UI can show "X FV @ $Y/FV (prospects)
            # + $Z (vet realized)" rather than a mixed apples/oranges
            # ratio. fv_prospect totals are summed RAW (no recency
            # weight) since FV is a snapshot grade; surplus totals are
            # recency-weighted to match the headline surplus_delta.
            "in_surplus_prospect_mm":  round(in_surplus_w_prospect, 2),
            "out_surplus_prospect_mm": round(out_surplus_w_prospect, 2),
            "in_fv_prospect":          round(in_fv_prospect, 1),
            "out_fv_prospect":         round(out_fv_prospect, 1),
            "in_vet_value_mm":         round(in_surplus_w_vet, 2),
            "out_vet_value_mm":        round(out_surplus_w_vet, 2),
            "in_vet_count":            in_surplus_n_vet,
            "out_vet_count":           out_surplus_n_vet,
            "in_prospect_count":       in_surplus_n_prospect,
            "out_prospect_count":      out_surplus_n_prospect,
            # Top weighted contributors for the tooltip (sorted by
            # absolute weighted_war desc, max 5).
            "top_weighted_trades": sorted(
                weighted_trades,
                key=lambda t: -abs(t["weighted_war"]),
            )[:5],
        }

    # Waivers sub-grade — walk transactions_by_player for non-trade
    # cross-org events (waiver_claim, rule_5_return, contract_purchase,
    # signed_free_agent).
    #
    # Phase A2 (2026-05): switched from the always-LATEST-FV proxy to a
    # transaction-date FV lookup. The prior approach over-valued waiver
    # claims that bloomed years AFTER the claim (e.g., a 2021 waiver of
    # a prospect now at FV 50 was credited at FV 50, not the FV ~38 the
    # claiming org actually saw). Walks player.points[] once per player
    # and indexes by snapshot_date so the per-tx lookup is O(log n).
    _WAIVER_KINDS = {"waiver_claim", "rule_5_return", "contract_purchase",
                     "signed_free_agent"}
    _waiver_in_by_org:  dict[str, list[float]] = {}
    _waiver_out_by_org: dict[str, list[float]] = {}
    # v3 hit-rate accumulators — per-org claimed-into-org count + count
    # of those that reached MLB. Used to compute Waiver Hit Rate as a
    # 50/50 z-blend partner to net_fv at the leaf-scoring layer.
    _waiver_claims_by_org:    dict[str, int] = {}
    _waiver_mlb_hits_by_org:  dict[str, int] = {}
    # Build a per-player chronological FV history (sorted ascending by
    # snapshot_date) so fv_at_date is a simple right-bisect. Skip
    # players with no points or no FV data at all.
    _player_fv_history: dict[str, list[tuple[str, float]]] = {}
    for p in actives + grads + inactives:
        hist: list[tuple[str, float]] = []
        _xh = {pt2.get("d"): pt2.get("x")
               for pt2 in (_xfv_hist_by_key.get(p.player_key) or [])
               if pt2.get("d") and pt2.get("x") is not None}
        for pt in (p.points or []):
            _fv = _xh.get(pt.snapshot_date)              # eFV at this snapshot (consensus fallback)
            if _fv is None and pt.consensus_fv_raw is not None:
                _fv = float(pt.consensus_fv_raw)
            if _fv is not None:
                hist.append((pt.snapshot_date, float(_fv)))
        if hist:
            # points are already date-ordered upstream, but sort
            # defensively in case of out-of-order ingest.
            hist.sort(key=lambda t: t[0])
            _player_fv_history[p.player_key] = hist

    def _fv_at_date(pkey: str, cutoff_date: str) -> float | None:
        """Return the most-recent consensus_fv_raw at-or-before cutoff
        for this player, or None if no point exists by that date.
        Falls back to the OLDEST point when cutoff predates all points
        (rare — usually a Rule-5/waiver before the player was published)."""
        hist = _player_fv_history.get(pkey)
        if not hist:
            return None
        # Right-bisect: find the last point where date <= cutoff_date.
        import bisect
        idx = bisect.bisect_right([t[0] for t in hist], cutoff_date) - 1
        if idx < 0:
            # Cutoff predates all snapshots — use the OLDEST FV as the
            # best available proxy (better than dropping the tx).
            return hist[0][1]
        return hist[idx][1]

    _txs = transactions_by_player or {}
    # Tally distinct kinds we encounter for a debug log — surfaces drift
    # if a new transaction type slips through derive_transactions
    # without being grouped here.
    _waiver_kinds_seen: dict[str, int] = {}
    for pkey, txs in _txs.items():
        if pkey not in _player_fv_history:
            continue
        # Reached-MLB signal — career_war present + any season recorded
        # means the player landed on a big-league roster at some point.
        cw_entry = (career_war or {}).get(pkey) or {}
        _player_reached_mlb = bool(cw_entry.get("career_war") is not None
                                   or (cw_entry.get("seasons") or {}))
        for tx in (txs or []):
            kind = tx.get("kind")
            if kind not in _WAIVER_KINDS:
                continue
            _waiver_kinds_seen[kind] = _waiver_kinds_seen.get(kind, 0) + 1
            # Transaction-date FV — what the claiming org actually saw,
            # not the retrospective FV. Falls back to the player's
            # oldest FV when the tx predates all snapshots.
            tx_date = tx.get("date") or ""
            fv = _fv_at_date(pkey, tx_date)
            if fv is None:
                continue
            # IMPORTANT: derive_transactions in stats.py emits the
            # `from_team` / `to_team` keys (not `_team_name`). An earlier
            # version of this loop used the wrong field names and silently
            # produced an empty scoreboard for all 30 orgs. The fix below
            # tracks the canonical field shape that stats.py actually
            # ships.
            from_team = tx.get("from_team")
            to_team   = tx.get("to_team")
            from_org  = canonical_org(from_team) if from_team else None
            to_org    = canonical_org(to_team)   if to_team   else None
            if from_org:
                _waiver_out_by_org.setdefault(from_org, []).append(fv)
            if to_org:
                _waiver_in_by_org.setdefault(to_org, []).append(fv)
                _waiver_claims_by_org[to_org] = _waiver_claims_by_org.get(to_org, 0) + 1
                if _player_reached_mlb:
                    _waiver_mlb_hits_by_org[to_org] = _waiver_mlb_hits_by_org.get(to_org, 0) + 1
    # _waiver_kinds_seen tally available for debug if a future kind
    # silently drops out of the filter — print or log on demand.
    for entry in org_summary:
        org_code = entry["org"]
        in_list  = _waiver_in_by_org.get(org_code, [])
        out_list = _waiver_out_by_org.get(org_code, [])
        in_fv  = round(sum(in_list), 1)
        out_fv = round(sum(out_list), 1)
        claims_total   = _waiver_claims_by_org.get(org_code, 0)
        claims_mlb_hit = _waiver_mlb_hits_by_org.get(org_code, 0)
        entry["tree"]["tx_waivers"] = {
            "net_fv":    round(in_fv - out_fv, 1) if (in_list or out_list) else None,
            "fv_in":     in_fv,
            "fv_out":    out_fv,
            "in_count":  len(in_list),
            "out_count": len(out_list),
            # v3 — Waiver Hit Rate (% claimed-into-org who reached MLB).
            # Sparse-data gate: <3 claims → None.
            "hit_rate":        (round(claims_mlb_hit / claims_total, 3)
                                if claims_total >= 3 else None),
            "claims_total":    claims_total,
            "claims_with_mlb": claims_mlb_hit,
        }

    _phase_done("dvm_trees")
    # ── Farm report card ────────────────────────────────────────────────────
    # Four raw component scores per org, each then rescaled to a 0-100 band
    # across the 30 orgs and blended into a single farm_score. The blend
    # weights are FARM_WEIGHT_* above. Each component also gets a letter
    # grade (its rank's bucket); the overall letter is the bucket the
    # blended farm_score lands in.
    today_iso = date.today()
    for entry in org_summary:
        # Fold provisional (source-ungraded) prospects into the rank-and-tier pool so the
        # genuine breakouts (eFV ~44-49) count toward top-end/depth alongside graded
        # prospects; filler (FV 20-30, ~0 tier points) ranks out. The displayed
        # entry["prospects"] list is NOT mutated -- only the scoring pool is augmented.
        # DEDUP IS LOAD-BEARING (2026-08-05). This concatenation used to be safe
        # only because the graded and provisional sets were complements: a player
        # with a consensus point never reached the provisional model. That stopped
        # being true when efv_ungraded started scoring constant-anchored players
        # (they carry a fabricated FV 35 consensus point AND now a provisional
        # grade), so a plain concat would double-count roughly 2,300 players in
        # _top_end_points / _depth_points / provisional_in_pool. Their tier points
        # are ~0 so the score effect is small, but a player counted twice in a
        # depth pool is a correctness bug regardless of its magnitude. The graded
        # row wins: it is the one the board displays.
        _prov = _prov_by_org.get(entry["org"], [])
        if _prov:
            _seen = {p.get("player_key") for p in entry["prospects"] if p.get("player_key")}
            _prov = [p for p in _prov
                     if not (p.get("player_key") and p.get("player_key") in _seen)]
        _pool = entry["prospects"] + _prov if _prov else entry["prospects"]
        entry["top_end_points"] = _top_end_points(_pool)
        entry["depth_points"]   = _depth_points(_pool)
        # Count of provisional sleepers that crack the org's scored top-25 (for the
        # farm-detail "includes N provisional sleepers" note).
        if _prov:
            _ranked25 = sorted(_pool, key=lambda p: (_eff_grade(p) or 0), reverse=True)[:FARM_DEPTH_END]
            entry["provisional_in_pool"] = sum(1 for p in _ranked25 if p.get("provisional"))
        # Trajectory at each available window. The blended score (60% 6y
        # + 30% 3y + 10% 1y) is also surfaced as `trajectory_score` so
        # the report-card grading anchors on the principal multi-cycle
        # signal — 6y dominates (sustained dev is the highest-conviction
        # org tell), 3y smooths over the current draft cycle, and 1y
        # still contributes so a hot current year isn't fully ignored.
        entry["trajectories"] = {
            key: _trajectory_score(
                entry["fv_history"], lookback_days=days, as_of=today_iso,
            )
            for key, days in FARM_TRAJECTORY_WINDOWS.items()
        }
        _T = entry["trajectories"]
        # Recency-tilted multi-horizon blend anchored on the principal window
        # (60% principal / 30% 3y / 10% 1y) — the principal carries sustained
        # development, the shorter horizons weight recent movement so a stale
        # multi-year regime can't fully mask a current hot (or cold) cycle.
        entry["trajectory_score"] = round(
            0.60 * (_T.get(FARM_PRINCIPAL_WINDOW) or 0)
            + 0.30 * (_T.get("3y") or 0)
            + 0.10 * (_T.get("1y") or 0),
            3,
        )
        entry["grad_pipeline_score"] = _grad_pipeline_score(
            entry["fv_events"], as_of=today_iso,
        )
        # v41 — Graduation-pace leaf: FV>=50 debuts/yr over the principal window
        # (the RHYTHM of quality graduations, vs. the trailing-12mo POINTS above).
        _gp_win_yrs = int(str(FARM_PRINCIPAL_WINDOW).rstrip("y"))
        entry.setdefault("tree", {})["mlb_production_grad_pace"] = {
            "grad_pace": _grad_pace_score(entry.get("fv_events") or [],
                                          window_years=_gp_win_yrs, as_of=today_iso),
            "window_years": _gp_win_yrs,
        }

    # Mean trajectory per window across all orgs. The list-page chart
    # subtracts a linear baseline of `mean * t/window_days` from each
    # org's series so the line shows "growth above the average farm",
    # not raw FV — that's the comparison the user actually wants when
    # ranking dev pipelines. Mean (not median) so the metric responds
    # to outliers — a system that's well above league mean reflects
    # real dev outperformance, not just being above the middle of the
    # pack. Standard deviation is also exported so DvM+ can use it to
    # convert raw deltas into a wRC+-style 100-anchored scale.
    def _mean(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    def _stdev(vals: list[float], mu: float) -> float:
        if len(vals) < 2:
            return 0.0
        return (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5

    farm_trajectory_means = {
        key: round(_mean([e["trajectories"][key] for e in org_summary]), 2)
        for key in FARM_TRAJECTORY_WINDOWS
    }
    farm_trajectory_stdevs = {
        key: round(
            _stdev(
                [e["trajectories"][key] for e in org_summary],
                farm_trajectory_means[key],
            ),
            4,
        )
        for key in FARM_TRAJECTORY_WINDOWS
    }
    for entry in org_summary:
        entry["delta_above_mean"] = {
            key: round(entry["trajectories"][key] - farm_trajectory_means[key], 2)
            for key in FARM_TRAJECTORY_WINDOWS
        }
        # DvM+ — wRC+/OPS+-style metric anchored at 100 = league mean.
        # 10 points = 1 stdev, mirroring the OPS+ convention. Stable
        # under sparse league spread (returns 100 when stdev ≈ 0).
        entry["dvm_plus"] = {}
        for key in FARM_TRAJECTORY_WINDOWS:
            sd = farm_trajectory_stdevs[key]
            delta = entry["delta_above_mean"][key]
            if sd > 1e-6:
                entry["dvm_plus"][key] = round(100 + 10 * (delta / sd))
            else:
                entry["dvm_plus"][key] = 100

    # v28 — Cohort-restricted Hitter / Pitcher trajectory + DvM+ per
    # window. Same algorithm as the org-wide trajectory above, but
    # scored against the cohort-only league pool (so a strong-pitcher
    # org gets credit even if its hitter pipeline is mediocre, and
    # vice-versa). Each entry gets:
    #   hitter_trajectories  / pitcher_trajectories  : raw smoothed dev
    #   hitter_delta_above_mean / pitcher_…          : delta vs cohort mean
    #   hitter_dvm_plus      / pitcher_dvm_plus      : 100-anchored index
    # Sparse-cohort orgs (no qualifying hitter / pitcher) yield None
    # for that side at that window — they read as "no data" in the
    # blend below, not as a zero.
    for entry in org_summary:
        entry["hitter_trajectories"]  = {
            key: _trajectory_score(entry["hitter_fv_history"],
                                   lookback_days=days, as_of=today_iso)
            for key, days in FARM_TRAJECTORY_WINDOWS.items()
        }
        entry["pitcher_trajectories"] = {
            key: _trajectory_score(entry["pitcher_fv_history"],
                                   lookback_days=days, as_of=today_iso)
            for key, days in FARM_TRAJECTORY_WINDOWS.items()
        }
    hitter_traj_means = {
        key: round(_mean([e["hitter_trajectories"][key] for e in org_summary]), 2)
        for key in FARM_TRAJECTORY_WINDOWS
    }
    hitter_traj_stdevs = {
        key: round(_stdev([e["hitter_trajectories"][key] for e in org_summary],
                          hitter_traj_means[key]), 4)
        for key in FARM_TRAJECTORY_WINDOWS
    }
    pitcher_traj_means = {
        key: round(_mean([e["pitcher_trajectories"][key] for e in org_summary]), 2)
        for key in FARM_TRAJECTORY_WINDOWS
    }
    pitcher_traj_stdevs = {
        key: round(_stdev([e["pitcher_trajectories"][key] for e in org_summary],
                          pitcher_traj_means[key]), 4)
        for key in FARM_TRAJECTORY_WINDOWS
    }
    for entry in org_summary:
        entry["hitter_delta_above_mean"]  = {
            key: round(entry["hitter_trajectories"][key]  - hitter_traj_means[key], 2)
            for key in FARM_TRAJECTORY_WINDOWS
        }
        entry["pitcher_delta_above_mean"] = {
            key: round(entry["pitcher_trajectories"][key] - pitcher_traj_means[key], 2)
            for key in FARM_TRAJECTORY_WINDOWS
        }
        entry["hitter_dvm_plus"]  = {}
        entry["pitcher_dvm_plus"] = {}
        for key in FARM_TRAJECTORY_WINDOWS:
            sdh = hitter_traj_stdevs[key]
            sdp = pitcher_traj_stdevs[key]
            dh  = entry["hitter_delta_above_mean"][key]
            dp  = entry["pitcher_delta_above_mean"][key]
            entry["hitter_dvm_plus"][key]  = (round(100 + 10 * (dh / sdh)) if sdh > 1e-6 else 100)
            entry["pitcher_dvm_plus"][key] = (round(100 + 10 * (dp / sdp)) if sdp > 1e-6 else 100)

    # v30.7 — Per-position-bucket FVDvM+ trajectory. Same
    # _trajectory_score / league-mean / stdev pattern as the
    # hitter/pitcher cohort math above, but applied independently to
    # each bucket: C, INF, OF, SP, RP. The bucket league means use
    # ONLY orgs that have a non-empty bucket so the league baseline
    # isn't pulled by orgs with zero bodies in (e.g.) catching.
    _bucket_traj: dict[str, dict[str, dict]] = {}    # bucket → {org → {win → score}}
    _bucket_traj_mean: dict[str, dict[str, float]] = {}
    _bucket_traj_stdev: dict[str, dict[str, float]] = {}
    for bucket in _HIT_BUCKETS + _PIT_BUCKETS:
        _bucket_traj[bucket] = {}
        for entry in org_summary:
            series = (entry.get("_pos_bucket_fv_history") or {}).get(bucket) or []
            if not series:
                _bucket_traj[bucket][entry["org"]] = {k: None for k in FARM_TRAJECTORY_WINDOWS}
                continue
            _bucket_traj[bucket][entry["org"]] = {
                k: _trajectory_score(series, lookback_days=days, as_of=today_iso)
                for k, days in FARM_TRAJECTORY_WINDOWS.items()
            }
        # League mean + stdev computed across orgs WITH data only.
        _bucket_traj_mean[bucket] = {}
        _bucket_traj_stdev[bucket] = {}
        for win in FARM_TRAJECTORY_WINDOWS:
            vals = [_bucket_traj[bucket][e["org"]][win] for e in org_summary
                    if _bucket_traj[bucket][e["org"]][win] is not None]
            if vals:
                mu = sum(vals) / len(vals)
                _bucket_traj_mean[bucket][win]  = mu
                _bucket_traj_stdev[bucket][win] = (sum((v - mu)**2 for v in vals) / len(vals)) ** 0.5
            else:
                _bucket_traj_mean[bucket][win]  = 0.0
                _bucket_traj_stdev[bucket][win] = 0.0
    # Now stamp per-bucket FVDvM+ per org.
    for entry in org_summary:
        entry["_pos_bucket_fv_dvm_plus"] = {}
        for bucket in _HIT_BUCKETS + _PIT_BUCKETS:
            entry["_pos_bucket_fv_dvm_plus"][bucket] = {}
            for win in FARM_TRAJECTORY_WINDOWS:
                raw = _bucket_traj[bucket][entry["org"]][win]
                sd  = _bucket_traj_stdev[bucket][win]
                if raw is None:
                    entry["_pos_bucket_fv_dvm_plus"][bucket][win] = None
                elif sd < 1e-6:
                    entry["_pos_bucket_fv_dvm_plus"][bucket][win] = 100
                else:
                    delta = raw - _bucket_traj_mean[bucket][win]
                    entry["_pos_bucket_fv_dvm_plus"][bucket][win] = int(round(100 + 10 * (delta / sd)))

    _apply_dvm_difficulty_fv(org_summary, _dvm_diff)        # no-op while the arm is None

    # v28 — Final blend pass. 70% cohort-restricted Overall DvM+ +
    # 30% tool-grade-based DvM+. Missing-signal: if one side is
    # absent the other takes 100%. Headline `dvm_plus` (which feeds
    # LEAF_SPECS letter grading) anchors on FARM_PRINCIPAL_WINDOW (7y),
    # the principal sustained-development signal. `dvm_plus_by_window`
    # exposes the blend at every window in FARM_TRAJECTORY_WINDOWS for
    # window-reactive frontend display. (Since v30.7 the blend is the
    # 3-way _blend_dvm_3way below, not this 70/30.)
    # v30 — Asymmetric over-grading penalty. When the overall (FV-based)
    # DvM+ outruns the tool-based DvM+ by a wide margin, the farm is
    # likely receiving FV upgrades the underlying tool grades haven't
    # caught up to — the canonical "overgraded farm" signature (the
    # Orioles / Red Sox case the user flagged: high FV trajectory +
    # much lower tool trajectory). The penalty SHIFTS the blend toward
    # the tool side; the reverse case (tools ahead of FV) is left
    # alone since that reads as a lagging scout upgrade, not
    # overgrading.
    #
    # Tool-weight schedule (gap = overall - tool):
    #   gap < 15   → 30%  (existing baseline, no penalty)
    #   gap 15-35  → ramps 40% → 60% (linear, 1pp per gap unit)
    #   gap ≥ 35   → 60%  (cap — even at extreme disparities, tools
    #                       never outweigh overall by more than 60/40)
    def _adaptive_tool_weight(overall, tool):
        if overall is None or tool is None:
            return FARM_DVM_TOOL_SHARE_IN_SLICE
        gap = overall - tool
        if gap < FARM_DVM_TOOL_PENALTY_GAP_START:
            return FARM_DVM_TOOL_SHARE_IN_SLICE
        if gap >= FARM_DVM_TOOL_PENALTY_GAP_CAP:
            return FARM_DVM_TOOL_SHARE_PENALTY_CAP
        return FARM_DVM_TOOL_SHARE_PENALTY_START + (gap - FARM_DVM_TOOL_PENALTY_GAP_START) * 0.01

    def _blend_dvm(overall, tool):
        if overall is None and tool is None:
            return None
        if overall is None:
            return int(round(tool))
        if tool is None:
            return int(round(overall))
        tool_w = _adaptive_tool_weight(overall, tool)
        return int(round((1 - tool_w) * overall + tool_w * tool))
    # v30 — Build a per-window disparity report so the UI can explain
    # whenever the over-grading penalty kicked in (Orioles / Red Sox-
    # style: FV trajectory well ahead of tool trajectory). Fields:
    #   overall_dvm_plus     — original FV-based DvM+ per window
    #   tool_dvm_plus_used   — tool DvM+ value passed into the blend
    #   gap                  — overall - tool per window (positive
    #                          when FV is ahead — direction we penalize)
    #   tool_weight_applied  — what fraction of the blend the tool
    #                          side actually got (≥ 0.30 baseline;
    #                          ≥ 0.40 means the penalty fired)
    #   penalty_pts          — base_blend - penalized_blend per window
    #                          (positive = farm got dinged; 0 = no
    #                          penalty)
    def _disparity_report(overall_map, tool_val):
        out = {}
        for win in FARM_TRAJECTORY_WINDOWS:
            ov = overall_map.get(win)
            if ov is None or tool_val is None:
                out[win] = {"overall_dvm_plus": ov, "tool_dvm_plus_used": tool_val,
                            "gap": None, "tool_weight_applied": None, "penalty_pts": 0}
                continue
            tw = _adaptive_tool_weight(ov, tool_val)
            base = int(round(0.7 * ov + 0.3 * tool_val))
            penal = int(round((1 - tw) * ov + tw * tool_val))
            out[win] = {
                "overall_dvm_plus": ov,
                "tool_dvm_plus_used": tool_val,
                "gap": round(ov - tool_val, 1),
                "tool_weight_applied": round(tw, 2),
                "penalty_pts": max(0, base - penal),
            }
        return out

    # v30.7 — StatcastDvM+ — a third dev sub-axis sitting alongside
    # FVDvM+ (the existing overall DvM+) and ToolDvM+. Anchored on the
    # org's per-side mean Statcast+ across actives; z-normalized
    # across the 30 orgs to a 100-anchored scale (100 = league mean,
    # 10pts = 1σ — same convention as the FV/Tool DvM+ scales). When
    # an org has fewer than 5 graded prospects on a side, the side's
    # SC+ DvM+ is None (treated as missing-axis in the 3-way blend).
    # Only the 6y window is exposed — Statcast doesn't have meaningful
    # 1y/3y windows in this dataset (the metric is a CURRENT snapshot,
    # not a historical trajectory, so the same value applies to every
    # window). The user direction was "incorporate SC+ avg into
    # development grades"; this leaves room for a future per-window
    # SC+ trajectory once historical SC+ values are tracked.
    _hit_sc_raw = [(e["org"], ((e.get("statcast_quality") or {}).get("hitter_mean")))
                   for e in org_summary]
    _pit_sc_raw = [(e["org"], ((e.get("statcast_quality") or {}).get("pitcher_mean")))
                   for e in org_summary]
    def _sc_dvm_map(rows: list[tuple[str, float | None]]) -> dict[str, int | None]:
        present = [(o, v) for o, v in rows if v is not None]
        if len(present) < 2:
            return {o: None for o, _ in rows}
        vals = [v for _, v in present]
        mu = sum(vals) / len(vals)
        sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5
        if sd < 1e-6:
            return {o: 100 if v is not None else None for o, v in rows}
        return {o: (int(round(100 + 10 * ((v - mu) / sd))) if v is not None else None)
                for o, v in rows}
    _hit_sc_dvm = _sc_dvm_map(_hit_sc_raw)
    _pit_sc_dvm = _sc_dvm_map(_pit_sc_raw)

    # v30.7 — Per-bucket StatcastDvM+. Same z-norm pattern as the
    # per-side version above, but partitioned by C/INF/OF/SP/RP.
    # League mean + stdev computed across orgs that HAVE a value in
    # this bucket (≥3 prospects gate set at aggregation time).
    _bucket_sc_dvm: dict[str, dict[str, int | None]] = {}
    for bucket in _HIT_BUCKETS + _PIT_BUCKETS:
        rows = [(e["org"], (e.get("_pos_bucket_sc_means") or {}).get(bucket))
                for e in org_summary]
        _bucket_sc_dvm[bucket] = _sc_dvm_map(rows)

    # v30.7 3-way DvM+ blend, as it runs today: FVDvM+ and ToolDvM+
    # share FARM_DVM_FV_TOOL_SHARE (0.75), StatcastDvM+ takes
    # FARM_DVM_STATCAST_SHARE (0.25), so the baseline split is FV 52.5 /
    # Tool 22.5 / Statcast 25 (the 50/30/20 this comment once named
    # predates the audit trim in the docstring). The FV+Tool slice keeps
    # its adaptive over-grade penalty (_adaptive_tool_weight).
    def _blend_dvm_3way(fv_dvm, tool_dvm, sc_dvm):
        """FV / Tool / Statcast development blend. v-arkmetric-audit (finding 9 —
        CIRCULARITY): scouting tool grades feed BOTH the consensus FV (so FV-DvM)
        AND ToolDvM+, so the tool signal enters this blend via two correlated paths
        (measured org-level corr(FV-DvM, Tool-DvM) ≈ 0.30 — modest but real double-
        count). The FV+Tool slice is trimmed 0.80 → 0.75 and the ORTHOGONAL Statcast
        axis (independent tracked-data signal) raised 0.20 → 0.25, proportionate to
        the shared variance — reducing the tool double-exposure without overcorrecting.
        Adaptive penalty fires only on the FV+Tool sub-blend so test_dvm_disparity_
        penalty.py still passes (`_blend_dvm` untouched, re-used in the SC-missing path)."""
        # All three present — apply the precise weight allocation.
        if fv_dvm is not None and tool_dvm is not None and sc_dvm is not None:
            tool_w_in_slice = _adaptive_tool_weight(fv_dvm, tool_dvm)
            # FV + Tool combined = 75% of total (was 80%); the tool-weight-in-slice
            # (baseline 30%, up to 60% under penalty) governs how the 75% splits.
            tool_w_total = FARM_DVM_FV_TOOL_SHARE * tool_w_in_slice
            fv_w_total   = FARM_DVM_FV_TOOL_SHARE - tool_w_total
            return int(round(fv_w_total * fv_dvm
                             + tool_w_total * tool_dvm
                             + FARM_DVM_STATCAST_SHARE * sc_dvm))
        # Missing-axis fallbacks. SC missing → original 2-way blend.
        if sc_dvm is None:
            return _blend_dvm(fv_dvm, tool_dvm)
        # Only SC present → use it directly.
        if fv_dvm is None and tool_dvm is None:
            return int(round(sc_dvm))
        # FV + SC (tool missing) → 70/30 FV-heavy.
        if tool_dvm is None:
            return int(round(0.70 * fv_dvm + 0.30 * sc_dvm))
        # Tool + SC (FV missing) → 60/40 Tool-heavy.
        return int(round(0.60 * tool_dvm + 0.40 * sc_dvm))

    # v30.7 — Position-bucket weights (user-confirmed). Hitters use
    # the FanGraphs positional-adjustment family (C carries premium
    # defensive value per body; INF heaviest by population × value;
    # OF rounds out). Pitchers heavily favor SP — SP development is
    # ~3-4× the WAR ceiling of RP.
    _POS_WEIGHTS_HIT = {"C": 0.35, "INF": 0.40, "OF": 0.25}
    _POS_WEIGHTS_PIT = {"SP": 0.80, "RP": 0.20}

    # v30.8 — Per-bucket tool importance weights for the per-bucket
    # Tool DvM+ aggregator. The keys must match TOOL_GROUPS names
    # ("hit", "pwr", "speed", "field", "arm", "pitch_sel",
    # "bat_ctrl", "fb", "sl", "cb", "ch", "cmd", "ct"). Within each
    # bucket the weights sum to 1.0; missing tools renormalize the
    # remaining weights at aggregation time, so an org without bat_ctrl
    # data on (say) its INF bucket still gets a defensible bucket
    # Tool DvM+ from the tools that DO have data.
    #
    # Reasoning:
    #  C: throw + frame/field carry premium-defense value at the position;
    #     hit/pwr still matter for the bat. (frame folds into field here.)
    #  INF: hit + pwr lead — bat carries the position; field/arm secondary.
    #  OF: hit + speed + pwr lead — speed is part of the OF profile.
    #  SP: FB + CMD + diversified arsenal; CT/CB ranked lower (less common).
    #  RP: FB + SL dominate; CMD important; CB/CH/CT marginal.
    _BUCKET_TOOL_WEIGHTS: dict[str, dict[str, float]] = {
        "C":   {"hit": 0.18, "pwr": 0.12, "speed": 0.05,
                "field": 0.18, "arm": 0.25,
                "pitch_sel": 0.10, "bat_ctrl": 0.12},
        "INF": {"hit": 0.25, "pwr": 0.20, "speed": 0.10,
                "field": 0.18, "arm": 0.12,
                "pitch_sel": 0.08, "bat_ctrl": 0.07},
        "OF":  {"hit": 0.25, "pwr": 0.20, "speed": 0.18,
                "field": 0.12, "arm": 0.10,
                "pitch_sel": 0.08, "bat_ctrl": 0.07},
        "SP":  {"fb": 0.25, "sl": 0.15, "cb": 0.12, "ch": 0.15,
                "cmd": 0.25, "ct": 0.08},
        "RP":  {"fb": 0.30, "sl": 0.25, "cb": 0.10, "ch": 0.10,
                "cmd": 0.20, "ct": 0.05},
    }

    def _bucket_tool_dvm_plus(per_tool_dvm: dict, bucket: str) -> float | None:
        """Position-weighted mean of per-bucket per-tool DvM+ values.
        Renormalizes weights across present tools so partial data
        still produces a defensible composite. Returns None when no
        tool in this bucket has a value."""
        weights = _BUCKET_TOOL_WEIGHTS.get(bucket) or {}
        present = [(k, w) for k, w in weights.items()
                   if per_tool_dvm.get(k) is not None]
        if not present:
            return None
        total_w = sum(w for _, w in present)
        if total_w <= 0:
            return None
        return sum(per_tool_dvm[k] * (w / total_w) for k, w in present)

    def _pos_weighted_blend(bucket_vals: dict[str, int | None],
                            weights: dict[str, float]) -> int | None:
        """Sum bucket values weighted by `weights`, with sparse-cohort
        redistribution: when a bucket has no value for this org, its
        weight is removed and the remaining weights renormalize to sum
        to 1.0 so the missing bucket doesn't drag the org down. Returns
        None when every bucket is missing (e.g. an org with no graded
        Statcast in any pos)."""
        present = {b: v for b, v in bucket_vals.items() if v is not None}
        if not present:
            return None
        total_w = sum(weights[b] for b in present if b in weights)
        if total_w <= 0:
            return None
        weighted = sum(v * (weights[b] / total_w) for b, v in present.items() if b in weights)
        return int(round(weighted))

    for entry in org_summary:
        tool_hit = entry.pop("_tool_hit_raw", None)
        tool_pit = entry.pop("_tool_pit_raw", None)
        hit_overall = entry["hitter_dvm_plus"]    # {window: int}
        pit_overall = entry["pitcher_dvm_plus"]
        # SC DvM+ is window-invariant in v30.7 (a snapshot, not a
        # history) — same value applies to 1y/3y/6y.
        hit_sc = _hit_sc_dvm.get(entry["org"])
        pit_sc = _pit_sc_dvm.get(entry["org"])

        # v30.7 — Per-position-bucket 3-way blend. Each bucket gets
        # its own (FV_b + Tool_b + SC_b) blend; the side-level
        # DvM+ becomes the weighted average across buckets (35/40/25
        # for hitter C/INF/OF; 80/20 for SP/RP).
        # v30.8 — Tool DvM+ is now PER-BUCKET (was org-side-wide v1
        # placeholder applied uniformly to every bucket). The
        # position-weighted aggregator uses per-bucket per-tool DvM+
        # values from _attach_per_tool_dvm_plus's bucket-aware league
        # pass. Hybrid fallback: when a bucket's tool aggregate is
        # None (insufficient prospects), we fall back to the org-side-
        # wide tool DvM+ so the cell stays defensible.
        bucket_fv_by_win  = entry["_pos_bucket_fv_dvm_plus"]   # {bucket: {win: int|None}}
        bucket_sc         = {b: _bucket_sc_dvm[b].get(entry["org"])
                             for b in _HIT_BUCKETS + _PIT_BUCKETS}
        # Per-bucket Tool DvM+ aggregation (position-weighted mean of
        # per-(bucket × tool) values, with fallback to org-wide tool
        # DvM+ when no bucket data exists).
        per_tool_dvm_buckets = (entry.get("tool_dev") or {}).get("per_tool_dvm_plus_by_bucket") or {}
        bucket_tool: dict[str, float | None] = {}
        for bucket in _HIT_BUCKETS + _PIT_BUCKETS:
            bucket_pertool = per_tool_dvm_buckets.get(bucket) or {}
            v = _bucket_tool_dvm_plus(bucket_pertool, bucket)
            if v is None:
                # Hybrid fallback — use the org-side-wide value so the
                # bucket cell isn't blank when the bucket cohort is too
                # thin to support its own per-tool aggregation.
                v = tool_hit if bucket in _HIT_BUCKETS else tool_pit
            bucket_tool[bucket] = v
        # Per-bucket per-window blend.
        bucket_blend_by_win: dict[str, dict[str, int | None]] = {}
        for bucket in _HIT_BUCKETS + _PIT_BUCKETS:
            bucket_blend_by_win[bucket] = {}
            tool_for_bucket = bucket_tool.get(bucket)
            for win in FARM_TRAJECTORY_WINDOWS:
                fv_b  = bucket_fv_by_win.get(bucket, {}).get(win)
                sc_b  = bucket_sc.get(bucket)
                bucket_blend_by_win[bucket][win] = _blend_dvm_3way(fv_b, tool_for_bucket, sc_b)
        # Side-level: weighted average across hitter / pitcher buckets.
        hit_by_window: dict[str, int | None] = {}
        pit_by_window: dict[str, int | None] = {}
        for win in FARM_TRAJECTORY_WINDOWS:
            hit_buckets_at_win = {b: bucket_blend_by_win[b][win] for b in _HIT_BUCKETS}
            pit_buckets_at_win = {b: bucket_blend_by_win[b][win] for b in _PIT_BUCKETS}
            hit_by_window[win] = _pos_weighted_blend(hit_buckets_at_win, _POS_WEIGHTS_HIT)
            pit_by_window[win] = _pos_weighted_blend(pit_buckets_at_win, _POS_WEIGHTS_PIT)
            # Fallback to the legacy org-wide blend if every bucket was sparse.
            if hit_by_window[win] is None:
                hit_by_window[win] = _blend_dvm_3way(hit_overall.get(win), tool_hit, hit_sc)
            if pit_by_window[win] is None:
                pit_by_window[win] = _blend_dvm_3way(pit_overall.get(win), tool_pit, pit_sc)
        # Stamp tree node + new pos_buckets sub-payload for UI.
        entry["tree"]["dev_hitter"]["dvm_plus"]            = hit_by_window.get(FARM_PRINCIPAL_WINDOW)
        entry["tree"]["dev_hitter"]["dvm_plus_by_window"]  = hit_by_window
        entry["tree"]["dev_hitter"]["overall_dvm_plus"]    = dict(hit_overall)
        entry["tree"]["dev_hitter"]["statcast_dvm_plus"]   = hit_sc
        entry["tree"]["dev_hitter"]["disparity_by_window"] = _disparity_report(hit_overall, tool_hit)
        # v30.8 — Per-bucket Tool DvM+ now reflects the bucket-specific
        # aggregate from _attach_per_tool_dvm_plus's bucket-aware
        # league pass (with hybrid fallback to org-side-wide when the
        # bucket cohort is too sparse for its own aggregation).
        entry["tree"]["dev_hitter"]["pos_buckets"] = {
            bucket: {
                "fv_dvm_plus_by_window": bucket_fv_by_win.get(bucket, {}),
                "tool_dvm_plus":         int(round(bucket_tool[bucket])) if bucket_tool.get(bucket) is not None else None,
                "tool_dvm_plus_is_bucket_specific": (per_tool_dvm_buckets.get(bucket) and
                                                     any(v is not None for v in (per_tool_dvm_buckets.get(bucket) or {}).values())),
                "statcast_dvm_plus":     bucket_sc.get(bucket),
                "blend_by_window":       bucket_blend_by_win[bucket],
                "active_count":          (entry.get("_pos_bucket_active_count") or {}).get(bucket, 0),
                "weight":                _POS_WEIGHTS_HIT[bucket],
            }
            for bucket in _HIT_BUCKETS
        }
        entry["tree"]["dev_pitcher"]["dvm_plus"]           = pit_by_window.get(FARM_PRINCIPAL_WINDOW)
        entry["tree"]["dev_pitcher"]["dvm_plus_by_window"] = pit_by_window
        entry["tree"]["dev_pitcher"]["overall_dvm_plus"]   = dict(pit_overall)
        entry["tree"]["dev_pitcher"]["statcast_dvm_plus"]  = pit_sc
        entry["tree"]["dev_pitcher"]["disparity_by_window"] = _disparity_report(pit_overall, tool_pit)
        entry["tree"]["dev_pitcher"]["pos_buckets"] = {
            bucket: {
                "fv_dvm_plus_by_window": bucket_fv_by_win.get(bucket, {}),
                "tool_dvm_plus":         int(round(bucket_tool[bucket])) if bucket_tool.get(bucket) is not None else None,
                "tool_dvm_plus_is_bucket_specific": (per_tool_dvm_buckets.get(bucket) and
                                                     any(v is not None for v in (per_tool_dvm_buckets.get(bucket) or {}).values())),
                "statcast_dvm_plus":     bucket_sc.get(bucket),
                "blend_by_window":       bucket_blend_by_win[bucket],
                "active_count":          (entry.get("_pos_bucket_active_count") or {}).get(bucket, 0),
                "weight":                _POS_WEIGHTS_PIT[bucket],
            }
            for bucket in _PIT_BUCKETS
        }
        # Clean up the temporary _ scratch fields so they don't bloat
        # the exported JSON payload.
        entry.pop("_pos_bucket_fv_history", None)
        entry.pop("_pos_bucket_fv_dvm_plus", None)
        entry.pop("_pos_bucket_sc_means", None)
        entry.pop("_pos_bucket_sc_counts", None)
        entry.pop("_pos_bucket_active_count", None)

    # Helper: normalize a list where some entries may be None (small-
    # sample orgs without enough data). None values get the cohort
    # median, so they sit dead-center in the blend instead of dragging
    # the org to either extreme.
    def _normalize_with_none(values: list[float | None]) -> list[float]:
        present = [v for v in values if v is not None]
        if not present:
            return [50.0] * len(values)
        norm = _normalize_to_100(present)
        med = sorted(norm)[len(norm) // 2] if norm else 50.0
        out: list[float] = []
        idx = 0
        for v in values:
            if v is None:
                out.append(med)
            else:
                out.append(norm[idx]); idx += 1
        return out

    top_end_100 = _normalize_to_100([e["top_end_points"]      for e in org_summary])
    depth_100   = _normalize_to_100([e["depth_points"]        for e in org_summary])
    # DvM+ replaces raw trajectory in the blend. The 1y window is the
    # default report-card axis (matches the old behavior of using the
    # 1y trajectory). DvM+ values are already 100-anchored, but we
    # rescale them through _normalize_to_100 so the 0-100 band is
    # consistent with the other components.
    dvm_plus_100 = _normalize_to_100([e["dvm_plus"]["1y"]     for e in org_summary])
    grad_100     = _normalize_to_100([e["grad_pipeline_score"] for e in org_summary])
    # Also expose trajectory_100 for back-compat (UI tooltip still shows
    # the raw value even though it no longer drives the letter grade).
    traj_100     = _normalize_to_100([e["trajectory_score"]    for e in org_summary])

    # New components — None-safe normalization for small-sample orgs.
    wag_100    = _normalize_with_none([(e["talent_translation"] or {}).get("wag_mean")        for e in org_summary])
    roi_100    = _normalize_with_none([(e["financial_roi"]      or {}).get("war_per_million") for e in org_summary])
    tools_100  = _normalize_with_none([(e["tools_quality"]      or {}).get("top10_mean")      for e in org_summary])
    # International depth: 0.7 * IFA% + 0.3 * (year_span / 10), capped.
    def _intl_score(e):
        d = e["international_depth"] or {}
        return 0.7 * (d.get("ifa_pct") or 0) + 0.3 * min((d.get("year_span") or 0) / 10.0, 1.0)
    intl_100   = _normalize_to_100([_intl_score(e) for e in org_summary])
    ready_100  = _normalize_to_100([(e["readiness"] or {}).get("pct_signal", 0) for e in org_summary])
    # Health is INVERTED — lower burden score = better. Negate before
    # normalization so the LOWEST burden gets the HIGHEST 100-score.
    health_100 = _normalize_to_100([-(e["health_burden"] or {}).get("score", 0) for e in org_summary])

    for entry, te, dp, dvm, gr, tr, wg, ro, tq, intl, rd, hl in zip(
        org_summary, top_end_100, depth_100, dvm_plus_100, grad_100, traj_100,
        wag_100, roi_100, tools_100, intl_100, ready_100, health_100,
    ):
        entry["score_components"] = {
            "top_end_100":             te,
            "depth_100":               dp,
            "dvm_plus_100":            dvm,
            "grad_100":                gr,
            "trajectory_100":          tr,   # back-compat / tooltip
            "talent_translation_100":  wg,
            "financial_roi_100":       ro,
            "tools_quality_100":       tq,
            "intl_depth_100":          intl,
            "readiness_100":           rd,
            "health_burden_100":       hl,
        }
        # Legacy 10-component blend — preserved on entry so anything that
        # already references farm_score before the tree composite below
        # overwrites it keeps a value to fall back to.
        entry["farm_score_legacy"] = round(
            FARM_WEIGHT_TOP_END             * te
          + FARM_WEIGHT_DEPTH               * dp
          + FARM_WEIGHT_DVM_PLUS            * dvm
          + FARM_WEIGHT_GRAD                * gr
          + FARM_WEIGHT_TALENT_TRANSLATION  * wg
          + FARM_WEIGHT_FINANCIAL_ROI       * ro
          + FARM_WEIGHT_TOOLS_QUALITY       * tq
          + FARM_WEIGHT_INTL_DEPTH          * intl
          + FARM_WEIGHT_READINESS           * rd
          + FARM_WEIGHT_HEALTH              * hl,
            1,
        )
        # farm_score gets overwritten with the tree composite below; we
        # set it here so the field exists if downstream code reads it
        # before the tree pass finishes.
        entry["farm_score"] = entry["farm_score_legacy"]

    # Per-component ranks (1 = best) feed the component letter grades on
    # the report card. The overall rank/letter come from farm_score.
    n_orgs = len(org_summary)
    top_end_rank = _rank_descending([e["top_end_points"]       for e in org_summary])
    depth_rank   = _rank_descending([e["depth_points"]         for e in org_summary])
    dvm_rank     = _rank_descending([e["dvm_plus"]["1y"]       for e in org_summary])
    traj_rank    = _rank_descending([e["trajectory_score"]     for e in org_summary])
    grad_rank    = _rank_descending([e["grad_pipeline_score"]  for e in org_summary])
    overall_rank = _rank_descending([e["farm_score"]           for e in org_summary])

    # Helper to rank a sparse list (None → rank=None, gets "—" letter).
    def _rank_with_none(values: list[float | None]) -> list[int | None]:
        present_idx = [i for i, v in enumerate(values) if v is not None]
        present_vals = [values[i] for i in present_idx]
        sub_ranks = _rank_descending(present_vals)
        out: list[int | None] = [None] * len(values)
        for i, r in zip(present_idx, sub_ranks):
            out[i] = r
        return out

    wag_rank    = _rank_with_none([(e["talent_translation"] or {}).get("wag_mean")        for e in org_summary])
    roi_rank    = _rank_with_none([(e["financial_roi"]      or {}).get("war_per_million") for e in org_summary])
    tools_rank  = _rank_with_none([(e["tools_quality"]      or {}).get("top10_mean")      for e in org_summary])
    intl_rank   = _rank_descending([_intl_score(e)                                          for e in org_summary])
    ready_rank  = _rank_descending([(e["readiness"]      or {}).get("pct_signal", 0)        for e in org_summary])
    # Health rank: LOWEST burden score = rank 1 (best). _rank_descending
    # ranks highest first, so negate the score before passing.
    health_rank = _rank_descending([-(e["health_burden"] or {}).get("score", 0)             for e in org_summary])
    n_with_wag    = sum(1 for r in wag_rank   if r is not None)
    n_with_roi    = sum(1 for r in roi_rank   if r is not None)
    n_with_tools  = sum(1 for r in tools_rank if r is not None)

    for entry, te_r, dp_r, dvm_r, gr_r, tr_r, ov_r, wg_r, ro_r, tq_r, intl_r, rd_r, hl_r in zip(
        org_summary, top_end_rank, depth_rank, dvm_rank, grad_rank, traj_rank, overall_rank,
        wag_rank, roi_rank, tools_rank, intl_rank, ready_rank, health_rank,
    ):
        entry["component_ranks"] = {
            "top_end":            te_r,
            "depth":              dp_r,
            "dvm_plus":           dvm_r,
            "trajectory":         tr_r,
            "grad":               gr_r,
            "talent_translation": wg_r,
            "financial_roi":      ro_r,
            "tools_quality":      tq_r,
            "intl_depth":         intl_r,
            "readiness":          rd_r,
            "health_burden":      hl_r,
        }
        # Letter grades. None ranks → "—" (insufficient data). Small
        # samples for WAG / ROI / Tool Quality also get "—" via the same
        # gate so a 1-graduate org doesn't get an A or D off a single
        # data point.
        entry["grades"] = {
            "top_end":            _letter_grade(te_r, n_orgs),
            "depth":              _letter_grade(dp_r, n_orgs),
            "dvm_plus":           _letter_grade(dvm_r, n_orgs),
            "trajectory":         _letter_grade(tr_r, n_orgs),
            "grad":               _letter_grade(gr_r, n_orgs),
            "talent_translation": (_letter_grade(wg_r, n_with_wag)
                                    if wg_r is not None
                                    and (entry["talent_translation"]["grad_count"] or 0) >= 3 else "—"),
            "financial_roi":      (_letter_grade(ro_r, n_with_roi)
                                    if ro_r is not None
                                    and (entry["financial_roi"]["grad_count_with_bonus"] or 0) >= 3 else "—"),
            "tools_quality":      (_letter_grade(tq_r, n_with_tools)
                                    if tq_r is not None
                                    and (entry["tools_quality"]["graded_count"] or 0) >= 5 else "—"),
            "intl_depth":         _letter_grade(intl_r, n_orgs),
            "readiness":          _letter_grade(rd_r, n_orgs),
            "health_burden":      _letter_grade(hl_r, n_orgs),
            "overall":            _letter_grade(ov_r, n_orgs),
        }

    _phase_done("report_card")
    # ────────────────────────────────────────────────────────────────────────
    # ── Farm Grade Tree v2 — main grade composites + new farm_score ──
    # ────────────────────────────────────────────────────────────────────────
    # 11 leaf metrics, each independently z-normalized across orgs.
    # Sparse-data orgs get None for that leaf and the parent main grade
    # falls back to the mean of its present sub-grades. Composite
    # farm_score = weighted sum of the 5 main-grade 100-anchored scores.

    def _zscore_to_100(values: list[float | None],
                       higher_is_better: bool = True) -> list[float | None]:
        """Per-org list → 100-anchored z-score list. None stays None.
        Mirrors the wRC+/OPS+ 100-anchor (μ → 100, +1σ → 110)."""
        present = [v for v in values if v is not None]
        if len(present) < 3:
            return [None] * len(values)
        mu = sum(present) / len(present)
        var = sum((v - mu) ** 2 for v in present) / len(present)
        sd = var ** 0.5
        if sd < 1e-6:
            return [100.0 if v is not None else None for v in values]
        sign = 1.0 if higher_is_better else -1.0
        out: list[float | None] = []
        for v in values:
            if v is None:
                out.append(None)
            else:
                out.append(round(100 + 10 * sign * (v - mu) / sd, 1))
        return out

    # ── v3 leaf scoring with multi-input composites ──
    # Some leaves blend 2-3 z-scored sub-inputs (e.g. IFA Performance =
    # WAG + WAR/yr + Cumulative WAR). Each sub-input is anchored at 100
    # across orgs with present data; the leaf score is the mean of
    # present sub-input scores per org. Single-input leaves use the
    # existing 1-input z-score path.
    LEAF_SPECS: dict[str, list[tuple[str, callable]]] = {
        # IFA Performance — v17: use WAR-based signals only. Primary input
        # is WAR/yr across IFA grads (raw production proxy); secondary is
        # cumulative WAR across the same cohort (total impact proxy).
        # WAG was previously layered in but the user wants WAG isolated to
        # the talent_translation leaf so it doesn't confound raw-production
        # signals.
        "acq_ifa": [
            ("war_per_yr_mean", lambda e: (e["tree"]["acq_ifa"] or {}).get("war_per_yr_mean")),
            ("career_war_mean", lambda e: (e["tree"]["acq_ifa"] or {}).get("career_war_mean")),
        ],
        # Draft Performance — pick-slot-adjusted value + ceiling-hits %
        "acq_draft": [
            # `is None` (not `or`): pick_value_mean is a DELTA metric whose natural
            # center is 0.0 - a legitimate exactly-average 0.0 must not be silently
            # replaced by the wag_mean fallback.
            ("pick_value", lambda e: ((e["tree"]["acq_draft"] or {}).get("wag_mean")
                                      if (e["tree"]["acq_draft"] or {}).get("pick_value_mean") is None
                                      else (e["tree"]["acq_draft"] or {}).get("pick_value_mean"))),
            ("ceiling_pct", lambda e: (e["tree"]["acq_draft"] or {}).get("ceiling_hits_pct")),
        ],
        # v30.7 — Trade Acumen now scores on REALIZED outcomes only —
        # net WAR delta (in-WAR minus out-WAR across all trades).
        # net_fv (the projection-side proxy) was the original signal
        # but is biased toward high-volume traders: an org that ships
        # 12 FV-40 lottery tickets for one FV-55 grades net-positive
        # on FV but tells you nothing about whether the FV-55 panned
        # out. WAR is the only signal that closes the outcome loop.
        # net_fv stays on the tree node for context display.
        # v31.8 — Surplus delta added as a co-scoring signal alongside
        # war_delta. war_delta is backward-looking (only counts debuted
        # players' realized WAR); surplus_delta closes the loop on
        # trades whose outcomes haven't crystallized yet — debuted
        # players use WAR × $8M/WAR, prospects use FV-anchored surplus.
        # Both inputs blend equally inside leaf_100 normalization so
        # an org that nets +5 WAR delta AND +30M surplus delta grades
        # better than one that nets +5 WAR but is currently down on
        # prospect-side surplus.
        "tx_trades": [
            ("war_delta",     lambda e: (e["tree"]["tx_trades"] or {}).get("war_delta")),
            ("surplus_delta", lambda e: (e["tree"]["tx_trades"] or {}).get("surplus_delta")),
        ],
        # v30.7 — Waiver Claims is now a pure hit-rate leaf. The prior
        # 50/50 blend of net_fv + hit_rate let big-system orgs win on
        # raw aggregate (more bodies in = more FV in) without
        # rewarding actual claim quality. Hit-rate ("share of claims
        # that reached MLB") measures org judgment about WHO to claim,
        # independent of volume, which is the signal Waiver Claims is
        # meant to capture. net_fv still ships on the tree node for
        # users who want to inspect the underlying totals.
        "tx_waivers": [
            ("hit_rate", lambda e: (e["tree"]["tx_waivers"] or {}).get("hit_rate")),
        ],
        # Development — v16: 6yDvM+ is the PRINCIPAL driver (heaviest
        # weight). 6yDvM+ measures the org's aggregate FV growth over a
        # full 6-year window — the most stable, multi-cycle development
        # signal. Per-tool DvM+ stays as a secondary input so granular
        # tool-development still shows through. Each leaf now has two
        # inputs blended equally inside leaf_100 normalization; the 6y
        # signal effectively dominates because it has wider stdev.
        # v41 — Org-wide principal-window DvM+ is the PRINCIPAL dev signal at an
        # explicit 2.0 weight vs the per-tool DvM+ at 1.0 (the same ~2/3 dominance
        # the old code got by DOUBLE-COUNTING the 6y getter; now stated as a real
        # weight, no duplication). Anchored on FARM_PRINCIPAL_WINDOW so the dev
        # leaf moves with the selected window.
        "dev_hitter":  [
            ("principal_dvm", lambda e: (e.get("dvm_plus") or {}).get(FARM_PRINCIPAL_WINDOW), 2.0),
            ("tool_dvm",      lambda e: (e["tree"]["dev_hitter"]  or {}).get("dvm_plus"), 1.0),
        ],
        "dev_pitcher": [
            ("principal_dvm", lambda e: (e.get("dvm_plus") or {}).get(FARM_PRINCIPAL_WINDOW), 2.0),
            ("tool_dvm",      lambda e: (e["tree"]["dev_pitcher"] or {}).get("dvm_plus"), 1.0),
        ],
        # Financial — single-input each (v18 + active-surplus leaf below)
        "fin_war_per_m":        [("war_per_m", lambda e: (e["tree"]["fin_war_per_m"]        or {}).get("value"))],
        "fin_contract_surplus": [("surplus",   lambda e: (e["tree"]["fin_contract_surplus"] or {}).get("mean_usd_per_yr"))],
        # v18 — Active-surplus: per-prospect normalized so big-system
        # orgs don't auto-win on raw aggregate (they DO win on raw
        # totals, but per-prospect surfaces "this org's actives are
        # net-profitable signings" as a distinct signal from "this org
        # has lots of actives").
        # v32.1 — Now 2-input blend with surplus_per_fv_pt_mm: $/prospect
        # captures "average prospect is net-profitable" while $/FV-pt
        # captures "FV is concentrated in high-leverage spots." Equal
        # 50/50 weight inside the leaf z-blend (the framework averages
        # the two z-scores), so both signals carry the leaf together.
        # v38 — Item-6/7: org $DvM+ graded league-relative (higher = the org's
        # prospects develop faster than peers at the same FV tier).
        "fin_dollar_dvm": [
            ("dollar_dvm_plus", lambda e: (e["tree"].get("fin_dollar_dvm") or {}).get("dollar_dvm_plus")),
        ],
        # v40 — PRIMARY value signal = AGGREGATE risk-adjusted controlled surplus
        # (total $ across the active pool). Pure aggregate (the prior per-prospect
        # spec deliberately normalized aggregate AWAY, v18, which is exactly why a
        # high-total-surplus farm couldn't grade up). The recalibrated value_framework
        # already prices elite ceiling non-linearly, so the total captures top-end-
        # vs-depth without an opaque premium.
        "fin_active_surplus": [
            ("total_surplus", lambda e: e.get("_active_surplus_net_mm")),
        ],
        # MLB Production — v17: renamed mlb_hitter_wag/mlb_pitcher_wag
        # leaves to mlb_hitter_production/mlb_pitcher_production. Primary
        # surfaced stat is WAR/yr (was WAG); WAG moves to a separate
        # talent_translation leaf below. Old key names kept as aliases.
        "mlb_hitter_production": [
            ("war_per_yr", lambda e: (e["tree"]["mlb_hitter_production"] or {}).get("war_per_yr_mean")),
            ("top3_cum_war", lambda e: (e["tree"]["mlb_hitter_production"] or {}).get("top3_career_war")),
        ],
        "mlb_pitcher_production": [
            ("war_per_yr", lambda e: (e["tree"]["mlb_pitcher_production"] or {}).get("war_per_yr_mean")),
            ("top3_cum_war", lambda e: (e["tree"]["mlb_pitcher_production"] or {}).get("top3_career_war")),
        ],
        # v17 — NEW Talent Translation leaf. WAG-based — measures whether
        # graduates outperformed their FV-implied baseline. Sibling to
        # mlb_*_production under the MLB Production parent.
        "talent_translation": [
            ("wag_mean", lambda e: (e["tree"]["talent_translation"] or {}).get("wag_mean")),
        ],
        # v4 NEW leaves under MLB Production.
        "mlb_production_boom_pct": [
            ("boom_pct", lambda e: (e["tree"]["mlb_production_boom_pct"] or {}).get("boom_pct")),
        ],
        # v7 NEW — bust_pct leaf, negated so higher bust% pulls the
        # composite DOWN. Same magnitude weight as boom_pct (equal
        # leaves under the parent), opposite direction.
        "mlb_production_bust_pct": [
            ("bust_pct_neg", lambda e: (
                -(e["tree"]["mlb_production_bust_pct"] or {}).get("bust_pct")
                if (e["tree"]["mlb_production_bust_pct"] or {}).get("bust_pct") is not None
                else None
            )),
        ],
        "mlb_production_top_grads": [
            ("top3_war_per_yr", lambda e: (e["tree"]["mlb_production_top_grads"] or {}).get("top3_war_per_yr")),
        ],
        # v30.7 — Conviction now scored on STAR COUNT (graduates the
        # org developed who hit ≥3 WAR/yr career OR a ≥3.5 WAR season
        # peak). Was a binary 0/1; the count is a stronger signal —
        # an org with 6 stars reads as more conviction-worthy than
        # one with the single Skenes-equivalent. Cached payloads still
        # carry `conviction` (0/1) as a back-compat field, but it no
        # longer drives the leaf grade.
        "mlb_production_conviction": [
            ("star_count", lambda e: (e["tree"]["mlb_production_conviction"] or {}).get("star_count")),
        ],
        # v41 — Graduation PACE. Complements the FV-weighted grad-pipeline POINTS
        # (a trailing-12mo snapshot) with the RHYTHM of quality graduations:
        # FV>=50 debuts per year over the principal window. Rewards a steady
        # MLB-quality stream over one lumpy class; a sustainable-throughput tell.
        "mlb_production_grad_pace": [
            ("grad_pace", lambda e: (e["tree"].get("mlb_production_grad_pace") or {}).get("grad_pace")),
        ],
        # v4 leaf, v32.1 — Now 2-input blend with fv_per_m_pool. The two
        # signals share the same denominator (pool $) but have different
        # numerators: WAR is lagging realized (grads), FV is fast-cycle
        # current (actives from the same draft window). 50/50 weight
        # inside the leaf z-blend so the leaf is responsive to recent
        # drafts (FV side) AND anchored to realized outcomes (WAR side).
        "fin_draft_pool_efficiency": [
            ("war_per_m_pool", lambda e: (e["tree"]["fin_draft_pool_efficiency"] or {}).get("war_per_m_pool")),
            ("fv_per_m_pool",  lambda e: (e["tree"]["fin_draft_pool_efficiency"] or {}).get("fv_per_m_pool")),
        ],
        # v17 — IFA ROI: primary input still WAR/$M IFA spend, but with a
        # fallback to acq_ifa's WAR/yr signal when no bonus dollars are on
        # file. Without the fallback, orgs whose IFA grads pre-date Spotrac
        # bonus coverage rendered "—" and contributed nothing to the
        # financial branch.
        "fin_ifa_roi": [
            ("war_per_m_ifa", lambda e: (e["tree"]["fin_ifa_roi"] or {}).get("war_per_m_ifa")),
            ("war_per_yr_fallback", lambda e: (e["tree"]["fin_ifa_roi"] or {}).get("war_per_yr_fallback")),
        ],
        # v31 — Health Management leaf under Development. Two NEGATED
        # inputs (LOWER burden = HIGHER score):
        #   * il_pct_current  — share of actives currently on IL
        #   * il_days_mean    — avg trailing 12mo IL days per active
        # v31.6 — Post-TJ share REMOVED from scoring. A pitcher being
        # post-TJ isn't inherently bad — the post-surgery grace period
        # often produces above-average outcomes, and a high post-TJ
        # share also reflects past injury exposure rather than current
        # development quality. Post-TJ count still ships on the leaf
        # payload as INFORMATIONAL only (no letter grade, no scoring
        # weight). Hitter post-TJ is dropped entirely from the data
        # model since TJ for hitters is rare enough that the metric
        # was misleading. Each input z-blends independently then
        # averages, sparse-gated downstream by _zscore_to_100's n≥3.
        "dev_health_mgmt": [
            ("il_pct_current_neg", lambda e: (
                -(e["tree"]["dev_health_mgmt"] or {}).get("il_pct_current")
                if (e["tree"]["dev_health_mgmt"] or {}).get("il_pct_current") is not None
                else None
            )),
            ("il_days_mean_neg", lambda e: (
                -(e["tree"]["dev_health_mgmt"] or {}).get("il_days_mean")
                if (e["tree"]["dev_health_mgmt"] or {}).get("il_days_mean") is not None
                else None
            )),
        ],
        # v31 — HOF-track leaf. Single input (count of grads w/ season
        # WAR ≥5). Treated as a higher-is-better scalar so a deeper
        # HOF-track grad list lifts the leaf.
        "mlb_production_hof_track": [
            ("hof_count", lambda e: (e["tree"]["mlb_production_hof_track"] or {}).get("hof_count")),
        ],
        # v31 — Statcast Quality leaf (Development). Single input from
        # the org's aggregate active-prospect Statcast+ mean. Sparse-
        # gated at ≥5 graded prospects (gate enforced upstream in the
        # statcast_quality aggregator).
        "dev_statcast_quality": [
            ("sc_mean", lambda e: (e["tree"]["dev_statcast_quality"] or {}).get("mean")),
        ],
    }
    # Compute each leaf's 100-anchored per-org list. Multi-input leaves
    # z-score each sub-input independently then average the present
    # z-scores per org (so sparse sub-inputs don't drag the leaf to None
    # if at least one is present).
    leaf_100: dict[str, list[float | None]] = {}
    leaf_raw: dict[str, list[float | None]] = {}  # back-compat for tests
    for leaf_key, specs in LEAF_SPECS.items():
        sub_z_lists = []
        sub_weights = []
        for spec in specs:
            getter = spec[1]
            # Optional 3rd element = explicit sub-input weight (defaults 1.0).
            # Lets a leaf weight one sub-input heavier WITHOUT the old
            # double-count hack (listing the same getter twice). Backward-
            # compatible: 2-tuples keep equal weight.
            w = spec[2] if len(spec) > 2 else 1.0
            raw = [getter(e) for e in org_summary]
            sub_z_lists.append(_zscore_to_100(raw, higher_is_better=True))
            sub_weights.append(w)
        # Per-org leaf score = WEIGHTED mean of present sub-input z-scores.
        per_org_scores: list[float | None] = []
        for i in range(len(org_summary)):
            num = 0.0
            den = 0.0
            for zl, w in zip(sub_z_lists, sub_weights):
                if zl[i] is not None:
                    num += zl[i] * w
                    den += w
            per_org_scores.append(round(num / den, 1) if den > 0 else None)
        leaf_100[leaf_key] = per_org_scores
        # Back-compat: leaf_raw[k] points to the FIRST sub-input's raw
        # values (used by some legacy test inspections).
        leaf_raw[leaf_key] = [specs[0][1](e) for e in org_summary]

    # Stamp leaf 100-anchored scores onto each org for display.
    for i, entry in enumerate(org_summary):
        for k, vs in leaf_100.items():
            entry["tree"][k]["score_100"] = vs[i]

    # Build main-grade scores by averaging the 100-anchored leaves
    # present for that parent. Orgs with NO present leaves under a
    # parent get None for that main grade (rare — usually only when
    # all sub-grades sparse-gated out).
    # v3 tree shape — Acquisition Strategy absorbs both the prior
    # Acquisitions (IFA + Draft) and Transactions (Trade + Waiver)
    # branches. Four main parents, ten leaves total.
    # v4: financial branch gains draft-pool efficiency + IFA ROI;
    # mlb_production gains boom%, top-3 WAR/yr, and Conviction.
    # 13 leaves total across 4 parents.
    TREE_PARENTS = {
        "acquisition_strategy": ["acq_ifa", "acq_draft", "tx_trades", "tx_waivers"],
        # v31 — Development picks up Health Management + Statcast
        # Quality leaves alongside the two DvM+ leaves. Health is part
        # of "are prospects progressing on schedule" — a chronically-
        # injured pipeline IS a development outcome, not a separate
        # axis. Statcast Quality surfaces the org's aggregate SC+ as
        # a standalone signal voice (the DvM+ leaves already carry
        # SC+ as their 20% input per-bucket; this leaf adds the
        # org-wide aggregate as a separate axis).
        "development":          ["dev_hitter", "dev_pitcher",
                                  "dev_health_mgmt", "dev_statcast_quality"],
        # v18 — Financial now carries fin_active_surplus alongside the
        # existing leaves. fin_contract_surplus measures graduates'
        # realized contract surplus; fin_active_surplus measures the
        # current actives' EXPECTED surplus net of acquisition cost.
        # Together they cover the full pipeline rather than only the
        # historical grad side.
        "financial":            ["fin_war_per_m", "fin_contract_surplus",
                                  "fin_active_surplus", "fin_dollar_dvm",
                                  "fin_draft_pool_efficiency", "fin_ifa_roi"],
        # v31 — HOF-track count joins MLB Production. Ceiling signal
        # complement to Conviction (which fires on the lower star
        # threshold).
        # v40 — talent_translation (WAG) DROPPED from the rollup: raw realized
        # graduate WAR is the production signal we grade on, not WAR-above-grade
        # (MLB translation matters far less than raw MLB output). The WAG leaf is
        # still computed for display/tooltip, just no longer in the grade.
        "mlb_production":       ["mlb_hitter_production",   # raw WAR/yr (v17)
                                  "mlb_pitcher_production",  # raw WAR/yr (v17)
                                  "mlb_production_boom_pct",
                                  "mlb_production_bust_pct",
                                  "mlb_production_top_grads",
                                  "mlb_production_conviction",
                                  "mlb_production_grad_pace",  # v41 — FV>=50 grads/yr (pace)
                                  "mlb_production_hof_track"],
    }
    # Legacy parent aliases — kept so any UI or test still reading
    # entry["acquisitions_score"] / entry["transactions_score"]
    # resolves to a sensible value (the parent's score, or None).
    for i, entry in enumerate(org_summary):
        for parent, leaves in TREE_PARENTS.items():
            # v9 — per-leaf weights inside a parent when FARM_LEAF_WEIGHTS
            # declares them (currently only Financial). Falls back to
            # equal-weight mean for parents without an entry. Either way
            # weights renormalize across PRESENT leaves so a sparse-data
            # leaf doesn't drag the parent toward 0 — it just drops out
            # and the others split the full 1.0.
            leaf_w = FARM_LEAF_WEIGHTS.get(parent)
            if leaf_w:
                present = [(k, leaf_100[k][i], leaf_w[k])
                           for k in leaves
                           if leaf_100[k][i] is not None and leaf_w.get(k)]
                total_w = sum(w for _, _, w in present)
                if total_w > 0:
                    entry[f"{parent}_score"] = round(
                        sum(v * w for _, v, w in present) / total_w, 1
                    )
                else:
                    entry[f"{parent}_score"] = None
            else:
                vs = [leaf_100[k][i] for k in leaves if leaf_100[k][i] is not None]
                entry[f"{parent}_score"] = (
                    round(sum(vs) / len(vs), 1) if vs else None
                )
        # Composite farm_score from the 4 main grades (v3), weighted.
        # Orgs missing a main grade contribute its weight at 100 (league
        # mean) so the overall doesn't get crushed by data-sparse axes.
        weights = {
            "acquisition_strategy": FARM_TREE_WEIGHT_ACQUISITION_STRATEGY,
            "development":          FARM_TREE_WEIGHT_DEVELOPMENT,
            "financial":            FARM_TREE_WEIGHT_FINANCIAL,
            "mlb_production":       FARM_TREE_WEIGHT_MLB_PRODUCTION,
        }
        composite = 0.0
        for parent, w in weights.items():
            v = entry.get(f"{parent}_score")
            composite += w * (v if v is not None else 100.0)
        # Apply the v6 composite stretch — magnifies distance from the
        # league mean BEFORE the cap + letter-grade pass, so weak orgs
        # sit further below the mean and strong orgs further above.
        # v31 — Stretch factor relaxed 1.35 → 1.20 now that the tree
        # carries deeper leaf granularity (Health Mgmt + HOF-track
        # added; sub-leaves expose internal breakdown). The richer
        # signal mix already spreads distributions wider naturally,
        # so the artificial stretch can ease back. Monotonic (rank
        # order preserved) and the mean is a fixed point.
        # Anchored at mean=100 because each main-grade score lives on
        # the DvM+-style 100-anchored scale (each branch z-rescaled to
        # mean=100 across the 30 orgs).
        #
        # DOES NOT COMPOUND WITH THE 1.35 PER-TOOL STRETCH (checked 2026-07-29).
        # The stretched per-tool DvM+ values do reach this composite, but only
        # through LEAF_SPECS -> _zscore_to_100, which re-standardizes each leaf
        # sub-input across the 30 orgs. z-scoring is invariant to any affine map,
        # so the 1.35 is erased at the leaf boundary and cannot multiply with the
        # 1.20 here; the "1.35 x 1.20 = 1.62x net widening" reading is wrong.
        # (What the 1.35 DOES survive into is the per-bucket blend weight inside
        # _blend_dvm_3way, which is upstream of the leaf; see the note there.)
        # Measured on the served 30-org run: leaf score_100 sd ~9.5 (as designed,
        # ~10), farm_score sd 6.4, i.e. this composite is COMPRESSED relative to
        # its leaves by the parent-averaging even after the 1.20 stretch.
        entry["farm_score"] = _stretch_composite(round(composite, 1), factor=1.20)
        # Back-compat: legacy field names (acquisitions_score,
        # transactions_score) resolve to the merged Acquisition Strategy
        # value so any UI reading the old keys still gets a number.
        entry["acquisitions_score"] = entry.get("acquisition_strategy_score")
        entry["transactions_score"] = entry.get("acquisition_strategy_score")

    # ── v40 — Continuous TIEBREAKER score ─────────────────────────────────
    # Differentiates farms that land on the same letter grade (coarse grades
    # collapse real value gaps). A normalized z-blend across the 30 orgs of the
    # three value dimensions, anchored DvM+-style (100 + 10 * z_blend, where
    # z_blend is the weighted blend RE-STANDARDIZED by its own measured pool sd;
    # see the `_tb_sd` block below for why the raw weighted sum is not unit-sd):
    #   • total surplus      0.40 — aggregate risk-adjusted controlled value ($)
    #   • 6yDvM+             0.25 — the indexed view of the same controlled value
    #   • raw graduate WAR   0.35 — REALIZED MLB production (not WAG) over the grad pool
    # Surplus and 6yDvM+ are the dollar/indexed views of one controlled-value
    # concept, so they share weight rather than double-count; raw grad WAR adds the
    # realized-output axis the paper-value measures can't see. The score gives a
    # finer continuous ordering and orders within-grade ties on the list.
    def _farm_z(vals: list[float | None]) -> list[float]:
        present = [v for v in vals if v is not None]
        if len(present) < 2:
            return [0.0] * len(vals)
        mu = sum(present) / len(present)
        sd = (sum((v - mu) ** 2 for v in present) / len(present)) ** 0.5 or 1.0
        return [((v - mu) / sd if v is not None else 0.0) for v in vals]

    _surp_z = _farm_z([e.get("_active_surplus_net_mm") for e in org_summary])
    _dvm_z  = _farm_z([(e.get("dvm_plus") or {}).get(FARM_PRINCIPAL_WINDOW) for e in org_summary])
    _gwar_z = _farm_z([e.get("_grad_war_total") for e in org_summary])
    # DvM+ term uses the PRINCIPAL (7y) window (matching _dvm_z above); the component key
    # and displayed input read the same 7y value so the label and the number can't disagree
    # (was labeled/displayed as "6y" while the z-score used 7y).
    _TB_W = {"surplus": 0.40, "dvm7y": 0.25, "grad_war": 0.35}
    _tb_blends = [
        (_TB_W["surplus"] * _surp_z[i] + _TB_W["dvm7y"] * _dvm_z[i]
         + _TB_W["grad_war"] * _gwar_z[i])
        for i in range(len(org_summary))
    ]
    # RE-STANDARDIZE the blend before mapping onto the 100 + 10z display scale.
    # Each leg is a unit-variance z, but a WEIGHTED SUM of unit z's only has
    # sd = 1 when the weights are an orthonormal combination, which these are
    # not: surplus and 7yDvM+ are the dollar and indexed views of one
    # controlled-value concept (measured pool correlation +0.52 on the current
    # 30-org run), and the weights sum to 1.0 rather than their squares. The
    # measured blend sd is ~0.70, so the un-restandardized score moved only
    # ~7.0 points per blend-sigma while the "100 + 10z" label promised 10.
    # Dividing by the pool's own measured sd is a positive-scalar map, so the
    # org ORDER is bit-for-bit identical; only the display width changes. Same
    # pattern as _join_fwdhem_plus in hitter_export.py (the house precedent).
    # `blend_sd` ships on the payload so the number and its scale can never
    # diverge silently.
    _tb_mu = sum(_tb_blends) / len(_tb_blends) if _tb_blends else 0.0
    _tb_sd = (
        (sum((b - _tb_mu) ** 2 for b in _tb_blends) / len(_tb_blends)) ** 0.5
        if len(_tb_blends) > 1 else 0.0
    ) or 1.0
    for i, entry in enumerate(org_summary):
        _blend = _tb_blends[i]
        entry["farm_tiebreaker"] = {
            "score": round(100 + 10 * (_blend / _tb_sd), 1),
            "weights": _TB_W,
            "blend_sd": round(_tb_sd, 4),
            "components": {
                "surplus_z":  round(_surp_z[i], 2),
                "dvm7y_z":    round(_dvm_z[i], 2),
                "grad_war_z": round(_gwar_z[i], 2),
            },
            "inputs": {
                "total_surplus_mm": round(entry.get("_active_surplus_net_mm") or 0.0, 1),
                "dvm_plus_7y":      (entry.get("dvm_plus") or {}).get(FARM_PRINCIPAL_WINDOW),
                "grad_war_total":   entry.get("_grad_war_total"),
            },
        }
    # Continuous "true rank" 1-30 by the tiebreaker score (finer than the letter
    # grade); the letter grade still comes from farm_score's rank bucket below.
    # Sorted on the UNROUNDED blend, not on the 1-decimal published score. Two
    # orgs whose scores collide only after display rounding (e.g. 101.26 and
    # 101.31 both printing 101.3) used to be ordered by their position in
    # org_summary, which is arbitrary; now the underlying value decides. This
    # also makes the rank invariant to the display scale, so the blend
    # re-standardization above provably cannot move an org's rank.
    _tb_order = sorted(range(len(org_summary)), key=lambda i: -_tb_blends[i])
    for _r, _i in enumerate(_tb_order, start=1):
        org_summary[_i]["farm_tiebreaker"]["rank"] = _r

    # v18 — Conviction cap removed. The 75th-percentile farm_score cap
    # for orgs without a star-tier graduate in the last 6 years was a
    # hard ceiling that punished young, talent-loaded systems for not
    # yet having a star MLB return. The conviction leaf itself still
    # contributes to the parent rollup (it's just one of the
    # MLB-Production sub-grades now), so the signal isn't lost — but
    # the orgs aren't artificially clamped to the upper-quartile mark.
    # (Was: clamped farm_score to sorted[p75] when conviction==0 +
    # farm_score>cap, and wrote farm_score_uncapped + conviction_cap_applied.)

    # Letter grades for the 11 leaves + 5 main + composite (17 total).
    # Sparse-data leaves get "—"; sparse parents and composite always grade
    # (since they fall back to 100 for missing children).
    def _rank_list(values: list[float | None]) -> list[int | None]:
        idx = [i for i, v in enumerate(values) if v is not None]
        sub = _rank_descending([values[i] for i in idx])
        ranks: list[int | None] = [None] * len(values)
        for i, r in zip(idx, sub):
            ranks[i] = r
        return ranks

    leaf_ranks = {k: _rank_list(vs) for k, vs in leaf_100.items()}
    parent_ranks = {
        parent: _rank_list([e.get(f"{parent}_score") for e in org_summary])
        for parent in TREE_PARENTS
    }
    composite_rank = _rank_list([e["farm_score"] for e in org_summary])

    n_orgs_tree = len(org_summary)
    # v18 — Sparse / missing subgrades render as a neutral "C" (the
    # average-tier letter) instead of "—". The dash communicated
    # "we don't have data" but read as "missing/broken" to most users;
    # defaulting to C preserves that the org is unmeasured-on-this-leaf
    # without leaving a literal gap in the tree visualization. Each
    # sparse leaf also gets a `sparse: true` marker on entry["grades_sparse"]
    # so any future tooltip / UI can dim or annotate the C accordingly.
    _SPARSE_FALLBACK = "C"
    for i, entry in enumerate(org_summary):
        # Update entry["grades"] with the v3 tree grades. Existing legacy
        # grades stay so the report-card glossary references still resolve.
        g = entry.get("grades") or {}
        gs = entry.get("grades_sparse") or {}
        # 4 main grades + back-compat aliases for the old 5-branch names
        for parent in TREE_PARENTS:
            r = parent_ranks[parent][i]
            present_n = sum(1 for x in parent_ranks[parent] if x is not None)
            if r is not None:
                g[parent] = _letter_grade(r, present_n)
            else:
                g[parent] = _SPARSE_FALLBACK
                gs[parent] = True
        # Back-compat: legacy keys still readable by old UI code paths.
        g["acquisitions"] = g.get("acquisition_strategy", _SPARSE_FALLBACK)
        g["transactions"] = g.get("acquisition_strategy", _SPARSE_FALLBACK)
        # 10 sub-grades — keyed identically to leaf_raw
        for k in leaf_raw:
            r = leaf_ranks[k][i]
            present_n = sum(1 for x in leaf_ranks[k] if x is not None)
            if r is not None:
                g[k] = _letter_grade(r, present_n)
            else:
                g[k] = _SPARSE_FALLBACK
                gs[k] = True
        # Composite (overwrites the legacy `overall` letter so the
        # displayed grade matches the displayed farm_score).
        r = composite_rank[i]
        if r is not None:
            g["overall"] = _letter_grade(r, n_orgs_tree)
        else:
            g["overall"] = _SPARSE_FALLBACK
            gs["overall"] = True
        entry["grades"] = g
        entry["grades_sparse"] = gs
        # Also stamp the ranks so the UI can read off them directly.
        cr = entry.get("component_ranks") or {}
        for parent in TREE_PARENTS:
            cr[parent] = parent_ranks[parent][i]
        cr["acquisitions"] = cr.get("acquisition_strategy")  # back-compat
        cr["transactions"] = cr.get("acquisition_strategy")  # back-compat
        for k in leaf_raw:
            cr[k] = leaf_ranks[k][i]
        cr["overall"] = composite_rank[i]
        entry["component_ranks"] = cr

    # Final sort + farm_rank assignment off of farm_score. Tiebreak by
    # top_end_points so the org with better stars edges out an equal one.
    org_summary.sort(key=lambda x: (-x["farm_score"], -x["top_end_points"]))
    for rank_i, entry in enumerate(org_summary, start=1):
        entry["farm_rank"] = rank_i

    # v31 — Attach sub_leaves payload to every tree leaf node so the
    # renderer's third column can show "what this leaf is made of".
    # Runs AFTER farm_rank assignment so the helper has the final tree
    # state to walk.
    for entry in org_summary:
        _attach_sub_leaves(entry)

    # v41 — Server-side farm-rank movement chip. Replaces the old client-side
    # "since your last visit" localStorage delta with an event-based "since the
    # last real change" signal from the de-noised engine. Reads the
    # farm_rank_history accrued by prior monthly runs, appends today's
    # freshly-assigned (rank, score) as the anchor (dropping any same-day row so
    # a re-run doesn't double-count), and walks back to the most recent genuine
    # rank step. Until a few months of history accrue every org reads flat —
    # expected, not a bug. Best-effort: a failure here must never abort the
    # export, so each entry still gets a (null) rank_movement key.
    try:
        from movement import compute_farm_movement
        _today_iso = date.today().isoformat()
        _hist_by_org: dict[str, list[dict]] = {}
        for _row in load_farm_rank_history():
            _hist_by_org.setdefault(_row["org"], []).append(_row)
        for entry in org_summary:
            _org = entry.get("org")
            _hist = [h for h in _hist_by_org.get(_org, [])
                     if h.get("snapshot_date") != _today_iso]
            _hist.append({"org": _org, "snapshot_date": _today_iso,
                          "farm_rank": entry.get("farm_rank"),
                          "farm_score": entry.get("farm_score")})
            entry["rank_movement"] = compute_farm_movement(_hist)
    except Exception:
        for entry in org_summary:
            entry.setdefault("rank_movement", None)

    # v31.1 — League pass that LETTER-GRADES selected sub-leaves so the
    # third tree column reads as another grade layer, not just a value
    # display. Currently grades:
    #   * Hitter/Pitcher DvM+ pos-bucket sub-leaves (C/INF/OF, SP/RP)
    #     — z-scores each bucket's 6y blend value across all 30 orgs,
    #     then assigns a letter grade so the user sees, e.g., that
    #     SEA grades A+ on their OF bucket development but C on
    #     their C bucket.
    # Sparse buckets (sub_leaves entry with sparse=true) are excluded
    # from the league cohort and grade as "—". Output is a `letter`
    # field on each sub_leaf dict (renderer renders it when present).
    # Helper: z-score → letter grade. Anchored at C (mean) with
    # symmetric stops at ±0.15σ (C+/C-), ±0.4σ (B-/D+), ±0.7σ (B/D),
    # ±1.0σ (B+/D-), ±1.5σ (A-/F), ±2.0σ (A/F-tail), beyond +2.0σ (A+).
    # Walks from the high side down so the most-extreme bucket fires
    # first. Anchored at the league MEAN (z=0 → C) so grades read as
    # "how far above/below league average is this org" rather than
    # rank position (which is misleading when only 3-5 orgs have data).
    def _z_to_letter(z: float) -> str:
        if z >=  2.0: return "A+"
        if z >=  1.5: return "A"
        if z >=  1.0: return "A-"
        if z >=  0.7: return "B+"
        if z >=  0.4: return "B"
        if z >=  0.15: return "B-"
        if z >= -0.15: return "C"
        if z >= -0.4: return "C-"
        if z >= -0.7: return "D+"
        if z >= -1.0: return "D"
        if z >= -1.5: return "D-"
        return "F"

    # Grade one sub-leaf label across the league. Pulls each org's
    # value, computes league mean + stdev across present values, then
    # maps each org's z-score (sign-flipped for lower-is-better) to a
    # letter via the schedule above. Missing / sparse entries default
    # to "C" (the league-mean grade) instead of "—" so the tree never
    # shows a literal gap.
    def _grade_sub_leaf_across_league(leaf_key: str, sub_label: str,
                                       higher_is_better: bool = True) -> None:
        vals: list[float | None] = []
        for entry in org_summary:
            node = (entry.get("tree") or {}).get(leaf_key) or {}
            subs = node.get("sub_leaves") or []
            match = next((s for s in subs if s.get("label") == sub_label), None)
            if not match or match.get("sparse") or match.get("value") is None:
                vals.append(None)
            else:
                vals.append(float(match["value"]))
        present_vals = [v for v in vals if v is not None]
        n_present = len(present_vals)
        # Need ≥3 present values to compute meaningful mean + stdev.
        # Below that, default everyone to "C".
        if n_present >= 3:
            mu = sum(present_vals) / n_present
            var = sum((v - mu) ** 2 for v in present_vals) / n_present
            sd = var ** 0.5
        else:
            mu, sd = 0.0, 0.0
        sign = 1.0 if higher_is_better else -1.0
        for i, v in enumerate(vals):
            entry = org_summary[i]
            node = (entry.get("tree") or {}).get(leaf_key) or {}
            subs = node.get("sub_leaves") or []
            match = next((s for s in subs if s.get("label") == sub_label), None)
            if match is None:
                continue
            if v is None or sd < 1e-9:
                # Missing value or zero-variance cohort → default to C.
                # Mark sparse_default so the renderer can show this is
                # a placeholder grade (the value itself is sparse, so
                # we're inferring it sits at the league mean).
                match["letter"] = "C"
                match["sparse_default"] = True
                match["rank_n"] = n_present
            else:
                z = sign * (v - mu) / sd
                match["letter"] = _z_to_letter(z)
                match["z_score"] = round(z, 2)
                match["rank_n"]  = n_present

    # Pos-bucket DvM+ sub-leaves (Hitter C/INF/OF, Pitcher SP/RP).
    _bucket_groups = [
        ("dev_hitter",  ("C", "INF", "OF")),
        ("dev_pitcher", ("SP", "RP")),
    ]
    for leaf_key, buckets in _bucket_groups:
        for bucket in buckets:
            _grade_sub_leaf_across_league(leaf_key, f"{bucket} bucket")

    # v31.5 — Per-tool DvM+ sub-leaves. Each tool's value is already
    # 100-anchored across the league (computed earlier), so grading
    # here just maps each org's value to a letter via z-score vs the
    # cohort mean. Higher tool DvM+ = better.
    _PER_TOOL_LABELS = {
        "dev_hitter":  ["HIT", "PWR", "SPD", "FLD", "ARM", "PSEL", "BCT"],
        "dev_pitcher": ["FB", "SL", "CB", "CH", "CMD", "CT"],
    }
    for leaf_key, tool_labels in _PER_TOOL_LABELS.items():
        for tool_label in tool_labels:
            _grade_sub_leaf_across_league(leaf_key, tool_label)

    # Draft round-tier + IFA bonus-tier sub-leaves.
    for tier_label in ("1st round (R1)", "Day 1 (R2-R10)", "Late (R11+)"):
        _grade_sub_leaf_across_league("acq_draft", tier_label)
    for tier_label in ("Top (≥$2M)", "Mid ($500K-$2M)", "Lower / unknown bonus"):
        _grade_sub_leaf_across_league("acq_ifa", tier_label)

    # Per-side health splits (LOWER IS BETTER — fewer on IL = better
    # letter). v31.6 — Post-TJ removed from grading (now info-only;
    # hitter TJ removed entirely as a metric). Only IL share splits
    # remain graded.
    for split_label in ("Pitcher IL share", "Hitter IL share"):
        _grade_sub_leaf_across_league("dev_health_mgmt", split_label,
                                       higher_is_better=False)
    # Org-wide health signals — same lower-is-better direction.
    for hsig_label in ("Currently on IL", "Avg IL days / active (12mo)"):
        _grade_sub_leaf_across_league("dev_health_mgmt", hsig_label,
                                       higher_is_better=False)

    # Statcast Quality sub-leaves (higher SC+ = better).
    for scq_label in ("Hitter SC+ mean", "Pitcher SC+ mean", "All graded actives"):
        _grade_sub_leaf_across_league("dev_statcast_quality", scq_label)

    # Acquisition aggregate sub-leaves (after tier-specific grading).
    for d_label in ("Pick value vs slot", "Ceiling hits", "Sleeper hit rate"):
        _grade_sub_leaf_across_league("acq_draft", d_label)
    for i_label in ("WAR/yr mean", "Career WAR mean", "Sleeper hit rate"):
        _grade_sub_leaf_across_league("acq_ifa", i_label)

    # Trade Acumen splits (higher inbound better; lower outbound
    # better — outbound WAR is "talent we gave up").
    _grade_sub_leaf_across_league("tx_trades", "Inbound WAR")
    _grade_sub_leaf_across_league("tx_trades", "Outbound WAR", higher_is_better=False)
    _grade_sub_leaf_across_league("tx_trades", "Unweighted WAR Δ")

    # Waiver Claims hit rate.
    _grade_sub_leaf_across_league("tx_waivers", "Hit rate")

    # MLB Production hitter/pitcher splits.
    for prod_label in ("WAR/yr mean", "Top-3 cum WAR", "WAG mean"):
        _grade_sub_leaf_across_league("mlb_hitter_production", prod_label)
        _grade_sub_leaf_across_league("mlb_pitcher_production", prod_label)
    # v31.5 — Per-position-bucket Production sub-leaves.
    for hbkt in ("C", "INF", "OF"):
        _grade_sub_leaf_across_league("mlb_hitter_production", f"{hbkt} grads")
    for pbkt in ("SP", "RP"):
        _grade_sub_leaf_across_league("mlb_pitcher_production", f"{pbkt} grads")

    # Top Grads / Conviction / HOF sub-leaves.
    _grade_sub_leaf_across_league("mlb_production_top_grads", "Top-3 mean WAR/yr")
    _grade_sub_leaf_across_league("mlb_production_conviction", "Star count")
    _grade_sub_leaf_across_league("mlb_production_conviction", "Peak career WAR/yr")
    # HOF-track label uses the threshold inline; resolve dynamically.
    for entry in org_summary:
        hof = (entry.get("tree") or {}).get("mlb_production_hof_track") or {}
        subs = hof.get("sub_leaves") or []
        for s in subs:
            # Mark the count + peak labels for grading.
            if s.get("label", "").startswith("Seasons ≥") or s.get("label") == "Peak season WAR":
                pass  # handled in the loop below
    _grade_sub_leaf_across_league("mlb_production_hof_track", "Peak season WAR")
    # The Seasons ≥N WAR label embeds the threshold (default 5); grade
    # whatever the actual label happens to be on each org's payload.
    _hof_count_label = None
    for entry in org_summary:
        hof = (entry.get("tree") or {}).get("mlb_production_hof_track") or {}
        subs = hof.get("sub_leaves") or []
        for s in subs:
            if s.get("label", "").startswith("Seasons ≥"):
                _hof_count_label = s["label"]
                break
        if _hof_count_label:
            break
    if _hof_count_label:
        _grade_sub_leaf_across_league("mlb_production_hof_track", _hof_count_label)

    # Active Surplus per-prospect (higher better; Cost basis is
    # informational only — not graded). v31.5 — also grade the per-
    # side splits.
    _grade_sub_leaf_across_league("fin_active_surplus", "$ / prospect")
    _grade_sub_leaf_across_league("fin_active_surplus", "Hitter $/prospect")
    _grade_sub_leaf_across_league("fin_active_surplus", "Pitcher $/prospect")

    # v31.5 — Financial WAR per $M channel split (Draft / IFA / Other).
    for chan_label in ("Draft $", "IFA $", "Other $"):
        _grade_sub_leaf_across_league("fin_war_per_m", chan_label)

    # v31.4 — Per-window letter grades for the DvM+ leaves. Lets the
    # frontend's 1y/3y/6y window selector ACTUALLY change the leaf
    # grade (not just the displayed DvM+ value). Stamps a
    # `grades_by_window` dict on each org keyed by window → {leaf: letter}.
    # Renderer reads this when state.formWindow changes; if absent it
    # falls back to the canonical `grades[leaf]` (which anchors on 6y).
    for entry in org_summary:
        entry["grades_by_window"] = {}
    for win in FARM_TRAJECTORY_WINDOWS:
        for leaf_key in ("dev_hitter", "dev_pitcher"):
            vals = []
            for entry in org_summary:
                node = (entry.get("tree") or {}).get(leaf_key) or {}
                v = (node.get("dvm_plus_by_window") or {}).get(win)
                vals.append(float(v) if v is not None else None)
            present = [v for v in vals if v is not None]
            n_p = len(present)
            if n_p >= 3:
                mu = sum(present) / n_p
                var = sum((v - mu) ** 2 for v in present) / n_p
                sd = var ** 0.5
            else:
                mu, sd = 0.0, 0.0
            for i, v in enumerate(vals):
                entry = org_summary[i]
                gbw = entry.setdefault("grades_by_window", {})
                wmap = gbw.setdefault(win, {})
                if v is None or sd < 1e-9:
                    wmap[leaf_key] = "C"
                else:
                    z = (v - mu) / sd
                    wmap[leaf_key] = _z_to_letter(z)

    # v31.5 — Per-window letter grades for MLB Production + Acquisition
    # leaves. Filters the per-grad records by recency (last_mlb_year for
    # production, acquisition year for acquisition leaves) so the
    # window selector actually reshapes those grades too. Tree node
    # `_top_grads` carries last_mlb_year + method; `acquisitions` table
    # carries the per-prospect year. We re-aggregate per-window then
    # z-score-grade across the league.
    _now_yr = date.today().year
    # Unified to the full trailing-window set so MLB-production / acquisition
    # recency filters track the SAME windows as DvM+ (year-rounded from days).
    _WINDOWS = {k: max(1, round(d / 365)) for k, d in FARM_TRAJECTORY_WINDOWS.items()}
    # Production windowing: aggregate WAR/yr from grads whose
    # last_mlb_year is within the window, per side (hitter vs pitcher).
    _PROD_LEAF_BY_SIDE = {False: "mlb_hitter_production",
                           True:  "mlb_pitcher_production"}
    for win_label, win_years in _WINDOWS.items():
        for is_pit, leaf_key in _PROD_LEAF_BY_SIDE.items():
            # Collect per-org WAR/yr mean for grads in window.
            org_vals = []
            for entry in org_summary:
                gagg_grads = (entry.get("_top_grads_for_windowing") or [])
                # _top_grads_for_windowing is populated below; fall back
                # to the persistent grad list on the tree-builder bucket
                # which we keep as _top_grads.
                if not gagg_grads:
                    # build it once: pull from entry's stashed _top_grads
                    # which we preserved on entry as _top_grads_raw.
                    gagg_grads = entry.get("_top_grads_raw") or []
                vals_w = []
                for g in gagg_grads:
                    if bool(g.get("is_pitcher")) != is_pit:
                        continue
                    lmy = g.get("last_mlb_year")
                    wpy = g.get("war_per_yr")
                    if lmy is None or wpy is None:
                        continue
                    if _now_yr - int(lmy) <= win_years:
                        vals_w.append((float(wpy), g.get("w", 1.0)))
                # VAL_4: share-weighted mean, gated on graduate-equivalents
                _wsum = sum(w for _, w in vals_w)
                org_mean = (sum(v * w for v, w in vals_w) / _wsum) if _wsum >= 3 else None
                org_vals.append(org_mean)
            present = [v for v in org_vals if v is not None]
            n_p = len(present)
            if n_p >= 3:
                mu = sum(present) / n_p
                var = sum((v - mu) ** 2 for v in present) / n_p
                sd = var ** 0.5
            else:
                mu, sd = 0.0, 0.0
            for i, v in enumerate(org_vals):
                entry = org_summary[i]
                gbw = entry.setdefault("grades_by_window", {})
                wmap = gbw.setdefault(win_label, {})
                if v is None or sd < 1e-9:
                    wmap[leaf_key] = "C"
                else:
                    z = (v - mu) / sd
                    wmap[leaf_key] = _z_to_letter(z)
                # Also stamp the windowed value on the tree node for
                # display.
                node = (entry.get("tree") or {}).get(leaf_key) or {}
                wpy_map = node.setdefault("war_per_yr_by_window", {})
                wpy_map[win_label] = round(v, 2) if v is not None else None
    # Acquisition windowing: per-leaf grade based on grads with acq
    # year in window. acq_draft windows on draft year; acq_ifa windows
    # on signed year. We aggregate WAR/yr means for grads filtered by
    # `acq_year_window`.
    _ACQ_GRAD_LISTS = {
        "acq_draft": "_draft_pool_grads",   # has draft_year + career_war
        "acq_ifa":   "_ifa_grads",          # has signed_year + career_war
    }
    for win_label, win_years in _WINDOWS.items():
        for leaf_key, grad_list_key in _ACQ_GRAD_LISTS.items():
            org_vals = []
            for entry in org_summary:
                grad_list = entry.get(grad_list_key + "_raw") or []
                vals_w = []
                for g in grad_list:
                    yr = g.get("draft_year") or g.get("signed_year")
                    cw = g.get("career_war")
                    if yr is None or cw is None:
                        continue
                    if _now_yr - int(yr) <= win_years:
                        vals_w.append((float(cw), g.get("w", 1.0)))
                # Use career WAR mean as the in-window signal (WAR/yr
                # not stored on _draft_pool_grads / _ifa_grads).
                # VAL_4: share-weighted mean, gated on graduate-equivalents
                _wsum = sum(w for _, w in vals_w)
                org_mean = (sum(v * w for v, w in vals_w) / _wsum) if _wsum >= 3 else None
                org_vals.append(org_mean)
            present = [v for v in org_vals if v is not None]
            n_p = len(present)
            if n_p >= 3:
                mu = sum(present) / n_p
                var = sum((v - mu) ** 2 for v in present) / n_p
                sd = var ** 0.5
            else:
                mu, sd = 0.0, 0.0
            for i, v in enumerate(org_vals):
                entry = org_summary[i]
                gbw = entry.setdefault("grades_by_window", {})
                wmap = gbw.setdefault(win_label, {})
                if v is None or sd < 1e-9:
                    wmap[leaf_key] = "C"
                else:
                    z = (v - mu) / sd
                    wmap[leaf_key] = _z_to_letter(z)
                # Stamp the windowed value on the tree node so the per-window
                # COMPOSITE bake can re-score the Acquisition branch per window.
                node = (entry.get("tree") or {}).get(leaf_key) or {}
                node.setdefault("career_war_by_window", {})[win_label] = v
    # Pop the scratch fields so they don't bloat the exported JSON.
    for entry in org_summary:
        entry.pop("_top_grads_raw", None)
        entry.pop("_draft_pool_grads_raw", None)
        entry.pop("_ifa_grads_raw", None)

    # ── Per-window COMPOSITE farm_score + overall letter ──────────────────
    # The user-selectable trailing window drives the WHOLE grade, re-scoring
    # EVERY legitimately-windowed branch at the selected window:
    #   • Development  — org DvM+[W] (weight 2) blended with per-window tool DvM+[W]
    #                    (weight 1), matching the dev-leaf spec.
    #   • MLB-Production — the windowed graduate-WAR/yr leaves (hitter+pitcher)
    #                    re-z-scored at W; the roll-up leaves (boom/bust/top/
    #                    conviction/grad-pace/HOF) stay at their canonical scores.
    #   • Acquisition  — the windowed draft/IFA graduate-WAR leaves re-z-scored at W;
    #                    trade/waiver leaves stay canonical.
    # Only FINANCIAL is held fixed: it's aggregate CURRENT surplus (a snapshot, not
    # a trailing window), so it's window-invariant by construction. Because Financial
    # is 65% of the composite the rank moves modestly across windows — that's honest:
    # the grade is value-anchored, and the window re-grades the ~35% development /
    # production / acquisition trajectory mass. Frontend reads farm_score_by_window
    # [W] / letter_by_window[W]; canonical farm_score stays on FARM_PRINCIPAL_WINDOW.
    _n_orgs = len(org_summary)
    _dev_health_100 = leaf_100.get("dev_health_mgmt")      or [None] * _n_orgs
    _dev_statc_100  = leaf_100.get("dev_statcast_quality")  or [None] * _n_orgs
    _PROD_STATIC = ["mlb_production_boom_pct", "mlb_production_bust_pct",
                    "mlb_production_top_grads", "mlb_production_conviction",
                    "mlb_production_grad_pace", "mlb_production_hof_track"]
    _ACQ_STATIC  = ["tx_trades", "tx_waivers"]
    _w_acq  = FARM_TREE_WEIGHT_ACQUISITION_STRATEGY
    _w_dev  = FARM_TREE_WEIGHT_DEVELOPMENT
    _w_fin  = FARM_TREE_WEIGHT_FINANCIAL
    _w_prod = FARM_TREE_WEIGHT_MLB_PRODUCTION

    def _node_win(leaf_key, by_window_key, win):
        return _zscore_to_100(
            [(((e.get("tree") or {}).get(leaf_key) or {}).get(by_window_key) or {}).get(win)
             for e in org_summary],
            higher_is_better=True)

    def _mean_present(vals):
        present = [v for v in vals if v is not None]
        return (sum(present) / len(present)) if present else None

    for entry in org_summary:
        entry["farm_score_by_window"] = {}
        entry["letter_by_window"] = {}
        entry["canopy_by_window"] = {}

    def _branch_cell(score, rank, present):
        """{score, letter, rank} for one branch at one window (None rank -> neutral C)."""
        return {"score": score,
                "letter": _letter_grade(rank, present) if rank is not None else _SPARSE_FALLBACK,
                "rank": rank}

    # Financial is aggregate CURRENT surplus (a snapshot), so it is window-invariant: the
    # same score/letter/rank repeats at every window (flagged so the UI can note it).
    _fin_scores = [e.get("financial_score") for e in org_summary]
    _fin_ranks = _rank_list(_fin_scores)
    _fin_present = sum(1 for x in _fin_ranks if x is not None)

    for win in FARM_TRAJECTORY_WINDOWS:
        # Development leaves at W.
        z_org = _zscore_to_100([(e.get("dvm_plus") or {}).get(win) for e in org_summary],
                               higher_is_better=True)
        dev_leaf_w = {}
        for leaf_key in ("dev_hitter", "dev_pitcher"):
            z_tool = _node_win(leaf_key, "dvm_plus_by_window", win)
            vals = []
            for i in range(_n_orgs):
                num = den = 0.0
                if z_org[i] is not None:  num += z_org[i] * 2.0; den += 2.0
                if z_tool[i] is not None: num += z_tool[i] * 1.0; den += 1.0
                vals.append(round(num / den, 1) if den > 0 else None)
            dev_leaf_w[leaf_key] = vals
        # Production windowed leaves (graduate WAR/yr) + Acquisition windowed leaves.
        z_prod_hit = _node_win("mlb_hitter_production",  "war_per_yr_by_window", win)
        z_prod_pit = _node_win("mlb_pitcher_production", "war_per_yr_by_window", win)
        z_acq_drf  = _node_win("acq_draft", "career_war_by_window", win)
        z_acq_ifa  = _node_win("acq_ifa",   "career_war_by_window", win)
        dev_parents, prod_parents, acq_parents, farm_scores_w = [], [], [], []
        for i, entry in enumerate(org_summary):
            dev_parent = _mean_present([dev_leaf_w["dev_hitter"][i], dev_leaf_w["dev_pitcher"][i],
                                        _dev_health_100[i], _dev_statc_100[i]])
            prod_parent = _mean_present([z_prod_hit[i], z_prod_pit[i]]
                                        + [(leaf_100.get(k) or [None] * _n_orgs)[i] for k in _PROD_STATIC])
            acq_parent = _mean_present([z_acq_drf[i], z_acq_ifa[i]]
                                       + [(leaf_100.get(k) or [None] * _n_orgs)[i] for k in _ACQ_STATIC])
            comp = (_w_acq  * (acq_parent  if acq_parent  is not None else 100.0)
                    + _w_dev  * (dev_parent  if dev_parent  is not None else 100.0)
                    + _w_fin  * (entry.get("financial_score") if entry.get("financial_score") is not None else 100.0)
                    + _w_prod * (prod_parent if prod_parent is not None else 100.0))
            # Same 1.20 as the canonical farm_score, and the same non-compounding
            # note applies: every leaf reaching `comp` came through
            # _zscore_to_100, so the upstream 1.35 per-tool stretch is already
            # erased and cannot multiply with this factor. See _stretch_composite.
            fs = _stretch_composite(round(comp, 1), factor=1.20)
            entry["farm_score_by_window"][win] = fs
            farm_scores_w.append(fs)
            dev_parents.append(round(dev_parent, 1) if dev_parent is not None else None)
            prod_parents.append(round(prod_parent, 1) if prod_parent is not None else None)
            acq_parents.append(round(acq_parent, 1) if acq_parent is not None else None)
        # Per-window branch + overall letters/ranks, stamped onto canopy_by_window so the
        # frontend canopy subgrades re-grade with the selected window. (Leaf grades are
        # unchanged; only the branch/composite grades are windowed here.)
        _dev_ranks, _prod_ranks, _acq_ranks = _rank_list(dev_parents), _rank_list(prod_parents), _rank_list(acq_parents)
        _dp = sum(1 for x in _dev_ranks if x is not None)
        _pp = sum(1 for x in _prod_ranks if x is not None)
        _ap = sum(1 for x in _acq_ranks if x is not None)
        ranks_w = _rank_descending(farm_scores_w)
        for i, entry in enumerate(org_summary):
            entry["letter_by_window"][win] = _letter_grade(ranks_w[i], _n_orgs)
            entry["canopy_by_window"][win] = {
                "development":          _branch_cell(dev_parents[i],  _dev_ranks[i],  _dp),
                "mlb_production":       _branch_cell(prod_parents[i], _prod_ranks[i], _pp),
                "acquisition_strategy": _branch_cell(acq_parents[i],  _acq_ranks[i],  _ap),
                "financial":            {**_branch_cell(_fin_scores[i], _fin_ranks[i], _fin_present), "window_invariant": True},
                "overall":              {"score": farm_scores_w[i], "letter": entry["letter_by_window"][win], "rank": ranks_w[i]},
            }

    # PRINCIPAL window IS the canonical slice: override farm_score_by_window[PW],
    # letter_by_window[PW], and canopy_by_window[PW] with the canonical composite/branch
    # scores so farm_score_by_window[PW] == farm_score EXACTLY and farm_rank (assigned off
    # farm_score) matches the board's default-window ranking. The neutralizing windowed
    # engine no longer overrides the canonical grade at the default view. Other windows keep
    # the windowed trajectory view.
    _PW = FARM_PRINCIPAL_WINDOW
    for entry in org_summary:
        g = entry.get("grades") or {}
        cr = entry.get("component_ranks") or {}
        entry["farm_score_by_window"][_PW] = entry["farm_score"]
        entry["letter_by_window"][_PW] = g.get("overall", _SPARSE_FALLBACK)
        entry["canopy_by_window"][_PW] = {
            "development":          {"score": entry.get("development_score"),          "letter": g.get("development", _SPARSE_FALLBACK),          "rank": cr.get("development")},
            "mlb_production":       {"score": entry.get("mlb_production_score"),       "letter": g.get("mlb_production", _SPARSE_FALLBACK),       "rank": cr.get("mlb_production")},
            "acquisition_strategy": {"score": entry.get("acquisition_strategy_score"), "letter": g.get("acquisition_strategy", _SPARSE_FALLBACK), "rank": cr.get("acquisition_strategy")},
            "financial":            {"score": entry.get("financial_score"),            "letter": g.get("financial", _SPARSE_FALLBACK),            "rank": cr.get("financial"), "window_invariant": True},
            "overall":              {"score": entry["farm_score"],                     "letter": g.get("overall", _SPARSE_FALLBACK),             "rank": cr.get("overall")},
        }
    # ────────────────────────────────────────────────────────────────────────

    # ── farm_rank follows the CANONICAL farm_score (owner) ────────────────
    # Previously farm_rank was RE-RANKED here onto farm_score_by_window["7y"], a separately
    # computed windowed engine that re-z-scored the branches and neutralized real branch
    # advantages -- so a lower-farm_score org (e.g. COL 90.0) out-ranked a higher one (NYY
    # 96.9), contradicting grades.overall / component_ranks / farm_tiebreaker. That re-rank
    # is REMOVED: farm_rank is the rank of the canonical farm_score (assigned above at the
    # composite pass), and the principal (7y) window is now defined AS the canonical slice
    # (farm_score_by_window["7y"] == farm_score), so farmWindowRank("7y"), the board #N, the
    # movement chip (derived off the canonical rank above), the snapshot, grades.overall, and
    # component_ranks all agree. Better dev/production/acquisition subgrades now rank up.

    _phase_done("farm_grade")
    # ── Per-org draft spending (computed from our acquisitions table) ──
    # The acquisitions table records `bonus_usd` for every drafted player
    # we know about — sum by org × year to produce a comparison set for
    # the IFA spending totals fed in by Spotrac. Pulls from EVERY drafted
    # player on file (graduates included), not just current actives, so
    # the multi-year history reflects each org's full cycle spending.
    draft_spending_by_org: dict[str, dict[int, dict]] = {}
    for key, rec in acquisitions.items():
        if (rec or {}).get("method") != "draft":
            continue
        bonus = rec.get("bonus_usd")
        year = rec.get("year")
        if bonus is None or year is None:
            continue
        # Resolve the player's CURRENT org. For drafted prospects the
        # acquiring team is on the rec, but trades may have moved them
        # elsewhere — we credit the *acquiring* org rather than the
        # current one because that's the spending-decision attribution
        # that matches what Spotrac's per-year IFA tracker does.
        team_name = rec.get("team_name")
        from trades import canonical_org
        org_code = canonical_org(team_name) if team_name else None
        if not org_code:
            continue
        bucket = draft_spending_by_org.setdefault(org_code, {}).setdefault(year, {
            "total_usd": 0, "signings": 0, "top_bonus": 0, "top_player": None,
        })
        bucket["total_usd"] += bonus
        bucket["signings"]  += 1
        if bonus > bucket["top_bonus"]:
            bucket["top_bonus"]  = bonus
            # Look up the player name — acquisitions records don't carry
            # it directly, but the player_key works well enough as a
            # display fallback (the farm page can resolve to full name
            # via the active/grad maps if needed).
            bucket["top_player"] = key

    # Attach IFA + draft spending to each org_summary entry so the farm
    # detail page can render a side-by-side comparison without joining
    # back to top-level payload structures.
    for entry in org_summary:
        org_code = entry["org"]
        entry["ifa_spending"]   = ifa_spending_by_org.get(org_code, {})
        entry["draft_spending"] = draft_spending_by_org.get(org_code, {})

    _phase_done("draft_spend")
    active_payload = [_serialize(p) for p in actives]
    inactive_payload = [_serialize(p) for p in inactives]
    graduate_payload = [_serialize(p) for p in grads]
    # VAL_4: who developed each graduate (club shares, signing club, tenures).
    # `org` stays the club he is with now; the farm leaves, the Club Ledger and
    # the PROSPX farm page credit the clubs in dev_credit.shares instead.
    if _dev_attr is not None:
        for _gpl in graduate_payload:
            _pa_g = _dev_attr.get(_gpl.get("player_key"))
            if _pa_g is not None and _pa_g.shares:
                _gpl["dev_credit"] = _pa_g.as_payload()
    _phase_done("serialise")
    # v38 — Item-6: stamp the per-prospect $DvM+ (computed in the league pre-pass
    # above) onto each active payload so the farm financial detail can surface it
    # alongside the prospect's surplus value.
    for _pl in active_payload:
        _pl["dollar_dvm_plus"] = _dollar_dvm_by_key.get(_pl.get("player_key"))
    # ── CONSENSUS-SIDE live form / list-movement signal — NOT an eFV output ──────
    # `consensus_live_score` = CONSENSUS FV (fv_close_raw) + live_signal.delta. Both
    # legs are consensus-side: the delta is dominated by EXTERNAL SCOUTING-LIST
    # MOVEMENT (top100_rank / joined / dropped / movement events, capped at +/-7),
    # with recent-form terms (level-adjusted production, contact quality, zone
    # discipline, injury drag) riding along. Franklin Arias's +6.05 delta was 5.68
    # from a single "BA Top 100 #4" driver.
    #
    # It is therefore a CONSENSUS composite, not a model grade, and it MUST NOT touch
    # the board ordering: eFV already blends consensus at lambda ~0.85, so adding this
    # on top would double-count the same scouting lists. Renamed from live_score /
    # live_overall_rank / live_rank_delta on 2026-07-25 because the bare "live_" prefix
    # read like an eFV output and was one of the three competing orderings.
    # `consensus_live_rank` is a SIDECAR ranking of this signal only, published for
    # transparency; `overall_rank` above is the board. The UI pill that once rendered
    # it was retired when eFV became the primary ranking signal.
    _live_ranked = []
    for _pl in active_payload:
        _base = _safe_float(_pl.get("fv_close_raw"))
        if _base is None:
            _base = _safe_float(_pl.get("fv_close"))
        _delta = _safe_float(((_pl.get("live_signal") or {}).get("delta")))
        if _base is None:
            continue
        _pl["consensus_live_score"] = round(_base + (_delta or 0.0), 2)
        _live_ranked.append(_pl)
    _live_ranked.sort(key=lambda _pl: (
        -(_safe_float(_pl.get("consensus_live_score")) or -999),
        -(_safe_float(_pl.get("fv_close_raw")) or -999),
        _pl.get("player_name") or "",
    ))
    for _idx, _pl in enumerate(_live_ranked, start=1):
        _pl["consensus_live_rank"] = _idx
        if _pl.get("overall_rank") is not None:
            # Board rank minus consensus-live rank. A gap is INFORMATION (the lists are
            # moving on a player the model has not re-graded), never a correction to apply.
            _pl["consensus_live_rank_delta"] = int(_pl["overall_rank"]) - _idx
    graduate_payload.sort(key=lambda p: p.get("debut_date") or "", reverse=True)
    # Stamp the precomputed Statcast+ onto each payload so downstream
    # consumers (UI badge, breakout gate, farm-grade rollup) can pull
    # one field instead of re-deriving from the raw maps.
    for _pl in active_payload + graduate_payload:
        _pl["statcast_plus"] = _sc_plus_map.get(_pl["player_key"])

    # X+ tool composites need cohort mean/stdev. Use the union of all
    # serialized prospects so a single norm anchors actives / inactives /
    # grads consistently — a graduate's last tool grade still reads
    # "+12 vs cohort mean" the same way it would have the day before
    # he graduated. Single call ensures every payload's composite_*_plus
    # references the same baseline.
    _attach_tool_plus_indices(active_payload + inactive_payload + graduate_payload)

    # v14 — Breakout indicator pass. Walks active prospects only and
    # stamps `breakout_flag` based on tool / FV velocity over the last
    # 6 months (or last 4 source updates, whichever spans more time) +
    # a performance gate (RPS+ for hitters, stf_plus_periph / fip_minus
    # for pitchers). Rare-but-possible — expects ~10-40 prospects to
    # qualify league-wide. v29: Statcast+ also passes the perf gate now
    # (threshold at _BREAKOUT_STATCAST_PLUS_GATE, see _compute_breakout_flag).
    _attach_breakout_flags(active_payload)

    # v30.7 — Surface the breakout flag as a driver chip on the
    # spotlights row. Stock was computed before breakout_flag existed
    # on the payload, so we splice the driver in here once the flag is
    # stamped. Only fires for risers / rebounders (fallers are already
    # gated out of the breakout flag itself by the mutual-exclusion
    # check at the top of _compute_breakout_flag).
    for _pl in active_payload:
        if not _pl.get("breakout_flag"):
            continue
        _stk = _pl.get("stock") or {}
        if _stk.get("bucket") not in ("riser", "rebound"):
            continue
        _meta = _pl.get("breakout_meta") or {}
        _reason = _meta.get("reason")
        _gate = _meta.get("perf_gate")
        # Build a one-line tooltip explaining WHY breakout fired —
        # mirrors the breakdown the user gets if they hover the ★
        # indicator on the FV badge.
        _why_bits = []
        if _reason == "fv" and _meta.get("fv_upgrade") is not None:
            _why_bits.append(f"FV +{_meta['fv_upgrade']:.0f} over breakout window")
        elif _reason == "tools" and _meta.get("tool_velocity") is not None:
            _why_bits.append(f"tool composite +{_meta['tool_velocity']:.1f}")
        elif _reason == "upside":
            _src = ", ".join(_meta.get("upside_sources") or []) or "scout source"
            _why_bits.append(f"+ upside added by {_src}")
        elif _reason == "stats":
            _why_bits.append("elite stat-only path")
        if _gate:
            _why_bits.append(f"perf gate: {_gate}")
        _tip = "; ".join(_why_bits) if _why_bits else "Flagged as a breakout candidate"
        _drv = {
            "label": "★ breakout",
            "valence": "breakout",
            "tooltip": _tip,
        }
        # Front-load the chip so it's the lead driver on the card
        # (matches how the ★ indicator already steals visual focus on
        # the FV badge — same signal, same priority in the driver row).
        _drivers_list = list(_stk.get("drivers") or [])
        # Skip if somehow already present (idempotency on re-export).
        if not any(
            (isinstance(_d, dict) and _d.get("label") == _drv["label"])
            for _d in _drivers_list
        ):
            _drivers_list.insert(0, _drv)
            # MAX_DRIVERS_PER_CARD = 8 in spotlights.py — hardcoded
            # here rather than importing to keep storage.py's
            # downstream-only role clean (no circular nip).
            _stk["drivers"] = _drivers_list[:8]
            _pl["stock"] = _stk

    # v29 — Fill the per-org breakout_count now that flags are stamped.
    # The per-prospect org loop ran before breakout was computed (the
    # flag uses fields populated by _attach_tool_plus_indices), so the
    # count gets backfilled here. Same for the breakout-indicator count
    # used by the new statcast_quality leaf. Builds an org→count map in
    # one pass then writes into each org_summary entry.
    _breakout_by_org: dict[str, int] = {}
    _org_by_key = {p.player_key: _active_display_org(p) for p in actives}
    for _pl in active_payload:
        if not _pl.get("breakout_flag"):
            continue
        _org_code = _org_by_key.get(_pl.get("player_key"))
        if not _org_code:
            continue
        _breakout_by_org[_org_code] = _breakout_by_org.get(_org_code, 0) + 1
    for _entry in org_summary:
        _scq = _entry.get("statcast_quality")
        if _scq is not None:
            _scq["breakout_count"] = _breakout_by_org.get(_entry.get("org"), 0)

    # Cleanup: `_active_keys` was retained on org_summary entries for
    # potential post-serialization joins (now unused after Tool Quality
    # moved into the actives loop). Drop the field so the JSON doesn't
    # carry an internal-only key.
    for entry in org_summary:
        entry.pop("_active_keys", None)

    from prospect_savant import attach_prospect_savant
    savant_matched = attach_prospect_savant(
        active_payload + inactive_payload + graduate_payload,
        Path(__file__).parent,
    )

    from spotlights import build_spotlights
    spotlight_payload = build_spotlights(active_payload, graduate_payload)

    # Model-audit WS-0c — log editorial flags AT EMIT TIME so 30/60-day
    # forward hit rates can be scored once cohorts mature (Phase 5).
    # Numeric FV comes from the player payload (the entry carries a label).
    try:
        _fv_of = {p.get("player_key"): (p.get("points") or [{}])[-1].get("consensus_fv_raw")
                  for p in active_payload}
        _today = date.today().isoformat()
        _flags = [{"player_key": e.get("player_key"), "flag_type": e.get("bucket"),
                   "score": e.get("score"), "fv": _fv_of.get(e.get("player_key")),
                   "level": e.get("level"), "age": e.get("age")}
                  for key in ("risers", "rebounders", "fallers")
                  for e in (spotlight_payload.get(key) or [])]
        _n_flags = insert_editorial_flags(_today, _flags)
        log.info("editorial flags: logged %d new (of %d emitted)", _n_flags, len(_flags))
    except Exception:                                      # noqa: BLE001 — additive, never aborts
        log.exception("editorial flag logging failed — continuing")

    # Split the export into a boot-critical file plus three lazy-loaded
    # sidecars so a first-paint download doesn't drag along ~40MB of
    # graduate / inactive / affiliate-roster data that the user typically
    # doesn't need until they navigate to those tabs.
    #
    #   timeseries.json   — meta + active players + spotlights + org
    #                       summaries + level/trajectory norms (boot path)
    #   debuts.json       — graduate-player payloads (the "debuts" slice)
    #   inactive.json     — inactive-player payloads
    #   rosters_by_org.json — per-org affiliate rosters (farm-detail only)
    #
    # The boot file carries `_slices` so the frontend knows which sidecars
    # exist and can fetch them on first tab-switch. Counts are duplicated
    # into the boot meta so empty-state copy can render before the slice
    # arrives.
    # NOTE: the boot JSON intentionally omits `graduates`, `inactive`, and
    # `rosters_by_org` — those slices live in sidecar files and the frontend
    # fetches them on demand. Tests that want a single dict can call
    # `load_export_unified(out_path)` to reassemble them.
    _phase_done("live_form")
    # ── Scout-reports extraction (Tier 2 perf — slice splitting) ──
    # The FanGraphs scout report prose lives inside per_source.fangraphs.
    # tools._extras.report on most snapshots. Across all players it's
    # ~11MB of repeated prose (same text often carries across cycles for
    # a single prospect). Extract the LATEST report per source per
    # player into a separate sidecar so the boot file shrinks ~17%.
    # Strip the `report` string from every per_source._extras dict in
    # the boot payload to dedupe.
    # Multi-cycle scout-reports sidecar.
    # Shape: scout_reports_sidecar[player_key][source] = [
    #   {date, label, text, hash}, ...   # ordered NEWEST → oldest
    # ]
    # Dedup by SHA1 of stripped text so identical writeups across
    # consecutive cycles only appear once (very common for off-cycle
    # months where FG reposts the same report under a new label).
    import hashlib
    from report_excerpt import excerpt_fields as _report_excerpt_fields
    scout_reports_sidecar: dict[str, dict[str, list[dict]]] = {}
    def _harvest_and_strip_reports(player_payload):
        pkey = player_payload.get("player_key")
        # Walk in date order, collecting unique report texts per source.
        by_src_seen_hashes: dict[str, set[str]] = {}
        by_src_entries: dict[str, list[dict]] = {}
        # Per-source external player ids, used to build "View on <source>" links
        # on the writeups + source-comparison panels. Currently the FanGraphs
        # player id (prefer the alphanumeric string form so minor-league "sa..."
        # ids survive). Date-ordered walk -> latest non-empty id wins.
        src_ids: dict[str, str] = {}
        for pt in (player_payload.get("points") or []):
            for src, info in (pt.get("per_source") or {}).items():
                # Same-day extra rows (a second list on one date, e.g. a
                # Pipeline team list beside its Top 100) rode into the boot,
                # debuts, inactive, player_detail and debuts_full files with
                # their full report text (census X07-02 follow-up,
                # 2026-10-01). Their report is stripped and NOT harvested: the
                # sidecar never read them, and 11 of them sit on common-name
                # keys (kevin_smith, jose_ramirez, ...) where a second human's
                # writeup would surface on the card as a new cycle.
                for _xr in ((info or {}).get("extras") or []):
                    _xt = _xr.get("tools") if isinstance(_xr, dict) else None
                    _xex = _xt.get("_extras") if isinstance(_xt, dict) else None
                    if isinstance(_xex, dict) and _xex.get("report"):
                        _xex["report"] = None
                tools = (info or {}).get("tools") or {}
                ex = tools.get("_extras") or {}
                if src == "fangraphs":
                    fgid = ex.get("fg_player_id_str") or ex.get("fg_player_id")
                    if fgid is not None and str(fgid).strip():
                        src_ids["fangraphs"] = str(fgid).strip()
                rpt = ex.get("report")
                if rpt:
                    h = hashlib.sha1(rpt.strip().encode("utf-8")).hexdigest()[:12]
                    seen = by_src_seen_hashes.setdefault(src, set())
                    if h not in seen:
                        seen.add(h)
                        # Label + date come from the PER-SOURCE entry, not the
                        # point. The point's interval_label is just one source's
                        # label (whichever sorted first that day), so using it
                        # here mislabeled every other source's writeup on a
                        # multi-source day - e.g. an MLB Pipeline report stamped
                        # "TJ Pre-Season 2026" because TJStats shared the date.
                        # The text is held whole until the walk ends so the
                        # excerpt and link are cut once, with the final ids.
                        by_src_entries.setdefault(src, []).append({
                            "date": (info or {}).get("snapshot_date") or pt.get("snapshot_date"),
                            "label": (info or {}).get("interval_label") or pt.get("interval_label"),
                            "text": rpt,
                            "hash": h,
                        })
                    # Strip the inline report so it doesn't bloat boot.
                    ex["report"] = None
        # Owner answer 2026-09-25 (census X07-02 option b): the served sidecar
        # carries an excerpt of each report plus its source link, never the
        # full text (report_excerpt.py). The hash stays the full text's, so
        # dedup and the cycle identity are unchanged.
        _mlbam = player_payload.get("mlbam_id")
        for src, entries in by_src_entries.items():
            for e in entries:
                e.update(_report_excerpt_fields(
                    e["text"], src, label=e.get("label"),
                    fg_id=src_ids.get("fangraphs") if src == "fangraphs" else None,
                    mlbam_id=_mlbam))
        # Reverse each list so newest is first (the walk was oldest-first).
        if by_src_entries or src_ids:
            for src in by_src_entries:
                by_src_entries[src].reverse()
            # _ids rides as a reserved sub-key alongside the per-source report
            # lists; the frontend reads sidecar._ids and only ever looks up known
            # source keys, so this never collides with a source's entry list.
            if src_ids:
                by_src_entries["_ids"] = src_ids
            scout_reports_sidecar[pkey] = by_src_entries
    for p in active_payload:
        _harvest_and_strip_reports(p)
    for p in graduate_payload:
        _harvest_and_strip_reports(p)
    for p in inactive_payload:
        _harvest_and_strip_reports(p)

    # v31.12 — pitch_plot sidecar harvest. The per-player pitch_plot
    # blob (raw per-pitch coordinates rendered by the player-detail
    # pitch-movement chart) is the single biggest contributor to the
    # boot payload (~36 MB combined: 17.8 MB at the top level + 18.8
    # MB nested inside level_splits[].pitch_plot). It's also used in
    # exactly one place — `makePitchMovementPlot` on the player detail
    # page — so it's a textbook lazy-load candidate. Extract into a
    # sidecar keyed by player_key; the boot dict carries only
    # `statcast_metrics` minus the pitch_plot fields.
    pitch_plots_sidecar: dict[str, dict] = {}
    def _harvest_and_strip_pitch_plots(player_payload):
        pkey = player_payload.get("player_key")
        sc = player_payload.get("statcast_metrics") or {}
        if not sc:
            return
        captured: dict = {}
        top_plot = sc.get("pitch_plot")
        if top_plot:
            captured["top"] = slim_pitch_plot_view(top_plot)
            sc["pitch_plot"] = {}
        ls = sc.get("level_splits") or []
        if ls:
            level_plots = {}
            for row in ls:
                if not isinstance(row, dict):
                    continue
                rp = row.get("pitch_plot")
                if rp:
                    lvl = row.get("level") or "_"
                    level_plots[lvl] = slim_pitch_plot_view(rp)
                    row["pitch_plot"] = {}
            if level_plots:
                captured["level_splits"] = level_plots
        if captured and pkey:
            # See slim_pitch_plot_view / dedupe_pitch_plot_entry above for
            # the published contract; readers go through
            # resolve_pitch_plot_entry (Python) or _resolvePitchPlot (JS).
            pitch_plots_sidecar[pkey] = dedupe_pitch_plot_entry(captured)
    for p in active_payload:
        _harvest_and_strip_pitch_plots(p)
    for p in graduate_payload:
        _harvest_and_strip_pitch_plots(p)
    for p in inactive_payload:
        _harvest_and_strip_pitch_plots(p)

    # v33 — player_detail per-player sidecar (Open Beta payload diet). After
    # the pitch-plot split the boot file's residual weight was (a) raw
    # batted-ball coordinates (contact_quality.hit_locations + rolling_xwoba,
    # duplicated per level split) feeding the spray chart + rolling-xwOBA
    # sparkline, (b) per-game logs (recent_games / standout_games), and
    # (c) HISTORICAL per_source tool grades + extras on old points. All are
    # card-only consumers, so they move to data/player_detail/{key}.json and
    # the card lazy-merges them back in (mirrors the v32 pitch_plots
    # pattern). What stays in boot, by consumer contract:
    #   • per-source SCALARS (fv_published / fv_plus / rank / status …) on
    #     EVERY point — the source-divergence chart + point tooltips read
    #     them across the whole history.
    #   • the full observation (tools + extras) on each source's NEWEST
    #     point, plus the newest point per source that carries
    #     tools._extras — newest→oldest walkers (_getFgExtras,
    #     computeFgFlags, _getPhysicalProfile) find identical data.
    #   • level_splits' scalar metrics — card percentile cohorts walk every
    #     player's splits, so those can never leave boot.
    # p90_ev is precomputed before hit_locations leave so the cohort
    # fallback (_p90EvOf) never needs the raw coordinates.
    player_detail_sidecar: dict[str, dict] = {}

    def _p90_from_locations(cq: dict) -> None:
        if not isinstance(cq, dict) or cq.get("p90_ev") is not None:
            return
        evs = []
        for loc in cq.get("hit_locations") or []:
            try:
                v = float(loc.get("launch_speed"))
            except (TypeError, ValueError, AttributeError):
                continue
            if v == v:  # not NaN
                evs.append(v)
        if evs:
            evs.sort()
            idx = min(len(evs) - 1, max(0, round((len(evs) - 1) * 0.90)))
            cq["p90_ev"] = round(evs[idx], 1)

    def _strip_statcast_heavy(holder: dict) -> dict:
        """Move hit_locations / rolling_xwoba / recent_games / standout_games
        out of a statcast block (top level or one level-split row). Returns
        the moved fields ({} when the block had none)."""
        moved: dict = {}
        cq = holder.get("contact_quality")
        if isinstance(cq, dict):
            _p90_from_locations(cq)
            cq_moved = {}
            for f in ("hit_locations", "rolling_xwoba"):
                if cq.get(f):
                    cq_moved[f] = cq[f]
                    cq[f] = []
            if cq_moved:
                moved["contact_quality"] = cq_moved
        for f in ("recent_games", "standout_games"):
            if holder.get(f):
                moved[f] = holder[f]
                holder[f] = []
        return moved

    def _harvest_player_detail(player_payload: dict) -> None:
        pkey = player_payload.get("player_key")
        if not pkey:
            return
        detail: dict = {}
        sc = player_payload.get("statcast_metrics") or {}
        if sc:
            top = _strip_statcast_heavy(sc)
            levels: dict = {}
            for row in sc.get("level_splits") or []:
                if not isinstance(row, dict):
                    continue
                lvl_moved = _strip_statcast_heavy(row)
                if lvl_moved:
                    levels[row.get("level") or "_"] = lvl_moved
            if top or levels:
                detail["statcast"] = {"top": top, "level_splits": levels}
        pts = player_payload.get("points") or []
        newest_any: set[str] = set()
        newest_extras: set[str] = set()
        moved_ps: dict[str, dict] = {}
        for pt in reversed(pts):              # newest → oldest
            for src, obs in (pt.get("per_source") or {}).items():
                if not isinstance(obs, dict):
                    continue
                tools = obs.get("tools") or {}
                has_extras = bool(isinstance(tools, dict) and tools.get("_extras"))
                keep = src not in newest_any or (has_extras and src not in newest_extras)
                newest_any.add(src)
                if has_extras:
                    newest_extras.add(src)
                if keep:
                    continue
                moved = {}
                for f in ("tools", "extras"):
                    if obs.get(f):
                        moved[f] = obs.pop(f)
                    elif f in obs:
                        del obs[f]          # drop the null stub outright
                # v46 payload-slim — historical per-source SCALARS. The only
                # cross-history readers of these four are card panels (the
                # per-source FV history table's Update/date columns), which
                # lazy-merge this shard back in. fv_published / fv_plus /
                # rank / dropped_off STAY inline on every point: the list
                # sparkline's upside dots, the movement mirror, and the
                # source_backtest / efv_dataset pipelines read them across
                # the whole history from the exported files.
                scalars = {}
                for f in ("interval_label", "snapshot_date", "status", "fv_adjusted"):
                    v = obs.pop(f, None)
                    if v is not None:
                        scalars[f] = v
                for f in ("fv_plus", "dropped_off"):
                    if f in obs and not obs[f]:
                        del obs[f]          # falsy flags read identically when absent
                if scalars:
                    moved["scalars"] = scalars
                if moved:
                    pt_key = f"{pt.get('snapshot_date')}|{pt.get('interval_label')}"
                    moved_ps.setdefault(pt_key, {})[src] = moved
        if moved_ps:
            detail["points_per_source"] = moved_ps
        # Pitch rates per career row ride this shard, not the boot rows: on the
        # 2026-10-09 export they cost 345 KB of boot gzip against the lane's
        # 150 KB budget (pitch_metrics.md STOP S15). The card merges them back
        # by (season, level). Absent while SERVE_PITCH_RATES is False.
        _pr_rows = career_pitch_rate_shard(player_payload.get("career_stats"),
                                           player_payload.get("mlbam_id"),
                                           _pitch_rate_lookup)
        if _pr_rows:
            detail["pitch_rates"] = {"career": _pr_rows}
        if detail:
            player_detail_sidecar[pkey] = detail

    # STANDOUT GAMES (census M02-06, 2026-09-25). The harvest below moves every
    # statcast standout_games list into the per-player shards, which left the
    # Standout Performances ribbon (it reads the boot rows) with 0 of 4,679
    # players carrying a game, so it always fell back to season aggregates.
    # Keep one compact top-level list of the ACTIVE board's standout games first.
    standouts: list[dict] = []
    for p in active_payload:
        _sg = (p.get("statcast_metrics") or {}).get("standout_games") or []
        for g in _sg:
            if not isinstance(g, dict) or not g.get("date") or not g.get("line"):
                continue
            standouts.append({
                "player_key": p.get("player_key"),
                "date": g.get("date"), "level": g.get("level"),
                "opponent": g.get("opponent"), "is_home": g.get("is_home"),
                "line": g.get("line"), "score": g.get("score"),
                "is_pitcher": g.get("is_pitcher"),
            })
    standouts.sort(key=lambda r: (r["date"] or "", r["player_key"] or ""), reverse=True)

    for p in active_payload:
        _harvest_player_detail(p)
    for p in graduate_payload:
        _harvest_player_detail(p)
    for p in inactive_payload:
        _harvest_player_detail(p)

    # v46 payload-slim — debuts_lite sidecar. The Graduates tab, the context
    # rail, and the farm/trade/news list surfaces read only a slim slice of
    # each graduate; the full monolith (points history, statcast level
    # splits, tools history) is fetched only where the whole record matters
    # (graduate card open, Time Machine, debuted chart mode). The field set
    # is derived from the prospx list-path readers; card-only blocks stay in
    # debuts.json, which the card path always loads before rendering.
    # Built AFTER the harvests so slimmed sub-blocks mirror the shipped
    # shape. Sub-objects are shared (not copied) wherever they ship whole.
    _LITE_SCALARS = (
        "player_key", "player_name", "position", "org", "age", "status",
        "debut_date", "current_level", "mlbam_id", "fv_close", "fv_close_raw",
        "fv_label", "fv_close_plus", "fv_total_instances", "overall_rank",
        "prev_overall_rank", "org_rank", "org_rank_total", "statcast_plus",
        "dollar_dvm_plus", "breakout_flag",
    )
    _LITE_WHOLE = (
        "statline", "sabermetrics", "career_war", "stock", "trades",
        "il_status", "il_stints", "acquisition", "breakout_meta", "dev_credit",
    )

    def _lite_handedness(g: dict):
        # Mirror of prospx _getHandedness: newest -> oldest, FanGraphs first,
        # then TJStats, then any other source; bats/throws come from ONE
        # extras blob (no cross-source merging). Runs post-harvest, so it
        # sees exactly the observations the frontend keeps inline.
        pts = g.get("points") or []

        def _scan(pick):
            for pt in reversed(pts):
                for src, obs in (pt.get("per_source") or {}).items():
                    if not pick(src) or not isinstance(obs, dict):
                        continue
                    tools = obs.get("tools")
                    ex = tools.get("_extras") if isinstance(tools, dict) else None
                    if not ex:
                        continue
                    bats = ex.get("bats") or ex.get("bat_side")
                    throws = ex.get("throws") or ex.get("throw_side")
                    if bats or throws:
                        return bats, throws
            return None

        for pick in (lambda s: s == "fangraphs",
                     lambda s: s == "tjstats",
                     lambda s: s not in ("fangraphs", "tjstats")):
            got = _scan(pick)
            if got:
                return got
        return None, None

    def _grad_lite(g: dict) -> dict:
        lite = {k: g.get(k) for k in _LITE_SCALARS if g.get(k) is not None}
        for k in _LITE_WHOLE:
            v = g.get(k)
            if v:
                lite[k] = v
        # career_stats: MLB rows only, the fields the WAG / WAR-rate helpers
        # read (gradWarPerYr / gradPersonalFullSeason season fractions), plus the
        # measured PA (stats.MEASURED_PA_FIELD) the Debuted MLB chip floor reads.
        cs_slim = [{f: r.get(f) for f in ("season", "level", "ip", "pa", "ab", "pa_measured")
                    if r.get(f) is not None}
                   for r in (g.get("career_stats") or [])
                   if isinstance(r, dict)
                   and str(r.get("level") or "").upper() == "MLB"]
        if cs_slim:
            lite["career_stats"] = cs_slim
        # transactions: kind drives the WAG outcome penalty; date/orgs/
        # description feed the farm-detail transaction feed.
        tx_slim = [{f: t.get(f) for f in ("kind", "date", "from_org",
                                          "to_org", "description")
                    if t.get(f) is not None}
                   for t in (g.get("transactions") or []) if isinstance(t, dict)]
        if tx_slim:
            lite["transactions"] = tx_slim
        rs = g.get("roster_status") or {}
        rs_slim = {f: rs.get(f) for f in ("on_40_man", "options_used",
                                          "options_used_years",
                                          "options_remaining", "service_phase",
                                          "mlb_debut_date")
                   if rs.get(f) is not None}
        if rs_slim:
            lite["roster_status"] = rs_slim
        sp = g.get("surplus")
        if isinstance(sp, dict) and sp:
            lite["surplus"] = {k: v for k, v in sp.items()
                               if k not in ("dist", "ci", "valuation_set")}
        dv = g.get("debuted_value")
        if isinstance(dv, dict) and dv:
            lite["debuted_value"] = {k: v for k, v in dv.items()
                                     if k not in ("prior", "remaining_dist")}
        sc = g.get("statcast_metrics")
        if isinstance(sc, dict) and sc:
            sc_slim = {k: v for k, v in sc.items()
                       if k not in ("level_splits", "coverage", "pitch_plot")}
            pm = sc.get("pitch_movement")
            if isinstance(pm, dict):
                sc_slim["pitch_movement"] = {k: v for k, v in pm.items()
                                             if k != "outings"}
            lite["statcast_metrics"] = sc_slim
        tl = g.get("tools")
        if isinstance(tl, dict):
            tl_slim = {k: v for k, v in tl.items()
                       if k in ("grades", "spread") or k.startswith("composite")}
            if tl_slim:
                lite["tools"] = tl_slim
        # Last consensus point only, per_source emptied: keeps the FV badge
        # label, wide-spread W mark, and shrinkage tooltip working on list
        # rows without shipping the history. Always present (the monolith
        # rows always carry `points`, even when empty), so the two shapes
        # stay drop-in compatible.
        pts = g.get("points") or []
        if pts and isinstance(pts[-1], dict):
            lp = {k: v for k, v in pts[-1].items() if k != "per_source"}
            lp["per_source"] = {}
            lite["points"] = [lp]
        else:
            lite["points"] = []
        bats, throws = _lite_handedness(g)
        if bats:
            lite["bats"] = bats
        if throws:
            lite["throws"] = throws
        lite["_lite"] = True
        return lite

    debuts_lite = [_grad_lite(g) for g in graduate_payload]

    # v46 payload-slim — scout reports also ship in a FIXED number of hash
    # chunks (scout_reports_0.json .. scout_reports_7.json) so a card open
    # pulls ~1/8th of the monolith instead of all of it. chunk index =
    # sum(ord(char)) over player_key mod N, mirrored by _scoutChunkOf in
    # prospx/index.html — keep the two in lockstep. The monolith keeps
    # being written: mlb_player_export.py and legacy cached HTML read it.
    _SCOUT_CHUNKS = 8
    scout_report_chunks: list[dict] = [{} for _ in range(_SCOUT_CHUNKS)]
    for _k, _v in scout_reports_sidecar.items():
        scout_report_chunks[sum(ord(_c) for _c in _k) % _SCOUT_CHUNKS][_k] = _v

    import value_framework as _vf_stamp        # local: module-level import is a cycle
    boot = {
        "generated_at": _utcnow_iso() + "Z",
        # Which dollar calibration priced players[].surplus on these rows. This
        # artifact is the reason the stamp exists: it was WRITTEN at 21:12 on
        # 2026-07-31, six and a half hours after the v6 config landed, and still
        # carried v5 dollars because a long-running chained export held the old
        # config in memory. Nothing could see it, because nothing said.
        "calibration": _vf_stamp.calibration_stamp(),
        # Present only under WAG_UNIFIED: tells PROSPX every WAG reads the baked engine
        # block. Absent, the client runs exactly as before (audit F25).
        **({"wag_definition": WAG_DEFINITION} if WAG_UNIFIED else {}),
        "run": latest_run_summary(),
        # The two-track "as of" stamps (grades, transactions/IL) the PROSPX tab
        # freshness lines and build_site read. Stamped HERE so every path that
        # regenerates this payload carries them (RPR09, 2026-10-02): a payload
        # re-exported outside run_monthly used to ship with no block at all, and
        # the Transactions, Injured List and Time Machine stamps rendered empty.
        # run_monthly._patch_export_run_summary still refreshes it after
        # finish_run, so a pipeline night ends on the finished run's stamps.
        "data_freshness": data_freshness(),
        "total_tracked": len(active_payload) + len(graduate_payload) + len(inactive_payload),
        "active_count": len(actives),
        "inactive_count": len(inactives),
        "debut_count": len(grads),
        "inactive_cutoff": cutoff.isoformat(),
        "prospect_savant_count": savant_matched,
        # PV-07: the "Not yet graded by any source" section's served description (on/off,
        # label sources, rejoin rule and its state), derived from
        # data/provisional_track_eval.json; PROSPX reads it to split the board.
        "prov_section": dict(prov_section_state(), n_board_rows=sum(
            1 for _k, _v in _source_graded_by_key.items() if not _v)),
        # The PROSPX display flags (EFV_DISPLAY_SWAPS above); the page reads them here only.
        "flags": {"efv_display_swaps": bool(EFV_DISPLAY_SWAPS)},
        "players":    active_payload,
        "spotlights": spotlight_payload,
        # Standout single games of active prospects (see the harvest note above);
        # read by the PROSPX Standout Performances ribbon.
        "standouts":  standouts,
        "org_summary": org_summary,
        "farm_trajectory_means": farm_trajectory_means,
        # v28 — cohort-restricted (hitter / pitcher) league trajectory means
        # per window. Mirror of the org-wide mean above; lets the frontend
        # render a cohort-only growth chart with the same baseline-removal
        # math used for the all-prospects chart. NB: the per-window league
        # STDEV maps (farm_trajectory_stdevs / hitter_traj_stdevs /
        # pitcher_traj_stdevs) are computed above and consumed INTERNALLY only
        # (they feed dvm_plus / hitter_dvm_plus / pitcher_dvm_plus). They are
        # deliberately NOT baked into the boot payload: the growth-chart
        # baseline math (makeFarmGrowthChart / makeFarmCohortGrowthPanel) uses
        # only the means, so shipping the stdevs was a dead wire field with no
        # JS/HTML reader (finding [32]).
        "farm_hitter_trajectory_means":   hitter_traj_means,
        "farm_pitcher_trajectory_means":  pitcher_traj_means,
        # The principal window and the DvM+ blend constants, so the farm
        # Development tab copy reads them instead of typing them (farm_dev_spec).
        "farm_dev_spec": farm_dev_spec(_dvm_diff["spec"] if _dvm_diff is not None else None),
        "level_norms": level_norms,
        # MLB Draft bonus-pool ceilings + per-pick slot values, scraped
        # from MLB.com per year. Keyed by year (int). Drives the
        # spending-block utilization caption on the farm detail page.
        "mlb_draft_pools": draft_pools,
        # v31.8c — mlb_trade_players moved to a sidecar so the boot
        # payload stays light. The frontend lazy-loads it only when
        # the user opens the Transactions tab (trade audit consumer).
        "_slices": {
            "debuts":             "debuts.json",
            # v46 payload-slim — list-render slice of the graduates. The
            # Graduates tab / context rail / idle warm read THIS; the full
            # debuts.json is fetched only on graduate card open, Time
            # Machine, and the debuted chart mode (ensureDebutsFull).
            "debuts_lite":        "debuts_lite.json",
            "inactive":           "inactive.json",
            "rosters_by_org":     "rosters_by_org.json",
            "scout_reports":      "scout_reports.json",
            "mlb_trade_players":  "mlb_trade_players.json",
            # NB: the Free Agency sidecars (fa_class/fa_archive/fa_meta,
            # written by fa_export.py) are NOT advertised here — the FA
            # module is its own surface (/fa/, assets/fa.js) and fetches
            # them from /data/ directly. PROSPX carries zero FA bytes.
        },
        # v46 payload-slim — chunked-slice contract: {name: {prefix, chunks}}.
        # The frontend fetches <prefix><i>.json where i = sum(ord) of the
        # player_key mod `chunks` (see ensureScoutReports). scout_reports
        # stays in _slices above so HTML predating this contract keeps
        # working off the monolith.
        "_slices_chunked": {
            "scout_reports": {"prefix": "scout_reports_",
                              "chunks": _SCOUT_CHUNKS},
        },
        # v32 — pitch_plot coordinates ship PER PLAYER under
        # data/pitch_plots/{player_key}.json (the monolithic sidecar
        # reached 411MB and one card open pulled all of it). The key
        # list keeps absent players from ever fetching; the directory
        # contract is advertised separately from the single-file slices.
        # v33 — player_detail/{player_key}.json rides the same contract
        # (spray/rolling-xwOBA coordinates, game logs, historical
        # per-source tool grades; lazy-merged when a card opens).
        # v47 - debuts_full/{player_key}.json carries the FULL graduate
        # record (the same object serialized into debuts.json for that
        # player: complete points, statcast level_splits, full tools,
        # career_stats). EVERY row in debuts.json has a shard, so no keys
        # list is needed; the graduate list itself is the key set.
        "_slices_dir": {"pitch_plots": "pitch_plots/",
                        "player_detail": "player_detail/",
                        "debuts_full": "debuts_full/"},
        "pitch_plots_keys": sorted(pitch_plots_sidecar),
        "player_detail_keys": sorted(player_detail_sidecar),
    }
    out_dir = out_path.parent
    # Compact JSON (no indent, no spaces in separators) — cuts the boot
    # payload roughly in half. The files are still valid JSON, just not
    # human-readable. Open in a browser DevTools console + JSON.parse if
    # you need to inspect interactively.
    # v25 — orjson serializer (3-5x faster than stdlib json for our
    # payload shape). Output is byte-equivalent compact JSON. Falls back
    # to stdlib if orjson isn't installed (CI without the optional dep).
    try:
        import orjson as _orjson
        # OPT_NON_STR_KEYS allows int keys (mlbam_id maps); orjson refuses
        # them by default. No SORT or INDENT — match the prior compact mode.
        _opts = _orjson.OPT_NON_STR_KEYS
        def _dump_bytes(obj) -> bytes:
            return _orjson.dumps(obj, option=_opts)
    except ImportError:
        _compact = {"separators": (",", ":")}
        def _dump_bytes(obj) -> bytes:
            # json.dumps keeps ensure_ascii=True, so these bytes are pure
            # ASCII and encoding-equivalent to the old write_text path.
            return json.dumps(obj, **_compact).encode("utf-8")

    def _dump(obj, path, force: bool = False):
        # v47 compare-before-write: when the target already holds byte-
        # identical content, skip the write entirely (size check first,
        # then a byte compare) so mtimes only move when payloads actually
        # change - rsync quick-check and the deploy box's nightly gzip
        # then skip the ~8k unchanged per-player shards. force=True is
        # for payloads carrying a per-run stamp (the boot's
        # meta.generated_at) where the compare could never match.
        # v48 (finding [19]): the byte compare STREAMS the on-disk file in
        # chunks (_file_equals_bytes) instead of path.read_bytes(), so a
        # ~60MB monolith is not loaded into a second full buffer alongside
        # `data` at the export peak. The size check still short-circuits the
        # common changed case before any read.
        data = _dump_bytes(obj)
        if not force:
            try:
                if path.stat().st_size == len(data) and _file_equals_bytes(path, data):
                    return
            except OSError:
                pass
        # ATOMIC (2026-08-06). This is the shared writer for EVERY exported
        # artifact (the 74MB boot/timeseries monolith, debuts, rosters_by_org and
        # every sidecar), so an in-place write here is the widest exposure in the
        # pipeline. data/timeseries.json was found TRUNCATED at 42.9MB of 74MB
        # after an interrupted write raced a second writer
        # (run_monthly._patch_export_run_summary re-serialises the same file to
        # stamp a run summary, and nothing serialises the pair). Nothing raised:
        # the half-file was structurally plausible enough to serve, and it faked
        # five org-test failures before anyone noticed it was the FILE that was
        # wrong. It is gitignored, so there was nothing to restore from either.
        # Temp file in the SAME directory, then os.replace, which is a
        # same-filesystem rename and therefore atomic: a concurrent reader gets
        # the whole old file or the whole new one, never a partial. Writing the
        # temp beside the target rather than in the system temp dir is what keeps
        # the rename atomic instead of a cross-device copy.
        tmp = path.with_name(path.name + f".tmp{os.getpid()}")
        try:
            tmp.write_bytes(data)
            _atomic_replace(tmp, path)
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass                    # already renamed: the success path
    _phase_done("assemble")
    _dump(boot, out_path, force=True)
    _dump(graduate_payload, out_dir / "debuts.json")
    _dump(rosters_by_org, out_dir / "rosters_by_org.json")
    _phase_done("write_boot")
    if intermediate:
        # v47 - mid-monthly intermediate export (run_monthly.main step 5
        # ONLY). Everything below this return is a frontend-only sidecar
        # that the chained daily's d9 full export rewrites ~15 min later;
        # nothing in the monthly tail reads them, so writing them here was
        # ~1GB of pure duplication. STALENESS CLASS REINTRODUCED: between
        # this export and the chained d9, debuts_lite / inactive /
        # scout_reports* / mlb_trade_players / pitch_plots/ /
        # player_detail/ / debuts_full/ on disk lag the boot + debuts.json
        # written above. Any FUTURE monthly-tail step that reads one of
        # the skipped sidecars must run after the full export (or this
        # call must drop intermediate=True). Stale-shard cleanup also
        # lives only in the full path below.
        return out_path
    _dump(debuts_lite, out_dir / "debuts_lite.json")
    _dump(inactive_payload, out_dir / "inactive.json")
    _dump(scout_reports_sidecar, out_dir / "scout_reports.json")
    # v46 payload-slim — fixed chunk count, so every index is always
    # (re)written and stale chunks can't linger between runs.
    for _i, _chunk in enumerate(scout_report_chunks):
        _dump(_chunk, out_dir / f"scout_reports_{_i}.json")
    # v31.8c — mlb_trade_players sidecar (lazy-loaded when the
    # Transactions tab opens, not part of initial boot).
    _dump(load_mlb_trade_players(), out_dir / "mlb_trade_players.json")
    # v32 — pitch_plots split per player (see _slices_dir above). Stale
    # per-player files from departed players are removed; the legacy
    # monolithic pitch_plots.json is deleted if present so the deploy
    # artifact never ships 411MB of coordinates again.
    pp_dir = out_dir / "pitch_plots"
    pp_dir.mkdir(parents=True, exist_ok=True)
    existing = {f.stem for f in pp_dir.glob("*.json")}
    for k, v in pitch_plots_sidecar.items():
        _dump(v, pp_dir / f"{k}.json")
    for stale in existing - set(pitch_plots_sidecar):
        try:
            (pp_dir / f"{stale}.json").unlink()
        except OSError:
            pass
    # v33 — player_detail per-player sidecar files (same lifecycle rules
    # as pitch_plots: write current, remove departed players' files).
    pd_dir = out_dir / "player_detail"
    pd_dir.mkdir(parents=True, exist_ok=True)
    pd_existing = {f.stem for f in pd_dir.glob("*.json")}
    for k, v in player_detail_sidecar.items():
        _dump(v, pd_dir / f"{k}.json")
    for stale in pd_existing - set(player_detail_sidecar):
        try:
            (pd_dir / f"{stale}.json").unlink()
        except OSError:
            pass
    # v47 - debuts_full per-player shards (see the _slices_dir contract
    # comment above): one file per graduate row carrying that player's
    # COMPLETE debuts.json record, so a graduate card open can fetch one
    # player instead of the whole monolith. debuts.json itself is
    # unchanged this pass (Time Machine + the debuted chart mode still
    # read it). Same lifecycle rules as player_detail: write current,
    # remove departed players' files.
    df_dir = out_dir / "debuts_full"
    df_dir.mkdir(parents=True, exist_ok=True)
    df_existing = {f.stem for f in df_dir.glob("*.json")}
    df_keys: set[str] = set()
    for g in graduate_payload:
        gk = g.get("player_key")
        if not gk:
            continue
        df_keys.add(gk)
        _dump(g, df_dir / f"{gk}.json")
    for stale in df_existing - df_keys:
        try:
            (df_dir / f"{stale}.json").unlink()
        except OSError:
            pass
    legacy_pp = out_dir / "pitch_plots.json"
    if legacy_pp.exists():
        try:
            legacy_pp.unlink()
        except OSError:
            pass
    _phase_done("write_sidecars")
    return out_path


# ============================================================================
# data/pitch_plots/{player_key}.json - the published shape
# ============================================================================
# An entry is one pitcher's pitch-movement coordinates: a `top` view and a
# `level_splits` map of per-level views. Three rules hold over what ships,
# and all three are about a Stuff+ value only meaning something next to the
# baseline it was scored on (mlb_stuff_plus's module docstring has the why):
#
#   1. EVERY VIEW NAMES ITS BASELINE. `stuff_baseline` is written by
#      statcast_metrics from the scorer's own return, so it is the baseline
#      the numbers in that view were ACTUALLY scored against, not one
#      re-derived here from a point list the plot already truncated.
#   2. THE MODEL LABEL SHIPS ONCE PER VIEW, not once per pitch. It was the
#      same 38-character string on all 1.85 million published points.
#   3. A VIEW IS NEVER SHIPPED TWICE. On 2026-09-18, 1,767 of 1,789 entries
#      had a `top` byte-identical to one of their own splits - every
#      single-level pitcher plus 588 multi-level ones whose aggregate
#      covered one level. Those ship `top_ref: "<LEVEL>"` instead, and
#      readers call resolve_pitch_plot_entry (prospx does the same in JS).
#      The 22 entries whose `top` is a genuine pool of several levels keep a
#      real `top`, because their numbers really are on a third baseline.

PITCH_PLOT_INTERNAL_FIELDS = ("ax_mirrored", "x0_mirrored")


def slim_pitch_plot_view(view: dict) -> dict:
    """One pitch-plot view in its published shape. Moves no number.

    Drops the scorer's own mirrored inputs (`ax_mirrored` / `x0_mirrored`,
    which exist to build a feature row and are read by no consumer) and
    hoists the per-row model stamp to `stuff_model` on the view. The stamp
    is only hoisted when every scored row agrees on it: a view carrying two
    model names keeps them per row rather than publishing one label over
    numbers that did not all come from it.
    """

    if not isinstance(view, dict):
        return view
    points = view.get("points")
    if not isinstance(points, list):
        return dict(view)
    models = {p.get("tj_stuff_plus_model") for p in points
              if isinstance(p, dict) and p.get("tj_stuff_plus_model")}
    hoist = len(models) == 1
    out = {k: v for k, v in view.items() if k != "points"}
    if hoist:
        out["stuff_model"] = next(iter(models))
    slim_points = []
    for p in points:
        if not isinstance(p, dict):
            slim_points.append(p)
            continue
        q = {k: v for k, v in p.items()
             if k not in PITCH_PLOT_INTERNAL_FIELDS
             and not (hoist and k == "tj_stuff_plus_model")}
        slim_points.append(q)
    out["points"] = slim_points
    return out


def dedupe_pitch_plot_entry(entry: dict) -> dict:
    """Replace a `top` that equals one of the entry's own splits with a
    `top_ref` naming that level. Byte-for-byte equality only - a pooled top
    that differs from every split by so much as one value is kept whole."""

    if not isinstance(entry, dict):
        return entry
    top = entry.get("top")
    splits = entry.get("level_splits") or {}
    if not top or not splits:
        return entry
    for level, block in splits.items():
        if block == top:
            out = {"top_ref": level}
            out.update({k: v for k, v in entry.items() if k != "top"})
            return out
    return entry


def resolve_pitch_plot_entry(entry: dict) -> dict:
    """Inverse of dedupe_pitch_plot_entry: the {top, level_splits} shape
    every reader expects, whichever form was on disk."""

    if not isinstance(entry, dict):
        return entry
    ref = entry.get("top_ref")
    if not ref:
        return entry
    out = {k: v for k, v in entry.items() if k != "top_ref"}
    block = (entry.get("level_splits") or {}).get(ref)
    if block is not None:
        out["top"] = block
    return out


def load_export_unified(boot_path: Path) -> dict:
    """Inverse of `export_timeseries_json`'s split — reads the boot JSON
    and inlines `debuts` / `inactive` / `rosters_by_org` /
    `scout_reports` from the sidecar files (if they exist) so callers
    (mostly tests) can work with a single dict.

    Returns the boot dict unchanged when the sidecars aren't present
    (legacy monolithic export, or a partial run).
    """
    boot_path = Path(boot_path)
    payload = json.loads(boot_path.read_text())
    out_dir = boot_path.parent
    for slice_name in ("debuts", "inactive", "rosters_by_org",
                        "scout_reports", "mlb_trade_players",
                        "pitch_plots"):
        if slice_name in payload:
            continue
        sidecar = out_dir / f"{slice_name}.json"
        if sidecar.exists():
            payload[slice_name] = json.loads(sidecar.read_text())
        elif slice_name == "pitch_plots" and (out_dir / "pitch_plots").is_dir():
            # v32 split-per-player layout: re-assemble the unified shape.
            payload[slice_name] = {
                f.stem: json.loads(f.read_text())
                for f in sorted((out_dir / "pitch_plots").glob("*.json"))}
        else:
            # Empty default keeps test assertions like `for g in
            # payload["debuts"]` from raising KeyError when the slice
            # is genuinely empty for this run.
            payload[slice_name] = [] if slice_name in ("debuts", "inactive") else {}
    # v31.12 — re-inline pitch_plots into the statcast_metrics block
    # for tests + ad-hoc callers that expect the unified shape. The
    # frontend lazy-loads + merges separately.
    pp = payload.get("pitch_plots") or {}
    if pp:
        for cohort_key in ("players", "debuts", "inactive"):
            for p in payload.get(cohort_key) or []:
                pkey = p.get("player_key")
                if pkey not in pp:
                    continue
                sc = p.get("statcast_metrics") or {}
                if not sc:
                    continue
                entry = resolve_pitch_plot_entry(pp[pkey])
                if entry.get("top"):
                    sc["pitch_plot"] = entry["top"]
                level_map = entry.get("level_splits") or {}
                if level_map:
                    for row in sc.get("level_splits") or []:
                        lvl = row.get("level") or "_"
                        if lvl in level_map:
                            row["pitch_plot"] = level_map[lvl]
    return payload


# ============================================================================
# Editorial flag logging (model-audit WS-0c) — flags persisted AT EMIT TIME
# with matched-control sampling keys so 30/60-day forward hit rates can be
# scored once cohorts mature (Phase 5). Lives ABOVE the FA section: the FA
# accessors below are guarded to fa_* tables only.
# ============================================================================

def _editorial_band(fv: float | None, age: float | None) -> tuple[str | None, str | None]:
    """Matched-control sampling keys for editorial-flag scoring: a flagged
    player's forward performance only means something against UNFLAGGED
    players of the same FV band x level x age band."""
    fv_band = None
    if fv is not None:
        fv_band = ("<45" if fv < 45 else "45" if fv < 50 else "50" if fv < 55
                   else "55" if fv < 60 else "60+")
    age_band = None
    if age is not None:
        age_band = ("<19" if age < 19 else "19-21" if age < 21 else "21-23"
                    if age < 23 else "23-25" if age < 25 else "25+")
    return fv_band, age_band


def insert_editorial_flags(emitted_at: str, flags: list[dict]) -> int:
    """Persist editorial flags AT EMIT TIME (model-audit WS-0c). Each flag:
    {player_key, flag_type, score?, fv?, level?, age?}. Append-only per
    (player, flag, date) — re-running an export the same day is a no-op,
    so the forward-evaluation cohorts can't be contaminated by reruns."""
    n = 0
    with connect() as con:
        for f in flags:
            if not (f.get("player_key") and f.get("flag_type")):
                continue
            fv_band, age_band = _editorial_band(f.get("fv"), f.get("age"))
            cur = con.execute(
                """INSERT OR IGNORE INTO editorial_flags
                   (player_key, flag_type, emitted_at, score, fv, fv_band,
                    level, age_band)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (f["player_key"], f["flag_type"], emitted_at, f.get("score"),
                 f.get("fv"), fv_band, f.get("level"), age_band))
            n += cur.rowcount
    return n


def load_editorial_flags(flag_type: str | None = None) -> list[dict]:
    """All logged flags (oldest first) — the editorial forward-evaluation
    (model-audit WS-10) scores these against matured outcomes."""
    where = " WHERE flag_type = ?" if flag_type else ""
    args = (flag_type,) if flag_type else ()
    with connect() as con:
        cur = con.execute(
            "SELECT player_key, flag_type, emitted_at, score, fv, fv_band, "
            "level, age_band FROM editorial_flags" + where +
            " ORDER BY emitted_at, player_key", args)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


# ============================================================================
# MLB Free Agency module — storage accessors (additive; fa_* tables only).
# Generic (key1, key2) payload_json upsert/load pairs in the career_war
# style. Nothing here touches prospect tables; the FA module's PROSPX
# consumption is read-only by construction.
# ============================================================================

def _fa_upsert(table: str, key_cols: tuple[str, str], rows: dict, extra_cols=None) -> int:
    """Shared two-key payload upsert. ``rows`` maps (k1, k2) -> payload
    dict; ``extra_cols`` optionally maps column name -> per-row getter so
    queryable columns (status, position…) ride alongside the payload."""
    extra_cols = extra_cols or {}
    n = 0
    cols = [key_cols[0], key_cols[1], *extra_cols.keys(), "payload_json"]
    placeholders = ", ".join("?" for _ in cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in [*extra_cols.keys(), "payload_json"])
    sql = (f"INSERT INTO {table} ({', '.join(cols)}, fetched_at) "
           f"VALUES ({placeholders}, datetime('now')) "
           f"ON CONFLICT({key_cols[0]}, {key_cols[1]}) DO UPDATE SET "
           f"{updates}, fetched_at=excluded.fetched_at")
    with connect() as con:
        for (k1, k2), payload in rows.items():
            if not payload:
                continue
            vals = [k1, k2, *(get(payload) for get in extra_cols.values()), json.dumps(payload)]
            con.execute(sql, vals)
            n += 1
    return n


def _fa_load(table: str, key_cols: tuple[str, str], where: str = "", args: tuple = ()) -> dict:
    try:
        with connect() as con:
            rows = con.execute(
                f"SELECT {key_cols[0]}, {key_cols[1]}, payload_json FROM {table} {where}", args
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {(r[0], r[1]): json.loads(r[2]) for r in rows}


def upsert_fa_class_players(class_year: int, players: list[dict]) -> int:
    rows = {(p["player_key"], class_year): p for p in players if p.get("player_key")}
    return _fa_upsert("fa_class_players", ("player_key", "class_year"), rows,
                      extra_cols={"mlbam_id": lambda p: p.get("mlbam_id"),
                                  "position": lambda p: p.get("position"),
                                  "status": lambda p: p.get("status")})


def load_fa_class_players(class_year: int | None = None) -> dict:
    where, args = ("WHERE class_year = ?", (class_year,)) if class_year else ("", ())
    return _fa_load("fa_class_players", ("player_key", "class_year"), where, args)


def upsert_fa_signings(class_year: int, signings: list[dict]) -> int:
    rows = {(s["player_key"], class_year): s for s in signings if s.get("player_key")}
    return _fa_upsert("fa_signings", ("player_key", "class_year"), rows)


def load_fa_signings(class_year: int | None = None) -> dict:
    where, args = ("WHERE class_year = ?", (class_year,)) if class_year else ("", ())
    return _fa_load("fa_signings", ("player_key", "class_year"), where, args)


def touch_fa_signings(class_year: int) -> int:
    """Bump fetched_at on the current class's signings to record that the FA
    pipeline re-checked them this run. A quiet in-season market produces no NEW
    signing rows, so without this the freshness stamp would freeze at the last
    actual signing and the UI's source-staleness check would read 'stale' even
    though the signings are current. Returns the number of rows touched.

    NOTE: this can only ever touch rows that EXIST. Before the winter opens a
    class has zero signing rows, so this no-ops and the stamp stays frozen on
    the previous class - the bug that made the 2027 board read "signings stale"
    every day from 2026-07-10 onward. `record_source_check` is the authority;
    this remains so an existing row's own fetched_at is not misleading."""
    with connect() as con:
        cur = con.execute(
            "UPDATE fa_signings SET fetched_at = datetime('now') WHERE class_year = ?",
            (class_year,))
        return cur.rowcount


def upsert_fa_team_payroll(season: int, teams: list[dict]) -> int:
    rows = {(t["team"], season): t for t in teams if t.get("team")}
    return _fa_upsert("fa_team_payroll", ("team", "season"), rows)


def load_fa_team_payroll(season: int | None = None) -> dict:
    where, args = ("WHERE season = ?", (season,)) if season else ("", ())
    return _fa_load("fa_team_payroll", ("team", "season"), where, args)


def insert_fa_events_first_seen(class_year: int, events: list[dict]) -> int:
    """Append-only event insert. Each event is {player_key, event_type,
    payload?}. The event_date stamps as today ONLY on first insert —
    re-observing the same transition on later refreshes is a no-op, so
    first-seen dates never drift."""
    n = 0
    with connect() as con:
        for e in events:
            if not (e.get("player_key") and e.get("event_type")):
                continue
            cur = con.execute(
                """INSERT OR IGNORE INTO fa_events
                   (class_year, player_key, event_type, event_date, payload_json)
                   VALUES (?, ?, ?, date('now'), ?)""",
                (class_year, e["player_key"], e["event_type"],
                 json.dumps(e.get("payload") or {})))
            n += cur.rowcount
    return n


def load_fa_events(class_year: int | None = None) -> list[dict]:
    """Events newest-first; each row carries class_year/player_key/
    event_type/event_date plus the payload fields."""
    where, args = ("WHERE class_year = ?", (class_year,)) if class_year else ("", ())
    try:
        with connect() as con:
            rows = con.execute(
                f"""SELECT class_year, player_key, event_type, event_date, payload_json
                    FROM fa_events {where} ORDER BY event_date DESC, player_key""",
                args).fetchall()
    except sqlite3.OperationalError:
        return []
    return [{"class_year": r[0], "player_key": r[1], "event_type": r[2],
             "event_date": r[3], **json.loads(r[4])} for r in rows]


def set_fa_class_player_status(class_year: int, player_key: str, status: str) -> None:
    """Flip one class member's queryable status column (e.g. → 'signed'
    when the winter tracker observes a deal). The payload keeps the raw
    as-scraped row; status is the pipeline's reconciled view."""
    with connect() as con:
        con.execute(
            "UPDATE fa_class_players SET status = ? WHERE class_year = ? AND player_key = ?",
            (status, class_year, player_key))


def upsert_fa_model_eval(model_version: str, gate: str, payload: dict) -> None:
    with connect() as con:
        con.execute(
            """INSERT INTO fa_model_eval (model_version, gate, payload_json, computed_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(model_version, gate) DO UPDATE SET
                 payload_json=excluded.payload_json, computed_at=excluded.computed_at""",
            (model_version, gate, json.dumps(payload)))


def load_fa_model_eval() -> dict:
    return _fa_load("fa_model_eval", ("model_version", "gate"))


# ---------------------------------------------------------------------------
# Staff Gems stage 1: staff persons, spells, units and player location spells
# ---------------------------------------------------------------------------
#
# Parsed from the gitignored .cache/staff/ by `staff_ingest.py --parse`, which
# is hand-run (not wired into run_monthly until stage 3). These tables carry
# WHO held WHICH job WHERE and WHEN, and WHERE each player was on which days.
# They carry no grade, no development number and no outcome, and nothing here
# joins a development or outcome number to a staff person (design
# docs/staff-gems/DESIGN.md section 4.1; gate docs/staff-gems/STAFF_GEMS_GATE.md).
#
#   staff_persons          one row per MLBAM person id; a name never creates a row
#   staff_spells           person x team x season x jobId, day or season resolution
#   staff_units            affiliate-seasons, MLB club-seasons, pseudo-teams, one
#                          org-offseason unit per org per winter, one 2020 org unit
#   staff_role_review      the role map's review queue (no role is ever guessed)
#   staff_identity_review  name-only rows that matched no person or more than one
#   player_location_spells where a player was: day resolution from the
#                          transactions cache, season resolution from career rows
#   staff_parse_runs       one row per parse, with its counts
#
# Every table is replaced whole by one parse inside one transaction, so a
# parse is idempotent: running it twice on the same cache leaves the same rows.
STAFF_SCHEMA = """
CREATE TABLE IF NOT EXISTS staff_persons (
    person_id     INTEGER PRIMARY KEY,      -- MLBAM id; the person IS the id
    full_name     TEXT NOT NULL,            -- the name on the latest season list
    names_json    TEXT NOT NULL,            -- every distinct name seen for this id
    first_season  INTEGER NOT NULL,
    last_season   INTEGER NOT NULL,
    n_spells      INTEGER NOT NULL,
    source        TEXT NOT NULL DEFAULT 'statsapi_coaches'
);

CREATE TABLE IF NOT EXISTS staff_units (
    unit_id     TEXT PRIMARY KEY,           -- T<team>_<season> | OFF_<org>_<season> | ORG2020_<org>
    kind        TEXT NOT NULL,              -- mlb | affiliate | pseudo | offseason | org_2020
    season      INTEGER NOT NULL,
    team_id     INTEGER,
    team_name   TEXT,
    org_id      INTEGER NOT NULL,           -- the parent MLB club's id
    org_code    TEXT,
    sport_id    INTEGER,
    level       TEXT,                       -- MLB AAA AA A+ A CPX DSL, NULL for pseudo and org units
    league      TEXT,
    start_date  TEXT,                       -- first played game, or the window's first day
    end_date    TEXT                        -- last played game, or the window's last day
);
CREATE INDEX IF NOT EXISTS idx_staff_units_team ON staff_units(team_id, season);

CREATE TABLE IF NOT EXISTS staff_spells (
    spell_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id        INTEGER NOT NULL REFERENCES staff_persons(person_id),
    team_id          INTEGER NOT NULL,
    season           INTEGER NOT NULL,
    unit_id          TEXT NOT NULL,
    org_id           INTEGER NOT NULL,
    org_code         TEXT,
    level            TEXT,
    job_id           TEXT NOT NULL,
    job              TEXT,
    title            TEXT,
    role             TEXT NOT NULL,         -- manager hitting pitching defense first_base third_base excluded review
    role_rule        TEXT NOT NULL,         -- pair | job | title | unmapped_job | unmapped_title
    start_date       TEXT,                  -- NULL only when the team played no game that season
    end_date         TEXT,
    resolution       TEXT NOT NULL,         -- day | season
    resolution_note  TEXT,                  -- not_bisected | no_games | bisect_error | unexplained
    source           TEXT NOT NULL DEFAULT 'statsapi_coaches',
    fetched_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_staff_spells_person ON staff_spells(person_id);
CREATE INDEX IF NOT EXISTS idx_staff_spells_unit ON staff_spells(unit_id);

CREATE TABLE IF NOT EXISTS staff_role_review (
    job_id        TEXT NOT NULL,
    title         TEXT NOT NULL,
    reason        TEXT NOT NULL,            -- explicit_review | unmapped_job | unmapped_title
    n_rows        INTEGER NOT NULL,
    n_persons     INTEGER NOT NULL,
    first_season  INTEGER NOT NULL,
    last_season   INTEGER NOT NULL,
    PRIMARY KEY (job_id, title)
);

CREATE TABLE IF NOT EXISTS staff_identity_review (
    review_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    source           TEXT NOT NULL,
    name             TEXT NOT NULL,
    org_id           INTEGER,
    season           INTEGER,
    reason           TEXT NOT NULL,         -- no_match | ambiguous | no_org_season
    candidates_json  TEXT NOT NULL DEFAULT '[]',
    payload_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS player_location_spells (
    loc_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    player_key    TEXT NOT NULL,
    season        INTEGER NOT NULL,
    team_id       INTEGER,                  -- NULL when a season row names an org level with several teams
    unit_id       TEXT,
    org_id        INTEGER,
    org_code      TEXT,
    level         TEXT,
    start_date    TEXT,
    end_date      TEXT,
    status        TEXT NOT NULL,            -- active | il | rehab
    resolution    TEXT NOT NULL,            -- day | season
    weight        REAL NOT NULL,            -- 1.0 for day rows; the games share for season rows
    n_candidates  INTEGER NOT NULL DEFAULT 1,
    source        TEXT NOT NULL             -- transactions | career
);
CREATE INDEX IF NOT EXISTS idx_player_loc_player ON player_location_spells(player_key, season);
CREATE INDEX IF NOT EXISTS idx_player_loc_unit ON player_location_spells(unit_id);

CREATE TABLE IF NOT EXISTS staff_parse_runs (
    run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    parsed_at    TEXT NOT NULL DEFAULT (datetime('now')),
    cache_dir    TEXT NOT NULL,
    role_map     TEXT NOT NULL,
    counts_json  TEXT NOT NULL
);
"""

STAFF_TABLES = ("staff_persons", "staff_units", "staff_spells", "staff_role_review",
                "staff_identity_review", "player_location_spells")


def init_staff_schema() -> None:
    """Create the Staff Gems stage 1 tables if missing (idempotent; never run by init_db)."""
    with connect() as con:
        con.executescript(STAFF_SCHEMA)


def replace_staff_tables(*, persons: list[dict], units: list[dict], spells: list[dict],
                         role_review: list[dict], identity_review: list[dict],
                         locations: list[dict], cache_dir: str, role_map: str,
                         counts: dict) -> int:
    """Replace every Staff Gems stage 1 table in ONE transaction and log the run.

    Refuses a spell whose person id is missing or unknown, so no row can exist
    without an MLBAM id and no name can create a person. Returns the run id."""
    known = {int(p["person_id"]) for p in persons}
    for s in spells:
        if s.get("person_id") is None or int(s["person_id"]) not in known:
            raise ValueError(f"staff spell without a known MLBAM person id: {s!r}")
    with connect() as con:
        con.executescript(STAFF_SCHEMA)
        for t in STAFF_TABLES:
            con.execute(f"DELETE FROM {t}")
        con.executemany(
            "INSERT INTO staff_persons (person_id, full_name, names_json, first_season,"
            " last_season, n_spells, source) VALUES (?,?,?,?,?,?,?)",
            [(int(p["person_id"]), p["full_name"], json.dumps(p["names"]), p["first_season"],
              p["last_season"], p["n_spells"], p.get("source", "statsapi_coaches"))
             for p in persons])
        con.executemany(
            "INSERT INTO staff_units (unit_id, kind, season, team_id, team_name, org_id, org_code,"
            " sport_id, level, league, start_date, end_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [(u["unit_id"], u["kind"], u["season"], u.get("team_id"), u.get("team_name"),
              u["org_id"], u.get("org_code"), u.get("sport_id"), u.get("level"), u.get("league"),
              u.get("start_date"), u.get("end_date")) for u in units])
        con.executemany(
            "INSERT INTO staff_spells (person_id, team_id, season, unit_id, org_id, org_code, level,"
            " job_id, job, title, role, role_rule, start_date, end_date, resolution,"
            " resolution_note, source, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(int(s["person_id"]), s["team_id"], s["season"], s["unit_id"], s["org_id"],
              s.get("org_code"), s.get("level"), s["job_id"], s.get("job"), s.get("title"),
              s["role"], s["role_rule"], s.get("start_date"), s.get("end_date"), s["resolution"],
              s.get("resolution_note"), s.get("source", "statsapi_coaches"), s.get("fetched_at"))
             for s in spells])
        con.executemany(
            "INSERT INTO staff_role_review (job_id, title, reason, n_rows, n_persons, first_season,"
            " last_season) VALUES (?,?,?,?,?,?,?)",
            [(r["job_id"], r["title"], r["reason"], r["n_rows"], r["n_persons"],
              r["first_season"], r["last_season"]) for r in role_review])
        con.executemany(
            "INSERT INTO staff_identity_review (source, name, org_id, season, reason,"
            " candidates_json, payload_json) VALUES (?,?,?,?,?,?,?)",
            [(r["source"], r["name"], r.get("org_id"), r.get("season"), r["reason"],
              json.dumps(r.get("candidates") or []), json.dumps(r.get("payload") or {}))
             for r in identity_review])
        con.executemany(
            "INSERT INTO player_location_spells (player_key, season, team_id, unit_id, org_id,"
            " org_code, level, start_date, end_date, status, resolution, weight, n_candidates,"
            " source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(r["player_key"], r["season"], r.get("team_id"), r.get("unit_id"), r.get("org_id"),
              r.get("org_code"), r.get("level"), r.get("start_date"), r.get("end_date"),
              r["status"], r["resolution"], r["weight"], r.get("n_candidates", 1), r["source"])
             for r in locations])
        cur = con.execute(
            "INSERT INTO staff_parse_runs (cache_dir, role_map, counts_json) VALUES (?,?,?)",
            (cache_dir, role_map, json.dumps(counts, sort_keys=True)))
        return int(cur.lastrowid)


def load_staff_table(table: str) -> list[dict]:
    """Every row of one Staff Gems stage 1 table, as dicts ([] when the table is absent)."""
    if table not in STAFF_TABLES + ("staff_parse_runs",):
        raise ValueError(f"not a staff table: {table}")
    try:
        with connect() as con:
            return [dict(r) for r in con.execute(f"SELECT * FROM {table}").fetchall()]
    except sqlite3.OperationalError:
        return []

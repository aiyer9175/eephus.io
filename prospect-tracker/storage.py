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
    Snapshot, canonical_player_key,
    HITTER_TOOL_KEYS, PITCHER_TOOL_KEYS, ALL_TOOL_KEYS,
)
from consensus import PlayerTimeseries, stock_movement
from stats import StatLine

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
    for pl in payloads:
        t = pl.get("tools")
        if not t:
            continue
        for k in plus_keys:
            mean, stdev = cohort_stats[k]
            t[f"{k}_plus"] = _index_plus(t.get(k), mean, stdev)
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
                    "note": f"{label} {raw_val:.1f} — Plus tier (60+) composite toolset.",
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
                "note": f"Stuff index {stuff_plus} — above-cohort arsenal.",
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
                "note": f"Tool {overall_raw:.1f} — Below-Average tier composite toolset.",
            })


# v14 — Breakout indicator constants.
_BREAKOUT_WINDOW_DAYS = 180          # 6 months
_BREAKOUT_WINDOW_MIN_UPDATES = 4     # at least 4 consensus points
_BREAKOUT_FV_UPGRADE_THRESHOLD = 5.0
_BREAKOUT_TOOL_VELOCITY_THRESHOLD = 3.0  # avg tool grade improvement
# v15 — Loosen hitter RPS+ gate from 120 → 110 (was producing zero hitter
# breakouts league-wide). 110 ≈ 1 stdev above cohort mean; still exclusive
# but allows truly-emerging bats through. Also accept a strong wRC+ proxy
# for graduated-statline hitters (≥130 wRC+).
_BREAKOUT_HITTER_RPS_PLUS_GATE = 110
_BREAKOUT_HITTER_WRC_PLUS_GATE = 130
_BREAKOUT_PITCHER_STF_PLUS_GATE = 105
_BREAKOUT_PITCHER_FIP_MINUS_GATE = 90
# v29 — Statcast+ as a perf gate. ≥115 is the top-quintile threshold
# both sides agree on (mirrors the JS filter chip). It picks up
# prospects whose contact-quality + zone discipline (or pitch-quality
# + induced whiffs) is elite even when the scout-published indices
# (Stuff+, wRC+, RPS+) haven't been computed yet. Same gate for
# hitters and pitchers since Statcast+ is already side-aware.
_BREAKOUT_STATCAST_PLUS_GATE = 115
# v29 — Stat-only Statcast+ bar. Higher than the perf-gate (115) since
# the stat-only path bypasses the tool/FV velocity requirement: only
# elite-tier Statcast composites should trigger breakout without ANY
# scout-side movement signal. 130 mirrors the wRC+ / RPS+ stat-only
# bar (≈+2σ on each metric's pool).
_BREAKOUT_STAT_STATCAST_PLUS_GATE = 130
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
            # v17 — Accept either wRC+ (MLB-experienced cohort) OR RPS+
            # (active-prospect cohort) as the hitter stat-only signal.
            # wRC+ is only on graduates/MLB-experienced players; RPS+ is
            # the equivalent metric on active MiLB prospects. RPS+ gate
            # mirrors the wRC+ gate's percentile (130 ≈ +2σ on each).
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
            rps = statline.get("rps_plus")
            try:
                if rps is not None and float(rps) >= _BREAKOUT_STAT_WRC_PLUS_GATE:
                    return {
                        "flag": True,
                        "reason": "stats",
                        "perf_gate": "rps_plus",
                        "fv_upgrade": None,
                        "tool_velocity": None,
                        "window_anchor_date": None,
                    }
            except (TypeError, ValueError):
                pass
            # v17 — Active-prospect MiLB hitters mostly don't have wRC+
            # OR RPS+ populated; their level-anchored equivalent is
            # `statline.ops_plus_level` (100 = level mean). Accept ≥130
            # at the same gate threshold for the stat-only breakout path.
            ops_plus = statline.get("ops_plus_level")
            try:
                if ops_plus is not None and float(ops_plus) >= _BREAKOUT_STAT_OPS_PLUS_LEVEL_GATE:
                    return {
                        "flag": True,
                        "reason": "stats",
                        "perf_gate": "ops_plus_level",
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

    # Performance gate — check hitter RPS+, then pitcher stf_plus_periph
    # or fip_minus. Two-way passes if either side passes. `statline` and
    # `saberm` already defined above for the stat-only gate path.
    perf_gate_passed = None

    rps = statline.get("rps_plus")
    try:
        if rps is not None and float(rps) >= _BREAKOUT_HITTER_RPS_PLUS_GATE:
            perf_gate_passed = "rps_plus"
    except (TypeError, ValueError):
        pass

    # v15 — wRC+ alternative for hitters (graduates / MLB-experienced
    # prospects who carry wRC+ in sabermetrics rather than RPS+).
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

-- Per-graduate career WAR aggregated from FanGraphs (bulk batting_stats /
-- pitching_stats pull via pybaseball). payload_json is a dict:
--   {"seasons": {"2023": 1.5, "2024": 2.8, ...},
--    "career_war": 4.3,
--    "war_per_yr": 2.15,
--    "war_seasons_count": 2,
--    "source": "fangraphs"}
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
    overall_rank  INTEGER,              -- PROSPX consensus board rank as-of
    consensus_fv  REAL,                 -- headline consensus FV (fv_close)
    fv_plus       INTEGER NOT NULL DEFAULT 0,
    fv_tier       TEXT,                 -- bucket label ('60','55',… ) for cohorting
    org           TEXT,
    position      TEXT,
    status        TEXT,                 -- active | debuted | inactive
    is_pitcher    INTEGER NOT NULL DEFAULT 0,
    age           REAL,
    payload_json  TEXT NOT NULL,        -- {dollar_dvm_plus, statcast_plus, live_score,
                                        --  tool, surplus_mm, …} — the Arkmetric family
    inserted_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (player_key, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_metric_snap_date ON metric_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_metric_snap_player ON metric_snapshots(player_key);

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

-- Mock drafts: one row per (source, snapshot, year, pick).
CREATE TABLE IF NOT EXISTS draft_mocks (
    source          TEXT NOT NULL,
    snapshot_date   TEXT NOT NULL,
    draft_year      INTEGER NOT NULL,
    pick_overall    INTEGER NOT NULL,
    team            TEXT NOT NULL,
    player_key      TEXT,
    player_name     TEXT NOT NULL,
    PRIMARY KEY (source, snapshot_date, draft_year, pick_overall)
);
CREATE INDEX IF NOT EXISTS idx_draft_mocks_year ON draft_mocks(draft_year);

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
CREATE TABLE IF NOT EXISTS draft_lottery_odds (
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
        # The one-shot tools/migrate_fv_plus_from_decimal.py back-fills
        # rows whose .5 fv values came from a "+" parse.
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
                """INSERT INTO players (player_key, player_name, position, org)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(player_key) DO UPDATE SET
                       player_name = excluded.player_name,
                       position    = COALESCE(excluded.position, players.position),
                       org         = COALESCE(excluded.org, players.org),
                       updated_at  = datetime('now')""",
                (s.player_key, s.player_name, s.position, s.org),
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
    """Append-only insert; the UNIQUE constraint dedupes re-runs."""
    from trades import Trade
    n = 0
    with connect() as con:
        for t in trades:
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


def upsert_career_war(by_key: dict[str, dict]) -> int:
    """Upsert one career-WAR aggregate per graduate. Skips empty payloads.

    Caller is expected to wrap each aggregate as:
      {"seasons": {"2023": 1.5, "2024": 2.8, ...},
       "career_war": 4.3,
       "war_per_yr": 2.15,
       "war_seasons_count": 2,
       "source": "fangraphs"}
    """
    n = 0
    with connect() as con:
        for key, rec in by_key.items():
            if not rec:
                continue
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
    return {r["player_key"]: dict(r) for r in rows}


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


def upsert_draft_mocks(rows: Iterable[dict]) -> int:
    n = 0
    with connect() as con:
        for r in rows:
            con.execute(
                """INSERT INTO draft_mocks
                     (source, snapshot_date, draft_year, pick_overall,
                      team, player_key, player_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source, snapshot_date, draft_year, pick_overall)
                   DO UPDATE SET
                     team        = excluded.team,
                     player_key  = COALESCE(excluded.player_key, draft_mocks.player_key),
                     player_name = excluded.player_name""",
                (r.get("source"), r.get("snapshot_date"), r.get("draft_year"),
                 r.get("pick_overall"), r.get("team"),
                 r.get("player_key"), r.get("player_name")),
            )
            n += 1
    return n


def load_draft_mocks(draft_year: int | None = None) -> list[dict]:
    q = """SELECT source, snapshot_date, draft_year, pick_overall,
                  team, player_key, player_name
           FROM draft_mocks"""
    params: tuple = ()
    if draft_year is not None:
        q += " WHERE draft_year = ?"
        params = (draft_year,)
    q += " ORDER BY snapshot_date DESC, pick_overall ASC"
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
    pick_pos, odds_pct (nullable for picks 7+), round_label (default '1';
    '1A' / '1B' for competitive-balance picks), snapshot_date, source."""
    n = 0
    with connect() as con:
        for r in rows:
            con.execute(
                """INSERT INTO draft_lottery_odds
                     (draft_year, team, pick_pos, odds_pct, round_label, snapshot_date, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(draft_year, team, pick_pos, snapshot_date) DO UPDATE SET
                     odds_pct    = excluded.odds_pct,
                     round_label = excluded.round_label,
                     source      = excluded.source,
                     inserted_at = datetime('now')""",
                (r["draft_year"], r["team"], r["pick_pos"], r.get("odds_pct"),
                 r.get("round_label", "1"), r["snapshot_date"], r["source"]),
            )
            n += 1
    return n


def load_draft_lottery_odds(draft_year: int | None = None,
                            latest_only: bool = True) -> list[dict]:
    """Return lottery odds rows. When latest_only=True, restrict to
    the most recent snapshot_date per (draft_year, team, pick_pos)."""
    if latest_only:
        q = """SELECT draft_year, team, pick_pos, odds_pct, round_label, snapshot_date, source
               FROM draft_lottery_odds o
               WHERE snapshot_date = (
                 SELECT MAX(snapshot_date) FROM draft_lottery_odds
                 WHERE draft_year = o.draft_year
                   AND team       = o.team
                   AND pick_pos   = o.pick_pos
               )"""
    else:
        q = """SELECT draft_year, team, pick_pos, odds_pct, round_label, snapshot_date, source
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
                "ORDER BY effective_date DESC").fetchall()]
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
    "dollar_dvm_plus",   # $DvM+
    "statcast_plus",     # SC+
    "live_score",        # live composite
    "tool",              # tool composite (ToolDvM+ base)
    "live_overall_rank",
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


def snapshot_board_metrics(players: Iterable[dict], snapshot_date: str | None = None) -> int:
    """Capture the DERIVED board state (consensus rank/FV + Arkmetric family)
    for every player in a built timeseries, one row per player per calendar
    date. Idempotent: re-running on the same date overwrites that date's rows.

    `players` is the list of serialized player dicts from timeseries.json
    (or the in-memory equivalent). Players with no consensus FV and no rank
    are skipped (nothing meaningful to snapshot).
    """
    snapshot_date = snapshot_date or date.today().isoformat()
    n = 0
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
            con.execute(
                """INSERT INTO metric_snapshots
                     (player_key, snapshot_date, overall_rank, consensus_fv,
                      fv_plus, fv_tier, org, position, status, is_pitcher,
                      age, payload_json, inserted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
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
                     inserted_at=excluded.inserted_at""",
                (key, snapshot_date, rank, fv, fv_plus,
                 _fv_tier_label(fv, fv_plus), p.get("org"), p.get("position"),
                 p.get("status"),
                 1 if (p.get("position") or "").upper() in ("SP", "RP", "P", "SIRP", "MIRP", "RHP", "LHP") else 0,
                 p.get("age"), json.dumps(payload)),
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

# Multi-window trajectories. The list page lets the user toggle between
# these to ask "who's been developing prospects best over the last X?".
# The 1y entry matches FARM_TRAJECTORY_LOOKBACK_DAYS and feeds the
# canonical `trajectory_score` (which keeps the report-card grading
# anchored to the 1y window). Longer windows surface orgs whose growth
# only shows up over a draft cycle or two.
FARM_TRAJECTORY_WINDOWS = {
    "1y": 365,
    "3y": 365 * 3,
    "6y": 365 * 6,
}

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


# Industry-standard draft pick-slot value curve (career WAR expectations
# based on FanGraphs / Baseball America surplus-value research). A
# 1st-overall pick has historically averaged ~9 career WAR; the curve
# decays steeply through the supplemental + 2nd round and tails to ~0
# by the late rounds. Used to compute "draft pick value above
# expectation" = actual_war − slot_expected_war, which credits orgs
# that beat the market at each pick slot (e.g., a 28th-rounder making
# the majors counts more than a #1 overall reaching the same outcome).
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


def _pick_slot_expected_war(pick_overall) -> float | None:
    """Step-lookup the historical expected career WAR for a draft slot.
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
    for threshold, war in _PICK_SLOT_EXPECTED_WAR:
        if p <= threshold:
            return war
    return _PICK_SLOT_EXPECTED_WAR[-1][1]


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
    string. Saves/games-started signal isn't reliably surfaced on the
    payload, so this defers to the consensus position (FG-driven, which
    already breaks out SP/MIRP/SIRP/CL when it can). Falls back to MIRP
    when the position is just RHP/LHP/P/RP without role detail."""
    pos = (graduate_payload.get("position") or "").upper()
    # Split on "/" — a "MIRP/SIRP" prospect leans MIRP.
    tokens = [t.strip() for t in pos.split("/") if t.strip()]
    if any(t in ("CL", "CP") for t in tokens):
        return "cl"
    if any(t == "SP" for t in tokens):
        return "sp"
    if any(t == "SIRP" for t in tokens):
        return "sirp"
    if any(t == "MIRP" for t in tokens):
        return "mirp"
    # Generic RP / RHP / LHP / P → assume multi-inning fallback.
    return "mirp"


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
            pa = int(s.get("pa") or 0)
        except (TypeError, ValueError):
            pa = 0
        if pa == 0:
            # Fall back to AB × ~1.13 (league-wide PA:AB ratio is ~1.135 —
            # walks + HBP + sacrifices push PA above AB). Better than
            # dropping the row entirely when PA isn't on file.
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

    full_season_war: float | None = None
    if is_pitcher:
        role = _pitcher_role(graduate_payload)
        target = _ROLE_BASELINES.get(f"{role}_ip_target",
                                     _ROLE_BASELINES["mirp_ip_target"])
        if target <= 0:
            return None
        if total_ip >= 50.0:
            full_season_war = (career_war / total_ip) * target
        elif war_per_yr is not None:
            # Pitcher full-season fallback: use war_per_yr as the projected
            # season rate. (Equivalent to treating one rate-season as a
            # full-target-IP season.)
            full_season_war = war_per_yr
    else:
        target = _ROLE_BASELINES.get("hitter_pa_target", 612.0)
        if target <= 0:
            return None
        if total_pa >= 150:
            full_season_war = (career_war / total_pa) * target
        elif war_per_yr is not None:
            full_season_war = war_per_yr

    if full_season_war is None:
        return None

    expected = _fv_to_expected_war_per_yr(fv_close, is_pitcher=is_pitcher)
    if expected is None:
        return None
    delta = full_season_war - expected
    if delta > 0:
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
_CONVICTION_RECENCY_YEARS        = 6   # was 5 (v6 — align with 6y DvM+)
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
    yvals = [g["war_per_yr"] for g in grads
             if g.get("war_per_yr") is not None]
    yvals.sort(reverse=True)
    top3 = yvals[:3]
    return {
        "top3_war_per_yr": (round(sum(top3) / len(top3), 2)
                            if len(top3) >= 3 else None),
        "grad_count_qualifying": len(grads),
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
    cwars = sorted([g["career_war"] for g in pool
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
            })

    # Order stars by descending signal magnitude so the top 5 tooltip
    # surfaces the most-impressive contributors.
    stars.sort(key=lambda s: max(s["war_per_yr"], s["season_peak"]),
               reverse=True)
    star_count = len(stars)
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
        "conviction":      1 if star_count >= 1 else 0,
        "grad_count_qualifying": len(grads),
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
            })
    hof_grads.sort(key=lambda s: s["season_peak"], reverse=True)
    return {
        "hof_count":         len(hof_grads),
        "hof_names":         [h["name"] for h in hof_grads[:5] if h.get("name")],
        "hof_grads":         hof_grads[:5],
        "peak_season_war":   max((h["season_peak"] for h in hof_grads), default=None),
        "threshold":         _HOF_TRACK_SEASON_WAR_THRESHOLD,
        "grad_count_qualifying": len(grads),
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
                blend = (v.get("blend_by_window") or {}).get("6y")
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
                "raw":   "Talent given up — same valuation as inbound side",
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
                "raw":      f"{hm.get('post_tj_count', 0)} of {hm.get('active_count', 0)} with prior TJ — informational only, not graded",
                "info_only": True,
            })
        if hm.get("post_tj_pct_pit") is not None:
            subs.append({
                "label":     "Pitcher post-TJ % (info)",
                "kind":      "pct",
                "value":     round(hm["post_tj_pct_pit"], 3),
                "n":         hm.get("actives_pit_count"),
                "raw":       "informational only — post-surgery grace period often correlates with above-avg outcomes",
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
    war_total = sum(g["career_war"] for g in relevant) if relevant else 0.0
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
        if len(relevant) >= 3:
            war_per_m = round(war_total / pool_total_mm, 3)
        if fv_total_active > 0:
            fv_per_m = round(fv_total_active / pool_total_mm, 3)

    return {
        "war_per_m_pool":   war_per_m,
        "fv_per_m_pool":    fv_per_m,
        "grad_count":       len(relevant),
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
    war_total = sum(g["career_war"] for g in relevant)
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
        return {"war_per_m_ifa": None, "grad_count": len(relevant),
                "war_total": round(war_total, 2), "ifa_total_usd": 0}
    war_per_m = round(war_total / (ifa_total / 1_000_000.0), 3)
    return {
        "war_per_m_ifa": war_per_m,
        "grad_count":    len(relevant),
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
    _BUCKETS as _SV_BUCKET_ORDER,
)

# Per-prospect Monte-Carlo draw counts for the baked surplus enrichment
# (`_build_surplus_payload`). These were referenced but never defined, so the
# `ci`/`dist` enrichment threw NameError and was silently swallowed by its
# `except: pass` — every player shipped with `surplus` but no distribution
# (no P10–P90 fan, no P(bust)). Modest counts keep the ~2k-player export fast
# while giving stable percentiles + P(bust); the engine's config defaults
# (10000 dist / 4000 CI) are reserved for one-off analysis. Pass None to fall
# back to those config defaults instead.
_SURPLUS_DIST_DRAWS = 4000   # outcome distribution (percentiles, P(bust), risk-adj)
_SURPLUS_CI_DRAWS   = 2000   # epistemic credible interval on expected SV


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
                           fv_dispersion=None, n_sources=None):
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
    point = _estimate_surplus_mm(fv, is_pitcher, position, age=age, eta_years=eta_years)
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
    }
    if eta_years is not None:
        out["eta_years"] = round(float(eta_years), 2)
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
                                   eta_years=eta_years, draws=_SURPLUS_CI_DRAWS)
        if ci and ci.get("point_mm") is not None:
            out["ci"] = {"lo_mm": ci["lo_mm"], "median_mm": ci["median_mm"],
                         "hi_mm": ci["hi_mm"], "cred": ci["cred"], "regime": ci.get("regime")}
        dist = _sv_distribution(fv, is_pitcher, position, age=age, eta_years=eta_years,
                                fv_dispersion=fv_dispersion, n_sources=n_sources,
                                draws=_SURPLUS_DIST_DRAWS)
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


def _engine_wag_result(fv, is_pitcher, position, observed_war, *, age=None,
                       service_years=None, career_stats=None):
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
        if service_years is not None:
            return _engine_wag(fv, is_pitcher, ow, position=position,
                               service_years=float(service_years), age=age)
        pa, ip = _mlb_exposure_pa_ip(career_stats)
        return _engine_wag(fv, is_pitcher, ow, position=position,
                           exposure_pa=(pa or None), exposure_ip=(ip or None), age=age)
    except Exception:
        return None


def _build_debuted_payload(fv, is_pitcher, position, *, age=None,
                           career_war=None, roster_status=None,
                           contract=None, career_stats=None):
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
        w = _engine_wag_result(fv, is_pitcher, position, observed_war,
                               age=age, service_years=service_years, career_stats=career_stats)
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
                # Standardized boom/bust label (percentile-keyed) -- the canonical
                # categorical grade signal, replacing the legacy _compute_boom_bust.
                "boom_label": _engine_wag_boom_bust(w),
            }
    except Exception:
        pass
    return out or None


_PITCHER_POS_RE = re.compile(r"^(RHP|LHP|SP|RP|MIRP|SIRP|P)")


def _finalize_active_surplus_leaf(m: dict) -> dict:
    """v18 — New financial leaf: sum of FV-implied surplus value across
    the org's active prospects (graduates excluded — they belong to the
    existing fin_contract_surplus / mlb_production_* family) minus the
    amortized acquisition bonus paid. Spreads the bonus over the 6yr
    cost-controlled window so a $5M signing bonus reads as ~$0.83M/yr
    of cost. Result = surplus_total_mm, surplus_per_prospect_mm, and a
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
# with the org-level 6y DvM+ window. Tunable in one place; tests pin the
# constant value.
FARM_TOOL_DELTA_LOOKBACK_DAYS = 365 * 6


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


def _top_end_points(prospects: list[dict], n: int = FARM_TOP_END_COUNT) -> float:
    """Sum of tiered points for the org's top N prospects (FV-sorted).
    Prospects list is expected pre-sorted by fv_raw descending — that
    matches how `m["prospects"]` is populated in `export_timeseries_json`."""
    return round(sum(_fv_to_points(p.get("fv_raw")) for p in prospects[:n]), 2)


def _depth_points(prospects: list[dict],
                  start: int = FARM_DEPTH_START,
                  end: int = FARM_DEPTH_END) -> float:
    """Sum of tiered points for prospects ranked `start+1` through `end`."""
    return round(sum(_fv_to_points(p.get("fv_raw")) for p in prospects[start:end]), 2)


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
    if pct < 0.14: return "A-"     # 7–14%    (was 10–20%)
    if pct < 0.24: return "B+"     # 14–24%   (was 20–30%)
    if pct < 0.36: return "B"      # 24–36%   (was 30–45%)
    if pct < 0.50: return "B-"     # 36–50%   (was 45–60%)
    if pct < 0.62: return "C+"     # 50–62%   (was 60–72%)
    if pct < 0.74: return "C"      # 62–74%   (was 72–85%)
    if pct < 0.86: return "C-"     # 74–86%   (was 85–95%)
    if pct < 0.93: return "D"      # 86–93%   (was bottom catch-all)
    if pct < 0.97: return "D-"     # NEW — 93–97%
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
        for pt in sorted_points:
            stream.append((pt.snapshot_date, "snapshot", pt.consensus_fv_raw))
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
                          top_n_active: int | None = None):
    """
    Serialize for the front-end widget.

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
    statlines = statlines or {}
    pitch_arsenals = pitch_arsenals or {}
    zone_metrics = zone_metrics or {}
    statcast_metrics = statcast_metrics or {}
    sabermetrics = sabermetrics or {}
    trades_by_player = trades_by_player or {}
    transactions_by_player = transactions_by_player or {}
    career_stats = career_stats or {}
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
    birth_dates = load_birth_dates()
    from stats import compute_age_decimal
    from age_level import score_age_vs_level
    from eta import estimate_eta
    from trades import canonical_org
    from level_norms import (
        compute_level_norms,
        age_baselines_from_norms,
        ops_norms_from_norms,
        era_norms_from_norms,
    )
    from stat_flags import compute_stat_flags, compute_tool_flags

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

    def _zone_num(v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def _percentile_rank_100(value: float, values: list[float], higher_is_better: bool) -> float:
        if not values:
            return 0.0
        if higher_is_better:
            count = sum(1 for v in values if v <= value)
        else:
            count = sum(1 for v in values if v >= value)
        return round(100.0 * count / len(values), 1)

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
            for row in level_rows:
                row["qualified"] = True
                row["percentile_sample_size"] = n
                for metric, higher_is_better in metric_directions.items():
                    value = _zone_num(row.get(metric))
                    if value is None:
                        continue
                    vals = [
                        _zone_num(peer.get(metric))
                        for peer in level_rows
                        if _zone_num(peer.get(metric)) is not None
                    ]
                    row["percentiles"][metric] = _percentile_rank_100(value, vals, higher_is_better)

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
        out = copy.deepcopy(scm)
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

    def _statcast_contact_metric(cq: dict, metric: str) -> float | None:
        if metric == "pull_air_pct":
            return _num((cq.get("spray") or {}).get("pull_air_pct"))
        return _num(cq.get(metric))

    def _normalize_statcast_contact_percentiles_for_export(scm_by_key: dict[str, dict]) -> dict[str, dict]:
        """Attach level/side contact-quality percentiles from stored rows.

        This is export-only and uses already-fetched Statcast contact_quality
        payloads, so it does not require another MLB API pass.
        """
        out = copy.deepcopy(scm_by_key or {})
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
            for row in level_rows:
                cq = row.get("contact_quality") or {}
                cq["percentile_sample_size"] = n
                for metric, higher_is_better in metric_directions.items():
                    value = _statcast_contact_metric(cq, metric)
                    if value is None:
                        continue
                    vals = [
                        _statcast_contact_metric(peer.get("contact_quality") or {}, metric)
                        for peer in level_rows
                    ]
                    vals = [v for v in vals if v is not None]
                    if len(vals) < 5:
                        continue
                    cq["percentiles"][metric] = _percentile_rank_100(value, vals, higher_is_better)

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
                payload["contact_quality"] = copy.deepcopy(normalized_primary.get("contact_quality") or {})
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
        out = copy.deepcopy(metric)
        keep_splits = out.get("level_splits") or []
        out.update(copy.deepcopy(match))
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

    # ── Per-org promotion-phase tendency (H1 vs H2) ───────────────────────
    # Walks every promotion event across every prospect (active +
    # graduated) and buckets by which half of the season the
    # promotion occurred in. The resulting per-org rate feeds into
    # each player's ETA half-season adjustment — orgs that
    # historically promote heavily post-ASB nudge the half-season-
    # elapsed adjustment downward (more debut risk this year);
    # H1-heavy orgs pull it back toward zero.
    #
    # Source of truth: `level_changes[player_key]` rows with
    # `kind in {"promotion", "debut"}`. We look at the trailing
    # 3 calendar years of events so the tendency reflects current
    # front-office behavior, not a decade-old pattern.
    def _compute_org_promotion_tendencies() -> dict[str, dict]:
        from datetime import date as _date
        from eta import ALL_STAR_BREAK_MONTH, ALL_STAR_BREAK_DAY
        today = _date.today()
        min_year = today.year - 3  # rolling 3-year window
        # player_key → org resolution. Prefer the player's current org
        # (roster_org_by_key) since most level changes happen at their
        # current org; graduates that crossed orgs are rare.
        org_h1: dict[str, int] = {}
        org_h2: dict[str, int] = {}
        for key, events in level_changes.items():
            org = roster_org_by_key.get(key)
            if not org:
                continue
            for ev in events or []:
                if ev.get("kind") not in {"promotion", "debut"}:
                    continue
                date_str = ev.get("date") or ""
                if len(date_str) < 10:
                    continue
                try:
                    d = _date.fromisoformat(date_str[:10])
                except ValueError:
                    continue
                if d.year < min_year:
                    continue
                # Bucket by H1 / H2 of the season the event landed in.
                # Off-season events (Nov-Feb) are skipped — they're
                # offseason adds, not in-season call-ups.
                if d.month in {11, 12, 1, 2}:
                    continue
                if (d.month, d.day) >= (ALL_STAR_BREAK_MONTH, ALL_STAR_BREAK_DAY):
                    org_h2[org] = org_h2.get(org, 0) + 1
                else:
                    org_h1[org] = org_h1.get(org, 0) + 1
        out: dict[str, dict] = {}
        per_org_n: dict[str, int] = {}
        for org in set(list(org_h1) + list(org_h2)):
            h1 = org_h1.get(org, 0)
            h2 = org_h2.get(org, 0)
            n = h1 + h2
            if n < 5:
                # Too few events to anchor a rate; skip — the player's
                # ETA falls back to the league-default half-season adj.
                continue
            per_org_n[org] = n
            out[org] = {
                "h1_rate":   round(h1 / n, 3),
                "h2_rate":   round(h2 / n, 3),
                "sample_n":  n,
            }
        # v31.11 — Org promotion aggressiveness. Index is the org's
        # rolling-3yr promotion+debut count divided by the league
        # median count over that same window. >1.0 = more aggressive
        # promoter than the median org (LAD/TBR profile), <1.0 = more
        # conservative (PIT/CIN profile). Consumed by eta.py as a
        # floor multiplier — aggressive orgs let quality cluster
        # compress further; conservative orgs hold the line.
        if per_org_n:
            sorted_n = sorted(per_org_n.values())
            mid = len(sorted_n) // 2
            if len(sorted_n) % 2 == 1:
                median_n = sorted_n[mid]
            else:
                median_n = (sorted_n[mid - 1] + sorted_n[mid]) / 2
            if median_n > 0:
                for org, n in per_org_n.items():
                    out[org]["aggressiveness_index"] = round(n / median_n, 3)
        return out

    org_promotion_tendencies = _compute_org_promotion_tendencies()

    def _derived_graduation_date(p: PlayerTimeseries) -> str | None:
        """
        Resolve a player's debut date (formerly "graduation_date").

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
        if api_debut:
            try:
                api_d = date.fromisoformat(api_debut)
            except ValueError:
                return api_debut
            if (api_d.month >= 11
                    and mlb_years and mlb_years[0] > api_d.year):
                return _safe_in_year_placeholder(
                    p.player_key, mlb_years[0], rows)
            return api_debut

        # 2. Earliest outright transaction date.
        _tx_rows = (transactions_by_player or {}).get(p.player_key) or []
        _outrights = sorted([
            tx.get("date") for tx in _tx_rows
            if (tx.get("kind") or "").lower() == "outrighted"
            and tx.get("date")
        ])
        if _outrights:
            return _outrights[0]

        # 3. consensus.py's snapshot-derived debut_date (FG-flagged path).
        if getattr(p, "debut_date", None):
            return p.debut_date

        # 4. Opening Day of the earliest MLB season we have on file.
        if mlb_years:
            return f"{min(mlb_years)}-04-01"

        return None

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
        # Resolve the player's CURRENT org for the promotion-tendency
        # lookup. Falls back gracefully if the player doesn't have an
        # org on file (rare — usually amateur/IFA pre-resolution).
        _player_org = canonical_org(
            roster_org_by_key.get(p.player_key) or p.org
        )
        _org_tendency = org_promotion_tendencies.get(_player_org) if _player_org else None
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
            # Per-org H1/H2 promotion tendency (computed once at top
            # of export). Scales the half-season adjustment — H2-heavy
            # orgs get a stronger post-break pull-in; H1-heavy orgs
            # get a softer one. None for orgs with <5 historical
            # promotions on file in the 3-year window.
            org_promotion_tendency=_org_tendency,
            # v12 — current IL status pushes ETA out. Season-ending
            # injury (or 60+ days on IL) adds +1.0y; 30-59 days adds
            # +0.5y. Fixes "Sebastian Walcott ETA 2026 despite being
            # out for the year" — without this, the ETA model only
            # tracked rolling-12mo health signals, not active IL.
            il_status=il_status.get(p.player_key) or {},
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
                    era = float(sl_out.get("era")) if sl_out.get("era") else None
                    avg_era = norms_perf.get("avg_era")
                    if era and avg_era and era > 0:
                        era_minus = round(era / avg_era * 100)
                        sl_out["era_minus_level"] = era_minus
                        sl_out["level_plus_pct"] = round((avg_era - era) / avg_era * 100)
                    # Peripheral STF+ (K%, BB%, HR/9 vs level mean). Replaces
                    # the scouting-grade composite as the headline STF+ chip;
                    # the scouting composite is still computed in tools.* but
                    # gets relabeled "Stuff grade+" in the UI.
                    stf_periph = _compute_peripheral_stf_plus(sl_out, norms_perf)
                    if stf_periph is not None:
                        sl_out["stf_plus_periph"] = stf_periph
                else:
                    ops_str = sl_out.get("ops")
                    ops = float(ops_str) if ops_str else None
                    avg_ops = norms_perf.get("avg_ops")
                    if ops and avg_ops and avg_ops > 0:
                        ops_plus = round(ops / avg_ops * 100)
                        sl_out["ops_plus_level"] = ops_plus
                        sl_out["level_plus_pct"] = round((ops - avg_ops) / avg_ops * 100)
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
                    _era = float(_rr.get("era")) if _rr.get("era") and _rr.get("era") != "—" else None
                    _avg_era = _norms_perf.get("avg_era")
                    if _era and _avg_era and _era > 0:
                        _rr["era_minus_level"] = round(_era / _avg_era * 100)
                else:
                    _ops = float(_rr.get("ops")) if _rr.get("ops") and _rr.get("ops") != "—" else None
                    _avg_ops = _norms_perf.get("avg_ops")
                    if _ops and _avg_ops and _avg_ops > 0:
                        _rr["ops_plus_level"] = round(_ops / _avg_ops * 100)
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
        tool_consensus_grades = (
            dict(latest_point.tools_consensus)
            if latest_point and latest_point.tools_consensus
            else None
        )
        # extras (frame/athl/delivery FG -2..+2 grades) and the
        # position bucket (catcher vs non-catcher) both feed the Tool /
        # D-Tool composite math, so consolidate once and pass through.
        _player_extras = _extract_player_extras(latest_point)
        _pos_bucket = _position_bucket(p.position)
        tools_payload = _compute_tool_composites(
            tool_consensus_grades, is_pitcher,
            player_extras=_player_extras,
            position_bucket=_pos_bucket,
        )
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
                    hitter_payload = _compute_tool_composites(
                        tool_consensus_grades, is_pitcher=False,
                        player_extras=_player_extras,
                        position_bucket=_pos_bucket)
                    pitcher_payload = _compute_tool_composites(
                        tool_consensus_grades, is_pitcher=True,
                        player_extras=_player_extras,
                        position_bucket=_pos_bucket)
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
            if history_entries:
                # Newest-first for the consensus timeline too.
                history_entries.sort(key=lambda e: e["snapshot_date"], reverse=True)
                tools_payload["history"] = history_entries
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
        tool_flags = compute_tool_flags(tools_payload, is_pitcher)

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
        _surplus = _build_surplus_payload(
            latest_fv, _is_pitcher_vf, p.position,
            age=age, eta_years=_eta_years_from(eta, date.today().year),
            fv_dispersion=(p.points[-1].fv_stddev if p.points else None))
        _debuted_value = (
            _build_debuted_payload(
                latest_fv, _is_pitcher_vf, p.position, age=age,
                career_war=career_war.get(p.player_key),
                roster_status=roster_status.get(p.player_key),
                contract=contracts_by_key.get(p.player_key),
                career_stats=career_stats.get(p.player_key))
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
            # Position in the FV-sorted active list, plus position within
            # the player's org. None for graduated/inactive (the maps below
            # only carry actives). Drives the rank pills on prospect detail.
            "overall_rank": overall_rank_by_key.get(p.player_key),
            # Position in the same FV-sorted list, but computed off the
            # second-to-last snapshot. Drives the rank-trend ▲/▼/—
            # under the diamond on list rows. None for players with
            # only one snapshot (new to the list — no prior position).
            "prev_overall_rank": prev_overall_rank_by_key.get(p.player_key),
            "org_rank": org_rank_by_key.get(p.player_key),
            "org_rank_total": org_size_by_key.get(p.player_key),
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
            "stock": stock_movement(p),
            "live_signal": _live_signal,
            "source_events": _source_events_export,
            "player_news": player_news_by_key.get(p.player_key, []),
            "statline": sl_out,
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
            # file (every active prospect who hasn't debuted).
            "career_war": career_war.get(p.player_key, {}),
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
            "roster_status": roster_status.get(p.player_key, {}),
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
                # actual year-adjustment applied (scaled by org-promo
                # tendency when on file, else the league-baseline -0.25
                # in post_break). All surface on the ETA panel.
                "half_season_adj": eta.half_season_adj,
                "season_phase": eta.season_phase,
                # Per-org promotion-phase tendency context. h1_rate +
                # h2_rate are floats in [0, 1] showing the org's
                # historical promotion split; org_promo_weight is the
                # multiplier applied to the league-baseline H1/H2
                # adjustment (1.0 = neutral). None when the org has
                # <5 historical promotions in the rolling 3yr window.
                "org_promo_h1_rate": eta.org_promo_h1_rate,
                "org_promo_h2_rate": eta.org_promo_h2_rate,
                "org_promo_weight":  eta.org_promo_weight,
                # v31.8 — Half-year bucket ("early" = Apr-Jun debut window
                # within eta_year; "late" = Jul-Sep). Combines fractional
                # ETA distance + org H1/H2 tendency + current-level bias.
                "half":              eta.eta_half,
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

        # Boom / Bust label — graduates only. Computed post-payload-build
        # since _compute_boom_bust reads career_war + career_stats fields
        # that were just stamped on the dict. Active prospects get None
        # (label only meaningful after the prospect has graduated AND
        # cleared the sample floor).
        if p.status == "debuted":
            try:
                payload["boom_label"] = _compute_boom_bust(payload)
            except Exception:
                payload["boom_label"] = "unsettled"
        else:
            payload["boom_label"] = None

        # Performance-anchored movement engine (replaces the FV-delta-only
        # `stock_movement`). compute_movement reads statline / career_stats
        # / age_vs_level / tools_consensus / acquisition / prospect_savant —
        # all of which are stamped on the payload above. Falls back to the
        # legacy `stock_movement` output (already in payload["stock"]) if
        # the engine raises.
        try:
            from spotlights import compute_movement
            payload["stock"] = compute_movement(payload)
        except Exception:
            log.exception("compute_movement failed for %s — keeping legacy "
                          "FV-delta stock signal", p.player_key)

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
    HARD_FV_STALE_YEARS = int(os.environ.get("HARD_FV_STALE_YEARS", "5"))
    try:
        hard_fv_cutoff = date(today.year - HARD_FV_STALE_YEARS, today.month, today.day)
    except ValueError:
        hard_fv_cutoff = date(today.year - HARD_FV_STALE_YEARS, today.month, 28)
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

        # ── Active-prospect recency ceiling (historical-leak fix) ──────────
        # Latest FV snapshot older than HARD_FV_STALE_YEARS → the player hasn't
        # been ranked by any source in 5+ years → aged out → inactive, even if
        # still playing or on an IL. Takes precedence over the IL bypass + the
        # softer fv_stale/play_stale gates below, so purely-historical players
        # (e.g. the 2017-2020 backfill cohort) can never enter the current pool.
        if latest_date < hard_fv_cutoff:
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
        "active-pool cleanup: %d low-FV (<%d), %d aged-out (FV >%dy stale), %d play-2yr-stale, "
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

    # ── DATA-INTEGRITY GUARD (historical-leak tripwire) ───────────────────
    # The active pool must contain only current prospects: none graduated, none
    # FV-stale beyond the aged-out ceiling. This catches regressions if a future
    # change weakens the cascade or a new historical ingestion sneaks players in.
    # Non-fatal: log loudly so the rebuild surfaces it (the pipeline still runs).
    _leak_graduated = [p.player_key for p in actives if p.status == "debuted"]
    _leak_aged_out = [
        p.player_key for p in actives
        if p.points and p.points[-1].snapshot_date
        and p.points[-1].snapshot_date < hard_fv_cutoff.isoformat()
    ]
    if _leak_graduated or _leak_aged_out:
        log.error(
            "INTEGRITY GUARD: active pool leak detected — %d graduated, %d aged-out "
            "(FV >%dy stale). Examples: %s",
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
    #   - _compute_breakout_flag → SC+ ≥ 115 perf gate / ≥ 130 stat-only
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
        # Rank by the SURFACED (snapped/displayed) consensus FV — so a 56.3 and
        # a 56.6 that both display as the same grade are TIED here and the
        # Tiebreaker-Score proxy arbitrates, rather than the higher decimal
        # auto-winning. The '+' upside flag is the only sub-FV distinction kept
        # ahead of TBS (a 45+ outranks a 45 but stays below 46).
        surfaced_fv = (latest.consensus_fv if latest.consensus_fv is not None
                       else (round(latest.consensus_fv_raw)
                             if latest.consensus_fv_raw is not None else 0))
        upside = 1 if getattr(latest, "consensus_fv_plus", False) else 0
        return (
            -surfaced_fv,        # surfaced (rounded) FV desc — primary
            -upside,             # '+' upside flag — ranks above same-FV non-'+'
            -_tbs_proxy(p),      # Tiebreaker Score desc — ARBITER on tied surfaced FV
            rank_key,            # avg_rank asc — final stable separator
        )
    actives.sort(key=_active_key)
    if top_n_active is not None:
        actives = actives[:top_n_active]

    # Pre-compute overall_rank (position in the FV-sorted active list) and
    # org_rank (position within the player's org by the same ordering).
    # `_serialize` reads these out of the maps below so we don't have to
    # re-sort in the front-end.
    overall_rank_by_key: dict[str, int] = {}
    org_rank_by_key: dict[str, int] = {}
    org_size_by_key: dict[str, int] = {}
    org_counters: dict[str, int] = {}
    org_totals: dict[str, int] = {}
    for p in actives:
        org_key = _active_display_org(p) or "?"
        org_totals[org_key] = org_totals.get(org_key, 0) + 1
    for i, p in enumerate(actives, start=1):
        overall_rank_by_key[p.player_key] = i
        org_key = _active_display_org(p) or "?"
        org_counters[org_key] = org_counters.get(org_key, 0) + 1
        org_rank_by_key[p.player_key] = org_counters[org_key]
        org_size_by_key[p.player_key] = org_totals[org_key]

    # Compute prev_overall_rank by re-sorting actives with the second-
    # to-last snapshot's consensus_fv instead of the latest, so the
    # frontend can render a rank-delta arrow (▲ +12 / ▼ -7 / — flat)
    # under each prospect's rank diamond. Players with only one
    # snapshot in history get no prior rank (they're new to the list).
    def _prior_key(p: PlayerTimeseries):
        pts = p.points or []
        if len(pts) < 2:
            return (999, 999, 999)
        prior = pts[-2]
        prior_fv = prior.consensus_fv_raw if prior.consensus_fv_raw is not None else None
        prior_rank = prior.avg_rank if prior.avg_rank is not None else 999
        # Same FV-then-Tools-then-rank tiebreak the current snapshot
        # uses, but reading the prior snapshot's tools_consensus so the
        # rank-delta arrow stays stable across snapshots with identical
        # FV but different tool grades.
        prior_tools = getattr(prior, "tools_consensus", None) or {}
        is_pitcher = bool(p.position
                          and p.position.split("/")[0] in PITCHER_POS_SET)
        comp = _compute_tool_composites(dict(prior_tools), is_pitcher)
        prior_tool = float(comp["composite_overall"]) if (comp and comp.get("composite_overall") is not None) else 0.0
        # v37 — apply the same on-IL tiebreak so the rank-delta arrow
        # reflects FV / tools movement rather than a one-time jump when a
        # player goes on or off the IL (current IL status cancels out of
        # both the current and prior keys).
        _il = il_status.get(p.player_key) or {}
        on_il = 1 if _il.get("is_on_il") else 0
        # v38 — Item-5: round the prior FV too, so the rank-delta arrow is
        # computed on the same surfaced-FV basis as the current rank (else a
        # sub-decimal FV drift would manufacture a phantom rank change).
        return (
            -round(prior_fv) if prior_fv is not None else 999,
            -prior_tool,
            on_il,
            prior_rank,
        )
    prior_actives = sorted(
        [p for p in actives if (p.points or []) and len(p.points) >= 2],
        key=_prior_key,
    )
    prev_overall_rank_by_key: dict[str, int] = {
        p.player_key: i for i, p in enumerate(prior_actives, start=1)
    }

    # Inactives: most recently seen first
    inactives.sort(key=lambda p: p.points[-1].snapshot_date if p.points else "", reverse=True)

    # Sort debuts by debut_date desc (most recent first)
    grads.sort(key=lambda p: p.debut_date or "", reverse=True)

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
    _ddvm_raw_by_key: dict[str, float] = {}
    _ddvm_tier_by_key: dict[str, int] = {}
    for p in actives:
        pts = p.points or []
        if not pts or pts[-1].consensus_fv_raw is None:
            continue
        fv_close = float(pts[-1].consensus_fv_raw)
        fv_open = float(pts[0].consensus_fv_raw) if pts[0].consensus_fv_raw is not None else fv_close
        try:
            _d0 = date.fromisoformat(pts[0].snapshot_date)
            _d1 = date.fromisoformat(pts[-1].snapshot_date)
            _yrs = max(0.5, (_d1 - _d0).days / 365.0)
        except Exception:
            _yrs = 1.0
        fv_move_rate = (fv_close - fv_open) / _yrs              # FV grade-pts / yr
        _bd = birth_dates.get(p.player_key)
        _age = compute_age_decimal(_bd)
        _sl = statlines.get(p.player_key)
        _lvl = _sl.get("level") if _sl else None
        _avl = score_age_vs_level(_age, _lvl, baselines=age_baselines)
        age_term = (-float(_avl.diff)) if (_avl and _avl.diff is not None) else 0.0
        # trajectory = FV-movement rate (primary) + 0.5 × age-for-level standing
        _ddvm_raw_by_key[p.player_key] = fv_move_rate + 0.5 * age_term
        _ddvm_tier_by_key[p.player_key] = int(round(fv_close / 5.0) * 5)
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
    _dollar_dvm_by_key: dict[str, float] = {}
    for _k, _traj in _ddvm_raw_by_key.items():
        _mu, _sd = _tier_stats.get(_ddvm_tier_by_key[_k], (_g_mu, _g_sd))
        _z = (_traj - _mu) / (_sd or 1.0)
        _dollar_dvm_by_key[_k] = round(max(40.0, min(160.0, 100.0 + 10.0 * _z)), 1)

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
                # 6yr surplus $M) − (acquisition bonus $M, NOT amortized
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
        m["prospects"].append({
            "name": p.player_name,
            "player_key": p.player_key,
            "pos": p.position,
            "age": age,
            "fv_label": fv_lab,
            "fv_raw": round(fv_raw, 1),
            "rank": idx + 1,
        })
        m["total_fv"] += fv_raw
        fv_int = int(fv_raw)
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
        elif avl.tier == "very-old":
            m["very_old_count"] += 1

        # Tool Quality accumulator — composite_overall (raw 20-80
        # power-mean of per-tool grades, same value as the prospect's
        # Tool composite). Computed directly from the latest consensus
        # tools dict so it's available even if a future re-ordering
        # moves the post-serialization passes around.
        is_pitcher_p = bool(p.position and p.position.split("/")[0] in PITCHER_POS_SET)
        _farm_extras = _extract_player_extras(p.points[-1] if p.points else None)
        _farm_pos_bucket = _position_bucket(p.position)
        _comp = _compute_tool_composites(
            dict(p.points[-1].tools_consensus) if p.points[-1].tools_consensus else None,
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
        _td = _compute_tool_deltas([
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
        _surplus_mm = _estimate_surplus_mm(fv_raw, is_pitcher_p, p.position)
        if _surplus_mm is not None:
            _bonus_mm = (float(acq_rec.get("bonus_usd") or 0) / 1_000_000.0)
            _net_mm = _surplus_mm - _bonus_mm
            m["_active_surplus_net_mm"]  += _net_mm
            m["_active_surplus_cost_mm"] += _bonus_mm
            m["_active_surplus_count"]   += 1
            # v32.0 — Track FV-pts contributing to surplus_net so
            # surplus_per_fv_pt_mm can be computed in finalize.
            # v32.1 — Per-side FV totals (hit / pit) for the asymmetry
            # display in the active_surplus leaf.
            if fv_raw is not None:
                m["_active_surplus_fv_total"] += float(fv_raw)
                if is_pitcher_p:
                    m["_active_surplus_fv_total_pit"] += float(fv_raw)
                else:
                    m["_active_surplus_fv_total_hit"] += float(fv_raw)
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
            if _method_bucket is not None and fv_raw is not None:
                _mb = m["_method_surplus"][_method_bucket]
                _mb["net_mm"]    += _net_mm
                _mb["cost_mm"]   += _bonus_mm
                _mb["fv_total"]  += float(fv_raw)
                _mb["count"]     += 1
        # Tree v3 — Draft Ceiling Hits: count drafted actives whose
        # current consensus FV ≥ 60 and whose draft year is within the
        # last 3 years. Captures whether the org's recent draft classes
        # produced high-ceiling prospects (not just whether grads beat
        # the slot in retrospect). Denominator: all drafted actives.
        if acq_rec.get("method") == "draft":
            m["_draft_actives_count"] = m.get("_draft_actives_count", 0) + 1
            draft_yr = acq_rec.get("year")
            today_yr = date.today().year
            if (draft_yr is not None
                    and today_yr - int(draft_yr) <= 3
                    and fv_raw is not None
                    and fv_raw >= 60.0):
                m["_draft_ceiling_hits"] = m.get("_draft_ceiling_hits", 0) + 1
            # v32.0 — Track FV-pts produced by active drafted prospects
            # in the same 3yr (T-5..T-2) window the war_per_m_pool leaf
            # uses for grads. This feeds the new fv_per_m_pool metric,
            # which gives a fast-cycle (no 5yr WAR maturation needed)
            # signal of draft-spending efficiency.
            if (draft_yr is not None
                    and today_yr - 5 <= int(draft_yr) <= today_yr - 2
                    and fv_raw is not None):
                m.setdefault("_draft_pool_active_fv_total", 0.0)
                m["_draft_pool_active_fv_total"] += float(fv_raw)
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

    # ── Per-org graduate aggregates (Farm Overhaul Steps 2 & 3) ──
    # Walk graduates ONCE to compute:
    #   - WAG sum + count (per-grad WAG via _grad_wag)
    #   - Total career WAR (across grads with a value)
    #   - Total bonus USD (across grads with bonus on file)
    # All grouped by graduate's CURRENT org (per user's choice).
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
        if not gp_org:
            continue
        # Build a minimal payload that _grad_wag can read. Pass through
        # the player's position so the rate-based WAG picks the right
        # pitcher/hitter expected-WAR-per-yr table.
        cw = (career_war or {}).get(gp.player_key) or {}
        fv_close_raw = (round(gp.points[-1].consensus_fv_raw, 2)
                        if gp.points else None)
        gp_bd = birth_dates.get(gp.player_key)
        gp_age = compute_age_decimal(gp_bd)
        gp_current_level = roster_level_by_key.get(gp.player_key)
        wag = _grad_wag({
            "career_war":   cw,
            "fv_close_raw": fv_close_raw,
            "fv_close":     gp.fv_close,
            "position":     gp.position,
            "career_stats": career_stats.get(gp.player_key, []),
            "transactions": transactions_by_player.get(gp.player_key, []),
            "age":          gp_age,
            "current_level": gp_current_level,
        })
        career_war_val = cw.get("career_war")
        gp_acq = (acquisitions or {}).get(gp.player_key, {}) or {}
        bonus_usd = gp_acq.get("bonus_usd")
        gp_method = gp_acq.get("method")  # "draft" | "international_fa" | "unknown"
        gp_is_pitcher = bool(gp.position
                             and gp.position.split("/")[0] in PITCHER_POS)
        gp_contract = (contracts_by_key or {}).get(gp.player_key) or {}
        gp_aav = gp_contract.get("aav_usd")

        bucket = grad_agg.setdefault(gp_org, {
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
        })
        # Boom/Bust classification for this graduate.
        career_rows = (career_stats or {}).get(gp.player_key, []) or []
        boom_label = _compute_boom_bust({
            "career_war":   cw,
            "fv_close_raw": fv_close_raw,
            "fv_close":     gp.fv_close,
            "career_stats": career_rows,
        })
        if boom_label == "boom":
            bucket["boom_count"] += 1
            bucket["settled_count"] += 1
        elif boom_label == "bust":
            bucket["bust_count"] += 1
            bucket["settled_count"] += 1
        elif boom_label == "settled":
            bucket["settled_count"] += 1
        if wag is not None:
            bucket["wag_sum"] += wag
            bucket["wag_count"] += 1
            # Acquisition-method split
            if gp_method == "international_fa":
                bucket["ifa_wag_sum"] += wag
                bucket["ifa_wag_count"] += 1
            elif gp_method == "draft":
                bucket["draft_wag_sum"] += wag
                bucket["draft_wag_count"] += 1
            # Position split for MLB Production branch
            if gp_is_pitcher:
                bucket["pit_wag_sum"] += wag
                bucket["pit_wag_count"] += 1
            else:
                bucket["hit_wag_sum"] += wag
                bucket["hit_wag_count"] += 1
        if career_war_val is not None:
            bucket["war_sum"] += float(career_war_val)
            bucket["war_count"] += 1
        # Tree v3 — cumulative WAR + WAR-per-year splits for IFA /
        # Hitter / Pitcher subsets. Per `career_war` payload shape:
        # `career_war` (total) + `war_per_yr` (career_war /
        # war_seasons_count). The 3-input composite at the leaf level
        # blends WAG + WAR/yr + cumulative WAR equally.
        war_per_yr = cw.get("war_per_yr")
        if career_war_val is not None or war_per_yr is not None:
            cval = float(career_war_val) if career_war_val is not None else None
            yval = float(war_per_yr)     if war_per_yr     is not None else None
            if gp_method == "international_fa":
                if cval is not None:
                    bucket["ifa_career_war_sum"]  += cval
                    bucket["ifa_career_war_count"] += 1
                if yval is not None:
                    bucket["ifa_war_per_yr_sum"]   += yval
                    bucket["ifa_war_per_yr_count"] += 1
            if gp_is_pitcher:
                if cval is not None:
                    bucket["pit_career_war_sum"]  += cval
                    bucket["pit_career_war_count"] += 1
                if yval is not None:
                    bucket["pit_war_per_yr_sum"]   += yval
                    bucket["pit_war_per_yr_count"] += 1
            else:
                if cval is not None:
                    bucket["hit_career_war_sum"]  += cval
                    bucket["hit_career_war_count"] += 1
                if yval is not None:
                    bucket["hit_war_per_yr_sum"]   += yval
                    bucket["hit_war_per_yr_count"] += 1
            # v31.5 — Sleeper development tracking. Grades each org's
            # ability to find ≥2 WAR/yr graduates from low-FV
            # (≤45 fv_open) acquisitions. Only fires for draft / IFA
            # method grads; trade / waiver acquisitions are excluded
            # since the org isn't doing initial scouting on those.
            _fv_open = getattr(gp, "fv_open", None)
            if _fv_open is not None and float(_fv_open) <= 45.0:
                if gp_method == "draft":
                    bucket["sleeper_low_fv_draft"] += 1
                    if yval is not None and float(yval) >= 2.0:
                        bucket["sleeper_hit_draft"] += 1
                elif gp_method == "international_fa":
                    bucket["sleeper_low_fv_ifa"] += 1
                    if yval is not None and float(yval) >= 2.0:
                        bucket["sleeper_hit_ifa"] += 1
            # v31.5 — Per-position-bucket production split. Routes
            # this grad's WAR/yr into the right C/INF/OF (hitter) or
            # SP/RP (pitcher) bucket so the Production leaves can
            # break their grade out by position type.
            if yval is not None:
                _grad_bucket = _pos_bucket_v2(gp.position)
                if _grad_bucket in ("C", "INF", "OF"):
                    bucket[f"hit_war_per_yr_sum_{_grad_bucket}"]   += yval
                    bucket[f"hit_war_per_yr_count_{_grad_bucket}"] += 1
                elif _grad_bucket in ("SP", "RP"):
                    bucket[f"pit_war_per_yr_sum_{_grad_bucket}"]   += yval
                    bucket[f"pit_war_per_yr_count_{_grad_bucket}"] += 1
            # v31.1 — Draft round-tier + IFA bonus-tier per-grad WAR/yr
            # accumulators. Only fires when WAR/yr is on file (graduate
            # has a non-empty MLB career). Tiers are mutually exclusive
            # within method, so a grad lands in exactly one tier bucket.
            if yval is not None and gp_method == "draft":
                _round = gp_acq.get("pick_round")
                if isinstance(_round, int) and _round >= 1:
                    if _round == 1:
                        bucket["draft_r1_war_per_yr_sum"]   += yval
                        bucket["draft_r1_war_per_yr_count"] += 1
                    elif _round <= 10:
                        bucket["draft_day1_war_per_yr_sum"]   += yval
                        bucket["draft_day1_war_per_yr_count"] += 1
                    else:
                        bucket["draft_late_war_per_yr_sum"]   += yval
                        bucket["draft_late_war_per_yr_count"] += 1
            if yval is not None and gp_method == "international_fa":
                _bonus = gp_acq.get("bonus_usd")
                _bonus_n = float(_bonus) if _bonus else 0.0
                if _bonus_n >= 2_000_000:
                    bucket["ifa_top_war_per_yr_sum"]   += yval
                    bucket["ifa_top_war_per_yr_count"] += 1
                elif _bonus_n >= 500_000:
                    bucket["ifa_mid_war_per_yr_sum"]   += yval
                    bucket["ifa_mid_war_per_yr_count"] += 1
                else:
                    bucket["ifa_lower_war_per_yr_sum"]   += yval
                    bucket["ifa_lower_war_per_yr_count"] += 1
        if bonus_usd is not None:
            bucket["bonus_sum"] += int(bonus_usd)
            bucket["bonus_count"] += 1
            # v31.5 — Channel split: route this grad's bonus + WAR
            # into the right channel bucket so the WAR/$M leaf can
            # surface a per-channel sub-leaf breakdown (Draft / IFA /
            # Other). career_war_val may be None — handled below by
            # checking before incrementing the WAR sum.
            _chan = "other"
            if gp_method == "draft":
                _chan = "draft"
            elif gp_method == "international_fa":
                _chan = "ifa"
            bucket[f"bonus_sum_{_chan}"] += int(bonus_usd)
            bucket[f"grad_count_{_chan}"] += 1
            if career_war_val is not None:
                bucket[f"war_sum_{_chan}"] += float(career_war_val)
        # Grad-Contract Surplus accumulator. 6-year amortization mirrors
        # the typical pre-FA cost-controlled window for a graduate; longer
        # extensions get credited yearly via aav_usd, not the bonus.
        if gp_aav and bonus_usd:
            try:
                surplus_yr = float(gp_aav) - (float(bonus_usd) / 6.0)
                bucket["contract_surplus_sum"]   += surplus_yr
                bucket["contract_surplus_count"] += 1
            except (TypeError, ValueError):
                pass
        # Pick-slot-adjusted draft value (v2 of Acquisitions/Draft).
        # Requires both a draft method AND a numeric pick_overall AND a
        # career_war on file. The delta is positive when the org
        # extracted more MLB value from that pick slot than the league
        # historically gets — credits late-round hits more than #1
        # overalls reaching the majors. Falls back silently when any
        # piece is missing (Spotrac-only graduates, IFA signings, etc.)
        if gp_method == "draft" and career_war_val is not None:
            slot_exp = _pick_slot_expected_war(gp_acq.get("pick_overall"))
            if slot_exp is not None:
                bucket["draft_pick_value_sum"]   += float(career_war_val) - slot_exp
                bucket["draft_pick_value_count"] += 1

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
            if gp_method:
                bucket["_method_grad_counts"][gp_method] = \
                    bucket["_method_grad_counts"].get(gp_method, 0) + 1
                _is_star = ((yval is not None and float(yval) >= _STAR_WAR_PER_YR_THRESHOLD)
                            or (season_peak >= _STAR_SEASON_WAR_THRESHOLD))
                if _is_star:
                    bucket["_method_star_counts"][gp_method] = \
                        bucket["_method_star_counts"].get(gp_method, 0) + 1
        # Draft-pool efficiency: grads drafted via the draft method,
        # tagged with their draft year + career WAR. The leaf-level
        # computation joins these to the per-year draft pool spend.
        if gp_method == "draft" and career_war_val is not None:
            dy = gp_acq.get("year")
            if dy is not None:
                bucket["_draft_pool_grads"].append({
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
        if gp_method == "international_fa" and career_war_val is not None:
            sy = gp_acq.get("year")
            if sy is not None:
                bucket["_ifa_grads"].append({
                    "signed_year": int(sy),
                    "bonus_usd":   int(bonus_usd) if bonus_usd else 0,
                    "career_war":  float(career_war_val),
                })

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
        # have both signing bonus AND career WAR on file. Requires the
        # bonus union (we use a separate bonus_count gate so a free
        # agent without a published bonus doesn't drag the ratio down).
        bonus_sum = gagg.get("bonus_sum") or 0
        war_sum = gagg.get("war_sum") or 0.0
        # v40 — total realized graduate WAR (raw MLB production) exposed for the
        # farm tiebreaker score. Sum of career bWAR across the org's graduates.
        m["_grad_war_total"] = round(war_sum, 2)
        m["financial_roi"] = {
            "war_per_million": (round(war_sum / (bonus_sum / 1_000_000), 3)
                                if bonus_sum >= 1_000_000 else None),
            "total_career_war":  round(war_sum, 2),
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
                    raw_b = 100 + 10 * z_b
                    stretched_b = _stretch_composite(raw_b)
                    _entry["tool_dev"]["per_tool_dvm_plus_by_bucket"] \
                        .setdefault(bucket, {})[grp_name] = int(round(stretched_b))

    # Composite ToolDvM+ — position-bucket importance-weighted blend of the
    # per-tool DvM+ values (see `_bucket_weighted_tool_dvm`). Rewards orgs
    # that develop the tools that MATTER for a position over ones that pad
    # the average with off-position gains. The internal storage key stays
    # `tools_dvm_plus`; the front-end label is "ToolDvM+".
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
    org_fv_history = _build_org_fv_history(
        actives + grads + inactives, _filter_real_trades, trades_by_player,
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
    hitter_fv_history  = _build_org_fv_history(hitter_players,  _filter_real_trades, trades_by_player)
    pitcher_fv_history = _build_org_fv_history(pitcher_players, _filter_real_trades, trades_by_player)
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
        for pt in (p.points or []):
            if pt.consensus_fv_raw is not None:
                hist.append((pt.snapshot_date, float(pt.consensus_fv_raw)))
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

    # ── Farm report card ────────────────────────────────────────────────────
    # Four raw component scores per org, each then rescaled to a 0-100 band
    # across the 30 orgs and blended into a single farm_score. The blend
    # weights are FARM_WEIGHT_* above. Each component also gets a letter
    # grade (its rank's bucket); the overall letter is the bucket the
    # blended farm_score lands in.
    today_iso = date.today()
    for entry in org_summary:
        entry["top_end_points"] = _top_end_points(entry["prospects"])
        entry["depth_points"]   = _depth_points(entry["prospects"])
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
        entry["trajectory_score"] = round(
            0.60 * (_T.get("6y") or 0)
            + 0.30 * (_T.get("3y") or 0)
            + 0.10 * (_T.get("1y") or 0),
            3,
        )
        entry["grad_pipeline_score"] = _grad_pipeline_score(
            entry["fv_events"], as_of=today_iso,
        )

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

    # v28 — Final blend pass. 70% cohort-restricted Overall DvM+ +
    # 30% tool-grade-based DvM+. Missing-signal: if one side is
    # absent the other takes 100%. Headline `dvm_plus` (which feeds
    # LEAF_SPECS letter grading) anchors on the 6y window — the
    # principal sustained-development signal. `dvm_plus_by_window`
    # exposes the full {1y, 3y, 6y} blend dict for window-reactive
    # frontend display.
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
            return 0.30
        gap = overall - tool
        if gap < 15:
            return 0.30
        if gap >= 35:
            return 0.60
        return 0.40 + (gap - 15) * 0.01

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

    # v30.7 — 3-way DvM+ blend. Adds StatcastDvM+ as a 20% leg
    # alongside the existing FVDvM+ (50%) + ToolDvM+ (30%). The
    # FV+Tool sub-blend keeps its adaptive over-grade penalty (when
    # FV outruns Tool by ≥15, Tool's share within its 30% slice ramps
    # up to absorb the difference). Statcast layers on top at a
    # fixed 20%.
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
            tool_w_total = 0.75 * tool_w_in_slice
            fv_w_total   = 0.75 - tool_w_total
            return int(round(fv_w_total * fv_dvm
                             + tool_w_total * tool_dvm
                             + 0.25 * sc_dvm))
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
        entry["tree"]["dev_hitter"]["dvm_plus"]            = hit_by_window.get("6y")
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
        entry["tree"]["dev_pitcher"]["dvm_plus"]           = pit_by_window.get("6y")
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
            ("pick_value", lambda e: ((e["tree"]["acq_draft"] or {}).get("pick_value_mean")
                                      or (e["tree"]["acq_draft"] or {}).get("wag_mean"))),
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
        "dev_hitter":  [
            ("six_y_dvm", lambda e: (e.get("dvm_plus") or {}).get("6y")),
            ("six_y_dvm_b", lambda e: (e.get("dvm_plus") or {}).get("6y")),  # double-count = 2/3 weight
            ("dvm_plus", lambda e: (e["tree"]["dev_hitter"]  or {}).get("dvm_plus")),
        ],
        "dev_pitcher": [
            ("six_y_dvm", lambda e: (e.get("dvm_plus") or {}).get("6y")),
            ("six_y_dvm_b", lambda e: (e.get("dvm_plus") or {}).get("6y")),
            ("dvm_plus", lambda e: (e["tree"]["dev_pitcher"] or {}).get("dvm_plus")),
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
        for _, getter in specs:
            raw = [getter(e) for e in org_summary]
            sub_z_lists.append(_zscore_to_100(raw, higher_is_better=True))
        # Per-org leaf score = mean of present sub-input z-scores.
        per_org_scores: list[float | None] = []
        for i in range(len(org_summary)):
            present = [z[i] for z in sub_z_lists if z[i] is not None]
            per_org_scores.append(round(sum(present) / len(present), 1)
                                  if present else None)
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
        entry["farm_score"] = _stretch_composite(round(composite, 1), factor=1.20)
        # Back-compat: legacy field names (acquisitions_score,
        # transactions_score) resolve to the merged Acquisition Strategy
        # value so any UI reading the old keys still gets a number.
        entry["acquisitions_score"] = entry.get("acquisition_strategy_score")
        entry["transactions_score"] = entry.get("acquisition_strategy_score")

    # ── v40 — Continuous TIEBREAKER score ─────────────────────────────────
    # Differentiates farms that land on the same letter grade (coarse grades
    # collapse real value gaps). A normalized z-blend across the 30 orgs of the
    # three value dimensions, anchored DvM+-style (100 + 10·z):
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
    _dvm_z  = _farm_z([(e.get("dvm_plus") or {}).get("6y") for e in org_summary])
    _gwar_z = _farm_z([e.get("_grad_war_total") for e in org_summary])
    _TB_W = {"surplus": 0.40, "dvm6y": 0.25, "grad_war": 0.35}
    for i, entry in enumerate(org_summary):
        _blend = (_TB_W["surplus"] * _surp_z[i] + _TB_W["dvm6y"] * _dvm_z[i]
                  + _TB_W["grad_war"] * _gwar_z[i])
        entry["farm_tiebreaker"] = {
            "score": round(100 + 10 * _blend, 1),
            "weights": _TB_W,
            "components": {
                "surplus_z":  round(_surp_z[i], 2),
                "dvm6y_z":    round(_dvm_z[i], 2),
                "grad_war_z": round(_gwar_z[i], 2),
            },
            "inputs": {
                "total_surplus_mm": round(entry.get("_active_surplus_net_mm") or 0.0, 1),
                "dvm_plus_6y":      (entry.get("dvm_plus") or {}).get("6y"),
                "grad_war_total":   entry.get("_grad_war_total"),
            },
        }
    # Continuous "true rank" 1–30 by the tiebreaker score (finer than the letter
    # grade); the letter grade still comes from farm_score's rank bucket below.
    _tb_order = sorted(range(len(org_summary)),
                       key=lambda i: -(org_summary[i]["farm_tiebreaker"]["score"]))
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
    _grade_sub_leaf_across_league("tx_trades", "Unweighted Δ")

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
    for win in ("1y", "3y", "6y"):
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
    _WINDOWS = {"1y": 1, "3y": 3, "6y": 6}
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
                        vals_w.append(float(wpy))
                org_mean = sum(vals_w) / len(vals_w) if len(vals_w) >= 3 else None
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
                        vals_w.append(float(cw))
                # Use career WAR mean as the in-window signal (WAR/yr
                # not stored on _draft_pool_grads / _ifa_grads).
                org_mean = sum(vals_w) / len(vals_w) if len(vals_w) >= 3 else None
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
    # Pop the scratch fields so they don't bloat the exported JSON.
    for entry in org_summary:
        entry.pop("_top_grads_raw", None)
        entry.pop("_draft_pool_grads_raw", None)
        entry.pop("_ifa_grads_raw", None)
    # ────────────────────────────────────────────────────────────────────────

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

    active_payload = [_serialize(p) for p in actives]
    inactive_payload = [_serialize(p) for p in inactives]
    graduate_payload = [_serialize(p) for p in grads]
    # v38 — Item-6: stamp the per-prospect $DvM+ (computed in the league pre-pass
    # above) onto each active payload so the farm financial detail can surface it
    # alongside the prospect's surplus value.
    for _pl in active_payload:
        _pl["dollar_dvm_plus"] = _dollar_dvm_by_key.get(_pl.get("player_key"))
    _live_ranked = []
    for _pl in active_payload:
        _base = _safe_float(_pl.get("fv_close_raw"))
        if _base is None:
            _base = _safe_float(_pl.get("fv_close"))
        _delta = _safe_float(((_pl.get("live_signal") or {}).get("delta")))
        if _base is None:
            continue
        _live_score = round(_base + (_delta or 0.0), 2)
        _pl["live_score"] = _live_score
        _live_ranked.append(_pl)
    _live_ranked.sort(key=lambda _pl: (
        -(_safe_float(_pl.get("live_score")) or -999),
        -(_safe_float(_pl.get("fv_close_raw")) or -999),
        _pl.get("player_name") or "",
    ))
    for _idx, _pl in enumerate(_live_ranked, start=1):
        _pl["live_overall_rank"] = _idx
        if _pl.get("overall_rank") is not None:
            _pl["live_rank_delta"] = int(_pl["overall_rank"]) - _idx
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
    # qualify league-wide. v29 — Statcast+ ≥ 115 also passes the perf
    # gate now (see _compute_breakout_flag).
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

    # Split the export into a boot-critical file plus three lazy-loaded
    # sidecars so a first-paint download doesn't drag along ~40MB of
    # graduate / inactive / affiliate-roster data that the user typically
    # doesn't need until they navigate to those tabs.
    #
    #   timeseries.json   — meta + active players + spotlights + org
    #                       summaries + level/trajectory norms (boot path)
    #   graduates.json    — graduate-player payloads
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
    scout_reports_sidecar: dict[str, dict[str, list[dict]]] = {}
    def _harvest_and_strip_reports(player_payload):
        pkey = player_payload.get("player_key")
        # Walk in date order, collecting unique report texts per source.
        by_src_seen_hashes: dict[str, set[str]] = {}
        by_src_entries: dict[str, list[dict]] = {}
        for pt in (player_payload.get("points") or []):
            for src, info in (pt.get("per_source") or {}).items():
                tools = (info or {}).get("tools") or {}
                ex = tools.get("_extras") or {}
                rpt = ex.get("report")
                if rpt:
                    h = hashlib.sha1(rpt.strip().encode("utf-8")).hexdigest()[:12]
                    seen = by_src_seen_hashes.setdefault(src, set())
                    if h not in seen:
                        seen.add(h)
                        by_src_entries.setdefault(src, []).append({
                            "date": pt.get("snapshot_date"),
                            "label": pt.get("interval_label"),
                            "text": rpt,
                            "hash": h,
                        })
                    # Strip the inline report so it doesn't bloat boot.
                    ex["report"] = None
        # Reverse each list so newest is first (the walk was oldest-first).
        if by_src_entries:
            for src in by_src_entries:
                by_src_entries[src].reverse()
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
            captured["top"] = top_plot
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
                    level_plots[lvl] = rp
                    row["pitch_plot"] = {}
            if level_plots:
                captured["level_splits"] = level_plots
        if captured and pkey:
            pitch_plots_sidecar[pkey] = captured
    for p in active_payload:
        _harvest_and_strip_pitch_plots(p)
    for p in graduate_payload:
        _harvest_and_strip_pitch_plots(p)
    for p in inactive_payload:
        _harvest_and_strip_pitch_plots(p)

    boot = {
        "generated_at": _utcnow_iso() + "Z",
        "run": latest_run_summary(),
        "total_tracked": len(active_payload) + len(graduate_payload) + len(inactive_payload),
        "active_count": len(actives),
        "inactive_count": len(inactives),
        "debut_count": len(grads),
        "inactive_cutoff": cutoff.isoformat(),
        "prospect_savant_count": savant_matched,
        "players":    active_payload,
        "spotlights": spotlight_payload,
        "org_summary": org_summary,
        "farm_trajectory_means": farm_trajectory_means,
        "farm_trajectory_stdevs": farm_trajectory_stdevs,
        # v28 — cohort-restricted (hitter / pitcher) league means + stdevs
        # per window. Mirror of the org-wide pair above; lets the frontend
        # render a cohort-only growth chart with the same baseline-removal
        # math used for the all-prospects chart.
        "farm_hitter_trajectory_means":   hitter_traj_means,
        "farm_hitter_trajectory_stdevs":  hitter_traj_stdevs,
        "farm_pitcher_trajectory_means":  pitcher_traj_means,
        "farm_pitcher_trajectory_stdevs": pitcher_traj_stdevs,
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
            "inactive":           "inactive.json",
            "rosters_by_org":     "rosters_by_org.json",
            "scout_reports":      "scout_reports.json",
            "mlb_trade_players":  "mlb_trade_players.json",
            # v31.12 — pitch_plot raw coordinates moved out of boot.
            # Lazy-loaded by the player-detail pitch chart only.
            "pitch_plots":        "pitch_plots.json",
        },
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
        def _dump(obj, path):
            path.write_bytes(_orjson.dumps(obj, option=_opts))
    except ImportError:
        _compact = {"separators": (",", ":")}
        def _dump(obj, path):
            path.write_text(json.dumps(obj, **_compact))
    _dump(boot, out_path)
    _dump(graduate_payload, out_dir / "debuts.json")
    _dump(inactive_payload, out_dir / "inactive.json")
    _dump(rosters_by_org, out_dir / "rosters_by_org.json")
    _dump(scout_reports_sidecar, out_dir / "scout_reports.json")
    # v31.8c — mlb_trade_players sidecar (lazy-loaded when the
    # Transactions tab opens, not part of initial boot).
    _dump(load_mlb_trade_players(), out_dir / "mlb_trade_players.json")
    # v31.12 — pitch_plots sidecar (lazy-loaded only when the player
    # detail page opens for a pitcher with tracked pitch data).
    _dump(pitch_plots_sidecar, out_dir / "pitch_plots.json")
    return out_path


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
                entry = pp[pkey]
                if entry.get("top"):
                    sc["pitch_plot"] = entry["top"]
                level_map = entry.get("level_splits") or {}
                if level_map:
                    for row in sc.get("level_splits") or []:
                        lvl = row.get("level") or "_"
                        if lvl in level_map:
                            row["pitch_plot"] = level_map[lvl]
    return payload

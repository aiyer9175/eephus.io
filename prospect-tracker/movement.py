"""De-noised prospect movement engine.

The legacy movement signals (consensus.stock_movement, build_site's
_latest_fv_change) and the spotlights bucket engine (spotlights.compute_movement)
all conflate "a source published an update" with "the prospect moved." The
headline up/down indicator keyed off `consensus_fv` — but consensus_fv is a
forward-filled, Bayesian-shrunk aggregate over a *changing* panel of sources, so
it shifts whenever:

  * the SET of contributing sources changes (a new source drops in, or an old
    one goes stale / drops the player off its list), or
  * a single outlier source re-grades, even when the field disagrees.

Neither means the prospect actually moved. This module measures GENUINE
directional movement by comparing only the sources that graded the player at
BOTH endpoints of the most-recent change (same-source delta), with on-field
performance as the backup signal and a confidence gate that keeps thin-sample
noise off the board.

Primary signal  = same-source scouting-consensus move ("since last real change").
Backup signal   = on-field performance (reuses spotlights._perf_delta /
                  _skills_delta).
Output `stock`  = a backward-compatible SUPERSET of compute_movement's shape, so
                  every existing frontend consumer keeps working; `delta` now
                  means a real same-source FV move in grade units.

spotlights.compute_movement is left UNTOUCHED — it still drives the curatorial
"Top Movers" buckets (where pedigree / list-jump flavor is intentional).
"""

from __future__ import annotations

from datetime import date
from statistics import mean

# Pure helpers reused from the spotlights engine. spotlights does NOT import
# this module (verified), so there is no import cycle.
from spotlights import (
    MAX_DRIVERS_PER_CARD,
    _normalize_driver,
    _perf_delta,
    _skills_delta,
)

# Plateau tolerance: same-source moves below this (grade units) are treated as
# "no change" when walking back to the last real step.
_EPS = 0.5

# Source display names — mirrors prospx/index.html SOURCE_LABELS. Both the
# data-layer key (`baseballamerica`) and the frontend key (`baseball_america`)
# are covered so driver strings read the same as the rest of the site.
_SOURCE_LABELS = {
    "fangraphs": "FanGraphs",
    "espn": "ESPN",
    "just_baseball": "Just Baseball",
    "tjstats": "TJStats",
    "baseballamerica": "Baseball America",
    "baseball_america": "Baseball America",
    "mlb_pipeline": "MLB Pipeline",
    "mlb_pipeline_international": "MLB Pipeline Intl",
    "the_athletic": "The Athletic",
}


def _src_label(src: str) -> str:
    return _SOURCE_LABELS.get(src) or str(src).replace("_", " ").title()


def xfv_movement(series: list) -> dict | None:
    """Movement from the eFV trajectory (xfv_history): the eFV grade's change since its last
    real step (dead-band _EPS). This is the PRIMARY movement signal (owner: movement = eFV
    delta); the consensus same-source step is the fallback when a player has no eFV history.
    Returns the headline-override fields (same direction enum + sign convention as
    compute_genuine_movement) or None when there is no usable series. `series` = [(date, grade)]."""
    pts = sorted(((d, float(x)) for d, x in (series or []) if d and x is not None),
                 key=lambda t: t[0])
    if len(pts) < 2:
        return None
    latest_d, latest = pts[-1]
    # Walk back to the last point whose eFV differs from the latest by >= the plateau EPS.
    anchor_d, anchor = pts[0]
    for d, x in reversed(pts[:-1]):
        if abs(latest - x) >= _EPS:
            anchor_d, anchor = d, x
            break
    delta = round(latest - anchor, 2)
    direction = "up" if delta >= _EPS else "down" if delta <= -_EPS else "flat"
    return {
        "direction": direction,
        "delta": delta,
        "basis": "xfv",
        "strength": round(min(1.0, abs(delta) / 5.0), 2),
        "from_label": f"eFV {round(anchor, 1)}",
        "to_label": f"eFV {round(latest, 1)}",
        "from_date": anchor_d,
        "to_date": latest_d,
    }


def _explicit_fv_map(pt: dict) -> dict:
    """Source -> published FV at this point, EXPLICIT grades only.

    Rank-only sources (Baseball America, early ESPN) carry fv_published=None and
    are skipped — they can never contribute to a same-source FV delta. per_source
    is forward-filled by build_timeseries, so a source's value only changes
    between points when that source actually re-published a grade."""
    out = {}
    for src, row in (pt.get("per_source") or {}).items():
        fv = row.get("fv_published")
        if fv is None:
            continue
        try:
            out[src] = float(fv)
        except (TypeError, ValueError):
            continue
    return out


def _ss_delta(a: dict, b: dict):
    """Same-source mean FV delta of point `a` relative to point `b`.

    Returns (mean_delta, common_sources, per_source_delta). mean_delta is None
    when no source published an explicit grade at BOTH points — the
    insufficient-evidence path (never fabricate a number)."""
    a_map, b_map = _explicit_fv_map(a), _explicit_fv_map(b)
    common = sorted(set(a_map) & set(b_map))
    if not common:
        return None, [], {}
    per = {s: a_map[s] - b_map[s] for s in common}
    return mean(per.values()), common, per


def same_source_change_anchor(points: list) -> dict | None:
    """Find the most recent same-source consensus STEP and report it.

    Walks back from the latest point. The current "plateau" is the run of
    consecutive earlier points whose same-source level equals the latest's
    (|delta| < _EPS). The step that created the plateau is the move we report:
    its magnitude is the latest level minus the pre-plateau level, measured only
    over sources present at both ends — so panel-composition changes and
    lone-outlier re-grades cancel out.

    Returns None when there are <2 dated points. Returns basis="insufficient"
    when no genuine same-source step exists (flat history, or only composition
    changes)."""
    pts = [pt for pt in (points or []) if pt.get("snapshot_date")]
    if len(pts) < 2:
        return None
    anchor = pts[-1]
    plateau_start = anchor  # earliest point still at the current level

    for pt in reversed(pts[:-1]):
        d, _common, _per = _ss_delta(anchor, pt)
        if d is None:
            # No overlap with the anchor's explicit-FV sources at this prior
            # (none of them had published yet). Earlier points overlap even
            # less — stop. The current level has no measurable origin.
            break
        if abs(d) < _EPS:
            plateau_start = pt  # still the same level; plateau continues
            continue
        # `pt` sits at a different level — the step happened between it and the
        # plateau start. Report anchor (current level) vs this pre-step point.
        delta, common, per = _ss_delta(anchor, pt)
        a_map = _explicit_fv_map(anchor)
        b_map = _explicit_fv_map(pt)
        return {
            "basis": "same_source",
            "delta": round(delta, 2),
            "common": common,
            "per_src_delta": per,
            "from_fv": {s: b_map[s] for s in common},
            "to_fv": {s: a_map[s] for s in common},
            "n_up": sum(1 for v in per.values() if v > 0),
            "n_down": sum(1 for v in per.values() if v < 0),
            "from_date": pt.get("snapshot_date"),
            "to_date": plateau_start.get("snapshot_date"),
            "from_label": pt.get("consensus_fv_label"),
            "to_label": anchor.get("consensus_fv_label"),
            "spread": anchor.get("fv_spread"),
        }

    # Never stepped: flat across all overlapping history, or only the panel
    # composition changed.
    return {"basis": "insufficient", "delta": None, "common": [], "per_src_delta": {}}


def _is_panel_update(anchor_pt: dict, prior_pt: dict) -> bool:
    """True when the consensus label moved between the two points but the move
    was driven by the panel changing (a source entering / dropping off), NOT by
    any source re-grading. Used only to explain a flat call; such moves never
    reach the wire."""
    if (anchor_pt.get("consensus_fv_label")) == (prior_pt.get("consensus_fv_label")):
        return False
    d, _common, _per = _ss_delta(anchor_pt, prior_pt)
    ss_flat = d is None or abs(d) < _EPS
    a_src = set(anchor_pt.get("sources_contributing") or [])
    p_src = set(prior_pt.get("sources_contributing") or [])
    dropped = any((row or {}).get("dropped_off")
                  for row in (anchor_pt.get("per_source") or {}).values())
    return ss_flat and (a_src != p_src or dropped)


def _source_drivers(ss: dict) -> list:
    """Driver chips naming the sources that actually moved, e.g.
    'FanGraphs & MLB Pipeline raised FV +5'. from->to per source in the
    tooltip."""
    per = ss.get("per_src_delta") or {}
    from_fv = ss.get("from_fv") or {}
    to_fv = ss.get("to_fv") or {}
    out = []
    for grp_sign, verb, valence in ((1, "raised", "good"), (-1, "cut", "bad")):
        grp = sorted((s, v) for s, v in per.items() if (v > 0) == (grp_sign > 0) and v != 0)
        if not grp:
            continue
        names = " & ".join(_src_label(s) for s, _ in grp)
        mag = abs(mean([v for _, v in grp]))
        sign = "+" if grp_sign > 0 else "-"
        tip = "; ".join(
            f"{_src_label(s)} {from_fv.get(s, '?'):g}->{to_fv.get(s, '?'):g}"
            if s in from_fv and s in to_fv else f"{_src_label(s)} {v:+g}"
            for s, v in grp)
        out.append({"label": f"{names} {verb} FV {sign}{mag:.0f}",
                    "valence": valence, "tooltip": tip})
    return out


def compute_genuine_movement(p: dict) -> dict:
    """De-noised movement signal. Backward-compatible superset of
    spotlights.compute_movement's `stock` dict.

    Output keys:
      direction : up_strong|up|flat|down|down_strong|debuted  (frontend enum —
                  the internal "insufficient" basis serializes as "flat")
      delta     : same-source FV move in grade units; None when perf-only
      basis     : same_source|performance|panel_update|insufficient
      strength  : 0..1 (|delta|/5)
      confidence: high|medium|low
      drivers   : [{label, valence, tooltip}] — genuine causes only
      from_label/to_label/from_date/to_date
      n_sources_up/n_sources_down, perf_delta/skills_delta
    """
    pts = [pt for pt in (p.get("points") or []) if pt.get("snapshot_date")]
    latest = pts[-1] if pts else {}
    prior_pt = pts[-2] if len(pts) >= 2 else latest

    # debuted short-circuit (matches both legacy engines).
    if (p.get("status") or "") == "debuted":
        return {
            "direction": "debuted", "delta": 0.0, "basis": "debuted",
            "strength": 0.0, "confidence": "low",
            "from_label": " - ", "to_label": " - ", "from_date": "", "to_date": "",
            "perf_delta": None, "skills_delta": None,
            "n_sources_up": 0, "n_sources_down": 0, "drivers": [],
        }

    perf, perf_driver = _perf_delta(p)
    skills, skills_drv = _skills_delta(p)
    is_pitcher = bool((p.get("statline") or {}).get("is_pitcher"))
    # Mirror spotlights._classify_movement bars.
    perf_riser_bar = 0.080 if is_pitcher else 0.100
    perf_faller_bar = -0.30 if is_pitcher else -0.080
    perf_is_riser = perf is not None and perf >= perf_riser_bar
    perf_is_faller = perf is not None and perf <= perf_faller_bar

    # Confidence from sample depth. A genuine same-source move backed by >=2
    # contributing sources is high confidence even under mild shrinkage; a
    # singleton (one FV observation ever) can never be a board mover.
    n_instances = p.get("fv_total_instances") or 0
    shrink_w = latest.get("shrinkage_weight", 1.0)
    shrink_w = 1.0 if shrink_w is None else shrink_w
    n_contrib = len(latest.get("sources_contributing") or [])
    if n_instances <= 1:
        confidence = "low"
    elif n_contrib >= 2 and shrink_w >= 1.0:
        confidence = "high"
    elif n_contrib >= 2 or shrink_w >= 1.0:
        confidence = "medium"
    else:
        confidence = "low"

    ss = same_source_change_anchor(pts) or {"basis": "insufficient", "delta": None}

    direction = "flat"
    basis = ss.get("basis", "insufficient")
    delta = None
    n_up = ss.get("n_up", 0)
    n_down = ss.get("n_down", 0)
    from_label = prior_pt.get("consensus_fv_label") or " - "
    to_label = latest.get("consensus_fv_label") or " - "
    from_date = prior_pt.get("snapshot_date") or ""
    to_date = latest.get("snapshot_date") or ""
    drivers: list = []

    if basis == "same_source":
        delta = ss["delta"]
        from_label = ss.get("from_label") or from_label
        to_label = ss.get("to_label") or to_label
        from_date = ss.get("from_date") or from_date
        to_date = ss.get("to_date") or to_date
        spread = ss.get("spread") or 0.0
        # Dead-band widens with cross-source disagreement (1.5 = stock_movement
        # entry bar). Strong tiers (>=4) require >=2 sources moving together; a
        # lone source needs on-field performance to corroborate (the `n_up>=2 or
        # perf_is_*` OR keeps single-outlier re-grades from firing on their own).
        deadband = 1.5 + 0.5 * (spread / 5.0)
        if delta >= 4 and n_up >= 2:
            direction = "up_strong"
        elif delta >= deadband and (n_up >= 2 or perf_is_riser):
            direction = "up"
        elif delta <= -4 and n_down >= 2:
            direction = "down_strong"
        elif delta <= -deadband and (n_down >= 2 or perf_is_faller):
            direction = "down"
        else:
            direction = "flat"
        drivers.extend(_source_drivers(ss))
        if perf_driver:
            drivers.append(perf_driver)
        drivers.extend(skills_drv)
        if direction == "flat" and spread >= 5:
            drivers.append({"label": f"sources split (spread {spread:g})",
                            "valence": "neutral",
                            "tooltip": "Sources disagree on FV — no clear move"})
    else:
        # No genuine same-source step. Fall back to on-field performance, then
        # explain the flat call (panel update vs building sample).
        panel = len(pts) >= 2 and _is_panel_update(latest, prior_pt)
        if n_instances <= 1:
            direction, basis = "flat", "insufficient"
            drivers.append({"label": "building sample (1 grade)", "valence": "neutral",
                            "tooltip": "Single FV observation — not enough to call a move"})
        elif perf_is_riser:
            direction, basis = "up", "performance"
            if perf_driver:
                drivers.append(perf_driver)
            drivers.extend(skills_drv)
        elif perf_is_faller:
            direction, basis = "down", "performance"
            if perf_driver:
                drivers.append(perf_driver)
            drivers.extend(skills_drv)
        elif panel:
            direction, basis = "flat", "panel_update"
            n_src = len(latest.get("sources_contributing") or [])
            drivers.append({"label": f"panel update - {n_src} source{'' if n_src == 1 else 's'}",
                            "valence": "neutral",
                            "tooltip": "Consensus shifted because the source panel changed, "
                                       "not because any source re-graded the player"})
        else:
            direction, basis = "flat", "insufficient"
            if perf_driver:
                drivers.append(perf_driver)
        # Performance-only conclusions can't be high confidence — no scouting
        # corroboration yet.
        if basis == "performance" and confidence == "high":
            confidence = "medium"

    # Hard gate: a one-grade-ever prospect is never a board mover.
    if n_instances <= 1:
        direction = "flat"

    strength = round(min(1.0, abs(delta) / 5.0), 2) if delta is not None else 0.0

    is_pitcher_ctx = is_pitcher
    normalized = [_normalize_driver(d, is_pitcher_context=is_pitcher_ctx) for d in drivers]
    return {
        "direction": direction,
        "delta": round(delta, 2) if delta is not None else None,
        "basis": basis,
        "strength": strength,
        "confidence": confidence,
        "from_label": from_label,
        "to_label": to_label,
        "from_date": from_date,
        "to_date": to_date,
        "perf_delta": round(perf, 3) if perf is not None else None,
        "skills_delta": round(skills, 2) if skills is not None else None,
        "n_sources_up": n_up,
        "n_sources_down": n_down,
        "drivers": normalized[:MAX_DRIVERS_PER_CARD],
    }


# ===========================================================================
# Farm-system RANK movement (an org climbing / falling in the 30-team farm
# rankings). Same event-based "since last real change" philosophy as the
# prospect engine, but the de-noising is simpler: a farm has exactly ONE
# "source" — our composite farm_score — so there is no changing-panel noise to
# cancel. The only noise is month-to-month rank churn driven by OTHER teams
# moving (the rank is relative), which a plateau tolerance + a dead-band on the
# reported move reject. Mirrors compute_genuine_movement's output contract: a
# `stock`-like dict whose `direction` serializes to the frontend enum and whose
# `delta` is the number of rank spots moved (positive = climbed toward #1).
# ===========================================================================

# Exact-rank plateau: only identical ranks count as "the same level" when
# walking back, so a single-spot wobble registers as a step whose magnitude the
# dead-band then judges. (Comparing each prior point to the anchor — not its
# neighbour — means a wider tolerance could never reach past the anchor's
# immediate neighbourhood anyway, so 0 is both the cleanest and the most honest
# choice.)
_FARM_PLATEAU_EPS = 0
# Dead-band: a farm has to move at least this many spots to register a
# direction. One spot is almost always relative churn (another org passed it),
# not a genuine move; two-plus is a real shift in the standings.
_FARM_RANK_DEADBAND = 2
# Strong tier: a multi-spot leap in a 30-team ranking is a marquee move.
_FARM_RANK_STRONG = 5


def _farm_flat(history_pts: list, basis: str, confidence: str) -> dict:
    """Flat / insufficient result. Carries the endpoints (when known) so the
    chip can still say "held at #N" if it wants to."""
    first = history_pts[0] if history_pts else {}
    last = history_pts[-1] if history_pts else {}
    return {
        "direction": "flat",
        "delta": None if basis == "insufficient" else 0,
        "basis": basis,
        "confidence": confidence,
        "from_rank": first.get("farm_rank"),
        "to_rank": last.get("farm_rank"),
        "from_score": first.get("farm_score"),
        "to_score": last.get("farm_score"),
        "score_delta": None,
        "from_date": first.get("snapshot_date", ""),
        "to_date": last.get("snapshot_date", ""),
        "n_points": len(history_pts),
    }


def compute_farm_movement(history: list) -> dict:
    """De-noised farm-system RANK movement for one org.

    `history` is that org's farm_rank_history rows — dicts carrying
    `snapshot_date`, `farm_rank`, `farm_score` — typically loaded oldest-first
    via storage.load_farm_rank_history, with the current run's freshly-computed
    (rank, score) appended as the final point (the anchor). Out-of-order or
    duplicate-date input is tolerated (sorted + de-duped here).

    Walks back from the anchor to the most recent genuine rank STEP: the run of
    consecutive earlier points at the anchor's exact rank is the current
    plateau; the step that created it (anchor rank vs the first earlier point at
    a different rank) is the move reported. A move smaller than the dead-band is
    reported as flat.

    Output keys (a superset compatible with the prospect `stock` shape):
      direction : up_strong|up|flat|down|down_strong
      delta     : rank spots moved (+ = climbed toward #1); None if insufficient
      basis     : rank_step|held|insufficient
      from_rank/to_rank, from_score/to_score, score_delta
      from_date/to_date  : bracket the transition that produced the current level
      confidence: high|medium|low
      n_points  : dated points considered
    """
    # Keep the last row per date (a same-day re-run appends a fresh anchor),
    # drop undated / rankless rows, then sort oldest-first.
    by_date: dict = {}
    for h in (history or []):
        if not isinstance(h, dict):
            continue
        d = h.get("snapshot_date")
        if not d or h.get("farm_rank") is None:
            continue
        by_date[d] = h
    pts = [by_date[d] for d in sorted(by_date)]

    if len(pts) < 2:
        # Singleton (or empty): no measurable origin — forced flat, exactly like
        # the prospect engine gates one-grade-ever players. Expected during the
        # warm-up runs before history accrues.
        return _farm_flat(pts, "insufficient", "low")

    anchor = pts[-1]
    a_rank = int(anchor["farm_rank"])
    plateau_start = anchor          # earliest point still at the current rank
    step_pt = None                  # the point just before the current level

    for pt in reversed(pts[:-1]):
        r = int(pt["farm_rank"])
        if abs(r - a_rank) <= _FARM_PLATEAU_EPS:
            plateau_start = pt
            continue
        step_pt = pt
        break

    # Confidence scales with how much history backs the call.
    confidence = "high" if len(pts) >= 3 else "medium"

    if step_pt is None:
        # Rank held at the same value across all of history — genuinely flat.
        return _farm_flat(pts, "held", confidence)

    # +ve delta = climbed (rank number went DOWN toward #1).
    delta = int(step_pt["farm_rank"]) - a_rank
    if delta >= _FARM_RANK_STRONG:
        direction = "up_strong"
    elif delta >= _FARM_RANK_DEADBAND:
        direction = "up"
    elif delta <= -_FARM_RANK_STRONG:
        direction = "down_strong"
    elif delta <= -_FARM_RANK_DEADBAND:
        direction = "down"
    else:
        direction = "flat"

    from_score = step_pt.get("farm_score")
    to_score = anchor.get("farm_score")
    score_delta = (round(to_score - from_score, 2)
                   if from_score is not None and to_score is not None else None)

    return {
        "direction": direction,
        "delta": delta,
        "basis": "rank_step",
        "confidence": confidence,
        "from_rank": int(step_pt["farm_rank"]),
        "to_rank": a_rank,
        "from_score": from_score,
        "to_score": to_score,
        "score_delta": score_delta,
        # from_date = the pre-step point; to_date = when the current level was
        # first reached (the plateau start). Together they bracket the move.
        "from_date": step_pt.get("snapshot_date", ""),
        "to_date": plateau_start.get("snapshot_date", ""),
        "n_points": len(pts),
    }


# ===========================================================================
# Per-prospect BOARD-RANK movement (a player climbing / falling the overall
# PROSPX rank). Same event-based "since last real change" philosophy as the
# farm engine, applied at the player grain. The input is the player's
# overall_rank over time (metric_snapshots) -- which becomes the eFV rank once
# _active_key ranks by eFV, so this measures eFV-rank movement going forward.
# The board has ~1,700 ranked players, so the rank is far noisier than the
# 30-team farm rank (a player's number shifts whenever neighbours re-grade); a
# generous plateau tolerance + dead-band reject that relative churn. Like the
# farm engine it cannot be back-filled, so it reads flat until a few runs of
# rank history accrue (expected, not a bug -- the eFV GRADE move on `stock`
# carries the immediate signal in the meantime).
# ===========================================================================

# Ranks within this many spots of the anchor are the "same level" when walking
# back -- absorbs the day-to-day churn from neighbouring players re-grading.
_RANK_PLATEAU = 10
# A board move has to clear this many spots to register a direction (smaller is
# relative churn, not a genuine climb/fall); a big leap is a marquee move.
_RANK_DEADBAND = 25
_RANK_STRONG = 100


def _rank_flat(pts: list, basis: str, confidence: str) -> dict:
    first = pts[0] if pts else {}
    last = pts[-1] if pts else {}
    return {
        "direction": "flat",
        "delta": None if basis == "insufficient" else 0,
        "basis": basis,
        "confidence": confidence,
        "from_rank": first.get("rank"),
        "to_rank": last.get("rank"),
        "from_date": first.get("snapshot_date", ""),
        "to_date": last.get("snapshot_date", ""),
        "n_points": len(pts),
    }


def compute_rank_movement(history: list) -> dict:
    """De-noised overall board-RANK movement for one prospect.

    `history` is the player's rank stream -- dicts carrying `snapshot_date` and
    `rank` (the overall board rank, 1 = best), typically loaded oldest-first
    with the current run's rank appended as the final point (the anchor).
    Out-of-order / duplicate-date input is tolerated.

    Walks back from the anchor to the most recent genuine rank STEP (a point
    more than _RANK_PLATEAU spots off the anchor); the move reported is that
    point's rank vs the anchor's. A move smaller than the dead-band is flat.

    Output (a `stock`-compatible superset):
      direction : up_strong|up|flat|down|down_strong
      delta     : rank spots moved (+ = climbed toward #1); None if insufficient
      basis     : rank_step|held|insufficient
      from_rank/to_rank, from_date/to_date, confidence, n_points
    """
    by_date: dict = {}
    for h in (history or []):
        if not isinstance(h, dict):
            continue
        d = h.get("snapshot_date")
        r = h.get("rank")
        if not d or r is None:
            continue
        by_date[d] = {"snapshot_date": d, "rank": int(r)}
    pts = [by_date[d] for d in sorted(by_date)]

    if len(pts) < 2:
        return _rank_flat(pts, "insufficient", "low")

    anchor = pts[-1]
    a_rank = anchor["rank"]
    plateau_start = anchor
    step_pt = None
    for pt in reversed(pts[:-1]):
        if abs(pt["rank"] - a_rank) <= _RANK_PLATEAU:
            plateau_start = pt
            continue
        step_pt = pt
        break

    confidence = "high" if len(pts) >= 3 else "medium"
    if step_pt is None:
        return _rank_flat(pts, "held", confidence)

    delta = step_pt["rank"] - a_rank          # + = climbed (number went down)
    if delta >= _RANK_STRONG:
        direction = "up_strong"
    elif delta >= _RANK_DEADBAND:
        direction = "up"
    elif delta <= -_RANK_STRONG:
        direction = "down_strong"
    elif delta <= -_RANK_DEADBAND:
        direction = "down"
    else:
        direction = "flat"

    return {
        "direction": direction,
        "delta": delta,
        "basis": "rank_step",
        "confidence": confidence,
        "from_rank": step_pt["rank"],
        "to_rank": a_rank,
        "from_date": step_pt.get("snapshot_date", ""),
        "to_date": plateau_start.get("snapshot_date", ""),
        "n_points": len(pts),
    }

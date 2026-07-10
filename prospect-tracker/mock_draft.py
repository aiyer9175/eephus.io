# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tendency-driven mock draft for the current pre-draft class.

A mock draft is a board-anchored, best-fit assignment. We walk the published
pick order in sequence and, at each pick, choose the best available prospect
for THAT team given four signals:

  1. The board   - consensus rank / Draft Stock+ (DS+). Best-available is the
                   default; a team rarely reaches far off the board.
  2. Tendencies  - how the org has actually drafted (org_tendencies.json):
                   college-vs-prep lean, pitching lean, position-bucket tilt,
                   up-the-middle bias, and the tool profile it gravitates to.
  3. Slot money  - the org's bonus-pool behavior (over-slot shoppers vs
                   slot-disciplined) crossed with the pick's slot value and
                   the candidate's signability (an elite faller usually needs
                   over-slot to sign).
  4. Projected   - each pick's overall slot vs the prospect's consensus pick,
     rounds/picks  so a "value" (a faller) and a "reach" are both visible.

The board is the anchor; tendencies + slot money can nudge a pick a few spots
within a small candidate window, never pull a clearly-better player off the
board. Output is deterministic - same inputs always yield the same mock.

This module is pure: `build_mock_draft()` takes already-assembled data and
returns a plain dict. `draft_export` calls it after a class block is built and
bakes the result onto `class["mock_draft"]`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# How many rounds to mock by default. Round 1 (incl. competitive-balance picks,
# which carry round_label "1") plus Round 2 gives a meaty product while staying
# well inside the differentiated top of the board (215 ranked prospects in 2026
# vs ~75 picks here), so every pick still has a deep candidate pool below it.
_DEFAULT_ROUNDS = 2

# Candidate window: how far down the board a team will look for a fit. A team
# picks at-or-near best-available; it does not pull a guy ranked 8+ spots lower
# purely for fit. 7 keeps reaches realistic.
_WINDOW = 7

# Board penalty per slot dropped. A candidate sitting `k` spots down the board
# starts at -k * _W_BOARD. Tendency terms below are weighted so a strongly-fit
# candidate can overcome ~3 board slots at most (sum of max-clamped tendency
# weights ~= 3.4) - enough to move a pick a few spots, never to invert the
# board wholesale.
_W_BOARD = 1.0

# Tendency weights (each multiplies a z-score clamped to +/-2).
_W_PREP = 0.35    # college-vs-prep lean
_W_PITCH = 0.30   # pitching-vs-hitting lean
_W_POSBUCKET = 0.30  # position-bucket tilt (P/C/MI/CI/OF)
_W_UPMID = 0.25   # up-the-middle (C/SS/2B/CF) bias
_W_SLOT = 0.30    # over-slot appetite x signability of a faller
_W_TRAIT = 0.20   # tool profile match (top org tilts vs prospect grades)

_Z_CLAMP = 2.0    # tendency z-scores are clamped to +/- this before weighting

# A candidate is a "faller" worth flagging (and a tougher sign) once their
# consensus pick is this many spots better than the slot they're available at.
_FALLER_GAP = 6

# Tag thresholds: a tendency only earns a human-readable fit tag when its
# contribution clears this, so the displayed reasons are the ones that actually
# moved the needle. The tool-profile signal is inherently smaller in magnitude
# (org tilts top out near z~0.8), so it gets a lower bar - a clear plus-tool
# match in a tool the org chases still earns its tag.
_TAG_MIN = 0.18
_TRAIT_TAG_MIN = 0.10

_PITCHER_POS = {"RHP", "LHP", "SP", "RP", "P"}
_UP_THE_MIDDLE = {"C", "SS", "2B", "CF"}

# Pretty labels for the org's tool tilts (matches draftTraits.tilts keys).
_TOOL_LABELS = {
    "hit": "Hit", "game_pwr": "Game power", "raw_pwr": "Raw power",
    "speed": "Speed", "field": "Field", "pitch_sel": "Pitch selection",
    "bat_ctrl": "Bat control", "fb": "Fastball", "sl": "Slider",
    "cb": "Curveball", "ch": "Changeup", "cmd": "Command",
}


def _primary_pos(position: str | None) -> str:
    """First listed position (the slash-primary), upper-cased. 'SS/3B' -> 'SS'."""
    if not position:
        return ""
    return str(position).split("/")[0].strip().upper()


def _is_pitcher(p: dict) -> bool:
    pt = str(p.get("player_type") or "").upper()
    if pt.endswith("P"):  # COLp / HSp / JCp
        return True
    return _primary_pos(p.get("position")) in _PITCHER_POS


def _is_hs(p: dict) -> bool:
    return str(p.get("player_type") or "").upper().startswith("HS")


def _pos_bucket(p: dict) -> str:
    """Bucket a prospect into P/C/MI/CI/OF to match draftPos.posBucketsZ."""
    if _is_pitcher(p):
        return "P"
    pos = _primary_pos(p.get("position"))
    if pos == "C":
        return "C"
    if pos in {"SS", "2B"}:
        return "MI"
    if pos in {"1B", "3B"}:
        return "CI"
    if pos in {"OF", "CF", "LF", "RF", "DH"}:
        return "OF"
    # Two-way / oddball primary defaults to OF (a bat) unless it pitched.
    return "OF"


def _is_up_the_middle(p: dict) -> bool:
    if _is_pitcher(p):
        return False
    return _primary_pos(p.get("position")) in _UP_THE_MIDDLE


def _clamp(z, lo=-_Z_CLAMP, hi=_Z_CLAMP) -> float:
    try:
        z = float(z)
    except (TypeError, ValueError):
        return 0.0
    return max(lo, min(hi, z))


def _prospect_grades(p: dict) -> dict:
    """Best available per-tool grade dict for a prospect (prefer FanGraphs)."""
    tg = p.get("tool_grades") or {}
    if not isinstance(tg, dict):
        return {}
    src = tg.get("fangraphs") or tg.get("mlb_pipeline") or next(
        (v for v in tg.values() if isinstance(v, dict)), {})
    if not isinstance(src, dict):
        return {}
    return {k: v for k, v in src.items()
            if k != "_extras" and isinstance(v, (int, float))}


def _trait_fit(p: dict, traits: dict | None) -> tuple[float, str | None]:
    """Reward picking a prospect whose strengths match the org's top tool tilts.

    Returns (bounded_contribution, best_matching_tool_label). Uses only the
    org's top tilts so the signal stays interpretable and low-noise; a 60-grade
    tool counts more than a 45 in a tool the org chases. The contribution is
    deliberately ONE-DIRECTIONAL: it is floored at 0, so a strong tool match can
    only nudge a candidate UP a spot, never push a player DOWN the board. That
    keeps the board the anchor - tool fit is a tiebreak-grade bonus, not a way to
    bury a better prospect over a single soft grade."""
    if not traits:
        return 0.0, None
    top = traits.get("top") or []
    grades = _prospect_grades(p)
    if not top or not grades:
        return 0.0, None
    best_term = 0.0
    best_tool = None
    for entry in top[:2]:
        tool = entry.get("tool")
        z = entry.get("z")
        if tool is None or z is None or tool not in grades:
            continue
        # Plus grade in a tool the org chases (positive z) scores; the floor
        # below means a soft grade simply contributes nothing (no penalty).
        grade_strength = max(-1.0, min(1.0, (float(grades[tool]) - 50.0) / 20.0))
        term = _W_TRAIT * _clamp(z) * grade_strength
        if term > best_term:
            best_term = term
            best_tool = tool
    return best_term, best_tool


def _score_candidate(p: dict, board_idx: int, pick: dict,
                     pos_t: dict | None, slot_t: dict | None,
                     traits_t: dict | None) -> tuple[float, list[str], str | None]:
    """Fit score for prospect `p` at this pick. Returns (score, tags, trait_tool)."""
    score = -board_idx * _W_BOARD
    tags: list[str] = []

    hs = _is_hs(p)
    pitcher = _is_pitcher(p)
    bucket = _pos_bucket(p)

    if pos_t:
        # College-vs-prep lean. zPrep > 0 = prep-heavy org.
        z_prep = _clamp(pos_t.get("zPrep"))
        prep_term = _W_PREP * (z_prep if hs else -z_prep)
        score += prep_term
        if prep_term >= _TAG_MIN:
            tags.append("Prep-heavy org" if hs else "College-lean org")

        # Pitching-vs-hitting lean.
        z_pitch = _clamp(pos_t.get("zPitch"))
        pitch_term = _W_PITCH * (z_pitch if pitcher else -z_pitch)
        score += pitch_term
        if pitch_term >= _TAG_MIN:
            tags.append("Pitching-lean org" if pitcher else "Position-player lean")

        # Position-bucket tilt.
        z_bucket = _clamp((pos_t.get("posBucketsZ") or {}).get(bucket))
        bucket_term = _W_POSBUCKET * z_bucket
        score += bucket_term
        if bucket_term >= _TAG_MIN:
            tags.append(f"Targets {bucket}")

        # Up-the-middle bias.
        if _is_up_the_middle(p):
            z_up = _clamp(pos_t.get("zUpMid"))
            up_term = _W_UPMID * z_up
            score += up_term
            if up_term >= _TAG_MIN:
                tags.append("Up-the-middle")

    # Slot money x signability. An elite faller usually needs over-slot to sign;
    # over-slot shoppers chase that, slot-disciplined teams shy from it.
    value_delta = (p.get("consensus_pick") or 0) - (pick.get("pick_overall") or 0)
    is_faller = value_delta <= -_FALLER_GAP
    if slot_t and is_faller:
        z_over = _clamp(slot_t.get("zOver"))
        slot_term = _W_SLOT * z_over
        score += slot_term
        if slot_term >= _TAG_MIN:
            tags.append("Over-slot fit")
        elif slot_term <= -_TAG_MIN:
            # A disciplined org passing the tough sign is itself the story when
            # they DON'T take the faller; no tag when they do anyway.
            pass

    # Tool profile match.
    trait_term, trait_tool = _trait_fit(p, traits_t)
    score += trait_term
    if trait_term >= _TRAIT_TAG_MIN and trait_tool:
        tags.append(f"Tool fit: {_TOOL_LABELS.get(trait_tool, trait_tool)}")

    # NB: value-vs-reach (board rank vs slot) is carried by `value_delta` and
    # rendered in its own column, so it is deliberately NOT duplicated as a fit
    # tag here - fit tags stay purely about WHY the org leaned this way.

    # Deterministic quality tiebreak so equal-fit candidates resolve by DS+
    # then FV - never by dict/order chance.
    score += (p.get("draft_stock_plus") or 0) * 1e-4
    score += (p.get("consensus_fv_raw") or 0) * 1e-6

    return score, tags, trait_tool


def _round_num(label) -> int | None:
    """Leading integer of a round_label ('1', '2', '1A' -> 1, 2, 1)."""
    s = str(label or "")
    num = ""
    for ch in s:
        if ch.isdigit():
            num += ch
        else:
            break
    return int(num) if num else None


def build_mock_draft(class_block: dict, tendencies: dict | None = None, *,
                     rounds: int = _DEFAULT_ROUNDS,
                     window: int = _WINDOW) -> dict | None:
    """Build a mock draft for one class block (as produced by draft_export).

    Returns a dict {basis, n_picks, rounds, used_tendencies, picks:[...]} or
    None when the class is not a pre-draft board (already drafted, or no order /
    no prospects to mock)."""
    order = class_block.get("draft_order") or []
    prospects = class_block.get("prospects") or []
    if not order or not prospects or not class_block.get("is_current"):
        return None
    # Only mock a board that hasn't drafted yet. Once real results land we show
    # those, not a mock.
    if any(o.get("player_key") or o.get("signed") for o in order):
        return None

    tendencies = tendencies or {}
    pos_orgs = ((tendencies.get("draftPos") or {}).get("orgs")) or {}
    slot_orgs = ((tendencies.get("slot") or {}).get("orgs")) or {}
    trait_orgs = ((tendencies.get("draftTraits") or {}).get("orgs")) or {}
    used_tendencies = bool(pos_orgs or slot_orgs or trait_orgs)

    # Board: ranked prospects only, best first. Mirrors draft_export's sort
    # (consensus_pick is the rendered rank; DS+ then FV break ties).
    board = [p for p in prospects if p.get("consensus_pick") is not None]
    board.sort(key=lambda p: (
        p.get("consensus_pick"),
        -(p.get("draft_stock_plus") or 0),
        -(p.get("consensus_fv_raw") or 0),
        p.get("player_name") or "",
    ))
    available = list(board)
    if not available:
        return None

    # Pick sequence: the published order, in pick order, limited to the mocked
    # rounds and to teams we know. Picks with no team are skipped (can't assign).
    picks = sorted((o for o in order if o.get("team")),
                   key=lambda o: o.get("pick_overall") or 1e9)
    picks = [o for o in picks
             if (_round_num(o.get("round_label")) or 99) <= rounds]

    out: list[dict] = []
    for pick in picks:
        if len(available) < 1:
            break
        team = pick.get("team")
        pos_t = pos_orgs.get(team)
        slot_t = slot_orgs.get(team)
        traits_t = trait_orgs.get(team)

        window_pool = available[:max(1, min(window, len(available)))]
        best = None
        best_idx = 0
        best_score = None
        best_tags: list[str] = []
        # window_pool is a prefix of `available`, so the loop index is also the
        # candidate's index in `available` - we pop by that index, never by
        # value equality (which could match a different equal dict).
        for idx, cand in enumerate(window_pool):
            sc, tags, _ = _score_candidate(
                cand, idx, pick, pos_t, slot_t, traits_t)
            if best_score is None or sc > best_score:
                best, best_idx, best_score, best_tags = cand, idx, sc, tags

        bpa = available[0]
        bpa_passed = None
        if best_idx != 0:
            bpa_passed = {
                "player_name": bpa.get("player_name"),
                "consensus_pick": bpa.get("consensus_pick"),
                "position": bpa.get("position"),
            }
        available.pop(best_idx)

        value_delta = (best.get("consensus_pick") or 0) - (pick.get("pick_overall") or 0)
        out.append({
            "pick_overall":     pick.get("pick_overall"),
            "round_label":      pick.get("round_label"),
            "pick_in_round":    pick.get("pick_in_round"),
            "team":             team,
            "slot_usd":         pick.get("slot_usd"),
            "player_key":       best.get("player_key"),
            "player_name":      best.get("player_name"),
            "position":         best.get("position"),
            "school":           best.get("school"),
            "school_logo_url":  best.get("school_logo_url"),
            "player_type":      best.get("player_type"),
            "consensus_fv":     best.get("consensus_fv"),
            "consensus_fv_raw": best.get("consensus_fv_raw"),
            "consensus_fv_plus": bool(best.get("consensus_fv_plus")),
            "consensus_pick":   best.get("consensus_pick"),
            "draft_stock_plus": best.get("draft_stock_plus"),
            "value_delta":      value_delta,
            "fit_tags":         best_tags,
            "bpa_passed":       bpa_passed,
        })

    if not out:
        return None

    basis = ("Board (consensus rank + Draft Stock+) anchors each pick; "
             "org tendencies, slot-pool behavior, and signability nudge the "
             "fit within a small window of best-available.")
    if not used_tendencies:
        basis = ("Board (consensus rank + Draft Stock+) only - no org tendency "
                 "data was available, so this is a straight best-player-available "
                 "projection.")
    return {
        "basis":           basis,
        "n_picks":         len(out),
        "rounds":          rounds,
        "used_tendencies": used_tendencies,
        "picks":           out,
    }


def load_tendencies(path: Path | str = "data/org_tendencies.json") -> dict:
    """Best-effort read of the org_tendencies sidecar. Missing/unreadable file
    yields an empty dict so the mock degrades to pure best-available."""
    try:
        with Path(path).open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, json.JSONDecodeError):
        log.warning("mock_draft: org_tendencies.json unavailable - "
                    "mock falls back to best-player-available")
        return {}


def attach_mock_draft(classes: list[dict],
                      tendencies: dict | None = None) -> None:
    """Bake `mock_draft` onto every pre-draft class block, in place."""
    if tendencies is None:
        tendencies = load_tendencies()
    for cls in classes:
        mock = build_mock_draft(cls, tendencies)
        if mock:
            cls["mock_draft"] = mock
            log.info("mock_draft: %d picks mocked for %s class",
                     mock["n_picks"], cls.get("year"))

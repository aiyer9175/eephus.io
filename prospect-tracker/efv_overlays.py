# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The served eFV overlays: what each is, whether it can be graded out of sample, and
where it goes when eFV V2 serves (DS-11, bug B6 in docs/efv-v2/DRIVER_SYSTEM_V2.md).

THE DEFECT. efv_score.run_live applies seven things to the model leg or the grade that
efv_model.oos_grades never applied: the injury haircut, the prospect-age ramp, the
reliever ceiling, the Statcast+ tilt, the S-XLINE lean, the dispersion correction and
the side-fairness recalibration. Every accuracy number the site publishes for eFV was
measured without them, so their effect on the served order had no measured sign.

WHAT THIS MODULE HOLDS.
  OVERLAYS            one entry per served overlay: what it acts on, whether as-of inputs
                      exist for the labelled rows (so it CAN be graded out of sample),
                      and the chip it becomes when it leaves the grade.
  asof_inputs()       the as-of inputs for the v1 training rows: age at the read (from
                      the row's birth date and read date) and injured-list status at the
                      read (placements and activations in player_transactions strictly
                      before the read). The list-time position already rides the row.
  DISPOSITION_RULE    the rule that decides, from the out-of-sample read, whether an
                      overlay may stay on the grade. FIXED BEFORE THE READ RAN (this file
                      was committed with the rule and the read tool together; the tool
                      copies the rule text into its artifact).
  dispositions()      the rule applied to data/efv_overlay_oos_eval.json.
  overlay_chips()     the labelled chips a served row carries for the overlays that
                      leave the grade: a statement that the overlay fires on this player,
                      never a move of the grade.

WHAT IT DOES NOT DO. Nothing here changes the served grade. eFV v1's board keeps every
overlay until DS-02 serves V2 (docs/efv-v2/PROGRAM.md, owner answer DS-Q1); the
dispositions below are what the V2 serving step applies.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): nothing here groups, counts or averages
rows by consensus-FV level; the read is scored within (side, decision year).
"""
from __future__ import annotations

import collections
import json
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
EVAL_PATH = DATA_DIR / "efv_overlay_oos_eval.json"
DB_PATH = ROOT / "prospects.db"

#: The disposition rule, fixed before the out-of-sample read ran. Primary statistic per
#: owner answer DS-Q3: the size-weighted mean of within-(side, decision year) Spearman
#: correlations of the scored object (the guarded blend, rank_war) with the six-season
#: label, on the rows the live board scores (rows with a MiLB block), overlay on minus
#: overlay off, paired player-clustered bootstrap CI95.
DISPOSITION_RULE = (
    "An overlay stays on the served grade only if it can be graded out of sample (as-of "
    "inputs exist for the labelled rows) AND, on every side where it fires, its paired "
    "within-(side, decision year) Spearman delta (overlay on minus off, scored object, "
    "rows with a MiLB block) has a CI95 lower bound above zero. Every other overlay "
    "leaves the grade: one with a measurable per-player statement becomes a labelled "
    "chip; one that cannot reorder players inside a side (a monotone per-side map, or "
    "a pricing-only map) is retired from the V2 grade because V2 sets the level from "
    "consensus values within (side, year) and prices from its own WAR line.")

#: Every served overlay. `acts_on`: model_leg (reaches rank_war and the board grade),
#: board_grade (a map applied after the blend, reaches only the board grade) or
#: pricing_grade (reaches only the surplus-pricing grade). `gradeable`: as-of inputs
#: exist for the labelled rows. `order_neutral`: cannot change the order of two
#: players of the same side.
OVERLAYS: dict[str, dict] = {
    "injury": {
        "function": "efv_score._injury_factor",
        "acts_on": "model_leg", "sides": ("pit",), "gradeable": True,
        "order_neutral": False,
        "asof_input": ("injured-list status at the read from player_transactions "
                       "(placements and activations before the read); the archive is "
                       "reliable from 2017 (tools/efv_health_profile_lab.py)"),
        "chip": "On the injured list",
        "owner_decision": "2026-09-04: pitchers only (hitter sign contraindicated)",
    },
    "age": {
        "function": "efv_score._age_factor",
        "acts_on": "model_leg", "sides": ("hit", "pit"), "gradeable": True,
        "order_neutral": False,
        "asof_input": "age at the read from the row's birth date and read date",
        "chip": "Old for a prospect",
        "owner_decision": "2026-07-30: onset 23.0 (policy dial D2)",
    },
    "role": {
        "function": "efv_score._role_factor",
        "acts_on": "model_leg", "sides": ("pit",), "gradeable": True,
        "order_neutral": False,
        "asof_input": ("the row's list-time position (SIRP / MIRP / RP / CL) and age at "
                       "the read"),
        "chip": "Reliever ceiling",
        "owner_decision": "2026-07-15: the reliever-ceiling directive",
    },
    "statcast": {
        "function": "efv_score._statcast_factor",
        "acts_on": "model_leg", "sides": ("hit", "pit"), "gradeable": False,
        "order_neutral": False,
        "why_not_gradeable": ("Statcast+ exists for current seasons only; no labelled "
                              "row has a Statcast+ value as of its read"),
        "chip": "Statcast+ quality",
    },
    "xline": {
        "function": "efv_statcast_overlay.overlay_fv",
        "acts_on": "model_leg", "sides": ("hit", "pit"), "gradeable": False,
        "order_neutral": False,
        "why_not_gradeable": ("the A-ball and AAA tracking signals start in 2023; no "
                              "cohort they cover has resolved, and the module itself "
                              "states it ships with no resolved out-of-sample fold"),
        "chip": "Statcast lean",
    },
    "dispersion": {
        "function": "efv_score.apply_dispersion_correction",
        "acts_on": "board_grade", "sides": ("hit", "pit"), "gradeable": True,
        "order_neutral": True,
        "why_order_neutral": ("a strictly increasing per-side map, applied after the "
                              "blend; identity (0, 1) on both sides since 2026-08-14, so "
                              "it moves nothing today"),
        "chip": None,
    },
    "side_fairness": {
        "function": "efv_score._apply_side_fairness_fix",
        "acts_on": "pricing_grade", "sides": ("hit", "pit"), "gradeable": True,
        "order_neutral": True,
        "why_order_neutral": ("re-anchors the surplus-pricing grade of the joint top "
                              "band only; within-side order is preserved by "
                              "construction and neither rank_war nor the board grade "
                              "reads it"),
        "chip": None,
    },
}

#: The overlays the out-of-sample read grades (model leg, as-of inputs exist).
GRADED: tuple[str, ...] = tuple(k for k, v in OVERLAYS.items()
                                if v["gradeable"] and v["acts_on"] == "model_leg")


# ---------------------------------------------------------------------------
# as-of inputs for the labelled rows
# ---------------------------------------------------------------------------

_IL_RE = re.compile(r"injured list|disabled list", re.I)
_PLACE_RE = re.compile(r"\bplaced\b|\btransferred\b", re.I)
_ACT_RE = re.compile(r"activated|reinstated|returned", re.I)
_TYPE_RE = re.compile(r"on the ([\w-]+?)[- ]?day injured list|on the (full-season) injured list",
                      re.I)


def _d(s):
    try:
        y, m, dd = str(s)[:10].split("-")
        return date(int(y), int(m), int(dd))
    except (TypeError, ValueError):
        return None


def il_events(db_path: Path | None = None) -> dict[str, list[dict]]:
    """{player_key: [{date, kind, il_type}]} of injured-list placements and activations
    from player_transactions, sorted by date (the parse tools/efv_health_profile_lab.py
    uses). An absent database gives {}."""
    p = Path(db_path or DB_PATH)
    if not p.exists():
        return {}
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    out: dict[str, list[dict]] = collections.defaultdict(list)
    try:
        for pk, payload in con.execute("select player_key, payload_json from player_transactions"):
            try:
                rows = json.loads(payload)
            except (TypeError, ValueError):
                continue
            for t in rows or []:
                txt = t.get("description") or ""
                if not _IL_RE.search(txt):
                    continue
                dt = _d(t.get("date"))
                if dt is None:
                    continue
                if _PLACE_RE.search(txt):
                    kind = "place"
                elif _ACT_RE.search(txt):
                    kind = "activate"
                else:
                    continue
                m = _TYPE_RE.search(txt)
                raw = (m.group(1) or m.group(2)) if m else None
                il_type = (f"{raw}-day" if raw and raw.isdigit() else raw)
                out[pk].append({"date": dt, "kind": kind, "il_type": il_type})
    finally:
        con.close()
    for pk in out:
        out[pk].sort(key=lambda e: e["date"])
    return dict(out)


def il_status_asof(events: list[dict], read: date) -> dict:
    """The live board's injury fields (efv_dataset live rows: il_on, il_type,
    il_days_12mo, il_stints_12mo) as of `read`, from events strictly before it. A stint
    still open at the read counts its elapsed days only, so nothing after the read is
    seen; days are capped at 365 per stint and in total, as storage's health profile
    caps them."""
    window = read - timedelta(days=365)
    open_at, open_type = None, None
    stints, days = 0, 0
    for e in events:
        if e["date"] >= read:
            break
        if e["kind"] == "place":
            if open_at is None:
                open_at = e["date"]
                if open_at >= window:
                    stints += 1
            open_type = e["il_type"] or open_type
        elif e["kind"] == "activate" and open_at is not None:
            if open_at >= window:
                days += min(365, max(0, (e["date"] - open_at).days))
            open_at, open_type = None, None
    on = open_at is not None
    if on and open_at >= window:
        days += min(365, max(0, (read - open_at).days))
    return {"il_on": 1 if on else 0, "il_type": open_type if on else None,
            "il_days_12mo": float(min(365, days)), "il_stints_12mo": float(stints)}


def age_at(birth_date, read: date):
    """Age in years at `read`, one decimal (the live board's age_now convention), or
    None without a birth date."""
    b = _d(birth_date)
    if b is None or read is None:
        return None
    return round((read - b).days / 365.25, 1)


def read_date(row: dict):
    """The date a labelled row's inputs are read at: its consensus read (asof_date),
    else its cutoff."""
    return _d(row.get("asof_date")) or _d(row.get("cutoff"))


def asof_inputs(rows: list[dict], events: dict[str, list[dict]] | None = None) -> dict:
    """{player_key: {age_now, il_on, il_type, il_days_12mo, il_stints_12mo}} for raw
    matrix rows, every field as of the row's read (read_date). No field reads the label,
    the debut or anything dated at or after the read."""
    ev = il_events() if events is None else events
    out = {}
    for r in rows:
        rd = read_date(r)
        if rd is None:
            continue
        rec = {"age_now": age_at(r.get("birth_date"), rd)}
        rec.update(il_status_asof(ev.get(r["player_key"]) or [], rd))
        out[r["player_key"]] = rec
    return out


# ---------------------------------------------------------------------------
# the rule, applied to the read
# ---------------------------------------------------------------------------

def decide(name: str, read: dict | None) -> dict:
    """The disposition of one overlay under DISPOSITION_RULE. `read` is the overlay's
    entry in the artifact's `overlays` block ({side: {"fires": n, "within": {"delta",
    "ci95"}}}) or None for an overlay the read did not grade."""
    meta = OVERLAYS[name]
    if meta["order_neutral"]:
        return {"disposition": "retired", "on_grade": False,
                "why": meta["why_order_neutral"]}
    if not meta["gradeable"]:
        return {"disposition": "chip", "on_grade": False,
                "why": "not gradeable out of sample: " + meta["why_not_gradeable"]}
    sides = [s for s in meta["sides"] if ((read or {}).get(s) or {}).get("fires")]
    if not sides:
        return {"disposition": "chip", "on_grade": False,
                "why": "fires on no labelled row with a MiLB block, so nothing was graded"}
    lows = {s: (((read[s].get("within") or {}).get("ci95")) or [None, None])[0]
            for s in sides}
    if all(v is not None and v > 0 for v in lows.values()):
        return {"disposition": "grade", "on_grade": True,
                "why": "CI95 lower bound above zero on every side where it fires",
                "ci95_low": lows}
    return {"disposition": "chip", "on_grade": False,
            "why": ("graded out of sample; the paired within-(side, decision year) delta "
                    "does not clear zero on every side where it fires"),
            "ci95_low": lows}


def dispositions(path: Path | None = None) -> dict[str, dict]:
    """{overlay: disposition} from the committed read (every overlay present; an
    overlay the artifact lacks is decided with no read)."""
    p = Path(path or EVAL_PATH)
    doc = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    reads = doc.get("overlays") or {}
    return {k: decide(k, reads.get(k)) for k in OVERLAYS}


def overlay_chips(r: dict, side: str, model_war: float, disp: dict | None = None) -> list:
    """The labelled chips for one served row: every overlay whose disposition is "chip"
    and that fires on this row, as {overlay, label, dir, on_grade: False}. A chip says
    the overlay's condition holds for the player; it never carries a grade move."""
    import efv_score as E
    disp = dispositions() if disp is None else disp
    names = [k for k, d in disp.items() if d["disposition"] == "chip"]
    model_names = [k for k in names if OVERLAYS[k]["acts_on"] == "model_leg"]
    parts = E.overlay_factors(r, side, model_war, model_names)
    out = []
    for k in model_names:
        label = OVERLAYS[k]["chip"]
        if k == "xline":
            if not parts["xline_fv"]:
                continue
            up = parts["xline_fv"] > 0
            # the lean's own label (the A-ball or AAA lean): the card's pill keys on it
            label = parts.get("xline_label") or label
        else:
            f = parts[k]
            if f == 1.0:
                continue
            up = f > 1.0
        out.append({"overlay": k, "label": label,
                    "dir": "up" if up else "down", "on_grade": False})
    return out

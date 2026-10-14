# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The served half of the DvM+ difficulty arm (DVM-5): the rows storage aggregates.

Owner ask 6 (2026-09-30) asked for DvM+ weighted by how hard a grade move is to make.
The study is tools/dvm_difficulty_lab.py under
docs/dvm-difficulty-2026-09-30/DVM_DIFFICULTY_GATE.md; its one look writes the frozen
expectation table data/dvm_difficulty.json. This module applies that frozen table to
the current store's same-source preseason steps (12-month, list to list, Q-DVM-4 A and
Q-DVM-5 A) and hands storage._build_org_dev_residuals one row per step with its credit.

NOTHING HERE RUNS WHILE storage.DVM_DIFFICULTY_ARM IS None, which it is until the
owner's flip (DVM-6). With the arm on:
  - the table must be the look's own artifact (a frame_receipt that is not a fixture);
    require_look_table() refuses anything else, so no growth is computed on real data
    against a table the look did not write;
  - the frame is the lab's build_frame (its frame rules F-R1 to F-R5 included) on the
    live store, and each step is split across clubs by VAL_4's org calendar
    (dev_attribution: Attribution.calendar), an unaffiliated stretch crediting nobody;
  - the credits are the lab's row_credits on the frozen models, re-centered per
    (source, step year) over the steps scored together (gate section 5).

The local render seam _install_fixture_for_local_render() swaps in the lab's dry-run
table and its synthetic fixture steps (mapped onto the 30 clubs and the given player
keys) so a dark build can be looked at with the arm on locally; it reads no grade from
the store and is never called by the pipeline.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
TABLE_FILE = "dvm_difficulty.json"
EVAL_FILE = "dvm_difficulty_eval.json"

#: storage.DVM_DIFFICULTY_ARM values and the credit each one reads (gate section 6):
#: "value" is DV (w - E^W, expected-WAR units), "difficulty" is D0 ((y - E) / s_hat).
ARM_CREDIT = {"value": ("v", "DV"), "difficulty": ("z", "D0")}
ARM_UNITS = {"value": "expected WAR", "difficulty": "grade-point spreads"}

#: The club code that stands for an unaffiliated stretch in the tenure events; its share
#: is dropped after the split, so it credits nobody (dev_attribution step 3).
UNAFFILIATED = "__unaffiliated__"

#: Tool groups (storage.TOOL_GROUPS keys) against the lab traits that carry an
#: expectation model (gate section 8). pitch_sel, bat_ctrl and ct are descriptive in the
#: lab (no model), so their groups read None under the arm.
TOOL_GROUP_TRAITS: dict[str, tuple[str, ...]] = {
    "hit": ("hit",), "pwr": ("game_pwr", "raw_pwr"), "speed": ("speed",),
    "field": ("field",), "arm": ("arm",),
    "fb": ("fb",), "sl": ("sl",), "cb": ("cb",), "ch": ("ch",), "cmd": ("cmd",),
}


class ArmError(RuntimeError):
    """The arm is on but its frozen table cannot be served."""


_FIXTURE: dict | None = None


def _lab():
    tools_dir = str(ROOT / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import dvm_difficulty_lab as lab  # noqa: PLC0415  loaded only with the arm on
    return lab


def load_table(data_dir: Path | None = None) -> tuple[dict, dict]:
    """(table, eval) from the look's artifacts; the fixture pair under the local seam."""
    if _FIXTURE is not None:
        return _FIXTURE["table"], _FIXTURE["eval"]
    data_dir = Path(data_dir or DATA_DIR)
    p = Path(data_dir) / TABLE_FILE
    if not p.exists():
        raise ArmError(f"{p} is missing: the arm needs the look's frozen table")
    table = json.loads(p.read_text(encoding="utf-8"))
    ev_p = Path(data_dir) / EVAL_FILE
    ev = json.loads(ev_p.read_text(encoding="utf-8")) if ev_p.exists() else {}
    return table, ev


def require_look_table(table: dict) -> dict:
    """The receipt of a table the look wrote; ArmError for a fixture or a bare table."""
    rec = (table or {}).get("frame_receipt") or (table or {}).get("receipt") or {}
    if _FIXTURE is not None:
        return rec
    if not (table or {}).get("frame_receipt") or rec.get("fixture"):
        raise ArmError("data/dvm_difficulty.json carries no look receipt; the arm serves "
                       "only the table the one look wrote")
    return rec


def club_events(calendars: dict[str, list]) -> dict[str, list[tuple[str, str, str]]]:
    """VAL_4 calendars as the lab's tenure events: each tenure opens with its club on
    its start day; an unaffiliated tenure opens the UNAFFILIATED stretch."""
    out: dict[str, list[tuple[str, str, str]]] = {}
    for pk, tenures in calendars.items():
        evs = [(str(t.start)[:10], t.org or UNAFFILIATED, "read") for t in tenures or []]
        if evs:
            out[pk] = evs
    return out


def clean_tau(tau: dict, clubs: Iterable[str]) -> dict[str, float]:
    """Drop the unaffiliated share (and any non-club code) without renormalizing: growth
    while unaffiliated credits nobody."""
    keep = set(clubs)
    return {c: float(s) for c, s in (tau or {}).items() if c in keep and s > 0}


def serve_pairs(con: sqlite3.Connection, *, calendar_of: Callable[[str], list],
                clubs: Iterable[str], player_keys: list[str] | None = None,
                data_dir: Path | None = None) -> tuple[list[dict], dict]:
    """The 12-month same-source steps of the current store, each split across clubs by
    VAL_4's calendar. Under the local seam: the fixture steps instead (no store read)."""
    clubs = sorted(clubs)
    if _FIXTURE is not None:
        return _fixture_pairs(clubs, player_keys or []), {"fixture": True}
    lab = _lab()
    from trades import canonical_org
    debut = lab.load_debut_days(Path(data_dir or DATA_DIR))
    frame = lab.build_frame(con, debut=debut)
    players = sorted({k[1] for k in frame["starts"]})
    events = club_events({pk: calendar_of(pk) for pk in players})
    ids = {st["person"] for st in frame["starts"].values() if st.get("person")}
    last = max((k[2] for k in frame["starts"]), default=2011) + 1
    this_year = date.today().year
    seasons = lab.load_person_seasons(ids, min(last, this_year))

    def active_in(person, season):
        ps = seasons.get(person) or {}
        if not any(season in (ps.get(g) or {}) for g in lab.ID.GROUPS):
            return False if season <= this_year - 1 else None
        return True

    pairs, census = lab.pairs_from_frame(frame, debut=debut, club_events=events,
                                         canon=canonical_org, active_in=active_in)
    out = []
    for p in pairs:
        if p["h"] != 1:
            continue
        p["tau"] = clean_tau(p.get("tau"), clubs)
        out.append(p)
    return out, dict(census)


def score(pairs: list[dict], table: dict, arm: str) -> tuple[list[dict], dict[str, list[dict]]]:
    """(fv_rows, tool_rows): every 12-month step with its expectation and both credits
    under the frozen table, re-centered per (source, step year) (gate sections 5 and 6),
    and per tool trait the D0 rows (section 8)."""
    if arm not in ARM_CREDIT:
        raise ArmError(f"unknown DVM_DIFFICULTY_ARM {arm!r}")
    lab = _lab()
    fv_rows: list[dict] = []
    for side in lab.SIDES:
        rows = lab.analysis_rows(pairs, h=1, side=side)
        m = (table.get("models") or {}).get(f"12m|{side}") or {}
        my, mw = m.get("y") or {}, m.get("w") or {}
        if not rows or not my.get("coef") or not mw.get("coef"):
            continue
        cr = lab.row_credits(rows, my, mw)
        for i, r in enumerate(rows):
            fv_rows.append({
                "pk": r["pk"], "src": r["src"], "V": r["V"], "step_end": r["V"] + r["h"],
                "side": side, "omega": r["omega"], "tau": r["tau"],
                "y": r["y"], "w": r["w"], "E": float(cr["E"][i]), "EW": float(cr["EW"][i]),
                "s_hat": lab.spread_of(my, r["rung"]),
                "v": float(cr["v"][i]), "z": float(cr["z"][i]),
                "origin": r["origin"], "rung": r["rung"], "level": r["level"],
                "age_rel": r["age_rel"],
            })
    tool_rows: dict[str, list[dict]] = {}
    for side in lab.SIDES:
        for trait in lab.TRAITS[side]:
            if trait == "FV":
                continue
            mt = (table.get("tool_models") or {}).get(f"{side}|{trait}") or {}
            if not mt.get("coef"):
                continue
            rows = lab.analysis_rows(pairs, trait=trait, h=1, side=side)
            if not rows:
                continue
            z = lab.row_credits(rows, mt)["z"]
            tool_rows[trait] = [{"pk": r["pk"], "step_end": r["V"] + r["h"], "side": side,
                                 "omega": r["omega"], "tau": r["tau"], "z": float(zz)}
                                for r, zz in zip(rows, z)]
    return fv_rows, tool_rows


def _r3(x):
    """3 decimals for a number; a word ("undefined") or None passes through."""
    return round(float(x), 3) if isinstance(x, (int, float)) and not isinstance(x, bool) else x


def spec_block(table: dict, ev: dict, arm: str, principal_window: str) -> dict:
    """The farm_dev_spec block the Development tab explainer reads: every number comes
    from the two artifacts. Verdict words appear only where H1 (12 months) or H2
    resolved (gate sections 10 and 11); otherwise the explainer shows rates only."""
    h2 = (ev or {}).get("h2") or {}
    desc = h2.get("descriptive") or {}
    table_rows: dict[str, list] = {}
    by_origin: dict[str, dict] = {}
    for side in ("hit", "pit"):
        d = desc.get(f"primary|{side}|12m") or {}
        p1, p2, m = d.get("P1") or {}, d.get("P2") or {}, d.get("m") or {}
        table_rows[side] = [{"rung": rg, "P1": _r3(p1.get(rg)), "P2": _r3(p2.get(rg)),
                             "m": _r3(m.get(rg))}
                            for rg in ("<=35", "40", "45", "50", "55", "60+")
                            if rg in p1 or rg in p2 or rg in m]
        if d.get("by_origin"):
            by_origin[side] = {g: {rg: {k: _r3(v) for k, v in cell.items()}
                                   for rg, cell in cells.items()}
                               for g, cells in d["by_origin"].items()}
    h2_words = [{"side": t.get("side"), "horizon": t.get("horizon"), "test": t.get("test"),
                 "verdict": t.get("verdict")}
                for t in h2.get("tests") or []
                if t.get("verdict") == "list grades rise less often from higher rungs"]
    h1_words = []
    for fam, blk in ((ev or {}).get("h1") or {}).get("families", {}).items():
        if not fam.startswith("12m|"):
            continue
        for c in blk.get("cells") or []:
            if c.get("verdict") not in (None, "not resolved", "unpowered"):
                h1_words.append({"side": c.get("side"), "trait": c.get("trait"),
                                 "contrast": c.get("contrast"),
                                 "estimand": fam.split("|", 1)[1], "verdict": c["verdict"]})
    ratio = {}
    for key, r in ((table or {}).get("ratio") or {}).items():
        if not key.startswith("12m|"):
            continue
        ratio[key.split("|", 1)[1]] = {n: _r3((r.get(n) or {}).get("ratio"))
                                       for n in ("today", "DV", "D0")}
    dec = (ev or {}).get("decision") or {}
    rec = (table or {}).get("frame_receipt") or (table or {}).get("receipt") or {}
    return {
        "arm": arm,
        "credit_units": ARM_UNITS[arm],
        "principal_window": principal_window,
        "frame": (table or {}).get("frame"),
        "look_date": rec.get("today") or (str(rec.get("generated_at") or "")[:10] or None),
        "fixture": bool(rec.get("fixture")),
        "min_publish_n": 10,
        "difficulty_table": table_rows,
        "by_origin": by_origin,
        "h2_verdicts": h2_words,
        "h1_verdicts": h1_words,
        "ratio_60_70_over_40_50": ratio,
        "decision": {"verdict": dec.get("verdict"), "copy": list(dec.get("copy") or [])},
    }


# ---------------------------------------------------------------------------
# the local render seam (never called by the pipeline)
# ---------------------------------------------------------------------------

def _install_fixture_for_local_render(table_dir: Path) -> None:
    """Serve the lab's dry-run artifacts and synthetic steps, for a local look at a dark
    build. table_dir holds the dry run's dvm_difficulty.json and dvm_difficulty_eval.json
    (python tools/dvm_difficulty_lab.py --dry-run DIR)."""
    global _FIXTURE
    d = Path(table_dir)
    _FIXTURE = {"table": json.loads((d / TABLE_FILE).read_text(encoding="utf-8")),
                "eval": json.loads((d / EVAL_FILE).read_text(encoding="utf-8"))}


def _fixture_pairs(clubs: list[str], player_keys: list[str]) -> list[dict]:
    """The lab's fixture steps, its clubs C00 to C29 mapped onto the real club codes and
    its players onto the given keys (so the player index lands on real rows)."""
    lab = _lab()
    keys = list(player_keys)
    n = min(len(keys), 900) if keys else 400
    pairs = lab.fixture_pairs(players=n, clubs=len(clubs))
    cmap = {f"C{i:02d}": c for i, c in enumerate(clubs)}
    pmap = {f"p{i:04d}": (keys[i] if i < len(keys) else f"p{i:04d}") for i in range(n)}
    out = []
    for p in pairs:
        if p["h"] != 1:
            continue
        q = dict(p)
        q["pk"] = pmap.get(p["pk"], p["pk"])
        q["tau"] = {cmap.get(c, c): s for c, s in (p.get("tau") or {}).items()}
        out.append(q)
    return out

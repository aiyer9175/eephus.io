# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The served view of the eFV v5 metric atlas (EFV5_ATLAS_PAGE; owner 2026-10-14,
decision EW3-3: the atlas is shown in the Library's Evidence shelf).

WHAT IT IS. A display projection of the atlas and nothing more. It reads
data/efv5_metric_atlas.json (labels, metrics, groups, the declared minimums) and the
atlas's cells file (one row per metric, group and label), and writes
data/efv5_metric_atlas_view.json, which the Library's "What Predicts the Majors" view
fetches. It fits nothing, scores nothing and selects nothing: every number in the view is
a number of the atlas, re-keyed and oriented for the page.

TWO SCORES PER ROW, both the atlas's own:
    raw          the chart's score on the cell's full MiLB population (AUC against a
                 reached-MLB label, or the within-season Spearman against a WAR label),
                 ORIENTED so it reads at or above the no-relation line (an AUC under 0.5
                 becomes 1 - AUC with the direction "lower is better"); the CI95 flips with
                 it
    incremental  the out-of-fold lift from adding the metric to PROSPX consensus FV on the
                 graded rows, with its player-clustered CI95 and its BH q. Only this score
                 can admit an eFV driver.

THE CHIP. Whether eFV uses a metric is read from the driver and head tasks' own artifacts,
never typed here:
    live            admitted by a selection AND that selection's served flag is on
    admitted        admitted by a selection (a driver step chosen on the development
                    frames, or a tracking-head metric that carries weight) while the flag
                    is off or the selection failed its ship rule
    tested          offered to a selection (a driver menu column, a tracking-head metric)
                    and not admitted
    untested        never offered to either
A driver column matches its own (side, metric, level, age band, group); a tracking-head
metric matches its side, metric and the head's tracked levels, any band or group. Absent
artifacts leave every chip "untested".

HIDDEN. The atlas scores a cell only at or above its declared minimum (players and reached
players); the view keeps that rule, so a group under it has no entry and the page says so.

BANS. No served eFV number reads this module. Nothing here groups, counts or averages by
consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md). Rows whose label window reaches the
spent R-VM cohort keep the atlas's flag and are labelled spent on the page.

Run:  python efv5_atlas_view.py          (writes data/efv5_metric_atlas_view.json)
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ATLAS_PATH = DATA_DIR / "efv5_metric_atlas.json"
OUT_PATH = DATA_DIR / "efv5_metric_atlas_view.json"
GROUP_SELECT_PATH = DATA_DIR / "_labs" / "efv5" / "efv5_group_select.json"
GROUP_SPENT_PATH = DATA_DIR / "_labs" / "efv5" / "efv5_group_spent.json"
TRACKING_HEAD_PATH = DATA_DIR / "efv5_tracking_head.json"
GROUP_DRIVERS_SRC = ROOT / "efv5_group_drivers.py"
TRACKING_HEAD_SRC = ROOT / "efv5_tracking_head.py"
TOOL = "efv5_atlas_view.py"
ITEM = "EFV5_ATLAS_PAGE"
SCHEMA = 1

LEVEL_NAMES = {"DSL": "Dominican Summer League", "CPX": "Complex leagues", "A-": "Short-season A",
               "A": "Single-A", "A+": "High-A", "AA": "Double-A", "AAA": "Triple-A"}
BAND_NAMES = {"all": "All ages", "young": "Young for the level",
              "average": "Average age for the level", "old": "Old for the level"}
FAMILY_NAMES = {"box": "Box score (2005+)", "pbp": "Pitch by pitch (2007+)",
                "bb": "Batted ball (2007+)", "tracking": "Tracking (2021+)"}
LABEL_ORDER = ("reach_h", "reach3", "reach5", "w3", "l6", "war_rate_h")
LABEL_NAMES = {"reach_h": "Reached MLB by 2026",
               "reach3": "Reached MLB within 3 seasons",
               "reach5": "Reached MLB within 5 seasons",
               "w3": "fWAR over the first 3 MLB seasons",
               "l6": "Six-season fWAR",
               "war_rate_h": "fWAR per MLB season through 2026"}
FRAME_NAMES = {"clean": "seasons whose window closes before the 2025 debut cohort",
               "all": "every resolved season"}

#: Display names, keyed by the atlas metric id minus its side suffix. "vs age" marks the
#: atlas's level-season age-line versions.
NAMES = {
    "age": "Age", "age_rel_level": "Age for level",
    "k_pct": "K%", "bb_pct": "BB%", "bb_minus_k": "BB-K%", "k_minus_bb": "K-BB%",
    "hr_pct": "HR%", "iso": "ISO", "avg": "AVG", "obp": "OBP", "slg": "SLG", "ops": "OPS",
    "babip": "BABIP", "woba": "wOBA", "sb_rate": "SB per PA", "gb_pct": "GB% (outs)",
    "era": "ERA", "bf_per_g": "Batters faced per game", "gs_share": "Starts share",
    "pbp_swstr": "Swinging-strike %", "pbp_contact": "Contact %", "pbp_swing": "Swing %",
    "pbp_two_strike_contact": "Two-strike contact %",
    "pbp_fstrike_taken": "First-pitch called strikes taken",
    "pbp_k_resid": "K% beyond whiffs", "pbp_cstr": "Called-strike %", "pbp_csw": "CSW%",
    "pbp_fstrike": "First-pitch strike %", "pbp_ball_rate": "Ball %",
    "bb_gb": "Ground-ball %", "bb_ld": "Line-drive %", "bb_fb": "Fly-ball %",
    "bb_pu": "Popup %", "bb_hard": "Hard-hit % (graded)", "bb_pull": "Pull %",
    "bb_oppo_hard": "Hard opposite-field %",
    "trk_fb_velo_mean": "Fastball velo (mean)", "trk_fb_velo_p95": "Top-end fastball velo",
    "trk_fb_ivb": "Fastball ride", "trk_fb_hb_arm": "Fastball arm-side run",
    "trk_extension": "Extension", "trk_arm_angle": "Arm angle", "trk_csw": "CSW% (tracked)",
    "trk_swstr": "Swinging-strike % (tracked)", "trk_whiff": "Whiff per swing",
    "trk_zone": "Zone %", "trk_chase": "Chase %", "trk_zone_contact": "Zone contact %",
    "trk_k_pct": "K% (tracked)", "trk_bb_pct": "BB% (tracked)",
    "trk_k_minus_bb": "K-BB% (tracked)", "trk_xwoba_against": "xwOBA against",
    "trk_ev_against": "Exit velo against", "trk_gb": "GB% (tracked)",
    "trk_whiff_fb": "Fastball whiff %", "trk_whiff_br": "Breaking-ball whiff %",
    "trk_whiff_os": "Offspeed whiff %", "trk_astuff_plus": "aStuff+",
    "trk_astuff_plus_fb": "aStuff+ fastballs", "trk_astuff_plus_br": "aStuff+ breaking balls",
    "trk_astuff_plus_os": "aStuff+ offspeed", "trk_ev_mean": "Exit velo (mean)",
    "trk_ev_p90": "Exit velo (90th pct)", "trk_ev_max": "Max exit velo",
    "trk_hard_hit": "Hard-hit %", "trk_barrel": "Barrel %", "trk_la_sd": "Launch angle spread",
    "trk_sweet_spot": "Sweet-spot %", "trk_xwoba": "xwOBA",
}
#: The tracking head's metric names -> the atlas's (side suffix added per side).
HEAD_METRIC = {"astuff_plus": "trk_astuff_plus", "fb_velo_p95": "trk_fb_velo_p95",
               "fb_ivb": "trk_fb_ivb", "xwoba_against": "trk_xwoba_against",
               "ev_against": "trk_ev_against", "arm_angle": "trk_arm_angle",
               "ev_p90": "trk_ev_p90", "hard_hit": "trk_hard_hit", "barrel": "trk_barrel",
               "chase": "trk_chase", "zone_contact": "trk_zone_contact"}
CHIP_STATES = {
    "live": "Used by eFV",
    "admitted": "Admitted, not live",
    "tested": "Tested, not admitted",
    "untested": "Not yet tested",
}
#: Every score, bound and q in a row is an integer in ten-thousandths (the atlas writes
#: 4 places), so the page divides by SCALE.
SCALE = 10000
#: The row columns, in order.
COLUMNS = ("m", "raw", "raw_lo", "raw_hi", "dir", "players", "pos", "incr", "incr_lo",
           "incr_hi", "q", "graded", "spent")


def _i(v):
    """A score in ten-thousandths (the atlas rounds to 4 places), None kept."""
    return None if v is None else int(round(float(v) * SCALE))


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def display_name(metric: str) -> str:
    base = re.sub(r"_(hit|pit)$", "", metric)
    rel = base.endswith("_rel") and base != "age_rel_level"
    if rel:
        base = base[: -len("_rel")]
    name = NAMES.get(base, base.replace("_", " "))
    return f"{name} vs age" if rel else name


def _flag(src: Path, name: str) -> bool | None:
    if not src.is_file():
        return None
    m = re.search(rf"^{name}\s*=\s*(True|False)\b", src.read_text(encoding="utf-8"), re.M)
    return None if not m else m.group(1) == "True"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def chip_rules(select: dict | None, spent: dict | None, head: dict | None,
               v5_on: bool | None, head_on: bool | None) -> list[dict]:
    """The admitted and tested lists, from the driver and head artifacts as written."""
    rules: list[dict] = []
    if select and isinstance(select.get("rule"), dict):
        cols = select["rule"].get("columns") or {}
        chosen = set()
        for side_add in ((select.get("selected") or {}).get("config") or {}).get("add", {}).values():
            for head_cols in side_add.values():
                chosen.update(head_cols)
        ships = bool(((spent or {}).get("ship_rule") or {}).get("ships"))
        for cid, c in cols.items():
            admitted = cid in chosen
            if admitted and v5_on and ships:
                state, why = "live", "an eFV v5 group driver, served"
            elif admitted:
                why = "chosen as an eFV v5 group driver on the development frames; "
                why += ("the selection failed its ship rule on the spent frames"
                        if spent and not ships else "the driver switch is off")
                state = "admitted"
            else:
                state, why = "tested", "offered to the eFV v5 group-driver selection and not chosen"
            rules.append({"side": c["side"], "metric": c["metric"], "level": c["level"],
                          "band": c["band"], "group": c["group"], "state": state,
                          "source": "group drivers", "why": why})
    if head and isinstance(head.get("weights"), dict):
        levels = (head.get("declared") or {}).get("levels") or []
        for side, ws in head["weights"].items():
            verdict = ((head.get("verdict") or {}).get(side) or {})
            by_metric: dict[str, bool] = {}
            for w in ws:
                by_metric[w["metric"]] = by_metric.get(w["metric"], False) or bool(w.get("carries_weight"))
            for hm, carries in by_metric.items():
                base = HEAD_METRIC.get(hm)
                if not base:
                    continue
                if carries and head_on and verdict.get("ships"):
                    state, why = "live", "carries weight in the tracking-era head, served"
                elif carries:
                    state = "admitted"
                    why = "carries weight in the tracking-era head (short-horizon label); "
                    why += ("the head passed its ship rule but its switch is off"
                            if verdict.get("ships") else "the head failed its ship rule")
                else:
                    state, why = "tested", "in the tracking-era head without carrying weight"
                for lv in levels:
                    rules.append({"side": side, "metric": f"{base}_{side}", "level": lv,
                                  "band": "*", "group": "*", "state": state,
                                  "source": "tracking-era head", "why": why})
    return rules


def _orient(score, lo, hi, binary: bool):
    """(score, lo, hi, direction) read at or above the no-relation line."""
    if score is None:
        return None, None, None, None
    mid = 0.5 if binary else 0.0
    if score >= mid:
        return score, lo, hi, 1
    flip = (lambda v: None if v is None else round(1.0 - v, 4)) if binary else \
           (lambda v: None if v is None else round(-v, 4))
    return flip(score), flip(hi), flip(lo), -1


def build_view(atlas: dict, cells: dict, rules: list[dict], *, atlas_sha: str | None = None,
               cells_sha: str | None = None) -> dict:
    cols = cells["columns"]
    ix = {c: i for i, c in enumerate(cols)}
    metric_ids = list(atlas["metrics"].keys())
    m_index = {m: i for i, m in enumerate(metric_ids)}
    labels = atlas["labels"]
    out_cells: dict[str, dict] = {}
    for r in cells["rows"]:
        g = lambda c: r[ix[c]]  # noqa: E731
        label = g("label")
        binary = labels[label]["kind"] == "binary"
        key = "|".join((g("side"), g("level"), g("age_band"), g("group"), label, g("frame")))
        cell = out_cells.setdefault(key, {"pop": g("population"), "players": 0, "pos": 0,
                                          "seasons": None, "cons": None, "cons_n": 0,
                                          "graded_players": 0, "spent": False,
                                          "rows": []})
        ci = g("raw_full_ci95") or [None, None]
        raw, lo, hi, d = _orient(g("raw_full"), ci[0], ci[1], binary)
        ici = g("incr_ci95") or [None, None]
        players = g("players_full")
        cell["players"] = max(cell["players"], players or 0)
        cell["pos"] = max(cell["pos"], g("pos_full") or 0)
        sf = g("seasons_full")
        if sf:
            s0, s1 = cell["seasons"] or sf
            cell["seasons"] = [min(s0, sf[0]), max(s1, sf[1])]
        nl = g("n_listed") or 0
        if g("consensus_raw") is not None and nl > cell["cons_n"]:
            cell["cons"], cell["cons_n"] = _i(g("consensus_raw")), nl
            cell["graded_players"] = g("players_listed") or 0
        spent = bool(g("reserved_overlap"))
        cell["spent"] = cell["spent"] or spent
        cell["rows"].append([m_index[g("metric")], _i(raw), _i(lo), _i(hi), d, players,
                             g("pos_full"), _i(g("incr")), _i(ici[0]), _i(ici[1]), _i(g("q")),
                             g("players_listed"), 1 if spent else 0])
    for cell in out_cells.values():
        cell["rows"].sort(key=lambda row: -(row[1] if row[1] is not None else -SCALE))
        cell.pop("cons_n", None)
    decl = atlas.get("declared", {})
    groups = atlas.get("groups", {})
    tests = len(cells["rows"])
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool": TOOL, "item": ITEM, "role": "development", "served_grade_moves": False,
        "note": ("display projection of the eFV v5 metric atlas: every number is the atlas's, "
                 "oriented for reading; nothing is fitted or selected here"),
        "source": {"artifact": "data/efv5_metric_atlas.json", "sha256": atlas_sha,
                   "generated_at": atlas.get("generated_at"), "cells_sha256": cells_sha,
                   "tests": tests, "candidates": len(atlas.get("candidates") or [])},
        "declared": {"min_players": decl.get("min_players"), "min_pos": decl.get("min_pos"),
                     "folds": decl.get("folds"), "bootstrap_b": atlas.get("bootstrap_b"),
                     "candidate_rule": decl.get("candidate_rule"),
                     "incremental": decl.get("incremental"), "interval": decl.get("interval"),
                     "age_bands": decl.get("age_bands"), "seasons": decl.get("seasons"),
                     "horizon": decl.get("horizon"),
                     "position_note": (decl.get("position_groups") or {}).get("note")},
        "spent_note": atlas.get("spent_note"),
        "labels": {k: {"name": LABEL_NAMES.get(k, k), "kind": labels[k]["kind"],
                       "horizon": labels[k]["horizon"], "what": labels[k]["what"],
                       "resolved": labels[k]["resolved"]}
                   for k in LABEL_ORDER if k in labels},
        "label_order": [k for k in LABEL_ORDER if k in labels],
        "frames": FRAME_NAMES,
        "levels": [lv for lv in decl.get("levels", []) if any(
            k.split("|")[1] == lv for k in out_cells)],
        "level_names": LEVEL_NAMES,
        "bands": groups.get("age_bands", ["all"]),
        "band_names": BAND_NAMES,
        "groups": {"hit": groups.get("hit", ["all"]), "pit": groups.get("pit", ["all"])},
        "group_names": groups.get("labels", {}),
        "families": FAMILY_NAMES,
        "metrics": [{"id": m, "name": display_name(m), "family": v["family"], "side": v["side"],
                     "what": v["what"]} for m, v in atlas["metrics"].items()],
        "chip_states": CHIP_STATES,
        "chips": rules,
        "columns": list(COLUMNS),
        "scale": SCALE,
        "cells": out_cells,
    }


def run(*, atlas_path: Path = ATLAS_PATH, out_path: Path = OUT_PATH,
        select_path: Path = GROUP_SELECT_PATH, spent_path: Path = GROUP_SPENT_PATH,
        head_path: Path = TRACKING_HEAD_PATH) -> dict:
    atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
    cells_path = ROOT / atlas["cells_file"]
    cells = json.loads(cells_path.read_text(encoding="utf-8"))
    rules = chip_rules(_load(select_path), _load(spent_path), _load(head_path),
                       _flag(GROUP_DRIVERS_SRC, "EFV_V5_ON"),
                       _flag(TRACKING_HEAD_SRC, "EFV_TRACKING_HEAD_ON"))
    view = build_view(atlas, cells, rules, atlas_sha=_sha(atlas_path), cells_sha=_sha(cells_path))
    out_path.write_text(json.dumps(view, separators=(",", ":")), encoding="utf-8")
    return view


def main(argv=None) -> int:
    view = run()
    n = sum(len(c["rows"]) for c in view["cells"].values())
    states: dict[str, int] = {}
    for r in view["chips"]:
        states[r["state"]] = states.get(r["state"], 0) + 1
    print(f"wrote {OUT_PATH.relative_to(ROOT)}: {len(view['cells'])} cells, {n} rows, "
          f"chips {states}, {OUT_PATH.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

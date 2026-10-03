# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eFV label pool census (EFV3_A1; EFV3_PLAN.md s3 'The label pool program',
LANE_A.md s1, s2 and s4). COUNTS ONLY.

Writes data/efv_label_pool_census.json, one dated census of every pool a label can be
drawn from, so the label pool program (A2 to A8) and the Source Comparison label-pool
panel read counts from one artifact instead of from a lane's notes:

  (a) snapshots   prospects.db `snapshots` rows and distinct FV-graded players per
                  source and list year, with the share read inside the Jan 1 to May 1
                  preseason window (source_backtest's window constants).
  (b) frame       F-LV row counts per side and vintage for the development vintages
                  and for 2022 and later, through efv_vintage_frame.build_frame with
                  milb=False and sidecars=False, with the outcome-blind id route
                  (id_how: name_unique, ambiguous, no_candidate) and record-id presence.
                  R-LV (2020, 2021) is NEVER built: its counts are copied from
                  docs/efv-v2/PROGRAM.md s2.4, and the reserved guard is called with no
                  sha and must raise before anything is counted.
  (c) debut_cohorts  data/debuts.json cohorts 2011 to 2026: debuts, rows with an
                  in-window consensus read, rows with FanGraphs and MLB Pipeline both,
                  rows with a career_war row.
  (d) bust_pool   data/inactive.json rows by efv_labels.reached_class, by (has id, has
                  birth date) and by last list year.
  (e) identity_join  career_war rows by provider (the stored `source`) and by id route
                  (debuts.json id, data/sources/mlbam_id_overrides.json, none).
  (f) label_views  for L6, W3, W2, R3 and first-2, which vintages or cohorts resolve at
                  RESOLVED_THROUGH and at RESOLVED_THROUGH + 1 (counts only), with the
                  label-only faithfulness numbers COPIED out of docs/efv-v2/PROGRAM.md
                  s2.2 and s3.3 (parsed from the committed text, sha256 stamped).
  (g) floor_curve  mde95(n) = Z95 * sd_ref * sqrt(n_ref / n) per frame type, sd_ref
                  copied from data/efv_v2_dev_eval.json ds16 (E_cond) and
                  data/xfv_headtohead_frame_eval.json vintage_matched (E_refit), each
                  with its path and sha256.

NO RATER SCORE is computed anywhere in this module: no grade meets an outcome, no
Spearman, AUC or delta exists in the artifact; the only statistics it carries are
label-to-label faithfulness numbers copied from committed documents. Nothing is
grouped by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md). The 39 closed arms
(data/xfv_arm_ledger.json) are not re-run. The eFV label is in an epoch
(docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md): the census stamps resolved_through and
war_source.DEFAULT_PROVIDER, so a post-epoch run is a new census, never an edit.

The ledger: one development row in data/efv_progress.json (model_id efv_label_pool,
raters {} and deltas {}, resolvable None, note 'label pool census, no score'), so the
progress ledger shows the census date beside the reads; the chart draws nothing from
it (no consensus leg).

Run:  python tools/efv_label_pool_census.py --write        (artifact + ledger row)
      python tools/efv_label_pool_census.py                (print the summary only)
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_dataset as D  # noqa: E402
import efv_labels as L  # noqa: E402
import efv_progress as P  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import source_backtest as SB  # noqa: E402
import war_source  # noqa: E402

OUT = ROOT / "data" / "efv_label_pool_census.json"
DB = ROOT / "prospects.db"
DEBUTS = ROOT / "data" / "debuts.json"
INACTIVE = ROOT / "data" / "inactive.json"
OVERRIDES = ROOT / "data" / "sources" / "mlbam_id_overrides.json"
PROGRAM_DOC = ROOT / "docs" / "efv-v2" / "PROGRAM.md"
DS16_PATH = ROOT / "data" / "efv_v2_dev_eval.json"
H2H_PATH = ROOT / "data" / "xfv_headtohead_frame_eval.json"

MODEL_ID = "efv_label_pool"
LEDGER_FRAME = "lv_dev"
LEDGER_NOTE = "label pool census, no score"

#: The only names a grouping may carry (the test whitelist).
STRATA = ("source", "list_year", "vintage", "side", "debut_cohort", "id_how",
          "bust_class", "label_view")

#: Debut cohorts the census counts (c). 2010 debuts exist in debuts.json but sit
#: outside efv_dataset.DEBUT_YEARS and are reported as such.
COHORT_FIRST, COHORT_LAST = 2011, 2026
#: Vintages built on top of DEV_VINTAGES: 2022 to the current season. R-LV is
#: never in this tuple; `check_reserved_guard` proves the guard raises for it.
LATER_VINTAGES: tuple[int, ...] = tuple(range(2022, D.CURRENT_SEASON + 1))
VINTAGES_BUILT: tuple[int, ...] = tuple(F.DEV_VINTAGES) + LATER_VINTAGES
assert not (set(VINTAGES_BUILT) & set(F.RESERVED_LV))

#: The n the floor curve is drawn at (LANE_A.md s2: vm2 today, the both-source and
#: consensus-present ceilings, the 2027 run, the R-VM releases, the Pipeline panel,
#: the n for a 0.02 lead, R-VM look 1 at three rules, R-LV, lv_dev plus R-LV).
N_CURVE: tuple[int, ...] = (829, 858, 995, 1179, 1266, 1464, 1864, 149, 176, 210,
                            2667, 5529)
Z95 = float(SB._Z95)

ID_ROUTES = ("debuts_json_id", "override_asset_id", "no_id", "key_not_in_debuts")
WINDOW_MMDD = (SB._WINDOW_START_MMDD, SB._WINDOW_END_MMDD)


# ---------------------------------------------------------------------------
# helpers

def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=False, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _year(s) -> int | None:
    s = str(s or "")
    return int(s[:4]) if len(s) >= 4 and s[:4].isdigit() else None


# ---------------------------------------------------------------------------
# the reserved guard, called first and with no sha

def check_reserved_guard() -> dict:
    """Call the guard for every reserved list vintage with no sha. It must raise;
    the census records that it did and never builds those vintages."""
    out = {}
    for v in sorted(F.RESERVED_LV):
        try:
            F.guard_score_request(int(v), gate_sha=None, purpose="census")
        except F.ReservedFrameError:
            out[str(v)] = "ReservedFrameError"
            continue
        raise RuntimeError(f"reserved vintage {v} did not raise; census refused")
    return out


# ---------------------------------------------------------------------------
# (a) snapshots

def snapshots_census(db: Path = DB) -> dict:
    lo, hi = WINDOW_MMDD
    sql = """
        SELECT source, substr(snapshot_date, 1, 4) AS list_year,
               COUNT(*),
               SUM(fv IS NOT NULL),
               COUNT(DISTINCT CASE WHEN fv IS NOT NULL THEN player_key END),
               SUM(fv IS NOT NULL AND substr(snapshot_date, 5, 6) >= ?
                   AND substr(snapshot_date, 5, 6) < ?),
               COUNT(DISTINCT CASE WHEN fv IS NOT NULL
                     AND substr(snapshot_date, 5, 6) >= ?
                     AND substr(snapshot_date, 5, 6) < ? THEN player_key END),
               MIN(snapshot_date), MAX(snapshot_date)
        FROM snapshots GROUP BY source, list_year ORDER BY source, list_year"""
    non_rater = set(SB._NON_RATER_SOURCES)
    constant = set(D._constant_anchor_sources())
    rows = []
    with sqlite3.connect(str(db)) as con:
        total = con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        for (src, y, n, n_fv, players, n_fv_win, players_win, first,
             last) in con.execute(sql, (lo, hi, lo, hi)):
            n_fv = int(n_fv or 0)
            rows.append({
                "source": src, "list_year": int(y) if str(y).isdigit() else None,
                "rows": int(n), "fv_rows": n_fv, "fv_players": int(players or 0),
                "fv_rows_in_window": int(n_fv_win or 0),
                "fv_players_in_window": int(players_win or 0),
                "in_window_share": (round(int(n_fv_win or 0) / n_fv, 4)
                                    if n_fv else None),
                "first_snapshot": first, "last_snapshot": last,
                "real_grader": src not in non_rater and src not in constant})
    by_source: dict[str, dict] = {}
    for r in rows:
        b = by_source.setdefault(r["source"], {"rows": 0, "fv_rows": 0, "first": None,
                                               "last": None, "list_years": []})
        b["rows"] += r["rows"]
        b["fv_rows"] += r["fv_rows"]
        b["first"] = min(x for x in (b["first"], r["first_snapshot"]) if x)
        b["last"] = max(x for x in (b["last"], r["last_snapshot"]) if x)
        if r["fv_rows"] and r["list_year"] is not None:
            b["list_years"].append(r["list_year"])
    return {"source_table": "prospects.db snapshots", "snapshot_rows": int(total),
            "window_mmdd": list(WINDOW_MMDD),
            "rule": ("a row is FV-graded when its fv column is set; the window is "
                     "source_backtest's preseason window on the snapshot date; "
                     "real_grader is False for the non-rater and constant-anchor "
                     "sources"),
            "by": ["source", "list_year"], "rows": rows, "by_source": by_source}


# ---------------------------------------------------------------------------
# (b) the frame

def _program_rlv_counts(text: str) -> dict:
    m = re.search(r"V 2020 \(W3 resolvable now: ([\d,]+) hit / ([\d,]+) pit rows\) and "
                  r"V 2021 \([^)]*?: ([\d,]+) / ([\d,]+)\)", text)
    if not m:
        raise RuntimeError("PROGRAM.md s2.4 R-LV counts not found; census refused")
    g = [int(x.replace(",", "")) for x in m.groups()]
    return {"2020": {"hit": g[0], "pit": g[1], "rows": g[0] + g[1]},
            "2021": {"hit": g[2], "pit": g[3], "rows": g[2] + g[3]},
            "quote": m.group(0)}


def frame_census(universe: dict | None = None, *, vintages=VINTAGES_BUILT,
                 program_text: str | None = None) -> dict:
    """F-LV rows per (side, vintage) through build_frame(milb=False, sidecars=False);
    reserved vintages are never built and are copied from PROGRAM.md s2.4."""
    bad = sorted(set(int(v) for v in vintages) & set(F.RESERVED_LV))
    if bad:
        raise F.ReservedFrameError(f"census asked to build reserved vintages {bad}")
    universe = universe if universe is not None else F.load_universe()
    rows = []
    for v in vintages:
        for side in F.SIDES:
            fr = F.build_frame(side, int(v), universe=universe, milb=False,
                               sidecars=False)
            how = collections.Counter(r.get("id_how") for r in fr)
            rows.append({
                "side": side, "vintage": int(v), "rows": len(fr),
                "id_how": {"name_unique": how.get("name_unique", 0),
                           "name_side": how.get("name_side", 0),
                           "name_recency": how.get("name_recency", 0),
                           "ambiguous": how.get("ambiguous", 0),
                           "no_candidate": how.get("no_candidate", 0),
                           "other": sum(c for k, c in how.items() if k not in
                                        ("name_unique", "name_side", "name_recency",
                                         "ambiguous", "no_candidate"))},
                "blind_id_present": sum(1 for r in fr if r.get("mlbam_id")),
                "record_id_present": sum(1 for r in fr if r.get("record_mlbam_id")),
                "with_consensus": sum(1 for r in fr
                                      if r["grades"].get(SB.CONSENSUS_KEY) is not None),
                "built": True})
    text = program_text if program_text is not None else \
        PROGRAM_DOC.read_text(encoding="utf-8")
    rlv = _program_rlv_counts(text)
    for v in sorted(F.RESERVED_LV):
        for side in F.SIDES:
            rows.append({"side": side, "vintage": int(v), "rows": rlv[str(v)][side],
                         "id_how": None, "blind_id_present": None,
                         "record_id_present": None, "with_consensus": None,
                         "built": False,
                         "copied_from": {"path": "docs/efv-v2/PROGRAM.md",
                                         "section": "s2.4"}})
    rows.sort(key=lambda r: (r["vintage"], r["side"]))
    dev = [r for r in rows if r["vintage"] in F.DEV_VINTAGES]
    dev_totals = {
        "vintages": [int(v) for v in F.DEV_VINTAGES],
        "rows": sum(r["rows"] for r in dev),
        "by_side": {s: sum(r["rows"] for r in dev if r["side"] == s) for s in F.SIDES},
        "id_how": {k: sum(r["id_how"][k] for r in dev)
                   for k in ("name_unique", "name_side", "name_recency", "ambiguous",
                             "no_candidate", "other")},
        "record_id_present": sum(r["record_id_present"] for r in dev)}
    later = [r for r in rows if r["vintage"] in LATER_VINTAGES]
    return {"by": ["side", "vintage"],
            "builder": "efv_vintage_frame.build_frame(side, V, milb=False, sidecars=False)",
            "rule": ("a row is a (player, V) with a real grader published inside the V "
                     "preseason window and no major league line before V; id_how is "
                     "the outcome-blind resolver's route (efv_identity), record_id "
                     "is the record's stored id (audit only, never an input)"),
            "rows": rows, "dev_totals": dev_totals,
            "later_totals": {"vintages": list(LATER_VINTAGES),
                             "rows": sum(r["rows"] for r in later)},
            "reserved_copied": {"vintages": sorted(F.RESERVED_LV),
                                "path": "docs/efv-v2/PROGRAM.md", "section": "s2.4",
                                "sha256": _sha(PROGRAM_DOC) if program_text is None else None,
                                "quote": rlv["quote"],
                                "rows": rlv["2020"]["rows"] + rlv["2021"]["rows"]}}


# ---------------------------------------------------------------------------
# (c) debut cohorts

def _window_reads(rec: dict, year: int) -> tuple[bool, set[str]]:
    """(an in-window consensus read exists, real sources published in the window)
    for the debut year's preseason window, closed at the debut day."""
    lo, hi = F.window_bounds(year, str(rec.get("debut_date") or "")[:10] or None)
    cons, srcs = False, set()
    for p in rec.get("points") or []:
        sd = str(p.get("snapshot_date") or "")[:10]
        if not (lo <= sd < hi):
            continue
        if p.get("consensus_fv") is not None:
            cons = True
        for s, ps in (p.get("per_source") or {}).items():
            if (ps or {}).get("fv_published") is not None:
                srcs.add(s)
    return cons, srcs


def debut_cohorts_census(debuts: list[dict] | None = None,
                         career_war_keys: set[str] | None = None) -> dict:
    debuts = debuts if debuts is not None else _load(DEBUTS)
    if career_war_keys is None:
        career_war_keys = set(war_source.career_war_table().keys())
    both = set(SB.SCORED_SOURCES)
    acc: dict[int, dict] = {}
    outside = collections.Counter()
    undated = 0
    for rec in debuts:
        y = _year(rec.get("debut_date"))
        if y is None:
            undated += 1
            continue
        if not (COHORT_FIRST <= y <= COHORT_LAST):
            outside[str(y)] += 1
            continue
        a = acc.setdefault(y, collections.Counter())
        a["debuts"] += 1
        cons, srcs = _window_reads(rec, y)
        a["in_window_consensus_read"] += int(cons)
        a["fangraphs_and_pipeline_both"] += int(both <= srcs)
        a["with_career_war_row"] += int(rec.get("player_key") in career_war_keys)
        a["with_record_id"] += int(bool(rec.get("mlbam_id")))
    rows = []
    for y in range(COHORT_FIRST, COHORT_LAST + 1):
        a = acc.get(y) or collections.Counter()
        rows.append({"debut_cohort": y,
                     "debuts": a["debuts"],
                     "in_window_consensus_read": a["in_window_consensus_read"],
                     "fangraphs_and_pipeline_both": a["fangraphs_and_pipeline_both"],
                     "with_career_war_row": a["with_career_war_row"],
                     "with_record_id": a["with_record_id"],
                     "reserved_vm": y >= F.R_VM_FIRST_DEBUT_YEAR})
    return {"by": ["debut_cohort"], "source_file": "data/debuts.json",
            "window": "the debut year's preseason window (efv_vintage_frame.window_bounds), closed at the debut day",
            "rule": ("in_window_consensus_read: a point inside the window with a "
                     "consensus_fv; fangraphs_and_pipeline_both: both SCORED_SOURCES "
                     "published an fv inside the window; with_career_war_row: the "
                     "player_key has a career_war row (presence only, no value read)"),
            "rows": rows, "records": len(debuts), "undated": undated,
            "outside_cohort_range": dict(outside),
            "r_vm_first_debut_year": int(F.R_VM_FIRST_DEBUT_YEAR)}


# ---------------------------------------------------------------------------
# (d) the bust pool

def bust_pool_census(inactive: list[dict] | None = None,
                     war: dict[str, dict[int, float]] | None = None) -> dict:
    inactive = inactive if inactive is not None else _load(INACTIVE)
    war = war if war is not None else L.war_seasons_table()
    by_class = collections.Counter()
    by_class_id_birth: dict[str, collections.Counter] = {}
    by_class_year: dict[str, collections.Counter] = {}
    by_class_noid_year: dict[str, collections.Counter] = {}
    for rec in inactive:
        cls = L.reached_class(rec, war.get(rec.get("player_key")))
        has_id = bool(rec.get("mlbam_id"))
        has_bd = bool(rec.get("birth_date"))
        years = [_year(p.get("snapshot_date")) for p in (rec.get("points") or [])]
        years = [y for y in years if y is not None]
        last = str(max(years)) if years else "none"
        by_class[cls] += 1
        key = f"id_{int(has_id)}_birth_{int(has_bd)}"
        by_class_id_birth.setdefault(cls, collections.Counter())[key] += 1
        by_class_year.setdefault(cls, collections.Counter())[last] += 1
        if not has_id and not has_bd:
            by_class_noid_year.setdefault(cls, collections.Counter())[last] += 1
    rows = [{"bust_class": c, "rows": by_class[c],
             "by_id_birth": dict(sorted(by_class_id_birth.get(c, {}).items())),
             "by_last_list_year": dict(sorted(by_class_year.get(c, {}).items())),
             "no_id_no_birth_by_last_list_year":
                 dict(sorted(by_class_noid_year.get(c, {}).items()))}
            for c in ("never", "censored_never", "reached")]
    return {"by": ["bust_class"], "source_file": "data/inactive.json",
            "classifier": "efv_labels.reached_class (BUST2)",
            "latest_milb_seasons": list(L.latest_milb_seasons(2)),
            "rule": ("id_1_birth_1 means the record carries an mlbam_id and a birth "
                     "date; the last list year is the latest snapshot year on the "
                     "record's points; the no-id no-birth rows flip to never when "
                     "that year is at or before RESOLVED_THROUGH - NEVER_LIST_LAG"),
            "never_list_lag": int(L.NEVER_LIST_LAG), "never_age": int(L.NEVER_AGE),
            "rows": rows, "records": len(inactive)}


# ---------------------------------------------------------------------------
# (e) the identity join at the epoch

def identity_join_census(table: dict[str, dict] | None = None,
                         debuts: list[dict] | None = None,
                         overrides: dict | None = None) -> dict:
    table = table if table is not None else war_source.career_war_table()
    debuts = debuts if debuts is not None else _load(DEBUTS)
    overrides = overrides if overrides is not None else _load(OVERRIDES)
    deb_id = {r.get("player_key"): bool(r.get("mlbam_id")) for r in debuts
              if r.get("player_key")}
    by_provider: dict[str, dict] = {}
    for pk, agg in table.items():
        prov = str((agg or {}).get("source") or "unknown")
        if pk in deb_id and deb_id[pk]:
            route = "debuts_json_id"
        elif pk in overrides:
            route = "override_asset_id"
        elif pk in deb_id:
            route = "no_id"
        else:
            route = "key_not_in_debuts"
        b = by_provider.setdefault(prov, {"rows": 0, "id_route": {r: 0 for r in ID_ROUTES}})
        b["rows"] += 1
        b["id_route"][route] += 1
    debuts_no_id = sum(1 for v in deb_id.values() if not v)
    covered = sum(1 for k, v in deb_id.items() if not v and k in overrides)
    return {"source_table": "prospects.db career_war",
            "default_provider": str(war_source.DEFAULT_PROVIDER),
            "rule": ("provider is the stored row's source field; the id route is the "
                     "first of: the debuts.json record carries an mlbam_id, the key "
                     "is in data/sources/mlbam_id_overrides.json, the key is in "
                     "debuts.json without an id, the key is not in debuts.json"),
            "rows": len(table), "by_provider": by_provider,
            "debuts_records_without_id": debuts_no_id,
            "debuts_without_id_covered_by_override_asset": covered,
            "override_asset": {"path": "data/sources/mlbam_id_overrides.json",
                               "entries": len(overrides), "sha256": _sha(OVERRIDES)}}


# ---------------------------------------------------------------------------
# (f) label views

def _program_faithfulness(text: str) -> dict:
    w3 = re.search(r"rho\(W3, six-season\) ([0-9.]+) hit / ([0-9.]+)\s+pit", text)
    f2 = re.search(r"first-2 vs six-season ([0-9.]+) hit / ([0-9.]+) pit", text)
    if not (w3 and f2):
        raise RuntimeError("PROGRAM.md faithfulness numbers not found; census refused")
    return {"w3": {"hit": float(w3.group(1)), "pit": float(w3.group(2)),
                   "section": "s2.2", "quote": w3.group(0)},
            "first_2": {"hit": float(f2.group(1)), "pit": float(f2.group(2)),
                        "section": "s3.3", "quote": f2.group(0)}}


def label_views_census(frame: dict, cohorts: dict, *, resolved_through: int | None = None,
                       program_text: str | None = None) -> dict:
    rt = int(resolved_through if resolved_through is not None else L.resolved_through())
    text = program_text if program_text is not None else \
        PROGRAM_DOC.read_text(encoding="utf-8")
    faith = _program_faithfulness(text)
    doc_ref = {"path": "docs/efv-v2/PROGRAM.md",
               "sha256": _sha(PROGRAM_DOC) if program_text is None else None}
    v_rows = {}
    for r in frame["rows"]:
        v_rows[r["vintage"]] = v_rows.get(r["vintage"], 0) + r["rows"]
    c_rows = {r["debut_cohort"]: r for r in cohorts["rows"]}

    def vint(lag: int, at: int) -> dict:
        vs = sorted(v for v in v_rows if v + lag <= at)
        return {"vintages": vs, "rows": sum(v_rows[v] for v in vs),
                "reserved_lv_inside": sorted(set(vs) & set(F.RESERVED_LV))}

    def coh(lag: int, at: int) -> dict:
        cs = sorted(c for c in c_rows if c + lag <= at)
        return {"debut_cohorts": cs,
                "debuts": sum(c_rows[c]["debuts"] for c in cs),
                "with_career_war_row": sum(c_rows[c]["with_career_war_row"] for c in cs),
                "reserved_vm_inside": [c for c in cs if c_rows[c]["reserved_vm"]]}

    def added(a: dict, b: dict, key: str) -> dict:
        keys = [k for k in b[key] if k not in a[key]]
        n_key = "rows" if key == "vintages" else "debuts"
        return {key: keys, n_key: b[n_key] - a[n_key]}

    w3_lag = L.W_DEBUT_WINDOW + L.W3_SEASONS - 1
    w2_lag = L.W_DEBUT_WINDOW + L.W2_SEASONS - 1
    r3_lag = L.W_DEBUT_WINDOW
    l6_lag = int(D.TARGET_SEASONS) - 1
    f2_lag = 1
    rows = []

    def view(name, definition, unit, lag, standing, faithfulness):
        if unit == "vintage":
            a, b = vint(lag, rt), vint(lag, rt + 1)
            add = added(a, b, "vintages")
        else:
            a, b = coh(lag, rt), coh(lag, rt + 1)
            add = added(a, b, "debut_cohorts")
        rows.append({"label_view": name, "definition": definition, "unit": unit,
                     "resolves_when": (f"V + {lag} <= RESOLVED_THROUGH" if unit == "vintage"
                                       else f"debut year + {lag} <= RESOLVED_THROUGH"),
                     "resolved_at_rt": a, "resolved_at_rt_plus_1": b,
                     "added_at_rt_plus_1": add, "standing": standing,
                     "faithfulness_to_six_season": faithfulness})

    view("L6", "first six MLB seasons, censored tail projected (efv_dataset._label_6yr)",
         "debut_cohort", l6_lag, "the training label and F-VM scoring label",
         {"hit": None, "pit": None, "note": "the six-season label itself"})
    view("W3", "WAR over the first three MLB seasons, 0 if no debut in V..V+3",
         "vintage", w3_lag, "the F-LV scoring label",
         dict(faith["w3"], **doc_ref))
    view("W2", "WAR over the first two MLB seasons, 0 if no debut in V..V+3",
         "vintage", w2_lag, "hazard component, not a scoring label",
         {"hit": None, "pit": None, "section": "s2.2",
          "note": "PROGRAM.md s2.2: W2, R3 and AA2 lose the grader ordering or are hazard components; not scoring labels"})
    view("R3", "reached within V..V+3", "vintage", r3_lag,
         "timing-head target only, not a scoring label",
         {"hit": None, "pit": None, "section": "s2.2",
          "note": "PROGRAM.md s2.2: W2, R3 and AA2 lose the grader ordering or are hazard components; not scoring labels"})
    view("first_2", "two observed seasons from the debut (R-VM look 1, L-D)",
         "debut_cohort", f2_lag, "the R-VM look-1 label by design",
         dict(faith["first_2"], **doc_ref))
    return {"by": ["label_view"], "resolved_through": rt,
            "rule": ("counts only: a vintage's rows are the frame rows of (b) (R-LV "
                     "copied, never built); a cohort's debuts are the rows of (c); "
                     "faithfulness numbers are parsed from the committed PROGRAM.md "
                     "text and are label-to-label, no rater enters"),
            "rows": rows}


# ---------------------------------------------------------------------------
# (g) the floor curve

def floor_references(ds16: dict | None = None, h2h: dict | None = None) -> list[dict]:
    ds16 = ds16 if ds16 is not None else _load(DS16_PATH).get("ds16")
    h2h = h2h if h2h is not None else _load(H2H_PATH)
    refs = []
    for fid, frame_type in (("vm_dev", "vm"), ("lv_dev", "lv")):
        leg = ds16["frames"][fid]["deltas"]["v2_vs_prospx_consensus"]["spearman"]
        refs.append({"id": f"{frame_type}_econd_within", "frame_type": frame_type,
                     "estimator": str(leg.get("estimator")),
                     "statistic": str(leg.get("statistic")),
                     "sd_ref": float(leg["sd"]), "n_ref": int(leg["n"]),
                     "n_clusters_ref": leg.get("n_clusters"),
                     "path": "data/efv_v2_dev_eval.json",
                     "key": f"ds16.frames.{fid}.deltas.v2_vs_prospx_consensus.spearman.sd",
                     "generated_at": ds16.get("generated_at"),
                     "sha256": _sha(DS16_PATH)})
    vm = h2h["vintage_matched"]
    refs.append({"id": "vm_erefit_pooled", "frame_type": "vm", "estimator": "E_refit",
                 "statistic": "pooled", "sd_ref": float(vm["sd"]),
                 "n_ref": int(h2h["point"]["vintage_matched"]["n_rows"]),
                 "n_clusters_ref": None,
                 "path": "data/xfv_headtohead_frame_eval.json",
                 "key": "vintage_matched.sd (n from point.vintage_matched.n_rows)",
                 "generated_at": h2h.get("generated_at"), "sha256": _sha(H2H_PATH)})
    return refs


def mde95_at(sd_ref: float, n_ref: int, n: int) -> float:
    return round(Z95 * float(sd_ref) * math.sqrt(float(n_ref) / float(n)), 4)


def floor_curve(refs: list[dict], ns=N_CURVE) -> dict:
    curve = {r["id"]: {str(n): mde95_at(r["sd_ref"], r["n_ref"], n) for n in ns}
             for r in refs}
    return {"z95": Z95, "formula": "mde95(n) = z95 * sd_ref * sqrt(n_ref / n)",
            "rule": ("the scaling PROGRAM.md s2.5 already uses; a floor of a different "
                     "frame type is not a function of n alone (LANE_A.md s2); the lv "
                     "E_refit floor is unmeasured (EV-05 owes it) and is not drawn"),
            "n": list(ns), "references": refs, "curve": curve}


# ---------------------------------------------------------------------------
# the document

def build(*, universe: dict | None = None, now: datetime | None = None) -> dict:
    guard = check_reserved_guard()
    now = now or datetime.now(timezone.utc)
    frame = frame_census(universe)
    cw = war_source.career_war_table()
    cohorts = debut_cohorts_census(career_war_keys=set(cw.keys()))
    doc = {
        "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "produced_by": "tools/efv_label_pool_census.py",
        "model_id": MODEL_ID,
        "role": "development",
        "adjudicates": "nothing; a census of the label pool, counts only, no score",
        "label": {"provider": L.provider(), "resolved_through": L.resolved_through(),
                  "resolved_through_plus_1": L.resolved_through() + 1,
                  "id": P.current_model_version().get("label")},
        "guards": {"reserved_lv": sorted(F.RESERVED_LV),
                   "reserved_lv_guard_called_without_sha": guard,
                   "r_vm_first_debut_year": int(F.R_VM_FIRST_DEBUT_YEAR),
                   "reserved_vm_pins": F.reserved_vm_pins(),
                   "vintages_built": list(VINTAGES_BUILT),
                   "no_rater_score": True,
                   "anchor_gate": "nothing grouped by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md)"},
        "strata": list(STRATA),
        "code": {"commit": _git_commit(), "tool_sha256": _sha(Path(__file__)),
                 "frame_module_sha256": _sha(ROOT / "efv_vintage_frame.py"),
                 "resolver_sha256": _sha(ROOT / "efv_identity.py")},
        "snapshots": snapshots_census(),
        "frame": frame,
        "debut_cohorts": cohorts,
        "bust_pool": bust_pool_census(),
        "identity_join": identity_join_census(table=cw),
        "label_views": label_views_census(frame, cohorts),
        "floor_curve": floor_curve(floor_references()),
        "epoch": ("the eFV label is in an epoch (docs/efv-2026-09-17/"
                  "FWAR_LABEL_EPOCH_GATE.md); label.provider and label.resolved_through "
                  "stamp this census, and a run after the epoch is a new census, never "
                  "an edit of this one"),
    }
    return doc


def ledger_row(doc: dict, artifact_path: Path, *, now_iso: str,
               trigger: str = "efv_change") -> dict:
    """The one development row: counts, no rater, no delta, resolvable None."""
    tot = doc["frame"]["dev_totals"]
    row = {"run_id": None, "date": doc["generated_at"][:10], "trigger": trigger,
           "model_id": MODEL_ID,
           "model_version": {"fingerprint": None, "commit": (doc["code"].get("commit") or "")[:8] or None,
                             "label": doc["label"].get("id"),
                             "resolved_through": doc["label"]["resolved_through"],
                             "provider": doc["label"]["provider"]},
           "frame": LEDGER_FRAME, "frame_version": None,
           "role": P.FRAMES[LEDGER_FRAME]["role"],
           "tilted": bool(P.FRAMES[LEDGER_FRAME]["tilted"]),
           "window": [tot["vintages"][0], tot["vintages"][-1]],
           "n": tot["rows"], "n_by_side": {s: tot["by_side"][s] for s in P.STRATA},
           "raters": {}, "deltas": {}, "resolvable": None,
           "verdict": "counts only, no score", "share": None,
           "sources": [{"path": P._rel(Path(artifact_path)),
                        "generated_at": doc["generated_at"],
                        "sha256": _sha(artifact_path)}],
           "note": LEDGER_NOTE, "last_verified_at": now_iso}
    row["content_hash"] = P.content_hash(row)
    row["run_id"] = f"{doc['generated_at']}|{LEDGER_FRAME}|{row['content_hash'][:8]}"
    return row


def write_artifact(doc: dict, out: Path = OUT) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def append_ledger(doc: dict, artifact_path: Path, *, data_dir=None, out_path=None,
                  ledger_path=None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    now_iso = P._now_iso(now)
    sb_path = (Path(data_dir) if data_dir else P.DATA_DIR) / P.SB_NAME
    sb = P._load_json(sb_path) if sb_path.exists() else None
    row = ledger_row(doc, artifact_path, now_iso=now_iso)
    return P.commit_rows([row], data_dir=data_dir, out_path=out_path,
                         ledger_path=ledger_path, sb=sb, now_iso=now_iso)


def summary(doc: dict) -> dict:
    tot = doc["frame"]["dev_totals"]
    return {"generated_at": doc["generated_at"], "label": doc["label"],
            "snapshot_rows": doc["snapshots"]["snapshot_rows"],
            "dev_frame_rows": tot["rows"], "dev_id_how": tot["id_how"],
            "later_frame_rows": doc["frame"]["later_totals"]["rows"],
            "reserved_copied_rows": doc["frame"]["reserved_copied"]["rows"],
            "career_war_rows": doc["identity_join"]["rows"],
            "bust_pool": {r["bust_class"]: r["rows"] for r in doc["bust_pool"]["rows"]}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true",
                    help="write the artifact and append the ledger row")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--no-ledger", action="store_true",
                    help="with --write: write the artifact only")
    ap.add_argument("--ledger-path", default=None,
                    help="the durable ledger copy (default efv_progress.LEDGER_PATH)")
    args = ap.parse_args(argv)
    doc = build()
    print(json.dumps(summary(doc), indent=1))
    if not args.write:
        return 0
    out = write_artifact(doc, Path(args.out))
    print(f"wrote {out}")
    if not args.no_ledger:
        res = append_ledger(doc, out, ledger_path=args.ledger_path)
        print(json.dumps({"ledger": res}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

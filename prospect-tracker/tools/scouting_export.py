# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /scouting/ page payload (TL_22_SCOUTING_PAGE_BUILD_DARK).

Spec: docs/scouting-2026-10/SCOUTING_PAGE.md (sections 2 to 7). Writes one JSON
payload with four blocks and a sources array:

  scale       the 20-80 adjective table: grade, SD from average, and each outlet's
              term, transcribed (framework 1.1, 1.3, 11.1, 11.2).
  fv_tiers    WAR by FV tier. Quantity A ('If he arrives'): the published role
              and WAR tables plus value_framework.fv_to_prime_war(g). Quantity B
              ('Expected, bust-inclusive'): the published Clemens tables plus
              value_framework.fv_to_6yr_avg_war(g) and
              value_framework.p_bucket_given_fv(g, is_pitcher), g in 20 to 80 by 5.
              Every cell says 'industry' or 'served_config'.
  tool_tiers  the FanGraphs framework estimate per tool tier (framework 2.1, 2.2),
              plus a measured column only where the Part T record of
              data/tool_tables_rederived_eval.json says PASS for that cell.
  sources     every number's registry row id, the file or function read, and the
              framework section and source id for transcribed values.

THE GUARD (SCOUTING_PAGE.md section 3 and test 3; test_scouting_page.py scans
this file with ast). This module imports the standard library and
value_framework, nothing else, and calls ONLY value_framework.fv_to_prime_war,
value_framework.fv_to_6yr_avg_war and value_framework.p_bucket_given_fv. It
reads no player row, groups nothing by grade, and names no fit or anchor file:
the served functions are the one door to the served tables.

THE FLAG. build_site.SCOUTING_PAGE_LIVE (default False). This module may not
import build_site, so it reads the flag's literal from build_site.py's source.
While it is False the payload lands only at PREVIEW_PATH under
.cache/scouting/preview/; nothing under data/ changes.

The output is deterministic (no clock), so two runs on the same inputs write the
same bytes.

Run: python tools/scouting_export.py [--print]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import value_framework as vf  # noqa: E402

TABLES_PATH = ROOT / "data" / "reference" / "fv_framework_tables.json"
TOOL_EVAL_PATH = ROOT / "data" / "tool_tables_rederived_eval.json"
OUT_PATH = ROOT / "data" / "scouting_reference.json"
PREVIEW_PATH = ROOT / ".cache" / "scouting" / "preview" / "scouting_reference.json"
BUILD_SITE_PATH = ROOT / "build_site.py"

SCHEMA = 1
GRADES = tuple(range(20, 81, 5))          # the FV and tool tiers the page prints
SCALE_GRADES = tuple(range(80, 19, -5))   # section A, top down

# Copy constants that mirror value_framework_config.yaml (test 11 reads the yaml;
# this module never does). The prime table starts at FV 35; below it the served
# function clamps, and a clamp is not a value, so those rows print 'no table'.
PRIME_TABLE_MIN_FV = 35
# The five buckets in yaml order: (key, yaml band, Clemens 2025 name, band words).
BUCKETS = (
    ("bust", "<0.5", "Washed out", "under 0.5 WAR"),
    ("bench", "0.5-1.5", "Backup", "0.5 to 1.5"),
    ("regular", "1.5-2.5", "Regular", "1.5 to 2.5"),
    ("good", "2.5-4.0", "Above average", "2.5 to 4"),
    ("star", "4.0+", "Star", "4+"),
)

# The registry rows TL_20 registered for this page (SCOUTING_PAGE.md section 6).
SOURCES = (
    {"id": "scale_terms", "block": "scale", "registry_row": "scouting_reference",
     "read": "transcription", "framework_section": ["1.3", "11.1", "11.2"],
     "source_id": ["S3", "B1", "P1"]},
    {"id": "scale_sd", "block": "scale", "registry_row": "scouting_reference",
     "read": "the scale's definition, (grade - 50) / 10", "framework_section": ["1.1"],
     "source_id": ["S3"]},
    {"id": "fv_roles", "block": "fv_tiers", "registry_row": "scouting_reference",
     "read": "transcription", "framework_section": ["3.1"], "source_id": ["S3"]},
    {"id": "fv_prime_war", "block": "fv_tiers", "registry_row": "scouting_reference",
     "read": "value_framework.fv_to_prime_war",
     "note": "a served display config of industry shape; no other registry row serves it"},
    {"id": "fv_six_yr_war", "block": "fv_tiers", "registry_row": "fv_to_war_anchors",
     "read": "value_framework.fv_to_6yr_avg_war",
     "note": "pending calibration test: prospect_anchor"},
    {"id": "fv_published_arrives", "block": "fv_tiers", "registry_row": "scouting_reference",
     "read": "transcription", "framework_section": ["3.1", "3.2", "3.3", "3.4"],
     "source_id": ["S3", "S2", "L7"]},
    {"id": "fv_low_end_roles", "block": "fv_tiers", "registry_row": "scouting_reference",
     "read": "transcription", "framework_section": ["3.5", "3.6"], "source_id": ["L7"]},
    {"id": "fv_published_expected", "block": "fv_tiers", "registry_row": "scouting_reference",
     "read": "transcription", "framework_section": ["7.2"], "source_id": ["L1"]},
    {"id": "fv_bucket_odds", "block": "fv_tiers", "registry_row": "prospect_surplus",
     "read": "value_framework.p_bucket_given_fv",
     "named_rows": ["xfv_odds_calibration_slope"],
     "note": "PROSPX odds apply a further calibration at the model grade (the named row)"},
    {"id": "fv_published_shares", "block": "fv_tiers", "registry_row": "scouting_reference",
     "read": "transcription", "framework_section": ["7.7"], "source_id": ["L6"]},
    {"id": "tool_estimates", "block": "tool_tiers", "registry_row": "scouting_reference",
     "read": "transcription", "framework_section": ["2.1", "2.2"], "source_id": ["S3", "W2"]},
    {"id": "tool_no_ground_truth", "block": "tool_tiers", "registry_row": "tool_grade_tables",
     "read": "TOOL_GRADE_TABLES 2.11"},
    {"id": "tool_measured", "block": "tool_tiers", "registry_row": "tool_tables_rederived",
     "read": "data/tool_tables_rederived_eval.json, Part T primary cells with verdict PASS"},
)
SOURCE_IDS = frozenset(s["id"] for s in SOURCES)

#: The keys the FV tier block may carry until TL_24 (test 4).
FV_TIER_KEYS = ("headline", "published_arrives", "low_end_roles", "published_expected",
                "bucket_odds", "published_shares")
FV_TIER_SOURCES = ("industry", "served_config")

# Section C: one table per tool and stat, in page order. Each column is a
# transcribed estimate (table key, column key, author, year) or the measured
# column of a Part T primary cell. A cell id names the Part T primary cell; its
# measured column prints only on PASS.
TOOL_TABLES = (
    {"key": "hit_avg", "tool": "hit", "stat": "AVG", "fmt": "avg", "cell": "hit__avg",
     "estimates": (("objective_tools", "batting_avg", "Batting average at maturity", "McDaniel", 2014),
                   ("smith_hit", "ba", "BA, 2010 to 2012", "Smith", 2013))},
    # Hit to K% has no published estimate (its incumbent is the grade-blind league
    # line, never printed): the table carries rows only if the cell PASSED.
    {"key": "hit_k", "tool": "hit", "stat": "K%", "fmt": "pct", "cell": "hit__k_pct",
     "estimates": ()},
    {"key": "game_pwr_hr", "tool": "game_pwr", "stat": "HR", "fmt": "hr", "cell": "game_pwr__hr_per600",
     "estimates": (("objective_tools", "homers", "Home runs per full season", "McDaniel", 2014),)},
    {"key": "game_pwr_iso", "tool": "game_pwr", "stat": "ISO", "fmt": "avg", "cell": "game_pwr__iso",
     "estimates": (("smith_power", "iso", "ISO", "Smith", 2013),)},
    {"key": "speed", "tool": "speed", "stat": "SB", "fmt": "num", "cell": "speed__sb_per600",
     "estimates": (("objective_tools", "rhh_to_1b", "Home to first, RHH (sec)", "McDaniel", 2014),
                   ("objective_tools", "lhh_to_1b", "Home to first, LHH (sec)", "McDaniel", 2014),
                   ("objective_tools", "run_60yd", "60-yard dash (sec)", "McDaniel", 2014),
                   ("smith_speed", "sb_per_season", "SB per season", "Smith", 2013))},
    {"key": "field", "tool": "field", "stat": "fielding runs", "fmt": "num", "cell": None,
     "estimates": (("smith_defense", "uzr_150", "UZR/150", "Smith", 2013),
                   ("smith_defense", "fld_per_season", "Fld per season", "Smith", 2013))},
    {"key": "fastball", "tool": "fb", "stat": "velocity", "fmt": "mph", "cell": "fb__velo_sp",
     "estimates": (("objective_tools", "fastball_velo", "Fastball velocity (mph)", "McDaniel", 2014),
                   ("smith_fastball", "sp_velo", "Starters (mph)", "Smith", 2013),
                   ("smith_fastball", "rp_velo", "Relievers (mph)", "Smith", 2013))},
    {"key": "command", "tool": "cmd", "stat": "BB%", "fmt": "pct", "cell": "cmd__bb_pct_sp",
     "estimates": (("smith_control", "sp_bb_pct", "Starters BB%", "Smith", 2013),
                   ("smith_control", "rp_bb_pct", "Relievers BB%", "Smith", 2013))},
)
#: Part T primary cells whose incumbent is the grade-blind league line, never
#: printed as an estimate (SCOUTING_PAGE.md section 4: hit to K%).
NO_ESTIMATE_CELLS = ("hit__k_pct",)
MEASURED_UNIT = {"hit__avg": "AVG", "game_pwr__hr_per600": "HR per 600 PA",
                 "game_pwr__iso": "ISO", "speed__sb_per600": "SB per 600 PA",
                 "cmd__bb_pct_sp": "BB%, starters", "fb__velo_sp": "mph, starters",
                 "hit__k_pct": "K%"}
# Disclosed floors (section 4): the printed value, with the source's own value kept.
FLOORS = {("smith_power", "iso", "20"): ".000",
          ("smith_speed", "sb_per_season", "20"): "0",
          ("smith_speed", "sb_per_season", "30"): "0"}

_FLAG_RE = re.compile(r"^SCOUTING_PAGE_LIVE\s*=\s*(True|False)\b", re.M)


def page_live() -> bool:
    """build_site.SCOUTING_PAGE_LIVE, read from the literal in build_site.py."""
    try:
        m = _FLAG_RE.search(BUILD_SITE_PATH.read_text(encoding="utf-8"))
    except OSError:
        return False
    return bool(m) and m.group(1) == "True"


def output_path() -> Path:
    return OUT_PATH if page_live() else PREVIEW_PATH


def _cell(v, ref: str, source: str | None = None, **extra) -> dict:
    if ref not in SOURCE_IDS:
        raise ValueError(f"unregistered source id {ref!r}")
    c = {"v": v, "ref": ref}
    if source is not None:
        c["source"] = source
    c.update(extra)
    return c


def _tcell(t: dict, row: str, col: str, ref: str, source: str | None = None) -> dict:
    """One transcribed cell, carrying its framework section and source id."""
    for r in t["rows"]:
        if r["row"] == row:
            c = r["cells"][col]
            return _cell(c["v"], ref, source, section=c["section"], sid=c["source"])
    return _cell(None, ref, source, status="not_published",
                 section=t["section"], sid=t["source"])


def _rows(t: dict) -> list:
    return [r["row"] for r in t["rows"]]


def _num(x: float, nd: int = 4):
    if x is None or not math.isfinite(float(x)):
        return None
    return round(float(x), nd)


def load_tables(path: Path | None = None) -> dict:
    return json.loads(Path(path or TABLES_PATH).read_text(encoding="utf-8"))


def load_tool_record(path: Path | None = None) -> dict | None:
    try:
        return json.loads(Path(path or TOOL_EVAL_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---- section A ---------------------------------------------------------------

def _pipeline_term(t: dict, g: int):
    for r in t["rows"]:
        lo, _, hi = r["row"].partition("-")
        lo_i, hi_i = int(lo), int(hi or lo)
        if lo_i <= g <= hi_i:
            c = r["cells"]["term"]
            band = r["row"] if hi else None
            return _cell(c["v"], "scale_terms", section=c["section"], sid=c["source"], band=band)
    return _cell("", "scale_terms", section=t["section"], sid=t["source"])


def scale_block(tables: dict) -> dict:
    fg, ba, pl = (tables["tables"][k] for k in ("adjective_ladder", "ba_ladder", "pipeline_ladder"))
    rows = []
    for g in SCALE_GRADES:
        s = str(g)
        fgc = _tcell(fg, s, "called", "scale_terms")
        bac = _tcell(ba, s, "term", "scale_terms")
        for c in (fgc, bac):
            if c.get("status") == "not_published":
                c.pop("status")
                c["v"] = ""
        rows.append({"grade": g,
                     "sd": _cell((g - 50) / 10, "scale_sd", section="1.1", sid="S3"),
                     "fangraphs": fgc, "baseball_america": bac,
                     "pipeline": _pipeline_term(pl, g)})
    return {"columns": [{"key": "grade"}, {"key": "sd"}, {"key": "fangraphs", "sid": "S3"},
                        {"key": "baseball_america", "sid": "B1"},
                        {"key": "pipeline", "sid": "P1"}],
            "rows": rows}


# ---- section B ---------------------------------------------------------------

def _q(key: str, quantity: str | None, **extra) -> dict:
    return dict({"key": key, "quantity": quantity}, **extra)


def fv_tier_block(tables: dict) -> dict:
    T = tables["tables"]
    ov = T["overall_grade_2014"]
    head_rows = []
    for g in GRADES:
        s = str(g)
        role = {k: _tcell(ov, s, k, "fv_roles", "industry") for k in ("hitter", "starter", "reliever")}
        if g < PRIME_TABLE_MIN_FV:
            prime = _cell(None, "fv_prime_war", "served_config", status="no_table")
        else:
            prime = _cell(_num(vf.fv_to_prime_war(g)), "fv_prime_war", "served_config")
        six = _cell(_num(vf.fv_to_6yr_avg_war(g)), "fv_six_yr_war", "served_config")
        head_rows.append({"fv": g, "role": role, "prime_war": prime, "six_yr_avg_war": six})
    headline = {"columns": [_q("fv", None), _q("role", "A"), _q("prime_war", "A"),
                            _q("six_yr_avg_war", "B")],
                "rows": head_rows}

    ph, ps = T["primer_hitters_2018"], T["primer_starters_2018"]
    arrive_rows = []
    for g in (80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30, 20):
        s = str(g)
        arrive_rows.append({
            "grade": g,
            "mcdaniel_2014": _tcell(ov, s, "war", "fv_published_arrives", "industry"),
            "primer_hitters": _tcell(ph, s, "war", "fv_published_arrives", "industry"),
            "primer_starters": _tcell(ps, s, "war", "fv_published_arrives", "industry")})
    published_arrives = {"columns": [_q("grade", None), _q("mcdaniel_2014", "A", sid="S3"),
                                     _q("primer_hitters", "A", sid="S2"),
                                     _q("primer_starters", "A", sid="S2")],
                         "rows": arrive_rows}

    def _roles(t: dict) -> dict:
        return {"columns": [_q("fv", None), _q("role", "A", sid="L7"), _q("examples", "A", sid="L7")],
                "rows": [{"fv": r["row"],
                          "role": _tcell(t, r["row"], "role", "fv_low_end_roles", "industry"),
                          "examples": _tcell(t, r["row"], "examples", "fv_low_end_roles", "industry")}
                         for r in t["rows"]]}
    low_end_roles = {"hitters": _roles(T["hitter_roles_2022"]),
                     "relievers": _roles(T["reliever_roles_2022"])}

    ev = T["expected_value_2026"]
    exp_rows = []
    for fv in dict.fromkeys(_rows(ev)):
        by_type = {r["cells"]["type"]["v"]: r for r in ev["rows"] if r["row"] == fv}
        row = {"fv": fv}
        for side, typ in (("hitter", "Hitter"), ("pitcher", "Pitcher")):
            cells = by_type[typ]["cells"]
            for col, key in (("expected_war", "war"), ("star_odds", "star_odds")):
                c = cells[col]
                row[f"{side}_{key}"] = _cell(c["v"], "fv_published_expected", "industry",
                                             section=c["section"], sid=c["source"])
        exp_rows.append(row)
    published_expected = {"columns": [_q("fv", None), _q("hitter_war", "B", sid="L1"),
                                      _q("hitter_star_odds", "B", sid="L1"),
                                      _q("pitcher_war", "B", sid="L1"),
                                      _q("pitcher_star_odds", "B", sid="L1")],
                          "rows": exp_rows}

    odds = {"buckets": [{"key": k, "band": b, "name": n, "band_words": w} for k, b, n, w in BUCKETS]}
    for side, is_p in (("hitter", False), ("pitcher", True)):
        rows = []
        for g in GRADES:
            p = vf.p_bucket_given_fv(g, is_p) or [None] * len(BUCKETS)
            row = {"fv": g}
            for (k, _b, _n, _w), v in zip(BUCKETS, p):
                row[k] = _cell(_num(v), "fv_bucket_odds", "served_config")
            rows.append(row)
        odds[side] = {"columns": [_q("fv", None)] + [_q(k, "B") for k, *_ in BUCKETS],
                      "rows": rows}

    shares = {}
    for side, key in (("hitter", "shares_2025_hitters"), ("pitcher", "shares_2025_pitchers")):
        t = T[key]
        cols = ("washed_out", "backup", "regular", "above_average", "star", "count")
        shares[side] = {"columns": [_q("fv", None)] + [_q(c, "B", sid="L6") for c in cols],
                        "rows": [dict({"fv": r["row"]},
                                      **{c: _tcell(t, r["row"], c, "fv_published_shares", "industry")
                                         for c in cols})
                                 for r in t["rows"]]}

    block = {"headline": headline, "published_arrives": published_arrives,
             "low_end_roles": low_end_roles, "published_expected": published_expected,
             "bucket_odds": odds, "published_shares": shares}
    assert tuple(block) == FV_TIER_KEYS
    return block


# ---- section C ---------------------------------------------------------------

def _verdicts(record: dict | None) -> dict:
    """Part T primary cells as recorded: verdict, both MAEs and the holdout n.
    An absent record, or one not spent, gives no verdicts (the page prints C-VOID)."""
    if not record or record.get("look") != "T" or record.get("spent") is not True:
        return {}
    out = {}
    for cid, c in ((record.get("result") or {}).get("primary") or {}).items():
        out[cid] = {"verdict": c.get("verdict"), "unit": MEASURED_UNIT.get(cid, ""),
                    "mae_candidate": _cell(_num(c.get("mae_candidate"), 6), "tool_measured", "measured"),
                    "mae_incumbent": _cell(_num(c.get("mae_incumbent"), 6), "tool_measured", "measured"),
                    "n_holdout": _cell(c.get("n"), "tool_measured", "measured")}
    return out


def _measured(record: dict | None, cid: str | None) -> dict:
    """{grade: (value cell, n cell)} at each non-thin bin of a PASS cell, else {}."""
    if not record or not cid:
        return {}
    c = ((record.get("result") or {}).get("primary") or {}).get(cid) or {}
    if c.get("verdict") != "PASS":
        return {}
    out = {}
    for b in c.get("candidate_bins") or []:
        if b.get("thin") or b.get("smoothed") is None:
            continue
        out[int(b["bin"])] = (_cell(_num(b["smoothed"], 6), "tool_measured", "measured"),
                              _cell(int(b["n"]), "tool_measured", "measured"))
    return out


def tool_tier_block(tables: dict, record: dict | None) -> dict:
    T = tables["tables"]
    verdicts = _verdicts(record)
    out_tables = []
    for spec in TOOL_TABLES:
        cols = []
        for tkey, col, label, author, year in spec["estimates"]:
            t = T[tkey]
            cols.append({"key": f"{tkey}.{col}", "kind": "estimate", "label": label,
                         "author": author, "year": year, "section": t["section"], "sid": t["source"]})
        meas = _measured(record, spec["cell"])
        if meas:
            cols.append({"key": "measured", "kind": "measured", "unit": MEASURED_UNIT[spec["cell"]]})
            cols.append({"key": "measured_n", "kind": "n"})
        rows = []
        for g in sorted(GRADES, reverse=True):
            s = str(g)
            row = {"grade": g}
            any_val = False
            for tkey, col, *_ in spec["estimates"]:
                t = T[tkey]
                c = _tcell(t, s, col, "tool_estimates")
                if c.get("status") != "not_published":
                    any_val = True
                    if c["v"] == "":
                        c["status"] = "blank_in_source"
                    floor = FLOORS.get((tkey, col, s))
                    if floor is not None:
                        c["source_value"] = c["v"]
                        c["v"] = floor
                        c["status"] = "floored"
                row[f"{tkey}.{col}"] = c
            if meas:
                if g in meas:
                    row["measured"], row["measured_n"] = meas[g]
                    any_val = True
                else:
                    row["measured"] = _cell(None, "tool_measured", "measured", status="thin_or_absent")
                    row["measured_n"] = _cell(None, "tool_measured", "measured", status="thin_or_absent")
            if any_val:
                rows.append(row)
        v = verdicts.get(spec["cell"]) if spec["cell"] else None
        out_tables.append({"key": spec["key"], "tool": spec["tool"], "stat": spec["stat"],
                           "fmt": spec["fmt"], "cell": spec["cell"],
                           "verdict": (v or {}).get("verdict") if spec["cell"] else None,
                           "columns": cols, "rows": rows})
    return {"record": None if not verdicts else {
                "look": record.get("look"), "spent": record.get("spent"),
                "generated_at": record.get("generated_at")},
            "verdicts": verdicts, "no_estimate_cells": list(NO_ESTIMATE_CELLS),
            "tables": out_tables,
            "no_ground_truth": _cell("TOOL_GRADE_TABLES 2.11", "tool_no_ground_truth")}


# ---- the payload -------------------------------------------------------------

def build_payload(tables: dict | None = None, record: dict | None = None,
                  record_path: Path | None = None) -> dict:
    tables = tables if tables is not None else load_tables()
    if record is None:
        record = load_tool_record(record_path)
    return {
        "schema": SCHEMA,
        "what": "The /scouting/ page: published 20-80 tables transcribed with section and source "
                "ids, plus served value-framework configs read at grades 20 to 80.",
        "transcription": {"file": "data/reference/fv_framework_tables.json",
                          "from": tables.get("transcribed_from"),
                          "from_commit": tables.get("transcribed_from_commit")},
        "citations": {k: {"author": v["author"], "title": v["title"], "url": v["url"],
                          "era": v["era"]} for k, v in tables["sources"].items()},
        "scale": scale_block(tables),
        "fv_tiers": fv_tier_block(tables),
        "tool_tiers": tool_tier_block(tables, record),
        "sources": [dict(s) for s in SOURCES],
    }


def write_payload(payload: dict, path: Path | None = None) -> Path:
    path = Path(path or output_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--print", action="store_true", help="print the payload, write nothing")
    a = ap.parse_args(argv)
    payload = build_payload()
    if a.print:
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        return 0
    path = write_payload(payload)
    where = "data/" if page_live() else "the preview (SCOUTING_PAGE_LIVE is False)"
    print(f"wrote {path} to {where}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The PROSPX graduate bridge (wiring W06, task Q9_26_GRADUATE_BRIDGE).

Pins: the /projections/#player= origin block prints the eFV a graduate
carried into the majors (xfv.json xfv_grade_at_debut, nearest point) and no
consensus arc; player_links carries the graduate flag and debut season; the
/mlbstats/ chip and debut-season filter print no number of their own; and no
surface groups a graduate's realized line by a grade
(docs/PROSPECT_ANCHOR_GATE.md)."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

import mlb_player_export as M

ROOT = Path(__file__).parent
MLBSTATS_JS = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
PROJ_JS = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
EXPORT_SRC = (ROOT / "mlb_player_export.py").read_text(encoding="utf-8")


def _js_fn(src: str, name: str) -> str:
    """The text of one `function name(...) {...}` by brace matching."""
    i = src.index(f"function {name}(")
    j = src.index("{", i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError(name)


def _fixture(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    debuts = [
        {"player_key": "grad_hitter", "mlbam_id": 101, "debut_date": "2026-03-26",
         "fv_open": 45.0, "fv_close": 55.0, "org": "PIT", "points": [],
         "career_stats": [{"level": "MLB", "season": 2026, "org": "STL", "stints": []}]},
        {"player_key": "old_placeholder", "mlbam_id": 102, "debut_date": "2019-04-01",
         "fv_open": 40.0, "fv_close": 40.0, "org": "Office of the Commissioner",
         "points": [], "career_stats": []},
        {"player_key": "no_efv_row", "mlbam_id": 103, "debut_date": "2025-06-01",
         "fv_open": 40.0, "fv_close": 45.0, "org": "SEA", "points": [], "career_stats": []},
    ]
    (d / "debuts.json").write_text(json.dumps(debuts), encoding="utf-8")
    xfv = {"meta": {}, "by_player": {
        "grad_hitter": {"kind": "debuted", "xfv_grade": 63.2, "xfv_grade_at_debut": 60.1},
        "old_placeholder": {"kind": "debuted", "xfv_grade": 40.0, "xfv_grade_at_debut": 40.0},
    }}
    (d / "xfv.json").write_text(json.dumps(xfv), encoding="utf-8")
    aaa = {"source_fetched": {"2025": "2026-06-11", "2026": "2026-10-01"},
           "source_through": {"2026": "2026-09-20"},
           "by_mlbam": {
               "101": {"xwoba": 0.353, "woba": 0.34, "ev": 90.8, "hardhit_percent": 48.4,
                       "whiff": 24.2, "luck_gap": 0.013, "pa": 221, "season": 2025,
                       "levels": ["AAA"]},
               "104": {"xwoba": 0.3, "ev": 88.0, "hardhit_percent": 40.0, "whiff": 20.0,
                       "luck_gap": -0.01, "pa": 150, "season": 2026, "levels": ["A"]},
           }}
    (d / "statcast_aaa_hitters.json").write_text(json.dumps(aaa), encoding="utf-8")
    return d


def test_origin_efv_is_the_at_debut_grade(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "DATA_DIR", _fixture(tmp_path))
    org = M._debut_origins()
    # The at-debut grade, never the served xfv_grade the rookie window moved.
    assert org[101]["efvDebut"] == 60.1
    assert org[102]["efvDebut"] == 40.0
    assert org[103]["efvDebut"] is None          # no xfv row: nothing printed
    # The club he debuted with, by the On This Day rule, not the current org.
    assert org[101]["devOrg"] == "STL"
    assert org[102]["devOrg"] is None            # a non-club placeholder is dropped
    assert org[103]["devOrg"] == "SEA"


def test_aaa_hitter_line_dates_a_partial_season_and_drops_luck(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "DATA_DIR", _fixture(tmp_path))
    lines = M._aaa_hitter_lines()
    assert lines[101] == {"season": 2025, "levels": ["AAA"], "pa": 221, "xwoba": 0.353,
                          "ev": 90.8, "hardHit": 48.4, "whiff": 24.2}
    assert lines[104]["thru"] == "2026-09-20" and "asOf" not in lines[104]
    assert all("luck" not in k.lower() for row in lines.values() for k in row)


def test_links_carry_the_graduate_flag_and_debut_season(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "DATA_DIR", tmp_path)
    monkeypatch.setattr(M, "_active_prospect_rows", lambda: [])
    payload = {"generated_at": "2026-10-08", "players": {
        "grad_hitter": {"mlbam": 101, "name": "Grad", "team": "STL", "pos": "2B",
                        "origin": {"prospx": "grad_hitter", "debut": "2026-03-26",
                                   "efvDebut": 60.1}},
        "vet": {"mlbam": 200, "name": "Vet", "team": "NYY", "pos": "SS"},
    }}
    M._export_links(payload)
    links = json.loads((tmp_path / "player_links.json").read_text(encoding="utf-8"))
    g, v = links["byMlbam"]["101"], links["byMlbam"]["200"]
    assert g["grad"] is True and g["debutYr"] == 2026
    assert "grad" not in v and "debutYr" not in v
    # The map carries the flag and the season, never a grade.
    assert not any(re.search(r"fv", k, re.I) for row in links["byKey"].values() for k in row)


def test_origin_line_prints_efv_at_debut_and_no_consensus_arc():
    i = PROJ_JS.index("const originLine")
    line = PROJ_JS[i:PROJ_JS.index("\n", PROJ_JS.index('      : "";', i))]
    assert 'term("xfv", "eFV")} at debut ${Math.round(org.efvDebut)}' in line
    for gone in ("fvOpen", "fvClose", "fvSpark", "FV ${"):
        assert gone not in line, gone
    assert "function fvSparkSVG" not in PROJ_JS
    hit = _js_fn(PROJ_JS, "aaaHitLine")
    assert "Statcast (tracked parks)" in hit and "luck" not in hit.lower()


def test_served_origin_efv_equals_xfv_at_debut():
    det_p, xfv_p = ROOT / "data" / "mlb_player_detail.json", ROOT / "data" / "xfv.json"
    if not det_p.exists() or not xfv_p.exists():
        pytest.skip("served payloads not generated on this machine")
    det = json.loads(det_p.read_text(encoding="utf-8"))
    if "origin_efv" not in (det.get("coverage") or {}):
        pytest.skip("mlb_player_detail.json predates the graduate bridge")
    xfv = json.loads(xfv_p.read_text(encoding="utf-8"))["by_player"]
    n = 0
    for p in det["players"].values():
        o = p.get("origin") or {}
        if o.get("efvDebut") is None:
            continue
        assert o["efvDebut"] == xfv[o["prospx"]]["xfv_grade_at_debut"], o["prospx"]
        n += 1
    assert n == det["coverage"]["origin_efv"] and n > 1000


def test_chip_and_filter_print_no_number():
    chip = _js_fn(MLBSTATS_JS, "gradChip")
    for lit in re.findall(r"'([^']*)'|\"([^\"]*)\"", chip):
        text = re.sub(r"<[^>]*>", "", "".join(lit))
        assert not re.search(r"[0-9]", text), text
    for name in ("gradSelect", "gradOptions"):
        body = _js_fn(MLBSTATS_JS, name)
        assert ".length" not in body, name      # no count printed beside an option
    opts = _js_fn(MLBSTATS_JS, "gradOptions")
    assert '"All players"' in opts and '"PROSPX graduates"' in opts
    assert '"Graduates, " + y + " debut"' in opts
    # The filter narrows rows on every player board and stacks with the rest.
    for matcher in ("relMatch", "starterMatch", "hitterMatch", "defenseMatch",
                    "warMatch", "winMatch", "filteredLeverage"):
        assert "passesGrad(r)" in _js_fn(MLBSTATS_JS, matcher), matcher
    assert "grad=" in _js_fn(MLBSTATS_JS, "writeHash")


def test_no_graduate_aggregate_by_grade():
    # The MLB Stats page reads no grade of any kind: a board can be cut to
    # graduates, never ranked or averaged by what PROSPX graded them.
    assert not re.search(r"efv|xfv|fv_close|fvClose|consensus", MLBSTATS_JS, re.I)
    # In the exporter the at-debut eFV is read in one loader, copied per player
    # in _debut_origins, and in build_payload appears only in the render
    # whitelist and a count of cards that carry it, never as a key or inside
    # an aggregate of a realized statistic.
    tree = ast.parse(EXPORT_SRC)
    users = {}
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            seg = ast.get_source_segment(EXPORT_SRC, fn) or ""
            if "efvDebut" in seg or "xfv_grade_at_debut" in seg:
                users[fn.name] = fn
    assert set(users) == {"_efv_at_debut", "_debut_origins", "build_payload"}
    for node in ast.walk(users["build_payload"]):
        if isinstance(node, ast.Call):
            seg = ast.get_source_segment(EXPORT_SRC, node) or ""
            if "efvDebut" not in seg:
                continue
            fname = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if fname == "get":
                continue
            assert fname == "sum", seg
            gen = node.args[0]
            assert isinstance(gen, ast.GeneratorExp) and isinstance(gen.elt, ast.Constant) \
                and gen.elt.value == 1, seg               # a count, not a sum of a stat
        if isinstance(node, ast.Subscript):
            seg = ast.get_source_segment(EXPORT_SRC, node.slice) or ""
            assert "efvDebut" not in seg and "xfv_grade" not in seg, seg
    for bad in ("statistics.", "mean(", "median("):
        assert bad not in (ast.get_source_segment(EXPORT_SRC, users["_debut_origins"]) or "")

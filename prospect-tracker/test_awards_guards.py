"""awards_core.py: THE FRAME GUARDS (AWARDS_2_RULES_CORE; AWARDS_PLAN 2 F10 to F12 and 6
'Invariants and tests' row I7).

The prospect superlatives pair eFV at debut with a season's WAR for one player at a time,
and only on debut cohorts the reserved eFV frames leave open. RESERVED_LV holds LIST
vintages (2020, 2021), whose members debut in 2020 or later, so every 2020 to 2024 debut
cohort waits for the R-LV look record, and every cohort from R_VM_FIRST_DEBUT_YEAR (2025)
waits for its own R-VM look record. The projection superlatives are dark for 2026 and for
any season whose registered looks are not all recorded. No awards module groups a realized
number by FV, eFV or consensus band or reads the realized FV anchor
(docs/PROSPECT_ANCHOR_GATE.md). No test opens a socket.
"""
from __future__ import annotations

import ast
import re
import socket
from pathlib import Path

import pytest

import awards_core as A

ROOT = Path(__file__).resolve().parent
FRAMES = {"lv_first": 2020, "vm_first": 2025}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("an awards guard test opened a socket")
    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


def _row(mlbam: int, debut: int, efv: float = 45.0, war: float = 3.0) -> dict:
    return {"mlbam": mlbam, "name": f"P{mlbam}", "club_code": "BOS", "player_key": f"p{mlbam}",
            "debut_season": debut, "efv_at_debut": efv, "war": war, "pa": 600, "ip": 0}


# --- the pool guard ------------------------------------------------------------------------

def test_reserved_frames_read_the_frame_module_pins():
    import efv_vintage_frame as V
    got = A.reserved_frames()
    assert got == {"lv_first": min(V.RESERVED_LV), "vm_first": V.R_VM_FIRST_DEBUT_YEAR} == FRAMES
    assert V.RESERVED_LV == frozenset({2020, 2021})


def test_r_vm_and_r_lv_debut_cohorts_never_enter_the_prospect_pool():
    rows = [_row(1, 2019, 20.0, 5.0), _row(2, 2025, 55.0, 4.0), _row(3, 2026, 60.0, 6.0),
            _row(4, 2022, 50.0, 7.0), _row(5, 2020), _row(6, 2024), _row(7, 2015, 40.0, 1.0)]
    for fn in (A.prospect_above, A.prospect_below):
        block = fn(rows, 2026, war_provider="ewar_v2", frames=FRAMES)
        ids = {r["id"] for r in block["rows"]}
        assert ids == {1, 7}, ids
        assert block["n_pool"] == 2
        assert {r["debut_season"] for r in block["rows"]} == {2019, 2015}
    for y in (2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027):
        assert A.prospect_pool_open(y, frames=FRAMES) is False, y
    for y in (2011, 2015, 2019):
        assert A.prospect_pool_open(y, frames=FRAMES) is True, y
    # the live pins give the same answer as the fixture frames
    assert A.prospect_pool_open(2019) is True and A.prospect_pool_open(2022) is False
    assert A.prospect_pool_open(2025) is False and A.prospect_pool_open(2026) is False


def test_open_late_cohorts_entries_carry_their_look_record():
    assert isinstance(A.OPEN_LATE_COHORTS, dict)
    for year, entry in A.OPEN_LATE_COHORTS.items():
        assert isinstance(year, int) and year >= FRAMES["lv_first"], year
        assert set(entry) >= {"gate_doc", "results_heading", "record"}, entry
        assert (ROOT / entry["gate_doc"]).exists(), entry["gate_doc"]
        assert A.look_record_exists(entry, ROOT), (
            f"OPEN_LATE_COHORTS names {year} but {entry['gate_doc']} carries no "
            f"{entry['record']} record under {entry['results_heading']!r}")


def test_an_entry_without_its_look_record_fails_and_keeps_the_cohort_closed(monkeypatch, tmp_path):
    entry = {"gate_doc": "docs/efv-v2/EFV_V2_GATE.md", "results_heading": "## 9. Results",
             "record": "R-LV"}
    # at HEAD section 9 holds the empty placeholder only, so the record does not exist
    assert A.look_record_exists(entry, ROOT) is False
    monkeypatch.setitem(A.OPEN_LATE_COHORTS, 2022, entry)
    assert A.prospect_pool_open(2022, frames=FRAMES) is False
    block = A.prospect_above([_row(4, 2022), _row(1, 2019)], 2026, war_provider="ewar_v2", frames=FRAMES)
    assert [r["id"] for r in block["rows"]] == [1]
    with pytest.raises(AssertionError):
        test_open_late_cohorts_entries_carry_their_look_record()
    # the same entry against a document that carries the record opens the cohort
    doc = tmp_path / "docs" / "efv-v2" / "EFV_V2_GATE.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# gate\n\n## 8. Rules\n\ntext\n\n## 9. Results\n\n"
                   "| date | frame | verdict |\n|---|---|---|\n| 2026-12-01 | R-LV | read |\n\n"
                   "## 10. Lab\n", encoding="utf-8")
    assert A.look_record_exists(entry, tmp_path) is True
    assert A.prospect_pool_open(2022, root=tmp_path, frames=FRAMES) is True
    # a record under another heading does not count
    other = dict(entry, results_heading="## 10. Lab")
    assert A.look_record_exists(other, tmp_path) is False
    # the placeholder alone never counts, whatever the record name
    doc.write_text("## 9. Results\n\n(Empty. Filled only by the look runner, R-LV included.)\n",
                   encoding="utf-8")
    assert A.look_record_exists(entry, tmp_path) is False


# --- the projection pair ------------------------------------------------------------------

def test_proj_dark_seasons_holds_2026_and_the_pair_is_blocked():
    assert 2026 in A.PROJ_DARK_SEASONS
    rows = [{"mlbam": 1, "name": "A", "club_code": "BOS", "war_realized": 5.0, "war_proj": 3.0,
             "p10": 1.0, "p90": 5.0, "pa": 600, "ip": 0}]
    for fn in (A.proj_above, A.proj_below):
        block = fn(rows, 2026, war_provider="ewar_v2")
        assert block["rows"] == [] and block["n_pool"] == 0
        assert block["blocked_on"] and "2026" in block["blocked_on"] and "2027" in block["blocked_on"]
    # a season with no PROJ_LOOKS entry is blocked too
    assert 2027 not in A.PROJ_DARK_SEASONS
    msg = A.proj_blocked_on(2027)
    assert msg and "2027" in msg
    assert A.proj_above(rows, 2027, war_provider="ewar_v2")["blocked_on"] == msg
    assert A.proj_above(rows, 2035, war_provider="ewar_v2")["blocked_on"]


def test_proj_pair_lights_only_when_every_registered_look_is_recorded(monkeypatch, tmp_path):
    doc = tmp_path / "docs" / "FORWARD_GATE.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("## 9. Results\n\n| 2027-11-01 | FORWARD-2027 | scored |\n", encoding="utf-8")
    recorded = {"gate_doc": "docs/FORWARD_GATE.md", "results_heading": "## 9. Results",
                "record": "FORWARD-2027"}
    missing = dict(recorded, record="AG_16-2027")
    rows = [{"mlbam": 1, "name": "A", "club_code": "BOS", "war_realized": 5.0, "war_proj": 3.0,
             "p10": 1.0, "p90": 5.0, "pa": 600, "ip": 0},
            {"mlbam": 2, "name": "B", "club_code": "NYY", "war_realized": 1.0, "war_proj": 4.0,
             "p10": 2.0, "p90": 6.0, "pa": 500, "ip": 0},
            {"mlbam": 3, "name": "C", "club_code": "SEA", "war_realized": 9.0, "war_proj": 1.0,
             "p10": 0.0, "p90": 2.0, "pa": 100, "ip": 0}]
    monkeypatch.setitem(A.PROJ_LOOKS, 2027, (recorded, missing))
    blocked = A.proj_blocked_on(2027, root=tmp_path)
    assert blocked and "AG_16-2027" in blocked and "FORWARD-2027" not in blocked
    monkeypatch.setitem(A.PROJ_LOOKS, 2027, (recorded,))
    assert A.proj_blocked_on(2027, root=tmp_path) is None
    above = A.proj_above(rows, 2027, war_provider="ewar_v2", root=tmp_path)
    assert above["blocked_on"] is None and [r["id"] for r in above["rows"]] == [1, 2]
    assert above["rows"][0]["from"] == 3.0 and above["rows"][0]["to"] == 5.0
    assert above["rows"][0]["value"] == 2.0 and above["rows"][0]["p90"] == 5.0
    below = A.proj_below(rows, 2027, war_provider="ewar_v2", root=tmp_path)
    assert [r["id"] for r in below["rows"]] == [2, 1] and below["caption"]
    # 2026 stays dark whatever PROJ_LOOKS says
    monkeypatch.setitem(A.PROJ_LOOKS, 2026, (recorded,))
    assert A.proj_blocked_on(2026, root=tmp_path)


# --- the anchor gate: no grouping by band, no read of the realized anchor ------------------------

_BAND_ID = re.compile(r"(^|_)(x?fv|efv|consensus)_?(band|bucket|cell|tier|bin|group|strat\w*)",
                      re.IGNORECASE)
_ANCHOR = re.compile(r"fv_to_6yr_avg_war|fv[_\s-]*to[_\s-]*war|FV-to-WAR", re.IGNORECASE)
_GROUPERS = {"groupby", "pivot_table", "cut", "qcut", "crosstab"}


def _awards_modules() -> list[Path]:
    return sorted(p for p in ROOT.glob("awards_*.py"))


def _identifiers(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id, node.lineno
        elif isinstance(node, ast.Attribute):
            yield node.attr, node.lineno
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node.name, node.lineno
        elif isinstance(node, ast.arg):
            yield node.arg, node.lineno
        elif isinstance(node, ast.keyword) and node.arg:
            yield node.arg, node.lineno
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) < 80:
            yield node.value, node.lineno


def test_no_awards_module_groups_by_an_fv_band_or_reads_the_anchor():
    mods = _awards_modules()
    assert {p.name for p in mods} >= {"awards_core.py", "awards_rookies.py"}
    for p in mods:
        src = p.read_text(encoding="utf-8")
        assert not _ANCHOR.search(src), f"{p.name} names the realized FV anchor"
        tree = ast.parse(src)
        for ident, line in _identifiers(tree):
            assert not _BAND_ID.search(ident), f"{p.name}:{line} groups by an FV band: {ident!r}"
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name in _GROUPERS:
                text = ast.unparse(node).lower()
                assert not re.search(r"fv|efv|consensus", text), f"{p.name}:{node.lineno}: {text}"
        # the module imports nothing that serves the realized anchor
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
                for n in names:
                    assert not re.search(r"anchor|fv_war|fv_to", n, re.IGNORECASE), f"{p.name}: {n}"


def test_prospect_rows_are_per_player_and_never_aggregated():
    rows = [_row(i, 2015 + (i % 5), efv=20.0 + i, war=float(i) / 2) for i in range(1, 13)]
    block = A.prospect_above(rows, 2026, war_provider="ewar_v2", frames=FRAMES)
    assert all(isinstance(r["id"], int) for r in block["rows"])
    keys = set()
    for r in block["rows"]:
        keys |= set(r)
    assert not any(_BAND_ID.search(k) for k in keys)
    assert not any(k in ("mean", "median", "count", "rate", "n_by_band") for k in keys)


# --- the provider ----------------------------------------------------------------------------

def test_awards_core_never_reads_the_training_default():
    src = (ROOT / "awards_core.py").read_text(encoding="utf-8")
    assert "DEFAULT_PROVIDER" not in src
    assert "served_war_basis" in src
    with pytest.raises(ValueError):
        A.league_split({"bat": [], "pit": []}, season=2026, war_provider=None)
    with pytest.raises(ValueError):
        A.war_unit_label("")
    assert A.war_unit_label("ewar_v2") == "eWAR v2" and A.war_unit_label("ewar_v3") == "eWAR v3"


def test_flag_is_off_and_nothing_served_names_awards():
    assert A.AWARDS_LIVE is False
    assert "awards" not in (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8").split()
    for name in ("glossary.json", "model_registry.json"):
        text = (ROOT / "data" / name).read_text(encoding="utf-8")
        assert '"awards_selection"' not in text and '"eephus_selection"' not in text, name
    assert not (ROOT / "awards" / "index.html").exists()
    assert not (ROOT / "data" / "awards.json").exists()

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EFV3_B9 pins: the count-only college source probe (tools/college_source_probe.py).

1. The receipt's frame counts equal efv_vintage_frame.frame_counts on the same universe
   (synthetic, and the committed receipt against the real frame at two vintages).
2. An empty season writes a zero row and a cache file; a failed fetch writes a zero row
   and never raises.
3. The college-line rule: a sport-22 line strictly below the draft year counts, a line
   in the draft year or later does not, a non-college row is never in the denominator,
   an unresolved id is in the denominator and never in the numerator.
4. Bans: development vintages only, the reserved guard called first; no label module
   imported; no stat field read off a line; no FV-cell grouping token; no call to
   amateur_leagues.build (the only file under data/ the tool writes is its receipt).
5. No em-dash in the tool, this file or the receipt.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))

import amateur_leagues as AL  # noqa: E402
import college_source_probe as P  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

DATA = ROOT / "data"
RECEIPT = DATA / "college_source_probe.json"
_HAVE_DATA = all((DATA / f).exists() for f in ("debuts.json", "inactive.json",
                                                "timeseries.json"))


def test_constants():
    assert P.PROBE_SEASONS == tuple(range(2005, 2021))
    assert P.PROBE_SPORTS == (22, 17)
    assert set(P.PROBE_SPORTS) <= set(AL.SPORTS)
    assert P.COLLEGE_SPORT == 22
    assert P.GROUPS == ("hitting", "pitching")
    assert P.OUT == DATA / "college_source_probe.json"
    # probe seasons are stat seasons, not list vintages; the frame guard is tested below


# ---------------------------------------------------------------------------
# 2. empty and failed seasons
# ---------------------------------------------------------------------------

def _empty_payload(url):
    return {"stats": [{"splits": [], "totalSplits": 0}]}


def test_empty_season_writes_a_zero_row_and_a_cache_file(monkeypatch, tmp_path):
    monkeypatch.setattr(AL, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(AL, "_fetch", _empty_payload)
    monkeypatch.setattr(AL, "_MIN_REQ_GAP", 0.0)
    out = P.fetch_counts(fetch=True, seasons=(2007,), sports=(22,))
    rec = out["2007"]["22"]
    for group in P.GROUPS:
        assert rec[group]["rows"] == 0
        assert rec[group]["players"] == 0
        assert rec[group]["leagues"] == {}
        assert rec[group]["fetch_error"] is None
        assert rec[group]["cached"] is True
        f = tmp_path / f"{group}_22_2007.json"
        assert f.exists() and json.loads(f.read_text(encoding="utf-8")) == []
    s = P.season_summary(out, sports=(22,))["22"]
    assert s["rows_total"] == 0 and s["all_probed_seasons_empty"] is True
    assert s["first_populated_season"] is None and s["fetch_failures"] == []


def test_failed_fetch_is_a_zero_row_and_never_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(AL, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(AL, "_MIN_REQ_GAP", 0.0)

    def boom(sport_id, season, group, fetch=True):
        raise RuntimeError("statsapi down")
    monkeypatch.setattr(AL, "season_splits", boom)
    out = P.fetch_counts(fetch=True, seasons=(2008,), sports=(17,))
    rec = out["2008"]["17"]["hitting"]
    assert rec["rows"] == 0 and rec["cached"] is False
    assert rec["fetch_error"].startswith("RuntimeError")
    s = P.season_summary(out, sports=(17,))["17"]
    assert s["fetch_failures"] == ["hitting_17_2008", "pitching_17_2008"]


def test_line_counts_reads_only_mlbam_season_league():
    rows = [{"mlbam": 1, "season": 2017, "league": "CBB", "ops": ".900"},
            {"mlbam": 1, "season": 2017, "league": "CBB"},
            {"mlbam": 2, "season": 2017, "league": "CCBL"},
            {"mlbam": None, "season": 2017}]
    c = P.line_counts(rows)
    assert c == {"rows": 4, "players": 2,
                 "leagues": {"CBB": 2, "CCBL": 1, "unknown": 1}}


# ---------------------------------------------------------------------------
# 1 and 3. the frame read
# ---------------------------------------------------------------------------

def _row(key, is_college, acq_year, mlbam, cons=True, milb=None):
    return {"player_key": key, "is_college": is_college, "acq_year": acq_year,
            "mlbam_id": mlbam, "grades": {"consensus": 50.0} if cons else {},
            "milb": milb}


_LINES = {"hitting": {11: {2014, 2015}, 12: {2016}, 13: {2010}},
          "pitching": {14: {2013}}}


def test_coverage_block_rule():
    import source_backtest as SB
    rows = [
        _row("a", 1.0, 2015, 11),          # 2014 line below the 2015 draft: counts
        _row("b", 1.0, 2016, 12),          # line in the draft year only: no
        _row("c", 1.0, 2016, None),        # unresolved id: denominator only
        _row("d", 0.0, 2015, 13),          # not a college row: never counted
        _row("e", 1.0, 2016, 14),          # pitching line below the draft year
        _row("f", 1.0, None, 11),          # no draft year known: not a college row here
    ]
    rows[0]["grades"] = {SB.CONSENSUS_KEY: 50.0}
    b = P.coverage_block(rows, "hit", _LINES)
    assert b["rows"] == 6
    assert b["is_college_rows"] == 4 and b["is_college_with_id"] == 3
    assert b["draft_years"] == {"2015": 1, "2016": 3}
    assert b["with_college_line_below_draft_year"] == {"same_group": 1, "either_group": 2}
    assert b["share_of_is_college_rows"] == {"same_group": 0.25, "either_group": 0.5}
    assert b["share_of_is_college_with_id"] == {"same_group": round(1 / 3, 4),
                                                "either_group": round(2 / 3, 4)}
    assert b["with_college_line_any_probed_season"] == 3
    empty = P.coverage_block([], "pit", _LINES)
    assert empty["is_college_rows"] == 0
    assert empty["share_of_is_college_rows"] == {"same_group": None, "either_group": None}


def _fake_frames(monkeypatch):
    seen = []

    def fake_build(side, vintage, *, gate_sha=None, universe=None, milb=True,
                   sidecars=True, milb_floor=None):
        F.guard_score_request(vintage, gate_sha=gate_sha, purpose="frame")
        seen.append((side, int(vintage)))
        n = (int(vintage) - 2010) * (2 if side == "hit" else 3)
        return [_row(f"{side}{vintage}{i}", 1.0 if i % 2 else 0.0, 2015, 11 if i % 3 else None,
                     cons=(i % 4 != 0), milb={"x": 1} if i % 5 else None)
                for i in range(n)]
    monkeypatch.setattr(F, "build_frame", fake_build)
    return seen


def test_frame_counts_equal_frame_counts_on_the_same_universe(monkeypatch):
    seen = _fake_frames(monkeypatch)
    counts, cov = P.frame_coverage(universe={}, lines=_LINES)
    assert counts == F.frame_counts(universe={})
    assert set(seen) <= {(s, v) for s in F.SIDES for v in F.DEV_VINTAGES}
    assert not {v for _s, v in seen} & F.RESERVED_LV
    for side in F.SIDES:
        for V in F.DEV_VINTAGES:
            assert cov[side][str(V)]["rows"] == counts[side][V]["rows"]


def test_guards_name_the_development_vintages_only():
    g = P.guards()
    assert g["vintages_read"] == list(F.DEV_VINTAGES)
    assert g["reserved_lv"] == [2020, 2021] and g["reserved_vm_pins"] == []


def test_run_writes_nothing_and_reads_no_network(monkeypatch, tmp_path):
    _fake_frames(monkeypatch)
    monkeypatch.setattr(AL, "CACHE_DIR", tmp_path)

    def no_net(url):
        raise AssertionError(f"network call {url}")
    monkeypatch.setattr(AL, "_fetch", no_net)
    doc = P.run(fetch=False, universe={})
    assert doc["probe"]["fetch_enabled"] is False
    assert doc["family_status"]["status"] == "no source"
    assert doc["frame_counts"]["hit"]["2011"]["rows"] == 2
    assert not list(tmp_path.iterdir())


# ---------------------------------------------------------------------------
# the committed receipt against the real frame and the real cache
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def receipt():
    if not RECEIPT.exists():
        pytest.skip("receipt not built")
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def test_receipt_shape(receipt):
    assert receipt["produced_by"] == "tools/college_source_probe.py"
    assert receipt["role"] == "development"
    assert receipt["probe"]["seasons"] == list(P.PROBE_SEASONS)
    assert receipt["guards"]["vintages_read"] == list(F.DEV_VINTAGES)
    assert sorted(int(v) for v in receipt["frame_counts"]["hit"]) == list(F.DEV_VINTAGES)
    for side in F.SIDES:
        for V, c in receipt["frame_counts"][side].items():
            assert int(V) not in F.RESERVED_LV
            b = receipt["college_coverage"]["by_vintage"][side][V]
            assert b["rows"] == c["rows"]
            assert b["is_college_with_id"] <= b["is_college_rows"] <= b["rows"]
            w = b["with_college_line_below_draft_year"]
            assert w["same_group"] <= w["either_group"] <= b["is_college_with_id"]
    assert receipt["family_status"]["status"]


@pytest.mark.skipif(not _HAVE_DATA, reason="served data files absent")
@pytest.mark.parametrize("V", [2011, 2019])
def test_receipt_frame_counts_match_the_frame(receipt, V):
    want = F.frame_counts(vintages=(V,))
    for side in F.SIDES:
        assert receipt["frame_counts"][side][str(V)] == want[side][V]


def test_receipt_by_season_matches_the_cache(receipt):
    checked = 0
    for season, per_sport in receipt["by_season"].items():
        for sport, per_group in per_sport.items():
            for group, rec in per_group.items():
                f = AL.CACHE_DIR / f"{group}_{sport}_{season}.json"
                if not f.exists():
                    continue
                assert rec["rows"] == len(json.loads(f.read_text(encoding="utf-8")))
                checked += 1
    if not checked:
        pytest.skip("probe cache absent")


# ---------------------------------------------------------------------------
# 4. bans, read off the source
# ---------------------------------------------------------------------------

_TOOL = ROOT / "tools" / "college_source_probe.py"
_BANNED_TOKENS = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
                  "fv_band", "fv_bin")
_FV_GRID = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
_STAT_FIELDS = {"pa", "ab", "ops", "obp", "slg", "avg", "hr", "sb", "ip", "bf", "era",
                "g", "gs", "so"}


def _names(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            yield node.name
        elif isinstance(node, ast.arg):
            yield node.arg
        elif isinstance(node, ast.alias):
            yield node.name


def test_tool_reads_no_label_no_stat_and_groups_no_fv_level():
    tree = ast.parse(_TOOL.read_text(encoding="utf-8"))
    imported = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                for a in n.names} | {n.module for n in ast.walk(tree)
                                     if isinstance(n, ast.ImportFrom) and n.module}
    assert not imported & {"efv_labels", "war_source", "ewar", "stats", "fwar_frame",
                           "fwar_vintage", "efv_model", "efv_v2_model", "efv_dataset",
                           "numpy", "sklearn", "scipy"}, imported
    for name in _names(tree):
        low = name.lower()
        assert not any(t in low for t in _BANNED_TOKENS), name
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (node.value, node.lineno)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            low = node.value.lower()
            assert not any(t in low for t in _BANNED_TOKENS), node.value
            assert node.value not in _STAT_FIELDS, (node.value, node.lineno)
    assert set(P.LINE_KEYS) == {"mlbam", "season", "league"}


def test_tool_never_lands_data_amateur_leagues():
    """amateur_leagues.build and warm_cache land or walk the served table; the probe
    goes through season_splits only and writes one file under data/, its receipt."""
    tree = ast.parse(_TOOL.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"build", "warm_cache", "DATA_PATH"}, node.lineno
    src = _TOOL.read_text(encoding="utf-8")
    assert src.count("write_text(") == 1
    assert re.search(r'OUT = ROOT / "data" / "college_source_probe\.json"', src)


def test_no_emdash():
    for p in (_TOOL, Path(__file__), RECEIPT):
        if p.exists():
            text = p.read_text(encoding="utf-8")
            assert chr(0x2014) not in text and chr(0x2013) not in text, p.name

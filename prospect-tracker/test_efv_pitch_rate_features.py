# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Q10_10 pins for the pitch-rate sidecar (owner ask 19; pitch_metrics.md s7).

1. The column: d = ln(rate / anchor) per qualifying (level, season) line, exposure
   weighted, shrunk n / (n + 100); up to 3 most recent qualifying seasons before V;
   floors PA 50 and BF 60; a level-season with no rate or no anchor (untracked) never
   enters; pitchers read the majority-role line against the ROLE anchor.
2. Missingness: no id or no qualifying line gives None and no flag; imputation is at
   the has-block TRAIN mean and refuses an empty training set.
3. Reserved list vintages raise everywhere; the tool drops R-VM rows before any count
   and its probes read no outcome.
4. The module reads no outcome, debut, label, stored id or orphan cache; nothing is
   grouped by consensus-FV level; no em-dash.
5. The committed sidecar covers development vintages only, and the arm ledger counts
   its probes.
"""
from __future__ import annotations

import ast
import json
import math
import re
import sys
from pathlib import Path

import pytest

import efv_pitch_rate_features as PR
import efv_vintage_frame as F

ROOT = Path(__file__).parent
SRC = ROOT / "efv_pitch_rate_features.py"
TOOL = ROOT / "tools" / "efv_pitch_rate_sidecar.py"
SIDECAR = ROOT / "data" / "_labs" / "efv_pitch_rate_features.json"
LEDGER = ROOT / "data" / "xfv_arm_ledger.json"
sys.path.insert(0, str(ROOT / "tools"))

_ALLOWED_IMPORTS = {"__future__", "math", "efv_vintage_frame", "pitch_rates"}
_OUTCOME_WORD = re.compile(r"(^|_)(war|fwar|ewar|debut|debuts|reached|w3|r3|l6|label|"
                           r"labels|outcome|statline|record_mlbam_id)(_|$)")
#: 50 and 60 are left out: they are the PA and BF floors (HIT_MIN_PA, PIT_MIN_BF).
_FV_GRID = {35, 40, 45, 55, 65, 70, 75, 80}
_BANNED_TOKENS = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
                  "fv_band", "fv_bin", "consensus")


def _source(lines: dict, anchors: dict) -> PR.RateSource:
    """lines {(season, level): {pid: line}}, anchors {(season, level): block}."""
    return PR.RateSource(lines=lambda s, lv: lines.get((s, lv), {}),
                         anchors=lambda lv, s: anchors.get((s, lv), {}))


def _hit(pa, rate):
    return {"hit": {"pa": pa, "np": round(pa * rate), "p_pa": rate}, "pit": None}


def _pit(role, bf, rate, basis="role_split"):
    line = {"bf": bf, "np": round(bf * rate)}
    return {"hit": None, "pit": {"role": role, "basis": basis, "p_bf": rate,
                                 "sp": line if role == "SP" else None,
                                 "rp": line if role == "RP" else None,
                                 "season_line": line}}


_ANCH = {"hit": {"p_pa": 4.0}, "sp": {"p_bf": 3.8}, "rp": {"p_bf": 4.0}}


# ---------------------------------------------------------------------------
# 1. the column
# ---------------------------------------------------------------------------

def test_hitter_column_is_weighted_and_shrunk():
    src = _source({(2016, "AA"): {7: _hit(300, 4.2)}, (2016, "AAA"): {7: _hit(100, 3.8)},
                   (2015, "AA"): {7: _hit(200, 4.0)}},
                  {(2016, "AA"): _ANCH, (2016, "AAA"): _ANCH, (2015, "AA"): _ANCH})
    f = PR.feature(7, 2017, "hit", src)
    d = [math.log(4.2 / 4.0), math.log(3.8 / 4.0), 0.0]
    e = [300, 100, 200]
    want = sum(a * b for a, b in zip(d, e)) / 600 * 600 / 700
    assert f["has_block"] and f["exposure"] == 600 and f["seasons"] == [2016, 2015]
    assert f["value"] == pytest.approx(want, abs=1e-12)


def test_three_most_recent_seasons_and_never_season_v():
    lines, anch = {}, {}
    for s in range(2011, 2018):
        lines[(s, "AAA")] = {7: _hit(100, 4.0 + 0.1 * (s - 2010))}
        anch[(s, "AAA")] = _ANCH
    f = PR.feature(7, 2017, "hit", _source(lines, anch))
    assert f["seasons"] == [2016, 2015, 2014]
    assert all(ln[0] < 2017 for ln in f["lines"])


def test_floors_and_untracked_level_seasons_never_enter():
    src = _source({(2016, "AA"): {7: _hit(49, 4.4)}, (2016, "A"): {7: _hit(300, 4.4)},
                   (2015, "AA"): {7: _hit(50, 4.4)}},
                  {(2016, "AA"): _ANCH, (2016, "A"): {"hit": {"p_pa": None}},
                   (2015, "AA"): _ANCH})
    f = PR.feature(7, 2017, "hit", src)
    assert f["seasons"] == [2015] and f["exposure"] == 50
    # a None rate on the line (missing pitches) is the same as no line
    src2 = _source({(2016, "AA"): {7: {"hit": {"pa": 300, "p_pa": None}}}},
                   {(2016, "AA"): _ANCH})
    assert PR.feature(7, 2017, "hit", src2)["value"] is None


def test_pitcher_reads_majority_role_line_against_role_anchor():
    src = _source({(2016, "AA"): {9: _pit("RP", 200, 4.4)},
                   (2015, "AA"): {9: _pit("SP", 59, 3.0)},
                   (2014, "AA"): {9: _pit("SP", 400, 3.8, basis="season_line_fallback")}},
                  {(2016, "AA"): _ANCH, (2015, "AA"): _ANCH, (2014, "AA"): _ANCH})
    f = PR.feature(9, 2017, "pit", src)
    assert f["seasons"] == [2016, 2014]
    want = (200 * math.log(4.4 / 4.0) + 400 * 0.0) / 600 * 600 / 700
    assert f["value"] == pytest.approx(want, abs=1e-12)
    assert PR.column_name("pit") == "pbf_rel" and PR.column_name("hit") == "ppa_rel"


# ---------------------------------------------------------------------------
# 2. missingness
# ---------------------------------------------------------------------------

def test_no_id_or_no_line_is_none_without_a_flag():
    src = _source({}, {})
    for pid in (None, 7):
        f = PR.feature(pid, 2017, "hit", src)
        assert f["value"] is None and f["has_block"] is False
        assert not any("absent" in k or "missing" in k for k in f)


def test_impute_at_train_mean_only():
    vals = {"a": 1.0, "b": 3.0, "c": None, "d": 10.0, "e": None}
    out = PR.impute_at_train_mean(vals, ["a", "b", "c"])
    assert out == {"a": 1.0, "b": 3.0, "c": 2.0, "d": 10.0, "e": 2.0}
    with pytest.raises(ValueError):
        PR.impute_at_train_mean(vals, ["c", "e"])


# ---------------------------------------------------------------------------
# 3. reserved frames
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("V", sorted(F.RESERVED_LV))
def test_reserved_vintages_raise_everywhere(V):
    src = _source({}, {})
    row = {"player_key": "a", "vintage": V, "side": "hit", "mlbam_id": 7}
    with pytest.raises(F.ReservedFrameError):
        PR.feature(7, V, "hit", src)
    with pytest.raises(F.ReservedFrameError):
        PR.attach([row], src)
    with pytest.raises(F.ReservedFrameError):
        PR.coverage({"hit": {V: []}})
    with pytest.raises(F.ReservedFrameError):
        PR.correlations([(V, 0.1, 0.2), (V, 0.2, 0.1), (V, 0.3, 0.4)])


def test_tool_drops_rvm_rows_and_reads_no_outcome():
    import efv_pitch_rate_sidecar as T
    lines = {(2016, "AA"): {7: _hit(300, 4.2), 8: _hit(300, 3.9), 9: _hit(300, 4.1)}}
    src = _source(lines, {(2016, "AA"): _ANCH})

    def row(pk, mid, debut=None, bb=0.01):
        return {"player_key": pk, "vintage": 2017, "side": "hit", "mlbam_id": mid,
                "debut_date": debut,
                "milb": {"obp_rel": bb, "k_rel": -bb, "bb_rel": bb, "rates_missing": 0.0}}

    frames = {"hit": {2017: [row("a", 7, bb=0.03), row("b", 8, "2025-04-01"),
                             row("c", 9, "2019-06-01", bb=0.02), row("d", None)]}}
    doc = T.build(frames=frames, source=src)
    assert doc["rvm_rows_dropped"] == {"hit": 1, "pit": 0}
    assert set(doc["rows"]["hit"]["2017"]) == {"a", "c"}
    assert doc["coverage"]["hit:2017"]["rows"] == 3
    assert doc["coverage"]["hit:2017"]["has_block"] == 2
    tags = set(doc["probes"])
    assert tags == {"PM19:coverage.ppa_rel:hit", "PM19:coverage.pbf_rel:pit",
                    "PM19:corr.ppa_rel:hit", "PM19:corr.pbf_rel:pit"}
    assert all(p["reads_outcome"] is False for p in doc["probes"].values())
    assert doc["steps"]["b"].startswith("not run")
    assert set(doc["rows"]["hit"]) <= {str(v) for v in F.DEV_VINTAGES}
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not any(m and ("label" in m or "war" in m.split("_")) for m in mods), mods


# ---------------------------------------------------------------------------
# 4. source scans
# ---------------------------------------------------------------------------

def _names(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            yield n.id
        elif isinstance(n, ast.Attribute):
            yield n.attr
        elif isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            yield n.name
        elif isinstance(n, ast.arg):
            yield n.arg


def test_module_reads_no_outcome_and_no_orphan_cache():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert mods <= _ALLOWED_IMPORTS, mods
    for name in _names(tree):
        assert not _OUTCOME_WORD.search(name.lower()), name
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) < 40:
            low = n.value.lower()
            assert not _OUTCOME_WORD.search(low.replace(" ", "_")), n.value
            assert "milb_platoon" not in low and "milb_stats" not in low, n.value


@pytest.mark.parametrize("path", [SRC, TOOL])
def test_no_fv_cell_grouping(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for name in _names(tree):
        assert not any(t in name.lower() for t in _BANNED_TOKENS), (path.name, name)
    for node in ast.walk(tree):
        if path == SRC and isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (node.value, node.lineno)


def test_no_em_dash():
    for p in (SRC, TOOL, Path(__file__)):
        txt = p.read_text(encoding="utf-8")
        assert chr(0x2014) not in txt and chr(0x2013) not in txt, p.name


# ---------------------------------------------------------------------------
# 5. the committed sidecar and the ledger
# ---------------------------------------------------------------------------

def test_committed_sidecar_is_development_only():
    if not SIDECAR.exists():
        pytest.skip("sidecar not built")
    doc = json.loads(SIDECAR.read_text(encoding="utf-8"))
    dev = {str(v) for v in F.DEV_VINTAGES}
    for side in F.SIDES:
        assert set(doc["rows"][side]) <= dev
    assert not any(str(v) in k for v in F.RESERVED_LV for k in doc["coverage"])
    assert doc["row_fields"] == ["value", "exposure", "seasons"]
    for side in F.SIDES:
        for V, blk in doc["rows"][side].items():
            for pk, (val, exp, seasons) in blk.items():
                assert isinstance(val, float) and exp > 0
                assert seasons and max(seasons) < int(V) and len(seasons) <= PR.MAX_SEASONS


def test_the_arm_ledger_counts_the_probes():
    if not (LEDGER.exists() and SIDECAR.exists()):
        pytest.skip("ledger or sidecar not built")
    import efv_arm_ledger as AL
    assert any(name.endswith("efv_pitch_rate_features.json") for name, _k, _l in AL.PROBES)
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    doc = json.loads(SIDECAR.read_text(encoding="utf-8"))
    mine = [p for p in led["probes"] if p["probe"].startswith("PM19:")]
    assert len(mine) == doc["n_probes"] == len(doc["probes"])
    assert all(p["lane"] != a["lane"] for p in mine for a in led["arms"])

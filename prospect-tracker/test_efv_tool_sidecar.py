# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""TL_9_EFV_TOOL_SIDECAR pins (Part 9 PLAN section 9.4.5; LANE_C.md section 2.7).

1. Guards: list vintages 2020 and 2021 raise while EFV_V2_GATE.md '## 9. Results' holds
   no R-LV entry; vintages reaching the R-VM cohorts raise; R-VM rows are dropped before
   any count; every input season is at most V - 1 and before 2026.
2. No outcome column read: the modules import no WAR, label or outcome module, a frame
   row's own fields at or after V never move its features, and the TIP fit asks for no
   MLB season at or after V.
3. The columns: earliest in-window grade per source, the consensus rule, pwr_comp is
   'not a candidate' unless look P served C2 with a below 1, the residual is shrunk ISO
   minus tip_level, and missing values carry no flag (imputed at the TRAIN mean).
4. The committed sidecar: development vintages only, keys match efv_vintage_frame rows,
   and the arm ledger counts its probes with role development.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

import efv_tool_features as TF
import efv_vintage_frame as F

ROOT = Path(__file__).parent
SRC = ROOT / "efv_tool_features.py"
TOOL = ROOT / "tools" / "efv_tool_sidecar.py"
SIDECAR = ROOT / "data" / "_labs" / "efv_tool_features.json"
LEDGER = ROOT / "data" / "xfv_arm_ledger.json"
sys.path.insert(0, str(ROOT / "tools"))

_OUTCOME_MODULES = re.compile(r"(war|label|outcome|ewar|fwar|w3|efv_labels|career_war|"
                              r"statsapi_saber|milb_platoon)")
_BANNED_TOKENS = ("groupby", "by_fv", "fv_band", "fv_bin", "fv_cell", "stratum", "strata")


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _row(pk, V, *, pid, side="hit", debut=None, level="AA", season=None):
    return {"player_key": pk, "mlbam_id": pid, "side": side, "vintage": V,
            "window": [f"{V}-01-01", f"{V}-05-01"], "debut_date": debut,
            "milb": {"milb_level": level, "milb_season": V - 1 if season is None else season}}


def _fixture(V=2019):
    """Frames for V - 2 .. V: 40 earlier-vintage hitters who debuted before V (the TIP
    fit set, game power 40 to 60 in two bins of 20) and three rows at V."""
    frames = {"hit": {}, "pit": {}}
    snaps = {}
    mlb_iso = {}
    for i in range(40):
        pk = f"fit_{i}"
        Y = V - 2
        g = 40.0 if i < 20 else 60.0
        frames["hit"].setdefault(Y, []).append(
            _row(pk, Y, pid=1000 + i, debut=f"{V - 1}-06-01"))
        snaps[pk] = [("fangraphs", f"{Y}-02-01", {"hit": 50, "game_pwr": g, "raw_pwr": g})]
        mlb_iso[1000 + i] = 0.120 if g < 50 else 0.200
    frames["hit"][V] = [
        _row("a_hitter", V, pid=1, level="AA"),
        _row("b_nogrades", V, pid=2, level="A"),
        _row("c_rvm", V, pid=3, debut="2025-05-01"),
    ]
    snaps["a_hitter"] = [("mlb_pipeline", f"{V}-03-01", {"hit": 55, "game_pwr": 60}),
                         ("mlb_pipeline", f"{V}-04-01", {"hit": 70, "game_pwr": 70}),
                         ("fangraphs", f"{V}-02-15", {"hit": 50, "game_pwr": 55,
                                                      "raw_pwr": 65}),
                         ("fangraphs", f"{V - 1}-12-01", {"hit": 80, "game_pwr": 80})]
    snaps["c_rvm"] = [("fangraphs", f"{V}-02-15", {"hit": 50, "game_pwr": 50})]
    frames["pit"][V] = [_row("p_arm", V, pid=4, side="pit")]
    asked: list = []

    def mlb_iso_line(pid, season):
        asked.append(season)
        iso = mlb_iso.get(pid)
        if iso is None:
            return None
        return {"ab": 400.0, "pa": 450.0, "doubles": iso * 400.0, "triples": 0.0, "hr": 0.0}

    def league(season):
        return [{"mlbam": 9000 + k, "season": season, "level": lv, "age": 22, "pa": 300,
                 "ab": 270, "avg": ".250", "slg": ".400" if lv == "MLB" else ".380"}
                for k, lv in enumerate(["AA", "AAA", "MLB", "A"])]

    def milb(pid, season, level):
        if pid == 1:
            return {"pa": 400, "avg": ".280", "slg": ".480"}
        return None

    look_p = {"verdict": {"serve": "C0"}, "served_a": 1.0}
    return frames, snaps, mlb_iso_line, league, milb, look_p, asked


def _build(V=2019, **over):
    import efv_tool_sidecar as T
    frames, snaps, mlb, league, milb, look_p, asked = _fixture(V)
    kw = dict(frames=frames, snaps=snaps, mlb=mlb, league=league, milb=milb, look_p=look_p,
              vintages=(V - 2, V))
    kw.update(over)
    return T.build(**kw), asked


# ---------------------------------------------------------------------------
# 1. guards
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("V", sorted(F.RESERVED_LV))
def test_reserved_vintage_raises_without_rlv_record(V):
    with pytest.raises(TF.SidecarGuardError):
        TF.assert_vintage_allowed(V)
    import efv_tool_sidecar as T
    with pytest.raises(TF.SidecarGuardError):
        T.build(frames={"hit": {}, "pit": {}}, snaps={}, vintages=(V,))


def test_rvm_vintage_raises_even_with_record():
    with pytest.raises(TF.SidecarGuardError):
        TF.assert_vintage_allowed(F.R_VM_FIRST_DEBUT_YEAR, rlv_record=True)


def test_rlv_record_reads_section_9_only():
    import efv_tool_sidecar as T
    empty = "## 9. Results\n\n(Empty. Filled only by the look runner.)\n\n---\n\n## 10. X\nR-LV\n"
    filled = "## 9. Results\n\n### R-LV look (2026-12-01)\nrows\n\n## 10. X\n"
    assert T.rlv_record_exists(empty) is False
    assert T.rlv_record_exists(filled) is True
    # the committed gate holds no R-LV entry today, so no 2020 or 2021 row may exist
    assert T.rlv_record_exists() is False


def test_seasons_at_or_after_v_raise():
    with pytest.raises(TF.SidecarGuardError):
        TF.assert_seasons_before(2019, [2018, 2019], "x")
    with pytest.raises(TF.SidecarGuardError):
        TF.assert_seasons_before(2030, [2026], "x")
    TF.assert_seasons_before(2019, [2014, 2018], "x")


def test_career_rows_refuse_a_mislabelled_season():
    def league(season):
        return [{"mlbam": 1, "season": season + 1, "level": "AA", "age": 22, "pa": 100}]
    with pytest.raises(TF.SidecarGuardError):
        TF.career_rows(league, 2019)


def test_career_rows_window_is_before_v():
    cs, bd, seasons = TF.career_rows(lambda s: [], 2019)
    assert seasons == list(range(2019 - TF.CAREER_WINDOW, 2019))
    assert max(seasons) <= 2018


def test_rvm_rows_dropped_before_any_count():
    doc, _ = _build()
    assert doc["rvm_rows_dropped"]["hit"] == 1
    assert "c_rvm" not in json.dumps(doc["rows"])
    assert doc["coverage"]["hit:2019"]["rows"] == 2


# ---------------------------------------------------------------------------
# 2. no outcome column read
# ---------------------------------------------------------------------------

def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


@pytest.mark.parametrize("path", [SRC, TOOL])
def test_no_outcome_module_imported(path):
    bad = sorted(m for m in _imports(path) if _OUTCOME_MODULES.search(m))
    assert bad == []


def test_fit_never_asks_for_a_season_at_or_after_v():
    _doc, asked = _build()
    assert asked and max(asked) <= 2018


def test_row_outcome_fields_do_not_move_its_features():
    base, _ = _build()
    frames, snaps, mlb, league, milb, look_p, _a = _fixture()
    for r in frames["hit"][2019]:
        r.update({"w3": 9.9, "war": 4.2, "label": 1, "debut_date": r["debut_date"]
                  if r["player_key"] == "c_rvm" else "2020-04-01"})
    import efv_tool_sidecar as T
    moved = T.build(frames=frames, snaps=snaps, mlb=mlb, league=league, milb=milb,
                    look_p=look_p, vintages=(2017, 2019))
    assert moved["rows"]["hit"]["2019"] == base["rows"]["hit"]["2019"]


# ---------------------------------------------------------------------------
# 3. the columns
# ---------------------------------------------------------------------------

def test_earliest_in_window_grade_per_source():
    _f, snaps, *_ = _fixture()
    ps = TF.earliest_grades(snaps["a_hitter"], "2019-01-01", "2019-05-01")
    assert ps == {"mlb_pipeline": {"hit": 55.0, "game_pwr": 60.0},
                  "fangraphs": {"hit": 50.0, "game_pwr": 55.0, "raw_pwr": 65.0}}
    assert TF.earliest_grades(snaps["a_hitter"], "2019-01-01", "2019-05-01",
                              frozenset({"fangraphs"})) == {"mlb_pipeline": {"hit": 55.0,
                                                                             "game_pwr": 60.0}}


def test_consensus_is_the_rounded_unweighted_mean():
    c = TF.consensus({"a": {"hit": 55.0, "game_pwr": 60.0},
                      "b": {"hit": 50.0, "game_pwr": 55.0, "raw_pwr": 65.0}})
    assert c == {"hit": 52.5, "game_pwr": 57.5, "raw_pwr": 65.0}
    assert TF.consensus({"a": {"hit": 51.0}, "b": {"hit": 50.0}})["hit"] == 50.5


@pytest.mark.parametrize("result,cand", [
    ({"verdict": {"serve": "C0"}, "served_a": 1.0}, False),
    ({"verdict": {"serve": "C1"}, "served_a": 1.0}, False),
    ({"verdict": {"serve": "C2"}, "served_a": 1.0}, False),
    ({"verdict": {"serve": "C2"}, "served_a": 0.8}, True),
    (None, False),
])
def test_pwr_comp_candidate_only_on_c2_below_one(result, cand):
    st = TF.pwr_comp_status(result)
    assert st["candidate"] is cand
    assert ("not a candidate" in st["reason"]) is (not cand)
    assert "served_a" not in st and "a" not in st


def test_residual_is_shrunk_iso_minus_tip():
    doc, _ = _build()
    row = doc["rows"]["hit"]["2019"]["a_hitter"]
    per_source, cons, resid, iso_shrunk, tip, level, season, pa = row
    assert cons == [52.5, 57.5, 65.0]
    assert level == "AA" and season == 2018 and pa == 400
    assert tip is not None and iso_shrunk is not None
    assert resid == pytest.approx(iso_shrunk - tip, abs=2e-6)
    s = TF.shrunk_iso({"pa": 400, "avg": ".280", "slg": ".480"}, 0.13)
    assert s["value"] == pytest.approx(0.13 + 400 / 450 * (0.200 - 0.13))
    assert doc["pwr_comp"]["candidate"] is False
    assert doc["tip_tables"]["2019"]["fit_max_season"] <= 2018
    assert doc["tip_tables"]["2019"]["career_seasons"][-1] == 2018


def test_missing_carries_no_flag_and_imputes_at_train_mean():
    doc, _ = _build()
    assert "b_nogrades" not in doc["rows"]["hit"]["2019"]
    for side in doc["rows"].values():
        for blk in side.values():
            for v in blk.values():
                assert len(v) == len(doc["row_fields"])
    assert not any("missing" in f or "absent" in f for f in doc["row_fields"])
    out = TF.impute_at_train_mean({"a": 1.0, "b": None, "c": 3.0, "d": 9.0}, ["a", "b", "c"])
    assert out == {"a": 1.0, "b": 2.0, "c": 3.0, "d": 9.0}
    with pytest.raises(ValueError):
        TF.impute_at_train_mean({"a": None, "b": 1.0}, ["a"])


def test_no_fv_cell_grouping_and_no_emdash():
    for path in (SRC, TOOL, Path(__file__)):
        text = path.read_text(encoding="utf-8")
        assert chr(0x2014) not in text and chr(0x2013) not in text
        if path != Path(__file__):
            low = text.lower()
            assert not [t for t in _BANNED_TOKENS if t in low]


# ---------------------------------------------------------------------------
# 4. the committed sidecar
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def doc():
    if not SIDECAR.exists():
        pytest.skip("sidecar not built")
    return json.loads(SIDECAR.read_text(encoding="utf-8"))


def test_committed_sidecar_reads_development_vintages_only(doc):
    vs = {int(v) for side in doc["rows"].values() for v in side}
    assert vs <= set(F.DEV_VINTAGES)
    assert not vs & set(F.RESERVED_LV)
    assert doc["guards"]["vintages_read"] == list(F.DEV_VINTAGES)
    assert doc["pwr_comp"]["candidate"] is False
    for t in doc["tip_tables"].values():
        assert t["career_seasons"] and max(t["career_seasons"]) < 2026
        if t["fit_max_season"] is not None:
            assert t["fit_max_season"] <= max(t["career_seasons"])
    text = json.dumps(doc["rows"])
    assert '"w3"' not in text and '"war"' not in text


def test_committed_sidecar_keys_match_the_frame(doc):
    V = max(F.DEV_VINTAGES)
    frame = F.build_frame("hit", V, sidecars=False, milb=False)
    keys = {r["player_key"] for r in frame if not TF.is_rvm(r)}
    assert set(doc["rows"]["hit"][str(V)]) <= keys
    assert doc["coverage"][f"hit:{V}"]["rows"] == len(keys)


def test_ledger_counts_the_probes(doc):
    import efv_arm_ledger as AL
    assert any(name.endswith("efv_tool_features.json") for name, _k, _l in AL.PROBES)
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    tl9 = [p for p in led["probes"] if str(p.get("probe", "")).startswith("TL9:")]
    assert {p["probe"] for p in tl9} == set(doc["probes"])
    assert all(p.get("role") == "development" for p in tl9)
    assert all(p["reads_outcome"] is False for p in doc["probes"].values())

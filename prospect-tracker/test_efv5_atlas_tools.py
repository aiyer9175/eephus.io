# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the eFV v5 atlas part two (efv5_atlas_tools.py, EFV5_ATLAS_TOOLS_STATCAST).

1. Tool grades as of the list: per source the latest board inside the row's own V
   window and on or before the as-of date; never a later board, never a board of
   another list vintage; future, present, gap and source disagreement by the rule.
2. The level as of the list is the highest qualified level of S; the consensus read
   with its as-of date matches the first atlas's read row for row.
3. Statcast components: the approach angle matches the kinematics solved directly;
   class rates need CLASS_MIN pitches; chase reads out-of-zone tracked pitches only;
   the primary fastball is the most thrown fastball.
4. Bans: the first atlas's metric list and artifacts are untouched; no network, no
   served import, no FV-cell grouping, no em-dash.
5. The artifact, when present: development only, its own families, every candidate
   meets the first atlas's rule, the cells file matches its columns.
No test touches the network.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import efv5_atlas as A  # noqa: E402
import efv5_atlas_tools as X  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import efv_w2_scout as SC  # noqa: E402

SRC = ROOT / "efv5_atlas_tools.py"
TEST_SRC = Path(__file__)


# ---------------------------------------------------------------------------
# tool grades as of the list
# ---------------------------------------------------------------------------

def _tj(tools, present=None, arm=None):
    t = dict(tools)
    ex = {}
    if present is not None:
        ex["present"] = present
    if arm is not None:
        ex["arm"] = arm
    if ex:
        t["_extras"] = ex
    return json.dumps(t)


def _index():
    rows = [
        # an older list vintage's board: never read for a 2019 row
        ("fangraphs", "2018-02-15", "p1", "SS", _tj({"hit": 40, "speed": 50}, {"hit": 20})),
        ("fangraphs", "2019-02-13", "p1", "SS", _tj({"hit": 55, "raw_pwr": 60, "game_pwr": 50,
                                                     "speed": 60, "field": 50},
                                                    {"hit": 30, "raw_pwr": 50, "game_pwr": 30},
                                                    arm=55)),
        ("mlb_pipeline", "2019-01-22", "p1", "SS", _tj({"hit": 50, "game_pwr": 45, "speed": 55,
                                                        "field": 55, "throw": 60})),
        # after the as-of date: never read
        ("fangraphs", "2019-04-20", "p1", "SS", _tj({"hit": 80})),
        ("mlb_pipeline", "2019-01-22", "p2", "RHP", _tj({"fb": 60, "sl": 55, "cmd": 45})),
        ("fangraphs", "2019-02-13", "p2", "RHP", _tj({"fb": 65, "ct": 50, "cmd": 40},
                                                     {"fb": 50, "cmd": 35})),
    ]
    return SC.SnapshotIndex.from_rows(rows, cap="2026-05-01")


def test_tool_values_read_the_list_and_never_later():
    idx = _index()
    per = X.list_entries(idx, "p1", "2019-03-01", "2019-01-01")
    assert set(per) == {"fangraphs", "mlb_pipeline"}
    assert per["fangraphs"][0] == "2019-02-13"            # not 2019-04-20, not 2018
    v = X.tool_values(per, "hit")
    assert v["tg_hit_fut_hit"] == pytest.approx(52.5)
    assert v["tg_hit_pre_hit"] == pytest.approx(30.0)
    assert v["tg_hit_gap_hit"] == pytest.approx(25.0)     # FanGraphs only carries both
    assert v["tg_hit_fgmp_hit"] == pytest.approx(5.0)
    assert v["tg_raw_pwr_fut_hit"] == pytest.approx(60.0)
    assert "tg_raw_pwr_fgmp_hit" not in v                 # Pipeline carries no raw power
    assert v["tg_arm_fut_hit"] == pytest.approx((55 + 60) / 2.0)   # FanGraphs _extras arm
    assert v["tg_run_fgmp_hit"] == pytest.approx(5.0)
    assert not any(k.endswith("_pit") for k in v)
    # an as-of date before the window's boards reads nothing from an older vintage
    assert X.list_entries(idx, "p1", "2019-01-10", "2019-01-01") == {}
    assert X.list_entries(idx, "p1", None, "2019-01-01") == {}


def test_pitcher_tools_and_cutter():
    idx = _index()
    v = X.tool_values(X.list_entries(idx, "p2", "2019-03-01", "2019-01-01"), "pit")
    assert v["tg_fb_fut_pit"] == pytest.approx(62.5)
    assert v["tg_fb_fgmp_pit"] == pytest.approx(5.0)
    assert v["tg_fb_gap_pit"] == pytest.approx(15.0)
    assert v["tg_ct_fut_pit"] == pytest.approx(50.0) and "tg_ct_fgmp_pit" not in v
    assert v["tg_cmd_pre_pit"] == pytest.approx(35.0)
    assert "tg_sl_pre_pit" not in v and v["tg_sl_fut_pit"] == pytest.approx(55.0)


def test_snapshot_cap_closes_before_the_horizon_season():
    assert X.TOOL_SNAPSHOT_CAP == f"{A.HORIZON}-05-01"
    idx = SC.SnapshotIndex.from_rows(
        [("fangraphs", "2026-07-23", "p9", "SS", _tj({"hit": 70}))], cap=X.TOOL_SNAPSHOT_CAP)
    assert idx.by_key == {}


def test_tool_metric_menu():
    hit = X.side_metrics("tools", "hit")
    pit = X.side_metrics("tools", "pit")
    assert len(hit) == 6 * 4 and len(pit) == 6 * 4
    for t in ("hit", "raw_pwr", "game_pwr", "run", "field", "arm"):
        for p in ("fut", "pre", "gap", "fgmp"):
            assert f"tg_{t}_{p}_hit" in hit
    for t in ("fb", "sl", "cb", "ch", "ct", "cmd"):
        assert f"tg_{t}_fut_pit" in pit
    assert set(X.FAMILIES) == {m[0] for m in X.METRICS.values()}


# ---------------------------------------------------------------------------
# rows
# ---------------------------------------------------------------------------

def _base(rows):
    return A.Table("hit", rows, ["k_pct_hit"])


def _r(pid, season, level, fv, band="young", group="SS"):
    return {"pid": pid, "season": season, "level": level, "band": band, "group": group, "fv": fv,
            "m": {"k_pct_hit": 0.2}, "y": {lb: (1.0 if lb == "reach3" else None) for lb in A.LABELS}}


def test_level_as_of_the_list_is_the_highest_qualified_level():
    T = _base([_r(1, 2018, "A", 50.0), _r(1, 2018, "A+", 50.0, band="old"),
               _r(2, 2018, "AA", None), _r(3, 2017, "CPX", 45.0), _r(3, 2018, "A-", 45.0)])
    best = X.list_level_rows(T)
    assert set(best) == {(1, 2018), (3, 2017), (3, 2018)}
    assert T.level[best[(1, 2018)]] == "A+" and T.band[best[(1, 2018)]] == "old"
    row = X._row_from(T, best[(1, 2018)], {"tg_hit_fut_hit": 55.0})
    assert row["y"]["reach3"] == 1.0 and row["y"]["l6"] is None and row["fv"] == 50.0


def test_consensus_read_matches_the_first_atlas(monkeypatch):
    def fake_frame(side, V, **kw):
        assert int(V) not in F.RESERVED_LV
        return [{"player_key": f"k{V}{i}", "mlbam_id": 100 + i, "window": [f"{V}-01-01", f"{V}-05-01"],
                 "position": "SS" if i % 2 else "CF", "asof_date": f"{V}-02-0{i + 1}",
                 "grades": {A.SB.CONSENSUS_KEY: 40.0 + i}} for i in range(4)]
    monkeypatch.setattr(F, "build_frame", fake_frame)
    a = A.consensus_reads("hit", {}, vintages=(2018, 2019), universe={}, log=lambda *_: None)
    b = X.consensus_reads_asof("hit", {}, vintages=(2018, 2019), universe={}, log=lambda *_: None)
    assert set(a) == set(b)
    for k in a:
        assert {kk: b[k][kk] for kk in a[k]} == a[k]
        assert b[k]["asof"].startswith(str(k[1] + 1)) and b[k]["vintage"] == k[1] + 1
    with pytest.raises(AssertionError):
        X.consensus_reads_asof("hit", {}, vintages=(2020,), universe={}, log=lambda *_: None)


# ---------------------------------------------------------------------------
# Statcast components
# ---------------------------------------------------------------------------

def _vaa_direct(vy0, vz0, ay, az):
    # y(t) = 50 + vy0 t + ay t^2 / 2 reaches 17/12 ft: the smaller positive root
    a, b, c = 0.5 * ay, vy0, 50.0 - 17.0 / 12.0
    t = (-b - math.sqrt(b * b - 4 * a * c)) / (2 * a)
    vy, vz = vy0 + ay * t, vz0 + az * t
    return -math.degrees(math.atan(vz / vy))


def test_vaa_matches_the_kinematics():
    for vy0, vz0, ay, az in ((-135.0, -5.0, 28.0, -15.0), (-125.0, -2.0, 24.0, -25.0)):
        assert float(X.vaa_deg(vy0, vz0, ay, az)) == pytest.approx(_vaa_direct(vy0, vz0, ay, az), abs=1e-9)
    assert -9.0 < float(X.vaa_deg(-135.0, -5.0, 28.0, -15.0)) < -3.0


def _pitches():
    pd = pytest.importorskip("pandas")
    rows = []
    # pitcher 7, 2023, AAA: 60 four-seamers, 30 sinkers, 40 sliders, 10 changeups
    for i in range(60):
        rows.append(("FF", 95.0, 6.0, 2300.0, 7, "swinging_strike" if i < 12 else
                     ("foul" if i < 30 else "called_strike" if i < 45 else "ball"),
                     5 if i < 40 else 12, 0.1, -137.0, -4.0, 30.0, -12.0, 1, 2023, "AAA"))
    for i in range(30):
        rows.append(("SI", 94.0, 5.5, 2100.0, 7, "ball", 13, 0.1, -136.0, -6.0, 29.0, -20.0, 1, 2023, "AAA"))
    for i in range(40):
        rows.append(("SL", 86.0, 5.9, 2500.0, 7, "swinging_strike" if i < 10 else "ball",
                     14 if i < 20 else 3, 0.2, -125.0, -3.0, 25.0, -30.0, 1, 2023, "AAA"))
    for i in range(10):
        rows.append(("CH", 87.0, 5.9, 1800.0, 7, "ball", 14, 0.2, -127.0, -3.0, 25.0, -30.0, 1, 2023, "AAA"))
    # an untracked out-of-zone swing: not in the chase denominator
    rows.append(("SL", None, None, None, 7, "swinging_strike", None, None, None, None, None, None, 1, 2023, "AAA"))
    # a High-A line: not a tracked level, never read
    rows.append(("FF", 95.0, 6.0, 2300.0, 8, "ball", 12, 0.1, -137.0, -4.0, 30.0, -12.0, 2, 2023, "A+"))
    cols = list(X._PITCH_COLS) + ["level"]
    return pd.DataFrame(rows, columns=cols)


def test_pitch_components_rules():
    pc = X.pitch_components(_pitches(), min_pitches=100, class_min=25)
    assert set(pc) == {(7, 2023, "AAA")}
    v = pc[(7, 2023, "AAA")]
    # primary fastball FF: spin, height, approach angle of the four-seamers only
    assert v["sc_fb_spin_pit"] == pytest.approx(2300.0) and v["sc_fb_rel_z_pit"] == pytest.approx(6.0)
    assert v["sc_fb_vaa_pit"] == pytest.approx(_vaa_direct(-137.0, -4.0, 30.0, -12.0), abs=1e-9)
    # fastball class = FF + SI (90 pitches): 12 whiffs of 30 swings; 15 called strikes
    assert v["sc_whiff_fb_pit"] == pytest.approx(12 / 30)
    assert v["sc_cstr_fb_pit"] == pytest.approx(15 / 90)
    # out of zone fastballs: FF 40..59 (zone 12; 0 swings), SI 30 (zone 13; 0 swings)
    assert v["sc_chase_fb_pit"] == pytest.approx(0.0)
    # breaking: 41 pitches (one untracked); out of zone tracked 20, swung at 10
    assert v["sc_chase_br_pit"] == pytest.approx(10 / 20)
    assert v["sc_whiff_br_pit"] == pytest.approx(11 / 11)
    # offspeed: 10 pitches, under CLASS_MIN: no rate
    assert not any(k.endswith("_os_pit") for k in v)
    # under the exposure rule: no line
    assert X.pitch_components(_pitches(), min_pitches=1000) == {}


# ---------------------------------------------------------------------------
# bans
# ---------------------------------------------------------------------------

def test_first_atlas_metric_list_untouched():
    assert not any(m.startswith(("tg_", "sc_")) for m in A.METRICS)
    assert not set(X.METRICS) & set(A.METRICS)
    assert X.OUT_PATH != A.OUT_PATH and X.CELLS_PATH != A.CELLS_PATH
    assert X.CELL_COLUMNS == A.CELL_COLUMNS


def test_source_bans():
    src = SRC.read_text(encoding="utf-8")
    for text in (src, TEST_SRC.read_text(encoding="utf-8")):
        assert chr(0x2014) not in text and chr(0x2013) not in text
    assert not re.search(r"(by|per|group)_?(fv|consensus|grade)", src)
    assert not re.search(r"fv_cell|fv_tier|fv_bucket", src)
    for banned in ("import backtest", "run_backtest", "import efv_export", "import proj_export",
                   "train_proj_models", "import efv_score", "import storage", "urlopen",
                   "http_get", "fetch_day", "fetch_all", "fetch_schedule(", "fetch_profile",
                   "warm_profile", "A.OUT_PATH", "A.CELLS_PATH", "write_artifact(res"):
        assert banned not in src, banned


# ---------------------------------------------------------------------------
# the artifact, when present
# ---------------------------------------------------------------------------

def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


@pytest.fixture(scope="module")
def artifact():
    if not X.OUT_PATH.exists():
        pytest.skip("artifact not built")
    return json.loads(X.OUT_PATH.read_text(encoding="utf-8"))


def test_artifact_is_development_only(artifact):
    assert artifact["schema"] == X.SCHEMA and artifact["item"] == X.ITEM
    assert artifact["role"] == "development" and artifact["served"] is False
    d = artifact["declared"]
    assert d["min_players"] == A.MIN_PLAYERS and d["min_pos"] == A.MIN_POS
    assert d["seed"] == A.SEED and d["folds"] == A.FOLDS
    assert d["reserved_lv_never_built"] == sorted(F.RESERVED_LV)
    assert set(d["consensus_vintages"]).isdisjoint(F.RESERVED_LV)
    assert d["tool_snapshot_cap"] == X.TOOL_SNAPSHOT_CAP
    assert artifact["inputs"]["fwar_vintage_id"].startswith("2026-10-02")
    assert set(artifact["tests_by_family"]) == set(X.FAMILIES)


def test_artifact_names_no_fv_cell_and_no_emdash(artifact):
    cell = re.compile(r"\bfv\s*_?\s*(35|40|45|50|55|60|65|70|80)\b", re.I)
    for s in _strings(artifact):
        assert chr(0x2014) not in s
        assert not cell.search(s), s
    for key in ("groups", "top_by_group", "candidates", "top_cells"):
        assert "fv" not in json.dumps(artifact[key]).lower().replace("consensus_raw", "")


def test_artifact_candidates_meet_the_rule(artifact):
    for c in artifact["candidates"]:
        assert c["incr"] > 0 and c["ci95"][0] > 0 and c["q"] <= A.CANDIDATE_Q
        assert c["metric"] in X.METRICS and c["family"] in X.FAMILIES
        assert c["status"] in ("clean", "spent-overlap")
        if c["frame"] == "clean":
            assert c["status"] == "clean"
        assert c["players"] >= A.MIN_PLAYERS
    for fam, blocks in artifact["top_cells"].items():
        for r in blocks["clean"]:
            assert r["status"] == "clean"
        for r in blocks["any"]:
            assert r["passes_rule"] == (r["incr"] > 0 and r["ci95"] is not None and r["ci95"][0] > 0
                                        and r["q"] is not None and r["q"] <= A.CANDIDATE_Q)


def test_cells_file_matches_columns(artifact):
    p = ROOT / artifact["cells_file"]
    if not p.exists():
        pytest.skip("cells file not built")
    cells = json.loads(p.read_text(encoding="utf-8"))
    assert cells["columns"] == list(A.CELL_COLUMNS)
    assert len(cells["rows"]) == artifact["tests"]
    cols = {c: i for i, c in enumerate(cells["columns"])}
    for row in cells["rows"]:
        assert row[cols["level"]] in A.LEVELS and row[cols["label"]] in A.LABELS
        assert row[cols["metric"]] in X.METRICS
        assert row[cols["family"]] == X.METRICS[row[cols["metric"]]][0]
        if row[cols["family"]] == "statcast":
            assert row[cols["level"]] in X.TRACK_LEVELS
        s_full, s_listed = row[cols["seasons_full"]], row[cols["seasons_listed"]]
        s_max = max(s[1] for s in (s_full, s_listed) if s)
        assert row[cols["reserved_overlap"]] == (A.label_max_debut(row[cols["label"]], s_max)
                                                 >= F.R_VM_FIRST_DEBUT_YEAR)
        if row[cols["frame"]] == "clean":
            assert row[cols["reserved_overlap"]] is False
        if row[cols["players_listed"]] is not None:
            assert row[cols["players_listed"]] >= A.MIN_PLAYERS

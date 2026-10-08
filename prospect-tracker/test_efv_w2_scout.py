# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Wave 2 scouting-grade pins (efv_w2_scout.py; EFV3_W2_1a, owner EW2-6).

1. As of: a snapshot dated after a row's as-of date is never read, nor one older than
   the lookback; nothing at or past the R-VM cap is loaded or asked for.
2. The columns: source mean, best breaking ball, present grades (FanGraphs and the
   Pipeline report text), the arm fallback, position value.
3. The lab column builder reads each frame row at its own as-of date and trips on a
   reserved list vintage; the guards trip on 2020 and on a 2025 debut year.
4. The arms are registered in the screening lab; the module groups nothing by
   consensus-FV level and carries no em or en dash.
5. A column V2's rule refuses reproduces the base in every fold on both frames; the
   forced sensitivity moves the order; the progress rows are development rows with a
   screening block and no PASS.

Synthetic rows and fixture snapshots throughout; nothing here builds a real frame.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_progress as P  # noqa: E402
import efv_screen_lab as LAB  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import efv_w2_scout as W  # noqa: E402

SRC = ROOT / "efv_w2_scout.py"
WEIGHTS = {"hit": {"w_skill": 0.5, "w_time": 0.2}, "pit": {"w_skill": 0.5, "w_time": 0.2}}
B_FAST = 60


def _tj(tools=None, present=None, report=None, arm=None):
    ex = {}
    if present:
        ex["present"] = present
    if report:
        ex["report"] = report
    if arm is not None:
        ex["arm"] = arm
    d = dict(tools or {})
    if ex:
        d["_extras"] = ex
    return json.dumps(d)


@pytest.fixture()
def index():
    rows = [
        ("mlb_pipeline", "2016-01-22", "a", "RHP", _tj({"fb": 55, "sl": 50, "cb": 60, "cmd": 45})),
        ("fangraphs", "2017-02-15", "a", "RHP",
         _tj({"fb": 65, "sl": 55, "ch": 50, "cmd": 50}, present={"cmd": 40, "fb": 55})),
        ("mlb_pipeline", "2017-01-22", "a", "RHP", _tj({"fb": 60, "sl": 45, "cb": 50, "cmd": 50})),
        # after the as-of date below: must never be read
        ("fangraphs", "2017-07-31", "a", "RHP", _tj({"fb": 80, "sl": 80, "ch": 80, "cmd": 80},
                                                    present={"cmd": 80})),
        ("mlb_pipeline", "2018-01-22", "a", "RHP", _tj({"fb": 80, "cmd": 80})),
        # Pipeline 2013 report-text grades
        ("mlb_pipeline", "2013-01-22", "b", "SS/2B", _tj(report=(
            "Scouting Grades* (present/future): Hit: 4/6 | Power: 3/5 | Run: 5/5 | "
            "Arm: 5/6 | Field: 5/5 | Overall: 4/5 Every class has one."))),
        ("fangraphs", "2017-02-15", "c", "CF", _tj({"field": 60, "raw_pwr": 55},
                                                   arm=45)),
        ("mlb_pipeline", "2017-01-22", "c", "OF", _tj({"field": 50, "throw": 55})),
        ("mlb_pipeline", "2011-01-22", "d", "OF", _tj({"field": 50})),
        # at the cap: never loaded
        ("fangraphs", W.SNAPSHOT_CAP, "a", "RHP", _tj({"fb": 80})),
    ]
    return W.SnapshotIndex.from_rows(rows)


# ---------------------------------------------------------------------------
# 1. as of
# ---------------------------------------------------------------------------

def test_a_snapshot_after_the_asof_date_is_never_read(index):
    got = index.asof("a", "2017-03-01")
    assert {s: e[0] for s, e in got.items()} == {"fangraphs": "2017-02-15",
                                                  "mlb_pipeline": "2017-01-22"}
    assert W.component_value("fb", got) == 62.5          # (65 + 60) / 2, never 80
    # the same-day read is allowed (on or before), the next board is not
    assert index.asof("a", "2017-01-22")["mlb_pipeline"][0] == "2017-01-22"
    assert "fangraphs" not in index.asof("a", "2017-01-22")
    for asof in ("2016-02-01", "2017-01-21", "2017-05-01", "2017-07-30"):
        for e in index.asof("a", asof).values():
            assert e[0] <= asof


def test_the_lookback_drops_a_stale_board(index):
    # 2011-01-22 is more than LOOKBACK_DAYS before 2013-01-01
    assert index.asof("d", "2012-01-01")["mlb_pipeline"][0] == "2011-01-22"
    assert index.asof("d", "2013-01-01") == {}
    assert index.asof("d", None) == {}


def test_nothing_at_or_past_the_r_vm_cap_is_loaded_or_asked(index):
    assert all(e[0] < W.SNAPSHOT_CAP for es in index.by_key.values() for e in es)
    with pytest.raises(F.ReservedFrameError):
        index.asof("a", W.SNAPSHOT_CAP)
    assert W.SNAPSHOT_CAP == f"{F.R_VM_FIRST_DEBUT_YEAR}-01-01"


# ---------------------------------------------------------------------------
# 2. the columns
# ---------------------------------------------------------------------------

def test_the_columns(index):
    a = index.asof("a", "2017-03-01")
    assert W.component_value("brk", a) == pytest.approx((55 + 50) / 2)  # FG sl, PL max(45, 50)
    assert W.component_value("ch", a) == 50.0                            # FanGraphs alone
    assert W.component_value("cmd", a) == 50.0
    assert W.component_value("cmd_present", a) == 40.0                   # FanGraphs present
    b = index.asof("b", "2013-03-01")
    assert W.component_value("game_pwr", b) == 50.0                      # report text 3/5
    assert W.component_value("pwr_present", b) == 30.0
    assert W.component_value("arm", b) == 60.0
    assert W.component_value("posval", b) == W.POSITION_RUNS["SS"]
    assert W.component_value("raw_pwr", b) is None                       # Pipeline has none
    c = index.asof("c", "2017-03-01")
    assert W.component_value("arm", c) == pytest.approx((45 + 55) / 2)  # FG extras arm
    assert W.component_value("posval", c) == W.POSITION_RUNS["CF"]      # FanGraphs first
    assert W.component_value("raw_pwr", c) == 55.0


def test_position_value_and_report_parse():
    assert W._position_runs("RHP/CF") == W.POSITION_RUNS["CF"]
    assert W._position_runs("LHP") is None and W._position_runs(None) is None
    assert W._position_runs("OF") == pytest.approx((2.5 - 7.5 - 7.5) / 3, abs=1e-3)
    assert W._position_runs("UTIL") == 0.0
    fut, pre = W.report_grades("Scouting Grades (present/future): Fastball: 5/7 | "
                               "Curve: 4/6 | Control: 3/5 | Overall: 4/6")
    assert fut == {"fb": 70.0, "cb": 60.0, "cmd": 50.0}
    assert pre == {"fb": 50.0, "cb": 40.0, "cmd": 30.0}
    assert W.report_grades("no grades here") == ({}, {})


# ---------------------------------------------------------------------------
# 3. the lab column builder and the guards
# ---------------------------------------------------------------------------

def test_the_lab_column_reads_each_row_at_its_own_asof(index):
    frames = {"pit": {2017: ([{"player_key": "a", "asof_date": "2017-03-01"}], [{}]),
                      2016: ([{"player_key": "a", "asof_date": "2016-03-01"}], [{}])}}
    vals = W.screen_column("fb", "pit", frames, index=index)
    assert vals == {(2016, "a"): 55.0, (2017, "a"): 62.5}
    with pytest.raises(ValueError):
        W.screen_column("fb", "hit", frames, index=index)
    bad = {"pit": {2020: ([{"player_key": "a", "asof_date": "2017-03-01"}], [{}])}}
    with pytest.raises(F.ReservedFrameError):
        W.screen_column("fb", "pit", bad, index=index)


def test_the_guards_trip_on_reserved_frames():
    with pytest.raises(F.ReservedFrameError):
        W.guards((2017, 2020), [2017])
    with pytest.raises(F.ReservedFrameError):
        W.guards((2017, 2018, 2019), [2023, 2025])
    g = W.guards((2017, 2018, 2019), list(range(2017, 2024)))
    assert g["reserved_vm_pins"] == [] and g["snapshot_cap"] == W.SNAPSHOT_CAP


# ---------------------------------------------------------------------------
# 4. registration and the source scan
# ---------------------------------------------------------------------------

def test_the_arms_are_registered_in_the_lab():
    names = [a["name"] for a in W.ARMS]
    assert len(names) == len(set(names)) == 13
    lab = LAB.w2_candidates()
    assert [a["name"] for a in lab] == [a["name"] for a in W.ARMS if a["kind"] == "column"]
    assert len(LAB.w2_candidates(kinds=None)) == len(W.ARMS)
    assert "efv_w2_scout" in LAB.W2_MODULES
    for a in W.ARMS:
        assert a["head"] == "skill" and a["side"] in F.SIDES
        for c in a["components"]:
            assert W.COMPONENTS[c]["side"] == a["side"]
            assert W.column_key(c).startswith(H.V2_SCREEN_PREFIX)
        if a["kind"] == "column":
            assert a["column"]["arg"] == a["components"][0]
    # wave 1 is untouched
    assert len(LAB.CANDIDATES) == 7


_BANNED = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv", "fv_band",
           "fv_bin", "by_consensus", "per_fv", "per_consensus")


def test_no_fv_grouping_and_no_dash_in_the_module():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    fv_group = re.compile(r"(by|per|group)_?(fv|consensus|grade)")
    for node in ast.walk(tree):
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.arg):
            name = node.arg
        if name:
            low = name.lower()
            assert not any(t in low for t in _BANNED), name
            assert not fv_group.search(low), name
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            assert not any(t in node.value.lower() for t in _BANNED), node.value
    for path in (SRC, Path(__file__)):
        text = path.read_text(encoding="utf-8")
        assert chr(0x2014) not in text and chr(0x2013) not in text


def test_the_module_imports_no_served_exporter():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    assert not mods & {"efv_export", "efv_v2_serve", "efv_score", "build_site",
                       "proj_export", "export_trade_values", "run_monthly", "backtest"}


# ---------------------------------------------------------------------------
# 5. the refit on both frames, and the progress rows
# ---------------------------------------------------------------------------

def _rows(side="pit", years=range(2013, 2020), n=90, seed=21, plant=0.6):
    rng = np.random.default_rng(seed)
    out, i = [], 0
    for yr in years:
        for _ in range(n):
            fv = float(rng.normal(45, 5))
            kr = float(rng.normal(0, 0.05))
            x = float(rng.normal(50, 10))
            t = 0.1 * (fv - 45) + 20.0 * kr + plant * (x - 50) / 10 + float(rng.normal(0, 1))
            feats = {"milb_unavailable": 0.0, "milb_missing": 0.0, "obp_rel": 0.0,
                     "k_rel": kr, "peak_k_rel": kr, "level_rank": float(rng.integers(0, 6)),
                     "age_rel_level": float(rng.normal(0, 1)), "tool_hit": 50.0,
                     "tool_speed": 48.0, "is_college": 0.0, "is_ifa": 0.0,
                     "pick_missing": 1.0}
            extra = {"bmi": float(rng.normal(25, 2)), "pl_rev": None,
                     "on_40man": float(rng.random() < 0.2), "nov_add": 0.0}
            out.append({"player_key": f"{side}{i}", "decision_year": yr, "fv": fv,
                        "target": t, "reached": float(t > 0.5), "weight": 1.0,
                        "feats": feats, "extra": extra, "v2": H.v2_row(feats, extra),
                        "frame": "lv", "ids_outcome_blind": True, "x": x})
            i += 1
    return out


@pytest.fixture(scope="module")
def lvframe():
    rows = _rows()
    fr = LAB.Frame.from_rows({"pit": rows}, weights=WEIGHTS, w_star=1.5,
                             absent_ok={"pit": False})
    fr.planted = {(r["decision_year"], r["player_key"]): r["x"] for r in rows}
    rng = np.random.default_rng(5)
    fr.noise = {(r["decision_year"], r["player_key"]): float(rng.normal()) for r in rows}
    return fr


def test_a_refused_column_is_the_base_and_forced_moves_it(lvframe):
    base = {(V, k): v for V in lvframe.folds
            for k, v in lvframe.base("pit", V)["order"].items()}
    key = W.column_key("fb")
    order, folds = W.lv_orders(lvframe, "pit", {key: lvframe.noise})
    refused = [k for k, f in folds.items() if not f["any_admitted"]]
    for fk in refused:
        V = int(fk.split("|")[1])
        assert all(order[(V, k)] == base[(V, k)] for (VV, k) in base if VV == V)
    forced, ffolds = W.lv_orders(lvframe, "pit", {key: lvframe.noise}, force=True)
    assert all(f.get("forced") for f in ffolds.values())
    assert any(forced[s] != base[s] for s in base)
    planted, pfolds = W.lv_orders(lvframe, "pit", {key: lvframe.planted})
    assert all(f["admitted"][key] for f in pfolds.values())
    cols = LAB._columns(lvframe, ("pit",), planted)
    assert W._within_point(cols) > 0
    # columns are detached afterwards
    assert all(key not in r["v2"] for r in lvframe.rows_of("pit"))


def _vm(rows, yr=2019, plantkey=None):
    tr = [dict(r, frame="vm") for r in rows if r["decision_year"] < yr]
    te = [dict(r, frame="vm") for r in rows if r["decision_year"] == yr]
    m = H.fit_v2(tr, "pit", frame="vm", weights=WEIGHTS)
    base = {p["player_key"]: float(p["order_idx"]) for p in H.predict_v2(m, te)}
    scored = [{"key": r["player_key"], "group": f"pit|{yr}", "cons": r["fv"],
               "w3": r["target"], "contributor": r["target"] > 1.5, "grades": {}}
              for r in te]
    return W.VmFrame({("pit", yr): {"train": tr, "test": te, "scored": scored,
                                    "base": base, "base_model": m}}, [yr], WEIGHTS, {})


def test_the_vm_refit_reads_its_own_slots():
    rows = _rows(seed=31)
    vm = _vm(rows)
    planted = {(r["decision_year"], r["player_key"], "test" if r["decision_year"] == 2019
                else "train"): r["x"] for r in rows}
    key = W.column_key("cmd")
    order, folds = W.vm_orders(vm, "pit", {key: planted})
    assert folds["pit|2019"]["admitted"][key]
    cols = W._vm_cols(vm, "pit", order)
    assert W._within_point(cols) > 0
    # an empty column is refused and reproduces the base exactly
    order0, folds0 = W.vm_orders(vm, "pit", {key: {}})
    assert not folds0["pit|2019"]["any_admitted"]
    blk = vm.folds[("pit", 2019)]
    assert all(order0[(2019, c["key"])] == blk["base"][c["key"]] for c in blk["scored"])


def test_the_progress_rows_are_development_rows_with_no_pass(lvframe, tmp_path):
    key = W.column_key("fb")
    order, folds = W.lv_orders(lvframe, "pit", {key: lvframe.planted})
    cols = LAB._columns(lvframe, ("pit",), order)
    blk = W.frame_block(cols, B=B_FAST, frame_id="lv_dev", window=[2017, 2019],
                        folds=folds, n_by_side={"pit": len(cols[0])})
    arm = {"name": "w2s_fb_pit", "side": "pit", "head": "skill", "kind": "column",
           "components": ["fb"], "model_id": f"{W.MODEL_PREFIX}:w2s_fb_pit:pit",
           "frames": {"lv_dev": blk, "vm_dev": blk},
           "twin": {"lv_dev": {"within": 0.0}, "vm_dev": {"within": 0.0}}}
    doc = {"generated_at": "2026-10-08T00:00:00Z", "label": {"id": "fixture"},
           "code": {"commit": "x"}, "arms": [arm]}
    art = tmp_path / "efv_w2_scout.json"
    art.write_text(json.dumps(doc), encoding="utf-8")
    res = W.update_progress(doc, artifact=art, data_dir=tmp_path,
                            out_path=tmp_path / "efv_progress.json",
                            ledger_path=tmp_path / "ledger.jsonl")
    assert len(res["appended"]) == 2
    rows = json.loads((tmp_path / "efv_progress.json").read_text(encoding="utf-8"))["rows"]
    assert {r["frame"] for r in rows} == {"lv_dev", "vm_dev"}
    for r in rows:
        assert r["role"] == "development" and r["resolvable"] is None
        assert r["verdict"] != "PASS" and r["verdict"].startswith("development only")
        assert r["screening"]["exploratory"] is False and r["screening"]["wave"] == 2
        assert r["model_id"].split(":")[2] == "w2s_fb_pit"
        assert r["model_id"].split(":")[3] == "pit"
        assert r["deltas"]["vs_efv_v2_base"]["spearman"]["delta"] == \
            blk["deltas"]["candidate_vs_efv_v2_base"]["spearman"]["delta"]
    # a second identical write appends nothing
    res2 = W.update_progress(doc, artifact=art, data_dir=tmp_path,
                             out_path=tmp_path / "efv_progress.json",
                             ledger_path=tmp_path / "ledger.jsonl")
    assert res2["appended"] == []
    assert P.SCREEN_RATERS and W.FRAMES == ("lv_dev", "vm_dev")

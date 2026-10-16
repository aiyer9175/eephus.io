# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EFV3_D2 pins for the scoreboard matrix producer (SP/efv3/LANE_D.md 3.9; the
registration docs/efv-v2/EFV_V2_GATE.md s8.1 to s8.4).

 1. the overall vm2 cell copies head_to_head_verdict.delta and the consensus Spearman
    ci95 of head_to_head_vs_sources byte for byte (and the parity receipt reproduces);
 2. the cells of each dimension partition the frame n (a hitter-only dimension
    partitions the hitter rows);
 3. `families` precedes `cells` and Family S equals the set at or above the floor;
 4. a cell under the floor carries no interval;
 5. the vocabulary is closed and every reading follows its rule from the cell's own
    numbers; the summary counts are a recount of the cells;
 6. ReservedFrameError on a reserved vintage or debut year without the gate sha;
 7. no key the ledger's _FV_CELL regex rejects;
 8. no em-dash and no copy_lint BAN_RE hit in the module or the artifact;
 9. compare-before-write leaves an unchanged artifact untouched;
10. a fixture with None and NaN in every printed cell renders without raising.

Fixture frames are synthetic (240 rows, B 60) so the suite never scores a real
row; the artifact tests read data/efv_matrix_eval.json as written by the producer.
"""
from __future__ import annotations

import inspect
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pytest

import efv_strata as ST
import efv_vintage_frame as F
import source_backtest as SB
import tools.efv_matrix as M

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))
import copy_lint  # noqa: E402

ART = ROOT / "data" / "efv_matrix_eval.json"
SBJ = ROOT / "data" / "source_backtest.json"
CONS = SB.CONSENSUS_KEY
_FV_CELL = re.compile(r"(?:^|[^0-9])(?:35|40|45|50|55|60|65|70)(?:\+|plus)?(?:$|[^0-9])|tier|fv_cell|fv_bucket",
                      re.IGNORECASE)
NAN = float("nan")


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _fixture(n_per=40, vintages=(2017, 2018, 2019), seed=1):
    rng = np.random.default_rng(seed)
    rows, k = [], 0
    for side in ("hit", "pit"):
        for V in vintages:
            for j in range(n_per):
                k += 1
                war = max(0.0, float(rng.normal(2.0, 3.0)))
                cons = float(rng.choice([40, 45, 50, 55, 60]))
                efv = cons + 0.8 * war + float(rng.normal(0, 3))
                fg = cons + float(rng.normal(0, 4))
                mp = cons + float(rng.normal(0, 4))
                grades = {"efv": efv, CONS: cons, "fangraphs": fg, "mlb_pipeline": mp}
                if j % 2:
                    grades["baseballamerica"] = cons + 1.0
                cells = {"side": side, "level_at_list": ["AA", "AAA", "A+"][j % 3],
                         "age_band": ["21-22", "23-24", ">=25"][j % 3], "list_year": str(V),
                         "archetype": (("hs_bat" if side == "hit" else "college_arm") if j % 2
                                       else ("unknown_bat" if side == "hit" else "intl_arm")),
                         "source_disagreement": "gap_10_plus" if abs(fg - mp) >= 10 else "gap_under_10"}
                if side == "hit":
                    cells["position_family"] = "IF" if j % 3 else "OF"
                rows.append({"key": f"p{k}", "group": f"{side}|{V}", "side": side, "vintage": V,
                             "debut_year": V, "war": war, "debuted": True, "grades": grades,
                             "cells": cells,
                             "l6": ({"resolved": war, "censored": war * 1.1,
                                     "censored_flag": j % 4 == 0, "weight": 1.0} if j % 5 else None),
                             "r3": int(war > 0.5)})
    return rows


LV_LEGS = [("auc_w1", lambda r: r["war"] >= 1.0), ("auc_wstar", lambda r: r["war"] >= 1.19),
           ("auc_r3", lambda r: r.get("r3") == 1)]


@pytest.fixture(scope="module")
def vm_block():
    rows = _fixture()
    return M.score_frame("vm2", rows, B=60), rows


@pytest.fixture(scope="module")
def lv_block():
    rows = [dict(r, debut_year=None) for r in _fixture()]
    return M.score_frame("lv_dev", rows, B=60, auc_legs=LV_LEGS), rows


@pytest.fixture(scope="module")
def bust_block():
    rows = _fixture()
    return M.score_frame("bust_inclusive", rows, B=60, statistics=("auc",)), rows


@pytest.fixture(scope="module")
def artifact():
    if not ART.exists():
        pytest.skip("data/efv_matrix_eval.json not built")
    return json.loads(ART.read_text(encoding="utf-8"))


def _scored_frames(artifact):
    return [(fid, f) for fid, f in artifact["frames"].items()
            if fid not in M.RESERVED_FRAMES]


# ---------------------------------------------------------------------------
# 1. the overall vm2 cell is COPIED from the served verdict
# ---------------------------------------------------------------------------

def test_overall_vm2_cell_copies_the_served_verdict_byte_for_byte(artifact):
    if not SBJ.exists():
        pytest.skip("data/source_backtest.json not built")
    sb = json.loads(SBJ.read_text(encoding="utf-8"))
    vm = artifact["frames"]["vm2"]
    if (vm.get("source") or {}).get("generated_at") != sb.get("generated_at"):
        pytest.skip("the matrix artifact and the served backtest are from different runs "
                    "(EFV3_D3 wires them into the same nightly block)")
    hv = sb["accuracy"]["head_to_head_verdict"]
    vs = sb["accuracy"]["head_to_head_vs_sources"]["sources"][CONS]["spearman"]
    ocb = vm["cells"]["overall"]["all"]["comparators"][CONS]
    hl = ocb["headline"]
    assert json.dumps(hl["delta"]) == json.dumps(hv["delta"])
    assert json.dumps(hl["n"]) == json.dumps(hv["n"])
    assert json.dumps(hl["ci95"]) == json.dumps(vs["ci95"])
    assert json.dumps(hl["verdict_ci95"]) == json.dumps(hv["ci95"])
    assert json.dumps(hl["mde95"]) == json.dumps(hv["mde95"])
    assert json.dumps(hl["sd"]) == json.dumps(vs["sd"])
    assert ocb["family"] == "P"
    P = vm["families"]["P"]
    assert "copied" in P["source"] and json.dumps(P["copied"]["delta"]) == json.dumps(hv["delta"])
    assert P["copied"]["n"] == hv["n"]
    par = vm["parity"]
    assert par["n_read"] == hv["n"] and par["reproduces"] is True, par


def test_family_i_is_copied_from_the_fp3_block(artifact):
    if not SBJ.exists():
        pytest.skip("data/source_backtest.json not built")
    sb = json.loads(SBJ.read_text(encoding="utf-8"))
    vm = artifact["frames"]["vm2"]
    if (vm.get("source") or {}).get("generated_at") != sb.get("generated_at"):
        pytest.skip("different runs")
    vs = sb["accuracy"]["head_to_head_vs_sources"]
    I = vm["families"]["I"]
    assert I["k"] == vs["holm"]["k"] == 6
    assert I["copied"]["family"] == vs["holm"]["family"]
    for r_, src in vs["sources"].items():
        for m_, leg in src.items():
            if isinstance(leg, dict):
                assert I["copied"]["sources"][r_][m_]["delta"] == leg.get("delta"), (r_, m_)


# ---------------------------------------------------------------------------
# 2. partitions
# ---------------------------------------------------------------------------

def _assert_partition(frame_block):
    n = frame_block["n"]
    for dim, by in frame_block["cells"].items():
        if dim == "overall":
            assert list(by) == ["all"] and by["all"]["n"] == n
            continue
        total = sum(b["n"] for b in by.values())
        side = ST.DIMENSION_SIDE.get(dim)
        expected = n if side is None else frame_block["n_by_side"][side]
        assert total == expected, (dim, total, expected)
        assert sum(b["n_hit"] + b["n_pit"] for b in by.values()) == total


def test_cells_of_each_dimension_partition_the_fixture_frames(vm_block, lv_block, bust_block):
    for blk, _rows in (vm_block, lv_block, bust_block):
        _assert_partition(blk)
        assert set(blk["cells"]) == {"overall", *ST.DIMENSIONS}


def test_cells_of_each_dimension_partition_the_artifact_frames(artifact):
    for fid, f in _scored_frames(artifact):
        _assert_partition(f)
        assert f["n"] == sum(f["n_by_side"].values()), fid


# ---------------------------------------------------------------------------
# 3. families first; Family S is the set at or above the floor
# ---------------------------------------------------------------------------

def _family_s_expected(frame_block):
    n = frame_block["n"]
    out = set()
    for dim, by in frame_block["cells"].items():
        if dim == "overall":
            continue
        for cell, blk in by.items():
            if not blk["declared"] or blk["n"] >= n:
                continue
            cb = blk["comparators"].get(CONS) or {}
            if cb.get("n", 0) >= M.FLOOR_ROWS:
                out.add((dim, cell))
    return out


def _check_families(frame_block, has_spearman=True):
    keys = list(frame_block)
    assert keys.index("families") < keys.index("cells") < keys.index("summary")
    fam = frame_block["families"]
    assert fam["written_before_cells"] is True
    assert set(fam) >= {"P", "I", "S"}
    S = fam["S"]
    got = {(c["dimension"], c["cell"]) for c in S["cells"]}
    if has_spearman:
        assert got == _family_s_expected(frame_block)
        assert S["k"] == len(S["cells"]) == frame_block["summary"]["k_family_s"]
        assert S["expected_false_flags_by_construction"] == round(M.ALPHA * S["k"], 2)
        for c in S["cells"]:
            assert c["n"] >= M.FLOOR_ROWS == c["floor_rows"]
        in_s = {(d, c) for d, by in frame_block["cells"].items() for c, b in by.items()
                if b.get("in_family_s")}
        assert in_s == got
    else:
        assert S["k"] == 0 and S["cells"] == [] and got == set()
    assert S["alpha"] == M.ALPHA == 0.05
    assert S["procedure"] == "source_backtest._holm_family"


def test_families_precede_cells_on_the_fixture_frames(vm_block, lv_block, bust_block):
    _check_families(vm_block[0])
    _check_families(lv_block[0])
    _check_families(bust_block[0], has_spearman=False)
    # D5-b: the two side cells are members of Family S
    assert {("side", "hit"), ("side", "pit")} <= {(c["dimension"], c["cell"])
                                                   for c in vm_block[0]["families"]["S"]["cells"]}


def test_families_precede_cells_on_the_artifact_frames(artifact):
    for fid, f in _scored_frames(artifact):
        _check_families(f, has_spearman="spearman_within" in f["statistics"])
    for fid in M.RESERVED_FRAMES:
        f = artifact["frames"][fid]
        assert f["reserved"] is True
        keys = list(f)
        assert keys.index("families") < keys.index("cells")
        if not f["cells"]:
            assert f["reading"] == "RESERVED_PENDING"


def test_the_primary_statistic_is_declared_per_cell(vm_block):
    blk, _ = vm_block
    # 40 hitters per vintage: IF (about 27 per group) keeps 3 groups, OF (about 13) keeps none
    assert blk["cells"]["position_family"]["IF"]["primary_statistic"] == "within"
    assert blk["cells"]["position_family"]["OF"]["primary_statistic"].startswith(
        "pooled (within degenerate:")
    for dim, by in blk["cells"].items():
        for cell, b in by.items():
            kg = b["groups_kept"]
            assert (b["primary_statistic"] == "within") == (len(kg) >= 2), (dim, cell, kg)
            for comp, cb in b["comparators"].items():
                if cb.get("statistics"):
                    assert "spearman_pooled" in cb["statistics"], "the pooled statistic is always beside"
                    assert cb["statistics"]["spearman_pooled"]["map"].startswith("identical output map")


# ---------------------------------------------------------------------------
# 4. under the floor: no interval
# ---------------------------------------------------------------------------

def _check_floor(frame_block):
    for dim, by in frame_block["cells"].items():
        for cell, blk in by.items():
            for comp, cb in blk["comparators"].items():
                if not blk["scored"] or cb["n"] < M.FLOOR_ROWS:
                    assert cb["statistics"] == {}, (dim, cell, comp)
                    assert cb["reading"] in ("UNPOWERED", "NOT_SCORED"), (dim, cell, comp)
                    assert "ci95" not in json.dumps(cb), (dim, cell, comp)
                else:
                    for key, leg in cb["statistics"].items():
                        assert leg["floor_rows"] == M.FLOOR_ROWS
                        if leg.get("status") == "derived":
                            assert isinstance(leg["ci95"], list) and len(leg["ci95"]) == 2
                            assert leg["estimator"] == "E_cond"
                            assert leg["seed"] == M.SEED == 20260906


def test_a_cell_under_the_floor_carries_no_interval(vm_block, lv_block, bust_block):
    for blk, _rows in (vm_block, lv_block, bust_block):
        _check_floor(blk)
    small = M.score_frame("vm2", _fixture(n_per=6), B=60)
    for dim, by in small["cells"].items():
        for cell, b in by.items():
            if b["n"] < M.FLOOR_ROWS:
                assert not b["scored"]
                for cb in b["comparators"].values():
                    assert cb["statistics"] == {}


def test_a_cell_under_the_floor_carries_no_interval_in_the_artifact(artifact):
    for fid, f in _scored_frames(artifact):
        _check_floor(f)
        assert f["summary"]["under_floor"] == sum(
            1 for d, by in f["cells"].items() if d != "overall"
            for b in by.values() if b["declared"] and not b["scored"])


# ---------------------------------------------------------------------------
# 5. the closed vocabulary, each reading from its rule
# ---------------------------------------------------------------------------

def _expected_reading(frame_block, cb, blk):
    dev = frame_block["development"]
    if cb["n"] == 0:
        return "NOT_SCORED"
    if not blk["scored"] or cb["n"] < M.FLOOR_ROWS:
        return "UNPOWERED"
    if "headline" in cb:
        return M.frame_reading(M.family_reading(cb["headline"], bool(frame_block["holm"]["P"]["survives"])), dev)
    pk = (cb.get("primary") or {}).get("leg")
    if pk is None:
        return "NOT_SCORED"
    leg = cb["statistics"][pk]
    if cb.get("family") in ("S", "P") and leg.get("holm"):
        return M.frame_reading(M.family_reading(leg, bool(leg["holm"]["reject_holm"])), dev)
    return M.frame_reading(M.interval_reading(leg), dev)


def _check_vocabulary(frame_block):
    counts = {w.lower(): 0 for w in M.READINGS}
    for dim, by in frame_block["cells"].items():
        for cell, blk in by.items():
            for comp, cb in blk["comparators"].items():
                assert cb["reading"] in M.READINGS, (dim, cell, comp, cb["reading"])
                assert cb["reading"] == _expected_reading(frame_block, cb, blk), (dim, cell, comp)
                if frame_block["development"] and cb["reading"] == "DEVELOPMENT":
                    assert cb["reading_if_claim_frame"] in ("AHEAD", "BEHIND") + M.INTERVAL_WORDS
                for key, leg in (cb.get("statistics") or {}).items():
                    if key == "mae":
                        assert "reading" not in leg, "MAE carries no verdict weight"
                        continue
                    assert leg["reading"] in M.READINGS
                    if not leg.get("holm"):
                        assert leg["reading"] == M.interval_reading(leg), (dim, cell, comp, key)
                        assert leg["note"] == M.UNCORRECTED_NOTE
                if dim != "overall" and blk["declared"] and comp == CONS and (
                        blk.get("in_family_s") or ("spearman_within" not in frame_block["statistics"]
                                                   and blk["scored"])):
                    counts[cb["reading"].lower()] += 1
    assert frame_block["summary"]["counts"] == counts
    line = frame_block["summary"]["line"]
    assert str(frame_block["summary"]["expected_false_flags_by_construction"]) in line \
        or frame_block["summary"]["k_family_s"] == 0
    # ties are ties: the two words are counted apart and never summed into a lead
    assert "equivalent" in counts and "unresolved" in counts
    assert {"AHEAD", "BEHIND"} <= set(M.READINGS) and M.PRINTED["EQUIVALENT"] != M.PRINTED["UNRESOLVED"]


def test_vocabulary_is_closed_and_every_reading_follows_its_rule(vm_block, lv_block, bust_block):
    for blk, _rows in (vm_block, lv_block, bust_block):
        _check_vocabulary(blk)
    assert all(w in M.PRINTED for w in M.READINGS)
    assert set(M.READINGS) == {"AHEAD", "BEHIND", "EQUIVALENT", "UNRESOLVED", "FLAGGED_UNCORRECTED",
                               "UNPOWERED", "NOT_SCORED", "DEVELOPMENT", "RESERVED_PENDING"}


def test_vocabulary_holds_on_the_artifact(artifact):
    for fid, f in _scored_frames(artifact):
        _check_vocabulary(f)
    lv = artifact["frames"]["lv_dev"]
    assert lv["development"] is True
    for dim, by in lv["cells"].items():
        for cell, blk in by.items():
            for cb in blk["comparators"].values():
                assert cb["reading"] not in ("AHEAD", "BEHIND", "EQUIVALENT", "UNRESOLVED",
                                             "FLAGGED_UNCORRECTED"), "a development frame prints no word"


def test_reading_rules_on_hand_legs():
    base = {"n": 100, "status": "derived", "delta": 0.001, "ci95": [-0.01, 0.012], "sd": 0.006,
            "mde95": 0.0099, "clears_own_floor": False}
    assert M.interval_reading(base) == "EQUIVALENT"
    assert M.interval_reading({**base, "ci95": [-0.03, 0.012]}) == "UNRESOLVED"
    assert M.interval_reading({**base, "delta": 0.03, "ci95": [0.01, 0.05], "clears_own_floor": True}) \
        == "FLAGGED_UNCORRECTED"
    assert M.interval_reading({**base, "mde95": 0.05, "sd": 0.03}) == "UNPOWERED"
    assert M.interval_reading({**base, "status": "not derived: x"}) == "UNPOWERED"
    assert M.interval_reading({**base, "unpowered_by_positives": True}) == "UNPOWERED"
    assert M.interval_reading({**base, "n": 0}) == "NOT_SCORED"
    assert M.interval_reading(None) == "NOT_SCORED"
    assert M.family_reading({**base, "delta": 0.03}, True) == "AHEAD"
    assert M.family_reading({**base, "delta": -0.03}, True) == "BEHIND"
    assert M.family_reading(base, False) == "EQUIVALENT"
    assert M.frame_reading("AHEAD", True) == "DEVELOPMENT"
    assert M.frame_reading("UNPOWERED", True) == "UNPOWERED"
    assert M.frame_reading("NOT_SCORED", True) == "NOT_SCORED"
    assert M.frame_reading("EQUIVALENT", False) == "EQUIVALENT"


# ---------------------------------------------------------------------------
# 6. reserved rows refuse without the gate sha
# ---------------------------------------------------------------------------

def test_reserved_rows_raise_without_the_gate_sha():
    row = _fixture(n_per=1)[0]
    for v in sorted(F.RESERVED_LV):
        with pytest.raises(F.ReservedFrameError):
            M.guard_rows("lv_dev", [dict(row, vintage=v, debut_year=None)])
        with pytest.raises(F.ReservedFrameError):
            M.guard_rows("lv_res", [dict(row, vintage=v, debut_year=None)], gate_sha="deadbeef")
    with pytest.raises(F.ReservedFrameError):
        M.guard_rows("vm2", [dict(row, vintage=F.R_VM_FIRST_DEBUT_YEAR,
                                  debut_year=F.R_VM_FIRST_DEBUT_YEAR)])
    with pytest.raises(F.ReservedFrameError):
        M.score_frame("vm_pros", [dict(row, vintage=2026, debut_year=2026)], B=60)
    with pytest.raises(F.ReservedFrameError):
        M.main(["--frames", "lv_res", "--no-write"])
    # development vintages pass the guard and the receipt names the bans
    g = M.guard_rows("lv_dev", [dict(row, vintage=2017, debut_year=None)])
    assert g["reserved_lv"] == sorted(F.RESERVED_LV) and g["r_vm_first_debut_year"] == F.R_VM_FIRST_DEBUT_YEAR


def test_the_tool_scores_no_reserved_frame_and_copies_them_from_the_gate_file():
    assert set(M.RESERVED_FRAMES) == {"lv_res", "vm_pros"}
    default_frames = inspect.signature(M.run).parameters["frames"].default
    assert set(default_frames) == {"vm2", "lv_dev", "bust_inclusive"}
    assert not (set(default_frames) & set(M.RESERVED_FRAMES))
    blk = M.reserved_frame("lv_res", None)
    assert blk["reserved"] is True and blk["reading"] == "RESERVED_PENDING" and blk["cells"] == {}
    assert blk["list_vintages"] == sorted(F.RESERVED_LV)
    assert blk["pre_registered_cells"]["list_year"] == [str(v) for v in sorted(F.RESERVED_LV)]
    copied = M.reserved_frame("lv_res", {"strata": {"lv_res": {"side": {"hit": {"n": 1}}}}})
    assert copied["cells"] == {"side": {"hit": {"n": 1}}} and "reading" not in copied


# ---------------------------------------------------------------------------
# 7. no FV cell key anywhere
# ---------------------------------------------------------------------------

def _keys(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield path + "/" + str(k)
            yield from _keys(v, path + "/" + str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _keys(v, f"{path}[{i}]")


def test_no_fv_cell_key_in_the_fixture_frames(vm_block, lv_block, bust_block):
    for blk, _rows in (vm_block, lv_block, bust_block):
        bad = [k for k in _keys(blk) if _FV_CELL.search(k.rsplit("/", 1)[-1])]
        assert bad == [], bad[:10]
    for dim in ST.DIMENSIONS:
        assert not _FV_CELL.search(dim)


def test_no_fv_cell_key_in_the_artifact(artifact):
    bad = [k for k in _keys(artifact) if _FV_CELL.search(k.rsplit("/", 1)[-1])]
    assert bad == [], bad[:10]
    assert artifact["design"]["dimensions"] == list(ST.DIMENSIONS)
    assert artifact["design"]["banned_dimensions"] == list(ST.BANNED_DIMENSIONS)


# ---------------------------------------------------------------------------
# 8. copy
# ---------------------------------------------------------------------------

def _strings(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)
    elif isinstance(o, str):
        yield o


def test_no_emdash_and_no_banned_word_in_the_module_and_the_artifact(artifact):
    src = (ROOT / "tools" / "efv_matrix.py").read_text(encoding="utf-8")
    assert "—" not in src and "–" not in src
    hits = [m.group(0) for m in (copy_lint.BAN_RE.search(ln) for ln in src.splitlines()) if m]
    assert hits == [], hits
    for s in _strings(artifact):
        assert "—" not in s and "–" not in s, s[:80]
        assert not copy_lint.BAN_RE.search(s), s[:80]
    for s in list(M.PRINTED.values()) + list(M.STAT_LABELS.values()) + [M.UNCORRECTED_NOTE]:
        assert not copy_lint.BAN_RE.search(s), s


# ---------------------------------------------------------------------------
# 9. compare-before-write
# ---------------------------------------------------------------------------

def test_compare_before_write_leaves_an_unchanged_artifact_untouched(tmp_path):
    out, hist = tmp_path / "m.json", tmp_path / "h.jsonl"
    doc = {"generated_at": "2026-10-03T00:00:00Z", "elapsed_s": 1.0, "label": {"provider": "x"},
           "code": {"commit": "abc"}, "frames": {"vm2": {"n": 3, "summary": {"k_family_s": 1}}}}
    r1 = M.write_artifact(doc, out, hist)
    assert r1["written"] is True
    b1 = out.read_bytes()
    r2 = M.write_artifact({**doc, "generated_at": "2026-10-04T00:00:00Z", "elapsed_s": 9.0}, out, hist)
    assert r2["written"] is False and "compare-before-write" in r2["reason"]
    assert out.read_bytes() == b1
    assert len(hist.read_text(encoding="utf-8").splitlines()) == 1
    r3 = M.write_artifact({**doc, "frames": {"vm2": {"n": 4, "summary": {"k_family_s": 1}}}}, out, hist)
    assert r3["written"] is True
    lines = hist.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and json.loads(lines[1])["frames"]["vm2"]["n"] == 4
    assert M._strip(doc) == M._strip({**doc, "generated_at": "z", "elapsed_s": 0})


def test_paths_resolve_at_call_time():
    sig = inspect.signature(M.write_artifact)
    assert sig.parameters["out_path"].default is None
    assert sig.parameters["history_path"].default is None
    assert inspect.signature(M.run).parameters["out_path"].default is None
    assert M.OUT_PATH.name == "efv_matrix_eval.json" and M.HISTORY_PATH.name == "history.jsonl"


def test_run_source_backtest_gained_an_optional_rows_return_only():
    p = inspect.signature(SB.run_source_backtest).parameters
    assert "return_rows" in p and p["return_rows"].default is False
    src = inspect.getsource(SB.run_source_backtest)
    assert "if return_rows:" in src and src.rstrip().endswith("return result")


# ---------------------------------------------------------------------------
# 10. None and NaN everywhere
# ---------------------------------------------------------------------------

def test_a_fixture_with_none_and_nan_in_every_cell_renders_without_raising(vm_block):
    blk, rows = vm_block
    hollow = json.loads(json.dumps(M._clean(blk)))
    for dim, by in hollow["cells"].items():
        for cell, b in by.items():
            for cb in b["comparators"].values():
                for leg in (cb.get("statistics") or {}).values():
                    for k in ("a", "b", "delta", "sd", "mde95", "p_one_sided", "p_gt_0"):
                        leg[k] = NAN if k in ("delta", "sd") else None
                    leg["ci95"] = [None, NAN]
                    assert M.interval_reading(leg) in M.READINGS
                    assert M.family_reading(leg, True) in M.READINGS
                cb["reading"] = None
    hollow["summary"]["line"] = None
    doc = {"generated_at": None, "label": {"provider": None, "resolved_through": None},
           "frames": {"vm2": hollow, "lv_dev": None, "lv_res": M.reserved_frame("lv_res"), "x": {}}}
    text = M.summary_text(doc)
    assert "eFV SCOREBOARD MATRIX" in text
    json.dumps(M._clean(doc), allow_nan=False)
    assert M.summary_text(None).startswith("===")
    # NaN and None grades and outcomes inside the producer itself
    rows2 = [dict(r, grades=dict(r["grades"])) for r in rows]
    for r in rows2[:6]:
        r["grades"]["efv"] = NAN
    for r in rows2[6:9]:
        r["grades"][CONS] = None
    for r in rows2[9:12]:
        r["war"] = NAN
    blk2 = M.score_frame("vm2", rows2, B=40)
    json.dumps(M._clean(blk2), allow_nan=False)
    assert blk2["n"] == len(rows2)


def test_an_exact_tie_is_marked_as_identical_ordering_not_a_measured_one():
    """On vm2 the served V2 orders its earliest decision years exactly as consensus
    does (2026-10-03 receipt: 7 of 14 (side, year) groups rank-identical), so a cell
    whose kept groups are those years reads a zero-width interval. The word stays
    EQUIVALENT (the CI95 sits inside the margin) and the leg says the tie is exact."""
    rows = _fixture()
    for r in rows:
        if r["vintage"] == 2017:
            r["grades"]["efv"] = r["grades"][CONS]
    blk = M.score_frame("vm2", rows, B=60)
    cb = blk["cells"]["list_year"]["2017"]["comparators"][CONS]
    leg = cb["statistics"][cb["primary"]["leg"]]
    assert leg["delta"] == 0 and leg["sd"] == 0 and leg["identical_ordering"] is True
    assert "exact tie" in leg["identical_note"]
    assert cb["reading"] == "EQUIVALENT"
    other = blk["cells"]["list_year"]["2019"]["comparators"][CONS]
    assert "identical_ordering" not in other["statistics"][other["primary"]["leg"]]
    agree = M._rank_agreement(rows)
    assert agree["hit|2017"]["rank_identical"] is True and agree["hit|2017"]["spearman_efv_vs_consensus"] == 1.0
    assert agree["pit|2019"]["rank_identical"] is False
    assert set(agree) == {f"{s}|{v}" for s in ("hit", "pit") for v in (2017, 2018, 2019)}


def test_artifact_receipts_carry_the_rank_agreement_by_group(artifact):
    for fid in ("vm2", "lv_dev"):
        agree = artifact["frames"][fid]["receipts"]["efv_consensus_rank_agreement_by_group"]
        assert set(agree) == set(artifact["frames"][fid]["groups"])
        for g, a in agree.items():
            assert a["n"] > 0 and a["rank_identical"] is (a["spearman_efv_vs_consensus"] == 1.0), g


def test_clean_turns_nan_and_numpy_scalars_into_json():
    out = M._clean({"a": NAN, "b": [float("inf"), np.float64(1.5), np.int64(2), np.bool_(True)],
                    "c": {"d": None}})
    assert out == {"a": None, "b": [None, 1.5, 2, True], "c": {"d": None}}
    json.dumps(out, allow_nan=False)
    assert M._rnd(NAN, 3) is None and M._rnd(1.23456, 3) == 1.235


# ---------------------------------------------------------------------------
# the row builders and the label stamp
# ---------------------------------------------------------------------------

def test_rows_from_vm_assigns_the_strata_and_keeps_the_extra_raters(monkeypatch):
    monkeypatch.setattr(M, "_extra_grades", lambda rec, year: {"baseballamerica": 55.0})
    sb_rows = [{"key": "k1", "year": 2019, "archetype": "hs_bat",
                "grades": {"xfv": 51.2, CONS: 50.0, "fangraphs": 50.0, "mlb_pipeline": 45.0},
                "outcome": {"war": 2.0, "debuted": True, "debut_year": 2019}},
               {"key": "k2", "year": 2019, "grades": {"xfv": 40.0, CONS: 40.0, "fangraphs": 40.0,
                                                      "mlb_pipeline": 40.0},
                "outcome": {"war": 0.0, "debuted": True, "debut_year": 2019}}]
    side_of = {"k1": "hit"}
    milb_of = {"k1": {"milb_level": "AA", "milb_season": 2018}}
    records = {"k1": {"player_key": "k1", "position": "SS", "birth_date": "1997-05-01"}}
    rows, rec = M.rows_from_vm("vm2", sb_rows, side_of, milb_of, records, {"k1": {"resolved": 2.0}})
    assert rec["rows_in"] == 2 and rec["no_matrix_side"] == 1 and len(rows) == 1
    r = rows[0]
    assert r["key"] == "k1" and r["group"] == "hit|2019" and r["war"] == 2.0 and r["debut_year"] == 2019
    assert r["grades"]["efv"] == 51.2 and r["grades"]["baseballamerica"] == 55.0
    assert r["cells"]["side"] == "hit" and r["cells"]["position_family"] == "IF"
    assert r["cells"]["level_at_list"] == "AA" and r["cells"]["age_band"] == "21-22"
    assert r["cells"]["list_year"] == "2019" and r["cells"]["source_disagreement"] == "gap_under_10"
    assert r["l6"] == {"resolved": 2.0} and r["r3"] is None
    assert set(r["cells"]) == set(ST.DIMENSIONS)


def test_label_block_stamps_the_provider_and_the_resolution():
    import efv_labels as L
    lb = M.label_block()
    assert lb["provider"] == L.provider()
    assert lb["resolved_through"] == L.resolved_through()
    if lb["provider"] == "ewar_v2":
        assert lb["epoch"].startswith("pre-epoch run on the eWAR v2 label")
    else:
        assert "after the fWAR label epoch" in lb["epoch"]


def test_artifact_carries_the_label_block_and_the_design(artifact):
    assert artifact["model_id"] == "efv_matrix"
    assert artifact["generated_at"].endswith("Z")
    lab = artifact["label"]
    assert lab["provider"] and lab["resolved_through"] and lab["epoch"]
    d = artifact["design"]
    assert d["floor_rows"] == SB.ARCH_MIN_N == 40
    assert d["bootstrap"] == {"B": 2000, "seed": 20260906, "estimator": "E_cond",
                              "unit": "player cluster",
                              "convention": "MDE95 = 1.645 * sd(delta), one-sided"}
    assert d["equivalence_margin"] == 0.02 and d["unpowered_mde95"] == 0.04
    assert d["vocabulary"] == list(M.READINGS)
    assert set(artifact["frames"]) == set(M.FRAMES)
    vm = artifact["frames"]["vm2"]
    assert vm["veto_leg"] == "auc_3" and artifact["frames"]["lv_dev"]["veto_leg"] == "auc_wstar"
    assert set(vm["comparators"]) == set(M.COMPARATORS)
    assert vm["cells"]["overall"]["all"]["comparators"]["espn"]["reading"] == "NOT_SCORED"
    assert artifact["frames"]["lv_dev"]["cells"]["overall"]["all"]["comparators"]["baseballamerica"]["reading"] \
        == "NOT_SCORED"
    for fid, f in _scored_frames(artifact):
        g = f["reserved_guard"]
        if ST.frame_kind(fid) == "lv":
            # R-LV: list vintages 2020 and 2021 never enter a list frame read here
            assert not (set(g["vintages_read"]) & set(F.RESERVED_LV)), fid
        else:
            # on a vm frame the vintage is the debut cohort; R-VM starts in 2025
            assert all(v < F.R_VM_FIRST_DEBUT_YEAR for v in g["vintages_read"]), fid
        assert g["reserved_vm_pins"] == []
        assert g["gate_sha"] is None
    assert math.isfinite(artifact["elapsed_s"])


def test_ba_comparisons_read_the_raw_grade():
    """PEER-5 (docs/efv-v2/EFV_PIT_AUDIT_FIXES.md section 5): the Baseball America
    comparator reads BA's raw grade. From the first adjusted-grade season the stored FV is
    risk-adjusted, so the raw grade under _extras is read and an entry without one is left
    out; before it the stored grade is the raw grade."""
    import baseballamerica_csv as BAC
    first = BAC.ADJUSTED_GRADE_FIRST_SEASON

    def pt(day, fv, raw=None, espn=None):
        ps = {"baseballamerica": {"fv_published": fv}}
        if raw is not None:
            ps["baseballamerica"]["tools"] = {"_extras": {"ba_raw_grade": raw}}
        if espn is not None:
            ps["espn"] = {"fv_published": espn}
        return {"snapshot_date": day, "per_source": ps}

    rec = {"points": [pt(f"{first}-02-01", 45.0, raw=55.0, espn=50.0),
                      pt(f"{first}-03-01", 40.0),
                      pt(f"{first - 1}-02-01", 50.0),
                      pt(f"{first - 1}-03-01", 45.0, raw=45.0),
                      pt(f"{first - 1}-07-01", 60.0, raw=60.0)]}
    assert M._ba_raw_by_year(rec) == {first: 55.0, first - 1: 50.0}
    assert M._extra_grades(rec, first) == {"baseballamerica": 55.0, "espn": 50.0}
    assert M._extra_grades(rec, first - 1) == {"baseballamerica": 50.0}
    assert M._extra_grades({"points": [pt(f"{first}-02-01", 45.0)]}, first) == {}
    assert M._extra_grades(None, first) == {}

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""M-1 pins: the head-to-head verdict may only be read off a SYMMETRIC frame.

Pre-registration: docs/efv-2026-08-13/HEADTOHEAD_FRAME_GATE.md.
Producer: tools/efv_headtohead_frame_lab.py -> data/xfv_headtohead_frame_eval.json.

The thing being guarded is a claim, not a number. eFV holds one grade per player,
fitted at that player's decision year, while the common set carries a consensus
read for every base year, so the comparison frame is a CHOICE and the choice
decides the answer:

    all base years      +0.0313 at 0.881x its floor   not resolvable
    pre-debut only      +0.0625 at 1.679x its floor   would read "beats consensus"
    base year == debut  +0.0040 at 0.131x its floor   dead tie

The middle frame is the only one that clears a floor, and it is the one a future
edit is most likely to promote by accident, because it is both the newest and the
most flattering. It removes the rows where the CONSENSUS is advantaged and keeps
the rows where eFV is, so its margin is earned partly by an asymmetry rather than
by better ordering. These tests exist so that promotion cannot happen quietly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"
ARTIFACT = DATA / "xfv_headtohead_frame_eval.json"
BACKTEST = DATA / "source_backtest.json"


def _load(p: Path):
    if not p.exists():
        pytest.skip(f"{p.name} not built on this tree")
    return json.loads(p.read_text(encoding="utf-8"))


def test_all_three_frames_are_scored_and_each_carries_its_own_floor():
    d = _load(ARTIFACT)
    for frame in ("incumbent", "corrected", "vintage_matched"):
        cell = d.get(frame)
        assert cell, f"{frame} missing from the artifact"
        assert cell.get("mde95"), f"{frame} has no floor"
        assert cell.get("delta") is not None, f"{frame} has no delta"
        # A frame without its own floor is the exact failure mode this lane was
        # opened to fix: a fresh delta read against an inherited constant.
        assert isinstance(cell["mde95"], (int, float)) and cell["mde95"] > 0


def test_the_frames_are_scored_inside_the_same_draws():
    """The incumbent must be RE-DERIVED here, never read off a stored constant.

    Mixing a stored floor with a fresh delta has crossed a verdict boundary twice
    in this program, which is why the lab scores every frame in one bootstrap.
    """
    d = _load(ARTIFACT)
    assert d.get("B_used", 0) >= 500, "too few usable draws to floor anything"
    assert "paired_difference" in d, "frames were not paired inside the draws"
    pd_ = d["paired_difference"]
    assert pd_.get("sd") is not None and pd_.get("ci95")


def test_the_direction_control_holds():
    """The consensus must order the REMOVED rows better than the retained ones.

    That is the whole mechanism: on a post-debut read the consensus is grading a
    player it has already watched in the majors. If this ever flips, the stated
    reason for stripping those rows is wrong and the frame choice has to be
    re-argued from scratch.
    """
    d = _load(ARTIFACT)
    dc = d.get("direction_control") or {}
    assert dc.get("mechanism_holds") is True, dc
    assert dc["consensus_rho_removed"] > dc["consensus_rho_retained"]


def test_the_published_verdict_is_read_off_the_symmetric_frame():
    """The site's head-to-head verdict must sit on the vintage-matched basis.

    Not on the pre-debut basis, which is the flattering one, and not on the
    all-vintages basis, which hands the consensus the outcome.
    """
    bt = _load(BACKTEST)
    acc = bt.get("accuracy") or {}
    if not acc.get("head_to_head_by_frame"):
        pytest.skip("source_backtest.json predates the M-1 frame split")
    hh = acc.get("head_to_head_verdict")
    assert hh, "the frame split ran but published no verdict"
    # FP3-1 (owner answer 2026-09-25): the symmetric frame is the timing-pinned
    # vintage-matched frame vm2; vm1 stays published as superseded history.
    assert hh.get("basis") == "pooled_efv_common_vintage_matched_vm2", (
        "the head-to-head verdict moved off the timing-pinned symmetric frame; if "
        "that is deliberate it needs its own gate, because the other frames each "
        "hand one of the two graders an information edge")
    assert hh.get("frame_version") == "vm2" and hh.get("role") == "headline"
    vm1 = acc["head_to_head_by_frame"].get("vintage_matched")
    if vm1:
        assert vm1.get("role") == "superseded" and vm1.get("frame_version") == "vm1"


def test_a_win_is_never_published_off_the_predebut_frame():
    """The load-bearing guard. `xfv_beats` may not be true on the tilted frame.

    Stated as a property of whatever the artifact currently holds rather than as
    a pinned number, so it keeps working after the next rebuild moves the
    decimals.
    """
    bt = _load(BACKTEST)
    frames = (bt.get("accuracy") or {}).get("head_to_head_by_frame") or {}
    if not frames:
        pytest.skip("source_backtest.json predates the M-1 frame split")
    pre = frames.get("predebut")
    if pre:
        assert "tilted TOWARD eFV" in (pre.get("basis_note") or ""), (
            "the pre-debut frame must keep disclosing which way it tilts")
    hh = (bt.get("accuracy") or {}).get("head_to_head_verdict") or {}
    if hh.get("xfv_beats"):
        assert hh.get("basis") == "pooled_efv_common_vintage_matched_vm2", (
            "a 'beats consensus' verdict was published off a tilted frame")


def test_every_frame_is_scored_on_identical_rows_within_itself():
    """Each frame re-scores EVERY rater on that frame's rows.

    A frame that scored eFV on one population and the consensus on another would
    reintroduce the 2026-08-07 defect that `pooled_efv_common` exists to fix.
    """
    bt = _load(BACKTEST)
    acc = bt.get("accuracy") or {}
    for key in ("pooled_efv_common", "pooled_efv_common_predebut",
                "pooled_efv_common_vintage_matched",
                "pooled_efv_common_vintage_matched_vm2"):
        blk = acc.get(key)
        if not blk:
            continue
        ns = {r: (v or {}).get("n") for r, v in blk.items() if isinstance(v, dict)}
        ns = {r: n for r, n in ns.items() if n is not None}
        assert len(set(ns.values())) == 1, f"{key} scored raters on different rows: {ns}"


# ---------------------------------------------------------------------------
# EV-01 (docs/efv-v2/PROGRAM.md s3.4): frame version vm2, the timing pin.
#
# vm1 scores eFV with its consensus input read at the last snapshot before the
# debut DATE, which for a midseason debut is a read the raters never get (E1:
# 247 of 812 rows read after May 1). vm2 scores the same fits with the input
# read at the raters' own preseason point. These pins say the pin holds on
# every row, that it is the raters' point and not merely a point in the window,
# and that vm1 stays the verdict until the owner promotes vm2.

def test_the_pin_window_is_the_raters_window():
    import efv_dataset as ed
    import source_backtest as sb
    assert ed.PRESEASON_WINDOW_START_MMDD == sb._WINDOW_START_MMDD
    assert ed.PRESEASON_WINDOW_END_MMDD == sb._WINDOW_END_MMDD
    assert ed.preseason_window(2019) == ("2019-01-01", "2019-05-01")


def test_the_accessor_reads_the_latest_in_window_point_only():
    import efv_dataset as ed
    rec = {"points": [
        {"snapshot_date": "2018-11-01", "consensus_fv_raw": 40.0},
        {"snapshot_date": "2019-02-01", "consensus_fv_raw": 45.0,
         "per_source": {"fangraphs": {"fv_published": 45}}},
        {"snapshot_date": "2019-04-30", "consensus_fv_raw": 47.5},
        {"snapshot_date": "2019-05-01", "consensus_fv_raw": 55.0},
        {"snapshot_date": "2019-07-15", "consensus_fv_raw": 60.0},
    ]}
    got = ed.preseason_consensus_asof(rec, 2019, "hit")
    assert got["asof_date"] == "2019-04-30"
    assert got["consensus_fv_raw"] == 47.5
    assert got["fv_trend"] == 7.5            # history stops at the pinned point
    assert ed.preseason_consensus_asof(rec, 2020, "hit") is None
    # Same consensus rule as the rater: consensus_fv when the raw key is absent.
    rec2 = {"points": [{"snapshot_date": "2021-03-01", "consensus_fv": 50.0}]}
    assert ed.preseason_consensus_asof(rec2, 2021, "pit")["consensus_fv_raw"] == 50.0
    rec3 = {"points": [{"snapshot_date": "2021-03-01", "consensus_fv_raw": None}]}
    assert ed.preseason_consensus_asof(rec3, 2021, "pit") is None


@pytest.fixture(scope="module")
def pinned():
    import efv_dataset as ed
    import efv_model as em
    for side in ("hit", "pit"):
        if not ed.matrix_path(side).exists():
            pytest.skip("eFV training matrices not built on this tree")
    out = {}
    for side in ("hit", "pit"):
        rc: dict = {}
        out[side] = (em.oos_grades(side), em.oos_grades(side, timing_pin=True, receipts=rc), rc)
    return out


def test_every_vm2_consensus_input_is_dated_inside_its_window(pinned):
    import efv_model as em
    n = 0
    for side, (_v1, v2, rc) in pinned.items():
        assert set(v2) == set(rc), f"{side}: a pinned score without its receipt"
        for k, r in rc.items():
            lo, hi = r["window"]
            assert (lo, hi) == (f"{r['window_year']}-01-01", f"{r['window_year']}-05-01")
            assert lo <= r["asof_date"] < hi, (side, k, r)
            # No reserved vintage: SCORED_YEARS ends before the 2025 debut cohort.
            assert r["window_year"] in em.SCORED_YEARS and r["window_year"] < 2025
            n += 1
    assert n > 500, "the pinned mode scored almost nothing"


def test_the_pin_changes_only_the_scored_input(pinned):
    """The fits are the vm1 fits: where the pinned read IS the matrix read, the
    vm2 score equals the vm1 score exactly."""
    same = 0
    for side, (v1, v2, rc) in pinned.items():
        assert set(v2) <= set(v1)
        for k, r in rc.items():
            if r["asof_date"] == r["matrix_asof_date"]:
                assert v2[k] == v1[k], (side, k)
                same += 1
    assert same > 100


def test_the_vm2_headline_carries_its_timing_receipt_and_vm1_is_superseded():
    """FP3-1: the headline verdict IS the vm2 frame; vm1 is kept as history."""
    bt = _load(BACKTEST)
    acc = bt.get("accuracy") or {}
    hv = acc.get("head_to_head_verdict")
    if not hv or hv.get("frame_version") != "vm2":
        pytest.skip("source_backtest.json predates the FP3-1 headline move")
    assert "head_to_head_verdict_vm2" not in acc and "head_to_head_vs_sources_vm2" not in acc, (
        "a second verdict key rides beside the headline; the page must read one key")
    assert hv["basis"] == "pooled_efv_common_vintage_matched_vm2"
    assert hv["role"] == "headline"
    frames = acc["head_to_head_by_frame"]
    assert frames["vintage_matched_vm2"]["frame_version"] == "vm2"
    assert frames["vintage_matched_vm2"]["role"] == "headline"
    vm1 = frames["vintage_matched"]
    assert vm1["frame_version"] == "vm1" and vm1["role"] == "superseded"
    assert vm1.get("superseded_note")
    # The floor is labelled carried, never passed off as measured on vm2.
    assert hv["mde95_status"] == "carried" and hv["mde95_carried_from"] == "vm1"
    assert hv["mde95"] == vm1["mde95"]
    tp = hv["timing_pin"]
    assert tp["n_rows"] == hv["n"] == acc["pooled_efv_common_vintage_matched_vm2"]["xfv"]["n"]
    assert tp["n_outside_window"] == 0
    # The input is the raters' own consensus read on every row, not just any
    # point inside the window.
    assert tp["n_input_equals_rater_consensus"] == tp["n_rows"]
    lo, hi = tp["input_mmdd_range"]
    assert "-01-01" <= lo and hi < "-05-01"
    assert sum(hv["n_by_side"].values()) == hv["n"]
    # A vm2 row is a vm1 row: the frame can only lose rows, never add them.
    assert hv["n"] <= vm1["n"]
    assert hv["n"] + tp["n_vintage_rows_without_pin"] == vm1["n"]
    if hv.get("xfv_beats"):
        assert hv["resolvable"] is True


def test_the_per_source_cells_carry_one_holm_family():
    """FP3-3: six cells, one family, alpha stated; a verdict word only on a cell
    that survives Holm, and the consensus Spearman cell also needs the headline."""
    bt = _load(BACKTEST)
    acc = bt.get("accuracy") or {}
    vs = acc.get("head_to_head_vs_sources") or {}
    if not vs.get("holm"):
        pytest.skip("source_backtest.json predates the FP3-3 Holm family")
    hv = acc["head_to_head_verdict"]
    assert vs["basis"] == hv["basis"]
    h = vs["holm"]
    assert h["k"] == 6 and h["alpha"] == 0.05
    assert h["family"] == [f"{r}.{m}" for r in ("prospx_consensus", "mlb_pipeline", "fangraphs")
                           for m in ("spearman", "auc")]
    steps = []
    n_words = 0
    for r, cell in vs["sources"].items():
        for m in ("spearman", "auc"):
            leg = cell.get(m)
            if not leg:
                continue
            ho = leg["holm"]
            steps.append(ho["holm_step"])
            if leg["verdict"]:
                n_words += 1
                assert ho["reject_holm"] is True
                assert abs(leg["delta"]) >= ho["mde95_holm"] - 1e-4
                assert leg["verdict"] in (f"beats {cell['label']}", f"loses to {cell['label']}")
                assert (leg["delta"] > 0) == leg["verdict"].startswith("beats")
            else:
                assert leg["reading"] == "interval only"
    assert sorted(steps) == list(range(1, len(steps) + 1))
    assert n_words == h["n_verdicts"]
    cons = vs["sources"]["prospx_consensus"]["spearman"]
    if cons["verdict"]:
        assert hv["resolvable"] is True
    # The headline's CI95 is the consensus Spearman cell's interval.
    assert hv["ci95"] == cons["ci95"]


def test_the_backtest_holm_matches_the_lab_implementation():
    """source_backtest._holm_family is a stdlib copy of
    tools/efv_power_lab.holm_family; on the same cells they agree exactly."""
    import sys
    import source_backtest as sb
    sys.path.insert(0, str(Path(__file__).parent / "tools"))
    lab = pytest.importorskip("efv_power_lab")
    cells = [{"key": "a", "delta": -0.0055, "sd": 0.0077},
             {"key": "b", "delta": 0.0013, "sd": 0.0044},
             {"key": "c", "delta": -0.0042, "sd": 0.0143},
             {"key": "d", "delta": 0.0113, "sd": 0.00815},
             {"key": "e", "delta": 0.0412, "sd": 0.0169},
             {"key": "f", "delta": 0.0352, "sd": 0.0099}]
    mine, theirs = sb._holm_family(cells), lab.holm_family(cells)
    assert mine["k"] == theirs["k"] == 6
    for x, y in zip(mine["cells"], theirs["cells"]):
        assert x["key"] == y["key"]
        assert x["p_one_sided"] == y["p_one_sided"]
        assert x["holm_step"] == y["holm_step"]
        assert x["reject_holm"] == y["reject_holm"]
        assert x["mde95_holm"] == y["mde95_holm_k6"]
    # A missing cell stays in the family at p = 1 and is never rejected.
    gap = sb._holm_family(cells[:5] + [{"key": "f", "delta": None, "sd": None}])
    assert gap["k"] == 6 and gap["cells"][-1]["reject_holm"] is False


def test_vm2_rows_drop_a_mismatched_or_out_of_window_pin():
    import source_backtest as sb
    C = sb.CONSENSUS_KEY

    def row(k, y, dy, cons):
        return {"key": k, "year": y, "outcome": {"debut_year": dy},
                "grades": {C: cons, "xfv": cons}}
    rows = [row("a", 2019, 2019, 50.0), row("b", 2019, 2019, 45.0),
            row("c", 2020, 2020, 40.0), row("a", 2018, 2019, 45.0)]
    raw = [1.0, 2.0, 3.0, 1.0]
    oos2 = {"a": 5.0, "b": 0.5, "c": 0.1}
    rc = {"a": {"asof_date": "2019-03-01", "window_year": 2019, "consensus_fv_raw": 50.0,
                "matrix_asof_date": "2019-07-01", "matrix_consensus_fv_raw": 52.0},
          "b": {"asof_date": "2020-03-01", "window_year": 2020, "consensus_fv_raw": 45.0,
                "matrix_asof_date": "2019-07-01", "matrix_consensus_fv_raw": 45.0},
          "c": {"asof_date": "2020-06-01", "window_year": 2020, "consensus_fv_raw": 40.0,
                "matrix_asof_date": "2020-06-01", "matrix_consensus_fv_raw": 40.0}}
    before = json.dumps(rows, sort_keys=True)

    def vm(c):
        return c["year"] == c["outcome"]["debut_year"]
    out, rec = sb._vm2_frame_rows(rows, raw, oos2, rc, vm)
    assert [r["key"] for r in out] == ["a"]
    assert rec["n_vintage_rows_without_pin"] == 1 and rec["n_outside_window"] == 1
    assert rec["n_input_date_moved"] == 1 and rec["n_consensus_value_moved"] == 1
    assert rec["n_input_equals_rater_consensus"] == 1
    assert out[0]["xfv_input"]["window"] == ["2019-01-01", "2019-05-01"]
    assert json.dumps(rows, sort_keys=True) == before, "vm1 rows were modified"

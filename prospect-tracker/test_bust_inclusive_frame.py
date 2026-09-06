"""A-CLAIM-4: the bust-inclusive head-to-head frame.

THE DEFECT IT CLOSES. `_is_vintage_matched` requires a debut year, so a prospect who
never reached the majors CANNOT enter the flagship head-to-head frame. Every accuracy
cell the artifact publishes is measured on players who all made it, and the ones a grade
got most wrong are exactly the ones who vanished.

THE THREE MISTAKES THESE TESTS EXIST FOR, and the first two were made:

  1. SCORING THE BUSTS ALONE. Every bust has the same outcome, zero WAR, so a rank
     correlation against it is undefined and every bootstrap draw returns NaN. The first
     build did this and the floor reported "not derived: too few usable draws", which is
     correct and useless.
  2. MIXING TWO GRADES. The common set's stored eFV values are remapped in place onto the
     consensus-FV distribution. Using them for the debuted half while the busts carry raw
     out-of-sample grades compares a remapped number against a raw one.
  3. ADMITTING BUSTS TO THE COMMON SET. The remap re-derives its grid from whatever
     population it is handed, so enlarging it would re-bin the ties for every existing row
     and move published cells. This lane is a receipt and is not entitled to do that.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import source_backtest as sb          # noqa: E402

ART = ROOT / "data" / "source_backtest.json"
GATE = ROOT / "docs" / "efv-2026-09-06" / "CLAIM_INSTRUMENTS.md"


@pytest.fixture(scope="module")
def bust():
    if not ART.exists():
        pytest.skip("data/source_backtest.json has not been built")
    ci = (json.loads(ART.read_text(encoding="utf-8"))
          .get("accuracy", {}).get("claim_instruments") or {})
    b = ci.get("bust_inclusive")
    if not b:
        pytest.skip("the bust-inclusive frame is not in the artifact")
    return b


# --------------------------------------------------------------------------
# The survivorship finding
# --------------------------------------------------------------------------

def test_the_flagship_frame_cannot_contain_a_never_debuted_player():
    """Structural, not statistical. The frame is keyed on a debut."""
    src = (ROOT / "source_backtest.py").read_text(encoding="utf-8")
    i = src.index("def _is_vintage_matched")
    assert "dy is not None" in src[i:i + 300], (
        "the vintage-matched predicate no longer requires a debut year; if that "
        "changed deliberately, this whole lane's premise needs re-reading")


def test_the_bust_pool_is_entirely_never_debuted():
    rows = json.loads((ROOT / "data" / "inactive.json").read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else (rows.get("players") or [])
    assert len(rows) > 2000
    assert not [r for r in rows if r.get("debut_date")], (
        "inactive.json now contains players with a debut date, so it is no "
        "longer the never-debuted pool this lane assumes")


# --------------------------------------------------------------------------
# The screens
# --------------------------------------------------------------------------

def test_a_player_with_real_major_league_war_is_not_a_bust():
    """Exactly one qualifies and he is a real reliever. Scoring him as a
    never-debuted failure would be a plain lie about a player a reader may
    remember."""
    uni = sb._load_universe(sb.DATA_DIR)
    kept, excluded = sb._load_bust_universe(sb.DATA_DIR, uni)
    war_drops = [e for e in excluded if "career WAR" in e["reason"]]
    assert war_drops, "the WAR screen fired on nobody; it should catch Britton"
    assert all(k.get("player_key") != d["player_key"]
               for k in kept for d in war_drops)


def test_an_identity_collision_is_excluded_and_named():
    """A bust whose MLBAM id is already in the debuted universe is the same
    human by two routes, and counting him twice lets one player be his own
    control."""
    uni = sb._load_universe(sb.DATA_DIR)
    _kept, excluded = sb._load_bust_universe(sb.DATA_DIR, uni)
    id_drops = [e for e in excluded if "mlbam id" in e["reason"]]
    assert id_drops, "no identity collisions were caught at all"
    for d in id_drops:
        assert d["player_key"], "an exclusion was recorded with no player named"


def test_every_exclusion_carries_a_reason():
    uni = sb._load_universe(sb.DATA_DIR)
    _kept, excluded = sb._load_bust_universe(sb.DATA_DIR, uni)
    for e in excluded:
        assert e.get("reason"), f"unexplained exclusion: {e}"


def test_a_missing_file_is_reported_rather_than_treated_as_an_empty_pool(tmp_path):
    kept, excluded = sb._load_bust_universe(tmp_path, [])
    assert kept == []
    assert excluded and "does not exist" in excluded[0]["reason"], (
        "an absent inactive.json reads as a pool with no busts in it, which "
        "would silently turn this lane into a no-op that still publishes")


# --------------------------------------------------------------------------
# The pool must be combined
# --------------------------------------------------------------------------

def test_the_frame_scores_the_combined_pool_not_the_busts_alone(bust):
    assert bust["n_bust_half"] > 100
    assert bust["n_debuted_half"] > 100
    assert bust["n_combined"] == bust["n_bust_half"] + bust["n_debuted_half"]
    assert "undefined" in bust["why_the_pool_is_combined"].lower()


def test_every_cell_actually_derived_a_floor(bust):
    """The signature of the busts-alone mistake: a floor that could not be
    derived because the outcome had no variance."""
    for comp, cell in bust["cells"].items():
        f = cell.get("floor_E_cond_in_run") or {}
        assert f.get("mde95") is not None, (
            f"{comp}: the floor came back {f.get('status')!r}. A pool whose "
            "outcome is constant cannot be rank-correlated against it.")
        assert cell.get("point_delta") is not None


def test_both_halves_are_scored_on_the_same_grade(bust):
    note = bust["both_halves_use_the_same_grade"].lower()
    assert "raw out-of-sample" in note and "remapped" in note


def test_the_comparator_is_recorded_on_every_cell(bust):
    for comp, cell in bust["cells"].items():
        assert cell.get("comparator") == comp, (
            "a cell does not record which rater it was scored against, so its "
            "delta has no stated direction")


def test_the_consensus_is_not_re_scored_here(bust):
    """The consensus bust cell is the already-measured full_pool_km. Re-deriving
    it would be a second read of a cell that has one."""
    assert sb.CONSENSUS_KEY not in bust["cells"]
    assert set(bust["cells"]) <= set(sb.SCORED_SOURCES)


# --------------------------------------------------------------------------
# The blast radius
# --------------------------------------------------------------------------

def test_the_frame_declares_that_it_moves_nothing(bust):
    assert bust["changes_no_published_number"] is True
    assert "never added to the common set" in bust["blast_radius"]


def test_the_common_set_contains_no_never_debuted_row():
    """The rule, checked against the artifact rather than trusted. A bust in the
    common set would re-bin the eFV remap for every existing row."""
    if not ART.exists():
        pytest.skip("artifact not built")
    a = json.loads(ART.read_text(encoding="utf-8"))["accuracy"]
    # The vintage-matched frame is defined by a debut year, so its own n is the
    # check: it must not have grown by the size of the bust pool.
    vm = a["claim_instruments"]["head_to_head_floors"]["vintage_matched"]
    b = a["claim_instruments"]["bust_inclusive"]
    assert vm["n"] < b["n_combined"], (
        "the vintage-matched frame is as large as the combined pool, which "
        "means the busts were admitted to the common set")


# --------------------------------------------------------------------------
# The result
# --------------------------------------------------------------------------

def test_nothing_is_resolvable_on_this_pool(bust):
    """The pre-registered expectation. eFV is nominally ahead of both raters and
    every margin sits inside the floor this pool can resolve, so no claim may be
    made in either direction."""
    for comp, cell in bust["cells"].items():
        d = abs(cell["point_delta"])
        m = (cell["floor_E_cond_in_run"] or {}).get("mde95")
        assert m is not None
        assert d <= m, (
            f"eFV vs {comp} now clears its floor on the bust-inclusive pool "
            f"({d:.5f} against {m}). That is a real result and it contradicts "
            "the pre-registration; confirm it before anything is claimed.")


def test_the_receipt_accounts_for_every_row_read(bust):
    r = bust["receipt"]
    total = (r["kept"] + r["no_points"] + r["not_graded_by_all_raters"]
             + r["no_efv"] + r["out_of_window_years"])
    assert total == r["considered"], (
        f"the receipt loses {r['considered'] - total} rows between reading and "
        "keeping; every drop must be named or the coverage claim is empty")
    assert r["read_from_inactive_json"] == r["considered"] + r["excluded_by_screen"]


def test_the_gate_document_exists_and_records_the_prediction():
    assert GATE.exists(), f"{GATE} is missing; the lane's clauses were frozen there"
    txt = GATE.read_text(encoding="utf-8")
    assert "Pre-registered expectations" in txt
    assert "HELD" in txt or "FAILED" in txt, (
        "the gate document does not record whether its prediction held; a "
        "failed prediction is written down, not edited")


def test_the_gate_document_records_the_cohort_drift():
    """The population underneath this artifact is not pinned by git, and a
    future reader comparing two runs needs to know that."""
    txt = GATE.read_text(encoding="utf-8").lower()
    assert "gitignored" in txt and "timeseries" in txt

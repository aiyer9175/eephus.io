# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the HEM+ family re-baseline and the HEM+ against xwOBA leg
(docs/HEM_XWOBA_REGATE_GATE.md, pre-registered 2026-10-15, run once as an
owner-waived early read).

Two layers. The rule layer runs always: the R1-6 table as code (decide) and
the per-row consequence (the mover), on synthetic cells, so the mapping from
a cell to a verdict cannot drift. The result layer runs once the one artifact
exists and pins what the run FOUND and the structure that made it trustworthy:
both conventions on every cell, Holm k = 3, the frozen-subset reproduction,
the owner-waived read written down, and the registry rows matching the
artifact. Pure file reads; no lab is executed here."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))
import hem_xwoba_regate_lab as lab  # noqa: E402
import register_hem_xwoba_regate as mover  # noqa: E402

GATE_DOC = ROOT / "docs" / "HEM_XWOBA_REGATE_GATE.md"
ART = ROOT / "data" / "hem_xwoba_regate_eval.json"
PRIOR = ROOT / "data" / "xhem_served_regate_eval.json"
ARMS = ("A1_xhem_plus", "A2_fwdhem_plus", "A3_hem_plus")

ran = pytest.mark.skipif(not ART.exists(), reason="the one run has not happened yet")


def _json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _row(model_id: str) -> dict:
    for m in _json(ROOT / "data" / "model_registry.json")["models"]:
        if m.get("model_id") == model_id:
            return m
    raise AssertionError(f"registry row missing: {model_id}")


def _cell(lo, hi):
    return {"gap_ci": {"mean": (lo + hi) / 2, "lo95": lo, "hi95": hi},
            "lo95_gt_0": lo > 0, "hi95_lt_0": hi < 0}


# ---------------------------------------------------------------------------
# the registration
# ---------------------------------------------------------------------------

def test_gate_document_exists_and_claims_its_order():
    text = GATE_DOC.read_text(encoding="utf-8")
    assert "NOTHING IN THIS DOCUMENT WAS COMPUTED" in text
    assert "HONESTY CLAUSE" in text
    assert "k = 3" in text and "SEED_R3 = 20261015" in text
    assert "rho(HEM+_served(Y), wOBA(Y+1)) - rho(xwOBA(Y), wOBA(Y+1))" in text
    assert chr(8212) not in text and chr(8211) not in text


# ---------------------------------------------------------------------------
# the rule layer: R1-6 as code, and the per-row consequence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("v1,v2,h1,h2,row,verdict", [
    ((0.01, 0.05), (0.01, 0.06), True, True, "both", "validated"),
    ((0.01, 0.05), (-0.01, 0.06), True, False, "v1_only", "provisional"),
    ((-0.01, 0.05), (0.01, 0.06), False, True, "v2_only", "provisional"),
    ((-0.01, 0.05), (-0.01, 0.06), False, False, "straddle", "provisional"),
    ((-0.08, -0.02), (-0.09, -0.01), False, False, "refuted", "deprecated"),
    ((0.01, 0.05), (-0.09, -0.01), True, False, "refuted", "deprecated"),
    # a cell above zero that Holm does not reject is NOT a pass
    ((0.01, 0.05), (0.01, 0.06), False, True, "v2_only", "provisional"),
])
def test_decide_is_the_r1_6_table(v1, v2, h1, h2, row, verdict):
    d = lab.decide({"v1": _cell(*v1), "v2": _cell(*v2)}, h1, h2)
    assert d["table_row"] == row and d["verdict"] == verdict


def test_the_per_row_consequence_follows_the_gate():
    arm = lambda row, v: {"table_row": row, "verdict": v}  # noqa: E731
    assert mover._consequence("fwdhem_plus", arm("both", "validated"))[0] == "validated"
    assert mover._consequence("fwdhem_plus", arm("straddle", "provisional"))[0] == "provisional"
    assert mover._consequence("fwdhem_plus", arm("v1_only", "provisional"))[0] == "provisional"
    assert mover._consequence("hem_plus", arm("refuted", "deprecated"))[0] == "deprecated"
    assert "display lane" in mover._consequence("hem_plus", arm("refuted", "deprecated"))[1]
    assert mover._consequence("hem_plus", arm("straddle", "provisional"))[0] == "provisional"
    assert mover._consequence("hem_plus", arm("both", "validated"))[0] == "validated"
    assert mover._consequence("xhem_plus", arm("both", "validated"))[0] == "validated"
    assert mover._consequence("xhem_plus", arm("v2_only", "provisional"))[0] == "provisional"


def test_the_mover_types_no_number_and_is_idempotent(monkeypatch):
    """The three rows move from a fixture artifact exactly once; every number
    in the moved row is read off the artifact; a second apply is a no-op."""
    monkeypatch.setenv("PLUS_LAB_SEASON_COMPLETE_ASOF", "2026:2026-10-01")
    art = lab.score(lab.fixtures(), boot=25, new_block_floor=0)
    art["verdict"]["status"] = "RAN"
    doc = _json(ROOT / "data" / "model_registry.json")
    before = copy.deepcopy(doc)
    moved = mover.apply(doc, art)
    assert sorted(moved) == ["fwdhem_plus", "hem_plus", "xhem_plus"]
    by_id = {r["model_id"]: r for r in doc["models"]}
    for mid in moved:
        r = by_id[mid]
        arm = art["arms"][mover.ARM_OF[mid]]
        d4 = arm["ladder"]["D4"]["v1"]
        assert r["eval_artifact"] == mover.ART_REL
        assert r["verdict"] == mover._consequence(mid, arm)[0]
        assert r["card"]["headline"][0]["champion"] == round(d4["rho_primary"], 3)
        assert r["card"]["headline"][0]["baseline"] == round(d4["rho_baseline"], 3)
        assert r["card"]["n"] == art["n_forward_pairs"][mover.ARM_OF[mid][:2]]
        assert mover.PRIOR_ART[mid] in r["notes"], "the prior artifact stays cited by path"
        assert "OWNER-WAIVED EARLY READ" in r["notes"]
        assert len(r["summary"].split()) <= 30
        assert chr(8212) not in r["notes"] and chr(8212) not in r["summary"]
    assert mover.apply(doc, art) == []
    # nothing else moved
    untouched = [r for r in doc["models"] if r["model_id"] not in moved]
    assert untouched == [r for r in before["models"] if r["model_id"] not in moved]


def test_the_mover_refuses_an_artifact_that_did_not_run():
    doc = _json(ROOT / "data" / "model_registry.json")
    art = {"verdict": {"status": "REFUSED"}, "owner_waived_early_read": {}}
    assert mover.apply(doc, art) == []
    art = {"verdict": {"status": "STOPPED_REPRODUCTION_FAILED"}, "owner_waived_early_read": {"x": 1}}
    assert mover.apply(doc, art) == []


# ---------------------------------------------------------------------------
# the result layer: what the one run found
# ---------------------------------------------------------------------------

@ran
def test_artifact_names_its_gate_and_its_waiver():
    d = _json(ART)
    assert d["gate_document"] == "docs/HEM_XWOBA_REGATE_GATE.md"
    assert d["pre_registered"].startswith("2026-10-15")
    ow = d["owner_waived_early_read"]
    assert "2026-11-16" in ow["registered_date"]
    assert ow["season_complete_override"]["seasons"] == {"2026": "2026-10-01"}
    assert d["harness"]["season_complete_override"]["seasons"] == {"2026": "2026-10-01"}
    assert d["verdict"]["status"] == "RAN"


@ran
def test_the_frozen_subset_reproduces_the_2026_09_18_cells():
    rep = _json(ART)["frozen_subset_reproduction"]
    assert rep["reproduces_all"] is True
    for arm in ("A1_xhem_plus", "A2_fwdhem_plus"):
        assert rep[arm]["reproduces"] is True
        assert rep["n_old_rows"][arm[:2]] == 1871


@ran
def test_the_2025_block_is_a_complete_season():
    cov = _json(ART)["coverage"]
    assert cov["new_block_predictor_season"] == 2025
    assert cov["new_block_n"] >= cov["new_block_floor"] == 200


@ran
@pytest.mark.parametrize("arm", ARMS)
def test_every_rung_reports_both_conventions_and_an_in_run_floor(arm):
    a = _json(ART)["arms"][arm]
    for rung, cells in a["ladder"].items():
        for conv in ("v1", "v2"):
            c = cells[conv]
            assert c["rho_primary"] is not None and c["rho_baseline"] is not None, (arm, rung, conv)
            assert c["gap_ci"] and c["mde95_in_run"] > 0, (arm, rung, conv)
            assert c["n_boot_draws"] == 2000
    assert "D4" in a["ladder"] and a["verdict_rung"] == "D4"


@ran
def test_holm_family_is_three_arms_per_convention():
    m = _json(ART)["multiplicity"]
    for conv in ("v1", "v2"):
        assert m[conv]["k"] == 3
        assert sorted(c["key"] for c in m[conv]["cells"]) == sorted(ARMS)


@ran
@pytest.mark.parametrize("arm", ARMS)
def test_each_verdict_is_the_rule_applied_to_its_own_cells(arm):
    d = _json(ART)
    a = d["arms"][arm]
    holm = {conv: next(c["reject_holm"] for c in d["multiplicity"][conv]["cells"] if c["key"] == arm)
            for conv in ("v1", "v2")}
    want = lab.decide(a["ladder"]["D4"], holm["v1"], holm["v2"])
    assert a["table_row"] == want["table_row"] and a["verdict"] == want["verdict"]


@ran
def test_a3_is_the_served_integer_against_xwoba_on_the_a2_rows():
    d = _json(ART)
    assert d["n_forward_pairs"]["A3"] == d["n_forward_pairs"]["A2"]
    a3 = d["arms"]["A3_hem_plus"]
    assert "int(round(hem_plus_raw))" in a3["served_construction"]
    assert a3["ladder"]["D4"]["n_distinct_values"] < a3["ladder"]["D3"]["n_distinct_values"]


@ran
@pytest.mark.parametrize("model_id", ["xhem_plus", "fwdhem_plus", "hem_plus"])
def test_registry_rows_carry_the_re_baseline(model_id):
    d = _json(ART)
    row = _row(model_id)
    arm = d["arms"][mover.ARM_OF[model_id]]
    assert row["eval_artifact"] == "data/hem_xwoba_regate_eval.json"
    assert row["verdict"] == mover._consequence(model_id, arm)[0]
    assert row["verdict"] == d["verdict"][model_id]
    d4 = arm["ladder"]["D4"]["v1"]
    head = row["card"]["headline"][0]
    assert head["champion"] == round(d4["rho_primary"], 3)
    assert head["baseline"] == round(d4["rho_baseline"], 3)
    assert "served" in head["label"].lower()
    assert "OWNER-WAIVED EARLY READ" in row["notes"]
    assert mover.PRIOR_ART[model_id] in row["notes"]


@ran
def test_the_gate_document_records_the_result():
    text = GATE_DOC.read_text(encoding="utf-8")
    sec = text.split("## 12. Results", 1)[1]
    assert "OWNER-WAIVED EARLY READ" in sec
    d = _json(ART)
    for arm in ARMS:
        assert d["arms"][arm]["verdict"] in sec
    assert str(d["n_forward_pairs"]["A1"]) in sec.replace(",", "")

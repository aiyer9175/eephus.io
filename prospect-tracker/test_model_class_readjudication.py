# Pins for the V3 model-class re-adjudication artifact
# (data/xfv_model_class_readjudication_eval.json, produced by
# tools/efv_model_class_gate.py against the frozen clauses in
# docs/efv-2026-08-19/MODEL_CLASS_READJUDICATION_GATE.md).
#
# What these tests protect, in order of the defect class they exist for:
#   1. the artifact exists and is valid JSON (the lane's evidence is on disk);
#   2. A0 passed: nothing below A0 is readable unless the lab reproduced the
#      shipped ridge path within the registered 1e-9 tolerance;
#   3. the controls held (zero-information twin below floor, no fold drops);
#   4. every cell's `ship` flag equals the frozen clause conjunction
#      (positive delta AND E_cond resolvable AND Holm reject AND S3 pass),
#      recomputed here from the cell's own stored legs, and the Holm rejects
#      themselves re-derive from the stored p-values; a reader must not be able
#      to quote a crossing cell that failed Holm as a win;
#   5. the verdict block agrees with the cells: `ships` lists exactly the
#      shipping cells, `all_null` is their emptiness, and the permanent-close
#      statement appears when and only when all four cells are null.
#
# Read-only: no fitting, no writes. Runs on the committed artifact.
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ART = ROOT / "data" / "xfv_model_class_readjudication_eval.json"
CELLS = ("hit_A1", "hit_A2", "pit_A1", "pit_A2")
ALPHA = 0.05


def _art() -> dict:
    raw = ART.read_text(encoding="utf-8")
    d = json.loads(raw)
    # round-trip validation: the artifact must reserialize
    json.loads(json.dumps(d))
    return d


def test_artifact_exists_and_is_valid_json():
    assert ART.exists(), "V3 artifact missing"
    d = _art()
    assert d.get("produced_by") == "tools/efv_model_class_gate.py"
    assert d.get("gate_doc") == "docs/efv-2026-08-19/MODEL_CLASS_READJUDICATION_GATE.md"


def test_a0_passed_and_tolerance_registered():
    d = _art()
    a0 = d.get("A0") or {}
    assert a0.get("passed") is True, "A0 failed: nothing below it is readable"
    assert a0.get("tolerance_pooled_rho") == 1e-9
    for side in ("hit", "pit"):
        s = a0["sides"][side]
        assert s["passed"] is True
        assert s["replica_pooled_rho_gap"] <= 1e-9
        assert s["lgbm_batch_max_abs_pred_gap"] <= 1e-9
        assert all(s["legs_equal_run_eval"].values())
        assert s["per_year_ridge_equal"] is True


def test_controls_held():
    d = _art()
    assert (d.get("C_c_fold_coverage") or {}).get("passed") is True
    tw = d.get("C_b_zero_information_twin") or {}
    assert tw.get("passed") is True
    for side in ("hit", "pit"):
        assert tw["sides"][side]["cleared_floor"] is False


def test_floors_are_frame_derived_at_registered_B():
    d = _art()
    fl = d.get("floors_E_cond") or {}
    assert fl.get("B") == 2000, "E_cond floors must be B=2000 as registered"
    assert fl.get("derived_before_arms_read") is True
    for key in CELLS:
        cell = fl["cells"][key]
        assert cell["B_used"] >= 1900
        assert cell["sd"] > 0
        assert abs(cell["mde95_onesided"] - round(1.645 * cell["sd"], 5)) < 1e-9


def _phi_upper(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def test_ship_flags_match_frozen_clauses():
    d = _art()
    cells = d["cells"]
    assert set(cells) == set(CELLS)
    # Holm re-derived from the stored p-values, independent of the lab's flags.
    ps = sorted((cells[k]["p_one_sided_win"], k) for k in CELLS)
    still, expect_holm = True, {}
    for i, (p, key) in enumerate(ps):
        rej = bool(still and p <= ALPHA / (len(ps) - i))
        if not rej:
            still = False
        expect_holm[key] = rej
    for key in CELLS:
        c = cells[key]
        # The p-value must agree with delta/sd. The lab computed p from the
        # UNROUNDED delta and sd; here we recompute from the stored values,
        # which carry 5dp (delta) / 6dp (sd) rounding. Worst-case induced p
        # shift is ~phi(0)/sd * 5e-6 ~= 2.2e-4 at sd ~0.009 (measured 1.07e-4
        # on hit_A2), so the guard is 5e-4: loose enough for rounding, tight
        # enough that a fabricated or transposed p still fails.
        sd = c["E_cond"]["sd"]
        expect_p = round(_phi_upper(c["delta_rho"] / sd), 6) if sd > 0 else 1.0
        assert abs(c["p_one_sided_win"] - expect_p) <= 5e-4, key
        assert c["holm_reject"] == expect_holm[key], key
        resolvable = abs(c["delta_rho"]) >= c["E_cond"]["mde95_onesided"]
        assert c["E_cond"]["resolvable"] == resolvable, key
        expect_ship = bool(c["delta_rho"] > 0 and resolvable
                           and c["holm_reject"] and c["S3"]["pass"])
        assert c["ship"] == expect_ship, (
            f"{key}: ship flag contradicts the frozen clause conjunction")
        # S3 internal consistency: pass is exactly "neither MAE leg worse
        # beyond its own CI"
        assert c["S3"]["pass"] == (not c["S3"]["mae_worse_beyond_ci"]
                                   and not c["S3"]["tail_worse_beyond_ci"]), key


def test_verdict_matches_cells_no_quotable_false_win():
    d = _art()
    cells = d["cells"]
    v = d["verdict"]
    ships = sorted(k for k in CELLS if cells[k]["ship"])
    assert sorted(v["ships"]) == ships
    assert v["all_null"] == (not ships)
    for key in CELLS:
        cs = v["cells_summary"][key]
        assert cs["ship"] == cells[key]["ship"], key
        assert cs["holm_reject"] == cells[key]["holm_reject"], key
        # a cell that failed Holm or its floor must be carried as non-shipping
        if not cells[key]["holm_reject"] or not cells[key]["E_cond"]["resolvable"]:
            assert cs["ship"] is False, key
    if v["all_null"]:
        assert "CLOSED" in v["statement"]
        assert "LABEL POOL" in v["statement"]
    else:
        for key in ships:
            assert key in v["statement"]


def test_e_refit_reported_beside_never_substituted():
    d = _art()
    ref = d.get("E_refit") or {}
    if ref.get("status") == "NOT COMPLETED":
        assert "measured_pace_s_per_draw" in ref
        return
    assert ref["B_used"] in (200, 100)
    assert "B_disclosure" in ref
    for key in CELLS:
        cell = ref["cells"][key]
        assert "secondary" in cell["role"]
        # the primary call in d["cells"] must not have been overwritten by this leg
        assert cell["point_delta"] == d["cells"][key]["delta_rho"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(name, "OK")

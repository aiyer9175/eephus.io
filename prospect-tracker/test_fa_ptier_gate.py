# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Fence tests for the 2026-08-19 ptier level gate + pooled tercile re-cut.

Task A (LOSS-RECORD): arm P-1, RECAL_MODE "shift_ptier" (per-predicted-tier
intercepts), FAILED its frozen gate (docs/fa-2026-08-19/PTIER_LEVEL_GATE.md
sections 2-3: C1 pooled MAE worsened vs the same-run champion; C5 the
permuted control improved, so the clause as registered fails). Nothing
shipped; RECAL_MODE stays "shift". The shift_ptier machinery remains in
fa_market.py default-off for a future re-gate (which needs a fresh
pre-registration with a paired-bootstrap gate, per the loss-record).

Task B (SHIPPED, owner default 2026-08-19): pooled verdict tercile edges
re-cut 109/223 -> 89/198 on the current NPV corpus (n=1,300; restores
434/433/433 against the 33/33/33 design; 180 historical pooled verdicts
flip). VERDICT_BAND_MODE stays "group", so served verdicts do not move
until VERDICT_GROUP_EDGES is re-cut on the same basis (followup owed).

These tests pin the fence:

  - RECAL_MODE default is "shift" and the P-1 lab knobs are inert; a
    "shift_ptier" default without a NEW passing gate doc is the
    invented-number defect class
  - _LAB_DEFAULTS tracks the shipped defaults (a stale entry makes every
    future lab score the wrong baseline)
  - the shift_ptier routing helpers behave as the gate doc registered them
    (raw-prediction ptier keying, pooled fallback)
  - the served artifact carries no positive ptier bias beyond +10 $M
    (the E5a overshoot check, standing)
  - artifact verdict edges match the fa_market.py constants, and the
    artifact carries generated_at. run_market_gate(persist=True) stamps
    generated_at and carries verdict_edges, *_gate and ptier_* blocks
    forward (a97e5359, 2026-08-19); since 2026-09-25 it also stamps
    war_provider. A plain re-persist therefore keeps the OLD edges: re-cutting
    them is its own step.

If a future re-gate ships shift_ptier or re-cuts any edge, it must update
these assertions IN THE SAME CHANGE as the new passing gate doc.
"""

import json
from pathlib import Path

import fa_market as fm

HERE = Path(__file__).parent
GATE_DOC = HERE / "docs" / "fa-2026-08-19" / "PTIER_LEVEL_GATE.md"


def _gate2() -> dict:
    return json.loads((HERE / "data" / "fa_gate2_eval.json")
                      .read_text(encoding="utf-8"))


def test_recal_mode_stays_shift():
    # P-1 verdict is NO SHIP: the champion intercept-only pooled shift.
    assert fm.RECAL_MODE == "shift", (
        "RECAL_MODE moved off 'shift' but the 2026-08-19 P-1 verdict is "
        "LOSS-RECORD; ship shift_ptier only through a NEW passing gate doc")
    # Lab-only knobs must be inert at import.
    assert fm.RECAL_TIER_PERMUTE_SEED == 0
    assert fm.RECAL_FIT_LOG is None


def test_lab_defaults_track_shipped():
    for key, val in fm._LAB_DEFAULTS.items():
        assert getattr(fm, key) == val, (
            f"_LAB_DEFAULTS[{key!r}]={val!r} != shipped {getattr(fm, key)!r}; "
            "LAB_RESET() would restore the wrong champion")


def test_guar_ptier_bins():
    # The Gate-2 predicted-guarantee tier bins at 10/20/50 $M.
    assert fm._guar_ptier(9.99e6) == "lt10"
    assert fm._guar_ptier(10e6) == "10to20"
    assert fm._guar_ptier(19.99e6) == "10to20"
    assert fm._guar_ptier(20e6) == "20to50"
    assert fm._guar_ptier(49.99e6) == "20to50"
    assert fm._guar_ptier(50e6) == "ge50"


def test_select_recal_routing():
    # Tuples (RECAL_MODE "shift") pass through untouched.
    line = (0.12, 1.0)
    assert fm._select_recal(line, 30e6, "SP") is line
    assert fm._select_recal(None, 30e6, "SP") is None
    # shift_ptier dicts key on the ptier of the RAW predicted guarantee,
    # the conditioning the intercepts were fit under.
    rc = {"_mode": "shift_ptier", "_pooled": (0.10, 1.0),
          "lt10": (0.01, 1.0), "ge50": (0.25, 1.0)}
    assert fm._select_recal(rc, 5e6, "SP") == (0.01, 1.0)
    assert fm._select_recal(rc, 60e6, "POS") == (0.25, 1.0)
    # A tier without its own intercept rides the pooled shift.
    assert fm._select_recal(rc, 30e6, "SP") == (0.10, 1.0)
    # fit_group dicts still key on the position group.
    rg = {"_pooled": (0.10, 1.0), "SP": (0.02, 0.9)}
    assert fm._select_recal(rg, 30e6, "SP") == (0.02, 0.9)
    assert fm._select_recal(rg, 30e6, "RP") == (0.10, 1.0)


def test_artifact_ptier_no_overshoot():
    # E5a standing check: no tier's guarantee bias may exceed +10 $M.
    g = _gate2()["pooled_by_pos_group"]
    tiers = ("lt10", "10to20", "20to50", "ge50")
    for t in tiers:
        cell = g[f"guarantee:ptier:{t}"]
        assert cell["n"] > 0
        assert cell["bias_model"] <= 10.0, (
            f"ptier {t} bias_model {cell['bias_model']:+.3f} overshoots the "
            "E5a +10 $M cap; any level-family ship must repeat this check")


def test_artifact_generated_at():
    d = _gate2()
    ga = d.get("generated_at")
    assert isinstance(ga, str) and len(ga) == 20 and ga.endswith("Z"), (
        "fa_gate2_eval.json lost generated_at; run_market_gate(persist=True) "
        "writes the summary wholesale, so a re-persist owes the stamp")


def test_verdict_edges_consistent():
    ve = _gate2().get("verdict_edges")
    assert ve, (
        "fa_gate2_eval.json lost the verdict_edges block; a re-persist owes "
        "it (docs/fa-2026-08-19/PTIER_LEVEL_GATE.md section 4b)")
    assert ve["band_mode"] == fm.VERDICT_BAND_MODE == "group"
    assert ve["pooled"]["overpay_max"] == fm.VERDICT_OVERPAY_MAX == 89
    assert ve["pooled"]["value_min"] == fm.VERDICT_VALUE_MIN == 198
    assert {k: tuple(v) for k, v in ve["group"].items()} \
        == fm.VERDICT_GROUP_EDGES
    recut = ve["recut_2026_08_19"]
    assert recut["new_edges"] == [fm.VERDICT_OVERPAY_MAX, fm.VERDICT_VALUE_MIN]
    n = recut["n"]
    assert n == sum(recut["new_counts"].values())
    # The re-cut restores the 33/33/33 design on its own corpus.
    for band, cnt in recut["new_counts"].items():
        assert abs(cnt - n / 3.0) <= 0.02 * n, (
            f"re-cut band {band} holds {cnt} of {n}; the pooled edges no "
            "longer cut terciles on the corpus they were fit on")
    assert recut["verdict_flips"] >= 0


def test_gate_doc_no_pending():
    txt = GATE_DOC.read_text(encoding="utf-8")
    assert "PENDING" not in txt, (
        "the ptier gate doc still carries a PENDING section; results must "
        "be filled with verbatim lab output before this lane is closed")
    assert "NO SHIP" in txt and "shift_ptier" in txt

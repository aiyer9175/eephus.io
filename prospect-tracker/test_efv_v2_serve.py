# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DS-02: eFV V2 serves from one order index (docs/efv-v2/DRIVER_SYSTEM_V2.md, bug B2).

What is pinned here:
  * on the served artifact, the board order of every V2-graded row (grade, then
    board_sort_key) IS the order of V2's order index, per side, with nothing out of
    place; the pricing grade and the odds grade are the served grade;
  * pitchers carry no driver chip unless the served fit admitted a pitcher driver
    (owner DS-Q2), and no v1 pitcher-block chip survives anywhere on the active board;
  * the board's claim is derived from data/efv_progress.json and never hardcoded;
  * the production fit reads no reserved row;
  * the fingerprint names the served model, and the Source Comparison scores it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import efv_v2_serve as S

ROOT = Path(__file__).parent
DATA = ROOT / "data"


def _xfv():
    p = DATA / "xfv.json"
    if not p.exists():
        pytest.skip("data/xfv.json not built on this machine")
    return json.loads(p.read_text(encoding="utf-8"))


def _v2_rows(doc):
    return {k: e for k, e in doc["by_player"].items()
            if e.get("kind") == "active" and e.get("grade_basis") == S.GRADE_BASIS}


# ---------------------------------------------------------------------------
# one order index, on the served artifact
# ---------------------------------------------------------------------------

def test_the_artifact_serves_v2():
    doc = _xfv()
    if not S.enabled():
        pytest.skip("eFV V2 is switched off")
    assert doc["meta"]["served_model"]["model_id"] == S.SERVED_MODEL_ID
    assert _v2_rows(doc), "no active row is V2-graded"


def test_board_order_equals_the_order_index_on_every_row():
    doc = _xfv()
    rows = _v2_rows(doc)
    if not rows:
        pytest.skip("no V2-graded rows")
    for side in ("H", "P"):
        sub = [(k, e) for k, e in rows.items() if e["side"] == side]
        board = [k for k, _ in sorted(sub, key=lambda kv: (-kv[1]["xfv_grade"],
                                                             -kv[1]["board_sort_key"], kv[0]))]
        idx = [k for k, _ in sorted(sub, key=lambda kv: (-kv[1]["efv_v2"]["order_idx"], kv[0]))]
        assert board == idx, f"{side}: the board order is not the order index"
        # the card's "#N by eFV" is the row's place in that same order
        assert [rows[k]["efv_v2"]["order_rank"] for k in board] == list(range(1, len(board) + 1))
    census = doc["meta"]["serve_vs_eval_census"]["v2_board_order"]
    for side, blk in census.items():
        assert blk["board_order_equals_order_index"] is True
        assert blk["rows_out_of_place"] == 0


def test_sort_key_pricing_grade_and_odds_grade_are_the_one_number():
    rows = _v2_rows(_xfv())
    if not rows:
        pytest.skip("no V2-graded rows")
    for k, e in rows.items():
        assert e["board_sort_key"] == pytest.approx(e["efv_v2"]["order_idx"], abs=1e-9), k
        assert e["xfv_grade_quantile"] == e["xfv_grade"], k          # prices surplus
        assert abs(e["xfv_grade_odds"] - e["xfv_grade"]) <= 0.05 + 1e-9, k   # keys the odds
        assert e.get("rank_war") is None, k                           # no v1 blend served


def test_within_a_side_the_grade_never_falls_as_the_order_index_rises():
    rows = _v2_rows(_xfv())
    if not rows:
        pytest.skip("no V2-graded rows")
    for side in ("H", "P"):
        sub = sorted((e for e in rows.values() if e["side"] == side),
                     key=lambda e: e["efv_v2"]["order_idx"])
        g = [e["xfv_grade"] for e in sub]
        assert all(a <= b for a, b in zip(g, g[1:])), side


# ---------------------------------------------------------------------------
# chips (owner DS-Q2)
# ---------------------------------------------------------------------------

def test_no_v1_pitcher_block_chip_survives_on_the_active_board():
    import efv_score as E
    doc = _xfv()
    if doc["meta"].get("served_model", {}).get("model_id") != S.SERVED_MODEL_ID:
        pytest.skip("eFV V2 is not the served model")
    block = {E._FACTOR_LABELS[k] for k in ("peak_k_rel", "bb_rel", "x_era_k", "tool_fb",
                                           "age", "age_rel_level", "k_rel", "era_rel",
                                           "peak_bb_rel", "tool_cmd", "tool_sl", "tool_ch",
                                           "tool_cb")}
    bad = [(k, f["label"]) for k, e in doc["by_player"].items()
           if e.get("kind") == "active" and e.get("side") == "P"
           and e.get("grade_basis") == S.GRADE_BASIS
           for f in (e.get("factors") or []) if f.get("label") in block]
    assert not bad, bad[:5]


def test_pitcher_driver_chips_only_for_admitted_pitcher_drivers():
    doc = _xfv()
    rec = (doc["meta"].get("served_model") or {}).get("receipt") or {}
    if not rec:
        pytest.skip("no served-model receipt")
    pit = rec["pit"]
    admitted = set()
    if pit["w_skill"] > 0 and pit.get("skill"):
        admitted |= set(pit["skill"]["keys"])
    if pit["w_time"] > 0 and pit.get("timing"):
        admitted |= set(pit["timing"]["keys"])
    for k, e in _v2_rows(doc).items():
        if e["side"] != "P":
            continue
        for f in e.get("factors") or []:
            if f.get("on_grade") is False:
                continue                      # a DS-11 overlay note, never a grade move
            assert f.get("driver") in admitted, (k, f)


def test_driver_chips_are_in_percentile_points_and_clear_the_floor():
    for k, e in _v2_rows(_xfv()).items():
        for f in e.get("factors") or []:
            if f.get("on_grade") is False:
                continue
            assert f["unit"] == "percentile points"
            assert f["mag"] >= S.CHIP_FLOOR_PCT - 1e-9, (k, f)


# ---------------------------------------------------------------------------
# the claim is derived, never written
# ---------------------------------------------------------------------------

def _prog(rows, head="vm"):
    return {"headline_frame": head,
            "frames": {"vm": {"label": "Vintage-matched"}, "lv_res": {"label": "List vintage, reserved"}},
            "rows": rows}


def _row(delta, ci, res, *, frame="vm", role="headline", trigger="nightly", model="efv_v2"):
    return {"model_id": model, "frame": frame, "role": role, "trigger": trigger,
            "n": 800, "date": "2026-09-25", "resolvable": res,
            "deltas": {"vs_prospx_consensus": {"spearman": {"delta": delta, "ci95": ci}}}}


def test_claim_words_follow_the_ledger():
    assert S.served_claim(_prog([]))["word"] == "not yet scored"
    assert S.served_claim(_prog([_row(-0.004, [-0.02, 0.01], False)]))["word"] == "ties"
    assert S.served_claim(_prog([_row(-0.03, [-0.05, -0.01], True)]))["word"] == "trails"
    # a lead on a spent headline frame is not a reserved read
    assert S.served_claim(_prog([_row(0.03, [0.01, 0.05], True)]))["word"] == "ties"
    look = _row(0.03, [0.01, 0.05], True, frame="lv_res", role="reserved", trigger="look")
    assert S.served_claim(_prog([_row(-0.004, [-0.02, 0.01], False), look]))["word"] == "leads"
    # another model's rows never speak for the served one
    assert S.served_claim(_prog([_row(-0.03, [-0.05, -0.01], True, model="efv_v1")]))[
        "word"] == "not yet scored"


def test_claim_numbers_are_copied_from_the_row():
    c = S.served_claim(_prog([_row(-0.0057, [-0.0231, 0.0116], False)]))
    assert c["delta"] == -0.0057 and c["ci95"] == [-0.0231, 0.0116] and c["n"] == 800
    assert "-0.0057" in c["text"] and c["source"] == "data/efv_progress.json"


def test_the_served_claim_equals_the_ledger_derivation():
    doc = _xfv()
    sm = doc["meta"].get("served_model") or {}
    if sm.get("model_id") != S.SERVED_MODEL_ID:
        pytest.skip("eFV V2 is not the served model")
    prog = json.loads((DATA / "efv_progress.json").read_text(encoding="utf-8"))
    derived = S.served_claim(prog)
    for k in ("word", "delta", "ci95", "n", "run_id", "frame"):
        assert sm["claim"].get(k) == derived.get(k), k


def test_no_page_hardcodes_the_claim():
    for rel in ("prospx/index.html", "assets/glossary.js"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert not re.search(r"ties (PROSPX )?consensus", src, re.I), rel


# ---------------------------------------------------------------------------
# the scored object and the fit
# ---------------------------------------------------------------------------

def test_served_score_breaks_only_exact_grade_ties_by_the_order_index():
    s = S.served_score([45.0, 45.0, 50.0, 40.0], [0.30, 0.70, 0.10, 0.99])
    order = sorted(range(4), key=lambda i: s[i])
    assert order == [3, 0, 1, 2]
    with pytest.raises(ValueError):
        S.served_score([45.0, 45.0000001], [1.0, -1.0])


def test_production_fit_reads_no_reserved_row():
    import efv_vintage_frame as F
    models = S.production_models()
    for side, m in models.items():
        assert max(m["train_years"]) < F.R_VM_FIRST_DEBUT_YEAR, side
        assert m["frame"] == "vm"


def test_pitchers_take_the_consensus_order_when_no_pitcher_driver_is_admitted():
    m = S.production_models()["pit"]
    import efv_v2_model as H
    if H.head_usable(m.get("skill")):
        pytest.skip("a pitcher skill driver is admitted on this fit")
    assert m["consensus_only"] is True
    assert m["w_skill"] == 0.0 and m["w_time"] == 0.0


def test_fingerprint_names_the_served_model(monkeypatch):
    import storage
    assert storage.board_basis_fingerprint().split("|")[-1] == "served=" + S.fingerprint_term()
    monkeypatch.setenv("EEPHUS_SERVE_EFV_V2", "0")
    assert S.fingerprint_term() == "efv_v1"
    assert storage.board_basis_fingerprint().endswith("|served=efv_v1")


def test_source_comparison_scores_the_served_model():
    p = DATA / "source_backtest.json"
    if not p.exists():
        pytest.skip("data/source_backtest.json not built")
    acc = json.loads(p.read_text(encoding="utf-8")).get("accuracy") or {}
    obj = acc.get("efv_scored_object") or {}
    if not S.enabled():
        pytest.skip("eFV V2 is switched off")
    assert obj.get("model_id") == S.SERVED_MODEL_ID
    prog = json.loads((DATA / "efv_progress.json").read_text(encoding="utf-8"))
    head = [r for r in prog["rows"] if r.get("frame") == prog.get("headline_frame")]
    assert head and head[-1]["model_id"] == S.SERVED_MODEL_ID


def test_the_module_groups_nothing_by_consensus_fv_level():
    src = (ROOT / "efv_v2_serve.py").read_text(encoding="utf-8")
    assert not re.search(r"(groupby|by_fv|fv_cell|per_fv|fv_bucket)", src)

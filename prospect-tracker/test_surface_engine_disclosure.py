"""Each surface serves the engine that won its own gate, and says so from artifacts.

Owner answer M15-1 (2026-09-25, "use whichever model wins"): /projections/ serves
the ML heads that beat the Marcel champion on the player-level holdout, /fa/
prices on the champion path its market model passed Gate 2 on. Both pages
disclose it, and both disclosures must read the committed eval artifacts
(data/proj_horizon_eval.json, data/fa_gate2_eval.json): the sentence they
replace, "ML paths failed the Gate 2 market test", rested on a 2026-06-11
measurement no artifact carries.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import proj_export as pe

ROOT = Path(__file__).resolve().parent
MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

HE = {"generated_at": "2026-08-19T22:08:36Z", "challenger_blocks": {
    "holdout_2022_2024": {"horizons": {
        "1": {"n": 6611, "mae": 0.5394}, "2": {"n": 5000, "mae": 0.4862}}},
    "holdout_2022_2024_champion": {"horizons": {
        "1": {"n": 6611, "mae": 0.6179}, "2": {"n": 5000, "mae": 0.4800}}}}}
G2 = {"generated_at": "2026-10-08T23:11:22Z", "war_provider": "fwar", "pass": True,
      "pooled": {"guarantee": {"mae_model": 9.8524, "mae_base": 10.7358, "n": 1199},
                 "aav": {"mae_model": 3.12, "mae_base": 3.19, "n": 1199},
                 "mega_guarantee": {"mae_model": 81.6, "mae_base": 97.2, "n": 50}}}


def _fake(name):
    return {"proj_horizon_eval.json": HE, "fa_gate2_eval.json": G2}.get(name, {})


def test_the_block_copies_both_artifacts(monkeypatch):
    monkeypatch.setattr(pe, "_read_data_json", _fake)
    se = pe._accountability_block()["surface_engines"]
    p, f = se["projections"], se["fa"]
    assert p["engine"] == "proj_lgbm_v1" and p["comparator"] == "marcel_decay_v2"
    assert p["artifact"] == "data/proj_horizon_eval.json"
    assert p["generated_at"] == HE["generated_at"]
    assert p["by_horizon"] == [{"h": 1, "n": 6611, "mae": 0.5394, "mae_comparator": 0.6179},
                               {"h": 2, "n": 5000, "mae": 0.4862, "mae_comparator": 0.48}]
    assert f["artifact"] == "data/fa_gate2_eval.json" and f["pass"] is True
    assert f["pooled"]["guarantee"] == {"mae_model": 9.8524, "mae_base": 10.7358, "n": 1199}
    assert "mega_guarantee" not in f["pooled"]
    assert "use_ml=False" in f["input"]


def test_absent_artifacts_disclose_nothing(monkeypatch):
    monkeypatch.setattr(pe, "_read_data_json", lambda name: {})
    se = pe._accountability_block()["surface_engines"]
    assert se["projections"] is None and se["fa"] is None


def test_the_block_matches_the_committed_artifacts():
    se = pe._accountability_block()["surface_engines"]
    he = json.loads((ROOT / "data" / "proj_horizon_eval.json").read_text(encoding="utf-8"))
    g2 = json.loads((ROOT / "data" / "fa_gate2_eval.json").read_text(encoding="utf-8"))
    cb = he["challenger_blocks"]
    for row in se["projections"]["by_horizon"]:
        h = str(row["h"])
        assert row["mae"] == cb["holdout_2022_2024"]["horizons"][h]["mae"]
        assert row["mae_comparator"] == cb["holdout_2022_2024_champion"]["horizons"][h]["mae"]
    assert se["fa"]["pass"] == g2["pass"]
    for k, v in se["fa"]["pooled"].items():
        assert v["mae_model"] == g2["pooled"][k]["mae_model"]
        assert v["mae_base"] == g2["pooled"][k]["mae_base"]


# ---------------------------------------------------------------------------
# /projections/: the board fold and the card's FA block
# ---------------------------------------------------------------------------
def _board_with(se):
    import test_projections_smoke as S
    bd = json.loads(S.BOARD)
    bd["first_season"] = 2027
    if se is not None:
        bd["accountability"] = {"surface_engines": se}
    return S, json.dumps(bd)


def _se():
    return {"projections": {"engine": "proj_lgbm_v1", "comparator": "marcel_decay_v2",
                            "frame": "2022-2024 holdout", "generated_at": "2026-08-19T22:08:36Z",
                            "by_horizon": [{"h": 1, "mae": 0.5394, "mae_comparator": 0.6179},
                                           {"h": 2, "mae": 0.4862, "mae_comparator": 0.5477}]},
            "fa": {"pass": True, "generated_at": "2026-10-08T23:11:22Z",
                   "pooled": {"guarantee": {"mae_model": 9.8524, "mae_base": 10.7358, "n": 1199}}}}


def _render(S, board, hash_):
    base = S.BOARD
    try:
        S.BOARD = board
        return S._render_all(hash_)
    finally:
        S.BOARD = base


def test_the_board_fold_reads_both_verdicts_from_the_payload():
    S, board = _board_with(_se())
    fold = _render(S, board, "")["proj-banner"].split('<details class="proj-how">', 1)[1]
    assert ("proj_lgbm_v1 serves here: it is ahead of marcel_decay_v2 at every scored horizon "
            "of the 2022-2024 holdout (year 1 MAE 0.539 against 0.618, measured 2026-08-19).") in fold
    assert ("/fa/ keeps the champion path, the input its market model passed "
            '<span data-gl="fa_gates">Gate 2</span> on (guarantee MAE $9.85M against $10.74M '
            "for its baseline, n 1,199, measured 2026-10-08).") in fold


def test_a_lost_horizon_and_a_failing_gate_are_printed_as_such():
    se = _se()
    se["projections"]["by_horizon"][1]["mae"] = 0.60
    se["fa"]["pass"] = False
    S, board = _board_with(se)
    fold = _render(S, board, "")["proj-banner"]
    assert "ahead of marcel_decay_v2 at 1 of 2 scored horizons" in fold
    assert "the input its market model is failing" in fold


def test_no_block_no_claim():
    S, board = _board_with(None)
    out = _render(S, board, "")
    assert "serves here" not in out["proj-banner"] and "Gate 2" not in out["proj-banner"]


def test_the_card_fa_block_reads_the_gate_and_drops_the_unbacked_claim():
    S, board = _board_with(_se())
    d = json.loads(S.DETAIL)
    d["players"]["vet_guy"]["fa"] = {
        "status": "FA 2027", "projYears": 7, "projGuar": 150000000, "projAav": 21000000,
        "warPath": [4.25, 3.75, 3.25, 2.71, 2.08], "warTotal": 16.0}
    base_d = S.DETAIL
    try:
        S.DETAIL = json.dumps(d)
        html = _render(S, board, "#player=vet_guy&ptab=projection")["proj-rows"]
    finally:
        S.DETAIL = base_d
    note = html.split("data-fa-pricing-path", 1)[1].split("</div>", 1)[0]
    assert "/fa/ keeps the champion path, the input its market model passed" in note
    assert "$9.85M against $10.74M" in note
    src = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
    assert "ML paths failed" not in src


# ---------------------------------------------------------------------------
# /fa/: the season panel
# ---------------------------------------------------------------------------
def _fa_clause_fn():
    src = (ROOT / "assets" / "fa.js").read_text(encoding="utf-8")
    m = re.search(r"\n  function championGateClause\(meta\) \{\n.*?\n  \}\n", src, re.S)
    assert m, "championGateClause is not a top-level function of fa.js"
    return src, m.group(0)


def test_the_fa_season_note_reads_gate_2_from_fa_meta():
    src, fn = _fa_clause_fn()
    assert "${championGateClause(D.fa_meta)}" in src
    assert "ML paths failed" not in src
    ctx = MiniRacer()
    ctx.eval("function esc(s){return String(s);}" + fn)
    meta = {"gate2": G2}
    out = ctx.eval(f"championGateClause({json.dumps(meta)})")
    assert out == (' The market model passed <span data-gl="fa_gates">Gate 2</span> on it '
                   "(guarantee MAE $9.85M against $10.74M for its baseline, n 1,199, "
                   "measured 2026-10-08).")
    meta["gate2"] = {**G2, "pass": False}
    assert "is failing" in ctx.eval(f"championGateClause({json.dumps(meta)})")
    assert ctx.eval("championGateClause({})") == ""
    assert ctx.eval("championGateClause(null)") == ""


def test_the_glossary_carries_no_unbacked_gate_2_claim():
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    e = next(x for x in g["entries"] if x["id"] == "fa_projection_engine")
    text = json.dumps(e)
    assert "failed Gate 2" not in text
    assert "won its own gate" in text

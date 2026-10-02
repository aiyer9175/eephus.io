# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""RBE01, RBE02, RBE03 (2026-10-02): the served copy of the gate state once
the vintage sample is past its bar.

With 777 vintage-graded games against 600 needed, /betting/ printed
'Short by -177 games' on Clock A, blamed the OPEN vintage_sample gate in the
'Why nothing is here' headline, and wrote '777 of the 600' in the record
label, the topline under the slots and the header chip. The closed gate is
graded_price_history. These tests run over the SERVED artifacts
(data/betting.json, data/betting_model_eval.json, data/betting_learning.json)
through the exporter's own label builder and through assets/betting.js in
py_mini_racer, so they hold for whatever the artifacts say on the day they
run, below the bar as well as past it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import betting_export as be  # noqa: E402

tb = pytest.importorskip("test_betting")

DATA = ROOT / "data"
OF_THE = re.compile(r"(\d+) of the (\d+)")
CHIP_OF = re.compile(r"vintage graded (\d+) of (\d+)")
SLOT_KEYS = ("pick_of_the_day", "best_value", "longshot", "ev_rank")


def _load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def served():
    return {"main": _load("betting.json"), "evald": _load("betting_model_eval.json"),
            "learning": _load("betting_learning.json")}


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _ctx(payload: dict, served: dict):
    return tb._ctx(tb._fetch_js(main=json.dumps(payload),
                                evald=json.dumps(served["evald"]),
                                learning=json.dumps(served["learning"])))


def _vintage(served) -> tuple[int, int]:
    prog = be.honest_backtest_progress(served["evald"])
    return prog["n_graded"], prog["n_needed"]


# ---------------------------------------------------------------------------
# 1. the record label, built from the served artifacts
# ---------------------------------------------------------------------------
def test_the_served_record_label_never_reads_n_of_the_m_past_the_bar(served):
    meta = served["main"].get("pick_meta") or {}
    label = be.provisional_record_label(
        served["evald"], min_edge=float(meta.get("min_edge") or be.PROVISIONAL_MIN_EDGE),
        provisional=True)
    n, need = _vintage(served)
    for a, b in OF_THE.findall(label):
        assert int(a) < int(b), label
    if n is not None and need is not None and n >= need:
        assert f"{n} graded, past the {need} games" in label
        closed = [g["id"] for g in served["evald"]["min_edge_gate"]["gates"]
                  if g.get("open") is False]
        for gid in closed:
            assert gid in label, (gid, label)
        assert "vintage_sample gate is closed" not in label


def test_the_label_below_the_bar_is_unchanged():
    evald = {"vintage": {"n_graded": 211, "min_graded_games_for_min_edge": 600}}
    txt = be.provisional_record_label(evald, min_edge=0.06, provisional=True)
    assert "211 of the 600 games the honest backtest needs are graded" in txt


def test_the_label_past_the_bar_names_every_closed_gate():
    gates = [{"id": "vintage_sample", "open": True},
             {"id": "out_of_sample_skill", "open": False},
             {"id": "graded_price_history", "open": False}]
    evald = {"vintage": {"n_graded": 777, "min_graded_games_for_min_edge": 600},
             "min_edge_gate": {"gates": gates}}
    txt = be.provisional_record_label(evald, min_edge=0.06, provisional=True)
    assert ("777 graded, past the 600 games the honest backtest needs, but the "
            "out_of_sample_skill and graded_price_history gates are closed") in txt
    assert "777 of the 600" not in txt
    assert txt.startswith("Provisional.") and txt.endswith("Recorded before the result.")
    # at exactly the bar the count is met, not short
    evald["vintage"]["n_graded"] = 600
    assert "600 graded, past the 600" in be.provisional_record_label(
        evald, min_edge=0.06, provisional=True)


# ---------------------------------------------------------------------------
# 2. Clock A and the no-selection headline, rendered from the served payload
# ---------------------------------------------------------------------------
def test_clock_a_short_by_is_never_negative_on_the_served_payload(served):
    c = _ctx(served["main"], served)
    copy = _text(c.eval("__show('validation')"))
    m = re.search(r"Short by (-?\d+) games", copy)
    assert m, copy[:400]
    assert int(m.group(1)) >= 0
    n, need = _vintage(served)
    if n >= need:
        assert "Short by 0 games (met)" in copy


def test_the_no_selection_headline_names_a_closed_gate(served):
    payload = json.loads(json.dumps(served["main"]))
    for k in SLOT_KEYS:
        if k in payload:
            payload[k] = None
    gates = ((payload.get("model") or {}).get("validation") or {}).get("gate", {}).get("gates") or []
    closed = [g["id"] for g in gates if g.get("open") is False]
    c = _ctx(payload, served)
    copy = _text(c.eval("__show('potd')"))
    m = re.search(r"No selection: ([^.]*\.)", copy)
    assert m, copy[:600]
    head = m.group(1)
    if not closed:
        assert "no minimum edge has been measured" in head
        return
    if closed[0] == "vintage_sample":
        assert "vintage-graded games exist" in head, head
    else:
        assert closed[0] in head, head
        assert "vintage-graded games exist" not in head, head


# ---------------------------------------------------------------------------
# 3. the header chip and the topline take the same branch
# ---------------------------------------------------------------------------
def test_the_chip_and_topline_follow_the_label_branch(served):
    c = _ctx(served["main"], served)
    potd = _text(c.eval("__show('potd')"))
    banner = _text(c.eval("__html['betting-banner'] || ''"))
    n, need = _vintage(served)
    if n >= need:
        assert f"vintage graded {n}, past {need} needed" in banner, banner
        assert CHIP_OF.search(banner) is None, banner
        assert f"has graded {n} games, past the {need} needed" in potd
        assert f"{n} of the {need}" not in potd
    else:
        assert f"vintage graded {n} of {need}" in banner, banner
        assert f"has graded {n} of the {need} games needed" in potd


def test_the_chip_below_the_bar_keeps_n_of_m(served):
    payload = json.loads(json.dumps(served["main"]))
    vin = payload["model"]["validation"]["vintage"]
    vin["n_graded"] = 211
    c = _ctx(payload, served)
    banner = _text(c.eval("__html['betting-banner'] || ''"))
    assert "vintage graded 211 of " in banner, banner

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the report-extraction read (efv_w2_report_read.py,
EFV4_REPORT_LLM_EXTRACTION). Fixtures only: no frame build, no label file, no model.

1. Heads: a grade-side column goes to the skill head only when its side's
   report_absent probe reads BALANCED; timing columns stay in the timing head.
2. The invariance control: a field the names-in run reads like the redacted run is
   kept; one whose names-in partial moves (point outside the CI95, or a paired
   difference whose CI95 excludes zero) is withheld.
3. The v3 column table is widened only inside a read and restored after it.
4. Ledger documents: development frames only, one per (arm, frame), never a spent
   frame; the summary labels spent rows.
5. Bans: no FV-level grouping token, no network or served-exporter import, no
   em-dash; the spent note is the registered string.
"""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np

import efv_w2_report_llm as R
import efv_w2_report_read as RR

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "efv_w2_report_read.py"


# 1. heads -----------------------------------------------------------------------------

def test_heads_follow_the_report_absent_probe():
    arms = RR.resolve_heads({"hit": {"verdict": "IMBALANCED"},
                             "pit": {"verdict": "BALANCED"}})
    by = {a["name"]: a for a in arms}
    assert by["rpt_risk_hit"]["head"] == "timing" and "head_note" in by["rpt_risk_hit"]
    assert by["rpt_risk_pit"]["head"] == "skill"
    assert by["rpt_arrival_pit"]["head"] == "timing"
    assert by["rpt_role_floor_hit"]["head"] == "timing"
    none = RR.resolve_heads({})
    assert all(a["head"] == "timing" for a in none)
    assert len(arms) == len(R.ARMS) == 22
    assert all(a["head"] in ("skill", "timing") for a in R.ARMS)


# 2. the invariance control --------------------------------------------------------------

def _store_fixture(n=120, leak=False, seed=3):
    rng = np.random.default_rng(seed)
    frames = {"hit": {}, "pit": {}}
    main, ctl, inv = [], [], []
    rows_by_v: dict = {}
    for i in range(n):
        V = 2015 + i % 3
        pk = f"p{i}"
        w3 = float(rng.normal())
        cons = float(rng.normal())
        rows_by_v.setdefault(V, []).append(
            ({"player_key": pk, "grades": {R.CONSENSUS_KEY: cons}}, {"w3": w3}))
        risk = int(rng.integers(1, 6))
        raw_risk = (5 if w3 > 0 else 1) if leak else risk
        did, cid = f"d{i}", "c" + f"{i:016d}"
        main.append({"doc_id": did, "control_id": None, "prompt_sha256": R.PROMPT_SHA,
                     "model_id": "m-1", "fields": _fields(risk=risk)})
        ctl.append({"doc_id": f"raw{i}", "control_id": cid, "prompt_sha256": R.PROMPT_SHA,
                    "model_id": "m-1", "fields": _fields(risk=raw_risk)})
        inv.append({"side": "pit", "vintage": V, "player_key": pk, "paired_doc_id": did,
                    "control_id": cid})
    for V, pairs in rows_by_v.items():
        frames["pit"][V] = ([p[0] for p in pairs], [p[1] for p in pairs])
    man = {"rows": [], "controls": {"invariance": inv, "shuffle": []}}
    return RR.Store(manifest=man, store=main + ctl), frames


def _fields(**kw):
    f = {"conviction": 3, "hedge_count": 1, "risk": 3, "injury_mention": "none",
         "makeup": 0, "body_projection": 0, "role_ceiling": 3, "role_floor": None,
         "reliever_risk": 2, "approach_concern": None, "writer_level": 4, "arrival": 0}
    f.update(kw)
    return f


def test_invariance_keeps_an_identical_reading():
    store, frames = _store_fixture(leak=False)
    out = RR.invariance_outcome(store, frames, B=200)
    risk = out["fields"]["risk"]
    assert out["n_scored"] == 120 and risk["diff"] == 0.0 and risk["withheld"] is False
    assert out["fields"]["role_floor"]["withheld"] is False
    assert RR.withheld_columns(out) == set()


def test_invariance_withholds_a_names_in_shift():
    store, frames = _store_fixture(leak=True)
    out = RR.invariance_outcome(store, frames, B=200)
    risk = out["fields"]["risk"]
    assert risk["withheld"] is True
    assert risk["names_in_outside_ci"] or risk["diff_ci_excludes_zero"]
    assert "txt_risk" in RR.withheld_columns(out)


# 3. the v3 menu ------------------------------------------------------------------------

def test_registered_columns_restores_the_v3_menu():
    import efv_v3 as V3
    before = dict(V3.W2_COLUMNS)
    arms = RR.resolve_heads({"pit": {"verdict": "BALANCED"}})
    with RR.registered_columns(arms):
        assert V3.W2_COLUMNS["rpt_risk_pit"]["head"] == "skill"
        assert V3.W2_COLUMNS["rpt_risk_hit"]["head"] == "timing"
        cfg = V3.base_config()
        cfg["add"]["pit"]["skill"].append("rpt_risk_pit")
        V3.validate_config(cfg)
    assert V3.W2_COLUMNS == before


# 4. ledger documents -------------------------------------------------------------------

def _arm_block(n):
    return {"name": n, "admitted_folds": 1, "n_folds": 3,
            "frame": {"n": 10, "deltas": {"candidate_vs_efv_v2_base": {
                "spearman": {"delta": 0.001, "ci95": [-0.01, 0.01]}},
                "candidate_vs_prospx_consensus": {"spearman": {"delta": -0.01,
                                                               "ci95": [-0.05, 0.03]}}}}}


def test_ledger_docs_are_development_only():
    doc = {"generated_at": "2026-10-09T00:00:00Z",
           "arms_declared": [{"name": "rpt_risk_pit", "field_column": "txt_risk",
                              "side": "pit", "head": "skill"},
                             {"name": "rpt_role_ceiling_pit",
                              "field_column": "txt_role_ceiling", "side": "pit",
                              "head": "skill", "withheld": "invariance"}],
           "lv_dev": {"arms": {"rpt_risk_pit": _arm_block("rpt_risk_pit")}},
           "vm_dev": {"arms": {"rpt_risk_pit": _arm_block("rpt_risk_pit")}},
           "spent": {"frames": {"lv_res": {"arms": {"rpt_risk_pit":
                                                    _arm_block("rpt_risk_pit")}}}}}
    docs = RR.ledger_docs(doc)
    assert [list(d["frames"]) for d in docs] == [["lv_dev"], ["vm_dev"]]
    assert all(d["role"] == "development" and d["screening"]["selects"] is False
               and d["screening"]["head"] == "skill" for d in docs)
    assert docs[0]["model_id"] == "efv_v2_screen:wave2:rpt_risk_pit:pit"
    s = RR.summary(doc)
    assert s[0]["lv_res"]["note"] == RR.SPENT_NOTE
    assert s[1]["withheld"] == "invariance" and "lv_dev" not in s[1]


# 5. bans -------------------------------------------------------------------------------

_BANNED_TOKENS = ("groupby", "tier", "bucket", "stratum", "strata", "by_fv", "fv_band",
                  "fv_bin", "by_consensus", "per_fv", "per_consensus")
_BANNED_IMPORTS = ("urllib", "requests", "http", "anthropic", "socket", "backtest",
                   "efv_export", "proj_export")


def test_no_fv_level_grouping_no_network_no_dash():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else node.attr
                if isinstance(node, ast.Attribute) else node.name
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else node.arg
                if isinstance(node, ast.arg) else None)
        if name:
            assert not any(t in name.lower() for t in _BANNED_TOKENS), name
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
            for mname in mods:
                assert not any(mname.split(".")[0] == b for b in _BANNED_IMPORTS), mname
        if isinstance(node, ast.Compare) and "fv" in ast.unparse(node).lower():
            assert not any(isinstance(n, ast.Constant) and type(n.value) in (int, float)
                           for n in ast.walk(node)), ast.unparse(node)
    for p in (SRC, Path(__file__)):
        txt = p.read_text(encoding="utf-8")
        assert chr(0x2014) not in txt and chr(0x2013) not in txt
    assert RR.SPENT_NOTE == "spent frame, read after the 10-08 confirmation"
    assert RR.OUT_PATH.as_posix().endswith("data/_labs/efv_w2/efv_w2_report_llm.json")


def test_invariance_is_deterministic():
    store, frames = _store_fixture(leak=False)
    a = RR.invariance_outcome(store, frames, B=50)
    b = RR.invariance_outcome(store, frames, B=50)
    assert a == b

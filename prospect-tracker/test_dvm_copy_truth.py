# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DvM+ copy truth (DVM-0, final-pass Part 8 queue task Q10_03).

The DvM+ family's copy had drifted from the code it describes: the Ledger said
$DvM+ is "clamped 40-160" (the clamp was removed 2026-07-29), the farm
Development tab named 6y as the principal window (it is 7y) and printed blend
weights the code no longer runs (70/30, 50/30/20), Top movers called a
"since last real change" eFV step a trailing 1-year consensus delta, and the
glossary and registry carried the same stale facts. These tests pin the copy
to the code:

  * no "clamped" claim about $DvM+ while storage applies no clamp;
  * the Development arc panel names the principal window from the payload
    (farm_dev_spec), and the JS fallback equals storage's constants;
  * blend weights printed by the copy equal the constants the blend runs on;
  * Top movers names the delta basis from each row's payload;
  * the glossary and registry describe the math the code runs.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

import storage

ROOT = Path(__file__).resolve().parent
PROSPX = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
STORAGE_SRC = (ROOT / "storage.py").read_text(encoding="utf-8")
LEDGER_SRC = (ROOT / "ledger_export.py").read_text(encoding="utf-8")

# A positive clamp claim: "clamped" not preceded by "not"/"NOT" ("unclamped" never
# matches because \b needs a non-word character before the c).
_CLAMP_CLAIM = re.compile(r"(?<!not )(?<!NOT )\bclamped\b|\bIS clamped\b|clamped 40-160")


def _js_function(name: str) -> str:
    """Source of one top-level `function name(` in prospx/index.html, up to the
    next top-level function or const."""
    m = re.search(r"\nfunction " + re.escape(name) + r"\(", PROSPX)
    assert m, f"{name} not found in prospx/index.html"
    nxt = re.search(r"\n(?:function |const |// v\d)", PROSPX[m.end():])
    return PROSPX[m.start(): m.end() + (nxt.start() if nxt else 20000)]


def _py_block(src: str, start: str, end: str) -> str:
    i = src.index(start)
    return src[i: src.index(end, i)]


def _dollar_dvm_clamped() -> bool:
    """True when storage's $DvM+ pass clamps the published value."""
    block = _py_block(STORAGE_SRC, "_dollar_dvm_by_key: dict[str, float] = {}", "org_map: dict[str, dict] = {}")
    return bool(re.search(r"max\(\s*40|min\(\s*160", block))


def _ledger_copy_source() -> str:
    """The dvm_within_tier copy string as ledger_export.py writes it (the adjacent
    literals joined)."""
    m = re.search(r'"dvm_within_tier": \((.*?)\),\n', LEDGER_SRC, re.S)
    assert m, "dvm_within_tier copy key missing from ledger_export.py"
    return ast.literal_eval("(" + m.group(1) + ")")


def _glossary() -> dict:
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    return {e["id"]: e for e in g["entries"]}


def _registry() -> dict:
    r = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    return {m["model_id"]: m for m in r["models"]}


def _pct(x: float) -> str:
    """Python twin of prospx _farmPct: a 0-1 share as a percent string."""
    v = round(x * 1000) / 10
    return str(int(v)) if v == int(v) else str(v)


# ---------------------------------------------------------------- D-1 clamp


def test_storage_dollar_dvm_is_unclamped():
    assert not _dollar_dvm_clamped(), "a $DvM+ clamp is back: restore the copy that says so"


def test_no_clamped_claim_while_no_clamp_exists():
    if _dollar_dvm_clamped():
        pytest.skip("storage clamps $DvM+ again; the clamp claim would be true")
    texts = {"ledger_export.py dvm_within_tier": _ledger_copy_source()}
    board = ROOT / "data" / "ledger_board.json"
    if board.exists():
        served = json.loads(board.read_text(encoding="utf-8"))["copy"]["dvm_within_tier"]
        texts["served ledger_board copy"] = served
    gl = _glossary()
    for gid in ("fin_dollar_dvm", "dvm_plus"):
        texts[f"glossary {gid}"] = json.dumps(gl[gid], ensure_ascii=False)
    texts["registry dvm_plus_dollar"] = json.dumps(_registry()["dvm_plus_dollar"])
    for where, text in texts.items():
        assert not _CLAMP_CLAIM.search(text), f"{where} claims a $DvM+ clamp that storage does not apply"


def test_ledger_copy_says_unclamped_and_not_dollars():
    text = _ledger_copy_source()
    assert "no clamp" in text and "not a dollar figure" in text


# ------------------------------------------------- D-6 principal window, payload


def test_payload_spec_carries_the_code_constants():
    spec = storage.farm_dev_spec()
    assert spec["principal_window"] == storage.FARM_PRINCIPAL_WINDOW
    assert spec["dvm_blend"] == {
        "fv_tool_share": storage.FARM_DVM_FV_TOOL_SHARE,
        "statcast_share": storage.FARM_DVM_STATCAST_SHARE,
        "tool_share_in_slice": storage.FARM_DVM_TOOL_SHARE_IN_SLICE,
        "penalty_gap_start": storage.FARM_DVM_TOOL_PENALTY_GAP_START,
        "penalty_gap_cap": storage.FARM_DVM_TOOL_PENALTY_GAP_CAP,
        "tool_share_penalty_start": storage.FARM_DVM_TOOL_SHARE_PENALTY_START,
        "tool_share_penalty_cap": storage.FARM_DVM_TOOL_SHARE_PENALTY_CAP,
    }
    # Shares of the whole blend sum to 1.
    assert abs(storage.FARM_DVM_FV_TOOL_SHARE + storage.FARM_DVM_STATCAST_SHARE - 1.0) < 1e-9


def test_boot_payload_serializes_the_spec():
    # farm_dev_spec() takes the DvM+ difficulty arm's explainer block (None while the
    # arm is None, DVM-5), so the call may carry an argument.
    assert re.search(r'"farm_dev_spec":\s*farm_dev_spec\(', STORAGE_SRC), \
        "export_timeseries_json no longer writes farm_dev_spec into the boot payload"


def test_js_fallback_equals_storage_constants():
    body = _js_function("farmDevSpec")
    spec = storage.farm_dev_spec()
    m = re.search(r'principal_window:\s*"(\w+)"', body)
    assert m and m.group(1) == spec["principal_window"]
    for key, val in spec["dvm_blend"].items():
        mm = re.search(key + r":\s*([0-9.]+)", body)
        assert mm, f"fallback lacks {key}"
        assert float(mm.group(1)) == pytest.approx(val), f"fallback {key} {mm.group(1)} != storage {val}"
    assert "DATA.farm_dev_spec" in body, "the copy must prefer the payload's spec"


def test_arc_panel_names_principal_window_from_payload():
    body = _js_function("makeFarmDvmMultiWindowPanel")
    assert "farmDevSpec().principal_window" in body
    assert not re.search(r'cell\("6y"', body), "arc panel still types a 6y cell"
    assert "6y is the principal" not in PROSPX
    assert "6y is the default and principal" not in PROSPX


# ---------------------------------------------------- D-6 blend weights in copy


def test_blend_uses_the_named_constants():
    block = _py_block(STORAGE_SRC, "def _blend_dvm_3way(", "# Missing-axis fallbacks.")
    assert "FARM_DVM_FV_TOOL_SHARE" in block and "FARM_DVM_STATCAST_SHARE" in block
    assert not re.search(r"\b0\.75\b|\b0\.25\b", block.split('"""')[-1]), \
        "_blend_dvm_3way types a share instead of reading the constant"
    tw = _py_block(STORAGE_SRC, "def _adaptive_tool_weight(", "def _blend_dvm(")
    for name in ("FARM_DVM_TOOL_SHARE_IN_SLICE", "FARM_DVM_TOOL_PENALTY_GAP_START",
                 "FARM_DVM_TOOL_PENALTY_GAP_CAP", "FARM_DVM_TOOL_SHARE_PENALTY_START",
                 "FARM_DVM_TOOL_SHARE_PENALTY_CAP"):
        assert name in tw


def test_blend_weights_in_copy_equal_code():
    # No typed weight survives anywhere on the page.
    for stale in ("FV 50% / Tool 30% / Statcast 20%", "70% cohort Overall", "30% Tool DvM+",
                  "50% FVDvM+", "20% StatcastDvM+", "70/30 blend of cohort"):
        assert stale not in PROSPX, f"typed blend weight {stale!r} is back on the page"
    # Every surface that prints weights reads farmDevBlendCopy / farmDevBlendSentence.
    for fn in ("makeFarmDevCohortSplit", "makeFarmPosBucketGrades"):
        assert "farmDevBlend" in _js_function(fn), f"{fn} does not read the blend from the spec"
    assert "bar('FVDvM+',       farmDevBlendCopy().fv" in PROSPX
    # The arithmetic the JS runs gives the code's baseline split.
    b = storage.farm_dev_spec()["dvm_blend"]
    tool = b["fv_tool_share"] * b["tool_share_in_slice"]
    assert (_pct(b["fv_tool_share"] - tool), _pct(tool), _pct(b["statcast_share"])) == ("52.5", "22.5", "25")
    body = _js_function("farmDevBlendCopy")
    assert "b.fv_tool_share - tool" in body and "b.fv_tool_share * b.tool_share_in_slice" in body


def test_bucket_weights_in_copy_come_from_payload():
    body = _js_function("farmDevBucketWeights")
    assert "pos_buckets" in body and ".weight" in body


# ------------------------------------------------------------ D-6 Top movers


def test_top_movers_names_its_basis_from_the_payload():
    body = _js_function("makeFarmDevTopMovers")
    assert "stock || {}).basis" in body
    for stale in ("365d", "1-year FV delta", "Δ 1y", "nearest 365"):
        assert stale not in body, f"Top movers still says {stale!r}"
    m = re.search(r"const _FARM_MOVE_BASIS_COPY = \{(.*?)\};", PROSPX, re.S)
    assert m and "xfv:" in m.group(1) and "same_source:" in m.group(1)


# -------------------------------------------------------------- D-7 glossary


def test_glossary_entries_describe_the_math():
    gl = _glossary()
    dvm = json.dumps(gl["dvm_plus"], ensure_ascii=False)
    assert "FV_EXPECTED_WAR" in dvm and "eFV retrospective" in dvm
    # The step values the entry quotes come from the table.
    w = storage._fv_to_expected_war
    assert round(w(70) - w(60), 1) == 13.0 and round(w(50) - w(40), 1) == 2.5
    assert "13.0" in dvm and "2.5" in dvm
    dev = json.dumps(gl["farm_grade_development"], ensure_ascii=False)
    assert "regardless of starting grade" not in dev
    assert "weight 2" in dev and "75%" in dev and "25%" in dev
    tools = json.dumps(gl["tools_dvm_plus"], ensure_ascii=False)
    assert "not in farm_score" not in tools and "≈ +0.6" not in tools
    assert "feeds the Development leaves" in tools and "two standard deviations" in tools
    fin = json.dumps(gl["fin_dollar_dvm"], ensure_ascii=False)
    assert "surplus dollars" not in fin and "surplus-dollar" not in fin
    assert "reads no dollars" in fin


# -------------------------------------------------------------- D-8 registry


def test_registry_rows_name_the_principal_window():
    reg = _registry()
    pw = storage.FARM_PRINCIPAL_WINDOW
    for mid in ("dvm_plus_org", "tbs_farm"):
        text = json.dumps(reg[mid])
        assert f"{pw}DvM+" in text, f"{mid} does not name {pw}DvM+"
    org = reg["dvm_plus_org"]
    assert "6y 0.60" not in org["notes"] and "6yDvM+ also enters" not in org["notes"]
    assert "6yDvM+" not in org["champion"] and "1y / 3y / 6y" not in org["predicts"]
    assert "6yDvM+" not in reg["tbs_farm"]["champion"]
    assert "NOT clamped" in reg["dvm_plus_dollar"]["notes"]
    assert "surplus-dollar" not in reg["dvm_plus_dollar"]["predicts"]

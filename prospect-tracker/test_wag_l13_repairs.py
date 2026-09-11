# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""WAG input and copy repairs from audit L13 (2026-09-11). None is a model change.

L13-05  a measured zero MLB exposure reaches the gate as zero; a missing one stays
        missing and is flagged, so the two are no longer the same fact.
L13-18  the client refuses the FV-0 sentinel as a WAG baseline, as the server does.
L13-07  the outcome-bar tooltip no longer prints WAR bands the engine does not price at.
L13-13  the eFV label series is named from war_source, not typed as bWAR.
L13-14  the glossary WAG, WARWAG and farm entries describe the code that runs.
L13-15  the one-series claim names the industry tables it does not cover.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import storage
import value_framework as vf

ROOT = Path(__file__).parent


def _glossary() -> dict:
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    return {e["id"]: e for e in g["entries"]}


def _text(e: dict) -> str:
    return " ".join(str(e.get(k) or "") for k in ("definition", "methodology", "formula", "example"))


def _html() -> str:
    return (ROOT / "prospx" / "index.html").read_text(encoding="utf-8").replace("\r\n", "\n")


def _js_block(src: str, head: str) -> str:
    """`head ... {...}` brace-matched, e.g. 'function fvExpectedWarPerYr(' or
    'const FV_WAR_ANCHORS = '."""
    start = src.index(head)
    depth, i = 0, src.index("{", start)
    while True:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1] + (";" if head.startswith("const ") else "")
        i += 1


# ---------------------------------------------------------------- L13-05
MLB_ZERO = [{"level": "MLB", "season": 2025, "ab": 0, "games": 1}]


def test_measured_exposure_distinguishes_zero_from_missing():
    assert storage._mlb_exposure_measured([]) == (None, None)
    assert storage._mlb_exposure_measured([{"level": "AA", "ab": 400}]) == (None, None)
    assert storage._mlb_exposure_measured(MLB_ZERO) == (0.0, None)
    assert storage._mlb_exposure_measured([{"level": "MLB", "ip": 0.0}]) == (None, 0.0)
    pa, ip = storage._mlb_exposure_measured([{"level": "MLB", "ab": 100},
                                             {"level": "MLB", "pa": 50}])
    assert pa == pytest.approx(160.0) and ip is None


def test_a_measured_zero_closes_the_gate():
    """A 0-AB MLB line used to reach the engine as None, which gates on len(seasons)
    full seasons, so it opened the 200 PA gate on a load nobody measured."""
    w = storage._engine_wag_result(50, False, "2B", -0.01, age=24.0, service_years=1.0,
                                   career_stats=MLB_ZERO)
    assert w["exposure_measured"] is True
    assert w["below_meaningful_exposure"] is True
    assert w["w_obs"] == 0.0 and w["regressed_wag"] == 0.0
    assert vf.wag_boom_bust(w) == "unsettled"


def test_missing_exposure_keeps_the_season_load_and_says_so():
    """No MLB row on file (620 graduates, Mike Trout among them) is NOT a zero: the
    engine keeps its season-implied load, byte for byte, and the result says so."""
    w = storage._engine_wag_result(55, False, "SS", 6.0, age=27.0, service_years=3.0,
                                   career_stats=[])
    ref = vf.wag(55, False, 6.0, position="SS", service_years=3.0,
                 exposure_pa=None, exposure_ip=None, age=27.0)
    assert w.pop("exposure_measured") is False
    assert w == ref
    assert w["below_meaningful_exposure"] is False


@pytest.mark.parametrize("is_pitcher,rows,pa,ip", [
    (False, [{"level": "MLB", "ab": 300}], 300 * 1.1, None),
    (True, [{"level": "MLB", "ip": 60.0}], None, 60.0),
])
def test_a_positive_measured_load_is_unchanged(is_pitcher, rows, pa, ip):
    pos = "RHP" if is_pitcher else "SS"
    w = storage._engine_wag_result(50, is_pitcher, pos, 1.0, age=25.0, service_years=2.0,
                                   career_stats=rows)
    ref = vf.wag(50, is_pitcher, 1.0, position=pos, service_years=2.0,
                 exposure_pa=pa, exposure_ip=ip, age=25.0)
    assert w.pop("exposure_measured") is True
    assert w == ref


def test_the_legacy_sample_counts_a_recorded_zero_pa_as_zero():
    both = {"career_stats": [{"level": "MLB", "pa": 0, "ab": 50}]}
    assert storage._career_pa_ip(both) == (0, 0.0)
    ab_only = {"career_stats": [{"level": "MLB", "ab": 100}]}
    assert storage._career_pa_ip(ab_only) == (113, 0.0)


# ---------------------------------------------------------------- L13-18
def _mini_racer():
    mr = pytest.importorskip("py_mini_racer")
    return mr.MiniRacer()


def test_the_client_refuses_the_fv0_sentinel():
    src = _html()
    ctx = _mini_racer()
    ctx.eval(_js_block(src, "const FV_WAR_ANCHORS = "))
    ctx.eval(_js_block(src, "function fvExpectedWarPerYr("))
    for fv in ("0", "0.0", "19.99", "-1", "NaN", "null", "undefined"):
        assert ctx.eval(f"fvExpectedWarPerYr({fv}, false)") is None, fv
        assert ctx.eval(f"fvExpectedWarPerYr({fv}, true)") is None, fv
    assert ctx.eval("fvExpectedWarPerYr(20, false)") == pytest.approx(0.09)
    assert ctx.eval("fvExpectedWarPerYr(45, false)") == pytest.approx(0.65)


# ---------------------------------------------------------------- L13-07
def test_the_outcome_bar_prints_no_war_band():
    src = _html()
    ctx = _mini_racer()
    ctx.eval("var SV_BUCKET_ORDER = ['bust','bench','regular','good','star'];"
             "var SV_BUCKET_COLOR = {bust:'r',bench:'g',regular:'a',good:'c',star:'u'};"
             "function escapeHtml(s){ return String(s); }"
             "var window = {VALUE_FRAMEWORK: {buckets: {bust:{band:'<0.5'}, bench:{band:'0.5-1.5'},"
             " regular:{band:'1.5-2.5'}, good:{band:'2.5-4.0'}, star:{band:'4.0+'}}}};")
    ctx.eval(_js_block(src, "const SV_BUCKET_LABEL = "))
    ctx.eval(_js_block(src, "function renderBucketBar("))
    out = ctx.eval("renderBucketBar({bust:0.5, bench:0.2, regular:0.15, good:0.1, star:0.05}, {})")
    titles = re.findall(r'title="([^"]*)"', out)
    assert titles and all("WAR" not in t for t in titles), titles
    assert "Elite: 5% chance" in titles
    assert "svBucketBand" not in src
    assert "top 4+ WAR/yr band" not in src


# ---------------------------------------------------------------- L13-13
def test_the_label_series_is_not_typed_as_bwar():
    import war_source
    ds = (ROOT / "efv_dataset.py").read_text(encoding="utf-8")
    assert "summed bWAR" not in ds and "_label_provider()" in ds
    for name in ("xfv_dataset_report.json", "xfv_pitcher_dataset_report.json"):
        rep = json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))
        assert "bWAR" not in rep["target"] and "bWAR" not in rep["baseline_note"]
        assert war_source.DEFAULT_PROVIDER in rep["target"]
    curve = json.loads((ROOT / "data" / "fv_outcome_curves_pooled.json").read_text(encoding="utf-8"))
    assert "bWAR" not in curve["schema"]["curve"]
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = next(r for r in reg["models"] if r["model_id"] == "fv_outcome_pooled_grade")
    assert "bWAR" not in row["predicts"] and "bWAR" not in row["champion"]


# ---------------------------------------------------------------- L13-14
def test_the_wag_entry_quotes_the_rules_the_code_runs():
    e = _glossary()["wag"]
    cfg = vf._config()["wag"]
    bb, me = cfg["boom_bust"], cfg["meaningful_exposure"]
    f = e["formula"]
    assert f"percentile >= {float(bb['boom_percentile']):.2f}" in f
    assert f"percentile <= {float(bb['bust_percentile']):.2f}" in f
    assert f"{int(me['hitter_pa'])} PA or {int(me['pitcher_ip'])} IP" in f
    assert "d >= +2.5" in f and "d <= -1.5" in f and "0.70 d + 0.30" in f
    assert "~1.57" not in _text(e)
    # the legacy thresholds the formula quotes are the ones the labeller applies
    def label(w):
        p = {"career_war": {"career_war": w * 2, "war_seasons_count": 2, "war_per_yr": w},
             "fv_close_raw": 50.0, "position": "SS",
             "career_stats": [{"level": "MLB", "pa": 900}]}
        return storage._compute_boom_bust(p)
    exp50 = storage._fv_to_expected_war_per_yr(50.0)
    assert label(exp50 - 1.5) == "bust" and label(exp50 - 1.49) == "settled"


def test_warwag_and_talent_translation_entries_drop_the_retired_numbers():
    g = _glossary()
    assert "FV-55 expects ~2.5" not in _text(g["warwag"])
    assert g["warwag"]["formula"] == "WARWAG = WAR/season + WAG (legacy)"
    tt = _text(g["farm_grade_talent_translation"])
    assert "actual_career_WAR" not in tt and "primer table" not in tt and "eFV" in tt


def test_the_mlb_production_entry_matches_the_tree():
    src = (ROOT / "storage.py").read_text(encoding="utf-8")
    block = re.search(r'"mlb_production":\s*\[(.*?)\]', src.split("TREE_PARENTS = {", 1)[1], re.S)
    leaves = re.findall(r'"(mlb_[a-z_]+)"', block.group(1))
    words = {8: "eight"}
    e = _glossary()["farm_grade_mlb_production"]
    assert f"{round(storage.FARM_TREE_WEIGHT_MLB_PRODUCTION * 100)}% of the farm score" in e["definition"]
    assert f"{words[len(leaves)]} equally weighted leaves" in e["definition"]
    assert "25% of farm_score" not in _text(e) and "career WAR ≥ +5" not in _text(e)
    assert "Grad_pace" in _glossary()["farm_report_card"]["formula"]
    assert "career WAR ≥ +5" not in _html()


# ---------------------------------------------------------------- L13-15
def test_the_one_series_claim_names_what_it_does_not_cover():
    g = _glossary()
    d = g["ewar"]["definition"]
    assert "anchors, surplus" not in d
    assert "Star Odds" in d and "peak WAR/yr" in d
    assert "One WAR series site-wide" not in g["war"]["methodology"]
    bp = _text(g["bust_prob"])
    assert "keyed to first-6-season WAR bands" not in bp

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""LIBRARY_6_EVIDENCE_V1_LABELS: Source Comparison names the eFV it scores.

Since 2026-09-25 the headline and the progress ledger on
/glossary/#view=source-comparison score eFV V2 (source_backtest.json
accuracy.efv_scored_object), while two panels still score eFV v1: the
"eFV vs consensus FV" panel (source_backtest's xfv_vs_consensus block, lifted
from data/xfv_eval.json and data/xfv_eval_pitcher.json) and the eFV scoreboard
(data/xfv_scoreboard_eval.json, whose basis reproduces xfv_eval pooled_oos).
Both printed plain "eFV". The Model upgrades panel presented three eFV v1 cards
(S-XLINE, P1 V3, B-L6) as current, and the capture-curve note always claimed
eFV sorts contributors "more sharply" while it printed 72 percent against 73.

Pinned here:
1. every Source Comparison panel that reads the eFV v1 evals carries "eFV v1" in
   its title, and the producer's protocol string says what it scores;
2. the capture sentence follows the sign of t20x minus t20c and never claims;
3. the Model upgrades panel is gone from the view and its three cards are
   Model Updates note rows labelled eFV v1 whose figures equal their artifact
   keys;
4. the hero, the window line and the caveat carry lane OD-31, 32, 33 and 36.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
JS = ROOT / "assets" / "glossary.js"
BT = ROOT / "data" / "source_backtest.json"
MU = ROOT / "data" / "model_updates.json"
TYPED = ROOT / "data" / "model_updates_typed.json"

V1_SUB = "the board's grade until September 25, 2026 and the graduates' locked grade"
PROTOCOL = ("forward-chained out of sample; debuted cohort; first-six-season eWAR "
            "(KM-censored). This panel scores eFV v1, the board's grade until September 25, "
            "2026 and the graduates' locked grade; the served eFV V2 is scored in the "
            "head-to-head above.")


def _js() -> str:
    return JS.read_text(encoding="utf-8")


def _fn_src(js: str, name: str) -> str:
    m = re.search(r"^function " + re.escape(name) + r"\([^)]*\) \{.*?\n\}\r?\n", js, re.S | re.M)
    assert m, f"{name} not found at module level in assets/glossary.js (renamed?)"
    return m.group(0)


def _module_functions(js: str) -> dict[str, str]:
    return {m.group(1): _fn_src(js, m.group(1))
            for m in re.finditer(r"^function (\w+)\(", js, re.M)}


def _rendered_by_source_comparison(js: str) -> set[str]:
    body = _fn_src(js, "renderSourceComparison")
    return set(re.findall(r"\b(_meth\w+)\(", body))


# The two ways a Source Comparison renderer reaches the eFV v1 evals.
_V1_READS = ("bt.xfv_vs_consensus;", "_S.scoreEval")
_TITLE_RE = re.compile(r'class="(?:meth-chart-title|source-comp-eyebrow|meth-h)"[^>]*>(.*?)</', re.S)


def test_every_source_comparison_panel_reading_the_v1_evals_is_titled_efv_v1():
    js = _js()
    fns = _module_functions(js)
    shown = _rendered_by_source_comparison(js)
    readers = sorted(n for n in shown if n in fns and any(k in fns[n] for k in _V1_READS))
    # Today: the eFV v1 vs consensus panel and the eFV v1 scoreboard. A new
    # renderer that reads either source joins this list and must be labelled.
    assert {"_methEfvPanel", "_methScoreboardHTML"} <= set(readers), readers
    for name in readers:
        titles = _TITLE_RE.findall(fns[name])
        assert titles, f"{name} reads an eFV v1 eval but renders no panel title"
        assert any("eFV v1" in t for t in titles), (name, titles)
        assert not any(re.search(r"\beFV(?! v1| V2)\b", t) for t in titles), (
            f"{name} names an unversioned eFV in a title: {titles}")
    panel = fns["_methEfvPanel"]
    assert "eFV v1 vs consensus FV" in panel and V1_SUB in panel
    assert "our model · out-of-sample" not in panel
    sb = fns["_methScoreboardHTML"]
    assert "eFV v1 scoreboard &middot; the graduates' locked grade, cell by cell" in sb
    assert "Where eFV v1 wins, and where it does not" in sb


def test_the_protocol_string_names_eFV_v1_in_the_producer_and_the_artifact():
    src = (ROOT / "source_backtest.py").read_text(encoding="utf-8")
    flat = re.sub(r'"\s*\n\s*"', "", src)
    assert PROTOCOL in flat
    assert "first-6-season \"" not in src and "The shipped headline rank is the guarded" not in src
    if not BT.exists():
        pytest.skip("data/source_backtest.json absent (gitignored build artifact)")
    doc = json.loads(BT.read_text(encoding="utf-8"))
    xc = doc.get("xfv_vs_consensus") or {}
    if xc.get("sides"):
        assert xc.get("protocol") == PROTOCOL


def _runtime():
    node = shutil.which("node")
    if node:
        return [node], {}
    code = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe"
    if code.exists():
        return [str(code)], {"ELECTRON_RUN_AS_NODE": "1"}
    return None, None


def _run_js(snippet: str, tmp_path: Path) -> str:
    cmd, env = _runtime()
    if not cmd:
        pytest.skip("no JS runtime (node or VS Code) on this box")
    src = tmp_path / "fn.js"
    src.write_text(_fn_src(_js(), "_captureCompareSentence") + "\n" + snippet, encoding="utf-8")
    out = subprocess.run(cmd + [str(src)], capture_output=True, text=True, timeout=60,
                         env={**os.environ, **env})
    assert out.returncode == 0, out.stderr
    return out.stdout


NO_CLAIM = "No floor is computed for this curve, so the gap is a description, not a claim."


@pytest.mark.parametrize("t20x,t20c,want", [
    (72, 73, "The consensus concentrates more of it."),
    (71, 74, "The consensus concentrates more of it."),
    (74, 71, "eFV concentrates more of it."),
    (73, 73, "The two boards concentrate the same share."),
])
def test_the_capture_sentence_follows_the_sign_of_t20x_minus_t20c(tmp_path, t20x, t20c, want):
    got = _run_js(f"process.stdout.write(_captureCompareSentence({t20x}, {t20c}));", tmp_path)
    assert got == f"{want} {NO_CLAIM}", got


def test_the_capture_curve_prints_the_derived_sentence_and_no_typed_claim():
    js = _js()
    body = _fn_src(js, "_methCaptureCurve")
    assert "_captureCompareSentence(t20x, t20c)" in body and "${capCmp}" in body
    assert "more sharply" not in js
    helper = _fn_src(js, "_captureCompareSentence")
    assert "Number(t20x) - Number(t20c)" in helper and NO_CLAIM in helper


# ---------------------------------------------------------------- Model upgrades
_RETIRED = ("_methModelUpgrades", "_loadUpgrades", "_methUpgradeXlineHTML", "_methUpgradeP1HTML",
            "_methDenoisedControlHTML", "What recently changed under the hood",
            "Model upgrades · gate-checked ships", "xfv_statcast_line_eval.json",
            "xfv_provisional_prior_eval.json", "xfv_denoised_baseline_eval.json")


def test_the_model_upgrades_panel_has_left_the_view():
    js = _js()
    for s in _RETIRED:
        assert s not in js, f"retired Model upgrades material is back in glossary.js: {s!r}"


def _dig(doc, dotted: str):
    cur = doc
    for part in dotted.split("."):
        cur = cur[part]
    return cur


def _notes():
    doc = json.loads(MU.read_text(encoding="utf-8"))
    return [e for e in doc["events"] if e.get("origin") == "model upgrades panel"]


def test_the_three_cards_are_dated_eFV_v1_note_rows_in_model_updates():
    rows = _notes()
    cards = ("S-XLINE", "P1 V3", "B-L6")
    got = sorted((e["date"], next((c for c in cards if e["change"].startswith(f"eFV v1, {c}")), None))
                 for e in rows)
    assert got == [("2026-07-23", "P1 V3"), ("2026-07-23", "S-XLINE"), ("2026-08-11", "B-L6")], got
    import model_updates as M
    for e in rows:
        assert e["model_id"] == "efv_v1" and e["layer"] == "note" and e["kind"] == "note"
        assert e["change"].startswith("eFV v1, "), e["change"][:40]
        assert not M.NOTE_VERDICT_RE.search(e["change"]), e["change"]
        assert e["edge"]["text"] == M.NO_SCORE_TEXT
        src = e["source"]
        assert src.get("path") and src.get("key"), src
        assert (ROOT / src["path"]).exists(), src["path"]
    # The typed input carries them too, and the validator passes the file whole.
    typed = json.loads(TYPED.read_text(encoding="utf-8"))
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    assert M.validate_notes(typed, {m["model_id"] for m in reg["models"]}) == []
    assert sum(1 for n in typed["notes"] if n.get("origin") == "model upgrades panel") == 3


def _figures_from(block, keys_fmt):
    return {fmt.format(_dig(block, k)) for k, fmt in keys_fmt}


@pytest.mark.parametrize("label,keys_fmt", [
    ("B-L6", [("delta", "+{:.5f}"), ("efv_rho", "{:.5f}"), ("consensus_rho", "{:.5f}"),
              ("MDE95_E_cond", "{:.4f}"), ("MDE95_E_refit", "{:.4f}"),
              ("margin_over_E_cond", "{:.3f}"), ("margin_over_E_refit", "{:.3f}")]),
    ("S-XLINE", [("hit.delta_rho", "+{:.4f}"), ("hit.n_pairs", "{}"),
                 ("pit.delta_rho_xslg_arm", "+{:.4f}"), ("pit.n_pairs", "{}")]),
    ("P1 V3", [("n_movers", "{}"), ("n_scored", "{}"), ("max_delta_fv", "{:.1f}")]),
])
def test_each_note_row_figure_equals_its_artifact_key(label, keys_fmt):
    row = next(e for e in _notes() if e["change"].startswith(f"eFV v1, {label}"))
    art = json.loads((ROOT / row["source"]["path"]).read_text(encoding="utf-8"))
    block = _dig(art, row["source"]["key"])
    for fig in _figures_from(block, keys_fmt):
        assert fig in row["change"], (label, fig, row["change"])


def test_the_b_l6_row_says_the_gap_did_not_clear_its_floor():
    row = next(e for e in _notes() if e["change"].startswith("eFV v1, B-L6"))
    art = json.loads((ROOT / "data" / "xfv_denoised_baseline_eval.json").read_text(encoding="utf-8"))
    inc = art["incumbent_rederived_today"]
    assert inc["delta"] < inc["MDE95_E_cond"] and inc["delta"] < inc["MDE95_E_refit"]
    assert "did not clear either" in row["change"]
    assert "lead" not in row["change"].lower()


# ---------------------------------------------------------------- hero copy
def test_hero_window_and_caveat_carry_the_od_rewrites():
    js = _js()
    hero = _fn_src(js, "_methHeroBanner")
    assert '<div class="source-comp-hero-kicker">Our grade against theirs</div>' in hero
    assert "A different kind of Future Value" not in js
    heads = re.findall(r'"(eFV [^"]*)"', hero.split("const headline =", 1)[1].split(";", 1)[0])
    assert len(heads) == 4 and all(h.startswith("eFV reorders the consensus where outcomes support it")
                                   for h in heads), heads
    # The tie, ahead and resolvable clauses stay as they were.
    tails = {h[len("eFV reorders the consensus where outcomes support it"):] for h in heads}
    assert tails == {".",
                     ", and out of sample it ranks ahead of every public source by a margin that clears our noise floor.",
                     ", and out of sample it ranks ahead of every public source - by a margin we still cannot call a win.",
                     ", and out of sample it is statistically indistinguishable from the best public scouting grade."}
    assert "what they actually <em>became</em>" not in js
    assert ("eFV starts from their consensus and reorders it within hitters and within pitchers, "
            "with drivers fit on resolved outcomes. It is scored leakage-free and forward-chained, "
            "on the same players, window and vintage as each source.") in hero
    assert '"our grade (eFV V2)"' in hero and "outcome-grounded model" not in js
    render = _fn_src(js, "renderSourceComparison")
    assert ("eFV is the primary grade: the consensus order, reordered by drivers fitted on "
            "resolved outcomes.") in render
    assert ("Statcast, injury, age and a reliever role show on each card as labelled notes; "
            "on the board today none of them moves the grade.") in render
    assert "only a live overlay" not in render
    # The EFV3_D4 copy contract: no stratum word reaches the hero.
    assert "stratum" not in hero

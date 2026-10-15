# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Library's copy states current facts (LIBRARY_9_COPY_CURRENT, owner ask
2026-10-02, plan LIBRARY_PLAN.md section 6, items OD-01 to OD-48).

One test per rewritten claim family:
  * no served copy names The Athletic as a consensus input (consensus.py: 0 rows);
  * no 'Bayesian' in consensus copy (the scheme has had no production caller since
    2026-05; the live rule is the one-third pull toward FV 35);
  * no 'guarded blend' or 'ridge' in eFV copy outside text labelled eFV v1 (the
    board serves eFV V2 since 2026-09-25, data/xfv.json meta.served_model);
  * SC+ copy says 10 points per standard deviation (statcast_plus.py);
  * the $/WAR level sentence reads value_framework dollars_per_war.level_basis;
  * the Breakout Indicator entry prints the bars storage gates on;
  * the xfv entry's retired v1 steps are Model Updates note rows;
  * How to Read names eFV as the headline grade, and the cadence FAQ matches the
    nightly job.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
GLJS = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8").replace("\r\n", "\n")


def _glossary() -> dict:
    d = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    return {e["id"]: e for e in d["entries"]}


def _text(entry: dict) -> str:
    return "\n".join(v for v in entry.values() if isinstance(v, str))


def _fn(name: str) -> str:
    m = re.search(r"\nfunction " + re.escape(name) + r"\(.*?\n\}\n", GLJS, re.S)
    assert m, f"{name} not found in assets/glossary.js"
    return m.group(0)


def _prose_part(key: str) -> str:
    body = _fn("_methProseParts")
    m = re.search(r"\n    " + re.escape(key) + r": `(.*?)\n`,", body, re.S)
    assert m, f"_methProseParts has no {key} part"
    return m.group(1)


# ---------------------------------------------------------------- The Athletic

def test_no_served_copy_names_the_athletic_as_a_consensus_input():
    import build_site
    assert not [r for r in build_site.SOURCE_ROWS if "Athletic" in r["name"]], (
        "/sources/ credits The Athletic; consensus.py counts 0 rows from it")
    assert "The Athletic" not in GLJS
    gl = _glossary()
    for eid in ("fv", "consensus_fv", "single_source_mark"):
        assert "Athletic" not in _text(gl[eid]), eid
    page = (ROOT / "sources" / "index.html").read_text(encoding="utf-8")
    assert "The Athletic" not in page


# ---------------------------------------------------------------- Bayesian

def test_no_bayesian_in_consensus_copy():
    gl = _glossary()
    for eid in ("fv", "consensus_fv", "single_source_mark"):
        assert "Bayesian" not in _text(gl[eid]), eid
        assert "shrunk = (n_obs" not in _text(gl[eid]), eid
    assert "Bayesian" not in _prose_part("consensus")
    assert "Bayesian" not in _fn("renderGuide")
    assert "one third of the way toward FV 35" in _prose_part("consensus")
    assert "forward-fill + shrink" not in GLJS


# ---------------------------------------------------------------- eFV v1 terms

_V1_TERMS = re.compile(r"guarded blend|\bridge\b", re.I)


def test_no_guarded_blend_or_ridge_outside_efv_v1_text():
    assert not _V1_TERMS.search(GLJS), "glossary.js names the v1 guarded blend or ridge"
    xfv = _glossary()["xfv"]
    for para in xfv["methodology"].split("\n\n"):
        if _V1_TERMS.search(para):
            assert para.startswith("EFV V1"), para[:80]
    for f in ("definition", "formula", "example"):
        assert not _V1_TERMS.search(xfv.get(f) or ""), f
    notes = json.loads((ROOT / "data" / "model_updates_typed.json").read_text(encoding="utf-8"))["notes"]
    for n in notes:
        if _V1_TERMS.search(n["text"]):
            assert n["model_id"] == "efv_v1" and n["text"].startswith("eFV v1"), n["text"][:80]


def test_efv_method_describes_v2():
    efv = _prose_part("efv")
    assert "eFV V2" in efv and "Consensus sets the level" in efv
    assert "3,961" not in efv and "regularized" not in efv
    assert "eFV v1" in efv  # graduates' locked grade, labelled


# ---------------------------------------------------------------- plus scales

def test_sc_plus_copy_says_10_points():
    import statcast_plus
    assert statcast_plus._SC_PLUS_ANCHOR == 100 and statcast_plus._SC_PLUS_PER_SIGMA == 10, (
        "statcast_plus.py no longer rescales 100 + 10z; change the copy with it")
    ark = _prose_part("arkmetrics")
    sc = ark[ark.index("SC+ - Statcast+"):]
    sc = sc[: sc.index("</dd>")]
    assert "10 points = one standard deviation" in sc and "15 points" not in sc
    assert "wRC+/OPS+" not in GLJS
    assert "10 points = one standard deviation" in _glossary()["statcast_plus"]["definition"]


def test_dvm_plus_methods_text_names_the_code_windows():
    import storage
    ark = _prose_part("arkmetrics")
    dvm = ark[ark.index("DvM+ - Development vs Mean"):]
    dvm = dvm[: dvm.index("</dd>")]
    pw = int(storage.FARM_PRINCIPAL_WINDOW.rstrip("y"))
    yrs = sorted(int(k.rstrip("y")) for k in storage.FARM_TRAJECTORY_WINDOWS)
    words = {1: "one", 8: "eight"}
    assert f"windows of {words[yrs[0]]} to {words[yrs[-1]]} years" in dvm
    assert f"{pw}-year window 60%" in dvm
    assert "1 / 3 / 6" not in dvm and "6y / 3y / 1y" not in dvm


# ---------------------------------------------------------------- $/WAR level

def test_dpw_level_sentence_reads_the_framework_field():
    body = _fn("_dpwLevelTxt")
    assert "level_basis" in body and "level_usd" in body and "applied" in body
    assert "_dpwLevelTxt()" in _fn("_methProseParts")
    assert "dpwLvl" in _prose_part("surplus") or "_dpwLvl" in _prose_part("surplus")
    assert "re-anchor" not in GLJS, "the retired FA re-anchor sentence is back"
    vf = json.loads((ROOT / "data" / "value_framework.json").read_text(encoding="utf-8"))
    lb = vf["dollars_per_war"]["level_basis"]
    assert lb["method"] == "fa_winter_level" and lb["applied"] is True
    typed = "$%.2fM" % (lb["level_usd"] / 1e6)
    assert typed not in GLJS, f"the level {typed} is typed instead of read"
    assert "One price of a win." in GLJS and "dpwLvl" in GLJS


# ---------------------------------------------------------------- Breakout

def _breakout_consts() -> dict:
    tree = ast.parse((ROOT / "storage.py").read_text(encoding="utf-8"))
    out = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id.startswith("_BREAKOUT_"):
            try:
                out[n.targets[0].id] = ast.literal_eval(n.value)
            except ValueError:
                pass
    return out


def test_breakout_entry_prints_the_storage_bars():
    c = _breakout_consts()
    meth = _glossary()["breakout_indicator"]["methodology"]
    g = lambda k: f"{c[k]:g}"  # noqa: E731
    for phrase in (f"wRC+ {g('_BREAKOUT_HITTER_WRC_PLUS_GATE')} or better",
                   f"Peripheral Stuff+ {g('_BREAKOUT_PITCHER_STF_PLUS_GATE')} or better",
                   f"FIP- {g('_BREAKOUT_PITCHER_FIP_MINUS_GATE')} or lower",
                   f"Statcast+ {g('_BREAKOUT_STATCAST_PLUS_GATE')} or better",
                   f"Peripheral Stuff+ {g('_BREAKOUT_STAT_STF_PLUS_GATE')} or better",
                   f"Statcast+ {g('_BREAKOUT_STAT_STATCAST_PLUS_GATE')} or better",
                   f"level wRC+ {g('_BREAKOUT_STAT_OPS_PLUS_LEVEL_GATE')} or better",
                   f"hitters through {g('_BREAKOUT_STAT_HITTER_MAX_AGE')}",
                   f"pitchers through {g('_BREAKOUT_STAT_PITCHER_MAX_AGE')}",
                   f"through {g('_BREAKOUT_MAX_AGE_STARTER')}",
                   f"through {g('_BREAKOUT_MAX_AGE_RELIEVER')}",
                   f"consensus FV up {g('_BREAKOUT_FV_UPGRADE_THRESHOLD')} or more",
                   f"tool grade up {g('_BREAKOUT_TOOL_VELOCITY_THRESHOLD')} or more",
                   "upside", "60-day IL", "faller"):
        assert phrase in meth, phrase
    assert "RPS+" not in _text(_glossary()["breakout_indicator"]), "RPS+ is no breakout gate"


# ---------------------------------------------------------------- xfv v1 history

def test_xfv_retired_steps_are_model_updates_notes():
    import model_updates as mu
    xfv = _glossary()["xfv"]["methodology"]
    for gone in ("LEVEL CALIBRATION, RETIRED", "stopped being displayed on 2026-07-25",
                 "The retired coefficients stay in the code", "Board overlays (live board only"):
        assert gone not in xfv, gone
    # eFV v5 COMBINED serves from 2026-10-15 (owner override EW3-10); V2 follows it
    assert xfv.startswith("EFV V5 COMBINED, SERVED FROM 2026-10-15")
    assert "\n\nEFV V2, SERVED 2026-09-25 TO 2026-10-15" in xfv
    assert "\n\nEFV V1, graduates and busts" in xfv
    doc = json.loads((ROOT / "data" / "model_updates_typed.json").read_text(encoding="utf-8"))
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    ids = [m["model_id"] for m in (reg["models"] if isinstance(reg, dict) else reg)]
    assert mu.validate_notes(doc, ids) == []
    hist = [n for n in doc["notes"] if n["origin"] == "xfv entry v1 history"]
    assert {n["date"] for n in hist} >= {"2026-08-14", "2026-07-25/30", "2026-09-25"}
    assert all(n["model_id"] == "efv_v1" for n in hist)
    blend = [n for n in doc["notes"] if "guarded blend" in n["text"]]
    assert blend and blend[0]["source"] == {"path": "data/xfv.json", "key": "meta.live_lambda"}
    lam = json.loads((ROOT / "data" / "xfv.json").read_text(encoding="utf-8"))["meta"]["live_lambda"]
    assert f"hitters {lam['hit']:.2f}" in blend[0]["text"] and f"pitchers {lam['pit']:.2f}" in blend[0]["text"]
    gl = _glossary()
    assert "single-path formula" not in _text(gl["tvi"])
    assert "single-path formula is retired" not in _text(gl["value_framework"])


# ---------------------------------------------------------------- How to Read, FAQ

def test_how_to_read_names_efv_as_the_headline_grade():
    guide = _fn("renderGuide")
    assert '"xfv",\n      "The headline grade: eFV' in guide
    assert 'archNode("xfv", "eFV"' in guide
    assert "eFV reorders the consensus inside each side" in guide
    assert "${escapeHtml(LIB_NAME)} entry" in guide


def test_cadence_faq_matches_the_nightly_job():
    sh = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    assert '"$(date +%d)" = "01"' in sh and "run_monthly.py --daily" in sh
    faq = _prose_part("faq")
    assert "runs on the first of each month and a daily refresh runs on the remaining nights" in faq
    assert "refresh monthly" not in faq


def test_reliability_monitor_names_the_distribution_it_scores():
    body = _fn("_methReliabilityHTML")
    assert "eFV v1's five-bucket outcome distribution" in body
    assert "does not score them" in body
    assert "These are the odds the site serves" not in body


@pytest.mark.parametrize("stale", [
    "the prospect grade trained on outcomes",
    "Our engine spends that difference",
    "Two rank-only sources",
    "eFV's prior) is built",
])
def test_retired_sentences_stay_gone(stale):
    assert stale not in GLJS

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The provisional eFV glossary entry and registry rows describe what is served.

WHY THIS EXISTS (census M01-06, 2026-09-24). The glossary said provisional grades were
"Shown on farm-detail rosters" and "not in the board rank", with "hit cap 43 / pit cap 40",
while the board ranks 3,392 provisional rows among the graded players (from #190 down) on
a soft map whose pitcher ceiling is 38. The registry said the de-cap had shipped
(UNCAPPED_GRADE is False since 2026-07-25), that PLUS% was an opt-in column (it is on by
default) and that the GRPO badge sat on the PROSPX board (it is on the Trade Machine).

Contract pinned here: every knee and ceiling the glossary names equals
data/xfv_ungraded.json meta.grade_map, its accuracy figures equal data/xfv_ungraded_eval.json,
and the stale surface strings are gone.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def _load(name):
    p = DATA / name
    if not p.exists():
        pytest.skip(f"data/{name} not built")
    return json.loads(p.read_text(encoding="utf-8"))


def _entry():
    g = _load("glossary.json")
    return next(e for e in g["entries"] if e.get("id") == "xfv_ungraded")


def _rows():
    return {m["model_id"]: m for m in _load("model_registry.json")["models"]}


def _num(v) -> str:
    v = float(v)
    return str(int(v)) if v == int(v) else ("%.1f" % v)


def test_glossary_does_not_place_provisional_grades_off_the_board():
    e = _entry()
    text = " ".join(str(e.get(k) or "") for k in ("definition", "methodology", "formula"))
    assert "not in the board rank" not in text
    assert "farm-detail rosters" not in text
    assert "hard cap" not in text
    assert re.search(r"ranks on the PROSPX board", text)


def test_glossary_knee_and_ceiling_equal_the_served_grade_map():
    gm = _load("xfv_ungraded.json")["meta"]["grade_map"]
    f = _entry()["formula"]
    for side, label in (("hit", "Hitters"), ("pit", "Pitchers")):
        m = re.search(label + r": (\d+(?:\.\d+)?) \+ (\d+(?:\.\d+)?) \* WAR, knee (\d+(?:\.\d+)?), ceiling (\d+(?:\.\d+)?)", f)
        assert m, f"the formula no longer names the {label.lower()} map"
        assert m.groups() == (_num(gm[side]["BASE"]), _num(gm[side]["SLOPE"]),
                              _num(gm[side]["KNEE"]), _num(gm[side]["CEIL"])), (
            f"{label} map in the glossary {m.groups()} differs from meta.grade_map {gm[side]}")
    assert "cap 40" not in f and "cap 43" not in f


def test_glossary_accuracy_figures_come_from_the_eval_artifact():
    bs = _load("xfv_ungraded_eval.json")["battery"]["by_side"]
    meth = _entry()["methodology"]
    assert "about as well as scout grades" not in meth
    for side, word in (("hit", "hitters"), ("pit", "pitchers")):
        want = "%.2f for %s (n %s)" % (round(bs[side]["rho_grade_weighted"], 2), word,
                                       format(bs[side]["n_scored"], ","))
        assert want in meth, f"methodology does not print the artifact's {word} figure: {want}"


def test_registry_surfaces_name_what_is_served():
    rows = _rows()
    assert "farm-detail" not in rows["xfv_ungraded"]["surface"]
    assert "opt-in #optpct" not in rows["upgrade_option"]["surface"]
    assert "PLUS%" in rows["upgrade_option"]["surface"]
    assert "PROSPX board breakout badge" not in rows["grpo_prospect"]["surface"]
    assert "Trade Machine" in rows["grpo_prospect"]["surface"]


def test_decap_row_is_not_claimed_as_shipped_while_the_flag_is_off():
    import efv_ungraded
    row = _rows()["xfv_ungraded_recal"]
    if not efv_ungraded.UNCAPPED_GRADE:
        assert not row["surface"].startswith("provisional grade de-cap, SHIPPED")
        assert row["verdict"] != "validated"


# --- PROVISIONAL_V2 defects D1-D6 (2026-10-01) ---------------------------------------

def test_module_copy_carries_no_stale_cap_or_unreproduced_claims():
    """D1 / D2: the module and the thin-p_bust lab stopped quoting a hard cap of 43 / 40,
    a pitcher knee 38 / ceiling 42 as current, Spearman figures that do not reproduce
    (data/xfv_ungraded_eval.json legacy_2026_07_14), and a live maximum of 44.9."""
    src = (ROOT / "efv_ungraded.py").read_text(encoding="utf-8")
    for stale in ("a hard cap (43 hit / 40 pit)", "KNEE 38 / CEIL 42 compresses hard",
                  "~0.22", "~0.31", "0.09 -> 0.24", "Hitters ~0.22",
                  "the live artifact's maximum is 44.9"):
        assert stale not in src, stale
    lab = (ROOT / "tools" / "pbust_thin" / "make_eval.py").read_text(encoding="utf-8")
    assert "the live provisional maximum is 44.9" not in lab
    assert 'new["meta"]["grade_dist"]["max"]' in lab


def test_eval_cli_cannot_write_the_gate_artifact(tmp_path, monkeypatch):
    """D4: `python efv_ungraded.py --eval` wrote the legacy two-number format over
    data/xfv_ungraded_eval.json, the gate battery the registry cites. evaluate() now
    defaults to no write, writes only the data/_labs/ path when asked, and refuses a
    target that resolves to the gate artifact."""
    import efv_ungraded as U
    gate = tmp_path / "gate.json"
    gate.write_text('{"battery": "keep me"}', encoding="utf-8")
    empty = tmp_path / "matrix.json"
    empty.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(U, "EVAL_PATH", gate)
    monkeypatch.setattr(U, "LEGACY_EVAL_PATH", tmp_path / "_labs" / "legacy.json")
    monkeypatch.setattr(U, "matrix_path", lambda side: empty)
    U.evaluate()
    assert not (tmp_path / "_labs" / "legacy.json").exists()
    U.evaluate(persist=True)
    assert (tmp_path / "_labs" / "legacy.json").exists()
    assert gate.read_text(encoding="utf-8") == '{"battery": "keep me"}'
    with pytest.raises(ValueError):
        U.evaluate(persist=True, out_path=gate)
    assert gate.read_text(encoding="utf-8") == '{"battery": "keep me"}'
    src = (ROOT / "efv_ungraded.py").read_text(encoding="utf-8")
    assert "EVAL_PATH.write_text" not in src.replace("LEGACY_EVAL_PATH", "")
    assert 'LEGACY_EVAL_PATH = DATA_DIR / "_labs" / ' in src


def test_penalty_copy_matches_the_board():
    """D3: _PROV_RANK_PENALTY is 0 since 2026-07-25, so neither the registry row nor the
    prospx efvRankValue comment may describe a penalty as shipped."""
    html = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    assert re.search(r"const _PROV_RANK_PENALTY = 0;", html)
    i = html.index("function efvRankValue(p)")
    body = html[i:html.index("function boardCmp(", i)]
    assert "take a fixed penalty" not in body
    row = _rows()["provisional_calibration"]
    assert "RETIRED 2026-07-25" in row["champion"]
    assert "both unchanged" not in row["champion"]
    assert row["notes"].startswith("PENALTY RETIRED 2026-07-25")


def test_xfv_ungraded_row_scopes_its_accuracy_figure():
    """D5: the figure is WAR skill on the source-graded pool, not grading skill, and
    every number the row quotes for it comes from data/xfv_ungraded_eval.json."""
    ev = _load("xfv_ungraded_eval.json")
    bs, leg = ev["battery"]["by_side"], ev["legacy_2026_07_14"]["reproduced_on_current_code_and_corpus"]
    row = _rows()["xfv_ungraded"]
    assert "source-GRADED labelled pool" in row["metric"] and "not grading skill" in row["metric"]
    notes = row["notes"]
    for side, word in (("hit", "hitters"), ("pit", "pitchers")):
        assert "%s %.3f (n %s)" % (word, bs[side]["rho_grade_weighted"],
                                   format(bs[side]["n_scored"], ",")) in notes
    assert "%.3f low-minors / %.3f all-levels" % (
        leg["hit"]["low_minors_age_le21"]["spearman_vs_realized_war"],
        leg["hit"]["all_levels"]["spearman_vs_realized_war"]) in notes
    assert "Spearman ~0.22 / all-levels ~0.31 (~matches" not in notes


def test_provisional_history_chart_is_labelled_as_rescored():
    """D6: the detail-page eFV-over-time chart re-scores past seasons with today's fit;
    it is not the grade the site served at the time."""
    html = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    assert "grade as-of each MiLB season" not in html
    assert "each MiLB season re-scored with the current model" in html

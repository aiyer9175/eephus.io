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

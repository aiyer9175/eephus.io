# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DS-11 (bug B6) pins: the served eFV overlays are named, the live path and the
out-of-sample path produce the same order on the same rows when the overlays are off
(and when the gradeable ones are on), and the disposition of every overlay follows the
rule that was fixed before the read (efv_overlays.DISPOSITION_RULE).
"""
from __future__ import annotations

import ast
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import efv_model as V1  # noqa: E402
import efv_overlays as OV  # noqa: E402
import efv_score as E  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
from efv_dataset import matrix_path  # noqa: E402

ART = ROOT / "data" / "efv_overlay_oos_eval.json"


# ---------------------------------------------------------------------------
# the registry

def test_every_served_overlay_is_registered():
    assert set(E.SERVED_OVERLAYS) == set(OV.OVERLAYS)
    assert set(E.MODEL_LEG_OVERLAYS) == {k for k, v in OV.OVERLAYS.items()
                                         if v["acts_on"] == "model_leg"}
    assert set(OV.GRADED) == {"injury", "age", "role"}


def test_unknown_overlay_is_refused():
    with pytest.raises(ValueError):
        E.overlay_factors({}, "hit", 1.0, ("age", "nonsense"))
    with pytest.raises(ValueError):
        V1.oos_grades("hit", overlays=("dispersion",))


def test_overlays_off_touch_nothing():
    r = {"age_now": 27.0, "position": "RP", "il_on": 1, "il_type": "60-day",
         "statcast_plus": 130.0, "milb": {"age": 27.0}}
    parts = E.overlay_factors(r, "pit", 3.0, ())
    assert parts == {"injury": 1.0, "age": 1.0, "role": 1.0, "statcast": 1.0,
                     "xline_fv": 0.0, "xline_label": None}
    assert E.apply_overlay_war(3.0, parts, {"a": 0.0, "b": 0.3}) == 3.0
    on = E.overlay_factors(r, "pit", 3.0, ("injury", "age", "role"))
    assert on["injury"] < 1 and on["age"] < 1 and on["role"] < 1
    assert E.apply_overlay_war(3.0, on, None) < 3.0


# ---------------------------------------------------------------------------
# live path == out-of-sample path on the same rows

def _fold(side: str):
    raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    full = [r for r in raw if not (r["kind"] == "bust" and r.get("bust_recent"))]
    yr = max(V1.SCORED_YEARS)
    tr = [r for r in full if V1._decision_year(r) < yr]
    te = [r for r in full if V1._decision_year(r) == yr and r.get("milb")]
    stack = V1.fit_production_stack(tr, side)
    assert stack is not None
    return full, te, stack


@pytest.mark.parametrize("side", ["hit", "pit"])
def test_live_and_oos_paths_give_the_same_order_with_overlays_off(side):
    """The acceptance test of DS-11: the same fold fit, the same rows, no overlays.
    run_live's unrounded rank_war equals oos_grades' score on every row it scores, so
    the two orders are identical."""
    _full, te, stack = _fold(side)
    got: dict = {}
    E.run_live(persist=False, side=side, overlays=(), stack=stack, rows=te, rank_out=got)
    oos = V1.oos_grades(side)
    assert len(got) >= 50
    for k, v in got.items():
        assert v == oos[k], k
    keys = sorted(got)
    assert (sorted(keys, key=lambda k: (got[k], k))
            == sorted(keys, key=lambda k: (oos[k], k)))


@pytest.mark.parametrize("side", ["hit", "pit"])
def test_live_and_oos_paths_agree_with_the_gradeable_overlays_on(side):
    """With the gradeable overlays on and the as-of inputs attached to the rows, both
    paths still produce the same numbers: the out-of-sample read grades exactly what
    run_live serves for those overlays."""
    full, te, stack = _fold(side)
    inputs = OV.asof_inputs(te)
    rows = [dict(r, **inputs.get(r["player_key"], {})) for r in te]
    got: dict = {}
    E.run_live(persist=False, side=side, overlays=OV.GRADED, stack=stack, rows=rows,
               rank_out=got)
    oos = V1.oos_grades(side, overlays=OV.GRADED, overlay_inputs=inputs)
    assert len(got) >= 50
    for k, v in got.items():
        assert v == oos[k], k


def test_default_oos_grades_apply_no_overlay():
    a = V1.oos_grades("pit")
    b = V1.oos_grades("pit", overlays=())
    assert a == b


# ---------------------------------------------------------------------------
# as-of inputs

def test_il_status_never_reads_at_or_after_the_read():
    ev = [{"date": date(2021, 5, 1), "kind": "place", "il_type": "7-day"},
          {"date": date(2021, 5, 20), "kind": "activate", "il_type": None},
          {"date": date(2022, 3, 1), "kind": "place", "il_type": "60-day"},
          {"date": date(2022, 6, 1), "kind": "activate", "il_type": None}]
    s = OV.il_status_asof(ev, date(2022, 4, 1))
    assert s["il_on"] == 1 and s["il_type"] == "60-day"
    assert s["il_days_12mo"] == 19 + 31 and s["il_stints_12mo"] == 2
    before = OV.il_status_asof(ev, date(2022, 3, 1))      # the placement day itself
    assert before["il_on"] == 0 and before["il_type"] is None
    later = OV.il_status_asof(ev, date(2023, 3, 2))       # both stints aged out
    assert later == {"il_on": 0, "il_type": None, "il_days_12mo": 0.0,
                     "il_stints_12mo": 0.0}


def test_age_is_read_at_the_read_date():
    assert OV.age_at("2000-04-01", date(2023, 4, 1)) == 23.0
    assert OV.age_at(None, date(2023, 4, 1)) is None
    assert OV.read_date({"asof_date": "2019-02-01", "cutoff": "2020-01-01"}) == date(2019, 2, 1)


# ---------------------------------------------------------------------------
# the rule

def _read(lo_hit, lo_pit, fires=(10, 10)):
    return {"hit": {"fires": fires[0], "within": {"delta": 0.01, "ci95": [lo_hit, 0.02]}},
            "pit": {"fires": fires[1], "within": {"delta": 0.01, "ci95": [lo_pit, 0.02]}}}


def test_the_rule():
    assert OV.decide("age", _read(0.001, 0.002))["disposition"] == "grade"
    assert OV.decide("age", _read(0.001, -0.002))["disposition"] == "chip"
    # only the sides where the overlay applies count (injury: pitchers only)
    assert OV.decide("injury", _read(-0.5, 0.002))["disposition"] == "grade"
    assert OV.decide("injury", _read(0.1, 0.1, fires=(10, 0)))["disposition"] == "chip"
    assert OV.decide("statcast", _read(0.1, 0.1))["disposition"] == "chip"
    assert OV.decide("xline", None)["disposition"] == "chip"
    assert OV.decide("dispersion", None)["disposition"] == "retired"
    assert OV.decide("side_fairness", None)["disposition"] == "retired"


def test_dispersion_is_identity_so_retiring_it_moves_nothing():
    for is_pit in (False, True):
        for w in (-2.0, -0.5, 0.0, 1.3, 7.0):
            assert E.apply_dispersion_correction(w, is_pit) == w


def test_chips_never_carry_a_grade_move():
    disp = {k: OV.decide(k, None) for k in OV.OVERLAYS}
    r = {"age_now": 27.0, "position": "RP", "il_on": 1, "il_type": "60-day",
         "statcast_plus": 130.0, "milb": {"age": 27.0}}
    chips = OV.overlay_chips(r, "pit", 3.0, disp)
    assert {c["overlay"] for c in chips} >= {"injury", "age", "role", "statcast"}
    for c in chips:
        assert c["on_grade"] is False and "mag" not in c
        assert c["label"] == OV.OVERLAYS[c["overlay"]]["chip"]


# ---------------------------------------------------------------------------
# the committed read

def test_artifact_contract():
    if not ART.exists():
        pytest.skip("data/efv_overlay_oos_eval.json not built")
    doc = json.loads(ART.read_text(encoding="utf-8"))
    assert doc["role"] == "development" and doc["adjudicates"] is False
    assert doc["rule"] == OV.DISPOSITION_RULE and doc["rule_fixed_before_read"] is True
    g = doc["reserved_guard"]
    assert max(g["decision_years"]) < F.R_VM_FIRST_DEBUT_YEAR
    assert g["list_vintages_read"] == []
    assert doc["dispositions"] == OV.dispositions(ART)
    assert set(doc["on_grade"]) | set(doc["to_chips"]) | set(doc["retired"]) == set(OV.OVERLAYS)
    f = doc["frames"]["vm_oos_dev"]
    assert f["verdict"].startswith("development only")
    assert f["n"] == sum(f["n_by_side"].values())
    import efv_progress as P
    assert P.FRAMES["vm_oos_dev"]["role"] == "development"
    assert "vm_oos_dev" not in P.CHART_FRAMES


@pytest.mark.parametrize("mod", ["efv_overlays.py", "tools/efv_overlay_oos_read.py"])
def test_nothing_is_grouped_by_grade(mod):
    banned = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
              "fv_band", "fv_bin")
    tree = ast.parse((ROOT / mod).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else node.attr
                if isinstance(node, ast.Attribute) else None)
        if name:
            assert not any(t in name.lower() for t in banned), name
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}, node.lineno

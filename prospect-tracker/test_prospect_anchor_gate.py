# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for docs/PROSPECT_ANCHOR_GATE.md's lab, tools/prospect_anchor_gate.py (section 15).

Everything here runs on FIXTURES. No test reads a real row, computes a statistic by
consensus-FV cell on real data, or touches the outcome frame: the look is a registered
read (section 14, not before 2026-11-20) and looking early disqualifies. The verdict pins
are added by the look, not here.

Pinned before any result exists: the five cells, the margin formula and the tolerance of
5.4, the look-day m_C ratio field at every cell, H and S partitioning the resolved pool with
no key in both, the power block preceding the cells block, no field from
data/mlb_projections.json (L7), SERVE_PROSPECT_ANCHOR_V2 defaulting to False with the OFF
payload of every 13.1 consumer equal to the pre-change payload, the sub-45 knots
byte-identical across the flag, war_anchor_scale absent from the config in both states, the
closed verdict vocabulary, the mechanical guards (the clock, one look, the label, no free
lever arguments) and the reporting path on a fixture frame with None values and an
unpowered cell.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import math
import os
import random
from pathlib import Path

import pytest

import value_framework as vf

ROOT = Path(__file__).parent
_LAB = None


def lab():
    global _LAB
    if _LAB is None:
        spec = importlib.util.spec_from_file_location(
            "prospect_anchor_gate", ROOT / "tools" / "prospect_anchor_gate.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _LAB = mod
    return _LAB


# The served table at the 2026-09-04 design day (section 0 and 5.4), used to check the
# design-day margins reproduce from the formula. FV 40 is the amended knot of that day.
DESIGN_TABLE = {"20": 0.0007, "25": 0.0019, "30": 0.0040, "35": 0.0069, "40": 0.0710,
                "45": 0.32, "50": 0.68, "55": 0.98, "60": 1.44, "65": 2.01, "70": 2.49,
                "80": 3.5}
# A fixture anchor table in the served file's shape (values are the step J table, used as
# a FIXTURE here: nothing is read against real rows).
FIXTURE_TABLE = {"20": 0.0091, "25": 0.0106, "30": 0.012, "35": 0.0143, "40": 0.0703,
                 "45": 0.31, "50": 0.68, "55": 0.98, "60": 1.5, "65": 1.99, "70": 2.47,
                 "80": 3.5}
STAMPS = {"war_basis": {"provider": "fixture"}, "RESOLVED_THROUGH": 2026,
          "label_window_rule": {"SERVICE_ALIGNED_WINDOW": False, "_SERVICE_YEAR_CUT_MMDD": "04-15"},
          "empirical_anchors_generated_at": "fixture", "empirical_anchors_cohort_window": [2014, 2020]}


def make_frame(seed: int = 7, shift: float = 0.0, scale: float = 1.0, with_nulls: bool = True,
               counts: dict | None = None) -> dict:
    """A synthetic resolved frame. `shift` adds WAR per season to every row's label;
    `scale` multiplies the anchor level the labels are drawn around. Cell counts per
    frame (H, S) default to a design with 60 and 65+ unpowered on H."""
    rng = random.Random(seed)
    counts = counts or {"45": (70, 70), "50": (60, 60), "55": (45, 50), "60": (10, 45),
                        "65+": (3, 8)}
    anchor = lab().interp_anchor(FIXTURE_TABLE)
    rows, cohort = [], []
    ranges = {c[0]: (c[1], c[2]) for c in lab().CELLS}
    n = 0
    for cell, (n_h, n_s) in counts.items():
        lo, hi = ranges[cell]
        for frame, k in (("H", n_h), ("S", n_s)):
            for _ in range(k):
                n += 1
                fv = lo + rng.random() * (hi - lo) * 0.999
                level = anchor(fv) * scale + shift
                war = 6.0 * max(0.0, rng.gauss(level, 0.6 + 0.3 * level)) if rng.random() > 0.35 else 0.0
                key = f"p{n:04d}"
                side = "hit" if rng.random() < 0.5 else "pit"
                year = rng.choice([2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021])
                rows.append({"player_key": key, "side": side, "fv": round(fv, 1), "war": round(war, 3),
                             "censored": False, "year": year, "debut_year": year + 2,
                             "n_sources": rng.choice([1, 1, 2, 3]),
                             "fv_fangraphs": None if rng.random() < 0.4 else round(fv, 1),
                             "fv_mlb_pipeline": round(fv, 1)})
                if frame == "S":
                    cohort.append(key)
    if with_nulls:
        rows += [
            {"player_key": "null_fv", "side": "hit", "fv": None, "war": 3.0, "censored": False, "year": 2016},
            {"player_key": "null_war", "side": "pit", "fv": 50.0, "war": None, "censored": False, "year": 2016},
            {"player_key": "censored_row", "side": "hit", "fv": 55.0, "war": 4.0, "censored": True, "year": 2022},
            {"player_key": None, "side": "hit", "fv": 50.0, "war": 1.0, "censored": False, "year": 2016},
            {"player_key": "sub45", "side": "pit", "fv": 38.0, "war": 0.0, "censored": False, "year": 2015},
            {"player_key": "null_census", "side": "hit", "fv": 46.0, "war": 0.0, "censored": False,
             "year": None, "n_sources": None, "fv_fangraphs": None, "fv_mlb_pipeline": None},
            {"player_key": "nan_fv", "side": "hit", "fv": float("nan"), "war": 1.0, "censored": False, "year": 2016},
        ]
    return {"rows": rows, "cohort_keys": cohort, "anchors": FIXTURE_TABLE, "stamps": STAMPS,
            "identity": {"fixture": True, "cross_side_key_overlap": 0}}


@pytest.fixture(scope="module")
def artifact(tmp_path_factory):
    """One fixture run of the whole reporting path, with the detection and coverage
    simulations on, written through the CLI path to a temp file."""
    d = tmp_path_factory.mktemp("anchor_gate")
    fx = d / "fixture.json"
    fx.write_text(json.dumps(make_frame()), encoding="utf-8")
    out = d / "prospect_anchor_gate.json"
    rc = lab().main(["--fixture", str(fx), "--out", str(out)])
    assert rc == 0
    return json.loads(out.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The criteria (section 15: pinned so they cannot be edited after a result is seen)
# ---------------------------------------------------------------------------
def test_registered_constants_are_the_gates():
    L = lab()
    assert L.CELLS == (("45", 42.5, 47.5, 45.0), ("50", 47.5, 52.5, 50.0),
                       ("55", 52.5, 57.5, 55.0), ("60", 57.5, 62.5, 60.0),
                       ("65+", 62.5, 80.0, 65.0))
    assert L.UPPER_INCLUSIVE == ("65+",)
    assert L.MIN_N == 40 == vf._config()["anchor_calibration"]["min_n_robust"]
    assert (L.B_BOOT, L.SEED, L.CI_LO, L.CI_HI) == (2000, 20260923, 0.05, 0.95)
    assert (L.MDE_Z, L.UNDERPOWERED_MULT, L.HOLM_ALPHA) == (1.645, 2.0, 0.10)
    assert (L.DETECT_B, L.DETECT_SEED, L.DETECT_FLOOR, L.COVERAGE_N_CHECK) == (1000, 20260923, 0.80, 200)
    assert L.RATIO_BOUNDS == (0.75, 1.25)
    assert L.LOOK_FLOOR == dt.date(2026, 11, 20) and L.STEP_Z_LAG_DAYS == 14
    assert L.CONFIRMED_REQUIRES_H == ("45", "50", "55")
    assert L.TARGET_SEASONS == 6
    assert {k: v["m"] for k, v in L.DESIGN_DAY.items()} == {
        "45": 0.152, "50": 0.165, "55": 0.190, "60": 0.258, "65+": 0.263}
    assert (L.V2_KNOTS, L.V2_K_SHRINK, L.V2_FACTOR_CAP, L.V2_MAX_REPAIR_MOVE, L.TWIN_SHARE) == (
        (45.0, 50.0, 55.0, 60.0, 65.0, 70.0), 30.0, (0.5, 2.0), 0.15, 0.75)
    assert L.OOF_YEARS == (2016, 2017, 2018, 2019, 2020, 2021) and L.OOF_MIN_FOLDS_FOR == 4


def test_the_five_cells_and_their_edges():
    L = lab()
    assert L.cell_of(42.5) == "45" and L.cell_of(47.49) == "45" and L.cell_of(47.5) == "50"
    assert L.cell_of(52.5) == "55" and L.cell_of(57.5) == "60" and L.cell_of(62.49) == "60"
    assert L.cell_of(62.5) == "65+" and L.cell_of(70) == "65+" and L.cell_of(80.0) == "65+"
    assert L.cell_of(80.01) is None and L.cell_of(42.49) is None and L.cell_of(40) is None
    assert L.cell_of(None) is None and L.cell_of(float("nan")) is None and L.cell_of("x") is None


def test_margin_formula_and_the_design_day_values():
    """m_C = (anchor(k + 2.5) - anchor(k - 2.5)) / 2 on the served table; on the design-day
    table it reproduces 5.4's illustration, and the ratio field is recorded at every cell."""
    L = lab()
    m = L.margins(L.interp_anchor(DESIGN_TABLE))
    for cell, _lo, _hi, k in L.CELLS:
        a = L.interp_anchor(DESIGN_TABLE)
        assert m[cell]["m_c"] == pytest.approx((a(k + 2.5) - a(k - 2.5)) / 2, abs=1e-9)
        assert m[cell]["m_c"] == pytest.approx(L.DESIGN_DAY[cell]["m"], abs=0.0015), cell
        assert m[cell]["anchor_at_k_minus_2_5"] == pytest.approx(L.DESIGN_DAY[cell]["anchor_lo"], abs=0.0015)
        assert m[cell]["anchor_at_k_plus_2_5"] == pytest.approx(L.DESIGN_DAY[cell]["anchor_hi"], abs=0.0015)
        assert m[cell]["ratio_to_design_day"] == pytest.approx(1.0, abs=0.01)
        assert m[cell]["ratio_inside_pin"] is True
        assert m[cell]["criterion"] == L.CRITERIA["margin"]
    assert L.CRITERIA["margin"] == ("m_C = ( anchor(k_C + 2.5) - anchor(k_C - 2.5) ) / 2, on the "
                                    "served table at the look (for the 65+ cell, at k = 65).")


def test_the_margin_pin_fires_outside_0_75x_to_1_25x():
    L = lab()
    steep = dict(FIXTURE_TABLE, **{"45": 0.31, "50": 1.4})
    m = L.margins(L.interp_anchor(steep))
    assert m["45"]["ratio_inside_pin"] is False
    assert m["45"]["ratio_to_design_day"] > 1.25


def test_h_and_s_partition_the_pool_with_no_key_in_both():
    L = lab()
    frame = make_frame()
    rows, drops = L.prepare_rows(frame["rows"])
    h, s = L.partition(rows, frame["cohort_keys"])
    assert len(h) + len(s) == len(rows)
    assert not ({r["player_key"] for r in h} & {r["player_key"] for r in s})
    assert all(r["player_key"] in set(frame["cohort_keys"]) for r in s)
    assert all(r["player_key"] not in set(frame["cohort_keys"]) for r in h)
    assert drops == {"no_player_key": 1, "fv_missing": 2, "label_missing": 1, "censored": 1,
                     "below_cells": 1}


def test_holm_step_down_at_family_alpha_0_10():
    L = lab()
    out = L.holm({"45": 0.01, "50": 0.04, "55": 0.2})
    assert out["k"] == 3 and out["alpha"] == 0.10
    assert out["rejected"] == ["45", "50"] and out["stopped_at_step"] == 3
    thr = [s["threshold"] for s in out["ordered"]]
    assert thr == pytest.approx([0.10 / 3, 0.10 / 2, 0.10 / 1], abs=1e-6)
    assert L.holm({})["k"] == 0 and L.holm({})["rejected"] == []
    one = L.holm({"60": 0.09})
    assert one["rejected"] == ["60"], "a single powered cell reduces to the interval excluding the band"


# ---------------------------------------------------------------------------
# The artifact on a fixture frame: shape, order, None handling, an unpowered cell
# ---------------------------------------------------------------------------
def test_power_block_precedes_cells_then_verdict(artifact):
    keys = list(artifact.keys())
    assert keys.index("power") < keys.index("cells") < keys.index("verdict")
    assert keys.index("label_stamps") < keys.index("power")
    assert keys.index("identity_checks") < keys.index("power")


def test_every_cell_carries_the_criteria_verbatim_and_the_ratio_field(artifact):
    L = lab()
    for cell in L.CELL_NAMES:
        blk = artifact["cells"][cell]
        for k in ("CONFIRMED", "MISCALIBRATED", "UNDECIDED", "UNPOWERED", "holm", "concordance"):
            assert blk["criteria"][k] == L.CRITERIA[k]
        assert blk["range"] == L.CRITERIA["cells"]
        assert blk["m_c"] == artifact["power"]["margins"][cell]["m_c"]
        assert artifact["power"]["margins"][cell]["ratio_to_design_day"] is not None
        assert "design_day_m_c" in artifact["power"]["margins"][cell]
        for fr in ("H", "S"):
            assert blk[fr]["disposition"] in L.VERDICTS
            assert blk[fr]["zero_convention"] == L.CRITERIA["L4"]
            assert "source_census" in blk[fr] and "per_side" in blk[fr]
            assert set(blk[fr]["per_side"]) >= {"hit", "pit", "resolver", "criterion"}
            p = artifact["power"]["frames"][fr][cell]
            assert p["m_c"] == blk["m_c"] and "mde95" in p and "boot_se" in p
        assert blk["H+S"]["label"] == "READ"
    assert artifact["verdict"] in L.VERDICTS
    assert artifact["verdict_vocabulary"] == list(L.VERDICTS)
    assert artifact["unconditional_sentence"] == L.SENTENCES["UNCONDITIONAL"]
    assert artifact["frames"]["no_key_in_both"] is True
    assert "decision_year_census" in artifact["frames"]["H"]


def test_the_unpowered_cells_publish_n_and_point_estimate_without_an_interval(artifact):
    L = lab()
    h60 = artifact["cells"]["60"]["H"]
    assert h60["n"] < L.MIN_N and h60["disposition"] == "UNPOWERED"
    assert h60["ci90"] is None and h60["d_c"] is not None and h60["mde95"] is None
    assert h60["sentence"].startswith("The resolved holdout carries 10 prospects at FV 60")
    assert "which can fail the anchor and cannot confirm it" in h60["sentence_10_4"]
    h65 = artifact["cells"]["65+"]["H"]
    assert h65["n"] == 3 and h65["disposition"] == "UNPOWERED" and h65["ci90"] is None
    # the power block says which frame is powered at each cell
    assert artifact["power"]["frames"]["H"]["60"]["powered_by_n"] is False
    assert artifact["power"]["frames"]["S"]["60"]["powered_by_n"] is True
    # powered cells carry the detection and coverage checks; unpowered ones do not
    p45 = artifact["power"]["frames"]["H"]["45"]
    assert p45["detection"]["b"] == 1000 and p45["detection"]["seed"] == 20260923
    assert 0.0 <= p45["detection"]["fraction_miscalibrated"] <= 1.0
    assert p45["coverage"]["n_check"] == 200 and 0.0 <= p45["coverage"]["coverage"] <= 1.0
    assert artifact["power"]["frames"]["H"]["60"]["detection"] is None
    assert artifact["power"]["criterion_mde95"] == L.CRITERIA["power_MDE95"]


def test_none_values_are_carried_or_dropped_never_crash(artifact):
    fi = artifact["frame_integrity"]
    assert fi["dropped"]["fv_missing"] == 2 and fi["dropped"]["label_missing"] == 1
    assert fi["dropped"]["censored"] == 1 and fi["dropped"]["no_player_key"] == 1
    assert fi["rows_below_cells"] == 1
    c45 = artifact["cells"]["45"]["H"]["source_census"]
    assert c45["n"] >= 70 and c45["n"] - c45["n_sources_known"] == 1, "the null-census row is carried, not dropped"
    assert artifact["frames"]["H"]["decision_year_census"].get("unknown") == 1


def test_s_frame_never_reads_confirmed_and_pooled_is_a_read(artifact):
    L = lab()
    for cell in L.CELL_NAMES:
        assert artifact["cells"][cell]["S"]["disposition"] != "CONFIRMED"
        assert artifact["cells"][cell]["H+S"]["label"] == "READ"
        assert "disposition" not in artifact["cells"][cell]["H+S"]
    assert artifact["families"]["H"]["alpha"] == 0.10 and artifact["families"]["S"]["alpha"] == 0.10
    assert artifact["families"]["combined_false_miscalibrated_rate_at_most"] == 0.19


def test_mde95_is_the_bootstrap_se_not_the_residual_sd(artifact):
    p = artifact["power"]["frames"]["H"]["45"]
    assert p["mde95"] == pytest.approx(1.645 * p["boot_se"], abs=2e-6)
    assert p["boot_se"] < p["residual_sd"]


def test_the_verdict_rule_on_a_planted_level_error():
    """A frame built around 1.6x the anchor must fail it (S veto or H), and the
    one-parameter reading is then published; a frame built on the anchor itself does not
    read MISCALIBRATED."""
    L = lab()
    hot = make_frame(seed=11, shift=1.5, with_nulls=False)
    art = L.build_artifact(hot, L.interp_anchor(FIXTURE_TABLE), stamps=STAMPS,
                           identity={"fixture": True}, detect=False)
    assert art["verdict"] == "MISCALIBRATED"
    assert art["one_parameter_reading"]["criterion"] == L.CRITERIA["one_parameter"]
    assert "MISCALIBRATED LOW" in art["sentence"]
    mis = [(fr, c) for c in L.CELL_NAMES for fr in ("H", "S")
           if art["cells"][c][fr]["disposition"] == "MISCALIBRATED"]
    assert mis and all(art["cells"][c][fr]["sign"] == "positive" for fr, c in mis)
    calm = make_frame(seed=11, with_nulls=False)
    art2 = L.build_artifact(calm, L.interp_anchor(FIXTURE_TABLE), stamps=STAMPS,
                            identity={"fixture": True}, detect=False)
    assert art2["verdict"] in ("CONFIRMED", "UNDECIDED")
    assert art2["one_parameter_reading"] is None


def test_concordance_rule_reads_undecided_with_the_annotation():
    """H planted far above the anchor and S planted far below at the same cell: the H
    MISCALIBRATED is removed by the concordance rule and the cell carries
    SOURCE_SCALE_SUSPECT, which is an annotation and never a verdict."""
    L = lab()
    h = make_frame(seed=3, shift=1.2, with_nulls=False, counts={"50": (80, 0)})
    s = make_frame(seed=4, shift=-0.9, with_nulls=False, counts={"50": (0, 80)})
    rows = [dict(r, player_key="h_" + r["player_key"]) for r in h["rows"]] + \
           [dict(r, player_key="s_" + r["player_key"]) for r in s["rows"]]
    keys = ["s_" + k for k in s["cohort_keys"]]
    art = L.build_artifact({"rows": rows, "cohort_keys": keys}, L.interp_anchor(FIXTURE_TABLE),
                           stamps=STAMPS, identity={"fixture": True}, detect=False)
    c = art["cells"]["50"]
    assert c["H"]["disposition"] == "UNDECIDED" and c["H"]["annotation"] == "SOURCE_SCALE_SUSPECT"
    assert art["concordance_fired"] == ["50"]
    assert c["H"]["sentence"].startswith("Cell 50 reads MISCALIBRATED on the holdout frame")
    assert "SOURCE_SCALE_SUSPECT" not in L.VERDICTS and L.ANNOTATION == "SOURCE_SCALE_SUSPECT"
    # the S veto at the same cell stands untouched by the rule
    assert c["S"]["disposition"] == "MISCALIBRATED" and art["verdict"] == "MISCALIBRATED"


def test_the_fixture_run_never_writes_the_real_artifact(tmp_path):
    L = lab()
    fx = tmp_path / "f.json"
    fx.write_text(json.dumps(make_frame()), encoding="utf-8")
    with pytest.raises(L.LabRefused, match="refuses to write the real artifact path"):
        L.run_fixture(fx, L.ARTIFACT, detect=False)


# ---------------------------------------------------------------------------
# L7, the fit ban and the free-argument ban
# ---------------------------------------------------------------------------
def test_no_field_derives_from_mlb_projections(artifact):
    L = lab()
    # no KEY of the artifact derives from a projection input ...
    for key_path in L._walk_keys(artifact):
        assert not any(b.lower() in key_path.lower() for b in L._BANNED_KEYS), key_path
    # ... and the only mentions in the text are the L7 criterion and the ban's own field
    text = json.dumps(artifact).replace(L.CRITERIA["L7"], "").replace(L.FORBIDDEN_INPUT, "")
    assert "mlb_projections" not in text and "warChamp" not in text and "proj_ml" not in text
    assert artifact["frame_integrity"]["L7"] == L.CRITERIA["L7"]
    src = (ROOT / "tools" / "prospect_anchor_gate.py").read_text(encoding="utf-8")
    assert "proj_export" not in src and "import proj_ml" not in src and "warChamp\"]" not in src
    # the banned path is a string the lab names (the constant, the criterion, two docstrings)
    # and never a path it opens
    assert 'mlb_projections.json"' not in src.replace('FORBIDDEN_INPUT = "data/mlb_projections.json"', "")
    assert "mlb_projections" not in "".join(ln for ln in src.splitlines() if "read_text" in ln or "open(" in ln)


def test_the_artifact_writer_refuses_a_projection_derived_key(tmp_path):
    L = lab()
    with pytest.raises(L.LabRefused, match="projection-derived field"):
        L.write_artifact({"power": {}, "cells": {"45": {"warChamp": 1.0}}}, tmp_path / "x.json")
    with pytest.raises(L.LabRefused, match="projection-derived field"):
        L.write_artifact({"proj_ml_mean": 1.0}, tmp_path / "x.json")


def test_the_lab_never_calls_value_framework_fit():
    src = (ROOT / "tools" / "prospect_anchor_gate.py").read_text(encoding="utf-8")
    assert "subprocess" not in src
    assert "derive_empirical_war_anchors(" not in src
    assert "fit_proportional_odds" not in src and "--fit\"" not in src and "'--fit'" not in src
    # every other mention of --fit is the ban itself, stated with the word never
    for ln in src.splitlines():
        if "--fit" in ln and "--fit-v2" not in ln and "fit_v2" not in ln:
            assert "never" in ln.lower(), ln


def test_fit_v2_takes_no_free_k_prior_side_table_or_knots():
    L = lab()
    for bad in (["--fit-v2", "--k", "10"], ["--fit-v2", "--prior", "x"],
                ["--fit-v2", "--knots", "45,50"], ["--fit-v2", "--side", "hit"]):
        with pytest.raises(SystemExit):
            L.main(bad)
    assert L.main(["--fit-v2", "--fixture", "x"]) == 2
    assert L.main(["--fixture", "x"]) == 2


# ---------------------------------------------------------------------------
# The guards: the clock, one look, the label
# ---------------------------------------------------------------------------
EPOCH_TEXT = ("# gate\n\n## 3. Preconditions\n\n### 2026-09-30: DISCLOSURE step Z expected\n\n"
              "## 9. Results\n\n### 2026-10-02: the arm set is fixed\n\n"
              "### 2026-10-03: step Z, the fWAR label epoch's results\n\ntext\n")


def test_step_z_entry_reads_part_9_only():
    L = lab()
    assert L.step_z_entry(EPOCH_TEXT) == "2026-10-03"
    assert L.step_z_entry(EPOCH_TEXT.split("## 9. Results")[0]) is None
    no_z = EPOCH_TEXT.replace("step Z, the fWAR", "step Y, the fWAR")
    assert L.step_z_entry(no_z) is None
    assert L.look_floor("2026-10-03") == dt.date(2026, 11, 20)
    assert L.look_floor("2026-11-15") == dt.date(2026, 11, 29)
    assert L.look_floor(None) is None


def test_the_real_epoch_document_records_step_z():
    L = lab()
    z = L.step_z_entry()
    assert z == "2026-10-03"
    assert L.look_floor(z) == dt.date(2026, 11, 20)


def test_the_clock_refuses_before_the_floor_and_on_look_days():
    L = lab()
    with pytest.raises(L.LabRefused, match="before the look floor"):
        L.check_clock(dt.date(2026, 11, 19), step_z="2026-10-03")
    with pytest.raises(L.LabRefused, match="before the look floor"):
        L.check_clock(dt.date(2026, 10, 8), step_z="2026-10-03")
    with pytest.raises(L.LabRefused, match="before the look floor"):
        L.check_clock(dt.date(2026, 11, 25), step_z="2026-11-15")
    for day in (dt.date(2026, 10, 23), dt.date(2026, 11, 6), dt.date(2026, 11, 13), dt.date(2026, 12, 1)):
        with pytest.raises(L.LabRefused, match="registered look day"):
            L.check_clock(day, step_z="2026-10-01")
    with pytest.raises(L.LabRefused, match="no step Z entry"):
        _no_step_z(L)
    ok = L.check_clock(dt.date(2026, 11, 20), step_z="2026-10-03")
    assert ok == {"today": "2026-11-20", "step_z_entry": "2026-10-03", "look_floor": "2026-11-20",
                  "early_read": None}


def test_the_owner_waiver_records_an_early_read_and_waives_only_the_floor():
    """EW3-5 (owner 2026-10-14): the registered look date is waived. The waiver is carried
    only by the explicit switch; with it a look before the floor proceeds and the clock
    block records an OWNER-WAIVED EARLY READ. It never waives step Z or a blocked day."""
    L = lab()
    assert "EW3-5" in L.OWNER_WAIVER
    ok = L.check_clock(dt.date(2026, 10, 14), step_z="2026-10-03", owner_waiver=L.OWNER_WAIVER)
    assert ok["today"] == "2026-10-14" and ok["look_floor"] == "2026-11-20"
    er = ok["early_read"]
    assert er["owner_waived"] is True and er["waiver"] == L.OWNER_WAIVER
    assert er["registered_floor"] == "2026-11-20" and er["days_before_floor"] == 37
    assert er["note"].startswith("OWNER-WAIVED EARLY READ")
    # on or after the floor the waiver changes nothing
    assert L.check_clock(dt.date(2026, 11, 20), step_z="2026-10-03", owner_waiver=L.OWNER_WAIVER)["early_read"] is None
    # without the switch the floor refuses as registered
    with pytest.raises(L.LabRefused, match="before the look floor"):
        L.check_clock(dt.date(2026, 10, 14), step_z="2026-10-03")
    # a blocked day and a missing step Z entry are never waived
    with pytest.raises(L.LabRefused, match="registered look day"):
        L.check_clock(dt.date(2026, 10, 23), step_z="2026-10-03", owner_waiver=L.OWNER_WAIVER)
    orig = L.step_z_entry
    L.step_z_entry = lambda text=None: None
    try:
        with pytest.raises(L.LabRefused, match="no step Z entry"):
            L.check_clock(dt.date(2026, 10, 14), owner_waiver=L.OWNER_WAIVER)
    finally:
        L.step_z_entry = orig
    # the switch is a flag, not a value: it takes no argument of its own
    with pytest.raises(SystemExit):
        L.main(["--owner-waived-early-read", "x"])


def _no_step_z(L):
    """check_clock with the epoch document read as one without a step Z entry."""
    orig = L.step_z_entry
    L.step_z_entry = lambda text=None: None
    try:
        L.check_clock(dt.date(2026, 11, 20))
    finally:
        L.step_z_entry = orig


def test_one_look_refuses_when_the_artifact_exists_or_section_18_is_written(tmp_path):
    L = lab()
    gate = L.GATE_DOC.read_text(encoding="utf-8")
    empty = gate.split("## 18. Results", 1)[0] + "## 18. Results\n\n**EMPTY AT REGISTRATION.**\n\nNo cell mean.\n\n---\n"
    assert L.section_18_is_empty(empty) is True
    written = empty.replace("No cell mean.", "No cell mean.\n\n### 2026-11-20: the look\n\nverdict")
    assert L.section_18_is_empty(written) is False
    assert L.section_18_is_empty(empty.replace("**EMPTY AT REGISTRATION.**", "")) is False
    with pytest.raises(L.LabRefused, match="section 18 is not empty"):
        L.check_one_look(tmp_path / "absent.json", written)
    present = tmp_path / "prospect_anchor_gate.json"
    present.write_text("{}", encoding="utf-8")
    with pytest.raises(L.LabRefused, match="exists; the look is taken once"):
        L.check_one_look(present, empty)
    L.check_one_look(tmp_path / "absent.json", empty)


def test_the_two_one_look_signals_agree_on_disk():
    """Before the look: section 18 empty and no artifact. After it: both written. Never one
    without the other."""
    L = lab()
    assert L.section_18_is_empty() == (not L.ARTIFACT.exists())


def test_the_label_guard_refuses_ewar_v2_and_a_stale_refit():
    L = lab()
    ea = {"generated_at": "2026-10-03T16:35:15", "cohort_window": [2014, 2020], "n_cohort": 3463}
    good = {"hit": "first-6-season summed WAR (fwar); resolved<= 2026", "pit": "first-6-season summed WAR (fwar); resolved<= 2026"}
    L.check_label("fwar", good, ea, "2026-10-03")
    with pytest.raises(L.LabRefused, match="not fwar"):
        L.check_label("ewar_v2", good, ea, "2026-10-03")
    with pytest.raises(L.LabRefused, match="not the fwar label"):
        L.check_label("fwar", {"hit": good["hit"], "pit": "first-6-season summed WAR (ewar_v2)"}, ea, "2026-10-03")
    with pytest.raises(L.LabRefused, match="predates the step Z entry"):
        L.check_label("fwar", good, dict(ea, generated_at="2026-09-04T10:00:00"), "2026-10-03")
    with pytest.raises(L.LabRefused, match="names no cohort_window"):
        L.check_label("fwar", good, dict(ea, cohort_window=None), "2026-10-03")


# ---------------------------------------------------------------------------
# The lever mode (section 11): refusal first, then the fixture path
# ---------------------------------------------------------------------------
def _fitted_copy(tmp_path: Path) -> Path:
    fitted = json.loads(L_FITTED().read_text(encoding="utf-8"))
    fitted.pop("empirical_anchors_v2", None)
    fitted["empirical_anchors"] = dict(fitted["empirical_anchors"], anchors=FIXTURE_TABLE)
    p = tmp_path / "value_framework_fitted.json"
    p.write_text(json.dumps(fitted, indent=2, sort_keys=True), encoding="utf-8")
    return p


def L_FITTED() -> Path:
    return lab().FITTED_PATH


def test_fit_v2_refuses_unless_the_verdict_reads_miscalibrated(tmp_path):
    L = lab()
    fitted = _fitted_copy(tmp_path)
    with pytest.raises(L.LabRefused, match="no artifact"):
        L.fit_v2_mode(tmp_path / "none.json", fitted, frame=make_frame(), write=False)
    art = tmp_path / "art.json"
    for verdict in ("CONFIRMED", "UNDECIDED", "NOT_AVAILABLE", "VOID"):
        art.write_text(json.dumps({"verdict": verdict, "lever": None}), encoding="utf-8")
        with pytest.raises(L.LabRefused, match="not MISCALIBRATED"):
            L.fit_v2_mode(art, fitted, frame=make_frame(), write=False)


def test_fit_v2_on_a_fixture_refuses_a_2x_correction_and_writes_nothing(tmp_path):
    L = lab()
    fitted = _fitted_copy(tmp_path)
    before = fitted.read_bytes()
    frame = make_frame(seed=5, shift=1.0, with_nulls=False)
    art_path = tmp_path / "art.json"
    art_path.write_text(json.dumps({"verdict": "MISCALIBRATED", "lever": None,
                                    "label_stamps": {"war_basis": {"provider": "fixture"}}}),
                        encoding="utf-8")
    block = L.fit_v2_mode(art_path, fitted, frame=frame, write=True)
    assert block["result"] == "REFUSED" and block["refused"]["knot"] == 45
    assert block["refused"]["sentence"].startswith("The recalibrated anchor moves knot 45 by a factor of")
    assert fitted.read_bytes() == before, "a refused lever writes nothing to the fitted file"
    art = json.loads(art_path.read_text(encoding="utf-8"))
    assert art["lever"]["result"] == "REFUSED"
    with pytest.raises(L.LabRefused, match="already carries a lever block"):
        L.fit_v2_mode(art_path, fitted, frame=frame, write=False)


def test_fit_v2_on_a_fixture_level_error_fits_the_twin_and_checks_out_of_fold(tmp_path):
    L = lab()
    fitted = _fitted_copy(tmp_path)
    frame = make_frame(seed=5, scale=1.45, with_nulls=False,
                       counts={"45": (80, 80), "50": (60, 60), "55": (50, 50), "60": (30, 40), "65+": (10, 12)})
    art_path = tmp_path / "art.json"
    art_path.write_text(json.dumps({"verdict": "MISCALIBRATED", "lever": None,
                                    "label_stamps": {"war_basis": {"provider": "fixture"}}}),
                        encoding="utf-8")
    orig_keys = set(json.loads(fitted.read_text(encoding="utf-8")))
    block = L.fit_v2_mode(art_path, fitted, frame=frame, write=True)
    assert block["result"] in ("PASS", "NULL")
    assert block["refused"] is None
    fit = block["fit"]
    for k in ("20", "25", "30", "35", "40"):
        assert fit["anchors"][k] == FIXTURE_TABLE[k], "sub-45 knots byte for byte"
    assert fit["anchors"]["80"] == round(fit["prior_per_knot"]["80"], 3), "80 is the prior alone"
    assert fit["k_shrink"] == 30.0 and set(fit["rows_per_knot"]) == {"45", "50", "55", "60", "65", "70"}
    vals = [fit["anchors"][k] for k in ("45", "50", "55", "60", "65", "70", "80")]
    assert vals == sorted(vals), "monotone non-decreasing"
    assert all(len(str(v).split(".")[-1]) <= 3 for v in vals), "three decimals"
    tw = block["twin"]
    assert tw["form"] in ("table", "scalar") and tw["rule"] == 0.75
    assert "slope_40_to_45_pre" in tw and "slope_40_to_45_post" in tw
    oof = block["out_of_fold"]
    assert oof["b"] == 2000 and oof["seed"] == 20260923 and oof["min_folds_for"] == 4
    assert [f["year"] for f in oof["folds"]] == [2016, 2017, 2018, 2019, 2020, 2021]
    assert all("served_partially_in_sample" in f for f in oof["folds"] if f["scored"])
    assert oof["comparator"].startswith("the incumbent RULE")
    written = json.loads(fitted.read_text(encoding="utf-8"))
    if block["result"] == "PASS":
        v2 = written["empirical_anchors_v2"]
        assert v2["form"] in ("table", "scalar")
        if v2["form"] == "scalar":
            assert "scale" in v2
        for k in ("20", "25", "30", "35", "40"):
            assert v2["anchors"][k] == written["empirical_anchors"]["anchors"][k]
        assert set(written) == orig_keys | {"empirical_anchors_v2"}, "exactly one key written"
    else:
        assert "empirical_anchors_v2" not in written
        assert block["sentence"].startswith("The recalibrated anchor does not beat the incumbent rule")


# ---------------------------------------------------------------------------
# The SERVE flag (section 12.1): default False, one read site, OFF payload byte for byte
# ---------------------------------------------------------------------------
def _legacy_fv_to_6yr_avg_war(fv):
    """The pre-change body of value_framework.fv_to_6yr_avg_war, copied verbatim, so the
    OFF payload is compared against what served before the flag existed."""
    if fv is None:
        return None
    try:
        f = float(fv)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    cal = vf._config().get("anchor_calibration", {})
    fitted_anchors = (vf._fitted().get("empirical_anchors") or {}).get("anchors") if cal.get("use_empirical") else None
    anchor = fitted_anchors or vf._config()["fv_to_6yr_avg_war"]
    pts = sorted((float(k), float(v)) for k, v in anchor.items())
    if f <= pts[0][0]:
        return pts[0][1]
    if f >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= f <= x1:
            t = (f - x0) / (x1 - x0)
            return y0 * (1 - t) + y1 * t
    return pts[-1][1]


GRID = [x / 2.0 for x in range(40, 161)] + [19.0, 20.0, 81.0, 100.0]


def _consumer_payload() -> dict:
    """The 13.1 consumers reachable without the DB, both sides, over the FV grid."""
    vf._reset_caches()
    out = {}
    for fv in GRID:
        out[f"anchor:{fv}"] = vf.fv_to_6yr_avg_war(fv)
        for is_pit, pos in ((False, "SS"), (True, "RHP")):
            tag = f"{fv}:{pos}"
            out[f"e6:{tag}"] = vf.expected_six_year_avg_war(fv, is_pit)
            out[f"surv:{tag}"] = vf.survivor_expected_war(fv, is_pit)
            out[f"scale:{tag}"] = vf._war_scale_for(fv, vf._role_key(is_pit))
            out[f"sv:{tag}"] = vf.surplus_value_mm(fv, is_pit, pos)
            out[f"esu:{tag}"] = vf.expected_surplus_usd(fv, is_pit, pos)
            out[f"pes:{tag}"] = vf.point_estimate_surplus_usd(fv, is_pit, pos)
    for war in (0.0, 0.5, 3.0, 10.0, 25.0):
        for is_pit in (False, True):
            out[f"rif:{war}:{is_pit}"] = vf.realized_implied_fv(war, is_pit)
    for fv in (45.0, 55.0, 62.0, 70.0):
        for is_pit, pos in ((False, "SS"), (True, "RHP")):
            out[f"ci:{fv}:{pos}"] = vf.sv_credible_interval(fv, is_pit, pos, draws=200, seed=7)
            out[f"dpv:{fv}:{pos}"] = vf.debuted_player_value(fv, is_pit, pos, observed_war=2.0,
                                                           service_time=1.0, draws=200, seed=7)
    return out


def test_serve_flag_defaults_false_and_is_read_at_one_site():
    assert vf.SERVE_PROSPECT_ANCHOR_V2 is False
    src = (ROOT / "value_framework.py").read_text(encoding="utf-8")
    assert src.count("EEPHUS_PROSPECT_ANCHOR_V2") == 2, "the env name appears on the flag line and at its one read site"
    code_lines = [ln for ln in src.splitlines()
                  if "SERVE_PROSPECT_ANCHOR_V2" in ln and not ln.strip().startswith("#")]
    assert len(code_lines) == 2, code_lines
    assert code_lines[0].startswith("SERVE_PROSPECT_ANCHOR_V2 = False"), "one definition"
    assert "v2_on = (SERVE_PROSPECT_ANCHOR_V2 if env is None" in code_lines[1], "one read"
    body = src.split("def fv_to_6yr_avg_war", 1)[1].split("\ndef ", 1)[0]
    assert "SERVE_PROSPECT_ANCHOR_V2" in body and "empirical_anchors_v2" in body
    assert src.count("empirical_anchors_v2") == 2, "the v2 key is read inside fv_to_6yr_avg_war and named in the 12.1 comment, nowhere else"
    # 12.1's comment block, verbatim
    for line in ("# Whether the recalibrated realized anchor is SERVED. Set from the verdict in",
                 "# False: fv_to_6yr_avg_war reads empirical_anchors.anchors, reproducing today's",
                 "# key records. ONE read site. war_anchor_scale is never the vehicle.",
                 "SERVE_PROSPECT_ANCHOR_V2 = False     # env override EEPHUS_PROSPECT_ANCHOR_V2, read at call time"):
        assert line in src, line
    for mod in ("efv_score", "proj_export", "storage", "comps_engine", "farm_grade_backtest"):
        text = (ROOT / f"{mod}.py").read_text(encoding="utf-8")
        assert "SERVE_PROSPECT_ANCHOR_V2" not in text and "empirical_anchors_v2" not in text, mod


def test_off_payload_equals_the_pre_change_payload(monkeypatch):
    monkeypatch.delenv("EEPHUS_PROSPECT_ANCHOR_V2", raising=False)
    assert vf._config()["anchor_calibration"]["use_empirical"] is True
    assert vf._fitted().get("empirical_anchors", {}).get("anchors"), "the served table is the fitted one"
    for fv in GRID + [None, "x", float("nan"), float("inf"), "55", 55]:
        assert vf.fv_to_6yr_avg_war(fv) == _legacy_fv_to_6yr_avg_war(fv), fv
    live = _consumer_payload()
    monkeypatch.setattr(vf, "fv_to_6yr_avg_war", _legacy_fv_to_6yr_avg_war)
    legacy = _consumer_payload()
    monkeypatch.undo()
    vf._reset_caches()
    assert json.dumps(live, sort_keys=True) == json.dumps(legacy, sort_keys=True)
    # the env override, with no empirical_anchors_v2 key on disk, moves nothing either
    assert "empirical_anchors_v2" not in vf._fitted()
    monkeypatch.setenv("EEPHUS_PROSPECT_ANCHOR_V2", "1")
    forced = _consumer_payload()
    monkeypatch.delenv("EEPHUS_PROSPECT_ANCHOR_V2")
    vf._reset_caches()
    assert json.dumps(forced, sort_keys=True) == json.dumps(live, sort_keys=True)


def test_sub45_knots_are_byte_identical_across_the_flag(monkeypatch):
    real = vf._fitted()
    served = dict(real["empirical_anchors"]["anchors"])
    v2 = {k: (v if float(k) < 45 else round(float(v) * 1.2, 3)) for k, v in served.items()}
    doc = dict(real, empirical_anchors_v2={"form": "scalar", "scale": 1.2, "anchors": v2})
    monkeypatch.setattr(vf, "_fitted", lambda: doc)
    vf._fv_war_scale.cache_clear()
    monkeypatch.setenv("EEPHUS_PROSPECT_ANCHOR_V2", "1")
    for k in ("20", "25", "30", "35", "40"):
        assert vf.fv_to_6yr_avg_war(float(k)) == served[k], k
    assert vf.fv_to_6yr_avg_war(60.0) == pytest.approx(served["60"] * 1.2)
    assert vf.fv_to_6yr_avg_war(40.0) == served["40"]
    monkeypatch.setenv("EEPHUS_PROSPECT_ANCHOR_V2", "0")
    for k in ("20", "25", "30", "35", "40", "45", "60", "80"):
        assert vf.fv_to_6yr_avg_war(float(k)) == served[k], k
    monkeypatch.undo()
    vf._reset_caches()
    assert vf.fv_to_6yr_avg_war(60.0) == served["60"]
    assert "war_anchor_scale" not in vf._config()


def test_war_anchor_scale_is_absent_in_both_flag_states(monkeypatch):
    assert "war_anchor_scale" not in vf._config()
    assert vf._war_anchor_scale_for("hitter") == 1.0 and vf._war_anchor_scale_for("pitcher") == 1.0
    monkeypatch.setenv("EEPHUS_PROSPECT_ANCHOR_V2", "1")
    vf._reset_caches()
    assert "war_anchor_scale" not in vf._config()
    assert vf._war_anchor_scale_for("hitter") == 1.0 and vf._war_anchor_scale_for("pitcher") == 1.0
    monkeypatch.delenv("EEPHUS_PROSPECT_ANCHOR_V2")
    vf._reset_caches()


def test_empirical_anchors_v2_exists_only_under_a_miscalibrated_verdict():
    """The served fitted file carries no v2 key while no verdict reads MISCALIBRATED."""
    L = lab()
    fitted = json.loads(L.FITTED_PATH.read_text(encoding="utf-8"))
    if L.ARTIFACT.exists():
        verdict = json.loads(L.ARTIFACT.read_text(encoding="utf-8")).get("verdict")
        if "empirical_anchors_v2" in fitted:
            assert verdict == "MISCALIBRATED"
            v2 = fitted["empirical_anchors_v2"]
            assert v2["form"] in ("table", "scalar")
            for k in ("20", "25", "30", "35", "40"):
                assert v2["anchors"][k] == fitted["empirical_anchors"]["anchors"][k]
    else:
        assert "empirical_anchors_v2" not in fitted


def test_the_registry_row_points_at_the_gate_with_no_artifact_yet():
    import model_registry as mr
    rows = {m["model_id"]: m for m in mr.load()["models"]}
    row = rows["prospect_anchor"]
    assert "docs/PROSPECT_ANCHOR_GATE.md" in row["notes"]
    assert row["verdict"] == "unvalidated" and row["eval_artifact"] in (None, "")
    prose = f"{row['baseline']} {row['metric']} {row['notes']}".lower()
    assert "registered" in prose and "2026-11-20" in prose and "separately gated" in prose
    assert rows["prospect_surplus"]["verdict"] == "validated", "prospect_surplus is untouched"

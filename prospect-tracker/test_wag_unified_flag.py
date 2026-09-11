# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""storage.WAG_UNIFIED: one WAG definition (design audit F25; audit L13-03, L13-04, with
L13-01 and L13-06 folded in). ON since 2026-09-11 (owner decision 14b).

ON must make every surface read the baked engine block. OFF rolls back decision 14b, the
WAG DEFINITION, and must reproduce the pre-flip definitions exactly; both halves are
asserted here, server and client. OFF does not roll back decision 14c: the measured
career-WAR exposure the engine gate reads is independent of this flag (last test).
"""
from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

import storage
import value_framework as vf

ROOT = Path(__file__).parent


@contextlib.contextmanager
def _flag(on: bool):
    old = storage.WAG_UNIFIED
    storage.WAG_UNIFIED = on
    try:
        yield
    finally:
        storage.WAG_UNIFIED = old


def _grad(war_per_season: float, fv: float, *, seasons: int = 2, pa: int = 900,
          age: float = 25.0, churn: int = 0, position: str = "SS") -> dict:
    return {
        "career_war": {"career_war": war_per_season * seasons, "war_seasons_count": seasons,
                       "war_per_yr": war_per_season},
        "fv_close_raw": fv, "fv_close": fv, "position": position, "age": age,
        "current_level": "MLB",
        "transactions": [{"kind": "dfa"}] * churn,
        "career_stats": [{"level": "MLB", "pa": pa}],
    }


GRID = [_grad(w, fv, churn=c, age=a) for w in (-0.4, 0.3, 1.1, 2.6) for fv in (30, 45, 55, 65)
        for c, a in ((0, 24.0), (2, 29.0))]
BLOCK = {"wag": {"regressed_wag": 9.9, "below_meaningful_exposure": False, "boom_label": "boom"}}


def test_the_flag_ships_on():
    """The owner flipped it now, not at the label epoch (decision 14b, 2026-09-11)."""
    assert storage.WAG_UNIFIED is True
    assert storage.WAG_DEFINITION == "engine_at_debut"


# ------------------------------------------------------------------ OFF = unchanged
def test_off_the_survivor_read_is_the_unclamped_curve():
    with _flag(False):
        for fv in (20, 25, 30, 34.9, 35, 45, 60, 80):
            for isp in (False, True):
                assert storage._fv_to_expected_war_per_yr(fv, isp) == round(
                    float(vf.survivor_expected_war(fv, isp)), 3)


def test_off_the_positive_branch_keeps_its_level_term():
    with _flag(False):
        for g in GRID:
            exp = storage._fv_to_expected_war_per_yr(g["fv_close_raw"])
            d = g["career_war"]["war_per_yr"] - exp
            want = round((d * 0.70 + g["career_war"]["war_per_yr"] * 0.30)
                         * storage._graduate_outcome_penalty(g), 2) if d > 0 else round(d, 2)
            assert storage._grad_wag(g) == want


def test_off_the_farm_reads_the_two_legacy_calls_and_ignores_the_block():
    with _flag(False):
        for g in GRID:
            label_payload = {k: g[k] for k in ("career_war", "fv_close_raw", "fv_close", "career_stats")}
            assert storage._farm_grad_wag_and_label(g, label_payload, BLOCK) == (
                storage._grad_wag(g), storage._compute_boom_bust(label_payload))


def test_off_the_debuted_block_and_the_boot_are_unchanged():
    with _flag(False):
        blk = storage._build_debuted_payload(
            50, False, "SS", age=26.0,
            career_war={"career_war": 3.0, "seasons": {"2024": 1.5, "2025": 1.5}},
            career_stats=[{"level": "MLB", "ab": 900}], wag_fv=50)
    assert "expected_rate" not in blk["wag"] and "definition" not in blk["wag"]
    src = (ROOT / "storage.py").read_text(encoding="utf-8")
    assert '**({"wag_definition": WAG_DEFINITION} if WAG_UNIFIED else {}),' in src


# ------------------------------------------------------------------ ON = one definition
def test_on_the_farm_grades_on_the_baked_block():
    with _flag(True):
        assert storage._farm_grad_wag_and_label({}, {}, BLOCK) == (9.9, "boom")
        thin = {"wag": {"regressed_wag": 0.0, "below_meaningful_exposure": True,
                        "boom_label": "unsettled"}}
        assert storage._farm_grad_wag_and_label({}, {}, thin) == (None, "unsettled")
        assert storage._farm_grad_wag_and_label({}, {}, None) == (None, "unsettled")


def test_on_the_block_carries_its_baseline_and_definition():
    kw = dict(age=26.0, career_war={"career_war": 3.0, "seasons": {"2024": 1.5, "2025": 1.5}},
              career_stats=[{"level": "MLB", "ab": 900}], wag_fv=50)
    with _flag(True):
        blk = storage._build_debuted_payload(50, False, "SS", **kw)
    ref = vf.wag(50, False, 3.0, position="SS", service_years=2.0, exposure_pa=900 * 1.1,
                 exposure_ip=None, age=26.0)
    assert blk["wag"]["definition"] == "engine_at_debut"
    assert blk["wag"]["expected_rate"] == ref["expected_rate"]
    assert blk["wag"]["regressed_wag"] == ref["regressed_wag"]


def test_on_the_survivor_read_is_monotone_l13_01():
    with _flag(False):
        assert storage._fv_to_expected_war_per_yr(20) > storage._fv_to_expected_war_per_yr(35)
    with _flag(True):
        vals = [storage._fv_to_expected_war_per_yr(fv) for fv in range(20, 81)]
        assert all(b >= a for a, b in zip(vals, vals[1:]))
        assert storage._fv_to_expected_war_per_yr(20) == storage._fv_to_expected_war_per_yr(35)
        assert storage._fv_to_expected_war_per_yr(0) is None


def test_the_flag_does_not_roll_back_the_exposure_wiring():
    """Decision 14c is not behind WAG_UNIFIED: with the flag off the engine block still
    gates on the career-WAR stints where career_stats measures nothing, and says so."""
    cw = {"career_war": 3.0, "seasons": {"2024": 1.5, "2025": 1.5},
          "seasons_pa": {"2024": 100, "2025": 50}, "seasons_ip": {"2024": 0.0, "2025": 0.0}}
    got = {}
    for on in (False, True):
        with _flag(on):
            got[on] = storage._build_debuted_payload(50, False, "SS", age=25.0, career_war=cw,
                                                     career_stats=[], wag_fv=50)["wag"]
    for w in got.values():
        assert (w["exposure_source"], w["exposure_load"]) == ("war_daily", 150.0)
        assert w["below_meaningful_exposure"] is True
    assert got[False]["regressed_wag"] == got[True]["regressed_wag"]


def test_on_a_positive_residual_carries_no_level_term_l13_06():
    with _flag(True):
        for g in GRID:
            exp = storage._fv_to_expected_war_per_yr(g["fv_close_raw"])
            assert storage._grad_wag(g) == round(g["career_war"]["war_per_yr"] - exp, 2)


# ------------------------------------------------------------------ client
def _client(stamp: bool):
    mr = pytest.importorskip("py_mini_racer")
    src = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8").replace("\r\n", "\n")

    def block(head):
        start = src.index(head)
        depth, i = 0, src.index("{", start)
        while True:
            depth += {"{": 1, "}": -1}.get(src[i], 0)
            if depth == 0 and src[i] == "}":
                return src[start:i + 1] + (";" if head.startswith("const ") else "")
            i += 1

    ctx = mr.MiniRacer()
    ctx.eval("function getCurrentLevelForDebut(p){ return (p && p.current_level) || null; }")
    ctx.eval("var DATA = " + ("{wag_definition: 'engine_at_debut'}" if stamp else "{}") + ";")
    for h in ("const FV_WAR_ANCHORS = ", "function fvExpectedWarPerYr(", "function _wagUnified(",
              "function wagBaked(", "function wagBakedBaseline(", "function gradPersonalFullSeason(",
              "function gradWarPerYr(", "function graduateOutcomePenalty(",
              "function _gradPerSeasonWar(", "function gradVsFvProjection(", "function gradWarWag("):
        ctx.eval(block(h))
    ctx.eval("""var G = {player_key: 'x', age: 25, current_level: 'MLB', fv_close_raw: 50,
      career_war: {career_war: 4.0, war_per_yr: 2.0, war_seasons_count: 2,
                   seasons: {'2024': 2.0, '2025': 2.0}},
      career_stats: [{level: 'MLB', season: 2024, ab: 600}, {level: 'MLB', season: 2025, ab: 600}],
      debuted_value: {wag: {regressed_wag: 0.33, below_meaningful_exposure: false,
                            expected_rate: 1.2, boom_label: 'settled'}}};""")
    return ctx


def test_client_without_the_stamp_runs_the_legacy_formula():
    ctx = _client(stamp=False)
    want = ctx.eval("(function(){ var e = fvExpectedWarPerYr(50, false), d = 2.0 - e;"
                    " return d > 0 ? (d * 0.70 + 2.0 * 0.30) * graduateOutcomePenalty(G) : d; })()")
    assert ctx.eval("gradVsFvProjection(G)") == pytest.approx(want)
    assert ctx.eval("gradWarWag(G)") == pytest.approx(2.0 + want)
    assert ctx.eval("gradVsFvProjection(G)") != pytest.approx(0.33)


def test_client_with_the_stamp_reads_the_baked_block():
    ctx = _client(stamp=True)
    assert ctx.eval("gradVsFvProjection(G)") == pytest.approx(0.33)
    assert ctx.eval("gradWarWag(G)") == pytest.approx(2.33)
    assert ctx.eval("wagBakedBaseline(G)") == pytest.approx(1.2)
    ctx.eval("G.debuted_value.wag.below_meaningful_exposure = true;")
    assert ctx.eval("gradVsFvProjection(G)") is None
    assert ctx.eval("gradWarWag(G)") is None

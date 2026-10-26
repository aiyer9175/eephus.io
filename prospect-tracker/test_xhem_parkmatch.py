# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The park-matched xHEM+ part (docs/ebr-2026-09-30/EBR_GATE.md 11.12; owner decision
EW3-52; task EWAR_XHEM_PARKMATCH, built dark).

Pinned:
  (a) the flag defaults off and only matters with the xHEM+ part on;
  (b) the pure core: the park term is fwar_frame's, the share fit recovers a planted slope
      and clamps to 0 to 1, d_pm is S1x's delta less b times the park term re-centred to
      zero with pitcher-batters outside, and the stops;
  (c) the frozen shares equal the tracked fit log, fitted on 2016 to 2019 only;
  (d) the builder: with the part on and the flag on, x = LAMBDA * d_pm / RPW*_s; with the
      flag off the part is 11.11's; the CLI refuses --parkmatch alone;
  (e) the park-pattern check: the slope tolerance, the named parks' bands on the Guts scale;
  (f) the lab's dry run on fixtures with nulls and planted signals.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import ewar_v3 as V3
import fwar_frame as F
import xhem_parkmatch as PM

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import build_ewar_v3 as B  # noqa: E402
import xhem_park_terms as XP  # noqa: E402
from test_ewar_xhem_half import XInputs  # noqa: E402

PARK = {2024: {1: -6.0, 2: 1.0, 3: 2.0}, 2026: {1: -5.0, 2: 0.5, 3: 0.0, 4: 0.0}}


class PInputs(XInputs):
    def __init__(self, *a, b=None, park=None, **k):
        super().__init__(*a, **k)
        self._b = {"xhem": 0.5, "hem": 0.25} if b is None else b
        self._pk = PARK if park is None else park

    def park(self, season):
        return dict(self._pk[int(season)])

    def park_shares(self):
        return self._b


@pytest.fixture
def quiet(monkeypatch):
    import fwar_vintage
    monkeypatch.setattr(B, "_sha", lambda p: "x")
    monkeypatch.setattr(fwar_vintage, "available", lambda: True)


# (a) ------------------------------------------------------------------------
def test_flag_defaults_off():
    assert V3.XHEM_PARKMATCH_LIVE is False, "flipped only by an owner answer after 11.12.7's PASS"
    assert V3.XHEM_HALF_LIVE is False
    assert V3.PREVIEW_XHEM_PM.parent == ROOT / ".cache" / "ewar_v3" / "preview"
    assert V3.PREVIEW_XHEM_PM != V3.PREVIEW_XHEM


def test_the_flag_matters_only_with_the_part_on(quiet, monkeypatch):
    monkeypatch.setattr(V3, "XHEM_PARKMATCH_LIVE", True)
    off = B.build(PInputs(), log=lambda *a: None, xhem=False)
    assert "xhem" not in off["meta"]["parts"]
    assert '"park_match"' not in json.dumps(off)


# (b) ------------------------------------------------------------------------
def test_park_term_is_fwar_frames_and_negative_in_a_run_friendly_park():
    p = PM.park_term([(400.0, 1.13), (200.0, 0.97)], 0.12)
    assert p == pytest.approx(F.park_runs(400.0, 0.12, 1.13) + F.park_runs(200.0, 0.12, 0.97))
    assert PM.park_term([(600.0, 1.13)], 0.12) < 0 < PM.park_term([(600.0, 0.95)], 0.12)


def test_stint_pa_follows_the_replica_rule():
    st = [{"team": "COL", "pa": 300}, {"team": "SFG", "pa": 100}]
    out = PM.stint_pa(500.0, st, {"COL": 115, "SFG": 137}, 115)
    assert out == [(115, 375.0), (137, 125.0)]
    assert PM.stint_pa(200.0, [], {}, 133) == [(133, 200.0)]
    assert PM.stint_pa(200.0, [{"team": "XXX", "pa": 50}], {}, 133) == [(133, 200.0)]


def test_fit_share_recovers_a_planted_slope_and_clamps():
    import random
    rng = random.Random(3)
    rows = []
    for s in (2016, 2017, 2018, 2019, 2021):
        for i in range(400):
            pa = rng.uniform(200, 650)
            pp = (1.0 - rng.choice((0.95, 1.0, 1.04, 1.13))) * 0.12 * pa
            g = 0.45 * pp + rng.gauss(0, 2.0) + 3.0 * (s - 2016)
            rows.append({"season": s, "pa": pa, "g": g, "P": pp})
    fit = PM.fit_share(rows)
    assert fit["seasons"] == [2016, 2017, 2018, 2019], "2021 is outside the fit seasons"
    assert fit["b"] == pytest.approx(0.45, abs=0.05)
    over = PM.fit_share([dict(r, g=1.8 * r["P"]) for r in rows])
    assert over["slope"] == pytest.approx(1.8) and over["b"] == 1.0
    under = PM.fit_share([dict(r, g=-0.5 * r["P"]) for r in rows])
    assert under["b"] == 0.0
    assert PM.fit_share(rows[:2])["b"] is None


def test_pm_deltas_remove_b_times_the_park_term_and_sum_to_zero():
    rows = {1: {"d": 3.0, "pa": 500.0, "arm": "xhem", "pb": False},
            2: {"d": -1.0, "pa": 400.0, "arm": "xhem", "pb": False},
            3: {"d": -2.0, "pa": 300.0, "arm": "hem", "pb": False},
            9: {"d": 0.0, "pa": 20.0, "arm": "hem", "pb": True}}
    park = {1: -6.0, 2: 1.0, 3: 2.0}
    b = {"xhem": 0.5, "hem": 0.25}
    d = PM.pm_deltas(rows, park, b)
    g = {1: 3.0 + 3.0, 2: -1.0 - 0.5, 3: -2.0 - 0.5}
    c = sum(g.values()) / 1200.0
    for m, pa in ((1, 500.0), (2, 400.0), (3, 300.0)):
        assert d[m] == pytest.approx(g[m] - pa * c)
    assert d[9] == 0.0
    assert sum(d.values()) == pytest.approx(0.0, abs=1e-12)
    # b = 0 is S1x as built (its stored delta already sums to zero)
    zero = PM.pm_deltas(rows, park, {"xhem": 0.0, "hem": 0.0})
    assert zero[1] == pytest.approx(3.0) and zero[3] == pytest.approx(-2.0)


def test_pm_deltas_stop_without_shares_or_park_term():
    rows = {1: {"d": 1.0, "pa": 300.0, "arm": "xhem", "pb": False},
            2: {"d": -1.0, "pa": 300.0, "arm": "hem", "pb": False}}
    with pytest.raises(PM.ParkMatchStop):
        PM.pm_deltas(rows, {1: 0.0, 2: 0.0}, None)
    with pytest.raises(PM.ParkMatchStop):
        PM.pm_deltas(rows, {1: 0.0}, {"xhem": 0.4, "hem": 0.1})
    # a row with no plate appearance needs no park term
    ok = PM.pm_deltas({**rows, 3: {"d": 0.0, "pa": 0.0, "arm": "hem", "pb": False}},
                      {1: 0.0, 2: 0.0}, {"xhem": 0.4, "hem": 0.1})
    assert ok[3] == 0.0


# (c) ------------------------------------------------------------------------
def test_the_frozen_shares_equal_the_tracked_fit_log():
    assert XP.FIT_PATH == ROOT / "docs" / "ebr-2026-09-30" / "xhem_parkmatch_fit.json"
    fit = json.loads(XP.FIT_PATH.read_text(encoding="utf-8"))
    assert PM.B_FROZEN is not None
    assert {k: round(v, 6) for k, v in PM.B_FROZEN.items()} == fit["b"]
    assert fit["fit_seasons"] == [2016, 2017, 2018, 2019] == list(PM.FIT_SEASONS)
    for arm in PM.ARMS:
        assert fit["arms"][arm]["seasons"] == [2016, 2017, 2018, 2019]
        assert 0.0 <= fit["b"][arm] <= 1.0
    # a second fit is refused: a refit is a new registration
    assert XP.main(["--fit"]) == 2


# (d) ------------------------------------------------------------------------
def test_builder_carries_d_pm_with_the_flag_on(quiet):
    asb = B.build(PInputs(), log=lambda *a: None, xhem=True, parkmatch=False)
    pmb = B.build(PInputs(), log=lambda *a: None, xhem=True, parkmatch=True)
    assert "park_match" not in asb["meta"]["parts"]["xhem"]
    assert pmb["meta"]["parts"]["xhem"]["park_match"]["b"] == {"xhem": 0.5, "hem": 0.25}
    g = {1: 3.0 + 3.0, 2: -1.0 - 0.5, 3: -2.0 - 0.5}
    c = sum(g.values()) / 1200.0
    for mid, pa in ((1, 500.0), (2, 400.0), (3, 300.0)):
        x = 0.5 * (g[mid] - pa * c) / 10.0
        assert pmb["players"][str(mid)]["2024"]["parts"]["xhem"]["wins"] == pytest.approx(x, abs=1e-6)
    # the as-built part is 11.11's, unchanged
    assert asb["players"]["1"]["2024"]["parts"]["xhem"]["wins"] == pytest.approx(0.15, abs=1e-6)
    for s in ("2024", "2026"):
        assert pmb["checks"][s]["xhem_receipt"]["sum_wins"] == pytest.approx(0.0, abs=1e-9)
        assert pmb["checks"][s]["xhem_receipt"]["park_match"]["b"] == {"xhem": 0.5, "hem": 0.25}
    # eWAR realized and the label basis do not move
    assert V3.departures(pmb, "realized") == V3.departures(asb, "realized")
    assert V3.departures(pmb, "headline", exclude=("xhem",)) == V3.departures(asb, "headline", exclude=("xhem",))


def test_builder_refuses_without_shares_or_park_term(quiet):
    with pytest.raises(V3.EwarV3Refusal):
        B.build(_NoShares(), log=lambda *a: None, xhem=True, parkmatch=True)
    with pytest.raises(V3.EwarV3Refusal):
        B.build(PInputs(park={2024: {1: -6.0}, 2026: PARK[2026]}), log=lambda *a: None, xhem=True,
                parkmatch=True)


class _NoShares(PInputs):
    def park_shares(self):
        return None


def test_cli_refuses_parkmatch_without_the_preview():
    assert B.main(["--parkmatch"]) == 2
    assert B.main(["--write", "--xhem-preview", "--parkmatch"]) == 2


# (e) ------------------------------------------------------------------------
def test_park_pattern_slope_and_named_bands():
    clubs = []
    for s in PM.CHECK_SEASONS:
        for j, pf in enumerate((95.0, 98.0, 100.0, 101.0, 102.0, 104.0)):
            clubs.append({"season": s, "club": 200 + j, "pf_pts": pf - 100.0, "c": (-1) ** (j + s) * 0.5})
        clubs.append({"season": s, "club": 115, "pf_pts": 13.0, "c": 0.2})
        if s >= 2025:
            clubs.append({"season": s, "club": 133, "pf_pts": 7.5, "c": -0.3})
    res = PM.park_pattern(clubs)
    assert res["slope_inside"] and res["pass"]
    assert res["n_neutral"] == 4 * len(PM.CHECK_SEASONS)      # 98, 100, 101 and 102 on the Guts scale
    tilted = [dict(r, c=r["c"] - 0.2 * r["pf_pts"]) for r in clubs]
    bad = PM.park_pattern(tilted)
    assert not bad["slope_inside"] and not bad["pass"]
    assert PM.SLOPE_TOL == 0.05 and PM.NEUTRAL_PF == (97.0, 103.0) and PM.NAMED_Z == 1.96
    assert [p[1] for p in PM.NAMED_PARKS] == [115, 133]


# (f) ------------------------------------------------------------------------
def test_the_lab_dry_run_passes_on_fixtures(tmp_path):
    import xhem_parkmatch_lab as LAB
    rec = LAB.dry_run(log=lambda *a: None, boot=60, tmp_dir=tmp_path)
    assert rec["status"] == "SCORED"
    assert (tmp_path / "xhem_parkmatch_eval.json").exists()
    assert LAB.DEFAULT_RECORD == ROOT / "docs" / "ebr-2026-09-30" / "xhem_parkmatch_eval.json"
    assert LAB.SEED == 20261008 and LAB.LAMBDA == 0.5 and LAB.DECIDING == (2021, 2022, 2023, 2024)

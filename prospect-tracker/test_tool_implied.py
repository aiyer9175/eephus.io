# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""tool_implied.py: the TIP tables of
docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md Part 1.2 (TL_4_TOOL_LAB_BUILD).

Pins: monotone smoothing (PAVA in the stat's expected direction), thin bins
dropped, no extrapolation beyond the first and the last non-thin bin, a table fit
on rows A never reads rows B, tip_first raises ServiceMissing without LANE B's
aging service, and tip_level's point-in-time rule (no input season at or after
V, none 2026 or later; the as-of date is December 31 of V - 1).
"""
from __future__ import annotations

import sys
from datetime import date

import pytest

import tool_implied as TI


def _rows(spec, stat_noise=0.0, start_id=0):
    """spec: [(bin_grade, n, value)] -> rows with ids, grades spread inside the bin."""
    rows = []
    i = start_id
    for g, n, v in spec:
        for k in range(n):
            rows.append({"id": i, "grade": g + (k % 5) * 0.5 - 1.0, "value": v + stat_noise * (k % 3)})
            i += 1
    return rows


def test_pava_is_monotone_in_both_directions():
    vals = [0.10, 0.08, 0.15, 0.14, 0.20]
    w = [20, 20, 20, 20, 20]
    up = TI.pava(vals, w, increasing=True)
    assert all(b >= a for a, b in zip(up, up[1:]))
    down = TI.pava(vals[::-1], w, increasing=False)
    assert all(b <= a for a, b in zip(down, down[1:]))
    # weights pull the pooled block toward the heavier bin
    pooled = TI.pava([0.10, 0.06], [30, 10], increasing=True)
    assert pooled[0] == pooled[1] == pytest.approx(0.09)


def test_fit_tables_smooths_non_monotone_bins_and_keeps_raw_medians():
    rows = _rows([(40, 20, 0.10), (45, 20, 0.16), (50, 20, 0.12), (55, 20, 0.20)])
    t = TI.fit_tables(rows, "game_pwr", "iso", "f3")
    assert t.computable
    assert list(t.values) == sorted(t.values)                    # non-decreasing
    raw = [b["median"] for b in t.bins if not b["thin"]]
    assert raw[1] > raw[2]                                       # the violation is in the raw medians
    assert t.sign == 1
    # a lower-is-better stat is oriented non-increasing
    rows_k = _rows([(40, 20, 28.0), (45, 20, 22.0), (50, 20, 24.0), (55, 20, 18.0)])
    tk = TI.fit_tables(rows_k, "hit", "k_pct", "f3")
    assert tk.sign == -1
    assert all(b <= a for a, b in zip(tk.values, tk.values[1:]))


def test_thin_bins_are_dropped_from_the_knots_but_reported():
    rows = _rows([(40, 20, 0.10), (45, 7, 0.90), (50, 20, 0.14)])
    t = TI.fit_tables(rows, "game_pwr", "iso", "f3")
    thin = [b for b in t.bins if b["thin"]]
    assert [b["bin"] for b in thin] == [45]
    assert len(t.knots) == 2
    # the thin bin's absurd median never enters the read
    assert t.read(45) == pytest.approx(0.12, abs=1e-9)
    assert t.bin_percentile(45, 0.5) is None                    # not computed in a thin bin
    assert t.bin_percentile(40, 0.10) == pytest.approx(0.5)     # ties sit at the mid rank


def test_no_extrapolation_beyond_the_last_non_thin_bin():
    rows = _rows([(40, 20, 0.10), (50, 20, 0.14), (60, 20, 0.20)])
    t = TI.fit_tables(rows, "game_pwr", "iso", "f3")
    lo, hi = t.knots[0], t.knots[-1]
    assert t.read(20) == t.read(lo) == pytest.approx(t.values[0])
    assert t.read(80) == t.read(hi) == pytest.approx(t.values[-1])
    assert t.read(lo - 5) == pytest.approx(t.values[0])
    assert t.read(hi + 5) == pytest.approx(t.values[-1])
    mid = (t.knots[0] + t.knots[1]) / 2.0
    assert t.values[0] < t.read(mid) < t.values[1]


def test_empty_or_all_thin_fit_is_not_computable():
    t = TI.fit_tables(_rows([(40, 5, 0.1)]), "game_pwr", "iso", "f3")
    assert not t.computable and t.read(50) is None
    t2 = TI.fit_tables([{"grade": None, "value": 0.1}, {"grade": 50, "value": None}], "game_pwr", "iso", "f3")
    assert t2.n_rows == 0 and t2.n_skipped == 2


def test_a_table_fit_on_rows_a_never_reads_rows_b():
    rows_a = _rows([(40, 20, 0.10), (50, 20, 0.14), (60, 20, 0.20)], start_id=0)
    rows_b = _rows([(40, 20, 0.90), (50, 20, 0.90), (60, 20, 0.90)], start_id=1000)
    t_a = TI.fit_tables(rows_a, "game_pwr", "iso", "f3")
    before = t_a.to_dict()
    rows_b.append({"id": 5000, "grade": 50, "value": 5.0})       # B changes after the fit
    assert t_a.to_dict() == before
    assert t_a.fit_ids == frozenset(r["id"] for r in rows_a)
    assert all(r["id"] not in t_a.fit_ids for r in rows_b)
    with pytest.raises(TI.TipInputError):
        t_a.assert_not_fit_on(rows_a[0]["id"])
    t_a.assert_not_fit_on(rows_b[0]["id"])
    t_ab = TI.fit_tables(rows_a + rows_b, "game_pwr", "iso", "f3")
    assert t_ab.read(50) != t_a.read(50)


def test_tip_now_reads_the_maturity_table_at_the_present_grade():
    t = TI.tip_mat(_rows([(40, 20, 0.10), (50, 20, 0.14), (60, 20, 0.20)]), "game_pwr", "iso")
    assert t.frame == "maturity"
    assert TI.tip_now(t, 45) == t.read(45)
    assert TI.tip_now(t, None) is None


# --- tip_first: a hook on LANE B's aging service ---------------------------
def _table():
    return TI.tip_mat(_rows([(40, 20, 0.10), (50, 20, 0.14), (60, 20, 0.20)]), "game_pwr", "iso")


def test_tip_first_raises_service_missing_when_aging_v3_is_not_importable(monkeypatch):
    monkeypatch.setitem(sys.modules, "aging_v3", None)
    with pytest.raises(TI.ServiceMissing):
        TI.tip_first(_table(), 50, 23, side="hit", comp="iso")


def test_tip_first_raises_service_missing_without_a_model(monkeypatch):
    aging_v3 = pytest.importorskip("aging_v3")

    def no_model():
        raise aging_v3.AgingV3Unavailable("no served model")
    monkeypatch.setattr(aging_v3, "served_model", no_model)
    with pytest.raises(TI.ServiceMissing):
        TI.tip_first(_table(), 50, 23, side="hit", comp="iso")
    with pytest.raises(ValueError):
        TI.tip_first(_table(), 50, 23, side="hit", comp="iso", aging="v3")


def test_tip_first_reads_the_service_curve_never_a_local_one():
    pytest.importorskip("aging_v3")

    class Model:
        def component_curve(self, side, comp, bucket=None):
            if comp != "iso":
                raise KeyError(comp)
            return {"H": {"24": {"delta": 0.010}, "25": {"delta": 0.006}, "26": {"delta": 0.002},
                          "27": {"delta": 0.0}}, "C": {}}
    out = TI.tip_first(_table(), 50, 23, side="hit", comp="iso", model=Model())
    assert out["base"] == pytest.approx(_table().read(50))
    assert out["delta"] == pytest.approx(0.018)
    assert out["value"] == pytest.approx(out["base"] + 0.018)
    at27 = TI.tip_first(_table(), 50, 27, side="hit", comp="iso", model=Model())
    assert at27["delta"] == 0.0
    none = TI.tip_first(_table(), 50, 23, side="hit", comp="babip", model=Model())
    assert none["delta"] == 0.0 and "no curve" in none["note"]
    import inspect
    src = inspect.getsource(TI)
    assert "aging_v3" in src and "AgingModel.component_curve" in src


# --- tip_level: point in time ----------------------------------------------
def _career(vintage_minus_one: int, extra_season=None):
    rows = {}
    bds = {}
    for i in range(40):
        pk = f"p{i}"
        bds[pk] = "1998-05-01"
        seasons = [vintage_minus_one - 2, vintage_minus_one - 1, vintage_minus_one]
        rows[pk] = []
        for s in seasons:
            rows[pk].append({"season": s, "level": "AA", "is_pitcher": False, "games": 100,
                             "ab": 400, "iso": 0.130 + 0.001 * (i % 5), "avg": ".250", "slg": ".380",
                             "k_pct": 22.0, "bb_pct": 8.0})
            rows[pk].append({"season": s, "level": "AAA", "is_pitcher": False, "games": 100,
                             "ab": 400, "iso": 0.150 + 0.001 * (i % 5), "avg": ".260", "slg": ".410",
                             "k_pct": 21.0, "bb_pct": 9.0})
            rows[pk].append({"season": s, "level": "MLB", "is_pitcher": False, "games": 100,
                             "ab": 400, "iso": 0.140 + 0.001 * (i % 5), "avg": ".255", "slg": ".395",
                             "k_pct": 23.0, "bb_pct": 8.5})
    if extra_season is not None:
        rows["p0"].append({"season": extra_season, "level": "AAA", "is_pitcher": False, "games": 100,
                           "ab": 400, "iso": 0.2, "avg": ".3", "slg": ".5", "k_pct": 20.0, "bb_pct": 9.0})
    return rows, bds


def _mlb_table(max_season: int, max_debut: int):
    rows = []
    for i, (g, v) in enumerate([(40, 0.10)] * 20 + [(50, 0.14)] * 20 + [(60, 0.20)] * 20):
        rows.append({"id": i, "grade": g + (i % 3) * 0.5, "value": v, "season": max_season - (i % 3),
                     "debut_year": max_debut - (i % 4)})
    return TI.fit_tables(rows, "game_pwr", "iso", "maturity")


def test_tip_level_raises_on_a_season_at_or_after_v_or_in_2026():
    V = 2023
    table = _mlb_table(V - 1, V - 1)
    career, bds = _career(V - 1, extra_season=V)
    with pytest.raises(TI.TipInputError):
        TI.tip_level(table, 50, "AAA", V, stat="iso", side="hit", career_stats=career, birth_dates=bds)
    career26, bds26 = _career(2025, extra_season=2026)
    with pytest.raises(TI.TipInputError):
        TI.tip_level(_mlb_table(2025, 2025), 50, "AAA", 2027, stat="iso", side="hit",
                     career_stats=career26, birth_dates=bds26)
    # the TIP table's own rows must also stop before V
    late_table = _mlb_table(V, V - 1)
    career_ok, bds_ok = _career(V - 1)
    with pytest.raises(TI.TipInputError):
        TI.tip_level(late_table, 50, "AAA", V, stat="iso", side="hit", career_stats=career_ok, birth_dates=bds_ok)
    debuted_in_v = _mlb_table(V - 1, V)
    with pytest.raises(TI.TipInputError):
        TI.tip_level(debuted_in_v, 50, "AAA", V, stat="iso", side="hit", career_stats=career_ok, birth_dates=bds_ok)


def test_tip_level_aaa_uses_the_within_player_offset_and_as_of_dec_31_of_v_minus_1():
    V = 2023
    table = _mlb_table(V - 1, V - 1)
    career, bds = _career(V - 1)
    out = TI.tip_level(table, 50, "AAA", V, stat="iso", side="hit", career_stats=career, birth_dates=bds)
    assert out["as_of"] == date(V - 1, 12, 31).isoformat()
    off = out["inputs"]["aaa_offset"]
    assert off["n_players"] == 40 and off["through_season"] == V - 1
    assert off["offset"] == pytest.approx(0.010, abs=1e-9)
    assert out["value"] == pytest.approx(table.read(50) + 0.010, abs=1e-9)
    assert out["label"] == "calibrated"
    assert TI.tip_level(table, 50, "MLB", V, stat="iso", side="hit", career_stats=career,
                        birth_dates=bds)["value"] == pytest.approx(table.read(50))


def test_tip_level_below_aaa_is_league_relative_and_labelled_uncalibrated(monkeypatch):
    import level_norms
    V = 2023
    table = _mlb_table(V - 1, V - 1)
    career, bds = _career(V - 1)
    seen = {}
    real = level_norms.compute_level_norms

    def spy(cs, bd, seasons_window=level_norms.DEFAULT_SEASONS_WINDOW, today=None):
        seen["today"] = today
        return real(cs, bd, seasons_window, today)
    monkeypatch.setattr(level_norms, "compute_level_norms", spy)
    out = TI.tip_level(table, 50, "AA", V, stat="iso", side="hit", career_stats=career, birth_dates=bds)
    assert seen["today"] == date(V - 1, 12, 31)                 # never the function's default of today
    assert out["label"].startswith("uncalibrated")
    lvl, mlb = out["inputs"]["level_norm"], out["inputs"]["mlb_norm"]
    assert lvl is not None and mlb
    assert out["value"] == pytest.approx(table.read(50) / mlb * lvl)

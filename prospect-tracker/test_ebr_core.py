# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""ebr.py, the pure eBR core (docs/ebr-2026-09-30/EBR_GATE.md part 2).

Fixture play-by-play only (test_fixtures/ebr/ebr_fixtures.py, built through the
runner record's own walk): the per-season RE24 recipe and its equality with
win_expectancy.run_expectancy where that function answers, the shrink, monotone
tables, the five parts' zero sums, the row identity, the double steal, the
third-out caught stealing, the exclusions, freezing, and the arms kept beside the
number. Nothing here reads the runner record, a cache or the network.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ebr  # noqa: E402


def _load_fixtures():
    """test_fixtures/ebr/ebr_fixtures.py, loaded by path (it is not a package)."""
    import importlib.util
    if "ebr_fixtures" in sys.modules:
        return sys.modules["ebr_fixtures"]
    spec = importlib.util.spec_from_file_location(
        "ebr_fixtures", ROOT / "test_fixtures" / "ebr" / "ebr_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ebr_fixtures"] = mod
    spec.loader.exec_module(mod)
    return mod


fx = _load_fixtures()

A, B, C = fx.A, fx.B, fx.C
AFTER_FREEZE = date(2026, 11, 2)


@pytest.fixture()
def unpinned(monkeypatch):
    """Fixture pools are not ebr_v1's frozen pool: lift the pins and shrink P."""
    monkeypatch.setattr(ebr, "FROZEN_K", None)
    monkeypatch.setattr(ebr, "FROZEN_POOL_SHA256", None)
    monkeypatch.setattr(ebr, "POOL_SEASONS", (2023, 2024))


# ---------------------------------------------------------------------------
# 2.3 the run basis
# ---------------------------------------------------------------------------
def _recipe_by_hand(pa) -> dict:
    """The recipe written out independently: runs from each play to the end of
    its half-inning, inclusive; the fit set (innings 1 to 8 and the top of the
    9th, three outs, no runner_placed); means by base-out cell at play start."""
    rows = pa.to_dict("records")
    halves = defaultdict(list)
    for r in rows:
        halves[(r["game_pk"], r["inning"], r["half"])].append(r)
    acc = defaultdict(list)
    for (g, inn, half), rs in halves.items():
        sched = int(rs[0]["scheduled_innings"] or 9)
        in_reg = inn <= sched - 1 or (inn == sched and str(half).startswith("top"))
        if not in_reg or max(int(r["outs_after"]) for r in rs) != 3:
            continue
        if any(bool(r["runner_placed"]) for r in rs):
            continue
        runs = [int(r["runs_scored_on_play"]) for r in rs]
        for i, r in enumerate(rs):
            b = sum(1 << j for j, col in enumerate(("on_first", "on_second", "on_third"))
                    if r[col] is not None and not (isinstance(r[col], float) and math.isnan(r[col]))
                    and str(r[col]) != "<NA>")
            acc[f"{b}|{int(r['outs_before'])}"].append(sum(runs[i:]))
    return {c: (len(v), sum(v) / len(v)) for c, v in acc.items()}


def test_raw_re24_equals_the_recipe_on_a_fixture_season():
    pa, _ = fx.season_frames(2024)
    pa = fx.concat([pa, fx.padding_frame(2024, halves=120, start_pk=7_000_000)])
    got = ebr.season_raw(pa)
    want = _recipe_by_hand(pa)
    assert set(got) == set(want) and len(got) == 24
    for c, (n, mean) in want.items():
        assert got[c]["n"] == n
        assert got[c]["mean"] == pytest.approx(mean, abs=1e-12)


def test_the_fit_set_drops_what_part_2_3_drops():
    base = fx.padding_frame(2024, halves=6, seed=3)
    keep = len(base)
    extra = []
    # a bottom of the ninth, an extra inning, a half with a placed runner, a half that
    # did not reach three outs, and a seven-inning game's bottom of the seventh
    for inning, half, placed, outs_end, sched in ((9, "bottom", False, 3, 9), (10, "top", False, 3, 9),
                                                  (5, "top", True, 3, 9), (6, "top", False, 2, 9),
                                                  (7, "bottom", False, 3, 7)):
        f = fx.padding_frame(2024, halves=1, seed=inning, start_pk=8_000_000 + inning)
        f["inning"] = inning
        f["half"] = half
        f["runner_placed"] = placed
        f["scheduled_innings"] = sched
        if outs_end == 2:
            f = f.iloc[:2].copy()
        extra.append(f)
    pa = fx.concat([base] + extra)
    mask = ebr.fit_mask(pa)
    assert int(mask.sum()) == keep
    assert sum(v["n"] for v in ebr.season_raw(pa).values()) == keep


def test_raw_re24_equals_run_expectancy_where_it_answers():
    import numpy as np

    import win_expectancy
    pa = fx.padding_frame(2024, halves=6400, seed=11)
    raw = ebr.season_raw(pa)
    assert min(v["n"] for v in raw.values()) >= win_expectancy.MIN_RE_N
    d = pa.copy()
    d["_base"] = ebr.base_code(d)
    theirs = win_expectancy.run_expectancy(d, np)
    assert set(theirs) == set(raw) == set(ebr.CELLS)
    for c in ebr.CELLS:
        assert theirs[c]["n"] == raw[c]["n"]
        assert round(raw[c]["mean"], 5) == theirs[c]["re"]


def test_ebr_never_calls_run_expectancy():
    src = (ROOT / "ebr.py").read_text(encoding="utf-8")
    assert "run_expectancy(" not in src
    assert "import win_expectancy" not in src


def _raw(n, mean, var=1.0):
    return {c: {"n": n, "mean": mean[c], "var": var} for c in ebr.CELLS}


def test_the_shrink_formula():
    pool_seasons = {2023: _raw(400, {c: v * 1.05 for c, v in fx.STD_RE.items()}),
                    2024: _raw(900, {c: v * 0.97 for c, v in fx.STD_RE.items()})}
    pool = ebr.pool_table(pool_seasons)
    for c in ebr.CELLS:
        assert pool[c] == pytest.approx((400 * fx.STD_RE[c] * 1.05 + 900 * fx.STD_RE[c] * 0.97) / 1300)
    raw = pool_seasons[2023]
    lam = ebr.season_lambda(raw, pool)
    assert lam == pytest.approx(sum(400 * raw[c]["mean"] for c in ebr.CELLS)
                                / sum(400 * pool[c] for c in ebr.CELLS))
    k = 1500.0
    t = ebr.shrunk_table(raw, pool, k, 2023)
    for c in ebr.CELLS:
        assert t[c] == pytest.approx((400 * raw[c]["mean"] + k * lam * pool[c]) / (400 + k))
    re_ = ebr.RE(t)
    assert re_(7, 3) == 0.0 and re_(0, 3) == 0.0 and re_(1, 0) == pytest.approx(t["1|0"])


def test_k_by_the_method_of_moments_and_its_clip():
    import numpy as np
    seasons = {}
    rng = np.random.default_rng(5)
    for i, s in enumerate((2021, 2022, 2023)):
        seasons[s] = {c: {"n": 2000 + 100 * i, "mean": fx.STD_RE[c] * (1 + 0.02 * i) + rng.normal(0, 0.03),
                          "var": 1.2} for c in ebr.CELLS}
    pool = ebr.pool_table(seasons)
    got = ebr.shrink_constant(seasons, pool)
    lam = {s: ebr.season_lambda(seasons[s], pool) for s in seasons}
    within, tau = [], []
    for c in ebr.CELLS:
        ms = np.array([seasons[s][c]["mean"] / lam[s] for s in sorted(seasons)])
        ns = np.array([seasons[s][c]["n"] for s in sorted(seasons)], float)
        vs = np.array([seasons[s][c]["var"] / lam[s] ** 2 for s in sorted(seasons)])
        tau.append(max(float(np.var(ms, ddof=1)) - float(np.mean(vs / ns)), 0.0))
        within.append(float(np.average(vs, weights=ns)))
    k_raw = np.mean(within) / np.mean(tau)
    assert got["K_raw"] == round(k_raw, 1)
    assert got["K"] == round(min(max(k_raw, 500.0), 5000.0), 1)
    flat = {s: {c: {"n": 5000, "mean": fx.STD_RE[c], "var": 1.0} for c in ebr.CELLS} for s in (1, 2)}
    assert ebr.shrink_constant(flat, ebr.pool_table(flat))["K"] == 5000.0
    wild = {1: {c: {"n": 5000, "mean": fx.STD_RE[c] * 2.0, "var": 0.01} for c in ebr.CELLS},
            2: {c: {"n": 5000, "mean": fx.STD_RE[c] * (0.5 if c.endswith("0") else 1.5), "var": 0.01}
                for c in ebr.CELLS}}
    assert ebr.shrink_constant(wild, ebr.pool_table(wild))["K"] == 500.0


def test_monotone_cells_or_a_refusal():
    pool = dict(fx.STD_RE)
    good = ebr.shrunk_table(_raw(1000, fx.STD_RE), pool, 1654.4, 2024)
    assert ebr.monotone_violations(good) == []
    bad_runner = dict(fx.STD_RE)
    bad_runner["3|0"] = 0.80          # adding a runner to 1B, 2B lowers RE below 2B alone
    with pytest.raises(ebr.EbrRefusal, match="not monotone"):
        ebr.shrunk_table(_raw(1000, bad_runner), pool, 0.0, 2024)
    bad_out = dict(fx.STD_RE)
    bad_out["0|1"] = 0.60             # adding an out raises RE
    assert "0@0->1" in ebr.monotone_violations(bad_out)
    missing = _raw(1000, fx.STD_RE)
    del missing["4|0"]
    with pytest.raises(ebr.EbrRefusal, match="lacks cells"):
        ebr.shrunk_table(missing, pool, 1654.4, 2024)


def test_the_frozen_pool_needs_every_season_of_p_and_its_pins():
    with pytest.raises(ebr.EbrRefusal, match="every season of P"):
        ebr.frozen_pool_document({2024: _raw(100, fx.STD_RE)}, {2024: []})
    doc = {"ebr_version": "ebr_v1", "pool_seasons": list(ebr.POOL_SEASONS), "K": 1000.0}
    doc["sha256"] = ebr.pool_doc_sha(doc)
    with pytest.raises(ebr.EbrRefusal, match="frozen with ebr_v1"):
        ebr.check_frozen_pool(doc)
    assert ebr.EBR_VERSION == "ebr_v1" and ebr.KAPPA == 20.0
    assert ebr.POOL_SEASONS == (2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)
    assert 500.0 <= ebr.FROZEN_K <= 5000.0 and len(ebr.FROZEN_POOL_SHA256) == 64


# ---------------------------------------------------------------------------
# 2.4 and 2.5: the parts
# ---------------------------------------------------------------------------
def _season_credits(season=2024, re_table=None):
    pa, rn = fx.season_frames(season)
    opps = ebr.xb_opportunities(pa, rn)
    ebr.finalize_opportunities(opps)
    credits, league, opps = ebr.season_credits(pa, rn, re_table or fx.STD_RE,
                                               ebr.pool_counts({season: opps}), opps=opps)
    return pa, rn, opps, credits, league


def test_each_part_sums_to_zero_over_every_runner():
    _, _, _, credits, _ = _season_credits()
    sums = defaultdict(float)
    for _, _, _, part, v in credits:
        sums[part] += v
    assert set(sums) == set(ebr.PARTS)
    for part in ebr.PARTS:
        assert abs(sums[part]) < 1e-9, (part, sums[part])


def test_parts_sum_to_ebr_within_rounding():
    pa, _, opps, credits, _ = _season_credits()
    rows = ebr.substrate_rows(2024, ebr.player_rows(credits, pa, opps))
    ix = {f: i for i, f in enumerate(ebr.FIELDS)}
    assert rows
    for r in rows:
        assert abs(sum(r[ix[p]] for p in ebr.PARTS) - r[ix["ebr"]]) <= 0.011
        assert all(not math.isnan(r[ix[p]]) for p in ebr.PARTS + ("ebr",))


def test_a_double_steal_sums_to_the_events_re_change():
    _, rn, _, _, _ = _season_credits()
    re_ = ebr.RE(fx.STD_RE)
    atts = [a for a in ebr.attempt_values(rn, re_) if a[2] == 2024 * 1000 + 2]
    assert sorted(a[0] for a in atts) == [A, B]
    lead = next(a for a in atts if a[0] == A)
    trail = next(a for a in atts if a[0] == B)
    assert lead[4] == 2 and trail[4] == 1
    # lead first with the trail runner still on first: 1B2B -> 1B3B; then 1B3B -> 2B3B
    assert lead[5] == pytest.approx(fx.STD_RE["5|0"] - fx.STD_RE["3|0"])
    assert trail[5] == pytest.approx(fx.STD_RE["6|0"] - fx.STD_RE["5|0"])
    assert lead[5] + trail[5] == pytest.approx(fx.STD_RE["6|0"] - fx.STD_RE["3|0"])


def test_a_steal_on_a_strikeout_is_valued_after_the_strikeout():
    _, rn, _, _, _ = _season_credits()
    att = [a for a in ebr.attempt_values(rn, ebr.RE(fx.STD_RE)) if a[2] == 2024 * 1000 + 1]
    assert len(att) == 1 and att[0][0] == B
    assert att[0][5] == pytest.approx(fx.STD_RE["6|1"] - fx.STD_RE["5|1"])


def test_a_third_out_caught_stealing_is_priced():
    _, rn, _, credits, league = _season_credits()
    att = [a for a in ebr.attempt_values(rn, ebr.RE(fx.STD_RE)) if a[2] == 2024 * 1000 + 3]
    assert len(att) == 1 and att[0][0] == A and att[0][3] == "sb" and att[0][7] == 1
    assert att[0][5] == pytest.approx(0.0 - fx.STD_RE["1|2"])
    assert any(c[2] == 2024 * 1000 + 3 and c[3] == "sb" and c[4] == pytest.approx(-fx.STD_RE["1|2"])
               for c in credits)
    assert league["steal"]["cs"] == 1 and league["steal"]["sb"] == 4


def test_a_pickoff_of_a_runner_not_attempting():
    _, rn, _, _, league = _season_credits()
    pk = [a for a in ebr.attempt_values(rn, ebr.RE(fx.STD_RE)) if a[3] == "pk"]
    assert len(pk) == 1 and pk[0][0] == B
    assert pk[0][5] == pytest.approx(fx.STD_RE["0|1"] - fx.STD_RE["1|0"])
    assert league["steal"]["pickoffs"] == 1


def test_wild_pitch_passed_ball_balk_and_error_advances_are_excluded():
    _, rn, opps, credits, _ = _season_credits()
    g5 = 2024 * 1000 + 5
    assert not [a for a in ebr.attempt_values(rn, ebr.RE(fx.STD_RE)) if a[2] == g5]
    # in game 5 only the centring credits (the league value per start on base) reach A
    assert all(abs(c[4]) < 0.01 for c in credits if c[2] == g5 and c[3] in ("sb", "pk"))
    assert not [o for o in opps if o["game_pk"] == g5 and o["c"] != "B"]
    # game 7: first to second on the single, then to third on the throwing error
    h7 = [o for o in opps if o["game_pk"] == 2024 * 1000 + 7 and o["c"] == "H"]
    assert len(h7) == 1 and h7[0]["y"] == 2 and h7[0]["trunc"] is True


def test_egdp_charges_the_double_play_at_its_state_cost():
    _, _, _, credits, league = _season_credits()
    cell = league["dp"]["table"]["1|0"]
    cost = fx.STD_RE["1|1"] - fx.STD_RE["0|2"]
    assert cell["cost"] == pytest.approx(cost)
    gidp = [c for c in credits if c[3] == "dp" and c[2] == 2024 * 1000 + 6]
    assert len(gidp) == 1 and gidp[0][0] == B
    assert gidp[0][4] == pytest.approx(-(1.0 - cell["p"]) * cost)


def test_xb_outcomes_split_exactly_into_adv_and_oob():
    _, _, opps, credits, league = _season_credits()
    by = defaultdict(float)
    for c in credits:
        if c[3] in ("xb_adv", "xb_oob"):
            by[c[3]] += c[4]
    assert abs(by["xb_adv"]) < 1e-9 and abs(by["xb_oob"]) < 1e-9
    assert league["xb"]["opportunities"]["H"] >= 4 and league["xb"]["opportunities"]["G"] == 1
    assert league["xb"]["opportunities"]["A"] >= 2


# ---------------------------------------------------------------------------
# freezing and the arms (through the builder, fixtures only)
# ---------------------------------------------------------------------------
def _build(tmp_path, seasons, *, arm_blob=None, today=AFTER_FREEZE, out=None):
    import build_ebr
    data = {s: fx.season_frames(s) for s in seasons}
    all_data = {s: fx.season_frames(s) for s in ebr.POOL_SEASONS}
    raw = {s: ebr.season_raw(pa) for s, (pa, rn) in all_data.items()}
    opps = {}
    for s, (pa, rn) in all_data.items():
        o = ebr.xb_opportunities(pa, rn)
        ebr.finalize_opportunities(o)
        opps[s] = o
    pool = ebr.frozen_pool_document(raw, opps)
    out = out or (tmp_path / "preview")
    sub, ev = build_ebr.build(record_data=(data, {}), out_dir=out, frozen_dir=tmp_path / "frozen",
                              today=today, generated_at="2026-11-02T00:00:00+00:00",
                              comparators=False, pool_doc=pool,
                              arm_blob=({} if arm_blob is None else arm_blob))
    build_ebr.write(sub, ev, out)
    return sub, ev


def test_a_completed_season_is_byte_identical_when_a_later_season_is_added(tmp_path, unpinned):
    out = tmp_path / "preview"
    one, _ = _build(tmp_path, (2023,), out=out)
    two, ev2 = _build(tmp_path, (2023, 2024), out=out)
    rows1 = [r for r in one["rows"] if r[1] == 2023]
    rows2 = [r for r in two["rows"] if r[1] == 2023]
    assert json.dumps(rows1) == json.dumps(rows2)
    assert one["re24"]["2023"] == two["re24"]["2023"]
    assert one["cadence"]["frozen_digests"]["2023"] == two["cadence"]["frozen_digests"]["2023"]
    assert ev2["identity"]["2023"]["I8"]["unchanged"] is True


def test_the_arms_never_change_ebr(tmp_path, unpinned):
    arm_blob = {"by_mlbam": {str(i): {"2023": {"primary_code": "8", "all": 80.0 + i % 17}}
                             for i in range(1, 60)}}
    plain, _ = _build(tmp_path, (2023, 2024), out=tmp_path / "a")
    armed, ev = _build(tmp_path, (2023, 2024), arm_blob=arm_blob, out=tmp_path / "b")
    assert json.dumps(plain["rows"]) == json.dumps(armed["rows"])
    assert "r_with_primary" in ev["arms"]["2024"]["P"]
    assert "r_with_primary" in ev["arms"]["2024"]["F"]
    pa, rn, opps, credits, _ = _season_credits()
    before = json.dumps([[o["c"], o["k"], o["y"], o["r"]] for o in opps])
    rows = ebr.substrate_rows(2024, ebr.player_rows(credits, pa, opps))
    bo = ebr.Backoff(opps, ebr.pool_counts({2024: opps}))
    ebr.arm_report(rows, opps, fx.STD_RE, bo, ebr.arm_p_override(opps, opps, bo))
    assert json.dumps([[o["c"], o["k"], o["y"], o["r"]] for o in opps]) == before
    credits2, _, _ = ebr.season_credits(pa, rn, fx.STD_RE, ebr.pool_counts({2024: opps}), opps=opps)
    assert ebr.substrate_rows(2024, ebr.player_rows(credits2, pa, opps)) == rows

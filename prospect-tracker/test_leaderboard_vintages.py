# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Tests for the betting validation path (leaderboard_vintages + the vintage
half of betting_model).

THE ONE THING THESE TESTS PROTECT: a number the module calls honest must
actually be honest. Everything else here serves that.

  1. A VINTAGE NEVER LOOKS FORWARD. `as_of(D)` must return a snapshot whose
     knowledge cutoff is STRICTLY BEFORE D, for every D, or the whole exercise
     is theatre with extra files. This is the test that would catch an
     off-by-one that turns "priced on yesterday" into "priced on tonight".

  2. THE FALLBACK ANNOUNCES ITSELF. With no vintage the read still works (that
     is the current behaviour and nothing may regress while the store fills),
     but it comes back flagged `contaminated: True` and named
     `live-leaderboards`. A silent fallback would be worse than no vintage
     path at all, because the artifact would claim a clean number.

  3. BOTH MODES SHIP, BOTH LABELLED. The backtest reports the contaminated
     numbers and the vintage numbers side by side, each carrying which mode
     produced it, so nobody has to remember which column is which.

  4. min_edge STAYS NULL. Below the stated sample threshold there is no
     threshold, and therefore no pick. The gate is also tested in the OPEN
     direction, because a gate that can only ever be closed is not a gate, it
     is a constant, and a constant would rot silently.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

import betting_model as bm
import leaderboard_vintages as lv

ORGS = ("NYM", "PHI", "ATL", "WSN")


# ===========================================================================
# fixtures: a synthetic store, so nothing here depends on a built checkout
# ===========================================================================
def _record(vintage_date: str, *, covers_through: str | None = None,
            bump: float = 0.0) -> dict:
    """A minimal but SHAPE-EXACT vintage record. Written by hand rather than
    through reduce_current so the on-disk contract is pinned independently of
    the producer: if the column order ever changes, this test fails and the
    stored archive is not silently reinterpreted."""
    return {
        "schema": lv.SCHEMA,
        "vintage_date": vintage_date,
        "covers_through": covers_through or vintage_date,
        "captured_at": f"{vintage_date}T07:10:00+00:00",
        "season": "2026",
        "org_codes": "canonical (trades.canonical_org)",
        "team_columns": list(lv.TEAM_COLUMNS),
        "pitcher_columns": list(lv.PITCHER_COLUMNS),
        "sources": {},
        "n_teams": len(ORGS),
        "n_pitchers": 4,
        "teams": {
            "NYM": [108.0 + bump, 104.0, 103.0, 560.0, 380.0],
            "PHI": [104.0, 108.0 + bump, 99.0, 590.0, 350.0],
            "ATL": [99.0, 97.0, 106.0 + bump, 540.0, 400.0],
            "WSN": [93.0, 92.0, 94.0, 520.0, 410.0],
        },
        "pitchers": {
            "101": [118.0, 5.9, "NYM", "SP"],
            "102": [109.0, 5.4, "PHI", "SP"],
            "103": [96.0, 5.1, "ATL", "SP"],
            "104": [88.0, 4.6, "WSN", "SP"],
        },
    }


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """An empty vintage store the module is pointed at for the whole test."""
    d = tmp_path / "leaderboard_vintages"
    d.mkdir()
    monkeypatch.setattr(lv, "VINTAGE_DIR", d)
    lv.reset_cache()
    bm.reset_vintage_cache()
    yield d
    lv.reset_cache()
    bm.reset_vintage_cache()


def _seed(store_dir, dates, **kw):
    for i, s in enumerate(dates):
        rec = _record(s, bump=0.1 * i, **kw)
        (store_dir / f"{s}.json").write_text(json.dumps(rec, separators=(",", ":")),
                                             encoding="utf-8")
    lv.reset_cache()
    bm.reset_vintage_cache()


def _daterange(start: str, n: int) -> list[str]:
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]


# ===========================================================================
# 1. THE STORE
# ===========================================================================
def test_snapshot_is_idempotent_for_a_date(store, tmp_path):
    """Two runs on one date leave ONE file, and the second run does not touch
    it. A vintage is evidence of what was knowable; a later, better-informed
    run overwriting it would put the leak back."""
    data = tmp_path / "data"
    data.mkdir()
    _write_fake_leaderboards(data, offense=110.0)
    first = lv.snapshot(on_date="2026-08-05", vintage_dir=store, data_dir=data)
    assert first["written"] is True
    on_disk = (store / "2026-08-05.json").read_text(encoding="utf-8")

    # Rebuild the leaderboards with different numbers, then re-run the same date.
    _write_fake_leaderboards(data, offense=999.0)
    second = lv.snapshot(on_date="2026-08-05", vintage_dir=store, data_dir=data)
    assert second["written"] is False
    assert second["reason"] == "already captured"
    assert (store / "2026-08-05.json").read_text(encoding="utf-8") == on_disk
    assert len(list(store.glob("*.json"))) == 1


def test_snapshot_force_is_the_only_way_to_overwrite(store, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    _write_fake_leaderboards(data, offense=110.0)
    lv.snapshot(on_date="2026-08-05", vintage_dir=store, data_dir=data)
    _write_fake_leaderboards(data, offense=120.0)
    forced = lv.snapshot(on_date="2026-08-05", vintage_dir=store, data_dir=data, force=True)
    assert forced["written"] is True
    assert forced["record"]["teams"]["NYM"][0] == 120.0


def test_snapshot_refuses_when_the_leaderboards_are_absent(store, tmp_path):
    """A half-populated vintage is worse than none: it would be eligible to
    price games and would price them on a broken prevention blend."""
    empty = tmp_path / "nodata"
    empty.mkdir()
    r = lv.snapshot(on_date="2026-08-05", vintage_dir=store, data_dir=empty)
    assert r["written"] is False and r["record"] is None
    assert not list(store.glob("*.json"))


def test_stored_org_codes_are_canonical(store, tmp_path):
    """The leaderboards carry StatsAPI codes. The store must not, or every
    downstream join drops eight clubs."""
    data = tmp_path / "data"
    data.mkdir()
    _write_fake_leaderboards(data, offense=110.0, statsapi_codes=True)
    rec = lv.snapshot(on_date="2026-08-05", vintage_dir=store, data_dir=data)["record"]
    assert set(rec["teams"]) == {"WSN", "CHW", "TBR", "SDP"}
    for stats_api_code in ("WSH", "CWS", "TB", "SD"):
        assert stats_api_code not in rec["teams"]


def test_reduce_current_stamps_a_conservative_cutoff(store, tmp_path):
    """covers_through is the max of the sources' as_of dates and the write
    date. A file written on 2026-08-05 may not price a game on 2026-08-05."""
    data = tmp_path / "data"
    data.mkdir()
    _write_fake_leaderboards(data, offense=110.0, as_of="2026-08-01")
    rec = lv.reduce_current(on_date="2026-08-05", data_dir=data)
    assert rec["covers_through"] == "2026-08-05"

    _write_fake_leaderboards(data, offense=110.0, as_of="2026-08-09")
    rec2 = lv.reduce_current(on_date="2026-08-05", data_dir=data)
    assert rec2["covers_through"] == "2026-08-09"


# ===========================================================================
# 2. as_of NEVER LOOKS FORWARD (the load-bearing test in this file)
# ===========================================================================
def test_as_of_never_returns_a_vintage_on_or_after_the_query_date(store):
    _seed(store, _daterange("2026-06-01", 20))
    for q in _daterange("2026-05-28", 30):
        rec = lv.as_of(q, vintage_dir=store)
        if rec is None:
            continue
        assert rec["covers_through"] < q, f"{rec['covers_through']} is not before {q}"
        assert rec["vintage_date"] < q


def test_as_of_takes_the_newest_eligible_vintage(store):
    _seed(store, ["2026-06-01", "2026-06-05", "2026-06-09"])
    assert lv.as_of("2026-06-06", vintage_dir=store)["vintage_date"] == "2026-06-05"
    assert lv.as_of("2026-06-05", vintage_dir=store)["vintage_date"] == "2026-06-01"
    assert lv.as_of("2026-06-01", vintage_dir=store) is None
    assert lv.as_of("2026-07-01", vintage_dir=store)["vintage_date"] == "2026-06-09"


def test_a_late_cutoff_makes_a_vintage_ineligible_for_its_own_day(store):
    """A record whose sources claim to know through 2026-06-10 cannot price a
    2026-06-10 game even though its filename says 2026-06-08."""
    rec = _record("2026-06-08", covers_through="2026-06-10")
    (store / "2026-06-08.json").write_text(json.dumps(rec), encoding="utf-8")
    lv.reset_cache()
    assert lv.as_of("2026-06-10", vintage_dir=store) is None
    assert lv.as_of("2026-06-11", vintage_dir=store)["vintage_date"] == "2026-06-08"


def test_coverage_counts_the_holes(store):
    _seed(store, ["2026-06-01", "2026-06-02", "2026-06-05"])
    cov = lv.coverage(vintage_dir=store)
    assert cov["n_vintages"] == 3
    assert cov["first"] == "2026-06-01" and cov["last"] == "2026-06-05"
    assert cov["missing_dates"] == ["2026-06-03", "2026-06-04"]
    assert cov["earliest_gradable_game_date"] == "2026-06-02"


def test_coverage_on_an_empty_store_says_zero_not_nothing(store):
    cov = lv.coverage(vintage_dir=store)
    assert cov["n_vintages"] == 0 and cov["first"] is None
    assert "contaminated" in cov["note"]


# ===========================================================================
# 3. THE MODEL'S VINTAGE READ PATH
# ===========================================================================
def test_fallback_flags_contamination_and_still_prices(store):
    """No vintage: the read still returns usable inputs (nothing regresses
    while the store fills) but says out loud that they leak."""
    b = bm.inputs_as_of("2026-06-15")
    assert b["source"] == "live-leaderboards"
    assert b["contaminated"] is True
    assert b["vintage_date"] is None
    assert "contaminated" in b["note"]


def test_fallback_can_be_refused_outright(store):
    """The backtest uses this door: no vintage means no features, not the
    live leaderboards wearing a vintage label."""
    b = bm.inputs_as_of("2026-06-15", allow_fallback=False)
    assert b["source"] == "none"
    assert b["teams"] == {} and b["starters"] == {}
    assert b["contaminated"] is False


def test_a_vintage_read_is_not_contaminated(store):
    _seed(store, ["2026-06-01"])
    b = bm.inputs_as_of("2026-06-10")
    assert b["source"] == "vintage"
    assert b["contaminated"] is False
    assert b["vintage_date"] == "2026-06-01"
    assert set(b["teams"]) == set(ORGS) | {"_scale"}
    assert set(b["starters"]) == {101, 102, 103, 104}


def test_vintage_inputs_go_through_the_same_standardization(store):
    """The vintage path and the live path share `_assemble_team_inputs`. If
    they ever diverge, a backtest stops being comparable to the served model
    for a reason nobody would see. Same raw numbers in, same z out."""
    rec = _record("2026-06-01")
    from_vintage = bm.team_inputs_from_vintage(rec)
    direct = bm._assemble_team_inputs(
        {o: rec["teams"][o][0] for o in ORGS},
        {o: rec["teams"][o][1] for o in ORGS},
        {o: rec["teams"][o][2] for o in ORGS},
        {o: rec["teams"][o][3] for o in ORGS},
        {o: rec["teams"][o][4] for o in ORGS},
    )
    assert from_vintage == direct
    assert from_vintage["NYM"]["z_off"] > from_vintage["WSN"]["z_off"]


def test_vintage_pitchers_keep_the_shape_starter_inputs_returns(store):
    out = bm.starter_inputs_from_vintage(_record("2026-06-01"))
    row = out[101]
    assert row["sem_plus"] == 118.0 and row["ip_per_gs"] == 5.9
    assert row["org"] == "NYM" and row["role"] == "SP"
    # The model never reads a display name, so the store does not carry one.
    assert row["name"] is None


def test_two_vintages_produce_different_prices(store):
    """The point of the whole exercise: the number a game gets depends on
    WHICH vintage priced it."""
    _seed(store, ["2026-06-01", "2026-06-20"])
    early = bm.inputs_as_of("2026-06-05")["teams"]
    late = bm.inputs_as_of("2026-06-25")["teams"]
    assert early["NYM"]["offense_plus"] != late["NYM"]["offense_plus"]


# ===========================================================================
# 4. THE TWO-MODE BACKTEST
# ===========================================================================
def _fake_games(dates, per_day=1):
    games = []
    pk = 1
    for i, d in enumerate(dates):
        for j in range(per_day):
            home = ORGS[(i + j) % len(ORGS)]
            away = ORGS[(i + j + 1) % len(ORGS)]
            games.append({
                "game_pk": pk, "season": "2026", "date": d,
                "home_org": home, "away_org": away,
                "home_runs": 4 + (pk % 3), "away_runs": 3 + ((pk + 1) % 3),
                "innings": 9,
                "home_sp": 101 + (pk % 4), "away_sp": 101 + ((pk + 2) % 4),
            })
            pk += 1
    return games


@pytest.fixture()
def small_model(store, monkeypatch):
    """The model wired to a 32-game synthetic season so the solvers finish in
    about a second. The floors are lowered with it: this fixture tests the
    PLUMBING of the two modes, not the size of the real sample."""
    games = _fake_games(_daterange("2026-06-01", 32))
    live = bm.team_inputs_from_vintage(_record("2026-08-04", bump=5.0))
    monkeypatch.setattr(bm, "completed_games", lambda season=None: list(games))
    monkeypatch.setattr(bm, "team_inputs", lambda: live)
    monkeypatch.setattr(bm, "starter_inputs",
                        lambda: bm.starter_inputs_from_vintage(_record("2026-08-04")))
    monkeypatch.setattr(bm, "park_index", lambda: {o: 1.0 for o in ORGS})
    monkeypatch.setattr(bm, "VINTAGE_MIN_FIT_GAMES", 8)
    monkeypatch.setattr(bm, "VINTAGE_MIN_EVAL_GAMES", 4)
    monkeypatch.setattr(bm, "VINTAGE_FIT_TARGET_GAMES", 8)
    return games


def test_backtest_reports_both_modes_and_labels_them(small_model, store):
    _seed(store, _daterange("2026-05-25", 40))
    r = bm.backtest(write=False)
    assert r["modes"] == ["contaminated", "vintage"]
    assert r["in_sample"]["mode"] == "contaminated"
    assert r["in_sample"]["honest"] is False
    v = r["vintage"]
    assert v["mode"] == "vintage" and v["honest"] is True
    assert v["status"] == "graded"
    assert v["n_graded"] > 0
    assert v["n_skipped_no_vintage"] == 0
    assert v["split_date"]
    # Both modes graded the same schedule with different features, so the
    # numbers must not be identical. Identical numbers would mean the vintage
    # resolver quietly handed back the live inputs.
    assert v["brier"] != r["in_sample"]["brier"]


def test_vintage_mode_skips_games_it_cannot_grade_honestly(small_model, store):
    """Half the season has a vintage, half does not. The half that does not is
    SKIPPED and counted, never graded on the fallback."""
    _seed(store, _daterange("2026-06-14", 20))
    r = bm.backtest(write=False)
    v = r["vintage"]
    assert v["n_skipped_no_vintage"] > 0
    assert v["n_gradable"] + v["n_skipped_no_vintage"] == r["n_games"]
    assert v["first_graded_date"] > "2026-06-14"


def test_vintage_mode_starts_at_zero_with_an_empty_store(small_model, store):
    r = bm.backtest(write=False)
    v = r["vintage"]
    assert v["n_gradable"] == 0 and v["n_graded"] == 0
    assert v["n_skipped_no_vintage"] == r["n_games"]
    assert v["status"] == "no vintages"
    assert r["in_sample"]["n"] > 0        # the contaminated mode still reports
    assert r["min_edge"] is None


def test_the_eval_artifact_carries_the_mode(small_model, store, tmp_path, monkeypatch):
    """Whatever a reader picks up, it must say which mode produced it."""
    out = tmp_path / "betting_model_eval.json"
    monkeypatch.setattr(bm, "EVAL_PATH", out)
    monkeypatch.setattr(bm, "DATA_DIR", tmp_path)
    bm.backtest(write=True)
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["headline_mode"] in ("contaminated", "vintage")
    assert d["in_sample"]["mode"] == "contaminated"
    assert d["vintage"]["mode"] == "vintage"
    assert d["min_edge"] is None
    assert d["min_edge_gate"]["gates"]


# ===========================================================================
# 5. THE min_edge GATE
# ===========================================================================
def test_min_edge_is_null_below_the_sample_threshold():
    gate = bm.min_edge_gate({"n_graded": bm.VINTAGE_MIN_GRADED_GAMES - 1,
                             "skill_vs_home_base": {"t": 9.0, "beats_baseline_95": True}})
    assert gate["min_edge"] is None
    assert gate["all_gates_open"] is False
    sample = [g for g in gate["gates"] if g["id"] == "vintage_sample"][0]
    assert sample["open"] is False


def test_min_edge_is_null_when_the_sample_is_big_but_unskilled():
    """Sample size is not evidence. 10,000 graded games with a t of 0.4 still
    buys no pick."""
    gate = bm.min_edge_gate({"n_graded": 10_000,
                             "skill_vs_home_base": {"t": 0.4, "beats_baseline_95": False}})
    assert gate["min_edge"] is None
    skill = [g for g in gate["gates"] if g["id"] == "out_of_sample_skill"][0]
    assert skill["open"] is False


def test_min_edge_is_null_without_a_graded_price_history():
    """Both model gates open and it is STILL null, because an edge threshold
    is a claim about EV against real prices and there are none."""
    gate = bm.min_edge_gate({"n_graded": 10_000,
                             "skill_vs_home_base": {"t": 3.0, "beats_baseline_95": True}})
    assert gate["min_edge"] is None
    price = [g for g in gate["gates"] if g["id"] == "graded_price_history"][0]
    assert price["open"] is False


def test_the_gate_can_actually_open():
    """A gate that can only ever be closed is a constant with extra steps. Feed
    it a passing sample, a passing skill test and a profitable graded history
    and a threshold comes out."""
    rows = ([{"edge": 0.06, "decimal": 2.0, "won": True}] * 240
            + [{"edge": 0.06, "decimal": 2.0, "won": False}] * 160)
    gate = bm.min_edge_gate(
        {"n_graded": 10_000, "skill_vs_home_base": {"t": 3.0, "beats_baseline_95": True}},
        graded_bets=rows)
    assert gate["all_gates_open"] is True
    assert gate["min_edge"] == pytest.approx(0.005)


def test_sweep_takes_the_smallest_threshold_that_clears_zero():
    """400 bets at a 0.06 edge win 60% at even money (+0.20 ROI). 400 more at a
    0.01 edge lose at the same rate (-0.20). Any threshold that includes the
    losers washes out, so the sweep must land on the first threshold that
    excludes them: 0.015."""
    good = ([{"edge": 0.06, "decimal": 2.0, "won": True}] * 240
            + [{"edge": 0.06, "decimal": 2.0, "won": False}] * 160)
    bad = ([{"edge": 0.01, "decimal": 2.0, "won": True}] * 160
           + [{"edge": 0.01, "decimal": 2.0, "won": False}] * 240)
    out = bm.sweep_min_edge(good + bad)
    assert out["min_edge"] == pytest.approx(0.015)
    low = [c for c in out["candidates"] if c["edge"] == 0.01][0]
    assert low["qualified"] is False


def test_sweep_on_no_history_is_null_with_a_reason():
    out = bm.sweep_min_edge([])
    assert out["min_edge"] is None
    assert "does not exist" in out["reason"]


def test_sweep_refuses_a_thin_sample():
    """Twenty bets that all won is not a threshold, it is a streak."""
    rows = [{"edge": 0.09, "decimal": 2.0, "won": True}] * 20
    out = bm.sweep_min_edge(rows)
    assert out["min_edge"] is None


def test_the_documented_threshold_is_the_measured_one():
    """600 comes from the forward split's paired Brier margin (+0.005794, sd
    0.08647): (1.645 * 0.08647 / 0.005794)^2 = 603, rounded down to 600. If
    somebody edits the constant, this test asks them to redo the arithmetic."""
    import math
    n = (bm.Z_95_ONE_SIDED * 0.08647 / 0.005794) ** 2
    assert 595 <= n <= 610
    assert 550 <= bm.VINTAGE_MIN_GRADED_GAMES <= math.ceil(n)
    assert bm.VINTAGE_MIN_GRADED_GAMES >= bm.VINTAGE_MIN_FIT_GAMES + bm.VINTAGE_MIN_EVAL_GAMES


def test_the_fit_window_is_a_target_size_not_a_share():
    """The eval window is what the gate counts, so the fit window is capped at
    a target size instead of taking 60% of the archive. On a long archive the
    fit stops at the target; on a short one it never takes more than half the
    dates."""
    long_dates = _daterange("2026-04-01", 120)
    long_games = _fake_games(long_dates, per_day=13)
    i = bm._vintage_cut_index(long_games, long_dates)
    fit_n = sum(1 for g in long_games if g["date"] < long_dates[i])
    assert bm.VINTAGE_FIT_TARGET_GAMES <= fit_n < bm.VINTAGE_FIT_TARGET_GAMES + 13
    assert i < len(long_dates) * bm.VINTAGE_FIT_MAX_DATE_SHARE

    short_dates = _daterange("2026-04-01", 10)
    short_games = _fake_games(short_dates, per_day=13)
    j = bm._vintage_cut_index(short_games, short_dates)
    assert j == 5           # half the dates, not the 300-game target


def test_the_tie_rate_is_measured_on_the_fit_window():
    """The extra-innings home rate used to come from the season-wide context,
    which the evaluation window helped produce. Small leak, real leak: a mode
    that calls itself honest cannot carry it."""
    extras_home = [{"innings": 10, "home_runs": 5, "away_runs": 4}] * 200
    extras_away = [{"innings": 11, "home_runs": 3, "away_runs": 4}] * 200
    assert bm._fit_tie_home(extras_home) > 0.6
    assert bm._fit_tie_home(extras_away) < 0.4
    # No extra-inning games in the window: the literature constant, never a
    # season-wide number.
    assert bm._fit_tie_home([{"innings": 9, "home_runs": 2, "away_runs": 1}]) == \
        bm.LITERATURE_TIE_HOME
    assert bm._fit_tie_home([]) == bm.LITERATURE_TIE_HOME


def test_paired_skill_is_signed_the_way_the_gate_reads_it():
    """Positive delta means the MODEL is better. A sign flip here would open
    the skill gate on a model that loses to the home-field baseline."""
    ys = [1] * 60 + [0] * 40
    base = 0.6
    sharp = [0.9 if y else 0.1 for y in ys]
    dull = [0.1 if y else 0.9 for y in ys]
    assert bm._paired_brier_skill(sharp, ys, base)["delta"] > 0
    assert bm._paired_brier_skill(dull, ys, base)["delta"] < 0
    assert bm._paired_brier_skill(sharp, ys, base)["beats_baseline_95"] is True
    assert bm._paired_brier_skill(dull, ys, base)["beats_baseline_95"] is False


# ===========================================================================
# helpers
# ===========================================================================
def _write_fake_leaderboards(data_dir, *, offense: float, as_of: str = "2026-08-04",
                             statsapi_codes: bool = False):
    """Three leaderboard files in the real shape, small enough to reason about."""
    orgs = ("WSH", "CWS", "TB", "SD") if statsapi_codes else ORGS
    (data_dir / "hitter_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": as_of,
        "teams": [{"team": o, "offense_plus": offense - 2 * i}
                  for i, o in enumerate(orgs)],
        "hitters": [],
    }), encoding="utf-8")
    (data_dir / "starter_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": as_of,
        "teams": [{"team": o, "rotation_plus": 104 - 3 * i, "starter_ip": 560.0}
                  for i, o in enumerate(orgs)],
        "starters": [{"mlbam": 101 + i, "team": o, "sem_plus": 110 - 5 * i,
                      "ip_per_gs": 5.5, "role": "SP"} for i, o in enumerate(orgs)],
    }), encoding="utf-8")
    (data_dir / "bullpen_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": as_of,
        "teams": [{"team": o, "bullpen_plus": 101 - 2 * i, "relief_ip": 380.0}
                  for i, o in enumerate(orgs)],
        "relievers": [{"mlbam": 201 + i, "team": o, "rem_plus": 103 - 4 * i}
                      for i, o in enumerate(orgs)],
    }), encoding="utf-8")

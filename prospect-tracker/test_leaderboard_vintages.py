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
    stored archive is not silently reinterpreted.

    Current-schema shape: every team row is as long as TEAM_COLUMNS. The first
    eleven entries are the schema-1 core and the schema-3 capture (the two order
    splits carry values, the xwOBA pair and the two availability columns are
    stated nulls), every later column is padded None the way a stated null is
    stored, and `throws` is populated the way the bulk join populates it."""
    pad = [None] * (len(lv.TEAM_COLUMNS) - 11)
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
        "feature_basis": {
            **{c: {"basis": lv.FEATURE_SOURCES[c],
                   "n": (len(ORGS) if c in ("off_vs_lhp", "off_vs_rhp") else 0)}
               for c in lv.SCHEMA3_TEAM_COLUMNS},
            "throws": {"basis": lv.FEATURE_SOURCES["throws"], "n": 4},
            "park": {"basis": "ABSENT: no park block in this fixture", "n": 0},
        },
        # columns 0-4 are the schema-1 core; 5-10 are the schema-3 dark capture
        # (xwoba_14, xwoba_30, off_vs_lhp, off_vs_rhp, lineup_strength, star_out);
        # the schema-4 and schema-5 columns follow as padded Nones
        "teams": {
            "NYM": [108.0 + bump, 104.0, 103.0, 560.0, 380.0,
                    None, None, 106.5, 109.0, None, None] + pad,
            "PHI": [104.0, 108.0 + bump, 99.0, 590.0, 350.0,
                    None, None, 102.0, 105.5, None, None] + pad,
            "ATL": [99.0, 97.0, 106.0 + bump, 540.0, 400.0,
                    None, None, 98.5, 100.0, None, None] + pad,
            "WSN": [93.0, 92.0, 94.0, 520.0, 410.0,
                    None, None, 91.0, 94.5, None, None] + pad,
        },
        "pitchers": {
            "101": [118.0, 5.9, "NYM", "SP", "L"],
            "102": [109.0, 5.4, "PHI", "SP", "R"],
            "103": [96.0, 5.1, "ATL", "SP", "R"],
            "104": [88.0, 4.6, "WSN", "SP", "L"],
        },
    }


def _schema2_record(vintage_date: str, *, covers_through: str | None = None) -> dict:
    """The archive as it existed BEFORE the schema-3 bump: five team columns,
    four pitcher columns, no feature_basis block. Ten of these are real files
    on the production box, so the reader's behaviour on them is a contract,
    not a hypothetical."""
    return {
        "schema": 2,
        "vintage_date": vintage_date,
        "covers_through": covers_through or vintage_date,
        "captured_at": f"{vintage_date}T07:10:00+00:00",
        "season": "2026",
        "org_codes": "canonical (trades.canonical_org)",
        "team_columns": ["offense_plus", "rotation_plus", "bullpen_plus",
                         "starter_ip", "relief_ip"],
        "pitcher_columns": ["plus", "ip_per_gs", "org", "role"],
        "sources": {},
        "n_teams": len(ORGS),
        "n_pitchers": 4,
        "teams": {
            "NYM": [108.0, 104.0, 103.0, 560.0, 380.0],
            "PHI": [104.0, 108.0, 99.0, 590.0, 350.0],
            "ATL": [99.0, 97.0, 106.0, 540.0, 400.0],
            "WSN": [93.0, 92.0, 94.0, 520.0, 410.0],
        },
        "pitchers": {
            "101": [118.0, 5.9, "NYM", "SP"],
            "102": [109.0, 5.4, "PHI", "SP"],
            "103": [96.0, 5.1, "ATL", "SP"],
            "104": [88.0, 4.6, "WSN", "SP"],
        },
    }


@pytest.fixture(autouse=True)
def _no_network_pitch_hand(monkeypatch):
    """The schema-3 throws join is ONE bulk StatsAPI call at assembly. No test
    here touches the network: the hand map is stubbed for every test, and the
    bulk-join test overrides this stub with a counting one."""
    import pal_export
    monkeypatch.setattr(pal_export, "load_pitch_hand",
                        lambda season: {101: "L", 102: "R", 103: "R", 104: "L",
                                        201: "R", 202: "R", 203: "L", 204: "R"})


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
    for a reason nobody would see. Same raw numbers in, same z out. The
    schema-3 dark columns ride the same call: one standardization, not two."""
    rec = _record("2026-06-01")
    cols = rec["team_columns"]
    dark_pos = {c: cols.index(c) for c in bm.DARK_TEAM_COLUMNS}
    from_vintage = bm.team_inputs_from_vintage(rec)
    direct = bm._assemble_team_inputs(
        {o: rec["teams"][o][0] for o in ORGS},
        {o: rec["teams"][o][1] for o in ORGS},
        {o: rec["teams"][o][2] for o in ORGS},
        {o: rec["teams"][o][3] for o in ORGS},
        {o: rec["teams"][o][4] for o in ORGS},
        {o: {c: rec["teams"][o][i] for c, i in dark_pos.items()} for o in ORGS},
    )
    assert from_vintage == direct
    assert from_vintage["NYM"]["z_off"] > from_vintage["WSN"]["z_off"]
    # The dark capture is standardized by the same seam, and stays dark: the
    # z exists on the row and nothing served consumes it.
    assert from_vintage["NYM"]["z_off_vs_lhp"] > from_vintage["WSN"]["z_off_vs_lhp"]


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
# 3a. SCHEMA 3: THE DARK CAPTURE (docs/diamond-betting.md section 5c)
# ===========================================================================
def test_dark_column_names_are_pinned_between_the_two_modules():
    """betting_model carries its own copy of each schema's dark column names so
    the assembly has a stable key set without an import cycle. Pinned PER SCHEMA:
    the copies must be the same tuples or the two modules quietly capture
    different features."""
    assert bm.DARK3_TEAM_COLUMNS == lv.SCHEMA3_TEAM_COLUMNS
    assert bm.DARK4_TEAM_COLUMNS == lv.SCHEMA4_TEAM_COLUMNS
    assert bm.DARK5_TEAM_COLUMNS == lv.SCHEMA5_TEAM_COLUMNS
    assert bm.DARK_TEAM_COLUMNS_BY_SCHEMA == {3: lv.SCHEMA3_TEAM_COLUMNS,
                                              4: lv.SCHEMA4_TEAM_COLUMNS,
                                              5: lv.SCHEMA5_TEAM_COLUMNS}
    assert bm.DARK_TEAM_COLUMNS == (lv.SCHEMA3_TEAM_COLUMNS + lv.SCHEMA4_TEAM_COLUMNS
                                    + lv.SCHEMA5_TEAM_COLUMNS)
    assert bm.DARK_PITCHER_COLUMNS == lv.SCHEMA3_PITCHER_COLUMNS
    assert set(lv.SCHEMA3_TEAM_COLUMNS) < set(lv.TEAM_COLUMNS)
    assert set(lv.SCHEMA3_PITCHER_COLUMNS) < set(lv.PITCHER_COLUMNS)


def test_every_stored_team_column_past_the_core_is_dark_in_some_schema():
    """A schema bump that adds a stored column without a dark tuple would store
    it and never standardize it, which is exactly how the nine schema-4 columns
    sat unread from 2026-09-09 to 2026-09-11. Every schema from 3 to the current
    one owns a tuple, and together they are every non-core stored column."""
    assert set(bm.DARK_TEAM_COLUMNS_BY_SCHEMA) == set(range(3, lv.SCHEMA + 1))
    assert bm.DARK_TEAM_COLUMNS == lv.TEAM_COLUMNS[5:]
    assert len(set(bm.DARK_TEAM_COLUMNS)) == len(bm.DARK_TEAM_COLUMNS)
    # The 5f and 5g sub-tuples are the registered names, in order.
    assert lv.SCHEMA5_PH_TEAM_COLUMNS == ("lineup_dis_vs_lhp", "lineup_dis_vs_rhp",
                                          "bench_adv_vs_lhp", "bench_adv_vs_rhp",
                                          "ph_share", "pen_lhp_share")
    assert lv.SCHEMA5_FLD_TEAM_COLUMNS == ("team_fld_runs",)


def _schema4_record(vintage_date: str) -> dict:
    """A record as the 2026-09-09 and 2026-09-10 files are: twenty team
    columns, the schema-4 capture populated, no schema-5 column at all."""
    cols = list(lv.TEAM_COLUMNS[:20])
    assert cols[-1] == "catch_frame_rate"
    rec = _record(vintage_date)
    rec["schema"] = 4
    rec["team_columns"] = cols
    i_frame, i_rest = cols.index("catch_frame_rate"), cols.index("rest_days")
    for n, org in enumerate(ORGS):
        row = rec["teams"][org][:11] + [None] * 9
        row[i_frame] = 1.5 - n
        row[i_rest] = 1 + (n % 2)
        rec["teams"][org] = row
    rec["feature_basis"].update({c: {"basis": "fixture", "n": len(ORGS)}
                                 for c in ("catch_frame_rate", "rest_days")})
    return rec


def test_schema4_columns_reach_the_standardization_seam():
    """THE PLUMBING 5f REGISTERED: a schema-4 column stored in a record now
    arrives on the assembled row with its z, through the same seam as the core,
    so the 5d harness standardizes exactly as the live path would."""
    rec = _schema4_record("2026-09-09")
    teams = bm.team_inputs_from_vintage(rec)
    assert teams["NYM"]["catch_frame_rate"] == 1.5
    assert teams["WSN"]["catch_frame_rate"] == -1.5
    assert teams["NYM"]["z_catch_frame_rate"] > teams["WSN"]["z_catch_frame_rate"]
    assert teams["NYM"]["rest_days"] == 1 and teams["PHI"]["rest_days"] == 2
    assert "catch_frame_rate" in teams["_scale"]["extras"]


def test_a_schema4_record_reads_none_for_every_schema5_column(store):
    """Absent is never zero, one schema up: a record that predates 5f and 5g
    reads None for each of their columns through every door, and the marking
    names the seam rather than leaving the key missing."""
    rec = _schema4_record("2026-09-09")
    row = lv.team_row(rec, "NYM")
    teams = bm.team_inputs_from_vintage(rec)
    for c in lv.SCHEMA5_TEAM_COLUMNS:
        assert row[c] is None, c
        assert teams["NYM"][c] is None and teams["NYM"]["z_" + c] is None, c
        assert c not in teams["_scale"]["extras"]
    fb = lv.feature_basis(rec)
    for c in lv.SCHEMA5_TEAM_COLUMNS:
        assert fb[c]["n"] == 0
        assert "predates the column" in fb[c]["basis"], c
    # Stored bases are never overwritten by the marking.
    assert fb["catch_frame_rate"] == {"basis": "fixture", "n": len(ORGS)}
    # And a schema-5 record written before 5f and 5g existed (the 5i-only shape)
    # is told apart by its OWN column list, not by its schema number.
    early5 = dict(rec, schema=5, team_columns=list(lv.TEAM_COLUMNS[:22]))
    fb5 = lv.feature_basis(early5)
    assert "predates the column" in fb5["ph_share"]["basis"]
    assert "predates the column" in fb5["team_fld_runs"]["basis"]
    # A column the record DOES store but gave no basis is a stated null of its
    # own kind, never counted as predating.
    assert fb5["lhb_share_vr"]["basis"].startswith("ABSENT")
    assert "predates the column" not in fb5["lhb_share_vr"]["basis"]
    assert lv.team_row(early5, "NYM")["ph_share"] is None


def test_a_schema2_record_reads_none_for_schema3_columns_with_marking(store):
    """The park precedent, applied: an old record returns None for a column it
    predates, through an explicit stated fallback, and the marking says WHY.
    A silent zero here would hand a dark feature a real-looking value exactly
    on the rows where it was never measured."""
    rec = _schema2_record("2026-08-01")
    # Reader helpers: None, never zero, for every schema-3 column.
    tr = lv.team_row(rec, "NYM")
    assert tr["offense_plus"] == 108.0
    for c in lv.SCHEMA3_TEAM_COLUMNS:
        assert tr[c] is None, f"{c} must read None off a schema-2 record"
    pr = lv.pitcher_row(rec, 101)
    assert pr["plus"] == 118.0 and pr["throws"] is None
    # The marking: a synthesized feature_basis that names the schema seam.
    fb = lv.feature_basis(rec)
    for c in lv.SCHEMA3_TEAM_COLUMNS + lv.SCHEMA3_PITCHER_COLUMNS:
        assert fb[c]["n"] == 0
        assert "predates the column" in fb[c]["basis"]
    # The model-side read routes the same Nones through the one assembly.
    teams = bm.team_inputs_from_vintage(rec)
    for c in bm.DARK_TEAM_COLUMNS:
        assert teams["NYM"][c] is None
        assert teams["NYM"]["z_" + c] is None
    assert teams["_scale"]["extras"] == {}
    assert bm.starter_inputs_from_vintage(rec)[101]["throws"] is None
    # And the bundle a game would be priced on carries the marking too.
    (store / "2026-08-01.json").write_text(json.dumps(rec), encoding="utf-8")
    lv.reset_cache()
    bm.reset_vintage_cache()
    b = bm.inputs_as_of("2026-08-05")
    assert b["source"] == "vintage"
    assert "predates the column" in b["feature_basis"]["throws"]["basis"]


def test_live_and_vintage_team_inputs_have_the_same_key_set(store, tmp_path, monkeypatch):
    """Key-set parity: a consumer that works on the live read works on the
    vintage read, dark columns included. Divergence here is how a candidate
    feature ends up measurable in one mode and silently absent in the other."""
    data = tmp_path / "data"
    data.mkdir()
    _write_fake_leaderboards(data, offense=110.0, with_orders=True)
    monkeypatch.setattr(bm, "DATA_DIR", data)
    rec = lv.snapshot(on_date="2026-08-05", vintage_dir=store, data_dir=data)["record"]
    live = bm.team_inputs()
    vint = bm.team_inputs_from_vintage(rec)
    org = ORGS[0]
    assert set(live[org].keys()) == set(vint[org].keys())
    assert set(live["_scale"].keys()) == set(vint["_scale"].keys())
    for c in bm.DARK_TEAM_COLUMNS:
        assert c in live[org] and ("z_" + c) in live[org]
    # The two order splits carry the same values through both doors: same
    # reduction helper, same artifact.
    assert live[org]["off_vs_lhp"] == vint[org]["off_vs_lhp"]
    assert live[org]["off_vs_rhp"] == vint[org]["off_vs_rhp"]
    # Pitcher rows: same key set; the hand is captured by the snapshot and
    # stated absent on the live read, never fetched per build.
    live_sp = bm.starter_inputs()
    vint_sp = bm.starter_inputs_from_vintage(rec)
    k = sorted(vint_sp)[0]
    assert set(live_sp[k].keys()) == set(vint_sp[k].keys())
    assert live_sp[k]["throws"] is None
    assert vint_sp[k]["throws"] in ("L", "R")


def test_throws_is_one_bulk_join_at_assembly(store, tmp_path, monkeypatch):
    """The hand join is ONE call to pal_export.load_pitch_hand per snapshot,
    never a per-pitcher or per-game lookup, and a pitcher the bulk map does
    not know stays None rather than being guessed."""
    import pal_export
    calls = []

    def counting_hand(season):
        calls.append(season)
        return {101: "L", 102: "R", 201: "R"}     # 103/104/202-204 unknown

    monkeypatch.setattr(pal_export, "load_pitch_hand", counting_hand)
    data = tmp_path / "data"
    data.mkdir()
    _write_fake_leaderboards(data, offense=110.0)
    rec = lv.reduce_current(on_date="2026-08-05", data_dir=data)
    assert calls == [2026], "exactly one bulk call, with the season"
    i_thr = rec["pitcher_columns"].index("throws")
    assert rec["pitchers"]["101"][i_thr] == "L"
    assert rec["pitchers"]["103"][i_thr] is None
    assert rec["feature_basis"]["throws"]["n"] == 3


def test_the_absent_columns_are_stated_facts_not_zeros(store, tmp_path):
    """xwoba_14/xwoba_30 have no committed builder and lineup_strength /
    star_out have none yet: the columns exist, hold None, and the record says
    why. The night a builder appears, the basis string changes and this test
    is the reminder to update it deliberately."""
    data = tmp_path / "data"
    data.mkdir()
    _write_fake_leaderboards(data, offense=110.0, with_orders=True)
    rec = lv.reduce_current(on_date="2026-08-05", data_dir=data)
    cols = rec["team_columns"]
    for c in ("xwoba_14", "xwoba_30", "lineup_strength", "star_out"):
        i = cols.index(c)
        assert all(row[i] is None for row in rec["teams"].values())
        assert rec["feature_basis"][c]["n"] == 0
        assert "ABSENT" in rec["feature_basis"][c]["basis"]
    assert "rolling-xwOBA builder" in rec["feature_basis"]["xwoba_14"]["basis"]
    # The populated pair really is populated, and PA-weighted.
    i_vl = cols.index("off_vs_lhp")
    assert all(row[i_vl] is not None for row in rec["teams"].values())
    assert rec["feature_basis"]["off_vs_lhp"]["n"] == len(ORGS)


# ===========================================================================
# 3b. SCHEMA 5: 5f AND 5g RIDE THE SAME RECORD WITHOUT TOUCHING SCHEMA 4
# ===========================================================================
@pytest.fixture()
def _fixed_builders(monkeypatch):
    """Every feed- and network-backed builder replaced by a fixed answer, so the
    record is a pure function of the fake boards and two runs can be compared
    byte for byte. The schema-4 values are deliberately non-null: a schema-5
    builder that wrote into them would show."""
    import betting_usage
    s4 = {c: {"values": {o: float(i + 1) for i, o in enumerate(ORGS)},
              "basis": f"fixture {c}"} for c in lv.SCHEMA4_TEAM_COLUMNS}
    monkeypatch.setattr(betting_usage, "build_schema4_team_columns",
                        lambda **k: {c: dict(b) for c, b in s4.items()})
    monkeypatch.setattr(betting_usage, "build_pitcher_schema4",
                        lambda pitchers, **k: {
                            "sp_rest_days": {"values": {m: 4 for m in pitchers},
                                             "basis": "fixture rest"},
                            "sp_tto3_bf": {"values": {}, "basis": "fixture tto"}})
    monkeypatch.setattr(betting_usage, "build_schema5_team_columns",
                        lambda **k: {"ph_share": {"values": {o: 0.05 for o in ORGS},
                                                  "basis": "fixture ph"},
                                     "pen_lhp_share": {"values": {o: 0.3 for o in ORGS},
                                                       "basis": "fixture pen"}})
    monkeypatch.setattr(lv, "build_team_fld_runs",
                        lambda hit, **k: {"team_fld_runs": {
                            "values": {o: 10.0 - i for i, o in enumerate(ORGS)},
                            "basis": "fixture fld"}})


def test_raising_schema5_builders_cost_only_their_own_columns(store, tmp_path,
                                                             monkeypatch, _fixed_builders):
    """THE ISOLATION 5f REGISTERED. Each schema-5 builder raising costs its own
    columns a stated null, the snapshot still writes, and every schema-1 to
    schema-4 value, basis, pitcher and park is byte-identical to the write in
    which the schema-5 builders ran: a schema-5 write carries the schema-4
    stream untouched."""
    import betting_usage
    data = tmp_path / "data"
    data.mkdir()
    _write_fake_leaderboards(data, offense=110.0, with_orders=True)
    ok = lv.reduce_current(on_date="2026-09-12", data_dir=data)
    i_ph = ok["team_columns"].index("ph_share")
    i_fld = ok["team_columns"].index("team_fld_runs")
    assert ok["teams"]["NYM"][i_ph] == 0.05 and ok["teams"]["NYM"][i_fld] == 10.0

    def boom(*a, **k):
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(lv, "build_lineup_hand_mix", boom)
    monkeypatch.setattr(lv, "build_ph_hitter_columns", boom)
    monkeypatch.setattr(betting_usage, "build_schema5_team_columns", boom)
    monkeypatch.setattr(lv, "build_team_fld_runs", boom)
    bad = lv.reduce_current(on_date="2026-09-12", data_dir=data)
    assert bad is not None and bad["schema"] == lv.SCHEMA

    keep = [i for i, c in enumerate(lv.TEAM_COLUMNS) if c not in lv.SCHEMA5_TEAM_COLUMNS]
    assert len(keep) == 20
    for org in ORGS:
        assert (json.dumps([bad["teams"][org][i] for i in keep])
                == json.dumps([ok["teams"][org][i] for i in keep])), org
    assert json.dumps(bad["pitchers"], sort_keys=True) == json.dumps(ok["pitchers"], sort_keys=True)
    assert bad["parks"] == ok["parks"]
    for c in lv.SCHEMA3_TEAM_COLUMNS + lv.SCHEMA4_TEAM_COLUMNS:
        assert bad["feature_basis"][c] == ok["feature_basis"][c], c
    for c in lv.SCHEMA5_TEAM_COLUMNS:
        i = lv.TEAM_COLUMNS.index(c)
        assert all(r[i] is None for r in bad["teams"].values()), c
        assert bad["feature_basis"][c]["n"] == 0
        assert bad["feature_basis"][c]["basis"].startswith("ABSENT"), c
        assert "raised RuntimeError" in bad["feature_basis"][c]["basis"], c

    # And the write itself goes through: a builder failure never costs a night.
    r = lv.snapshot(on_date="2026-09-12", vintage_dir=store, data_dir=data)
    assert r["written"] is True


def test_one_schema5_builder_raising_leaves_its_siblings_populated(tmp_path, monkeypatch,
                                                                   _fixed_builders):
    import betting_usage
    data = tmp_path / "data"
    data.mkdir()
    _write_fake_leaderboards(data, offense=110.0, with_orders=True)

    def boom(**k):
        raise RuntimeError("tally down")

    monkeypatch.setattr(betting_usage, "build_schema5_team_columns", boom)
    rec = lv.reduce_current(on_date="2026-09-12", data_dir=data)
    fb = rec["feature_basis"]
    assert fb["ph_share"]["n"] == 0 and "tally down" in fb["ph_share"]["basis"]
    assert fb["pen_lhp_share"]["n"] == 0
    assert fb["team_fld_runs"]["n"] == len(ORGS)
    assert fb["catch_frame_rate"]["n"] == len(ORGS)


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
                             statsapi_codes: bool = False, with_orders: bool = False):
    """Three leaderboard files in the real shape, small enough to reason about.
    `with_orders` adds the teams[].orders.vl/.vr blocks the schema-3 capture
    reduces; without it the split columns read None, which is itself a case
    the capture must survive."""
    orgs = ("WSH", "CWS", "TB", "SD") if statsapi_codes else ORGS

    def _orders(i):
        if not with_orders:
            return {}
        return {"orders": {
            "vl": [{"slot": s, "hem_plus": 100 + 2 * i + s, "pa": 400 + s}
                   for s in range(1, 10)],
            "vr": [{"slot": s, "hem_plus": 98 + 2 * i + s, "pa": 380 + s}
                   for s in range(1, 10)],
        }}

    (data_dir / "hitter_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": as_of,
        "teams": [{"team": o, "offense_plus": offense - 2 * i, **_orders(i)}
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


# ---- dark clocks read off the store (M12-05, 2026-09-25) -------------------
# 5e and 5i-B were dated off an expected 2026-09-11.json that was never written.
# The clock start is a fact about a vintage's own basis record, so it is read
# off the store; a look before the derived date is refused.

def _clock_rec(on: str, *, platoon: bool, lhb_n: int = 30, park_n: int = 29,
               estimator: str | None = lv.SPLIT_ESTIMATOR_ID) -> dict:
    basis = "orders.vl; platoon_splits.available %s" % platoon
    if estimator:
        basis += "; split_estimator %s" % estimator
    fb = {"lineup_dis_vs_lhp": {"basis": basis, "n": 30},
          "lhb_share_vr": {"basis": "orders.vr", "n": lhb_n},
          "park_by_hand": {"basis": "fa_meta park_factors_by_hand", "n": park_n}}
    return {"schema": 5, "vintage_date": on, "covers_through": on,
            "feature_basis": fb}


def _clock_store(tmp_path, recs: dict):
    for on, rec in recs.items():
        (tmp_path / f"{on}.json").write_text(json.dumps(rec), encoding="utf-8")
    lv.reset_cache()
    return tmp_path


def test_a_store_missing_09_11_starts_both_clocks_on_09_13(tmp_path):
    vdir = _clock_store(tmp_path, {
        "2026-09-10": {"schema": 4, "vintage_date": "2026-09-10",
                       "covers_through": "2026-09-10"},
        "2026-09-13": _clock_rec("2026-09-13", platoon=True),
        "2026-09-14": _clock_rec("2026-09-14", platoon=True),
    })
    for fam in ("5e", "5i-B"):
        clk = lv.dark_clock(fam, vintage_dir=vdir)
        assert clk["first_vintage"] == "2026-09-13", clk
        assert clk["earliest_look"] == "2026-10-11", clk
        assert not lv.dark_look_allowed(fam, "2026-10-09", vintage_dir=vdir)
        assert not lv.dark_look_allowed(fam, "2026-10-10", vintage_dir=vdir)
        assert lv.dark_look_allowed(fam, "2026-10-11", vintage_dir=vdir)


def test_the_clock_waits_for_its_own_condition(tmp_path):
    """A vintage that carries the columns but not the condition does not start
    the clock: platoon False holds 5e, park_by_hand n 28 holds 5i-B."""
    vdir = _clock_store(tmp_path, {
        "2026-09-11": _clock_rec("2026-09-11", platoon=False, park_n=28),
        "2026-09-12": _clock_rec("2026-09-12", platoon=True, park_n=28),
        "2026-09-13": _clock_rec("2026-09-13", platoon=True, park_n=29),
    })
    assert lv.dark_clock("5e", vintage_dir=vdir)["first_vintage"] == "2026-09-12"
    assert lv.dark_clock("5i-B", vintage_dir=vdir)["first_vintage"] == "2026-09-13"


def test_an_unstarted_clock_refuses_every_look(tmp_path):
    vdir = _clock_store(tmp_path, {"2026-09-10": {"schema": 4}})
    clk = lv.dark_clock("5e", vintage_dir=vdir)
    assert clk["first_vintage"] is None and clk["earliest_look"] is None
    assert not lv.dark_look_allowed("5e", "2027-01-01", vintage_dir=vdir)
    with pytest.raises(ValueError):
        lv.dark_clock_condition("5x", {})


# ---- the owner-signed 5e / 5f restart (2026-09-25) --------------------------
# The per-hand HEM+ switched to the platoon-ratio estimator. A vintage written
# under the old construction (available True, no marker) must not start either
# clock, and both refuse every date before the new start plus 28 days.

def test_old_construction_vintages_do_not_start_5e_or_5f(tmp_path):
    vdir = _clock_store(tmp_path, {
        "2026-09-13": _clock_rec("2026-09-13", platoon=True, estimator=None),
        "2026-09-30": _clock_rec("2026-09-30", platoon=True, estimator=None),
    })
    for fam in ("5e", "5f"):
        clk = lv.dark_clock(fam, vintage_dir=vdir)
        assert clk["first_vintage"] is None and clk["earliest_look"] is None, clk
        for d in ("2026-10-11", "2026-10-29", "2027-12-31"):
            assert not lv.dark_look_allowed(fam, d, vintage_dir=vdir), (fam, d)
    # 5i-B's condition does not read the per-hand construction and is unmoved.
    assert lv.dark_clock("5i-B", vintage_dir=vdir)["first_vintage"] == "2026-09-13"


def test_5e_restarts_at_the_first_new_construction_vintage(tmp_path):
    vdir = _clock_store(tmp_path, {
        "2026-09-13": _clock_rec("2026-09-13", platoon=True, estimator=None),
        "2026-09-30": _clock_rec("2026-09-30", platoon=True, estimator=None),
        "2026-10-02": _clock_rec("2026-10-02", platoon=True),
        "2026-10-03": _clock_rec("2026-10-03", platoon=True),
    })
    clk = lv.dark_clock("5e", vintage_dir=vdir)
    assert clk["first_vintage"] == "2026-10-02" and clk["earliest_look"] == "2026-10-30"
    # the superseded 2026-10-11 floor no longer admits a look
    for d in ("2026-10-11", "2026-10-29"):
        assert not lv.dark_look_allowed("5e", d, vintage_dir=vdir), d
    assert lv.dark_look_allowed("5e", "2026-10-30", vintage_dir=vdir)


def test_the_marker_alone_does_not_start_the_clock(tmp_path):
    """The restart rule keeps the 2026-09-10 condition: a marker on a night the
    split feed was down is not a qualifying vintage."""
    vdir = _clock_store(tmp_path, {
        "2026-10-02": _clock_rec("2026-10-02", platoon=False),
        "2026-10-03": _clock_rec("2026-10-03", platoon=True),
    })
    assert lv.dark_clock("5e", vintage_dir=vdir)["first_vintage"] == "2026-10-03"
    assert not lv.dark_clock_condition(
        "5e", _clock_rec("2026-10-04", platoon=True, estimator="season_shrink_v0"))


def test_5f_is_embargoed_to_after_the_2027_regular_season(tmp_path):
    vdir = _clock_store(tmp_path, {
        "2026-09-30": _clock_rec("2026-09-30", platoon=True, estimator=None),
        "2026-10-02": _clock_rec("2026-10-02", platoon=True),
    })
    clk = lv.dark_clock("5f", vintage_dir=vdir)
    assert clk["first_vintage"] == "2026-10-02"
    assert clk["earliest_look"] == "2027-10-06", clk
    for d in ("2026-10-30", "2027-07-01", "2027-10-05"):
        assert not lv.dark_look_allowed("5f", d, vintage_dir=vdir), d
    assert lv.dark_look_allowed("5f", "2027-10-06", vintage_dir=vdir)
    # a start late enough that start + 28 days passes the floor uses that date
    (tmp_path / "late").mkdir()
    late = _clock_store(tmp_path / "late", {
        "2027-09-20": _clock_rec("2027-09-20", platoon=True)})
    assert lv.dark_clock("5f", vintage_dir=late)["earliest_look"] == "2027-10-18"


def test_the_capture_basis_carries_the_estimator_marker():
    blob = {"platoon_splits": {"available": True, "estimator": lv.SPLIT_ESTIMATOR_ID},
            "bat_side": {"available": True}, "teams": []}
    out = lv.build_ph_hitter_columns(blob)
    rec = {"feature_basis": {c: {"basis": v["basis"]} for c, v in out.items()}}
    assert lv.dark_clock_condition("5e", rec) and lv.dark_clock_condition("5f", rec)
    blob["platoon_splits"].pop("estimator")
    out = lv.build_ph_hitter_columns(blob)
    rec = {"feature_basis": {c: {"basis": v["basis"]} for c, v in out.items()}}
    assert not lv.dark_clock_condition("5e", rec)

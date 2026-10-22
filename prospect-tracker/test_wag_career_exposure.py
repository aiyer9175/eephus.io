# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Measured MLB exposure on the career-WAR stints (owner decision 14c, 2026-09-11).

641 graduates (Mike Trout and Mookie Betts among them) have no MLB career_stats row, so the
WAG gate read a season-implied 600 PA / 200 IP per season for them. The career_war row now
carries the war_daily PA / IPouts of the same stints its WAR sums: the WAR funnel writes
them with the WAR, storage.persist_career_war_exposure backfills rows stored earlier, and
the gate reads them where career_stats measures nothing. The export never reads the cache.
Offline: synthetic frames, a throwaway sqlite file, a temp parquet cache.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

import stats
import storage
import value_framework as vf
import war_source

ROOT = Path(__file__).parent


def _frames():
    pd = pytest.importorskip("pandas")
    nan = float("nan")
    bat = pd.DataFrame([
        # hitter 1: two 2023 stints sum; a blank-WAR 2024 line is no stint at all
        {"mlb_ID": 1, "year_ID": 2023, "PA": 300, "WAR": 1.0},
        {"mlb_ID": 1, "year_ID": 2023, "PA": 200, "WAR": 0.5},
        {"mlb_ID": 1, "year_ID": 2024, "PA": 50, "WAR": nan},
        {"mlb_ID": 1, "year_ID": 2025, "PA": 610, "WAR": 3.1},
        # outside the window: neither WAR nor exposure
        {"mlb_ID": 1, "year_ID": 2009, "PA": 400, "WAR": 2.0},
        # pitcher 2's blank batting line
        {"mlb_ID": 2, "year_ID": 2024, "PA": 0, "WAR": nan},
    ])
    pit = pd.DataFrame([
        {"mlb_ID": 2, "year_ID": 2024, "IPouts": 540, "WAR": 3.0},
        {"mlb_ID": 2, "year_ID": 2025, "IPouts": 100, "WAR": 0.4},
        {"mlb_ID": 2, "year_ID": 2025, "IPouts": 50, "WAR": 0.1},
    ])
    return bat, pit


TARGETS = [("hitter", 1, False), ("pitcher", 2, True)]


def _bulk(monkeypatch, bat, pit):
    pytest.importorskip("pybaseball")
    frames = {"bat": bat, "pit": pit}

    def fake(side, **kw):
        if frames[side] is None:
            raise RuntimeError("download failed")
        return frames[side]
    monkeypatch.setattr(war_source, "stint_frame", fake)
    return stats.fetch_career_war_bulk(TARGETS, 2011, 2026)


# ------------------------------------------------------------------ the builder
def test_the_builder_sums_exposure_on_the_stints_it_sums_war_on(monkeypatch):
    bat, pit = _frames()
    out = _bulk(monkeypatch, bat, pit)
    h, p = out["hitter"], out["pitcher"]
    assert h["seasons"] == {"2023": 1.5, "2025": 3.1}
    assert h["seasons_pa"] == {"2023": 500, "2025": 610}        # 2024 blank, 2009 outside
    assert h["seasons_ip"] == {"2023": 0.0, "2025": 0.0}        # frame read, no stint
    assert p["seasons"] == {"2024": 3.0, "2025": 0.5}
    assert p["seasons_ip"] == {"2024": 180.0, "2025": 50.0}     # IPouts / 3, stints summed
    assert p["seasons_pa"] == {"2024": 0, "2025": 0}
    # one exposure entry per WAR season, never more
    for row in out.values():
        assert set(row["seasons_pa"]) == set(row["seasons_ip"]) == set(row["seasons"])


def test_a_side_that_did_not_load_is_omitted_not_zeroed(monkeypatch):
    bat, _ = _frames()
    out = _bulk(monkeypatch, bat, None)
    assert "seasons_ip" not in out["hitter"]
    assert out["hitter"]["seasons_pa"] == {"2023": 500, "2025": 610}
    no_col = bat.drop(columns=["PA"])
    assert stats.season_exposure_by_id(no_col, "bat") is None
    assert stats.season_exposure_by_id(None, "pit") is None


# ------------------------------------------------------------------ the table
@pytest.fixture
def db(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test_wag_exposure.db", raising=False)
    try:
        storage.init_db()
    except sqlite3.OperationalError:
        pytest.skip("storage cannot init on a temp path in this layout")
    yield storage


BASE = {"career_war": 3.0, "war_per_yr": 1.5, "war_seasons_count": 2, "source": "bbref"}


def test_upsert_merges_exposure_by_the_union_rule(db):
    db.upsert_career_war({"p": dict(BASE, seasons={"2023": 1.0, "2024": 2.0},
                                    seasons_pa={"2023": 400, "2024": 550},
                                    seasons_ip={"2023": 0.0, "2024": 0.0})})
    # a rebase-shaped payload carries no exposure: the stored maps survive it
    db.upsert_career_war({"p": dict(BASE, seasons={"2023": 1.1, "2024": 2.0}, source="ewar_v2")})
    r = db.load_career_war()["p"]
    assert r["seasons_pa"] == {"2023": 400, "2024": 550}
    # a narrow refetch: new wins per year, old years kept
    db.upsert_career_war({"p": dict(BASE, seasons={"2024": 2.2, "2025": 0.4},
                                    seasons_pa={"2024": 560, "2025": 120},
                                    seasons_ip={"2024": 0.0, "2025": 0.0})})
    r = db.load_career_war()["p"]
    assert r["seasons_pa"] == {"2023": 400, "2024": 560, "2025": 120}
    assert r["seasons_ip"] == {"2023": 0.0, "2024": 0.0, "2025": 0.0}
    assert set(r["seasons_pa"]) == set(r["seasons"])


def test_a_row_without_exposure_merges_exactly_as_before(db):
    db.upsert_career_war({"q": dict(BASE, seasons={"2015": 1.0, "2016": 2.0})})
    db.upsert_career_war({"q": dict(BASE, seasons={"2016": 2.5})})
    r = db.load_career_war()["q"]
    assert "seasons_pa" not in r and "seasons_ip" not in r


def _fetched_at(key):
    with storage.connect() as con:
        return con.execute("SELECT fetched_at FROM career_war WHERE player_key = ?",
                           (key,)).fetchone()[0]


def test_storing_exposure_touches_only_the_maps(db):
    db.upsert_career_war({"s": dict(BASE, seasons={"2024": 1.0, "2025": 2.0},
                                    seasons_pa={"2024": 400})})
    with storage.connect() as con:
        con.execute("UPDATE career_war SET fetched_at = '2026-01-01 00:00:00' WHERE player_key = 's'")
    before = db.load_career_war()["s"]
    n = db.store_career_war_exposure({"s": {"seasons_pa": {"2024": 999, "2025": 500},
                                            "seasons_ip": {"2024": 0.0, "2025": 0.0}},
                                      "nobody": {"seasons_pa": {"2024": 1}}})
    after = db.load_career_war()["s"]
    assert n == 1                                            # no row is created
    assert "nobody" not in db.load_career_war()
    assert after["seasons_pa"] == {"2024": 400, "2025": 500}  # the stored value wins
    assert after["seasons_ip"] == {"2024": 0.0, "2025": 0.0}
    assert {k: v for k, v in after.items() if not k.startswith("seasons_")} == \
        {k: v for k, v in before.items() if not k.startswith("seasons_")}
    assert after["seasons"] == before["seasons"]
    # the monthly WAR refresh keys on fetched_at: a backfill must not look like a fetch
    assert _fetched_at("s") == "2026-01-01 00:00:00"
    assert db.store_career_war_exposure({"s": {"seasons_pa": {"2024": 1}}}) == 0


# ------------------------------------------------------------------ the gate
CW = {"career_war": 3.0, "seasons": {"2024": 1.5, "2025": 1.5},
      "seasons_pa": {"2024": 100, "2025": 50}, "seasons_ip": {"2024": 0.0, "2025": 0.0}}


def _prov(w):
    return (w.pop("exposure_measured"), w.pop("exposure_source"), w.pop("exposure_load"),
            w.pop("exposure_unit"))


def test_the_exposure_needs_every_season():
    assert storage._career_war_exposure(CW) == (150.0, 0.0)
    partial = dict(CW, seasons_pa={"2024": 100})
    assert storage._career_war_exposure(partial) == (None, 0.0)
    assert storage._career_war_exposure({"seasons": {"2024": 1.0}}) == (None, None)
    assert storage._career_war_exposure(None) == (None, None)


def test_the_stints_fill_the_gate_where_career_stats_measures_nothing():
    """The 14c population: no MLB career_stats row, so the gate used to read two
    season-implied 600 PA loads (1,200, gate open). It now reads the 150 PA the WAR was
    earned over, and closes."""
    w = storage._engine_wag_result(50, False, "SS", 3.0, age=25.0, service_years=2.0,
                                   career_stats=[], career_war=CW)
    ref = vf.wag(50, False, 3.0, position="SS", service_years=2.0,
                 exposure_pa=150.0, exposure_ip=None, age=25.0)
    assert _prov(w) == (True, "war_daily", 150.0, "PA")
    assert w == ref and w["below_meaningful_exposure"] is True
    old = storage._engine_wag_result(50, False, "SS", 3.0, age=25.0, service_years=2.0,
                                     career_stats=[], career_war={"seasons": CW["seasons"]})
    assert old["exposure_source"] is None and old["below_meaningful_exposure"] is False


def test_a_row_already_measured_on_career_stats_does_not_move():
    """Decision 14c as answered covers the rows with nothing measured. A row measured on
    career_stats keeps that load, byte for byte, whatever its career_war row carries;
    WAG_EXPOSURE_STINTS_FIRST (off) is the switch for the wider change."""
    rows = [{"level": "MLB", "ab": 1000}]
    kw = dict(age=25.0, service_years=2.0, career_stats=rows)
    bare = storage._engine_wag_result(50, False, "SS", 3.0, **kw)
    got = storage._engine_wag_result(50, False, "SS", 3.0, career_war=CW, **kw)
    assert storage.WAG_EXPOSURE_STINTS_FIRST is False
    assert got == bare and got["exposure_source"] == "career_stats"
    assert got["exposure_load"] == 1100.0


def test_the_extension_switch_reads_the_stints_first(monkeypatch):
    monkeypatch.setattr(storage, "WAG_EXPOSURE_STINTS_FIRST", True)
    w = storage._engine_wag_result(50, False, "SS", 3.0, age=25.0, service_years=2.0,
                                   career_stats=[{"level": "MLB", "ab": 1000}], career_war=CW)
    assert (w["exposure_source"], w["exposure_load"]) == ("war_daily", 150.0)
    # a partial map still falls back to career_stats, and says so
    w2 = storage._engine_wag_result(50, False, "SS", 3.0, age=25.0, service_years=2.0,
                                    career_stats=[{"level": "MLB", "ab": 1000}],
                                    career_war=dict(CW, seasons_pa={"2024": 100}))
    assert (w2["exposure_source"], w2["exposure_load"]) == ("career_stats", 1100.0)


def test_a_pitcher_gates_on_the_stint_innings():
    cw = dict(CW, seasons_pa={"2024": 3, "2025": 0}, seasons_ip={"2024": 60.0, "2025": 30.1})
    w = storage._engine_wag_result(50, True, "RHP", 3.0, age=25.0, service_years=2.0,
                                   career_stats=[], career_war=cw)
    assert (w["exposure_source"], w["exposure_unit"], w["exposure_load"]) == ("war_daily", "IP", 90.1)
    assert w["below_meaningful_exposure"] is False
    # a pitcher with MLB batting rows but no innings on career_stats is still unmeasured
    # there, so the stints fill in
    w2 = storage._engine_wag_result(50, True, "RHP", 3.0, age=25.0, service_years=2.0,
                                    career_stats=[{"level": "MLB", "ab": 4}], career_war=cw)
    assert w2["exposure_source"] == "war_daily"


def test_the_debuted_block_serves_the_provenance():
    blk = storage._build_debuted_payload(50, False, "SS", age=25.0, career_war=CW,
                                         career_stats=[], wag_fv=50)
    w = blk["wag"]
    assert (w["exposure_source"], w["exposure_load"], w["exposure_unit"]) == ("war_daily", 150.0, "PA")
    assert w["exposure_measured"] is True and w["boom_label"] == "unsettled"


# ------------------------------------------------------------------ the backfill
def _cache(by_id):
    return lambda ids: {int(m): by_id[int(m)] for m in ids if int(m) in by_id}


def test_the_fill_uses_the_id_the_war_was_built_on(monkeypatch):
    asked = []

    def fake(ids):
        ids = list(ids)
        asked.extend(ids)
        return _cache({111: {2024: {"pa": 600, "ip": 0.0, "war": 1.0},
                             2025: {"pa": 580, "ip": 0.0, "war": 1.0}},
                       333: {2024: {"pa": 90, "ip": 0.0, "war": 0.5}}})(ids)
    monkeypatch.setattr(stats, "war_daily_exposure", fake)
    rebased = {"career_war": 2.0, "seasons": {"2024": 1.1, "2025": 1.1}, "source": "ewar_v2",
               "seasons_bwar": {"2024": 1.0, "2025": 1.0}, "ewar_coverage": {"mlbam": 111}}
    gap = dict(BASE, seasons={"2024": 0.5, "2025": 0.5})
    table = {"stored": dict(CW), "rebased": rebased, "gap": gap, "none": {"seasons": {}},
             "noid": dict(BASE, seasons={"2024": 1.0})}
    maps, rec = storage._career_war_exposure_fill(table, {"rebased": 222, "gap": 333})
    assert sorted(asked) == [111, 333]                    # the receipt id beats the id map
    assert "stored" not in maps                           # complete maps: untouched
    assert maps["rebased"] == {"seasons_pa": {"2024": 600, "2025": 580},
                               "seasons_ip": {"2024": 0.0, "2025": 0.0}}
    # 2025 is the cache's latest year but id 333 holds no 2025 stint: stays missing
    assert maps["gap"] == {"seasons_pa": {"2024": 90}, "seasons_ip": {"2024": 0.0}}
    assert rec["no_id"] == 1 and rec["seasons_no_stint"] == 1 and rec["rows_completed"] == 1
    assert "seasons_pa" not in table["rebased"]            # the input is not mutated


def test_the_fill_checks_the_war_vintage(monkeypatch):
    """A completed season whose stored bWAR differs from the cache's is not the same
    stints: not filled. The season in progress is filled and counted, since the WAR of a
    graduate outside the monthly cohort is not refreshed nightly."""
    monkeypatch.setattr(stats, "war_daily_exposure", _cache({
        7: {2024: {"pa": 500, "ip": 0.0, "war": 2.0}, 2025: {"pa": 610, "ip": 0.0, "war": 3.0}},
        8: {2024: {"pa": 400, "ip": 0.0, "war": 1.0}, 2025: {"pa": 300, "ip": 0.0, "war": 1.0}}}))
    table = {"stale_now": dict(BASE, seasons={"2024": 2.0, "2025": 1.2}),
             "revised": dict(BASE, seasons={"2024": 1.4, "2025": 1.0})}
    maps, rec = storage._career_war_exposure_fill(table, {"stale_now": 7, "revised": 8})
    assert maps["stale_now"]["seasons_pa"] == {"2024": 500, "2025": 610}
    assert maps["revised"]["seasons_pa"] == {"2025": 300}
    assert rec["seasons_current_newer"] == 1 and rec["seasons_vintage_mismatch"] == 1


def test_the_fill_is_loud_and_inert_without_a_cache(monkeypatch, caplog):
    monkeypatch.setattr(stats, "war_daily_exposure", lambda ids: {})
    table = {"k": dict(BASE, seasons={"2024": 1.0}, ewar_coverage={"mlbam": 5})}
    with caplog.at_level("WARNING", logger=storage.log.name):
        maps, rec = storage._career_war_exposure_fill(table)
    assert maps == {} and rec["cache_ok"] is False and rec["incomplete"] == 1
    assert "war_daily cache" in caplog.text


def test_persist_writes_the_fill_through_the_table(db, monkeypatch):
    db.upsert_career_war({"t": dict(BASE, seasons={"2024": 1.0, "2025": 2.0})})
    monkeypatch.setattr(db, "_durable_mlbam_by_key", lambda: {"t": 42})
    monkeypatch.setattr(stats, "war_daily_exposure", _cache(
        {42: {2024: {"pa": 300, "ip": 0.0, "war": 1.0}, 2025: {"pa": 610, "ip": 0.0, "war": 2.0}}}))
    dry = db.persist_career_war_exposure(dry_run=True)
    assert dry["persisted"] == 0 and "seasons_pa" not in db.load_career_war()["t"]
    rec = db.persist_career_war_exposure()
    assert rec["persisted"] == 1 and rec["rows_completed"] == 1
    assert db._career_war_exposure(db.load_career_war()["t"]) == (910.0, 0.0)
    assert db.persist_career_war_exposure()["persisted"] == 0     # idempotent


def test_war_daily_exposure_reads_the_last_good_cache(monkeypatch, tmp_path, caplog):
    pytest.importorskip("pyarrow")
    bat, pit = _frames()
    bat.to_parquet(tmp_path / "bat.parquet", index=False)
    pit.to_parquet(tmp_path / "pit.parquet", index=False)
    monkeypatch.setattr(war_source, "_cache_path", lambda side: tmp_path / f"{side}.parquet")
    stats._WAR_DAILY_EXPOSURE_MEMO.clear()
    got = stats.war_daily_exposure([1, 2, 99])
    assert got[1][2023] == {"pa": 500, "ip": 0.0, "war": 1.5}
    assert got[1][2009] == {"pa": 400, "ip": 0.0, "war": 2.0}   # the cache is not windowed
    assert 2024 not in got[1]                                   # blank-WAR line is no stint
    assert got[2] == {2024: {"pa": 0, "ip": 180.0, "war": 3.0},
                      2025: {"pa": 0, "ip": 50.0, "war": 0.5}}
    assert 99 not in got
    (tmp_path / "pit.parquet").unlink()
    stats._WAR_DAILY_EXPOSURE_MEMO.clear()
    with caplog.at_level("WARNING", logger=stats.log.name):
        assert stats.war_daily_exposure([1]) == {}               # both sides or nothing
    assert "no war_daily cache" in caplog.text
    stats._WAR_DAILY_EXPOSURE_MEMO.clear()


# ------------------------------------------------------------------ the export
def test_the_export_reads_stored_exposure_only():
    """No cache read at export: a served label must not depend on a gitignored file
    being present on the night. A table with no measured row is reported, loudly."""
    src = (ROOT / "storage.py").read_text(encoding="utf-8")
    body = src[src.index("def export_timeseries_json("):]
    body = body[:body.index("\ndef ", 10)]
    assert "war_daily_exposure" not in body and "_career_war_exposure_fill" not in body
    assert '_xcen = _career_war_exposure_census(career_war)' in body
    assert '"career_war_exposure", ok=False' in body
    assert storage._career_war_exposure_census({"a": CW, "b": {"seasons": {"2024": 1.0}},
                                                "c": {}}) == {"rows": 2, "complete": 1}


def test_the_payload_serves_career_war_without_the_exposure_maps():
    served = storage._served_career_war(CW)
    assert "seasons_pa" not in served and "seasons_ip" not in served
    assert served["seasons"] == CW["seasons"] and "seasons_pa" in CW
    bare = {"seasons": {"2024": 1.0}}
    assert storage._served_career_war(bare) is bare
    assert storage._served_career_war(None) == {}
    src = (ROOT / "storage.py").read_text(encoding="utf-8")
    assert '"career_war": _served_career_war(career_war.get(p.player_key, {})),' in src


# ------------------------------------------------------------------ registry, glossary, client
def test_the_registry_row_names_the_engine_not_the_survivor_curve():
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = next(r for r in reg["models"] if r["model_id"] == "wag")
    assert "survivor curve" not in row["champion"]
    assert "value_framework.wag" in row["champion"] and "war_daily" in row["champion"]
    assert row["verdict"] == "provisional"
    notes = row["notes"].lower()
    assert "realized-pit artifact does not exist" in notes
    assert "current-season vintage" in notes and "overseas_export" in notes


def test_the_glossary_says_which_load_the_gate_reads():
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    e = next(x for x in g["entries"] if x["id"] == "wag")
    m = e["methodology"]
    assert m.index("MLB Stats API rows") < m.index("war_daily")    # career_stats first
    assert "season in progress" in m and "exposure_measured false" in m


def _html() -> str:
    return (ROOT / "prospx" / "index.html").read_text(encoding="utf-8").replace("\r\n", "\n")


def test_prospx_wag_copy_quotes_the_engine_rules():
    """The sort chips and the farm Boom/Bust copy describe the served (engine) rule, with
    the numbers value_framework applies; the retired thresholds survive only on the
    server-rollback branch of the farm copy."""
    cfg = vf._config()["wag"]
    bb, me = cfg["boom_bust"], cfg["meaningful_exposure"]
    gate = f"{int(me['hitter_pa'])} PA or {int(me['pitcher_ip'])} IP"
    src = _html()
    chips = re.findall(r'<button class="chip" data-debut-sort="(vs_fv_proj|vs_fv_proj_low|warwag'
                       r'|warwag_low)"\s+title="([^"]*)"', src)
    assert len(chips) == 4
    for _, title in chips:
        assert "full-season equivalent" not in title and "primer" not in title
        assert "2 \u00d7" not in title and "without a WAG sink to the bottom" in title
    assert gate in dict(chips)["vs_fv_proj"] and "eFV grade at debut" in dict(chips)["vs_fv_proj"]
    farm = src[src.index("const boomTooltip = boomLeaf"):src.index("const topGradsTooltip")]
    one = [ln for ln in farm.split("\n") if "_wagOne" not in ln and "Share of settled" in ln
           and "percentile" in ln]
    assert any(f"percentile {float(bb['boom_percentile']):.2f} or higher" in ln for ln in one)
    assert any(f"percentile {float(bb['bust_percentile']):.2f} or lower" in ln for ln in one)
    assert f"{gate} measured" in farm
    for ln in one:
        assert "+2.5" not in ln and "800 PA" not in ln
    card = src[src.index('<span class="metric-label">Boom%</span>') - 400:
               src.index('<span class="metric-label">Bust%</span>')]
    # the card title reads "percentile 0.80+" since the COPY_3 pass (6fe85259)
    assert f"percentile {float(bb['boom_percentile']):.2f}+" in card
    assert "_wagUnified()" in card


def test_client_discloses_the_gate_load():
    mr = pytest.importorskip("py_mini_racer")
    src = _html()
    start = src.index("function wagExposureNote(")
    depth, i = 0, src.index("{", start)
    while True:
        depth += {"{": 1, "}": -1}.get(src[i], 0)
        if depth == 0 and src[i] == "}":
            break
        i += 1
    ctx = mr.MiniRacer()
    ctx.eval(src[start:i + 1])
    note = "(function(w){ return wagExposureNote({debuted_value: {wag: w}}); })"
    got = ctx.eval(note + "({exposure_measured: true, exposure_load: 1512.4, exposure_unit: 'PA'})")
    assert got.replace(",", "") == "1512 PA"
    assert ctx.eval(note + "({exposure_measured: true, exposure_load: 90.1, exposure_unit: 'IP'})") == "90 IP"
    assert "not on file" in ctx.eval(note + "({exposure_measured: false})")
    assert ctx.eval("wagExposureNote({})") == ""

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Measured MLB plate appearances on the stored career rows (owner answer M7M8-2 (c),
2026-10-01).

The Debuted MLB chip floor is 100 PA, and no stored MLB career row carried PA, so the
floor estimated PA as AB x 1.1. The StatsAPI season lines carry plateAppearances. Pinned
here:
  * the row builders write stats.MEASURED_PA_FIELD on MLB hitter rows only (never on a
    pitcher row or a MiLB row) and never under `pa`, which ten readers take before `ab`;
  * the cached-season reader and the backfill: the same id, season and AB fills the
    field, an AB mismatch leaves it absent, and a second run changes nothing;
  * the database migration rewrites payload_json only (fetched_at drives the monthly
    freshness skip) and is idempotent;
  * the nightly runs the migration ahead of the export, and the export ships the field.
"""
from __future__ import annotations

import inspect
import json
import re
import sqlite3

import pytest

import stats
import storage

F = stats.MEASURED_PA_FIELD


def _split(level, stat, team_id=1):
    return {"season": "2025", "_level": level, "_level_label": "x", "_org": "KCR",
            "team": {"id": team_id}, "stat": stat}


HIT = {"gamesPlayed": 30, "atBats": 100, "plateAppearances": 112, "baseOnBalls": 9,
       "strikeOuts": 20, "hits": 25, "totalBases": 40, "hitByPitch": 2, "sacFlies": 1,
       "avg": ".250", "obp": ".327", "slg": ".400", "ops": ".727"}


def test_field_is_not_pa():
    assert F == "pa_measured"


def test_row_builder_writes_measured_pa_on_mlb_hitter_rows_only():
    mlb = stats._row_from_split(_split("MLB", HIT), is_pitcher=False)
    assert mlb[F] == 112 and "pa" not in mlb and mlb["ab"] == 100
    aaa = stats._row_from_split(_split("AAA", HIT), is_pitcher=False)
    assert F not in aaa and "pa" not in aaa
    pit = stats._row_from_split(_split("MLB", {"inningsPitched": "10.0", "battersFaced": 44}),
                                is_pitcher=True)
    assert F not in pit
    no_pa = dict(HIT); no_pa.pop("plateAppearances")
    assert F not in stats._row_from_split(_split("MLB", no_pa), is_pitcher=False)


def test_combined_stints_sum_measured_pa():
    other = dict(HIT, atBats=50, plateAppearances=57)
    row = stats._combine_stints([_split("MLB", HIT, 1), _split("MLB", other, 2)], is_pitcher=False)
    assert row[F] == 169 and row["ab"] == 150
    row = stats._combine_stints([_split("AA", HIT, 1), _split("AA", other, 2)], is_pitcher=False)
    assert F not in row


def test_bulk_row_shape_carries_measured_pa():
    s = {"season": "2025", "sport": {"id": 1}, "league": {"name": "AL"}, "team": {},
         "stat": HIT, "player": {"id": 7}}
    assert stats._career_row_from_bulk_split(s, "hitting")[F] == 112
    s["sport"] = {"id": 11}
    assert F not in stats._career_row_from_bulk_split(s, "hitting")


def _write_cache(d, season, lines):
    splits = [{"season": str(season), "player": {"id": pid},
               "stat": {"atBats": ab, "plateAppearances": pa}} for pid, ab, pa in lines]
    (d / f"fa_statsapi_hitting_{season}.json").write_text(
        json.dumps({"copyright": "x", "stats": [{"splits": splits}]}), encoding="utf-8")


def test_cached_season_reader(tmp_path):
    _write_cache(tmp_path, 2024, [(1, 100, 112), (2, 50, 55), (2, 10, 11)])
    _write_cache(tmp_path, 2025, [(1, 400, 450)])
    (tmp_path / "fa_statsapi_hitting_bad.json").write_text("{}", encoding="utf-8")
    lines = stats.load_statsapi_hitting_pa(tmp_path)
    assert lines == {2024: {1: (100, 112)}, 2025: {1: (400, 450)}}  # player 2 had two lines


def test_fill_measured_pa_paths_and_idempotence():
    lines = {2024: {1: (100, 112), 3: (80, 90)}, 2025: {1: (400, 450)}}
    career = {
        "a": [{"season": 2025, "level": "MLB", "ab": 120, "is_pitcher": False},   # stale row
              {"season": 2024, "level": "MLB", "ab": 100, "is_pitcher": False},   # match
              {"season": 2024, "level": "AAA", "ab": 100, "is_pitcher": False}],  # MiLB
        "b": [{"season": 2023, "level": "MLB", "ab": 10, "is_pitcher": False}],   # season not cached
        "c": [{"season": 2024, "level": "MLB", "ab": 80, "is_pitcher": False}],   # second id matches
        "p": [{"season": 2024, "level": "MLB", "ip": 50.0, "is_pitcher": True}],
    }
    ids = {"a": [1], "b": [1], "c": [9, 3], "p": [1]}
    res = stats.fill_measured_pa(career, ids, lines)
    assert career["a"][1][F] == 112 and F not in career["a"][0] and F not in career["a"][2]
    assert career["c"][0][F] == 90 and F not in career["b"][0] and F not in career["p"][0]
    assert set(res["changed"]) == {"a", "c"}
    c = res["counts"]
    assert (c["mlb_hitter_rows"], c["filled"], c["ab_mismatch"], c["no_cached_season"]) == (4, 2, 1, 1)
    again = stats.fill_measured_pa(career, ids, lines)
    assert again["changed"] == {} and again["counts"]["already"] == 2
    keep = {"k": [{"season": 2024, "level": "MLB", "ab": 100, "is_pitcher": False, F: 111}]}
    assert stats.fill_measured_pa(keep, {"k": [1]}, lines)["changed"] == {}
    assert keep["k"][0][F] == 111
    none = {"k": [{"season": 2024, "level": "MLB", "ab": 100, "is_pitcher": False}]}
    assert stats.fill_measured_pa(none, {}, lines)["counts"]["no_id"] == 1


def test_database_migration_is_idempotent_and_keeps_fetched_at(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(stats, "ID_CACHE_FILE", tmp_path / "mlbam_ids.json")
    (tmp_path / "mlbam_ids.json").write_text(json.dumps({"k2": 3}), encoding="utf-8")
    storage.init_db()
    cache = tmp_path / "cache"
    cache.mkdir()
    _write_cache(cache, 2024, [(1, 100, 112), (3, 80, 90)])
    rows1 = [{"season": 2024, "level": "MLB", "ab": 100, "is_pitcher": False},
             {"season": 2024, "level": "AA", "ab": 50, "is_pitcher": False}]
    rows2 = [{"season": 2024, "level": "MLB", "ab": 80, "is_pitcher": False}]
    rows3 = [{"season": 2024, "level": "MLB", "ab": 99, "is_pitcher": False}]
    con = sqlite3.connect(storage.DB_PATH)
    for k, r in (("k1", rows1), ("k2", rows2), ("k3", rows3)):
        con.execute("INSERT INTO career_stats (player_key, payload_json, fetched_at) "
                    "VALUES (?, ?, '2026-01-01 00:00:00')", (k, json.dumps(r)))
    con.execute("INSERT INTO statlines (player_key, season, payload_json) VALUES (?, ?, ?)",
                ("k1", 2024, json.dumps({"mlbam_id": 1})))
    con.execute("INSERT INTO statlines (player_key, season, payload_json) VALUES (?, ?, ?)",
                ("k3", 2024, json.dumps({"mlbam_id": 1})))
    con.commit()
    con.close()

    first = storage.backfill_career_pa_measured(cache)
    assert (first["filled"], first["ab_mismatch"], first["players_updated"]) == (2, 1, 2)
    got = storage.load_career_stats()
    assert got["k1"][0][F] == 112 and F not in got["k1"][1]
    assert got["k2"][0][F] == 90            # bound through the id cache
    assert F not in got["k3"][0]            # 99 AB is not the 100 AB line
    assert got["k1"][0]["ab"] == 100 and "pa" not in got["k1"][0]
    assert set(storage.load_career_stats_meta().values()) == {"2026-01-01 00:00:00"}

    second = storage.backfill_career_pa_measured(cache)
    assert (second["filled"], second["players_updated"], second["already"]) == (0, 0, 2)
    assert storage.load_career_stats() == got


def test_nightly_runs_the_migration_before_the_export():
    import run_monthly
    src = inspect.getsource(run_monthly.run_daily)
    m = re.search(r'with _step\("d5f\. Measured MLB PA backfill \(career_stats\)", log\):', src)
    assert m, "run_daily has no d5f measured-PA step"
    step = src[m.end():src.index("with _step(", m.end())]
    assert "backfill_career_pa_measured()" in step
    assert "if chained" not in step  # every night, monthly ones included
    assert m.start() < src.index('with _step("d9. Rebuild timeseries')


def test_export_ships_measured_pa_on_debuts_lite_rows():
    src = inspect.getsource(storage.export_timeseries_json)
    m = re.search(r'cs_slim = \[\{f: r\.get\(f\) for f in \(([^)]*)\)', src)
    assert m and '"pa_measured"' in m.group(1), m and m.group(1)

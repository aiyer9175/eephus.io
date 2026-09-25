# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EV-03 modern-signal retention (tools/snapshot_modern_signals.py).

The contract under test, from docs/efv-v2/PROGRAM.md 3.4: per-season,
as-of-dated snapshots under data/signal_snapshots/<season>/, and a later
season never overwrites an earlier file. Also pinned: the live season merges
and never drops a row, a re-run with no new data leaves the bytes alone, the
statcast snapshot keeps season aggregates and drops per-event lists, and the
snapshots are not served (no deploy consumer ships the directory, no
publish_paths line, no data catalog row).

Every test that writes uses tmp_path; none touches data/.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from tools import snapshot_modern_signals as S

ROOT = Path(__file__).parent


def _db(path: Path, rows: dict[str, list[tuple[str, int, dict]]]) -> Path:
    con = sqlite3.connect(path)
    for t in S.DB_TABLES:
        con.execute(f"CREATE TABLE IF NOT EXISTS {t} (player_key TEXT PRIMARY KEY, "
                    "season INTEGER NOT NULL, payload_json TEXT NOT NULL, "
                    "fetched_at TEXT)")
        con.execute(f"DELETE FROM {t}")
    for t, items in rows.items():
        for pk, season, payload in items:
            con.execute(f"INSERT INTO {t} (player_key, season, payload_json) VALUES (?,?,?)",
                        (pk, season, json.dumps(payload)))
    con.commit()
    con.close()
    return path


def _statline(pk, season, ops, fetched):
    return (pk, season, {"player_key": pk, "season": season, "ops": ops,
                         "fetched_at": fetched, "level": "AA"})


def _run(tmp_path, db, *, today, data_dir=None, savant=None):
    return S.snapshot(snap_dir=tmp_path / "snap", data_dir=data_dir or tmp_path / "nodata",
                      db_path=db, savant_dir=savant or tmp_path / "nosavant", today=today)


def _rows(path: Path) -> dict:
    head, rows = S.decode(path.read_text(encoding="utf-8"))
    return head, {r["player_key"]: r for r in rows}


def test_a_later_season_never_overwrites_an_earlier_file(tmp_path):
    db = _db(tmp_path / "a.db", {"statlines": [_statline("a", 2026, ".800", "2026-09-20")]})
    _run(tmp_path, db, today=date(2026, 9, 24))
    f26 = tmp_path / "snap" / "2026" / "statlines.json"
    before = f26.read_bytes()
    # next season: the table rolls to 2027, and a stale 2026 row with a new
    # value still sits beside it. Neither may touch the 2026 file.
    con = sqlite3.connect(db)
    con.execute("INSERT INTO statlines (player_key, season, payload_json) VALUES (?,?,?)",
                ("b", 2026, json.dumps({"player_key": "b", "ops": ".999",
                                        "fetched_at": "2027-04-02"})))
    con.execute("UPDATE statlines SET season=2027, payload_json=? WHERE player_key='a'",
                (json.dumps({"player_key": "a", "ops": ".650", "fetched_at": "2027-04-30"}),))
    con.commit()
    con.close()
    res = _run(tmp_path, db, today=date(2027, 5, 1))
    assert res["live_season"] == 2027
    assert res["actions"]["2026/statlines.json"] == "frozen"
    assert f26.read_bytes() == before
    _, r27 = _rows(tmp_path / "snap" / "2027" / "statlines.json")
    assert r27["a"]["ops"] == ".650"


def test_an_earlier_season_stays_frozen_even_when_the_db_regresses(tmp_path):
    """Once a 2027 directory exists, 2026 is frozen whatever the DB holds."""
    db = _db(tmp_path / "a.db", {"statlines": [_statline("a", 2027, ".700", "2027-05-01")]})
    _run(tmp_path, db, today=date(2027, 5, 1))
    (tmp_path / "snap" / "2026").mkdir(parents=True)
    old = tmp_path / "snap" / "2026" / "statlines.json"
    old.write_text("SENTINEL", encoding="utf-8")
    _db(db, {"statlines": [_statline("a", 2026, ".100", "2027-06-01")]})
    res = _run(tmp_path, db, today=date(2027, 6, 1))
    assert res["actions"]["2026/statlines.json"] == "frozen"
    assert old.read_text(encoding="utf-8") == "SENTINEL"


def test_the_live_season_merges_and_never_drops_a_row(tmp_path):
    db = _db(tmp_path / "a.db", {"statlines": [_statline("a", 2026, ".800", "2026-08-01"),
                                               _statline("b", 2026, ".700", "2026-08-01")]})
    _run(tmp_path, db, today=date(2026, 8, 2))
    _db(db, {"statlines": [_statline("b", 2026, ".750", "2026-09-01")]})
    res = _run(tmp_path, db, today=date(2026, 9, 2))
    assert res["actions"]["2026/statlines.json"] == "updated"
    head, rows = _rows(tmp_path / "snap" / "2026" / "statlines.json")
    assert set(rows) == {"a", "b"}
    assert rows["a"]["ops"] == ".800" and rows["a"]["fetched_at"] == "2026-08-01"
    assert rows["b"]["ops"] == ".750"
    assert head["as_of"] == "2026-09-01"


def test_a_rerun_with_no_new_data_keeps_the_bytes(tmp_path):
    db = _db(tmp_path / "a.db", {"statlines": [_statline("a", 2026, ".800", "2026-08-01")]})
    _run(tmp_path, db, today=date(2026, 8, 2))
    f = tmp_path / "snap" / "2026" / "statlines.json"
    m = tmp_path / "snap" / S.MANIFEST
    before, mbefore = f.read_bytes(), m.read_bytes()
    res = _run(tmp_path, db, today=date(2026, 9, 2))
    assert res["actions"]["2026/statlines.json"] == "unchanged"
    assert f.read_bytes() == before and m.read_bytes() == mbefore


def test_a_crlf_checkout_is_not_a_change(tmp_path):
    """core.autocrlf=true rewrites tracked files to CRLF on checkout. That is
    not new data: neither the season file nor the manifest may be rewritten."""
    db = _db(tmp_path / "a.db", {"statlines": [_statline("a", 2026, ".800", "2026-08-01")]})
    _run(tmp_path, db, today=date(2026, 8, 2))
    snap = tmp_path / "snap"
    for p in (snap / "2026" / "statlines.json", snap / S.MANIFEST):
        p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    before = {p: p.read_bytes() for p in snap.rglob("*.json")}
    res = _run(tmp_path, db, today=date(2026, 9, 2))
    assert res["actions"]["2026/statlines.json"] == "unchanged"
    assert {p: p.read_bytes() for p in snap.rglob("*.json")} == before


def test_statcast_keeps_aggregates_and_drops_event_lists(tmp_path):
    payload = {
        "player_key": "p", "mlbam_id": 1, "season": 2026, "level": "AAA",
        "is_pitcher": True, "fetched_at": "2026-09-01",
        "coverage": {"games_checked": 3, "venues": [{"id": 1, "name": "x"}]},
        "contact_quality": {"avg_ev": 88.1, "hit_locations": [{"x": 1}] * 50,
                            "rolling_xwoba": [{"date": "d"}] * 20,
                            "spray": {"pull_pct": 40.0}},
        "pitch_movement": {"tracked_pitches": 100, "outings": [{"g": 1}] * 9,
                           "pitch_summary": [{"pitch_type": "FF", "pitch_name": "Four-Seam",
                                              "count": 60, "avg_velo": 95.1,
                                              "usage_by_batter_side": {"L": {"count": 20, "usage_pct": 40.0}}}]},
        "pitch_plot": {"points": [[1, 2]] * 500},
        "recent_games": [{"date": "d"}] * 5,
        "level_splits": [{"player_key": "p", "level": "AA", "fetched_at": "2026-09-01",
                          "contact_quality": {"avg_ev": 85.0}, "pitch_plot": {"points": [[1]]}}],
    }
    db = _db(tmp_path / "a.db", {"statcast_metrics": [("p", 2026, payload)]})
    _run(tmp_path, db, today=date(2026, 9, 2))
    text = (tmp_path / "snap" / "2026" / "statcast_metrics.json").read_text(encoding="utf-8")
    head, rows = S.decode(text)
    assert {(r["row"], r["level"]) for r in rows} == {("primary", "AAA"), ("split", "AA")}
    prim = next(r for r in rows if r["row"] == "primary")
    assert prim["contact_quality.avg_ev"] == 88.1
    assert prim["contact_quality.spray.pull_pct"] == 40.0
    assert prim["coverage.games_checked"] == 3
    cols = head["meta"]["pitch_summary_columns"]
    ff = dict(zip(cols, prim["pitch_movement.pitch_summary"][0]))
    assert ff["pitch_type"] == "FF" and ff["avg_velo"] == 95.1 and ff["usage_L_pct"] == 40.0
    for gone in ("hit_locations", "rolling_xwoba", "outings", "pitch_plot",
                 "recent_games", "venues"):
        assert gone not in "".join(head["columns"]), gone


def test_a_latest_only_sidecar_marks_older_seasons_partial(tmp_path):
    data = tmp_path / "d"
    data.mkdir()
    (data / "stuff_plus_aaa.json").write_text(json.dumps({
        "generated_at": "2026-09-24", "model": "m", "pool": "p",
        "players": {"1": {"stuff_plus": 101.0, "season": 2026},
                    "2": {"stuff_plus": 99.0, "season": 2024}}}), encoding="utf-8")
    db = _db(tmp_path / "a.db", {"statlines": [_statline("a", 2026, ".800", "2026-09-01")]})
    _run(tmp_path, db, today=date(2026, 9, 24), data_dir=data)
    h26 = json.loads((tmp_path / "snap" / "2026" / "astuff_plus.json").read_text(encoding="utf-8"))
    h24 = json.loads((tmp_path / "snap" / "2024" / "astuff_plus.json").read_text(encoding="utf-8"))
    assert h26["completeness"] == S.COMPLETE
    assert h24["completeness"] == S.PARTIAL
    assert h26["as_of"] == "2026-09-24" and h26["served"] is False


def test_savant_cache_snapshots_one_file_per_season_with_both_sides(tmp_path):
    sv = tmp_path / "sv"
    sv.mkdir()
    (sv / "batter_2024.csv").write_text(
        '"player_id","player_name","pa","xwoba","pos3_int_start_distance"\n'
        '10,"A, B",120,0.3141592,107\n', encoding="utf-8")
    (sv / "pitcher_2024.csv").write_text(
        '"player_id","player_name","pa","velocity"\n11,"C, D",200,94.2\n', encoding="utf-8")
    db = _db(tmp_path / "a.db", {"statlines": [_statline("a", 2026, ".800", "2026-09-01")]})
    _run(tmp_path, db, today=date(2026, 9, 24), savant=sv)
    head, rows = S.decode((tmp_path / "snap" / "2024" / "savant_minors.json").read_text(encoding="utf-8"))
    by = {(r["side"], r["mlbam_id"]): r for r in rows}
    assert by[("batter", 10)]["xwoba"] == 0.3142
    assert by[("pitcher", 11)]["velocity"] == 94.2
    assert "pos3_int_start_distance" not in head["columns"]


def test_the_monthly_run_calls_the_snapshot_with_a_heartbeat():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    _, _, main_src = src.partition("\ndef main(")
    assert "snapshot_modern_signals" in main_src
    assert '"signal_snapshots"' in main_src


def test_snapshots_are_not_served():
    publish = (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8")
    nightly = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    workflow = (ROOT.parent / ".github" / "workflows"
                / "deploy-prospect-tracker.yml").read_text(encoding="utf-8")
    for text in (publish, nightly, workflow):
        assert "signal_snapshots" not in text
    # both consumers take data/ at depth one plus NAMED shard dirs only
    assert "--include='/data/*.json'" in nightly and "--exclude='*'" in nightly
    assert "find data -maxdepth 1" in workflow
    import data_catalog
    assert not [a for a in data_catalog.ARTIFACTS
                if "signal_snapshots" in str(a.get("file", ""))]


def test_the_committed_snapshot_is_well_formed():
    snap = ROOT / "data" / "signal_snapshots"
    if not snap.is_dir():
        pytest.skip("no snapshot on disk")
    man = json.loads((snap / S.MANIFEST).read_text(encoding="utf-8"))
    assert man["files"], "manifest lists no files"
    for rel, info in man["files"].items():
        p = snap / rel
        head, rows = S.decode(p.read_text(encoding="utf-8"))
        assert head["served"] is False and head["season"] == int(rel.split("/")[0])
        assert head["as_of"] and len(rows) == head["n_rows"]
        keys = [json.dumps([r.get(k) for k in head["key"]]) for r in rows]
        assert len(keys) == len(set(keys)), f"{rel}: duplicate key rows"

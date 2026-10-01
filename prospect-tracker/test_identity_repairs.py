# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the identity-repair list (identity_repairs.py) and its tool.

tools/repair_identity_split_2026_09_30.py reads the list; the fWAR epoch's
step A wires its run_step() as a receipt-guarded pipeline step (owner answer
B4ID-2). The Flores entry (owner answer PVA-2, 2026-10-01) re-binds the MIL
RHP Joshua Flores's board row from 832714 (the BAL DSL catcher Jose Flores)
to his own id 834237.

Three groups: the list's schema, the tool on a fixture database (dry run,
apply, receipts, idempotence), and the repaired local prospects.db, opened
READ-ONLY.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

import identity_repairs as IR

HERE = Path(__file__).resolve().parent
DB = HERE / "prospects.db"
ID_CACHE = HERE / ".cache" / "mlbam_ids.json"

BOARD = "joshua_flores__sa3069242"
KEYS = (BOARD, "joshua_flores", "joshua_flores__noid")
WRONG, RIGHT = 832714, 834237


def _tool():
    spec = importlib.util.spec_from_file_location(
        "repair_identity_split_tool",
        HERE / "tools" / "repair_identity_split_2026_09_30.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _flores():
    return IR.by_id()["flores_joshua_834237"]


# ---------------------------------------------------------------------------
# The list's schema
# ---------------------------------------------------------------------------

def test_the_list_is_sound():
    assert IR.schema_errors() == []
    ids = [e["repair_id"] for e in IR.REPAIRS]
    assert len(ids) == len(set(ids))


def test_the_flores_entry_names_both_humans():
    e = _flores()
    assert (e["kind"], e["board_key"], e["wrong_id"], e["right_id"]) == \
        ("rebind", BOARD, WRONG, RIGHT)
    assert e["date"] == "2026-10-01"
    right, wrong = e["proof"]["right"], e["proof"]["wrong"]
    assert (right["name"], right["birth_date"], right["org"]) == \
        ("Joshua Flores", "2007-06-14", "MIL")
    assert (wrong["name"], wrong["birth_date"], wrong["position"], wrong["org"]) == \
        ("Jose Flores", "2007-11-03", "C", "BAL")
    assert e["birth_date"] == ("2007-11-03", "2007-06-14")
    assert set(e["fragment_keys"]) == set(KEYS) - {BOARD}


def test_the_m02_11_split_is_on_the_list():
    splits = {(e["board_key"], e["wrong_id"]): e["moved_to"]
              for e in IR.REPAIRS if e["kind"] == "row_split"}
    assert splits == {
        ("jose_rodriguez", 679563): "jose_rodriguez_679563",
        ("jose_rodriguez", 800412): "jose_rodriguez_800412",
        ("jose_rodriguez", 836624): "jose_rodriguez_836624",
        ("michael_massey", 695602): "michael_massey__sa3037259",
        ("carlos_rodriguez", 677578): "carlos_d_rodriguez",
    }


def test_schema_check_catches_a_broken_entry():
    bad = dict(_flores())
    bad["right_id"] = bad["wrong_id"]
    bad["date"] = "Oct 1"
    bad["proof"] = {"right": {"name": "x"}, "wrong": {}, "evidence": ""}
    errs = IR.schema_errors((bad,))
    assert any("wrong_id equals right_id" in m for m in errs)
    assert any("date must be" in m for m in errs)
    assert any("proof.wrong.birth_date missing" in m for m in errs)
    assert any("proof.evidence missing" in m for m in errs)
    assert IR.schema_errors((_flores(), _flores()))  # duplicate id


def test_every_rebind_has_its_forward_pin():
    import scrapers
    for e in IR.REPAIRS:
        if e["kind"] != "rebind":
            continue
        for k in (e["board_key"], *e["fragment_keys"]):
            assert scrapers.split_key_for_mlbam(k, e["wrong_id"]) == e["split_key"], k
            assert scrapers.split_key_for_mlbam(k, e["right_id"]) is None, k


# ---------------------------------------------------------------------------
# The tool on a fixture database
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE snapshots (id INTEGER PRIMARY KEY, source TEXT, snapshot_date TEXT,
  interval_label TEXT, player_key TEXT, player_name TEXT, position TEXT, org TEXT,
  rank INTEGER, fv REAL, status TEXT, tools_json TEXT, fv_plus INTEGER);
CREATE TABLE players (player_key TEXT PRIMARY KEY, player_name TEXT, position TEXT,
  org TEXT, is_pitcher INTEGER, updated_at TEXT, birth_date TEXT);
CREATE TABLE player_photos (mlbam_id INTEGER PRIMARY KEY, headshot_ctx TEXT NOT NULL,
  player_key TEXT, checked_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE statlines (player_key TEXT, season INTEGER, payload_json TEXT, fetched_at TEXT);
CREATE TABLE career_stats (player_key TEXT, payload_json TEXT, fetched_at TEXT);
CREATE TABLE acquisitions (player_key TEXT, method TEXT, year INTEGER, team_name TEXT,
  bonus_usd INTEGER, signing_date TEXT);
CREATE TABLE player_transactions (player_key TEXT, payload_json TEXT, fetched_at TEXT);
CREATE TABLE roster_status (player_key TEXT, payload_json TEXT, fetched_at TEXT);
CREATE TABLE metric_snapshots (player_key TEXT, snapshot_date TEXT);
"""


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    """The pre-repair Flores state as the local DB carried it on 2026-10-01."""
    db = tmp_path / "prospects.db"
    con = sqlite3.connect(db)
    con.executescript(_SCHEMA)
    for k in KEYS:
        con.execute("INSERT INTO players VALUES (?, 'Joshua Flores', 'SIRP', 'MIL', 1, "
                    "'2026-08-03', '2007-11-03')", (k,))
        con.execute("INSERT INTO player_transactions VALUES (?, ?, '2026-05-19')",
                    (k, json.dumps([{"description": "Baltimore Orioles signed C Jose Flores."}])))
        con.execute("INSERT INTO roster_status VALUES (?, '{\"mlb_debut_date\": null}', '')", (k,))
    con.execute("INSERT INTO player_photos (mlbam_id, headshot_ctx, player_key) "
                "VALUES (?, 'none', ?)", (WRONG, BOARD))
    con.execute("INSERT INTO statlines VALUES (?, 2026, ?, '')",
                (BOARD, json.dumps({"mlbam_id": WRONG, "is_pitcher": True})))
    con.execute("INSERT INTO career_stats VALUES (?, ?, '')",
                (BOARD, json.dumps([{"level_label": "DSL", "is_pitcher": False}])))
    con.execute("INSERT INTO acquisitions VALUES ('joshua_flores', 'draft', 2025, 'MIL', "
                "722500, NULL)")
    for k in (BOARD, "joshua_flores__noid"):
        con.execute("INSERT INTO acquisitions VALUES (?, 'international_fa', 2025, "
                    "'Baltimore Orioles', NULL, '2025-01-15')", (k,))
    con.execute("INSERT INTO metric_snapshots VALUES (?, '2026-09-30')", (BOARD,))
    con.commit()
    con.close()
    cache = tmp_path / "mlbam_ids.json"
    cache.write_text(json.dumps({"joshua_flores": WRONG, "joshua_flores__noid": WRONG,
                                 BOARD: None, "someone_else": 1}), encoding="utf-8")
    return db, cache


def _dump(db: Path) -> list:
    con = sqlite3.connect(db)
    out = []
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' "
                            "ORDER BY name").fetchall():
        out.append((t, sorted(map(repr, con.execute(f"SELECT * FROM {t}").fetchall()))))
    con.close()
    return out


def test_dry_run_on_a_fixture_plans_the_repair_and_writes_nothing(tmp_path):
    tool = _tool()
    db, cache = _fixture(tmp_path)
    before_db, before_cache = _dump(db), cache.read_text(encoding="utf-8")
    receipts = tmp_path / "receipts.jsonl"
    res = tool.repair_result(db, apply=False, cache_path=cache,
                             entries=(_flores(),), receipt_path=receipts)
    assert res["rc"] == 0 and res["refused"] == []
    # 2 photo bindings + 3 birth dates + statline + career line
    # + 2 Baltimore acquisitions + 3 transaction logs
    assert res["db_writes"] == 12
    assert res["cache_edits"] == 3
    assert _dump(db) == before_db
    assert cache.read_text(encoding="utf-8") == before_cache
    assert not receipts.exists()


def test_apply_on_a_fixture_rebinds_and_receipts_once(tmp_path):
    tool = _tool()
    db, cache = _fixture(tmp_path)
    receipts = tmp_path / "receipts.jsonl"
    res = tool.repair_result(db, apply=True, cache_path=cache,
                             entries=(_flores(),), receipt_path=receipts)
    assert res["rc"] == 0 and res["db_writes"] == 12
    con = sqlite3.connect(db)
    photos = dict(con.execute("SELECT mlbam_id, player_key FROM player_photos"))
    assert photos == {WRONG: None, RIGHT: BOARD}
    assert {r[0] for r in con.execute("SELECT birth_date FROM players")} == {"2007-06-14"}
    assert con.execute("SELECT COUNT(*) FROM statlines").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM career_stats").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM player_transactions").fetchone()[0] == 0
    # the bare key's own MIL draft row stays; the roster rows stay
    assert con.execute("SELECT player_key, team_name FROM acquisitions").fetchall() == \
        [("joshua_flores", "MIL")]
    assert con.execute("SELECT COUNT(*) FROM roster_status").fetchone()[0] == 3
    con.close()
    c = json.loads(cache.read_text(encoding="utf-8"))
    assert {k: c[k] for k in KEYS} == {k: RIGHT for k in KEYS}
    assert c["someone_else"] == 1
    rows = [json.loads(x) for x in receipts.read_text(encoding="utf-8").splitlines()]
    assert [(r["repair_id"], r["outcome"], r["db_writes"]) for r in rows] == \
        [("flores_joshua_834237", "applied", 12)]
    assert rows[0]["entry"] == tool.entry_fingerprint(_flores())
    # idempotent: a second pass plans nothing
    again = tool.repair_result(db, apply=False, cache_path=cache,
                               entries=(_flores(),), receipt_path=None)
    assert (again["rc"], again["db_writes"], again["cache_edits"]) == (0, 0, 0)


def test_a_drifted_value_is_refused_and_never_receipted(tmp_path):
    tool = _tool()
    db, cache = _fixture(tmp_path)
    con = sqlite3.connect(db)
    con.execute("UPDATE players SET birth_date = '1999-01-01' WHERE player_key = ?", (BOARD,))
    con.commit()
    con.close()
    receipts = tmp_path / "receipts.jsonl"
    res = tool.repair_result(db, apply=True, cache_path=cache,
                             entries=(_flores(),), receipt_path=receipts)
    assert res["rc"] == 1
    assert any("1999-01-01" in m for m in res["refused"])
    assert not receipts.exists()
    con = sqlite3.connect(db)
    assert con.execute("SELECT birth_date FROM players WHERE player_key = ?",
                       (BOARD,)).fetchone()[0] == "1999-01-01"
    con.close()


def test_run_step_backs_up_applies_and_then_skips(tmp_path):
    """The step A entry point on the whole list: the fixture has no M02-11
    rows, so those entries refuse and stay pending; Flores is applied behind
    a dated backup and receipted; a second run skips it."""
    tool = _tool()
    db, cache = _fixture(tmp_path)
    receipts = tmp_path / "receipts.jsonl"
    out = tool.run_step(db, cache_path=cache, receipt_path=receipts)
    assert out["backup"] and (tmp_path / out["backup"]).exists()
    assert out["rc"] == 1
    assert out["receipted"] == ["flores_joshua_834237"]
    con = sqlite3.connect(db)
    assert con.execute("SELECT player_key FROM player_photos WHERE mlbam_id = ?",
                       (RIGHT,)).fetchone()[0] == BOARD
    con.close()
    again = tool.run_step(db, cache_path=cache, receipt_path=receipts,
                          make_backup=False)
    assert "flores_joshua_834237" not in again["pending"]
    assert again.get("db_writes", 0) == 0


# ---------------------------------------------------------------------------
# The repaired local prospects.db (read-only)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def con():
    if not DB.exists():
        pytest.skip("prospects.db unavailable")
    c = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    yield c
    c.close()


def test_the_relievers_row_carries_his_own_id(con):
    bound = dict(con.execute("SELECT mlbam_id, player_key FROM player_photos "
                             "WHERE mlbam_id IN (?, ?)", (WRONG, RIGHT)).fetchall())
    assert bound.get(RIGHT) == BOARD
    assert bound.get(WRONG) not in KEYS
    q = ",".join("?" * len(KEYS))
    assert {r[0] for r in con.execute(
        f"SELECT birth_date FROM players WHERE player_key IN ({q})", KEYS)} == \
        {"2007-06-14"}
    for table, needle in (("statlines", '"mlbam_id": 832714'),
                          ("player_transactions", "C Jose Flores")):
        n = con.execute(f"SELECT COUNT(*) FROM {table} WHERE player_key IN ({q}) "
                        "AND payload_json LIKE ?", (*KEYS, f"%{needle}%")).fetchone()[0]
        assert n == 0, table
    assert con.execute(f"SELECT COUNT(*) FROM acquisitions WHERE player_key IN ({q}) "
                       "AND team_name = 'Baltimore Orioles'", KEYS).fetchone()[0] == 0
    if ID_CACHE.exists():
        c = json.loads(ID_CACHE.read_text(encoding="utf-8"))
        for k in KEYS:
            assert c.get(k) in (RIGHT, None), k

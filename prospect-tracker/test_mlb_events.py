# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The MLB events builder (mlb_events.py, run_daily step 9e-pre0g), pinned.

Wiring W01 part 1 (Q9_22a). Fixture tests build their own cache under tmp_path;
the reconciliation tests read the real cache (.cache/mlb_transactions/) and skip
when it is absent. Nothing here writes under data/ or the real preview directory.
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import mlb_events as M  # noqa: E402

NYY, BOS, AFF = 147, 111, 531   # two MLB clubs and a minor-league affiliate


def _tx(tid, pid, day, code, desc, frm=None, to=None, name=None):
    t = {"id": tid, "date": day, "typeCode": code, "description": desc}
    if pid is not None:
        t["person"] = {"id": pid, "fullName": name or f"Player {pid}"}
    if frm is not None:
        t["fromTeam"] = {"id": frm}
    if to is not None:
        t["toTeam"] = {"id": to}
    return t


def _cache(tmp_path, months: dict) -> Path:
    d = tmp_path / "tx"
    d.mkdir(parents=True, exist_ok=True)
    for (y, m), rows in months.items():
        with gzip.open(M.tx_path(y, m, d), "wt", encoding="utf-8") as fh:
            json.dump({"transactions": rows}, fh)
    return d


def _build(tx_dir, as_of, players=None, **kw):
    kw.setdefault("links", {})
    kw.setdefault("fa_events", [])
    kw.setdefault("arb", [])
    kw.setdefault("draft", {})
    return M.build(tx_dir=tx_dir, as_of=as_of, players=players or {},
                   mlb_ids=M.MLB_TEAM_IDS, **kw)


# --------------------------------------------------------------------------
# the flag and the dark path
# --------------------------------------------------------------------------

def test_the_flag_is_off_and_defined_once():
    assert M.MLB_EVENTS_LIVE is False
    assert M.output_dir() == M.PREVIEW_DIR
    hits = []
    for p in ROOT.glob("*.py"):
        if p.name.startswith("test_"):
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        if "MLB_EVENTS_LIVE =" in src:
            hits.append(p.name)
    assert hits == ["mlb_events.py"], hits


def test_nothing_is_written_under_data_while_the_flag_is_off(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(M, "DATA", data)
    monkeypatch.setattr(M, "SERVED_DIR", data / "mlb_events")
    monkeypatch.setattr(M, "PREVIEW_DIR", tmp_path / "cache" / "mlb_events" / "preview")
    tx = _cache(tmp_path, {(2026, 9): [_tx(1, 10, "2026-09-02", "SE", "NYY selected X.", AFF, NYY)]})
    fetched = []

    def fetch(url):
        fetched.append(url)
        if "2026-10-01" in url:
            return {"transactions": [_tx(2, 11, "2026-10-01", "CU", "NYY recalled Y.", AFF, NYY)]}
        return {"transactions": [_tx(1, 10, "2026-09-02", "SE", "NYY selected X.", AFF, NYY)]}

    res = M.nightly(as_of=date(2026, 10, 3), tx_dir=tx, fetch=fetch, log_fn=lambda *_: None,
                    players={10: {"key": "x", "name": "X"}, 11: {"key": "y", "name": "Y"}},
                    links={}, fa_events=[], arb=[], draft={})
    assert res["ok"] is True and len(fetched) == 2
    assert list(data.rglob("*")) == [], "the dark build wrote under data/"
    pre = M.PREVIEW_DIR
    assert sorted(p.name for p in pre.iterdir()) == ["10.json", "11.json", "index.json", "recent.json"]
    with pytest.raises(RuntimeError):
        M.write(M.build(tx_dir=tx, as_of=date(2026, 10, 3), players={}, links={},
                        fa_events=[], arb=[], draft={}), data / "mlb_events")
    assert not (ROOT / "data" / "mlb_events").exists()


# --------------------------------------------------------------------------
# the vocabulary and the dedupe
# --------------------------------------------------------------------------

def test_a_deal_keeps_every_player_and_drops_only_repeats(tmp_path):
    """One StatsAPI id is one deal with one row per person; a repeat of the same
    (id, person) is the only thing dropped."""
    desc = "New York Yankees traded RHP A to Boston Red Sox for LHP B."
    rows = [_tx(900, 1, "2026-07-01", "TR", desc, NYY, BOS),
            _tx(900, 2, "2026-07-01", "TR", desc, BOS, NYY),
            _tx(900, 2, "2026-07-01", "TR", desc, BOS, NYY),
            _tx(900, None, "2026-07-01", "TR", desc, NYY, BOS)]
    tx = _cache(tmp_path, {(2026, 7): rows})
    r = _build(tx, date(2026, 7, 31), players={1: {}, 2: {}})
    trades = [x for x in r["recent"]["rows"] if x["type"] == "trade"]
    assert sorted(x["mlbam"] for x in trades) == [1, 2]
    assert {x["deal"] for x in trades} == {900}
    assert all(x["desc"] == desc for x in trades), "the description is copied verbatim"
    assert r["index"]["counts"]["dupe_tx_person"] == 1
    assert r["index"]["counts"]["no_person"] == 1


def test_type_codes_and_the_mlb_club_rule(tmp_path):
    rows = [
        _tx(1, 1, "2026-06-01", "SE", "NYY selected the contract of A.", AFF, NYY),
        _tx(2, 1, "2026-06-02", "OPT", "NYY optioned A to AFF.", NYY, AFF),
        _tx(3, 1, "2026-06-03", "SFA", "NYY signed free agent A to a minor league contract.", None, NYY),
        _tx(4, 2, "2026-06-03", "SFA", "NYY signed free agent B.", None, NYY),
        _tx(5, 3, "2026-06-04", "REL", "AFF released C.", AFF, None),
        _tx(6, 3, "2026-06-05", "ASG", "C assigned to AFF.", None, AFF),
        _tx(7, 4, "2026-06-06", "NUM", "D changed number to 42.", None, NYY),
        _tx(8, 4, "2026-06-07", "R5M", "NYY selected D in the Rule 5 Draft.", BOS, NYY),
        _tx(9, 5, "2026-06-08", "DES", "NYY designated E for assignment.", NYY, None),
    ]
    tx = _cache(tmp_path, {(2026, 6): rows})
    r = _build(tx, date(2026, 6, 30), players={1: {}, 2: {}, 3: {}, 4: {}, 5: {}})
    got = {(x["mlbam"], x["type"]) for x in r["recent"]["rows"]}
    assert got == {(1, "callup"), (1, "optioned"), (1, "minor_deal"), (2, "fa_sign"),
                   (4, "rule5"), (5, "dfa")}
    assert all(x["type"] in M.TYPE_CODES for x in r["recent"]["rows"])


def test_draft_signings_are_split_on_the_draft_file(tmp_path):
    rows = [_tx(1, 1, "2025-07-20", "SGN", "NYY signed A.", None, NYY),
            _tx(2, 2, "2025-07-21", "SGN", "NYY signed B.", None, NYY),
            _tx(3, 3, "2026-07-21", "SGN", "NYY signed C.", None, NYY)]
    tx = _cache(tmp_path, {(2025, 7): rows[:2], (2026, 7): rows[2:]})
    r = _build(tx, date(2026, 7, 31), players={1: {}, 2: {}, 3: {}},
               draft={2025: frozenset({1})})
    types = {pid: p["rows"][0]["type"] for pid, p in r["players"].items()}
    assert types == {1: "draft_sign", 2: "minor_deal", 3: "draft_sign"}


def test_il_rows_parse_the_list_and_a_placement_inside_another_code(tmp_path):
    rows = [
        _tx(1, 1, "2025-05-01", "SC", "NYY placed A on the 15-day injured list. Right hamstring strain.", None, NYY),
        _tx(2, 1, "2025-05-21", "SC", "NYY activated A from the 15 day injured list.", None, NYY),
        _tx(3, 2, "2025-06-01", "CU", "NYY recalled B from AFF. Placed on the 60-day injured list.", AFF, NYY),
        _tx(4, 2, "2025-06-10", "SC", "NYY transferred B from the 10-day injured list to the 60-day injured list.", None, NYY),
        _tx(5, 3, "2025-06-01", "SC", "C roster status changed by NYY.", None, NYY),
    ]
    tx = _cache(tmp_path, {(2025, 5): rows[:2], (2025, 6): rows[2:]})
    r = _build(tx, date(2025, 12, 31), players={1: {}, 2: {}, 3: {}})
    a = r["players"][1]["rows"]
    assert [(x["type"], x["il"]) for x in a] == [("il_place", "15-day IL"), ("il_return", "15-day IL")]
    assert a[0]["il_days"] == 20 and a[0]["il_end"] == "2025-05-21"
    assert a[0]["desc"].endswith("Right hamstring strain."), "verbatim, nothing parsed out of it"
    assert set(a[0]) <= {"date", "type", "src", "desc", "tx", "from", "to", "il", "il_days", "il_end"}
    b = r["players"][2]["rows"]
    assert {x["type"] for x in b} == {"recall", "il_place"}, "the transfer is no event"
    assert r["players"][2]["il_seasons"] == {"2025": [122, 1]}, "open stint closes at Oct 1"
    assert r["players"][3]["rows"] == []
    assert r["index"]["il_placements_by_season"] == {"2025": 2}


def test_one_row_per_person_date_and_type(tmp_path):
    rows = [_tx(1, 1, "2026-05-02", "SC", "NYY activated A from the 60 day injured list.", None, NYY),
            _tx(2, 1, "2026-05-02", "SC", "NYY activated A from the 60-day injured list.", None, NYY)]
    tx = _cache(tmp_path, {(2026, 5): rows})
    r = _build(tx, date(2026, 5, 31), players={1: {}})
    (row,) = r["players"][1]["rows"]
    assert row["tx"] == 1 and row["tx_more"] == [2]
    assert row["desc_more"] == ["NYY activated A from the 60-day injured list."]


def test_an_fa_signing_absorbs_the_statsapi_row_within_three_days(tmp_path):
    rows = [_tx(1, 1, "2026-01-10", "SFA", "NYY signed free agent A.", None, NYY)]
    tx = _cache(tmp_path, {(2026, 1): rows})
    fa = [{"player_key": "a", "event_type": "signing", "event_date": "2026-01-12",
           "player_name": "A", "to_team": "NYY", "years": 2, "guarantee_usd": 18000000},
          {"player_key": "zz", "event_type": "qo_offered", "event_date": "2026-01-12"}]
    r = _build(tx, date(2026, 1, 31), players={1: {}}, links={"a": 1}, fa_events=fa)
    (row,) = r["players"][1]["rows"]
    assert row["src"] == "fa_class" and row["date"] == "2026-01-12" and row["years"] == 2
    assert row["desc"] == "NYY signed free agent A." and row["tx"] == 1
    assert r["index"]["counts"]["fa_unjoined"] == 1


def test_arbitration_salaries_are_season_rows_and_never_recent(tmp_path):
    tx = _cache(tmp_path, {(2026, 1): []})
    arb = [[2026, 1, "A", "NYY", 2, 5000000, 4800000, None, 200000, -100000, 1.2, 0]]
    r = _build(tx, date(2026, 1, 31), players={1: {}}, arb=arb)
    (row,) = r["players"][1]["rows"]
    assert row == {"date": None, "season": 2026, "type": "arb_salary", "src": "arb",
                   "club": "NYY", "arb_year": 2, "salary_usd": 5000000}
    assert r["recent"]["n_rows"] == 0


def test_recent_covers_35_days_and_no_row_leaves_the_window(tmp_path):
    rows = [_tx(1, 1, "2026-08-27", "CU", "NYY recalled A.", AFF, NYY),
            _tx(2, 1, "2026-08-28", "OPT", "NYY optioned A.", NYY, AFF),
            _tx(3, 2, "2026-09-30", "DES", "NYY designated B for assignment.", NYY, None),
            _tx(4, 2, "2026-10-04", "REL", "NYY released B.", NYY, None)]
    tx = _cache(tmp_path, {(2026, 8): rows[:2], (2026, 9): rows[2:3], (2026, 10): rows[3:]})
    r = _build(tx, date(2026, 10, 1), players={1: {}, 2: {}})
    assert r["recent"]["from"] == "2026-08-28"
    assert [x["tx"] for x in r["recent"]["rows"]] == [3, 2]
    assert r["index"]["window"] == {"first": "2026-08-01", "last": "2026-10-01",
                                    "through": "2026-09-30", "months_on_disk": 3}
    assert r["index"]["counts"]["outside_window"] == 1


# --------------------------------------------------------------------------
# the refresh
# --------------------------------------------------------------------------

def test_the_refresh_is_two_calls_on_a_complete_cache(tmp_path):
    tx = _cache(tmp_path, {(2026, m): [] for m in range(1, 11)})
    done = time.mktime((2026, 10, 2, 12, 0, 0, 0, 0, -1))
    for p in tx.glob("*.gz"):
        os.utime(p, (done, done))
    assert M.months_to_refresh(date(2026, 10, 3), tx) == [(2026, 10), (2026, 9)]


def test_the_refresh_fills_a_gap_and_a_month_fetched_while_open(tmp_path):
    tx = _cache(tmp_path, {(2026, m): [] for m in range(1, 8)})
    fetched_on = time.mktime((2026, 7, 23, 19, 0, 0, 0, 0, -1))   # the cache's real date
    for p in tx.glob("*.gz"):
        os.utime(p, (fetched_on, fetched_on))
    assert M.months_to_refresh(date(2026, 10, 3), tx) == [(2026, 10), (2026, 9), (2026, 8), (2026, 7)]
    assert M.months_to_refresh(date(2026, 10, 3), tx, cap=2) == [(2026, 10), (2026, 9)]


def test_a_short_read_never_shrinks_a_month_and_a_failure_is_reported(tmp_path):
    tx = _cache(tmp_path, {(2026, 9): [_tx(1, 1, "2026-09-01", "CU", "x", AFF, NYY),
                                       _tx(2, 2, "2026-09-02", "CU", "y", AFF, NYY)]})
    done = time.mktime((2026, 10, 2, 12, 0, 0, 0, 0, -1))
    os.utime(M.tx_path(2026, 9, tx), (done, done))

    def fetch(url):
        if "2026-09-01" in url:
            return {"transactions": [_tx(1, 1, "2026-09-01", "CU", "x", AFF, NYY)]}
        raise OSError("statsapi down")

    out = M.refresh(date(2026, 10, 3), tx_dir=tx, fetch=fetch, log_fn=lambda *_: None)
    assert out["calls"] == 2 and out["written"] == []
    assert out["kept"] and out["failed"]
    with gzip.open(M.tx_path(2026, 9, tx), "rt", encoding="utf-8") as fh:
        assert len(json.load(fh)["transactions"]) == 2


# --------------------------------------------------------------------------
# the real cache: the invariants the plan registers
# --------------------------------------------------------------------------

IL_TABLE = M.TX_DIR / "il_table.json"


@pytest.fixture(scope="module")
def real():
    if not M.cache_months() or not IL_TABLE.exists():
        pytest.skip("no league transaction cache on this box")
    if not (ROOT / "data" / "mlb_player_detail.json").exists():
        pytest.skip("run mlb_player_export.py (writes data/mlb_player_detail.json)")
    return M.build(as_of=date.today(), fa_events=[])


def test_per_player_il_days_reconcile_with_il_table(real):
    il = json.loads(IL_TABLE.read_text(encoding="utf-8"))["il"]
    checked = 0
    for pid, p in real["players"].items():
        mine = p["il_seasons"]
        theirs = il.get(str(pid)) or {}
        for y in range(2015, 2026):
            a, b = mine.get(str(y)), theirs.get(str(y))
            assert (a is None) == (b is None), (pid, y, a, b)
            if a is not None:
                assert a[0] == b[0] and a[1] == b[1], (pid, y, a, b)
                checked += 1
        days = Counter()
        for r in p["rows"]:
            if r["type"] == "il_place":
                days[r["date"][:4]] += r["il_days"]
        assert {y: d for y, d in days.items() if d} == {y: v[0] for y, v in mine.items() if v[0]}
    assert checked > 1000


def test_per_season_placements_match_the_audited_series(real):
    audited = json.loads((ROOT / "data" / "fa_pt_risk_eval.json").read_text(
        encoding="utf-8"))["data_phase"]["per_year_placements"]
    mine = real["index"]["il_placements_by_season"]
    assert mine["2025"] == audited["2025"] == 850
    for y in range(2015, 2026):
        assert mine[str(y)] == audited[str(y)], y
    assert mine["2026"] >= audited["2026"]


def test_no_event_outside_the_cache_window_and_one_row_per_key(real):
    w = real["index"]["window"]
    assert w["first"] == "2008-01-01"
    for pid, p in real["players"].items():
        keys = Counter((r.get("date") or f"season:{r.get('season')}", r["type"]) for r in p["rows"])
        assert max(keys.values(), default=1) == 1, pid
        for r in p["rows"]:
            assert r["type"] in M.TYPE_CODES
            if r["src"] == "statsapi":
                assert w["first"] <= r["date"] <= w["last"], (pid, r)
    rk = Counter((x["mlbam"], x["date"], x["type"]) for x in real["recent"]["rows"])
    assert max(rk.values(), default=1) == 1


def test_the_july_2026_trades_keep_one_deal_per_transaction_id(real):
    p = M.tx_path(2026, 7)
    if not p.exists():
        pytest.skip("tx_2026_07.json.gz not on disk")
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        raw = json.load(fh)["transactions"]
    ids = set(M.MLB_TEAM_IDS)
    tr = [t for t in raw if t.get("typeCode") == "TR" and (t.get("person") or {}).get("id")
          and ({(t.get("toTeam") or {}).get("id"), (t.get("fromTeam") or {}).get("id")} & ids)]
    want = {(t["id"], t["person"]["id"]) for t in tr}
    full = M.build(as_of=date(2026, 7, 31), fa_events=[], players={})
    got = {(x["tx"], x["mlbam"]) for x in full["recent"]["rows"]
           if x["type"] == "trade" and x["date"].startswith("2026-07")}
    assert got == want
    assert len({x[0] for x in got}) == len({t["id"] for t in tr})


# --------------------------------------------------------------------------
# the wiring
# --------------------------------------------------------------------------

def test_the_step_is_wired_into_the_daily():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    daily = src[src.index("def run_daily("):src.index("\ndef ", src.index("def run_daily(") + 10)]
    step = daily.index('_step("9e-pre0g. MLB transaction events (mlb_events preview)"')
    assert daily.index('_step("9e-pre0e. In-Game Management nightly') < step
    assert step < daily.index('_step("9e-pre-wx. Forecast weather capture')
    assert "import mlb_events as _mev" in daily
    assert "_mev.nightly(log_fn=log.info)" in daily
    assert '_hb.record("mlb_events", ok=bool(_me["ok"])' in daily
    assert '_hb.record("mlb_events", ok=False' in daily
    assert '_record_ingest("mlb_events", bool(_me["ok"])' in daily
    assert '_record_ingest("mlb_events", False' in daily
    assert src.count("9e-pre0g") >= 2
    i = src.index("SCHEDULED_EXPORTS = (")
    assert '"mlb_events"' in src[i:src.index("\n)\n", i)]


def test_the_served_directory_is_gitignored():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/mlb_events/" in lines

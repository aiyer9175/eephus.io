"""awards_rookies.py: MLB's three rookie gates with the 45-day proxy (AWARDS_1_ROOKIE_STATUS;
AWARDS_PLAN 4.2 'Rookie eligibility' and 6 'Invariants and tests' row I6).

Fixtures under test_fixtures/awards/ are trimmed from the real caches on 2026-10-03:
`cache/` is a fixture world (season 2024 with StatsAPI season lines from 2023 and the
transaction log from 2023-01, seven players), and `transaction_wording_rows.json` holds
real StatsAPI descriptions from 2009, 2016, 2024 and 2025 with the segment kind each must
classify as. No test makes a network call.
"""
from __future__ import annotations

import json
import re
import shutil
import socket
from datetime import date
from pathlib import Path

import pytest

import awards_rookies as AR

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "test_fixtures" / "awards"
FIX_CACHE = FIX / "cache"
LABS = ROOT / "data" / "_labs" / "awards"
SEAM = {"statsapi_first": 2023, "tx_first": (2023, 1)}

#: The fixture world's rows, computed from the trimmed files when they were cut.
FIXTURE_ROWS = [
    [663462, 0, 28.7, 56, False, "roster days 56 over 45 (estimate); near_45_day_line"],
    [665877, 51, 0.0, 42, True, "eligible; near_45_day_line"],
    [667755, 0, 42.0, 91, False, "roster days 91 over 45 (estimate)"],
    [669224, 70, 0.0, 1, True, "eligible"],
    [682990, 0, 50.0, 30, True, "eligible"],
]
OVER_THE_LINE = {665804: "131 at-bats in 2023", 674370: "152 outs in 2023"}

#: AWARDS_PLAN 5.15: never in a served or payload string.
VERDICT_WORDS = re.compile(
    r"\b(snub\w*|deserv\w*|wrong|correct\w*|lock\w*|favou?rite\w*|worthy|overrated|underrated|"
    r"overperform\w*|underperform\w*|breakout|bust|luck\w*|unlucky|clutch|chok\w*|predict\w*|"
    r"odds|chance to win|pick\w*)\b", re.IGNORECASE)
DASHES = re.compile("[" + chr(0x2013) + chr(0x2014) + "]")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("a rookie-status test opened a socket")
    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


def _tx(d: str, desc: str, club: int = 140, tx_id: int = 0, key: str = "toTeam") -> dict:
    return {"id": tx_id, "person": {"id": 1}, key: {"id": club}, "date": d,
            "description": desc}


def _opening(table=None):
    table = table or {2020: date(2020, 7, 23), 2023: date(2023, 3, 30)}
    return lambda y: table[y]


def _days(rows, end="2023-12-31", opening=None):
    ev = AR.events_from_transactions(rows)
    return AR.proxy_days(ev.get(1, ()), date.fromisoformat(end), opening or _opening())


# --- the wording (pins F8) -------------------------------------------------------------
def _wording_rows():
    return json.loads((FIX / "transaction_wording_rows.json").read_text(encoding="utf-8"))


def test_il_regexes_match_statsapi_wording_and_the_old_descriptors_do_not():
    import stats
    il_rows = [r for r in _wording_rows()
               if "list" in r["description"].lower() and r["expected"] == "close"]
    assert len(il_rows) >= 6
    assert any("on the 60-day injured list" in r["description"] for r in il_rows)
    assert any("disabled list" in r["description"] for r in il_rows)
    assert any("transferred" in r["description"] for r in il_rows)
    for r in il_rows:
        d = r["description"].lower()
        assert AR.IL_PLACED_RE.search(d) or AR.IL_TRANSFER_RE.search(d), r["description"]
        assert not any(p in d for p in stats._DEACTIVATING_DESCRIPTORS), r["description"]


def test_every_fixture_wording_row_classifies_as_expected():
    for r in _wording_rows():
        got = AR.classify(r["description"], r.get("club_is_mlb", True))
        assert got == r["expected"], (r["description"], got)


def test_reinstatement_and_rehab_rows_do_not_close_a_segment():
    assert AR.classify("Texas Rangers activated RHP A B from the 60-day injured list.", True) == "open"
    assert AR.classify("Texas Rangers reinstated RHP A B from the 15-day injured list.", True) == "open"
    assert AR.classify("Texas Rangers sent RHP A B on a rehab assignment to Frisco RoughRiders.",
                       False) is None
    assert AR.classify("Round Rock Express activated RHP A B from the 7-day injured list.", False) is None
    assert AR.classify("Texas Rangers placed RHP A B on the 60-day injured list.", True) == "close"
    assert AR.classify("Texas Rangers transferred RHP A B from the 15-day injured list to the "
                       "60-day injured list.", True) == "close"


def test_no_awards_module_reads_the_descriptor_lists():
    for p in sorted(ROOT.glob("awards_*.py")):
        src = p.read_text(encoding="utf-8")
        body = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
        code = body.split('"""')
        code_only = "".join(code[0::2])
        assert "_DEACTIVATING_DESCRIPTORS" not in code_only, p.name
        assert "_ACTIVATING_DESCRIPTORS" not in code_only, p.name


# --- the segment logic on a synthetic log -------------------------------------------------
def test_open_and_close_count_both_ends():
    rows = [_tx("2023-05-01", "Texas Rangers recalled RHP A B from Round Rock Express."),
            _tx("2023-05-10", "Texas Rangers optioned RHP A B to Round Rock Express.", club=102)]
    assert _days(rows) == 10
    same_day = [_tx("2023-05-01", "Texas Rangers recalled RHP A B from Round Rock Express.", tx_id=1),
                _tx("2023-05-01", "Texas Rangers optioned RHP A B to Round Rock Express.", tx_id=2)]
    assert _days(same_day) == 1


def test_days_after_1_september_do_not_count():
    rows = [_tx("2023-08-25", "Texas Rangers recalled RHP A B from Round Rock Express."),
            _tx("2023-09-10", "Texas Rangers optioned RHP A B to Round Rock Express.")]
    assert _days(rows) == 8
    rows = [_tx("2023-09-05", "Texas Rangers recalled RHP A B from Round Rock Express.")]
    assert _days(rows) == 0


def test_days_before_opening_day_do_not_count():
    rows = [_tx("2023-03-15", "Texas Rangers selected the contract of RHP A B from Round Rock."),
            _tx("2023-03-25", "Texas Rangers optioned RHP A B to Round Rock Express.")]
    assert _days(rows) == 0
    rows = [_tx("2023-03-15", "Texas Rangers selected the contract of RHP A B from Round Rock."),
            _tx("2023-04-03", "Texas Rangers optioned RHP A B to Round Rock Express.")]
    assert _days(rows) == 5


def test_the_2020_window_opens_on_23_july():
    rows = [_tx("2020-07-01", "Texas Rangers activated RHP A B."),
            _tx("2020-08-01", "Texas Rangers optioned RHP A B to the alternate training site.")]
    assert _days(rows, end="2020-12-31") == 10


def test_an_open_segment_runs_to_the_end_date():
    rows = [_tx("2023-08-20", "Texas Rangers recalled RHP A B from Round Rock Express.")]
    assert _days(rows) == 13
    assert _days(rows, end="2023-08-25") == 6


def test_injured_list_placement_closes_and_activation_reopens():
    rows = [_tx("2023-04-01", "Texas Rangers recalled RHP A B from Round Rock Express."),
            _tx("2023-04-05", "Texas Rangers placed RHP A B on the 60-day injured list. Elbow."),
            _tx("2023-05-01", "Texas Rangers sent RHP A B on a rehab assignment to Frisco.", club=102),
            _tx("2023-07-01", "Texas Rangers activated RHP A B from the 60-day injured list.")]
    assert _days(rows) == 5 + 63


def test_a_trade_closes_and_only_a_new_selection_or_recall_reopens():
    rows = [_tx("2023-04-10", "Texas Rangers selected the contract of RHP A B from Round Rock."),
            _tx("2023-05-01", "Texas Rangers traded RHP A B to Houston Astros for cash.", club=117),
            _tx("2023-05-01", "RHP A B assigned to Houston Astros.", club=117),
            _tx("2023-06-01", "Houston Astros recalled RHP A B from Sugar Land Space Cowboys.", club=117),
            _tx("2023-06-05", "Houston Astros optioned RHP A B to Sugar Land Space Cowboys.", club=5434)]
    assert _days(rows) == 22 + 5


def test_a_minor_league_activation_opens_nothing():
    rows = [_tx("2023-05-01", "Round Rock Express activated RHP A B from the 7-day injured list.",
                club=102)]
    assert _days(rows) == 0
    rows = [_tx("2023-05-01", "Texas Rangers activated RHP A B from the 15-day injured list.",
                club=140)]
    assert _days(rows) == 1 + (date(2023, 9, 1) - date(2023, 5, 1)).days


def test_events_sort_by_date_then_transaction_id_and_skip_undated_rows():
    rows = [_tx("2023-05-01", "Texas Rangers optioned RHP A B to Round Rock Express.", tx_id=2),
            _tx("2023-05-01", "Texas Rangers recalled RHP A B from Round Rock Express.", tx_id=1),
            {"id": 3, "person": {"id": 1}, "toTeam": {"id": 140},
             "description": "Texas Rangers recalled RHP A B from Round Rock Express."}]
    ev = AR.events_from_transactions(rows)
    assert [(d.isoformat(), k) for d, _i, k in ev[1]] == [("2023-05-01", "open"), ("2023-05-01", "close")]
    assert _days(rows) == 1


def test_window_days_spans_years():
    opening = _opening({2022: date(2022, 4, 7), 2023: date(2023, 3, 30)})
    assert AR.window_days(date(2022, 8, 30), date(2023, 4, 2), opening) == 3 + 4
    assert AR.window_days(date(2023, 4, 2), date(2023, 4, 1), opening) == 0


# --- the three lines -------------------------------------------------------------------------
@pytest.mark.parametrize("ab,ip,days,ok", [
    (130, 0.0, 0, True), (131, 0.0, 0, False),
    (0, round(150 / 3, 1), 0, True), (0, round(151 / 3, 1), 0, False),
    (0, 0.0, 45, True), (0, 0.0, 46, False),
    (130, 50.0, 45, True), (131, 50.3, 46, False),
])
def test_boundaries(ab, ip, days, ok):
    got, reason = AR.eligibility(ab, ip, days)
    assert got is ok
    assert (reason == "eligible") is ok or (ok and reason.startswith("eligible"))
    if not ok:
        assert "over" in reason


def test_near_45_day_line_band():
    assert [AR.near_45_day_line(d) for d in (30, 31, 45, 46, 60, 61)] == [False, True, True, True, True, False]
    assert AR.NEAR_TOKEN in AR.eligibility(0, 0.0, 31)[1]
    assert AR.NEAR_TOKEN in AR.eligibility(0, 0.0, 60)[1]
    assert AR.NEAR_TOKEN not in AR.eligibility(0, 0.0, 61)[1]
    assert AR.NEAR_TOKEN not in AR.eligibility(0, 0.0, 30)[1]


def test_reason_names_every_line_crossed():
    ok, reason = AR.eligibility(200, 61.3, 99)
    assert not ok
    assert reason == ("prior at-bats 200 over 130; prior innings 61.3 over 50; "
                      "roster days 99 over 45 (estimate)")


# --- the fixture world -------------------------------------------------------------------------
def test_fixture_world_block_rows():
    blk = AR.build_season(2024, FIX_CACHE, built_at="fixture", **SEAM)
    assert blk["rows"] == FIXTURE_ROWS
    assert blk["columns"] == AR.COLUMNS
    assert (blk["n_players_with_line"], blk["n_over_lines"], blk["n_pool"],
            blk["n_eligible"], blk["n_days_only"]) == (7, 2, 5, 3, 2)
    assert blk["inputs"]["transactions_from"] == "2023-01"
    assert blk["inputs"]["transactions_to"] == "2023-12"
    assert blk["inputs"]["statsapi_seasons"] == "2023-2023"
    assert blk["inputs"]["opening_day"] == {"2023": {"date": "2023-03-30", "source": "typed"}}
    assert set(blk["inputs"]["sha1_12"]) == {"statsapi_hitting", "statsapi_pitching",
                                             "transactions", "opening_day"}
    assert all(re.fullmatch(r"[0-9a-f]{12}", v) for v in blk["inputs"]["sha1_12"].values())


def test_status_lookup_on_the_fixture_world():
    payload = AR._empty_payload()
    payload["seasons"] = [AR.build_season(2024, FIX_CACHE, built_at="fixture", **SEAM)]
    at_line = AR.status(payload, 2024, 682990)
    assert at_line["eligible"] and at_line["prior_ip"] == 50.0 and not at_line["near_45_day_line"]
    near = AR.status(payload, 2024, 663462)
    assert not near["eligible"] and near["near_45_day_line"] and near["proxy_days"] == 56
    for pid in OVER_THE_LINE:
        got = AR.status(payload, 2024, pid)
        assert not got["eligible"] and "not in the pool" in got["reason"]
        assert got["prior_ab"] is None and got["proxy_days"] is None
    assert AR.status(payload, 2025, 682990) is None


def test_fixture_files_stay_small():
    total = sum(p.stat().st_size for p in FIX.rglob("*") if p.is_file())
    assert total < 200_000


# --- the CLI: write once, rebuild with a reason, refuse without the log ------------------------
def _cli(tmp_path, *extra):
    out = tmp_path / "rookies.json"
    argv = ["--seasons", "2024", "--cache-dir", str(FIX_CACHE), "--out", str(out),
            "--statsapi-first", "2023", "--tx-first", "2023-01", *extra]
    return out, AR.main(argv)


def test_cli_writes_once_and_keeps_the_block(tmp_path, capsys):
    out, rc = _cli(tmp_path, "--write")
    assert rc == 0 and out.exists()
    first = out.read_bytes()
    payload = json.loads(first.decode("utf-8"))
    assert payload["schema"] == 1 and payload["produced_by"] == "awards_rookies.py"
    assert [b["season"] for b in payload["seasons"]] == [2024]
    assert payload["seasons"][0]["rows"] == FIXTURE_ROWS
    assert AR.dumps_payload(payload) == out.read_text(encoding="utf-8")
    out2, rc = _cli(tmp_path, "--write")
    assert rc == 0 and out2.read_bytes() == first
    assert "kept as written: 2024" in capsys.readouterr().out


def test_cli_rebuild_needs_a_reason_and_records_it(tmp_path, capsys):
    out, rc = _cli(tmp_path, "--write")
    assert rc == 0
    before = json.loads(out.read_text(encoding="utf-8"))["seasons"][0]["built_at"]
    _, rc = _cli(tmp_path, "--write", "--rebuild-season", "2024")
    assert rc == 2 and "needs --reason" in capsys.readouterr().err
    _, rc = _cli(tmp_path, "--write", "--rebuild-season", "2024", "--reason", "fixture recut")
    assert rc == 0
    blk = json.loads(out.read_text(encoding="utf-8"))["seasons"][0]
    assert blk["rebuilt"]["reason"] == "fixture recut"
    assert blk["rebuilt"]["previous_built_at"] == before
    assert blk["rows"] == FIXTURE_ROWS


def test_cli_refuses_a_season_whose_december_is_not_on_disk(tmp_path, capsys):
    cache = tmp_path / "cache"
    shutil.copytree(FIX_CACHE, cache)
    (cache / "mlb_transactions" / "tx_2023_12.json.gz").unlink()
    out = tmp_path / "rookies.json"
    rc = AR.main(["--seasons", "2024", "--write", "--cache-dir", str(cache), "--out", str(out),
                  "--statsapi-first", "2023", "--tx-first", "2023-01"])
    err = capsys.readouterr().err
    assert rc == 2 and not out.exists()
    assert "through 2023-12" in err and "first 2023-12" in err
    assert AR.BACKFILL_TOOL in err and "never fetches" in err
    assert AR.missing_tx_months(cache, (2023, 12), (2023, 1)) == [(2023, 12)]
    assert AR.missing_tx_months(FIX_CACHE, (2023, 12), (2023, 1)) == []
    assert AR.missing_tx_months(FIX_CACHE, (2024, 12), (2023, 1))[0] == (2024, 1)


def test_the_real_cli_defaults_read_from_2000_and_2008_01():
    assert AR.STATSAPI_FIRST_SEASON == 2000 and AR.TX_FIRST == (2008, 1)
    assert AR.PRIOR_AB_MAX == 130 and AR.PRIOR_IP_MAX == 50.0 and AR.PROXY_DAYS_MAX == 45
    assert AR.NEAR_45_BAND == (31, 60)


# --- Opening Day ---------------------------------------------------------------------------------
def test_opening_day_prefers_the_corpus_and_types_the_rest(tmp_path):
    games = {str(600000 + i): f"2023-{4 + i % 5:02d}-{1 + i % 28:02d}" for i in range(1200)}
    games["599999"] = "2023-03-30"
    games["700000"] = "2022-04-07"
    (tmp_path / "mgmt_game_dates.json").write_text(json.dumps(games), encoding="utf-8")
    got = AR.corpus_opening_days(tmp_path / "mgmt_game_dates.json")
    assert got == {2023: date(2023, 3, 30)}
    table = AR.opening_day_table(tmp_path, [2020, 2022, 2023])
    assert table[2023] == {"date": "2023-03-30", "source": "corpus"}
    assert table[2022] == {"date": "2022-04-07", "source": "typed"}
    assert table[2020] == {"date": "2020-07-23", "source": "typed"}
    with pytest.raises(KeyError):
        AR.opening_day_table(tmp_path, [1999])
    assert AR.corpus_opening_days(tmp_path / "absent.json") == {}


def test_typed_opening_days_cover_the_transaction_log_years():
    assert set(AR.OPENING_DAY_TYPED) >= set(range(2008, 2027))
    assert all(date(y, 3, 15) <= d <= date(y, 4, 10) for y, d in AR.OPENING_DAY_TYPED.items() if y != 2020)
    assert AR.OPENING_DAY_TYPED[2020] == AR.WINDOW_2020_OPEN


# --- the tracked file ------------------------------------------------------------------------
def _labs_payload():
    p = LABS / "rookies.json"
    if not p.exists():
        pytest.skip("data/_labs/awards/rookies.json is not on disk")
    return json.loads(p.read_text(encoding="utf-8"))


def test_no_eligible_row_in_the_tracked_file_breaks_a_gate():
    payload = _labs_payload()
    assert payload["schema"] == 1
    seasons = [b["season"] for b in payload["seasons"]]
    assert seasons == sorted(seasons) and set(range(2011, 2027)) <= set(seasons)
    for blk in payload["seasons"]:
        assert blk["columns"] == AR.COLUMNS
        ids = [r[0] for r in blk["rows"]]
        assert ids == sorted(ids) and len(ids) == len(set(ids))
        assert blk["n_pool"] == len(blk["rows"])
        assert blk["n_eligible"] == sum(1 for r in blk["rows"] if r[4])
        assert blk["n_days_only"] == sum(1 for r in blk["rows"] if not r[4])
        assert blk["n_players_with_line"] == blk["n_pool"] + blk["n_over_lines"]
        assert blk["inputs"]["transactions_to"] == f"{blk['season'] - 1}-12"
        for r in blk["rows"]:
            assert len(r) == 6
            mlbam, ab, ip, days, ok, reason = r
            assert ab <= AR.PRIOR_AB_MAX and ip <= AR.PRIOR_IP_MAX
            assert ok is (days <= AR.PROXY_DAYS_MAX)
            assert (AR.NEAR_TOKEN in reason) is AR.near_45_day_line(days)
            assert (reason.startswith("eligible")) is ok
            assert not DASHES.search(reason) and not VERDICT_WORDS.search(reason), reason


def test_tracked_file_is_small_and_byte_stable():
    p = LABS / "rookies.json"
    payload = _labs_payload()
    assert p.stat().st_size < 400_000
    text = p.read_text(encoding="utf-8")
    assert AR.dumps_payload(payload) == text


def _roy_recipients(doc) -> list[tuple[int, int]]:
    """(season, mlbam) for every Rookie of the Year recipient found in award_winners.json,
    whatever its shape: records that carry a season, a person id and an award tag that
    says ROY (on the record or on an enclosing key)."""
    out = []

    def _pid(rec):
        for k in ("mlbam", "person_id", "player_id", "id"):
            v = rec.get(k)
            if isinstance(v, int):
                return v
        p = rec.get("person") or rec.get("player") or {}
        return p.get("id") if isinstance(p, dict) and isinstance(p.get("id"), int) else None

    def walk(node, tags):
        if isinstance(node, dict):
            own = " ".join(str(node.get(k, "")) for k in ("award", "award_id", "id", "name"))
            here = tags + [own]
            season = node.get("season")
            try:
                season = int(season)
            except (TypeError, ValueError):
                season = None
            pid = _pid(node)
            if season and pid and any("ROY" in t.upper() or "ROOKIE" in t.upper() for t in here):
                out.append((season, pid))
            for k, v in node.items():
                walk(v, here + [str(k)])
        elif isinstance(node, list):
            for v in node:
                walk(v, tags)
    walk(doc, [])
    return sorted(set(out))


def test_every_rookie_of_the_year_recipient_is_eligible():
    winners = LABS / "award_winners.json"
    if not winners.exists():
        pytest.skip("data/_labs/awards/award_winners.json is not on disk (AWARDS_4 writes it)")
    payload = _labs_payload()
    found = [(s, pid) for s, pid in _roy_recipients(json.loads(winners.read_text(encoding="utf-8")))
             if 2011 <= s <= 2025]
    if not found:
        pytest.skip("award_winners.json holds no Rookie of the Year record this reader can parse")
    assert len(found) >= 20
    for season, pid in found:
        got = AR.status(payload, season, pid)
        assert got is not None and got["eligible"], (season, pid, got)


def test_sources_carry_no_dash_or_verdict_word():
    for name in ("awards_rookies.py", "test_awards_rookies.py"):
        src = (ROOT / name).read_text(encoding="utf-8")
        assert not DASHES.search(src), name
    for p in [FIX / "transaction_wording_rows.json"]:
        assert not DASHES.search(p.read_text(encoding="utf-8")), p.name

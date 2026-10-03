# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The club season-line ingest's contract, offline (Part 8 lane
league_team_stats, section 8).

Nothing here touches the network: every fetch goes through the `http_get` seam
and answers with the StatsAPI responses saved by the lane's probe on
2026-09-30 (test_fixtures/team_stats/). What is pinned: the sp / rp read always
asks for limit=100 and is refused when it holds fewer than 30 clubs per code
(the default page returned 50 of 60); a refusal writes nothing and files a red;
the team-line parser; the xWinLoss parser (never xWinLossSeason); the season
identities; and the TTL rule (a complete season is fetched once, a live one
daily).
"""
from __future__ import annotations

import copy
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import mlb_team_season as MTS

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "test_fixtures" / "team_stats"


def _fix(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


HIT = _fix("teamstats_hit_2025.json")
PIT = _fix("teamstats_pit_2025.json")
SPRP = _fix("teamstats_pit_sprp_2025_l100.json")
SPRP_NOLIMIT = _fix("teamstats_pit_sprp_2025_nolimit.json")
STANDINGS = _fix("standings_2025_trim.json")


class FakeAPI:
    """The http_get seam: answers each teams/stats request from the fixtures
    and counts calls."""

    def __init__(self, sprp: dict = SPRP, hit: dict = HIT, pit: dict = PIT):
        self.calls: list[dict] = []
        self.sprp, self.hit, self.pit = sprp, hit, pit

    def __call__(self, path: str, params: dict) -> dict:
        assert path == "teams/stats"
        self.calls.append(dict(params))
        if params.get("stats") == "statSplits":
            return copy.deepcopy(self.sprp)
        return copy.deepcopy(self.hit if params["group"] == "hitting" else self.pit)


class Ledger:
    def __init__(self):
        self.rows: list[dict] = []

    def __call__(self, source, *, ok, n_rows=0, message="", import_fallback=True):
        self.rows.append({"source": source, "ok": ok, "n_rows": n_rows, "message": message})


def _ts(y, m, d, h=12) -> float:
    return datetime(y, m, d, h, tzinfo=timezone.utc).timestamp()


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------

def test_sprp_request_always_carries_limit_100():
    path, params = MTS.request_for("sprp", 2025)
    assert path == "teams/stats"
    assert params["limit"] == 100 == MTS.SPLIT_LIMIT
    assert params["sitCodes"] == "sp,rp"
    assert params["stats"] == "statSplits" and params["group"] == "pitching"
    assert params["sportIds"] == 1 and params["gameType"] == "R" and params["season"] == 2025


def test_season_line_requests():
    for kind, group in (("hit", "hitting"), ("pit", "pitching")):
        path, params = MTS.request_for(kind, 2025)
        assert path == "teams/stats"
        assert params == {"season": 2025, "sportIds": 1, "gameType": "R",
                          "group": group, "stats": "season"}
    with pytest.raises(ValueError):
        MTS.request_for("fielding", 2025)


# --------------------------------------------------------------------------
# Validation and refusals
# --------------------------------------------------------------------------

def test_season_lines_parse_thirty_clubs():
    for blob, kind in ((HIT, "hit"), (PIT, "pit")):
        rows = MTS.parse_response(blob, kind, 2025)
        assert len(rows) == 30
        assert len({r["club"] for r in rows}) == 30
        assert all(isinstance(r["stat"], dict) for r in rows)


def test_sprp_with_limit_parses_thirty_per_code():
    rows = MTS.parse_response(SPRP, "sprp", 2025)
    assert len(rows) == 60
    for code in ("sp", "rp"):
        assert len({r["club"] for r in rows if r["code"] == code}) == 30


def test_sprp_default_page_is_refused():
    """The saved default read: totalSplits 60, 50 rows on the page."""
    block = SPRP_NOLIMIT["stats"][0]
    assert block["totalSplits"] == 60 and len(block["splits"]) == 50
    with pytest.raises(MTS.Refused, match="50 of its 60"):
        MTS.parse_response(SPRP_NOLIMIT, "sprp", 2025)


def test_sprp_fewer_than_thirty_clubs_per_code_is_refused():
    blob = copy.deepcopy(SPRP)
    block = blob["stats"][0]
    drop = next(i for i, s in enumerate(block["splits"]) if s["split"]["code"] == "rp")
    del block["splits"][drop]
    block["totalSplits"] = len(block["splits"])        # a page that agrees with itself
    with pytest.raises(MTS.Refused, match="29 clubs for code rp"):
        MTS.parse_response(blob, "sprp", 2025)


def test_season_line_short_of_thirty_is_refused():
    blob = copy.deepcopy(HIT)
    blob["stats"][0]["splits"].pop()
    blob["stats"][0]["totalSplits"] = 29
    with pytest.raises(MTS.Refused, match="29 clubs"):
        MTS.parse_response(blob, "hit", 2025)


@pytest.mark.parametrize("mutate,match", [
    (lambda b: b["stats"][0]["splits"][3].__setitem__("season", "2024"), "season 2024"),
    (lambda b: b["stats"][0]["group"].__setitem__("displayName", "pitching"), "expected hitting"),
    (lambda b: b["stats"][0]["splits"][0]["stat"].pop("plateAppearances"), "missing"),
    (lambda b: b.__setitem__("stats", []), "no stats block"),
])
def test_shape_changes_are_refused(mutate, match):
    blob = copy.deepcopy(HIT)
    mutate(blob)
    with pytest.raises(MTS.Refused, match=match):
        MTS.parse_response(blob, "hit", 2025)


# --------------------------------------------------------------------------
# The team-line parser
# --------------------------------------------------------------------------

def test_team_line_parser_hitting():
    sp = next(s for s in HIT["stats"][0]["splits"] if s["team"]["id"] == 141)
    line = MTS.parse_team_line(sp["stat"], "hit")
    st = sp["stat"]
    assert line["pa"] == st["plateAppearances"] == 6180
    assert line["pitches"] == st["numberOfPitches"]
    assert line["g"] == 162
    assert line["hr"] == st["homeRuns"] and line["so"] == st["strikeOuts"]
    assert line["sf"] == st["sacFlies"] and line["ibb"] == st["intentionalWalks"]
    assert set(line) == set(MTS.HIT_FIELDS)


def test_team_line_parser_pitching_and_role_lines():
    sp = next(s for s in PIT["stats"][0]["splits"] if s["team"]["id"] == 140)
    line = MTS.parse_team_line(sp["stat"], "pit")
    assert line["outs"] == 4329 and line["ip"] == pytest.approx(1443.0)
    assert line["bf"] == 5942 and line["pitches"] == 22907 and line["gs"] == 162
    assert line["hbp"] == sp["stat"]["hitBatsmen"]
    role = {s["split"]["code"]: MTS.parse_team_line(s["stat"], "pit")
            for s in SPRP["stats"][0]["splits"] if s["team"]["id"] == 140}
    assert role["sp"]["gs"] == 162 and role["rp"]["gs"] == 0
    assert role["sp"]["outs"] + role["rp"]["outs"] == line["outs"]
    assert role["rp"]["ir"] is not None                 # inherited runners ride the role line
    assert MTS.parse_team_line({}, "pit")["ip"] is None
    with pytest.raises(ValueError):
        MTS.parse_team_line({}, "field")


# --------------------------------------------------------------------------
# Identities
# --------------------------------------------------------------------------

def _rows():
    return {"hit": MTS.parse_response(copy.deepcopy(HIT), "hit", 2025),
            "pit": MTS.parse_response(copy.deepcopy(PIT), "pit", 2025),
            "sprp": MTS.parse_response(copy.deepcopy(SPRP), "sprp", 2025)}


def test_identities_hold_on_the_2025_reads():
    rows = _rows()
    assert MTS.check_identities(rows, complete=True) == []
    pa = sum(r["stat"]["plateAppearances"] for r in rows["hit"])
    bf = sum(r["stat"]["battersFaced"] for r in rows["pit"])
    assert pa == bf == 182926


def test_identity_break_is_exact_on_complete_and_tolerant_live():
    rows = _rows()
    rows["sprp"][0]["stat"]["outs"] += 1
    assert any("sp + rp outs" in p for p in MTS.check_identities(rows, complete=True))
    assert MTS.check_identities(rows, complete=False) == []
    rows["sprp"][0]["stat"]["outs"] += 100                # far past 0.1 percent
    assert MTS.check_identities(rows, complete=False)


# --------------------------------------------------------------------------
# Load: write, refuse, TTL
# --------------------------------------------------------------------------

def test_load_writes_three_files_and_records_ok(tmp_path):
    api, led = FakeAPI(), Ledger()
    docs = MTS.load(2025, cache_dir=tmp_path, today=date(2026, 10, 3),
                    now=_ts(2026, 10, 3), http_get=api, record=led)
    assert len(api.calls) == 3
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2025_hit.json", "2025_pit.json", "2025_sprp.json"]
    assert all(docs[k]["complete"] for k in MTS.KINDS)
    assert "limit=100" in docs["sprp"]["url"]
    assert led.rows == [{"source": "mlb_team_season", "ok": True, "n_rows": 120,
                         "message": "2025 hit+pit+sprp fetched (complete)"}]
    lines = MTS.team_lines(2025, tmp_path)
    assert {k: len(v) for k, v in lines.items()} == {"hit": 30, "pit": 30, "sp": 30, "rp": 30}


def test_refusal_writes_nothing_and_files_a_red(tmp_path):
    good = MTS.load(2025, cache_dir=tmp_path, today=date(2026, 10, 3), now=_ts(2026, 10, 3),
                    http_get=FakeAPI(), record=Ledger())
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    led = Ledger()
    with pytest.raises(MTS.Refused):
        MTS.load(2025, force=True, cache_dir=tmp_path, today=date(2026, 10, 3),
                 now=_ts(2026, 10, 4), http_get=FakeAPI(sprp=SPRP_NOLIMIT), record=led)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    assert [r["ok"] for r in led.rows] == [False] and "50 of its 60" in led.rows[0]["message"]
    assert good["sprp"]["n_rows"] == 60


def test_refusal_on_a_cold_cache_leaves_it_empty(tmp_path):
    def broken(path, params):
        raise OSError("connection reset")
    led = Ledger()
    with pytest.raises(MTS.Refused, match="fetch failed"):
        MTS.load(2025, cache_dir=tmp_path, today=date(2026, 10, 3), http_get=broken, record=led)
    assert list(tmp_path.iterdir()) == []
    assert led.rows[0]["ok"] is False


def test_ttl_rule_season_complete_from_november_first():
    assert MTS.season_complete(2025, date(2026, 10, 3))
    assert not MTS.season_complete(2026, date(2026, 10, 3))
    assert not MTS.season_complete(2026, date(2026, 10, 31))
    assert MTS.season_complete(2026, date(2026, 11, 1))


def test_ttl_complete_season_is_never_refetched(tmp_path):
    MTS.load(2025, cache_dir=tmp_path, today=date(2026, 10, 3), now=_ts(2026, 10, 3),
             http_get=FakeAPI(), record=Ledger())
    api, led = FakeAPI(), Ledger()
    MTS.load(2025, cache_dir=tmp_path, today=date(2031, 1, 1), now=_ts(2031, 1, 1),
             http_get=api, record=led)
    assert api.calls == [] and led.rows == []
    MTS.load(2025, force=True, cache_dir=tmp_path, today=date(2031, 1, 1),
             now=_ts(2031, 1, 1), http_get=api, record=led)
    assert len(api.calls) == 3


def test_ttl_live_season_refetches_daily(tmp_path):
    live = date(2025, 9, 1)                       # 2025 is the live season on this date
    t0 = _ts(2025, 9, 1, 8)
    docs = MTS.load(2025, cache_dir=tmp_path, today=live, now=t0,
                    http_get=FakeAPI(), record=Ledger())
    assert not any(docs[k]["complete"] for k in MTS.KINDS)
    api = FakeAPI()
    MTS.load(2025, cache_dir=tmp_path, today=live, now=t0 + 23 * 3600, http_get=api, record=Ledger())
    assert api.calls == []                         # a same-day rerun reads the cache
    MTS.load(2025, cache_dir=tmp_path, today=live, now=t0 + 25 * 3600, http_get=api, record=Ledger())
    assert len(api.calls) == 3                     # the next day's run refetches


def test_readers_never_fetch(tmp_path):
    with pytest.raises(MTS.NotCached):
        MTS.team_lines(2025, tmp_path)
    with pytest.raises(MTS.NotCached):
        MTS.expected_records(2025, standings_dir=tmp_path)


# --------------------------------------------------------------------------
# The xWinLoss parser
# --------------------------------------------------------------------------

def _team_records(raw):
    for rec in raw["records"]:
        yield from rec["teamRecords"]


def test_xwinloss_parser_reads_xwinloss_and_sums_to_games():
    out = MTS.parse_expected_records(STANDINGS)
    assert len(out) == 30
    for row in out.values():
        assert row["xw"] + row["xl"] == row["g"]
    assert out["TOR"] == {"team_id": 141, "g": 162, "w": 94, "l": 68, "xw": 88, "xl": 74}


def test_xwinloss_parser_never_reads_xwinlossseason():
    raw = copy.deepcopy(STANDINGS)
    for tr in _team_records(raw):
        for e in tr["records"]["expectedRecords"]:
            if e["type"] == "xWinLossSeason":
                e["wins"], e["losses"] = 1, 1
    assert MTS.parse_expected_records(raw) == MTS.parse_expected_records(STANDINGS)
    for tr in _team_records(raw):
        tr["records"]["expectedRecords"] = [e for e in tr["records"]["expectedRecords"]
                                            if e["type"] != "xWinLoss"]
        break
    with pytest.raises(MTS.Refused, match="no xWinLoss"):
        MTS.parse_expected_records(raw)


def test_xwinloss_that_misses_games_played_is_refused():
    raw = copy.deepcopy(STANDINGS)
    tr = next(_team_records(raw))
    x = next(e for e in tr["records"]["expectedRecords"] if e["type"] == "xWinLoss")
    x["wins"] += 1
    with pytest.raises(MTS.Refused, match="does not sum"):
        MTS.parse_expected_records(raw)


def test_xwinloss_short_of_thirty_clubs_is_refused():
    raw = copy.deepcopy(STANDINGS)
    raw["records"][0]["teamRecords"].pop()
    with pytest.raises(MTS.Refused, match="29 clubs"):
        MTS.parse_expected_records(raw)


def test_expected_records_reads_the_standings_cache(tmp_path):
    (tmp_path / "statsapi_standings_2025.json").write_text(json.dumps(STANDINGS), encoding="utf-8")
    assert MTS.expected_records(2025, standings_dir=tmp_path) == MTS.parse_expected_records(STANDINGS)

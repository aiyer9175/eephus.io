# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/award_winners_ingest.py and its file (AWARDS_4_WINNERS_INGEST; AWARDS_PLAN 4.1
'Files', 4.11 'Past seasons and the writers', 6 'Invariants and tests' row I6).

No test touches the network: an autouse fixture refuses every socket, the parser runs on
the saved StatsAPI samples in data/sources/samples/, and ingest() takes a fake fetch.
The last tests read the tracked data/_labs/awards/award_winners.json: every person id
joins an MLBAM id (a player season in data/ewar.json) or, for the Manager award, a club.
"""
from __future__ import annotations

import copy
import json
import re
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import award_winners_ingest as W  # noqa: E402
import awards_export as E  # noqa: E402

SAMPLES = ROOT / "data" / "sources" / "samples"
WINNERS = ROOT / "data" / "_labs" / "awards" / "award_winners.json"
DASHES = re.compile("[" + chr(0x2013) + chr(0x2014) + "]")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("an award winners test opened a socket")
    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


def _sample(name):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def _responses(seasons=(2011, 2012)):
    """Eight recipient responses in the sample's own field layout, one row a season."""
    base = _sample("awards_roy_recipients_05.json")
    proto = base["awards"][0]
    out = {}
    for i, aid in enumerate(W.AWARD_IDS):
        rows = []
        for S in seasons:
            r = copy.deepcopy(proto)
            r["id"], r["season"], r["date"] = aid, str(S), f"{S}-11-15"
            r["player"]["id"] = 600000 + 100 * i + (S - 2000)
            r["player"]["nameFirstLast"] = f"Player {aid} {S}"
            r["team"]["id"] = 108 + i
            if i % 2:
                r.pop("votes", None)
            rows.append(r)
        out[aid] = {"copyright": base["copyright"], "awards": rows}
    return out


class _Fetch:
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def __call__(self, aid):
        self.calls.append(aid)
        return self.responses[aid]


def test_the_parser_reads_the_saved_recipients_sample():
    doc = _sample("awards_roy_recipients_05.json")
    got = W.parse_recipients("MLBROY", doc, 1947, 1948)
    assert set(got) == {1947, 1948}
    assert got[1947] == {"person_id": 121314, "name": "Jackie Robinson", "team_id": 119,
                         "team_code": "LAD", "date": "1947-11-01", "votes": 129}
    assert got[1948]["person_id"] == 113052 and got[1948]["team_code"] == "ATL"
    assert W.parse_recipients("MLBROY", doc, 1948, 1948).keys() == {1948}
    assert W.parse_recipients("MLBROY", doc, 2011, 2025) == {}
    with pytest.raises(W.IngestRefusal):
        W.parse_recipients("ALROY", doc, 1947, 1948)


def test_votes_ride_only_where_the_feed_has_them():
    doc = _sample("awards_roy_recipients_05.json")
    doc["awards"][0].pop("votes")
    got = W.parse_recipients("MLBROY", doc, 1947, 1948)
    assert "votes" not in got[1948] and got[1947]["votes"] == 129


def test_a_shared_award_is_refused():
    doc = _sample("awards_roy_recipients_05.json")
    doc["awards"][1]["season"] = doc["awards"][0]["season"]
    with pytest.raises(W.IngestRefusal):
        W.parse_recipients("MLBROY", doc, 1940, 1950)


def test_the_award_ids_are_the_listed_ones_and_the_exporters():
    listed = {a["id"]: a for a in _sample("awards_list_04.json")["awards"]}
    league = {103: "AL", 104: "NL"}
    for aid, (award, lg) in W.AWARD_IDS.items():
        assert aid in listed and league[listed[aid]["league"]["id"]] == lg
    assert W.AWARD_IDS == E.STATSAPI_AWARD_IDS
    assert len(W.AWARD_IDS) == 8


def test_ingest_writes_every_season_and_the_copyright_verbatim(tmp_path):
    out = tmp_path / "award_winners.json"
    fetch = _Fetch(_responses())
    doc = W.ingest(2011, 2012, out=out, fetch=fetch, pause=0, now="2026-10-08T00:00:00+00:00",
                   log=lambda *_a: None)
    assert fetch.calls == list(W.AWARD_IDS)
    assert list(doc["seasons"]) == ["2011", "2012"]
    assert all(set(v) == set(W.AWARD_IDS) for v in doc["seasons"].values())
    assert doc["copyright"] == _sample("awards_roy_recipients_05.json")["copyright"]
    assert doc["fetch_log"] == [{"fetched_at": "2026-10-08T00:00:00+00:00", "seasons": [2011, 2012], "calls": 8}]
    assert json.loads(out.read_text(encoding="utf-8")) == doc
    assert out.read_bytes().endswith(b"\n") and b"\r\n" not in out.read_bytes()


def test_a_closed_season_is_never_refetched_or_rewritten(tmp_path):
    out = tmp_path / "award_winners.json"
    W.ingest(2011, 2012, out=out, fetch=_Fetch(_responses()), pause=0, log=lambda *_a: None)
    before = out.read_bytes()
    for first, last in ((2011, 2011), (2012, 2013), (2010, 2011)):
        fetch = _Fetch(_responses((2010, 2011, 2012, 2013)))
        with pytest.raises(W.IngestRefusal):
            W.ingest(first, last, out=out, fetch=fetch, pause=0, log=lambda *_a: None)
        assert fetch.calls == [] and out.read_bytes() == before


def test_the_command_line_refuses_a_closed_season_in_the_tracked_file():
    _tracked()
    before = WINNERS.read_bytes()
    assert W.main(["--first", "2025", "--last", "2025"]) == 1
    assert WINNERS.read_bytes() == before


def test_a_later_season_is_added_and_the_closed_ones_keep_their_records(tmp_path):
    out = tmp_path / "award_winners.json"
    W.ingest(2011, 2012, out=out, fetch=_Fetch(_responses()), pause=0, log=lambda *_a: None)
    old = json.loads(out.read_text(encoding="utf-8"))
    doc = W.ingest(2013, 2013, out=out, fetch=_Fetch(_responses((2011, 2012, 2013))), pause=0,
                   now="2026-11-20T00:00:00+00:00", log=lambda *_a: None)
    assert list(doc["seasons"]) == ["2011", "2012", "2013"]
    assert {k: doc["seasons"][k] for k in ("2011", "2012")} == old["seasons"]
    assert [e["seasons"] for e in doc["fetch_log"]] == [[2011, 2012], [2013, 2013]]


def test_an_incomplete_season_writes_nothing(tmp_path):
    out = tmp_path / "award_winners.json"
    resp = _responses((2011, 2012))
    resp["NLMOY"]["awards"] = [r for r in resp["NLMOY"]["awards"] if r["season"] != "2012"]
    with pytest.raises(W.IngestRefusal, match="2012 lacks NLMOY"):
        W.ingest(2011, 2012, out=out, fetch=_Fetch(resp), pause=0, log=lambda *_a: None)
    assert not out.exists()


def _tracked():
    if not WINNERS.exists():
        pytest.skip("data/_labs/awards/award_winners.json is not on disk")
    return json.loads(WINNERS.read_text(encoding="utf-8"))


def test_the_tracked_file_holds_2011_to_2025_for_all_eight_awards():
    doc = _tracked()
    assert [int(s) for s in doc["seasons"]] == list(range(2011, 2026))
    assert all(list(v) == list(W.AWARD_IDS) for v in doc["seasons"].values())
    assert doc["source"]["id"] == "awards_statsapi" and doc["copyright"].startswith("Copyright")
    assert WINNERS.stat().st_size < 60_000
    rows = E.winner_rows(doc)
    assert len(rows) == 15 * 8 and all(r["winner"] for r in rows)


def test_every_person_id_joins_an_mlbam_id_or_a_club():
    doc = _tracked()
    ewar = json.loads((ROOT / "data" / "ewar.json").read_text(encoding="utf-8"))["players"]
    clubs = {W.team_code(t) for t in range(108, 159)} - {None}
    assert len(clubs) == 30
    for S, by_id in doc["seasons"].items():
        for aid, rec in by_id.items():
            assert isinstance(rec["person_id"], int) and rec["name"]
            if W.AWARD_IDS[aid][0] == "MOY":
                assert rec["team_code"] in clubs, (S, aid, rec)
                assert rec["team_code"] == W.team_code(rec["team_id"])
            else:
                assert S in (ewar.get(str(rec["person_id"])) or {}), (S, aid, rec["name"])


def test_sources_carry_no_dash():
    for p in (ROOT / "tools" / "award_winners_ingest.py", Path(__file__)):
        assert not DASHES.search(p.read_text(encoding="utf-8")), p.name

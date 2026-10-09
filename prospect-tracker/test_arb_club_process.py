# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Club arbitration process, the parser part (task Q9_17, plan row FAA-3).

The MLB Trade Rumors tracker groups its entries under club headings. The
ingest records the heading on every tracker row, and the attribution rule is
the heading the tracker lists the player under on exchange day, never the
season-end club in arb_history (Tarik Skubal's 2026 case is a Detroit case
although arb_history credits his 2026 award to LAD).

The dated re-capture (2026-10-09, six requests) adds the filed figures of the
57 exchanged cases and a hearing field, and the Cot's Contracts block adds the
2011-2023 backfill; none of it adds or removes a ledger entry.

No test here touches the network: every socket connect raises. Tests that read
the gitignored .cache/mlbtr pages skip when the cache is absent; the committed
lab file data/_labs/arb_ledger.json carries the same facts and is always read.
"""
from __future__ import annotations

import importlib.util
import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
_SPEC = importlib.util.spec_from_file_location(
    "ingest_arbitration_ledger", ROOT / "tools" / "ingest_arbitration_ledger.py")
ingest = importlib.util.module_from_spec(_SPEC)
sys.modules["ingest_arbitration_ledger"] = ingest
_SPEC.loader.exec_module(ingest)

LEDGER = ROOT / "data" / "_labs" / "arb_ledger.json"
CACHED = {y: ROOT / ".cache" / "mlbtr" / f"{y}_01_{y}-arbitration-tracker.html"
          for y in (2024, 2025, 2026)}
# Exchanged cases per winter on the cached exchange-day pages, as the lane
# design counted them (finance_to_fa_arb.md section 1.4) and the filing-figure
# posts' own titles state them (22, 17 and 18 players).
EXCHANGED = {2024: 22, 2025: 17, 2026: 18}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("test_arb_club_process must not touch the network")
    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


def _li(name: str, bref: str, svc: str, tail: str) -> str:
    return (f'<li><a href="https://www.baseball-reference.com/players/'
            f'{bref[0]}/{bref}.shtml">{name}</a> ({svc}): {tail}</li>')


FIXTURE = (
    "<p>Today is the deadline to exchange figures in arbitration.</p>"
    "<p><strong>Tigers</strong></p><ul>"
    + _li("Tarik Skubal", "skubata01", "5.114",
          "No agreement reached, likely heading to a hearing")
    + _li("Riley Greene", "greenri03", "3.000", "$4.5MM agreement today")
    + "</ul><p><strong>White Sox</strong></p><ul>"
    + _li("Mike Clevinger", "clevimi01", "6.100", "$1MM agreement today")
    + "</ul><p>Notes</p><ul>"
    + _li("Loose Entry", "looseen01", "3.050", "$2MM agreement today")
    + "</ul>")


def _rows(html=FIXTURE, kind="tracker", cy=2026):
    return {r["bbref_id"] or r["player_name"]: r
            for r in ingest.parse_post(html, class_year=cy, kind=kind,
                                       source_url="test")}


def _ledger() -> dict:
    return json.loads(LEDGER.read_text("utf-8"))


# --------------------------------------------------------------------------- #
# The parser, on a fixture
# --------------------------------------------------------------------------- #

def test_every_tracker_row_carries_its_heading_and_code():
    rows = _rows()
    assert (rows["skubata01"]["club_heading"], rows["skubata01"]["club"]) == ("Tigers", "DET")
    assert rows["greenri03"]["club"] == "DET"
    assert (rows["clevimi01"]["club_heading"], rows["clevimi01"]["club"]) == ("White Sox", "CHW")


def test_an_entry_outside_a_club_list_is_credited_to_no_club():
    # "Notes" is not a club; the nearest club heading above it is White Sox,
    # and crediting the entry there is the error the strict rule prevents.
    assert _rows()["looseen01"]["club"] is None


def test_projection_rows_carry_no_club_field():
    # A projection post is the Swartz comparator; its rows stay byte-identical.
    assert all("club" not in r for r in _rows(kind="projection").values())


def test_heading_codes_agree_with_canonical_org():
    import trades
    for name, code in ingest.TRACKER_CLUB_CODES.items():
        if name == "D-backs":
            continue  # canonical_org passes this short form through unchanged
        assert trades.canonical_org(name) == code, name


# --------------------------------------------------------------------------- #
# The committed lab file
# --------------------------------------------------------------------------- #

def test_ledger_tracker_sources_carry_thirty_headings_each():
    trackers = {s["class_year"]: s for s in _ledger()["sources"].values()
                if s["kind"] == "tracker"}
    assert sorted(trackers) == [2024, 2025, 2026]
    for cy, s in trackers.items():
        assert s["club_headings"] == 30, cy
        assert s["n_entries_without_club"] == 0, cy


def test_ledger_exchanged_counts_by_winter():
    ent = [e for e in _ledger()["entries"] if e["kind"] == "tracker"]
    got = {cy: sum(1 for e in ent if e["class_year"] == cy
                   and e["outcome"] == "exchanged") for cy in EXCHANGED}
    assert got == EXCHANGED


def test_every_ledger_tracker_row_has_a_club_and_no_projection_row_does():
    for e in _ledger()["entries"]:
        if e["kind"] == "tracker":
            assert e["club"] in set(ingest.TRACKER_CLUB_CODES.values()), e["player_name"]
        else:
            assert "club" not in e


def test_skubal_2026_is_a_detroit_case():
    rows = [e for e in _ledger()["entries"]
            if e["kind"] == "tracker" and e.get("bbref_id") == "skubata01"
            and e["class_year"] == 2026]
    assert len(rows) == 1
    assert rows[0]["club"] == "DET" and rows[0]["club_heading"] == "Tigers"
    assert rows[0]["outcome"] == "exchanged"


# --------------------------------------------------------------------------- #
# The cached exchange-day pages (skip without the gitignored cache)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("cy", sorted(CACHED))
def test_cached_page_headings_and_exchanged(cy):
    p = CACHED[cy]
    if not p.exists():
        pytest.skip(f"{p.name} not cached on this machine")
    from bs4 import BeautifulSoup
    html = p.read_text("utf-8", errors="ignore")
    assert len(ingest.club_headings(BeautifulSoup(html, "html.parser"))) == 30
    rows = ingest.parse_post(html, class_year=cy, kind="tracker", source_url="test")
    assert sum(1 for r in rows if r["outcome"] == "exchanged") == EXCHANGED[cy]
    assert all(r["club"] for r in rows)
    if cy == 2026:
        sk = [r for r in rows if r["bbref_id"] == "skubata01"]
        assert [r["club"] for r in sk] == ["DET"]


# --------------------------------------------------------------------------- #
# Hearing lines (none fires on any capture so far; the classes are pinned on a
# fixture so the February capture's lines classify when they arrive)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text, outcome, result", [
    ("No agreement reached, likely heading to a hearing", "exchanged", None),
    ("No agreement reached, likely heading to hearing. Update: won his hearing",
     "hearing_won", "player_won"),
    ("Did not reach agreement. Update: lost his arbitration hearing",
     "hearing_lost", "club_won"),
    ("Exchanged figures; the Tigers won the hearing", "hearing_won", "club_won"),
    ("Filed at $2MM, team filed at $1.5MM. Team lost the hearing",
     "hearing_lost", "player_won"),
    ("$4.15MM agreement today", "agreed", None),
])
def test_hearing_lines_classify(text, outcome, result):
    assert ingest._classify(text) == outcome
    assert ingest.hearing_result(text) == result


# --------------------------------------------------------------------------- #
# Filing-figure posts, both layouts
# --------------------------------------------------------------------------- #

FILING_2026 = (
    '<div class="entry-content"><p>Tigers</p><ul><li><strong>'
    '<a href="https://www.baseball-reference.com/players/s/skubata01.shtml">'
    'Tarik Skubal</a></strong> (5.114): Filed at $32MM, team filed at $19MM</li>'
    '</ul><p>Mariners</p><ul><li><strong><a href="https://www.baseball-reference'
    '.com/search/search.fcgi?pid=millebr04,miller005bry&amp;search=Bryce+Miller">'
    'Bryce Miller</a></strong> (2.153): Filed at $2.625MM, team filed at $2.25MM'
    '</li></ul></div>')
FILING_2024 = (
    '<div class="entry-content"><ul><li><strong><a href="https://www.baseball-'
    'reference.com/players/w/wardta01.shtml">Taylor Ward</a></strong>: $4.8MM in '
    'desired salary. <strong>Angels </strong>offered $4.3MM</li><li><strong>'
    '<a href="https://www.baseball-reference.com/players/g/guerrvl02.shtml">'
    'Vladimir Guerrero Jr.</a></strong>: $19.9MM. Blue Jays $18.05MM</li>'
    '<li><strong><a href="https://www.baseball-reference.com/players/m/mizeca01'
    '.shtml">Casey Mize</a></strong>: $840K. <strong>Tigers</strong> $815K</li>'
    '</ul></div>')


def test_filing_post_2025_2026_layout():
    rows = {r["player_name"]: r for r in ingest.parse_filing_post(
        FILING_2026, class_year=2026, source_url="test")}
    sk = rows["Tarik Skubal"]
    assert (sk["bbref_id"], sk["club"], sk["service_time"]) == ("skubata01", "DET", "5.114")
    assert (sk["player_usd"], sk["club_usd"]) == (32_000_000, 19_000_000)
    bm = rows["Bryce Miller"]
    assert bm["bbref_id"] is None and bm["club"] == "SEA"
    assert (bm["player_usd"], bm["club_usd"]) == (2_625_000, 2_250_000)


def test_filing_post_2024_layout():
    rows = {r["player_name"]: r for r in ingest.parse_filing_post(
        FILING_2024, class_year=2024, source_url="test")}
    assert rows["Taylor Ward"]["club"] == "LAA"
    assert (rows["Taylor Ward"]["player_usd"], rows["Taylor Ward"]["club_usd"]) == (
        4_800_000, 4_300_000)
    # The club in plain text between the two figures.
    assert rows["Vladimir Guerrero Jr."]["club"] == "TOR"
    assert (rows["Casey Mize"]["club"], rows["Casey Mize"]["club_usd"]) == ("DET", 815_000)
    assert all(r["service_time"] is None for r in rows.values())


def _entry(cy, bref, name, outcome, text, club):
    return {"class_year": cy, "bbref_id": bref, "player_name": name,
            "kind": "tracker", "outcome": outcome, "text": text, "club": club,
            "settled_usd": None, "figure_usd": None}


def test_apply_recaptures_adds_fields_and_never_rows():
    entries = [
        _entry(2026, "skubata01", "Tarik Skubal", "exchanged",
               "No agreement reached, likely heading to a hearing", "DET"),
        _entry(2026, None, "Bryce Miller", "exchanged",
               "No agreement reached, likely headed to hearing", "SEA"),
        {"class_year": 2026, "bbref_id": "skubata01", "kind": "projection",
         "projected_usd": 1},
    ]
    before = json.loads(json.dumps(entries))
    tracker_html = (
        "<p><strong>Tigers</strong></p><ul>"
        + _li("Tarik Skubal", "skubata01", "5.114",
              "No agreement reached, likely heading to a hearing. Update: won his hearing")
        + "</ul>")
    cap = {"date": "2027-02-20", "receipts": {"aborted": None}, "pages": [
        {"url": "u1", "class_year": 2026, "kind": "tracker", "html": tracker_html,
         "sha1_bytes": "x", "page_modified": None,
         "rows": ingest.parse_post(tracker_html, class_year=2026, kind="tracker",
                                   source_url="u1")},
        {"url": "u2", "class_year": 2026, "kind": "filing", "html": "",
         "sha1_bytes": "y", "page_modified": None,
         "rows": ingest.parse_filing_post(FILING_2026, class_year=2026,
                                          source_url="u2")}]}
    block = ingest.apply_recaptures(entries, [cap])
    assert len(entries) == 3
    for old, new in zip(before, entries):
        assert {k: new[k] for k in old} == old  # no existing field moves
    sk, bm, proj = entries
    assert sk["hearing"]["result"] == "player_won" and sk["hearing"]["capture"] == "2027-02-20"
    assert sk["recaptured"] == {"on": "2027-02-20", "outcome": "hearing_won", "club": "DET"}
    assert sk["filing"]["player_usd"] == 32_000_000 and sk["filing"]["club"] == "DET"
    assert bm["hearing"] is None and bm["filing"]["club_usd"] == 2_250_000
    assert "hearing" not in proj and "filing" not in proj
    src = block["2027-02-20"]["sources"]
    assert src["u1"]["n_hearing_lines"] == 1 and src["u1"]["n_outcome_changed"] == 1
    assert src["u2"]["n_joined"] == 2 and src["u2"]["unjoined"] == []


# --------------------------------------------------------------------------- #
# The re-capture command: one dated key, six requests, circuit breaker
# --------------------------------------------------------------------------- #

def test_recapture_spends_six_requests_and_refuses_a_second_run(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "RECAPTURE_DIR", tmp_path)
    calls = []

    def fake_fetch(url, *, force=False, first=False, dest=None):
        calls.append((url, first))
        p = dest / ingest._slug(url)
        p.write_bytes(b"<html></html>")
        return p

    monkeypatch.setattr(ingest, "fetch_one", fake_fetch)
    assert ingest.cmd_recapture("2027-01-08", 6) == 0
    assert [u for u, _ in calls] == list(ingest.RECAPTURE_URLS)
    assert [f for _, f in calls] == [True] + [False] * 5  # delay after the first
    rec = json.loads((tmp_path / "2027-01-08" / "receipts.json").read_text("utf-8"))
    assert rec["aborted"] is None and len(rec["requests"]) == 6
    assert all(r["status"] == 200 and r["sha1_bytes"] for r in rec["requests"])
    # One capture per dated key, and never more URLs than the request budget.
    assert ingest.cmd_recapture("2027-01-08", 6) == 2
    assert ingest.cmd_recapture("2027-01-09", 5) == 2
    assert len(calls) == 6


def test_recapture_circuit_breaker_stops_on_the_first_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "RECAPTURE_DIR", tmp_path)
    calls = []

    def fake_fetch(url, *, force=False, first=False, dest=None):
        calls.append(url)
        if len(calls) == 2:
            raise ingest.DeadURL("HTTP 404")
        p = dest / ingest._slug(url)
        p.write_bytes(b"x")
        return p

    monkeypatch.setattr(ingest, "fetch_one", fake_fetch)
    assert ingest.cmd_recapture("2027-02-20", 6) == 1
    assert len(calls) == 2
    rec = json.loads((tmp_path / "2027-02-20" / "receipts.json").read_text("utf-8"))
    assert rec["aborted"] and rec["requests"][-1]["status"] is None


# --------------------------------------------------------------------------- #
# The committed lab file: re-capture and backfill blocks
# --------------------------------------------------------------------------- #

def test_ledger_recapture_block_is_six_requests_unaborted():
    rc = _ledger()["recaptures"]["2026-10-09"]
    assert rc["aborted"] is None
    assert sorted(rc["sources"]) == sorted(ingest.RECAPTURE_URLS)
    kinds = sorted((s["class_year"], s["kind"]) for s in rc["sources"].values())
    assert kinds == [(y, k) for y in (2024, 2025, 2026) for k in ("filing", "tracker")]
    for s in rc["sources"].values():
        if s["kind"] == "tracker":
            assert s["club_headings"] == 30 and s["n_club_changed"] == 0
        else:
            assert s["n_joined"] == EXCHANGED[s["class_year"]] and s["unjoined"] == []
            assert s["n_club_differs_from_tracker"] == 0


def test_every_exchanged_case_carries_its_filed_figures():
    for e in _ledger()["entries"]:
        if e["kind"] != "tracker":
            continue
        assert "hearing" in e
        h = e["hearing"]
        assert h is None or h["result"] in ("player_won", "club_won")
        if e["outcome"] == "exchanged":
            f = e["filing"]
            assert f["club"] == e["club"], e["player_name"]
            assert f["player_usd"] > f["club_usd"] > 0, e["player_name"]
        else:
            assert "filing" not in e


def test_skubal_2026_filing_reads_detroit():
    e = [e for e in _ledger()["entries"] if e["kind"] == "tracker"
         and e.get("bbref_id") == "skubata01" and e["class_year"] == 2026][0]
    assert (e["filing"]["club"], e["filing"]["player_usd"], e["filing"]["club_usd"]) == (
        "DET", 32_000_000, 19_000_000)


def test_cots_backfill_block_cites_the_capture():
    cb = _ledger()["cots_backfill"]
    assert cb["available"] is True and cb["window"] == [2011, 2023]
    assert cb["attribution"] == "Cot's Contracts (Baseball Prospectus)"
    assert len(cb["receipts"]) == 30
    assert all(r["sha256"] and r["fetched_at"] and r["url"] for r in cb["receipts"])
    assert "user_agent" not in cb["capture"]
    assert cb["n_cases"] == len(cb["rows"]) > 0
    sheets = {r["sheet"] for r in cb["receipts"]}
    for r in cb["rows"]:
        assert 2011 <= r["class_year"] <= 2023
        assert r["sheet"] in sheets and r["club"]
        assert r["process"] in ("hearing", "settled")
        assert (r["hearing"] is not None) == (r["process"] == "hearing")
        if r["process"] == "hearing":
            assert r["exchanged"] is True


def test_cots_backfill_matches_the_cots_lab_file():
    # The same cases data/_labs/cots_arb_cases.json holds for the window, one
    # row per (player, season, kind): a player listed on two sheets counts once.
    lab = json.loads((ROOT / "data" / "_labs" / "cots_arb_cases.json").read_text("utf-8"))
    want = {(c["player"], c["season"], c["kind"]) for c in lab["cases"]
            if c["season"] and 2011 <= c["season"] <= 2023}
    got = {(r["player_name"], r["class_year"], r["process"])
           for r in _ledger()["cots_backfill"]["rows"]}
    assert got == want

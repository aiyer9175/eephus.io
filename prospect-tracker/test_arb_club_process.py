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

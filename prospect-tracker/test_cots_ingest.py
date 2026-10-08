# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Guards on the one-time Cot's Contracts capture and the deferral check (X05-20, M04-25).

The parser is tested on a saved sample of real sheet fragments; nothing here
touches the network. The artifact is checked for schema and attribution, and
the second-capture refusal is exercised against a receipts file in tmp_path.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
_SPEC = importlib.util.spec_from_file_location(
    "ingest_cots", ROOT / "tools" / "ingest_cots.py")
cots = importlib.util.module_from_spec(_SPEC)
sys.modules["ingest_cots"] = cots
_SPEC.loader.exec_module(cots)

ATTR = "Cot's Contracts (Baseball Prospectus)"
SAMPLE = (ROOT / "test_fixtures" / "cots" / "sample_sheet.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def players():
    return {p["name"]: p for p in cots.parse_sheet(SAMPLE, "sample")}


def test_parse_players_and_contracts(players):
    assert {"Aaron Judge", "Gerrit Cole"} <= set(players)
    judge = players["Aaron Judge"]
    assert judge["contracts"][0]["years"] == 9
    assert judge["contracts"][0]["total_usd"] == 360_000_000
    assert (judge["contracts"][0]["first_season"], judge["contracts"][0]["last_season"]) == (2023, 2031)


def test_arbitration_filing_figures_and_hearing(players):
    ev = cots.arbitration_events(players["Aaron Judge"])
    filed = [e for e in ev if e["season"] == 2022][0]
    assert (filed["player_figure_usd"], filed["club_figure_usd"]) == (21_000_000, 17_000_000)
    assert filed["kind"] == "settled" and filed["club_raw"] == "NY Yankees"
    hear = [e for e in cots.arbitration_events(players["Gerrit Cole"])
            if e["kind"] == "hearing"][0]
    assert hear["result"] == "player_won" and hear["season"] == 2019
    assert (hear["player_figure_usd"], hear["club_figure_usd"]) == (13_500_000, 11_425_000)


def test_deferral_event_and_ledger_key(players):
    sanchez = [p for n, p in players.items() if n.startswith("Cristopher S")][0]
    ev = cots.deferral_events(sanchez)
    assert len(ev) == 1 and ev[0]["class_year"] == 2027
    assert ev[0]["player_slug"] == "cristopher_sanchez"
    assert cots.deferral_events(players["Aaron Judge"]) == []


def test_money_and_slug_parsing():
    assert cots.parse_money("$605,000") == 605_000
    assert cots.parse_money("$1.35M") == 1_350_000
    assert cots.parse_money("$162") is None  # unit dropped on the sheet
    assert cots.slugify("José Ramírez") == "jose_ramirez"
    assert cots.slugify("J.T. Realmuto") == "j_t_realmuto"


def test_terms_lines_found_on_sample():
    lines = cots.terms_lines(SAMPLE)
    assert any("Baseball Prospectus" in t for t in lines)
    assert any("permission of MLB Advanced Media" in t for t in lines)


def test_deferral_check_matches_ledger_and_flags_contradiction():
    deferred = [
        {"player": "A B", "player_slug": "a_b", "sheet": "s", "contract": "c",
         "total_usd": 1, "class_year": 2025, "last_season": 2030, "notes": ["x"]},
        {"player": "C D", "player_slug": "c_d", "sheet": "s", "contract": "c",
         "total_usd": 2, "class_year": 2026, "last_season": 2030, "notes": ["x"]},
        {"player": "E F", "player_slug": "e_f", "sheet": "s", "contract": "c",
         "total_usd": 3, "class_year": 2026, "last_season": 2030, "notes": ["x"]},
    ]
    ledger = {"a_b:2025": {"deferred": True}, "c_d:2026": {"deferred": False},
              "e_f:2024": {"deferred": True}}
    out = cots.deferral_check(deferred, ledger)
    assert out["n_deferred_signings"] == 3 and out["n_in_ledger"] == 2
    assert out["n_without_ledger_entry"] == 1
    assert out["n_ledger_entry_says_no_deferral"] == 1
    assert out["winters_covered"] == [2025, 2026]
    miss = [r for r in out["signings"] if not r["in_ledger"]][0]
    assert miss["ledger_names_other_years"] == ["e_f:2024"]


def test_second_capture_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(cots, "CACHE", tmp_path)
    monkeypatch.setattr(cots, "RECEIPTS", tmp_path / "receipts.json")

    def boom(*a, **k):
        raise AssertionError("network touched on a refused capture")
    monkeypatch.setattr(cots.urllib.request, "urlopen", boom)
    cots._save_receipts({"attribution": ATTR, "sheets": [], "drops": [],
                         "captures": [{"started_at": "2026-10-08T00:00:00+00:00", "n_ok": 30}]})
    assert cots.capture(force=False) == 2
    assert cots.capture(force=True, reason=None) == 2
    assert cots.capture(force=True, reason="no date here") == 2
    assert "REFUSED" in cots.capture_refused(cots._load_receipts(), False, None)
    assert cots.capture_refused(cots._load_receipts(), True, "2026-11-02 sheets restructured") is None
    # a first capture is not refused
    assert cots.capture_refused({"captures": []}, False, None) is None


def test_capture_stays_inside_request_budget():
    assert len(cots.SHEETS) == 30 and cots.MAX_REQUESTS == 30
    assert cots.MIN_DELAY >= 5
    assert "arkndjl" in cots.UA and "ProspectTracker" in cots.UA


def test_not_reachable_from_the_pipeline():
    for name in ("run_monthly.py", "run_nightly.py", "build_site.py"):
        f = ROOT / name
        if f.exists():
            assert "ingest_cots" not in f.read_text(encoding="utf-8", errors="replace"), name


def test_artifact_schema_and_attribution():
    a = json.loads((ROOT / "data" / "cots_deferral_check.json").read_text(encoding="utf-8"))
    assert a["attribution"] == ATTR
    assert ATTR in " ".join(a["_doc"])
    cov = a["deferral_coverage"]
    assert cov["n_deferred_signings"] == len(cov["signings"]) > 0
    assert cov["n_in_ledger"] + cov["n_without_ledger_entry"] == cov["n_deferred_signings"]
    assert cov["winters_covered"] == sorted(set(cov["winters_covered"]))
    assert a["n_sheets"] == 30
    keys = {"player", "ledger_key", "in_ledger", "ledger_deferred", "sheet", "contract",
            "total_usd", "class_year", "notes"}
    for r in cov["signings"]:
        assert keys <= set(r)
        assert r["ledger_key"] == f"{cots.slugify(r['player'])}:{r['class_year']}"
    # the ledger the check reads is the curated one, and the verdicts agree with it
    ledger = json.loads((ROOT / "data" / "deferrals.json").read_text(encoding="utf-8"))["players"]
    for r in cov["signings"]:
        assert r["in_ledger"] == (r["ledger_key"] in ledger)


def test_registry_and_glossary_rows_carry_the_attribution():
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = [m for m in reg["models"] if m["model_id"] == "cots_deferral_check"]
    assert len(row) == 1
    assert row[0]["eval_artifact"] is None
    assert row[0]["provisional_kind"] == "measurement_only"
    assert ATTR in json.dumps(row[0])
    gl = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    e = [x for x in gl["entries"] if x["id"] == "cots_contracts"]
    assert len(e) == 1 and ATTR in e[0]["origin"]

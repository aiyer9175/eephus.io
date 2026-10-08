# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Guards on the MLB Trade Rumors Top 50 prediction capture (FA_PRED_CAPTURE).

The parser is read on trimmed fixtures of two real posts (no live call), one
per header format: 2015-16 names one predicted team in the header, 2025-26
prints a position and four writers' team picks on the next line. The lab file
is checked for shape only: nothing here scores, compares or reads an outcome
(the FA destination gate owns every comparison, after its registration).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
_SPEC = importlib.util.spec_from_file_location(
    "fa_predictions_capture", ROOT / "tools" / "fa_predictions_capture.py")
cap = importlib.util.module_from_spec(_SPEC)
sys.modules["fa_predictions_capture"] = cap
_SPEC.loader.exec_module(cap)

FIX = ROOT / "test_fixtures" / "fa_predictions"


def _rows(off: str) -> list[dict]:
    return cap.parse_mlbtr((FIX / f"mlbtr_top50_{off}_trimmed.html")
                           .read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("a parser test touched the network")
    monkeypatch.setattr(cap.urllib.request, "urlopen", _boom)


def test_single_team_header_format_2015_16():
    rows = _rows("2015-16")
    assert [r["rank"] for r in rows] == [1, 2, 3]
    price = rows[0]
    assert price["player_name"] == "David Price"
    assert (price["pred_years"], price["pred_total_mm"]) == (7, 217.0)
    assert price["pred_aav_mm"] == 31.0
    assert price["pred_team"] == "Cubs"
    assert price["pred_team_by_writer"] is None
    assert rows[1]["player_name"] == "Jason Heyward"
    assert (rows[1]["pred_years"], rows[1]["pred_total_mm"], rows[1]["pred_team"]) == (10, 200.0, "Yankees")
    assert rows[2]["pred_team"] == "Dodgers"


def test_writer_picks_header_format_2025_26():
    rows = _rows("2025-26")
    assert [r["rank"] for r in rows] == [1, 2, 3]
    tucker = rows[0]
    assert (tucker["player_name"], tucker["position"]) == ("Kyle Tucker", "RF")
    assert (tucker["pred_years"], tucker["pred_total_mm"]) == (11, 400.0)
    assert tucker["pred_team"] is None
    picks = {p["writer"]: p["team"] for p in tucker["pred_team_by_writer"]}
    assert picks == {"Tim Dierkes": "Dodgers", "Anthony Franco": "Yankees",
                     "Darragh McDonald": "Phillies", "Steve Adams": "Giants"}
    # Later rows use first names only; they map back to the full names.
    bo = rows[1]
    assert (bo["player_name"], bo["position"], bo["pred_years"]) == ("Bo Bichette", "SS", 8)
    assert {p["writer"] for p in bo["pred_team_by_writer"]} == set(picks)
    assert {p["team"] for p in bo["pred_team_by_writer"]} == {"Blue Jays"}


def test_no_field_is_inferred():
    for off in ("2015-16", "2025-26"):
        for r in _rows(off):
            assert r["age"] is None          # the headers print no age
            assert "signed" not in r["prediction_text"].lower()


def test_footer_and_out_of_sequence_numbers_are_not_entries():
    # Each fixture ends with a '99. Not An Entry' line in the footer.
    for off in ("2015-16", "2025-26"):
        assert all(r["player_name"] != "Not An Entry" for r in _rows(off))


def test_contract_and_team_helpers():
    m = cap._CONTRACT.search("Kenta Maeda - Diamondbacks. $20MM posting fee plus five year, $60MM")
    assert (cap._years(m.group("years")), float(m.group("total"))) == (5, 60.0)
    assert cap._team("D-Backs") == "D-backs"
    assert cap._team("Red Sox") == "Red Sox"
    assert cap._team("Sox") is None


def test_capture_is_a_lab_file_and_no_pipeline_imports_the_tool():
    assert cap.RETRO_PATH.parent.parent.name == "_labs"
    hits = [p.name for p in ROOT.glob("*.py")
            if p.name != Path(__file__).name
            and "fa_predictions_capture" in p.read_text(encoding="utf-8", errors="replace")]
    assert hits == []


def test_retro_lab_file_shape_when_present():
    if not cap.RETRO_PATH.exists():
        pytest.skip("retro capture not written")
    d = json.loads(cap.RETRO_PATH.read_text(encoding="utf-8"))
    assert "MLB Trade Rumors" in d["attribution"]["source"]
    assert set(d["seasons"]) | set(d["offseasons_missing"]) == set(cap.RETRO_URLS)
    for off, s in d["seasons"].items():
        assert s["source_url"] == cap.RETRO_URLS[off] == d["attribution"]["posts"][off]
        assert len(s["raw_sha256"]) == 64 and s["captured_at"]
        assert s["parser_version"] == cap.PARSER_VERSION
        assert [r["rank"] for r in s["rows"]] == list(range(1, len(s["rows"]) + 1))
        assert s["n_unresolved"] == sum(r["mlbam_id"] is None for r in s["rows"])

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The postseason bracket simulator against its registration
(docs/betting-2026-10/BRACKET_SIM_GATE.md, section 14): the constants, the
formats, the label and the sentences, the record's paths, the registry row,
the glossary entry, the pipeline step, and the fence that no betting price,
slot, record or ledger path reads the payload. Reads source and docs only."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import bracket_sim as bs  # noqa: E402

GATE = ROOT / "docs" / "betting-2026-10" / "BRACKET_SIM_GATE.md"
SRC = (ROOT / "bracket_sim.py").read_text(encoding="utf-8")


def _gate() -> str:
    return re.sub(r"\s+", " ", GATE.read_text(encoding="utf-8"))


def test_identity_and_the_serve_flag():
    assert bs.MODEL_ID == "postseason_bracket_sim"
    assert bs.METHOD_VERSION == "bracket_v1"
    assert (ROOT / bs.GATE_DOC).exists()
    g = _gate()
    assert "Model id `postseason_bracket_sim`" in g and "method `bracket_v1`" in g
    # Landed 2026-10-01, inside the owner's window (by 2026-10-03): served.
    assert "When the build lands by 2026-10-03 it lands with the flag True" in g
    assert bs.SERVE_BRACKET_SIM is True


def test_the_prior_is_the_literature_elo_untouched():
    from tools import betting_elo as be
    g = _gate()
    assert "base rating 1500, K = 4, home advantage 24 Elo points" in g
    assert (be.BASE_RATING, be.LITERATURE_K, be.LITERATURE_HOME_ADV_ELO) == (1500.0, 4.0, 24.0)
    assert "about 0.5345" in g
    assert abs(bs.elo_win_prob(1500.0, 1500.0, bs._elo_home_adv()) - 0.5345) < 1e-4
    assert "refresh=False" in SRC and "final_ratings" in SRC


def test_the_formats_are_the_registered_table():
    g = _gate()
    assert "| Wild Card Series | F | best of 3 | every game at the higher seed |" in g
    assert "2-2-1: the higher seed hosts games 1, 2 and 5" in g
    assert "2-3-2: the higher seed hosts games 1, 2, 6 and 7" in g
    assert bs.ROUND_NEED == {"F": 2, "D": 3, "L": 4, "W": 4}
    assert bs.ROUND_LENGTH == {"F": 3, "D": 5, "L": 7, "W": 7}
    assert bs.HOST_TABLE["F"] == (1, 1, 1)
    assert bs.HOST_TABLE["D"] == (1, 1, 0, 0, 1)
    assert bs.HOST_TABLE["L"] == bs.HOST_TABLE["W"] == (1, 1, 0, 0, 0, 1, 1)
    assert bs.PLAYED_STATES == ("F", "O")
    assert bs.BOARD_GAME_TYPES == ("F", "D", "L", "W")


def test_exact_with_no_seed_and_no_random_draw():
    assert "Exact, with no random draws, so there is no seed and no simulation error" in _gate()
    assert "import random" not in SRC and "numpy" not in SRC and "seed(" not in SRC


def test_the_label_and_the_sentences_are_the_registered_ones():
    g = _gate()
    assert 'the label **"implied, no market"**' in g
    assert bs.LABEL == "implied, no market"
    assert ("Pennant and World Series: implied by the postseason bracket simulator as of "
            "<date>, no market.") in g
    assert bs.LINE_TEMPLATE.format(as_of="<date>") in g
    assert '"The postseason odds did not update on <date>."' in g
    assert bs.NOT_UPDATED_TEMPLATE.format(as_of="<date>") in g
    for col in ("Division", "Playoffs", "Bye", "Proj W", "Win band"):
        assert col in bs.DIVISION_COLUMNS_TEMPLATE


def test_the_record_lives_under_cache_and_its_copies_are_ignored():
    # read from the source: the test harness points the constants at a mirror
    assert 'RECORD_PATH = CACHE / "bracket_sim" / "record.json"' in SRC
    assert 'RECORD_DERIVED_PATH = DATA / "bracket_sim_record.json"' in SRC
    assert 'OUT_PATH = DATA / "bracket_sim.json"' in SRC
    assert 'CACHE = ROOT / ".cache"' in SRC and 'DATA = ROOT / "data"' in SRC
    assert "`.cache/bracket_sim/record.json`" in _gate()
    for rel in ("data/bracket_sim.json", "data/bracket_sim_record.json"):
        r = subprocess.run(["git", "check-ignore", rel], cwd=ROOT, capture_output=True, text=True)
        assert r.returncode == 0, f"{rel} is not gitignored"


def test_the_registry_row_is_the_registered_one():
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    rows = {m["model_id"]: m for m in reg["models"]}
    row = rows["postseason_bracket_sim"]
    assert row["verdict"] == "unvalidated" and row["eval_artifact"] is None
    assert row["registration_status"].startswith("registered")
    assert "data/bracket_sim.json" in row["surface"] and "implied, no market" in row["surface"]
    assert row["baseline"].startswith("the coin bracket")
    assert row["champion"].startswith("bracket_v1: exact series recursion")
    assert "INT-A2 (b)" in row["notes"] and "Q901-1 (c)" in row["notes"]
    assert "regular-season only" in row["notes"].lower()
    assert "BRACKET_SIM_GATE.md" in row["notes"]
    elo = rows["betting_elo_benchmark"]["surface"]
    assert "postseason_bracket_sim" in elo and "construction, not the tier" in elo


def test_the_glossary_entry_exists_for_both_surfaces():
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    e = {x["id"]: x for x in g["entries"]}["postseason_bracket_sim"]
    assert e["category"] == "betting" and set(e["module"]) == {"betting", "franchise"}
    assert "implied, no market" in e["definition"]
    assert "regular-season games only" in e["methodology"]


def test_the_step_runs_after_the_board_and_before_the_franchise_board():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i9e = src.index('_step("9e. Betting odds snapshot + payload (betting.json)"')
    ib = src.index('_step("d10f. Postseason bracket simulator (bracket_sim.json)"')
    ifr = src.index('_step("6b7d. Franchise board (franchise_board.json)"')
    assert i9e < ib < ifr
    import run_monthly
    assert "bracket_sim" in run_monthly.SCHEDULED_EXPORTS
    assert '_record_ingest("bracket_sim", False, 0,' in src


# ---------------------------------------------------------------------------
# the fence (gate 12)
# ---------------------------------------------------------------------------
def _betting_side_files():
    files = sorted(ROOT.glob("betting_*.py")) + sorted((ROOT / "tools").glob("betting_*.py"))
    files += sorted(ROOT.glob("provisional_*.py"))
    files += [ROOT / "proj_export.py", ROOT / "leaderboard_vintages.py"]
    return [p for p in files if p.exists()]


def test_no_price_slot_record_or_ledger_path_reads_the_payload():
    offenders = []
    for p in _betting_side_files():
        src = p.read_text(encoding="utf-8", errors="replace")
        for needle in ("bracket_sim", "postseason_bracket_sim"):
            if needle in src:
                offenders.append(f"{p.name} names {needle}")
    assert not offenders, offenders
    # the betting record and the provisional picks live in betting_export
    assert (ROOT / "betting_export.py") in _betting_side_files()


def test_the_simulator_writes_no_betting_artifact_and_derives_no_price():
    for banned in ("betting_record", "shadow", "calibration.jsonl", "published_slots",
                   "SERVE_PROB_CALIBRATION", "SERVE_RUN_DISPERSION", "_fair_american",
                   "impliedAmerican", "kelly"):
        assert banned not in SRC, banned
    imported = set(re.findall(r"^\s*(?:import|from)\s+([\w.]+)", SRC, re.M))
    for mod in ("betting_export", "betting_settle", "betting_shadow", "betting_learning",
                "betting_credits", "betting_ingest"):
        assert mod not in imported, mod
    # the board is READ, at one path, and never written
    assert SRC.count("BOARD_PATH") == 2 and "_read_json(BOARD_PATH)" in SRC


def test_the_franchise_writer_never_emits_pennants_or_titles():
    import franchise_export as fr
    assert {"pennants", "titles"} <= fr.FORBIDDEN_KEYS
    assert '"pennants"' not in SRC and '"titles"' not in SRC

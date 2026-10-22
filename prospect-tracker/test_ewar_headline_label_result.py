# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The headline eWAR label check's result pin (docs/efv-2026-10-22/EWAR_HEADLINE_LABEL_GATE.md
part 9, the 2026-10-22 entry): the circularity guard held by identity, as part 4.5 stated
before the look, so the switch is cleared. The entry's numbers are asserted against the
tracked records.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "efv-2026-10-22" / "EWAR_HEADLINE_LABEL_GATE.md"
GUARD = ROOT / "docs" / "efv-2026-10-22" / "ewar_headline_label_guard.json"
BLAST = ROOT / "docs" / "efv-2026-10-22" / "ewar_headline_label_blast.json"


def _entry() -> str:
    text = re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))
    return text.split("### 2026-10-22: the guard HOLDS, by identity, as part 4.5 stated", 1)[1]


def test_verdict_structure_and_record():
    rec = json.loads(GUARD.read_text(encoding="utf-8"))
    assert rec["verdict"] == {"g1_non_inferior": True, "g2_non_inferior": True, "guard_holds": True,
                              "twin_also_non_inferior": True, "structure_as_registered": True,
                              "switch_cleared": True}
    assert rec["structure"]["holds"] is True
    assert rec["registration"] == "docs/efv-2026-10-22/EWAR_HEADLINE_LABEL_GATE.md"
    assert rec["label"]["vintage_id"] == "ewar-headline-2026-10-02-a020cf64844a-8b30fccf933d"
    assert rec["run"]["git_head"].startswith("2f6ce6c6")
    assert rec["generated_at"] == rec["run"]["finished_at"]
    entry = _entry()
    assert "**THE GUARD HOLDS (part 4.4). The switch is cleared**" in entry
    assert "It says nothing about the eABS part; EWHL-R1 is the first read that can" in entry


def test_g1_and_g2_are_exact_identities():
    rec = json.loads(GUARD.read_text(encoding="utf-8"))
    g1 = rec["g1"]
    assert g1["n_pairs"] == 2416 and g1["n_players"] == 713 and g1["n_pairs_departing"] == 0
    assert g1["gap"] == 0.0 and g1["lower"] == 0.0 and g1["sd"] == 0.0
    assert g1["s_series"] == g1["s_fwar"] and round(g1["s_fwar"], 4) == 0.4788
    assert g1["twin"]["gap"] == 0.0
    g2 = rec["g2"]
    assert g2["n_departing_cells"] == 0 and g2["underpowered"] is False
    want = {"runs_scored": 0.4524, "runs_allowed": 0.5250, "run_differential": 0.7312, "wins": 0.7146}
    for k, r in want.items():
        o = g2["outcomes"][k]
        assert o["n_club_seasons"] == 360 and o["dT"] == 0.0 and o["r_part"] == o["r_frame"]
        assert round(o["r_frame"], 4) == r
        assert f"{r:.4f}"[1:] in _entry() or f"{r:.4f}" in _entry()


def test_secondary_legs_match_the_entry():
    sec = json.loads(GUARD.read_text(encoding="utf-8"))["secondary"]
    real = sec["realized_pitchers"]
    assert real["n_pairs"] == 1536 and round(real["gap"], 4) == -0.1075 and round(real["lower"], 4) == -0.1311
    for k in ("rate_per_600pa", "floor_200pa", "framing_rows"):
        assert sec[k]["gap"] == 0.0
    assert sec["floor_200pa"]["n_pairs"] == 3217 and sec["framing_rows"]["n_pairs"] == 254


def test_blast_radius_matches_the_entry():
    b = json.loads(BLAST.read_text(encoding="utf-8"))
    assert b["rows"] == 2698 and b["rows_moved"] == 1029
    assert b["rows_by_source"] == {"bbref": 6, "ewar_v2": 6, "fwar": 2686}
    assert list(b["seasons_moved"]) == ["2026"]
    s = b["seasons_moved"]["2026"]
    assert (s["n"], s["mean"], s["sd"], s["max_abs"], s["n_abs_ge_0_1"], s["n_abs_ge_0_5"]) == (
        1029, -0.0011, 0.0718, 0.51, 112, 1)
    entry = _entry()
    assert "Under the switch 1,029 rows move, every move in 2026: mean -0.0011 WAR, sd 0.0718" in entry


def test_registry_row_claims_no_accuracy():
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = next(r for r in reg["models"] if r["model_id"] == "ewar_headline_label")
    assert row["verdict"] == "provisional" and row["provisional_kind"] == "measurement_only"
    assert row["eval_artifact"] == "docs/efv-2026-10-22/ewar_headline_label_guard.json"
    assert "No accuracy claim is made for any label." in row["notes"]
    assert "by identity" in row["notes"]


def test_the_switch_flipped_with_the_epoch_and_the_fingerprint():
    # the flag commit (part 4.4, owner default EWHL-Q1 (a)): flag, epoch and label term together
    import ewar_headline_label as H
    import storage
    import war_source
    assert war_source.EFV_LABEL_EWAR_HEADLINE is True
    assert war_source.EFV_LABEL_PROVIDER == "ewar_headline"
    assert war_source.DEFAULT_PROVIDER == "fwar" and war_source.LABEL_EWAR_CORE is False
    assert storage.BOARD_RANK_BASIS_EPOCH == "2026-10-22"
    assert f"|label=ewar_headline@{H.vintage_id()}|" in storage.BOARD_BASIS_FINGERPRINT
    assert storage.board_basis_fingerprint() == storage.BOARD_BASIS_FINGERPRINT
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = next(r for r in reg["models"] if r["model_id"] == "ewar_headline_label")
    assert "war_source.EFV_LABEL_EWAR_HEADLINE = True" in row["notes"]


def test_glossary_names_efv_label_without_an_accuracy_claim():
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    by_id = {e.get("id"): e for e in g["entries"]}
    assert "eFV's own training label (first-six-season WAR) is, from 2026-10-22, the headline eWAR" in         by_id["war"]["definition"]
    assert "no accuracy gain is claimed from it" in by_id["war"]["methodology"]
    assert "on eFV's training label (from 2026-10-22 the headline eWAR" in by_id["xfv"]["formula"]


def test_flip_entry_names_its_commit():
    text = re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))
    assert "### 2026-10-22: the switch flipped (`70c0c00d`)" in text
    assert "EWHL-R1 stays registered for the 2027 season's data." in text

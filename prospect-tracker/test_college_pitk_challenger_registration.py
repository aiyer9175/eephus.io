# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The pitcher K% challenger is registered before any look, and stays unscored
until its one registered date.

Owner answer M19-1 (2026-09-25): keep the no-skill CollegeSavant legs flagged
and muted, and pre-register a pitcher K% challenger on full-season NCAA box K%
(census M03-05, M03-19). The registration is docs/COLLEGE_PIT_K_CHALLENGER_GATE.md
plus the registry row college_pitk_box_challenger; the scorer is
tools/college_pitk_challenger_lab.py. These tests pin that the three agree,
that the frozen pair file holds identities and no rates, that the scorer
refuses off its date, and that its arithmetic does what the gate says on
synthetic rows (no real pair is scored here).
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import random
from pathlib import Path

import model_registry as mr

ROOT = Path(__file__).parent
GATE = ROOT / "docs" / "COLLEGE_PIT_K_CHALLENGER_GATE.md"
PAIRS = ROOT / "docs" / "college-pitk-challenger-2026-10-01" / "frozen_pairs.json"


def _lab():
    spec = importlib.util.spec_from_file_location(
        "college_pitk_challenger_lab", ROOT / "tools" / "college_pitk_challenger_lab.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_gate_names_pairs_metric_rule_date_and_disclosure():
    text = GATE.read_text(encoding="utf-8")
    for needle in ("registered, not scored", "frozen_pairs.json", "2026-11-02",
                   "seed 20261102", "2000 draws", "|S| >= 60", "P1", "P2", "P3",
                   "Earlier measurements on these pairs", "4.013", "3.995",
                   "COL-XRV", "100 * SO / (outs + H + BB)"):
        assert needle in text, needle


def test_frozen_pairs_hold_identities_only():
    doc = json.loads(PAIRS.read_text(encoding="utf-8"))
    assert doc["n_pairs"] == len(doc["pairs"]) == 232
    assert doc["by_cs_year"] == {"2024": 224, "2025": 8}
    for p in doc["pairs"]:
        assert set(p) == {"name_key", "cs_name", "pitcher_id", "cs_year", "cs_team",
                          "single_a_season"}, p


def test_registry_row_is_registered_not_scored():
    rows = {m["model_id"]: m for m in mr.load()["models"]}
    row = rows["college_pitk_box_challenger"]
    assert row["verdict"] == "provisional"
    assert row["provisional_kind"] == "data_blocked_stub"
    assert row["registration_status"] == "registered, not scored"
    assert not row["eval_artifact"]
    # The docs/ path left the registry's reader fields in COPY_11 (2026-10-04);
    # the row still says it is gated, and the gate doc is the file GATE names.
    assert "gated by registration" in row["baseline"] and GATE.is_file()
    assert "2026-11-02" in row["champion"]


def test_scorer_constants_match_the_gate():
    lab = _lab()
    assert lab.REGISTERED_LOOK_DATE == dt.date(2026, 11, 2)
    assert (lab.MIN_PAIRS, lab.BOOT_B, lab.SEED, lab.N_PERM, lab.MIN_NCAA_IP) == (
        60, 2000, 20261102, 200, 20.0)
    assert lab.PAIRS_PATH == PAIRS


def test_scorer_refuses_off_its_date(monkeypatch, capsys):
    lab = _lab()

    class _D(dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 1)

    monkeypatch.setattr(lab.dt, "date", _D)
    if lab.RESULT_PATH.exists():
        assert lab.main([]) == 2
        return
    assert lab.main([]) == 2
    assert "refused" in capsys.readouterr().out
    assert not lab.RESULT_PATH.exists()


def test_box_k_pct_definition():
    lab = _lab()
    assert lab.box_k_pct({"ip": 30.0, "so": 36, "h": 25, "bb": 11}) == 100.0 * 36 / 126
    assert lab.box_k_pct({"ip": 19.2, "so": 30, "h": 10, "bb": 5}) is None
    assert lab.box_k_pct({"ip": 40.0, "so": 50, "bb": 5}) is None


def _synthetic(n, informative, seed=7):
    rnd = random.Random(seed)
    rows = []
    for _ in range(n):
        box = rnd.gauss(24, 6)
        tracked = rnd.gauss(24, 6)
        signal = box if informative else rnd.gauss(24, 6)
        rows.append((box, tracked, 24 + 0.8 * (signal - 24) + rnd.gauss(0, 2)))
    return rows


def test_score_reads_signal_and_noise_as_the_gate_says():
    lab = _lab()
    assert lab.score(_synthetic(40, True))["verdict"] == "COVERAGE-STARVED"
    good = lab.score(_synthetic(80, True))
    assert good["verdict"] == "PASS", good
    bad = lab.score(_synthetic(80, False))
    assert bad["verdict"] == "FAIL", bad
    assert not bad["clauses"]["P1_beats_null"]

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The two Baserunning flags are True after the flip (task EBR_2F_FLIP; built
dark by EBR_2_BUILD_DARK; integration.md 5; plan Part 8 8.A, class 2).

MLBSTATS_BASERUNNING_LIVE gates the /mlbstats/ tab and the exporter's output
path (data/ only while on, else .cache/baserunning/preview/); CARD_BASERUNNING_LIVE
gates skills.br on the MLB player card. EBR_2F_FLIP flips both in ONE commit and
updates the pins below in the same commit, so a half-flipped tree (a tab with no
card block, or a card block with no board under data/) cannot ship.
"""
from __future__ import annotations

from pathlib import Path

import baserunning_export as bre

ROOT = Path(__file__).parent


def test_both_flags_are_true_after_the_flip():
    assert bre.MLBSTATS_BASERUNNING_LIVE is True
    assert bre.CARD_BASERUNNING_LIVE is True


def test_the_flags_flip_together():
    """One commit carries both: a tab without the card block, or the reverse,
    is the half-flipped state this pin refuses."""
    assert bre.MLBSTATS_BASERUNNING_LIVE == bre.CARD_BASERUNNING_LIVE


def test_the_live_exporter_writes_data_and_the_four_files_exist():
    assert bre.out_dir() == bre.DATA_DIR
    for name in (bre.OUT_NAME, bre.HISTORY_NAME, bre.SUBSTRATE_NAME, bre.EVAL_NAME):
        assert (ROOT / "data" / name).exists(), f"data/{name} is missing after the flip"


def test_the_served_shell_carries_the_baserunning_tab_after_the_flip():
    shell = (ROOT / "mlbstats" / "index.html").read_text(encoding="utf-8")
    assert 'data-mlbsection="baserunning"' in shell
    assert "mlbstats-section-baserunning" in shell
    assert 'data-mlbsection="defense"' in shell and 'data-mlbsection="leverage"' in shell


def test_the_card_exporter_reads_the_flag_from_the_exporter_module():
    """mlb_player_export never carries a flag of its own: the two surfaces
    read one module, so one flip reaches both."""
    src = (ROOT / "mlb_player_export.py").read_text(encoding="utf-8")
    assert "_bre.CARD_BASERUNNING_LIVE" in src
    assert "CARD_BASERUNNING_LIVE =" not in src
    page = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
    assert "function baserunningBlock(" in page and "skills || {}).br" in page


def test_the_board_page_hides_the_section_without_the_shells_panel():
    """mlbstats.js reads section=baserunning only when the shell wrote the
    panel, the League tab's rule, so a dark build renders what it did before."""
    js = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
    assert 'function baserunningLive() { return !!document.getElementById("mlbstats-section-baserunning"); }' in js
    assert 's[1] === "baserunning" ? baserunningLive()' in js

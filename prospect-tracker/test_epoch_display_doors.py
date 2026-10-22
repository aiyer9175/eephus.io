# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The fWAR label epoch's display doors (step D + U, 2026-10-03).

Owner answer EPOCH-Q4 (2026-09-30): "Keep eWAR v2 shown": eWAR v2 stays the
displayed WAR, the training label is fWAR either way. The orchestrator's
implementation ruling (EPOCH-Q4-IMPL, R1a) and its reader classification
principle: a DISPLAY reader (a served WAR number, page, chart, export or stamp
a visitor sees, or an identity helper using WAR as a tiebreak) reads
provider="ewar_v2" explicitly; a LABEL reader (the training label, the label
corpus, a refit, a backtest, an eval artifact or a gate statistic) follows
war_source.DEFAULT_PROVIDER, which is "fwar"; a DUAL reader's served output
keeps eWAR v2 and its label consumer gets its own fwar path.

This file pins each door BY SOURCE, so a refactor that quietly drops a
provider= argument (and lets a display fall through to the label default)
fails here with the door's name.

THE eWAR v3 FLIP (owner answers EBR-Q5 and EW3-19; docs/ebr-2026-09-30/EBR_GATE.md
11.10.5): every display door reads war_source.DISPLAY_PROVIDER, which is eWAR v3
while war_source.EWAR_V3_LIVE is on and eWAR v2 otherwise. F-DEF's input file
reads only Baseball-Reference's decomposition columns and stays on ewar_v2. It also pins the fingerprint's `label=` term
to the frozen vintage's id, which is what the gate's part 7 row D + U and part
8 name as the training label build.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent


def _src(obj) -> str:
    return inspect.getsource(obj)


def _file(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# the two providers
# --------------------------------------------------------------------------- #
def test_the_label_default_is_fwar_and_the_display_provider_follows_the_v3_flag():
    import war_source
    assert war_source.DEFAULT_PROVIDER == "fwar"
    assert war_source.DISPLAY_PROVIDER == ("ewar_v3" if war_source.EWAR_V3_LIVE else "ewar_v2")
    assert "ewar_v3" in war_source.PROVIDERS and war_source.DEFAULT_PROVIDER != "ewar_v3"


def test_the_label_term_names_the_frozen_vintage_build():
    """Gate part 7 row D + U and part 8: the `label=` term reads fwar@<vintage id>
    once the label flips. Ruling R1a: the term names the TRAINING LABEL build."""
    import fwar_vintage
    import storage
    if not fwar_vintage.available():
        pytest.skip("needs data/fwar_vintage.json (EPOCH_D9_FREEZE)")
    vid = fwar_vintage.load().get("vintage_id")
    assert vid, "the frozen vintage carries no vintage_id"
    def _label_term(fp: str) -> str:
        # the disp= term carries a bare '|' inside it, so pick the label= part by prefix
        return next(part for part in fp.split("|") if part.startswith("label="))[len("label="):]

    want = f"fwar@{vid}"
    import war_source
    if war_source.EFV_LABEL_PROVIDER == "ewar_headline":
        # the headline eWAR label check's switch (EWAR_HEADLINE_LABEL_GATE.md part 3): the term
        # names eFV's label, whose frozen vintage id embeds this fWAR vintage's id
        import ewar_headline_label
        want = f"ewar_headline@{ewar_headline_label.vintage_id()}"
        assert ewar_headline_label.vintage_id().startswith(f"ewar-headline-{vid}-")
    assert _label_term(storage.board_basis_fingerprint()) == want
    assert _label_term(storage.BOARD_BASIS_FINGERPRINT) == want
    # the epoch bump rode the same commit (runbook U)
    assert storage.BOARD_RANK_BASIS_EPOCH >= "2026-10-03"


# --------------------------------------------------------------------------- #
# D1 and D2: every display door names eWAR v2
# --------------------------------------------------------------------------- #
DP = "provider=war_source.DISPLAY_PROVIDER"


def test_the_mlbstats_boards_side_war_reads_the_display_provider():
    import bullpen_export as be
    import war_source
    assert f"war_source.side_war_by_season({DP})" in _src(be._side_war_by_season)
    basis = be.served_war_basis()
    assert basis["war_provider"] == war_source.DISPLAY_PROVIDER
    body = _src(be.served_war_basis).split('"""', 2)[2]
    assert "DEFAULT_PROVIDER" not in body, "served_war_basis must not follow the label default"
    assert be._served_war_provider() == war_source.DISPLAY_PROVIDER


def test_the_player_pages_served_war_reads_the_display_provider():
    import mlb_player_export as mpe
    body = _src(mpe._war_maps)
    assert f"war_source.side_war_by_season({DP})" in body
    assert 'war_source.side_war_by_season(provider="bwar")' in body   # the reference read
    assert "DEFAULT_PROVIDER" not in body.split('"""', 2)[2]
    refs = _src(mpe._war_ref_maps)
    assert '"provider": "ewar_v3", "series": "realized"' in refs and '"provider": "ewar_v2"' in refs


def test_the_pal_history_war_reads_the_display_provider():
    src = _file("pal_export.py")
    assert "provider = war_source.DISPLAY_PROVIDER" in src
    assert 'war_source.stint_frame("pit", provider=provider)' in src
    assert "stint_frame('pit', provider='{_WAR_PROVIDER" in src   # the served stamp names it too


def test_the_earned_board_frames_read_the_display_provider():
    import war_board_export as wbe
    assert f"war_source.stint_frame(side, {DP})" in _src(wbe._stint_frame)


def test_the_trade_lookup_reads_the_display_provider():
    src = _file("mlb_trade_lookup.py")
    assert DP in src
    assert "war_source.condensed_frame(" in src


def test_f_def_input_file_stays_on_ewar_v2_by_name():
    # decomposition columns only, an input to a Franchise grade (EBR_GATE.md 11.10.5)
    src = _file("tools/build_def_history.py")
    assert 'war_source.run_value_frame("bat", provider="ewar_v2")' in src


def test_the_identity_helpers_read_the_display_provider():
    import fa_ident
    import proj_export
    assert f"war_source.stint_frame(side, {DP})" in _src(fa_ident.war_daily_index)
    assert f"war_source.stint_frame(side, {DP})" in _src(proj_export._display_names)


def test_the_fa_archive_frames_read_the_display_provider():
    import fa_pipeline
    body = _src(fa_pipeline._resolve_signed_via_war_daily)
    assert f"war_source.stint_frame(side, {DP})" in body
    assert '"source": war_source.DISPLAY_PROVIDER' in body


def test_no_display_door_names_ewar_v2_as_its_provider():
    """Every door above reads DISPLAY_PROVIDER; only F-DEF's input names ewar_v2
    (and the player pages' eWAR v2 reference column, which is not the served WAR)."""
    for rel in ("bullpen_export.py", "pal_export.py", "war_board_export.py", "mlb_trade_lookup.py",
                "fa_ident.py", "proj_export.py", "fa_pipeline.py", "overseas_export.py"):
        src = _file(rel)
        assert 'provider="ewar_v2")' not in src, rel
        assert 'row_on_provider(cw, "ewar_v2")' not in src, rel
    import mlb_player_export as mpe
    assert 'provider="ewar_v2")' not in _src(mpe._war_maps)


def test_the_hall_of_fame_line_stays_pinned_to_bwar():
    import hof_data
    assert hof_data.WAR_PROVIDER == "bwar"


def test_the_ewar_nightly_prices_on_the_bwar_input_frames():
    src = _file("tools/build_ewar.py")
    assert 'war_source.stint_frame("bat", provider="bwar")' in src
    assert 'war_source.stint_frame("pit", provider="bwar")' in src


# --------------------------------------------------------------------------- #
# B: the timeseries career_war payload is split
# --------------------------------------------------------------------------- #
def test_the_timeseries_career_war_block_is_the_displayed_series():
    import storage
    body = _src(storage._served_career_war)
    assert "war_source.row_on_provider(row, war_source.DISPLAY_PROVIDER)" in body
    export_src = _src(storage.export_timeseries_json)
    assert '"career_war": _served_career_war(' in export_src
    assert '"career_war_label": _label_career_war(' in export_src


def test_row_on_provider_re_expresses_an_fwar_row_on_the_incumbent():
    import war_source
    row = {"seasons": {"2023": 2.5, "2024": 4.27}, "career_war": 6.77, "war_per_yr": 3.38,
           "war_seasons_count": 2, "source": "fwar",
           "seasons_ewar_v2": {"2023": 2.4, "2024": 4.6},
           "seasons_bwar": {"2023": 2.4, "2024": 4.3},
           "ewar_coverage": {"covered": 2, "total": 2, "fallback_years": []},
           "fwar_coverage": {"n_fwar": 2, "war_basis": "fwar"},
           "seasons_pa": {"2023": 10, "2024": 0}}
    shown = war_source.row_on_provider(row, "ewar_v2")
    assert shown["seasons"] == {"2023": 2.4, "2024": 4.6}
    assert shown["career_war"] == 7.0 and shown["war_per_yr"] == 3.5
    assert shown["war_seasons_count"] == 2 and shown["source"] == "ewar_v2"
    assert shown["incumbent_of"] == "fwar" and "fwar_coverage" not in shown
    assert shown["seasons_bwar"] == row["seasons_bwar"] and shown["seasons_pa"] == row["seasons_pa"]
    assert row["seasons"] == {"2023": 2.5, "2024": 4.27}, "the input must not be mutated"
    # the label series is the row as stored; a pre-epoch row has nothing to re-express
    assert war_source.row_on_provider(row, "fwar") == row
    legacy = {"seasons": {"2023": 1.0}, "career_war": 1.0, "source": "ewar_v2"}
    assert war_source.row_on_provider(legacy, "ewar_v2") == legacy
    bw = war_source.row_on_provider(row, "bwar")
    assert bw["seasons"] == {"2023": 2.4, "2024": 4.3} and bw["source"] == "bbref"
    assert war_source.row_on_provider(None, "ewar_v2") == {}


def test_the_label_consumers_of_the_payload_read_career_war_label():
    import source_backtest
    assert _file("bayes_trade_value.py").count('player.get("career_war_label")') >= 4
    assert 'player.get("career_war_label")' in _file("grpo_prospect.py")
    assert _file("source_backtest.py").count("career_war_label") >= 3
    assert 'p.get("career_war_label")' in _file("draft_source_backtest.py")
    assert 'p.get("career_war_label")' in _src(source_backtest._outcome)


def test_overseas_signings_show_the_displayed_ewar_and_grade_on_the_label():
    src = _file("overseas_export.py")
    assert "_ws.row_on_provider(cw, _ws.DISPLAY_PROVIDER)" in src
    assert '"career_war_label": cw' in src
    assert 'entry.get("career_war_label") or cw' in src


# --------------------------------------------------------------------------- #
# the display check's receipt: the frozen vintage this run flipped to
# --------------------------------------------------------------------------- #
def test_the_frozen_vintage_is_the_one_the_fingerprint_names():
    p = ROOT / "data" / "fwar_vintage.json"
    if not p.exists():
        pytest.skip("needs data/fwar_vintage.json (EPOCH_D9_FREEZE)")
    import storage
    blob = json.loads(p.read_text(encoding="utf-8"))
    import war_source
    if war_source.EFV_LABEL_PROVIDER == "ewar_headline":
        # the headline label's vintage is built on this fWAR vintage and names it
        assert f"label=ewar_headline@ewar-headline-{blob.get('vintage_id')}-" in storage.BOARD_BASIS_FINGERPRINT
    else:
        assert f"label=fwar@{blob.get('vintage_id')}" in storage.BOARD_BASIS_FINGERPRINT

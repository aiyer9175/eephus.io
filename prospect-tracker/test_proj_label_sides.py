# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The two-sided label repair (2026-09-18), pinned so the double count cannot
come back.

WHAT WAS WRONG. fa_projection._war_age_maps returns {(mlbam, season): war}
summed across the war_daily bat and pit frames, and build_corpus wrote that
whole-player total onto the HITTER row and onto the PITCHER row through one
side-blind lookup. proj_ml.build_training_frame and proj_eval._assemble then
added the two rows together, so a player who both hit and pitched trained and
scored at exactly 2x. Measured on the corpus: 671 of 35,825 player-seasons
carry a row on both sides, all 671 held the identical value on each, and the
label sum ran 26,408.0 against a repaired 26,269.7. Ohtani 2023 entered the
frame at 17.08 against a real 8.54.

WHAT THESE TESTS PIN, in the order the repair has to hold:

  1. the side-keyed map keeps the sides apart, and the whole-player map that
     the LABEL is built from still sums them (both contracts, one source);
  2. build_corpus writes THIS SIDE'S WAR into `war` and the whole-player WAR
     into `war_total`, on both rows of a two-way player;
  3. a two-way player's label is his REAL total WAR, exactly ONCE - the
     regression guard, which fails the moment the sum comes back;
  4. a ONE-SIDED player is untouched, including the pitcher whose plate
     appearances the hitter corpus excludes by position: his label is still
     bat + pit, so the repair removes the doubling and not the totality;
  5. the training frame and the eval harness agree, because they are the same
     function;
  6. a corpus pickled before the repair cannot be served or silently reused:
     the label_shape stamp makes it stale, re-keys proj_ml's caches, and the
     live bundle says so when it was fitted before the repair.
"""

from __future__ import annotations

import logging
import pickle
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

import fa_projection as fp
import proj_eval
import proj_ml

# One two-way season (5.0 batting, 3.0 pitching), one pure hitter, and one
# pitcher who batted badly - the three cases the repair has to separate.
TWOWAY, HITTER, PITCHER = 101, 202, 303
SEASON = 2024
FRAMES = {
    "bat": [(TWOWAY, SEASON, 5.0, 29), (HITTER, SEASON, 4.0, 27),
            (PITCHER, SEASON, -0.4, 31)],
    "pit": [(TWOWAY, SEASON, 3.0, 29), (PITCHER, SEASON, 2.5, 31)],
}


def _frame(side):
    rows = FRAMES[side]
    return pd.DataFrame({"mlb_ID": [r[0] for r in rows],
                         "year_ID": [r[1] for r in rows],
                         "WAR": [r[2] for r in rows],
                         "age": [r[3] for r in rows]})


@pytest.fixture
def war_frames(monkeypatch):
    """war_source and pybaseball stubbed at the import site, so the maps are
    exercised for real with no network and no war_daily pull."""
    ws = types.ModuleType("war_source")
    ws.DEFAULT_PROVIDER = "ewar_v2"
    ws.stint_frame = lambda side, provider=None: _frame(side)
    monkeypatch.setitem(sys.modules, "war_source", ws)
    monkeypatch.setitem(sys.modules, "pybaseball", types.ModuleType("pybaseball"))
    return ws


def _statsapi_rows():
    """The minimum StatsAPI shape build_corpus reads: the two-way player and
    the hitter get hitting lines, the two-way player and the pitcher get
    pitching lines, and the pitcher's hitting line carries position P so the
    hitter corpus drops it exactly as it does in production."""
    def hit(mlbam, pos):
        return {"player": {"id": mlbam}, "position": {"abbreviation": pos},
                "stat": {"plateAppearances": 600, "atBats": 540, "hits": 150,
                         "doubles": 30, "triples": 2, "homeRuns": 30,
                         "baseOnBalls": 55, "strikeOuts": 130, "hitByPitch": 5,
                         "sacFlies": 5, "runs": 90}}

    def pit(mlbam):
        return {"player": {"id": mlbam}, "position": {"abbreviation": "P"},
                "stat": {"battersFaced": 700, "inningsPitched": "170.1",
                         "strikeOuts": 190, "baseOnBalls": 50, "hitByPitch": 6,
                         "homeRuns": 18, "earnedRuns": 65, "gamesStarted": 28,
                         "gamesPlayed": 28}}

    return {(SEASON, "hitting"): [hit(TWOWAY, "DH"), hit(HITTER, "3B"), hit(PITCHER, "P")],
            (SEASON, "pitching"): [pit(TWOWAY), pit(PITCHER)]}


@pytest.fixture
def corpus(monkeypatch, tmp_path, war_frames):
    """A real build_corpus over the stubbed sources, with every cache path
    inside tmp_path so the run cannot touch .cache."""
    monkeypatch.setattr(fp, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(fp, "CORPUS_CACHE", tmp_path / "fa_corpus.pkl")
    monkeypatch.setattr(fp.fa_sources, "fetch_statsapi_season_range",
                        lambda first, last: _statsapi_rows())
    return fp.build_corpus(first_season=SEASON, last_season=SEASON, force=True)


def _row(corpus, side, mlbam):
    got = [r for r in corpus[side] if r["mlbam"] == mlbam]
    assert len(got) == 1, (side, mlbam, len(got))
    return got[0]


# ---------------------------------------------------------------- 1. the maps

def test_the_side_keyed_map_keeps_the_sides_apart(war_frames):
    side_war, age = fp._side_war_age_maps()
    assert side_war == {("bat", TWOWAY, SEASON): 5.0, ("bat", HITTER, SEASON): 4.0,
                        ("bat", PITCHER, SEASON): -0.4,
                        ("pit", TWOWAY, SEASON): 3.0, ("pit", PITCHER, SEASON): 2.5}
    assert age == {(TWOWAY, SEASON): 29, (HITTER, SEASON): 27, (PITCHER, SEASON): 31}


def test_the_whole_player_map_still_sums_the_sides(war_frames):
    """_war_age_maps keeps its documented contract. The LABEL is a total and
    has to stay one; what the repair moved is which of the two quantities the
    corpus ROW carries."""
    war, age = fp._war_age_maps()
    assert war == {(TWOWAY, SEASON): 8.0, (HITTER, SEASON): 4.0,
                   (PITCHER, SEASON): pytest.approx(2.1)}
    assert age == {(TWOWAY, SEASON): 29, (HITTER, SEASON): 27, (PITCHER, SEASON): 31}


# --------------------------------------------------------- 2/3. the corpus row

def test_each_corpus_row_carries_its_own_sides_war(corpus):
    hit = _row(corpus, "hit", TWOWAY)
    pit = _row(corpus, "pit", TWOWAY)
    assert hit["war"] == 5.0, "the hitter row must carry HITTING WAR"
    assert pit["war"] == 3.0, "the pitcher row must carry PITCHING WAR"
    assert hit["war_total"] == pit["war_total"] == 8.0


def test_the_two_way_label_is_his_real_war_exactly_once(corpus):
    """THE REGRESSION GUARD. Before the repair both rows read 8.0 and every
    consumer added them, so this player's label was 16.0. If the side-blind
    lookup comes back, or if a consumer goes back to summing `war` across
    sides, this fails."""
    label = fp.war_actual_map(corpus)
    assert label[(TWOWAY, SEASON)] == 8.0
    assert label[(TWOWAY, SEASON)] != 16.0
    rows = [_row(corpus, "hit", TWOWAY), _row(corpus, "pit", TWOWAY)]
    assert rows[0]["war"] != rows[1]["war"], (
        "identical war on both rows is the defect's own signature")
    assert rows[0]["war"] + rows[1]["war"] == pytest.approx(rows[0]["war_total"]), (
        "H + P = T: the per-side split must reconstruct the whole")


# ----------------------------------------------------- 4. the one-sided player

def test_a_one_sided_player_is_left_exactly_where_he_was(corpus):
    """The hitter has no pitcher row and never did: 4.0 before and after.

    The pitcher is the case the side key could have broken. His plate
    appearances are excluded from the hitter corpus by position, so he carries
    a corpus row on ONE side while war_daily carries him on both. Summing the
    corpus rows would drop his batting WAR and quietly change the estimand for
    7,745 player-seasons. `war_total` is the whole quantity, so his label is
    still bat + pit."""
    label = fp.war_actual_map(corpus)
    assert label[(HITTER, SEASON)] == 4.0
    assert _row(corpus, "hit", HITTER)["war"] == 4.0
    assert not [r for r in corpus["pit"] if r["mlbam"] == HITTER]

    assert label[(PITCHER, SEASON)] == pytest.approx(2.1), "bat -0.4 plus pit 2.5"
    assert _row(corpus, "pit", PITCHER)["war"] == 2.5, "the ROW is pitching only"
    assert not [r for r in corpus["hit"] if r["mlbam"] == PITCHER], "pos P is dropped"


# --------------------------------------- 5. the frame and the harness agree

def test_the_training_frame_and_the_eval_harness_read_the_same_label(corpus):
    """Both call fa_projection.war_actual_map. Scoring against a truth built
    differently from the one you trained on is how the doubling stayed
    invisible: it cancelled on both sides of every published comparison."""
    label = fp.war_actual_map(corpus)
    _lg, _by, harness = proj_eval._assemble(corpus)
    assert harness == label
    assert harness[(TWOWAY, SEASON)] == 8.0
    src = proj_ml.build_training_frame.__code__.co_names
    assert "war_actual_map" in src, (
        "build_training_frame must build its label through the shared function, "
        "not by summing r['war'] across sides again")


# ------------------------------------------------- 6. nothing stale is reused

def test_a_pre_repair_corpus_is_stale_and_cannot_be_served(corpus, tmp_path):
    assert corpus["label_shape"] == fp.LABEL_SHAPE
    assert fp._corpus_label_shape_stale(corpus) is None
    legacy = {k: v for k, v in corpus.items() if k != "label_shape"}
    reason = fp._corpus_label_shape_stale(legacy)
    assert reason and "2x" in reason


def test_the_cache_keys_separate_the_repaired_labels(corpus):
    """The frame cache and the 29 point-in-time bundles key on _war_tag and on
    nothing about the rows, so without the shape in the key a frame built on
    the doubled labels would be handed straight to a retrain on the repaired
    corpus."""
    legacy = {k: v for k, v in corpus.items() if k != "label_shape"}
    assert proj_ml._war_tag(corpus) == "_ewar_v2_side_keyed_v1"
    assert proj_ml._war_tag(legacy) == "_ewar_v2"
    assert proj_ml._war_tag({"war_provider": "bwar"}) == "", "no historical filename moves"


def test_a_legacy_corpus_reproduces_the_old_doubling_and_says_so(corpus, caplog):
    """The fallback is the OLD behaviour and nothing else. A third semantics
    invented for corpora that cannot supply the label would be worse than the
    defect, because it would be undocumented."""
    legacy = {k: v for k, v in corpus.items() if k != "label_shape"}
    for side in ("hit", "pit"):
        legacy[side] = [{k: v for k, v in r.items() if k != "war_total"}
                        for r in legacy[side]]
    with caplog.at_level(logging.WARNING, logger=fp.log.name):
        out = fp.war_actual_map(legacy)
    assert out[(TWOWAY, SEASON)] == 8.0, "5.0 + 3.0: the pre-repair sum of two side rows"
    assert "DOUBLES" in caplog.text


def test_the_live_bundle_says_when_it_predates_the_repair(monkeypatch, tmp_path, caplog):
    """model/proj_lgbm loads by PATH and carries no cache key, so the stamp in
    meta is the only thing that can tell a bundle fitted on doubled labels from
    one fitted after the repair. It warns and keeps serving: refusing here
    would drop every /projections/ row to the champion decay to fix a
    bookkeeping gap."""
    import joblib
    monkeypatch.setattr(proj_ml, "_LOADED", None)
    d = tmp_path / "proj_lgbm"
    d.mkdir()
    joblib.dump({"meta": {"version": "proj_lgbm_v1"}}, d / "models.joblib")
    with caplog.at_level(logging.WARNING, logger=proj_ml.log.name):
        proj_ml.load(d)
    assert "label_shape absent" in caplog.text and "2x" in caplog.text

    monkeypatch.setattr(proj_ml, "_LOADED", None)
    caplog.clear()
    joblib.dump({"meta": {"version": "proj_lgbm_v1", "label_shape": fp.LABEL_SHAPE}},
                d / "models.joblib")
    with caplog.at_level(logging.WARNING, logger=proj_ml.log.name):
        proj_ml.load(d)
    assert "label_shape" not in caplog.text
    monkeypatch.setattr(proj_ml, "_LOADED", None)


def test_the_off_hook_that_build_ewar_takes_still_works(monkeypatch, tmp_path, war_frames):
    """tools/build_ewar.live_fip_corpus rebuilds a FIP-only corpus for the
    nightly eWAR artifact and switches the WAR and age join off by replacing
    fa_projection._war_age_maps with a stub that returns empty maps. It has to:
    the war_daily frames it would otherwise read are priced by the artifact it
    is rebuilding.

    Moving build_corpus onto the side-keyed map would have defeated that
    override silently and made the nightly re-enter the artifact, so the
    override is consulted explicitly and this pins it."""
    monkeypatch.setattr(fp, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(fp, "CORPUS_CACHE", tmp_path / "off.pkl")
    monkeypatch.setattr(fp.fa_sources, "fetch_statsapi_season_range",
                        lambda first, last: _statsapi_rows())
    pulled = []
    real = fp._side_war_age_maps
    monkeypatch.setattr(fp, "_side_war_age_maps",
                        lambda provider=None: (pulled.append(1), real(provider))[1])
    monkeypatch.setattr(fp, "_war_age_maps", lambda provider=None: ({}, {}))
    c = fp.build_corpus(first_season=SEASON, last_season=SEASON, force=True)
    assert pulled == [], "the override must switch the war_daily pull off entirely"
    assert all(r["war"] is None and r["war_total"] is None
               for side in ("hit", "pit") for r in c[side])
    assert all(r["age"] is None for r in c["hit"])


def test_the_normal_path_pulls_the_frames_once(corpus, monkeypatch):
    """The override is honoured without paying for it: war_daily is not read a
    second time to recover the whole-player total, which is summed from the
    side-keyed rows instead."""
    calls = []
    monkeypatch.setattr(fp, "_side_war_age_maps",
                        lambda provider=None: (calls.append("side"), ({}, {}))[1])
    fp.build_corpus(first_season=SEASON, last_season=SEASON, force=True)
    assert calls == ["side"], calls


def test_the_corpus_pickle_round_trips_the_stamp(corpus, tmp_path):
    """The stamp has to survive the pickle or the staleness check reads a
    corpus that is repaired in memory and pre-repair on disk."""
    p = tmp_path / "fa_corpus.pkl"
    assert p.exists(), "build_corpus wrote its cache inside tmp_path"
    with open(p, "rb") as fh:
        back = pickle.load(fh)
    assert back["label_shape"] == fp.LABEL_SHAPE
    assert _row(back, "hit", TWOWAY)["war"] == 5.0
    assert _row(back, "hit", TWOWAY)["war_total"] == 8.0


def test_no_lab_builds_its_own_label_by_summing_across_sides():
    """809902c6 named nine lab sites that accumulated r["war"] across sides into
    their own war_actual. After the repair a row's `war` is its own side's WAR,
    so that sum is the whole-player total only by accident of the summing
    order; the ONE label is fa_projection.war_actual_map. A source fence, so
    the pattern cannot come back in a new lab."""
    import re
    pat = re.compile(r'war_actual\[[^\]]+\]\s*=\s*war_actual\.get\([^)]*\)\s*\+\s*r\["war"\]')
    here = Path(__file__).parent
    offenders = sorted(
        str(f.relative_to(here)).replace("\\", "/")
        for f in list(here.glob("tools/*.py")) + list(here.glob("*.py"))
        if f.name != Path(__file__).name and pat.search(f.read_text(encoding="utf-8", errors="replace"))
    )
    assert offenders == [], offenders

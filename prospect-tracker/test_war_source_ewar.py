# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The servable 'ewar_v2' provider (eWAR epoch, 2026-09-03, wave 1 lane L2).

Offline. A synthetic pybaseball module supplies the bWAR frames and a
synthetic eWAR payload is injected into ewar._CACHE (the memo ewar.load
serves), so the facade's transform runs on numbers this file controls:

  covered pitcher-season, one stint     Ohtani 2023   bwp 3.8 -> ewp 3.2
  covered pitcher-season, two stints    two_stint 2024  1.0 + 0.2 = 1.2 -> 1.6
                                        (IPouts 300 / 100, so +0.3 / +0.1)
  covered season, no batting move       Trout 2024    ewb == bwb == 2.5
  uncovered seasons                     Trout 2023, Skenes 2025 (bWAR served,
                                        recorded in fallback_years)
  artifact-only player-season           777777 2024 (in the side map, not in
                                        any frame: the union never shrinks)
  blank batting line (WAR NaN)          Skenes 2024 bat: artifact 0.0, frame
                                        NaN; no "bat" key invented, NaN kept
  artifact-only, all zero               888888 2024: never enters the side map
  frame row with no mlb_ID              keeps bWAR, no crash

WHAT IS HELD
  * ewar_v2 is the default provider
  * career_war_bulk: covered season == ewar_for()['ewar'], uncovered ==
    bWAR and listed in fallback_years, seasons_bwar kept, aggregates
    recomputed, source 'ewar_v2'
  * stint_frame: per (mlb_ID, year_ID) the stint WARs sum to the artifact's
    side total to 1e-9; league sum == bWAR league sum + sum of deltas;
    WAR_bwar preserved; every other column untouched; IPouts / PA split
  * condensed_frame: same replacement, equal split without an exposure column
  * side_war_by_season: artifact overlay, bWAR fill, superset of keys
  * provider='bwar' byte-exact vs stats over the raw frames
  * coverage_report shape; DataUnavailable names the build command;
    mlbam_for resolution order; the frame pin restores itself
"""
from __future__ import annotations

import contextlib
import inspect
import json
import math
import pathlib
import sys
import types

import numpy as np
import pandas as pd
import pytest

import ewar
import fa_ident
import mlb_player_export
import stats
import war_source


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
_BAT_ROWS = [
    {"name_common": "Mike Trout", "mlb_ID": 545361, "year_ID": 2023,
     "age": 31, "team_ID": "LAA", "PA": 507, "G": 119, "WAR": 2.9,
     "WAR_def": -0.4, "runs_position": -2.1, "pitcher": "N", "salary": 37116667},
    {"name_common": "Mike Trout", "mlb_ID": 545361, "year_ID": 2024,
     "age": 32, "team_ID": "LAA", "PA": 126, "G": 29, "WAR": 1.9,
     "WAR_def": -0.1, "runs_position": -0.7, "pitcher": "N", "salary": 37116667},
    {"name_common": "Mike Trout", "mlb_ID": 545361, "year_ID": 2024,
     "age": 32, "team_ID": "LAA", "PA": 40, "G": 10, "WAR": 0.6,
     "WAR_def": 0.0, "runs_position": -0.2, "pitcher": "N", "salary": 37116667},
    {"name_common": "Shohei Ohtani", "mlb_ID": 660271, "year_ID": 2023,
     "age": 28, "team_ID": "LAA", "PA": 599, "G": 135, "WAR": 6.2,
     "WAR_def": -1.0, "runs_position": -8.0, "pitcher": "Y", "salary": 30000000},
    # Skenes' BLANK batting line: B-Ref publishes the row with WAR NaN (PA 0),
    # the artifact prices it 0.0, and the facade must neither invent a "bat"
    # key for it nor fill the NaN.
    {"name_common": "Paul Skenes", "mlb_ID": 694973, "year_ID": 2024,
     "age": 22, "team_ID": "PIT", "PA": 0, "G": 23, "WAR": np.nan,
     "WAR_def": np.nan, "runs_position": np.nan, "pitcher": "Y", "salary": 740000},
]
_PIT_ROWS = [
    {"name_common": "Shohei Ohtani", "mlb_ID": 660271, "year_ID": 2023,
     "age": 28, "team_ID": "LAA", "IPouts": 396, "G": 23, "WAR": 3.8,
     "WAA": 2.5, "salary": 30000000},
    {"name_common": "Paul Skenes", "mlb_ID": 694973, "year_ID": 2024,
     "age": 22, "team_ID": "PIT", "IPouts": 399, "G": 23, "WAR": 4.3,
     "WAA": 3.4, "salary": 740000},
    {"name_common": "Paul Skenes", "mlb_ID": 694973, "year_ID": 2025,
     "age": 23, "team_ID": "PIT", "IPouts": 540, "G": 30, "WAR": 5.6,
     "WAA": 4.5, "salary": 800000},
    {"name_common": "Two Stint", "mlb_ID": 123456, "year_ID": 2024,
     "age": 30, "team_ID": "AAA", "IPouts": 300, "G": 20, "WAR": 1.0,
     "WAA": 0.4, "salary": 1000000},
    {"name_common": "Two Stint", "mlb_ID": 123456, "year_ID": 2024,
     "age": 30, "team_ID": "BBB", "IPouts": 100, "G": 8, "WAR": 0.2,
     "WAA": 0.0, "salary": 1000000},
    {"name_common": "No Id", "mlb_ID": np.nan, "year_ID": 2024,
     "age": 27, "team_ID": "CCC", "IPouts": 60, "G": 5, "WAR": 0.5,
     "WAA": 0.3, "salary": 740000},
]

_TARGETS = [
    ("shohei_ohtani", 660271, True),
    ("mike_trout", 545361, False),
    ("paul_skenes", 694973, True),
    ("two_stint", 123456, True),
    ("nobody_in_mlb", 999999, False),
]


def _blk(**kw):
    kw.setdefault("tm", ["X"])
    return kw


#: The synthetic artifact. Blocks carry a side only where a war_daily row of
#: that side exists (ewar.export_payload), which this mirrors.
_EWAR = {
    "model": "ewar_v2", "generated_at": "2026-09-03T00:00:00",
    "seasons": [2016, 2026], "n_player_seasons": 6,
    "players": {
        "660271": {"2023": _blk(ew=9.4, bw=10.0, ewb=6.2, bwb=6.2,
                                ewp=3.2, bwp=3.8)},
        # Skenes 2024: pitching priced, batting side present but BLANK (0.0);
        # 2025 absent from the artifact
        "694973": {"2024": _blk(ew=4.9, bw=4.3, ewb=0.0, bwb=0.0,
                                ewp=4.9, bwp=4.3)},
        "545361": {"2024": _blk(ew=2.5, bw=2.5, ewb=2.5, bwb=2.5)},   # 2023 absent
        "123456": {"2024": _blk(ew=1.6, bw=1.2, ewp=1.6, bwp=1.2)},
        "777777": {"2024": _blk(ew=3.0, bw=2.0, ewp=3.0, bwp=2.0)},   # no frame row
        "888888": {"2024": _blk(ew=0.0, bw=0.0, ewb=0.0, bwb=0.0)},   # no frame row, zero
    },
}

#: A variant where the batting side MOVES (as it would if fielding ever
#: did): Trout 2024 ewb 2.9 vs bwb 2.5, spread over PA 126 / 40.
_EWAR_FIELDING_MOVES = json.loads(json.dumps(_EWAR))
_EWAR_FIELDING_MOVES["players"]["545361"]["2024"].update({"ew": 2.9, "ewb": 2.9})

_CONDENSED_COLS = ["mlb_ID", "year_ID", "name_common", "WAR"]


def _fake_pybaseball() -> types.ModuleType:
    mod = types.ModuleType("pybaseball")
    bat = pd.DataFrame(_BAT_ROWS)
    pit = pd.DataFrame(_PIT_ROWS)

    def bwar_bat(return_all=False):
        return bat.copy() if return_all else bat[_CONDENSED_COLS].copy()

    def bwar_pitch(return_all=False):
        return pit.copy() if return_all else pit[_CONDENSED_COLS].copy()

    mod.bwar_bat = bwar_bat
    mod.bwar_pitch = bwar_pitch
    return mod


def _clear_memos() -> None:
    fa_ident.war_daily_index.cache_clear()
    with contextlib.suppress(Exception):
        import bullpen_export
        bullpen_export._side_war_by_season.cache_clear()
    with contextlib.suppress(Exception):
        import pal_export
        pal_export.load_bref_pitcher_war.cache_clear()
    war_source._EWAR_FRAME_DIAG.clear()


@contextlib.contextmanager
def _world(payload: dict = _EWAR):
    """Fake pybaseball + injected artifact + last-good cache redirected to a
    temp dir (the production guard test_war_source.py explains: the real
    cache must never hold these fixtures). Everything restored on exit."""
    import tempfile
    saved_mod = sys.modules.get("pybaseball")
    sys.modules["pybaseball"] = _fake_pybaseball()
    saved_cache_dir = war_source._cache_dir
    saved_ewar = ewar._CACHE
    ewar._CACHE = payload
    tmp = tempfile.TemporaryDirectory()
    war_source._cache_dir = lambda: pathlib.Path(tmp.name)
    _clear_memos()
    try:
        yield
    finally:
        war_source._cache_dir = saved_cache_dir
        ewar._CACHE = saved_ewar
        tmp.cleanup()
        if saved_mod is None:
            sys.modules.pop("pybaseball", None)
        else:
            sys.modules["pybaseball"] = saved_mod
        _clear_memos()


def _group_sums(df) -> dict[tuple[int, int], float]:
    sub = df[df["mlb_ID"].notna()]
    out: dict[tuple[int, int], float] = {}
    for r in sub.itertuples(index=False):
        k = (int(r.mlb_ID), int(r.year_ID))
        out[k] = out.get(k, 0.0) + float(r.WAR)
    return out


# --------------------------------------------------------------------------- #
# the default
# --------------------------------------------------------------------------- #
def test_default_provider_is_ewar_v2():
    assert war_source.DEFAULT_PROVIDER == "ewar_v2"
    for fn in (war_source.career_war_bulk, war_source.career_war_table,
               war_source.side_war_by_season, war_source.stint_frame,
               war_source.condensed_frame, war_source.run_value_frame,
               war_source.name_index):
        assert inspect.signature(fn).parameters["provider"].default == "ewar_v2", \
            fn.__name__


# --------------------------------------------------------------------------- #
# career_war_bulk
# --------------------------------------------------------------------------- #
def test_career_war_bulk_serves_ewar_where_covered_and_bwar_where_not():
    with _world():
        out = war_source.career_war_bulk(_TARGETS, 2000, 2026)
    assert "nobody_in_mlb" not in out

    oh = out["shohei_ohtani"]
    assert oh["seasons"] == {"2023": 9.4}                    # == ewar_for()['ewar']
    assert oh["seasons"]["2023"] == ewar.ewar_for(660271, 2023, payload=_EWAR)["ewar"]
    assert oh["seasons_bwar"] == {"2023": 10.0}              # bat 6.2 + pit 3.8
    assert oh["career_war"] == 9.4 and oh["war_per_yr"] == 9.4
    assert oh["war_seasons_count"] == 1
    assert oh["source"] == "ewar_v2"
    assert oh["ewar_coverage"] == {"covered": 1, "total": 1, "fallback_years": []}

    tr = out["mike_trout"]
    assert tr["seasons"] == {"2023": 2.9, "2024": 2.5}       # 2023 = bWAR fallback
    assert tr["seasons_bwar"] == {"2023": 2.9, "2024": 2.5}
    assert tr["ewar_coverage"] == {"covered": 1, "total": 2, "fallback_years": [2023]}
    assert tr["career_war"] == 5.4 and tr["war_per_yr"] == 2.7

    sk = out["paul_skenes"]
    assert sk["seasons"] == {"2024": 4.9, "2025": 5.6}
    assert sk["seasons_bwar"] == {"2024": 4.3, "2025": 5.6}
    assert sk["ewar_coverage"]["fallback_years"] == [2025]
    assert sk["career_war"] == 10.5 and sk["war_per_yr"] == 5.25

    ts = out["two_stint"]
    assert ts["seasons"] == {"2024": 1.6} and ts["seasons_bwar"] == {"2024": 1.2}

    # 2dp everywhere, like the incumbent
    for row in out.values():
        for v in list(row["seasons"].values()) + [row["career_war"], row["war_per_yr"]]:
            assert v == round(v, 2)


def test_career_war_bulk_with_no_mlbam_is_all_fallback():
    """Identity is the binding constraint: a target with no id gets the bWAR
    aggregate whole, every year recorded as a fallback, never a guess."""
    with _world():
        out = war_source.career_war_bulk(
            [("mike_trout", 545361, False)], 2000, 2026)
        # stats keys the frame join on mlbam, so a None id finds nothing;
        # exercise the transform directly with a present aggregate instead
        agg = {"seasons": {"2023": 2.9, "2024": 2.5}, "career_war": 5.4,
               "war_per_yr": 2.7, "war_seasons_count": 2, "source": "bbref"}
        row = war_source._ewar_aggregate(agg, None, _EWAR)
    assert out["mike_trout"]["ewar_coverage"]["covered"] == 1
    assert row["seasons"] == agg["seasons"]
    assert row["source"] == "ewar_v2"
    assert row["ewar_coverage"] == {"covered": 0, "total": 2,
                                    "fallback_years": [2023, 2024]}


def test_career_war_bulk_bwar_is_byte_exact_over_the_raw_frames():
    """The explicit 'bwar' request must equal stats over the RAW frames (the
    pre-epoch behaviour), not stats over eWAR-replaced frames, even though
    stats reads stint_frame on the default provider."""
    with _world():
        with war_source._frames_pinned("bwar"):
            old = stats.fetch_career_war_bulk(_TARGETS, 2000, 2026)
        new = war_source.career_war_bulk(_TARGETS, 2000, 2026, provider="bwar")
    assert json.dumps(old, sort_keys=True) == json.dumps(new, sort_keys=True)
    assert new["shohei_ohtani"]["seasons"]["2023"] == 10.0
    assert new["two_stint"]["seasons"]["2024"] == 1.2
    assert new["paul_skenes"]["source"] == "bbref"
    assert all("seasons_bwar" not in r for r in new.values())


# --------------------------------------------------------------------------- #
# stint frames
# --------------------------------------------------------------------------- #
def test_pitching_stint_frame_sums_to_the_artifact_side_total():
    with _world():
        import pybaseball as pyb
        raw = pyb.bwar_pitch(return_all=True)
        df = war_source.stint_frame("pit")
        diag = war_source.ewar_frame_diagnostics()["pit"]

    # shape: same rows, same order, one new column at the end
    assert list(df.columns) == list(raw.columns) + ["WAR_bwar"]
    assert len(df) == len(raw)
    # WAR_bwar carries the original and every other column is untouched
    assert df["WAR_bwar"].equals(raw["WAR"])
    for c in raw.columns:
        if c != "WAR":
            assert df[c].equals(raw[c]), c

    sums = _group_sums(df)
    targets = war_source._artifact_side_targets(_EWAR, "pit")
    for k, s in sums.items():
        if k in targets:
            assert abs(s - targets[k][0]) < 1e-9, (k, s, targets[k])
        else:
            assert abs(s - _group_sums(raw)[k]) < 1e-12, (k, "uncovered must keep bWAR")
    assert abs(sums[(660271, 2023)] - 3.2) < 1e-9
    assert abs(sums[(694973, 2024)] - 4.9) < 1e-9
    assert abs(sums[(694973, 2025)] - 5.6) < 1e-12        # uncovered
    assert abs(sums[(123456, 2024)] - 1.6) < 1e-9

    # the two-stint split is proportional to IPouts (300 : 100 of +0.4)
    two = df[df["mlb_ID"] == 123456].sort_values("IPouts", ascending=False)
    assert np.allclose(two["WAR"].values, [1.3, 0.3])
    # the row with no mlb_ID keeps bWAR
    assert df.loc[df["mlb_ID"].isna(), "WAR"].tolist() == [0.5]

    # league sum == bWAR league sum + sum of deltas over covered player-seasons
    raw_sums = _group_sums(raw)
    deltas = sum(targets[k][0] - raw_sums[k] for k in raw_sums if k in targets)
    assert abs(deltas - (-0.6 + 0.6 + 0.4)) < 1e-9
    assert abs(df["WAR"].sum() - (raw["WAR"].sum() + deltas)) < 1e-9
    assert abs(diag["delta_sum"] - deltas) < 1e-9
    assert diag["covered_rows"] == 4 and diag["covered_player_seasons"] == 3
    assert diag["artifact_player_seasons"] == 4                # incl. 777777
    assert diag["bwar_revised"] == 0
    assert diag["artifact_generated_at"] == "2026-09-03T00:00:00"


def test_batting_stint_frame_does_not_move_at_fielding_weight_zero():
    """ewb == bwb on every covered block today, so the batting WAR column is
    unchanged in value; the same distribution still runs (WAR_bwar appears)."""
    with _world():
        import pybaseball as pyb
        raw = pyb.bwar_bat(return_all=True)
        df = war_source.stint_frame("bat")
        rv = war_source.run_value_frame()
        diag = war_source.ewar_frame_diagnostics()["bat"]   # cleared on exit
    assert np.allclose(df["WAR"].values, raw["WAR"].values, equal_nan=True)
    assert df["WAR_bwar"].equals(raw["WAR"])
    assert rv.equals(df)
    assert {"WAR_def", "runs_position", "PA", "pitcher", "WAR_bwar"} <= set(rv.columns)
    # the blank batting line stays blank: the artifact's 0.0 does not fill it
    assert df.loc[df["mlb_ID"] == 694973, "WAR"].isna().all()
    assert diag["covered_rows"] == 3 and diag["covered_player_seasons"] == 2
    assert diag["artifact_player_seasons"] == 4          # 660271, 694973, 545361, 888888


def test_batting_delta_is_spread_by_pa_if_fielding_ever_moves():
    with _world(_EWAR_FIELDING_MOVES):
        df = war_source.stint_frame("bat")
    two = df[(df["mlb_ID"] == 545361) & (df["year_ID"] == 2024)]
    two = two.sort_values("PA", ascending=False)
    # +0.4 over PA 126 : 40
    exp = [1.9 + 0.4 * 126 / 166, 0.6 + 0.4 * 40 / 166]
    assert np.allclose(two["WAR"].values, exp)
    assert abs(two["WAR"].sum() - 2.9) < 1e-9
    assert two["WAR_bwar"].tolist() == [1.9, 0.6]
    # the untouched seasons stay bWAR
    assert df.loc[(df["mlb_ID"] == 545361) & (df["year_ID"] == 2023), "WAR"].tolist() == [2.9]


def test_condensed_frame_replaces_war_with_an_equal_split_without_exposure():
    with _world():
        import pybaseball as pyb
        raw = pyb.bwar_pitch()
        cond = war_source.condensed_frame("pit")
    assert list(cond.columns) == _CONDENSED_COLS + ["WAR_bwar"]
    assert cond["WAR_bwar"].equals(raw["WAR"])
    two = cond[cond["mlb_ID"] == 123456]["WAR"].tolist()
    assert np.allclose(sorted(two), [0.4, 1.2])          # +0.2 each, no IPouts
    assert abs(sum(two) - 1.6) < 1e-9
    assert cond.loc[cond["mlb_ID"] == 660271, "WAR"].tolist() == pytest.approx([3.2])
    assert cond.loc[cond["mlb_ID"].isna(), "WAR"].tolist() == [0.5]


def test_frames_reflect_the_explicit_bwar_request_and_the_pin():
    with _world():
        import pybaseball as pyb
        assert war_source.stint_frame("pit", provider="bwar").equals(
            pyb.bwar_pitch(return_all=True))
        assert war_source.condensed_frame("pit", provider="bwar").equals(pyb.bwar_pitch())
        # the pin overrides the default for legacy readers inside the window
        with war_source._frames_pinned("bwar"):
            assert war_source.stint_frame("pit").equals(pyb.bwar_pitch(return_all=True))
        assert war_source._FRAME_PIN is None
        # nested pins restore the outer value
        with war_source._frames_pinned("bwar"):
            with war_source._frames_pinned("ewar_v2"):
                assert war_source._FRAME_PIN == "ewar_v2"
            assert war_source._FRAME_PIN == "bwar"
        assert war_source._FRAME_PIN is None
        with pytest.raises(ValueError):
            with war_source._frames_pinned("fwar"):
                pass


def test_the_last_good_cache_holds_the_raw_bwar_frame():
    """The eWAR transform runs on top of the cached download, never into it:
    a later outage must fall back to bWAR rows and re-apply the artifact."""
    with _world():
        war_source.stint_frame("pit")
        cached = pd.read_parquet(war_source._cache_path("pit"))
    assert "WAR_bwar" not in cached.columns
    assert cached.loc[cached["mlb_ID"] == 660271, "WAR"].tolist() == [3.8]


# --------------------------------------------------------------------------- #
# side_war_by_season
# --------------------------------------------------------------------------- #
def test_side_war_by_season_overlays_the_artifact_and_keeps_bwar_elsewhere():
    with _world():
        with war_source._frames_pinned("bwar"):
            base = mlb_player_export._war_daily()
        out = war_source.side_war_by_season()
        explicit = war_source.side_war_by_season(provider="bwar")
    assert explicit == base
    # coverage never shrinks: every bWAR (mlbam, season) is still there
    for mid, seasons in base.items():
        for season in seasons:
            assert season in out[mid], (mid, season)
    assert out[660271][2023] == {"bat": 6.2, "pit": 3.2}
    assert out[694973][2024] == {"pit": 4.9}                # blank bat line: no key
    assert out[694973][2025] == {"pit": 5.6}                # bWAR fill
    assert out[545361][2023] == {"bat": 2.9}                # bWAR fill
    assert out[545361][2024] == {"bat": 2.5}                # artifact, same value
    assert out[123456][2024] == {"pit": 1.6}
    assert out[777777][2024] == {"pit": 3.0}                # artifact-only, nonzero
    # the blank-row rule: a zero-valued side the bWAR map lacks is not added,
    # whether the block has another side (Skenes) or nothing at all (888888)
    assert "bat" not in out[694973][2024]
    assert 888888 not in out
    assert 694973 not in base or "bat" not in base[694973].get(2024, {})


# --------------------------------------------------------------------------- #
# the table, the coverage report, the name index
# --------------------------------------------------------------------------- #
def test_coverage_report_shape_on_a_synthetic_table():
    table = {
        "a": {"seasons": {"2023": 1.0, "2024": 2.0}, "source": "ewar_v2",
              "ewar_coverage": {"covered": 2, "total": 2, "fallback_years": []}},
        "b": {"seasons": {"2015": 0.5, "2016": 1.5, "2017": 0.1}, "source": "ewar_v2",
              "ewar_coverage": {"covered": 2, "total": 3, "fallback_years": [2015]}},
        "c": {"seasons": {"2022": 3.0}, "source": "bbref"},        # not rebased
        "d": {"seasons": {"2015": 0.2}, "source": "ewar_v2",
              "ewar_coverage": {"covered": 0, "total": 1, "fallback_years": [2015]}},
    }
    with _world():
        rep = war_source.coverage_report(table)
    assert rep["rows"] == 4
    assert rep["by_source"] == {"bbref": 1, "ewar_v2": 3}
    assert rep["season_values"] == 7
    assert rep["season_values_ewar"] == 4
    assert rep["share_ewar"] == round(4 / 7, 4)
    assert rep["fallback_years"] == {2015: 2}
    assert rep["artifact"] == {"model": "ewar_v2",
                               "generated_at": "2026-09-03T00:00:00",
                               "seasons": [2016, 2026]}
    assert war_source.coverage_report({}) ["share_ewar"] is None
    assert set(rep) == {"rows", "by_source", "season_values", "season_values_ewar",
                        "share_ewar", "fallback_years", "artifact"}


def test_career_war_table_is_served_as_stored(monkeypatch):
    """No re-transform on read: a not-yet-rebased row serves bWAR and its
    source field says so."""
    import storage
    stored = {"x": {"seasons": {"2024": 1.0}, "career_war": 1.0, "war_per_yr": 1.0,
                    "war_seasons_count": 1, "source": "bbref"}}
    monkeypatch.setattr(storage, "load_career_war", lambda: dict(stored))
    with _world():
        assert war_source.career_war_table() == stored
        assert war_source.career_war_table(provider="bwar") == stored


def test_name_index_is_provider_invariant():
    with _world():
        a = war_source.name_index()
        b = war_source.name_index(provider="bwar")
    assert a is b                       # one memo, identity is identity
    assert 660271 in a["shohei_ohtani"]
    assert a["shohei_ohtani"][660271]["years"] == {2023}


# --------------------------------------------------------------------------- #
# DataUnavailable, mlbam_for
# --------------------------------------------------------------------------- #
def test_missing_artifact_names_the_build_command(tmp_path, monkeypatch):
    monkeypatch.setattr(ewar, "OUT", tmp_path / "ewar.json")
    monkeypatch.setattr(ewar, "_CACHE", None)
    with pytest.raises(war_source.DataUnavailable) as ei:
        war_source.stint_frame("pit")
    msg = str(ei.value)
    assert war_source.EWAR_BUILD_CMD in msg
    assert "ewar.json" in msg and "provider='bwar'" in msg
    # writing the artifact makes it servable without a restart
    (tmp_path / "ewar.json").write_text(json.dumps(_EWAR), encoding="utf-8")
    war_source._require("ewar_v2")


def test_mlbam_for_resolution_order(tmp_path, monkeypatch):
    """player_photos first and never re-pointed; the two override files fill
    only what the table lacks, in order."""
    import storage
    monkeypatch.setattr(storage, "load_mlbam_player_keys",
                        lambda: {"100": "bound_key", "200": "shared_key"})
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps({"shared_key": 999, "override_key": 300,
                             "both_files": 400}), encoding="utf-8")
    b.write_text(json.dumps({"both_files": 401, "bust_key": 500}), encoding="utf-8")
    monkeypatch.setattr(war_source, "MLBAM_OVERRIDE_FILES", (a, b))
    monkeypatch.setattr(war_source, "_MLBAM_INDEX", None)
    idx = war_source.mlbam_index()
    assert idx == {"bound_key": 100, "shared_key": 200, "override_key": 300,
                   "both_files": 400, "bust_key": 500}
    assert war_source.mlbam_for("shared_key") == 200          # the binding wins
    assert war_source.mlbam_for("nobody") is None
    assert war_source.mlbam_for("") is None
    # memoised until refresh
    monkeypatch.setattr(storage, "load_mlbam_player_keys", lambda: {})
    assert war_source.mlbam_for("bound_key") == 100
    assert war_source.mlbam_index(refresh=True).get("bound_key") is None
    monkeypatch.setattr(war_source, "_MLBAM_INDEX", None)


def test_math_sanity_of_fixture():
    """The fixture's own arithmetic, so a failing test above is the facade."""
    assert math.isclose(6.2 + 3.8, 10.0)
    assert math.isclose(1.0 + 0.2, 1.2)
    assert math.isclose(1.9 + 0.6, 2.5)


# --- the served eWAR vintage (audit F10-02 / F11-01) -------------------------

def test_the_vintage_block_reports_absence_rather_than_zero():
    """Since 2026-09-11 (owner decision D11) the pipeline re-prices the live
    season nightly (tools/build_ewar.py --nightly, run_monthly d8b / 3-pre), so
    the flag reads the ARTIFACT: True on a nightly build, False on the committed
    hand build until the first night has run. The block must never report a
    clean zero it did not measure, which is the failure mode that let the
    staleness run unnoticed."""
    import war_source as ws
    v = ws.ewar_vintage()
    nightly = ws.ewar_cadence().get("mode") == "nightly"
    assert v["rebuilds_on_a_schedule"] is nightly, (
        "the flag, the artifact's cadence block and the glossary sentence move together")
    assert v["build_command"] == (ws.EWAR_NIGHTLY_CMD if nightly else ws.EWAR_BUILD_CMD)
    if not v["frames_read"]:
        assert v["stale"] is None and "reason" in v, (
            "with no frame read the drift is UNAVAILABLE, not zero")
    else:
        assert isinstance(v["stale"], bool)


def test_the_vintage_block_goes_stale_past_its_own_threshold(monkeypatch):
    """The tripwire itself. Seeded drift above the threshold must flip `stale`,
    because a disclosure that cannot fire is not a disclosure."""
    import war_source as ws
    seeded = {"bat": {"artifact_generated_at": "2026-09-03T12:35:09",
                      "bwar_revised": ws.EWAR_STALE_REVISED_MAX + 1,
                      "covered_player_seasons": 900},
              "pit": {"artifact_generated_at": "2026-09-03T12:35:09",
                      "bwar_revised": 0, "covered_player_seasons": 900}}
    monkeypatch.setattr(ws, "ewar_frame_diagnostics", lambda: seeded)
    v = ws.ewar_vintage(as_of="2026-09-10")
    assert v["stale"] is True
    assert "warning" in v and "rebuild" in v["warning"].lower()
    assert v["artifact_generated_at"] == "2026-09-03T12:35:09"

    seeded["bat"]["bwar_revised"] = 0
    clean = ws.ewar_vintage(as_of="2026-09-10")
    assert clean["stale"] is False and "warning" not in clean


def test_the_glossary_states_the_nightly_and_the_freeze():
    """The served sentence once said data/ewar.json 'rebuilds with the season'
    while nothing rebuilt it, and that claim made the staleness invisible. Since
    2026-09-11 the live season does rebuild nightly and completed seasons are
    frozen; the entry says exactly that, not the old whole-series claim."""
    import json
    from pathlib import Path
    g = json.loads((Path(__file__).parent / "data" / "glossary.json")
                   .read_text(encoding="utf-8"))
    entry = next((e for e in g["entries"] if e.get("id") == "ewar"), None)
    assert entry is not None
    meth = entry.get("methodology") or ""
    assert "rebuilds with the season" not in meth
    assert "DOES NOT REBUILD WITH THE SEASON" not in meth
    assert "THE LIVE SEASON REBUILDS NIGHTLY" in meth and "November 1" in meth


def test_the_three_year_war_rate_columns_share_the_one_year_basis():
    """F10-01, closed 2026-09-11 by owner decision: the lab re-pointed from bWAR
    to the served provider, so the 3-year WAR-rate columns and the 1-year
    columns beside them are one series. The 2026-09-10 disclosure that they
    were NOT on one scale is now false and must be gone; each entry states the
    shared basis instead. bullpen_export.join_war_rate_3yr enforces the same
    fact on the data (it refuses an artifact on another provider)."""
    import json
    from pathlib import Path
    g = json.loads((Path(__file__).parent / "data" / "glossary.json")
                   .read_text(encoding="utf-8"))
    by = {e.get("id"): e for e in g["entries"]}
    for slug in ("war_ip_plus_sp_3yr", "war_ip_plus_rp_3yr", "war_pa_plus_3yr"):
        meth = (by[slug].get("methodology") or "")
        assert "NOT on one scale" not in meth, f"{slug} still discloses a divergence"
        assert "measured on bWAR" not in meth, f"{slug} still claims a bWAR basis"
        assert "same eWAR series as the one-year" in meth, (
            f"{slug} does not state the basis it shares with the 1-year column")

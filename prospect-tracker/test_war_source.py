# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""war_source facade pin (lane B1, 2026-08-04d; eWAR epoch 2026-09-03 L2).

Provider 'bwar' must be a NO-OP refactor: the same payload, byte for byte,
whether a site calls the underlying stats/fa_ident/mlb_player_export function
directly over the raw bWAR frames (the OLD path) or goes through the facade
with provider='bwar' (the NEW path). If someone later reimplements a facade
function instead of delegating, these fail.

Also pinned: 'ewar_v2' is the DEFAULT provider everywhere (owner decision
2026-09-03); 'bwar' stays first in PROVIDERS as the input frame; an unknown
provider raises ValueError before any work; 'ewar_merged' raises
DataUnavailable NAMING the missing input; 'ewar_v2' raises DataUnavailable
only when data/ewar.json is missing, and then names the build command.

fWAR label epoch, precondition E3 part (3): 'fwar' is in PROVIDERS (after the
three above, 'bwar' still first), servable through every door on a fixture
vintage, NOT the default, and refuses with DataUnavailable naming the frozen
vintage and its build command when data/fwar_vintage.json is absent. The
'ewar_v2' and 'bwar' doors give the same answer with a vintage present or not.

Offline: the frame-equivalence tests inject a synthetic pybaseball module
into sys.modules (real mlbams, fabricated rows) AND a synthetic, EMPTY eWAR
payload into ewar._CACHE, so the default provider's transform is a value
no-op on these fixtures (the real artifact covers Trout, Ohtani and Skenes
and would move the numbers). Every downstream memo is cleared on the way in
AND out, so no fake data can leak into other tests. The full-table digest
reads the career_war sqlite table already on disk through
storage.load_career_war on both paths. Nothing fetches.
"""
from __future__ import annotations

import contextlib
import hashlib
import inspect
import json
import pathlib
import sys
import types

import pandas as pd
import pytest

import ewar
import fa_ident
import mlb_player_export
import stats
import storage
import war_source


# --------------------------------------------------------------------------- #
# synthetic war_daily frames (real mlbams: Ohtani 660271, Trout 545361,
# Skenes 694973). Deliberately exercises the two summing rules the bulk
# aggregate promises: multi-stint seasons sum within a side, and a two-way
# season sums across sides.
# --------------------------------------------------------------------------- #
_BAT_ROWS = [
    # Trout: one clean season + a two-stint season (1.9 + 0.6 must sum).
    {"name_common": "Mike Trout", "mlb_ID": 545361, "year_ID": 2023,
     "age": 31, "team_ID": "LAA", "PA": 507, "G": 119, "WAR": 2.9,
     "WAR_def": -0.4, "runs_position": -2.1, "pitcher": "N"},
    {"name_common": "Mike Trout", "mlb_ID": 545361, "year_ID": 2024,
     "age": 32, "team_ID": "LAA", "PA": 126, "G": 29, "WAR": 1.9,
     "WAR_def": -0.1, "runs_position": -0.7, "pitcher": "N"},
    {"name_common": "Mike Trout", "mlb_ID": 545361, "year_ID": 2024,
     "age": 32, "team_ID": "LAA", "PA": 40, "G": 10, "WAR": 0.6,
     "WAR_def": 0.0, "runs_position": -0.2, "pitcher": "N"},
    # Ohtani bats...
    {"name_common": "Shohei Ohtani", "mlb_ID": 660271, "year_ID": 2023,
     "age": 28, "team_ID": "LAA", "PA": 599, "G": 135, "WAR": 6.2,
     "WAR_def": -1.0, "runs_position": -8.0, "pitcher": "Y"},
]
_PIT_ROWS = [
    # ...and Ohtani pitches the same season (bat 6.2 + pit 3.8 = 10.0).
    {"name_common": "Shohei Ohtani", "mlb_ID": 660271, "year_ID": 2023,
     "age": 28, "team_ID": "LAA", "IPouts": 396, "G": 23, "WAR": 3.8},
    {"name_common": "Paul Skenes", "mlb_ID": 694973, "year_ID": 2024,
     "age": 22, "team_ID": "PIT", "IPouts": 399, "G": 23, "WAR": 4.3},
    {"name_common": "Paul Skenes", "mlb_ID": 694973, "year_ID": 2025,
     "age": 23, "team_ID": "PIT", "IPouts": 540, "G": 30, "WAR": 5.6},
]

_TARGETS = [
    ("shohei_ohtani", 660271, True),
    ("mike_trout", 545361, False),
    ("paul_skenes", 694973, True),
    ("nobody_in_mlb", 999999, False),   # must be silently absent
]

#: An artifact with no blocks: the ewar_v2 transform is a value no-op on it.
_EMPTY_EWAR = {"model": "ewar_v2", "generated_at": "2026-09-03T00:00:00",
               "seasons": [2016, 2026], "players": {}, "n_player_seasons": 0}


def _fake_pybaseball() -> types.ModuleType:
    mod = types.ModuleType("pybaseball")
    bat = pd.DataFrame(_BAT_ROWS)
    pit = pd.DataFrame(_PIT_ROWS)

    # The two frames differ in SHAPE, which is the whole reason the facade has
    # two doors: return_all=True carries the decomposition columns, the default
    # call carries only the narrow public set. The stub mirrors that so a test
    # can prove each door asks for the frame its callers were written against.
    _CONDENSED_COLS = ["mlb_ID", "year_ID", "name_common", "WAR"]

    def bwar_bat(return_all=False):
        return bat.copy() if return_all else bat[_CONDENSED_COLS].copy()

    def bwar_pitch(return_all=False):
        return pit.copy() if return_all else pit[_CONDENSED_COLS].copy()

    mod.bwar_bat = bwar_bat
    mod.bwar_pitch = bwar_pitch
    return mod


def _clear_memos() -> None:
    """Every lru_cache that can hold war_daily-derived state. Cleared going
    in (so the fake is actually read) and going out (so no fake data leaks
    into the rest of the suite)."""
    fa_ident.war_daily_index.cache_clear()
    with contextlib.suppress(Exception):
        import bullpen_export
        bullpen_export._side_war_by_season.cache_clear()
    with contextlib.suppress(Exception):
        import pal_export
        pal_export.load_bref_pitcher_war.cache_clear()
    war_source._EWAR_FRAME_DIAG.clear()
    war_source._FWAR_FRAME_DIAG.clear()


@contextlib.contextmanager
def _patched_pybaseball(payload: dict | None = None, vintage: dict | None = None):
    """Fake pybaseball, inject an eWAR payload (default: the EMPTY artifact),
    AND redirect the last-good cache to a throwaway dir.

    THE CACHE REDIRECT IS NOT HYGIENE, IT IS A PRODUCTION GUARD. stint_frame
    writes every successful read to .cache/war_daily/<side>.parquet as the
    last-good copy it serves when Baseball-Reference fails, which is the whole
    point of that cache: bwar_pitch has no disk cache of its own, so a failed
    pitching download is what blanked 79 of 228 free agents once already.
    Without this redirect these three-row fixtures overwrite that file, and
    since the deploy gate runs the suite ON THE BOX, the next real download
    failure there would fall back to a frame containing Trout, Ohtani and
    Skenes and quietly price the entire class off it.
    Measured 2026-08-07: the real cache held exactly those fixtures.

    THE PAYLOAD INJECTION IS THE SAME KIND OF GUARD in the other direction:
    ewar.load() is memoised in ewar._CACHE, so whatever this test leaves there
    is what the next test serves. Saved and restored."""
    import tempfile
    saved = sys.modules.get("pybaseball")
    sys.modules["pybaseball"] = _fake_pybaseball()
    saved_cache_dir = war_source._cache_dir
    saved_ewar = ewar._CACHE
    ewar._CACHE = _EMPTY_EWAR if payload is None else payload
    import fwar_vintage
    saved_vintage = fwar_vintage._CACHE
    fwar_vintage._CACHE = vintage
    tmp = tempfile.TemporaryDirectory()
    war_source._cache_dir = lambda: pathlib.Path(tmp.name)
    _clear_memos()
    try:
        yield
    finally:
        war_source._cache_dir = saved_cache_dir
        ewar._CACHE = saved_ewar
        fwar_vintage._CACHE = saved_vintage
        tmp.cleanup()
        if saved is None:
            sys.modules.pop("pybaseball", None)
        else:
            sys.modules["pybaseball"] = saved
        _clear_memos()


def _digest(payload) -> str:
    """Stable hash over sorted rows (sets become sorted lists first)."""
    def _norm(o):
        if isinstance(o, dict):
            return {str(k): _norm(v) for k, v in sorted(o.items(), key=lambda kv: str(kv[0]))}
        if isinstance(o, (set, frozenset)):
            return sorted(_norm(v) for v in o)
        if isinstance(o, (list, tuple)):
            return [_norm(v) for v in o]
        return o
    blob = json.dumps(_norm(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# THE PIN: provider 'bwar' is byte-identical to the old path
# --------------------------------------------------------------------------- #
def test_career_war_bulk_byte_identical_to_stats():
    with _patched_pybaseball():
        # the OLD path: stats over the raw bWAR frames (pre-epoch behaviour)
        with war_source._frames_pinned("bwar"):
            old = stats.fetch_career_war_bulk(_TARGETS, 2000, 2026)
        new = war_source.career_war_bulk(_TARGETS, 2000, 2026, provider="bwar")
    assert old == new
    old_bytes = json.dumps(old, sort_keys=True).encode()
    new_bytes = json.dumps(new, sort_keys=True).encode()
    assert old_bytes == new_bytes
    # the payload is real, not vacuously empty, and the summing rules held:
    assert "nobody_in_mlb" not in new
    assert new["shohei_ohtani"]["seasons"]["2023"] == 10.0     # bat+pit summed
    assert new["mike_trout"]["seasons"]["2024"] == 2.5         # stints summed
    assert new["paul_skenes"]["war_seasons_count"] == 2
    assert new["paul_skenes"]["source"] == "bbref"
    # and the bwar payload carries NONE of the eWAR epoch keys
    for row in new.values():
        assert "seasons_bwar" not in row and "ewar_coverage" not in row


def test_career_war_table_full_digest_identical_to_storage():
    """The full-table pin on the REAL career_war sqlite table: row count plus
    a stable hash over sorted rows, old path vs facade, BOTH providers (the
    table is served as stored; see career_war_table's docstring)."""
    old = storage.load_career_war()
    assert len(old) > 0, "career_war table is empty; the digest pin would be vacuous"
    for provider in ("bwar", "ewar_v2"):
        new = war_source.career_war_table(provider=provider)
        assert len(old) == len(new), provider
        assert _digest(old) == _digest(new), provider
        # spot-check a sample of real players end to end (sorted = deterministic)
        for key in sorted(new)[:25]:
            assert new[key] == old[key]
            assert set(new[key]) >= {"seasons", "career_war"}
    assert war_source.career_war_table() == old      # the default, too


def test_name_index_identical_to_fa_ident():
    with _patched_pybaseball():
        old = fa_ident.war_daily_index()
        fa_ident.war_daily_index.cache_clear()   # force a genuine rebuild
        new = war_source.name_index(provider="bwar")
    assert old is not new                        # two builds, not one memo
    assert old == new
    assert _digest(old) == _digest(new)
    assert 545361 in new["mike_trout"]
    # the index rides the displayed series: eWAR v2 on the patched bWAR frame, or,
    # since the eWAR v3 flip, FanGraphs' published 2023 total plus the headline's
    # own departure for the season (none at the flip; the xHEM+ half since the
    # park-matched flip 8be6f71e, owner EW3-53, which the departures table carries)
    if war_source.DISPLAY_PROVIDER == "ewar_v3":
        import ewar_v3
        import fwar_vintage
        want = fwar_vintage.season_totals()[(660271, 2023)]
        want += sum((ewar_v3.departures(None, "headline").get((660271, 2023)) or {}).values())
        assert abs(new["shohei_ohtani"][660271]["war"][2023] - want) < 1e-6
    else:
        assert new["shohei_ohtani"][660271]["war"][2023] == 10.0


def test_side_war_by_season_identical_to_mlb_player_export():
    with _patched_pybaseball():
        with war_source._frames_pinned("bwar"):
            old = mlb_player_export._war_daily()
        new = war_source.side_war_by_season(provider="bwar")
    assert old == new
    assert _digest(old) == _digest(new)
    # the side split survives (the two-way rule war_rate_plus depends on)
    assert new[660271][2023] == {"bat": 6.2, "pit": 3.8}


def test_stint_and_run_value_frames_are_the_raw_frames():
    with _patched_pybaseball():
        import pybaseball as pyb
        assert war_source.stint_frame("bat", provider="bwar").equals(
            pyb.bwar_bat(return_all=True))
        assert war_source.stint_frame("pit", provider="bwar").equals(
            pyb.bwar_pitch(return_all=True))
        rv = war_source.run_value_frame(provider="bwar")
        assert rv.equals(pyb.bwar_bat(return_all=True))
        # the decomposition columns build_def_history reads are present
        assert {"WAR_def", "runs_position", "PA", "pitcher"} <= set(rv.columns)
        # and the raw frame carries no epoch column
        assert "WAR_bwar" not in rv.columns


def test_condensed_frame_is_the_narrow_frame_and_not_the_stint_frame():
    """mlb_trade_lookup's WAR backfill reads pybaseball's DEFAULT call, a
    different column set from the stint frame. The two doors must stay
    distinct: a caller written against one KeyErrors on the other."""
    with _patched_pybaseball():
        import pybaseball as pyb
        for side, fn in (("bat", pyb.bwar_bat), ("pit", pyb.bwar_pitch)):
            cond = war_source.condensed_frame(side, provider="bwar")
            assert cond.equals(fn())
            # narrow by construction: the decomposition columns are ABSENT
            assert "WAR_def" not in cond.columns
            assert set(cond.columns) < set(
                war_source.stint_frame(side, provider="bwar").columns)
            # and it still carries what the backfill joins on
            assert {"mlb_ID", "year_ID", "WAR"} <= set(cond.columns)


# --------------------------------------------------------------------------- #
# the provider contract
# --------------------------------------------------------------------------- #
_PUBLIC_FNS = (
    war_source.career_war_bulk,
    war_source.career_war_table,
    war_source.side_war_by_season,
    war_source.stint_frame,
    war_source.condensed_frame,
    war_source.run_value_frame,
    war_source.name_index,
)


def _call(fn, provider):
    kwargs = {"provider": provider}
    if fn is war_source.career_war_bulk:
        return fn([("x", 1, False)], 2000, 2026, **kwargs)
    if fn in (war_source.stint_frame, war_source.condensed_frame):
        return fn("bat", **kwargs)
    return fn(**kwargs)


def test_fwar_is_the_default_provider_everywhere():
    """Owner decisions O1 and O2 (2026-09-17) and the fWAR label epoch's step D + U
    (2026-10-03): the LABEL WAR is published fWAR, so the facade default is 'fwar'.
    The DISPLAYED WAR stays eWAR v2 (owner answer EPOCH-Q4), named explicitly by
    every display door (test_epoch_display_doors.py). 'bwar' stays first in
    PROVIDERS because it is the input frame."""
    assert war_source.DEFAULT_PROVIDER == "fwar"
    assert war_source.DISPLAY_PROVIDER == ("ewar_v3" if war_source.EWAR_V3_LIVE else "ewar_v2")
    assert war_source.PROVIDERS == ("bwar", "ewar_v2", "ewar_merged", "fwar", "ewar_v3", "ewar_core")
    for fn in _PUBLIC_FNS:
        sig = inspect.signature(fn)
        assert sig.parameters["provider"].default == "fwar", fn.__name__
        assert sig.parameters["provider"].kind is inspect.Parameter.KEYWORD_ONLY, \
            f"{fn.__name__}: provider must be keyword-only"


def test_unknown_provider_raises_before_any_work():
    for fn in _PUBLIC_FNS:
        try:
            _call(fn, "no_such_provider")
        except ValueError as e:
            assert "no_such_provider" in str(e), fn.__name__
        else:
            raise AssertionError(f"{fn.__name__} accepted an unknown provider")


def test_ewar_merged_raises_loud_dataunavailable():
    assert issubclass(war_source.DataUnavailable, RuntimeError)
    for fn in _PUBLIC_FNS:
        try:
            _call(fn, "ewar_merged")
        except war_source.DataUnavailable as e:
            msg = str(e)
            for token in ("parquet", "BENCHMARK_MANIFEST"):
                assert token in msg, (fn.__name__, token)
        else:
            raise AssertionError(f"{fn.__name__} served provider 'ewar_merged'")


def test_ewar_v2_raises_dataunavailable_only_when_the_artifact_is_missing(
        tmp_path, monkeypatch):
    """With no data/ewar.json and nothing memoised, every public function
    refuses BEFORE any work and names the build command. Nothing falls back
    to bWAR on its own."""
    monkeypatch.setattr(ewar, "OUT", tmp_path / "absent" / "ewar.json")
    monkeypatch.setattr(ewar, "_CACHE", None)
    for fn in _PUBLIC_FNS:
        try:
            _call(fn, "ewar_v2")
        except war_source.DataUnavailable as e:
            msg = str(e)
            for token in ("ewar.json", "build_ewar.py", "--write"):
                assert token in msg, (fn.__name__, token)
        else:
            raise AssertionError(
                f"{fn.__name__} served 'ewar_v2' with the artifact missing")
    # and a memoised payload alone makes it servable again (the test seam)
    monkeypatch.setattr(ewar, "_CACHE", _EMPTY_EWAR)
    war_source._require("ewar_v2")


def test_stint_frame_rejects_unknown_side():
    try:
        war_source.stint_frame("both")
    except ValueError as e:
        assert "both" in str(e)
    else:
        raise AssertionError("stint_frame accepted an unknown side")


# --------------------------------------------------------------------------- #
# provider 'fwar' (fWAR label epoch, precondition E3 part 3), on a fixture
# vintage. The incumbent artifact re-prices Skenes 2024 (4.3 -> 4.6) so the
# kept eWAR v2 series is visibly not bWAR.
# --------------------------------------------------------------------------- #
_EWAR_FIX = {"model": "ewar_v2", "generated_at": "2026-09-03T00:00:00",
             "seasons": [2016, 2026], "n_player_seasons": 1,
             "players": {"694973": {"2024": {"ew": 4.6, "bw": 4.3, "ewp": 4.6, "bwp": 4.3}}}}


def _grp(rows: dict, status: str = "frozen") -> dict:
    return {"status": status, "fields": ["war", "rar", "numTeams"],
            "rows": {str(k): [v, None, 1] for k, v in rows.items()}}


_VINTAGE_FIX = {
    "schema": "fwar_vintage/1", "vintage_id": "2026-10-05-0123456789ab",
    "seasons": {
        "2023": {"hitting": _grp({545361: 2.81, 660271: 5.95}),
                 "pitching": _grp({660271: 3.04})},
        # the two-stint Trout season; the Skenes blank batting line is a 0.0 the feed carries
        "2024": {"hitting": _grp({545361: 1.7, 694973: 0.0}),
                 "pitching": _grp({694973: 4.27})},
        # a mixed season (pitching absent): served by no door, the incumbent stays
        "2010": {"hitting": _grp({545361: 9.9}), "pitching": _grp({}, "absent")},
    },
}


def test_fwar_build_command_is_the_vintage_builders():
    import fwar_vintage
    assert war_source.FWAR_BUILD_CMD == fwar_vintage.BUILD_CMD


def test_fwar_raises_dataunavailable_when_the_vintage_is_absent(tmp_path, monkeypatch):
    import fwar_vintage
    monkeypatch.setattr(fwar_vintage, "VINTAGE_PATH", tmp_path / "absent" / "fwar_vintage.json")
    monkeypatch.setattr(fwar_vintage, "_CACHE", None)
    for fn in _PUBLIC_FNS:
        try:
            _call(fn, "fwar")
        except war_source.DataUnavailable as e:
            msg = str(e)
            for token in ("fwar_vintage.json", "build_fwar_vintage.py", "EPOCH_D9_FREEZE",
                          "never reads the live sabermetrics feed"):
                assert token in msg, (fn.__name__, token)
        else:
            raise AssertionError(f"{fn.__name__} served 'fwar' with the vintage missing")
    # the vintage alone is not enough: the incumbent's artifact must exist too
    monkeypatch.setattr(fwar_vintage, "_CACHE", _VINTAGE_FIX)
    monkeypatch.setattr(ewar, "OUT", tmp_path / "absent" / "ewar.json")
    monkeypatch.setattr(ewar, "_CACHE", None)
    try:
        war_source._require("fwar")
    except war_source.DataUnavailable as e:
        assert "incumbent" in str(e) and "ewar.json" in str(e)
    else:
        raise AssertionError("'fwar' served without the incumbent's artifact")
    monkeypatch.setattr(ewar, "_CACHE", _EMPTY_EWAR)
    war_source._require("fwar")


def test_fwar_career_war_bulk_serves_fwar_and_keeps_both_incumbent_series():
    with _patched_pybaseball(_EWAR_FIX, _VINTAGE_FIX):
        inc = war_source.career_war_bulk(_TARGETS, 2000, 2026, provider="ewar_v2")
        new = war_source.career_war_bulk(_TARGETS, 2000, 2026, provider="fwar")
    assert set(new) == set(inc) and "nobody_in_mlb" not in new
    o, t, s = new["shohei_ohtani"], new["mike_trout"], new["paul_skenes"]
    assert o["seasons"] == {"2023": 8.99}                  # 5.95 + 3.04, the two groups summed
    assert t["seasons"] == {"2023": 2.81, "2024": 1.7}
    assert s["seasons"] == {"2024": 4.27, "2025": 5.6}     # 2025 is not in the vintage
    for key, row in new.items():
        assert row["source"] == "fwar"
        assert row["seasons_ewar_v2"] == inc[key]["seasons"]       # the incumbent, bit for bit
        assert row["seasons_bwar"] == inc[key]["seasons_bwar"]
        assert row["career_war"] == round(sum(row["seasons"].values()), 2)
        assert row["war_seasons_count"] == len(row["seasons"])
    assert s["seasons_ewar_v2"] == {"2024": 4.6, "2025": 5.6}
    assert s["seasons_bwar"] == {"2024": 4.3, "2025": 5.6}
    cov = s["fwar_coverage"]
    assert cov["vintage_id"] == "2026-10-05-0123456789ab" and cov["mlbam"] == 694973
    assert cov["n_fwar"] == 1 and cov["n_fallback_pre"] == 1 and cov["fallback_pre_years"] == [2025]
    assert cov["war_basis"] == "mixed" and cov["incumbent_source"] == "ewar_v2"
    assert new["mike_trout"]["fwar_coverage"]["war_basis"] == "fwar"


def test_the_shared_fwar_transform_contract():
    import fwar_vintage
    idx = war_source.fwar_index(_VINTAGE_FIX)
    assert idx["fwar_years"] == {2023, 2024}                # 2010 is mixed: not served
    seasons, rec = war_source.fwar_seasons_from_incumbent(
        {"2010": 3.3, "2023": 2.0, "2024": 1.1}, 545361, idx)
    assert seasons == {"2010": 3.3, "2023": 2.81, "2024": 1.7}
    assert rec["n_fallback_pre"] == 1 and rec["fallback_pre_years"] == [2010]
    # an fwar season with no feed row for the player is an in-window fallback
    seasons, rec = war_source.fwar_seasons_from_incumbent({"2023": 0.4}, 999999, idx)
    assert seasons == {"2023": 0.4} and rec["fallback_post_years"] == [2023]
    # no mlbam: every season keeps the incumbent
    seasons, rec = war_source.fwar_seasons_from_incumbent({"2023": 0.4}, None, idx)
    assert seasons == {"2023": 0.4} and rec["n_fwar"] == 0 and rec["war_basis"] == "mixed"
    assert fwar_vintage.mixed_seasons(_VINTAGE_FIX) == [2010]


def test_fwar_career_war_table_is_the_table_as_stored():
    import fwar_vintage
    saved = fwar_vintage._CACHE
    fwar_vintage._CACHE = _VINTAGE_FIX
    try:
        assert _digest(war_source.career_war_table(provider="fwar")) == \
            _digest(storage.load_career_war())
    finally:
        fwar_vintage._CACHE = saved


def test_fwar_side_war_by_season_overlays_the_vintage_per_side():
    with _patched_pybaseball(_EWAR_FIX, _VINTAGE_FIX):
        inc = war_source.side_war_by_season(provider="ewar_v2")
        new = war_source.side_war_by_season(provider="fwar")
        diag = war_source.fwar_frame_diagnostics()
    assert new[660271][2023] == {"bat": 5.95, "pit": 3.04}
    assert new[545361][2024] == {"bat": 1.7}
    assert new[694973][2024] == {"pit": 4.27}               # the 0.0 batting line is not added
    assert new[694973][2025] == inc[694973][2025]           # outside the vintage: incumbent
    assert inc[694973][2024] == {"pit": 4.6}
    assert diag["bat"]["skipped_blank"] == 1 and diag["pit"]["covered_player_seasons"] == 2
    assert diag["bat"]["vintage_id"] == "2026-10-05-0123456789ab"


def test_fwar_stint_frame_splits_the_season_total_like_ewar_v2():
    with _patched_pybaseball(_EWAR_FIX, _VINTAGE_FIX):
        bat = war_source.stint_frame("bat", provider="fwar")
        pit = war_source.stint_frame("pit", provider="fwar")
        rv = war_source.run_value_frame("bat", provider="fwar")
        diag = war_source.fwar_frame_diagnostics()
    assert {"WAR", "WAR_bwar", "WAR_ewar_v2"} <= set(bat.columns)
    t24 = bat[(bat.mlb_ID == 545361) & (bat.year_ID == 2024)]
    # bWAR 1.9 + 0.6 = 2.5, fWAR 1.7: the -0.8 delta splits by PA 126 : 40
    want = [1.9 + (1.7 - 2.5) * 126 / 166, 0.6 + (1.7 - 2.5) * 40 / 166]
    assert t24["WAR"].tolist() == pytest.approx(want, abs=1e-12)
    assert abs(t24["WAR"].sum() - 1.7) < 1e-12
    assert t24["WAR_bwar"].tolist() == [1.9, 0.6]
    sk = pit[(pit.mlb_ID == 694973)].set_index("year_ID")
    assert sk.loc[2024, "WAR"] == pytest.approx(4.27) and sk.loc[2024, "WAR_ewar_v2"] == 4.6
    assert sk.loc[2024, "WAR_bwar"] == 4.3
    assert sk.loc[2025, "WAR"] == sk.loc[2025, "WAR_ewar_v2"] == 5.6   # not in the vintage
    assert rv.equals(bat)
    # bat: Trout 2023, Trout 2024, Ohtani 2023 placed; the Skenes 0.0 bat line has no row
    assert diag["bat"]["covered_player_seasons"] == 3 and diag["bat"]["vintage_unplaced"] == 1
    assert diag["pit"]["covered_player_seasons"] == 2


def test_fwar_condensed_frame_splits_equally_without_exposure():
    with _patched_pybaseball(_EWAR_FIX, _VINTAGE_FIX):
        cond = war_source.condensed_frame("bat", provider="fwar")
    t24 = cond[(cond.mlb_ID == 545361) & (cond.year_ID == 2024)]
    assert t24["WAR"].tolist() == pytest.approx([1.9 - 0.4, 0.6 - 0.4], abs=1e-12)
    assert "WAR_def" not in cond.columns and "WAR_ewar_v2" in cond.columns


def test_fwar_name_index_is_the_identity_index():
    with _patched_pybaseball(_EWAR_FIX, _VINTAGE_FIX):
        a = war_source.name_index(provider="fwar")
        b = war_source.name_index(provider="ewar_v2")
    assert a is b


def test_ewar_v2_and_bwar_doors_do_not_see_the_vintage():
    """The 'ewar_v2' and 'bwar' answers with a vintage present equal the answers
    without one, door by door (the refactor's byte-identity on the real frames
    is the E3 receipt; this pins that the vintage cannot leak in)."""
    outs = []
    for vintage in (None, _VINTAGE_FIX):
        with _patched_pybaseball(_EWAR_FIX, vintage):
            got = {}
            for prov in ("ewar_v2", "bwar"):
                got[prov, "bulk"] = war_source.career_war_bulk(_TARGETS, 2000, 2026, provider=prov)
                got[prov, "side"] = war_source.side_war_by_season(provider=prov)
                for side in ("bat", "pit"):
                    got[prov, "stint", side] = war_source.stint_frame(side, provider=prov)
                    got[prov, "cond", side] = war_source.condensed_frame(side, provider=prov)
            outs.append(got)
    for k in outs[0]:
        a, b = outs[0][k], outs[1][k]
        if isinstance(a, pd.DataFrame):
            assert a.equals(b) and list(a.columns) == list(b.columns), k
            assert "WAR_ewar_v2" not in a.columns, k
        else:
            assert json.dumps(a, sort_keys=True, default=str) == \
                json.dumps(b, sort_keys=True, default=str), k
    sk = outs[1]["ewar_v2", "stint", "pit"]
    assert sk[(sk.mlb_ID == 694973) & (sk.year_ID == 2024)]["WAR"].tolist() == [4.6]
    for row in outs[1]["ewar_v2", "bulk"].values():
        assert row["source"] == "ewar_v2" and "seasons_ewar_v2" not in row

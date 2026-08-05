# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""war_source facade pin (lane B1, 2026-08-04d).

Provider 'bwar' must be a NO-OP refactor: the same payload, byte for byte,
whether a site calls the underlying stats/fa_ident/mlb_player_export function
directly (the OLD path) or goes through the facade (the NEW path). If someone
later reimplements a facade function instead of delegating, these fail.

Also pinned: 'bwar' is the default provider everywhere; an unknown provider
raises ValueError before any work; the declared-but-absent providers
('ewar_v2', 'ewar_merged') raise DataUnavailable with a message NAMING the
missing input, so nothing can silently fall back to bWAR.

Offline: the frame-equivalence tests inject a synthetic pybaseball module
into sys.modules (real mlbams, fabricated rows) and clear every downstream
memo on the way in AND out, so no fake data can leak into other tests. The
full-table digest reads the career_war sqlite table already on disk through
storage.load_career_war on both paths. Nothing fetches.
"""
from __future__ import annotations

import contextlib
import hashlib
import inspect
import json
import sys
import types

import pandas as pd

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


@contextlib.contextmanager
def _patched_pybaseball():
    saved = sys.modules.get("pybaseball")
    sys.modules["pybaseball"] = _fake_pybaseball()
    _clear_memos()
    try:
        yield
    finally:
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
        old = stats.fetch_career_war_bulk(_TARGETS, 2000, 2026)
        new = war_source.career_war_bulk(_TARGETS, 2000, 2026)
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


def test_career_war_table_full_digest_identical_to_storage():
    """The full-table pin on the REAL career_war sqlite table: row count plus
    a stable hash over sorted rows, old path vs facade."""
    old = storage.load_career_war()
    new = war_source.career_war_table()
    assert len(old) == len(new)
    assert len(new) > 0, "career_war table is empty; the digest pin would be vacuous"
    assert _digest(old) == _digest(new)
    # spot-check a sample of real players end to end (sorted = deterministic)
    for key in sorted(new)[:25]:
        assert new[key] == old[key]
        assert set(new[key]) >= {"seasons", "career_war"}


def test_name_index_identical_to_fa_ident():
    with _patched_pybaseball():
        old = fa_ident.war_daily_index()
        fa_ident.war_daily_index.cache_clear()   # force a genuine rebuild
        new = war_source.name_index()
    assert old is not new                        # two builds, not one memo
    assert old == new
    assert _digest(old) == _digest(new)
    assert 545361 in new["mike_trout"]
    assert new["shohei_ohtani"][660271]["war"][2023] == 10.0


def test_side_war_by_season_identical_to_mlb_player_export():
    with _patched_pybaseball():
        old = mlb_player_export._war_daily()
        new = war_source.side_war_by_season()
    assert old == new
    assert _digest(old) == _digest(new)
    # the side split survives (the two-way rule war_rate_plus depends on)
    assert new[660271][2023] == {"bat": 6.2, "pit": 3.8}


def test_stint_and_run_value_frames_are_the_raw_frames():
    with _patched_pybaseball():
        import pybaseball as pyb
        assert war_source.stint_frame("bat").equals(pyb.bwar_bat(return_all=True))
        assert war_source.stint_frame("pit").equals(pyb.bwar_pitch(return_all=True))
        rv = war_source.run_value_frame()
        assert rv.equals(pyb.bwar_bat(return_all=True))
        # the decomposition columns build_def_history reads are present
        assert {"WAR_def", "runs_position", "PA", "pitcher"} <= set(rv.columns)


def test_condensed_frame_is_the_narrow_frame_and_not_the_stint_frame():
    """mlb_trade_lookup's WAR backfill reads pybaseball's DEFAULT call, a
    different column set from the stint frame. The two doors must stay
    distinct: a caller written against one KeyErrors on the other."""
    with _patched_pybaseball():
        import pybaseball as pyb
        for side, fn in (("bat", pyb.bwar_bat), ("pit", pyb.bwar_pitch)):
            cond = war_source.condensed_frame(side)
            assert cond.equals(fn())
            # narrow by construction: the decomposition columns are ABSENT
            assert "WAR_def" not in cond.columns
            assert set(cond.columns) < set(war_source.stint_frame(side).columns)
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


def test_bwar_is_the_default_provider_everywhere():
    assert war_source.DEFAULT_PROVIDER == "bwar"
    assert war_source.PROVIDERS[0] == "bwar"
    for fn in _PUBLIC_FNS:
        sig = inspect.signature(fn)
        assert sig.parameters["provider"].default == "bwar", fn.__name__
        assert sig.parameters["provider"].kind is inspect.Parameter.KEYWORD_ONLY, \
            f"{fn.__name__}: provider must be keyword-only"


def test_unknown_provider_raises_before_any_work():
    for fn in _PUBLIC_FNS:
        try:
            _call(fn, "fwar")
        except ValueError as e:
            assert "fwar" in str(e), fn.__name__
        else:
            raise AssertionError(f"{fn.__name__} accepted an unknown provider")


def test_declared_providers_raise_loud_dataunavailable():
    assert issubclass(war_source.DataUnavailable, RuntimeError)
    for provider, must_name in (
        ("ewar_v2", ("ewar.json", "Stage-2")),
        ("ewar_merged", ("parquet", "BENCHMARK_MANIFEST")),
    ):
        for fn in _PUBLIC_FNS:
            try:
                _call(fn, provider)
            except war_source.DataUnavailable as e:
                msg = str(e)
                for token in must_name:
                    assert token in msg, (fn.__name__, provider, token)
            else:
                raise AssertionError(f"{fn.__name__} served provider {provider!r}")


def test_stint_frame_rejects_unknown_side():
    try:
        war_source.stint_frame("both")
    except ValueError as e:
        assert "both" in str(e)
    else:
        raise AssertionError("stint_frame accepted an unknown side")

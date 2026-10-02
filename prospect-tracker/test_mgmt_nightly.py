# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The In-Game Management nightly (mgmt_nightly.py, run_daily step 9e-pre0e), pinned.

Owner answer 2026-09-25 (census M10-05): the play corpus refreshes nightly for the
OPEN season only, completed seasons stay frozen, an unchanged win-probability corpus
skips the chain with a reason, and a rerun changes nothing. Every test here builds
its own corpus under tmp_path from the synthetic games test_pbp_corpus uses; nothing
writes under data/ or .cache/.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import mgmt_nightly as MN  # noqa: E402
import mgmt_shards  # noqa: E402
from test_pbp_corpus import _game  # noqa: E402
from tools import build_pbp_corpus as bpc  # noqa: E402

OPEN = 2026


def _cache(tmp_path, games):
    cache = tmp_path / "win_prob"
    cache.mkdir(parents=True, exist_ok=True)
    for pk, season in games:
        (cache / f"{pk}.json").write_text(json.dumps(_game(pk, season)), encoding="utf-8")
    return cache


def _frozen_corpus(tmp_path):
    """A corpus whose 2018 season is complete, plus one 2026 game in the cache."""
    pytest.importorskip("pyarrow")
    cache = _cache(tmp_path, [(529406, 2018), (529407, 2018)])
    out = tmp_path / "pbp_corpus"
    bpc.build(cache, out, seasons={2018})
    _cache(tmp_path, [(776001, OPEN)])
    return cache, out


def _bytes(out, season):
    return {t: bpc.table_path(out, t, season).read_bytes() for t in bpc.TABLES}


# --------------------------------------------------------------------------
# the corpus step
# --------------------------------------------------------------------------

def test_the_open_season_is_built_then_a_rerun_is_a_no_op(tmp_path):
    cache, out = _frozen_corpus(tmp_path)
    first = bpc.refresh_open_season(cache, out, OPEN)
    assert first["status"] == "rebuilt" and first["games"] == 1
    tables = _bytes(out, OPEN)
    manifest = bpc.manifest_path(out).read_bytes()
    again = bpc.refresh_open_season(cache, out, OPEN)
    assert again["status"] == "unchanged", again
    assert again["fingerprint"] == first["fingerprint"]
    assert _bytes(out, OPEN) == tables, "an unchanged night rewrote the open season"
    assert bpc.manifest_path(out).read_bytes() == manifest


def test_a_refetch_of_identical_bytes_is_not_a_change(tmp_path):
    """The win_prob fetcher re-fetches on a TTL; same content, new mtime."""
    cache, out = _frozen_corpus(tmp_path)
    bpc.refresh_open_season(cache, out, OPEN)
    p = cache / "776001.json"
    st = p.stat()
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    assert bpc.refresh_open_season(cache, out, OPEN)["status"] == "unchanged"


def test_a_new_open_season_game_rebuilds_the_open_season(tmp_path):
    cache, out = _frozen_corpus(tmp_path)
    bpc.refresh_open_season(cache, out, OPEN)
    _cache(tmp_path, [(776002, OPEN)])
    res = bpc.refresh_open_season(cache, out, OPEN)
    assert res["status"] == "rebuilt" and res["games_before"] == 1 and res["games"] == 2
    man = json.loads(bpc.manifest_path(out).read_text(encoding="utf-8"))
    assert man["seasons"][str(OPEN)]["source_fingerprint"] == res["fingerprint"]
    assert man["seasons"][str(OPEN)]["complete"] is True


def test_a_pruned_cache_never_shrinks_the_built_open_season(tmp_path):
    """The disk preflight prunes win_prob; fewer files is not new data."""
    cache, out = _frozen_corpus(tmp_path)
    _cache(tmp_path, [(776002, OPEN)])
    bpc.refresh_open_season(cache, out, OPEN)
    tables = _bytes(out, OPEN)
    (cache / "776002.json").unlink()
    res = bpc.refresh_open_season(cache, out, OPEN)
    assert res["status"] == "cache_shrank" and res["games"] == 2
    assert _bytes(out, OPEN) == tables


def test_a_completed_season_is_never_rewritten(tmp_path):
    """Its tables keep their bytes, and a late file of that season is not folded in."""
    cache, out = _frozen_corpus(tmp_path)
    before = _bytes(out, 2018)
    row_before = json.loads(bpc.manifest_path(out).read_text(encoding="utf-8"))["seasons"]["2018"]
    _cache(tmp_path, [(529408, 2018)])
    res = bpc.refresh_open_season(cache, out, OPEN)
    assert res["status"] == "rebuilt"
    assert res["frozen_seasons"] == [2018]
    assert res["other_season_files_not_in_corpus"] == 1
    assert _bytes(out, 2018) == before
    man = json.loads(bpc.manifest_path(out).read_text(encoding="utf-8"))
    assert man["seasons"]["2018"] == row_before


def test_no_completed_season_on_disk_writes_nothing(tmp_path):
    """The deploy box carries no corpus: building the open season alone there would
    leave a one-season corpus and a one-season ledger behind."""
    pytest.importorskip("pyarrow")
    cache = _cache(tmp_path, [(776001, OPEN)])
    out = tmp_path / "pbp_corpus"
    res = bpc.refresh_open_season(cache, out, OPEN)
    assert res["status"] == "no_frozen_corpus"
    assert not out.exists()


# --------------------------------------------------------------------------
# the chain and its skip
# --------------------------------------------------------------------------

def _stamp(data_dir, built_at):
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in MN.STAMPED:
        (data_dir / name).write_text(json.dumps({"corpus_built_at": built_at}), encoding="utf-8")


def test_an_unchanged_corpus_skips_the_chain_and_says_why(tmp_path):
    cache, out = _frozen_corpus(tmp_path)
    data = tmp_path / "data"
    calls = []

    def downstream(season, say):
        calls.append(season)
        _stamp(data, MN.manifest_built_at(out))
        return {"n_decisions": 1}

    first = MN.run(season=OPEN, cache_dir=cache, corpus=out, data_dir=data,
                   downstream=downstream, log_fn=lambda m: None)
    assert first["status"] == "rebuilt" and calls == [OPEN]
    second = MN.run(season=OPEN, cache_dir=cache, corpus=out, data_dir=data,
                    downstream=downstream, log_fn=lambda m: None)
    assert second["status"] == "skipped" and calls == [OPEN]
    assert "unchanged" in second["why"]


def test_an_artifact_from_another_corpus_build_is_rebuilt_on_an_unchanged_night(tmp_path):
    """A failed night, or a hand corpus rebuild without the chain, is caught up."""
    cache, out = _frozen_corpus(tmp_path)
    data = tmp_path / "data"
    bpc.refresh_open_season(cache, out, OPEN)
    _stamp(data, "2026-01-01T00:00:00+00:00")
    calls = []
    res = MN.run(season=OPEN, cache_dir=cache, corpus=out, data_dir=data,
                 downstream=lambda s, say: calls.append(s) or {}, log_fn=lambda m: None)
    assert res["corpus"]["status"] == "unchanged"
    assert res["status"] == "rebuilt" and calls == [OPEN]
    assert "management_running.json" in res["why"]


def test_no_corpus_on_the_machine_is_a_skip_not_a_build(tmp_path):
    pytest.importorskip("pyarrow")
    cache = _cache(tmp_path, [(776001, OPEN)])
    res = MN.run(season=OPEN, cache_dir=cache, corpus=tmp_path / "none",
                 data_dir=tmp_path / "data",
                 downstream=lambda s, say: pytest.fail("chain ran without a corpus"),
                 log_fn=lambda m: None)
    assert res["status"] == "skipped" and "stand" in res["why"]


# --------------------------------------------------------------------------
# the shard writer
# --------------------------------------------------------------------------

def _rows(season, dv_cell=-0.02):
    return [{"season": season, "club": "NYY", "family": "bunt", "kind": "sac_bunt",
             "game_pk": 1, "ab": 4, "idx": -1, "date": f"{season}-04-01", "opp": "BOS",
             "home": True, "half": "bottom", "inning": 1, "outs": 0, "base": 1,
             "score_diff": 0, "li": 1.1, "mwpa": 0.01, "dv_cell": dv_cell}]


def test_a_rerun_of_the_shard_writer_leaves_every_byte_alone(tmp_path):
    mgmt_shards.write_season(_rows(OPEN), tmp_path, OPEN)
    p = tmp_path / mgmt_shards.shard_name(OPEN, "NYY")
    before = p.read_bytes()
    os.utime(p, ns=(0, 0))
    idx = mgmt_shards.write_season(_rows(OPEN), tmp_path, OPEN)
    assert p.read_bytes() == before
    assert p.stat().st_mtime_ns == 0, "an identical shard was rewritten"
    assert idx == [{"season": OPEN, "club": "NYY", "n": 1, "bytes": len(before)}]


def test_a_frozen_seasons_shard_bytes_do_not_change(tmp_path):
    """The bunt cells are pooled over every season, so a growing open season moves
    dv_cell on a completed season's rows; a frozen shard keeps its bytes anyway."""
    mgmt_shards.write_season(_rows(2018), tmp_path, 2018)
    p = tmp_path / mgmt_shards.shard_name(2018, "NYY")
    before = p.read_bytes()
    idx = mgmt_shards.write_season(_rows(2018, dv_cell=-0.02001), tmp_path, 2018, frozen=True)
    assert p.read_bytes() == before
    assert idx == [{"season": 2018, "club": "NYY", "n": 1, "bytes": len(before)}]
    mgmt_shards.write_season(_rows(2018, dv_cell=-0.02001), tmp_path, 2018)
    assert p.read_bytes() != before, "an open season's moved row must be written"


def test_a_frozen_shard_missing_from_disk_is_written(tmp_path):
    mgmt_shards.write_season(_rows(2018), tmp_path, 2018, frozen=True)
    assert (tmp_path / mgmt_shards.shard_name(2018, "NYY")).exists()


# --------------------------------------------------------------------------
# the wiring
# --------------------------------------------------------------------------

def test_the_step_is_wired_into_the_daily_before_its_readers():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    daily = src[src.index("def run_daily("):src.index("\ndef ", src.index("def run_daily(") + 10)]
    step = daily.index('_step("9e-pre0e. In-Game Management nightly (management_board.json)')
    assert daily.index('_step("9e-pre0. Refresh team leaderboards') < step
    assert daily.index('_step("9e-pre. Leaderboard vintage snapshot') < step
    assert step < daily.index('_step("9e. Betting odds snapshot')
    assert step < daily.index('_step("6b7d. Franchise board')
    assert 'mgmt_nightly as _mgn' in daily
    assert '_hb.record("mgmt_nightly", ok=True' in daily
    assert '_hb.record("mgmt_nightly", ok=False' in daily
    assert '_record_ingest("mgmt_nightly", True' in daily
    assert '_record_ingest("mgmt_nightly", False' in daily
    i = src.index("SCHEDULED_EXPORTS = (")
    assert '"mgmt_nightly"' in src[i:src.index("\n)\n", i)]
    assert "_mdc.build(freeze_before=date.today().year)" in src


def test_the_nightly_freezes_completed_seasons_in_the_ledger():
    src = (ROOT / "mgmt_nightly.py").read_text(encoding="utf-8")
    assert "mgmt_decisions.build(freeze_before=season)" in src
    md = (ROOT / "mgmt_decisions.py").read_text(encoding="utf-8")
    assert "frozen=freeze_before is not None and int(season) < int(freeze_before)" in md


# --------------------------------------------------------------------------
# the cache the corpus is read from
# --------------------------------------------------------------------------

def test_a_play_list_cut_off_before_the_end_is_not_served_as_final(tmp_path, monkeypatch):
    """Game 823062 was cached an hour after first pitch with one pre-game advisory and
    the date TTL served it as final; a list that does not end the game is re-fetched."""
    import mlb_leverage as ML
    assert ML.plays_end_the_game([{"homeTeamWinProbability": 0.0}])
    assert ML.plays_end_the_game([{"homeTeamWinProbability": 100}])
    assert not ML.plays_end_the_game([{"homeTeamWinProbability": 50.0}])
    assert not ML.plays_end_the_game([])
    monkeypatch.setattr(ML, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(ML.time, "sleep", lambda s: None)
    full = [{"homeTeamWinProbability": 50.0}, {"homeTeamWinProbability": 100.0}]
    calls = []

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return full

    monkeypatch.setattr(ML.feed_cache.SESSION, "get",
                        lambda *a, **k: calls.append(a) or Resp())
    (tmp_path / "1.json").write_text(json.dumps([{"homeTeamWinProbability": 50.0}]),
                                     encoding="utf-8")
    assert ML.get_win_probability(1, game_date="2026-07-07") == full
    assert len(calls) == 1
    assert ML.get_win_probability(1, game_date="2026-07-07") == full
    assert len(calls) == 1, "a finished game is served from the cache"

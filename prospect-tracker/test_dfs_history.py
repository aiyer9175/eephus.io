# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Tests for the DFS slate archive (dfs_export._archive_slate / _prune_archive,
2026-08-16). Fixture payloads, temp dirs, no network, no corpus.

The archive exists so a later backtest can grade slate pricing: data/dfs.json
is overwritten daily and the model registry's dfs_slate_pricing row records
that no history was being kept. These tests pin: a healthy build writes one
compact file per slate date, an empty or refused payload writes nothing, the
compact rows carry the grading keys, retention prunes past the documented
bound, and refresh() routes a published board through the archive."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import dfs_export as dx


def _tmpdir() -> Path:
    return Path(tempfile.mkdtemp())


def _healthy_payload(day="2026-08-10", n=2):
    players = [{
        "mlbam": 100 + i, "side": "hit" if i % 2 else "pit",
        "name": "P%d" % i, "team": "AAA", "opp": "BBB", "game_pk": 900001,
        "is_home": bool(i % 2), "start_rate": 0.9, "games_today": 1,
        "pts": {"dk": 10.0 + i, "fd": 12.0 + i},
        "line": {"pa": 4.3}, "ctx": {"mult": 1.02}, "est": ["matchup"],
    } for i in range(n)]
    return {
        "generated_at": "2026-08-10T12:00:00Z", "slate_date": day,
        "season": 2026, "season_fraction": 0.7,
        "fantasy_generated_at": "2026-08-01T00:00:00Z",
        "n_games": 1, "n_players": n,
        "games": [{"game_pk": 900001, "date": day, "datetime": day + "T23:00:00Z",
                   "status": "Preview", "venue": "Park", "venue_id": 1,
                   "park_run_pf": 1.05, "park_source": "savant_mlb",
                   "vegas": {"total": 8.5}, "home": {}, "away": {}}],
        "players": players,
        "empty_reason": None, "empty_reason_kind": None,
    }


# ---- _archive_slate --------------------------------------------------------
def test_archive_written_with_compact_shape():
    d = _tmpdir()
    p = dx._archive_slate(_healthy_payload(), archive_dir=d)
    assert p is not None and p.name == "2026-08-10.json"
    got = json.loads(p.read_text(encoding="utf-8"))
    assert got["slate_date"] == "2026-08-10" and got["n_players"] == 2
    assert got["archived_at"]
    row = got["players"][0]
    # The grading keys survive; the bulky vectors do not.
    for k in ("mlbam", "side", "game_pk", "pts", "start_rate", "team", "opp"):
        assert k in row, row
    assert "line" not in row and "ctx" not in row and "est" not in row
    g = got["games"][0]
    assert g["game_pk"] == 900001 and g["park_run_pf"] == 1.05
    assert g["vegas"] == {"total": 8.5}
    assert "home" not in g and "away" not in g


def test_archive_refuses_empty_and_refused_payloads():
    d = _tmpdir()
    empty = _healthy_payload()
    empty.update(n_players=0, players=[])
    assert dx._archive_slate(empty, archive_dir=d) is None
    broken = _healthy_payload()
    broken["empty_reason"] = "collapsed"
    assert dx._archive_slate(broken, archive_dir=d) is None
    undated = _healthy_payload(day="not-a-date")
    assert dx._archive_slate(undated, archive_dir=d) is None
    assert list(d.glob("*.json")) == []


def test_archive_same_day_rebuild_overwrites_not_duplicates():
    d = _tmpdir()
    dx._archive_slate(_healthy_payload(), archive_dir=d)
    later = _healthy_payload(n=3)
    later["generated_at"] = "2026-08-10T18:00:00Z"
    dx._archive_slate(later, archive_dir=d)
    files = list(d.glob("*.json"))
    assert len(files) == 1
    got = json.loads(files[0].read_text(encoding="utf-8"))
    assert got["n_players"] == 3 and got["generated_at"] == "2026-08-10T18:00:00Z"


# ---- retention -------------------------------------------------------------
def test_retention_prunes_past_the_bound():
    d = _tmpdir()
    (d / "2026-01-01.json").write_text("{}", encoding="utf-8")   # 222 days old
    (d / "2026-08-01.json").write_text("{}", encoding="utf-8")   # inside bound
    (d / "notes.json").write_text("{}", encoding="utf-8")        # not a date
    n = dx._prune_archive(d, today="2026-08-10")
    assert n == 1, n
    names = {f.name for f in d.glob("*.json")}
    assert names == {"2026-08-01.json", "notes.json"}, names


def test_archive_write_prunes_in_the_same_pass():
    d = _tmpdir()
    (d / "2026-01-01.json").write_text("{}", encoding="utf-8")
    dx._archive_slate(_healthy_payload(day="2026-08-10"), archive_dir=d)
    names = {f.name for f in d.glob("*.json")}
    assert names == {"2026-08-10.json"}, names


# ---- refresh() wiring ------------------------------------------------------
def test_refresh_archives_a_published_board():
    d = _tmpdir()
    out = d / "dfs.json"
    arch = d / "hist"
    orig = dx.build_payload
    dx.build_payload = lambda **kw: _healthy_payload()
    try:
        n = dx.refresh(log=lambda *a, **k: None, day="2026-08-10",
                       out_path=out, archive_dir=arch)
    finally:
        dx.build_payload = orig
    assert n == 2
    assert (arch / "2026-08-10.json").exists()
    # and the published payload itself is untouched by the archiving
    assert json.loads(out.read_text(encoding="utf-8"))["n_players"] == 2


def test_refresh_does_not_archive_an_empty_slate():
    d = _tmpdir()
    out = d / "dfs.json"
    arch = d / "hist"
    n = dx.refresh(log=lambda *a, **k: None, day="2026-01-15", games=[],
                   out_path=out, archive_dir=arch)
    assert n == 0
    assert not arch.exists() or list(arch.glob("*.json")) == []


if __name__ == "__main__":
    import sys
    mod = sys.modules[__name__]
    fns = [f for n, f in vars(mod).items() if n.startswith("test_") and callable(f)]
    for f in fns:
        f()
    print(f"ALL {len(fns)} dfs_history tests PASS")

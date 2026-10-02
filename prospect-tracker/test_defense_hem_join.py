# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Defense board's HEM+ column is the hitter board's HEM+ (audit RML03).

THE DEFECT. data/defense_leaderboards.json copies hem_plus off
data/hitter_leaderboards.json by MLBAM for the glove-versus-bat chart and the
Standard view's HEM+ column. On 2026-10-01 the hitter board was rebuilt by hand
(`python hitter_export.py`, the per-hand HEM+ change) after the nightly had
built the Defense board, so 5 of 652 fielders served the previous build's HEM+
(Brandon Valenzuela 100 against 99, Ceddanne Rafaela 95 against 96, Michael
Massey 91 against 92, Brett Baty 90 against 91, Gunnar Henderson 96 against 95).

What is pinned here:
  * order: every path that writes the hitter board runs the defense export
    after it (run_monthly 6b4g then 6b4i, run_daily 9e-pre0 then 9e-pre0b, and
    hitter_export's own entry point); the rebuild-only path writes neither;
  * the served pair: every shared MLBAM carries the same hem_plus on both
    boards (exact), and hem_plus_join names the hitter board it read
    (generated_at, as_of, season, and a digest of its HEM+ column).
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
DEF = ROOT / "data" / "defense_leaderboards.json"
HIT = ROOT / "data" / "hitter_leaderboards.json"


def _src(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _fn_body(module: str, name: str) -> str:
    src = _src(module)
    node = next(n for n in ast.parse(src).body
                if isinstance(n, ast.FunctionDef) and n.name == name)
    return "\n".join(src.split("\n")[node.lineno - 1:node.end_lineno])


# ---------------------------------------------------------------------------
# order
# ---------------------------------------------------------------------------
def test_the_monthly_runs_the_defense_board_after_the_hitter_board():
    body = _fn_body("run_monthly.py", "main")
    i_hit = body.index('_step("6b4g. Hitter Leaderboards (hitter_leaderboards.json)"')
    i_def = body.index('_step("6b4i. Defense Leaderboards (defense_leaderboards.json)"')
    assert i_hit < i_def
    assert "from hitter_export import export as _export_hitters" in body[i_hit:i_def]
    assert "from defense_export import" in body[i_def:]
    # No other hitter-board write sits after the defense step in the monthly.
    assert "hitter_export" not in body[i_def:]


def test_the_daily_runs_the_defense_board_after_the_hitter_board():
    body = _fn_body("run_monthly.py", "run_daily")
    i_hit = body.index('_step("9e-pre0. Refresh team leaderboards')
    i_def = body.index('_step("9e-pre0b. Refresh Defense Leaderboards')
    assert i_hit < i_def
    assert '__import__("hitter_export").export' in body[i_hit:i_def]
    assert "from defense_export import export" in body[i_def:]
    assert body.count("hitter_export") == 1, "a second hitter-board write in run_daily"


def test_the_rebuild_only_path_writes_neither_board():
    for fn in ("rebuild_only", "rebuild_only_cli", "_rebuild_ledger_and_franchise"):
        body = _fn_body("run_monthly.py", fn)
        assert "hitter_export" not in body and "defense_export" not in body, fn


def test_the_hitter_entry_point_runs_the_defense_board_after_its_own():
    src = _src("hitter_export.py")
    main = src[src.index('if __name__ == "__main__":'):]
    assert "export_then_defense(_season)" in main


def test_export_then_defense_order_and_a_failed_hitter_board(monkeypatch):
    import defense_export
    import hitter_export
    calls: list[str] = []
    monkeypatch.setattr(hitter_export, "export",
                        lambda season=None, **kw: calls.append("hitter") or 661)
    monkeypatch.setattr(defense_export, "export",
                        lambda season=None, **kw: calls.append("defense") or 654)
    assert hitter_export.export_then_defense(2026, log=lambda *_: None) == 661
    assert calls == ["hitter", "defense"]
    calls.clear()
    monkeypatch.setattr(hitter_export, "export",
                        lambda season=None, **kw: calls.append("hitter") or 0)
    assert hitter_export.export_then_defense(2026, log=lambda *_: None) == 0
    assert calls == ["hitter"], "a hitter board that did not write leaves the Defense board alone"


# ---------------------------------------------------------------------------
# the join block (no export runs: the hitter board is a temp file)
# ---------------------------------------------------------------------------
def test_the_join_block_names_the_board_it_read(monkeypatch, tmp_path):
    import defense_export as de
    p = tmp_path / "hitter_leaderboards.json"
    p.write_text(json.dumps({"generated_at": "2026-10-01", "as_of": "2026-10-01",
                             "season": 2026, "hitters": [
                                 {"mlbam": 1, "hem_plus": 99},
                                 {"mlbam": 2, "hem_plus": None}]}), encoding="utf-8")
    monkeypatch.setattr(de, "HITTER_BOARD", p)
    rows = [{"mlbam": 1}, {"mlbam": 2}, {"mlbam": 3}]
    meta = de._join_hem_plus(rows, 2026)
    assert meta["n_stamped"] == 1 and rows[0]["hem_plus"] == 99
    assert "hem_plus" not in rows[1] and "hem_plus" not in rows[2]
    assert meta["hitter_generated_at"] == "2026-10-01" and meta["hitter_season"] == 2026
    assert meta["hem_plus_digest"] == de.hem_plus_digest({1: 99, 2: None})
    assert de.hem_plus_digest({1: 99}) != de.hem_plus_digest({1: 100})
    # Another season joins nothing and says why.
    rows = [{"mlbam": 1}]
    meta = de._join_hem_plus(rows, 2025)
    assert meta["n_stamped"] == 0 and "hem_plus" not in rows[0]
    assert "2026 season" in meta["reason"]


# ---------------------------------------------------------------------------
# the served pair
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def served():
    if not (DEF.exists() and HIT.exists()):
        pytest.skip("defense or hitter board not generated")
    return (json.loads(DEF.read_text(encoding="utf-8")),
            json.loads(HIT.read_text(encoding="utf-8")))


def test_every_shared_fielder_serves_the_hitter_boards_hem_plus(served):
    d, h = served
    if d.get("season") != h.get("season"):
        pytest.skip("the two boards are different seasons")
    hem = {r["mlbam"]: r.get("hem_plus") for r in h["hitters"]}
    shared = [f for f in d["fielders"] if f.get("mlbam") in hem]
    assert len(shared) >= 300
    off = [(f["mlbam"], f.get("name"), f.get("hem_plus"), hem[f["mlbam"]])
           for f in shared if f.get("hem_plus") != hem[f["mlbam"]]]
    assert not off, (f"{len(off)} of {len(shared)} fielders serve a HEM+ the hitter "
                     f"board does not: {off[:5]}; re-run python defense_export.py")
    # And no fielder carries a HEM+ the hitter board has no row for.
    assert all(f.get("hem_plus") is None for f in d["fielders"] if f.get("mlbam") not in hem)


def test_the_join_block_carries_the_hitter_boards_stamp(served):
    d, h = served
    j = d["hem_plus_join"]
    assert j["hitter_generated_at"] == h["generated_at"]
    assert j["hitter_as_of"] == h.get("as_of")
    assert j["hitter_season"] == h["season"]
    import defense_export as de
    assert j["hem_plus_digest"] == de.hem_plus_digest(
        {r["mlbam"]: r.get("hem_plus") for r in h["hitters"]})
    assert j["n_stamped"] == sum(1 for f in d["fielders"] if f.get("hem_plus") is not None)

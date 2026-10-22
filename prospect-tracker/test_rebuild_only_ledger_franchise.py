"""The standalone rebuild-only path rebuilds the Club Ledger and Franchise
boards after their inputs (owner answer LEDTRIM-1 = (c), 2026-10-01).

THE DEFECT. `run_monthly.py --rebuild-only` rewrote trade_values.json,
mlb_projections.json and the timeseries farm roll-up (org_summary) but never
the two boards that read them (nightly steps d10e and 6b7d), so a rebuild left
both boards one vintage behind until the next nightly. Measured 2026-09-30
when they were finally rebuilt: farm rank moved on 5 clubs, Cost+ on 4, the
financial letter on PIT and SFG, the franchise rank on 8.

What is pinned here:
  * order: rebuild_only (trade values, farm roll-up) -> player cards ->
    ledger board -> franchise board, and the rebuild path has no site build of
    its own (the caller's build_site runs after it returns);
  * one writer each: the nightly steps and the rebuild tail call the same
    _export_ledger_board / _export_franchise_board;
  * guards: an input missing, a rebuild aimed at another directory, or a
    ledger that did not rebuild skips the board with a logged reason, and the
    file on disk is left alone.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent


def _src() -> str:
    return (ROOT / "run_monthly.py").read_text(encoding="utf-8")


def _fn_body(name: str) -> str:
    src = _src()
    tree = ast.parse(src)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    lines = src.split("\n")
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def _calls_in_order(name: str) -> list[str]:
    """The names of the plain function calls in a function, in source order."""
    src = _src()
    tree = ast.parse(src)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    calls = [(c.lineno, c.col_offset, c.func.id) for c in ast.walk(node)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)]
    return [n for _, _, n in sorted(calls)]


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------
def test_the_rebuild_cli_runs_the_boards_after_their_inputs_and_in_order():
    calls = _calls_in_order("rebuild_only_cli")
    for n in ("rebuild_only", "_rebake_mlb_player_detail", "_rebuild_ledger_and_franchise"):
        assert calls.count(n) == 1, (n, calls)
    assert (calls.index("rebuild_only") < calls.index("_rebake_mlb_player_detail")
            < calls.index("_rebuild_ledger_and_franchise")), calls
    # The inputs the tail needs are all written inside rebuild_only, which runs
    # first: the timeseries (its org_summary is the farm roll-up), the
    # projections, then the trade board.
    body = _fn_body("rebuild_only")
    i_ts = body.index("export_timeseries_json(")
    i_proj = body.index("_export_proj()")
    i_tv = body.index("export_trade_values_json(tv_players")
    assert i_ts < i_proj < i_tv
    # No site build inside the rebuild path: the caller's build_site runs after.
    for fn in ("rebuild_only", "rebuild_only_cli", "_rebuild_ledger_and_franchise"):
        body = _fn_body(fn)
        assert "import build_site" not in body and "build_site.main(" not in body, fn


def test_the_tail_runs_the_ledger_before_the_franchise_board():
    calls = _calls_in_order("_rebuild_ledger_and_franchise")
    assert calls.count("_export_ledger_board") == 1 and calls.count("_export_franchise_board") == 1
    assert calls.index("_export_ledger_board") < calls.index("_export_franchise_board")
    # xM$ (XM_2) runs once, before the ledger whose club block it feeds.
    assert calls.count("_export_xm") == 1
    assert calls.index("_export_xm") < calls.index("_export_ledger_board")


def test_the_nightly_steps_and_the_rebuild_share_one_writer_each():
    src = _src()
    i = src.index('_step("d10e. Club Ledger board (ledger_board.json)"')
    j = src.index('_step("d10f. Postseason bracket simulator')
    k = src.index('_step("6b7d. Franchise board (franchise_board.json)"')
    m = src.index("finish_run(run_id", k)
    assert "_export_ledger_board(log)" in src[i:j] and "_lg.build_all()" not in src[i:j]
    assert "_export_franchise_board(log)" in src[k:m] and "_fr.build()" not in src[k:m]
    led = _fn_body("_export_ledger_board")
    assert led.index("_lg.OUT.write_text(") < led.index("_lg.write_shards(") < led.index("_lg.write_trade_cbt(")
    assert '_record_ingest("ledger_export", True' in led and '_record_ingest("ledger_export", False' in led
    fr = _fn_body("_export_franchise_board")
    assert "_fr.write(_frd)" in fr and "_fr.OUT.write_text(" not in fr and "FranchiseRefusal" in fr
    assert '_record_ingest("franchise_export", True' in fr and '_record_ingest("franchise_export", False' in fr


def test_the_guard_names_the_inputs_the_boards_read():
    import run_monthly as rm
    assert rm.REBUILD_LEDGER_INPUTS == ("timeseries.json", "trade_values.json", "mlb_projections.json")
    assert rm.REBUILD_FRANCHISE_INPUTS == rm.REBUILD_LEDGER_INPUTS + ("ledger_board.json",)
    import franchise_export
    import ledger_export
    assert Path(ledger_export.DATA).resolve() == Path(rm._EXPORTER_DATA_DIR).resolve()
    assert Path(franchise_export.DATA).resolve() == Path(rm._EXPORTER_DATA_DIR).resolve()


# ---------------------------------------------------------------------------
# behaviour (no exporter runs: the two writers are replaced)
# ---------------------------------------------------------------------------
@pytest.fixture
def wired(monkeypatch, tmp_path):
    import mlb_player_export
    import run_monthly as rm
    calls: list[str] = []
    monkeypatch.setattr(rm, "_EXPORTER_DATA_DIR", tmp_path)
    monkeypatch.setattr(rm, "rebuild_only", lambda out_dir=None, **kw: calls.append("rebuild"))
    monkeypatch.setattr(mlb_player_export, "export", lambda: calls.append("cards"))
    monkeypatch.setattr(rm, "_export_xm", lambda log: calls.append("xm") or True)
    monkeypatch.setattr(rm, "_export_ledger_board", lambda log: calls.append("ledger") or True)
    monkeypatch.setattr(rm, "_export_franchise_board", lambda log: calls.append("franchise") or True)
    for n in rm.REBUILD_FRANCHISE_INPUTS:
        (tmp_path / n).write_text("{}", encoding="utf-8")
    return rm, calls, tmp_path


def test_a_rebuild_with_its_inputs_writes_both_boards_after_the_cards(wired):
    rm, calls, d = wired
    rm.rebuild_only_cli(out_dir=d)
    assert calls == ["rebuild", "cards", "xm", "ledger", "franchise"]


@pytest.mark.parametrize("gone", ["timeseries.json", "trade_values.json", "mlb_projections.json"])
def test_a_missing_ledger_input_skips_both_boards_with_a_reason(wired, caplog, gone):
    rm, calls, d = wired
    (d / gone).unlink()
    with caplog.at_level(logging.WARNING, logger="rebuild_only"):
        rm.rebuild_only_cli(out_dir=d)
    assert calls == ["rebuild", "cards"]
    text = caplog.text
    assert "ledger board SKIPPED: input missing: " + gone in text
    assert "franchise board SKIPPED: input missing: " + gone in text


def test_a_failed_ledger_skips_the_franchise_board(wired, caplog, monkeypatch):
    rm, calls, d = wired
    monkeypatch.setattr(rm, "_export_ledger_board", lambda log: calls.append("ledger") and False)
    with caplog.at_level(logging.WARNING, logger="rebuild_only"):
        res = rm._rebuild_ledger_and_franchise(d, logging.getLogger("rebuild_only"))
    assert calls == ["xm", "ledger"]
    assert res["ledger"] == "failed" and res["franchise"].startswith("skipped: ")
    assert "the ledger board did not rebuild in this pass" in caplog.text


def test_a_missing_ledger_board_skips_only_the_franchise_board(wired, caplog, monkeypatch):
    rm, calls, d = wired
    (d / "ledger_board.json").unlink()
    # A ledger writer that does not leave its file behind (a stub here).
    with caplog.at_level(logging.WARNING, logger="rebuild_only"):
        res = rm._rebuild_ledger_and_franchise(d, logging.getLogger("rebuild_only"))
    assert calls == ["xm", "ledger"]
    assert res == {"ledger": "written", "franchise": "skipped: input missing: ledger_board.json"}
    assert "franchise board SKIPPED: input missing: ledger_board.json" in caplog.text


def test_a_rebuild_aimed_elsewhere_leaves_both_boards_alone(wired, caplog, tmp_path_factory):
    rm, calls, d = wired
    other = tmp_path_factory.mktemp("elsewhere")
    with caplog.at_level(logging.WARNING, logger="rebuild_only"):
        rm.rebuild_only_cli(out_dir=other)
    assert calls == ["rebuild", "cards"]
    assert caplog.text.count("SKIPPED: this rebuild wrote to") == 2

"""d9 sub-step timings (perf(pipeline), PERF_9, 2026-10-03).

THE GAP. The daily step 'd9. Rebuild timeseries (no scrape)' was one opaque
row in logs/pipeline_steps_daily.json: 962.40 s, 53.6 percent of run 538, with
nothing inside it ranked. Every block of run_monthly.rebuild_only and every
stage of efv_export.regen_all now records itself through the same _step
recorder as a SUB-STEP (id token 'd9.<slug>', 'd9.efv.<stage>'), so the step
table ranks them; export_timeseries_json logs its own phase timers.

What is pinned here:
  * the sub-step rule: a token "<root>.<name>" whose root is registered in
    run_monthly._NESTED_STEP_PARENTS names a nested row whose parent is the
    token without its last ".<name>", and the run total never adds a nested
    row's seconds a second time while an enclosing row is present;
  * rebuild_only records every expected sub-step, and the eFV regen hook
    reaches regen_all's stages (functional, every producer stubbed);
  * no sub-step id collides with a top-level step id anywhere in
    run_monthly.py (test_* and the audit-doc generator read those literals);
  * the standalone --rebuild-only path writes its own step table
    (logs/pipeline_steps_rebuild.json), never the daily one;
  * export_timeseries_json carries its phase timers.
"""
from __future__ import annotations

import ast
import json
import logging
import re
import sys
import types
from pathlib import Path

import run_monthly
import storage

ROOT = Path(__file__).resolve().parent

REBUILD_SUBSTEPS = (
    "d9.dpw", "d9.ingest", "d9.draft", "d9.overseas", "d9.build", "d9.inputs", "d9.export",
    "d9.efv", "d9.efv_tripwire", "d9.rebake", "d9.ifa", "d9.identity", "d9.college",
    "d9.org_tendencies", "d9.milb_translation", "d9.pace_defhome", "d9.efv_proxy",
    "d9.proj", "d9.grpo", "d9.grpo_history", "d9.trade_values", "d9.summary",
)
REGEN_STAGES = (
    "dataset", "score", "backgrade", "history", "tools", "ungraded",
    "provisional_v2", "reliability", "consolidate", "valuation_curve", "statcast_alevel",
)


def _token(name: str) -> str:
    return name.split(" ", 1)[0].rstrip(".")


def _all_step_literals() -> list[str]:
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    lits = re.findall(r'_step\(\s*"([^"]+)"', src)
    lits += re.findall(r'_STEP_TIMES\.append\(\(\s*"([^"]+)"', src)
    return lits


# ---------------------------------------------------------------------------
# the sub-step rule
# ---------------------------------------------------------------------------
def test_the_parent_rule_reads_the_token_before_the_dot():
    assert run_monthly._step_parent("d9.export. Serialise timeseries") == "d9"
    assert run_monthly._step_parent("d9.efv.score. eFV regen stage (score)") == "d9.efv"
    assert run_monthly._step_parent("d9. Rebuild timeseries (no scrape)") is None
    assert run_monthly._step_parent("d9-std. Nightly standings read health") is None
    assert run_monthly._step_parent("3d-bis. Approximate zone metrics") is None
    assert run_monthly._step_parent("9e-pre0d. Live-season window panel") is None
    assert run_monthly._step_parent("fa: signing window") is None
    # main()'s roman-numeral ids are siblings of their stem, not children
    assert run_monthly._step_parent("2b.ii. Acquisition classification") is None
    assert run_monthly._step_parent("2b.iii. Spotrac IFA scrape + merge") is None


def test_the_step_table_ranks_substeps_without_double_counting(tmp_path, monkeypatch):
    monkeypatch.setattr(run_monthly, "_STEP_TIMES", [
        ("d9. Rebuild timeseries (no scrape)", 100.0),
        ("d9.export. Serialise timeseries", 60.0),
        ("d9.efv. eFV regen", 30.0),
        ("d9.efv.score. eFV regen stage (score)", 20.0),
        ("d10. FA signing-window refresh", 20.0),
    ])
    out = run_monthly.write_step_timings("daily", 110.0, path=tmp_path / "steps.json")
    doc = json.loads(out.read_text(encoding="utf-8"))
    # 100 + 20 top-level seconds, never 230: the nested rows are already inside d9.
    assert doc["total_s"] == 120.0
    assert doc["n_steps"] == 5
    names = [s["step"] for s in doc["steps"]]
    assert names[0].startswith("d9. ") and names[1].startswith("d9.export.")
    by_name = {s["step"]: s for s in doc["steps"]}
    assert by_name["d9.export. Serialise timeseries"]["parent"] == "d9"
    assert by_name["d9.efv.score. eFV regen stage (score)"]["parent"] == "d9.efv"
    assert "parent" not in by_name["d9. Rebuild timeseries (no scrape)"]
    assert "parent" not in by_name["d10. FA signing-window refresh"]
    assert by_name["d9.export. Serialise timeseries"]["pct"] == 50.0


def test_a_substep_without_its_parent_row_counts_once(tmp_path, monkeypatch):
    # the standalone --rebuild-only pass records the d9.* rows with no d9 row
    monkeypatch.setattr(run_monthly, "_STEP_TIMES", [
        ("d9.export. Serialise timeseries", 60.0),
        ("d9.efv. eFV regen", 30.0),
        ("d9.efv.score. eFV regen stage (score)", 20.0),
    ])
    out = run_monthly.write_step_timings("rebuild-only", 1.0, path=tmp_path / "steps.json")
    doc = json.loads(out.read_text(encoding="utf-8"))
    # 60 + 30: the score stage is inside the recorded d9.efv row
    assert doc["total_s"] == 90.0


# ---------------------------------------------------------------------------
# no collisions
# ---------------------------------------------------------------------------
def test_substep_ids_collide_with_no_top_level_step_id():
    lits = _all_step_literals()
    subs = [n for n in lits if run_monthly._step_parent(n) is not None]
    tops = [n for n in lits if run_monthly._step_parent(n) is None]
    sub_tokens = [_token(n) for n in subs]
    assert len(set(sub_tokens)) == len(sub_tokens), "duplicate sub-step id"
    top_tokens = {_token(n) for n in tops}
    assert not (set(sub_tokens) & top_tokens)
    assert {run_monthly._step_parent(n) for n in subs} == {"d9"}
    assert "d9" in top_tokens
    for want in REBUILD_SUBSTEPS:
        assert want in sub_tokens, want
    # the regen stage names live in efv_export and are formatted at the hook
    assert any(t.startswith("d9.efv.") for t in sub_tokens) is False, (
        "regen stage ids are formatted from the hook, not written as literals")


def test_rebuild_only_wraps_its_blocks_in_sub_steps():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "rebuild_only")
    body = "\n".join(src.split("\n")[node.lineno - 1:node.end_lineno])
    tokens = [_token(n) for n in re.findall(r'with _step\(\s*"([^"]+)"', body)]
    assert [t for t in tokens if t != "d9-std"] == list(REBUILD_SUBSTEPS)
    # the eFV regen hands the recorder down to regen_all's stages
    assert "_regen_xfv(step=" in body


# ---------------------------------------------------------------------------
# functional: rebuild_only records the sub-steps, every producer stubbed
# ---------------------------------------------------------------------------
def _module(name: str, **attrs) -> types.ModuleType:
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


def test_rebuild_only_records_the_d9_substeps(tmp_path, monkeypatch, caplog):
    rm = run_monthly
    monkeypatch.setattr(rm, "_STEP_TIMES", [])
    noop = lambda *a, **k: None                                    # noqa: E731
    for name in ("init_db", "_write_dpw_series_step", "_stage_fangraphs_articles",
                 "_utf8_console", "_record_ingest", "_statsapi_standings_health",
                 "_post_export_summary", "_patch_export_run_summary",
                 "_merge_ifa_bonuses_into_acquisitions"):
        monkeypatch.setattr(rm, name, noop)
    monkeypatch.setattr(rm, "ingest_source_article_drops", lambda out_dir, log: (0, 0))
    monkeypatch.setattr(rm, "load_all_snapshots", lambda: [])
    monkeypatch.setattr(rm, "build_timeseries", lambda snaps, normalize=False: [])
    monkeypatch.setattr(rm, "load_acquisitions", lambda: {})
    monkeypatch.setattr(rm, "_load_spotrac_ifa", lambda **kw: ({}, {}))
    monkeypatch.setattr(rm, "_load_spotrac_contracts", lambda **kw: {})
    monkeypatch.setattr(rm, "_load_draft_pools_for_rebuild", lambda: {})
    monkeypatch.setattr(rm, "_derive_all_transactions", lambda: {})
    monkeypatch.setattr(rm, "_derive_all_level_changes", lambda: {})
    for name in ("load_statlines", "load_pitch_arsenals", "load_zone_metrics",
                 "load_statcast_metrics", "load_sabermetrics", "load_trades",
                 "load_career_stats", "load_career_war", "load_il_status",
                 "load_roster_status"):
        monkeypatch.setattr(rm, name, lambda: {})
    exported: list[Path] = []
    monkeypatch.setattr(rm, "export_timeseries_json",
                        lambda ts, out_path, **kw: exported.append(out_path))
    monkeypatch.setattr(storage, "rebake_board_ranks",
                        lambda out_path, log=None: {"written": False, "n_moved": 0,
                                                    "n_active": 0, "top": [], "message": "stub"})

    hooked: list[str] = []

    def fake_regen_all(persist=True, include_eval=False, step=None):
        assert step is not None, "rebuild_only must hand its recorder to regen_all"
        for stage in ("dataset", "score"):
            with step(stage):
                hooked.append(stage)
        return {"meta": {"n_players": 0, "n_active": 0}}

    stubs = {
        "fangraphs_csv": _module("fangraphs_csv", ingest_drops=lambda **kw: (0, 0)),
        "draft_promotion": _module("draft_promotion", promote_drafted_players=noop,
                                   seed_signed_draftees=noop),
        "draft_export": _module("draft_export", export_draft_json=lambda p: 0),
        "overseas_promotion": _module("overseas_promotion", promote_signed_players=noop,
                                      ingest_postings=noop),
        "overseas_export": _module("overseas_export", export_overseas_json=lambda p: 0),
        "efv_export": _module("efv_export", regen_all=fake_regen_all),
        "tools.efv_regen_tripwire": _module(
            "tools.efv_regen_tripwire",
            run=lambda log: {"observed": True, "n_alerts": 0, "message": "stub"}),
        "ifa_export": _module("ifa_export", export_ifa_json=lambda p: 0),
        "identity_audit": _module("identity_audit", build=lambda path: {
            "summary": {"critical_player_keys": 0, "critical_active_player_keys": 0,
                        "frankenstein_records": 0}}),
        "college_translation": _module("college_translation",
                                       build=lambda out_dir: {"factors": {}, "bridge_count": 0}),
        "org_tendencies": _module("org_tendencies", export=noop),
        "milb_translation": _module("milb_translation", build=lambda: {"fits": []}),
        "advancement_pace_export": _module("advancement_pace_export", run=noop),
        "def_home_export": _module("def_home_export", run=noop),
        "efv_proxy": _module("efv_proxy", run=lambda: {"sides": {}}),
        "proj_export": _module("proj_export", export=lambda: 0, FIRST_SEASON=2026),
        "grpo_prospect": _module("grpo_prospect",
                                 export_grpo_scores=lambda *a, **k: {"scored": 0},
                                 snapshot_grpo_scores=lambda **k: 0),
        "bayes_trade_value": _module("bayes_trade_value",
                                     export_trade_values_json=lambda *a, **k: 0,
                                     _reset_cache=noop),
        "tools.export_trade_values": _module("tools.export_trade_values",
                                             write_slim_sidecar=noop),
    }
    for name, mod in stubs.items():
        monkeypatch.setitem(sys.modules, name, mod)

    with caplog.at_level(logging.INFO, logger="rebuild_only"):
        rm.rebuild_only(tmp_path, stamp_summary=False)

    assert exported == [tmp_path / "timeseries.json"]
    assert hooked == ["dataset", "score"]
    crashed = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert not crashed, crashed

    names = [n for n, _ in rm._STEP_TIMES]
    tokens = [_token(n) for n in names]
    for want in REBUILD_SUBSTEPS:
        assert want in tokens, (want, tokens)
    assert "d9.efv.dataset" in tokens and "d9.efv.score" in tokens
    assert "d9-std" in tokens
    # source order: the eFV regen sits between the export and the re-bake
    assert tokens.index("d9.export") < tokens.index("d9.efv.dataset") \
        < tokens.index("d9.efv") < tokens.index("d9.rebake") < tokens.index("d9.proj") \
        < tokens.index("d9.trade_values") < tokens.index("d9.summary")

    # and the daily table lists them, each under its parent
    out = rm.write_step_timings("daily", 1.0, path=tmp_path / "pipeline_steps_daily.json")
    doc = json.loads(out.read_text(encoding="utf-8"))
    listed = {s["step"]: s for s in doc["steps"]}
    for want in REBUILD_SUBSTEPS:
        row = next(s for n, s in listed.items() if _token(n) == want)
        assert row["parent"] == "d9"
    assert "parent" not in next(s for n, s in listed.items() if _token(n) == "d9-std")


# ---------------------------------------------------------------------------
# functional: regen_all's stages, every eFV producer stubbed
# ---------------------------------------------------------------------------
def test_regen_all_runs_every_stage_through_the_hook(monkeypatch):
    import efv_export

    seen: list[str] = []
    calls: list[str] = []

    def rec(label):
        return lambda *a, **k: calls.append(label)

    stubs = {
        "efv_dataset": _module("efv_dataset", run=rec("dataset.run"),
                               build_live=rec("dataset.build_live")),
        "efv_score": _module("efv_score", run=rec("score.run"), run_live=rec("score.run_live"),
                             run_backgrade=rec("backgrade"), score_history=rec("history")),
        "efv_tools": _module("efv_tools", run=rec("tools.run"), run_live=rec("tools.run_live")),
        "efv_ungraded": _module("efv_ungraded", build=rec("ungraded")),
        "provisional_v2": _module("provisional_v2", build=rec("provisional_v2")),
        "efv_reliability": _module("efv_reliability", build=rec("reliability")),
        "statcast_alevel_export": _module("statcast_alevel_export", run=rec("statcast_alevel")),
    }
    for name, mod in stubs.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr(efv_export, "run", lambda persist: calls.append("consolidate") or
                        {"by_player": {}, "meta": {"n_players": 0, "n_active": 0}})
    monkeypatch.setattr(efv_export, "_valuation_curve", rec("valuation_curve"))

    from contextlib import contextmanager

    @contextmanager
    def hook(name):
        seen.append(name)
        yield

    out = efv_export.regen_all(persist=True, step=hook)
    assert out["meta"]["n_players"] == 0
    assert seen == list(REGEN_STAGES)
    assert calls == ["dataset.run", "dataset.build_live", "dataset.run", "dataset.build_live",
                     "score.run", "score.run_live", "score.run", "score.run_live",
                     "backgrade", "history", "tools.run", "tools.run_live", "ungraded",
                     "provisional_v2", "reliability", "consolidate", "valuation_curve",
                     "statcast_alevel"]


def test_regen_all_without_a_hook_still_times_its_stages(monkeypatch, caplog):
    import efv_export
    noop = lambda *a, **k: None                                    # noqa: E731
    stubs = {
        "efv_dataset": _module("efv_dataset", run=noop, build_live=noop),
        "efv_score": _module("efv_score", run=noop, run_live=noop, run_backgrade=noop,
                             score_history=noop),
        "efv_tools": _module("efv_tools", run=noop, run_live=noop),
        "efv_ungraded": _module("efv_ungraded", build=noop),
        "efv_reliability": _module("efv_reliability", build=noop),
    }
    for name, mod in stubs.items():
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr(efv_export, "run", lambda persist: {"by_player": {}, "meta": {}})
    with caplog.at_level(logging.INFO, logger="efv_export"):
        efv_export.regen_all(persist=False)
    stages = [m.group(1) for m in
              (re.match(r"regen_all stage (\S+) done", r.getMessage()) for r in caplog.records)
              if m]
    # persist=False skips provisional_v2, the valuation curve and the signal bake
    assert stages == ["dataset", "score", "backgrade", "history", "tools", "ungraded",
                      "reliability", "consolidate"]


# ---------------------------------------------------------------------------
# the standalone path writes its own table; the export logs its phases
# ---------------------------------------------------------------------------
def test_the_rebuild_cli_writes_its_own_step_table(tmp_path, monkeypatch):
    rm = run_monthly
    monkeypatch.setattr(rm, "_STEP_TIMES", [])
    monkeypatch.setattr(rm, "STEP_TIMINGS_PATH", tmp_path / "pipeline_steps_latest.json")

    def fake_rebuild(out_dir=None, **kw):
        with rm._step("d9.export. stub"):
            pass

    monkeypatch.setattr(rm, "rebuild_only", fake_rebuild)
    monkeypatch.setattr(rm, "_rebake_mlb_player_detail", lambda log, label="": None)
    monkeypatch.setattr(rm, "_rebuild_ledger_and_franchise", lambda out_dir, log: None)
    rm.rebuild_only_cli(out_dir=tmp_path)
    written = tmp_path / "pipeline_steps_rebuild.json"
    assert written.exists()
    assert not (tmp_path / "pipeline_steps_daily.json").exists()
    assert not (tmp_path / "pipeline_steps_latest.json").exists()
    doc = json.loads(written.read_text(encoding="utf-8"))
    assert doc["mode"] == "rebuild-only"
    assert [s["step"] for s in doc["steps"]] == ["d9.export. stub"]


def test_export_timeseries_json_logs_its_phase_timers():
    import inspect
    src = inspect.getsource(storage.export_timeseries_json)
    labels = re.findall(r'_phase_done\("([^"]+)"\)', src)
    assert len(labels) >= 8, labels
    assert len(set(labels)) == len(labels), "phase labels must be distinct"
    assert "export phase" in src

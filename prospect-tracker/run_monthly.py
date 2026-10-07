# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
Monthly run entry point.

Pipeline:
  1. Read the manual rankings CSV and any working scrapers.
  2. Append-insert new snapshots; skip already-stored intervals.
  3. Rebuild consensus time series + candlestick high/low.
  4. Fetch current-season MiLB stat lines for every tracked prospect.
  5. Detect trades (MLB Stats API + org-change inference).
  6. Export data/timeseries.json for the front-end.

Schedule via cron / GitHub Actions / launchd. The whole pipeline is
idempotent — same input → same output, and re-running is always safe.

Cadence: monthly is the right rhythm for prospect rankings. BA refreshes
mid-month in-season; FanGraphs "Updated" once mid-summer; TJStats
publishes monthly; ESPN/Pipeline/Athletic ~twice a year. Running more
often than monthly mostly just re-reads the CSV without finding new data.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import concurrent.futures
from pathlib import Path


# ===========================================================================
# MODULE IDENTITY (2026-08-05) - claim the name "run_monthly" for the LIVE
# pipeline module when this file is launched as a script.
# ===========================================================================
# THE DEFECT THIS CLOSES. deploy/nightly-build.sh runs `python run_monthly.py`,
# so the running pipeline IS sys.modules["__main__"] and NOTHING owns the name
# "run_monthly". Ten helper call sites across eight modules file their
# ingest-health rows with `from run_monthly import _record_ingest`, and with
# that name unclaimed the import statement does not find the running pipeline -
# it IMPORTS A SECOND, SEPARATE COPY of this file. The copy gets its own empty
# _INGEST_HEALTH list, the row is appended there, and write_ingest_health
# drains the FIRST module's list. MEASURED on the __main__ launch shape:
# 0 of 1 filed rows reached the drained payload before this line, 1 of 1 after
# (repro: tools-free script asserting the drain, run 2026-08-05).
#
# Fixing it HERE, at the name, is what makes every one of those call sites real
# at once - bullpen/hitter/leverage/starter, ifa, fa, fantasy, dfs, betting,
# draft and mlbam_ingest - rather than patching ten importers one at a time and
# leaving the eleventh to be written wrong.
#
# setdefault, not assignment: under `python -m run_monthly`, a plain import, or
# pytest, the name may already be bound to the correct object and rebinding it
# would be the same two-module hazard in reverse.
if __name__ == "__main__":                  # pragma: no cover - script entry
    sys.modules.setdefault("run_monthly", sys.modules["__main__"])


# v19 — Step timing infrastructure. Each major phase wraps itself in
# `with _step("name"):` which logs the duration on exit and records it
# in `_STEP_TIMES` for the end-of-run summary. The summary table sorts
# by duration so the slowest steps surface at the top — actionable
# perf intel for the next optimization pass.
_STEP_TIMES: list[tuple[str, float]] = []


@contextmanager
def _step(name: str, log: logging.Logger | None = None):
    """Context manager that logs + records the duration of a pipeline step."""
    start = time.monotonic()
    if log:
        # v19 — ASCII-only step markers. The prior ▶/● glyphs blew up
        # Windows cp1252 consoles with UnicodeEncodeError on every log
        # line (data still captured to _STEP_TIMES, but the per-step
        # progress messages were swallowed in noisy tracebacks).
        log.info("[step start] %s", name)
    try:
        yield
    finally:
        dur = time.monotonic() - start
        _STEP_TIMES.append((name, dur))
        if log:
            log.info("[step done ] %s in %s", name, _fmt_duration(dur))


def _fmt_duration(seconds: float) -> str:
    if seconds < 1.0:
        return f"{int(seconds * 1000)}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins = int(seconds // 60)
    secs = seconds - mins * 60
    return f"{mins}m{int(secs):02d}s"


def _efv_progress_update(out_dir: Path, where: str) -> None:
    """EV-00: append the eFV progress ledger (data/efv_progress.json) from the
    freshly written backtest and scoreboard, under the `efv_progress`
    heartbeat. Trigger "nightly" from both the daily and the monthly hook.
    Best-effort: a ledger failure is logged and never aborts the run."""
    _log = logging.getLogger("efv_progress")
    try:
        import efv_progress
        import job_heartbeat as _hb
        _res = efv_progress.update(out_dir, "nightly")
        _hb.record("efv_progress", ok=(_res.get("status") == "ok"),
                   result=f"{where}: {efv_progress.summary_line(_res)}"[:120])
        _log.info("efv_progress (%s): %s", where, efv_progress.summary_line(_res))
    except Exception as _e:
        _log.exception("efv_progress update failed (%s) - continuing", where)
        try:
            import job_heartbeat as _hb
            _hb.record("efv_progress", ok=False, result=f"{where}: {_e}"[:120])
        except Exception:
            pass


def _model_updates_update(out_dir: Path, where: str) -> None:
    """LIBRARY_11: append the Model Updates record (data/model_updates.json,
    model_updates.py) from the registry, its derived cards and the eFV
    progress ledger, under the `model_updates` heartbeat and ingest-health
    row. Runs after _efv_progress_update on the daily path and after the
    registry refresh on the monthly path. Append-only and idempotent; the
    backfill never runs here. Best-effort: a failure is logged and recorded,
    never raised."""
    _log = logging.getLogger("model_updates")
    try:
        import model_updates
        import job_heartbeat as _hb
        _res = model_updates.update(data_dir=out_dir)
        _ok = _res.get("status") == "ok" and not _res.get("note_problems")
        _line = model_updates.summary_line(_res)
        _hb.record("model_updates", ok=_ok, result=f"{where}: {_line}"[:120])
        _record_ingest("model_updates", _ok, n_rows=_res.get("n_events") or 0,
                       message=_line, log=_log)
        _log.info("model_updates (%s): %s", where, _line)
    except Exception as _e:
        _log.exception("model_updates update failed (%s) - continuing", where)
        try:
            import job_heartbeat as _hb
            _hb.record("model_updates", ok=False, result=f"{where}: {_e}"[:120])
            _record_ingest("model_updates", False, message=str(_e)[:200], log=_log)
        except Exception:
            pass


STEP_TIMINGS_PATH = Path(__file__).resolve().parent / "logs" / "pipeline_steps_latest.json"

# PERF_9 (2026-10-03): steps recorded INSIDE another recorded step. A step id
# "<root>.<name>" (or "<root>.<name>.<name>") whose <root> is listed here is a
# sub-step: the step table ranks it like any row and gives it a "parent" field
# (the id with its last ".<name>" dropped), and its seconds are never added to
# the run total a second time while an enclosing row is recorded. Listed by name,
# not matched by pattern: main()'s "2b.ii" style ids are siblings of "2b", run
# after it, not inside it.
_NESTED_STEP_PARENTS = frozenset({"d9"})


def _step_token(name: str) -> str:
    return name.split(" ", 1)[0].rstrip(".")


def _step_parent(name: str) -> str | None:
    """The enclosing step id of a sub-step row, None for a top-level row."""
    tok = _step_token(name)
    head, dot, tail = tok.partition(".")
    if dot and tail[:1].isalpha() and head in _NESTED_STEP_PARENTS:
        return tok.rsplit(".", 1)[0]
    return None


def _top_level_seconds(rows: list[tuple[str, float]]) -> float:
    """Sum of the rows that no other recorded row encloses."""
    tokens = {_step_token(n) for n, _ in rows}

    def _enclosed(name: str) -> bool:
        if _step_parent(name) is None:
            return False
        parts = _step_token(name).split(".")
        return any(".".join(parts[:i]) in tokens for i in range(1, len(parts)))

    return sum(d for n, d in rows if not _enclosed(n))


def _provisional_nightly(log: logging.Logger, where: str) -> None:
    """PV-02: retain tonight's served provisional grade
    (provisional_history.retain) under the `provisional_retention` heartbeat.
    PV-04: then score every committed provisional freeze against the first
    source grades ingested so far (provisional_track.update, append-only) under
    the `provisional_track` heartbeat. Each half is best-effort on its own: a
    failure is logged and recorded, never raised."""
    try:
        import provisional_history
        import job_heartbeat as _hb
        _res = provisional_history.retain()
        _hb.record("provisional_retention", ok=(_res.get("status") == "ok"),
                   result=f"{where}: {provisional_history.summary_line(_res)}"[:120])
        log.info("provisional retention (%s): %s", where,
                 provisional_history.summary_line(_res))
    except Exception as _e:                                   # noqa: BLE001
        log.exception("provisional retention failed (%s) - continuing", where)
        try:
            import job_heartbeat as _hb
            _hb.record("provisional_retention", ok=False, result=f"{where}: {_e}"[:120])
        except Exception:                                     # noqa: BLE001
            pass
    try:
        import provisional_track
        import job_heartbeat as _hb
        _res = provisional_track.update()
        _hb.record("provisional_track", ok=(_res.get("status") == "ok"),
                   result=f"{where}: {provisional_track.summary_line(_res)}"[:120])
        log.info("provisional track (%s): %s", where, provisional_track.summary_line(_res))
    except Exception as _e:                                   # noqa: BLE001
        log.exception("provisional track failed (%s) - continuing", where)
        try:
            import job_heartbeat as _hb
            _hb.record("provisional_track", ok=False, result=f"{where}: {_e}"[:120])
        except Exception:                                     # noqa: BLE001
            pass


def write_step_timings(mode: str, total_runtime: float,
                       log: logging.Logger | None = None,
                       path: Path | None = None,
                       run_id: object = None) -> Path | None:
    """Write the per-step timings as JSON so a run can be RANKED, not just read.

    WHY: before this, the only on-disk step record was `logs/pipeline_latest.log`
    from May 2026 - which predates the eval labs, the Statcast three-pass
    rewrite and the versa census entirely, so nothing in it can be compared
    against a current run. Every runtime claim therefore had to be sourced from
    comments in the code rather than from a measurement. This makes the next
    run produce its own baseline.

    Shape::

        {"generated_at": iso, "mode": "monthly"|"daily"|..., "run_id": str,
         "total_s": float, "n_steps": int,
         "steps": [{"step", "seconds", "pct"[, "parent"]}, ...]}   # slowest first

    A sub-step row (see _NESTED_STEP_PARENTS) carries "parent"; total_s counts
    it once, through its parent row.

    Written LAST-WINS to a single stable filename so before/after is a two-file
    diff. Best-effort: instrumentation must never be able to fail a run."""
    out_path = Path(path or STEP_TIMINGS_PATH)
    try:
        ranked = sorted(_STEP_TIMES, key=lambda x: x[1], reverse=True)
        total = max(total_runtime, _top_level_seconds(ranked))
        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "mode": mode,
            "run_id": None if run_id is None else str(run_id),
            "total_s": round(total, 2),
            "n_steps": len(ranked),
            "steps": [{"step": name, "seconds": round(dur, 2),
                       "pct": round((dur / total * 100) if total > 0 else 0.0, 2),
                       **({"parent": _step_parent(name)} if _step_parent(name) else {})}
                      for name, dur in ranked],
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if log:
            log.info("step timings -> %s (%d steps, %.0fs total)",
                     out_path, len(ranked), total)
        return out_path
    except Exception as e:                                   # noqa: BLE001
        if log:
            log.warning("step-timing artifact write failed: %s", e)
        return None


def _log_step_summary(log: logging.Logger, total_runtime: float,
                      mode: str = "monthly", run_id: object = None) -> None:
    """Print the per-step duration table + a `% of total` column, and write the
    machine-readable companion artifact.
    Steps are listed by descending duration so the worst hogs lead.
    """
    if not _STEP_TIMES:
        log.info("step summary: no timed steps recorded")
        return
    ranked = sorted(_STEP_TIMES, key=lambda x: x[1], reverse=True)
    total = max(total_runtime, _top_level_seconds(ranked))
    log.info("=" * 64)
    log.info("RUN STEP SUMMARY — sorted by duration")
    log.info("%-44s %10s %8s", "step", "duration", "% total")
    log.info("-" * 64)
    for name, dur in ranked:
        pct = (dur / total * 100) if total > 0 else 0
        log.info("%-44s %10s %7.1f%%", name[:44], _fmt_duration(dur), pct)
    log.info("-" * 64)
    log.info("%-44s %10s %7.1f%%", "TOTAL", _fmt_duration(total), 100.0)
    log.info("=" * 64)
    write_step_timings(mode, total, log=log, run_id=run_id)


# ===========================================================================
# Ingest observability (2026-07-31)
# ===========================================================================
# WHY: TJStats wrote ZERO rows from 2026-07-08 to 2026-07-21 while seven full
# monthly runs completed and reported success. Nothing anywhere recorded the
# outage. Three independent gaps produced that silence:
#   1. run_tjstats_pipeline never raises (correct) and its returned status was
#      DISCARDED by both callers, so a skipped ingest looked like a done one;
#   2. logs/pipeline_latest.log was last written in May - all pipeline logging
#      goes to stdout, and nothing was capturing stdout;
#   3. the end-of-run summary reports STEP DURATIONS only. A step that fetched
#      nothing still shows a healthy-looking duration.
#
# The fix is a per-run ledger written to data/ingest_health.json plus a RED
# line in the run summary for any scheduled grade source that wrote 0 rows.
# The DURABLE half rides storage.record_source_check / load_source_checks (the
# table the FA module already added) rather than a second mechanism: the JSON
# is this run's view, source_checks is the across-runs "when did this source
# last actually work" stamp that survives a run producing no output at all.

# Sources that are SCHEDULED to write grade rows on a normal run. Zero rows
# from one of these is an OUTAGE, not a quiet day - which is exactly the
# distinction the 8-day TJStats gap needed someone to make.
SCHEDULED_GRADE_SOURCES = ("tjstats", "mlb_pipeline_live", "mlb_pipeline_org")

# Scheduled EXPORTS: steps that build a served artifact and file their OWN
# explicit ok=False when they catch a silent-empty (2026-08-05's defect class -
# a fetch or join that fails into an empty-but-valid result and publishes a
# blank-but-parseable board). Added because the guards shipped that day were
# INERT: every one of these names was filed into the ledger and then dropped at
# drain time, because `red` was computed against SCHEDULED_GRADE_SOURCES alone.
# MEASURED: 17 of 17 filed export sources produced an empty red[].
#
# WHY A SECOND TUPLE RATHER THAN MORE NAMES IN THE FIRST. Two different failure
# tests, and collapsing them would make one of the two wrong:
#   grade source - "wrote 0 rows" IS the failure, and ABSENCE is the worst case
#                  (the step never ran), so a missing record is itself RED.
#   export       - the step decides for itself what broke and says so with
#                  ok=False. Row count is not the test: a healthy export can
#                  legitimately roll up zero rows, and several of these are
#                  gated off on a normal night (no slate today, no odds key,
#                  monthly-only steps), so alarming on ABSENCE here would fire
#                  nightly and train the reader to ignore the section. Silence
#                  from an export means "did not run"; the ok=True rows the
#                  exports now file are what distinguish that from "ran and
#                  found nothing", without manufacturing a red.
# Both land in the same red[] array, because deploy/nightly-build.sh prints
# that array and a dark board deserves the same shout as a dead ingest. They
# stay TELLABLE APART in the payload through each row's `kind`.
#
SCHEDULED_EXPORTS = (
    # /mlbstats/ leaderboards: the team-rollup guard behind the Offense+ outage
    "hitter_leaderboards", "starter_leaderboards", "bullpen_leaderboards",
    "leverage_leaderboards", "leverage_batters", "leverage_starters",
    "hitter_bat_side",
    # DEM+ board: the zero-rollup guard, and the framing tripwire that fires if
    # MLB's run line changes shape and the recovered framing residual goes to zero
    "defense_leaderboards", "defense_published_fielding",
    # The eWAR board: a coverage refusal (a degenerate WAR read) leaves the
    # previous file on disk and files here, and the empty-block guard on
    # `players` / `teams` files under the same name. Watched because the page
    # paints "being computed" on a missing payload, so a silent failure looks
    # to a reader exactly like a board that has not been built yet.
    "war_leaderboards",
    # /fantasy/ + /dfs/ + /betting/, all of which read the same probables feed
    "fantasy_schedule", "fantasy_teams_context", "fantasy_export",
    "dfs_schedule", "dfs_slate", "betting_export",
    # section joins that publish a dark chart when they resolve nothing
    "ifa_efv_join", "fa_prospect_arc", "draft_overperformance",
    # org authority: a blank parent-org map silently re-orgs the whole board
    "mlbam_parent_org_map",
    # FA identity substrate. Added 2026-08-06, closing a gap this list caused:
    # fa_export._record_identity_outage filed a row for the outage that blanked
    # 79 free agents, and because the name was missing here the row was
    # filtered out of red[] and the deploy shell never printed INGEST RED for
    # it. The ledger knew and the operator did not.
    "fa_class_identity",
    # The /mlbstats/ leaderboard join that bakes the HEM+/REM+/SEM+/leverage
    # tiles onto every MLB player card (mlb_player_export._skill_index). The
    # four artifacts above are watched as they are WRITTEN; this row is the
    # only watch on whether they could be READ back at bake time, which is a
    # separate failure with the same blank result on every card.
    "mlb_card_skill_index",
    # Team Outlook's farm columns (proj_export._org_farm_blocks). Reads
    # timeseries.json, the artifact that was found truncated mid-file, and a
    # truncation empties the farm block on all 30 rows without erroring.
    "proj_team_outlook_farm",
    # The eFV regen tripwires (tools/efv_regen_tripwire). Added 2026-08-07,
    # lane T. Files ok=False ONLY when the instrument could not observe the
    # regen at all - a missing dataset report, an unfittable production stack,
    # an unwritable ledger. A tripwire that FIRES is not a red: it is a real
    # data event, it rides log.warning and the ledger, and the measured base
    # rate is about one regen in three. Named here so that the dead-watch case
    # survives write_ingest_health's drain instead of being filed as
    # 'unwatched' and dropped, which is exactly what happened to
    # fa_class_identity for a day.
    "efv_regen_tripwire",
    # The /management/ board, watched on the same reasoning as /hof/ below.
    "mgmt_export",
    # The /management/ decision ledger (step 6b7e: management_decisions.json,
    # management_baseline.json and the data/mgmt_decisions/ shards). Watched
    # for a raise: the page renders four tabs dark on a missing ledger. On a
    # box without the play corpus the step records nothing and the committed
    # artifacts stand (an export absent from a run is not a red, see below).
    "mgmt_decisions",
    # The /hof/ board. Watched for the same reason as the arbitration board
    # below: the page paints an empty state on a missing payload, so a silent
    # failure is invisible to a reader and to an operator alike.
    "hof_export",
    # The /arbitration/ board. Watched because a silent failure
    # here empties a whole module rather than erroring.
    "arbitration_export",
    # The per-season eWAR substrate and the multi-year window lab. Both refuse
    # rather than publish (a substrate on another eWAR build; a window too thin
    # to carry a pool), and both file an ok=True heartbeat on a good run, so
    # "ran and refused" is distinguishable from "never ran". A refusal filed
    # under a name this list does not hold never reaches the deploy shell's
    # INGEST RED, which is the inert-guard defect the war_leaderboards comment
    # above records. Placed HERE, below mgmt_export, on purpose:
    # test_mgmt_export scans a fixed window of this tuple's text.
    "war_seasons", "mlbstats_windows",
    # The /ledger/ Club Ledger board (step d10e: ledger_board.json). Watched
    # because the page paints its load-error sentence on a missing payload,
    # which reads to a visitor exactly like a board that has not been built.
    # Appended BELOW mlbstats_windows on purpose: nothing may sit above
    # mgmt_export (test_mgmt_export scans a fixed window of this tuple's text).
    "ledger_export",
    # The /franchise/ board (step 6b7d: franchise_board.json). Watched because
    # the page paints its load-error sentence on a missing payload and the
    # exporter REFUSES (FranchiseRefusal) when fewer than 30 clubs resolve on
    # a graded branch, leaving the previous file on disk: without this row a
    # refusal never reaches INGEST RED. Appended BELOW ledger_export on purpose
    # (test_mgmt_export scans a fixed window above mgmt_export).
    "franchise_export",
    # The postseason series cache (step d8p, postseason.py): the one
    # postseason results source, 2000 to the live season. Watched because a
    # failed fetch leaves yesterday's live file standing, which reads exactly
    # like a quiet night. Appended BELOW franchise_export on purpose
    # (test_mgmt_export scans a fixed window above mgmt_export).
    "postseason_cache",
    # THE CLOSE-ODDS CAPTURE. Not an export this pipeline runs at all: it is
    # tools/betting_close_job.py, on its own cron, and that is exactly why it is
    # watched from here. The job exits 0 on every legitimate no-op, so a cron
    # that was never installed, or is installed in the wrong timezone window,
    # looks identical in the log to a healthy evening before first pitch.
    # Measured 2026-08-09: 4 open snapshots cached, ZERO close snapshots ever,
    # so CLV was ungradeable for every slate on record and nothing said so.
    # The row is filed off .cache/odds/ (which survives `git checkout -- .`),
    # never off a heartbeat (data/job_heartbeat.json does not).
    "betting_close_capture",
    # THE POSTED-LINEUP CAPTURE (2026-09-17). Same shape and the same reason:
    # tools/betting_lineup_job.py is dark, spends nothing and exits 0 on every
    # legitimate no-op, so a */15 TZ=UTC cron that was never installed reads in
    # the log exactly like a quiet afternoon. That is precisely how the close
    # capture sat at ZERO snapshots for months with nothing saying so, and a
    # lineup capture is the same kind of loss: evidence about what was posted
    # at an instant, which cannot be rebuilt afterwards. Filed off
    # .cache/lineup_captures/, which survives `git checkout -- .`. This
    # pipeline never imports or runs the job: 5j phase 1 stays dark.
    "betting_lineup_capture",
    # THE NIGHTLY-GAP SENTINEL (2026-08-19). The 2026-08-15 and 2026-08-17
    # nightlies never ran and NOTHING said so: two leaderboard vintage nights,
    # a DFS slate and two days of schema-3 dark-capture accrual are gone, and
    # the loss is permanent because a vintage is evidence about what was
    # knowable that night and cannot be rewritten later. Same design as
    # betting_close_capture: the row is filed off the two .cache/ archives
    # that survive `git checkout -- .` (leaderboard_vintages/, dfs_history/),
    # never off a heartbeat, because a heartbeat cannot witness a night the
    # pipeline did not run at all. See _vintage_capture_gap.
    "vintage_capture_gap",
    # The Savant minors refresh behind the PROSPX "Statcast (tracked parks)"
    # card (step 6b2a, owner answer M25-3). A refused or failed fetch keeps the
    # last good CSV and files ok=False here, so a card frozen at an old date
    # shouts.
    "savant_aaa_batters",
    # The postseason bracket simulator (step d10f, docs/betting-2026-10/
    # BRACKET_SIM_GATE.md 9): a crash writes a crash entry and no number, and
    # the Futures panel falls back to the end-of-season stamp. Watched so the
    # deploy shell prints the red instead of the page going quietly stale.
    "bracket_sim",
    # The In-Game Management nightly (step 9e-pre0e, owner answer 2026-09-25):
    # the open season's play corpus and the management chain on it. A skip on
    # an unchanged corpus files ok=True with the reason; a raise files a red.
    "mgmt_nightly",
    # The nightly's own StatsAPI standings read (fa_fit_backtest.standings_now,
    # called by proj_export's current-season attach; step d9-std inside
    # rebuild_only, STANDINGS_9). It returns {} on a failed read, and Team
    # Outlook, Futures, Franchise and F-SCORE then degrade with nothing saying
    # so. Filed off what the read returned and the cache file's age; it never
    # fetches.
    "statsapi_standings",
    # The Source Updates list on /glossary/ (step d10g: source_updates.json,
    # owner ask 2026-10-02). Read-only over the snapshot tables; a raise or a
    # payload over its size line leaves the previous file and files a red here.
    "source_updates_export",
    # The Model Updates record (LIBRARY_11, model_updates.py, data/
    # model_updates.json), daily after the eFV progress ledger and monthly
    # after the registry refresh. A raise, or a note row the validator
    # rejects, files a red here.
    "model_updates",
    # The Spotrac team contract pages' FORMAT SENTINEL (SPOTRAC_POS_CODES_2026_10,
    # spotrac.contract_format_report). On 2026-10-03 Spotrac's 'Pos' column
    # began serving numeric ids and the parser passed them through: 128 pitcher
    # cards turned into hitter cards and nothing said so. Filed red when a
    # position, age or money cell has the wrong type, a table loses its year
    # columns, or the coded positions stop matching StatsAPI's side.
    "spotrac_contracts_format",
    # The MLB transaction events nightly (step 9e-pre0g, mlb_events.py): the
    # cache refresh and the events builder. A failed StatsAPI refresh leaves
    # the cache at its last month, which reads like a quiet week; the row
    # files ok=False so the deploy shell prints it.
    "mlb_events",
    # The steal context beside the /management/ steal rows (step 9e-pre0f,
    # W11 stage 1): runner sprint speed percentile and catcher pop time. A
    # raise, or a build with no steal rows, files a red and the committed file
    # stands.
    "mgmt_steal_context",
)

# The Awards board's health row (steps d10h and 6b7f, _export_awards_board,
# AWARDS_PLAN 4.9). Appended BELOW statsapi_standings and every row above it,
# and only inside the module flag: while awards_core.AWARDS_LIVE is False the
# exporter writes its preview alone and the row stays unwatched; the flip
# (AWARDS_11) turns the flag and the row joins the tuple on the same commit.
# Nothing above mgmt_export moves (test_mgmt_export scans a fixed window).
try:
    from awards_core import AWARDS_LIVE as _AWARDS_LIVE
except Exception:   # noqa: BLE001 - without the module the tuple stands as written
    _AWARDS_LIVE = False
if _AWARDS_LIVE:
    SCHEDULED_EXPORTS = SCHEDULED_EXPORTS + ("awards_export",)

# Recorded by _record_ingest during a run; drained by write_ingest_health.
_INGEST_HEALTH: list[dict] = []


def _ingest_kind(source: str) -> str:
    """Which watch-list a source belongs to: 'grade_source', 'export', or
    'unwatched'.

    Rides on each ledger row so the payload keeps the two RED classes apart
    without growing a second top-level array (the deploy shell and the
    payload-shape contract both read exactly {generated_at, mode, sources,
    red}). 'unwatched' is a real answer, not a fallthrough: just_baseball and
    espn_article_probe legitimately publish nothing for months, and they are
    reported without ever being alarmed on."""
    if source in SCHEDULED_GRADE_SOURCES:
        return "grade_source"
    if source in SCHEDULED_EXPORTS:
        return "export"
    return "unwatched"


def _record_ingest(source: str, ok: bool, n_rows: int = 0, message: str = "",
                   scope: str = "", log: logging.Logger | None = None) -> None:
    """Log one source's ingest outcome for this run.

    `ok=True` also stamps the durable source_checks ledger. Per that table's
    own contract we stamp ONLY on a verified-good check: a parser that
    silently returned nothing must leave the OLD stamp in place, because a
    frozen stamp is the signal."""
    _INGEST_HEALTH.append({
        "source": source, "scope": scope, "ok": bool(ok),
        "n_rows": int(n_rows or 0), "message": message or "",
        "date": date.today().isoformat(),
    })
    if ok:
        try:
            from storage import record_source_check
            record_source_check(source, scope, n_rows)
        except Exception:                                # noqa: BLE001
            if log:
                log.warning("ingest health: could not stamp source_checks for %s", source)
    if log:
        if ok:
            log.info("ingest health: %s OK (%d rows)%s", source, n_rows,
                     f" - {message}" if message else "")
        else:
            log.error("ingest health: %s FAILED (%d rows) %s", source, n_rows, message)


# The nightly standings read's health row (STANDINGS_9, STANDINGS_PLAN 4.5).
STATSAPI_STANDINGS_CLUBS = 30
STATSAPI_STANDINGS_MAX_AGE_H = 48.0


def _statsapi_standings_health(season: int, *, log: logging.Logger | None = None,
                               reads: dict | None = None,
                               cache_dir: Path | None = None,
                               calendar_dir: Path | None = None,
                               today: date | None = None,
                               now_ts: float | None = None,
                               record=None) -> tuple[bool, int, str]:
    """File the `statsapi_standings` ingest row for the nightly's own standings
    read, fa_fit_backtest.standings_now(season), which proj_export's
    current-season attach has just made. Reads only what is already in this
    process and on disk, and NEVER FETCHES:

      * how many clubs that call returned (fa_fit_backtest.STANDINGS_NOW_CLUBS,
        or `reads` in a test); no entry means the call never ran this pass;
      * the cache file .cache/statsapi_standings_{season}.json and its mtime;
      * the regular-season dates from the cached StatsAPI /seasons payload
        (.cache/fantasy_schedule/season_{season}.json).

    ok when the read returned all 30 clubs and, during the regular season, the
    cache file is under 48 hours old. Red when standings_now returned {} or
    fewer than 30 clubs, did not run, or (in season) the file is 48 hours old
    or absent. Outside the regular season, or with no calendar on disk, the
    age is printed and not judged. The message names the cache path and its
    modification time either way. Returns (ok, n_clubs, message)."""
    root = Path(__file__).resolve().parent
    cache_dir = Path(cache_dir) if cache_dir is not None else root / ".cache"
    calendar_dir = (Path(calendar_dir) if calendar_dir is not None
                    else root / ".cache" / "fantasy_schedule")
    today = today or date.today()
    now_ts = time.time() if now_ts is None else float(now_ts)
    if reads is None:
        _fb = sys.modules.get("fa_fit_backtest")
        reads = dict(getattr(_fb, "STANDINGS_NOW_CLUBS", None) or {})
    n = reads.get(int(season))

    path = cache_dir / f"statsapi_standings_{int(season)}.json"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    age_h = None if mtime is None else max(0.0, (now_ts - mtime) / 3600.0)

    start = end = None
    try:
        cal = json.loads((calendar_dir / f"season_{int(season)}.json")
                         .read_text(encoding="utf-8"))
        for row in (cal or {}).get("seasons") or []:
            if str((row or {}).get("seasonId")) == str(int(season)):
                start = row.get("regularSeasonStartDate")
                end = row.get("regularSeasonEndDate")
                break
    except (OSError, ValueError):
        pass
    in_season = None
    if start and end:
        in_season = str(start) <= today.isoformat() <= str(end)

    problems = []
    if n is None:
        problems.append(f"standings_now({season}) did not run in this pass")
    elif n == 0:
        problems.append(f"standings_now({season}) returned {{}}")
    elif n < STATSAPI_STANDINGS_CLUBS:
        problems.append(f"standings_now({season}) returned {n} of "
                        f"{STATSAPI_STANDINGS_CLUBS} clubs")
    if in_season:
        if mtime is None:
            problems.append("the cache file is absent during the regular season")
        elif age_h >= STATSAPI_STANDINGS_MAX_AGE_H:
            problems.append(f"the cache file is {age_h:.1f} h old during the "
                            f"regular season (limit {STATSAPI_STANDINGS_MAX_AGE_H:.0f} h)")

    if mtime is None:
        stamp = f"cache {path} absent"
    else:
        stamp = (f"cache {path} modified "
                 f"{datetime.fromtimestamp(mtime, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
                 f" ({age_h:.1f} h old)")
    if in_season is None:
        window = "regular-season dates not on disk, age not judged"
    elif in_season:
        window = f"in the regular season ({start} to {end})"
    else:
        window = f"outside the regular season ({start} to {end}), age not judged"
    ok = not problems
    head = (f"standings_now({season}) returned {n} of {STATSAPI_STANDINGS_CLUBS} clubs"
            if ok else "; ".join(problems))
    message = f"{head}; {stamp}; {window}"
    (record or _record_ingest)("statsapi_standings", ok, int(n or 0), message,
                               scope=str(int(season)), log=log)
    return ok, int(n or 0), message


# ===========================================================================
# THE NIGHTLY-GAP SENTINEL (2026-08-19)
# ===========================================================================
# WHY: the 2026-08-15 and 2026-08-17 nightlies missed silently. Every existing
# watch fires INSIDE a run (a step that ran and produced nothing), so a night
# on which the pipeline never started produced no ledger row, no RED line and
# no ingest_health.json at all - absence read as success, the TJStats shape
# again, one level up. The cost is permanent: a leaderboard vintage is
# evidence about what was knowable that night, so a missed capture cannot be
# backfilled from a fresher file without manufacturing the leak the archive
# exists to close.
#
# The sentinel therefore runs on the NEXT night that does run, off the two
# .cache/ per-date archives (the same stores the incident holed), and lists
# the missing dates by name. Severity is graded:
#   red    - the newest vintage is >= VINTAGE_GAP_STALE_DAYS calendar days
#            back (an ONGOING outage, ~36h+ old at the nightly hour), or two
#            or more dates are missing inside the window (the exact 08-15 +
#            08-17 shape);
#   yellow - one missing date, or the DFS archive tail is stale while the
#            vintage tail is current (a DFS-only miss; an off day or a
#            no-slate stretch can legitimately look like this and the message
#            says so).
# The window is short ON PURPOSE: a hole is permanent, so an unbounded window
# would print the same red every night until the season ended, which is how a
# reader learns to skip the line. Three nights of shouting per hole, then the
# frozen count in coverage()'s missing_dates remains the durable record.
#
# SEASON FENCE, two conditions and both must hold before anything can fire:
# the month is March..November AND the archive holds a current-year entry.
# Off-season the boards freeze and the newest vintage goes stale legitimately;
# a sentinel that fired all winter would be dead by opening day.
VINTAGE_GAP_WINDOW_DAYS = 3
VINTAGE_GAP_STALE_DAYS = 2   # newest entry 2+ calendar days back is ~36h+ old
                             # at the nightly hour: two straight missed nights

# THE ODDS LEG (2026-09-06). Third archive, same doctrine, same permanence: an
# OPENING price is evidence about what the market believed before first pitch,
# and a slate whose open was never captured can never be graded for CLV or
# priced from a pregame book again. It was invisible until now.
#
# MEASURED on .cache/odds the day this was written: 22 snapshots, every one of
# kind "open", covering 22 distinct slate dates across the 31-day span
# 2026-08-06..2026-09-05. NINE slate days inside that span hold no open capture
# at all: 08-15, 08-17, 08-22, 08-25, 08-26, 08-28, 08-29, 09-01, 09-02. Two of
# those (08-15, 08-17) are the nights the vintage leg was built for; the other
# seven were silent. That is the gap this leg makes visible.
#
# OPT-IN AT THE CALL SITE, deliberately. `odds_dir=None` leaves the leg quiet,
# so a box with no EEPHUS_ODDS_API_KEY cannot capture, cannot be blamed for not
# capturing, and does not learn to skip a red line it can do nothing about. The
# nightly passes the real directory only when betting_ingest.configured().


def _odds_slate_dates(dirpath: Path, year: int) -> list[date]:
    """Sorted US-Eastern SLATE dates the cached open-odds archive covers,
    current year only.

    NOT the filename date. A snapshot is named for its UTC capture stamp
    (`YYYY-MM-DD-HHMM.json`) while the slate it belongs to is US-Eastern: a
    10:10pm ET first pitch closes after UTC midnight, which is why
    2026-08-09-0133.json carries slate_date 2026-08-08. Counting filenames
    would report 08-08 missing and 08-09 captured twice, both wrong.

    The wrapper's own `slate_date` field is authoritative and is read first.
    The fallback, for a pre-slate_date or unreadable file, converts the
    filename stamp at the same fixed EDT offset betting_ingest.slate_date_of
    uses; measured 2026-09-06, that fallback reproduces the wrapper's
    slate_date on 22 of 22 cached snapshots. Cost of the read: 22 files,
    1.9 MB, 15 ms.

    Reads only; never raises past its caller."""
    p = Path(dirpath)
    if not p.exists():
        return []
    out: list[date] = []
    for f in sorted(p.glob("*.json")):
        stem = f.stem
        try:
            stamp = datetime.strptime(stem, "%Y-%m-%d-%H%M")
        except ValueError:
            continue                      # not a snapshot filename, skip it
        slate = None
        try:
            wrap = json.loads(f.read_text(encoding="utf-8"))
            sd = (wrap or {}).get("slate_date")
            if isinstance(sd, str):
                slate = date.fromisoformat(sd)
        except (OSError, ValueError, TypeError):
            slate = None
        if slate is None:
            slate = (stamp - timedelta(hours=4)).date()
        if slate.year == year:
            out.append(slate)
    return sorted(set(out))


def _archive_dates(dirpath: Path, year: int) -> list[date]:
    """Sorted date-stemmed *.json entries from one per-date archive, current
    year only. Filenames only, nothing parsed: the sentinel asks WHEN capture
    happened, not whether the capture was any good."""
    p = Path(dirpath)
    if not p.exists():
        return []
    out = []
    for f in p.glob("*.json"):
        try:
            d = date.fromisoformat(f.stem)
        except ValueError:
            continue
        if d.year == year:
            out.append(d)
    return sorted(out)


def _vintage_capture_gap(*, today: date | None = None,
                         vintage_dir: Path | None = None,
                         dfs_dir: Path | None = None,
                         odds_dir: Path | None = None) -> dict:
    """The nightly-gap verdict: {ok, severity, message, newest_vintage,
    newest_dfs, newest_odds, missing_vintage_dates, missing_dfs_dates,
    missing_odds_dates, n_vintages_in_window, n_odds_in_window,
    odds_archive_empty}.

    Pure read, injectable dirs and clock for tests, never raises past its
    caller's try. `today` is INCLUDED in the window because the daily path
    records this row AFTER step 9e-pre wrote tonight's vintage, so a missing
    today means tonight's own capture failed, not that it has not run yet.

    `odds_dir` is the ONE argument whose default means OFF rather than
    'use the standard location': None leaves the odds leg silent. Capture
    there is gated on a credential this pipeline does not always hold, and a
    sentinel that reds every night on an unarmed box teaches a reader to skip
    the line. The nightly call site passes .cache/odds only when
    betting_ingest.configured() says a capture was even possible.

    AN EMPTY ODDS ARCHIVE IS RED, and that is deliberate. Passing odds_dir is
    already proof the capture is ARMED, so an in-season archive holding nothing
    for this year does not mean 'not watching yet', it means the armed capture
    has produced nothing all season and every slate so far is unpriced. That is
    the exact state this leg exists to catch, and an earlier draft was blind to
    it: the whole leg sat behind `if o_dates:`, so an empty directory left
    newest_odds None, missing_odds_dates empty and severity untouched, and the
    row read ok forever. The verdict is carried on its own key,
    odds_archive_empty, so a reader can tell 'never captured' from 'captured and
    then stopped'. Note the asymmetry with the VINTAGE leg, which stays quiet on
    an empty archive: the vintage leg is always on and cannot tell a first night
    from an outage, while this one is only ever switched on by a caller that
    already checked the credential.

    ONE STATE STILL ESCAPES, and it escapes by ordering: an empty CURRENT-SEASON
    vintage archive returns 'no_archive' above, before the odds leg is reached,
    so a box with nothing running at all reports quiet rather than red. That is
    the pipeline being dark, not the odds capture being broken, and the vintage
    leg owns it."""
    root = Path(__file__).parent
    t = today or date.today()
    vdir = Path(vintage_dir) if vintage_dir else (root / ".cache" / "leaderboard_vintages")
    ddir = Path(dfs_dir) if dfs_dir else (root / ".cache" / "dfs_history")

    quiet = {"ok": True, "severity": "ok", "newest_vintage": None,
             "newest_dfs": None, "newest_odds": None,
             "missing_vintage_dates": [], "missing_dfs_dates": [],
             "missing_odds_dates": [], "n_vintages_in_window": 0,
             "n_odds_in_window": 0, "odds_archive_empty": False}
    if not (3 <= t.month <= 11):
        quiet["severity"] = "off_season"
        quiet["message"] = (f"month {t.month} is outside March..November; the "
                            "vintage-gap sentinel is quiet in the offseason")
        return quiet

    v_dates = _archive_dates(vdir, t.year)
    if not v_dates:
        quiet["severity"] = "no_archive"
        quiet["message"] = ("no current-season leaderboard vintage exists yet; "
                            "the sentinel starts watching at the first capture")
        return quiet

    newest_v = v_dates[-1]
    have_v = set(v_dates)
    window_start = max(v_dates[0], t - timedelta(days=VINTAGE_GAP_WINDOW_DAYS))
    missing_v, cur = [], window_start
    while cur <= t:
        if cur not in have_v:
            missing_v.append(cur.isoformat())
        cur += timedelta(days=1)
    stale_v = (t - newest_v).days >= VINTAGE_GAP_STALE_DAYS
    n_in_window = sum(1 for d in v_dates if d >= window_start)

    # The DFS leg. dfs_history/ only gains a file on a day a priced slate
    # published, so a hole here is AMBIGUOUS in a way a vintage hole is not:
    # an off day, the All-Star break and a legitimately empty board all leave
    # no file. It can therefore raise YELLOW at most, and only off its own
    # stale tail while the vintage tail is current (pipeline running, DFS not
    # archiving) - the shape of a dead _archive_slate rather than a dark park.
    d_dates = _archive_dates(ddir, t.year)
    newest_d = d_dates[-1] if d_dates else None
    missing_d, stale_d = [], False
    if d_dates:
        dstart = max(d_dates[0], window_start)
        have_d, cur = set(d_dates), dstart
        while cur <= t:
            if cur not in have_d:
                missing_d.append(cur.isoformat())
            cur += timedelta(days=1)
        stale_d = (t - newest_d).days >= VINTAGE_GAP_STALE_DAYS

    # The ODDS leg. Off entirely unless the caller handed us a directory (see
    # the docstring). Graded like the VINTAGE leg, not like the DFS one: a
    # slate with no open capture is a permanent hole in the pricing record,
    # not an ambiguous off day, because the Odds API returns a board on every
    # calendar day of the season and an empty board still writes a file.
    # An armed leg with an EMPTY current-year archive is its own red, not a
    # silence: see the docstring. `odds_dir` truthy is the arming proof.
    o_dates = _odds_slate_dates(Path(odds_dir), t.year) if odds_dir else []
    newest_o = o_dates[-1] if o_dates else None
    missing_o, stale_o, n_o_in_window = [], False, 0
    odds_empty = bool(odds_dir) and not o_dates
    if o_dates:
        ostart = max(o_dates[0], t - timedelta(days=VINTAGE_GAP_WINDOW_DAYS))
        have_o, cur = set(o_dates), ostart
        while cur <= t:
            if cur not in have_o:
                missing_o.append(cur.isoformat())
            cur += timedelta(days=1)
        stale_o = (t - newest_o).days >= VINTAGE_GAP_STALE_DAYS
        n_o_in_window = sum(1 for d in o_dates if d >= ostart)

    if (stale_v or len(missing_v) >= 2 or stale_o or len(missing_o) >= 2
            or odds_empty):
        severity = "red"
    elif missing_v or missing_o or (stale_d and not stale_v):
        severity = "yellow"
    else:
        severity = "ok"

    bits = []
    if stale_v:
        bits.append(f"newest leaderboard vintage is {newest_v.isoformat()}, "
                    f"{(t - newest_v).days} day(s) back (>= "
                    f"{VINTAGE_GAP_STALE_DAYS} days is an ongoing outage)")
    if missing_v:
        bits.append(f"vintage night(s) MISSING: {', '.join(missing_v)} - a "
                    "missed capture cannot be backfilled and the night is lost")
    if stale_d:
        bits.append(f"newest DFS slate archive is {newest_d.isoformat()} while "
                    "the vintage tail is current; an off day or empty slate "
                    "can look like this, a dead _archive_slate also does"
                    if not stale_v else
                    f"newest DFS slate archive is {newest_d.isoformat()}")
    if missing_d and severity != "ok":
        bits.append(f"DFS archive day(s) without a file in the window: "
                    f"{', '.join(missing_d)} (off days are legitimate here)")
    if stale_o:
        bits.append(f"newest OPEN ODDS capture is {newest_o.isoformat()}, "
                    f"{(t - newest_o).days} slate day(s) back; nothing on the "
                    "board since can be priced pregame or graded for CLV")
    if missing_o:
        bits.append(f"slate day(s) with NO open odds capture: "
                    f"{', '.join(missing_o)} - an opening price cannot be "
                    "recaptured, so those slates are unpriceable for good")
    if odds_empty:
        bits.append(f"the open-odds archive holds NOTHING for {t.year} while "
                    "the capture is ARMED (this leg only runs when a key is "
                    f"configured): {odds_dir} has no {t.year} snapshot, so "
                    "every slate this season is unpriced and no CLV is gradable")
    if severity == "ok":
        msg = (f"capture current: newest vintage {newest_v.isoformat()}, "
               f"newest DFS slate "
               f"{newest_d.isoformat() if newest_d else 'none this season'}, "
               f"no gap inside the {VINTAGE_GAP_WINDOW_DAYS}-day window")
        if odds_dir:
            msg += (", newest open odds "
                    f"{newest_o.isoformat() if newest_o else 'none this season'}")
    else:
        msg = f"!!! VINTAGE GAP {severity.upper()}: " + "; ".join(bits)

    return {"ok": severity == "ok", "severity": severity, "message": msg,
            "newest_vintage": newest_v.isoformat(),
            "newest_dfs": newest_d.isoformat() if newest_d else None,
            "newest_odds": newest_o.isoformat() if newest_o else None,
            "missing_vintage_dates": missing_v,
            "missing_dfs_dates": missing_d,
            "missing_odds_dates": missing_o,
            "n_vintages_in_window": n_in_window,
            "n_odds_in_window": n_o_in_window,
            "odds_archive_empty": odds_empty}


def write_ingest_health(out_dir: Path, mode: str,
                        log: logging.Logger | None = None) -> dict:
    """Write data/ingest_health.json and emit a RED summary line per scheduled
    grade source that wrote no rows and per scheduled export that reported a
    failure.

    Shape:
      {generated_at, mode, sources: [{source, scope, kind, date, ok, n_rows,
                                      message, last_ok_at, last_ok_rows}],
       red: [source, ...]}

    `last_ok_at` comes from the durable source_checks table, so a source that
    produced nothing THIS run still reports the last date it genuinely worked
    - the single number that would have made the TJStats gap obvious on day
    one instead of day eight.

    `kind` (see _ingest_kind) is how a reader tells a dead INGEST from a dark
    EXPORT while both share one red[] array. It rides on the row rather than in
    a second top-level key on purpose: the deploy shell indexes `sources` by
    name and would otherwise need a matching edit to see the new class at
    all."""
    try:
        from storage import load_source_checks
        checks = load_source_checks()
    except Exception:                                    # noqa: BLE001
        checks = {}

    rows: list[dict] = []
    for r in _INGEST_HEALTH:
        stamp = checks.get((r["source"], r.get("scope") or "")) or {}
        rows.append({**r,
                     "kind": _ingest_kind(r["source"]),
                     "last_ok_at": stamp.get("checked_at"),
                     "last_ok_rows": stamp.get("n_rows")})

    seen = {r["source"] for r in rows}
    # A scheduled GRADE SOURCE that produced no ledger entry AT ALL is the
    # worst case (its step never ran, or crashed before recording) - surface it
    # rather than letting absence read as success. Deliberately NOT extended to
    # SCHEDULED_EXPORTS: those steps are conditionally gated (daily vs monthly,
    # no slate, no odds key) and would file a nightly false red, which is how a
    # reader learns to skip the section. See the tuple's comment.
    for src in SCHEDULED_GRADE_SOURCES:
        if src not in seen:
            stamp = checks.get((src, "")) or {}
            rows.append({"source": src, "scope": "", "ok": False, "n_rows": 0,
                         "kind": "grade_source",
                         "message": "no ingest attempt recorded this run",
                         "date": date.today().isoformat(),
                         "last_ok_at": stamp.get("checked_at"),
                         "last_ok_rows": stamp.get("n_rows")})

    # Two tests, one array. A grade source is judged on ROW COUNT (writing zero
    # is the TJStats outage). An export is judged on its OWN ok flag only: it
    # files ok=False when it catches its silent-empty, and judging it on rows
    # would turn a legitimately-zero rollup or a healthy ok=True heartbeat
    # (n_rows defaults to 0) into a manufactured red.
    red = sorted({r["source"] for r in rows
                  if r["kind"] == "grade_source"
                  and (not r["ok"] or r["n_rows"] <= 0)}
                 | {r["source"] for r in rows
                    if r["kind"] == "export" and not r["ok"]})
    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "mode": mode,
        "sources": sorted(rows, key=lambda r: (r["source"], r["scope"])),
        "red": red,
    }
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "ingest_health.json").write_text(
            json.dumps(payload, indent=1), encoding="utf-8")
    except OSError as e:
        if log:
            log.warning("ingest health: could not write ingest_health.json: %s", e)

    if log:
        log.info("=" * 64)
        log.info("INGEST HEALTH (%s)", mode)
        log.info("%-22s %-12s %-10s %6s  %s",
                 "source", "kind", "status", "rows", "last OK")
        log.info("-" * 64)
        for r in payload["sources"]:
            # The table's verdict must match red[]'s, or the two halves of this
            # block disagree in the same log: an export that ran clean and
            # rolled up nothing is OK here because it is not red there.
            status = "OK" if (r["source"] not in red) else "FAIL"
            log.info("%-22s %-12s %-10s %6d  %s", (r["source"] + (
                f"/{r['scope']}" if r["scope"] else ""))[:22],
                r.get("kind") or "unwatched",
                status, r["n_rows"], r.get("last_ok_at") or "never")
        log.info("-" * 64)
        for src in red:
            hit = next((r for r in payload["sources"] if r["source"] == src), {})
            if hit.get("kind") == "export":
                log.error("RED: scheduled export %r reported a failure this run "
                          "(last OK %s). %s", src,
                          hit.get("last_ok_at") or "never", hit.get("message") or "")
            else:
                log.error("RED: scheduled grade source %r wrote 0 rows this run "
                          "(last OK %s). %s", src,
                          hit.get("last_ok_at") or "never", hit.get("message") or "")
        if not red:
            log.info("ingest health: all scheduled grade sources wrote rows "
                     "and every scheduled export reported clean")
        log.info("=" * 64)
    return payload


def _patch_export_run_summary(out_path: Path, log: logging.Logger) -> None:
    """Refresh boot JSON's run summary after finish_run() has completed.

    Also stamps the two-track `data_freshness` block (grades = last monthly
    run, transactions/IL = last run of any kind) so the front-end can render
    data-aware 'as of' labels that distinguish daily-fresh fast-moving data
    from monthly grade data.
    """
    try:
        payload = json.loads(out_path.read_text(encoding="utf-8"))
        payload["run"] = latest_run_summary()
        try:
            from storage import data_freshness as _data_freshness
            payload["data_freshness"] = _data_freshness()
        except Exception:
            log.exception("could not compute data_freshness for %s", out_path)
        try:
            import orjson as _orjson
            blob = _orjson.dumps(payload, option=_orjson.OPT_NON_STR_KEYS)
        except ImportError:
            blob = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        # ATOMIC (2026-08-06). This used to write IN PLACE, and data/timeseries.json
        # is 74MB with TWO writers: storage.export_timeseries_json builds it and this
        # re-serialises it to stamp a run summary, with nothing serialising the pair.
        # An in-place write that is interrupted, or that races the other writer,
        # leaves a TRUNCATED file that is still structurally plausible enough to be
        # served. That happened: the file was found with a JSON decode error 42.9MB
        # in, and because it is gitignored there was nothing to restore from. It also
        # produced a phantom bug, five org-test "failures" that were really the test
        # reading a truncated file.
        # Same directory so os.replace is a same-filesystem rename, which is atomic:
        # a concurrent reader sees either the whole old file or the whole new one,
        # never a half-written one. This does not make the two writers safe to run
        # together, it makes an interrupted write survivable.
        tmp = out_path.with_name(out_path.name + f".tmp{os.getpid()}")
        try:
            tmp.write_bytes(blob)
            from storage import _atomic_replace
            _atomic_replace(tmp, out_path)
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass                       # already renamed, which is the good path
    except Exception:
        log.exception("could not patch latest run summary into %s", out_path)


def _chain_daily_and_stamp(out_path: Path, log: logging.Logger, chain) -> str:
    """Run the chained daily refresh, then leave EXACTLY ONE run-summary stamp.

    The number of writers to data/timeseries.json is a correctness property,
    not a performance one: it is 74MB and was found truncated once by a race
    between its two writers. run_daily stamps the file itself after its own
    finish_run, and that stamp is strictly newer than anything main() could
    write before chaining, so the monthly path must NOT stamp first.

    The stamp here covers only the path where the chain died before reaching
    its own. Without it a failed chain would serve the step-5 export, whose
    run and data_freshness blocks were read before finish_run, so the site's
    "as of" line would name the previous run.

    `chain` is a zero-argument callable so the ordering above can be tested
    without running a pipeline. Returns "chained" or "fallback".
    """
    try:
        chain()
        return "chained"
    except Exception:
        log.exception("chained daily refresh failed - monthly run already completed")
        # The DB's newest run on this path is the FAILED daily, so the as-of
        # block names it. grades_updated_at still resolves to the monthly run
        # that did complete, and a stamp naming a failed run beats no stamp.
        log.warning("stamping the run summary from the chain-failure fallback")
        _patch_export_run_summary(out_path, log)
        return "fallback"


from scrapers import scrape_all, probe
from storage import (
    init_db, insert_snapshots, start_run, finish_run,
    load_all_snapshots, load_statlines, upsert_statlines,
    insert_trades, load_trades,
    upsert_birth_dates, load_birth_dates,
    auto_debut_player,
    upsert_pitch_arsenals, load_pitch_arsenals,
    upsert_zone_metrics, load_zone_metrics, load_zone_metrics_meta,
    upsert_statcast_metrics, load_statcast_metrics, load_statcast_metrics_meta,
    upsert_sabermetrics, load_sabermetrics,
    upsert_career_war, load_career_war, load_career_war_meta,
    upsert_career_stats, load_career_stats, load_career_stats_meta,
    upsert_acquisitions, load_acquisitions,
    upsert_il_status, load_il_status,
    upsert_player_transactions, load_player_transactions,
    load_player_transactions_meta,
    upsert_roster_status, load_roster_status,
    upsert_source_events,
    export_timeseries_json, latest_run_summary,
    snapshot_board_metrics, snapshot_trade_values, snapshot_farm_ranks,
    snapshot_farm_grades, record_il_observation,
)
from consensus import (build_timeseries, ADOPT_NORMALIZED_CONSENSUS,
                       CONSTANT_ANCHOR_SOURCES)
from stats import (fetch_statlines_for, derive_statlines_from_career,
                   fetch_pitch_arsenal, fetch_sabermetrics,
                   fetch_career_stats,
                   bulk_fetch_season_stats, merge_bulk_into_career_cache,
                   bulk_resolve_ids,
                   bulk_fetch_mlb_debut_dates,
                   detect_debuts_from_index,
                   bulk_fetch_drafts,
                   bulk_fetch_ifa_signings,
                   bulk_fetch_il_status,
                   bulk_fetch_player_transactions,
                   derive_level_changes,
                   derive_roster_status,
                   fetch_team_affiliations,
                   PlayerIndex)
from trades import detect_trades
from stat_flags import is_pitcher as _is_pitcher


DAILY_STATCAST_TRACKED_LEVELS = {"MLB", "AAA", "AA", "A+", "A", "CPX"}


# v24 — Freshness gates dropped to 0 so every run refetches stats,
# debuts, zone metrics, and statcast metrics. The 24h HTTP cache in
# stats.py still absorbs duplicate-payload cost on same-day re-runs;
# this just stops the per-player skip from short-circuiting the API
# pass. --force is now a no-op for these gates (kept for HTTP cache).
#
# RUNTIME 2026-08-04 — 0 -> 1. At 0 these constants did not "refetch
# everything": they made four gates UNREACHABLE, because `_is_career_fresh`
# tests `days < max_age_days` and `days` is a non-negative integer, so
# `days < 0` is false for every row that has ever existed. The dead branches
# were the career `skipped_fresh` skip, the career-WAR skip, the transactions
# TTL skip, and the two "90% of the pool is fresh" whole-step gates for zone
# and Statcast metrics — roughly 80 lines of logic (and their log lines) that
# could never execute. Rather than delete gates that are genuinely wanted,
# restore the smallest TTL that makes them reachable.
#
# WHY 1 IS NOT A DATA CHANGE. `stats.CACHE_TTL_SECONDS` is 24h, so a second
# run inside the same day was already being served byte-identical payloads out
# of the HTTP cache: the refetch it performed could not produce different
# data, only re-pay the request, parse and DB-write cost. A 1-day TTL skips
# exactly that repayment. `_is_career_fresh` floors to whole days, so "fresh"
# means "stamped less than ~24h ago"; the normal nightly cadence (>= 24h
# apart) still refetches everything, and the monthly cadence (~30d) is not
# affected at all. What this buys is the case the v24 note did not consider:
# a run that crashes and is restarted the same day currently repays every
# per-player fan-out from scratch.
#
# ESCAPE HATCH: --force (force_refetch) still bypasses all of them, and it is
# no longer a no-op for these gates.
#
# INTERACTION with the 2026-08-04 incremental Statcast pass: skipped players'
# rows are not rewritten, so their `fetched_at` does not advance and the
# Statcast 90%-fresh whole-step gate will usually NOT fire on a restart. That
# is the safe ordering — the incremental gate inside the step is the precise
# one; the 90% gate is the coarse one.
CAREER_STATS_FRESH_DAYS = 1
ZONE_METRICS_FRESH_DAYS = 1
STATCAST_METRICS_FRESH_DAYS = 1

# WS-R (2026-07): positional-versatility freshness gate. Unlike the stats
# gates above (dropped to 0 so every run refetches fast-moving lines), versa
# is derived from SEASON-CUMULATIVE fielding games/starts that barely move
# day to day, yet the per-player StatsAPI fielding fetch (step 3a-ii) was the
# single slowest step in the pipeline: measured 437s. Gate the WHOLE artifact
# (positions_played.json carries no per-entry timestamps) — skip the refetch
# when it was regenerated within this window. --force (and an explicit
# EEPHUS_FULL=1 owner rebuild) override.
VERSA_FRESH_DAYS = 7

# WS-R (2026-07): eval-lab cadence gate. The 6b4 reliever/starter/hitter
# eval labs re-derive validation artifacts for ALREADY-validated (or already
# rejected) metrics; combined they cost ~500s (leverage 271s + reliever 185s
# + hitter 47s, plus the starter lab) yet their conclusions move on a
# monthly-plus horizon, not nightly. Skip a lab when its own eval artifact's
# generated_at is younger than this. EEPHUS_LABS=1 forces them all (for a
# metric-research session). The leaderboard EXPORTS they feed still run every
# run — only the slow re-validation is gated.
#
# RUNTIME 2026-08-04, OWNER-POLICY CHANGE: 30 -> 45. This is a deliberate
# change to a PUBLISHED re-validation cadence, not a tuning tweak, so it is
# recorded here as well as in the execution doc.
#
# WHY 30 was the worst possible value: the full monthly pipeline runs on the
# 1st of each calendar month (deploy/nightly-build.sh gates on
# `date +%d = 01`), i.e. every 28-31 days. A 30-day gate therefore expires
# essentially every single monthly run - the artifact is 28-31 days old when
# the gate reads it, so the gate NEVER skips in February and skips at best
# erratically the rest of the year. The labs it guards (leverage 271s +
# reliever 185s + hitter 47s + the starter lab, plus the three history
# exports) were re-derived on every monthly night, which is exactly what the
# gate existed to stop.
#
# WHY 45: it clears the longest month by 14 days, so the gate now reliably
# skips on the monthly cadence and expires roughly every OTHER run - the
# "monthly-plus horizon" the original comment says these conclusions actually
# move on. It does not weaken the escape hatch: EEPHUS_LABS=1 still forces
# every lab for a metric-research session, and a missing or malformed eval
# artifact still reads as stale and re-runs (fail-open, see _lab_should_skip).
# Cost of the change: a lab conclusion can now be up to 45 days old instead of
# up to 30 before it is re-derived.
LAB_EVAL_FRESH_DAYS = 45

# How many CollegeSavant teams the NCAA box-score pass renders per run (densest
# tracked teams first). Bounded because each team is a headless-Chrome render;
# raise once the first run is validated. 0 disables the pass.
COLLEGESAVANT_MAX_TEAMS = 40


def _vintage_years_by_key(timeseries) -> dict[str, int]:
    """F2 vintage-guard input for stats.bulk_resolve_ids: {player_key: last
    list year} for NON-ACTIVE identities (inactive busts + graduates). A
    dormant record re-resolved against the current PlayerIndex can bind a
    same-name kid whose first pro season postdates the record's entire list
    era (the luke_jackson class); the guard rejects those candidates.
    Actives are exempt: their lists are current, and the guard could misfire
    on a legitimately rehabbing recent signee."""
    out: dict[str, int] = {}
    for p in timeseries:
        if p.status == "active":
            continue
        yrs = [int(pt.snapshot_date[:4]) for pt in (p.points or [])
               if pt.snapshot_date and str(pt.snapshot_date)[:4].isdigit()]
        if yrs:
            out[p.player_key] = max(yrs)
    return out


def _is_career_fresh(fetched_at: str | None, max_age_days: int) -> bool:
    """True if a career_stats row is younger than max_age_days."""
    if not fetched_at:
        return False
    try:
        from datetime import datetime as _dt, timezone as _tz
        # storage writes via datetime('now') which produces 'YYYY-MM-DD HH:MM:SS'.
        ts = _dt.fromisoformat(fetched_at.replace(" ", "T"))
    except ValueError:
        return False
    # Naive UTC subtraction — both sides are naive UTC timestamps.
    return (_dt.now(_tz.utc).replace(tzinfo=None) - ts).days < max_age_days


def _artifact_fresh(path: Path, max_age_days: int) -> bool:
    """True if a JSON artifact's top-level `generated_at` is younger than
    max_age_days. The WS-R freshness/cadence gates (positional versatility +
    the 6b4 eval labs) key off the WHOLE-artifact stamp because those files
    carry no per-entry timestamps. FAIL-OPEN: any missing/unreadable/malformed
    artifact (or absent stamp) returns False (not fresh) so the caller RE-RUNS
    the step rather than trusting stale or corrupt output.

    EXPLICIT INVALIDATION beats age (added 2026-08-14). A top-level
    `invalidated_by` string forces a rebuild no matter how young the stamp is.

    WHY THIS EXISTS, measured rather than imagined. AGE IS THE WRONG QUESTION
    FOR AN ARTIFACT WHOSE INPUTS CAN BE RE-KEYED. The jesus_lopez identity
    repair landed 2026-08-12 and split a Boston DSL RHP (mlbam 838819) off a
    Texas catcher's key (805052). data/positions_played.json had been built
    2026-08-11, ONE DAY EARLIER, so at VERSA_FRESH_DAYS = 7 every subsequent
    run skipped step 3a-ii and the artifact kept serving the merge-window
    value: the catcher's key credited with `P {g:10, gs:9}`, which is the
    RHP's line. Verified against the authoritative per-player endpoint on
    2026-08-14: 805052 fields `C {g:97, gs:96}` and `DH {g:38, gs:36}` with
    ZERO pitching, and 838819 fields `P {g:11, gs:10}`.

    The cost was not cosmetic. test_identity_collisions::
    test_no_new_merged_identity_on_the_active_board reads that artifact, so a
    COMPLETED repair kept failing its own gate, and the baseline entry's leave
    condition ("still red after the next rebuild means the repair is
    INCOMPLETE") pointed at the wrong conclusion. Nothing was wrong with the
    repair; the gate was answering a question about age when the artifact had
    been invalidated by a re-keying.

    Backdating `generated_at` would have cleared it in one line and is
    forbidden: that field is provenance, and moving it to buy a rebuild is
    falsifying a measurement stamp. Hence a separate, self-documenting key."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(doc, dict):
        return False
    if doc.get("invalidated_by"):
        return False
    gen = doc.get("generated_at")
    return _is_career_fresh(gen, max_age_days) if gen else False


def _artifact_age_days(path: Path) -> int | None:
    """Whole days since a JSON artifact's top-level `generated_at`, or None if
    unreadable/absent. Companion to _artifact_fresh, used only for log copy."""
    try:
        gen = json.loads(Path(path).read_text(encoding="utf-8")).get("generated_at")
        from datetime import datetime as _dt, timezone as _tz
        ts = _dt.fromisoformat(str(gen).replace(" ", "T"))
        return (_dt.now(_tz.utc).replace(tzinfo=None) - ts).days
    except Exception:
        return None


def _maybe_prune_cache(log: logging.Logger) -> None:
    """OPT-IN, DEFAULT OFF: bound the refetchable `.cache/` at run start.

    `.cache/` was 55GB on 2026-08-04 (win_prob ~19G, statcast_metrics ~15G,
    zone_metrics ~5G) and only `game_feeds` had a pruner wired into the
    pipeline (`feed_cache.prune_old_feeds`, called just above this in main).
    The other caches DO have one - `tools/prune_cache.py`, which already
    covers all three by name, is age/target aware, protects a trailing window
    and excludes backups - it was simply never called from a run; the deploy
    shell invokes it only under disk pressure.

    This wires it in WITHOUT changing default behaviour: every knob is an env
    var that is unset by default, so an unconfigured run prunes nothing. The
    owner opts in per box:

      EEPHUS_PRUNE_CACHE_DAYS=400        age-prune the safe caches
      EEPHUS_PRUNE_VERSIONED_DAYS=30     sweep hash-keyed orphans only
      EEPHUS_PRUNE_TARGET_FREE_GB=25     pressure-prune oldest-first
      EEPHUS_PRUNE_MIN_KEEP_DAYS=120     floor for the pressure prune
      EEPHUS_PRUNE_DRY_RUN=1             report only, delete nothing

    Best-effort in the same spirit as the feed prune above: cache maintenance
    must never abort a pipeline run."""
    days = os.environ.get("EEPHUS_PRUNE_CACHE_DAYS")
    vdays = os.environ.get("EEPHUS_PRUNE_VERSIONED_DAYS")
    target = os.environ.get("EEPHUS_PRUNE_TARGET_FREE_GB")
    if not (days or vdays or target):
        return
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
        import prune_cache
        dry = os.environ.get("EEPHUS_PRUNE_DRY_RUN") == "1"
        if days:
            n, freed = prune_cache.prune_by_age(float(days), dry_run=dry)
            log.info("cache prune (age %sd)%s: %d files, %.2f GB",
                     days, " [dry-run]" if dry else "", n, freed / 1e9)
        if vdays:
            n, freed = prune_cache.prune_versioned_orphans(float(vdays), dry_run=dry)
            log.info("cache prune (versioned orphans %sd)%s: %d files, %.2f GB",
                     vdays, " [dry-run]" if dry else "", n, freed / 1e9)
        if target:
            keep = float(os.environ.get("EEPHUS_PRUNE_MIN_KEEP_DAYS") or 120)
            n, freed, reached = prune_cache.prune_to_target(
                float(target), min_keep_days=keep, dry_run=dry)
            log.info("cache prune (target %s GB free, keep %.0fd)%s: %d files, "
                     "%.2f GB, reached=%s", target, keep,
                     " [dry-run]" if dry else "", n, freed / 1e9, reached)
            if not reached:
                log.warning("cache prune could not reach %s GB free without "
                            "touching the protected recent window", target)
    except Exception as e:                                   # noqa: BLE001
        log.warning("cache prune skipped: %s", e)


def _lab_should_skip(artifact: Path, label: str, log: logging.Logger,
                     max_age_days: int = LAB_EVAL_FRESH_DAYS) -> bool:
    """WS-R eval-lab cadence gate. Return True (SKIP the lab) when EEPHUS_LABS
    is unset AND the lab's own eval artifact was regenerated within
    max_age_days; logs the artifact age either way. FAIL-OPEN: a missing or
    malformed artifact reads as NOT fresh (returns False -> caller RUNS the
    lab), so a corrupt file can never suppress a re-validation. Wrap the call
    inside the lab's existing try/except so this stays best-effort."""
    if os.environ.get("EEPHUS_LABS") == "1":
        log.info("%s: RUN eval lab (EEPHUS_LABS=1 forces the metric-research labs)", label)
        return False
    if _artifact_fresh(artifact, max_age_days):
        age = _artifact_age_days(artifact)
        log.info("%s: SKIP eval refresh - %s regenerated %s ago (< %dd cadence; "
                 "set EEPHUS_LABS=1 to force)", label, artifact.name,
                 f"{age}d" if age is not None else "recently", max_age_days)
        return True
    return False


def _iso_date_prefix(value: object) -> str | None:
    text = str(value or "").strip()
    if len(text) < 10:
        return None
    prefix = text[:10]
    if prefix[4:5] == "-" and prefix[7:8] == "-":
        try:
            date.fromisoformat(prefix)
            return prefix
        except ValueError:
            return None
    return None


def _statcast_log_date(split: dict) -> str | None:
    game = split.get("game") or {}
    return (
        _iso_date_prefix(split.get("date"))
        or _iso_date_prefix(game.get("officialDate"))
        or _iso_date_prefix((game.get("gameDate") if isinstance(game, dict) else None))
    )


def _latest_statcast_log_date(logs: list[dict] | None, level_hint: str | None = None) -> str | None:
    dates: list[str] = []
    for split in logs or []:
        level = split.get("_level") or level_hint
        if level not in DAILY_STATCAST_TRACKED_LEVELS:
            continue
        d = _statcast_log_date(split)
        if d:
            dates.append(d)
    return max(dates) if dates else None


def _latest_statcast_metric_game_date(metric: dict | None) -> str | None:
    dates: list[str] = []

    def add_rows(rows: object) -> None:
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            d = _iso_date_prefix(row.get("date"))
            if d:
                dates.append(d)

    def add_payload(payload: object) -> None:
        if not isinstance(payload, dict):
            return
        add_rows(((payload.get("pitch_movement") or {}).get("outings") or []))
        add_rows(((payload.get("pitch_plot") or {}).get("points") or []))
        add_rows(((payload.get("contact_quality") or {}).get("hit_locations") or []))
        add_rows(payload.get("standout_games") or [])
        add_rows(payload.get("recent_games") or [])

    add_payload(metric)
    if isinstance(metric, dict):
        for split in metric.get("level_splits") or []:
            add_payload(split)
    return max(dates) if dates else None


def _statcast_logs_newer_than_metric(
    logs: list[dict] | None,
    metric: dict | None,
    level_hint: str | None = None,
) -> bool:
    latest_log_date = _latest_statcast_log_date(logs, level_hint=level_hint)
    if not latest_log_date:
        return False
    latest_metric_date = _latest_statcast_metric_game_date(metric)
    return latest_metric_date is None or latest_log_date > latest_metric_date


def _career_rows_need_org_stint_backfill(rows: list[dict] | None) -> bool:
    """True for legacy career-cache rows that predate org/stint preservation.

    The old bulk path stored combined level rows with neither `org` nor
    `stints`. That loses cases like Cole Ragans 2023, where both MLB and AAA
    had TEX/KCR stints. A per-player yearByYear refresh repairs those rows by
    carrying single-stint orgs and multi-org `stints` payloads.
    """
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if row.get("org") is None and not row.get("stints"):
            return True
    return False


# A to AAA sports of the StatsAPI league census (milb_history's cache). Sport 15 is
# the pre-2021 short-season A, folded to A there and in stats._YBY_SPORT_LEVEL.
_CENSUS_SPORT_LEVEL = {11: "AAA", 12: "AA", 13: "A+", 14: "A", 15: "A"}
# Seasons back from the current one that the level-line check reads. A career table
# keeps 5 seasons, and a gap year or two (injury, a season abroad) still lands inside.
CENSUS_CHECK_SEASONS = 10


def _league_level_index(seasons, groups=("hitting", "pitching")) -> dict:
    """{(group, mlbam): {(season, level), ...}} for every A to AAA line with any
    playing time (PA for hitters, batters faced for pitchers) in the cached StatsAPI
    league census. Cache only: an absent file adds nothing, so a cold cache can
    never force a re-fetch, it can only miss one."""
    from milb_history import season_splits
    out: dict = {}
    for group in groups:
        exp_key = "pa" if group == "hitting" else "bf"
        for yr in seasons:
            for sport, level in _CENSUS_SPORT_LEVEL.items():
                try:
                    rows = season_splits(sport, int(yr), group, fetch=False)
                except Exception:                              # noqa: BLE001
                    continue
                for r in rows or []:
                    mid = r.get("mlbam")
                    try:
                        n = int(r.get(exp_key) or 0)
                    except (TypeError, ValueError):
                        n = 0
                    if not mid or n <= 0:
                        continue
                    out.setdefault((group, int(mid)), set()).add((int(yr), level))
    return out


def _career_missing_league_lines(rows: list[dict] | None, mlbam, is_pitcher: bool,
                                 index: dict) -> list[tuple[int, str]]:
    """(season, level) A to AAA lines the league census records for this player that
    his cached career table lacks, from the table's oldest kept season on.

    WHY (RPR10, 2026-10-02). The bulk season endpoint returns the qualified pool
    only, so a player qualified at one level comes back with that level alone, the
    bulk merge replaces his whole season with it, and the per-player yearByYear pass
    then skipped him as bulk-covered. When the season ended the one-level row froze:
    Aroon Escobar's 2025 read AA 22 AB with his 316 PA at A and 198 at A+ gone, Josh
    Kasevich's 2024 read AAA with no AA line (393 PA). An empty list means the table
    is complete or there is nothing to compare (no id, no cached rows)."""
    if not mlbam or not rows:
        return []
    have = {(int(r.get("season") or 0), r.get("level"))
            for r in rows if isinstance(r, dict)}
    seasons = [s for s, _lvl in have if s]
    if not seasons:
        return []
    floor = min(seasons)
    want = index.get(("pitching" if is_pitcher else "hitting", int(mlbam))) or set()
    return sorted(x for x in want if x[0] >= floor and x not in have)


def ingest_source_article_drops(out_dir: Path, log: logging.Logger) -> tuple[int, int]:
    """Ingest local source article text drops into snapshots + source_events."""
    try:
        from source_articles import parse_source_article_drops
        snapshots, events = parse_source_article_drops(out_dir)
        n_snap = insert_snapshots(snapshots) if snapshots else 0
        n_events = upsert_source_events(events) if events else 0
        if snapshots or events:
            log.info("source articles: ingested %d snapshots + %d events", n_snap, n_events)
        return n_snap, n_events
    except Exception:
        log.exception("source article ingest failed — continuing")
        return 0, 0


def _stage_fangraphs_articles(log) -> None:
    """Copy COMMITTED FG-article CSVs (tracked, reproducible) into the
    gitignored FG drop folder so the standard ingest re-applies them on every
    build. This is how scraped FanGraphs ARTICLE boards (e.g. the Marlins 2026
    Top 53) reach the deploy box: its prospects.db is persistent but FanGraphs
    is Cloudflare-blocked for re-scraping and data/fangraphs_imports/ is
    gitignored, so without a tracked source the article would never propagate.
    Idempotent — the snapshots UNIQUE(source,interval_label,player_key)
    constraint dedupes, and the tracked originals stay put (only the drop-folder
    copies move to processed/ after ingest)."""
    import shutil
    try:
        from fangraphs_csv import DROP_DIR
    except Exception:
        return
    art = Path(__file__).parent / "data" / "fangraphs_articles"
    if not art.is_dir():
        return
    DROP_DIR.mkdir(parents=True, exist_ok=True)
    staged = 0
    for csv in sorted(art.glob("*.csv")):
        try:
            shutil.copy2(csv, DROP_DIR / csv.name)
            staged += 1
        except Exception:
            log.exception("could not stage FG article CSV %s", csv.name)
    if staged:
        log.info("fangraphs_csv: staged %d committed article CSV(s) for ingest", staged)


def _write_dpw_series_step(log) -> None:
    """VAL_1 (owner decision FP2-1, 2026-09-25): write THE one $/WAR series
    (data/fa_dpw_series.json, fa_market.write_dpw_series) before anything in
    the rebuild prices a prospect or a veteran. Everything downstream reads its
    pricing.level_usd: the timeseries and eFV surplus through value_framework,
    proj_export's veteran seasons, the trade values, and fa_export later in the
    night (d10 / d10b). fa_export cannot be the writer: it runs after
    proj_export and reads mlb_projections, which would price the two a night
    apart. value_framework caches its config for the life of the process, so
    the caches are dropped after the write; a stale level in memory is the
    21:12 timeseries incident class. Best-effort: on failure the file on disk
    (the previous night's) still prices every surface at one level."""
    try:
        import fa_market as _fm
        import value_framework as _vf
        from fa_export import CLASS_YEAR as _FA_CLASS_YEAR
        _p = _fm.write_dpw_series(_FA_CLASS_YEAR)
        _vf._reset_caches()
        log.info("dpw series: class %s level $%s per WAR (winter %s carried at %s)",
                 _p.get("class_year"), _p.get("level_usd"), _p.get("anchor_winter"),
                 _p.get("carry_rate"))
    except Exception:
        log.exception("dpw series write failed - pricing on the file already on disk")


def rebuild_only(out_dir: Path = Path("data"), *,
                 stamp_summary: bool = True) -> None:
    """Fast export-only path: ingest any FG drops, rebuild the timeseries
    from the current DB state, write `data/timeseries.json`. No scraping,
    no MLB API calls. Use after a fangraphs_csv drop when you don't want
    to wait through the full monthly pipeline.

    stamp_summary=False suppresses the closing run-summary stamp for callers
    that stamp the same 74MB file themselves once their own run is finished
    (run_daily's d9). Their stamp is strictly newer, so writing here first is
    a second writer to a file a two-writer race truncated once. Standalone
    callers keep the default: export_timeseries_json writes a data_freshness
    block read mid-run, and the stamp is what moves it and the run block onto
    the finished run."""
    _utf8_console()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("rebuild_only")
    with _step("d9.dpw. DB init + the one $/WAR series", log):
        init_db()
        _write_dpw_series_step(log)
    with _step("d9.ingest. Source article drops + FanGraphs drop folder", log):
        ingest_source_article_drops(out_dir, log)

        # First: drain the FanGraphs drop folder so any waiting CSVs land
        # in the DB before we rebuild. (The FG ingest internally routes
        # <year>draft slugs to draft_csv, so dropping a draft CSV set works
        # without a separate call.)
        _stage_fangraphs_articles(log)   # committed FG-article boards -> drop folder
        try:
            from fangraphs_csv import ingest_drops as _fg_ingest_drops
            fg_inserted, fg_files = _fg_ingest_drops(called_from_run_monthly=True)
            if fg_files:
                log.info("fangraphs_csv: ingested %d snapshots from %d report-set(s)",
                         fg_inserted, fg_files)
        except Exception:
            log.exception("fangraphs_csv: drop-folder ingest failed - continuing")

    # Draft pipeline — promote any newly-drafted players + write the
    # draft_timeseries.json sidecar. Promotion is idempotent.
    with _step("d9.draft. Draft promotion + draft sidecar", log):
        try:
            from draft_promotion import promote_drafted_players, seed_signed_draftees
            from draft_export import export_draft_json
            promote_drafted_players()
            seed_signed_draftees()
            n_draft = export_draft_json(out_dir / "draft_timeseries.json")
            log.info("draft pipeline (rebuild): exported %d draft prospects", n_draft)
        except Exception:
            log.exception("draft pipeline crashed in rebuild_only - continuing")

    # Overseas pipeline — promote any newly-signed KBO/NPB players +
    # ingest any manual postings + write the overseas_timeseries.json
    # sidecar. Skips stats refresh on rebuild_only (that's a slow HTTP
    # path; only fires in the full main()).
    with _step("d9.overseas. Overseas promotion + overseas sidecar", log):
        try:
            from overseas_promotion import promote_signed_players, ingest_postings
            from overseas_export import export_overseas_json
            ingest_postings()
            promote_signed_players()
            n_ov = export_overseas_json(out_dir / "overseas_timeseries.json")
            log.info("overseas pipeline (rebuild): exported %d overseas prospects", n_ov)
        except Exception:
            log.exception("overseas pipeline crashed in rebuild_only - continuing")

    with _step("d9.build. Load snapshots + build the consensus timeseries", log):
        log.info("rebuild_only: loading snapshots + ancillary tables from DB")
        all_snaps = load_all_snapshots()
        timeseries = build_timeseries(all_snaps, normalize=ADOPT_NORMALIZED_CONSENSUS)
        log.info("rebuild_only: built timeseries for %d players", len(timeseries))

    # Preserve the existing rosters_by_org sidecar — it's built at
    # scrape time during the full pipeline, so a rebuild-only pass would
    # otherwise clobber it with `{}` and break every farm-detail page.
    # Same pass-through applies to roster_status (used by per-prospect
    # 40-man / options state on the detail page) so we don't lose those
    # signals on every fast rebuild.
    with _step("d9.inputs. Rosters, acquisitions, Spotrac IFA + contracts", log):
        existing_rosters: dict = {}
        rosters_path = out_dir / "rosters_by_org.json"
        if rosters_path.exists():
            try:
                with rosters_path.open(encoding="utf-8") as fp:
                    existing_rosters = json.load(fp)
            except Exception:
                log.exception("rebuild_only: could not load existing rosters_by_org.json - "
                              "falling back to empty (farm-detail pages will be blank)")
        else:
            log.warning("rebuild_only: no existing rosters_by_org.json - farm-detail "
                        "pages will be blank until a full `python run_monthly.py` runs")

        # IFA scrape feeds both ifa_spending_by_org (per-org cycle totals) and
        # ifa_bonus_by_key (per-player bonus merge). Spotrac HTML cache keeps
        # this offline on warm runs.
        acquisitions = load_acquisitions()
        ifa_bonus_by_key, ifa_spending_by_org = _load_spotrac_ifa(
            force=False, log=log, label="rebuild_only IFA",
        )
        _merge_ifa_bonuses_into_acquisitions(
            acquisitions, ifa_bonus_by_key, log, label="rebuild_only",
        )

        # Spotrac per-team contracts. Loaded offline from the per-team HTML
        # cache; manual overrides in data/contract_overrides.json layer on
        # top of this inside storage.py.
        contracts_by_key = _load_spotrac_contracts(
            force=False, log=log, label="rebuild_only contracts",
        )

    with _step("d9.export. Serialise the timeseries export", log):
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "timeseries.json"
        export_timeseries_json(
            timeseries, out_path,
            statlines=load_statlines(),
            pitch_arsenals=load_pitch_arsenals(),
            zone_metrics=load_zone_metrics(),
            statcast_metrics=load_statcast_metrics(),
            sabermetrics=load_sabermetrics(),
            trades_by_player=load_trades(),
            transactions_by_player=_derive_all_transactions(),
            career_stats=load_career_stats(),
            career_war=load_career_war(),
            acquisitions=acquisitions,
            il_status=load_il_status(),
            rosters_by_org=existing_rosters,
            level_changes=_derive_all_level_changes(),
            roster_status=load_roster_status(),
            ifa_spending_by_org=ifa_spending_by_org,
            contracts_by_key=contracts_by_key,
            # v30.7 - Rebuild-only was passing draft_pools={} (empty),
            # which made fin_draft_pool_efficiency return None for every
            # org → all 30 collapsed to a default 'C' grade. build_draft_pools
            # hits a 7-day on-disk cache for any year already scraped, so
            # the warm path is fast (no HTTP); cold years would scrape, but
            # the 2021-current run normally lives on disk. Failure here is
            # logged + swallowed to preserve the rebuild-doesn't-network
            # contract - fin_draft_pool_efficiency falls back to None
            # exactly as before.
            draft_pools=_load_draft_pools_for_rebuild(),
            player_ids={},
        )

    # eFV — our outcome-grounded grade. Regenerates the labeled training matrix +
    # the CURRENT active-board feature matrix from the just-written timeseries.json,
    # fits the model, scores both cohorts (live board gated on a pro track record),
    # and consolidates data/xfv.json (the site sidecar shown next to consensus FV).
    # The forward-chained backtest eval (registry artifact) is stable -> not re-run
    # here. Best-effort; a failure must not abort the run. Provisional grade.
    with _step("d9.efv. eFV regen (efv_export.regen_all)", log):
        try:
            from efv_export import regen_all as _regen_xfv
            _xfv = _regen_xfv(step=lambda _stage: _step(
                f"d9.efv.{_stage}. eFV regen stage ({_stage})", log))
            log.info("eFV (rebuild): %d players (%d live board) -> data/xfv.json",
                     _xfv["meta"]["n_players"], _xfv["meta"]["n_active"])
        except Exception:
            log.exception("eFV regen crashed in rebuild_only - continuing")

    # eFV REGEN TRIPWIRES (lane T, 2026-08-07). Records, per regen, the training
    # pool's MiLB coverage, the SERVED ridge weights, and how much of the live
    # board's explainer output changed, into data/xfv_regen_ledger.json.
    #
    # WHY IT SITS HERE. The 2026-08-04 regen took hitter coverage from 48.0 to
    # 59.2 percent and the refit moved the whole production weight block (level
    # premium down 32 percent, on-base down 36, age-for-level up 46). Nothing
    # gated it, because a refit is not a ship, and nothing connected the two, so
    # the owner found it by noticing a prospect had moved.
    # docs/ARIAS_ATTRIBUTION_2026-08-07.md is the session that cost.
    #
    # Immediately after regen_all on purpose: it reads the matrices and
    # data/xfv.json this step just wrote, in this process, before anything else
    # can touch them.
    #
    # REPORTS, NEVER GATES. It cannot fail the run: run() swallows its own
    # exceptions, and the try here is belt and braces. ok=False is filed ONLY
    # when the instrument could not observe at all, which is the one condition
    # worth a RED - a watch that has silently stopped watching is the exact
    # failure class it exists to catch. A tripwire FIRING leaves ok True and
    # rides log.warning plus the ledger: the measured base rate is about one
    # regen in three, and a RED at that rate is a RED nobody reads.
    with _step("d9.efv_tripwire. eFV regen tripwires", log):
        try:
            from tools.efv_regen_tripwire import run as _regen_tripwire
            _tw = _regen_tripwire(log)
            _record_ingest("efv_regen_tripwire", bool(_tw.get("observed")),
                           int(_tw.get("n_alerts") or 0),
                           _tw.get("message") or "", scope="", log=log)
        except Exception as e:                                # noqa: BLE001
            log.exception("eFV regen tripwire crashed in rebuild_only - continuing")
            _record_ingest("efv_regen_tripwire", False, 0, f"crashed: {e}", log=log)

    # BOARD RANK RE-BAKE (2026-09-05). export_timeseries_json above baked overall_rank /
    # org_rank off the eFV file ON DISK, which regen_all has just REPLACED, so until this
    # step the baked rank was one run stale against the grades the board displays and
    # sorts on. Measured 2026-09-05: Josue De Paula and Theo Gillen tied at 58.3 with
    # board_sort_key 9.617 vs 9.670; the homepage (baked rank) said #4 / #5 and the board
    # (fresh file) said #5 / #4. The re-bake re-applies THE ordering (storage.board_rank_key)
    # with only the two model terms refreshed, rewrites the payload atomically and updates
    # today's metric_snapshots rows when the monthly snapshot was already taken. It sits
    # directly after the regen and BEFORE every sidecar that reads overall_rank (ifa_export,
    # identity_audit, org_tendencies), which is why the eFV block moved up to here on the
    # same date. Reports through ingest health; never aborts the run.
    with _step("d9.rebake. Board rank re-bake on the fresh eFV file", log):
        try:
            from storage import rebake_board_ranks as _rebake_ranks
            _rb = _rebake_ranks(out_path, log=log)
            log.info("board ranks re-baked on the fresh eFV file: %d active rows, %d moved "
                     "(top 5: %s)", _rb.get("n_active") or 0, _rb.get("n_moved") or 0,
                     ", ".join(f"#{i} {pk}" for i, pk, _g in (_rb.get("top") or [])[:5]))
            _record_ingest("board_rank_rebake", bool(_rb.get("written")),
                           int(_rb.get("n_moved") or 0), _rb.get("message") or "",
                           scope="", log=log)
        except Exception as e:                                # noqa: BLE001
            log.exception("board rank re-bake crashed in rebuild_only - continuing")
            _record_ingest("board_rank_rebake", False, 0, f"crashed: {e}", log=log)

    # International Amateurs sidecar — IFA signing classes (2021–current)
    # from the cached Spotrac tracker, enriched against the freshly-written
    # timeseries.json. Best-effort; a failure here must not abort the run.
    with _step("d9.ifa. International amateurs sidecar", log):
        try:
            from ifa_export import export_ifa_json
            n_ifa = export_ifa_json(out_dir / "ifa_timeseries.json")
            log.info("ifa pipeline (rebuild): exported %d signings", n_ifa)
        except Exception:
            log.exception("ifa export crashed in rebuild_only - continuing")

    # Merged-identity report (the "Jesus Flores" class): two humans whose
    # names normalize to the same slug fused onto one player_key. Pure
    # detection over the just-written sidecars + a READ-ONLY read of
    # player_photos; it never writes to prospects.db and never re-keys
    # anything. Writes data/identity_collisions.json so the defect is
    # visible on every build instead of being found by a reader.
    # Best-effort; a failure must not abort the run.
    with _step("d9.identity. Merged-identity audit", log):
        try:
            from identity_audit import build as _build_identity_audit
            _ident = _build_identity_audit(path=out_dir / "identity_collisions.json")
            log.info("identity audit (rebuild): %d critical keys (%d active), "
                     "%d frankenstein records",
                     _ident["summary"]["critical_player_keys"],
                     _ident["summary"]["critical_active_player_keys"],
                     _ident["summary"]["frankenstein_records"])
        except Exception:
            log.exception("identity audit crashed in rebuild_only - continuing")

    # CollegeSavant -> Single-A translation. Re-fits the matched-pair factors
    # against the just-refreshed Single-A statlines and rebuilds the per-player
    # sidecar (CS player pages) + the PROSPX draft bridge. Reads CollegeSavant's
    # vendored TrackMan data + the DB; the factor bands tighten as more
    # college->Single-A pairs accrue. Best-effort; a failure must not abort.
    with _step("d9.college. CollegeSavant to Single-A translation", log):
        try:
            from college_translation import build as _build_college_translation
            _ct = _build_college_translation(out_dir=out_dir)
            log.info("CollegeSavant translation (rebuild): %d factor blocks, %d draft-bridge entries",
                     len(_ct.get("factors", {})), _ct.get("bridge_count", 0))
        except Exception:
            log.exception("CollegeSavant translation crashed in rebuild_only - continuing")

    # Organization Tendencies — pure aggregation over the DB + the
    # just-rebuilt sidecars (timeseries, ifa, debuts). Best-effort.
    with _step("d9.org_tendencies. Organization Tendencies", log):
        try:
            from org_tendencies import export as _export_ot
            _export_ot()
        except Exception:
            log.exception("org tendencies export crashed in rebuild_only - continuing")

    # MiLB -> first-MLB rate translation (K% / BB%; matched-pair, LOO-validated).
    # Needs the eFV matrices (built above) + debuts.json. Best-effort.
    with _step("d9.milb_translation. MiLB to first-MLB rate translation", log):
        try:
            import milb_translation
            _mt = milb_translation.build()
            log.info("MiLB->MLB rate translation: %d fits -> data/milb_translation.json",
                     len(_mt["fits"]))
        except Exception:
            log.exception("milb_translation crashed in rebuild_only - continuing")

    # Advancement Pace+ (W5, descriptive display ONLY - contract forbids any model
    # consumer) + defensive-home sidecar (W7). Both read caches/DB already refreshed
    # above and are compare-before-write. Best-effort.
    with _step("d9.pace_defhome. Advancement Pace+ and defensive home", log):
        try:
            import advancement_pace_export
            advancement_pace_export.run()
            log.info("advancement_pace_export: refreshed data/advancement_pace.json")
        except Exception:
            log.exception("advancement_pace_export crashed in rebuild_only - continuing")
        try:
            import def_home_export
            def_home_export.run()
            log.info("def_home_export: refreshed data/def_home.json")
        except Exception:
            log.exception("def_home_export crashed in rebuild_only - continuing")

    # eFV PROXY — faster-resolving leading indicator (pre-debut profile -> first-MLB Statcast
    # quality), forward-validated on recent debut cohorts. Separate artifact, NOT eFV; pulls
    # Savant expected-stats (cached). Best-effort; a Savant outage must not abort the run.
    with _step("d9.efv_proxy. eFV proxy leading indicator", log):
        try:
            import efv_proxy as _xfv_proxy
            _xp = _xfv_proxy.run()
            log.info("eFV proxy: hit r=%s / pit r=%s -> data/xfv_proxy_eval.json",
                     _xp["sides"].get("hit", {}).get("r"), _xp["sides"].get("pit", {}).get("r"))
        except Exception:
            log.exception("eFV proxy crashed in rebuild_only - continuing")

    # MLB Projections re-bake. THIS BLOCK IS ORDER-CRITICAL IN BOTH DIRECTIONS,
    # and it is here (not in the daily tail) because it sits between its two
    # neighbours, which both live inside rebuild_only:
    #
    #   AFTER  efv_export.regen_all (above): proj_export bakes each post-ETA
    #          prospect's eFV off data/xfv.json, so exporting before the regen
    #          publishes a /projections/ eFV the PROSPX board has already moved
    #          past (e.g. 63 vs 62 for the same prospect). This is the staleness
    #          the old daily step d9b was added to fix.
    #   BEFORE export_trade_values_json (below): bayes_trade_value's
    #          apply_platform_surplus re-points EVERY MLB board row onto the
    #          contract surplus it reads out of data/mlb_projections.json ON
    #          DISK. d9b used to run after d9, i.e. after the board had already
    #          been written, so the board was deterministically priced off the
    #          PREVIOUS cycle's projections, every single run. Measured on the
    #          2026-08-07 tree: 968 board rows carry surplus_source ==
    #          "projection" and 474 of them (49.0 percent) disagreed with the
    #          projections artifact by more than the 0.15M test tolerance, worst
    #          case 26.46M (kyle_harrison, 64.6 vs 91.06). The copy is verbatim,
    #          so an in-sync pair can differ by at most 0.05M of rounding.
    #
    # Placed ahead of the 66MB timeseries.json parse below on purpose: proj_export
    # holds its own timeseries copy, and running it after _ts_payload exists would
    # stack that peak on the trade-value peak on the ~6GB box.
    #
    # OOM: while it lived in the daily tail this ran with rebuild_only's frame
    # already popped, so it paid for its own timeseries copy and nothing else.
    # Inside the frame it would otherwise sit on top of the in-memory `timeseries`
    # this function built at the top. That dict is DEAD from here: its last read is
    # the export_timeseries_json call above, and everything downstream re-reads the
    # written file (_ts_payload below). Dropping it more than covers proj_export's
    # own copy. Mirrors the same del run_daily does before it calls us. all_snaps
    # stays: _post_export_summary at the tail still reads it.
    with _step("d9.proj. MLB projections re-bake (proj_export)", log):
        import gc as _gc
        del timeseries
        _gc.collect()

        # Best-effort in the same shape as every other step here: it reads cached
        # FA/contract inputs, and a cache miss must not abort the rebuild. If it does
        # fail, the trade board below prices off the LAST GOOD projections file, which
        # is exactly the (bad) behaviour this move replaces, not a new failure mode.
        try:
            from proj_export import export as _export_proj
            _n_proj = _export_proj()   # returns the payload size in bytes, not a row count
            log.info("mlb projections (rebuild): %dKB -> data/mlb_projections.json "
                     "(post eFV regen, pre trade-value export)", int(_n_proj) // 1024)
        except Exception:
            log.exception("proj_export crashed in rebuild_only - continuing")

    # The nightly standings read's health row (STANDINGS_9). proj_export above
    # made the season's one standings_now read through its current-season
    # attach; this files what that read returned and the cache file's age under
    # `statsapi_standings` (SCHEDULED_EXPORTS), so a stopped read prints
    # INGEST RED instead of Team Outlook, Futures and Franchise going quietly
    # null. Disk and memory only: it never fetches.
    with _step("d9-std. Nightly standings read health (statsapi_standings)", log):
        try:
            from proj_export import FIRST_SEASON as _proj_first_season
            _statsapi_standings_health(_proj_first_season - 1, log=log)
        except Exception as _e:                          # noqa: BLE001
            log.exception("statsapi_standings health check crashed - continuing")
            _record_ingest("statsapi_standings", False, 0,
                           f"health check crashed: {type(_e).__name__}: {_e}", log=log)

    # GRPO breakout scores — runs before trade values so scores can adjust FV priors.
    # Parse the 66MB timeseries.json ONCE; reused by the GRPO + trade-value blocks below
    # (was parsed 3x in immediate succession -- ~0.68s each).
    with _step("d9.grpo. GRPO breakout scores", log):
        try:
            _ts_payload = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _ts_payload = {}
        try:
            from grpo_prospect import export_grpo_scores
            # storage writes the graduate sidecar as debuts.json (renamed from
            # graduates.json); fall back like the grpo CLI so retrain never
            # silently trains on an empty set and freezes grpo_scores.json.
            _grads_path = next((p for p in (out_dir / "graduates.json",
                                            out_dir / "debuts.json") if p.exists()), None)
            _grads_for_grpo = json.loads(_grads_path.read_text(encoding="utf-8")) \
                if _grads_path else []
            _grpo_result    = export_grpo_scores(
                _ts_payload.get("players") or [], _grads_for_grpo,
                out_path=out_dir / "grpo_scores.json",
                model_path=out_dir / "grpo_model.pkl",
                level_norms=_ts_payload.get("level_norms"),
                retrain=True,
            )
            log.info("grpo: scored %d prospects", _grpo_result.get("scored", 0))
            # Free the first debuts.json parse (~60MB) before the trade-value block
            # below re-parses the SAME file - otherwise two full debuts copies (this
            # _grads_for_grpo + tv_players) coexist at the trade-value peak. Both
            # names are guaranteed defined here (the log line above reads
            # _grpo_result) and are unused past this point. The tv path re-reads
            # rather than reusing this list on purpose: the grpo fallback prefers
            # graduates.json first while the tv loop appends both sidecars, so the
            # two lists can differ - the del is the correct zero-risk fix.
            del _grads_for_grpo, _grpo_result
        except Exception:
            log.exception("grpo scoring failed in rebuild_only - continuing")

    # GRPO score archive (2026-08-19): grpo_scores.json is overwritten in place
    # by every retrain, so before this step no forward eval of the breakout
    # badge could ever be built. Append today's scores to grpo_score_history,
    # reading the JUST-WRITTEN artifact (never recomputing) so the archive
    # records exactly what the badge serves. INSERT OR IGNORE keyed on
    # (snapshot_date, player_key) makes a same-day re-run a no-op. Best-effort
    # like every neighbour in this block: an archive failure must not abort
    # the rebuild or the trade-value export below. Gate registration:
    # docs/grpo-2026-08-19/GRPO_FORWARD_GATE.md.
    with _step("d9.grpo_history. GRPO score archive", log):
        try:
            from grpo_prospect import snapshot_grpo_scores
            _n_grpo_hist = snapshot_grpo_scores(scores_path=out_dir / "grpo_scores.json")
            log.info("grpo_score_history: archived %d new rows", _n_grpo_hist)
        except Exception:
            log.exception("grpo_score_history snapshot failed in rebuild_only - continuing")

    # Bayesian trade values — runs after GRPO scores so priors are GRPO-informed.
    # Includes active prospects (timeseries.json), debuted players (debuts.json),
    # and full graduates (graduates.json) so the Trade Board is comprehensive.
    with _step("d9.trade_values. Bayesian trade values + slim sidecar", log):
        try:
            from bayes_trade_value import export_trade_values_json, _reset_cache
            _reset_cache()   # clear GRPO cache so new scores are loaded
            tv_players = list(_ts_payload.get("players") or [])   # reuse the single parse above
            lnorms     = _ts_payload.get("level_norms")
            # Sidecars are OPTIONAL but their absence must be VISIBLE. graduates.json
            # is read here, by efv_score and by grpo_prospect, and NOTHING IN THIS
            # REPO WRITES IT - a declared input that has silently never arrived,
            # because `if exists()` makes a missing file indistinguishable from an
            # empty one. Same failure shape as the FA parser that returned [] for a
            # day without anyone noticing (2026-07-31).
            for _sidecar in ("debuts.json", "graduates.json"):
                _sp = out_dir / _sidecar
                if _sp.exists():
                    _rows = json.loads(_sp.read_text(encoding="utf-8"))
                    tv_players += _rows
                    log.info("trade values: %s contributed %d rows", _sidecar, len(_rows))
                else:
                    log.warning("trade values: %s ABSENT - no producer exists in this "
                                "repo; the board is built without it", _sidecar)
            n_tv = export_trade_values_json(tv_players, out_dir / "trade_values.json",
                                            level_norms=lnorms)
            log.info("trade values (rebuild): exported %d players", n_tv)
            # The slim Transactions sidecar (owner answer M10-1): the same writer
            # tools/export_trade_values.py runs, from the file just written.
            try:
                from tools.export_trade_values import write_slim_sidecar
                write_slim_sidecar(out_dir / "trade_values.json")
            except Exception:
                log.exception("trade values slim sidecar failed in rebuild_only - continuing")
        except Exception:
            log.exception("trade value export crashed in rebuild_only - continuing")

    # Post-export sanity: surface what landed in the JSON so the user
    # doesn't have to grep the file.
    with _step("d9.summary. Post-export summary + run stamp", log):
        _post_export_summary(out_path, all_snaps, log)

        # Stamp run + data_freshness so a manual --rebuild-only produces the same
        # "as of" freshness block as daily/monthly runs (mirrors run_daily / main).
        # Skipped when the caller owns the stamp: run_daily reaches here at d9,
        # before its own finish_run, so this stamp would carry a run row that is
        # not finished yet and be superseded minutes later at the daily tail.
        if stamp_summary:
            _patch_export_run_summary(out_path, log)
        else:
            log.info("rebuild: run-summary stamp deferred to the caller")


# --------------------------------------------------------------------------- #
# secrets
# --------------------------------------------------------------------------- #
# Search order. /etc first because on the box that is the root-owned chmod-600
# file OUTSIDE the checkout (the deploy runs `git checkout -- .`, so a secrets
# file inside the repo would be destroyed nightly); the repo-local .env is the
# developer convenience and is gitignored.
_ENV_FILES = (Path("/etc/eephus.env"), Path(__file__).parent / ".env")
# Names we will report on. Values are NEVER logged.
_SECRET_KEYS = ("EEPHUS_ODDS_API_KEY", "EEPHUS_CARD_SCRAPE")


def _load_env_files(log=None) -> list[str]:
    """Load `KEY=value` / `export KEY=value` lines into os.environ. Returns the
    NAMES loaded (never values).

    WHY THE PIPELINE LOADS ITS OWN SECRETS (2026-08-05). Every key-gated step
    reads os.environ directly and nothing loaded the env file, so the key had to
    arrive from whatever shell happened to invoke the pipeline. It never did:
    deploy/nightly-build.sh had no reference to EEPHUS_ODDS_API_KEY and did not
    source /etc/eephus.env, so run_daily step 9e ("betting odds snapshot") had
    NEVER fired on the box - data/betting_status.json reported `configured: true`
    (the key exists in a file nothing reads) beside `n_snapshots_cached: 0`, and
    the API itself confirmed 0 of 500 credits ever used. The betting module was
    not waiting on a data feed; it was waiting on an environment.
    The shell wrapper now sources the file, but that only fixes ONE entry point.
    A direct `python run_monthly.py`, an `EEPHUS_FULL=1` one-off, or a cron line
    someone writes later all still start with an empty environment, and each
    would silently no-op exactly the same way. Loading here makes the pipeline
    correct however it is invoked, which is where the guarantee belongs.

    NEVER OVERRIDES an already-set variable: an explicit `export` in the calling
    shell, or a per-run override, must win over a file on disk."""
    loaded: list[str] = []
    for path in _ENV_FILES:
        try:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue                       # unreadable (perms) is not fatal
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):].lstrip()
            name, _, value = line.partition("=")
            name = name.strip()
            if not name or not name.isidentifier():
                continue
            value = value.strip().strip('"').strip("'")
            # setdefault semantics: the environment always outranks the file.
            if name not in os.environ:
                os.environ[name] = value
                loaded.append(name)
    if log:
        if loaded:
            # names only - a value in a log is a leaked secret, and these logs
            # are kept 30 days and read by whoever debugs the box.
            log(f"  secrets: loaded {len(loaded)} var(s) from disk: "
                f"{', '.join(sorted(set(loaded)))}")
        missing = [k for k in _SECRET_KEYS if not os.environ.get(k)]
        if missing:
            log(f"  secrets: NOT SET -> {', '.join(missing)}. The steps gated on "
                f"them will no-op (betting odds snapshot, card scrape).")
    return loaded


# ===========================================================================
# THE EARLY-UTC OPEN-ODDS CAPTURE (2026-09-06)
# ===========================================================================
# WHY IT NEEDS ITS OWN CRON. The open snapshot has always been captured by
# whichever step of the nightly happened to reach it, so the capture hour is
# whatever hour the nightly runs. MEASURED over the 22 cached snapshots
# (.cache/odds, 2026-08-06..2026-09-05, every one kind "open"):
#
#   * capture time of day ranges 01:33 to 23:19 UTC; 22 is even, so the median
#     straddles the two middle captures, 19:25 and 19:46;
#   * the earliest slate opening is 16:16 UTC. Rule: for each slate take its
#     first game's start, then take the smallest clock time over slates. Do NOT
#     take the smallest clock time over all 434 events, which is 00:05 UTC and
#     is a night game belonging to the PREVIOUS Eastern slate;
#   * 11 of 22 captures landed AFTER their own slate's first game had started;
#   * 49 of the 434 events in those captures (11.3 percent) were already in
#     progress at capture time, so they arrive priced in-game and the export's
#     in-game filter drops them;
#   * same-day priced games by capture hour: captures before 19:00 UTC average
#     13.0 games over 7 captures, 19:00-20:00 average 14.0 over 5, at or after
#     20:00 average 9.1 over 10.
#
# THE LOWER BOUND ON GAMES LOST, AND THE RULE THAT MAKES IT CHECKABLE. Assign
# every event to the Eastern calendar date of its own commence_time, which is
# the same key the wrapper's slate_date carries (verified: slate_date equals the
# Eastern date of captured_at on all 22). For slate S let UNIVERSE(S) be every
# event id any capture in the cache places on S, and HELD(S) be the event ids
# S's own capture carried whose Eastern date is S. LOST(S) = UNIVERSE(S) minus
# HELD(S). Re-derived 2026-09-06 over the 22 cached files:
#
#   08-08 priced 11 of 15 (lost 4)      08-19 priced 14 of 15 (lost 1)
#   08-13 priced  3 of  9 (lost 6)      08-20 priced  6 of  9 (lost 3)
#
# 14 games across 4 of the 22 captured slates, and the other 18 slates lose
# nothing. Every one of the 14 is proved by the PRIOR day's capture, and every
# one of the 14 had already started when its own slate's capture fired, so the
# loss is the late hour and nothing else. The true figure is larger, because on
# a day whose only capture is late there is no earlier capture to compare with.
# This bound is rule-dependent: attributing events to the UTC date of the
# capture instead of the Eastern date of the game splits slates across midnight
# and reports 53. That is why the rule is written out here rather than the
# number alone.
#
# So the vintage clock accrues at roughly two thirds to one half the rate the
# same credit spend could buy, and the deficit is invisible in the artifact
# because a game that was never priced leaves nothing behind.
#
# THE FIX IS THE HOUR, NOT MORE CREDITS. This entry point does the ONE paid
# open call and nothing else, so it can be crontabbed early in the UTC day,
# before the earliest observed first pitch of 16:16 UTC. Recommended:
#
#   10 13 * * *  cd <repo> && python run_monthly.py --odds-open
#
# 13:10 UTC is 09:10 ET, after the books have posted the day's openers and
# more than three hours before the earliest first pitch on record.
#
# CREDITS, the whole arithmetic. betting_ingest.credits_for() is 3 markets x 1
# region = 3 credits a call. One call a day is 3 x 31 = 93 in the longest
# month, against The Odds API free tier's 500. The provider's own meter, read
# off the newest cached wrapper (.cache/odds/2026-09-05-1718.json, credits
# block): used 9, remaining 491 for September. 93 + 9 = 102 of 500, and the
# separate props cap (props_credits_cap, 6) is charged against its own ledger.
# This step ADDS NO SPEND: it MOVES the existing daily call to a better hour,
# and step 9d-pre-odds is demoted to a guarded fallback that skips when this
# already captured today's slate.
#
# THE DUPLICATE GUARD IS AT THE CALL SITE, AND IT HAS TO BE. It would be
# convenient if betting_ingest refused a duplicate for free, and it does not:
# betting_ingest.run() calls fetch_snapshot() BEFORE write_snapshot(), so the
# 3 credits are spent on the provider's meter before the FileExistsError can
# fire, and that error only triggers on a collision of the exact
# YYYY-MM-DD-HHMM filename anyway, which means two calls a minute apart both
# succeed and both bill. Verified by reading betting_ingest.run and
# write_snapshot on 2026-09-06. So the refusal must happen here, before the
# call, exactly as step 9e already does it.
def _book_credits(job: str, cost: int, note: str, log) -> None:
    """Charge the shared tier ledger. Never raises.

    Called on BOTH paths, success and failure, because The Odds API bills on the
    request rather than the response: a call that reached the provider and then
    blew up has already cost its credits, and a ledger that only counts
    successes drifts below the truth in exactly the situation where an accurate
    count matters most.
    """
    try:
        import betting_credits as _bc
        _bc.record(job, cost, note=note)
    except Exception:                                     # noqa: BLE001
        if log is not None:
            log.warning("credit ledger: could not book %s credits for %s",
                        cost, job, exc_info=True)


def run_odds_open(*, log=None) -> dict:
    """Capture today's OPEN odds snapshot, once, early, and nothing else.

    Returns {ok, action, slate, reason} and never raises: this is a cron
    entry point, and a crash here must not become a retry loop that bills.
    `action` is one of "captured", "skipped_existing", "skipped_unarmed",
    "skipped_no_credits", "failed".

    THE SLATE, not the calendar day. The guard asks whether an open snapshot
    already exists for the US-Eastern slate date, computed at the same fixed
    EDT offset betting_ingest.slate_date_of stamps into the wrapper, so the
    question the guard asks and the label the ingest writes are the same
    question. Using the box's local date instead would ask a different one on
    any box not set to Eastern."""
    _utf8_console()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    log = log or logging.getLogger("run_odds_open")
    _load_env_files(log.info)

    now = datetime.now(timezone.utc)
    slate = (now - timedelta(hours=4)).strftime("%Y-%m-%d")
    out = {"ok": False, "action": "failed", "slate": slate, "reason": ""}

    with _step("odds-open. Early-UTC open odds capture", log):
        try:
            import betting_ingest
        except Exception as exc:                          # noqa: BLE001
            out["reason"] = f"betting_ingest import failed: {exc}"
            log.exception("odds-open: cannot import betting_ingest")
            return out

        if not betting_ingest.configured():
            out.update(ok=True, action="skipped_unarmed",
                       reason="EEPHUS_ODDS_API_KEY is not set; no call made")
            log.warning("odds-open: %s", out["reason"])
            return out

        # THE GUARD, before any billable call.
        try:
            existing = betting_ingest.latest_snapshot(kind="open", on_date=slate)
        except Exception:                                 # noqa: BLE001
            # An unreadable cache must not license a second paid pull.
            log.exception("odds-open: could not read the snapshot cache; "
                          "refusing to spend credits on an unknown state")
            out["reason"] = "snapshot cache unreadable; no call made"
            return out
        if existing:
            out.update(ok=True, action="skipped_existing",
                       reason=f"open snapshot for slate {slate} already cached "
                              f"({Path(str(existing.get('_path'))).name}); "
                              "no second 3-credit call")
            log.info("odds-open: %s", out["reason"])
            return out

        # THE TIER GUARD, after the duplicate guard and before the call. The
        # duplicate guard asks "have we already bought this slate"; this one
        # asks "can the month afford it at all", and four jobs now share one
        # 500-credit tier. It refuses BEFORE the request because
        # betting_ingest.run() fetches before it writes: after the call the
        # credits are gone whatever happens next.
        _cost = 3
        try:
            import betting_credits as _bc
            _cost = int(betting_ingest.credits_for())
            _okc, _whyc = _bc.check("open", _cost)
        except Exception:                                 # noqa: BLE001
            # A broken ledger must not stop a job that was running fine before
            # the ledger existed. Proceed, and say so.
            _okc, _whyc = True, "credit ledger unavailable; proceeding unguarded"
            log.warning("odds-open: credit ledger unusable", exc_info=True)
        if not _okc:
            out.update(ok=True, action="skipped_no_credits", reason=_whyc)
            log.warning("odds-open: %s", _whyc)
            return out
        log.info("odds-open: credits %s", _whyc)

        try:
            st = betting_ingest.run("open")
        except Exception as exc:                          # noqa: BLE001
            # SENT BUT FAILED still bills: the provider charges on the request.
            _book_credits("open", _cost, f"raised: {exc}", log)
            out["reason"] = f"ingest raised: {exc}"
            log.exception("odds-open: capture failed")
            return out
        _book_credits("open", _cost, str((st or {}).get("last_run"))[:80], log)

        last = str((st or {}).get("last_run") or "")
        ok = last.startswith("ok:")
        out.update(ok=ok, action="captured" if ok else "failed", reason=last)
        log.info("odds-open: %s", last or "no status")

        # Say the margin out loud. A capture that lands after first pitch is
        # the exact failure this step exists to end, and it is silent unless
        # somebody prints it.
        try:
            wrap = betting_ingest.latest_snapshot(kind="open", on_date=slate)
            stamps = []
            for ev in ((wrap or {}).get("events") or []):
                ct = (ev or {}).get("commence_time")
                if ct:
                    stamps.append(datetime.fromisoformat(
                        str(ct).replace("Z", "+00:00")))
            if stamps:
                lead = (min(stamps) - now).total_seconds() / 60.0
                started = sum(1 for s in stamps if s <= now)
                log.info("odds-open: %d event(s) on slate %s, first pitch in "
                         "%.0f min, %d already in progress at capture",
                         len(stamps), slate, lead, started)
                out["minutes_to_first_pitch"] = round(lead, 1)
                out["n_events"] = len(stamps)
                out["n_already_started"] = started
        except Exception:                                 # noqa: BLE001
            log.warning("odds-open: could not report the first-pitch margin")

    try:
        import job_heartbeat as _hb
        _hb.record("betting_odds_snapshot", ok=out["ok"],
                   result=f"{out['action']}: {out['reason']}"[:120])
    except Exception:                                     # noqa: BLE001
        pass
    return out


#: The date (ISO) the eWAR nightly last wrote the artifact in THIS process, so
#: the daily chained onto a monthly run does not price the live season twice.
_EWAR_NIGHTLY_DONE: str | None = None


def _ewar_nightly_step(log: logging.Logger, where: str) -> int:
    """Re-price the eWAR live season (tools/build_ewar.py --nightly) and log the
    freshness assertion. Owner decision D11 (2026-09-11): data/ewar.json
    rebuilds NIGHTLY, in WAR_BASIS_RUNBOOK step B's place: ahead of every WAR
    reader of the run. It is not the whole of step B. Only the live season is
    re-priced; every completed season is carried byte for byte, so nothing below
    step B in the runbook is invalidated.

    What moves nightly: the live season's blocks of the eWAR artifact and every
    served live-season eWAR that reads them through war_source. What does not:
    completed seasons, generated_at (the frozen series' build, the board
    fingerprint's label term), the eWAR eval, the career_war table (monthly
    3d), the outcome curve, the anchors, the draft slot curve and the
    war_rate_plus vintages.

    The FRESHNESS ASSERTION is war_source.ewar_cadence_status: the live season
    built today on that night's frames, stats and standings, and every frozen
    season still on its digest. It reports and records the `ewar_nightly`
    heartbeat; it never stops the run, because a stale numerator is a
    disclosure (ewar_vintage) and not an outage. Returns the step's rc (0, or 2
    when it refused or failed); SystemExit from an input loader is caught here
    as well as inside the step, so one bad data file cannot end the night."""
    global _EWAR_NIGHTLY_DONE
    rc, cad = 2, {}
    try:
        import war_source as _ws
        from tools import build_ewar as _build_ewar
        rc = _build_ewar.run_nightly(write=True)
        cad = _ws.ewar_cadence_status()
        if rc != 0 or not cad.get("ok"):
            log.error("%s: eWAR nightly rc=%s, freshness problems: %s",
                      where, rc, cad.get("problems"))
        else:
            log.info("%s: eWAR live season %s built %s; %d seasons frozen", where,
                     cad.get("live_season"), cad.get("live_built_at"),
                     len(cad.get("frozen_seasons") or []))
        if rc == 0:
            _EWAR_NIGHTLY_DONE = date.today().isoformat()
        result = "; ".join(cad.get("problems") or []) or "ok"
        if rc != 0:
            result = f"refused (rc {rc}); " + result
    except (Exception, SystemExit) as _e:                 # noqa: BLE001
        log.exception("%s: eWAR nightly failed - the boards serve the previous "
                      "build and say so (ewar_vintage) - continuing", where)
        result = f"{type(_e).__name__}: {_e}"
    try:
        import job_heartbeat as _hb
        _hb.record("ewar_nightly", ok=bool(rc == 0 and cad.get("ok")), result=result[:120])
    except Exception:                                     # noqa: BLE001
        pass
    return rc


def _rebake_mlb_player_detail(log, label: str) -> None:
    """Re-bake data/mlb_player_detail.json (the /projections/#player= cards and
    the Trade Machine evaluator) off the mlb_projections.json now on disk.

    The card copies the board's money and control keys verbatim, so every writer
    of the board has to be followed by this, or the card serves the previous
    vintage (M05-08, 2026-09-24: 143 surplus rows and one control window behind
    after a standalone --rebuild-only). Best-effort: a failed bake must not
    abort the caller."""
    try:
        from mlb_player_export import export as _export_mlbp
        _export_mlbp()
    except Exception:
        log.exception("%s: mlb player detail re-bake failed - continuing", label)


# --------------------------------------------------------------------------- #
# The Club Ledger and Franchise boards: one writer each, two callers
# --------------------------------------------------------------------------- #
# Owner answer LEDTRIM-1 = (c), 2026-10-01. A standalone --rebuild-only
# rewrote trade_values.json, mlb_projections.json and the timeseries farm
# roll-up (org_summary) but never the two boards that read them, so the
# ledger and franchise boards stayed one vintage behind their inputs until the
# next nightly (measured 2026-09-30 when they were finally rebuilt: farm rank
# moved on 5 clubs, Cost+ on 4, the financial letter on PIT and SFG, the
# franchise rank on 8). The nightly steps d10e and 6b7d and the rebuild tail
# below call the same two writers, so the paths cannot write them differently.

#: What the rebuild tail needs on disk before it rebuilds the ledger: the
#: timeseries (its org_summary is the farm roll-up the farm block copies), and
#: the trade board and the projections board rebuild_only has just written.
REBUILD_LEDGER_INPUTS = ("timeseries.json", "trade_values.json", "mlb_projections.json")
#: The franchise board's FIN section quotes the ledger board, so it needs that
#: file too, and it runs only when the ledger rebuilt in the same pass.
REBUILD_FRANCHISE_INPUTS = REBUILD_LEDGER_INPUTS + ("ledger_board.json",)
#: The directory both exporters read (ledger_export.DATA, franchise_export.DATA).
_EXPORTER_DATA_DIR = Path(__file__).resolve().parent / "data"


def _export_source_updates(log) -> bool:
    """Write data/source_updates.json (the body of nightly step d10g). True on
    a write. A failure leaves the previous file on disk and files a red under
    "source_updates_export" (SCHEDULED_EXPORTS)."""
    try:
        import source_updates_export as _su
        _sud = _su.build()
        _sun = _su.write(_sud)
        _n_rows = sum(len(s["lists"]) for u in _sud["updates"] for s in u["sets"])
        log.info("source updates: %d updates, %d list rows, %d bytes, through %s",
                 len(_sud["updates"]), _n_rows, _sun, _sud["through"])
        _record_ingest("source_updates_export", True, _n_rows,
                       f"{len(_sud['updates'])} updates through {_sud['through']}",
                       "prospects", log)
        return True
    except Exception as e:                # noqa: BLE001
        log.exception("source updates export failed - continuing")
        _record_ingest("source_updates_export", False, 0,
                       f"source updates export raised: {e}", "prospects", log)
        return False


def _export_ledger_board(log) -> bool:
    """Write the Club Ledger board, its thirty per-club row files and the
    Trade Machine CBT slice (the body of nightly step d10e). True on a write.
    A failure leaves the previous files on disk and files a red under
    "ledger_export" (SCHEDULED_EXPORTS)."""
    try:
        import ledger_export as _lg
        _lgd, _lgs = _lg.build_all()
        _lg.OUT.write_text(
            json.dumps(_lgd, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8")
        # D5 (2026-09-24): the thirty per-club row files beside the board,
        # tracked like data/mgmt_decisions; written from the bytes the
        # board indexed so shards.files matches disk.
        _lg.write_shards(_lgd, _lgs)
        # M27-4 (2026-09-25): the Trade Machine's CBT slice, read off
        # the board just written so the two never disagree.
        _lg.write_trade_cbt(_lgd)
        _lg_n = sum(int((d.get("contracts") or {}).get("n_priced") or 0)
                    for d in _lgd["clubs"].values())
        log.info("ledger: %d clubs, %d priced contract rows",
                 len(_lgd["clubs"]), _lg_n)
        _record_ingest("ledger_export", True, len(_lgd["clubs"]),
                       f"club ledger board, {_lg_n} priced rows", "mlb", log)
        return True
    except Exception as e:                # noqa: BLE001
        log.exception("ledger export failed - continuing")
        _record_ingest("ledger_export", False, 0, f"ledger export raised: {e}",
                       "mlb", log)
        return False


def _export_franchise_board(log) -> bool:
    """Write the Franchise board and its thirty club files (the body of
    nightly step 6b7d). True on a write. A refusal (fewer than 30 clubs on a graded branch, or a settled
    season's ODDS contradicting the final standings) or a raise leaves the
    previous file on disk and files a red under "franchise_export"."""
    try:
        import franchise_export as _fr
        _frd = _fr.build()
        # QCLP10 (2026-10-03): the board plus its thirty club files
        # (data/franchise_clubs/CODE.json), split by the exporter's own writer.
        _fr.write(_frd)
        _fr_top = min(_frd["clubs"], key=lambda d: d["index"]["rank"])
        log.info("franchise: %d clubs; #1 %s index %s",
                 len(_frd["clubs"]), _fr_top["code"], _fr_top["index"]["score"])
        _record_ingest("franchise_export", True, len(_frd["clubs"]),
                       "franchise board", "mlb", log)
        return True
    except Exception as e:                # noqa: BLE001
        # A refusal is a result, not a crash: the exporter declined to
        # publish and the committed board stands. Matched by name so a
        # failed import cannot leave the alias unbound in this clause.
        if type(e).__name__ == "FranchiseRefusal":
            log.warning("franchise board REFUSED: %s; the previous file stands", e)
            _record_ingest("franchise_export", False, 0,
                           f"franchise export refused: {e}", "mlb", log)
        else:
            log.exception("franchise export failed - continuing")
            _record_ingest("franchise_export", False, 0,
                           f"franchise export raised: {e}", "mlb", log)
        return False


def _export_awards_board(log) -> bool:
    """Write the Awards board payloads (the body of nightly step d10h and monthly
    step 6b7f): awards_export.export(), which reads the served boards, the .cache
    payloads and the war_daily stint frames (the one network read, the same frame
    the war board step reads) and REFUSES rather than publishes: a stale eWAR
    board, a stint frame served off its last-good parquet, a Top-25 row that
    breaks the league-share law, a projection provider mismatch, a thin standings
    cache, a frozen record whose hash the freeze log does not carry. While
    awards_core.AWARDS_LIVE is False every file lands under .cache/awards/preview/
    and nothing served moves. True on a write; a refusal or a raise leaves the
    previous files on disk and files a red under "awards_export", a row the
    watched tuple holds only once the flag is True."""
    try:
        import awards_export as _aw
        _res = _aw.export(log=log.info)
        _where = "served" if _aw.A.AWARDS_LIVE else "preview"
        if _res.get("ok"):
            log.info("awards (%s): %s", _where, _res.get("message"))
            _record_ingest("awards_export", True, int(_res.get("n_rows") or 0),
                           f"awards board ({_where})", "mlb", log)
            return True
        log.warning("awards board REFUSED: %s; the previous files stand", _res.get("reason"))
        _record_ingest("awards_export", False, 0,
                       f"awards export refused: {_res.get('reason')}", "mlb", log)
        return False
    except Exception as e:                # noqa: BLE001
        log.exception("awards export failed - continuing")
        _record_ingest("awards_export", False, 0,
                       f"awards export raised: {e}", "mlb", log)
        return False


def _rebuild_ledger_and_franchise(out_dir: Path, log) -> dict:
    """The rebuild-only tail: the ledger board, then the franchise board. Each
    is skipped with a logged reason when its inputs are not there, and the file
    on disk stands. Returns {"ledger": s, "franchise": s} where s is "written",
    "failed" or "skipped: <reason>"."""
    data_dir = _EXPORTER_DATA_DIR
    try:
        same_dir = Path(out_dir).resolve() == Path(data_dir).resolve()
    except OSError:
        same_dir = False
    if not same_dir:
        why = (f"this rebuild wrote to {out_dir}, but both exporters read {data_dir}, "
               "so the inputs this pass wrote are not the ones they would read")
        log.warning("rebuild_only: ledger board SKIPPED: %s; the board on disk stands", why)
        log.warning("rebuild_only: franchise board SKIPPED: %s; the board on disk stands", why)
        return {"ledger": f"skipped: {why}", "franchise": f"skipped: {why}"}

    res: dict = {}
    missing = [n for n in REBUILD_LEDGER_INPUTS if not (Path(data_dir) / n).is_file()]
    if missing:
        why = "input missing: " + ", ".join(missing)
        log.warning("rebuild_only: ledger board SKIPPED: %s; the board on disk stands", why)
        res["ledger"] = f"skipped: {why}"
    else:
        res["ledger"] = "written" if _export_ledger_board(log) else "failed"

    missing = [n for n in REBUILD_FRANCHISE_INPUTS if not (Path(data_dir) / n).is_file()]
    if missing:
        why = "input missing: " + ", ".join(missing)
    elif res["ledger"] != "written":
        why = ("the ledger board did not rebuild in this pass and the franchise FIN "
               "section quotes it")
    else:
        why = None
    if why:
        log.warning("rebuild_only: franchise board SKIPPED: %s; the board on disk stands", why)
        res["franchise"] = f"skipped: {why}"
    else:
        res["franchise"] = "written" if _export_franchise_board(log) else "failed"
    log.info("rebuild_only: ledger %s; franchise %s", res["ledger"], res["franchise"])
    return res


def rebuild_only_cli(out_dir: Path = Path("data")) -> None:
    """The standalone `--rebuild-only` entry point. rebuild_only() re-writes
    mlb_projections.json and trade_values.json but never the player cards (the
    nightly does that at d9b2), so a standalone pass re-bakes them here, after
    rebuild_only's frame (and its in-memory timeseries) is gone: the OOM note
    at the proj_export block is why this is not inside rebuild_only.

    Then the Club Ledger board and the Franchise board (owner answer LEDTRIM-1,
    2026-10-01), in the order their inputs require: after rebuild_only's
    trade-value export and the timeseries farm roll-up, the ledger first, the
    franchise board second (its FIN section quotes the ledger). They sit here,
    not inside rebuild_only, because the nightly calls rebuild_only at d9 and
    writes both boards later at d10e and 6b7d, after the FA re-export and the
    bracket simulator they also read. A standalone rebuild runs no site build:
    the caller's build_site comes after this returns.

    PERF_9 (2026-10-03): the pass writes its own step table,
    logs/pipeline_steps_rebuild.json, with the d9.* sub-steps rebuild_only
    records. Its own file, never the daily one: a standalone pass is not a
    nightly and must not overwrite the nightly's record."""
    _STEP_TIMES.clear()
    _t0 = time.monotonic()
    rebuild_only(out_dir=out_dir)
    log = logging.getLogger("rebuild_only")
    _rebake_mlb_player_detail(log, label="rebuild_only")
    _rebuild_ledger_and_franchise(out_dir, log)
    write_step_timings("rebuild-only", time.monotonic() - _t0, log=log,
                       path=STEP_TIMINGS_PATH.with_name("pipeline_steps_rebuild.json"))


def run_daily(out_dir: Path = Path("data"), workers: int | None = None,
              no_cache: bool = False, chained: bool = False) -> None:
    """DAILY fast-moving refresh — the time-sensitive subset of the pipeline.

    `chained=True` is set ONLY by main() when the monthly run tail-calls this
    (see the chain at the end of main()). In that mode two steps are skipped as
    pure duplication of monthly work that ran minutes earlier in THIS process:
    d5c (statlines: the monthly 3a career fetch + 3b derive just rebuilt every
    line) and d5d (incremental Statcast: the monthly 3d-ter full scrape just
    ran). Measured saving: 68s + 167s = ~235s off the chained-daily tail.
    A standalone `--daily` invocation always runs chained=False, so its
    behavior is byte-for-byte identical to before this change.

    Pulls and updates the data that moves between monthly grade releases, so
    the outcome-grounded eFV grade (re-scored at the end via rebuild_only)
    tracks it day to day. Every input eFV consumes is refreshed here:
      • daily Live board captures (TJStats / MLB Pipeline) -> consensus FV
      • current-season stat lines (d5c) -> the MiLB rate features eFV uses
        (k_rel / obp_rel / ops_rel / era_rel, derived from the statline)
      • incremental Statcast metrics (d5d) -> the Statcast tilt, for players
        with newly tracked games at Statcast levels
      • Injured-List stints (+ append-only il_history) -> the injury tilt
      • player transactions, roster status, debuts & graduations, trades

    It then rebuilds data/timeseries.json from the refreshed DB via the
    no-scrape `rebuild_only()` path, which re-runs the eFV pipeline
    (efv_export.regen_all) against the fresh consensus / stats / injuries, so a
    consensus move, a new stat line, or an IL change all flow into eFV the same
    night.

    The HEAVY, slow-HTTP work stays monthly in `main()`: full career-stat
    backfill, the full Statcast season scrape, the MLB-only sabermetrics
    endpoint (wRC+/xFIP, NOT an eFV input), scout-grade snapshots, Arkmetrics,
    farm grades, and the full ranking. run_daily and run_monthly run on
    different nights (deploy: `--daily` most nights, full on the 1st), so a row
    the daily incremental path writes is simply overwritten by the monthly full
    pass; never simultaneously. Every step is idempotent; a failure in one
    fetch logs and continues so a single flaky endpoint can't strand the run.
    """
    _utf8_console()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("run_daily")
    # BEFORE any step reads os.environ. Step 9e (odds snapshot) and the card
    # scrape are gated on keys this loads; see _load_env_files for why the
    # pipeline owns this rather than trusting the caller's shell.
    _load_env_files(log.info)
    import stats as stats_mod
    stats_mod.FORCE_REFETCH = no_cache

    init_db()
    run_id = start_run()
    log.info("started DAILY run %s", run_id)
    season = date.today().year
    _STEP_TIMES.clear()
    _run_start = time.monotonic()
    n_il = n_debuts = n_trades = 0

    try:
        # --- d00. Registered identity repairs (receipt-guarded) -----------
        # Owner answers B4ID-2 (b) and PVA-2 (2026-10-01): every repair in
        # identity_repairs.REPAIRS runs ONCE per database through
        # tools/repair_identity_split_2026_09_30.run_step, which skips the
        # repairs this DB already holds a receipt for
        # (.cache/identity_repairs/receipts.jsonl), takes one dated backup
        # before any write, refuses a row whose cached Pipeline pages are
        # missing (listed under `refused`, retried the next night) and never
        # raises. It runs before every exporter so the deploy box's first
        # nightly after the code sync repairs its own prospects.db; nobody runs
        # the script by hand on the box. Wired by the fWAR label epoch's step A
        # (EPOCH_RUN, 2026-10-03).
        with _step("d00. Registered identity repairs", log):
            _idr_rc = 2
            try:
                from tools import repair_identity_split_2026_09_30 as _idr
                _idr_summary = _idr.run_step()
                _idr_rc = int(_idr_summary.get("rc") or 0)
                log.info("identity repairs: receipted %d, pending %d, rc %s, backup %s, refused %s",
                         len(_idr_summary.get("receipted") or []),
                         len(_idr_summary.get("pending") or []), _idr_rc,
                         _idr_summary.get("backup"), _idr_summary.get("refused") or [])
                _idr_result = (("ok" if _idr_rc == 0 else "refused")
                               + f"; receipted {len(_idr_summary.get('receipted') or [])}")
            except Exception as _idr_e:                    # noqa: BLE001
                log.exception("identity repairs step crashed - continuing")
                _idr_result = f"{type(_idr_e).__name__}: {_idr_e}"
            try:
                import job_heartbeat as _idr_hb
                _idr_hb.record("identity_repairs", ok=(_idr_rc == 0), result=_idr_result[:120])
            except Exception:                              # noqa: BLE001
                pass

        # --- d0. TJStats Live board (daily point-in-time capture) ---------
        # TJStats updates continuously, so a daily Live pull gives finer Time
        # Machine resolution AND keeps TJStats's present-day consensus contribution
        # fresh between monthly runs. Live only (named historical snapshots are a
        # monthly concern). Date-stamped label -> a same-day re-run updates in
        # place; a new day creates a new point-in-time row. Never aborts the run.
        with _step("d0. TJStats Live capture", log):
            if chained:
                # WS-R: monthly 1c captured TJStats Live+history (and ran
                # export_movers) minutes ago in THIS process.
                log.info("daily: SKIP d0: monthly 1c just captured TJStats (chained)")
            else:
                try:
                    import tjstats
                    _tj = tjstats.run_tjstats_pipeline(live=True, history=False,
                                                       scope="daily-am")
                    if _tj.get("live"):
                        log.info("tjstats: daily Live %d players @ %s",
                                 _tj["live"]["n_players"], _tj["live"]["captured_at"])
                        tjstats.export_movers()   # wire sidecar + source events
                    elif _tj.get("health"):
                        log.error("tjstats: health check failed, skipped: %s", _tj["health"])
                    _record_ingest("tjstats", _tj.get("ok", False),
                                   _tj.get("n_rows", 0),
                                   "; ".join(_tj.get("health") or [])
                                   or (_tj.get("error") or ""),
                                   scope="daily-am", log=log)
                except Exception as e:            # noqa: BLE001
                    log.exception("tjstats daily capture crashed — continuing")
                    _record_ingest("tjstats", False, 0, f"crashed: {e}",
                                   scope="daily-am", log=log)

        # --- d0b. MLB Pipeline Live board (daily point-in-time capture) ---
        # Same rationale as d0: Pipeline re-ranks in-season (graduations,
        # FV moves), but the monthly scrape overwrites one fixed preseason
        # interval. The live capture writes a date-stamped interval behind
        # a parse-health gate (validate_pipeline_live_board) so an MLB.com
        # redesign can't zero or pollute ingestion. Never aborts the run.
        with _step("d0b. MLB Pipeline Live capture", log):
            try:
                from scrapers import run_mlb_pipeline_live
                _pl = run_mlb_pipeline_live()
                if _pl.get("live"):
                    log.info("mlb_pipeline: daily Live %d players @ %s",
                             _pl["live"]["n_players"], _pl["live"]["captured_at"])
                elif _pl.get("health"):
                    log.error("mlb_pipeline: health gate refused, skipped: %s",
                              _pl["health"])
                else:
                    log.error("mlb_pipeline: live capture failed: %s",
                              _pl.get("error"))
                _record_ingest("mlb_pipeline_live", bool(_pl.get("live")),
                               (_pl.get("live") or {}).get("n_players", 0),
                               "; ".join(_pl.get("health") or [])
                               or (_pl.get("error") or ""), log=log)
            except Exception as e:                # noqa: BLE001
                log.exception("mlb_pipeline daily capture crashed — continuing")
                _record_ingest("mlb_pipeline_live", False, 0, f"crashed: {e}", log=log)

        # --- d0b-i. Just Baseball rolling board (content-hash gated) ------
        # JB republishes ONE permalink. The old fixed-label ingest turned the
        # stored March board into a 126-row chimera with 26 duplicate ranks
        # (see scrapers.JB_INTERVALS). run_just_baseball_live date-stamps the
        # label and writes ONLY when the board's (key, rank, fv) fingerprint
        # actually changed, so the common case is a no-op and a genuine new
        # edition lands in its own point-in-time interval. Never aborts.
        with _step("d0b-i. Just Baseball rolling capture", log):
            if chained:
                # Monthly 1c-bis ran this minutes ago in THIS process. The
                # fingerprint gate would make a second call a no-op anyway,
                # but skip the fetch rather than knock on JB twice for nothing.
                log.info("daily: SKIP d0b-i: monthly 1c-bis just captured "
                         "Just Baseball (chained)")
            else:
                try:
                    from scrapers import run_just_baseball_live
                    _jb = run_just_baseball_live()
                    if _jb.get("live"):
                        log.info("just_baseball: NEW board %d players -> %r",
                                 _jb["live"]["n_players"], _jb["live"]["label"])
                    elif _jb.get("unchanged"):
                        log.info("just_baseball: board unchanged (%d players), "
                                 "no write", _jb["unchanged"]["n_players"])
                    elif _jb.get("health"):
                        log.error("just_baseball: health gate refused, skipped: %s",
                                  _jb["health"])
                    else:
                        log.error("just_baseball: capture failed: %s",
                                  _jb.get("error"))
                    # "unchanged" IS a healthy check - the source was reached
                    # and parsed. It stamps source_checks so a quiet board can
                    # never be confused with a dead scraper (the fa_signings
                    # lesson).
                    _ok = bool(_jb.get("live") or _jb.get("unchanged"))
                    _n = int((_jb.get("live") or _jb.get("unchanged")
                              or {}).get("n_players") or 0)
                    _record_ingest("just_baseball", _ok, _n,
                                   "; ".join(_jb.get("health") or [])
                                   or (_jb.get("error") or "")
                                   or ("unchanged" if _jb.get("unchanged") else ""),
                                   log=log)
                except Exception as e:            # noqa: BLE001
                    log.exception("just_baseball daily capture crashed - continuing")
                    _record_ingest("just_baseball", False, 0, f"crashed: {e}",
                                   log=log)

        # --- d0b-ii. MLB Pipeline per-team Top 30 boards (daily) ----------
        # Same staleness fix as d0b, one tier down: the monthly backfill
        # freezes each org's Top 30 at the {y}-01-22 preseason release, so
        # the ~800 prospects who sit in a team Top 30 but not the Live Top
        # 100 carry a January-vintage Pipeline grade all season. This capture
        # re-scrapes the 30 current /prospects/{year}/{slug} pages and
        # re-stamps the SAME per-team label with today's date (upsert bumps
        # snapshot_date in place) so consensus reads the current vintage. A
        # parse-health gate (>= 25 orgs, >= 20 players each) refuses a
        # degraded scrape. Never aborts the run.
        with _step("d0b-ii. MLB Pipeline per-team Top 30 capture", log):
            try:
                from scrapers import run_mlb_pipeline_org_live
                _po = run_mlb_pipeline_org_live()
                if _po.get("orgs"):
                    log.info("mlb_pipeline: daily org Top-30 %d players across "
                             "%d orgs @ %s",
                             _po["orgs"]["n_players"], _po["orgs"]["n_orgs"],
                             _po["orgs"]["snap_date"])
                elif _po.get("health"):
                    log.error("mlb_pipeline: org Top-30 health gate refused, "
                              "skipped: %s", _po["health"])
                else:
                    log.error("mlb_pipeline: org Top-30 capture failed: %s",
                              _po.get("error"))
                _record_ingest("mlb_pipeline_org", bool(_po.get("orgs")),
                               (_po.get("orgs") or {}).get("n_players", 0),
                               "; ".join(_po.get("health") or [])
                               or (_po.get("error") or ""), log=log)
            except Exception as e:                # noqa: BLE001
                log.exception("mlb_pipeline daily org capture crashed - continuing")
                _record_ingest("mlb_pipeline_org", False, 0, f"crashed: {e}", log=log)

        # --- 1. Player set from existing snapshots (no scrape). -----------
        # --- d0. MLBAM-anchored prospect discovery —————————————————————————
        # Pulls qualified current-season performers at each MiLB level from
        # the MLB Stats API and creates provisional player records for anyone
        # not yet in the DB.  This is the fix for missing prospects like
        # Franklin Primera: players with no scouting source coverage but who
        # have an MLBAM ID and are producing in affiliated ball enter the DB
        # here rather than waiting for a publication cycle.
        with _step("d0. MLBAM prospect discovery (unranked actives)", log):
            try:
                from mlbam_ingest import (ingest_unranked_active_prospects,
                                          refresh_performance_anchors)
                _mlbam_summary = ingest_unranked_active_prospects(season=season)
                _mlbam_total = sum(_mlbam_summary.values())
                if _mlbam_total:
                    log.info("mlbam_ingest: added %d new unranked prospects %s",
                             _mlbam_total, _mlbam_summary)
                # d0a. RE-DATE the anchors of players discovered on an EARLIER
                # run who still qualify this season. The discovery pass above
                # skips every already-known player, so before this step an
                # auto-tracked player's anchor date was written once and never
                # again: measured 2026-07-25, all 2,760 performance_ingest rows
                # sat at snapshot_date 2026-01-01 (min == max). That matters
                # because efv_dataset._stale_anchor_discount decays a model
                # anchor older than 18 months toward a -10 FV terminal at 30
                # months, so a permanently frozen stamp would have dragged the
                # whole cohort from FV 35 to FV 25 starting 2027-07 -- a
                # "dropped off the lists" event that never happened. Re-stamped
                # ONLY while the player still appears in the qualifying leaders,
                # and never for a player who has a real published anchor.
                _refresh = refresh_performance_anchors(season=season)
                log.info("mlbam_ingest: re-dated %d synthetic anchors %s",
                         _refresh.get("refreshed", 0), _refresh)
            except Exception:
                log.exception("mlbam_ingest: discovery step failed — continuing")

        with _step("d1. Build player set from DB", log):
            all_snaps = load_all_snapshots()
            timeseries = build_timeseries(all_snaps, normalize=ADOPT_NORMALIZED_CONSENSUS)
            log.info("daily: %d tracked players", len(timeseries))

        # --- 2. Resolve MLBAM IDs + PlayerIndex (disk-cached, fast). ------
        with _step("d2. Resolve IDs (warm PlayerIndex)", log):
            prospects = [(p.player_key, p.player_name, p.position) for p in timeseries]
            ids_by_key, _bds, player_index = bulk_resolve_ids(
                prospects, season=season, force_rebuild_index=no_cache,
                last_list_year_by_key=_vintage_years_by_key(timeseries),
            )

        # (d3 "Team affiliations" was cut 2026-07-14: its team_affil result
        # was never read - _derive_all_level_changes self-fetches per-year
        # affiliations when it actually derives moves.)

        # --- 4. Transactions (promotions/demotions + move timeline). ------
        with _step("d4. Player transactions", log):
            if chained:
                log.info("daily: SKIP d4: monthly path just refreshed transactions (chained)")
            else:
                try:
                    tx_tasks = [(p.player_key, ids_by_key.get(p.player_key))
                                for p in timeseries
                                if ids_by_key.get(p.player_key) is not None]
                    if tx_tasks:
                        max_w = (max(1, min(workers, len(tx_tasks))) if workers is not None
                                 else min(24, max(1, len(tx_tasks))))
                        new_tx = bulk_fetch_player_transactions(tx_tasks, max_workers=max_w)
                        if new_tx:
                            upsert_player_transactions(new_tx)
                        log.info("daily: refreshed transactions for %d players", len(new_tx))
                except Exception:
                    log.exception("daily: transactions refresh failed — continuing")

        # --- 5. IL status (+ append-only il_history timeline). ------------
        with _step("d5. IL status", log):
            if chained:
                log.info("daily: SKIP d5: monthly 2b.vii just refreshed IL status (chained)")
            else:
                try:
                    il_mids = {p.player_key: ids_by_key.get(p.player_key)
                               for p in timeseries
                               if ids_by_key.get(p.player_key) is not None
                               and p.status != "debuted"}
                    # Same concurrency as the d4 transactions fetch on the
                    # same endpoint (RU08); --workers / EEPHUS_MAX_WORKERS
                    # still caps it.
                    il_by_mid = bulk_fetch_il_status(il_mids.values(),
                                                     max_workers=workers or 24)
                    il_updates = {k: il_by_mid.get(m) for k, m in il_mids.items()}
                    upsert_il_status(il_updates)
                    n_il = sum(1 for v in il_updates.values() if v)
                    hist = record_il_observation(load_il_status())
                    log.info("daily: %d on IL (il_history +%d placed / %d activated)",
                             n_il, hist["placed"], hist["activated"])
                except Exception:
                    log.exception("daily: IL refresh failed — continuing")

        # --- 5c. Current-season stat lines (fast stats refresh) -----------
        # The board's current-season numbers used to wait for the monthly
        # run; the daily job now refreshes every ACTIVE prospect's
        # current-season stat line (24h HTTP TTL means each daily run pulls
        # fresh data; graduates stay frozen - their MiLB line is final).
        # Grades/tools/Arkmetrics still move ONLY monthly, so the graded
        # board's cadence stamp stays honest; this keeps OPS/ERA columns
        # and level pills no more than a day old.
        with _step("d5c. Current-season stat lines", log):
            if chained:
                # WS-R: chained after the monthly run, whose 3a career fetch +
                # 3b derive already rebuilt every current-season line minutes
                # ago in THIS process. This HTTP re-fetch (measured 68s) would
                # only re-derive data we just wrote. Standalone --daily still
                # runs it (chained=False).
                log.info("daily: SKIP d5c: monthly 3a/3b just rebuilt statlines (chained)")
            else:
                try:
                    from stats import fetch_statlines_for
                    from storage import upsert_statlines
                    active = [(p.player_key, p.player_name, _is_pitcher(p.position))
                              for p in timeseries
                              if p.status != "debuted"
                              and ids_by_key.get(p.player_key) is not None]
                    if active:
                        sl = fetch_statlines_for(active, season,
                                                 max_workers=workers or 24,
                                                 id_cache=ids_by_key)
                        n_sl = upsert_statlines(sl, season) if sl else 0
                        log.info("daily: refreshed %d current-season stat lines", n_sl)
                except Exception:
                    log.exception("daily: stat-line refresh failed — continuing")

        # --- 5d. Incremental Statcast-style metrics ----------------------
        # Game plots/tables need same-day starts, but re-running the full
        # Statcast season scrape in daily would be wasteful. We first fetch
        # cheap game logs with a short TTL, compare the newest tracked game
        # date against the newest date already embedded in the cached metric
        # payload, then rebuild full-season metrics only for players with
        # newer games. The rebuild replaces that player's row, preserving the
        # existing summary math without trying to merge partial pitch samples.
        # WS-R: when chained after the monthly run, the 3d-ter full Statcast
        # scrape just ran in THIS process; this incremental rebuild (measured
        # 167s) would only re-derive rows we already hold. Standalone --daily
        # (chained=False) still runs it for same-day starts between grades.
        if chained:
            log.info("daily: SKIP d5d: monthly 3d-ter Statcast scrape just ran (chained)")
        else:
            with _step("d5d. Incremental Statcast metrics", log):
                try:
                    from statcast_metrics import _game_logs, fetch_statcast_metrics_for_players

                    statlines = load_statlines()
                    statcast_metric_cache = load_statcast_metrics()
                    statcast_metric_meta = load_statcast_metrics_meta()
                    eligible = []
                    for p in timeseries:
                        mlbam = ids_by_key.get(p.player_key)
                        if mlbam is None:
                            continue
                        sl = statlines.get(p.player_key) or {}
                        level = sl.get("level")
                        if level is not None and level not in DAILY_STATCAST_TRACKED_LEVELS:
                            continue
                        if p.player_key not in statcast_metric_meta and level != "MLB":
                            continue
                        is_pitcher = bool(sl.get("is_pitcher")) or _is_pitcher(p.position)
                        eligible.append((p, mlbam, level, is_pitcher))

                    if not eligible:
                        log.info("daily: no Statcast-eligible players")
                    else:
                        max_w = max(1, min(workers or 16, len(eligible)))
                        log_ttl = 0 if no_cache else 1800
                        logs_by_key: dict[str, list[dict]] = {}

                        def _fetch_daily_statcast_logs(item):
                            p, mlbam, _level, is_pitcher = item
                            try:
                                return p.player_key, _game_logs(
                                    int(mlbam),
                                    season,
                                    is_pitcher=is_pitcher,
                                    ttl_seconds=log_ttl,
                                )
                            except Exception as e:
                                log.debug("daily: Statcast game logs failed for %s: %s",
                                          p.player_key, e)
                                return p.player_key, []

                        scan_start = time.monotonic()
                        scan_done = 0
                        log.info(
                            "daily: scanning Statcast game logs for %d players (%d workers)",
                            len(eligible),
                            max_w,
                        )
                        with concurrent.futures.ThreadPoolExecutor(max_workers=max_w) as ex:
                            for key, logs in ex.map(_fetch_daily_statcast_logs, eligible):
                                logs_by_key[key] = logs
                                scan_done += 1
                                if scan_done % 250 == 0 or scan_done == len(eligible):
                                    log.info(
                                        "daily: Statcast game-log scan %d/%d done (%.0fs)",
                                        scan_done,
                                        len(eligible),
                                        time.monotonic() - scan_start,
                                    )

                        refresh_players = []
                        refresh_logs: dict[str, list[dict]] = {}
                        for p, mlbam, level, is_pitcher in eligible:
                            logs = logs_by_key.get(p.player_key) or []
                            if not _statcast_logs_newer_than_metric(
                                logs,
                                statcast_metric_cache.get(p.player_key),
                                level_hint=level,
                            ):
                                continue
                            refresh_players.append((
                                p.player_key,
                                p.player_name,
                                mlbam,
                                level,
                                is_pitcher,
                            ))
                            refresh_logs[p.player_key] = logs

                        log.info(
                            "daily: Statcast scan found %d/%d players with newer tracked games",
                            len(refresh_players),
                            len(eligible),
                        )
                        if refresh_players:
                            new_statcast_metrics = fetch_statcast_metrics_for_players(
                                refresh_players,
                                season,
                                workers=max_w,
                                logs_by_key=refresh_logs,
                            )
                            n_sc = upsert_statcast_metrics(new_statcast_metrics, season) if new_statcast_metrics else 0
                            log.info("daily: refreshed %d Statcast metric rows", n_sc)
                except Exception:
                    log.exception("daily: incremental Statcast metrics failed — continuing")

        # --- d5e. Per-game box-line slice (leaderboard_gamelogs.json) -----
        # Powers the date-windowed PROSPX leaderboards ("last N days"). Wired
        # into nothing before WS-R, so the committed slice went stale. Rebuilt
        # in-process for the top ~200 prospects by overall rank, REUSING the
        # feed cache the d5d Statcast scan just primed moments earlier (same
        # statcast_metrics._game_logs feed) so most pulls are disk-cache hits.
        # Runs on chained monthly nights too (freshness matters then as well).
        # SOFT ~210s budget: on a cache-miss storm the remainder is skipped and
        # a partial slice is written (the frontend staleness notice covers gaps)
        # so this never balloons the nightly wall time. Best-effort; never aborts.
        with _step("d5e. Leaderboard game logs (leaderboard_gamelogs.json)", log):
            try:
                from tools.build_leaderboard_gamelogs import build as _build_gamelogs
                # ttl 0 forces fresh feeds when --no-cache; otherwise accept the
                # day-old cache d5d wrote seconds ago (86400s window).
                _gl = _build_gamelogs(
                    season=season,
                    limit=200,
                    workers=max(1, min(workers or 8, 12)),
                    ttl_seconds=0 if no_cache else 86400,
                    deadline_s=210.0,
                    log=log,
                )
                log.info("daily: gamelogs slice %d players / %d games (%.0fs%s)",
                         _gl.get("players", 0), _gl.get("games", 0),
                         _gl.get("elapsed_s", 0.0),
                         f", {_gl['skipped_deadline']} skipped by budget"
                         if _gl.get("skipped_deadline") else "")
            except Exception:
                log.exception("daily: leaderboard gamelogs build failed — continuing")

        # --- d5f. Measured MLB PA on the stored career rows. ---------------
        # Owner answer M7M8-2 (c), 2026-10-01: the migration step that writes
        # measured plate appearances onto stored MLB hitter rows from the cached
        # StatsAPI season lines (storage.backfill_career_pa_measured). Forward only
        # and idempotent; it runs on every night (a monthly night reaches it through
        # the chained daily) and ahead of d9, whose export ships the field to the
        # Debuted MLB chip floor. Reads no network and never moves fetched_at.
        with _step("d5f. Measured MLB PA backfill (career_stats)", log):
            try:
                from storage import backfill_career_pa_measured
                _pa = backfill_career_pa_measured()
                log.info("daily: measured MLB PA: %d of %d MLB hitter rows filled tonight, "
                         "%d already carried it, %d AB mismatch, %d no cached line, "
                         "%d no id, %d season not cached (%d players updated)",
                         _pa["filled"], _pa["mlb_hitter_rows"], _pa["already"],
                         _pa["ab_mismatch"], _pa["no_line"], _pa["no_id"],
                         _pa["no_cached_season"], _pa["players_updated"])
            except Exception:
                log.exception("daily: measured MLB PA backfill failed, continuing")

        # --- 6. Roster status (fresh tx + cached career stats). -----------
        with _step("d6. Roster status", log):
            if chained:
                log.info("daily: SKIP d6: monthly path just derived roster status (chained)")
            else:
                try:
                    career_cache = load_career_stats()
                    tx_cache = load_player_transactions()
                    roster_status_by_key: dict[str, dict] = {}
                    for p in timeseries:
                        tx_rows = tx_cache.get(p.player_key, [])
                        cs_rows = career_cache.get(p.player_key, [])
                        mid = ids_by_key.get(p.player_key)
                        api_debut = player_index.get_debut_date(mid) if mid else None
                        roster_status_by_key[p.player_key] = derive_roster_status(
                            tx_rows, cs_rows, api_debut_date=api_debut)
                    if roster_status_by_key:
                        upsert_roster_status(roster_status_by_key)
                    log.info("daily: roster_status for %d players", len(roster_status_by_key))
                except Exception:
                    log.exception("daily: roster_status derivation failed — continuing")

        # --- 7. Debut / graduation detection. -----------------------------
        with _step("d7. Auto-debut detection", log):
            try:
                active_for_debut = [
                    (p.player_key, p.player_name, _is_pitcher(p.position))
                    for p in timeseries if p.status != "debuted"
                ]
                debuts_found = detect_debuts_from_index(
                    load_career_stats(), active_for_debut,
                    player_index=player_index, id_cache=ids_by_key,
                    statlines=load_statlines() or None,
                )
                for pkey, debut_date in (debuts_found or {}).items():
                    auto_debut_player(pkey, debut_date=debut_date)
                n_debuts = len(debuts_found or {})
                if n_debuts:
                    log.info("daily: auto-debuted %d players", n_debuts)
                    all_snaps = load_all_snapshots()  # refresh statuses for trades
            except Exception:
                log.exception("daily: debut detection failed — continuing")

        # --- 8. Trade detection. ------------------------------------------
        with _step("d8. Trade detection", log):
            if chained:
                log.info("daily: SKIP d8: monthly step 4 just ran trade detection (chained)")
            else:
                try:
                    tracked = {p.player_key: (p.player_name, ids_by_key.get(p.player_key))
                               for p in timeseries}
                    new_trades = detect_trades(all_snaps, tracked_players=tracked,
                                               skip_api=False)
                    n_trades = insert_trades(new_trades)
                    log.info("daily: detected %d trades (%d new)", len(new_trades), n_trades)
                except Exception:
                    log.exception("daily: trade detection failed — continuing")

        # --- d8p. Postseason series cache. ---------------------------------
        # postseason.nightly fetches the live season's postseason series at
        # most once a day, never before its regular season ends, and never a
        # frozen (completed) season; completed seasons 2000 to 2025 ride the
        # tracked copy under data/_labs/postseason/. Network, guarded: a
        # failure writes nothing, so the frozen seasons and yesterday's live
        # file stand, and files a red under postseason_cache.
        with _step("d8p. Postseason series cache", log):
            try:
                import postseason as _postseason
                _psr = _postseason.nightly(log=log)
                _record_ingest("postseason_cache", True, _psr.get("n_series", 0),
                               _psr.get("message", ""), log=log)
            except Exception as e:                       # noqa: BLE001
                log.exception("daily: postseason series cache failed - continuing")
                _record_ingest("postseason_cache", False, 0,
                               f"postseason cache failed: {e}", log=log)

        # OOM: free the whole-universe caches BEFORE d9. all_snaps + timeseries
        # (built at d1) are the largest structures in the daily frame and are
        # dead from here on - last live read is d8 trade detection (non-chained)
        # or d7 (chained). d9 rebuild_only() INDEPENDENTLY reloads its own
        # all_snaps + timeseries, so without this drop two full snapshot-universe
        # copies coexist through the rebuild/export/site-build tail. Mirrors the
        # cleanup main() does at its tail before chaining the daily refresh. Both
        # locals are guaranteed defined (built unconditionally at d1).
        import gc as _gc
        del all_snaps, timeseries
        _gc.collect()

        # --- d8b. eWAR: re-price the live season ------------------------
        # WAR_BASIS_RUNBOOK step B's place: ahead of every WAR reader the rest
        # of the night runs (d9's projections export and its eFV regen, d9b2's
        # player cards, 9e-pre0's three boards, d10b's FA re-export all read
        # eWAR through war_source). _ewar_nightly_step says what moves and what
        # does not. On a chained monthly night step 3-pre already priced the
        # live season before the monthly's first WAR reader, on the same day's
        # inputs, so this skips.
        with _step("d8b. eWAR live-season rebuild (ewar.json)", log):
            if chained and _EWAR_NIGHTLY_DONE == date.today().isoformat():
                log.info("daily: SKIP d8b: monthly 3-pre priced the eWAR live season "
                         "today (chained)")
            else:
                _ewar_nightly_step(log, "daily")

        # --- 9. Rebuild the timeseries artifact from the refreshed DB. ---
        # stamp_summary=False: this run is not finished yet, and the tail
        # below stamps the same 74MB file once finish_run has closed the row.
        # Both stamps used to run, so every nightly re-parsed and rewrote the
        # artifact twice for one purpose. The crash path below carries the
        # fallback stamp that this one used to provide.
        with _step("d9. Rebuild timeseries (no scrape)", log):
            rebuild_only(out_dir, stamp_summary=False)

        # --- 9b: moved INSIDE d9 (rebuild_only) 2026-08-07. ---------------
        # The re-bake still exists and still runs on this chain, one frame down:
        # rebuild_only now exports mlb_projections.json between the eFV regen (which
        # writes the data/xfv.json grades proj_export bakes in) and the trade-value
        # export. It had to move because a step that runs AFTER d9 cannot feed d9,
        # and bayes_trade_value.apply_platform_surplus prices every MLB board row
        # off data/mlb_projections.json ON DISK, so running the re-bake out here
        # left trade_values.json built from the PREVIOUS cycle's projections on
        # every run (474 of 968 projection-sourced rows off by more than 0.15M,
        # worst case 26.46M). Not re-run here: proj_export is ~2 minutes and would
        # be pure duplication, and a second write of the same file is a second
        # writer to an artifact this repo has already lost once to a race.
        # Standalone `--rebuild-only` picks the re-bake up for free now, which it
        # never did while the step lived out here.
        log.info("d9b SKIP: proj_export now runs inside d9 rebuild_only "
                 "(post eFV regen, pre trade-value export)")

        # --- 9b2. Re-bake MLB player detail off the fresh projections. ----
        # mlb_player_detail.json (the /projections/#player= cards) used to
        # bake only in monthly 6b3, BEFORE the d9 eFV regen — so player cards
        # could serve a stale eFV vs the PROSPX board for up to a month (the
        # same staleness class d9b fixed for mlb_projections.json). Re-baking
        # in the daily tail keeps cards, board, and projections in lock-step
        # nightly, and makes the artifact fully daily-regenerated (so the
        # repo no longer tracks it). Best-effort in its own right: d9b is now
        # a log-only skip and no longer models anything, so the try/except
        # below is the only thing keeping a detail-bake failure from aborting
        # the daily tail.
        # --- d9b1. Current-season fielding innings (fielding_innings.json) ----
        # One request refreshes the live season's innings by position, so the card
        # bake below, the Defense board and Position Fit stop pairing current runs
        # with a July innings file. Rewrites only that season's key, atomically.
        with _step("d9a. Provisional grade retention + track (provisional_track_eval.json)", log):
            # PV-02. d9 just rewrote the served provisional grade, a gitignored
            # file, so it has no history unless it is kept here: a snapshot
            # under .cache/provisional_history/ (untracked) plus a small
            # tracked digest. Heartbeat `provisional_retention`.
            # PV-04. Then score the committed freezes against the first source
            # grades ingested so far (after d0 and, on a chained night, the
            # monthly ingest), append-only, interim rows marked "window open".
            # Heartbeat `provisional_track`. Neither half aborts the run.
            _provisional_nightly(log, "daily")

        with _step("d9b1. Refresh current-season fielding innings (fielding_innings.json)", log):
            try:
                from fielding_innings import refresh_current as _refresh_innings
                _refresh_innings(log=log.info)
            except Exception:
                log.exception("daily: fielding innings refresh failed - continuing")

        with _step("d9b2. Re-bake MLB player detail (mlb_player_detail.json)", log):
            _rebake_mlb_player_detail(log, label="daily")

        # --- 9c. Headshot resolution (data/photo_ctx.json). ---------------
        # Refresh the mlbstatic photo-context map on the DAILY path too, not just
        # the monthly build — otherwise mid-month additions (new draftees, fresh
        # call-ups) stay unresolved until the 1st and show a silhouette on deploy.
        # Incremental: TTL-skips already-resolved ids and only probes new or
        # still-missing players, so a steady-state night probes ~nothing. Runs
        # after the timeseries/debuts exports it reads and before d11 so build_site
        # and the GFX exporter (which read the map directly and don't self-heal)
        # see fresh coverage. Best-effort — a network hiccup must not fail the run
        # (the front-end onerror chain recovers any unresolved id regardless).
        with _step("d9c. Headshot resolution (photo_ctx.json)", log):
            try:
                from headshots import backfill as _backfill_headshots
                _hs = _backfill_headshots(data_dir=out_dir, workers=16, write_json=True)
                log.info("daily headshots: %.1f%% coverage (%d/%d) — %d probed, %d missing",
                         _hs["pct"], _hs["with_photo"], _hs["total"],
                         _hs.get("probed_this_run", 0), _hs["missing_count"])
            except Exception:
                log.exception("daily: headshot resolution failed — continuing")

        # --- d9d. PROSPX Leaderboards data file --------------------------
        # The lazy file the condensed Leaderboards table reads (PROSPX_1_LB_DATA):
        # StatsAPI season lines with their counting components per player, season
        # and level, plus one summed MiLB row per player-season, Season FIP and
        # K-BB%, per-season level norms and team games, and the current season's
        # Statcast, zone and model indexes. Runs after d9 because it reads the
        # board pool and level norms d9 just wrote. Past seasons come from the
        # .cache/prospx_lb/ files; only the current season refetches. Best-effort.
        with _step("d9d. PROSPX leaderboard data (prospx_leaderboard.json)", log):
            try:
                import prospx_leaderboard_export as _plb
                _plbs = _plb.export(out=out_dir / "prospx_leaderboard.json",
                                    data_dir=out_dir)
                log.info("daily: prospx leaderboard %d rows, %d players, %s bytes gz",
                         _plbs.get("rows", 0), _plbs.get("players", 0),
                         _plbs.get("gzip_bytes"))
            except Exception:
                log.exception("daily: prospx leaderboard export failed, continuing")

        # --- 9d. Fantasy daily refresh (schedule-only; cheap) -------------
        # Re-pull the probable-pitcher schedule and rebuild the schedule-driven
        # fantasy sections (Daily Streamers, Two-Start SP) off the monthly ROS
        # players. Skips build_corpus (kept on the monthly path for memory), so
        # the daily job stays light. No-op until the monthly build seeds
        # fantasy.json. Best-effort — never aborts.
        with _step("9d. Fantasy daily refresh (fantasy.json schedule)", log):
            try:
                from fantasy_export import refresh_live as _refresh_fantasy
                _refresh_fantasy(log=log.info)
            except Exception:
                log.exception("daily: fantasy refresh failed — continuing")

        # --- 9d-pre-odds. The odds snapshot, BEFORE the DFS slate ---------
        # THE DEFECT THIS CLOSES (found 2026-08-16): dfs.json was built at
        # 18:01:51Z and the day's only odds snapshot was captured at 18:09:02Z
        # by step 9e, eight minutes later, so dfs_export._vegas_index found
        # nothing on every slate this pipeline ever priced: vegas_games read 0
        # for the module's whole life while the betting page consumed the same
        # snapshot happily. The one paid pull now happens here, before 9d-bis
        # reads it. Step 9e keeps a GUARDED retry (it checks for tonight's
        # snapshot before pulling, because betting_ingest.run fetches BEFORE
        # its duplicate-path check and a second call would spend 3 more
        # credits), so a transient failure here still gets one more chance and
        # the nightly cost stays one 3-credit call.
        #
        # DEMOTED 2026-09-06 to a SAME-DAY FALLBACK. The primary capture now
        # runs on its own early-UTC cron (`--odds-open`, see run_odds_open),
        # because the nightly's hour is not early enough: 11 of the 22 cached
        # snapshots landed after their own slate's first pitch. This seam still
        # fires when that cron did not (never installed, box asleep, transient
        # failure), so a nightly on its own still produces a capture - just a
        # late one, which is what it always produced.
        #
        # THE GUARD IS THE SAME ONE STEP 9e USES, and it is not optional.
        # betting_ingest.run() fetches BEFORE write_snapshot can raise
        # FileExistsError, and that error only fires on an identical
        # YYYY-MM-DD-HHMM filename, so the ingest CANNOT refuse a same-day
        # duplicate without billing 3 credits first (verified by reading
        # betting_ingest.run and write_snapshot, 2026-09-06). The refusal has
        # to live here. Slate date, not box-local date, so the question matches
        # the label betting_ingest writes.
        with _step("9d-pre-odds. Betting odds snapshot (before the DFS slate)", log):
            try:
                import betting_ingest
                import job_heartbeat as _hb
                _slate = (datetime.now(timezone.utc)
                          - timedelta(hours=4)).strftime("%Y-%m-%d")
                if betting_ingest.latest_snapshot(kind="open", on_date=_slate):
                    log.info("betting odds: slate %s already captured (the "
                             "early --odds-open cron, or an earlier run); no "
                             "second 3-credit call", _slate)
                    _st = {"last_run": f"skipped: slate {_slate} already captured"}
                else:
                    # Same tier guard as the primary. This seam is a FALLBACK,
                    # so it books against the same "open" allocation: the two
                    # are one job that runs from two places, and giving the
                    # fallback its own budget would double the job's ceiling.
                    _c = int(betting_ingest.credits_for())
                    try:
                        import betting_credits as _bc
                        _okc, _whyc = _bc.check("open", _c)
                    except Exception:                     # noqa: BLE001
                        _okc, _whyc = True, "credit ledger unavailable"
                    if not _okc:
                        log.warning("betting odds: %s", _whyc)
                        _st = {"last_run": f"skipped: {_whyc}"}
                    else:
                        try:
                            _st = betting_ingest.run("open")
                        finally:
                            _book_credits("open", _c, "9d-pre-odds fallback", log)
                _hb.record("betting_odds_snapshot", ok=True,
                           result=str((_st or {}).get("last_run"))[:120])
            except Exception as _e:
                log.exception("daily: odds snapshot failed - 9e retries")
                try:
                    import job_heartbeat as _hb
                    _hb.record("betting_odds_snapshot", ok=False, result=str(_e)[:120])
                except Exception:
                    pass

        # --- 9d-park. The short-sample park block, before anything prices it -
        # data/fa_meta.json is tracked, so the checkout reverts it to the
        # committed copy, and DFS (9d-bis), the betting refit (9e-pre1), the
        # vintage snapshot (9e-pre) and the board (9e) all read its
        # park_factors_short_window block (betting_model.SERVE_ATH_PARK: the
        # Athletics at Sutter Health Park, the Rays' two-season Tropicana row)
        # hours before d10b rewrites fa_meta. This rewrites ONLY the two park
        # sibling blocks, off Savant pages fa_sources caches. Best-effort: a
        # failure keeps the committed block, which is what prices tonight.
        with _step("9d-park. Refresh the fa_meta park blocks (fa_meta.json)", log):
            try:
                import fa_export
                fa_export.refresh_park_siblings(log_fn=log.info)
            except Exception:
                log.exception("daily: fa_meta park block refresh failed; the committed "
                              "block prices tonight - continuing")

        # --- 9d-bis. DFS daily slate (dfs.json) ---------------------------
        # Prices today's slate off the probables 9d just refreshed. Reads the
        # fantasy corpus already on disk, so it adds no second corpus build.
        # Empty-slate days write an honest empty payload rather than nothing.
        # Best-effort — never aborts. Runbook: docs/diamond-fantasy.md.
        with _step("9d-bis. DFS daily slate (dfs.json)", log):
            try:
                import dfs_export
                dfs_export.refresh(log=log.info)
            except Exception:
                log.exception("daily: dfs slate export failed — continuing")

        # --- 9e-pre0. Refresh the boards the vintage is about to freeze ------
        # WITHOUT THIS THE CLOCK TICKS ON A STILL PICTURE. The three team
        # leaderboards were built only in main(), which the box runs monthly,
        # while the vintage snapshot below runs nightly. covers_through is
        # max(source as_of, write date), so it advances with the WRITE date
        # regardless of how old the features are: thirty nightly vintages would
        # carry thirty distinct dates and one identical feature set, and the
        # coverage report would call that archive perfectly healthy.
        #
        # That is a QUALITY failure, not a leakage one. A stale board knows less
        # than its stamp claims, never more, so nothing published off it is
        # dishonest. It is simply a month-old view of the league pretending to
        # be tonight's, on the one input the model weights most.
        #
        # Best effort per board: a leaderboard that fails to rebuild leaves
        # yesterday's file in place, and the snapshot below records the as_of it
        # actually found rather than the one it hoped for.
        # Imported by name rather than through __import__ so the audit-doc
        # generator and a human reader can both see which artifacts this step
        # writes. A dynamic import made DATA_SOURCES.md render its outputs as
        # "-", which is how a step goes missing from the pipeline map.
        # `chained` skips work main() just did in this same process. Without it
        # a full monthly night rebuilds all three boards twice, which measured
        # 92s of pure waste (6b4 53.6s + 6b4f 19.4s + 6b4g 19.2s), and the
        # bullpen walk is the one step that can balloon to minutes if the
        # win_prob cache was pruned by the disk preflight.
        with _step("9e-pre0. Refresh team leaderboards (bullpen_leaderboards.json, "
                   "starter_leaderboards.json, hitter_leaderboards.json)", log):
            if chained:
                # monthly 6b4/6b4f/6b4g built all three minutes ago in THIS
                # process. Measured cost of doing it twice: 92s (53.6 + 19.4 +
                # 19.2), and the bullpen walk is the step that balloons to
                # minutes when the disk preflight has pruned .cache/win_prob.
                log.info("daily: SKIP 9e-pre0: monthly 6b4/6b4f/6b4g just built "
                         "the three team leaderboards (chained)")
            else:
                for _name, _import in (
                        ("bullpen", lambda: __import__("bullpen_export").export),
                        ("starter", lambda: __import__("starter_export").export),
                        ("hitter", lambda: __import__("hitter_export").export)):
                    try:
                        log.info("daily leaderboards: %s scored %s",
                                 _name, _import()(log=log.info))
                    except Exception:
                        log.exception(
                            "daily: %s leaderboard refresh failed; tonight's "
                            "vintage will freeze the PREVIOUS %s file while "
                            "stamping today's date - continuing", _name, _name)

        # --- 9e-pre. Leaderboard vintage snapshot (the validation clock) ---
        # Writes .cache/leaderboard_vintages/<date>.json: the team inputs the
        # betting model consumes, stamped with the date they were true. A game
        # on date D is then priced on the newest snapshot whose knowledge
        # cutoff is strictly before D, which is the only thing that can make
        # betting_model.backtest() genuinely out of sample. Idempotent (first
        # write wins), offline, ~25KB a night, loud no-op when the leaderboards
        # are absent. Every night this does not run is a night the honest
        # backtest cannot buy back later. Additive; never aborts.
        # Runbook: docs/diamond-betting.md section 5.
        with _step("9e-pre. Leaderboard vintage snapshot (validation clock)", log):
            try:
                import job_heartbeat as _hb
                import leaderboard_vintages
                leaderboard_vintages.run(log_fn=log.info)
                _hb.record("leaderboard_vintage", ok=True)
            except Exception as _e:
                log.exception("daily: leaderboard vintage snapshot failed — continuing")
                try:
                    import job_heartbeat as _hb
                    _hb.record("leaderboard_vintage", ok=False, result=str(_e)[:120])
                except Exception:
                    pass

        # --- 9e-pre0b. Refresh the Defense board (display only) -------------
        # Placed AFTER the vintage snapshot on purpose: DEM+ feeds no model, and
        # work between the boards the clock freezes and the snapshot moves its timing.
        # Two cheap reads of caches 9e-pre0's hitter export just warmed.
        with _step("9e-pre0b. Refresh Defense Leaderboards (defense_leaderboards.json)", log):
            if chained:
                log.info("daily: SKIP 9e-pre0b: monthly 6b4i just built the defense board (chained)")
            else:
                try:
                    from defense_export import export as _export_defense_daily
                    log.info("daily leaderboards: defense scored %s",
                             _export_defense_daily(log=log.info))
                except Exception:
                    log.exception("daily: defense leaderboard refresh failed - continuing")

        # --- 9e-pre0c. Refresh the eWAR board (display only) ----------------
        # After the four boards above, which it reads for the `boards` field,
        # and after the vintage snapshot for the same reason 9e-pre0b is: this
        # board feeds no model, so it must not sit between the leaderboards the
        # validation clock freezes and the snapshot that freezes them. It pays
        # the same war_daily stint read 6b4j does (see there) every night it
        # runs, and refuses rather than publishing when a season feed is dead.
        with _step("9e-pre0c. Refresh eWAR Leaderboard (war_leaderboards.json)", log):
            if chained:
                log.info("daily: SKIP 9e-pre0c: monthly 6b4j just built the eWAR board (chained)")
            else:
                try:
                    from war_board_export import export as _export_war_board_daily
                    log.info("daily leaderboards: ewar board scored %s",
                             _export_war_board_daily(log=log.info))
                except Exception:
                    log.exception("daily: ewar leaderboard refresh failed - continuing")

        # --- 9e-pre0d. Live-season window panel (display only) ---------------
        # Owner answer M17-1 (2026-09-25, census M06-03): the multi-year
        # windows rebuild NIGHTLY, which reverses the old "lab cadence, not
        # nightly" note on monthly 6b4k. Only the live season's panel is
        # re-walked (about 75 s); completed seasons stay memoised under
        # .cache/mlbstats_windows/. Placed AFTER the 9e-pre vintage snapshot
        # like 9e-pre0b and 9e-pre0c (no model reads a window), and after
        # 9e-pre0c because the Overall window folds the per-season substrate
        # that step writes and the lab refuses a substrate on another eWAR build.
        # Then the four boards 9e-pre0 wrote are re-joined from the new l3 file
        # (answer M17-2), so the Current *_3yr column and the Last 3 view print
        # one number. A window built today on the served basis (a chained
        # monthly night whose 6b4k ran) is not rebuilt; a moved basis always
        # is (basis_moved). Additive; never aborts.
        with _step("9e-pre0d. Live-season window panel (mlbstats_window_*.json)", log):
            # Writes mlbstats_window_l3.json, mlbstats_window_l5.json and
            # mlbstats_windows.json, then re-joins the 3yr keys of
            # hitter_leaderboards.json, starter_leaderboards.json,
            # bullpen_leaderboards.json and defense_leaderboards.json.
            try:
                from tools import mlbstats_window_lab as _mwl
                _win_idx = _mwl.INDEX_PATH
                if _mwl.built_today(_win_idx) and not _mwl.basis_moved(_win_idx):
                    log.info("daily: SKIP 9e-pre0d window rebuild: the windows "
                             "were built today on the served eWAR basis")
                else:
                    log.info("daily windows: %d window(s) published",
                             _mwl.export(log=log.info))
                import bullpen_export as _be_win
                _be_win.restamp_window_3yr(log=log.info)
            except Exception:
                log.exception("daily: live-season window panel failed - the "
                              "previous windows and 3yr columns stand - continuing")

        # --- 9e-pre0e. In-Game Management nightly (owner answer 2026-09-25) --
        with _step("9e-pre0e. In-Game Management nightly (management_board.json)", log):
            # Census M10-05: the play corpus was rebuilt only by hand, so
            # /management/ sat on the last hand rebuild while the win_prob
            # cache grew nightly. mgmt_nightly.run rebuilds the OPEN season's
            # corpus tables when its win_prob files changed (completed seasons
            # stay frozen), then re-runs management.py, mgmt_bunt.py, the
            # decision ledger with its shard writer and mgmt_export, writing
            # management_running.json, management_bunt.json,
            # management_decisions.json, management_baseline.json, the
            # data/mgmt_decisions/ shards of the open season and
            # management_board.json. An unchanged corpus skips the chain and
            # the heartbeat says why. Placed AFTER 9e-pre0 (its bullpen walk
            # fills the win_prob cache) and after the 9e-pre vintage snapshot
            # (no model reads this), and BEFORE 9e and 6b7d, whose Dugout
            # blocks read the board written here. No priced cell reads it.
            # Offline; never aborts.
            try:
                import job_heartbeat as _hb
                import mgmt_nightly as _mgn
                _mn = _mgn.run(log_fn=log.info)
                _mn_why = f"{_mn['status']}: {_mn.get('why') or ''}"
                log.info("mgmt nightly: %s", _mn_why)
                _hb.record("mgmt_nightly", ok=True, result=_mn_why[:200])
                _record_ingest("mgmt_nightly", True,
                               int((_mn.get("corpus") or {}).get("games") or 0),
                               _mn_why[:200], "mlb", log)
            except Exception as _e:
                log.exception("daily: management nightly failed - the committed "
                              "management artifacts stand - continuing")
                try:
                    import job_heartbeat as _hb
                    _hb.record("mgmt_nightly", ok=False, result=str(_e)[:120])
                except Exception:
                    pass
                _record_ingest("mgmt_nightly", False, 0,
                               f"management nightly raised: {_e}"[:200], "mlb", log)

        # --- 9e-pre0f. Steal context: runner speed and catcher pop time -----
        with _step("9e-pre0f. Steal context (management_steal_context.json)", log):
            # W11 stage 1 (owner answer W-OQ3, 2026-10-01): the runner's sprint
            # speed percentile and the catcher's pop time beside every steal
            # row of the decision shards, CONTEXT ONLY (DV stays priced at a
            # league-average runner). Placed AFTER 9e-pre0e, whose shard writer
            # names the steal rows it joins. Refetches the open season's Savant
            # sprint speed leaderboard once a day and reads the throwing board
            # through savant_catcher's own one-day TTL; a failed fetch keeps
            # the cache, then the previous build's block. Never aborts.
            try:
                import job_heartbeat as _hb
                import mgmt_steal_context as _msc
                _sc = _msc.run(log_fn=log.info)
                _sc_why = f"{_sc['status']}: {_sc.get('why') or ''}"
                _hb.record("mgmt_steal_context", ok=True, result=_sc_why[:200])
                _record_ingest("mgmt_steal_context", _sc["status"] == "built",
                               int(_sc.get("attempts") or 0), _sc_why[:200], "mlb", log)
            except Exception as _e:
                log.exception("daily: steal context failed - the committed "
                              "management_steal_context.json stands - continuing")
                try:
                    import job_heartbeat as _hb
                    _hb.record("mgmt_steal_context", ok=False, result=str(_e)[:120])
                except Exception:
                    pass
                _record_ingest("mgmt_steal_context", False, 0,
                               f"steal context raised: {_e}"[:200], "mlb", log)

        # --- 9e-pre0g. MLB transaction events (dark until MLB_EVENTS_LIVE) ---
        # Wiring W01, part 1 (Q9_22a). Refreshes the league-wide StatsAPI
        # transaction cache (.cache/mlb_transactions/tx_YYYY_MM.json.gz) for the
        # previous and the current month (2 keyless calls a night; a missing
        # month, or one fetched while it was open, is refetched once inside a
        # 12-month look-back), then runs the mlb_events builder: one row per
        # (person, date, type code) from that cache, its IL placements and
        # activations, the arbitration salaries and the FA event ledger. While
        # mlb_events.MLB_EVENTS_LIVE is False it writes only under
        # .cache/mlb_events/preview/ and nothing under data/. Placed after
        # 9e-pre0e with the other display-only nightlies: no model and no priced
        # cell reads it. A failed refresh still builds from the cache on disk
        # and files ok=False. Additive; never aborts.
        with _step("9e-pre0g. MLB transaction events (mlb_events preview)", log):
            try:
                import job_heartbeat as _hb
                import mlb_events as _mev
                _me = _mev.nightly(log_fn=log.info)
                _hb.record("mlb_events", ok=bool(_me["ok"]), result=_me["message"][:200])
                _record_ingest("mlb_events", bool(_me["ok"]), int(_me["n_rows"]),
                               _me["message"][:200], "mlb", log)
            except Exception as _e:
                log.exception("daily: mlb events step failed - the previous "
                              "events files stand - continuing")
                try:
                    import job_heartbeat as _hb
                    _hb.record("mlb_events", ok=False, result=str(_e)[:120])
                except Exception:
                    pass
                _record_ingest("mlb_events", False, 0,
                               f"mlb events step raised: {_e}"[:200], "mlb", log)

        # --- 9e-pre-wx. Forecast weather capture (DARK; ARMED 2026-09-11) ---
        # docs/diamond-betting.md section 5h. Captures the pregame forecast for
        # today's remaining games and tomorrow's into .cache/weather_forecasts/
        # (one keyless Open-Meteo request, one immutable snapshot a night), then
        # runs the 5h-C Previous Runs backfill for completed 2026 regular-season
        # games not yet in the store (capped at 40 archive requests and 200 feed
        # fetches a night, stopping at the first failure). Nothing served reads
        # either. Runs before the export so the capture timestamp precedes the
        # night's prices. Additive; never aborts.
        with _step("9e-pre-wx. Forecast weather capture (dark, armed)", log):
            try:
                import betting_weather
                betting_weather.run(log_fn=log.info)
            except Exception:
                log.exception("daily: forecast weather capture failed - continuing")

        # --- 9e-pre1. Betting model refit, so the validation clock TICKS ---
        # THE DEFECT THIS CLOSES (2026-08-06). Every ingredient of the honest
        # backtest was already nightly: the vintage snapshot at 9e-pre, the
        # boards at 9e-pre0, and the games themselves. The one thing that reads
        # them was not. betting_model.build_context/backtest ran ONLY at step 6f
        # in main(), which the box runs on the 1st, so data/betting_model_eval.json
        # and its n_graded could not move for up to a month at a time. The page
        # would have shown a validation clock that was correct once a month and
        # frozen the rest of the time.
        #
        # This is the third instance of the same shape today: a job configured,
        # wired, and never actually reached on the path that runs.
        #
        # No network beyond the results top-up, and no cost when nothing is new:
        # the completed-games cache is extended by one StatsAPI call and the
        # refit is arithmetic over rows already on disk. Additive; never aborts.
        with _step("9e-pre1. Betting model refit (betting_model_eval.json)", log):
            try:
                import betting_model
                # Pin the CURRENT season explicitly. Both default to None, which
                # pools every season in the cache, and docs/diamond-betting.md
                # rules that sample out: a partial tail of one season plus an
                # early run of the next "should not" be accepted as one sample,
                # because the leaderboards reset between seasons. Passing the
                # season keeps the gate counting a single season's games.
                _season = str(date.today().year)
                betting_model.build_context(season=_season, log_fn=log.info)
                _bt = betting_model.backtest(season=_season, log_fn=log.info)
                _v = (_bt or {}).get("vintage") or {}
                # Say the number out loud every night. A clock nobody can read
                # is how this one sat at zero without anybody noticing.
                log.info("betting validation clock: %s of %s vintage-graded "
                         "games (%s vintages, status %s)",
                         _v.get("n_graded"), betting_model.VINTAGE_MIN_GRADED_GAMES,
                         _v.get("n_vintages"), _v.get("status"))
                import job_heartbeat as _hb
                _hb.record("betting_model_refit", ok=True,
                           result=f"n_graded={_v.get('n_graded')}")
            except Exception as _e:
                log.exception("daily: betting model refit failed - continuing")
                try:
                    import job_heartbeat as _hb
                    _hb.record("betting_model_refit", ok=False, result=str(_e)[:120])
                except Exception:
                    pass

        # --- 9e. Betting: odds snapshot + /betting/ payload ---------------
        # Prices the same slate against the team leaderboards. The odds pull is
        # ONE 3-credit call on The Odds API free tier and is a loud no-op when
        # EEPHUS_ODDS_API_KEY is unset (the page then says "odds feed not
        # configured" instead of rendering blank). Best-effort — never aborts.
        # Runbook: docs/diamond-betting.md.
        with _step("9e. Betting odds snapshot + payload (betting.json)", log):
            try:
                import betting_ingest
                import job_heartbeat as _hb
                from datetime import date as _date
                # THE ORIGINAL OFFENDER. This step existed, was reached, and had
                # never once produced a snapshot. `configured: true` in its own
                # status file said nothing about whether it FIRED.
                #
                # Since 2026-08-16 the paid pull lives at 9d-pre-odds so the DFS
                # slate can read it; this seam is the RETRY. The guard is at the
                # call site because betting_ingest.run fetches BEFORE its
                # duplicate-path check: calling it again tonight would spend 3
                # more credits to learn the snapshot already exists.
                if betting_ingest.latest_snapshot(kind="open",
                                                  on_date=_date.today().isoformat()):
                    log.info("betting odds: tonight's open snapshot exists, "
                             "no second pull")
                else:
                    _st = betting_ingest.run("open")
                    _hb.record("betting_odds_snapshot", ok=True,
                               result=str((_st or {}).get("last_run"))[:120])
            except Exception as _e:
                log.exception("daily: betting odds snapshot failed — continuing")
                try:
                    import job_heartbeat as _hb
                    _hb.record("betting_odds_snapshot", ok=False, result=str(_e)[:120])
                except Exception:
                    pass
            # THE BOARD EXPORT WAS THE ONE TAP IN THIS STEP WITH NO HEARTBEAT,
            # and its own handler could never fire: refresh_live catches
            # Exception itself and returns {} (deliberately, so it never raises
            # into the pipeline), so `except Exception` here is unreachable and
            # log.exception below it has never printed. A night on which the
            # board did not rebuild therefore reported fully green, and the two
            # ledgers underneath then recorded against a STALE board, which is
            # the empty-but-valid failure this codebase keeps getting bitten by.
            #
            # refresh_live's never-raise contract is left alone. What changes is
            # that its RETURN VALUE is now read: an empty payload is the failure
            # signal, it is stamped, and it is logged at error level.
            try:
                from betting_export import refresh_live as _refresh_betting
                _bp = _refresh_betting(log=log.info) or {}
                _bok = bool(_bp)
                import job_heartbeat as _hb
                _hb.record("betting_board_export", ok=_bok,
                           result=(f"{_bp.get('n_games')} game(s)" if _bok
                                   else "build returned nothing")[:120])
                if not _bok:
                    log.error("!!! BETTING RED: the board export produced no "
                              "payload, so data/betting.json is STALE and every "
                              "ledger below records against yesterday's board")
            except Exception as _e:
                log.exception("daily: betting export failed - continuing")
                try:
                    import job_heartbeat as _hb
                    _hb.record("betting_board_export", ok=False, result=str(_e)[:120])
                except Exception:
                    pass
            # --- props pull (armed only), then a re-export to price it -------
            # DOUBLE-ARMED on EEPHUS_ODDS_API_KEY + EEPHUS_PROPS_CREDITS, both
            # owner-set; inert otherwise and the payload names both variables.
            # Game selection is deterministic (betting_export.props_value_games,
            # doc section 7c), so the credit spend is reviewable from the board
            # alone. The second export exists because props pricing is a pure
            # read of cached snapshot bytes: pull first, then price. Wired
            # 2026-08-16; the hard monthly guard lives in betting_ingest and
            # refuses BEFORE any request that would breach the owner's cap.
            try:
                import betting_ingest as _bi
                if _bi.props_armed():
                    import json as _json
                    _pl = _json.loads(
                        (out_dir / "betting.json").read_text(encoding="utf-8"))
                    _games = __import__("betting_export").props_value_games(
                        _pl.get("team_bets") or [],
                        slots={"pick_of_the_day": _pl.get("pick_of_the_day")})
                    _eids = [g.get("odds_event_id") for g in _games
                             if g.get("odds_event_id")]
                    if _eids:
                        _pst = _bi.run("props", event_ids=_eids)
                        log.info("props pull: %s", (_pst or {}).get("last_run"))
                        from betting_export import refresh_live as _reprice
                        _reprice(log=log.info)
                else:
                    log.info("props pull: not armed "
                             "(EEPHUS_ODDS_API_KEY + EEPHUS_PROPS_CREDITS), skipped")
            except Exception:
                log.exception("daily: props pull failed - continuing")
            # --- close-capture health, off the cache that survives the night ---
            # NOT a heartbeat. data/job_heartbeat.json is git-tracked and
            # `git checkout -- .` reverts it before this pipeline runs, so a
            # heartbeat written by the 19:00 close job is gone before the 03:10
            # build could read it: the artifact would report the job as never
            # having run whether it ran or not. This reads .cache/odds/, which
            # is gitignored, survives the checkout, and is the same evidence CLV
            # grading uses. `diagnosis` names the REPAIR, not the symptom.
            try:
                import betting_export as _be
                _fh = _be.snapshot_health(days=14)
                _msg = ("!!! BETTING RED: " + _fh["diagnosis"]) if _fh["red"] else _fh["diagnosis"]
                _record_ingest("betting_close_capture", not _fh["red"],
                               _fh.get("n_slates_with_close", 0), _msg, log=log)
                if _fh["red"]:
                    log.error("!!! BETTING RED: %s", _fh["diagnosis"])
            except Exception as _e:
                _record_ingest("betting_close_capture", False, 0,
                               f"!!! BETTING RED: snapshot_health crashed: {_e}", log=log)
            # --- posted-lineup capture health, off the job's own store ----
            # READ, NEVER IMPORTED. The job is 5j phase 1 and must stay
            # unreachable from the pipeline, so this reads its directory and
            # nothing else. Three named failures, because "no capture today" is
            # ambiguous on its own: no slate file at all means the job has never
            # run on this box; a slate older than a day means it has stopped; a
            # slate that lists recent games with no capture beside it means it
            # is running and not capturing. An off day and the whole offseason
            # read as healthy, because the slate says there was nothing to post.
            try:
                import re as _re                    # run_monthly imports no re
                _lud = Path(__file__).resolve().parent / ".cache" / "lineup_captures"
                _cut = (date.today() - timedelta(days=3)).isoformat()
                _caps = [p for p in (sorted(_lud.iterdir()) if _lud.is_dir() else [])
                         if _re.match(r"^\d{4}-\d{2}-\d{2}-\d{4}\.json$", p.name)
                         and p.name[:10] >= _cut]
                _sl = _lud / "slate.json"
                _sldoc = json.loads(_sl.read_text(encoding="utf-8")) if _sl.exists() else None
                _slage = None
                if _sldoc:
                    _st = str(_sldoc.get("fetched_at") or "")[:10]
                    _slage = _st if _st else None
                _games = [g for g in ((_sldoc or {}).get("games") or [])
                          if str(g.get("official_date") or "") >= _cut]
                if not _sldoc:
                    _lumsg = ("!!! BETTING RED: tools/betting_lineup_job.py has never run "
                              "on this box (no .cache/lineup_captures/slate.json). The "
                              "*/15 TZ=UTC cron is not installed; run it with --selfcheck")
                elif _slage is None or _slage < (date.today() - timedelta(days=1)).isoformat():
                    _lumsg = (f"!!! BETTING RED: the posted-lineup job last ran {_slage}. "
                              f"The cron has stopped reaching it, and a lineup capture "
                              f"cannot be rebuilt after the fact")
                elif _games and not _caps:
                    _lumsg = (f"!!! BETTING RED: the posted-lineup job is running but has "
                              f"captured nothing in 3 days across {len(_games)} scheduled "
                              f"game(s); check its heartbeat and run log")
                else:
                    _lumsg = (f"{len(_caps)} posted-lineup capture file(s) in 3 days over "
                              f"{len(_games)} scheduled game(s)")
                _record_ingest("betting_lineup_capture",
                               not _lumsg.startswith("!!!"), len(_caps), _lumsg, log=log)
                if _lumsg.startswith("!!!"):
                    log.error("%s", _lumsg)
            except Exception as _e:
                _record_ingest("betting_lineup_capture", False, 0,
                               f"!!! BETTING RED: lineup-capture health crashed: {_e}",
                               log=log)
            # --- the nightly-gap sentinel, off the two per-date archives -----
            # Runs AFTER step 9e-pre (tonight's vintage) and the DFS export, so
            # a missing today means tonight's own capture failed. A night the
            # whole pipeline skips cannot report itself; this is the next
            # night's run noticing, which is the only place that can.
            #
            # THE ODDS LEG (2026-09-06) rides the same row. It is handed the
            # directory ONLY when a capture was possible at all: on a box with
            # no EEPHUS_ODDS_API_KEY the leg stays silent rather than reddening
            # every night over a call that could never have been made. Measured
            # before it existed: 9 slate days in a 31-day span held no open
            # capture and nothing in the pipeline said so.
            try:
                _odir = None
                try:
                    import betting_ingest as _bi_gap
                    if _bi_gap.configured():
                        _odir = Path(__file__).parent / ".cache" / "odds"
                except Exception:                        # noqa: BLE001
                    _odir = None
                _vg = _vintage_capture_gap(odds_dir=_odir)
                _record_ingest("vintage_capture_gap", _vg["ok"],
                               _vg.get("n_vintages_in_window", 0),
                               _vg["message"], log=log)
                if not _vg["ok"]:
                    log.error("%s", _vg["message"])
            except Exception as _e:
                _record_ingest("vintage_capture_gap", False, 0,
                               f"!!! VINTAGE GAP RED: sentinel crashed: {_e}",
                               log=log)
            # --- the two ledgers: settle yesterday, then log today -----------
            # This is the loop that breaks gate 3. sweep_min_edge needs 100+
            # settled bets carrying a taken price PER TAG, and nothing produced
            # them: publishing a pick needed min_edge, min_edge needed settled
            # picks. Paper bets at the real captured price close that circle
            # without the site claiming anything, and the calibration ledger
            # records every priced side with no floor at all so the probability
            # curve is measured somewhere other than where the model disagrees
            # with the market.
            #
            # SETTLE FIRST, then record. Settling reads the completed games that
            # step 9e-pre1 just refreshed, and recording reads the board the
            # export above just wrote, so this order uses both while current.
            #
            # BOTH LEDGERS SETTLE THROUGH betting_settle.run, on ONE read of the
            # schedule. That is not an optimisation: two reads a few seconds
            # apart can straddle a feed update and grade the same game two ways,
            # and two ledgers over the same slate may never disagree about
            # whether a side covered.
            try:
                import json as _json
                import betting_settle
                import betting_shadow
                from tools import betting_calibration
                # Move the paper ledger to .cache/betting/ before anything reads
                # it. It used to sit in data/ untracked AND unignored, one
                # `git add -A` away from the defect that destroyed the public
                # record, and outside the one directory the runbook says to back
                # up. Migrates whatever data/betting_shadow.json holds; a no-op
                # once the durable copy exists.
                _mig = betting_shadow.ensure_ledger()
                if _mig.get("created"):
                    log.info("shadow ledger: created the durable store at %s "
                             "(migrated %s row(s))", _mig.get("path"),
                             _mig.get("migrated"))
                _settled = betting_settle.run(log_fn=log.info)
                _st = _settled.get("shadow") or {}
                _cst = _settled.get("calibration") or {}
                _payload = _json.loads(
                    (out_dir / "betting.json").read_text(encoding="utf-8"))
                _meta = _payload.get("pick_meta") or {}
                # BOTH published slots are handed in, so each one is logged
                # even when it is not among the top rows by EV. The headline
                # slot selects on model probability inside a price band, which
                # by construction can sit below the EV ranking, and a published
                # pick with no ledger row is a claim with no evidence behind it.
                #
                # include_board_all=True IS THE VOLUME POLICY, DECIDED HERE
                # (2026-08-09) because betting_shadow keeps it off by default and
                # says the cost belongs at the call site. Gate 3 now sweeps PER
                # TAG and needs 100 settled rows in one tag, not 100 pooled: at
                # the measured 8.6 clearing sides a slate day the uncapped tag
                # reaches that in roughly 7 to 12 slate days, ev_rank at 3 a day
                # needs 34, and each single-pick slot needs about 100 - i.e. more
                # slate days than remain in this season. Without this flag the
                # per-tag gate is strictly harder to open than the pooled one it
                # replaced and the module would have gone backwards. It is also
                # the only tag whose ROI is a statement about the population the
                # published floor is actually applied to, because it is the only
                # one whose membership is not truncated by a cap.
                # `or` here once treated a MEASURED min_edge of 0.0 as absent
                # and silently substituted the provisional floor (PHASE3 finding,
                # fixed 2026-08-16). Only None means "not measured".
                _floor = _meta.get("min_edge")
                if _floor is None:
                    _floor = __import__("betting_export").PROVISIONAL_MIN_EDGE
                # EACH LEDGER GETS ITS OWN TRY (2026-08-16). These two calls sat
                # in one try with the settle above: a raise from the shadow
                # record skipped the calibration record entirely, and a slate's
                # ~44 calibration rows are unrecoverable the next day because
                # the board they price no longer exists. A failed leg is now a
                # RED on that leg, never a silent loss of its sibling.
                _rec, _rec_err = {}, None
                try:
                    _rec = betting_shadow.record_slate(
                        _payload,
                        min_edge=_floor,
                        gate_state={"provisional": _meta.get("provisional"),
                                    "basis": _meta.get("basis")},
                        slots={k: _payload.get(k) for k in
                               ("pick_of_the_day", "longshot_of_the_day")},
                        include_board_all=True,
                        log_fn=log.info)
                except Exception as _e:  # noqa: BLE001
                    _rec_err = _e
                    log.exception("daily: shadow record_slate failed - the "
                                  "calibration ledger still records")
                # NO FLOOR on this one, by design. A side the model rated 0.31
                # against a market fair 0.33 is worthless as a bet and exactly as
                # informative about calibration as the one it liked.
                _cal, _cal_err = {}, None
                try:
                    _cal = betting_calibration.record_slate(_payload, log_fn=log.info)
                except Exception as _e:  # noqa: BLE001
                    _cal_err = _e
                    log.exception("daily: calibration record_slate failed - "
                                  "the shadow ledger already recorded")
                _sum = betting_shadow.summary()
                _ready = _sum.get("sweep_readiness") or {}
                # PER TAG, never pooled. docs/diamond-betting.md section 7a: a
                # pooled ROI measures a mixture nobody bet, and a pooled COUNT
                # in the log reads as one clock when there are four.
                _per_tag = {t: b.get("n") for t, b in _ready.items()}
                log.info("shadow ledger: +%s logged (%s, %s), %s settled; "
                         "per-tag toward the sweep (need %s): %s",
                         _rec.get("written"), _rec.get("reason"),
                         _rec.get("by_slot") or {}, _st.get("settled"),
                         _sum.get("min_bets_for_sweep"), _per_tag)
                log.info("calibration ledger: +%s priced side(s), %s settled",
                         _cal.get("written"), _cst.get("settled"))
                # THE DATED READ, committed beside the ledger. The ledger file
                # itself is a bare JSON array with nowhere to put a date, and a
                # write stamp on it would answer the wrong question anyway: a
                # slate where nothing cleared the floor rewrites nothing, so the
                # file's mtime and the newest row's age come apart on exactly
                # the nights that matter. This renders the per-market readiness
                # with its own generated_at AND the newest row's timestamp, so a
                # reader can tell a fresh render of a stale ledger from a fresh
                # ledger. It is a report; it never raises.
                try:
                    _art = betting_shadow.write_readiness_artifact()
                    log.info("shadow readiness: rendered %s cells, newest row %s",
                             sum(len(v) for v in
                                 (_art.get("sweep_readiness_by_market_tag") or {}).values()),
                             _art.get("newest_row_at"))
                except Exception:                                 # noqa: BLE001
                    log.warning("daily: shadow readiness artifact not rendered; "
                                "the ledger is unaffected", exc_info=True)
                _store = _sum.get("storage") or {}
                if not _store.get("durable"):
                    log.error("!!! BETTING RED: the paper ledger is not on the "
                              "durable path: %s", _store.get("why"))
                # THE MISSING HEARTBEAT. Every other tap in this step stamps one
                # and this one never did, so the single loop that can open gate 3
                # was the only betting job with no record that it ran. A shadow
                # ledger that silently stops logging looks exactly like a slate
                # on which nothing cleared the floor.
                # READ THE REASON. betting_settle catches per-ledger and
                # returns {'settled': 0, 'reason': 'failed: ...'}, so stamping
                # ok=True unconditionally made a settlement CRASH indistinguishable
                # from a night with nothing to settle. Both are "0 settled" and
                # only one of them is fine.
                def _settle_ok(res):
                    return not str((res or {}).get("reason", "")).startswith("failed")
                import job_heartbeat as _hb
                _hb.record("betting_shadow_ledger",
                           ok=_settle_ok(_st) and _rec_err is None,
                           result=(f"+{_rec.get('written')} logged, "
                                   f"{_st.get('settled')} settled, per-tag "
                                   f"{_per_tag} of "
                                   f"{_sum.get('min_bets_for_sweep')}"
                                   f"{'' if _settle_ok(_st) else ' | ' + str(_st.get('reason'))}"
                                   f"{'' if _rec_err is None else ' | record: ' + str(_rec_err)}")[:120])
                _hb.record("betting_calibration_ledger",
                           ok=_settle_ok(_cst) and _cal_err is None,
                           result=(f"+{_cal.get('written')} priced side(s), "
                                   f"{_cst.get('settled')} settled"
                                   f"{'' if _settle_ok(_cst) else ' | ' + str(_cst.get('reason'))}"
                                   f"{'' if _cal_err is None else ' | record: ' + str(_cal_err)}")[:120])
                for _lbl, _res in (("shadow", _st), ("calibration", _cst)):
                    if not _settle_ok(_res):
                        log.error("!!! BETTING RED: the %s ledger did not settle: %s",
                                  _lbl, _res.get("reason"))
                for _lbl, _err in (("shadow", _rec_err), ("calibration", _cal_err)):
                    if _err is not None:
                        log.error("!!! BETTING RED: the %s ledger did not record "
                                  "tonight's slate: %s", _lbl, _err)
            except Exception as _e:
                log.exception("daily: betting ledgers failed - continuing")
                try:
                    import job_heartbeat as _hb
                    _hb.record("betting_shadow_ledger", ok=False, result=str(_e)[:120])
                    _hb.record("betting_calibration_ledger", ok=False,
                               result=str(_e)[:120])
                except Exception:
                    pass
            # --- the learning series (data/betting_learning.json) ------------
            # LAST IN THE STEP, and the order is the whole point: it reads the
            # eval 9e-pre1 refit, the board the export wrote, and both ledgers
            # after tonight's rows landed in them. Run any earlier and the
            # published series would be a day behind the numbers beside it.
            #
            # data_catalog advertises this file at cadence "daily" and nothing
            # wrote it - the copy in the tree was produced BY HAND, so on
            # production the row would have advertised a URL that 404s forever.
            # Additive; never aborts.
            try:
                import betting_learning
                import job_heartbeat as _hb
                _lrn = betting_learning.run(log_fn=log.info)
                _lat = (_lrn.get("latest") or {})
                _vc = ((_lat.get("clocks") or {}).get("vintage_sample") or {})
                _hb.record("betting_learning", ok=True,
                           result=(f"vintage {_vc.get('have')}/{_vc.get('need')}, "
                                   f"{_lrn.get('n_history')} history row(s), "
                                   f"min_edge={(_lat.get('gates') or {}).get('min_edge')}"
                                   )[:120])
            except Exception as _e:
                log.exception("daily: betting learning series failed - continuing")
                try:
                    import job_heartbeat as _hb
                    _hb.record("betting_learning", ok=False, result=str(_e)[:120])
                except Exception:
                    pass

        # --- 9g. eFV scoreboard refresh (xfv_scoreboard_eval.json) --------
        # The /diamond/ receipts read this artifact and NOTHING regenerated it:
        # tools/efv_scoreboard.py was wired into no pipeline step, so the sales
        # page quoted a 9-day-old scoreboard while every artifact beside it
        # rebuilt nightly (found 2026-08-16). Subprocess because the tool
        # os.chdir()s at import, which must not move this process. Idempotent
        # (compare-before-write) and cheap while source_backtest.json is under
        # SB_MAX_AGE_DAYS old: measured 0.7s on 2026-08-16. Best-effort.
        with _step("9g. eFV scoreboard refresh (xfv_scoreboard_eval.json)", log):
            try:
                import subprocess as _sp
                import sys as _sys
                import job_heartbeat as _hb
                # --no-progress: the ledger update below owns the "nightly"
                # row, so the tool's by-hand "efv_change" hook stays out of it.
                _r = _sp.run([_sys.executable, "tools/efv_scoreboard.py", "--no-progress"],
                             capture_output=True, text=True, timeout=1800,
                             cwd=str(Path(__file__).resolve().parent))
                _ok = _r.returncode == 0
                _hb.record("efv_scoreboard", ok=_ok,
                           result=(_r.stdout or _r.stderr or "").strip().splitlines()[-1][:120]
                           if (_r.stdout or _r.stderr) else f"rc={_r.returncode}")
                if not _ok:
                    log.error("daily: efv_scoreboard exited %s: %s",
                              _r.returncode, (_r.stderr or "")[-400:])
            except Exception as _e:
                log.exception("daily: efv_scoreboard refresh failed - continuing")
                try:
                    import job_heartbeat as _hb
                    _hb.record("efv_scoreboard", ok=False, result=str(_e)[:120])
                except Exception:
                    pass
            # EFV3_D3: the eFV scoreboard matrix (efv_matrix_eval.json,
            # tools/efv_matrix.py), FRAME x CELL x COMPARATOR x STATISTIC on
            # the served backtest the refresh above reused or reran. It runs
            # AFTER the scoreboard and BEFORE the ledger update below, which
            # copies its summary counts into the headline and DS-16 rows.
            # Subprocess so a failure inside the scoring cannot take the daily
            # job down; own heartbeat key; never fatal. Idempotent
            # (compare-before-write): a night with no change rewrites nothing
            # and the ledger then appends nothing. Measured 337 s at B 2000
            # on 2026-10-03; the timeout leaves room for a slow box.
            try:
                import subprocess as _sp
                import sys as _sys
                import job_heartbeat as _hb
                _r = _sp.run([_sys.executable, "tools/efv_matrix.py", "--quiet"],
                             capture_output=True, text=True, timeout=3600,
                             cwd=str(Path(__file__).resolve().parent))
                _ok = _r.returncode == 0
                _hb.record("efv_matrix", ok=_ok,
                           result=(_r.stdout or _r.stderr or "").strip().splitlines()[-1][:120]
                           if (_r.stdout or _r.stderr) else f"rc={_r.returncode}")
                if not _ok:
                    log.error("daily: efv_matrix exited %s: %s",
                              _r.returncode, (_r.stderr or "")[-400:])
            except Exception as _e:
                log.exception("daily: efv_matrix refresh failed - continuing")
                try:
                    import job_heartbeat as _hb
                    _hb.record("efv_matrix", ok=False, result=str(_e)[:120])
                except Exception:
                    pass
            # EV-00 progress ledger (data/efv_progress.json, the dated record
            # the glossary Source Comparison view charts). Append-only and
            # idempotent: a night with no change adds no row and only moves
            # the latest row's last_verified_at. Best-effort.
            _efv_progress_update(out_dir, "daily")
            # LIBRARY_11 Model Updates record (data/model_updates.json): the
            # vm2 row just appended lands the same night. Best-effort.
            _model_updates_update(out_dir, "daily")

        # --- 10. FA signing-window tracker (Oct-Mar). ----------------------
        # In-winter the class moves daily (signings, option decisions, QO
        # acceptances), so the daily job re-scrapes the current class and
        # re-exports the fa_* sidecars. Outside the window the FA refresh
        # rides the monthly run only; June payrolls don't move daily. The
        # months are fa_pipeline.DAILY_SCRAPE_MONTHS (the Oct-Jan option and
        # QO window plus Feb-Mar), so an October decision is first seen the
        # night after it posts, not on Nov 1 (M04-05).
        from fa_pipeline import DAILY_SCRAPE_MONTHS as _FA_DAILY_MONTHS
        if date.today().month in _FA_DAILY_MONTHS:
            with _step("d10. FA signing-window refresh", log):
                try:
                    import fa_pipeline
                    from fa_export import CLASS_YEAR as _FA_CLASS_YEAR
                    from fa_export import export_all as _export_fa
                    fa_pipeline.refresh_current_class(_FA_CLASS_YEAR,
                                                      force=no_cache)
                    _export_fa()
                except Exception:
                    log.exception("daily: FA refresh failed — continuing")
        else:
            # --- 10b. FA re-export off the FRESH projections (year-round). ----
            # ORDERING REPAIR 2026-07-25. fa_fit.team_baselines now reads
            # team_outlook out of data/mlb_projections.json (T1.0), but the
            # monthly step 6 exports the FA sidecars BEFORE the projections are
            # rebuilt: monthly 6b is a documented SKIP because the daily tail
            # re-bakes projections post-eFV-regen (in d9's rebuild_only since
            # 2026-08-07, in d9b before that), i.e. AFTER step 6 either way.
            # Outside the Nov-Mar window nothing re-exported FA afterwards, so
            # baseSrc advertised "mlb_projections" while baseWins
            # carried the PREVIOUS run's outlook (measured: 0 of 30 clubs equal,
            # mean |delta| 1.483 wins). Attributing a number to a source it does
            # not equal is worse than the old honest fallback. Re-exporting here
            # costs one cached export and makes the attribution true. Inside the
            # window d10 above already runs after the re-bake and covers this.
            with _step("d10b. FA re-export off fresh projections", log):
                try:
                    from fa_export import export_all as _export_fa
                    _export_fa()
                except Exception:
                    log.exception("daily: FA re-export failed — continuing")

        # --- d10p. Served P(enter) snapshot (M04-05, 2026-09-25) -----------
        # The frozen P(enter) decision eval scores the LAST served value before
        # each option decision, read from snapshots; the file is rewritten
        # nightly, so this records what d10 / d10b just served, one row per
        # pending_option member per night (upsert by date, last write wins).
        # Runs after BOTH branches so every night is covered. Best-effort: a
        # failed snapshot costs one night of record, never the build.
        with _step("d10p. FA P(enter) served snapshot", log):
            try:
                from fa_export import snapshot_served_penter
                log.info("fa penter snapshot: %d pending-option rows recorded",
                         snapshot_served_penter())
            except Exception:
                log.exception("daily: P(enter) snapshot failed - continuing")

        # --- d10c. TJStats SECOND Live capture of the day -----------------
        # The owner's Franklin Arias complaint was NOT a broken scraper: it
        # works. TJStats reshuffles its board CONTINUOUSLY, and we captured
        # once per day at ~12:58 UTC. Arias sat at #4 in our per-source
        # history while a live probe during the investigation returned #1,
        # because the board moved after our capture.
        #
        # This is the second polite pull of the day (the endpoint is one
        # person's JSON API; the client throttles to 1.5s between requests
        # and two pulls a day is well inside courteous use). It lands on the
        # SAME date-stamped label, so insert_snapshots upserts the morning
        # row in place -> one row per day, holding the LATEST state of that
        # day rather than the earliest. The sidecar's captured_at moves with
        # it, and export_movers now ships that timestamp so the served board
        # says WHEN it was captured instead of only what day.
        with _step("d10c. TJStats Live second capture", log):
            try:
                import tjstats
                _tj2 = tjstats.run_tjstats_pipeline(live=True, history=False,
                                                    scope="daily-pm")
                if _tj2.get("live"):
                    log.info("tjstats: second daily Live %d players @ %s",
                             _tj2["live"]["n_players"], _tj2["live"]["captured_at"])
                    tjstats.export_movers()
                elif _tj2.get("health"):
                    log.error("tjstats: second capture health check failed: %s",
                              _tj2["health"])
                _record_ingest("tjstats", _tj2.get("ok", False),
                               _tj2.get("n_rows", 0),
                               "; ".join(_tj2.get("health") or [])
                               or (_tj2.get("error") or ""),
                               scope="daily-pm", log=log)
            except Exception as e:                # noqa: BLE001
                log.exception("tjstats second capture crashed - continuing")
                _record_ingest("tjstats", False, 0, f"crashed: {e}",
                               scope="daily-pm", log=log)

        # --- d10d. ESPN unwired-article probe (log only, never ingests) ---
        with _step("d10d. ESPN new-article probe", log):
            try:
                from scrapers import probe_espn_new_prospect_article
                _esp = probe_espn_new_prospect_article()
                _record_ingest(
                    "espn_article_probe", not _esp.get("error"),
                    len(_esp.get("candidates") or []),
                    _esp.get("error") or _esp.get("summary") or "; ".join(
                        f"{c['id']} {c['headline']}"
                        for c in (_esp.get("candidates") or [])),
                    log=log)
            except Exception as e:                # noqa: BLE001
                log.exception("espn article probe crashed - continuing")
                _record_ingest("espn_article_probe", False, 0, f"crashed: {e}",
                               log=log)

        # --- d10e. Club Ledger board (ledger_board.json) ------------------
        # The /ledger/ payload (2026-09-23, D1): every club's CBT payroll on
        # both Spotrac bases, the computed tax beside Spotrac's estimate, the
        # commitments timeline as three labelled segments (never summed into a
        # payroll), controlled surplus, farm capital and the free agency ledger.
        # Reads served artifacts and the DB only, never a socket. Sits after
        # d10b's FA re-export so fa_meta / fa_class are the fresh ones; d10c and
        # d10d are taken, hence the letter. A failure leaves the previous file
        # on disk and files a red under "ledger_export" (SCHEDULED_EXPORTS).
        with _step("d10e. Club Ledger board (ledger_board.json)", log):
            # The writer is shared with the standalone rebuild-only tail
            # (_export_ledger_board, owner answer LEDTRIM-1), so the two paths
            # write the board, its shards and the CBT slice the same way.
            _export_ledger_board(log)

        # --- d10f. The postseason bracket simulator -----------------------
        with _step("d10f. Postseason bracket simulator (bracket_sim.json)", log):
            # docs/betting-2026-10/BRACKET_SIM_GATE.md 6.2: one isolated step,
            # AFTER the 9e board export (it reads the board that export
            # wrote, for the games the board prices) and after d9's
            # write_futures (it quotes the season simulator's build date in the
            # division-columns stamp), and BEFORE 6b7d, whose ODDS section
            # reads its payload. It writes data/bracket_sim.json, appends the
            # day's frozen entry to .cache/bracket_sim/record.json (first write
            # wins) and re-renders data/bracket_sim_record.json. A crash files
            # a red under "bracket_sim" and nothing else waits on it. Nothing
            # in the betting pricer, a slot, the record or a ledger reads it.
            try:
                import bracket_sim as _bsim
                _br = _bsim.run(log_fn=log.info)
                _record_ingest("bracket_sim", bool(_br.get("ok")), _br.get("n_clubs", 0),
                               (_br.get("message") or "")[:200], "mlb", log)
            except Exception as e:                # noqa: BLE001
                log.exception("bracket simulator failed - continuing")
                _record_ingest("bracket_sim", False, 0,
                               f"bracket simulator raised: {e}", "mlb", log)

        # --- d10g. Source update dates ------------------------------------
        with _step("d10g. Source update dates (source_updates.json)", log):
            # The Source Updates list on /glossary/ (owner ask 2026-10-02): one
            # row per (source, list, list date) read from the snapshot tables,
            # read-only. AFTER every ingest step of the night (d0 to d0b-ii, the
            # TJStats second capture d10c and the ESPN probe d10d), so a list
            # captured tonight is dated tonight. Idempotent: the same database
            # writes the same rows; only the `built` stamp moves. The comment
            # sits inside the _step body for tools/gen_audit_docs.py.
            _export_source_updates(log)

        # --- 6b7d. Franchise board ----------------------------------------
        with _step("6b7d. Franchise board (franchise_board.json)", log):
            # The /franchise/ payload (2026-09-23, D3): the org-level grade tree
            # in data/franchise_board.json. Reads served artifacts and three
            # caches only (standings, venues, war_daily through
            # data/franchise_spine.json); never a socket. Sits AFTER d10e so the
            # FIN section quotes the ledger board written a moment ago, after
            # d9's rebuild_only for fresh trade_values, and after the day's
            # projections; the id is the one the D3 spec reserved (6b7e is the
            # management ledger, d10e the club ledger). A refusal (fewer than 30
            # clubs on a graded branch) or a raise leaves the previous file on
            # disk and files a red under "franchise_export". The comment sits
            # inside the _step body on purpose: tools/gen_audit_docs.py credits
            # a phase's text from its _step line to the next one, so a comment
            # above the line would credit these files to d10e. The writer is
            # shared with the standalone rebuild-only tail (LEDTRIM-1).
            _export_franchise_board(log)

        # --- d10h. Awards board ------------------------------------------
        with _step("d10h. Awards board (awards.json)", log):
            # The Awards board (AWARDS_3_EXPORTER; AWARDS_PLAN 4.8): the eephus
            # selection for MVP, Cy Young, Rookie and Manager of the Year in
            # each league, the superlatives and My Ballot's candidate pools.
            # Sits AFTER 6b7d so the eWAR live rebuild, rebuild_only's
            # projections, the boards, management and the standings read have
            # all run and nothing is a run stale. Its one network read is the
            # war_daily stint frame the war board step reads too. While
            # awards_core.AWARDS_LIVE is False it writes only
            # .cache/awards/preview/ and nothing served moves. The id is d10h
            # because d10g is the Source Updates step above. A refusal or a
            # raise leaves the previous files and files a red under
            # "awards_export". The comment sits inside the _step body for
            # tools/gen_audit_docs.py, as the Franchise step's does.
            _export_awards_board(log)

        finish_run(run_id, new_snapshots=0, stat_lines=0,
                   notes=f"DAILY: {n_il} on IL, {n_debuts} debuts, {n_trades} new trades")
        # Patch the just-written run summary into timeseries.json so the
        # site's "as of" reflects this daily refresh.
        _patch_export_run_summary(out_dir / "timeseries.json", log)
        # Ingest health ledger + RED lines. Written BEFORE the site build so
        # the sidecar rides the same rsync as the rest of data/.
        write_ingest_health(out_dir, "daily", log)
        # d11. Rebuild the static site from the fresh data. Without this the daily
        # data refresh (trades/promos/IL/debuts to today, refreshed MiLB statlines)
        # never reaches the browser -- the homepage "MLB News" wire, /news/, and
        # the player pages are build-time artifacts that freeze at the last build.
        # main() chains run_daily() at its tail, so this single step also rebuilds
        # the site on a full monthly run. Best-effort: a build failure must not fail
        # the data pipeline. (nightly-build.sh also runs build_site after the pipeline
        # on the server; this makes freshness robust to how the pipeline is invoked.)
        # The deploy shell (nightly-build.sh) runs build_site as its OWN process
        # right after the pipeline, so on the box this in-process rebuild just
        # stacks a full site-build heap onto the already-peaked pipeline process
        # (an OOM contributor). EEPHUS_SKIP_INPROC_BUILD=1 skips it there; it still
        # runs by default so a bare `run_monthly.py` self-publishes.
        if os.environ.get("EEPHUS_SKIP_INPROC_BUILD") == "1":
            log.info("d11 SKIP: EEPHUS_SKIP_INPROC_BUILD=1 (deploy shell rebuilds the site separately)")
        else:
            try:
                with _step("d11. Rebuild site (build_site)", log):
                    import build_site
                    build_site.main()
            except Exception:
                log.exception("daily: site rebuild failed — continuing (data is fresh, pages stale)")
        total = time.monotonic() - _run_start
        log.info("DAILY run %s complete in %.1fs", run_id, total)
        for label, secs in _STEP_TIMES:
            log.info("  %-34s %6.1fs", label, secs)
        # Machine-readable companion so a daily run is rankable too. Daily
        # writes its OWN file: a chained daily runs inside the monthly process
        # and clears _STEP_TIMES at its start, and a standalone daily runs
        # every night, so sharing the monthly filename would clobber the
        # monthly baseline this artifact exists to preserve.
        write_step_timings("daily-chained" if chained else "daily", total, log=log,
                           path=STEP_TIMINGS_PATH.with_name("pipeline_steps_daily.json"),
                           run_id=run_id)
    except Exception:
        log.exception("DAILY run %s failed", run_id)
        finish_run(run_id, new_snapshots=0, stat_lines=0, notes="DAILY: failed")
        # A crash after d9 leaves a freshly exported timeseries.json whose run
        # and data_freshness blocks were read before finish_run, so they name
        # the previous run. d9 no longer stamps, so this is the path that moves
        # the site's "as of" line onto this run on a partial night.
        _patch_export_run_summary(out_dir / "timeseries.json", log)
        # Same reasoning as the monthly crash path: publish what we know
        # about which sources landed before the failure.
        try:
            write_ingest_health(out_dir, "daily-FAILED", log)
        except Exception:                                # noqa: BLE001
            log.exception("ingest health write failed on the crash path")
        raise


def _load_draft_pools_for_rebuild() -> dict:
    """Load MLB draft bonus pools for rebuild-only paths. Uses
    build_draft_pools which hits the on-disk cache (7-day TTL) so a
    warm rebuild stays HTTP-free. Errors are swallowed — the pool
    leaf is opt-in, so a failed scrape just demotes it to None and
    the rest of the pipeline keeps going."""
    import logging
    log = logging.getLogger("rebuild_only")
    try:
        from scrapers import build_draft_pools
        pools = build_draft_pools(
            range(2021, date.today().year + 1),
            force=False,
        )
        covered = sorted(pools.keys()) if pools else []
        log.info("rebuild_only draft pools: %d years on file (%s)",
                 len(covered), ", ".join(str(y) for y in covered))
        return pools or {}
    except Exception:
        log.exception("rebuild_only draft-pool load failed — "
                      "fin_draft_pool_efficiency will be None")
        return {}


def _affil_by_year_for_transactions(tx_cache: dict, log) -> dict[int, dict]:
    """Point-in-time team-affiliation maps keyed by event YEAR, covering every
    year that appears in the cached transactions.

    fetch_team_affiliations is season-aware (the MLB Stats API returns the
    era-correct team name + league per season), so resolving each move against
    the map for ITS OWN year fixes the 2021-reorg nomenclature: a 2019 complex
    move reads 'AZL Rangers' / Rookie, not the post-reorg 'ACL Rangers' / CPX.
    Each season's map is cached on disk for 7 days, so warm reruns do no network.
    No fallback to current naming — a year that fails to fetch stays empty, so
    moves that year surface unlabeled rather than mislabeled."""
    from stats import fetch_team_affiliations
    years: set[int] = set()
    for rows in tx_cache.values():
        for tx in (rows or []):
            d = tx.get("date") or ""
            if len(d) >= 4 and d[:4].isdigit():
                years.add(int(d[:4]))
    affil_by_year: dict[int, dict] = {}
    for yr in sorted(years):
        try:
            affil_by_year[yr] = fetch_team_affiliations(yr)
        except Exception as e:
            log.warning("team_affil fetch failed for %d (%s) — moves that year "
                        "stay unlabeled (no fallback to current naming)", yr, e)
            affil_by_year[yr] = {}
    log.info("point-in-time team affiliations: %d seasons (%s..%s)",
             len(affil_by_year), min(years) if years else "-",
             max(years) if years else "-")
    return affil_by_year


def _derive_all_level_changes() -> dict:
    """Helper: rebuild level_changes_by_key from the cached transactions
    table. Mirrors the per-player loop in main(). Used by rebuild_only().

    Team-affiliation map comes from fetch_team_affiliations(), which has
    its own 7-day on-disk cache — a warm cache returns instantly with no
    network, a cold cache does ~6 HTTP calls. The previous version of
    this function tried to import a nonexistent `team_affil` module and
    silently returned {} on every rebuild, killing the per-org H1/H2
    promotion-tendency data feeding the ETA model.
    """
    _log = logging.getLogger("derive_level_changes")
    try:
        from stats import derive_level_changes, fetch_team_affiliations
    except Exception as e:
        _log.warning("stats import failed (%s) — skipping", e)
        return {}
    tx_cache = load_player_transactions()
    if not tx_cache:
        return {}
    affil_by_year = _affil_by_year_for_transactions(tx_cache, _log)
    out: dict = {}
    for key, tx_rows in tx_cache.items():
        try:
            evs = derive_level_changes(tx_rows, affil_by_year)
            if evs:
                out[key] = evs
        except Exception as e:
            _log.debug("derive_level_changes failed for %s: %s", key, e)
            continue
    _log.info("rebuilt level_changes for %d players (from %d tx-cache keys)",
              len(out), len(tx_cache))
    return out


def _load_spotrac_ifa(force: bool, log, label: str) -> tuple[dict, dict]:
    """Scrape Spotrac IFA tracker once and return both downstream views.

    Returns `(ifa_bonus_by_key, ifa_spending_by_org)`. On any failure both
    halves are returned as empty dicts and the exception is logged at
    EXCEPTION level — the rest of the pipeline degrades gracefully.

    Shared between `main()` (force=force_refetch, label="spotrac IFA")
    and `rebuild_only()` (force=False, label="rebuild_only").
    """
    try:
        from spotrac import (
            scrape_spotrac_ifa_range,
            build_ifa_bonus_by_key,
            build_org_ifa_spending,
        )
        years = list(range(2021, date.today().year + 1))
        rows = scrape_spotrac_ifa_range(years, force=force)
        bonus_by_key = build_ifa_bonus_by_key(rows)
        spending_by_org = build_org_ifa_spending(rows)
        log.info("%s: %d signings, %d players with bonus, %d orgs with totals",
                 label, len(rows), len(bonus_by_key), len(spending_by_org))
        return bonus_by_key, spending_by_org
    except Exception:
        log.exception("%s: spotrac IFA scrape failed — continuing without bonus data", label)
        return {}, {}


def _merge_ifa_bonuses_into_acquisitions(
    acquisitions: dict, ifa_bonus_by_key: dict, log, label: str,
) -> int:
    """Fill in `acquisitions[key].bonus_usd` from the Spotrac IFA payload.

    Only IFA-method records with an existing None bonus are touched.
    Returns the count of records updated.
    """
    n_merged = 0
    for key, bonus in ifa_bonus_by_key.items():
        rec = acquisitions.get(key)
        if rec and rec.get("method") == "international_fa" and rec.get("bonus_usd") is None:
            rec["bonus_usd"] = bonus
            n_merged += 1
    log.info("%s: merged %d IFA bonuses into acquisitions", label, n_merged)
    return n_merged


def _load_spotrac_contracts(force: bool, log, label: str) -> dict:
    """Scrape Spotrac per-team contract pages once; return contracts_by_key.

    On any failure returns {} and logs the exception — surplus calcs fall
    back to the league-min+arb salary estimate.
    """
    try:
        from spotrac import scrape_all_spotrac_contracts, build_contracts_by_key
        rows = scrape_all_spotrac_contracts(force=force)
        # keep_alts: a name slug two players share keeps both Spotrac rows, and
        # the export binds each to its own mlbam id (storage.resolve_contracts_to_ids).
        out = build_contracts_by_key(rows, keep_alts=True)
        log.info("%s: %d player-rows fetched, %d unique players", label, len(rows), len(out))
        _spotrac_format_sentinel(log, label)
        return out
    except Exception:
        log.exception("%s: spotrac contracts scrape failed — falling back to manual overrides only", label)
        return {}


# Set when the Spotrac format sentinel files red in this process, so a
# standalone --rebuild-only exits non-zero after finishing its writes.
_SPOTRAC_FORMAT_RED = False


def _spotrac_format_sentinel(log, label: str) -> dict:
    """File the `spotrac_contracts_format` ingest row for the contracts scrape
    that just ran (spotrac.contract_format_report). A wrong-type cell never
    reaches a served position (the parser reads it as None), but the run says
    so: a red ingest row, an error line, and a non-zero exit for a standalone
    --rebuild-only."""
    global _SPOTRAC_FORMAT_RED
    try:
        from spotrac import contract_format_report
        rep = contract_format_report()
    except Exception as e:                                  # noqa: BLE001
        rep = {"ok": False, "n_pages": 0, "n_rows": 0, "n_coded": 0,
               "by_kind": {"report": 1}, "examples": [str(e)[:80]], "side_check": None}
    side = rep.get("side_check") or {}
    msg = (f"{rep['n_pages']} pages, {rep['n_rows']} rows, {rep['n_coded']} coded "
           f"positions mapped; side check {side.get('agree', '-')}/{side.get('matched', '-')}; "
           f"wrong-type cells {rep['by_kind'] or 'none'}")
    _record_ingest("spotrac_contracts_format", bool(rep["ok"]), rep["n_rows"], msg, log=log)
    if not rep["ok"]:
        _SPOTRAC_FORMAT_RED = True
        if log:
            log.error("!!! SPOTRAC FORMAT RED (%s): %s; examples %s", label, msg,
                      rep.get("examples"))
    return rep


def _derive_all_transactions() -> dict:
    """Helper: rebuild transactions_by_key from cached per-player tx rows."""
    try:
        from stats import derive_transactions
    except Exception:
        return {}
    tx_cache = load_player_transactions()
    out: dict = {}
    for key, tx_rows in (tx_cache or {}).items():
        try:
            txs = derive_transactions(tx_rows)
            if txs:
                out[key] = txs
        except Exception:
            continue
    return out


def _post_export_summary(out_path: Path, all_snaps, log) -> None:
    """Final log line summarizing what just got written. Helps the user
    confirm a regen actually picked up the new fangraphs rows."""
    try:
        from collections import Counter
        src_counter = Counter()
        latest_date = ""
        for s in all_snaps:
            src_counter[s.source] += 1
            if s.snapshot_date > latest_date:
                latest_date = s.snapshot_date
        fg_count = src_counter.get("fangraphs", 0)
        n_total = sum(src_counter.values())
        n_sources = len(src_counter)
        # v19 — ASCII arrow so Windows cp1252 console doesn't error.
        log.info("timeseries.json refreshed: %d snapshots across %d sources "
                 "(latest %s, fangraphs rows: %d) -> %s",
                 n_total, n_sources, latest_date or "n/a", fg_count, out_path)
    except Exception:
        log.exception("post-export summary failed (non-fatal)")


def _utf8_console() -> None:
    """Stop a non-UTF-8 console turning a log line into a traceback.

    Several modules log a right-arrow ("wrote N players -> path"). On a Windows
    console defaulting to cp1252 the StreamHandler cannot encode it, so logging
    prints a UnicodeEncodeError traceback for a line that is pure progress
    reporting. Measured 2026-07-30: seven such tracebacks in one rebuild, every
    one of them cosmetic, and every one of them alarming in a log a human is
    reading to decide whether a pipeline run went well.

    Reconfigures stdout/stderr to UTF-8 and, failing that, degrades to replacing
    the offending character. Never raises: a logging convenience must not be the
    thing that stops a run. No effect on the Linux box, where UTF-8 is already
    the default.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(force_refetch: bool = False, skip_stats: bool = False,
         out_dir: Path = Path("data"), workers: int | None = None,
         cache_ttl: int | None = None, no_cache: bool = False, fast: bool = False):
    _utf8_console()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("run_monthly")
    # BEFORE any step reads os.environ - the monthly chains run_daily, whose 9e
    # odds snapshot is key-gated. See _load_env_files.
    _load_env_files(log.info)
    import stats as stats_mod
    # Propagate --force to stats module so the per-run HTTP cache can be bypassed
    stats_mod.FORCE_REFETCH = force_refetch or no_cache
    # Propagate --cache-ttl if specified
    if cache_ttl is not None:
        stats_mod.CACHE_TTL_SECONDS = max(0, cache_ttl)

    init_db()
    run_id = start_run()
    log.info("started run %s", run_id)

    # Keep the permanent game-feed cache bounded: completed games are cached
    # ~forever (immutable), so prune by mtime instead of TTL. Best-effort.
    try:
        import feed_cache
        feed_cache.prune_old_feeds()
    except Exception as e:  # noqa: BLE001 — never let cache maintenance abort a run
        log.warning("feed cache prune skipped: %s", e)
    # The other big refetchable caches (win_prob, statcast_metrics,
    # zone_metrics). Opt-in via env; a run with nothing configured is a no-op.
    _maybe_prune_cache(log)

    new_count = 0
    stat_count = 0
    # v19 — Reset step timer for this run (don't accumulate across calls).
    _STEP_TIMES.clear()
    _run_start = time.monotonic()

    try:
        # --- 0. Fix encoding in CSV ----------------------------------------
        with _step("0. CSV encoding fix", log):
            import subprocess
            result = subprocess.run([sys.executable, "fix_encoding.py"],
                                  capture_output=True, text=True, cwd=Path(__file__).parent)
            if result.returncode == 0:
                log.info(result.stdout.strip())
            else:
                log.warning("encoding fix script failed: %s", result.stderr)

        # --- 0b. Auto-ingest FanGraphs CSV drops --------------------------
        # Files dropped into data/fangraphs_imports/ matching
        # `fangraphs_<list>_<YYYY-MM-DD>.csv` get parsed + inserted into
        # the snapshots DB before the rest of the run picks them up.
        # Wrapped in try/except so a malformed file never blocks the
        # downstream pipeline.
        with _step("0b. FanGraphs CSV drops", log):
            try:
                from fangraphs_csv import ingest_drops as _fg_ingest_drops
                # called_from_run_monthly=True so the function knows the
                # full pipeline will refresh timeseries.json downstream and
                # suppresses the standalone-rebuild hint.
                fg_inserted, fg_files = _fg_ingest_drops(called_from_run_monthly=True)
                if fg_files:
                    log.info("fangraphs_csv: ingested %d snapshots from %d report-set(s)",
                             fg_inserted, fg_files)
            except Exception:
                log.exception("fangraphs_csv: drop-folder ingest failed — "
                              "continuing with the rest of the pipeline")

        # --- 0c / 0d / 1 in parallel ----------------------------------
        # These three phases write to disjoint tables (draft_*, overseas_*,
        # snapshots) and never read each other's output during this block.
        # Running them concurrently overlaps their HTTP work (~30-60s
        # wall-clock savings on cold runs). SQLite WAL mode + per-call
        # connect() in storage.py makes concurrent writes safe; failures
        # in any one phase log + continue without blocking the others.

        def _run_draft_pipeline():
            with _step("0c. Draft pipeline (scrape + promote + export)", log):
                try:
                    from scrapers import scrape_all_draft, scrape_mlb_draft_tracker
                    from storage import insert_draft_snapshots, upsert_draft_results
                    from draft_promotion import promote_drafted_players, seed_signed_draftees
                    from draft_export import export_draft_json

                    draft_snaps = scrape_all_draft(force=force_refetch)
                    if draft_snaps:
                        n_d = insert_draft_snapshots(draft_snaps)
                        log.info("inserted %d draft snapshot rows", n_d)
                    this_year = date.today().year
                    # 2017+ so the historical classes stay authoritative: the FG
                    # 2017 board is pre-draft (no picks) and the 2018/2020 FG CSVs
                    # encode Pick as <TEAM>/<overall>, so the tracker is the org
                    # source of record for those years. Idempotent upsert.
                    for y in range(2017, this_year + 1):
                        rows = scrape_mlb_draft_tracker(y, force=force_refetch)
                        if rows:
                            upsert_draft_results(rows)
                    from scrapers import scrape_spotrac_draft_order, scrape_tankathon_lottery
                    from storage import upsert_draft_order, upsert_draft_lottery_odds
                    for y in (this_year, this_year + 1):
                        so_rows = scrape_spotrac_draft_order(y, force=force_refetch)
                        if so_rows:
                            upsert_draft_order(so_rows)
                    tk_rows = scrape_tankathon_lottery(this_year + 1, force=force_refetch)
                    if tk_rows:
                        upsert_draft_lottery_odds(tk_rows)
                    promote_drafted_players()
                    seed_signed_draftees()
                    # v31.7 — Fetch college / HS / showcase stats from
                    # FG player pages for draft prospects with an FG ID
                    # on file. Concurrent (8 workers); on-disk cache
                    # so subsequent runs are fast.
                    try:
                        from draft_stats import refresh_draft_stats
                        refresh_draft_stats(force=force_refetch, workers=8)
                    except Exception:
                        log.exception("draft_stats fetch crashed — continuing with draft export")
                    # v33 — Second-source gap-fill for prospects FanGraphs can't
                    # cover (the ~88% with no FG id). MLB-API identity backfill
                    # then NCAA D-I box scores (headless render of stats.ncaa.org).
                    # Best-effort: a source failing must not abort the export.
                    try:
                        from college_stats import refresh_college_fallback_stats
                        counts = refresh_college_fallback_stats(force=force_refetch)
                        log.info("college fallback stats: %s", counts)
                    except Exception:
                        log.exception("college fallback stats crashed — continuing with draft export")
                    # v34 — extend the NCAA capture to CollegeSavant's broader
                    # tracked universe (players who are NOT draft prospects), so
                    # those tracked players carry a real college box score too.
                    # Bounded by COLLEGESAVANT_MAX_TEAMS; best-effort.
                    if COLLEGESAVANT_MAX_TEAMS:
                        try:
                            from college_stats import refresh_collegesavant_stats
                            cs_n = refresh_collegesavant_stats(
                                this_year, force=force_refetch,
                                max_teams=COLLEGESAVANT_MAX_TEAMS)
                            log.info("collegesavant box scores: %d rows", cs_n)
                        except Exception:
                            log.exception("collegesavant stats crashed — continuing")
                    n_draft = export_draft_json(out_dir / "draft_timeseries.json")
                    log.info("draft pipeline: exported %d prospects across all classes",
                             n_draft)
                except Exception:
                    log.exception("draft pipeline crashed — continuing with MiLB run")

        def _run_overseas_pipeline():
            with _step("0d. Overseas pipeline (refresh + promote + export)", log):
                try:
                    from overseas_stats import refresh_overseas_stats
                    from overseas_promotion import promote_signed_players, ingest_postings
                    from overseas_export import export_overseas_json
                    refresh_overseas_stats(force=force_refetch)
                    ingest_postings()
                    promote_signed_players()
                    n_ov = export_overseas_json(out_dir / "overseas_timeseries.json")
                    log.info("overseas pipeline: exported %d prospects", n_ov)
                except Exception:
                    log.exception("overseas pipeline crashed — continuing with MiLB run")

        def _run_milb_scrape() -> tuple[int, dict]:
            with _step("1. Scrape MiLB rankings + insert snapshots", log):
                snapshots, csv_birth_dates = scrape_all(force=force_refetch)
                log.info("scraped %d total snapshot rows", len(snapshots))
                # One ingest_health row per wired ESPN interval: a refused
                # fetch or a 0-row parse of a list that exists is a miss,
                # not "nothing published" (see scrapers.espn_interval_outcomes).
                try:
                    from scrapers import espn_interval_outcomes
                    for _label, _n in espn_interval_outcomes(snapshots):
                        _record_ingest(
                            "espn", _n > 0, _n,
                            f"{_label}: {_n} rows" if _n else
                            f"{_label}: 0 rows (fetch refused or parser found nothing; see log)",
                            scope=_label, log=log)
                except Exception:                            # noqa: BLE001
                    log.exception("espn per-interval health record failed - continuing")
                _new = insert_snapshots(snapshots)
                log.info("inserted %d new snapshot rows", _new)
                ingest_source_article_drops(out_dir, log)
                upsert_birth_dates(csv_birth_dates)
                if csv_birth_dates:
                    log.info("upserted %d birth dates from CSV", len(csv_birth_dates))
                return _new, csv_birth_dates

        with _step("0c/0d/1 parallel block", log):
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as _ex_0:
                _f_draft = _ex_0.submit(_run_draft_pipeline)
                _f_overseas = _ex_0.submit(_run_overseas_pipeline)
                _f_milb = _ex_0.submit(_run_milb_scrape)
                # MiLB scrape result is needed by downstream steps; wait
                # for it explicitly. The other two are fire-and-forget
                # (their exceptions are logged internally).
                new_count, _ = _f_milb.result()
                for _f in (_f_draft, _f_overseas):
                    _f.result()  # propagate any unexpected exception

        # --- 1c. TJStats Top-100 (Thomas Nestico) ----------------------
        # The Live board is scraped at the real moment and feeds TJStats's
        # contribution to PRESENT-DAY consensus (it lands in the shared snapshots
        # table with today's date -> newest tjstats snapshot -> drives current).
        # Named historical snapshots land in the point-in-time sidecar
        # (tjstats_snapshots) only, never the shared table, so they can't move
        # current consensus/farm rankings. Runs SEQUENTIALLY (not in the parallel
        # block) to avoid DB-lock contention, and BEFORE the consensus build below.
        with _step("1c. TJStats Top-100 (Live + history)", log):
            try:
                import tjstats
                _tj = tjstats.run_tjstats_pipeline(live=True, history=True,
                                                   scope="monthly")
                if _tj.get("health"):
                    log.error("tjstats: health check failed, skipped ingest: %s", _tj["health"])
                elif _tj.get("live"):
                    log.info("tjstats: Live %d players @ %s + %d historical snapshot(s)",
                             _tj["live"]["n_players"], _tj["live"]["captured_at"],
                             len(_tj["history"]))
                    tjstats.export_movers()   # wire sidecar + source events
                _record_ingest("tjstats", _tj.get("ok", False), _tj.get("n_rows", 0),
                               "; ".join(_tj.get("health") or [])
                               or (_tj.get("error") or ""),
                               scope="monthly", log=log)
            except Exception as e:                # noqa: BLE001
                log.exception("tjstats pipeline crashed — continuing")
                _record_ingest("tjstats", False, 0, f"crashed: {e}",
                               scope="monthly", log=log)

        # --- 1c-bis. Just Baseball rolling board (content-hash gated) ----
        # Replaces the old fixed-label JB entry in scrape_all (see
        # scrapers.JB_INTERVALS for the chimera this prevents). Writes only
        # when JB has actually republished. Never aborts the run.
        with _step("1c-bis. Just Baseball rolling capture", log):
            try:
                from scrapers import run_just_baseball_live
                _jb = run_just_baseball_live(force=force_refetch)
                if _jb.get("live"):
                    log.info("just_baseball: NEW board %d players -> %r",
                             _jb["live"]["n_players"], _jb["live"]["label"])
                elif _jb.get("unchanged"):
                    log.info("just_baseball: board unchanged (%d players), no write",
                             _jb["unchanged"]["n_players"])
                elif _jb.get("health"):
                    log.error("just_baseball: health gate refused: %s", _jb["health"])
                else:
                    log.error("just_baseball: capture failed: %s", _jb.get("error"))
                _ok = bool(_jb.get("live") or _jb.get("unchanged"))
                _n = int((_jb.get("live") or _jb.get("unchanged")
                          or {}).get("n_players") or 0)
                _record_ingest("just_baseball", _ok, _n,
                               "; ".join(_jb.get("health") or [])
                               or (_jb.get("error") or "")
                               or ("unchanged" if _jb.get("unchanged") else ""),
                               log=log)
            except Exception as e:                # noqa: BLE001
                log.exception("just_baseball capture crashed - continuing")
                _record_ingest("just_baseball", False, 0, f"crashed: {e}", log=log)

        # --- 1c-ter. ESPN unwired-article probe (log only) ---------------
        # ESPN needs a code edit per new McDaniel list; without this probe a
        # missed list is indistinguishable from a healthy source.
        with _step("1c-ter. ESPN new-article probe", log):
            try:
                from scrapers import probe_espn_new_prospect_article
                _esp = probe_espn_new_prospect_article(force=force_refetch)
                _record_ingest(
                    "espn_article_probe", not _esp.get("error"),
                    len(_esp.get("candidates") or []),
                    _esp.get("error") or _esp.get("summary") or "; ".join(
                        f"{c['id']} {c['headline']}"
                        for c in (_esp.get("candidates") or [])),
                    log=log)
            except Exception as e:                # noqa: BLE001
                log.exception("espn article probe crashed - continuing")
                _record_ingest("espn_article_probe", False, 0, f"crashed: {e}",
                               log=log)

        # --- 2. Build consensus ----------------------------------------
        with _step("2. Build consensus timeseries", log):
            all_snaps = load_all_snapshots()
            timeseries = build_timeseries(all_snaps, normalize=ADOPT_NORMALIZED_CONSENSUS)
            log.info("built timeseries for %d players", len(timeseries))

        # --- 2a. Bulk resolve IDs + birth dates for every prospect -----
        # Single bulk pass that:
        #   1. Builds the PlayerIndex once (disk-cached, ~0.4s cold / ~50ms warm)
        #   2. Resolves every uncached prospect using position-aware scoring
        #   3. Collects birth dates for free from the same index payload
        # Replaces ~300ms-per-prospect sequential people-search calls and the
        # per-prospect birth-date fetch loop with one parallel pass.
        season = date.today().year
        with _step("2a. Bulk resolve IDs + birth dates", log):
            all_prospects_for_resolve = [
                (p.player_key, p.player_name, p.position)
                for p in timeseries
            ]
            log.info("bulk resolving IDs + birth dates for %d prospects",
                     len(all_prospects_for_resolve))
            ids_by_key, bds_from_index, player_index = bulk_resolve_ids(
                all_prospects_for_resolve,
                season=season,
                force_rebuild_index=force_refetch,
                last_list_year_by_key=_vintage_years_by_key(timeseries),
            )
            # overwrite=True because these dates are tied to a freshly-resolved
            # MLBAM ID; any pre-existing date in the DB may correspond to a
            # previously-cached wrong ID and is now stale. One connection and
            # one commit for the whole batch (perf: the per-row loop cost
            # about 55 s of this step on a monthly night).
            upsert_birth_dates(bds_from_index, overwrite=True)
            if bds_from_index:
                log.info("upserted %d birth dates from PlayerIndex", len(bds_from_index))
            # Persist the RESOLUTION itself, not just what it implied. The ids
            # lived only in the .cache map, which the export cannot see:
            # --rebuild-only passes an empty player_ids map, so a row with no
            # current-season statline and no photo binding published
            # `mlbam_id: null` even though this step had just resolved it. That
            # is how the 2026 draft class stayed unidentifiable on the board
            # after their ids came back. Same reasoning as the birth dates
            # above, one line later than it should have been.
            try:
                from storage import bind_player_ids
                n_bound = bind_player_ids(ids_by_key)
                if n_bound:
                    log.info("bound %d resolved MLBAM ids into player_photos", n_bound)
            except Exception:                                # noqa: BLE001
                log.exception("player id binding failed - continuing")

        # --- 2b. Bulk fetch draft data for the full window of years a tracked
        # prospect could plausibly have been drafted in. One call per year
        # returns thousands of picks each; matching to tracked prospects happens
        # in-memory via mlbam_id. A no-draft-match is NOT defaulted to IFA — it is
        # classified from data below (acquisition_classify). The window spans a
        # full career length so older prospects/recent grads (e.g. a 2016 R1 pick)
        # still resolve to Draft instead of falling through. /draft/{year} payloads
        # are cached on disk for 30 days, so reruns within a month are near-free.
        with _step("2b. Bulk fetch draft data (career-span window)", log):
            draft_years = list(range(season - 20, season + 1))
            log.info("fetching draft picks for years %s", draft_years)
            draft_by_id = bulk_fetch_drafts(draft_years)

        acquisitions: dict[str, dict] = {}
        unresolved_by_key: dict[str, int] = {}  # no draft match → classify from data below
        for p in timeseries:
            mid = ids_by_key.get(p.player_key)
            if mid is None:
                continue
            pick = draft_by_id.get(mid)
            if pick is not None:
                acquisitions[p.player_key] = {
                    "method":       "draft",
                    "year":         pick["year"],
                    "round_label":  pick["round_label"],
                    "pick_round":   pick["pick_round"],
                    "pick_overall": pick["pick_overall"],
                    "bonus_usd":    pick["bonus_usd"],
                    "team_name":    pick["team_name"],
                    "school":       pick["school"],
                    "signing_date": None,
                }
            else:
                # No draft match — do NOT default to IFA. Collect for the
                # data-derived classification below (signing window + explicit
                # ifa_timeseries match); unresolved entries become 'unknown'.
                unresolved_by_key[p.player_key] = mid

        # --- 2b.ii Classify the no-draft-match prospects from DATA — never a
        # default. One /transactions call per prospect returns the SFA/SGN signing
        # (team + date, the MLB API doesn't expose bonus dollars). A prospect is
        # international_fa ONLY on positive evidence — an explicit ifa_timeseries
        # signing, or a signing in the international window (Jan-Apr) — otherwise
        # 'unknown' ("Entry type not on file"). Spotrac (2b.iii) fills bonus_usd.
        with _step("2b.ii. Acquisition classification (no-draft-match)", log):
            if unresolved_by_key:
                from acquisition_classify import (classify_acquisition,
                                                  load_ifa_signing_ids)
                log.info("classifying %d no-draft-match prospects",
                         len(unresolved_by_key))
                signings = bulk_fetch_ifa_signings(unresolved_by_key.values())
                ifa_mids, ifa_keys = load_ifa_signing_ids(out_dir / "ifa_timeseries.json")
                n_ifa = n_unknown = 0
                for key, mid in unresolved_by_key.items():
                    rec = classify_acquisition(
                        None, signings.get(mid),
                        (key in ifa_keys) or (mid in ifa_mids))
                    acquisitions[key] = rec
                    if rec["method"] == "international_fa":
                        n_ifa += 1
                    else:
                        n_unknown += 1
                log.info("acquisition classify: %d international_fa, %d unknown "
                         "(of %d no-draft-match)", n_ifa, n_unknown,
                         len(unresolved_by_key))

        # --- 2b.iii Spotrac IFA tracker — bonus dollars + per-org cycle
        # spending. Scrapes 2021-current; cached per year on disk so
        # subsequent runs are near-instant. Two outputs feed downstream:
        #   * ifa_bonus_by_key  — {player_key: bonus_usd}; merged into
        #     acquisitions[key].bonus_usd for IFA-method prospects so
        #     the detail page can show the actual signing bonus.
        #   * ifa_spending_by_org — {org: {year: {total_usd, signings,
        #     top_bonus, top_player}}}; captures *every* signing across
        #     2021-now (graded prospects + org filler) so the farm-page
        #     "IFA spending" view reflects true cycle commitment, not
        #     just the slice that bled into our tracker.
        ifa_bonus_by_key: dict[str, int] = {}
        ifa_spending_by_org: dict[str, dict[int, dict]] = {}
        with _step("2b.iii. Spotrac IFA scrape + merge", log):
            ifa_bonus_by_key, ifa_spending_by_org = _load_spotrac_ifa(
                force=force_refetch, log=log, label="spotrac IFA",
            )
            _merge_ifa_bonuses_into_acquisitions(
                acquisitions, ifa_bonus_by_key, log, label="spotrac IFA",
            )

        # Spotrac team contract pages — pulls current-year salary + AAV +
        # remaining contract years for every active MLB roster player.
        # Used downstream to replace the league-min+arb salary estimate
        # in the realized-surplus calc for graduates. ~30 HTTP requests
        # per regen (cached); failure is non-fatal so the rest of the
        # pipeline keeps running with the synthesized salary model.
        with _step("2b.iv. Spotrac contracts scrape", log):
            contracts_by_key = _load_spotrac_contracts(
                force=force_refetch, log=log, label="spotrac contracts",
            )

        # MLB Draft bonus-pool back-fill — fetches per-year articles
        # for 2021-current and consolidates the per-team pool + per-pick
        # slot value into one nested dict keyed by year. Drives the
        # spending-block utilization caption on the farm detail page.
        # 2024-2026 articles parse to full 30-team coverage; 2021-2023
        # have partial coverage (top teams only) per the article format.
        draft_pools: dict = {}
        with _step("2b.v. MLB draft bonus-pool back-fill", log):
            try:
                from scrapers import build_draft_pools
                draft_pools = build_draft_pools(
                    range(2021, date.today().year + 1),
                    force=force_refetch,
                )
                covered = sorted(draft_pools.keys())
                log.info("MLB draft pools: %d years on file (%s)",
                         len(draft_pools), ", ".join(str(y) for y in covered))
            except Exception:
                log.exception("MLB draft pool scrape failed — continuing without pool data")

        with _step("2b.vi. Upsert acquisitions", log):
            if acquisitions:
                upsert_acquisitions(acquisitions)
                n_draft = sum(1 for a in acquisitions.values() if a["method"] == "draft")
                log.info("acquisitions: %d draft, %d IFA",
                         n_draft, len(acquisitions) - n_draft)

        # --- 2b.iii Detect current IL stints. Same /transactions endpoint
        # as IFA + trade discovery, so we share its 30-day disk cache.
        # Returns only players currently on IL; everyone else gets cleared
        # so a prior IL badge doesn't linger after activation.
        with _step("2b.vii. IL status check", log):
            il_mids_by_key = {p.player_key: ids_by_key.get(p.player_key)
                              for p in timeseries
                              if ids_by_key.get(p.player_key) is not None
                              and p.status != "debuted"}
            log.info("checking IL status for %d active prospects",
                     len(il_mids_by_key))
            # Same concurrency as the 2b.iii transactions fetch on the same
            # endpoint (RU08: 116.7 s at 8 workers on a cold cache);
            # --workers / EEPHUS_MAX_WORKERS still caps it.
            il_by_mid = bulk_fetch_il_status(il_mids_by_key.values(),
                                             max_workers=workers or 24)
            il_updates: dict[str, dict | None] = {}
            for key, mid in il_mids_by_key.items():
                il_updates[key] = il_by_mid.get(mid)
            upsert_il_status(il_updates)
            # Append-only IL stint timeline (records placements once, stamps
            # activation when a player comes off). Idempotent; runs here too
            # so the timeline accrues even on monthly-only cadence.
            try:
                _ilh = record_il_observation(load_il_status())
                log.info("IL: %d currently on IL (il_history +%d placed / %d activated)",
                         sum(1 for v in il_updates.values() if v),
                         _ilh["placed"], _ilh["activated"])
            except Exception:
                log.exception("il_history update failed — continuing")
                log.info("IL: %d prospects currently on IL",
                         sum(1 for v in il_updates.values() if v))

        # --- 2b.viii-2b.xii External data-source ingests ------------------
        # Five standalone, disk-cached, fail-soft ingests that each land a
        # data/*.json sidecar for the model/consensus layer (that wiring lives
        # elsewhere; this block only fetches + lands the data). Every module is
        # already internally fail-soft (a layout / network failure keeps the
        # prior on-disk cache and returns without raising), and each step is
        # ADDITIONALLY wrapped here + individually skippable via its own
        # EEPHUS_SKIP_* env gate so a flaky source can be disabled without a
        # code change. None of these feed any other step in THIS run.

        # 2b.viii Tommy John surgery list (community sheet CSV) ->
        # data/tj_surgery.json. Entry: tj_surgery.run().
        if os.environ.get("EEPHUS_SKIP_TJ_SURGERY") == "1":
            log.info("2b.viii SKIP: EEPHUS_SKIP_TJ_SURGERY=1 (Tommy John surgery ingest)")
        else:
            with _step("2b.viii. Tommy John surgery list ingest", log):
                try:
                    import tj_surgery
                    _tj_surg = tj_surgery.run()
                    log.info("tj_surgery: landed %d players / %d surgeries",
                             _tj_surg.get("n_players", 0), _tj_surg.get("n_rows", 0))
                except Exception:
                    log.exception("tj_surgery ingest failed - continuing")

        # 2b.ix Official MLB draft slot/bonus keyed by MLBAM id ->
        # data/draft_bonus_slot.json. Entry: draft_bonus.build() (there is no
        # run(); build lands the JSON). --force bypasses the per-year cache.
        if os.environ.get("EEPHUS_SKIP_DRAFT_BONUS") == "1":
            log.info("2b.ix SKIP: EEPHUS_SKIP_DRAFT_BONUS=1 (draft slot/bonus ingest)")
        else:
            with _step("2b.ix. MLB draft slot/bonus ingest", log):
                try:
                    import draft_bonus
                    _db_records, _db_report = draft_bonus.build(use_cache=not force_refetch)
                    log.info("draft_bonus: %d unique MLBAM ids (%d with bonus) across %s",
                             _db_report.get("unique_mlbam", 0),
                             _db_report.get("records_with_bonus", 0),
                             _db_report.get("years_landed", []))
                except Exception:
                    log.exception("draft_bonus ingest failed - continuing")

        # 2b.x Ballpark metadata from the StatsAPI /venues endpoint ->
        # data/venue_meta.json. Entry: venue_meta.build().
        if os.environ.get("EEPHUS_SKIP_VENUE_META") == "1":
            log.info("2b.x SKIP: EEPHUS_SKIP_VENUE_META=1 (ballpark metadata ingest)")
        else:
            with _step("2b.x. Ballpark venue metadata ingest", log):
                try:
                    import venue_meta
                    _venues = venue_meta.build()
                    log.info("venue_meta: landed %d venues", len(_venues))
                except Exception:
                    log.exception("venue_meta ingest failed - continuing")

        # 2b.xi Amateur / winter / independent league season stats ->
        # data/_labs/amateur_leagues.json (tracked, unpublished, read by no
        # page). Entry: amateur_leagues.build() (warm_cache only primes
        # caches; build lands the keyed JSON).
        if os.environ.get("EEPHUS_SKIP_AMATEUR_LEAGUES") == "1":
            log.info("2b.xi SKIP: EEPHUS_SKIP_AMATEUR_LEAGUES=1 (amateur/winter/indy stats ingest)")
        else:
            with _step("2b.xi. Amateur/winter/indy league stats ingest", log):
                try:
                    import amateur_leagues
                    _amateur = amateur_leagues.build()
                    log.info("amateur_leagues: landed %d players / %d season lines",
                             len(_amateur), sum(len(v) for v in _amateur.values()))
                except Exception:
                    log.exception("amateur_leagues ingest failed - continuing")

        # 2b.xii MLB Pipeline point-in-time Top-100 vintages ->
        # data/pipeline_vintages.json. Entry: pipeline_vintage.build() (there is
        # no run(); build lands the JSON).
        if os.environ.get("EEPHUS_SKIP_PIPELINE_VINTAGE") == "1":
            log.info("2b.xii SKIP: EEPHUS_SKIP_PIPELINE_VINTAGE=1 (Pipeline vintage ingest)")
        else:
            with _step("2b.xii. MLB Pipeline vintage boards ingest", log):
                try:
                    import pipeline_vintage
                    _vint = pipeline_vintage.build()
                    log.info("pipeline_vintage: landed %d vintage years (mlbam fill %.1f%%)",
                             len(_vint.get("years", [])),
                             100 * _vint.get("mlbam_fill_rate", 0.0))
                except Exception:
                    log.exception("pipeline_vintage ingest failed - continuing")

        # --- 2c. Affiliate roster map. ~6 HTTP calls (one per sport level)
        # returns every MLB + MiLB team with its parent_org_id, which lets
        # us group the PlayerIndex by (parent_org_abbr, level) to build
        # full affiliate rosters for the farm-system page. Builds the
        # roster structure here so storage.export_timeseries_json stays a
        # pure serializer.
        _team_affil_start = time.monotonic()
        log.info("fetching team affiliations for season %d", season)
        team_affil = fetch_team_affiliations(season)
        _STEP_TIMES.append(("2c. Team affiliations fetch", time.monotonic() - _team_affil_start))

        # Map of MLBAM ID -> {player_key, fv_label, fv_raw} for our tracked
        # prospects. The roster builder uses this to flag and grade matches.
        tracked_by_mid: dict[int, dict] = {}
        for p in timeseries:
            mid = ids_by_key.get(p.player_key)
            if mid is None:
                continue
            latest = p.points[-1] if p.points else None
            # fv_synthetic_only: this player's ONLY contributing source is a
            # fabricated constant anchor (performance_ingest / auto_detect), so
            # fv_raw is a placeholder rather than anybody's published opinion.
            #
            # WHY THIS FLAG EXISTS. efv_ungraded.flagship_owns() partitions on
            # `fv_raw is not None`, and its docstring states the invariant as
            # "has a scout grade -> consensus point -> fv_raw set -> FLAGSHIP".
            # The constant breaks that invariant: consensus folds it back in as a
            # LAST RESORT (consensus.py CONSTANT_ANCHOR_SOURCES) so these players
            # do not vanish from the board, which sets fv_raw, which makes them
            # read as scouted, which routes them AWAY from the provisional model
            # built to replace the constant. Measured 2026-08-05: 2,632 of the
            # 2,720 constant-only players were excluded that way, every one of
            # them carrying fv_raw exactly 35.0. The constant was blocking its own
            # replacement. Same defect the docstring already describes for the
            # retired baseballamerica_statcast_by_age FV 40.
            _srcs = set(getattr(latest, "sources_contributing", None) or ()) if latest else set()
            tracked_by_mid[mid] = {
                "player_key": p.player_key,
                "fv_label": latest.consensus_fv_label if latest else None,
                "fv_raw":   latest.consensus_fv_raw   if latest else None,
                "fv_synthetic_only": bool(_srcs) and _srcs <= CONSTANT_ANCHOR_SOURCES,
                "status":   p.status,
            }

        from datetime import date as _date
        def _age_from(bd: str | None) -> float | None:
            if not bd:
                return None
            try:
                b = _date.fromisoformat(bd)
            except ValueError:
                return None
            today = _date.today()
            return round((today - b).days / 365.25, 1)

        # Build {org_abbr: {level: [player_records]}}. The MLB Stats API's
        # `abbreviation` uses 2-char codes for several teams (AZ, KC, SD,
        # SF, TB, CWS) while our prospect-ranking sources use 3-letter
        # canonical codes (ARI, KCR, SDP, SFG, TBR, CHW). Normalize via
        # canonical_org so the rosters keyed here line up with the codes
        # the front-end uses on the farm list / detail pages.
        _rosters_start = time.monotonic()
        from trades import canonical_org
        rosters_by_org: dict[str, dict[str, list[dict]]] = {}
        for rec in player_index.players:
            tid = rec.get("current_team_id")
            if not tid:
                continue
            info = team_affil.get(int(tid))
            if not info:
                continue
            org_abbr = canonical_org(info.get("parent_org_abbr") or "") or ""
            level = info.get("level") or ""
            if not org_abbr or not level:
                continue
            tracked = tracked_by_mid.get(int(rec["id"]))
            player_record = {
                "mlbam_id":   rec["id"],
                "fullName":   rec.get("fullName") or "",
                "position":   rec.get("position") or "",
                "age":        _age_from(rec.get("birthDate")),
                "team_name":  rec.get("current_team_name") or info.get("name"),
                "player_key": tracked["player_key"] if tracked else None,
                "fv_label":   tracked["fv_label"] if tracked else None,
                "fv_raw":     tracked["fv_raw"]   if tracked else None,
                # carried so efv_ungraded.flagship_owns can tell a published
                # grade from the constant placeholder that merely looks like one
                "fv_synthetic_only": bool(tracked and tracked.get("fv_synthetic_only")),
            }
            rosters_by_org.setdefault(org_abbr, {}).setdefault(level, []).append(player_record)

        # Within each level, sort tracked prospects (by FV desc) ahead of
        # un-graded org filler — that's the natural reading order on the page.
        for org, levels in rosters_by_org.items():
            for level, players in levels.items():
                players.sort(key=lambda r: (
                    -(r["fv_raw"] or -1),               # graded first, highest FV
                    r["fullName"].lower(),
                ))
        log.info("built rosters for %d orgs across %d affiliate levels",
                 len(rosters_by_org), len(set(
                     lvl for levels in rosters_by_org.values() for lvl in levels)))
        _STEP_TIMES.append(("2c-ii. Build rosters_by_org structure", time.monotonic() - _rosters_start))

        # eWAR nightly on the monthly path. The monthly reads WAR from step
        # 3d-bis (career WAR through war_source) on, and every one of those
        # readers (3d-bis, 4, 6, 6b..6b7b) runs before main() chains the daily,
        # so pricing the live season only at the daily's d8b would feed the
        # whole monthly yesterday's numerator. Same step, same guarantees
        # (_ewar_nightly_step); the chained daily skips its d8b.
        with _step("3-pre. eWAR live-season rebuild (ewar.json)", log):
            _ewar_nightly_step(log, "monthly")

        # --- 3a. Fetch career year-by-year stats.
        # Two-pass design:
        #   (1) BULK pass — one paginated call per (sport, group) hits the
        #       /stats?stats=season endpoint and returns every player's
        #       current-season line in 12 calls instead of ~3000 per-player
        #       yearByYear calls. We splice the resulting rows into the
        #       per-player career_cache so the rest of the pipeline (career
        #       table, statline derivation, auto-grad threshold) consumes
        #       them uniformly.
        #   (2) PER-PLAYER fallback — for players not in the bulk (no
        #       current-season stats: rookies, IFAs, injured, holdouts)
        #       OR with no other cached career rows (new to the tracker,
        #       needs prior-season backfill), still hit yearByYear.
        # Three filters further narrow the per-player set:
        #   - skip already-graduated prospects (their career is frozen)
        #   - skip prospects whose cached row is < CAREER_STATS_FRESH_DAYS old
        #     unless --force is set
        #   - skip prospects with no resolved MLBAM ID
        career_cache = load_career_stats()
        career_meta = load_career_stats_meta()
        statlines = load_statlines()
        non_grad_keys: set[str] = {p.player_key for p in timeseries
                                   if p.status != "debuted"}
        keys_with_bulk_2026: set[str] = set()
        _step_3a_bulk_start = time.monotonic() if not skip_stats else None
        if not skip_stats:
            # (1) Bulk pass — hitting + pitching across MLB + 5 MiLB levels.
            bulk_hitting  = bulk_fetch_season_stats(season, group="hitting")
            bulk_pitching = bulk_fetch_season_stats(season, group="pitching")
            # Merge: a two-way player can show in both endpoints; retain
            # every current-season row so multi-level / multi-org seasons
            # keep their per-level career-table detail.
            from stats import LEVEL_ORDER
            bulk_by_mlbam: dict[int, list[dict]] = {
                pid: (rows if isinstance(rows, list) else [rows])
                for pid, rows in bulk_hitting.items()
            }
            for pid, rows in bulk_pitching.items():
                incoming = rows if isinstance(rows, list) else [rows]
                bulk_by_mlbam.setdefault(pid, []).extend(incoming)
            for rows in bulk_by_mlbam.values():
                rows.sort(key=lambda r: (-int(r.get("season") or 0),
                                         LEVEL_ORDER.index(r["level"])))
            log.info("bulk season-stats: %d distinct players across hitting+pitching",
                     len(bulk_by_mlbam))

            # Splice bulk rows into career_cache (non-graduated only) and
            # persist. The fetched_at refresh inside upsert_career_stats
            # makes these players "fresh" for the next freshness check.
            bulk_updates = merge_bulk_into_career_cache(
                bulk_by_mlbam, career_cache, ids_by_key,
                season=season, eligible_keys=non_grad_keys,
            )
            if bulk_updates:
                upsert_career_stats(bulk_updates)
                keys_with_bulk_2026 = set(bulk_updates.keys())
            log.info("merged bulk season-stats into career_cache for %d players",
                     len(bulk_updates))
            _STEP_TIMES.append(("3a-i. Bulk season-stats fetch + merge", time.monotonic() - _step_3a_bulk_start))
        # --- 3a-ii. Game-data positional versatility (fielding) -----------
        # Per-position career games/starts from the StatsAPI fielding group ->
        # versa (positions with >=10 G or >=5 GS each). Position players only;
        # monthly cadence (per-player network fetch). Frontend loads the sidecar
        # and surfaces the game-data versa, preferring it over the FG-reported one.
        if not skip_stats:
            with _step("3a-ii. Positional versatility (fielding)", log):
                try:
                    # WS-R freshness gate (measured 437s, the single slowest
                    # step in the pipeline). versa is derived from SEASON-
                    # CUMULATIVE fielding games/starts that barely move day to
                    # day, and positions_played.json carries no per-entry
                    # timestamps, so gate the WHOLE artifact: skip the per-player
                    # StatsAPI fetch when it was regenerated within VERSA_FRESH_
                    # DAYS. --force (force_refetch) and an explicit EEPHUS_FULL=1
                    # owner rebuild override. Fail-open: a missing/corrupt
                    # artifact reads as stale via _artifact_fresh -> rebuilds.
                    _versa_path = out_dir / "positions_played.json"
                    _versa_forced = force_refetch or os.environ.get("EEPHUS_FULL") == "1"
                    if not _versa_forced and _artifact_fresh(_versa_path, VERSA_FRESH_DAYS):
                        _versa_age = _artifact_age_days(_versa_path)
                        log.info("3a-ii positional versatility: SKIP - %s regenerated "
                                 "%s ago (< %dd; --force / EEPHUS_FULL=1 override)",
                                 _versa_path.name,
                                 f"{_versa_age}d" if _versa_age is not None else "recently",
                                 VERSA_FRESH_DAYS)
                    else:
                        from fielding_positions import build_positions_played
                        versa_input = [
                            {"player_key": p.player_key,
                             "mlbam_id": ids_by_key.get(p.player_key),
                             "statline": {"is_pitcher": _is_pitcher(p.position)}}
                            for p in timeseries
                            if p.status != "debuted" and ids_by_key.get(p.player_key)
                        ]
                        # RUNTIME 2026-08-04: the builder now derives by_pos
                        # from the LEAGUE-WIDE season census (~154 cached
                        # (sportId, season) files folded to the board's id
                        # allowlist in ~0.7s of CPU) instead of one serial
                        # StatsAPI request per player with a 50ms sleep. Two
                        # guards keep it honest - players the census does not
                        # carry, and players it scores below their own
                        # previous career total, fall back to the per-player
                        # career endpoint through a 16-way pool. Set
                        # EEPHUS_VERSA_PER_PLAYER=1 to force the old route
                        # (still pooled). See fielding_positions for the
                        # measured coverage numbers.
                        build_positions_played(versa_input, log_=log,
                                               workers=min(16, workers or 16))
                except Exception:
                    log.exception("positions_played build failed — continuing")
        _step_3a_per_start = time.monotonic() if not skip_stats else None
        if not skip_stats:
            # STALENESS (needs-owner): _derive_all_level_changes() reads the
            # player_transactions DB table, which is NOT refreshed until step 3e
            # (upsert_player_transactions, further below). So the
            # current_year_level_change_keys computed here reflect the PREVIOUS
            # monthly run's transactions. A player promoted THIS cycle whose
            # promotion transaction is first fetched at 3e is therefore not
            # flagged, and if they are bulk-covered (in keys_with_bulk_2026)
            # with >1 cached career row they get skipped from the per-player
            # yearByYear refetch below. Impact is bounded and self-healing: the
            # bulk merge in 3a-i already spliced the new level's current-season
            # AGGREGATE row into career_cache, so only the finer yearByYear
            # per-stint / org-stint detail lags one monthly cycle. (The other
            # gate path this flag feeds - the _is_career_fresh skip at 2005-2009
            # - is inert on the ~30-day monthly cadence because
            # CAREER_STATS_FRESH_DAYS is 1: it only fires on a same-day
            # re-run, where the 24h HTTP cache would have returned the same
            # payload anyway.)
            # This same derivation (affil map + derive_level_changes) also runs
            # a second time at 3e over the FRESHLY fetched tx (see line ~2526),
            # so it executes twice per monthly run (warm-cache CPU only;
            # fetch_team_affiliations is 7-day disk-cached). The clean fix -
            # refresh transactions before this gate, then reuse ONE derivation
            # instead of recomputing at 3e - is a structural reorder (3e also
            # derives non-trade transactions and 3f roster-status depends on
            # it), so it is left for owner review rather than reordered blind.
            level_changes_for_stats = _derive_all_level_changes()
            current_year_level_change_keys = {
                key for key, evs in level_changes_for_stats.items()
                if any(str(ev.get("date") or "").startswith(str(season))
                       and ev.get("to_level") for ev in (evs or []))
            }
            non_grad_players = [
                (p.player_key, p.player_name, _is_pitcher(p.position))
                for p in timeseries if p.status != "debuted"
            ]
            graduated_repair_players = [
                (p.player_key, p.player_name, _is_pitcher(p.position))
                for p in timeseries
                if p.status == "debuted"
                and _career_rows_need_org_stint_backfill(career_cache.get(p.player_key))
            ]
            # A cached table missing a level line the league census records is
            # never skipped as bulk-covered or fresh: the bulk pass is the
            # qualified pool only and is what dropped the line (see
            # _career_missing_league_lines).
            _census_idx = _league_level_index(
                range(season - CENSUS_CHECK_SEASONS, season + 1))
            incomplete_keys = {
                key for key, _name, is_p in non_grad_players
                if _career_missing_league_lines(career_cache.get(key),
                                                ids_by_key.get(key), is_p,
                                                _census_idx)
            }
            log.info("career tables missing a league-census A to AAA line: %d "
                     "non-graduated players (re-fetched from yearByYear)",
                     len(incomplete_keys))
            cs_tasks: list[tuple[str, int, bool]] = []
            skipped_fresh = 0
            skipped_bulk = 0
            for key, _name, is_p in non_grad_players + graduated_repair_players:
                mlbam = ids_by_key.get(key)
                if mlbam is None:
                    continue
                # If the bulk pass updated this player AND they already had
                # at least one prior-season row cached, the per-player fetch
                # would just refresh data we already have — skip. Players
                # in the bulk WITHOUT prior-season rows fall through so
                # yearByYear can backfill the detail-page career history.
                has_current_year_level_change = key in current_year_level_change_keys
                missing_lines = key in incomplete_keys
                if (key in keys_with_bulk_2026
                        and not has_current_year_level_change
                        and not missing_lines
                        and len(career_cache.get(key, [])) > 1):
                    skipped_bulk += 1
                    continue
                if not force_refetch and _is_career_fresh(
                        career_meta.get(key), CAREER_STATS_FRESH_DAYS
                ) and not has_current_year_level_change and not missing_lines:
                    skipped_fresh += 1
                    continue
                cs_tasks.append((key, mlbam, is_p))
            log.info(
                "fetching career stats for %d players (%d graduated legacy-org "
                "repairs; skipped %d graduated, %d covered-by-bulk, "
                "%d fresh-cached, %d unresolved)",
                len(cs_tasks),
                len(graduated_repair_players),
                len(timeseries) - len(non_grad_players) - len(graduated_repair_players),
                skipped_bulk,
                skipped_fresh,
                len(non_grad_players) + len(graduated_repair_players)
                - skipped_bulk - skipped_fresh - len(cs_tasks),
            )
            new_career: dict = {}
            if cs_tasks:
                if workers is not None:
                    max_workers = max(1, min(workers, len(cs_tasks)))
                else:
                    # v25 — Bumped 16 → 24. MLB Stats API tolerates this
                    # comfortably; reduces wall time on the per-player
                    # career-stats fetch when freshness gates miss.
                    max_workers = min(24, max(1, len(cs_tasks)))
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                    future_to_key = {
                        ex.submit(fetch_career_stats, key, mlbam, is_pitcher=is_p): key
                        for key, mlbam, is_p in cs_tasks
                    }
                    for fut in concurrent.futures.as_completed(future_to_key):
                        key = future_to_key[fut]
                        try:
                            rows = fut.result()
                            if rows:
                                new_career[key] = rows
                        except Exception as e:
                            log.debug("career stats fetch failed for %s: %s", key, e)
            if new_career:
                upsert_career_stats(new_career)
                career_cache.update(new_career)
            log.info("fetched career stats for %d players", len(new_career))
            if _step_3a_per_start is not None:
                _STEP_TIMES.append(("3a-ii. Per-player career stats fetch (parallel)", time.monotonic() - _step_3a_per_start))

            # --- 3a-iii. Self-heal graduates frozen pre-org-feature ----------
            # Graduates are otherwise frozen (their MiLB career is over), but a
            # pre-feature freeze left their cached career_stats with NO `org`
            # key at all — so the detail-page career table couldn't attribute
            # per-season orgs (e.g. Cole Ragans's 2022 read as his current org
            # and his 2023 Texas->KC split was lost). Re-fetch only those
            # stale-shape graduates; once rebuilt with `org` (+ split stints)
            # they stop matching, so this is a bounded one-time catch-up that
            # respects the freeze. The active backfill is covered above.
            grad_heal = [
                (p.player_key, ids_by_key[p.player_key], _is_pitcher(p.position))
                for p in timeseries
                if p.status == "debuted"
                and ids_by_key.get(p.player_key)
                and (career_cache.get(p.player_key))
                and all("org" not in r for r in career_cache[p.player_key])
            ]
            if grad_heal:
                log.info("self-healing per-season org for %d graduates frozen "
                         "before the org/split-stints feature", len(grad_heal))
                healed: dict = {}
                heal_workers = min(24, max(1, len(grad_heal)))
                with concurrent.futures.ThreadPoolExecutor(max_workers=heal_workers) as ex:
                    heal_futs = {
                        ex.submit(fetch_career_stats, k, m, is_pitcher=ip): k
                        for k, m, ip in grad_heal
                    }
                    for fut in concurrent.futures.as_completed(heal_futs):
                        try:
                            rows = fut.result()
                            if rows:
                                healed[heal_futs[fut]] = rows
                        except Exception as e:
                            log.debug("graduate career heal failed for %s: %s",
                                      heal_futs[fut], e)
                if healed:
                    upsert_career_stats(healed)
                    career_cache.update(healed)
                log.info("healed per-season org for %d graduates", len(healed))

        # --- 3b. Derive current-season stat lines (top-level digest) ------
        # Skips already-graduated prospects since their graduation snapshot
        # already exists; the existing statlines row in the DB is preserved
        # for the export. The career_cache populated in step 3a already
        # contains every season's row per player, so we derive the
        # current-or-most-recent statline from it without firing another
        # HTTP call — even for the "no 2026 stats — using 2025" fallback
        # case which previously fired 4–8 per-player requests during the
        # year walkback.
        with _step("3b. Derive statlines from career cache", log):
            if not skip_stats:
                non_grad_for_statlines = [
                    (p.player_key, p.player_name, _is_pitcher(p.position))
                    for p in timeseries if p.status != "debuted"
                ]
                log.info("deriving stat lines for %d non-graduated prospects from career cache",
                         len(non_grad_for_statlines))
                new_statlines = derive_statlines_from_career(
                    non_grad_for_statlines, career_cache, season,
                    id_cache=ids_by_key,
                )
                stat_count = upsert_statlines(new_statlines, season)
                log.info("upserted %d stat lines", stat_count)
                for k, sl in new_statlines.items():
                    from dataclasses import asdict
                    statlines[k] = asdict(sl)
            else:
                new_statlines = {}

        # --- 3c. Single debut-detection pass. v21: every prospect whose
        # MLB API record carries an mlbDebutDate is moved to the Debuted
        # section. No rookie-threshold AB/IP gate — debut date is the
        # source of truth.
        with _step("3c. Auto-debut detection", log):
            active_for_debut = [
                (p.player_key, p.player_name, _is_pitcher(p.position))
                for p in timeseries if p.status != "debuted"
            ]
            debuts_found = detect_debuts_from_index(
                career_cache, active_for_debut,
                player_index=player_index,
                id_cache=ids_by_key,
                statlines=new_statlines or None,
            )
            if debuts_found:
                for pkey, debut_date in debuts_found.items():
                    auto_debut_player(pkey, debut_date=debut_date)
                log.info("auto-debuted %d players (mlbDebutDate on file)",
                         len(debuts_found))
                # Rebuild timeseries once so subsequent steps + export see the
                # correct statuses.
                all_snaps = load_all_snapshots()
                timeseries = build_timeseries(all_snaps, normalize=ADOPT_NORMALIZED_CONSENSUS)

        # --- 3d. Pitch arsenals (pitchers) + sabermetrics (everyone).
        # The MLB Stats API only carries this data for MLB seasons, so most
        # MiLB-only prospects return None. We still include GRADUATES here
        # because that's where the data actually exists — the prospect
        # detail page for a graduate gets wRC+/xFIP/arsenal from these
        # calls. --fast skips both for dev iteration.
        _step_3d_start = time.monotonic()
        arsenals = load_pitch_arsenals()
        zone_metric_cache = load_zone_metrics()
        statcast_metric_cache = load_statcast_metrics()
        sabermetrics = load_sabermetrics()
        if not skip_stats:
            if fast:
                log.info("--fast: skipping pitch arsenals + sabermetrics")
            else:
                # RUNTIME 2026-08-04 — MLB-ONLY FAN-OUT GATE.
                # Both endpoints below (pitch arsenal, sabermetrics) are
                # MLB-only: the comments right here have always said so, and
                # for a ~4,500-player, overwhelmingly-MiLB tracked population
                # that means most of ~6.5K requests per run return None BY
                # CONSTRUCTION. The has-MLB-career-row test the WAR cohort
                # already computes a few dozen lines below (`has_mlb`) is
                # exactly the right filter, so it is hoisted here and shared.
                #
                # SAFETY — this must never miss a FIRST MLB stint:
                #   * a player with NO career_cache row at all still fetches
                #     (an absent row means step 3a never landed for him, not
                #     that he has no MLB time);
                #   * so does anyone the board already calls debuted, or whose
                #     current statline level is MLB, which covers the case
                #     where 3a-i's bulk merge has the MLB row but the cached
                #     rows this dict was built from do not yet.
                # 3a-i splices the current season's MLB aggregate into
                # career_cache earlier in THIS run, and 3c's auto-debut pass
                # has already rebuilt the timeseries, so a debut that happened
                # since the last run is visible to all three tests.
                _mlb_fanout_keys: set[str] = set()
                for p in timeseries:
                    _rows = career_cache.get(p.player_key) or []
                    if (not _rows
                            or any(r.get("level") == "MLB" for r in _rows)
                            or p.status == "debuted"
                            or (statlines.get(p.player_key) or {}).get("level") == "MLB"):
                        _mlb_fanout_keys.add(p.player_key)

                pitchers = [(p.player_key, p.player_name)
                            for p in timeseries
                            if _is_pitcher(p.position)]
                all_active = [(p.player_key, p.player_name, _is_pitcher(p.position))
                              for p in timeseries]

                log.info("fetching pitch arsenals for %d pitchers", len(pitchers))
                new_arsenals: dict = {}
                pa_tasks: list[tuple[str, int]] = [
                    (key, ids_by_key[key]) for key, _name in pitchers
                    if key in ids_by_key and ids_by_key[key] is not None
                    and key in _mlb_fanout_keys
                ]
                log.info("pitch arsenal: %d of %d pitchers have MLB exposure "
                         "(or no career row yet); the rest are MiLB-only and the "
                         "endpoint would return None for them",
                         len(pa_tasks), len(pitchers))
                if pa_tasks:
                    if workers is not None:
                        max_workers = max(1, min(workers, len(pa_tasks)))
                    else:
                        # v25 — 10 → 16. Pitch-arsenal endpoint is light
                        # per-call; the prior cap left throughput on the table.
                        max_workers = min(16, max(1, len(pa_tasks)))
                    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                        future_to_key = {
                            ex.submit(fetch_pitch_arsenal, key, mlbam, season): key
                            for key, mlbam in pa_tasks
                        }
                        for fut in concurrent.futures.as_completed(future_to_key):
                            key = future_to_key[fut]
                            try:
                                pa = fut.result()
                                if pa:
                                    new_arsenals[key] = pa
                            except Exception as e:
                                log.debug("pitch arsenal fetch failed for %s: %s", key, e)
                if new_arsenals:
                    upsert_pitch_arsenals(new_arsenals, season)
                    for k, pa in new_arsenals.items():
                        from dataclasses import asdict
                        arsenals[k] = asdict(pa)
                log.info("fetched %d pitch arsenals", len(new_arsenals))

                # Sabermetrics (wRC+ / xFIP / wOBA / FIP / FIP- / ERA-).
                # The MLB Stats API sabermetrics endpoint only covers MLB
                # seasons, so for most tracked prospects this call returns
                # None. We still attempt it for everyone: graduates have
                # full MLB time, and any tracked prospect who's had even
                # a brief MLB cup-of-coffee will surface a value.
                new_sabermetrics: dict = {}
                sm_tasks: list[tuple[str, int, bool]] = [
                    (key, ids_by_key[key], is_p) for key, _name, is_p in all_active
                    if key in ids_by_key and ids_by_key[key] is not None
                    and key in _mlb_fanout_keys        # see the fan-out gate above
                ]
                log.info("fetching sabermetrics (wRC+/xFIP) for %d of %d tracked "
                         "players (MLB-only endpoint; MiLB-only players skipped)",
                         len(sm_tasks), len(all_active))
                if sm_tasks:
                    if workers is not None:
                        max_workers = max(1, min(workers, len(sm_tasks)))
                    else:
                        # v25 — 16 → 24. Matches the career-stats cap;
                        # sabermetrics endpoint has similar per-call cost.
                        max_workers = min(24, max(1, len(sm_tasks)))
                    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                        future_to_key = {
                            ex.submit(fetch_sabermetrics, key, mlbam, season, is_pitcher=is_p): key
                            for key, mlbam, is_p in sm_tasks
                        }
                        for fut in concurrent.futures.as_completed(future_to_key):
                            key = future_to_key[fut]
                            try:
                                sm = fut.result()
                                if sm:
                                    new_sabermetrics[key] = sm
                            except Exception as e:
                                log.debug("sabermetrics fetch failed for %s: %s", key, e)
                if new_sabermetrics:
                    upsert_sabermetrics(new_sabermetrics, season)
                    for k, sm in new_sabermetrics.items():
                        from dataclasses import asdict
                        sabermetrics[k] = asdict(sm)
                log.info("fetched sabermetrics for %d players", len(new_sabermetrics))

                # --- 3d-bis. Career WAR for anyone who has touched MLB.
                # Uses pybaseball.bwar_bat / bwar_pitch - the two static
                # BASEBALL-REFERENCE war_daily tables - in one bulk pull.
                # This comment used to describe a FanGraphs batting_stats /
                # pitching_stats pull; FG 403s pybaseball's endpoint, so the
                # site moved to bWAR and the comment did not follow
                # (corrected 2026-08-03). The MLB Stats API only exposes WAR
                # via single-season sabermetrics calls, so a per-player loop
                # would cost ~2-4k extra requests on a cold cache.
                # Cohort = every tracked player whose career_stats carries
                # at least one MLB row (covers active cup-of-coffee call-
                # ups, graduates, and reclassified inactives in one pass).
                war_cohort: list[tuple[str, int, bool]] = []
                # career_cache is kept in-sync with the DB via the
                # career_cache.update(new_career) call earlier in this
                # block, so we can reuse it here without re-reading.
                _cs_now = career_cache
                for p in timeseries:
                    mid = ids_by_key.get(p.player_key)
                    if not mid:
                        continue
                    rows = _cs_now.get(p.player_key, []) or []
                    has_mlb = any(r.get("level") == "MLB" for r in rows)
                    if not has_mlb:
                        continue
                    is_p = bool((rows[0].get("is_pitcher") if rows else False))
                    war_cohort.append((p.player_key, mid, is_p))
                if war_cohort:
                    war_meta = load_career_war_meta()
                    if force_refetch:
                        war_targets = war_cohort
                    else:
                        war_targets = [
                            t for t in war_cohort
                            if not _is_career_fresh(war_meta.get(t[0]), CAREER_STATS_FRESH_DAYS)
                        ]
                    log.info("fetching career WAR for %d players "
                             "(skipped %d fresh-cached)",
                             len(war_targets),
                             len(war_cohort) - len(war_targets))
                    if war_targets:
                        # AUDIT FIX 2026-07-14: the window is FLOORED at 2011
                        # (the earliest eFV training debut cohort). The old
                        # sliding start_year=season-10 silently DELETED
                        # early-career seasons from stored payloads on every
                        # refetch (Correa's 2015 ROY season vanished in the
                        # 2026 refetch), and the label builder counted the
                        # missing years as 0 WAR - progressive label decay.
                        try:
                            # eWAR epoch (2026-09-03): the funnel goes through
                            # the war_source facade on its DEFAULT provider, so
                            # the payload the table stores is whatever the site
                            # serves (eWAR v2 once the provider lands; bWAR
                            # payloads until then, merged as before). Never pass
                            # provider= here: the default IS the served basis.
                            import war_source
                            war_data = war_source.career_war_bulk(
                                war_targets,
                                start_year=min(season - 10, 2011),
                                end_year=season,
                            )
                            if war_data:
                                upsert_career_war(war_data)
                                log.info("cached career WAR for %d players",
                                         len(war_data))
                        except Exception as e:
                            log.warning("career WAR fetch failed: %s", e)
        _STEP_TIMES.append(("3d. Arsenals + sabermetrics + career WAR", time.monotonic() - _step_3d_start))

        _step_3d_bis_start = time.monotonic()
        # --- 3d-bis. Approximate zone metrics for MiLB hitters.
        # Train once on MLB Gameday x/y + official zone labels, then apply
        # the classifier to tracked hitters at AAA/AA/A+/A. We run the same
        # MLB Stats API methodology at every supported level, including AAA
        # and Carolina League, so the site has one internally consistent
        # source instead of mixing in Prospect Savant exports.
        if not skip_stats:
            if fast:
                log.info("--fast: skipping approximate MiLB zone metrics")
            else:
                # v19 — Freshness gate. If a meaningful fraction of the
                # active player pool already has a recent zone-metric
                # row (within ZONE_METRICS_FRESH_DAYS), skip the whole
                # step. Avoids a ~2-3 minute rebuild on weekly re-runs
                # when nothing material has changed. --force overrides.
                #
                # Eligibility set MUST mirror what the fetcher actually
                # processes — hitters and pitchers at tracked levels. A
                # hitter-only gate can skip the whole refresh while pitcher
                # splits are stale, e.g. an MLB-debut arm with a stored MLB
                # zone row but newly available AAA tape.
                _zone_tracked_levels = {"MLB", "AAA", "AA", "A+", "A", "CPX"}
                _zone_meta = load_zone_metrics_meta()
                _zone_eligible_keys = [
                    p.player_key for p in timeseries
                    if ids_by_key.get(p.player_key) is not None
                       and (statlines.get(p.player_key) or {}).get("level") in _zone_tracked_levels
                ]
                _zone_metric_cache = load_zone_metrics()
                def _zone_has_statcast_levels(player_key: str) -> bool:
                    """Rows missing known Statcast split levels are stale."""
                    zm = _zone_metric_cache.get(player_key) or {}
                    sc = statcast_metric_cache.get(player_key) or {}
                    sc_levels = {
                        row.get("level")
                        for row in (sc.get("level_splits") or [])
                        if isinstance(row, dict) and row.get("level") in _zone_tracked_levels
                    }
                    if not sc_levels:
                        return True
                    zone_levels = {
                        row.get("level")
                        for row in (zm.get("level_splits") or [])
                        if isinstance(row, dict) and row.get("level") in _zone_tracked_levels
                    }
                    if not zone_levels and zm.get("level") in _zone_tracked_levels:
                        zone_levels.add(zm.get("level"))
                    return sc_levels.issubset(zone_levels)
                _zone_fresh_count = sum(
                    1 for k in _zone_eligible_keys
                    if _is_career_fresh(_zone_meta.get(k), ZONE_METRICS_FRESH_DAYS)
                    and _zone_has_statcast_levels(k)
                )
                _zone_fresh_pct = (_zone_fresh_count / max(1, len(_zone_eligible_keys))) * 100
                _zone_should_skip = (
                    not force_refetch
                    and _zone_eligible_keys
                    and _zone_fresh_pct >= 90
                )
                if _zone_should_skip:
                    log.info("zone metrics: SKIP (%d/%d eligible players fresh within %dd, %.0f%%)",
                             _zone_fresh_count, len(_zone_eligible_keys),
                             ZONE_METRICS_FRESH_DAYS, _zone_fresh_pct)
                else:
                    try:
                        from zone_metrics import fetch_zone_metrics_for_players
                        zone_players = []
                        for p in timeseries:
                            sl = statlines.get(p.player_key) or {}
                            zone_players.append((
                                p.player_key,
                                p.player_name,
                                ids_by_key.get(p.player_key),
                                sl.get("level"),
                                bool(sl.get("is_pitcher")) or _is_pitcher(p.position),
                            ))
                        new_zone_metrics = fetch_zone_metrics_for_players(
                            zone_players,
                            season,
                            train_games=30,
                            train_start_date=f"{season}-05-15",
                        )
                        if new_zone_metrics:
                            upsert_zone_metrics(new_zone_metrics, season)
                            from dataclasses import asdict
                            zone_metric_cache.update({
                                key: asdict(value)
                                for key, value in new_zone_metrics.items()
                            })
                        log.info("fetched approximate zone metrics for %d players",
                                 len(new_zone_metrics))
                    except Exception:
                        log.exception("approximate zone metrics failed — continuing")
        _STEP_TIMES.append(("3d-bis. Approximate zone metrics", time.monotonic() - _step_3d_bis_start))

        _step_3d_ter_start = time.monotonic()
        # --- 3d-ter. Statcast-style pitch movement + contact quality.
        # Coverage is park/feed dependent. The fetcher emits rows only when
        # game feeds expose actual movement or launch-speed fields, which
        # covers AAA and some lower-level parks such as spring-training
        # complex venues.
        if not skip_stats:
            if fast:
                log.info("--fast: skipping Statcast-style pitch/contact metrics")
            else:
                # v19 — Freshness gate. Same logic as zone metrics —
                # the per-player game-feed fetch loop runs 10+ minutes
                # on cold cache, so skip the whole step when 90%+ of
                # the tracked pool already has a fresh row. Eligibility
                # mirrors the fetcher: TRACKED_LEVELS now includes MLB
                # (v20) so debuted players who have both AAA + MLB tape
                # get level_splits for both.
                _sc_tracked_levels = {"MLB", "AAA", "AA", "A+", "A", "CPX"}
                _sc_meta = load_statcast_metrics_meta()
                _sc_eligible_keys = [
                    p.player_key for p in timeseries
                    if ids_by_key.get(p.player_key) is not None
                       and (statlines.get(p.player_key) or {}).get("level") in _sc_tracked_levels
                ]
                _sc_fresh_count = sum(
                    1 for k in _sc_eligible_keys
                    if _is_career_fresh(_sc_meta.get(k), STATCAST_METRICS_FRESH_DAYS)
                )
                _sc_fresh_pct = (_sc_fresh_count / max(1, len(_sc_eligible_keys))) * 100
                _sc_should_skip = (
                    not force_refetch
                    and _sc_eligible_keys
                    and _sc_fresh_pct >= 90
                )
                if _sc_should_skip:
                    log.info("statcast metrics: SKIP (%d/%d eligible players fresh within %dd, %.0f%%)",
                             _sc_fresh_count, len(_sc_eligible_keys),
                             STATCAST_METRICS_FRESH_DAYS, _sc_fresh_pct)
                else:
                    try:
                        from statcast_metrics import (
                            METRIC_SCHEMA_VERSION as _SC_SCHEMA,
                            fetch_statcast_metrics_for_players,
                        )
                        statcast_players = []
                        for p in timeseries:
                            sl = statlines.get(p.player_key) or {}
                            statcast_players.append((
                                p.player_key,
                                p.player_name,
                                ids_by_key.get(p.player_key),
                                sl.get("level"),
                                bool(sl.get("is_pitcher")) or _is_pitcher(p.position),
                            ))
                        # RUNTIME 2026-08-04 — INCREMENTAL 3d-ter.
                        # The monthly pass rebuilt every tracked player from
                        # scratch every run: thousands of /feed/live blobs in
                        # pass 2 and a full CPU-bound process-pool sweep in
                        # pass 3, for players who had not played a tracked
                        # game since the last run. The daily path has skipped
                        # those since WS-R via _statcast_logs_newer_than_metric;
                        # this hands the monthly path the same filter, applied
                        # AFTER pass 1's game-log scan proves a player has no
                        # newer game.
                        #
                        # SAFETY - this is a skip gate, so it can silently
                        # freeze rows. Three things force a full rebuild:
                        #   * --force (force_refetch) or EEPHUS_FULL=1;
                        #   * no stored row for that player;
                        #   * a stored payload whose schema_version differs
                        #     from statcast_metrics.METRIC_SCHEMA_VERSION.
                        # The stamp is the load-bearing one: it is what stops
                        # a future change to the payload shape from leaving
                        # skipped players on the old shape with nothing
                        # raising - the exact failure mode of the 2026-08-03
                        # standout/recent-games defect. Rows written before
                        # the stamp existed carry none, so the first run after
                        # this ships rebuilds everything and only later runs
                        # are incremental.
                        _sc_full = (force_refetch
                                    or os.environ.get("EEPHUS_FULL") == "1")
                        _sc_incremental: dict[str, str] = {}
                        if not _sc_full:
                            for _k, _payload in (statcast_metric_cache or {}).items():
                                if not isinstance(_payload, dict):
                                    continue
                                if _payload.get("schema_version") != _SC_SCHEMA:
                                    continue          # stale shape -> rebuild
                                _d = _latest_statcast_metric_game_date(_payload)
                                if _d:
                                    _sc_incremental[_k] = _d
                            log.info("3d-ter incremental: %d/%d stored rows are "
                                     "current-schema and datable (the rest rebuild)",
                                     len(_sc_incremental), len(statcast_metric_cache or {}))
                        else:
                            log.info("3d-ter incremental: DISABLED (%s) - "
                                     "rebuilding every row",
                                     "--force" if force_refetch else "EEPHUS_FULL=1")
                        new_statcast_metrics = fetch_statcast_metrics_for_players(
                            statcast_players,
                            season,
                            # v25 — 10 → 16. Statcast is the longest-running
                            # step in a cold full run (~56s); more workers
                            # cuts it materially.
                            workers=workers or 16,
                            skip_if_not_newer_than=_sc_incremental or None,
                        )
                        if new_statcast_metrics:
                            upsert_statcast_metrics(new_statcast_metrics, season)
                            from dataclasses import asdict
                            statcast_metric_cache.update({
                                key: asdict(value)
                                for key, value in new_statcast_metrics.items()
                            })
                        log.info("fetched Statcast-style metrics for %d players",
                                 len(new_statcast_metrics))
                    except Exception:
                        log.exception("Statcast-style metrics failed — continuing")
        _STEP_TIMES.append(("3d-ter. Statcast pitch movement / contact quality", time.monotonic() - _step_3d_ter_start))

        _step_3e_start = time.monotonic()
        # --- 3e. Per-player transactions cache + within-season level changes.
        # The /transactions?playerId=X endpoint returns every affiliate
        # assignment, contract selection, recall, etc. for one player —
        # the source of truth for promotion/demotion markers and the
        # options / debut / service-time heuristics. One HTTP call per
        # player; cached for TRANSACTIONS_FRESH_DAYS so dev iterations
        # reuse the prior payload.
        tx_cache = load_player_transactions()
        tx_meta = load_player_transactions_meta()
        if not skip_stats:
            # All players (incl. graduates) — graduates are the ones with
            # MLB debut + options data worth tracking, and their cache is
            # stable so the TTL skip keeps subsequent runs cheap.
            all_for_tx = [
                (p.player_key, ids_by_key.get(p.player_key))
                for p in timeseries
            ]
            tx_tasks = [
                (key, mlbam) for key, mlbam in all_for_tx
                if mlbam is not None and (
                    force_refetch or not _is_career_fresh(
                        tx_meta.get(key), CAREER_STATS_FRESH_DAYS)
                )
            ]
            log.info("fetching player transactions for %d players "
                     "(skipped %d fresh-cached / unresolved)",
                     len(tx_tasks),
                     len(all_for_tx) - len(tx_tasks))
            if tx_tasks:
                # v25 — 16 → 24. The /transactions endpoint is also light
                # and parallelizes well.
                max_w = (max(1, min(workers, len(tx_tasks)))
                         if workers is not None
                         else min(24, max(1, len(tx_tasks))))
                new_tx = bulk_fetch_player_transactions(tx_tasks, max_workers=max_w)
                if new_tx:
                    upsert_player_transactions(new_tx)
                    tx_cache.update(new_tx)
                log.info("fetched transactions for %d players", len(new_tx))

        # Compute level_changes + non-trade transactions per player from
        # the cached transactions. Both are pure CPU passes over the
        # already-cached payload — no extra HTTP.
        #
        # `level_changes` covers promotions/demotions (the FV-chart line
        # changes); `transactions` covers everything else worth showing
        # on the timeline (waiver claims, releases, DFAs, contract
        # purchases, Rule 5 moves, free-agent signings). Trades stay in
        # their own `trades` table — they have stricter cross-org dedup
        # logic and an inferred-from-snapshots fallback for prospect-only
        # deals the global API endpoint hasn't published yet.
        from stats import derive_transactions
        level_changes_by_key: dict[str, list[dict]] = {}
        transactions_by_key:  dict[str, list[dict]] = {}
        # v25 — Plain loop. The prior ThreadPoolExecutor wrapper hurt
        # this step: both derive_* helpers are pure CPU (dict + list
        # work, no I/O), and Python's GIL serializes thread execution
        # anyway. Removing the pool eliminates the per-task submit /
        # collect overhead and the worker startup cost.
        affil_by_year = _affil_by_year_for_transactions(tx_cache, log)
        for key, tx_rows in tx_cache.items():
            evs = derive_level_changes(tx_rows, affil_by_year)
            txs = derive_transactions(tx_rows)
            if evs:
                level_changes_by_key[key] = evs
            if txs:
                transactions_by_key[key] = txs
        log.info("derived level_changes for %d players, "
                 "non-trade transactions for %d players",
                 len(level_changes_by_key), len(transactions_by_key))
        _STEP_TIMES.append(("3e. Transactions cache + level changes", time.monotonic() - _step_3e_start))

        _step_3f_start = time.monotonic()
        # --- 3f. MLB roster-status derivation (debut, 40-man, options,
        # service phase). Combines the transactions cache with career_stats
        # rows we already loaded for the stat-line derivation. Pure CPU
        # pass — every player gets a row, even those with no MLB activity,
        # so downstream the front-end can render `Pre-MLB` vs `Pre-arb` vs
        # `Arb eligible` consistently.
        roster_status_by_key: dict[str, dict] = {}
        for p in timeseries:
            tx_rows = tx_cache.get(p.player_key, [])
            cs_rows = career_cache.get(p.player_key, [])
            # PlayerIndex carries the MLB Stats API's authoritative
            # mlbDebutDate — first actual MLB game, not first 40-man add.
            # Pass it in so derive_roster_status doesn't surface a Rule 5
            # protection date as the prospect's debut.
            mid = ids_by_key.get(p.player_key)
            api_debut = player_index.get_debut_date(mid) if mid else None
            rs = derive_roster_status(tx_rows, cs_rows, api_debut_date=api_debut)
            roster_status_by_key[p.player_key] = rs
        # Backfill mlb_debut_date for players who have MLB career rows
        # OR are already marked graduated but for whom PlayerIndex has no
        # mlbDebutDate (typically older graduates outside the current
        # season's roster pool, and international free agents who never
        # had a MiLB stint). Hits /people/{id} once per missing id; the
        # value gets written into the in-memory roster_status_by_key for
        # this run and persisted via upsert below.
        debut_backfill_ids: list[int] = []
        debut_backfill_keys_by_id: dict[int, str] = {}
        for p in timeseries:
            rs = roster_status_by_key.get(p.player_key) or {}
            # DS-12 (bug B7): a date that is only the first contract selection
            # and falls in the offseason (a Rule 5 protection add) is not a game
            # date. storage rolls it forward to a {year}-07-01 placeholder, which
            # the eFV matrix then reads as the debut day. Ask /people/{id} first.
            _d = rs.get("mlb_debut_date") or ""
            _offseason_selection = (rs.get("mlb_debut_date_source") == "selection"
                                    and _d[5:7] in ("11", "12", "01", "02"))
            if rs.get("mlb_debut_date") and not _offseason_selection:
                continue
            mid = ids_by_key.get(p.player_key)
            if not mid:
                continue
            needs_lookup = (
                p.status == "debuted"
                or (rs.get("career_mlb_ab", 0) or 0) > 0
                or (rs.get("career_mlb_ip", 0) or 0) > 0
                or bool(rs.get("mlb_seasons"))
            )
            if needs_lookup:
                debut_backfill_ids.append(int(mid))
                debut_backfill_keys_by_id[int(mid)] = p.player_key
        if debut_backfill_ids:
            log.info("backfilling mlb_debut_date for %d players missing one",
                     len(debut_backfill_ids))
            debut_map = bulk_fetch_mlb_debut_dates(debut_backfill_ids)
            for mid, debut in debut_map.items():
                key = debut_backfill_keys_by_id.get(mid)
                if key:
                    rs = roster_status_by_key.setdefault(key, {})
                    rs["mlb_debut_date"] = debut
                    rs["mlb_debut_date_source"] = "api_people"

        if roster_status_by_key:
            upsert_roster_status(roster_status_by_key)
        rookie_exhausted_grads = {
            k: v.get("mlb_debut_date")
            for k, v in roster_status_by_key.items()
            if v.get("rookie_exhausted")
        }
        log.info("roster_status derived for %d players "
                 "(%d on 40-man, %d rookie-exhausted)",
                 len(roster_status_by_key),
                 sum(1 for v in roster_status_by_key.values() if v.get("on_40_man")),
                 len(rookie_exhausted_grads))

        # v21 — Rookie-threshold revalidation removed. Debut-date is the
        # sole gate now (per `detect_debuts_from_index` in step 3c); a
        # player's auto_detect row stays as long as MLB API has an
        # mlbDebutDate on file for them. The previous belt-and-
        # suspenders rookie-exhaustion auto-graduate pass is also gone —
        # `detect_debuts_from_index` already catches everyone the
        # rookie-threshold pass would have caught (and more).
        _STEP_TIMES.append(("3f-g. Roster status + rookie-exhaustion compute", time.monotonic() - _step_3f_start))

        # Trade detection. The org-change inference always runs (just walks
        # snapshots we already have); the MLB API path is skipped under
        # --skip-stats. tracked_players is built directly from ids_by_key,
        # avoiding the per-player resolve_mlbam_id loop the previous version
        # ran here.
        with _step("4. Trade detection", log):
            tracked = {}
            if not skip_stats:
                for p in timeseries:
                    tracked[p.player_key] = (p.player_name, ids_by_key.get(p.player_key))
            new_trades = detect_trades(all_snaps, tracked_players=tracked,
                                        skip_api=skip_stats)
            trade_count = insert_trades(new_trades)
            log.info("detected %d trades (%d new)", len(new_trades), trade_count)
            trades_by_player = load_trades()

            # v31.8 — Resolve MLB veterans named in trade descriptions
            # who aren't in our tracked-prospect database (e.g. Brendan
            # Donovan going to SEA for a prospect package). Fetches
            # career WAR + position from MLB Stats API + BBRef; cached
            # in mlb_trade_players for the frontend trade-audit UI.
            # v31.8c — Pipeline-safe defaults: max_new=50 + 90s budget,
            # so first runs chip through the backlog incrementally
            # instead of stalling on a 600+ name first-resolve. The
            # BBRef WAR download is timeout-wrapped to 30s so a slow
            # mirror can't hang the whole pipeline either.
            try:
                from mlb_trade_lookup import refresh_mlb_trade_players
                refresh_mlb_trade_players(force=force_refetch,
                                           workers=4,
                                           max_new=50,
                                           time_budget_seconds=90.0)
            except Exception:
                log.exception("MLB trade-player lookup crashed — continuing")

            # Career WAR — loaded once here and reused by the JSON export.
            career_war_all = load_career_war()

        # --- 5. Export -------------------------------------------------
        _step_5_start = time.monotonic()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "timeseries.json"
        export_timeseries_json(timeseries, out_path,
                               statlines=statlines,
                               pitch_arsenals=arsenals,
                               zone_metrics=zone_metric_cache,
                               statcast_metrics=statcast_metric_cache,
                               sabermetrics=sabermetrics,
                               trades_by_player=trades_by_player,
                               transactions_by_player=transactions_by_key,
                               career_stats=career_cache,
                               career_war=career_war_all,
                               acquisitions=load_acquisitions(),
                               il_status=load_il_status(),
                               rosters_by_org=rosters_by_org,
                               level_changes=level_changes_by_key,
                               roster_status=roster_status_by_key,
                               ifa_spending_by_org=ifa_spending_by_org,
                               contracts_by_key=contracts_by_key,
                               draft_pools=draft_pools,
                               player_ids=ids_by_key,
                               # v47 - mid-monthly export: main() ALWAYS
                               # chains run_daily(chained=True), whose d9
                               # rebuild_only re-runs the FULL export ~15
                               # min from here; nothing in the monthly
                               # tail reads the frontend-only sidecars, so
                               # this pass writes only boot + debuts.json
                               # + rosters_by_org.json (~1GB of sidecar
                               # duplication skipped). NEVER set this on
                               # the daily / d9 / rebuild paths.
                               intermediate=True)
        log.info("wrote %s", out_path)
        _post_export_summary(out_path, all_snaps, log)
        # International Amateurs sidecar — IFA signing classes from the
        # cached Spotrac tracker, enriched against the just-written
        # timeseries.json. Best-effort; never aborts the run.
        try:
            from ifa_export import export_ifa_json
            n_ifa = export_ifa_json(out_dir / "ifa_timeseries.json")
            log.info("ifa pipeline: exported %d signings", n_ifa)
        except Exception:
            log.exception("ifa export crashed — continuing")
        # Merged-identity report. See the rebuild_only copy of this block
        # for the full rationale; detection only, no DB writes, no re-keying.
        try:
            from identity_audit import build as _build_identity_audit
            _ident = _build_identity_audit(
                path=out_dir / "identity_collisions.json")
            log.info("identity audit: %d critical keys (%d active), "
                     "%d frankenstein records",
                     _ident["summary"]["critical_player_keys"],
                     _ident["summary"]["critical_active_player_keys"],
                     _ident["summary"]["frankenstein_records"])
        except Exception:
            log.exception("identity audit crashed — continuing")
        _STEP_TIMES.append(("5. Export timeseries.json + summary", time.monotonic() - _step_5_start))

        # OOM: free the monthly whole-universe caches HERE, right after the
        # step-5 export consumed them, instead of waiting for the pre-daily-chain
        # block far below. Steps 6-6b6 (FA refresh/export, Swing+, AAA Stuff+,
        # the six /mlbstats/ leaderboards, PAL, and especially fantasy
        # build_corpus) all re-load what they need from disk/DB and never read
        # these locals, so holding ~11 whole-universe dicts (all_snaps + the
        # career/statline/Statcast/zone/arsenal/sabermetric/tx/trades/career-WAR
        # caches + draft_by_id) atop the fantasy corpus is dead weight through
        # the heaviest monthly phase. The ONLY post-export reads are len() of
        # timeseries + new_trades in the finish_run note below, so stash the one
        # count and keep new_trades (small) live. all_snaps was last read by
        # _post_export_summary just above.
        _n_ts = len(timeseries)
        # Source coverage for tonight's metric_snapshots rows (owner answer
        # B4SP-2, 2026-10-01): outlet count and best league-wide rank off each
        # player's latest consensus point, kept as one small dict because the
        # build itself is freed below and the snapshot is taken after step 6.
        try:
            from consensus import source_coverage_by_player as _src_cov_by_player
            _source_cov = _src_cov_by_player(timeseries)
        except Exception:
            log.exception("source coverage for metric_snapshots failed, recording none tonight")
            _source_cov = None
        import gc as _gc
        all_snaps = timeseries = career_cache = statlines = statcast_metric_cache = \
            zone_metric_cache = arsenals = sabermetrics = tx_cache = draft_by_id = \
            trades_by_player = career_war_all = None
        _gc.collect()

        # --- 6. Free Agency module (the standalone /fa/ surface) --------
        # Refresh the constructed class (Spotrac, page-cached) + payroll
        # ledger, then re-export the fa_* sidecars assets/fa.js consumes.
        # Best-effort: the FA module is additive by contract and must
        # never abort the prospect pipeline.
        with _step("6. FA refresh + export (fa_* sidecars)", log):
            try:
                import fa_pipeline
                from fa_export import CLASS_YEAR as _FA_CLASS_YEAR
                from fa_export import FUTURE_CLASS_YEARS as _FA_FUTURE
                from fa_export import export_all as _export_fa
                fa_pipeline.refresh_current_class(_FA_CLASS_YEAR,
                                                  force=force_refetch)
                # Future winters (year selector on the board) - the same
                # constructed-class pipeline per Spotrac forward page;
                # best-effort, the current class never waits on them.
                for _fy in _FA_FUTURE:
                    try:
                        fa_pipeline.refresh_current_class(_fy,
                                                          force=force_refetch)
                    except Exception:
                        log.exception("fa future class %d failed — continuing", _fy)
                fa_pipeline.refresh_payroll(force=force_refetch)
                _export_fa()
            except Exception:
                log.exception("fa pipeline failed — continuing")

        # --- 6b. MLB Projections module (the /projections/ surface) -----
        # The FA engine over the whole league + post-ETA prospects. Reads
        # the corpus cache, Spotrac contract pages (cached) and the
        # just-written timeseries.json. Additive; never aborts the run.
        with _step("6b. MLB projections export (mlb_projections.json)", log):
            # WS-R merge (2026-07-14): main() always chains run_daily, which
            # re-runs proj_export AFTER the eFV regen - the export here was
            # overwritten ~15 min later every monthly night (and, being pre-regen,
            # was the STALER of the two). Skipped as duplication; standalone
            # --daily and standalone --rebuild-only both get the re-bake.
            #
            # STILL CORRECT after the 2026-08-07 write-order fix, and now for a
            # second reason: the re-bake moved OUT of daily step d9b and INTO
            # rebuild_only, where it lands between the eFV regen and the
            # trade-value export. Exporting here as well would put a pre-regen
            # mlb_projections.json on disk for the ~15 minutes before the chain
            # reaches d9, which is precisely the window in which anything pricing
            # off that file (bayes_trade_value.apply_platform_surplus) would read
            # the stale copy. Leaving it skipped keeps ONE writer per night.
            log.info("6b SKIP: chained d9 rebuild_only re-exports mlb_projections "
                     "post-regen, ahead of the trade-value export")

        # --- 6b2. Swing+ scoring (Will Cahoon's model, vendored) ---------
        # Per-player MLB bat-tracking pulls (cached; closed seasons
        # immutable, current season on a short TTL) scored to
        # data/swing_plus.json. MLB-only by data boundary. Best-effort.
        with _step("6b2. Swing+ scoring (swing_plus.json)", log):
            try:
                from swing_plus_ingest import run as _swing_run
                _sw = _swing_run()
                log.info("swing+: %d hitters scored", _sw.get("n_scored", 0))
            except Exception:
                log.exception("swing+ scoring failed — continuing")

        # --- 6b2a. Savant minors batter refresh (PROSPX Statcast (tracked parks) card)
        # Owner answer M25-3 (2026-09-25): refetch the current season's Savant
        # minors batter aggregates monthly and rebake the card sidecar. Gated to
        # the AAA regular season plus ONE final pull after it ends; one request,
        # cached; a failed or malformed fetch keeps the last good CSV and files
        # ok=False under savant_aaa_batters. The refresh lands in
        # .cache/savant_minors_live/, which only this card reads: the model
        # cache that S-XLINE eFV and the SC+ re-source read stays as it is
        # until the fWAR epoch's step M (see statcast_aaa_hitters.py).
        with _step("6b2a. Savant minors batter refresh, tracked parks (statcast_aaa_hitters.json)", log):
            try:
                from statcast_aaa_hitters import refresh as _aaa_bat_refresh
                _ab = _aaa_bat_refresh()
                _record_ingest("savant_aaa_batters", bool(_ab.get("ok")),
                               int(_ab.get("n_hitters") or 0),
                               str(_ab.get("message") or "")[:200], log=log)
            except Exception as _e:
                log.exception("savant minors batter refresh failed - continuing")
                _record_ingest("savant_aaa_batters", False, 0,
                               f"crashed: {_e}"[:200], log=log)

        # --- 6b2b. AAA Stuff+ re-score (in-house pitch-quality model) ----
        # Incremental current-season pitch fetch (closed seasons immutable
        # in cache, current season on a 14-day TTL) + re-score against the
        # committed model artifact. Never retrains here - the shipping fit
        # is hand-run with its season-out eval. Best-effort.
        with _step("6b2b. AAA Stuff+ re-score (stuff_plus_aaa.json)", log):
            try:
                from stuff_plus_aaa import refresh as _aaa_stuff_refresh
                _st = _aaa_stuff_refresh()
                log.info("aaa stuff+: %d pitchers scored", _st.get("n_scored", 0))
            except Exception:
                log.exception("aaa stuff+ re-score failed — continuing")

        # --- 6b2c. Modern-signal retention (EV-03) -----------------------
        # The DB signal tables (statcast_metrics, zone_metrics, pitch_arsenals,
        # sabermetrics, statlines) hold one season and the aStuff+ sidecar keeps
        # the latest season per player, so a season's as-of record survives only
        # if someone copies it. tools/snapshot_modern_signals.py writes
        # data/signal_snapshots/<season>/ (tracked, NOT served): an earlier
        # season is written once and frozen, the live season merges by key and
        # never drops a row. Runs after 6b2/6b2b so Swing+ and aStuff+ are fresh.
        # Offline (no fetch). Heartbeat `signal_snapshots`. Never aborts.
        with _step("6b2c. Modern-signal snapshots (data/signal_snapshots/)", log):
            try:
                from tools import snapshot_modern_signals as _sms
                import job_heartbeat as _hb
                _sn = _sms.snapshot()
                _hb.record("signal_snapshots", ok=True,
                           result=_sms.summary_line(_sn)[:120])
                log.info("signal snapshots: %s", _sms.summary_line(_sn))
            except Exception as _e:
                log.exception("signal snapshots failed - continuing")
                try:
                    import job_heartbeat as _hb
                    _hb.record("signal_snapshots", ok=False, result=str(_e)[:120])
                except Exception:
                    pass

        # --- 6b3. MLB player detail export (player pages) ----------------
        # The /projections/#player= + FA-card-linked per-player payloads:
        # careers (StatsAPI + war_daily), Savant percentiles, arsenals,
        # Swing+, AAA Stuff+, FA market fields.
        with _step("6b3. MLB player detail export (mlb_player_detail.json)", log):
            # WS-R merge (2026-07-14): moved into the daily tail (d9b2) so the
            # cards bake off the POST-regen eFV/projections. Baking here read
            # the pre-regen 6b output, so /projections/ player cards served a
            # stale eFV vs the PROSPX board for up to a month.
            log.info("6b3 SKIP: chained d9b2 re-bakes mlb_player_detail post-regen")

        # --- 6b4. Bullpen Leaderboards (the /mlbstats/ surface) ---------
        # REM+ (FIP-based, pool-relative reliever skill; 100 = average) + team
        # Bullpen+ + gmLI role depth charts. Skill core from the StatsAPI season
        # leaderboard; gmLI / WPA self-computed from the winProbability feed
        # (FanGraphs is 403-blocked here). The per-game feed is cached, so this
        # is one big first walk, then incremental. Additive; never aborts.
        with _step("6b4. Bullpen Leaderboards (bullpen_leaderboards.json)", log):
            try:
                from bullpen_export import export as _export_bullpen
                _bp_n = _export_bullpen(log=log.info)
                log.info("bullpen: %d relievers scored", _bp_n)
            except Exception:
                log.exception("bullpen leaderboards export failed - continuing")

        # --- 6b4b. gmLI consistency artifact (leverage_consistency_eval) -
        # Refreshes data/leverage_consistency_eval.json (multi-year gmLI
        # deployment stability + per-player gmli_3yr values) from the
        # leaderboards + leverage caches 6b4 just built. bullpen_export joins
        # the artifact at export time, so the joined values lag one cycle; a
        # 3-year trailing mean makes that immaterial. Additive; never aborts.
        with _step("6b4b. gmLI consistency (leverage_consistency_eval.json)", log):
            try:
                # WS-R cadence gate (measured 271s): gmLI 3yr stability is a
                # slow re-derivation of an already-validated artifact. Skip when
                # fresh; EEPHUS_LABS=1 forces. The 6b4/6b4h leverage EXPORTS
                # still run every run; only this eval refresh is gated.
                if not _lab_should_skip(out_dir / "leverage_consistency_eval.json",
                                        "6b4b gmLI consistency", log):
                    import subprocess as _sp
                    _sp.run([sys.executable,
                             str(Path(__file__).parent / "tools" / "leverage_consistency_eval.py")],
                            check=True, timeout=1800)
            except Exception:
                log.exception("gmLI consistency refresh failed - continuing")

        # --- 6b4c. Reliever-metric lab (rem_plus_multiyear + riv_plus evals) --
        # Refreshes data/rem_plus_multiyear_eval.json (3-year REM+ proposed_values,
        # joined by bullpen_export next cycle, same trailing-window lag as gmli_3yr)
        # and data/riv_plus_eval.json (RIV+ accountability; RIV+ itself is computed
        # live in the 6b4 export). Also re-runs the pre-registered X-R1 SwStr gate
        # (loss ledger). Multi-season leverage walk uses the warm cache. Never aborts.
        with _step("6b4c. reliever lab (rem_plus_multiyear + riv_plus evals)", log):
            try:
                # WS-R cadence gate (measured 185s): re-derives 3yr REM+ +
                # RIV+/SwStr loss-ledger evals for already-settled metrics. Skip
                # when fresh; EEPHUS_LABS=1 forces. The 6b4 REM+/RIV+ export is
                # computed live every run; this only gates the eval refresh.
                if not _lab_should_skip(out_dir / "rem_plus_multiyear_eval.json",
                                        "6b4c reliever lab", log):
                    import subprocess as _sp
                    _sp.run([sys.executable,
                             str(Path(__file__).parent / "tools" / "rem_plus_lab.py")],
                            check=True, timeout=2400)
            except Exception:
                log.exception("reliever-metric lab refresh failed - continuing")

        # --- 6b4d. Yearly reliever history (bullpen_history.json) -------------
        # Per-season qualified-reliever boards for the /mlbstats/ history tabs.
        # Cached winProbability keeps the multi-season walk fast. Never aborts.
        with _step("6b4d. bullpen history (bullpen_history.json)", log):
            try:
                # WS-R cadence gate (measured 3m33s): HISTORY_SEASONS are all
                # CLOSED, immutable seasons - re-deriving them nightly buys
                # nothing. Skip when the artifact is fresh; EEPHUS_LABS=1
                # forces (e.g. after bumping HISTORY_SEASONS at season close).
                if not _lab_should_skip(out_dir / "bullpen_history.json",
                                        "6b4d bullpen history", log):
                    from bullpen_export import export_history as _export_bp_history
                    _export_bp_history(log=log.info)
            except Exception:
                log.exception("bullpen history export failed - continuing")

        # --- 6b4e. Starter lab (sem_plus_eval + sem_plus_multiyear_eval) ------
        # The validated SEM+ starter gate + 3-year SEM+ proposed_values. One
        # StatsAPI call per season, no leverage walk. Run before the starter
        # export so the 3yr join reads the fresh artifact. Never aborts.
        with _step("6b4e. starter lab (sem_plus + sem_plus_multiyear evals)", log):
            try:
                # WS-R cadence gate: re-validates the SEM+ starter gate + 3yr
                # proposed_values, an already-settled artifact. Skip when fresh;
                # EEPHUS_LABS=1 forces. The 6b4f starter EXPORT still runs every
                # run; only this eval refresh is gated.
                if not _lab_should_skip(out_dir / "sem_plus_eval.json",
                                        "6b4e starter lab", log):
                    import subprocess as _sp
                    _sp.run([sys.executable,
                             str(Path(__file__).parent / "tools" / "sem_plus_lab.py")],
                            check=True, timeout=1200)
            except Exception:
                log.exception("starter-metric lab refresh failed - continuing")

        # --- 6b4f. Starter Leaderboards + history (starter_*.json) ------------
        with _step("6b4f. Starter Leaderboards (starter_leaderboards.json)", log):
            try:
                from starter_export import export as _export_starters, export_history as _export_st_history
                _st_n = _export_starters(log=log.info)
                log.info("starters: %d starters scored", _st_n)
                # History = closed seasons only; same immutable-data cadence
                # gate as 6b4d. The live export above still runs every run.
                if not _lab_should_skip(out_dir / "starter_history.json",
                                        "6b4f starter history", log):
                    _export_st_history(log=log.info)
            except Exception:
                log.exception("starter leaderboards export failed - continuing")

        # --- 6b4g-lab. Hitter lab (hem_plus_eval + hem_plus_multiyear_eval) ----
        # Forward-chained HEM+ validation + the 3yr proposed_values. Runs off the
        # CACHED StatsAPI hitting seasons, so it is offline + cheap. Additive.
        with _step("6b4g-lab. hitter lab (hem_plus + hem_plus_multiyear evals)", log):
            try:
                # WS-R cadence gate (measured 47s): forward-chained HEM+
                # validation over already-settled seasons. Skip when fresh;
                # EEPHUS_LABS=1 forces. The 6b4g hitter EXPORT runs every run.
                if not _lab_should_skip(out_dir / "hem_plus_eval.json",
                                        "6b4g-lab hitter lab", log):
                    from tools import hem_plus_lab
                    hem_plus_lab.run(write=True)
            except Exception:
                log.exception("hitter lab failed - continuing (export uses the last eval)")
            try:
                # Savant xwOBA forward-validation (network); same WS-R cadence gate.
                if not _lab_should_skip(out_dir / "xhem_plus_eval.json",
                                        "6b4g-lab xhem lab", log):
                    from tools import xhem_plus_lab
                    xhem_plus_lab.run(write=True)
            except Exception:
                log.exception("xhem lab failed - continuing")

        # --- 6b4g. Hitter Leaderboards + history (hitter_*.json) --------------
        # HEM+ hitter board + team Offense+ from the StatsAPI season hitting
        # leaderboard. Validated (forward-chained vs next-year wOBA; tools/
        # hem_plus_lab.py -> data/hem_plus_eval.json). 3yr HEM+ joined by MLBAM
        # from the multiyear eval (validated companion). Additive; never aborts.
        with _step("6b4g. Hitter Leaderboards (hitter_leaderboards.json)", log):
            try:
                from hitter_export import export as _export_hitters, export_history as _export_hit_history
                _hit_n = _export_hitters(log=log.info)
                log.info("hitters: %d hitters scored", _hit_n)
                # History = closed seasons only; same immutable-data cadence
                # gate as 6b4d. The live export above still runs every run.
                if not _lab_should_skip(out_dir / "hitter_history.json",
                                        "6b4g hitter history", log):
                    _export_hit_history(log=log.info)
            except Exception:
                log.exception("hitter leaderboards export failed - continuing")

        # --- 6b4h. Leverage Leaderboards (leverage_leaderboards.json) --------
        # Realized in-game WPA impact for BATTERS (WPA / pLI / Clutch / WPA-LI)
        # and STARTERS (per-start WPA), self-computed from the StatsAPI
        # winProbability feed in ONE extra pass over the already-warm cache the
        # bullpen board (6b4) just walked. Descriptive realized value (the RIV+ /
        # xREM+ precedent), not a predictive model. Additive; never aborts.
        with _step("6b4h. Leverage Leaderboards (leverage_leaderboards.json)", log):
            try:
                from leverage_export import (export as _export_leverage,
                                             export_history as _export_lev_history)
                _lev_n = _export_leverage(log=log.info)
                log.info("leverage: %d batter+starter rows scored", _lev_n)
                # Yearly batter/starter history (leverage_history.json) for the
                # season pills - closed seasons only, so it rides the same
                # immutable-data cadence gate as 6b4d (measured 1-2m saved).
                if not _lab_should_skip(out_dir / "leverage_history.json",
                                        "6b4h leverage history", log):
                    _export_lev_history(log=log.info)
            except Exception:
                log.exception("leverage leaderboards export failed - continuing")

        # --- 6b4i-lab. Defense lab (dem_plus_eval + dem_plus_multiyear_eval) --
        # The pre-registered DEM+ validation (docs/dem-plus-2026-09-11/) and the
        # 3yr proposed_values. Offline against the caches 6b4g just warmed.
        with _step("6b4i-lab. defense lab (dem_plus + dem_plus_multiyear evals)", log):
            try:
                if not _lab_should_skip(out_dir / "dem_plus_eval.json",
                                        "6b4i-lab defense lab", log):
                    from tools import dem_plus_lab
                    dem_plus_lab.run(write=True)
            except Exception:
                log.exception("defense lab failed - continuing (export uses the last eval)")

        # --- 6b4i. Defense Leaderboards + history (defense_*.json) ------------
        # DEM+ fielder board + Team DEM+ from FanGraphs' published fielding runs
        # (MLB sabermetrics feed, framing recovered as the rar residual) and the
        # season fielding innings. After 6b4g, which it reads for the HEM+ join.
        with _step("6b4i. Defense Leaderboards (defense_leaderboards.json)", log):
            try:
                from defense_export import (export as _export_defense,
                                            export_history as _export_def_history)
                _def_n = _export_defense(log=log.info)
                log.info("defense: %d fielders scored", _def_n)
                if not _lab_should_skip(out_dir / "defense_history.json",
                                        "6b4i defense history", log):
                    _export_def_history(log=log.info)
            except Exception:
                log.exception("defense leaderboards export failed - continuing")

        # --- 6b4j. eWAR Leaderboard (war_leaderboards.json) -------------------
        # The whole-player board the other five cannot draw: batting plus
        # pitching eWAR summed BEFORE rounding, so a two-way player reads as one
        # season and a swingman on neither pitcher board still appears, plus the
        # club rollup on both bases (the roster today, and the club the eWAR was
        # earned for). LAST of the /mlbstats/ steps on purpose: it reads the four
        # boards 6b4 to 6b4i just wrote for the `boards` field, and it shares the
        # lru-cached side map they built, so the eWAR sides cost nothing here.
        # WHAT IT DOES COST: the Earned basis is the only thing on this page
        # built from the war_daily STINT frames, so it reads one frame per side
        # (shared with the name fallback, one read each). The batting one comes
        # off pybaseball's disk cache; the pitching one is a live download of
        # war_daily_pitch.txt, which pybaseball does not cache (war_source
        # .stint_frame's ASYMMETRY note). A failed download is served from the
        # last-good parquet and disclosed on the artifact, not hidden.
        # Additive; never aborts.
        with _step("6b4j. eWAR Leaderboard (war_leaderboards.json)", log):
            try:
                from war_board_export import export as _export_war_board
                _war_n = _export_war_board(log=log.info)
                log.info("ewar board: %d players scored", _war_n)
            except Exception:
                log.exception("ewar leaderboard export failed - continuing")

        # --- 6b4k. Multi-year windows (mlbstats_window_*.json) ----------------
        # The fixed set of season WINDOWS the /mlbstats/ boards can be read on:
        # counts summed, rates pooled over their own denominator, and every "+"
        # index RECOMPUTED for the window by the recipe the shipped three-year
        # columns use. AFTER 6b4j, because the Overall window folds the
        # per-season substrate that step writes and the lab refuses to serve a
        # substrate on another eWAR build.
        # THE OWNER REVERSED THIS STEP'S CADENCE NOTE ON 2026-09-25 (answer
        # M17-1, census M06-03). It used to read "on the lab cadence, not
        # nightly", which let a window's live-season slice lag the boards beside
        # it by up to LAB_EVAL_FRESH_DAYS. The live-season panel is now rebuilt
        # NIGHTLY by run_daily step 9e-pre0d (about 75 s: completed seasons
        # memoise under .cache/mlbstats_windows/ and only the live season is
        # re-walked), and the Current boards' HEM+ / SEM+ / REM+ / DEM+ 3yr
        # columns read the l3 window it writes (answer M17-2). This monthly step
        # keeps its cadence gate and its basis_moved override; the nightly step
        # skips when this one built the windows today on the served basis.
        # EEPHUS_LABS=1 forces, the same escape hatch every other lab has.
        # STALE_DAYS is untouched by either step. Additive; never aborts.
        with _step("6b4k. Multi-year windows (mlbstats_window_*.json)", log):
            try:
                from tools import mlbstats_window_lab
                _win_path = out_dir / "mlbstats_windows.json"
                # THE CADENCE GATE ASKS AGE; THIS ASKS BASIS. The windows carry
                # an eWAR column and the eWAR build moves nightly, so a 45-day
                # cadence could leave the window's `war` up to 45 days behind
                # the column beside it - and the test that asserts the two share
                # a basis would go red on a rebuild this gate then refused to
                # let the pipeline clear. basis_moved is the artifact-level
                # `invalidated_by` argument applied one step earlier.
                _win_moved = mlbstats_window_lab.basis_moved(_win_path)
                if _win_moved:
                    log.info("6b4k multi-year windows: RUN - the served eWAR "
                             "basis moved under the window artifact")
                if _win_moved or not _lab_should_skip(
                        _win_path, "6b4k multi-year windows", log):
                    _win_n = mlbstats_window_lab.export(log=log.info)
                    log.info("mlbstats windows: %d window(s) published", _win_n)
                # 6b4 to 6b4i wrote the four boards BEFORE this step, so their
                # *_3yr columns were joined from the previous window file.
                # Re-join them from mlbstats_window_l3.json now (only those keys
                # of hitter_leaderboards.json, starter_leaderboards.json,
                # bullpen_leaderboards.json and defense_leaderboards.json move).
                import bullpen_export as _be_win
                _be_win.restamp_window_3yr(log=log.info)
            except Exception:
                log.exception("multi-year window lab failed - continuing")

        # --- 6b5. Alchemy Lab (the /pal/ surface) ---------------
        # RP<->SP role-conversion candidate scores + a validated conversion
        # history. Arsenal/velocity from bulk Statcast, platoon from StatsAPI
        # splits, role from the season leaderboard; reuses the REM+ model for the
        # relief projection. Additive; never aborts.
        with _step("6b5. Alchemy Lab (pal.json)", log):
            try:
                from pal_export import export as _export_pal
                _pal_n = _export_pal(log=log.info)
                log.info("pal: %d conversion candidates scored", _pal_n)
            except Exception:
                log.exception("alchemy lab export failed - continuing")

        # --- 6b7. Arbitration Predictor (arbitration.json) ---------------
        # Projected arbitration salaries for every eligible player plus the
        # per-season award history. Reads the committed arbitration ledger,
        # the Spotrac status grid and the projection board; the one-time
        # MLBTR ingest is NOT part of this and never runs from the pipeline.
        # Additive; never aborts.
        with _step("6b7. Arbitration Predictor (arbitration.json)", log):
            try:
                from arb_export import export as _export_arb
                _arb = _export_arb(log=log.info)
                _arb_n = len((_arb.get("board") or {}).get("rows") or [])
                log.info("arbitration: %d players with remaining arb years", _arb_n)
                _record_ingest("arbitration_export", True, _arb_n,
                               "arbitration board", "mlb", log)
            except Exception:
                log.exception("arbitration export failed - continuing")
                _record_ingest("arbitration_export", False, 0,
                               "arbitration export raised", "mlb", log)

        # --- 6b7e. In-Game Management decision ledger --------------------
        # The decision ledger behind the League, Clubs and Decisions tabs:
        # mgmt_decisions.build runs the matched-state baseline
        # (management_baseline.json), the nine-family ledger
        # (management_decisions.json) and the per club-season shards
        # (data/mgmt_decisions/). Realized value per family only; no plus
        # metric, no cross-family total, the club-season as the agent.
        #
        # PLACED BEFORE 6b7c because the board export reads the ledger summary
        # this step writes; the other way round the served board was one run
        # stale after every corpus rebuild (the baked-rank precedent).
        #
        # OFFLINE BY CONSTRUCTION: it reads the play corpus, the daily WAR
        # frames and the raw win_prob feed heads; nothing fetches. The ledger
        # moves when the corpus moves: the daily step 9e-pre0e rebuilds the open
        # season's corpus nightly and re-runs this ledger on it (owner answer
        # 2026-09-25). WITHOUT THE CORPUS (the deploy box carries
        # none) the step writes nothing and records nothing: the committed
        # artifacts stand, and a "not built" stub must never overwrite them,
        # which is what served four tabs dark with an operator instruction.
        # A raise is still recorded as a red. 6b7d is the Franchise board (D3).
        with _step("6b7e. In-Game Management decision ledger "
                   "(management_baseline.json, mgmt_decisions shards)", log):
            try:
                import mgmt_decisions as _mdc
                # Completed seasons stay frozen (owner answer 2026-09-25): their
                # shards on disk keep their bytes; the open season's are written.
                _mdd = _mdc.build(freeze_before=date.today().year)
                if _mdd.get("status") == "built":
                    _mdc.OUT.write_text(
                        json.dumps(_mdd, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
                    log.info("mgmt decisions: %s rows, %d club-seasons, %d shards",
                             f"{_mdd.get('n_all', 0):,}",
                             (_mdd.get("clubs") or {}).get("n_rows", 0),
                             len((_mdd.get("shards") or {}).get("index") or []))
                    _record_ingest("mgmt_decisions", True, int(_mdd.get("n_all") or 0),
                                   "in-game management decision ledger", "mlb", log)
                else:
                    log.info("mgmt decisions: %s; the committed ledger stands",
                             _mdd.get("status"))
            except Exception:
                log.exception("mgmt decisions failed - continuing")
                _record_ingest("mgmt_decisions", False, 0,
                               "mgmt decisions raised", "mlb", log)

        # --- 6b7c. In-Game Management board (management_board.json) ------
        # The /management/ payload. Reads the committed artifacts (the running
        # game, the gate eval, the win expectancy model and the ledger summary
        # 6b7e writes just above, so the board is never a run stale) and,
        # when the play corpus is present, recomputes the club STYLE board from
        # it. No per-club plus metric is written: the gate battery returned a
        # bounded null and the payload says so.
        #
        # Additive; never aborts. The club board is the only part that needs the
        # corpus, and mgmt_export degrades to a status string without it rather
        # than failing the step.
        with _step("6b7c. In-Game Management board (management_board.json)", log):
            try:
                import mgmt_export as _mg
                _mgd = _mg.build()
                _mg.OUT.write_text(
                    json.dumps(_mgd, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
                _mg_n = (_mgd.get("teams") or {}).get("n_rows", 0)
                log.info("management: %d attempts priced, %d club-seasons",
                         _mgd["running_game"]["n_attempts_priced"], _mg_n)
                _record_ingest("mgmt_export", True,
                               _mgd["running_game"]["n_attempts_priced"],
                               "in-game management board", "mlb", log)
            except Exception:
                log.exception("management export failed - continuing")
                _record_ingest("mgmt_export", False, 0,
                               "management export raised", "mlb", log)

        # --- 6b7b. Hall of Fame board (hof_board.json) -------------------
        # The /hof/ payload: career WAR, WAR7, JAWS, WAR ink and the public HoF
        # Monitor and Standards columns for every ten-season player, in three
        # bands, with the induction ledger joined in three states.
        #
        # OFFLINE BY CONSTRUCTION. hof_export reads war_source's last-good
        # parquet by path, never through pybaseball, because the pitching side
        # carries no disk cache and would be a live download on every run. It
        # also reads the committed ballot panel. Nothing here fetches.
        #
        # Additive; never aborts. Four of the page's eight sections are dark,
        # and a failure here leaves the previous board in place rather than
        # publishing a page with no numbers on it.
        with _step("6b7b. Hall of Fame board (hof_board.json)", log):
            try:
                import hof_export as _hof
                # THE MODULE'S OWN PATH CONSTANT, not a second copy of it. The
                # first version wrote to a path spelled out here against a `ROOT`
                # that is not a run_monthly global, which raised NameError inside
                # a best-effort try/except: the step would have reported failure
                # every night and written nothing. test_no_undefined_names caught
                # it, which is the whole reason that test exists.
                _hofd = _hof.build()
                _hof.OUT.write_text(
                    json.dumps(_hofd, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
                _hof_n = len(_hofd.get("leaderboard") or [])
                log.info("hof: %d eligible, %d watch, %d not yet eligible",
                         _hof_n, len(_hofd.get("watch") or []),
                         len(_hofd.get("not_yet_eligible") or []))
                _record_ingest("hof_export", True, _hof_n,
                               "hall of fame board", "mlb", log)
            except Exception:
                log.exception("hall of fame export failed - continuing")
                _record_ingest("hof_export", False, 0,
                               "hall of fame export raised", "mlb", log)

        # --- 6b7f. Awards board -------------------------------------------
        with _step("6b7f. Awards board (awards.json)", log):
            # The monthly Awards board (AWARDS_PLAN 4.8), after the Hall of
            # Fame board and the month's boards and management, through the
            # same writer as the daily step d10h. Additive; never aborts: a
            # refusal or a raise leaves the previous files on disk and files a
            # red under "awards_export".
            _export_awards_board(log)

        # --- 6b6. Fantasy Tools (the /fantasy/ surface) -----------------
        # ROS fantasy projections (reuse the FA/Projections engine) scored in the
        # Ottoneu formats + the probable-pitcher schedule -> 8 sections (daily
        # streamers, ROS SP/RP/hitters, two-start, buy/sell, closers, callups).
        # The heavy build_corpus() lives HERE (monthly); run_daily does a cheap
        # schedule-only refresh (fantasy_export.refresh_live). Additive; never aborts.
        with _step("6b6. Fantasy Tools (fantasy.json)", log):
            try:
                from fantasy_export import export as _export_fantasy
                _fan_n = _export_fantasy(log=log.info)
                log.info("fantasy: %d players projected ROS", _fan_n)
            except Exception:
                log.exception("fantasy export failed - continuing")

        # --- 6f. Betting model context refit (offline) -------------------
        # Re-fits the run-scoring coefficients and the two one-parameter
        # corrections (home-field, run-differential shrink) on completed games
        # read out of .cache/game_feeds, then re-runs the backtest artifact. No
        # network. On a box with no game-feed cache this is a no-op and the
        # model falls back to documented literature priors, which the payload
        # and the page both report as the coefficient source. Additive; never
        # aborts. Runbook: docs/diamond-betting.md.
        with _step("6f. Betting model context refit", log):
            try:
                import betting_model
                # Same season pin as run_daily 9e-pre1; see the note there.
                _season6f = str(date.today().year)
                betting_model.build_context(season=_season6f, log_fn=log.info)
                betting_model.backtest(season=_season6f, log_fn=log.info)
            except Exception:
                log.exception("betting model refit failed - continuing")

        # --- 6c. Organization Tendencies (farm-detail Tendencies tab) ---
        # Pure aggregation over the DB + just-written sidecars; additive.
        # --- 6c / 6d: exported by the chained daily tail instead. --------
        # WS-R merge (2026-07-14): main() always chains run_daily(chained=True),
        # whose d9 rebuild_only re-exports org_tendencies.json AND
        # trade_values.json ~15 min from now with FRESHER inputs (post
        # eFV-regen + GRPO retrain) - the exports here were overwritten every
        # monthly night, so they were pure duplication (7.7s + 19.2s) and the
        # trade_value_history snapshot recorded a board the site never served.
        # The monthly-cadence snapshot_trade_values now runs AFTER the chained
        # tail (see below) against the artifact actually published.
        log.info("6c/6d SKIP: chained d9 re-exports org_tendencies + trade_values "
                 "with post-regen inputs; snapshot moved after the chain")

        finish_run(run_id, new_snapshots=new_count, stat_lines=stat_count,
                   notes=f"{_n_ts} players, {len(new_trades)} trades")
        # NO RUN-SUMMARY STAMP HERE (2026-08-07). It used to sit on this line
        # and was always superseded within the same night by the chained
        # daily's own stamp, so the 74MB artifact was parsed, re-serialised and
        # replaced three times per monthly night for one purpose. The stamp now
        # happens once, at the chain (see _chain_daily_and_stamp below), with a
        # fallback there for the path where the chain raises. Do not re-add a
        # stamp before the chain: this is the file a two-writer race truncated.
        # Capture the DERIVED board state (consensus rank/FV + Arkmetric
        # family) for the active board so the time-travel board (Part 2) and
        # the Arkmetric-vs-outcome backtest (Part 4) accrue monthly history.
        # Monthly-only: the daily job does NOT snapshot here (grades/rankings
        # only change on the monthly cadence). Idempotent (upsert-by-date).
        try:
            _ts = json.loads(out_path.read_text(encoding="utf-8"))
            _n_metric = snapshot_board_metrics(_ts.get("players") or [],
                                               source_coverage=_source_cov)
            log.info("metric_snapshots: captured board state for %d players "
                     "(source coverage for %d)", _n_metric, len(_source_cov or {}))
            # Org-grain sibling: record the composite farm_rank so farm-system
            # rank movement accrues a server-side history (the de-noised
            # movement engine reads it on the NEXT export). Monthly-only, same
            # as the board snapshot above; idempotent upsert-by-(org, date).
            _n_farm = snapshot_farm_ranks(_ts.get("org_summary") or [])
            log.info("farm_rank_history: captured rank for %d orgs", _n_farm)
            # Letter-grade sibling (review-queue item 10, moved up to
            # 2026-07-02): the composite farm LETTER was derived at export
            # and never persisted, so the farm_grades registry row had no
            # forward-validatable history. Additive and best-effort: a
            # failure here must never abort the run. Idempotent
            # upsert-by-(org, date), no-ops when grades are not computable.
            try:
                _n_fg = snapshot_farm_grades(_ts.get("org_summary") or [])
                log.info("farm_grade_history: captured letter grade for %d orgs", _n_fg)
            except Exception:
                log.exception("farm_grade_history capture failed, continuing")
        except Exception:
            log.exception("metric_snapshots/farm_rank_history capture failed — continuing")
        # Source-vs-source predictive backtest (data/source_backtest.json for
        # the Methodology tab). Reads the just-written timeseries + debuts, so
        # it refreshes as new outcome WAR lands and 2024+ cohorts resolve.
        try:
            from source_backtest import run_source_backtest
            _bt = run_source_backtest(data_dir=out_dir, write=True)
            log.info("source_backtest: %d resolved base years, common_n=%d",
                     len(_bt["window"]["years"]), _bt["accuracy"]["common_n"])
        except Exception:
            log.exception("source_backtest failed — continuing")
        # EV-00 progress ledger: the backtest just moved, so record it now
        # rather than waiting for the daily 9g hook.
        _efv_progress_update(out_dir, "monthly")
        # Cohort-conditioned source accuracy (data/source_cohort_accuracy.json,
        # served at /glossary/#view=source-accuracy). ORDER IS LOAD-BEARING and
        # is why this sits exactly here, between its two neighbours:
        #   AFTER  run_source_backtest, because the reproduction leg compares
        #          its recomputed per-archetype Spearmans against the SERVED
        #          data/source_backtest.json; run it first and that leg grades
        #          the previous cycle's artifact.
        #   BEFORE run_consensus_weight_ab, because source_backtest.
        #          _cohort_ab_sidecar (source_backtest.py:1218, called at :1339)
        #          reads this file and appends its cohort_ab block to the weight
        #          eval. Missing file = key simply absent, which is honest but
        #          silently drops the cohort arms from the eval every run.
        # Ships NOTHING: it writes no source_weights.json and changes nothing in
        # consensus.py. Same try/except-and-continue as its neighbours, and no
        # heartbeat, because none of the backtests in this block has one.
        try:
            from source_cohort_accuracy import run_source_cohort_accuracy
            _ca = run_source_cohort_accuracy(data_dir=out_dir, write=True)
            log.info("source cohort accuracy: n=%d cells=%d answerable=%d ships_a_weight=%s",
                     _ca["basis"]["deduped_players"],
                     _ca["multiplicity"]["cells_tested"],
                     _ca["multiplicity"]["cells_flagged_answerable"],
                     _ca["ships_a_weight"])
        except Exception:
            log.exception("source cohort accuracy failed - continuing")
        # WS-5 — consensus weight A/B + vintage-frozen source weights. The
        # weights only move when a NEW base year resolves (yearly), so the
        # monthly rerun is a freshness pass, not a jitter source; they take
        # effect on the NEXT rebuild (consensus loads them at import).
        try:
            from source_backtest import run_consensus_weight_ab
            _ab = run_consensus_weight_ab(data_dir=out_dir, write=True)
            log.info("consensus weight A/B: ship=%s weights=%s",
                     _ab["ship"], _ab["live_weights"])
        except Exception:
            log.exception("consensus weight A/B failed — continuing")
        # Draft analog — FanGraphs vs MLB Pipeline pre-draft FV accuracy on the
        # resolved classes (2018-2021). Same ship discipline: only writes
        # data/draft_source_weights.json (consumed by draft_export at import on
        # the next rebuild) when the weighted blend beats equal. Reads
        # draft_timeseries.json + debuts.json, both produced above.
        try:
            from draft_source_backtest import run_draft_weight_ab
            _dab = run_draft_weight_ab(data_dir=out_dir, write=True)
            log.info("draft weight A/B: ship=%s weights=%s resolved=%s",
                     _dab["ship"], _dab["live_weights"], _dab["resolved_years"])
        except Exception:
            log.exception("draft weight A/B failed — continuing")
        # ETA backtest rerun (Phase 4b WS-8 — cheap, cache-only StatsAPI
        # reads). Rescores the live v39 bases as new debuts land; the
        # frozen v38 comparator keeps the before/after honest forever.
        try:
            from eta_backtest import run as _eta_bt
            _er = _eta_bt()
            log.info("eta_backtest: champion MAE %.3f within-1y %.3f (n=%d)",
                     _er["champion_heuristic"]["mae"],
                     _er["champion_heuristic"]["within_1y"],
                     _er["champion_heuristic"]["n"])
        except Exception:
            log.exception("eta_backtest failed — continuing")
        # Star-odds artifacts (data/star_label_view.json + star_odds_eval.json).
        # Rebuilds the published-vs-realized star-rate calibration and the label
        # view off the resolved debut/career + xfv data produced above. Was only
        # ever produced by a manual tool run, so the display + realized-rate
        # disclosure silently froze between runs; wire it onto the pipeline
        # cadence. Reads-only from the DB + xfv; additive, never aborts.
        try:
            from tools import build_star_odds_artifacts
            build_star_odds_artifacts.main()
        except Exception:
            log.exception("star_odds artifacts failed — continuing")
        # Editorial forward-validation (Phase 5 WS-10). Scores matured
        # 30/60-day flag cohorts vs matched controls; WITHHOLDS the
        # artifact until the first cohort matures (registry honesty —
        # an empty eval would let spotlights masquerade as measured).
        # NB once it first writes data/editorial_eval.json, the standing
        # rule test goes red in dev/CI until the owner registers the
        # verdict — that forcing function is the design. (Deploy runs,
        # EEPHUS_DEPLOY_RUN=1, skip-with-warning instead so a pending
        # verdict can't freeze nightly publishing; see 2026-07-14 note in
        # DEPLOY_RUNBOOK section 6.)
        try:
            from editorial_eval import run as _ed_eval
            _ed = _ed_eval()
            log.info("editorial_eval: %s matured, %s pending, written=%s",
                     _ed.get("flags_matured", _ed.get("matured", 0)),
                     _ed.get("flags_pending", _ed.get("pending", 0)),
                     _ed.get("written"))
        except Exception:
            log.exception("editorial_eval failed — continuing")
        # Model registry freshness pass (data/model_registry.json) — restamps
        # artifact ages + re-validates references. Verdicts are hand-committed
        # with their evals; this only keeps the accountability ledger honest
        # about staleness. Best-effort.
        try:
            from model_registry import refresh_stamps
            _reg = refresh_stamps()
            if _reg.get("problems"):
                log.warning("model registry problems: %s", _reg["problems"])
            # Regenerate the generated audit docs in the same breath: the
            # restamp rewrites freshness fields that MODEL_REGISTRY.md renders,
            # so regenerating here keeps the tree self-consistent and the
            # test_generated_docs_in_sync gate green (both files travel in the
            # same commit). Best-effort like everything in this tail.
            import subprocess as _sp_docs
            _sp_docs.run([sys.executable,
                          str(Path(__file__).parent / "tools" / "gen_audit_docs.py")],
                         check=True, timeout=300)
        except Exception:
            log.exception("model registry refresh failed — continuing")
        # LIBRARY_11 Model Updates record: after the registry refresh so the
        # derived cards it diffs are fresh. Best-effort.
        _model_updates_update(out_dir, "monthly")
        # Headshot resolution (data/photo_ctx.json for the photo fallback chain).
        # Incremental: TTL-skips already-resolved ids and only re-probes new or
        # still-missing players, so steady-state runs are cheap. Best-effort —
        # a network hiccup must not fail the pipeline (the front-end falls back
        # to the legacy 67+generic URL for any unresolved id).
        try:
            from headshots import backfill as _backfill_headshots
            _hs = _backfill_headshots(data_dir=out_dir, workers=16, write_json=True)
            log.info("headshots: %.1f%% coverage (%d/%d) — %d probed this run, %d still missing",
                     _hs["pct"], _hs["with_photo"], _hs["total"],
                     _hs.get("probed_this_run", 0), _hs["missing_count"])
        except Exception:
            log.exception("headshot resolution failed — continuing")
        # v19 — Per-step duration table. Sorted by slowest first so the
        # biggest wall-time culprits surface at the top of the log. Also
        # writes logs/pipeline_steps_latest.json (machine-readable) so the
        # NEXT run can be diffed against this one instead of against a
        # May-2026 log that predates half these steps.
        _log_step_summary(log, time.monotonic() - _run_start,
                          mode="monthly", run_id=run_id)
        # The monthly run also performs the DAILY fast-moving refresh
        # (transactions, IL, roster status, debuts/graduations, trades) so a
        # plain `python run_monthly.py` never leaves them stale — the Injured
        # List section in particular ONLY moves on the daily job, so without
        # this a monthly-only cadence froze it between nightly runs. Runs after
        # the monthly grade work so the rebuilt timeseries carries both the
        # fresh monthly grades and the up-to-the-day transactions/IL. Best-effort
        # + self-contained (own run_id + timeseries rebuild); a daily-side
        # failure must not fail the already-completed monthly run.
        #
        # OOM: the monthly whole-universe caches (all_snaps, timeseries, and the
        # career/statline/Statcast/zone/arsenal/sabermetric/tx/trades/career-WAR
        # caches + draft_by_id) were already freed right after the step-5 export
        # above (see that block) - they are None here. This final collect sweeps
        # the step 6-6b6 garbage (FA + leaderboard + fantasy corpora) before the
        # daily/rebuild/export/site-build heaps stack, which is the main memory
        # driver on the ~6GB box.
        import gc as _gc
        _gc.collect()

        def _chained_daily_refresh() -> None:
            log.info("monthly run: chaining the daily fast-moving refresh")
            # WS-R: chained=True elides the steps the monthly path just ran in
            # THIS process: d5c (statlines, 3a/3b), d5d (Statcast, 3d-ter),
            # and since 2026-07-14 also d0 (TJStats Live, 1c), d4 (tx), d5
            # (IL, 2b.vii), d6 (roster), d8 (trades, step 4) - pure re-fetch
            # duplication minutes apart. d0b (Pipeline Live), MLBAM discovery,
            # d7 (debuts), d9 (final eFV regen + projections re-bake + board),
            # d5e (game logs) and d11 (site build) still run. run_daily owns
            # the single run-summary stamp for the whole monthly night.
            run_daily(out_dir=out_dir, workers=workers, no_cache=no_cache,
                      chained=True)
            # Monthly-cadence trade-value snapshot, AFTER the chain so the
            # history records the trade_values.json actually published (the
            # chained d9 re-exports it with post-regen inputs; snapshotting
            # in old step 6d recorded a board the site never served).
            try:
                _tv_written = json.loads(
                    (out_dir / "trade_values.json").read_text(encoding="utf-8"))
                _n_tvh = snapshot_trade_values(_tv_written.get("players") or [])
                log.info("trade_value_history: snapshotted %d board records", _n_tvh)
            except Exception:
                log.exception("trade_value snapshot failed - continuing")

        _chain_daily_and_stamp(out_path, log, _chained_daily_refresh)
        # Ingest health, last. The chained daily already wrote a "daily"
        # ledger; rewriting it here as "monthly" folds in this run's own
        # entries (TJStats 1c, JB 1c-bis, the ESPN probe) so the published
        # sidecar describes the FULL run, not just its daily tail.
        write_ingest_health(out_dir, "monthly", log)
    except Exception:
        log.exception("run failed")
        finish_run(run_id, new_snapshots=new_count, stat_lines=stat_count,
                   notes="FAILED — see logs")
        # A crashed run is exactly when the ingest ledger matters most: it
        # records which sources HAD landed before the failure, and which
        # scheduled ones never ran at all.
        try:
            write_ingest_health(out_dir, "monthly-FAILED", log)
        except Exception:                                # noqa: BLE001
            log.exception("ingest health write failed on the crash path")
        # Still print the partial step summary on crash — useful for
        # debugging which phase blew up. The JSON companion is written too:
        # a crashed run's step table is exactly when someone needs to rank
        # what had already been paid for.
        _log_step_summary(log, time.monotonic() - _run_start,
                          mode="monthly-FAILED", run_id=run_id)
        raise


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Prospect stock tracker — monthly pipeline runner.",
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="Probe each source and report what's working. "
                         "No DB writes, no consensus build, no export.")
    ap.add_argument("--force",      action="store_true",
                    help="Bypass HTML/JSON cache and re-fetch every URL.")
    ap.add_argument("--skip-stats", action="store_true",
                    help="Skip MiLB stat-line fetch (faster local runs).")
    ap.add_argument("--out-dir", type=Path, default=Path("data"))
    ap.add_argument("--workers", type=int, default=None,
                    help="Maximum worker threads for concurrent fetches (default: auto)")
    ap.add_argument("--cache-ttl", type=int, default=None,
                    help="Cache TTL in seconds for MLB API responses (default: 86400 = 24h)")
    ap.add_argument("--no-cache", action="store_true",
                    help="Bypass HTTP caching (same as --force for cache)")
    ap.add_argument("--fast", action="store_true",
                    help="Skip pitch arsenals + Statcast metrics fetch. "
                         "Core consensus FV / stat lines still fetched. "
                         "Useful for local dev iterations.")
    ap.add_argument("--rebuild-only", action="store_true",
                    help="Skip scraping entirely. Ingest any pending "
                         "FanGraphs CSV drops, then rebuild + export "
                         "data/timeseries.json from the current DB state. "
                         "Use after dropping new FG CSVs to push the data "
                         "to the website without rerunning the full pipeline.")
    ap.add_argument("--daily", action="store_true",
                    help="DAILY fast-moving refresh only: transactions, IL, "
                         "roster status, debuts/graduations, and trades, then "
                         "rebuild data/timeseries.json. Grades, tool evals, "
                         "Arkmetrics, farm grades and the ranking stay on the "
                         "monthly cadence (a plain `python run_monthly.py`). "
                         "Run this nightly.")
    ap.add_argument("--odds-open", action="store_true", dest="odds_open",
                    help="ONE early-UTC open-odds capture and nothing else. "
                         "Its own cron (suggested 13:10 UTC), because the "
                         "nightly's hour is not early enough: 11 of the 22 "
                         "cached snapshots landed after their slate's first "
                         "pitch. Costs 3 credits, skips for free when today's "
                         "slate is already captured, and adds no spend because "
                         "step 9d-pre-odds then skips.")
    args = ap.parse_args()
    # Ceiling worker counts on low-RAM deploy boxes: the spawn ProcessPoolExecutor
    # in statcast pass-3 is the one pool whose resident memory scales with worker
    # count, so bounding `workers` bounds the peak. EEPHUS_MAX_WORKERS (e.g. 2-3 on
    # the ~6GB box) trades a little wall-time for headroom; unset = unchanged.
    _wcap = os.environ.get("EEPHUS_MAX_WORKERS")
    if _wcap:
        try:
            _wc = max(1, int(_wcap))
            args.workers = _wc if args.workers is None else min(args.workers, _wc)
        except ValueError:
            pass
    if args.dry_run:
        probe(force=args.force)
        sys.exit(0)
    # Ahead of --daily on purpose: --odds-open is the tiny standalone cron, and
    # the two are never meant to be combined. Exit 0 on a skip as well as a
    # capture; the only nonzero is a capture that was attempted and failed, so
    # cron mail means something.
    if args.odds_open:
        _res = run_odds_open()
        sys.exit(0 if _res.get("ok") else 1)
    if args.daily:
        run_daily(out_dir=args.out_dir, workers=args.workers, no_cache=args.no_cache)
        sys.exit(0)
    if args.rebuild_only:
        rebuild_only_cli(out_dir=args.out_dir)
        # Non-zero when the Spotrac format sentinel filed red (the writes above
        # still finished, with every wrong-type position read as None).
        sys.exit(1 if _SPOTRAC_FORMAT_RED else 0)
    main(force_refetch=args.force, skip_stats=args.skip_stats, out_dir=args.out_dir,
         workers=args.workers, cache_ttl=args.cache_ttl, no_cache=args.no_cache,
         fast=args.fast)

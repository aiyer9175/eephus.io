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
from datetime import date
import concurrent.futures
from pathlib import Path


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


def _log_step_summary(log: logging.Logger, total_runtime: float) -> None:
    """Print the per-step duration table + a `% of total` column.
    Steps are listed by descending duration so the worst hogs lead.
    """
    if not _STEP_TIMES:
        log.info("step summary: no timed steps recorded")
        return
    ranked = sorted(_STEP_TIMES, key=lambda x: x[1], reverse=True)
    total = max(total_runtime, sum(d for _, d in ranked))
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
            out_path.write_bytes(_orjson.dumps(payload, option=_orjson.OPT_NON_STR_KEYS))
        except ImportError:
            out_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    except Exception:
        log.exception("could not patch latest run summary into %s", out_path)

from scrapers import scrape_all, probe
from storage import (
    init_db, insert_snapshots, start_run, finish_run,
    load_all_snapshots, load_statlines, upsert_statlines,
    insert_trades, load_trades,
    upsert_birth_date, load_birth_dates,
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
    snapshot_board_metrics, snapshot_trade_values, snapshot_farm_ranks, record_il_observation,
)
from consensus import build_timeseries
from stats import (fetch_statlines_for, derive_statlines_from_career,
                   fetch_pitch_arsenal, fetch_sabermetrics,
                   fetch_career_war_bulk,
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
CAREER_STATS_FRESH_DAYS = 0
ZONE_METRICS_FRESH_DAYS = 0
STATCAST_METRICS_FRESH_DAYS = 0

# How many CollegeSavant teams the NCAA box-score pass renders per run (densest
# tracked teams first). Bounded because each team is a headless-Chrome render;
# raise once the first run is validated. 0 disables the pass.
COLLEGESAVANT_MAX_TEAMS = 40


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


def rebuild_only(out_dir: Path = Path("data")) -> None:
    """Fast export-only path: ingest any FG drops, rebuild the timeseries
    from the current DB state, write `data/timeseries.json`. No scraping,
    no MLB API calls. Use after a fangraphs_csv drop when you don't want
    to wait through the full monthly pipeline."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("rebuild_only")
    init_db()
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
        log.exception("fangraphs_csv: drop-folder ingest failed — continuing")

    # Draft pipeline — promote any newly-drafted players + write the
    # draft_timeseries.json sidecar. Promotion is idempotent.
    try:
        from draft_promotion import promote_drafted_players
        from draft_export import export_draft_json
        promote_drafted_players()
        n_draft = export_draft_json(out_dir / "draft_timeseries.json")
        log.info("draft pipeline (rebuild): exported %d draft prospects", n_draft)
    except Exception:
        log.exception("draft pipeline crashed in rebuild_only — continuing")

    # Overseas pipeline — promote any newly-signed KBO/NPB players +
    # ingest any manual postings + write the overseas_timeseries.json
    # sidecar. Skips stats refresh on rebuild_only (that's a slow HTTP
    # path; only fires in the full main()).
    try:
        from overseas_promotion import promote_signed_players, ingest_postings
        from overseas_export import export_overseas_json
        ingest_postings()
        promote_signed_players()
        n_ov = export_overseas_json(out_dir / "overseas_timeseries.json")
        log.info("overseas pipeline (rebuild): exported %d overseas prospects", n_ov)
    except Exception:
        log.exception("overseas pipeline crashed in rebuild_only — continuing")

    log.info("rebuild_only: loading snapshots + ancillary tables from DB")
    all_snaps = load_all_snapshots()
    timeseries = build_timeseries(all_snaps)
    log.info("rebuild_only: built timeseries for %d players", len(timeseries))

    # Preserve the existing rosters_by_org sidecar — it's built at
    # scrape time during the full pipeline, so a rebuild-only pass would
    # otherwise clobber it with `{}` and break every farm-detail page.
    # Same pass-through applies to roster_status (used by per-prospect
    # 40-man / options state on the detail page) so we don't lose those
    # signals on every fast rebuild.
    existing_rosters: dict = {}
    rosters_path = out_dir / "rosters_by_org.json"
    if rosters_path.exists():
        try:
            with rosters_path.open(encoding="utf-8") as fp:
                existing_rosters = json.load(fp)
        except Exception:
            log.exception("rebuild_only: could not load existing rosters_by_org.json — "
                          "falling back to empty (farm-detail pages will be blank)")
    else:
        log.warning("rebuild_only: no existing rosters_by_org.json — farm-detail "
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
        # v30.7 — Rebuild-only was passing draft_pools={} (empty),
        # which made fin_draft_pool_efficiency return None for every
        # org → all 30 collapsed to a default 'C' grade. build_draft_pools
        # hits a 7-day on-disk cache for any year already scraped, so
        # the warm path is fast (no HTTP); cold years would scrape, but
        # the 2021-current run normally lives on disk. Failure here is
        # logged + swallowed to preserve the rebuild-doesn't-network
        # contract — fin_draft_pool_efficiency falls back to None
        # exactly as before.
        draft_pools=_load_draft_pools_for_rebuild(),
        player_ids={},
    )

    # International Amateurs sidecar — IFA signing classes (2021–current)
    # from the cached Spotrac tracker, enriched against the freshly-written
    # timeseries.json. Best-effort; a failure here must not abort the run.
    try:
        from ifa_export import export_ifa_json
        n_ifa = export_ifa_json(out_dir / "ifa_timeseries.json")
        log.info("ifa pipeline (rebuild): exported %d signings", n_ifa)
    except Exception:
        log.exception("ifa export crashed in rebuild_only — continuing")

    # CollegeSavant -> Single-A translation. Re-fits the matched-pair factors
    # against the just-refreshed Single-A statlines and rebuilds the per-player
    # sidecar (CS player pages) + the PROSPX draft bridge. Reads CollegeSavant's
    # vendored TrackMan data + the DB; the factor bands tighten as more
    # college->Single-A pairs accrue. Best-effort; a failure must not abort.
    try:
        from college_translation import build as _build_college_translation
        _ct = _build_college_translation(out_dir=out_dir)
        log.info("CollegeSavant translation (rebuild): %d factor blocks, %d draft-bridge entries",
                 len(_ct.get("factors", {})), _ct.get("bridge_count", 0))
    except Exception:
        log.exception("CollegeSavant translation crashed in rebuild_only — continuing")

    # Organization Tendencies — pure aggregation over the DB + the
    # just-rebuilt sidecars (timeseries, ifa, debuts). Best-effort.
    try:
        from org_tendencies import export as _export_ot
        _export_ot()
    except Exception:
        log.exception("org tendencies export crashed in rebuild_only — continuing")

    # xFV — our outcome-grounded grade. Regenerates the labeled training matrix +
    # the CURRENT active-board feature matrix from the just-written timeseries.json,
    # fits the model, scores both cohorts (live board gated on a pro track record),
    # and consolidates data/xfv.json (the site sidecar shown next to consensus FV).
    # The forward-chained backtest eval (registry artifact) is stable -> not re-run
    # here. Best-effort; a failure must not abort the run. Provisional grade.
    try:
        from xfv_export import regen_all as _regen_xfv
        _xfv = _regen_xfv()
        log.info("xFV (rebuild): %d players (%d live board) -> data/xfv.json",
                 _xfv["meta"]["n_players"], _xfv["meta"]["n_active"])
    except Exception:
        log.exception("xFV regen crashed in rebuild_only — continuing")

    # MiLB -> first-MLB rate translation (K% / BB%; matched-pair, LOO-validated).
    # Needs the xFV matrices (built above) + debuts.json. Best-effort.
    try:
        import milb_translation
        _mt = milb_translation.build()
        log.info("MiLB->MLB rate translation: %d fits -> data/milb_translation.json",
                 len(_mt["fits"]))
    except Exception:
        log.exception("milb_translation crashed in rebuild_only - continuing")

    # xFV PROXY — faster-resolving leading indicator (pre-debut profile -> first-MLB Statcast
    # quality), forward-validated on recent debut cohorts. Separate artifact, NOT xFV; pulls
    # Savant expected-stats (cached). Best-effort; a Savant outage must not abort the run.
    try:
        import xfv_proxy as _xfv_proxy
        _xp = _xfv_proxy.run()
        log.info("xFV proxy: hit r=%s / pit r=%s -> data/xfv_proxy_eval.json",
                 _xp["sides"].get("hit", {}).get("r"), _xp["sides"].get("pit", {}).get("r"))
    except Exception:
        log.exception("xFV proxy crashed in rebuild_only — continuing")

    # GRPO breakout scores — runs before trade values so scores can adjust FV priors.
    try:
        from grpo_prospect import export_grpo_scores
        _grads_for_grpo = json.loads((out_dir / "graduates.json").read_text()) \
            if (out_dir / "graduates.json").exists() else []
        _ts_for_grpo    = json.loads(out_path.read_text()).get("players") or []
        _grpo_result    = export_grpo_scores(
            _ts_for_grpo, _grads_for_grpo,
            out_path=out_dir / "grpo_scores.json",
            model_path=out_dir / "grpo_model.pkl",
            level_norms=json.loads(out_path.read_text()).get("level_norms"),
            retrain=True,
        )
        log.info("grpo: scored %d prospects", _grpo_result.get("scored", 0))
    except Exception:
        log.exception("grpo scoring failed in rebuild_only — continuing")

    # Bayesian trade values — runs after GRPO scores so priors are GRPO-informed.
    # Includes active prospects (timeseries.json), debuted players (debuts.json),
    # and full graduates (graduates.json) so the Trade Board is comprehensive.
    try:
        from bayes_trade_value import export_trade_values_json, _reset_cache
        _reset_cache()   # clear GRPO cache so new scores are loaded
        ts_payload = json.loads(out_path.read_text(encoding="utf-8"))
        tv_players = list(ts_payload.get("players") or [])
        lnorms     = ts_payload.get("level_norms")
        for _sidecar in ("debuts.json", "graduates.json"):
            _sp = out_dir / _sidecar
            if _sp.exists():
                tv_players += json.loads(_sp.read_text(encoding="utf-8"))
        n_tv = export_trade_values_json(tv_players, out_dir / "trade_values.json",
                                        level_norms=lnorms)
        log.info("trade values (rebuild): exported %d players", n_tv)
    except Exception:
        log.exception("trade value export crashed in rebuild_only — continuing")

    # Post-export sanity: surface what landed in the JSON so the user
    # doesn't have to grep the file.
    _post_export_summary(out_path, all_snaps, log)

    # Stamp run + data_freshness so a manual --rebuild-only produces the same
    # "as of" freshness block as daily/monthly runs (mirrors run_daily / main).
    _patch_export_run_summary(out_path, log)


def run_daily(out_dir: Path = Path("data"), workers: int | None = None,
              no_cache: bool = False) -> None:
    """DAILY fast-moving refresh — the time-sensitive subset of the pipeline.

    Pulls and updates the data that moves between monthly grade releases, so
    the outcome-grounded xFV grade (re-scored at the end via rebuild_only)
    tracks it day to day. Every input xFV consumes is refreshed here:
      • daily Live board captures (TJStats / MLB Pipeline) -> consensus FV
      • current-season stat lines (d5c) -> the MiLB rate features xFV uses
        (k_rel / obp_rel / ops_rel / era_rel, derived from the statline)
      • incremental Statcast metrics (d5d) -> the Statcast tilt, for players
        with newly tracked games at Statcast levels
      • Injured-List stints (+ append-only il_history) -> the injury tilt
      • player transactions, roster status, debuts & graduations, trades

    It then rebuilds data/timeseries.json from the refreshed DB via the
    no-scrape `rebuild_only()` path, which re-runs the xFV pipeline
    (xfv_export.regen_all) against the fresh consensus / stats / injuries, so a
    consensus move, a new stat line, or an IL change all flow into xFV the same
    night.

    The HEAVY, slow-HTTP work stays monthly in `main()`: full career-stat
    backfill, the full Statcast season scrape, the MLB-only sabermetrics
    endpoint (wRC+/xFIP, NOT an xFV input), scout-grade snapshots, Arkmetrics,
    farm grades, and the full ranking. run_daily and run_monthly run on
    different nights (deploy: `--daily` most nights, full on the 1st), so a row
    the daily incremental path writes is simply overwritten by the monthly full
    pass; never simultaneously. Every step is idempotent; a failure in one
    fetch logs and continues so a single flaky endpoint can't strand the run.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("run_daily")
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
        # --- d0. TJStats Live board (daily point-in-time capture) ---------
        # TJStats updates continuously, so a daily Live pull gives finer Time
        # Machine resolution AND keeps TJStats's present-day consensus contribution
        # fresh between monthly runs. Live only (named historical snapshots are a
        # monthly concern). Date-stamped label -> a same-day re-run updates in
        # place; a new day creates a new point-in-time row. Never aborts the run.
        with _step("d0. TJStats Live capture", log):
            try:
                import tjstats
                _tj = tjstats.run_tjstats_pipeline(live=True, history=False)
                if _tj.get("live"):
                    log.info("tjstats: daily Live %d players @ %s",
                             _tj["live"]["n_players"], _tj["live"]["captured_at"])
                    tjstats.export_movers()   # wire sidecar + source events
                elif _tj.get("health"):
                    log.error("tjstats: health check failed, skipped: %s", _tj["health"])
            except Exception:
                log.exception("tjstats daily capture crashed — continuing")

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
            except Exception:
                log.exception("mlb_pipeline daily capture crashed — continuing")

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
                from mlbam_ingest import ingest_unranked_active_prospects
                _mlbam_summary = ingest_unranked_active_prospects(season=season)
                _mlbam_total = sum(_mlbam_summary.values())
                if _mlbam_total:
                    log.info("mlbam_ingest: added %d new unranked prospects %s",
                             _mlbam_total, _mlbam_summary)
            except Exception:
                log.exception("mlbam_ingest: discovery step failed — continuing")

        with _step("d1. Build player set from DB", log):
            all_snaps = load_all_snapshots()
            timeseries = build_timeseries(all_snaps)
            log.info("daily: %d tracked players", len(timeseries))

        # --- 2. Resolve MLBAM IDs + PlayerIndex (disk-cached, fast). ------
        with _step("d2. Resolve IDs (warm PlayerIndex)", log):
            prospects = [(p.player_key, p.player_name, p.position) for p in timeseries]
            ids_by_key, _bds, player_index = bulk_resolve_ids(
                prospects, season=season, force_rebuild_index=no_cache,
            )

        # --- 3. Team affiliations (cached) — needed for level_changes. ----
        with _step("d3. Team affiliations", log):
            try:
                team_affil = fetch_team_affiliations(season)
            except Exception:
                log.exception("daily: team affiliations fetch failed — promotions "
                              "may be stale this run")
                team_affil = {}

        # --- 4. Transactions (promotions/demotions + move timeline). ------
        with _step("d4. Player transactions", log):
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
            try:
                il_mids = {p.player_key: ids_by_key.get(p.player_key)
                           for p in timeseries
                           if ids_by_key.get(p.player_key) is not None
                           and p.status != "debuted"}
                il_by_mid = bulk_fetch_il_status(il_mids.values())
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

        # --- 6. Roster status (fresh tx + cached career stats). -----------
        with _step("d6. Roster status", log):
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
            try:
                tracked = {p.player_key: (p.player_name, ids_by_key.get(p.player_key))
                           for p in timeseries}
                new_trades = detect_trades(all_snaps, tracked_players=tracked,
                                           skip_api=False)
                n_trades = insert_trades(new_trades)
                log.info("daily: detected %d trades (%d new)", len(new_trades), n_trades)
            except Exception:
                log.exception("daily: trade detection failed — continuing")

        # --- 9. Rebuild timeseries.json from the refreshed DB. ------------
        with _step("d9. Rebuild timeseries (no scrape)", log):
            rebuild_only(out_dir)

        # --- 10. FA signing-window tracker (Nov–Mar only). ----------------
        # In-winter the class moves daily (signings, option decisions, QO
        # acceptances), so the daily job re-scrapes the current class and
        # re-exports the fa_* sidecars. Outside the window the FA refresh
        # rides the monthly run only — June payrolls don't move daily.
        if date.today().month in (11, 12, 1, 2, 3):
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

        finish_run(run_id, new_snapshots=0, stat_lines=0,
                   notes=f"DAILY: {n_il} on IL, {n_debuts} debuts, {n_trades} new trades")
        # Patch the just-written run summary into timeseries.json so the
        # site's "as of" reflects this daily refresh.
        _patch_export_run_summary(out_dir / "timeseries.json", log)
        total = time.monotonic() - _run_start
        log.info("DAILY run %s complete in %.1fs", run_id, total)
        for label, secs in _STEP_TIMES:
            log.info("  %-34s %6.1fs", label, secs)
    except Exception:
        log.exception("DAILY run %s failed", run_id)
        finish_run(run_id, new_snapshots=0, stat_lines=0, notes="DAILY: failed")
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
        out = build_contracts_by_key(rows)
        log.info("%s: %d player-rows fetched, %d unique players", label, len(rows), len(out))
        return out
    except Exception:
        log.exception("%s: spotrac contracts scrape failed — falling back to manual overrides only", label)
        return {}


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


def main(force_refetch: bool = False, skip_stats: bool = False,
         out_dir: Path = Path("data"), workers: int | None = None,
         cache_ttl: int | None = None, no_cache: bool = False, fast: bool = False):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("run_monthly")
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
                    from draft_promotion import promote_drafted_players
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
                _new = insert_snapshots(snapshots)
                log.info("inserted %d new snapshot rows", _new)
                ingest_source_article_drops(out_dir, log)
                for key, bd in csv_birth_dates.items():
                    upsert_birth_date(key, bd)
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
                _tj = tjstats.run_tjstats_pipeline(live=True, history=True)
                if _tj.get("health"):
                    log.error("tjstats: health check failed, skipped ingest: %s", _tj["health"])
                elif _tj.get("live"):
                    log.info("tjstats: Live %d players @ %s + %d historical snapshot(s)",
                             _tj["live"]["n_players"], _tj["live"]["captured_at"],
                             len(_tj["history"]))
                    tjstats.export_movers()   # wire sidecar + source events
            except Exception:
                log.exception("tjstats pipeline crashed — continuing")

        # --- 2. Build consensus ----------------------------------------
        with _step("2. Build consensus timeseries", log):
            all_snaps = load_all_snapshots()
            timeseries = build_timeseries(all_snaps)
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
            )
            # overwrite=True because these dates are tied to a freshly-resolved
            # MLBAM ID; any pre-existing date in the DB may correspond to a
            # previously-cached wrong ID and is now stale.
            for key, bd in bds_from_index.items():
                upsert_birth_date(key, bd, overwrite=True)
            if bds_from_index:
                log.info("upserted %d birth dates from PlayerIndex", len(bds_from_index))

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
            il_by_mid = bulk_fetch_il_status(il_mids_by_key.values())
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
            tracked_by_mid[mid] = {
                "player_key": p.player_key,
                "fv_label": latest.consensus_fv_label if latest else None,
                "fv_raw":   latest.consensus_fv_raw   if latest else None,
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
                    from fielding_positions import build_positions_played
                    versa_input = [
                        {"player_key": p.player_key,
                         "mlbam_id": ids_by_key.get(p.player_key),
                         "statline": {"is_pitcher": _is_pitcher(p.position)}}
                        for p in timeseries
                        if p.status != "debuted" and ids_by_key.get(p.player_key)
                    ]
                    build_positions_played(versa_input, log_=log)
                except Exception:
                    log.exception("positions_played build failed — continuing")
        _step_3a_per_start = time.monotonic() if not skip_stats else None
        if not skip_stats:
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
                if (key in keys_with_bulk_2026
                        and not has_current_year_level_change
                        and len(career_cache.get(key, [])) > 1):
                    skipped_bulk += 1
                    continue
                if not force_refetch and _is_career_fresh(
                        career_meta.get(key), CAREER_STATS_FRESH_DAYS
                ) and not has_current_year_level_change:
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
                timeseries = build_timeseries(all_snaps)

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
                ]
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
                log.info("fetching sabermetrics (wRC+/xFIP) for %d players", len(all_active))
                new_sabermetrics: dict = {}
                sm_tasks: list[tuple[str, int, bool]] = [
                    (key, ids_by_key[key], is_p) for key, _name, is_p in all_active
                    if key in ids_by_key and ids_by_key[key] is not None
                ]
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
                # Uses pybaseball.batting_stats / pitching_stats once per
                # year in the window to pull FanGraphs WAR. The MLB Stats
                # API only exposes WAR via single-season sabermetrics calls,
                # so a per-player loop would cost ~2-4k extra requests on
                # a cold cache; the bulk FG pull is two calls per year.
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
                        # 10-year window covers every modern graduate.
                        # Older grads (rare) get truncated WAR but still
                        # surface a value.
                        try:
                            war_data = fetch_career_war_bulk(
                                war_targets,
                                start_year=season - 10,
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
                        from statcast_metrics import fetch_statcast_metrics_for_players
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
                        new_statcast_metrics = fetch_statcast_metrics_for_players(
                            statcast_players,
                            season,
                            # v25 — 10 → 16. Statcast is the longest-running
                            # step in a cold full run (~56s); more workers
                            # cuts it materially.
                            workers=workers or 16,
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
            if rs.get("mlb_debut_date"):
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
                               player_ids=ids_by_key)
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
        _STEP_TIMES.append(("5. Export timeseries.json + summary", time.monotonic() - _step_5_start))

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
            try:
                from proj_export import export as _export_proj
                _export_proj()
            except Exception:
                log.exception("mlb projections export failed — continuing")

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

        # --- 6b3. MLB player detail export (player pages) ----------------
        # The /projections/#player= + FA-card-linked per-player payloads:
        # careers (StatsAPI + war_daily), Savant percentiles, arsenals,
        # Swing+, AAA Stuff+, FA market fields. Reads the exports above.
        with _step("6b3. MLB player detail export (mlb_player_detail.json)", log):
            try:
                from mlb_player_export import export as _export_mlbp
                _export_mlbp()
            except Exception:
                log.exception("mlb player detail export failed — continuing")

        # --- 6c. Organization Tendencies (farm-detail Tendencies tab) ---
        # Pure aggregation over the DB + just-written sidecars; additive.
        with _step("6c. Org tendencies export (org_tendencies.json)", log):
            try:
                from org_tendencies import export as _export_ot
                _export_ot()
            except Exception:
                log.exception("org tendencies export failed — continuing")

        # --- 6d. Bayesian trade values (data/trade_values.json) ---
        with _step("6d. Bayesian trade value export (trade_values.json)", log):
            try:
                from bayes_trade_value import export_trade_values_json
                _ts_payload = json.loads(out_path.read_text(encoding="utf-8"))
                _tv_players = list(_ts_payload.get("players") or [])
                _lnorms     = _ts_payload.get("level_norms")
                for _sc in ("debuts.json", "graduates.json"):
                    _sp = out_dir / _sc
                    if _sp.exists():
                        _tv_players += json.loads(_sp.read_text(encoding="utf-8"))
                _n_tv = export_trade_values_json(
                    _tv_players, out_dir / "trade_values.json", level_norms=_lnorms
                )
                log.info("trade values: exported %d players", _n_tv)
                # Snapshot the board surplus values so a TRUE forward backtest of
                # the Trade Machine becomes possible (the eval is rank-only today
                # because trade_values.json was never snapshotted). Cannot be
                # back-filled; the track record begins this run. Idempotent.
                try:
                    _tv_written = json.loads((out_dir / "trade_values.json").read_text(encoding="utf-8"))
                    _n_tvh = snapshot_trade_values(_tv_written.get("players") or [])
                    log.info("trade_value_history: snapshotted %d board records", _n_tvh)
                except Exception:
                    log.exception("trade_value snapshot failed — continuing")
            except Exception:
                log.exception("trade value export failed — continuing")

        finish_run(run_id, new_snapshots=new_count, stat_lines=stat_count,
                   notes=f"{len(timeseries)} players, {len(new_trades)} trades")
        _patch_export_run_summary(out_path, log)
        # Capture the DERIVED board state (consensus rank/FV + Arkmetric
        # family) for the active board so the time-travel board (Part 2) and
        # the Arkmetric-vs-outcome backtest (Part 4) accrue monthly history.
        # Monthly-only: the daily job does NOT snapshot here (grades/rankings
        # only change on the monthly cadence). Idempotent (upsert-by-date).
        try:
            _ts = json.loads(out_path.read_text(encoding="utf-8"))
            _n_metric = snapshot_board_metrics(_ts.get("players") or [])
            log.info("metric_snapshots: captured board state for %d players", _n_metric)
            # Org-grain sibling: record the composite farm_rank so farm-system
            # rank movement accrues a server-side history (the de-noised
            # movement engine reads it on the NEXT export). Monthly-only, same
            # as the board snapshot above; idempotent upsert-by-(org, date).
            _n_farm = snapshot_farm_ranks(_ts.get("org_summary") or [])
            log.info("farm_rank_history: captured rank for %d orgs", _n_farm)
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
        # Editorial forward-validation (Phase 5 WS-10). Scores matured
        # 30/60-day flag cohorts vs matched controls; WITHHOLDS the
        # artifact until the first cohort matures (registry honesty —
        # an empty eval would let spotlights masquerade as measured).
        # NB once it first writes data/editorial_eval.json, the standing
        # rule test goes red until the owner registers the verdict —
        # that forcing function is the design.
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
        except Exception:
            log.exception("model registry refresh failed — continuing")
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
        # biggest wall-time culprits surface at the top of the log.
        _log_step_summary(log, time.monotonic() - _run_start)
        # The monthly run also performs the DAILY fast-moving refresh
        # (transactions, IL, roster status, debuts/graduations, trades) so a
        # plain `python run_monthly.py` never leaves them stale — the Injured
        # List section in particular ONLY moves on the daily job, so without
        # this a monthly-only cadence froze it between nightly runs. Runs after
        # the monthly grade work so the rebuilt timeseries carries both the
        # fresh monthly grades and the up-to-the-day transactions/IL. Best-effort
        # + self-contained (own run_id + timeseries rebuild); a daily-side
        # failure must not fail the already-completed monthly run.
        try:
            log.info("monthly run: chaining the daily fast-moving refresh")
            run_daily(out_dir=out_dir, workers=workers, no_cache=no_cache)
        except Exception:
            log.exception("chained daily refresh failed — monthly run already completed")
    except Exception:
        log.exception("run failed")
        finish_run(run_id, new_snapshots=new_count, stat_lines=stat_count,
                   notes="FAILED — see logs")
        # Still print the partial step summary on crash — useful for
        # debugging which phase blew up.
        _log_step_summary(log, time.monotonic() - _run_start)
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
    args = ap.parse_args()
    if args.dry_run:
        probe(force=args.force)
        sys.exit(0)
    if args.daily:
        run_daily(out_dir=args.out_dir, workers=args.workers, no_cache=args.no_cache)
        sys.exit(0)
    if args.rebuild_only:
        rebuild_only(out_dir=args.out_dir)
        sys.exit(0)
    main(force_refetch=args.force, skip_stats=args.skip_stats, out_dir=args.out_dir,
         workers=args.workers, cache_ttl=args.cache_ttl, no_cache=args.no_cache,
         fast=args.fast)

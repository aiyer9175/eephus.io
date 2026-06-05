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
    """Refresh boot JSON's run summary after finish_run() has completed."""
    try:
        payload = json.loads(out_path.read_text(encoding="utf-8"))
        payload["run"] = latest_run_summary()
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


# v24 — Freshness gates dropped to 0 so every run refetches stats,
# debuts, zone metrics, and statcast metrics. The 24h HTTP cache in
# stats.py still absorbs duplicate-payload cost on same-day re-runs;
# this just stops the per-player skip from short-circuiting the API
# pass. --force is now a no-op for these gates (kept for HTTP cache).
CAREER_STATS_FRESH_DAYS = 0
ZONE_METRICS_FRESH_DAYS = 0
STATCAST_METRICS_FRESH_DAYS = 0


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

    # Post-export sanity: surface what landed in the JSON so the user
    # doesn't have to grep the file.
    _post_export_summary(out_path, all_snaps, log)


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
    from datetime import date as _date
    season = _date.today().year
    try:
        team_affil = fetch_team_affiliations(season)
    except Exception as e:
        _log.warning("team_affil fetch failed (%s) — promotions will be "
                     "unlabeled by level", e)
        team_affil = {}
    out: dict = {}
    for key, tx_rows in tx_cache.items():
        try:
            evs = derive_level_changes(tx_rows, team_affil)
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
                    for y in range(2021, this_year + 1):
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

        # --- 2b. Bulk fetch draft data for the rolling window of years a
        # current prospect could plausibly have been drafted in. One call
        # per year (~10 total) returns thousands of picks each; matching to
        # tracked prospects happens in-memory via mlbam_id. Players with no
        # draft match are labeled 'international_fa' since the user's
        # convention is to treat undrafted prospects as IFA signings.
        # /draft/{year} payloads are cached on disk for 30 days, so reruns
        # within a month cost nothing beyond reading the local cache.
        with _step("2b. Bulk fetch draft data (10-year window)", log):
            draft_years = list(range(season - 9, season + 1))
            log.info("fetching draft picks for years %s", draft_years)
            draft_by_id = bulk_fetch_drafts(draft_years)

        acquisitions: dict[str, dict] = {}
        ifa_mids_by_key: dict[str, int] = {}
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
                # No draft record across the lookback window — treat as IFA.
                # We enrich below with the original signing transaction.
                ifa_mids_by_key[p.player_key] = mid
                acquisitions[p.player_key] = {
                    "method":       "international_fa",
                    "year":         None,
                    "round_label":  None,
                    "pick_round":   None,
                    "pick_overall": None,
                    "bonus_usd":    None,
                    "team_name":    None,
                    "school":       None,
                    "signing_date": None,
                }

        # --- 2b.ii Enrich IFA records with original signing transaction.
        # One /transactions call per IFA prospect returns the SFA/SGN event
        # that records the signing team + date. The MLB Stats API doesn't
        # publish signing-bonus dollars; we layer in Spotrac (below) to
        # fill the bonus_usd field where they have a row for the player.
        with _step("2b.ii. IFA signing enrichment (MLB transactions)", log):
            if ifa_mids_by_key:
                log.info("fetching IFA signing info for %d prospects",
                         len(ifa_mids_by_key))
                ifa_by_id = bulk_fetch_ifa_signings(ifa_mids_by_key.values())
                n_enriched = 0
                for key, mid in ifa_mids_by_key.items():
                    sig = ifa_by_id.get(mid)
                    if not sig:
                        continue
                    rec = acquisitions[key]
                    rec["year"]         = sig.get("year")
                    rec["team_name"]    = sig.get("team_name")
                    rec["signing_date"] = sig.get("signing_date")
                    n_enriched += 1
                log.info("IFA enrichment: %d/%d signings resolved",
                         n_enriched, len(ifa_mids_by_key))

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
            # Merge: a two-way player would show in both endpoints; pick
            # the highest-level row (LEVEL_ORDER index ascending).
            from stats import LEVEL_ORDER
            bulk_by_mlbam: dict[int, dict] = dict(bulk_hitting)
            for pid, row in bulk_pitching.items():
                existing = bulk_by_mlbam.get(pid)
                if (existing is None
                        or LEVEL_ORDER.index(row["level"])
                        < LEVEL_ORDER.index(existing["level"])):
                    bulk_by_mlbam[pid] = row
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
            cs_tasks: list[tuple[str, int, bool]] = []
            skipped_fresh = 0
            skipped_bulk = 0
            for key, _name, is_p in non_grad_players:
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
                "fetching career stats for %d players (skipped %d graduated, "
                "%d covered-by-bulk, %d fresh-cached, %d unresolved)",
                len(cs_tasks),
                len(timeseries) - len(non_grad_players),
                skipped_bulk,
                skipped_fresh,
                len(non_grad_players) - skipped_bulk - skipped_fresh - len(cs_tasks),
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
        for key, tx_rows in tx_cache.items():
            evs = derive_level_changes(tx_rows, team_affil)
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

        finish_run(run_id, new_snapshots=new_count, stat_lines=stat_count,
                   notes=f"{len(timeseries)} players, {len(new_trades)} trades")
        _patch_export_run_summary(out_path, log)
        # v19 — Per-step duration table. Sorted by slowest first so the
        # biggest wall-time culprits surface at the top of the log.
        _log_step_summary(log, time.monotonic() - _run_start)
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
    args = ap.parse_args()
    if args.dry_run:
        probe(force=args.force)
        sys.exit(0)
    if args.rebuild_only:
        rebuild_only(out_dir=args.out_dir)
        sys.exit(0)
    main(force_refetch=args.force, skip_stats=args.skip_stats, out_dir=args.out_dir,
         workers=args.workers, cache_ttl=args.cache_ttl, no_cache=args.no_cache,
         fast=args.fast)

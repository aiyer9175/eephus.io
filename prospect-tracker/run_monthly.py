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
import logging
import sys
from datetime import date
import concurrent.futures
from pathlib import Path

from scrapers import scrape_all, probe
from storage import (
    init_db, insert_snapshots, start_run, finish_run,
    load_all_snapshots, load_statlines, upsert_statlines,
    insert_trades, load_trades,
    upsert_birth_date, load_birth_dates,
    auto_graduate_player,
    upsert_pitch_arsenals, load_pitch_arsenals,
    upsert_statcast_metrics, load_statcast_metrics,
    upsert_career_stats, load_career_stats,
    export_timeseries_json,
)
from consensus import build_timeseries
from stats import (fetch_statlines_for, resolve_mlbam_id, fetch_birth_date,
                   fetch_birth_date_by_name,
                   fetch_pitch_arsenal, fetch_statcast_metrics,
                   fetch_career_stats,
                   bulk_resolve_ids,
                   detect_graduations_from_career,
                   PlayerIndex)
from trades import detect_trades


def _is_pitcher(position: str | None) -> bool:
    if not position:
        return False
    return any(p in position.upper() for p in ("RHP", "LHP", "SP", "RP"))


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

    try:
        # --- 0. Fix encoding in CSV ----------------------------------------
        import subprocess
        result = subprocess.run([sys.executable, "fix_encoding.py"],
                              capture_output=True, text=True, cwd=Path(__file__).parent)
        if result.returncode == 0:
            log.info(result.stdout.strip())
        else:
            log.warning("encoding fix script failed: %s", result.stderr)

        # --- 1. Scrape & store rankings ---------------------------------
        snapshots, csv_birth_dates = scrape_all(force=force_refetch)
        log.info("scraped %d total snapshot rows", len(snapshots))
        new_count = insert_snapshots(snapshots)
        log.info("inserted %d new snapshot rows", new_count)

        # Persist any birth dates supplied directly via the CSV. These win
        # over API-fetched dates for any player they cover.
        for key, bd in csv_birth_dates.items():
            upsert_birth_date(key, bd)
        if csv_birth_dates:
            log.info("upserted %d birth dates from CSV", len(csv_birth_dates))

        # --- 2. Build consensus ----------------------------------------
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
        all_prospects_for_resolve = [
            (p.player_key, p.player_name, p.position)
            for p in timeseries
        ]
        log.info("bulk resolving IDs + birth dates for %d prospects",
                 len(all_prospects_for_resolve))
        _ids_resolved, bds_from_index = bulk_resolve_ids(
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

        # --- 3a. Fetch career year-by-year stats EARLY so they can drive
        #         the bulk graduation pass below — no per-prospect career
        #         API calls needed. Replaces 1-30 sequential
        #         /people/{id}/stats?stats=career calls from the previous
        #         bulk_detect_graduations implementation with one parallel
        #         pre-fetch we'd be doing anyway.
        career_cache = load_career_stats()
        statlines = load_statlines()
        if not skip_stats:
            all_players = [
                (p.player_key, p.player_name, _is_pitcher(p.position))
                for p in timeseries
            ]
            log.info("fetching career year-by-year stats for %d players",
                     len(all_players))
            new_career: dict = {}
            cs_tasks: list[tuple[str, int, bool]] = []
            for key, name, is_p in all_players:
                mlbam = resolve_mlbam_id(key, name)
                if mlbam is None:
                    continue
                cs_tasks.append((key, mlbam, is_p))
            if cs_tasks:
                if workers is not None:
                    max_workers = max(1, min(workers, len(cs_tasks)))
                else:
                    max_workers = min(16, max(1, len(cs_tasks)))
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

        # --- 3b. Bulk graduation detection from career_stats (no API I/O) -
        # Sums MLB-level rows from career_stats we just fetched. Identifies
        # any prospect who has crossed the 130-AB / 50-IP rookie threshold.
        # Replaces the per-prospect /people/{id}/stats?stats=career calls
        # the old bulk_detect_graduations made.
        active_for_grad = [
            (p.player_key, p.player_name, _is_pitcher(p.position))
            for p in timeseries if p.status != "graduated"
        ]
        log.info("bulk graduation check: %d non-graduated prospects",
                 len(active_for_grad))
        player_index = PlayerIndex.load_or_build(season)
        graduates_found = detect_graduations_from_career(
            career_cache, active_for_grad, player_index=player_index,
        )
        if graduates_found:
            for pkey, debut_date in graduates_found.items():
                auto_graduate_player(pkey, grad_date=debut_date)
            log.info("auto-graduated %d players from career-stats sum",
                     len(graduates_found))
            # Rebuild timeseries so subsequent steps see correct status
            all_snaps = load_all_snapshots()
            timeseries = build_timeseries(all_snaps)

        # --- 3c. Fetch stat lines (current-season top-level digest) ------
        if not skip_stats:
            # Rebuild after graduation rebuild above
            all_players = [
                (p.player_key, p.player_name, _is_pitcher(p.position))
                for p in timeseries
            ]
            log.info("fetching stat lines for %d prospects (all levels)",
                     len(all_players))
            new_statlines = fetch_statlines_for(all_players, season, max_workers=workers)
            stat_count = upsert_statlines(new_statlines, season)
            log.info("upserted %d stat lines", stat_count)
            for k, sl in new_statlines.items():
                from dataclasses import asdict
                statlines[k] = asdict(sl)

            # Auto-graduation: if an active prospect's stat line came back
            # at MLB level, mark them graduated in the DB immediately.
            # Their graduation_date will be today (approximate — the exact
            # date is whenever they first exceeded the rookie threshold, but
            # we don't track that here; a manual CSV row can correct it).
            auto_grads: list[str] = []
            for p in timeseries:
                if p.status == "graduated":
                    continue  # already graduated, skip
                sl = new_statlines.get(p.player_key)
                if sl and sl.level == "MLB":
                    log.warning(
                        "AUTO-GRADUATING %s — detected at MLB level",
                        p.player_name,
                    )
                    # grad_date=None → uses today; bulk detection already
                    # provides accurate debut dates for most cases
                    auto_graduate_player(p.player_key, grad_date=None)
                    auto_grads.append(p.player_name)

            if auto_grads:
                log.info("Auto-graduated %d players: %s",
                         len(auto_grads), ", ".join(auto_grads))
                # Rebuild timeseries so the export reflects the new statuses
                all_snaps = load_all_snapshots()
                timeseries = build_timeseries(all_snaps)

            # 3b. Pitch arsenals (pitchers only) + Statcast metrics (all)
            # Both are best-effort: many MiLB players won't have data,
            # especially below AA. We fetch and silently skip on None.
            # --fast skips both — they're the slowest stage of the pipeline
            # and aren't needed for consensus-FV iteration during dev.
            arsenals = load_pitch_arsenals()
            statcast = load_statcast_metrics()

            if fast:
                log.info("--fast: skipping pitch arsenals + Statcast metrics")
            else:
                pitchers = [(p.player_key, p.player_name)
                            for p in timeseries if _is_pitcher(p.position)]
                hitters  = [(p.player_key, p.player_name)
                            for p in timeseries if not _is_pitcher(p.position)]

                log.info("fetching pitch arsenals for %d pitchers", len(pitchers))
                new_arsenals: dict = {}
                pa_tasks: list[tuple[str, int]] = []
                for key, name in pitchers:
                    mlbam = resolve_mlbam_id(key, name)
                    if mlbam is None:
                        continue
                    pa_tasks.append((key, mlbam))
                if pa_tasks:
                    if workers is not None:
                        max_workers = max(1, min(workers, len(pa_tasks)))
                    else:
                        max_workers = min(10, max(1, len(pa_tasks)))
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

                log.info("fetching Statcast metrics for %d players", len(all_players))
                new_statcast: dict = {}
                sc_tasks: list[tuple[str, int, bool]] = []
                for key, name, is_p in all_players:
                    mlbam = resolve_mlbam_id(key, name)
                    if mlbam is None:
                        continue
                    sc_tasks.append((key, mlbam, is_p))
                if sc_tasks:
                    if workers is not None:
                        max_workers = max(1, min(workers, len(sc_tasks)))
                    else:
                        max_workers = min(16, max(1, len(sc_tasks)))
                    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                        future_to_key = {
                            ex.submit(fetch_statcast_metrics, key, mlbam, season, is_pitcher=is_p): key
                            for key, mlbam, is_p in sc_tasks
                        }
                        for fut in concurrent.futures.as_completed(future_to_key):
                            key = future_to_key[fut]
                            try:
                                sc = fut.result()
                                if sc:
                                    new_statcast[key] = sc
                            except Exception as e:
                                log.debug("statcast fetch failed for %s: %s", key, e)
                if new_statcast:
                    upsert_statcast_metrics(new_statcast, season)
                    for k, sc in new_statcast.items():
                        from dataclasses import asdict
                        statcast[k] = asdict(sc)
                log.info("fetched Statcast metrics for %d players", len(new_statcast))

                # Career stats already fetched up in step 3a; nothing more
                # to do here.

        else:
            arsenals = load_pitch_arsenals()
            statcast = load_statcast_metrics()


        # The org-change inference always runs (it's just a walk over the
        # snapshots we already have). The MLB API call is skipped if
        # --skip-stats was passed, since both depend on external HTTP.
        tracked = {}
        if not skip_stats:
            for p in timeseries:
                tracked[p.player_key] = (p.player_name,
                                          resolve_mlbam_id(p.player_key, p.player_name))
        new_trades = detect_trades(all_snaps, tracked_players=tracked,
                                    skip_api=skip_stats)
        trade_count = insert_trades(new_trades)
        log.info("detected %d trades (%d new)", len(new_trades), trade_count)
        trades_by_player = load_trades()

        # --- 5. Export -------------------------------------------------
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "timeseries.json"
        export_timeseries_json(timeseries, out_path,
                               statlines=statlines,
                               pitch_arsenals=arsenals,
                               statcast_metrics=statcast,
                               trades_by_player=trades_by_player,
                               career_stats=load_career_stats())
        log.info("wrote %s", out_path)

        finish_run(run_id, new_snapshots=new_count, stat_lines=stat_count,
                   notes=f"{len(timeseries)} players, {len(new_trades)} trades")
    except Exception:
        log.exception("run failed")
        finish_run(run_id, new_snapshots=new_count, stat_lines=stat_count,
                   notes="FAILED — see logs")
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
    args = ap.parse_args()
    if args.dry_run:
        probe(force=args.force)
        sys.exit(0)
    main(force_refetch=args.force, skip_stats=args.skip_stats, out_dir=args.out_dir,
         workers=args.workers, cache_ttl=args.cache_ttl, no_cache=args.no_cache,
         fast=args.fast)

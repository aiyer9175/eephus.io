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
    upsert_career_stats, load_career_stats, load_career_stats_meta,
    upsert_acquisitions, load_acquisitions,
    export_timeseries_json,
)
from consensus import build_timeseries
from stats import (fetch_statlines_for, fetch_birth_date,
                   fetch_birth_date_by_name,
                   fetch_pitch_arsenal, fetch_statcast_metrics,
                   fetch_career_stats,
                   bulk_resolve_ids,
                   detect_graduations_from_career,
                   bulk_fetch_drafts,
                   fetch_team_affiliations,
                   PlayerIndex)
from trades import detect_trades


# How long a cached career_stats row stays fresh before we refetch on the
# next run. Monthly cadence + 7-day window means a normal monthly run
# always refetches, while dev iterations within a week reuse the cache.
CAREER_STATS_FRESH_DAYS = 7


def _is_pitcher(position: str | None) -> bool:
    if not position:
        return False
    return any(p in position.upper() for p in ("RHP", "LHP", "SP", "RP"))


def _is_career_fresh(fetched_at: str | None, max_age_days: int) -> bool:
    """True if a career_stats row is younger than max_age_days."""
    if not fetched_at:
        return False
    try:
        from datetime import datetime as _dt
        # storage writes via datetime('now') which produces 'YYYY-MM-DD HH:MM:SS'.
        ts = _dt.fromisoformat(fetched_at.replace(" ", "T"))
    except ValueError:
        return False
    return (_dt.utcnow() - ts).days < max_age_days


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
        draft_years = list(range(season - 9, season + 1))
        log.info("fetching draft picks for years %s", draft_years)
        draft_by_id = bulk_fetch_drafts(draft_years)

        acquisitions: dict[str, dict] = {}
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
                # Bonus + signing_date stay unknown unless future enrichment
                # surfaces them.
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
        if acquisitions:
            upsert_acquisitions(acquisitions)
            n_draft = sum(1 for a in acquisitions.values() if a["method"] == "draft")
            log.info("acquisitions: %d draft, %d IFA",
                     n_draft, len(acquisitions) - n_draft)

        # --- 2c. Affiliate roster map. ~6 HTTP calls (one per sport level)
        # returns every MLB + MiLB team with its parent_org_id, which lets
        # us group the PlayerIndex by (parent_org_abbr, level) to build
        # full affiliate rosters for the farm-system page. Builds the
        # roster structure here so storage.export_timeseries_json stays a
        # pure serializer.
        log.info("fetching team affiliations for season %d", season)
        team_affil = fetch_team_affiliations(season)

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

        # Build {org_abbr: {level: [player_records]}}
        rosters_by_org: dict[str, dict[str, list[dict]]] = {}
        for rec in player_index.players:
            tid = rec.get("current_team_id")
            if not tid:
                continue
            info = team_affil.get(int(tid))
            if not info:
                continue
            org_abbr = info.get("parent_org_abbr") or ""
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

        # --- 3a. Fetch career year-by-year stats. Three filters narrow the
        # set we actually hit the network for:
        #   (1) skip already-graduated prospects (their career is frozen)
        #   (2) skip prospects whose cached row is < CAREER_STATS_FRESH_DAYS old
        #       unless --force is set (lets dev iterations within a week reuse
        #       the cache; monthly runs always refetch)
        #   (3) skip prospects with no resolved MLBAM ID
        # Each prospect now costs one HTTP call (combined mlb_milb endpoint
        # in fetch_career_stats) instead of two, halving traffic again.
        career_cache = load_career_stats()
        career_meta = load_career_stats_meta()
        statlines = load_statlines()
        if not skip_stats:
            non_grad_players = [
                (p.player_key, p.player_name, _is_pitcher(p.position))
                for p in timeseries if p.status != "graduated"
            ]
            cs_tasks: list[tuple[str, int, bool]] = []
            skipped_fresh = 0
            for key, _name, is_p in non_grad_players:
                mlbam = ids_by_key.get(key)
                if mlbam is None:
                    continue
                if not force_refetch and _is_career_fresh(
                        career_meta.get(key), CAREER_STATS_FRESH_DAYS):
                    skipped_fresh += 1
                    continue
                cs_tasks.append((key, mlbam, is_p))
            log.info(
                "fetching career stats for %d players (skipped %d graduated, "
                "%d fresh-cached, %d unresolved)",
                len(cs_tasks),
                len(timeseries) - len(non_grad_players),
                skipped_fresh,
                len(non_grad_players) - skipped_fresh - len(cs_tasks),
            )
            new_career: dict = {}
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

        # --- 3b. Fetch current-season stat lines (top-level digest) -------
        # Skips already-graduated prospects since their graduation snapshot
        # already exists; the existing statlines row in the DB is preserved
        # for the export.
        if not skip_stats:
            non_grad_for_statlines = [
                (p.player_key, p.player_name, _is_pitcher(p.position))
                for p in timeseries if p.status != "graduated"
            ]
            log.info("fetching stat lines for %d non-graduated prospects (all levels)",
                     len(non_grad_for_statlines))
            new_statlines = fetch_statlines_for(
                non_grad_for_statlines, season,
                max_workers=workers, id_cache=ids_by_key,
            )
            stat_count = upsert_statlines(new_statlines, season)
            log.info("upserted %d stat lines", stat_count)
            for k, sl in new_statlines.items():
                from dataclasses import asdict
                statlines[k] = asdict(sl)
        else:
            new_statlines = {}

        # --- 3c. Single graduation pass: career-threshold + current-season
        # MLB-statline, both in-memory. Merges the prior per-player auto-grad
        # loop into one detect_graduations_from_career call. Pre-filters
        # candidates by PlayerIndex.mlbDebutDate so we only run the
        # threshold sum on prospects who actually have an MLB debut on
        # record (typically <50 of ~3000 active players).
        active_for_grad = [
            (p.player_key, p.player_name, _is_pitcher(p.position))
            for p in timeseries if p.status != "graduated"
        ]
        graduates_found = detect_graduations_from_career(
            career_cache, active_for_grad,
            player_index=player_index,
            id_cache=ids_by_key,
            statlines=new_statlines or None,
        )
        if graduates_found:
            for pkey, debut_date in graduates_found.items():
                auto_graduate_player(pkey, grad_date=debut_date)
            log.info("auto-graduated %d players (career-threshold + MLB statline)",
                     len(graduates_found))
            # Rebuild timeseries once so subsequent steps + export see the
            # correct statuses.
            all_snaps = load_all_snapshots()
            timeseries = build_timeseries(all_snaps)

        # --- 3d. Pitch arsenals (pitchers) + Statcast metrics (everyone).
        # Both are best-effort: many MiLB players won't have data, especially
        # below AA. --fast skips both for dev iteration.
        arsenals = load_pitch_arsenals()
        statcast = load_statcast_metrics()
        if not skip_stats:
            if fast:
                log.info("--fast: skipping pitch arsenals + Statcast metrics")
            else:
                pitchers = [(p.player_key, p.player_name)
                            for p in timeseries
                            if _is_pitcher(p.position) and p.status != "graduated"]
                all_active = [(p.player_key, p.player_name, _is_pitcher(p.position))
                              for p in timeseries if p.status != "graduated"]

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

                log.info("fetching Statcast metrics for %d players", len(all_active))
                new_statcast: dict = {}
                sc_tasks: list[tuple[str, int, bool]] = [
                    (key, ids_by_key[key], is_p) for key, _name, is_p in all_active
                    if key in ids_by_key and ids_by_key[key] is not None
                ]
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


        # Trade detection. The org-change inference always runs (just walks
        # snapshots we already have); the MLB API path is skipped under
        # --skip-stats. tracked_players is built directly from ids_by_key,
        # avoiding the per-player resolve_mlbam_id loop the previous version
        # ran here.
        tracked = {}
        if not skip_stats:
            for p in timeseries:
                tracked[p.player_key] = (p.player_name, ids_by_key.get(p.player_key))
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
                               career_stats=load_career_stats(),
                               acquisitions=load_acquisitions(),
                               rosters_by_org=rosters_by_org)
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

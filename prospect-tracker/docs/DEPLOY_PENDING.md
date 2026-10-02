# Deploy steps deferred under the owner's DEPLOY-3 ruling (2026-10-01): one dated line per step, run at the next sync.

- 2026-10-02 STATS_PA_PIPELINE: at the next beta sync the box nightly's new step d5f (run_monthly.run_daily) migrates the box's prospects.db career_stats forward only, writing pa_measured onto MLB hitter rows from the box's .cache/fa_statsapi_hitting_<season>.json; after the first nightly, check the log line 'daily: measured MLB PA: ...' (local run filled 2,090 of 2,552 rows) and that data/debuts_lite.json MLB rows carry pa_measured.

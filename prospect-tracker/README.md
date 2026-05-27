# MLB PROSPX (Alpha v0.1)

## Install

```bash
pip install -r requirements.txt
```

## Run the pipeline

```bash
python run_monthly.py
```

Flags:

```bash
python run_monthly.py --skip-stats   # skip MLB / MiLB stat fetches
python run_monthly.py --force        # bypass HTTP + DB freshness cache
python run_monthly.py --dry-run      # diagnostic; no DB writes, no export
python run_monthly.py --workers 8    # cap thread-pool size
python run_monthly.py --out-dir path # write data/*.json elsewhere
```

## Serve locally

```bash
python -m http.server 8000
# open http://localhost:8000/
```

## Run tests

```bash
python -m pytest -q
```

## Edit the prospect lists

```
data/manual_rankings.csv
```

Columns: `source,snapshot_date,interval_label,player_name,position,org,rank,fv,status,birth_date`

Valid `source`: `fangraphs`, `espn`, `just_baseball`, `tjstats`, `baseball_america`, `mlb_pipeline`, `the_athletic`.
Valid `status`: `active`, `graduated`, `injured_list`, `off_list`.

## Deploy (GitHub Pages)

One-time:

```
Repo Settings → Pages → Source: GitHub Actions
```

Subsequent deploys: push to `main`, run the workflow manually, or wait for the monthly cron.

```bash
gh workflow run deploy-prospect-tracker.yml
```

## Files

```
prospect-tracker/
├── index.html                 # the site
├── data/manual_rankings.csv   # source of truth (edit by hand)
├── data/timeseries.json       # boot payload (generated)
├── data/graduates.json        # lazy slice (generated)
├── data/inactive.json         # lazy slice (generated)
├── data/rosters_by_org.json   # lazy slice (generated)
├── prospects.db               # SQLite cache (regenerable)
├── run_monthly.py             # pipeline entry point
├── consensus.py               # FV grid + unweighted aggregation
├── stats.py                   # MLB Stats API + BBRef WAR fetchers
├── trades.py                  # MLB transactions API + org-change inference
├── storage.py                 # SQLite schema + JSON export
├── scrapers.py                # CSV ingest + diagnostic probe
├── spotlights.py              # heat / arc / surprise buckets
├── prospect_savant.py         # Baseball Savant CSV attach
├── spotrac.py                 # IFA spending scrape
├── eta.py                     # MLB ETA projection
├── stat_flags.py              # red / green flag detection
├── level_norms.py             # empirical level baselines
├── age_level.py               # age-vs-level tiers
└── test_*.py                  # 198 tests
```

---

## Copyright & License

Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
Unauthorized copying of this file, via any medium is strictly prohibited
Proprietary and confidential
Written by Noah J. Dengler (@ARKNDJL), 2026

See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md) for full terms.

# Prospect Tracker — Running the Pipeline

## Current Setup

Your pipeline now uses:
- **Just Baseball HTML scraper** — Only web scraper (working)
- **Manual CSV input** — For FanGraphs, ESPN, MLB Pipeline, TJStats, etc.

All other scrapers (FanGraphs API, Baseball America, TJStats) are disabled.

## Quick Start

### Full monthly run
```bash
python run_monthly.py
```

This will:
1. Fetch data from Just Baseball + manual CSV
2. Build consensus rankings across all snapshots
3. Fetch MiLB stat lines for all tracked prospects
4. Detect trades and auto-graduate to MLB
5. Export `data/timeseries.json` for the website

### Dry run (test without DB writes)
```bash
python run_monthly.py --dry-run
```

Shows:
- Just Baseball scraper status
- Manual CSV rows loaded from `manual_rankings.csv` in the project root

### Skip stats (faster local testing)
```bash
python run_monthly.py --skip-stats
```

Builds consensus and exports without fetching external stat lines.

## Using the Manual CSV

The CSV format is:
```
source,snapshot_date,interval_label,player_name,position,org,rank,fv,status,birth_date
fangraphs,2026-05-17,FG 2026 Report,Konnor Griffin,SS,PIT,1,70,active,
espn,2026-05-17,ESPN 2026 May,Julio Rodriguez,SS,NYY,2,65,active,
```

Required columns:
- `source` — fangraphs, espn, mlb-pipeline, tjstats, etc.
- `snapshot_date` — YYYY-MM-DD
- `interval_label` — display name for this ranking list
- `player_name` — full name (UTF-8, handles accents automatically)
- `rank` — 1-100
- `fv` — future value grade (55, 60, 65+, etc.)

Optional columns:
- `position` — SS, CF, SP, etc.
- `org` — team abbreviation
- `status` — active, graduated, injured_list, off_list
- `birth_date` — YYYY-MM-DD (only needed if you have it)

## Character Encoding

The system automatically handles special characters (ó, ú, ñ, é, etc.) in Spanish/Latino names.

**Julio Rodríguez** variants like "Julio Rodriguez" (stripped) and "Julio RodrÃ­guez" (mojibake) 
are normalized to the same player key internally, so duplicate detection works correctly.

If you ever need to fix corrupted Unicode in the player_name column:
```bash
python fix_encoding.py
```

## Workflow Example

### Adding a new FanGraphs snapshot

1. Copy FanGraphs' top 100 list from the website
2. Paste into `manual_rankings.csv` with these columns filled:
   - source: `fangraphs`
   - snapshot_date: Today's date (YYYY-MM-DD)
   - interval_label: `FG 2026 May` (or whatever label)
   - player_name, rank, fv
3. Run: `python run_monthly.py --skip-stats`
4. Check the console output for any parse errors
5. If all rows load, run full: `python run_monthly.py`

## Command Reference

```bash
python run_monthly.py                    # Full pipeline
python run_monthly.py --dry-run          # Probe sources only
python run_monthly.py --force            # Bypass cache, re-fetch JB
python run_monthly.py --skip-stats       # Fast: consensus only, no stat fetches
python run_monthly.py --out-dir ./data   # Export to custom directory

python fix_encoding.py                   # Fix mojibake in manual_rankings.csv
```

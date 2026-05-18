# MLB Prospect Stock Tracker

Tracks consensus future-value grades (20-80 scale, anchored to the
[FanGraphs scouting primer](https://blogs.fangraphs.com/the-new-fangraphs-scouting-primer/))
across the major industry prospect-ranking sources. Builds a weighted
consensusFV per prospect, preserves the full FV time series for
candlestick visuals, fetches current minor-league stat lines, detects
trades, and separates active prospects (top 100) from graduates.

## How to run it: the CSV workflow

Most prospect-ranking sites are React applications or paywalled, so
reliable HTML scraping is genuinely hard. The right way to feed this
tracker is a CSV that you maintain by hand. Each monthly run takes
about 15 minutes of data entry.

### Step 1 — install

```bash
pip install -r requirements.txt
python -m pytest tests/ -v       # should show 40 passed
```

### Step 2 — collect lists from each source

Visit each source and grab their current top-100 list. For sources that
let you sign in, look for an "Export" button. Otherwise copy/paste the
ranked list into a spreadsheet:

| Source            | URL                                                        | FV? | How to get the list                       |
| ----------------- | ---------------------------------------------------------- | --- | ----------------------------------------- |
| FanGraphs         | fangraphs.com/prospects/the-board/2026/summary             | Yes | "Export Data" button (sign-in required)   |
| ESPN (McDaniel)   | espn.com/mlb/insider/insider/story (top 100 prospects)     | Yes | Copy/paste ranked list                    |
| Just Baseball     | justbaseball.com/prospects/top-100-mlb-prospects/          | Yes | Copy/paste                                |
| TJStats           | tjstats.ca (latest monthly top 100)                        | Yes | Copy/paste                                |
| Baseball America  | baseballamerica.com/rankings/                              | No  | Copy/paste the ranked names                |
| MLB Pipeline      | mlb.com/prospects/2026                                     | No  | Copy/paste                                |
| The Athletic      | nytimes.com/athletic (Keith Law's top 100)                 | No  | Copy/paste                                |

### Step 3 — paste rows into `data/manual_rankings.csv`

The file ships with just a header row:

```csv
source,snapshot_date,interval_label,player_name,position,org,rank,fv,status,birth_date
```

Add one row per (player × source × update interval). Examples:

```csv
fangraphs,2026-02-16,FG 2026 Report,Konnor Griffin,SS/OF,PIT,1,70,active,2006-05-03
fangraphs,2026-02-16,FG 2026 Report,Leo De Vries,SS,ATH,2,65,active,2006-12-27
espn,2026-01-27,ESPN 2026 Preseason,Konnor Griffin,SS/OF,PIT,1,65,active,
espn,2026-01-27,ESPN 2026 Preseason,Leo De Vries,SS,ATH,3,60,active,
baseball_america,2026-05-13,BA 2026 May,Konnor Griffin,SS/OF,PIT,1,,active,
mlb_pipeline,2026-01-22,Pipeline 2026,Konnor Griffin,SS/OF,PIT,1,,active,
```

Column rules:

- **`source`** must be one of: `fangraphs`, `espn`, `just_baseball`,
  `tjstats`, `baseball_america`, `mlb_pipeline`, `the_athletic`.
  Typos mean the row is ingested but won't be weighted by the consensus
  engine.
- **`snapshot_date`** and **`interval_label`** identify the update.
  Two rows with the same `(source, snapshot_date, interval_label,
  player_name)` are silently deduped. Different intervals from the same
  source need different labels: `"FG 2026 Report"` vs `"FG 2026 Updated"`.
- **`player_name`** must match across sources or the same player will
  appear twice. Drop middle initials, normalize accents (`Jesús` and
  `Jesus` are different).
- **`rank`** is optional. Leave blank for sources that don't publish
  ranks. The string `""` is fine.
- **`fv`** is optional, and only meaningful for FanGraphs, ESPN, Just
  Baseball, and TJStats. The others should leave it blank. Values can
  be `70`, `55+`, or PV/FV format like `50/55` (TJStats).
- **`status`** is one of: `active`, `graduated`, `injured_list`,
  `off_list`. Default to `active`.
- **`birth_date`** is optional, ISO format (`YYYY-MM-DD`). If you have
  it, include it once for the player — the first non-empty value wins
  and gets cached forever. If you don't include it, the pipeline will
  fetch it from the MLB Stats API automatically on the next run that
  doesn't pass `--skip-stats`. Age is computed as decimal years from
  this date.

A row with FanGraphs marking a player `graduated` once is enough to
flip them into the graduates section for good — that's the rookie
threshold signal.

### Step 4 — run the pipeline

```bash
python run_monthly.py
```

This will:
1. Read the CSV
2. Insert any new snapshots (deduped by source × interval × player)
3. Rebuild the consensus time series
4. Fetch current-season MiLB stats from the MLB Stats API
5. Detect trades from the MLB transactions API + org-change inference
6. Write `data/timeseries.json` for the front-end

Output is idempotent — re-running on the same CSV is safe.

Useful flags:
```bash
python run_monthly.py --skip-stats   # skip MLB Stats API (faster, no network for stats)
python run_monthly.py --force        # bypass HTTP cache and re-fetch
python run_monthly.py --dry-run      # diagnostic: show what each source returns, no writes
```

### Step 5 — verify the output

```bash
python -c "
import json
d = json.load(open('data/timeseries.json'))
print(f\"{d['active_count']} active, {d['graduate_count']} graduates\")
for p in d['players'][:10]:
    pt = p['points'][-1]
    print(f\"  {p['player_name']:25} consensusFV {pt['consensus_fv_label']}\")
"
```

If you see duplicate players where there should be one, fix name
spelling in the CSV and re-run.

### Step 6 — next month

Open `data/manual_rankings.csv`, paste new rows for any source that
published an update, re-run `python run_monthly.py`. The append-only
snapshots table preserves history, so the candlesticks and time-series
charts get richer with each month you maintain it.

## Web app (visualize the data)

The `web/` directory is a self-contained interactive frontend that
reads `data/timeseries.json` and renders the tracker — active
prospects with FV history, candlesticks, MiLB stats, age-vs-level
coloring, plus a graduates section with MLB stats. Includes filters
for stock direction and organization, multiple sort modes, click-to-
expand source-by-source detail, dark mode, and responsive layout.

To see it locally:

```bash
python run_monthly.py    # produces data/timeseries.json
python -m http.server 8000
# Open http://localhost:8000/web/
```

To deploy publicly (Netlify, GitHub Pages, S3, or any static host),
or to embed into an existing site via iframe, see
[`web/README.md`](web/README.md) for full recipes.

## Schedule monthly (optional)

GitHub Actions:

```yaml
on:
  schedule: [{ cron: "0 11 1 * *" }]   # 11:00 UTC on the 1st of each month
  workflow_dispatch:
jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - run: python run_monthly.py
      - uses: actions/upload-artifact@v4
        with: { name: timeseries, path: data/timeseries.json }
```

This only matters if you've committed an updated CSV in the
intervening month — the action just re-processes whatever the CSV
contains. The MLB Stats API and trade detection happen automatically
on each run.

## What gets computed

Per (player, snapshot_date) bucket, four metrics:

1. **`avg_fv`** — mean of explicit FV grades from sources that publish
   them (display only).
2. **`avg_rank`** — mean of ordinal ranks across all sources.
3. **`rank_implied_fv`** — mean of ranks converted to implied FV via
   the FanGraphs tier mapping.
4. **`consensus_fv`** — weighted mean of all signals, snapped to a
   valid published grade (`20, 30, 40, 45, 45+, 50, 50+, 55, 55+, 60,
   60+, 65, 70, 80`).

Source weights (in `consensus.py`):

```python
fangraphs:        rank_weight=1.0, fv_weight=3.0
espn:             rank_weight=1.0, fv_weight=2.5
just_baseball:    rank_weight=1.0, fv_weight=2.0
tjstats:          rank_weight=1.0, fv_weight=2.0
baseball_america: rank_weight=1.0, fv_weight=0.0   # rank-only
mlb_pipeline:     rank_weight=1.0, fv_weight=0.0
the_athletic:     rank_weight=1.0, fv_weight=0.0
```

Per prospect, candlestick fields (`fv_open`, `fv_high`, `fv_low`,
`fv_close`) plus stock movement (delta between the two most recent
update intervals).

## Trade detection

Each run also detects which tracked prospects have been traded:

1. **MLB Stats API transactions endpoint** (authoritative): returns
   exact trade date and from/to teams. The same free, unauthenticated
   API serving mlb.com player pages.
2. **Org-change inference** (fallback): when a player's org changes
   between two adjacent snapshots in your CSV, that's an inferred trade
   even if the API missed it.

Trades show up as ⇄ markers on each prospect's time-interval chart.

## MiLB stats integration

For each active prospect, resolves MLBAM ID via pybaseball's Chadwick
Bureau lookup (cached forever), then fetches current-season minor-league
stats from the official MLB Stats API:

```
GET statsapi.mlb.com/api/v1/people/{id}/stats
  ?stats=season&group=hitting&season=YYYY
  &sportIds=11,12,13,14,16   # AAA / AA / A+ / A / Rk
```

If a player has been promoted mid-season we report the highest level
reached. IL and graduated players are absent from the stats payload.

## File layout

```
prospect_tracker/
├── scrapers.py              # CSV ingest + diagnostic probe (HTML scraping is best-effort)
├── consensus.py             # FV grid, weighting, build_timeseries, candlestick
├── stats.py                 # MLBAM ID lookup + MiLB stat-line fetcher
├── trades.py                # MLB transactions API + org-change inference
├── storage.py               # SQLite + JSON export with active/graduate split
├── run_monthly.py           # entry point; --dry-run for diagnostics
├── data/
│   ├── manual_rankings.csv     # the file you maintain by hand
│   └── timeseries.json         # generated output the front-end reads
├── web/
│   ├── index.html              # standalone web app (open in browser)
│   ├── embed.html              # iframe / embed example
│   └── README.md               # deployment recipes (Netlify, GH Pages, S3)
├── tests/
│   ├── test_consensus.py    # 23 tests on consensus math + export
│   ├── test_trades.py       # 17 tests on org inference + reconciliation
│   └── test_age.py          # 10 tests on age computation + DOB round-trip
└── requirements.txt
```

## Caveats

- **Name normalization matters.** "Jesús Made" and "Jesus Made" become
  two separate players. Pick one spelling per player and use it
  consistently across sources in your CSV.
- **Same-date dedup is on (source, interval_label, player_name).** If
  you want to paste a corrected version of FanGraphs' 2026 Report,
  delete the old rows from the CSV first or use a different
  `interval_label`.
- **The snapshots table is append-only.** Past data is preserved when
  you add new rows — useful for the candlestick history, but it also
  means the DB grows over time. If you ever want a clean slate,
  `rm prospects.db` and re-run.
- **ToS.** Personal hobby use only. The MLB Stats API allows this kind
  of polite read access; the rest is whatever you paste into the CSV.

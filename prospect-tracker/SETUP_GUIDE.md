# Prospect Tracker — Setup & Data Entry Guide

You already have a working pipeline and a populated CSV with FanGraphs
2025–2026 data. This guide explains how to add the other six sources
and keep everything current going forward.

---

## Quick start (if you haven't run it yet)

```bash
cd prospect_tracker
pip install -r requirements.txt
python run_monthly.py --skip-stats   # first run, no MLB API calls
python -m http.server 8000            # open http://localhost:8000/web/
```

The CSV at `data/manual_rankings.csv` already has ~265 rows of
FanGraphs data. Adding other sources is what makes the consensus FV
meaningful.

---

## The CSV format

Every row you add follows this schema:

```
source, snapshot_date, interval_label, player_name, position, org, rank, fv, status, birth_date
```

| Column | Format | Required | Notes |
|---|---|---|---|
| `source` | see below | yes | must match exactly |
| `snapshot_date` | YYYY-MM-DD | yes | date the list was published |
| `interval_label` | any text | yes | descriptive name (e.g. "ESPN 2026 Preseason") |
| `player_name` | text | yes | must be consistent across sources |
| `position` | SS, RHP, OF, etc. | no | use the source's listed position |
| `org` | 3-letter code | yes | PIT, MIL, ATH, etc. |
| `rank` | integer | no | leave blank if source doesn't rank |
| `fv` | 50, 55, 60, etc. | no | leave blank if source doesn't grade |
| `status` | active / graduated / injured_list | yes | default: active |
| `birth_date` | YYYY-MM-DD | no | fill in when available |

**Valid source values** (copy exactly):
```
fangraphs
espn
just_baseball
tjstats
baseball_america
mlb_pipeline
the_athletic
```

---

## Source by source

---

### 1. FanGraphs (already in your CSV)

**FV grades: Yes | Ranks: Yes | Free: Partial**

The Board at fangraphs.com/prospects/the-board has every historical
list going back to 2017. To get prior years you haven't entered yet:

1. Go to **fangraphs.com/prospects/the-board**
2. In the "Time Frame" dropdown, select the interval you want
   (e.g. "2024 Report", "2024 Updated", "2023 Report")
3. Click **Export Data** (the small CSV icon below the table — requires
   a free FanGraphs account)
4. The export includes: player name, position, team, rank, FV grade

**Map the export columns to the CSV:**

| FG export column | CSV column |
|---|---|
| `Name` | `player_name` |
| `Team` | `org` |
| `Pos` | `position` |
| `Rank` | `rank` |
| `FV` | `fv` |

Use `fangraphs` as the source and pick a date and label for the
interval. For the 2024 Report published February 2024, use:
```
snapshot_date: 2024-02-15
interval_label: FG 2024 Report
```

**Historical FG intervals to add:**

| Label | Approx date | Notes |
|---|---|---|
| FG 2021 Report | 2021-02-15 | |
| FG 2021 Updated | 2021-07-29 | |
| FG 2022 Report | 2022-02-15 | |
| FG 2022 Updated | 2022-07-29 | |
| FG 2023 Report | 2023-02-15 | |
| FG 2023 Updated | 2023-07-29 | |
| FG 2024 Report | 2024-02-15 | |
| FG 2024 Updated | 2024-07-29 | |

---

### 2. TJStats ✦ easiest to add

**FV grades: Yes | Ranks: Yes | Free: Yes**

TJStats publishes a monthly updated top 100 at **tjstats.ca** — no
paywall, no login. It updates more frequently than any other source,
making it the most useful for tracking in-season movement.

**How to get the data:**

1. Go to **tjstats.ca** and find the current top 100 list
2. The table is copy-paste friendly — select all rows, paste into a
   spreadsheet
3. Columns are typically: Rank, Name, Team, Position, FV

**Example rows:**
```csv
tjstats,2026-05-01,TJ May 2026,Konnor Griffin,SS/OF,PIT,1,70,active,
tjstats,2026-05-01,TJ May 2026,Jesus Made,SS/2B,MIL,2,65,active,
```

**Cadence:** TJStats updates mid-month. Add a new set of rows each
month during the season (April–September). Use the actual publication
date as `snapshot_date`.

---

### 3. Just Baseball

**FV grades: Yes | Ranks: Yes | Free: Yes**

Just Baseball (justbaseball.com) publishes a preseason top 100 with
FV grades and updates it a few times per season.

**How to get the data:**

1. Go to **justbaseball.com/prospects**
2. Find the current Top 100 Prospects article
3. The list is in article format — copy the table or the ranked list
4. They publish FV grades alongside ranks

**Example rows:**
```csv
just_baseball,2026-03-04,JB 2026 Preseason,Konnor Griffin,SS/OF,PIT,1,65,active,
just_baseball,2026-03-04,JB 2026 Preseason,Jesus Made,SS/2B,MIL,5,60,active,
```

**Cadence:** Preseason (February–March) and 1–2 midseason updates.

---

### 4. Baseball America

**FV grades: No | Ranks: Yes | Free: Partial (paywall for full list)**

BA publishes a top 100 preseason and a midseason update. They rank
but don't publish FV grades — the pipeline uses rank-only weighting
for BA rows. Leave the `fv` column blank.

**How to get the data (free):**

The free preview on baseballamerica.com shows the top 10–20 and
cluster descriptions. For the full list:

- **Option A:** BA publishes a tweet thread of their full top 100 on
  list drop day — these always appear on Twitter/X and are archived
  on baseball forums. Search `"baseball america top 100" site:twitter.com`
  around the list publication date.
- **Option B:** If you have a BA subscription, the full list is at
  baseballamerica.com/rankings — copy/paste the table.

**Example rows:**
```csv
baseball_america,2026-01-21,BA 2026 Preseason,Konnor Griffin,SS/OF,PIT,1,,active,
baseball_america,2026-01-21,BA 2026 Preseason,Jesus Made,SS/2B,MIL,4,,active,
```

**Cadence:** Preseason (January) and one midseason update (May–June).

---

### 5. MLB Pipeline

**FV grades: No | Ranks: Yes | Free: Yes**

MLB Pipeline (mlb.com/prospects) is the official MLB list. No FV
grades but it's free, authoritative, and useful as a rank signal
(especially for system-wide lists by org).

**How to get the data:**

1. Go to **mlb.com/prospects/2026** (update year as needed)
2. The top 100 is a scrollable ranked list
3. Copy player names and ranks — position and org are also shown

**Example rows:**
```csv
mlb_pipeline,2026-01-22,Pipeline 2026,Konnor Griffin,SS/OF,PIT,1,,active,
mlb_pipeline,2026-01-22,Pipeline 2026,Jesus Made,SS/2B,MIL,3,,active,
```

**Cadence:** Preseason only (January). Pipeline updates org lists
throughout the season but the overall top 100 is typically set once
per year.

---

### 6. ESPN / Keith Law

**FV grades: Yes | Ranks: Yes | Free: No (ESPN+)**

ESPN's prospect list is compiled by Keith Law. It publishes FV grades
and is one of the most-cited lists.

**How to get the data:**

- If you have ESPN+, the list is at espn.com — search "ESPN top 100
  prospects [year]"
- Law's preseason list typically drops in late January; he publishes
  a midseason update in July
- The list is sometimes shared on baseball forums and Reddit in the
  days after publication

**Example rows:**
```csv
espn,2026-01-27,ESPN 2026 Preseason,Konnor Griffin,SS/OF,PIT,1,65,active,
espn,2026-01-27,ESPN 2026 Preseason,Jesus Made,SS/2B,MIL,5,60,active,
```

**Cadence:** Preseason (January) and one midseason update (July).

---

### 7. The Athletic / Keith Law

**FV grades: No | Ranks: Yes | Free: No (NYT/Athletic subscription)**

The Athletic (formerly separate, now part of the New York Times)
publishes its own top 100. Rank-only, no FV grades.

**How to get the data:**

- If you have a subscription, the list is at nytimes.com/athletic
- Search "top 100 prospects 2026" within Athletic content
- Like BA, the full list often appears on Twitter/X on publication day

**Example rows:**
```csv
the_athletic,2026-01-26,Athletic 2026,Konnor Griffin,SS/OF,PIT,1,,active,
the_athletic,2026-01-26,Athletic 2026,Jesus Made,SS/2B,MIL,4,,active,
```

**Cadence:** Preseason only.

---

## Your first data entry session

Here's the order I'd recommend for maximum impact:

1. **TJStats** — free, current, has FV grades. Takes 20 minutes to add
   the current list. Immediately makes consensus FV meaningful.

2. **Just Baseball** — free, has FV grades. Another 20 minutes.

3. **MLB Pipeline** — free, no grades but adds a third rank signal.
   20 minutes.

4. **FanGraphs historical** — use The Board export to backfill 2021–
   2024 intervals. Each year is ~5 minutes with the CSV export. This
   is what makes the sparklines meaningful for veteran prospects who've
   been on lists for years.

5. **Baseball America / ESPN / Athletic** — add when you have access.
   Even partial lists (top 30) improve the consensus.

After each batch, run:
```bash
python run_monthly.py --skip-stats
```

The pipeline dedupes by `(source, snapshot_date, interval_label,
player_name)` so you can re-run as many times as you want — it won't
double-count anything.

---

## Name consistency

The single most important thing: **player names must match across
sources**. The pipeline identifies players by their name key, not an
external ID. A few common mismatches to watch for:

| Problem | Fix |
|---|---|
| `Jesus Made` vs `Jesús Made` | Pick one, use it everywhere |
| `JJ Wetherholt` vs `J.J. Wetherholt` | Pick one |
| `Jurrangelo Cijntje` — easy to misspell | Copy-paste, don't retype |
| Middle initials | Drop them (use `Ryan Sloan` not `Ryan J. Sloan`) |

If the same player appears twice in your output with different names,
fix the spelling in the CSV and re-run. The old snapshots won't
disappear — delete the database and rebuild:

```bash
rm prospects.db
python run_monthly.py --skip-stats
```

---

## Monthly workflow (once set up)

During the season:

1. **~1st of each month:** Check TJStats for their new update. Add
   ~100 rows to the CSV. Run `python run_monthly.py`.

2. **When FG publishes an update** (typically pre-deadline in July,
   end-of-season in October): Export from The Board, add rows.

3. **When a prospect graduates** (crosses the MLB rookie threshold):
   FanGraphs moves them to the Graduates tab. Add a row with
   `status=graduated` and today's date as the snapshot_date. The
   pipeline will move them to the Graduates section automatically.

4. **Pre-season** (January–February): All seven sources publish. This
   is the big data entry session — budget an hour to add all of them.

---

## Verifying the output

After each run, a quick sanity check:

```bash
python -c "
import json
d = json.load(open('data/timeseries.json'))
print(f'Active: {d[\"active_count\"]}  Graduates: {d[\"graduate_count\"]}')
print(f'Orgs: {len(d[\"org_summary\"])}')
for p in d['players'][:5]:
    pt = p['points']
    sources = len(set(
        s['source']
        for point in pt
        for s in point.get('sources_contributing', [])
    ))
    print(f'  {p[\"player_name\"]:22} {len(pt)} intervals  {sources} sources')
"
```

You want to see at least 2–3 sources per top prospect. Once you've
added TJStats and Just Baseball, the top players will have 3 sources
and the consensus FV will be a real weighted average rather than just
FanGraphs' number.

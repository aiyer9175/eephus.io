# The current-year MLB Pipeline preseason vintage is not a vintage

Found 2026-08-13 while scoping the Pipeline re-ingest the owner asked for. Measured
read-only against the live DB. Nothing repaired at the time of writing.

## The claim

`MLB Pipeline {Y} Top 100` is treated everywhere as the PRESEASON vintage for year
Y: one board, captured before the season, stamped `Y-01-22`. For the CURRENT year
that is false. The label is an accreting union of every board the scraper has seen
since the first capture, every row stamped `Y-01-22`, including players who did not
exist on any board in January.

## Measured

    MLB Pipeline 2026 Top 100 -> 139 rows for 100 distinct ranks
    every row stamped snapshot_date = 2026-01-22

Rows by INSERTION month, which the label itself does not expose:

| inserted | rows |
| --- | --- |
| 2026-05 | 101 |
| 2026-06 | 11 |
| 2026-07 | 10 |
| 2026-08 | 17 |

Note the first capture is itself **May**, not January. The `2026-01-22` stamp was
already a fiction before any accretion: `MLB_PIPELINE_INTERVALS`
(`scrapers.py:2065-2077`) hardcodes `f"{y}-01-22"` regardless of when the page is
actually read.

Rank collisions the accretion produces, first few:

    rank  5   Trey Yesavage     | Kade Anderson
    rank  6   Colt Emerson      | Josue De Paula
    rank 12   Travis Bazzana    | Theo Gillen
    rank 17   Bryce Eldridge    | Josuar Gonzalez
    rank 25   Ethan Holliday    | Noah Schultz

**Ten players on the 2026 preseason label were drafted in 2026**, five months after
the date they are stamped with: Roch Cholowsky, Grady Emerson, Vahn Lackey, Jackson
Flora, Derek Curiel, Eric Booth Jr., Drew Burress, Tyler Bell, Jacob Lombard, Gio
Rojas. Sixteen rows landed on 2026-08-13 alone, during a live `run_monthly`.

## Mechanism, and it is not primarily the cache

`MLB_PIPELINE_INTERVALS` builds an archive interval for every year in
`range(2011, 2027)` off `https://www.mlb.com/milb/prospects/{y}/top100/`. For a PAST
year mlb.com serves a frozen page, so the interval is genuinely archival. For the
CURRENT year that same URL serves the LIVE board, which is rewritten all season.

So the archive interval and the live capture (`run_mlb_pipeline_live`,
`scrapers.py:2517-2548`) read the SAME URL, and the archive one writes what it finds
under the preseason label with the preseason date. `insert_snapshots` upserts on
`(source, interval_label, player_key)` (`storage.py:1966-2013`), so a player on
today's board who was not on the first capture is INSERTED as a new row under the
January label rather than updating anything. Hence 139 rows for 100 ranks.

The shared cache key compounds it (`run_mlb_pipeline_live` passes no `cache_key`, so
it defaults to `mlb_pipeline_{year}_top100`, `scrapers.py:2257-2258`, which is the
key the archive interval also uses, and the live caller runs `force=True` and
rewrites that cache file). But the defect does not need the cache: the archive
scrape of the current year returns today's board whether it comes off the wire or
off disk.

## Why it matters here specifically

`scrapers.py:2527-2528` states the reason the live capture uses a separate dated
label: "backtests key on the earliest same-year snapshot, which stays the preseason
archive page". For the current year that guarantee does not hold, and the rows that
break it are exactly the ones a backtest must never see, namely players whose grades
postdate the decision point.

`pipeline_vintage.py` is the real point-in-time archive and is deliberately NOT
imported by `run_monthly`, `consensus` or `efv_dataset` (`pipeline_vintage.py:37-39`),
so nothing downstream mitigates this.

## Scope, stated honestly

**The eFV training frame is probably NOT affected today.** `SCORED_YEARS` ends at
2024 and decision years are bounded by `DEBUT_YEARS`, so a 2026 board is not a
training vintage. The damage is to the 2026 SERVED consensus and to any future
backtest that reaches the 2026 cohort.

**Past years are mostly explained by something else.** 2014 (118 rows) and 2016 (127)
also carry excess rows, and the same-year-draftee probe returns only 1 to 2 players
for those years, all of them known collision slugs (Carlos Martinez, Jake Thompson,
Nick Williams). So the historical excess is largely identity collision, not
accretion, and this document does not claim otherwise. The accretion mechanism is
nonetheless the same one that ran during those years, and whether it contributed is
UNVERIFIED.

## The repair

1. **Stop the accretion.** The archive interval must not be scraped for the current
   year, because its URL is not archival for the current year. The live capture
   already covers the current year under correctly dated labels.
2. **Remove the contaminated rows** from the current-year preseason label, keeping
   the first capture. Idempotent, `--apply` gated, following the
   `tools/repair_*_collision.py` precedent.
3. **Stop stamping a date the capture does not have.** `f"{y}-01-22"` is asserted,
   not observed. Out of scope for this repair, recorded so it is not rediscovered.

## Results

(empty at pre-registration)

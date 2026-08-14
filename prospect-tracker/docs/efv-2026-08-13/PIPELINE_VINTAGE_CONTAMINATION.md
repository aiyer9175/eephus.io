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

The full 2011-2026 audit the owner called for did NOT confirm the hypothesis above
for the historical years. It refuted it, with better evidence, and found a second
defect that had nothing to do with accretion. Recording that the plan was wrong
before recording what shipped.

### THREE defects, one symptom

`rows > distinct ranks` turned out to be three unrelated things.

**CLASS A, accretion. Confirmed, current year only.** The mechanism above is
correct and it is confined to the year being scraped live. 388 rows: 39 on the
Top 100 and 349 across all 30 org boards. Every prior year is clean at its own
published depth.

**CLASS B, a WRONG-LIST WRITE. Not accretion at all.** 2014 (118 rows) and 2016
(127) looked like older accretion. They are not. On 2026-06-22 at 02:50:02 the
2011, 2014 and 2016 Top-100 pages parsed from a cache holding the **Yankees org
board**, and 10, 20 and 30 rows were ingested under the Top-100 labels. A forced
re-run **48 seconds later** wrote the true boards over them, but the upsert could
only correct the Yankees who were ALSO genuine Top-100 players. The rest were left
behind carrying an org rank under a Top-100 label.

Four independent lines of evidence, none of which the accretion story survives:

- the insertion span is 48 SECONDS inside one run, not months (2026 spans May to
  August, genuinely different)
- the early batch is SET-IDENTICAL to that year's Yankees org board, and the batch
  sizes 10/20/30 match era-correct org depth exactly (2011 orgs are 10 deep,
  2012-14 are 20, 2015-16 are 30)
- the AUTOINCREMENT id blocks reconstruct the run: pass 2 spans exactly 550 ids,
  242 inserts plus 308 upsert-burned, and the arithmetic closes to the row
- the survivors name the mechanism. The rows that were NOT orphaned are exactly
  the Yankees who were on the real board, moved from org rank to true rank:
  **Aaron Judge 2 -> 31**, Jesus Montero 1 -> 9, Jorge Mateo 1 -> 30.

The repair tool's own dry run confirmed it a fifth time without being told to look
for it: every one of the 52 orphans is a Yankees prospect. Betances, Romine and
Brackman in 2011; Heathcott, Murphy and Jagielo in 2014; Kaprielian, Garcia and
Fowler in 2016.

**Root cause, and it is the finding worth keeping.** The archive Top-100 loop was
the ONLY Pipeline path with no health gate. `validate_pipeline_live_board` is
called from the live capture and `validate_pipeline_org_boards` from the org
capture; the archive loop called nothing, so a 10-row parse of a 100-row page was
indistinguishable from success. Fixed with a dedicated
`validate_pipeline_archive_board`, because the live gate requires 90 rows and 80%
FV coverage and would have refused two legitimate boards (2011 is a Top 50 at ~38%
FV, 2012 runs ~73%). The wrong-list payloads are internally consistent, so a size
floor is the only discriminator.

**CLASS C, split identities.** Two keys per human on 8 labels
(`jose_f_miranda`/`jose_miranda` on 7, `lou_trivino`/`lou_trivino_iii` on 1). Not
a vintage defect and not repaired by deleting a row: routed through
`consensus.PLAYER_KEY_ALIASES`, where the merge applies to every consumer.

### Blast radius: SERVED-ONLY, and narrower than the row count suggests

Measured by running the shipped path twice, once with the contaminated label
removed, 9,472 players both arms.

- **The eFV training frame is untouched.** Zero contaminated rows can reach either
  matrix, proved structurally and empirically.
- **Served `consensus_fv` is unchanged for all ten same-year draftees.** The
  forward fill keys on `snapshot_date` and cannot see `inserted_at`, so the
  same-day live and org rows supersede the January row, and they carry an
  IDENTICAL FV anyway.
- **The damage is the candlestick.** Each affected player gained a phantom
  `2026-01-22` event date, which moves the history open and low:
  `roch_cholowsky` `fv_open` 50 where it should read 58, `jackson_flora` 47
  against 52.

### What the repair could NOT fix, and why the label was deleted

Deleting the accreted rows brought the 2026 Top 100 to 100 rows but only **78
distinct ranks**, and that number is the lesson. `insert_snapshots` updates `rank`
in place and never touches `inserted_at`, so the SURVIVING first-capture rows had
their grades overwritten all season: 66 of 100 match the 2026-08-13 live board on
both key and rank, while the 34 who fell off the board kept their May ranks. The
label was a May membership carrying August values under a January date, and no
row-level delete reaches that. The first capture was itself **May**, not January,
so the preseason vintage for 2026 was never captured at all.

Owner decision: delete the whole current-year archive label. Checked first that no
player would lose their only Pipeline representation (0 would); the
`MLB Pipeline Live YYYY-MM-DD` family carries 4,703 correctly dated rows.

### Final state

| family | before | after |
| --- | --- | --- |
| 2011 Top 100 | 57 rows / 50 ranks | 50 / 50 |
| 2014 Top 100 | 118 / 100 | 100 / 100 |
| 2016 Top 100 | 127 / 100 | 100 / 100 |
| 2026 Top 100 | 139 / 100 | deleted |
| 2026 org x30 | 1,249 | 900 |
| 2022 Top 100 | 101 / 100 | 101 / 100, resolved by alias at read time |

540 rows deleted total, database backed up to
`prospects.db.bak-vintage-2026-08-13` first.

### Residual, stated rather than left to be rediscovered

The 2024 and 2025 org families remain at 901 rows against 900. The audit
identified this as a third name-variant pair on the Rangers boards, one row each.
It is NOT aliased here: the class-C detector found the Miranda and Trivino pairs
and did not match this one, and chasing it belongs with the identity lane rather
than with a vintage repair.

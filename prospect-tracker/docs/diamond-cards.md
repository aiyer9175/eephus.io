# Baseball Card Market runbook (/cards/)

Module owner files: `card_prices_ingest.py`, `card_market_export.py`,
`assets/cards.js`, `assets/cards.css`, `test_card_market.py`,
`data/card_watchlist.json`. Page shell lives in `build_site.build_cards()`.
Scheduling lives in `run_monthly` (steps `6g-pre` and `9f`) and
`deploy/betting-crontab.example`.

Read this before dropping comps, before enabling the scraper, and before
anyone asks why the page will not quote a sale price.

If you are here because the board shows 0 priced, go to **section 4b** (what is
wired and what the operator still owns) and **section 4c** (`meta.ingest`, which
says which kind of empty this is).

---

## 1. The posture, in one paragraph

The owner decision (2026-08-04) was to source card prices by scraping public
sold listings, **with mitigations binding**. Those mitigations are the design:

* Raw comps are stored **locally and forever**, in `prospects.db`. That file is
  gitignored, and so is every `*.csv` under `data/drops/`. Nothing raw is
  committed and nothing raw is served.
* The site publishes **derived values only**: a per-card eephus Card Index (a
  grade-mix adjusted trimmed median), its trend against the prior window, and a
  screen label. No sale price, sale date, listing title, listing id, seller or
  URL appears in `data/card_market.json`. `test_card_market.py` asserts the
  absence structurally (banned keys anywhere in the document) and numerically
  (no stored comp price is published as a value).
* The **manual CSV drop is a first-class, equal input**, not a fallback bolted
  on afterwards. The scraper is off by default and can be deleted from the
  rotation without touching the model.
* The **licensed swap is documented** (section 6). If the scraper breaks, or ToS
  exposure stops being acceptable, the module keeps working from drops.

Legal note, plainly: post-hiQ, scraping publicly visible data is not a
computer-fraud problem, but it is breach-of-contract exposure under a
marketplace's terms of service. Publishing a derived index from stored comps is
materially safer than republishing the comps. That distinction is the whole
reason this module is shaped the way it is, so do not "simplify" it by putting a
comp table on the page.

---

## 2. The watchlist

`data/card_watchlist.json` is a **curated** list of about forty cards. It is
committed, hand-editable, and regenerated from the live board with:

    python card_prices_ingest.py --build-watchlist

The generator takes the top of the live eFV board through
`efv_board_scale.board_value` (the one-basis rule; never a second eFV scale),
joins `data/timeseries.json` for name / org / mlbam / ETA, and adds the HEM+ and
SEM+ leaders off the committed leaderboards as the MLB tier. ETA is stamped onto
each entry at build time so `card_market_export` never has to parse the 73MB
timeseries for forty players.

Entry shape:

| field | meaning |
|---|---|
| `card_id` | `slug(player_key)\|slug(set_desc)\|slug(grade_bucket)`. THE identity. |
| `player_key` | joins to `data/xfv.json` `by_player` |
| `player_name`, `mlbam`, `org`, `position`, `side` | identity, for display and links |
| `tier` | `prospect` or `mlb`. Percentiles are computed WITHIN tier. |
| `set_desc` | the card, e.g. `Bowman Chrome Prospect Auto` |
| `parallel` | e.g. `Base Refractor` |
| `grade_bucket` | the target grade the index is expressed in, e.g. `PSA 10` |
| `hot` | daily refresh instead of weekly |
| `eta` | ETA year, stamped at build time |

After regenerating, hand-edit freely. Which parallel a player's market actually
trades on is a hobby judgement, not a model output.

Identity for entries with no `mlbam` goes through `stats.bulk_resolve_ids`.
**Never `resolve_mlbam_id`**: the single-player entry point writes a negative-id
cache entry on a miss and a later good lookup reads the poisoned entry. That is
the defect that left a whole draft class without stats on 2026-08-03, and
`test_card_market.py` pins the bulk path.

---

## 3. CSV drop format (the primary path)

Drop the file at:

    data/drops/card_comps_YYYY-MM-DD.csv

Then:

    python card_prices_ingest.py --drops          # every drop file
    python card_prices_ingest.py --csv <path>     # one file

### Columns

Required: a price column and a sale-date column. Everything else is optional but
helps. Header matching is case-insensitive and space-insensitive, and unknown
extra columns are ignored, so an export from another tool usually works as-is.

| canonical | accepted header aliases | notes |
|---|---|---|
| `card_id` | `card_id`, `cardid`, `card` | best identity; copy it from the watchlist |
| `player_key` | `player_key`, `playerkey`, `player` | used when `card_id` is absent |
| `set_desc` | `set_desc`, `set`, `set_parallel`, `description`, `card_desc` | with `player_key` + `grade`, identifies the card |
| `grade` | `grade`, `grade_bucket`, `gradebucket`, `condition` | grade **as sold**, e.g. `PSA 9`, `RAW` |
| `sold_date` | `sold_date`, `date`, `sale_date`, `solddate` | **required**. ISO, US, or `Mar 3 2026` forms all parse |
| `price_usd` | `price_usd`, `price`, `sale_price`, `amount` | **required**. Currency symbols and commas are stripped |
| `title` | `title`, `listing_title`, `name` | stored locally, never published |
| `listing_id` | `listing_id`, `id`, `item_id`, `listingid` | see idempotency below |

Example:

    card_id,player_key,set,grade,sold_date,price,title,listing_id
    jesus-made|bowman-chrome-prospect-auto|psa-10,jesus_made,Bowman Chrome Prospect Auto,PSA 10,2026-08-01,1250.00,"2024 Bowman Chrome Jesus Made Auto PSA 10",1234567890

### What happens to bad rows

A row with an unparseable price or date is **dropped and counted**, never
guessed at. A missing price does not become a zero. The ingest logs the skip
count per file.

A row for a player on the watchlist but a parallel that is not is kept under its
own generated `card_id`. The export only reads watchlist ids, so the sale is
stored and simply not published until the watchlist names that card.

### Idempotency

Re-running a drop stores nothing new and rewrites nothing. The primary key is
`(card_id, listing_hash)` and every write is `INSERT OR IGNORE`.

`listing_hash` is the source's `listing_id` when it supplies one, otherwise a
content hash of `(card_id, sold_date, price, grade, title)`. The practical
consequence: **two identical sales on the same day at the same price collapse
into one row unless the source numbers them.** If your source has listing ids,
include them.

---

## 4. The scraper (off by default)

    EEPHUS_CARD_SCRAPE=1 python card_prices_ingest.py --scrape --hot

Without the flag the call refuses and logs; it does not silently no-op into a
zero-comp export.

Posture:

* **>= 5s between requests**, enforced by `Throttle`, whose interval floor
  cannot be lowered below `MIN_REQUEST_INTERVAL` (a test pins this).
* **Honest User-Agent** naming the project and a contact address.
* **Resilient parse.** `parse_sold_html` walks item blocks and requires BOTH a
  price and a sale date in the same block. A layout change therefore yields
  **zero rows and a loud log**, never a wrong price. Zero rows is a designed
  outcome. If the movers board goes flat, check the ingest log before assuming
  the market went quiet.
* Target URL is one constant, `SEARCH_URL_TEMPLATE`, overridable with
  `EEPHUS_CARD_SCRAPE_URL`. A host change or a swap to a licensed feed is one
  edit.

Nothing in the test suite makes a network request; the scraper tests run on
fixture HTML.

### Cadence

Owned by the module (`card_prices_ingest.CADENCE`), scheduled by the box:

* `hot` entries (roughly the top twelve prospects plus the MLB tier): daily
* everyone else: every 7 days
* a full sweep on Sundays (`full_sweep_weekday`), which must complete inside 60
  days, because marketplaces expire their own sold windows at 90 and an unseen
  comp is gone for good. The 7-day rule alone would also cover the tail, but it
  spreads it across whichever nights each card happens to age out on, and that
  makes "did the sweep actually complete" unanswerable. A weekday makes a missed
  sweep one visible gap instead of a diffuse drift.

---

## 4b. What is wired (2026-08-05), and what the box operator still owns

Before this date **nothing called the ingest.** `run_monthly` step 6g ran only
`card_market_export.export()`, no schedule anywhere invoked
`card_prices_ingest`, and this file's own crontab example documented
`EEPHUS_CARD_SCRAPE=1` while installing no card job. The flag armed a scraper
that nothing ran, so `/cards/` served 40 tracked cards and 0 priced, forever,
and the export was doing its job perfectly on an empty store.

### The one entry point

    python card_prices_ingest.py --scheduled

`run_scheduled_ingest()` is what that calls, and it is the **only** thing the
pipeline and the crontab invoke, so the two cannot drift apart about what the
cadence is. It reads `CADENCE`, not its caller:

1. ingest every `data/drops/card_comps_*.csv` (no network, always)
2. pick tonight's scope: `full` on the sweep weekday, otherwise `hot`
3. scrape the cards that are due under `due_cards`, but only when
   `EEPHUS_CARD_SCRAPE=1` and only when that scope has not already been fetched
   today

**It is safe to call more than once a day**, which is what makes the pipeline
step and the belt-and-braces cron entry legal side by side. Drops are already
idempotent at the row level (`INSERT OR IGNORE` on `(card_id, listing_hash)`)
and at the file level (`card_drop_files`); the scrape is guarded by the new
`card_scrape_runs` table, whose primary key is `(ran_on, scope)`. A scope
already fetched today is **skipped, not re-fetched**, so no marketplace sees the
same page twice in a night no matter how many callers fire.

**It no-ops safely with the flag unset**, which is the state of every box that
has not edited `/etc/eephus.env`: the drop path runs, the scrape returns
`enabled: false` with a stated reason, and nothing raises.

### Where it runs now

| where | step | what it does |
|---|---|---|
| `run_monthly` (monthly) | `6g-pre` | `run_scheduled_ingest()`, then existing `6g` exports |
| `run_monthly` (daily tail) | `9f` | `run_scheduled_ingest()`, then `card_market_export.export()` |
| `deploy/betting-crontab.example` | `40 6 * * *` | the same two commands, sourcing `/etc/eephus.env` |

`9f` sits **after** `d9` on purpose. `d9` is `rebuild_only`, which re-runs
`efv_export.regen_all`, so the talent side of the buy signal reads the same
`data/xfv.json` the rest of the night's site serves. Running the card export
before the regen would screen tonight's prices against yesterday's board.

Monthly `6g` is deliberately left in place as well. It makes a bare
`run_monthly.py` self-publish, and the chained daily re-exports about fifteen
minutes later against the post-regen board, so the served file ends the night on
the fresher inputs either way. The file is about forty rows; the duplicate write
costs nothing worth engineering around.

### What the box operator still owns

Nothing in the tree can do these four:

1. **Put `EEPHUS_CARD_SCRAPE=1` in `/etc/eephus.env`** (root-owned, chmod 600) if
   scraping is wanted. Leaving it out is a supported configuration, not a broken
   one: drops still ingest and the payload says the scraper was not armed.
   **As of 2026-08-07 this flag is deliberately UNSET and arming it does
   nothing useful.** eBay 403s every request from this module (measured twice,
   1832 byte block page, identical for our UA and a plain browser UA), so the
   two armed nights produced 22 attempts and 22 errors and zero comps. Do not
   re-arm it against `SEARCH_URL_TEMPLATE`'s default host until a source has
   been cleared. See `docs/card-price-source-survey-2026-08-07.md`.
2. **Install the cron lines** from `deploy/betting-crontab.example`. The nightly
   pipeline already runs the ingest, so this only covers nights the pipeline
   does not run, exactly like the leaderboard-vintage line it sits next to.
3. **Create `data/drops/`** and drop CSVs there if the drop path is being used.
   The directory does not exist in a fresh checkout and `ingest_drops` logs and
   returns rather than creating it, because an empty directory that silently
   appears is indistinguishable from one somebody meant to fill.
4. **Decide the watchlist.** Which parallel a player's market actually trades on
   is a hobby judgement (section 2).

Until at least one of (1) or (3) happens, `data/card_market.json` will keep
reporting `meta.ingest.state = "no_comps_yet"`, which is the truth.

---

## 4c. Why the board is empty, published in the payload

`meta.ingest` in `data/card_market.json` exists because **a zero-priced board
has three completely different causes and they used to look identical**:

* nothing has been ingested yet, which is honest and is the state `/cards/`
  shipped in;
* the ingest **ran and understood nothing**, which is a parser regression; and
* **nothing ever came back**, which is a blocked source and is the state this
  module has actually been in since the fetcher was first armed.

`parse_sold_html` is deliberately built to yield zero rows on layout drift
(section 4: it requires both a price and a sale date in the same block, so a
redesign produces nothing rather than plausible garbage). That design is right,
and it is exactly what makes all three cases byte-identical in `card_comps`:
every one of them writes no rows. So `scrape_cards` counts `cards_attempted`,
`cards_fetched` and `fetch_errors` next to `rows_parsed`, stamps all of them
into `card_scrape_runs`, and `card_market_export.ingest_state()` publishes the
verdict.

| state | meaning | files a RED? |
|---|---|---|
| `no_comps_yet` | nothing has ever been ingested | no, this is honest |
| `ingest_ran_empty` | something ran and stored nothing, but too small or too mixed a batch to be a claim about the parser or the source | no |
| `fetch_blocked` | 3 or more cards attempted, **zero** pages fetched, every attempt an error: the source is refusing us | **yes** |
| `parse_regression` | 3 or more pages fetched, **zero** sales parsed from all of them | **yes** |
| `drop_parse_empty` | the newest CSV drop parsed zero usable rows: a column-contract break | **yes** |
| `stale` | comps on file but nothing new stored in 14 days: the schedule is not reaching the store | no |
| `ok` | comps are being ingested on schedule | no |

`fetch_blocked` and `parse_regression` cannot both be true: the first needs zero
pages back, the second needs three or more. The distinction is the one that
decides who has work to do. A parse regression is ours to fix in
`parse_sold_html`; a blocked fetch cannot be fixed by any parser, any watchlist
edit or any retry, and the only move is to change the source. It was added
2026-08-07 after two armed nights (22 attempted, 0 fetched, 22 errors) had
classified as `ingest_ran_empty` with `red: false`, because `ingest_state` read
`cards_fetched` and `rows_parsed` and never `fetch_errors`. The board would have
stayed dark indefinitely while reporting the honest empty state.

Three is the threshold because forty tracked cards do not go simultaneously
silent, and three is the smallest batch where "every single one had no sales" or
"every single one failed" stops being plausible. Both rules share the constant
(`FETCH_BLOCKED_MIN_CARDS` is an alias of `PARSE_REGRESSION_MIN_CARDS`) so they
cannot drift into disagreeing about how many failures make a pattern. Fourteen
days is longer than the 7-day long-tail cadence and shorter than the 45-day
index window, so `stale` fires while the index is still computable rather than
after it has already gone null.

The three RED states file through **`bullpen_export._ingest_red`**, the sanctioned
template from the 2026-08-05 silent-empty sweep, rather than a third mechanism.
The RED is filed **after** the artifact is written, deliberately: the index
arithmetic is correct even when the tap is broken (what is wrong is the input),
and refusing to publish would hide the very block that explains the problem.
Same posture as `guard_nonempty_block`: keep serving, make the failure visible.

`card_scrape` and `card_drops` are deliberately **not** in
`run_monthly.SCHEDULED_GRADE_SOURCES`. They write comps, not grade rows, and a
source that is legitimately switched off would otherwise print
`!!! INGEST RED` every single night until everyone stopped reading the line.
The verdict is loud in three other places instead: an `ERROR` from
`scrape_cards` the moment a whole batch parses nothing, an `ERROR` from the
export and from daily step 9f, and two rows in the ingest-health table the
pipeline prints at the end of every run.

Those two rows (`run_monthly._record_card_ingest`) are **two and not one**
on purpose. `ingest_drops` re-parses every drop file on every run, so a single
CSV dropped in March would keep a combined row green forever and hide a scraper
that died in April. Split, `card_scrape`'s `last OK` answers the only question
worth asking of it: **when did the scraper last actually parse a sale.**

Both key on **rows parsed, not rows stored**. A re-read of the same 90-day sold
window stores zero new rows and is perfectly healthy, so keying on stored would
report a working ingest as a failure every night after the first.

A scrape that is not armed records `ok=False` with `EEPHUS_CARD_SCRAPE is not 1`
as the message. That reads as loud, and it should: an unarmed scraper with no
scheduled caller is precisely the condition that left this board at 0 priced for
its whole first life while nothing anywhere said so.

Nothing in this block is a comp. Counts, our own ingest dates, and a state name:
no sale price, no sale date, no title, no listing id. `store_health()` exists
alongside `store_stats()` for exactly this reason, and returns
`last_ingest_on` where `store_stats` returns `first_sale` / `last_sale`, because
a sale date is a raw fact this module does not publish even in aggregate.

---

## 5. The model

`card_market_export.py` writes `data/card_market.json`.

**The Card Index.** For each watchlist card, over a rolling 45-day window:

1. Keep comps with `sold_date` inside the window.
2. Grade-adjust each price onto the card's own grade bucket:
   `adjusted = price * factor[target] / factor[sold_grade]`. A comp whose grade
   is not in `GRADE_FACTORS` is **dropped**, not guessed.
3. Trim by **value**: drop adjusted prices outside `0.20x` to `5.00x` the
   window's raw median.
4. Median what is left. Fewer than 5 usable comps and the index is `null` with a
   stated reason, which renders as a visible empty cell, never a zero.
5. Publish on a coarse grid: nearest $1 under $100, nearest $5 under $1,000,
   nearest $25 above.

Two of those steps deserve a note.

*Why the trim is by value.* Symmetric **count** trimming cannot move a median at
all: dropping k values from each tail leaves the middle order statistics exactly
where they were, so a "10 percent trimmed median" is byte-identical to a plain
median at every n. It would have been decorative arithmetic. What actually
contaminates card comps is off-card sales surviving the query (a five-dollar lot
of base cards, a reprint, a mis-parsed price), and those arrive in clusters,
which is the case a plain median does not handle. The band handles it. A test
proves the count-trim identity so nobody re-introduces the decorative version.

*Why the publish grid is coarse.* A median of an odd sample can land exactly on
one observed sale. The grid means the published number is a statistic about a
market rather than a quotation of somebody's sale, which is the line this whole
module is drawn around.

**Trend** is the same index over the prior 45-day window, and the percent change
between them. Null when either leg is null.

**The buy signal** is a gap between percentiles, both computed **within tier**:

    gap = talent percentile - price percentile

Talent is the eFV blend cloned structurally from
`fantasy_export._dynasty_prospects` (grade quantile, plus 10 x P(star), minus
6 x P(bust), plus 4 x ETA proximity, plus 2 x normalized surplus). The
**displayed** eFV is the board grade through `fantasy_export._board_grade`, which
is `efv_board_scale.board_value`; the quantile stays a model input only, exactly
as it does in the fantasy module. One eFV basis site-wide.

Tiers are separated because a prospect's forward eFV and a debuted player's
retrospective cohort grade are different quantities (the Quantity A vs Quantity B
trap), and because a modern prospect auto and a decade-old flagship rookie are
not one market.

Bands are `gap >= +20` buy, `gap <= -20` fade, otherwise hold. **These are
display conventions, not fitted thresholds**, and the payload says so in words.

---

## 6. Why v1 is a screen, and what would make it a signal

`data/card_market.json` carries `"screen": true`, and the page carries the label
wherever a signal appears. This follows the PAL RP-to-SP precedent: a labelled
screen is honest, an unlabelled screen is not.

There is no price-history backtest, because there is no price history. The
module starts accumulating one at first export (`card_index_history`, one row per
card per export day). The pre-registration lives in
`card_market_export.eval_stub()` and is written to `data/card_market_eval.json`
with:

    python card_market_export.py --eval

It states, before the data exists, what would have to be true:

* **target**: forward 90-day percent change in the published index
* **candidate**: the gap at t0
* **baselines**: a zero-information control (gap permuted across cards),
  momentum carry (the card's own prior trend), and eFV level alone
* **metric**: Spearman rho of gap vs forward return, plus decile spread
* **ship bar**: beat BOTH baselines out of sample, with the zero-information
  control excluded from the bootstrap CI, on at least 3 of 4 forward windows
* **earliest possible run**: two full non-overlapping forward windows after the
  first export with at least 30 priced cards

If it fails, the ledger records the refusal and the page keeps the screen label.
The index itself is descriptive and survives a failed signal gate.

> **Order of operations for the registry.** The registry row cites
> `data/card_market_eval.json` in its notes rather than in `eval_artifact`,
> because there is nothing to evaluate yet and `test_model_registry` correctly
> refuses to let an `unvalidated` row carry an artifact. Whenever the artifact is
> first written, the notes citation already registers it. Do not promote the row
> to `provisional` until a gate has actually run.

---

## 7. The licensed swap, surveyed 2026-08-07

**Read `docs/card-price-source-survey-2026-08-07.md` before acting on this
section.** Every source below was actually requested with the module's own UA at
the pinned 5s floor on 2026-08-07; the status codes are measured, not assumed.
The short version: **no source passes today**, and the recommendation this
section used to make was wrong.

* **SportsCardsPro** is the only near miss. Its public card pages are fetchable
  (200, server rendered, `robots.txt` allows them) and carry per grade sold rows
  with a date, a title and a price, which is the section 3 column contract
  exactly. It fails on TERMS: their Price Data Acceptable Use clause forbids
  using their price data "in any software, application, or system that is
  accessible to third parties ... without express written permission", and a
  derived index on a public page is exactly that. The terms name a contact for
  permission. **Asking is the recommended next move, and it is one email.**
* **RETRACTED, and this correction is why the survey exists.** This section used
  to call the SportsCardsPro CSV price guide "the clean swap ... no model
  change, no page change, no schema change". **It is not a swap at all.** Their
  own API and CSV documentation states: *"The API and CSV only support current
  item values in various grades and conditions. Historic prices and historic
  sales are not supported."* The CSV is one current value per grade per card. It
  has no `sold_date` and no per sale `price_usd`, so `parse_drop_csv` would skip
  every row; and even reshaped, feeding daily guide snapshots into `card_index`
  would publish a median of somebody else's medians under a method block that
  says "trimmed median of sold comps". The Legendary tier ($49/month) buys that
  CSV plus API access, and its data rights are explicitly internal use only.
  Nobody had ever fetched it. A fallback nobody has fetched is a plan.
* **PSA APR** is now behind a login: both the set and the card pages redirect to
  `app.collectors.com/signin`, for our UA and for an unrelated one. There is a
  paid API (contact `collectors-apis@collectors.com`), terms unknown until asked.
* **130point**, **COMC** and **Heritage** all return 403 behind a JavaScript
  challenge, which only a browser emulation would pass, and passing it is the
  banned move. **Goldin** serves a client-rendered shell with no results in the
  HTML. **Card Ladder** is enterprise-only. **eBay Marketplace Insights** is a
  Limited Release API that eBay's own docs describe as closed to new users.
  **Market Movers** is consumer-app only.

What survives all of that is the path that never needed a source: **manual CSV
drops.** The ingest is interface-shaped for exactly this: `parse_drop_csv`
produces `Comp` rows, `store_comps` appends them, and the export never knows
where a comp came from beyond a `source` string it does not publish. The honest
cost is operator time, a few hundred rows a month to keep forty cards inside a
45-day window at `MIN_COMPS = 5`.

---

## 8. Operating checklist

Fresh box, first run:

1. `python card_prices_ingest.py --build-watchlist` (or accept the committed one)
2. `mkdir -p data/drops` and drop a CSV, or put `EEPHUS_CARD_SCRAPE=1` in
   `/etc/eephus.env` (or both)
3. `python card_prices_ingest.py --scheduled`
4. `python card_market_export.py` and read the `ingest` line it prints
5. rebuild the site; `/cards/` reads `/data/card_market.json`

Steps 3 and 4 are also what the nightly pipeline runs (steps `6g-pre` / `9f`) and
what the crontab runs, so a hand run and a scheduled run do the same thing.

Health checks:

* `python card_prices_ingest.py --stats` prints comps, distinct cards, and the
  first and last sale dates on file. **Local only:** it reports sale dates, which
  is why the export reads `store_health()` instead.
* `python card_market_export.py` prints `meta.ingest.state` and its one-sentence
  reason. **Start here.** It is the difference between "nothing has been
  ingested" and "the scrape fetched pages and parsed nothing", and section 4c
  has the full table.
* `meta.n_priced` in the payload is the number of cards with an index today. If
  it drops sharply, read `meta.ingest` before concluding anything about the
  market: `parse_regression` means the parser broke, not that the hobby went
  quiet.
* The ingest-health table the pipeline prints at the end of every run carries
  `card_drops` and `card_scrape` rows whose `last OK` column answers "when did
  this tap last actually work". `never` on a box that has been running for weeks
  is the signal.
* The page's empty state is deliberate and says where the data comes from. A
  blank board means no comps have been ingested; it does not mean the module is
  broken.

Things that must stay true:

* no raw comp in any committed file
* no second eFV basis on this page
* the screen label stays until a gate actually runs
* the throttle floor stays at 5 seconds
* the ingest has a scheduled caller. It did not for the module's whole first
  life, and the symptom was a board that looked exactly like a healthy board
  with a quiet market.
* an empty board says WHICH kind of empty it is. `meta.ingest` is not
  decoration; it is the only thing separating the honest state from a parser
  regression that would otherwise look identical forever.

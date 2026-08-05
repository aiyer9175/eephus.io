# Baseball Card Market runbook (/cards/)

Module owner files: `card_prices_ingest.py`, `card_market_export.py`,
`assets/cards.js`, `assets/cards.css`, `test_card_market.py`,
`data/card_watchlist.json`. Page shell lives in `build_site.build_cards()`.

Read this before dropping comps, before enabling the scraper, and before
anyone asks why the page will not quote a sale price.

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
* a full sweep must complete inside 60 days, because marketplaces expire their
  own sold windows at 90 and an unseen comp is gone for good

Suggested box wiring (NOT wired into `run_monthly` by this lane; see the
followups handed to the orchestrator):

    # daily tail, after the leaderboards step
    python card_prices_ingest.py --drops
    EEPHUS_CARD_SCRAPE=1 python card_prices_ingest.py --scrape --hot   # optional
    python card_market_export.py

    # weekly (Sunday), long tail
    EEPHUS_CARD_SCRAPE=1 python card_prices_ingest.py --scrape

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

## 7. The licensed swap

If scraping breaks, becomes unacceptable, or simply is not worth the exposure:

* **SportsCardsPro** sells a documented CSV / price-guide product aimed at small
  sites. This is the clean swap. Map its export onto the column contract in
  section 3 (the aliases already cover most of it), drop it at
  `data/drops/card_comps_YYYY-MM-DD.csv`, and delete the scraper call from the
  box schedule. **No model change, no page change, no schema change.**
* **PSA APR** has a paid API (contact `collectors-apis@collectors.com`); the free
  web tier is throttled to roughly one call a day and is not a pipeline.
* **Card Ladder** is enterprise-only. **eBay Marketplace Insights** is closed to
  new users (Limited Release, 90-day window). **130point** is a free manual tool
  with no API and its own ToS fragility. **Market Movers** is consumer-app only.

The ingest is interface-shaped for exactly this: `parse_drop_csv` produces `Comp`
rows, `store_comps` appends them, and the export never knows where a comp came
from beyond a `source` string it does not publish.

---

## 8. Operating checklist

Fresh box, first run:

1. `python card_prices_ingest.py --build-watchlist` (or accept the committed one)
2. drop a CSV, or arm the scraper
3. `python card_prices_ingest.py --drops`
4. `python card_market_export.py`
5. rebuild the site; `/cards/` reads `/data/card_market.json`

Health checks:

* `python card_prices_ingest.py --stats` prints comps, distinct cards, and the
  first and last sale dates on file.
* `meta.n_priced` in the payload is the number of cards with an index today. If
  it drops sharply, look at the ingest log for zero-row scrape warnings before
  concluding anything about the market.
* The page's empty state is deliberate and says where the data comes from. A
  blank board means the export has not run; it does not mean the module is
  broken.

Things that must stay true:

* no raw comp in any committed file
* no second eFV basis on this page
* the screen label stays until a gate actually runs
* the throttle floor stays at 5 seconds

# /betting/ module runbook

Lane C3 of the 2026-08-04d omnibus plan. Everything the Sports Betting module
needs to be operated, argued with, and eventually validated.

Status at ship: **Diamond preview, public, model UNVALIDATED.** Since
2026-08-06 the module publishes PROVISIONAL picks against a policy floor rather
than showing nothing for a season, and since 2026-08-07 there are two slots.
Every one of them is labelled provisional on every surface and none of it makes
the model validated. Section 7a is the selection rule; section 7 is the gate
that would replace the policy floor with a measured one. That is the honest
state, not a bug.

Status of the validation path: **built and empty.** `leaderboard_vintages.py`
snapshots the model's team inputs nightly, `backtest()` grades in two modes and
labels both, and `min_edge` is gated on the vintage sample. Zero vintages have
been captured, so the honest sample is zero games. Section 5 is the clock.

---

## 1. Files

| Path | Owns |
|---|---|
| `betting_ingest.py` | The Odds API snapshot, immutable cache, status sidecar |
| `betting_model.py` | Game probabilities, de-vig, offline fit, the two-mode backtest, the `min_edge` gate |
| `leaderboard_vintages.py` | The dated snapshots of the model's team inputs (the validation path) |
| `betting_export.py` | `data/betting.json`, the preview slice, the append-only record |
| `assets/betting.js` | The six sections, the calculators, the bet tracker |
| `test_betting.py` | The append-only pins plus the shipped-artifact pins |
| `test_leaderboard_vintages.py` | The vintage store, the strictly-before read, both modes, the three gates |
| `test_fixtures/odds_api_mlb_sample.json` | The only odds any test ever reads |

Artifacts written:

| Path | What | Cadence |
|---|---|---|
| `data/betting.json` | Module payload | daily tail |
| `data/betting_preview.json` | Public preview slice (the gating seam) | daily tail |
| `data/betting_status.json` | Odds-feed configuration state | every ingest run |
| `data/betting_record.json` | The public pick record, APPEND ONLY | only via `append_record` |
| `data/betting_model_context.json` | Fitted coefficients + league constants | on demand |
| `data/betting_model_eval.json` | Backtest output, BOTH modes | on demand |
| `.cache/odds/<date>-<hhmm>.json` | Raw snapshots, immutable | daily |
| `.cache/betting/completed_games.json` | Compact game results from the feed cache | on demand |
| `.cache/leaderboard_vintages/<date>.json` | Dated team inputs, ~25 KB each, first write wins | daily |

---

## 2. Odds key setup

The module runs on **The Odds API free tier**, 500 credits a month.

1. Create a key at the-odds-api.com (free tier, no card).
2. On the deploy box, export it for the pipeline user:

   ```
   export EEPHUS_ODDS_API_KEY="<key>"
   ```

   Put it wherever the box already keeps pipeline secrets. It is read from the
   environment only. It is never written to an artifact, never logged, and
   `data/betting_status.json` records only whether one exists.
3. Confirm:

   ```
   python betting_ingest.py --status
   ```

   `configured: true` means the next daily run will pull.

### The credit arithmetic, because the whole plan rests on it

A credit is **markets x regions, per request**.

```
markets = h2h, spreads, totals   -> 3
regions = us                     -> 1
one snapshot                     -> 3 credits
open + close, every day, 31 days -> 186 credits
budget                              500
```

That leaves ~314 credits of headroom for retries, manual pulls and a second
region if one is ever wanted. `test_credit_arithmetic_is_markets_times_regions`
pins it.

**Player props are deliberately not pulled.** Props live behind the per-event
endpoint, which bills per event: a 15-game slate with two prop markets is 30
credits a day and the free tier is gone in about two weeks. The module ships
model fair lines for props with no book comparison instead. If the $30-59 tier
is ever approved, the book side drops in beside the existing rows without
touching the model.

---

## 3. Daily operation

### Open snapshot (morning)

```
python betting_ingest.py --snapshot open
```

Writes `.cache/odds/<date>-<hhmm>.json` and refreshes the status sidecar.
Snapshots are **immutable**: an existing file at the target path raises
`FileExistsError` rather than being overwritten, because a snapshot is the
evidence behind an odds-at-post claim.

### Close snapshot (near first pitch), for CLV

Closing line value needs a second capture. The schedule is data, not a cron
guess:

```python
import betting_ingest as bi, betting_export as be
games = be.slate_games()
bi.closing_window(games)      # UTC ISO minute of the earliest first pitch
```

Schedule the close snapshot a few minutes before that stamp:

```
python betting_ingest.py --snapshot close
```

This module installs no timer. It tells the box when to run; the box owns the
scheduling.

### Leaderboard vintage (nightly, before the payload)

```
python leaderboard_vintages.py --snapshot
```

Offline, idempotent, ~25 KB. This is the validation clock: every night it does
not run is a night the honest backtest cannot buy back later. Section 5 has the
whole story. Check it with `--coverage`.

### Payload

```
python betting_export.py --summary
```

Offline safe. No key, no snapshot, no leaderboards: each degrades to a stated
empty state that names the missing input. It never raises into the pipeline
(`betting_export.refresh_live` wraps it).

---

## 4. The model

### Inputs, all of them already on this site

| Input | Source |
|---|---|
| Team offense | `hitter_leaderboards.json` teams[].offense_plus (HEM+ rollup) |
| Team bullpen | `bullpen_leaderboards.json` teams[].bullpen_plus (REM+ rollup) |
| Rotation | `starter_leaderboards.json` teams[].rotation_plus (SEM+ rollup) |
| The listed probable | `starter_leaderboards.json` starters[].sem_plus + ip_per_gs |
| Park | `fa_meta.json` park_factors[org].runs (Savant, already read by the FA engine) |
| Slate + probables | `fantasy.json` schedule.games (refreshed by run_monthly 9d) |

No new feed. `/betting/` costs the pipeline zero extra StatsAPI calls.

### The scoring model

Two rows per game, one per scoring side:

```
runs_S = b0 + b1*z_off_S + b2*z_prev_O + b3*park + b4*home
```

`z_prev_O` is the opponent's run prevention **for this game**: the listed
probable's own SEM+ over `ip_per_gs / 9` of the game, the opponent's bullpen
for the rest. With no probable announced, the rotation average stands in,
which is what a book does with a TBD.

Coefficients are **fitted, not assumed**, on completed games read out of the
existing `.cache/game_feeds` StatsAPI cache. Fitted values as of the 2026-08-05
build (n = 1,705 completed 2026 games, 3,410 rows). They move a little every
time the leaderboards rebuild, so re-run `--context` after one:

| Term | Fitted | Literature prior (fallback) |
|---|---|---|
| b0 league runs | 4.490 | 4.45 |
| b1 runs per sigma of offense | 0.283 | 0.32 |
| b2 runs per sigma of opposing prevention | -0.326 | -0.32 |
| b3 park pass-through | 3.211 | 3.20 |
| b4 home dummy | 0.012 | 0.09 |

R-squared 0.045 at the game level, which is what a single game of baseball
looks like: mostly noise. League run environment measured at 4.494 per team per
game, home win rate 0.5232.

### Two corrections, both measured, both one parameter

**Home field (`home_field_runs_adj`, fitted 0.215 runs).** The runs regression
recovers almost nothing for home field (b4 = 0.013) while home teams actually
won 52.3% of the same games. Both are right: a home team leading after the top
of the ninth **does not bat**, so its runs-scored column is censored exactly in
the games it wins. The adjustment restores the observed home win rate as a run
differential (+adj/2 home, -adj/2 away), so the runline moves with the
moneyline and the fair total is untouched. 0.215 runs matches the published MLB
home-field differential.

**Margin shrink (`diff_shrink`, fitted 0.78).** The first calibration table
caught the raw predictor spreading games as far as 90/10, with the 0.80+ bin
coming back 0.86 predicted against 0.67 actual. `diff_shrink` scales the run
differential toward zero, holding the pair mean, fitted by minimizing log loss.
0.78 says the linear predictor separated clubs about 25% further than the
results did, which is the normal failure mode for a model stacked out of
already-shrunk season rate stats.

Margin distribution is a Poisson difference by direct convolution (no scipy in
the serving path). Ties are impossible in MLB, so the P(margin = 0) mass is
split by the measured extra-innings home rate, shrunk toward a coin flip on a
100-game prior (raw 0.479 on 140 games, shrunk 0.4875).

### De-vig

**Proportional.** `q_i = 1/decimal_i`, then `p_i = q_i / sum(q)`. A -110/-110
market holds 4.76% and de-vigs to exactly 50/50. Shin and the power method
both take relatively more vig off the longshot and would move every edge on
the page, so the method name travels in the payload and
`betting_model.devig` raises on anything else.

Fair probabilities always come from **one book's two-sided market**. Mixing the
best price on each side across books manufactures a fair line with a negative
hold. The best price and the de-vig source are reported separately.

---

## 5. The validation path: leaderboard vintages

This is the section that matters. Everything above it works; this is the thing
that was blocking the module from having a product.

### The problem, exactly

The model's team inputs are SEASON-TO-DATE leaderboards. Grading a June game
against them means the features already contain that June game's result. The
forward split refits the coefficients on an earlier window, which removes
COEFFICIENT leakage, but the features stay contaminated. That is why `min_edge`
was null and there was no pick of the day.

There is no backfill available. The leaderboards are a full recompute over the
season to date and nothing keeps the intermediate states, so what the numbers
said on 2026-05-14 is simply gone. The fix is not a rebuild, it is a clock:
start writing down what the inputs say each night, and wait.

### What gets snapshotted

`leaderboard_vintages.reduce_current()` reduces the three leaderboards to
exactly what the model reads, and nothing else:

| Stored | From |
|---|---|
| per team `offense_plus` | `hitter_leaderboards.json` teams[] |
| per team `rotation_plus`, `starter_ip` | `starter_leaderboards.json` teams[] |
| per team `bullpen_plus`, `relief_ip` | `bullpen_leaderboards.json` teams[] |
| per pitcher `sem_plus` (or `rem_plus`), `ip_per_gs`, org, role | `starters[]` + `relievers[]` |

Measured size: 30 teams and about 690 pitchers, **25 KB per night**, roughly
4.4 MB for a 180-night season.

Three design decisions, each with a reason:

**One file per date, not one file keyed by date.** A single keyed file is
rewritten in full every night, so one bad write costs the entire archive.
Per-date files cost one night. The archive is evidence that cannot be
regenerated, so the failure mode that loses all of it is the one to design out.

**Under `.cache/`, not `data/`.** `deploy/nightly-build.sh` runs
`git checkout -- .` before every pull, which reverts every TRACKED file the
pipeline wrote. A tracked vintage store would be destroyed each night and would
only ever hold the most recent run. `.cache/` is the box-persistent, gitignored
state the deploy README already names. The cost is that the archive lives on
one box: if the box is ever rebuilt, the clock restarts. Back up
`.cache/leaderboard_vintages/` with `prospects.db`.

**First write wins.** Re-running a date that already has a file is a no-op that
returns the record on disk. A snapshot is evidence of what was knowable; a
later, better-informed run overwriting it would put the leak back. `--force`
exists for a repair and logs that it happened.

### The knowledge cutoff, which is the whole safety property

Each record carries `covers_through` = max(the sources' own `as_of` dates, the
date the file was written). A record may price a game on date D only when
`covers_through < D`. Using the WRITE date in that max is deliberately
conservative: a file written on 2026-08-05 cannot prove it excludes games
played on 2026-08-05, so the earliest game it may price is 2026-08-06. With a
nightly snapshot that costs nothing in steady state (a game on D uses the
snapshot from D-1). Without one it is the difference between an honest backtest
and a dishonest one.

Org codes are canonicalized through `trades.canonical_org` **at write time**,
so a stored record joins directly against park factors and the game feed and
cannot silently drop the eight clubs whose StatsAPI and Baseball-Reference
codes disagree.

### Daily operation

```
python leaderboard_vintages.py --snapshot
```

Idempotent, offline, and a loud no-op when the leaderboards are absent. Wire it
into the daily tail (see section 3). Check coverage with:

```
python leaderboard_vintages.py --coverage
```

which reports the count, the span, the missing days inside that span, and
`earliest_gradable_game_date`. To see which vintage a given slate would be
priced on:

```
python leaderboard_vintages.py --as-of 2026-08-07
```

### How long until the model can be graded honestly

Gradability starts the day AFTER the first snapshot. The gate is on the eval
half of the vintage split, and the arithmetic is:

| Quantity | Value | Where it comes from |
|---|---|---|
| Games needed in the eval window | 600 | `VINTAGE_MIN_GRADED_GAMES`, section 6 |
| Fit window (anchored, not a share) | 300 games | `VINTAGE_FIT_TARGET_GAMES` |
| Gradable games needed | ~900 | 600 + 300 |
| Completed MLB games per calendar date, 2026 | 13.1 | measured over 130 dates |
| **Slate days needed** | **~69** | 900 / 13.1 |

Starting a nightly snapshot on 2026-08-05, that lands in mid October, which is
past the end of the regular season. **The realistic first honest grade is
therefore May or June of 2027**, unless a partial 2026 tail plus an early 2027
run is accepted as one sample (it should not be: the leaderboards reset between
seasons).

The fit window is a target SIZE rather than a share on purpose. A 60/40 split
would need 1,500 gradable games (about 115 slate days) to put 600 in the eval
window. Five coefficients and two one-parameter corrections are comfortably
estimated on 300 games (600 design rows, three times the floor
`fit_coefficients` enforces), so anchoring the fit there and giving everything
later to the eval window buys about 46 slate days.

### The caveat that makes this slower than it looks

**The three leaderboard exports run on the MONTHLY path only** (run_monthly
steps 6b4, 6b4f, 6b4g), and `deploy/nightly-build.sh` runs the full monthly on
the 1st. So the underlying numbers change about once a month even though the
snapshot runs nightly. The store is still correct and the backtest is still
honest, because an old vintage is still strictly-before. But the FEATURES a
vintage offers can be up to 30 days stale, which will make the vintage-mode
model weaker than the contaminated one. That is a quality ceiling, not an
honesty problem, and the fix is to move a cheap team-level leaderboard refresh
onto the daily path. Snapshot nightly anyway: a gap in the store is the only
evidence that the step stopped firing, and the day the exports move to daily
the store gets daily resolution with no rewiring.

---

## 6. The backtest: two modes, both labelled

```
python betting_model.py --backtest
```

Runs offline against `.cache/game_feeds` and reports BOTH modes. Every graded
block carries `mode` and `honest`, so nobody has to remember which column was
which.

### Mode 1: contaminated

| Test | n | Brier | flat .500 | home base | Accuracy | Total MAE |
|---|---|---|---|---|---|---|
| in-sample | 1,705 | 0.24198 | 0.25 | 0.24946 | 56.8% | 3.54 |
| forward from 2026-06-24 | 521 | 0.24416 | 0.25 | 0.24995 | 53.9% | 3.61 |

These move whenever the leaderboards rebuild, so re-read the artifact rather
than this table. The forward Brier in particular moved from 0.24327 to 0.24416
in this lane, for a reason worth recording: the extra-innings tie rate is now
measured on the FIT window (0.500) instead of the whole season (0.4875), which
was a small leak. Removing it made the number slightly worse, which is what
removing a leak usually does.

> The team inputs are SEASON-TO-DATE aggregates. Every game graded above
> contributed to the features used to predict it. The forward split removes
> coefficient leakage by refitting on games before the split date; it does not
> remove feature leakage.

A number worth having, added with this lane: the paired per-game Brier
difference against the home-field baseline. In the forward window it is
**+0.005794 with a paired sd of 0.08647, t = 1.529**. The old claim that "the
model beats both baselines in both windows" is true of the point estimates and
**not significant**, even with the leak helping it. The artifact now reports
`skill_vs_home_base` on every graded block so that cannot be misread again.

### Mode 2: vintage (the honest one)

Each game is priced on the newest leaderboard vintage whose knowledge cutoff is
strictly before it. Games with no such vintage are **skipped and counted**,
never graded on the fallback. Coefficients and both one-parameter corrections
are refit inside the vintage window too, on vintage features, so the mode leaks
nothing at all.

**It starts at n = 0 and stays there until the store fills.** The block reports
`n_vintages`, `n_gradable`, `n_graded`, `n_skipped_no_vintage`, the split date,
and the same metric set as the contaminated blocks.

### The fallback, and why it is loud

`betting_model.inputs_as_of(date)` returns the vintage bundle when one exists.
When none does it returns the LIVE leaderboards with `source:
"live-leaderboards"`, `contaminated: true`, and a once-per-process log warning.
Nothing in the module silently looks forward. The vintage backtest calls it
with `allow_fallback=False`, which returns an empty bundle instead, so it
cannot accidentally grade a game on contaminated features.

---

## 7. The `min_edge` gate

`min_edge` stays **null** until three gates are all open. Check them with:

```
python betting_model.py --gate
```

**Gate 1: vintage sample, 600 graded games.** This number is measured, not
picked to look serious. The forward split's paired Brier margin over the
home-field baseline is +0.005794 with a paired sd of 0.08647, so detecting a
margin that size at one-sided 95% needs

```
n = (1.645 * 0.08647 / 0.005794)^2 = 603 games
```

rounded to 600. Two honesty notes travel with it. A clean margin is very likely
SMALLER than the contaminated one, so 600 games makes the test possible, it
does not make it pass. And 600 is a floor on the SAMPLE, not a substitute for
the test, which is gate 2.

**Gate 2: out-of-sample skill.** On that sample, the paired Brier difference
against the home-field baseline must clear zero at one-sided 95% (t >= 1.645).
Sample size is not evidence. A model that cannot beat "always take the home
team" on games it could not see has not earned a pick.

**Gate 3: a graded price history.** An edge threshold is a claim about EV
against real prices, so it can only be swept on settled bets that have a taken
price. `betting_model.sweep_min_edge(rows)` implements the sweep: for each
candidate threshold it re-grades the qualifying bets at flat 1 unit and accepts
the threshold only when `mean(profit) - 1.645 * stderr > 0`, taking the
SMALLEST qualifying threshold (a higher one is a smaller sample pretending to
be a stronger result). The function is written and tested; what does not exist
yet is the join that turns cached odds snapshots plus completed games into
settled rows. That join is the remaining work on this path, and the odds
snapshots accumulate nightly alongside the vintages, so the two clocks run
together.

Until all three are open:

- `data/betting_model_eval.json` carries `validated: false`, `contaminated:
  true`, `gates_picks: false`, `min_edge: null`, and a `min_edge_gate` block
  naming which gate is closed.
- The MEASURED threshold stays null. What the page publishes against is the
  provisional POLICY floor described in section 7a; the two are different
  numbers with different standing and the payload says which one it used.
- The registry row is `unvalidated` with **no** eval artifact (the registry's
  own honesty rule: an unvalidated row that points at an artifact is lying).

When they open, flip the registry row to `provisional` with
`eval_artifact: data/betting_model_eval.json`, and only to `validated` after a
live season of published, CLV-graded picks.

Do not invent a threshold to make a pick appear. That is the single most
dishonest number this module could publish.

---

## 7a. The two published slots (provisional)

Owner decision 2026-08-06 published a provisional pick rather than showing an
empty module for a season. Owner decision 2026-08-07 split it into TWO slots,
because one slot ranked on EV is one slot that always shows a longshot.

### The floor, which both slots share

`betting_export.resolve_min_edge(evald)` is the ONLY source of a floor on this
page. It returns the measured `min_edge` the moment all three gates in section
7 are open, and `PROVISIONAL_MIN_EDGE` (0.06) until then, plus the basis string
every surface keys its labelling off. Nothing has to be edited when the gates
open.

0.06 is a POLICY number, chosen to be far stricter than anything the model can
currently justify: the whole in-sample margin over the home-field baseline is
0.0079 Brier and the honest margin will be thinner. The intended failure mode is
publishing NOTHING on most slates.

**Both slots read that one floor and no slot may have its own.** A longshot slot
quietly running at a lower threshold so it always has something in it is a
threshold invented to make a pick appear, which the paragraph above names as the
single most dishonest number this module could publish. An empty slot names the
floor it could not clear and stays empty.

### Slot 1: `pick_of_the_day`

The highest MODEL WIN PROBABILITY among floor-clearing sides priced inside
`POTD_ODDS_BAND`, currently -199 to +199 inclusive. Ties break to the price
nearest -110, then to the higher EV per unit; both terms are deterministic, so
two identical boards cannot publish two different picks.

Why not EV: EV is probability times payout and payout dominates, so an EV
ranking selects the longest price on the board nearly every time. On the
2026-08-06 board that put WSN moneyline +304 at a 32.9% model probability in the
headline slot. Honest number, terrible flagship.

All three markets are eligible. A runline or total pick carries `caveat` on the
row (`POISSON_CAVEAT`), because the Poisson-difference margin underdisperses
real run scoring and therefore inflates those two markets' probabilities;
section 11 is the standing account of that limit. The caveat rides the ROW, not
a page-level list, so a client that renders the pick without the list cannot
drop it.

### Slot 2: `longshot_of_the_day`

The highest EV PER UNIT among floor-clearing sides priced at
`LONGSHOT_MIN_ODDS` (+200) or longer, tie broken by the higher model
probability. Ranking these by probability would just pick the shortest of them,
which is the wrong question at a long price.

### Staking

Display units are 1.0u for the headline slot and 0.5u for the longshot
(`SLOT_DISPLAY_UNITS`). The RECORDED stake is `STAKE_UNITS` (1.0) for both, on
the public record and in the shadow ledger, without exception: a published ROI
computed over variable recorded stakes cannot be audited from its own rows,
because a reader would have to take it on trust that the sizing was decided
before the result and not after it. Quarter Kelly (`kelly_full / 4`) is served
as `kelly_quarter` and shown as an information chip, never as a stake.

### Candidate enumeration, and the defect it is defending against

`_floor_clearing_sides` walks the BOARD ROWS `team_bets` already built. It does
not re-read `.cache/odds` and it does not price anything. On 2026-08-06 the
board shopped each side of a market for its best price independently, which
fused Bovada's runline with FanDuel's price for the opposite side and produced a
0.38839 "edge" that the provisional pick immediately selected (commit 628d04e).
The line is now chosen first by book count (`_consensus_point`) and prices and
the de-vig are restricted to books posting it (`_best_price_on_line`). Both
slots and the per-game best-value badge read the output of that, so no two
surfaces on the page can disagree about what a side costs.
`test_betting.test_every_published_slot_is_a_row_off_the_board` pins it.

### Payload shape

| Key | Carries |
|---|---|
| `pick_of_the_day` | slot 1 row or null (the key name is a contract: client, preview and tests read it) |
| `longshot_of_the_day` | slot 2 row or null |
| `pick_reason` | slot 1's reason, pick or no pick |
| `pick_meta` | `provisional`, `min_edge`, `basis`, `policy`, `shared_floor_note`, `n_floor_clearing_sides`, and `slots.<key>` sub-blocks (rule, band, present, reason, n_candidates, stake_units, suggested_units) |

`pick_meta` is in the PREVIEW slice as well as the full payload, since
2026-08-07. It was omitted for as long as the preview existed, which handed the
free tier a pick with no provisional flag, no floor and no basis beside it.

`pick_blockers` is unchanged and still published in full. A provisional pick
does not make any blocker untrue.

### Slot tags in the shadow ledger

Each new shadow row carries `slot`, one of:

| Tag | Written when |
|---|---|
| `potd_band` | the row is the published `pick_of_the_day` |
| `longshot` | the row is the published `longshot_of_the_day` |
| `ev_rank` | the row entered on the EV ranking alone |

`MAX_PER_SLATE` went 3 -> 5 on **2026-08-07**, the date the selection rule
changed: the budget is the two slot picks plus the top three by EV, so a slate
can never log fewer rows than it publishes. The slot picks are taken FIRST,
ahead of the EV ranking, because the headline slot selects on probability and
can sit below the top of the board on EV by construction.

**Rows written before 2026-08-07 carry no `slot` and are NOT backfilled.** They
were selected by the one-slot EV rule and stamping a tag on them now would
assert a fact the writer did not know; `betting_shadow.summary()` counts them
under `untagged`.

FOR THE FUTURE MIN-EDGE SWEEP: condition on the tag, do not pool it. The three
tags select on three different quantities (probability inside a price band, EV
at a long price, EV anywhere), so a pooled ROI measures a mixture nobody bet and
a threshold fitted to that mixture is wrong for every slot it is applied to.
`summary()["by_slot"]` reports the split and deliberately does not merge it.

---

## 8. The append-only record

`data/betting_record.json` is an array. `betting_export.write_record` proves
the write is append-only before publishing:

- shorter than what is on disk -> `RecordImmutabilityError` (a deletion)
- any byte of a leading row differs -> `RecordImmutabilityError` (an edit)
- a published `bet_id` reappears -> `RecordImmutabilityError`
- the file exists but will not parse -> `RecordImmutabilityError` (a corrupt
  record must stop the pipeline, not reset the ledger)

A correction is a NEW ROW, never an edit. `append_record` is the only
sanctioned way in.

Row shape:

```json
{"bet_id": "...", "posted_at": "...", "slate_date": "...", "market": "h2h",
 "selection": "NYM", "book": "draftkings", "odds_at_post": -140,
 "stake_units": 1.0, "result": "open|won|lost|push|void", "settled_at": null,
 "odds_at_close": null, "beat_close": null, "clv_pct": null, "clv_prob": null}
```

Staking is **flat 1 unit, always**. Kelly is displayed as information and never
as a stake, because a variable stake makes a published ROI unauditable.

CLV grading (`grade_clv`) reports two numbers: price CLV
(`decimal_at_post / decimal_at_close - 1`) and probability CLV (raw implied at
close minus at post), plus the plain `beat_close` boolean. It needs the close
snapshot, so it stays null until section 3's close job runs.

---

## 9. Legal rails (non-negotiable)

Every betting surface carries: **21+**, informational and entertainment only,
sports betting is not legal in all states, **1-800-GAMBLER**.

- The block is defined ONCE in `betting_export.DISCLAIMER` and rendered by
  `betting.js` into its own region above the section content, so it is on
  screen for every tab including the failure states.
- `betting.js` also carries `LEGAL_FALLBACK`, a second copy used when the
  payload never arrives. A legal notice that depends on a successful fetch is
  not a legal notice.
- **No affiliate links. No sportsbook links at all.** `betting.js` contains no
  absolute URL, and `test_client_links_nowhere_off_site` pins that. Outbound
  links to books are where state licensing attaches; revisit only with legal
  review.
- No guaranteed-winnings language anywhere. The copy leans the other way: the
  module says out loud that it is unvalidated and that it publishes no picks.

---

## 10. The client

Six sections, hash-routed on `#section=pick|team|props|parlays|calc|mybets`.

**Calculators and My Bets never touch the payload.** They work with no data
file, no odds feed, no account and no network. Pinned by
`test_client_calculators_do_not_depend_on_the_payload`.

**The picks tab renders two cards, each with a PROVISIONAL badge.** Before
2026-08-07 the word `provisional` appeared ZERO times in `assets/betting.js`:
the flag the whole labelling contract rests on was payload-only and never
reached a reader, so a provisional pick rendered exactly like a validated one.
Each card also carries a plain-English sentence built entirely from served
fields, the unit line, a quarter-Kelly information chip, and the row's caveat
when it is a runline or a total. A slot with nothing in it renders an empty
card naming the floor it could not clear rather than disappearing.

**The validation and model panels are COLLAPSED, not removed.** They sit behind
a `<details>` toggle under a one-sentence topline that states the model is not
validated and how far the honest sample has to go. Every word of the
contamination account, the gate table and the backtest is still there. Leading
a casual reader straight into it taught him nothing; hiding it would be
dishonest.

**Per-game best-value badges** mark the single largest floor-clearing edge in a
game and highlight that row in the market table. The threshold comes from
`pick_meta.min_edge`, the same resolved floor the server used to pick the slots,
so the badge and the picks can never disagree about the bar. A game with no
qualifying side gets NO badge; the absence is the information.

**Glossary spans.** The betting vocabulary is registered in
`build_glossary_data.BETTING_ENTRIES` (group `Betting & Markets`) and merged
into the artifact with `python build_glossary_data.py --betting`, which is
additive and idempotent. Do NOT run `build_glossary_data.py --rebuild`: it
regenerates from `prospx/index.html`'s inline `GLOSSARY` block, which no longer
exists, and `data/glossary.json` has been the canonical hand-edited artifact
since that script ran once. `betting.js`'s `gl()` helper no longer emits the
`g-term` class itself, so a slug the artifact does not yet carry degrades to
plain text instead of rendering a term that looks clickable and defines
nothing; `eephus-gl.wire()` adds the class when it resolves the slug.

**Naive same-game parlay math is blocked, not warned about.** Two legs from one
game are correlated, so their product is not a price. Both the board builder
and the standalone calculator refuse to print a number, in both cases with the
reason. The moneyline/runline pair on one team is a hard block (it is one bet
with two prices).

**The Diamond gate is wired and OFF.** `betting.js` reads
`window.EEPHUS_DIAMOND` (emitted as `assets/diamond-config.js` by the
diamond-core lane). With `gating: false`, and with the config file absent
entirely, every reader gets the full `data/betting.json`. If the flag is ever
flipped, a non-member reads `data/betting_preview.json`, which
`betting_export.build` already writes on every run. That is a cosmetic seam,
not a paywall: genuinely gated data cannot live in `/data/` on a static site,
so the real gate is a Supabase-served path or an edge function.

**My Bets** calls `EephusAccount.listBets/addBet/updateBet` when the account
layer is configured and the reader is signed in, and falls back to
`localStorage` (`eephus_bets_v1`) otherwise. It works logged out, and merges
local rows up on sign-in via `mergeLocalBets` when that exists. This module
never edits `assets/eephus-account.js`.

---

## 11. Known limits, stated on the page

- Poisson underdisperses real run scoring. Baseball scores in clumps, so the
  true margin distribution has fatter tails than the convolution assumes.
  Runline and total probabilities sit too close to the middle; the moneyline is
  the least exposed of the three.
- The SERVED prices are still built from season-to-date team inputs, and always
  will be: a live pick has to use the newest numbers. The vintage store fixes
  the BACKTEST, which is what validation needs. Until the vintage sample is
  large enough, every published number about model skill is contaminated and
  labelled so.
- Vintage features can be up to 30 days stale, because the three leaderboard
  exports run on the monthly pipeline path only. Honest, but a quality ceiling
  on the vintage mode. Section 5 has the fix.
- Hitter prop lines assume a projected batting order against a right-hander and
  a PA-by-slot table (4.65 at leadoff down to 3.85 at the nine hole). A posted
  lineup card beats this every time.
- No weather, no umpire, no travel, no injury news beyond what the leaderboards
  already absorb.
- 29 of 30 parks have a Savant runs index in `fa_meta.json`; the missing one
  resolves neutral at lookup rather than being invented.

---

## 12. If it breaks

| Symptom | Cause | Fix |
|---|---|---|
| Page says "odds feed not configured" | no `EEPHUS_ODDS_API_KEY` | section 2 |
| Page says "no slate found" | `fantasy.json` schedule is stale | run the 9d fantasy refresh |
| All 30 clubs missing from the model | org-code mismatch | every join goes through `betting_model._org`; the leaderboards carry StatsAPI codes (SD, SF, TB, KC, AZ, CWS, WSH) and park factors carry Baseball-Reference codes (SDP, SFG, TBR, KCR, ARI, CHW, WSN). Mixing them silently drops eight clubs |
| `coefficients()["source"] == "literature-priors"` | no `betting_model_context.json` | `python betting_model.py --context` on a box with `.cache/game_feeds` |
| `RecordImmutabilityError` on a build | something tried to rewrite history | do not force it. Read the message, find what changed, append a correction row |
| `FileExistsError` from the ingest | two snapshots in the same minute | wait a minute or pass an explicit `when` |
| Log line "no leaderboard vintage strictly before ..." | the vintage store is empty or has a hole covering that date | expected until the nightly snapshot has been running. `python leaderboard_vintages.py --coverage` |
| `vintage.n_graded` stuck at 0 while vintages exist | every completed game predates the first vintage cutoff | expected: gradability starts the day AFTER the first snapshot. `--coverage` reports `earliest_gradable_game_date` |
| `--coverage` shows a run of `missing_dates` | the daily snapshot step stopped firing | fix the step. The gap cannot be backfilled; those dates are gone |
| `min_edge` still null with a big vintage sample | gate 2 or gate 3 | `python betting_model.py --gate` names the closed one |
| Vintage store empty after a box rebuild | `.cache/` was not restored | the clock restarts. Back up `.cache/leaderboard_vintages/` with `prospects.db` |

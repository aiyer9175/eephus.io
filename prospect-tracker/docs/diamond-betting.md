# /betting/ module runbook

Lane C3 of the 2026-08-04d omnibus plan. Everything the Sports Betting module
needs to be operated, argued with, and eventually validated.

Status at ship: **Diamond preview, public, model UNVALIDATED.** Since
2026-08-06 the module publishes PROVISIONAL selections against a policy floor
rather than showing nothing for a season, and since 2026-08-07 there are two
slots. Since 2026-08-16 the two slots are framed as a MODEL WATCH (section 7a):
the selection rules, the provisional labels and the accrual all continue, and
the word "pick" does not, until the three gates in section 7 open. Every slot
is labelled provisional on every surface and none of it makes the model
validated. Section 7a is the selection rule; section 7 is the gate that would
replace the policy floor with a measured one; section 7b is the market-level
gate that can remove a whole market from both slots on ledger evidence. That
is the honest state, not a bug.

Status of the validation path: **running, and no longer empty.**
`leaderboard_vintages.py` snapshots the model's team inputs nightly,
`backtest()` grades in two modes and labels both, and `min_edge` is gated on the
vintage sample. Since 2026-08-09 the store also holds 10 vintages reconstructed
from git history (`tools/backfill_vintages.py`), which took the honest sample
from 41 gradable games to 419 and the first possible grade from 2027 to about
2026-09-16. Section 5 is the clock, section 5a is the reconstruction and the
leakage check it is held to.

---

## 1. Files

| Path | Owns |
|---|---|
| `betting_ingest.py` | The Odds API snapshot, immutable cache, status sidecar |
| `betting_model.py` | Game probabilities, de-vig, offline fit, the two-mode backtest, the `min_edge` gate |
| `leaderboard_vintages.py` | The dated snapshots of the model's team inputs (the validation path) |
| `tools/backfill_vintages.py` | Reconstructs vintages from git history; cutoff is the commit date |
| `betting_export.py` | `data/betting.json`, the preview slice, the append-only record |
| `assets/betting.js` | The six sections, the calculators, the bet tracker |
| `test_betting.py` | The append-only pins plus the shipped-artifact pins |
| `test_betting_market_gate.py` | Section 7b: the ledger leg, the dwell, both seams |
| `tools/betting_calibration.py` | The calibration ledger and `market_gate()` (section 7b) |
| `test_leaderboard_vintages.py` | The vintage store, the strictly-before read, both modes, the three gates |
| `test_backfill_vintages.py` | The commit-date cutoff, the named skips, first-write-wins, the arm split |
| `betting_weather.py` | Section 5h: the pregame forecast capture (armed 2026-09-11), the 5h-C Previous Runs backfill, their two readers, the literature props prior |
| `test_betting_weather.py` | Section 5h: the arming pins, the row-timestamp and issue-time readers, the arm split, the wind geometry, nothing served reads it |
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
| `.cache/betting/market_gate_state.json` | Section 7b dwell state, one evaluation per UTC day | daily tail |
| `.cache/weather_forecasts/<date>-<hhmm>.json` | Section 5h forecast captures, immutable | daily (armed 2026-09-11) |
| `.cache/weather_forecasts/previous-runs-<date>-<hhmm>.json` | Section 5h-C backfill snapshots, immutable, first write wins per game | daily, after the capture, when there are new games |
| `.cache/weather_forecasts/state/backfill_last_run.json` | The last armed backfill run's counts and skips by code; the one mutable file in the store, outside both snapshot globs | daily, after the capture |

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

Closing line value needs a second capture, and the right moment is DATA, not a
cron guess: first pitch moves by hours between a getaway day and a night
slate. The capture is owned by `tools/betting_close_job.py`, which is designed
to be cron'd every 15 minutes ALL DAY and to act once. It exits quietly on
every invocation except the one inside the firing window, refuses to fire
twice for a slate, and refuses to fire after first pitch. On the night it
fires it also grades the published record's CLV sidecar and attaches closing
prices to the calibration ledger (`betting_calibration.append_close`), because
that is the only moment the close is guaranteed to be on disk.

**Install it (promoted into this runbook 2026-08-16, because the job had been
finished for a week while no scheduler on any machine was reaching it):**

- Linux box: install `deploy/betting-crontab.example` with `crontab -e`. The
  entry is `*/15 * * * *` under `TZ=UTC`; every window decision is made inside
  the job, so no cron window is needed and none should be added.
- Windows box: `powershell -ExecutionPolicy Bypass -File
  deploy\betting-close-task.ps1 -Register` (elevated, as the user who owns
  the checkout).
- Verify: `python tools/betting_close_job.py --selfcheck`. It reads the
  heartbeat the job stamps on EVERY invocation, refusals included, and answers
  the question a dry run cannot: has the SCHEDULER ever reached this job on
  this machine. Exit 1 with "NEVER RUN" means no cron or task is installed,
  however finished the code is.
- Inspect today's window without spending a credit:
  `python tools/betting_close_job.py --why`.

As of 2026-08-16, `--selfcheck` reports NEVER RUN on every machine this repo
has touched: the job was never the bottleneck, the installation was. Until it
is installed, `market_move_pct` in the calibration ledger stays null and
`data/betting_learning.json` says exactly that (its market-move block walks
this chain by name). Two defects to know about when reading this path's
history: the crontab example shipped 2026-08-05 with a box-local `12-23` hour
window that closes before most first pitches (fixed 2026-08-09, all-day UTC),
and the job's calibration attach shipped 2026-08-09 filtering the folded
ledger rows on a `phase` field the fold deliberately drops, so its first real
night would have attached zero closes (fixed 2026-08-16; the selector now
reads `close_odds` and `result` off the folded row, and the attach result is
persisted to `.cache/betting/close_attach_result.json`).

A manual capture remains `python betting_ingest.py --snapshot close`; the
snapshot cache is immutable either way.

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
the serving path). Ties are impossible in MLB, so for the MONEYLINE the
P(margin = 0) mass is split by the measured extra-innings home rate, shrunk
toward a coin flip on a 100-game prior (raw 0.479 on 140 games, shrunk 0.4875).

**The runline does not split it, and until 2026-09-11 nothing said so (L14-01).**
The served runline prices home -1.5 as P(margin >= 2) and away -1.5 as
P(margin <= -2), so the whole tie atom is a +1.5 cover for BOTH sides. That is
the unstated claim that no game which goes to extra innings is ever won by two or
more. The same completed-game cache measures it: on 2026-09-11, 193 extra-inning
games in 2,200, the home side won 93 and won by two or more in 10, the away side
won 100 and won by two or more in 51. The asymmetry is the walk-off, the home
team stops batting the moment it leads. So every served +1.5 side is overstated
by the tie mass times the other side's two-run-plus share, and the -1.5 side of
the same pair is understated by exactly as much.

What changed on 2026-09-11, and what did not:

- `betting_model.split_tie_atom` is the ONE reader of the atom. The moneyline,
  the runline and `dfs_export`'s implied team totals all go through it, so the
  two markets can no longer disagree about the same games without it showing.
- The measured split is published every `--context` run as
  `extra_inning_runline_split_fitted`: P(home by 2+ | home won in extras) and
  P(away by 2+ | away won in extras), with the counts. The runline's share of the
  tie is `tie_home` times the first and `1 - tie_home` times the second, which is
  coherent with the moneyline by construction: the runline can never say a side
  wins by two in extras more often than the moneyline says it wins there.
- It is **not served**. `SERVE_RUNLINE_TIE_SPLIT` is False and every served
  price is bit-identical to what shipped. Serving it is a runline pricing change
  and waits on the runline margin gate (B-RUNLINE: held-out both-sides log loss
  at t >= 1.645 at all three split quantiles plus the ledger arm), gated jointly
  with the one-run band in 11a, with a `MODEL_VERSION` bump so the ledgers do not
  pool two pricers. The flag's comment carries the full flip procedure.
- What it would have done is disclosed on the row instead. Every runline board
  row carries a `tie_atom` block (the tie mass, the row's probability and edge
  under the measured split, the counts), and a runline in a published slot
  carries `tie_atom_caveat`, a sentence built from that block and the slot's
  floor with no typed number. On the 2026-09-10 board the headline slot was
  CHW +1.5 at an edge of 0.08747; under the split it is 0.05161, under the 0.06
  floor, and the slot would have gone to PIT at CHW Over 7.5.
- The model's tie atom is not a calibrated chance of extra innings: 0.1352 at
  the league run environment against an observed extras rate of 0.0877. The
  split moves the runline toward the observed margin distribution; it does not
  calibrate it.

**Served since 2026-09-11, by owner decision.** The bullets above are left as
written. Later the same day the owner answered the decisions list (item 4,
"reprice now"): `SERVE_RUNLINE_TIE_SPLIT` is flipped on, ahead of the B-RUNLINE
gate the "not served" bullet says it waited on, so the owner's decision is the
basis and no gate result is claimed for it. The runline now gives each +1.5 side
only its measured share of the tie atom, and the labs that read a runline
probability (the backtest's per-market grade and the 11a dispersion arms) price
it on their fit window's own split. It shipped in the same pricer change as the
short-sample parks (5i-A) and two-way starters on the starter board (owner
decision 23), under ONE `MODEL_VERSION` bump, `betting_runs_v1` to
`betting_runs_v2`, so the ledgers never pool the old and new pricers; v1 rows
stay v1. The flag's comment in `betting_model.py` and the commit that flipped it
carry the measured moves on the board it shipped against. The last measurement
recorded in this document is the one above, where the 2026-09-10 headline CHW
+1.5 falls from an edge of 0.08747 to 0.05161, under the 0.06 floor.

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

The leaderboards are a full recompute over the season to date and nothing keeps
the intermediate states, so the numbers cannot be RECOMPUTED for 2026-05-14.
The fix for everything forward is a clock: start writing down what the inputs
say each night, and wait. What that argument missed for four days is that the
boards are TRACKED artifacts and every rebuild since 2026-07-05 is a blob in git
history. Section 5a is the reconstruction.

### What gets snapshotted

`leaderboard_vintages.reduce_current()` reduces the three leaderboards to
exactly what the model reads, and nothing else:

| Stored | From |
|---|---|
| per team `offense_plus` | `hitter_leaderboards.json` teams[] |
| per team `rotation_plus`, `starter_ip` | `starter_leaderboards.json` teams[] |
| per team `bullpen_plus`, `relief_ip` | `bullpen_leaderboards.json` teams[] |
| per pitcher `sem_plus` (or `rem_plus`), `ip_per_gs`, org, role | `starters[]` + `relievers[]` |
| per park runs index (schema 2 and later) | `fa_meta.json` park_factors[org].runs |
| dark capture columns (schema 3 and later): team `off_vs_lhp` / `off_vs_rhp` / `xwoba_14` / `xwoba_30` / `lineup_strength` / `star_out`, pitcher `throws` | section 5c; nothing served reads them |

Measured size: 30 teams and about 690 pitchers, **25 KB per night**, roughly
4.4 MB for a 180-night season.

**The park leak (plan F1.1) is CLOSED, and this is the check.** The park was the
one model input that was never dated, so `backtest()` in vintage mode read the
LIVE `park_index()` (the in-progress season) to price and to fit games it then
called leak-free. Verified on the tree as it stands: `leaderboard_vintages
.SCHEMA` is 2 and `reduce_current` writes a `parks` block;
`betting_model._vintage_resolver` returns a 3-tuple whose third element is the
vintage's own park index or `NEUTRAL_PARK_INDEX`; and `_grade` rebinds
`gt, gs, gpk = got` and passes `parks=gpk`, not the enclosing live `parks`. One
record in the archive predates the bump, the live 2026-08-05 capture, and it is
schema 1 with `parks: null`: games priced on it get a NEUTRAL park and are
counted in `vintage.park_basis`, which is the conservative direction (the park
term is dropped, not invented). Every backfilled record carries 29 parks.

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

Gradability starts the day AFTER the earliest knowledge cutoff in the store. The
gate is on the eval half of the vintage split, and the arithmetic is:

| Quantity | Value | Where it comes from |
|---|---|---|
| Games needed in the eval window | 600 | `VINTAGE_MIN_GRADED_GAMES`, section 6 |
| Fit window (anchored, not a share) | 300 games | `VINTAGE_FIT_TARGET_GAMES` |
| Gradable games needed | ~900 | 600 + 300 |
| Gradable on 2026-08-09 | 419 | backfill + live store, section 5a |
| Still to accumulate | ~481 | 900 - 419 |
| Completed MLB games per calendar date, 2026 | 13.1 | measured over 130 dates |
| **Slate days still needed** | **~37** | 481 / 13.1 |
| **First possible honest grade** | **about 2026-09-16** | 2026-08-09 + 38 slate days |

Before the git reconstruction this table read 69 slate days from a standing
start of zero, landed in mid October, and concluded that **the realistic first
honest grade is May or June of 2027**. That conclusion is withdrawn: it rested
on the premise that no backfill was possible, and section 5a is the backfill.

> **Recomputed 2026-08-16, and now published nightly by the artifact itself.**
> This arithmetic is the `gradable_games` clock in
> `data/betting_learning.json` (new 2026-08-16, section 5b), so the table and
> the artifact can no longer do the same sum on different numbers: both read
> `n_gradable` and its measured growth.
>
> | Quantity | Value | Where it comes from |
> |---|---|---|
> | Games needed in the eval window | 600 | `VINTAGE_MIN_GRADED_GAMES` |
> | Fit window in front of them | 300 | `VINTAGE_FIT_TARGET_GAMES` |
> | Gradable games needed | ~900 | 600 + 300 |
> | Gradable on 2026-08-16 | 507 | `betting_model_eval.json` vintage block |
> | Graded (eval window) on 2026-08-16 | 258 | same block; the half-date clamp splits 38 archive dates at 2026-07-28, 249 fit / 258 eval |
> | Still to accumulate | ~393 | 900 - 507 |
> | Archive growth, measured | 12.4 games per calendar day | 507 games over the 41 days 2026-07-06 to 2026-08-15 |
> | **Slate days still needed** | **~32** | 393 / 12.4 |
> | **First possible honest grade** | **about 2026-09-17** | 2026-08-16 + 32 days |
>
> If a 504-day figure for this module is in your head, read section 5b: it
> was a measurement bug in the learning artifact's rate, not a property of
> the archive.

Four caveats ride with the new date and none of them are small.

1. **The no-pooling rule STANDS.** A 2026 tail plus an early 2027 run is not one
   sample and must never be graded as one. The leaderboards reset between
   seasons, so a vintage from September and a vintage from April are not
   measuring the same quantity. The reconstruction moves the date precisely
   because it keeps the whole sample inside 2026.
2. **Gate 1 opening is not gate 2 passing.** 900 gradable games makes the paired
   Brier test possible at the designed power. It says nothing about whether the
   model clears it, and a clean margin is very likely smaller than the
   contaminated +0.005794.
3. **Every missed nightly snapshot costs a day**, and the reconstruction cannot
   buy those back going forward: git only holds what the pipeline committed, and
   the pipeline commits the boards on the monthly path.
4. **The date assumes 13.1 completed games per calendar date holds.** September
   slates are full, so this is the reasonable direction to be wrong in, but a
   rainout week pushes it.

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
vintage offers can be stale, which will make the vintage-mode model weaker than
the contaminated one. That is a quality ceiling, not an honesty problem, and the
fix is to move a cheap team-level leaderboard refresh onto the daily path.
Snapshot nightly anyway: a gap in the store is the only evidence that the step
stopped firing, and the day the exports move to daily the store gets daily
resolution with no rewiring.

> **Correction, 2026-08-16.** The paragraph above is out of date and stands as
> the record of why the fix exists. The three team leaderboards have refreshed
> NIGHTLY since step 9e-pre0 landed on the daily path (run_monthly.py:2125,
> "Refresh the boards the vintage is about to freeze"): the daily tail
> rebuilds the bullpen, starter and hitter leaderboards immediately before the
> vintage snapshot freezes them, skipping only on nights the monthly chain
> just built them. The staleness ceiling this passage describes was real and
> is closed going forward; `vintage_age_days` in the coverage block is the
> instrument that verifies it stays closed.

That staleness is now MEASURED rather than bounded by a guess.
`coverage()["vintage_age_days"]` publishes the distribution of "how old were the
features that priced this date" every time coverage is reported, and
`backtest()` copies the whole coverage block into `vintage_coverage`, so it
reaches `data/betting_model_eval.json` on the next build without any rewiring.
On the archive as it stands:

| Basis | n | median | p90 | max | mean |
|---|---|---|---|---|---|
| Graded game dates | 419 | 3 days | 10.2 | 13 | 4.08 |
| Calendar days in the archive | 36 | 2 days | 10 | 13 | 3.86 |

The GAME-weighted row is the one `backtest()` now publishes.
`backtest()` used to call `coverage()` with no arguments, which weights an off
day the same as a fifteen-game Saturday and reported the calendar row beside an
`n_graded` the calendar row is not about. It now passes the graded game dates,
so the number sitting next to `n_graded` is the one a reader of `n_graded` is
asking for. The published vintage is STALER than the calendar view said,
because this archive's holes fall on days that carry games.

The worst stretch is the 2026-07-16 to 2026-07-29 gap, where the pipeline
committed no board for 13 days. That is honest and it is weak, and a reader is
entitled to both halves of that sentence. `coverage()` takes the calendar basis
by default and the game basis when it is handed `game_dates`; the two answer
different questions and an off day is not a Saturday.

**Worth knowing before anybody "improves" this number.** Writing the 2026-08-03
duplicate day would move the published game-weighted median from 3 days to 2
while adding no leaderboard information at all: its three boards are the same
blobs as 2026-08-01. A whole day of apparent freshness, bought with nothing.
That is why the backfill refuses the date.

---

## 5a. The git reconstruction of the clock

### The argument

`data/hitter_leaderboards.json` and its two siblings are TRACKED. Every rebuild
since 2026-07-05 is therefore a blob in git history, and **a blob committed at
time T cannot contain information created after T**. A vintage reduced from that
blob and stamped with the COMMIT DATE is leak-free by exactly the same argument
the nightly clock rests on, and it exists today rather than in nine months.

`tools/backfill_vintages.py` resolves, for each candidate date, the newest blob
of each source committed at or before that date, extracts it with `git show`
into a temp directory, and calls `leaderboard_vintages.snapshot(data_dir=...)`
against it.

### The four rules it runs under

**The cutoff is the commit date, never the blob's own `as_of`.** `as_of`
describes the data a board was built from; the commit date describes when the
board existed. The rule is conservative BY CONSTRUCTION, not by anecdote: a
board can only be built from data that already exists, so `as_of <= commit
date` always, and taking the later of the two can only make a vintage price
FEWER games. `reduce_current` then takes
`covers_through = max(sources' as_of, on_date)`, which cannot walk that back.
Arm 3 below pins it empirically at 0 forward-dated violations over 10 records.
The commit date used is max(author date, committer date), because a rebase
moves one and not the other and the later of the two is the first moment the
tree can prove the blob existed.

> **Correction, 2026-08-09.** This paragraph used to cite commit d50c1afb,
> "Regen: one coherent vintage behind the identity repair", as a counterexample
> in this tree - a commit that supposedly rewrote all three boards under a stamp
> chosen by the regen rather than by the calendar. **That is verified FALSE.**
> d50c1afb has author date 2026-08-04 16:46:48 -0400, committer date
> 2026-08-04 16:46:48 -0400, and all three blobs at that commit carry
> `as_of 2026-08-04`. Every clock agrees; the commit is not a counterexample to
> anything. The RULE is unchanged and still correct, because it never needed the
> anecdote: it rests on the construction argument above. The same false sentence
> is also carried by `tools/backfill_vintages.py` and the
> `leaderboard_vintages.py` module docstring and is being removed there
> separately.

**First write wins, across both clocks.** A live nightly record read the working
tree, which is a superset of what was committed, so it is the better evidence
for its own date. An overlapping date resolves to the live record and the skip
is counted and named. The tool has no `--force` and never passes one.

**A date that adds no new board is not written.** 2026-08-03 resolves to the
2026-08-01 boards plus a newer `fa_meta`. Writing it would add zero feature
information and would pull the published vintage-age distribution down, making
the archive look fresher than it is. The cost is one day of a slightly newer
park index, and park factors are a multi-year regressed index that barely moves
inside a season.

**Nothing is written into `data/`.** Blobs are extracted to a temp directory and
the store is `.cache/leaderboard_vintages/` as always.

### What it produced

| Quantity | Value |
|---|---|
| Candidate commit dates | 35 |
| Reduce cleanly | 13 |
| Written | 10 (2026-07-05 through 2026-08-04) |
| Skipped, no required board in history | 22 (2026-06-09 to 2026-07-03) |
| Skipped, already captured live | 2 (2026-08-05, 2026-08-06) |
| Skipped, no new board | 1 (2026-08-03) |
| Store after | 15 vintages: 10 backfilled, 5 live |
| Gradable completed games | 41 before, 414 after (419 on the cache today) |
| Vintage backtest status | `no vintages` before, `graded` at n = 221 after (211 on the cache today) |

Every written record carries `provenance.source: "git-backfill"`, the sha of the
board that set the cutoff, the per-source sha map, and
`cutoff_basis: "git commit date"`. A live snapshot carries
`provenance.source: "live"`, and a record with no provenance block at all reads
as live by definition: the five records on disk when the block shipped all came
off the nightly clock. `coverage()` counts `n_vintages_backfilled` and
`n_vintages_live` separately and never blends them, because the arm split below
is unaskable if it cannot tell them apart.

### The pre-registered leakage check

**Written into this file before the arms were graded.** The whole reconstruction
rests on an argument about git, not on a measurement, so it needs a way to be
caught being wrong. If the backfilled sample scores MATERIALLY BETTER than the
live sample, the most likely explanation is that a blob reached forward in a way
the commit-date argument did not anticipate, and the backfill is discarded.

Three arms, and the discard rule is any one of them firing:

**Arm 1, matched games (the primary).** Games on 2026-08-06 through 2026-08-08
can be priced by BOTH stores: the backfilled arm's newest cutoff is 2026-08-04
and the live arm's oldest is 2026-08-05. Price each of those games twice, once
per store, with an identical coefficient set, and take the paired per-game Brier
difference (live minus backfilled). Same games, same model, so the difference
isolates provenance. **Discard the backfill if mean(diff) > 0.005 with a paired
t > 1.645.** 0.005 is chosen because it is the size of the model's ENTIRE
measured edge over the home-field baseline in the contaminated forward window
(+0.005794): a provenance artefact as large as the whole claimed effect would
make the sample useless for the gate that effect is measured by. Note the
direction of the prior: the backfilled arm is 2 to 4 days STALER on these games,
so it should score slightly WORSE, and a positive result is doubly suspicious.

**Arm 2, full arms (the brief's literal ask, and underpowered).** Grade each
store on every game it can price, report Brier and n for both, and compare each
arm's skill against its own home-field baseline so that different schedules
cannot be mistaken for different provenance. **Discard if the backfilled arm's
skill margin exceeds the live arm's by more than 0.005794.** This arm is
reported as a description, not as a test: the live store can price about 31
games, and with a per-game Brier sd near 0.086 that is a standard error of about
0.0155, so the smallest difference it could detect at one-sided 95% is about
0.0255, roughly 4.4x the effect it is being asked to rule out.

**Arm 3, forward-dated sources.** For every record the backfill writes,
`max(source as_of) <= vintage_date` must hold: no board in the archive may have
been built from data dated after the day its record claims to be.
**Discard on any violation.** Beside it, and NOT as a discard condition, rebuild
2026-08-05 and 2026-08-06 into a scratch directory and report how far the
reconstruction differs from the live capture of the same date, as a descriptive
reproduction measure.

> Arm 3 was rewritten once, before any arm was graded, and the first version is
> recorded here rather than deleted. It read "discard if a reconstructed record
> carries a source `as_of` later than the live capture's for the same date". It
> was mis-specified: the live 2026-08-05 capture ran before that day's hitter
> board was committed, so the reconstruction IS sharper on that date, and it
> still cannot price a single game the live record cannot, because both are
> stamped 2026-08-05 and both may price only 2026-08-06 onward. The rule would
> have fired on a non-leak. The replacement tests the property the git argument
> actually rests on. The trigger for the rewrite was reading the five live
> records' `as_of` fields, which happened before any Brier was computed; arms 1
> and 2 are untouched.

### Result: all three arms clear, the backfill is KEPT

Recorded 2026-08-09, after the rules above were written into this file.

| Arm | Measurement | Threshold | Fires |
|---|---|---|---|
| 1, matched (n = 41 as first run; n = 46 on the store today) | mean(live - backfilled) = **-0.000406**, paired sd 0.011373, t = **-0.229**. Under four named specifications on the current store the mean is **+0.00045 to +0.00117**, max t **+1.070**: see the retraction below | mean > 0.005 and t > 1.645 | **no**, under every specification |
| 2, full arms | skill gap backfilled minus live = **+0.004274** | gap > 0.005794 | **no** |
| 3, forward-dated | **0 violations** over 10 backfilled records | any source `as_of` > `vintage_date` | **no** |

**Arm 1 clears its threshold. The SIGN ARGUMENT that used to sit here is
RETRACTED.** The measurement recorded above (41 matched games,
mean(live - backfilled) = -0.000406) was read as evidence: the backfilled arm is
2 to 4 days staler, it scored slightly worse, that is what a leak-free store
should do, and "a leaking store would have shown the opposite sign".

That last clause is wrong. **The sign is a free parameter of an unpinned
specification.** The pre-registration said "an identical coefficient set" and
never said WHICH one, and arm 1 prices the same 46 games under whatever set the
reader supplies. Re-run 2026-08-09 on the store as it now stands, under four
NAMED specifications:

| # | Coefficient specification | mean(live - backfilled) | paired sd | t |
|---|---|---|---|---|
| A | served set: `coefficients()` + `league_context()["extra_inning_home_rate"]`, `home_adj` None, `diff_shrink` None | **+0.000450** | 0.011688 | +0.261 |
| B | vintage-window refit, 208 games - what the honest mode actually uses | **+0.001167** | 0.007399 | +1.070 |
| C | full-archive in-sample fit, corrections off | **+0.000790** | 0.015395 | +0.348 |
| D | literature priors, corrections off | **+0.000603** | 0.017511 | +0.234 |

n = 46 for every row, 2026-08-06 through 2026-08-09, same games, same store,
same test. All four are POSITIVE, and the value recorded when arm 1 first ran
was NEGATIVE. A quantity that changes sign when the coefficient set changes is
not measuring provenance.

**The discard rule still does not fire, and that is the part that matters.**
It requires mean > 0.005 AND t > 1.645. The largest absolute mean across all
four specifications is 0.001167, which is 4.3x under the threshold, and no
specification reaches t = 1.645. KEEP survives under every spec, so the
backfilled sample counts and the 419-game gradable archive stands.

**What the pre-registration owed and did not carry: the coefficient set.** Arm 1
is only a test if the set is named before it runs. Spec A above is the one this
document is pinned to going forward - `coefficients()` plus
`league_context()["extra_inning_home_rate"]`, with `home_adj` and `diff_shrink`
left None so they resolve from the context file - and the other three are
published beside it precisely so nobody can pick a spec after the fact. The
honest summary of arm 1 is narrow and it is enough: **no specification produces
a provenance effect anywhere near the size of the effect the gate is trying to
measure.** It is not evidence about direction.

> The four rows above do not reproduce the numbers recorded when arm 1 first
> ran, and they are not supposed to: the live store has grown from 3 records to
> 5, the matched set from 41 games to 46, and the vintage fit window from 193
> games to 208. Two intermediate readings taken on the smaller store, +0.002126
> at t = +1.447 under the vintage refit and +0.000937 at t = +1.629 under the
> full-archive fit, are recorded here rather than dropped: they are the same
> sign and the same order of magnitude as rows B and C, and neither fires the
> discard rule either.

**Arm 2's gap is positive and under the bar.** The backfilled arm grades 414
games (Brier 0.253536 against a 0.249014 home-field baseline, skill -0.004522,
t = -1.232); the live arm grades 41 (Brier 0.257458 against 0.248662, skill
-0.008796, t = -0.725). The +0.004274 gap is the difference between grading 414
games across five weeks and grading 41 games in three days: two schedules, not
two provenances. Both arms lose to the home-field baseline.

That sentence used to end "on the SAME games the backfilled arm is the worse of
the two", and it no longer does, because that reading came from arm 1's sign and
arm 1's sign is retracted above. Arm 2's gap is unexplained by anything measured
here. It is also 4.7x under its own threshold and the arm is underpowered by its
own pre-registration, so "unexplained" costs nothing: nothing in it approaches
the size that would discard the backfill.

The power caveat from the pre-registration held and was slightly optimistic in
the arm's favour. It assumed 31 live games at a per-game sd of 0.086; the live
store had grown to five records and 41 gradable games by the time this ran, sd
0.0776, so the standard error is 0.0121 and the smallest gap arm 2 could detect
at one-sided 95% is about 0.0199. That is still 3.4x the effect it was asked to
rule out. Arm 2 remains a description. **Arm 1 is a bounded null, not a
direction:** it says no specification produces a provenance effect near the size
that would matter, and it says nothing about which store is fresher.

**Arm 3, reproduction.** The 2026-08-06 rebuild from git is IDENTICAL to the
live capture of the same date: same 30 teams to the last digit, 696 pitchers
both, 29 parks both. 2026-08-05 differs, and the difference is instructive:
the live capture ran before that day's hitter board was committed, so it carries
`as_of 2026-08-04` and schema 1 with no park column, while the reconstruction
carries `as_of 2026-08-05`, schema 2 and 29 parks, with a largest per-team
`offense_plus` difference of 3.0. Both are stamped `covers_through 2026-08-05`
and neither may price a game before 2026-08-06, so the sharper record buys no
game the other cannot have.

**One measured cost of first-write-wins.** Keeping the live 2026-08-05 record
keeps a schema 1 record, so the 11 completed games of 2026-08-06 are priced on a
NEUTRAL park (`vintage.park_basis.n_eval_games_neutral_park` = 11). The
reconstruction of that date carries 29 parks and would recover the park term for
them. That is an owner decision, not a bug, and the fix if it is ever wanted is
one explicit repair, never a tool default:
`python leaderboard_vintages.py --snapshot --date 2026-08-05 --force` is NOT it
(it would read today's boards); it would take a hand run of the backfill's
extraction against a forced snapshot. Left alone.

### What the honest mode says now that it runs

`vintage` has moved from `status: "no vintages"` to `status: "graded"` for the
first time. It is not good news and it is not supposed to be:

| Quantity | First run (1,761 games cached) | Current (1,766 games cached) |
|---|---|---|
| Gradable | 414 | **419** |
| Split date | 2026-07-24 | **2026-07-25** |
| Fit window / graded eval window | 193 / 221 | **208 / 211** |
| Brier | 0.25045 | **0.24920** |
| Brier, home-field baseline | 0.24885 | **0.24797** |
| Accuracy | 50.7% | **52.6%** |
| Paired skill vs home base | -0.001603, sd 0.05482, t = -0.435 | **-0.001224**, sd 0.05358, **t = -0.332** |
| Games priced on a neutral park | 11 of 414 | 11 of 419 |

**The model LOSES to "always take the home team" on the honest sample, by an
amount that is not distinguishable from zero.** Five more cached games moved the
split date by one day, which moved ten games from the eval window into the fit
window and moved every number in the right-hand column. The headline did not
move: the sign is still negative, |t| is still under 0.5, and the deficit is
still smaller than its own noise. Gate 1 is still closed (211 of 600 graded) and
gate 2 is currently failing rather than merely unmeasured.

That is the number the reconstruction was built to produce nine months early,
and it is the one that was always the likely one: the contaminated forward
margin is +0.006624 at t = 1.931 on the same cache, which was +0.005794 at
t = 1.529 when the 600-game floor was derived and has never been significant at
a size that survives removing the leak.

**The dispersion correction in section 11a does not move this number, and could
not have.** It did not clear its gate and is not served, so the honest mode is
priced by the same Poisson it always was. Even had it passed, its moneyline arm
was non-inferior at BEST (paired Brier delta -9.3e-05, one-sided 95% lower bound
-0.000383): a correction that is at best neutral on the moneyline cannot rescue
a -0.001224 moneyline deficit. The run distribution being wrong is a real
defect and it is not the reason this model does not beat the home team.

---

## 5b. The learning artifact's clocks, and the 504-day story (2026-08-16)

`data/betting_learning.json` publishes the module's progress as measured
arrival rates applied forward. Since 2026-08-16 it carries THREE clocks:

| Clock | Numerator / need | Question |
|---|---|---|
| `vintage_sample` | `n_graded` / 600 | gate 1's own counter: eval-window games graded |
| `gradable_games` | `n_gradable` / ~900 | the archive itself: 600 plus the 300-game fit window in front of them. This is the clock section 5's ETA table runs on |
| `graded_price_history` | settled rows / 100 PER TAG | gate 3, one clock per selection rule, never pooled (section 7a) |

### The 504-day story, which was a measurement bug

On 2026-08-16 the artifact published the vintage clock at 0.68 graded games a
day and a 504-day ETA to the 600-game gate, in a season where MLB completes
~13.1 games per calendar date. A 19x gap between the world and the instrument
is never one bug. `tools/betting_clock_probe.py` (read-only; run it) measured
where every factor of it lives, with an unexplained remainder of ~0:

| Factor | Size | Mechanism |
|---|---|---|
| Series-youth denominator inflation | 7.0x | `measured_rate` divided 19 arrivals from a 4-day diffable span by the full 28-day window. Arrivals predating the first history row (221 games were already graded when the series began on 2026-08-10) were dropped from the numerator while their days stayed in the denominator, and the window exceeded the series age outright |
| Fit-boundary absorption | 2.0x | `n_graded` counts EVAL-window games only. While the fit window holds fewer than `VINTAGE_FIT_TARGET_GAMES` (300; it held 249), the half-of-dates clamp governs the split (`_vintage_cut_index = min(target_idx, half_idx)`, verified target_idx 23 vs half_idx 19 on 38 dates), so the eval counter receives roughly half of the archive's growth |
| Missed and zero-increment nights | 1.3x | 2026-08-15 produced no learning row at all, and 2026-08-12 ran against an eval artifact that had not refreshed its graded count |
| Schedule constant vs this archive's density | 1.06x | 13.1 is measured over 130 season dates; this archive window ran at 12.4 |

7.0 x 1.97 x 1.32 x 1.06 = 19.3. The games were arriving on schedule the
whole time; the instrument was wrong, twice by construction and once by
operations.

Two repairs shipped the same day, both in `betting_learning.py`:

- `measured_rate`'s denominator is now `min(window_days, series age in days)`.
  The age and the effective window are published beside the rate, and the old
  full-window figure is kept as `per_day_28d` so the fix can never be read as
  the module having sped up. First corrected build: 5.3 graded games a day and
  a 65-day ETA, against the 0.68 and 504 it replaced.
- The `gradable_games` clock publishes the archive's own numerator and its
  measured rate (12.4 gradable games a day on the same build, ~32 days to
  ~900), which is the quantity the graded counter systematically understates
  by the fit-boundary factor above.

### The gate-versus-clocks denominator trap

The artifact's gate table used to be copied from `betting_model_eval.json`,
which freezes at model refit time, while the clocks read the live shadow
ledger the same night. On 2026-08-16 the frozen gate said `board_all` had 47
settled rows while the clocks said 72: one artifact, one quantity, two
denominators. The build now always recomputes `betting_model.min_edge_gate`
against the ledger as it stands, stamps the result `computed_at`, and keeps
the eval's copy beside it as `gates_as_of_eval`, so the drift stays visible
instead of being resolved silently.

### What the empty market-move block may claim

The calibration ledger's `market_move_pct` stays empty until the close job
runs (section 3 has the install runbook). The artifact's `blocked_by` used to
name `data/betting_clv.json` as the repair, but that file is the published
record's CLV sidecar and no calibration row is built from it; worse, whenever
the sidecar existed the block asserted a book mismatch no run had measured.
It now walks the real chain by name (close job, close snapshot ingest,
`betting_export.close_events_for_calibration`,
`betting_calibration.append_close`) and claims a book mismatch only off the
attach result the close job persists to
`.cache/betting/close_attach_result.json`.

---

## 5c. Schema 3: the dark feature capture (pre-registered 2026-08-16)

**This section is written before the schema bump it describes exists in code
and before any captured number has been looked at**, in the same discipline as
5a, 7b and 11a. The columns below start accruing tonight; nothing served reads
them, and nothing served changes.

### Why capture columns nobody prices on

Every candidate feature this module might ever test needs the same thing the
core inputs needed: a dated archive, accrued BEFORE anyone looks at whether the
feature helps. A column added to the vintage record tonight is measurable in
four to six weeks; a column added the day somebody wants it is measurable never,
because its history would have to be reconstructed from live season-to-date
files, which is the leak this whole store exists to close. So the schema is
bumped once, the columns accrue dark, and the measurement protocol (below) is
already on the record.

### The columns and where each one comes from

Team columns added (`TEAM_COLUMNS` grows from 5 to 11):

| Column | Source tonight | Basis |
|---|---|---|
| `off_vs_lhp` | `hitter_leaderboards.json` teams[].orders.vl, PA-weighted mean of per-slot `hem_plus` | populated. Verified on the 2026-08-16 artifact: 30 teams, 540 order slots, 0 missing `pa` or `hem_plus` |
| `off_vs_rhp` | teams[].orders.vr, same reduction | populated, same verification |
| `xwoba_14` | **no committed source exists.** No team-level rolling-xwOBA builder is on any pipeline path (checked 2026-08-16: `hitter_export` carries per-hitter season xwOBA only) | captured as null with the basis naming the missing builder. The schema is ready; the number is not invented |
| `xwoba_30` | same | same |
| `lineup_strength` | builder is a later lane | null with a stated basis |
| `star_out` | builder is a later lane | null with a stated basis |

Pitcher column added (`PITCHER_COLUMNS` grows from 4 to 5):

| Column | Source tonight | Basis |
|---|---|---|
| `throws` | `pal_export.load_pitch_hand(season)`, **one bulk StatsAPI call at assembly**, never a per-game lookup | populated when the fetch succeeds; null with the fetch failure named in the basis when it does not |

One caveat rides with the two order splits and it is a fact about the source,
not about the capture: on nights the batSide lens is down, `platoon_applied` is
false and the vl and vr orders are byte-identical (see `hitter_export`'s
platoon availability block), so the two captured values are the same number.
The capture stores what the artifact said; the stored basis is how a reader
finds out which kind of night it was.

### The rules, which are the park precedent applied verbatim

- **Old records return None for the new columns.** A schema-2 record read under
  the schema-3 reader yields None for every new column, through an explicit
  stated fallback, never a silent zero. Zero is a value on every one of these
  scales; None is the absence of one.
- **Per-record marking.** Every schema-3 record carries a `feature_basis` block
  naming, per new column, where the value came from or why it is null. The
  existing `park_basis` reporting in the backtest is KEPT unchanged for
  back-compat and the new block generalizes it: the backtest's vintage block
  reports, per feature, how many graded games carried a dated value, how many
  carried a stated null, and how many rode a record that predates the column.
- **`inputs_as_of` never fills a new column from live files.** A vintage that
  lacks a column serves None for it. Filling it from tonight's leaderboards
  would put the exact leak back that the store exists to remove.
- **One standardization.** Everything that reaches the model goes through
  `betting_model._assemble_team_inputs`, the same seam the five core columns
  use, so the day a candidate is measured its z-scores are computed by the
  identical code on the live path and the vintage path.
- **Dark means dark.** No served price, no slot, no record row and no exported
  edge reads any of these columns. They exist in the record, in the assembled
  team inputs, and nowhere else, until a candidate clears the protocol below.

### The B3/B4 candidate protocol (rolling form, availability)

Pre-registered now so the first measurement cannot shape its own rules:

1. **Each candidate gets its own gate section in this document before any
   number is computed on it.** The section names the estimand, the split, the
   criteria and the thresholds, the way 11a and 11b do. A candidate measured
   before its section exists is disqualified, whatever it measured.
2. **The clock: 4 to 6 weeks of schema-3 vintages minimum** before the first
   measurement. Schema 3 landing tonight starts that clock; the earliest
   admissible first look is 2026-09-13, and a candidate whose column was null
   over the accrual window (the xwOBA pair, until a builder exists) has not
   started its clock at all.
3. **The B3 permuted-team control.** Every rolling-form candidate is scored
   against its own permuted twin: the same fit with the candidate column
   permuted across teams within each date. Rolling form is partly team quality
   wearing a trend costume, and the twin is what separates "the feature helps"
   from "the feature smuggles offense_plus in again". A candidate that does not
   beat its twin is a null whatever its headline delta says.
4. **Serve requires BOTH legs**: the contaminated-forward diagnostic (the cheap
   large-n screen on season-to-date features, labelled contaminated, which can
   only ever DISQUALIFY a candidate, never qualify one) AND calibration
   non-degradation on the vintage eval half, under the same two-criterion form
   the 11b gate uses (paired Brier improvement at one-sided t >= 1.645, paired
   log loss not worse on the point estimate). Availability candidates (B4:
   `star_out`, `lineup_strength`) carry the additional burden that their
   builder must be on the nightly path before their clock starts.

### Correction (2026-08-19): the clock started 2026-08-18, not 2026-08-16

The pre-registration above is left as written; this note corrects the clock
against what is actually on disk. The first schema-3 vintage in
`.cache/leaderboard_vintages/` is `2026-08-18.json` (`schema: 3`). The
`2026-08-16.json` vintage exists but carries `schema: 2`, so the columns did
not accrue that night, and two nights have no vintage file at all: 2026-08-15
and 2026-08-17. Rule 2's clock therefore starts 2026-08-18, and under the
strict 4-week floor the earliest admissible first B3/B4 look moves from
2026-09-13 to ~2026-09-15. Nothing else in the protocol changes; a null-column
candidate still has no clock at all.

### Correction (2026-08-19b): the four null columns got their builders

The table above that says "no committed source exists" / "builder is a later
lane" for xwoba_14, xwoba_30, lineup_strength, and star_out is superseded:
all four dark-capture builders shipped 2026-08-19 in leaderboard_vintages.py
(xwoba pair by cumulative difference against the newest git-committed hitter
board on or before D-14/D-30, 7d anchor tolerance, window-PA floors 100/200;
lineup_strength from the day's captured orders joined to projected year-1
wOBA, >= 7 of 9 slots per side; star_out from the roster IL cache over the
top projected players). The 2026-08-19 vintage predates the builders and
first-write-wins keeps it, so BY RULE 2 those four columns' clocks start with
the 2026-08-20 vintage, and their strict 4-week earliest look is ~2026-09-17.
A source gap still degrades a column to a stated null with its basis, never a
silent zero.

### Correction (2026-09-11): `lineup_strength` changed membership at `7cd5f572`, and its clock restarts

**Standing.** Filed under the reading of rule 1 that the 2026-09-10 5e correction
used: a pre-registration may be amended before its first look, on a fact established
without touching outcomes. `lineup_strength` has not been looked at. Its clock opened
with the 2026-08-20 vintage (2026-08-19b correction), and for this column only that
start date is superseded below; the rest of both 2026-08-19 corrections stands.
Written 2026-09-11, four days after the change, where X9 (plan 4.2) asks for the same
day. It lands in one commit with the 2026-09-11b correction below, whose reading its
dates use, no later than 2026-09-15 (plan 5.1, the I3 deadline). It goes beyond plan
item I3, which asked only that the ~2026-09-17 look report pre/post counts: it moves
this column's look to 2026-10-05. The plan edits that needs are listed at the end.
**Nothing in this correction was measured against a game result.** Read to write it:
- the diff and message of `7cd5f572`;
- `as_of`, `generated_at` and the `roster_filter` block of the committed hitter boards
  `944502c5` and `7cd5f572`;
- per vintage file 2026-08-18 to 2026-09-10: `schema`, `vintage_date`, `captured_at`,
  `covers_through`, `provenance.source`, `sources[*].as_of`, and the
  `feature_basis.lineup_strength` basis string and `n`;
- code: `hem_plus.team_offense`, `bullpen_export._active_mlbam_ids`,
  `leaderboard_vintages` (`reduce_current`, `snapshot`, `as_of`,
  `lineup_strength_from_orders`), `betting_model._feature_basis`,
  `tools/backfill_vintages.py`.

No column value, score, run, win probability or price was read.

**What changed.** Commit `7cd5f572` ("Nick Kurtz was batting second for the Athletics
while out for the season", 2026-09-07 12:04:02 -04:00, 16:04:02Z) gave
`hem_plus.team_offense` an `active_ids` argument. The constructed `teams[].orders.vl` /
`.vr`, `lineup` and `bench` in `hitter_leaderboards.json` now draw only on hitters on a
StatsAPI active roster (`rosterType=active`). Before it, `build_batting_order` took the
top nine by season PA from every hitter with a HEM+ and a plate appearance, injured or
optioned included. The commit message measures 37 of 270 constructed lineup slots
(13.7%) held by players off an active roster before the change and 0 of 270 after.
Offense+ stays on the full season pool; `test_the_aggregates_are_not_filtered`
(`test_roster_aware_charts.py`) pins `offense_plus` and `team_pa`.

`lineup_strength` is built from those orders.
`leaderboard_vintages.lineup_strength_from_orders` averages projected year-1 wOBA
(`mlb_projections.json vets[].woba[0]`) over each side's joined slots, and drops a side
that joins fewer than `LINEUP_MIN_JOINED_SLOTS` (7) of 9. The builder has not changed
since `3eda89d7` (2026-08-19). The set of players it averages over changed, and no 5c
text recorded it.

**Which vintages are on which side.** The record carries no roster-filter flag. The
split is read off capture time and the committed boards:

| Side | Vintages (all live, `feature_basis` n 30 each) | Evidence |
|---|---|---|
| pre-change | 2026-08-20, 08-21, 08-23, 08-24, 08-27, 08-30, 08-31, 09-03, 09-04, 09-05, 09-06: 11 nights over 18 calendar days | All captured before 16:04:02Z on 2026-09-07. The last, 2026-09-06, reduced a board stamped `as_of` 2026-09-05, and the committed blob with that stamp (`944502c5`) has no `roster_filter` block |
| post-change | 2026-09-07, 09-09, 09-10 (on disk 2026-09-11) | 2026-09-07 was captured at 17:04:38Z, one hour after the commit, from a board stamped `as_of` 2026-09-07. The one committed board with that stamp (`7cd5f572`) reads `roster_filter.applied` true, `n_active_roster_ids` 839, `n_dropped_from_constructions` 232, 0 clubs `roster_filter_skipped`. The vintage stores no hash of its source board, and the daily path rebuilds the boards before the snapshot (step 9e-pre0), so this is consistent with a filtered night, not proof of one |

`n_dropped_from_constructions` sums each club's `n_off_roster_dropped`: hitters removed
from the construction pool (`hem_plus.py:588`), not slots, whatever the name says.

Under the knowledge cutoff (section 5: a record prices D only when
`covers_through < D`), games dated 2026-08-21 to 2026-09-07 are priced on pre-change
vintages, and games from 2026-09-08 on are priced on post-change ones.

**The treatment.**

1. **The clock restarts with the 2026-09-07 vintage.** Rule 4's B4 burden is that the
   builder be on the nightly path before the clock starts. The only part of this column
   that reads availability is the active-roster filter on the orders, and that code was
   on the path from `7cd5f572`, committed one hour before the 2026-09-07 capture. The
   start rests on the code, not on that night's roster walk; the walk is a per-night
   question, handled below. Under the 2026-09-11b reading the four-week floor is
   **2026-10-05**.
2. **Why not pool. This extends the record and is stated as an extension.** The 5e
   correction held that rows whose two columns "could not differ" were "uninformative
   about this candidate by construction". The pre-change rows here can differ, but they
   measure a construction the live path no longer produces, and 11 of the 14 populated
   nights on disk are pre-change, so a pooled verdict would mostly grade that
   construction. The nearest standing no-pooling rule is section 5 caveat 1 (a 2026
   tail and a 2027 run are never one sample). 7a's "measures a mixture nobody bet"
   (slot tags) and 5h's "never pool two pricers" (ledgers) are analogies only.
3. **The pre-change vintages are kept and never graded for this column.** They stay on
   disk as written (first write wins) and are never force-rewritten. A game priced on
   one goes to a fourth bucket, "pre-change membership" (to be built, see 2026-09-11b),
   outside `lineup_strength`'s graded n. Every other column those records carry is
   graded as before.
4. **The pre-change side is never read on its own.** It stopped at 11 nights over 18
   calendar days, short of the rule 2 floor, and no later night can extend it.

**The look: once, on 2026-10-05.**
- Read once, on 2026-10-05 or the first day after it on which the pinned harness runs,
  never earlier. No second read on 2026 data. A 2027 test is a new registration under
  N9 (plan 4.2), never a continuation (section 5 caveat 1).
- The graded window is fixed now: games priced on vintages 2026-09-07 to 2026-10-04 and
  dated before 2026-10-05, regular season only by default (O25 below). A later run
  reads the same games.
- The incumbent and the harness are those of the ~2026-09-17 B3/B4 look, by commit. If
  that look is not recorded, the incumbent is the served pricer at the commit that
  lands this correction, and the harness commit is named in a dated note filed before
  any `lineup_strength` number exists.
- Fit, counting and the night floor are the 2026-09-11b rules for the four 5c columns.
  At 13.1 games a date (section 5), the 20 regular-season dates 2026-09-08 to
  2026-09-27 hold about 260 games, about 130 a half, before any bucket removal.
- A look that cannot run records INDETERMINATE, neither passed nor closed, with no
  second 2026 read. That covers fewer than `VINTAGE_MIN_FIT_GAMES` (100) inner-fit
  games, fewer than `VINTAGE_MIN_EVAL_GAMES` (50) graded games, a missed night floor,
  and a fit or twin that cannot run.

**Nothing on this column is computed before its look.** No fit, paired score, permuted
twin or rule 4 leg 1 contaminated-forward screen is computed for `lineup_strength`
before 2026-10-05. The ~2026-09-17 harness (to be built) leaves it out of its candidate
list, and a test (to be built) pins that the 09-17 run never fits, scores or twins it.
For this column that look reports counts only:
- the vintage nights on each side, listed;
- the graded eval games in each bucket;
- the post-change nights whose filter state the record cannot show.

**The close-variant embargo moves with the look.** Until the `lineup_strength` look is
recorded, no posted-lineup, active-roster or lineup-strength variant is related to an
outcome or a price. That includes either side of the change alone, another roster
source, another projections input, 5j's delta and 5j's contaminated screen. `star_out`
and the xwOBA pair are registered columns, not variants, and keep the ~2026-09-17 date.

**Disqualification.** Any number relating `lineup_strength`, either side of the change,
or a variant above to a game outcome or a price before the 2026-10-05 look
disqualifies the candidate under rule 1.

**The projections retrain (plan step M), decided now.** Step M can move the joined
`woba[0]`. Projections coverage also decides which slots reach the 7-of-9 join, so it
can move who is averaged. Step M does not land before 2026-09-27 (2026-10-04 if O25
counts postseason), so no vintage that prices a graded game reads a retrained bundle.
This amends the O11 default ("after the 2026-09-17 look and the 2026-09-18 read"). It
costs the plan nothing, because W2 places step M after the ~2026-10-05 freeze. If step M
lands earlier anyway, every vintage written after it goes to an ungraded
"post-retrain" bucket; no later record decides this. Any other projections refresh is
part of the construction registered in 2026-08-19b and buckets nothing.

**Postseason, DEFAULT (new owner decision O25, open).** The regular season ends
2026-09-27. By default postseason games are not graded here, as in 5f and 5g, because
October rosters are what this column's filter reads. This diverges from the owner's
2026-09-11 answer that 5e counts postseason, though 5e reads the same orders; O20
covers 5j only. O25 goes into the plan's decision table and is locked by 2026-09-15.
After that date no amendment to `lineup_strength` is admissible.

**What the record cannot show per night, and the stamp that will.**
- **Board-level fallback.** `bullpen_export._active_mlbam_ids` returns None when the
  team-list fetch fails, or when fewer than `MIN_CLUBS_FOR_ROSTER_FILTER` (28) of 30
  club walks return a roster. Nothing is then filtered and the board reads
  `roster_filter.applied` false.
- **Per-club fallback.** In a 28- or 29-club walk, a club whose fetch failed matches no
  bat. `hem_plus.team_offense` (lines 589-594) then serves that club the unfiltered
  nine and sets `roster_filter_skipped`, while `applied` reads true.
- **Unreadable ids.** A hitter with no readable mlbam is kept (line 587).
- **The stamp (to be built; no stored value changes).** From the first vintage after
  this correction lands, the `lineup_strength` basis string carries:
  - the board's `roster_filter.applied`;
  - `n_dropped_from_constructions`, in hitters;
  - the list of clubs with `roster_filter_skipped`;
  - the count of kept hitters with no readable mlbam.

  A game is pre-change membership when the board reads `applied` false or either club
  is on the skipped list.
- **Nights before the stamp, from 2026-09-07 on**, are graded as post-change and
  counted as "filter flag unrecorded". 2026-09-07 is one of them.

**Other readers of the same orders.**
- `off_vs_lhp` / `off_vs_rhp` (5e) changed membership at the same commit. Their clock
  restarted at "the first vintage whose `platoon_splits.available` is true", after the
  2026-09-10 repair, so it opens after this change. A night on pre-change membership
  still carries a real hand split, which is 5e's candidate, so 5e grades it. The stamp
  above rides in the `off_vs_*` basis too, and 5e's look reports the nights with
  `applied` false and the skipped club-games. 5e counts postseason. If 3 or more
  eliminated clubs' active rosters come back empty in October (unverified; no probe
  run), `_active_mlbam_ids` returns None, and the stamp records it.
- The schema-5 readers of the orders or bench (5i-B `lhb_share_vr/vl`; 5f
  `lineup_dis_vs_*`, `bench_adv_vs_*`) landed in code on 2026-09-11, after the change,
  and have no vintage yet. They carry the same stamp (to be built).

**Forward.** Any later change to which players enter `teams[].orders` is recorded here
the same day (X9). Its treatment before 2026-10-05 is fixed now: vintages written after
it go to their own ungraded bucket, the clock does not restart again, and the look reads
only the nights before the change. Under the night floor that can make it INDETERMINATE.

**Plan edits this needs** (`docs/master-plan-2026-09-11-war-epoch-drivers-betting.md`):
- 5.1, the ~2026-09-17 row: drop `lineup_strength`.
- 5.1, a new 2026-10-05 row: the `lineup_strength` look, once. Preconditions: no
  posted-lineup, active-roster or lineup-strength variant related to an outcome or a
  price, and step M not landed.
- E5 and O11: step M comes after the 09-17 look and the 09-18 GRPO read, and not before
  2026-09-27 (2026-10-04 if O25 counts postseason).
- W1 and the dependency spine: the 09-17 look is the xwOBA pair and `star_out`.
  R4-candidate computation follows the 2026-10-05 look.
- 4.1 (5j): the contaminated screen and any 5j close-variant number wait for the
  2026-10-05 look.
- 4.2, I3: record that this correction moves the look, beyond "reports pre/post
  counts".
- 6: add O25.
- 7.2, risk 7: for `lineup_strength`'s variants, "before 09-17" becomes "before 10-05".

**Not reopened.** No criterion, control or threshold in rules 1 to 4 is amended. For
this column, this correction changes:
- the clock start and the look date;
- the pinned incumbent and harness;
- the buckets and the embargo;
- the earliest date for step M.

The xwOBA pair and `star_out` keep the ~2026-09-17 date, subject to rule 1 (see
2026-09-11b). They were cleared against `7cd5f572` only. The xwOBA pair reads
`hitters[]`, the full season pool (`leaderboard_vintages.py:752-761`). `star_out` reads
`vets[].warY1Champ` and the cached 40-man roster. No other construction change between
2026-08-20 and 2026-09-17 was audited for them here.

### Correction (2026-09-11b): rule 2 counts calendar weeks, and what a missing night costs

**Standing.** Rule 2 stays as written. This correction is filed under the same reading
of rule 1 (amendable before a first look, on a fact established without touching
outcomes) and lands with the correction above, no later than 2026-09-15.
**Nothing in this correction was measured against a game result.** Read to write it:
- the file names in `.cache/leaderboard_vintages/`, and each file's `schema`,
  `vintage_date`, `captured_at`, `covers_through` and `provenance.source`;
- `leaderboard_vintages.snapshot`, `reduce_current`, `as_of` and `_age_distribution`;
  `betting_model.inputs_as_of` and `_feature_basis`; `tools/backfill_vintages.py`;
- `git log` of the three boards since 2026-08-17.

**The fact.** Rule 2 says "4 to 6 weeks of schema-3 vintages". It does not say whether
a week is seven calendar days or seven files. On this box nights are missing (plan I2
records the same list):

| Window | Nights | Files | Missing nights |
|---|---|---|---|
| schema 3 and later, 2026-08-18 to 2026-09-10 | 24 | 16 (14 schema 3; 2 schema 4, which carry every schema-3 column) | 2026-08-22, 08-25, 08-26, 08-28, 08-29, 09-01, 09-02, 09-08 |
| B3/B4 builder columns, 2026-08-20 to 2026-09-10 | 22 | 14 | the same 8 |

All 16 files are live provenance, with `captured_at` on their own `vintage_date` and
`covers_through` equal to it. No 2026-09-11 file existed when this was written. The
reading below was chosen with these counts in hand. It keeps every date on the record,
and the floor in point 2 was set knowing it cannot bind the ~2026-09-17 look.

**The reading.**

1. **A week is calendar time.** A column's clock starts on the date of the first present
   night (point 3) that carries it populated under its registered construction. The
   four-week floor is that date plus 28 calendar days. A missing night neither stops the
   clock nor moves the floor. Every date already on the record was computed this way,
   and none moves:
   - 2026-08-18 to ~2026-09-15, and 2026-08-20 to ~2026-09-17 (the 2026-08-19
     corrections);
   - 2026-09-09 to 2026-10-07 (5d);
   - 2026-09-07 to 2026-10-05 (the correction above).

   A clock restarts only before the column's first look, and only on a code change
   named by commit. A value refresh never restarts one, and nothing restarts one once
   any number relating the column to an outcome exists.
2. **A night floor.** At least 14 of the 28 nights from the clock start to the floor
   must be present, or the look is INDETERMINATE. 14 is half, and it is POLICY.
   Without a floor, two files 28 days apart would satisfy rule 2. It was set with the
   counts above in hand. The B3/B4 window (2026-08-20 to 2026-09-16) already holds 14
   present nights, so the floor cannot bind the ~2026-09-17 look and guards only the
   later ones. The `lineup_strength` window (2026-09-07 to 2026-10-04) holds 3 of its
   first 4 nights.
3. **A present night.** Night D is present when three things hold: `<D>.json` exists,
   its `provenance.source` is live, and its `captured_at` UTC date is D or D+1. All 16
   files on disk today qualify. A backfilled record is never a present night and never
   prices a graded game for a dark column.
4. **What a missing night costs.** At the store, no game. `as_of` prices a game on D
   from the newest same-season vintage whose `covers_through` is before D, and there is
   no maximum age. So a game after a gap rides the last vintage before it, one or more
   days older. `vintage_age_days` (game date minus that cutoff, `_age_distribution`)
   measures the cost. Counting files instead would tie the floor to pipeline uptime and
   move every date above. Two exceptions:
   - A gap just after a column's first file sends games to an older vintage. They fall
     in "predates the column" and leave the graded n.
   - The 5d day-specific columns (`pen_b2b_arms`, `pen_arms_avail`, `pen_ip_l3`,
     `pen_plus_avail`, `rest_days`, `games_in_l7`, `sp_rest_days`) are built at
     `on_date=vintage_date` (`leaderboard_vintages.py:1616`; pitcher columns at
     1752). A game priced across a missing night carries a value for a different day,
     which is wrong, not stale. For these columns, a game with `vintage_age_days` of 2
     or more goes to an ungraded bucket, "priced across a missing night". This is filed
     before any 5d number. It does not settle 5d's steady-state offset (vintage V
     prices V+1 games on availability as of V), which is for 5d to file before
     2026-10-07.
5. **A missed night stays missing.**
   - **It is never written late, with or without `--force`.** `snapshot(on_date=D)`
     run after D reduces the boards as they stand at the write and stamps
     `vintage_date` D. It sets `covers_through` to the max of the boards' `as_of` and D
     (`leaderboard_vintages.py:1718`). Only the boards' `as_of` bounds it, and that can
     lag the write date (the 2026-09-06 file reduced boards stamped 2026-09-05). Its
     date-keyed builders (xwOBA anchors, pen availability, climatology windows) would
     run for D over later boards and feeds, so one record would mix dates, and its
     file would show D as present. A refusal in `snapshot` for a past `on_date` on
     live provenance is to be built.
   - **The git backfill writes none of them.** `tools/backfill_vintages.py` plans only
     dates that carry a board commit, and never forces (line 246). Where it does write,
     it runs the full `reduce_current` through `lv.snapshot` (line 383), dark builders
     included, and some of them read live `.cache` files. No board was committed on any
     of the 8 missing dates. The board commits since 2026-08-17 are `69fe0fca`
     (2026-09-04), `944502c5` (2026-09-06) and `7cd5f572` (2026-09-07), all on dates
     already captured live. "Reconstruct only the five core inputs" is N1's rule
     (plan 4.2), not a property of this tool. Point 3 keeps any future backfilled
     record out of every dark column's graded n.
   - `inputs_as_of` never fills a dark column from live files (5c). Section 5 caveat 3
     already says "Every missed nightly snapshot costs a day".

**The report, fixed now so the look cannot choose it.** For every column read under
rule 2, the look reports the items below. They are to be built in the look harness and
in `betting_model._feature_basis`. Today that function has three statuses, covers the
schema-3 columns only, and marks a record populated when any club has a value.
- the clock start, the floor, and the nights present and missing between them, with
  the missing dates listed;
- the graded eval games by pricing vintage, in 5c's three buckets (dated value, stated
  null, predates the column), plus "pre-change membership" for `lineup_strength` and
  "priced across a missing night" for the 5d day-specific columns;
- of the dated-value games, how many rode a vintage 2 or more days old, with their
  game-weighted `vintage_age_days`.

**Graded n and the fit, for the four 5c B3/B4 columns only** (`xwoba_14`, `xwoba_30`,
`star_out`, `lineup_strength`).
- **Graded n.** A game is dated-value only when BOTH clubs carry a value in the pricing
  vintage (5f's form). The code's record-level count is not this; the game-level count
  is to be built. The graded n is the dated-value games. A game in any other bucket is
  counted and reported. It is never scored, and it never enters as a zero paired
  difference, because None is not zero (5c, "Old records return None"). Section 6
  recomputes the other tiers on a subsample's own games; that is an analogy for grading
  only the games that carry the feature, not a rule that requires it.
- **The fit.** Every game in the anchored fit window (the first
  `VINTAGE_FIT_TARGET_GAMES`, 300, split near 2026-07-28 to 2026-08-01 per section 5's
  2026-08-16 table and 5h-C) rides a vintage that predates schema 3. So no fit-half row
  carries a value, and a zero-filled coefficient is unidentified. The fit therefore
  takes 5h-A's form:
  - The incumbent keeps every parameter as fitted on the anchored window.
  - The parameters the candidate adds are fitted by least squares on the incumbent's
    per-side residual (runs minus lambda), over the dated-value games before the
    calendar midpoint of the dated-value game dates, first to last.
  - Games on or after the midpoint are graded.
  - The split date is written into the look record before any fit and never moved.

  The graded games all fall in the vintage eval half, so rule 4 reads as written. At
  13.1 games a date (section 5), the 27 dates 2026-08-21 to 2026-09-16 hold about 350
  games for the ~2026-09-17 look, about 175 a half.
- **The ~2026-09-17 window.** At that look the B3/B4 window holds at most 20 of 28
  nights: 14 on disk through 2026-09-10, plus 2026-09-11 to 2026-09-16 if none of those
  nights is missed.

**Scope.**
- The calendar reading (points 1, 3 and 5) and the night floor (point 2) govern every
  clock counted in vintage files under rule 2: the four 5c columns, 5d, the restarted
  5e, 5f and 5g.
- The graded-n and fit rules govern the four 5c columns only. Sections with their own
  null or fit rules keep them: 5e's effective n; 5f's exclusions, `g = 0` one-hand
  null and fit-half delta zero; 5g's criterion 4. The anchored fit window predates
  schemas 3 and 4 alike, so 5d-A's "existing vintage fit/eval split, unchanged" and
  5e's replacement face the same fit fact. Each settles it in its own text before its
  look.
- 5d takes point 4's day-specific bucket.
- 5i-B qualifies each vintage by its own basis counts. A night with no file is read the
  same way there; beyond that, 5i-B's clock is its own.
- 5h is out of scope. Its store is `.cache/weather_forecasts`, and its clock starts at
  `clock_started`. `forecast_for_game` returns None when no row was captured at least
  `MIN_LEAD_HOURS` ahead, so a missed capture night does remove games from its
  400-game floor.
- Where a section adds a game floor (5g 600/300), that floor applies alongside the
  calendar weeks.

**Not reopened, and not settled.** No criterion, control or pass threshold is amended.
This correction adds:
- a clock condition (the night floor);
- two ungraded buckets;
- the fit treatment for the four 5c columns, which rule 4 left open.

Rule 1 is unchanged. Each of the four columns still needs its own gate section
(estimand, split, criteria, thresholds) committed before any number is computed on it.
None is on the record today: the four appear only in sections 5 and 5c. Those sections
inherit the rules here. The missing nights are an operational fault (plan I2), not
evidence about any candidate.

## 5d. Schema 4: bullpen availability, schedule rest, weather (pre-registered 2026-09-07)

**Written before the schema bump it describes exists in code and before any
captured number has been related to any outcome**, in the same discipline as 5a,
5c, 7b and 11a. The columns below start accruing tonight; nothing served reads
them and nothing served changes. Coverage checks are reported here because 5c
set that precedent (it verified 30 teams and 540 order slots before writing its
own table); a coverage count is not a measurement of whether a feature helps.

### The owner ask this answers

Three things, asked 2026-09-07: adjust for lineup strength against the
handedness of the starting pitcher; work out which relievers are unavailable
tonight and price that ("if a reliever is used 2 days in a row, they usually
never pitch the next day"); and look for weather correlations.

The first needs no new column. `off_vs_lhp`, `off_vs_rhp` and the pitcher's
`throws` have accrued since 2026-08-18 and its gate is section 5e below. The
other two are new and are what this schema bump is for.

### Where the data comes from, and why none of it is a new dependency

`.cache/game_feeds` holds 20,490 complete StatsAPI live feeds. Both new families
read that cache and nothing else: no new API, no new credential, no new nightly
call. Coverage on a 400-feed random sample (seed 0), checked 2026-09-07:

| Signal | Path | Coverage |
|---|---|---|
| game-time weather | `gameData.weather.{temp,condition,wind}` | 400 of 400 |
| wind with a direction | `gameData.weather.wind`, e.g. `"9 mph, Out To CF"` | 400 of 400 |
| pitchers used, in order | `liveData.boxscore.teams[side].pitchers` | 400 of 400 |
| per-arm workload | `...players["ID<mlbam>"].stats.pitching.{outs,pitchesThrown}` | present on the sampled arms |

Wind directions parse to a closed vocabulary: `Out To LF/CF/RF`, `In From
LF/CF/RF`, `L To R`, `R To L`, `Calm`, `Varies`, `None`.

### The columns

Team columns (`TEAM_COLUMNS` grows from 11 to 20):

| Column | Source | Basis |
|---|---|---|
| `pen_b2b_arms` | relievers appearing in this org's feeds on BOTH of the two prior calendar days | populated whenever both prior days resolve; a club's off day is a real zero, not a null |
| `pen_arms_avail` | rostered relievers not flagged unavailable by the availability rule below | populated when the bullpen leaderboard and the prior feeds both resolve |
| `pen_ip_l3` | bullpen outs over the three prior days, divided by 3 | populated |
| `pen_plus_avail` | the club's `bullpen_plus` recomputed over AVAILABLE arms only, innings-weighted | populated; **this is the servable form of the ask** and it drops straight into `game_prevention_z`, where `bullpen_plus` already sits |
| `rest_days` | days since this club's previous game; 0 on the second leg of a doubleheader | populated |
| `games_in_l7` | this club's games in the seven prior days | populated |
| `wx_temp_climo` | mean observed temperature at THIS venue within a +/- 7 calendar-day window, over seasons STRICTLY BEFORE the vintage date | populated where the venue has >= 10 prior-season games in the window; null with the count otherwise |
| `wx_wind_out_climo` | same window, mean signed out-to-centre wind component (out +, in -, lateral and calm 0) | same rule |
| `catch_frame_rate` | called strikes above the league's own rate in the same location bin, per 100 taken pitches, trailing 30d (section 5d-D) | populated; 30 of 30 clubs on the 2026-09-07 window |

Pitcher columns (`PITCHER_COLUMNS` grows from 5 to 7):

| Column | Source | Basis |
|---|---|---|
| `sp_rest_days` | days since this pitcher's previous appearance in any cached feed | populated when a prior appearance exists; null on a season debut, with that stated |
| `sp_tto3_bf` | mean batters faced for the 3rd+ time per start, trailing 30d, min 2 starts (section 5d-E) | populated for 173 pitchers on the 2026-09-07 window; null below the start floor |

### The availability rule, named before it is measured

A reliever is UNAVAILABLE for today when either holds, evaluated on feeds dated
strictly before today:

- he appeared on **both** of the two prior calendar days, or
- he appeared **yesterday** on 30 or more pitches.

Both numbers are POLICY, not measurement, and are named as such the way
`PROVISIONAL_MIN_EDGE` and `SLATE_OPEN_MIN_PREGAME_SHARE` are. The
back-to-back-two-days rule is the owner's own statement of the convention and
matches ordinary bullpen practice; 30 pitches is the common threshold for a
heavy outing. Nothing in this repo can derive either, and the honest way to hold
them is to publish them, not to tune them. **Tuning either constant against
outcomes before the gate below runs would be fitting the feature to the eval
window**, which is the failure this whole store exists to prevent. If a
candidate clears its gate, a sensitivity check across neighbouring constants is
a SEPARATE, later question.

### Weather cannot be served from observed weather, and that is the whole design

`gameData.weather` is the weather AT THE GAME. It is not known before the game,
so a model priced pregame on it is reading the future. This is not a small
leak: temperature is exactly the sort of variable whose observed value is most
correlated with the thing it would be predicting.

So the two families are kept apart, deliberately:

- **The vintage store gets CLIMATOLOGY only.** `wx_temp_climo` and
  `wx_wind_out_climo` are built from seasons strictly before the vintage date,
  at the same venue, in a calendar window around the same date. That is dated
  history and is servable.
- **Observed weather is a CONTAMINATED SCREEN and never a column.** The size of
  the true weather effect is measured directly off the game feeds, labelled
  contaminated, under the existing rule for such diagnostics: it can only ever
  DISQUALIFY a candidate, never qualify one. If climatology cannot see an effect
  that the observed screen says is large, that gap is a statement about
  forecastability and it is the honest place to stop, not a licence to serve the
  observed value.
- **A real forecast is a separate decision with a cost.** Serving a same-day
  forecast means a new external dependency and possibly a paid one. It is not
  taken here and is not implied by anything above.

### The gates

Each candidate family gets its criteria named now.

**5d-A. Bullpen availability (`pen_plus_avail`, B4 family).**
Estimand: does replacing `bullpen_plus` with `pen_plus_avail` inside
`game_prevention_z` improve calibration on the vintage eval half. Split: the
existing vintage fit/eval split, unchanged. Criteria, BOTH required, the same
two-criterion form as 11b: paired Brier improvement at one-sided t >= 1.645 on
player-clustered bootstrap, AND paired log loss not worse on the point estimate.
Plus the B4 burden from 5c: the builder must be on the nightly path before the
clock starts. Control: the permuted twin from 5c rule 3, permuting availability
across teams within each date, because "the club with tired arms" is partly "the
club that has been playing badly" wearing a fatigue costume.

**5d-B. Schedule rest (`rest_days`, `games_in_l7`, `sp_rest_days`).**
Same estimand shape, entered as an additive term on run prevention. Same two
criteria. Same permuted twin. NOTE the confound to be reported whichever way it
lands: rest is correlated with travel, and with the schedule maker's tendency to
give good teams favourable dates. The twin is what separates them.

**5d-C. Weather climatology (`wx_temp_climo`, `wx_wind_out_climo`).**
Estimand is on the TOTAL, not the moneyline, because that is where a run
environment effect should land, and a candidate that moves the moneyline but not
the total is reporting a park proxy rather than weather. Criteria: paired
absolute error on total, improvement at one-sided t >= 1.645, AND no degradation
of moneyline Brier on the point estimate. The observed-weather screen runs first
and can only disqualify.

### 5d-D. Catcher framing (`catch_frame_rate`), added to schema 4 on 2026-09-07

**Source.** `.cache/game_feeds` play events. Verified on a 40-feed random sample:
11,753 pitch events, **all 11,753 carrying pX/pZ coordinates** and each plate
appearance carrying its own `strikeZoneTop` / `strikeZoneBottom`. No new
dependency; a 30-day window is 408 games and 3.5 seconds.

**The number.** Called strikes above the league's own rate in the same location
bin, per 100 TAKEN pitches, over a trailing 30-day window ending the day before
the vintage date. Bins are (batter side, |pX| in 0.1 ft, height normalized to
that batter's own zone in 0.1 units), and a bin under 40 league pitches is
dropped from BOTH the actual and the expected side so a thin bin cannot
manufacture a difference.

**Three design choices that are the whole feature.** Height is normalized to the
batter's own zone, because binning raw feet would make the expectation a model of
batter height. Swings are excluded, because a swing is not an umpire decision and
carries no framing information. And the catching club is read off the HALF
INNING rather than off a pitcher-to-team map: in the top half the away team bats,
so the home team is catching, which is exact, needs no roster join, and is immune
to the mid-inning substitutions that make per-catcher attribution hard.

**The units are a rate and stay a rate.** Converting to runs needs a
runs-per-called-strike constant that nothing in this repo measures, and inventing
one would put a fabricated number on a scale that looks measured.
`_assemble_team_inputs` standardizes every column anyway.

**Coverage check, not a measurement.** 30 of 30 clubs carry a rate on the
2026-09-07 window, spread from +1.76 to -2.22 per 100. Reported here for the same
reason 5c reported its 540 order slots: it says the builder produces a number.
**No value in this section has been related to any game outcome.**

**Gate.** Estimand: does adding `catch_frame_rate` to run prevention improve
calibration on the vintage eval half. Criteria, both required, the 11b form:
paired Brier improvement at one-sided t >= 1.645, AND paired log loss not worse
on the point estimate. Control: the 5c rule 3 permuted twin, permuting framing
across clubs within each date. The confound the twin exists for: a good framing
club is disproportionately a good PITCHING club, and `bullpen_plus` and
`rotation_plus` already carry that.

### 5d-E. Times through the order (`sp_tto3_bf`), added to schema 4 on 2026-09-07

**The number.** Mean batters a starter faces for the THIRD OR LATER time, per
start, over his own starts in the trailing 30-day window. Only each side's first
pitcher counts; a reliever's third time through is a different event with a
different cause. Minimum 2 starts in the window or the column is null.

**EXPOSURE, NOT PENALTY, and the distinction is the reason this is buildable.**
How far a starter gets into the order a third time is well measured from his own
recent starts. How much WORSE he is on that third pass is a per-pitcher split
with a season of noise in it, and pricing one would need shrinkage this has not
earned. The candidate asked here is narrow: does exposure carry information the
innings share (`ip_per_gs`, already in `game_prevention_z`) does not. The
per-pitcher decline is a separate, harder candidate and is not asked.

**Coverage check.** 173 pitchers carry a value on the 2026-09-07 window, mean
4.33, median 4.40, range 0.0 to 8.5. Again: a builder check, not a measurement.

**Gate.** Same two criteria and the same permuted twin. **The confound to report
whichever way it lands:** `sp_tto3_bf` is mechanically correlated with
`ip_per_gs`, which the model already reads, so the twin and a variance-inflation
read on the pair are both part of the result. A candidate that only reproduces
the innings share has found nothing.

### 5d-F. The home plate umpire is NOT SERVABLE, and this records why

The umpire was scoped on 2026-09-07 and **no column was added**, because the
assignment is not knowable at pricing time.

`liveData.boxscore.officials` carries the home plate umpire and it resolves on
**40 of 40** completed feeds, so his identity is available AFTER the game. A live
probe of game_pk 824792 (CLE at BAL, 2026-09-08) in `Preview` state returned an
**EMPTY officials list**. The board prices pregame, so an umpire column would be
either empty when it is needed or filled from the future.

This is the same shape as the observed-weather problem in 5d-C and it takes the
same answer: **a contaminated screen only.** The size of the umpire effect can be
measured off completed games, labelled contaminated, under the standing rule that
such a diagnostic can only ever DISQUALIFY a candidate and never qualify one.
That measurement is worth running for one specific reason: it decides whether
chasing a pregame assignment source is worth a new external dependency. If the
effect is small, the question closes. It has not been run and no number about it
exists.

**Do not add an umpire column to the vintage store until a source publishes the
assignment BEFORE first pitch.** A column filled from a completed feed would be
dated after the game it describes, which is the exact leak this store exists to
close.

### Correction (2026-09-07, same day): there are no prior seasons to build climatology from

The 5d-C table above says `wx_temp_climo` and `wx_wind_out_climo` are built
"over seasons STRICTLY BEFORE the vintage date" with a ">= 10 prior-season
games" floor. That is not buildable on this box and the claim is withdrawn
before anything was measured on it. `.cache/game_feeds` resolves 2,155 MLB games
and ALL of them are 2026 (2026-03-25 to 2026-09-07); 2024 and 2025 resolve zero.
A multi-season venue climatology has no seasons to average.

The replacement is same-season and still dated strictly before the game: the
mean observed temperature and signed out-to-centre wind at THAT VENUE over its
own games in the TRAILING 30 DAYS, ending the day before the vintage date. The
window is trailing rather than season-to-date on purpose, because an April game
is not evidence about a September one and pooling the season would bias every
late estimate cold. A venue hosts roughly nine to twelve games in thirty days,
so the floor drops from 10 to **>= 4 games in the window**, and the realized
count rides in the basis so a reader can see how thin any given estimate is.

This is a weaker instrument than a multi-season normal and the gate is unchanged
by that: it either clears its criteria or it does not. If the contaminated
observed-weather screen shows a large effect that this cannot see, the honest
reading is that the effect is real and not FORECASTABLE from what we hold, which
is a finding about our data rather than about weather.

### The clock

Rule 2 of 5c governs: 4 to 6 weeks of accrued vintages before the first look.
Schema 4 lands with the 2026-09-08 vintage at the earliest, so the strict
four-week earliest admissible first look for every column in this section is
**~2026-10-06**. A column that is null across its accrual window has not started
its clock at all.

### Correction (2026-09-11): schema 4 landed with the 2026-09-09 vintage

The paragraph above is left as written. On disk, `2026-09-07.json` is the last
schema-3 vintage, there is no `2026-09-08.json`, and the first schema-4 record is
`2026-09-09.json` (captured 2026-09-09T19:16:44Z). So the strict four-week
earliest first look for every column in 5d is **2026-10-07**, one day later than
stated. Coverage on 2026-09-11, counts only and no value read: 2 schema-4
records (2026-09-09, 2026-09-10), 60 team rows, `wx_temp_climo` and
`wx_wind_out_climo` populated on 60 of 60, basis "32 venue(s) resolved, 0
club(s) below the 4-game floor" on both nights. The climatology candidate is
unchanged; the separate FORECAST candidate is section 5h.

---

## 5e. The handedness gate (pre-registered 2026-09-07, columns accruing since 2026-08-18)

The columns for this one already exist. `off_vs_lhp`, `off_vs_rhp` and the
pitcher's `throws` have accrued since the first schema-3 vintage, and on the
2026-09-07 backtest artifact all three read 259 populated eval games, 0 stated
nulls, 243 games on records that predate the columns. This section exists
because 5c rule 1 requires it BEFORE any number is computed, and none has been.

**The candidate.** The served model reads one offense number per club,
`z_off`, standardized from `offense_plus`. The candidate replaces it with the
platoon-matched split: `off_vs_rhp` when the opposing probable throws R,
`off_vs_lhp` when he throws L, standardized through the same
`_assemble_team_inputs` seam so the live and vintage paths cannot diverge.

**What must be reported whichever way it lands.** 5c already records that on
nights the batSide lens is down, `platoon_applied` is false and the vl and vr
orders are BYTE-IDENTICAL. On those games the candidate is arithmetically the
same model as the baseline, so they carry no information about it. The count of
such games in the eval window is part of the result, not a footnote, and the
effective n is the games where the two differ.

**Criteria.** Both required: paired Brier improvement over the served model at
one-sided t >= 1.645, AND paired log loss not worse on the point estimate.
Control: the 5c rule 3 permuted twin, permuting the handedness assignment across
teams within each date. A club that hits RHP well is largely a club that hits,
and the twin is what separates the platoon signal from the offense level that
`z_off` already carries.

**Clock.** The 2026-08-19 correction pins the schema-3 clock to the 2026-08-18
vintage, so the strict four-week earliest admissible first look is
**~2026-09-15**. Eight days after this section was written. It is written now
precisely so that it cannot be written to fit what the first look shows.

### Correction (2026-09-10): the candidate column was its own baseline, and the clock restarts

Found by the FanGraphs-library audit (finding F08-02) BEFORE the first look, and
recorded here under 5c rule 1, which permits amending a pre-registration before
its clock opens on a fact established without touching outcomes. **Nothing in
this correction was measured against a game result.**

**What was wrong.** `hem_plus._platoon_adj` says it in its own docstring: it
re-lenses the ORDER vs L and vs R and never the published number. So both
hand-labelled orders carried each hitter's SEASON `hem_plus`, and
`leaderboard_vintages._pa_weighted_hem` averaged that over a permutation of the
same nine bats. A PA-weighted mean over a permutation is permutation-invariant,
so `off_vs_lhp` and `off_vs_rhp` were equal BY CONSTRUCTION, not by coincidence.

**Measured on the served board and on the dark capture.** All 30 clubs
bit-identical; all 480 stored (date, team) rows across 16 vintage dates
identical. And this was NOT the "batSide lens is down" case the paragraph above
anticipated: the lens was fully UP (737 of 737 hitters stamped) and the two
orders were genuinely different permutations (0 of 30 teams identical). The
paragraph above therefore describes the wrong failure mode, and the guard that
was in place (`bat_side.available`, `n_teams_identical_orders`) could not see
this one, because it checks the ORDERS and the defect was in the VALUES.

**The repair (2026-09-10).** `hitter_export.load_platoon_splits` pulls each
hitter's real per-hand counting line in two bulk StatsAPI calls
(`statSplits`, `sitCodes=vl|vr`, `playerPool=All`; the default pool returns
qualified hitters only and the everyday nine reaches well past it).
`hem_plus.split_hem_plus` scores a hand-specific HEM+ from that line on the SAME
season pool anchor, so the league-wide platoon effect survives rather than being
re-centred away, and the existing per-component reliability constants shrink a
thin split harder with no new constant. Each slot gains `hem_plus_split`
ALONGSIDE the untouched season `hem_plus`; `_pa_weighted_hem` prefers it and
falls back per slot. Measured after the repair on the live board: 540 of 540
lineup slots resolved, clubs serving an identical split went 30 to 0, and the
vs-LHP minus vs-RHP spread runs -20.74 to +11.24 with a median of -4.17.
Offense+ and every per-slot displayed number are byte-unchanged, verified.

**THE CLOCK RESTARTS, and this is the part that costs.** Every row captured
before the repair carries a column that could not differ, so the accrued 480
rows are uninformative about this candidate by construction. The earliest
admissible first look is four weeks after the first vintage whose
`platoon_splits.available` is true, NOT ~2026-09-15. Vintages are
first-write-wins, so the first such file is the night AFTER the repair ships.

**Two additions to what must be reported.** The `platoon_splits` block on the
hitter artifact is now part of the result: `n_slots_split` of `n_slots`, and
`n_teams_split_equal`, which is the tripwire that would have caught this. A run
where the feed is reported available and every club is still identical WARNS and
does not raise, because the nightly vintage write is what this clock and the
schema-4 accrual both run on, and an unconditional raise would stop that stream.

**Not reopened.** No criterion, control or threshold above is amended. The
candidate, the two-leg bar and the permuted twin stand exactly as registered.

### Amendment (2026-09-11): postseason games COUNT, and the new earliest look

Recorded under the same rule as the 2026-09-10 correction: before the look and
before any number relates the candidate to a game outcome. Unlike that
correction it is not a fact found in the data. 5e was silent on postseason
games, and the owner answered the question (decisions list, item 8, 2026-09-11):
**they count.** Nothing in this amendment was measured against a game result.
The paragraphs above are left as written.

**The clock.** The 2026-09-10 restart rule, unchanged: four weeks after the
first vintage whose `platoon_splits.available` is true. What this amendment adds
is that postseason vintage nights count toward the four weeks exactly as
regular-season nights do. The repair landed 2026-09-10 at 20:52 EDT, after that
night's vintage was captured (2026-09-10T19:34:37Z), so no vintage on disk has
the repaired split: the newest is `2026-09-10.json`, and the hitter artifact
it read predates the repair. The hitter artifact dated 2026-09-11 reports
`platoon_splits.available` true with 540 of 540 slots split and 0 clubs
split-equal. Vintages are first-write-wins, so the first qualifying vintage is
expected to be `2026-09-11.json`, and the earliest admissible first look is
**2026-10-09** (2026-09-11 plus 28 days). The start date is read off the vintage
record, never off the day's artifact: since schema 5 the basis string of the 5f
hitter columns (`lineup_dis_vs_lhp` and its three siblings) carries the night's
`platoon_splits.available`, and that flag is the condition, as registered. The
count of clubs whose stored `off_vs_lhp` and `off_vs_rhp` are equal (the
`n_teams_split_equal` tripwire, read off the stored rows) is reported with the
result and, as the 2026-09-10 correction registered, warns and does not decide.
If `2026-09-11.json` is not written, or its basis does not read available true,
the clock starts at the first vintage that does and the look moves with it.

**What postseason inclusion does to the eval set.**

- *It adds games the served backtest cannot see, and only to the eval side.*
  `betting_model.build_game_cache` and `_row_from_schedule` keep `gameType` R
  and nothing else, on purpose (their comment: different team quality and
  roster rules, which a fit would absorb). That stays. At the look, the 5e
  harness adds the final postseason games (`gameType` F, D, L and W) through the
  same vintage resolver, each priced from the vintage dated before it, and
  scores the candidate and the served model with the coefficients fitted on the
  regular-season vintage fit window. No fit sees a postseason game, and the
  served fit, the served backtest and every served price are unchanged.
- *Where the information sits.* Games on vintages that predate the repair price
  the candidate identically to the served model, so they carry no information
  (the effective-n rule above). The resolver reads the newest same-season
  vintage whose cutoff is strictly before the game's date, so the first
  qualifying vintage (2026-09-11) first prices the 2026-09-12 slate, and the
  2026-09-11 games price off the pre-repair 2026-09-10 vintage and carry none.
  The informative games are the regular-season slates from 2026-09-12 through
  the 2026-09-27 season end, 16 slates and at most 215 games (2,430 scheduled,
  less the 2,200 final through 2026-09-10 in the completed-games cache and the
  15 on the 2026-09-11 board; a postponement not made up lowers it; the cached
  schedule holds 79 of them, 2026-09-12 to 2026-09-17), plus every postseason
  game played before the look. The whole
  2026 postseason is 32 to 53 games (Wild Card Series 8 to 12, Division Series
  12 to 20, League Championship Series 8 to 14, World Series 4 to 7); a look on
  2026-10-09 sees the Wild Card Series and whatever part of the Division Series
  has been played. A four-week floor from 2026-09-11 cannot be met inside the
  2026 regular season, which is the question 5e left open: whether October
  nights count toward it, and whether October games are graded. This amendment
  answers yes to both.
- *The permuted twin weakens on October dates.* The twin permutes the
  handedness assignment across clubs within each date. A postseason date carries
  one to four games, so it has few distinct permutations, and a one-game date
  has two. That makes the control weaker, not the candidate stronger, and it is
  reported rather than corrected.
- *The games differ.* Starters go shorter and bullpens carry more of the game in
  October, which dilutes the starter's-hand signal this candidate reads (it is
  why 5f excludes postseason); home field follows the seeding, and the served
  home constant is applied unchanged; every opponent is a playoff club. None of
  this is adjusted for.

**Added to what must be reported.** The postseason game count, split by round;
the number of eval dates carrying fewer than four games; and, beside the pooled
result that decides, the two criteria computed on the regular-season games
alone, reported and never qualifying. Vintage gaps are handled by the resolver's
own rule, unchanged: a game is priced from the newest same-season vintage
strictly before it at whatever age that vintage is, a game with no such vintage
is dropped and never filled from live files (5c), and the vintage-age
distribution is reported (the store has gaps: September so far has no
`2026-09-01.json`, `2026-09-02.json` or `2026-09-08.json`).

**Not reopened.** The candidate, both criteria, the twin and every threshold
stand as registered. The decision is 5e's alone: 5f and 5g still exclude
postseason games.

## 5f. The pinch-hit and bullpen-handedness gate (pre-registered 2026-09-11, schema 5)

**Written before the schema bump it describes exists in code and before the
candidate has been computed for any club or related to any outcome**, in the
discipline of 5a, 5c, 5d and 5e. Disclosed, because 5c rule 1 turns on it: before
this section was written, the pinch-hit design lane (2026-09-11) measured pinch-hit
frequency, innings, platoon share, each club's pinch-hit rate and each club's
bullpen LHP share on `.cache/pbp_corpus` (2018, 2019, 2021-2026). Those are exposure
measurements; no score, run, win, win probability or leverage field was read, and
the candidate below was never computed.

**The owner ask this answers.** "Incorporate pinch-hit awareness into the betting
model ... Pinch hitting awareness should have platoon/handedness awareness."
(2026-09-11)

**The candidate.** The served model reads one offense number per club, `z_off`.
The candidate adds a per-game delta over the BULLPEN share of the game only:

```
z_off_ph = z_off + (1 - w) * [ (pL - pL_bar) * (L - R)
                              + phi * (pL * g_L + (1 - pL) * g_R) ] / off_sd
```

`w` is the opposing probable's starter share exactly as `game_prevention_z`
computes it; `pL` the opposing club's `pen_lhp_share`; `pL_bar` its mean over the
clubs in the same vintage; `L`, `R` the scoring club's `off_vs_lhp`, `off_vs_rhp`;
`phi` its `ph_share`; `g_h = max(0, bench_adv_vs_h - lineup_dis_vs_h)`, zero when
either is null. Coefficients are refit on the fit half as the served model's are;
fit-half games whose vintage predates schema 5 enter with a delta of zero, which
makes those rows identical to the served model's. There is no new free parameter.
It is computed by `game_offense_ph_z`, which nothing served calls.

**The six columns (schema 5).** `lineup_dis_vs_lhp` and `lineup_dis_vs_rhp`: the
per-hand HEM+ (`hem_plus_split`) of the constructed nine's bats WITHOUT the platoon
edge against that hand, season-PA weighted, null when the nine has none.
`bench_adv_vs_lhp` and `bench_adv_vs_rhp`: the same over bench bats WITH the edge
(switch hitters count on both hands), null when none carries a split, never a
season-number fallback. `ph_share`: the club's pinch-hit PA over its relief PA,
season to date through the day before the vintage, shrunk by `K_PHI = 298` toward
the league rate. `pen_lhp_share`: relief PA thrown by the club's left-handers over
all its relief PA, same window, `K_PEN = 142`. The betting builder reads the raw
bench rows and the orders, never the page's platoon-option markers, whose display
constants must be free to move without moving a dark column.

**Constants, and where each comes from.** `K_PHI` and `K_PEN` are the median
split-half pseudo-counts over 2022-2025, derived with no 2026 data. The platoon
restriction on the bench and the lineup and the `max(0, ...)` are POLICY, grounded
in exposure: in 2026, 86.4% of non-switch pinch hitters held the platoon edge
against 46.6% of all non-switch PA against relievers, and the replaced regular was
on the wrong side 90.6% of the time. Season-to-date rather than a trailing window
because the two predicted a club's next 27 games equally (9 and 8 of 15
comparisons). Tuning any of these against outcomes before the look is fitting the
feature to the eval window.

**How it stays separate from 5e.** 5e swaps the whole-game `z_off` for the split
matching the STARTER's `throws`. This candidate never reads `throws` and leaves the
starter share of the game at the served number; takes its hand from the opposing
BULLPEN's season-to-date usage, and its bench term from columns 5e does not have;
reads `off_vs_lhp` and `off_vs_rhp` and never writes them (the schema-5 build must
leave both columns, every `orders` slot and Offense+ byte-identical on the same
inputs, verified before it ships); and is frozen now, before 5e's look, so 5e's
result cannot shape it. If 5e is SERVED before this look, the candidate is re-based
mechanically: the served starter segment becomes 5e's and the bracket's reference
becomes the split 5e served, `z_off_ph = z_off_5e + (1 - w) * (late -
off_vs_throws) / sd_5e`, `late = pL * L + (1 - pL) * R + phi * (pL * g_L + (1 - pL)
* g_R)`. Which form runs is read off the serve flag on the look date.

**The pre-registered expectation, stated before the first fit: FAIL, for power.**
Pinch-hit PAs are 2.41% of 2026 plate appearances (0.914 per team-game). At the
served slope a plausible candidate moves a game's win probability by about 0.03 to
1.0 points; at 1,000 eval games the paired-Brier leg can see about 5.2, so a
correct candidate has power of about 5 to 7%, the false-positive rate. A FAIL is not
evidence that pinch hitting does not matter, and a PASS on its own would not be
evidence that it does.

**The power precondition, computed before any outcome is joined.** At the look, for
each split quantile, compute on the eval games the RMS of (candidate p_home minus
served p_home) from features and fit-half coefficients only. If sqrt(n_eval) times
that RMS is below 1.645 at ANY quantile, the look records UNDERPOWERED with the RMS
and n_eval, the outcome comparison is not computed, and the candidate is neither
passed nor closed. This rule is specific to 5f: it is the only candidate whose own
exposure says the two legs cannot resolve it.

**Criteria**, only when the precondition holds. Both required, at all three split
quantiles (0.6, 0.7, 0.8) with the `VINTAGE_MIN_FIT_GAMES` and
`VINTAGE_MIN_EVAL_GAMES` floors: paired Brier improvement over the served model at
one-sided t >= 1.645, AND paired log loss not worse on the point estimate. The eval
set is regular-season games whose vintage is schema 5 or later. A game is EXCLUDED
when either club's `ph_share` or `pen_lhp_share` is null, or when all four of
either club's hitter-derived columns are null. A null on ONE hand's bench or lineup
column is the stated "no qualifying bat" case and scores `g = 0` on that hand.

**Control.** The 5c rule 3 permuted twin, 200 seeded permutations (seeds 0 to 199):
within each vintage date, permute `pen_lhp_share` across clubs and, independently,
each club's bench pair `(g_L, g_R)` together with its `ph_share`; each club keeps
its own `L` and `R`. The candidate beats its twin only if its paired Brier
improvement exceeds the 95th percentile of the 200 twin improvements.

**What must be reported whichever way it lands.** The effective n and the count
dropped for each null; the count of vintage nights with `platoon_splits.available`
false or `n_teams_split_equal` above zero (5e's tripwire, on which arm A is zero);
the precondition's RMS and expected t at each quantile; the decomposition, arm A
alone and arm B alone, reported and never qualifying; the correlation of this
candidate's delta with `z_off` and with 5e's delta; bench coverage.

**Clock.** 5c rule 2 governs: at least four weeks of schema-5 vintages. Postseason
games are excluded from the eval set (rosters, bench and bullpen usage change in
October, and they are exactly what this candidate prices). One look per season,
after the last regular-season game; **the first is the end of the 2027 regular
season.** No other look, in either direction.

**What this gate is not.** A pricing question: does knowing a club's pinch-hit
habit and bench, and the opposing bullpen's hands, improve a pregame forecast of a
fully observed result. It is not the In-Game Management question of whether any
pinch-hit DECISION was good, which needs the counterfactual of the pinch hit that
did not happen; nothing the management module measures may be read into this gate.

**Shared bump.** 5f and 5g land in ONE schema-5 bump. The same bump generalizes
`betting_model.DARK_TEAM_COLUMNS` to one dark tuple per schema, pinned per schema,
because today it is pinned to schema 3 only and the nine schema-4 columns (5d) are
stored but never reach `_assemble_team_inputs`; the 5d harness needs that read path
before its look.

## 5g. Team fielding (`team_fld_runs`), schema 5 (pre-registered 2026-09-11)

**Written before the schema bump it describes exists in code and before any value
of the column has been related to any game outcome**, in the discipline of 5a, 5c,
5d, 7b and 11a. Nothing served reads it and nothing served changes.

**Why this is a gap and not a double count.** Run prevention in the served model is
`z_prev`, a blend of the probable's SEM+ and the club's `bullpen_plus`
(`game_prevention_z`). Both are sample-shrunk FIP: strikeouts, walks, hit batters
and home runs. Balls in play, and so the fielders behind the pitcher, sit outside
every prevention input. League-average fielding lives in `b0`; club-to-club fielding
lives nowhere.

**Source.** MLB StatsAPI `stats=sabermetrics`, the bulk season-total feed the hitter
export already fetches every night before the vintage write, read through
`saber_feed.load_components`. Its per-hitter `fielding` is FanGraphs' served WAR
fielding component, in runs, excluding framing. The builder reads `saber_feed` and
never the DEM+ index, the Defense board or its history.

**The number.** For each club, the sum over its current position players whose
primary position is not C, P or DH of `fielding` for the prior full season plus
`fielding` for the current season to date. Runs, never an index. Current club from
the vintage's own `canonical_org` join, the feed row's `team` as fallback; the
multi-team count rides in the basis.

**Three choices that are the whole feature.** Catchers are excluded, because served
catcher fielding context includes framing, framing has its own column and gate
(5d-D), and a framed strike partly lands in the K and BB that SEM+ and REM+ already
read. Two seasons rather than season to date, because a single season of fielding
runs is mostly noise and the prior season is dated history. Current-club
attribution, because the price is for tonight's fielders.

**Vintage safety.** The basis records the cache fetch time; the column is null when
that time falls after the vintage date. Old records return None, absent is never
zero, and `inputs_as_of` never fills the column from live files.

**Coverage and adjacent facts, disclosed, not measurements of this candidate.**
Before this section existed, a design lane summed 2026 season-to-date served
`fielding` per feed-row team (one season, feed-row team, DH included) to confirm a
builder produces a number: 30 of 30 clubs, -43.4 to +68.6 runs; and computed the
player-level year-over-year persistence of served fielding per 600 PA (r 0.474 on
800 pairs, 2021-2025). The DEM+ lab (docs/dem-plus-2026-09-11/) computed player-level
forward correlations of the published fielding RATE. None of these relates any
value to any game result; the registered construction above differs from all of
them.

**Candidate.** One additive term on run prevention, `runs_S = ... + b6 * z_fld_O`,
where `z_fld_O` is the opponent's standardized `team_fld_runs`, fitted by the same
`fit_coefficients` path on the vintage fit window.

**Gate.** Estimand: does adding `z_fld_O` improve calibration on the vintage eval
half. Split: the existing vintage fit/eval split; regular-season games only. ALL
required: (1) paired Brier improvement at one-sided t >= 1.645; (2) paired log loss
not worse on the point estimate; (3) `b6` carries the run-prevention sign (better
opposing fielding lowers runs scored), and a wrong sign fails the candidate whatever
(1) and (2) read; (4) at least `VINTAGE_MIN_GRADED_GAMES` (600) eval-half games
carrying a populated value, with the 300-game fit window in front of them. Control:
the 5c rule 3 permuted twin, permuting `team_fld_runs` across clubs within each
date; the candidate must beat its twin. Report whichever way it lands: the
variance-inflation read of `z_fld` against `z_prev` and `z_off`, and the park term
(outfield fielding runs are partly park-shaped).

**Not asked, each needing its own section.** Lineup-aware fielding (tonight's nine
at their positions); the pitcher-by-fielding interaction; a shrunk fielding read;
the season-to-date-only form; any catcher term.

**Clock.** 5c rule 2 AND criterion (4). The 2026 regular season ends 2026-09-27, so
a column first captured this month accrues at most about 240 regular-season games
in 2026; **the earliest admissible first look is the first 2027 date on which both
hold.** Postseason vintages accrue and are not graded.

**Contaminated screen.** End-of-season fielding against 2026 outcomes may run,
labelled contaminated, only after this section is committed, and can only
DISQUALIFY.

**Disqualification.** Any number relating this column, or a close variant (season
to date, catchers included, feed-row team), to game outcomes before this section is
committed disqualifies the candidate under 5c rule 1.

## 5h. Forecast weather (pre-registered 2026-09-11; the capture ships OFF)

**ARMED 2026-09-11 by owner decision, and the 5h-C backfill approved.** The
heading and the pre-registration below are left as written; what changed, the
clock rule for backfilled rows and what the approval does and does not buy are
in "Armed, and the backfill approved" at the end of this section.

**Written before the pipeline has captured a single forecast and before any
forecast has been related to any game outcome**, in the discipline of 5a, 5c,
5d and 7b. One probe request was made while scoping the source (below) to
confirm the response shape; it returned tomorrow's weather at two parks and
nothing about any game result. Nothing served reads anything in this section,
and nothing served changes. This is a SEPARATE candidate from the 5d-C
climatology candidate, with its own columns, its own store, its own gate and
its own clock; neither one's result may be read as the other's.

### The owner ask this answers

2026-09-11, in his words: "Can we also make the sports betting module
weather/ballpark aware, especially for overs/unders and player props?" It was
asked in the same message as "most of the edge/value bets are overs", and the
two are different questions. This section answers the weather one only.

### What weather cannot explain on today's board

Board facts off `data/betting.json` for the 2026-09-11 slate, a description of
the served prices and not an outcome. Mean model fair total minus the posted
line, by the venue's roof type:

| Roof | Games | Mean fair total minus line | Positive-edge total sides | Of which overs |
|---|---|---|---|---|
| Open | 10 | +0.818 | 10 | 9 |
| Retractable | 4 | +1.280 | 4 | 4 |
| Dome | 1 | +0.100 | 1 | 0 |

The lean is as large under a roof as outdoors, so it is not a weather effect
the model is missing, and a weather term would not remove it. It is the
board-wide level error that lane B-TOTAL-LEVEL (the 2026-09-05 master plan,
Part 2 section 2.2) names, and that plan orders the level fix BEFORE any totals
feature work. This section inherits that ordering as a hard rule (addition 1
below).

### Why a forecast, and why neither existing weather source is one

- `gameData.weather` is the weather AT THE GAME (5d). Pricing on it reads the
  future. It stays a contaminated screen that can only disqualify.
- `wx_temp_climo` / `wx_wind_out_climo` (5d) are a trailing venue climatology.
  Servable, but a climatology cannot see tonight's cold front, which is exactly
  what the owner is asking about.
- A FORECAST captured before first pitch is the only pregame signal that sees
  tonight's weather without reading the future. The whole safety property is the
  capture timestamp on the row.

### The source, scoped with one probe (2026-09-11)

**Open-Meteo forecast API** (`api.open-meteo.com/v1/forecast`), no key. The
probe was one request carrying Wrigley Field and Coors Field as comma-separated
coordinates (taken from the cached feeds), hourly `temperature_2m`,
`relative_humidity_2m`, `surface_pressure`, `wind_speed_10m`,
`wind_direction_10m`, `wind_gusts_10m`, `precipitation_probability`, in F, mph
and GMT. It returned HTTP 200 and a JSON LIST of two objects in request order,
48 hourly steps each (2026-09-11T00:00 to 2026-09-12T23:00 at
`forecast_days=2`). Coordinates snap to the model grid: Wrigley 41.948171,
-87.655503 came back 41.962704, -87.67416 at elevation 182 m (the feed says 595
ft, 181 m); Coors came back at 1582 m (the feed says 5190 ft, 1582 m). One
request covers every venue on a slate, so a night costs one call. A
single-location request returns one object rather than a list, and the parser
handles both.

Open-Meteo sells two archive products and only one of them is honest here:

- **Previous Runs API** (`previous-runs-api.open-meteo.com`): `<var>_previous_day1`
  is the value predicted 24 hours before the valid time, up to day 7, archived
  from January 2024 for most models (GFS 2 m temperature from March 2021). A
  genuine forecast at a fixed lead, so it is a candidate BACKFILL (5h-C).
- **Historical Forecast API** (`historical-forecast-api.open-meteo.com`): built by
  stitching the first hours of each successive model run, and by the provider's
  own description it tracks actual conditions. That is an analysis, close to
  observed weather, and a backtest on it would bring the 5d leak back in a
  disguised form. **It may not be used for this candidate, as a feature or as a
  backfill.**

**The licence is the reason this is an owner decision.** Open-Meteo's terms say
the free API is for non-commercial use only, and they list "operating websites
or apps that have subscriptions or display advertisements" as commercial. This
site sells a subscription tier, so Open-Meteo means its commercial plan (API
Standard, 1M calls a month; the price is shown only at checkout) and a CC BY 4.0
attribution line on the page. The code supports the commercial endpoint through
the `EEPHUS_OPEN_METEO_KEY` environment variable and never writes the key
anywhere.

**NWS** (`api.weather.gov`): no key, a User-Agent with contact details
(`EEPHUS_NWS_USER_AGENT`), and its documentation says the data is "free to use
for any purpose". US only, so Rogers Centre (TOR) has no forecast; it is a
retractable venue, so the primary arm loses nothing. Two requests per venue
(`/points`, then the hourly forecast), wind direction as a 16-point compass
string, no pressure, and NO archive, so there is no backfill arm on this source.
Its response shape is documented and was NOT probed in this lane (the probe
budget was one call); the parser is tested on the documented shape.

### Venues, coordinates, bearing and roof: already on disk

`gameData.venue` in the cached feeds carries `location.defaultCoordinates`,
`location.azimuthAngle` (the bearing from home plate to centre field) and
`fieldInfo.roofType`, so the only new network call is the forecast itself.
Offline read by `betting_weather.venue_table` (newest three games per club): 30
home venues, 0 missing coordinates, 0 missing a bearing; 22 Open, 7 Retractable
(HOU, MIA, SEA, MIL, TOR, TEX, ARI), 1 Dome (TBR). Over the 2,197 cached
completed 2026 games whose feed resolves, 1,613 were at open-air venues, 512 at
retractable and 72 at the dome. At the 512 retractable games the feed's at-game
condition read "Roof Closed" 342 times, and the roof decision is not published
before first pitch in anything this repo holds. Bearing spot check against
known geography: Wrigley 37 and Fenway 45 (both face north-east), Coors 4,
Oracle 85.

### What is captured

One row per scheduled game, averaged over `GAME_WINDOW_HOURS` (3) hours from the
first-pitch hour:

| Column | Meaning |
|---|---|
| `fc_temp_f` | forecast 2 m temperature |
| `fc_wind_mph`, `fc_wind_from_deg` | forecast 10 m wind speed, and the direction it blows FROM (first hour) |
| `fc_wind_out_mph` | signed out-to-centre component: speed times cos(toward minus bearing), toward = from + 180. Out is positive, the sign `betting_usage.WIND_OUT_COMPONENT` gives the feed's own "Out To CF". Averaged per hour as a component, so an hour out and an hour in are a zero, not a crosswind |
| `fc_rh_pct`, `fc_pressure_hpa`, `fc_precip_prob_pct` | carried, not in the candidate |
| `weather_applies` | True only at an open-air venue. Dome venues are never fetched; retractable venues are fetched for the secondary arm and carry False |
| `captured_at`, `lead_hours`, `hours_used` | the safety property, on the row |

The store is `.cache/weather_forecasts/<UTC date>-<HHMM>.json`, one immutable
file per capture (a second capture in the same minute raises
`FileExistsError`, exactly like the odds snapshots). The nightly step
`9e-pre-wx` runs after the vintage snapshot and before the export, and captures
today's remaining games and tomorrow's (`HORIZON_DAYS = 2`), because tomorrow's
day games start before the next nightly run. `MIN_LEAD_HOURS = 1` is POLICY: a
row captured later than one hour before first pitch never informs that game.

Offline dry run on the 2026-09-11 schedule with the request stubbed from the
probe response: 30 games in the two-day horizon, 1 skipped (Wrigley at 18:20Z,
already under way at a 19:00Z capture), 29 rows, 14 venues in the one request
(the dome not asked). A day game's only capture is the previous night's, at a
lead of about 23 hours.

### The rules: 5c verbatim, plus three additions

- **Dark means dark.** No served price, slot, record row or exported edge reads
  a forecast. `betting_weather.forecast_for_game` is the only reader. It returns
  the newest row whose OWN `captured_at` is at least `MIN_LEAD_HOURS` before
  first pitch (never a file name), and None otherwise: never the observed
  weather, never the climatology, never a zero. `test_betting_weather.py` pins
  that no served module imports it.
- **Addition 1, ordering.** The candidate may not be measured until B-TOTAL-LEVEL
  has either shipped or been closed, and the incumbent in 5h-A is the served
  model as it stands on the day of the look. A weather term measured on top of the
  board's +0.89-run mean total gap would be credited with part of the level fix,
  because September is colder than the season the level was fitted on.
- **Addition 2, no intercept.** Both regressors are de-meaned on the fit portion
  and enter with no intercept, so the candidate cannot absorb a level error by
  construction.
- **Addition 3, what may be computed before the clock.** Coverage counts, and
  the FORECAST FIDELITY CHECK: the captured forecast against the same game's
  feed-reported temperature and wind out-component. It reads no score; it
  measures the instrument (bias and mean absolute error; the slope of the feed's
  out-component on the forecast's, which is the wind pass-through 5h-B needs;
  and the sign agreement of the two out-components, which is the test of the
  bearing convention). It may never be joined to runs, totals or any betting
  row, and a fidelity result may not amend a 5h-A criterion.

### 5h-A. The totals candidate

**Estimand.** On the TOTAL, for 5d-C's reason: a run environment effect lands
on the total, and a candidate that moves the moneyline but not the total is
reporting a park proxy.

**The challenger.** The incumbent's per-side lambda plus
`b_t * (fc_temp_f - T_ref) + b_w * fc_wind_out_mph` at open-air games; zero at
retractable and dome games. `T_ref` is the venue's own trailing-30-day
climatology from `betting_usage.venue_climatology` at the game's date (the
schema-4 builder, dated strictly before the game), so the term prices the
ANOMALY that the park index, which already carries the venue's usual weather,
cannot see. `b_t` and `b_w` are fitted by least squares on the incumbent's
per-side residual (runs minus lambda) on the fit portion only; every other
parameter of the incumbent is untouched, so the comparison is one term wide.

**Split.** The live-capture window, from the first accrual night to the look
date, split at its calendar midpoint: the earlier half fits, the later half
grades. The split date is written into this section on the day of the look and
never moved.

**Criteria, both required, the 5d-C form.** (1) Paired absolute error on the
game total (incumbent minus challenger) improves at one-sided t >= 1.645 over
the graded open-air games. (2) Moneyline paired Brier not worse on the point
estimate.

**The contaminated leg.** The 5d observed-weather screen, the same two
regressors built from `gameData.weather`, labelled contaminated. It can only
DISQUALIFY: if the observed weather itself shows no effect on the total, a
forecast of it has nothing to find.

**The permuted-venue twin.** Permute the (temperature anomaly, wind
out-component) pairs across the open-air venues playing on the same date,
refit, and grade, 200 times with seed 20260911. The challenger's mean graded
improvement must exceed the 95th percentile of the twin's. The twin separates
weather at THIS park from a date-level effect: a league-wide cold night, a
getaway-day slate, or anything else every game that night shares.

**Reported whichever way it lands:** the retractable secondary arm (roof
assumed open), n by roof type, the lead-hour distribution, and the fidelity
check's numbers.

### 5h-B. The props prior (home runs, total bases)

A LITERATURE prior, never fitted here, in `betting_weather.hr_weather_prior`:

| Constant | Value | Source |
|---|---|---|
| carry per degree F | 0.33 ft | Nathan, "Effect of Temperature on Home Run Production" (trajectory calculator, 103 mph at 28 degrees, linear over 50 to 100 F, slope 0.33143) |
| carry per mph straight out / in | 3.2 ft / 3.4 ft | Nathan, "The Carry of a Fly Ball": 397 ft in still air, 413 ft with 5 mph out, 380 ft with 5 mph in |
| home runs per foot of carry | ln(1.25) / 8.5 = 0.026252 per ft, log-linear | Nathan: shifting Statcast 2015-2017 fly balls past ~400 ft by 8.5 ft raised home runs about 25% |

The multiplier on a batter's HR rate is `exp(0.026252 * carry_ft)` with
`carry_ft = 0.33 * (fc_temp_f - T_ref) + (3.2 or 3.4) * (p * fc_wind_out_mph -
wind_ref)`. Temperature alone is 0.87% per degree F, which cross-checks against
Nathan's own "about 1%" and Callahan and Mankin (BAMS 2023), about 2% per degree
C of daily high, 1.1% per degree F. The elasticity is local to about 8.5 ft,
and a result beyond that carries `extrapolated: true`. The reference is the
venue climatology, as in 5h-A.

**The wind pass-through `p` is not a literature number and is not invented.**
It is the fraction of the forecast 10 m wind that reaches the field, and the
fidelity check (addition 3) measures it without reading a score.
`WIND_PASS_THROUGH` is None until then and the prior's wind term is OFF; the
measured value is written into this section before any look.

**Total bases.** `1 + s * (m_HR - 1)`, with `s` the hitter's own 4 x HR / TB off
the same rest-of-season line `props_fair_lines` prices from. A lower bound: it
ignores extra carry on doubles and triples, and the contact effect (Rob Arthur,
via Nathan, about +0.0001 BABIP per degree F).

**Size, as arithmetic and not as a measurement.** At +10 F over the reference
the HR multiplier is 1.0905; a 0.034 HR/PA hitter over 4.2 PA goes from a 0.13522
to a 0.14673 chance of a home run, +0.0115, about a fifth of the 0.06 floor; at
-10 F it is -0.0107. A 1.5 total-bases line at s = 0.34 moves by a 1.0308
multiplier. With `p = 0.5` a 10 mph forecast wind straight out is 16 ft of
carry and a 1.522 multiplier, flagged extrapolated, which is why the wind term
waits for the measured `p`.

**How the dark props model reads it.** `betting_props_dark`'s HR ladder gains an
arm A4 = A3 times this multiplier on the same batter-games. It is NOT wired in
this lane, because that module grades against outcomes whenever it runs, and
wiring it now would measure it before its clock. **Gate:** that module's own
rule, A4 against A3, paired Brier with the game-clustered bootstrap, the 95%
interval wholly below zero, and log score not worse on the point estimate; the
same permuted-venue twin; the same clock as 5h-A.

### 5h-C. The backfill arm (a separate owner decision)

The Previous Runs API's `_previous_day1` for every open-air and retractable
venue over the 2026 season to date: about one request per venue with a date
range, roughly 30 requests once. Records are counted SEPARATELY from the live
capture, the 5a arm split. Before any backfilled row is used, the live-against-
archive agreement check (a weather-against-weather comparison on the nights
both exist) must hold: mean absolute temperature difference at most 3 F and
out-component sign agreement on at least 80% of open-air rows (both POLICY). If
approved and agreeing, 5h-A may fit on the vintage FIT half (the games before
the 2026-08-01 split, which are fitted on and never graded) and grade on the
vintage eval window, reported beside the live arm; the live arm governs, and a
sign disagreement between the arms is INDETERMINATE. The archive arm's first
look is no earlier than the live clock below, so the agreement check has four
weeks of overlap to run on. Nothing in this lane requests the archive.

### The clock

It starts the first night `betting_weather.coverage()` reports an open-air row
carrying a forecast (`clock_started`), which is the night the capture is armed
and first runs. Two conditions, both required, before the first look: four
weeks (5c rule 2), AND at least 400 open-air games carrying a live forecast
across the window (POLICY: the 5d-C column covers every game, this one covers
only captured nights, and only half the window is graded). About two and a half
weeks of the 2026 regular season remain after 2026-09-11, at roughly 11
open-air games a night, so a capture armed now accrues about 180 open-air games
before the season ends. **The live arm's first look therefore falls in 2027
unless 5h-C is approved.** That is the cost of doing this honestly, stated now
so that nobody discovers it at the look.

### What a pass would change, and the flag it would ship behind

Serving needs a new flag in `betting_model.py` in the `SERVE_RUN_DISPERSION`
idiom, default False, flipped in one commit with a `MODEL_VERSION` bump so the
ledgers never pool two pricers. Flipping it would move `lam_home` and
`lam_away` at every open-air game by the fitted anomaly terms, so every open-air
fair total and total side probability moves, the moneyline and runline move
slightly through the same two lambdas, and the Pick of the Day can change on any
night the slot holds a total or a total newly clears the 0.06 floor. **This
lane adds no such flag,** because a serving path for an unmeasured feature is
exactly what 5c forbids. What this lane does add, `FORECAST_CAPTURE_ENABLED`,
changes no served number, no side marked value and neither Model Watch slot when
flipped: it only starts the capture and the clock.

### The owner decisions this section needs

1. **Arm the capture at all.** It is a new external dependency.
2. **Which source.** Open-Meteo's commercial plan (one call a night, the best
   shape, archived day-ahead forecasts, a CC BY 4.0 attribution line, price at
   checkout) or NWS (free for any purpose, US only, no archive, about 28 calls
   a night). The free Open-Meteo endpoint is not an option for a subscription
   site under its own terms.
3. **The 5h-C backfill.** The only route to a 2026 measurement.
4. **Where the attribution line lives,** if Open-Meteo is chosen.

### Armed, and the backfill approved (owner decision 2026-09-11)

The section above is left as written. The owner answered on 2026-09-11
(decisions list, item 3, "arm + Previous-Runs backfill"): decision 1 yes,
decision 2 Open-Meteo, keyless, and decision 3 yes. Decision 4 is still open.

**What changed.** `FORECAST_CAPTURE_ENABLED = True`, `FORECAST_SOURCE =
"open-meteo"`, and a new `BACKFILL_ENABLED = True`. The nightly
`betting_weather.run()` (step `9e-pre-wx`) now makes one keyless forecast
request and writes one live snapshot, THEN runs the backfill in its own guard,
so the backfill can neither delay the live timestamp nor block it. **No served
number moves:** no price, fair total, edge, side marked value, Model Watch
slot, record row, ledger row or vintage record reads anything in this section,
and `test_betting_weather.py` still pins that no served module imports it.
What is added is network and disk: one forecast request a night, the backfill's
requests (32 the first night, then one batched request a night), a StatsAPI
feed fetch for any completed game whose feed is not cached, and files under
`.cache/weather_forecasts/`. Every one of those is capped so an outage costs
one timeout and not the nightly critical path: at most
`BACKFILL_MAX_REQUESTS_PER_NIGHT` (40) archive requests and
`BACKFILL_MAX_FEED_FETCHES_PER_NIGHT` (200) feed fetches a night, and the first
failure of either kind ends that kind for the night; every game it would have
filled is retried on a later night. The first backfill is meant to be run by
hand once (`python betting_weather.py --backfill`), so the nightly step only
ever makes the one batched request. The live clock starts on the first night
`coverage()` reports a live open-air row; that date is written here when it
happens, not predicted now.

**The licence paragraph above still stands.** Keyless means the free endpoint,
whose terms name subscription sites as commercial. Setting
`EEPHUS_OPEN_METEO_KEY` moves the capture and the backfill to the commercial
hosts with no code change (the backfill's host follows Open-Meteo's `customer-`
convention and has not been exercised, because no key exists). CC BY 4.0 needs
an attribution line on any page that shows the data; no page shows any today,
because the columns are dark.

**A transport defect, fixed before it could fail silently.** The capture
shipped on `urllib` and had never made a request through it. On 2026-09-11,
on the Windows development machine, `urllib` failed certificate verification
against both Open-Meteo hosts ("certificate has expired") while `requests`
returned HTTP 200 from the same hosts. The fetch now goes through `requests`
and falls back to `urllib` only when `requests` is missing.

**The backfill as built.** `betting_weather.backfill()` reads the completed
regular-season games from the completed-games cache, and each game's venue,
coordinates, bearing, roof and first pitch from that game's OWN cached feed,
never from the home club's usual park: the 2026 schedule so far carries 10
neutral-site games (Mexico City 2, Las Vegas Ballpark 6, the Field of Dreams 1,
Williamsport 1). Open-air and retractable venues are fetched, as 5h-C
registered (retractable rows carry `weather_applies = False` for the secondary
arm, as in the live capture); dome games and venues without coordinates are
written as stated nulls. It requests `<var>_previous_day1` for the same seven
variables the live capture takes and nothing else, averages the same three
hours from the first-pitch hour, and writes `previous-runs-<UTC date>-<HHMM>.json`
into the same store, immutable, first write wins per game. A feed missing from
`.cache/game_feeds` (a pruned box) is fetched through `feed_cache`, the same
document the cache holds; there is deliberately no fallback to the home club's
venue, because that is the neutral-site error above. A game whose feed cannot
be read, whose request failed or was deferred, or whose returned series misses
its hours is listed with a code (`SKIP_CODES`) and not written, so a later night
fills it. The live glob cannot match a backfill file, so the two arms never
pool (the 5a arm split), and `coverage()["backfill"]` counts the backfill
separately, including the last run's skips by code, read off the one mutable
file, `state/backfill_last_run.json`, which neither snapshot glob matches. The
arm is pinned to the approved season, `BACKFILL_SEASONS = ("2026",)`: on a date
in another season it makes no request and says why.

**The clock rule for backfilled rows.**

1. *What the value is.* Open-Meteo: `_previous_day1` is "the value that was
   predicted 24 hours before valid time". The 2026-09-11 probe is consistent
   with the value at hour T coming from the newest archived run initialised at
   or before T minus 24 hours: on all 44 past hours probed it differed from the
   current run's value, and for valid times more than about a day ahead it
   equals the current run, which is what that rule gives when the newest run is
   the current one.
2. *The issue time.* Each row carries `run_initialised_by` (its latest hour
   minus `BACKFILL_NOMINAL_LEAD_HOURS`, 24) and `issued_at`, that plus
   `BACKFILL_ISSUE_ALLOWANCE_HOURS` (12, POLICY: twice the six-hour update cycle
   Open-Meteo states for its global models, to cover publication). `issued_at`
   is the LATEST moment the forecast behind the row could have existed, an upper
   bound and never an optimistic guess.
3. *The rule.* A backfilled row may inform a game only when its `issued_at` is
   at least `MIN_LEAD_HOURS` (1) before first pitch. It is enforced twice: a row
   that fails it is never written, and `backfill_forecast_for_game`, the only
   reader of the arm, tests it again on the row, never on a file name. With the
   three-hour window the bound sits 10.00 to 10.83 hours before first pitch on
   every one of the 2,123 rows the dry run below would fetch, so no row is
   refused at the registered constants and none can carry a value issued after
   first pitch.
4. *The fetch time is not the issue time.* `captured_at` on a backfilled row is
   the honest fetch time, which is after the game. That is why the live reader,
   which tests `captured_at`, can never return one, and why backfilled rows
   never start or advance the live clock.
5. *Never the analysis.* The Historical Forecast API stays banned, and the
   backfill never requests the current-run value for a past hour.
6. *Not before agreement.* No candidate reads a backfilled row until
   `live_archive_agreement()`, the registered weather-against-weather check,
   holds on the games both arms carry, in the registered words: mean absolute
   temperature difference at most 3 F and "out-component sign agreement on at
   least 80% of open-air rows". The denominator is therefore every open-air
   pair, and a pair where either out-component is zero or null counts as not
   agreeing; the share over signed pairs only is reported beside it and never
   decides. The check gives no verdict (`holds` is None) until the paired games
   span `AGREEMENT_MIN_OVERLAP_DAYS` (28), the "four weeks of overlap" 5h-C
   names. The nightly backfill writes archive rows for the same games the live
   capture covers, which is the overlap it runs on.

**Coverage, counts only (2026-09-11, no value read against anything).** A dry
run over the completed-games cache (2,200 games through 2026-09-10) with the
request stubbed: 2,197 games resolve a feed (3 finals from 2026-09-10 are not
cached yet and would be retried), 1,613 open-air (1,611 with coordinates; the 2
Mexico City games carry none), 512 retractable, 72 dome; 32 venues, so 32
requests the first night; about 25 to 40 seconds of feed reads, once. 8 open-air
neutral-site games carry no bearing, so their out-component is null and their
temperature is kept. Real fetches through the backfill code, into a scratch
folder and not into the store: the 2026-09-09 slate (15 games, one batched
request, 15 of 15 rows filled on every column) and 2026-06-08 to 2026-06-14 (89
games, 19 per-venue requests because the span crossed the seven-day batch cap,
86 of 86 fetched rows filled on every variable, the out-component on 80, the six
without being Las Vegas). With the three shape probes that is 24 requests in all
while scoping; none went to the Historical Forecast API, and nothing fetched was
related to any game result.

**What the approval buys, and what it does not.** The live arm's clock is
unchanged: four weeks AND 400 open-air games, which still lands in 2027. For the
archive arm, 5h-C says, verbatim: "The archive arm's first look is no earlier
than the live clock below, so the agreement check has four weeks of overlap to
run on." That clause admits two readings, and choosing between them is an
owner call, not this document's:

- *Reading A, the calendar half.* No earlier than four weeks after the live
  clock STARTS (about 2026-10-10 if the first live open-air row lands
  2026-09-12). The "so ... four weeks of overlap" clause points this way.
- *Reading B, the clock as defined.* No earlier than the live clock's own first
  look, both of its conditions, so the 400 live open-air games too, which puts
  it in 2027.

Until the owner rules, this document holds the stricter, B. Under either
reading the agreement check decides next, and it cannot give a verdict in 2026:
the backfill covers regular-season games only, so the overlap runs from the
first live capture to the 2026-09-27 season end, about 16 nights at roughly 11
open-air games a night, short of the 28 days the check requires. The thresholds
and the minimum are not moved to fit that. So the archive arm waits for 2027
either way, and in 2027 it needs the archive to keep running beside the live
capture for four weeks, which `BACKFILL_SEASONS` does not allow: continuing the
archive arm into 2027 is a further owner decision. Addition 1 (the
B-TOTAL-LEVEL ordering) still applies to any 5h-A look.


## 5i. Ballpark awareness: the Athletics' park, and park by bat side (pre-registered 2026-09-11)

**Written before any column, flag or arm below existed in code, and before any
number about any candidate here was related to a game outcome**, in the
discipline of 5a, 5c, 5d and 7b. Every number in this section is one of two
kinds and says which: a fact about the SOURCE (Savant's own park indices, read
off its pages), or a fact about SERVED PRICES (the 2026-09-11 board repriced).
Neither kind is a measurement of whether a candidate predicts results.

### The owner ask

2026-09-11: most of the edge and value bets on the board are overs; is that a
bug or a feature; and make the module weather and ballpark aware, especially
for totals and player props. On that day's board the model's fair total sat a
mean +0.89 runs above the posted line, above it on 14 of 15 games, and 13 of the
15 positive-edge totals were overs. Section 7f measured why: the total is
priced as a Poisson whose centre sits above where real totals split (the fit-half
level bias is only +0.058 runs), and section 7g's total-scoped dispersion is the
registered shape repair. Nothing in this section is a fix for that lean. Weather
is sections 5d (climatology) and 5h (forecast). This section is the park.

### What the park term is today

One number per game, both sides: `b3 * (runs index / 100 - 1)`, the index read
by `betting_model.park_index()` out of `data/fa_meta.json` park_factors, which
is Savant's DEFAULT view, a 3-season rolling index. Served b3 is 3.386903 on
4,400 rows. It carries no batter side.

### 5i-A. The Athletics' park: a data repair behind `SERVE_ATH_PARK`

**The defect (audit C5-F1).** Savant's default view drops any venue without a
full 3-season window. Read 2026-09-11 off `.cache/savant_pf_2026_all.html` and
`_2025_all.html`: the 2024-2026 view carries 29 venues and the 2023-2025 view 28.
The Athletics have played at Sutter Health Park since 2025, so every consumer
of the index has priced every A's home game at a NEUTRAL park: the served board,
the coefficient fit that sets b3, the vintage backtest, the dark props frame and
`dfs_export`.

**The measured factor.** Savant publishes the venue at shorter windows
(`fa_sources.fetch_savant_park_factors(year, rolling="2")`, fetched 2026-09-11):

| View | Runs | wOBA | HR | PA |
|---|---|---|---|---|
| 2025-2026 (rolling 2) | 121 | 110 | 121 | 34,287 |
| 2025 alone | 117 | 108 | 112 | 18,073 |
| 2026 alone | 125 | 112 | 129 | 15,449 |
| 2025-2026, left-handed batters | 117 | 108 | 121 | 14,219 |
| 2025-2026, right-handed batters | 125 | 112 | 121 | 20,068 |

The completed-game cache agrees on direction, louder: 72 A's home games average
11.667 total runs against 8.387 in their 75 road games, a raw ratio of 1.391,
the highest of the 30 clubs. A raw ratio is not on Savant's player-controlled
scale; it is corroboration and nothing is priced on it.

**The shrink, derived rather than typed.** A 2-season factor must not ride b3
as if it were a 3-season one. Over Savant's single-season indices (2018, 2019,
2021-2026; 206 stable venue-season pairs, same venue id and club), the noise
variance of a single-season runs index is 32.372 index points squared at the
mean single-season sample of 17,577 PA, and the signal variance 53.673. The
sample-implied single-season reliability is 0.6238 against a direct
season-to-season correlation of 0.6221, so the decomposition reproduces the one
number it can be checked against. Reliability is 0.8360 at the 3-season view's
median 54,034 PA and 0.7638 at the A's 34,287. b3 was fitted on 3-season
indices, so the A's deviation is scaled by 0.7638 / 0.8360 = 0.9137: 121 becomes
119.19, served as 1.1919. `betting_model.short_window_park_value` computes it
from the constants and the row's own PA, so the value follows the sample as the
season adds to it. Tropicana's 3-season row carries 34,861 PA and is served
unshrunk today; the same argument would shrink it about as much, and that is a
separate served change this section does not make.

**What flipping it changes, on the 2026-09-11 board** (15 games; repricing with
the same inputs reproduces all 90 served model probabilities exactly):

| | Flag off (served) | Flag on, coefficients held | Flag on, after the `--context` refit |
|---|---|---|---|
| SEA at ATH fair total (line 10.0) | 9.86 | 11.16 | 11.27 |
| Over 10.0 model prob / edge | 0.45648 / -0.05587 | 0.63349 / +0.12114 | 0.64684 / +0.13449 |
| ATH moneyline | 0.44855 | 0.45156 | 0.45392 |
| floor-clearing sides | 26 | 27 | 27 |
| positive-edge totals that are overs | 13 of 15 | 14 of 15 | 14 of 15 |
| fair minus line, mean / median | +0.8933 / +0.8500 | +0.9800 / +1.1600 | +0.9433 / +1.0500 |
| Pick of the Day | ATL moneyline 0.75485 | unchanged | ATL moneyline 0.74978, edge 0.12368 |
| Longshot of the Day | empty | empty | empty |

The refit column exists because `build_context` fits b0..b4 through the same
`park_index()` seam. Refit on the 2,200-game cache with the A's at 1.1919: b3
3.386903 to 3.852374, b0 4.477242 to 4.452830, b1 -0.003093, b2 +0.008276, b4
+0.00052. The omission was attenuating b3: 72 home games that scored like a 1.39
park were coded neutral. After the refit every total moves, the 14 other games
by -0.13 to +0.03 runs.

**It makes the over tilt worse, and that is the honest reading.** SEA at ATH was
the one game the model priced under its line, and only because its park term
was missing. The flag adds an over to the value set and does nothing about the
Poisson centre that section 7f names as the cause.

**Blast radius.** 72 completed A's home games (55 in the vintage fit half before
the 2026-08-01 split, 17 after), 10 distinct A's home events in the 27 cached
odds snapshots, 7 shadow-ledger rows, 16 calibration-ledger rows over 2 games.
ZERO served props numbers: `props_fair_lines` carries no park term. The dark
props frame's A3 arm reads fa_meta park_factors and is untouched.

**Standing.** A data-completeness repair to an existing fitted input, not a new
feature, so it carries no gate of its own; it carries the measurement above and
the owner flips it. The flip procedure is in the flag's comment in
`betting_model.py`: set it, bump `MODEL_VERSION`, re-run `--context`, flip the
tripwire in `test_betting_ballpark.py`. The flag reaches only
`SHORT_WINDOW_PARK_ORGS` (ATH), so its effect cannot grow by itself the day
another club moves. Vintage records reach it only through their own dated
`parks_short_window` block (schema 5); an older record keeps the A's neutral.
`dfs_export` reads fa_meta park_factors and is not changed by this flag.

**Served since 2026-09-11, by owner decision.** Later the same day the owner
answered the decisions list (item 2, "flip on + refit", and the park follow-ups:
DFS reads the same factor, and "the Rays aren't playing at Tropicana this year,
make sure you have the right ballpark for each year"). `SERVE_ATH_PARK` is True,
and the change that flipped it reaches further than the paragraphs above
describe. Three of their sentences are no longer true, and are corrected here
rather than rewritten:

- *"The flag reaches only `SHORT_WINDOW_PARK_ORGS` (ATH)."* Corrected
  2026-09-11: it reaches ATH and TBR. The venue audit found that the Rays
  played 2025 at George M. Steinbrenner Field and all 72 of their 2026 home
  games so far at Tropicana Field (venue 12, a dome), so Savant's 2024-2026
  Tropicana row holds only 2024 and 2026. The Rays now take that row shrunk by
  its own sample, under the same flag and the same shrink as the A's; a short
  row can only pull a measured 3-season factor toward neutral by that factor's
  own sample, never replace it with another number. The list is still explicit.
- *"Tropicana's 3-season row ... is served unshrunk today; ... a separate served
  change this section does not make."* Corrected 2026-09-11: that change is now
  made, in the same flip.
- *"`dfs_export` reads fa_meta park_factors and is not changed by this flag."*
  Corrected 2026-09-11: `dfs_export`'s park leg now reads the same
  venue-correct table through `betting_model.park_index_from_meta`, so /dfs/
  prices the A's and the Rays at the factor /betting/ serves (its legs carry the
  source `savant_mlb_short_window`). The FA engine's team-fit park component
  (`fa_fit.venue_park_row`) reads it through the same shrink.

**What the table above measures, and what it does not.** It is the A's flip
alone, with the coefficients held and after the `--context` refit, on the
2026-09-11 board. The served flip also moves the one dome game on that board,
HOU at TBR, through the Rays' shrunk Tropicana factor, and ships under the one
`MODEL_VERSION` bump (`betting_runs_v1` to `betting_runs_v2`) that also carries
the runline tie split (section 4) and two-way starters on the starter board
(owner decision 23). The moves of the change as shipped, both parks and the
refit included, are in the flag's comment in `betting_model.py` and the commit
that flipped it; this document does not restate them. A fact for the venue
audit that no club-keyed park term fixes, read off the cached 2026 game feeds
(venue only, no score): six Athletics home games (2026-06-08 to 2026-06-14,
against MIL and COL) were played at Las Vegas Ballpark, not Sutter Health Park,
so a park term keyed on the home club prices those six at Sutter's factor.

### 5i-B. Park by bat side for the TOTAL (dark, schema 5)

**A source finding first, because it decides what the candidate can be.** Over
Savant's single-season pages (2019, 2021-2026; 176 stable venue-season pairs;
no game outcome read), the per-venue LEFT minus RIGHT difference is:

| Index | Season-to-season r of (L - R) | 3-season reliability (Spearman-Brown) | L index alone, r |
|---|---|---|---|
| runs | 0.0065 | 0.0191 | 0.4262 |
| HR | 0.1406 | 0.3293 | 0.3735 |

The RUNS split is almost pure noise at the samples Savant publishes, and the HR
split is weak and real. On the current 3-season view the L minus R runs
difference spreads -16 to +12 (sd 6.49) across 29 parks, which is what noise at
about 24,000 and 30,000 PA per hand produces on its own. A lineup-weighted park
runs factor built from the raw split would add variance to every total. The
candidate is therefore the SHRUNK one, with the shrink fixed here.

**The columns (schema 5, `leaderboard_vintages`).** They ride the ONE schema-5
bump that 5f and 5g register; the three sets of columns are independent of one
another, and whichever lands first carries `SCHEMA = 5` for all of them. Team:
`lhb_share_vr` and `lhb_share_vl`, each club's left-handed share of expected PA
in its captured order against a right- and a left-handed starter, slots weighted
by the PA-by-slot table (`LINEUP_SLOT_PA`, pinned equal to
`betting_export.SLOT_PA`), switch hitters batting opposite the starter's hand,
null below 7 of 9 readable slots or when `bat_side.available` is false. Record
blocks: `parks_by_hand` ({org: {L, R, hr_L, hr_R}} as index / 100, off fa_meta's
new `park_factors_by_hand` sibling) and `parks_short_window` (5i-A's raw row).
Coverage check on the 2026-09-11 hitter board: 30 of 30 clubs resolve both
shares; vs RHP median 0.5647 (0.2301 to 0.8967), vs LHP median 0.4536 (0.2144 to
0.6562); 54 switch-hitter slots across both orders. A builder check, not a
measurement.

**The candidate (`betting_model.lineup_park_factor`).** For each scoring side,
with `s` its lineup's LHB share against the opposing probable's `throws`:

    park_S = park_all + 0.0191 * (s * (L - park_all) + (1 - s) * (R - park_all))

replacing the one shared `park` in that side's run row. 0.0191 is the runs-split
reliability above, fixed now. At that scale the candidate differs from the
served term by hundredths of an index point, and **the expected result is a
null**; it is registered anyway, because the owner asked and a null on the
record is worth more than one assumed. A side with any input missing prices on
`park_all` and is counted.

**Gate, both required** (the 5d-C form, because a park effect lands on the
total): paired absolute error on the TOTAL, candidate better at one-sided
t >= 1.645; AND moneyline paired Brier not worse on the point estimate. Control,
also required: the SWAPPED twin, the same function at `1 - s`, must lose to the
candidate on the first criterion. What must be reported whichever way it lands:
the effective n (games where the candidate moves either side's park term by more
than 0.0001), and whether a section 7f or 7g total repair was served at the
first look; both arms share the total's level and shape either way, so neither
can score for either arm.

**Clock.** Four weeks of vintages whose `feature_basis` shows `lhb_share_vr`
n = 30 AND `park_by_hand` n >= 29, counted from the first such vintage.
fa_meta gains the by-hand sibling only when `fa_export` next writes it, so the
earliest admissible first look is four weeks after that night, no earlier than
~2026-10-10.

### 5i-C. Park by bat side for HR and total-bases props (dark props frame)

Props are graded DARK (`betting_props_dark.py`) and priced from the projection
engine with no park term at all, so a props park candidate enters the dark
frame and nowhere else. The existing all-hands park arm A3 is already a clean
null on top of the batter rate (the artifact's `structure_leg`), which sets the
expectation: a hand-scaled version of a null is expected to be a null.

**The arms, added in their own blocks so no pre-existing number moves.**
- HR ladder: `A4_eb_park_hand` is A3 with the park HR index read for the side
  the batter hits from, its deviation from the all-hands index scaled by the
  HR-split reliability 0.3293 (`HR_HAND_SPLIT_RELIABILITY`, pinned equal to
  `betting_model.PARK_HAND_SPLIT_RELIABILITY["hr"]`). `A4_swap` reads the
  opposite hand's index.
- Total-bases ladder, new, on the 1.5 line the board prices: `C0_league` (league
  per-PA mix of single, double, triple, HR), `C2_eb` (each component shrunk to
  the league by the frozen 200-PA batter prior, reused and not refitted),
  `C3_eb_park` (the all-hands park HR index on the HR rate, the added mass taken
  from the zero-base outcome), `C4_eb_park_hand` (the hand-read index), `C4_swap`.
  P(TB > 1.5) is exact under independent PAs: 1 - p0^n - n p1 p0^(n - 1).
- Side: the listed bat side; a switch hitter bats opposite the opposing
  starter's hand, read off the feed's first pitcher. Coverage check over the
  cached feeds: 44,800 batter-games, 44,800 with a side, 43,306 with a by-hand
  index; the 1,494 without are exactly the games at Sutter Health Park (no
  3-season by-hand row), which price like A3.

**Criteria, all required for each ladder**, the frame's existing rule (a
game-clustered bootstrap interval on the paired Brier delta lying wholly below
zero): the hand arm beats the arm it extends (`hand_leg`: A4 vs A3, C4 vs C3),
AND beats its swapped twin (`hand_twin_leg`). Beating A3 alone could be a
noisier copy of the same park. The TB ladder's `structure_leg` (C3 vs C2) is
reported beside it and decides nothing about the hand.

**Admissibility.** The first run of `betting_props_dark.py` after this section
is committed AND after `fa_export` has written the `park_factors_by_hand`
sibling is the first look, and its result is reported whichever way it lands. A
run before the sibling exists publishes both hand legs as `NOT SCORED` with the
reason: every hand arm would equal the arm it extends, and a zero-width null
there is an artifact the module refuses to print. The reliability constant, the
batter prior and the burn-in cut are frozen as written; re-tuning any of them
after that run disqualifies the arm. The by-hand index is the live season's
3-season view, contaminated in the same way A3's is, and the artifact carries
that alongside A3's. A pass opens no slot and moves no served number: it would
license a registered serving lane for the props park term, nothing more.

### What this section does not claim

It does not explain the over tilt and does not reduce it. It does not add
weather; sections 5d and 5h own that and neither clock has opened. It does not
change any served price with its flag off, and the one flag it adds moves prices
in the direction of MORE overs on the board it was measured on.

## 5j. Posted lineups (pre-registered 2026-09-11, schema 6)

**Written before any column, capture, job, helper, candidate function or flag below
exists in code, and before the candidate has been computed for any club or related to
any outcome or any price**, in the discipline of 5a, 5c, 5d, 5e, 5f and 7b. Nothing
served reads anything in this section and no served price changes. The publication
rules under Prerequisites change how the slots and the record publish, not what any
row is priced at. Every name below that does not exist in code today is marked (to be
built). The heading carries the date of the commit that adds this section.

This section must be committed before the 5c B3/B4 look (~2026-09-17; plan section 5.1
sets the deadline at 2026-09-15), so that the look's result on `lineup_strength` and
`star_out`, both close relatives of this candidate, cannot shape it. **If it is
committed after that look is recorded, it is void**, and the candidate needs a new
registration that discloses the look's result.

Disclosed, because 5c rule 1 turns on it. Before this section was written, the
posted-lineup planning lane (R4, 2026-09-11) counted, on the cached completed games,
game feeds, schedule captures and odds capture times:

- starting-nine coverage: 2,197 of 2,200 completed games carry a full starting nine
  on both sides, 545 of the 548 vintage eval-half games;
- the boxscore `battingOrder` array against the true starting nine: different on
  3,464 of 4,394 sides (78.8%);
- when cards post, over 27 cached `/schedule?hydrate=lineups` captures: 42 of 42
  sides posted inside an hour of first pitch, 46 of 48 at 60 to 120 minutes, 51 of 58
  at 120 to 180, 54 of 106 at 180 to 240, 4 of 96 at 240 to 360, and 0 of 84 at six
  hours or more;
- the posted card against the nine that started: identical on 177 of 180 sides, and a
  different nine by exactly one player on the other 3;
- the listed probable against the first pitcher used, over 116 cached probable
  captures: the probable started on 469 of 470 announced sides inside six hours;
- a club's nine against its previous game: identical on 302 of 4,364 team-games over
  the season and 82 of 1,060 in the eval half. In the eval half the count of bats
  changed from the previous game was 1 on 222 team-games, 2 on 338, 3 on 285, 4 on
  121, 5 on 11 and 6 on 1. A count of changed bats is a named close variant (see
  Disqualification); no value was attached to any bat. A club's nine against its modal
  nine: identical on 296 of 4,394 over the season and 161 of 1,090 in the eval half;
- odds capture lead times, read off capture times only: 97 of 448 pregame events in
  27 open snapshots were captured inside three hours of first pitch;
- per-hand coverage by id: 32,254 of 39,546 starter slots belong to a player with a
  per-hand HEM+ on the 2026-09-11 board. That was counted against the 418 ids the
  board's orders and bench carry, not the full `build_split_hem` set, so it is not the
  future `hand_index` coverage;
- the spread of club offense numbers on the 2026-09-11 board: `offense_plus` sd 3.391
  across 30 clubs, the constructed vs-RHP nine (season HEM+, season-PA weighted)
  4.613, and the per-hand constructed nines 5.348 (vs RHP) and 5.015 (vs LHP). The
  last two are that board's `off_vs_rhp` and `off_vs_lhp`, which are 5e's own candidate
  columns, read as a spread across clubs. No outcome was joined, so this is not a 5c
  rule 1 relation for 5e either. It is disclosed because the plan's calendar bars
  reading those columns before 5e's look.

The betting holistic lane (R5, 2026-09-11) counted:

- the share of each club's Offense+ PA taken by hitters not active tonight (median
  0.166);
- cards posted in the 27 lineup cache files at each file's fetch time (file mtime):
  457 of 694 sides pooled, and on five of this box's builds 3 of 30 (2026-09-05
  17:18Z), 7 of 32 (09-04 19:12Z), 13 of 30 (09-09 19:16Z), 16 of 30 (09-11 19:55Z)
  and 28 of 28 (08-30 20:44Z);
- the backtest's starter against the first pitcher used: the same on 2,191 of 2,197
  home sides and 2,194 of 2,197 away. The schedule cache's last pre-pitch probable
  against the first pitcher used: different on 19 of 1,968 sides, TBD on 41;
- open-capture timing: 264 same-slate event-captures, a median 3.83 hours before
  first pitch (p10 0.73, p90 8.39).

None of these counts read a score, run, win, win probability or price value, and none
attached a value to any posted or started nine. R5 separately read the committed eval
artifact and the served-versus-graded probability spread (R5-F1); those concern the
core model and no lineup quantity. P, the delta and the candidate below were never
computed.

**The owner ask.** "... can we pull real lineups when they are posted before each game
and have the model calculate based on this rather than on expected lineups?"
(2026-09-11)

**What the served prices read today, which corrects the premise.** The served
moneyline, runline and total price no lineup, expected or real. `expected_runs` reads
`z_off`, the standardized `offense_plus`, which is a season HEM+ rollup over the club's
whole roster (`betting_model._assemble_team_inputs`). The constructed nine
(`hitter_leaderboards.json teams[].orders`) reaches only the props fair lines and the
dark vintage columns. A median 0.166 of each club's Offense+ PA come from hitters not
active tonight: 20 of 30 clubs are above 0.15, and SF sits at 0.423 (R5, a roster fact
with no outcome in it). On the production schedule as written (`deploy/README.md`, the
03:10 ET nightly), the board is built once, when no card has posted (0 of 84 sides six
hours or more before first pitch). This box's afternoon builds saw some cards (the five
counts above). So what the owner asked for is a new model input: tonight's nine against
tonight's starter.

**The registered candidate does not replace the rollup, and this says why.** It ADDS a
posted-minus-constructed delta to the offense term that serves. The rollup stays in
`z_off_base`, and so does its median 0.166 share of PA from hitters not active tonight.
There are three reasons.
- Offense+ was left on the full season pool on purpose, because it feeds the 600-game
  clock (R5-F5, `roster_filter.scope`).
- The served coefficients are fitted on the rollup's scale. A replacement would change
  the offense term's membership and its scale at once, and one look could not separate
  the two.
- The additive form holds everything except WHO IS PLAYING at the served number.

The replacement form (P in place of `z_off`, the owner's literal ask) and an
active-roster Offense+ are close variants (see Disqualification). Neither is asked here,
and each needs its own section.

**What this candidate reads, and the betting columns that read WAR.** The candidate
reads HEM+ and nothing else. HEM+ is a ratio to its own season pool and references no
WAR frame and no wOBA scale (a word-match for war, ewar, fwar, bwar, woba_scale,
league_constants and war_source in `hem_plus.py` returns nothing). The served run model
reads no WAR either. Two lineup-shaped dark columns on this module do read the
projections bundle, though. 5c's `lineup_strength` is the mean projected year-1 wOBA
(`mlb_projections.json vets[].woba[0]`) over the captured order slots. 5c's `star_out`
ranks each club's top five by projected `vets[].warY1Champ` (`leaderboard_vintages.py`,
the `star_out` builder). A projections retrain, which the WAR label epoch's cascade
includes, can therefore move those two columns. It cannot move this candidate.

**The capture, which moves no price and computes nothing.** The source is StatsAPI
`/schedule` hydrated `lineups,probablePitcher`, at zero Odds API credits, read through a
new helper beside `fantasy_schedule.fetch_lineups` (to be built). `fetch_lineups` itself,
which `/dfs/` reads, cannot serve: it hydrates `lineups` only, caches one file per day
(`lineups_<day>_<game_type>.json`, 12-minute TTL) and returns
`{game_pk: {home: [ids], away: [ids]}}`. It drops each player's `primaryPosition`, the
game's status and time, and the probables. The helper keeps its own cache, so the
3-hour probable cache and the 12-minute lineup cache do not fight (R4 section A). The
raw response lists each side's card in batting order with `id`, `fullName` and
`primaryPosition`, and carries no bat side. Bat side joins from the hitter board and
pitcher hand from `pal_export.load_pitch_hand`. The job is `tools/betting_lineup_job.py`
(to be built), modelled on `tools/betting_close_job.py`:
- cron `*/15` under TZ=UTC, with `--why`, `--selfcheck` and a heartbeat stamped on
  every invocation, including refusals;
- it acts only when a pregame game is 10 to 180 minutes from first pitch (POLICY, from
  the posting counts above);
- one StatsAPI call per invocation, asking for game types R, F, D, L and W, so
  postseason cards are captured too (coverage only; see Postseason);
- one immutable row per side whose posted state changed (a first posting, a changed
  card, a changed probable), written to `.cache/lineup_captures/<UTC date>-<HHMM>.json`
  (to be built). A same-minute collision raises `FileExistsError`, like the odds and
  weather stores. The row carries `game_pk`, `game_type`, `side`, `org`, `posted_ids`
  in order, `probable_id`, `captured_at`, `first_pitch`, `lead_minutes` and `status`;
- it refuses any capture later than `MIN_LEAD_MINUTES = 5` (to be built; POLICY)
  before first pitch.

The unit is a SIDE, never a game. The `fetch_lineups` docstring records game 823428
with nine home players posted and none away (2026-08-07), and count B found no partial
card within a side. The store lives under `.cache/`, so the nightly `git checkout -- .`
cannot touch it.

**The starting nine.** A side's first-pitch nine is the nine players on the completed
feed's `boxscore.teams[side].players` whose own `battingOrder` code is `100` to `900`.
It is never the `battingOrder` array, which names the CURRENT occupant of each slot,
substitutes included, and differs on 78.8% of completed sides. The reader is
`starting_nine(feed, side)` (to be built). A test pins it against the array on a feed
with a substitution. The `fetch_lineups` docstring's "verified" claim covers the posted
card's ORDER only, and it is corrected in the same change.

**The candidate.** For scoring side S facing opponent O, whose starter throws h:

```
N_h(nine) = sum_k SLOT_PA[k] * v_h(bat_k) / sum_k SLOT_PA[k]      (k = 1..9)
N_s(nine) = the same with v_s
P_h, P_s  = N over the nine the leg reads for S (Leg O: the first-pitch
            nine; Leg M: the captured card)
C_h, C_s  = N over S's constructed nine for hand h in the same vintage
            (orders.vl when h = L, else orders.vr)
z_off_lu  = z_off_base + [ w_O * (P_h - C_h) + (1 - w_O) * (P_s - C_s) ] / sd_base
```

- `v_h(bat)` is the bat's per-hand HEM+ against hand h from the vintage `hand_index`
  (`hem_plus.build_split_hem`, scored on the season pool, so the league platoon effect
  survives). It falls back per bat to his season HEM+. `v_s` is the season HEM+. **The
  same fallback applies to P and to C**, so one side of the subtraction cannot
  manufacture the delta by having more split coverage than the other.
- `SLOT_PA` is FROZEN here as a literal: 4.65, 4.55, 4.45, 4.35, 4.25, 4.15, 4.05, 3.95,
  3.85 for slots 1 to 9 (sum 38.25). That is today's
  `leaderboard_vintages.LINEUP_SLOT_PA`. A later repair of `betting_export.SLOT_PA` or
  of that table does not reach this candidate.
- `w_O` is FROZEN here as registered, not read from a served helper. When O's starter
  carries a SEM+, `w_O` is his `ip_per_gs / 9`, clipped to [0.25, 0.85], taking 5.2 / 9
  when `ip_per_gs` is missing. With no such starter, it is O's own starter innings share
  (`sp_ip_share`), and 5.2 / 9 when that is missing. That is today's
  `betting_model._starter_share` with `DEFAULT_SP_SHARE = 5.2 / 9`. A later change to
  that helper does not reach this candidate. Plan N6(d) (G4-10) would replace
  `ip_per_gs` there.
- `sd_base` is the sd that standardizes the base's HEM+ column. While the base is `z_off`
  or any form still built on `offense_plus`, it is the vintage's `_scale.off_sd` (the
  population sd of `offense_plus` across that vintage's clubs, from
  `_assemble_team_inputs`). If 5e's split is the base, it is 5e's `sd_5e`. That is the
  5f re-basing rule, divisor included. The live path and the vintage path standardize
  with identical code.
- h is the opposing starter's `throws` (the schema-3 pitcher column in the vintage;
  live, `pal_export.load_pitch_hand`). Leg M reads the starter named in the capture.
- The starter segment is hand-matched and the bullpen segment is hand-neutral, on
  purpose. The bullpen's hand mix is 5f's lever, and the starter's hand applied to the
  whole game is 5e's. What is left for this candidate is WHO IS PLAYING.
- `z_off_base` is the offense term that serves on the look date. That is `z_off` today.
  It is 5e's platoon-matched split if 5e serves first (the 5f re-basing rule), and the
  5c B4 form if B4 serves first. The candidate is an ADDITION to it, never a replacement.
- It is computed by `betting_model.game_offense_lineup_z` (to be built), which nothing
  served calls, and a test pins that, as for `game_offense_ph_z`. The reduction is one
  function, `leaderboard_vintages.nine_hand_value(nine_ids, hand, index)` (to be
  built). The live path, the vintage path and the candidate share it, the way they
  share `off_splits_from_hitter_team` today.
- **ASSUMPTION: no new free parameter.** The delta enters through the offense
  coefficient b1. That rests on the premise that a HEM+ point of a nine is worth a HEM+
  point of the rollup, because both are PA-weighted means of the same shrunk per-hitter
  HEM+. The premise is not measured. Slot weights differ from season-PA weights,
  per-hand values are shrunk harder than season values, and a b1 fitted between clubs
  may be attenuated for a delta within a club. Each would make b1 misprice the delta.
  The look reports b1 per arm and fits no separate coefficient.

**Fallbacks, per side, carried on the row as `lineup_basis` (to be built).** The labels
apply to whichever nine the leg reads.
- Not posted (live only): delta 0, the constructed-nine assumption, `constructed`.
- A nine, opposing hand unknown: both segments on season values,
  `posted_hand_unknown`.
- A nine with one bat carrying neither a split nor a season value: that bat takes the
  club's bench PA-weighted season HEM+, `posted_one_imputed`. This is POLICY: an
  unscored starter is a bench or call-up bat by construction, and 100 would price a
  debut as a league-average bat.
- A nine with two or more such bats, or no constructed order: delta 0, and the side is
  counted as `posted_unreadable`.
- Otherwise: the full delta, `posted`.

**The record blocks (schema 6, ASSUMED; all to be built).** These are record blocks,
not team columns, following the 5i `parks_by_hand` pattern, so the per-schema dark tuples
do not grow:
- `hand_index`: {mlbam: {s, L, R, pa, pa_L, pa_R, bats, org}}, off a new top-level
  `hand_index` block on the hitter artifact;
- `orders`: {org: {vl: [nine ids], vr: [nine ids]}};
- `bench_mean_hem`: {org: v}.

`hitter_export` publishes `hand_index` with Offense+, every order slot and every
displayed number byte-identical on the same inputs, verified before it ships (the
F08-02 standard). A record older than these blocks returns None for them. Its games
are EXCLUDED from the eval set and counted. In a fit half they enter at delta zero (the
5f rule). They are never priced at zero in evaluation. `inputs_as_of` never fills a
block from live files. Every record's `feature_basis` names each block's source or why
it is null, and carries `platoon_splits.available`.

The schema number is ASSUMED. `leaderboard_vintages.SCHEMA` is 5 in code today (the 5f,
5g and 5i-B bump), and no schema-5 vintage is on this box yet: the newest records,
2026-09-09 and 2026-09-10, are schema 4. These blocks land in whatever bump follows. If
that number is not 6, a dated correction records the number and the first vintage that
carries it, as 5d's correction of 2026-09-11 did, and nothing else in this section
changes.

**Provenance of the nine each leg reads (`lineup_source`, to be built).** There are
three values, counted separately and never blended.
- `archive-reconstruct`: the first-pitch nine, read by `starting_nine` from the game's
  own completed feed. Leg O and every fit half read this. It is not a vintage column and
  does not pass through `covers_through`. Who starts is fixed before the first pitch and
  before any outcome of the game, so it is joined at pricing time as a pregame fact. The
  vintage blocks the candidate also reads obey `covers_through < D`, like every vintage
  value.
- `live-capture`: the card in a `.cache/lineup_captures/` row. Leg M reads this, and a
  served price would too.
- `git-backfill`: the constructed nines of the backfill arm (below).

Reading the first-pitch nine rests on owner decision O22 (OPEN; DEFAULT allow, labelled
per row; plan section 6). As tabled, O22 covers 5k(a), N6 and the lineup backfill. This
section extends it to the Leg O nine, and the question put to the owner must say so. If
O22 is refused before the 5c B3/B4 look is recorded, Leg O reads the card in each
side's newest capture row before first pitch instead, and games without one are
excluded and counted. A refusal after that look closes this section (see Owner
decisions).

**The information each leg assumes, stated.** Leg O prices the nine that STARTED, which
is at least as informed as any pregame capture: in cached captures the posted card
equalled it on 177 of 180 sides. Leg O's starter is the final feed's probable, which
equals the first pitcher used on 4,385 of 4,392 sides, while the nightly board prices
the probable listed the night before. Leg O is therefore an upper bound on what a live
refresh knows. Leg M prices only what its price's capture could have seen (below). The
report carries the live posted-versus-started agreement count from the capture store.

**The pre-registered expectation, stated before the first fit: UNDERPOWERED on
outcomes, and likely null.**
- For a correct candidate the expected paired-Brier t is about sqrt(n) times the RMS of
  (p_candidate minus p_incumbent), on the home side.
- For size, take the served context pricer (b1 0.25102, `diff_shrink` 0.8,
  `data/betting_model_context.json` of 2026-09-11; it is fitted on every completed game,
  R5-F1). A 110 bat resting for a 95 bench bat at slot 3 moves the nine by
  15 * 4.45 / 38.25 = 1.745 HEM+ points. That is 0.51 sd of `offense_plus`, 0.13 runs,
  and about 1.4 points of win probability near an even game. A Skellam at 4.5 runs a
  side has margin sd 3.0, so about 0.133 of win probability per run of margin, times
  `diff_shrink` 0.8.
- A 140 star resting for a 90 bat at the same slot is 5.8 HEM+ points, 1.72 sd and 0.43
  runs, about 4.6 points of win probability.
- The outcome leg needs an RMS of about 6.7 points at 600 eval games and 5.2 at 1,000.
- The second reason concerns the offense term, not lineups. On the vintage fit half the
  own-offense coefficient came back at -0.037205, and the sign-constrained ridge pinned
  it at exactly zero at all three gate splits (7e-B, 2026-09-06). A refit b1 at zero
  prices this delta at nothing, and below zero it prices it backwards.

A FAIL on the outcome leg is not evidence that lineups do not matter.

**The sample: one regular season, never pooled.** Every fit and every eval half lies
inside ONE regular season (section 5, caveat 1: a 2026 tail and a 2027 run are not one
sample). Schema-6 games of 2026 are COVERAGE ONLY and are never graded here, in any leg.
There are at most 15 regular-season days of them: a block first written by the
2026-09-12 nightly prices 2026-09-13 to 2026-09-27, and the plan puts R4-3 in W1, from
2026-09-17. Each look uses its own season alone. The split quantiles are 0.6, 0.7 and 0.8
(`DISPERSION_SPLIT_QUANTILES`) of that season's vintage-gradable dates, and no fit reaches
into an earlier season. The plan's N9 protocol (a 2027 served fit on all 2026
vintage-graded games) is not adopted here.

**Fitting: one procedure, both arms.** The incumbent is the served model's
specification on the look date: its inputs and serve flags as they stand that day. That
includes whichever of the owner's 2026-09-11 answers have landed (the Athletics' park,
the runline tie split). This section fixes no `MODEL_VERSION` string. The candidate is
that specification with `z_off_lu` in place of `z_off_base`. Both arms are fitted by the
same procedure on the same games, and never on an eval game. Neither arm is the served
context file: `build_context` fits on every completed game with live leaderboards, eval
games included (R5-F1). The procedure is the one the serving pricer uses on the look
date, read off `SERVE_PRICER` (to be built, 7e-D):
- `vintage`, and also when `SERVE_PRICER` does not exist. Owner decision O14 (OPEN)
  DEFAULTS to this state when the 7e-D replay fails. Each split's fit half: both arms
  refit every coefficient, the tie rate, `diff_shrink` and the home adjustment there
  (the 7e-B and 11a rule), so a tuned incumbent is never graded against an untuned
  challenger.
- `context`, after a 7e-D PASS: the 7e-D as-served replay, applied to both arms
  identically. For each eval date D, both arms fit on every gradable game of the same
  season dated before D, on the vintage that prices D.
- If some other procedure serves on the look date (N1's `SERVE_HISTORY_FIT`, N9's
  cross-season fit), both arms use the fit-half procedure. The report says the graded
  procedure is not the served one, and serving the delta waits for a registered read on
  the procedure that serves.

Every fit (a fit half, or each date's fit) needs `VINTAGE_MIN_FIT_GAMES` (100) games,
and each eval half `VINTAGE_MIN_EVAL_GAMES` (50). A split below either cannot pass.
**`p_incumbent` and `p_candidate`** are each arm's moneyline home-win probability. Every
leg, the control and the power precondition read these two and no other pricer.

**The eval set, per game.** An eval-half regular-season game enters only when both of
these hold:
- (a) its vintage carries all three blocks under the construction in force since the
  clock's start (Clock);
- (b) BOTH sides' `lineup_basis`, for the nine the leg reads, is `posted`,
  `posted_one_imputed` or `posted_hand_unknown`.

Any other game is excluded and counted by reason: a record older than the blocks, a
side `posted_unreadable`, a side with no nine, and for Leg M the reasons listed there.
A game whose delta is exactly zero on both sides stays in the eval set. It enters with
its computed paired differences, which are not zero because the two arms are fitted
separately, and it is counted apart. In a fit half, a side with no readable delta (an
older record, a `posted_unreadable` side, a side with no nine) enters with delta zero
(the 5f rule).

**Leg O, outcomes (required, non-inferiority).** At every split quantile, all three
must hold:
1. The one-sided 95% lower bound on paired moneyline Brier (incumbent minus candidate)
   is at least -0.001, the 11a moneyline threshold.
2. Paired moneyline log loss (the home-win event), incumbent minus candidate, is not
   worse on the point estimate.
3. Paired absolute error of the fair total against runs scored, incumbent minus
   candidate, is not worse on the point estimate.

Superiority, meaning paired moneyline Brier improvement at one-sided t >= 1.645, is
computed at a quantile only when the power precondition holds there. Otherwise it is
recorded UNDERPOWERED and not computed. It qualifies only in the fallback form under
Verdict.

**Leg M, the market (required in the default form, superiority; the qualifying leg is
a DEFAULT pending owner decision O19).**
- **Which games.** Eval-set games of the split for which all of the following hold.
  Any game that fails one is excluded and counted by reason.
  - Each side has at least one capture row carrying a posted card before first pitch.
  - The job's heartbeat shows no gap longer than 30 minutes (POLICY) between T-180 and
    T-5 minutes for the game, so a card change the job missed cannot hide behind an
    outage.
  - A snapshot of kind `lineup` (to be built) or `close` carries a two-sided h2h market
    for the game. It was captured before first pitch, and at or after each side's
    newest capture row before first pitch.
  - The opposing side's newest capture row names a probable (`probable_id` not null).
- **One price per game.** The NEWEST such snapshot. Its `captured_at` is the game's
  information time.
- **What both arms price.** Each side's card, and the opposing starter named by
  `probable_id`, as they stand in each side's newest capture row at or before the
  information time. By the rule above, that is each side's newest row before first
  pitch, so neither arm knows a change the price could not have seen. P reads that card
  (`live-capture`), never the first-pitch nine. Each arm applies its own Leg O fitted
  coefficients to these inputs.
- **The statistic.** Per game, d = (p_incumbent - m)^2 - (p_candidate - m)^2. Here m is
  the proportional de-vig of that snapshot, averaged across the books posting a
  two-sided h2h market in it (the section 6 rule). Games whose delta is zero on both
  sides enter with their computed d and are counted apart.
- **The bar.** Mean d > 0 at one-sided t >= 1.645, at ALL THREE quantiles. Each
  quantile needs at least 100 Leg M games whose delta is non-zero (above 1e-9 in
  absolute value) on at least one side. That is the module's one small-sample floor
  (7b).
- **Why the market.** The market is the sharpest pregame forecast there is. The one
  thing a lineup-correct adjustment must do is move toward the price the market set
  once it saw the cards.
- **What a pass is not.** A Leg M pass is evidence that the adjustment points where the
  market moved. It is not evidence of an edge against that price, and it opens no
  `min_edge` gate.
- **Captures.** None of these prices exist today: 0 of the 27 cached team snapshots are
  kind `close`, and there is no `lineup` kind. Leg M therefore needs the close job
  installed (owner decision O16, OPEN; DEFAULT install now). It also needs the
  post-lineup capture (O18, OPEN; DEFAULT L-0 until the close job is verified running,
  then L-1, one capture a day at T-60 of the slate's modal evening first pitch, about 93
  credits a month from the 150 reserve). A `lineup` capture must be its own `kind`, so
  that `resolve_snapshot`, the section 6 ladder's `market_open_devig` and the close job
  never read it as an open or a close. A test pins that.

**Control (required).** The 5c rule 3 permuted twin, 200 seeded permutations (seeds 0 to
199). Within each date, permute the per-side delta pairs (P_h - C_h, P_s - C_s) across
the sides entering that leg on that date: for Leg O the first-pitch deltas, and for Leg
M the captured-card deltas of its games. Permute the deltas every fit reads within each
date the same way. Then fit and grade each twin exactly as the candidate, on the candidate's
games. At every quantile, the candidate's improvement on the qualifying leg must exceed
the 95th percentile of the 200 twin improvements: mean d in the default form, paired
moneyline Brier improvement in the fallback form. The twin's other numbers are reported.
The twin tests ASSIGNMENT: whether this club's delta tonight carries information beyond
a delta of the same size landing on another club that date. It does not separate the
card from the schedule. A day-after-night or getaway effect is club- and game-level, and
the permutation breaks that link as well. For that reason the delta's correlation with
5d-B's `rest_days` is reported.

**The power precondition, computed at the look before any outcome is joined.** 5j adopts
5f's rule, which 5f calls specific to itself, with one difference: here non-inferiority
still runs. At each quantile, compute the RMS of (p_candidate minus p_incumbent) over
the Leg O eval games, from features and fitted coefficients only, and sqrt(n_eval) times
that RMS. If the product is below 1.645 at a quantile, Leg O superiority at that
quantile is recorded UNDERPOWERED, with the RMS and n_eval, and is not computed.

**The contaminated screen (required; it can only DISQUALIFY).** This is 5c rule 4's
first leg, in the one form registered here.
- **Data.** Every cached 2026 regular-season completed game with both first-pitch
  nines. Per-hand, season and bench values and the constructed orders come from the
  hitter artifact as published after the last 2026 regular-season game (end-of-season
  values, so contaminated). `z_off` and every other input come from the live
  season-to-date leaderboards (section 6, Mode 1).
- **Split.** By date at the 70% point `backtest()` uses for its contaminated forward
  block (11a). Both arms refit on the fit half.
- **Rule.** The candidate is disqualified if paired moneyline Brier or paired moneyline
  log loss is worse for it at one-sided t >= 1.645. Nothing the screen shows can
  qualify the candidate or amend a criterion.
- **When.** Once, after this section is committed, after the 5c B3/B4 look is
  recorded, and after 5e's look is recorded. 5e's columns are the per-hand constructed
  nines this delta subtracts, and 5e's eval window holds 2026 games. The screen must
  have run before the first look is recorded.
- Its games are 2026 games and never enter a 5j eval window. A `.cache/pbp_corpus` form
  (2018 to 2025 nines) is not registered, because no dated per-hand hitter values exist
  for those seasons.

**Verdict.**

*Where the default form departs from 5c rule 4, and what licenses it.* Rule 4 requires
two legs to serve. The first is the contaminated-forward screen, and it is kept (above).
The second is paired Brier improvement at one-sided t >= 1.645 with log loss not worse
(the 11b form). The default form replaces that second leg with Leg O non-inferiority
plus Leg M superiority, because the expectation above says an outcome-only improvement
cannot resolve a correct candidate at this module's samples. Owner decision O19 (OPEN;
DEFAULT yes) is what licenses the substitution. The fallback form restores rule 4's
improvement leg. 5e, 5f and 5g all carry that leg.

In the default form (O19 yes), a PASS needs every item below at every quantile:
1. Leg O's three non-inferiority criteria.
2. Leg M's bar.
3. The twin beaten on Leg M.
4. b1 above zero in every fit the candidate arm makes at that split. At b1 = 0 the
   delta prices nothing, and below zero it prices a weaker nine as scoring more. Such a
   split cannot pass whatever the legs read (the 5g sign idiom).

In the fallback form (O19 no, recorded before the 5c B3/B4 look is recorded), Leg M is
reported and never qualifying, and a PASS needs every item below at every quantile:
1. Leg O's three non-inferiority criteria.
2. Leg O superiority at one-sided t >= 1.645.
3. The twin beaten on Leg O's Brier improvement.
4. The same sign condition.

If the power precondition fails at any quantile in the fallback form, the look records
UNDERPOWERED with the RMS and n_eval, and the candidate is neither passed nor closed
(5f).

The verdicts, and what each does:
- PASS: every quantile passes.
- INDETERMINATE: some quantiles pass and some do not (11a: a verdict that moves with
  the split point is a verdict about the split point).
- FAIL: no quantile passes.
- UNDERPOWERED: the fallback form only, as above.
- NOT READ: a floor is unmet.

Anything short of a PASS does not ship. PASS, FAIL and INDETERMINATE are final for this
registration. UNDERPOWERED and NOT READ wait for the next season's look. A PASS serves
nothing until the contaminated screen has run without disqualifying (5c rule 4).

*No Holm family.* 5j is the only estimator of its estimand, the posted-minus-constructed
offense delta, so there is no family to size. The coefficient-vector family (7e-B, 7e-C,
7e-D), the run-environment family (5k, 5d-C, 5h) and the z_prev family (N6) estimate
other quantities. 5j's checks form a conjunction, whose false-pass rate is bounded by
that of its weakest check. The three splits overlap: they are a robustness condition
(11a), not a multiplicity control.

**Reported whichever way it lands.**
- the fitting procedure used, `SERVE_PRICER`, `MODEL_VERSION` and every `SERVE_*` flag
  on the look date;
- the effective n (sides with a delta above 1e-9 in absolute value), the sides at
  exactly zero, and the games at zero on both sides;
- the counts per `lineup_basis` and per `lineup_source`, the hand-unknown count, and
  the eval exclusions by reason;
- the Leg M exclusions by reason (no capture row, a heartbeat gap, no qualifying
  snapshot, a null probable), and the lead-time distribution of the snapshots used;
- the fitted b1 per quantile per arm;
- the precondition's RMS and expected t per quantile;
- the correlation of the delta with `z_off`, with 5e's delta, with 5c's
  `lineup_strength` and `star_out`, and with 5d-B's `rest_days`;
- the two-segment decomposition (starter segment alone, bullpen segment alone, never
  qualifying);
- the contaminated screen's numbers;
- the live posted-versus-started agreement count.

**What may be computed before the look.** Coverage only, never joined to a score, a
run, a win or a price value:
- the posting curve and the posted-versus-started agreement off the capture store. The
  posting curve and the late-scratch rate rest today on 27 lineup and 116 probable
  captures from one box, and are re-read after a month;
- the count of games with a snapshot captured after both cards (timing only), and the
  job's heartbeat gaps;
- the `lineup_basis` counts;
- `hand_index` and `bench_mean_hem` coverage.

No value of P, C or the delta, and no statistic of them, is published or summarized
before the look.

**Clock.** The clock starts on the date of the first vintage whose `feature_basis` shows
`hand_index`, `orders` and `bench_mean_hem` all populated and
`platoon_splits.available` true. That is the first vintage on which v_h and C are what
this section registers. Four weeks is 28 calendar days from that date. A missing night
neither stops it nor moves it. A look also needs, in the look's season:
- at least 600 (`VINTAGE_MIN_GRADED_GAMES`) eval-set games in the eval half of the
  anchored split (`_vintage_cut_index`, the split gate 1 counts on);
- at least 100 Leg M games with a non-zero delta at every quantile.

Because 2026 games are coverage only, **the first look is in 2027**, after the last
regular-season game. This candidate is not fitted on pre-2026 data. Nor is it
archive-reconstructable in its registered per-hand form: no committed board holds
per-hand values for the bats outside its constructed orders. So it carries a 2027 first
look, as the plan's section 5 requires a registration to say. One look per season,
after its last regular-season game. No other look, in either direction.

*A change to what defines C, v_h or the bench value restarts the clock.* That covers
the constructed-order builder and its membership, HEM+ and split-HEM+ scoring
(`hem_plus`, `hitter_export.load_platoon_splits`), the `hand_index` source and the bench
rows. Such a change needs a same-day dated correction under this section (plan X9). The
clock restarts at the first vintage after the change. That season's games on earlier
vintages leave the eval set and enter the fit half at delta zero.

*Lapse.* The section lapses unread if no look has met every floor by the end of the
2028 regular season. That could happen if O17 is refused, if O18 stays at L-0, or if the
capture is down. A later attempt needs a new registration.

**Postseason (DEFAULT pending owner decision O20).** Postseason captures and vintages of
any season accrue and are not graded here. The look runs after the last regular-season
game, and October changes rosters and usage (5f's reason). The owner's 2026-09-11 answer
to count postseason games was given for 5e and does not carry to this section. If the
owner aligns 5j with 5e, that must be recorded under Owner decisions.

**Backfill arm (registered, NOT armed; DEFAULT pending owner decision O20).** This is
the season-only form, (P_s - C_s) over the whole game, for 2026 games from 2026-07-06.
- **Sources.** C comes from hitter boards committed to git strictly before each game
  date (5a: `covers_through < D`), under the 5a four rules. That is 17 commit dates from
  2026-07-05 to 2026-09-07, none between 2026-08-13 and 2026-09-04. P is the first-pitch
  nine. C's provenance is `git-backfill`, counted separately and never blended with the
  live store. Per-hand values do not exist in those blobs.
- **Two memberships.** 16 of the 17 boards predate `7cd5f572` (2026-09-07), the commit
  that made the constructed orders roster-aware (13.7% of constructed slots were
  off-roster that day, R5-F4). The 2026-09-07 board is that commit's own, and it carries
  the filter. So the arm's C is a different object before and after, and the two
  memberships are reported apart.
- **Standing.** The arm is REPORT-ONLY: never qualifying, alone or jointly. It reports
  Leg O statistics only. Leg M is impossible, because no post-lineup price exists for a
  2026 game.
- **When.** If it is armed before the 5c B3/B4 look is recorded, it runs once under
  the screen's timing and is reported beside the first look.

**Owner decisions this section uses, and when they bind.**
- The defaults for O19 (Leg M qualifies), O20 (no backfill; postseason not graded) and
  O22 (archive-reconstruct allowed) bind from the commit. A different answer takes
  effect only as a dated correction recorded before the 5c B3/B4 look is recorded, on a
  fact established without outcomes. A different answer after that closes this section
  unread, and the candidate needs a new registration that discloses the B3/B4 result.
- O14 changes no text here. Its effect is read off `SERVE_PRICER` on the look date
  (Fitting).
- O16, O17, O18 and O21 are operational. They decide whether and when the legs can be
  fed and how the slots publish, never what is graded.

**Prerequisites: the publication rules that land before any intraday build.** None of
these is a criterion. Each is a precondition of the Phase 2 disclosure rebuild and of
any serving. Phase 2 is the intraday rebuild of `data/betting.json` and `data/dfs.json`
when a capture lands. Phase 2 reprices nothing.
- **Slot lock.** `.cache/betting/published_slots/<slate>.json` (to be built) is
  first-write-wins and holds both slot rows as first published, with `published_at`.
  Every later build of the slate serves `pick_of_the_day` and `longshot_of_the_day`
  from the lock verbatim and never re-selects. Anything later (a posted card, a changed
  probable, a started game) rides beside the locked row as `since_published` (to be
  built), never in place of it. `write=False` builds never create a lock.
- **Record guard.** `betting_export.maybe_publish_record` refuses a row whose
  `(slate_date, slot)` already has one, naming the reason. This is in addition to
  today's bet-identity check. The test builds a slate, changes one input so the slot
  moves, builds again, and asserts one record row per slot. The defect is latent today
  only because `RECORD_PUBLISH_ARMED` is False.
- **Ledgers.** Shadow `board_all` rows written by an intraday pass carry
  `pricing_basis` (to be built; `constructed` or `posted`) and are never pooled across
  bases (the 7a tag rule). Calibration rows from an intraday reprice go under their own
  `phase: "lineup"` id namespace (to be built), never pooled with the nightly rows.
  Otherwise first-write-wins would keep only the pre-lineup price. This is a code
  change: `tools/betting_calibration._check_phase` raises on an unknown phase today
  (`PHASE_FIELDS` holds open, close and settled), and the fold merges phases per
  `cal_id`, so a lineup row must never share a nightly `cal_id`.
- **The stale-price rule.** An edge is valid only against a price captured after every
  input change that moved the model. A repriced side whose price predates its latest
  input change carries `price_predates_input: true` (to be built) and cannot enter a
  slot, a badge or the record. The invariant test: no served edge on a `posted` side
  whose market `captured_at` is earlier than its lineup `captured_at`.
- **Phase 2's lineup block, bounded.** These are its only fields, all to be built. Per
  side: `posted`, `captured_at`, `n_bats_vs_constructed`, `regulars_missing` (the
  constructed regulars not on the card) and `probable_status` (`confirmed` or
  `changed`). On a slot: `lineup_caveat`, a sentence with no typed number (the
  `tie_atom_caveat` idiom). The block never carries a HEM+ value of a card, P, C, the
  delta or any candidate value. `n_bats_vs_constructed` is a named close variant (a
  count of changed bats). Publishing it is not a relation. But until the look, no shadow
  or calibration ledger row carries any of these fields, and `pricing_basis` reads
  `constructed` on every row. Relating archived lineup fields to an outcome or a price
  disqualifies (see Disqualification).
- **Publication timing (DEFAULT pending owner decision O21).** Slots are chosen at the
  nightly and locked, until 5j passes. Choosing them after the cards post, against a
  post-lineup price, is a new selection rule with its own shadow tag, its own gate-3
  clock and its own decision.
- **Arming (DEFAULT pending owner decision O17).** The capture is armed now, at zero
  credits. Phase 2 follows only after the slot lock and the record guard land.

**How it sits beside the registered candidates.**
- 5c B4 (`lineup_strength`, `star_out`, first look ~2026-09-17) reads the constructed
  orders, the IL cache and the projections bundle. This candidate reads the card. If B4
  serves first, B4 is the base.
- 5e swaps the whole-game offense to the constructed nine's split by the starter's
  hand. This delta is posted-minus-constructed on the same hand. The two add in form,
  not on one reference. C_h here is `SLOT_PA`-weighted, while 5e's `off_vs_*` is
  season-PA weighted, and 5e covers the whole game while this hand term covers only
  `w_O` of it. Their correlation is reported.
- 5f owns the bullpen's hands.
- Posted-nine variants of 5i-B, 5f, 5g and 5d-D are not asked here. Each stays frozen
  on the constructed nine until its own section.

**Disqualification.** The close variants are:
- season-PA weights;
- an equal-weight nine;
- a count of changed bats;
- the constructed-nine gap from `star_out`;
- the season-only form;
- the replacement form (P in place of `z_off`);
- active-roster Offense+ (R5-F5; plan 5.1 bars active-roster variants before the B3/B4
  look);
- the whole game on the starter's hand (`w_O` = 1);
- either segment alone.

Outside a registered look, the only admissible relations of this delta, or a close
variant, to a game outcome or a price are the contaminated screen and, if armed, the
backfill arm, each at its registered time. Any other such relation disqualifies the candidate
under 5c rule 1, on any game and whether it was computed before or after this commit.
Registered looks of other sections on their own columns (5c B3/B4, 5e, 5f, 5i-B) are not
relations of this delta. Counts of capture times that read no price value are not a
relation either.

**Changes after the commit.** Three kinds of change are recorded by dated correction
whenever they occur: the schema number, the first vintage that carries the blocks, and
the restarts under Clock. Other changes are possible only by a dated correction
recorded before the 5c B3/B4 look is recorded, on a fact established without outcomes.
That covers the candidate, the reduction, the fallbacks, the frozen `SLOT_PA` literal,
the frozen starter share, the criteria and the three defaults under Owner decisions. A
change after that closes the section.

**What a pass would change.** No serving flag is added before a pass, because a serving
path for an unmeasured feature is exactly what 5c forbids (5h's rule). On a PASS,
`SERVE_POSTED_LINEUPS` (to be built) lands in `betting_model.py`, default False, with
its tripwire test. Only after the contaminated screen has run without disqualifying, the
owner flips it in one commit with a `MODEL_VERSION` bump, so no ledger pools two
pricers, and a `--context` re-run. A flip is outward-facing and is the owner's call even
on a PASS (7g). It serves on the pricer whose procedure was graded (Fitting). Only sides
with a posted card move. The moneyline, runline and total of a posted game all move,
through the two lambdas. Every repriced side obeys the stale-price rule, the published
slots stay locked, and serving needs the post-lineup price capture (O18).

**No number has been computed on this candidate.**

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

**It ran at n = 0 for four days and now grades 211.** The block reports
`n_vintages`, `n_gradable`, `n_graded`, `n_skipped_no_vintage`, the split date,
`park_basis`, and the same metric set as the contaminated blocks. Current
numbers and what they say are in section 5a; the short version is that the
honest mode loses to the home-field baseline by 0.0012 Brier at t = -0.332,
which is a null, not a win and not a loss.

`vintage_coverage` in the same artifact now carries `n_vintages_backfilled` and
`n_vintages_live` separately, plus `vintage_age_days`. Do not add them together
and quote one number: a backfilled record is evidence about a git blob and a
live record is evidence that the nightly step fired, and only the second of
those keeps accumulating on its own.

### The fallback, and why it is loud

`betting_model.inputs_as_of(date)` returns the vintage bundle when one exists.
When none does it returns the LIVE leaderboards with `source:
"live-leaderboards"`, `contaminated: true`, and a once-per-process log warning.
Nothing in the module silently looks forward. The vintage backtest calls it
with `allow_fallback=False`, which returns an empty bundle instead, so it
cannot accidentally grade a game on contaminated features.

### The benchmark ladder on the vintage eval window (pre-registered 2026-08-16)

**Written before the ladder existed in code and before any tier's number was
computed.** A Brier score with no ladder under it reads however the reader
wants it to; the honest frame is the ordered set of things a model of this
class must beat. The ladder is a VALIDATION SURFACE ONLY: it is dark, no
served probability reads any tier, and no tier ever fills a slot.

`backtest()` gains a `benchmarks` block computed on the vintage EVAL window
(the same games gate 2 grades), with four tiers:

| Tier | What it is | Standing |
|---|---|---|
| `home_constant` | the eval window's own home win rate as a constant probability, the identical base `brier_home_base` already uses | always measurable |
| `market_open_devig` | the de-vigged (proportional) home probability from the cached OPEN snapshot for the game's slate, averaged across the books posting a two-sided h2h market in it | a SUBSAMPLE: only slates with a cached open capture. n is reported, and the tiers it is compared against are recomputed on the SAME games. The subsample is never the headline |
| `market_close_devig` | the same statistic off close-kind snapshots | auto-appears as close captures accrue. Today n = 0 and the block says so rather than omitting the row |
| `elo_literature` | Elo from game results ONLY (`tools/betting_elo.py`): base rating 1500, K = 4, home advantage 24 Elo points, the standard published MLB configuration | the constants are LITERATURE PRIORS, labelled so, and are never fitted on the eval window or anywhere else. Ratings start flat at 1500 each season, no carryover, and every prediction uses only strictly-prior results (a game's probability is computed before its own update) |

**The claim rule, which is the point of pre-registering a display block:**
never claim an unmeasured tier. A tier with n = 0 has no number and no claim. A
tier whose n is below the window's n is a subsample and may be compared only
against the other tiers recomputed on those same games; "the model beats the
market" and "the market beats the model" are both unsayable from a subsample
row unless the same-games column says so. A doubleheader's two games read the
same open capture, which is stated on the block rather than silently averaged
away.

What each tier is FOR: `home_constant` is the floor the module already grades
against; `market_open_devig` is the number that decides whether the model
knows anything the market did not know at open; `market_close_devig` is the
sharper version of that question and the one CLV ultimately answers;
`elo_literature` is the results-only floor a feature model must clear to
justify carrying features at all. A model losing to tier 4 while carrying six
leaderboards is a finding about the features, not about Elo.

**First measurement (run 2026-08-16, after the pre-registration above).** On
the n=269 vintage eval window, 2026-07-28 to 2026-08-16:

| Tier | n | Brier |
|---|---|---|
| market open, de-vigged | 122 (subsample) | **0.24254** |
| Elo, literature config | 269 | 0.24556 |
| home constant | 269 | 0.24875 |
| **the model (vintage)** | 269 | **0.25053** |
| market close | 0 | unmeasured, no claim |

On the 122-game subsample, recomputed on identical games as the claim rule
requires: market 0.24254, Elo 0.24347, home constant 0.24671, model 0.25356.
**The model is last on every comparison the window allows.** A six-leaderboard
feature model behind a zero-parameter results-only Elo is the finding tier 4
exists to expose: the features are not currently paying for their complexity.
That is consistent with the vintage mode's standing null against the
home-field baseline (skill t -0.629 this run) and with B1's boundary result
(the blend optimum at w = 1). None of these orderings is a resolved verdict
at 269 games, 45% of the 600-game gate; the ladder's job is to keep the
ordering in view while the sample accrues.

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

## 7a. The two published slots: Model Watch (owner decision 2026-08-16)

Owner decision 2026-08-06 published a provisional selection rather than
showing an empty module for a season. Owner decision 2026-08-07 split it into
TWO slots, because one slot ranked on EV is one slot that always shows a
longshot. **Owner decision 2026-08-16 supersedes the 2026-08-06 framing**: an
unvalidated model whose honest sample loses to the home team does not publish
a "pick" in any user-facing word, and it does not go dark either. While the
three gates in section 7 are closed, the two slots are a MODEL WATCH. The
selection rules below are unchanged, the provisional labels are unchanged, the
shadow ledger keeps tagging and settling every slot row, and the record funnel
keeps standing behind its blockers. What changes is the frame: each slot is
presented as **today's largest model disagreement** with the market, beside
that selection rule's own settled paper record, not as a recommendation.

### The language scope ruling, recorded here because it looks inconsistent

User-facing language and payload PROSE retire the word "pick" while the gates
are closed. The structural JSON keys (`pick_of_the_day`,
`longshot_of_the_day`, `pick_meta`, `pick_blockers`) KEEP their names. That is
not an oversight: the shadow ledger's slot continuity (`SLOT_TAGS` maps those
key names to `potd_band` and `longshot`) and the record funnel both depend on
the key names, and the same owner decision requires the accrual to CONTINUE
through the reframe. Renaming the keys would orphan every tagged row and reset
gate 3's clocks to zero for a vocabulary point. A key name is plumbing; a
sentence is a claim.

### The self-lift, coded rather than remembered

The frame keys off the same resolution every other surface uses:
`resolve_min_edge` returns `provisional=True` while the gates are shut and
`False` the moment the measured threshold exists. Gates closed serves
`pick_meta.frame = "watch"` with the watch labels; gates open serves
`frame = "pick"` and the pick vocabulary returns automatically, everywhere,
with no edit. The slot labels by frame:

| Slot key | Watch (gates closed) | Pick (gates open) |
|---|---|---|
| `pick_of_the_day` | Model Watch: largest disagreement | Pick of the Day |
| `longshot_of_the_day` | Model Watch: long-price disagreement | Longshot Value of the Day |

### The watch card carries its own evidence (2026-08-16)

Two additions ride with the reframe, both served on the payload so the client
computes neither:

- **The slot's own tag record, inline.** Each slot's meta block carries
  `tag_record`: the settled W-L, push count, net units and ROI of ITS OWN
  shadow tag (`potd_band` for the headline slot, `longshot` for the long
  one), read from `betting_shadow.summary()["by_tag"]`. The card can then say
  "this selection rule is 2-4, -47.9%" without a second fetch, and the client
  labels the sample small until the tag reaches the 100-row sweep floor. The
  tags are never pooled, here or anywhere.
- **A worked de-vig example on the card.** A collapsible block computed from
  the served row and its game's board rows: both sides' raw implied
  probabilities, the overround, the proportional fair probability, the model
  probability, and edge = model minus fair. The disagreement framing only
  means something if a reader can see what the disagreement is measured
  against.

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

A runline pick ALSO carries `tie_atom_caveat` (2026-09-11, L14-01, section 4):
the runline gives the model's whole tie-after-nine mass to both +1.5 sides while
the moneyline splits it, and the sentence says, with numbers read off the row's
own `tie_atom` block and the slot's floor, what this side's probability and edge
would be under the measured split and whether it would still clear the floor.
The split is not served, so the slot still ranks on the served probability.
**2026-09-11, later:** the owner flipped the split on (section 4), so the served
probability the slot ranks on is now the split one; what the caveat says after
the flip is recorded with that commit.

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

## 7b. The market-level publishability gate (pre-registered 2026-08-16)

**This section was written before `market_gate()` or any of its wiring
existed**, in the same discipline as 5a and 11a: the rule goes on the record
before the first number is computed, so the threshold cannot be picked after
the data has been seen.

**OWNER SIGN-OFF 2026-08-18.** The constants stand as registered (n >= 100
canonical games, one-sided 95%, dwell 3, trailing-200 re-open), with the
consequence accepted in the same breath: if the moneyline still grades worse
than a coin when its canonical count reaches 100, the gate closes it and
BOTH Model Watch slots go empty until the re-open test clears. No slot
renders a disagreement on a market the gate has called unpriceable.

### Why a second leg

The dispersion exclusion (section 11a, `betting_model.market_is_publishable`)
is a THEORY leg. It bars the runline and the total because the margin model
that prices them is known to be mis-shaped, and it lifts itself the day
`SERVE_RUN_DISPERSION` flips. What it cannot catch is the other failure mode:
a market whose model is not known to be broken but whose measured
probabilities are, in fact, losing to a coin. The calibration ledger scores
every priced side nightly, so that evidence accumulates on its own; until now
nothing consulted it. This gate is the EVIDENCE leg. The two legs are AND-ed:
a market must clear both to fill a slot or reach the public record. The
dispersion tuple stays exactly as it is.

### The statistic

Computed per market by `tools/betting_calibration.market_gate()`, on the
ledger's settled CANONICAL-SIDE games only:

- **One side per market per game** (home, home runline, over), the
  `CANONICAL_SIDES` choice the ledger already fixes for its bias statistics.
  Brier(p) equals Brier(1 - p), so the two sides of one game are the same
  evidence twice, and counting per-side rows would double n without adding a
  game. `n_games` counts GAMES, deduplicated on game_pk within a market.
- `delta_vs_coin` = mean per-game Brier minus 0.25. Positive means worse than
  a coin.
- `t` = delta_vs_coin / (sd / sqrt(n_games)), sd the sample standard deviation
  of the per-game Brier.
- `worse_than_coin_95` = (n_games >= 100) AND (t >= 1.645): the one-sided 95%
  lower bound on delta_vs_coin sits above zero at a sample the floor accepts.

One honesty note rides with it: the ledger's model probabilities are priced
from season-to-date inputs, which FAVOURS the model. A market that resolves
worse than a coin with the contamination helping it has earned the verdict
with room to spare, so the leg's direction of error is the safe one.

### The rule

- **LEDGER-CLOSED**: `worse_than_coin_95` is true on the market's FULL settled
  canonical sample for **3 consecutive nightly evaluations**.
- **RE-OPENS**: the same statistic computed on the **trailing 200** settled
  canonical games fails to resolve worse-than-coin (`worse_than_coin_95`
  false there) for **3 consecutive nightly evaluations**.

An evaluation is one per UTC calendar day. The pipeline can run more than once
in a day and the dwell counters move at most once, because "3 consecutive
evaluations" means three nights, not three process starts; a second build on
the same date refreshes the statistics and leaves the dwell where it was.

### Where each constant comes from, honestly

| Constant | Value | Standing |
|---|---|---|
| n floor | 100 games | mirrors `betting_shadow.MIN_BETS_FOR_SWEEP`, so the module has one small-sample floor rather than two |
| z | 1.645 | `betting_model.Z_95_ONE_SIDED`, the same one-sided 95% every other gate in this module tests at |
| dwell | 3 consecutive evaluations | POLICY, chosen for hysteresis, not measured |
| trailing window | 200 games | POLICY, chosen for hysteresis, not measured |

The dwell and the trailing window are named as policy because that is what
they are. Nothing in the ledger picked 3 or 200; the dwell exists so a single
noisy night cannot flap a market closed and open again, and the trailing
window exists so a market that has genuinely improved can re-open on recent
evidence without dragging its whole history behind it. Pretending either
number was measured would be the exact laundering the rest of this document
exists to prevent.

### What it can do today: nothing, and the table must say so

On the live ledger (2026-08-16) moneyline holds **49 canonical settled
games** (98 settled rows across both sides), runline 48, total 47. Note the
basis: the ledger's own `canonical_side.n` reports 50 and 56 canonical ROWS
for those two markets, because a game that appears on two slates (a
postponement) or at two lines settles more than one canonical row, and the
gate deduplicates to GAMES. Every market is under the 100-game floor, so
`worse_than_coin_95` is false everywhere and this gate can CLOSE NOTHING yet. Its published state for all
three markets is `unresolved`, and the table carries that word rather than
"open": "open" would read as a verdict, and no verdict exists at n < 100.
The runline and the total are still off the slots today, on the theory leg
alone.

### Wiring

- `tools/betting_calibration.market_gate()` returns the per-market statistic:
  `{n_games, brier, delta_vs_coin, t, worse_than_coin_95}`, with an optional
  trailing-window form for the re-open test.
- `betting_export.market_publishability()` combines the dispersion leg, the
  ledger leg and the dwell state into one table, one row per market, each row
  carrying `publishable` and the reason. The payload publishes the table.
- The dwell state persists in `.cache/betting/market_gate_state.json`. The
  append-only learning history (`data/betting_learning.json`) was considered
  first and refused, with the reason on the record: its rows are appended by
  betting_learning.py's own build under its own append-only check, that module
  is outside this lane's ownership, and a foreign key written into its
  artifact from here would be dropped on the next nightly rebuild. A state
  file under `.cache/` survives the checkout the same way the record log does.
- BOTH seams consult the table, the same two funnels the dispersion exclusion
  guards: `_floor_clearing_sides` (the slots) and `append_record` (the public
  record). One repair landed with the wiring: record rows carry the FEED
  vocabulary (`h2h` / `spreads` / `totals`) while both guards test board
  names, so the dispersion guard at `append_record` had been checking a key
  the feed vocabulary walks straight past. The funnel now canonicalizes the
  row's market through `board_market()` before either leg is consulted.
- `betting_shadow` does NOT consult it, for the same reason it does not
  consult the dispersion exclusion: the paper ledger and the calibration
  ledger are the instruments that accumulate the settled evidence a closed
  market needs to ever re-open, and excluding them there would freeze every
  closure permanently. `test_betting_market_gate.py` pins the non-consultation
  the way `test_betting_dispersion_exclusion.py` pins it for the theory leg.

---

## 7c. Props value bets (pre-registered 2026-08-16; ships INERT)

**This section was written before any of the code existed**, in the same
discipline as 7b: the shape, the caps, the arming mechanism and the tag rules
go on the record first, so none of them can be tuned after the first pull.
Everything below builds and verifies against fixtures; on this repo's boxes
the machinery is INERT because neither arming variable is set.

**OWNER ARMING DECISION 2026-08-18: 120 credits a month, 3 games a day, all
four registered markets.** The box action is one line in the same root-owned
environment file that carries the odds key: `EEPHUS_PROPS_CREDITS=120`. At
~4 credits per event and 12 a day the ceiling is ~370 a month SHARED with
the ~186 the team snapshots already spend, inside the 500 tier; the hard
guard refuses before any request that would cross 120 on the props ledger
alone. Until that line lands on the box the machinery stays inert and the
page says so.

### The owner-approved shape

| Parameter | Value | Standing |
|---|---|---|
| games per day | `PROPS_MAX_GAMES_PER_DAY = 3` | owner band is 2 to 3; 3 is pre-registered here and changing it is one constant edit, recorded in this table |
| monthly credit cap | `EEPHUS_PROPS_CREDITS` (env) | the owner's number, inside 60 to 180. The machinery NEVER assumes one: an unset cap means no pull, however the key is set |
| markets | `PROPS_MARKETS`: `pitcher_strikeouts`, `batter_total_bases`, `batter_hits`, `batter_home_runs` | key names verified against The Odds API market list on 2026-08-16 |
| shadow tags | `props_<market>`, one per props market, per-tag budget 3 rows a slate | NEVER pooled with the team tags, and never with each other; section 7a's rule, one level down |
| min_edge | swept PER TAG, same 100-settled-row floor as every team tag | a props threshold fitted to team-market evidence would be wrong for both |

### The arming mechanism, and what inert means

The per-event pull fires only when BOTH are set:

- `EEPHUS_ODDS_API_KEY`, the same key the team feed uses, and
- `EEPHUS_PROPS_CREDITS`, the owner's monthly props budget.

Either one absent leaves the machinery INERT: `betting_ingest.run("props",
event_ids=[...])` refuses without spending, and the payload's `props_value`
block says exactly which of the two variables is missing, by name, so the
page can state why the section is empty instead of rendering a blank. The
key alone must not arm props, because the key alone is the 500-credit team
budget and props bill against a SEPARATE owner-approved number.

### The credit arithmetic, per event this time

The per-event endpoint bills markets x regions PER EVENT: 4 markets x 1
region = 4 credits per event, so a full 3-game day is 12 credits and a month
of daily use is ~372, which is why the cap is the owner's call and not a
default. The guard is HARD and it sits BEFORE the request:
`.cache/odds/props_spend.json` is the calendar-month ledger, and any request
whose cost would push the month's spend past `EEPHUS_PROPS_CREDITS` is
refused with the arithmetic in the refusal. A guard that reconciles after
the response has already spent the credits it was guarding.

Snapshots land at `.cache/odds/<date>-props-<event_id>.json` with kind
`props`, immutable exactly like the team snapshots, and invisible to
`list_snapshots()` (the team snapshot name pattern does not match them), so
nothing about the open/close resolution changes.

### Game selection, deterministic

The watch-slot game first (the published `pick_of_the_day` row's game, when
one exists), then the remaining games ranked by their largest team-market
edge, descending, ties to the lower game_pk, capped at
`PROPS_MAX_GAMES_PER_DAY`. Both inputs are already on the payload, so two
identical boards select identical props games.

### Pricing: the team-market discipline, reused verbatim

`betting_export.props_value_bets()` prices each (market, player) pair through
the SAME `_market_view` function the team board uses, not a copy: consensus
point first by book count, prices shopped only among books posting it, fair
probabilities from the minimum-hold book on that line, and the
staleness / hold / consensus-distance rejection ledger published per pair.
The model probability is the EXISTING Poisson props lambda (section 4's fair
lines, on the A5a vs-hand order) evaluated at the BOOK's line, with
whole-number lines push-conditioned exactly as `total_side_probabilities`
does for totals. Edge, EV per unit, quarter Kelly and the provisional
labelling are the team rows' own fields, byte for byte the same builder
(`_priced_side`).

### Publishability: uniform, not exempt

Props markets are NOT in `DISPERSION_SENSITIVE_MARKETS` (the margin model
does not price them), so the theory leg does not bar them. Each props market
enters `market_publishability` as its own market with the same ledger
evidence leg as section 7b: n >= 100 settled canonical rows, canonical side
`over`, deduplicated per (market, game, player) so two books, or one player
at two lines, count once, exactly the way one team game at two totals counts
once, the same z, the same dwell. The calibration ledger logs
props sides as distinct markets (`props_<key>`); `betting_settle.grade_side`
cannot grade a player count off a run score, so props calibration rows stay
OPEN rather than being guessed, the props ledger legs read `unresolved`, and
the table says so. A props grader against box scores is the named unlock and
is NOT part of this lane.

### What may ship while everything is unresolved

The `props_value` block is fixture-verified machinery plus an inert state
sentence. When armed and priced it publishes watch-frame rows under the same
floor and the same provisional labels as the team slots; nothing props-shaped
reaches the public record, and no props row may enter a team tag's sweep
(`test_betting_props.py` and `test_betting_shadow.py` pin both).

---

## 7d. Any-market slots (owner decision 2026-09-05)

Owner instruction, in intent: the Pick of the Day is not locked to the moneyline.
Spread, moneyline, overs/unders and player props are all allowed; the slot finds
the best pick. `betting_model.SLOT_MARKET_POLICY = "any"` implements it.

What changes:

- `_floor_clearing_sides` no longer skips a market. The dispersion leg (11a) and
  the ledger leg (7b) STAMP the candidate instead: `evidence_closed` on the row,
  and `_publish_slot` attaches `caveat` (runline / total, the Poisson
  underdispersion) and `evidence_caveat` (a ledger-closed market) beside
  `market_policy`. The row says what was overridden; nothing is hidden.
- Priced props value rows (7c) enter the same candidate list on the same floor
  and the same rule. To make that possible the props fair lines and value rows
  are priced BEFORE the slots (a first pass with no watch-slot preference) and
  the served props block is rebuilt AFTER the slots exactly as before. Inert
  while the props pull is unarmed.
- `append_record` keeps every row and stamps `dispersion_sensitive`,
  `evidence_closed` and `market_policy` on it, computed on the BOARD name
  (the 2026-08-16 vocabulary repair still applies).
- `market_publishability` still measures and publishes both legs per market,
  unchanged; `publishable` is True under the policy, `policy_override` says
  when the legs would have barred it, and the reason sentence keeps the legs'
  own words after the override clause. The client renders a both-legs market
  as "two independent cautions" under the policy and as "watch-only" without it.
- `SLOT_MARKET_POLICY = "dispersion_gated"` restores the 2026-08-14 / 2026-08-16
  behaviour at both seams, so the earlier decision is one constant away and the
  tests pin both states.

What does NOT change: the selection rules (7a), the shared floor, the tags, the
shadow ledger (which never excluded these markets), the record funnel's
append-only chain, and the props credit discipline (7c). The rule itself is not
reliability-aware: a runline probability off the underdispersed Skellam can win
the headline slot on confidence it has not earned, which is why the row carries
the caveat and why the accuracy-and-ROI selection bake-off (a registered lane,
not a silent edit) is the next step: rank candidates on a per-market
reliability-adjusted probability and EV, scored on the settled ledger and the
vintage backtest before it replaces this rule.

Settlement gap, stated plainly: a props row that wins a slot settles only when
the props box-score grader exists (7c). Until then a props pick accrues no record
of its own and the slot meta says so through the tag record.

---

## 7e. The per-market objective and the coefficient fit (2026-09-06)

**Standing on the pre-registration, stated first because it is weaker here than
in 5a, 7b and 11a.** Those sections were written before their code existed and
say so. This one is not that. The CLAUSES below are the owner's, fixed in the
2026-09-05 plan and written into `betting_model.PER_MARKET_OBJECTIVE` and
`betting_model.RIDGE_FIT_GATE_CRITERIA` before either was run; the thresholds
(-0.002, -0.001, t >= 1.645, n >= 100, split quantiles 0.6 / 0.7 / 0.8) come
from that plan and were not chosen after the grids were read. What this section
cannot claim is that the PROSE predates the numbers, because it does not: the
tables and the text were written in the same session as the runs. Read the
clauses as fixed and the commentary as after the fact.

This is the "accuracy-and-ROI selection bake-off" section 7d names as the next
step. It is registered, it is measured, and it changes nothing that is served.

### 7e-A. The per-market objective (owner decision 6)

**Lexicographic, accuracy first.** For each market the board prices:

1. **The accuracy leg, read FIRST.** Paired per-game Brier and log loss on the
   vintage eval window against the section 6 ladder tiers, always including the
   market OPEN tier recomputed on the same games. A subsample may only appear
   against tiers recomputed on exactly its own games, which is the section 6
   claim rule and is why every tier in the table below is scored on the
   same-games window rather than on the full 487.
2. **The ROI leg.** Flat-stake ROI with the one-sided 95% lower bound
   `sweep_min_edge` already uses, plus expected log growth at quarter Kelly on
   the RECORDED price, computed per `(market, rule)` cell of the shadow ledger.
   The record stakes flat 1 unit and always will (7a); the Kelly number is a
   reported diagnostic and nothing stakes it.
3. **CLV is one key.** `roi.clv_unavailable` carries the reason, not a column of
   nulls: *"close job never installed; 0 settled ledger rows carry a close
   price"*. Measured 2026-09-06: 22 cached odds snapshots, every one of kind
   `open`, zero of kind `close`, and 0 of the 255 ledger rows carry a close
   price under any name.
4. **The combination.** A market may set a threshold only when its accuracy leg
   is non-inferior to the market open on the same games (paired Brier
   `lb95 >= -0.002`) AND its ROI leg clears `lb95 > 0` at `n >= 100` inside ONE
   `(market, rule)` cell. A market that fails the accuracy leg has its ROI leg
   REPORTED and NOT CONSULTED: a positive ROI on a market whose probabilities
   lose to the open is a sample, not a finding, and `roi_cells_clearing` is
   empty for such a market even when a cell would have qualified on its own
   numbers.
5. **Floors.** 100 same-games comparisons per market for the accuracy leg, 100
   settled rows per `(market, rule)` cell for ROI. Both are 100 because
   `betting_shadow.MIN_BETS_FOR_SWEEP` and the 7b n floor are 100; this module
   has one small-sample floor, not three.

**Where the market prices come from.** `betting_model._market_open_by_market` is
a SECOND walker over the same snapshots, deliberately: `_market_fair_probs`
serves the section 6 ladder and its numbers are published, so widening it to
three markets would change that ladder as a side effect of adding this block.
The three rules are the same three: earliest capture per slate, proportional
de-vig, average across the books posting a two-sided market. The runline event
is "the HOME side of the posted 1.5 spread covers", whichever way the book posts
it, because fixing the event as "home wins by 2 or more" is unpriced on every
game where the home team is the underdog. The total is the modal posted line,
and on a whole number both sides of the comparison are conditional on no push
(the de-vigged two-way market is, and `total_side_probabilities` is).

**The cross-check that the second walker is the same walker.** On the moneyline
it reproduces the section 6 ladder's own `same_games` block to the digit:
n = 254, market open 0.23467, model 0.24576, constant 0.24944, Elo 0.24505.

#### Measured 2026-09-06

Vintage eval window from 2026-08-01, 487 graded games, 22 slates with an open
capture. Every tier scored on the same-games window for its market. Positive
delta means the MODEL is better than the market open.

| market | n same-games | model Brier | open Brier | constant Brier | Elo Brier | paired delta | t | lb95 | accuracy |
|---|---|---|---|---|---|---|---|---|---|
| moneyline | 254 | 0.24576 | 0.23467 | 0.24944 | 0.24505 | -0.011093 | -1.929 | -0.020556 | FAIL |
| runline | 247 | 0.23649 | 0.23163 | 0.24980 | n/a | -0.004859 | -0.636 | -0.017432 | FAIL |
| total | 250 | 0.27530 | 0.25128 | 0.24998 | n/a | -0.024015 | -2.431 | -0.040268 | FAIL |

Log loss, same pairs: moneyline -0.027083 (t = -2.162), runline -0.010600
(t = -0.644), total -0.084821 (t = -2.272). Games in the eval window with no
open capture: 233 / 240 / 231. Six totals landed exactly on the line and were
dropped as pushes from both sides.

Against the constant tier instead of the open, the same paired Brier:
moneyline +0.003681 (t = 1.664, lb95 +0.000042), runline +0.013309 (t = 1.170),
total -0.025312 (t = -2.537). **The total is worse than its own base rate**, at
two and a half standard errors, which is the section 11a dispersion defect
showing up in a market rather than in a variance ratio. The moneyline is the
only market that beats a constant, and it does so by less than it loses to the
open.

ROI leg, `per_market_cap` era, one row per `(market, rule)` cell:

| cell | n | ROI | ROI lb95 | quarter-Kelly log growth per bet |
|---|---|---|---|---|
| moneyline::board_all | 43 | -0.30925 | -0.56745 | -0.009373 |
| moneyline::longshot | 4 | -0.22500 | -1.32907 | +0.001668 |
| moneyline::potd_band | 9 | +0.08686 | -0.47750 | +0.001876 |
| runline::board_all | 71 | -0.01306 | -0.18604 | -0.003200 |
| runline::potd_band | 6 | -0.47935 | -0.97385 | -0.025869 |
| total::board_all | 100 | -0.12844 | -0.28706 | -0.008189 |

One cell of six meets the 100-row floor (`total::board_all`) and it does not
clear. `moneyline::potd_band` is the only positive ROI on the board and it is
nine bets; its lower bound is -0.478.

**Verdict: no market may set a threshold, and every one of them fails on the
accuracy leg alone.** The ROI leg never had to be consulted. That is the
lexicographic order working as intended rather than a shortage of ROI data,
and it is worth saying which way round it fell: if the order had been ROI
first, `moneyline::potd_band` at +8.7% over nine bets is exactly the kind of
row a rule reads as encouraging.

**Standing: dark.** `betting_model.PER_MARKET_SURFACE`. No slot, no record row,
no exported edge and no `min_edge` reads this block. It states what each market
would have to show; nothing consults it, the same standing the section 6 ladder
ships under.

### 7e-B. The coefficient fit: a wrong sign, and repairing it costs accuracy

**The defect.** The vintage fit half (305 games, 610 design rows, split at
2026-08-01) returns

    b0 4.345387   b1 -0.037205   b2 -0.096479   b3 0.594771   b4 0.149360
    rmse 3.288484   r2 0.003049   and then diff_shrink 1.28

`b1` is the scoring team's OWN offense and it is negative: the fit says a better
offense scores fewer runs. The contaminated 4,248-row fit puts the same term at
+0.260319, so the sign is not a property of the feature; it is 610 rows at
r2 = 0.003 read as a slope. `diff_shrink` then comes back at 1.28, EXPANDING a
differential that a parameter named "shrink" exists to contract.

**The challenger.** The same five coefficients as a ridge shrunk toward
`LITERATURE_COEFFS`, with three hard sign constraints (`b1 > 0`, `b2 < 0`,
`b3 > 0`), solved exactly by enumerating the eight faces of the constrained
orthant rather than by any iterative projection whose step size nobody
registered. The penalty is chosen on the FIT half alone, by moneyline log loss
on an inner date split at q = 0.75. One constant moves the whole thing:
`betting_model.SERVE_RIDGE_FIT`.

**The family does not contain the incumbent on this window**, which is worth
saying because the opposite is the natural assumption about a ridge. Penalty 0
reproduces the OLS to 1e-14 only when the OLS is already sign-feasible; where it
is not, the CONSTRAINT still moves it. Measured on the vintage fit half, the
path is:

| penalty | b1 | b2 | b3 | b4 | constraint binding |
|---|---|---|---|---|---|
| 0.0 | 0.000000 | -0.096682 | 0.576559 | 0.147895 | b1 |
| 0.001 | 0.000000 | -0.094463 | 1.031442 | 0.147881 | b1 |
| 0.01 | 0.000000 | -0.088626 | 2.352576 | 0.146428 | b1 |
| 0.1 | 0.000000 | -0.093504 | 3.079566 | 0.131576 | b1 |
| 0.3 | +0.041543 | -0.110087 | 3.157603 | 0.114985 | none |
| 1.0 | +0.139601 | -0.153313 | 3.186386 | 0.099384 | none |

(OLS for comparison: b1 -0.037205, b2 -0.096479, b3 0.594771, b4 0.149360.) The
penalty grid cannot return the incumbent here, so the gate compares two
genuinely different fits rather than a fit against a shrunken copy of itself.

**The gate**, `RIDGE_FIT_GATE_CRITERIA`, at split quantiles 0.6, 0.7 and 0.8,
all three or nothing: (1) non-inferiority against OLS, paired per-game Brier
`lb95 >= -0.001`; (2) superiority over the literature Elo tier, paired Brier
`t >= 1.645`; (3) paired log loss not worse on the point estimate. Both arms
re-solve the tie rate, `diff_shrink` and the home adjustment on their own fit
half, so a tuned incumbent is never graded against an untuned challenger.

#### Measured 2026-09-06

| split | cut | n_fit | n_eval | Brier delta | lb95 | log loss delta | Elo t (ridge / OLS) | checks |
|---|---|---|---|---|---|---|---|---|
| 0.6 | 2026-08-13 | 469 | 323 | -0.000221 | -0.000774 | -0.000442 | 1.641 / 1.625 | 1 of 3 |
| 0.7 | 2026-08-19 | 548 | 244 | -0.000203 | -0.000553 | -0.000411 | 1.632 / 1.645 | 1 of 3 |
| 0.8 | 2026-08-25 | 627 | 165 | +0.000213 | -0.000611 | +0.000432 | 2.098 / 1.937 | 3 of 3 |

**Verdict: INDETERMINATE. `SERVE_RIDGE_FIT` stays False and the OLS keeps
serving.** One split of three passes.

Two readings that belong beside it, both persisted, neither a criterion:

- **Check 2 is a bar on the model class, not on the challenger.** The incumbent
  misses the Elo bar at q = 0.6 (t = 1.625) and lands exactly on it at q = 0.7
  (t = 1.645). A split where the ridge misses that bar is not evidence that the
  ridge broke something. Every split persists `elo.ols_vs_elo` beside
  `elo.ridge_vs_elo` so the two cannot be confused.
- **The served window is where the interesting number is.** On the shipped cut
  (2026-08-01, fit 305 / eval 487, the window a flip of the flag would actually
  change) the ridge at penalty 0.3 repairs every symptom that motivated it:

  | quantity | OLS | ridge | note |
  |---|---|---|---|
  | b1 | -0.037205 | +0.041543 | sign repaired, and the constraint is NOT binding there |
  | b2 | -0.096479 | -0.110087 | |
  | b3 | 0.594771 | 3.157603 | literature prior is 3.20 |
  | b4 | 0.149360 | 0.114985 | |
  | diff_shrink | 1.28 | 1.08 | still above 1, less so |
  | home adj | -0.0443 | +0.0063 | sign repaired |
  | eval Brier | 0.24460 | 0.24522 | delta -0.000617, t -0.812, lb95 -0.001868 |
  | eval log loss | 0.68228 | 0.68352 | |

  Every coefficient becomes more plausible and the out-of-sample Brier gets
  worse. Not significantly worse (t = -0.812), and its one-sided lower bound
  sits at -0.001868, below the registered -0.001 non-inferiority bar. So the
  served window would not have carried the flip either.

**What that means, and it is a finding about the FEATURE rather than the
solver.** At the constrained optimum the own-offense term is pinned to EXACTLY
zero at all three gate splits, at the penalties the inner split chose (0.01,
0.003, 0.1). On vintage features that column is not paying for itself at any
penalty the selection was willing to take. The wrong sign is real; repairing it
buys nothing measurable; and the reason both statements hold at once is that the
term carries no signal to get the sign of.

### 7e-C. The fit window: growing it is measurably worse

`VINTAGE_FIT_TARGET_GAMES = 300` anchors the vintage fit half, so every new
slate goes to the eval window and the fit stays at about 300 games forever. The
plan asked for it to grow. It does not, and the reason is measured.

The two shipped configurations cannot be compared directly, because the fit half
and the eval half are COMPLEMENTS: growing one shrinks the other, so their two
Brier numbers are not paired. `betting_model.fit_window_probe` answers the
question the only way it can be answered, by holding the eval window and varying
only the fit. Anchored is the earliest 305 games before the cut, which is what
the shipped rule builds; grown is every gradable game before the same cut. Both
arms price the same eval games and re-solve every correction on their own fit
window. Positive delta means grown is better.

| split | cut | anchored n_fit | grown n_fit | n_eval | delta | t | lb95 |
|---|---|---|---|---|---|---|---|
| 0.6 | 2026-08-13 | 305 | 469 | 323 | -0.002789 | -2.107 | -0.004967 |
| 0.7 | 2026-08-19 | 305 | 548 | 244 | -0.000133 | -0.162 | -0.001482 |
| 0.8 | 2026-08-25 | 305 | 627 | 165 | +0.001750 | +0.867 | -0.001570 |

The grown fit is worse at 0.6, a coin flip at 0.7 and better at 0.8 on the point
estimate, but it misses the -0.001 bar (reused from the ridge gate rather than
invented for this) at ALL THREE splits: the lb95 column reads -0.004967,
-0.001482 and -0.001570, and every one of them is below -0.001. The split where
growth looks best is no exception, because 165 eval games do not buy an interval
tight enough to carry a +0.001750 point estimate over the bar.
`VINTAGE_FIT_WINDOW_GROWS` stays False.

It is worse WHILE LOOKING HEALTHIER. The grown fit at q = 0.6 carries b3 = 2.83
against the anchored 0.59, a park coefficient much nearer the literature prior,
and still grades 0.00279 of Brier worse on the same 323 games. Coefficient
plausibility and out-of-sample accuracy point in opposite directions on this
sample, twice now, and the flags follow the accuracy.

The accounting cost the probe cannot see: on the 2026-09-06 archive (792
gradable games over 59 dates) anchoring leaves 487 eval games and a date-share
split leaves 408, which is 79 fewer on the `VINTAGE_MIN_GRADED_GAMES` clock. No
paired statistic can price that, because those games are the ones the paired
statistic would need in order to exist.

### What ships from 7e

Three measurements and no behaviour change. `SERVE_RIDGE_FIT` False,
`VINTAGE_FIT_WINDOW_GROWS` False, the per-market block dark. The artifact keys
are `data/betting_model_eval.json -> per_market`, `-> ridge_fit`, and
`-> ridge_fit.fit_window_probe`. The one thing 7e establishes for the record is
that the moneyline is the only market this model beats a constant on, it loses
to the market open on all three, and the total loses to its own base rate.

---

## 7f. The total level: why most value totals are Overs (BET1, 2026-09-11)

The owner asked, on 2026-09-11, whether a board where most edge and value bets
are Overs is a bug or a feature. **It is a bug, it is systematic, and its
mechanism is not the one the 2026-09-05 plan (B-TOTAL-LEVEL) assumed.**

### The skew is on every slate

Every cached open capture in `.cache/odds/` re-priced on the served context
coefficients and the dated leaderboard vintage for its slate, actual starters
standing in for the probables (26 slates with a completed game, 425 games):

| Basis | n | mean fair total minus line | positive-edge Over / Under | at the 0.06 floor |
|---|---|---|---|---|
| served 2026-09-11 board | 15 | +0.893 (median +0.85) | 13 / 2 | 12 / 0 |
| every cached slate, re-priced | 425 | +0.604 (median +0.65), positive on 26 of 26 slates | 323 / 102 | 232 / 44 |
| calibration ledger as served, inverted through the served Poisson | 100 | +0.652, positive on 18 of 18 slates | 155 / 46 | 112 / 19 |

### The mechanism, decomposed on the vintage FIT half only

The 305 gradable games before the 2026-08-01 split, priced by the served
coefficients on dated features, against the runs actually scored. The market is
not read here.

| Piece | Measured |
|---|---|
| mean model total | 8.8649 |
| mean actual total | 8.8066, so the LEVEL bias is **+0.058 runs** |
| intercept 2*b0 + b4 | +9.0023 |
| offense, prevention, park terms | -0.0041, -0.0807, -0.0526 (they pull the level DOWN) |
| in-sample over all 2,200 games | 8.9632 against 8.9632, zero by the OLS identity |
| actual total, fit half | median 8, var/mean 2.347 |

`b0` is not too high and the prevention and park terms do not push the level
up. What is wrong is the Poisson CENTRE. A Poisson with the right mean puts its
middle at that mean; real run totals, skewed by blowouts, split about a run
lower, and a book posts its line where they split. So a correctly levelled
Poisson compares its mean with the market's median and calls the Over:

| Line | observed Over | served Poisson | Poisson recentred to the true mean | NB2 (alpha 0.3366 fitted on the same half) |
|---|---|---|---|---|
| 7.5 | 0.5344 | 0.6485 | 0.6416 | 0.5570 |
| 8.5 | 0.4328 | 0.5206 | 0.5131 | 0.4699 |
| 9.5 | 0.3869 | 0.3958 | 0.3885 | 0.3895 |
| 10.5 | 0.3213 | 0.2849 | 0.2785 | 0.3178 |

A mean recentre moves nothing. A total-scoped dispersion fixes most of every
line. The NB2 column is a fit-half DESCRIPTION, not a graded result; it is the
pointer for B-TOTAL stage 2.

### The flag, and its pre-registered gate

`SERVE_TOTAL_LEVEL` (default False) is one additive constant on the Poisson
total mean, fitted on the vintage fit half by over/under log loss at the fixed
lines 7.5, 8.5, 9.5 and 10.5. It prices the TOTAL ONLY: the margin, the
moneyline and the runline come from the unshifted lambdas and are
byte-identical, which `test_betting_total_level.py` asserts at the model and at
the export. `fair_total` stays the expected runs; `total_price_mean` names the
mean the total is priced on. On the served pricer the fitted constant is
**-0.2315 runs** (mean arm -0.0583).

The gate was written into `betting_model.TOTAL_LEVEL_GATE_CRITERIA` before any
eval-window outcome was scored: the centre arm must beat the incumbent on the
grid's summed log loss at t >= 1.645 AND be no worse at three of the four lines,
at the anchored split and at date quantiles 0.6, 0.7 and 0.8, all four or
nothing. Result, `python betting_model.py --total-level`, 2026-09-11:

| split | cut | n_fit | n_eval | centre delta | grid log loss delta | t | pass |
|---|---|---|---|---|---|---|---|
| anchored | 2026-08-01 | 305 | 548 | -0.2731 | -0.000053 | -0.005 | no |
| 0.6 | 2026-08-16 | 507 | 346 | -0.1949 | -0.007571 | -0.714 | no |
| 0.7 | 2026-08-22 | 587 | 266 | -0.1754 | -0.008713 | -0.797 | no |
| 0.8 | 2026-08-29 | 679 | 174 | -0.1771 | -0.017736 | -1.309 | no |

**Verdict FAIL; the flag stays False.** At every split the recentre improves
Over 7.5 (t +3.60 at the anchored split) and damages Over 10.5 (t -3.48): one
shift cannot fix a wrong shape. The mean arm is identically zero inside the lab,
because the lab refits OLS on each fit half. The posted-line diagnostic (never a
criterion) says the same thing from the other side: on the 292 anchored eval
games with an open capture the incumbent's Over sits +0.044 above the realised
rate and the recentre +0.008.

What flipping it would do, measured on the served constant: the moneyline and
runline are unchanged on every slate; on the 2026-09-11 board positive-edge
totals go 13/2 to 12/3, floor-clearing 12/0 to 7/2, and the Pick of the Day
(ATL moneyline -178) does not change; across the 26 cached slates positive-edge
totals go 323/102 to 281/144, floor-clearing 232/44 to 171/71, 42 games change
their positive-edge side, and the headline slot changes on 6 slates. To flip:
the gate ships, this section and the tripwire move together, `MODEL_VERSION` is
bumped, and `--context` is re-run so `total_level` is written.

### The invariant that would have caught it

`betting_export.total_level_check` runs on every build. Per priced total it
takes the Over's model probability minus its de-vigged market probability at the
posted line and averages over the slate; it FIRES when at least 8 totals are
priced, the mean lean exceeds 0.03 (the canonical total bias band B-TOTAL
already names) and it is distinguishable from zero at one-sided 95%. When it
fires the build log warns, the payload carries `total_level_check` with the
sentence, every priced total row carries `total_level_caveat`, and the page
shows it on the board head, on a total's best-value badge and on a total slot.
The market is a diagnostic target here: nothing priced reads the block. The
run-scale gap (`mean_gap_runs`) rides beside it as description only, because it
reads about +0.6 on a model whose level is perfect.

It fires on the 2026-09-11 board (mean lean +0.0998, t 4.79) and on 22 of the 26
cached slates; with the unserved recentre it would fire on 11.
`test_served_invariants.test_a_board_whose_totals_lean_says_so` holds every
built board to it, with a mutation test on the incident shape.

## 7g. The total's shape: a total-scoped dispersion (pre-registered 2026-09-11)

**Written before the code exists and before any eval-window game has been scored
under the candidate.** Section 7f found that the Over lean is a SHAPE defect: the
level is right on the fit half and one shift cannot fix every line. This is the
shape half, the direction section 11a left on the record ("a correction scoped to
the total ... is the live direction").

**Disclosed, because it is what makes the expectation a PASS.** Two earlier reads
point the same way and neither is this gate. (1) Section 11a, 2026-08-09, on the
1,775-game live cache with NB2 on both sides at alpha 0.28425: criterion 3 (the
total over 9.0) improved by +0.010709 at t = +2.545; a different sample, a different
mode (live features, not vintages) and a whole-model correction, not a total-scoped
one. (2) The BET1 lane described NB2 on the vintage FIT half (grading nothing): the
Over 7.5 bias falls from +0.114 to +0.023 and Over 8.5 from +0.088 to +0.037. The
eval half has not been read under any NB total.

**The candidate.** The Over, Under and push are priced off the total of two
independent NB2 sides with the SAME dispersion alpha_T, at the model's own
unshifted lambdas, through `_score_joint`'s total convolution. The margin
distribution, and so the moneyline and the runline, are built from the first
(served) pass and cannot move; `fair_total` stays the expected runs. No recentre.
alpha_T is fitted on the fit half ALONE as the argmin of the summed over/under log
loss at the fixed grid (7.5, 8.5, 9.5, 10.5), golden-section on [0.0001, 2.0].

**Criteria**, the 7f form so the two halves of the repair are judged alike. Splits:
the anchored served split and the date quantiles 0.6, 0.7, 0.8 of the
vintage-gradable dates; every split refits the coefficients, tie rate, differential
shrink and home adjustment on its own fit half, fits alpha_T on that same fit half,
and scores the eval half. On each eval half BOTH must hold, at ALL FOUR splits or
the verdict is not ship: (1) paired per-game total log loss summed over the grid,
incumbent Poisson minus candidate, greater than 0 at one-sided t >= 1.645; (2)
paired per-game log loss at EACH grid line not worse on the point estimate for at
least three of the four lines. Structural and asserted by test, not measured: the
moneyline and runline byte-identical with the flag on and off. Fit half >= 100
games and eval half >= 50 or the split cannot pass. Diagnostics, never criteria:
model P(over) at the posted line minus the realised over rate on eval games with a
cached open capture, and the Over/Under split of positive-edge totals.

**Serving.** `SERVE_TOTAL_DISPERSION`, default False, flipped only from this gate.
Flipping it moves every total side's probability, edge, EV and Kelly, which total
side is value on some games, and the slots whenever a total was or becomes their
best row; nothing on the moneyline or the runline. With it: `MODEL_VERSION` bumps
(every settled total row was priced by the Poisson), the tripwire test moves, and
`--context` is re-run so the served key is written. A flip is outward-facing and is
the owner's call even on a PASS.

### Result (run 2026-09-11, once): FAIL, and the Poisson total keeps serving

`python betting_model.py --total-dispersion`, vintage-gradable games only:

| split | cut | fit / eval | alpha_T | grid log loss delta | t | lines not worse | pass |
|---|---|---|---|---|---|---|---|
| anchored | 2026-08-01 | 305 / 548 | 0.638 | +0.0119 | 0.73 | 2 of 4 | no |
| 0.6 | 2026-08-16 | 507 / 346 | 0.459 | +0.0290 | 1.61 | 4 of 4 | no |
| 0.7 | 2026-08-22 | 587 / 266 | 0.453 | +0.0357 | 1.62 | 4 of 4 | no |
| 0.8 | 2026-08-29 | 679 / 174 | 0.461 | +0.0178 | 0.65 | 2 of 4 | no |

The dispersed total beats the Poisson on the point estimate at every split and
clears t = 1.645 at none. It fixes the tails (Over 10.5 at the 0.6 split: Poisson
0.268, NB 0.314, observed 0.347; per-line t 2.54) and OVERCORRECTS the middle: on
the anchored split it prices Over 8.5 at 0.445 against 0.485 observed, where the
Poisson said 0.519. So one dispersion cannot fit both the median and the tails of
these totals either, the same lesson 11a recorded for the margin. What remains
open, each needing its own section: a total distribution with a free median
(a quantile or isotonic map of the Poisson CDF fitted on the fit half), or a
bivariate model of the two scores. Until then the lean is DISCLOSED on every
affected row (section 7f), not repaired.

## 7h. The total's median: a two-parameter survival map (pre-registered 2026-09-11)

**Written before the code exists, after 7f and 7g failed, and disclosed as such.**
7f moved the level (one parameter) and 7g the dispersion (one parameter); each fixed
one end of the line grid and broke the other. The third candidate gives the shape
two degrees of freedom. **Disclosed, because it bears on 5c rule 1:** the 7g run
printed, for each split's EVAL half, the observed Over rate at each grid line (for
example 0.560, 0.485, 0.385, 0.327 at 7.5 to 10.5 on the anchored split). No
candidate below had been computed on any eval game when this was written, and the
criteria are the 7f/7g criteria unchanged, so the knowledge can steer nothing but
the choice to try a two-parameter shape at all.

**The candidate.** For each game, S(k) = P(total > k) under the served Poisson total
at the model's own lambdas. The candidate replaces it with S'(k) = sigmoid(a *
logit(S(k)) + b) for every integer k, which is a valid survival function whenever
a > 0 (monotone, from about 1 at k = -1 to about 0 in the tail), and prices the Over,
Under and push off the pmf it implies, pmf'(k) = S'(k-1) - S'(k). (a, b) are fitted
on the fit half ALONE by maximum likelihood of the Over outcomes at the fixed grid
(7.5, 8.5, 9.5, 10.5), pooled, with the module's existing `fit_platt` (Newton,
deterministic, refuses separable data). a < 1 compresses the Poisson toward 50/50
at every line; b moves the median. The margin, the moneyline and the runline come
from the served pass and cannot move. A fitted a <= 0 is refused and the split
cannot pass.

**Criteria**, the 7f/7g form, unchanged: anchored plus quantiles 0.6, 0.7, 0.8; every
split refits the pricer on its own fit half and fits (a, b) there; on each eval half
BOTH, at ALL FOUR splits: (1) paired grid log loss, Poisson minus candidate, > 0 at
one-sided t >= 1.645; (2) per-line log loss not worse on the point estimate at >= 3
of 4 lines. Fit >= 100, eval >= 50. Market diagnostics are never criteria.

**Serving.** `SERVE_TOTAL_CALIBRATION`, default False, flipped only from this gate and
only by the owner. The same flip checklist as 7f and 7g: `MODEL_VERSION`, the
tripwire test, `--context`.

### Result (run 2026-09-11, once): INDETERMINATE, and the Poisson total keeps serving

`python betting_model.py --total-calibration`, vintage-gradable games only:

| split | cut | fit / eval | a | b | grid log loss delta | t | lines not worse | pass |
|---|---|---|---|---|---|---|---|---|
| anchored | 2026-08-01 | 305 / 548 | 0.472 | -0.246 | +0.0112 | 0.71 | 2 of 4 | no |
| 0.6 | 2026-08-16 | 507 / 346 | 0.564 | -0.207 | +0.0298 | 1.67 | 4 of 4 | yes |
| 0.7 | 2026-08-22 | 587 / 266 | 0.554 | -0.198 | +0.0377 | 1.73 | 4 of 4 | yes |
| 0.8 | 2026-08-29 | 679 / 174 | 0.551 | -0.201 | +0.0204 | 0.75 | 2 of 4 | no |

Better than the Poisson on the point estimate at every split, resolved at two of
four, so under the rule fixed before the run the grid is INDETERMINATE and nothing
ships. The fitted map is stable across the windows (a 0.47 to 0.56, b -0.20 to
-0.25) and it fixes the tails (Over 10.5 at the 0.7 split: Poisson 0.267, mapped
0.317, observed 0.350). What it cannot do is the middle of the anchored window: it
prices Over 8.5 at 0.448 against 0.485 observed. Two things are visible in the grid
and neither is a criterion: the late-season eval half runs hotter than any fit half
(Over 7.5 observed 0.615 after 2026-08-29), and the misses are where the run
environment moved. A run-environment term is a feature, and features enter only
dark, through their own section.

**Where the three total repairs leave the Over lean.** The lean is a shape defect
(7f). A level shift (7f), a dispersion (7g) and a two-parameter survival map (7h)
each beat the Poisson on the point estimate and none clears its gate at every
split. The lean is DISCLOSED on every affected row and not repaired; the next
admissible attempt is a dark run-environment feature with its own section, or more
eval games under the same 7h criteria (no re-fit of the rule).

### The one re-read, on 2026-09-28 (pre-registered 2026-09-11)

**Written on 2026-09-11, in the discipline of 5a, 5c and 7f to 7h, before the first
nightly that settles a game dated after 2026-09-10.** The date was fixed earlier that day
by the plan (commit bfb000be, 2026-09-11 17:05 ET, section 5.1). This block stands as
written only if it is committed before that nightly (the 2026-09-12 build). If it lands
later, the committer changes the heading date to the commit date and adds one line
before committing: how many nightly builds had by then settled a total dated after
2026-09-10. Either way it is committed alone, docs only, by 2026-09-16 (plan 5.2, W0).
It sits in 7h, directly under the 2026-09-11 result, whose last paragraph ends "(no re-fit
of the rule).", and above the `---` before section 8.

**The licence, and when it was written.** The last paragraph of 7h's result allows this
and nothing wider: "the next admissible attempt is a dark run-environment feature with its
own section, or more eval games under the same 7h criteria (no re-fit of the rule)." That
sentence was written AFTER the first read printed INDETERMINATE, with passes at the 0.6
(t 1.67) and 0.7 (t 1.73) splits. It is not in 7h's pre-registration. Open owner decision
O23 (plan section 6) also postdates that result, and this block carries its DEFAULT: "Yes,
once, registered before 09-27. A pass still needs the owner's flip of
`SERVE_TOTAL_CALIBRATION`." So this second look exists because the first one passed at two
splits of four. That is optional stopping. A PASS here is labelled "PASS at a second, post
hoc look" wherever it is cited.

**Owner answer.** If the owner answers O23 "no" before the read, a dated correction below
cancels the re-read and 7h closes. Any other answer (another date, window, code or rule)
is not a correction to this block. It is a new candidate under "No second re-read", and
its section discloses both 7h reads.

**Disclosed, because 5c rule 1 turns on it.** Everything the 2026-09-11 run printed is
known:
- the table above;
- the observed, Poisson and mapped Over rates at each grid line on each split's eval half;
- that the eval half after 2026-08-29 runs hotter (Over 7.5 observed 0.615).

None of it chose the date, which is the day after the last regular-season game
(2026-09-27, plan 5.1).

For this block and its two reviews, three things were read and nothing was run:
- `betting_model.py` and `leaderboard_vintages.py`, to name functions and constants;
- one config key in the served context file (`run_dispersion_alpha`, null);
- game DATES in the game cache (no runs).

No number relating the map, the Poisson total or any close variant to a game outcome or a
price has been computed since the 2026-09-11 run. Until the read, the calibration ledger
and the lean check (7f) publish the served Poisson total's settled rows and its lean every
night. That is why the date, the window, the code and the invocation are all fixed here.

**What counts as a look, and what one costs.** A look is any computation, by any path,
after the 2026-09-11 run and before the scheduled read, that does either of these:
- (a) applies a survival map of the 7h form to a game dated after 2026-09-10 and relates
  it to that game's runs or to a price. Any (a, b) counts: the lab pair, the served pair in
  `total_calibration_fitted`, or any other.
- (b) calls `total_calibration_gate`, `_total_calibration_split`, `total_level_gate`,
  `_total_level_split`, `total_dispersion_gate` or `_total_dispersion_split` on a game list
  that holds such a game. Test fixtures are not games.

Any look is recorded here with its date and whatever it printed. A look FORFEITS the
re-read: the scheduled read does not run, 7h closes, and no PASS can come from it.
- **Not looks.** The nightly `build_context` (called by `run_monthly.py` at lines 2826
  and 5664, and by `--context`) fits the served pair on the anchored fit half. It uses the
  served coefficients, which are fitted on every cached game, new ones included, but it
  computes no loss on a game dated on or after the cut. The 7b ledger statistic, and any
  nightly artifact that grades the Poisson total without a map, price no map.
- **Date guard.** A guard that refuses the lab switches before 2026-09-28 does not exist
  (to be built if wanted, not required).
- **Known looks.** None known when this block was written.

**The window.** Every 2026 regular-season game dated on or before 2026-09-27 that is final
in the game cache after a top-up on the read day. The top-up runs in the main tree
(`build_game_cache(refresh=True)`) after the last game dated 2026-09-27 is final.
- Postseason games cannot enter, because both cache doors keep game type R only
  (`betting_model.py` lines 3129 and 3310).
- A game dated after 2026-09-27 (a makeup) is outside the window.
- A game with no vintage strictly before it is skipped and counted, never graded on the
  fallback (section 6). The gate counts no skips itself, so the invocation below does.

**The code and configuration, frozen at commit 37e9382d.** This block was written
against that tree:
- `betting_model.py`, blob 873713d0;
- `leaderboard_vintages.py`, blob d69aa9be;
- every other module and the tracked `data/` of that commit.

Nothing written after 37e9382d reaches the read. The read runs from a detached worktree of
37e9382d (`git worktree add --detach`) whose `prospect-tracker/.cache` is a directory
junction to the main tree's `.cache`. The frozen code therefore reads the current game
cache and vintage store and nothing else that moved.

Why 37e9382d and not the first run's bbf00237: two commits since then (997a4b17 and
e328f62a) added the Athletics' park behind an off flag and the schema-5 dark capture, and
the new games are priced on vintages written by that code. The anchored reproduction below
certifies that the two versions price the fit half alike.

Every flag at 37e9382d:

| Constant | Value | Path into this lab |
|---|---|---|
| `SERVE_TOTAL_CALIBRATION` | False | none; the lab applies its own (a, b) |
| `SERVE_RIDGE_FIT` | False | `fit_coefficients` (OLS) |
| `SERVE_RUN_DISPERSION` | False; context `run_dispersion_alpha` null | `_solve_diff_shrink`, `_solve_home_adj` (run_alpha None reads the key): Poisson margins |
| `SERVE_ATH_PARK` | False | `parks_from_vintage`: the Athletics' park stays neutral on every vintage |
| `SERVE_RUNLINE_TIE_SPLIT` | False | none; the lab passes `tie_home` |
| `SERVE_TOTAL_LEVEL`, `SERVE_TOTAL_DISPERSION`, `SERVE_PROB_CALIBRATION` | False | frozen as is |
| `VINTAGE_FIT_WINDOW_GROWS` | False | `_vintage_cut_index` (line 6017): holds the anchored cut |
| `MODEL_VERSION` | `betting_runs_v1` | recorded |
| `SERVE_PRICER` | absent at 37e9382d (to be built, plan 4.2 repair 1) | none |

**Excluded by name: the owner-answered repairs of 2026-09-11.** The Athletics' park is to
serve on the board, and the runline tie split is to be repriced there. Neither enters this
read. The runline never reaches the lab. The park would reach both arms alike, but only
through code written after this block.

**What does not change.** All of it is as at 37e9382d:
- **Criteria:** `TOTAL_CALIBRATION_GATE_CRITERIA`. Both checks must hold at ALL FOUR
  splits, and a mixed grid is INDETERMINATE.
- **Grid:** `TOTAL_LEVEL_LINES` (7.5, 8.5, 9.5, 10.5).
- **Splits:** the anchored cut (`_vintage_cut_index`) plus `DISPERSION_SPLIT_QUANTILES`
  (0.6, 0.7, 0.8) of the vintage-gradable dates. Each split refits the pricer on its own
  fit half.
- **Fit:** (a, b) by `fit_platt` on each fit half's pooled grid outcomes; a <= 0 is
  refused.
- **Floors:** `VINTAGE_MIN_FIT_GAMES` 100 and `VINTAGE_MIN_EVAL_GAMES` 50;
  `VINTAGE_FIT_TARGET_GAMES` 300 and `VINTAGE_FIT_MAX_DATE_SHARE` 0.5 set the anchored cut.
- **Test:** `_paired_delta` at `Z_95_ONE_SIDED` 1.645.
- **Seeds:** none. Newton in `fit_platt` and an analytic t in `_paired_delta`; no
  bootstrap, permutation or seed.

The freeze is by commit, not by name. For the record, the read runs through:
- the gate: `total_calibration_gate`, `_total_calibration_split`, `_vintage_cut_index`;
- the rows and the incumbent: `_total_dispersion_rows`, `expected_runs`, `_total_pmf`,
  `_pmf_over`;
- the map: `fit_total_calibration`, `_total_cal_samples`, `_total_cal_losses`, `fit_platt`,
  `apply_platt`, `_logit`, `_sigmoid`, `_PROB_EPS`, `_paired_delta`;
- gradability: `_vintage_resolver`, `inputs_as_of`, `leaderboard_vintages.as_of`;
- the window: `completed_games`, `build_game_cache`;
- the refit: `fit_coefficients`, `_fit_tie_home`, `_solve_diff_shrink`, `_solve_home_adj`,
  `_p_home_series`, `game_probabilities`, `_score_joint`.

**Readiness, before the read.** This step runs in the worktree and relates nothing to an
outcome or a price:

```
python -c "import betting_model as bm; g = [x for x in bm.completed_games(refresh=False) if '2026-01-01' <= (x.get('date') or '') <= '2026-09-27']; res, _ = bm._vintage_resolver(); old = [x for x in g if (x.get('date') or '') <= '2026-09-10']; new = [x for x in g if (x.get('date') or '') > '2026-09-10']; print(sum(1 for x in old if res(x)), len(new), sum(1 for x in new if res(x)))"
```

- **Old gradable games must be 853** (the first run's 305 + 548). If the count differs, an
  input moved. The read does not run that day. The cause is found and recorded without
  relating anything to an outcome, and the read runs once the count is 853 again, by the
  kill date.
- **New gradable games under 50** (`VINTAGE_MIN_EVAL_GAMES`; the 0.8 split grades only new
  games) mean the frozen code cannot price the new games. The read does not run, and 7h
  closes without a re-read, recorded with the cause.

**The read.** This is the one command, in the worktree:

```
python -c "import json, betting_model as bm; g = [x for x in bm.completed_games(refresh=False) if '2026-01-01' <= (x.get('date') or '') <= '2026-09-27']; r = bm.total_calibration_gate(games=g, log_fn=print); r['n_window'] = len(g); r['n_skipped'] = len(g) - r.get('n_gradable', 0); r['last_window_date'] = max(x.get('date') or '' for x in g); print(json.dumps(r, indent=1, default=str))"
```

It calls the function that `--total-calibration` calls, with the window as its `games`
list, which the function already accepts. The switch itself is not used: it takes no games
argument and prints neither `n_gradable` nor the last date (`betting_model.py` lines 6921
to 6936). The 2026 date filter changes no gradable game, because `as_of` fences every
vintage to its own season.

**When.** Once, on 2026-09-28.
- **A slip.** If the read cannot run that day (box, cache, feed or readiness failure), it
  runs on the first day it can, no later than 2026-10-06, under the same window, code and
  invocation. The result records the late date. A slipped read is still the one read.
- **Kill date.** If it has not run by 2026-10-06, 7h closes without a re-read and the text
  records why. The kill date keeps this read ahead of the 2026-10-07 reads of 5d and 5k,
  which use the same late-season totals.

**What moves by the rule, and is not a re-fit.** At the first run there were 64 gradable
dates (2026-07-06 to 2026-09-10, with 07-13 to 07-15 empty); its 0.6, 0.7 and 0.8 cuts
reproduce from them. The re-read adds up to 17 dates, so it has 80 or 81.
- **Anchored:** the cut stays 2026-08-01 (305 fit games), because
  `VINTAGE_FIT_WINDOW_GROWS` is False and the target index sits below the half cap
  (`_vintage_cut_index`, lines 6025 to 6032). The fit half, the refit pricer and (a, b) are
  the same. The eval half is the first 548 games plus every new game.
- **0.6 and 0.7:** the cuts move to about 2026-08-26 and 2026-09-03 (index int(q x 81) =
  48 and 56). The fit halves grow. Each eval half keeps the part of the first run's eval
  half dated on or after its new cut, plus every new game.
- **0.8:** the cut lands on the first new game date (index 64). Its fit half is the first
  run's 853 games. Its eval half is new games only, disjoint from the first read's 0.8 eval
  half.
- **Fit halves:** no split's fit half holds a game dated after 2026-09-10 (int(0.8 x 81)
  is 64). With the frozen `SERVE_ATH_PARK` False, `parks_short_window` is unread at every
  split, whatever schema a record carries. At writing, the records those games resolve to
  are schema 4 or lower (5d, correction 2026-09-11).

That is what the committed rule does with more dates. Scoring at the old cut dates
instead would be the re-fit.

**The anchored reproduction, and VOID.** The anchored split must reproduce the first run
in four values: cut 2026-08-01, n_fit 305, and a 0.472 and b -0.246 to the three places
the table prints. If any of the four differs, an input or the code moved, and the read is
VOID:
- it is recorded in full;
- it cannot PASS, and `SERVE_TOTAL_CALIBRATION` stays False;
- 7h closes, and there is no re-run.

**What each verdict does.**
- **PASS** (both checks at all four splits, anchored reproduced): recorded as "PASS at a
  second, post hoc look". The lab says `ship`. Nothing serves until the owner flips
  `SERVE_TOTAL_CALIBRATION` ("flipped only from this gate and only by the owner"). The flip
  is the 7f checklist in one commit:
  - the flag set True and 7h updated;
  - `MODEL_VERSION` bumped;
  - the tripwire moved (`test_betting_total_dispersion.py` line 153,
    `assert bm.SERVE_TOTAL_CALIBRATION is False`);
  - `--context` re-run so `total_calibration` is written.

  The flip commit, and any page copy that cites the pass, cite both reads.

  **The served pair.** It is the pair `fit_total_calibration_vintage` fits on the anchored
  fit half for whichever pricer serves at the flip. Under the O14 DEFAULT (if 7e-D fails,
  the graded vintage pricer serves), the served pair follows the pricer that serves after
  7e-D and is refitted at the next `--context`. The re-read's per-split (a, b) are
  evidence, not served constants.

  **Slots.** Under the O15 DEFAULT (publishable markets only), the total stays out of
  slots and badges until its ledger leg (7b) re-opens on its own trailing-200 statistic.
  So a flip moves total prices, not slots.

  **What a pass cannot claim.** The lab grades the map on its own refit pricer at the
  frozen code. The served pair rides the served pricer: the context fit, plus the board's
  live repairs, the Athletics' park included. No registered section grades the served
  (a, b) on the served pricer. 7e-D (to be registered, plan 4.2 repair 1) grades the served
  pricer on moneyline criteria only (`RIDGE_FIT_GATE_CRITERIA`).
- **INDETERMINATE or FAIL:** nothing changes. `SERVE_TOTAL_CALIBRATION` stays False, the
  Poisson total keeps serving, and the Over lean stays DISCLOSED on every affected row
  (owner answer 2026-09-11). 7h closes.
- **A refused split** (a <= 0, or `fit_platt` refuses) or one below the floors cannot
  pass, and the verdict follows the rule.

**No second re-read.**
- **This is the only re-read 7h gets.** After it, the map is not read on 2026 games again,
  whatever this read prints. A later look at it, on 2027 games included, is a new
  candidate. It needs its own section under 5c rule 1, and that section discloses both 7h
  reads.
- **7f and 7g are not re-read** on this date or any other. Their texts allow none.

**Multiplicity, disclosed and not corrected.** The two reads overlap unevenly:
- the anchored split re-grades all 548 of its first eval games;
- the 0.6 and 0.7 splits re-grade the part dated on or after their new cuts;
- the 0.8 split grades new games only.

Two looks, each at one-sided t >= 1.645, with the second taken because the first passed at
two splits, make a looser test than the nominal one-sided 0.05. By how much is not
computed here. It is not corrected, because raising the bar after the first result would
itself change the rule. It is disclosed instead, through the post hoc label above. What
bounds it:
- there are exactly two looks;
- the second date was fixed before any new game was scored under the map;
- a pass needs all four splits.

**Expectation, stated so the result cannot be steered.** There is no new number here; this
is arithmetic on the recorded t and n.
- **New games:** the 7h table graded 548 anchored eval games over the 41 dates 2026-08-01
  to 2026-09-10, 13.4 a game date. It is not the 10.71 a day of the `vintage_sample`
  clock, which counts nightly arrivals (plan 5.1). 17 more dates (2026-09-11 to
  2026-09-27) give about 227 new games, taking the anchored eval half from 548 to about
  775.
- **The anchored split:** its first 548 per-game deltas are fixed (see above). At the same
  per-game spread, the anchored t goes from 0.71 to about 0.84 if the new games repeat the
  old mean improvement. Reaching 1.645 needs the new games to carry about 4.2 times the old
  per-game improvement.
- **The 0.8 split:** it grades about 227 new games alone, with a map fitted on 853. At the
  first run it read t 0.75 on 174 games.
- **The verdict:** a PASS at all four splits is unlikely. INDETERMINATE or FAIL is the
  expected verdict.

**Where it sits.**
- **No Holm family.** The plan names four betting families (the 7e coefficient vector,
  run environment, z_prev, the N4 grid), and 7h is in none of them.
- **No dark clock is touched.** The read uses no weather and no dark column. Its rows are
  priced on the five core inputs the vintage resolver returns, so no dark clock is touched
  (5c to 5i, and 5j and 5k once they are registered).
- **Not a fourth repair** (plan X1): no parameter, line, split or criterion is added.
- **7i is not stacked on 7h** (plan N2). If both pass, `SERVE_TOTAL_CALIBRATION` and 7i's
  flag (`SERVE_SCORE_KERNEL`, to be built) never price the total together, and which one
  serves is the owner's call.
- **Ordering against the run-environment family.** Three texts are owed:
  - the 5k registration, due by 2026-09-15 (plan 5.1);
  - the amendments that put 5d-C and 5h in one Holm family with 5k (plan 4.2 N3 and 5.1).

  If all three are not committed before the read, the result block withholds the per-line
  observed, Poisson and mapped Over rates until those reads land, and records the rest.
  Those rates describe the late-season residual that 5k, 5d-C and 5h target. Between this
  read and theirs, no amendment to 5d-C, 5h or 5k is written unless it names this printout.

**The result block.** It is appended directly under this block as `### Result (run
2026-09-28, once): VERDICT, and ...`, with the actual run date if the read slipped. The
2026-09-11 result above is left unedited (the 11a V1 precedent). It carries:
- the look record: none, or each look and its consequence;
- the readiness counts: old gradable, new in window, new gradable;
- the invocation, the worktree commit 37e9382d, the two blob hashes, the main tree's HEAD,
  and the python and numpy versions;
- `MODEL_VERSION` and the flag values as run;
- `n_window`, `n_gradable`, `n_skipped` and the last date in the window;
- per split, the columns the first run printed (cut, fit / eval, a, b, grid log loss
  delta, t, lines not worse, pass), plus the per-line observed, Poisson and mapped Over
  rates unless they are withheld under "Where it sits";
- the anchored reproduction: cut, n_fit, a and b against 2026-08-01, 305, 0.472 and
  -0.246.

Nothing in this block was measured against a game result. It adds no new number: the
expectation is arithmetic on the recorded t and n.

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

- The run distribution was WRONG, not soft, and the caveat above understated it
  by about 5x. Measured 2026-08-09 on all 1,761 cached completed games: team
  runs var/mean 2.3355, margin variance 2.3680x the Skellam-implied,
  P(|margin| >= 5) 0.2981 observed against 0.1389 modelled. The subsection below
  is the correction and the gate it had to pass.
- The SERVED prices are still built from season-to-date team inputs, and always
  will be: a live pick has to use the newest numbers. The vintage store fixes
  the BACKTEST, which is what validation needs. Until the vintage sample is
  large enough, every published number about model skill is contaminated and
  labelled so.
- Vintage features are stale by a MEASURED amount, because the three leaderboard
  exports run on the monthly pipeline path only: game-weighted median 3 days,
  p90 10.2, max 13 over 419 graded game dates, worst across the 2026-07-16 to
  2026-07-29 gap. Honest, but a quality ceiling on the vintage mode, and the
  vintage-mode model should be expected to look WORSE than the contaminated one
  partly for this reason. `coverage()["vintage_age_days"]` publishes the
  distribution, game weighted. Section 5 has the fix.
- The honest mode grades 211 games and LOSES to the home-field baseline (paired
  Brier -0.001224, t = -0.332, accuracy 52.6% against a 54.5% home-win base
  rate). That is a real result on a real sample, it is not significant in either
  direction, and it is 211 of the 600 the gate asks for. It is the single most
  important fact about this model right now. Section 5a.
- The runline and the total are priced off a margin model the site has
  measured as mis-shaped. The dispersion correction in 11a did not clear its
  gate - the verdict is INDETERMINATE, it passes at two of the three
  pre-declared split points and misses at the third. **Corrected 2026-09-11:**
  this bullet used to say both markets were therefore excluded from
  `pick_of_the_day`, `longshot_of_the_day`, the public record and the paper bet
  ledger. The ledger exclusion was never implemented, on purpose (the 2026-08-14
  amendment in `betting_model.market_is_publishable`: the shadow ledger is the
  evidence that could lift the exclusion), and the slot and record exclusion
  ended with the any-market owner decision of 2026-09-05 (section 7d,
  `SLOT_MARKET_POLICY = "any"`). Both markets are eligible for both slots and
  the record; the caveat rides the published row as disclosure, and the
  published headline on 2026-09-10 was a runline. `SLOT_MARKET_POLICY =
  "dispersion_gated"` restores the exclusion this bullet described.
- The runline gives the model's whole tie-after-nine mass to both +1.5 sides,
  while the moneyline splits the same mass by the measured extra-innings home
  rate (L14-01). Every served +1.5 side runs high and every -1.5 side low by the
  tie mass times the other side's two-run-plus share of extra-inning games. The
  measured split is published and not served; section 4 has the numbers and the
  gate it waits on, and a runline slot says so on the row.
  **2026-09-11, later:** SERVED. The owner flipped `SERVE_RUNLINE_TIE_SPLIT` on
  ahead of that gate (section 4), under the `betting_runs_v2` bump. The runline
  is still priced off the mis-shaped margin model of the bullet above; the split
  fixes the tie atom's allocation, not the shape.
- Hitter prop lines assume a projected batting order against a right-hander and
  a PA-by-slot table (4.65 at leadoff down to 3.85 at the nine hole). A posted
  lineup card beats this every time.
- No weather, no umpire, no travel, no injury news beyond what the leaderboards
  already absorb.
  **2026-09-11:** still true of every served price. Venue weather
  climatology accrues dark (5d), and a pregame forecast capture is authored
  and ships OFF behind an owner decision (5h); neither reaches a price until
  its own pre-registered gate clears. **Later the same day** the owner armed
  the forecast capture and approved its Previous Runs backfill (5h, "Armed");
  both accrue dark and still reach no price.
- 29 of 30 parks have a Savant runs index in `fa_meta.json`; the missing one
  resolves neutral at lookup rather than being invented. **Amended 2026-09-11:**
  the missing one is the Athletics' Sutter Health Park, which Savant publishes
  at a 2-season window (runs 121 on 34,287 PA) and whose game carried the
  highest posted total (10.0) on the 2026-09-11 board. Neutral was the wrong
  default for it. The shrunk measured factor (1.1919) is built and NOT served:
  `SERVE_ATH_PARK` is False, and flipping it adds an over to the 2026-09-11
  value set rather than removing one. Section 5i-A. **2026-09-11, later:**
  SERVED. The owner flipped `SERVE_ATH_PARK` on with a refit (5i-A). The A's
  home games now price at Sutter Health Park's shrunk factor, which adds to the
  over tilt rather than reducing it, and the Rays' home games at their
  two-season Tropicana row shrunk by its own sample; /dfs/ reads the same
  table. Neutral-site games are still priced at the home club's park (the six
  A's home games at Las Vegas Ballpark, 5i-A).
- The park term carries no batter side. The by-hand split of Savant's runs
  index is measured near-pure noise (3-season reliability 0.0191) and its HR
  split weak (0.3293); both are captured dark with their gates in 5i-B and 5i-C.

### 11a. The run distribution is wrong by a factor the caveat understated 5x

Poisson asserts var = mean. Measured on all 1,766 completed games in
`.cache/betting/completed_games.json`, over the 3,532 scoring-side rows the
model actually prices:

| Quantity | Poisson says | The games say | Ratio |
|---|---|---|---|
| Team runs, var / mean | 1.000 | **2.3385** (mean 4.4853, var 10.4889) | 2.34x |
| Margin variance | 8.9714 (Skellam-implied) | **21.3057** | 2.37x |
| P(\|margin\| >= 5) | 0.1390 | **0.2990** | 2.15x |
| P(\|margin\| >= 2), the runline | 0.6171 | **0.7276** | 1.18x |

The old caveat said runline and total probabilities "sit too close to the
middle". They do, but a caveat about softness is the wrong category for an
error this size: the model is short more than half the mass that decides every
runline.

**It is not lambda heterogeneity, and that was checked first.** Under a Poisson
mixture var(Y) = E[lam] + var(lam), so a model whose per-game means vary enough
would produce excess variance without the distribution being wrong. The model's
own lambdas have sd 0.6128 across the 3,532 rows, which is var 0.3755 of the
6.0036 of excess: **6.25%**. The other 93.75% is within-game clumping, a rally
scores runs in a correlated burst, and no feature work touches it.

**The estimator: one-parameter NB2 per scoring side, pure Python.** var = lam +
alpha*lam^2 with r = 1/alpha. It needs no library and no gamma function, only
the exact ratio recurrence p(k)/p(k-1) = (k-1+r)/k * lam/(r+lam), so the
"no scipy in the serving path" invariant at `betting_model.py:39-41` is not
spent. `r=None` recovers Poisson bit for bit, which is what makes the gate below
a true A/B on one flag. Conditional MLE given the model's own per-row lambda:
**alpha = 0.28425** (r = 3.5181), worth **+725.71 nats** of held-in
log-likelihood for one parameter.

Two NB2s with different means do not sum to an NB2, so the total loses the
closed form it had under Poisson. `margin_distribution` and `total_distribution`
are now thin wrappers over one `_score_joint` pass, which prices both markets
off the same convolution and cannot let them disagree about one game.

**The NB total carries its own tail, and the Poisson one deliberately does
not.** The first version of the joint pass dropped every cell with
i + j > 40. `total_side_probabilities` prices a half-point Under as
`1 - p_over`, so the whole discarded tail was handed to the Under: 4.98e-06 at
lam 4.5/4.5, 3.02e-05 at 7.5/1.5, 2.44e-04 at 9.5/1.5 and **1.55e-02 at the
9.5/9.5 lambda ceiling**, a quarter of the 0.06 provisional edge floor. The NB
branch now returns the FULL convolution support instead, so nothing is dropped,
nothing is top-coded and every cell still means P(total == k); the residual is
the loop's own 1e-12 prune. Top-coding the last cell into P(total >= 40) was
tried and withdrawn: it also sums to 1, but it changes what that cell means and
lands 4.98e-06 off the exact closed form the NB total is checked against.

The Poisson branch keeps its truncated closed form untouched, leak and all: it
is short 8.09e-06 at the lam ceiling of 19.0 total and 6.11e-15 at the
league-typical 9.0, both under the 5th decimal every published probability is
rounded to. Repairing a Poisson error worth less than one ulp of a published
digit would cost the invariant that `r=None` reproduces the shipped Skellam bit
for bit, and that invariant is the only thing making the gate below a true A/B
on one flag.

**All three fitted parameters are re-solved together, in the order alpha,
shrink, adj, with one refinement pass.** `diff_shrink` was fitted to fix
moneyline overconfidence UNDER POISSON, and widening the run distribution is
itself a de-confidencing device. Holding it fixed and switching dispersion on
would compare a TUNED incumbent against an UNTUNED challenger, which is rigged
toward Poisson, and a pass under those conditions would mean nothing.

#### The pre-registered gate

**Written into this file before the gate was run**, and carried verbatim in
`betting_model.DISPERSION_GATE_CRITERIA` so the doc and the code cannot drift.

Split `.cache/betting/completed_games.json` by DATE at the same 70% point
`backtest()` already uses. Fit {coefficients, alpha, diff_shrink,
home_field_runs_adj} on the fit half. On the HELD-OUT half **all four must
hold**:

| Market | Loss | Test |
|---|---|---|
| home win | paired Brier | non-inferiority: one-sided 95% lower bound on delta >= -0.001 |
| margin >= 2 | paired log loss | delta > 0 at t >= 1.645 |
| total over 9.0 | paired log loss | delta > 0 at t >= 1.645 |
| runs, both sides | out-of-sample log-likelihood per row | NB > Poisson |

delta is incumbent loss minus challenger loss on every row, so positive always
means NB2 is better.

**Row 2 of that table is the V1 text and it is left unedited.** "margin >= 2"
names no side, that gap is load-bearing, and the amendment that closes it is
recorded below rather than written back over the sentence it amends. V1 lives in
`betting_model.DISPERSION_GATE_CRITERIA_V1`, the amended text in
`DISPERSION_GATE_CRITERIA`, and both are pinned by
`test_betting_dispersion.py`.

**Moneyline is non-inferiority on purpose.** `diff_shrink` already absorbs that
market's calibration, so crediting NB for beating it there would be crediting it
for work the incumbent had already done. The two markets the distribution's
SHAPE decides, the runline and the total, carry the superiority tests.

The gate runs on the CONTAMINATED forward split, and that is deliberate. Both
arms see identical features and an identical fit window, so the contamination
cannot favour one distribution over the other; the question here is shape, not
skill. The vintage sample (221 graded games) is far too small to answer it.

**If it passes**, alpha ships in `betting_model_context.json` and the caveat on
the runline and total rows is replaced with one that names both honest numbers,
the fix AND the overcorrection.

**If it fails, or is indeterminate**, the runline and the total are excluded
from both published slots, from the public record and from the paper bet ledger
until a correction passes. They stay ON the board with the caveat and still
enter the calibration ledger, because that ledger is a scoring rule on a census
of every board row, not a bet: nothing is staked, nothing is published as a
pick, and dropping the two worst-calibrated markets out of a calibration record
is exactly how a model stops being able to see its own error.

#### Reading 1, SUPERSEDED: the home-side-only run

Run 2026-08-09 on the split it pre-registered: fit 1,223 games through
2026-06-26, held out 543 from 2026-06-27. Both arms re-solved every free
parameter on the fit half.

| # | Criterion | Test | Value | Passes |
|---|---|---|---|---|
| 1 | moneyline (home win), paired Brier | lb95 >= -0.001 | **-0.000413** (delta -0.00012, sd 0.004147, t -0.675) | **yes** |
| 2 | runline (home margin >= 2), paired log loss | delta > 0, t >= 1.645 | **-0.003075**, t **-0.717** | **NO** |
| 3 | total (over 9.0), paired log loss | delta > 0, t >= 1.645 | **+0.011031**, t **+2.592** | **yes** |
| 4 | runs both sides, out-of-sample log-likelihood per row | NB > Poisson | **+0.223203** nats/row | **yes** |

That reading was reported as a FAIL. It is kept here because it is what the
first run said, and because criterion 2's number in it is real. It is no longer
the verdict, for the reason immediately below.

#### The amendment: criterion 2 named no side, and the side decides the verdict

V1 of the pre-registration said "margin >= 2" and did not say WHOSE margin. That
is an under-specification and it is load-bearing. The board publishes four
runline prices per game and they are TWO binary events, because
p_home_plus_1_5 = 1 - p_away_minus_1_5 and log loss is invariant under
complementation. The two distinct events are the two TAILS of one margin
distribution: home margin >= +2, and home margin <= -2. The first run scored the
home tail alone.

The amended criterion 2 scores **both sides**, as the per-game sum of the two
log losses. The argument is about the estimand, not about the number it returns,
and it is carried in full in `betting_model.RUNLINE_SIDE_AMENDMENT`:

1. The criterion decides whether a distribution SHAPE may be served to the
   runline market, and the runline market is both sides. An estimand should be
   the loss on what is published.
2. alpha is ONE symmetric widening parameter. It moves both tails at once and
   cannot move only the home one. Reading its effect off a single tail measures
   half the effect and discards half the data.
3. The defect was stated symmetrically and in absolute margin everywhere it was
   measured. A test for a symmetric defect that reads one tail is not the test
   the defect asked for.
4. Home-referencing is a naming convention in this module, not a measurement
   decision, so it is not a neutral default.

**And the choice flips the gate, which is stated up front rather than
discovered.** The home tail fails, the away tail and the both-sides sum pass.
Picking the specification after seeing that is exactly the failure mode, so the
verdict was moved off any single fit: `DISPERSION_SPLIT_QUANTILES = (0.6, 0.7,
0.8)` was fixed in code, and the ship rule declared **before the sweep ran** is
that the amended criterion must hold at EVERY quantile or the gate is
INDETERMINATE and dispersion stays off. A verdict that moves with the split
point is a verdict about the split point.

#### Result: the sweep, and the verdict is INDETERMINATE

`dispersion_gate_sensitivity`, run 2026-08-09 on the 1,775-game completed cache.
Three splits, three side readings, both arms refitted at every split.
`run_dispersion.sensitivity` in `data/betting_model_eval.json` carries the grid.

| split | date | n_fit | n_eval | home delta / t | away delta / t | both delta / t | amended verdict |
|---|---|---|---|---|---|---|---|
| 0.6 | 2026-06-14 | 1054 | 721 | -0.003628 / -0.972 | +0.015004 / +3.860 | **+0.011376 / +3.069** | PASS |
| 0.7 | 2026-06-27 | 1223 | 552 | -0.003280 / -0.769 | +0.015018 / +3.367 | **+0.011738 / +2.799** | PASS |
| 0.8 | 2026-07-11 | 1413 | 362 | -0.004701 / -0.886 | +0.011155 / +2.034 | **+0.006454 / +1.224** | FAIL |

Criteria 1, 3 and 4 pass at all three splits. So the amended criterion 2 clears
the t >= 1.645 bar at 0.6 and 0.7 and misses it at 0.8, where the delta is still
POSITIVE and it is the standard error that runs out: n_eval falls from 721 to
362. Robustness by side: **home fails at all three, away passes at all three,
both-sides is INDETERMINATE.**

**`SERVE_RUN_DISPERSION` stays False.** Alpha does not reach a price and the
module keeps the Poisson it shipped with.

Two things this supersedes, and both pointed the other way:

- The home-only reading above, at -0.003075 / t -0.717, is not the estimand.
- **The pre-registered single split now PASSES all four criteria** under the
  amended criterion 2: runline +0.011738 at t +2.799, total +0.010709 at
  t +2.545, runs +0.2190 nats per row, moneyline lb95 -0.000383. If the verdict
  were taken from that one split the flag would be True. It is not taken from
  one split, on purpose, and that rule was fixed before the sweep ran. This is
  why `run_dispersion.passed` (True, one split) and `run_dispersion.verdict`
  (`indeterminate`, the sweep) are allowed to disagree in the artifact, with
  `verdict` governing and `served` following it.

**Why the home side loses, and it is mechanical rather than a sample-size
accident.** NB2 fixes the tail and OVERCORRECTS THE MIDDLE. On the full
1,775-game cache priced from the served context:

| | Poisson | NB2 | Observed |
|---|---|---|---|
| P(\|margin\| >= 5) | 0.1390 | **0.2897** | 0.2986 |
| P(\|margin\| == 1) | 0.2503 | **0.1917** | 0.2721 |
| P(\|margin\| >= 2) | 0.6171 | **0.7077** | 0.7279 |

The tail is essentially repaired: 0.1390 to 0.2897 against 0.2986 observed. The
one-run band goes the WRONG WAY: 0.2503 to 0.1917 against 0.2721 observed, so
NB2 is further from the truth on the middle than Poisson was. Real baseball
concentrates at one run because a tied home ninth ends the instant the run
scores, so the HOME team's two-run-plus tail is clipped in a way the away team's
is not - the held-out half bears that out, home -1.5 lands 0.3442 of the time
against away -1.5 at 0.3768. No product of two INDEPENDENT count distributions
can represent that asymmetry, and the runline is priced exactly on the band NB2
damages. That is the whole reason criterion 2 is the wobbly one.

**A result worth keeping for whoever tries next.** Criterion 3 passed at
t = +2.545 and criterion 4 by +0.2190 nats per row: dispersion is real and NB2
captures it for the TOTAL, where the two sides add and the walk-off structure
does not bite. A correction scoped to the total, or a bivariate model with a
one-run atom, is where this goes. A wider symmetric margin distribution is not.

**`diff_shrink` moved from 0.70 to 1.08 in the NB arm, and that vindicates
re-solving.** Under Poisson the moneyline needed shrinking toward the middle;
under NB2 the distribution is already wide enough that the fit wants to EXPAND
the differential past 1.0. Had the gate held `diff_shrink` at its Poisson value
it would have double-shrunk the challenger and failed it for the wrong reason.

#### What it would have done to the live board

Measured on the 2026-08-09 board (5 games, 10 runline sides, 10 total sides),
old = served Poisson, new = the counterfactual NB2 set:

| Game | Side | p old | p new | delta | edge old | edge new |
|---|---|---|---|---|---|---|
| BAL at TEX | BAL +1.5 | 0.64857 | 0.59922 | **-0.04935** | +0.02075 | -0.02860 |
| DET at SFG | SFG +1.5 | 0.70103 | 0.65256 | **-0.04847** | +0.11910 | +0.07063 |
| LAD at ARI | ARI +1.5 | 0.62213 | 0.57056 | **-0.05157** | +0.07975 | +0.02818 |
| TBR at SEA | SEA +1.5 | 0.70963 | 0.66240 | **-0.04723** | +0.07195 | +0.02472 |
| HOU at SDP | HOU +1.5 | 0.68540 | 0.63753 | **-0.04787** | +0.05585 | +0.00798 |

Every favourite side moves by the identical amount with the opposite sign, so
the five rows above are the whole board. Totals move the same direction on the
Over, between -0.026 and -0.080, largest on LAD at ARI Over 9.0 (0.60180 to
0.52230, edge +0.11046 to +0.03096).

**It kills the live pick.** `pick_of_the_day` was SEA +1.5 at edge 0.07195
against the 0.06 provisional floor; under the correction that edge is 0.02472
and the row does not clear. Four of the five +1.5 dog sides fall below the
floor. One does not: SFG +1.5 lands at 0.07063 and would BECOME the pick. So
the honest description is that the correction would have replaced the pick, not
emptied the slot, and it would have removed 4 of 5 runline edges on this board.

That the entire published edge on this market is smaller than the size of a
known distributional error is the finding, and it does not depend on the gate.
It is the strongest available evidence that the current runline edges are
manufactured by the model's own shape rather than found in the market.

#### What follows from an indeterminate verdict

Exactly what follows from a failure, and that is the point of declaring the ship
rule in advance: indeterminate does not ship.

Per the pre-registration: **the runline and the total are excluded from
`pick_of_the_day`, from `longshot_of_the_day`, from the public record and from
the paper bet ledger until a correction passes.** They stay ON the board with
the caveat, and they still enter the calibration ledger, which is a scoring rule
on a census of every board row rather than a bet - nothing is staked and nothing
is published as a pick, and removing the two worst-calibrated markets from a
calibration record is how a model stops being able to see its own error.

The caveat text on those rows is replaced. The old one said the probabilities
"sit too close to the middle" and treat the edge as "the softest of the three
markets", which understates a 2.15x tail error by about 5x and names no number.
The replacement names the size, names the market, and says the row is not
bettable here.

**Correction (2026-09-11), recorded rather than written over the paragraph
above.** The replacement was never made. `betting_export.POISSON_CAVEAT` still
carries the "sit too close to the middle" and "softest of the three markets"
text, and it is the caveat on every published runline and total slot today. The
size of the dispersion error reaches the pick card only through the client's
dispersion line (`dispersionLine` in `assets/betting.js`, which reads
`run_dispersion` off the eval artifact and names alpha and the verdict, not the
2.15x tail). Replacing the caveat text is open work for the dispersion lane. The
one runline error the caveat never covered, the tie atom, now has its own
row-level sentence (section 4, `tie_atom_caveat`).

**2026-09-11, `betting_runs_v2`: the gate re-run on its own schedule reads FAIL.**
Serving the runline split of the tie atom (`SERVE_RUNLINE_TIE_SPLIT`, owner
decision 4) changes what criterion 2 grades, because both arms now price the
runline on their fit window's own split (`_lab_runline_split`). Measured on the
2,200 cached games under the amended both-sides criterion, t at split quantiles
0.6 / 0.7 / 0.8:

| Pricer | Runline | Total | Verdict |
|---|---|---|---|
| v1 | 3.196 / 2.086 / 2.221 | 2.271 / 1.334 / 0.049 | INDETERMINATE |
| tie split alone | 0.482 / -0.127 / 0.540 | | FAIL |
| parks alone | | 2.614 / 1.841 / 0.517 | INDETERMINATE |
| two-way starters alone | | 2.309 / 1.381 / 0.080 | INDETERMINATE |
| v2 (all three) | 0.473 / -0.116 / 0.540 | 2.645 / 1.876 / 0.539 | FAIL |

Dispersion did not ship and does not ship; `SERVE_RUN_DISPERSION` stays False. The
total leg's gain at 0.7 (1.334 to 1.876) comes from the park repair, a
pricer-input change. This is the registered gate re-run on its own nightly
schedule, not a look at the B-TOTAL lane.

### 11b. B5: Platt response-scale calibration, the pre-registered gate (2026-08-16)

**This section is written before the calibration lab exists in code and before
any number has been looked at**, in the discipline of 7b and 11a: the rule goes
on the record first, so neither the threshold nor the estimand can be chosen
after the data has been seen.

**The candidate.** p' = sigmoid(a * logit(p) + b), two parameters, fitted by
maximum likelihood. Platt scaling is monotone in p, so it is order-preserving:
it cannot change which side the model prefers on any game, only how sure the
model claims to be. That bounds what it can fix.

**The pre-registered expectation, stated before the first fit:** Platt repairs
RESPONSE SCALE, overconfidence and inversion at the extremes. It cannot
manufacture discrimination, and it is NOT expected to open the skill gate:
gate 2 reads a paired Brier against a constant baseline, and a model whose
ordering carries no information converges TOWARD that baseline under a scale
repair rather than past it. Converging toward the baseline is a finding about
the model, not a failure of the method. One more reason to expect a null is
already in the module: `diff_shrink` is fitted on the fit half by minimizing
log loss, so most of the response scale is absorbed before Platt ever sees a
probability, and a fitted (a, b) near (1, 0) is the honest likely outcome.

**Arm 1, the vintage arm.** On the vintage-gradable sample (games with a
vintage strictly before them), split the gradable DATES at quantiles 0.6, 0.7
and 0.8, the same fixed grid the dispersion gate uses and for the same reason:
a verdict that moves with the split point is a verdict about the split point.
At each split:

- fit {coefficients, tie rate, diff_shrink, home_field_runs_adj} on the fit
  half, on vintage features, exactly as the honest mode's `_grade` does;
- fit (a, b) by MLE on the fit half's own per-game (p_home, home win) pairs.
  Nothing from the eval half reaches the fit, and nothing later than the split
  date reaches either half's features;
- on the HELD-OUT half, BOTH must hold:
  1. paired per-game Brier delta, identity minus Platt, > 0 at one-sided
     t >= 1.645;
  2. paired log loss delta not worse on the point estimate (>= 0).

**ALL THREE quantiles or nothing.** Floors: the fit half must carry at least
`VINTAGE_MIN_FIT_GAMES` (100) games and the eval half at least
`VINTAGE_MIN_EVAL_GAMES` (50); a split that cannot meet its floors cannot pass,
so an arm with an unrunnable split cannot pass either.

**Arm 2, the ledger arm.** The calibration ledger's settled CANONICAL-SIDE
moneyline games, one row per game
(`tools/betting_calibration.canonical_settled_games`), which carry the SERVED
model probability and the outcome. This arm ACTIVATES at n >= 100 settled
canonical moneyline games. On 2026-08-16 the ledger holds 49, so **this arm
cannot count yet, in either direction**, and that is being written down before
any number is computed on it. When it activates: rows in chronological settled
order, the same three split quantiles, (a, b) fitted on the fit segment, the
same two criteria on the held-out segment, all three quantiles or nothing. One
honesty note rides with it: the ledger's model probabilities are priced from
season-to-date inputs, which favours the model, but a scale repair measured on
the served probabilities is a repair of exactly the scale the serve seam would
apply to, so this arm is the one closest to the deployed question.

**The ship rule.** `SERVE_PROB_CALIBRATION` flips to True only when BOTH arms
pass. Today that is impossible by construction, whatever arm 1 returns,
because arm 2 cannot count before ~100 settled canonical moneyline games
exist. A green arm 1 alone is recorded, not served. The flag, the
`prob_calibration` block in the eval artifact, and the tripwire in
`test_betting_platt.py` move in ONE commit or not at all, the
`SERVE_RUN_DISPERSION` three-move-together pattern.

**Serving scope: moneyline only.** The runline and the total stay behind the
dispersion gate (11a) and the market gate (7b) whatever this section returns;
a response-scale repair on p_home says nothing about a mis-shaped margin
distribution.

**What the artifacts carry.** `betting_model_eval.json` gains a
`prob_calibration` block: the per-quantile grid (n_fit, n_eval, fitted a and
b, both criteria's paired deltas and t), both arms' status, the verdict, and
`served` / `served_ab` beside it. `betting_model_context.json` carries
`prob_calibration` (the served (a, b), null while the flag is off) and
`prob_calibration_fitted` (the full-sample measurement, published whether or
not it is served, the same convention `run_dispersion_alpha_fitted` set).

#### Result (run 2026-08-16, after the pre-registration above): FAIL, and the expectation is confirmed

The vintage arm, on the 518-gradable sample:

| split | date | n_fit | n_eval | fitted (a, b) | Brier delta / t | log loss delta | verdict |
|---|---|---|---|---|---|---|---|
| 0.6 | 2026-08-01 | 305 | 213 | (1.137, -0.010) | -0.000505 / -1.418 | -0.001024 | FAIL |
| 0.7 | 2026-08-05 | 358 | 160 | (1.048, -0.005) | -0.000115 / -0.862 | -0.000232 | FAIL |
| 0.8 | 2026-08-09 | 414 | 104 | (1.005, -0.001) | -0.000004 / -0.292 | -0.000008 | FAIL |

**Fail at all three splits, on both criteria.** Platt is not merely short of
the t bar; it is slightly WORSE than identity out of sample at every split.
The ledger arm holds 49 of its 100-game floor and cannot count, so the ship
rule was unsatisfiable today whatever this arm returned; it returned a fail
anyway. `SERVE_PROB_CALIBRATION` stays False and identity is served.

The pre-registered expectation is what the table shows. The fitted maps
converge to identity as the fit window grows (a: 1.137 to 1.048 to 1.005),
because `diff_shrink` is fitted on each fit half by minimizing log loss and
absorbs the response scale before Platt sees a probability; the residual two
parameters fit noise and pay for it held out. The moneyline's problem is
DISCRIMINATION, not scale, and no monotone recalibration touches
discrimination. Re-run `backtest()` and read both arms when the ledger
reaches 100 settled canonical moneyline games; do not fit anything by hand
before then.

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
| `vintage.n_graded` stuck at 0 while vintages exist | every completed game predates the earliest vintage cutoff | gradability starts the day AFTER the earliest cutoff. `--coverage` reports `earliest_gradable_game_date`. If that date is later than the boards in git, `python tools/backfill_vintages.py --dry-run` says how far back the archive can be pushed |
| `n_graded` is far below `n_gradable` | the fit window took the difference | expected. The split is anchored at `VINTAGE_FIT_TARGET_GAMES` (300) but capped at half the DATES, so on a short archive the fit takes half the calendar: 419 gradable split at 2026-07-25 into 208 fit and 211 eval |
| `--coverage` shows a run of `missing_dates` | the daily snapshot step stopped firing | fix the step first. Then `python tools/backfill_vintages.py --dry-run`: a gap is recoverable exactly as far as the boards were COMMITTED over it, which on the monthly export path is not far. It never overwrites, so running it is safe |
| `n_vintages_backfilled` is climbing and `n_vintages_live` is not | the nightly snapshot is dead and the reconstruction is masking it | the two counts are separate for this reason. A backfill is not a substitute for the clock |
| `min_edge` still null with a big vintage sample | gate 2 or gate 3 | `python betting_model.py --gate` names the closed one |
| Vintage store empty after a box rebuild | `.cache/` was not restored | the clock restarts. Back up `.cache/leaderboard_vintages/` with `prospects.db` |

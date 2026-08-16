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
- The runline and the total are NOT bettable here. The dispersion correction in
  11a did not clear its gate - the verdict is INDETERMINATE, it passes at two of
  the three pre-declared split points and misses at the third - so both markets
  are excluded from `pick_of_the_day`, `longshot_of_the_day`, the public record
  and the paper bet ledger. They stay on the board, carry the caveat, and still
  enter the calibration ledger.
- Hitter prop lines assume a projected batting order against a right-hander and
  a PA-by-slot table (4.65 at leadoff down to 3.85 at the nine hole). A posted
  lineup card beats this every time.
- No weather, no umpire, no travel, no injury news beyond what the leaderboards
  already absorb.
- 29 of 30 parks have a Savant runs index in `fa_meta.json`; the missing one
  resolves neutral at lookup rather than being invented.

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

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

### Correction (2026-09-18): the snapshot dates the starter's RATINGS, not his identity

The paragraph above, `leaderboard_vintages.PARK_SOURCE`'s preamble and the
served sentence `betting_export.MODE_MEANING["vintage"]` all read as though the
whole starter came out of the dated snapshot. He does not, and the difference is
worth one sentence because the vintage mode is the only thing on this platform
allowed to validate the game model.

What the snapshot dates is `starter_leaderboards.json`: that pitcher's SEM+ and
his innings per start, as of a cutoff strictly before the game. WHICH pitcher is
read off the completed-game row (`completed_games.home_sp` / `away_sp`), which
carries the FINAL feed's `probablePitchers`. The served board prices the
probable listed at the 03:10 ET build instead, so the graded pricer holds a
starter the board did not always have. Measured (`betting_model._starter_basis`,
R4 count, 2026-09-11): the final feed's probable equals the first pitcher
actually used on 4,385 of 4,392 sides, and the two doors into that stored field
agree on 4,576 sides across 2,288 games with 0 differences (2026-09-17).

**This is a difference in INFORMATION and not an outcome leak**, because who
starts is fixed before first pitch. The distinction has to be stated rather than
implied: a reader who is told the backtest used the final feed must be able to
tell which of the two it is.

Three copies of the old wording were repaired on 2026-09-18, and no number
moved:

- `betting_export.MODE_MEANING["vintage"]`, which is COPIED into
  `data/betting.json` and rendered on /betting/, listed "the listed probable"
  among the things that come out of the snapshot. It now names the SEM+ ratings
  as the dated half, the completed-game row as the source of the identity, and
  carries the information-not-leak sentence.

  **That constant has two doors, and the served one was the stale one.** The
  page renders `model.validation.mode_meaning.vintage` out of the payload, not
  the Python constant, and the payload is written by the nightly export. So a
  repair to the constant alone would have reached a reader only at the next
  03:10 ET build, and until then the tab would have carried the old sentence
  directly above the new panel that contradicts it, which is the class of
  defect this whole step exists to close. `assets/betting.js` therefore carries
  the current text as well, in `MODE_MEANING`, and prefers it over the payload's
  copy; `test_betting_policy_copy` pins the two byte for byte and renders the
  tab against a payload holding the OLD sentence to prove which door wins. A
  payload with no `mode_meaning` at all still renders nothing there, as before.
  As of 2026-09-18 the two tracked artifacts `data/betting.json` and
  `data/betting_preview.json` still hold the old sentence; the page no longer
  shows it, and the next export rewrites them.
- The `PARK_SOURCE` preamble in `leaderboard_vintages.py` said the first three
  of the four inputs "were vintage-dated by this module from day one". It now
  says which half of the starter that covers.
- `MODEL_REGISTRY.md`'s `betting_game_prob` row calls the model starter "the
  listed probable" with no eval basis. That file belongs to another lane; the
  replacement text is handed over rather than applied here.

### Owner decision (2026-09-18): the validation tab renders the starter basis

The block `starter_basis` shipped in `data/betting_model_eval.json` on
2026-09-17 and was published but not rendered; the open question that step left
was whether the validation tab should carry it beside the vintage Brier and the
skill t. The answer is yes. `assets/betting.js` grows one panel, "What the
graded sample was priced on", directly under the validation panel and above the
calibration panel, with three blocks:

- **The starter**, off `starter_basis`: the source and stored field, what the
  served board reads instead, the 4,385 of 4,392 agreement with the first
  pitcher used, the two-door agreement, the coverage counts, and the frozen
  denominator note. The lead sentence states the information-versus-leak
  distinction in full, so the panel cannot be read as disclosing a leak.
- **The park index**, off the payload's own `vintage.park_basis`, which was
  served and never drawn.
- **The dark columns**, off `vintage.feature_basis`, under a heading that says
  they priced nothing, with the block's own served note beneath them.

Every number in the panel is READ from an artifact. Nothing on the page sums,
averages or rounds them, and `starter_basis.copy_repair_owed` is deliberately
NOT rendered: it is an internal marker, and it went stale the moment the repair
above landed. Its replacement string is handed to the `betting_model` lane with
the `MODEL_REGISTRY.md` text.

**THREE BLOCKS, THREE POOLS, SAID OUT LOUD.** The bases do not share a
denominator, so the panel names each one where it is used rather than letting
the heading imply a single sample. The lead names the graded sample (`n_graded`,
642 on the 2026-09-18 artifact). The park rows carry their own pool line,
`n_gradable` with `n_fit_games` and `n_graded` beside it (947 gradable, 305
fitted, 642 graded), because a park index is an INPUT and the fit half has one
too: counting the fit half's park source is not grading it, and the house rule
that the 305 are never graded is untouched. The dark-column table is labelled as
the eval-window sample, which is the graded one. The starter block carries a
fine line saying its counts walk the completed-game cache (2,294 games), which
is not a grading pool at all, on top of the served note that says the 4,385 of
4,392 rate is a frozen archive and not those counts.

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

### 5c-A. The B3 rolling-form gate: `xwoba_14` and `xwoba_30`, look 2026-09-28 (drafted 2026-09-11, committed 2026-09-16)

**Standing.** This is the gate section rule 1 requires for the two B3 rolling-form
columns. It was drafted on 2026-09-11 and lands after `6e82acd5` (2026-09-11
19:55:59 -0400), the commit that carries the two 2026-09-11 corrections above, and
after the plan's 2026-09-15 deadline (5.1). Between the draft and this commit the
vintage store gained the 2026-09-13, 09-14 and 09-16 nights and missed 09-11, 09-12
and 09-15; the game cache grew from 2,200 games (last date 2026-09-10) to 2,270 (last
date 2026-09-15); `data/betting_model_eval.json` was regenerated on 2026-09-14 and
2026-09-16 with the same anchored cut and coefficients. **No number relating either
column, or a close variant, to a game outcome or a price was computed in the interval
or before it.** If this section lands after 2026-09-16, the committer changes the
heading date to the commit date and adds one line saying what moved on disk since
(the 7h re-read's form). It inherits rules 1 to 4, both 2026-08-19 corrections and
both 2026-09-11 corrections. For the pair only, it supersedes the three committed
sentences that keep the ~2026-09-17 date (the 2026-09-11 correction, "The
close-variant embargo" and "Not reopened"; 2026-09-11b, "The ~2026-09-17 window"),
later and never earlier, on counts alone. The 2026-08-20 clock start and the
2026-09-17 floor are unchanged.

Read to write it, and re-read on 2026-09-16:
- per vintage file 2026-08-18 to 2026-09-16: `schema`, `vintage_date`, `captured_at`,
  `covers_through`, `provenance.source`, the `feature_basis` string and `n` of both
  columns, and whether each club's cell is null (never the value);
- `.cache/betting/completed_games.json`: `date`, `home_org` and `away_org`. The count
  script (`counts3.py`) parses the whole file and projects each row to those three
  fields at once; no runs field is read or kept;
- `data/betting_model_eval.json`, the `vintage` block: `coefficients`, `diff_shrink`,
  `home_field_runs_adj`, `extra_inning_home_rate`, `split_date`, `fit_window`,
  `n_fit_games`, `run_dispersion_alpha` and the `feature_basis` counts;
- `data/betting_model_context.json`: the `run_dispersion_alpha` key only;
- `git log` of `data/hitter_leaderboards.json`, and which of its commits are on
  `origin/main`;
- the R5 lane record (R5-F1, R5-F3, R5-F10); plan sections 4 and 5; the 5c-B and
  5c-C sections;
- the code named below, at `3eda89d7`, at HEAD `a890f36a` and on the working tree.

The power arithmetic under "The expectation" is arithmetic on a Poisson pair and reads
no data (`power_arith.py`, `final_rev/power2.py`).

**Estimand.** Does adding `b * (z_xwoba_30 - zbar)` to the incumbent's per-side lambda
improve moneyline calibration, paired Brier on the home win, on the graded half of the
dated-value games, beyond a permuted twin and beyond offense re-entry, without
worsening log loss or the total?

**The columns, as built.** `leaderboard_vintages.build_xwoba_windows` differences
tonight's `hitter_leaderboards.json` `hitters[]` (xwoba * pa) against the newest
git-committed board whose committer date is on or before D-14 (`xwoba_14`) or D-30
(`xwoba_30`), through `xwoba_window_from_boards`. A club's value is window xwoba * pa
over window PA, rounded to 4 places.
- Null when the anchor trails its target by more than `XWOBA_ANCHOR_TOLERANCE_DAYS`
  (7), when a club's window PA is under `XWOBA_MIN_WINDOW_PA` (100 / 200), at the
  season fence, or when the builder raises.
- The per-hitter input is Savant's season `est_woba`, joined by
  `hitter_export._join_xhem_plus` for hitters with at least 100 Savant PA
  (`_XHEM_MIN_PA`, a local inside that function) and `est_woba > 0`, rounded to 3
  places.
- A hitter on the anchor board without an xwoba is excluded; a hitter absent from it
  counts his whole season; a traded hitter's window rides his current club.
- The true window is W to W+7 days, and the basis string records it.
- Every builder function is byte-identical at `3eda89d7`, HEAD `a890f36a` and the
  working tree of 2026-09-16 (`final_rev/freeze_identity_output.txt`; see
  "Construction freeze").

**Why nights are null, and will be.** Anchors are board commits, not nights. The hitter
board has 24 commits in 2026; after `52ffcb59` (2026-08-13) the next are `69fe0fca`
(09-04), `944502c5` (09-06) and `7cd5f572` (09-07), and none since. From those dates
and the 7-day tolerance alone, and absent a new commit:
- `xwoba_14` is null on every vintage from 2026-09-04 to 09-17, populated on the
  2026-09-18 to 09-28 vintages, and null from 09-29;
- `xwoba_30` was null on the 2026-08-23 to 08-28 vintages, is populated through the
  2026-09-19 vintage, is null on the 2026-09-20 to 10-03 vintages, and is populated
  from 10-04.

The basis strings on disk agree night by night through 2026-09-16. A later commit
cannot fill a past target. A board commit is the registered anchor source, not a
construction change. No board commit landing after 2026-09-16 can anchor any vintage
that prices a window game: for `xwoba_14` its earliest target is 2026-09-16, which is
the 2026-09-30 vintage; for `xwoba_30` every window vintage targets 2026-09-03 or
earlier.

**The anchors, pinned by sha and committer date.** `_git_board_anchor` runs `git log
--format=%H %cI` on the checkout at capture time and `_iso_date` keeps the first 10
characters, so the anchor is the committer date of a commit in THIS checkout's
history. The branch (`efv-conviction-2026-08-08`) is 136 commits ahead of `origin`.
`52ffcb59`, `69fe0fca` and `944502c5` are on `origin/main`; `7cd5f572` is on no remote
branch. The basis string records the anchor date, not the sha. So:
- **Expected anchor per future vintage** (target = vintage minus W; anchor = newest
  board commit on or before the target):

  | Vintages | `xwoba_14` anchor | `xwoba_30` anchor |
  |---|---|---|
  | 2026-09-17 | null (52ffcb59 trails by 21d) | `52ffcb59` 2026-08-13 (5d) |
  | 2026-09-18, 09-19 | `69fe0fca` 2026-09-04 (0d, 1d) | `52ffcb59` 2026-08-13 (6d, 7d) |
  | 2026-09-20 | `944502c5` 2026-09-06 (0d) | null (52ffcb59 trails by 8d) |
  | 2026-09-21 to 09-28 | `7cd5f572` 2026-09-07 (0d to 7d) | null (9d to 16d) |
  | 2026-09-29 to 10-03 | null (8d to 12d) | null (17d to 21d) |

- The look reads the anchor date off every dated-value game's basis string and checks
  it against this table and, for games already on disk, against the dates already
  recorded (08-13 on every populated `xwoba_30` night from 2026-09-13; 08-10 on the
  2026-09-10 night). A mismatch is a construction change under the freeze, and the
  games it prices go to the freeze bucket.
- **No history rewrite** (rebase, squash, amend, filter) of the four board commits
  above, or of any commit between `52ffcb59` and HEAD on this branch, before the look
  is recorded. A rewrite moves committer dates and silently changes values or nulls
  nights. The look record prints `git log --format=%H %cI -- data/hitter_leaderboards.json`
  at the harness commit beside the table.

**Coverage, counts only** (disk on 2026-09-16 after that night's capture; clock window
2026-08-20 to 2026-09-16; `counts3_output.txt`):

| | `xwoba_14` | `xwoba_30` |
|---|---|---|
| present nights in the window (of 17 present, 28 elapsed) carrying the column populated | 8 | 14 |
| dated-value games, both clubs carrying a value | 205, on 15 dates 08-21 to 09-04 | 258, on 19 dates 08-21 to 09-15 |
| stated-null games dated 08-21 to 09-15 | 146 | 93 |
| priced before the clock, predates the builder (dated 08-19 and 08-20, on the 08-18 and 08-19 records) | 24 | 24 |
| games with one club valued and the other null | 0 | 0 |
| dated-value games on a vintage 1 / 2 / 3 days old | 113 / 62 / 30 | 174 / 60 / 24 |
| a ~2026-09-17 look: last date, m, fit / graded | 09-04, 08-28, 92 / 113 | 09-16, 09-03, 87 / 171 on disk |
| the 2026-09-28 look, expected: last date, m, fit / graded | 09-27, 09-08, 205 / about 118 | 09-20, 09-05, 112 / about 211 |

The artifact's record-level `feature_basis` counts (populated 205 / 258, null_stated
170 / 117) coincide with the game-level counts here because every populated night
carries all 30 clubs; the 2026-09-11b game-level count is still to be built. m is the
split date defined under "The split". The expected row assumes the vintages from
2026-09-18 on are present (`xwoba_14`) and that the 2026-09-19 vintage is present and
populated (`xwoba_30`); its two contingencies are under "The split". Graded sides are
estimates at 13.1 games a date (section 5b):
- `xwoba_14`: 9 dates, 2026-09-19 to 09-27.
- `xwoba_30`: 146 games on disk (dated 09-05 to 09-15), plus 5 dates 2026-09-16 to
  09-20.

**One primary, and the secondary reads nothing in 2026.** `xwoba_30` is the primary.
`xwoba_14` is registered here for its estimand, its clock, its embargo and its
counts, and no number relating it to an outcome or a price is computed in 2026: no
fit, no criterion, no twin, no control, no leg 1. Its 2026 read is forgone, not
sealed, so nothing exists to be opened later. A 2027 test of either window is a new
registration under N9; it must disclose that the 30-day primary was read in 2026, and
if both windows are tested in 2027 they form one Holm family of two.

Why one primary and not a Holm family of two: the two windows are one construct. The
30-day window contains the 14-day one, both are differenced off the same anchors, and
one flag serves one of them. Serving both at once would be a third, unregistered
candidate.

Why `xwoba_30`, on counts alone and fixed before any outcome is read:
- It carries about 211 graded games at the look against about 118, and 146 of its
  graded games are on disk already, against none.
- Its window-PA floor is 200 against 100, so each club value rests on more plate
  appearances.
- Its fit side is on disk today under the expected last date (112 games dated 08-21 to
  09-04), while the secondary's graded side has not begun.

**The challenger (one parameter).** The incumbent's per-side lambda plus an own-offense
term:

    lam_S' = min(9.5, max(1.5, lam_S + b * (z_S - zbar)))

- `lam_S` is the incumbent's `expected_runs` lambda for scoring side S, unrounded,
  after `diff_shrink` and the home adjustment and clamped to [1.5, 9.5] there.
- `z_S` is the scoring club's `z_xwoba_30`, computed by `_assemble_team_inputs` from the
  pricing vintage (`inputs_as_of(date, allow_fallback=False)` then
  `team_inputs_from_vintage`): (v - mu) / sd over the clubs in the three-board
  intersection that carry a value, population sd (`_mean_sd`), and None when fewer
  than 2 do.
- `zbar` is the mean of z over the 2 x n_fit fit rows. The term enters with no intercept
  (5h-A addition 2), so it cannot absorb the board's total-level error (7f) or the late
  run-environment rise (7h).
- The opposing club's column does not enter, because this xwOBA is batting.
- **One seam prices both arms (to be built; nothing served calls it).** It takes the
  incumbent's (`lam_home`, `lam_away`), adds `b * (z - zbar)` to each side, clamps, and
  prices through `_score_joint(lam_home', lam_away', r=None)` and `split_tie_atom` at
  the incumbent's fit-window tie rate, Platt at identity. r is passed as None
  explicitly; the harness also asserts that `data/betting_model_context.json`
  `run_dispersion_alpha` is null and that `SERVE_PROB_CALIBRATION` is False at the
  harness commit, because `game_probabilities` resolves both from context when not
  told. At b = 0 the seam must reproduce `game_probabilities(...)["p_home"]` to its 5
  published places on every window game, and the harness asserts it before any
  number. That check reads no outcome.

**The fit (the 2026-09-11b 5h-A form).** Two rows per fit-side dated-value game, one per
scoring side, each with residual r = runs - lam. `_lambda_rows` returns bare
(lam, runs) tuples and drops the org, so a row builder (to be built) returns
(`game_pk`, date, side, scoring org, lam, runs) at the incumbent's parameters and
counts what it skips. Then b = sum((z - zbar) * r) / sum((z - zbar)^2). No incumbent
parameter is touched. This single calendar-midpoint split is the committed 2026-09-11b
fit rule for the four 5c columns; it replaces 11b's three quantiles here.

**The incumbent, pinned.** The vintage-mode graded pricer as `backtest._grade` fits it
on the anchored window, and never `build_context`'s in-sample fit (R5-F1: served b1
0.2510, b2 -0.3126). Pinned now, from `data/betting_model_eval.json` `vintage` at
2026-09-16 (unchanged since 7e-B):
- the anchored window: `split_date` 2026-08-01, `fit_window` 305 games 2026-07-06 to
  07-31, `n_fit_games` 305;
- `coefficients`: b0 4.345387, b1 -0.037205, b2 -0.096479, b3 0.594771, b4 0.149360
  (OLS, `n_rows` 610, `rmse` 3.288484);
- `diff_shrink` 1.28; `home_field_runs_adj` -0.0443;
- the tie rate: `extra_inning_home_rate` 0.4921 (`_fit_tie_home` on the fit window,
  shrunk toward 0.5 with `TIE_SHRINK_K` 100);
- `run_alpha` None, and the context key null.

The flag set, by name and value at HEAD `a890f36a`, which the harness commit must
carry unchanged or the look records INDETERMINATE before any fit:
`SERVE_RIDGE_FIT` False; `SERVE_RUN_DISPERSION` False; `SERVE_PROB_CALIBRATION` False;
`SERVE_RUNLINE_TIE_SPLIT` True; `SERVE_ATH_PARK` True; `SERVE_TOTAL_LEVEL`,
`SERVE_TOTAL_DISPERSION` and `SERVE_TOTAL_CALIBRATION` False;
`VINTAGE_FIT_WINDOW_GROWS` False; `MODEL_VERSION` `betting_runs_v2`;
`SERVE_SCORE_KERNEL`, `SERVE_PRICER` and `SERVE_XWOBA_FORM` absent. `SERVE_ATH_PARK`
reaches a vintage-priced game only through a schema-5 `parks_short_window` block, so
the anchored window and every schema-3 and schema-4 record price the pre-flag park in
both arms; the look reports how many window games rode a record without the block.

Parity, before any fit: the harness re-solves the incumbent inline (as
`_total_level_split` does) and must reproduce the five coefficients, `diff_shrink`, the
home adjustment and the tie rate to the artifact's rounding (6, 2, 4 and 4 places) on
the cut `_vintage_cut_index` returns. If the cut is not 2026-08-01 or any value
differs, the look records INDETERMINATE and nothing is fitted; 2026-08-01 governs and
is never replaced by a later cut.

**The harness and the dated note.** The harness is the commit that lands the pair's
mode and its fixture tests. It is named in a dated note filed no later than
2026-09-27, before any number on this pair exists, which pins:
- the harness commit, after it passes the b = 0 identity check and the parity check;
- the flag set above, printed by name and value at that commit;
- the store: `prospect-tracker/.cache/leaderboard_vintages/` on host NOAH-PC (the
  store R5-F3 measured), with a SHA-256 over the sorted (file name, file SHA-256) pairs
  of every file the run may read. No file from the deploy box is copied in (5c-B, the
  store).

The look runs from a detached worktree of the harness commit with `.cache` junctioned
to the main tree's (the 7h re-read's method), so no flag flipped after that commit
reaches either arm. On 2026-09-28 the order is: 7i first (its own text), then the 7h
re-read, then this look. Neither of those reads changes this look's incumbent, because
its flags are frozen at the harness commit.

**The graded window.** Fixed now:
- **Games.** Regular-season games (the `build_game_cache` set, which drops any
  `gameType` other than R) dated 2026-08-21 to 2026-09-27. Each is priced on the
  vintage `inputs_as_of` resolves.
- **Dated value.** A game is dated-value for a column when that vintage is a present
  night (2026-09-11b point 3) and both clubs' cells are non-null. Only dated-value games
  are fitted or graded. Every other game is counted in its bucket and never scored, and
  never enters as a zero paired difference.
- **Postseason.** Not graded, by the date bound alone: the window ends with the
  regular season, 2026-09-27 (plan 5; R5-F10), whatever O25 decides and whenever the
  look runs. The 2026 Wild Card start is not on the record in this repository; the
  window does not depend on it. The owner's 2026-09-11 answer that 5e counts
  postseason belongs to 5e alone.

**The split.** m = first + floor((last - first) / 2) days over the column's dated-value
game dates. The floor settles the half day 2026-09-11b left open. It was chosen with
the counts table in view: under the expected last date (09-20, span 30) floor and
ceiling coincide at 09-05; under contingency A below (span 37) the floor gives 153 fit
games and the ceiling 168, and the floor stands as registered.
- Games dated before m are fitted; games on or after m are graded.
- m is computed at the look from dates on disk, written into the look record before
  any fit, and never moved. It depends on the LAST dated-value date, which is not on
  disk today, because `as_of` prices a game on the newest earlier vintage with no
  maximum age (2026-09-11b point 4). Two contingencies, fixed now:
  - **A. A missing night from 2026-09-20 on extends the window.** Games on the missed
    dates ride the 2026-09-19 vintage (or the last populated one before it) at age 2 or
    more and are dated-value. If every night 09-20 to 09-27 were missed, last = 09-27,
    m = 09-08, fit 153 (`counts3_output.txt`). The 2026-09-11b bucket report shows the
    age-2-or-more games either way.
  - **B. A present 2026-09-19 vintage whose builder raised or whose git call failed**
    is null for every club, so the 09-20 slate is not dated-value; then last = 09-19,
    m = 09-04, fit 96, under the 100 floor: INDETERMINATE. A missing 09-19 night is
    not this case: the 09-20 games then ride 09-18 at age 2.
- All dated-value games fall after the 2026-08-01 cut, inside the vintage eval half, so
  rule 4 reads as written.

**Floors, carried from 11b unchanged.** Per column: at least `VINTAGE_MIN_FIT_GAMES`
(100) dated-value fit games and `VINTAGE_MIN_EVAL_GAMES` (50) dated-value graded games,
or the column records INDETERMINATE. `VINTAGE_MIN_GRADED_GAMES` (600) is not a
criterion here, as in 11b's form.
- **Not lowered.** The table shows both columns under 100 at a ~2026-09-17 look, and a
  floor set knowing the count it must admit is a floor chosen to admit it.
- **Night floor** (2026-09-11b point 2: at least 14 of the 28 nights 2026-08-20 to
  2026-09-16 present). Two readings exist, and both are disclosed:
  - **File-level, which governs.** Point 2 counts present nights, and point 3 defines a
    present night by file, source and capture time; "populated" enters point 1 only,
    for the clock start. On disk 17 nights are present: 08-20, 08-21, 08-23, 08-24,
    08-27, 08-30, 08-31, 09-03, 09-04, 09-05, 09-06, 09-07, 09-09, 09-10, 09-13, 09-14
    and 09-16. Missing: 08-22, 08-25, 08-26, 08-28, 08-29, 09-01, 09-02, 09-08, 09-11,
    09-12 and 09-15. The window is closed and the floor is met.
  - **Column-level, reported.** Counting only present nights that carry the column
    populated: `xwoba_30` 14 of 28, which also meets 14; `xwoba_14` 8 of 28, which
    would not. Nothing turns on the second, because `xwoba_14` reads nothing in 2026.
  The look reports both counts per column.

**The look: once, on 2026-09-28, kill date 2026-10-06.**
- The read runs on 2026-09-28, or the first day after it on which the pinned harness
  runs under the same window, code and rules. A slipped read is still the one look.
- **Kill date 2026-10-06.** If the read has not run by then, the pair closes for 2026
  without a verdict and the record says why. That matches 7i and keeps the pair ahead
  of the 2026-10-07 reads of 5d and 5k.
- **The read is spent at the first outcome read**, which is the fit-side residual. An
  abort before it (identity check, parity, counts, m) may be repaired and rerun, and
  each attempt is recorded. An abort after it, for any cause, records INDETERMINATE
  and nothing is rerun. INDETERMINATE therefore covers a floor unmet, the night floor
  missed, a parity failure, contingency B, and a fit, twin or control that cannot run
  or that crashes after the fit.
- There is no second read on 2026 data; a 2027 test is a new registration under N9.
- This moves the pair off the ~2026-09-17 date the record left it on, later and never
  earlier, on counts alone:
  - **~2026-09-17 is the earliest admissible look, not a required one.** The
    2026-08-19b text calls it the "strict 4-week earliest look". Rule 2 reads "4 to 6
    weeks ... minimum", and 2026-09-28 is 39 days (5.6 weeks) after the 2026-08-20
    start; six weeks is 2026-10-01.
  - **A ~2026-09-17 look is INDETERMINATE in advance.** Both columns sit under the fit
    floor then (92 and 87), so that look would spend the pair's one 2026 read on a
    result known before it runs.
  - **2026-09-28 is the first day every regular-season dated-value game exists.** The
    graded window is the whole season, and no choice of date can shorten it.
- **No look is required on ~2026-09-17.** If a harness run is held on any day before
  2026-09-28, it leaves both columns out of its candidate list and reports counts
  only: nights present and missing, populated nights per column, and dated-value games
  per bucket per column. The same holds for `star_out` (5c-C) and `lineup_strength`
  (5c-B) under their own sections.

**Before the look: fixtures only, and a guard.** The pair's mode (the seam, the row
builder, the residual fit, the twin, control 2, the report) is developed and tested on
synthetic fixtures only. The harness refuses to fit, score or twin either column on the
real store before 2026-09-28: a date guard and an outcome-field refusal in the form of
`tools/ph_gate.check_look_date` and `refuse_outcome_fields`, each with a test (to be
built). Only two things may run on the real store earlier, and the look record says
whether each did and on what day: the b = 0 identity check, which reads no outcome,
and the counts report. A dry run of the fit on the real store before 2026-09-28 is a
rule 1 measurement and disqualifies the pair.

**The expectation, stated before the first fit: FAIL or INDETERMINATE, for power.**
Arithmetic, no data: independent Poisson sides at 4.5 runs each, the tie atom split
50/50, z ~ N(0, 1) per side, lambdas clamped to [1.5, 9.5].

| b, runs per sd | RMS shift in p_home | expected t at 118 games | at 210 | at 2,000 |
|---|---|---|---|---|
| 0.05 | 0.0093 | 0.10 | 0.13 | 0.41 |
| 0.10 | 0.0185 | 0.20 | 0.27 | 0.83 |
| 0.20 | 0.0369 | 0.40 | 0.53 | 1.65 |
| 0.260319 (b_ref, below) | 0.0480 | 0.52 | 0.70 | 2.15 |
| 0.30 | 0.0552 | 0.60 | 0.80 | 2.47 |

- The paired-Brier leg's expected t is about sqrt(n) x RMS (5f's arithmetic).
- At about 210 graded games the leg needs an RMS near 0.113 (1.645 / sqrt(210)). That is
  b near 0.63 runs per sd (`final_rev/power2_output.txt`), more than twice the
  contaminated full-season own-offense slope of +0.260319 (7e-B, 4,248 rows).
- At b_ref = 0.260319 the leg reaches t 1.645 only at about 1,176 graded games.
- One standard error of b is about 0.22 runs per sd: the fit half's rmse 3.288484 over
  2 x 112 rows of unit-variance z (`final_checks/power_precondition_output.txt`).

So a FAIL here is not evidence that recent form does not matter, and a PASS on its own
would not be evidence that it does (5f's wording). A PASS at this n would rest on about
211 graded games and is labelled so wherever it is cited.

**No power precondition.** 5f stops at UNDERPOWERED when sqrt(n) x RMS is below 1.645,
and says "This rule is specific to 5f". This section adds no such verdict, for 5c-B's
reason: a precondition read off the fitted b is a fit-side significance test that
decides whether the graded outcomes are read at all, and it shields a small b, the
null, from a FAIL; a precondition at a slope fixed now (b_ref = 0.260319) is decided
by the arithmetic above before the look and would record UNDERPOWERED at every 2026 n,
which is a decision not to read dressed as a measurement. The look runs once and reads
its outcomes. Two numbers are reported beside the verdict, neither of which decides:
- the RMS of challenger minus incumbent p_home over the graded games, from features
  and the fitted b only, and sqrt(n) times it;
- the same RMS at b_ref = 0.260319, and sqrt(n) times it.

**Criteria, vintage leg.** On the primary's graded games. All four are required. Every
delta is incumbent loss minus challenger loss per game, so positive means the challenger
is better (11a, 11b).
1. **Moneyline, paired Brier on p_home.** `_paired_delta` (population sd, t = mean /
   (sd / sqrt(n)), lb95): mean delta > 0 at one-sided t >= 1.645 (`Z_95_ONE_SIDED`). y is
   home runs greater than away runs, as `_grade` scores it.
2. **Moneyline, paired log loss** (`_logloss`, eps 1e-9). Mean delta >= 0 on the point
   estimate.
3. **Sign.** b > 0: a club hitting better lately scores more. A wrong sign fails the
   column whatever 1 and 2 read (5g criterion 3's form).
4. **Total, not worse.** Paired absolute error |home runs + away runs - (lam_home +
   lam_away)|, on unrounded lambdas. Mean delta >= 0 on the point estimate. The term
   moves both lambdas, so a flag cannot move the moneyline without the total. This is a
   point-estimate non-degradation condition; it carries no alpha and is not a member of
   family RE (5k).

Criteria 1 and 2 are rule 4's 11b form at the 2026-09-11b split; 3 and 4 are added
here. The runline is reported only, on both sides as the per-game sum of the two
tails' log losses (the 11a amendment), under the incumbent's construction at the
harness commit: `_lab_runline_split` of the anchored fit window while
`SERVE_RUNLINE_TIE_SPLIT` is True. The split never touches p_home.

**Control 1: the permuted twin (rule 3, per pricing vintage).** 200 replicates,
replicate k seeded `random.Random(k)` for k = 0 to 199. Each replicate:
1. For every pricing vintage in ascending `vintage_date`, shuffles the column's stored
   values among the clubs carrying one (clubs in ascending org order). There is one
   permutation per vintage, applied to every game that vintage prices, on the fit side
   and the graded side alike. Rule 3 says "within each date"; this section permutes
   within each pricing vintage, because z is standardized per vintage and two dates that
   ride one vintage share every feature. That is this section's own rule, listed under
   "This section adds".
2. Standardizes through `_assemble_team_inputs`. A permutation leaves mu and sd
   unchanged, so the z-scores permute exactly.
3. Refits b with its own zbar, and grades.

The candidate beats its twin when its mean paired Brier delta is strictly greater than
at least 190 of the 200 twin deltas, ties counted against it. That is a nearest-rank
bar and this section's own rule.

**What beating the twin means, and what it cannot mean.**
- **It means** the column's assignment to clubs carries information the incumbent lacks,
  beyond what one fitted slope on a regressor with the same distribution and date
  structure finds by chance.
- **It removes date-level effects.** z is standardized within each vintage, so a
  league-wide hot or cold stretch is removed from both the column and its twin, and
  neither is credited with it.
- **It does NOT separate form from team quality.** A column that was only team quality
  would beat its twin too, because the twin carries no club identity at all. Rule 3
  names exactly that separation as the twin's purpose, so this section adds control 2.

**Control 2: offense re-entry.** The same fit, on the same rows, with the scoring club's
`z_off` from the same record in place of the column. The candidate passes only if its
mean paired Brier delta exceeds the control's on the point estimate.

Why it is needed: the incumbent's own-offense slope is b1 -0.037205 on the anchored
window (OLS). 7e-B's constrained ridge pinned that term at exactly zero at the three
gate splits (0.6, 0.7, 0.8) at the penalties the inner split chose, and on the
anchored 2026-08-01 window at penalty 0.3 it read +0.041543 with the constraint not
binding. Either way the incumbent prices almost no own-offense, so any team-offense
proxy fitted on later games can "help" simply by putting offense back. A column that
does not beat this control is re-fitting offense on a later window. That is rule 3's
"smuggles offense_plus in again", and a null.

What control 2 buys, exactly: a PASS shows information beyond `offense_plus`. It does
not show recent form as such; a season-level xwOBA quality read with no form in it
would beat `z_off` too. The two-term fit and the correlation with `z_off` (reported
below) are the reader's instruments for that, and neither decides.

**Leg 1: the contaminated screen (to be built).** This is rule 4's first leg, and it can
only disqualify. It runs once, and only after the vintage leg and both controls pass: it
exists to block a serve, and a column that did not pass has no serve to block. So no
contaminated number exists for a column that did not pass.
- **Column.** Club trailing-30-day xwOBA over games dated D-30 to D-1.
  - Source: Baseball Savant's pitch-level `statcast_search` CSV, the same host
    `swing_plus_ingest.SEARCH` names. That constant is a per-batter season template
    (`fetch_player_season(mlbam, season)`), not a league pull; the league-wide query
    chunked by game date, fetched once for the 2026 regular season and cached under
    `.cache/`, is to be built. No credential and no Odds API credit.
  - Per plate-appearance-ending pitch: Savant's `estimated_woba_using_speedangle`
    where Savant fills it, else `woba_value`, over `woba_denom`. These are Savant's
    column names; none of the three appears in the repository today.
  - Each PA is credited to the club that batted in that game. A club-date under the
    column's `XWOBA_MIN_WINDOW_PA` (200) is null. Values are standardized within date by
    the same population-sd formula.
- **Why it is labelled contaminated.** It differs from the registered column in four
  named ways: game-club rather than current-club attribution, every PA rather than the
  100-PA Savant subset, an exact 30-day window rather than 30 to 37, and today's Savant
  model. Its incumbent is contaminated too.
- **Fit and grade.** Section 6 mode 1 forward, on `backtest()`'s own split (the 70% date
  quantile of the 2026 completed regular-season dates) with its season-to-date `_grade`
  incumbent.
  - b is fitted in the 5h-A residual form on fit-half games where both clubs carry a
    value.
  - It is graded on held-out games where both clubs carry a value. That is the last 30%
    of the season's dates, three to four times the vintage leg's graded games at 13.1
    games a date.
- **DISQUALIFY** when b <= 0, or when the paired Brier delta (incumbent minus candidate)
  is <= 0 on the point estimate. If there is no improvement at that sample size, with the
  incumbent's features leaking the game, a dated column has nothing to find.
- **Not built in time.** If leg 1 does not exist when the vintage leg passes, the record
  reads PASS pending leg 1 and the column cannot serve. Leg 1 then runs once, when
  built, under this text.

**Reported whichever way it lands.**
- The dated note: harness commit, flag set, store host, path and hash, `MODEL_VERSION`.
- The incumbent: parameters, the governing cut and `_vintage_cut_index`'s cut beside
  it, the parity result, the identity check and the day it ran, and which runline
  construction both arms used.
- The construction audit to the harness commit, and the anchor-date check.
- The 2026-09-11b report, per column:
  - clock start and floor;
  - nights present and missing, with the missing dates listed, and the populated-night
    count;
  - graded games by pricing vintage in the three buckets, plus the freeze bucket;
  - of the dated-value games, how many rode a vintage 2 or more days old, with the
    game-weighted `vintage_age_days`;
  - games on a record without `parks_short_window`.
- For the primary: m, the first and last dated-value dates, n_fit and n_graded, and the
  true-window distribution (30 to 37) off the basis strings of the dated-value games.
- b with its standard error and zbar.
- The two power numbers above.
- Every criterion's delta, sd, t and lb95.
- The twin's 200 deltas, the 190th smallest, and the candidate's rank.
- Control 2's slope and delta.
- The two-term fit, with `z_off` and the column together (reported only).
- The correlation of the column's z with `z_off` over the fit rows and the graded rows,
  from features only.
- The runline, both tails.
- Leg 1's numbers when it runs, labelled contaminated.

**Verdicts, for the primary.**

| Verdict | When |
|---|---|
| INDETERMINATE | a floor unmet, the night floor missed, parity failed, contingency B, or a fit, twin or control that cannot run or that aborts after the first outcome read. Neither passed nor closed |
| FAIL | any of criteria 1 to 4, or either control, fails. A 2026 null, at 2026 power |
| PASS pending leg 1 | all of the above pass and leg 1 has not run. Not servable |
| DISQUALIFIED | leg 1 fires |
| PASS | all of the above pass and leg 1 does not fire |

No verdict is followed by a second 2026 read. On a FAIL or INDETERMINATE the column
stays dark and keeps accruing; 2026 is closed for it; a 2027 test is a new registration
under N9.

**What a pass would change, and the flag it would ship behind.** On the look day,
nothing served changes. Serving needs a new flag, `SERVE_XWOBA_FORM` (to be built),
default False, in the `SERVE_RUN_DISPERSION` idiom. It flips in one commit with:
- a `MODEL_VERSION` bump, so the ledgers never pool two pricers;
- b and zbar frozen as literals, the look's fit-side values, never refit on the graded
  games (plan 4.2 X4);
- a tripwire test.

Flipped, it moves `lam_home` and `lam_away` at every game where both clubs carry
`xwoba_30`. The moneyline, the runline and the total all move, and the Pick of the Day
can change on any night. A game where either club's value is null is priced by the
incumbent and says so; absent is never zero.

A pass does not flip the flag; the owner does, and only after three prerequisites:
1. **A live builder.** `team_inputs_detail` sets both columns to None on the live path
   today.
2. **An anchor that exists every night.** With anchors on board commits only, the column
   would be null on most nights (on every vintage 2026-09-20 to 10-03 for `xwoba_30`). A
   nightly anchor store (to be built) changes where the anchor comes from, not the
   computation. It is recorded here as an amendment before the flip, provided the W to
   W+7 window rule is unchanged.
3. **O14.** b was fitted on the graded vintage pricer's residual, and the pricer that
   serves is a different fit (R5-F1). A flip therefore needs either the graded pricer
   served, or the term re-validated on the served pricer through the 7e-D replay.

A flip inside the 2026 postseason would price games this gate did not grade. It could
not reach a price before the 2026-10-04 vintage anyway.

**Embargo until the look is recorded.** No number relating either column, or a close
variant, to a game outcome or a price.
- **A trailing window** is one whose START moves with the game date D. Season-to-date
  measures are not trailing windows: `offense_plus` and its `z_off`, HEM+, the season
  `xwoba` and `xhem_plus` on the hitter board, and every other incumbent input are
  outside this embargo, and the served board, the nightly contaminated backtest and
  control 2 read them as they always have.
- **Close variants, embargoed by this section:**
  - any club-level trailing-window offense measure (xwOBA, wOBA, HEM+, runs scored,
    OPS, barrel or hard-hit rate) over any window of 7 to 45 days, from any source
    (Savant, `.cache/game_feeds`, `.cache/pbp_corpus`, git boards, the vintage store);
  - the column net of `z_off`;
  - any other anchor tolerance or window-PA floor;
  - leg 1's own column.
- **Embargoed by other sections, and not lifted here.** The 2026-09-28 record lifts only
  the four items above. Per-hand trailing splits are 5e's (~2026-10-09); lineup-weighted
  or posted-lineup trailing measures are 5c-B's and 5j's (2026-10-05); star
  availability is 5c-C's (2026-10-05); league-level trailing windows carry no
  club-to-club variation and are 5k's, read on or after 2026-10-07.
- **N1** never reconstructs the pair (plan 7.1 item 14).

**Construction freeze (plan 4.2 X9's form).** The registered construction is, by
function name at `3eda89d7` (3eda89d7 lines in brackets, HEAD `a890f36a` lines in
parentheses):
- `leaderboard_vintages.py`: `XWOBA_WINDOWS` [444] (573),
  `XWOBA_ANCHOR_TOLERANCE_DAYS` [445] (574), `XWOBA_MIN_WINDOW_PA` [449] (578),
  `BOARD_FILE` [450] (579), `_hitter_xwoba_map` [475-491] (604-620),
  `xwoba_window_from_boards` [494-543] (623-672), `_git_board_anchor` [546-593]
  (675-722), `build_xwoba_windows` [596-639] (725-768), `_org` [263-272] (381-390),
  `_iso_date` [279-292] (397-410), and the `build_dark_team_columns` call site
  [810-821] (939-950);
- `hitter_export._join_xhem_plus` [394-436] (409-451), with its `pa >= 100 and
  est_woba > 0` join condition and 3-place rounding, and the `hitters[]` row writer in
  `hitter_export.export` (through `hem_plus.score_pool`) for the `mlbam`, `team`, `pa`
  and `xwoba` keys the builder reads;
- `trades.canonical_org` [322-350] (375-403), which `_org` calls.

All thirteen are byte-identical across `3eda89d7`, HEAD and the working tree of
2026-09-16 (`final_rev/freeze_identity_output.txt`, AST source segments). Any change to
any of them before the look is recorded here the same day. Vintages written after it
go to their own ungraded bucket, the clock does not restart, and the look reads only
games priced before the change. The 2026-09-11 correction cleared the pair against
`7cd5f572` only. The look record therefore carries the same identity check from
`3eda89d7` to the harness commit over all thirteen, plus the anchor-date check above,
read before any fit.

**Disqualification.** Any number relating `xwoba_14`, `xwoba_30` or a close variant
above to a game outcome or a price before the 2026-09-28 look is recorded, by any
path, disqualifies both columns under rule 1. That includes a fit, score or twin of
either column on the real store before that date.

**To be built.**
- **The pair's mode in the harness:** the seam, the row builder, the residual fit, the
  b = 0 identity check, the parity check, the twin, control 2 and the report, on
  synthetic fixtures.
- **The guard:** the date refusal before 2026-09-28 and the outcome-field refusal, with
  the test that no run dated before 2026-09-28 fits, scores or twins either column.
- **The 2026-09-11b reporting:** the game-level both-clubs count, the populated-night
  count and the bucket report.
- **The dated note.**
- **Leg 1:** its builder and the screen.
- **For serving:** `SERVE_XWOBA_FORM`, the live builder and the nightly anchor store.

**Plan edits this needs** (`docs/master-plan-2026-09-11-war-epoch-drivers-betting.md`),
made once for 5c-A, 5c-B and 5c-C together:
- 5.1, the ~2026-09-17 row: no column looks. It becomes "if a harness run is held,
  counts only for the xwOBA pair and `star_out`", or is deleted.
- 5.1, the 2026-09-28 row: add the `xwoba_30` look, once, with `xwoba_14` counts;
  kill date 2026-10-06.
- 5.1, the 2026-10-05 row: add `star_out` (5c-C).
- E5, O11 and W1: "the 5c look" is `xwoba_30` on 2026-09-28 and `star_out` and
  `lineup_strength` on 2026-10-05; step M does not touch the pair's inputs, so its
  sequencing names `star_out` and its date.
- The dependency spine: the I3 amendments feed the 2026-09-28 look, then the
  2026-10-05 looks.
- 7.2, risk 7: rolling-form close variants are embargoed until 2026-09-28.

**Doc edits this needs** (`docs/diamond-betting.md`): the three committed sentences
that keep the pair on ~2026-09-17 (2026-09-11 correction, "The close-variant embargo"
and "Not reopened"; 2026-09-11b, "The ~2026-09-17 window") each gain "superseded for
the xwOBA pair by 5c-A".

**Not reopened.** No criterion, control or threshold in rules 1 to 4 or in the
2026-09-11b reading is amended, and neither floor moves. This section adds:
- the primary designation, and the secondary's forgone 2026 read;
- the rounding of m, and its two contingencies;
- the pinned incumbent, flag set and parity check;
- the anchor table and the no-rewrite rule;
- the fixtures-only rule and the guard;
- criteria 3 and 4;
- the twin permuted per pricing vintage, and the 190-of-200 bar;
- control 2;
- leg 1's construction, and its place after the vintage leg;
- the pair's look date, 2026-09-28, the kill date and the spent-read rule. This
  supersedes, for the pair only, the 2026-09-11 corrections' "keep the ~2026-09-17
  date": it is later than that date and never earlier.

#### Closure, recorded 2026-10-02: the pair closes for 2026 without a verdict

This closes "The look: once, on 2026-09-28, kill date 2026-10-06." above.
- **The look code does not exist** at main HEAD 842b5f64 on 2026-10-02. The pair's mode
  in the look runner (the seam, the row builder, the residual fit, the b = 0 identity check,
  the parity check, the twin, control 2, the report) is unbuilt, and so is the guard: the
  date refusal and the outcome-field refusal "in the form of
  `tools/ph_gate.check_look_date` and `refuse_outcome_fields`". `tools/ph_gate.py` carries
  functions of those two names, but they are 5f's pinch-hit gate module (its date guard
  refuses before the end of the 2027 regular season) and are not wired to this pair.
- **No build is scheduled before the 2026-10-06 kill date.** The writer slots of the gap
  from 2026-10-04 to the epoch's step A belong to the fWAR epoch's preconditions (plan
  Part 8, 8.C 'The gap (Sun 10-04 to step A), in order').
- **So the pair closes for 2026 without a verdict**, under the look paragraph's own text:
  "If the read has not run by then, the pair closes for 2026 without a verdict and the
  record says why." It is recorded now, with the 7h re-read, rather than on 2026-10-06.
- **The look record.** Neither the b = 0 identity check nor the counts report ran on the
  real store, because no runner exists to run them. No number relating `xwoba_14`,
  `xwoba_30` or a close variant to an outcome or a price was computed, so the embargo
  held and nothing is disqualified.
- **A later test.** In the look paragraph's words: "There is no second read on 2026 data;
  a 2027 test is a new registration under N9." That registration discloses this closure.


### 5c-B. The B4 availability gate: `lineup_strength`, look 2026-10-05 (drafted 2026-09-11, revised 2026-09-16)

**Standing.** This is the rule 1 section for `lineup_strength`. It was written on
2026-09-11 and revised on 2026-09-16 on two reviews, before any number related the
column, either side of the `7cd5f572` membership change, or any variant to a game
outcome or a price. It is committed on the date its commit carries, after the two
2026-09-11 corrections (commit `6e82acd5`, 2026-09-11 19:55:59 -0400) and after the
2026-09-15 lock the first of them set. What admits it is rule 1: each candidate gets its
own gate section before any number is computed on it, and the 2026-09-11b correction
repeats that none of the four columns has one. The 09-15 lock bars amendments to
`lineup_strength`; this section amends neither correction. What it adds (the candidate,
the estimand, the criteria and thresholds, two twins, the bar for each, rule 4's
contaminated leg and the verdict order) is rule 1 gate content. Where it goes further
than the corrections, it says so under "Extensions", in their own form. Its look is the
2026-10-05 row that the first correction adds to plan 5.1.

**O25 closed at its default.** The first correction locked O25 (postseason games in
this look) by 2026-09-15 with the default "not graded". No answer was given by that
date. For this look the default binds:
the window is regular-season games. An answer given later cannot move this look's
window or its split, because every fit-side game will have been played by then, and a
parameter chosen after the data exist is a parameter chosen on the data. A later answer
goes to a 2027 registration under N9. The plan's decision table should read O25 as
closed at the default for 2026.

Those corrections fix:
- the clock (2026-09-07 to the 2026-10-05 floor) and the one look;
- the graded window, the pre-change and post-retrain buckets, X9 and the embargo;
- the fit form, the night floor, the O25 default and step M's earliest date.

**Nothing in this section was measured against a game result.** Read to write it:
- this document's sections 5, 5a, 5c (with all four corrections), 5d, 5e, 5f, 5g, 5h
  (rules and 5h-A), 6, 7e, 11a and 11b; plan sections 2.3, 4 and 5; the R5 lane record;
  the 2026-09-11 drafts of 5c-A and 5c-C and 5c-A's 2026-09-16 revision;
- code, read at HEAD `a890f36a` (2026-09-11 19:56:48 -0400) on a tree whose
  `betting_model.py`, `leaderboard_vintages.py`, `hem_plus.py`, `bullpen_export.py`,
  `fa_projection.py`, `betting_export.py`, `dfs_export.py` and `tools/ph_gate.py` are
  clean at HEAD on 2026-09-16. `betting_model.py` and `leaderboard_vintages.py` are
  byte-identical at `497d667f`, `6e82acd5` and `a890f36a` (the commits between touch
  docs only). Code is cited by name, never by line, because line numbers move:
  - `leaderboard_vintages` (`_proj_year1_woba_map`, `lineup_strength_from_orders`,
    `build_lineup_strength`, `snapshot`, `as_of`, `LINEUP_MIN_JOINED_SLOTS`,
    `LINEUP_SLOT_PA`);
  - `hem_plus` (`build_batting_order`, `team_offense`); `bullpen_export`
    (`_active_mlbam_ids`, `MIN_CLUBS_FOR_ROSTER_FILTER`); `fa_projection` (`rate_path`,
    `_assemble_hitter`, `_woba_scale`);
  - `betting_model` (`_assemble_team_inputs`, `_mean_sd`, `team_inputs_detail`,
    `team_inputs_from_vintage`, `expected_runs`, `game_probabilities`, `_score_joint`,
    `split_tie_atom`, `_lambda_rows`, `_paired_delta`, `_logloss`, `_lab_runline_split`,
    `_total_level_split`, `_total_dispersion_split`, `backtest`, `_vintage_cut_index`,
    `_feature_basis`, `DARK3_TEAM_COLUMNS`, the serve flags and vintage constants);
  - `betting_export.props_fair_lines`; `dfs_export` (the `fetch_lineups` call);
    `fantasy_schedule.fetch_lineups`; `tools/ph_gate.py`;
- `git log` and `git diff` of the commits in the construction audit below, and an
  AST-extracted function compare between `7cd5f572` and `a890f36a` (script
  `rev3_funcdiff.py`, output beside it);
- per vintage file 2026-08-18 to 2026-09-16: `schema`, `vintage_date`, `captured_at`,
  `covers_through`, `provenance.source`, `sources[*].as_of`, the
  `feature_basis.lineup_strength` basis and `n`, whether a `parks_short_window` block
  exists and its keys, and the per-club count of non-null values;
- the live `data/hitter_leaderboards.json` of 2026-09-16: `as_of`, `generated_at` and
  the `roster_filter` flags;
- `.cache/betting/completed_games.json`: `game_pk`, `date`, `home_org`, `away_org`;
- `.cache/fantasy_schedule/lineups_2026-09-10_R.json`, `2026-09-11_2026-09-17_R.json`,
  `2026-09-14_2026-09-20_R.json` and `2026-09-16_2026-09-22_R.json`: `gamePk`,
  `officialDate`, `gameType`, status;
- `data/betting_model_eval.json`: the `vintage` block's `split_date`, `fit_window`,
  `coefficients`, `diff_shrink` and `home_field_runs_adj`; the top-level `split_date`
  and `forward.n`.

No column value, score, run, win probability or price was read.

**The column, as registered.** Per club per vintage:
- `lineup_strength_from_orders` joins each slot `key` of `teams[].orders.vl` and `.vr`
  in `hitter_leaderboards.json` to projected year-1 wOBA, `mlb_projections.json
  vets[].woba[0]` (`_proj_year1_woba_map`, keyed by mlbam as a string).
- A side counts when at least `LINEUP_MIN_JOINED_SLOTS` (7) slots join.
  `build_batting_order` emits nine slots or none; the builder counts joined slots and
  does not check for nine. Joined slots weigh equally. An unjoined slot is skipped,
  never zero.
- The value is the mean of the surviving side means, rounded to 4 places. One surviving
  side stands alone; none makes the club null.

Since `7cd5f572` the nine is drawn from active-roster hitters when the filter applied,
except where the first correction's three fallbacks apply: the board-level fallback
(`applied` false, nothing filtered), the per-club fallback (`roster_filter_skipped`, the
unfiltered nine), and kept hitters with no readable mlbam. The three builder functions
and the constant are byte-unchanged since `3eda89d7`; `git log -L` returns that commit
only. The equal slot weights are part of the construction. A slot-PA-weighted form
(`LINEUP_SLOT_PA`) is a variant and is embargoed.

**Construction audit, `7cd5f572` to `a890f36a`.** Every commit in that span that touched
the orders builder, the roster walk, the vintage builder or the engine behind
`woba[0]`. None changes membership or the construction. The AST compare pins it:
`_active_mlbam_ids`, `_proj_year1_woba_map`, `lineup_strength_from_orders`,
`build_lineup_strength` and `_paired_delta` are identical at `7cd5f572` and `a890f36a`;
`build_batting_order` and `team_offense` differ (the two commits below) and
`team_offense` is identical from `77174943` to `a890f36a`.

| Commit | Touches | Class | Evidence |
|---|---|---|---|
| `0629fb69` (2026-09-10) | `hem_plus.build_batting_order` and `team_offense` gain `split_hem`; `hitter_export`; `leaderboard_vintages` (the 5e repair) | not a membership change | the nine is still `build_batting_order(avail, hand, split_hem)` over `avail`, the HEM+ pool filtered by `active_ids`; `hem_plus_split` is stamped beside `hem_plus`, "never instead of it"; the three builder functions are untouched |
| `77174943` (2026-09-11) | `hem_plus.team_offense`: bench, `slot_meta`, `platoon_options`, `regulars_out` | not a membership change | the bench drops pitchers; the orders are not touched ("`orders`, `lineup` and every aggregate are built before it is read and never see it"); this column reads the orders only. `hem_plus.py` has no commit after this one |
| `5f6293ed`, `419811bb` (2026-09-11) | `bullpen_export` (Ohtani's card; the eWAR frame) | not a membership change | `_active_mlbam_ids` and `MIN_CLUBS_FOR_ROSTER_FILTER` (28) are identical at `7cd5f572` and `a890f36a`; neither commit touches `hem_plus.py` |
| `2fbc82ac`, `609774aa`, `997a4b17`, `e328f62a`, `497d667f` | `leaderboard_vintages`: schema 4 and 5 columns and blocks; the park short window (`497d667f`) | not a construction change | `git log -L` on the builder returns `3eda89d7` only; the AST compare above |
| `dc648755`, `723848c6`, `419811bb` | `league_constants`; `fa_projection._woba_scale` (`dc648755`) | not a construction change | `_assemble_hitter` builds `woba_proj` from the rate components and the config's fixed `assembly.woba_weights`; the scale enters only `wraa_pa` and wRC+. `723848c6`: "No consumer reads the solved weights yet". `419811bb`: "pitchers and projected rates do not move" |
| `06fdabdc`, `0cffda7e`, `a0dc0065` | `hitter_export` URL move and copy | not a membership change | the `score_pool` call gains display arguments only |
| `57ebc163`, `6e82acd5`, `39347a6a`, `192c04e4`, `d79067a5`, `aabc8455`, `a890f36a` | docs, `betting_weather`, `run_monthly`, `DATA_SOURCES` | out of scope | none touches the paths above |

No board has been committed since `7cd5f572` (`git log -- data/hitter_leaderboards.json`:
`7cd5f572`, `944502c5`, `69fe0fca`, `52ffcb59`). The look record repeats this audit up
to the harness commit before any fit.

**Forward: X9, post-retrain, refresh.** Before the look:
- **X9.** The correction's event is a change to who enters `teams[].orders`. This
  section adds a code change to the three builder functions or the constant. Vintages
  written after either go to the X9 bucket.
- **Post-retrain.** The correction's event is step M. This section adds any code change
  to how `woba[0]` is computed: `fa_projection.rate_path`, `_assemble_hitter`,
  `assembly.woba_weights`, or which vets carry a hit path. Wiring `723848c6`'s solved
  weights into `_assemble_hitter` would be one. Vintages written after it go to the
  post-retrain bucket.
- **Refresh.** A nightly rebuild of the boards or the projections bundle on unchanged
  code. It is part of the construction and buckets nothing (the correction).

Each event is recorded here the same day. The clock does not restart.

**The candidate: one term on each scoring side's lambda, and nothing else.**

```
lam'_S = min(9.5, max(1.5, lam_S + c * x_S)),   x_S = z_lineup_strength_S - xbar_fit
```

- `lam_S` is the incumbent's per-side lambda, unrounded, after its home adjustment,
  `diff_shrink` and the [1.5, 9.5] clamp in `expected_runs`.
- `z_lineup_strength_S` is the scoring club's z from its pricing vintage, as
  `team_inputs_from_vintage` and `_assemble_team_inputs` produce it: (v - mu) / sd over
  the core-intersection clubs carrying a value, population sd, None when fewer than 2
  carry one.
- `xbar_fit` is the mean of z over the fit-side rows. There is no intercept, so `c`
  cannot absorb a level error (5h's addition 2, "no intercept").
- One free parameter, `c`, in runs per standard deviation. The opponent's value does
  not enter: the column is a batting nine.

**One seam prices both arms (to be built; nothing served calls it).** It takes the
incumbent's (`lam_home`, `lam_away`) for a game, adds `c * x` to each side, clamps, and
prices through `_score_joint` (Poisson, r None while `SERVE_RUN_DISPERSION` is False)
and `split_tie_atom` at the incumbent's fit-window `tie_home`, Platt at identity. The
incumbent arm is the same seam at c = 0, so the two arms share every rounding. Before any
number, the harness asserts that at c = 0 the seam's p_home equals
`game_probabilities(...)["p_home"]` to its 5 published places on every window game. That
check reads no outcome.

**Rows (to be built).** `_lambda_rows` returns bare (lam, runs) tuples and silently
skips games it cannot price, so x cannot be joined to its rows. A row builder returns
(`game_pk`, date, side, scoring org, lam, runs) per scoring side at the incumbent's
parameters, and counts what it skips.

**Runline and park, both arms alike.**
- **Runline.** `game_probabilities` resolves the served split only when `tie_home` is
  None, and every lab passes a fit-window `tie_home`. So the owner's 2026-09-11 reprice
  (`SERVE_RUNLINE_TIE_SPLIT` True since `497d667f`) reaches a lab only through
  `_lab_runline_split(fit_games)`, which `backtest._grade` threads at that commit. Both
  arms take `_lab_runline_split` of the anchored fit window. If the pinned commit lacks
  it, both take the whole-atom construction, and the record says which. The split never
  touches p_home.
- **Park.** `SERVE_ATH_PARK` (True since `497d667f`) reaches a vintage-priced game only
  through the record's own `parks_short_window` block. The 2026-09-07, 09-09 and 09-10
  records (schema 3 and 4) carry none, and neither do the anchored window's records.
  The 2026-09-13, 09-14 and 09-16 records (schema 5) carry one, with keys `ATH` and
  `TBR`. So the window's games ride two park terms for the flagged clubs' home games,
  and both kinds sit inside one `c` fit, on the fit side (games of 2026-09-08 to 09-13
  on records without the block, 09-14 to 09-16 on records with it) and on the graded
  side. This is not a leak: the block is dated with its record and both arms read it
  alike. The look reports graded and fit-side games on records with and without the
  block, per bucket.
- No xwOBA or `star_out` term enters either arm, whatever 5c-A or 5c-C records.

**The incumbent.** The first correction names "those of the ~2026-09-17 B3/B4 look, by
commit", or failing that "the served pricer at the commit that lands this correction".
That commit is `6e82acd5`. Its `betting_model.py` is `497d667f`'s: `MODEL_VERSION`
`betting_runs_v2`, `SERVE_ATH_PARK` True, `SERVE_RUNLINE_TIE_SPLIT` True,
`SERVE_RUN_DISPERSION` False, `SERVE_PROB_CALIBRATION` False, `SERVE_TOTAL_LEVEL`,
`SERVE_TOTAL_DISPERSION` and `SERVE_TOTAL_CALIBRATION` False. "Served pricer" here means
that code and those flags with the parameters the vintage mode fits on the anchored
window, never `build_context`'s live fit:
- `backtest._grade` in vintage mode: `fit_coefficients`, `_fit_tie_home`,
  `_solve_diff_shrink`, `_solve_home_adj`, alpha None, and every serve flag of that
  commit.
- It is never `build_context`'s parameters. 2026-09-11b says "The incumbent keeps every
  parameter as fitted on the anchored window". `build_context` fits on every completed
  game, graded ones included, with season-to-date boards (R5-F1).
- **The anchored window** is every vintage-gradable game dated before 2026-08-01. That
  split date governs. On the 2026-09-11 artifact it holds 305 games, 2026-07-06 to
  07-31, with b0 4.345387, b1 -0.037205, b2 -0.096479, b3 0.594771, b4 0.149360,
  `diff_shrink` 1.28 and home adjustment -0.0443 (7e-B). The look record prints
  `_vintage_cut_index`'s own cut at the look run beside it. If the two differ it says
  so, and 2026-08-01 still governs.
- **Inline, with parity.** `backtest._grade` is a closure inside `backtest()`, and
  `backtest()` pops `_per_game_markets` before it returns. So the harness re-solves the
  incumbent inline, as `_total_level_split` and `_total_dispersion_split` do. Before any
  number: coefficients, `diff_shrink`, home adjustment, tie rate, split date and n_fit
  must equal the artifact's `vintage` block at the pinned commit, to its rounding.
- **The two branches, read now.** The ~2026-09-17 look is not being held: 5c-A's
  2026-09-16 revision moves the xwOBA pair to 2026-09-28, and 5c-C's draft moves
  `star_out` into this run. The correction's first branch is read as the first 5c
  B3/B4 look recorded on or before 2026-10-04, if any: its incumbent and harness
  commits are the ones named. If none is recorded by 2026-10-04, the incumbent is the
  pricer at `6e82acd5` as read above. In both branches the dated note pins everything
  directly, so nothing is left to a chain.

**The dated note, filed before any number on this column.** It pins directly:
- this look's harness commit, after it passes the identity check and both parity checks
  (the second is leg 1's, below), and the incumbent commit (`6e82acd5`, or the first
  recorded 5c look's), with `MODEL_VERSION` and the state of every serve flag at each;
- the anchored window as its `game_pk` set, and the incumbent's parameters;
- the store: host, absolute path, and a SHA-256 over the sorted (file name, file
  SHA-256) pairs of every file the run may read;
- the split date M, from dates and buckets alone;
- the counts step 1 reads.

The harness that runs this look is later than any earlier 5c harness in both branches,
because the seam, the row builder, the residual fit, the twins, the season-end version
and the stamp are all to be built. Until the first candidate number exists, the harness
may be fixed, and the note names the commit that ran.

**The look: once, first day 2026-10-05, last day 2026-10-31.**
- The read runs on 2026-10-05, or the first day after it on which the pinned harness
  runs under the same window, code and rules. A slipped read is still the one look.
- If it has not run by 2026-10-31, the look records INDETERMINATE, 2026 closes for the
  column, and the record says why. That matches 7e-D's close and 5d-C's date.
- There is no second read on 2026 data. A 2027 test is a new registration under N9.

**The store.** The one every count here and in both corrections reads:
`prospect-tracker/.cache/leaderboard_vintages/` on host NOAH-PC, the store R5-F3
measured. The deploy box's store is not read for this look, and no file from it is
copied in. A copied file would pass the present-night test and let the look choose its
nights by coverage.

**Estimand.** On regular-season window games: does adding `c * x_S` to both per-side
lambdas lower paired per-game moneyline Brier on the graded side, without worsening log
loss or the total? `c` is fitted on the incumbent's residuals before the calendar
midpoint; the graded side is on or after it.
- The moneyline decides, in rule 4's 11b form. Here "11b form" means its two criteria
  only: 2026-09-11b replaces 11b's 0.6/0.7/0.8 grid with one calendar-midpoint split.
- The total is a guard (criterion 4). The runline is reported only.

**The graded window and its buckets.** A game is in the window when:
- `lv.as_of(date)` prices it on a vintage dated 2026-09-07 to 2026-10-04;
- it is dated before 2026-10-05;
- it is `gameType` R (O25, closed at its default).

Each window game falls in exactly one bucket, checked in this order:
1. priced on a record that is not a present night (2026-09-11b point 3): ungraded;
2. "post-retrain": priced on a vintage written after step M or after a `woba[0]` code
   change, whenever it lands: ungraded;
3. an X9 bucket: priced on a vintage written after an X9 event: ungraded;
4. "pre-change membership": where the stamp exists (in the record, or read from a
   committed board, below), the board reads `roster_filter.applied` false, or either
   club is on `roster_filter_skipped`: ungraded;
5. "stamp missing": priced on a vintage dated 2026-09-19 or later whose
   `lineup_strength` basis carries no roster-filter stamp and whose board is not
   committed: ungraded;
6. stated null: either club carries no value: ungraded;
7. dated value: both clubs carry a value. This is the graded n. Inside it, two counts
   are reported and never chosen at the look:
   - "filter flag unrecorded": priced on the 2026-09-07, 09-09 or 09-10 vintage, the
     nights before `6e82acd5`. The correction grades them as post-change, and this
     section cannot amend that;
   - "stamp late": priced on an unstamped vintage dated 2026-09-12 to 2026-09-18 (on
     disk: 09-13, 09-14, 09-16). They were captured after the correction promised the
     stamp and before this section could bind. They grade, under their own count.

**The roster-filter stamp, dated now.** The correction promised it "from the first
vintage after this correction lands". It is not built: `leaderboard_vintages.py` has no
`roster_filter` reference, and the 09-13, 09-14 and 09-16 basis strings are the
unchanged text. The rule from here:
- The stamp lands in the commit that lands this section, or the next code commit, so
  the 2026-09-19 vintage carries it at the latest. Every later vintage without it goes
  to bucket 5, ungraded. Delay costs graded games, never adds them.
- Where a board commit exists whose `as_of` equals the vintage's
  `sources.hitter_leaderboards.json.as_of`, that board's `roster_filter` block is the
  stamp, read from git and labelled "stamped from git" (`7cd5f572` is the precedent for
  2026-09-07). No board has been committed since `7cd5f572`, so today this reaches
  2026-09-07 alone, and there it only agrees with the correction's reading.
- The three "stamp late" nights are graded rather than dropped because dropping them
  would put the fit side at 80 games (09-08 to 09-13), under the 100 floor, by a bucket
  rule written after those nights were captured. Choosing INDETERMINATE that way would
  be choosing on the calendar after the fact. The choice is recorded here, before any
  number, with the count.
- Recorded now, as flags read on 2026-09-16 from the live board (`as_of` 2026-09-16,
  `generated_at` 2026-09-16): `roster_filter.applied` true, `n_active_roster_ids` 840,
  `n_dropped_from_constructions` 235, no club with `roster_filter_skipped`. The
  2026-09-16 vintage (captured 15:16:50Z) reduced a board stamped `as_of` 2026-09-16.
  As with 2026-09-07, this is consistent with a filtered night, not proof of one.

Kept hitters with no readable mlbam bucket no game: the correction makes them a stamp
count only, and the look reports that count per stamped night. "Predates the column"
cannot occur, because every window vintage is schema 3 or later. A game the incumbent
cannot price is outside every bucket and is counted. No ungraded game is scored or
enters as a zero difference.

**Split and fit (the 2026-09-11b 5h-A form).**
- Let F and L be the first and last dated-value game dates. The split date is
  M = F + floor((L - F) / 2) calendar days.
- Dated-value games before M are the fit side; games on or after M are graded.
- M is computed from dates and buckets alone. It is written into the look record
  before any fit and never moved.
- `c` = sum(x_S * (runs_S - lam_S)) / sum(x_S^2), over both scoring sides of every
  fit-side game, on the row builder's rows.
- Every graded game falls after 2026-08-01, in the vintage eval half, so rule 4 reads
  as written.

**The statistic, written out.** For each graded game i, d_i is the incumbent's loss
minus the candidate's loss, so positive means the candidate is better. With n graded
games:
- mean = sum(d_i) / n;
- sd = sqrt(sum((d_i - mean)^2) / (n - 1)), the n-1 divisor;
- se = sd / sqrt(n); t = mean / se; lb95 = mean - 1.645 se.
- If sd = 0 the criterion cannot run (verdict row 3). Nothing escapes to se = 0.

`_paired_delta` at HEAD uses the n divisor and returns t None on sd = 0. Plan 4.2 repair
3 moves the module to the n-1 divisor with a zero-variance refusal. The written form
governs whichever lands: the harness computes it inline, and before any number asserts
on a fixture that `_paired_delta` at the pinned commit agrees to its rounding, or the
note says the helper differs and the inline form ran. n-1 is chosen because it is the
plan's direction, 5c-C's form, and the smaller t.

**Leg 2, the vintage leg. All four required, on the graded games.** Every delta is
incumbent loss minus candidate loss per game, so positive means the candidate is better.
1. **Moneyline Brier**, the statistic above: mean > 0 and t >= `Z_95_ONE_SIDED` (1.645).
   y is home runs greater than away runs, as `_grade` scores it.
2. **Moneyline log loss** (`_logloss`, eps 1e-9), same statistic: mean >= 0 on the point
   estimate.
3. **Sign.** `c` > 0: a stronger projected nine scores more runs. A wrong sign fails the
   candidate whatever 1 and 2 read. This is 5g criterion 3's form; 7e-B's wrong-sign
   own-offense fit on 610 rows is why.
4. **Total, not worse.** Paired absolute error |home runs + away runs - (lam_home +
   lam_away)| on unrounded lambdas. That sum is the `fair_total` `game_probabilities`
   builds before any total level, and a lab gets none. Mean >= 0 on the point estimate.
   The term moves both lambdas, so a flip moves the total. The total is ledger-closed
   with a disclosed Over lean (plan 4.2), and 5j's Leg O and 5c-A carry the same guard.

The runline is reported only, never a criterion, on both sides: the per-game sum of the
two tails' log losses (home margin >= 2, home margin <= -2; the 11a amendment,
`RUNLINE_SIDE_AMENDMENT` "both"), and each tail's Brier. It is 11a's form, which needs
no posted price, not 7e-A's, which does.

**Twin A, rule 3's permuted twin (the chance control).** It calibrates chance. It does
not separate offense level. Permuting across clubs destroys the column's offense level
along with its availability content, so a column that was only offense level would beat
it too. And offense level stays in the residual `c` is fitted on: the incumbent's
own-offense term is b1 -0.037205, pinned at 0 under sign constraints (7e-B).
- Replicate k, for k = 0 to 199, uses `random.Random(k)` (to be built; no betting code
  seeds this way today).
- Rule 3's "within each date" is read as within each pricing vintage. z is standardized
  within the vintage, and one vintage's value prices every game it covers: the
  2026-09-07 vintage prices the 09-08 and 09-09 games, and both get one permuted value.
- Walk the pricing vintages that price at least one dated-value game, in ascending
  `vintage_date`. In each, shuffle the stored values among the clubs carrying one,
  listed in canonical org-code order. mu and sd do not change, so z permutes exactly.
  The buckets fix the vintage set before any fit.
- Refit `c` with its own `xbar_fit` on the same fit side, and grade the same graded
  side.

**Twin B, the within-club twin (the availability control).** It keeps each club's level
and destroys only the timing, which is the B4 claim.
- Replicate k, for k = 0 to 199, uses `random.Random(200 + k)`.
- Within each half, fit among fit and graded among graded, so no twin fit reads a
  graded-side value. For each club in canonical org-code order, shuffle its z across
  its own dated-value club-games, listed in (date, `game_pk`) order.
- Refit and grade as above.
- A club whose value never moves within a half is unchanged by twin B. That is the null
  working, and the count of such clubs per half is reported.

**The bar, for each twin.** The candidate's criterion 1 mean must be strictly greater
than at least 190 of the 200 twin means, that is, greater than the 190th smallest. Ties
count against it. This is the 95th-percentile bar of 5f and 5h-A, as an order statistic.

**Reported, never qualifying: the `z_off` arm.** The same fit on the same rows, with
the scoring club's centered `z_off` from the same record in place of the column. It asks
whether the column beats a refit of offense level. The column may simply be a better
offense level than Offense+, since it reads projections and tonight's nine. That is not
what B4 registered, and twin B tests the availability claim directly. So this arm is
reported and not required, with the correlation of `z_lineup_strength` and `z_off`.

**Leg 1, the contaminated-forward screen (rule 4). It can only fail the candidate.**
- **The column (to be built)** is its season-end reading. Each club takes its value
  from the newest present vintage dated on or before 2026-09-27 where it carries a value
  outside every ungraded bucket. That means the board reads `applied` true (or the
  night is "filter flag unrecorded" or "stamp late"), the club is not on
  `roster_filter_skipped`, and the vintage precedes step M, any `woba[0]` code change
  and any X9 event. A club with no such vintage is excluded and counted, with every
  game it plays.
- That value is applied to every 2026 regular-season game of the club. It is the analog
  of the season-to-date boards the contaminated mode reads. z is standardized once over
  the clubs' season-end values (population sd, sd 0 read as 1.0, `_mean_sd`'s form),
  then centered on the forward fit-half rows.
- **The incumbent** is `backtest()`'s contaminated `forward` fit at the pinned commit,
  split at `dates[int(len(dates) * 0.7)]` over the completed dates. On the 2026-09-11
  artifact that is 2026-07-22, with 682 forward games. The cut moves with the season's
  dates: about 0.3 x 2,430 = 729 forward games at the look run if games spread evenly.
  It is re-solved inline, with a parity check against the artifact's `forward` block and
  top-level `split_date`. Its fit-half lambdas come from the row builder. Today only
  eval-half lambdas exist, and only inside `_grade`.
- `c1` is fitted by the same residual least squares on the forward fit half.
- **Leg 1 fires**, and the candidate fails, when the forward-eval paired Brier mean is
  <= 0 on the point estimate, or when `c1` <= 0. Leaked features that show no effect in
  the right direction leave a dated feature nothing to find.
- It is labelled contaminated. It runs in the look run only, on or after 2026-10-05.

**Order of operations.**
0. Before any number: the c = 0 identity check, both parity checks, the `_paired_delta`
   fixture check, then the dated note.
1. Counts, on the pinned commit and the named store:
   - present nights from 2026-09-07 to 2026-10-04: at least 14 of 28 (2026-09-11b
     point 2);
   - dated-value fit-side games: at least `VINTAGE_MIN_FIT_GAMES` (100);
   - dated-value graded games: at least `VINTAGE_MIN_EVAL_GAMES` (50).

   If any count fails, nothing is fitted, scored or twinned, and leg 1 does not run.
2. Fit `c`. It cannot run when sum(x_S^2) = 0, or when a pricing vintage has fewer than
   2 clubs with a value.
3. Criteria 1 to 4, both twins and leg 1, in one run. Everything that runs is reported.

**The verdict. The first row that matches wins.**

| Order | Verdict | When |
|---|---|---|
| 1 | INDETERMINATE | the look has not run by 2026-10-31, or step 1 or step 2 fails. Nothing else is computed |
| 2 | FAIL | any of criteria 1 to 4 fails, either twin is not beaten, or leg 1 fires. A failed requirement is a FAIL even when another component could not run |
| 3 | INDETERMINATE | nothing failed, but a criterion (sd = 0), a twin or leg 1 could not run |
| 4 | PASS | every floor met, criteria 1 to 4 hold, both twins beaten, leg 1 ran and is silent |

**No second read.** No verdict permits a second 2026 read. A harness defect found
after the run makes the look INDETERMINATE, recorded with the defect named: the file,
the function and the reported numbers it touched. The original numbers stay beside it,
labelled defective. Nothing is recomputed on 2026 outcomes. A defect can move a PASS or a
FAIL to INDETERMINATE, never to PASS. Before the first candidate number the harness may
be fixed, and the dated note names the commit that ran.

**Multiplicity and stacking.** Four 5c candidates read the same incumbent family on
overlapping 2026 games: the xwOBA pair (5c-A, 2026-09-28), `star_out` (5c-C, this run)
and this column. Each faces an unadjusted one-sided t >= 1.645, by design:
- Rule 4 sets that bar per candidate. A Holm family in plan 2.3's form would raise the
  first-ranked bar, which amends rule 4's threshold, and this section does not do that.
- The cost is stated: the chance that at least one of four null candidates passes
  criterion 1 is at most 0.20 (Bonferroni); for the two B4 columns read in this run, at
  most 0.10 (0.0975 if independent).
- No candidate's term ever enters another's arms. Serving two terms at once would be a
  third, unregistered candidate, a two-term fit, which needs its own section under
  rule 1. A PASS here and a PASS on `star_out` give two separate flag proposals.

**Known pre-existing readers of the same orders, each a named exception.** The embargo
("no posted-lineup, active-roster or lineup-strength variant is related to an outcome
or a price") is read as the correction's disqualification rule: a number relating such a
variant to a game outcome or a market price. These pre-existing relations are not that,
and are listed in 7e-D's form. A change to any of their constructions is a new instance,
to be listed here the same day.

| # | Item | Relates | Why it is not a variant of this column |
|---|---|---|---|
| 1 | `betting_export.props_fair_lines`: reads `teams[].orders.vr` / `.vl` (the roster-filtered nine since `7cd5f572`) nightly into the model-only props fair lines, the order picked by the opposing probable's hand | an order to a served fair line, no book comparison | reads no `woba[0]`, averages nothing over the nine, joins no outcome and no market price; plan 4.1 already records that the constructed nine reaches the props fair lines and the dark vintage columns and nothing else |
| 2 | `dfs_export`: `fantasy_schedule.fetch_lineups(day)` reads the posted card; a posted bat's start rate becomes 1.0 and a club's posted status is stamped on the card | a posted card to a served DFS projection | the StatsAPI card, not the constructed nine; no `woba[0]`; no outcome, no price |
| 3 | `hem_plus.team_offense` and the site's lineup cards (`77174943`): the orders, bench and per-hand HEM+ published on the hitter board | an order to a served page | a display of the construction; computes no team value from projections; no outcome, no price |
| 4 | `betting_model._feature_basis`: counts each dark column's status (populated, null stated, predates the column) per graded game, nightly | a column's presence to a count | counts, no value, no fit |
| 5 | The 5j capture job `tools/betting_lineup_job.py` (BUILT at `78c22d7a`; it did not exist at `a890f36a`) | a posted card to a capture row | computes nothing; 5j's first look is 2027 and its contaminated screen waits for this look (plan 4.1) |

**Coverage on 2026-09-11 (counts, no value; as read at 23:45Z that day).**
- Post-change nights on disk:
  - 2026-09-07, 09-09 and 09-10, each live, captured on its own date,
    `feature_basis` n 30, 30 of 30 clubs non-null, no `parks_short_window` block;
  - 2026-09-08 missing;
  - no `2026-09-11.json` at 23:45Z.
- Window games so far: 35, all dated value, 0 stated null, all "filter flag
  unrecorded", all on a record without `parks_short_window`.
  - 2026-09-08: 15, on the 2026-09-07 vintage, `vintage_age_days` 1;
  - 2026-09-09: 15, on the same vintage, age 2;
  - 2026-09-10: 5, on the 2026-09-09 vintage, age 1 (all 5 of the day's regular-season
    games in `lineups_2026-09-10_R.json`).
- Outside the window: 246 dated-value games dated 2026-08-21 to 09-07 sit in the
  pre-change membership bucket.
- The ceiling:
  - 2,430 regular-season games (30 x 162 / 2);
  - 2,165 completed games in the cache are dated on or before 2026-09-07;
  - so at most 265 remain for the window.
- `2026-09-11_2026-09-17_R.json` holds 94 regular-season games 2026-09-11 to 09-17: 15,
  15, 15, 10, 15, 15 and 9 by date.

**Addendum, 2026-09-16 (counts, no value; read at 18:58Z, script `rev3_counts.py`).**
- Nights present in the window so far: 2026-09-07, 09-09, 09-10, 09-13, 09-14, 09-16,
  6 of the first 10. Missing: 09-08, 09-11, 09-12, 09-15; none can be written late
  (2026-09-11b point 5). The 2026-09-11 file the first block waited on was never
  written.
- The three new nights are schema 5, live, captured on their own date (09-13 20:23:45Z,
  09-14 17:30:11Z, 09-16 15:16:50Z), `feature_basis` n 30, 30 of 30 clubs non-null,
  `parks_short_window` present with keys `ATH` and `TBR`, `sources` hitter `as_of` on
  the same date, and no roster-filter stamp in the basis.
- `completed_games.json`: 2,270 games, max date 2026-09-15; 105 dated 2026-09-08 to
  09-15 (15, 15, 5, 15, 15, 15, 10, 15), all dated value by construction; 160 remain to
  2,430. 2026-09-16's 15 scheduled games are pending.
- Pricing so far (`as_of`: the newest vintage whose `covers_through` is before the
  game date): 09-08 and 09-09 games on the 09-07 vintage (30); 09-10 on 09-09 (5);
  09-11, 09-12 and 09-13 on 09-10 (45); 09-14 on 09-13 (10); 09-15 and 09-16 on 09-14
  (30); 09-17 on 09-16 (9, graded side). So 80 fit-side games (09-08 to 09-13) ride
  records without `parks_short_window` and up to 40 (09-14 to 09-16) ride records with
  it. The same 80 are "filter flag unrecorded"; the 40 plus 09-17's 9 are "stamp late".
- Schedule (`2026-09-14_2026-09-20_R.json`, `2026-09-16_2026-09-22_R.json`): 09-17 9,
  09-18 15, 09-19 15, 09-20 15, 09-21 3, 09-22 16 regular-season games.

**The split, as arithmetic on those counts.**
- With F = 2026-09-08 and L = 2026-09-27, M = 2026-09-17.
- The fit side, 2026-09-08 to 09-16, holds at most 105 + 15 = 120 games; 105 are already
  in the cache, so the 100 floor is met on counts unless a bucket removes 6 or more of
  them. The graded side, 09-17 to 09-27, holds at most 265 - 120 = 145.
- This refines the correction's "about 130 a half": the midpoint does not halve the
  games (2026-09-10 carried 5, 09-14 carried 10, 09-17 carries 9, 09-21 carries 3).
- The fit side clears the 100 floor by at most 20 games, about 1.5 slates at 13.1 a
  date. Any mix that removes more than 20 fit-side games makes the look INDETERMINATE:
  - fit-side games in any ungraded bucket (not a present night, post-retrain, X9,
    pre-change membership, stamp missing, stated null);
  - postponements from 2026-09-08 to 09-16 not made up inside that span. One made up on
    or after 09-17 moves to the graded side.
- An ungraded bucket that ends the dated-value dates before 2026-09-27 moves L, and so
  M, earlier and shrinks the fit side further. At L = 2026-09-25, M is 2026-09-16 and
  the fit side holds at most 105.

**The night floor, as arithmetic (2026-09-16).** Of the 28 nights, 6 are present and 4
are missing. The floor needs 8 of the remaining 18 (2026-09-17 to 10-04). Whether the
nightly writes vintages after the 2026-09-27 season end is unverified. If it does not,
the floor needs 8 of the 11 nights 2026-09-17 to 09-27, which is 73% uptime. At the
window's own rate (6 of 10) those 11 nights yield about 6.6; at the schema-3 rate (16 of
24, the 2026-09-11b table) about 7.3. On that branch the floor misses at either rate,
and the look is INDETERMINATE before any number. That is the correction's rule and the
operational fault plan I2 records, not evidence about the candidate.

**Power, as arithmetic on counts.** Suppose the candidate's probabilities were exactly
right. Its expected paired-Brier t is then about sqrt(n) x RMS of its p_home shift, the
arithmetic 5f and plan 4.1's 5j summary use. At the graded ceiling n = 145 (sqrt
12.04), with the chance of t >= 1.645 from a normal approximation:

| RMS shift in p_home | expected t | chance of t >= 1.645 |
|---|---|---|
| 0.01 | 0.12 | 0.064 |
| 0.02 | 0.24 | 0.080 |
| 0.046 (plan 4.1's resting star on an even game) | 0.55 | 0.138 |
| 0.137 | 1.645 | 0.50 |
| 0.207 | 2.49 | 0.80 |

These chances are upper bounds, because they ignore:
- the noise in `c`: one standard error is about 0.21 runs per standard deviation. That
  is 3.18 runs of per-side residual sd (11a's 10.4889 run variance less 0.3755 of
  lambda variance) over about 240 fit-side rows;
- criteria 2 to 4, and both twins.

**The pre-registered expectation: FAIL or INDETERMINATE, for power.** A FAIL at this n
is not evidence that the column carries nothing. A PASS would need a shift several
times the 4.6-point resting-star shift plan 4.1 records.

**No power precondition.** 5f and 5c-A stop at UNDERPOWERED when sqrt(n) x RMS is
below 1.645. This section adds no such verdict. Its INDETERMINATE conditions are
readings of the correction's "a look that cannot run", and a power precondition is not
one: it would be a new verdict that stops the graded read. The look runs once, so
reading it costs no later look. Two numbers are reported beside the verdict instead,
neither of which decides:
- the RMS of candidate minus incumbent p_home over the graded games, from the features
  and the outcome-fitted `c`;
- sqrt(n) times that RMS.

**Reported whichever way it lands.**
- The dated note: harness and incumbent commits, `MODEL_VERSION`, flag states, store
  host, path and hash, M, the step 1 counts.
- The incumbent: its parameters, the governing split 2026-08-01 and
  `_vintage_cut_index`'s cut beside it, both parity results, the identity check, the
  `_paired_delta` fixture result, and which runline construction both arms used.
- The construction audit to the harness commit.
- The clock start, the floor, and the present and missing nights, with the missing
  dates listed.
- The 11 pre-change nights, listed, and their bucket counts.
- The graded eval games by pricing vintage, in every bucket:
  - "pre-change membership" split into board `applied` false and skipped club;
  - "filter flag unrecorded" and "stamp late" within dated value, and "stamp missing";
  - the per-night stamp fields, including the unreadable-mlbam count, and which nights
    were stamped in the record, from git, or not at all;
  - games on a record with and without `parks_short_window`, fit side and graded.
- Of the dated-value games, the count on a vintage 2 or more days old, and their
  game-weighted `vintage_age_days`.
- F, L, M, and the fit and graded n.
- `c`, its standard error, and `xbar_fit`.
- Criteria 1 to 4: mean, sd, t and lb95.
- Each twin: its 200 means, the 190th smallest, and the candidate's rank. For twin B,
  the clubs per half whose value never moves.
- The `z_off` arm's slope and mean.
- Leg 1's numbers, labelled contaminated, and its excluded clubs and games.
- The runline, both tails.
- The correlation of `z_lineup_strength` with `z_off` over fit-side and graded rows,
  from features only.
- The RMS and sqrt(n) x RMS above.
- Whether step M or a `woba[0]` code change has landed.

**What a pass would change.**
- On the look day, nothing served changes.
- A PASS licenses a flag proposal, not a flip. The flag would be
  `SERVE_LINEUP_STRENGTH` (to be built, default False, in the `SERVE_RUN_DISPERSION`
  idiom). The owner flips it in one commit with a `MODEL_VERSION` bump and a tripwire
  test, so the ledgers never pool two pricers.
- The served `c` and `xbar_fit` are the look's fit-side values, frozen as literals
  (X4). They are never refit on the 2026 graded games, since that would reuse the
  graded outcomes.
- Serving needs a live builder in `team_inputs_detail` that reads the same
  construction. Today that function sets the column None.
- A flip would move `lam_home` and `lam_away` at every game by `c` times each club's
  centered z. So the moneyline, the runline and the total all move, and the Pick of the
  Day can change.
- The proposal must state two things:
  - `c` was fitted on the graded vintage pricer's residual, so serving it on the
    `build_context` pricer serves a pair never graded together (O14, 7e-D);
  - after step M the column reads a retrained bundle, a construction this look did not
    grade.

  The owner decides both.
- A PASS here and a PASS on `star_out` give two separate flag proposals, never a joint
  one.
- A FAIL or INDETERMINATE changes nothing:
  - the column stays dark and keeps accruing;
  - 2026 is closed for it;
  - a 2027 test is a new registration under N9.

**Before the look, counts only, and the exclusion that makes it so.** No fit, paired
score, twin or leg 1 is computed for this column before 2026-10-05. `lineup_strength`
sits in `betting_model.DARK3_TEAM_COLUMNS`, the tuple a generic candidate loop would
iterate, so:
- any harness that runs on the real store before 2026-10-05 (the 2026-09-28 run of
  5c-A; a ~2026-09-17 run if one is held) carries, in the same commit as the harness and
  before its first run, an exclusion of this column from its candidate list and a test
  pinning it;
- that run's record lists its candidate columns. A run whose record does not list them
  is treated as having computed on this column, and the candidate is disqualified;
- such a run reports the correction's three counts for this column (the nights on each
  side, the graded eval games per bucket, the post-change nights whose filter state the
  record cannot show). If no such run is held, the look record reports them first.

**Disqualification.** Any of these before the 2026-10-05 look disqualifies the
candidate under rule 1:
- any number relating `lineup_strength` to a game outcome or a price, whether either
  side of the change or a variant;
- the variants are the embargoed list: posted-lineup, active-roster or lineup-strength
  variants, another roster source, another projections input, slot-PA weights, 5j's
  delta and 5j's contaminated screen; the named exceptions above are not variants;
- any fit, score or twin of this column in any run before 2026-10-05, including a run
  whose record lists no candidate columns.

The pre-change side is never related to an outcome on its own, before or after the
look.

**To be built before the look.** Named so the run cannot improvise:
- the harness arm, with a date refusal (refuse before 2026-10-05 and after 2026-10-31,
  fixed dates) and an outcome-field refusal. `tools/ph_gate.check_look_date` and
  `refuse_outcome_fields` are the form; `check_look_date` itself refuses every date on
  or before the regular-season end of a season at or after `FIRST_LOOK_SEASON` (2027),
  so it cannot be reused for this look;
- the exclusion of this column from any earlier harness's candidate list, with its
  test, in that harness's own commit;
- the row builder, the lambda-override seam, the c = 0 identity check and the inline
  incumbent with both parity checks;
- the residual fit, the written statistic, its `_paired_delta` fixture check, both
  twins with their seeds, and the `z_off` arm;
- the season-end contaminated version, and the forward fit-half rows;
- the game-level both-clubs count and the bucket report in `_feature_basis`;
- the roster-filter stamp, dated above, and the git read of a committed board's
  `roster_filter` block;
- the dated note and the look record, carrying M before any fit;
- the `snapshot` refusal for a past `on_date`.

**Extensions.** Each extends the record and is stated as an extension. None can make a
pass easier.
1. **The incumbent reading**: code at the pinned commit, parameters as the vintage mode
   fits them on the anchored window, split 2026-08-01 fixed by date. 2026-09-11b's "keeps
   every parameter as fitted on the anchored window" requires it, and `build_context`'s
   fit has seen every graded game (R5-F1).
2. **The pin in the dated note**: harness commit, incumbent commit, flags, window,
   parameters, store and M are pinned there directly, because the 09-17 look the
   correction chains through is not being held. The correction's first branch is read
   as the first 5c B3/B4 look recorded on or before 2026-10-04, if any.
3. **The store**: one store, named now, never merged, so nights cannot be chosen by
   coverage (R5-F3).
4. **Bucket 1** covers any record that is not a present night. 2026-09-11b point 3 names
   backfilled records. A live file written after D+1 (which point 5 forbids) fails the
   same test, and a record the night floor does not count must not price a graded game.
5. **Post-retrain** covers a `woba[0]` code change as well as step M. It moves the
   joined input as step M does.
6. **X9** covers a code change to the builder functions or the constant as well as
   membership. It changes the construction as much.
7. **floor** settles the half-day midpoint 2026-09-11b left open.
8. **INDETERMINATE readings.** The correction's "a fit or twin that cannot run" is read
   to cover leg 1 and a zero-variance criterion too, since rule 4 serves nothing without
   them. A defect found after the run moves a verdict only to INDETERMINATE, and
   nothing is recomputed. A look not run by 2026-10-31 is INDETERMINATE.
9. **The stamp rule.** The correction promised the stamp and dated nothing. This section
   dates it (2026-09-19), adds the "stamp missing" ungraded bucket for later unstamped
   nights, the git read of a committed board, and the "stamp late" count for the three
   unstamped nights already on disk, which stay graded for the reason given.
10. **The statistic.** The n-1 divisor and the zero-variance refusal, written out, where
    `_paired_delta` at HEAD uses n and escapes to t None.
11. **The exclusion rule.** An earlier harness must carry the exclusion in its own
    commit and list its candidates, or it counts as a computation on this column.
12. **The named exceptions.** Five pre-existing readers of the orders, listed so the
    embargo does not read as disqualifying the candidate nightly.
13. **The section's own additions**: criteria 3 and 4, twin B, the 190-of-200 bar for
    both twins, leg 1's construction and its firing rule, the verdict order and the
    last day. Rule 4 leaves leg 1's form to the section; the rest can only make passing
    harder.

**Not reopened.** No criterion, control or threshold in rules 1 to 4, or in the two
2026-09-11 corrections, is amended. The additions above are this section's own. Their
precedents are 5g (sign), 5h-A and 5f (the twin bar), 5c-C (the within-club twin and the
n-1 divisor), 5c-A and plan 4.1 (the total guard), 7e-D (the named exceptions and the
last day) and 5c-A (the exclusion before an earlier run).

#### The dated note (filed 2026-10-08, before any number on `lineup_strength` or `star_out`; 5c-C chains to it)

This is the note the section above requires, filed before any fit, paired score, twin or
leg 1 on either B4 column. The full pin is `docs/betting-b4-look/note_2026-10-08.json`
(the store's per-file SHA-256 list, the anchored window's 305 `game_pk` values, both
columns' counts and the step 0 receipts); the lines below are what it holds.

**The slip, disclosed.** The look did not run on 2026-10-05. The owner's E5 waiver
(EPOCH-Q1, `DECISIONS_FOR_OWNER.md` 'ANSWERED 2026-09-30 (AskUserQuestion), Part 8 batch 1
(the fWAR label epoch)', filed as the 2026-10-02 amendment in
`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 3) moved both B4 looks after the fWAR
label epoch's step Z, which part 9 records on 2026-10-03. The look code was built on
2026-10-07 at `b9bf49c8`; 2026-10-07 is a registered look date (5d's earliest look, the RE
family's first read day), so the note and the look wait for 2026-10-08, inside the span
that ends 2026-10-31.

**The harness.** `tools/b4_availability_look.py` at `b9bf49c8`, unchanged at HEAD
(`git diff b9bf49c8 HEAD` on it is empty). Its 39 fixture tests passed again on 2026-10-08,
including the reporting path fed rows with None values. Step 0 ran on 2026-10-08 and
passed:
- the c = 0 identity check: the seam's `p_home` equals `game_probabilities(...)["p_home"]`
  to 5 places on all 290 window games of the two columns, 0 mismatches, 0 skipped;
- the vintage parity: b0 4.345387, b1 -0.037205, b2 -0.096479, b3 0.594771, b4 0.149360,
  `diff_shrink` 1.28, home adjustment -0.0443, tie rate 0.4921, split date 2026-08-01 and
  n_fit 305, each equal to the `vintage` block of `data/betting_model_eval.json` at
  `6e82acd5`;
- the forward parity (leg 1's contaminated incumbent): split 2026-08-03, n 747, b0 to b4,
  `diff_shrink` 0.82, home adjustment 0.1999 and tie rate 0.4895, each equal to the
  artifact on disk (`generated_at` 2026-10-02T16:15:12Z);
- the `_paired_delta` fixture check: the helper at the pinned commit uses the n divisor
  (fixture sd 0.029814 against 0.032660), so it differs and the inline n-1 form runs, as
  both sections write it.

**The incumbent.** The vintage-mode pricer at `6e82acd5`, loaded from git into the look
process (blobs `b0528749` for `betting_model.py`, `2a6cf96d` for
`leaderboard_vintages.py`), never HEAD's pricer and never `build_context`'s fit. No 5c
B3/B4 look was recorded on or before 2026-10-04 (5c-A closed without look code at
`239ef253`), so the second branch binds. `MODEL_VERSION` is `betting_runs_v2` at
`6e82acd5` and at `b9bf49c8`, and every serve flag reads the same at both:
`SERVE_ATH_PARK` True, `SERVE_RUNLINE_TIE_SPLIT` True, `SERVE_RUN_DISPERSION` False,
`SERVE_PROB_CALIBRATION` False, `SERVE_RIDGE_FIT` False, `SERVE_TOTAL_LEVEL` False,
`SERVE_TOTAL_DISPERSION` False, `SERVE_TOTAL_CALIBRATION` False. `SERVE_LINEUP_STRENGTH`
and `SERVE_STAR_OUT` exist at neither commit. Both arms take `_lab_runline_split` of the
anchored fit window.

**The anchored window.** 305 vintage-gradable games dated before 2026-08-01;
`_vintage_cut_index`'s cut at the run is 2026-08-01, the same date. The `game_pk` set's
SHA-256 is `3dba75d5d921ef931428bc40068769cff9ad7ea7b7796d9f36f157d3f1cfd719`; the set
itself is in the JSON.

**The store.** Host NOAH-PC, `prospect-tracker/.cache/leaderboard_vintages/`, 59 files,
SHA-256 over the sorted (file name, file SHA-256) pairs
`f8d6ea177705fd202c319d9875a32cf3aa8ebc39673cfb7f2bb89dd3967c1b6c`. Every vintage that
prices a window game is live and its file mtime equals its `captured_at` (lag 0.0 h), and
no file was copied in from the box. One fact is
disclosed: `2026-10-08.json` was written at 13:34:08 local on the note day, during the
counts read, by a process outside this lane that reaches the main tree's `.cache` through
a worktree junction. It is a live record, it prices no window game, and the hash covers it.

**5c-B, `lineup_strength`: the step 1 counts (read 2026-10-07 and again 2026-10-08,
identical).**
- Present nights 2026-09-07 to 2026-10-04: 21 of 28 (floor 14). Missing: 2026-09-08,
  09-11, 09-12, 09-15, 09-20, 09-22 and 09-25.
- F 2026-09-08, L 2026-09-27, **M 2026-09-17**. Dated-value fit side 120 games (floor 100),
  graded 83 (floor 50). Step 1 passes on counts.
- Window buckets: dated value 203, stamp missing 61 (the 2026-09-19, 09-21 and 09-23
  vintages); not a present night, post-retrain, X9, pre-change membership and stated null
  0 each. Outside the window: pre-change membership 246, predates the column 572, no
  vintage 1,347. The six sum to the cache's 2,429 games.
- Inside dated value: filter flag unrecorded 80, stamp late 79, stamped from git 74 (the
  2026-09-07 vintage from `7cd5f572`, 2026-09-24 from `1b20dc2a`, 2026-09-26 from
  `3f449c5c`; each board reads `applied` true with no skipped club).
- `parks_short_window`: fit side 40 with, 80 without; graded 83 with, 0 without.
- Vintage age: 73 of 203 dated-value games on a vintage 2 or more days old; game-weighted
  mean age 1.433 days.
- Construction audit to the harness commit: `git log -L` on `_proj_year1_woba_map`,
  `lineup_strength_from_orders` and `build_lineup_strength` and `git log -S` on
  `LINEUP_MIN_JOINED_SLOTS` return `3eda89d7` only; `bullpen_export._active_mlbam_ids`
  last changed at `7cd5f572`. The `hem_plus.py` commits after `77174943` (`48f4c806`,
  `d4a76a62`, `24c56eca` on 2026-10-01 and `4eb8bc2d` on 2026-10-07) postdate every vintage
  that prices a window game, since the regular season ended 2026-09-27, so none can bucket
  one. The post-retrain event is step M (`a4bd70e8`, 2026-10-03T22:15Z), after the same
  vintages.

**5c-C, `star_out`: the step 1 counts (read 2026-10-07 and again 2026-10-08, identical).**
- Present nights 2026-09-05 to 2026-10-02: 21 of 28 (floor 14), missing the same seven
  dates.
- F 2026-09-06, L 2026-09-19, **M 2026-09-12**. Dated-value fit side **76 games, under
  the 100 floor**; graded 109 (floor 50).
- Window buckets: dated value 185, stamp missing 49 (the build stamp was never built, so
  every vintage from 2026-09-19 lacks it), post-retrain 56 (vintages captured after
  `809902c6`, 2026-09-23T16:54Z, which keys the corpus label by side, a construction-class
  change on the label path; step D `8232729f` follows on 2026-10-03), X9 0 (`d11ed73f`,
  2026-09-25, the vet team rule, falls after the post-retrain event), stated null 0.
  Outside the window: basis unconfirmed 15, pre-change ranking basis 205, predates the
  column 572, no vintage 1,347.
- Inside dated value: basis unrecorded 185 of 185. `parks_short_window`: fit side 0 with,
  76 without; graded 79 with, 30 without. Dated-value games on vintages before and after
  `419811bb`'s nightly cadence: 106 and 79.
- Vintage age: 60 of 185 on a vintage 2 or more days old; game-weighted mean 1.405 days.
- Step 1 fails on the fit floor. Under verdict row 1 nothing is fitted, scored or twinned
  for this column and leg 1 does not run; the look run records that.
- Step A's pins for leg 1 are on disk and match part 9:
  `_pre_epoch_fwar_2026-10/mlb_projections.json` SHA-256
  `1e9383f3cbcd61e16737d5f8269053f038056f4ce0ce79527bd27cfd6fb33c86`, corpus `war_provider`
  `ewar_v2`, champion fit key `9f2638f2`.
- Not reported, because the store does not carry it: the champion fit key per night. Each
  record stores the count only.

**What runs next, in this order, on 2026-10-08.** The 5c-B look, then the 5c-C look, each
once, each teed to a file before anything else runs, from the harness at `b9bf49c8`
against this note. A run whose store, anchored window, M or counts differ from this note
refuses before any number.

### Result (run 2026-10-08, once): FAIL, and `lineup_strength` stays dark

**The run.** Once, on 2026-10-08 from 17:39:02Z to 17:39:25Z in the main tree on host
NOAH-PC: harness `tools/b4_availability_look.py` at `b9bf49c8` (blob `27520045`), against
the dated note above, committed alone at `15282680`; incumbent the vintage-mode pricer at
`6e82acd5`. The full record, with every reported number and each twin's 200 means, is
`data/_labs/b4_look/5cB_look_record.json`, committed with this block. The store hash at the
run equals the note's (`f8d6ea17...1b6c`, 59 files), and so do M, both counts and the
anchored window. Nothing failed to run.

**The slip, disclosed.** The registered first day was 2026-10-05. The fWAR label epoch
moved it: the owner's E5 waiver (EPOCH-Q1, the 2026-10-02 amendment in
`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 3) put both B4 looks after step Z,
recorded 2026-10-03. The look code landed 2026-10-07 at `b9bf49c8`, a registered look date
for another family, so 2026-10-08 is the first day after 2026-10-05 on which the pinned
harness ran under the same window, code and rules. It is the one look.

**Verdict row 2, FAIL**, on three requirements: criterion 1 (t 1.337, under 1.645),
criterion 4 (the total's mean is negative) and twin B (not beaten). Criteria 2 and 3, twin
A and leg 1 hold.

**Step 0.** The c = 0 identity check on the 264 window games: 0 mismatches. The vintage
parity and the forward parity: equal. `_paired_delta` at `6e82acd5` uses the n divisor and
differs from the written form, so the inline n-1 form ran. Both arms took
`_lab_runline_split` of the anchored fit window. `_vintage_cut_index`'s cut at the run is
2026-08-01, the governing split.

**Step 1.** Present nights 21 of 28. F 2026-09-08, L 2026-09-27, M 2026-09-17 (written
before the fit). Fit side 120 games, graded 83. The row builder skipped no game.

**Step 2.** c = 0.340946 runs per standard deviation (standard error 0.207326), `xbar_fit`
0.020707, on 240 fit-side rows.

**Leg 2, on the 83 graded games** (incumbent loss minus candidate loss, n-1 divisor):

| Criterion | Mean | sd | t | lb95 | Result |
|---|---|---|---|---|---|
| 1. Moneyline Brier | 0.008593 | 0.058536 | 1.337 | -0.001976 | FAIL (t < 1.645) |
| 2. Moneyline log loss | 0.019256 | 0.121925 | 1.439 | -0.002759 | holds (mean >= 0) |
| 3. Sign | c = 0.340946 | | | | holds (c > 0) |
| 4. Total, absolute error | -0.069563 | 0.378039 | -1.676 | -0.137822 | FAIL (mean < 0) |

**The twins** (the candidate's criterion 1 mean against 200 replicates each):
- Twin A (`random.Random(k)`): 190th smallest mean 0.004256; the candidate's mean exceeds
  197 of the 200. Beaten.
- Twin B (`random.Random(200 + k)`): 190th smallest mean 0.012382; the candidate's mean exceeds
  77 of the 200. Not beaten. No club's value is constant within either half.

**Leg 1, CONTAMINATED** (season-to-date features; it can only fail the candidate): each
club's season-end value from the 2026-09-26 vintage, all 30 clubs, none excluded; the
forward incumbent split at 2026-08-03 (1,682 fit-half games, 3,364 rows; 747 eval games).
c1 = 0.008928 (standard error 0.054733); forward-eval paired Brier mean 0.0000377 (t
0.702). Silent: the mean is positive and c1 is positive.

**Reported, never qualifying.**
- The `z_off` arm: slope 0.136574 (standard error 0.209680); graded paired Brier mean
  0.005548 (t 2.076).
- The correlation of `z_lineup_strength` with `z_off`, from features only: 0.518 on the
  fit side, 0.558 on the graded side.
- The runline: the two tails' log loss sum, mean 0.032300 (t 1.396); Brier at home -1.5,
  mean 0.010423 (t 1.974); Brier at away -1.5, mean 0.003338 (t 0.480).
- RMS of candidate minus incumbent `p_home` over the graded games 0.0694; sqrt(n) x RMS
  0.632.
- Step M landed on 2026-10-03 (`a4bd70e8`), after every vintage that prices a window game;
  the post-retrain bucket holds 0 window games.

**What it changes.** Nothing served. `SERVE_LINEUP_STRENGTH` was never built and nothing
is proposed. The column stays dark and keeps accruing, 2026 is closed for it, and a 2027
test is a new registration under N9. There is no second read on 2026 data.

### 5c-C. The B4 availability gate: `star_out`, look 2026-10-05 (drafted 2026-09-11, revised 2026-09-16)

**Standing.** This is the gate section rule 1 requires for `star_out`. It was drafted on
2026-09-11 and revised on 2026-09-16 on two reviews, before any number related the column,
either side of the `f8c17ffe` ranking-basis change, or any variant to a game outcome or a
price. It lands after `584184d8` (2026-09-16 19:50:30 -0400), the commit that carries 5c-A
and 5c-B, and after the two 2026-09-11 corrections at `6e82acd5` (2026-09-11 19:55:59
-0400). It is late: plan 5.1 set 2026-09-15 as the deadline for the I3 amendments and the
rule-1 gate sections, and this one missed it. Lateness costs nights and graded games, never
adds them, and it changes nothing this section may claim. If the section lands after
2026-09-16 the committer changes the heading date to the commit date and adds one line
saying what moved on disk since, the form 5c-A uses.

**No `star_out` number exists at commit, and here is how that was checked.** `star_out`
appears in three places in the tree: the builder functions in `leaderboard_vintages.py`,
the dark column tuple `DARK3_TEAM_COLUMNS` and one comment in `betting_model.py`, and two
test files (`test_leaderboard_vintages.py`, `test_schema3_builders.py`) whose fixtures carry
no game result. `tools/` holds `ph_gate.py` (5f) and no B3/B4, look or dark harness. Nothing
in the tree joins this column, a variant or a delta to a run, a win, a probability or a
price. The restart below is therefore still admissible under 2026-09-11b point 1, which ends
a restart only once such a number exists.

**What moved on disk between the draft and this commit, read as counts only.** The vintage
store gained 2026-09-13, 09-14 and 09-16 and lost 09-15 for good (2026-09-11b point 5). The
game cache grew from 2,200 games (last date 2026-09-10) to 2,270 (last date 2026-09-15). The
projections bundle was rebuilt (mtime 2026-09-16T15:15:00Z, `generated_at` "2026-09-16",
1,380 vets, against 1,370 on the 2026-09-11 bundle). The champion fit key moved twice with
HEAD unchanged, to `a39327f2` (2026-09-13T19:23Z) and `44ea7f96` (2026-09-16T14:32Z).
`data/betting_model_eval.json` was regenerated (2026-09-16T15:17:35Z) with the same anchored
cut and coefficients. None of these is a value of this column and none was read as one.

**For this column only, three committed sentences are superseded, later and never earlier.**
This document records rather than writes over (11a), so nothing above is edited:
- the 2026-09-11 correction, "The close-variant embargo moves with the look": "`star_out`
  and the xwOBA pair are registered columns, not variants, and keep the ~2026-09-17 date";
- the same correction, "Not reopened": "The xwOBA pair and `star_out` keep the ~2026-09-17
  date, subject to rule 1 (see 2026-09-11b)". The "subject to rule 1" clause is what admits
  this section;
- 2026-09-11b, "The ~2026-09-17 window", to the extent it assumes a 2026-09-17 B3/B4 look
  reads this column.

5c-A superseded the same sentences for the xwOBA pair on 2026-09-16. With both landed, no 5c
column looks on ~2026-09-17. The 2026-08-19b clock start and the four-week floor rule are
unchanged; what moves is this column's own start date, for the reason in the next section.

**Amendment cutoff.** This section is final at commit. After it the only admissible
additions are the dated X9 and post-retrain records it requires below, each a record of an
event rather than a change to a criterion, a threshold, a window, a split or a bucket rule.
A later owner answer, a later review and a later count change nothing. A 2027 test is a new
registration under N9.

**Nothing in this section was measured against a game result.** Read to write it:
- this document's sections 5, 5a, 5c (with all four corrections), 5c-A, 5c-B, 5d, 5e, 5f,
  5g, 5h (rules and 5h-A), 6, 7e, 11a and 11b; plan sections 1.1, 1.3, 1.5, 4 and 5; the R5
  lane record (R5-F1, R5-F2, R5-F3, R5-F10, I2, I10);
- code, read at HEAD `584184d8` on a clean tree. `betting_model.py`,
  `leaderboard_vintages.py`, `proj_export.py`, `fa_projection.py`, `fa_market.py` and
  `war_source.py` are byte-identical at `497d667f`, `6e82acd5`, `a890f36a` and `584184d8`
  (blob compare), and the working tree equals HEAD on all of them. `run_monthly.py` differs
  at `57ebc163` in the weather step alone. Code is cited by name, never by line, because
  line numbers move:
  - `leaderboard_vintages` (`_il_by_org`, `star_out_from_projections`, `build_star_out`,
    `build_dark_team_columns`, `snapshot`, `as_of`, `_org`, `STAR_OUT_TOP_N`,
    `IL_CACHE_MAX_AGE_HOURS`);
  - `proj_export` (`build_payload`, `_il_out60`, `_IL60_CODES`, the vet row, `FIRST_SEASON`);
    `fa_market`'s champion path; `fa_projection` (`build_corpus`, `_war_age_maps`,
    `_corpus_provider_stale`, `_corpus_sig`, `DEF_FEATURE_DEFAULT`, the `EEPHUS_FA_DEF`
    override); `war_source.DEFAULT_PROVIDER`; `scrapers._fetch`; `fa_fit`'s roster write;
    `run_monthly`'s d9 `rebuild_only` and step 9e-pre; `tools/train_proj_models.py --final`;
    `trades.canonical_org`;
  - `betting_model` (`_assemble_team_inputs`, `_mean_sd`, `team_inputs_detail`,
    `team_inputs_from_vintage`, `inputs_as_of`, `expected_runs`, `game_probabilities`,
    `_score_joint`, `split_tie_atom`, `run_dispersion_alpha`, `served_platt`,
    `_lab_runline_split`, `_lambda_rows`, `_paired_delta`, `_logloss`, `backtest`,
    `backtest._grade`, `_vintage_cut_index`, `_feature_basis`, `build_game_cache`,
    `fetch_finals`, `_row_from_schedule`, `DARK3_TEAM_COLUMNS`, the serve flags and the
    vintage constants); `tools/ph_gate.py`;
- `git log` and `git diff` of every commit in the construction audit below, and
  `git log -L` on `_il_by_org`, `star_out_from_projections` and `build_star_out`;
- per vintage file 2026-08-18 to 2026-09-16: `schema`, `vintage_date`, `captured_at`,
  `covers_through`, `provenance.source`, the `feature_basis.star_out` basis string and `n`,
  whether a `parks_short_window` block exists, and whether each club's `star_out` cell is
  null, never the value;
- `.cache/betting/completed_games.json`: `date`, `game_pk`, `home_org`, `away_org` only;
  `.cache/fantasy_schedule/2026-09-*_R.json`: `officialDate`, `gamePk`, `gameType`;
- `data/mlb_projections.json`: top-level keys, `generated_at`, mtime, the vet count, and the
  positions of each club's top five with no IL join (`construction_counts_output.txt`,
  2026-09-11);
- the 2026-09-11 40-man roster cache: the status-code inventory and the cache ages, and the
  mtimes of the 30 roster files and the teams cache today;
- mtimes and keys of `.cache/fa_corpus.pkl` and `.cache/fa_fits_*`, and the corpus
  `war_provider` stamp;
- `data/betting_model_eval.json`: the `vintage` block's `split_date`, `fit_window`,
  `coefficients`, `diff_shrink` and `home_field_runs_adj`, the top-level `split_date` and
  `forward.n`;
- the memory record of the 2026-09-04 nightly (`execution-2026-09-04-ewar-epoch`).

No column value, score, run, win probability, outcome or price was read.

**What the column counts.** Per club per vintage, how many of its top `STAR_OUT_TOP_N` (5)
players carry a StatsAPI 40-man status code starting "D". An integer 0 to 5; 0 is a value.
- **Who is a star.** `vets[].warY1Champ` in `data/mlb_projections.json`, descending, ties by
  mlbam (`star_out_from_projections`). `warY1Champ` is the champion (non-ML) mean WAR for the
  first projected season, `FIRST_SEASON` 2027: `proj_export` sums each side's
  `war_y1_champ`, and `fa_market` sets that to the champion path's own year 1 inside the ML
  branch. `proj_ml` never reaches it. The club is the vet row's `team`: contract club first,
  observed club as fallback, mapped through `trades.canonical_org` by `_org`.
- **Stars are hitters and pitchers.** On the 2026-09-11 bundle (1,370 vets; 458 RP, 270 SP):
  of the 150 top-five slots, 88 are position players, 58 SP, 3 RP and 1 the two-way row, so
  62 of 150 are pitchers; 29 of 30 clubs have at least one pitcher in their five; all 30
  clubs have five or more rankable vets, and none is dropped for a missing mlbam, team or
  `warY1Champ`. Counts, not values, read 2026-09-11.
- **Who is out.** `code.startswith("D")` on the cached roster. On the 2026-09-11 cache
  (1,367 rows over 30 clubs) the D codes are D60 (176), D15 (48), D10 (41) and D7 (1), 266 in
  all; every other code is A (840), RM (258), BRV (2) or NYR (1). An optioned star (RM) is
  not out. The rule is `startswith("D")`, not a code list: `proj_export._IL60_CODES` and the
  builder's own comment show compound codes exist, and whatever StatsAPI emits, the rule is
  frozen by X9 below. The inventory is dated 2026-09-11 because the cache is overwritten
  nightly.
- **The roster source.** `.cache/statsapi_roster_40man_{teamId}_{season}.json`, fresh when
  its mtime is within `IL_CACHE_MAX_AGE_HOURS` (48) of `time.time()` at the builder run,
  which precedes `captured_at`. It is written by `proj_export._il_out60`, which
  `build_payload` calls only inside its `standings_now` branch, through `scrapers._fetch`
  under the 24h current-year TTL; `fa_fit` writes the same keys. So a night reads IL status
  fetched up to 48 hours before its capture. The builder never fetches. Verified for one
  night, 2026-09-16: the 30 roster files carry mtimes 14:28:54Z to 14:29:09Z and the teams
  cache 14:28:53Z, the bundle was written 15:15:00Z, and the vintage was captured 15:16:50Z,
  which is the d9 then 9e-pre order.
- **Nulls, the whole list.** ABSENT for every club when: `mlb_projections.json` is absent or
  carries no vets; the `statsapi_teams_{season}` cache is missing or unreadable (no freshness
  test is applied to that file); no club has a fresh roster cache; or the builder raises. One
  club null when: its roster file is missing, its mtime is older than 48 hours, its JSON is
  unreadable, its org code is longer than 3 characters, or it has fewer than 5 rankable vets.
  On all 19 populated nights 2026-08-20 to 2026-09-16 the basis reads 30 orgs fresh, 0 stale,
  0 missing, and 30 of 30 clubs carry an integer.
- **The record stores the count only.** No identity, no bundle hash, no corpus basis, no
  cache age. A hitter and pitcher split of the count cannot be recovered from the store, so
  it is not part of this gate; it would be a new column with its own clock, and the embargo
  below covers it.

**The construction changed at `f8c17ffe`, and the clock restarts.**

- **The fact.** `f8c17ffe` (2026-09-03 21:49:55 -0400, 2026-09-04T01:49:55Z) made `ewar_v2`
  the `war_source` default. `fa_projection._war_age_maps` labels the projection corpus
  through that default, and `_corpus_provider_stale` rebuilds any cached corpus whose
  `war_provider` differs. That corpus fits the champion WAR map, so `warY1Champ` is ranked on
  a different label series after it. Per the commit message, pitcher-seasons are re-priced on
  FIP within season and role and position players are "numerically identical" to bWAR. That
  claim is the commit's, and it is not exactly true: the 2026-09-04 execution record measured
  107 of 1,899 hitter rows moving, every one a position player who threw mop-up innings. The
  reach is also narrower than "a bWAR engine becomes an eWAR v2 one": `ewar_v2` reaches back
  to 2011 with a per-season bWAR fallback, and the corpus spans 2000 to 2026, so the pre-2011
  rows stay bWAR under an `ewar_v2` stamp (plan 1.1 measures 40.0% of hit and 35.6% of pit
  corpus rows as bWAR). What is measured is that 62 of 150 top-five slots are pitchers on the
  2026-09-11 bundle. Whether the membership of any club's five actually changed at the commit
  was NOT measured, here or anywhere, and this section does not claim it did.
- **Which nights.** 2026-08-20 to 2026-09-03 (8 populated nights) ranked on the old series;
  the 2026-09-03 capture (15:16:50Z) precedes the commit.
- **2026-09-04 cannot be placed, so it starts nothing.** The 2026-09-04 capture is
  19:12:08Z, 17h22m after the commit. The 2026-09-04 nightly ran 13:46 to 15:21 EDT (17:46 to
  19:21Z), so that capture sits inside it. The execution record for that day says the nightly
  "pre-empted the epoch" and "rebuilt every served artifact on a MIXED basis", and plan 1.5's
  step D row records the same incident. The epoch's step E then deleted `fa_corpus.pkl` and
  `fa_fits_*`, and the oldest champion-fit cache on disk is `d196c408`, written
  2026-09-04T20:06:08Z, after that capture. So the record cannot show which basis the bundle
  the 2026-09-04 vintage read was built on. Under 2026-09-11b point 1 a clock starts on the
  first present night carrying the column "populated under its registered construction", and
  that night does not qualify.
- **2026-09-05 can be placed, by mtime.** Its capture is 2026-09-05T17:18:50Z. The only
  champion-fit key alive between 2026-09-04T20:06:08Z and 2026-09-06T04:09Z is `d196c408`,
  and the corpus on disk reads `war_provider` `ewar_v2`. So the bundle that night's d9 wrote,
  and the 9e-pre capture read, was fitted on the new series.
- **Why the old clock cannot stand.** Under the 2026-09-11b fit rule a ~2026-09-17 look would
  split at 2026-09-03: all 180 fit-half games would ride 2026-08-20 to 2026-08-31 vintages,
  before the change, and of 101 graded games 25 would ride pre-change vintages and 76
  post-change ones. The fit would be on one construction and the grade mostly on the other.
- **The treatment.**
  1. The clock restarts with the **2026-09-05** vintage, the first present night that can be
     shown to carry the column under the new ranking basis. The start rests on the code and
     the fit-cache record, as `lineup_strength`'s rests on the code. The four-week floor is
     **2026-10-03**, and the night window is 2026-09-05 to 2026-10-02.
  2. The 2026-09-04 vintage is kept as written, never force-rewritten, and goes to an
     ungraded **basis unconfirmed** bucket with every game it prices. On disk that is 15
     games, all dated 2026-09-05.
  3. The 2026-08-20 to 2026-09-03 vintages are kept as written and go to an ungraded
     **pre-change ranking basis** bucket. On disk that is 205 games, priced 15 / 30 / 10 /
     37 / 46 / 12 / 39 / 16 on the 08-20, 08-21, 08-23, 08-24, 08-27, 08-30, 08-31 and 09-03
     vintages. Every other column on those records grades as before. That side is never read
     on its own, before or after the look.
  4. Starting on 09-05 rather than 09-04 costs one night of night-floor slack and 15 fit-side
     games, and moves the floor one day later. It is the harder of the two starts in every
     direction, which is how a start chosen with counts in hand should read.

**Construction change or refresh: the rule, and every commit classified.**

The rule, taken from the committed 2026-09-11 correction ("Any other projections refresh is
part of the construction registered in 2026-08-19b and buckets nothing") and 2026-09-11b
point 1 ("A value refresh never restarts one"):

> A construction change is a commit that replaces the label series
> `fa_projection._war_age_maps` fits the champion WAR map on, or changes who enters or how
> the five are ranked. Everything else that moves `warY1Champ`'s numbers is a refresh: it
> buckets nothing, restarts nothing, and is reported.

A re-key of the champion fit is not evidence of a code change: `_corpus_sig` digests every
corpus row's `war`, and the key took ten values in the thirteen days 2026-09-04 to
2026-09-16 (`d196c408` 09-04T20:06Z, `a8b9b08d` 09-06T04:09Z, `fdcf9120` 09-06T23:41Z,
`25a4798c` 09-09T18:44Z, `6cd1a293` 09-10T19:02Z, `7b43c863` 09-11T16:50Z, `cc10d35d`
09-11T19:47Z, `ee815fe0` 09-11T22:11Z, `a39327f2` 09-13T19:23Z, `44ea7f96` 09-16T14:32Z),
the last two with HEAD unchanged. The fit-key list per night is the refresh record and is
reported with the look.

**This reading was chosen knowing where each commit falls**, which 2026-09-11b's own
disclosure form requires. Reading `419811bb` (2026-09-11T22:44:20Z) as a construction change
would put the clock at 2026-09-12, the floor at 2026-10-10, and, under the night floor and
the 2026-09-27 season end, almost certainly at INDETERMINATE before any number. Reading it as
a refresh keeps the 2026-10-03 floor and the 2026-10-05 look. The rule above is the committed
one and it is applied the same way to every commit in the table.

Every commit from 2026-08-19 (the builder's own commit) to HEAD `584184d8` touching
`war_source.py`, `fa_projection.py`, `proj_export.py`, `fa_market.py`, `league_constants.py`,
`scrapers.py`, `fa_fit.py`, `leaderboard_vintages.py`, `run_monthly.py` or
`tools/train_proj_models.py`:

| Commit | Date (UTC) | Touches | Class | Evidence |
|---|---|---|---|---|
| `3eda89d7` | 2026-08-20T00:20:11Z | the three builder functions | the construction itself | `git log -L` on `_il_by_org`, `star_out_from_projections` and `build_star_out` returns this commit only; 19h53m before the first populated capture |
| `b528517c` | 2026-09-03T16:14:40Z | `scrapers._fetch`, `run_monthly` | out of scope | adds an ESPN-only TTL branch and a `headers` parameter; the `statsapi_roster_40man_*` key path and its 24h current-year TTL are untouched |
| `f8c17ffe` | 2026-09-04T01:49:55Z | `war_source.DEFAULT_PROVIDER`, `fa_projection`, `proj_export`, `run_monthly` | **construction change** | replaces the label series `_war_age_maps` fits on; the restart above |
| `489d40d4`, `7c45c5c1`, `c5bc2554`, `1362d7f7`, `5f7c4a3d`, `7a095fd2` | 2026-09-06 | `run_monthly`, `proj_export` (Futures forward record, tab copy) | refresh or out of scope | none touches the corpus path, the champion path, the vet `team` rule or `warY1Champ` |
| `609774aa`, `2fbc82ac` | 2026-09-07 | `leaderboard_vintages` schema-4 columns | not a construction change | `git log -L` on the three builder functions returns `3eda89d7` only |
| `7cd5f572` | 2026-09-07T16:04:02Z | `hem_plus.team_offense`, the orders | does not touch this column | its roster walk, `bullpen_export._active_mlbam_ids`, reads `rosterType=active`, never the 40-man cache; `lineup_strength` is the column it moved (5c-B) |
| `0629fb69` | 2026-09-11T00:52:37Z | `leaderboard_vintages` (the 5e repair) | not a construction change | same `git log -L` |
| `0cffda7e` | 2026-09-11T01:18:44Z | `war_source` | refresh (disclosure only) | adds `ewar_vintage` and `EWAR_STALE_REVISED_MAX` and stamps three boards; no served WAR value and no provider changes |
| `dc648755` | 2026-09-11T01:43:20Z | `fa_projection._woba_scale`, `league_constants` | refresh | its own message: WAR must not move; it re-keys the fit, which is a key change, not a series change |
| `723848c6` | 2026-09-11T17:52:09Z | `league_constants` | refresh (inert) | "No consumer reads the solved weights yet"; `fa_projection` reads only the wOBA scale |
| `483a17bb`, `8c79e5aa` | 2026-09-11 | `proj_export`, `fa_market` copy | out of scope | copy strings; no path, no ranking field |
| `06fdabdc`, `48ab3de9`, `e7ceaa5d`, `997a4b17`, `e328f62a` | 2026-09-11 | `run_monthly`, `fa_fit`, `leaderboard_vintages` schema-5 blocks | refresh or out of scope | same `git log -L`; `fa_fit` writes the same roster cache keys under the same TTL |
| `419811bb` | 2026-09-11T22:44:20Z | `war_source` (nightly cadence), `league_constants` (wOBA scale from 2015), `run_monthly` | **refresh, and reported** | the provider does not change and the label series is not replaced. Per its message the scale move changes 127 of 641 hitter paths with a year-1 maximum of 0.30 WAR and pitchers do not move; those are the commit's figures, not measured here. What it does add is a nightly re-price of the LIVE season, so the corpus 2026 rows now move every night under the same provider. That is a cadence change inside the registered construction. The look reports the dated-value games priced on vintages before and after it |
| `497d667f` | 2026-09-11T23:53:21Z | `fa_fit`, `leaderboard_vintages`, `run_monthly` (parks, runline split) | not a construction change | same `git log -L`; it reaches this look only through both arms alike, below |
| `57ebc163` | 2026-09-11T23:54:07Z | `run_monthly` | out of scope | the 9e-pre-wx weather step only |
| `39347a6a`, `192c04e4`, `d79067a5`, `aabc8455`, `a890f36a`, `6e82acd5`, `584184d8` | 2026-09-11 to 09-16 | docs | out of scope | doc commits; `betting_model.py` and `leaderboard_vintages.py` are byte-identical across all of them |

The look record repeats this audit up to the harness commit before any fit.

**What moves this column's ranking, and what does not.** `warY1Champ` moves when the corpus
`war_provider` changes or the champion fits are refitted: the epoch's step D (flip
`DEFAULT_PROVIDER`), step E (delete `fa_corpus.pkl` and `fa_fits_*`),
`_corpus_provider_stale` on any nightly, and any corpus rebuild. It does NOT move at step M:
`tools/train_proj_models.py --final` trains and saves `proj_ml` only, and `fa_market` writes
the champion's own year 1 into the ML branch. Step M moves `lineup_strength`'s `woba[0]`, not
this ranking. The plan's 1.1 row and E5 should read "steps D and E" for this column, not
"step M".

**The candidate: two terms, one on each side's lambda.** The count covers hitters and
pitchers, so it enters both sides. For scoring side S against opponent O:

```
lam'_S = min(9.5, max(1.5, lam_S + c_own * (z_S - zbar) + c_opp * (z_O - zbar)))
```

- `lam_S` is the incumbent's per-side lambda, unrounded, after its home adjustment,
  `diff_shrink` and the [1.5, 9.5] clamp in `expected_runs`.
- `z` is `z_star_out` exactly as `team_inputs_from_vintage` and `_assemble_team_inputs`
  produce it from the pricing vintage: (v - mu) / sd over the core-intersection clubs
  carrying a value, population sd (`_mean_sd`, `sqrt(var) or 1.0`), None when fewer than 2
  carry one.
- `zbar` is the mean of z over the fit-side rows. It is the same constant in both terms,
  because every club-game appears once as S and once as O. There is no intercept, so neither
  coefficient can absorb a level error (5h addition 2).
- Two free parameters, in runs per standard deviation. `c_own` is expected negative (a star
  bat out) and `c_opp` positive (a star arm out).
- This adds a term; it does not replace `z_off`. The served `z_off` still counts plate
  appearances by hitters not active tonight (plan 4.1: a median 16.6% of Offense+ PA).

**The fit.** `c_own` and `c_opp` are fitted together by least squares on the incumbent's
per-side residual (runs minus `lam_S`) over both scoring sides of every fit-side game, at the
incumbent's parameters. That is the 2026-09-11b 5h-A form. Every incumbent parameter stays as
fitted on the anchored window. The fit cannot run when the design matrix is singular, when
either column's sum of squares is 0, or when a pricing vintage has fewer than 2 clubs with a
value; that is verdict row 1.

**One seam prices both arms (to be built; nothing served calls it).** It takes the
incumbent's (`lam_home`, `lam_away`) for a game, adds the two terms to each side, clamps, and
prices through `_score_joint` (Poisson: `_grade` passes alpha None, `game_probabilities` then
calls `run_dispersion_alpha()`, which reads the context key `build_context` writes as None
while `SERVE_RUN_DISPERSION` is False) and `split_tie_atom` at the incumbent's fit-window
`tie_home`. Platt is identity (`served_platt` returns None while `SERVE_PROB_CALIBRATION` is
False). The incumbent arm is the same seam at `c_own = c_opp = 0`, so both arms share every
rounding. Before any number the harness asserts that at zero the seam's `p_home` equals
`game_probabilities(...)["p_home"]` to its 5 published places on every window game. That check
reads no outcome. It is needed because `_grade` rounds `p_home` to 5 places and the tie to 4,
and the unrounded lambdas live only in `_per_game_markets`, which `backtest()` pops before it
returns.

**Rows (to be built).** `_lambda_rows` returns bare (lam, runs) tuples and silently skips
games it cannot price, so the regressors cannot be joined to its rows. A row builder returns
(`game_pk`, date, side, scoring org, opposing org, lam, runs) per scoring side at the
incumbent's parameters, and counts what it skips. A game the incumbent cannot price is
outside every bucket and is counted.

**Runline and park, both arms alike.**
- **Runline.** `game_probabilities` resolves the served split only when `tie_home` is None,
  and every lab passes a fit-window `tie_home`, so the owner's 2026-09-11 reprice
  (`SERVE_RUNLINE_TIE_SPLIT` True since `497d667f`) reaches a lab only through
  `_lab_runline_split(fit_games)`, which `backtest._grade` threads at that commit. Both arms
  take `_lab_runline_split` of the anchored fit window; if the pinned commit lacks it, both
  take the whole-atom construction and the record says which. The split never touches
  `p_home`.
- **Park.** `SERVE_ATH_PARK` (True since `497d667f`) reaches a vintage-priced game only
  through the record's own `parks_short_window` block. The 2026-09-05, 09-06, 09-07, 09-09 and
  09-10 records carry none; the 09-13, 09-14 and 09-16 records carry one, with keys `ATH` and
  `TBR`. So the window's games ride two park terms for those clubs' home games, on the fit
  side and the graded side alike. This is not a leak: the block is dated with its record and
  both arms read it alike. The look reports fit-side and graded games on records with and
  without the block.
- No xwOBA and no `lineup_strength` term enters either arm, whatever 5c-A or 5c-B records.

**Estimand.** On regular-season window games: does adding the two `star_out` terms to the
vintage-mode incumbent's per-side lambdas lower paired per-game moneyline Brier on the graded
side, without worsening log loss or the total, beyond both twins? The moneyline decides, in
rule 4's 11b form, which here means its two criteria only: 2026-09-11b replaces 11b's
0.6/0.7/0.8 grid with one calendar-midpoint split. The total is a guard. The runline is
reported only.

**The incumbent.** The vintage-mode pricer, never `build_context`:
- `backtest._grade` in vintage mode at the pinned commit: `fit_coefficients`,
  `_fit_tie_home`, alpha None, `_solve_diff_shrink`, `_solve_home_adj`, and every serve flag
  of that commit.
- 2026-09-11b says the incumbent "keeps every parameter as fitted on the anchored window".
  `build_context` fits on every completed game, graded ones included, with season-to-date
  boards (R5-F1), so it cannot be that pricer. This is the pricer 7e-D grades and plan 4.2
  repair 1 names.
- **The anchored window** is every vintage-gradable game dated before 2026-08-01. That split
  date governs. On the 2026-09-16 artifact it holds 305 games, 2026-07-06 to 07-31, with b0
  4.345387, b1 -0.037205, b2 -0.096479, b3 0.594771, b4 0.149360, `diff_shrink` 1.28 and home
  adjustment -0.0443. `MODEL_VERSION` is `betting_runs_v2`.
- **Inline, with parity.** `_grade` is a closure inside `backtest()`, so the harness re-solves
  the incumbent inline, as `_total_level_split` does. Before any number: the five
  coefficients, `diff_shrink`, the home adjustment, the tie rate, the split date and n_fit
  must equal the artifact's `vintage` block at the pinned commit, to its rounding, and
  `_vintage_cut_index`'s own cut at the run is printed beside 2026-08-01. If the cut is not
  2026-08-01 or any value differs, the look records INDETERMINATE and nothing is fitted;
  2026-08-01 governs and is never replaced by a later cut.

**The pin, and the one thing this section adds to it.** This look runs in the same harness
run as the `lineup_strength` look. 5c-B's committed "dated note, filed before any number on
this column" pins, directly: the harness commit after it passes the identity and parity
checks, the incumbent commit with `MODEL_VERSION` and every serve flag at each, the anchored
window as its `game_pk` set, the incumbent's parameters, the store host, path and hash, the
split date M, and the step 1 counts. This section chains to that note by name and takes every
pin in it, and adds one condition:

> The note must be filed before the FIRST outcome join of ANY B3/B4 column on that harness,
> the 2026-09-28 xwOBA run included. If a B3/B4 column is joined to an outcome on that
> harness before the note exists, this look records INDETERMINATE.

The reason is dated: the 2026-09-28 run joins outcomes, on the same harness, to games dated
2026-09-16 to 09-27, which are this column's graded games. A harness commit chosen after that
read is a choice made after data. Until the first candidate number exists the harness may be
fixed, and the note names the commit that ran.

**The store.** `prospect-tracker/.cache/leaderboard_vintages/` on host NOAH-PC, the store
R5-F3 measured and the one every count here reads (40 files today). The deploy box's store is
not read for this look and no file from it is copied in. A copied file would pass the
present-night test and let the look choose its nights by coverage, and with 4 of the first 12
window nights missing and 6 more needed, that is a live risk, not a hypothetical one (R5-F3,
I10).

**The look: once, first day 2026-10-05, last day 2026-10-31.**
- The read runs on 2026-10-05, or the first day after it on which the pinned harness runs
  under the same window, code and rules. A slipped read is still the one look.
- The floor is 2026-10-03; the look is 2026-10-05 because it is 5c-B's date and the two run
  together. Both dates see the same graded games, because the regular season ends 2026-09-27.
- If it has not run by 2026-10-31, the look records INDETERMINATE, 2026 closes for the
  column, and the record says why. That matches 5c-B's last day.
- There is no second read on 2026 data, whatever the verdict. A 2027 test is a new
  registration under N9, never a continuation (section 5 caveat 1).

**The graded window.** A game is in the window when:
- `lv.as_of(date)` prices it on a vintage dated 2026-09-05 to 2026-10-04 (the newest
  same-season vintage whose `covers_through` is strictly before the game date);
- it is dated before 2026-10-05;
- it is `gameType` R.

**Postseason is not graded, and here is whose decision that is.** The window is
regular-season games. `completed_games.json` carries no `gameType` field; R is a fetch-time
filter in both doors (`fetch_finals`'s params, `_row_from_schedule`, and the feed walk's
`game.get("type") != "R"`), which `build_game_cache` keeps. So grading October would need the
5e-style harness addition, which is not built. Three further reasons, in order of weight:
- The other B4 column in this same run is regular-season only: the 2026-09-11 correction set
  O25's default at "not graded" with a 2026-09-15 lock, no answer was given, and 5c-B closed
  it at the default. Split answers would put two looks in one run on different game sets.
- The owner's 2026-09-11 answer that 5e counts postseason binds 5e alone: the 5e amendment
  itself says "5f and 5g still exclude postseason games".
- 5f and 5g exclude October for bench, bullpen and roster-usage reasons. A 40-man IL code is
  not that fact, so that reason does not transfer, and this section does not borrow it.

No new owner number is opened. O25's lock date has passed and the fit side is already
complete on disk, so a window answer taken now would be a window chosen after the data exist.
A later answer goes to a 2027 registration under N9.

**The buckets. Each window game falls in exactly one, checked in this order.**
1. **not a present night** (2026-09-11b point 3: `<D>.json` exists, `provenance.source` live,
   `captured_at` UTC date D or D+1): ungraded.
2. **post-retrain**: priced on a vintage written after the corpus `war_provider` changed, or
   after a code change on the label path that replaces the series (steps D and E, or any
   commit the audit rule classes as a construction change): ungraded.
3. **X9**: priced on a vintage written after an X9 event below: ungraded.
4. **stamp missing**: priced on a vintage dated 2026-09-19 or later whose `star_out` basis
   carries no build stamp: ungraded.
5. **stated null**: either club carries no value: ungraded.
6. **dated value**: BOTH clubs carry a value (2026-09-11b, 5f's form). This is the graded n.

Outside the window, reported and never graded, never scored, never entered as a zero paired
difference: **basis unconfirmed** (priced on the 2026-09-04 vintage: 15 games on disk),
**pre-change ranking basis** (priced on a 2026-08-20 to 2026-09-03 vintage: 205 games on
disk), **predates the column** (priced on a vintage with no `star_out` value: 572 games), and
games with no vintage at all (1,347). Those four plus the 131 dated-value games account for
all 2,270 games in the cache.

Inside dated value, two counts are reported and never chosen at the look: **basis unrecorded**
(priced on a vintage written before the stamp lands) and games on a record with and without
`parks_short_window`.

**The stamp (to be built, I9; no stored value changes).** The correction's form, dated here.
From the commit that lands this section, or the next code commit, so that the 2026-09-19
vintage carries it at the latest, the `star_out` basis string carries:
- the projections bundle's mtime and a content hash. Its `generated_at` is
  `date.today().isoformat()` and cannot separate two builds on one day, which is exactly the
  2026-09-04 and 2026-09-11 cases;
- the corpus `war_provider`, which `proj_export` must also start writing into the bundle (the
  bundle carries no such key today);
- the champion fit key (`_corpus_sig`);
- the oldest and newest roster-cache mtime read;
- the codes counted as out.

Every vintage from 2026-09-19 without it goes to bucket 4, ungraded. Delay costs graded
games, never adds them. Nights from 2026-09-05 to the stamp are graded and counted as "basis
unrecorded"; if the stamp does not ship within the eleven days to the 2026-09-27 season end,
that count is every graded game, and a reader of the look record should expect 100%.

**Split and fit (the 2026-09-11b 5h-A form).**
- Let F and L be the first and last dated-value game dates. The split date is
  M = F + floor((L - F) / 2) calendar days. The floor settles the half day 2026-09-11b left
  open.
- Dated-value games dated before M fit; games on or after M are graded.
- M is computed at the look from dates and buckets alone, written into the look record before
  any fit, and never moved.
- Every graded game falls after 2026-08-01, in the vintage eval half, so rule 4 reads as
  written.

**What that arithmetic already fixes, and what it does not.** F is 2026-09-06: the 2026-09-05
vintage first prices the 09-06 slate. With L = 2026-09-27 the span is 21 days and M is
2026-09-16. L is not on disk, so M is not final, and it moves with the last dated-value date:

| L | span | M | fit-side games on disk |
|---|---|---|---|
| 2026-09-20 | 14 | 2026-09-13 | 91 |
| 2026-09-21 | 15 | 2026-09-13 | 91 |
| 2026-09-22 | 16 | 2026-09-14 | 106 |
| 2026-09-24 | 18 | 2026-09-15 | 116 |
| 2026-09-26 or 09-27 | 20 or 21 | 2026-09-16 | 131 |

So the 100-game fit floor is met if and only if the last dated-value game date is 2026-09-22
or later. If the store dies before then, the look is INDETERMINATE on step 1, which is the
correction's rule and plan I2's operational fault, not evidence about the candidate.

Under the expected L every graded game is unplayed at commit: the game cache's last date is
2026-09-15 and M is 2026-09-16. Under an earlier L the graded side reaches back into dates
already played. Either way no number on this column against any of those outcomes exists at
commit, and the split rule is fixed arithmetic on dates, not a choice.

**The statistic, written out.** For each graded game i, d_i is the incumbent's loss minus the
candidate's loss, so positive means the candidate is better. With n graded games:
- mean = sum(d_i) / n;
- sd = sqrt(sum((d_i - mean)^2) / (n - 1)), the n-1 divisor;
- se = sd / sqrt(n); t = mean / se; lb95 = mean - 1.645 se.
- If sd = 0 the criterion cannot run (verdict row 3). Nothing escapes to se = 0.

**The divisor, disclosed.** `_paired_delta` at the pinned commit divides by n, not n-1, and
returns t None on sd = 0. Plan 4.2 repair 3 moves the module to the n-1 divisor with a
zero-variance refusal. The written form above governs whichever lands: the harness computes it
inline and, before any number, asserts on a fixture that `_paired_delta` at the pinned commit
agrees to its rounding, or the note says the helper differs and the inline form ran. n-1 is
chosen because it is the plan's direction and the smaller t. 5c-B carries the same written
form and cites this section for it. 5c-A, also committed, reads `_paired_delta` itself and so
carries the population divisor. That is a real divergence inside one run, it is recorded here
rather than papered over, and it cannot be fixed from this section, because 5c-A is committed
pre-registration. The look record prints which divisor each column used.

**Leg 2, the vintage leg. All four required, on the graded dated-value games.** Every delta
is incumbent loss minus candidate loss per game, so positive means the candidate is better.
1. **Moneyline Brier**, the statistic above: mean > 0 and t >= `Z_95_ONE_SIDED` (1.645). y is
   home runs greater than away runs, as `_grade` scores it.
2. **Moneyline log loss** (`_logloss`, eps 1e-9), same statistic: mean >= 0 on the point
   estimate.
3. **Net availability sign**: `c_own - c_opp < 0`. A club's run differential moves by
   (c_own - c_opp)(z - zbar), so this is the statement that a club with more stars out is
   priced to a worse differential. A wrong net sign fails the candidate whatever 1 and 2
   read. The two signs separately are reported, not required. This is 5g criterion 3's form.
4. **Total, not worse.** Paired absolute error |home runs + away runs - (lam_home +
   lam_away)| on unrounded lambdas, the `fair_total` `game_probabilities` builds before any
   total level. Mean >= 0 on the point estimate. Both terms move both lambdas, so a flip moves
   the total, and the total is ledger-closed with a disclosed Over lean (plan 4.2). 5c-A and
   5c-B carry the same guard.

The runline is reported only, never a criterion, on both sides: the per-game sum of the two
tails' log losses (home margin >= 2, home margin <= -2; the 11a amendment,
`RUNLINE_SIDE_AMENDMENT` "both") and each tail's Brier. It is 11a's form, which needs no
posted price.

**Is rule 3's twin right for an availability count?** Rule 3 binds rolling-form candidates in
its own words, and 5d-A applied it to availability. On its own it is the wrong control for a
count like this. Permuting across clubs within a date destroys two things at once: the club's
standing level of injured stars and the night's timing. So beating it cannot separate "this
club's stars are out tonight" from "this club has carried injured stars all month", and the
second is a club trait that tracks what `z_off` and `z_prev` already price. Rule 3's twin is
kept as twin A, and twin B is added. Both are required.

**Twin A, rule 3's permuted twin (the chance control).**
- Replicate k, for k = 0 to 199, uses `random.Random(k)`, one generator per replicate,
  advanced across vintages. It is not reseeded per vintage: reseeding would give every 30-club
  night the same permutation, a fixed club relabelling that keeps club persistence, which is a
  different null.
- Rule 3's "within each date" is read as within each pricing vintage. z is standardized within
  the vintage and one vintage's value prices every game it covers, so per-vintage is the unit.
  This reading is this section's own and is listed under "Extensions".
- Walk the pricing vintages that price at least one dated-value game, in ascending
  `vintage_date`. In each, shuffle the stored values among the clubs carrying one, listed in
  canonical org-code order. mu and sd do not change, so the z-scores permute exactly. The
  buckets fix the vintage set before any fit.
- Refit `c_own` and `c_opp` with their own `zbar` on the same fit side, and grade the same
  graded side.

**Twin B, the within-club twin (the availability control).** It keeps each club's level and
destroys only the timing, which is the B4 claim.
- Replicate k, for k = 0 to 199, uses `random.Random(200 + k)`.
- Within each half, fit among fit and graded among graded, so no twin fit reads a graded-side
  value. Inside the fit half a game may take a later fit-half value; that is the null, and the
  property claimed is only that no graded-side value enters a fit.
- For each club in canonical org-code order, shuffle its z across its own dated-value
  club-games, listed in (date, `game_pk`) order. Both of a game's regressors take the permuted
  values, since a club's value is its own z whether it is scoring or opposing.
- Refit and grade as above.
- A club whose z never moves within a half is unchanged by twin B. A club whose stored COUNT
  never moves can still have a moving z, because z is standardized per vintage over that
  vintage's clubs. The count of clubs with a constant z per half is reported.

**zbar and both coefficients are recomputed on every replicate**, because clubs appear
unequally often per vintage, so the fit-row mean of z moves under permutation.

**The bar, for each twin.** The candidate's criterion 1 mean must be strictly greater than at
least 190 of the 200 twin means, that is, greater than the 190th smallest. Ties count against
it. This is 5h-A's "exceed the 95th percentile" as a nearest-rank order statistic. Its exact
size under the null is 11/201 = 5.47%, not 5%; 191 of 200 would give 4.98%. 190 is kept
because 5c-A and 5c-B are committed with the same bar and one run must read alike, and the
size is stated here so no reader has to derive it.

**Reported, never qualifying: the offense arm.** The same fit on the same rows with the
scoring club's centered `z_off` from the same record in place of `z_star_out`, plus the
correlation and variance-inflation read of `z_star_out` against `z_off` and `z_prev` over
fit-side and graded rows, from features only. It asks whether the column beats a refit of
offense level. Twin B tests the availability claim directly, so this arm is reported and not
required.

**Leg 1, the contaminated-forward screen (rule 4; to be built; it can only fail the
candidate).**
- **The column (to be built).** No season-to-date `star_out` exists: `team_inputs_detail`
  sets every dark column None. The screen builds one per game date D for every 2026
  regular-season game:
  - the top five by `warY1Champ` on a PINNED bundle, recorded by mtime and content hash, with
    its corpus `war_provider` and champion fit key. The bundle must be an `ewar_v2` build
    written before the epoch's step D. The look date is also the D9 freeze and step D (plan
    5.1, W2), after which `_corpus_provider_stale` rebuilds the corpus on `fwar` at the next
    nightly, so "the bundle on disk when the harness runs" is not a pin and is not used. If no
    such bundle is on disk at the run, leg 1 is recorded unrunnable and verdict row 3 applies;
  - counted against the 40-man status as of D-1, from
    `/api/v1/teams/{teamId}/roster?rosterType=40Man&date=<D-1>`, codes starting "D";
  - standardized within date, `_mean_sd`'s form, then centered on the forward fit-half rows.
- **The endpoint is unverified.** No probe has been run. A probe before the look that reads
  roster data only, joins no outcome and no price, may run, and the record says whether it did
  and on what day. If the endpoint cannot return a dated status, the fallback named now is IL
  spells rebuilt from the StatsAPI transactions feed. If neither yields a dated status for 28
  of 30 clubs on 90% of dates, leg 1 is unbuildable and the candidate cannot serve in 2026
  whatever leg 2 reads.
- **It is contaminated twice, and labelled so**: the ranking bundle has seen the season, and a
  dated roster read can show an IL placement made retroactively.
- **It reads 40-man IL codes only.** It never reads active-roster membership, a posted lineup
  or a boxscore roster, so it is not a variant the `lineup_strength` embargo covers.
- **The incumbent** is `backtest()`'s contaminated `forward` fit at the pinned commit, split at
  `dates[int(len(dates) * 0.7)]` over the completed dates. That cut moves with the season: on
  the 2026-09-11 artifact it was 2026-07-22 with 682 forward games, and on the 2026-09-16
  artifact it is 2026-07-26 with 700. The rule is the pin, not the value; the artifact's
  `generated_at` and the cut at the run are recorded, with a parity check against the
  artifact's `forward` block and top-level `split_date`.
- The two coefficients are fitted by the same residual least squares on the forward fit half.
- **Leg 1 fires**, and the candidate fails, when the forward-eval paired Brier mean is <= 0 on
  the point estimate, or when `c_own - c_opp >= 0`. Leaked features that show no effect in the
  right direction leave a dated feature nothing to find.
- **It runs in the look run only**, on or after 2026-10-05, never after it. "Or after it"
  would be a second 2026 outcome read on this column, on the graded games among others, with
  leg 2 already known.

**Order of operations.**
0. Before any number: the zero-coefficient identity check, both parity checks, the
   `_paired_delta` fixture check, then the dated note.
1. Counts, on the pinned commit and the named store:
   - present nights from 2026-09-05 to 2026-10-02: at least 14 of 28 (2026-09-11b point 2);
   - dated-value fit-side games: at least `VINTAGE_MIN_FIT_GAMES` (100);
   - dated-value graded games: at least `VINTAGE_MIN_EVAL_GAMES` (50);
   - the identification precondition: at least 30 fit-side club-games carry a count of 1 or
     more and at least 30 carry 0. POLICY. It was set with the D-code inventory (266 of 1,367
     rows on the 2026-09-11 cache) and the top-five composition in hand, which are counts, not
     stored column values, and that is disclosed rather than denied.

   If any count fails, nothing is fitted, scored or twinned, and leg 1 does not run.
2. Fit `c_own` and `c_opp`.
3. Criteria 1 to 4, both twins, the offense arm and leg 1, in one run. Everything that runs is
   reported.

`VINTAGE_MIN_GRADED_GAMES` (600) is not a criterion here, as in 11b's form, so a pass would
rest on at most about 160 graded games. That is one reason a pass serves nothing in 2026.

**The verdict. The first row that matches wins.**

| Order | Verdict | When |
|---|---|---|
| 1 | INDETERMINATE | the look has not run by 2026-10-31, the dated note was not filed before the first B3/B4 outcome join on the harness, a parity or identity check fails, or step 1 or step 2 fails. Nothing else is computed |
| 2 | FAIL | any of criteria 1 to 4 fails, either twin is not beaten, or leg 1 fires. A failed requirement is a FAIL even when another component could not run |
| 3 | INDETERMINATE | nothing failed, but a criterion (sd = 0), a twin or leg 1 could not run |
| 4 | PASS | every floor met, criteria 1 to 4 hold, both twins beaten, leg 1 ran and is silent |

**No second read.** No verdict permits a second 2026 read. A harness defect found after the
run makes the look INDETERMINATE, recorded with the defect named: the file, the function and
the reported numbers it touched. The original numbers stay beside it, labelled defective.
Nothing is recomputed on 2026 outcomes. A defect can move a PASS or a FAIL to INDETERMINATE,
never to PASS.

**No power precondition.** 5f and 5c-A stop at UNDERPOWERED when sqrt(n) x RMS is below 1.645.
This section adds no such verdict, as 5c-B adds none: the look runs once, so reading it costs
no later look, and a power verdict would be a new stopping rule on the graded read. Two
numbers are reported beside the verdict and neither decides: the RMS of candidate minus
incumbent `p_home` over the graded games, and sqrt(n) times it.

**Multiplicity and stacking.** Three 5c candidates read the same incumbent family on
overlapping 2026 games: the xwOBA pair (5c-A, 2026-09-28), `lineup_strength` (5c-B, this run)
and this column. Each faces an unadjusted one-sided t >= 1.645, by design. Rule 4 sets that
bar per candidate; a Holm family in plan 2.3's form would raise the first-ranked bar, which
amends rule 4's threshold, and this section does not do that. `star_out` sits in no existing
Holm family (RE is total-only; 7e's family is coefficient estimators), and none is assigned
after the verdict. The cost is stated: for the two B4 columns read in this run, the chance
that at least one of two null candidates passes criterion 1 is at most 0.10 (0.0975 if
independent); across all four 5c candidates at most 0.20. No candidate's term ever enters
another's arms. A PASS here and a PASS on `lineup_strength` give two separate flag proposals,
never a joint one, because a two-term fit is a third, unregistered candidate.

**Coverage at commit (counts, no value; 2026-09-16, script `rev4/counts4.py`).**
- Nights in the window (2026-09-05 to 2026-10-02): 8 present of the 12 elapsed, 2026-09-05,
  09-06, 09-07, 09-09, 09-10, 09-13, 09-14 and 09-16. Missing: 2026-09-08, 09-11, 09-12 and
  09-15; none can be written late (2026-09-11b point 5). Every present night is live, captured
  on its own date, `feature_basis.star_out` n 30, 30 of 30 clubs non-null.
- `completed_games.json`: 2,270 games, last date 2026-09-15.
- Buckets over all 2,270 games at the as_of rule: 131 dated value (2026-09-06 to 09-15), 15
  basis unconfirmed (the 2026-09-04 vintage, all dated 09-05), 205 pre-change ranking basis,
  572 predates the column, 1,347 no vintage. 0 stated null. The five sum to 2,270.
- Dated-value games by date: 09-06 15, 09-07 11, 09-08 15, 09-09 15, 09-10 5, 09-11 15, 09-12
  15, 09-13 15, 09-14 10, 09-15 15.
- The ceiling on the graded side: 2,430 scheduled regular-season games less 2,270 complete
  leaves at most 160, every one dated 2026-09-16 or later. The schedule cache holds 88 of
  them, 2026-09-16 to 09-22 (15, 9, 15, 15, 15, 3, 16); it reaches no further, so the
  2026-09-27 season end here rests on 5e, 5g and plan 5.1, not on the cache.
- The look reports, of the dated-value games, how many rode a vintage 2 or more days old,
  with their game-weighted `vintage_age_days`.

**The night floor, as arithmetic.** Of the 28 window nights, 8 are present and 4 are missing,
so the floor needs 6 of the remaining 16 (2026-09-17 to 10-02). Whether the nightly writes
vintages after the 2026-09-27 season end is unverified. If it does not, the floor needs 6 of
the 11 nights 2026-09-17 to 09-27, which is 55% uptime. At the window's own rate (8 of 12,
67%) those 11 nights yield about 7.3, and at the schema-3 rate (16 of 24, the 2026-09-11b
table) about 7.3 as well. The floor is reachable at the observed rate with little slack. The
2026-09-04 start would have needed 5 of 15; that one night of slack is what the restart's
honest start costs.

**Power, as arithmetic on counts.** Suppose the candidate's probabilities were exactly right.
Its expected paired-Brier t is then about sqrt(n) x RMS of its `p_home` shift, the arithmetic
5f and plan 4.1's 5j summary use. At the graded ceiling n = 160 (sqrt 12.65), with the chance
of t >= 1.645 from a normal approximation:

| RMS shift in p_home | expected t | chance of t >= 1.645 |
|---|---|---|
| 0.010 | 0.13 | 0.064 |
| 0.020 | 0.25 | 0.082 |
| 0.046 (plan 4.1's resting star on an even game) | 0.58 | 0.144 |
| 0.130 | 1.65 | 0.50 |
| 0.197 | 2.49 | 0.80 |

These are upper bounds, because they ignore the noise in the two coefficients and criteria 2
to 4 and both twins. One standard error on a coefficient is about 0.20 runs per standard
deviation: 3.18 runs of per-side residual sd (11a's 10.4889 run variance less 0.3755 of lambda
variance) over the 262 fit-side rows the 131 fit games give, ignoring the correlation between
the two regressors, which is real because each club-game enters once as S and once as O.

**The pre-registered expectation: FAIL or INDETERMINATE, for power.** A FAIL at this n is not
evidence that availability does not matter. A PASS would need a shift several times the
4.6-point resting-star shift plan 4.1 records.

**Reported whichever way it lands.**
- The dated note's contents, and which divisor this column used.
- The incumbent: its parameters, the governing split 2026-08-01 with `_vintage_cut_index`'s
  own cut beside it, both parity results, the identity check and the `_paired_delta` fixture
  result, and which runline construction both arms used.
- The construction audit to the harness commit, and the fit-key list per night.
- The clock start, the floor, and the nights present and missing, with the missing dates
  listed.
- The 8 pre-change nights listed, the 2026-09-04 night listed on its own, and their game
  counts.
- The window games per bucket, per pricing vintage, with "basis unrecorded" and the
  `parks_short_window` split inside dated value.
- Of the dated-value games, the count on a vintage 2 or more days old and their game-weighted
  `vintage_age_days`.
- F, L, M, the fit and graded n, `zbar`, `c_own`, `c_opp` and their standard errors.
- Criteria 1 to 4: mean, sd, t and lb95.
- Each twin: its 200 means, the 190th smallest, and the candidate's rank. For twin B, the
  clubs per half whose z never moves.
- The offense arm, and the correlation and variance-inflation reads.
- Leg 1's delta, t and both signs, labelled contaminated, with its pinned bundle's mtime,
  hash, `war_provider` and fit key, the forward cut and the artifact `generated_at`, and its
  excluded clubs and games.
- The runline, both tails.
- The distribution of stored counts on the fit and graded halves.
- The RMS and sqrt(n) x RMS above.
- The dated-value games priced on vintages before and after `419811bb`'s nightly cadence.
- Reported, never qualifying: criteria 1 and 2 on the graded games at vintage age 1 only; a
  date-clustered t; and, on the look-date bundle, the top-five players absent from their
  club's 40-man cache.

**Before the look: counts only, and the guard that makes it so.** No fit, paired score, twin
or leg 1 is computed for this column before 2026-10-05. `star_out` sits in
`betting_model.DARK3_TEAM_COLUMNS`, the tuple a generic candidate loop would iterate and
`_assemble_team_inputs` standardizes, so:
- any harness that runs on the real store before 2026-10-05, the 2026-09-28 run of 5c-A
  included, carries in its own commit and before its first run an exclusion of this column
  from its candidate list, a date refusal before 2026-10-05 and an outcome-field refusal in
  the form of `tools/ph_gate.check_look_date` and `refuse_outcome_fields` (that function
  itself refuses every date before `FIRST_LOOK_SEASON` 2027, so it cannot be reused as is),
  and a test that no run dated before 2026-10-05 writes `z_star_out` beside an outcome field;
- that run's record lists its candidate columns. A run whose record does not list them is
  treated as having computed on this column, and the candidate is disqualified;
- such a run reports, for this column, the nights on each side of `f8c17ffe` listed, the
  window games per bucket, and the nights on the new basis the record cannot confirm. If no
  such run is held, the look record reports them first.

**Known readers of the same 40-man cache, and why none is a pre-existing relation.** No served
price reads a 40-man IL code. `proj_export._il_out60` writes the cache and serves a display
badge; `fa_fit` and `hitter_export` read the same keys and price no game; the DFS and fantasy
availability rules read `rosterType=active`, a different endpoint.
`betting_model._feature_basis` counts each dark column's status per graded game and reads no
value. So the embargo below needs no named exceptions, and this is recorded so a reader does
not mistake the nightly cache write for a relation.

**Embargo.** Until this look is recorded, no star-availability, IL, injury or active-roster
variant of this column is related to a game outcome or a price. That covers another top-N,
another ranking field or WAR basis, a hitter-only or pitcher-only count, a WAR-weighted count,
another roster source, another freshness window, and either side of `f8c17ffe` alone. The
pre-change side and the basis-unconfirmed night are never related to an outcome on their own,
before or after the look.

**Disqualification.** Any of these before the 2026-10-05 look disqualifies the candidate under
rule 1: any number relating `star_out`, either side of the change, or a variant above to a game
outcome or a price; any fit, score or twin of this column in any run before 2026-10-05,
including a run whose record lists no candidate columns.

**Forward (X9).** Any later change to who enters the five or what counts as out is recorded
here the same day: `STAR_OUT_TOP_N`; the ranking field or its definition; the corpus WAR
provider; `fa_projection.DEF_FEATURE_DEFAULT` (True since `4853e683`, 2026-07-31) or the
`EEPHUS_FA_DEF` environment override read ahead of it; the vet `team` rule or
`trades.canonical_org`'s mapping; the D-code rule; the roster endpoint, cache key or TTL;
`IL_CACHE_MAX_AGE_HOURS`. Vintages written after such a change go to the X9 bucket, the clock
does not restart again, and the look reads only the nights before it. Under the night floor
that can make the look INDETERMINATE.

**Post-retrain and refresh, forward.** The post-retrain bucket's events are a corpus
`war_provider` change and a construction-class code change on the label path, the epoch's
steps D and E above all. Step M is not one of them. Plan W2 puts step D in the epoch after
the ~2026-10-05 freeze, and the 2026-09-11 correction keeps step M after 2026-09-27, so no
graded game should be touched. If either lands earlier, every vintage written after it goes
to the post-retrain bucket, and no later record decides that. Any other projections refresh,
including the nightly live-season re-price `419811bb` added and every re-key of the champion
fit, is part of the construction and buckets nothing.

**What a pass changes: nothing served in 2026.**
- It records that `star_out` passed both legs, all four criteria and both twins on at most
  about 160 games, and licenses a flag proposal, not a flip.
- The flag would be `SERVE_STAR_OUT` (to be built, default False, in the
  `SERVE_RUN_DISPERSION` idiom), flipped by the owner in one commit with a `MODEL_VERSION`
  bump and a tripwire test, so the ledgers never pool two pricers.
- The served coefficients and `zbar` are the look's fit-side values, frozen as literals (X4),
  never refit on the 2026 graded games.
- Serving needs a live builder on `team_inputs_detail`'s path; that function sets the column
  None today.
- A flip would move `lam_home` and `lam_away` at every game where either club's count is off
  the mean, so every moneyline, runline and total side moves and the Pick of the Day can
  change.
- The proposal must state two things, and the owner decides both: the coefficients were fitted
  on the vintage-mode pricer's residual, so serving them on the `build_context` pricer serves a
  pair never graded together (O14, 7e-D); and the ranking field changes series at the fWAR
  epoch (step D), so a 2026 pass describes a construction the 2027 pipeline will not produce.
  It enters N9's 2027 protocol as a candidate, re-registered on the new basis.

**What a FAIL or INDETERMINATE changes.** Nothing. The column stays dark and keeps accruing,
2026 closes for it, and a 2027 test is a new registration under N9.

**To be built before the look.** Named so the run cannot improvise: the seam and the row
builder; the residual fit and the written statistic with its fixture check; both twins with
their seeds; the offense arm; leg 1's column, its endpoint probe and its pinned bundle; the
game-level both-clubs count and the bucket report in `_feature_basis`; the basis stamp above;
the harness arm with its date and outcome-field refusals and their tests; the exclusion of
this column from any earlier harness's candidate list, in that harness's own commit; the
`snapshot` refusal for a past `on_date`; the look record, carrying M before any fit.

**Extensions.** Each extends the record and is stated as an extension. None can make a pass
easier.
1. **The clock start.** 2026-09-05 rather than 2026-09-04, on the record that the 2026-09-04
   capture ran inside a nightly that wrote a mixed basis, and the fit-cache mtimes that place
   2026-09-05 on the new series. It costs a night of floor slack and 15 fit-side games.
2. **The basis-unconfirmed bucket** for that one night and its 15 games.
3. **The refresh rule, written out** with every commit since 2026-08-19 classified, and the
   disclosure that the reading was chosen knowing where each commit falls.
4. **The pin condition**: 5c-B's dated note must precede the first B3/B4 outcome join on the
   harness, the 2026-09-28 run included.
5. **The postseason window**, settled in this column's own terms rather than borrowed from 5f
   and 5g, and routed to N9 for 2027.
6. **The stamp, dated** (2026-09-19 at the latest), with the "stamp missing" ungraded bucket,
   and the bundle mtime and hash in place of `generated_at`, which is a date string.
7. **Criteria 3 and 4, twin B, the 190-of-200 bar, the identification precondition, the
   verdict order and the last day**, all of which can only make passing harder.
8. **The statistic and the n-1 divisor** written out where `_paired_delta` uses n, with the
   divergence from 5c-A disclosed.
9. **The store**, named now, never merged (R5-F3, I10).
10. **The twin reading**: per pricing vintage rather than per date, because z is per vintage.

**Plan edits this needs** (`docs/master-plan-2026-09-11-war-epoch-drivers-betting.md`),
consistent with the list 5c-A already carries:
- 5.1, the ~2026-09-17 row: no column looks. It becomes "if a harness run is held, counts only
  for the xwOBA pair, `star_out` and `lineup_strength`", or is deleted.
- 5.1, the 2026-10-05 row: add the `star_out` look beside `lineup_strength`, with its
  preconditions (its rule-1 gate section; no star-availability variant related to an outcome
  or a price; no construction-class change on the label path landed).
- 1.1 and E5: `star_out` moves at **steps D and E**, not at step M. E5's "`star_out`
  ~2026-09-17" becomes 2026-10-05.
- 1.5, "Betting touch points of step M": step M does not move `star_out`'s ranking; the
  corpus and champion fits do. The stamp item stays.
- O11: the sequencing constraint for this column is steps D and E, not the 09-17 look; the
  09-17 date it names is spent.
- E4 clause (j), the `star_out` handling: the post-retrain and X9 buckets above, and the
  stamp.
- I3: record that this section moves this column's look and restarts its clock.
- I9: the stamp contents above.
- W1 and the dependency spine: the 09-17 row is counts only; the 2026-09-28 xwOBA look, then
  the 2026-10-05 `lineup_strength` and `star_out` looks.
- 4.1 (5j) and the N12 / G4-08 market-residual screen: for star-availability variants the
  exclusion date is 2026-10-05.
- 7.2, risk 7: "before 09-17" becomes "before 10-05" for star variants, which is now the same
  date both B4 columns carry.

**Doc edits this needs** (`docs/diamond-betting.md`): the two committed sentences that keep
`star_out` on ~2026-09-17 (the 2026-09-11 correction, "The close-variant embargo" and "Not
reopened") and 2026-09-11b's "The ~2026-09-17 window" paragraph each gain "superseded for
`star_out` by 5c-C", beneath them and never over them.

**Not reopened.** No criterion, control or threshold in rules 1 to 4, or in the two 2026-09-11
corrections, is amended. For this column this section fixes: the clock start (2026-09-05) and
the floor (2026-10-03); the look (2026-10-05, last day 2026-10-31); the candidate, the fit,
the estimand, the four criteria, both twins and their bar, leg 1 and the verdict order; the
window, the split rule, the buckets, the stamp, the embargo and the disqualification rule.
Their precedents are 5g (sign), 5h-A and 5f (the twin bar), 5c-B (the within-club twin, the
written statistic, the store, the defect rule and the last day), 5c-A and plan 4.1 (the total
guard) and 7e-D (the last day).



### Result (run 2026-10-08, once): INDETERMINATE, and `star_out` stays dark

**The run.** Once, on 2026-10-08 from 17:39:31Z to 17:39:51Z, in the same harness run as
5c-B's look and after it: harness `tools/b4_availability_look.py` at `b9bf49c8` (blob
`27520045`), against 5c-B's dated note, committed alone at `15282680` before the first
outcome join of any B3/B4 column on this harness (5c-B's look, 17:39:02Z); incumbent the
vintage-mode pricer at `6e82acd5`. The record is `data/_labs/b4_look/5cC_look_record.json`,
committed with this block. The store hash at the run equals the note's (`f8d6ea17...1b6c`,
59 files), and so do M, both counts and the anchored window.

**The slip, disclosed.** The registered first day was 2026-10-05. The fWAR label epoch
moved it: the owner's E5 waiver (EPOCH-Q1, the 2026-10-02 amendment in
`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 3) put both B4 looks after step Z,
recorded 2026-10-03. The look code landed 2026-10-07 at `b9bf49c8`, a registered look date
for another family, so 2026-10-08 is the first day after 2026-10-05 on which the pinned
harness ran under the same window, code and rules. It is the one look.

**Verdict row 1, INDETERMINATE: step 1 fails on the fit floor.** The dated-value fit side
holds 76 games against `VINTAGE_MIN_FIT_GAMES` (100). Under row 1 nothing else is
computed: no coefficient was fitted, no game was scored, no twin was drawn, the
identification precondition was not counted and leg 1 did not run. No number relates
`star_out` to a game outcome or a price.

**Step 0, which passed.** The zero-coefficient identity check on the 290 window games: 0
mismatches. The vintage parity and the forward parity: equal. `_paired_delta` at
`6e82acd5` uses the n divisor, so this column's written form is the inline n-1 one (no
statistic was computed under it). Both arms would have taken `_lab_runline_split` of the
anchored fit window. `_vintage_cut_index`'s cut at the run is 2026-08-01, the governing
split.

**Step 1, the counts.**
- Present nights 2026-09-05 to 2026-10-02: 21 of 28 (floor 14). Missing: 2026-09-08,
  09-11, 09-12, 09-15, 09-20, 09-22 and 09-25.
- F 2026-09-06, L 2026-09-19, M 2026-09-12. Fit side 76 games (floor 100, fails), graded
  109 (floor 50, met).
- Why L is 2026-09-19 and not 2026-09-27: every vintage from 2026-09-19 lacks the build
  stamp, which was never built (stamp missing, 49 games), and every vintage captured after
  `809902c6` (2026-09-23T16:54Z, the corpus label keyed by side, a construction-class
  change on the label path) is post-retrain (56 games). Step D (`8232729f`, 2026-10-03)
  and the X9 event `d11ed73f` (2026-09-25, the vet team rule) fall after it, so X9 holds 0.
  Stated null 0; not a present night 0.
- Outside the window: basis unconfirmed 15 (the 2026-09-04 vintage, all dated 2026-09-05),
  pre-change ranking basis 205 (the eight 2026-08-20 to 2026-09-03 vintages), predates the
  column 572, no vintage 1,347. With the window's 185 dated-value, 49 stamp-missing and 56
  post-retrain games these sum to the cache's 2,429.
- Inside dated value: basis unrecorded 185 of 185. `parks_short_window`: fit side 0 with,
  76 without; graded 79 with, 30 without. Dated-value games on vintages before and after
  `419811bb`'s nightly cadence: 106 and 79. Vintage age: 60 of 185 on a vintage 2 or more
  days old, game-weighted mean 1.405 days.
- Leg 1's step A pins were on disk and matched part 9 (`mlb_projections.json` SHA-256
  `1e9383f3cbcd61e16737d5f8269053f038056f4ce0ce79527bd27cfd6fb33c86`, `war_provider` `ewar_v2`, champion fit key `9f2638f2`); leg 1 did not
  run because step 1 failed, not for want of them.
- Not reported, because the store does not carry it: the champion fit key per night.

**What it changes.** Nothing served. `SERVE_STAR_OUT` was never built and nothing is
proposed. The column stays dark and keeps accruing, 2026 is closed for it, and a 2027 test
is a new registration under N9, on the fWAR basis the ranking field now reads. No verdict
permits a second 2026 read.

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

**Note (2026-09-30), disclosure only.** The section "Starter workload: expected outs
and pitches per start" (after 5l), registered the same day, is plan candidate N6(d):
an expected-outs share that would REPLACE the innings share this gate names as its
confound. It reads nothing of 5d-E. Its stage 1 never reads `sp_tto3_bf` or
`sp_rest_days`, and its stage-2 look (not before 2027-07-01) reads `sp_tto3_bf` only
as a dark column in a VIF table. It changes none of 5d-E's criteria, its twin, its
variance-inflation read or its date.

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

**Reopened (2026-10-08, owner answer 2026-09-25 batch 5).** The paragraphs above are left
as written. Their premise, that the assignment is not knowable at pricing time, rested
on one `Preview`-state live feed; the schedule endpoint with `hydrate=officials` is a
different source (census X05-04). The section "The home-plate umpire: a dark pregame
assignment capture" registers the capture and its family, and its capture time rule is
what the sentence above asks for: only an assignment captured before the slate's price
vintage counts. No umpire column is added to the vintage store; the candidate columns
live in a frozen prior-season table. The contaminated effect-size measurement this
section describes has still not been run, and the new section forbids it outside its
look.

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

### Amendment (2026-09-11): 5d-C is read inside the run-environment Holm family

The 5d-C gate above is left as written.

**The ground, recorded as a new precedent.** The one recorded permission, in the 5e
correction of 2026-09-10, is a pre-registration amended "under 5c rule 1, which permits
amending a pre-registration before its clock opens on a fact established without touching
outcomes". 5d-C's clock opened with the 2026-09-09 vintage (the correction above), so that
wording does not cover this amendment. This is a new precedent, recorded as one: an
amendment made after a clock opens and before the look, that ONLY TIGHTENS, on a fact
established without touching outcomes, and that the 2026-09-11 master plan requires (4.2,
N3; 5.1). The fact is section 5k, registered the same day: three more tests of the same
question on the TOTAL (does a dated run-environment term beat the served model).
**Nothing in this amendment was measured against a game result.** No 5d-C value has been
read against anything (the correction above: counts only).

**What changes, three things, each a tightening:**
1. **The family.** 5d-C's criterion 1 is one member of family RE (section 5k: 5d-C, 5h-A,
   5k-A14, 5k-A30, 5k-B; family alpha 0.05, one-sided; Holm). Its p is the one-sided
   normal p of its registered t. Its bar is the Holm step that p lands on: t 2.326 to
   1.645 at m = 5, never below the registered 1.645. A disqualification by the
   observed-weather screen enters the family as p = 1 and stays in m.
2. **The read day.** 5d gave an earliest admissible look, 2026-10-07. 5d-C is now read in
   one run with the three 5k members, on 5k's read day R: the first day on or after
   2026-10-07 on which both harnesses are ready (committed, fixture tests passing) and the
   run completes. No result of either is opened before all are written. If 5d-C's harness
   is not ready by 2026-10-31, 5d-C is decided that day at p = 1 and never read; any later
   read is a new candidate.
3. **Early looks.** A run before R that computes 5d-C's criterion is a look, and 5d-C is
   decided that day at p = 1.

Everything else in 5d-C stands: its estimand, split, criterion 2, and the screen running
first. 5d-A, 5d-B, 5d-D and 5d-E are moneyline-calibration candidates, not members, and
their gates and dates are untouched.

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

**Correction (2026-09-25): the first qualifying vintage is `2026-09-13.json`,
and the earliest admissible first look is 2026-10-11.** A fact about filenames
and basis flags, recorded before the look and without reading any column value,
game, price or outcome (5c rule 1). `2026-09-11.json` and `2026-09-12.json` were
never written: the store holds `2026-09-10.json` (schema 4, no 5f columns) and
then `2026-09-13.json` (schema 5, covers through 2026-09-13), whose
`lineup_dis_vs_lhp` basis reads `platoon_splits.available True`. Under the
paragraph above, the clock starts 2026-09-13 and the earliest admissible first
look is **2026-10-11** (2026-09-13 plus 28 days). A look on 2026-10-09 or
2026-10-10 would come before the floor and disqualify the candidate. By the
resolver rule below, the 2026-09-12 and 2026-09-13 slates price off the
pre-repair 2026-09-10 vintage, so the first informative slate is 2026-09-14,
not 2026-09-12. The date is no longer typed anywhere it is enforced:
`leaderboard_vintages.dark_clock("5e")` reads the start off the store and
`dark_look_allowed("5e", date)` refuses any earlier date
(`test_leaderboard_vintages.py`). Nothing else in this amendment moves.

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

### Restart (2026-09-25, owner-signed): the per-hand HEM+ construction changes, and the clock restarts again

Recorded under 5c rule 1, before any look and before any number relates the
candidate to a game outcome or a price. **Nothing in this restart was measured
against a game result.** The paragraphs above are left as written; where they
date the clock, this restart supersedes them.

**The owner's answer.** 2026-09-25 ('more' batch 17): switch `hem_plus_split` to
the platoon-ratio estimator now, and the owner SIGNS the restart of the 5e
(handedness) and 5f (pinch-hit) dark clocks.

**Why the construction changes.** Census finding M06-05 (2026-09-24):
`hem_plus.split_hem_plus` reuses the season shrink (each wOBA component regressed
toward the hitter pool's mean by its own reliability constant) on the split's
smaller denominator, so a thin split is pulled toward 100, the league, rather than
toward the player's own level. On the served board (`hitter_leaderboards.json`
dated 2026-09-30, the 270 hitters with a per-hand value on both hands in the
constructed orders), the PA-weighted mean of the two hands minus season HEM+ has a
slope of -0.15 on (season - 100); hitters at 125 or better lose 4.7 points on
average (n 20) and hitters at 95 or below gain 2.2 (n 108). Yordan Alvarez reads
159 on the season, 168 against right-handers (508 PA) and 112 against left-handers
(184 PA). These are facts about how a column is built from hitter counting lines;
no game, price or outcome was read to find them.

**What the change moves.** The per-hand value on every slot of
`teams[].orders.vl` and `teams[].orders.vr` and on every bench row's per-hand
fields in `hitter_leaderboards.json`, and so every column built from them: this
gate's `off_vs_lhp` and `off_vs_rhp`, and 5f's `lineup_dis_vs_lhp`,
`lineup_dis_vs_rhp`, `bench_adv_vs_lhp` and `bench_adv_vs_rhp`. It moves no order
(the nine and its sequence are still built on season HEM+ and the `_platoon_adj`
heuristic), no season HEM+, no Offense+ and therefore no `z_off`: the served model
and every served price are unchanged. The estimator itself is pre-registered in
its own subsection below, before its constant is fitted.

**No look was taken before this restart.** The floor this restart replaces was
2026-10-11 (the 2026-09-25 correction above), `dark_look_allowed("5e", ...)`
refused every earlier date, and no harness has computed the candidate, its twin or
either criterion against any game. The stored `off_vs_lhp` / `off_vs_rhp` rows are
kept as written (vintages are immutable) and carry the old construction.

**The new earliest-look rule.** The same four-weeks-after-first-vintage rule as
the 2026-09-10 restart, counted from the first vintage written under the NEW
construction. A vintage is under the new construction when its own basis record
says so: the 5f hitter-column basis carries both `platoon_splits.available True`
and `split_estimator platoon_ratio_v1`, the marker the re-export stamps into the
hitter artifact's `platoon_splits` block. Vintages are first-write-wins, so the
first such file is the NEXT nightly vintage written after the re-export ships,
never a file already on disk. Postseason nights count toward the four weeks and
postseason games are graded, exactly as the 2026-09-11 amendment registered. The
date is not typed here: `leaderboard_vintages.dark_clock("5e")` reads the start
off the store, and `dark_look_allowed("5e", date)` refuses any date before the
start plus 28 days, and every date while no vintage carries the marker
(`test_leaderboard_vintages.py`).

**Which games inform the candidate.** A game priced from a vintage that predates
the first new-construction vintage carries the old column and is out of the 5e
eval set; the resolver rule (newest same-season vintage strictly before the game)
is unchanged, so the first informative games are the ones on the slate after the
first new-construction vintage. The 2026 regular season ended 2026-09-27, so the
2026 part of the eval set is postseason games only; the count by round is
reported, as the 2026-09-11 amendment requires.

**Not reopened.** The candidate, both criteria, the permuted twin, every threshold
and the postseason ruling stand as registered. Only the column's construction and
the clock's start move.

### The per-hand estimator `platoon_ratio_v1`, pre-registered (2026-10-01, before its constant is fitted)

Written before the shrink constant below is fitted and before the switch is
coded; the commit that fits it records the fit output and changes nothing here.
`hem_plus.py` carries the same text in its module docstring.

**The estimate.** For a hitter with a season line and a counting line against
each pitcher hand (`d_L`, `d_R` the wOBA denominators of the two lines, `x_L`,
`x_R` their raw wOBA):

1. Raw platoon ratio `q = x_L / x_R - 1`, defined when both lines exist and
   `x_R > 0`.
2. Its sample `n = d_L * d_R / (d_L + d_R)`: the variance of a ratio of two
   means scales with `1/d_L + 1/d_R`. A hitter missing a hand has `n = 0`.
3. Regressed ratio `q* = (n * q + K_b * mu_b) / (n + K_b)`, where `b` is the
   hitter's bat side (L, R or S; an unknown side uses the all-hitter values) and
   `mu_b` is this season's league mean ratio for that side: pooled wOBA against
   left-handers over pooled wOBA against right-handers, minus 1, over every
   hitter of that side with both lines. A side whose season pool holds fewer
   than 1,000 wOBA-PA on either hand uses the frozen 2016-2018 `mu_b` instead.
4. Spread around the season level so the two hands average back to it:
   `m_R = (d_L + d_R) / (d_L * (1 + q*) + d_R)`, `m_L = (1 + q*) * m_R`. Then
   `d_L * m_L + d_R * m_R = d_L + d_R` exactly, and a hitter with one line only
   gets `m = 1` on it.
5. The per-hand estimate is the season shrunk wOBA times `m_h`, i.e. season
   shrunk wOBA x (1 + regressed platoon ratio for that hand), scored to HEM+ on
   the SEASON pool anchor exactly as the season number is (so the league platoon
   effect survives, as the 2026-09-10 repair registered), rounded to the nearest
   integer. A hand with no line serves null, as today.

**The constant, fitted once.** `K_b` for L, R, S and all hitters, by the DEM+
precedent (`positional_fit.fit_signal`, year-over-year persistence): StatsAPI
`statSplits` (`sitCodes` vl and vr, `playerPool` All, regular season) for 2016,
2017 and 2018 and each season's `batSide`; pairs are the same hitter in
consecutive seasons (2016 to 2017, 2017 to 2018) on the same bat side with
`n >= 50` in both; `r` is the Pearson correlation of `q` across the pair, clamped
to [0.05, 0.95]; `hm` the mean of the pair's harmonic-mean `n`; `K_b = hm * (1 -
r) / r`, rounded to the nearest 10. A side with fewer than 30 pairs takes the
all-hitter K. As `fit_signal` notes, persistence also absorbs real year-to-year
change, so K errs toward more shrinkage. The frozen `mu_b` are the pooled
2016-2018 ratios by side. Nothing from 2019 on is read, no outcome of any game is
read, and the fit is never re-run against later seasons.

**Pass condition for the switch, on the re-exported board.** For hitters with
300 or more PA and a value on both hands in the constructed orders: the
split-PA weighted mean of the two hands is within 1 HEM+ point of season HEM+,
and the slope of that gap on (season - 100) is within 0.03 of zero (it was -0.15
under the old construction). Served betting probabilities on the day's board are
byte-identical before and after, because the served model reads `z_off` only.

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

### Restart (2026-09-25, owner-signed): the construction start is re-dated

Recorded under 5c rule 1 with the 5e restart of the same date (see it for the
owner's answer, census finding M06-05 and the measurements). **Nothing in this
restart was measured against a game result**, and no 5f look exists to have been
taken: the first is the end of the 2027 regular season.

**Why.** The four hitter-derived columns (`lineup_dis_vs_lhp`, `lineup_dis_vs_rhp`,
`bench_adv_vs_lhp`, `bench_adv_vs_rhp`) are season-PA weighted `hem_plus_split`,
and the candidate's `L` and `R` are 5e's `off_vs_lhp` and `off_vs_rhp`. All six
change construction when `hem_plus_split` switches to the platoon-ratio estimator.
`ph_share` and `pen_lhp_share` do not move.

**What is re-dated.** The construction start. Where this section says "schema 5",
read "schema 5 AND written under the new per-hand construction" (the basis marker
the 5e restart names): the eval set is regular-season games whose vintage carries
the marker; fit-half games whose vintage predates it enter with a delta of zero,
which makes them identical to the served model's rows; and 5c rule 2's four weeks
are four weeks of marker-carrying vintages. The 2026 regular season ended before
the new construction, so the whole eval set is 2027 games.

**What stands.** The end-of-2027-regular-season embargo (one look per season,
after the last regular-season game, no other look in either direction), the power
precondition, both criteria, the control, the postseason exclusion and every
constant. `leaderboard_vintages.dark_clock("5f")` reads the construction start off
the store and `dark_look_allowed("5f", date)` refuses any date before the start
plus 28 days or before 2027-10-06, whichever is later. 2027-10-06 is a floor, not
the look date: it is the day after the latest regular-season final day since 2016
(2022-10-05), so it can only delay a look and never admit one early; the look
still waits for the last 2027 regular-season game to be final, which a lockout or
a late schedule moves later.

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

### Amendment (2026-09-11): 5h-A is read inside the run-environment Holm family

Sections 5h-A to 5h-C are left as written. The fact is the same as the 5d amendment's,
on the same day: section 5k. Here the 5e correction's wording covers the amendment as
written ("before its clock opens"), because 5h's clock has not started. It only
tightens, and the 2026-09-11 master plan requires it (4.2, N3; 5.1). The owner answered on 2026-09-11: arm the capture, with the
5h-C Previous-Runs backfill. At HEAD 37e9382d the capture has not run
(`betting_weather.FORECAST_CAPTURE_ENABLED` is False), and no forecast has been related to
any outcome. **Nothing in this amendment was measured against a game result.**

**What changes, and only this.**
- 5h-A's criterion 1 is one member of family RE (section 5k). Its p is the one-sided
  normal p of the registered t of the LIVE arm, the arm 5h-C says governs.
- That p is 1 until the live arm reads, expected in 2027: 400 open-air live games are
  needed and about 180 accrue in 2026 (The clock above; plan 5.1).
- An archive-arm reading is reported beside it and never enters the family. This
  amendment adds no route by which the archive arm decides 5h-A.
- When the live arm reads, 5h-A's bar is the Holm step its p lands on over its p and the
  four p values recorded in 2026, unchanged, never below the registered 1.645. If it never
  reads, it keeps p = 1.

Everything else stands: the three additions, the split rule, criterion 2, the
contaminated leg, the permuted-venue twin (200, seed 20260911), the clock, and 5h-C's
agreement check. 5h-B is a props estimand under the dark props frame's own interval rule,
not a member.


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
`betting_export.SLOT_PA`; **pin withdrawn, see the 2026-09-17 amendment at the
end of this section**), switch hitters batting opposite the starter's hand,
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

**Correction (2026-09-25): the clock started 2026-09-13, so the earliest look
is 2026-10-11.** Read off the basis flags alone, before any look (5c rule 1):
the first vintage on disk meeting both conditions is `2026-09-13.json`
(`lhb_share_vr` n 30, `park_by_hand` n 29); the one before it,
`2026-09-10.json`, is schema 4 and carries neither column, and no vintage was
written for 2026-09-11 or 2026-09-12. Four weeks from 2026-09-13 is
**2026-10-11**; the "~2026-10-10" above and in the 2026-09-17 amendment below
is one day early, and a look on it would disqualify the candidate.
`leaderboard_vintages.dark_clock("5i-B")` derives the date from the store and
`dark_look_allowed("5i-B", date)` refuses any earlier one. The candidate, twin,
criteria and floor are unchanged.

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

### Amendment (2026-09-17): the hand-mix weights are a frozen literal, not a read of the served table

**Standing.** 5c rule 1 as the 2026-09-10 (5e) and 2026-09-11
(`lineup_strength`) corrections read it: a pre-registration may be amended
before its first look, on a fact established without touching outcomes. 5i-B
has not been looked at, and cannot have been: its clock starts with the first
vintage carrying `lhb_share_vr` n = 30 AND `park_by_hand` n >= 29, `fa_meta`
has not yet written the `park_factors_by_hand` sibling, and the earliest
admissible look is ~2026-10-10. **Nothing in this amendment was measured
against a game result, a price or a market.** Read to write it: the plan's
repair 8 (`docs/master-plan-2026-09-11-war-epoch-drivers-betting.md` 4.2), the
R5 lane record D4, audit finding L17-F3, the code
(`leaderboard_vintages.LINEUP_SLOT_PA`, `betting_export.SLOT_PA`,
`test_betting_ballpark`), and a count of plate appearances by lineup slot off
`.cache/pbp_corpus`. No column value, no score, no run, no win probability and
no price was read.

**What changes.** The registration above weights each slot's bat side "by the
PA-by-slot table (`LINEUP_SLOT_PA`, pinned equal to `betting_export.SLOT_PA`)".
**The pin is withdrawn.** The weights are FROZEN here as a literal, exactly the
way 5j freezes the same table for its own candidate: 4.65, 4.55, 4.45, 4.35,
4.25, 4.15, 4.05, 3.95, 3.85 for slots 1 to 9 (sum 38.25). That is today's
`leaderboard_vintages.LINEUP_SLOT_PA` and it does not move. A later repair of
`betting_export.SLOT_PA`, or of any served constant, does not reach
`lhb_share_vr` or `lhb_share_vl`.

**Why now.** A dark column's constant pinned to a served constant is stop item
X4 (plan 4.2): the served table can be repaired for served reasons at any time,
and a pin turns that repair into a silent change of a dark column's input
membership, which is stop item X9. The served table is due for repair under
plan repair 8 (L17-F3: the rule hands nine starters 38.25 plate appearances out
of the roughly 37.8 a team-game carries), so the pin is withdrawn BEFORE that
repair rather than discovered after it. The order matters and it is the order
the plan asks for: freeze first, then repair.

**Nothing captured moves, and no clock moves.** `LINEUP_SLOT_PA` keeps the nine
numbers it has carried since the column was registered, so every vintage
record's `lhb_share_vr` and `lhb_share_vl`, on disk and to come, is what it
would have been with no amendment at all. 5i-B's membership, its four-week
floor, its ~2026-10-10 earliest look, its candidate function, its swapped twin
and its criteria are untouched. This is the same-day X9 note for a change that
does NOT move a dark column's input membership, written so the next reader can
see the membership was checked rather than assumed. 5c-B's `lineup_strength`
keeps its equal slot weights and the slot-PA-weighted form stays embargoed
there. 5i-C's `HR_HAND_SPLIT_RELIABILITY` pin is a different pin, to a
reliability constant and not to a PA table; it is not touched here and stands
as registered.

**The test that held the pin.** `test_betting_ballpark` asserted
`lv.LINEUP_SLOT_PA == be.SLOT_PA` under the name
`test_one_pa_by_slot_table_on_the_site`. That assertion IS the X4 pin in
executable form, so it is replaced by a pin to the nine literals above, under a
name that says what it now protects. The comment in `leaderboard_vintages` that
named the equality is corrected here, with this amendment, ahead of the repair
that will make it false.

**What this amendment does not do, and what the repair beside it DOES do.**
This amendment does not change any served number: it freezes a dark column's
weights at the values they already carry. The repair it clears the way for is a
different matter and must not be read as covered by that sentence. Plan repair
8 replaces `betting_export.SLOT_PA` with a measured, home-and-away-split table,
and that DOES move a served number: every hitter props fair line and every
served props Over probability on /betting/ falls, one-signed. The size and the
sign are recorded in section 11 with the flag that carries them
(`SERVE_SLOT_PA_MEASURED`), not here, because this section is 5i's and the
repair is the props table's. What neither half touches is the moneyline, the
runline or the total, which is what `MODEL_VERSION` tracks, so neither half
bumps it. Neither half measures 5i-B, names a result, or moves a date, and
neither licenses reading `lhb_share_vr` or `lhb_share_vl` for anything before
2026-10-10.

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
`/schedule` hydrated `lineups,probablePitcher`, at zero Odds API credits, read through
`tools/betting_lineup_job.fetch_schedule` (BUILT at `78c22d7a`, line 207). This sentence
asked for "a new helper beside `fantasy_schedule.fetch_lineups`, to be built"; it was
built inside the job instead, because it needs its own game types and its own cache
clock, which is the reason the 2026-09-17 arming note gives. `fetch_lineups` itself,
which `/dfs/` reads, cannot serve: it hydrates `lineups` only, caches one file per day
(`lineups_<day>_<game_type>.json`, 12-minute TTL) and returns
`{game_pk: {home: [ids], away: [ids]}}`. It drops each player's `primaryPosition`, the
game's status and time, and the probables. The helper keeps its own cache, so the
3-hour probable cache and the 12-minute lineup cache do not fight (R4 section A). The
raw response lists each side's card in batting order with `id`, `fullName` and
`primaryPosition`, and carries no bat side. Bat side joins from the hitter board and
pitcher hand from `pal_export.load_pitch_hand`. The job is `tools/betting_lineup_job.py`
(BUILT at `78c22d7a`; the list below is the spec it was built to, kept as
written), modelled on `tools/betting_close_job.py`:
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
`starting_nine(feed, side)`, BUILT at `78c22d7a` in `tools/betting_lineup_job.py`, and
`test_betting_lineup_job.py` pins it against the array on a feed with a substitution.
The `fetch_lineups` docstring's "verified" claim covers the posted card's ORDER only,
and that correction has been made (see the 2026-09-17 arming note below).

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
  only because `RECORD_PUBLISH_ARMED` is False. (2026-09-25: the guard is built and
  tested in `test_betting_slot_lock.py`, and the owner armed the record in writing the
  same day, so `RECORD_PUBLISH_ARMED` is now True.)
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

**Correction (2026-09-17), the arming of the capture job and the close job that
will not be installed. Recorded rather than written over the paragraphs above.**
Two owner answers of 2026-09-17, recorded as dated operational corrections
before the 5c B3/B4 look is recorded. Neither changes what this section grades.
Both change what can feed it.

*The capture job is armed.* `tools/betting_lineup_job.py` exists as of this date
and is armed on 2026-09-17 by owner decision, phase 1 capture only, at zero
credits, and it moves no served price. That is the default under Arming (owner
decision O17) confirmed, not a change to it. The cron line is NOT installed by
this change: the job ships with `*/15 * * * *` under `TZ=UTC` as its intended
entry, and `--selfcheck` reports NEVER RUN on this machine until a scheduler
reaches it. Phase 2 still waits on the slot lock and the record guard, as Arming
says.

Two details of the job differ from the Capture paragraph above and are recorded
rather than written over it. The fetch helper lives inside
`tools/betting_lineup_job.py`, not beside `fantasy_schedule.fetch_lineups`,
because it needs its own game types and its own cache clock. And the correction
that paragraph owes to the `fetch_lineups` docstring, whose "verified" claim
covers the posted card's ORDER and not the completed feed's array, HAS BEEN MADE
(re-read 2026-09-18): the docstring now carries it under "WHAT THAT CHECK IS
NOT, corrected 2026-09-17", keeps the half that is true about the card, and
points at `tools/betting_lineup_job.starting_nine` for the nine who started.
This paragraph said it was still owed, which stopped being true in the same
batch it was written in.

The job's pre-call gate reads a slate the job writes itself, under
`.cache/lineup_captures/`, and never `data/fantasy.json`. Three properties of
that artifact rule it out, and the first was observed on this date: its
19:31:22Z build carried an empty schedule block while StatsAPI held a full card
for the same date, because its producer degrades to an empty list on any failure
and says nothing. A rebuild later the same day filled it, which is the point:
downstream, nothing distinguishes the two states. It is also regular-season
only, while this job must ask for R, F, D, L and W. And it is tracked, so the
nightly `git checkout -- .` reverts it, the same line this section cites as the
reason the capture store lives under `.cache/`. A gate on it would have exited
before the call on every invocation of that hour while stamping a healthy
heartbeat, which is the one shape Leg M's gap rule cannot see. The heartbeat is
therefore two files: a last-run stamp, and an append-only run log, because a
last-run stamp is overwritten every fifteen minutes and can never show a gap.

*O16 is answered NO.* The close job will not be installed by owner decision of
2026-09-17. The Captures bullet under Leg M still reads "owner decision O16,
OPEN; DEFAULT install now", and the plan's decision table
(docs/master-plan-2026-09-11-war-epoch-drivers-betting.md, the row that reads
"Install all three now") still carries that default. Both are corrected by this
note, and neither is edited from here.

O18 therefore stays at L-0 by its own conditional default, which reads "L-0
until the close job is verified running, then L-1". With O16 declined there is
no close job to verify, so no snapshot of kind `close` and no snapshot of kind
`lineup` will exist for a 2026 game. Leg M reads one of those two kinds. It has
no price source and cannot be scored.

*What this does NOT do.* O19's default stands: Leg M qualifies. Leg M is
BLOCKED, not replaced. This is not a switch to the fallback form under Verdict,
which activates only on an O19 answer of no. So this section keeps accruing
captures and can read Leg O, and it cannot reach a PASS on its registered
default form until a post-lineup price source exists. The Lapse clause above
already names this state ("That could happen ... if O18 stays at L-0") and its
2028 deadline is unchanged.

*The consequences, stated narrowly, because one of them was overstated when this
was decided.* True: no CLV for any 2026 slate, and CLV is unrecoverable after
the fact; `betting_close_job.attach_closes` never fires, so the calibration
ledger's market-move block stays empty; Leg M is unfeedable, so 5j's qualifying
leg is blocked. It does NOT block the third publish gate: `graded_price_history`
counts settled shadow rows carrying the price taken from that slate's OPEN
snapshot, and no close price enters that path.

No count, capture tally, result or price relation is recorded here, and no
number has been computed on this candidate.

## 5k. Run environment: trailing league scoring and a calendar-month offset (pre-registered 2026-09-11)

**Written before any function, table, constant or flag below exists in code, before
either term has been computed for any date, and before any pre-2026 season has been
read for it**, in the discipline of 5a, 5c, 5d, 5h and 7b. No served number changes: the
one served-code change is a keyword whose default reproduces today's output bit for bit
(below).

**Disclosed, because 5c rule 1 turns on it.** These outcome summaries are on the record
and were known when this was written. Each describes outcomes over a season or a split
window. None is a trailing league mean, a month offset or either term below.
- 7f, the vintage fit half (305 games before 2026-08-01): mean actual total 8.8066
  against the model's 8.8649, median 8; observed Over 0.5344, 0.4328, 0.3869, 0.3213 at
  7.5 to 10.5; 8.9632 over all 2,200 games. The centre deltas fitted on the four growing
  fit halves: -0.2731, -0.1949, -0.1754, -0.1771. The incumbent's Over +0.044 above the
  realised rate on 292 anchored eval games with an open capture.
- 7g and 7h: the 7g run printed each split's eval-half observed Over rate at the four
  lines (0.560, 0.485, 0.385, 0.327 on the anchored split; 0.347 at 10.5 on the 0.6
  split; 0.350 at 10.5 on the 0.7 split), and 7h records Over 7.5 observed 0.615 after
  2026-08-29 and that the misses sit where the run environment moved. The four eval
  windows are NESTED (cuts 2026-08-01, 08-16, 08-22, 08-29), so differencing them would
  give disjoint-window rates, a coarse dated series of 2026 league scoring. That has not
  been done.
- Section 4: league run environment 4.494 runs per team per game (the full-season fit).
- `lg_rpg`: `build_context` writes the season-to-date league runs per team-game with
  `n_games` (`betting_model.py:3798`) to the tracked `data/betting_model_context.json`,
  and `/betting/` shows it (`assets/betting.js:2070`). It is display only; no price reads
  it. Two dates' `lg_rpg x n_games` difference exactly to a trailing-window league mean,
  a close variant of 5k-A. No two copies have been differenced or related to a later
  game.

Those rates are why this section exists; 7h names "a dark run-environment feature with
its own section" as the next admissible attempt. No number relating either arm, or any
close variant named under Disqualification, to a later game, a total or a price has been
computed.

**Where the pieces come from.** The two windows are the house's two trailing windows,
both fixed before 7g or 7h printed anything: `xwoba_14` and `xwoba_30` (5c, 2026-08-16)
and the trailing 30 days of the 5d-C climatology (5d, correction of 2026-09-07). The
2026-09-11 master plan adopts the same pair (4.2, N3). No other window length is read in
this section. The offset is the 2026-09-05 plan's B-TOTAL stage 1a ("calendar-month EB
offset fitted on pre-2026 finals, the one dated-results feature that is vintage-safe by
construction"), written before 7g and 7h ran.

**Why a league term.** The team inputs enter standardized across clubs
(`_assemble_team_inputs`), so the league's scoring level reaches a price mainly through
the intercept: 2*b0 + b4 is +9.0023 on the total over the 7f fit half, against -0.0041,
-0.0807 and -0.0526 from the offense, prevention and park terms (7f). The intercept is
fitted over a window that ends before the game: the vintage fit half in every gate, every
completed game in the served build (section 4). When the league's scoring moves after
that window, every later total inherits the gap. No price reads the league's recent
scoring.

**Sources, and one served-code hook.**
- Arm A's 2026 values read `completed_games("2026")`, the results cache at
  `.cache/betting/completed_games.json`, regular season on both of its doors (the feed
  walk drops `game.type != "R"`, `_row_from_schedule` drops `gameType != "R"`). The season
  argument is pinned: `completed_games(None)` returns every cached season.
- The pre-2026 fits (arm A's `k_w` and arm B's table) read 2018, 2019 and 2021 to 2025
  regular-season finals from `fetch_finals`, one StatsAPI schedule request per season,
  seven in all, no credential and no credits. The `.cache/pbp_corpus` plays table carries
  no date (`tools/build_pbp_corpus.py`, `_schemas()`). 2020 is excluded; the corpus holds
  none. The fetched rows are stored under `.cache/betting/` (to be built), never `data/`.
- **The census check.** Each season's count is reconciled against the 2026-09-05 plan's
  B-CORPUS census, "2431/2429/2429/2430/2430/2429/2430/2124, no 2017 or 2020". The
  season labels are inferred from that order (2018, 2019, 2021 to 2026); the seven
  pre-2026 entries sum to 17,008, the pre-2026 game count the 2026-09-11 plan gives for
  `.cache/pbp_corpus` (4.2, N1). The census counts the `.cache/win_prob` play corpus, not
  schedule finals, so the check compares two sources. Any difference is resolved on
  `game_pk` lists alone, with no runs field read, before any slope, offset or runs mean
  is computed. The prefit refuses to fit while a difference is unexplained, and the
  resolution is written into the Fitted block. No season is dropped once any slope,
  offset or runs mean of it has been computed.
- **Row rules, the same for every window mean, every pre-2026 fit and each contaminated
  screen:**
  - deduplicate `game_pk`, counted;
  - drop a row whose `season` is not the season requested, counted (the range trap
    `_topup_game_cache` documents);
  - drop a row with no `innings` or `innings` below 9, counted (7i's rule: rain-shortened
    games, and 2021's seven-inning doubleheaders);
  - drop every RESUMED game, counted: a game whose final was recorded on a date other
    than its `date`. `feed_cache.py:104-105` and `:171` record that a
    suspended-then-resumed game keeps its original date, so a reconstruction that kept it
    could hold a final that was unknown on D. No results row carries a resume marker
    today (both doors write the same ten keys), so the lookup is to be built: a
    `resumed_on` read from each game's cached feed or schedule entry, kept inside the dark
    builders and never added to `_row_from_schedule`'s served row shape. A `game_pk`
    listed on two schedule dates is treated as resumed. A game whose resume status cannot
    be resolved STOPS the build with its `game_pk` named; it is never silently included.
  - The graded eval set is not filtered by these rules. It is the 7f to 7h labs' own
    rows, so the incumbent is scored on the games those labs score.
- **The hook.** The term is league-level and in runs, so it does NOT pass through
  `_assemble_team_inputs` (standardizing a value every club shares on a date would zero
  it). It enters the run rows `expected_runs` builds, beside the park term, through a
  keyword `env_runs` on `expected_runs` (to be built, default 0.0). A test pins that the
  served output is bit-identical at the default and that no served caller passes it. The
  value comes from one dark function the live and vintage paths share,
  `betting_model.run_environment_term` (to be built), which nothing served calls, pinned
  by a test.

### 5k-A. Trailing league scoring, two windows (members 5k-A14 and 5k-A30)

**The number.** For a game on date D and w in {14, 30}, `R_w(D)` is the league's runs per
team-game (both clubs' runs over twice the games) over every qualifying regular-season
final of D's season whose `date` falls in the w calendar days ending D-1. Games on D never
enter, so game 2 of a doubleheader never reads game 1. A window holding fewer than half
the games that 13.1 completed games per calendar date (section 5) would give it, rounded
up (92 for 14 days, 197 for 30), gives no term for D. Such a game is excluded from that
member's eval half and from its `Rbar_w`, and counted.

**Vintage safety and provenance.** Each row's `covers_through` is the newest final date
in its window, always before D, so the 5a cutoff `covers_through < D` holds. That
definition replaces section 5's max over sources and the write date, which would stamp a
reconstructed row with its build date. It is the O22 ruling's definition (the 2026-09-05
plan, 6.5: "`covers_through` = last play date"). The build that prices D runs at 03:10 ET
(the 2026-09-11 plan, 4.1), after the D-1 slate. A D-1 final not yet in the results cache
at that hour is missing from that build's window, so a reconstruction is at least as
informed as a live build, and never more than by a late D-1 final, because resumed games
are dropped. Every past date's value is REBUILT from the results cache. Each row carries
`provenance.source: "archive-reconstruct"` (5a's record shape), `covers_through`,
`window_days`, `n_games` and each drop count. Rows are counted apart from live and
git-backfill records, never blended (5a). Arm A reconstructs no clocked dark column (the
plan's N1 rule): it reads finals and nothing a vintage stores.

**DEFAULT, owner decision O22 open:** archive-reconstruct provenance is allowed, labelled
per row (the 2026-09-11 plan, section 6).
- Refused before the read: 5k-A14 and 5k-A30 are decided on the read day at p = 1 and are
  not computed. A read from a live nightly record of the window is a new candidate, with
  its own section and its own family, in 2027.
- Refused after the read: each A member's verdict is voided (recorded, never servable).
  No other member's decision is revisited.

**The term,** the same amount on both sides:

    raw_S' = raw_S + k_w * (R_w(D) - Rbar_w),   S in {home, away}

`raw_home` and `raw_away` are the run rows `expected_runs` builds before the midpoint, the
differential shrink and the [1.5, 9.5] clamp, so the pair mean moves and the
half-difference does not. `Rbar_w` is the game-weighted mean of `R_w` over the split's
fit-half games that carry a term. This is 5h's addition 2 applied to one regressor: "Both
regressors are de-meaned on the fit portion and enter with no intercept, so the candidate
cannot absorb a level error by construction." The term averages zero where the
incumbent's intercept was fitted. A serving pricer de-means by the same rule over the
games it was fitted on.

**`k_w`, fitted on 2018-2025 only.** Pooled over the seven seasons, no intercept, weighted
by team-games on D (twice the qualifying finals dated D):

    x(D) = R_w(D) - mu_s,   y(D) = L(D) - mu_s,   k_w = sum n_D x y / sum n_D x^2

`L(D)` is the league's runs per team-game over the qualifying finals dated D, and `mu_s`
is season s's runs per team-game over all its qualifying finals. The sum runs over every
regular-season date with a qualifying final whose window meets its floor. `mu_s` is a
season fixed effect and nothing more.

**One centring mismatch, reported and not corrected.** Before 2026, `k_w` is the slope
around each FULL season's mean. In 2026 the term is centred on the split's FIT-HALF mean
of `R_w`, the only centre knowable at pricing. These are different centres.

**Reported in the Fitted block:**
- per-season slopes, which are descriptive, and no season is dropped after they are
  seen;
- a season-block bootstrap: 1,000 resamples of the seven seasons with replacement,
  `numpy.random.default_rng(20260911)`;
- the 2023-2025 slope beside the pooled one, descriptive and never substituted;
- every count and drop.

A `k_w` at or below 0 records that member NULL BY CONSTRUCTION: no 2026 comparison is
computed and it enters the family at p = 1.

**Why 2018-2025 and not 7i's 2023-2025.** 7i fits how a game ENDS, which the 2023 rules
changed (the automatic runner, the pitch clock), so it takes the seasons under 2026's
rules. `k_w` and the month table are within-season shapes measured against each season's
own mean, so the season fixed effect absorbs a rule change's level. Seven seasons also
give arm B's `V(m)` seven points where three would give three. The 2023-2025 readings are
reported beside the pooled ones so a rule-era difference is visible.

### 5k-B. A calendar-month offset, fitted on 2018-2025 (member 5k-B)

**The table.** Six bins: April (March games pooled in), May, June, July, August,
September (regular-season October games pooled in). For season s and bin m, `d(s, m)` is
the league's runs per team-game over its qualifying finals in bin m, minus `mu_s`.
`dbar(m)` is the mean of `d(s, m)` over the seven seasons, and `V(m)` is its sample
variance over them (ddof 1). Normal-normal empirical Bayes toward zero, by the method of
moments:

    A    = max(0, mean over the six bins of [dbar(m)^2 - V(m)/7])
    o(m) = A / (A + V(m)/7) * dbar(m)

`A` = 0 records the member NULL BY CONSTRUCTION, as above.

**The term.** `raw_S' = raw_S + (o(m(D)) - obar)` on both sides, placed as in 5k-A. `m(D)`
is D's calendar month, binned as above, and `obar` is the game-weighted mean of
`o(m(D))` over the split's fit-half games. The pass-through is 1 and is not fitted: `o`
is already in runs per team-game and already shrunk. Rows carry
`provenance.source: "pre-2026-fit"`, the seasons and a digest of the table.

**What neither arm does.** Neither fits a parameter on a 2026 game. That keeps 5k outside
X1 (the 2026-09-11 plan, 4.2: no fourth one-parameter total repair fitted on the
305-game fit half) and inside that plan's section 5 rule: arm A is archive-reconstructable
and arm B is fitted on pre-2026 data. **No 2026 outcome is read to build either term.**
The windows, floors, row rules, `k_14`, `k_30` and the table are fixed here or fitted on
2018-2025. Arm A's VALUE on D reads 2026 finals dated D-1 and earlier: the cutoff every
vintage obeys, and information the build that prices D already holds. The de-meaning
constants read those dated values, never a priced game's own result.

**Frozen before the read.** `k_14`, `k_30`, the table, their input counts, the bootstrap
readings and the power figures below are written into this section as a dated block
(`### Fitted (DATE): the 5k pre-2026 constants`). They are also literals in
`betting_model.RUN_ENV_PRE2026` (to be built), pinned to that block by a test and never to
a served constant (plan X4). The same test pins every choice in "Choices pinned" below.
The fit is `tools/betting_run_env_prefit.py` (to be built), deterministic, and reads no
2026 game. The block is committed before 2026-09-28. Re-fitting any constant after its
block is committed disqualifies the member.

**Power, stated in the Fitted block, never a criterion or a precondition.** On 2018-2025
only, the prefit reports:
- `RMS_T`: the RMS of each member's term on the TOTAL (twice the per-side term),
  centred on each season's mean;
- `sigma_T`: the sd of a game's total about its season mean;
- the ceiling `t* = sqrt(n_eval) x RMS_T / (sigma_T x sqrt(2 pi))`. This is the expected
  criterion-1 t if the term were exactly right, errors were normal and games were
  independent. It is evaluated at each split's n_eval once the read fixes n_eval.

The read reports `RMS_T` on each eval half from the terms alone. Unlike 5f, there is no
UNDERPOWERED rule: the result stands whichever way it lands.

### The 5k gate

**The incumbent** is the served model on the read day, whatever `MODEL_VERSION` and flags
serve that day (the owner's 2026-09-11 A's-park and runline answers included). It is
refit on each split's fit half (coefficients, tie rate, differential shrink, home
adjustment) as the 7f, 7g and 7h labs do. Each challenger is the incumbent plus one term,
with nothing re-solved (5h-A's rule).

**Why 5h-A's rule governs here and not 11a's re-solve rule.** 11a re-solves because a
dispersion changes the margin's shape, so a fixed `diff_shrink` would be "rigged toward
Poisson". This term moves only the pair mean:
- `diff_shrink` scales the half-difference and holds the pair mean;
- the home adjustment enters as +adj/2 and -adj/2 and cancels in the total;
- the tie rate prices the moneyline only.

So criterion 1 is untouched by all three. Criterion 2 feels the term only through the
Poisson spread and the clamp, and a fixed shrink there, if anything, handicaps the
challenger on a non-degradation condition, which is the conservative side.

The lab is `python betting_model.py --run-environment` (to be built). It writes
`data/betting_model_eval.json -> run_environment`.

**Sample and splits.** The graded sample is the 2026 regular-season games in
`completed_games("2026")` that the vintage resolver grades, whatever the read day. The
splits are the 7f/7g/7h set: the anchored served split and date quantiles 0.6, 0.7 and 0.8
of that sample's gradable dates. Because the sample is fixed once the regular season ends
(2026-09-27, the 2026-09-11 plan section 5), the cuts do not move with the read day; each
cut is written into the result. Each split needs a fit half of at least
`VINTAGE_MIN_FIT_GAMES` (100) and an eval half of at least `VINTAGE_MIN_EVAL_GAMES` (50),
or it cannot pass. The results set is regular season on both doors, so postseason is never
graded. The owner's 2026-09-11 answer that counts postseason belongs to 5e and does not
reach here.

**Criteria, the 5d-C form, per member, at ALL FOUR splits.**
1. Paired absolute error on the game total, incumbent minus challenger, greater than 0 at
   the member's Holm threshold in family RE (below). Each model's scored total is
   `lam_home + lam_away` as `expected_runs` returns them, before any total-pricing layer,
   so no 7f, 7g, 7h or 7i flag moves either number.
2. Moneyline paired Brier not worse on the point estimate.

**Choices pinned.** Each is fixed here, pinned by the `RUN_ENV_PRE2026` test:
- **Criterion 1's t.** The per-game difference is `d_i = |err_inc,i| - |err_chal,i|`, and
  `dbar` is its mean over the N eval games. The standard error is clustered on date with
  the CR1 small-sample factor, because every game on a date shares the term:
  `S_g = sum over games on date g of (d_i - dbar)`, `SE = sqrt(G/(G-1) x sum_g S_g^2) / N`,
  `t = dbar / SE`. G is the eval half's date count. The split's one-sided p is the upper
  tail of a t distribution with G - 1 degrees of freedom, not the normal, because G is
  small at the 0.8 split.
- **Seeds.** `numpy.random.default_rng(seed)` for seeds 0 to 199, one permutation per
  seed.
- **The twin's bar.** `numpy.percentile(improvements, 95)` with its default linear
  interpolation over the 200 twin improvements. The member must exceed it strictly.
- **Row rules, the census response and `V(m)`'s ddof,** as written above.
- **The screens** use each member's frozen pass-through and de-mean by that member's own
  rule over the fit half, as written below.

**Control, the permuted-date twin, required at every split.** This is the 5c rule 3
control, permuted across dates because every club shares the term on a date.
- 5k-A: within each split's eval half, permute the dated term across the eval dates (a
  date's games move together), with `Rbar_w` untouched. The twin keeps the eval half's
  mean shift and breaks the dating, so a member that is only a level shift ties its twin.
- 5k-B: permute the six offsets across the six bins, then de-mean on the fit half. A
  dated permutation would be the identity at a split whose eval half lies in one month.

At every split, the member's mean paired improvement on criterion 1 must exceed the twin's
bar.

**The contaminated screen runs first and can only DISQUALIFY.**
- 5k-A: the member with `R_w(D)` replaced by `S(D)`, the league's runs per team-game over
  the qualifying finals dated D (the graded game's own included). It uses the member's
  frozen `k_w` and is de-meaned by the same rule over the fit half. This is the league's
  scoring that same day, at the member's own pass-through, so it differs from the member
  only in what it knows.
- 5k-B: 2026's own realized offsets `d(2026, m)`, over the full 2026 regular season, at
  pass-through 1, de-meaned the same way.

Both are labelled contaminated. A member whose contaminated version does not improve
criterion 1 on the point estimate at every split is disqualified: if the league's actual
scoring that day or month does not help, a trailing or climatological estimate of it has
nothing to find. A disqualified member's numbers are computed and reported, and it enters
the family at p = 1.

**The expectation, stated before any number: criterion 1 is hard for this candidate.**
Absolute error is minimized at the median, and the served total sits above where totals
split: on the 7f fit half the model's mean total is 8.8649 against an actual median of 8,
and on the 292 anchored eval games with an open capture its Over sits +0.044 above the
realised rate (both 7f). Where the league scores above its fit-half level, each member
raises a centre that is already above the median, and absolute error charges for that even
when the new mean is right; 7h's disclosed grid says the late eval window ran hotter. So a
FAIL on criterion 1 is not evidence that league scoring carries nothing about tonight's
total. The criterion is kept because 5d-C and 5h-A are read under it, and a family read
under two criteria is not one family.

**Reported whichever way it lands, never qualifying.**
- the effective n and every count dropped (window floor, each row rule, clamp hits at 1.5
  and 9.5);
- each term's mean, sd, range and `RMS_T` on both halves of every split;
- paired SQUARED error on the total with its t (the loss a mean is consistent for);
- the 7f grid log loss at 7.5 to 10.5;
- criterion 1 by roof type (open, retractable, dome, from `betting_weather.venue_table`);
- market diagnostics, never criteria: the positive-edge Over/Under split, and model
  P(over) minus the realised rate on games with an open capture;
- the twin distributions and both screens;
- each member's correlation with 5d-C's climatology term on shared games;
- the Fitted block.

### The run-environment Holm family (RE)

**Members, one test each.** 5d-C, 5h-A, 5k-A14, 5k-A30, 5k-B: m = 5. All five ask one
question of the TOTAL: does a dated run-environment term beat the served model. A member's
one test is its criterion 1. Three choices are decided in this section, not taken from the
plan, which states no alpha for this family:
- **Family alpha 0.05, one-sided.** That is the level 5d-C and 5h-A were registered at
  alone, so joining can only raise a member's bar.
- **Criterion 2, twins and screens carry no alpha and add nothing to m.** They are
  point-estimate conditions and controls, not tests with a size. This departs from the
  plan's PROSPX rule that "both legs of every arm count in m" (section 2.3), which is
  written for arms whose legs are both tests.
- **5d-A, 5d-B, 5d-D and 5d-E are not members.** They are moneyline-calibration
  estimands. Plan 5.1's row ("5d A-E (schema 4) and 5k run environment, one Holm family
  with 5d-C and 5h") can be read either way. The R5 lane's N3 names 5d-C and 5h only, and
  this section follows it. Also not members, with their gates standing as registered:
  - 5h-B, a props estimand under the dark props frame's own interval rule;
  - 5i-B, a venue-by-lineup park term, not a date-level environment.

**Why one family and not 5k alone.** Read apart, 5d-C, 5h-A and a 5k-only family would
each spend 0.05. If the three were independent, the chance that some run-environment term
clears by luck would approach 1 - 0.95^3 = 0.143. It is one question asked five ways, and
the plan puts 5k in one family with 5d-C and 5h (4.2, N3; 5.1). Joining tightens 5d-C and
5h-A, so it is recorded as an amendment to each, below, and only in that direction.

**The procedure.**
- **The p values.** A 5k member's p at a split is the t_(G-1) p pinned above. 5d-C's and
  5h-A's p is the one-sided normal p of the t their own sections register, so p <= 0.05
  exactly when that t >= 1.645. A member read at several splits, all required, takes its
  LARGEST split p: an intersection-union test is level alpha at its largest component.
- **Holm.** The j-th smallest p is compared with 0.05 / (m - j + 1), stopping at the first
  that fails. Ties are ranked in the member order listed above. At m = 5 the normal
  equivalents are t 2.326, 2.241, 2.128, 1.960 and 1.645, so no member's bar falls below
  the 1.645 it was registered at. A 5k member's bar in t is the t_(G-1) quantile at the
  same p, which is higher at every finite G.

**Members read on different dates.** Each member is decided ONCE, on its own read date, by
Holm over the p values on record that day, with every unread member at p = 1. It is never
revisited. Holm is monotone in the p values: lowering an unread member's p from 1 can only
add rejections. So every rejection made this way is one a single Holm run over all five
would also make, and the family-wise error stays at most 0.05. The price is that a member
decided early is never promoted by a later member's small p. A member that never reads
keeps p = 1, and a disqualified or NULL BY CONSTRUCTION member enters at p = 1 and stays in
m.

**5h-A's date and p.** On 2026-09-11 the owner armed the forecast capture with the 5h-C
Previous-Runs backfill. At HEAD 37e9382d, `betting_weather.FORECAST_CAPTURE_ENABLED` is
still False, and that day's 03:10 ET nightly has run, so the first armed night is
2026-09-12 at the earliest and four weeks put 5h-A's earliest look at 2026-10-10. The
live arm also needs 400 open-air live games, and about 180 accrue before the season ends
(5h, The clock), so the live arm reads in 2027 (plan 5.1). 5h-C says "the live arm
governs". So:
- 5h-A's p in family RE is the governing live arm's, and it stays 1 until that arm reads.
- An archive-arm reading in 2026 is reported beside it and never enters RE. This
  amendment adds no route by which the archive arm decides 5h-A.
- 5h-A's decision, expected in 2027, is Holm over its p and the four p values recorded
  in 2026, unchanged.

**A member PASSES** only when all of these hold:
- Holm rejects its null;
- criterion 2 holds at every split;
- it beats its twin at every split where its section registers one;
- no screen disqualified it.

**The labels.** A member's rank j is its place among the family's p values on its read day,
and its per-split bar is p <= 0.05 / (m - j + 1) at that split.
- FAIL: it clears that bar at no split.
- INDETERMINATE: it clears at some splits but not all, as 7h did.
- FAIL (Holm stopped): it clears at every split but Holm stopped at an earlier step.

**If an amendment block is missing.** Family RE is the three 5k members plus each of 5d-C
and 5h-A whose amendment block is committed in this document before 2026-09-28. m is 3, 4
or 5 accordingly, and the bars follow the formula above. That is fixed by the commit
history before the 2026-09-28 printouts, not by any result.

### When 5k is read

**The read day, R.** 5d-C and the three 5k members are computed in one run. That means one
invocation of `--run-environment`, which computes 5d-C through 5d-C's own harness, or
back-to-back invocations on the same day. Every member's result is written before any is
opened. R is the first day on or after 2026-10-07 on which both harnesses are ready and
the run completes. 2026-10-07 is 5d-C's earliest admissible look (5d, correction of
2026-09-11; plan 5.1). The last read date is 2026-10-31, a date decided in this section.
A trailing league mean and a venue temperature climatology are close variants (both
follow the season's warming and cooling), so neither is read before the other:
- **Ready** means the member's harness is committed to the repository and its fixture
  tests pass. For 5k, the harness is the builders, `run_environment_term`, the `env_runs`
  keyword, the lab, the prefit and the committed Fitted block.
- **A 5k harness first ready on or after 2026-09-28**, the date of the first 2026 printout
  after this commit, still computes on R and is reported, but its three members enter RE
  at p = 1.
- **If 5d-C's harness is not ready by 2026-10-31,** 5d-C is decided that day at p = 1 and
  never read; any later 5d-C read is a new candidate. The 5k members read on 2026-10-31.
  5d-C is at risk: its climatology columns exist only from the 2026-09-09 vintage (5d,
  correction of 2026-09-11), and the anchored fit half ends 2026-07-31.
- **A slipped run** (box, cache or feed failure on R) runs on the first day it can, no
  later than 2026-10-31, with the same code.

The sample does not grow after 2026-09-27, so waiting changes no graded game.

**The guard and early looks.**
- `--run-environment` (to be built) refuses a run dated before 2026-10-07, and refuses a
  second run once a 5k result block exists.
- Any run before R that computes a 5k criterion, a twin or a screen, or sets a 2026 value
  of either term beside any 2026 outcome or price, is a look. The members it touched are
  decided that day at p = 1 and recorded with the printout. There is no later read of
  them. Recording such a look as a verdict would read 5k before 5d-C, which the one-run
  rule forbids.
- Before R the builders run for coverage only, and a coverage run prints counts only
  (window counts, floors, each drop, the pre-2026 reconciliation). It never prints a 2026
  `R_w`, `S`, `d` or term value, because a printed series of trailing means already sits
  beside the later games. The 2026 term series is first written by the read itself.
- Tests run on fixtures or on pre-2026 data only.

**No accrual clock.** 5k needs no accrual clock: it adds no vintage column (5c rule 2
counts columns), arm A is archive-reconstructable and arm B is pre-2026 (the 2026-09-11
plan, section 5).

**5h's addition 1, and why it is met.** Addition 1 bars measurement until B-TOTAL-LEVEL
"has either shipped or been closed". Its concern, a term "credited with part of the level
fix", applies with more force to a league-level term than to weather. Three records close
the level repair for 2026:
- 7f read `TOTAL_LEVEL_GATE_CRITERIA` once, behind `SERVE_TOTAL_LEVEL`: "Verdict FAIL; the
  flag stays False", and 7f found the mechanism is not the one B-TOTAL-LEVEL assumed;
- the owner answered on 2026-09-11 that the Over lean stays disclosed, with no
  `SERVE_TOTAL_*` flip;
- plan X1 bars a fourth one-parameter total repair on the fit half.

5k also cannot re-fit 7f's constant, because every member is de-meaned on the fit half.
`SERVE_TOTAL_CALIBRATION` (7h) and `SERVE_SCORE_KERNEL` (7i, to be built) act after
`expected_runs` returns the lambdas, so a flip of either before R leaves criterion 1
untouched. Serving 5k on top of either is its own section.

**Printouts between this commit and R.**
- **DEFAULT, owner decision O23 open:** the 7h re-read on 2026-09-28 may print eval-half
  Over rates on grown windows.
- 7i's look, on or after 2026-09-28, prints the grid and the realised-rate diagnostic.

Both are known in advance. They can steer nothing here, because every constant, row rule,
window, criterion, seed and procedure above is fixed in this text or on 2018-2025, the
Fitted block and harness are committed before 2026-09-28, and m is fixed by then. Any
amendment to 5k written after 2026-09-28 names every printout that preceded it.

**Disqualification.** Any number relating either arm, or a close variant, to a later 2026
game's total, result or price before this section is committed disqualifies the candidate
under 5c rule 1. After commit and before R, the same relation is a look (above). A close
variant is any of these:
- a trailing league runs mean over any window;
- a calendar-month or weekly league offset built from 2026 games;
- an Over rate, mean total or runs mean for any 2026 date window derived from the 7g, 7h,
  7h re-read or 7i printouts (by differencing nested splits or otherwise), compared with a
  later window;
- `lg_rpg` and `n_games` differenced across dates;
- any of these against posted totals.

None of these has been computed.

### What a 5k pass would change

A new flag in the `SERVE_RUN_DISPERSION` idiom (to be built), added only after a pass (5h:
a serving path for an unmeasured feature is exactly what 5c forbids), default False. The
owner flips it in one commit with:
- a `MODEL_VERSION` bump;
- the tripwire test;
- a `--context` re-run that writes the served term and its constants.

One term serves: if more than one family member passes, none is stacked on another. The
owner chooses, and stacking is its own section.

**What a flip moves.** Both lambdas of every game move by one amount, so every fair total
and total side probability moves. The moneyline and runline move slightly, through the
Poisson spread and the clamp.
- **Slots.** **DEFAULT, owner decision O15 open:** slots come from publishable markets
  only, so the total stays out of the slots and badges while its ledger leg is closed
  (since 2026-09-03, plan 4.2). No `SLOT_MARKET_POLICY` value does that today (HEAD
  `"any"`, `betting_model.py:385`); a ledger-leg value is to be built. **2026-09-17:
  built as `"ledger_gated"` and registered at the end of 7d, which also corrects how
  this sentence reads, the line number in it, and the words "and badges" (the
  best-value badge is a client-side surface no policy value has ever gated,
  measured in 7d); HEAD is still `"any"`.** Under that default
  a flip moves total prices, not slots. If O15 is answered otherwise, a slot can change on
  any night a total holds it or newly clears the 0.06 floor (at the nightly only, under
  O21's DEFAULT lock).
- **The Over lean.** In a window where the league scores above the fitted level, a flip
  raises every total, which ADDS to the disclosed Over lean. 7f names that lean a shape
  defect, and this term does not touch shape. The lean stays disclosed either way (owner
  answer, 2026-09-11) and `total_level_check` does not change.

**Which pricer a pass speaks for.** The lab grades each split's vintage refit, and the
served pricer is the context fit (R5-F1: served b1 0.2510 against graded -0.0372). A pass
is a statement about the vintage refit and says nothing about the served context pricer
until 7e-D lands (plan X3). **DEFAULT, owner decision O14 open:** if the served pricer
fails the 7e-D replay, the graded vintage pricer serves with a `MODEL_VERSION` bump. A 5k
flip rides on whichever pricer serves, de-meaned over the games that pricer was fitted on.

**What 5k does not claim.** It does not repair the Over lean, and it reopens nothing in 7f,
7g or 7h: no rule there is re-fit and no member changes the total's shape. It says nothing
about weather (5d-C, 5h) or the park (5i). **No number has been computed on this
candidate.**

---

## 5l. Club policy rates from the dugout (`mg_pen_per_game_l30`, `mg_hook_pitches_l30`), schema after 5j's (pre-registered 2026-09-23)

**Written before the schema bump it describes exists in code and before any value of
the column has been related to any game outcome**, in the discipline of 5a, 5c, 5d, 5g,
5k, 7b and 11a. Nothing served reads either column and nothing served changes. The long
form of this registration, with the read ledger and the candidate census, is
docs/BETTING_DUGOUT_GATE.md; the two documents carry one wording for every threshold
and for the contaminated-screen paragraph, and test_betting_mgmt_policy_registration.py
pins both.

**What this section is not.** The Dugout context block on /betting/ (the collapsed
"Dugout context, not priced" details on every game card and both slot cards, read from
data/management_board.json by betting_dugout.py) is a rendering of the served
descriptive board beside a price. It is not a candidate, not a column, not a look, and
it reads into no probability, edge, expected value, Kelly figure, slot, badge or record
row; test_betting_mgmt_fence.py keeps it so. A rendered value is not a measurement.
This section registers two DATED columns that do not exist tonight and that the board
does not carry.

**Disclosed, because 5c rule 1 turns on it.** No candidate was scored to write this
section. Nothing was fitted, no column was built, no dated value exists. What was read
during design: the served management board's season-to-date club-season rows and its
league hook_pitch_count {median 89, p10 64, p90 102, n 37,964}, none of them related to
any game outcome or any price; the served model's own vintage eval (brier 0.24269, log
loss 0.6784, n_graded 705, split 2026-08-01, fit window 305 games 2026-07-06 to
2026-07-31), read for the power floor only; docs/IN_GAME_MANAGEMENT_GATE.md (a
management gate on a management quantity, relating nothing to a betting outcome); 5c,
5d, 5f, 5g, 5j, 5k and the plan's 5.1 calendar. Layer 1 of the D4 spec shipping before
this section is committed does not constitute a look: no Layer 1 code, test or fixture
relates a management value to a result or to an edge.

**Why this is a gap and not a double count.** The served model's run prevention is
`z_prev`, a blend of the probable's SEM+ and the club's `bullpen_plus` weighted by the
STARTER's own innings share, w = ip_per_gs / 9 (`game_prevention_z`). That share is a
fact about the pitcher. How quickly THIS club goes to its bullpen, independent of who
starts, is a fact about the dugout: two clubs with the same probable and the same
bullpen_plus can hand the game to the pen at different points. The candidate asks
whether the club's policy carries information the starter's share and his third-time-
through exposure (5d-E `sp_tto3_bf`) do not. It is a gap only if it beats those two
neighbours, which is why the twin and a variance-inflation read are part of the result.
"A candidate that only reproduces the innings share has found nothing" (5d-E).

**Source.** .cache/game_feeds/{game_pk}.json (the 2026 MLB feeds the 5d builders
already walk; the same source in 2027), read by a builder in betting_usage.py beside
`build_schema4_team_columns`, over the club's games dated STRICTLY BEFORE the vintage
date. Never the management board, never the corpus parquet, never a per-club decision
ledger file, never mgmt_*. The fence tests keep betting_usage free of management
imports.

**The numbers.**
- 5l-A `mg_pen_per_game_l30`: for club C on vintage date D, the count of pitching
  substitutions made by C as the fielding side over C's games in the 30 calendar days
  before D (dated strictly before D), divided by C's games in that window. Source
  event: liveData.plays.allPlays[].playEvents[] entries of type "action" whose
  details.eventType is "pitching_substitution" (the corpus's own event vocabulary).
  Fielding side from the half. Null when the window holds fewer than 10 club games.
  Units: changes per game, never an index.
- 5l-B `mg_hook_pitches_l30`: over the same window, the median pitch count at removal
  of C's FIRST pitcher in each game (liveData.boxscore.teams[side].pitchers[0], his
  players["ID<mlbam>"].stats.pitching.pitchesThrown, the per-arm workload field 5d
  already reads), across games in which he was removed (a complete game has no hook and
  is excluded, the count published in the basis). Null when fewer than 5 hooks in the
  window. Units: pitches. Openers are not separated; a separate opener-aware form is
  not asked.

**Why not the board's z's.** The served board's z_hook and z_pen are standardized across
the thirty club-seasons of a season through the corpus rebuild date, so a vintage dated
2026-06-01 would read a value that includes July games (the offense_plus
contamination), and the board moves only when the corpus is rebuilt by hand. They are
NOT the registered form. The registered form is the dated trailing-30-day rate above,
built strictly before the vintage date and standardized by the one seam like every
other column.

**Standardization.** Each rides through `_assemble_team_inputs` as `<col>` and
`z_<col>` standardized over the clubs carrying a value on that vintage, None never
zero, exactly as every dark column does. The z is a betting-lane z over the slate's
clubs on the vintage date; it is not the board's z (thirty club-seasons, season to
date): two different quantities with the same name shape.

**Vintage safety.** The rule is 5d's (betting_usage.py: a game is skipped when
`d >= on_date`): the window holds C's games dated STRICTLY BEFORE D whose cached feed
is complete (gameData.status.abstractGameState "Final" and liveData.plays.allPlays
present); an incomplete or missing feed is excluded with the count stated in the
basis. The cached feed carries NO fetch time (top keys copyright, gameData, gamePk,
link, liveData, metaData; metaData holds gameEvents, logicalEvents, timeStamp, wait),
so the basis records, per club, the latest `metaData.timeStamp` among the feeds read
(the feed's own last-update stamp, e.g. "20260803_172707") and names it as such; a
stamp later than the vintage night is visible in the basis and is a disclosure, not an
exclusion rule. Old records return None; `inputs_as_of` never fills the column from
live files or from the board. First-write-wins: the column lands on the NEXT vintage
night after the builder ships.

**Parity fixture (buildable now, no look).** On one 2025 game and one 2026 game, the
builder's per-game pitching-substitution count and first-pitcher pitch count at removal
must equal the management corpus's (the decision ledger's events.event_type
"pitching_substitution" and starter_hook pitch_count). The comparison lives in
test_schema7_builders.py, which may import the ledger module as a TEST (the fence
forbids pricer modules importing it, not tests). Comparing two derivations of a count
on two games relates nothing to an outcome.

**Candidate terms.** Two additive terms on run prevention, fitted by the same
`fit_coefficients` path on the vintage fit window, computed by a function nothing
served calls:
  runs_S = b0 + b1 z_off_S + b2 z_prev_O + b3 park + b4 home + b7 z_mgpen_O   (5l-A)
  runs_S = b0 + b1 z_off_S + b2 z_prev_O + b3 park + b4 home + b8 z_mghook_O  (5l-B)
Each member is tested ALONE (one test each); the pair together is a reported
diagnostic, not a third test. No sign is predicted for either coefficient (a quick
hook can mean weak starters, already in z_prev, or aggressive leverage relief), so the
5g sign criterion does not apply and the twin plus the VIF read are the controls, in
the 5d-E form. The sign is REPORTED.

**Not asked, each needing its own section.** An opener-aware hook form; the club's
first-reliever LI policy (needs LI, which is post-game in the feed); the season-to-date
form; any interaction with the probable's ip_per_gs; a total or runline estimand; a
bench rate (a close variant of 5f `ph_share`, deferred until 5f's first look is
recorded); an intentional-walk rate (no predicted sign, no mechanism named; owner
decision 2026-09-23, not asked); a mound-visit rate (counted only in the module, capped
by rule, nothing priceable pregame).

**Never a candidate, in any window, under any label.** Realized mwpa_<family> (the
same game's figure leaks the outcome; a trailing or season-to-date series is exactly
the club "decision quality" rank docs/IN_GAME_MANAGEMENT_GATE.md withheld, and a pricer
that reads it asserts the skill claim the page refuses; "but it is lagged" is not an
argument); DVS, best, worst, per-decision ledger rows, window plays, wp_before and
wp_after (post-game by construction); the steal DV, ER and realized_delta and the bunt
dv_cell (the running-game model's priced decision values; the steal family's gate
returned a bounded null); defensive-sub timing (5g team_fld_runs owns fielding);
challenges, lineups and ejections (dark or counted; lineups are 5j's). Bullpen usage
over the last three days is ALREADY REGISTERED as 5d `pen_ip_l3` with `pen_b2b_arms`,
`pen_arms_avail` and `pen_plus_avail` (look 2026-10-07); a management-corpus version
would be a second registration of a quantity 5d owns, the double look rule 1 forbids.

**Estimand.** Does adding the club-policy term improve moneyline calibration on the
vintage eval half. The label is the moneyline result (home club wins, 0/1, the served
model's own objective). The score is the paired per-game Brier of p_home against the
served model on the same games; log loss is criterion 2. Regular-season games only;
postseason vintages accrue toward the clock and are not graded. A game enters the pair
only when BOTH clubs carry a populated dated value on that vintage (otherwise excluded
and counted).

**Split.** The existing vintage fit / eval split, 2027 form: the fit window is the
VINTAGE_FIT_TARGET_GAMES (300) games immediately preceding the eval half, on which
`fit_coefficients` fits b0..b4 and the candidate coefficient jointly; the eval half is
every later graded game with a populated value. The 305 games of the 2026 fit window
(2026-07-06 to 2026-07-31) stay ungraded in every mode of every artifact this gate
writes; they are the fit half, named in the eval as fit_window.why_not_graded, and
grading them would open the 600-game gate on in-sample data
(test_min_edge_cannot_be_set_from_the_contaminated_mode). The 2027 look never reads a
2026 game as evidence.

**Decision rule, per member, ALL required.**
1. Paired Brier improvement at one-sided t >= 1.645, and under the family adjustment
   below the smaller of the two members' p-values must clear alpha / 2 = 0.025 (Holm,
   m = 2).
2. Paired log loss not worse on the point estimate.
3. The 5c rule 3 permuted twin: the same fit with the column permuted across clubs
   within each date; the candidate's improvement exceeds the 95th percentile of 200
   twin improvements (the 5f form).
4. At least VINTAGE_MIN_GRADED_GAMES (600) eval-half games with a populated value on
   both clubs, with the 300-game fit window in front of them.
5. The VIF read: the candidate's z against z_prev, z_off, and the neighbours
   ip_per_gs / sp_tto3_bf (as dark columns). A VIF above 5 against the innings share
   fails the member as "reproduces the innings share", whatever (1) and (2) read.
Report whichever way it lands: the coefficient and its sign, the twin distribution,
the VIF table, the pair's joint fit as a diagnostic, coverage per club, the count of
complete games excluded from 5l-B, and the contaminated screen's reading.

**Outcomes.** PASS, FAIL and INDETERMINATE are final for this registration.
UNDERPOWERED and NOT READ wait for the 2028 look. A PASS serves nothing until the
contaminated screen has run without disqualifying (5c rule 4) and the flip commit
lands.

**MDE and the power precondition (computed BEFORE the eval read, on the fit half
only).** At n = 600 paired eval-half games, one-sided alpha 0.025 (the Holm-adjusted
level for the harder member) and 80 percent power, the smallest detectable paired Brier
improvement is (1.96 + 0.84) * sd_d / sqrt(600) = 0.114 * sd_d, where sd_d is the
standard deviation of the per-game paired Brier difference. sd_d is unknown until a
candidate exists and is measured ONCE, on the 300-game 2027 fit window from the
candidate fit, before any eval-half game is read, and published as
`mgmt_policy_gate.power_precondition` in betting_model_eval.json. That sd_d is
IN-SAMPLE (the residual sd of the fit that produced it) and therefore smaller than the
eval-half sd, so the precondition is lenient by construction; the gate block records
`power_precondition.basis = "in-sample fit-window sd, lenient"`, and after the eval
read the eval-half sd_d and the MDE it implies are reported beside it as a diagnostic.
No threshold changes. The floor of interest is pre-declared at 0.0024 Brier, one
percent of the served vintage Brier 0.24269 (betting_model_eval.json vintage.brier on
705 graded games, 2026-09-23). If 0.114 * sd_d exceeds 0.0024 the look returns
UNDERPOWERED without reading the eval half and waits for 2028 with the larger n; the
precondition may not be re-measured on a different window to lower it. If a member
passes (1) with an improvement below 0.0024, the result is recorded as
PASS-BELOW-FLOOR and does not ship (an effect the gate can detect but the site would
not serve).

**Contaminated screen (5c rule 4's first serve leg, in the 5c-A form as corrected
2026-09-11).** It runs ONCE, AFTER the 2027 look, only on a member that passed
criteria 1-5, on the 2027 season-to-date form of the same rate (the club's pitching
changes per game, or its starter pitch count at removal, over the 2027 regular season
through the look date, built by the betting lane from the feeds; never the board's
z_pen or z_hook, which are standardized across thirty club-seasons and move only when
the corpus is rebuilt by hand), labelled contaminated, and it can only DISQUALIFY. It
is graded in the 5c-A fit-and-grade form on backtest()'s own split of the 2027
completed regular-season dates, and it disqualifies when the paired Brier delta
(served model minus candidate) on the held-out dates is <= 0 on the point estimate;
the 5c-A sign criterion does not apply because no sign is predicted. A contaminated
positive qualifies nothing. No look of any 2026 form exists, contaminated or not, and
no contaminated number exists for a member that did not pass (5c-A: "a column that did
not pass has no serve to block"). It is not the look, it reads no dated column, and it
is taken on a calendar date after the look's, never the same one. This paragraph is
the 5c-A form; the older 5g wording of a contaminated screen on the registration
season's outcomes, which the 2026-09-11 correction superseded for 5j, is not inherited
here.

### The dugout Holm family (MG)

**Members, one test each.** 5l-A `mg_pen_per_game_l30`, 5l-B `mg_hook_pitches_l30`;
m = 2. Family alpha 0.05, one-sided, Holm: the smaller p at 0.025, the larger at 0.05.
Criteria 2 to 5, the twins and the screens carry no alpha and add nothing to m (the 5k
family's rule). Not members of RE (a total-side family), of the coefficient-vector
family (7e-B/C/D), of the z_prev family (N6), or of 5d's moneyline candidates (5d-A,
5d-B, 5d-D, 5d-E, which the 5k section records as "not members" of any family). Why
one family: both members ask one question of the moneyline (does a dugout policy term
beat the served prevention blend) from two mechanically correlated measurements of one
policy; a reader offered the better of the two has been offered the best of two looks.
Owner decision 2026-09-23: MG = {5l-A, 5l-B}, m = 2; the intentional-walk rate is not
a third member.

### The clock, and the sentence that binds it

5c rule 2 AND criterion 4. The 2026 regular season ends 2026-09-27; a column that does
not exist tonight accrues nothing in 2026 and plan stop item X7 forbids registering it
as if a 2026 look existed. The builder lands before Opening Day 2027 (plan 5.1: "every
2027 dark column landed"), after 5j's schema-6 bump; if 5j's bump has not landed when
this builder is ready, this builder WAITS (no renumbering of 5j). April is null by the
window floor; populated values begin about the third week of the season; 900 games
with both clubs populated (600 eval behind a 300 fit) arrive about mid-June at the
league's rate.

**The earliest admissible look is 2027-07-01.** The look is taken on the first nightly
on or after 2027-07-01 on which criterion 4 holds, by
tools/betting_mgmt_policy_gate.py (to be written), which reads vintages only, refuses
a run dated before 2027-07-01 and a second run once a `mgmt_policy_gate` block exists,
and writes that one block. If criterion 4 does not hold by 2027-08-01 the candidate
waits for 2028 (no stretch-run read, and no read on the same date as the season-end
looks of 5j and 5f). The look is never taken on the same calendar date as any other
registered look (5g's first-2027-date look is expected in June; 5e's, if not read in
October 2026, is scheduled by its own section), so a read of two families is never one
commit. If another registered look falls on the nightly 5l would take, 5l yields and
is taken on the next nightly on which criterion 4 holds; the yield is recorded in the
`mgmt_policy_gate` block.

Disclosures that will precede the look and are amended into this section the day each
is recorded, without changing any threshold above: the 5c-B and 5c-C reads
(2026-10-05), the 5d read of `pen_ip_l3`, `pen_b2b_arms`, `pen_arms_avail`,
`pen_plus_avail` and `sp_tto3_bf` (2026-10-07), the 5e read (2026-10-09 or 2027), the
5g read (2027). Each tells the lane something about the innings-share neighbourhood
the 5l members sit in; none is a read of a 5l column.

Added 2026-09-30, disclosure only: the section "Starter workload: expected outs and
pitches per start" (below) registers a per-pitcher pitch budget, the per-pitcher
hook-rate close variant named under Disqualification below. Its stage 1 relates
per-pitcher pitch counts only to the starter's own workload (his outs and pitches per
start) on pre-2026 corpus games, and nothing to a game result, price, edge or ledger
row; its moneyline look and any props flip wait for this section's `mgmt_policy_gate`
block. No threshold above changes.

**Whatever the effect size, neither column enters the model before that look.** Not
as a served input, not as a slot tiebreak, not as a badge, not as a "context-adjusted"
probability, not as a shadow-ledger tag, and not through the Dugout context block. A
Dugout context figure that appears to predict is a reason to wait for the look, not to
shorten it.

**The SERVE flag and MODEL_VERSION.** When the builder lands (before Opening Day 2027),
betting_model.py gains `SERVE_MGMT_POLICY = False` in the SERVE_RUN_DISPERSION idiom
and `DARK7_TEAM_COLUMNS = ("mg_pen_per_game_l30", "mg_hook_pitches_l30")` under
DARK_TEAM_COLUMNS; nothing served reads them. SERVE_MGMT_POLICY stays False until a
separate flip commit that cannot exist before the look's artifact does. The flip
requires, in ONE commit: the 5l look returning PASS on a member, the contaminated
screen having run without disqualifying, MODEL_VERSION bumped to betting_runs_v3 (or
the next), the --context re-run, the tripwire in test_betting_mgmt_policy.py and the
persisted `mgmt_policy_gate` block in betting_model_eval.json. The four move together
or not at all. MODEL_VERSION does not move on the registration, on the builder, or on
the look; only on the flip.

**What lands after this section, and before Opening Day 2027.** leaderboard_vintages
`SCHEMA7_TEAM_COLUMNS` appended to TEAM_COLUMNS with the SCHEMA bump to the number
after 5j's; `betting_usage.build_schema7_team_columns(*, on_date, feed_dir=None,
games=None)` in the `build_schema4_team_columns` idiom on the nightly 9e-pre path
inside its own try/except; the DARK7 tuple and the flag above; test_schema7_builders.py
(strictly-before rule, the 10-game and 5-hook null floors, complete games excluded and
counted, incomplete feeds excluded and counted, the parity fixture, the basis stamp,
and a clock test that the schema-7 clock does not open before 2027-07-01);
test_betting_mgmt_policy.py (the flag is off at HEAD; no served path reads an mg_
column by AST and by string; the registration predates the builder by git date); and a
"### Builder landed YYYY-MM-DD" amendment here naming the first vintage night carrying
the columns (the X9 same-day amendment). Until that amendment exists, no non-test
module at the repo root or under tools/ may contain "mg_pen_" or "mg_hook_"; the
registration test asserts it.

**Disqualification.** Any number relating either column, or a close variant (the
board's z_pen or z_hook, the season-to-date rates, a different window length, the
opener-aware form, a per-pitcher hook rate), to game outcomes, to edges or to
shadow-ledger results before this section is committed, or before 2027-07-01 after it,
voids the member under 5c rule 1. A voided member may return only as a new
registration that discloses the early read.

**What would falsify this registration's premise.** If the 5d read of 2026-10-07 shows
`sp_tto3_bf` and the innings share already absorb the hook (the VIF read of criterion 5
would then fail 5l-B by construction), the member stays registered and the look still
runs; the disclosure is amended in and the result is reported whichever way it lands.
If the parity fixture fails, no look is taken until it passes. If the power
precondition is not on disk, no criterion may be read. **No number has been computed
on either candidate.**

---

## 5m. Starter workload: expected outs and pitches per start (N6(d), pre-registered 2026-09-30)

**Written before any code, builder, column, lab, flag or number on the candidate
exists**, in the discipline of 5a, 5c, 5d, 5j and 5l. Nothing served reads anything in
this section, and no served price, props fair line, slot, record row or page changes.
Every name below that does not exist in code today is marked (to be built). Other
sections, specs and tests refer to this section by its title, "Starter workload:
expected outs and pitches per start", never by its letter: betting registrations take
their letters in commit order.

**Neighbouring looks recorded when this section commits: none.** At commit this
document records no result for 5c-A (`xwoba_14`, `xwoba_30`), 5c-B
(`lineup_strength`), 5c-C (`star_out`) or 5d (`pen_ip_l3`, `pen_b2b_arms`,
`pen_arms_avail`, `pen_plus_avail`, `sp_tto3_bf`). The 5j precedent voids a
registration written after a neighbouring look is recorded unless it discloses that
look's result; there is no result to disclose, so nothing here says whether
`sp_tto3_bf`'s verdict bears on this candidate. This section is committed before the
5c-B and 5c-C look day (2026-10-05) and before the 5d read (2026-10-07).

**The owner ask** (ask 16, 2026-09-30, verbatim): "Plug P/IP into the sports betting
module to project how many pitches / IP a pitcher will throw in each game; use P/PA
for hitters and lineups to tweak this based on the lineup each pitcher faces to
calculate expected pitches and expected innings pitched."

**What the served prices read today.** The served run prevention for a side is
`z_prev`, the blend of the listed probable's SEM+ and the club's `bullpen_plus`,
weighted by the starter's innings share w = ip_per_gs / 9, clipped to [0.25, 0.85],
and 5.2 / 9 when `ip_per_gs` is missing (`betting_model._starter_share` and
`game_prevention_z`, betting_model.py lines 2611-2645 at 64bf1bb3; `DEFAULT_SP_SHARE`
at line 190). That share weights the model's one working term (b2). The same
`ip_per_gs` sets every served props fair line: `props_fair_lines` (betting_export.py
lines 4444-4513) takes expected_ip = ip_per_gs (else the projection line's ip / gs,
else 5.2), clipped to [2.0, 7.5] at line 4491, and prices Strikeouts, Earned runs,
Hits allowed and Outs recorded off it. No pitch count enters any served price, line,
edge or slot.

**The finding this section rests on, a definition and not a measurement of any
price.** `ip_per_gs` divides ALL of a pitcher's innings, relief included, by his
starts (`sem_plus.derive_rates`, sem_plus.py line 104, `ip_per_gs = ip / gs`), so a
starter with relief outings is credited with longer starts than he made. It is a
vintage pitcher column, 5j froze its `w_O` on it, and 5d-E and 5l name it as the share
their candidates must beat, so it is NEVER redefined; a starts-only length rides as a
new quantity. The size of the bias in 2025 is a disclosed read, below.

**Disclosed, because 5c rule 1 turns on it.** No candidate, comparator, diagnostic,
forecast or error was computed to write this section. The Part 8 design lane
(pitch_metrics, 2026-09-30, read-only) read:

- the cached StatsAPI season lines
  (`.cache/fa_statsapi_{hitting,pitching}_{2008..2026}.json`) for pitch-count
  coverage, league rates, spreads and year-to-year stability, among them league
  starter P/IP 16.33 (2024), 16.32 (2025) and 16.38 (2026), and year-to-year r over
  the 2021-2026 season pairs of 0.512 for starter P/IP and 0.697 for starter P/BF (334
  pairs, 100+ IP both years), 0.778 for hitter P/PA (994 pairs, 300+ PA both years)
  and 0.351 for reliever P/IP (367 pairs);
- six StatsAPI requests saved in the lane's bundle, among them the 2025 role split
  (starts 16.394 P/IP, 3.880 P/BF, 85.0 pitches per start over 4,860 starts; relief
  16.614 P/IP), the AAA 2025 split (starts 16.955 P/IP) and the team split's 50-of-60
  rows at the default limit;
- the 2025 `ip_per_gs` measurement: of 249 true starters (GS / G at least 0.5), 89 had
  relief outs, and `ip_per_gs` overstated the starts-only length by 0.5 IP or more for
  48 of them (median 0.54 among those with relief, max 3.83 IP);
- the `.cache/pbp_corpus` 2025 parity read: the first pitcher of each fielding half
  gives 4,860 starts, 85.03 pitches per start, 16.392 P/IP and 3.870 P/BF, a per-start
  mean of 15.56 outs, and per-start SDs of 16.2 pitches and 4.12 outs;
- `.cache/milb_platoon`, the schemas of the MiLB caches, a working copy of
  data/timeseries.json and the row keys of the HEAD leaderboards, none of which bears
  on this candidate.

**Named plainly: the 2025 `ip_per_gs` measurement and the 2025 corpus parity figures
(4,860 starts, 85.0 pitches per start, and the per-start outs mean and spreads beside
them) are READS OF 2025, A SEASON STAGE 1 SCORES,** and the 2024 league rate and the
stability pairs that include 2024 or 2025 are reads of seasons stage 1 scores too.
They sit beside the lane's other reads of 2026-09-30. Each is a marginal count or
rate: the per-start outs mean and spreads are the stage-1 label's own 2025
distribution, read once and disclosed here. No forecast of any start, no value of A0,
C1, D1, D2 or the candidate, and no error of any of them was computed on any season.
None of these reads was joined to a game result, a price, an edge or a ledger row. The
writer of this section read the served code cited here and the corpus manifest (its
season list, 2018, 2019 and 2021 to 2026, and its build validation counters), and no
data value.

**Family.** The candidate is plan candidate N6(d), G4-10 "starter expected outs"
(docs/master-plan-2026-09-11-war-epoch-drivers-betting.md, the N6 row), the fourth
member of the z_prev Holm family N6, m = 4 as tabled: F05-07 (the run-scale SEM+/REM+
blend), F08-01 (the HR point as a betting estimand), G4-02 (the velocity form) and
G4-10 (this section). m does not shrink if the other three are never registered: N6 is
read by conservative Holm at family alpha 0.05, one-sided, and the smallest p is read
at 0.05 / 4 = 0.0125. N6 is not RE, not MG, not the coefficient-vector family
(7e-B/C/D), and not 5d's moneyline candidates. Stage 1's headline is a workload
estimand in no Holm family; its two attribution contrasts are their own family of two
(below).

**The candidate, for the listed probable P on date D (every input dated strictly
before D).**

```
n        = P's starts in the 365 days before D
budget   = (pitches over those n starts + k_b * L_pgs) / (n + k_b)
ppo      = (pitches over those n starts + k_o * L_ppo) / (outs over those n starts + k_o)
r_L      = [ (pitches seen by the opposing club's hitters over its games in the
             30 days before D + k_l * L_ppa) / (their PA + k_l) ] / L_ppa
xOuts    = min(27, budget / (ppo * r_L))
xIP      = xOuts / 3
xPitches = budget
```

- L_pgs (league pitches per start), L_ppo (league pitches per out in starts) and L_ppa
  (league pitches per PA) come from the prior complete season, pooled (sum over sum,
  never a mean of player rates). In the corpus, the prior complete season of a 2021
  date is 2019: 2020 is not in the corpus.
- The priors come from a grid published and frozen here: k_b in {2, 4, 8, 16, 32}
  starts, k_o in {15, 30, 60, 120, 240} outs, k_l in {100, 300, 1000, 3000} PA. They
  are chosen once, by outs MAE on 2018-2019 only, before any later season is read (the
  `betting_props_dark` burn-in idiom, betting_props_dark.py lines 59-90). The burn-in
  scores the 2019 starts; 2018 games enter only as history for 2019's windows and
  anchors, because the corpus holds no 2017 season to anchor a 2018 row. A tie goes to
  the smallest priors in the order listed. The full grid table is published in the
  artifact's burn-in block.
- Clubs join via `trades.canonical_org`.
- The opposing lineup is the club's own trailing hitting line over its last 30 days,
  never a posted card: posted-card variants belong to 5j until its look.
- The stage-2 share is clip(xOuts / 27, 0.25, 0.85), the served clip.
- What the ask's two outputs are, exactly: expected innings is xIP and expected
  pitches is xPitches, the budget. The lineup term moves outs and innings; in this
  form it does not move pitches.

**Comparators, named before anything is computed.**

- A0, the incumbent, is the served props number: A0 = 3 x clip(P's season-to-date IP /
  GS over ALL appearances, strictly before D, 2.0, 7.5), with 5.2 (the served float,
  15.6 outs) when P has no start yet that season.
- C1, tested (T2): C1 = (outs over P's starts in the 365 days before D + k_c x L_opg)
  / (n + k_c), with L_opg the prior complete season's league outs per start and k_c
  chosen on 2018-2019 from the k_b grid by the same rule. C1 is a same-window,
  same-shrinkage, starts-only outs-per-start comparator: it differs from the candidate
  only in carrying no pitch rates.
- D2, tested (T1): the candidate with r_L = 1, on the same frozen k_b and k_o. It
  isolates the opposing lineup's P/PA.
- D1, reported and never tested: A0's form on starts only (season-to-date starts-only
  IP / GS, the same clip and fallback), the pure definition repair.

**Stage 1: the workload estimand.** Eval artifact data/starter_workload_eval.json (to
be built), this section's own tracked artifact, with registry row
`starter_workload_xouts` (to be built).

- Data: `.cache/pbp_corpus` seasons 2018, 2019 and 2021-2025, regular season. NEVER
  2026, neither as a scored row nor as history: 2026 holds the betting eval half. The
  unit is a start, the first pitcher of each fielding half (archive-reconstruct
  provenance, allowed and labelled per row under owner decision O22).
- The estimand: outs recorded by the starter in the start (primary) and pitches he
  threw (secondary). A start's own outs and pitches never enter its inputs.
- Walk forward by date: every start on D is priced from games dated strictly before D,
  and only then do D's games fold into the history.
- Splits: 2018-2019 burn-in (the priors); 2021-2023 fixes the floor, 1 percent of A0's
  outs MAE on 2021-2023, written to the artifact before any 2024 row is read;
  2024-2025 scored once.
- PASS needs all four, on outs unless named: (1) the paired improvement MAE(A0) minus
  MAE(candidate), pooled over 2024-2025, has a game-clustered bootstrap lower bound
  above 0 (B 2000, seed 20260930; games resampled with replacement, both starts of a
  game together; the lower bound is the 5th percentile of the 2,000 replicate
  improvements); (2) a positive point improvement in 2024 and in 2025 separately; (3)
  the pooled point improvement at or above the floor, else PASS-BELOW-FLOOR, which
  ships nothing; (4) the pitches MAE of `budget` no worse than that of P's
  season-to-date pitches-per-start mean (L_pgs when P has no start yet that season),
  on the pooled point estimate.
- PASS, FAIL and PASS-BELOW-FLOOR are final.
- Stage 1 never reads `sp_tto3_bf`, `sp_rest_days` or any `mg_` column; never the
  management board, a decision ledger or any mgmt_ module; never a vintage record, a
  2026 game feed, a price, an odds capture or a betting artifact. The lab names its
  quantities budget, ppo and xouts, never by the dark column names below.
- Reported whichever way it lands: RMSE and bias for every arm; every figure per
  season and for April-May; openers (a trailing 365-day mean under 6 outs per start);
  D1, D2 and C1; the count of starts with n = 0; the count of 2021 starts whose
  365-day window reaches into the absent 2020 season; the grid table.

**What a stage-1 pass can credit: the attribution family, tested.** Two contrasts form
one Holm family, m = 2, family alpha 0.05 one-sided, on 2024-2025 with the same
game-clustered bootstrap (B 2000, seed 20260930, the same resampled games as criterion
1): (T1) the candidate against D2, improvement MAE(D2) minus MAE(candidate), the only
contrast that isolates the opposing lineup's P/PA; (T2) the candidate against C1,
improvement MAE(C1) minus MAE(candidate). Each one-sided p is (1 + the number of
replicates with an improvement at or below 0) / (B + 1); the smaller p is read at
0.025 and the larger at 0.05. D1 stays reported and untested. **The wording is
pre-committed:** without a T2 pass, results copy, any props change and every later
reference credit "starts-only length over a 365-day window", not pitch rates; without
a T1 pass, nothing credits the opposing lineup's P/PA. T1 and T2 decide wording only:
they do not change the stage-1 verdict, and the stage-2 candidate stays the one
registered here.

**When stage 1 runs.** Once, by tools/starter_workload_lab.py (to be built), under the
crash protocol (a full dry run of the reporting path on fixtures with nulls; the run's
stdout and stderr teed before anything else runs; on any exception after scoring
began, stop without rerunning and put the question to the owner). Not before the later
of 2026-10-11 and the owner's answer to PM-Q3 (DECISIONS_FOR_OWNER.md); if that answer
is to wait for 5l, on the first admissible date after 5l's look is recorded. Never on
a date that is another registered look's date (docs/*GATE*.md, this document, plan
Part 8 section 8.B), and never between the fWAR label epoch's step A and its step Z
entry. The lab refuses a 2026 season, an early date and a second run; its one-run
guard reads both the artifact's stage-1 block and this section's results heading. The
result is appended under this section as a heading
`### Stage 1 result (run DATE, once): VERDICT`. The registry row lands with the lab
code as `unvalidated`; the run commit sets the artifact and the verdict (PASS:
`provisional`, dark; anything else: `deprecated`).

**Stage 2: the moneyline price.** Runs only on a stage-1 PASS; on any other stage-1
verdict it is recorded NOT READ.

- The candidate share replaces w in `game_prevention_z`, side by side, and is fitted
  by `fit_coefficients` on the VINTAGE_FIT_TARGET_GAMES (300) games immediately before
  the eval half. The label is the moneyline result (home club wins, 0/1).
  Regular-season games only. The 305 games of the 2026 fit window stay ungraded in
  every mode of every artifact this section writes, and the 2027 look never reads a
  2026 game as evidence.
- Decision rule, ALL required, the 5l form: (1) paired Brier improvement at one-sided
  t >= 1.645, and Holm in N6 (m = 4; with no other member read, its p must clear
  0.0125); (2) paired log loss not worse on the point estimate; (3) the
  permuted-pitcher twin: xOuts permuted across the date's probables, 200 draws, the
  candidate's improvement above the 95th percentile of the twin improvements; (4) at
  least VINTAGE_MIN_GRADED_GAMES (600) eval-half games with both probables populated,
  behind the 300-game fit window; (5) the VIF read against `ip_per_gs`, `sp_tto3_bf`
  and `mg_hook_pitches_l30` (as dark columns): a VIF above 5 against the innings share
  fails the candidate as "reproduces the innings share", whatever (1) and (2) read.
- The power precondition and the floor, the 5l form at N6's level: at n = 600,
  one-sided 0.0125 and 80 percent power, the smallest detectable paired Brier
  improvement is (2.241 + 0.842) x sd_d / sqrt(600) = 0.126 x sd_d, with sd_d measured
  ONCE on the 300-game 2027 fit window from the candidate fit, before any eval-half
  game is read, and recorded as in-sample and lenient. The floor is 0.0024 Brier, as
  5l registered it (this section read no betting eval artifact). If 0.126 x sd_d
  exceeds 0.0024 the look returns UNDERPOWERED without reading the eval half and waits
  a year; a pass of (1) below 0.0024 is PASS-BELOW-FLOOR and does not ship.
- PASS, FAIL and PASS-BELOW-FLOOR are final; UNDERPOWERED and NOT READ (a floor unmet)
  wait for the next season's look.
- The look: the first nightly on or after 2027-07-01 on which (4) holds AND 5l's
  `mgmt_policy_gate` block exists (5l's look recorded) AND no other registered look
  falls that day; otherwise it yields to the next such nightly and records the yield.
  If (4) and 5l's block do not both hold by 2027-08-01, it waits for 2028. Tool:
  tools/betting_workload_gate.py (to be built), which refuses an early run and a
  second run. The result is appended under this section as a heading
  `### Stage 2 result (run DATE, once): VERDICT`.
- Reported whichever way it lands: the fitted coefficients, the twin distribution, the
  VIF table, coverage per club, the candidate share against the served share, and
  later the contaminated screen's reading.

**Where both stages write, and why.** `betting_model.backtest()` rebuilds
data/betting_model_eval.json from scratch every night (run_monthly step 9e-pre1), so a
foreign block there is erased by the next nightly. Stage 1 writes
data/starter_workload_eval.json and stage 2 writes a stage2 block in the same
artifact; neither ever writes data/betting_model_eval.json. The one-run guard of each
stage reads both the artifact and this section's results block.

**The dark capture (to be built).** Pitcher columns `sp_n365`, `sp_budget`, `sp_ppo`,
`sp_xouts` and team column `bat_ppa_l30`:

- `sp_n365` is n; `sp_budget` and `sp_ppo` are the candidate's budget and ppo on the
  priors stage 1 froze; `sp_xouts` is min(27, sp_budget / sp_ppo), the lineup-neutral
  value; `bat_ppa_l30` is the club's shrunk P/PA over its last 30 days, the numerator
  of r_L, that is (pitches seen plus k_l x L_ppa) / (PA plus k_l). The game's xOuts
  takes r_L = bat_ppa_l30 / L_ppa from the opposing club inside a candidate function
  nothing served calls (to be built). Each record's basis carries the raw counts
  (starts, pitches, outs, PA) and the anchors.
- The schema number is the next one after the last landed builder in commit order when
  this builder commits. It does not wait for 5j's or 5l's builder: 5j's number may
  move by a dated correction, and only 5l waits for 5j. A dated
  `### Builder landed YYYY-MM-DD` amendment here names the schema number and the first
  vintage night carrying the columns.
- The builder lands before Opening Day 2027, after the stage-1 record exists (it reads
  the priors frozen there) and only on a stage-1 PASS; otherwise no column is built.
  It sits in betting_usage.py beside `build_schema4_team_columns`, reads
  `.cache/game_feeds` dated strictly before D, and follows the 5d and 5l
  vintage-safety rule (an incomplete or missing feed is excluded and counted in the
  basis).
- First-write-wins, a basis per record, None never zero (an `sp_n365` of 0 is a real
  count), old records return None, and `inputs_as_of` never fills a column from live
  files. A DARK tuple in betting_model.py; no served path reads the columns (AST and
  string tests); a parity test against the corpus on one 2025 game and one 2026 game.
- Until the `### Builder landed` amendment exists, no non-test module at the repo root
  or under tools/ may name `sp_n365`, `sp_budget`, `sp_ppo`, `sp_xouts` or
  `bat_ppa_l30`; test_betting_workload_registration.py asserts it.

**Props: no props arm reads the candidate before the stage-2 look.**
`SERVE_WORKLOAD_PROPS` (added only with its flip commit, default False) may not flip
until BOTH 5l's `mgmt_policy_gate` block and this section's stage-2 look exist. The
reason is mechanical: `props_value_bets` turns any cached props snapshot into edge, EV
and Kelly rows, armed or not, and hands them to `provisional_picks` as slot candidates
(betting_export.py lines 4883-4899 and 7017-7026), and a per-pitcher pitch budget is
the close variant 5l names ("a per-pitcher hook rate", 5l's Disqualification
paragraph). A stage-1 PASS licenses nothing served. The one registered earlier form is
a FENCE: if the owner wants the workload number displayed before those looks, a fenced
flag may show it only if candidate-derived props rows carry no market comparison,
value row, slot candidacy, shadow row or record row, pinned by a test in the
test_betting_mgmt_fence.py style, in a commit that also names every moved fair line.

**Serving the game price.** No serving flag exists before a stage-2 PASS, because a
serving path for an unmeasured feature is what 5c forbids (5h's rule as applied in
5j). On a PASS: the contaminated screen (5c rule 4, in the 5l form: once, after the
look, on the 2027 season-to-date form, labelled contaminated, disqualify-only), then
ONE commit carrying `SERVE_STARTER_WORKLOAD` (to be built), the `MODEL_VERSION` bump,
the `--context` re-run, the tripwire test and the persisted stage2 block. They move
together or not at all. A flip is outward-facing and is the owner's call even on a
PASS (7g).

**Disqualification.** Any number relating the candidate, or a close variant, to a game
result, a price, an edge, a slot, or a shadow, calibration or ledger row outside the
stage-2 look voids it under 5c rule 1, on any game, whether computed before or after
this commit. The close variants are: budget alone; ppo alone; other window lengths;
season-to-date forms; the posted-card lineup ratio; a club-level version; C1; and the
D1 and D2 diagnostics. The only admissible reads are stage 1 (workload only: the
starter's own outs and pitches, on pre-2026 corpus games) and the stage-2 look. A
voided candidate may return only as a new registration that discloses the early read.
Registered looks of other sections on their own columns are not relations of this
candidate.

**Changes after the commit.** The schema number and the first vintage night are
recorded by dated correction whenever they occur. Any other change is possible only by
a dated correction recorded before any stage-1 number exists, on a fact established
without outcomes; a change after that closes the section.

**No number has been computed on this candidate.**

---


## 5n. The home-plate umpire: a dark pregame assignment capture (pre-registered 2026-10-08)

**Written before any capture, builder, column, table, lab, flag or number on the
candidate exists**, in the discipline of 5a, 5c, 5d, 5j, 5l and 5m. Nothing served reads
anything in this section, and no served price, props fair line, slot, record row or page
changes. Every name below that does not exist in code today is marked (to be built). Other
sections, specs and tests refer to this section by its title, "The home-plate umpire: a
dark pregame assignment capture", never by its letter: betting registrations take their
letters in commit order. The long form, with the read ledger, the candidate census and the
look's step order, is docs/BETTING_UMPIRE_GATE.md; the two carry the same thresholds in
the same words, and test_betting_umpire_registration.py (to be built) pins them to each
other.

**The owner answer this registers** (2026-09-25, batch 5): register a DARK home-plate
umpire betting family, reopening the 5d-F ban on a new fact. The fact is census item
X05-04 (docs/master-plan-2026-09-24-final-pass.md): the MLB schedule endpoint carries the
game's officials, the home-plate umpire among them, before the game, and the 2026-09-08
probe that 5d-F rests on read a single `Preview`-state live feed (game_pk 824792), not
the schedule.

**What is known about the source tonight, and what is not.** One StatsAPI request was
made to write this section: `/api/v1/schedule?sportId=1&startDate=2026-10-08&endDate=2026-10-11&gameType=R,F,D,L,W&hydrate=officials`
at 2026-10-09T00:01:42Z (20:01 ET on 2026-10-08). It returned three postseason games.
Game 849832 (type D, abstract state `Live`, detailed state `Warmup`, first pitch 0.0 hours
away) carried six officials, the home-plate umpire among them. Games 849831 (48 hours out)
and 849809 (72 hours out) carried none. So the schedule hydrate names the plate umpire by
first pitch, which the live feed in `Preview` state did not; **how many hours before first
pitch it does so is NOT measured.** The census line says "hours before"; this probe neither
confirms nor refutes that, and a postseason crew is not a regular-season rotation. The lead
is the first thing the capture measures. No score, result, line, price or edge was read
from the response, and it is not committed.

**Neighbouring results recorded when this section commits, disclosed by verdict.** 5c-B
`lineup_strength` FAIL and 5c-C `star_out` INDETERMINATE (both run 2026-10-08); 7g FAIL and
7h INDETERMINATE (both run 2026-09-11) and 7h's one re-read FAIL (run 2026-10-02), each
leaving the Poisson total serving; 11b FAIL (2026-08-16). None of them reads an umpire. No
result is recorded for 5c-A, 5d, 5e, 5k or the run-environment family RE. The writer of
this section read those headings and verdict lines, the served code and documents cited
here, and the one probe above; no data value about any umpire was read.

**The pregame source.** StatsAPI `/api/v1/schedule` with `hydrate=officials` (free, keyless,
zero Odds API credits), all five game types R, F, D, L and W so postseason assignments are
captured. The home-plate umpire is the entry whose `officialType` is "Home Plate". Never
the live feed, never a completed feed, never `liveData.boxscore.officials`, never a
third-party umpire site, and never a rotation guess: an assignment the schedule has not
published is not an assignment.

**The capture time rule.** For a game g, let T_price(g) be the `captured_at` of the slate's
price vintage: the open odds snapshot (kind `open`, `betting_ingest`) that the served board
priced g's slate against, which is the price the shadow ledger records. An assignment
counts for g only when it stands in a capture row whose `captured_at` is strictly earlier
than T_price(g) AND at least 5 minutes before g's first pitch. The row that counts is the
NEWEST such row; if that row names no plate umpire (a retraction), g has no assignment.
A game whose slate has no open snapshot has no T_price and is excluded and counted.
A game whose first assignment row was captured at or after T_price(g) is excluded from
every criterion and counted under "assignment after price vintage". An assignment that a
capture outage delayed is excluded by the same rule, so an outage can only shrink the
graded set, never put a later fact before an earlier price. **One pre-look correction is
allowed:** if the capture's own timing (when rows first appear relative to the open
snapshot, a fact about publication with no outcome in it) shows the open is earlier than
publication on most games, a dated correction filed before any look number exists may
re-point T_price to the close snapshot (kind `close`) for every game. It may not be made
after a look number exists, and it changes nothing else.

**The capture (step 2 of the owner answer).** `tools/betting_umpire_job.py` (to be built
next, in its own commit after this section): a self-gating job in the
`tools/betting_lineup_job.py` shape, cron `*/15 * * * *` under `TZ=UTC`, one schedule call
per acting invocation over the UTC dates D-1 to D+2, writing immutable files
`<UTC date>-<HHMM>.json` under `.cache/umpire_captures/` (created exclusively, never
overwritten). A row is written per game whose plate assignment CHANGED since its last row
(first sighting, a different umpire, or a retraction), only while the game is pregame and
at least 5 minutes from first pitch. Each row carries `game_pk`, `game_type`,
`official_date`, `first_pitch`, `captured_at`, `lead_minutes`, `status`, `double_header`,
`home_team_id`, `away_team_id`, `venue_id`, `hp_umpire_id`, `hp_umpire_name`, `crew` (every
listed official's type and id) and `last_unassigned_at` (the newest earlier call at which
the job saw the game pregame with no plate umpire, so publication is bracketed between
that instant and `captured_at`). That list is the capture schema `umpire_capture/1`, and
nothing else is stored: **no score, run, winner, line, price or any other outcome field
sits beside an assignment**, the job reads no game feed and imports no pricer, settle,
scores or results module, and no served module imports the job. Tests pin each of these.

**The candidate columns (to be built; both game-level, both from PRIOR SEASONS ONLY).**
For a 2027 game whose counted assignment names plate umpire u:

- **5n-A `ump_cs_rate_prior`**: u's called-strike share of taken pitches over his
  home-plate games in prior regular seasons, as a deviation from each season's league
  share: the sum over u's taken pitches of (1 if called strike else 0, minus that season's
  league called-strike share of taken pitches), divided by (u's taken pitches + k_c), with
  k_c = 3000 taken pitches. A taken pitch is a pitch row with `call_code` "C" (called
  strike), "B" or "*B" (ball); every other code is excluded and the code census is
  published. Units: share of taken pitches. Predicted sign on runs: NEGATIVE (a wider
  called zone lowers scoring).
- **5n-B `ump_rpg_prior`**: u's runs-per-game effect over his home-plate games in prior
  regular seasons: the sum over those games of (the game's total runs minus that season's
  league mean total runs per game), divided by (u's games + k_r), with k_r = 150 games.
  Units: runs per game. Predicted sign: POSITIVE.
- Source: `.cache/pbp_corpus`, regular season, seasons 2018, 2019 and 2021 to 2026 (the
  corpus holds no 2020), never 2027. A game's plate umpire is the `home_plate_umpire_id`
  on its first pitch; a game whose id changes within the game stays with the first
  umpire and is counted. 2026 pitches that the feed marks as overturned by an ABS
  challenge are excluded from 5n-A and counted; if the builder cannot identify them,
  5n-A drops 2026 entirely and says so. An umpire with no prior home-plate game (5n-B) or
  no prior taken pitch (5n-A) is None, never zero, and the game is excluded and counted.
- k_c and k_r are fixed here without reading any umpire data. They are not estimated, no
  variance component is fitted, and no other value is tried: another k is a close variant.
- Both columns are frozen once, before Opening Day 2027, in one table
  (`data/_labs/umpire_prior/umpire_prior_2027.json`, to be built by
  `tools/umpire_prior_table.py`, to be built), keyed by umpire id with each umpire's counts,
  and its sha256 is recorded in a dated `### Builder landed YYYY-MM-DD` amendment here.
  data/_labs/ ships in neither deploy consumer.
- **The builder computes each umpire's value and nothing else.** No summary across
  umpires (spread, standard deviation, top or bottom list, correlation with anything,
  split-half or year-to-year stability) is computed, printed or stored before the look.
  The builder's published counts are taken pitches, games, excluded codes and the null
  count. A year-to-year stability of 5n-B would be a read of the look's own question on
  earlier seasons, and is forbidden by name.

**The look's estimand and criteria (the 5k form, on the TOTAL).** The incumbent is the
served model on the look day, fitted on the fit window as the 7f to 7h labs fit it. Each
challenger is the incumbent plus ONE additive term c x v_g on both sides' expected runs,
where v_g is the column's value for g's counted umpire, with c fitted by
`fit_coefficients` on the fit window and nothing else re-solved (5h-A's rule). Each
model's scored total is `lam_home + lam_away` as `expected_runs` returns them, before any
total-pricing layer. Regular-season 2027 games only; postseason captures accrue and are
never graded; no 2026 game is ever evidence.

- **Halves.** Eligible games are 2027 regular-season games with a counted assignment and a
  non-null value. The fit window is the first whole dates of eligible games holding at
  least VINTAGE_FIT_TARGET_GAMES (300); the eval half is every later eligible game through
  the day before the look.
- **Criterion 1.** Paired absolute error on the game total, d_i = |err_inc,i| -
  |err_chal,i|, mean above 0, with the 5k pinned t: clustered on date with the CR1 factor,
  one-sided p from t with G - 1 degrees of freedom, at the member's Holm level in family
  UMP.
- **Criterion 2.** Moneyline paired Brier not worse on the point estimate.
- **Criterion 3, the twin.** The 5c rule 3 control as an ASSIGNMENT twin: within each
  date, permute the column's values across that date's eligible games (fit window and
  eval half alike), refit c, grade on the same games; seeds 0 to 199 with
  `numpy.random.default_rng(seed)`. The member's mean improvement must strictly exceed
  `numpy.percentile(twin_improvements, 95)`. The twin asks whether THIS umpire on THIS
  game carries information beyond a value of the same size landing on another game that
  night.
- **Criterion 4, the sign.** The fitted c carries the predicted sign (negative for 5n-A,
  positive for 5n-B). A wrong-signed member FAILS whatever criteria 1 to 3 read.
- **Criterion 5, the counts.** At least VINTAGE_MIN_GRADED_GAMES (600) eval-half games
  behind the 300-game fit window, AND at least 4 weeks (28 days) between the first 2027
  regular-season capture row and the look date.
- **The power precondition (the 5l form).** At n = 600, one-sided 0.025 (the Holm level
  of the harder member) and 80 percent power, the smallest detectable improvement is
  (1.96 + 0.84) x sd_d / sqrt(600) = 0.114 x sd_d, with sd_d the standard deviation of d_i
  measured ONCE on the fit window from the candidate fit, before any eval-half game is
  read, recorded as in-sample and lenient. The floor of interest is 1 percent of the
  incumbent's fit-window mean absolute error on the total, computed in the same step. If
  0.114 x sd_d exceeds the floor the member is UNDERPOWERED without reading the eval half;
  a criterion 1 pass below the floor is PASS-BELOW-FLOOR and ships nothing.
- **Verdicts.** PASS needs criteria 1 to 5 and the precondition. PASS, FAIL and
  PASS-BELOW-FLOOR are final; UNDERPOWERED and NOT READ wait for the 2028 look.
- **Reported whichever way it lands, never qualifying.** The counts excluded by each rule
  (assignment after price vintage, retraction, null value, refusal boundary, postseason);
  the publication lead distribution (`captured_at` and `last_unassigned_at` against first
  pitch and against T_price); assignment agreement, the counted umpire against the
  completed feed's plate umpire, an identity count only; c and its sign; paired squared
  error on the total; the twin distribution; the pair's joint fit as a diagnostic; each
  member's correlation with 5d-D's `catch_frame_rate` on shared games.

**The Holm family UMP.** Members, one test each: 5n-A, 5n-B; m = 2. Family alpha 0.05,
one-sided, Holm: the smaller p at 0.025, the larger at 0.05, ties ranked 5n-A first.
Criteria 2 to 5, the twin and the screen carry no alpha and add nothing to m (the 5k
rule). UMP is not RE: RE's membership was fixed by its own section's commit history
before 2026-09-28, and a member added after that would amend a family already scheduled
to read. Not N6, not MG, not the coefficient-vector family (7e-B/C/D), and not 5d's
moneyline candidates. Why one family: both members ask one question of the total (does
the plate umpire move tonight's run total beyond the served model) from two correlated
measurements of one umpire; offered the better of the two, a reader has been offered the
best of two looks.

**The clock.** 5c rule 2 and criterion 5. The capture accrues from the night it is
installed; nothing accrues while it is not. **The earliest admissible look is
2027-06-01**, on the first nightly on or after 2027-06-01 on which criterion 5 holds, the
prior table's `### Builder landed` amendment exists, and no other registered look falls
that day (docs/*GATE*.md, this document, plan Part 8 section 8.B); otherwise it yields
to the next such nightly and records the yield. If criterion 5 does not hold by
2027-08-01, the look waits for 2028. Tool: `tools/betting_umpire_gate.py` (to be built),
which reads the capture store, the frozen table and the vintage path only, refuses a run
dated before 2027-06-01, a run without the table hash, and a second run, and writes one
`umpire_gate` block to data/betting_umpire_eval.json (to be built; never
data/betting_model_eval.json, which the nightly rebuilds from scratch) with registry row
`betting_umpire_dark` (to be built, `unvalidated` until the look). The result is appended
here as `### Result (run DATE, once): VERDICT`. **Looking early DISQUALIFIES.**

**The SERVE flag and the schema.** `SERVE_UMPIRE = False` (to be built) lands in
betting_model.py with the gate tool, in the SERVE_RUN_DISPERSION idiom, and stays False.
The capture schema is `umpire_capture/1`; the two candidate columns live in the frozen
table and are never added to the leaderboard vintage store, whose team and pitcher columns
cannot carry a game-level fact. The flip, in ONE commit and only after a PASS that the
contaminated screen did not disqualify: `SERVE_UMPIRE` True, the `MODEL_VERSION` bump, the
`--context` re-run, the tripwire test and the persisted `umpire_gate` block. They move
together or not at all, and a flip is the owner's call even on a PASS (7g).

**The contaminated screen (5c rule 4, the 5l form).** Once, after the look and on a later
calendar date, only on a member that passed: the same term with u's value replaced by his
2027 regular-season value through the look date (the graded games included), labelled
contaminated. It can only DISQUALIFY (a paired absolute-error delta at or below 0 on the
eval half's point estimate); a contaminated positive qualifies nothing.

**Not asked, each needing its own section.** A rotation prediction of the plate umpire
before the schedule publishes it; a crew effect; a location-adjusted zone metric; the
umpire's strikeout or walk rate; any props estimand (strikeouts, walks); a moneyline
estimand; a same-season or trailing-window form; a third-party umpire figure.

**Disqualification.** Any number relating either column, the captured assignment, or a
close variant to a game result, a price, an edge, a slot, or a shadow, calibration or
ledger row outside the look voids the member under 5c rule 1, on any game, whether
computed before or after this commit. The close variants are: other k values or seasons;
the umpire's identity as a fixed effect; the same-season or trailing form; the crew; a
location-adjusted zone; the umpire's strikeout, walk or run-value rate; any between-umpire
spread or stability read of 5n-B. The only admissible reads are the builder's per-umpire
values (above), the capture's timing and identity counts, and the look. A voided member
may return only as a new registration that discloses the early read.

**Changes after the commit.** The capture's install date, the builder's landing and the
table hash are recorded by dated amendment whenever they occur, and the one T_price
correction above may be filed before any look number exists. Any other change is possible
only by a dated correction recorded before any number on either column exists, on a fact
established without outcomes; a change after that closes the section.

**No number has been computed on this candidate.**

### Capture landed 2026-10-08, not installed

`tools/betting_umpire_job.py` landed in the commit after this section, with
test_betting_umpire_job.py and test_betting_umpire_registration.py. It is NOT installed:
the cron entry is a deploy step, deferred under DEPLOY-3 and listed in
docs/DEPLOY_PENDING.md, so nothing accrues toward the clock yet. One local run on
2026-10-09T00:13:40Z into a scratch store (never `.cache/umpire_captures/`) made one
schedule call and wrote no row: of three games in the span, one was in progress and two
were outside the 36-hour window. No assignment, umpire value or outcome was read.

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

### The third value: `ledger_gated` (owner decision 2026-09-17, O15)

**What the owner locked.** The LEDGER leg BARS a slot. The DISPERSION leg stays
a DISCLOSURE. `betting_model.SLOT_MARKET_POLICY = "ledger_gated"` is that
value. A market whose section 7b ledger leg is CLOSED fills neither slot and
reaches no public record row. A market the 11a dispersion correction bars,
whose ledger leg is open, keeps both slots and the record and carries the
Poisson `caveat` on the published row exactly as it does under `"any"` today.

**WHAT THE POLICY DOES NOT REACH: the per-game best-value badge.** 5k and 7e-D
both say "slots and badges", and the badge half of that sentence has never been
true of any `SLOT_MARKET_POLICY` value, this one included. The badge is
computed CLIENT-SIDE by `bestValueSide` in assets/betting.js, which walks
`b.moneyline`, `b.runline` and `(b.total || {}).sides` on the served board and
takes the highest edge clearing `pick_meta.min_edge`. There is no market-policy
filter anywhere on that path, and the payload carries no field that would let
there be one. MEASURED on the cached 2026-09-18 board, under all three values
alike: three games still carry a best-value badge on the TOTAL, the one
ledger-closed market on this box - game 823331 Over 8.0 at edge 0.10854, 825032
Over 8.0 at 0.14793 and 823898 Over 8.0 at 0.13013. The badge is therefore an
UNFILTERED surface and is recorded as one here rather than asserted away.
Gating it means stamping the board rows server-side and having `bestValueSide`
skip them; that is a change to assets/betting.js, which belongs to another
track, and it is a NAMED FOLLOW-UP below rather than a claim made in advance.

**Why the second value could not serve as the third.** Two sections asked for
this state by name and could not have it. 5k: "slots come from publishable
markets only, so the total stays out of the slots and badges while its ledger
leg is closed". 7e-D: "under its default (publishable markets only; the policy
value is to be built), the ledger-closed total cannot fill a slot". Under
`"dispersion_gated"` the total does leave the slots, but so does the RUNLINE,
whose own ledger leg is OPEN and which is barred there only by the dispersion
correction this section decided on 2026-09-05 to disclose rather than enforce.
One bit cannot both bar on one leg and speak on the other, and until today
every seam read the policy as one bit (`gated = SLOT_MARKET_POLICY != "any"`).

**A correction to how two of those sentences read.** 5k says "No
`SLOT_MARKET_POLICY` value does that today ... a ledger-leg value is to be
built". Read literally that is not what the code did: `"dispersion_gated"` has
barred a ledger-closed market from the slots since 2026-08-16, at both seams.
What did not exist is a value that bars on the LEDGER leg WITHOUT also barring
on the dispersion leg, which is how 7e-D and stop item X2 word it and which is
what was built. The pointer in that 5k sentence and in X2 to
`betting_model.py:385` is also stale: `SLOT_MARKET_POLICY` is at
`betting_model.py:438` in the tree that carries this paragraph. The words "and
badges" in 5k and in 7e-D are a THIRD thing those sentences get wrong, and that
one is not repaired by this change: see the measured badge paragraph above.
Nothing else in either sentence changes, and neither default moves.

**Where it is implemented, and how the legs are read.**
`betting_export.slot_market_policy_legs()` is the single reading of the
constant. It answers two booleans, `dispersion_bars` and `ledger_bars`, and
every seam asks it instead of comparing the constant:

- `_floor_clearing_sides` (seam 1, the slots; NOT the badges, see above);
- `append_record` (seam 2, the public record funnel);
- `market_publishability` (the served table's `publishable`, `policy_override`
  and both note sentences, plus the new `policy.dispersion_leg_bars`,
  `policy.ledger_leg_bars` and `policy.registered_policy`);
- `provisional_picks` (`pick_meta.markets_eligible` and the new
  `pick_meta.market_policy_legs`).

The dispersion leg is read through `betting_model.market_theory_ok`, the leg
itself, and not through `market_is_publishable`, which folds the policy back
into the leg (`if SLOT_MARKET_POLICY == "any": return True`) and so cannot
answer a three-value question. The two agree for both older values and
`test_betting_slot_market_policy.py` pins that they agree, so this is a
narrowing of the question asked and not a change of answer.
`market_is_publishable` keeps its meaning and its other callers, and
`betting_model.py` is not edited by this change.

**An unregistered value bars BOTH legs**, which is exactly what `!= "any"` did,
including for a value with the wrong case. A typo in the constant must not be
the thing that opens the slots to a market two legs closed. The served table
says so through `policy.registered_policy`.

**DEFAULT OFF. HEAD is still `SLOT_MARKET_POLICY = "any"`.** Building a value
is not selecting it. Selecting it is one constant in `betting_model.py` and the
owner's own commit, and that commit carries: the constant, this paragraph's
date, and the 7b table re-read. It does NOT carry a `MODEL_VERSION` bump,
because no probability, edge, EV or Kelly number moves: the policy chooses
among rows the pricer already priced.

**What a flip would move, measured on the cached 2026-09-18 board (15 games,
write=False, no request made).** The only ledger-closed market on the box is
the total. The Pick of the Day is PIT moneyline -175 at edge 0.08328 under all
three values and the longshot slot is empty under all three, so on THIS board a
flip moves no published row. What moves is the candidate pool and the table:
floor-clearing candidate sides 5 under `"any"`, 2 under `"ledger_gated"`, 1
under `"dispersion_gated"`, against 5 before the policy under all three
(`pick_meta.n_floor_clearing_sides_before_policy`); `publishable` for the total
True to False under both gated values, and for the runline True to False under
`"dispersion_gated"` only. No number was read against an outcome.

**NAMED FOLLOW-UPS IN assets/betting.js: LANDED 2026-09-18.** Three things in
that file read the policy or its census in a shape the third value outgrew.
They were latent while HEAD is `"any"`, each had the field it needed already on
the payload, and each now reads that field.

**What moved on the served board: nothing.** Measured by rendering every section
of /betting/ against `data/betting.json` (policy `"any"`, both legs False) before
and after, the rendered text of the census sentence, the best-value badge note
and the both-legs market note are BYTE-IDENTICAL, and no number moves anywhere
on the page. The both-legs head keeps its owner-decision receipt because the
sentence now READS it: the policy name comes from `slot_market_policy` and the
date is parsed off `slot_market_policy_note`, which ends "(owner decision
2026-09-05, docs/diamond-betting.md 7d)", so "eligible under the any-market
policy (2026-09-05)" is reproduced rather than re-typed, and a policy whose note
carries no date prints none. Measured across all nine sections at 1280, 1440 and
390, the rendered text of potd, teams, props, parlays, calculators, record,
futures and mybets is byte-identical, and the whole page gains 48 numbers and
loses none, every one of them inside the validation tab. The two changes there
are the repaired vintage blurb and the new basis panel, and both are named
above.

- `marketGateNotes` took its branch from `pol.slot_market_policy === "any"`, so
  under `"ledger_gated"` it printed the both-legs copy for a market both legs
  have closed, including "Clearing one leg does not reopen the market". Under
  `"ledger_gated"` clearing the LEDGER leg alone DOES reopen it, so that
  sentence was false there. It now branches on a new client helper `policyLegs`,
  which reads `market_publishability.policy.ledger_leg_bars` and
  `.dispersion_leg_bars`, falling back to `pick_meta.market_policy_legs`, and
  re-derives nothing from the policy name. Four states are written, one per
  combination of the two booleans, plus a fifth for a payload that carries
  neither field, which says which legs are CLOSED and stops there. THREE OF THE
  FOUR ARE REACHABLE TODAY: `slot_market_policy_legs` maps every value other
  than `"any"` and `"ledger_gated"` to both legs barring, so a theory leg that
  bars always arrives with an evidence leg that bars, and no payload the server
  writes can render the theory-leg-only branch. It is written anyway, and driven
  by a synthetic payload in the tests, so that a fourth registered value cannot
  land on a branch whose sentence nobody has read.
- `bestValueSide` is unfiltered, as measured above, and the repair is to the
  SENTENCE rather than to the ranking: the badge note said the edge floor was
  "the bar the picks use", which is true only where no leg bars. It now reads
  `policyLegs` and, where a leg bars, says the badge is the edge floor alone and
  that a badge is not a claim of eligibility.
- `pickCensus` rendered `pick_meta.n_floor_clearing_sides`, which is
  policy-filtered at seam 1, under the words "cleared the floor", beside its own
  unfiltered count of priced sides. The floor clause now reads
  `pick_meta.n_floor_clearing_sides_before_policy`, and the filtered count is
  named in its own clause only when the two differ.

**A FOURTH THING, NOT ON THAT LIST, CLOSED IN THE SAME PASS.**
`marketGateNotes` returned early on `if (!m.both_legs) return;`, so the page's
only market-bar disclosure was the both-legs one. Under a gated policy a market
closed on ONE leg fills no slot either and the page said nothing at all about
it: on the 2026-09-18 payload the runline is theory-closed with its evidence leg
open, which under `"dispersion_gated"` is barred and silent, and the total is
ledger-closed under `"ledger_gated"` only through its both-legs row. A second
pass now emits one line for any market the payload marks `publishable: false`
whose closing leg is one the policy lets bar, naming which leg bars, which leg
is open, and the served reason verbatim. It is guarded by `pl.bars`, so under
`"any"` it prints nothing and moves no served copy.

**THE ONE-BIT PIN MOVED WITH THEM.**
`test_betting_slot_market_policy.test_the_one_client_side_one_bit_read_is_the_named_follow_up`
bounded the known state at exactly ONE client-side comparison of the policy
string. That comparison is gone, so the test is renamed
`test_no_client_side_one_bit_read_of_the_policy_survives`, holds the count at ZERO and
asserts the two boolean reads in its place. Both halves walk the
COMMENT-STRIPPED source, so a comment that quotes the old expression to explain
why it is gone does not satisfy the pin and deleting a real read does not slip
past it. A new comparison appearing fails there rather than reaching a page
under a policy value nobody has read the copy against.

**The lock and the policy do not fight.** A slot published under one policy is
a claim that was made. Under O21's default (R4-1a, the slot lock) a later build
of the same slate serves the published row verbatim whatever the policy is
now, and the flip is disclosed through `since_published` as
`no_longer_selected` with the sentence riding in `caveat`. That is the same
rule 7e-D writes for a pricer flip: "a slate whose slots were already locked
keeps them". The policy takes effect on the next slate.

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

### 7e-D. The as-served replay: grade the pricer that serves (pre-registered 2026-09-11)

**Written before the code exists, before any replay fit has been run for any
date, and before any replay probability has been computed for any game, related
to any outcome or compared with any price**, in the discipline of 5a, 5c, 7b and
11a. The prose predates the replay's numbers. It does not predate every number
about the served pricer: the list under "Disclosed" names those, and the table
of choices says which of them each choice was made beside. The clause comes from
the 2026-09-11 plan (section 4.2, repair 1) and lane R5 (item D1).

This is an EVAL MODE, not a feature. It reads the five core columns and, once
`SERVE_ATH_PARK` serves, the schema-5 `parks_short_window` block, which is
served data, not dark. It reads no dark column (schemas 3 to 5) and no
`archive-reconstruct` record. Plan section 5 asks each betting item which of
three kinds it is. This one reads only dated records written before each game
(live and git-backfill vintages through 2026-09-27), needs no pre-2026 fit and
no 2027 look, and has its one look in 2026.

It moves no served price until it has run and the owner has acted under O14
below. It changes one published line before the run: landing `SERVE_PRICER`
turns gate 2's line to "not graded" for the served pricer (see the tripwire
below, and the dated correction under section 7 it requires).

#### Why: the pricer that serves is not the pricer gate 2 grades

These facts are the reason for the replay, not a result of it (R5-F1 unless
named).

- **The served fit is in-sample.** `build_context` (`betting_model.py:3791`)
  runs every night at `run_monthly` step 9e-pre1, just before `backtest()`. It
  fits on every completed 2026 game with the LIVE season-to-date boards. The
  working-tree `data/betting_model_context.json` (generated
  2026-09-11T19:55:10Z, uncommitted) reads n 2,200, b1 0.2510, b2 -0.3126,
  b3 3.4731, `diff_shrink` 0.80, home adjustment 0.2149. The committed copy
  (generated 2026-09-05) reads n 2,124, b1 0.2603, `diff_shrink` 0.78. Its
  `source_note` says the fit "is IN-SAMPLE and cannot validate the model".
- **The honest mode grades a different fit.** It fits the 305-game anchored fit
  half on dated boards: b1 -0.0372, b2 -0.0965, b3 0.5948
  (`vintage.coefficients`), `diff_shrink` 1.28 (`vintage.diff_shrink`), home
  adjustment -0.0443 (`vintage.home_field_runs_adj`), all in
  `data/betting_model_eval.json` (7e-B).
- **The two spread differently.** Bin counts only (R5 script
  `m2_served_vs_graded.py`). The served open moneyline home probability sits
  outside 0.4 to 0.6 on 45 of 178 games (25.3%; calibration-ledger open rows,
  home side, one per game). The graded pricer does so on 15 of 548 eval games
  (2.7%). The 2026-09-11 Pick of the Day was priced at 0.755 against a fair
  0.6261 (edge 0.1289). In that range the graded pricer has 10 games in the 0.6
  to 0.7 bin and none above 0.7.
- **Gate 2 certifies the pricer that publishes nothing.** Gate 2's
  `out_of_sample_skill` reads n 548, Brier 0.24334 against the home constant's
  0.24792, t 2.314. The served edges come from a pricer whose only honest record
  is the forward calibration ledger: moneyline 0.243617 on 175 canonical games,
  t -1.006 against a coin, not resolved.
- **Plausible coefficients are not evidence.** 7e-B and 7e-C each found
  coefficient plausibility and out-of-sample accuracy pointing opposite ways on
  this sample. The served set is the most plausible of all (literature priors
  0.32, -0.32, 3.20). That is a reason to grade it, not to trust it.

Plan stop-item X3 follows from this. `out_of_sample_skill` is not quoted as
validation of the served board until this section has run.

#### Disclosed, because 5c rule 1 turns on it

No replay number exists. For this section `betting_model.py`,
`betting_export.py`, `betting_shadow.py`, `tools/betting_calibration.py` and
`run_monthly.py` were read to name functions, the key names of
`data/betting_model_eval.json` were listed, and the context file's header was
read. Nothing was run. Every number quoted below was already on the record: in
this document, in lane R5's outputs, or in the published artifacts as the review
lanes read them.

**A close variant** is any fit of `build_context`'s construction on any board,
live or dated, or any served coefficient set from the history of
`data/betting_model_context.json`, that is graded on, or priced against, games
dated in this section's window, in any market. `build_context`'s construction
means: coefficients by `fit_coefficients` with every fit game priced on one
board, then its tie rate, `diff_shrink` and home adjustment. The honest
construction (each fit game on its own vintage, gradable games only) is the
comparator's family and is not a close variant.

**The known pre-existing relations, each a named exception.** "Inside" means
inside all three criterion eval halves. Those start at the run's 0.6 cut. The
nightly 0.6 cut on 2026-09-11 was 2026-08-16, and the run's falls later as dates
are appended.

| # | Item | Relates the served pricer to | Where |
|---|---|---|---|
| 1 | The served board: nightly prices, edges, slots (the 2026-09-11 Pick of the Day, 0.755 against fair 0.6261, R5-F1) and the shadow ledger (`board_all` ROI -0.06557, lb95 -0.16217, R5 section 0; the 7e-A ROI table) | prices, outcomes | inside |
| 2 | The forward calibration ledger (7b; `data/betting.json -> market_publishability`): moneyline 0.243617 on 175 canonical games, runline 0.257521 on 173, total 0.268081 on 171, LEDGER-CLOSED since 2026-09-03 | outcomes, as priced each night | inside |
| 3 | `data/betting_model_eval.json -> in_sample`, rebuilt nightly: the served construction graded on all 2,200 games ("coefficients and features both leak"), Brier 0.2411 against 0.24923, t 4.37 | outcomes | inside, every game |
| 4 | `-> forward`, rebuilt nightly: a coefficient refit before 2026-07-22 on live boards, graded on the 682 games after it, 0.24039 against 0.24876, t 2.658 | outcomes | inside |
| 5 | `-> run_dispersion` (11a), rebuilt nightly: its Poisson arm is the served construction refit at 2026-07-22 (n_eval 682), with the date-quantile sweep | outcomes | inside |
| 6 | The context file's nightly measurements: `diff_shrink_log_loss` and `prob_calibration_fitted` (all 2,200 games); `total_level_fitted`, `total_dispersion_fitted` and `total_calibration_fitted` (the served coefficients priced on dated boards on the vintage fit half, against runs) | outcomes | the first two inside; the total fits before every cut |
| 7 | 7f, fit half: 305 games before 2026-08-01 priced with the 2026-09-11 served coefficients on dated boards, against runs (mean model total 8.8649 against 8.8066) | outcomes | before every cut |
| 8 | 7f, 26 cached slates (425 games): the same coefficients on dated vintages, against posted prices. It reports the moneyline and runline unchanged by the total flag on every slate and the headline slot changing on 6 slates, so moneyline and runline edges were computed | prices | inside |
| 9 | 5a arm 1, specifications A to D (46 games, 2026-08-06 to 2026-08-09): A the served set of 2026-08-09, B the vintage-window refit, C the full-archive in-sample fit with corrections off (the served coefficient fit), D the literature priors. Only the paired live-minus-backfilled Brier difference was reported (+0.000450 to +0.001167) | outcomes, paired across stores | before every cut |
| 10 | 5i-A: `build_context` refit with the A's park on the 2,200-game cache, and the 2026-09-11 board repriced with it (Pick of the Day edge 0.12368) | prices | inside |
| 11 | R5's spread counts (m2): bin counts | nothing | n/a |
| 12 | The git history of `data/betting_model_context.json`: 8 commits, the last 944502c5 (2026-09-06), a per-date record of served sets. No relation has been computed on it | nothing yet | n/a |
| 13 | The nightly `ridge_fit` and `ridge_fit.fit_window_probe`, rebuilt by `backtest()` every night (`betting_model.py:5948-5951`). Comparator family, not a close variant; listed because they bear on the comparator and the Holm members | outcomes | inside |

**Why none of them can steer the replay arm.** The arm has nothing left to fit
by hand: it is `build_context` as it stands. The criteria are committed
constants with a stricter z. What remains are the choices in the next table.
Several were made with items 1, 2, 8 and 13 in view, and that is the disclosure.
The standing is therefore the 7e preamble's, not 5a's: read the clauses as fixed
and the listed knowledge as what the choices were made beside.

#### The choices this section makes

| # | Choice | Source and date | Made with in view |
|---|---|---|---|
| 1 | Grade the served pricer at all | R5 D1 and plan 4.2 repair 1 (committed bfb000be), 2026-09-11 | the spread counts, the Pick of the Day against its fair price, the forward ledger (t -1.006) |
| 2 | Seats: the replay is the challenger, the vintage pricer the incumbent, so the burden is on the served pricer | R5 D1 ("non-inferiority ... against the vintage pricer"), 2026-09-11 | as 1 |
| 3 | Comparator: the anchored honest pricer, not a per-split refit or 7e-B's grown OLS | this section, 2026-09-11 | 7e-C, the nightly probe (below) |
| 4 | Criteria: the `RIDGE_FIT_GATE_CRITERIA` form at 0.6, 0.7, 0.8 | R5 D1 and plan repair 1, 2026-09-11 | the 7e-B record |
| 5 | Family: 7e-B, 7e-C, 7e-D | plan repair 1 and R5 D1, 2026-09-11 | the 7e-B and 7e-C records |
| 6 | m = 3, one intersection-union p per member; Holm applied to check 2 as well as check 1 | this section, 2026-09-11 | 7e-B's Elo readings |
| 7 | Family alpha one-sided 0.05, locked | this section, 2026-09-11; no source names one | the forward ledger |
| 8 | Window end 2026-09-27; run on or after 2026-09-28 and by 2026-10-31 | season end (plan 5); the deadline is this section's | the forward ledger |
| 9 | INDETERMINATE takes the FAIL response | O14 DEFAULT, extended here; the plan's text says "if it fails" | none |
| 10 | A miss on check 2 alone flips nothing | this section, 2026-09-11 | 7e-B's Elo readings |
| 11 | The graded state, the provenance rule, the store | this section, 2026-09-11 | none |
| 12 | Postseason not graded | the 5f and 5g precedent and the O20 default. The owner's 2026-09-11 5e answer went the other way (count); here the choice is moot because the window ends on the last regular-season day | none |

**The comparator (choice 3) rests on two facts that no reading moves**: it is
the pricer gate 2 grades, and it is the pricer the O14 response would serve.
Disclosed beside it: 7e-C read grown minus anchored -0.002789 (t -2.107) at 0.6
on 2026-09-06. The nightly `fit_window_probe` in the working-tree artifact
(generated 2026-09-11T17:13:58Z, cuts 2026-08-16, 08-22, 08-29) reads -0.001465
(t -1.764, lb95 -0.002831) at 0.6, +0.002557 (t 1.803, lb95 +0.000224) at 0.7
and +0.004807 (t 2.287, lb95 +0.001349) at 0.8. On that reading grown beats
anchored at 0.7 and 0.8, so the anchored comparator is the easier one to be
non-inferior to at those splits.

**The family alpha (choice 7) is locked at this commit.** It may be changed only
to tighten it, by a dated correction committed on or before 2026-09-27.

#### The replay arm

For each eval date D:

1. **The vintage.** V_D is the newest admissible record (below) with
   `covers_through < D`: the `_vintage_resolver` and
   `inputs_as_of(D, allow_fallback=False)` contract. A date with no such record
   is skipped and counted (section 6), never priced on the fallback.
2. **The fit set.** F_D is every completed 2026 regular-season game in the game
   manifest (below) dated before D, gradable or not. It is the set a served
   build on D's night would have fitted. On a missed night nothing was fitted,
   and the replay grades the construction, not the build that ran.
3. **The fit.** `build_context`'s own procedure on F_D, with V_D's team inputs,
   starters and park index in place of `team_inputs()`, `starter_inputs()` and
   `park_index()`. It solves the coefficients and the shrunk extra-innings home
   rate, then `diff_shrink` and the home adjustment in one solve and one
   refinement pass (the loop runs twice). Each SERVED sub-fit is solved on F_D:
   dispersion only if `SERVE_RUN_DISPERSION`, the runline tie split
   (`_fit_runline_tie_split`) only if `SERVE_RUNLINE_TIE_SPLIT`, the Platt map
   and the three total fits only if their flags serve. Unserved sub-fits are
   skipped for each date.

   Every F_D game is priced on V_D's one board. That is the served build's
   in-sample construction, contamination included, and the contamination is
   part of the object being graded. Nothing dated D or later reaches the fit,
   so the GRADE leaks nothing.
4. **The price.** D's games are priced with that fit on V_D through
   `game_probabilities`, the same call `_grade` makes, with the starters the
   honest mode uses.

**The leak assertion, per date.** The run persists and asserts, for every D,
max(F_D date) < D and V_D `covers_through` < D. A failure makes the run VOID.

**Frozen inputs (to be built).** At the first nightly after 2026-09-27, before
any replay code touches real data, two manifests are written:

- **The store manifest.** Every record in the store: file, sha256,
  `provenance.source`, `captured_at`, `covers_through`. Admissible: `live`
  records captured on or before 2026-09-27T23:59:59Z, and `git-backfill` records
  captured on or before the date of this section's commit. `archive-reconstruct`
  records are not read by either arm (the O22 ALLOW default governs other
  sections). A record added or overwritten after its cutoff (an I2 repair, a
  backfill run, a `--force` snapshot) is not read.
- **The game manifest.** `game_pk` and `officialDate` of every completed
  regular-season 2026 game dated on or before 2026-09-27 in the game cache at
  that moment.

Both arms read only what these list. Per date, the result persists V_D's file,
sha256, provenance and `covers_through`. The store is the
`.cache/leaderboard_vintages/` of the box named as the single writer under O16
(I10). If none is named by then, it is this box's, the store R5-F3 measured. The
host name is recorded.

**To be built:**

- **A `build_context` seam** that takes the games and the boards as arguments and
  writes nothing. The replay IS `build_context`, not a copy.
- **A seam self-check**, `--as-served-replay --seam-check`. Fed today's live
  inputs and every completed game, the seam's served keys serialize
  byte-identical to the ones `build_context(write=False)` returns:
  `coefficients`, `extra_inning_home_rate_shrunk`, `diff_shrink`,
  `home_field_runs_adj`, and each flag-served key (`run_dispersion_alpha`,
  `extra_inning_runline_split`, `prob_calibration`, `total_level`,
  `total_dispersion_alpha`, `total_calibration`). The `_fitted` measurements are
  not compared. This is the one real-data call permitted before the run,
  because it reproduces the nightly build, which is already published. It
  prints only the key-by-key match.
- **`as_served_replay`**, reached only by the CLI flag `--as-served-replay`;
  `backtest()` never calls it. It refuses to run before 2026-09-28 or after
  2026-10-31, with any window end other than 2026-09-27, or without both
  manifests. The three dates are literals, `AS_SERVED_REPLAY_WINDOW_END`,
  `AS_SERVED_REPLAY_FIRST_RUN` and `AS_SERVED_REPLAY_LAST_RUN`, pinned by test.
- **The result file** `data/betting_as_served_replay.json`, written once by the
  CLI and never by `backtest()`, which rewrites the whole eval file every night
  (`betting_model.py:5979`).
- **A cache of per-date fits** keyed by (D, V_D sha256, `MODEL_VERSION`). It is
  never filled from the real archive before the run. Tests use synthetic
  fixtures only.

**Four approximations, disclosed:**

- **Board age.** The served build on D read the boards the vintage store froze
  that same night. Under `covers_through < D`, that record cannot price D. So
  the replay runs one board refresh behind in steady state, and further behind
  on missing nights: 10 of 36 live-era nights since 2026-08-06 are missing (26
  on disk), and vintage age at grading has median 1 day, p90 8, max 13
  (R5-F3). The replay is the served CONSTRUCTION on the dated board, not a byte
  copy of what served. The calibration ledger stays the only record of the
  exact served prices.
- **Starter identity.** Both arms read the final feed's `probablePitchers`. That
  matched the first pitcher used on 2,191 of 2,197 home sides and 2,194 of 2,197
  away sides (R5-F6). The schedule cache at its LAST pre-pitch refresh disagreed
  with the first pitcher on 19 of 1,968 sides (0.97%) and was TBD on 41. The
  03:10 ET board read an earlier refresh, so 0.97% is a lower bound on how often
  the board's starter differed. The hindsight affects both arms' inputs
  identically. Its effect on each arm's score is not measured, and equal inputs
  need not mean equal benefit: the served fit weights the pitcher term about 3.2
  times the graded one (b2 -0.3126 against -0.0965).
- **The Athletics' park.** Once `SERVE_ATH_PARK` serves, the served build prices
  A's home games at 1.1919 on the live index (the 5i-A refit moves b3 from
  3.386903 to 3.852374). A vintage record reaches that value only through its
  own dated `parks_short_window` block (schema 5), and no schema-5 vintage is on
  this box yet (the newest, 2026-09-09 and 2026-09-10, are schema 4). So for
  nearly every D both arms fit and price A's home games at a neutral park, where
  the served pricer does not. Recorded counts: 72 A's home games, 55 before
  2026-08-01 and 17 after (DB 5i-A). The seam self-check runs on live inputs and
  cannot catch this. The flag is not back-filled into older records, because
  the 2025-2026 factor contains 2026 data from after D. **A fixed sensitivity
  row, never a criterion:** the same grid with A's home games dropped from every
  eval half, both arms, fits unchanged.
- **Late finals.** The game cache carries no arrival time, so F_D cannot be cut
  at D's nightly exactly. A game dated before D whose final arrived after D's
  nightly (a suspended game resumed later) would enter F_D. Where the cached row
  marks a resumption on or after D (to be built), the game is dropped from F_D
  and counted. Where it cannot tell, the difference is disclosed, not closed.

#### The comparator

The comparator is the graded vintage pricer, exactly as the shipped honest mode
builds it, on the same manifests. That is `_grade`, through `_grade_vintage`, on
the anchored fit window: the earliest whole slates crossing
`VINTAGE_FIT_TARGET_GAMES` (`_vintage_cut_index`; `VINTAGE_FIT_WINDOW_GROWS`
False). Each fit game is priced on its own vintage. The tie rate, `diff_shrink`
and the home adjustment are solved on that window.

The comparator is the same at every split, because `_vintage_cut_index` caps the
anchored cut at `VINTAGE_FIT_MAX_DATE_SHARE` (0.5) of the dates, below the 0.6
quantile. It is also the pricer the O14 response would serve.

The two arms differ in fit set, features and correction procedure. Each arm is
exactly the pricer it names, so that difference is the estimand, not a
confound.

#### The window and the splits

- **Sample.** Vintage-gradable regular-season games in the game manifest, dated
  on or before 2026-09-27. Postseason games are not graded (choice 12).
- **Splits.** Date quantiles 0.6, 0.7 and 0.8 of those gradable dates
  (`DISPERSION_SPLIT_QUANTILES`), cut the way `ridge_fit_gate` cuts them. The
  eval half is every gradable game dated on or after the cut.
- **Guards.** A split whose cut falls inside the comparator's fit window, or
  where the two arms do not price the identical games, makes the run VOID. It is
  an engineering failure, never a FAIL.
- **The honest window, reported.** The anchored window (cut by
  `_vintage_cut_index`) is the window gate 2 reads. It is reported with the full
  section 6 ladder: `_benchmarks_block`, recomputed on the replay's per-game
  probabilities, every tier on identical games under the claim rule. It also
  carries the replay's `skill_vs_home_base`. Nothing on this window is a
  criterion. It is what gate 2 reads after a pass.

#### The criteria

The criteria use the `RIDGE_FIT_GATE_CRITERIA` form (committed 2026-09-06,
7c45c5c1). The replay takes the challenger seat and the graded vintage pricer
the incumbent seat. The one-sided critical value is the family's z = 2.128 (see
the Holm family below) instead of 1.645. At split quantiles 0.6, 0.7 and 0.8,
ALL THREE or nothing:

1. **Non-inferiority** against the graded vintage pricer. Paired per-game Brier,
   with delta = vintage minus replay (positive means the replay is better):
   delta - 2.128 x se >= -0.001.
2. **Superiority** over the literature Elo tier (`tools/betting_elo`, the
   section 6 results-only floor). Paired per-game Brier, Elo minus replay:
   t >= 2.128.
3. **Log loss** not worse. Paired log loss, vintage minus replay, >= 0 on the
   point estimate.

**Floors.** The comparator's fit window and every F_D need at least
`VINTAGE_MIN_FIT_GAMES` (100) games. Every eval half needs at least
`VINTAGE_MIN_EVAL_GAMES` (50). A split below a floor makes the run VOID.

**The verdict label** follows 7e-B's rule. All three splits pass: PASS. A mixed
grid: INDETERMINATE. None: FAIL. What each label does is in the response below.

**The recorded prior on check 2.** At each 7e-B split the vintage construction
(7e-B's OLS arm, grown fit half) read Elo t 1.625, 1.645 and 1.937
(`elo.ols_vs_elo`), all below 2.128. The nightly `ridge_fit` in the working-tree
artifact reads ridge-vs-Elo t 1.477 at 0.6. On the served window the graded
pricer leads Elo by 0.00106 Brier on 548 games (0.24334 against 0.2444). Check
2 is a bar on the model class (7e-B), so a miss there alone says nothing about
which pricer is better. The incumbent's own reading, `elo.vintage_vs_elo`, is
persisted at the same z on the same games beside `elo.replay_vs_elo` (both to be
built; the existing keys are `ols_vs_elo` and `ridge_vs_elo`). It is never a
criterion.

**Power and the burden.** Non-inferiority at a 0.001 margin and z 2.128, between
two pricers that spread this differently (25.3% against 2.7% outside 0.4 to
0.6), may not resolve even if the served pricer is as good. The burden is on the
served pricer by design (choice 2): too little evidence means the vintage pricer
serves under the O14 default. Persisted per split, never a criterion and with no
response: sqrt(n_eval) x RMS(p_replay - p_vintage), computed before any eval
outcome is joined.

**The text above becomes constants.** It is carried in
`AS_SERVED_REPLAY_CRITERIA`, with `AS_SERVED_REPLAY_Z = 2.128` as a literal (both
to be built). A test pins both, the way it pins `DISPERSION_GATE_CRITERIA`.
`RIDGE_FIT_GATE_CRITERIA` is not edited, because it still governs 7e-B.

**Scope: the moneyline**, the market these criteria and gate 2 are written in.
The replay's runline and total are priced on the same games and reported in
7e-A's layout (same games, against the open). They are never criteria, and the
total report prints no observed Over rate. The total is ledger-closed and its
Over lean is disclosed (7f to 7h). Nothing here repairs it.

**Persisted with the grid:**

- Per split: both arms' Brier and log loss; the delta, sd, t and the bound at
  z = 2.128; `elo.replay_vs_elo` beside `elo.vintage_vs_elo`; the power
  reading; the share of each arm's probabilities outside 0.4 to 0.6.
- The A's sensitivity row.
- Per date: the replay's coefficients and corrections, V_D's file, sha256,
  provenance and `covers_through`, n and max date of F_D, and the leak
  assertion.
- For the run: the host, the HEAD commit, `model_version`, `SERVE_PRICER`, the
  state of every `SERVE_*` flag and `VINTAGE_FIT_WINDOW_GROWS`, and the seam
  self-check result.

The verdict reads the three criteria and nothing else.

#### The Holm family: 7e-B, 7e-C and 7e-D

The three are estimators of one coefficient vector on one eval archive (R5 D1),
so they form one Holm family, m = 3.

- **Family alpha: one-sided 0.05, locked at this commit** (choice 7). Nothing in
  this document or the plan names a betting family alpha. 0.05 is the one-sided
  level every single gate in this document tests at. It may only be tightened,
  by 2026-09-27.
- **Each member's p** is the intersection-union p of the member's conjunction:
  the largest one-sided normal p among its inferential checks across its
  splits. A point-estimate check carries no p. A member that misses one is a
  non-rejection.
- **Why a conjunction needs no correction within itself.** A member passes only
  if every check passes, so its false-pass rate is bounded by its weakest check.
- **The departure from the house form, stated.** Plan section 2.3 reads "both
  legs of every arm count in m", for the Z1 driver families. Here each member's
  verdict is one conjunction of all its checks at all splits, and the
  intersection-union p of a conjunction is a valid p for that verdict, so Holm
  over three members holds the family-wise rate at alpha. Counting legs would
  also hold it, more conservatively (m = 5, step-1 z 2.326). It would also let
  one member's legs clear at different Holm steps: 7e-B's check 1, which cleared
  at all three splits, would enter as a leg of its own. The member form reads
  each member as the verdict it is.

**What joining does to 7e-B and 7e-C: nothing.** Both were read on 2026-09-06
under their own single-test bars, and neither shipped. Their verdicts, their
flags (`SERVE_RIDGE_FIT` False, `VINTAGE_FIT_WINDOW_GROWS` False) and their
tables stand as recorded, and each member's family p is pinned to that record.
`backtest()` recomputes both blocks every night (`betting_model.py:5948-5951`).
The nightly re-runs are not family members and do not re-label the recorded
verdicts. The working-tree artifact reads `ridge_fit.verdict` "fail" at cuts
2026-08-16, 08-22 and 08-29, where the committed copy (2026-09-07) reads
"indeterminate", and the probe values given above.

Both members carry p above 0.05, on the record and on the nightly reading.
7e-B's check 2 missed at t 1.641 and 1.632 on 2026-09-06 (nightly: 1.477 at
0.6). 7e-C's lb95 fell below -0.001 at all three splits on 2026-09-06 (nightly:
-0.002831 at 0.6).

**7e-D's bar is Holm's first step.** Holm never steps past its first threshold,
so 7e-D's bar is the step-1 bar: one-sided 0.05 / 3 = 0.016667, z = 2.128. That
holds whatever order the p values fall in, because a p at or below 0.016667 is
below both pinned member p values.

**The family is closed at three.** N1 stage 2 is not a member, and no alpha is
reserved for it. Its stage 1 is a new data source (pre-2026 play-by-play, R5
N1), and its stage 2 is graded against whichever pricer this section leaves
serving. Its own section declares its own family and discloses this one and its
verdict. Any other later estimator on this archive does the same. Nothing can
move 7e-D's bar once 7e-D has run.

#### The run: once

- **When.** Once, on or after 2026-09-28 and by 2026-10-31, after the result
  block of the 7h re-read (O23 DEFAULT, 2026-09-28) is committed. The 7h read
  goes first, so nothing the replay reports can reach it.
- **The graded state, named now.** The run waits for all of these:
  - `SERVE_PRICER` "context", landed with its tripwire and ledger stamps (below);
  - `SERVE_ATH_PARK` True and `SERVE_RUNLINE_TIE_SPLIT` True, each landed with
    its `MODEL_VERSION` bump and `--context` re-run (owner answers of
    2026-09-11);
  - `SERVE_RUN_DISPERSION`, `SERVE_PROB_CALIBRATION`, `SERVE_RIDGE_FIT` and
    `VINTAGE_FIT_WINDOW_GROWS` False, as at this commit;
  - the `SERVE_TOTAL_*` flags as they stand. They do not reach the moneyline;
    a 7h flip, if the owner makes one, is recorded.

  If the state has not landed by 2026-10-31, or anything else that reaches the
  moneyline has changed by the run, the run is VOID.
- **What the verdict covers.** The graded state's moneyline construction. A
  later `MODEL_VERSION` bump whose test asserts the moneyline byte-identical
  (the 7f to 7h form) keeps it. After any other bump, gate 2 reports the served
  pricer "not graded" until a re-read, registered before it runs, has run.
- **The owner's O14 answer** is recorded as a dated correction under this
  section BEFORE the run. Until then the defaults below stand.

#### The response, pre-registered (O14, DEFAULT pending the owner's answer)

**PASS** (all three checks at all three splits).

- `SERVE_PRICER` stays "context". No price moves, and there is no bump.
- `backtest()` publishes the replay's grading nightly as
  `data/betting_model_eval.json -> as_served`, beside `vintage` (to be built),
  and gate 2 reads its `skill_vs_home_base`.
- From that build on, `out_of_sample_skill` may be cited for the served board,
  as that number, whatever it says. A pass of this section is not a pass of
  gate 2. Before that build it may not be cited (X3).

**FAIL response: check 1 or check 3 misses at any split** (label INDETERMINATE
or FAIL; INDETERMINATE taking this response is part of the O14 default). The
graded vintage pricer serves. One commit carries all of the following:

- `SERVE_PRICER = "vintage"`.
- A `MODEL_VERSION` bump.
- The tripwire, moved with the flag.
- A `--context` re-run, so the served coefficient vector and its three
  corrections are the honest mode's anchored fit. The context-fitted set stays
  published beside them as a measurement (the `_fitted` convention). If the
  owner has flipped `SERVE_TOTAL_CALIBRATION`, this re-run also re-fits the
  served 7h pair, because `build_context` fits it on the served coefficients.
- The ledger stamps and filters below, if they have not landed already.

The flip takes effect at the next nightly build. A slate whose slots were
already locked (O21 default) keeps them.

Accepted before the run: the Pick of the Day, the longshot and the value badges
may go empty until a pricer clears. The shared floor (`PROVISIONAL_MIN_EDGE`
0.06, 7a) is not lowered, and no slot gets a floor of its own. An empty slot
names the floor it could not clear. Whether the slots empty depends on O15.
Under its default (publishable markets only; the policy value is to be built,
and was built 2026-09-17 as `"ledger_gated"` and registered at the end of 7d),
the ledger-closed total cannot fill a slot. Under `SLOT_MARKET_POLICY = "any"`
as it stands, the total's Over lean can fill them under either pricer (on the
served set, 232 of 425 re-priced games carried an Over clearing 0.06, 7f), with
the lean disclosed on the row. The slots refill when the served pricer's own
sides clear the unchanged floor, or when a later pricer clears its own
registered gate (N1 stage 2 is the named route).

The flip is outward-facing and is the owner's act. From the flip's commit on,
gate 2 reads the served pricer's construction graded on dated boards, while the
served prices come from live boards one refresh ahead (the board-age gap above).
So `out_of_sample_skill` may be cited for boards priced after the flip, and
never for rows the context pricer priced.

**Check 2 alone: checks 1 and 3 hold at every split, and check 2 misses at one
or more.** No flip. X3 stays in force, gate 2 reports the served pricer as not
graded, `elo.vintage_vs_elo` is shown beside `elo.replay_vs_elo`, and the choice
of pricer returns to the owner.

**VOID.** A disqualified replay; a guard or floor failure; a seam self-check
that is not byte-identical; a failed leak assertion; the graded state not
reached, or changed; or no run by 2026-10-31. There is no verdict. X3 stays in
force, gate 2 reports the served pricer as not graded, and the choice of pricer
returns to the owner.

#### `SERVE_PRICER`, the tripwire and the ledgers (to be built)

`betting_model.SERVE_PRICER` takes the values "context" or "vintage". It lands
at "context", which is what serves today, so landing it moves no price and needs
no bump.

Its tripwire test (for example `test_betting_serve_pricer.py`) asserts five
things:

1. **Gate 2 reads the pricer that serves.** The `out_of_sample_skill` gate in
   `min_edge_gate` reads the skill block that `SERVE_PRICER` names: `vintage`
   for "vintage", `as_served` for "context". When that block is absent, or
   grades a moneyline construction no verdict covers, the gate reports
   `open: false`, with the reason that the pricer that serves has not been
   graded. The graded vintage pricer's number rides beside it, labelled as that
   pricer's.
2. **The served context matches the flag.** Its coefficients and three
   corrections are the named pricer's.
3. **The flip changes the version.** `model_version` differs between the two
   states.
4. **The seam is exact.** The seam self-check (above) passes on a fixture.
5. **The ledgers do not pool the two pricers.** Today they would: calibration
   rows (`tools/betting_calibration.record_slate`) and shadow rows
   (`betting_shadow`) carry no version, only public record rows do
   (`betting_export.py:1919`), and `market_gate`
   (`tools/betting_calibration.py:696`) and the gate-3 sweep
   (`_shadow_graded_bets_by_tag` into `sweep_min_edge_by_tag`) read every row.
   Both row kinds are stamped with `serve_pricer` and `model_version`, and both
   readers take only rows of the serving pricer. An unstamped row counts as
   "context", the only pricer that has ever served.

**7b across a flip.** 7b's dwell state carries over. A market LEDGER-CLOSED at
the flip stays closed, and its re-open test reads the new pricer's rows only
once they reach 7b's 100-game floor. Without that rule, filtering would re-open
the total within three nights, because `worse_than_coin_95` is false below 100
games. This amends 7b's wiring and is recorded as a dated correction under 7b
in the flip commit (part of the O14 default). Filtering by `MODEL_VERSION` in
general, which the flip idiom promises ("so the ledgers never pool two
pricers") and the code does not do, is a standing gap. It is disclosed here and
not repaired.

**What landing it does before the run.** Today gate 2 reads the vintage block
(t 2.314) for a board the context pricer prices. With the flag at "context" and
no replay yet, gate 2 reports not graded. That re-points section 7's gate 2 from
"that sample" to the pricer that serves, so a dated correction under section 7
lands with the code. `min_edge` is null either way: gate 1 stood at 548 of 600
on 2026-09-11, and gate 3 is closed (`board_all` ROI lb95 -0.16217, R5). What
changes is the published gate-2 line, not a price. That is X3 made mechanical.

#### Disqualification

These void the replay's verdict under 5c rule 1:

- any number relating the replay arm, or a close variant, to an outcome or a
  market price, computed before this section is committed or outside the one
  registered run;
- any fill of the per-date fit cache from the real archive before the run;
- any run of `--as-served-replay` other than the seam self-check before
  2026-09-28 (the CLI refuses; a bypass voids).

These do not:

- the thirteen listed items in their current form, including every nightly
  rebuild of items 1 to 6 and 13 by the served pipeline. A change to a listed
  item's construction is a new instance;
- the served pipeline pricing the current slate as it serves, including every
  `--context` re-run, and a flip's before-and-after comparison on the current
  board in the 5i-A form. The flips in flight (the A's park and the runline tie
  split, workflow wf_02e3c0ae-178) fall here only if they reprice the current
  board alone. A re-price of past slates with a served coefficient set (the 7f
  form) is a new instance;
- the seam self-check;
- publication after the verdict: the PASS response's nightly `as_served` block
  and the FAIL response's `--context` re-run.

Any new instance voids the verdict. The result block lists every instance it
knows of.

#### What this section does not claim

- **It does not claim either pricer is better, and states no expected
  verdict.** It records the prior on check 2 (above). The rest points both ways.
  Today's served fit uses about seven times the games (2,200 against 305:
  context `n_games`, `vintage.n_fit_games`, R5-F1), and every F_D inside the
  window is smaller than 2,200. 7e-C found a grown fit window worse at the 0.6
  split on 2026-09-06 (delta -0.002789, t -2.107), and the nightly probe now
  reads it better at 0.7 and 0.8. The replay's fit carries in-sample features
  that 7e-C's did not.
- **It does not reopen 7e-B or 7e-C.** Their nightly recomputation continues
  and is not a family member. It does not change the honest mode, gate 1's
  counter or the 600-game clock. It reads no dark column and touches no dark
  clock.
- **It does not repair the total or the runline.**
- **"What ships from 7e" below still describes 2026-09-06.** That paragraph is
  left as written.

Committed alone, docs only, ahead of the code that implements it. Nothing in
this section was measured against a game result.

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

### Result (run 2026-10-02, once): FAIL, and the Poisson total keeps serving

**The late date.** The read was registered for 2026-09-28 and ran on 2026-10-02 at 15:31
-0400, four days late, under the block's slip rule ("it runs on the first day it can, no
later than 2026-10-06, under the same window, code and invocation"). No box, cache, feed or
readiness failure caused the slip: no session ran the read between 2026-09-28 and
2026-10-01, and plan Part 8 (8.B 'The clock: the fWAR epoch calendar') had slotted it for
2026-10-04. It ran on the first day it was dispatched. The window is fixed at games dated on
or before 2026-09-27, so the slip moves no game into or out of it. This is still the one
read.

**The look record: none.** The 7h, 7i and 5c-A sections record no look, and `git log
--since=2026-09-11` holds no commit that ran `total_calibration_gate`, any of the five
other functions named under "What counts as a look", or `--total-calibration`. Nothing was
forfeited.

**Ordering.** 7i did not run: its look code does not exist (closure recorded under 7i's
"The look", 2026-10-02). So 7h ran alone, and first.

**Withholding.** The 5k registration and the two Holm-family amendments (5d-C and 5h-A)
were all committed before the read, in d79067a5 (2026-09-11 19:56:47 -0400). The per-line
rates are printed below, not withheld. This printout now exists, so any later amendment to
5d-C, 5h or 5k names it.

**Readiness, in the worktree, before the read.** The top-up ran first in the main tree,
`python -c "import betting_model as bm; bm.build_game_cache(refresh=True)"`, which logged
"StatsAPI returned 14 final games for 2026-09-27..2026-10-02" and left 2,429 cached 2026
rows, last date 2026-09-27. The readiness one-liner, verbatim, printed `853 229 229`:
- old gradable (dated on or before 2026-09-10): 853, equal to the first run's 305 + 548;
- new in window (2026-09-11 to 2026-09-27): 229;
- new gradable: 229, above the floor of 50.

**What ran.** The read one-liner, verbatim, in a detached worktree of 37e9382d whose
`prospect-tracker/.cache` was a directory junction to the main tree's `.cache`:
- worktree commit 37e9382d00b2dd56dc4b890decdd2be5183f0b64;
- `betting_model.py` blob 873713d04c06d6493f601d549babcc6a4777c733;
- `leaderboard_vintages.py` blob d69aa9be27882fc41bb9fc86beaf9410d5faa1e9;
- main tree HEAD 6deecb7d55ec63b209c12494876597bba123141d;
- Python 3.13.9 (Anaconda), numpy 2.3.5;
- `MODEL_VERSION` `betting_runs_v1`; `SERVE_TOTAL_CALIBRATION`, `SERVE_RIDGE_FIT`,
  `SERVE_RUN_DISPERSION`, `SERVE_ATH_PARK`, `SERVE_RUNLINE_TIE_SPLIT`,
  `SERVE_TOTAL_LEVEL`, `SERVE_TOTAL_DISPERSION`, `SERVE_PROB_CALIBRATION` and
  `VINTAGE_FIT_WINDOW_GROWS` all False; `SERVE_PRICER` absent. These were printed from
  the imported worktree module before the read and match the flag table above.

Before the read, the reporting line was dry-run on a hand-made dict of None values (no
game touched), and the read's stdout and stderr were teed to disk. It exited 0.

`n_window` 2,429, `n_gradable` 1,082, `n_skipped` 1,347 (games with no vintage strictly
before them, never graded on the fallback), last date in the window 2026-09-27.

| split | cut | fit / eval | a | b | grid log loss delta | t | lines not worse | pass |
|---|---|---|---|---|---|---|---|---|
| anchored | 2026-08-01 | 305 / 777 | 0.472 | -0.246 | -0.0041 | -0.31 | 2 of 4 | no |
| 0.6 | 2026-08-26 | 642 / 440 | 0.552 | -0.213 | -0.0016 | -0.10 | 2 of 4 | no |
| 0.7 | 2026-09-03 | 752 / 330 | 0.564 | -0.188 | -0.0013 | -0.07 | 1 of 4 | no |
| 0.8 | 2026-09-11 | 853 / 229 | 0.566 | -0.188 | -0.0099 | -0.44 | 2 of 4 | no |

The delta is Poisson minus candidate, so a negative value means the mapped total scored
worse than the Poisson on the point estimate. The cuts land where the block said they
would: the anchored cut holds, 0.6 and 0.7 move to 2026-08-26 and 2026-09-03, and the 0.8
cut is the first new date, with the first run's 853 games as its fit half.

**The anchored reproduction.** Cut 2026-08-01 (registered 2026-08-01), n_fit 305 (305), a
0.472 (0.472; printed 0.47218), b -0.246 (-0.246; printed -0.24622). All four match, so
the read is not VOID.

Over rates on each eval half: observed, served Poisson, and mapped.

| split | line | observed | Poisson | mapped |
|---|---|---|---|---|
| anchored | 7.5 | 0.578 | 0.653 | 0.513 |
| anchored | 8.5 | 0.501 | 0.519 | 0.448 |
| anchored | 9.5 | 0.402 | 0.388 | 0.387 |
| anchored | 10.5 | 0.324 | 0.273 | 0.329 |
| 0.6 | 7.5 | 0.611 | 0.642 | 0.529 |
| 0.6 | 8.5 | 0.530 | 0.509 | 0.452 |
| 0.6 | 9.5 | 0.425 | 0.380 | 0.381 |
| 0.6 | 10.5 | 0.341 | 0.267 | 0.315 |
| 0.7 | 7.5 | 0.597 | 0.655 | 0.544 |
| 0.7 | 8.5 | 0.518 | 0.523 | 0.466 |
| 0.7 | 9.5 | 0.421 | 0.393 | 0.393 |
| 0.7 | 10.5 | 0.324 | 0.278 | 0.325 |
| 0.8 | 7.5 | 0.620 | 0.657 | 0.546 |
| 0.8 | 8.5 | 0.537 | 0.525 | 0.468 |
| 0.8 | 9.5 | 0.441 | 0.395 | 0.394 |
| 0.8 | 10.5 | 0.319 | 0.280 | 0.326 |

**The verdict.** No split passes either check, so under the rule fixed before the run the
grid is FAIL (`verdict` "fail", `ship` false). The first read's point-estimate gain at the
anchored split (+0.0112 on 548 games) is negative on 777 (-0.0041), and the 229 new games
graded alone at the 0.8 split read -0.0099 (t -0.44). The fitted (a, b) stay in the first
run's range (a 0.47 to 0.57, b -0.19 to -0.25). What moved is the eval games: more of them
went over 7.5 and 8.5 than in the fit halves (anchored fit half 0.534 and 0.433, eval half
0.578 and 0.501), and the map prices both lines below the observed rate (0.513 and 0.448
on the anchored eval half). At 8.5 the Poisson (0.519) sat closer to the observed rate
than the map did.

**What follows, by the block's own text.**
- `SERVE_TOTAL_CALIBRATION` stays False. Nothing was flipped and no owner question is
  raised.
- The Poisson total keeps serving, and the Over lean stays DISCLOSED on every affected row
  (owner answer 2026-09-11).
- 7h closes. "This is the only re-read 7h gets." A later look at the map, on 2027 games
  included, is a new candidate with its own section under 5c rule 1, and that section
  discloses both 7h reads.
- The late-season reading belongs to 5k, 5d-C and 5h, read on 2026-10-07 in one Holm
  family.

## 7i. The score kernel: one joint distribution fitted on pre-2026 finals (pre-registered 2026-09-11)

**Written before any reference table, tilt or gate for this candidate exists in code,
and before the candidate has been computed for any game, pre-2026 or 2026, or related
to any outcome or any market price**, in the discipline of 5a, 5c, 7b, 7g, 7h and 11a.
It is committed alone, docs only, after the 7h re-read block and by 2026-09-16 (plan
5.2, W0). It sits directly under that block and above the `---` before section 8. If it
lands after 2026-09-11, the heading carries the commit date.

It is candidate N2 of the 2026-09-11 plan
(`docs/master-plan-2026-09-11-war-epoch-drivers-betting.md`, section 4.2). It is the
successor 11a names ("a bivariate model with a one-run atom"), and the 7g result names it
too ("a bivariate model of the two scores"). It takes up the B-RUNLINE lane of the
2026-09-05 plan (`docs/master-plan-2026-09-05-opus.md`) and keeps that lane's first
binding constraint: fit on pre-2026 finals only. Where it departs from B-RUNLINE or from
the plan, the list near the end says so and why. Plan section 5 admits three kinds of
betting candidate, and this is the kind fitted on pre-2026 data. Nothing served reads
anything here, and nothing served changes.

**Disclosed, because 5c rule 1 turns on it.** Every number this section quotes was on
the record before it. Each describes the INCUMBENT or the fit data, never the candidate.
- **The incumbent's shape errors on 2026 games.** All but the last were measured on
  caches that include vintage eval-window games (dated from 2026-08-01):
  - the tie atom (section 4, the 2,200-game cache of 2026-09-11);
  - team-runs var/mean and its decomposition (11a, all 1,766 cached games, 2026-08-09);
  - the one-run band (11a, the 1,775-game cache priced from the served context) and the
    side asymmetry (11a's held-out half, from 2026-06-27);
  - the total's shape (7f, the 305 fit-half games only).
- **Eval-half observed Over rates.** The 7g run printed them for every split (disclosed
  in 7h), and the 7g and 7h results quote some of them.
- **Pre-2026 descriptives of the fit data,** from G4-07
  (`scratchpad/fg-audit-2026-09-09/ideas/G4_betting_accuracy.md`, via lane R5), all read
  off `.cache/pbp_corpus`, which holds 1,448,967 plays over 17,008 pre-2026 games (plan
  4.2, N1):
  - home win rate by season: 2018 0.5278, 2019 0.5294, 2021 0.5385, 2022 0.5329, 2023
    0.5210, 2024 0.5216, 2025 0.5428;
  - per-side runs var/mean by season: 2.291, 2.285, 2.238, 2.258, 2.245, 2.168, 2.370 for
    2018, 2019 and 2021 to 2025 (2020 is not in the corpus);
  - extra-inning share 0.083 to 0.089, extra-inning home rate 0.472 to 0.542 on 201 to
    216 games a season, and P(|margin| = 1) 0.266 to 0.294, each a range with no season
    named.
- **One 2026 descriptive, listed apart:** per-side runs var/mean 2.340 (G4-07).
- **Who saw what.** The draft of this section cited only lane R5's ranges (per-side
  var/mean 2.168 in 2024 to 2.370 in 2025, home rates 0.5210 to 0.5428), and it fixed the
  season window below. Whether its author opened G4-07's per-season lists is not recorded.
  The author of this revision read them after the window was fixed, and the window did
  not change.

No reference table has been built. No tilt has been solved, and no kernel probability
has been computed for any game. For this section and its two reviews, code was read to
name functions and nothing was run: `betting_model.py`, `betting_export.py`,
`betting_shadow.py`, `dfs_export.py`, `tools/build_pbp_corpus.py` and
`tools/betting_calibration.py`. The knowledge above can steer two things: the choice to
try a joint table of final scores at all, and the season window, which is argued below
from the rule calendar. It sets no parameter. The kernel has no parameter fitted on 2026,
and its criteria are the ones 11a, 7g and 7h already use.

**Why one distribution.** The served model prices the two sides as independent
Poissons and prices every market off that product. The product is wrong in three
measured places:
- **The tie atom** is 0.1352 at the league run environment, against an observed extras
  rate of 0.0877 (section 4; 193 of 2,200 games).
- **The one-run band.** P(|margin| = 1) is 0.2503 under Poisson against 0.2721
  observed. NB2 moved it to 0.1917, the wrong way (11a).
- **The total's shape.** var/mean is 2.347 on the fit half, where a Poisson has 1 (7f).
  Team runs sit at var/mean 2.3385, and 93.75% of that excess is within-game clumping,
  not lambda spread (11a).

**The walk-off is what no product of two independent sides can carry (11a).** Of 193
extra-inning games, the home side won 93 and won by two or more in 10. The away side
won 100 and won by two or more in 51 (section 4). On 11a's held-out half, home -1.5
landed 0.3442 against away -1.5 at 0.3768.

**Every repair so far kept the independent product** and fitted one or two parameters
on 2026 games:
- NB2 fixed the margin tail and damaged the band (11a).
- The tie split reassigns one atom that the Poisson overstates (section 4).
- 7f fixed the low end of the total grid and broke the high end. 7g and 7h fixed the
  tails and missed the middle of the anchored window.

The reference below, a table of real final scores, carries all of it at league scoring:
no ties, the clipped home winning margin, the band, the tail and the skew. Whether the
tilted kernel keeps it at a game's own lambdas is what the gate reads. Three markets read
off one table cannot disagree about one game, which is the property `_score_joint` and
`split_tie_atom` were built to protect. These facts are motivation only. None of them is
a criterion, and none of them sets a number below.

### The fit data: pre-2026 finals only

The reference table n(h, a) counts the games that ended with the home side on h runs and
the away side on a runs.
- **Source.** For each season Y, one call `fetch_finals(f"{Y}-03-01", f"{Y}-11-30")`:
  one StatsAPI schedule request (`gameType=R`, hydrate `linescore`) and no Odds API
  credit. `fetch_finals` is the schedule door of `build_game_cache`, and both doors write
  the same row: `home_runs` and `away_runs` off the linescore, `innings` (the linescore's
  `currentInning`) and `season`. Where the linescore carries no runs, `_row_from_schedule`
  falls back to `teams.score`; the builder counts those rows (to be built).
- **Seasons 2023, 2024 and 2025.** The 2023 rule package (the pitch clock, limits on
  defensive shifts, larger bases) is the last change to the rules under which runs are
  scored, and 2026 plays under it. So these are the pre-2026 seasons whose scoring
  process 2026 shares. That is a run-environment reason, not a game-ending one. The rules
  for how a game ends do not separate 2022: the automatic runner decided extra innings
  from 2020 (2023 made it permanent), and nine-inning doubleheaders returned in 2022.
  That is why the sensitivity arm is 2022 to 2025. It differs from the main arm only by
  the season before the package. No per-season number chose the window (see "Who saw
  what").
- **Dropped and counted:**
  - a row whose `season` is not Y (the range trap `_topup_game_cache` documents);
  - a repeated `game_pk`, kept once (the later-dated row);
  - a row with no inning count or fewer than 9 innings (a shortened game);
  - a row whose final is level (no final can be, so it is a source defect).
- **Nothing else.** No smoothing, no pseudo-count, no prior and no season weight. A
  final score never seen in those three seasons has zero mass in every kernel.
- **Completeness floors (POLICY, fixed now).** At least 2,420 distinct finals returned
  per season, and at least 2,350 kept after the drops. The corpus census is 2,429 to
  2,430 games per season for 2022 to 2025 (09-05 plan B-CORPUS; G4-07). Below either
  floor the build refuses.
- **Cross-check.** For each `game_pk` that is also in `.cache/pbp_corpus`, the fetched
  final is compared with the corpus's: the post-play `home_score` and `away_score` on
  the game's last play. Disagreements are counted and listed. More than 12 in any season
  (0.5% of 2,430, POLICY) refuses the build. Otherwise the table is built from the
  `fetch_finals` rows.
- **A refused build** may be re-fetched. The floors, the cap and the rules do not
  change. If it still refuses on 2026-10-06, 7i closes without a verdict and the text
  records why.
- **Frozen.** The table is written once, after this section is committed, to
  `.cache/betting/score_kernel_reference.json` (to be built), outside the published
  `data/` tree until the look. It carries the per-season counts, the drops, the
  cross-check and a SHA-256 of the table. The hash is pinned as
  `SCORE_KERNEL_REFERENCE_SHA256` (to be built) in a constant-only commit, and the gate
  refuses a file whose hash differs.
- **No shape before the look.** The build prints the counts, the drops, the cross-check
  and the hash, and no shape statistic. The table's shape is first computed in the
  result block.
- **Never rebuilt.** No nightly, monthly or `--context` path rebuilds it. 2026 finals
  never enter it. A reference with 2026 in it is a different candidate, with its own
  section and a 2027 look.

### The candidate

For each game the pricer returns `lam_home` and `lam_away`: the pair `expected_runs`
returns after `home_adj`, `diff_shrink` and the [1.5, 9.5] clamp. The kernel is the
reference tilted to those two means:

    K(h, a) = n(h, a) * exp(t_h * h + t_a * a) / Z(t_h, t_a)

Here (t_h, t_a) is the unique solution of E_K[h] = lam_home and E_K[a] = lam_away, which
exists for any pair of means inside the convex hull of the table's support. That makes K
the distribution nearest the reference in relative entropy that has the game's two
means, so the kernel has no free parameter. It is solved by damped Newton from (0, 0) to
a mean error below 1e-9. The solution is fixed by the two equations, not by the solver.
A tilt that does not converge at the look raises, and that split cannot pass. There is
no fallback.

Every market is read from K alone:
- **Moneyline:** p_home is the mass on h > a. K has no mass on h = a, so there is no tie
  atom, no `tie_home` and no runline split.
- **Runline:** P(home margin >= 2) and P(home margin <= -2), read through
  `split_tie_atom` with a zero atom. `split_tie_atom` still takes a `tie_home`. With a
  zero atom any value in [0, 1] is inert, and the lab passes 0.5.
  `p_home_minus_1_5 <= p_home` holds by construction.
- **Total:** P(h + a = k). The Over, the Under and the push come from
  `total_side_probabilities`.

**What is not known until the look.** A joint tilt is not a tilt of each side. The
kernel's home marginal is proportional to exp(t_h * h) * n_h(h) * E_ref[exp(t_a * a) |
h]. The last factor varies with h, because the two sides are dependent in the reference
(the empty diagonal, the walk-off clip). So the kernel's marginal dispersion at a game's
lambdas is not the reference's, and it is unknown until the look.

**The total moves with two 2026-fitted parameters.** Under the Poisson the total depends
only on lam_home + lam_away, so `diff_shrink` and `home_adj` leave it alone (the
`expected_runs` docstring). Under the kernel the total's pmf depends on each lambda. So
the kernel arm's total moves with two moneyline parameters fitted on the 2026 fit half,
though its mean does not. Neither is fitted to the total, which is why plan X1 (no
fourth one-parameter total repair on the 305-game fit half) does not bind.

**Structural, asserted by test (to be built), never measured:**
- **On synthetic tables:** every kernel sums to 1 within 1e-12, has zero mass on h = a,
  and hits both means within 1e-9 on a lambda grid over [1.5, 9.5] squared. The margin
  and the total come from the same table.
- **On the frozen references (main and sensitivity), once built:** the tilt converges
  and hits both means within 1e-9 at every point of the [1.5, 9.5] squared grid at step
  0.25 (1,089 points, POLICY). The test reads no game and no outcome, and prints no
  probability. A failure may be repaired before the look by a better solver, because
  the solution is fixed by the equations. The result block names the repair.
- **The hash** of each reference matches the pinned one.
- **No served module** imports the kernel until a flip.

**A known bias, stated before the look.** The reference's spread includes the
between-game spread in true scoring rate, and the tilt moves the mean without removing
that spread. So the part of it the pricer's own lambdas already explain is counted
twice. On the served lambdas 11a measured that part at 0.3755 of 6.0036 runs squared of
excess variance (6.25%). The vintage pricer's win probabilities spread less than the
served ones: 2.7% of graded games sit outside 0.4 to 0.6, against 25.3% served (plan
4.2). That is a proxy for a narrower lambda spread, so less should be counted twice on
the graded lambdas than 11a's figure. The bias is not repaired, because a repair needs a
parameter fitted somewhere, and the gate is where the bias shows.

### The incumbent, frozen here by construction

The lab reads no serving flag and no context key. It passes every choice below
explicitly, so no flip before the run, including one that follows the 7h re-read, can
change what the kernel must beat. "Held False" means the gate holds the module constant
for the run and restores it afterwards (to be built). On each split's fit half the
incumbent is refit the way every lab in 7e to 7h refits it:

| Piece | Frozen as | Through |
|---|---|---|
| coefficients | OLS; `SERVE_RIDGE_FIT` has no path in | `fit_coefficients` |
| tie rate | the fit half's extra-inning home rate, shrunk | `_fit_tie_home` |
| runline | the tie split at every split, whatever `SERVE_RUNLINE_TIE_SPLIT` reads | `_fit_runline_tie_split`, `split_tie_atom` |
| margin | Poisson (`run_alpha` None); shrink and home level re-solved | `_solve_diff_shrink`, `_solve_home_adj`, `_p_home_series`, `game_probabilities`, `_score_joint` |
| total | the Poisson total: no 7f level, no 7g alpha_T, no 7h map, whatever `SERVE_TOTAL_LEVEL`, `SERVE_TOTAL_DISPERSION` and `SERVE_TOTAL_CALIBRATION` read | `_total_pmf` (alpha None), `_pmf_over`, `total_side_probabilities` |
| moneyline response | no Platt map; `SERVE_PROB_CALIBRATION` has no path in | none |
| the Athletics' park | `SERVE_ATH_PARK` held False: the park is neutral at every split, in both arms | `parks_from_vintage` |
| the cut | `VINTAGE_FIT_WINDOW_GROWS` held False: the anchored cut | `_vintage_cut_index` |
| the pricer | the vintage pricer, refit per split; the O14 response does not reach the lab | `_vintage_resolver`, `inputs_as_of`, `leaderboard_vintages.as_of` |

Why these values:
- **The tie split.** The owner answered "reprice now" on 2026-09-11. So the kernel must
  beat the repriced runline, and it cannot win on the atom that answer already moved.
- **The Poisson total.** It serves at HEAD, with its Over lean disclosed (7f; owner
  answer 2026-09-11). If `SERVE_TOTAL_CALIBRATION` has been flipped before the run, the
  result also reports, never as a criterion, the kernel's grid delta against the 7h map
  refit per split (`fit_total_calibration`).
- **The park.** The owner answered that it serves. But it reaches both arms through the
  same lambdas, and a record older than schema 5 keeps the club neutral whatever the flag
  reads (`parks_from_vintage`). Holding it False keeps the fit halves those of the 7f to
  7h runs, and matches the 7h re-read's freeze.
- **The cut.** It is 2026-08-01 with 305 fit games on the record (7f to 7h).

**A tie split that returns None.** `_fit_runline_tie_split` returns None when a fit half
has no extra-inning win on one side. The incumbent would then fall back to the whole
atom, which the owner's answer retired. A split where that happens cannot pass, and it is
recorded.

**Not stacked on anything.** The challenger is the kernel alone. In the lab and in
serving, it is never composed with any of these:
- the 7f level;
- the 7g alpha_T;
- the 7h survival map;
- the 11a run alpha;
- the 11b Platt map;
- the tie split.

`SERVE_SCORE_KERNEL` may not be True while any of `SERVE_RUN_DISPERSION`,
`SERVE_TOTAL_LEVEL`, `SERVE_TOTAL_DISPERSION`, `SERVE_TOTAL_CALIBRATION` or
`SERVE_PROB_CALIBRATION` is True. The flip commit's test pins that.
`SERVE_RUNLINE_TIE_SPLIT` is left out of that list on purpose: under the kernel the atom
is zero, so the split is inert, and after the owner's reprice the flag reads True.

**Re-solving, per arm.** The two arms share the coefficient fit, because OLS on runs
reads no distribution. Each arm re-solves `diff_shrink` and `home_adj` on its own fit
half, under its own distribution. That is 11a's rule and B-RUNLINE's third constraint.
Under NB2 the shrink moved from 0.70 to 1.08 (11a), and holding the Poisson's values
would grade a tuned incumbent against an untuned challenger. Today `_solve_diff_shrink`
and `_solve_home_adj` thread only `run_alpha`, through `_p_home_series` into
`game_probabilities`. The kernel arm needs a kernel-threaded path through both (to be
built). The kernel itself carries no parameter fitted on 2026, so it is not a fourth
one-parameter repair on the 305-game fit half (plan X1).

### The eval window, the criteria and the verdicts

**The window.** Every 2026 regular-season game dated on or before 2026-09-27 that is
final in the game cache after a top-up on the read day. The top-up is
`build_game_cache(refresh=True)`, run after the last game dated 2026-09-27 is final.
- **Pricing.** Each game is priced on a dated vintage through `_vintage_resolver`. A
  game with no vintage strictly before it is skipped and counted, and never graded on
  the fallback (section 6).
- **Excluded.** A game dated after 2026-09-27 (a makeup) is outside the window.
  Postseason games cannot enter, because both doors of `build_game_cache` keep
  regular-season games only.
- **Shortened games stay in.** The reference and the eval read one row definition but
  not one scope: the reference drops games of fewer than 9 innings, and the eval grades
  every final. A shortened game counts against whichever arm misprices it, and the
  result reports how many there are. They are not dropped, because dropping them would
  condition the eval on a post-game fact and remove the games a 9-inning table fits
  worst.
- **The splits** are the 7f/7g/7h grid: the anchored cut plus date quantiles 0.6, 0.7
  and 0.8 of the gradable dates. Each fit half refits the pricer and each eval half
  grades.
- **The fit half is never graded.** Every eval half lies on or after the anchored cut,
  so no game in the 305-game anchored fit half is graded at any split.

**Criteria.** All are required, at ALL FOUR splits.
- **Floors.** A split below `VINTAGE_MIN_FIT_GAMES` (100) or `VINTAGE_MIN_EVAL_GAMES`
  (50) cannot pass.
- **Sign.** delta is incumbent loss minus kernel loss per game, through
  `_paired_delta`, so a positive delta means the kernel is better.
- **Source.** The rows are 11a's four criteria, with its total row (over 9.0) replaced
  by the 7g/7h grid.

| # | Market | Paired per-game loss | Test on each eval half |
|---|---|---|---|
| 1 | moneyline (home win) | Brier | non-inferiority: one-sided 95% lower bound on delta >= -0.001 (11a; B-RUNLINE's second constraint). At the anchored split, `beats_baseline_95` from `_paired_brier_skill` against the home constant may not read True for the incumbent and False for the kernel |
| 2 | runline, both sides | per-game sum of the log loss on home margin >= 2 and on home margin <= -2 (`RUNLINE_SIDE_AMENDMENT = "both"`) | delta > 0 at one-sided t >= 1.645 |
| 3a | total, grid | log loss of the Over summed over `TOTAL_LEVEL_LINES` (7.5, 8.5, 9.5, 10.5) | delta > 0 at one-sided t >= 1.645 |
| 3b | total, per line | log loss at each grid line | not worse on the point estimate at >= 3 of 4 lines |
| 4 | runs, both sides | log-likelihood per scoring-side row of the observed final runs, the kernel's marginal against the Poisson side, top-coded as below | kernel > incumbent on the point estimate |

**The top-code (POLICY).** Criterion 4 pools 15 or more runs into one cell, in both
arms. If the reference's home or away marginal is empty at some r below 15, the top-code
for both arms becomes the smallest such r. That is fixed on the reference alone, before
the look, and recorded. So no observed score can land in a zero cell.

**A mixed grid ships nothing, and neither does one market.** One table prices all three
markets. Serving it on the runline while the Poisson prices the total would price one
game from two distributions, the incoherence `split_tie_atom` was built to remove.
Per-market readings are persisted and reported.

**Controls.**
- **The mirrored twin, required.** Transpose the reference, n'(h, a) = n(a, h), then run
  the same tilt and the same re-solves. The tilt restores each game's two means, so the
  twin differs from the candidate only in which side carries the home-side structure:
  the walk-off clip and the unplayed bottom of the ninth. At every split, the
  candidate's criterion 2 delta must exceed the twin's on the point estimate. A kernel
  that cannot beat its own mirror on the runline is not pricing the structure this
  section is about.
- **The sensitivity arm, reported and never qualifying.** The same construction, on a
  reference built from 2022 to 2025 finals under the same rules, floors and cap, and
  pinned the same way.
- **No seeds.** Every step is deterministic, with no bootstrap and no permutation. There
  is no column to permute, so 5c rule 3's permuted twin has nothing to act on.
- **No contaminated leg.** 5c rule 4's contaminated screen is for dark columns. Like 7f
  to 7h, this candidate has no column.

**Verdicts.**
- **PASS:** every criterion at every split, the twin beaten at every split, and no split
  refused (a floor, a tilt that does not converge, or a tie split that returns None).
- **FAIL:** the twin not beaten at some split, or no split passing every criterion.
- **INDETERMINATE:** anything else.

Nothing ships on FAIL or INDETERMINATE, and no re-read follows either.

### Holm, and the five attempts at the total

N2 is a family of one.
- **Families it is not in:**
  - the 7e coefficient family, because it fits no coefficient;
  - the 5k, 5d-C and 5h run-environment family, because it moves no location and reads
    no weather, venue, date or dark column;
  - N6, and the N4 grid.
- **Within this section.** Requiring every criterion at every split can only lower the
  false-pass rate below each test's one-sided 0.05, so no correction applies.

**Across the total, disclosed and not corrected.** This is the fifth featureless repair
of the 2026 total on overlapping eval games: 7f, 7g, 7h, the 7h re-read and 7i. It comes
after 11a's joint NB2, whose total row (over 9.0) passed at all three splits in
contaminated mode and did not ship. The run-environment family (5d-C, 5h, 5k) is
separate. No family-wise correction spans the five, and joining them now would amend
7h, whose text fixes its criteria. What 7i fixes for itself, now:
- **The tie-break.** If the 7h re-read and 7i both PASS, the pre-registered
  recommendation is the kernel, because one table prices all three markets and the map
  prices the total alone. The two never price the total together (the tripwire above).
  The flip stays the owner's call. A flip of the map over a passing kernel is recorded in
  its flip commit as a departure from this rule.
- **The label.** The flip commit, and any page copy that cites a PASS, call it the fifth
  featureless total repair on overlapping 2026 eval games.
- **A report, never a criterion:** the kernel's grid delta on eval games dated after
  2026-09-10, the only games no total run before 2026-09-28 printed.

**The pre-registered expectation, stated before any fit.**
- **Criterion 2** is the question this section exists to ask.
- **Criterion 3 is the likeliest miss.** 7g and 7h each missed the middle of the
  anchored window, pricing Over 8.5 at 0.445 and 0.448 against 0.485 observed, and the
  known bias above widens the kernel.
- **Criterion 4 leans to a pass.** The reference carries the dispersion 11a measured
  (NB2 alone bought +0.2190 nats per row on 11a's pre-registered split, in contaminated
  mode). But the kernel's marginal is not the reference's (see above), so this is a
  lean, not a property.
- **Criterion 1 should be near neutral** once `diff_shrink` re-solves.

None of this rests on a number about the kernel.

### What is reported, and what is withheld

**Reported whichever way it lands.**
- **The references (main and sensitivity):**
  - per-season counts and drops, the fallback rows and repeated `game_pk` included;
  - the corpus cross-check;
  - the hash and the top-code;
  - the shape, computed here first: mean runs per side, var/mean per side and for the
    total, P(|margin| = 1) and P(|margin| >= 5).
- **Per split:**
  - n_fit, n_eval and the skipped count;
  - each arm's `diff_shrink` and `home_adj`;
  - the incumbent's `tie_home` and runline split (or None);
  - every criterion's delta, sd, t and lb95;
  - the twin's criterion 2 delta.
- **Per eval half,** each for the kernel, the incumbent and the observed games:
  - P(|margin| = 1), which is B-RUNLINE's fourth constraint, against the 0.2721 on the
    record;
  - P(|margin| >= 2) and P(|margin| >= 5);
  - the home -1.5 and away -1.5 landing rates, the walk-off diagnostic (11a read 0.3442
    and 0.3768);
  - the Over rate at each grid line, unless withheld (below).
- **The tilt:** the largest mean error, and the count of games at the lambda clamp.
- **The sensitivity arm's** full grid beside the candidate's.
- **Report-only:**
  - the grid delta on games dated after 2026-09-10;
  - the grid delta against the 7h map, if it was flipped before the run;
  - the count of shortened eval games.
- **Market diagnostics, never criteria:**
  - model P(over) at the posted line minus the realised rate, on eval games with a
    cached open capture, unless withheld (below);
  - the Over/Under split of positive-edge totals on every cached slate.
- **The look record:** none, or each look and its consequence; the readiness counts.
- **Configuration:** the worktree commit and the commits named under "Code", the main
  tree's HEAD, `MODEL_VERSION`, the values the gate held, and the python and numpy
  versions.

**Withheld until the run-environment reads.** If the 5k registration and the amendments
that put 5d-C and 5h in one Holm family with 5k are not all committed before this run,
the result block withholds two things until those reads land, and records the rest:
- the per-line Over rates (kernel, incumbent and observed) on every eval half;
- the posted-line diagnostic.

Those numbers describe the late-season residual that 5k, 5d-C and 5h target. 7h's
late-window reading (Over 7.5 observed 0.615 after 2026-08-29) is a location question,
and it belongs to them. Between this run and theirs, no amendment to 5d-C, 5h or 5k is
written unless it names this printout.

### The look

**What counts as a look, and what one costs.**
- **A look** is any computation, by any path, before the scheduled run, of the kernel,
  the twin or the sensitivity arm at any game's lambdas: 2026 or pre-2026, N1's
  reconstructed inputs included. The path does not matter, because an off-lab look is
  easy: the board publishes `lam_home` and `lam_away` on every priced game
  (`betting_export.py`), every 2026 result is public, and the reference sits on this
  box. Development tests use synthetic tables and synthetic games only.
- **A run of the switch before 2026-09-28** is a look too. A guard (to be built) refuses
  one.
- **The cost.** Any look is recorded here with its date and whatever it printed, and it
  FORFEITS 7i: the scheduled run does not happen, 7i closes, and no PASS can come from
  it.
- **Not looks:** building a reference and printing its counts, drops, cross-check and
  hash; the structural tests; the readiness counts below.

**No amendment between commit and look,** except a dated correction on a fact that
involves neither a reference's shape nor any outcome (a name, a path, a pinned hash). A
cancellation needs a dated correction before the main reference is built. After that
there is none. After the look, changing the seasons, the inclusion rules, the floors,
the tilt, the top-code or any criterion makes a new candidate. It needs its own section,
and it is graded on games this look did not see.

**The read: once, on 2026-09-28.** `score_kernel_gate` (to be built; `python
betting_model.py --score-kernel`).
- **Code.** The read runs from a detached worktree of the commit that pins the reference
  hashes, with `prospect-tracker/.cache` junctioned to the main tree's (the 7h re-read's
  method). The result names that commit, and every commit since this section's that
  changed a function in the incumbent table, with the reason. None may change a
  criterion, the window, the reference rules or the incumbent's construction. A change
  that would is a new candidate.
- **Readiness,** relating nothing to an outcome. The gradable games dated on or before
  2026-09-10 must number 853 (the 305 + 548 of 7f to 7h), and the anchored cut must be
  2026-08-01 with 305 fit games. If either differs, the read does not run that day. The
  cause is found and recorded without relating anything to an outcome, and the read runs
  once the counts hold, by the kill date.
- **A slip.** If the read cannot run on 2026-09-28 (code, box, cache, feed, build or
  readiness), it runs on the first day it can, under the same window, code and rules. A
  slipped read is still the one look.
- **Kill date 2026-10-06.** If it has not run by then, 7i closes without a verdict and
  the text records why. That keeps it ahead of the 2026-10-07 reads of 5d and 5k, which
  use the same late-season totals.
- **Order against the 7h re-read.** If both run on one day, 7i runs first. Otherwise the
  result says which ran first.
- **Why that date.** It is the day after the regular season ends, so the window is the
  whole season and cannot be chosen by when the code lands. The incumbent is frozen
  above, so the landing date cannot choose that either.
- **No accrual clock** applies, because the kernel is fitted on pre-2026 data.
- **Where it lands.** The criteria ride verbatim in `SCORE_KERNEL_GATE_CRITERIA` (to be
  built). The grid persists at `data/betting_model_eval.json -> score_kernel`. The result
  is appended as `### Result (run DATE, once): VERDICT, and ...`.

#### Closure, recorded 2026-10-02: 7i closes for 2026 without a verdict

- **The look code does not exist** at main HEAD 842b5f64 on 2026-10-02: no
  `score_kernel_gate`, no `python betting_model.py --score-kernel` switch, no
  `SCORE_KERNEL_GATE_CRITERIA`, no reference table, no date guard and no fixture tests. A
  search of every `.py` file under `prospect-tracker/` for `score_kernel` finds nothing.
- **No build is scheduled before the 2026-10-06 kill date.** The writer slots of the gap
  from 2026-10-04 to the epoch's step A belong to the fWAR epoch's preconditions (plan
  Part 8, 8.C 'The gap (Sun 10-04 to step A), in order'), and nothing before 2026-10-04
  builds it.
- **So 7i closes for 2026 without a verdict**, under this section's own text: "If it has
  not run by then, 7i closes without a verdict and the text records why." It is recorded
  now, with the 7h re-read, rather than on 2026-10-06.
- **No look happened.** No reference was built, and no number relating the kernel, the
  twin or the sensitivity arm to an outcome or a price was computed, at any game's lambdas,
  2026 or pre-2026. Nothing is forfeited, and no result block is written.
- **Order against the 7h re-read.** 7h ran alone on 2026-10-02 (FAIL, recorded under 7h).
  7i did not run.
- **A later test is a new candidate.** In this section's words: "After the look, changing
  the seasons, the inclusion rules, the floors, the tilt, the top-code or any criterion
  makes a new candidate. It needs its own section, and it is graded on games this look did
  not see." With no look taken, a 2027 test of the kernel is a new registration under N9,
  graded on 2027 games, and it discloses this closure and both 7h reads.

### If it passes: the flip, and what moves

The lab lands with no serving path, because a serving path for an unmeasured candidate
is what 5c forbids (5h). On a PASS, the serving path lands behind `SERVE_SCORE_KERNEL`
(to be built), default False, and the flip is the owner's call.

The flip is one commit:
- the flag and its tripwire test;
- the main reference committed into `data/`, so every box serves the same table, with
  its hash checked against the pinned one;
- one `MODEL_VERSION` bump for all three markets. It labels the artifacts and the record
  rows (`betting_export` writes `model_version` into each record row). The calibration
  and shadow ledger rows carry no version field (`OPEN_FIELDS` in
  `tools/betting_calibration.py`; `betting_shadow.py`);
- `--context` re-run, so the kernel arm's `diff_shrink` and `home_adj` are written (keys
  to be built).

**After a flip the ledgers pool two pricers, and this says so.** 7b's statistics run on
the settled canonical games in ledger order, with no version filter (`market_gate`;
`trailing=200` takes the last 200).
- The closure test for the moneyline and the runline keeps reading rows priced by the
  Poisson product beside kernel rows. On the runline, after the owner's reprice, those
  older rows are the Poisson plus the tie split.
- The total's trailing-200 re-open test pools the two until 200 kernel-priced canonical
  games settle.
- Pooling leans against re-opening the total, because the rows it carries over are the
  ones that closed it. It leans toward keeping the moneyline and the runline open on the
  older rows.

A window scoped to `slate_date` on or after the flip is not registered here. It would be
a dated 7b amendment with its own code (to be built). It would also have to say what
happens below 100 scoped games, where `worse_than_coin_95` cannot be true and the
re-open test would pass on no evidence.

What moves:
- every moneyline, runline and total probability, edge, EV and Kelly;
- which side is value;
- both Model Watch slots, at the next nightly, whenever their best row moves (O21,
  DEFAULT: slots chosen at the nightly and locked until 5j passes).

What is re-read or checked:
- **The text that describes the Poisson:** the `tie_atom` block, `tie_atom_caveat`,
  `POISSON_CAVEAT`, section 4's atom paragraph, and section 11's runline and
  run-distribution bullets.
- **`total_level_check`** keeps running unchanged and decides for itself whether the
  lean remains.
- **`dfs_export`'s implied team totals** read `margin_distribution` and `split_tie_atom`
  directly, so the flag does not reach them. The flip commit says whether they follow.

What does not move:
- **Props.**
- **The total's ledger leg.** It has been LEDGER-CLOSED since 2026-09-03, at 0.268081 on
  171 games (plan 4.2). A pass does not reopen it. Only 7b's re-open test does, on the
  pooled window above.
- **The total's slots.** Under O15's DEFAULT (slots from publishable markets only; a
  ledger-leg-only `SLOT_MARKET_POLICY` value is to be built; **built 2026-09-17 as
  `"ledger_gated"`, registered at the end of 7d, and OFF: HEAD is still `"any"`**), the
  total stays out of the slots until its ledger leg reopens. The BADGE is not gated
  by any policy value and is measured as an unfiltered client-side surface in 7d.

**What a pass cannot claim.** The lab grades the kernel on its own refit vintage pricer,
with the Athletics' park neutral. The served kernel rides the served pricer, the park
and the board's live repairs included. No registered section grades the kernel on the
served pricer. Which pricer serves is 7e-D's question (O14, DEFAULT: if the replay
fails, serve the graded vintage pricer), and X3 stands. Criterion 1's
`beats_baseline_95` clause protects gate 2 and validates nothing.

### What 7i does not claim

- **No feature and no location term.** The level stays the pricer's. The late-window
  reading belongs to 5k.
- **Nothing about 2026's rules.** Whatever 2026 changed about how games are played is
  not in the reference. The eval is where that would show.
- **Nothing about the kernel's marginal dispersion** before the look.

### Departures from the plan and from B-RUNLINE

- **The clock.** Plan 4.2 (N2) and lane R5 say "immediate after registration", and plan
  5.2 (W4) puts N2 stage 1 in the offseason. 7i has one look, on 2026-09-28, with a kill
  date of 2026-10-06. The reason is the whole regular season as the window, on a date the
  landing day cannot move. 7i has no pre-2026 scoring stage: the kernel has no free
  parameter for such a stage to choose, and scoring it on pre-2026 games before the look
  is a look.
- **N4 is not folded in.** Plan 4.2 and R5 say N4 folds into N2 if N2 ships first. 7i
  carries no tie prior, because it has no atom, and no home prior, because each arm
  re-solves `home_adj` on the 2026 fit half. If the kernel ships, N4's tie prior has no
  object on the served path. N4's home prior stays in N4's own section, graded against
  whatever serves then.
- **Four splits, not three.** B-RUNLINE and R5 grade at 0.6, 0.7 and 0.8. 7i adds the
  anchored split, as 7f to 7h do, so its total row reads the same grid as the candidates
  it competes with. That is stricter, not looser.
- **No ledger arm.** B-RUNLINE's gate added "the ledger arm on the 141 canonical games",
  and section 4 repeats it as the condition for serving the tie split, a condition the
  owner's answer has since overtaken. 7i has none, for three reasons:
  - the ledger's probabilities are priced on season-to-date inputs, contaminated
    forward (7b's honesty note), and B-RUNLINE's own first constraint names those 2026
    rows as what the fit must avoid;
  - the ledger stores probabilities, not lambdas. A ledger arm would first invert a
    moneyline row and a total row of the same game through the construction that priced
    them. 7f inverted totals that way as a market diagnostic, never as a gate arm. The
    inversion adds an assumption the vintage window does not need;
  - the ledger's slates all date from August 2026 on (open captures from 2026-08-06,
    G4-07), inside the vintage eval window, which grades both arms on uncontaminated
    lambdas.

  The choice is fixed before the reference exists.
- **All three markets, not the runline alone.** B-RUNLINE modelled the margin only, kept
  the Poisson total, and would have shipped the runline alone. 7i prices all three markets
  from one table and ships all or none, for the coherence reason above.
- **Three seasons.** B-RUNLINE and R5 say pre-2026 finals and name no seasons. G4-07 and
  N4 use eight. 7i uses the three seasons of the current scoring rules, with 2022 to 2025
  as the sensitivity arm.

### Disqualification

Any number relating this kernel, or a close variant, to a game outcome or a market price
before this section is committed disqualifies the candidate under 5c rule 1. A close
variant is any of these:
- a reference built from any season set;
- any smoothing, pseudo-count or reweighting of a reference;
- any other map of a score table onto the pricer's lambdas;
- the twin or the sensitivity arm;
- a parametric joint score model with a walk-off or one-run term.

After the commit, the look rules above govern: any such computation before the scheduled
read is a look, and it forfeits 7i. Building a reference after the commit, printing its
counts, drops, cross-check and hash, and running the structural tests are the fit, and
they are allowed.

Committed alone, docs only, ahead of any code that implements it. No number here relates
the kernel or a close variant to a game result or a price; every quoted number was on the
record.

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

## 8a. Postseason games are priced (owner decision 2026-10-01, INT-A1)

**The decision.** On 2026-10-01 the owner answered INT-A1 with (c) "Yes,
full" (recorded in `_audit_2026-09-09/DECISIONS_FOR_OWNER.md` under "Part 8
batch 8 (rest) and batch 9 (part): links and postseason betting"), departing
from the recommended "no": /betting/ prices postseason games, and they may fill
the Pick of the Day and longshot slots and post public record rows, although
the pricer has never been fitted or graded on a postseason game. Task
BET_POSTSEASON_PRICING carries it out.

**What the model's evidence is.** Every game behind every number this module
publishes about itself is a regular-season game: the coefficient fit and the
vintage backtest read `betting_model.completed_games()`, which takes
StatsAPI gameType R only (`_row_from_schedule`), and the paper and calibration
ledgers held regular-season sides only until this date. Pricing the postseason
is an owner decision, not a finding.

**How postseason games enter: the game scope, and nothing else.**
`fantasy_export._attach_schedule` writes a second list,
`schedule.postseason_games`, from `fantasy_schedule.fetch_postseason` (gameType
F, D, L, W over the same three-day window as `games`). `games` stays
regular-season because the streamer, two-start and DFS boards read it.
`betting_export._schedule_rows` joins the two lists while
`BET_POSTSEASON_SCOPE` is True, and `slate_games` and `resolve_slate` both read
that one helper, so the board and the close job agree on which games exist.
False restores the regular-season board byte for byte. No coefficient is
refitted, no feature is added, and the pricer prices a postseason game exactly
as it prices a regular-season one: the listed probable's SEM+ when one is
announced (a postseason probable is often posted later than a regular-season
one, and an unannounced side falls back to the club's rotation, as it always
has), season-to-date team inputs, the home club's park index and home field. A
matchup still to be decided (StatsAPI lists the club as "ATL/PHI") has no
model row and is skipped, as any unknown club is.

**The labels (binding condition 1).** Every postseason card in
`team_bets`, every slot candidate and published slot, every shadow ledger row
and every public record row carries `game_type` (F, D, L or W) and
`postseason_label`, the string "never graded on a postseason game", from one
definition, `betting_settle.postseason_fields`. A card also carries `series`.
A regular-season row carries neither key, so it is byte-identical to every row
before this date, and a row with no `game_type` reads as R. The calibration
ledger's open phase gained `game_type` on postseason sides for the same reason.
The page renders the label as a tag on the game card and on a filled slot, and
the slot card adds one sentence saying the model's evidence is regular-season
only.

**The sub-ledger (binding condition 2).** `record_summary` counts the
regular-season rows in its headline (`scope: regular_season`, with
`scope_note` saying postseason rows are excluded) and tallies postseason rows
apart under `record.postseason`, with `by_game_type`. `chain_sha` is still
folded over every row, because the chain proves the whole record was appended
to. `betting_shadow.summary()` and `data/betting_subledger.json` follow the
same split: every existing block is regular-season, and `postseason` holds
the postseason paper rows by market and by game type. `n_rows_all` is the
whole ledger in each.

**No gate's frame moves.** The 5c, 5d and 5l sections and every gate in 7, 7b,
7e and 11b name regular-season frames, and this section touches none of their
clauses. Postseason rows are refused at the shaping seams so the frames stay
what they were registered as: `betting_shadow._sweep_row` refuses a postseason
paper row (gate 3, the readiness counts and the per-cell sweeps),
`tools/betting_calibration.canonical_settled_games` skips a postseason side
(the 7b market gate and the 11b ledger arm), the calibration summary counts
them only under `postseason`, and `betting_learning._price_clock` does not
count them in its arrival rate. The dark columns and the outcome joins of
5c, 5d, 5e, 5f, 5j and 5l read `completed_games()` and are untouched.

**Unchanged rules (binding condition 4).** The per-slot record guard (one row
per slate and slot, `maybe_publish_record`) and the total-lean bar
(`BAR_TOTAL_LEAN_SLOTS`) apply to postseason rows exactly as written.
`test_betting_postseason.py` pins both on postseason rows.

**Settlement.** A postseason row settles against
`betting_model.postseason_finals()`, a separate cache
(`.cache/betting/postseason_games.json`, one StatsAPI request at most every 30
minutes) that `betting_settle.load_completed` appends to the regular-season
list on the settlement path only. `completed_games()` never sees a postseason
score.

**The registry and the glossary (binding condition 3).** The
`betting_game_prob` row and the `provisional_pick` glossary entry say the
model's evidence is regular-season only and that postseason pricing is an
owner decision of 2026-10-01.

**What is not done here.** No postseason odds or bracket view (INT-A2 and
Q901-1 are their own tasks), no postseason props (the corpus is in
next-season mode and prices no prop), and no postseason grading claim of any
kind: the sub-ledger is a description of history, not evidence.

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
  **2026-09-17:** the table is now a MEASURED one, counted off the cached
  play-by-play corpus over 2022-2024 and checked once against a 2025 hold-out
  (`tools/props_slot_pa_lab.py`, `data/betting_props_slot_pa_eval.json`, flag
  `SERVE_SLOT_PA_MEASURED`, plan repair 8 and audit L17-F3). It is SPLIT HOME
  FROM AWAY, because the home club does not bat in the ninth when it leads:
  leadoff reads 4.5785 away and 4.3873 at home, the nine hole 3.5652 and
  3.3711. The rule it replaced handed nine starters 38.25 plate appearances out
  of the 37.6 a team-game carries, so every hitter Over was priced a little
  high. THIS MOVED SERVED NUMBERS, all in one direction, measured on the
  2026-09-17 board (39 hitter rows, 117 sides, every one of them down): total
  bases P(over) -0.0177 on average and -0.0335 at worst, 1+ hits -0.0124, 1+
  home runs -0.0045, and the published fair lines -0.056, -0.033 and -0.005.
  The `Exp PA` column on the page moves with them, from 4.65 to 4.5785 for an
  away leadoff man and to 4.3873 for a home one. The plan's own estimate was
  0.5 to 1.8 points on 30 of 30 rows; the home side of the split is larger than
  that range because it corrects the level and the side at once, and that gap
  against the estimate is recorded rather than smoothed. What did NOT move: no
  moneyline, runline or total, so `MODEL_VERSION` does not bump; and no props
  value bet, because that block stays unarmed. A posted lineup card still beats
  the table. What the table still does not condition on, from B-PA-DIST's own
  brief: run environment and extra innings, neither knowable before the game.
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

# /betting/ module runbook

Lane C3 of the 2026-08-04d omnibus plan. Everything the Sports Betting module
needs to be operated, argued with, and eventually validated.

Status at ship: **Diamond preview, public, model UNVALIDATED, no picks
published, no odds feed configured.** That is the honest state, not a bug, and
the page says so on every surface.

---

## 1. Files

| Path | Owns |
|---|---|
| `betting_ingest.py` | The Odds API snapshot, immutable cache, status sidecar |
| `betting_model.py` | Game probabilities, de-vig, offline fit, backtest |
| `betting_export.py` | `data/betting.json`, the preview slice, the append-only record |
| `assets/betting.js` | The six sections, the calculators, the bet tracker |
| `test_betting.py` | 74 tests; the append-only pins are the load-bearing ones |
| `test_fixtures/odds_api_mlb_sample.json` | The only odds any test ever reads |

Artifacts written:

| Path | What | Cadence |
|---|---|---|
| `data/betting.json` | Module payload | daily tail |
| `data/betting_preview.json` | Public preview slice (the gating seam) | daily tail |
| `data/betting_status.json` | Odds-feed configuration state | every ingest run |
| `data/betting_record.json` | The public pick record, APPEND ONLY | only via `append_record` |
| `data/betting_model_context.json` | Fitted coefficients + league constants | on demand |
| `data/betting_model_eval.json` | Backtest output | on demand |
| `.cache/odds/<date>-<hhmm>.json` | Raw snapshots, immutable | daily |
| `.cache/betting/completed_games.json` | Compact game results from the feed cache | on demand |

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

## 5. The backtest, and why nothing ships off it

```
python betting_model.py --backtest
```

Runs offline against `.cache/game_feeds`. Results, 2026 season:

| Test | n | Brier | flat .500 | home base | Accuracy | Total MAE |
|---|---|---|---|---|---|---|
| in-sample | 1,705 | 0.24164 | 0.25 | 0.24946 | 56.7% | 3.54 |
| forward from 2026-06-24 | 521 | 0.24327 | 0.25 | 0.24995 | 55.1% | 3.61 |

The model beats both baselines in both windows. **It is still unvalidated**,
and this is the paragraph that matters:

> The team inputs are SEASON-TO-DATE aggregates. Every game graded above
> contributed to the features used to predict it. The forward split removes
> coefficient leakage by refitting on games before the split date; it does not
> remove feature leakage, because there is no vintage-dated copy of the
> leaderboards to grade against.

So:

- `data/betting_model_eval.json` carries `validated: false`, `contaminated:
  true`, `gates_picks: false`, `min_edge: null`.
- `pick_of_the_day` is null and stays null.
- The registry row is `unvalidated` with **no** eval artifact (the registry's
  own honesty rule: an unvalidated row that points at an artifact is lying).

### What would actually validate it

1. **Vintage-dated team inputs.** Snapshot `offense_plus` / `bullpen_plus` /
   `rotation_plus` / per-starter `sem_plus` nightly, keyed by date, the way the
   board snapshots already work. Then rebuild the features as of the morning of
   each game and re-run `backtest()`. That single change removes the leakage.
2. **A measured `min_edge`.** With clean probabilities, sweep the edge
   threshold on held-out games and take the smallest threshold whose ROI
   confidence interval clears zero. Write it into the eval artifact. The export
   reads `min_edge` from there and picks unlock automatically.
3. **Then** flip the registry row to `provisional` with
   `eval_artifact: data/betting_model_eval.json`, and only to `validated` after
   a live season of published, CLV-graded picks.

Do not invent a threshold to make a pick appear. That is the single most
dishonest number this module could publish.

---

## 6. The append-only record

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

## 7. Legal rails (non-negotiable)

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

## 8. The client

Six sections, hash-routed on `#section=pick|team|props|parlays|calc|mybets`.

**Calculators and My Bets never touch the payload.** They work with no data
file, no odds feed, no account and no network. Pinned by
`test_client_calculators_do_not_depend_on_the_payload`.

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

## 9. Known limits, stated on the page

- Poisson underdisperses real run scoring. Baseball scores in clumps, so the
  true margin distribution has fatter tails than the convolution assumes.
  Runline and total probabilities sit too close to the middle; the moneyline is
  the least exposed of the three.
- Team inputs are season to date, not vintage dated. This is the blocker for
  validation, not a rounding problem.
- Hitter prop lines assume a projected batting order against a right-hander and
  a PA-by-slot table (4.65 at leadoff down to 3.85 at the nine hole). A posted
  lineup card beats this every time.
- No weather, no umpire, no travel, no injury news beyond what the leaderboards
  already absorb.
- 29 of 30 parks have a Savant runs index in `fa_meta.json`; the missing one
  resolves neutral at lookup rather than being invented.

---

## 10. If it breaks

| Symptom | Cause | Fix |
|---|---|---|
| Page says "odds feed not configured" | no `EEPHUS_ODDS_API_KEY` | section 2 |
| Page says "no slate found" | `fantasy.json` schedule is stale | run the 9d fantasy refresh |
| All 30 clubs missing from the model | org-code mismatch | every join goes through `betting_model._org`; the leaderboards carry StatsAPI codes (SD, SF, TB, KC, AZ, CWS, WSH) and park factors carry Baseball-Reference codes (SDP, SFG, TBR, KCR, ARI, CHW, WSN). Mixing them silently drops eight clubs |
| `coefficients()["source"] == "literature-priors"` | no `betting_model_context.json` | `python betting_model.py --context` on a box with `.cache/game_feeds` |
| `RecordImmutabilityError` on a build | something tried to rewrite history | do not force it. Read the message, find what changed, append a correction row |
| `FileExistsError` from the ingest | two snapshots in the same minute | wait a minute or pass an explicit `when` |

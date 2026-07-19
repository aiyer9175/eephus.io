# Prospect Valuation Methodology (Clemens 2026 recalibration)

> **Status (2026-07-05):** the diff report was reviewed and the production default
> is now `clemens_2026` (MODEL mode): the career-path engine reprices per player
> under the FanGraphs / Ben Clemens 2026 market conventions (prior-season arb basis,
> 4-step arb, 7yr control, net-7% discount, published FG cost-of-win). `prospx_current`
> remains the BASE-IDENTITY set (byte-identical to the base config; overlay no-op) and
> stays selectable for the legacy comparison. This flip applies MODEL mode, not the
> flat published table (~2x), so per-player resolution is preserved; the model<->table
> gap is reported as a diagnostic in the eval artifacts, not forced onto the board.
> Companion reports: `reports/validation.md`, `reports/sensitivity.md`,
> `reports/diff.md`. Engine: `value_framework.py`; sets: `config/valuation_sets/`.

This document has two parts, mirroring the two FanGraphs source posts: a
plain-language introduction, then the details with the sensitivity table. Only
numbers we computed are filled in; anything not yet computed is marked TODO.

---

# Part 1 - Introduction (plain language)

A prospect's value is the surplus a team captures by holding a cheap, controllable
player instead of buying the same production in free agency. Two things set that
value: how much major-league production the prospect will deliver over his team
control years, and what that production would cost on the open market.

On 2026-07-02 FanGraphs replaced its long-standing Craig Edwards (2019) valuation
framework with a new Ben Clemens methodology. Our engine's dollar anchors descend
from the Edwards lineage (though they were already empirically re-anchored to
realized 2017-2020 outcomes in our v47 pass, see `surplus-recalibration.md`). This
recalibration makes the new framework a first-class, versioned option without
disturbing the live board.

**Valuation sets.** A valuation set is a versioned config that carries both the
published tier table (surplus, control WAR, and star odds per FV and role) and the
global parameters the engine prices with (cost of a win, arbitration schedule,
discount rate, control-year convention, star definition, residence time). Two sets
ship:

- `prospx_current` (base-identity set, alias `edwards_2019`): the legacy production
  engine, byte-identical to the base config (overlay no-op), captured so the legacy
  pipeline stays reproducible. A 50 FV hitter is about $17.7M here.
- `clemens_2026` (production default since 2026-07-05): the FanGraphs 2026 framework.
  In MODEL mode (the shipped board), the engine reprices per player under the clemens
  market conventions; a 50 FV hitter model surplus is about $18.5M (55 FV ~$35.2M),
  a modest +3% whole-stock lift over `prospx_current`, NOT the flat published table.
  The published TABLE values (50 FV hitter $45.0M, pitcher $33.5M, 70 FV ~$195M -
  roughly 2x the mid tiers) remain the calibration target + the draft/star-odds
  display source, but are deliberately NOT the per-player board price.

**Two modes.** *Table mode* prices a player directly at his tier value (exact
replication of the published framework, and the fallback and display option).
*Model mode* is our career-path mixture Monte Carlo: it prices each simulated
season through a convex cost-of-a-win curve, nets salary, discounts, and averages
across outcomes. The tier table is a calibration target, not a per-player
override: model-mode tier aggregates are meant to reconcile to the table.

**Star Odds.** The new framework introduces the odds of becoming a star, defined
as two or more seasons of four or more WAR during team control. We surface the
FanGraphs published tier value (hitters run higher than pitchers, since a bullpen
outcome rarely clears four WAR) and compute our own per-player version as a
diagnostic.

---

# Part 2 - Details

## 1. Valuation sets and global parameters

`clemens_2026` parameters (from the three source posts, fetched 2026-07-03,
checksum-validated by `valuation_sets._validate_checksums`):

- **Cost of a win**, graduated by production, 2024-2026 free-agency average:
  $6.97M per WAR for 0-1 WAR seasons, $8.76M for 1-2, $13.63M for 2+. These are the
  mean of the cost-of-win post's 2024, 2025 and 2026 rows (the post publishes only
  2026-only and a 2020-2026 average; the framework states a 2024-2026 basis).
- **Arbitration**: 15 / 35 / 50 / 75 percent of the prior season's free-agency
  value for Arb 1 through Arb 4, floored at the league minimum, over a seven-season
  control window (three pre-arb plus four arb).
- **Discount**: net 7 percent, applied as the exact net-7-percent-flat branch (a
  10 percent discount rate minus 3 percent annual win-cost growth). Exactly one of
  the two is applied, never both.
- **Star definition**: two or more control seasons of four or more WAR.
- **Residence time**: 2.0 years central (1.9 to 2.5 band), used only for the
  sub-50 aggregate stock-to-flow reconciliation, never for per-player pricing.

Checksums that passed on load: 50 FV hitter $45.0M / 13.5%; 50 FV pitcher $33.5M /
7.0%; 45 FV hitter $14.5M; 45+ FV hitter $18.5M; 40 FV hitter $5.5M; 70 FV in
$150M-$200M.

## 2. Convex pricing kernel

Each simulated season's WAR is priced through a convex cost-of-a-win curve keyed to
that season's own WAR. Two modes:

- `smoothed` (production default): a C1 smoothstep ramp through the tier-center
  rates, so there is no cliff at a breakpoint.
- `bucket_step` (calibration): the faithful hard three-step per-bucket rate.

Because the curve is convex, pricing per season and aggregating last beats pricing
an averaged WAR (Jensen). The Jensen test confirms it: two path sets with identical
expected control WAR (five 1.5-WAR seasons vs half five-3.0-WAR and half all zeros)
price equally under price-the-mean, but the volatile set is worth strictly more
when priced per season per path.

## 3. Salary and discounting

Pre-arb seasons pay the league minimum. Arb seasons pay the schedule fraction of a
reference season's kernel-priced value: the current season under the legacy
`current_season` basis, or the prior season under the `clemens_2026`
`prior_season` basis, floored at the league minimum. Each season's surplus is
discounted once by a single net real factor `((1 + growth) / (1 + discount))` per
year from projected debut. There is no second inflation or discount anywhere on
the path (the `present_value` helper is intentionally never called; a test guards
this).

**Super-two.** The engine blends a second service path for the roughly 22 percent
of the two-to-three-year service class that reaches arbitration a year early: one
league-minimum pre-arb season converts into an extra early arbitration season
(more career salary, less surplus than the standard path). The fraction paid in
that extra year is the configured `super_two_first_fraction` clamped to the
schedule's own Arb 1 step (`value_framework._arb_ladder`), so the ladder is
monotone by construction: an earlier arbitration year can never be priced above
the year that follows it. Under the legacy 0.40/0.60/0.80 schedule the calibrated
0.25 sits below Arb 1 and passes through unchanged; under the `clemens_2026`
0.15/0.35/0.50/0.75 schedule it clamps to the 0.15 Arb 1 fraction, which is the
natural reading of that year under the Clemens semantics (a super-two's first
arbitration year is an Arb 1 hearing held a year early). Recalibrated 2026-07-16:
before the clamp, the legacy 0.25 was prepended unchanged onto the clemens
schedule, producing the non-monotone ladder [0.25, 0.15, 0.35, 0.50, 0.75] (a
super-two priced as earning more in his first arbitration year than his second),
overstating super-two salaries and slightly understating surplus. The clamp is a
consistency correction to the configured value, not a new empirical estimate of
super-two award levels.

## 4. Star Odds

Computed analytically from the same mixture the surplus uses: for each outcome
bucket, each control season's WAR is modeled as Gamma(mean = the bucket's
per-season level, cv = the bucket's within-bucket coefficient of variation); the
per-season exceedance probabilities feed a Poisson-binomial for the probability of
two or more qualifying seasons; buckets are weighted by P(bucket | FV) and, for
pitchers, blended across the starter and bullpen-capped reliever paths. The result
is monotone in FV within a role (enforced by isotonic shrinkage for the published
curve) and lower for pitchers than hitters.

The displayed Star Odds are the FanGraphs published tier values (table mode). Our
model version is a diagnostic. Under the current v47 realized (bust-heavy) WAR
anchors the model runs below the published tiers, so the tier calibration shows a
large deviation: max absolute deviation about 0.55 (hitter) and 0.64 (pitcher). See
`data/star_odds_eval.json`. Reconciling the model to the table is the open Phase 5
calibration item.

An xFV training-label view (player, debut class, control seasons, star boolean) is
built from real realized MLB WAR (`data/star_label_view.json`): 2,491 debuted
players, of whom about 108 have two or more career seasons of four or more WAR (96
inside the seven-season control window). The positive class is small; it is a label
source, not yet a trained model. No outcomes are synthesized.

## 5. Validation, totals and organization rollup

Universe: 4,044 active graded prospects on the 2026-07-04 metric snapshot. This is
our graded stock, not the FanGraphs Board, so totals need not match the published
aggregates. Coverage caveats are printed in every report.

- Whole-minors totals: `prospx_current` model $9.68B; `clemens_2026` table $17.42B
  (raw stock).
- Residence-time reconciliation: our raw sub-50 table stock is $12.58B versus the
  published $6.3B sub-50 pool. Scaling by 1 / residence (2.0y) gives $6.29B, in line
  with the published pool (the exact FanGraphs conversion is not fully published).
  The 50+ stock is $4.83B (published $5.7B). The residence-reconciled whole-minors
  total is $11.13B, inside the published $10.5B-$13.75B band.
- Organization rollup and a depth-versus-stars stat (the sub-50 share of each org's
  value) are in `reports/validation.md`. TODO: reconcile the top-org magnitude
  against the published ~$671M once org membership is aligned to the Board.

## 6. Sensitivity

Our totals are on a different scale than the FanGraphs $12B (different universe, no
residence flow, ~98% sub-50), so compare direction and relative size, not absolute
dollars.

| perturbation | our move ($M) | published (~$M) |
| --- | --- | --- |
| discount +3pt / -3pt | -355 / +430 | ~700 |
| win cost +10% / -10% | +671 / -620 | not published |
| arb +30% / -30% | -542 / +574 | ~400 |
| residence -0.5yr / +0.5yr (flow) | +2097 / -1258 | ~600 |
| flat vs graduated kernel | +2879 (raises) | lowers to $10.5B |

Discount, win-cost and arb moves match the published direction and order of
magnitude. The residence and flat-kernel figures differ in size, and the flat
kernel even flips sign, because our stock is about 98 percent sub-50: flattening
lifts the many sub-1-WAR seasons to the higher flat rate rather than stripping the
2+ WAR premium from Top-100 prospects. This is a universe-composition effect, not a
disagreement with the published mechanism. Details in `reports/sensitivity.md`.

## 7. Diff: prospx_current vs clemens_2026

`reports/diff.md` gives per-tier surplus deltas, the top 25 player movers, org
movers, and the sub-50 share shift. The new framework lifts the whole-stock total
and shifts value toward deeper systems. This is the report to review before flipping
the production default.

## 8. Draft pick surplus

Implied pick surplus = the `clemens_2026` tier value for the drafted player's FV and
role minus the pick's cost, using real ingested bonus and slot data. The cost is the
actual signing bonus when known, otherwise the expected slot value; unsigned and
over-slot picks show the input, not a guess. It is computed in the static board
(`draft_export`) and the live poller, and surfaced as a labeled Draft War Room
column. The War Room chip is always discoverable in the draft section (it lands on
the "opens on draft night" state pre-draft), and a homepage banner links to it while
the live feed is active.

---

# Part 3 - Tier 2 (post-beta roadmap)

## 9. Upgrade-option layer (`upgrade_option.py`)

A prospect's grade is a call option on development. We model the grade as a
role-split absorbing Markov chain (grades 35-70 plus graduated and out, annual step),
estimated from our own dated grade history (`prospects.db` snapshots, fangraphs +
mlb_pipeline pooled to one grade per player per year), Laplace-smoothed; graduated is
a debut (`data/debuts.json`), out is inactive (`data/inactive.json`), and a
still-active player's last year is censored (no fabricated transitions). The payoff
is the `clemens_2026` table value of the grade a player graduates from.

- total = expected payoff under the full chain (grade can move)
- intrinsic = payoff under frozen-grade transitions (stay / graduate / out at the
  current grade)
- option = total - intrinsic; OPT% = option / total

Low grades are long-dated out-of-the-money calls on development: a 45 FV hitter's
OPT% is about 60 percent. High grades run low or negative OPT% because they are thin
in our data (60 FV about 221 hitter observations) and grade mobility at the top is
net-downgrade risk the frozen-at-grade intrinsic ignores. A config-prior mode
(labelled literature anchor: a 45 FV position player upgrades at roughly 20 percent)
is available as a cross-check. Report: `reports/upgrade_option.md`; eval:
`data/upgrade_option_eval.json`. Surfaced 2026-07-05 as the opt-in OPT% column on
the PROSPX active board (`#optpct`; provisional, negatives shown honestly).

## 10. Cross-source grade normalization (`grade_normalization.py`)

Each source's grade distribution is quantile-mapped onto FanGraphs FV on the OVERLAP
(players graded by both source and FanGraphs), per role per cycle -- the same
distribution-matching the FanGraphs methodology used for old Baseball America
ordinals. Mapping on the shared players separates a genuine scale bias from a
coverage difference, so a top-only outlet is not called hot for skipping the low
tiers. No scale equivalences are assumed; thin cells pool the source's overlap across
years (flagged). Raw and normalized grades sit side by side; a normalized consensus
is the mean of the FanGraphs-scale normalized per-source grades. The reference maps
to itself (identity) and recomputation is deterministic. ADOPTED 2026-07-05 as the
LIVE consensus scale: `consensus.build_timeseries` applies the remapper per source
before aggregation (gated by `ADOPT_NORMALIZED_CONSENSUS`), preserving the source
weights, single-source pull, dropped-off shrinkage and forward-fill; the per-source
published grades on the card are untouched, only the consensus scale moves. The 2026
cycle flags mlb_pipeline and espn as grading materially higher than FanGraphs on
shared players. Report: `reports/grade_normalization.md`; eval:
`data/grade_normalization_eval.json`.

## Resolved (2026-07-05 followups)

- Production default FLIPPED to `clemens_2026` (MODEL mode), keyed off a
  `_BASE_IDENTITY_SET` split so the clemens overlay actually applies on the default
  path. This changes the shared $/WAR + salary + discount conventions site-wide
  (prospects, and downstream FA / projections / trade / WAG), not just the board.
- Model<->table reconciliation is now a REPORTED diagnostic (`fit_tier_reconciliation`
  + `surplus_tier_calibration`): a single per-role WAR-anchor multiplier best-aligns
  the model aggregates to the published tiers, with the residual disclosed. It is NOT
  applied to the live board (no `war_anchor_scale` in the shipped set), so the board
  stays model-mode +3%, not the ~2x table.
- Validation report gained a residence-reconciled org rollup (top org drops from
  ~$858M raw stock toward the published ~$671M) and a FanGraphs-Board-aligned
  universe comparison (793 of 1005 ranked).
- Safety flags enabled: the mlb_trade_lookup per-season kernel (opt-out) and the
  PROSPX Star Odds column.
- Tier 2 surfaced: OPT% is an opt-in PROSPX column; the cross-source normalized
  consensus is now the live consensus scale (`ADOPT_NORMALIZED_CONSENSUS`).

## Open items

- The model<->table residual is irreducible under a single anchor scale (star odds is
  a nonlinear tail functional, surplus near-linear in WAR); reported, not forced.
- Adopting the normalized consensus adds a scale seam to the append-only history
  (metric_snapshots, farm_grade_history) at the adoption date, and eFV (which reads
  consensus_fv_raw) settles over one pipeline run.

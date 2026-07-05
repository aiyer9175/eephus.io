# Prospect Valuation Methodology (Clemens 2026 recalibration)

> **Status (2026-07-04):** Tier 1 of the recalibration is built behind versioned
> valuation sets. The production default is unchanged (`prospx_current`); the new
> FanGraphs / Ben Clemens 2026 framework ships as a selectable set (`clemens_2026`)
> for comparison and for the published Star Odds and draft pick-surplus surfaces.
> No published board number moves until the diff report is reviewed and the default
> is flipped. Companion reports: `reports/validation.md`, `reports/sensitivity.md`,
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

- `prospx_current` (default, alias `edwards_2019`): the current production engine,
  captured so the legacy pipeline stays reproducible. A 50 FV hitter is about
  $17.7M here.
- `clemens_2026`: the FanGraphs 2026 published framework. A 50 FV hitter is $45.0M
  (pitcher $33.5M); a 70 FV is about $195M. Adopting it roughly doubles published
  surplus at the mid tiers, which is why the default does not change until the diff
  is reviewed.

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

TODO (Phase 6): implied pick surplus = the `clemens_2026` tier value for the drafted
player's FV and role minus the expected or actual signing bonus, using real ingested
bonus and slot data. To be surfaced in the Draft War Room.

## Open items

- Model-mode reconciliation to the published tier table (surplus and star odds) is
  the outstanding calibration work; the deviations are reported honestly rather than
  forced.
- The production default stays `prospx_current` until the diff report is reviewed and
  the owner approves flipping to `clemens_2026`.
- TODO: top-org magnitude reconciliation and any Board-aligned universe comparison.

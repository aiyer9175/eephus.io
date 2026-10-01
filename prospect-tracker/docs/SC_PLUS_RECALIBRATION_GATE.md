# Statcast+ recalibration gate (pre-registered 2026-08-07)

Covers BOTH ships of omnibus-3 lane E, owner decision 5: shrink first, then
re-standardize. Written and committed before the adjudicating battery was read.
Producer: `tools/sc_plus_recalibration_lab.py`. Artifact:
`docs/sc-plus-2026-08-07/battery.json`.

Registry note: `statcast_plus` is `provisional` today on the forward-r analog
(`data/statcast_plus_eval.json`, r about 0.12 to 0.17). A calibration fix does
NOT promote it. The verdict stays `provisional` on both ships. If either ship
fails, its row records the null and the code stays as it is.

## 0. What is being fixed, measured first

Every number below was re-measured on the served pool
(`data/timeseries.json`, 4,586 actives, generated 2026-08-06) before any code
was written. Where the lane brief and the measurement disagree, the measurement
is what this gate uses.

| claim | brief | measured | verdict |
|---|---|---|---|
| served SC+ carriers | 3,603 | 3,603 (3,582 recomputable from payloads) | reproduces |
| served SC+ pooled sd | 6.19 | 6.192 | reproduces |
| site max is a no-volume profile | Kreiling 130, 87 pitches, no BBE, no velo | exactly that | reproduces |
| carriers with contact quality under 10 BBE | 419 | 419 | reproduces |
| composite pool sd | 0.52 hit / 0.46 pit (2026-07-29) | 0.608 hit / 0.593 pit | DRIFTED, direction holds |
| points per sigma | "about a sixth" | 6.08 hit / 5.93 pit | reproduces |

Two things the brief did not name, both measured here and both load-bearing:

**A. The served field is already a MIXTURE of two scales.** 349 of 3,603
carriers do not come from `statcast_plus.compute_statcast_plus` at all. They come
from the Savant-minors AAA re-source override at `storage.py:10935-10958`, which
calls `arkmetric_forward_eval.sc_analog_index` and stamps `100 + 10*mean(z)` over
FOUR components. Those rows carry sd 7.08 against the game-feed rows' 6.08. So a
served SC+ 115 means a different thing depending on a code path the reader cannot
see. Both paths must move in the same commit, which is why the brief named the
analog, and the measurement says the coupling is tighter than "stay on one scale".

**B. The compression is not one number, it is FIVE.** The composite is an
equal-weight mean of k correlated unit-z legs, and its spread falls as k rises.
Measured points per sigma by contributing-leg class on the shipped pool:

| side | legs | n | pts per sigma |
|---|---|---|---|
| hit | zone only (3) | 810 | 6.6 |
| hit | full (6) | 845 | 5.4 |
| pit | zone only (2) | 1,050 | 6.5 |
| pit | zone + velo (3) | 4 | 4.8 |
| pit | full (5) | 872 | 5.1 |

A partial-data player is on a scale 22 percent wider than a full-data player, so
the top of the board is selected for MISSING DATA, not for talent. The EB shrink
alone makes this WORSE (it drops sub-floor legs, so more players fall into the
wide classes: hit 3-leg goes 6.6 to 7.5 pts/sigma while hit 6-leg goes 5.4 to
5.2, a 1.45x ratio). This is the mechanism behind the owner's complaint, and it
is not fixed by the per-side divisor the brief specifies.

Therefore the second ship is registered as TWO candidates, and the gate picks
between them on measurement:

- **S2**, the brief's version: divide the composite z by ONE per-side sd.
- **S3**: divide by the sd of the player's own contributing-leg class, falling
  back to the per-side sd for any class under 50 members.

S3 is NOT a composite reweight (the banned experiment). The legs keep equal
weight; only the divisor that converts their mean into "10 points per sigma"
stops pretending every player has the same coverage.

## 1. Ship 1: EB shrink and volume floors

The reverted 2026-07-29 C1 build, recorded at
`docs/efv-2026-07-29/GATED_CANDIDATES.md:14-44`. Not re-derived.

- `(n*value + K*prior)/(n+K)`, prior = the component's raw pool mean.
- Contact quality: floor 10 batted balls, K=50. Zone: floor 25 pitches, K=100.
  Velocity: floor 10 pitches of the top pitch type, K=50.
- A leg whose sample is below its floor is DROPPED, not shrunk to the prior.
- Pool hygiene, same block: the column set comes from the union of all rows
  rather than `rows[0].keys()`, and the degenerate-column guard becomes a
  relative near-zero test instead of `sd > 0`.
- The pool mean and sd are recomputed on the SHRUNK column. Taking the divisor
  from the unshrunk pool while the numerator is shrunk is the measured aStuff+
  defect (`GATED_CANDIDATES.md` C3, 7.16 points per sigma against an advertised
  10). It is the same bug in the same shape and it is not being re-shipped here.

### Ship criteria (all must hold)

1. **S1.1** No row in the served top 10 has a CONTRIBUTING leg built on a
   sample below that leg's floor. Stated on contributing legs, not on the row:
   a player with 2 batted balls whose contact legs were dropped and whose zone
   legs rest on 500 pitches is a legitimate top-10 row, and the original phrasing
   ("no player with under 10 BBE") would have failed him wrongly.
2. **S1.2** Harrison Kreiling (87 pitches, zero batted balls, zero velo) is no
   longer the site maximum.
3. **S1.3** Carriers lost to the floors are under 2 percent of the shipped
   3,582. A correctness fix that blanks the metric for a large population is a
   different change and needs its own decision.
4. **S1.4** Spearman(S0, S1) on the common set is in [0.85, 0.98]. Above 0.98
   means the fix did nothing and there was no defect to fix; below 0.85 means it
   is not a repair, it is a new metric.
5. **S1.5** The eFV tilt factor stays inside its shipped +/-18 percent clamp for
   every carrier, and the count of clamped rows does not rise.
6. **S1.6** Suite green (run by the orchestrator, serially).

### Zero-information control

Re-run the shrink with the volume fields ROW-PERMUTED across players (identical
marginal distribution of sample sizes, no association with the player). If the
permuted shrink relocates the top 10 as much as the real one does, the shrink is
reordering on noise rather than on volume, and ship 1 FAILS. Registered
threshold: the real shrink must displace strictly more of the shipped top 10
than the permuted shrink does, on the median of 20 permutations.

### Committed loss

If S1.1 or the control fails, `statcast_plus.py` is left as shipped, this
document records the null, `model_registry.json` gains the dated failed-gate
note, and ship 2 does not run (there is no point re-standardizing a composite
whose top is still noise).

## 2. Ship 2: true 10 per sigma, atomic with every consumer

Adjudicated between S2 and S3 by criterion **S2.1** below. Losing candidate is
recorded as a measured no-ship in this file.

### Ship criteria (all must hold)

1. **S2.1 (the adjudicator)** Served sd within [9.5, 10.5] for EVERY coverage
   class with n >= 50, on both sides. A candidate that hits 10.0 pooled while
   individual classes sit outside the band has not fixed the scale, it has
   averaged over the defect. This is the criterion S2 is expected to fail.
2. **S2.2** Every row in the served top 10 clears S1.1, and the site maximum is
   in [125, 150]. Below 125 is still compressed; above 150 means a coverage class
   with too few members got its own divisor.
3. **S2.3 POPULATIONS PRESERVED.** Each shipped threshold is mapped through the
   transform, not left at its number. After remapping, the population on each
   side of every gate is within +/-2 rows, or within 5 percent for gates holding
   more than 40 rows, of its post-ship-1 population. Gates in scope: eta
   130/115/85 (`eta.py:544-549`), breakout 115 and 130 (`storage.py:637,643`),
   quintiles 110/90 (`statcast_plus.py:53-54`), spotlight 130/120/115/105/95,
   prospx filter chips 120/105/95, prospx pill colors, GFX tile 105/95.
   Explicitly registered: the shipped numeric thresholds are NOT preserved and
   the copy that quotes them moves with them.
4. **S2.4** The TBS band `_tbsNorm(sc, 80, 130)` at `prospx/index.html:11369`
   is re-banded in the same commit. Mean absolute change in the TBS base term,
   weight 0.20 included, under 0.005; max under 0.03. This term reaches
   `_tbsSurplusMult`, so it reaches served dollars, and an unbanded rescale would
   saturate it.
5. **S2.5 eFV TILT PRESERVED IN SPREAD.** The per-side sd of the served
   `_statcast_factor` output after ship 2 is within 2 percent of its value after
   ship 1. The slope is divided by the ship-time points-per-sigma ratio to hold
   it there. Registered honestly: per-PLAYER tilts DO move under S3, because
   redistributing spread between coverage classes is the content of the fix. The
   preserved quantity is the aggregate scale, not each row. Letting the tilt grow
   to its intent size (r times 10 percent per sigma) is a SEPARATE question with
   its own gate and is not being ridden along.
6. **S2.6** `arkmetric_forward_eval.sc_analog_index` receives the identical
   treatment in the same commit, so the 349 AAA-override rows and the game-feed
   rows land on one scale. Measured after: the two sub-populations' served sds
   agree to within 1.0 point.
7. **S2.7** `efv_statcast_overlay` output byte-identical (it consumes raw
   component z's, not the composite; verified rather than assumed).
8. **S2.8** Suite green.

### Zero-information control

Recompute the coverage divisors from a RANDOM partition of each side into cells
of the same sizes as the real coverage classes. If random cells flatten the
per-class served sd as well as the real ones do, the coverage conditioning is
fitting noise and S3 FAILS back to S2. Registered threshold: the real
partition's worst-class deviation from 10.0 must be at least 2x better than the
random partition's, on the median of 20 draws.

### Committed loss

If S2.1 fails for both candidates, ship 1 stands alone and SC+ stays on its
compressed scale with the compression DOCUMENTED in the glossary copy rather
than fixed. That is a complete deliverable: the owner's complaint was that 130
is not believable as a maximum, and ship 1 alone already removes the fabricated
maximum.

## 3. Out of scope, explicitly

- Composite reweighting (queued to season close, `docs/archive/REVIEW_QUEUE.md` item 12).
- Adding SC+ component legs to eFV (`efv_model.py` does not read `statcast_plus`
  at all; it is a serve-time tilt in `efv_score._statcast_factor` only, so the
  eFV out-of-sample eval CANNOT see this change and the 0.017/0.016 feature-add
  floors are not the instrument here. Verified: zero `statcast_plus` references
  in `efv_model.py`).
- Display clamping of SC+.
- Promoting the registry verdict.

## 3a. RESULT, adjudicated 2026-08-07 after the criteria above were committed

Artifacts: `docs/sc-plus-2026-08-07/battery.json` (candidate comparison, from
`tools/sc_plus_recalibration_lab.py`) and `docs/sc-plus-2026-08-07/SHIP_VERIFY.txt`
(the gate re-run against the SHIPPED code, from `tools/sc_plus_ship_verify.py`).
The second exists because a criterion that passes in a lab which defines its own
variants has not been shown to hold on the site.

### Ship 1: SHIPPED

| criterion | result |
|---|---|
| S1.1 top-10 contributing legs all above floor | PASS, zero violations |
| S1.2 Kreiling no longer the maximum | PASS, 130 -> 125 against a max of 143 |
| S1.3 carriers lost under 2% | PASS, 18 of 3,582 (0.50%) |
| S1.4 Spearman(S0,S1) in [0.85, 0.98] | PASS, 0.9078 |
| S1.5 tilt inside the +/-18% clamp, clamped count not rising | PASS, 0 clamped before and after |

The 0.908 is a REORDER, close to the 0.925 the July build measured, so no
"ordering preserved" defence was available and the battery was the right
instrument.

**Zero-information control, reported in full including the part that did not
work.** The registered statistic was "the real shrink must displace strictly
more of the shipped top 10 than a volume-permuted shrink does". It reads real 8
of 10 against a permuted median of 7.5 of 10. That is a nominal pass and it is
NOT being claimed as one: the statistic is bounded at 10 and the null reaches
7.5, so it has almost no dynamic range and cannot distinguish the hypotheses.
Recorded as UNINFORMATIVE.

The instrument with power, and this is a POST-HOC choice made after seeing the
registered one saturate: within a SINGLE coverage class (the 6-leg hitters, so
leg count cannot confound), the rank correlation between composite extremity
and batted-ball sample.

| | rho(|z|, BBE) | share of the defect removed |
|---|---|---|
| shipped | -0.3396 (n=845) | - |
| real shrink | +0.0781 (n=615) | 77.0% |
| volume-permuted control, median of 20 | -0.3104 | 8.6% |

The shipped composite gets MORE extreme as the sample gets THINNER, which is
the defect stated as a number. The real shrink removes 77% of it; the
zero-information twin removes 8.6%. Ratio about 9x. An earlier pooled version
of this test read -0.0101 and looked like a null; it was confounded, because
"minimum contributing sample" mixes batted-ball counts (median 30) with pitch
counts (median 692) and coverage class drives extremity in the opposite
direction. Conditioning on one class removes the confound.

### Ship 2: S3 SHIPPED, S2 is the measured no-ship

**S2.1, the adjudicator, decided it and decided it the way the pre-registration
expected.** Served points per sigma per coverage class:

| coverage class | n | S2 (per-side divisor) | S3 (per-class divisor) |
|---|---|---|---|
| hit, 3 legs | 1,024 | 11.12 | 10.01 |
| hit, 6 legs | 615 | 7.67 | 10.00 |
| pit, 2 legs | 1,082 | 10.72 | 10.00 |
| pit, 3 legs | 160 | 12.23 | 9.98 |
| pit, 5 legs | 683 | 7.89 | 10.02 |

S2 spans 7.67 to 12.23 and FAILS. It hits 10 pooled by averaging over the
defect: a full-coverage player would still have been on a scale 45% narrower
than a zone-only player, and the elite band would still have been selected for
missing data. S3 spans 9.98 to 10.02.

**Zero-information control for the conditioning:** divisors refit on a RANDOM
partition of each side into cells of the same sizes. Real partition's worst
class deviation from 10.0 is 0.000; random partition's is 2.306 (median of 20,
range 2.279 to 2.382). The registered bar was a 2x margin; the observed margin
is total. The conditioning is on real structure.

| criterion | result |
|---|---|
| S2.1 every class in [9.5, 10.5] | PASS (S3), FAIL (S2). Worst deviation 0.024 |
| S2.2 top-10 legs above floor, max in [125,150] | PASS, max 143 |
| S2.3 populations preserved | **FAIL AS WRITTEN**, see below |
| S2.4 TBS re-band, mean move < 0.005 | PASS, 0.0031 (max 0.0213) |
| S2.5 tilt spread preserved within 2% | PASS, -0.44% hit / +0.27% pit |
| S2.6 both code paths on one scale | PASS by construction, both divide by their own composite sd |
| S2.7 overlay untouched | PASS, `efv_statcast_overlay.py` has zero references to `statcast_plus` and imports only json/os/functools/pathlib. It cannot see this change |
| S2.8 suite | run by the orchestrator |

**S2.3 FAILED AS WRITTEN and is not being reported as a pass.** Four of eight
gates land outside the registered tolerance (+/-2 rows, or 5% above 40 rows):

| gate | map | population | delta | best any integer can do |
|---|---|---|---|---|
| eta elite / breakout stat-only | 130 -> 143 | 1 -> 1 | +0 | +0 |
| spotlight elite / filter chip | 120 -> 130 | 12 -> 12 | +0 | +0 |
| eta top / breakout perf | 115 -> 122 | 43 -> 40 | -3 (-7.0%) | **-3 at 122** |
| eta bottom | 85 -> 77 | 56 -> 60 | +4 (+7.1%) | **+4 at 77** |
| spotlight above / filter chip | 105 -> 107 | 865 -> 918 | +53 (+6.1%) | **+53 at 107** |
| spotlight below / filter chip | 95 -> 92 | 762 -> 739 | -23 (-3.0%) | -23 at 92 |

The residual is DISCRETIZATION, not a wrong remap: SC+ is an integer, the
shipped cut is the population-optimal integer for every gate (verified by
sweeping every threshold from 30 to 200), and one step of the grid in the tails
is worth more than the whole registered tolerance. 121 instead of 122 would
give +18 rather than -3; 106 instead of 107 would give +206 rather than +53.

The criterion was mis-specified: it assumed a continuous scale. **That judgement
was made AFTER seeing the result, which is exactly the move pre-registration
exists to make visible, so it is written down rather than absorbed.** What the
criterion existed to prevent did not happen: the failure mode was the
elite-nudge population multiplying (measured at 43 -> 589 if the thresholds had
been left at their numbers), and the worst observed move is 1.07x. If the owner
wants the tolerance honoured literally, the fix is to gate on an unrounded SC+
and let the thresholds be non-integer; that is a separate change.

### What the reader sees change

- Site maximum 130 -> 143, and it is Yordani Martinez on 501 tracked pitches
  rather than Harrison Kreiling on 87 pitches and no batted-ball data.
- 18 players lose SC+ entirely: every leg they had was below its floor.
- 458 ETA nudges and 231 breakout-gate memberships change relative to the
  pre-shrink board. Almost all of that is ship 1 removing noise-driven passes,
  not ship 2 moving the scale.
- Served eFV grades move only through the tilt, whose spread is held to within
  half a percent. No served grade moves because of the rescale as such.

### Registry

`statcast_plus` stays `provisional`. A calibration fix is not evidence of
forward skill, and the forward-r artifact is unchanged by this work: Pearson and
Spearman are invariant to a positive linear rescale, so `data/statcast_plus_eval.json`
does not need regenerating and `efv_score._SC_FWD_R` reads the same numbers.

## 4. Known consumers NOT owned by this lane

Reported as follow-ups, not edited:

- **`org_tendencies.py:687-700` is the one that will produce a visible wrong
  number and it is NOT fixed here.** It computes SC+ DRIFT as last-minus-first
  across `metric_snapshots`, and renders it at `prospx/index.html` as "SC+
  drift" with a z-bar on the org page. Snapshots written before this ship are
  on the old scale, snapshots after are on the new one, so every drift window
  spanning the ship date measures the RECALIBRATION rather than any
  development: a player at a true +1 sigma reads 106 before and 110 after, and
  the org page will report that as a real gain. The drift needs an epoch guard
  (ignore pairs that straddle the ship date) or a one-time series reset. Until
  one lands, the org SC+ drift figures for the next window are not meaningful.
- `data/glossary.json` entry `statcast_plus` needs its copy updated. It is
  canonical and hand-edited, and `build_glossary_data.py` is a one-time builder
  that would overwrite it, so this is an edit to the JSON, not a re-run.
  Required: the filter-chip numbers "105 / 95 / 120" become "107 / 92 / 130";
  the Python tier constants sentence stays 110 and 90 but they are now genuinely
  plus or minus one sigma; the "one population standard deviation moves the
  index 10 points" claim was FALSE (the served pool moved 6.08 hit / 5.93 pit)
  and is now TRUE, so it can stay; and the methodology block should gain the
  shrink, the volume floors and the coverage-conditional divisor.
- `data/model_registry.json` needs a dated row note on `statcast_plus`: verdict
  unchanged at `provisional`, with this document and
  `docs/sc-plus-2026-08-07/` as the gate artifacts.
- `build_site.py:2059` carries an SC+ glossary teaser label (no threshold).

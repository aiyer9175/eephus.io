# Driver sweep: volume, level weights, age interactions, health (2026-09-04)

Four owner asks, all answered against the eWAR label from the same day's epoch. Written
after the measurements ran; every number here comes from an artifact, and the artifacts are
`data/xfv_volume_driver_eval.json`, `data/xfv_level_weight_eval.json`, `data/xfv_age_interaction_eval.json` and `data/xfv_health_profile_eval.json`.

NO LANE SHIPS A FEATURE. All four produce a record. Two of them overturn an expectation
that would otherwise have been coded straight into the model, and one of them finds that a
rule already in the model may point the wrong way.

## Ask 1: volume and cumulative stats as eFV drivers

> "what amount of players who hit 200+ hits in a single Minor League season went on to be
> stars/superstars? -> 200+ hits eFV driver. Sweep and check for all examples or
> combinations of cumulative stats that could potentially correlate to eFV drivers"

### The literal answer: nobody

**No player in the pool has ever had a 200-hit minor-league season.** A full-season MiLB
schedule is about 140 games, so 200 hits is roughly unreachable; the highest bracket with
any support at all is 180+, and it holds two players. The thresholds that do carry support:

| threshold | n | star rate inside | star rate outside | lift | bust rate inside |
| --- | --- | --- | --- | --- | --- |
| 160+ hits | 27 | 29.6% | 16.1% | 1.79 | 18.5% |
| 140+ hits | 155 | 18.7% | 16.1% | 1.13 | 38.7% |
| 30+ HR | 29 | 27.6% | 16.2% | 1.67 | 48.3% |
| 250+ total bases | 65 | 23.1% | 16.0% | 1.39 | 43.1% |
| 140+ H and 30+ SB | 41 | 29.3% | 15.9% | 1.77 | 24.4% |

Star means 10+ WAR over the first six years; the pool rate is 16.5 percent. So the shape of
the instinct is right: a big single-season volume line does mark a better-than-average
group, and the 160-hit and hits-plus-speed cells roughly double the star rate while
cutting the bust rate in half.

### The finding that matters more, and it points the other way

**Career minor-league volume is a strongly NEGATIVE signal.**

| threshold | n | star rate inside | star rate outside | lift | bust rate inside |
| --- | --- | --- | --- | --- | --- |
| 1,000+ career MiLB PA | 404 | 10.9% | 21.8% | 0.66 | 51.2% |
| 1,500+ career MiLB PA | 213 | 5.2% | 20.4% | 0.31 | 57.3% |
| 2,000+ career MiLB PA | 68 | 2.9% | 17.8% | 0.18 | 63.2% |

Career PA carries the strongest raw correlation in the whole family at -0.102, with minor
league seasons played at -0.109. The mechanism is not subtle: good prospects get promoted,
so accumulating 2,000 minor-league plate appearances is itself evidence that nobody was in
a hurry. Time in the minors is a bust marker.

### Whether any of it belongs in eFV

Separately from the descriptive table, every candidate was added to the shipped feature set
and scored as an incremental forward-chained margin under the gate standard, with a
permutation null and Holm across the family. Two controls decide how to read it.

- **The missingness control.** About 31 percent of hitter rows have no readable MiLB season
  at the decision point, and every volume feature reads 0.0 for them. Because career volume
  correlates negatively, a missing row is scored as though it were a fast-moving low-volume
  prospect. So the sweep runs twice, once on the full pool and once on readable rows only,
  and a candidate that works only in the full pool is sensing missingness rather than volume.
- **Holm.** The family is 38 candidates per side and several individual permutation p-values
  land near 0.01 in the NEGATIVE direction. Uncorrected, that would read as findings; it is
  what a search of this size produces by chance.

### The gated verdict: nothing ships, and the raw counts actively hurt

| scope | rows | baseline margin | tested | clears own floor | survives Holm | SHIPPABLE |
| --- | --- | --- | --- | --- | --- | --- |
| hit, full pool | 845 | +0.0105 | 37 | 3 | 0 | **0** |
| hit, readable only | 581 | +0.0225 | 36 | 2 | 0 | **0** |
| pit, full pool | 983 | -0.0129 | 19 | 0 | 0 | **0** |
| pit, readable only | 695 | +0.0014 | 18 | 4 | 0 | **0** |

Not one candidate on either side, in either scope, clears its own floor with a positive
delta and survives Holm. The descriptive lift is real and it is already priced: eFV carries
the consensus grade, the level reached and the age-relative-to-level read, so a 160-hit
season is largely a restatement of "he was an everyday player at a full-season level and he
hit".

The more useful result is the sign. Every candidate that clears a floor does so NEGATIVE,
and three of them are emphatic: adding raw peak home runs costs -0.0352 against a floor of
0.0317 with a permutation p of 0.000, career home runs -0.0296, career hits -0.0269. These
are not weak features, they are harmful ones. A raw count is a playing-time and level proxy
wearing a performance label, and handing it to the ridge alongside features that already
encode level and age adds variance with no signal. The per-fold signs agree: career home
runs is positive in 1 fold of 11.

One scope difference is worth keeping. The hitter baseline margin is +0.0105 on the full
pool and +0.0225 on readable rows only, so the model does visibly better on players with a
minor-league record than on those without. That is a statement about the 31 percent with no
readable history, not about volume, and it is the kind of thing a missingness control
exists to surface.

## Ask 2: level and league weights

> "what is the weight of a DSL performance compared to a Double A performance? My instinct
> says AA > A+ > A > AAA > CPX > DSL ... the PCL is known for being very friendly to
> hitters, so hitting well here should be weighted less heavily"

Two quantities hide in that question and the lab keeps them apart.

**RAW strength** is the correlation between level-relative performance at a level and
first-six-year WAR, among players who posted a qualifying season there. That is the question
as asked.

**INCREMENTAL strength** is the same correlation after the consensus FV and age-relative-to
-level are partialled out. That is what an eFV driver needs, because eFV already carries the
scouting grade and the age read.

### Raw strength, hitters. The instinct is right about the shape and wrong about AAA

| level | n | key | raw rho | interval excludes zero | derived weight |
| --- | --- | --- | --- | --- | --- |
| AAA | 239 | OBP vs level | +0.189 | yes | **1.00** |
| AA | 491 | OBP vs level | +0.155 | yes | 0.82 |
| A | 515 | BB vs level | +0.097 | yes | 0.51 |
| A+ | 525 | BB vs level | +0.049 | no | 0.00 |
| CPX | 287 | BB vs level | +0.028 | no | 0.00 |
| DSL | 71 | ISO vs level | -0.010 | no | 0.00 |

The measured order is **AAA > AA > A > A+ > CPX > DSL**. The expectation had AAA fourth,
below A; it is in fact the strongest level on the board. That makes sense once stated: AAA
is the last stop before the majors, so performance there is the closest available proxy for
major-league readiness. The bottom of the expected order is confirmed exactly. Complex ball
and the DSL carry no measurable signal, and the DSL cell is 71 players wide, which is too
thin to weight at all.

Pitchers order differently and more weakly: A+ strikeout rate is the only clearly positive
raw cell (+0.180), with A behind it (+0.100). AA, AAA, CPX and DSL all span zero.

### Incremental strength: almost all of it is already in the grade

Once the consensus FV and age are partialled out, the hitter table collapses. Only A-level
walk rate survives with an interval clear of zero (+0.098), and AAA falls to +0.118 with an
interval spanning zero. On the pitcher side two cells survive: AAA strikeout rate at +0.175
and A+ at +0.092.

That is the useful conclusion for the model. **A per-level weighting scheme built on raw
strength would mostly be re-weighting the scouting grade**, because scouts already know
that a good AAA line means more than a good complex-league line. The residual, which is
where a driver could live, is thin and concentrated in pitcher strikeout rate at the top of
the ladder.

### The PCL question: the norms already handle it, and a second penalty would double-count

Every rate in this lab is already level-relative to contemporaneous season-and-level norms.
A hitter-friendly league is therefore normalised by its own league's median before anything
is compared, which is the mechanism the ask was reaching for. The remaining question is
whether a residual league effect survives that normalisation, and the answer is no:

| side | key tests | intervals excluding zero | expected by chance |
| --- | --- | --- | --- |
| hit | 90 | 6 | 4.5 |
| pit | 54 | 6 | 2.7 |

Both counts sit at or near the chance line, and the per-cell headline is a maximum over
five keys, which inflates them further. So there is no evidence for a residual PCL discount.
Specifically, AAA Pacific Coast League power reads +0.247 after the norms, an interval that
spans zero and points UP rather than down. Applying a hand penalty on top of the norms would
subtract the environment twice.

## Ask 3: age-vs-level as a weight on production instead of a flat feature

> "Instead of having a flat eFV driver weighting age for level, can we instead test and
> possibly implement age-vs-level-weighting into eFV statistical production drivers?"

Four interaction shapes were built per production key: the product of age-relative-to-level
with the rate, a split into separate young-for-level and old-for-level slopes, the product
with level rank, and all products jointly. Then the arm the ask is literally about: drop the
flat age term and put the products in its place. The permutation null shuffles the AGE
vector inside each decision year, so it preserves both marginals and the cohort structure
and destroys only the pairing.

**All 24 arms across both sides come back negative. Not one is positive.**

| arm | hitters | pitchers |
| --- | --- | --- |
| replace the flat age term with the products | -0.0300 | -0.0164 |
| all products jointly | -0.0327 | -0.0207 |
| split obp or bb slopes by age band | -0.0403 | -0.0166 |

The one cell that clears its own floor and survives Holm is the hitter OBP split at -0.0403
with a permutation p of 0.000, which makes it significantly HARMFUL rather than merely
unhelpful. The mechanism is ordinary collinearity: the ridge already carries
age-relative-to-level and the production rates as separate columns, and the consensus FV
already prices young-for-level performance, because that is exactly what scouts do. The
interaction columns therefore add variance without adding information.

So the answer is no, and it is a clean no. The flat additive term is the better form.

## Ask 4: a health profile driver, outcome-grounded

> "build a predictive machine-learning based driver submodel which will build a player's
> health profile ... this will replace our current system of just penalizing players for
> being currently on IL ... what correlation is there between Tommy John and a pitcher's
> MLB production? What correlation is there between players who spent a cumulative number
> of X days on the Injured List during their time as a prospect and their eventual
> outcomes?"

This lane was run twice. The first pass was blocked by data and the second pass fixed the
data, corrected the population, and produced an answer that is the opposite of the naive one.

### The archive was our limit, not the source's

`il_history` is not a history: 1,415 of its 1,662 placements are 2026 and it was first
populated on 2026-06-06. The real source is `player_transactions`, which carries both
placements and activations so cumulative days are computable. It started in 2019 because
`stats.TRANSACTIONS_LOOKBACK_SEASONS` was 7, not because the endpoint stopped there. Probed
with an explicit start year, the API returns injured-list events back to 2014 for Byron
Buxton and 2016 for Aaron Nola.

Backfilled with a superset guard: **16,678 pre-2019 events recovered across 1,684 players**,
no refusals. Pre-decision coverage went from 33.8 percent to 49.3 (hitters) and 46.0
(pitchers), and the observable cohort roughly doubled. The constant is now 16 so it does not
regress.

Archive reliability is now measured rather than assumed. The injured-list rate per ACTIVE
player-year plateaus near 27 percent from 2017 and is clearly thin before it:

| 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2021 | 2024 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6.4% | 13.6% | 16.8% | 15.9% | 21.9% | 23.7% | 24.2% | 28.2% | 27.2% |

So a missing stint before 2017 is more likely a missing record than a healthy player, and
observability is now a coverage share of each player's own window against that floor.

### The exposure confound, which is the actual finding

**A player cannot be placed on an injured list unless he is on a roster.** So "no IL record"
conflates a healthy prospect with one who never had enough rostered time to be placed on
one. On the full pool, 576 of 1,127 observable hitters have no record at all, and:

| cohort | n | mean WAR | star | **bust** |
| --- | --- | --- | --- | --- |
| hitters with NO IL record | 576 | 1.25 | 5.0% | **83.7%** |
| hitters with any IL record | 551 | 1.92 | 7.4% | **68.6%** |

Read raw, the data says injuries are good for you. They are not; being rostered is.

The pool choice flips the sign on its own. Hitter `il_stints` correlates **-0.084** with the
label on debuted rows and **+0.014** on the full pool. Scoring debuted-only conditions on the
outcome an injury is most likely to prevent, so it is the wrong population for this question
even though it is the right one everywhere else in this program.

### Exposure-controlled, the answer is side-asymmetric

Partialling out the scouting grade, age and the best available proxies for rostered time:

| burden feature | hitters raw | hitters controlled | pitchers raw (debuted) | pitchers controlled |
| --- | --- | --- | --- | --- |
| cumulative IL days | +0.039 | **+0.165** | -0.071 | **-0.119** |
| longest single stint | +0.041 | **+0.173** | -0.064 | **-0.110** |
| 2+ stints | +0.006 | +0.087 | -0.093 | **-0.112** |
| 60-day placements | +0.015 | **+0.203** | -0.045 | -0.124 |
| on the IL at the decision | +0.033 | +0.065 | -0.026 | **-0.166** (full pool) |

**For hitters, injury burden is not a negative signal once exposure is controlled; it is
positive.** Among hitters of equal grade, age and rostered time, the ones who missed time did
better, which most plausibly reads as organizations investing rehab time in players they
rate. **For pitchers the control makes the harm larger, not smaller**, and being on the IL at
the decision date is the strongest negative in the table.

### The penalty decision, taken and shipped

The shipped rule is `efv_score._injury_factor`: a multiplicative haircut on eFV WAR, gated on
`il_on`, and it used to apply to both sides on the live board.

Before changing it, the rule was tested as the rule, on the full pool, with the grade, age
and rostered-exposure proxies partialled out, and with bootstrap intervals rather than point
estimates. The bar was the owner's: a penalty stays only if it is PROVEN, so the interval has
to exclude zero on the negative side.

| side | n | rho | CI95 | verdict |
| --- | --- | --- | --- | --- |
| pitchers | 1,220 | -0.1664 | [-0.2228, -0.1087] | **SUPPORTED**, interval below zero |
| hitters | 1,127 | +0.0651 | [+0.0021, +0.1282] | **CONTRAINDICATED**, interval above zero |

The hitter cell does not say "unproven". It says the sign is the other way. An unproven
penalty is not a neutral default: it is a live subtraction from a real player's grade, rank
and dollars, and this one was subtracting against the evidence on 225 served hitters at a
median multiplier of 0.738.

**SHIPPED**: `efv_score.INJURY_PENALTY_SIDES = frozenset({"pit"})`. The board effect on those
225 hitters is 74 grades up, 150 flat and 1 down, mean +0.31 FV, largest +4.6 (leo_de_vries
55.5 to 60.1). The 150 flat rows sit at the FV20 floor, where the outcome curve is constant
below 0 WAR, so lifting a penalty cannot move them. The single row that falls is
cameron_nelson, whose `grade_basis` flips from `provisional_capped` to `outcome_pooled` as
his model WAR crosses zero: that is the floor-routing discontinuity the design audit already
records, not a new defect. 360 pitchers keep their haircut unchanged.

`BOARD_BASIS_FINGERPRINT` gained an `injsides=` term in the same commit as the change, so the
coordination device can see a live overlay it previously could not. It rides the same
`BOARD_RANK_BASIS_EPOCH` 2026-09-04 as the label epoch, since both are one-time basis moves
on the same day.

**NOT changed, and the distinction is deliberate**: the severity dispatch by IL type and the
deepening modifiers on trailing days and stints. Those could only be measured on the players
the gate actually taxes (n=144 pitchers) and every interval spans zero. At that width it is
low power, not evidence of absence, so removing them would be acting on the absence of
evidence rather than on evidence. They keep their behaviour for pitchers and are the obvious
thing to re-read when the cohort grows.

### As a driver: nothing ships

Every candidate, including a stacked forward-chained health submodel over stints, days,
longest stint and the 60-day and full-season counts, was added to the shipped feature set and
scored with an E_cond floor, a permutation null and Holm across the family.

| cell | observable | scored | SHIPPABLE | best positive delta |
| --- | --- | --- | --- | --- |
| hit, full pool | 1,127 | 1,024 | **none** | il_days_ge_30 +0.0133 (floor 0.0149) |
| hit, debuted only | 516 | 444 | **none** | cat_wrist +0.0128 |
| pit, full pool | 1,220 | 1,081 | **none** | durable_zero_il +0.0050 |
| pit, debuted only | 635 | 559 | **none** | il_days +0.0079 |

The submodel is negative in all four cells (-0.003 to -0.057) and never clears its floor.
The first pass's most promising cell, pitcher 90-or-more IL days at +0.0172, **collapsed to
+0.0037** once the archive was repaired. It was a small-sample artifact, which is exactly
what the repair was for.

One instrument defect is worth recording because it was mine. The first submodel build
scored -0.174 with a permutation p of 0.000, which looked like a dramatic result. The raw
out-of-fold score is a WAR-scale prediction whose level drifts by fold (per-fold means 4.08,
5.03, 4.36, 3.81, 4.06, 3.63) and whose first fold has no prior data at all, so it was
encoding cohort year rather than health. Standardised within decision year it reads -0.003,
a clean null.

### Tommy John cannot be answered on the prospect window

Not for want of an archive. **Minor-league placements name the injury 3.2 percent of the
time** (319 of 10,039) against 54.5 percent in the majors, because affiliate transactions
are usually bare. The prospect-window Tommy John cell is n=1 before the backfill and still
too thin after it. Answering the question properly means asking it on the major-league side,
where the naming rate supports it, and that is a different question from the one a prospect
driver asks.

## What none of these lanes change

No feature was added, no weight was shipped, no copy moved. The do-not-reopen ledger gains
FOUR closed families rather than losing any: volume and cumulative counts, per-level or
per-league weighting of MiLB rates, age-by-production interactions, and the health profile.

The health family closes differently from the other three, and the distinction matters. The
first three are null because the signal is already priced. Health is null because the signal
that looked like health was mostly ROSTERED EXPOSURE, and once that is partialled out what
remains is real but side-asymmetric and still inside every floor. It closes as a DRIVER while
leaving one live question behind it: the shipped injured-list haircut is applied to both
sides identically, and the outcome evidence supports it for pitchers only.

One thing did change outside the models. The injury archive was widened from 7 seasons to 16
and backfilled, which is a permanent data improvement that outlives this null: the lane can
be re-run as cohorts mature, and any future work touching injuries starts from 2011 instead
of 2019.

All four were opened legitimately: the eWAR label epoch replaced the label, which is the
registered condition for a re-sweep. All four are recorded with their numbers so the next
person does not pay for them again.

One methodological note that applies across the set. Every family here produced individual
cells with permutation p-values under 0.05, and in a search of this size that is expected
rather than informative. Holm is what separates them, and after Holm exactly one cell in
110 volume tests, zero in 24 interaction arms and zero in 43 health arms survives, while the
single interaction cell that does survive is negative. A sweep that reports its best cell
without its family size is not reporting a finding.

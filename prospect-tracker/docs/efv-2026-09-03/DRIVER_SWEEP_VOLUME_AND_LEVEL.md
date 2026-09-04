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

### The data question comes first, and it binds

`il_history` is not a history. 1,415 of its 1,662 placements are 2026 and the table was
first populated on 2026-06-06, so it is forward-collected. The usable source is
`player_transactions`, which carries 27,255 injured-list events on 4,887 players with both
placements and activations, so cumulative days really are computable. It starts in 2019.

That gives pre-decision injury coverage of zero for debut years 2016 to 2018 and 39 to 79
percent for 2020 to 2024. Roughly half of each side is observable, and only 311 hitter and
455 pitcher rows can be scored. A feature built on the full pool would read "no injuries"
for every pre-2019 row and would therefore encode debut era, not health. Every gated arm
below runs on the observable cohort only.

### Descriptively, the instinct is right

| cohort | n | mean WAR inside | outside | star inside | outside | bust inside | outside |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hitters, no IL placement | 174 | 4.08 | 2.62 | 16.1% | 9.6% | 44.8% | 52.6% |
| hitters, 4+ stints | 34 | 1.42 | 3.34 | 5.9% | 12.7% | 58.8% | 48.8% |
| pitchers, no IL placement | 254 | 2.15 | 1.40 | 5.9% | 2.9% | 50.8% | 54.1% |
| pitchers, 2+ stints | 151 | 1.19 | 1.95 | 1.3% | 5.4% | 52.3% | 52.7% |
| pitchers, 30+ cumulative days | 224 | 1.22 | 2.09 | 2.7% | 5.4% | 57.6% | 49.2% |

Cumulative injured-list days correlate negatively with outcomes on both sides, most
strongly for pitchers, where longest single stint reads -0.083 and cumulative days -0.080.
Durability is worth roughly a doubling of the star rate on the pitcher side.

### Gated, nothing survives, but this family came closest

No candidate ships. The best cell is pitcher 90-or-more cumulative injured-list days at
+0.0172, which does clear its own 0.0153 floor with a permutation p of 0.005, but lands at
Holm 0.10 in a family of twenty. That is nearer to shipping than anything else measured on
2026-09-04, and the reason it falls short is sample size, not effect size.

### The finding that bears on the current penalty

The signal the existing haircut uses, being on the injured list at the decision date, points
the WRONG WAY in this cohort. Hitters carrying it average 3.80 WAR against 3.10, with a star
rate of 17.5 percent against 11.4; pitchers carrying it star at 7.7 percent against 3.9. The
samples are 57 and 52 and the cohort is selected, so this is not a verdict. It is enough to
say that penalising current injured-list status is unsupported by outcomes and may be
backwards, most likely because a prospect who stays highly ranked while hurt is one the
industry believes in.

The honest disposition: do not remove the haircut on this evidence alone, and do not defend
it on outcomes either. What would change the verdict is a longer injury archive, not a
better model.

## What none of these lanes change

No feature was added, no weight was shipped, no copy moved. The do-not-reopen ledger gains
three closed families rather than losing any: volume and cumulative counts, per-level or
per-league weighting of MiLB rates, and age-by-production interactions. The health family
stays OPEN as provisional, because it is the only one whose failure is sample size rather
than absence of signal, and because its incidental finding about the current injured-list
penalty deserves a decision rather than a filing.

All four were opened legitimately: the eWAR label epoch replaced the label, which is the
registered condition for a re-sweep. All four are recorded with their numbers so the next
person does not pay for them again.

One methodological note that applies across the set. Every family here produced individual
cells with permutation p-values under 0.05, and in a search of this size that is expected
rather than informative. Holm is what separates them, and after Holm exactly one cell in
110 volume tests, zero in 24 interaction arms and zero in 43 health arms survives, while the
single interaction cell that does survive is negative. A sweep that reports its best cell
without its family size is not reporting a finding.

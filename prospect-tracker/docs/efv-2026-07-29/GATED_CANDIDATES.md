# Gated candidates from the 2026-07-29 Arkmetric sweep

Four fixes were built, measured, and then REVERTED because they move served model output
and a correctness sweep may not do that. None is abandoned. Each is a real defect with a
working fix; each needs a pre-registered gate under `docs/EFV_GATE_STANDARD.md` before it
can ship. This file is the registration.

The reverting rule that produced this list is worth stating once: a fix that is correct in
isolation is still out of scope if it changes a grade, a rank, or a dollar. Those changes
need their own evidence, not a ride along on someone else's.

---

## C1. SC+ sample gate and shrink

**The defect is real.** `statcast_plus.py` applies no volume gate and no shrink, so a
hitter with 3 batted balls contributes a full-magnitude exit-velocity z, and if that is his
only present component his SC+ is a single unshrunk z. Every other plus-metric in the suite
has an EB shrink or a volume gate. Two smaller defects sit beside it: the pool's column set
is taken from `rows[0].keys()` only, and the degenerate-column guard tests `sd > 0`, which
does not stop a near-zero sd from producing an unbounded z.

**Why it did not ship.** It moves eFV. `efv_score._statcast_factor` multiplies the eFV WAR
projection by `1 + (SC+ - 100) * slope`, and the tilt factor changed for **2,887 players**,
mean 0.303% of projected WAR, max 5.88%. Critically **Spearman(old SC+, new SC+) = 0.925**,
so this is a REORDERING, not a monotone rescale, and no "ordering preserved" defence is
available. On top of that there are about 295 gate-band crossings reaching the `eta.py`
plus-or-minus 0.25y and 0.5y nudges and the 115/130 breakout gates, plus the SC+ term at
weight 0.20 in the active-MiLB TBS branch, which feeds the surplus multiplier.

**Gate it needs.** Treat as a rank-moving eFV change: forward-chained pooled Spearman and
AUC on both sides against the registered floors (0.017 hit, 0.016 pit), a zero-information
control, and a bounded post-flip board-movement battery. Report how many of the 295
gate-band crossings change an ETA or a breakout flag, since those are user-visible.

**Sizing note for whoever runs it:** the shrink constants used in the reverted build were
contact quality floor 10 / K=50, zone discipline floor 25 / K=100, velocity floor 10 / K=50,
matching the house `(n*value + K*prior)/(n+K)` recipe.

**Also measured and worth keeping in the record:** SC+ averages up to six correlated unit-z
components, so its composite pool sd is about **0.52 hit / 0.46 pit**. One SC+ point is
roughly a fifth of a pool sigma, not a tenth, and the metric has always been on that scale.
Re-standardizing it would widen SC+ against fixed downstream thresholds, so it is a separate
decision from the gate and shrink.

---

## C2. Draft and overseas RPS+ / Tool+ from 15z to 10z

**The defect is real.** `draft_export.py` and `overseas_export.py` still emit
`100 + 15*z` clamped to `[60, 140]`, while the rest of the backend harmonized on
`100 + 10*z`. 37 rows currently pin at a clamp bound. The owner has chosen full
true-to-model harmonization.

**Why it did not ship.** `prospx/index.html` hard-codes the old scale in
`_tbsNorm(v, 80, 130)` at four sites (draft weights 0.18 and 0.21, overseas 0.22 and 0.20).
Under 15z, 130 is two sigma; under 10z it is three. So the conversion compresses both terms'
TBS contribution by a third relative to DS+, tools and age. Measured over
`data/draft_timeseries.json` (2,347 rows): mean absolute TBS-base change 0.0121, max 0.0648,
with 450 rows moving at least 0.02. For draft and overseas the weights sum to 1.00 and there
is no eFV term, so that lands roughly 1:1 on the 0-130 TBS integer, worst cases about 6.5
points (Wideman, Cholowsky, Lackey).

TBS is the sole tie-arbiter in `fvCmpDesc` and draft rows tie on consensus FV constantly, so
this reorders the boards; and TBS feeds `_tbsSurplusMult`, a linear map from TBS to a 0.88 to
1.12 multiplier, so a 6.5-point move is about a **1.6% surplus-dollar move** on top draft
prospects.

**The fix must be atomic.** Convert the producers AND re-band the four `_tbsNorm` call sites
in the same change, then gate the resulting board movement. Converting either side alone is
worse than doing nothing. Note also that `tool_plus` renders nowhere on the site, so on its
own the conversion is pure model effect with zero display benefit.

---

## C3. aStuff+ standardizing denominator

**The defect is real and large.** `stuff_plus_aaa.py` takes `mu` and `sd` from the UNSHRUNK
pool while the numerator uses the SHRUNK value, so the scale delivers **7.16 points per
sigma against an advertised 10** (`sd_raw` 0.003786 versus `sd_shrunk` 0.002712, ratio
0.7164 on the 638-arm anchor pool). Fixing it moves 1,353 of 1,379 served values, mean
absolute change 2.15, max 14.10, and widens the served sd from 7.01 to 9.81. The same bug is
mirrored in `aaa_physics_export.py`, and the two must move together because
`aaa_physics_export.meta.served_json_agreement` cross-checks them.

**Why it did not ship.** `efv_statcast_overlay.py` regresses features on the aStuff+ scale
using FROZEN coefficients (`intercept + slope * ast`, residual-sd standardized) read from
`data/aaa_physics.json`. Rescaling aStuff+ invalidates those coefficients silently: the
overlay would keep applying a fit calibrated to the old spread.

**The fix must be atomic.** Rescale aStuff+ and re-fit the overlay coefficients in the same
change, then verify the overlay's output is unchanged where it should be. If the overlay is
default-OFF at the time, say so and the coupling is weaker, but check rather than assume.

**Separately, and NOT a blocker:** the anchor pool is `VALID_SEASON = 2025` only while scores
are stamped from each pitcher's latest season, so 2026 arms are compared against a 2025 pool.
That is arguably correct (a fixed anchor is what makes scores comparable across seasons) and
is the registered convention, but the drift is real and worth publishing: season means run
2023 97.08, 2024 98.04, 2025 100.06, 2026 99.34.

---

## C4. Reviving the dormant RPS+ term in the active TBS

**The situation.** `prospx/index.html` carried an active-MiLB TBS term
`[_tbsNorm(rps, 80, 130), 0.22]` reading `statline.rps_plus`, a field populated for **0 of
4,505 players**. It always resolved null, was filtered out, and the surviving weights
renormalized, so the in-code note claiming "perf up (was 0.16)" described a reweight that
never happened on a single active row. The term has been REMOVED, which is a true no-op.

**Why it was not simply repointed** at the live browser-computed RPS+, which is what the
display surfaces now use: that would make a dormant 0.22 weight suddenly bind, moving TBS,
which moves rank ordering and the surplus multiplier.

**Two things must be settled before a revival.** First, the band is wrong for the metric:
active RPS+ is a RATIO index with sd near 20, so `_tbsNorm(v, 80, 130)` saturates about 23%
of rows (roughly 15% at the floor, 7% at the ceiling), and saturated rows contribute no
discrimination. The sibling SC+ term on the identical band is `100 + 10z` with sd near 10 and
saturates far less, so the two terms are not comparable despite sharing a band. Second, a
revival moves served ordering, so it needs a board-movement gate.

---

## Standing note

All four were built, measured, and reverted in the same session. The measurements above are
the expensive part and they are recorded here so a future attempt starts from evidence rather
than from scratch. What none of them has is a gate, and that is the only thing standing
between them and shipping.

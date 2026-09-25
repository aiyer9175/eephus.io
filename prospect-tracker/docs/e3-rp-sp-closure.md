# Lane E3 closure: RP to SP is sign-wrong, not underpowered

Written 2026-08-06. No new run was performed. Everything below cites artifacts
already on disk, chiefly `data/pal_gamelog_eval.json` (generated 2026-07-15) and
`.cache/pal_xrv/w3_detail.json`.

## The finding

The master plan's premise for this lane was that "the binding constraint is n,
not features", and the instruction was to expand the closed-event set and
re-gate. **That expansion has already been run, and the premise is wrong.**

From `data/pal_gamelog_eval.json`, `verdicts.lane_a.rp_sp_stays_sign_wrong`:

| set | n | Spearman rho | passes gate |
|---|---|---|---|
| legacy | 25 | -0.2062 | no |
| expanded | 35 | -0.1736 | no, and no under v2 |

The gate requires the model's rank correlation with `war_delta` to beat the best
baseline, with the gap's lower 95% bound above -0.01. The observed correlation is
**negative**. The fit ranks RP-to-SP candidates in close to the opposite of the
order their outcomes take.

## Why more data cannot fix it

A sample-size argument applies to an effect that is real but not yet resolvable.
This effect is resolvable and points the wrong way.

Bootstrap spread on Spearman rho at this size is approximately
`sd(n) = 1.106 / sqrt(n)`, so the gate's minimum detectable effect is about
**+0.356 at n = 35** and about **+0.207 at n = 100**. The observed gap against
the best baseline is **-0.198**. No n closes a gap that is on the wrong side of
zero; collecting more events makes the failure more certain, not less.

The arrival rate settles it as a practical matter too. The expansion recovered 89
conversion events in total, of which the RP-to-SP gate set gained **10** (25 to
35), not the roughly 100 that decision #8 assumed. That estimate was reading the
SP-to-RP figure. At the observed rate of about 5.8 new RP-to-SP gate rows per
season, n = 100 arrives around **2037**.

## What the same expansion did prove

`verdicts.lane_a.sp_rp_pass_strengthens`, the other direction, **passed and got
stronger**:

| set | n | rho | gap lo95 | passes |
|---|---|---|---|---|
| legacy | 61 | 0.2916 | +0.0745 | yes |
| expanded | 100 | 0.3607 | +0.4647 | yes, under v1 and v2 |

So the owner's "run both, report both" decision is discharged. One direction
works and is now better evidenced than it was; the other does not work and cannot
be rescued by volume.

This asymmetry is itself informative. The event detector, the labeling, and the
gate machinery are all shared between the two directions, so SP-to-RP passing on
the same pipeline rules out a harness defect as the explanation for RP-to-SP
failing. What is left is the model.

**Caveat added 2026-09-25 (final pass M07-01).** The SP-to-RP pass above is
weaker evidence than this section reads. Every registered baseline (K-BB%,
negated ERA, SEM+) is signed so a better pre-season predicts a bigger gain,
while war_delta pays out on a bad pre-season. Read the other way, the negated
ERA baseline ranks the legacy 61 events at +0.62 (data/pal_eval.json -0.62)
and the expanded 100 at +0.6828 (data/pal_gamelog_eval.json -0.6828), above
FIT both times, and FIT scales with starter ERA through its conversion-need
term. So "one direction works" holds against quality reads, not against
regression to the mean, and the harness-defect argument rests on the same
pass. Nothing here was re-gated; a need-direction re-gate is a new
pre-registration (owner sign-off, after the fWAR season-close epoch), and the
RP-to-SP closed-event set stays closed.

## Status

**Lane E3 is closed as a NO-SHIP for RP to SP.** Nothing was shipped, and the
`pal_conversion` registry verdict stays `provisional`.

Added to the banned-experiment ledger: do not propose expanding the RP-to-SP
closed-event set again as a route to passing this gate. The expansion has been
run, the direction of the effect is the problem, and the power arithmetic above
is the reason.

## What would legitimately reopen it

Not more rows. A different model or a different target, pre-registered as such:

1. **A different target.** `war_delta` may be the wrong outcome for this
   question. A held-the-role label, or an innings-weighted quality measure,
   changes what is being predicted rather than how much of it there is.
2. **A different feature basis.** The current fit is an arsenal-depth-anchored
   weighted blend with frozen literature weights. The negative correlation is
   consistent with the blend being anti-informative for this direction, which is
   a model claim and is testable directly.
3. **The W3 ARM-1 aStuff plus blend gate**, pre-registered in
   `tools/pal_xrv_lab.py` and never run. It is a separate question from the
   event count and remains open.

Any of those is a new pre-registration with its own gate, not a continuation of
this one.

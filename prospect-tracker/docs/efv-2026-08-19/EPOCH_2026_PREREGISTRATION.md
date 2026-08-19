# V1: the RESOLVED_THROUGH-2026 epoch, pre-registered 2026-08-19

STATUS: REGISTERED AND DATA-BLOCKED by the calendar. Runs when the 2026 season resolves
(early 2027). Frozen now so unlock day is measurement day, not design day. Results PENDING.

## What the advance does (mechanical, already wired)

- efv_dataset.py:269 RESOLVED_THROUGH 2025 -> 2026 (one constant).
- DEBUT_YEARS is DERIVED (tuple(range(2011, RESOLVED_THROUGH))), so the 2025 debut cohort
  (243 debuts already in debuts.json) is admitted automatically with >= 2 observed seasons.
- The pitcher-stuff fold (test year 2025) exists for the first time; the aStuff+ gate
  (data/xfv_pitcher_stuff_eval.json) becomes runnable; its registration already pins that a
  thin first fold (~48 covered training rows) reporting null is recorded as UNDERPOWERED,
  never as "stuff does not predict".
- SAME-COMMIT CHECKLIST: tools/build_star_odds_artifacts.py:27 carries an independent
  _RESOLVED_THROUGH copy; grep for any other shadow copies at flip time; label matrices,
  evals, floors, and the golden fingerprint all regenerate; margins re-read AFTER regeneration
  (a margin read against a stale artifact is the 2026-08-13b vacuous-re-read defect).

## Measurement protocol (frozen)

1. FLOORS FIRST: re-derive every floor on the new frame (E_cond primary, E_refit beside)
   before reading ANY delta. The old floors adjudicate nothing on the new frame.
2. Then measure EXACTLY the claim-frame cells C1-C4 of CONVICTION_PROGRAM.md, Holm across
   four. No new cells may be added after the first read; cells may only be retired by the
   decidability triage BEFORE the read.
3. The pitcher-stuff gate runs as its own registered lane (existing registration), not inside
   the claim frame.
4. Publish the power delta: old floor vs new floor per cell, and the components (pool growth
   vs refit-share change). The head-to-head cell's floor is the one with majority-removable
   refit share (0.128 recorded at EFV_GATE_STANDARD power ceiling); verify that figure on the
   new frame rather than reusing it.

## Pre-committed interpretations (so the answer cannot be argued after the fact)

- All four cells clear under Holm: the site claim upgrades through the derived three-branch
  copy; nothing is hand-written.
- Some cells clear: partial derived branches only; the headline claim does NOT ship.
- No cell clears: the tie frame stands; the label-pool lever is spent for the year; the
  program's next admissible lever is V2 new data only.

## Power projection (runs NOW, projection only)

A lab may project the 2026 floors by scaling the stored bootstrap components of the current
floors to the projected pool sizes (current resolved pools plus the 2025 cohort's expected
debuted counts). The projection adjudicates NOTHING; it exists to size expectations and is
labeled a projection in its artifact. Its artifact: data/xfv_epoch2026_power_projection.json
(registered as a companion on the conviction program's ledger row when created).

## Projection results note (2026-08-19, projection only, adjudicates nothing)

Ran as tools/efv_epoch_power_projection.py, artifact data/xfv_epoch2026_power_projection.json
(projection_only: true). Cohort: 243 tracked 2025 debuts (110 hit, 133 pit) against 2,208
tracked 2011-2024 debuts; per-cell increments derived from the pools' own historical entry
rates (C3 +68 of 645, C4 +88 of 766; C1/C2 per-side split constructed from the pooled
vintage-matched n=802, an assumption stated in the artifact). Refit component held fixed,
sampling component sqrt-n scaled; the head-to-head refit share was recomputed from stored
components, 1 - (0.01956/0.02095)^2 = 0.1283 vs 0.128 stored, match. Projected E_cond floors:
C1 0.0411 to 0.0391, C2 0.0391 to 0.0370, C3 0.0131 to 0.0125, C4 0.0205 to 0.0194, a 4.9-5.3
pct reduction. Honest read: NO cell plausibly resolves on labels alone. C1/C2 sit at a
NEGATIVE pooled delta vs the best rater (-0.0021 vs mlb_pipeline) and a floor cut cannot clear
a negative delta; C3 is closest but its stored 0.00965 margin stays under even the most
favorable Holm slot (0.0125); C4 sits near 0.21x. Central expectation for the V1 unlock is the
prereg's "no cell clears" branch; the lever's value is the floor reduction plus the first
pitcher-stuff fold. These numbers size expectations only; measurement-time floors on the new
frame are the only floors that adjudicate.

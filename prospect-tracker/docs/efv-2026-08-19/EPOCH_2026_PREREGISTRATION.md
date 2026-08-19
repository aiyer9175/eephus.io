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

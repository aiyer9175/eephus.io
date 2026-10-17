# EFV_X3_POOLED_MODEL: candidate list

EFV_X3_POOLED_MODEL (the pooled eFV model of the expert program, owner decision EW3-12) has no
registration document yet. This file collects the dated addenda that pre-register candidates
for it; X3's own registration selects among them. Earlier hand-offs are recorded in their own
documents and are only pointed to here:

- EFV_X1_MLE_TRANSLATION: the translated, reliability-weighted rates and their year-over-year
  changes, passed as inputs, none flagged (`docs/efv-v2/EFV_X1_MLE_TRANSLATION.md` section 11).
- EFV_ETOOLS_REWEIGHT: the re-weighted tool arm `efv_etools_reweight.etool_inputs`
  (`docs/efv-v2/EFV_ETOOLS_REWEIGHT_RESULTS.md`).
- ETOOLS: the passing eTools as one pre-declared arm (`docs/tools-2026-10/ETOOLS_RESULTS.md`,
  "What feeds EFV_X3").

No em-dashes.

## Addendum 2026-10-16: upside and volatility markers (EFV_UPSIDE_VOLATILITY_DRIVERS)

Owner decision EW3-35 (2026-10-16). Pre-registered as X3 candidates before any of their
numbers exists: the UPSIDE markers U01 to U18 (height, weight, age-adjusted frame, FanGraphs
frame, athleticism and levers, run grade, stolen-base and triple rates, the athleticism
composite, age for level, the ISO and contact peaks, max exit velocity, the strikeout and
walk peaks, fastball top and sitting velocity) and the VOLATILITY markers V01 to V10 (velocity
change, top-velocity change, workload spike and its flag, prior surgeries, IL stints, days,
recurrence and 60-day stints, FanGraphs delivery), each defined in
`docs/efv-v2/EFV_UPSIDE_VOLATILITY_DRIVERS.md` section 3.

Condition on X3's registration: a marker this task hands over on a distributional score (CRPS
on six-season WAR or the bust, middle and star class log loss) is scored by X3 on that same
distributional score as well as on within Spearman. The pass list is appended below by the
task's read; until then no marker is flagged.

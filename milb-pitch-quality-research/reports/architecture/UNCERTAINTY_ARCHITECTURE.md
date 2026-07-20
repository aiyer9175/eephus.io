# Uncertainty Architecture

Phase 9. Explicit uncertainty propagation design — not simple inheritance, per the charter's instruction.

## Uncertainty sources, by module

| Module | Primary uncertainty source | Magnitude (this research's evidence) |
|---|---|---|
| Module 1 (Stuff) | Sampling (finite pitches per pitcher) | Small — split-half r=0.91-0.99 means measurement noise is low relative to true between-pitcher variance |
| Module 2 (Arsenal) | Sampling + unconfirmed own-reliability | Unknown — the one module where "how uncertain" hasn't been measured at all, only "does it add information" |
| Module 3 (Miss, tracked) | Sampling + genuine unexplained variance | Moderate — split-half r=0.33-0.51, and even the full six-family model only explains 22.8% of its variance |
| Module 4 (Ground-Ball) | Sampling + unconfirmed own-reliability | Unknown, same gap as Module 2 |
| Module 5 (Damage Suppression) | Sampling + near-total unexplained variance + possible confounds (park/defense/luck) | Large and poorly characterized — the least trustworthy uncertainty estimate in this architecture, because even the *sources* of its noise aren't identified, only that "everything tested explains almost none of it" |
| Module 6 (Outcome-only) | Sampling + fundamentally thin information content | Large — R²=0.016 from its only predictor means most of its variation should be treated as noise until shown otherwise |

## Propagation design (not simple inheritance)

The charter's illustrative chain — "Physical Stuff uncertainty → Miss Ability uncertainty → Pitcher Value uncertainty" — cannot be built as naive inheritance here, because Phase 1C's incremental-information findings show the downstream modules are **not** deterministic functions of the upstream ones:

- Module 3 (Miss) is only 22.8% explained by Modules 1-2 combined — 77.2% of its variance is *its own*, not inherited uncertainty from Stuff/Arsenal. A propagation model that treated Module 3's uncertainty as "Module 1's uncertainty plus a little more" would be wrong by a wide margin; the correct model treats Module 3's own split-half reliability (0.33-0.51) as the primary uncertainty figure, with Modules 1-2's contribution as one input among several to what that uncertainty comes from, not a full explanation of it.
- Module 5 (Damage Suppression) is barely related to Modules 1+3 at all (1.9-3.7% R²) — propagating Module 1's high confidence into Module 5 would be actively misleading. Module 5's uncertainty must be estimated on its own terms (once its own reliability is tested — currently a gap), not derived from upstream modules.
- Module 4 (Ground-Ball) is the one case where a meaningful propagated component exists (Movement explains 10.3 of its 13.4 R² points) — here, and only here, is it legitimate to say a meaningful share of Module 4's uncertainty traces to Module 1's Movement component specifically.

**Design rule**: propagate uncertainty from an upstream module to a downstream one *only* in proportion to the measured incremental-R² relationship between them (from `reports/phase1c/INCREMENTAL_INFORMATION_REPORT.md`), never by default inheritance. Where that relationship is weak (Modules 3, 5 vs. their upstream inputs), the downstream module's own directly-measured reliability is the primary uncertainty statement, with upstream propagation as a minor adjustment, not the main story.

## Confidence reporting

Three-tier language, matched to what's actually been measured (no formal CIs exist in this research yet, per `PUBLICATION_ARCHITECTURE.md` — this is reliability-coefficient-based, not bootstrap-based):

- **High confidence** (r>0.9): Module 1.
- **Moderate confidence** (r 0.3-0.6): Module 3 (tracked).
- **Low/insufficient confidence** (r<0.3 or untested): Modules 2, 4, 5, 6 — these should not display a bare number without an explicit "limited evidence" qualifier attached, per `PUBLICATION_ARCHITECTURE.md`'s publication gates.

## Reliability indicators

Directly reuse Phase 1B's split-half/month-to-month reliability coefficients as the reliability indicator for each module, refreshed on the same cadence the module itself refreshes (see `REFRESH_ARCHITECTURE.md`) — not a one-time historical figure frozen at this research's pilot scale.

## Stabilization indicators

Phase 1B's stabilization curves (reliability vs. minimum-pitch-count threshold) directly define the minimum-sample gate each module needs before displaying a pitcher's score — a pitcher below the threshold where a module's reliability curve is still rising should show "insufficient sample" rather than a number with a wide, unstated error bar. This mirrors `swing-plus`'s existing `k=360`-swings shrinkage convention and `sem_plus`/`rem_plus`'s empirical-Bayes shrinkage (`CURRENT_ECOSYSTEM_MAP.md`) — proven patterns in this codebase, not a new invention.

## Observed evidence / Inference / Speculation

The uncertainty-magnitude table is Observed evidence (Phase 1B/1C numbers). The propagation design rule is Inference — a design choice justified by those numbers, not itself an empirical finding. No part of this document is speculation; where evidence is missing (Modules 2, 4, 5's own reliability), that's stated as a gap, not papered over with an assumed uncertainty figure.

## Future work

Formal confidence intervals (bootstrap, matching `sem_plus`/`rem_plus`'s convention) are the concrete next step to bring this research's uncertainty reporting to parity with the codebase's already-validated systems.

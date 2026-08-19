# The conviction program (registered 2026-08-19, owner instruction)

Owner instruction 2026-08-19: find a way to make eFV's Spearman/AUC scores measurably more
accurate than every public source. Under the reopen standard (omnibus-2 s2) this is a named
reopen condition for the SPECIFIC lanes below. It does not repeal EFV_GATE_STANDARD.md; every
lane here inherits it wholesale (paired bootstrap with refit where feasible, zero-information
twin, permutation null band, >=4 time splits, named estimators, two-sided coverage, Holm,
no floor-shopping, no estimator-shopping, no post-hoc frame or arm selection).

## The claim frame (V5), frozen before any measurement

The public claim "eFV is measurably more accurate than every public source" may ship if and
only if ALL FOUR cells below clear, under Holm across the four, each against the BEST public
source on that cell (beating the best implies beating all):

| cell | frame | statistic | estimator |
| --- | --- | --- | --- |
| C1 | hitters, vintage-matched common set | Spearman delta vs best rater | E_cond primary |
| C2 | pitchers, vintage-matched common set | Spearman delta vs best rater | E_cond primary |
| C3 | hitters, debuted_km, contributor label | AUC delta vs best rater | E_cond primary |
| C4 | pitchers, debuted_km, contributor label | AUC delta vs best rater | E_cond primary |

Raters: fangraphs, mlb_pipeline, prospx_consensus. Full-pool AUC stays INADMISSIBLE
(EFV_GATE_STANDARD.md:121-144). E_refit reported beside every cell. Floors are derived on the
measurement frame at measurement time, never reused from another experiment. Partial results
render the partial derived branch (site copy already three-valued); no partial result ships
the headline claim. If the program ends null, the copy stays on the tie frame and this file
plus the lane artifacts are the public receipt.

2026-08-19 baseline (data/source_backtest.json, 2026-08-18 build): C1/C2 delta vs best is
NEGATIVE or inside floor (Pipeline nominally leads eFV pooled vintage-matched on both legs);
C3/C4 margins ran 0.16x-0.74x of their floors at the 2026-08-14 AUC adjudication. The program
attacks delta (model), floor (labels and estimator), and nothing else.

## Lanes

- V1 label pool: docs/efv-2026-08-19/EPOCH_2026_PREREGISTRATION.md (frozen now, runs when
  RESOLVED_THROUGH advances to 2026). Plus a power projection lab NOW (analytic + bootstrap
  scaling of existing floor components to the projected 2025-cohort pool sizes; projection
  only, adjudicates nothing).
- V2 new data: (a) BA backfill recon and, if local, execution for the B-L6 denoised-baseline
  unblock; (b) BA risk ordinal power-check (power BEFORE fit; one resolvable base year);
  (c) new-boards feasibility recon (BP, Law/Athletic, ESPN), identity-resolution cost measured
  first, report-only this cycle.
- V3 model class: docs/efv-2026-08-19/MODEL_CLASS_READJUDICATION_GATE.md (one registered
  attempt, permanent-close pre-commitment).
- V4 consensus-input integrity: verify the two remaining direct-remapper call sites, then
  regenerate the affected evals and re-read every margin (a regen that moves no number is a
  failed regen).
- V5 the claim frame above plus decidability triage: cells that cannot resolve at any feasible
  n are retired from the public-claim family and recorded as retired, not re-reported as fresh
  nulls each cycle.

## Stop clauses (program-wide)

1. No re-run of any of the 39 closed feature arms, in any costume.
2. No blend-lambda movement, direct or via rank_war routing.
3. No sixth correction family.
4. No floor or estimator shopping; the estimator is named in the registration, per cell.
5. Every lane carries its permanent-close pre-commitment inside its own gate doc before its
   lab runs. A lane without one does not run.

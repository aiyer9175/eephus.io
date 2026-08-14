# AUC FLOOR GATE (Lane A-1, 2026-08-14)

Pre-registered 2026-08-14, committed ALONE with the Results section EMPTY so git
timestamps it, BEFORE `tools/efv_auc_floor_lab.py` exists. Clauses are frozen from
this commit. No clause is amended after it answers.

Artifact: `data/xfv_auc_floor_eval.json`. Lab: `tools/efv_auc_floor_lab.py`.

---

## THE QUESTION

`xfv_eval.json` and `xfv_eval_pitcher.json` already publish an `auc_breakdown`
in which eFV beats consensus on **every pooled cell, both sides, both cuts, both
labels**, measured on the fresh 2026-08-14 basis:

| side | cut | label | model | consensus | margin |
| --- | --- | --- | --- | --- | --- |
| hit | debuted_km (n=645) | contributor | 0.7508 | 0.7411 | +0.0096 |
| hit | debuted_km | star | 0.8175 | 0.8112 | +0.0063 |
| hit | full_pool_km (n=1,605) | contributor | 0.8545 | 0.8422 | +0.0123 |
| hit | full_pool_km | star | 0.8943 | 0.8919 | +0.0024 |
| pit | debuted_km (n=766) | contributor | 0.7047 | 0.7007 | +0.0040 |
| pit | debuted_km | star | 0.8462 | 0.8400 | +0.0062 |
| pit | full_pool_km (n=1,695) | contributor | 0.7876 | 0.7680 | +0.0197 |
| pit | full_pool_km | star | 0.9084 | 0.8951 | +0.0133 |

**Nothing adjudicates any of them.** `data/xfv_power_eval.json` `partb_floors`
carries 13 cells and every one is a RANK statistic. The rank gate is
Spearman-only. So the one leg on which eFV appears to lead has never been
floored, while the Spearman legs it is judged on are mixed-sign nulls.

The precedent is not speculative: `consensus_vs_inputs` resolves on AUC
(+0.0116 at 1.48x its 0.0078 floor) and ties on Spearman (+0.0015 at 0.13x).
AUC floors elsewhere in this repo are 0.0052 and 0.0078, roughly a quarter of
the Spearman floors.

## WHY A SEPARATE LAB AND NOT A NEW CELL IN efv_power_lab

`scored_frame` has no pluggable statistic and `frame_delta` hardcodes
`rho(challenger) - rho(baseline)`. Adding AUC would mean changing the core of a
file whose `parity_x1` control exists to prove `frame_delta` is bit-exact
against `delta_of` on 24,000 real draws. **Widening that function to serve a
second statistic invalidates the control that makes every existing floor
trustworthy.** This lab therefore derives AUC floors on its own and writes its
own artifact; `partb_floors` is left untouched.

## CLAUSES

### A0 REPRODUCTION (blocking)

The lab must reproduce all 8 published `auc_breakdown` pooled margins from
`xfv_eval*.json` to within 0.0010 absolute, with every `n` and `n_pos` equal
exactly. FAIL means BLOCKED and no floor is reported: a floor derived on a frame
that cannot reproduce the published margin says nothing about the published
margin.

### A1 ADMISSIBILITY, DECIDED BEFORE MEASURING

`docs/EFV_GATE_STANDARD.md:121-144` already rules **full-pool debut/no-debut AUC
INADMISSIBLE** for any candidate that can sense MiLB-block missingness, because
the no-block indicator is a near-deterministic proxy for the label. That ruling
is inherited here rather than re-litigated:

* **`debuted_km` is the PRIMARY.** Contributor and star AUC on the debuted pool
  are admissible.
* **`full_pool_km` is a SENSITIVITY and can never carry the headline**, even
  though its margins are the larger ones. Stating this before measuring is the
  point: the inadmissible cut is the one that flatters eFV most.

### A2 THE FLOORS

For each admissible cell, MDE95 under BOTH estimators, B=2000, seed 20260814:

* **E_cond** holds the fit and resamples scored rows, clustered by player.
* **E_refit** resamples train and test and refits per draw.

`MDE95 = 1.645 * sd(delta)` one-sided, `1.96 * sd` reported beside it, matching
`tools/efv_mde_lab.py`. Two-sided coverage reported for both; over-coverage
fails exactly like under-coverage.

### A3 MULTIPLICITY

The cells are **NOT independent**: nested labels (star is a subset of
contributor), shared rows, and one shared consensus anchor. **Holm across the
admissible family.** The 8-of-8 sign agreement is NOT 8 independent tests and
may not be quoted as one anywhere, in the artifact or in copy.

### A4 CONTROLS THAT CAN FAIL

* **C-a WEIGHTING.** Every pooled rho in this repo is pair-weighted by
  `observed_seasons/6`; no AUC in the chain is weighted. Report BOTH weighted
  and unweighted AUC. If they disagree by more than the derived floor, the
  weighting choice is doing the work and the cell is reported as undecided.
* **C-b PERMUTATION.** Labels permuted within fold, seeded, sorted integer
  indices. PASS if `abs(AUC - 0.5) < 0.02`.
* **C-c PREVALENCE.** Report `n_pos` per cell. The star cells sit at 96 and 46
  positives; a cell below 40 positives is reported as underpowered by
  construction and not adjudicated.
* **C-d SPEARMAN BESIDE IT.** Every published AUC claim carries its Spearman
  counterpart in the same row. AUC is a co-primary, never a replacement, and a
  reader must be able to see both.

### STOP CLAUSES

1. A0 fails -> BLOCKED, no floors reported.
2. Coverage fails on E_cond -> stop. Do not shop a third estimator.
3. **If the admissible (debuted_km) cells do not resolve, that is the answer.**
   The inadmissible full-pool cells may not be promoted to rescue the lane.
4. This lane derives floors and adjudicates. Copy changes are a separate step
   and must be DERIVED from the artifact, never hardcoded.

## RESULT (appended after the run)

*(empty at pre-registration)*

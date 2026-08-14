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

Run 2026-08-14, `tools/efv_auc_floor_lab.py 2000 2000`, artifact
`data/xfv_auc_floor_eval.json`. No clause amended.

### A0 REPRODUCTION: PASS, all 8 cells

Every published margin, `n` and `n_pos` reproduced exactly.

### THE VERDICT: NULL ON EVERY ADMISSIBLE CELL, UNDER BOTH ESTIMATORS

| cut | cell | margin | E_cond floor | xE_cond | E_refit floor | xE_refit |
| --- | --- | --- | --- | --- | --- | --- |
| **debuted_km (PRIMARY)** | hit contributor | +0.00965 | 0.0131 | **0.736x** | 0.0258 | 0.374x |
| **debuted_km** | hit star | +0.00626 | 0.0123 | 0.509x | 0.0304 | 0.206x |
| **debuted_km** | pit contributor | +0.00403 | 0.0205 | 0.196x | 0.0282 | 0.143x |
| **debuted_km** | pit star | +0.00617 | 0.0397 | 0.156x | 0.0522 | 0.118x |
| full_pool (INADMISSIBLE) | hit contributor | +0.01264 | 0.0142 | 0.890x | 0.0216 | 0.585x |
| full_pool (INADMISSIBLE) | hit star | +0.00271 | 0.0154 | 0.176x | 0.0211 | 0.128x |
| full_pool (INADMISSIBLE) | pit contributor | +0.01967 | 0.0172 | **1.143x** | 0.0252 | 0.781x |
| full_pool (INADMISSIBLE) | pit star | +0.01328 | 0.0330 | 0.402x | 0.0436 | 0.305x |

**No admissible cell resolves under either estimator, and none survives Holm**
(best p 0.113 against alpha 0.0125). Exactly ONE cell crosses anywhere: an
INADMISSIBLE full-pool cell, under E_cond only, and it fails under E_refit at
0.781x. Stop clause 3 forbids promoting it and it is not promoted.

**THE SMOKE RUN WOULD HAVE LIED.** At B=60 `hit.full_pool_km.contributor` read
1.019x and "resolves". At B=2000 it reads 0.890x. A bootstrap sd carries
relative error 1/sqrt(2B), which is 9.1% at B=60, and that alone moved a cell
across the line. **Pre-registering B and honouring it is what stopped a noise
crossing from becoming a finding.**

### AUC IS THE BETTER INSTRUMENT AND STILL RETURNS A NULL

The owner adopted AUC as a co-primary on the hypothesis that its floors are
smaller. Measured, on the same contrast and the same rows (hit, debuted_km):

| metric | margin | E_cond floor | margin / floor |
| --- | --- | --- | --- |
| Spearman | +0.0101 | 0.0204 | 0.495x |
| **AUC (contributor)** | +0.0097 | 0.0131 | **0.736x** |

**AUC raises the margin-to-floor ratio by about 50% and still does not clear.**
The decision was directionally right; the answer is still a null. That is
knowledge, not a failure, and it is the honest outcome of the lane.

### C-b FAILED, AND THE DEFECT IS IN MY OWN CLAUSE

Single-draw permutation returned model AUC 0.4697 hit / 0.4815 pit against a
pre-registered bar of `|AUC - 0.5| < 0.02`. **Hitters FAIL as written.**

The bar is mis-specified. The analytic null SE of AUC is
`sqrt((n1+n2+1)/(12*n1*n2))` = **0.0237 hit / 0.0243 pit**, so the bar sits at
**0.84 SE** and a CORRECT implementation fails it roughly 40% of the time. The
200-draw supplement puts the null at mean 0.5001 (sd 0.0240) and 0.5024 (sd
0.0225), centred on 0.5 and matching the analytic SE, with the observed draw at
the 20th percentile of its own null.

**The clause is frozen and stands as FAILED.** The supplement is evidence about
the machinery, not a rescue, and is labelled as such in the artifact. **No
verdict depends on it**: every admissible cell is a null at 0.15x to 0.74x
whichever way C-b is read. The reusable lesson is the one
`efv_board_serve_probe` already recorded and I re-learned: a single draw of a
null cannot answer whether the null is centred, and a bar set below its own
sampling error is not a control.

### OTHER CONTROLS

C-a: AUC in this chain is UNWEIGHTED while every pooled rho is pair-weighted by
`observed_seasons/6`. Recorded so the asymmetry is visible. C-c: every cell
clears 40 positives (lowest is pit star at 46), so none is refused for
prevalence. C-d: Spearman published beside every AUC cell.

### WHAT THIS MEANS FOR THE CO-PRIMARY DECISION

The AUC leg is now floored, adjudicated and honest for the first time. It says
eFV leads on every cell in SIGN and on none in RESOLUTION. Site copy may
therefore say eFV and the consensus are indistinguishable on discrimination as
well as on ordering, and may NOT say eFV discriminates better. Any copy change
is derived from this artifact.

# BUCKET-AGE-HEAD pre-registered calibration gate -- VERDICT: **FAIL**

Run 2026-07-15. Seed 20260715, 2000-rep bootstraps, fully deterministic.
Design run EXACTLY as pre-registered: pit-only p(bucket | grade_band,
age_band), age bands <=22 / 23-24 / 25+, existing 5-point grade bands,
partial pooling toward the incumbent row with weight n/(n+25), fit on the
resolved labeled pitcher matrix, forward-chained folds 2020-2023 fit strictly
pre-fold, incumbent `p_bucket_given_fv` untouched.

Three of four gates pass decisively; the head fails the grade monotone-sanity
gate, and a post-hoc ablation shows the measured gains are not age signal.
Per the pre-registration (ALL must hold; marginal = FAIL), **no ship**.

## Gate results

| Gate | Condition | Result | Numbers |
|---|---|---|---|
| G1 | pooled multiclass log-loss <= incumbent (folds 2020-2023) | **PASS** | 0.36184 -> 0.30733, delta -0.05451, CI90 [-0.0615, -0.0473], P(delta<=0)=1.000 |
| G2 | E-ISO4 guard: pit BENCH and GOOD log-loss <= +1.0% rel | **PASS** | bench -11.2% rel (0.20339 -> 0.18062); good -17.0% rel (0.04431 -> 0.03677); both CI90 fully below 0 |
| G3 | age-25+ subset log-loss improves | **PASS** | n=90: 0.36661 -> 0.28004, delta -0.08657, CI90 [-0.0994, -0.0735] |
| G4 | valid distributions AND monotone-sane in grade per age band | **FAIL** | distributions valid (sum 1, all >=0); monotonicity: 12 band-seam stochastic-ordering violations, worst **+0.076** |

**G4 detail.** Crossing INTO the fv35 band at grade 32.5->32.75, P(bust) JUMPS
UP in all three age bands (+0.076 / +0.070 / +0.061): below the fitted support
the head serves the incumbent (bust ~0.89 at fv32.5), while the fv35 cells are
all-bust empirical (n=31-55) shrunk only partially back. A higher grade
getting strictly worse odds violates the grade-monotone constraint the head
was required to stay below. Further seams at 37.5 (+0.016), 47.5 (+0.016),
52.75, 62.75, 67.5, 72.75 (thin n=1-8 cells). The piecewise cell structure
cannot preserve grade stochastic ordering when cell empiricals sit far from
the incumbent curve; this is structural, not a tuning miss.

## The deeper (post-hoc, non-gate) finding: the gains are not age

A covariate-free ablation (grade-band-only head, identical n/(n+25) pooling,
identical folds, same 524 eval rows) DOMINATES the registered age head:

| pooled log-loss | incumbent | grade-band-only | age head |
|---|---|---|---|
| all 524 eval rows | 0.36184 | **0.17907** | 0.30733 |
| age-known subset (n=291) | 0.43266 | **0.26921** | 0.33450 |
| age-25+ subset (n=90) | 0.36661 | **0.21162** | 0.28004 |

The G1/G3 passes are population-level recalibration: the incumbent
(Clemens published-list population) is far too optimistic for the resolved
matrix pool (fv45 pit band pooled empirical bust ~0.87 vs incumbent 0.51),
so ANY shrink toward pool empiricals wins log-loss. That effect class is
exactly what the CLOSED grade-monotone calibration line (X-ISO/E-ISO2/3/4)
already established as blocked. Caveat recorded in results.json: the ablation
comparison is confounded by coverage (age head only fires on the 40%
age-known rows) and by shrink strength (small age cells keep 24-84% incumbent
weight vs ~93-97% empirical for the big grade cells), so it is not a clean
"age has zero signal" estimate -- but the registered design being dominated
by its own ablation stands.

G2's pass carries a population caveat too: this pre-registration fixed the
RESOLVED-only frame, where realized bench/good frequencies are low and
cutting bench/good mass is rewarded; it does not contradict the E-ISO4
pit-BENCH blocker, which was measured on the KM full pool.

## Moore report (required)

- Registered motivation: published p_bust 0.388 vs band-empirical 0.81.
  Incumbent p_bust(48.0) = 0.388 exactly -- the published figure keys to his
  PRE-overlay grade ~48. His current live grade is 45.8 (incumbent 0.476
  after the age/role overlays already shipped this week).
- Head at his cell (grade 45.8 -> band 45, age 26.9 -> 25p):
  **p_bust 0.542** (vs incumbent 0.476 at 45.8; at the registered grade 48.0
  the head gives 0.545 vs incumbent 0.388).
- The claimed band-empirical **0.81 does not reproduce** under the lab's
  conventions: the fv45/25+ cell is n=8, empirical p_bust **0.750**, shrink
  weight 0.242. And inside the fv45 band the age gradient runs the WRONG way
  for the motivation: mean realized WAR6 0.51 (<=22) / 1.70 (23-24) /
  2.51 (25+); bust 0.918 / 0.828 / 0.750. The within-band age-bust story is
  real at fv40 (25+ bust 0.988, n=81) but not at Moore's band. n=84 in the
  motivation matches the fv45 age-known band population (n=86 here), so the
  workflow-report numbers appear to describe a slightly different convention
  and, at fv45, older-is-BETTER on resolved outcomes.

## Honest caveats on the eval frame

- Resolved-only folds make 2021-2023 bust-only cohorts (debut 2021+ are
  censored); only the 2020 fold (104 debuted / 100 busts) tests non-bust
  discrimination. Per-fold deltas all favor the head (-0.041/-0.033/-0.060/-0.076).
- Age is recoverable for only 623/1569 fit rows, and missingness correlates
  with outcome (busts are 72% of age-missing vs 58% of age-known rows); live
  serve rows always have age -- an unpriced train/serve mismatch.

## Disposition

**NO SHIP.** Loss ledger embedded in results.json. Incumbent
`p_bucket_given_fv` stays untouched in production. Candidate wiring preserved
in `patched/` (verified: incumbent output byte-identical, head reproduces the
lab to 2e-16; see PATCH_NOTES.md).

**Mandatory re-run marker (F-SIDE S5 tripwire pattern, stamped in
results.json and in the head artifact):** the FIRST pipeline run where the
2024 decision fold becomes trainable in the DEBUTED frame (resolved
censored==False debuted rows with decision_year 2024; the bust-only full-pool
2024 cell does not count) trips a named re-run of BUCKET-AGE-HEAD under these
same gates before the head may ship or baselines reset -- that is also when
the Moore-class RP-role cohort first becomes gateable. Any redesign (e.g.
hierarchical shrink toward the grade-band empirical with per-age-band
isotonic-in-grade repair, or a serve-population-matched frame) requires fresh
pre-registration.

## Deliverables

- `results.json` -- full artifact: design echo, pool/fold diagnostics, all
  gate numbers, 2000-rep bootstrap CIs, per-fold/per-band blocks, Moore block,
  production head cells, post-hoc ablation, loss ledger, rerun marker.
- `SUMMARY.md` -- this file.
- `patched/value_framework.py`, `patched/efv_score.py`,
  `patched/data/xfv_bucket_age_head.json` -- candidate implementation (DO NOT SHIP).
- `PATCH_NOTES.md` -- wiring + verification detail.
- Reproduction: `gate_lab.py` (the gate), `diag_ablation.py` (ablation),
  `finalize_results.py`, `verify_patch.py`, `profile_pool.py`;
  `eval_rows_ckpt.json` (fold-eval checkpoint).

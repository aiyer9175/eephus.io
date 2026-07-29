# P1 — provisional pedigree prior — pre-registered gate (2026-07-19)

Registered BEFORE the arm is run at the canonical matrix vintage (program rule:
metrics + thresholds declared up front; loser or winner, the result is committed).

## What the arm does

For a fresh draftee with **no MiLB track record yet**, `efv_score` currently grades
on the CONSENSUS prior alone (the `not row["milb"]` branch: `xfv_war = cons_war`),
discarding the `pick_overall` / `bonus_usd` already carried in-row. A high-pedigree
top pick therefore reads identically to a fringe consensus-FV twin (the
Cholowsky / Gracia case).

P1 replaces that prior with a **precision-weighted blend** of the shipped draft-slot
first-6 WAR curve (`storage._pick_slot_expected_war`, the `first6_step_curve`) and the
consensus WAR:

```
prior_war = w · slot_war + (1 − w) · cons_war
w         = pedigree / (pedigree + base_precision)
pedigree  = pick_tier_precision + bonus_log_precision          (capped at 3.0)
          = {top10 .8 | round1 .4 | round2 .15 | later .05}
            + max(0, log10(bonus / $10k)) · 0.5
```

Bonus adds **trust (a weight), never a WAR value** — it is dimensionless precision,
so it is never summed as WAR (that would be a units error). IFA / no-pick rows keep
`cons_war` (no WAR expectation is invented from a bonus alone). Config:
`efv_provisional_prior` in `value_framework_config.yaml`; `enabled: false` until this
gate passes. With the flag off the branch is byte-identical to today.

## Why this is LOW risk

No provisional (no-MiLB-track-record) player is in the flagship forward-chained
rank/AUC eval — that eval scores resolved cohorts with track records. So P1
**cannot move the flagship pooled-OOS Spearman / MAE / contributor-AUC**. The gate is
therefore a **directional-sanity + no-regression** check, not a rank-improvement claim.

## Gate (ALL clauses required to ship — challenger-beats-champion rule)

Run at the CANONICAL matrix vintage (box or seeded dev env), not the restored-from-git
local vintage. Compare the served eFV grades for the affected provisional cohort
(picks present, no MiLB rows) OFF vs ON.

1. **Flagship untouched (hard invariant):** the forward-chained pooled-OOS Spearman,
   MAE, and contributor-AUC on the resolved eval are **identical** OFF vs ON
   (bit-for-bit — provisional rows are not in that eval). Any change ⇒ the wiring
   leaked into the flagship path ⇒ FAIL, do not ship.
2. **Monotonic in pedigree:** within the affected cohort, holding consensus FV fixed,
   a better pick (lower `pick_overall`) and/or larger bonus yields a
   `prior_war` that is **≥** a worse pick's (weakly increasing). Spot-checked on the
   real cohort; any inversion ⇒ FAIL.
3. **Bounded pull:** no provisional grade moves by more than the shipped grade band
   width (≤ ~5 FV points on the 20-80 scale) purely from the prior for a pick worse
   than #1; i.e. the blend does not overpower consensus for non-elite picks. A pick-1
   / max-bonus row may approach the slot expectation; later picks barely move.
4. **Cholowsky/Gracia sanity:** the specific high-pedigree cases the audit named move
   UP relative to their consensus-only grade (directionally correct), and no
   low-pedigree consensus twin moves up.
5. **Distribution sanity:** the provisional cohort's grade distribution does not
   develop an implausible spike; the count of grades ≥ 55 rises by ≤ the number of
   genuine top-2-round picks in the cohort.

PASS all five ⇒ flip `enabled: true`, regenerate `data/xfv.json` on the box, owner
restamp the served grades. Fail any ⇒ committed loss; the code stays, the flag stays
off, this file records the result.

## Committed-loss note

If P1 fails clause 2–5 (a real modeling defect) the flag stays off and the loss is
recorded here. Clause 1 failing means the WIRING is wrong (a bug), not a modeling
loss — fix the leak and re-gate.

## Harness

`tools/efv_provisional_prior_lab.py` — runs clauses 2-5 (clause 1 is a separate
`efv_model.run` OFF-vs-ON bit-identity check). Artifact:
`data/xfv_provisional_prior_eval.json` (do NOT commit a copy produced on a degraded
matrix). The lab ABSTAINS (not FAIL) when it detects a degenerate `target_censored`
column, so a degraded-vintage run cannot be mistaken for a loss.

## Units basis (verified 2026-07-19 — do not break)

Both blend terms are **6-season-TOTAL WAR**: `cons_war = _pred_ols(ols, cons_fv)` is
the OLS on `target_censored`, which `efv_dataset` builds over a `TARGET_SEASONS=6`
window; `storage._pick_slot_expected_war` returns the `first6_step_curve`, also
6-season-total WAR. So the blend is on one consistent axis and feeds
`rank_war`/`realized_implied_fv` unchanged (documented in the helper docstring). If
either basis ever moves to per-season, the other must be rescaled or grades shift ~6x.

## RESULTS

- **2026-07-19 (local, PRELIMINARY):** ABSTAIN. The restored-from-git dev matrix has an
  all-zero `target_censored` column, so the consensus-WAR OLS baseline collapses to ~0
  and OFF-vs-ON is not measurable here. The harness runs end-to-end and abstains
  correctly. **Re-run on the canonical matrix (box / seeded dev env) for a real verdict.**
- **2026-07-23 (V1, non-degenerate local matrix): FAIL, committed loss, flag stays off**
  (`data/xfv_provisional_prior_eval.json` at that date; registry `xfv_provisional_prior`
  verdict deprecated). Clause 1 bit-identity PASSED (wiring clean); clauses 2/3/4 FAILED.
  Root causes named in the loss ledger:
  - **(A) top-pick pull unbounded:** the slot curve pays 8.49 WAR at pick 4 vs cons_war
    ~0.5-1.0 for an FV-40 arm; with w ~0.44-0.69 the slot leg overpowers consensus
    (Asa Lacy +11.3 FV vs the 5.0 bound; Kohl Stewart +7.3).
  - **(B) degenerate consensus floor:** the consensus OLS floors at 0.0 WAR for the
    FV 35-38 mass, so ANY positive slot WAR (0.776 past pick 110) rides the steep
    display-band grade map (86/358 low-pedigree risers +2.3 to +3.3).
  Independent support kept on record: the 804-draftee backtest validated the DESIGN
  direction (ARM-P +0.026 CI-clean; slot-alone worse; the tools arm is dead, do NOT
  add tools).

---

# P1 V2 re-registration (2026-07-23, owner-approved)

Registered BEFORE the V2 arm is run (same program rule). The V2 changes target the two
named V1 defects (A) and (B) and nothing else: the pedigree-precision weights, the
pick tiers, the bonus-log trust term, and the flag plumbing are all UNTOUCHED from V1.

## V2 formula (the no-MiLB-track-record draft branch)

```
mix6_war = TARGET_SEASONS * vf.expected_six_year_avg_war(cons_fv, is_pitcher)
ref_war  = max(cons_war, mix6_war)                     # Fix B: non-degenerate baseline
pull     = clip(slot_war - ref_war, 0, PULL_CAP_WAR)   # Fix A: bounded, upward-only
prior    = cons_war + w * pull                         # w = V1 pedigree weight, untouched
```

Equivalently in the V1 blend algebra: `slot_war_eff = cons_war + pull` and
`prior = w*slot_war_eff + (1-w)*cons_war`, i.e. the owner-specified
`slot_war_eff = cons_war + min(slot_war - baseline, PULL_CAP_WAR)` with the degenerate
baseline replaced per Fix B and the pull floored at 0. When `cons_fv`/`is_pitcher` are
unavailable (defensive only; both production call sites pass them) the baseline
degrades to `cons_war` (capped V1). Flag OFF remains byte-identical (early return
before any of this).

### Fix A: PULL_CAP_WAR = 1.9, derivation (frozen, no post-hoc adjustment)

The clause-3 bound is 5.0 FV on the DISPLAY grade, so the cap must be derived through
the served grade map (efv_score._build_grade_map on the 2026-07-23 live scored pools:
hit 1937 knots spanning rank_war -1.40..11.33 / grade 35..65; pit 2247 knots,
-1.04..7.58 / 35..62). Define the worst-case map move
`Delta_s(d) = sup_x [G_s(x+d) - G_s(x)]` (measured on knots + a 400-point grid):

- largest d with Delta_hit(d) <= 5.0:  d*_hit = 1.226 WAR
- largest d with Delta_pit(d) <= 5.0:  d*_pit = 0.7435 WAR

The maximum rank_war shift V2 can produce is `lam * w_max * PULL_CAP_WAR` with
lam_hit = 0.70, lam_pit = 0.52 (blend_lambda at registration) and
w_max = ped_cap/(ped_cap+base) = 3.0/4.0 = 0.75. Therefore:

```
PULL_CAP_WAR <= min( d*_hit/(0.70*0.75),  d*_pit/(0.52*0.75) )
             =  min( 2.335,               1.906 )              ->  FROZEN 1.9
```

(1.906 rounded DOWN for margin; pit worst shift 0.52*0.75*1.9 = 0.741 <= 0.7435.)
This bounds EVERY row, every base point, pick 1 included (stricter than clause 3,
which exempts pick 1). No down-moves exist (pull >= 0), so |delta| = delta.

### Fix B: the bucket-mixture baseline (frozen function choice + form)

`vf.expected_six_year_avg_war(fv, is_pitcher)` is the calibrated bucket-mixture
expectation (P(bucket|FV) x calibrated midpoints x war scale), bust-inclusive, the
same core the surplus model prices on; times TARGET_SEASONS = 6 it is on the P1
6-season-total axis (units invariant preserved). Measured at registration:
mix6 in [1.111, 1.170] WAR across FV 35..40 on both sides, FV-monotone at band scale.
Consequences, derived a priori from the frozen slot table:

- slot(pick>150) = 0.65/0.553/0.203 and slot(101-150) = 0.776 and slot(76-100) = 1.073
  are ALL below min(mix6) = 1.111, so at FV < 40 every pick past 75 carries ZERO pull:
  the entire V1 defect-(B) riser cell (86 rows, picks 86-500) is dead by construction.
- the worst low-pedigree cell still alive is picks 71-75 (slot 1.482) with bonus at the
  $1M low-ped boundary: shift <= lam * 0.512 * (1.482-1.111) = 0.133 (hit) / 0.099
  (pit). From the OLS-attainable low-FV bases the maps move +0.6 FV (hit; band edge at
  x=0.222) and +0.0 FV (pit; the 35->37.4 cliff starts at x=0.14), inside the +2.0
  clause-4 bar.

**Rejected alternative, recorded at registration (not post-hoc):** replacing the
consensus LEG wholesale (`cons_leg = mix6` for FV < 40) was rejected in derivation:
the level shift lam*mix6 (0.80 hit / 0.59 pit WAR) maps to +2.3/+5.0 FV for
ZERO-pedigree rows through the display-band cliffs, mechanically failing clause 4;
and the mix6 sawtooth (a period-1-FV wiggle, range ~0.06 WAR, from the shipped
war-scale interpolation) would print cross-FV grade inversions. The mixture therefore
enters ONLY as the pull baseline (the registered purpose: a nonzero, FV-monotone
floor so tiny slot WAR cannot dominate a degenerate zero); re-anchoring the served
LEVEL of the provisional cohort is the provisional display penalty's territory
(provisional_calibration), not P1's.

The upward-only clip is likewise required by clause 2: with a trusted BELOW-baseline
slot expectation the prior would DECREASE in pedigree (more weight w on a negative
pull), which the pedigree partial order forbids; V1's symmetric blend carried this
structural inversion channel.

## V2 clauses (numbers per the original registration; clause-4 riser bound per the
## owner's V2 instruction; ALL required to flip the flag)

1. **Flagship untouched (hard invariant):** `efv_model.run(persist=False)` OFF vs ON,
   both sides: pooled-OOS Spearman, MAE, and contributor-AUC blocks bit-identical.
2. **Monotone in pedigree:** within EXACT consensus FV, for every pair with
   `pick_i <= pick_j` AND `bonus_i >= bonus_j` (missing bonus = 0, matching the model),
   `grade_on_i >= grade_on_j - 1e-6`. OPERATIONALIZATION FIX, registered here: the V1
   lab sorted rounded-FV buckets on pick alone, comparing incomparable pedigrees
   (different bonuses / different exact FV inside one rounded bucket); V2 tests the
   registered clause (the pedigree partial order) faithfully. Not a weakening: every
   comparable pair is still required to be monotone at the same 1e-6 tolerance.
3. **Bounded pull:** no provisional grade moves more than 5.0 FV for any pick > 1
   (V2's construction bounds pick 1 too).
4. **Directional sanity:** the named live movers (roch_cholowsky pick 1/$10.35M
   FV 57.58; aj_gracia pick 9/$4.0M FV 46.7) move UP vs their consensus-only grade;
   NO low-pedigree row (pick > 70 and bonus <= $1M) moves up more than +2.0 FV.
5. **Distribution sanity:** FULL-cohort tally (V1 lab only spot-checked top_moves):
   every row crossing to grade >= 55 ON must be a genuine top-2-round pick
   (pick <= 70), and the count of new >= 55 grades is <= the number of top-2-round
   picks in the cohort.

Run vintage: the same 2026-07-23 local matrix the V1 FAIL was measured on
(target_censored non-degenerate: hit max 47.54, pit max 41.40; hit pool 1892 /
pit pool 2002). The canonical-box re-run note from V1 stands for the flip on the box.

PASS all five: flip `efv_provisional_prior.enabled: true`, movers list committed in
the eval artifact, registry row -> provisional (shipped V2), `data/xfv.json`
regenerated on the box, owner restamp. Any fail: flag stays false, honest RESULTS,
loss ledger.

---

# IFA $1M-step arm (registered 2026-07-23, BEFORE the validation run; wiring
# STRICTLY conditional on the P1 V2 flip)

From the `ifa_pedigree` loss ledger (data/ifa_pedigree_eval.json, seed 20260723): the
7-tier bonus curve FAILED its LOO gate (pooled rho 0.0407, lo95 < 0) and sub-$1M
bonus rank carries zero-to-inverted information (the $10-50k tier outperforms the
$100-250k tier). The ONE robust structure is the >= $1M step: realized window-WAR
mean 1.717 (n=142) vs 0.182 (n=1,387), boot CI95 on the diff [0.653, 2.62]. That
ledger's own finding: a >= $1M-only arm is a NEW experiment needing its own
pre-registration. This is that registration.

## Integration formula (draft-branch rails reused verbatim)

In `_provisional_prior_war`'s IFA branch (no overall pick), for
`bonus_usd >= ifa_step_bonus_usd` ($1,000,000, frozen):

```
pull_ifa = clip(ifa_step_war - ref_war, 0, PULL_CAP_WAR)     # same Fix A/B rails
prior    = cons_war + w_ifa * pull_ifa
w_ifa    = ifa_step_precision / (ifa_step_precision + base_precision) = 0.25/1.25 = 0.2
```

- `ifa_step_precision = 0.25`, frozen A PRIORI: below draft round-1 (0.4) and far
  below top-10 (0.8); an IFA bonus is softer information than a draft slot (the
  PROPOSED_DIFF's deliberate stance, kept).
- `ifa_step_war` = the >= $1M group's FIRST6-basis mean from the validation cohort
  (the units-correct twin of the realized step mean; first6 = the P1 blend axis).
  Frozen from the validation artifact BEFORE the eFV-side movers are computed.
- Sub-$1M / missing-bonus IFA rows: `return cons_war` unchanged, bit-identical (the
  ledger's "no WAR from a bonus alone" stands below the boundary, with evidence).
- Max shift = lam * 0.2 * PULL_CAP_WAR = 0.266 (hit) WAR: <= 5 FV through both maps
  (bounded-pull clause satisfied by the same Delta_s derivation, Delta_hit(0.27)=2.4).
- High-FV IFA rows (posted pros, e.g. roki_sasaki FV 65) get pull 0 by construction
  (ref_war >> ifa_step_war): the constant can only lift LOW-FV big-bonus signees.

## Validation (the gate; run whether or not P1 V2 flips)

The ifa_pedigree lab's LOCO-by-class protocol (identical cohort build: Spotrac
classes 2012-2017, same dedup/matching/QA amendments, seed 20260723), restricted to
the step boundary:

- **LOCO folds:** leave one signing class out (6 folds). Per fold, fit the two-level
  means (>= $1M vs < $1M) on the 5 training classes; DIRECTION STABILITY clause: the
  training hi-mean must exceed the training lo-mean in ALL 6 folds ("monotone in the
  step" at the fit level).
- **Pooled step-boundary read (THE gate):** pooled held-out mean difference,
  mean(outcome | bonus >= $1M) - mean(outcome | < $1M), window basis (sign+2..sign+8,
  the protocol's primary outcome), bootstrap CI95 with numpy RandomState(20260723),
  10,000 resamples: **PASS requires lo95 > 0.**
- **Wiring units clause:** the same read on the FIRST6 basis (the constant actually
  consumed) must ALSO have lo95 > 0, else no wire even on a window-basis pass.
- **Reported, never gating (protocol-inherited):** pooled held-out Spearman of the
  two-level prediction + CI; per-class held-out diffs; posted-pro-excluded
  (Japan/South Korea/Taiwan) sensitivity; Cuba split; first6 2012-2014-only
  (censoring) sensitivity.

Artifact: `data/ifa_step_prior_eval.json` (committed win or lose).

## Wiring decision rule (frozen)

`ifa_step_enabled: true` ONLY IF (P1 V2 clauses 1-5 all pass) AND (window-basis
lo95 > 0) AND (first6-basis lo95 > 0) AND (direction stable in all 6 folds).
Any other outcome: `ifa_step_enabled` stays false, results recorded as a ledger,
no consumer (the P1 flag OFF path never reaches the IFA step code).

## V2 RESULTS

**2026-07-23 (same-day as registration, run AFTER the freeze; 2026-07-23 local
matrix, target_censored non-degenerate): ALL FIVE CLAUSES PASS. Flag flipped
`enabled: true`. IFA step validation ALSO passed; step WIRED
(`ifa_step_enabled: true`, `ifa_step_war: 1.917`).**
Artifacts: `data/xfv_provisional_prior_eval.json` + `data/ifa_step_prior_eval.json`.

- **Clause 1 (flagship bit-identity): PASS.** `efv_model.run(persist=False)` OFF vs
  ON, both sides: evals + era split + lambda calibration + feature diagnostics
  compared as canonical JSON, IDENTICAL (hit 18,212 bytes, pit 18,194 bytes).
- **Clause 2 (monotone, pedigree partial order, exact FV): PASS.** Zero violations.
- **Clause 3 (bounded pull): PASS.** Max |delta| = 5.0 FV (pit, at the derived cap,
  e.g. ryan_jensen pick 27 FV 37.66: 35.0 -> 40.0), hit max 3.3. Nothing exceeds
  the band. The V1 blowups are contained: asa_lacy +11.3 -> +2.7 (40.0 -> 42.7),
  kohl_stewart +7.3 -> inside the band.
- **Clause 4 (directional): PASS.** Named live movers UP: roch_cholowsky (pick 1,
  $10.35M, FV 57.58) 56.1 -> 58.01 (+1.91); aj_gracia (pick 9, $4.0M, FV 46.7)
  45.0 -> 47.3 (+2.30). Low-pedigree max riser +0.6 FV (exactly the a-priori
  derivation's bound for the picks-71-75 cell), under the 2.0 bar. Risers 29/358
  (V1: 86/358); every one is pedigree-driven; downward moves are impossible by
  construction (upward-only pull).
- **Clause 5 (distribution, full-cohort tally): PASS.** Grades >= 55: 2 OFF -> 3 ON;
  the single crosser is reid_detmers (pick 10, 53.07 -> 57.14), a genuine
  top-2-round pick; bound was 63.
- **Sub-$1M IFA invariance: PASS.** All 14 no-pick provisional matrix rows (every
  one sub-$1M) bit-identical OFF vs ON.

### IFA $1M-step validation results (frozen gate, seed 20260723)

- **Pooled step-boundary read (THE gate), window basis: PASS.** hi 1.717 (n=142) vs
  lo 0.182 (n=1,387), diff **1.535, CI95 [0.653, 2.62]**, lo95 > 0.
- **Wiring units clause, first6 basis: PASS.** hi 1.917 vs lo 0.320, diff **1.597,
  CI95 [0.710, 2.631]**, lo95 > 0. Consumable `ifa_step_war = 1.917`.
- **Direction stability: PASS.** Train hi > lo in all 6 LOCO folds; every held-out
  class diff positive (2012 +0.305, 2013 +1.026, 2014 +0.424, 2015 +2.017,
  2016 +1.170, 2017 +2.952).
- Reported (never gating): held-out two-level predictor pooled Spearman 0.0301,
  CI95 [-0.0268, 0.0844] (the rank read stays weak, as the ifa_pedigree ledger
  found; the step is a MEAN effect, which is what the prior consumes);
  posted-pro-excluded diff window 1.222 / first6 1.377 (still CI-clean scale);
  Cuba split hi-lo +2.231 (n 27/27); first6 2012-2014-only diff +0.847
  (censoring-conservative, still positive).
- **Wiring decision (frozen rule): WIRE.** P1 V2 passed AND window lo95 0.653 > 0
  AND first6 lo95 0.710 > 0 AND direction stable 6/6. Config now carries
  `ifa_step_enabled: true`, `ifa_step_war: 1.917`.
- Live IFA movers with the step wired: fabricio_blanco ($1.0M, FV 42.66)
  42.3 -> 42.7 (+0.4); jose_luis_acevedo ($2.3M, FV 40.0) 40.0 -> 40.0 (flat
  display band); roki_sasaki-class posted pros: pull 0 by construction (high FV).

### Post-flip operational notes

- Served artifacts (`data/xfv.json`, `data/xfv_history.json`) move on the next
  box regen: the provisional cohort only (run_backgrade + score_history paths).
  Owner restamp of the golden applies, per the standing rule for served-number
  changes. The flagship eval artifacts do NOT move (clause 1).
- Registry: `xfv_provisional_prior` -> provisional (shipped V2); new row
  `ifa_step_prior` (the step arm's own ledger + ship record).
- The canonical-box note stands: re-run this lab on the box vintage as a
  confirmation read; the clause structure (bounded by construction) is
  vintage-robust, but the committed artifact should be the box's.

---

## V3 registration (2026-07-23, owner directive: the Grady Emerson case)

Owner ask (verbatim intent): Emerson (2026 pick 2, TBR) serves 49 eFV / #114 despite elite
draft pedigree; verify the pedigree calculation; consider DS+ (Draft Stock+), signing bonus,
draft slot, or a combination. Registered BEFORE any V3 arm runs.

Verified mechanism state (diagnosis, recorded): V2 executes correctly to the digit for this
row. cons_war 3.67 (single-source anchor: FG trade-deadline 55 normalized to 48.3), slot_war
(pick 2) 8.49, raw pull 4.8+ capped at 1.9, pedigree 0.8 (top-10 pick) with ZERO bonus trust
because bonus_usd is null (live StatsAPI confirms pick 2 unsigned as of 2026-07-23), so
w = 0.444 and credit = 0.844 (the served factor mag 0.84). Signed at slot he would carry
w = 0.698, credit = 1.326. The three binding constraints: (i) train/serve bonus-trust skew
for unsigned current-class picks (training rows nearly all carry real bonuses; live unsigned
rows carry none - the _TOOL_IMPUTE bug class); (ii) the multi-source draft-board pedigree
(ESPN rank 2 / Pipeline rank 1, FV 60/65) never reaches the active-board anchor; (iii) the
a-priori pull cap 1.9 binds. The cap and the tier precisions are registered constants and are
NOT retuned in V3.

ARM-A slot-trust imputation (correctness class, the _TOOL_IMPUTE precedent): where
bonus_usd is missing AND draft_results carries slot_usd for the pick AND the pick is a
current-class selection not yet signed, the bonus log-trust term consumes slot_usd in place
of the bonus. Upward-only by construction (w rises, pull >= 0). Bars:
- A1: 804-draftee-class resolved backtest, delta Spearman vs the V2 baseline lo95 >= -0.005
  (no-harm bar; the target population is live-skewed so a gain is not claimable there).
- A2: live move battery: movers restricted to missing-bonus drafted rows, every move upward,
  max served xfv_grade_quantile move <= 3.0 FV (standing ceiling).
- A3: flag-OFF bit-identity.

ARM-B DS+ pedigree precision: ped += 0.4 * max(0, (DSplus - 100) / 10), DSplus = the
class-normalized Draft Stock+ recomputed from pre-draft draft_snapshots via the draft_export
rank-consensus path (pre-signing information only); rows without a computable DSplus are
unchanged. The 0.4 scale and the /10 normalization are a-priori round choices, frozen here.
Existing max_pedigree_precision 3.0 still caps. Bars:
- B1: resolved-backtest delta Spearman vs V2 lo95 > 0 on the DSplus-covered subcohort
  (draft boards backfilled 2018+, so coverage is late-cohort; report n) AND pooled-804
  no-harm lo95 >= -0.005.
- B2: monotonicity: prior non-decreasing in DSplus within pick tier (any inversion = FAIL).
- B3: served ceiling 3.0 FV; B4: flag-OFF bit-identity.
- STOP-B: if the DSplus-covered resolved subcohort has n < 60, verdict COVERAGE-STARVED,
  arm stays OFF, keep-alive keyed to 2020+ draft classes resolving.

ARM-C = A + B combined, judged under B's bars (plus A2's battery).

Seed 20260723, 2000 bootstrap reps, one attempt per arm. Ship rule: ARM-A may ship alone as
a train/serve correctness fix on A1+A2+A3; ARM-B/C ship only on B1 (and their batteries);
flips + regen + post-flip battery run centrally; env flags EEPHUS_P1_SLOT_TRUST and
EEPHUS_P1_DSPLUS, both default OFF until then. Artifact: data/xfv_provisional_prior_eval.json
gains a v3 block (companion convention on the existing xfv_provisional_prior registry row).

### V3 RESULTS + flip record (2026-07-23)

- ARM-A slot-trust: A1 PASS (delta -0.00045, CI95 [-0.00126, 0.0] vs no-harm bar -0.005;
  near-null by construction, only 2 resolved slot-imputable rows - the registration
  anticipated this), A2 PASS (10 in-process movers, all current-class missing-bonus, all
  upward, max +2.3), A3 PASS (bit-identity on 804 backtest + 209 live rows).
  SHIPPED: default ON in efv_score (_p1v3_defaults), env override wins both directions.
  Post-flip SERVED battery (full regen ON vs OFF diff): 12 movers, all upward, max +2.3
  <= 3.0 ceiling (the 2 extras are sub-0.3 display-map neighbor nudges); restore-regen
  determinism 0 diffs. Emerson 48.6 -> 50.2 (war 4.51 -> 4.99, credit 0.844 -> 1.326).
  Self-expiring: as the class signs, the imputable set empties and the flag no-ops.
- ARM-B DSplus: B1 FAIL (covered n=294, delta -0.0016, CI95 [-0.0077, +0.0030], p_gt0
  0.294; pooled no-harm passed but the gain bar is the ship bar). B2/B3/B4 passed, moot.
  Reading: rank-consensus pedigree beyond pick tier + bonus is already priced (matches
  the V2-era tools-arm-dead finding). Keep-alive: 2020+ classes resolving.
- ARM-C: FAIL under B's bars (CI95 [-0.0085, +0.0029]). Stays OFF.
- Golden note: local tree runs under the standing local-only directive; the dev golden
  fingerprint remains the expected env-class failure and restamps on the box regen.

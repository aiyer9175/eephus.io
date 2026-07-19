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

## RESULTS

_Pending the canonical-vintage run on the box._

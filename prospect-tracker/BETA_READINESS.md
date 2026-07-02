# Beta Readiness (go/no-go)

Launch: 2026-07-11. Curated checklist. Legend: [x] verified, [ ] open.

## VERDICT (2026-07-02): GO, conditional on the three owner actions below

Everything code-side is done, verified and pushed: three audit waves, an
adversarial verification pass over the full diff (no P0 findings, every P1/P2
fixed), four gated model experiments honestly rejected with loss ledgers, one
new validated metric shipped (gmLI 3yr), and the full gate battery green. The
remaining launch risk is entirely in the owner actions (production deploy,
automation secrets, payload size) and the ordinary pre-launch data refresh.

## Data freshness

- [x] Daily pipeline green: latest daily run completed clean 2026-07-02
      (timeseries generated_at 2026-07-02T17:39Z; timeseries.json is
      untracked by design, owned by the pipeline).
- [x] Model registry: 47 rows, validate() clean (see MODEL_REGISTRY.md,
      generated from the same file).
- [ ] Monthly run lands before launch with this pass's pipeline additions in
      (6b4b gmLI refresh, generated-docs regen after registry restamps;
      draft/pipeline fixes only reach tracked draft_timeseries.json on the
      next rebuild).

## Test + artifact state

- [x] Suite green through the close-out commit (1,717+ collected; the
      pre-existing red bayes test fixed in 9fe4852).
- [x] Copy gates suite-enforced (test_copy_gates.py) and clean on the final
      tree.
- [x] test_generated_docs_in_sync green on the final tree (docs regenerated
      last; run_monthly now regenerates them after registry restamps).
- [x] Golden-fingerprinted TRACKED artifacts (xfv.json, trade_values.json,
      grpo_scores.json, milb_translation.json) byte-identical to the p3-base
      baseline through every wave: the whole pass is output-neutral on
      published model numbers. All four model-change experiments were
      rejected at their pre-registered gates, so no expected-CHANGED entry
      exists.

## Wave results

- [x] Lane B: stabilization constants centralized, output-diff IDENTICAL
      (8570cf7). Lane H2: glossary stamp + copy backlog + enforced copy
      gates (f894429). Experiments wave 1a: $/WAR sensitivity + SC+
      isolation shipped, isotonic rejected at gate (d60c4d3).
- [x] Lane G: audit deliverables (this file + 6 siblings), generator +
      sync test landed; regenerated after all lanes.
- [x] Lane H1: visible error states + retry in all six module apps (F-02),
      REM+/Bullpen+ on-page explainers (F-08), per-year P90 upside element,
      eFV-primary grade language on projections board + #cmp.
- [x] Lane P: surplus $ credible band on player detail (D4), GFX badges
      follow rank mode (B3), eFV-vs-consensus track-record panel (C1),
      reliability diagram of the shipped distribution (C2).
- [x] X-D1 (gmLI stability): gate PASSED cleanly (pooled rho 0.4683, CI
      floor 0.412 vs 0.30 bar); registered; display wiring lands this pass.
- [x] X-D2 (age-relative index): numeric bar met but NOT a clear pass
      (post-hoc stability instruments, out-predicted by the level-relative
      comparator, selection confound); NOT wired; owner decision queued.
- [x] X-ISO (eFV isotonic): REJECTED at pre-registered gate; loss ledger +
      deprecated registry row; published numbers untouched.
- [x] Wave 2 adversarial verification (4 read-only lanes over the full pass
      diff): 16 findings, no P0; every P1/P2 fixed in the close-out commit
      (glossary deep link, gmLI season derivation, SC+ decision pinned to
      closed seasons), P3s fixed or recorded. Live Playwright boot of all
      shipped surfaces: zero page errors.
- [x] eFV round (owner-directed): E-ISO2, E-LAMBDA, E-STUFF all rejected or
      inconclusive at pre-registered gates; loss ledgers + registry rows
      45-47; eFV published numbers unchanged. The measured takeaway: eFV
      ranking is at its trainable-data ceiling; the real calibration gain
      found (bucket probabilities at FV45+) is blocked by a rank-gate
      tolerance tighter than the eval's noise floor, recorded for a future
      pre-registration.

## Owner actions (pending, cannot be done by agents)

- [ ] Production eephus.io is a STALE nginx build; redeploy the current tree
      (nightly Pages workflow exists; production box was never repointed).
- [ ] One-time Pages automation setup: cron or the 3 repo secrets for the
      07:30 UTC nightly workflow.
- [ ] Payload backlog decision: debuts payload ~122MB, boot payload ~62MB;
      either accept for Beta or approve the trim plan before launch.

## Launch-day tasks

- [ ] Run editorial_eval when the first spotlight cohort matures
      (~2026-07-11). NOTE the designed forcing function: once it first
      writes data/editorial_eval.json, the standing-rule test goes red until
      the owner registers a verdict for the `spotlights_movement` row.
- [ ] Final `python tools/gen_audit_docs.py` + commit, so the generated
      deliverables snapshot the shipped tree.

## Standing rules in force for the wave

- No em/en dashes in user-facing copy; FV and 20-80 grades display CEILING;
  eFV and "+"-style metrics round to NEAREST.
- Every model claim maps to a registry row + committed eval artifact.
- Gated experiments only: marginal or failed results go to the loss ledger
  and REVIEW_QUEUE.md, never to the site.

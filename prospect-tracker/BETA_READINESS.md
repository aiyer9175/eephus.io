# Beta Readiness (go/no-go)

Launch: 2026-07-11. Curated checklist; the audit orchestrator fills the
final go/no-go after the current wave lands. Legend: [x] verified,
[ ] open, [WAVE] awaiting this wave's results (do not hand-mark; the
orchestrator writes these from lane reports).

## Data freshness

- [x] Daily pipeline green: timeseries daily run completed clean 2026-07-01.
- [x] Model registry stamped 2026-06-30, 42 rows, validate() clean, stored
      problems: none (see MODEL_REGISTRY.md, regenerated from the same file).
- [ ] Monthly run lands before launch with the wave's pipeline fixes in
      (draft/pipeline fixes only reach tracked draft_timeseries.json on the
      next rebuild).

## Test + artifact state

- [x] Suite green: 1,705 collected, green after 9fe4852 (the pre-existing
      red test fixed by asserting the rarity-floor invariant, CHANGELOG.md
      entry 1).
- [x] Golden fingerprint baseline recorded as `p3-base` (5/5 artifacts,
      commit 4525ec5 baseline); wave output-diffs are judged against it.
- [WAVE] All lanes re-run the copy gates (tools/copy_lint.py +
      tools/strip_emdashes.py --check) after final edits.
- [WAVE] test_generated_docs_in_sync passes on the final tree (regenerate
      tools/gen_audit_docs.py LAST, after every lane's edits land, since
      SITE_MAP.md/DATA_SOURCES.md introspect live source).
- [WAVE] Golden-fingerprinted artifacts byte-unchanged unless a lane's
      expected-CHANGED justification is on file (pipeline_artifact_diff).

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

# Beta Readiness (go/no-go)

> **ARCHIVED 2026-09-25. Historical record, not current status.** This is the
> go/no-go checklist for the Beta launch of 2026-07-11, kept as written. Its
> figures are from that date: the model registry it counts at 75 rows carries
> 317 today (`MODEL_REGISTRY.md`). Launch planning for the production port lives
> in `docs/LAUNCH_READINESS.md` (the current checklist), `docs/port/PORT_SPEC.md`
> and `docs/master-plan-2026-09-24-final-pass.md`. Moved here from the repository
> root on 2026-10-01 (owner answer M23-4).

Launch: 2026-07-11. Curated checklist. Legend: [x] verified, [ ] open.

## VERDICT (2026-07-02): GO, conditional on the owner actions below

Everything code-side is done, verified and pushed: three audit waves, an
adversarial verification pass over the full diff (no P0 findings, every P1/P2
fixed), four gated model experiments honestly rejected with loss ledgers, one
new validated metric shipped (gmLI 3yr), and the full gate battery green. The
remaining launch risk is entirely in the owner actions (production deploy,
nginx config, db backup, payload sign-off) and the ordinary pre-launch data
refresh.

Addendum (2026-07-07): deploy target resolved to the self-building nginx box
(deploy/README.md Option 1) with a written runbook
(docs/prelaunch-2026-07/DEPLOY_RUNBOOK.md); the owner-action list below is now
the deploy cron + first-run seed, the initial webroot redeploy, the nginx
cache-header block, the prospects.db backup cron, and a one-line payload
accept-for-Beta sign-off. Launch-cycle code work landed today is in the new
"Completed 2026-07-07" section.

## Data freshness

- [x] Daily pipeline green: latest daily run completed clean 2026-07-02
      (timeseries generated_at 2026-07-02T17:39Z; timeseries.json is
      untracked by design, owned by the pipeline).
- [x] Model registry: 75 rows (21 validated / 38 provisional / 4 unvalidated /
      12 deprecated), validate() clean (see MODEL_REGISTRY.md, generated from the
      same file). Refreshed 2026-07-07 by the pre-beta registry-hygiene pass
      (xfv_backgrade registered; the external/pending unvalidated rows relabeled;
      see "Completed 2026-07-07" below). May rise further when the eFV accuracy
      pass (docs/prelaunch-2026-07/GATES.md) registers any M-gate winner rows.
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
- [x] Review-queue round (owner-directed): SHIPPED farm-letter snapshotting,
      the PROSPX gradeBlock refactor + grade-scale outcome band, and the F-01
      total-band fix (dropped as miscalibrated per the owner-approved
      fallback). RESOLVED the ERA-shrink unification (keep two) and MiLB park
      factors (infeasible on cached data). CLOSED the eFV bucket-calibration
      line (E-ISO3, final loss ledger). Overseas wRC+ upgraded to
      ready-to-run and queued. AgeRel+ stays parked. Registry 51 rows at that
      round (now 71 after the 2026-07-05 improvement pass), suite
      1,725 green, golden artifacts still byte-identical to baseline (the
      whole review-queue round is output-neutral on published model numbers).
      DEFERRED: Country/IFA entity pages (build lane failed on a formatting
      error, not a data problem; REVIEW_QUEUE item 14).

## Owner actions (pending, cannot be done by agents)

Deploy target is CHOSEN: the nginx box builds itself nightly (deploy/README.md
Option 1 - it pulls the repo, runs the pipeline, gates on the suite, and rsyncs
the webroot; a red suite leaves the live site untouched). The full owner-facing
runbook is docs/prelaunch-2026-07/DEPLOY_RUNBOOK.md; the lines below reference it
rather than duplicate it. (deploy/README.md Option 2, the Actions-builds +
SSH-push path with 3 repo secrets, stays documented as the alternative.)

- [ ] Install the nightly cron + seed the first run: DEPLOY_RUNBOOK.md sections
      1-2 (the exact 03:10 ET line; `EEPHUS_FULL=1` for the very first run so
      every tracked artifact rebuilds once from a clean pull).
- [ ] Initial webroot redeploy (production is STALE): production nginx still
      serves a hand-copied build and is not replaced until the first green
      nightly rsyncs the fresh build into `$WEBROOT` (DEPLOY_RUNBOOK.md section
      3). Treat launch day as "not live until the first green nightly publishes";
      confirm the webroot timestamps advanced and `/data/` boot JSON matches.
- [ ] nginx server block: enable `gzip_static` + the per-location cache headers
      (deploy/README.md nginx section, updated 2026-07-07). `/data/` takes a long
      `max-age` (payloads are `?v=<stamp>` cache-busted); `/assets/` and `*.html`
      stay `no-cache` so a rebuild is picked up on the next request and the
      hand-authored PROSPX/CollegeSavant shared `?v=` lag can never strand assets.
      `sudo nginx -t && sudo systemctl reload nginx` after.
- [ ] prospects.db nightly backup: add the sqlite `.backup` cron line a few
      minutes before the build (DEPLOY_RUNBOOK.md section 5). prospects.db is the
      one piece of state that does not rebuild from scratch.
- [ ] Payload weight: RECOMMENDATION is accept-for-Beta as-is (debuts payload
      ~122MB, boot ~62MB on disk; `gzip_static` ships the `.gz` twins so wire
      weight is far lower). The trim plan is deferred to REVIEW_QUEUE.md item 16
      (post-beta), so this is a one-line owner sign-off, not a pre-launch build.

## Launch-day tasks

Morning-of checklist: docs/prelaunch-2026-07/LAUNCH_DAY.md.

- [ ] editorial_eval same-day-verdict rule: when the first spotlight cohort
      matures (~2026-07-11) the pipeline writes data/editorial_eval.json for the
      first time, which turns the withheld-until-matured guard
      (`test_phase4b_evals.py`) RED and FREEZES the nightly deploy (the gate
      blocks the rsync, so the site stops publishing). Register the
      `spotlights_movement` verdict OFF `unvalidated` in the model registry and
      commit it the SAME DAY. Full procedure: DEPLOY_RUNBOOK.md section 6.
- [ ] Final `python tools/gen_audit_docs.py` + commit, so the generated
      deliverables snapshot the shipped tree.

## Completed 2026-07-07 (launch-cycle pass)

- [x] Deploy/golden reconciliation: the nightly gate runs with
      `EEPHUS_DEPLOY_RUN=1`, which relaxes the dev-time exact-hash golden
      tripwires (data/xfv.json + sibling artifact goldens) to SHAPE checks,
      because a deploy run legitimately regenerates those files from fresh data
      every night; dev and CI keep the exact-hash behavior (DEPLOY_RUNBOOK.md
      section 1).
- [x] Asset versioning: generated pages hash `/assets/` via
      `build_site._asset_ver()`; the hand-authored PROSPX/CollegeSavant pages
      `?v=`-stamp their vendor + same-directory JS, and the `/assets/` no-cache
      header (owner action above) covers the shared-`?v=` lag.
- [x] Beta badge shipped (PROSPX).
- [x] Tokens/chips pass.
- [x] L15 (last-15) chip.
- [x] Staleness notice: the site surfaces data_freshness stamps (PROSPX) so a
      stale nightly is visible to readers instead of failing silently.
- [x] Consensus glossary note.
- [x] Draft-weights equal-weight reset: draft-board sources hold at 1.0
      (`draft_consensus_weight`; the accuracy-weighted blend did not clear equal
      out-of-sample, so equal-weight is the honest live vote).
- [x] Model-registry hygiene: `xfv_backgrade` registered (provisional,
      documented under the eFV glossary entry); the external/pending unvalidated
      rows (`stuff_plus_external`, `swing_plus_external`, `spotlights_movement`)
      relabeled with dated honesty notes (kept `unvalidated` on purpose);
      validate() clean; MODEL_REGISTRY.md regenerated.

## Standing rules in force for the wave

- No em/en dashes in user-facing copy; FV and 20-80 grades display CEILING;
  eFV and "+"-style metrics round to NEAREST.
- Every model claim maps to a registry row + committed eval artifact.
- Gated experiments only: marginal or failed results go to the loss ledger
  and REVIEW_QUEUE.md, never to the site.

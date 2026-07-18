# Fresh audit 2026-07-18 — findings ledger + dispositions

Method: 8 targeted finder lanes over the least-recently-audited surfaces (the
2026-07-16/17 payload+export surge, draft-night features, statcast process-pool
rework, FA wave-2, prospx frontend, module JS, least-audited Python), each with a
2-lens adversarial verify pass (refute + reproduce). The verify pass exhausted its
budget mid-run, so lanes prospx-frontend / statcast-pool / draft-night /
payload-surge were re-verified by hand (owner session, Opus) against the code.
Do-not-refind lists from `.claude/maps/priorAudits.md` were honored.

## FIXED this pass (safe: correctness / dead-code / display; no published-number model change)

| # | sev | area | fix |
|---|---|---|---|
| A1 | P1 | payload/perf | `debuts_full` per-player shard path was dead: prospx read `DATA._slices.debuts_full` but storage advertises it under `_slices_dir` (storage.py:14468) → every graduate card fell back to the full monolith. Routed the JS through `_slices_dir.debuts_full` (matching pitch_plots), AND added `/data/debuts_full/***` to the nightly rsync + CI staging (it was shipped by neither). |
| A2 | P1 | prospx display | Farm-detail showed two different eFV grades for one player: graded-by-level list used raw `Math.round(xfv_grade)` while the affiliate table used the quantile headline `efvGradeDisplay`. Routed the graded-by-level badge through `efvGradeDisplay` and the `_rosterGrade` sort key through `efvRankValue` (quantile-consistent, breaks the 961 non-monotone inversions). |
| A3 | P2 | prospx feature | `chase_pct` was dead on ~8 surfaces: JS read `z.chase_pct` but zone rows only serialize `o_swing_pct` (zone_metrics.py; statcast_plus.py:85 documents the same bug class). Added a shared `chaseOf(z)` accessor (o_swing_pct-first, chase_pct fallback) and routed all sites through it. |
| A4 | P1 | GFX engine | `eephus-gfx.js` renderBoard indexed row cells by *filtered* column position after dropping `wideOnly` columns on narrow canvases, shifting every later cell when a wideOnly column is non-trailing (FA specs put them mid-list) → Deal WAR printed under the Surplus header on all non-wide FA share graphics. Preserve original column indices when filtering. |
| A5 | P2 | FA nav | Future-class views dropped the `class=` hash param on player/rail/value-map links → wrong or missing player card. Thread `class=` through the link builders. |
| A6 | P2 | hub nav | Hub strip advertised an "MLB Projections → player page" chip for never-debuted prospects, dead-ending at a "No detail" error. Gate the chip on projections availability. |
| A7 | P2 | prospx display | WAG list pills recomputed client-side (stale `FV_WAR_ANCHORS` mirror, consensus basis) and disagreed with the server-baked eFV-basis `regressed_wag` shown on detail/Time-Machine. Prefer the baked `debuted_value.wag.regressed_wag` when present; JS recompute stays the legacy fallback. |
| A8 | P1 | statcast ops | Pass-3 result loop swallowed worker/pool failures with no logging → a BrokenProcessPool (spawn worker death) could silently stale hundreds of rows in a "success" run. Added a `log.warning` in the except so failures are visible at production log level. |
| A9 | P3 | dead code | `spotlights.py` shadowed `_statcast_drivers` (two defs; first dead). Removed the dead one. |
| A10 | P3 | dead code | `trademachine.js` `renderTradeBoard()` duplicated `mount()`'s fetch/wire/GRPO block, unreferenced. Removed. |
| A11 | P3 | CollegeSavant | Hitter leaderboard descending sort floated missing values to the top (null-guard × direction). Fixed the null sink to stay last in both directions. |
| A12 | P3 | GFX engine | Modal dropped control changes made while a render was in flight (preview/export could mismatch selected options). Re-read options after each render. |
| A13 | P2/P3 | docs/gov | `docs/generate-gfx.md` rewritten to the shipped system; CHANGELOG backfilled 07-15b..07-18; REVIEW_QUEUE item 16 + BETA_READINESS stale boxes reconciled; registry note added for the 07-17 injury directive. |

## DEFERRED to owner (moves published model numbers, or needs the canonical DB to verify/fix)

| # | sev | area | why deferred |
|---|---|---|---|
| B1 | P2 | value_framework.py:2343 | `super_two` is only blended by the population rate at exactly (sample≤0 AND service≤0); the instant a debuted player has any sample/service it is priced as **definitively non-super-two** (callers pass `super_two=False` because real super-two status is unknowable pre-fact). Correcting this (population-blend for unknown-status serviced players) changes published surplus/arb dollars → needs owner sign-off + golden restamp, not a silent fix. |
| B2 | P1 | draft team pools | Finder claims Spotrac's $150K round-11-20 placeholder slots survive the results merge and inflate 2026 `team_pool_usd` by ~$1.5M/team. Cannot reproduce without the canonical draft DB (7-day-cached `build_draft_pools`); fixing pool math blind risks breaking correct behavior. Owner to verify against the live pool figures. |
| B3 | P2 | draft overperformers | Class flip may push the just-drafted 2026 class into `_attach_overperformance`, showing draft-day grades as "FV now" and polluting expected-FV-per-pick medians. Needs canonical data to confirm the cohort is actually included. |
| B4 | P2 | draft simulate | `_simSlotForPick` indexes `order[pick-1]` vs gapped `pick_overall`; "Round 1" length counts label 1/1A/1B vs comp-round labels — possible wrong slot/budget for picks after the comp gap. Draft-night-only surface; verify next draft cycle. |
| B5 | P2 | prospx sort | Prior-anchored (`xfv_provisional`) grades still sort as model reads in the "eFV − consensus gap" board sort (the GFX-export half of this is fixed under the GFX overhaul; the sort-semantics half is an owner display call — should provisional players be excluded from a gap sort, or flagged?). |
| B6 | P2/P3 | statcast infra | Deeper spawn-robustness beyond A8: `feed_cache` fixed shared tmp filename (concurrent same-game writers), FINAL_TTL immutability vs suspended-resumed games, `_get_json` serving crash-truncated cache as hard errors. Real but infra-hardening with test/repro cost; batch into a dedicated statcast-hardening pass. |

## DROPPED (intentional, refuted, or already-known)

- `STATCAST_METRICS_FRESH_DAYS = 0`: the intentional "always refresh" sentinel (matches career-stats stage 3a freshness=0), not dead code.
- BETA_READINESS go/no-go checkbox drift: already logged in priorAudits §2.2.
- projections.js "per-year bands unaffected" comment: a change-scope statement, not a calibration claim (verifier-refuted).
- Wave-2 lab re-runnability, supply_pop "alignment" sigma: refuted / not-a-defect on inspection.

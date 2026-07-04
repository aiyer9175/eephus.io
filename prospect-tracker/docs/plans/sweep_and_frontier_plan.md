# Sweep & Frontier Plan (Phase A, Step 3)

The in-repo companion to the approved research-sweep plan. Details in `docs/audit/current_state_map.md` (census) and `docs/audit/research_check.md` (correctness). Owner-approved 2026-07-03; Phase B in progress.

## (a) Research-check fixes by severity
- **Fix-now:** RC-1 OPS+ formula (copy), RC-2 ABS-regime silence (copy).
- **Fix-soon:** RC-3 RPS+ scale honesty (copy; number-unification queued), RC-4 pStuff+ tooltip (copy), RC-5 Stuff+ label collision + credit.
- **Polish:** RC-6 per-season shrink (number-changing, fix-now with output-diff per owner), RC-7 em-dash generated notes, RC-8 stale docstrings, RC-9 milb park-factor disclosure.
- **Verified clean:** transform-first-aggregate-last (value_framework), within-level percentiles (regime-safe), plus-stat hygiene, aging survivorship correction. See research_check RC-N1..N5.

## (b) Glossary reclamation — three shelves
Census 245 entries: **142 Arkmetric / 63 Foundation / 40 Industry**; 183 keep, 36 rewrite, 19 verify, 7 merge, **0 delete**.
- Add explicit `shelf` field (builder already computes `FOUNDATION_CATS`, does not emit).
- Credit ~30 uncredited industry entries (Tango/FanGraphs, McCracken, Studeman, Swartz, Statcast, Sarris/Bay, Pitcher List) + Arkmetric origin+version lines.
- Add missing entries: xwOBA/xwOBAcon, BABIP, VAA/VAAoe. Sync 6 registry models lacking a glossary entry.
- 41 rewrites to template; 7 merges (CPX/Complex, comp-pick, rarity); disambiguate 13 multi-resolving aliases.
- Architecture: registry↔glossary **join** (registry drives verdict/accountability, glossary drives prose), not full generation.

## (c) Frontier evaluation table

| # | Idea | Feasible | Effort | Tier / disposition |
|---|---|---|---|---|
| 1 | Draft War Room | partial | L | **Tier 1** (cached-poller artifact; owner chose full build) |
| 2 | FV Tape | partial | M | **Tier 1** (top-history subset, graceful degrade, flag-dark) |
| 3 | Risk-adjusted Surplus (Sortino) | partial | M | **Tier 1** (downside/bust column on existing mixture) |
| 4 | System Duration / Window Alignment | yes | M | **Tier 1** (highest confidence; ETA rollup + alignment) |
| 5 | Model Report Cards v0 | yes | S | **Tier 1** (~70% shipped; inline proof charts) |
| 6 | Dev+ org development alpha | yes | M | Tier 2 |
| 7 | Environment Engine | partial | L | Tier 3 (ship level/league/era unification; park sub-layer blocked) |
| 8 | Savant Bridge AAA→MLB | yes | M | Tier 2 (strong) |
| 9 | Catcher / Challenge Value | blocked | M | Tier 3 (blocked — no catcher-defense or ABS-challenge data ingested) |
| 10 | Attrition curves | partial | M | Tier 2/3 |
| 11 | Crunch Index | yes | S | **Down-tier** — largely already built (rule5_urgency/on_40_man/options) |
| 12 | aStuff+ v2 deception | partial | M | Tier 2/3 |
| 13 | REM+ extensions | partial | M | Tier 2 |
| 14 | Prospect Greeks | yes | S | Tier 2/3 (cheap; curves already exist) |
| 15 | Transmutation / Conversion+ | yes | S | Tier 2 |
| 16 | Exploitability sequencing | partial | L | Tier 3 (needs per-pitch sequence store) |
| 17 | Judgment (swing decisions) | partial | L | Tier 3 (needs count-conditional per-pitch retention) |
| 18 | Fingerprint matchups | partial | M | Tier 3 |
| 19 | IFA Efficiency | yes | S | Tier 2 (strong; bonus-pool data ingested) |
| 20 | Posting Clock | partial | M | Tier 3 |
| 21 | Source Alpha (lead-lag) | yes | M | Tier 2 |
| 22 | Portfolio Frontier | yes | S | **Down-tier** — engine already built (system_surplus_distribution) |

**Proposed Tier 1 pre-launch subset (owner-approved):** all of #1–5, each behind a flag, each with a registry row + glossary entry + Report Card hook at birth.

## (d) Organization & polish shortlist
Money-formatter consolidation, dash/fvCeil centralization, ark-vs-industry origin badges, qualifier/shrinkage chips + sticky headers on Projections/FA, Projections surplus uncertainty cue, tooltip→glossary wiring (CollegeSavant + Projections team table), nav/masthead name consistency. Deferred: PROSPX `data-term`→`data-gl` unification, shared empty/error component.

## (e) Risk register
See the approved plan's risk table: Draft War Room poller (highest), number-changing shrink (output-diff sign-off), glossary `shelf`/alias changes (resolve/CmdK), Report Card `card` field (refresh_stamps round-trip), surplus local-lambda isolation, pre-existing owner launch blockers (stale nginx, Pages cron, payload, editorial_eval).

# Minimum Architecture — Phase 1C

Deliverable 6. The smallest architecture that recovers nearly all supported signal found across Phases 1A-1C. Every module below must justify: why it exists, why it can't be absorbed into another module, what unique information it contributes, and what evidence supports it. Modules without evidence are excluded, not included provisionally.

## Gate 0: Tracking-status routing (not a module — a precondition)

Every module below except the Outcome-Only module requires tracked-venue data. This isn't itself a production component; it's the dispatch logic Phase 1A/1B established is architecturally load-bearing (venue-level, not level-level).

## Module 1: Physical Stuff (Velocity + Movement + Spin)

- **Why it exists**: three fields, each independently highly reliable (split-half r=0.91-0.99, Phase 1B) and only modestly correlated with each other (r=0.27-0.33, `FEATURE_REDUNDANCY_REPORT.md`) — genuinely related but not redundant.
- **Why it can't be absorbed elsewhere**: it's the only module with near-total measurement reliability; folding it into an outcome-based module would contaminate a clean signal with noisy ones (whiff-rate reliability tops out at 0.51; Stuff's tops out at 0.99).
- **Unique information**: physical, non-outcome-dependent — measurable even for a pitcher who hasn't accumulated enough outcomes yet to estimate a results-based metric reliably.
- **Evidence**: `IDENTIFIABILITY_REPORT.md` (Phase 1B), `VARIANCE_DECOMPOSITION.md` (Phase 1B: real between-pitcher ICC 12-35%), this phase's redundancy matrix.

## Module 2: Arsenal Construction (pitch mix / diversity)

- **Why it exists**: contributes the single largest incremental-R² block to whiff rate (0.071, larger than velocity+movement+spin combined at 0.066) — real, independent information Module 1 doesn't capture.
- **Why it can't be absorbed into Module 1**: `FEATURE_REDUNDANCY_REPORT.md` shows `pitch_entropy` correlates only moderately with velocity (-0.44) and spin (-0.33) — related, but a genuinely separate axis, and it requires categorical pitch-type data Module 1 doesn't use at all.
- **Unique information**: what a pitcher throws, not how well any single pitch is thrown.
- **Evidence**: `INCREMENTAL_INFORMATION_REPORT.md` Chain 1, this phase.

## Module 3: Miss-Inducing Ability (whiff rate)

- **Why it exists**: moderate but real reliability (split-half r=0.33-0.51 depending on level, Phase 1B) and receives independent incremental contributions from Modules 1, 2, and location — not fully explained by any of them (total R²=0.228, meaning most of its variance is still its own).
- **Why it can't be absorbed elsewhere**: it's an outcome, not a physical trait — Modules 1-2 predict it partially but don't replace it; keeping it separate preserves the ability to ask "does this pitcher over/under-perform their stuff+mix" (a legitimate, evidence-motivated question this architecture enables).
- **Unique information**: realized swing-and-miss outcomes, beyond what physical inputs predict.
- **Evidence**: `IDENTIFIABILITY_REPORT.md` (Phase 1B reliability), `INCREMENTAL_INFORMATION_REPORT.md` (Phase 1C, this phase — confirms it's not redundant with Modules 1-2).

## Module 4: Ground-Ball Tendency

- **Why it exists**: real, mechanically sensible relationship with Movement specifically (10.3-point R² increment, the largest single increment found anywhere in this phase) — a genuine, distinct signal.
- **Why it can't be absorbed into Module 1 (Movement) directly**: it's an outcome measured from `hitData`, not a repackaging of the `pfxZ` input — Movement predicts it well but isn't identical to it (R²=0.134, not 1.0), and no separate reliability test has confirmed `ground_ball_rate` itself is stable enough to skip as "just movement."
- **Unique information**: realized batted-ball trajectory outcomes.
- **Evidence**: `INCREMENTAL_INFORMATION_REPORT.md` Chain 4, this phase. **Caveat**: `ground_ball_rate`'s own reliability was never tested (only its relationship to Movement) — flagged as a real gap before this module is built in Phase 2, not glossed over.

## Module 5: Damage Suppression (merged: avg. launch speed + hard-hit rate)

- **Why it exists as ONE module, not two**: `avg_launch_speed` and `hard_hit_rate` correlate at r=0.72 — the one clear redundancy this phase found. Building both as separate production components would duplicate the same underlying signal.
- **Why it's included at all, given how weakly explained it is**: it's not excluded for being unexplained by other modules — that's exactly the charter's point (unique information, not redundant). It IS included with a strong caveat: this phase found essentially nothing (1.9-3.7% R²) that explains it, meaning **this module's own reliability was never separately tested**, and it may turn out to be dominated by noise once that's checked (the same open question Phase 1B flagged for command).
- **Evidence**: `FEATURE_REDUNDANCY_REPORT.md` (the merge justification), `INCREMENTAL_INFORMATION_REPORT.md` Chains 2-3 (the near-null connection to everything else).
- **Status**: **provisional module, not a confirmed one** — see `PRODUCTION_COMPONENT_RECOMMENDATIONS.md` for its classification as research-only pending a dedicated reliability check.

## Module 6: Outcome-Only Result Rate (whiff rate, all-levels)

- **Why it exists**: the only viable module at AA/High-A/untracked-Low-A — without it, those levels have zero production coverage.
- **Why it's separate from Module 3**: different population (untracked levels), different (much weaker) supporting evidence (Chain 5: R²=0.016 total from the only available predictor), and cannot be pitch-type-specific by construction.
- **Unique information**: the only recoverable pitcher-level signal at untracked venues.
- **Evidence**: `IDENTIFIABILITY_REPORT.md` (Phase 1B: whiff-rate reliability at AA/High-A/untracked Low-A), this phase's Chain 5.

## Explicitly excluded (evidence says no, not "not yet")

- **Command / location as its own module**: split-half r=0.07-0.19 at typical sample sizes (Phase 1B) — the weakest-supported tracked-only construct tested across all three phases. Not merged into any module above; recommended for exclusion until the larger-sample retest flagged repeatedly since Phase 1B either confirms or further disconfirms it.
- **Called-strike rate, anywhere**: r=-0.10 to +0.06 at every level, every sample size (Phase 1B) — the single clearest negative finding in this entire research program. Excluded outright.
- **A single universal composite score**: rejected in `ARCHITECTURE_COMPARISON.md` — the evidence doesn't support collapsing largely-independent modules into one number.
- **Role, sequencing, pitch aging**: not excluded on evidence (none exists either way) — simply not built, flagged as future work, not part of this minimum architecture.

## Observed evidence / Inference / Speculation

Every module's justification above cites a specific number from this phase's or Phase 1B's computed output. The "why it can't be absorbed elsewhere" arguments are Inference built directly on those numbers. Module 5's inclusion-with-caveat is the one place this report explicitly flags remaining uncertainty rather than resolving it either way.

## Future work

Confirm Module 4 and Module 5's own reliability (never separately tested — this phase only tested their relationship to other modules, not their internal stability) before either proceeds past research-only status. Confirm Module 2's family-restricted reliability (flagged since Phase 1B) before treating Arsenal Construction as fully validated rather than "contributes real incremental information in a pooled test."

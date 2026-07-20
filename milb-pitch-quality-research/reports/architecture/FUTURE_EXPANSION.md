# Future Expansion

Phase 12. How future information integrates without requiring a redesign — tested against this architecture's actual design choices, not asserted.

## Expanded MiLB tracking

Directly accommodated by design: `TRACKING_BRANCH_ARCHITECTURE.md`'s gate is a routing table keyed on venue, re-evaluated seasonally (`REFRESH_ARCHITECTURE.md`). A newly-tracked venue moves its pitchers from the Outcome-only branch to the Tracked branch going forward, with no module redesign — this was explicitly tested as a design requirement in Phase 4/`TRACKING_BRANCH_ARCHITECTURE.md`.

## Reconciling with Baseball Savant's `statcast-search-minors` (the `stuff_plus_aaa` endpoint)

Not yet accommodated — this is the most concrete, near-term expansion this charter identified (`BENCHMARK_INTEGRATION.md`, `DEPENDENCY_GRAPH.md`). Adopting or reconciling with that endpoint would add `arm_angle` and a real `delta_run_exp` label to Module 1/3's available inputs. Because Modules 1-6 are defined at the feature-family level (`FEATURE_FAMILY_INVENTORY.md`, Phase 1C), adding a new field to an existing family (e.g., `arm_angle` into the Movement family) is additive, not restructuring — the incremental-information chains would simply gain another block to test.

## TrackMan / Hawk-Eye (if MiLB adopts a unified tracking vendor)

Would likely **change the venue-tracking gate's granularity** — if tracking becomes universal (all venues, all levels), the entire Tracked/Outcome-only branch split (`TRACKING_BRANCH_ARCHITECTURE.md`) would collapse to a single branch by construction, not by redesign: the gate would simply route 100% of venues to the Tracked path. No module itself would need to change; only the gate's routing table would.

## College data

`CURRENT_ECOSYSTEM_MAP.md` found CollegeSavant's pitcher app already has an independent college pitch-tracking dataset (`pitcher_pitch_data_2024/2025/2026.js`, embedded, no MiLB linkage). Integrating college data into this architecture would require (a) a new tier below the current lowest level in the tracking-status gate, and (b) resolving the college data's own field schema against this research's `FEATURE_FAMILY_INVENTORY.md` families — an additive tier, not a restructuring, provided the college data's fields map onto the same family concepts (velocity, movement, spin, etc.), which is plausible but unverified.

## International leagues

No international pitch-tracking data source was identified anywhere in this repo or this research. Would require establishing a new raw-data pipeline (parallel to `scripts/pull_schedule.py`/`pull_game_feeds.py`'s MLB-Stats-API-specific implementation) — the tracking-status-gated architecture itself would still apply (some international venues tracked, some not, by the same logic as MiLB), but the raw ingestion layer would need new code, not just new routing.

## Biomechanics

Not accommodated by anything in the current feature-family structure — biomechanical data (motion capture, force plates, etc.) is a fundamentally different measurement type than anything in `FEATURE_FAMILY_INVENTORY.md`. Would likely warrant a new feature family (e.g., "Kinematic Sequencing") parallel to the existing ones, testable via the same incremental-information methodology (`INCREMENTAL_INFORMATION_REPORT.md`'s block-wise R² approach) without disturbing existing modules — additive, consistent with the architecture's design intent, but genuinely new territory with no current evidence either way.

## Future Eephus research

The clearest anticipated future integration is value-translation: once this research's pitch-quality modules exist and are validated, a natural next question is whether they translate into `pitcher_ewar`-style run-value-above-replacement — but this is explicitly **not** attempted by this architecture (Layer 1 vs. Layer 2 champion split, per your decision) and remains blocked on private-data access regardless of how much further pitch-quality research happens (`KNOWN_GAPS.md`).

## Observed evidence / Inference / Speculation

The MiLB-tracking-expansion and TrackMan/Hawk-Eye sections are Inference directly testing this architecture's own design claims against a hypothetical future event — a genuine test of Governing Philosophy #4, not just an assertion that it holds. The college/international/biomechanics sections are more speculative, since no data source was found for any of them in this research or repo — flagged as such, not presented with false confidence.

## Future work

None of this section requires action now — it exists to demonstrate the architecture doesn't need redesigning under plausible future scenarios, per the charter's explicit requirement.

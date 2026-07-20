# Feature Family Inventory — Phase 1C

Deliverable 1. Groups candidate variables into families rather than individual columns, building on Phase 1A's field inventory and Phase 1B's per-metric identifiability findings. `data_cache/derived/pitch_dataset_v2.parquet` extends Phase 1B's dataset with `hitData` fields (launch speed, launch angle, trajectory, hardness) — the one gap Phase 1B explicitly flagged as not computed. No new API pull; re-parsed from the same cached games.

| Family | Representative metric(s) used this phase | Scope | Status entering Phase 1C |
|---|---|---|---|
| Velocity | `velocity` (mean start speed) | TRACKED_ONLY | Established highly identifiable, Phase 1B |
| Movement | `movement_pfx_x`, `movement_pfx_z` | TRACKED_ONLY | Established highly identifiable, Phase 1B |
| Spin | `spin_rate` | TRACKED_ONLY | Established highly identifiable, Phase 1B (with a completeness caveat) |
| Pitch usage / diversity / arsenal depth | `share_fastball`, `share_breaking`, `share_offspeed`, `pitch_entropy` (Shannon entropy over family shares) | TRACKED_ONLY (needs pitch-type identity) | New this phase — Phase 1B flagged pitch-mix as untested |
| Pitch sequencing / interaction | Not computed this phase | Would need within-PA pitch-order extraction | Untested — flagged in Phase 1B, still untested |
| Location / Command | `zone_rate` | TRACKED_ONLY | Established **not identifiable at pilot sample sizes**, Phase 1B |
| Swing decision | `chase_rate` (tracked), `swing_rate_all_levels` (outcome-only) | Split: TRACKED_ONLY for chase, ALL_LEVELS for raw swing rate | Chase rate weakly-moderately identifiable (Phase 1B); swing rate ALL_LEVELS |
| Whiff ability | `whiff_rate` | ALL_LEVELS (computed here on the tracked population for a fair chain, and separately on the all-levels population) | Established moderately identifiable, Phase 1B |
| Weak contact | `avg_launch_speed` (mean exit velocity allowed, batted balls only) | TRACKED_ONLY (`hitData`) | New this phase |
| Damage suppression | `hard_hit_rate` (share of batted balls ≥95 mph) | TRACKED_ONLY (`hitData`) | New this phase |
| Ground-ball tendency | `ground_ball_rate` (share of batted balls classified `ground_ball`) | TRACKED_ONLY (`hitData`) | New this phase |
| Context (count state, handedness) | Not aggregated into a per-pitcher scalar this phase | ALL_LEVELS | Present in the dataset structurally (used to build outcome flags), not analyzed as an independent family |
| Organization / Park | Not re-derived this phase | ALL_LEVELS | Already assessed in Phase 1B: between-venue ICC 0.01–0.3% for every outcome metric at every level — effectively no detected park/org signal. Reused, not repeated. |
| Role (starter/reliever) | Not computed | — | No roster/appearance data pulled at any phase — remains unbuilt, not merely untested |
| Development trajectory / pitch aging | Not computed | — | Needs multi-season data; this research is single-season (2025) throughout |

## Observed evidence
Every family with a "this phase" metric is backed by a real, computed per-pitcher aggregate in `data_cache/derived/pitcher_family_table.csv` (internal artifact, gitignored) — see `scripts/phase1c/family_analysis.py`. 600 pitchers cleared the ≥100-tracked-pitch threshold used for the physical/tracked families; 577 of those also cleared ≥15 batted balls for the `hitData`-dependent families.

## Inference
The family list splits cleanly into three groups by data requirement: (1) tracked-physical (velocity/movement/spin/pitch-mix/location/chase), (2) tracked-batted-ball (weak contact/damage/ground-ball — a subset of (1)'s population, further restricted to pitchers with enough batted-ball events), (3) outcome-only (whiff, swing rate, as computed on the all-levels population). This mirrors the Branch A / Branch B split Phase 1B already recommended architecturally.

## Speculation
Pitch sequencing/interaction likely represents genuine additional information beyond the families tested here (count-state fields already exist in the dataset), but this is speculation pending the future work flagged below — not tested this phase.

## Future work
Extract within-plate-appearance pitch order to build a sequencing family; build a role classification from appearance-pattern data (innings/game, appearances/week) if roster data becomes available; multi-season pull for development-trajectory analysis.

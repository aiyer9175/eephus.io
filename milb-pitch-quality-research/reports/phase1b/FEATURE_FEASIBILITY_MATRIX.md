# Feature Feasibility Matrix — Phase 1B

Deliverable 2. Every candidate feature scored on: measurable, trustworthy, stabilizes, survives promotion, likely recoverable signal, supports causal interpretation. `ALL_LEVELS` vs. `TRACKED_ONLY` follows the load-bearing boundary established before this phase began: pitch-type identity itself is unavailable at untracked venues, so nothing pitch-type-specific can ever be `ALL_LEVELS`. Numbers pull directly from `RELIABILITY_STATS.json`, `VARIANCE_STATS.json`, `PROMOTION_SEAM_STATS.json` (AAA figures shown; see those files for all 4 levels).

| Feature | Scope | Measurable | Trustworthy | Stabilizes | Survives promotion (exploratory) | Recoverable signal | Causal interpretation |
|---|---|---|---|---|---|---|---|
| Velocity (`avg_start_speed`) | TRACKED_ONLY | Yes, precise | Yes (~100% coverage at tracked venues) | Yes — split-half r=0.98 at n≥20 pitches already | Not directly tested (physical trait, not in ALL_LEVELS promotion check) | High — ICC 24-27% between-pitcher | Direct physical measurement — high |
| Spin rate | TRACKED_ONLY | Yes | Partial — measurably less complete than velocity even at tracked venues (Information Content Report) | Yes — split-half r=0.98 | Not tested | High — ICC 27-31% | Direct physical measurement — high |
| Movement (pfxX/pfxZ) | TRACKED_ONLY | Yes | Yes | Yes — r=0.93-0.98 | Not tested | High — ICC 12-35% | Direct physical measurement — high |
| Pitch type / arsenal identity | TRACKED_ONLY | Yes, at tracked venues (auto-classified) | Not independently validated against a ground truth in this pilot | Not directly tested | Not tested | Enables the nested pitcher×family decomposition (`VARIANCE_DECOMPOSITION.md`) — family explains more variance than pitcher for velocity/spin | Algorithmic classification, not causal by itself |
| Pitch usage / mix | TRACKED_ONLY | Yes, given pitch type | Same caveat as pitch type | Not directly tested this phase | Not tested | Plausible given family-level variance findings | Descriptive, not causal |
| Pitch sequencing | ALL_LEVELS (count state is universal) | Yes (`balls_pre`/`strikes_pre` present everywhere) | Yes | Not directly tested this phase | Not tested | Not directly tested — flagged for Phase 2 | Requires care — count state is itself an outcome of prior pitches |
| Pitch interaction / velocity separation | TRACKED_ONLY | Requires ≥2 pitch types per pitcher with tracked velocity | Depends on per-family sample size | Not directly tested | Not tested | Plausible (family variance dominates residual for velocity) but not directly measured as a separation statistic this phase | Descriptive |
| Pitch entropy | TRACKED_ONLY (needs pitch-type identity) | Computable from pitch-type distribution | Depends on per-pitcher pitch count | Not tested | Not tested | Not tested this phase | Descriptive |
| Whiff rate | ALL_LEVELS | Yes | Yes | Split-half r=0.33 (AAA), 0.51 (AA), 0.49 (High-A), 0.34 (Low-A) — moderate, level-dependent | r=0.30 across level transitions (n=348) — real but partial persistence | Low at single-pitch grain (ICC ~1.3%), moderate at season-aggregate grain | Confounded by opponent quality, count, sequencing — not isolated here |
| Called-strike rate | ALL_LEVELS | Yes | Yes | Split-half r=-0.10 to 0.06 — **essentially unreliable at this sample size** | r=0.05 (n=404) — near zero | Very low (ICC ~0.1-0.2%) | Strongly confounded by umpire/framing (Eephus's own `framing_treatment: DISCLOSED_SHARED` finding is directly relevant) |
| Chase rate | TRACKED_ONLY (needs zone) | Yes, at tracked venues | Yes | Split-half r=0.21 (AAA), 0.55 (Low-A) — inconsistent between the two tracked populations | Not tested (TRACKED_ONLY, excluded from promotion check by design) | Low-moderate, ICC <1% | Confounded by opponent approach |
| Ground balls / damage suppression | Not computed this phase | `hitData.trajectory`/`hardness` present at tracked venues (Phase 1A) but not built into this phase's metric set | Untested | Untested | Untested | Untested | Untested |
| Weak contact | Not computed this phase | Same as above | Untested | Untested | Untested | Untested | Untested |
| Location / command (`zone_rate`) | TRACKED_ONLY | Yes | Yes | Split-half r=0.07 (AAA) to 0.19 (Low-A) at n≥20, rising to 0.50-0.67 only among the few pitchers with 400+ tracked pitches | Not tested | Very low at pilot sample sizes; residual variance dominates (0.244 of ~0.25 total in the nested decomposition) | Confounded by catcher target, batter, count |
| Count leverage | ALL_LEVELS (count fields present everywhere) | Yes | Yes | Not tested this phase | Not tested | Not tested this phase | Requires game-state modeling, not attempted |
| Opponent quality | Not computed this phase | Batter ID present everywhere (`ALL_LEVELS`), no independent batter-quality measure built in this pilot | Untested | Untested | Untested | Untested | Would need an external batter-quality reference — not attempted |
| Role (starter/reliever) | Not computed this phase | Derivable from innings/appearance pattern, not built into this phase's dataset | Untested | Untested | Untested | Untested | Untested |
| Development trajectory / pitch aging | Not computed this phase | Would require multi-season data; this pilot is single-season (2025) | Untested | Untested | Untested | Untested | Untested |
| Pitch-mix evolution within season | Partially testable | `season_third` bucket exists in the dataset | Untested this phase (not run) | Untested | N/A | Untested | Untested |

## Observed evidence
All numeric entries above are pulled directly from this phase's own computed output, not assumed.

## Inference
Two feasibility classes emerge cleanly: (1) physical/tracked fields — measurable, trustworthy, stabilize fast, plausibly recoverable, causally direct; (2) outcome-derived fields — measurable and trustworthy as raw data, but stabilize slowly or not at all at pilot sample sizes, and are causally confounded by factors (umpire, opponent, catcher, defense) this pilot doesn't isolate.

## Speculation
Command (`zone_rate`) may prove more identifiable with either (a) much larger per-pitcher samples than this pilot's, given its stabilization curve was still climbing at n=400, or (b) a better command proxy than raw zone-rate (e.g. distance-to-target rather than binary zone membership) — not tested here.

## Future work
Ground-ball/damage-suppression/weak-contact metrics from `hitData` were scoped out of Phase 1B's metric set for time; they're natural Phase 2 candidates given `hitData` fields were confirmed present at tracked venues in Phase 1A. Role, opponent-quality, and multi-season pitch-aging features all require data this pilot didn't build (roster/appearance-pattern data, an external batter-quality reference, multi-season pulls respectively).

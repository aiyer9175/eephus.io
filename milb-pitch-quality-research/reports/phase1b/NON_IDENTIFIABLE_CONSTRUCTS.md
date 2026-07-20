# Non-Identifiable Constructs — Phase 1B

Deliverable 8. What cannot be recovered, explicitly, rather than quietly omitted.

## Not identifiable from any source available to this research (public MLB Stats API)

- **Release deception / tunneling**: no early-flight-path or release-consistency-relative-to-batter-recognition-window data exists in this feed at any resolution finer than the single release-point coordinate already extracted. True tunneling analysis needs multiple pitches' trajectories compared at a common post-release time slice — not available here.
- **True command (intended-target accuracy)**: the feed has no intended-target field. `zone_rate` (in/out of the strike zone) is the closest available proxy, and Phase 1B's own evidence shows it doesn't stabilize at pilot sample sizes even where tracking exists (`IDENTIFIABILITY_REPORT.md`). A pitcher intentionally locating just off the zone is indistinguishable from one missing badly — this is a definitional gap, not merely a sample-size gap.
- **Execution quality** (as distinct from command): same root cause — no intended-shape/intended-location data to compare an actual pitch against.
- **Tracking-vendor identity** (Trackman vs. Hawkeye vs. other): not exposed in this feed. Any measurement-quality difference between vendors (e.g. the spin-rate completeness gap noted in `INFORMATION_CONTENT_REPORT.md`) can't be attributed to a specific vendor from this data source alone.

## Not identifiable at AA, High-A, or the untracked majority of Low-A specifically

Everything requiring `pitchData` (velocity, movement, spin, extension, plate location, zone) or `hitData` (exit velocity, launch angle, trajectory, hardness) — because Phase 1A established, and Phase 1B's pooled dataset confirms (0.00% tracked share at AA and High-A across 358 and 363 sampled games respectively), that these fields are structurally absent at untracked venues, not merely sparse. This includes, as a direct consequence:

- Fastball/breaking-ball/offspeed quality, movement proxy, velocity talent — anything built on `pitchData`.
- Chase rate, zone rate, and any other zone-dependent metric.
- Ground-ball tendency, damage suppression, weak contact — anything built on `hitData`.
- Pitch usage, pitch mix, arsenal depth, pitch entropy — anything requiring pitch-type identity, since `details.type.code` is a tracking-derived field, absent wherever tracking is absent (confirmed directly in Phase 1A's probe of a cached AA game, not assumed).

## Not identifiable at pilot scale, though not proven structurally impossible

- **Command/location** (all levels, even tracked ones) — see `IDENTIFIABILITY_REPORT.md` and `NOISE_AND_STABILITY_REPORT.md`. Distinguished from the "structurally impossible" category above because the fields exist and are trustworthy; the reliability just hasn't stabilized within this pilot's sample sizes, and the stabilization curve was still rising, not flat, at the largest tested threshold.
- **Called-strike rate as a pitcher-skill signal** — reliability is near-zero-to-negative at every level and every tested sample size, with no rising trend (unlike command/chase rate). This is closer to "probably not a recoverable pitcher signal from outcome data alone" than "just needs more data," though this pilot cannot fully rule out the latter — see `NOISE_AND_STABILITY_REPORT.md`'s speculation on umpire/framing confounds.
- **Family-restricted fastball/breaking/offspeed quality** — not proven non-identifiable, simply not yet tested (`LATENT_CONSTRUCT_INVENTORY.md`); listed here only to be explicit that "identifiable in the pooled/untyped form" is not the same claim as "identifiable per pitch family," and the latter remains open.
- **Deception, sequencing value, pitch aging/development trajectory, release consistency** — not tested this phase at all (see `LATENT_CONSTRUCT_INVENTORY.md` for each); listed here to avoid the appearance that silence means "identifiable."

## Observed evidence / Inference / Speculation

Every item in the first two sections above is Observed evidence (a direct, measured absence of a required field, or a directly measured near-zero/negative reliability figure with no rising trend). The third section mixes Observed evidence (the specific reliability numbers) with Inference (that a rising-but-incomplete trend suggests more data would help) — kept in the same section deliberately, since both are genuinely "not identifiable *yet*," distinguished from the first section's "not identifiable *from this data source, at any scale*."

## Future work

Re-test command/chase-rate reliability at substantially larger sample sizes (a natural Phase 2 candidate, since the trend is rising) before concluding they're unrecoverable rather than merely data-starved. Called-strike rate deserves a dedicated investigation into whether umpire- or catcher-level context (unavailable in this pilot) explains its flatness, before concluding it's simply not a pitcher signal.

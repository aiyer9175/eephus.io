# Latent Construct Inventory — Phase 1B

Deliverable 3. Candidate baseball constructs — not model outputs, hypotheses about what might be identifiable. Each entry: scientific definition, observable evidence, missing information, potential proxy, confidence, future validation required.

## Fastball quality
- **Definition**: the intrinsic, repeatable quality of a pitcher's fastball(s) — velocity, movement, and their interaction, independent of the batter/count/park context they're thrown in.
- **Observable evidence**: `avg_start_speed` and `avg_pfx_z`/`avg_pfx_x` restricted to `family == "fastball"` pitches, at tracked venues. Split-half reliability for the untyped (all-pitch-type) versions of these metrics is 0.91-0.98; the nested decomposition shows real between-pitcher variance in velocity (8.4 mph² at AAA) that survives even after accounting for family-level variance.
- **Missing information**: this phase computed family-level variance but did not re-run split-half reliability *restricted to the fastball family specifically* — the reliability figures above are pooled across all pitch types, not fastball-isolated. That's a real gap, not a forced conclusion.
- **Potential proxy**: mean fastball velocity + mean fastball induced vertical break, per pitcher, at tracked venues only.
- **Confidence**: Moderate-high for the "measurable and stable" half of the claim (physical fields are reliable); untested for the "fastball-specific" half.
- **Future validation required**: re-run `reliability_analysis.py`-style split-half restricted to `family == "fastball"` rows; test whether fastball quality specifically (not pooled velocity) predicts outcome-based results (whiff/damage) — not attempted this phase.

## Breaking-ball quality / Offspeed quality
- **Definition**: analogous to fastball quality, for slider/curve/cutter-family and changeup/splitter-family pitches respectively.
- **Observable evidence**: same underlying fields, restricted to `family == "breaking"` / `"offspeed"` — not separately re-run this phase (same gap as fastball quality above).
- **Missing information**: per-family sample sizes are smaller than the pooled sample (a pitcher who throws mostly fastballs has few breaking-ball observations), so per-family reliability is expected to require larger volume than this pilot's ~30-games/team pull provides for anything beyond a primary breaking pitch.
- **Potential proxy**: mean breaking/offspeed velocity, spin rate, and movement, per pitcher, per family, at tracked venues.
- **Confidence**: Low — untested, and expected to be lower-power than fastball quality given smaller per-pitcher sample sizes per secondary pitch.
- **Future validation required**: family-restricted reliability analysis with an explicit minimum-pitch-count gate per family (this pilot's `MIN_OBS_PER_GROUP = 5` for variance decomposition is almost certainly too low for a real reliability claim at the family level).

## Arsenal depth
- **Definition**: the number of distinct, viable pitch types a pitcher commands.
- **Observable evidence**: `families_observed` per pitcher is implicitly available in the underlying dataset (pitch_type_code → family mapping in `scripts/phase1b/metrics.py`) but was not aggregated into a per-pitcher arsenal-depth count this phase.
- **Missing information**: no distinction between a "viable" pitch type (thrown with real intent and effectiveness) and a rarely-used show-me pitch — a naive count would conflate these.
- **Potential proxy**: count of pitch families with ≥ some minimum usage share (e.g. ≥5% of pitches).
- **Confidence**: Untested.
- **Future validation required**: define and test a usage-share threshold; check whether arsenal depth predicts outcome metrics independent of the individual pitch-quality proxies above.

## Velocity talent
- **Definition**: a pitcher's underlying capacity for velocity, as distinct from any single pitch type's observed velocity (e.g., "how hard could this pitcher's fastball play if it were his only pitch").
- **Observable evidence**: closely related to (but not identical to) fastball quality above; this phase did not attempt to separate "talent" from "observed fastball velocity."
- **Missing information**: no independent measure of effort/max-effort vs. pitch-mix-averaged velocity.
- **Potential proxy**: max observed velocity per pitcher (rather than mean) as a talent ceiling proxy — not computed this phase.
- **Confidence**: Untested as a distinct construct from fastball quality.
- **Future validation required**: compare max-velocity-based and mean-velocity-based proxies for reliability and predictive value.

## Movement proxy
- **Definition**: the physical break/movement profile of a pitch, independent of velocity.
- **Observable evidence**: `avg_pfx_x`/`avg_pfx_z` — split-half reliability 0.91-0.98 (pooled across pitch types), between-pitcher ICC 12-35%.
- **Missing information**: same family-pooling caveat as fastball/breaking/offspeed quality above — movement varies enormously by pitch type, and this phase's reliability figures mix that in rather than isolating within-family movement consistency.
- **Potential proxy**: `avg_pfx_x`/`avg_pfx_z`, ideally family-restricted.
- **Confidence**: Moderate for "measurable and stable" (strong reliability numbers); low for "isolated from pitch-mix effects" (untested).
- **Future validation required**: family-restricted movement reliability, same as fastball/breaking/offspeed above.

## Command proxy
- **Definition**: a pitcher's ability to locate pitches to an intended target, as distinct from raw stuff.
- **Observable evidence**: `zone_rate` — split-half reliability only 0.07 (AAA) to 0.19 (Low-A) at the pilot's default minimum-pitch threshold, climbing to 0.50-0.67 only among the small subset of pitchers with 400+ tracked pitches (`RELIABILITY_STATS.json` stabilization curves). Nested variance decomposition shows residual (pitch-to-pitch) variance dominating (~0.244 of ~0.25 total) — between-pitcher and between-family variance are both small (<0.01 each).
- **Missing information**: no intended-target data exists in this or any public feed — `zone_rate` is a crude proxy (did the pitch land in the strike zone at all) not a true command measure (did it hit the intended target, in or out of zone). A pitcher intentionally locating just off the zone would score identically to one missing badly.
- **Potential proxy**: `zone_rate` is the best available proxy from this data source; a distance-based proxy (e.g., dispersion of `plate_x`/`plate_z` around a pitcher's own mean location, per pitch type) was not computed this phase.
- **Confidence**: **Low.** This is a genuine negative-leaning finding, not a data limitation being talked around — see `NON_IDENTIFIABLE_CONSTRUCTS.md`.
- **Future validation required**: test a dispersion-based command proxy instead of zone-rate; retest reliability at much larger sample sizes given the still-climbing stabilization curve.

## Execution quality
- **Definition**: how well a pitcher's actual pitch matches its intended shape and location on a given attempt — a combination of command and consistency.
- **Observable evidence**: not directly computed; would require a per-pitch execution-error measure this pilot doesn't have (no intended-target data, as above).
- **Confidence**: Untested, and likely **not identifiable** from public data without intended-target information — see `NON_IDENTIFIABLE_CONSTRUCTS.md`.

## Pitch interaction / Sequencing value
- **Definition**: value created (or lost) by how pitches are sequenced relative to each other and to count state, beyond each pitch's stand-alone quality.
- **Observable evidence**: count-state fields (`balls_pre`/`strikes_pre`) are present at every level (`ALL_LEVELS`), but no sequencing-specific metric was computed this phase.
- **Missing information**: a proper sequencing analysis needs within-plate-appearance pitch order, which exists in the raw feed (`playEvents` order) but wasn't extracted as a sequence-indexed feature in `build_pitch_dataset.py`.
- **Confidence**: Untested.
- **Future validation required**: extract within-PA pitch sequences; test whether sequencing patterns (e.g., fastball-then-breaking vs. breaking-then-fastball) predict outcomes beyond the individual pitches' stand-alone rates.

## Deception proxy
- **Definition**: how much a pitcher's release/tunneling makes pitches hard to distinguish pre-recognition.
- **Observable evidence**: none in this data source — deception/tunneling requires release-point consistency and early-flight-path data at a resolution this feed doesn't expose (see `NON_IDENTIFIABLE_CONSTRUCTS.md`).
- **Confidence**: Not identifiable from this data source.

## Pitch survivability / Development rate / Pitch aging
- **Definition**: how a pitcher's stuff or command changes over a season or career.
- **Observable evidence**: `season_third` exists in the dataset (early/mid/late) but within-season trajectory was not analyzed this phase; pitch aging across seasons needs multi-season data this pilot (single-season, 2025) doesn't have.
- **Confidence**: Untested this phase; explicitly out of scope for a single-season pilot.
- **Future validation required**: within-season trend analysis using `season_third`; multi-season pull for true aging curves (flagged in `PHASE_2_RECOMMENDATION.md`).

## Release consistency proxy
- **Definition**: how consistent a pitcher's release point is, pitch to pitch.
- **Observable evidence**: release coordinates (`x0`/`y0`/`z0`) are extracted by Phase 1A's field list and present in the raw feed at tracked venues, but not carried into Phase 1B's flattened dataset or analyzed.
- **Confidence**: Untested — a real gap, not a negative finding.
- **Future validation required**: add release-point fields to `build_pitch_dataset.py`, compute per-pitcher release-point dispersion, test reliability.

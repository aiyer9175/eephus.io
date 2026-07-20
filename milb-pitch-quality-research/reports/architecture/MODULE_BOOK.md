# Module Book

Required Final Deliverable. One-page-per-module reference compiling `MODULE_SPECIFICATIONS.md` + `PRODUCTION_CLASSIFICATION.md` + `ARCHITECTURE_SIMPLIFICATION.md`'s dispositions. Each entry is complete on its own; full evidence trails live in the cited source documents.

---

### Module 1 — Physical Stuff
**Question**: How good are this pitcher's pitches, physically? **Status**: redirected — see Implementation Phase A (`IMPLEMENTATION_ROADMAP.md`). Not scheduled as a standalone surface pending the `stuff_plus_aaa` reconciliation. **Confidence**: highest in this research (split-half r=0.91-0.99). **Classification**: Player Page Metric (if independent) / Production Feature (if integrated into `stuff_plus_aaa`). **Consumer**: none yet; `stuff_plus_aaa` is the candidate integration target. **Limitation**: sourced from a different public endpoint than `stuff_plus_aaa` uses — unreconciled.

### Module 2 — Arsenal Construction
**Question**: How is this pitcher's arsenal built? **Status**: Implementation Phase B (family-restricted reliability test required first). **Confidence**: real incremental information confirmed (largest single R² contributor to whiff rate, 0.071); own reliability untested. **Classification**: Production Feature, pending upgrade to Player Page Metric. **Consumer**: none yet; no existing system does this. **Limitation**: requires pitch-type identity, tracked venues only.

### Module 3 — Miss-Inducing Ability (tracked)
**Question**: Does this pitcher get swings and misses, and how much is stuff vs. something else? **Status**: Implementation Phase C. **Confidence**: moderate (split-half r=0.33-0.51), confirmed non-redundant with Modules 1-2. **Classification**: Player Page Metric. **Consumer**: none yet — first module scheduled to get one built, per the `milb-decision-plus` lesson. **Limitation**: ~77% of its own variance remains unexplained by every family tested.

### Module 3 variant — Outcome-Only Result Rate (Module 6)
**Question**: Does this pitcher miss bats, at a level with no tracking? **Status**: Implementation Phase C, alongside Module 3. **Confidence**: weak (R²=0.016 from its only predictor) — the thinnest module in this architecture, shipped anyway because it's the *only* coverage available at AA/High-A/untracked-Low-A. **Classification**: Player Page Metric, with a mandatory "limited signal" qualifier. **Consumer**: none yet. **Limitation**: cannot be pitch-type-specific; not comparable in magnitude to the tracked-branch version of the same concept.

### Module 4 — Ground-Ball Tendency
**Question**: Does this pitcher generate ground balls, and is that explained by movement? **Status**: Implementation Phase D (own-reliability test required first). **Confidence**: real relationship to Movement (R²=0.134, mostly from Movement specifically); own reliability untested. **Classification**: Research Metric, pending upgrade. **Consumer**: none yet; no existing system does this. **Limitation**: batted-ball-volume gated, on top of the tracking gate.

### Module 5 — Damage Suppression
**Question**: How hard is this pitcher hit when contact occurs? **Status**: **held back, not scheduled** (`ARCHITECTURE_SIMPLIFICATION.md`). **Confidence**: lowest of all modules — nearly unexplained by anything else measured (1.9-3.7% R²), own reliability untested, possible unaddressed confounds (park/defense/luck). **Classification**: Internal Diagnostic. **Consumer**: none, and none planned until status changes.

---

## Excluded constructs (not modules, evidence says no)

- **Command / zone rate** — Unsupported. r=0.07-0.19, weakest-tested construct across two phases.
- **Called-strike rate** — Unsupported. r=-0.10 to +0.06 everywhere — the clearest negative finding in this research.
- **A single universal composite** — architecturally rejected (`ARCHITECTURE_COMPARISON.md`), not a per-construct exclusion.

## Observed evidence / Inference / Speculation

Every entry's confidence figure is Observed evidence (Phase 1B/1C). Status/scheduling is this document's Inference, following `IMPLEMENTATION_ROADMAP.md`'s and `ARCHITECTURE_SIMPLIFICATION.md`'s reasoning.

## Future work

See `IMPLEMENTATION_ROADMAP.md` for phase-by-phase detail on closing each module's flagged gap.

# Engineering Standards

Phase 8. Formalizes the charter's Global Eephus Engineering Rule and the per-module standards list, scoped to this research's own modules. **Note on authority**: this document *proposes* these standards for repo-wide adoption, per the charter's own instruction ("this rule should become an Eephus-wide engineering standard") — but `eephus.io` has no root-level governance file (`CLAUDE.md`/`AGENTS.md`; confirmed absent, Phase 1A reconnaissance) for this research to amend, and creating one repo-wide is a decision beyond a research charter's authority. This document is written so it's ready to be adopted as-is if whoever owns repo governance chooses to.

## The Global Eephus Engineering Rule (restated as a checklist)

A model/module is complete only when **all** of the following hold:

- [ ] Has a real, named downstream consumer (not a documented intention — `milb-decision-plus/` is the standing counter-example, `CURRENT_ECOSYSTEM_MAP.md`).
- [ ] Is integrated into production (wired into `run_monthly.py`/`build_site.py`/the publish manifest, not just committed to a repo).
- [ ] Its consumer is validated (the consuming code actually reads and displays/uses the value correctly).
- [ ] Its interfaces are versioned (`DATA_CONTRACTS.md`'s semver scheme).
- [ ] Refresh behavior is defined (`REFRESH_EXECUTION_PLAN.md`).
- [ ] Uncertainty is preserved end-to-end (`UNCERTAINTY_ARCHITECTURE.md`'s propagation design, not simple inheritance).
- [ ] Regression tests exist (schema validation at minimum, per `IMPLEMENTATION_DEPENDENCIES.md`'s testing section).
- [ ] Documentation matches implementation (glossary + model registry entries reflect the actual shipped fields, not an aspirational set).

## Per-module standards

- **Single responsibility**: each of the 6 modules answers exactly one baseball question (`MODULE_SPECIFICATIONS.md`'s own framing) — no module should grow a second, unrelated responsibility without becoming a new module.
- **Versioned interfaces**: `DATA_CONTRACTS.md`'s semver scheme, non-negotiable.
- **Schema validation**: every published JSON validated against its contract before publish — a new pytest-gate check, following `milb-projections/tests/test_fixtures_match_contracts.py`'s pattern.
- **Regression tests**: `test_generated_docs_in_sync.py`-style byte-compares for anything auto-generated; a determinism check (re-run produces identical output) for every pipeline stage — directly reusing this research's own pilot convention (verified in Phase 1A/1B/1C, every deterministic re-run confirmed byte-identical).
- **Deterministic builds**: every module's computation must be seeded/deterministic (already true throughout this research's pipeline — no random sampling without a fixed seed anywhere in `scripts/`).
- **Consumer validation**: see `CONSUMER_VALIDATION.md`.
- **Documentation**: glossary + model registry entries, kept in sync (enforced by the same regression-test mechanism above).
- **Monitoring hooks**: freshness stamps (`model_registry.py`'s existing convention), reused not reinvented.
- **Explicit uncertainty**: no module ships a bare point estimate where a reliability figure exists to attach — and, per `MODULE_INTERFACES.md`'s discipline, no module ships a *fabricated* reliability figure where none has been tested (Modules 2, 4 currently have no confidence field, correctly).
- **Explicit reliability**: same standard, using this research's Phase 1B/1C methodology (split-half, month-to-month, stabilization curves) as the required evidentiary bar before any confidence claim.
- **No hidden dependencies**: every module's dependency on another module (per `MODULE_INTERACTION.md`'s DAG) is declared in its interface (`MODULE_INTERFACES.md`), not implicit in shared code.
- **No hard-coded paths**: `scripts/common.py` already follows this (configurable `DATA_CACHE`/`REPORTS_DIR` via `Path(__file__)`-relative resolution, no absolute username-bearing paths) — every future module must match, mirroring `milb-projections/adapters/*.py`'s own "never a hardcoded absolute path containing a username" rule (`ARCHITECTURE.md`, `milb-projections`).
- **No silent failures**: `REFRESH_EXECUTION_PLAN.md`'s failure-isolation design (each module fails independently and reports its own status) is the concrete mechanism; a module that silently returns `null`/empty rather than erroring on a genuine failure violates this standard.
- **No undocumented transformations**: every derived field (e.g., `is_whiff` from `call_description`) has its derivation logic in one place (`IMPLEMENTATION_DEPENDENCIES.md`'s shared-feature-engineering point) and is named in `DATA_CONTRACTS.md`, not buried in an unexplained one-liner.

## Observed evidence / Inference / Speculation

The checklist items are a direct restatement of the charter's own governing rule (not a new empirical claim). The "reuse X, don't reinvent" specifics throughout are Observed evidence (each named mechanism is a real file in this repo). The authority caveat at the top is this document's own honest acknowledgment of its scope limits — Inference about what a research charter can and cannot bind.

## Future work

If this document's standards are adopted repo-wide, the natural next step is a root-level `CLAUDE.md`/`AGENTS.md` codifying them for every package, not just this research's modules — explicitly flagged as a decision for whoever owns that, not something this charter presumes to enact.

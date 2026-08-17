# Program 0 Certification

Recorded: 2026-08-16. This is Program 0's instance of the reporting standard
in `docs/CERTIFICATION_STANDARD.md`.

## Summary block

```
PROGRAM: Program 0 -- Claude Code Bootstrap, Research Architecture,
         Mathematical Governance, and Certification
VERDICT: CERTIFIED

DATA:            infrastructure only -- no research dataset acquired or used
OBSERVATIONS:    NOT_APPLICABLE (no dataset)
PLAYERS:         NOT_APPLICABLE (no dataset)
SEASONS:         NOT_APPLICABLE (no dataset)

PRIMARY ENDPOINT: infrastructure exists, is tested, and detects deliberately
                   introduced problems (Part BV)
RESULT:            126 tests pass, 0 fail, 97% statement coverage of
                   src/eephus_research; all 10 required deliberate-failure
                   fixtures fail for the right reason, all 10 good
                   counterparts pass

COMPUTATIONAL VALIDITY: PASS (Layer 1 -- unit/invariant/regression tests pass;
                         see docs/RESEARCH_CONSTITUTION.md)
STATISTICAL VALIDITY:   NOT_APPLICABLE (no empirical claim made by this program)
CONSTRUCT VALIDITY:     NOT_APPLICABLE (no construct defined by this program)
PRODUCTION READINESS:   NOT_APPLICABLE (infrastructure is not a shippable model)

TESTS:         126 passed, 0 failed (pytest, this repository's .venv)
CERTIFICATION: CERTIFIED (see gate table below; all critical gates PASS)

BLOCKERS: none

PRODUCTION FILES MODIFIED: none (verified via git status on the main
                            eephus.io worktree -- clean)
GITHUB MODIFIED: none (no commit, no push, no remote branch created)
```

## Gate table

Statuses use the vocabulary from `CLAUDE.md` J4. Critical gates are marked
**yes**; per `docs/CERTIFICATION_STANDARD.md` ("No averaged certification"),
a single failed critical gate would block `CERTIFIED` regardless of how many
other gates pass. None did.

| Gate | Description | Status | Critical | Notes |
|---|---|---|---|---|
| P0-01 | Machine state documented | PASS | no | `docs/MACHINE_STATE.md` |
| P0-02 | Repositories inventoried | PASS | no | `docs/REPOSITORY_INVENTORY.md`, `docs/repository_inventory.json` |
| P0-03 | Production boundary established | PASS | no | `docs/DATA_GOVERNANCE.md`, `CLAUDE.md` J5, enforced in code by `provenance.manifest.assert_not_production_path` |
| P0-04 | Workbench isolated | PASS | no | `eephus-stuff-research/` is a distinct top-level directory; see decision `D-001` for why it's inside `eephus.io` rather than standalone |
| P0-05 | Git safe | PASS | no | No destructive git operations run; no force-push, no reset, no remote write |
| P0-06 | Python environment reproducible | PASS | no | `.venv/`, `pyproject.toml`, `requirements.lock.txt`; all imports verified |
| P0-07 | Claude operating contract present | PASS | no | `CLAUDE.md` |
| P0-08 | Claim registry valid | PASS | no | `registry/claims/C-001.yaml`, validated against schema in `tests/certification/test_registry_schema.py` |
| P0-09 | Decision registry valid | PASS | no | `registry/decisions/D-001.yaml`, `D-002.yaml`, `D-003.yaml`, schema-validated |
| P0-10 | Experiment registry valid | PASS_WITH_FINDINGS | no | Structure + schema + `TEMPLATE.yaml` exist; zero real entries, correctly, since Program 0 runs no experiments |
| P0-11 | Dataset registry valid | PASS_WITH_FINDINGS | no | Structure + schema + `TEMPLATE.yaml` exist; zero real entries, correctly, since Program 0 acquires no data |
| P0-12 | Provenance manifest works | PASS | no | `src/eephus_research/provenance/manifest.py`; round-trip, tamper-detection, and production-path-guard tests pass |
| P0-13 | Schema validation works | PASS | no | `src/eephus_research/validation/schema.py`; missing-column, duplicate-key, nullable, dtype, and range violations all tested |
| P0-14 | Mathematical invariant testing works | PASS | no | `src/eephus_research/validation/identities.py`; includes the specific "high correlation, wrong identity" case Part S warns about |
| P0-15 | Split-leakage detection works | PASS | no | `src/eephus_research/diagnostics/splits.py`, `diagnostics/leakage.py`; 5 split regimes, overlap assertion tested |
| P0-16 | Pitcher-overlap detection works | PASS | no | `diagnostics.leakage.check_group_overlap` + `diagnostics.splits.pitcher_grouped_split`, tested with a synthetic pitcher-clustered fixture |
| P0-17 | Target-leakage test works | PASS | no | `diagnostics.leakage.check_exact_target_leakage`, tested on an identical-column fixture |
| P0-18 | Determinism test works | PASS | no | `utils/seed.py` + `tests/certification/test_deliberate_failures.py` cases 6a/6b (unseeded-global vs. seeded-generator) |
| P0-19 | Failure fixtures fail correctly | PASS | **yes** | All 10 required Part BV fixtures (`tests/fixtures/bad/*`) fail for the documented reason |
| P0-20 | Valid fixtures pass | PASS | **yes** | All 10 corresponding good fixtures (`tests/fixtures/good/*`) pass |
| P0-21 | Certification framework works | PASS | no | `src/eephus_research/certification/gates.py`; "no averaged certification" behavior directly tested |
| P0-22 | Beginner guide complete | PASS | no | `docs/BEGINNER_OPERATIONS.md` |
| P0-23 | Identity-reconstruction audit hook present | PASS | no | `src/eephus_research/diagnostics/identity_audit.py`; generic building blocks tested with synthetic group labels, not run against any real model (none exists) |
| P0-24 | No Stuff model fit | PASS | **yes** | No model artifact of any kind exists in this workbench; `tests/certification/test_program0_structure.py::test_no_stuff_model_artifact_present` enforces this by scanning for `.pkl`/`.joblib`/`.onnx`/`.h5` files |
| P0-25 | Production files unchanged | PASS | **yes** | `git status` on the main `eephus.io` worktree is clean; only `eephus-stuff-research/` (new) and the pre-existing, pre-Program-0 `milb-pitch-quality-research/` (untouched, per decision `D-002`) are untracked |
| P0-26 | No remote write performed | PASS | **yes** | No commit was made this session (`HEAD` unchanged at `d63eb7b9`); no `git push`; the working branch has no corresponding remote ref |

**Verdict: CERTIFIED.** All five critical gates (`P0-19`, `P0-20`, `P0-24`,
`P0-25`, `P0-26`) pass.

## Self-audit (Part BW)

Answered honestly, including where the answer is "yes, and here is the
residual risk" rather than a reassuring "no":

1. **Can a future researcher accidentally train on validation data?**
   Partially mitigated, not prevented. `FitOnTrain` (Part AG) raises if
   `.transform()` is called before `.fit()`, and the leakage/split modules
   catch group and row overlap when actually invoked -- but nothing stops a
   researcher from writing raw `sklearn` calls that bypass these wrappers
   entirely. Mitigation is real but not enforced at the language level.

2. **Can a derived dataset lose its provenance?** Yes, if a researcher
   forgets to register a `registry/datasets/DS-NNN.yaml` entry for it.
   `provenance/manifest.py` can build a manifest entry automatically, but
   nothing forces every write to go through it. This is a process
   obligation (`CLAUDE.md`, `docs/DATA_GOVERNANCE.md`), not a hard gate.

3. **Can a mathematical formula change without a regression signal?** Yes,
   for any formula nobody wrote an invariant test for.
   `validation/identities.py` makes it cheap to write that test; it doesn't
   retroactively cover formulas that don't exist yet.

4. **Can a result be reported without an experiment ID?** Yes, technically
   -- nothing blocks writing a report that skips `registry/experiments/`.
   This is enforced by convention (`CLAUDE.md` J6) and by
   `tests/certification/test_registry_schema.py` validating whatever *does*
   get registered, not by preventing unregistered work from happening.

5. **Can a public claim be unsupported by an artifact?** This one was
   fixed during Program 0's own self-audit, not just documented:
   `schemas/claim.schema.json` now requires that any claim asserted
   `PASS`/`PASS_WITH_FINDINGS`/`FAIL` point at a non-empty
   `artifact_refs`/`code_refs`/`dataset_refs`/`experiment_refs` list, not
   just a prose `evidence` string. See
   `tests/certification/test_claim_evidence_linkage.py`.

6. **Can pitcher overlap occur unnoticed?** Only if the researcher never
   calls `diagnostics.leakage.check_group_overlap` or
   `diagnostics.splits.assert_no_group_overlap`. The tools exist and are
   tested; invocation is not automatic.

7. **Can production files be modified during research accidentally?**
   Mitigated for anything routed through `provenance.manifest`'s write
   functions (`assert_not_production_path` raises `ProductionPathError`,
   tested against every known production directory name). Not mitigated
   for a direct `open(...)`/`df.to_csv(...)` call that bypasses those
   functions entirely -- this is a real gap for a future program to close,
   e.g. by routing all writes through a single audited helper.

8. **Can one failed critical gate be hidden by an aggregate pass count?**
   No. `GateTable.verdict()` checks `failed_critical_gates()` explicitly and
   never computes or exposes a pass-rate number. Directly tested
   (`tests/unit/test_gates.py::test_no_averaged_certification_...`).

9. **Can raw data be overwritten?** No technical prevention exists yet
   (e.g. no read-only file permissions after ingestion) -- `data/raw/` is
   currently empty, so this is a gap to close when a future program
   actually acquires raw data, not before.

10. **Can a prior numerical result be inherited without reproduction?**
    Mitigated by `certification/reproduction_gate.py` and `CLAUDE.md` J2,
    but only if a researcher chooses to run the gate. Not automatically
    enforced.

11. **Can post-hoc analysis masquerade as preregistered?** Nothing
    programmatically stops editing an experiment YAML's original fields
    after the fact beyond convention (`registry/experiments/README.md`) and
    ordinary git history review. A future program's certification should
    diff a experiment's file history against its `status`, not just trust
    the current file content.

12. **Can benchmark data contaminate model training unnoticed?** The
    `benchmark` field's enum (including `PROHIBITED_FROM_MODEL`) exists in
    `schemas/experiment.schema.json`, but nothing cross-checks a model's
    actual feature list against that classification. Declarative, not
    enforced.

13. **Can a Stuff model later evade the pitcher-identity reconstruction
    audit?** The hook (`diagnostics/identity_audit.py`) exists and is
    documented as mandatory in `docs/STATISTICAL_GOVERNANCE.md` and
    `docs/CERTIFICATION_STANDARD.md`. Enforcement is at the certification
    gate / human-review level -- a future program's gate table should
    include an explicit identity-audit gate, and that gate should be
    marked critical.

**Net finding:** most residual risk in this list is "the tool exists and is
tested, but nothing forces a researcher to use it." That is an accurate
description of what infrastructure alone can guarantee -- see
`docs/RESEARCH_CONSTITUTION.md`'s framing that passing software tests is
never proof a scientific claim is correct. The concrete, cheap fix found
(item 5) was applied immediately rather than only logged.

## Test results

```
126 passed, 0 failed
97% statement coverage of src/eephus_research (571 statements, 18 missed)
```

Command used (from `eephus-stuff-research/`):
`./.venv/Scripts/python.exe -m pytest -q --cov=src/eephus_research --cov-report=term-missing`

Test class breakdown: `tests/unit` (function-level correctness),
`tests/invariants` (mathematical identities + Hypothesis property tests),
`tests/regression` (seed consistency, manifest-baseline tamper detection),
`tests/integration` (schema-validation-then-leakage-audit pipeline),
`tests/statistical` (split regimes, simulation recovery, reliability,
clustering, identity-audit building blocks), `tests/certification` (the
required Part BV deliberate-failure harness, registry schema validation
against real files, structural self-check, the claim-evidence-linkage fix).

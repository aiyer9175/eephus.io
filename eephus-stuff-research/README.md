# eephus-stuff-research

Quantitative research infrastructure for Eephus, built by **Program 0** of the
Eephus Quantitative Research Workstation. This is **infrastructure only** — no
Stuff/pitch-quality model has been built, fit, tuned, selected, or evaluated
here. See `docs/PROGRAM_0_CERTIFICATION.md` for the certification record and
`P0-24 STUFF MODEL FIT: NOT_ATTEMPTED`.

## What this is

A research system that makes errors difficult to introduce silently, easier
to detect, reproducible, attributable to a precise pipeline stage, reviewable
by another researcher, and distinguishable as computational, statistical, or
scientific failures. It exists because passing software tests is never proof
that a scientific claim is correct — see `docs/RESEARCH_CONSTITUTION.md`.

## Where this lives and why

This directory is a top-level folder inside the production `eephus.io`
repository, on a research branch — the same pattern already used by
`defense-plus/`, `swing-plus/`, `milb-decision-plus/`, `playing-time-model/`,
and `milb-projections/`, all of which started as branch-based research and
were later merged to `main`. See `docs/repository_inventory.json` and
`registry/decisions/D-001.yaml` for why this location was chosen over a
standalone repository. `main` and every already-shipped model directory
remain **production** and are **read-only** to this research program.

## Start here

- New to this, or new to Claude Code entirely? Read `docs/BEGINNER_OPERATIONS.md` first.
- Picking up a research thread? Read `docs/MACHINE_STATE.md` and
  `docs/REPOSITORY_INVENTORY.md`, then the relevant entries in `registry/`.
- About to make a scientific claim? Read `docs/RESEARCH_CONSTITUTION.md` and
  `docs/CERTIFICATION_STANDARD.md` before you start, not after.
- About to do statistics? Read `docs/STATISTICAL_GOVERNANCE.md`.
- About to define or transform a quantity with units? Read
  `docs/MATHEMATICAL_GOVERNANCE.md`.
- About to bring in or export data? Read `docs/DATA_GOVERNANCE.md`.

## Layout

```
eephus-stuff-research/
├── README.md, CLAUDE.md, pyproject.toml, requirements.lock.txt, .gitignore
├── config/            research.yaml, paths.example.yaml, logging.yaml
├── docs/               governance, machine state, inventory, standards
├── registry/           claims/ decisions/ experiments/ datasets/ models/
├── schemas/             JSON Schemas for every registry type
├── data/                external/ raw/ interim/ processed/ manifests/
├── src/eephus_research/ io/ validation/ statistics/ diagnostics/
│                        provenance/ certification/ utils/
├── experiments/, notebooks/, reports/, artifacts/
└── tests/               unit/ invariants/ regression/ integration/
                          statistical/ certification/ fixtures/{good,bad}/
```

## Environment

```
cd eephus-stuff-research
python -m venv .venv          # already done for this session; see docs/BEGINNER_OPERATIONS.md
./.venv/Scripts/python.exe -m pip install -e ".[dev]"   # Windows / Git Bash
pytest
```

Python 3.14.5, pinned in `.python-version`. Dependencies are declared in
`pyproject.toml` and locked in `requirements.lock.txt`. See
`docs/BEGINNER_OPERATIONS.md` for the full walkthrough, including what
"clean" `pytest` output should look like.

## The next program

**Stuff Research Program 1** — construct, target, data, and falsification
design. Not started here. See the final report in this program's transcript
and `docs/PROGRAM_0_CERTIFICATION.md` for what it inherits.

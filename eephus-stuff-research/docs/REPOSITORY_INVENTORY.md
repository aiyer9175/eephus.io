# Repository Inventory

Recorded: 2026-08-16. Read-only archaeology; nothing in this document's
production was modified to produce it. Machine-readable twin:
`repository_inventory.json`.

## Repositories found

Only one Eephus repository was found on this machine: `eephus.io`, checked
out as three worktrees of the same underlying `.git`. No other Eephus
repository (by name, remote URL, or content) was found. This search covered
the current worktree, its sibling worktrees, and the parent directory
structure visible from them; it was not an exhaustive whole-filesystem crawl
of every drive.

### 1. `eephus.io` (production) — main worktree

| Field | Value |
|---|---|
| Absolute path | `C:/Users/ciaci/New folder/codex/eephus.io` |
| Git status | clean at time of writing |
| Branch | `main` |
| Remotes | `origin` → `https://github.com/aiyer9175/eephus.io.git`; `upstream` → `https://github.com/arkhdji/eephus.io.git` |
| Last commit | `d63eb7b9` 2026-08-07 "Close the last plan item: three UI suspects, one reproduces, and it has one pixel of room" |
| Purpose | The live application. `prospect-tracker/` (PROSPX) is the flagship module — prospect rankings, college leaderboards, draft tools. |
| Production? | **Yes.** This is what the README describes as the deployed site. |
| Contains research? | Yes — several directories that read as "research that shipped": `defense-plus/`, `swing-plus/`, `milb-decision-plus/`, `playing-time-model/`, `xRV models/`, `advancement_pace/`, `milb-projections/`. |
| Contains datasets? | Yes — `NCAA 26 Averages S+.csv` (~6.1 MB) and a fitted `xwoba_model.pkl` (~1.75 MB) sit at repo root. |
| Contains pitching infrastructure? | Yes, indirectly — `milb-projections/` (see below) is a governance/export layer for a *future* pitch-quality model, not the model itself. |

Production model directories and their last touch:

| Directory | Last commit | Date |
|---|---|---|
| `defense-plus/` | `ece03efe` | 2026-06-24 |
| `swing-plus/` | `347100cb` | 2026-06-24 |
| `milb-decision-plus/` | `ece03efe` | 2026-06-24 |
| `playing-time-model/` | `00ce565e` | 2026-06-13 |
| `xRV models/` | `e3322dde` | 2026-05-17 |
| `advancement_pace/` | `c214d017` | 2026-07-17 |
| `milb-projections/` | `9b888b71` | 2026-07-18 |
| `prospect-tracker/` | `d63eb7b9` | 2026-08-07 |

**Pattern observed:** every one of these started as a topic-branch research
directory and was merged into `main` as a top-level folder. This is the
precedent the operator chose to follow for `eephus-stuff-research/` (decision
`D-001`).

### 2. `eephus.io` — this worktree (Program 0 session)

| Field | Value |
|---|---|
| Absolute path | `.../.claude/worktrees/milb-pitch-quality-research-e53bba` |
| Branch | `claude/eephus-research-infrastructure-47aa1e` |
| Remotes | same `origin`/`upstream` as above (shared `.git`) |
| Last commit | `d63eb7b9` (branched from the same tip as `main` at time of writing) |
| Purpose | This Program 0 session. `eephus-stuff-research/` is being created here. |
| Production? | No — but it is a checkout of the production repository, so anything committed here is one `git push`/merge away from production. Treat with the same care. |

### 3. `eephus.io` — sibling worktree (unrelated, do not touch)

| Field | Value |
|---|---|
| Absolute path | `.../.claude/worktrees/project-structure-setup-ad3fd2` |
| Branch | detached HEAD at `71ea151f` |
| Last commit | `71ea151f` "prospx: preserve sort-header keyboard focus across board re-renders (a11y fix) + doc sync" |
| Purpose | A different, unrelated Claude Code session doing site-restructuring/a11y work on PROSPX. Not touched by Program 0. |

## Orphaned prior work found in this worktree

Two pieces of prior work directly relevant to a future pitch-quality model
were found. Per the operator's decision (`D-002`), **neither was modified,
merged, or deleted** — they are documented here for future reference only.

### A. `milb-pitch-quality-research/` — physically present, untracked here

This directory sits at the top of this worktree
(`.../milb-pitch-quality-research-e53bba/milb-pitch-quality-research/`) but
is **untracked on the currently checked-out branch**
(`claude/eephus-research-infrastructure-47aa1e`). It is leftover from a prior
session that worked on a different branch,
`claude/milb-pitch-quality-research-e53bba` (note: this is the branch the
worktree *directory* was originally named for — see the naming trap in
`MACHINE_STATE.md`).

What's physically on disk right now:

| Path | Contents | Size |
|---|---|---|
| `milb-pitch-quality-research/data_cache/{AA,AAA,High-A,Low-A}/` | Raw MLB Stats API game-feed JSON, one file per game ID | ~1400 files |
| `milb-pitch-quality-research/data_cache/derived/` | `pitch_dataset.parquet`, `pitch_dataset_v2.parquet`, `pitcher_family_table.csv` (gitignored by a nested `.gitignore` that ships with that branch's tree) | — |
| `milb-pitch-quality-research/data_cache/{schedules,samples}/` | Supporting schedule/sample data | — |
| `milb-pitch-quality-research/scripts/`, `scripts/phase1b/`, `scripts/phase1c/` | Python analysis scripts (plus stale `__pycache__/`) | — |
| **Total on disk** | | **~1.0 GB** |

File modification times cluster around 2026-07-20, matching that branch's
last commit date — this is roughly four weeks old, not something generated
earlier in the current session.

What is **not** physically present, but does exist in git history on
`origin/claude/milb-pitch-quality-research-e53bba` (last commit `4c5de9d8`,
2026-07-20, "MiLB pitch-quality research: Engineering Charter (architecture
freeze, interfaces, Module 1 readiness)"): `README.md`, `DECISION_LEDGER.md`,
`PILOT_SCOPE.md`, and a `reports/` tree including `ARCHITECTURE_MAP.md`,
`COVERAGE_MATRIX.{md,json}`, `DATA_AUDIT_REPORT.md`,
`FIELD_AVAILABILITY_MATRIX.{md,json}`, `MISSINGNESS_MATRIX.{md,json}`,
`TRUST_MATRIX.{md,json}`, and a further `reports/architecture/` tree with
~20 documents (dependency graph, module book, final architecture ruling,
known gaps, etc.) — 84 tracked files total. **These are not lost; they are
safe in git history on that branch/remote.** They are simply not checked out
in this worktree right now.

Commit sequence on that branch (newest first): "Engineering Charter" →
"Architecture & Integration Charter" → "Phase 1C incremental information,
redundancy, architecture finalization" → "Phase 1B identifiability,
information content, noise isolation" → "Phase 1 data audit pilot" → branches
off the same production history as everything else.

**Interpretation:** a prior session got through a Phase 1 data-audit and
architecture-design stage for a MiLB pitch-quality model, spent real API
calls building a ~1 GB local cache, and then the work stopped (last commit
2026-07-20, no merge to `main`). It was neither finished nor abandoned in a
way that's visible from here — `NOT_MEASURED` whether it was intentionally
paused or simply superseded by a new task. The operator chose (`D-002`) to
leave this alone rather than fold it into Program 0, so it remains exactly as
found. A future program that wants to resume pitch-quality research proper
should treat `origin/claude/milb-pitch-quality-research-e53bba` as a
candidate starting point worth reviewing before starting over, and should
decide deliberately whether the ~1 GB cache here is worth reusing (it is
real API data, not synthetic, but its provenance/freshness has not been
audited by this program).

### B. `milb-projections/` (on `main`) — a builder handoff package, not a model

Originally added as `milb-pitch-quality-handoff/` (commit `d2406e66`,
"Add MiLB pitch-quality handoff: reconnaissance, inventory, scaffolding"),
built out over 15 phases, then renamed to `milb-projections/` (commit
`9b888b71`, 2026-07-18) and merged to `main`. **This is not a Stuff model.**
Its own `README.md` states explicitly: *"No arsenal/Stuff+/Command+ model
exists yet anywhere in Eephus... building it is future, out-of-charter
work."*

What it actually is: a packaging layer exporting Eephus-specific assets
(model outputs, schemas, methodology, identity mappings, park factors,
governance rules) so an *external builder* can independently research a MiLB
pitch-quality/arsenal proxy system without reverse-engineering the existing
Eephus pitcher ecosystem. It includes, among other things, a
`PITCH_QUALITY_RESEARCH_CONTRACT.md` that defines four levels of signal
(observed effectiveness → context-adjusted effectiveness → stable
pitcher-by-pitch-type signal → latent arsenal quality), a required reliability
program, and a list of required negative controls (shuffled pitcher identity,
park-only model, tracking-source-only model, etc.).

Per the operator's decision (`D-003`), Program 0's own governance documents
were written **self-contained**, without deferring to or restating
`milb-projections/PITCH_QUALITY_RESEARCH_CONTRACT.md`. A future Stuff
Research Program should read that document directly — it is
domain-specific in a way this generic infrastructure program is not, and the
two are complementary rather than duplicative: `milb-projections/` defines
*what the pitch-quality construct must not collapse into*; Program 0's
`eephus-stuff-research/` defines *the infrastructure that makes errors hard
to introduce silently*, for whatever gets built next.

## Existing datasets found

| Dataset | Location | Notes |
|---|---|---|
| `NCAA 26 Averages S+.csv` | `eephus.io/` root | ~6.1 MB, production |
| `xwoba_model.pkl` | `eephus.io/` root | ~1.75 MB, fitted production model artifact |
| MiLB game-feed JSON cache | `milb-pitch-quality-research/data_cache/` (this worktree, untracked) | ~1 GB, see above |

No other datasets were found during this read-only pass. This was not an
exhaustive scan of every subdirectory's contents (e.g. `prospect-tracker/`'s
internal data pipeline was not enumerated file-by-file) — only top-level and
directly-relevant paths were inventoried.

## Existing configuration / virtual environments / remotes

- No project-local Python virtual environment was found anywhere in
  `eephus.io` prior to this program.
- Git remotes are limited to `origin` and `upstream`, both pointed at GitHub;
  no other remotes (no local bare repos, no additional forks) were found.
- No `.env` or credential files were found at the top level of the main
  worktree (see the caveat about scan depth in `MACHINE_STATE.md`).

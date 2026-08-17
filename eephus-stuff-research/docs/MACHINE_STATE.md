# Machine State

Recorded: 2026-08-16, at the start of Program 0 (Claude Code Bootstrap).
This document is a snapshot. It will go stale. Do not treat it as current
without re-running the commands below.

## Operating system

```
MINGW64_NT-10.0-19045 DESKTOP-L29G9S8 3.6.9-b4195d69.x86_64 2026-06-06 Msys
```

- Windows 10 Home, build 19045
- Shell surfaced to Claude Code: Git Bash (MSYS2) for the `Bash` tool, Windows
  PowerShell 5.1 for the `PowerShell` tool. Both are available; this program
  used Bash for all commands recorded here.
- CPU architecture: x86_64

## Python

| Field | Value |
|---|---|
| Version | 3.14.5 |
| Executable | `C:\Users\ciaci\AppData\Local\Python\pythoncore-3.14-64\python.exe` |
| `venv` module | available |
| pip | 26.1.1 |

`python`, `python3`, and `py` all resolve to the same 3.14.5 install — there is
only one Python on this machine's PATH. No pyenv/conda/asdf version manager
was detected.

## Package managers

- `pip` 26.1.1 (bundled with the Python 3.14 install)
- No `poetry`, `uv`, `conda`, or `pipenv` checked for or assumed. If a future
  session wants one, verify it is actually installed before using it.

## Git

```
git version 2.55.0.windows.3
```

- Git user configured at the repo/global level was not modified or inspected
  beyond what `git log` authorship shows (out of scope for read-only
  archaeology; do not assume identity from commit authorship alone).

## Claude Code

`claude --version` was not resolvable from the Bash tool's PATH inside this
sandboxed session (`command not found`). This does not mean Claude Code is
absent from the machine — this session is itself a Claude Code session,
launched by a harness that does not necessarily expose its own binary on the
Bash tool's PATH. Treat the exact CLI version as `NOT_MEASURED` from inside
this session; if it matters, the operator should run `claude --version` from
their own terminal.

## Disk

```
Filesystem      Size  Used Avail Use%
C:              466G  429G   37G  93%
```

37 GB free on the `C:` drive at time of writing. The drive is 93% full. This
is relevant to Part BI (large-data handling): do not casually duplicate
multi-gigabyte datasets on this machine without checking free space first.

## Working directory and worktree structure

Current working directory for this session:

```
C:\Users\ciaci\New folder\codex\eephus.io\.claude\worktrees\milb-pitch-quality-research-e53bba
```

This is a **git worktree**, not an independent repository. `git worktree list`
shows three worktrees sharing one repository:

| Path | HEAD | Branch |
|---|---|---|
| `C:/Users/ciaci/New folder/codex/eephus.io` | d63eb7b9 | `main` |
| `.../.claude/worktrees/milb-pitch-quality-research-e53bba` (this session) | d63eb7b9 | `claude/eephus-research-infrastructure-47aa1e` |
| `.../.claude/worktrees/project-structure-setup-ad3fd2` | 71ea151f | detached HEAD (site-restructuring work, unrelated to pitch quality) |

**Important naming trap:** this worktree's directory is named
`milb-pitch-quality-research-e53bba`, but the branch actually checked out here
is `claude/eephus-research-infrastructure-47aa1e` — a different branch than
the one the directory name suggests (`claude/milb-pitch-quality-research-e53bba`).
The directory name is leftover from how the worktree was originally
provisioned; it is not a live indicator of what branch is checked out. See
`REPOSITORY_INVENTORY.md` for what that means for files physically sitting in
this directory.

## Current working directory is inside a production repository

`eephus.io` is not a scratch machine — it is the production Eephus repository
(remote `origin` → `https://github.com/aiyer9175/eephus.io.git`, also has an
`upstream` remote → `https://github.com/arkhdji/eephus.io.git`). Its `main`
branch contains the live site (`prospect-tracker/`, the PROSPX module) and
several already-shipped model directories (`defense-plus/`, `swing-plus/`,
`milb-decision-plus/`, `playing-time-model/`, `xRV models/`,
`milb-projections/`, plus a top-level `xwoba_model.pkl`).

Per the operator's decision (recorded as `D-001` in the decision registry),
the new Program 0 research workbench is being created **inside** this
repository, as a new top-level directory (`eephus-stuff-research/`), on the
current feature branch — matching the pattern already established by
`defense-plus/`, `swing-plus/`, `milb-decision-plus/`, `playing-time-model/`,
and `milb-projections/`, all of which appear to have started as research
directories on branches and were later merged to `main`.

`main` and any already-shipped model directory remain **production** and are
**read-only** for this program. See `docs/DATA_GOVERNANCE.md` and
`docs/RESEARCH_CONSTITUTION.md` for the enforced boundary.

## Existing configuration / secrets scan

A shallow, read-only, top-level-only scan of the main `eephus.io` worktree for
`.env*`, `*credential*`, `*secret*` files at the repository root found none.
This was **not** a recursive or exhaustive secrets scan — it only checked the
top level of the main worktree. Do not treat this as a clearance for the rest
of the tree; a full secret scan was out of scope for Program 0's read-only
archaeology phase and would need its own pass before anything in this
repository is made more widely available.

## Existing virtual environments

None found or created prior to this program. `eephus-stuff-research/` gets its
own project-local `.venv/` as part of this program (Part I); see
`docs/BEGINNER_OPERATIONS.md` for how to activate it.

## Existing Stuff-model work

See `REPOSITORY_INVENTORY.md` for the full detail. Summary: **no fitted
Stuff/Command/pitch-quality model exists anywhere in this repository.** There
is substantial *governance and reconnaissance* work adjacent to it (a merged
handoff package at `milb-projections/`, and an abandoned Phase-1 research
effort on branch `claude/milb-pitch-quality-research-e53bba` whose data cache
is still sitting on disk in this worktree). Program 0 does not touch, fit, or
evaluate any model — see `P0-24` in the certification report.

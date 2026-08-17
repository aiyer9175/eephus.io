# Beginner Operations Guide

Written for someone new to Claude Code, terminal workflows, Git, or Python
project structure. If you already know these tools, skip to
`REPOSITORY_INVENTORY.md`.

## Starting work

Open a terminal, go to this directory, and start Claude Code:

```
cd "C:\Users\ciaci\New folder\codex\eephus.io\.claude\worktrees\milb-pitch-quality-research-e53bba\eephus-stuff-research"
claude
```

("Go to this directory" means: paste that `cd ...` line into your terminal
and press Enter. `cd` stands for "change directory" — it moves your terminal
into that folder so every command you run afterward acts on the files
there.)

## Checking Git state

```
git status
```

Run from anywhere inside the `eephus.io` repository (this folder is inside
it). This tells you what's changed since the last commit. The words it uses:

- **modified** — a file that's already tracked by Git has been changed, but
  the change hasn't been saved to Git's history yet.
- **untracked** — a file Git has never seen before (e.g. a new file you or
  Claude just created). Git won't include it in anything until you `git add`
  it.
- **staged** — a file that's been marked with `git add` as "include this in
  the next commit." Staged is a waiting room between "changed" and
  "permanently recorded."
- **committed** — saved permanently into Git's history with a message
  describing why. Nothing is committed until you (or Claude, with your
  approval) run `git commit`.

## Viewing changes

```
git diff
```

Shows the actual line-by-line changes in files that are modified but not yet
staged. Green lines were added, red lines were removed.

## Viewing history

```
git log --oneline
```

Shows a compact list of past commits, newest first, one line each: a short
hash (an ID for that commit) and its message.

## Running tests

From this directory (`eephus-stuff-research/`), with the virtual environment
active:

```
./.venv/Scripts/python.exe -m pytest
```

("Virtual environment" — `.venv/` — is a self-contained copy of Python with
just this project's packages installed, so it doesn't interfere with any
other Python project on your machine. You don't need to "activate" it to run
commands this way — calling `.venv/Scripts/python.exe` directly works from
Git Bash, PowerShell, or cmd.)

What success looks like: a line ending in something like
`XX passed in N.NNs` with no red `FAILED` lines above it. If you see `FAILED`
lines, that's Git Bash/pytest telling you something is broken — don't assume
it's fine because most tests passed (see `docs/CERTIFICATION_STANDARD.md`,
"No averaged certification").

To run just one class of tests (see `docs/VALIDATION_STANDARD.md` for what
each class means):

```
./.venv/Scripts/python.exe -m pytest tests/unit
./.venv/Scripts/python.exe -m pytest tests/certification
```

## Leaving Claude Code

Type `exit` or press Ctrl+C, or just close the terminal window. Nothing is
lost — anything committed to Git stays committed; anything not committed but
saved to a file stays on disk; anything not committed and not saved (rare,
since Claude Code writes files as it works, not just in memory) would be
lost, which is exactly why the filesystem, not the conversation, is the
source of truth (see `CLAUDE.md`, "Session continuity").

## Returning later

```
cd "C:\Users\ciaci\New folder\codex\eephus.io\.claude\worktrees\milb-pitch-quality-research-e53bba\eephus-stuff-research"
claude
```

Same command as starting. Claude Code (or you) should re-read
`docs/MACHINE_STATE.md`, `git status`, and `git log --oneline` to reconstruct
what's true right now, rather than trusting what an old conversation said.

## Important safety rule

**If Claude proposes deleting something, force-resetting Git, force-pushing,
modifying anything in the production paths listed in `CLAUDE.md` (J5), or
making any change to a remote repository (GitHub) that you don't understand
— do not approve it until it's been explained to you in plain English:**
what it does, why it's needed, whether it changes files, and whether it can
be undone. Asking "explain that before you do it" is always a reasonable
thing to say.

## How to talk to Claude Code in this project

You don't need to write code or use precise terminal syntax to drive this
research. A few example instructions and why they work well:

**Good instruction (starts a stage of work):**
> Inspect the current machine and relevant files first. Do not modify
> production. Tell me what you found, what remains uncertain, and then
> proceed with the preregistered stage.

**Good correction (stops a specific bad habit):**
> Stop. Do not infer that value. Establish it from the artifact or mark it
> NOT_MEASURED.

**Good audit request (forces reproduction before extension):**
> Reproduce the prior result from raw/derived artifacts before extending it.

**Good review request (asks for a real critique, not a rubber stamp):**
> Attack this result. Look for leakage, dependence, target contamination,
> identity reconstruction, selection effects, unstable inference, and
> alternative explanations.

These work because they name a specific, checkable behavior instead of a
vague goal — "be careful" is hard for anyone (human or Claude) to act on;
"establish it from the artifact or mark it NOT_MEASURED" is not.

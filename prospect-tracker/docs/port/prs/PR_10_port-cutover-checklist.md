# PR 10: port-cutover-checklist

**Branch:** `port-cutover-checklist` (stacked on PR 9). **Commit:** 1c3b963. **Target:** `main` after PR 9. Docs only.

## What

`docs/port-cutover.md`: the day `main-deploy` first publishes the producer's served bundle, as checkboxes to tick in the cutover PR with the time.

- **0. Before the day:** PRs 1 to 9 merged and tested on the box outside the webroot; the box's uncommitted edits committed; a `pre-port-<date>` tag and a webroot tarball; 10 GB free; the ship channel open and a dry run from the producer; the pin's `reference` set to the frozen bundle by PR.
- **1. main-deploy:** the merge, eight binaries, the units, the server restarted with `-bundle-dir`, nginx and Cloudflare no-store for the two heartbeats, a `bin/shipgate -check`.
- **2. The first bundle:** `RECEIVED`, `current`, `bin/receive -require-reference -verify-only`, one Purge Everything, the receipt.
- **3. Acceptance:** Gate C over HTTP (nothing DIFFERENT, MISSING or BLOCKED), Gate B's 404s, the heartbeat, the sidecar header, spot pages in both themes. A failure stops and rolls back before the next 03:10 Build.
- **4. The first nights:** link-dest, prune, sweep, a week without a rejection.
- **5. Rollback, smallest layer first:** a bad bundle (repoint `current`, publish); the ship channel off; back to the Build's site (drop `current` and `-bundle-dir`); the whole port reverted to the pre-port tag by PR, with the tarball as the last resort and the owner pausing the PC's ship.
- A table of who does each step.

## Why

The PR set changes how the site is published; the day it goes live needs one ordered list both sides can follow and one rollback per failure layer, written before it is needed.

## How verified

Docs only. Every command in it names a binary, unit, file or flag that exists in PRs 1 to 9 (checked against the tree at this commit); GOOS=linux `go build ./...` and `go vet ./...` exit 0 on the branch (`verify/port-cutover-checklist.txt`).

## Asks

Read it once against your box and correct anything that does not match how you operate it (paths, the reload command, the purge), by a commit on this branch or in review.

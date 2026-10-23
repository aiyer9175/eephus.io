# Port PR plan: the box's half of Strategy D, prepared locally (2026-10-22)

**For:** the owner and the webmaster. **Prepared by:** task PORT_PR_PREP, on the owner's PC, from the local read-only copy of `eephus/eephus` (`refs/eephusgit/heads/main` = 9e1423cc, the merge of PR #4; `main-deploy` 9c7c04e4 has the same tree).

**Nothing was pushed, no remote was configured, the server was not touched.** The six branches below live in a scratch clone and in a git bundle; the owner or the webmaster pushes them.

- Scratch clone: `C:/Users/noah/AppData/Local/Temp/claude/c--Users-noah-baseball-projects-BaseballR/b7a7d3e5-214d-4434-a171-b2b4900b0199/scratchpad/eephusgit/prs/eephus` (branch `port-stage1-pages` checked out; no remote).
- Transport: `C:/Users/noah/AppData/Local/Temp/claude/c--Users-noah-baseball-projects-BaseballR/b7a7d3e5-214d-4434-a171-b2b4900b0199/scratchpad/eephusgit/prs/eephus-port-prs.bundle` (3,628,499 bytes, `git bundle verify` okay, requires 9e1423cc). `git fetch <bundle> 'refs/heads/*:refs/heads/*'` in a clone of `eephus/eephus` at `main` restores all six branches.
- Rehearsal bundle the pin references: `.../scratchpad/eephusgit/prs/bundle_out/20261023T001053Z-6f82911d5778` (17,837 files, 1,304,296,283 bytes, built from the producer's worktree commit 1a1bd74d in 2m17s).
- Go toolchain used: `go1.25.14 windows/amd64`, portable zip at `C:/Users/noah/tools/go` (sha256 `119044a92b3987c341cd6aebb256676dd4780d292f7b4e72a3e9976677841697`, matched against go.dev's listing), `GOTOOLCHAIN=local`, matching `go.mod`'s `go 1.25.0`. No installer, no PATH change.

## Conventions followed

REPO.md: a feature branch per change, reviewed into `main`, then `main` into `main-deploy` by the webmaster. AGENTS.md: Go only, no `.py` enters the repository (none does; the producer's Python stays on GitHub and the owner's PC, PORT-R3). Commits are full sentences in his style, LF endings like every blob in the repository (the scratch clone was re-checked-out with `core.autocrlf=false` after a first checkout under the system's `autocrlf=true`; every committed file is LF). Each commit ends with the owner's attribution trailer.

## Merge order

The six branches are **stacked**: each is one commit on top of the previous, so merging them in order is six fast-forwards and the webmaster can review each diff alone. PR 1 is independent hygiene; PR 2 through PR 6 are Stage 1.

| # | Branch | Commit | One line | Files |
|---|---|---|---|---|
| 1 | `port-stage0-withheld-data` | 33398bf | Untrack the six withheld data files; `data_exclude.txt` becomes the 44-name union | 7 |
| 2 | `port-stage1-publish-contract` | f277e7c | The pin `frontend/deploy/artifact_manifest.json`; `publish.sh` publishes `current/site` with `data/<subdir>` shards; `publish_paths.txt` gains the 33 dirs, drops `teams/` | 3 |
| 3 | `port-stage1-buildsite-ownership` | 3eac0ba | `cmd/buildsite` and the site tests honour the pin's `owned` list | 7 |
| 4 | `port-stage1-receive` | 5e0bf24 | `cmd/receive` + `internal/artifact`: verify, receipt, atomic `current` swap, prune; `eephus-receive.path/.service`; README; nginx and Cloudflare no-store for the bundle heartbeats | 9 |
| 5 | `port-stage1-sidecars` | 935dc8c | The 20 JSON `/partials/` routes serve the bundle's file verbatim under `-bundle-dir`; a missing file is a 404, never the Build's numbers | 6 |
| 6 | `port-stage1-pages` | 03b5013 | The producer's 214 pages and assets replace `frontend/`'s (LF), `teams/` deleted, the deep-link fix carried in; the other rebuild fixes recorded as not applicable to static pages | 190 |

PR descriptions (what, why, how verified, asks): `PR_1_port-stage0-withheld-data.md` ... `PR_6_port-stage1-pages.md` beside this file.

## Test lines, per branch

The box is Linux, so the gate that matters is `GOOS=linux GOARCH=amd64 go build ./...` and `go vet ./...` (vet type-checks every test file). The native Windows `go test ./...` is recorded for comparison with `main` on the same PC; its failures are platform-only and identical on every branch and on `main` (`verify/baseline-main-lf.txt`): `cmd/nightly`, `internal/httpserver` and `internal/nightlyjobs` do not build on Windows because `disk.go` uses `syscall.Statfs`, and the six `internal/pipeline` `TestRunBuild_*` fail for symlink privilege. Nothing new fails on any branch.

| Branch | GOOS=linux build | GOOS=linux vet | gofmt -l | native go test (windows) | Record |
|---|---|---|---|---|---|
| main (baseline, LF tree) | exit 0 | exit 0 | clean | 83 ok; 3 [build failed] + `pipeline` FAIL (platform) | `verify/baseline-main-lf.txt` |
| `port-stage0-withheld-data` | exit 0 | exit 0 | clean | same set as main | `verify/port-stage0-withheld-data.txt` |
| `port-stage1-publish-contract` | exit 0 | exit 0 | clean | same set as main | `verify/port-stage1-publish-contract.txt` |
| `port-stage1-buildsite-ownership` | exit 0 | exit 0 | clean | same set as main | `verify/port-stage1-buildsite-ownership.txt` |
| `port-stage1-receive` | exit 0 | exit 0 | clean | same set as main; `internal/artifact` ok | `verify/port-stage1-receive.txt` |
| `port-stage1-sidecars` | exit 0 | exit 0 | clean | same set as main | `verify/port-stage1-sidecars.txt` |
| `port-stage1-pages` | exit 0 | exit 0 | clean | same set as main | `verify/port-stage1-pages.txt` |

Targeted runs, verbatim:

```
PR 1   go test ./internal/site/ -run 'TestExcludedData' -v
       --- PASS: TestExcludedDataIsNotFetchedByAnyPage (0.25s)
       --- PASS: TestExcludedDataIsNotARegistryArtifact (0.01s)
       ok   git.btq.ee/eephus/eephus-backend/internal/site 1.330s
PR 3   go test ./internal/site/ ./cmd/buildsite/
       ok   git.btq.ee/eephus/eephus-backend/internal/site 1.891s
       ok   git.btq.ee/eephus/eephus-backend/cmd/buildsite 1.603s
       (five generated-vs-committed comparisons SKIP as bundle-owned; TestRunSkipsBundleOwnedPages,
        TestRunWithoutAPinWritesEverything, TestOwnership*, TestCommittedPinOwnsTheStageOnePages PASS)
PR 4   go test ./internal/artifact/
       ok   git.btq.ee/eephus/eephus-backend/internal/artifact 0.732s
       (TestAcceptWritesTheReceiptMarksReceivedAndRepointsCurrent SKIP on Windows: symlink privilege)
       bin/receive -verify-only <rehearsal bundle>
       ok: 20261023T001053Z-6f82911d5778, 17837 files, 1304296283 bytes verified in 1m29.24s
       bin/receive -require-reference -verify-only <rehearsal bundle>
       ok: 20261023T001053Z-6f82911d5778, 17837 files, 1304296283 bytes verified in 1.935s
       (unlisted file planted)   rejected: 1 unlisted (zz_planted.txt)   exit 1
       (removed)                 ok: ... verified in 1.906s               exit 0
PR 5   go test ./internal/httpserver/   (under an uncommitted Windows shim for disk.go, see PR 5)
       ok   git.btq.ee/eephus/eephus-backend/internal/httpserver 3.083s
PR 6   go test -count=1 ./internal/site/
       ok   git.btq.ee/eephus/eephus-backend/internal/site 3.103s
       --- PASS: TestExcludedDataIsNotFetchedByAnyPage (2.26s)
       tracked page set == bundle manifest's 214 non-data rows: True
```

Not executed on the preparing PC: the rsync in `publish.sh` (no rsync here; `bash -n` and a by-hand run of its include builder against the rehearsal bundle, 48 rules), the systemd units, and the symlink swap on a real `/opt/eephus/artifacts` (the swap's unit test runs on Linux).

## What the webmaster does, in order

1. Fetch the bundle (or the branches) into a clone of `eephus/eephus`; push the six branches; open six PRs in the order above; merge each into `main` after review, then `main` into `main-deploy`.
2. On the box: `git pull --ff-only`, `go build -o bin/ ./cmd/...` (now six binaries), `systemctl restart eephus-server` (it gains `-bundle-dir`), install `eephus-receive.path/.service`, create the `ship` user and `/opt/eephus/artifacts` as the README section says (PR 4's asks), reload nginx with the two no-store locations, add the two paths to Cloudflare's Rule 3.
3. Send the owner the ship host, user and host key; the owner fills `%USERPROFILE%\.eephus\port_ship.conf` and runs `deploy/port-nightly.ps1 -SkipPipeline` once by hand (PORT_BUNDLE.md section 7).
4. The first bundle lands: `systemctl status eephus-receive.service`, `cat /opt/eephus/artifacts/current/RECEIVED`, then the owner runs `tools/port_equivalence.py compare-http --bundle <id> --origin https://eephus.io` (Gate C over HTTP) and `tools/port_live_check.py --origin https://eephus.io` (Gate B: the 44 withheld names answer 404).
5. Cutover (PORT_RUNBOOK T8 as amended by PORT_RECON section 5): the pin's `reference` set to Gate C's REF by PR, `bin/receive -require-reference` once, purge Cloudflare, re-run both checks against production.

## Owner decisions this plan takes as defaults (veto any)

- **Headshot proxy:** the pages keep their `img.mlbstatic.com` URLs (byte-identical to the local build, every surface's own face crop and size). Alternative: move a surface to `/images/headshots/{mlbamID}` (producer-side change plus an explained-list line; his proxy serves one 128 px cached crop and 404s until a photo context resolves).
- **Forums and account layer:** shipped inert with the pages (identical to local). Alternative: drop it in his repo and name it in the explained list.
- **Repository copy of the pages:** LF endings and unstripped sources; the bundle carries CRLF and the stripped copies. The equivalence tool reads CRLF as LF, and `compare-http` compares the bundle, not the repository.
- **`publish_paths.txt` in his repo** now carries `data/<subdir>` entries that the producer's own copy does not (the producer's `port_equivalence.page_files` would double-count them). The two files are separate contracts; if they are ever unified, `page_files` must skip `data/` entries.

## Risks carried forward (from PORT_RECON section 8, unchanged)

Producer uptime on the PC; the 36-hour alarm watches the receive time, not his Build; his 03:10 Build still runs and still triggers a publish, which republishes the same bundle (idempotent) rather than flipping the site; the box's disk (two bundles at about 2.6 GB with hard links); the review latency of six PRs then Stage 2's twenty routes.

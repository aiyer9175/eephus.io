# Port PR plan: the box's half of Strategy D, prepared locally (2026-10-22, extended 2026-10-27)

**For:** the owner and the webmaster. **Prepared by:** tasks PORT_PR_PREP (PRs 1 to 6), PORT_STAGE2_PREP (PRs 7 to 10) and PORT_SCORES_PR11 (PR 11), on the owner's PC, from the local read-only copy of `eephus/eephus` (`refs/eephusgit/heads/main` = 9e1423cc, the merge of PR #4; `main-deploy` 9c7c04e4 has the same tree).

**Nothing was pushed, no remote was configured, the server was not touched.** The eleven branches below live in a scratch clone and in a git bundle; the owner or the webmaster pushes them.

- Scratch clone: `C:/Users/noah/AppData/Local/Temp/claude/c--Users-noah-baseball-projects-BaseballR/b7a7d3e5-214d-4434-a171-b2b4900b0199/scratchpad/eephusgit/prs/eephus` (branch `port-stage2-scores-in-bundle` checked out; no remote).
- Transport: `C:/Users/noah/AppData/Local/Temp/claude/c--Users-noah-baseball-projects-BaseballR/b7a7d3e5-214d-4434-a171-b2b4900b0199/scratchpad/eephusgit/prs/eephus-port-prs.bundle` (3,686,614 bytes, eleven refs, `git bundle verify` okay, requires 9e1423cc; rebuilt 2026-10-27 late evening). `git fetch <bundle> 'refs/heads/*:refs/heads/*'` in a clone of `eephus/eephus` at `main` restores all eleven branches.
- Rehearsal bundle the pin references: `.../scratchpad/eephusgit/prs/bundle_out/20261023T001053Z-6f82911d5778` (17,837 files, 1,304,296,283 bytes, built from the producer's worktree commit 1a1bd74d in 2m17s).
- Go toolchain used: `go1.25.14 windows/amd64`, portable zip at `C:/Users/noah/tools/go` (sha256 `119044a92b3987c341cd6aebb256676dd4780d292f7b4e72a3e9976677841697`, matched against go.dev's listing), `GOTOOLCHAIN=local`, matching `go.mod`'s `go 1.25.0`. No installer, no PATH change.

## Conventions followed

REPO.md: a feature branch per change, reviewed into `main`, then `main` into `main-deploy` by the webmaster. AGENTS.md: Go only, no `.py` enters the repository (none does; the producer's Python stays on GitHub and the owner's PC, PORT-R3). Commits are full sentences in his style, LF endings like every blob in the repository (the scratch clone was re-checked-out with `core.autocrlf=false` after a first checkout under the system's `autocrlf=true`; every committed file is LF). Each commit ends with the owner's attribution trailer.

## Merge order

The eleven branches are **stacked**: each is one commit on top of the previous, so merging them in order is eleven fast-forwards and the webmaster can review each diff alone. PR 1 is independent hygiene; PR 2 through PR 6 are Stage 1; PR 7 is Stage 2's transport; PR 8 and PR 9 are Stage 3's entry conditions; PR 10 is the cutover checklist (docs only); PR 11 publishes the scores store from the bundle.

| # | Branch | Commit | One line | Files |
|---|---|---|---|---|
| 1 | `port-stage0-withheld-data` | 33398bf | Untrack the six withheld data files; `data_exclude.txt` becomes the 44-name union | 7 |
| 2 | `port-stage1-publish-contract` | f277e7c | The pin `frontend/deploy/artifact_manifest.json`; `publish.sh` publishes `current/site` with `data/<subdir>` shards; `publish_paths.txt` gains the 33 dirs, drops `teams/` | 3 |
| 3 | `port-stage1-buildsite-ownership` | 3eac0ba | `cmd/buildsite` and the site tests honour the pin's `owned` list | 7 |
| 4 | `port-stage1-receive` | 5e0bf24 | `cmd/receive` + `internal/artifact`: verify, receipt, atomic `current` swap, prune; `eephus-receive.path/.service`; README; nginx and Cloudflare no-store for the bundle heartbeats | 9 |
| 5 | `port-stage1-sidecars` | 935dc8c | The 20 JSON `/partials/` routes serve the bundle's file verbatim under `-bundle-dir`; a missing file is a 404, never the Build's numbers | 6 |
| 6 | `port-stage1-pages` | 03b5013 | The producer's 214 pages and assets replace `frontend/`'s (LF), `teams/` deleted, the deep-link fix carried in; the other rebuild fixes recorded as not applicable to static pages | 190 |
| 7 | `port-stage2-transport` | 766a65e | `cmd/shipgate`, the ship user's forced command: only the body into `incoming/<id>/` and then `READY`, a disk floor, never into a marked bundle; the daily sweep of abandoned uploads; sshd drop-in and key file; README | 13 |
| 8 | `port-stage3-shadow-gates` | e14d10d | `deploy/shadow_gates.tsv` (20 registered per-field gates, 10 modules) and `cmd/shadoweq`: the Go models measured against the bundle, a report, nothing served | 6 |
| 9 | `port-stage3-asof-accessor` | 64b78aa | `internal/asof`: an as-of connection through temp views, all 57 store tables classified, the schema test; `docs/AS_OF_ACCESSOR.md` | 4 |
| 10 | `port-cutover-checklist` | 1c3b963 | `docs/port-cutover.md`: main-deploy day and its rollback, layer by layer | 1 |
| 11 | `port-stage2-scores-in-bundle` | 48c2084 | `publish_paths.txt` gains `data/scores` (the scores store travels in the bundle as of its build, owner PORT-Q-SCORES); nginx serves it from the webroot and its comment forbids the old box-written alias; `internal/site/scores_test.go`; README and cutover lines | 6 |

PR descriptions (what, why, how verified, asks): `PR_1_port-stage0-withheld-data.md` ... `PR_11_port-stage2-scores-in-bundle.md` beside this file.

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
| `port-stage2-transport` | exit 0 | exit 0 | clean | same set as main; `internal/shipgate` ok | `verify/port-stage2-transport.txt` |
| `port-stage3-shadow-gates` | exit 0 | exit 0 | clean | same set as main; `internal/shadow` ok | `verify/port-stage3-shadow-gates.txt` |
| `port-stage3-asof-accessor` | exit 0 | exit 0 | clean | same set as main; `internal/asof` ok | `verify/port-stage3-asof-accessor.txt` |
| `port-cutover-checklist` | exit 0 | exit 0 | clean | same set as main | `verify/port-cutover-checklist.txt` |
| `port-stage2-scores-in-bundle` | exit 0 | exit 0 | clean | same set as main; `internal/site` ok | `verify/port-stage2-scores-in-bundle.txt` |

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
PR 7   go test -count=1 -v ./internal/shipgate/
       --- PASS: TestTheProducersCommandsParse   (the producer's --print-remote fixture, verbatim)
       --- PASS: TestTheGrammarRefusesEachDefectAlone   (31 planted refusals)
       --- PASS: TestOtherRsyncVersionsClusterStillParses
       --- PASS: TestCheckFollowsTheBundlesState
       --- PASS: TestTheDiskFloorRefusesABodyWithAClearMessage
       --- PASS: TestSweepRemovesOnlyAbandonedUploads
       --- PASS: TestIDTime
       ok   git.btq.ee/eephus/eephus-backend/internal/shipgate 0.486s
       rehearsal (verify/stage2_rehearsal.txt), bin/shipgate -check with a local pin:
       accepted: body of 20261027T031000Z-0123456789ab (link-dest "20261023T001053Z-6f82911d5778")
       refused: READY goes last: bundle 20261027T031000Z-0123456789ab has no MANIFEST.tsv yet; send the body first
       refused: 383.9 GB free under ... is below the 100000.0 GB floor; nothing was written. ...
       bin/receive -verify-only <rehearsal bundle>
       ok: 20261023T001053Z-6f82911d5778, 17837 files, 1304296283 bytes verified in 1.816s
PR 8   go test -count=1 -v ./internal/shadow/   (6 PASS)
       ok   git.btq.ee/eephus/eephus-backend/internal/shadow
       bin/shadoweq, the bundle against itself: 10 PASS, 0 FAIL, 0 NOT RUN
       bin/shadoweq, committed frontend/data as a stand-in challenger: 0 PASS, 8 FAIL, 2 NOT RUN
       (verify/stage3_shadow_rehearsal.txt)
PR 9   go test -count=1 -v ./internal/asof/   (5 PASS)
       asof_test.go:63: 57 tables: 11 observed, 21 seasonal, 2 reference, 23 unversioned
       ok   git.btq.ee/eephus/eephus-backend/internal/asof
PR 10  docs only; GOOS=linux build and vet exit 0
PR 11  go test -count=1 -v ./internal/site/ -run 'TestTheScoresStoreShipsFromTheBundle|TestSitemapSurfacesAreShipped'
       --- PASS: TestSitemapSurfacesAreShipped (0.00s)
       --- PASS: TestTheScoresStoreShipsFromTheBundle (0.05s)
       ok   git.btq.ee/eephus/eephus-backend/internal/site 0.775s
       (planted: data/scores removed from publish_paths.txt and an alias block added to nginx: each fails on its own line)
       bin/receive -verify-only <producer bundle with the store>
       ok: 20261028T025004Z-d763ad28d516, 19543 files, 1309775995 bytes verified in 3.493s
       crawl of that bundle's site/ (verify/scores_bundle_crawl.txt): /data/scores/latest.json 200, the store's bytes;
       /scores/ stamp "Updates paused. Scores as of 10:34 PM. Published with the nightly site build, October 27, 10:50 PM."
```

Not executed on the preparing PC: the rsync in `publish.sh` (no rsync here; `bash -n` and a by-hand run of its include builder against the rehearsal bundle, 48 rules), the systemd units, and the symlink swap on a real `/opt/eephus/artifacts` (the swap's unit test runs on Linux).

## What the webmaster does, in order

1. Fetch the bundle (or the branches) into a clone of `eephus/eephus`; push the eleven branches; open eleven PRs in the order above; merge each into `main` after review, then `main` into `main-deploy` on cutover day by `docs/port-cutover.md`.
2. On the box: `git pull --ff-only`, `go build -o bin/ ./cmd/...` (now eight binaries: server, nightly, buildsite, chadwick, fit, receive, shipgate, shadoweq), `systemctl restart eephus-server` (it gains `-bundle-dir`), install `eephus-receive.path/.service` and `eephus-ship-sweep.service/.timer`, create the `ship` user and `/opt/eephus/artifacts` as the README section says (PR 4's asks), install `/etc/eephus/ship_authorized_keys` and the sshd drop-in (PR 7's asks), reload nginx with the two no-store locations, add the two paths to Cloudflare's Rule 3.
3. Send the owner the ship host, user and host key; the owner fills `%USERPROFILE%\.eephus\port_ship.conf` and runs `deploy/port-nightly.ps1 -SkipPipeline` once by hand (PORT_BUNDLE.md section 7).
4. The first bundle lands: `systemctl status eephus-receive.service`, `cat /opt/eephus/artifacts/current/RECEIVED`, then the owner runs `tools/port_equivalence.py compare-http --bundle <id> --origin https://eephus.io` (Gate C over HTTP) and `tools/port_live_check.py --origin https://eephus.io` (Gate B: the 44 withheld names answer 404).
5. Cutover: `docs/port-cutover.md` (PR 10), which carries PORT_RUNBOOK T8 as amended by PORT_RECON section 5: the pin's `reference` set to Gate C's REF by PR, `bin/receive -require-reference` once, purge Cloudflare, re-run both checks against production, and the rollback layers.
6. Stage 3, any time after: run `bin/shadoweq` against a shadow server once and send the owner the report (PR 8's ask). No Go model serves a module until its gates pass and its inputs read through `internal/asof` (PR 9).

## Owner decisions this plan takes as defaults (veto any)

- **Headshot proxy:** the pages keep their `img.mlbstatic.com` URLs (byte-identical to the local build, every surface's own face crop and size). Alternative: move a surface to `/images/headshots/{mlbamID}` (producer-side change plus an explained-list line; his proxy serves one 128 px cached crop and 404s until a photo context resolves).
- **Forums and account layer:** shipped inert with the pages (identical to local). Alternative: drop it in his repo and name it in the explained list.
- **Repository copy of the pages:** LF endings and unstripped sources; the bundle carries CRLF and the stripped copies. The equivalence tool reads CRLF as LF, and `compare-http` compares the bundle, not the repository.
- **`publish_paths.txt` in his repo** now carries `data/<subdir>` entries that the producer's own copy does not (the producer's `port_equivalence.page_files` would double-count them). The two files are separate contracts; if they are ever unified, `page_files` must skip `data/` entries.
- **Ship gate floor and sweep (PR 7):** refuse a body under 8 GB free (the Build's 6 GB floor plus one bundle); sweep a markerless upload once its id is 48 hours old. Alternatives: another floor, or no sweep (abandoned uploads then wait for a person).
- **Shadow gate floors (PR 8):** every registered field must print the same digits on every row (floor 1). Alternative: a per-field share below 1, which would let a takeover change printed numbers.
- **Bundle slimming (producer):** on by default (`--no-slim` builds the full set). Alternative: off until the webmaster's disk asks for it; it saves 0.45%.

## Producer side, 2026-10-27 (task PORT_STAGE2_PREP, lane worktree branch wt-PORT_STAGE2_PREP)

- `tools/port_ship.py`, `.ps1` and `.sh` match the gate: `--chmod=D775,F664`, the remote dir must be the absolute inbox, and `--print-remote <id> [--link-from <id>]` prints the remote commands; `test_fixtures/port_ship/remote_commands.txt` is byte-identical to PR 7's testdata (sha256 pinned in `test_port_ship.py`).
- Bundle slimming: `SLIM_EXCLUDE` in `tools/port_bundle.py` leaves out 37 payloads (5,865,389 bytes, 0.45%) that no page, asset, script or other served file names and no crawl fetched; a slimmed build refuses when something served starts to name one. Proved by `port_equivalence.py compare-bundles`: 214 page rows identical, nothing changed or added, every crawled file present and identical, 206 crawled requests answered the same by both bundles' sites; `bin/receive -verify-only` accepts the slim bundle. The shard directories (the bulk) are all reachable. `docs/port/PORT_BUNDLE.md` section 9.
- Found: `data/scores/` is in no bundle (the scores job was meant to write it on the box behind its own nginx alias); under PORT-R1 the box runs no Python, so `/scores/` loads without its data. An owner question in the PORT_STAGE2_PREP report, answered the same day (below).

## Producer side, 2026-10-27 late evening (task PORT_SCORES_PR11, lane worktree branch wt-PORT_SCORES_PR11)

- Owner PORT-Q-SCORES ("Ship it in the bundle"): `port_equivalence.LIVE_DIRS = ("data/scores",)` and `port_bundle.served_files` carry the scores store in every served bundle as of the build, never slimmed; a live file the job removed between the listing and the copy is left out and named in `BUNDLE.json` (`live_vanished`) rather than failing the night; `BUNDLE.json` counts the store under `live`. The nightly rsync's set is unchanged. `compare-bundles` reports live rows apart and never fails on their bytes. Measured: 19,462 files and 1,309,204,786 bytes before, 19,542 and 1,311,641,012 after (`--plan-served`, the store 80 files and 2,436,226 bytes); one real bundle `20261028T025004Z-d763ad28d516`, 19,543 files, 1,309,775,995 bytes, `--verify-served` ok, `bin/receive -verify-only` ok. `docs/port/PORT_BUNDLE.md` section 11.
- The page: `assets/scores.js` asks `/data/bundle_info.json` once when the stale rule reads the job's updates as paused and appends "Published with the nightly site build, <month day>, <time>." to the stamp when a bundle answers; the local site (404) says nothing more. The producer's `deploy/README.md` and `deploy/WEBMASTER.md` section 10 mark the box-run scores job and its alias withdrawn.

## Risks carried forward (from PORT_RECON section 8, unchanged)

Producer uptime on the PC; the 36-hour alarm watches the receive time, not his Build; his 03:10 Build still runs and still triggers a publish, which republishes the same bundle (idempotent) rather than flipping the site; the box's disk (two bundles at about 2.6 GB with hard links); the review latency of six PRs then Stage 2's twenty routes.

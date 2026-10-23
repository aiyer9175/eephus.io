# PR 2: port-stage1-publish-contract

**Branch:** `port-stage1-publish-contract` (stacked on PR 1). **Commit:** f277e7c. **Target:** `main` after PR 1.

## What

1. **`frontend/deploy/artifact_manifest.json`, the pin.** The served bundle's contract: the `incoming` and `current` paths under `/opt/eephus/artifacts`, the files every bundle carries (`MANIFEST.tsv`, `SHA256SUMS`, `BUNDLE.json`, `READY`, `site/`, and the two heartbeats inside `site/data`), the bundle id pattern, the 36-hour receive alarm, and the paths the bundle **owns**: every page and asset directory the producer serves, the five root files and the retired `teams/`. Its `reference` block records the rehearsal bundle this contract was verified against (`20261023T001053Z-6f82911d5778`: 17,837 files, 1,304,296,283 bytes, built from the producer's commit 1a1bd74d); the cutover reference replaces it by PR on the day the port lands.
2. **`eephus-backend/deploy/publish.sh`.** When `$ARTIFACTS/current` holds a received bundle (`RECEIVED` present), the rsync source is `current/site` after a `sha256sum -c --quiet SHA256SUMS` re-check; a bundle that fails leaves the webroot as it is and exits 1. With no received bundle it publishes the frontend tree exactly as before. The include builder understands a `data/<subdir>` entry and ships that directory whole. The Build's heartbeat `data/build_info.json` is protected from `--delete` and copied in after the sync in bundle mode.
3. **`frontend/deploy/publish_paths.txt`.** The producer's 33 page directories and five root files (so the bundle publishes whole), and nine `data/<subdir>` entries: `pitch_plots`, `player_detail`, `debuts_full`, `mgmt_decisions`, `ledger_clubs`, `franchise_clubs`, `mlb_events`, `mlbstats_player`, `mlb_player_detail`. `teams/` is dropped (retired by the producer on 2026-10-07; its `404.html` forwards `/teams/`). `history/` and `parks/` were in the tree and absent from the list, so they had never shipped.

## Why

Strategy D (`docs/port/PORT_RECON.md`, owner decisions PORT-R1 and PORT-R2): the producer stays the one producer and ships a sha256-manifested bundle; this box publishes it through your own `publish.sh` and `go test` gate, so the site is identical to the producer's build by construction. The old filter shipped only depth-one data files, so every per-player shard directory the pages fetch on demand answered 404 on the live site (the recon's first read-only sample: 11 of 12 files MISSING). The ownership list is what the next PR's generator and tests read.

## How verified

- `bash -n deploy/publish.sh` clean. The include builder, run by hand against the rehearsal bundle, produces 48 rules: 5 files, 34 page directories, 9 data subdirectories.
- `go test ./internal/site/ -run 'TestSitemap|TestRobots|TestExcludedData'`: the sitemap pin resolves every advertised surface against the new list (a `data/...` entry is ignored by its top-level segment match).
- GOOS=linux `go build ./...` and `go vet ./...` exit 0 (`verify/port-stage1-publish-contract.txt`).
- Not executed here: the rsync itself (the preparing PC has no rsync). Its rule order is unchanged from the version that runs nightly; the protect filter and the `data/<subdir>` includes are additions. Please read the diff of step 3 and 4 with that in mind.

## Asks

- The `paths` in the pin are the layout the receive PR installs (`/opt/eephus/artifacts`). If you want another, change the pin; `publish.sh` also honours `EEPHUS_ARTIFACTS`.
- `paths.keep` is 2 because the producer's rsync uses `--link-dest=../<last id>`; the previous bundle must still be on disk for a cheap second night. Budget about 2.6 GB for two generations, less with the hard links.

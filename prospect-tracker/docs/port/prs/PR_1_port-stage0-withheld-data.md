# PR 1: port-stage0-withheld-data

**Branch:** `port-stage0-withheld-data` (off `main` at 9e1423cc). **Commit:** 33398bf. **Target:** `main`, then `main-deploy` by your PR.

## What

- `git rm` six files from `frontend/data`: `comps.json`, `fielding_census_ids.json`, `identity_collisions.json`, `milb_pitch_rates.json`, `positional_fit.json`, `positions_played_seasons.json` (380,378 lines).
- `frontend/deploy/data_exclude.txt` becomes the union of your list (24 names) and the producer's (`prospect-tracker/deploy/data_exclude.txt`, 44 names, a superset), with the producer's comments so each name carries its reason. Line endings stay LF.

## Why

`publish.sh`'s `/data/*.json` include shipped those six every night because the exclude list did not name them. The producer has withheld them since July: `identity_collisions.json` is an ops ledger naming players whose records fuse two humans; `comps.json` is an unshipped donor pool; the other four are model-side inputs no page fetches. The list is a leakage control, not a size control (the producer's `docs/port/PORT_SPEC.md` 1.3). This is Stage 0 of the port recon (`docs/port/PORT_RECON.md`, Strategy D): hygiene before the bundle arrives. Because `rsync` runs with `--delete`, the next publish drops the six from the webroot.

## How verified

```
go test ./internal/site/ -run 'TestExcludedData' -v
--- PASS: TestExcludedDataIsNotFetchedByAnyPage (0.25s)
--- PASS: TestExcludedDataIsNotARegistryArtifact (0.01s)
ok      git.btq.ee/eephus/eephus-backend/internal/site  1.330s
```

GOOS=linux `go build ./...` and `go vet ./...` exit 0 (the full per-branch record is in `verify/port-stage0-withheld-data.txt` beside this file). The native Windows `go test ./...` on the preparing PC carries the same pre-existing platform failures as `main` (`syscall.Statfs` in `nightlyjobs/disk.go`, symlink privilege in `pipeline`, and the four `site` page comparisons) and nothing new.

## Not in this PR

Nothing else under `frontend/data` moves; Stage 2 decides what of the committed 65 MB stays once the bundle is the data source.

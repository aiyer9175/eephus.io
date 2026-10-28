# PR 11: port-stage2-scores-in-bundle

**Branch:** `port-stage2-scores-in-bundle` (stacked on PR 10). **Commit:** 48c2084. **Target:** `main` after PR 10.

## What

`/scores/` and `/standings/` read `/data/scores/` (latest, the index, a file per date, the `games/` and `standings/` shards), which the producer's scores job writes on its PC every few minutes. Under the port (PORT-R1, no Python on this box) that job never runs here, so until now the store reached no bundle and the two pages loaded on the box without their data. The owner decided on 2026-10-27 (PORT-Q-SCORES, "Ship it in the bundle") that the nightly served bundle carries `data/scores/` as of its build (about 80 files, 2.4 MB a night), and this PR makes the box publish it.

- `frontend/deploy/publish_paths.txt` gains `data/scores` with a comment, so `publish.sh`'s include builder ships the directory whole from `current/site`, like the nine shard directories (PR 2). `publish.sh`'s comment names the third kind of `data/<subdir>` entry.
- `deploy/nginx/eephus.io.conf`: a comment on the `/data/` location. The store is served from the webroot through that location (no new block); the comment says the location must never gain an alias to a directory a job on this box writes, because a second writer would shadow the bundle's files and the producer's equivalence check would read a different site. The earlier design (the producer's `deploy/README.md`, a cron job writing `/opt/eephus/scores` behind `location ^~ /data/scores/`) is withdrawn and was never installed.
- `eephus-backend/deploy/README.md`, "The served bundle": a paragraph on the store. `docs/port-cutover.md`, acceptance: `/data/scores/latest.json` answers 200 and the `/scores/` stamp reads "Published with the nightly site build".
- `internal/site/scores_test.go`: `TestTheScoresStoreShipsFromTheBundle` pins the publish entry, that `assets/scores.js`, `standings.js` and `home-scores.js` still read `/data/scores/`, and that the nginx config names no `/opt/eephus/scores` and carries no alias on a `/data/scores/` location.

Not in this PR: the page copy. The bundle owns `scores/` and `assets/` (the pin's `owned` list), and the producer's `assets/scores.js` now reads the bundle's heartbeat once the job's next update is overdue and appends "Published with the nightly site build, <month day>, <time>." to its stamp line. That ships inside the bundle; the repository copies of the pages refresh with the next pages PR, as PR 6 set the convention.

## Why

PORT-R1 keeps every job in Python on the PC; `/scores/` would otherwise be a page with no data on the box. The alternatives (the ship user syncing the store every few minutes through a third `bin/shipgate` shape, or a Go scores job behind a shadow gate) are later PRs if the owner ever wants live scores on the box; the bundle is the smallest change and the page states the staleness.

## How verified

```
gofmt -l ./internal/site                                      (clean)
GOOS=linux GOARCH=amd64 go build ./... && go vet ./...        exit 0
go test -count=1 -v ./internal/site/ -run 'TestTheScoresStoreShipsFromTheBundle|TestSitemapSurfacesAreShipped'
--- PASS: TestSitemapSurfacesAreShipped (0.00s)
--- PASS: TestTheScoresStoreShipsFromTheBundle (0.05s)
ok      git.btq.ee/eephus/eephus-backend/internal/site  0.775s
planted defects (data/scores removed from publish_paths.txt; an alias block added to nginx): each fails on its own line
    scores_test.go:33: deploy/publish_paths.txt does not name data/scores; ...
    scores_test.go:54: deploy/nginx/eephus.io.conf names /opt/eephus/scores: ...
    scores_test.go:59: the /data/scores/ location carries an alias; ...
bin/receive -verify-only <producer bundle 20261028T025004Z-d763ad28d516>
ok: 20261028T025004Z-d763ad28d516, 19543 files, 1309775995 bytes verified in 3.493s
```

The producer's bundle built the same evening carries 80 `data/scores/` rows (`BUNDLE.json` `live`), and a headless crawl of its `site/` served `/data/scores/latest.json` 200 with the store's bytes, rendered `/scores/` and `/standings/` from it, and read the stamp "Updates paused. Scores as of 10:34 PM. Published with the nightly site build, October 27, 10:50 PM." (`verify/scores_bundle_crawl.txt`). The native `go test ./...` has the same platform-only failures as `main` and nothing new (`verify/port-stage2-scores-in-bundle.txt`).

Not executed here: the rsync (no rsync on the preparing PC); the entry takes the same `--include=/data/scores/***` form as the nine shard entries PR 2 added.

## Asks

- Nothing to install beyond the merge. If `/opt/eephus/scores` or a `location ^~ /data/scores/` was ever added by hand from the producer's old README, remove it before the first bundle publishes; the test only reads the committed config.
- Cloudflare: `/data/scores/*` is purged with the rest of `/data/` by `publish.sh` when the token is set; no rule change.

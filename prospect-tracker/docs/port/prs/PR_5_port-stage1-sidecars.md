# PR 5: port-stage1-sidecars

**Branch:** `port-stage1-sidecars` (stacked on PR 4). **Commit:** 935dc8c. **Target:** `main` after PR 4.

## What

- `internal/httpserver/sidecar.go`: the table of the twenty JSON routes under `/partials/` and the producer file each one replaced (`/partials/efv` is `data/xfv.json`, `/partials/boot` is `data/timeseries.json`, `/partials/mlb/{name}` is the board's file with the three renamed ones mapped, `/partials/player/detail/{key}` is `data/player_detail/<key>.json`, and so on), plus the wrapper. With `-bundle-dir`, the route answers with the bundle file's bytes unchanged through `http.ServeContent` (as `/partials/boot` already did), with `X-Eephus-Source: bundle` on the response; a file the bundle lacks is a 404, never this Build's own numbers under the same URL. Without `-bundle-dir` every route answers from the Build Target as before.
- `server.go`: the JSON registrations go through the wrapper; the Fragment routes are untouched.
- `cmd/server`: the `-bundle-dir` flag. `deploy/eephus-server.service` passes `/opt/eephus/artifacts/current/site`, read through the `current` symlink on every request, so a bundle accepted after the server started is picked up with no restart.
- A route parameter must be one segment of player-key characters (`^[A-Za-z0-9][A-Za-z0-9_.-]*$`), so no key can leave `data/<dir>/`.

## Why

Owner decision PORT-R4: the Go models keep running as shadow challengers and serve nothing until a registered equivalence gate passes. A JSON route that returns the bundle's file verbatim meets the first condition of the per-route gate (the recon's Gate F: the sidecar's bytes equal the bundle file), and it is what lets a page be switched from `/data/<file>` to the route with no change in what it reads. The Fragment routes (the board, farm pages, charts, leaderboards, time machine and the others that return HTML or a JSON island) are re-templated one at a time in Stage 2, against the static page's rendered text and numbers.

## How verified

```
gofmt -l ./internal/httpserver ./cmd/server      (clean)
GOOS=linux go build ./...   exit 0
GOOS=linux go vet ./internal/httpserver/ ./cmd/server/   exit 0
go test ./internal/httpserver/
ok      git.btq.ee/eephus/eephus-backend/internal/httpserver    3.083s
--- PASS: TestSidecarsServeTheBundleFileVerbatim
--- PASS: TestSidecarsNeverFallBackToTheBuildTargetUnderABundle
--- PASS: TestSidecarKeyRejectsAnythingButOneSegment
--- PASS: TestSidecarWithoutABundleIsTheFallback
```

Every existing route test still passes through the transparent wrapper. `TestSidecarsServeTheBundleFileVerbatim` also asserts that every `sidecarFiles` entry is exercised, so a route added to the table without a test is caught.

A note on the preparing PC: the `httpserver` test binary does not build on Windows at `main` because `internal/nightlyjobs/disk.go` uses `syscall.Statfs` (and `payloadroundtrip_test.go` imports `nightlyjobs`). The run above used an uncommitted local shim for that one function; nothing of it is in the branch, and the box's Linux toolchain needs none. The per-branch record (`verify/port-stage1-sidecars.txt`) therefore shows `httpserver [build failed]` on Windows exactly as `main` does.

## Not in this PR

The Fragment routes, the boot payload's composition, and any page change: at Stage 1 the static pages read `/data/<file>` directly and no page calls these routes.

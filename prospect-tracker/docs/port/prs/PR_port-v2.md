# Port v2: serve the producer's nightly bundle

**Branch:** `port-v2` (11 commits on `main` at 9e1423cc, a clean fast-forward). **Target:** `main`. Replaces #6.

## What

One commit per step; read them in order:

1. Stop publishing six internal data files; `data_exclude.txt` becomes the 44-name union.
2. `publish.sh` publishes the received bundle; the pin `frontend/deploy/artifact_manifest.json`.
3. `cmd/buildsite` skips pages the bundle owns.
4. `cmd/receive`: verify the bundle against its manifest, atomic swap, prune; systemd path unit.
5. JSON `/partials/` routes serve the bundle's files verbatim.
6. `frontend/` updated to the producer's current pages and assets.
7. `cmd/shipgate`: the `ship` user's forced command (upload only, disk floor).
8. `cmd/shadoweq`: measures the Go models against the bundle; serves nothing.
9. `internal/asof`: as-of reads for the store, with a schema test.
10. `docs/port-cutover.md`: cutover and rollback checklist.
11. `data/scores` ships in the bundle.

## How verified

Each commit: `GOOS=linux go build ./...` and `go vet ./...` exit 0, `gofmt -l` clean, `go test` with no new failures against `main`. Per-commit notes: `docs/port/prs/PR_1..PR_11` in the producer repo.

## After merge

Nothing changes on the live site until the box steps are done: build the binaries, create the `ship` user and `/opt/eephus/artifacts/`, enable `eephus-receive.path`, and send the owner the ship host, user, port and host key. The first bundle is then shipped and checked before `main-deploy`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

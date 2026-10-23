# PR 4: port-stage1-receive

**Branch:** `port-stage1-receive` (stacked on PR 3). **Commit:** 5e0bf24. **Target:** `main` after PR 3.

## What

- `cmd/receive` (Go, one binary beside the other five). Started by `eephus-receive.path` when `incoming/*/READY` appears. For every pending bundle, oldest first: verify, then accept or reject.
  - **Verify** (`internal/artifact.Verify`): every `MANIFEST.tsv` row present with its byte count and sha256; nothing under `site/` the manifest does not list except the receipt; no name from `deploy/data_exclude.txt` (read from beside the pin) or from `BUNDLE.json`'s own withheld list present under `site/data/`; no publisher file (`data/build_info.json`) inside; `READY`, `BUNDLE.json`, the manifest and `site/data/bundle_info.json` all naming one bundle; the directory name equal to the id.
  - **Accept**: write `site/data/bundle_receipt.json` (`bundle_id`, `received_at`), rename `READY` to `RECEIVED` (same line), repoint `current` with a temp symlink and a rename, the swap `internal/pipeline.finalize` makes on a Build Target's Current. The symlink is the last step, so a failure before it leaves `current` where it was.
  - **Reject**: rename `READY` to `REJECTED` with the reason inside; exit 1; `current` does not move. Either way `READY` is gone, so the path unit does not fire again.
  - **Prune**: keep the newest two received bundles (the newer is the producer's `rsync --link-dest`), never the current one, never one still `READY`, never a directory with no marker (an upload in flight).
  - Flags: `-pin`, `-artifacts` (override the pin's paths), `-verify-only DIR` (check one bundle, write nothing), `-require-reference` (accept only the pin's reference bundle: cutover mode), `-keep`.
- `deploy/eephus-receive.path` and `deploy/eephus-receive.service` (`OnSuccess=eephus-publish.service`; `ReadWritePaths=/opt/eephus/artifacts`).
- `deploy/README.md`: a section "The served bundle (port Stage 1)" with the layout, the install (a restricted `ship` user with `rrsync` rooted at `incoming/`, the directory group-owned by `eephus` with the setgid bit), the checks and the rollback (the symlink). `eephus.env.example` documents `EEPHUS_ARTIFACTS`.
- Root `deploy/nginx/eephus.io.conf` and `deploy/cloudflare.md`: never cache `data/bundle_info.json` and `data/bundle_receipt.json`, as for `build_info.json` (the producer's 36-hour alarm reads them).

## Why

The producer ships one bundle a night and sends `READY` last (`docs/port/PORT_BUNDLE.md` section 4 states the receive contract); nothing on the box acted on it. The verify is the gate between the ship channel and the webroot, and the symlink swap is your own Current pattern applied to a directory.

## How verified

```
gofmt -l ./internal/artifact ./cmd/receive      (clean)
go test ./internal/artifact/
ok      git.btq.ee/eephus/eephus-backend/internal/artifact      0.732s
```

13 tests. The refusal table plants each defect alone and asserts the finding that names it: a changed byte, a changed size, a missing file, an unlisted file, a withheld name from either list, the publisher's heartbeat, a `READY` naming another manifest, a manifest edited after `READY`, a `bundle_info` naming another bundle, a directory holding another bundle. `TestAcceptWritesTheReceiptMarksReceivedAndRepointsCurrent` SKIPs on the preparing Windows box (no symlink privilege); it runs on Linux.

Against the real rehearsal bundle (17,837 files, 1.3 GB) with the built binary:

```
bin/receive -verify-only <bundle>
ok: 20261023T001053Z-6f82911d5778, 17837 files, 1304296283 bytes verified in 1m29.24s   (cold disk)
bin/receive -require-reference -verify-only <bundle>
ok: 20261023T001053Z-6f82911d5778, 17837 files, 1304296283 bytes verified in 1.935s     (warm)
(planted an unlisted file under site/)
rejected: 1 unlisted (zz_planted.txt)        exit 1
(removed it)
ok: 20261023T001053Z-6f82911d5778, 17837 files, 1304296283 bytes verified in 1.906s     exit 0
```

GOOS=linux `go build ./...` and `go vet ./...` exit 0 (`verify/port-stage1-receive.txt`).

## Asks

1. Create the `ship` user and the `/opt/eephus/artifacts` tree as the README section says, with the SSH port open to the producer's address only (`ADMIN_SSH_CIDR`, WireGuard or Tailscale; Cloudflare Free proxies no SSH). Send the owner the host key and the user name; the producer's `tools/port_ship.py` config takes them.
2. `go build -o bin/ ./cmd/...`, then `systemctl enable --now eephus-receive.path`.
3. On cutover day, run `bin/receive -require-reference` once by hand with the pin's `reference` set to Gate C's REF (PR 2's note).

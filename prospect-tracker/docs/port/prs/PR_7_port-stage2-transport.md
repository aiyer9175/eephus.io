# PR 7: port-stage2-transport

**Branch:** `port-stage2-transport` (stacked on PR 6). **Commit:** 766a65e. **Target:** `main` after PR 6.

## What

- `cmd/shipgate` and `internal/shipgate`: the forced command on the ship user's SSH key. It reads the client's request from `SSH_ORIGINAL_COMMAND` and accepts exactly the producer's two rsync calls (its `tools/port_ship.py`):

  | Call | Remote command accepted |
  |---|---|
  | the body | `rsync --server <cluster> --partial [--bwlimit=N] [--link-dest=../<previous id>] . /opt/eephus/artifacts/incoming/<id>/` |
  | the marker | `rsync --server <cluster> --partial [--bwlimit=N] . /opt/eephus/artifacts/incoming/<id>/READY` |

  `<cluster>` is rsync's server option cluster (letters `rtvicuzWIxnS`, then `e` and the capability letters; `-rte.iLsfxCIvu` from rsync 3.2). Everything else is refused with its reason: an empty command or a shell, a download (`--sender`), `--delete` and every other long option, links, permissions, owner and devices, any destination but the pin's `paths.incoming` spelled exactly plus a bundle id plus `/` or `/READY`, and any quote, escape or shell character. An accepted upload runs `/usr/bin/rsync` with the client's arguments unchanged, under umask 002.
- Before rsync starts: `READY` is refused until the body's `MANIFEST.tsv`, `SHA256SUMS`, `BUNDLE.json` and `site/` are there; either call into a bundle that already has `READY`, `RECEIVED` or `REJECTED` is refused; a body is refused when less than `-min-free-gb` (8) is free under the inbox, with a message naming what is free, the floor, that nothing was written and what to do. An unreadable disk is a refusal.
- `bin/shipgate -sweep` removes abandoned uploads (no marker, the id more than 48 hours old, not current); `eephus-ship-sweep.service` and `.timer` run it daily at 14:30. `bin/receive`'s prune never touches a directory with no marker, so without this a ship that failed every night would fill the disk.
- `-check "<command>"` prints the decision and runs nothing; `-log FILE` appends one line per decision.
- `deploy/sshd_eephus_ship.conf` (Match User ship: `ForceCommand`, publickey only, no TTY or forwarding, `AuthorizedKeysFile /etc/eephus/ship_authorized_keys`), `deploy/ship_authorized_keys.example` (`restrict,from=,command=`), the README section "The ship channel (port Stage 2)", and the pin's `producer.channel` naming the gate.

## Why

Stage 1 named the channel (a restricted user, `rrsync` rooted at `incoming/`) and left three things that would have failed on the first night:
1. `rrsync` is the Python rewrite since rsync 3.2.4; this repository takes no Python.
2. The producer sent `--chmod=D755,F644`, so what it uploaded was owner-writable only, and `bin/receive`, running as `eephus`, could not write the receipt, rename `READY` or prune. The producer now sends `--chmod=D775,F664` (its worktree commit, same day) and the gate's umask keeps the group bit.
3. sshd's StrictModes refuses an `authorized_keys` under a group-writable home, which the 2775 inbox is. The key file is now root-owned under `/etc/eephus`, which also stops the ship user adding a key.

## How verified

```
gofmt -l ./internal/shipgate ./cmd/shipgate      (clean)
GOOS=linux GOARCH=amd64 go build ./... && go vet ./...   exit 0
go test -count=1 -v ./internal/shipgate/
--- PASS: TestTheProducersCommandsParse
--- PASS: TestTheGrammarRefusesEachDefectAlone        (31 planted refusals, each for its own reason)
--- PASS: TestOtherRsyncVersionsClusterStillParses
--- PASS: TestCheckFollowsTheBundlesState
--- PASS: TestTheDiskFloorRefusesABodyWithAClearMessage
--- PASS: TestSweepRemovesOnlyAbandonedUploads
--- PASS: TestIDTime
ok      git.btq.ee/eephus/eephus-backend/internal/shipgate
```

`testdata/port_ship_remote_commands.txt` is the producer's `tools/port_ship.py --print-remote` output for three ships (sha256 `137e017b...ca23d8`); the producer's `test_port_ship.py` pins its own copy to the same bytes.

A rehearsal on the preparing PC with the built binary and a local copy of the pin (`verify/stage2_rehearsal.txt`): the producer's own `--print-remote` and `--dry-run` remote commands accepted; `READY` refused before the body ("READY goes last: bundle ... has no MANIFEST.tsv yet; send the body first") and accepted after; both calls refused once `READY` landed; the body refused under a 100000 GB floor ("383.9 GB free under ... is below the 100000.0 GB floor; nothing was written. ...") while `READY` passed; seven hostile commands refused; the sweep removing only the abandoned upload; and `bin/receive -verify-only` on the rehearsal bundle: `ok: 20261023T001053Z-6f82911d5778, 17837 files, 1304296283 bytes verified in 1.816s`.

Not executed here: sshd and a real rsync session (the preparing PC has neither rsync nor sshd configured). The remote command a client sends is the one rsync builds from its options; if a client of another rsync version sends a long option the gate does not know, the refusal names it and `-log` records the full command.

## Asks

1. Install as the README section says: `go build -o bin/ ./cmd/...`, the key file and sshd drop-in (`sshd -t`, reload), the sweep timer.
2. Send the owner the host key and confirm the address the ship comes from (`from=` and the firewall).
3. If you prefer a different floor than 8 GB, change `-min-free-gb` in both the key line and the drop-in.

# The served bundle: producer side of port Strategy D

**Date:** 2026-10-22. **Decisions:** PORT-GOAL and PORT-R1 to R4 (owner, DECISIONS_FOR_OWNER.md, section PORT RECON).

The public site must equal the final local build while building on the webmaster's
rebuild. Under R1 our Python pipeline stays the single producer, on the owner's PC,
and ships a frozen, sha256-manifested bundle nightly over a restricted SSH channel.
His box only publishes it. This page is the producer half: what the bundle holds, how
it is verified, how it ships, how its arrival is watched and when it runs. The box
half (the receive step, the publish filter, the buildsite skip-list) arrives as PRs
into his repository and is not built here.

Nothing here has shipped. No remote is configured, nothing was pushed, and the
scheduled task is not installed.

## 1. What the bundle holds

`python tools/port_bundle.py --served-bundle OUT_ROOT` writes `OUT_ROOT/<bundle-id>/`:

| Path | What it is |
|---|---|
| `site/` | The webroot image. Every page and asset directory of `deploy/publish_paths.txt`, plus every payload the nightly rsync ships: `data/*.json` and `data/*.js` at depth one minus `deploy/data_exclude.txt`, plus the per-player directories (`pitch_plots`, `player_detail`, `debuts_full`, `mgmt_decisions`, `ledger_clubs`, `franchise_clubs`, `mlb_events`, `mlbstats_player`, `mlb_player_detail`). The set is `port_equivalence.page_files` and `payload_files`, imported, so the bundle, the Gate C snapshot and the nightly's include lines agree. |
| `site/data/bundle_info.json` | Bundle id, `built_at`, git sha, content sha256, file and byte counts. |
| `MANIFEST.tsv` | `relpath`, `bytes`, `sha256` for every file under `site/`. |
| `SHA256SUMS` | The same sums in `sha256sum -c` form, so the box checks them with coreutils and no Python. |
| `BUNDLE.json` | Bundle id, git sha and dirty flag, counts by directory, the withheld names, the strip outcome per file, and the sha256 of `MANIFEST.tsv`. |
| `READY` | Written last: `<bundle-id><TAB><MANIFEST.tsv sha256>`. |

- **Bundle id:** `<UTC build time YYYYMMDDTHHMMSSZ>-<first 12 hex of the content sha256>`. Ids sort by build time, and two builds of the same bytes share the suffix.
- **Comment strips:** the nightly's two publish-time strips (`tools/strip_prospx_comments.py`, `tools/strip_asset_comments.py`) run on the bundle's copies, never on the sources, and fail open as they do on the box. `--no-strip` ships the sources unchanged.
- **Left out on purpose:**
  - `data/build_info.json` is the publisher's own heartbeat;
  - the scores and standings files live in the box's scores store behind their own nginx location;
  - `.cache/`, the database and the licensed imports are not served.
- **Retention:** `--keep 2` (the default) prunes all but the two newest bundles under `OUT_ROOT`, only after the new one verifies.

**Measured 2026-10-22.**
- **One real build, from a copy of the tree:** 17,837 files and 1,304,128,312 bytes after the strips, in 129 s.
  - That is 17,622 payloads: 9,047 player_detail, 2,768 debuts_full, 1,799 pitch_plots, 1,727 mlb_player_detail, 1,409 mlbstats_player, 572 at depth one, 240 mgmt_decisions, 30 ledger_clubs and 30 franchise_clubs.
  - Then 214 page and asset files, and `bundle_info.json`.
  - The strips touched 77 files; prospx went from 3,536,173 to 2,716,484 bytes.
  - `--verify-served` took 11 s, and `sha256sum -c` took 4 s.
- **The main tree's planned set:** 17,772 files and 1,305,847,718 bytes.
- **The older figure:** PORT_SPEC 1.1's about 19,346 payloads and 1.77 GB was measured on an earlier tree.

## 2. Verify

`python tools/port_bundle.py --verify-served OUT_ROOT/<bundle-id>` exits 1 unless all of these hold:
- every manifest row is present, with its byte count and sha256;
- nothing under `site/` is unlisted, except the receipt below;
- no name from the bundle's withheld list and no publisher heartbeat is present;
- `READY`, `BUNDLE.json` and `site/data/bundle_info.json` name the same bundle and the same manifest sha256.

The build verifies its own output before pruning, and the ship verifies again before anything leaves the PC.

On the box the same check needs no Python: `cd <bundle-id> && sha256sum -c --quiet SHA256SUMS`.

## 3. Ship

`tools/port_ship.ps1` (Windows) and `tools/port_ship.sh` (POSIX) wrap `tools/port_ship.py`.

**Configuration.** It lives in a local file the owner fills:
- the path is `EEPHUS_PORT_SHIP_CONF`, else `%USERPROFILE%\.eephus\port_ship.conf`;
- the template is `deploy/port_ship.conf.example`;
- the tool refuses a config file inside any git work tree, so the filled copy is never committed;
- the host must be an address Cloudflare does not proxy: the box's own address from an `ADMIN_SSH_CIDR` network, or WireGuard or Tailscale.

**A ship, in order:**
1. Verify the bundle (section 2). A bundle that fails is never sent.
2. `rsync -rt --partial` over `ssh -i <key> -p <port> -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes`. It sends everything but `READY` into `<remote dir>/<bundle-id>/` (default `/opt/eephus/artifacts/incoming`), with `--link-dest=../<last shipped id>`, so unchanged files become hard links on the box and only changed bytes cross the wire.
3. Send `READY` alone, last.
4. Record the ship in `.cache/port_ship/last_ship.json` and `ship_log.tsv`. Nothing is recorded unless both rsync calls succeed.

The ship never deletes anything on the box. `--dry-run` prints both commands and runs nothing.

**rsync on the PC.** The PC has no rsync today. Install cwRsync, MSYS2 (`pacman -S rsync`) or use WSL, then set `EEPHUS_SHIP_RSYNC` and `EEPHUS_SHIP_PATH_STYLE` (`cygdrive`, `msys` or `wsl`) to match.

## 4. The receive contract (for the webmaster's PR)

The box acts only on a directory under `incoming/` that holds `READY`. Its steps:
1. Run `sha256sum -c --quiet SHA256SUMS` there, and check that `READY`'s second field equals `sha256sum MANIFEST.tsv`.
2. Write `site/data/bundle_receipt.json` as `{"bundle_id": "...", "received_at": "<UTC ISO 8601>"}`. It is the one file the manifest does not list, and verify allows it.
3. Swap a `current` symlink to the new bundle atomically, the same pattern as his `Current` Build link.
4. Publish through his `publish.sh`.

**Rollback** repoints `current` to the previous bundle.

**Restricted user.** It needs write access to `incoming/` only: `rrsync` or a forced command. With `rrsync` rooted at `incoming/`, set `EEPHUS_SHIP_REMOTE_DIR=.`. `--link-dest` then stays inside the restricted directory.

**Disk.** Budget about 2.6 GB for two generations, less with the hard links.

## 5. The 36-hour heartbeat

`python tools/port_live_check.py --heartbeat --origin https://eephus.io` alarms (exit 1) when the newest bundle on the live site was received more than 36 hours ago, or when nothing answers.

It reads `/data/bundle_receipt.json` (`received_at`). If there is no receipt, it reads `/data/bundle_info.json` (`built_at`), which is an upper bound on the receive age, and it names which one it read.

It never reads the Go Build's `/data/build_info.json`. A box that keeps building its own numbers while our bundles stop arriving must alarm. A Cloudflare challenge counts as no answer.

## 6. Checking the published site against the bundle

```
python tools/port_equivalence.py compare-http --bundle OUT_ROOT/<bundle-id> --origin https://eephus.io --pace 0.5 --explained explained.tsv --out report.json
```

This fetches every manifest row from the published webroot. It sends one request at a time, with a browser user agent through curl, `--pace` seconds apart, and sorts each file into a category:

| Category | Meaning | Fails the check? |
|---|---|---|
| IDENTICAL | Same bytes. | No |
| LINE_ENDINGS | Same bytes once CRLF reads as LF. | No |
| CDN_INJECTED | An HTML page that is equal once Cloudflare's injected scripts are removed. | No |
| TIMESTAMP, FLOAT_REPR, ORDERING | The JSON ladder of Gate C. | No |
| EXPLAINED | Differs, and is named in the `--explained` file (`glob<TAB>reason`), for example the headshot proxy or the forums layer. | No |
| DIFFERENT | Differs, and the difference is named: the differing JSON leaves with both values, or the first differing line of any other file. | Yes |
| MISSING | Any status but 200. | Yes |
| BLOCKED | A Cloudflare challenge, not the origin's answer. | Yes |

- `--only data/` and `--every N` take a fixed slice for a quick pass.
- `--ref ref.json` compares against a `snapshot` instead of a bundle, but it can only name payload categories, because a snapshot keeps no page bytes.
- `port_live_check.py` gains `--pace` for its own pass, which also covers Gate B: the withheld names answer 404.

**First read-only sample, 2026-10-22.** Every 1,500th row (12 files) at a 1 s pace against the live site:
- all 12 were MISSING (404): `404.html` and eleven files under the data subdirectories, which the box's `publish.sh` filter does not ship today;
- the heartbeat alarmed, with no receipt and no `bundle_info.json`.

Both are expected before Stage 1.

## 7. When it runs

`deploy/port-nightly-task.xml` is a Windows Task Scheduler task. It is **not installed.**
- It runs `deploy/port-nightly.ps1` daily at 03:10 local time, the box nightly's old slot.
- `StartWhenAvailable` runs a missed night as soon as the PC is back.
- `IgnoreNew` never doubles a run.
- An 8-hour limit applies.

**The script keeps `deploy/nightly-build.sh`'s order:**
1. Yesterday's heartbeat (report-only).
2. The one-writer guard.
3. `run_monthly.py --daily`, or the full monthly on the 1st.
4. `build_site.py`.
5. The pytest gate (`EEPHUS_DEPLOY_RUN=1`): a red suite ships nothing.
6. The served bundle.
7. The ship.

Registering it is the owner's act:

```
Register-ScheduledTask -TaskName EephusPortNightly -Xml (Get-Content -Raw deploy\port-nightly-task.xml)
```

Register only after the config is filled and rsync is installed.

A hand run that builds a bundle and ships nothing:

```
powershell -ExecutionPolicy Bypass -File deploy\port-nightly.ps1 -SkipPipeline -NoShip
```

## 8. The box half, prepared as PRs (2026-10-22, task PORT_PR_PREP)

The webmaster's side of Strategy D is prepared as six stacked feature branches of `eephus/eephus`, built and tested locally from the read-only copy of his `main` (9e1423cc) and never pushed: `port-stage0-withheld-data` (the six withheld files untracked, the 44-name exclude union), `port-stage1-publish-contract` (the pin `frontend/deploy/artifact_manifest.json`, `publish.sh` publishing `current/site` with the nine `data/<subdir>` shards, `publish_paths.txt` with our 33 page directories and no `teams/`), `port-stage1-buildsite-ownership` (his generator and site tests skip the pages the pin says the bundle owns), `port-stage1-receive` (`cmd/receive` in Go: verify against MANIFEST.tsv and the pin, write the receipt, rename READY to RECEIVED or REJECTED, swap `current` atomically, prune; `eephus-receive.path` and `.service`; nginx and Cloudflare no-store for the two bundle heartbeats), `port-stage1-sidecars` (the twenty JSON `/partials/` routes serve the bundle's file verbatim under `-bundle-dir`) and `port-stage1-pages` (our 214 pages and assets in his `frontend/`, LF, with his deep-link fix carried in). The plan with merge order, test lines and the owner defaults is `docs/port/prs/PR_PLAN.md`; the six PR descriptions and the per-branch build and test records sit beside it. The receive contract of section 4 is what `cmd/receive` implements, measured against the rehearsal bundle `20261023T001053Z-6f82911d5778` (17,837 files, 1,304,296,283 bytes): verified in 1m29s cold and 1.9s warm, a planted unlisted file rejected.

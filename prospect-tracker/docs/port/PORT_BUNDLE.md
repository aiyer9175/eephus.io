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
  - `data/build_info.json`'s box-side twin, the publisher's receipt, is written by the box, never shipped;
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
2. `rsync -rt --partial --chmod=D775,F664` over `ssh -i <key> -p <port> -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes`. It sends everything but `READY` into `<remote dir>/<bundle-id>/` (default `/opt/eephus/artifacts/incoming`), with `--link-dest=../<last shipped id>`, so unchanged files become hard links on the box and only changed bytes cross the wire. The modes are group-writable so the box's receive step, running as `eephus` in the inbox's group, can write the receipt, rename `READY` and prune (with `D755,F644`, the first version, it could do none of the three).
3. Send `READY` alone, last.
4. Record the ship in `.cache/port_ship/last_ship.json` and `ship_log.tsv`. Nothing is recorded unless both rsync calls succeed.

The ship never deletes anything on the box. `--dry-run` prints both commands, and the two remote commands they make rsync send, and runs nothing.

**rsync on the PC.** The PC has no rsync today. Install cwRsync, MSYS2 (`pacman -S rsync`) or use WSL, then set `EEPHUS_SHIP_RSYNC` and `EEPHUS_SHIP_PATH_STYLE` (`cygdrive`, `msys` or `wsl`) to match.

## 4. The receive contract (for the webmaster's PR)

The box acts only on a directory under `incoming/` that holds `READY`. Its steps:
1. Run `sha256sum -c --quiet SHA256SUMS` there, and check that `READY`'s second field equals `sha256sum MANIFEST.tsv`.
2. Write `site/data/bundle_receipt.json` as `{"bundle_id": "...", "received_at": "<UTC ISO 8601>"}`. It is the one file the manifest does not list, and verify allows it.
3. Swap a `current` symlink to the new bundle atomically, the same pattern as his `Current` Build link.
4. Publish through his `publish.sh`.

**Rollback** repoints `current` to the previous bundle.

**Restricted user.** Its key forces the webmaster's `bin/shipgate` (port PR 7, `internal/shipgate`), which reads the remote command from `SSH_ORIGINAL_COMMAND` and accepts exactly the two calls above: `rsync --server <cluster> --partial [--bwlimit=N] [--link-dest=../<id>] . <inbox>/<bundle-id>/`, then the same into `<inbox>/<bundle-id>/READY`. `<inbox>` is the pin's `paths.incoming` spelled exactly, so `EEPHUS_SHIP_REMOTE_DIR` must be that absolute path (the tool refuses `.` or a trailing slash). Before rsync runs, the gate refuses `READY` until the body's `MANIFEST.tsv`, `SHA256SUMS`, `BUNDLE.json` and `site/` have arrived, refuses either call into a bundle that already has `READY`, `RECEIVED` or `REJECTED` (so a bundle id is shipped once), and refuses the body when the box's free space under the inbox is below its floor (8 GB by default), with a message that lands in the PC's ship log. `python tools/port_ship.py --print-remote <bundle-id> [--link-from <id>]` prints the remote commands; `test_fixtures/port_ship/remote_commands.txt` is that output and the gate's test fixture, byte for byte (`test_port_ship.py` pins its sha256). A daily sweep on the box removes an abandoned upload (no marker, its id more than 48 hours old).

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

## 9. Bundle slimming (2026-10-27, task PORT_STAGE2_PREP)

**Question.** Which of the bundle's files does no page or script ever fetch, so the bundle can leave them out without changing a served page?

**Method.** Two independent reads of the served set, intersected:
- A static scan of every page-set file (the 214 pages, assets, prospx, the CollegeSavant modules and vendor; 82 MB of text). A payload counts as named when its file name appears, its stem appears as a quoted string, or a numbered prefix of it appears (`awards_${year}.json`). A shard directory counts as named when `<dir>/` appears. A payload that no page names is then looked up in every other served depth-one payload (a registry row a page may render as a link) and in the Go server's sidecar table (port PR 5). On top of that, every shard file's key was looked up among every string, key and integer of the served payloads and every token of the page set.
- A headless Chromium crawl of all 37 pages plus six deep links on the served worktree, logging every request the server answered (210 requests, 76 under `data/`).

**Result.** The bundle is close to minimal. Every shard directory is named, and every shard key is reachable but one (`mlb_player_detail/will_smith__519293.json`, 4,555 bytes, kept, because a disambiguated key can be built at run time). At depth one, 536 of 573 payloads are named; 37 (5,865,389 bytes, 0.45% of the bundle) are named by nothing: pipeline inputs (overrides, maps, benchmarks), lab, gate and evaluation records, pipeline ledgers, and `model_updates.json`, which `build_site.build_model_updates` renders into `/models/updates/` at build time. None of them was requested by the crawl.

**The list.** `SLIM_EXCLUDE` in `tools/port_bundle.py`, each with its reason. `--served-bundle` leaves them out by default and `--no-slim` keeps them. They stay in the local tree and in `port_equivalence.payload_files` (the nightly rsync's set), so the local site and its snapshot are unchanged. Before a slimmed build, `slim_violations` re-runs the name scan for the listed files (about 10 seconds on the full tree); if any page, asset or other payload has started to name one, the build refuses (`SlimError`, exit 1) and writes nothing, so a page that begins fetching a listed file fails the build instead of answering 404 on the box.

**The proof** (`python tools/port_equivalence.py compare-bundles`). Two bundles from the same worktree, minutes apart: full `20261027T235310Z-0507c0fe732a` (19,500 files, 1,313,198,226 bytes) and slim `20261027T235541Z-e54140664b09` (19,463 files, 1,307,332,837 bytes). All 214 page and asset rows identical; no row changed or added; 37 dropped, exactly the list; every file fetched by the worktree crawl and by crawls of both bundles' sites present in the slim bundle with the same bytes; and the two bundle crawls answered every one of 206 requests with the same status and bytes. The webmaster's `bin/receive -verify-only` accepts the slim bundle (`ok: 20261027T235541Z-e54140664b09, 19463 files, 1307332837 bytes verified in 2.039s`).

**Not slimmed, and why.** The shard directories are the bulk (pitch plots 439 MB, player detail 262 MB, graduates 80 MB, management decisions 42 MB) and every file in them is reachable from a key a page holds. Trimming them is a producer question (fewer pitch plot points, or shards only for players on a board), not a packaging one.

**Found on the way.** `data/scores/` is in neither the nightly rsync's set nor the bundle: the scores job (`tools/scores_job.py`) was designed to write it on the box behind its own nginx alias (`deploy/README.md`, the `/data/scores/` location). Under PORT-R1 the box runs no Python, so on the box `/scores/` loads its page and 404s `/data/scores/latest.json` (both bundle crawls show it). This is an owner question (the PORT_STAGE2_PREP report), not a slimming change. Resolved by the owner on 2026-10-27 (PORT-Q-SCORES, "Ship it in the bundle"): section 11.

## 11. The scores store travels in the bundle (2026-10-27, task PORT_SCORES_PR11)

**Decision.** Owner PORT-Q-SCORES (2026-10-27, "Ship it in the bundle"): `data/scores/` rides the nightly served bundle, as of the build, so `/scores/` and `/standings/` have their data on the box under PORT-R1. The scores job keeps running on the PC and writing the local store every few minutes; the published copy moves once a night with the bundle.

**Producer side.** `port_equivalence.LIVE_DIRS = ("data/scores",)` and `live_files()` name the live store; `port_bundle.served_files` adds it to the page set and the nightly rsync's payload set, never slimmed, and `build_served` copies it with one tolerance the shards do not need: a live file the job removed between the listing and the copy is left out of that night's bundle and named in `BUNDLE.json` (`live_vanished`) instead of failing the build. `BUNDLE.json` counts the store under `live` and `files_by_top`. The nightly rsync's set is unchanged: `payload_files` never gains the store, `deploy/nightly-build.sh`, `publish_paths.txt` and `data_exclude.txt` still do not name it, and `test_scores_fence` and `test_publish_manifest` keep that fence. `compare-bundles` reports live rows under `live` (changed, added, dropped) and never fails on their bytes, because two bundles from the same tree minutes apart differ there whenever the job has run; a live file a crawl fetched must still be present in the new bundle, and the two site crawls must have answered a live path with the same status. `compare-http --bundle` compares the store's rows like every other row: on the box they are the bundle's own bytes.

**Measured 2026-10-27 (worktree wt-PORT_SCORES_PR11).** `--plan-served`: 19,462 files and 1,309,204,786 bytes before, 19,542 files and 1,311,641,012 bytes after; the store is 80 files and 2,436,226 bytes (latest, the index, `index-2026`, 20 date files, 29 games and the standings shards). One real build: bundle `20261028T025004Z-d763ad28d516`, 19,543 files, 1,309,775,995 bytes, `MANIFEST.tsv` sha256 5dbc4f0e, `--verify-served` ok, `live` 80 and `live_vanished` none; the webmaster's `bin/receive -verify-only` accepts it (docs/port/prs/verify/scores_receive_verify.txt). A headless crawl of the bundle's `site/` (docs/port/prs/verify/scores_bundle_crawl.txt): `/data/scores/latest.json` answers 200 with the store's bytes, `/scores/` and `/standings/` render from it, and the stamp line on `/scores/` reads the sentence below.

**The page.** On the box the job's `next_by` has passed by the time a reader arrives, so `assets/scores.js` reads S1 (or S2 on a date with a game that was live at the build, S3 after 36 hours), and in those states it asks `/data/bundle_info.json` once; when the bundle's heartbeat answers, the stamp adds "Published with the nightly site build, <month day>, <time>." after the stale sentence. A site without a bundle (the local tree) answers 404 and the stamp says nothing more; while the job is current (S0) nothing is asked. `test_scores_client.py` pins the loader and `test_scores_render.py` renders the three cases.

**Box side.** PR 11, `port-stage2-scores-in-bundle` (docs/port/prs/PR_11_port-stage2-scores-in-bundle.md): `frontend/deploy/publish_paths.txt` gains `data/scores`, so `publish.sh` ships the directory whole from `current/site`; `deploy/nginx/eephus.io.conf` serves it through the existing `/data/` location and its comment forbids an alias to a box-written directory; the earlier design of a job on the box writing `/opt/eephus/scores` behind `location ^~ /data/scores/` (our `deploy/README.md`, `deploy/WEBMASTER.md` section 10) is withdrawn and was never installed; `internal/site/scores_test.go` pins the entry, the three assets' `/data/scores/` reads and the absence of the alias; `docs/port-cutover.md` checks `/data/scores/latest.json` on cutover day.

**Staleness, stated.** The published scores are up to a day old during games; the page says so. Live scores on the box would need the ship channel to carry the store every few minutes (PORT_STAGE2_PREP's OWNER-Q1 option (a)) or a Go scores job behind a shadow gate (option (c)); either is a later PR, and the owner chose the bundle.

## 10. The ship gate and Stage 3 (2026-10-27, task PORT_STAGE2_PREP)

Four more stacked branches of `eephus/eephus` sit on `port-stage1-pages` (docs/port/prs/PR_PLAN.md has the merge order and the test lines):
- `port-stage2-transport`: `bin/shipgate`, the forced command on the ship user's key, accepting exactly the two calls in section 3, with the disk floor, READY last, never into a marked bundle, and a daily sweep of abandoned uploads; the producer side moved to `--chmod=D775,F664` so the box's receive step can mark, swap and prune what arrives.
- `port-stage3-shadow-gates`: `bin/shadoweq` and `deploy/shadow_gates.tsv`, the registered per-field equivalence table the Go models are measured against; it serves nothing.
- `port-stage3-asof-accessor`: `internal/asof` and `docs/AS_OF_ACCESSOR.md`, the schema-level as-of accessor and its classification of all 57 store tables.
- `port-cutover-checklist`: `docs/port-cutover.md`, main-deploy day and its rollback.

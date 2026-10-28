# PORT RUNBOOK: the local eephus.io build to git.eephus.io and the live box, Strategy D

Rewritten 2026-10-27 by task PORT_FINAL around the owner's 2026-10-22 answers (PORT-GOAL,
PORT-R1 to R4, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md` section PORT RECON) and the
reconnaissance of git.eephus.io (`docs/port/PORT_RECON.md`, a copy of the 2026-10-22
report). The first version (2026-10-22, task PORT_PREP) pushed the Python repository to
the box and ran the pipeline there; that is Strategy A in PORT_RECON section 4 and it
is withdrawn. The design is `docs/port/PORT_SPEC.md`; the producer half is
`docs/port/PORT_BUNDLE.md`; the box half is the ten prepared PRs in
`docs/port/prs/PR_PLAN.md`; the cutover day is PR 10's `docs/port-cutover.md`. This
file is the order of operations across all of them, with the commands.

**The goal (owner, verbatim):** "The goal is to have the public site (via git.eephus)
be identical to the final local version of the site, while building on what the
webmaster has already built in regards to the rebuild." Two hard requirements:
IDENTICAL (every page, feature and served number on eephus.io equals the frozen local
build, proven by an equivalence check with each difference named) and BUILD ON HIS WORK
(his Go backend, deploy, Forgejo PR flow and frontend fixes are kept and extended).

**Strategy D in one paragraph.** Our Python pipeline stays the one producer, on the
owner's PC, outside his repository. Each night it builds a frozen, sha256-manifested
bundle of the served site and ships it over a restricted SSH channel. His box verifies
the bundle and publishes it through his own `publish.sh`. Ten small PRs into his `main`
make that possible (Stage 0 hygiene; Stage 1 the publish contract, receive step,
sidecars and pages; Stage 2 the transport; Stage 3 the shadow-challenger measurement and
the as-of accessor). His Go models keep running as shadow challengers and serve nothing
until a registered equivalence gate passes.

Three parties take part:

- **OWNER**, on the Windows PC `C:/Users/noah/baseball-projects/BaseballR`, branch
  `efv-conviction-2026-08-08`. Claude Code runs here. The PC is the producer.
- **WEBMASTER** (baron), who owns `eephus/eephus` on git.eephus.io, the box and
  Cloudflare. He reviews and merges every PR and operates the box.
- **THE BOX**, one Debian VPS (3 vCPU, 6 GB RAM, 55 GB disk) behind Cloudflare Free. It
  runs no Python after the port.

How to use this file with Claude Code: open Claude Code in the named directory on the
PC, paste the step's **Say** line, and let it run the step's commands. Each step ends
with a **Check**; do not start the next step until the check passes. Steps marked
WEBMASTER are his; the owner sends him the step's text. Nothing here force-pushes,
pushes to `main` or `main-deploy`, or deletes a repository or the live webroot.

---

## 0. Where things stand (measured 2026-10-22, corrected 2026-10-27)

**The live site is the webmaster's replacement stack**, not this codebase: git.eephus.io
`eephus/eephus`, branch `main-deploy` at `9c7c04e465e7` plus uncommitted edits on the
box (the heartbeat's `-dirty`), with a Go nightly Build into SQLite at 03:10 ET,
`cmd/buildsite` regenerating 13 shell pages, and a Go server answering `/partials/` and
`/images/headshots/`. Its frontend is our code at `71ea151` (2026-07-19) plus his fixes.
The full inventory is PORT_RECON sections 1 to 3.

### 0.1 Every live-versus-local difference, its cause, and the step that resolves it

| # | Difference (live https://eephus.io against the local build) | Cause | Resolved by |
|---|---|---|---|
| LV-1 | Live heartbeat `data/build_info.json` reads `{"generated_at":"2026-10-22T07:24:40Z","git_sha":"9c7c04e465e7-dirty","mode":"nightly"}`. | Written by his Go binary (`internal/nightlyjobs/heartbeat.go:30`); `-dirty` means the box's tree has uncommitted edits. | Ask 2 (he commits the box diff). After cutover the bundle's own heartbeats (`bundle_info.json`, `bundle_receipt.json`) are what the 36-hour alarm reads; his `build_info.json` keeps reporting his Build. |
| LV-2 | Live assets are the remote `frontend/assets` at main-deploy: `eephus-nav.js`, `site.css`, `fa.js`, `parks.css` byte-equal to `origin/beta` 03c1428e; `projections.js`, `glossary.js`, `trademachine.js`, `mlbstats.js`, `pal.js`, `parks.js` rewired to `/partials/`. | His frontend fork. | PR 6 (our 214 pages and assets replace `frontend/`); the bundle ships them. |
| LV-3 | Live serves 38 `/partials/` routes (HTML fragments and JSON sidecars) from his Build. | His live-query layer (PORT_SPEC section 7, W-1). | Owner R2: static pages at cutover; PR 5 makes the JSON sidecars serve the bundle's file verbatim; a fragment route goes back to htmx only after Gate F (section 7). |
| LV-4 | Live sitemap 17 URLs, local 33; 18 local routes 404 live (`/arbitration/ /awards/ /betting/ /diamond/ /forums/ /franchise/ /franchises/ /history/ /hof/ /ledger/ /library/ /management/ /models/ /models/updates/ /parks/ /scores/ /scouting/ /standings/`). | Built after 2026-07-19, never delivered. | PR 2 (`publish_paths.txt` gains the 33 directories, drops `teams/`), PR 6, the bundle. |
| LV-5 | Live nav 14 links; local `NAV_ITEMS` 22. | Same as LV-4. | PR 6, the bundle. |
| LV-6 | Of 570 local depth-one payloads, 329 answer 404 live, including `timeseries.json`, `debuts.json`, `trade_values.json`, `mlb_projections.json`, `player_links.json`, the `scout_reports_N.json` chunks and every awards, betting, hof, management, franchise and ledger payload; the data subdirectories (about 22) are not shipped by his `publish.sh` filter at all. | Newer exporters; his publish ships only top-level `/data/*.json` and `*.js`. | PR 2 (`publish.sh` publishes `current/site` with the nine `data/<subdir>` shards); the bundle. |
| LV-7 | Six withheld files are served live: `comps.json`, `fielding_census_ids.json`, `identity_collisions.json`, `milb_pitch_rates.json`, `positional_fit.json`, `positions_played_seasons.json`. | They are tracked in his `frontend/data` and missing from his 24-entry `data_exclude.txt`; deleting them from the webroot is undone by his next publish. | PR 1 (`git rm` the six, `data_exclude.txt` becomes the 44-name union; his `TestExcludedData*` pass). Gate B asserts all 44 names answer 404. |
| LV-8 | Of 85 local `assets/`, 59 answer 404 live. | Same as LV-2 and LV-4. | PR 6, the bundle. |
| LV-8b | `robots.txt` live still disallows `/teams/`; local drops the line. | Beta-era file. | PR 6. |
| LV-9 | Live `data/xfv.json` says `generated_at 2026-07-17`, 9,040 players; the live pages read `/partials/efv`. | The file is tracked in his repo. | PR 6 and the bundle (the bundle's `xfv.json` is the one the pages read). |
| LV-10 | **Served numbers differ for every sampled entity.** Ten entities (seed 20261022), 80 field comparisons, 25 equal: every MLBAM id and most org codes equal; every eFV grade, eFV WAR, trade value and projection WAR different (Jacob Wilson eFV 60.5 live / 55.1 local, trade value $15.7M / $34.4M; Jake Fraley trade value $23.4M / $0.0M; Daniel Jackson eFV 48.5 / 41.9). Coverage differs: trade values 5,231 players live / 6,316 local, eFV 5,231 / 9,515, projection veterans 1,150 / 1,400, player links 5,231 / 6,415. Team codes `OAK`, `WAS` live / `ATH`, `WSN` local. | His Go re-implementation (bWAR frame, the summer xFV lineage, a name-slug identity key) is a different model, not an older copy of ours. | Expected and intended: at cutover **every model number on the live site moves to the local value**, and the dated note of P-6 says so (`docs/port/NEWS_NOTE_V2.md`). His models become shadow challengers (section 7). |
| LV-11 | git.eephus.io inventory. | Read 2026-10-22 with the owner's credentials into `refs/eephusgit/*` (read-only, nothing pushed). | Closed: PORT_RECON section 1. |
| LV-12 | GitHub `origin`: `efv-conviction-2026-08-08` there is `8e2361f4` (2026-10-07); the local branch is 1,048 commits ahead (2026-10-27). | Nothing pushed since 2026-10-07 (lanes never push). | Owner step L2 pushes the archive (`-c http.sslBackend=schannel`); GitHub stays the read-only archive (R3). |

### 0.2 What the rehearsals showed

- **2026-10-22, Strategy A clean clone (kept for the record):** a clean clone seeded from
  the 29.71 GB cache bundle and the database rebuilt every served payload identical to the
  local build only when the gitignored served data was carried too (P-5 (a));
  `--rebuild-only` alone left 3,146 payloads missing and 3,054 different, mostly because
  the local served artifacts were older than the code. That is why the producer rebuilds
  before every freeze (step L1). The clone needed no R. The deploy test gate then read
  177 failures, 91 of them red at HEAD too: owner P-8 cleared them
  (`docs/port/RED_TESTS_CLEARED.md`, 17,686 passed in all).
- **2026-10-23 to 2026-10-27, Strategy D (PORT_BUNDLE_TOOLING, PORT_PR_PREP,
  PORT_STAGE2_PREP):** a served bundle builds in about 2 to 3 minutes (17,837 files,
  1,304,296,283 bytes on 2026-10-23; 19,463 files and 1,307,332,837 bytes slimmed on
  2026-10-27), verifies in 11 s with Python and 4 s with `sha256sum -c`; his
  `bin/receive -verify-only` accepts it (1m29s cold, 1.9 s warm) and rejects a planted
  unlisted file; the ship's remote commands match his `bin/shipgate` fixture byte for
  byte; `bin/shadoweq` reads 10 PASS on the bundle against itself and 8 FAIL with his
  committed data as the challenger; `internal/asof` classifies all 57 store tables.
  Every Go gate is green on every branch (`docs/port/prs/verify/`).
- **2026-10-27, the final tree (this task, section 6):** the v2.0 label applied, the
  regeneration of RED_TESTS_CLEARED section 0 rerun, the test files of everything changed
  since that document rerun in deploy mode (RED_TESTS_CLEARED section 6), the REF
  snapshot and a slimmed bundle frozen from the result.
- **2026-10-27, the re-freeze (PORT_REFREEZE, section 6):** after the PORT_SCORES_PR11 and
  LEDGER_PAYROLL_REFRESH merges, their main-tree steps, `build_site.py`, the restamp and
  `gen_audit_docs.py` rerun and committed (no served number moved: stamps, shard hashes
  and two corrected asset stamps), then L4 and L5 rerun; the bundle now carries the
  80-file scores store.

---

## 1. Owner decisions

The 2026-10-22 answers supersede the first runbook's defaults where they differ.

| ID | Question | Answer (2026-10-22) | What it changes |
|---|---|---|---|
| P-1 | History on the new remote | **Superseded by R3 "Outside his repo":** no history push into `eephus/eephus`. GitHub stays the archive; optionally a separate `eephus/pipeline-archive` pushed in pieces under 100 MB (largest blob 49.3 MB). | Step L2 pushes the archive to GitHub. The 855 MiB pack never crosses Cloudflare's 100 MB cap. |
| P-2 | The `/partials/` layer | **Superseded by R2 "Pages + numbers":** static pages at cutover; the JSON sidecars serve the bundle's bytes (PR 5); a fragment route returns to htmx only when its rendered page and numbers equal the static page (Gate F). Named differences: the headshot proxy (not taken by default) and the forums and accounts layer (shipped inert). | Nothing is removed from his server; it is brought to equivalence route by route. |
| P-3 | Python on the target | **Default stands, re-scoped to the producer:** Python 3.13.9 with `constraints-local.txt` on the PC. The box runs no Python. | `tools/freeze_constraints.py --check` is a producer check. |
| P-4 | Cache carry | **Superseded by R1 "Your PC, ships nightly":** the 29.71 GB cache (363,455 files, `tools/port_bundle.py --plan`, 2026-10-22) and the 1.96 GB database stay on the PC with the producer. | Nothing large crosses to the box; its disk budget is two bundle generations (about 2.6 GB with hard links). The PC backup list in section 10 replaces the box backup. |
| P-5 | Gitignored served artifacts | **Default stands as "the bundle is the served data":** every payload the nightly rsync ships goes in the bundle (`port_equivalence.payload_files`), minus the 36 payloads nothing fetches (`SLIM_EXCLUDE`, PORT_BUNDLE section 9; 37 until 2026-10-28). | The first publish equals the reference by construction. |
| P-6 | Announcing the number change | **(a) a dated note the day of cutover.** `/news/` has no hand-written row type, so the note is a dated article (`docs/port/NEWS_NOTE_V2.md`), published in cutover day's first bundle (step C-6). It names every model that moved and links `/models/` and the registry; it includes the xHEM+ park-matched flip (EW3-53). | A reader who saw the old numbers is told why they moved. |
| P-7 | The version label (FP1-4) | **(a) applied before the snapshot, 2026-10-27:** `EEPHUS_VERSION = "v2.0"`, the module beta chips dropped (`_stage_chip` renders nothing for a beta-stage row), the Diamond preview chips kept; PROSPX and the CollegeSavant bar edited by hand to match. | The reference and the published site carry the same label. |
| P-8 | The red tests | **Cleared first** (`docs/port/RED_TESTS_CLEARED.md`, 2026-10-26, 17,686 passed in all; the delta rerun of 2026-10-27 in its section 6). | The PC's nightly gate (`deploy/port-nightly.ps1` step 5) means what it says: a red suite ships nothing. |
| P-9 | CollegeSavant logos | **Default stands:** the 16 gitignored `collegesavant/logos/*.png` ride in the bundle (every gitignored file inside a published page directory does). | No clone step; the bundle is complete. |
| Q1 | Where the producer runs | **R1 (a):** the owner's PC, shipping nightly. Revisit a second box after the watch week if PC uptime or the 15-minute betting jobs require it. | Section 9 risk 1. |
| Q2 | "Identical" for htmx pages | **R2 (a):** identical pages and numbers. | Gate F per route. |
| Q3 | Where the Python code lives | **R3 (a):** outside `eephus/eephus`. | No `.py` file ever enters his repo (his AGENTS.md). |
| Q4 | His Go models | **R4 (a):** shadow challengers behind registered gates, with the as-of accessor first. | PR 8 and PR 9; Gate G. |

Defaults the preparing tasks took, each vetoable (PR_PLAN.md "Owner decisions this plan
takes as defaults"): the pages keep their `img.mlbstatic.com` headshot URLs; the forums
and account layer ships inert; his repository's copy of the pages is LF with unstripped
sources while the bundle carries the stripped copies; the ship gate refuses a body under
8 GB free and sweeps a markerless upload after 48 hours; the shadow gates require the same
printed digits on every row; bundle slimming is on. PORT_STAGE2_PREP's open question
on `data/scores/` was answered on 2026-10-27 (PORT-Q-SCORES, "Ship it in the bundle"):
the bundle carries the store as of its build, PR 11 publishes it on the box, and the
page says the scores came with the nightly build (PORT_BUNDLE.md section 11).

---

## 2. OWNER steps on the PC (the producer side)

### L1. Freeze the tree: rebuild, label, note

**Say:** "Run PORT_RUNBOOK step L1: confirm nothing is running, rebuild the served
artifacts in the documented order, and show me what is uncommitted under prospect-tracker."

```bash
tasklist | findstr /i python          # no run_monthly.py, no pytest, no exporter
cd prospect-tracker && git status --short | head -50
```

The bundle carries the working tree's served files, so an uncommitted artifact ships; the
rule is that every served artifact is the output of the commit being frozen. Rebuild in
the nightly's order (outside 06:00 to 11:00 UTC, on no registered look day), which is
RED_TESTS_CLEARED section 0 plus its section 4:

```bash
python run_monthly.py --rebuild-only        # or --daily for the daily-only artifacts and F-SCORE
python tools/export_trade_values.py && python tools/export_trade_values.py
python fa_export.py && python ledger_export.py && python fscore_export.py && python franchise_export.py
python -c "import fa_pipeline; print(fa_pipeline.rebuild_realized_ledger())" && python fa_export.py
python tools/port_red_tests_glossary_registry.py
python build_site.py
python -c "import build_site as B; B.restamp_hand_authored_pages()"
python tools/gen_audit_docs.py
```

P-7 is already applied at HEAD (v2.0). P-6's note is published on cutover day, not here
(step C-6), because its date is cutover day. Commit the regenerated tracked artifacts by
path as one snapshot commit ("Port snapshot: tracked artifacts as built on <date>").

**Check:** `git status --short` prints nothing under `prospect-tracker/` except
gitignored state, and `python tools/copy_lint.py --served --check` is clean.

### L2. Record and push the archive (R3)

**Say:** "Run PORT_RUNBOOK step L2."

```bash
cd /c/Users/noah/baseball-projects/BaseballR
git for-each-ref --format="%(objectname) %(refname)" refs/heads refs/remotes > prospect-tracker/docs/port/ARCHIVE_TIPS.txt
git ls-remote https://github.com/aiyer9175/eephus.io >> prospect-tracker/docs/port/ARCHIVE_TIPS.txt
git add prospect-tracker/docs/port/ARCHIVE_TIPS.txt && git commit -m "Port: record every branch tip before the move"
git -c http.sslBackend=schannel push origin efv-conviction-2026-08-08      # the owner's own push (FP1-2)
```

GitHub is the read-only archive of the Python code and its history (PORT_SPEC 4.3, 6.4):
push nothing else there, never delete it. The lanes never push; this is the owner's
command. An optional `eephus/pipeline-archive` on git.eephus.io takes the same history in
pushes under 100 MB each (`git push <remote> <commit>:refs/heads/archive` for successive
commits; the largest blob is 49.3 MB).

**Check:** `git ls-remote origin efv-conviction-2026-08-08` prints the local sha.

### L3. The test baseline (Gate A)

Owner P-8 cleared the suite: `docs/port/RED_TESTS_CLEARED.md` records
`3 failed, 17683 passed, 93 skipped, 2 xfailed` on the last full deploy-mode run with the
three load-flaky PROSPX card waits green on rerun (17,686 passed in all), and section 6
the delta rerun of 2026-10-27. The full suite takes about 2.5 hours on this PC and is not
rerun for the port; the PC nightly's gate runs it every night before a ship
(`deploy/port-nightly.ps1` step 5).

```bash
cd /c/Users/noah/baseball-projects/BaseballR/prospect-tracker
python --version && python tools/freeze_constraints.py --check      # P-3: 3.13.9, constraints-local.txt
```

**Check:** `freeze_constraints.py --check` prints "constraints-local.txt matches this interpreter".

### L4. The reference snapshot (Gate C's REF)

**Say:** "Run PORT_RUNBOOK step L4."

```bash
cd /c/Users/noah/baseball-projects/BaseballR/prospect-tracker
mkdir -p ../port_out
python tools/port_equivalence.py snapshot --root . --out ../port_out/ref.json
python tools/port_equivalence.py selftest data/trade_values.json
sha256sum ../port_out/ref.json
```

The snapshot records every served payload's leaves and every page's hash; the selftest is
the positive control and must print `"ok": true` with one leaf reported. The frozen
values of 2026-10-27 are in section 6; re-freeze after any rebuild, because the REF must
be the output of the commit being ported. The REF that the box pins is the shipped
bundle's `MANIFEST.tsv` sha256 (step C-1), and `ref.json` is what `compare-http --ref`
reads when a bundle directory is not at hand.

**Check:** both commands exit 0; the sha256 is written into section 6.

### L5. Build the served bundle

**Say:** "Run PORT_RUNBOOK step L5."

```bash
python tools/port_bundle.py --plan-served                                   # counts only
python tools/port_bundle.py --served-bundle ../port_out/bundles             # slimmed, stripped, --keep 2
python tools/port_bundle.py --verify-served ../port_out/bundles/<bundle-id>
```

What the bundle holds, how it verifies and how it ships is PORT_BUNDLE.md sections 1 to
3. `--no-slim` keeps the 36 unfetched payloads (37 until 2026-10-28, PORT_BUNDLE section 9); `--no-strip` ships the comment-carrying
sources. The cache, the database and the licensed imports never enter a bundle.

**Check:** `--verify-served` exits 0; `READY` names the bundle id and the `MANIFEST.tsv`
sha256; the counts match `--plan-served`.

### L6. Prepare the ship channel

PORT_BUNDLE.md section 3 and `deploy/port_ship.conf.example`. Install rsync on the PC
(cwRsync, MSYS2 or WSL); copy the example to `%USERPROFILE%\.eephus\port_ship.conf`
(outside every checkout) and fill `EEPHUS_SHIP_HOST`, `EEPHUS_SHIP_USER`,
`EEPHUS_SHIP_KEY` and the absolute `EEPHUS_SHIP_REMOTE_DIR` (the pin's `paths.incoming`,
`/opt/eephus/artifacts/incoming`) once the webmaster has sent the host, user and host key
(step S-4). Then:

```bash
python tools/port_ship.py --latest ../port_out/bundles --dry-run      # prints both rsync calls and the remote commands
```

**Check:** the dry run's remote commands have the shape of `test_fixtures/port_ship/remote_commands.txt`.

---

## 3. Stage 0 and Stage 1: the PR set, numbered (OWNER and WEBMASTER)

The eleven branches are prepared, tested and never pushed (PR_PLAN.md; PR 11 was added on
2026-10-27 for the scores store). They are stacked: each is one commit on the previous, so
merging in order is eleven fast-forwards and the webmaster reviews each diff alone.

| # | Branch | Commit | What it does | Stage |
|---|---|---|---|---|
| 1 | `port-stage0-withheld-data` | 33398bf | Untracks the six withheld files; `data_exclude.txt` becomes the 44-name union | 0 |
| 2 | `port-stage1-publish-contract` | f277e7c | The pin `frontend/deploy/artifact_manifest.json`; `publish.sh` publishes `current/site` with the nine `data/<subdir>` shards; `publish_paths.txt` gains our 33 directories and drops `teams/` | 1 |
| 3 | `port-stage1-buildsite-ownership` | 3eac0ba | `cmd/buildsite` and the site tests honour the pin's `owned` list, so his generator never overwrites a bundle-owned page | 1 |
| 4 | `port-stage1-receive` | 5e0bf24 | `cmd/receive` and `internal/artifact`: verify against `MANIFEST.tsv` and the pin, write the receipt, atomic `current` swap, prune; `eephus-receive.path/.service`; nginx and Cloudflare no-store for the two bundle heartbeats | 1 |
| 5 | `port-stage1-sidecars` | 935dc8c | The JSON `/partials/` routes serve the bundle's file verbatim under `-bundle-dir`; a missing file is a 404, never the Build's numbers | 1 |
| 6 | `port-stage1-pages` | 03b5013 | Our 214 pages and assets replace `frontend/`'s (LF), `teams/` deleted, his deep-link fix carried in | 1 |
| 7 | `port-stage2-transport` | 766a65e | `cmd/shipgate`, the ship user's forced command (body then `READY`, disk floor, never into a marked bundle), the daily sweep, the sshd drop-in and key file | 2 |
| 8 | `port-stage3-shadow-gates` | e14d10d | `deploy/shadow_gates.tsv` (20 registered per-field gates over 10 modules) and `cmd/shadoweq`: his models measured against the bundle, a report, nothing served | 3 |
| 9 | `port-stage3-asof-accessor` | 64b78aa | `internal/asof`: an as-of connection through temp views, all 57 store tables classified, the schema test; `docs/AS_OF_ACCESSOR.md` | 3 |
| 10 | `port-cutover-checklist` | 1c3b963 | `docs/port-cutover.md`: main-deploy day and its rollback, layer by layer | cutover |
| 11 | `port-stage2-scores-in-bundle` | 48c2084 | `publish_paths.txt` gains `data/scores` (the store as of the nightly build, PORT-Q-SCORES); the nginx comment on `/data/`; `TestTheScoresStoreShipsFromTheBundle`; the old `/opt/eephus/scores` alias withdrawn; the cutover checkbox | 2 |

### S-1. OWNER: push the eleven branches

The repository is private and behind Cloudflare; git over HTTPS needs the WAF skip rule
of ask 1 (section 4) and a Forgejo personal access token (PAT, scope `write:repository`)
used as the password. On this PC every push needs `-c http.sslBackend=schannel`.

```bash
cd /c/Users/noah/AppData/Local/Temp/claude/c--Users-noah-baseball-projects-BaseballR/b7a7d3e5-214d-4434-a171-b2b4900b0199/scratchpad/eephusgit/prs/eephus
git remote add eephus https://git.eephus.io/eephus/eephus.git
git -c http.sslBackend=schannel fetch eephus main                       # confirm his main is still 9e1423cc (the branches require it)
for b in port-stage0-withheld-data port-stage1-publish-contract port-stage1-buildsite-ownership \
         port-stage1-receive port-stage1-sidecars port-stage1-pages port-stage2-transport \
         port-stage3-shadow-gates port-stage3-asof-accessor port-cutover-checklist \
         port-stage2-scores-in-bundle; do
  git -c http.sslBackend=schannel push eephus "$b:refs/heads/$b" || break
done
```

If his `main` has moved past 9e1423cc, rebase the stack onto it first
(`git rebase --onto eephus/main 9e1423cc port-stage2-scores-in-bundle` carries all eleven,
then re-run the Go gates of PR_PLAN.md on the result). If a push is refused at 100 MB, push
PRs 1 to 5 first and PR 6 alone (its chain compresses to under the cap; the git bundle
`eephus-port-prs.bundle`, 3.7 MB, is the measure). If git over HTTPS is blocked, send him
the git bundle instead: `git fetch <bundle> 'refs/heads/*:refs/heads/*'` in his clone
restores all eleven.

Never push to `main` or `main-deploy`; never self-merge.

**Check:** `git -c http.sslBackend=schannel ls-remote eephus 'refs/heads/port-*'` lists eleven branches at the shas above.

### S-2. OWNER: open eleven PRs in order

One PR per branch, in the table's order, each targeting `main`, each with the body from
`docs/port/prs/PR_<n>_<branch>.md` (what, why, how verified, asks). Open PR 2 only after
PR 1 is merged, and so on, so each diff is one commit.

### S-3. WEBMASTER: review and merge, what to read in each

| PR | What to review | Test line to confirm |
|---|---|---|
| 1 | The six names in `data_exclude.txt` are a leakage control (PORT_SPEC 1.3); `frontend/data` no longer tracks them | `go test ./internal/site/ -run TestExcludedData` |
| 2 | The pin's `paths` (`/opt/eephus/artifacts`, `keep: 2`), the include builder in `publish.sh` (48 rules by hand on the rehearsal bundle), the 33 directories and no `teams/` | `go vet ./...`, `bash -n deploy/publish.sh` |
| 3 | The `owned` skip-list keeps `cmd/buildsite` from writing the 13 shells the bundle owns; `TestRunWithoutAPinWritesEverything` keeps the old behaviour without a pin | `go test ./internal/site/ ./cmd/buildsite/` |
| 4 | The receive contract (PORT_BUNDLE section 4): `sha256sum -c`, the receipt as the one unlisted file, the atomic `current` swap in your `Current` pattern, prune after verify, the units, the two no-store locations | `go test ./internal/artifact/`; `bin/receive -verify-only <bundle>` on the box |
| 5 | A sidecar route reads the bundle file or answers 404; it never falls back to the Build | `go test ./internal/httpserver/` |
| 6 | Size: 190 files, the producer's history since 71ea151; the deep-link fix carried; the other rebuild fixes recorded as not applicable to static pages | `go test -count=1 ./internal/site/` |
| 7 | The forced command's grammar (31 planted refusals), the 8 GB floor, the 48-hour sweep, the sshd drop-in | `go test -count=1 -v ./internal/shipgate/` |
| 8 | The 20 gates and their display rules; a wrong rule is corrected by PR before the first run | `go test -count=1 -v ./internal/shadow/` |
| 9 | The table classification (`tables.go`); a better knowledge column is a one-line change | `go test -count=1 -v ./internal/asof/` |
| 10 | The checklist against how you operate the box (paths, reload, purge) | docs only |

Merge each into `main`; `main` into `main-deploy` only on cutover day (PR 10).

### S-4. WEBMASTER: the box, after PRs 1 to 9 are on `main`

Outside the webroot, nothing visible changes yet:

1. `git -C /opt/eephus/repo pull --ff-only` (a branch other than `main-deploy` for the rehearsal, or a second clone).
2. `go build -o bin/ ./cmd/...` (eight binaries: server, nightly, buildsite, chadwick, fit, receive, shipgate, shadoweq).
3. Create the `ship` user and `/opt/eephus/artifacts/{incoming,bundles}` as PR 4's README section says; install `/etc/eephus/ship_authorized_keys` (root-owned, the producer's address and key) and the sshd drop-in `sshd_eephus_ship.conf` (`sshd -t`, reload) from PR 7, in place of any rrsync line.
4. `systemctl enable --now eephus-receive.path`; install and enable `eephus-ship-sweep.timer`.
5. nginx: the two no-store locations for `/data/bundle_info.json` and `/data/bundle_receipt.json`; `nginx -t`, reload. Cloudflare: add the two paths to Rule 3.
6. Send the owner the ship host, user name, port and host key (step L6).
7. `bin/shipgate -check` with the pin (PR 7's rehearsal line) and `bin/receive -verify-only` on any bundle that lands in `incoming/`.

### S-5. OWNER: the first bundle

```bash
cd /c/Users/noah/baseball-projects/BaseballR/prospect-tracker
powershell -ExecutionPolicy Bypass -File deploy\port-nightly.ps1 -SkipPipeline      # build, verify, ship; no pipeline run
```

Then the acceptance checks, read-only, from the PC:

```bash
python tools/port_live_check.py --heartbeat --origin https://eephus.io
python tools/port_equivalence.py compare-http --bundle ../port_out/bundles/<bundle-id> --origin https://eephus.io --pace 0.5 --explained docs/port/explained.tsv --out ../port_out/gateC_http.json
python tools/port_live_check.py --origin https://eephus.io --stripped --pace 0.5 --out ../port_out/gateB.json
```

Before cutover the box has not published the bundle, so Gate C reads MISSING for most
rows and the heartbeat alarms; the step proves the channel (`RECEIVED`, `current`, the
receipt). After cutover (section 5) the same three commands are the acceptance: Gate C
nothing DIFFERENT, MISSING or BLOCKED; Gate B every one of the 44 withheld names 404;
the heartbeat under 36 hours.

**Check (box, WEBMASTER):** `systemctl status eephus-receive.service` clean, `cat
/opt/eephus/artifacts/current/RECEIVED` names the bundle id, `bin/receive
-require-reference -verify-only` passes once the pin's `reference` is set (step C-1).

---

## 4. The asks for the webmaster (send with the PRs)

1. **Cloudflare WAF custom rule** so git over HTTPS and the OAuth token endpoint pass:
   expression `http.host eq "git.eephus.io" and (ends_with(http.request.uri.path, "/info/refs") or ends_with(http.request.uri.path, "/git-upload-pack") or ends_with(http.request.uri.path, "/git-receive-pack") or http.request.uri.path eq "/login/oauth/access_token")`;
   action Skip the remaining custom rules, Security Level, Browser Integrity Check,
   Managed Rules and User Agent Blocking. Bot Fight Mode on Free cannot be skipped per
   path as far as we know, so it goes off zone-wide (his `deploy/cloudflare.md:104-106`
   says otherwise; please check against Cloudflare's docs). Optionally Security Level
   "Essentially Off" for the git host.
2. **Commit the box's uncommitted edits** as a PR to `main`, then `main-deploy`, so the
   deployed tree equals a commit (the heartbeat's `-dirty`). Send `git -C /opt/eephus/repo
   remote -v` and `df -h` (finding 116 recorded the disk at 93%).
3. **Disk:** two bundle generations with hard links are about 2.6 GB; the ship gate
   refuses a body under 8 GB free (`-min-free-gb`, PR 7) and the Build keeps its own
   6 GB floor. Say if the box cannot hold that.
4. **The restricted SSH user** (`ship`), key-only, forced to `bin/shipgate`, reachable
   from the producer's address without Cloudflare (`ADMIN_SSH_CIDR`, WireGuard or
   Tailscale). Send the host key, user, port and address.
5. **Review our PRs yourself**; we never merge into `main` or `main-deploy`. Consider
   branch protection on both.
6. **Agree the ownership model:** our pipeline (outside your repo) produces the
   manifested bundle; your `publish.sh` publishes it; the buildsite skip-list protects
   bundle-owned pages; a sidecar route reads the bundle; no Go model serves a module
   until its shadow gate passes and its inputs read through `internal/asof`.
7. **Keep the Go models running as shadow challengers**: run `bin/shadoweq` once against
   a shadow server after PR 8 and send the report.
8. **Confirm two things:** ADR-0004 (cited at `deploy/README.md:150`, not in
   `docs/adr/`), and your stance on the inert forums and accounts layer (shipped as is by
   default, or dropped and named as an explained difference).
9. **`/scores/` data** (PORT_STAGE2_PREP OWNER-Q1, answered 2026-10-27): the bundle
   carries `data/scores/` as of its build and PR 11 (`port-stage2-scores-in-bundle`)
   publishes it from the bundle; never add the `/opt/eephus/scores` alias of the old
   design. Merge PR 11 with the others.

---

## 5. Cutover day (PR 10, `docs/port-cutover.md`), in order

The owner and the webmaster run PR 10's checklist, ticking each box with the time in the
cutover PR. The order, with who does what:

| Step | Who | What |
|---|---|---|
| C-0 | both | PRs 1 to 9 merged and tested on the box outside the webroot; the box's edits committed; a `pre-port-<date>` tag and a webroot tarball (`tar czf /opt/eephus/rollback/webroot-$(date +%F).tgz -C /var/www eephus.io`); 10 GB free; the ship channel open and a dry run from the PC |
| C-1 | OWNER then WEBMASTER | The pin's `reference` set to the frozen REF (the `MANIFEST.tsv` sha256 of the bundle built from the final tree, section 6) by a one-line PR; merged |
| C-2 | WEBMASTER | PR `main` into `main-deploy`; on the box `git pull --ff-only`, `go build -o bin/ ./cmd/...`, the units, `systemctl restart eephus-server` (it gains `-bundle-dir`), nginx and Cloudflare no-store for the two heartbeats, `bin/shipgate -check` |
| C-3 | OWNER | Ship the bundle built from the final tree (step S-5's command without the pipeline, or the nightly's own run) |
| C-4 | WEBMASTER | `RECEIVED` present, `current` repointed, `bin/receive -require-reference -verify-only` passes, `publish.sh` has run (his 03:10 Build triggers it too and republishes the same bundle), Cloudflare Purge Everything once |
| C-5 | OWNER | Acceptance: the three commands of step S-5 against production. Gate C: nothing DIFFERENT, MISSING or BLOCKED (LINE_ENDINGS, CDN_INJECTED, TIMESTAMP, FLOAT_REPR, ORDERING and EXPLAINED pass). Gate B: the 44 withheld names 404, every page, asset and payload 200. The heartbeat under 36 hours. A sidecar check (`/partials/efv` bytes equal the bundle's `xfv.json`). Spot pages in both themes: `/prospx/`, `/projections/#player=juan_soto`, `/franchise/#team=MIL`, `/betting/`, `/standings/`. A failure stops and rolls back (section 8) before the next 03:10 Build. |
| C-6 | OWNER | Publish the v2.0 note: copy the block in `docs/port/NEWS_NOTE_V2.md` to `content/articles/eephus-io-v2.md` with `date:` set to today, `python build_site.py`, commit by path, build and ship the next bundle. The note is the one page change between the frozen REF and that bundle; its pages (`articles/eephus-io-v2/index.html`, `articles/index.html`, the homepage lead) are listed in `docs/port/explained.tsv` for Gate C until the REF is re-frozen at the next L4. |
| C-7 | OWNER | Register the PC nightly: `Register-ScheduledTask -TaskName EephusPortNightly -Xml (Get-Content -Raw deploy\port-nightly-task.xml)` (03:10 local, `StartWhenAvailable`, 8-hour limit; PORT_BUNDLE section 7). The betting, umpire and scores jobs keep running on the PC (`deploy/betting-crontab.example` has the UTC schedule; the Windows equivalents are the owner's). |
| C-8 | both | The watch week: seven nights of `link-dest` reuse, prune to two bundles, no rejection; `tools/port_live_check.py --heartbeat` once a day; a weekly `compare-http --every 100`. Keep the tarball, the `pre-port` tag and the GitHub archive for at least 30 days (PORT_SPEC 5.6). |

Deferred box items (`docs/DEPLOY_PENDING.md`): everything the seed carried in the
Strategy A runbook is now a PC matter (the database, the caches, the migrations, the
identity repairs and the fWAR rebase are already true on the producer). What is still
owed on the box: the `error_page 404 /404.html;` line (LIBRARY_8's redirect map); the
`/data/scores/` publish entry (PR 11; the old alias is withdrawn); the scores and
standings backfills run on the PC. Strike an item in `docs/DEPLOY_PENDING.md` with the
date when it is done.

---

## 6. The equivalence snapshot (re-frozen 2026-10-27, task PORT_REFREEZE)

The snapshot is the local build with every served number in it, taken from the final tree
after the regeneration of step L1. Three artifacts carry it:

| Artifact | Value | How it was made |
|---|---|---|
| The final tree | commit `6af3861c` (branch `wt-PORT_REFREEZE`, lane 201, on the integration head `bbfa0104` of `efv-conviction-2026-08-08`): PORT_FINAL's snapshot `151b4f9e`, then the PORT_SCORES_PR11 and LEDGER_PAYROLL_REFRESH merges, then their main-tree steps (the payroll row replay, the FA, ledger, F-SCORE and franchise exporters, `build_site.py`, the hand-page restamp, `gen_audit_docs.py`) committed as the regeneration commit; its integration merge carries it to the main branch | section 2, step L1; the two lanes' integration notes |
| `ref.json` (Gate C's REF) | sha256 `7f83c24b2f65636a5701b44bbcb2f2d21e106cdaa9317ef48c17e501ba68667a`; 19,221 payloads and 214 pages; kept at `port_out/ref.json` beside the repository | `python tools/port_equivalence.py snapshot --root . --out ref.json` |
| The served bundle | id `20261028T034022Z-a488e90dd97a`, 19,479 files, 1,309,489,428 bytes, `MANIFEST.tsv` sha256 `964ae99d6c1385fecb36f6ced4fc9856cdd4c10e6e291d4e2c7a24659835a6cf`; `--verify-served` ok, 19,479 checked, 0 problems; live `data/scores` 80 files (PR 11), none vanished | `python tools/port_bundle.py --served-bundle <out> --keep 1` (slimmed, stripped), then `--verify-served` |

The copy of `ref.json` and the bundle's `MANIFEST.tsv`, `SHA256SUMS`, `BUNDLE.json` and
`READY` sit in `port_out/bundles/20261028T034022Z-a488e90dd97a/` beside the repository
(measured in the lane worktree `C:/Users/noah/baseball-projects/wt/s201/port_out/` at
commit `6af3861c`, 2026-10-27, L4 and L5; the integrator moves them beside the main tree
or re-runs L4 and L5 there after the merge). Against PORT_FINAL's REF of the same day
(ref sha `84d54f50...`, bundle `20261028T022015Z-184c94ecf896`, 19,399 files; superseded,
as is the lane's earlier `6a4be091...` / `20261028T015745Z-0fd5e50fbffd`): 65 payloads
differ, all from the payroll refetch (`fa_class`, `fa_meta`, `trade_cbt`, `ledger_board`,
`franchise_board` and their 60 club shards), 2 differ by timestamp only, 19 by line
endings only, none missing; 9 pages or assets differ (`assets/ledger.js`, `assets/scores.js`,
`ledger/index.html`, `scores/index.html`, and the rebuilt `arbitration`, `models`, `sources`,
`standings` and `team` pages); the bundle gains the 80-file scores store. The pin's
`reference` takes this bundle's MANIFEST sha (step C-1). A later rebuild re-freezes the
same way.

Every served number means: every leaf of every payload `port_equivalence.payload_files`
names (the depth-one `data/*.json` minus `deploy/data_exclude.txt`, plus the nine shard
directories), and the hash of every page and asset of `deploy/publish_paths.txt`. The
`compare` and `compare-http` ladder sorts each file into IDENTICAL, LINE_ENDINGS,
CDN_INJECTED, TIMESTAMP, FLOAT_REPR, ORDERING, EXPLAINED (pass) or DIFFERENT, MISSING,
BLOCKED (fail). The explained list, `docs/port/explained.tsv` (`glob<TAB>reason`, created
at step C-6), may name only: the v2.0 note's pages and the homepage between cutover and
the next freeze; the forums and accounts layer if the webmaster drops it; the headshot
URLs if the owner moves a surface to his proxy. Nothing else is explained; a difference
not on the list stops the port until its cause is written down.

The cache manifest of the first runbook (P-4: 363,455 files, 29.71 GB, `tools/port_bundle.py
--plan`) is superseded by R1: the cache stays on the PC and is never shipped. The manifest
that crosses to the box is `MANIFEST.tsv`.

---

## 7. Stage 2 and Stage 3: the post-cutover program

Both stages change how a number is served, never which number. Each step has a gate that
reads the bundle as the reference.

**Stage 2, per route (PR 5 and PR 7 are its foundation).**
- The JSON sidecar routes already serve the bundle's file verbatim (PR 5). The check per
  route: the bytes at `/partials/<route>` equal the bundle's `site/data/<file>`.
- A Go artifact-import Source (a later PR) loads the bundle into `nightly.db` so a fragment
  route can be re-templated from our numbers.
- **Gate F, per HTML fragment route (20 routes):** a page returns to htmx only when the
  rendered page's DOM text and every number on it equal the static page's. The static page
  stays until then. A route that cannot reach equality stays static; that is not a
  failure.
- Review latency is the risk: 20 routes, one reviewer. Static pages beside unused partials
  is an acceptable steady state.

**Stage 3, per model (PR 8 and PR 9 are its entry conditions).**
- `deploy/shadow_gates.tsv` registers 20 per-field gates over 10 modules (consensus, xFV,
  valuation, projections, the plus boards and the others his Build already produces).
  `bin/shadoweq -bundle <current/site> -challenger http://127.0.0.1:8081 -out <report>`
  measures his Build against the bundle and serves nothing. Floor 1: every registered
  field prints the same digits on every row.
- **Gate G, per model:** a Go re-implementation may replace the Python producer for one
  module only after its shadow gate passes on a pre-registered run (EFV_GATE_STANDARD
  floors) and its inputs read through `internal/asof` (PR 9), the schema-level as-of
  accessor, so no request-time query can read past its knowledge date. A changed display
  rule after a run has read the table is a new registration.
- "Never port and rewrite at once" (PORT_SPEC 5.1) holds throughout: the bundle is the
  reference on both sides of every gate.

---

## 8. Rollback, smallest layer first

1. **A bad bundle:** repoint `current` to the previous bundle (`--keep 2` leaves it on
   disk), run `publish.sh`, purge Cloudflare. The PC's next ship replaces it.
2. **The ship channel:** disable `eephus-receive.path` (no bundle is accepted); the last
   good bundle keeps serving.
3. **Back to his Build's site:** drop `current` and the server's `-bundle-dir`; his
   `publish.sh` publishes the Build's pages again (the pin's `owned` list is honoured only
   while `current` exists).
4. **The whole port:** revert the Stage PRs on `main-deploy` to the `pre-port-<date>` tag
   by PR, pull, build, publish, purge; the webroot tarball is the last resort. The owner
   pauses the PC's scheduled task so no bundle lands on a reverted box.

Nothing on git.eephus.io needs rewriting: every change arrived by PR and reverts by PR.
GitHub and the PC are untouched by any of it.

---

## 9. Risks (PORT_RECON section 8, carried forward)

1. **Producer on the owner's PC.** The PC blue-screens under load and a missed night leaves
   the site stale. The 36-hour alarm (`port_live_check.py --heartbeat`) reads the bundle
   receive time, never his Go Build time. `StartWhenAvailable` runs a missed night on
   restart. Revisit a second box after the watch week.
2. **Two writers.** His 03:10 Build still runs and still triggers `publish.sh`; with the
   pin and `current` in place it republishes the same bundle (idempotent). Without PR 3's
   skip-list it would rewrite the 13 shell pages to July markup every night.
3. **Data subdirectories.** About 22 local subdirectories 404 under his old filter; PR 2
   ships the nine the nightly rsync ships. `pages_test.go` blocks publish on any manifest
   mismatch, which is the right failure.
4. **Live jobs.** Betting odds every 15 minutes, the umpire job and the scores job are
   Python and run on the PC; `data/scores/` reaches the box once a night inside the
   bundle (PR 11), so the published scores are up to a day old and the page says so.
5. **Cloudflare caching.** `/data/*.json` has a 4-hour edge TTL and `/assets/` a 1-year
   one; a missed purge or an unchanged `?v=` stamp serves mixed versions. Purge after every
   publish; the two bundle heartbeats are no-store.
6. **Disk.** 93% full on 2026-10-22; two bundles (about 2.6 GB with hard links) plus his
   6.5 GB baseline must stay above the floors (8 GB ship gate, 6 GB Build).
7. **Review latency.** One reviewer for ten PRs, then 20 Stage 2 routes.
8. **Different numbers.** Any route that serves from his tables before its Gate G serves a
   different model (LV-10: 25 of 80 fields equal). PR 5 closes that for the sidecars; the
   fragment routes stay static until Gate F.
9. **Leakage.** His store has no as-of column; Stages 2 and 3 add request-time queries.
   The accessor (PR 9) is an entry condition, and his repo has to keep that promise.
10. **Visible changes.** The forums and accounts layer and the headshot proxy must be
    accepted as named differences, or the identical check cannot pass; by default neither
    is a difference (the layer ships inert, the URLs stay `img.mlbstatic.com`).
11. **The push.** Cloudflare's 100 MB request cap and the Forgejo 768M memory cap apply to
    every push; the ten branches total 3.7 MB as a git bundle, and PR 6 alone is the only
    one that could approach the cap.

---

## 10. What not to do, and what to keep

- Never push to `main` or `main-deploy`, never self-merge into `eephus/eephus`, never add
  a `.py` file to it (his AGENTS.md), never force-push anything anywhere, never delete
  GitHub or git.eephus.io.
- Never run the Python pipeline on the box, and never copy the cache, the database or the
  licensed imports (`data/imports/`) to it.
- Never hand-edit a bundle or a `data/*.json` artifact to make a gate pass; find the cause.
- Never run pytest while any exporter or `run_monthly.py` writes (the conftest guard
  reverts the pipeline's writes), and never ship while the suite is red.
- Never refetch or "refresh" frozen `*_eval.json` sidecars (PORT_SPEC section 3), and
  never cold-rebuild the database (`EEPHUS_ALLOW_COLD_REBUILD=1`): the 2021+ snapshot
  history is not re-scrapable.
- Keep on the PC, backed up: `prospects.db` (the 02:55 `.backup` line of
  `deploy/betting-crontab.example`, run on the PC), `.cache/efv_progress/`,
  `.cache/provisional_track/`, `.cache/model_updates/`, `.cache/trade_partner_screen/record/`,
  `.cache/bracket_sim/`, `.cache/betting/`, `.cache/odds/`, `.cache/umpire_captures/`,
  `.cache/leaderboard_vintages/`, `.cache/port_ship/` and `data/imports/`.

---

## 11. Re-running the measurements

```bash
python tools/port_live_check.py --origin https://eephus.io --pace 0.5 --out live_check.json   # LV-4 to LV-9, Gate B
python tools/port_live_check.py --heartbeat --origin https://eephus.io                          # the 36-hour alarm
python tools/port_equivalence.py snapshot --root . --out ref.json                               # a new REF (L4)
python tools/port_bundle.py --plan-served                                                       # bundle counts (L5)
python tools/port_equivalence.py compare-http --bundle <bundle-dir> --origin https://eephus.io --pace 0.5 --every 100   # Gate C, a 1% slice
```

LV-10's entity comparison read `/partials/efv`, `/partials/mlb/trade_values`,
`/partials/mlb/projections` and `/partials/player-links` on the live site against
`data/xfv.json`, `data/trade_values.json`, `data/mlb_projections.json` and
`data/player_links.json`. After PR 5 those routes serve the bundle's files, so the
comparison collapses into Gate C.

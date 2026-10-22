# PORT RUNBOOK: the local eephus.io build to git.eephus.io and the live box

Written 2026-10-22 by task PORT_PREP for the owner, to be run with Claude Code.
The design and the gates are in `docs/port/PORT_SPEC.md` (2026-09-18); this file
is the order of operations, with the commands. Every number below was measured
on 2026-10-22 unless it says otherwise.

Two machines take part:

- **LOCAL**: the owner's Windows PC, `C:/Users/noah/baseball-projects/BaseballR`,
  branch `efv-conviction-2026-08-08`. It holds the reference build, the
  database and the cache.
- **TARGET**: the box that serves https://eephus.io and can reach
  https://git.eephus.io. Claude Code runs there as the deploy user.

How to use this file with Claude Code: open Claude Code in the named
directory on the named machine, paste the step's **Say** line, and let it run
the step's commands. Each step ends with a **Check**; do not start the next
step until the check passes. Nothing here force-pushes, and nothing deletes
the old repository or the current live webroot.

---

## 0. Where things stand (measured 2026-10-22)

**The live site is not this codebase.** It is the beta branch of 2026-08-01
(the rollback commit `03c1428e` on github.com/aiyer9175/eephus.io) plus the
webmaster's own changes, built nightly on the box and served partly by a
server process that answers `/partials/...` requests. The local branch is
3,346 commits deep; against `origin/beta` its tree adds 2,665 files, deletes
665, changes 516 and renames 11 (4,277 tracked files against 2,277).

**git.eephus.io could not be read.** It is a Forgejo 16.0.3 server (its API
reports `16.0.3+gitea-1.22.0`). Anonymous requests see no repositories, the
`eephus` organisation answers `HasOrgOrUserVisible` (it exists and is hidden),
`/eephus/eephus` answers 404 and `git-upload-pack` answers 401. Its branch list
and file tree are therefore not in this file; step T1 reads them with the
owner's credentials.

### 0.1 Every live-versus-local difference, its cause, and the step that resolves it

| # | Difference (live https://eephus.io against the local build) | Cause | Resolved by |
|---|---|---|---|
| LV-1 | Live heartbeat `data/build_info.json` read `{"generated_at":"2026-10-21T07:29:38Z","git_sha":"9c7c04e465e7-dirty","mode":"nightly"}` at 07:20 UTC on 2026-10-22, and `2026-10-22T07:24:40Z` with the same sha at 08:30 UTC (the box rebuilds nightly around 07:25 UTC). That sha is in no local branch and on no GitHub ref; `mode` is `nightly`, while this repo's `deploy/nightly-build.sh` writes `daily`, `full` or `publish-only`. | The box builds from its own checkout (a commit made on the box or on git.eephus.io, with uncommitted edits) with its own build script. | L6 seeds the remote, T2 checks out this repo, T7 writes the heartbeat with this repo's script. |
| LV-2 | Live code is beta-era: `assets/eephus-nav.js`, `assets/site.css`, `assets/fa.js` and `assets/parks.css` are byte-identical to `origin/beta` 03c1428e; `projections.js`, `glossary.js`, `trademachine.js`, `mlbstats.js`, `pal.js` and `parks.js` differ from beta and from anything in local history. | The webmaster rewrote those six modules to read `/partials/...` endpoints. | T7/T8 publish this repo's assets. |
| LV-3 | Live serves at least 40 distinct `/partials/...` endpoints (for example `/partials/efv` JSON 3.5 MB, `/partials/mlb/projections`, `/partials/mlb/trade_values`, `/partials/player-links`, `/partials/farm/board` HTML), generated from 2026-10-21 data. The local build has no such endpoint; every page reads static `/data/*.json`. | The webmaster's server-side layer (PORT_SPEC section 7, W-1: the live-query design). | Owner decision P-2 below; the default publishes static files and leaves the partials server unrouted. |
| LV-4 | Live sitemap lists 17 URLs, local 33. Of the 40 local pages at depth two or less, 21 return 200 live and 19 return 404 (one is `/404.html` itself, which answers 404 by design). The 18 missing routes: `/arbitration/ /awards/ /betting/ /diamond/ /forums/ /franchise/ /franchises/ /history/ /hof/ /ledger/ /library/ /management/ /models/ /models/updates/ /parks/ /scores/ /scouting/ /standings/`. | Built after beta, never delivered to the box (DEPLOY-3 deferral). | T7/T8. |
| LV-5 | Live nav has 14 links (articles, collegesavant, fa, fantasy, glossary, mlbstats, news, pal, projections, prospx, report, sources, team, trademachine); local `build_site.NAV_ITEMS` has 22 entries including franchise, scores, arbitration, ledger, management, awards, betting, diamond, forums and scouting. | Same as LV-4. | T7/T8. |
| LV-6 | Of the 570 payloads the local build publishes at `data/` depth one, 241 answer 200 live and 329 answer 404, including `timeseries.json`, `debuts.json`, `trade_values.json`, `mlb_projections.json`, `player_links.json`, the eight `scout_reports_N.json` chunks and every `awards`, `betting`, `hof`, `management`, `franchise` and `ledger` payload. | Newer exporters, plus the partials layer replacing some static files. | T3 (seed), T7 (publish). |
| LV-7 | **Six withheld files are served live**: `comps.json`, `fielding_census_ids.json`, `identity_collisions.json`, `milb_pitch_rates.json`, `positional_fit.json`, `positions_played_seasons.json` (all on `deploy/data_exclude.txt`, which PORT_SPEC 1.3 calls a leakage control; `identity_collisions.json` names players whose records fuse two people). | The rsync uses `--delete` without `--delete-excluded`, so a file that shipped before it was excluded stays in the webroot forever; or the box's own exclude list is older. | T7 publishes into a **new, empty** webroot, and T7's check asserts all 42 withheld names answer 404. Interim, optional: ask the webmaster to delete those six files from the current webroot today. |
| LV-8 | Of the 85 files under local `assets/`, 26 answer 200 live (only `parks.css` byte-identical) and 59 answer 404 (for example `eephus-ui.js`, `betting.js`, `standings.js`, `xm-surfaces.js`). | Same as LV-2 and LV-4. | T7/T8. |
| LV-8b | `robots.txt` live still disallows `/teams/`; local drops the line (the four retired folders now forward through `/404.html`'s redirect map). | Beta-era file. | T7. |
| LV-9 | Live `data/xfv.json` says `generated_at 2026-07-17` and 9,040 players; the live pages read `/partials/efv` instead. | A stale tracked file left in the webroot. | T7 (new webroot). |
| LV-10 | **Served numbers differ for every sampled entity.** Ten entities (seed 20261022: five prospects, five MLB veterans), 80 field comparisons, 25 equal. Equal: every MLBAM id (9 of 9 present on both), most org codes. Different: every eFV grade, eFV WAR, trade value and projection WAR. Examples: Jacob Wilson eFV 60.5 live / 55.1 local, trade value $15.7M / $34.4M; Jake Fraley trade value $23.4M / $0.0M; Daniel Jackson eFV 48.5 / 41.9. Coverage also differs: trade values 5,231 players live / 6,316 local, eFV 5,231 / 9,515, projection veterans 1,150 / 1,400, player links 5,231 / 6,415. Team codes `OAK`, `WAS` live / `ATH`, `WSN` local in projections. Both sides are stamped 2026-10-21 data. | Same data day, different model code: the live box runs the 2026-08-01 models (before the eWAR and fWAR label epochs, eFV v3 to v5, the trade-value and projection changes since). | Expected and intended: at cutover **every model number on the live site moves to the local value**. T6 proves the target reproduces the local numbers; the move itself is the point of the port. Tell readers (P-6). |
| LV-11 | git.eephus.io inventory unreadable anonymously (see above). | Private Forgejo instance. | T1 lists its branches and diffs its tree against this repo with credentials. |
| LV-12 | GitHub (`origin`): `efv-conviction-2026-08-08` there is `8e2361f4` (2026-10-07); local is 928 commits ahead. `main` there is `63541afe` (2026-09-06), 1,861 behind local. `beta` there is `03c1428e`. | Nothing pushed since 2026-10-07 (owner rule: never push from lanes). | L6 (the new remote); GitHub stays the read-only archive. |

Evidence for every row (raw curl captures, the crawl JSON and the entity
comparison) was kept with the task's report; the commands that regenerate it are
in section 6.

### 0.2 What the clean-clone rehearsal showed (2026-10-22, on LOCAL)

The target steps were rehearsed on LOCAL: a clean clone of the branch into an
empty directory, seeded only from a bundle built by `tools/port_bundle.py`
(no served data, P-5 (b)), R removed from `PATH`.

- **Bundle**: 358,891 cache files, 28.89 GB, plus 498 import files (45.5 MB)
  and a 1,958,387,712-byte seed database (61 tables, `integrity_check ok`).
  Building it took 29 min 52 s; extracting it 8 min 47 s; `--verify` checked
  359,389 rows in 30 min with 0 missing and 0 mismatched. The spec's 2026-09-18
  figure (115,412 files, 3.77 GB) is out of date: `win_prob_hist` alone is
  15.48 GB, then `pbp_runners` 2.69 GB, `dvm_difficulty` 1.95 GB,
  `win_prob_post` 0.88 GB, `ewar_innovate_ledger` 0.75 GB. After the
  rehearsal the tool also carries every small SAFE_CACHES directory (about
  0.8 GB, see the refusals below) and the 16 gitignored
  `collegesavant/logos/*.png` the CollegeSavant pages load: today's `--plan`
  reads 363,455 cache files, 29.71 GB, and 514 import files, 45.9 MB.
- **Before any rebuild**: of 19,346 published payloads, the 830 tracked ones
  were IDENTICAL to the local build and the 18,516 gitignored ones were missing,
  as expected.
- **`run_monthly.py --rebuild-only`** (31 min), `tools/export_trade_values.py`
  and `build_site.py` all exited 0. Against the local build: 13,141 IDENTICAL
  (every `pitch_plots/` and `player_detail/` file among them), 5 TIMESTAMP,
  3,054 DIFFERENT, 3,146 MISSING.
  - MISSING, because `--rebuild-only` does not write them (the daily or
    monthly run does): `data/mlb_events/` (1,726), `data/mlbstats_player/`
    (1,409), and `betting_learning`, `betting_record`, `betting_settlement`,
    `betting_shadow`, `bracket_sim`, `bracket_sim_record`,
    `leaderboard_gamelogs`, `photo_ctx`, `prospx_leaderboard`,
    `source_backtest`, `trade_partner_screen_chain` (`.json`).
  - DIFFERENT, mostly because **the local served artifacts are older than the
    code**: the local `debuts_full/*.json` were written 2026-10-19 with
    `career_war.source ewar_v2`, and today's code writes `ewar_v3` with
    `seasons_fwar`; date-relative fields such as `stale_days` move by the days
    between builds. That is why step L1 rebuilds locally before L4 snapshots:
    the reference must be the output of the commit being ported. Affected:
    `debuts_full/` (2,762), `mlb_player_detail/` (222), `ledger_clubs/` (30)
    and 40 top-level files (`timeseries`, `debuts`, `xfv`, `trade_values`,
    `mlb_projections`, `player_links` and others).
  - Three refusals, each the code's guard working as designed:
    `draft_export` ran before `timeseries.json` and `debuts.json` existed, so
    picks that resolve only through them published `current_fv: null` (run
    `--rebuild-only` twice on a box without served data, or carry it, P-5 (a));
    `franchise_export` refused because the tracked `data/fscore.json` is not
    today's (the committed franchise files stand until a nightly writes
    F-SCORE); `prospect_statline` raised "the served fit does not reproduce the
    look's fit: hit:xwoba" because its fit reads
    `.cache/savant_mlb/expected_<side>_<season>.csv`, which the SAFE_CACHES rule
    left behind. With those 47 files copied in, the fit reproduced and the
    export wrote. The test gate found a second case: `efv_surrogate` pins the
    2005 to 2013 `.cache/milb_stats/` season files, which `milb_history`
    reads cache-only, and 11 tests raised "hitting sport 1 2013 drifted from
    its pin". `tools/port_bundle.py` now carries every SAFE_CACHES directory
    except the four large feed caches (`LEAVE_BEHIND`: win_prob,
    statcast_metrics, zone_metrics, game_feeds).
  - A served-file gap: `collegesavant/logos/` (16 PNGs) is ignored by the
    root `.gitignore` (`logos/`, `*.png`) yet published with the
    `collegesavant/` directory, so a clean clone serves no college logos
    (`test_mlb_player_pages.py::test_collegesavant_logos_present`). The
    bundle now carries every gitignored file inside a published page
    directory.
- **R**: nothing in the rebuild or the test gate needed it (`Rscript` absent
  from `PATH` for the whole rehearsal).
- **Deploy test gate** (`EEPHUS_DEPLOY_RUN=1 python -m pytest -q`) on the
  rebuilt clone: **177 failed, 17,008 passed, 265 skipped, 1 xfailed,
  5 errors in 2 h 49 min**. Sorting the 182 failing ids:
  - 91 fail on the local build too (rerun on the worktree): they are red at
    HEAD, not port defects. One (`test_dependency_lock`, a false positive on
    `import __main__`) is fixed in f595a0b5; the other 90 are listed in
    `docs/port/BASELINE_PYTEST.txt` (owner decision P-8).
  - 46 of the other 91 passed once the small SAFE directories and the
    daily-only artifacts were present (both now in the bundle).
  - The last 45 (club-link renders, franchise and ledger reconciliations,
    trade audit, value ruler, the logos) all passed (44 passed, 1 xfailed)
    once the clone was reset to HEAD plus the carried served data, which is
    the default path P-5 (a). On that path the clean clone's gate is exactly
    the local gate.
  - Gate C on that path: `tools/port_equivalence.py compare` read all
    19,346 payloads IDENTICAL to the local build, and the 214 pages and assets
    equal (207 byte-identical, 7 differing only in CRLF against LF, which is
    why the tool now reads CRLF as LF and reports `LINE_ENDINGS`).

---

## 1. Owner decisions (defaults in bold; Claude takes the default unless you say otherwise)

| ID | Question | Options (default first) | What each changes |
|---|---|---|---|
| P-1 | History on the new remote (open since X04-07 / M25-4) | **(a) full history** of `efv-conviction-2026-08-08`, 855 MiB pack; (b) one squashed snapshot commit | (a) keeps `tools/backfill_vintages.py`'s git-date evidence for 10 of the leaderboard vintages (PORT_SPEC 4.3, 6.2) and every `git log` receipt cited in gate docs; (b) is small and clean, and those receipts then live only in the GitHub archive, which must stay readable forever. |
| P-2 | The live `/partials/...` server layer | **(a) static publish**: nginx serves the built tree, partials left unrouted; (b) keep the partials server beside the static site | (a) is what this repo builds and tests, and it keeps refusal, vintage stamps and the fit half (PORT_SPEC D2); (b) needs the webmaster to port 40+ endpoints onto today's exporters, and nothing here tests them. |
| P-3 | Python on the target | **(a) 3.13.9 with `constraints-local.txt`** (the versions that produced the reference numbers); (b) 3.12 resolving the floors in `requirements.txt` (the old box's way, M25-2) | (a) makes T6's equivalence meaningful; (b) can move numbers through library versions (PORT_SPEC C.0.3) and T6 then reads differences that are not port bugs. |
| P-4 | Cache carry size | **(a) the tool's default: the PORT_SPEC rule plus the small SAFE directories, 363,455 files, 29.71 GB**; (b) `--exclude-dir win_prob_hist --exclude-dir win_prob_post` (about 13.3 GB); (c) also ship the four feed caches the tool leaves behind (54.7 GB more, about 84 GB in all: win_prob 19.5 GB, statcast_metrics 15.2 GB, game_feeds 14.6 GB, zone_metrics 5.4 GB) | (c) makes the first full nightly refetch nothing, so its numbers can differ from local only through new data; (b) saves 16.4 GB of transfer; both directories are StatsAPI feeds that refetch at a rate-limited pace (days), and `tools/build_runner_moves.py` reads win_prob_hist for the 2011 to 2017 and 2020 seasons. |
| P-5 | Gitignored served artifacts | **(a) carry them** (`--served-data`, 18,614 files, 1.12 GB) so the first publish equals the reference; (b) rebuild them on the target | (a) gave a clean clone the local gate exactly in the rehearsal; (b) left 3,146 payloads missing, 3,054 different and 45 gate failures beyond the local ones (section 0.2) until a full nightly runs. |
| P-6 | Announcing the number change | **(a) a dated note on /news/ the day of cutover**: "the live site now runs the current models"; (b) no note | Every eFV, trade value and projection on the live site moves at cutover (LV-10). |
| P-7 | The version label (FP1-4, answered 2026-09-23) | **(a) apply it in L1**: "v2.0", module beta chips dropped, Diamond keeps its preview chip; (b) after cutover | It is a page change, so doing it before L4 keeps the reference and the target identical. |
| P-8 | The 90 tests red at HEAD (`docs/port/BASELINE_PYTEST.txt`) | **(a) clear them in a writer pass before L1**, then re-record L3; (b) carry them as a written known-red list and publish T7 by hand (the rsync block of `deploy/nightly-build.sh`) | `nightly-build.sh` runs `set -e` and the pytest gate before the rsync, so with any red test neither the publish-only run in T7 nor any nightly after cutover publishes. (a) keeps the gate meaning what it says; (b) ships sooner and leaves the box's nightly unable to publish until they are cleared. |

---

## 2. LOCAL steps (Windows, Claude Code in `C:/Users/noah/baseball-projects/BaseballR`)

### L1. Freeze the tree

**Say:** "Run PORT_RUNBOOK step L1: confirm nothing is running, then show me what is uncommitted under prospect-tracker."

```bash
tasklist | findstr /i python          # no run_monthly.py, no pytest, no exporter
cd prospect-tracker
git status --short | head -50
```

The port carries **git plus the bundle**, so anything modified but uncommitted
does not reach the target. On 2026-10-22 the main tree held the owner's
2026-09-23 pipeline churn (about 76 `data/*.json` files and several generated
pages). Either commit it as one snapshot commit ("Port snapshot: tracked
artifacts as built on <date>") or restore it with `git checkout -- <paths>`;
then rebuild once so every served artifact is the output of the commit being
ported (the rehearsal found local `debuts_full/` files written by older code,
section 0.2). Use the nightly's own path, outside the 06:00 to 11:00 UTC fetch
window and on no registered look day:

```bash
python run_monthly.py --daily          # writes the daily-only artifacts and F-SCORE too
python tools/export_trade_values.py
python build_site.py
```

`python run_monthly.py --rebuild-only` is the offline alternative (31 minutes
in the rehearsal), but it leaves the daily-only artifacts as they are and the
franchise export refuses on a stale `fscore.json`.

Apply P-7 here if you chose (a). Then commit by path.

**Check:** `git status --short` prints nothing under `prospect-tracker/` except
gitignored state.

### L2. Record the archive tips

**Say:** "Run PORT_RUNBOOK step L2."

```bash
cd /c/Users/noah/baseball-projects/BaseballR
git for-each-ref --format="%(objectname) %(refname)" refs/heads refs/remotes > prospect-tracker/docs/port/ARCHIVE_TIPS.txt
git ls-remote https://github.com/aiyer9175/eephus.io >> prospect-tracker/docs/port/ARCHIVE_TIPS.txt
git add prospect-tracker/docs/port/ARCHIVE_TIPS.txt
git commit -m "Port: record every branch tip before the move"
```

**Check:** the file lists `refs/remotes/origin/beta 03c1428e...`.

### L3. Record the test baseline (PORT_SPEC P0.1, Gate A)

**Say:** "Run PORT_RUNBOOK step L3 and write both pytest summaries to docs/port/BASELINE_PYTEST.txt."

```bash
cd /c/Users/noah/baseball-projects/BaseballR/prospect-tracker
mkdir -p ../port_out
python -m pytest -q -p no:cacheprovider > ../port_out/pytest_dev.txt 2>&1
EEPHUS_DEPLOY_RUN=1 python -m pytest -q -p no:cacheprovider > ../port_out/pytest_deploy.txt 2>&1
python --version; pip freeze > ../port_out/pip_freeze.txt
python tools/freeze_constraints.py --check
```

Add the two summary lines, the Python version, the chromium status and the
list of failing test ids to `docs/port/BASELINE_PYTEST.txt` (it already holds
the 2026-10-22 rehearsal and the 90 ids red at HEAD) and commit it. Each run
takes about 3 hours on this PC. A failure on the list is a known red, not a
port defect; the nightly gate blocks publishing while any test fails, so take
P-8 before T7.

**Check:** the file exists, and `freeze_constraints.py --check` prints
"constraints-local.txt matches this interpreter".

### L4. Take the reference snapshot (Gate C's REF)

**Say:** "Run PORT_RUNBOOK step L4."

```bash
cd /c/Users/noah/baseball-projects/BaseballR/prospect-tracker
python tools/port_equivalence.py snapshot --root . --out ../port_out/ref.json
python tools/port_equivalence.py selftest data/trade_values.json
```

The snapshot records 19,346 payloads and 214 pages (2026-10-22 count) and takes
about 7 minutes. The selftest is the positive control: it must print `"ok": true`
with one leaf reported.

**Check:** both commands exit 0. Note the date: run T6 on the same calendar date
or expect the date-seeded sample in `build_site.py` (PORT_SPEC C.0.5) to differ.

### L5. Build the state bundle

**Say:** "Run PORT_RUNBOOK step L5 with the P-4 and P-5 answers."

```bash
python tools/port_bundle.py --plan                                  # counts only
python tools/port_bundle.py --out ../port_out/bundle --served-data  # P-4 (b): add --exclude-dir win_prob_hist --exclude-dir win_prob_post
# P-4 (c) only: also ship the refetchable caches (no manifest; they are refetchable by definition)
# tar cf ../port_out/bundle/cache-safe.tar $(python -c "import sys; sys.path.insert(0,'tools'); import port_bundle as p; print(' '.join('.cache/'+d for d in p.LEAVE_BEHIND))")
```

The bundle holds `prospects.seed.db` (SQLite `VACUUM INTO`, integrity-checked),
`cache-carry.tar` (`.cache/` minus the four feed caches in `LEAVE_BEHIND`), `data-imports.tar`
(the FanGraphs and Baseball America drops, **licensed, never published**, and
the gitignored `collegesavant/logos/`),
`served-data.tar`, `MANIFEST.tsv` (one sha256 per file), `SHA256SUMS.txt` and
`BUNDLE_INFO.json`. The rehearsal took 30 minutes and about 31 GB of disk
without `--served-data` (section 0.2); `--served-data` adds about 1.1 GB.
Copy `../port_out/ref.json` into the bundle directory too.

**Check:** `BUNDLE_INFO.json` shows `"integrity_check": "ok"` and the file
counts match `--plan`.

### L6. Seed the new remote (owner's choice P-1)

**Say:** "Run PORT_RUNBOOK step L6 option A" (or B).

Never push over an existing branch on git.eephus.io: the webmaster's current
work lives there. Push to a new branch and let the webmaster make it the default.

Option A, full history:

```bash
git remote add eephus https://git.eephus.io/eephus/eephus.git
git push eephus efv-conviction-2026-08-08:refs/heads/port/2026-10
```

Option B, one squashed snapshot commit (the tree is identical, the history is one commit):

```bash
git remote add eephus https://git.eephus.io/eephus/eephus.git
git checkout --orphan port-snapshot
git commit -m "eephus.io snapshot of efv-conviction-2026-08-08 at $(git rev-parse --short efv-conviction-2026-08-08)"
git push eephus port-snapshot:refs/heads/port/2026-10
git checkout efv-conviction-2026-08-08
```

Keep `origin` (GitHub) as the read-only archive: push nothing more there and
never delete it (PORT_SPEC 4.3, 6.4).

**Check:** `git ls-remote eephus` lists `refs/heads/port/2026-10` at the sha you pushed.

### L7. Move the bundle

```bash
cd ../port_out/bundle
scp -r . deploy@TARGET:/opt/eephus/port_in/
```

**Check:** on the target, `cd /opt/eephus/port_in && sha256sum -c SHA256SUMS.txt` prints OK for every line.

---

## 3. TARGET steps (Linux box, Claude Code as the deploy user)

### T0. Record the live state for rollback

**Say:** "Run PORT_RUNBOOK step T0. Change nothing; record."

The paths below are the layout `deploy/WEBMASTER.md` documents. The live box
runs the webmaster's own build (LV-1), so if a path is missing, have Claude
read the real ones from `sudo nginx -T` and `crontab -l` first and substitute.

```bash
mkdir -p /opt/eephus/rollback && cd /opt/eephus/rollback
sudo nginx -T > nginx_full.conf
crontab -l > crontab.txt
systemctl list-units --type=service --no-pager > services.txt
git -C /opt/eephus/repo log -1 --format=%H > live_head.txt; git -C /opt/eephus/repo status --short > live_dirty.txt
git -C /opt/eephus/repo diff > live_dirty.patch
tar czf webroot-$(date +%F).tgz -C /var/www eephus.io
```

**Check:** `live_head.txt` starts `9c7c04e465e7` (the sha the live heartbeat names) and the webroot tarball exists.

### T1. Inventory git.eephus.io against this repo (LV-11)

**Say:** "Run PORT_RUNBOOK step T1 and list every file that exists only on the webmaster's branch."

```bash
cd /opt/eephus/repo
git ls-remote https://git.eephus.io/eephus/eephus.git   # every branch on git.eephus.io
git fetch https://git.eephus.io/eephus/eephus.git refs/heads/port/2026-10:refs/remotes/port/2026-10
git diff --name-status HEAD refs/remotes/port/2026-10 | cut -f1 | sort | uniq -c
git diff --name-status HEAD refs/remotes/port/2026-10 | awk '$1=="D"' > /opt/eephus/rollback/only_on_live.txt
```

Histories are disjoint, so this is a tree diff, not a merge. Read
`only_on_live.txt` with the webmaster: the partials server and any box-side fix
he wants kept are re-applied by hand after cutover (PORT_SPEC 6.3), never merged.

**Check:** you have a written list of files only on the live branch and a keep or drop note for each.

### T2. Check out this repo beside the live one, with the pinned environment

**Say:** "Run PORT_RUNBOOK step T2."

```bash
git clone --branch port/2026-10 https://git.eephus.io/eephus/eephus.git /opt/eephus/port
cd /opt/eephus/port/prospect-tracker
python3.13 -m venv /opt/eephus/venv-port            # P-3 (b): python3.12
/opt/eephus/venv-port/bin/pip install -r requirements.txt -c constraints-local.txt
/opt/eephus/venv-port/bin/pip install -r requirements-dev.txt -c constraints-local.txt
/opt/eephus/venv-port/bin/python -m playwright install --with-deps chromium
```

The live checkout `/opt/eephus/repo` and its venv stay untouched until T8, so
rollback is a symlink and an nginx root away. R is not needed: no pipeline or
served path calls it (`tools/rbridge.py` is offline-only, and its tests skip
when `Rscript` is absent).

**Check:** `/opt/eephus/venv-port/bin/python tools/freeze_constraints.py --check` prints "matches" (it only matches exactly on the same platform; on Linux compare the versions by eye) and chromium launches.

### T3. Install the state bundle

**Say:** "Run PORT_RUNBOOK step T3."

```bash
cd /opt/eephus/port/prospect-tracker
tar xf /opt/eephus/port_in/cache-carry.tar
tar xf /opt/eephus/port_in/data-imports.tar
tar xf /opt/eephus/port_in/served-data.tar          # P-5 (a)
[ -f /opt/eephus/port_in/cache-safe.tar ] && tar xf /opt/eephus/port_in/cache-safe.tar   # P-4 (c)
cp /opt/eephus/port_in/prospects.seed.db prospects.db
/opt/eephus/venv-port/bin/python tools/port_bundle.py --verify /opt/eephus/port_in/MANIFEST.tsv --root .
sqlite3 prospects.db "PRAGMA integrity_check"
```

**Check:** `--verify` prints `"ok": true` with `missing 0` and `mismatched 0`, and SQLite prints `ok`.

### T4. Secrets

Put the keys in `/etc/eephus.env` (root-owned, `chmod 600`, outside every
checkout; PORT_SPEC P2.6): `EEPHUS_ODDS_API_KEY=...` and any other key the old
box's file holds (`sudo cat /etc/eephus.env` on the old layout). Never in a
tracked file: `assets/eephus-config.js` stays the committed blank stub, and a
Supabase `service_role` key never goes anywhere the site can read (PORT_SPEC
section 8). The local `.env` holds two names, `EEPHUS_ODDS_API_KEY` and
`EEPHUS_CARD_SCRAPE`; its values never entered git history (checked
2026-10-22 with `git log --all -S` over all refs).

**Check:** `sudo stat -c '%a %U' /etc/eephus.env` prints `600 root`.

### T5. Gate A, copy pass

**Say:** "Run PORT_RUNBOOK step T5 and compare the summary with docs/port/BASELINE_PYTEST.txt."

```bash
cd /opt/eephus/port/prospect-tracker
EEPHUS_DEPLOY_RUN=1 /opt/eephus/venv-port/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tail -30
```

**Check:** passed, skipped and failed counts equal the deploy-mode baseline
(PORT_SPEC Gate A: exit 0 alone is not the gate; a box without chromium skips
the browser modules and still exits 0).

### T6. Gate C, served-number equivalence

**Say:** "Run PORT_RUNBOOK step T6, first pass then rebuild pass."

First pass, before anything rebuilds (proves the copy):

```bash
/opt/eephus/venv-port/bin/python tools/port_equivalence.py compare --ref /opt/eephus/port_in/ref.json --root . --out /opt/eephus/rollback/gateC_copy.json
```

Every payload must be `IDENTICAL` or `LINE_ENDINGS` (the Windows checkout
holds 461 tracked `data/*.json` files with CRLF endings that the Linux checkout
holds with LF; the bytes are otherwise equal); anything else is a copy defect
(re-run T3).

Rebuild pass, on the same calendar date as L4 (PORT_SPEC C.0.5):

```bash
export OPENBLAS_NUM_THREADS=1 PYTHONHASHSEED=0 EEPHUS_MAX_WORKERS=3
/opt/eephus/venv-port/bin/python run_monthly.py --rebuild-only
/opt/eephus/venv-port/bin/python tools/export_trade_values.py
/opt/eephus/venv-port/bin/python build_site.py
/opt/eephus/venv-port/bin/python tools/port_equivalence.py compare --ref /opt/eephus/port_in/ref.json --root . --out /opt/eephus/rollback/gateC_rebuild.json
```

For each `DIFFERENT` file, list the leaves:

```bash
/opt/eephus/venv-port/bin/python tools/port_equivalence.py diff <the file from served-data.tar or git> data/<file>
```

**Check:** every file is IDENTICAL, LINE_ENDINGS, TIMESTAMP, FLOAT_REPR or ORDERING, or it is
on the expected list from the rehearsal (section 0.2) with the same cause. A
difference not on that list stops the port until it is explained in writing
(PORT_SPEC section 10 holds the only fixes allowed to move a number).

### T7. Publish to a staging webroot, then run Gate B

**Say:** "Run PORT_RUNBOOK step T7."

```bash
sudo mkdir -p /var/www/eephus-port && sudo chown deploy /var/www/eephus-port
EEPHUS_SKIP_PIPELINE=1 EEPHUS_REPO=/opt/eephus/port EEPHUS_VENV=/opt/eephus/venv-port \
EEPHUS_WEBROOT=/var/www/eephus-port EEPHUS_LOG_DIR=/opt/eephus/port-logs \
  /opt/eephus/port/prospect-tracker/deploy/nightly-build.sh
```

`EEPHUS_SKIP_PIPELINE=1` (added 2026-10-22) skips the checkout, pull, pip and
pipeline, then runs `build_site.py`, the pytest gate, the heartbeat
(`mode: publish-only`), the manifest-driven rsync, both comment strips and the
gzip twins. The webroot is new and empty, so no withheld file can survive from
an older build (LV-7).

Serve it on a staging name (for example `port.eephus.io`) with the server
block from `deploy/README.md`, plus one line so crawlers never index the
staging copy (the pages carry `https://eephus.io` canonicals, PORT_SPEC P0.13):

```nginx
add_header X-Robots-Tag "noindex, nofollow" always;
```

Then the Gate B check, read-only, from the target checkout:

```bash
/opt/eephus/venv-port/bin/python tools/port_live_check.py --origin https://port.eephus.io --stripped --out /opt/eephus/rollback/gateB_staging.json
```

**Check:** `"ok": true`: every page, asset and payload answers 200, all 42
withheld names answer 404, and `build_info.mode` is `publish-only`. Open
`/prospx/`, `/projections/#player=juan_soto`, `/franchise/#team=MIL`,
`/betting/` and `/standings/` in a browser and confirm they render. Confirm
`curl -sI -H "Accept-Encoding: gzip" https://port.eephus.io/data/timeseries.json`
shows `content-encoding: gzip`.

### T8. Cut over

**Say:** "Run PORT_RUNBOOK step T8."

1. Point the `eephus.io` server block's `root` at `/var/www/eephus-port` (or
   rename it to `/var/www/eephus.io` after moving the old webroot aside), and
   remove any `location /partials/` proxy (P-2 (a)). `sudo nginx -t && sudo systemctl reload nginx`.
2. Stop the old nightly: comment out its crontab line (T0 saved it).
3. Cloudflare: Caching, Purge Cache, Purge Everything. Keep Browser Cache TTL on
   "Respect Existing Headers" and no cache rule on `/data/` or HTML (deploy/README.md).
4. Run the Gate B check against production:

```bash
/opt/eephus/venv-port/bin/python tools/port_live_check.py --origin https://eephus.io --stripped --out /opt/eephus/rollback/gateB_live.json
```

**Check:** `"ok": true`, and `https://eephus.io/data/build_info.json` shows the
port branch's sha with `mode: publish-only`.

### T9. Crons (the box becomes the one nightly writer again)

**Say:** "Run PORT_RUNBOOK step T9."

Point the existing layout at the new checkout so every example file works
unchanged: move `/opt/eephus/repo` to `/opt/eephus/repo-live-old` and
`/opt/eephus/venv` to `/opt/eephus/venv-live-old`, then
`ln -s /opt/eephus/port /opt/eephus/repo` and `ln -s /opt/eephus/venv-port /opt/eephus/venv`.
Set `EEPHUS_WEBROOT` in `/etc/eephus.env` if the webroot is not `/var/www/eephus.io`.

```cron
55 2 * * * TZ=America/New_York mkdir -p /opt/eephus/backups && sqlite3 /opt/eephus/repo/prospect-tracker/prospects.db ".backup /opt/eephus/backups/prospects-$(date +\%Y\%m\%d).db" && find /opt/eephus/backups -name 'prospects-*.db' -mtime +14 -delete
10 3 * * * TZ=America/New_York /opt/eephus/repo/prospect-tracker/deploy/nightly-build.sh >> /opt/eephus/nightly.log 2>&1
```

Then paste `deploy/betting-crontab.example` (TZ=UTC is load-bearing; T1 to T8
of PORT_SPEC 5.5) and, after its own conditions, `deploy/scores-crontab.example`
below the betting lines (deploy/WEBMASTER.md section 10). The nightly now pulls
`port/2026-10` (or whatever branch the checkout tracks): set it with
`git -C /opt/eephus/repo branch --set-upstream-to=origin/port/2026-10`.
The nightly's `pip install -q -r requirements.txt` resolves floors only (owner
answer M25-2); it does not upgrade a package the T2 constraints already
satisfy, so the pinned versions stay until a floor rises.

**Check:** the next morning `curl -s -A "Mozilla/5.0" https://eephus.io/data/build_info.json`
shows a new `generated_at`, `mode` `daily`, and `tools/betting_close_job.py --selfcheck`
exits 0.

### T10. The deferred box steps (docs/DEPLOY_PENDING.md, 26 lines)

The seed carries the local database and cache, so most deferred items are
already true on the target after T3. What is still owed by hand:

| Deferred line | State after T3 | Still to do on the target |
|---|---|---|
| STATS_PA_PIPELINE, EFV3_A3_EPOCH_ID_JOIN, EPOCH_RUN step A and step Z, EFV3_A2 (draft cache), Q9_22c (mlb_transactions), TR_5 (pbp_physics, league_trends/savant_days), B6_MGMT_NIGHTLY (pbp_corpus) | Done: the seeded DB took the migrations, identity repairs and the fWAR rebase locally, and the caches they need are in `cache-carry.tar` | Nothing. Do **not** re-run `rebase_career_war.py` or the identity repair by hand on the seeded DB. |
| DISPLAY_franchise, DISPLAY_projections, CLEAN_4, CLEAN_8, LIBRARY_8, AWARDS_11, STANDINGS_7 (page side), Q8_15, SCORES_5a (page side) | Done by this repo's `nightly-build.sh` and `publish_paths.txt` in T7 | Keep `error_page 404 /404.html;` in nginx (LIBRARY_8's redirect map). |
| B6_ARCHIVE_PATHS, LIBRARY_11, W08_2, bracket simulator record | State carried | Add `.cache/efv_progress/`, `.cache/provisional_track/`, `.cache/model_updates/`, `.cache/trade_partner_screen/record/`, `.cache/bracket_sim/`, `.cache/betting/`, `.cache/odds/`, `.cache/umpire_captures/` and `.cache/leaderboard_vintages/` to the box backup. |
| SCORES_2 / SCORES_5a / SCORES_5b, STANDINGS_2 | Code present | deploy/WEBMASTER.md section 10 in order (directory, nginx `location ^~ /data/scores/`, `EEPHUS_SCORES_HOST=1`, cron line, `--selfcheck`, the standings backfill commands). |
| B5_UMPIRE_DARK_FAMILY | Code present | Its cron line (`*/15 * * * * TZ=UTC ... tools/betting_umpire_job.py`) and `--selfcheck`. |
| AWARDS_3, Q8_11 | Run by the nightly | Read the first nightly log for the lines each names. |

When an item is done, strike it in `docs/DEPLOY_PENDING.md` with the date.

### T11. Watch week

For seven nights read `!!! INGEST RED` and the pytest tail in
`/opt/eephus/nightly.log`, and re-run `tools/port_live_check.py` once a day. Keep
`/opt/eephus/repo-live-old`, the old venv, the T0 tarball and the GitHub archive
for at least 30 days (PORT_SPEC 5.6).

---

## 4. Rollback

Any time before T9's symlink swap, rollback is the nginx root alone:

```bash
# point root back at the old webroot (restore it from T0 if it was moved)
sudo tar xzf /opt/eephus/rollback/webroot-<date>.tgz -C /var/www    # only if the old webroot was removed
sudo nginx -t && sudo systemctl reload nginx
crontab /opt/eephus/rollback/crontab.txt                             # the old nightly and its jobs
```

After the swap, also restore the links:

```bash
rm /opt/eephus/repo /opt/eephus/venv
mv /opt/eephus/repo-live-old /opt/eephus/repo && mv /opt/eephus/venv-live-old /opt/eephus/venv
```

Then purge Cloudflare. Nothing on git.eephus.io needs undoing: the port
lives on its own branch `port/2026-10`, and the webmaster's branches were
never touched.

---

## 5. What not to do

- Do not force-push anything to git.eephus.io or GitHub, and do not delete either repository.
- Do not cold-rebuild the database (`EEPHUS_ALLOW_COLD_REBUILD=1`): the 2021+ snapshot history is not re-scrapable.
- Do not publish into the old webroot: withheld files survive there (LV-7).
- Do not run pytest while any exporter or `run_monthly.py` writes (the conftest guard reverts the pipeline's writes).
- Do not hand-edit a `data/*.json` artifact on the target to make T6 pass; find the cause.
- Do not refetch or "refresh" frozen `*_eval.json` sidecars (PORT_SPEC section 3).

---

## 6. Re-running the measurements

```bash
python tools/port_live_check.py --origin https://eephus.io --out live_check.json   # LV-4 to LV-8b
python tools/port_bundle.py --plan                                                  # carry counts
python tools/port_equivalence.py snapshot --root . --out ref.json                   # a new REF
```

LV-10's entity comparison read `/partials/efv`, `/partials/mlb/trade_values`,
`/partials/mlb/projections` and `/partials/player-links` on the live site against
`data/xfv.json`, `data/trade_values.json`, `data/mlb_projections.json` and
`data/player_links.json`; once the static site is live those partials are gone
and `port_live_check.py` plus `port_equivalence.py` are the whole check.

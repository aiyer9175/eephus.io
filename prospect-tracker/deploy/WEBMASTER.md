# eephus.io - webmaster runbook (refreshed 2026-07-18)

Hand this file to whoever runs the production box. Following it top to bottom
takes a fresh box to a self-updating nightly deploy that serves a site
**byte-for-byte identical to the developer's local build** - same code, same
seeded database, same `build_site.py` / `run_monthly.py`, same test gate.

Diamond (accounts, entitlements, the gate flip): the ordered go-live
checklists live in `docs/diamond-go-live.md` (added 2026-08-16). Do not turn
Supabase on or flip `gating` in `assets/diamond-config.js` without walking
them; the gate flag deliberately neutralizes itself while the account layer
is unconfigured.

Assumes: Ubuntu-ish box, nginx, Python 3.12, a `deploy` user that owns
`/opt/eephus`. Companion doc: `deploy/README.md` (architecture rationale, nginx
config, DB seeding). The build entry point is `deploy/nightly-build.sh`.

---

## 0. The model in one paragraph (why the site matches local)

There is exactly ONE nightly writer: this box. It `git pull`s the repo, runs the
same pipeline (`run_monthly.py` / `--daily`) against a **seeded canonical
`prospects.db`**, runs `build_site.py`, runs the full pytest gate, and only then
rsyncs to the nginx webroot. Because the box uses the same code and the same
seeded database the developer used, the published pages are identical to the
local `python build_site.py && python -m http.server 8000` experience. GitHub
Actions is a break-glass CI path only (it does not publish unless explicitly
armed - see deploy/README.md). Do not add a second writer.

---

## 1. Which branch the box tracks

**Track `beta`.** Development lands on `main`; a single `Sync beta to main@<sha>`
commit then delivers a full-tree snapshot of main onto `beta` (an orphan
operations branch), and the box's nightly `git pull --ff-only` picks it up. This
is the established delivery path (the operator's own box-side fixes have
historically been committed on `beta`, and the developer pushes the sync
commits).

One-time, on the box:

```bash
git -C /opt/eephus/repo checkout beta
git -C /opt/eephus/repo branch --set-upstream-to=origin/beta beta
git -C /opt/eephus/repo rev-parse --abbrev-ref HEAD   # must print: beta
```

> As of 2026-07-18 `main` and `beta` point at identical trees (main@3e06473 ==
> beta@07a22a7), so a box on either branch builds the same site tonight. The
> divergence risk returns the moment `main` moves without a beta sync - hence
> pin the box to `beta` and rely on the sync commits. If you ever find the box on
> `main`, that is fine too, but then it will pick up dev work a sync-commit
> earlier than beta-tracking boxes; keep all your boxes on the SAME branch.

The nightly script is branch-agnostic (`git pull --ff-only` on whatever branch is
checked out), so no script change is needed - just check out `beta` once.

---

## 2. One-time: install the canonical database (do NOT skip)

The live numbers are only correct with the seeded database - a cold rebuild
cannot recover the 2021+ grade-history archive and silently publishes wrong FV
histories and surplus values. The owner produces the seeds on the dev machine
(see deploy/README.md "Seeding the canonical database"):
`prospects.seed.db.gz` (~250-350MB), `cache-core.tgz` (~1GB of FanGraphs pages
that CANNOT be refetched + rate-limited scrape caches), and `fg-imports.tgz`
(hand-curated FanGraphs CSVs the pipeline ingests). Verify then install:

```bash
cd /opt/eephus
sha256sum -c SHA256SUMS.txt            # verify the three files first
gunzip prospects.seed.db.gz
mv prospects.seed.db repo/prospect-tracker/prospects.db
tar xzf cache-core.tgz -C repo/prospect-tracker/
tar xzf fg-imports.tgz -C repo/prospect-tracker/
```

The nightly script REFUSES to run without `prospects.db` (`prospects.db is
MISSING` abort). If you see that, restore the seed or a backup - never force a
cold rebuild with the override flag; that is exactly the wrong-numbers bug.

Seed vintage note: a seed cut on/after 2026-07-16 already contains the 2026
draft ingestion and the draft-board-leak + debut-date repairs, so you do NOT need
`tools/delete_draft_board_leak.py` / `tools/repair_debut_snapshots_2026.py` after
installing it. Those tools only matter for a database older than the seed.

---

## 3. One-time: repo + venv (skip what already exists)

```bash
sudo mkdir -p /opt/eephus && sudo chown deploy /opt/eephus
git clone https://github.com/aiyer9175/eephus.io.git /opt/eephus/repo
git -C /opt/eephus/repo checkout beta        # section 1
python3.12 -m venv /opt/eephus/venv
/opt/eephus/venv/bin/pip install -r /opt/eephus/repo/prospect-tracker/requirements.txt
```

The build script expects the venv at `/opt/eephus/venv` and the webroot at
`/var/www/eephus.io` (override with `EEPHUS_VENV` / `EEPHUS_WEBROOT` if your
layout differs). `pip install` is re-run every night to pick up requirement
changes, so a new dependency lands automatically.

---

## 4. First build (manual, watch it)

```bash
EEPHUS_FULL=1 /opt/eephus/repo/prospect-tracker/deploy/nightly-build.sh 2>&1 | tee /opt/eephus/nightly.log
```

Order of events: flock -> `git checkout -- .` (restore tracked artifacts the
prior pipeline rewrote) -> `git pull --ff-only` -> pip sync -> full pipeline
(30-60 min warm; longer if you skipped the cache seed) -> `build_site.py` ->
test gate -> `build_info.json` heartbeat -> rsync to webroot -> gzip precompress.
A red test suite stops before the rsync on purpose: the live site is never
replaced by a broken build.

---

## 5. Install the crons (this is the "auto-updates daily")

`crontab -e` as the deploy user:

```cron
# consistent DB backup a few minutes before the build, then auto-prune backups
# older than 14 days so /opt/eephus/backups can't fill the disk (%'s escaped)
55 2 * * * TZ=America/New_York mkdir -p /opt/eephus/backups && sqlite3 /opt/eephus/repo/prospect-tracker/prospects.db ".backup /opt/eephus/backups/prospects-$(date +\%Y\%m\%d).db" && find /opt/eephus/backups -name 'prospects-*.db' -mtime +14 -delete
# nightly build + publish, 03:10 ET (inside the 2-4am ET quiet window)
10 3 * * * TZ=America/New_York /opt/eephus/repo/prospect-tracker/deploy/nightly-build.sh >> /opt/eephus/nightly.log 2>&1
```

The script auto-selects the mode: the FULL monthly pipeline on the 1st of the
month (or with `EEPHUS_FULL=1`, or if `prospects.db` is absent), the fast
`--daily` refresh every other night. Force a full rebuild any time with
`EEPHUS_FULL=1 .../nightly-build.sh`. The `find ... -mtime +14 -delete` above
keeps two weeks of DB backups; widen it if you have the disk.

### What "auto-refresh" does each night (the mechanics)

cron 03:10 ET -> `git checkout -- .` + `git pull --ff-only` (picks up new beta
commits) -> pip sync -> pipeline (`--daily`, or FULL on the 1st) refreshes
prospects.db from the live sources and rewrites the tracked `data/*.json` +
generated pages -> `build_site.py` rebuilds every HTML page (so the committed
built pages in git are irrelevant; the box regenerates them) -> pytest gate ->
`data/build_info.json` heartbeat written -> rsync `--delete` to the webroot ->
`gzip -9` twins for nginx `gzip_static`. Reader-facing freshness shows on the
PROSPX footer (`data_freshness` stamp) and in `timeseries.json` `generated_at`.

---

## 6. nginx + Cloudflare (verify once)

nginx (full block in deploy/README.md): `gzip_static on;` (without it the boot
JSON ships uncompressed), `error_page 404 /404.html`, `location /data/` ->
`max-age=604800` (safe for the stamped payloads: glossary and the Diamond
build-time artifacts ride `?v=<stamp>` cache-busting since 2026-08-16; the
betting payloads deliberately stay `no-cache` fetches because the close job
mutates them intra-day, and revalidation is a cheap 304), `/assets/` and
`*.html` -> `no-cache` (ETag + gzip_static make revalidation a cheap 304), and
Range requests must stay enabled (the PROSPX boot probe reads bytes 0-2048 of
`timeseries.json` for its version stamp). After edits: `sudo nginx -t &&
sudo systemctl reload nginx`.

Cloudflare (dashboard, verify once):
- Caching -> Browser Cache TTL -> **"Respect Existing Headers"** (it was
  rewriting `/assets/` no-cache to a 4h max-age, so users saw stale assets).
- No "Cache Everything" rules on `/data/` or HTML.
- The bot managed-challenge 403s non-browser user agents - point any uptime
  monitor at the site with a browser User-Agent (or add a WAF skip).
- After the first successful build, do one "Purge Cache -> purge everything".

---

## 7. Verify

```bash
# heartbeat: generated_at must be tonight and must advance every night
curl -s -A "Mozilla/5.0" https://eephus.io/data/build_info.json

# every module page + script dep + per-player shard dir must be 200
for p in /prospx/ /fa/ /projections/ /mlbstats/ /pal/ /trademachine/ \
         /collegesavant/ /news/ /report/ \
         /data/value_framework.js /data/collegesavant_translation.js \
         /data/source_backtest.json /data/photo_ctx.json /data/build_info.json \
         /data/debuts_full/ ; do
  curl -s -o /dev/null -w "%{http_code} $p\n" -A "Mozilla/5.0" https://eephus.io$p
done
```

Data-sanity spot checks (confirms the site matches the intended local build):
1. Open any top prospect's detail page on `/prospx/` - the FV-history chart
   should show a multi-year line with many points per source (a degraded/cold
   DB shows only 2026 points). This is the single best "is the seed installed"
   check.
2. Open a **Farm Systems** detail page - the "graded prospects by level" list and
   the affiliate-rosters table must show the SAME eFV grade for the same player
   (the 2026-07-18 A2 fix). If they disagree, the deploy is serving pre-A2 code.
3. Open a graduate card, then open a second one - the per-player `debuts_full/`
   shard should load (Network tab shows `debuts_full/<key>.json`, 200) rather
   than re-pulling the whole debuts monolith (the 2026-07-18 A1 fix; the shard
   dir is now in both the rsync manifest and CI staging).
4. On any list, click **Generate GFX** - the graphic should render with the
   current filters/sort and a scannable QR.

---

## 8. Ongoing / troubleshooting

- `generated_at` in `build_info.json` stalls => `tail -200 /opt/eephus/nightly.log`.
  The script prints a loud `!!! WEBROOT STALE` banner when `index.html` in the
  webroot is >48h old, and the test gate prints its failures right above the
  missing rsync. The step-summary tail names the failed phase.
- The nightly test gate runs under `EEPHUS_DEPLOY_RUN=1`, which relaxes the
  dev-time exact-hash golden tripwires to shape checks (a deploy run legitimately
  regenerates them). Do not remove that flag - its absence is what froze
  publishing after 2026-07-11.
- A log line `OWNER ACTION PENDING: editorial_eval` (if it appears) is informational
  for the owner; deploys are NOT frozen by it - the nightly SKIPS that step with a
  warning and keeps publishing. (Older docs describing a hard editorial-eval
  freeze are superseded.)
- GitHub Actions does NOT touch this box unless the repo variable
  `EEPHUS_CI_PUBLISH` is set to `true` (break-glass only, e.g. box outage). Normal
  operation: this box is the only writer. A CI runner's DB is a degraded cold
  rebuild, so arm CI publish only during a real outage, then unset it.
- Ongoing FanGraphs data: scp new CSVs to `data/fangraphs_imports/` on the box,
  then force one `EEPHUS_FULL=1 .../nightly-build.sh` to ingest them.
- State worth backing up: `prospects.db` (cron above), `.cache/` and, inside it
  and named separately because it is the one directory that CANNOT be rebuilt,
  **`.cache/betting/`** and **`.cache/odds/`**, plus two append-only ledgers that
  also cannot be rebuilt: **`.cache/efv_progress/ledger.jsonl`** (the dated rows
  behind `data/efv_progress.json`, the glossary Source Comparison record) and
  **`.cache/provisional_track/`** (the ledger behind
  `data/provisional_track_eval.json`). Both are untracked so they survive the
  nightly `git checkout -- .`, which also means a box rebuild loses them unless
  they are backed up. Everything
  else rebuilds from the repo. Note that `data/scout_reports.json` on the webroot
  is a frozen fallback (it is publish-excluded but survives via rsync without
  `--delete-excluded`); its live content ships via the chunked
  `scout_reports_*.json` shards.
- **The postseason bracket simulator's forward record** is
  `.cache/bracket_sim/record.json` (docs/betting-2026-10/BRACKET_SIM_GATE.md
  7.2): one chain-hashed entry per day of the postseason, first write wins, and
  it cannot be rebuilt, because each entry froze that day's bracket and board.
  Back it up with `.cache/betting/`. `data/bracket_sim_record.json` and
  `data/bracket_sim.json` are derived re-renders published by rsync.
- **Postseason results.** The 26 files `data/_labs/postseason/statsapi_postseason_{2000..2025}.json` are tracked and never published (neither deploy consumer ships `data/_labs/`), so this box's checkout and its nightly `git checkout -- .` carry every completed postseason; the live season is fetched by run_daily step d8p on this box itself into `.cache/statsapi_postseason_{Y}.json`.
- **Why those two betting directories are not "just cache".** `.cache/odds/` is
  the immutable price evidence: a closing line that was not captured near first
  pitch is gone, and every CLV grade on the public record is derived from it.
  Inside `.cache/betting/` there are exactly three files that matter, and this
  list is the one the code writes - an earlier revision of this runbook named a
  `shadow.jsonl` that has never existed:

  | file | what it is | rebuildable |
  | --- | --- | --- |
  | `record.jsonl` | the append-only PUBLIC BETTING RECORD itself, one chain-hashed envelope per line | no |
  | `shadow.json` | the paper-bet ledger gate 3 of the min-edge sweep counts toward, tagged by selection rule | no |
  | `published_chain.json` | the chain hash the last build published, which is the only thing that can tell an append apart from a rewrite | no |

  `calibration.jsonl` also lives here (every priced side, no floor, for the
  probability curve); losing it costs the calibration series but no claim.
  `data/betting_record.json` and `data/betting_shadow.json` are DERIVED
  re-renders written by every build and published by rsync. They are not backups
  of anything.
  A box rebuild that restores only `prospects.db` destroys the record, the paper
  ledger and every price they were graded against, and none of it re-pulls: The
  Odds API sells the current board, not last Tuesday's close.
  They live under `.cache/` and not under `data/` for one reason:
  `deploy/nightly-build.sh` runs `git checkout -- .` before every pipeline, and
  `data/betting_record.json` was git-tracked, so a row appended there at 21:00
  was reverted to the committed `[]` at 03:10 with no error anywhere. That file
  was untracked on 2026-08-09 (`git rm --cached`) and is now gitignored, along
  with `data/betting_shadow.json`, which had been untracked AND unignored - one
  `git add -A` away from arming the identical defect on the evidence base.
- **How to check the record is actually safe on this box**, in one command:

  ```sh
  cd ~/eephus/prospect-tracker && python -c "import betting_export as be, betting_shadow as bs, json; print(json.dumps({'record': be.record_storage(), 'anchor': be.read_published_chain(), 'shadow': bs.storage()}, indent=1))"
  ```

  `record.durable` and `shadow.durable` must both be `true`, and `anchor.source`
  must end in `published_chain.json`. An `anchor.source` still naming
  `data/betting.json` means no build has stamped the durable anchor yet, and
  until one does the rewrite half of the `record_storage` publish blocker passes
  by construction rather than by evidence.
- **Disk / low-space.** The build does a disk preflight: if free space is under
  `EEPHUS_DISK_MIN_GB` (default 6) it prunes the refetchable game/player caches
  (`.cache/win_prob`, `statcast_metrics`, `zone_metrics`, `game_feeds`, Savant
  pulls - the bulk of the ~40GB+ cache, all re-pullable from StatsAPI/Savant)
  toward `EEPHUS_DISK_TARGET_GB` (default 12) and, only if still tight, aborts
  BEFORE the build rather than dying mid-write. Inspect or run pruning by hand:
  `python tools/prune_cache.py --report` (per-cache sizes),
  `python tools/prune_cache.py --target-free-gb 20` (reclaim to 20GB free),
  `python tools/prune_cache.py --max-age-days 400` (steady-state age bound).
  Pruned files simply re-fetch on the next run that needs them (a slower build,
  never wrong data). On a deliberately tiny box set `EEPHUS_DISK_MIN_GB=0` to
  skip the guard, but then watch `df -h` yourself. Backups auto-prune at 14 days
  via the cron above; `.cache/efv_backup`, `bref_register`, `draft_history` are
  never auto-pruned (backup / rate-limited scrapes).

---

## 9. What changed since the last runbook (2026-07-14 -> 2026-07-18)

- **Branch pinned (section 1).** The prior runbook cloned without naming a branch;
  the box now explicitly tracks `beta`.
- **debuts_full shards now ship.** `deploy/nightly-build.sh` and the CI staging
  step gained `/data/debuts_full/***`; the PROSPX graduate-card lazy-load was
  fixed to read the shard directory (2026-07-18 A1). Verify #3 above covers it.
- **The old "what is wrong today" section is retired** - the July 2026 incidents
  (404ing modules, frozen CI, cold-rebuilt wrong numbers) are fixed in the repo
  and this runbook describes the healthy steady state, not the recovery.
- **Boot-payload size:** the 2026-07-15..17 payload-slimming program (prospx
  sharding, debuts lite/full split, scout-report chunking, CollegeSavant
  year-split) materially reduced wire weight; re-measure with the browser Network
  tab if you need a current figure rather than trusting an old "~26MB" number.
- After any new dev work lands on `main`, a `Sync beta to main@<sha>` commit is
  the prerequisite for this box (on `beta`) to pick it up; confirm the box built
  it via `build_info.json`'s `git_sha`.

---

## 10. MLB Scores job (install only after step Z and the SCORES_LIVE flip)

**When.** Do this only after the fWAR label epoch's step Z is recorded AND after
the SCORES_LIVE flip (SCORES_5a_LIVE_FLIP) has reached this box through the owner's
push, the beta sync and a nightly pull (SCORES_PLAN.md section 17). Before the
flip the job writes only `.cache/scores/preview/` whatever its environment says,
so an early install serves nothing. Until then this section is a plan, not the
live state.

**In order, as the deploy user** (below, `PY=/opt/eephus/venv/bin/python`):

1. Confirm the checkout holds the job and the flip:
   `git -C /opt/eephus/repo log -1 --oneline`, then
   `grep -n "^SCORES_LIVE" /opt/eephus/repo/prospect-tracker/scores_core.py`
   must print `SCORES_LIVE = True`.
2. The directory: `mkdir -p /opt/eephus/scores`, then `namei -l /opt/eephus/scores`
   (nginx must be able to traverse and read it; the job writes every file 0644 and
   every directory 0755).
3. The location: add the `location ^~ /data/scores/` block from deploy/README.md
   ("MLB Scores: the /data/scores/ location") ABOVE `location /data/`, then
   `sudo nginx -t && sudo systemctl reload nginx`.
4. The health row: add `EEPHUS_SCORES_HOST=1` to `/etc/eephus.env`, so the
   nightly files the `scores_job` ingest-health row on this machine (a machine
   without the job files nothing).
5. The cron line: install `deploy/scores-crontab.example` with `crontab -e`. Its
   `EEPHUS=/opt/eephus/repo/prospect-tracker` is the checkout the nightly uses
   and its line sets `EEPHUS_SCORES_OUT=/opt/eephus/scores`. Pasted into one
   crontab with the betting example, the scores block goes AFTER the betting
   lines (the betting file's `EEPHUS` names the wrong checkout).
6. After one cycle: `cd /opt/eephus/repo/prospect-tracker && $PY tools/scores_job.py --selfcheck`
   (exit 0 and a recent last run), then the curl:

   ```bash
   curl -sI -A "Mozilla/5.0" https://eephus.io/data/scores/latest.json
   # expect HTTP 200 and cache-control: no-cache; latest.json's job.state reads ok or idle
   ```

   Keep Cloudflare on "Respect Existing Headers" with no cache rule on `/data/`.
7. A weekly logrotate stanza, `/etc/logrotate.d/eephus-scores`:

   ```
   /opt/eephus/repo/prospect-tracker/logs/scores-job.log {
       weekly
       rotate 4
       compress
       missingok
       notifempty
       copytruncate
   }
   ```

8. The 2026 history (owner answer SC-HISTORY (a)): between 11:00 UTC and first
   pitch, or on an off day, one month at a time:

   ```bash
   cd /opt/eephus/repo/prospect-tracker && \
     EEPHUS_SCORES_OUT=/opt/eephus/scores EEPHUS_WEBROOT=/var/www/eephus.io \
     $PY tools/scores_job.py --backfill 2026-03-25:2026-04-30
   ```

   It refuses 06:00 to 11:00 UTC, any date before 2026-03-25, and any run while a
   game is live; it releases the job lock every 50 requests so live cycles
   interleave, and a rerun skips the games it already froze.

**What it owns.** `/opt/eephus/scores` belongs to the scores job; the nightly
never ships or compresses /opt/eephus/scores; it is rebuildable, no backup needed.
The job also keeps `.cache/scores/` (its slate, state, heartbeat, run logs and
work files) and `logs/scores-job.log`; it writes no tracked file, nothing under
`data/`, nothing in the webroot, and never touches the nightly's lock.

**The kill switch for embedded video** (once SCORES_4a lands):
`touch /opt/eephus/scores/EMBED_OFF` takes effect at the next cron tick; remove
the file to restore.

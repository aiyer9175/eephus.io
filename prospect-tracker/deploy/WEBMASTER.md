# eephus.io - webmaster setup (2026-07-14)

Hand this file to whoever runs the production box. Following it top to
bottom takes the site from its current state (frozen at July 11, whole
modules 404ing, wrong historical numbers) to a self-updating nightly
deploy. Assumes: Ubuntu-ish box, nginx, Python 3.12 available, and a
`deploy` user that owns `/opt/eephus`.

## What is wrong today (context)

1. `/mlbstats/`, `/pal/`, `/trademachine/`, `/news/` return 404 while the
   homepage nav and sitemap.xml link to them - the old deploy scripts
   shipped a hardcoded, incomplete directory list. Fixed in the repo
   (`deploy/publish_paths.txt` is now the single manifest); the fix
   reaches production on your first successful build below.
2. Nothing has published since 2026-07-11 - the CI publish path froze on
   a red test gate (also fixed in the repo) and no server cron exists.
3. The live numbers are quietly WRONG: the server database was rebuilt
   from scratch, which cannot recover the 2021+ grade-history archive.
   Players show a handful of FV data points instead of dozens, and
   consensus/surplus values are off by large amounts. The one-time
   database seed below fixes this - do not skip it.

## Step 1 - one-time: receive and install the canonical database

The owner produces the seeds on the dev machine (see deploy/README.md
"Seeding the canonical database"): `prospects.seed.db.gz` (~250-350MB),
`cache-core.tgz` (~1GB: FanGraphs pages that CANNOT be refetched +
rate-limited scrape caches) and `fg-imports.tgz` (hand-curated FanGraphs
CSVs the pipeline ingests). Install all three:

```bash
gunzip /opt/eephus/prospects.seed.db.gz
mv /opt/eephus/prospects.seed.db /opt/eephus/repo/prospect-tracker/prospects.db
tar xzf /opt/eephus/cache-core.tgz -C /opt/eephus/repo/prospect-tracker/
tar xzf /opt/eephus/fg-imports.tgz -C /opt/eephus/repo/prospect-tracker/
```

(Do not worry about the dev machine's full 47GB `.cache/` - the rest is
refetchable API caches; the first full run rebuilds what it needs, it
just takes a few hours longer.)

Note: the nightly script now REFUSES to run without `prospects.db` (a
cold rebuild silently publishes wrong numbers - that is exactly the
current live bug). If you ever see it abort with `prospects.db is
MISSING`, restore the seed or a backup; do not just re-run with the
override flag.

## Step 2 - one-time: repo + venv (skip what already exists)

```bash
sudo mkdir -p /opt/eephus && sudo chown deploy /opt/eephus
git clone https://github.com/aiyer9175/eephus.io.git /opt/eephus/repo   # or: git -C /opt/eephus/repo pull --ff-only
python3.12 -m venv /opt/eephus/venv
/opt/eephus/venv/bin/pip install -r /opt/eephus/repo/prospect-tracker/requirements.txt
```

The build script expects the venv at `/opt/eephus/venv` and the webroot
at `/var/www/eephus.io` (override with `EEPHUS_VENV` / `EEPHUS_WEBROOT`
if your layout differs).

## Step 3 - first build (manual, watch it)

```bash
EEPHUS_FULL=1 /opt/eephus/repo/prospect-tracker/deploy/nightly-build.sh 2>&1 | tee /opt/eephus/nightly.log
```

Order of events: git pull -> pip sync -> full pipeline (30-60 min warm,
longer if you skipped the cache seed) -> page build -> test gate -> rsync
to webroot -> gzip precompress. A red test suite stops before the rsync
on purpose: the live site is never replaced by a broken build.

## Step 4 - install the crons (this is the "auto-update daily")

`crontab -e` as the deploy user:

```cron
# consistent DB backup a few minutes before the build (%'s must be escaped)
55 2 * * * TZ=America/New_York mkdir -p /opt/eephus/backups && sqlite3 /opt/eephus/repo/prospect-tracker/prospects.db ".backup /opt/eephus/backups/prospects-$(date +\%Y\%m\%d).db"
# nightly build + publish, 03:10 ET (inside the 2-4am ET quiet window)
10 3 * * * TZ=America/New_York /opt/eephus/repo/prospect-tracker/deploy/nightly-build.sh >> /opt/eephus/nightly.log 2>&1
```

The script runs the fast daily refresh most nights and the FULL monthly
pipeline automatically on the 1st. Force a full rebuild any time with
`EEPHUS_FULL=1 .../nightly-build.sh`. Prune `/opt/eephus/backups` on
whatever retention you like (a week or two is plenty).

## Step 5 - nginx (verify once)

The server block must have `gzip_static on;` plus the cache-header
locations documented in deploy/README.md (nginx section). Without
`gzip_static` the ~26MB boot JSON ships uncompressed. After edits:
`sudo nginx -t && sudo systemctl reload nginx`.

## Step 6 - Cloudflare (verify once, in the dashboard)

- Caching -> Browser Cache TTL -> **"Respect Existing Headers"**.
  (Observed live: Cloudflare rewrote our `/assets/` `no-cache` to
  `max-age=14400`, so users could see stale assets for 4h after a
  deploy.)
- No "Cache Everything" rules on `/data/` or HTML.
- The bot challenge (403 for non-browser user agents) is fine to keep,
  but point any uptime monitor at the site with a browser User-Agent.
- After your first successful build, do one "Purge Cache -> purge
  everything" so nothing stale lingers.

## Step 7 - verify

```bash
# heartbeat: generated_at must be tonight, and must advance every night
curl -s -A "Mozilla/5.0" https://eephus.io/data/build_info.json

# formerly-404 resources must all be 200 now: the module pages, the
# /data/*.js script deps, and the monthly-only artifacts the first FULL
# run generates (source_backtest, photo_ctx)
for p in /mlbstats/ /pal/ /trademachine/ /news/ /report/ /prospx/ \
         /data/value_framework.js /data/collegesavant_translation.js \
         /data/source_backtest.json /data/photo_ctx.json /data/build_info.json; do
  curl -s -o /dev/null -w "%{http_code} $p\n" -A "Mozilla/5.0" https://eephus.io$p
done
```

Data sanity after the DB seed: open any top prospect's detail page on
/prospx/ - the FV history chart should show a multi-year line with many
points per source (the degraded build showed only 2026 points).

## Ongoing

- `generated_at` in build_info.json stalls => check
  `tail -200 /opt/eephus/nightly.log`. The script prints a loud
  `!!! WEBROOT STALE` banner when previous nights failed, and the test
  gate prints its failures right above the missing rsync.
- A log line containing `OWNER ACTION PENDING: editorial_eval` is for
  the owner (a model-registry verdict is due); the site keeps
  publishing.
- GitHub Actions does NOT touch this server unless the repo variable
  `EEPHUS_CI_PUBLISH` is set to `true` (break-glass only, e.g. box
  outage). Normal operation: this box is the only writer.
- State worth backing up: `prospects.db` (cron above) and `.cache/`.
  Everything else rebuilds from the repo.

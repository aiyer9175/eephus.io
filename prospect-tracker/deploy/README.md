# Deploying eephus.io (without GitHub Pages)

Production serves from an nginx box. The box is the ONE nightly writer
(Option 1). The GitHub workflow is CI; its SSH publish is a break-glass
path that stays off unless you explicitly arm it (Option 2).

## Seeding the canonical database (do this FIRST)

`prospects.db` carries the 2021+ snapshot history: per-source grade
lists, tool grades, metric/Arkmetric snapshots, IL history. The archive
backfills that built it were ONE-TIME - a fresh box that re-scrapes
today's sources gets only current lists and silently publishes wrong FV
history, consensus, and surplus numbers (production did exactly this
after 2026-07-11: 6 FV instances for players with 61, surplus off by
tens of $M). `nightly-build.sh` therefore REFUSES to run without a DB
unless `EEPHUS_ALLOW_COLD_REBUILD=1` is set.

On the dev machine (the box that has the real history):

```bash
cd prospect-tracker
# consistent snapshot even if something has the DB open (also compacts):
python -c "import sqlite3; sqlite3.connect('prospects.db').execute(\"VACUUM INTO 'prospects.seed.db'\")"
gzip -9 prospects.seed.db                       # ~4-5x smaller on the wire
scp prospects.seed.db.gz deploy@SERVER:/opt/eephus/

# Cache seed - SELECTIVE. The full .cache is ~47GB (measured 2026-07-14:
# win_prob 19GB + statcast_metrics 15GB + game_feeds 6GB + zone_metrics
# 5GB), all refetchable API caches - do NOT ship those unless bandwidth
# is free (they only make the first full run hours faster). What IS
# worth shipping is small and partly irreplaceable:
#   fg_*           FanGraphs pages  (~80MB - FG blocks Python; CANNOT refetch)
#   milb_stats/    xFV model stat splits (~30MB)
#   savant_*, spotrac_*, fa_*  (rate-limited scrape caches, ~700MB)
tar czf cache-core.tgz .cache/fg_* .cache/milb_stats .cache/savant_* \
    .cache/spotrac_* .cache/fa_*
scp cache-core.tgz deploy@SERVER:/opt/eephus/
# also ship the manual FanGraphs CSV drops (gitignored, hand-curated):
tar czf fg-imports.tgz data/fangraphs_imports data/fangraphs_articles 2>/dev/null || true
scp fg-imports.tgz deploy@SERVER:/opt/eephus/
```

On the server:

```bash
gunzip /opt/eephus/prospects.seed.db.gz
mv /opt/eephus/prospects.seed.db /opt/eephus/repo/prospect-tracker/prospects.db
tar xzf /opt/eephus/cache-core.tgz -C /opt/eephus/repo/prospect-tracker/
tar xzf /opt/eephus/fg-imports.tgz -C /opt/eephus/repo/prospect-tracker/
```

## Getting NEW FanGraphs data into production (ongoing)

FanGraphs blocks the pipeline's HTTP client, so FG lists enter via
hand-dropped CSVs in `data/fangraphs_imports/` (gitignored - they stay
out of the repo). Now that the SERVER is the publishing box, a CSV
dropped on the dev machine never reaches production by itself:

```bash
scp data/fangraphs_imports/NEW_FILE.csv deploy@SERVER:/opt/eephus/repo/prospect-tracker/data/fangraphs_imports/
# ingestion happens on the next FULL run (step 0b) - force one:
ssh deploy@SERVER 'EEPHUS_FULL=1 /opt/eephus/repo/prospect-tracker/deploy/nightly-build.sh >> /opt/eephus/nightly.log 2>&1'
```

## Option 1 - the server builds itself (THE production path)

The nginx box pulls the repo and runs the pipeline locally, so
`prospects.db`, `.cache/`, and `data/pitch_plots/` live on a real disk
forever (no CI cache eviction, no cold rebuilds).

One-time setup on the server:

```bash
sudo mkdir -p /opt/eephus && sudo chown "$USER" /opt/eephus
git clone https://github.com/aiyer9175/eephus.io.git /opt/eephus/repo
python3.12 -m venv /opt/eephus/venv
/opt/eephus/venv/bin/pip install -r /opt/eephus/repo/prospect-tracker/requirements.txt
# seed prospects.db (and optionally .cache/) as described above, THEN:
EEPHUS_FULL=1 /opt/eephus/repo/prospect-tracker/deploy/nightly-build.sh
```

Then `crontab -e`:

```cron
10 3 * * * TZ=America/New_York /opt/eephus/repo/prospect-tracker/deploy/nightly-build.sh >> /opt/eephus/nightly.log 2>&1
```

Point the nginx `root` at `/var/www/eephus.io` (the script's WEBROOT).
The script fast-forward-pulls, runs `--daily` (full pipeline on the 1st),
rebuilds pages, gates on pytest, and rsyncs only the browser-served
files into the webroot. A red test suite leaves the live site untouched.

## Option 2 - CI publish over SSH (BREAK-GLASS ONLY)

The workflow (`.github/workflows/deploy-prospect-tracker.yml`) builds
and test-gates on every push, but it publishes to the server only when
BOTH the three SSH secrets exist AND the repo variable
`EEPHUS_CI_PUBLISH` is set to `true`. Keep the variable unset in normal
operation: a CI runner's DB is a cold rebuild without the snapshot
history, so letting it rsync over the box's canonical build regresses
the live numbers (July 2026 incident). Arm it only when the box is down
and a knowingly-degraded emergency publish beats an outage - then unset
it again.

Setup (only if you ever want the break-glass path available):

```bash
# anywhere local:
ssh-keygen -t ed25519 -f eephus_deploy -N "" -C "eephus-nightly-deploy"
# on the server, append eephus_deploy.pub to ~deploy/.ssh/authorized_keys
```

Repo Settings -> Secrets and variables -> Actions:

| kind     | name                | value                                       |
|----------|---------------------|---------------------------------------------|
| secret   | `DEPLOY_SSH_KEY`    | contents of the PRIVATE key `eephus_deploy` |
| secret   | `DEPLOY_SSH_HOST`   | `deploy@your.server.ip`                     |
| secret   | `DEPLOY_WEBROOT`    | `/var/www/eephus.io`                        |
| variable | `EEPHUS_CI_PUBLISH` | `true` ONLY during a box outage             |

## Why one writer?

Two schedules rsyncing the same webroot from different databases is how
you get a site whose numbers change depending on which writer ran last,
and `--delete` runs that remove files the other writer shipped. The box
has the durable state, so the box owns the webroot; CI gates pushes.

## Publish-time comment strip (prospx)

`tools/strip_prospx_comments.py` runs in `nightly-build.sh` between the
rsync and the precompress, rewriting **the webroot copy only** of
`prospx/index.html` (~630KB raw / ~265KB gz smaller at introduction). The
repo source keeps every comment - it is the app's documentation. The tool
is a conservative tokenizer (own-line `//`, `/* */`, and `<!-- -->` only;
strings, template literals, regex literals, `<style>`, and Copyright
notices are never touched; it refuses to write unless a re-scan of its own
output ends in a clean lexer state) and the sh step is fail-open: a strip
failure ships the commented copy instead of blocking the nightly. The CI
break-glass path (`EEPHUS_CI_PUBLISH`) does NOT strip - acceptable for an
emergency publish, the page is just its commented size.

`tools/strip_asset_comments.py` (2026-10-03) runs right after it, on the
webroot copies of `assets/*.css`, `assets/*.js`, `collegesavant/app.js` and
`collegesavant/pitcher_app.js` (about 830KB raw of comments at introduction,
`site.css` alone 40 percent). It reuses the prospx JS tokenizer, adds a CSS
tokenizer that walks strings and unquoted `url(...)` bodies, and validates
each file before writing it: JS must compile under `node --check` (node on
PATH, the `EEPHUS_NODE` override, or V8 through `py_mini_racer`), CSS must
keep balanced braces and the same rule count. A file that fails keeps its
commented copy, and with no JavaScript engine every JS file ships whole.
The `?v=` stamps hash the repo sources, so they do not move.

## nginx server block (required pieces)

The build script precompresses every text asset (`*.gz` twins, gzip -9).
nginx needs `gzip_static` to serve them - without it the boot JSON ships
uncompressed and the Open Beta page-weight work is wasted. The 404 page
and sensible cache headers ride the same block:

```nginx
server {
    server_name eephus.io;
    root /var/www/eephus.io;
    index index.html;

    # Serve the precompressed .gz twins (build script writes them).
    # ngx_http_gzip_static_module ships with stock nginx.
    gzip_static on;
    # Fallback live compression for anything without a twin.
    gzip on;
    gzip_types application/json application/javascript text/css
               image/svg+xml application/xml text/plain;
    gzip_comp_level 5;
    gzip_min_length 1024;

    # The on-theme not-found page (build_site.py writes /404.html).
    error_page 404 /404.html;

    # Data payloads are fetched with ?v=<stamp> cache-busting, so a long
    # max-age is safe for /data/. Assets under /assets/ are NOT uniformly
    # stamped: the generated pages hash them, but the hand-authored PROSPX
    # and CollegeSavant pages hand-bump a shared ?v= that can lag a deploy.
    # Serving /assets/ no-cache makes the browser revalidate with the ETag
    # and take a cheap 304 when the file is unchanged; gzip_static keeps
    # that revalidation cheap because the .gz twin ships the same ETag and
    # no body rides the 304. The HTML pages stay no-cache too so a rebuild
    # shows up on the next reload. (The hand-authored pages also ?v=-stamp
    # their /vendor/ and same-directory JS, so those stay cache-safe under
    # the default location.)
    location /data/    { add_header Cache-Control "public, max-age=604800"; }
    location /assets/  { add_header Cache-Control "no-cache"; }
    location ~* \.html$ { add_header Cache-Control "no-cache"; }

    # Range requests must stay enabled (default) - the PROSPX boot probe
    # reads bytes 0-2048 of timeseries.json for its version stamp.
}
```

Reload with `sudo nginx -t && sudo systemctl reload nginx`.

## MLB Scores: the /data/scores/ location (NOT INSTALLED YET)

Add this only after the fWAR label epoch's step Z is recorded and after the
SCORES_LIVE flip (SCORES_5a_LIVE_FLIP) has reached the box, in the order
deploy/WEBMASTER.md section 10 gives. Until then the server block above is the
live state and carries no scores entry. `tools/scores_job.py` is the only writer
of `/opt/eephus/scores/`; nginx serves it at the URL the page reads:

```nginx
# /data/scores/ belongs to tools/scores_job.py: one writer, one directory, no twins.
location ^~ /data/scores/ {
    alias /opt/eephus/scores/;
    gzip_static off;      # the job writes no .gz twin; never serve a stale one
    gzip on;              # on-the-fly; gzip_types already lists application/json
    add_header Cache-Control "no-cache";
}
```

Put it above `location /data/`. It is the longer prefix, so it wins over
`location /data/` and its week-long max-age, and `^~` also stops the regex
locations. The nightly rsync never names it, so its `--delete` cannot touch it;
the precompress step walks the webroot only, so no stale `.gz` twin can shadow
`latest.json`; the CI break-glass rsync cannot reach it either. Nothing in the
nightly changes. If the location is missing the page gets a 404 and says live
scores are not available; nothing else breaks.

Verify after the job's first cycle (Cloudflare challenges bare user agents, so
send a browser one):

```bash
curl -sI -A "Mozilla/5.0" https://eephus.io/data/scores/latest.json
# expect: HTTP 200 and cache-control: no-cache
curl -s -A "Mozilla/5.0" https://eephus.io/data/scores/latest.json | python -c "import json,sys; j=json.load(sys.stdin)['job']; print(j['state'], j['next_by'])"
# expect: state ok or idle, and next_by in the future
```

## Cloudflare (the site fronts through it)

Observed live 2026-07-14, worth pinning down in the dashboard:

- **Browser Cache TTL rewrites our headers.** Origin serves `/assets/`
  as `no-cache`, but Cloudflare rewrote it to `max-age=14400` (its
  default Browser Cache TTL), so browsers can hold stale assets for 4h
  after a deploy. Set Caching -> Browser Cache TTL to **"Respect
  Existing Headers"**.
- **Do NOT enable "Cache Everything"** (or any cache rule) for `/data/`
  or `*.html`. The nightly refresh depends on HTML and the un-stamped
  boot probe revalidating; `?v=`-stamped data URLs are already safe.
- **Bot challenge**: non-browser user agents get a managed challenge
  (403). Fine for humans; note it blocks naive uptime checks - point
  monitors at the site with a browser UA or add a WAF skip rule for
  your monitor.
- After a deploy that changes shared assets, "Purge Cache -> purge
  everything" is the blunt-but-safe reset while the TTL rule above is
  not yet in place.

## Did tonight's build publish? (verification)

The nightly writes a heartbeat the rsync ships:

```bash
curl -s -A "Mozilla/5.0" https://eephus.io/data/build_info.json
# {"generated_at":"2026-07-15T07:41:02Z","git_sha":"abc1234","mode":"daily"}
```

`generated_at` must move every night. If it stops: `tail -100
/opt/eephus/nightly.log` on the box - the script logs a loud
`!!! WEBROOT STALE` line when the previous nights failed to publish,
and a red test suite (the publish gate) prints its failures right
above the missing rsync line. Spot-check the modules after any deploy
change: `/prospx/`, `/mlbstats/`, `/pal/`, `/trademachine/`, `/news/`,
`/report/` must all be 200.

## Fresh-box / first-run notes

`nightly-build.sh` is safe on a clean clone EXCEPT for the database:
a missing `prospects.db` aborts with instructions (see "Seeding the
canonical database" - a cold rebuild cannot recover the 2021+ snapshot
history; `EEPHUS_ALLOW_COLD_REBUILD=1` overrides if you truly want a
degraded site). Everything else self-heals: `data/pitch_plots/` and
`data/player_detail/` are (re)created by the exporter, and
`build_site.py` writes every page plus robots.txt / sitemap.xml /
404.html from scratch. Shell scripts are pinned LF via .gitattributes,
so a checkout from any OS runs under cron. The only state worth
backing up is `prospects.db` and `.cache/` (everything else rebuilds).

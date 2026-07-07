# Deploying eephus.io (without GitHub Pages)

Production serves from an nginx box. Two supported ways to make it
auto-refresh nightly in the 2-4am ET window - pick ONE.

## Option 1 - the server builds itself (recommended: durable state)

The nginx box pulls the repo and runs the pipeline locally, so
`prospects.db`, `.cache/`, and `data/pitch_plots/` live on a real disk
forever (no CI cache eviction, no cold rebuilds).

One-time setup on the server:

```bash
sudo mkdir -p /opt/eephus && sudo chown "$USER" /opt/eephus
git clone https://github.com/aiyer9175/eephus.io.git /opt/eephus/repo
python3.12 -m venv /opt/eephus/venv
/opt/eephus/venv/bin/pip install -r /opt/eephus/repo/prospect-tracker/requirements.txt
# seed the state once (the full pipeline; takes a while cold):
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

## Option 2 - GitHub Actions builds, then pushes over SSH

The nightly workflow (`.github/workflows/deploy-prospect-tracker.yml`,
07:30 UTC) already builds and test-gates the full site. Add three
secrets and it rsyncs the build straight to the server - the box needs
nothing but rsync + an authorized key.

One-time setup:

```bash
# anywhere local:
ssh-keygen -t ed25519 -f eephus_deploy -N "" -C "eephus-nightly-deploy"
# on the server, append eephus_deploy.pub to ~deploy/.ssh/authorized_keys
```

Repo Settings -> Secrets and variables -> Actions:

| secret            | value                                      |
|-------------------|--------------------------------------------|
| `DEPLOY_SSH_KEY`  | contents of the PRIVATE key `eephus_deploy` |
| `DEPLOY_SSH_HOST` | `deploy@your.server.ip`                     |
| `DEPLOY_WEBROOT`  | `/var/www/eephus.io`                        |

The workflow's "Publish to server over SSH" step activates only when
the secrets exist; without them it logs a skip line. GitHub Pages
remains an optional mirror - its steps are continue-on-error, so a
repo with Pages disabled still gets the SSH publish.

## Why not both?

You can: Option 2 for the site plus Option 1's cron WITHOUT the rsync
(state-only) is pointless complexity. If the server is beefy enough to
run the pipeline, Option 1 alone is the simplest reliable system; if
you would rather keep the server dumb, Option 2 alone.

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

## Fresh-box / first-run notes

`nightly-build.sh` is safe on a clean clone: a missing `prospects.db`
forces the FULL monthly pipeline (slow, one time), `data/pitch_plots/`
and `data/player_detail/` are (re)created by the exporter, and
`build_site.py` writes every page plus robots.txt / sitemap.xml /
404.html from scratch. Shell scripts are pinned LF via .gitattributes,
so a checkout from any OS runs under cron. The only state worth
backing up is `prospects.db` and `.cache/` (everything else rebuilds).

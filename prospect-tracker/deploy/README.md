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

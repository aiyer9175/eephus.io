# Deploy runbook (nginx box, nightly build)

Owner-facing runbook for the eephus.io production box. The box IS the pipeline
runner: it pulls the repo, runs the pipeline, gates on the test suite, and
rsyncs the built site into the nginx webroot. Script: `deploy/nightly-build.sh`.

## 1. Cron

Install as the deploy user. This is the exact line from the script header
(03:10 ET nightly, inside the 2-4am refresh window):

```
10 3 * * * TZ=America/New_York /opt/eephus/repo/prospect-tracker/deploy/nightly-build.sh >> /opt/eephus/nightly.log 2>&1
```

If the box runs UTC and you drop `TZ=`, use `10 7 * * *` (about 3:10 EDT).

The script self-restores the tracked tree (`git checkout -- .`) before the
`git pull --ff-only`, so the previous night's regenerated artifacts do not
leave the tree dirty and abort the fast-forward. Untracked state that must
persist (`prospects.db`, `.cache/`, `data/pitch_plots/`) is not touched by the
restore.

The test gate runs with `EEPHUS_DEPLOY_RUN=1`. That flag relaxes the dev-time
exact-hash golden tripwires (data/xfv.json and any sibling artifact goldens) to
shape checks, because a deploy run legitimately regenerates those files from
fresh data every night. With the flag unset (dev and CI), the exact-hash
behavior is unchanged.

## 2. First run

**Seed `prospects.db` BEFORE the first run** (deploy/README.md, "Seeding the
canonical database"). The DB carries the 2021+ snapshot history that a
re-scrape cannot recover; since 2026-07-14 the script refuses to start
without it (`EEPHUS_ALLOW_COLD_REBUILD=1` overrides, producing a
knowingly-degraded site - production accidentally ran degraded like this
from 2026-07-11 to 2026-07-14).

Then force the FULL monthly pipeline on the very first run so every tracked
artifact is (re)built once from a clean pull, rather than a partial daily
refresh:

```
EEPHUS_FULL=1 /opt/eephus/repo/prospect-tracker/deploy/nightly-build.sh
```

(The script also picks FULL automatically on the 1st of the month.)

Verify the publish: `curl -s -A "Mozilla/5.0" https://eephus.io/data/build_info.json`
must show tonight's `generated_at` and the expected `git_sha`, and the
previously-404 modules (`/mlbstats/`, `/pal/`, `/trademachine/`, `/news/`,
`/report/`) must all return 200.

## 3. Initial webroot redeploy (production is stale)

Production nginx currently serves a stale hand-copied build. The first
successful nightly run is what replaces it: the rsync step writes the freshly
built site into `$WEBROOT` (default `/var/www/eephus.io`). Confirm after the
first run that the webroot timestamps advanced and the boot JSON under
`/data/` matches the new build. Until that first run lands, the live site is
whatever was last copied by hand, so treat launch day as "not live until the
first green nightly publishes".

## 4. nginx cache headers (change owned by WS-F4)

The server block that ships gzip_static plus the per-location cache headers is
documented in `deploy/README.md` (nginx server block section). Data payloads
are fetched with `?v=<stamp>` cache-busting so `/data/` can carry a long
`max-age`, while `/assets/` and `*.html` stay `no-cache` so a rebuild is picked
up on the next request. The actual header edit for launch is owned by WS-F4;
this runbook only references it. After any nginx config change:
`sudo nginx -t && sudo systemctl reload nginx`.

## 5. prospects.db nightly backup

`prospects.db` is the one piece of state that does not rebuild from scratch, so
back it up nightly with a consistent sqlite snapshot (safe to run while the DB
is live; `.backup` takes a proper copy). Add a second cron line a few minutes
before the build:

```
55 2 * * * TZ=America/New_York mkdir -p /opt/eephus/backups && sqlite3 /opt/eephus/repo/prospect-tracker/prospects.db ".backup /opt/eephus/backups/prospects-$(date +\%Y\%m\%d).db"
```

(The `%` signs must be backslash-escaped in a crontab.) Prune old copies on
whatever retention you want; a week or two is plenty.

## 6. editorial_eval forcing function (owner action, no longer a freeze)

UPDATED 2026-07-14. The standing-rule test
`test_phase4b_evals.py::test_editorial_artifact_withheld_until_matured` used to
hard-fail the moment the pipeline first wrote `data/editorial_eval.json` while
`spotlights_movement` was still `unvalidated` in the model registry - and
because the nightly gate blocks the rsync on ANY red test, that deliberately
froze all publishing until the owner registered a verdict. This is one of the
failure modes that (would have) kept production frozen after launch.

Behavior now: under `EEPHUS_DEPLOY_RUN=1` (the nightly box), the test SKIPS
with a loud "OWNER ACTION PENDING" message instead of failing, so the site
keeps publishing. In dev and CI (flag unset) it still hard-fails, so the
verdict cannot be forgotten indefinitely: the next local test run or push
after the artifact lands goes red until the registry is updated.

Action stands: when `data/editorial_eval.json` first appears (watch
`/opt/eephus/nightly.log` for the `editorial_eval: ... written=` line),
register the `spotlights_movement` verdict in the model registry and commit
it promptly - the nightly log will carry the skip warning until you do.

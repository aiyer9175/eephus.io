# Launch day (morning-of checklist)

The short list for the morning of launch (~2026-07-11). Assumes the nightly
nginx build is already installed (docs/prelaunch-2026-07/DEPLOY_RUNBOOK.md) and
the initial webroot redeploy has landed. Work top to bottom; if any step is red,
STOP and fix it before announcing. Deeper procedures live in DEPLOY_RUNBOOK.md;
this file is the checklist, not the manual.

## 1. Did the nightly run, pass the gate, and publish?

- `tail -n 80 /opt/eephus/nightly.log`: the most recent run ends with the
  step-summary block (`_log_step_summary`) and a GREEN suite. A RED suite means
  the test gate skipped the rsync, so the live site is whatever last published -
  do not announce on a red night.
- Confirm the webroot advanced: `ls -la /var/www/eephus.io` timestamps are from
  tonight, and the `/data/` boot JSON matches the new build.
- Boot stamp: the PROSPX boot probe reads `timeseries.json` `generated_at` (bytes
  0-2048); it should read today.

## 2. Freshness stamps on the site

- Load `/prospx/` and check the `data_freshness` stamp in the footer reads today
  (or within the expected daily window). A stale stamp means the nightly did not
  publish; go back to step 1.
- The pipeline run summary is embedded in `timeseries.json` (`run`, via
  `latest_run_summary()`), so a stale `generated_at` there is the machine-readable
  tell that publishing did not advance.

## 3. editorial_eval verdict (the deploy-freezing gate)

- Check whether `data/editorial_eval.json` appeared this run (watch the nightly.log
  `editorial_eval: ... written=` line).
- IF it appeared: the withheld-until-matured guard (`test_phase4b_evals.py`) is now
  RED and the nightly deploy is FROZEN (the gate blocks the rsync). Register the
  `spotlights_movement` verdict OFF `unvalidated` in the model registry and commit
  it the SAME DAY. Nothing publishes until you do. Full procedure:
  DEPLOY_RUNBOOK.md section 6.
- IF it did NOT appear yet: nothing to do; the first flag cohort has not matured.

## 4. Smoke the 5 flagship pages

Load each and confirm it renders with no error state, tables/grades populate, and
the browser console is clean:

- `/prospx/` - prospect board + eFV grades (open one player detail + one farm page)
- `/fa/` - Free Agency class board
- `/projections/` - MLB Projections + Team Outlook
- `/mlbstats/` - Bullpen / Starter / Hitter / Leverage leaderboards
- `/trademachine/` - trade board + one-currency deal evaluator

## 5. Where to look when something is stale

- Pipeline: `/opt/eephus/nightly.log` - the `_step` summary at the tail names the
  phase that failed or was skipped; a red suite there is what froze the rsync.
- Model freshness map: MODEL_REGISTRY.md `age (d)` / `stale` columns (the
  registry's own stamps, written by `model_registry.refresh_stamps()` on the
  pipeline cadence, STALE_DAYS = 240) plus `checked_at`. A stale flag is advisory,
  not a launch blocker.
- Data freshness: the `data_freshness` stamp on PROSPX + `timeseries.json`
  `generated_at` / run summary.
- If the site is UP but OLD: the nightly most likely went red (deploy frozen, last
  good build still served). Fix the suite, re-run `deploy/nightly-build.sh`, and
  confirm the webroot timestamps advanced.

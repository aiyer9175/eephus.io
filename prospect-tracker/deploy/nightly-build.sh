#!/usr/bin/env bash
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
#
# Server-side nightly build for eephus.io (Option 1: the nginx box IS the
# pipeline runner - no GitHub Pages, no Actions dependency).
#
# What it does, in order:
#   1. git pull (fast-forward only - a dirty or diverged tree aborts loudly)
#   2. pip-sync the venv against requirements.txt
#   3. run the pipeline: --daily most nights, the FULL monthly on the 1st
#   4. rebuild the editorial pages
#   5. gate on the test suite (a red suite leaves the live site untouched)
#   6. rsync the site files into the nginx webroot (atomic-ish: rsync
#      updates in place; pages reference data by ?v= stamps so a mid-sync
#      reader at worst sees one stale fetch)
#
# State that must persist on this box (the whole reason this option is
# more durable than CI runners): prospects.db, .cache/, data/pitch_plots/.
#
# Install (one time, as the deploy user):
#   sudo mkdir -p /opt/eephus && sudo chown "$USER" /opt/eephus
#   git clone https://github.com/aiyer9175/eephus.io.git /opt/eephus/repo
#   python3.12 -m venv /opt/eephus/venv
#   crontab -e   and add (03:10 ET nightly - inside the 2-4am window):
#     10 3 * * * TZ=America/New_York /opt/eephus/repo/prospect-tracker/deploy/nightly-build.sh >> /opt/eephus/nightly.log 2>&1
#   (If the box runs UTC and you skip TZ=, use `10 7 * * *` ~ 3:10 EDT.)
#
# nginx: point the site root at $WEBROOT below.

set -euo pipefail

REPO="${EEPHUS_REPO:-/opt/eephus/repo}"
APP="$REPO/prospect-tracker"
VENV="${EEPHUS_VENV:-/opt/eephus/venv}"
WEBROOT="${EEPHUS_WEBROOT:-/var/www/eephus.io}"
LOCK="/tmp/eephus-nightly.lock"

# Memory guardrails for low-RAM boxes (the ~6GB VPS was OOM-killed mid-build).
# Cap the statcast spawn ProcessPoolExecutor (the one pool whose RSS scales with
# worker count) and skip the pipeline's IN-PROCESS site rebuild - this script
# rebuilds the site in its own process below, so the pipeline needn't also do it
# inside its already-peaked heap. Raise EEPHUS_MAX_WORKERS if the box has RAM.
export EEPHUS_MAX_WORKERS="${EEPHUS_MAX_WORKERS:-3}"
export EEPHUS_SKIP_INPROC_BUILD="${EEPHUS_SKIP_INPROC_BUILD:-1}"

# SECRETS. Without this the nightly runs with an empty environment and every
# key-gated step is a silent no-op that looks perfectly healthy in the log.
# MEASURED 2026-08-05: this file had ZERO references to EEPHUS_ODDS_API_KEY, so
# run_daily step 9e ("betting odds snapshot") had never once fired on the box -
# data/betting_status.json reported `configured: true` (the key exists in the
# repo .env, which nothing loads) alongside `n_snapshots_cached: 0`. The betting
# module was not waiting on a data source; it was waiting on this line. The
# close-job crontab already sources the same file (deploy/betting-crontab.example)
# and only the nightly was missed.
# Root-owned, chmod 600, OUTSIDE the checkout - the deploy does `git checkout --`
# so a secrets file inside the repo would be destroyed nightly.
# shellcheck source=/dev/null
[ -r /etc/eephus.env ] && . /etc/eephus.env
if [ -z "${EEPHUS_ODDS_API_KEY:-}" ]; then
  echo "NOTE: EEPHUS_ODDS_API_KEY is unset - the odds snapshot (9e) will no-op." >&2
fi
# If it STILL OOM-kills, add swap (highest-leverage ops fix on a small box):
#   sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
#   sudo mkswap /swapfile && sudo swapon /swapfile
#   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date -Is) another nightly build is still running - skipping"
  exit 0
fi

echo "=== $(date -Is) nightly build start ==="
cd "$APP"

# ---------------------------------------------------------------------------
# Log capture (2026-07-31)
# ---------------------------------------------------------------------------
# The pipeline logs to STDOUT only, and logs/pipeline_latest.log was last
# written in May. That is how TJStats managed to write zero rows from
# 2026-07-08 to 2026-07-21 across seven completed runs with no trail: the
# only copy of the evidence was whatever the cron MAILTO/redirect happened to
# keep. Tee everything from here on into a dated file under logs/ plus a
# stable `pipeline_latest.log` symlink-equivalent, and rotate by COUNT so the
# directory cannot grow without bound on the small box.
#
# `exec > >(tee ...)` keeps stdout going to the cron redirect AS WELL, so
# /opt/eephus/nightly.log behaves exactly as before - this only ADDS a copy
# that lives with the app and rides nobody's mail spool.
LOG_DIR="${EEPHUS_LOG_DIR:-$APP/logs}"
LOG_KEEP="${EEPHUS_LOG_KEEP:-30}"
mkdir -p "$LOG_DIR"
RUN_LOG="$LOG_DIR/pipeline-$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "$RUN_LOG") 2>&1
# Stable filename for "what happened last night" without globbing. Copied
# rather than symlinked so a reader always gets a complete file even if the
# dated log is rotated away underneath them.
trap 'cp -f "$RUN_LOG" "$LOG_DIR/pipeline_latest.log" 2>/dev/null || true' EXIT
echo "--- logging to $RUN_LOG (keeping $LOG_KEEP runs)"
# Rotate: keep the newest $LOG_KEEP dated logs, delete the rest.
# `|| true` on the pipeline: with `set -o pipefail` a no-match glob makes ls
# exit non-zero, which would abort the whole nightly on a fresh box.
{ ls -1t "$LOG_DIR"/pipeline-*.log 2>/dev/null | tail -n +$((LOG_KEEP + 1)) \
    | while IFS= read -r old; do rm -f "$old"; done; } || true

# Staleness alarm: if the webroot hasn't been touched in 48h, something has
# been silently failing (red gate, dead cron) - say so loudly in the log.
if [ -f "$WEBROOT/index.html" ] && [ -n "$(find "$WEBROOT/index.html" -mtime +2 2>/dev/null)" ]; then
  echo "!!! WEBROOT STALE: $WEBROOT/index.html is older than 48h - previous nightlies did not publish. Check this log's history for the first failure."
fi

# The pipeline (below) rewrites TRACKED artifacts (data/xfv.json et al.) in place, so
# the tree is dirty when this run ends. Restore tracked files before pulling so the
# fast-forward can't abort on a dirty tree. Untracked state we deliberately keep
# (prospects.db, .cache/, data/pitch_plots/) is not touched by `checkout -- .`.
git -C "$REPO" checkout -- .
git -C "$REPO" pull --ff-only

# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -q -r requirements.txt

# A missing DB is NOT a normal cold start: prospects.db carries the 2021+
# snapshot history (grade lists, tool grades, Arkmetric/metric snapshots,
# IL history) that a re-scrape CANNOT recover - the archive backfills were
# one-time. Rebuilding cold silently produces a plausible-looking site
# with wrong FV history, consensus, and surplus numbers (this is what
# production served after 2026-07-11). Seed the canonical DB first (see
# deploy/README.md "Seeding the canonical database"), or opt into a
# knowingly-degraded rebuild with EEPHUS_ALLOW_COLD_REBUILD=1.
if [ ! -f prospects.db ] && [ "${EEPHUS_ALLOW_COLD_REBUILD:-}" != "1" ]; then
  echo "!!! prospects.db is MISSING. Refusing to cold-rebuild (it cannot recover"
  echo "!!! the 2021+ snapshot history and would publish wrong numbers)."
  echo "!!! Seed the canonical DB per deploy/README.md, or set"
  echo "!!! EEPHUS_ALLOW_COLD_REBUILD=1 to build a knowingly-degraded site."
  exit 1
fi

# Disk preflight. A disk-full MID-BUILD leaves a half-written data/*.json that
# then poisons the rsync'd deploy, so catch low disk BEFORE the hour-long build.
# The refetchable game/player caches (.cache/win_prob ~19GB, statcast_metrics,
# zone_metrics, ...) grow without bound; under pressure we reclaim from them
# (safe - everything there re-pulls from StatsAPI/Savant) and only then abort if
# still tight. Tunables: EEPHUS_DISK_MIN_GB (hard floor), EEPHUS_DISK_TARGET_GB
# (reclaim target). Set EEPHUS_DISK_MIN_GB=0 to disable (big-disk boxes).
DISK_MIN_GB="${EEPHUS_DISK_MIN_GB:-6}"
DISK_TARGET_GB="${EEPHUS_DISK_TARGET_GB:-12}"
if [ "$DISK_MIN_GB" != "0" ]; then
  FREE_GB="$(python tools/prune_cache.py --print-free 2>/dev/null || echo 999)"
  echo "--- disk preflight: ${FREE_GB} GB free (min ${DISK_MIN_GB}, target ${DISK_TARGET_GB})"
  if awk "BEGIN{exit !(${FREE_GB} < ${DISK_MIN_GB})}"; then
    echo "!!! LOW DISK - pruning the refetchable cache toward ${DISK_TARGET_GB} GB free"
    python tools/prune_cache.py --target-free-gb "$DISK_TARGET_GB" || true
    FREE_GB="$(python tools/prune_cache.py --print-free 2>/dev/null || echo 999)"
    echo "--- after prune: ${FREE_GB} GB free"
    if awk "BEGIN{exit !(${FREE_GB} < ${DISK_MIN_GB})}"; then
      echo "!!! STILL LOW DISK (${FREE_GB} GB < ${DISK_MIN_GB} GB) after cache prune."
      echo "!!! Aborting BEFORE the build to avoid a mid-write disk-full that would"
      echo "!!! corrupt the deploy. Free space (old /opt/eephus/backups, nightly.log)"
      echo "!!! and re-run, or lower EEPHUS_DISK_MIN_GB if this box is intentionally small."
      exit 1
    fi
  fi
fi

if [ "$(date +%d)" = "01" ] || [ "${EEPHUS_FULL:-}" = "1" ] || [ ! -f prospects.db ]; then
  echo "--- FULL monthly pipeline"
  MODE=full
  python run_monthly.py
else
  echo "--- daily refresh"
  MODE=daily
  python run_monthly.py --daily
fi

# Ingest health gate (report-only). run_monthly writes data/ingest_health.json
# with a `red` array naming any SCHEDULED grade source that wrote zero rows.
# We print it loudly here so it lands at the top of the nightly log rather
# than buried in the pipeline's own output, and so a `grep '!!! INGEST RED'`
# over logs/ answers "when did this source stop working?" in one command.
# Deliberately does NOT fail the build: a single dead source must not stop
# publishing the rest of the site.
if [ -f data/ingest_health.json ]; then
  python - <<'PY' || true
import json, pathlib
h = json.loads(pathlib.Path("data/ingest_health.json").read_text(encoding="utf-8"))
red = h.get("red") or []
by = {s["source"]: s for s in h.get("sources", [])}
if red:
    for src in red:
        s = by.get(src, {})
        print(f"!!! INGEST RED: {src} wrote 0 rows this run "
              f"(last OK {s.get('last_ok_at') or 'never'}) {s.get('message','')}")
else:
    print(f"--- ingest health OK ({len(h.get('sources', []))} sources checked)")
PY
else
  echo "!!! ingest health: data/ingest_health.json was not written by the pipeline"
fi

python build_site.py

# The gate: never sync a build the suite rejects. Browser-dependent tests
# skip themselves when playwright isn't installed on the box. EEPHUS_DEPLOY_RUN
# relaxes the dev-time exact-hash golden tripwires (xfv.json et al.) to shape
# checks, since this run legitimately regenerates those artifacts from fresh data.
EEPHUS_DEPLOY_RUN=1 python -m pytest -q

# Deploy heartbeat: a tiny sidecar the webmaster (and a curl one-liner) can
# check to confirm the nightly actually published. Written into the app's
# data/ so the normal rsync ships it; untracked, so the pre-pull
# `git checkout -- .` never sees it.
printf '{"generated_at":"%s","git_sha":"%s","mode":"%s"}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "$(git -C "$REPO" rev-parse --short HEAD)" \
  "$MODE" > data/build_info.json

# The include-list is the shared manifest deploy/publish_paths.txt (one
# source of truth with the GitHub workflow's staging step). Directories
# ship recursively, bare names ship as root files; data/ rides its own
# include rules below, minus deploy/data_exclude.txt (model internals no
# page fetches - excludes must precede the /data/*.json include because
# rsync applies the first matching rule).
echo "--- rsync -> $WEBROOT"
mkdir -p "$WEBROOT"
INCLUDES=()
while IFS= read -r p; do
  case "$p" in ''|\#*) continue ;; esac
  if [ -d "$APP/$p" ]; then
    INCLUDES+=("--include=/$p/***")
  else
    INCLUDES+=("--include=/$p")
  fi
done < "$APP/deploy/publish_paths.txt"
DATA_EXCLUDES=()
while IFS= read -r p; do
  case "$p" in ''|\#*) continue ;; esac
  DATA_EXCLUDES+=("--exclude=/data/$p")
done < "$APP/deploy/data_exclude.txt"
rsync -a --delete \
  "${INCLUDES[@]}" \
  "${DATA_EXCLUDES[@]}" \
  --include='/data/' --include='/data/*.json' --include='/data/*.js' \
  --include='/data/pitch_plots/***' --include='/data/player_detail/***' \
  --include='/data/debuts_full/***' \
  --exclude='*' \
  "$APP/" "$WEBROOT/"

# Publish-time comment strip (2026-07-23): the SHIPPED prospx page drops its
# dev comments (~630KB raw / ~265KB gz at introduction) while the SOURCE
# prospx/index.html keeps them - the tool only ever touches the webroot copy,
# AFTER the rsync and BEFORE the precompress so the .gz twin is built from
# the stripped file. Conservative by construction (tokenizer; own-line //
# + /* */ + <!-- --> only, strings/regex/styles untouched, Copyright kept)
# and fail-OPEN: a strip failure ships the commented copy rather than
# blocking the nightly (the tool writes atomically, so a failure never
# leaves a half-stripped page).
echo "--- strip prospx comments -> $WEBROOT/prospx/index.html"
python "$APP/tools/strip_prospx_comments.py" "$WEBROOT/prospx/index.html" --in-place \
  || echo "!!! prospx comment strip failed - shipping the commented copy"

# Precompress text assets so nginx (gzip_static on; see deploy/README.md)
# serves .gz next to the original with zero per-request CPU. The boot JSON
# compresses ~8-10x, which is most of the page-weight win on slow links.
# Only (re)compress when the source is newer than its .gz twin; prune
# orphaned .gz files so --delete'd sources don't leave stale compressed
# copies behind.
echo "--- precompress (gzip -9) -> $WEBROOT"
find "$WEBROOT" -type f \( -name '*.json' -o -name '*.js' -o -name '*.css' \
    -o -name '*.html' -o -name '*.svg' -o -name '*.xml' -o -name '*.txt' \) \
    -size +1k | while read -r f; do
  if [ ! -f "$f.gz" ] || [ "$f" -nt "$f.gz" ]; then
    gzip -9 -k -f "$f"
  fi
done
find "$WEBROOT" -type f -name '*.gz' | while read -r gz; do
  [ -f "${gz%.gz}" ] || rm -f "$gz"
done

echo "--- disk after build: $(python tools/prune_cache.py --print-free 2>/dev/null || echo '?') GB free"
echo "=== $(date -Is) nightly build done ==="

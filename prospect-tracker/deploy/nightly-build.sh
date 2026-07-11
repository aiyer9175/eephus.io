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

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date -Is) another nightly build is still running - skipping"
  exit 0
fi

echo "=== $(date -Is) nightly build start ==="
cd "$APP"

# The pipeline (below) rewrites TRACKED artifacts (data/xfv.json et al.) in place, so
# the tree is dirty when this run ends. Restore tracked files before pulling so the
# fast-forward can't abort on a dirty tree. Untracked state we deliberately keep
# (prospects.db, .cache/, data/pitch_plots/) is not touched by `checkout -- .`.
git -C "$REPO" checkout -- .
git -C "$REPO" pull --ff-only

# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -q -r requirements.txt

if [ "$(date +%d)" = "01" ] || [ "${EEPHUS_FULL:-}" = "1" ] || [ ! -f prospects.db ]; then
  echo "--- FULL monthly pipeline"
  python run_monthly.py
else
  echo "--- daily refresh"
  python run_monthly.py --daily
fi

python build_site.py

# The gate: never sync a build the suite rejects. Browser-dependent tests
# skip themselves when playwright isn't installed on the box. EEPHUS_DEPLOY_RUN
# relaxes the dev-time exact-hash golden tripwires (xfv.json et al.) to shape
# checks, since this run legitimately regenerates those artifacts from fresh data.
EEPHUS_DEPLOY_RUN=1 python -m pytest -q

echo "--- rsync -> $WEBROOT"
mkdir -p "$WEBROOT"
rsync -a --delete \
  --include='/index.html' --include='/404.html' \
  --include='/robots.txt' --include='/sitemap.xml' --include='/favicon.ico' \
  --include='/articles/***' --include='/assets/***' \
  --include='/collegesavant/***' --include='/fa/***' \
  --include='/forums/***' --include='/glossary/***' \
  --include='/player/***' --include='/projections/***' \
  --include='/prospx/***' --include='/sources/***' \
  --include='/team/***' --include='/teams/***' \
  --include='/report/***' --include='/vendor/***' \
  --include='/data/' --include='/data/*.json' \
  --include='/data/pitch_plots/***' --include='/data/player_detail/***' \
  --exclude='*' \
  "$APP/" "$WEBROOT/"

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

echo "=== $(date -Is) nightly build done ==="

#!/bin/bash
# Daily 2026 data refresh — runs at 6 AM ET (11 AM UTC)
# Logs to ~/swing_plus/logs/daily_refresh.log

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/logs/daily_refresh.log"
PY="$DIR/.venv/bin/python"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG"
cd "$DIR"
"$PY" refresh_2026.py >> "$LOG" 2>&1
echo "--- done ---" >> "$LOG"

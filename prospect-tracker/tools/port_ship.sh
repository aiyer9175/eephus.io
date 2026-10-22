#!/usr/bin/env bash
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
#
# eephus.io port (Strategy D): ship a verified served bundle to the box.
#
# A thin wrapper around tools/port_ship.py, which verifies the bundle, runs the
# two rsync calls over the restricted SSH user (READY last) and records the
# ship. Connection settings come from the local config file the owner fills
# (EEPHUS_PORT_SHIP_CONF, else ~/.eephus/port_ship.conf; template
# deploy/port_ship.conf.example), never from this repository.
#
# Usage (from prospect-tracker/):
#   tools/port_ship.sh --latest ../port_out/bundles [--dry-run]
#   tools/port_ship.sh --bundle ../port_out/bundles/<bundle-id> [--dry-run]

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE/.."
exec "${EEPHUS_PYTHON:-python}" "$HERE/port_ship.py" "$@"

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Freeze the preseason MLB projections, once, by hand.

docs/PROJ_FORWARD_VINTAGE_GATE.md section 2. Run on the day of the season's
first regular-season game, before first pitch, on the served projections file
of the last nightly (copy it from the box when the box served it), then commit
the folder and the hash literal in test_proj_forward_vintage.py by hand:

  python tools/freeze_proj_forward_vintage.py --season 2027
      --source <the served projections file> --source-label "box webroot"
      --first-game-pk <gamePk> --first-game-date 2027-03-25

  python tools/freeze_proj_forward_vintage.py --check

The first game is StatsAPI's earliest gameType R game of the season,
international openers included. The tool refuses a second freeze of a season,
a file whose first_season is not the season, and a file generated after the
first game. It never fetches anything and never runs in the nightly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import proj_forward_vintage as pfv  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="re-verify every logged hash and write nothing")
    ap.add_argument("--season", type=int)
    ap.add_argument("--source", type=Path)
    ap.add_argument("--source-label")
    ap.add_argument("--first-game-pk", type=int)
    ap.add_argument("--first-game-date")
    ap.add_argument("--vintage-dir", type=Path, default=pfv.VINTAGE_DIR)
    ap.add_argument("--label-provider",
                    help="the WAR series the bundle was trained on (default: the bundle meta's)")
    a = ap.parse_args(argv)
    if a.check:
        probs = pfv.check(a.vintage_dir)
        n = len(pfv.load_log(a.vintage_dir)["entries"])
        print(json.dumps({"entries": n, "problems": probs}, indent=1))
        return 1 if probs else 0
    missing = [k for k in ("season", "source", "source_label", "first_game_pk",
                           "first_game_date") if getattr(a, k) in (None, "")]
    if missing:
        ap.error("a freeze needs --" + ", --".join(m.replace("_", "-") for m in missing))
    entry = pfv.freeze(a.season, a.source, first_game_pk=a.first_game_pk,
                       first_game_date=a.first_game_date, source_label=a.source_label,
                       vintage_dir=a.vintage_dir, label_provider=a.label_provider)
    print(json.dumps({k: entry[k] for k in entry if k != "extract"}, indent=1))
    print(f"commit {a.vintage_dir} by hand and pin sha256 {entry['sha256']} "
          "in test_proj_forward_vintage.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

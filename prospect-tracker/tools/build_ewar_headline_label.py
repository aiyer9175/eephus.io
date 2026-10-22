# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Freeze the headline eWAR label vintage, data/ewar_headline_label.json (written ONCE).

    python tools/build_ewar_headline_label.py            # build and check, no write
    python tools/build_ewar_headline_label.py --write    # write once; refuses other content

docs/efv-2026-10-22/EWAR_HEADLINE_LABEL_GATE.md part 3 (identity 3 under amendment 9.1).
Reads only data/ewar_v3.json and the frozen fWAR vintage's id; never a feed. Every identity
is checked before anything is written.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ewar_headline_label as H   # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    try:
        payload = H.build(log=print)
    except H.EwarHeadlineLabelRefusal as e:
        print(f"REFUSED: {e}")
        return 2
    n = {k: sum(len(b[k]) for b in payload["seasons"].values()) for k in ("bat", "pit", "real_bat", "real_pit")}
    print(f"headline eWAR label {payload['vintage_id']}: headline departures bat {n['bat']}, pit {n['pit']}; "
          f"realized bat {n['real_bat']}, pit {n['real_pit']} (content_sha256 {payload['content_sha256']})")
    if a.write:
        try:
            path, how = H.write(payload)
        except H.EwarHeadlineLabelRefusal as e:
            print(f"REFUSED: {e}")
            return 3
        print(f"{how}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

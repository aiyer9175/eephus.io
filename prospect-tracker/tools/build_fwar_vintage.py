# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Freeze published fWAR per season into data/fwar_vintage.json.

    python tools/build_fwar_vintage.py --freeze 2000-2026            # PLAN: no network, no write
    python tools/build_fwar_vintage.py --freeze 2000-2026 --write    # fetch, then write once
    python tools/build_fwar_vintage.py --verify                      # hashes + field presence

fWAR label epoch, precondition E3 part 1 (docs/efv-2026-09-17/
FWAR_LABEL_EPOCH_GATE.md parts 3, 7 and 8). The rules live in fwar_vintage's
module docstring and are enforced there, not here: a frozen season is never
overwritten (--refreeze is the only way past it, and the epoch program never
passes it), an in-progress season is refused, the fetch goes straight to
StatsAPI and never through the .cache payloads, and a run that fails any call
writes nothing.

2000 to 2010 are the pre-2011 path of owner answer O4 (22 calls, no credits):
each calls pitching first, so the first call of a 2000-2026 run is the
pre-2011 pitching probe, and a clean empty answer is recorded as ABSENT with
the response it got (fwar_vintage rule 6); such a season is `mixed` and its
consumers stamp `war_basis: mixed`.

Since 2026-10-15 (EWAR_P0_VINTAGE_PA) every frozen hitting group also makes one
call to StatsAPI's season hitting line and keeps its plateAppearances, which the
sabermetrics feed does not carry (fwar_vintage.freeze_pa), so the next freeze
does not store that column null again.

Without --write the tool only PLANS: it names every season it would fetch, the
URLs, the call count and every refusal, and it touches neither the network nor
the file. The freeze itself is EPOCH_D9_FREEZE's step, not this tool's author's.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fwar_vintage as FV  # noqa: E402


def parse_seasons(spec: str) -> list[int]:
    """'2011-2026' or '2011,2013,2015-2016' -> a sorted list of seasons."""
    out: set[int] = set()
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-", 1))
            if hi < lo:
                raise ValueError(f"empty season range {part!r}")
            out.update(range(lo, hi + 1))
        else:
            out.add(int(part))
    if not out:
        raise ValueError(f"no season in {spec!r}")
    return sorted(out)


def plan_text(existing: dict | None, seasons: list[int], refreeze: bool, today=None) -> str:
    """What a --write run would do, with no network and no write."""
    import datetime as _dt
    today = today or _dt.date.today()
    frozen = {int(s) for s in ((existing or {}).get("seasons") or {})}
    lines = [f"fwar vintage plan ({len(seasons)} seasons, {FV.VINTAGE_PATH})"]
    n_calls = 0
    refused = []
    for s in seasons:
        ok, why = FV.season_complete(s, today)
        if s in frozen and not refreeze:
            refused.append(f"{s}: already frozen (never overwritten)")
        elif not ok:
            refused.append(f"{s}: {why}")
        else:
            order = FV._call_order(s)
            # one PA line per hitting group (2026-10-15); a pre-2011 hitting group
            # the feed answers empty makes no PA call, so this is the most a run makes
            n_calls += len(order) + 1
            lines.append(f"  {s}: " + ", ".join(
                f"{g} {FV.saber_feed.SABER_URLS[g].format(season=s)}" for g in order)
                + f", hitting PA line {FV.PA_LINE_URL.format(season=s)}")
    lines.append(f"  calls {n_calls} (at most)")
    if refused:
        lines.append("  REFUSED (a --write run refuses whole): " + "; ".join(refused))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--freeze", metavar="SEASONS",
                    help="seasons to freeze, e.g. 2011-2026 or 2011,2013")
    ap.add_argument("--write", action="store_true",
                    help="fetch every named season and write the vintage (all or nothing)")
    ap.add_argument("--refreeze", action="store_true",
                    help="allow overwriting a frozen season (the epoch program never uses this)")
    ap.add_argument("--verify", action="store_true",
                    help="recompute every hash on the file and print the field presence receipt")
    ap.add_argument("--out", type=Path, default=None,
                    help=f"vintage path (default {FV.VINTAGE_PATH})")
    args = ap.parse_args(argv)
    path = Path(args.out or FV.VINTAGE_PATH)
    existing = FV.load(path) if path.exists() else None

    if args.verify:
        if existing is None:
            print(f"no vintage at {path}")
            return 1
        probs = FV.verify(existing)
        print(json.dumps({"vintage_id": existing.get("vintage_id"),
                          "fwar_seasons": FV.fwar_seasons(existing),
                          "non_fwar_seasons": FV.mixed_seasons(existing),
                          "problems": probs,
                          "field_presence": FV.field_presence(existing)}, indent=1))
        return 0 if not probs else 2

    if not args.freeze:
        ap.error("--freeze SEASONS or --verify is required")
    seasons = parse_seasons(args.freeze)
    print(plan_text(existing, seasons, args.refreeze))
    if not args.write:
        print("\nPLAN ONLY: no network call was made and nothing was written. "
              "Pass --write to freeze.")
        return 0
    try:
        blob = FV.freeze_seasons(existing, seasons, refreeze=args.refreeze)
    except FV.FreezeError as exc:
        print(f"\nREFUSED, nothing written: {exc}")
        return 2
    probs = FV.verify(blob)
    if probs:
        print("\nREFUSED, nothing written: the built vintage fails its own hashes: "
              + "; ".join(probs))
        return 2
    FV.write(blob, path)
    print(f"\nwrote {path} vintage_id {blob['vintage_id']}")
    for s in seasons:
        sb = blob["seasons"][str(s)]
        print(f"  {s} {sb.get('basis')} fetched_at {sb.get('fetched_at')} "
              + " ".join(f"{g} {sb[g]['status']} rows {sb[g]['n_rows']}" for g in FV.GROUPS))
    return 0


if __name__ == "__main__":
    sys.exit(main())

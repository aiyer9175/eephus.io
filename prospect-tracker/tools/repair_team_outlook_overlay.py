"""Re-apply the current-season overlay to the served team outlook.

WHY THIS EXISTS RATHER THAN A FULL REBUILD. `data/mlb_projections.json` was written
while `standings_now()` silently dropped Arizona: StatsAPI calls the club "D-backs",
the name resolver passed that through unchanged, and the `len(org) <= 3` guard
skipped the row. Arizona was the only one of thirty clubs carrying `current: None`,
and because `_attach_current_season` also runs the playoff simulation, EVERY club's
wild-card odds were computed on a field with a 75-68 contender deleted.

The resolver is fixed. The artifact is not, and a resolver fix does not repair a file
that was already written wrong.

A full `proj_export` rebuild would repair it and would also move the 2027 projection,
the prospect dollars and the surplus numbers, none of which have anything to do with
this defect. This tool calls proj_export's OWN overlay function on the served rows
instead, which is the same code the nightly runs, and touches only the `current`
block and the simulation that depends on it.

IDEMPOTENT. Running it twice changes nothing the second time. It stamps what it did
onto the artifact so the repair is auditable rather than invisible.

Offline: `standings_now` reads the disk-cached StatsAPI payload.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ART = ROOT / "data" / "mlb_projections.json"

log = logging.getLogger("repair_team_outlook_overlay")


def repair(*, path: Path | None = None, write: bool = True) -> dict:
    import proj_export
    from fa_fit_backtest import standings_now

    p = Path(path or ART)
    doc = json.loads(p.read_text(encoding="utf-8"))
    rows = doc.get("team_outlook") or []
    if not rows:
        return {"ok": False, "why": "no team_outlook block in the artifact"}

    season = proj_export.FIRST_SEASON - 1
    before_null = sorted(r.get("team") for r in rows if r.get("current") is None)
    before_odds = {r.get("team"): (r.get("current") or {}).get("wildcardPct")
                   for r in rows}

    sn = standings_now(season)
    if not sn:
        return {"ok": False, "why": f"standings_now({season}) returned nothing; "
                                    "refusing to blank the overlay"}
    if len(sn) < 30:
        return {"ok": False, "why": f"standings_now({season}) resolved only "
                                    f"{len(sn)} clubs; the resolver is still "
                                    "dropping somebody and re-applying the "
                                    "overlay now would bake that in"}

    sched = proj_export._attach_current_season(
        rows, sn, il_out60=proj_export._il_out60(season), season=season)

    after_null = sorted(r.get("team") for r in rows if r.get("current") is None)
    after_odds = {r.get("team"): (r.get("current") or {}).get("wildcardPct")
                  for r in rows}
    moved = {t: (before_odds.get(t), after_odds.get(t))
             for t in after_odds
             if before_odds.get(t) != after_odds.get(t)}

    stamp = {
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "by": "tools/repair_team_outlook_overlay.py",
        "season": season,
        "clubs_resolved": len(sn),
        "null_current_before": before_null,
        "null_current_after": after_null,
        "wildcard_pct_moved_for": sorted(moved),
        "why": (
            "the club resolver was matching StatsAPI names, which have changed "
            "three times (D-backs, Indians, Expos), and the len<=3 guard then "
            "dropped whatever it failed to map. Arizona was missing from the "
            "field the playoff simulation ran on, so every club's wild-card "
            "odds were computed without a 75-68 contender."),
    }
    doc.setdefault("overlay_repairs", []).append(stamp)
    if sched is not None:
        doc["mc_schedule_source"] = sched
    if write:
        p.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return {"ok": True, "stamp": stamp, "moved": moved, "schedule_source": sched}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")
    out = repair(write="--dry-run" not in argv)
    if not out["ok"]:
        print("REFUSED:", out["why"])
        return 1
    s = out["stamp"]
    print(f"clubs resolved: {s['clubs_resolved']}")
    print(f"null current BEFORE: {s['null_current_before'] or 'none'}")
    print(f"null current AFTER : {s['null_current_after'] or 'none'}")
    print(f"schedule source: {out['schedule_source']}")
    print(f"wild-card odds moved for {len(out['moved'])} clubs")
    for t, (b, a) in sorted(out["moved"].items())[:12]:
        print(f"   {t}: {b} -> {a}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

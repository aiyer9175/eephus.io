# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""draft_anchor_backfill.py -- give already-active pros their real, already-owned
pre-draft board grade.

THE PROBLEM (measured 2026-07-25 against prospects.db + data/xfv.json):
  2,624 of 4,477 active board players (58.6%) carry NO real scouting anchor. Their
  only explicit-FV snapshot is the synthetic `performance_ingest` stamp, a flat
  FV 35.0 constant. 2,577 of them therefore serve consensus_fv == 35.0 exactly,
  and 2,214 sit pinned at the served eFV floor (77% of the 2,879-player floor).

WHAT THIS MODULE DOES:
  Some of those players were graded before they signed. `draft_snapshots` already
  holds 2,839 draft-board FVs from fangraphs / mlb_pipeline_draft / espn_draft, and
  `draft_canonical_keys` already links the draft key to the professional key. But
  `draft_promotion.seed_signed_draftees` only seeds the CURRENT year's class
  ("never resurrect old draftees"), so a 2019-2025 signee who never made an org
  Top 30 keeps a synthetic constant while his real published grade sits unused one
  join away.

  This backfill lifts exactly that, under a guard that keeps the "no resurrection"
  rule intact: a prior-class draftee is seeded ONLY if he is ALREADY an active
  tracked player. Nothing is created, nothing is resurrected, and no grade is
  invented -- the FV written is the mean of the LATEST FV per draft source, the
  same `_draft_board_consensus_fv` the current-class seeder uses, and it is dated
  at the board's own snapshot_date (NOT today) so anchor staleness stays honest.

MEASURED YIELD (2026-07-25, paired same-run re-score of the whole live board:
efv_score.run_live both sides + efv_export.run, baseline and treated captured in
one session, matrices restored byte-identical afterwards):
  candidates                        71
  served eFV grades that moved      66  (the 5 non-movers grade to FV 35.0
                                         exactly, i.e. no change by construction)
  left the served eFV floor         44  treated, plus 22 displaced off it by the
                                         rank re-sort; 0 joined
  treated delta (served grade)      min +1.6, p25 +4.3, median +5.0, p75 +5.1,
                                         max +10.0, mean +5.4
  collateral (rank re-sort)        197 players, median +0.1, range -0.7..+1.6,
                                         19 at |delta| > 0.5

  This is a COVERAGE result, not a model-accuracy claim: it moves 71 players off a
  fabricated constant and onto their own published grade. No eFV accuracy gain is
  claimed or measured here (the population is far too small to resolve against the
  docs/EFV_GATE_STANDARD.md floors) and none should be inferred.

SCOPE NOTE (the honest null this module documents):
  MLB Pipeline org Top 30 CANNOT close the remaining gap. Verified live
  2026-07-25 against data-graph.mlb.com (HTTP 200, 30/30 orgs, 900 unique MLBAM
  ids, samples in .cache/anchor_probe/): 899 of those 900 already carry a real
  anchor. Exactly ONE org-Top-30 player is in the 2,624 gap. A 30-id sample of
  the gap cohort returned a Pipeline player entity for 5, an ETA for 0 and a
  grade for 0. Pipeline does not carry these players; the org-list lane is
  exhausted, not under-ingested.

Run: python draft_anchor_backfill.py [--apply] [--limit N]
"""

from __future__ import annotations

import logging
from datetime import date

log = logging.getLogger(__name__)

# Sources that carry NO published grade information.
#   performance_ingest -- the auto-discovery stamp: a flat FV 35.0 constant,
#                         identical for every player it touches.
#   auto_detect        -- a debut / roster tracker, never an FV publication.
# NOTE `draft_signing` is deliberately NOT here. grade_normalization lists it
# among _SYNTHETIC_SOURCES, but that flag means "pass the scale through raw,
# never quantile-map it" -- the VALUE is a real published draft-board FV. A
# player already carrying a draft_signing row therefore has a real anchor and
# must not be counted in the anchor gap (measured 2026-07-25: all 49 current-
# class draftees that look gap-like under the looser definition are already
# serving consensus 36.7-41.7 off that row, not the 35.0 constant).
SYNTHETIC_SOURCES = ("performance_ingest", "auto_detect")

MIN_DRAFT_YEAR = 2015          # older classes are graduated or long gone
SOURCE_LABEL = "draft_signing"  # same synthetic-passthrough lane as the current
                                # class: grade_normalization must not quantile-map
                                # a draft-board scale onto the pro scale


def _active_board_keys() -> set[str]:
    """player_keys the site currently serves as ACTIVE prospects.

    Read from the served eFV artifact so the guard is anchored on what the board
    actually shows, not on a roster heuristic. Empty set = refuse to seed."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parent / "data" / "xfv.json"
    try:
        bp = (json.loads(p.read_text(encoding="utf-8")) or {}).get("by_player") or {}
    except (OSError, ValueError) as exc:
        log.warning("draft_anchor_backfill: cannot read %s (%s)", p, exc)
        return set()
    return {k for k, v in bp.items() if v.get("kind") == "active"}


def find_candidates(limit: int | None = None) -> list[dict]:
    """Prior-class signed draftees who are active today and whose ONLY explicit-FV
    snapshot source is synthetic. Pure read; no writes."""
    from storage import connect

    active = _active_board_keys()
    if not active:
        log.warning("draft_anchor_backfill: no active board keys -- refusing to seed")
        return []

    cur_year = date.today().year
    out: list[dict] = []
    with connect() as con:
        con.row_factory = __import__("sqlite3").Row
        # keys with a synthetic anchor and no real one
        synth_only = {
            r["player_key"] for r in con.execute(
                f"""SELECT player_key,
                           SUM(CASE WHEN source IN {SYNTHETIC_SOURCES} THEN 1 ELSE 0 END) AS syn,
                           SUM(CASE WHEN source NOT IN {SYNTHETIC_SOURCES} THEN 1 ELSE 0 END) AS real
                      FROM snapshots
                     WHERE fv IS NOT NULL
                  GROUP BY player_key"""
            ) if r["syn"] and not r["real"]
        }
        canon = {r["draft_key"]: r["milb_key"] for r in con.execute(
            "SELECT draft_key, milb_key FROM draft_canonical_keys WHERE milb_key IS NOT NULL")}

        # latest FV per (draft_key, source) + the board's own date
        boards: dict[str, dict[str, float]] = {}
        bdate: dict[str, str] = {}
        for r in con.execute(
            """SELECT player_key, source, fv, snapshot_date
                 FROM draft_snapshots
                WHERE fv IS NOT NULL
             ORDER BY snapshot_date"""
        ):
            boards.setdefault(r["player_key"], {})[r["source"]] = float(r["fv"])
            bdate[r["player_key"]] = r["snapshot_date"]

        # earliest SIGNED year per pro key -- the same name-collision guard
        # seed_signed_draftees uses (an earlier signed pick owns the key).
        earliest: dict[str, int] = {}
        rows = [dict(r) for r in con.execute(
            "SELECT player_key, player_name, draft_year, signed, team FROM draft_results")]

    from draft_promotion import _milb_key_from_name
    for r in rows:
        if not r.get("signed"):
            continue
        mk = canon.get(r["player_key"]) or _milb_key_from_name(r.get("player_name") or "")
        y = r.get("draft_year") or 0
        if mk and (mk not in earliest or y < earliest[mk]):
            earliest[mk] = y

    best: dict[str, dict] = {}
    for r in rows:
        dk, y = r["player_key"], (r.get("draft_year") or 0)
        if not r.get("signed") or not r.get("team") or not dk:
            continue
        if y >= cur_year or y < MIN_DRAFT_YEAR:
            continue                    # current class is seed_signed_draftees' job
        mk = canon.get(dk) or _milb_key_from_name(r.get("player_name") or "")
        if not mk or mk not in active or mk not in synth_only:
            continue                    # not active today, or already really anchored
        if earliest.get(mk, y) < y:
            continue                    # an earlier signed pick owns this identity
        grades = boards.get(dk)
        if not grades:
            continue                    # never board-graded -- nothing honest to seed
        rec = {
            "player_key":   mk,
            "player_name":  r.get("player_name"),
            "draft_key":    dk,
            "draft_year":   y,
            "team":         r.get("team"),
            "fv":           round(sum(grades.values()) / len(grades), 1),
            "n_sources":    len(grades),
            "board_date":   bdate.get(dk),
        }
        prev = best.get(mk)
        if prev is None or y > prev["draft_year"]:
            best[mk] = rec

    out = sorted(best.values(), key=lambda x: (x["draft_year"], x["player_key"]))
    return out[:limit] if limit else out


def build(apply: bool = False, limit: int | None = None) -> dict:
    """Report (and optionally write) the backfill seeds. Idempotent: the
    (source, interval_label, player_key) upsert rewrites in place."""
    cands = find_candidates(limit)
    summary = {
        "candidates": len(cands),
        "above_floor": sum(1 for c in cands if c["fv"] > 35.0),
        "by_year": {},
        "written": 0,
        "applied": bool(apply),
    }
    for c in cands:
        summary["by_year"][str(c["draft_year"])] = summary["by_year"].get(str(c["draft_year"]), 0) + 1

    if apply and cands:
        from scrapers import Snapshot
        from storage import insert_snapshots
        try:
            from trades import canonical_org
        except ImportError:
            canonical_org = lambda t: t  # noqa: E731
        seeds = [Snapshot(
            source        = SOURCE_LABEL,
            # the board's OWN date, never today: an anchor must not claim to be
            # fresher than the observation behind it (efv_dataset's staleness
            # ramp reads exactly this field).
            snapshot_date = c["board_date"],
            interval_label= f"{c['draft_year']} Draft Class",
            player_key    = c["player_key"],
            player_name   = c["player_name"],
            position      = None,
            org           = canonical_org(c["team"]) or c["team"],
            rank          = None,
            fv            = float(c["fv"]),
            status        = "active",
        ) for c in cands]
        summary["written"] = insert_snapshots(seeds)

    log.info("draft_anchor_backfill: %s", summary)
    return summary


if __name__ == "__main__":
    import argparse, json, sys
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write the seeds (default: report only)")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    print(json.dumps(build(apply=args.apply, limit=args.limit), indent=2))

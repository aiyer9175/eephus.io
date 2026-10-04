# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""College source probe: a COUNT-ONLY coverage receipt for the one family the
screening lab could not screen for lack of a source (EFV3_B9; EFV3_PLAN.md s4
"Families with no vintage-matched source", LANE_B.md F-B10 and s7, EFV_V2_GATE.md
s10.14; lane B owner question E3-Q24, option A taken by default per the s9 unifier
note).

What it does, and all it does:

1. The fetch. amateur_leagues.season_splits (the module's own fetch path, the one
   that wrote the 2021 and later files) is called once per (sport, group, season) for
   sportId 22 (the StatsAPI amateur family: college, Cape Cod, Appalachian, MLB Draft
   League) and sportId 17 (the winter family: AFL and the Caribbean circuits; the task
   spec's second id) over the seasons 2005 to 2020. Each call lands
   .cache/amateur_leagues/<group>_<sport>_<season>.json exactly as the 2021+ files
   (an empty season is cached as []). A failed call is logged and counted as zero
   rows; nothing raises. amateur_leagues.build is NOT called: it lands
   data/_labs/amateur_leagues.json, and no file under data/ may move here but the receipt.

2. The receipt, data/college_source_probe.json. Per season, sport and group: the row
   count, the distinct player count and the league breakdown. Then, on the F-LV
   development frame (efv_vintage_frame.build_frame, V 2011 to 2019, the reserved
   guard called first, R-VM pins asserted empty), the share of is_college rows whose
   OUTCOME-BLIND mlbam_id carries a sport-22 line in a season strictly below the
   draft year (acq_year, which the frame only exposes when it is before V), by side
   and vintage. The receipt also records frame_counts for every (side, V) it built,
   verbatim, so the frame it read is the frame every other receipt reads.

What it never does: no stat is read off a line (only mlbam, season and league are
touched), nothing is joined to a label, a grade, a WAR or a debut, no correlation, no
fit, no feature column, no FV cell (docs/PROSPECT_ANCHOR_GATE.md), no reserved vintage
(R-LV 2020, 2021) and no 2025+ debut cohort. If the feed returns 0 splits before 2021
the receipt says so and the college family stays "no source" in the gate's s10.14
table.

Run:  python tools/college_source_probe.py             (fetches, writes the receipt)
      python tools/college_source_probe.py --no-fetch  (cache only, writes the receipt)
      python tools/college_source_probe.py --dry-run   (prints, writes nothing)
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import amateur_leagues as AL  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

log = logging.getLogger(__name__)

OUT = ROOT / "data" / "college_source_probe.json"
#: The seasons the probe asks for: the first season on disk for every affiliated sport
#: id (2005) up to the last season the 2021+ cache does not cover.
PROBE_SEASONS: tuple[int, ...] = tuple(range(2005, 2021))
#: The two sport ids the task names (amateur_leagues.SPORT_LABEL carries the family).
PROBE_SPORTS: tuple[int, ...] = (22, 17)
GROUPS: tuple[str, ...] = ("hitting", "pitching")
#: The sport id a "college line" is read from (CBB, CCBL, APP, MLBDL sit under it).
COLLEGE_SPORT = 22
#: The only fields this tool reads off a cached line.
LINE_KEYS: tuple[str, ...] = ("mlbam", "season", "league")
GROUP_OF_SIDE = {"hit": "hitting", "pit": "pitching"}


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------

def guards() -> dict:
    """The reserved guard must raise for every R-LV vintage; the R-VM pins must be
    empty; the vintages read are the development vintages and nothing else."""
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    for V in sorted(F.RESERVED_LV):
        try:
            F.guard_score_request(V, purpose="college source probe")
        except F.ReservedFrameError:
            continue
        raise F.ReservedFrameError(f"the reserved guard did not raise for {V}")
    assert not (set(F.DEV_VINTAGES) & F.RESERVED_LV)
    return {"reserved_lv": sorted(F.RESERVED_LV),
            "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
            "vintages_read": list(F.DEV_VINTAGES), "reserved_vm_pins": pins}


# ---------------------------------------------------------------------------
# 1. the fetch (counts only)
# ---------------------------------------------------------------------------

def _cache_path(group: str, sport: int, season: int) -> Path:
    return AL.CACHE_DIR / f"{group}_{sport}_{season}.json"


def line_counts(rows: list[dict]) -> dict:
    """Row count, distinct players and the league breakdown of one cached file. Only
    LINE_KEYS are read; no stat field is touched."""
    players: set[int] = set()
    leagues: dict[str, int] = {}
    for r in rows:
        mid = r.get("mlbam")
        if mid is not None:
            players.add(int(mid))
        lg = str(r.get("league") or "unknown")
        leagues[lg] = leagues.get(lg, 0) + 1
    return {"rows": len(rows), "players": len(players),
            "leagues": {k: leagues[k] for k in sorted(leagues)}}


def fetch_counts(fetch: bool = True, seasons=PROBE_SEASONS, sports=PROBE_SPORTS) -> dict:
    """One season_splits call per (sport, group, season), fail-soft: a failed or empty
    call is a zero row, never an exception. Returns by_season[season][sport][group]."""
    out: dict = {}
    for season in seasons:
        for sport in sports:
            for group in GROUPS:
                err = None
                try:
                    rows = AL.season_splits(int(sport), int(season), group, fetch=fetch)
                except Exception as e:                            # noqa: BLE001
                    log.warning("college_source_probe %s/%s/%s failed: %s",
                                group, sport, season, e)
                    rows, err = [], f"{type(e).__name__}: {e}"
                rec = line_counts(rows or [])
                rec["cached"] = _cache_path(group, int(sport), int(season)).exists()
                rec["fetch_error"] = err
                out.setdefault(str(season), {}).setdefault(str(sport), {})[group] = rec
    return out


def season_summary(by_season: dict, sports=PROBE_SPORTS) -> dict:
    """Per sport: rows by season, the first populated season, whether every probed
    season is empty, and which fetches failed."""
    out: dict = {}
    for sport in sports:
        rows_by_season = {}
        failed = []
        for season, per_sport in by_season.items():
            groups = (per_sport.get(str(sport)) or {})
            rows_by_season[season] = sum(int(c.get("rows") or 0) for c in groups.values())
            failed.extend(f"{g}_{sport}_{season}" for g, c in groups.items()
                          if c.get("fetch_error"))
        populated = sorted(int(s) for s, n in rows_by_season.items() if n > 0)
        out[str(sport)] = {
            "label": AL.SPORT_LABEL.get(int(sport), str(sport)),
            "rows_by_season": {s: rows_by_season[s] for s in sorted(rows_by_season)},
            "rows_total": sum(rows_by_season.values()),
            "first_populated_season": populated[0] if populated else None,
            "populated_seasons": populated,
            "all_probed_seasons_empty": not populated,
            "fetch_failures": sorted(failed),
        }
    return out


# ---------------------------------------------------------------------------
# 2. the frame read (counts only)
# ---------------------------------------------------------------------------

def college_lines(seasons=PROBE_SEASONS) -> dict[str, dict[int, set[int]]]:
    """{group: {mlbam: {seasons with a sport-22 line}}} over the probed seasons, cache
    only (fetch=False; a missing file is empty). Only LINE_KEYS are read."""
    out: dict[str, dict[int, set[int]]] = {g: {} for g in GROUPS}
    for season in seasons:
        for group in GROUPS:
            for r in AL.season_splits(COLLEGE_SPORT, int(season), group, fetch=False) or []:
                mid = r.get("mlbam")
                if mid is None:
                    continue
                out[group].setdefault(int(mid), set()).add(int(r.get("season") or season))
    return out


def _share(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def coverage_block(rows: list[dict], side: str, lines: dict) -> dict:
    """The receipt for one (side, V): how many is_college rows carry a college line
    below their draft year. Counts and shares, nothing else."""
    group = GROUP_OF_SIDE[side]
    other = [g for g in GROUPS if g != group][0]
    college = [r for r in rows
               if float(r.get("is_college") or 0.0) == 1.0 and r.get("acq_year") is not None]
    with_id = [r for r in college if r.get("mlbam_id") is not None]
    draft_years: dict[int, int] = {}
    for r in college:
        y = int(r["acq_year"])
        draft_years[y] = draft_years.get(y, 0) + 1

    def _has(r: dict, g: str, below: bool) -> bool:
        seasons = lines.get(g, {}).get(int(r["mlbam_id"]), set())
        if not below:
            return bool(seasons)
        return any(int(s) < int(r["acq_year"]) for s in seasons)

    below_same = sum(1 for r in with_id if _has(r, group, True))
    below_any = sum(1 for r in with_id if _has(r, group, True) or _has(r, other, True))
    any_season = sum(1 for r in with_id if _has(r, group, False) or _has(r, other, False))
    return {
        "rows": len(rows),
        "is_college_rows": len(college),
        "is_college_with_id": len(with_id),
        "draft_years": {str(y): draft_years[y] for y in sorted(draft_years)},
        "with_college_line_below_draft_year": {
            "same_group": below_same, "either_group": below_any},
        "share_of_is_college_rows": {
            "same_group": _share(below_same, len(college)),
            "either_group": _share(below_any, len(college))},
        "share_of_is_college_with_id": {
            "same_group": _share(below_same, len(with_id)),
            "either_group": _share(below_any, len(with_id))},
        "with_college_line_any_probed_season": any_season,
    }


def frame_coverage(universe: dict | None = None, lines: dict | None = None,
                   vintages=F.DEV_VINTAGES) -> tuple[dict, dict]:
    """(frame_counts, coverage) by side and vintage, from ONE build per (side, V):
    frame_counts is exactly what efv_vintage_frame.frame_counts reports for the
    same universe (rows, with_consensus, with_milb), and coverage is coverage_block."""
    import source_backtest as SB
    universe = universe if universe is not None else F.load_universe()
    lines = lines if lines is not None else college_lines()
    counts: dict = {}
    cov: dict = {}
    for side in F.SIDES:
        for V in vintages:
            F.guard_score_request(V, purpose="college source probe")
            rows = F.build_frame(side, V, universe=universe)
            counts.setdefault(side, {})[int(V)] = {
                "rows": len(rows),
                "with_consensus": sum(1 for r in rows
                                      if r["grades"].get(SB.CONSENSUS_KEY) is not None),
                "with_milb": sum(1 for r in rows if r.get("milb")),
            }
            cov.setdefault(side, {})[str(V)] = coverage_block(rows, side, lines)
    return counts, cov


def totals(cov: dict) -> dict:
    out = {}
    for side, by_v in cov.items():
        blocks = list(by_v.values())
        n_col = sum(b["is_college_rows"] for b in blocks)
        n_id = sum(b["is_college_with_id"] for b in blocks)
        same = sum(b["with_college_line_below_draft_year"]["same_group"] for b in blocks)
        either = sum(b["with_college_line_below_draft_year"]["either_group"] for b in blocks)
        out[side] = {
            "rows": sum(b["rows"] for b in blocks),
            "is_college_rows": n_col,
            "is_college_with_id": n_id,
            "with_college_line_below_draft_year": {"same_group": same, "either_group": either},
            "share_of_is_college_rows": {"same_group": _share(same, n_col),
                                         "either_group": _share(either, n_col)},
            "with_college_line_any_probed_season": sum(
                b["with_college_line_any_probed_season"] for b in blocks),
        }
    return out


def family_status(summary: dict, tot: dict, cov_by_vintage: dict) -> dict:
    """The count-only reading the gate's s10.14 row records: 'no source' unless some
    development row carries a college line below its draft year."""
    s22 = summary[str(COLLEGE_SPORT)]
    covered = sum(t["with_college_line_below_draft_year"]["either_group"]
                  for t in tot.values())
    n_college = sum(t["is_college_rows"] for t in tot.values())
    populated = s22["populated_seasons"]
    by_v = {side: {V: b["with_college_line_below_draft_year"]["either_group"]
                   for V, b in cov.items()
                   if b["with_college_line_below_draft_year"]["either_group"]}
            for side, cov in cov_by_vintage.items()}
    if s22["all_probed_seasons_empty"]:
        status = "no source"
        why = ("StatsAPI sportId 22 returned 0 splits for every probed season 2005 to "
               "2020; the college family stays 'no source' in EFV_V2_GATE.md s10.14")
    elif covered == 0:
        status = "source present before 2021, no development row covered"
        why = (f"sportId 22 returned rows for {populated} but no F-LV development row "
               f"(V 2011 to 2019) carries a college line in a season below its draft "
               f"year")
    else:
        status = (f"source present before 2021; development coverage {covered} of "
                  f"{n_college} is_college rows ({_share(covered, n_college)})")
        why = (f"sportId 22 returned rows for {populated} (rows by season in "
               f"season_summary); {covered} of {n_college} F-LV development is_college "
               f"rows carry a college line below their draft year, at {by_v}")
    return {"status": status, "why": why,
            "sport22_populated_seasons": populated,
            "sport22_rows_by_season": s22["rows_by_season"],
            "dev_is_college_rows": n_college,
            "dev_rows_with_prior_college_line": covered,
            "dev_rows_with_prior_college_line_by_vintage": by_v,
            "reserved_note": ("list vintages 2020 and 2021 are R-LV and were not built; "
                              "nothing here reads them")}


def _commit() -> str | None:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip() or None
    except OSError:
        return None


def run(fetch: bool = True, universe: dict | None = None) -> dict:
    g = guards()
    by_season = fetch_counts(fetch=fetch)
    summary = season_summary(by_season)
    lines = college_lines()
    counts, cov = frame_coverage(universe=universe, lines=lines)
    tot = totals(cov)
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "produced_by": "tools/college_source_probe.py",
        "role": "development",
        "adjudicates": ("nothing; a count-only coverage receipt for the college "
                        "production family (EFV3_B9, lane B E3-Q24 option A by default); "
                        "no stat read, no label, no correlation, no fit, no feature"),
        "what": ("StatsAPI sportId 22 and 17 season splits 2005 to 2020 through "
                 "amateur_leagues.season_splits (cached beside the 2021+ files), and "
                 "the share of F-LV development is_college rows whose outcome-blind "
                 "mlbam_id has a sport-22 line in a season below the draft year"),
        "probe": {
            "seasons": list(PROBE_SEASONS),
            "sports": {str(s): AL.SPORT_LABEL.get(s, str(s)) for s in PROBE_SPORTS},
            "sport_note": ("22 is the amateur family (CBB, CCBL, APP, MLBDL); 17 is the "
                           "winter family (AFL, LIDOM, LMP, LVBP, PWL, CS, ABL), the "
                           "second id the task names"),
            "groups": list(GROUPS),
            "calls": len(PROBE_SEASONS) * len(PROBE_SPORTS) * len(GROUPS),
            "fetch_enabled": bool(fetch),
            "fail_soft": True,
            "cache_pattern": ".cache/amateur_leagues/<group>_<sport>_<season>.json",
            "line_keys_read": list(LINE_KEYS),
            "data_amateur_leagues_json_untouched": True,
        },
        "guards": g,
        "code": {"commit": _commit()},
        "by_season": by_season,
        "season_summary": summary,
        "frame_counts": {s: {str(v): counts[s][v] for v in sorted(counts[s])}
                         for s in counts},
        "college_coverage": {
            "rule": ("is_college rows (acquisition method draft, age 21 or more in the "
                     "draft year, known before V) whose outcome-blind mlbam_id has a "
                     "sport-22 line in a season strictly below acq_year; same_group reads "
                     "the side's group, either_group reads both"),
            "by_vintage": cov,
            "totals": tot,
        },
        "family_status": family_status(summary, tot, cov),
        "not_in_efv_progress": "no score is read here; nothing enters any ledger",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    doc = run(fetch=not args.no_fetch)
    for sport, s in doc["season_summary"].items():
        print(f"sport {sport} ({s['label']}): rows {s['rows_total']} first populated "
              f"{s['first_populated_season']} failed {len(s['fetch_failures'])}")
        print("  by season:", json.dumps(s["rows_by_season"]))
    for side in F.SIDES:
        for V, b in doc["college_coverage"]["by_vintage"][side].items():
            w = b["with_college_line_below_draft_year"]
            print(f"{side} {V}: rows {b['rows']} is_college {b['is_college_rows']} "
                  f"with_id {b['is_college_with_id']} prior college line "
                  f"{w['same_group']} / {w['either_group']}")
    print("totals:", json.dumps(doc["college_coverage"]["totals"]))
    print("family:", doc["family_status"]["status"])
    if not args.dry_run:
        OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

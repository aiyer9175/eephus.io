# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""W2 PARK-LINE: in-house MiLB park-factor neutralization for eFV stat lines.

Mechanism (pre-registered in docs/wills-2026-07-23/GATES.md section W2): for
MiLB seasons 2021+ where the player's season-level line is wholly attributable
to a single affiliate whose home venue carries an in-house run park factor
(data/milb_park_factors.json, built by tools/park_line_lab.py from StatsAPI
schedule scores: league-season centered, EB-shrunk toward 1.0 with K_G=70,
3-season venue window using only seasons <= t), neutralize the stat line
BEFORE the level-relative conversion in efv_dataset._season_rates (the
S-XLINE measurement-layer pattern).

Frozen formulas (registered a priori, never retuned):
  applied_run_pf = (venue_run_pf + 1) / 2      (half of games are on the road,
                                                treated as neutral)
  hitters : obp, slg, ops, iso each divided by sqrt(applied_run_pf). The row
            carries no iso field; iso is derived in _season_rates as
            slg - avg, so avg is scaled by the same sqrt factor, which lands
            the derived iso exactly on iso / sqrt(applied_run_pf).
  pitchers: era divided by applied_run_pf      (runs scale 1:1)
  K and BB rates untouched (the layer carries run and HR factors only).

Clamps at application time (clause 3, round a-priori bounds): run PF
[0.90, 1.10]; HR PF [0.80, 1.25]. The HR factor feeds no frozen formula
(iso/slg use the run factor), so hr_pf is carried in the artifact for
display/audit only and is clamped wherever it is read.

Dominant affiliate: the league-wide StatsAPI season endpoint aggregates
multi-team player-seasons into one split (numTeams field), so a numTeams==1
line is 100 percent attributable to its team (trivially past the registered
70 percent dominance bar) and a numTeams>1 line cannot be split without a
per-person refetch: it resolves to NO dominant affiliate and stays untouched
(the conservative reading of the registration).

Rows with no coverage (pre-2021, no dominant affiliate, unmapped venue, no
factor) return the SAME object (the invariance clause). Coverage reads from
.cache/milb_team_stats/ (player-affiliate mapping, fetched by the lab) and
data/milb_park_factors.json; both absent-safe (no coverage, never an error).

Flags: default-off module constants, overridable per side by env vars
EEPHUS_PARKLINE_HIT / EEPHUS_PARKLINE_PIT ("1"/"0") read at call time so the
gate lab can toggle within one process. Flip the defaults only on gate PASS
(central consolidator).
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

PARKLINE_HIT_DEFAULT = False    # W2 gate verdict pending; central consolidator flips
PARKLINE_PIT_DEFAULT = False
FIRST_PF_SEASON = 2021          # first modern-alignment MiLB season with schedule feeds
DOMINANT_SHARE = 0.70           # registered dominance bar (numTeams==1 rows are 1.00)
RUN_PF_LO, RUN_PF_HI = 0.90, 1.10   # clause 3 clamp, applied at application time
HR_PF_LO, HR_PF_HI = 0.80, 1.25     # clause 3 clamp (display/audit reads only)

_DATA_DIR = Path(__file__).parent / "data"
_PF_PATH = _DATA_DIR / "milb_park_factors.json"
_TEAM_STATS_DIR = Path(__file__).parent / ".cache" / "milb_team_stats"
_SPORTS = (11, 12, 13, 14, 16)


def _flag(side: str) -> bool:
    env = os.environ.get("EEPHUS_PARKLINE_PIT" if side == "pit" else "EEPHUS_PARKLINE_HIT")
    if env is not None:
        return env.strip() == "1"
    return PARKLINE_PIT_DEFAULT if side == "pit" else PARKLINE_HIT_DEFAULT


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


@lru_cache(maxsize=1)
def _pf_maps():
    """(team-season -> venue id, (venue, season) -> windowed run PF) from the
    factor artifact; a pair of empty dicts when the artifact is absent."""
    try:
        doc = json.loads(_PF_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, {}
    tv, vw = {}, {}
    for t in doc.get("team_seasons") or []:
        if t.get("venue_id") is not None:
            tv[(int(t["team_id"]), int(t["season"]))] = int(t["venue_id"])
    for v in doc.get("venues") or []:
        for s, val in (v.get("window_run_pf") or {}).items():
            if val is not None:
                vw[(int(v["venue_id"]), int(s))] = float(val)
    return tv, vw


@lru_cache(maxsize=32)
def _affiliate_index(season: int, group: str) -> dict:
    """{(mlbam, level): team_id} for player-season-level lines wholly
    attributable to one affiliate (numTeams==1; see module docstring).
    Cache-only and absent-safe."""
    out, ambiguous = {}, set()
    for sport in _SPORTS:
        path = _TEAM_STATS_DIR / f"{group}_{sport}_{season}.json"
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in rows:
            mid, team, level = r.get("mlbam"), r.get("team_id"), r.get("level")
            if not mid or not team or not level:
                continue
            key = (int(mid), level)
            if (r.get("num_teams") or 1) > 1:
                ambiguous.add(key)
                continue
            if key in out and out[key] != int(team):
                ambiguous.add(key)      # defensive; one split per sport in practice
                continue
            out[key] = int(team)
    for key in ambiguous:
        out.pop(key, None)
    return out


def venue_run_pf(team_id, season):
    """Clamped windowed run PF for a team-season's home venue, or None."""
    tv, vw = _pf_maps()
    ven = tv.get((int(team_id), int(season)))
    if ven is None:
        return None
    pf = vw.get((ven, int(season)))
    if pf is None:
        return None
    return min(RUN_PF_HI, max(RUN_PF_LO, pf))


def maybe_adjust_row(row, mlbam, season, level, side: str):
    """Return `row` unchanged, or a park-neutralized shallow copy when the W2
    layer applies (flag on, 2021+, dominant affiliate, mapped venue factor)."""
    if not season or int(season) < FIRST_PF_SEASON or not mlbam:
        return row
    if not _flag("pit" if side == "pit" else "hit"):
        return row
    try:
        mid = int(mlbam)
    except (TypeError, ValueError):
        return row
    group = "pitching" if side == "pit" else "hitting"
    team = _affiliate_index(int(season), group).get((mid, level))
    if team is None:
        return row
    run_pf = venue_run_pf(team, int(season))
    if run_pf is None:
        return row
    applied = (run_pf + 1.0) / 2.0          # frozen half-weighting
    if side == "pit":
        era = _f(row.get("era"))
        if era is None:
            return row
        adj = dict(row)
        adj["era"] = era / applied          # frozen: runs scale 1:1
        return adj
    obp, slg = _f(row.get("obp")), _f(row.get("slg"))
    ops, avg = _f(row.get("ops")), _f(row.get("avg"))
    if None in (obp, slg, ops, avg):
        return row
    f = applied ** 0.5                      # frozen sqrt damping for hitter rates
    adj = dict(row)
    adj["obp"] = obp / f
    adj["slg"] = slg / f
    adj["ops"] = ops / f
    adj["avg"] = avg / f                    # makes derived iso = iso / sqrt(applied)
    return adj

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eWAR v3, the house WAR on FanGraphs' frame: the arithmetic and the reader
(docs/ebr-2026-09-30/EBR_GATE.md parts 9.2, 9.7 and amendment 11.10).

THE SERIES. eWAR v3 is the frozen published fWAR vintage (data/fwar_vintage.json)
plus named departures, each zero-sum per season and side. After the outcome look
(part 12.1), the skill look (12.2) and the holdout (12.3) no look-decided part is
admitted, so two departures exist (11.10):

  eabs  candidate part 8, the ABS reattribution part, carried by OWNER OVERRIDE
        (EW3-32), 2026 on, in both series (abs_terms below; EABS_GATE.md part 7);
  r2    the realized pitching basis R2 of 11.3.3, in eWAR realized only, 2016 on.

  headline eWAR     fWAR + eabs / RPW_s                       (owner EW3-20: "eWAR")
  eWAR realized     fWAR + eabs / RPW_s + r2 (pitchers)       (owner EW3-20: "eWAR realized")

Every player-season the artifact does not list carries fWAR unchanged on both
series; the artifact's meta says so.

THE ARTIFACT. data/ewar_v3.json, written by tools/build_ewar_v3.py while
war_source.EWAR_V3_LIVE is on (.cache/ewar_v3/preview/ewar_v3.json otherwise).
players[mlbam][season] holds, per side ("bat" hitting group, "pit" pitching
group), the published fWAR side value and each series' departure in wins
(`dh` headline, `dr` realized), with the parts that make them (`abs` in runs and
wins, `r2` in wins). war_source's provider 'ewar_v3' reads it through
departures(); this module never fetches and never writes data/ewar.json.

Nothing here is a training label, a driver or an input to a fitted consumer
(EBR_GATE.md part 9.1, kept by 11.10).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT = DATA_DIR / "ewar_v3.json"
PREVIEW = ROOT / ".cache" / "ewar_v3" / "preview" / "ewar_v3.json"

VERSION = "ewar_v3_1"
GATE_DOC = "docs/ebr-2026-09-30/EBR_GATE.md"
BUILD_CMD = "python tools/build_ewar_v3.py --write"

#: The first season of the ABS part: ABS challenges began in MLB in 2026.
ABS_FIRST_SEASON = 2026
#: The first season R2 is built for (the swar preview's first season).
R2_FIRST_SEASON = 2016
#: Identity tolerance, runs or wins.
TOL = 1e-9

SIDES = ("bat", "pit")

#: Card labels of the parts (11.10.2, 11.10.3).
PART_LABELS = {
    "eabs": "eABS (ABS challenges)",
    "r2": "realized pitching (runs allowed, adjusted for park, defense and inherited runners)",
}


class EwarV3Refusal(RuntimeError):
    """A build that must not write: the message names the identity or input."""


# ---------------------------------------------------------------------------
# the arithmetic
# ---------------------------------------------------------------------------

def recentre(raw: dict, expo: dict) -> dict:
    """d_k = raw_k - expo_k * (sum raw) / (sum expo), over every key of `expo`
    (the rows of one side). A raw key outside `expo` must be dropped by the
    caller first (a coverage gap). Sums to zero exactly in exact arithmetic; a
    side with no exposure keeps its raw values (and refuses unless they sum to 0)."""
    keys = list(expo)
    total_raw = sum(float(raw.get(k, 0.0)) for k in keys)
    total_expo = sum(max(0.0, float(expo[k] or 0.0)) for k in keys)
    if total_expo <= 0:
        if abs(total_raw) > TOL:
            raise EwarV3Refusal("re-centring a side with no exposure")
        return {k: float(raw.get(k, 0.0)) for k in keys}
    rate = total_raw / total_expo
    return {k: float(raw.get(k, 0.0)) - max(0.0, float(expo[k] or 0.0)) * rate for k in keys}


def abs_terms(challenges, hit_pa: dict, pit_ip: dict, catcher_inn: dict) -> dict:
    """The ABS part for one season (EBR_GATE.md 11.10.2), in runs.

    challenges   dicts with role ('batter', 'catcher', 'pitcher', other),
                 challenge_side ('batting' or 'fielding'), challenger_id,
                 pitcher_id, o (1 overturned, 0 upheld), v (the value if
                 overturned) and c (the option cost of a failure): the eABS frame
    hit_pa       {mlbam: PA} over every hitting-group row of the season
    pit_ip       {mlbam: IP} over every pitching-group row of the season
    catcher_inn  {mlbam: innings at C}

    Returns {"bat": {mlbam: {...}}, "pit": {mlbam: {...}}, "receipt": {...}},
    each row carrying the raw and re-centred terms and `runs` (their sum)."""
    m = defaultdict(float)     # catcher move credits
    f = defaultdict(float)     # hitter-side failure costs (batters and catchers)
    q = defaultdict(float)     # pitcher charges for catcher-won calls on his pitches
    p = defaultdict(float)     # pitcher-side failure costs
    rec = {"challenges": 0, "no_challenger": 0, "pitcher_self_overturned": 0,
           "batter_overturned_not_added": 0, "catcher_won_runs": 0.0,
           "failure_cost_runs": 0.0, "no_pitcher_on_catcher_win": 0}
    for ch in challenges:
        rec["challenges"] += 1
        role = ch.get("role")
        cid = ch.get("challenger_id")
        if cid is None or role not in ("batter", "catcher", "pitcher"):
            rec["no_challenger"] += 1
            continue
        cid = int(cid)
        o = 1 if ch.get("o") else 0
        v = float(ch.get("v") or 0.0)
        c = float(ch.get("c") or 0.0)
        if v < 0 or c < 0 or v != v or c != c:
            raise EwarV3Refusal(f"a challenge carries a negative or non-finite value or cost ({cid})")
        if o:
            if role == "catcher" and ch.get("challenge_side") == "fielding":
                m[cid] += v
                rec["catcher_won_runs"] += v
                pid = ch.get("pitcher_id")
                if pid is None:
                    rec["no_pitcher_on_catcher_win"] += 1
                else:
                    q[int(pid)] -= v
            elif role == "pitcher":
                rec["pitcher_self_overturned"] += 1
            else:
                rec["batter_overturned_not_added"] += 1
        else:
            rec["failure_cost_runs"] += c
            if role == "pitcher":
                p[cid] -= c
            else:
                f[cid] -= c

    def _drop(raw: dict, rows: dict, what: str) -> dict:
        gaps = sorted(k for k in raw if k not in rows)
        rec[f"gap_{what}"] = len(gaps)
        rec[f"gap_{what}_runs"] = float(sum(raw[k] for k in gaps))
        return {k: v for k, v in raw.items() if k in rows}

    m = _drop(m, hit_pa, "move")
    f = _drop(f, hit_pa, "hit_cost")
    q = _drop(q, pit_ip, "charge")
    p = _drop(p, pit_ip, "pit_cost")
    expo_c = {k: max(0.0, float(catcher_inn.get(k, 0.0) or 0.0)) for k in hit_pa}
    bad = sorted(k for k, val in m.items() if val > 0 and expo_c.get(k, 0.0) <= 0)
    if bad:
        raise EwarV3Refusal(f"catchers with challenge wins and no innings at C: {bad[:10]}")
    M = recentre(m, expo_c)
    F = recentre(f, hit_pa)
    Q = recentre(q, pit_ip)
    P = recentre(p, pit_ip)
    bat = {k: {"move_raw": m.get(k, 0.0), "move": M[k], "cost_raw": f.get(k, 0.0), "cost": F[k],
               "runs": M[k] + F[k]} for k in hit_pa}
    pit = {k: {"charge_raw": q.get(k, 0.0), "charge": Q[k], "cost_raw": p.get(k, 0.0), "cost": P[k],
               "runs": Q[k] + P[k]} for k in pit_ip}
    rec["sum_move"] = sum(M.values())
    rec["sum_hit_cost"] = sum(F.values())
    rec["sum_charge"] = sum(Q.values())
    rec["sum_pit_cost"] = sum(P.values())
    rec["sum_move_raw"] = sum(m.values())
    rec["sum_charge_raw"] = sum(q.values())
    for key in ("sum_move", "sum_hit_cost", "sum_charge", "sum_pit_cost"):
        if abs(rec[key]) > 1e-6:
            raise EwarV3Refusal(f"the ABS part's {key} is {rec[key]} runs, not zero")
    return {"bat": bat, "pit": pit, "receipt": rec}


# ---------------------------------------------------------------------------
# the reader
# ---------------------------------------------------------------------------

_CACHE: dict | None = None
_DEP_CACHE: dict = {}


def available() -> bool:
    """True when the artifact can serve: a memoised payload (the test seam) or
    data/ewar_v3.json on disk."""
    return _CACHE is not None or OUT.exists()


def load(path: Path | None = None) -> dict:
    """Read data/ewar_v3.json (memoised; a `path` read is not memoised)."""
    global _CACHE
    if path is not None:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    if _CACHE is None:
        _CACHE = json.loads(OUT.read_text(encoding="utf-8"))
    return _CACHE


def set_payload(payload: dict | None) -> None:
    """Inject (or clear) the payload: the test seam."""
    global _CACHE
    _CACHE = payload
    _DEP_CACHE.clear()


def departures(payload: dict | None = None, series: str = "headline") -> dict:
    """{(mlbam, season): {"bat": wins, "pit": wins}} for one series
    ('headline' or 'realized'): the departure from published fWAR on each side
    the artifact lists. A side or a player-season not listed departs by 0."""
    if series not in ("headline", "realized"):
        raise ValueError(f"unknown eWAR v3 series {series!r}")
    blob = load() if payload is None else payload
    key = (id(blob), series)
    if payload is None and key in _DEP_CACHE:
        return _DEP_CACHE[key]
    fld = "dh" if series == "headline" else "dr"
    out: dict = {}
    for mid_s, seasons in (blob.get("players") or {}).items():
        for season_s, blk in seasons.items():
            d = blk.get(fld) or {}
            cell = {s: float(d[s]) for s in SIDES if d.get(s) is not None}
            if cell:
                out[(int(mid_s), int(season_s))] = cell
    if payload is None:
        _DEP_CACHE[key] = out
    return out


def block_for(mlbam: int, season: int, payload: dict | None = None) -> dict | None:
    """The artifact's block for one player-season, or None (fWAR on both series)."""
    blob = load() if payload is None else payload
    return ((blob.get("players") or {}).get(str(int(mlbam))) or {}).get(str(int(season)))


def meta(payload: dict | None = None) -> dict:
    blob = load() if payload is None else payload
    return dict(blob.get("meta") or {})

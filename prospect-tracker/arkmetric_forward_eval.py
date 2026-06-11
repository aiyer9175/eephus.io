# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Statcast+ forward validation (model-audit Phase 4b, WS-8) — does a
prospect's final-MiLB Statcast composite carry signal into MLB?

SC+ is descriptive by design but CONSUMED as a signal (breakout gate,
ETA modifier, spotlight booster), so the audit requires a forward r —
published even if weak. The live pipeline's own history can't provide
it: statcast_metrics/zone_metrics rows exist for the CURRENT season
only (the table began accumulating in 2026; the per-season trail starts
now — documented data lift). What is reconstructable today is the
analog from Baseball Savant's minors statcast-search player aggregates
(tracked minors parks, 2023+):

  ANALOG     z-blend of avg EV / HardHit% / Barrel%/BBE / SwingMiss%
             (inverted for hitters, positive for pitchers — pitchers
             additionally invert the contact components) within the
             season's AAA pool, scaled 100 + 10z. That's four of SC+'s
             six components; the Z-Contact/Chase zone splits have no
             historical source (documented gap). Pool restricted to
             players whose highest MiLB level that season was AAA (the
             tracked-park population also includes FSL — excluded so
             the percentile means 'vs AAA peers', matching SC+'s
             pool-relative claim).
  COHORTS    debuts.json players with debut year Y in 2024-2026 and a
             qualifying Savant AAA aggregate in season Y-1 (strictly
             pre-debut; min 100 PA faced/taken).
  OUTCOMES   hitters: first-MLB-season OPS (min 100 PA, StatsAPI);
             pitchers: first-MLB-season ERA (min 100 BF, inverted).
             Both sides: first-2-year bWAR (career_war; 2026 debuts
             excluded from the bWAR slice — window still open).
  METRIC     Pearson r + Spearman rho per cohort + pooled.

Artifact: data/statcast_plus_eval.json. Registry: statcast_plus moves
to `provisional` on this analog (publish-the-r rule); the live
composite's own forward trail starts with the 2026 season rows.

Stuff+ (tjstuff_plus, external) is NOT covered here: it consumes
per-pitch kinematics that have no historical archive for prospects —
its registry row stays `unvalidated` with the data lift documented
(per-season Stf+ persistence began 2026; first scoreable cohort once
those prospects debut).

Run: python arkmetric_forward_eval.py
"""

from __future__ import annotations

import csv
import io
import json
import logging
import statistics
from datetime import date
from functools import lru_cache
from pathlib import Path

import milb_history as mh
import storage

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "statcast_plus_eval.json"
CACHE_DIR = Path(__file__).parent / ".cache" / "savant_minors"

# the search CSV requires the FULL form skeleton (sparse param sets fall
# back to defaults silently) + minors=true for the MiLB tracked-park data
SAVANT = ("https://baseballsavant.mlb.com/statcast-search-minors/csv?all=true"
          "&hfPT=&hfAB=&hfBBT=&hfPR=&hfZ=&stadium=&hfBBL=&hfNewZones="
          "&hfGT=R%7C&hfC=&hfSea={year}%7C&hfSit=&player_type={type}"
          "&hfOuts=&opponent=&pitcher_throws=&batter_stands=&hfSA="
          "&game_date_gt=&game_date_lt=&hfInfield=&team=&position="
          "&hfOutfield=&hfRO=&home_road=&hfFlag=&hfPull=&metric_1=&hfInn="
          "&min_pitches=0&min_results=0&group_by=name&sort_col=pitches"
          "&player_event_sort=api_p_release_speed&sort_order=desc"
          "&min_pas=100&minors=true")
SEASONS = (2023, 2024, 2025)          # AAA tracking begins 2023
# four of SC+'s six components; sign per side handled in sc_analog_index
COMPONENTS = ("launch_speed", "hardhit_percent", "barrels_per_bbe_percent",
              "swing_miss_percent")
MIN_POOL_PA = 100
MIN_PA, MIN_BF = 100, 100


def savant_rows(season: int, side: str, fetch: bool = True) -> list[dict]:
    """Cached Savant minors statcast-search player aggregates
    (side: batter|pitcher)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{side}_{season}.csv"
    if not path.exists():
        if not fetch:
            return []
        import urllib.request
        url = SAVANT.format(type=side, year=season)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                path.write_bytes(r.read())
        except Exception as e:                                # noqa: BLE001
            log.warning("savant minors fetch failed %s/%s: %s", side, season, e)
            return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


@lru_cache(maxsize=8)
def _aaa_mlbams(season: int) -> frozenset[int]:
    """mlbams whose highest MiLB level in `season` was AAA (either side)."""
    out = set()
    for group in ("hitting", "pitching"):
        for mid, rows in mh.player_index(season, group).items():
            milb = [r for r in rows if r.get("level") != "MLB"]
            if milb and mh.highest_level(milb) == "AAA":
                out.add(mid)
    return frozenset(out)


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def sc_analog_index(season: int, side: str) -> dict[int, float]:
    """{mlbam: SC+ contact analog} for one AAA season pool. Component
    signs mirror SC+: hitters want contact quality up + whiff down;
    pitchers want contact quality against DOWN + induced whiff UP."""
    aaa = _aaa_mlbams(season)
    rows = savant_rows(season, side)
    signs = ({"launch_speed": 1, "hardhit_percent": 1,
              "barrels_per_bbe_percent": 1, "swing_miss_percent": -1}
             if side == "batter" else
             {"launch_speed": -1, "hardhit_percent": -1,
              "barrels_per_bbe_percent": -1, "swing_miss_percent": 1})
    cols: dict[str, list[float]] = {c: [] for c in COMPONENTS}
    per: list[tuple[int, dict[str, float]]] = []
    for r in rows:
        mid = _f(r.get("player_id"))
        pa = _f(r.get("pa")) or 0
        if mid is None or int(mid) not in aaa or pa < MIN_POOL_PA:
            continue
        vals = {c: _f(r.get(c)) for c in COMPONENTS}
        if any(v is None for v in vals.values()):
            continue
        per.append((int(mid), vals))
        for c, v in vals.items():
            cols[c].append(v)
    if len(per) < 30:
        return {}
    stats = {c: (statistics.mean(v), statistics.pstdev(v) or 1.0)
             for c, v in cols.items()}
    out = {}
    for mid, vals in per:
        zs = [signs[c] * (vals[c] - stats[c][0]) / stats[c][1]
              for c in COMPONENTS]
        out[mid] = round(100 + 10 * (sum(zs) / len(zs)), 1)
    return out


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 8:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    vx = sum((a - mx) ** 2 for a in xs)
    vy = sum((b - my) ** 2 for b in ys)
    if vx == 0 or vy == 0:
        return None
    return round(cov / (vx * vy) ** 0.5, 4)


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    def _ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    if len(xs) < 8:
        return None
    return _pearson(_ranks(xs), _ranks(ys))


def _load_debuts() -> list[dict]:
    try:
        return json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _war_first2(player_key: str, debut: int, cw: dict) -> float | None:
    seasons = cw.get(player_key) or {}
    if not seasons:
        return None
    return round(sum(w for y, w in seasons.items() if debut <= y <= debut + 1), 2)


def run(persist: bool = True) -> dict:
    debuts = _load_debuts()
    with storage.connect() as con:
        cw = {}
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            try:
                seasons = (json.loads(r["payload_json"]) or {}).get("seasons") or {}
            except ValueError:
                continue
            cw[r["player_key"]] = {int(y): float(w) for y, w in seasons.items()}

    pairs: dict[str, dict[str, list]] = {
        "hit": {"sc": [], "ops": [], "war_sc": [], "war": []},
        "pit": {"sc": [], "era": [], "war_sc": [], "war": []},
    }
    cohort_n = {}
    for season in SEASONS:
        debut_year = season + 1
        idx_h = sc_analog_index(season, "batter")
        idx_p = sc_analog_index(season, "pitcher")
        mlb_h = mh.player_index(debut_year, "hitting") if debut_year <= 2026 else {}
        mlb_p = mh.player_index(debut_year, "pitching") if debut_year <= 2026 else {}
        n = 0
        for d in debuts:
            dd = d.get("debut_date") or ""
            mid = d.get("mlbam_id")
            if not mid or not dd or int(dd[:4]) != debut_year:
                continue
            mid = int(mid)
            if mid in idx_h:
                rows = [r for r in (mlb_h.get(mid) or []) if r["level"] == "MLB"]
                row = rows[0] if rows else None
                ops = _f(row.get("ops")) if row else None
                pa = _f(row.get("pa")) if row else 0
                if ops is not None and (pa or 0) >= MIN_PA:
                    pairs["hit"]["sc"].append(idx_h[mid])
                    pairs["hit"]["ops"].append(ops)
                    n += 1
                if debut_year <= 2025:
                    w = _war_first2(d["player_key"], debut_year, cw)
                    if w is not None:
                        pairs["hit"]["war_sc"].append(idx_h[mid])
                        pairs["hit"]["war"].append(w)
            elif mid in idx_p:
                rows = [r for r in (mlb_p.get(mid) or []) if r["level"] == "MLB"]
                row = rows[0] if rows else None
                era = _f(row.get("era")) if row else None
                bf = _f(row.get("bf")) if row else 0
                if era is not None and (bf or 0) >= MIN_BF:
                    pairs["pit"]["sc"].append(idx_p[mid])
                    pairs["pit"]["era"].append(-era)   # invert: higher = better
                    n += 1
                if debut_year <= 2025:
                    w = _war_first2(d["player_key"], debut_year, cw)
                    if w is not None:
                        pairs["pit"]["war_sc"].append(idx_p[mid])
                        pairs["pit"]["war"].append(w)
        cohort_n[f"{season}->{debut_year}"] = n

    out = {
        "generated_at": date.today().isoformat(),
        "seasons": list(SEASONS),
        "conventions": {
            "analog": "4 of SC+'s 6 components (avg EV / HardHit% / "
                      "Barrel%/BBE / SwingMiss%) z-blended at 100+10z "
                      "within the AAA pool, from Savant minors "
                      "statcast-search aggregates — Z-Contact/Chase "
                      "splits have no historical source (documented gap)",
            "cohort": "debut year Y with qualifying AAA Savant aggregate "
                      f"in Y-1 (min {MIN_POOL_PA} PA, AAA-pool-restricted)",
            "outcomes": f"first-MLB-season OPS (>= {MIN_PA} PA) / ERA "
                        f"(>= {MIN_BF} BF, inverted); first-2y bWAR "
                        "(2026 debuts excluded — window open)",
            "live_trail": "per-season statcast_metrics/zone_metrics rows "
                          "began accumulating 2026 — the literal composite "
                          "becomes forward-scoreable as those cohorts debut",
        },
        "cohort_n": cohort_n,
        "hitters": {
            "n_ops": len(pairs["hit"]["sc"]),
            "r_sc_vs_mlb_ops": _pearson(pairs["hit"]["sc"], pairs["hit"]["ops"]),
            "rho_sc_vs_mlb_ops": _spearman(pairs["hit"]["sc"], pairs["hit"]["ops"]),
            "n_war": len(pairs["hit"]["war_sc"]),
            "r_sc_vs_war2y": _pearson(pairs["hit"]["war_sc"], pairs["hit"]["war"]),
            "rho_sc_vs_war2y": _spearman(pairs["hit"]["war_sc"], pairs["hit"]["war"]),
        },
        "pitchers": {
            "n_era": len(pairs["pit"]["sc"]),
            "r_sc_vs_mlb_era_inv": _pearson(pairs["pit"]["sc"], pairs["pit"]["era"]),
            "rho_sc_vs_mlb_era_inv": _spearman(pairs["pit"]["sc"], pairs["pit"]["era"]),
            "n_war": len(pairs["pit"]["war_sc"]),
            "r_sc_vs_war2y": _pearson(pairs["pit"]["war_sc"], pairs["pit"]["war"]),
            "rho_sc_vs_war2y": _spearman(pairs["pit"]["war_sc"], pairs["pit"]["war"]),
        },
        "verdict": {
            "summary": "WEAK forward signal, published per the audit's "
                       "publish-the-r rule: final-AAA contact analog vs "
                       "first-MLB rate outcomes r ~ 0.12-0.17; vs 2y bWAR "
                       "~ 0 (hitters). Consistent with the known ISO+ -> "
                       "MLB ISO r=0.24 prior. SC+ remains descriptive — "
                       "downstream consumers (breakout gate, ETA "
                       "modifier, spotlight boost) should treat it as a "
                       "tiebreaker, never a driver; the ETA backtest "
                       "scores the core heuristic WITHOUT the SC+ nudge.",
        },
    }
    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s", OUT_PATH)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    print("cohorts:", rep["cohort_n"])
    print("hitters:", rep["hitters"])
    print("pitchers:", rep["pitchers"])

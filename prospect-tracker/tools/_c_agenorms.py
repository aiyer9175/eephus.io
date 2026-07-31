"""Phase C2 - build the ONE decimal, prospect-filtered, per-level age-norm table.

Why this exists
---------------
eFV norms age-for-level against a static hand-set table (`efv_dataset._TYPICAL_LEVEL_AGE`),
the site norms it against `level_norms.compute_level_norms` (an EMPIRICAL table computed over
EVERY tracked player at the level), and ETA norms it against a third table
(`eta.EXPECTED_AGES`). The three disagree by up to 2.4 yr at AAA, so the site can call a
player "young for level, -1.7" while the model scores him exactly neutral.

The empirical table cannot simply be adopted: it reads AAA 26.37 because AAA rosters carry
org veterans, minor-league free agents and MLB rehabbers who are not prospects and are not
the population eFV's age feature is about. This builds the same empirical median over the
PROSPECT-FILTERED cohort (the tracked prospect universe only) with two further corrections:

  * DECIMAL season-midpoint ages from birth_date, not the integer StatsAPI baseball age;
  * the SAME exposure gate `efv_dataset._milb_features` applies when it picks a primary
    level (>= 50 PA hitting / >= 60 BF pitching), so the norm describes players who
    actually played the level rather than everyone who appeared there.

Offline: reads the MiLB stat cache (fetch=False) and the prospect universe JSONs. Writes
nothing unless --write is passed (then data/_c_agenorms.json, an eval artifact).
"""
from __future__ import annotations

import json
import statistics as st
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import milb_history as mh                                            # noqa: E402
from efv_dataset import _LEVEL_RANK, _TYPICAL_LEVEL_AGE              # noqa: E402

DATA = ROOT / "data"
FIRST_SEASON = 2014          # StatsAPI MiLB coverage is usable from here
LAST_SEASON = 2026


def universe() -> dict[int, str]:
    """{mlbam_id: birth_date} over the tracked PROSPECT universe (actives +
    graduates + busts). Everyone here was on a public prospect list at some point,
    which is exactly the population eFV's age feature describes."""
    out: dict[int, str] = {}
    for fn in ("timeseries.json", "debuts.json", "inactive.json"):
        p = DATA / fn
        if not p.exists():
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        recs = doc.get("players") if isinstance(doc, dict) else doc
        for r in recs or []:
            mid, bd = r.get("mlbam_id"), r.get("birth_date")
            if mid and bd:
                out[int(mid)] = bd
    return out


def collect(uni: dict[int, str]):
    """[(level, season, decimal_age)] for every prospect-season-level that clears the
    _milb_features exposure gate."""
    rows = []
    for group, expo, minexp in (("hitting", "pa", 50), ("pitching", "bf", 60)):
        for season in range(FIRST_SEASON, LAST_SEASON + 1):
            idx = mh.player_index(season, group, fetch=False)
            if not idx:
                continue
            mid = date(season, 6, 30)
            for mlbam, rs in idx.items():
                bd = uni.get(int(mlbam))
                if not bd:
                    continue
                try:
                    b = date.fromisoformat(bd[:10])
                except (TypeError, ValueError):
                    continue
                age = (mid - b).days / 365.25
                if not (14.0 <= age <= 40.0):
                    continue
                for lv in {r.get("level") for r in rs}:
                    if lv not in _LEVEL_RANK:
                        continue
                    lr = mh.level_row(rs, lv, group) or {}
                    try:
                        e = float(lr.get(expo) or 0.0)
                    except (TypeError, ValueError):
                        e = 0.0
                    if e >= minexp:
                        rows.append((lv, season, age, group))
    return rows


def table(rows, per_season: bool = False):
    if per_season:
        by: dict[tuple[str, int], list[float]] = {}
        for lv, se, ag, _g in rows:
            by.setdefault((lv, se), []).append(ag)
    else:
        by = {}
        for lv, _se, ag, _g in rows:
            by.setdefault(lv, []).append(ag)
    return {k: (round(st.median(v), 2), len(v)) for k, v in sorted(by.items(), key=str)}


def main():
    uni = universe()
    rows = collect(uni)
    print(f"prospect universe with birth_date + mlbam: {len(uni)}")
    print(f"qualified prospect-season-level rows: {len(rows)}")
    pooled = table(rows)
    print("\nlevel  eFV static   NEW prospect-filtered decimal median      n")
    for lv in ("DSL", "CPX", "A", "A+", "AA", "AAA"):
        m, n = pooled.get(lv, (None, 0))
        old = _TYPICAL_LEVEL_AGE.get(lv)
        d = f"{m - old:+.2f}" if m is not None else "  n/a"
        print(f"{lv:5s}  {old:9.2f}   {m if m is not None else float('nan'):>8}   ({d})   {n:7d}")
    per_side = {}
    for g in ("hitting", "pitching"):
        per_side[g] = table([r for r in rows if r[3] == g])
    print("\nper-side check (hitting / pitching medians):")
    for lv in ("DSL", "CPX", "A", "A+", "AA", "AAA"):
        h = per_side["hitting"].get(lv, (None, 0))
        p = per_side["pitching"].get(lv, (None, 0))
        print(f"  {lv:5s} hit {h[0]} (n={h[1]})   pit {p[0]} (n={p[1]})")
    ps = table(rows, per_season=True)
    out = {"pooled": {k: {"median": v[0], "n": v[1]} for k, v in pooled.items()},
           "per_side": {g: {k: {"median": v[0], "n": v[1]} for k, v in t.items()}
                        for g, t in per_side.items()},
           "per_level_season": {f"{k[0]}|{k[1]}": {"median": v[0], "n": v[1]}
                                for k, v in ps.items()},
           "static_efv_table": _TYPICAL_LEVEL_AGE,
           "n_rows": len(rows), "n_universe": len(uni),
           "seasons": [FIRST_SEASON, LAST_SEASON]}
    if "--write" in sys.argv:
        (DATA / "_c_agenorms.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("\nwrote data/_c_agenorms.json")
    else:
        print("\n(dry run; pass --write to persist the eval artifact)")


if __name__ == "__main__":
    main()

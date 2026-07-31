# SCRATCH LAB (lane: scale-audit). Read-only.
# Builds BOTH versions of the surplus-calibration input pool on the SAME
# (player, listing-year) cells:
#   RAW   = surplus_backtest_real._load_inputs (median of each source's EARLIEST
#           same-year snapshot FV, no normalization)  <- what the shipped
#           calibration linearmap-v5 was fit on
#   NEW   = same cells, each per-source FV passed through the PRODUCTION
#           normalizer (grade_normalization.build_remapper(aliases=SOURCE_ALIASES),
#           working tree = post 2026-07-25 repair), then the same median
#   OLD   = same cells under the PRE-repair normalizer (discrete np.interp
#           quantile map, no min_n drop, no alias fallback) -- reconstructed
#           verbatim from git HEAD grade_normalization.py
# Writes tools/_dpw_out/scale_pool.json
import json
import os
import statistics
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))
os.chdir(_HERE)
OUT = _HERE / "tools" / "_dpw_out"
OUT.mkdir(exist_ok=True)

import storage  # noqa: E402
import grade_normalization as gn  # noqa: E402
import consensus as cons  # noqa: E402

# The shipped calibration window is 2017-2019; we build EVERY cycle so the
# scale claim gets forward-chained time splits (the 3-year fit window alone
# cannot supply the >=4 splits docs/EFV_GATE_STANDARD.md asks for).
LISTING_YEARS = tuple(range(2017, 2027))
CAL_YEARS = (2017, 2018, 2019)
MIN_FV = 40.0


# ---------- OLD (pre-repair) remapper: verbatim reconstruction of git HEAD ----------
def build_remapper_OLD(years=None):
    latest = gn._all_latest()
    sources = set()
    for players in latest.values():
        for d in players.values():
            sources.update(d.keys())
    table = {}
    for (role, yr) in list(latest.keys()):
        if years is not None and yr not in years:
            continue
        for src in sources:
            if src == gn.REFERENCE or src in gn._SYNTHETIC_SOURCES:
                continue
            s_sorted, r_sorted, _p = gn._paired_dists(src, role, yr)
            if len(s_sorted) and len(r_sorted) and gn._mappable(s_sorted, r_sorted):
                table[(src, role, yr)] = (s_sorted, r_sorted)

    def remap(fv, source, position, year):
        if fv is None:
            return None
        if source == gn.REFERENCE:
            return float(fv)
        try:
            yr = int(year)
        except (TypeError, ValueError):
            return float(fv)
        role = "pitcher" if gn._is_pitcher(position) else "hitter"
        ent = table.get((source, role, yr))
        if not ent:
            return float(fv)
        src, ref = ent
        if len(src) == 1:
            q = 0.5
        else:
            q = float(np.interp(float(fv), src, np.linspace(0.0, 1.0, len(src))))
        return float(np.interp(q, np.linspace(0.0, 1.0, len(ref)), ref))

    return remap


def main():
    yrs = ",".join(f"'{y}'" for y in LISTING_YEARS)
    with storage.connect() as con:
        # earliest same-year snapshot_date per (player, source, year)
        rows = con.execute(f"""
            SELECT player_key, source, substr(snapshot_date,1,4) AS y,
                   MIN(snapshot_date) AS d
            FROM snapshots WHERE fv IS NOT NULL
              AND substr(snapshot_date,1,4) IN ({yrs})
            GROUP BY player_key, source, y""").fetchall()
        want = {(r["player_key"], r["source"], r["d"]) for r in rows}
        # one pass for the fv+position at those exact (player, source, date) rows
        detail = {}
        for r in con.execute(f"""
            SELECT player_key, source, snapshot_date, fv, position
            FROM snapshots WHERE fv IS NOT NULL
              AND substr(snapshot_date,1,4) IN ({yrs})"""):
            k = (r["player_key"], r["source"], r["snapshot_date"])
            if k in want and k not in detail:
                detail[k] = (float(r["fv"]), r["position"])
        # player-level position (players table) for the role fallback
        pbio = {r["player_key"]: dict(r) for r in con.execute(
            "SELECT player_key, position, is_pitcher FROM players")}

    remap_new = gn.build_remapper(aliases=cons.SOURCE_ALIASES)
    remap_old = build_remapper_OLD()

    cells = {}
    for r in rows:
        k = (r["player_key"], r["source"], r["d"])
        if k not in detail:
            continue
        fv, pos = detail[k]
        pos = pos or (pbio.get(r["player_key"], {}) or {}).get("position")
        cells.setdefault((r["player_key"], int(r["y"])), []).append(
            {"source": r["source"], "fv": fv, "pos": pos, "date": r["d"]})

    pool = []
    for (pk, yr), srcs in sorted(cells.items()):
        raws = [s["fv"] for s in srcs]
        news = [remap_new(s["fv"], s["source"], s["pos"], yr) for s in srcs]
        olds = [remap_old(s["fv"], s["source"], s["pos"], yr) for s in srcs]
        pool.append({
            "player_key": pk, "year": yr, "n_sources": len(srcs),
            "date": min(s["date"] for s in srcs),
            "is_pitcher": bool((pbio.get(pk) or {}).get("is_pitcher")),
            "raw": statistics.median(raws),
            "new": statistics.median(news),
            "old": statistics.median(olds),
            "sources": [s["source"] for s in srcs],
            "per_source": [[s["source"], s["fv"], round(n, 3), round(o, 3)]
                           for s, n, o in zip(srcs, news, olds)],
        })
    (OUT / "scale_pool.json").write_text(json.dumps(pool), encoding="utf-8")
    n_ship = sum(1 for p in pool if p["raw"] >= MIN_FV)
    print(f"cells total {len(pool)}   raw>=40 (SHIPPED pool gate) {n_ship}")
    print(f"  new>=40 {sum(1 for p in pool if p['new'] >= MIN_FV)}"
          f"   old>=40 {sum(1 for p in pool if p['old'] >= MIN_FV)}")


if __name__ == "__main__":
    main()

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""LANE recalibrate -- pool builder (READ-ONLY lab).

Builds the surplus-calibration cohort on BOTH FV scales in one pass and caches
the raw ingredients (never the prices) so every downstream pricing regime can be
re-run without touching the DB again.

Scales
  raw    median of each source's EARLIEST same-year snapshot FV  (what the
         shipped calibration linearmap-v5 was fit on)
  norm   the same median, but each source grade first remapped onto the
         FanGraphs scale by grade_normalization.build_remapper(aliases=
         consensus.SOURCE_ALIASES) -- what PRODUCTION consensus feeds.

Validated against the shipped loader: for LISTING_YEARS (2017,2018,2019) with
scale=raw and the MIN_FV gate on raw, this must return exactly 3,368 listings
and 2,236 resolved players (the registered v5 fit n).

Writes a pickle of ingredients only: fv_raw, fv_norm, role, position, age,
eta_years, war_by_year, debut, resolved. Salaries/prices are NOT cached because
they depend on the $/WAR regime under test.
"""
from __future__ import annotations

import json
import pickle
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import storage                                                  # noqa: E402
import consensus as _cons                                       # noqa: E402
from grade_normalization import build_remapper                  # noqa: E402
from surplus_backtest_real import (                             # noqa: E402
    _LEVEL_ETA, _age_at, _highest_level_through, _last_activity,
    _mlb_seasons_from_stats, CONTROL_YEARS, LAST_FULL_SEASON, MIN_FV,
    WASHED_BEFORE)

SCRATCH = Path(r"C:\Users\noah\AppData\Local\Temp\claude"
               r"\c--Users-noah-baseball-projects-BaseballR"
               r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")


def out_path(years) -> Path:
    return SCRATCH / f"recal_pool_{min(years)}_{max(years)}.pkl"


def build(years: tuple[int, ...]) -> dict:
    remap = build_remapper(aliases=_cons.SOURCE_ALIASES)
    ylist = ",".join(f"'{y}'" for y in years)
    with storage.connect() as con:
        rows = con.execute(
            "SELECT player_key, source, snapshot_date, fv, position FROM snapshots "
            f"WHERE fv IS NOT NULL AND substr(snapshot_date,1,4) IN ({ylist})"
        ).fetchall()
        # earliest same-year snapshot per (player, source, year)
        first: dict[tuple, tuple] = {}
        for r in rows:
            k = (r["player_key"], r["source"], int(str(r["snapshot_date"])[:4]))
            d = str(r["snapshot_date"])
            if k not in first or d < first[k][0]:
                first[k] = (d, float(r["fv"]), r["position"])
        per: dict[tuple, list] = {}
        for (pk, src, y), (d, fv, pos) in first.items():
            fvn = remap(fv, src, pos, y)
            per.setdefault((pk, y), []).append((fv, float(fvn), d))
        cw = {r["player_key"]: json.loads(r["payload_json"])
              for r in con.execute("SELECT player_key, payload_json FROM career_war")}
        cs = {}
        for r in con.execute("SELECT player_key, payload_json FROM career_stats"):
            try:
                cs[r["player_key"]] = json.loads(r["payload_json"])
            except ValueError:
                continue
        bio = {r["player_key"]: dict(r) for r in con.execute(
            "SELECT player_key, position, is_pitcher, birth_date FROM players")}

    listings = {}
    for key, vals in per.items():
        med_raw = statistics.median(v for v, _, _ in vals)
        med_norm = statistics.median(n for _, n, _ in vals)
        listings[key] = {"fv_raw": med_raw, "fv_norm": med_norm,
                         "date": min(d for _, _, d in vals), "n_sources": len(vals)}

    acct = {"listed": 0, "scored": 0, "scored_busts": 0, "excluded_no_war": 0,
            "censored_active": 0, "excluded_post_debut_listing": 0,
            "excluded_no_bio": 0, "resolved": 0}
    out = []
    for (key, year), li in sorted(listings.items()):
        acct["listed"] += 1
        b = bio.get(key)
        if not b:
            acct["excluded_no_bio"] += 1
            continue
        stats_rows = cs.get(key) or []
        war_seasons = (cw.get(key) or {}).get("seasons") or {}
        mlb_seen = _mlb_seasons_from_stats(stats_rows) | {int(y) for y in war_seasons}
        if any(s < year for s in mlb_seen):
            acct["excluded_post_debut_listing"] += 1
            continue
        if war_seasons:
            debut = min(int(y) for y in war_seasons)
            resolved = (debut + CONTROL_YEARS - 1) <= LAST_FULL_SEASON
        elif mlb_seen:
            acct["excluded_no_war"] += 1
            continue
        else:
            last = _last_activity(stats_rows)
            if last is not None and last >= WASHED_BEFORE:
                acct["censored_active"] += 1
                continue
            debut, resolved = None, True
            acct["scored_busts"] += 1
        lvl = _highest_level_through(stats_rows, year)
        out.append({
            "key": key, "year": year,
            "fv_raw": li["fv_raw"], "fv_norm": li["fv_norm"],
            "n_sources": li["n_sources"],
            "is_pitcher": bool(b.get("is_pitcher")), "position": b.get("position"),
            "age": _age_at(b.get("birth_date"), li["date"]),
            "eta_years": _LEVEL_ETA.get(lvl or "", 3.5),
            "war_by_year": {int(k): float(v) for k, v in war_seasons.items()},
            "debut": debut, "resolved": resolved,
        })
        acct["scored"] += 1
        if resolved:
            acct["resolved"] += 1
    return {"records": out, "accounting": acct, "years": list(years),
            "n_listings_all": len(listings),
            "listings_gate_raw": sum(1 for v in listings.values() if v["fv_raw"] >= MIN_FV),
            "listings_gate_norm": sum(1 for v in listings.values() if v["fv_norm"] >= MIN_FV),
            "generated_at": date.today().isoformat()}


if __name__ == "__main__":
    years = tuple(int(a) for a in sys.argv[1:]) or (2017, 2018, 2019)
    rep = build(years)
    OUT = out_path(years)
    OUT.write_bytes(pickle.dumps(rep))
    print("years", rep["years"])
    print("listings (all, ungated)", rep["n_listings_all"])
    print("listings gate_raw>=40 ", rep["listings_gate_raw"])
    print("listings gate_norm>=40", rep["listings_gate_norm"])
    print("accounting (ungated)", rep["accounting"])
    for gate in ("raw", "norm"):
        recs = [r for r in rep["records"] if r[f"fv_{gate}"] >= MIN_FV]
        print(f"  gate={gate:4s} scored={len(recs):5d} "
              f"resolved={sum(1 for r in recs if r['resolved']):5d}")
    print("wrote", OUT)

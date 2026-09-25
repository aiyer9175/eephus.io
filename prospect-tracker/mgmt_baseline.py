#!/usr/bin/env python
"""The matched-state league baseline behind decision value above state (DVS).

THE BUNT RECIPE GENERALISED. For each family f and matched state cell

    S = (season, inning bucket {1-3, 4-6, 7, 8, 9+}, half, outs, base code,
         score-diff bucket {<= -4, -3, -2, -1, 0, +1, +2, +3, >= +4})

the baseline is the league mean realized window mWPA over EVERY window of the same
shape from S, decision or not:

    baseline_f(S) = mean over league windows from S of mWPA(window)
    DVS(d)        = mWPA(d) - baseline_f(S(d))

The non-decision windows are: for the pitching change, every stint start (any pitcher's
first plate appearance in a half-inning, and every mid-inning pitcher change) to the end
of that stint; for the pinch hit and the bunt, every plate appearance; for the
pinch run, every half-inning remainder from a state with a runner on; for the intentional
walk, every two-plate-appearance span whose first plate appearance was pitched to; for the
defensive sub, every rest-of-game span. The steal has no baseline: its realized value is
the steal itself on the house win expectancy table (mgmt_decisions.MODEL_REALIZED), not a
feed window, and its value above holding is its DV. MIN_CELL on the baseline side; thin cells are
published as excluded, exactly as mgmt_bunt does.

WHAT DVS REMOVES: the level of the state, so a club that faced many high-leverage spots
is not credited for the spots. WHAT IT DOES NOT REMOVE: player quality and selection (the
manager chooses when to act). It is realized value above what the league realized from
the same spot: still descriptive, still not skill, and it lives on the per-decision
drill-down and the League census ONLY, never on a club-season or manager row (spec 5.1).

THE IDENTITY, CHECKED NOT ASSERTED: within every cell the residuals of the league windows
sum to zero by construction; the artifact publishes the largest absolute mean residual
it found so a reader can see the construction held.

Offline. python mgmt_baseline.py [--seasons 2024,2025]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "management_baseline.json"

log = logging.getLogger(__name__)

#: A cell needs this many league windows before it prices a decision; below it the
#: cell is published as thin and DVS is null for decisions that land in it.
MIN_CELL = 25

INNING_BUCKETS = (("1-3", 1, 3), ("4-6", 4, 6), ("7", 7, 7), ("8", 8, 8), ("9+", 9, 99))
SCORE_BUCKETS = ("<=-4", "-3", "-2", "-1", "0", "+1", "+2", "+3", ">=+4")

#: Which computed cell table each family reads. Single-plate-appearance families
#: share one table: every plate appearance from the state is the league window.
CELL_SOURCE = {"pitching_change": "pitching_change", "pinch_hit": "single_pa",
               "bunt": "single_pa", "pinch_run": "pinch_run",
               "intentional_walk": "intentional_walk", "defensive_sub": "defensive_sub"}

SELECTION_CAVEAT = {
    "intentional_walk": ("intentional walks are given to the hitters a manager least wants "
                         "to face, so the state-matched mean of pitching to him is measured "
                         "over weaker batters and is biased FOR the walk. Stated, not solved."),
    "pinch_hit": ("a pinch hitter is sent up for the batters a manager least wants at the "
                  "plate, so the state-matched league plate appearance is a different "
                  "population of hitters from the ones lifted. Stated, not solved."),
}
SINGLE_PA_CAVEAT = (
    "for the single-plate-appearance families (pinch hit, bunt) the baseline is the league "
    "mean realized change over every plate appearance from the same state, which a "
    "calibrated win model puts near zero, so DVS there is mWPA plus the feed model's local "
    "miscalibration and is NOT an independent second number; it differs materially only "
    "for the stint-length windows (pitching change, pinch run, intentional walk). The "
    "steal has no DVS.")


def inning_bucket(inning: int) -> str:
    inning = int(inning)
    for label, lo, hi in INNING_BUCKETS:
        if lo <= inning <= hi:
            return label
    return "9+"


def score_bucket(sd_home: int) -> str:
    v = max(-4, min(4, int(sd_home)))
    if v <= -4:
        return "<=-4"
    if v >= 4:
        return ">=+4"
    return f"{v:+d}" if v else "0"


def cell_key(season, inning, half, outs, base, sd_home) -> str:
    """The matched-state key. The score is HOME minus AWAY before the play; with the
    half in the key that fixes both clubs' views."""
    h = "bottom" if str(half).startswith("bot") else "top"
    return f"{int(season)}|{inning_bucket(inning)}|{h}|{int(outs)}|{int(base)}|{score_bucket(sd_home)}"


def _cells_from(ctx, keys, mwpa) -> dict:
    """Aggregate (cell, mwpa) pairs into {cell: {n, mean_mwpa, thin}} plus the identity."""
    import numpy as np
    import pandas as pd
    df = pd.DataFrame({"cell": keys, "mwpa": np.asarray(mwpa, dtype=float)})
    df = df[df["mwpa"].notna()]
    if df.empty:
        return {"cells": {}, "identity_max_abs": None, "n_windows": 0}
    g = df.groupby("cell")["mwpa"]
    n = g.size()
    mean = g.mean()
    resid = df["mwpa"] - g.transform("mean")
    ident = resid.groupby(df["cell"]).mean().abs().max()
    cells = {c: {"n": int(n[c]), "mean_mwpa": round(float(mean[c]), 5), "thin": bool(n[c] < MIN_CELL)}
             for c in n.index}
    return {"cells": cells, "identity_max_abs": float(ident), "n_windows": int(len(df))}


def _keys(ctx, idx):
    import numpy as np
    idx = np.asarray(idx, dtype=int)
    return [cell_key(ctx.season, ctx.inning[i], ctx.half[i], ctx.outs[i], ctx.base[i], ctx.sd[i])
            for i in idx]


def season_cells(ctx) -> dict:
    """The league windows of every shape for one season, from a mgmt_decisions.SeasonCtx.
    Returns {family: {cell: {n, mean_mwpa, thin}}} with the shared single-PA table
    aliased under pinch_hit and bunt, and the per-table identity under
    the "_meta" key."""
    import numpy as np
    n = ctx.n
    idx = np.arange(n)
    s_bat = np.where(ctx.bot, 1.0, -1.0)
    s_field = -s_bat
    tables: dict = {}
    # single plate appearance, batting perspective
    tables["single_pa"] = _cells_from(ctx, _keys(ctx, idx), s_bat * (ctx.wpa - ctx.wpb) / 100.0)
    # intentional walk: two-PA span whose first PA was pitched to, fielding perspective
    j = np.where(idx + 1 <= ctx.h_end, idx + 1, idx)
    keep = ctx.etype != "intent_walk"
    tables["intentional_walk"] = _cells_from(
        ctx, _keys(ctx, idx[keep]), (s_field * (ctx.wpa[j] - ctx.wpb) / 100.0)[keep])
    # pinch run: half-inning remainder from any state with a runner on, batting perspective
    keep = ctx.base != 0
    tables["pinch_run"] = _cells_from(
        ctx, _keys(ctx, idx[keep]), (s_bat * (ctx.wpa[ctx.h_end] - ctx.wpb) / 100.0)[keep])
    # defensive sub: rest of game, fielding perspective
    tables["defensive_sub"] = _cells_from(
        ctx, _keys(ctx, idx), s_field * (ctx.wpa[ctx.g_end] - ctx.wpb) / 100.0)
    # pitching change: every stint start to the end of the stint, fielding perspective
    starts, ends = [], []
    for key, rows in ctx.side_rows.items():
        p = ctx.pitcher[rows]
        p = np.where(np.isnan(p), -1.0, p)          # NaN != NaN would start a run on every row
        run_start = np.ones(len(rows), dtype=bool)
        run_start[1:] = p[1:] != p[:-1]
        # end of each run
        run_end = np.empty(len(rows), dtype=int)
        last = len(rows) - 1
        for k in range(len(rows) - 1, -1, -1):
            if k < len(rows) - 1 and run_start[k + 1]:
                last = k
            run_end[k] = last
        half_first = ctx.h_start[rows] == rows
        for k in np.flatnonzero(run_start | half_first):
            starts.append(int(rows[k]))
            ends.append(int(rows[run_end[k]]))
    starts = np.asarray(starts, dtype=int)
    ends = np.asarray(ends, dtype=int)
    tables["pitching_change"] = _cells_from(
        ctx, _keys(ctx, starts), s_field[starts] * (ctx.wpa[ends] - ctx.wpb[starts]) / 100.0)
    out = {f: tables[src]["cells"] for f, src in CELL_SOURCE.items()}
    out["_meta"] = {src: {"identity_max_abs": t["identity_max_abs"], "n_windows": t["n_windows"]}
                    for src, t in tables.items()}
    return out


def assemble(frames: dict) -> dict:
    """Merge per-season cell tables into the artifact. Cells carry the season in
    their key, so seasons never mix; the per-table identity is the max over seasons."""
    families: dict = {}
    for src in sorted(set(CELL_SOURCE.values())):
        cells: dict = {}
        ident = None
        nwin = 0
        for season, tab in frames.items():
            fam = next(f for f, s in CELL_SOURCE.items() if s == src)
            cells.update(tab.get(fam) or {})
            m = (tab.get("_meta") or {}).get(src) or {}
            if m.get("identity_max_abs") is not None:
                ident = m["identity_max_abs"] if ident is None else max(ident, m["identity_max_abs"])
            nwin += int(m.get("n_windows") or 0)
        # COMPACT CELLS: [n, mean_mwpa] per key, thin implied by n < min_cell. The
        # object form ({n, mean_mwpa, thin}) put the artifact over the registry's
        # 4,000,000-byte stamp-parse ceiling (model_registry._MAX_STAMP_PARSE_BYTES),
        # which reads a bigger file as UNDATED and ages it by checkout mtime.
        families[src] = {
            "n_windows": nwin, "n_cells": len(cells),
            "thin_cells": sum(1 for c in cells.values() if c["thin"]),
            "identity_max_abs": None if ident is None else float(f"{ident:.3g}"),
            "cells": {k: [c["n"], c["mean_mwpa"]] for k, c in cells.items()},
        }
    for f, src in CELL_SOURCE.items():
        if f != src:
            families[f] = {"same_cells_as": src,
                           "n_windows": families[src]["n_windows"], "n_cells": families[src]["n_cells"],
                           "thin_cells": families[src]["thin_cells"],
                           "identity_max_abs": families[src]["identity_max_abs"]}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "produced_by": "mgmt_baseline.py",
        "min_cell": MIN_CELL,
        "cell_columns": ["n", "mean_mwpa"],
        "cell_note": ("each cell is [n, mean_mwpa] (wins, realized, league windows from the "
                      "state); a cell is thin, and prices no decision, when n is below min_cell"),
        "buckets": {"inning": [b[0] for b in INNING_BUCKETS], "score_diff_home_minus_away": list(SCORE_BUCKETS),
                    "key": "season|inning bucket|half|outs|base code|score bucket"},
        "what_this_is": ("baseline_f(S) = the league mean realized window mWPA over every "
                         "window of the same shape from state S, decision or not; "
                         "DVS(d) = mWPA(d) - baseline_f(S(d)). Removes the level of the "
                         "state, not player quality and not selection. Descriptive, not skill."),
        "identity": ("within every cell the residuals of the league windows sum to zero by "
                     "construction; identity_max_abs is the largest absolute mean residual "
                     "found, checked not asserted"),
        "selection_caveat": SELECTION_CAVEAT,
        "single_pa_caveat": SINGLE_PA_CAVEAT,
        "where_dvs_lives": ("the per-decision drill-down and the League census only; never "
                            "a column on a club-season or manager row"),
        "families": families,
    }


def build(*, corpus: Path | None = None, seasons=None) -> dict:
    """Standalone build from the corpus (the nightly runs it through mgmt_decisions.build,
    which shares the season load)."""
    import mgmt_decisions as MD
    import mgmt_teams
    corpus = Path(corpus or MD.CORPUS)
    if not (corpus / "plays").exists():
        return {"status": f"not built: no corpus at {corpus}"}
    want = [int(s) for s in seasons] if seasons else MD.seasons_on_disk(corpus)
    tmap_raw = mgmt_teams.build_map(corpus=corpus)
    tmap = {g: {"home": MD._canon(v["home"]), "away": MD._canon(v["away"]), "season": v["season"]}
            for g, v in tmap_raw.items()}
    frames = {}
    for season in want:
        pl, ev, pi = MD.load_season(corpus, season)
        if pl.empty:
            continue
        ctx = MD.SeasonCtx(season, pl, ev, pi, tmap)
        frames[str(season)] = season_cells(ctx)
        log.info("mgmt_baseline: %s done", season)
    return assemble(frames)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default=None)
    ap.add_argument("--corpus", default=None)
    a = ap.parse_args(argv)
    seasons = [s.strip() for s in a.seasons.split(",")] if a.seasons else None
    d = build(corpus=Path(a.corpus) if a.corpus else None, seasons=seasons)
    OUT.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e3:.0f} KB)")
    for f, blk in (d.get("families") or {}).items():
        print(f"  {f:18s} windows={blk.get('n_windows'):>9,} cells={blk.get('n_cells'):>6,} "
              f"thin={blk.get('thin_cells')} identity={blk.get('identity_max_abs')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

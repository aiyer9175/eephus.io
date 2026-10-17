# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""The MiLB fielding runs eFV driver read, to docs/sdr-2026-08-18/MILB_FIELDING_RUNS_GATE.md
part 11 (registered at 935ce9b7, after estimand (b) passed). Development read: nothing served
moves and nothing served imports this module; passing candidates are handed to EFV_X3.

efv5_atlas.py is imported unchanged (its hitter table, labels, out-of-fold heads, cluster
bootstrap and BH q). The metric is mfr_row, the row's own level-season fielding runs per 1,000
innings (level-native, shrunk with the innings-weighted k of the positions played), from the
MFR build's season tables. Frames: the clean development frames only (reach3 and w3 on S <=
2021). Null N-d permutes the metric within (level, season); planted P-d is a synthetic metric
carrying a 0.3 label-rank signal.

    python tools/milb_fielding_runs_driver.py            # the read, once
    python tools/milb_fielding_runs_driver.py --dry-run  # the scoring path on a fixture table
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import milb_fielding_runs as M  # noqa: E402

OUT = ROOT / "data" / "_labs" / "milb_fielding_runs" / "driver_read.json"
LEVEL_SPORT = {"AAA": 11, "AA": 12, "A+": 13, "A": 14, "CPX": 16, "DSL": 16}
ROW_INN_MIN = 50.0
FRAME_MAX_S = 2021
LABELS_READ = ("reach3", "w3")
B_READ = 2000
SEED_BOOT = 20261021
SEED_FOLDS = 20261014
SEED_NULL = 20261022
SEED_PLANT = 20261023
PLANT_RHO = 0.3
CAND_Q = 0.10


def row_metric(st, kpos: dict) -> dict:
    """{(pid, season, sport): mfr_row} with ROW_INN_MIN+ innings (part 11)."""
    s = st.copy()
    s["k"] = s.pos.map(lambda p: kpos[str(p)]["k"]).astype(float)
    s["kin"] = s.k * s.inn
    g = s.groupby(["pid", "season", "sport"]).agg(runs=("runs", "sum"), inn=("inn", "sum"),
                                                  kin=("kin", "sum"))
    g = g[g.inn >= ROW_INN_MIN]
    kw = g.kin / g.inn
    val = 1000.0 * g.runs / (g.inn + kw)
    return {(int(a), int(b), int(c)): float(v) for (a, b, c), v in val.items()}


def _bh(ps: list) -> list:
    idx = [i for i, p in enumerate(ps) if p is not None]
    out = [None] * len(ps)
    if not idx:
        return out
    order = sorted(idx, key=lambda i: ps[i])
    m = len(order)
    q_prev = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        q = min(q_prev, ps[i] * m / rank)
        out[i] = round(q, 5)
        q_prev = q
    return out


def _candidate(r: dict) -> bool:
    ci = r.get("ci95")
    return (r.get("incr") is not None and r["incr"] > 0 and ci is not None and ci[0] > 0
            and r.get("q") is not None and r["q"] <= CAND_Q)


def score(T, A, log=print) -> dict:
    """Score mfr_row, the null and the planted metric on every registered cell."""
    rng = np.random.default_rng(SEED_NULL)
    x = T.x["mfr_row"]
    null = x.copy()
    for lv in np.unique(T.level):
        for s in np.unique(T.season):
            idx = np.flatnonzero((T.level == lv) & (T.season == s) & np.isfinite(x))
            null[idx] = x[idx][rng.permutation(idx.size)]
    T.x["mfr_null"] = null
    rngp = np.random.default_rng(SEED_PLANT)
    for label in LABELS_READ:
        y = T.y[label]
        z = np.full(T.n, np.nan)
        for s in np.unique(T.season):
            idx = np.flatnonzero((T.season == s) & np.isfinite(y))
            if idx.size < 3:
                continue
            r = A._ranks(y[idx])
            r = (r - r.mean()) / (r.std() or 1.0)
            z[idx] = PLANT_RHO * r + math.sqrt(1 - PLANT_RHO ** 2) * rngp.normal(0, 1, idx.size)
        T.x[f"planted_{label}"] = z
    folds_all = A.player_folds(T.pid, A.FOLDS, SEED_FOLDS)
    frame = T.season <= FRAME_MAX_S
    cells = []
    for lv in A.LEVELS:
        m_lv = (T.level == lv) & frame
        if not m_lv.any():
            continue
        for band in A.BANDS:
            m_b = m_lv if band == "all" else (m_lv & (T.band == band))
            for g in A.HIT_GROUPS:
                m = m_b if g == "all" else (m_b & (T.group == g))
                if np.unique(T.pid[m]).size < A.MIN_PLAYERS:
                    continue
                for label in LABELS_READ:
                    w = A.cell_weights(T, m, label, B_READ, SEED_BOOT)
                    if w is None:
                        continue
                    for metric, fam in (("mfr_row", "fielding"), ("mfr_null", "null"),
                                        (f"planted_{label}", "planted")):
                        r = A.score_cell(T, m, metric, label, B=B_READ, seed=SEED_BOOT,
                                         folds_all=folds_all, weights=w)
                        if r is None or "listed" not in r:
                            continue
                        li = r["listed"]
                        cells.append({"level": lv, "age_band": band, "group": g, "label": label,
                                      "metric": metric, "family": fam, "n": li["n"],
                                      "players": li["players"], "pos": li["pos"],
                                      "raw_listed": li["score"], "consensus_raw": li["consensus"],
                                      "model_c": li["model_c"], "model_cm": li["model_cm"],
                                      "incr": li["delta"], "ci95": li["ci95"], "p": li["p"],
                                      "q": None})
                log(f"  {lv} {band} {g}: {len(cells)} scored so far")
    for fam in ("fielding", "null", "planted"):
        for label in LABELS_READ:
            idx = [i for i, c in enumerate(cells) if c["family"] == fam and c["label"] == label]
            qs = _bh([cells[i]["p"] for i in idx])
            for i, q in zip(idx, qs):
                cells[i]["q"] = q
    for c in cells:
        c["candidate"] = _candidate(c)
    key = lambda c: (c["level"], c["age_band"], c["group"], c["label"])  # noqa: E731
    planted_ok = {key(c) for c in cells if c["family"] == "planted" and c["candidate"]}
    null_hits = [c for c in cells if c["family"] == "null" and c["candidate"]]
    real = [c for c in cells if c["family"] == "fielding"]
    for c in real:
        c["powered"] = key(c) in planted_ok
    cands = [c for c in real if c["candidate"] and c["powered"]]
    verdict = ("VOID" if null_hits else
               ("CANDIDATES" if cands else
                ("NO CANDIDATE" if any(c["powered"] for c in real) else "UNDERPOWERED")))
    return {"cells": cells, "real_cells": len(real), "powered_cells": sum(c["powered"] for c in real),
            "null_candidates": len(null_hits), "candidates": cands, "verdict": verdict}


def planted_same_rows(T, A, real_cells: list, log=print) -> list:
    """Part 10 note N2: P-d re-scored on the metric's own rows. The registered P-d was built
    on every labelled row of the frame (S <= 2021, back to 2005), while mfr_row exists only
    on S = 2021; this scores the same planted signal on the rows where mfr_row is finite, in
    the cells where mfr_row was scored. The metric itself is not re-scored."""
    rngp = np.random.default_rng(SEED_PLANT)
    have = np.isfinite(T.x["mfr_row"]) & (T.season <= FRAME_MAX_S)
    for label in LABELS_READ:
        y = T.y[label]
        z = np.full(T.n, np.nan)
        for s in np.unique(T.season[have]):
            idx = np.flatnonzero(have & (T.season == s) & np.isfinite(y))
            if idx.size < 3:
                continue
            r = A._ranks(y[idx])
            r = (r - r.mean()) / (r.std() or 1.0)
            z[idx] = PLANT_RHO * r + math.sqrt(1 - PLANT_RHO ** 2) * rngp.normal(0, 1, idx.size)
        T.x[f"planted_same_{label}"] = z
    folds_all = A.player_folds(T.pid, A.FOLDS, SEED_FOLDS)
    frame = T.season <= FRAME_MAX_S
    out = []
    for c in real_cells:
        m = (T.level == c["level"]) & frame
        if c["age_band"] != "all":
            m &= T.band == c["age_band"]
        if c["group"] != "all":
            m &= T.group == c["group"]
        w = A.cell_weights(T, m, c["label"], B_READ, SEED_BOOT)
        r = A.score_cell(T, m, f"planted_same_{c['label']}", c["label"], B=B_READ,
                         seed=SEED_BOOT, folds_all=folds_all, weights=w)
        li = (r or {}).get("listed")
        out.append({"level": c["level"], "age_band": c["age_band"], "group": c["group"],
                    "label": c["label"], "n": li["n"] if li else None,
                    "incr": li["delta"] if li else None, "ci95": li["ci95"] if li else None,
                    "p": li["p"] if li else None})
    qs = {}
    for label in LABELS_READ:
        idx = [i for i, o in enumerate(out) if o["label"] == label]
        for i, q in zip(idx, _bh([out[i]["p"] for i in idx])):
            qs[i] = q
    for i, o in enumerate(out):
        o["q"] = qs.get(i)
        o["candidate"] = _candidate(o)
    return out


def build_table(log=print):
    import pandas as pd
    import efv5_atlas as A
    mlb = A.mlb_seasons()
    war, vid = A.fwar_totals()
    listings = A.load_listings()
    universe = A.F.load_universe()
    cons = A.consensus_reads("hit", listings, universe=universe, log=log)
    T = A.build_table("hit", mlb=mlb, war=war, cons=cons, log=log)
    st = pd.read_parquet(M.TABLES / "season_table.parquet")
    meta = json.loads((M.TABLES / "build_meta.json").read_text(encoding="utf-8"))
    rm = row_metric(st, meta["k"])
    T.x["mfr_row"] = np.array([rm.get((int(p), int(s), LEVEL_SPORT.get(str(lv), -1)), np.nan)
                               for p, s, lv in zip(T.pid, T.season, T.level)], dtype=float)
    return T, A, {"fwar_vintage_id": vid, "rows": int(T.n),
                  "rows_with_metric": int(np.isfinite(T.x["mfr_row"]).sum()),
                  "rows_in_frame_with_metric": int((np.isfinite(T.x["mfr_row"])
                                                    & (T.season <= FRAME_MAX_S)).sum())}


def fixture_table(seed: int = 5):
    """A small atlas-shaped hitter table carrying None labels, for the dry run."""
    import efv5_atlas as A
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(900):
        lv = ["AAA", "AA", "A"][i % 3]
        y = {lb: None for lb in A.LABELS}
        reach = float(rng.random() < 0.3)
        y["reach3"] = reach if rng.random() > 0.05 else None
        y["w3"] = float(rng.normal() * reach) if rng.random() > 0.05 else None
        rows.append({"pid": 100000 + i // 3, "season": 2021, "level": lv,
                     "band": ["young", "average", "old"][i % 3], "group": "SS",
                     "fv": None if rng.random() < 0.1 else float(rng.choice([40, 45, 50, 55])),
                     "m": {"mfr_row": None if rng.random() < 0.1 else float(rng.normal())},
                     "y": y})
    return A.Table("hit", rows, ["mfr_row"]), A


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--planted-same-rows", action="store_true")
    a = ap.parse_args(argv)
    if a.planted_same_rows:
        doc = json.loads(OUT.read_text(encoding="utf-8"))
        real = [c for c in doc["cells"] if c["family"] == "fielding"]
        T, A, meta = build_table()
        res = planted_same_rows(T, A, real)
        out = OUT.with_name("driver_planted_same_rows.json")
        out.write_text(json.dumps({"generated_at": M._now(), "gate": M.GATE_DOC,
                                   "note": "part 10 note N2", "cells": res}, indent=1,
                                  default=str) + "\n", encoding="utf-8")
        print(json.dumps(res))
        return 0
    if a.dry_run:
        T, A = fixture_table()
        res = score(T, A, log=lambda *x: None)
        print(json.dumps({k: v for k, v in res.items() if k != "cells"}, default=str)[:600])
        print("dry run complete")
        return 0
    if OUT.exists():
        print(f"REFUSED: the driver read is spent ({OUT.name} exists)")
        return 3
    T, A, meta = build_table()
    print("table:", json.dumps(meta), flush=True)
    res = score(T, A)
    doc = {"generated_at": M._now(), "gate": M.GATE_DOC, "part": "11 (eFV driver read)",
           "registration": "935ce9b7", "read": "development only; nothing served moves",
           "frames": {"labels": list(LABELS_READ), "max_s": FRAME_MAX_S},
           "constants": {"B": B_READ, "seed_boot": SEED_BOOT, "seed_folds": SEED_FOLDS,
                         "seed_null": SEED_NULL, "seed_plant": SEED_PLANT, "plant_rho": PLANT_RHO,
                         "candidate_q": CAND_Q, "row_inn_min": ROW_INN_MIN,
                         "min_players": A.MIN_PLAYERS, "min_pos": A.MIN_POS},
           "table": meta, **res, "handoff": "EFV_X3 (candidates only, nothing more)"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("cells", "candidates")}))
    print("candidates:", json.dumps(res["candidates"])[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

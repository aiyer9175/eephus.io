# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Catcher value 2.0, the pure core (catcher_value_v2). docs/ewar/CATCHER_VALUE_2_GATE.md.

CV2 = FRM + BLK + THR per catcher-season, read from the pitch-level ledger
(docs/ewar/PITCH_LEDGER_GATE.md) over the steps he caught, fielding side positive:
  FRM = -sum x_frm, BLK = -sum (x_babs + x_blk), THR = -sum x_sres.
eABS is never inside CV2 (owner decision EW3-19 leaves its entry to the owner).

The validations of gate part 3 read: catcher_totals (V-P), wowy and refit_framing (V-S).
Pure: numpy and pandas, no I/O.
"""
from __future__ import annotations

import numpy as np

CATCHER_VALUE_VERSION = "catcher_value_v2"
GATE_DOC = "docs/ewar/CATCHER_VALUE_2_GATE.md"
FLOOR_CALLED = 2000          # gate 3.1: called pitches caught in both seasons
FLOOR_PA_HALF = 300          # gate 3.2: plate appearances caught in each half
SEED = 20261016
BOOT = 2000


def catcher_totals(steps) -> "object":
    """DataFrame by catcher_id: pitches, called, pa, FRM, BLK, THR, CV2, rate per 1,000 pitches."""
    import pandas as pd
    s = steps
    isp = s["kind"] == "p"
    g = s.groupby("catcher_id")
    out = pd.DataFrame({
        "pitches": isp.groupby(s["catcher_id"]).sum(),
        "called": g["called"].sum(),
        "FRM": -g["x_frm"].sum(),
        "BLK": -(g["x_babs"].sum() + g["x_blk"].sum()),
        "THR": -g["x_sres"].sum(),
    })
    pa = s[isp].drop_duplicates(["game_pk", "at_bat_index"]).groupby("catcher_id").size()
    out["pa"] = pa.reindex(out.index).fillna(0).astype(int)
    out["CV2"] = out["FRM"] + out["BLK"] + out["THR"]
    out["rate"] = 1000.0 * out["CV2"] / out["pitches"].where(out["pitches"] > 0)
    return out


def pa_table(steps):
    """One row per plate appearance: game, ab, fielding team, catcher and pitcher at its first
    pitch, runs saved (-sum dRE over every step of the plate appearance)."""
    import pandas as pd
    s = steps
    first = s[s["kind"] == "p"].drop_duplicates(["game_pk", "at_bat_index"])[
        ["game_pk", "at_bat_index", "fld_team_id", "catcher_id", "pitcher_id"]]
    tot = s.groupby(["game_pk", "at_bat_index"])["dre"].sum().rename("dre_pa").reset_index()
    pa = first.merge(tot, on=["game_pk", "at_bat_index"], how="left")
    pa["saved"] = -pa["dre_pa"]
    return pa


def wowy(pa, catcher, team) -> tuple[float | None, int]:
    """Gate 3.2: pitcher-matched runs saved per plate appearance with this catcher over the
    team's other catchers. pa: plate appearances of one team and half. (value, PA caught)."""
    t = pa[pa["fld_team_id"] == team]
    mine = t[t["catcher_id"] == catcher]
    other = t[t["catcher_id"] != catcher]
    if len(mine) == 0 or len(other) == 0:
        return None, int(len(mine))
    a = mine.groupby("pitcher_id")["saved"].agg(["mean", "size"])
    b = other.groupby("pitcher_id")["saved"].agg(["mean", "size"])
    j = a.join(b, lsuffix="_c", rsuffix="_o", how="inner")
    if len(j) == 0:
        return None, int(len(mine))
    w = 1.0 / (1.0 / j["size_c"] + 1.0 / j["size_o"])
    return float((w * (j["mean_c"] - j["mean_o"])).sum() / w.sum()), int(len(mine))


def refit_framing(called, sigma: dict):
    """Gate 3.2: refit the ledger's person effects (its part 4.2) on one half's called pitches
    and return -x_frm per row (fielding side positive). called: rows of the ledger with
    called & modelled, columns L_full_minus_effects, s1_call, v_called and the four ids."""
    import pitch_ledger as pl
    L0 = called["L_full_minus_effects"].to_numpy(dtype=float)
    y = called["s1_call"].to_numpy(dtype=float)
    idx = {}
    for g, col in (("catcher", "catcher_id"), ("pitcher", "pitcher_id"), ("batter", "batter_id"),
                   ("umpire", "hp_umpire_id")):
        a = called[col].to_numpy(dtype=float)
        a = np.where(np.isfinite(a), a, -1.0)
        idx[g], _ = pl.encode(a)
    b0, eff, _info = pl.fit_effects(L0, y, idx, sigma)
    sh, _ = pl.shares(L0 + b0, {g: eff[g][idx[g]] for g in pl.GROUPS})
    v = called["v_called"].to_numpy(dtype=float)
    return sh["catcher"] * v      # -x_frm = d_c * v


def pearson(x, y) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def spearman(x, y) -> float:
    from scipy.stats import rankdata
    return pearson(rankdata(x), rankdata(y))


def cluster_boot(stat, clusters, B: int = BOOT, seed: int = SEED):
    """Percentile bootstrap of stat(index array) drawing clusters with replacement."""
    rng = np.random.default_rng(seed)
    clusters = np.asarray(clusters)
    uniq = np.unique(clusters)
    members = {u: np.flatnonzero(clusters == u) for u in uniq}
    vals = []
    for _ in range(B):
        draw = rng.choice(uniq, size=len(uniq), replace=True)
        ix = np.concatenate([members[u] for u in draw])
        v = stat(ix)
        if np.isfinite(v):
            vals.append(v)
    vals = np.asarray(vals)
    if len(vals) == 0:
        return {"lo95": None, "hi95": None, "sd": None, "n_boot": 0}
    return {"lo95": float(np.percentile(vals, 2.5)), "hi95": float(np.percentile(vals, 97.5)),
            "sd": float(vals.std(ddof=1)), "n_boot": int(len(vals))}

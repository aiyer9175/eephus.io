#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""catcher_value_lab - catcher value 2.0's census and its two validations.

docs/ewar/CATCHER_VALUE_2_GATE.md. Reads the pitch ledger (.cache/ewar_innovate_ledger/ledger),
the cached game feeds for game start times (read only), the cached StatsAPI sabermetrics files,
data/fielding_innings.json, Savant's cached catcher boards and data/eabs_leaderboards.json.
Writes data/_labs/ewar_innovate/catcher_value_eval.json and per-catcher values under
.cache/ewar_innovate_ledger/catcher_value/.

  --dry-run   the whole reporting path on a synthetic fixture with nulls; writes nothing tracked
  (default)   the census (part 2), V-P (3.1) and V-S (3.2) once, on 2018 and 2019 only
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import random
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for p in (str(ROOT), str(TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

import catcher_value as cvl  # noqa: E402
import pitch_ledger as pl  # noqa: E402

LEDGER = ROOT / ".cache" / "ewar_innovate_ledger" / "ledger"
CACHE = ROOT / ".cache" / "ewar_innovate_ledger" / "catcher_value"
FEEDS = ROOT / ".cache" / "win_prob"
OUT = ROOT / "data" / "_labs" / "ewar_innovate" / "catcher_value_eval.json"
CENSUS_SEASONS = (2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)
DEV = (2018, 2019)
COLS = ["game_pk", "at_bat_index", "kind", "catcher_id", "pitcher_id", "batter_id", "hp_umpire_id",
        "fld_team_id", "called", "modelled", "x_frm", "x_babs", "x_blk", "x_sres", "x_ch", "dre",
        "L_full_minus_effects", "s1_call", "v_called", "challenger_id", "challenge_side"]


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def load(season: int):
    import pandas as pd
    return pd.read_parquet(LEDGER / f"{season}.parquet", columns=COLS)


def game_starts(seasons) -> dict:
    """{game_pk: first play start time} from the cached feeds (read only), cached locally."""
    import orjson
    import pandas as pd
    f = CACHE / "game_start.json"
    have = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    for s in seasons:
        if str(s) in have:
            continue
        gks = pd.read_parquet(LEDGER / f"{s}.parquet", columns=["game_pk"])["game_pk"].unique()
        m = {}
        for gk in gks:
            p = FEEDS / f"{int(gk)}.json"
            if not p.exists():
                continue
            plays = orjson.loads(p.read_bytes())
            t = None
            for pl_ in plays:
                t = (pl_.get("about") or {}).get("startTime")
                if t:
                    break
            m[str(int(gk))] = t
        have[str(s)] = m
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(have), encoding="utf-8")
    return have


def halves(steps, starts: dict):
    """Per (fielding team, game): 0 for the team's odd-numbered games, 1 for even (gate 3.2)."""
    g = steps[["fld_team_id", "game_pk"]].drop_duplicates().copy()
    g["t"] = [starts.get(str(int(k))) or "" for k in g["game_pk"]]
    g = g.sort_values(["fld_team_id", "t", "game_pk"])
    g["n"] = g.groupby("fld_team_id").cumcount() + 1
    g["half"] = (g["n"] % 2 == 0).astype(int)
    return g[["fld_team_id", "game_pk", "half"]]


# --------------------------------------------------------------------------
# V-P (gate 3.1)
# --------------------------------------------------------------------------
def v_p(t0, t1, fg0=None, fg1=None, seed: int = cvl.SEED, B: int = cvl.BOOT) -> dict:
    """t0, t1: catcher_totals of the two seasons. fg0/fg1: {id: rate} comparators."""
    a = t0[t0.called >= cvl.FLOOR_CALLED]
    b = t1[t1.called >= cvl.FLOOR_CALLED]
    ids = sorted(set(a.index) & set(b.index))
    x = a.loc[ids, "rate"].to_numpy()
    y = b.loc[ids, "rate"].to_numpy()
    rng = random.Random(seed)
    order = sorted(a.index)
    perm = order[:]
    rng.shuffle(perm)
    pmap = dict(zip(order, perm))
    xt = np.array([a.loc[pmap[i], "rate"] for i in ids])
    cl = np.arange(len(ids))
    boot = cvl.cluster_boot(lambda ix: cvl.spearman(x[ix], y[ix]), cl, B, seed)
    tw = cvl.cluster_boot(lambda ix: cvl.spearman(xt[ix], y[ix]), cl, B, seed)
    out = {"n_pairs": len(ids), "floor_called": cvl.FLOOR_CALLED,
           "boot_sd": boot["sd"], "mde95": (1.645 * boot["sd"]) if boot["sd"] is not None else None,
           "rho": cvl.spearman(x, y), "lo95": boot["lo95"], "hi95": boot["hi95"],
           "twin_rho": cvl.spearman(xt, y), "twin_lo95": tw["lo95"], "twin_hi95": tw["hi95"]}
    out["pass"] = bool(out["lo95"] is not None and out["lo95"] > 0 and tw["lo95"] is not None and tw["lo95"] <= 0)
    if fg0 is not None and fg1 is not None:
        j = [i for i in ids if fg0.get(int(i)) is not None and fg1.get(int(i)) is not None]
        if len(j) >= 5:
            fx = np.array([fg0[int(i)] for i in j])
            fy = np.array([fg1[int(i)] for i in j])
            fb = cvl.cluster_boot(lambda ix: cvl.spearman(fx[ix], fy[ix]), np.arange(len(j)), B, seed)
            out["comparator_fangraphs"] = {"n_pairs": len(j), "rho": cvl.spearman(fx, fy),
                                           "lo95": fb["lo95"], "hi95": fb["hi95"],
                                           "note": "reported beside, no weight"}
    return out


# --------------------------------------------------------------------------
# V-S (gate 3.2)
# --------------------------------------------------------------------------
def half_units(steps, hv, sigma: dict, log=print):
    """Per (team, catcher, half): CV2 per PA caught (refit framing on the half) and WOWY."""
    import pandas as pd
    s = steps.merge(hv, on=["fld_team_id", "game_pk"], how="left")
    out = []
    pa_all = cvl.pa_table(s)
    pa_all = pa_all.merge(hv, on=["fld_team_id", "game_pk"], how="left")
    for h in (0, 1):
        sh = s[s["half"] == h]
        called = sh[sh["called"] & sh["modelled"]]
        frm = cvl.refit_framing(called, sigma)
        fr = pd.Series(frm, index=called.index).groupby(called["catcher_id"]).sum()
        fr_team = pd.Series(frm, index=called.index).groupby([called["fld_team_id"], called["catcher_id"]]).sum()
        blk = -(sh["x_babs"] + sh["x_blk"]).groupby([sh["fld_team_id"], sh["catcher_id"]]).sum()
        thr = -sh["x_sres"].groupby([sh["fld_team_id"], sh["catcher_id"]]).sum()
        ph = pa_all[pa_all["half"] == h]
        npa = ph.groupby(["fld_team_id", "catcher_id"]).size()
        for (team, c), n in npa.items():
            if n < 1:
                continue
            w, _ = cvl.wowy(ph, c, team)
            f = float(fr_team.get((team, c), 0.0))
            out.append({"team": team, "catcher": c, "half": h, "pa": int(n),
                        "FRM": f, "BLK": float(blk.get((team, c), 0.0)), "THR": float(thr.get((team, c), 0.0)),
                        "wowy": w})
        log(f"    half {h}: {len(called):,} called pitches refitted, {len(npa)} catcher-team units")
    u = pd.DataFrame(out)
    u["CV2"] = u["FRM"] + u["BLK"] + u["THR"]
    for c in ("CV2", "FRM", "BLK", "THR"):
        u[c + "_pa"] = u[c] / u["pa"]
    return u


def v_s_observations(units_by_season: dict, fg_rate: dict | None = None):
    """Rows (season, team, catcher, cv2_h centred, wowy_other_h centred) for qualifying units."""
    import pandas as pd
    rows = []
    for s, u in units_by_season.items():
        q = u.groupby(["team", "catcher"])["pa"].min()
        ok = set(k for k, v in q.items() if v >= cvl.FLOOR_PA_HALF)
        uu = u[[(t, c) in ok for t, c in zip(u.team, u.catcher)]].copy()
        for h in (0, 1):
            a = uu[uu.half == h].set_index(["team", "catcher"])
            b = uu[uu.half == 1 - h].set_index(["team", "catcher"])
            j = a.join(b, lsuffix="_m", rsuffix="_o", how="inner")
            j = j[j["wowy_o"].notna()]
            if len(j) == 0:
                continue
            for comp in ("CV2_pa", "FRM_pa", "BLK_pa", "THR_pa"):
                w = j["pa_m"]
                mu = (j[comp + "_m"] * w).groupby(level=0).transform("sum") / w.groupby(level=0).transform("sum")
                j[comp + "_c"] = j[comp + "_m"] - mu
            wo = j["pa_o"]
            muw = (j["wowy_o"] * wo).groupby(level=0).transform("sum") / wo.groupby(level=0).transform("sum")
            j["wowy_c"] = j["wowy_o"] - muw
            for (team, c), r in j.iterrows():
                rows.append({"season": s, "team": team, "catcher": c, "h": h,
                             "cv2": r["CV2_pa_c"], "frm": r["FRM_pa_c"], "blk": r["BLK_pa_c"],
                             "thr": r["THR_pa_c"], "wowy": r["wowy_c"],
                             "fg": (fg_rate or {}).get((s, int(c)))})
    return pd.DataFrame(rows)


def v_s(obs, seed: int = cvl.SEED, B: int = cvl.BOOT) -> dict:
    x = obs["cv2"].to_numpy(dtype=float)
    y = obs["wowy"].to_numpy(dtype=float)
    cl = obs["catcher"].to_numpy()
    boot = cvl.cluster_boot(lambda ix: cvl.pearson(x[ix], y[ix]), cl, B, seed)
    # twin: CV2 permuted among the catchers of the same team-season (and half)
    rng = random.Random(seed)
    xt = x.copy()
    grp = obs.groupby(["season", "team", "h"]).indices
    singles = 0
    for k in sorted(grp, key=lambda z: (z[0], z[1], z[2])):
        ix = list(grp[k])
        if len(ix) < 2:
            singles += 1
            continue
        perm = ix[:]
        rng.shuffle(perm)
        xt[ix] = x[perm]
    tw = cvl.cluster_boot(lambda ix: cvl.pearson(xt[ix], y[ix]), cl, B, seed)
    out = {"n_obs": int(len(obs)), "n_catchers": int(len(np.unique(cl))),
           "n_team_seasons": int(obs.groupby(["season", "team"]).ngroups) if len(obs) else 0,
           "boot_sd": boot["sd"], "mde95": (1.645 * boot["sd"]) if boot["sd"] else None,
           "r": cvl.pearson(x, y), "lo95": boot["lo95"], "hi95": boot["hi95"],
           "twin_r": cvl.pearson(xt, y), "twin_lo95": tw["lo95"], "twin_hi95": tw["hi95"],
           "twin_single_catcher_groups": singles}
    out["pass"] = bool(out["lo95"] is not None and out["lo95"] > 0 and tw["lo95"] is not None and tw["lo95"] <= 0)
    beside = {}
    for comp in ("frm", "blk", "thr"):
        xc = obs[comp].to_numpy(dtype=float)
        b2 = cvl.cluster_boot(lambda ix, xc=xc: cvl.pearson(xc[ix], y[ix]), cl, B, seed)
        beside[comp] = {"r": cvl.pearson(xc, y), "lo95": b2["lo95"], "hi95": b2["hi95"]}
    if "fg" in obs and obs["fg"].notna().sum() >= 5:
        o2 = obs[obs["fg"].notna()]
        fx = o2["fg"].to_numpy(dtype=float)
        fy = o2["wowy"].to_numpy(dtype=float)
        b3 = cvl.cluster_boot(lambda ix: cvl.pearson(fx[ix], fy[ix]), o2["catcher"].to_numpy(), B, seed)
        beside["fangraphs_season_not_held_out"] = {"n_obs": int(len(o2)), "r": cvl.pearson(fx, fy),
                                                   "lo95": b3["lo95"], "hi95": b3["hi95"]}
    out["beside_no_weight"] = beside
    return out


# --------------------------------------------------------------------------
# comparators and the census
# --------------------------------------------------------------------------
def fg_catcher(season: int) -> dict:
    """{mlbam: (fld + frm, innings at C)} for catchers, from cached files only."""
    import saber_feed
    f = ROOT / ".cache" / f"{saber_feed.cache_key(season)}.json"
    inn = json.loads((ROOT / "data" / "fielding_innings.json").read_text(encoding="utf-8"))["seasons"].get(str(season), {})
    if not f.exists():
        return {}
    stats = json.loads(f.read_text(encoding="utf-8")).get("stats") or []
    splits = (stats[0].get("splits") or []) if stats else []
    rows, _, _ = saber_feed.resolve_groups(splits, require="fielding")
    out = {}
    for pid, row in rows.items():
        c_inn = ((inn.get(str(pid)) or {}).get("C") or {}).get("inn")
        if not c_inn:
            continue
        st = row.get("stat") or {}
        fld = saber_feed.run_value(st.get("fielding"))
        frm = saber_feed.framing_residual(st) or 0.0
        if fld is None:
            continue
        out[int(pid)] = (float(fld) + float(frm), float(c_inn))
    return out


def savant_col(name: str, season: int, col: str) -> dict:
    f = ROOT / ".cache" / "savant_catcher" / f"{name}_{season}.csv"
    if not f.exists():
        return {}
    out = {}
    with open(f, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            try:
                out[int(r["player_id"])] = float(r[col])
            except (KeyError, ValueError, TypeError):
                pass
    return out


def census(totals: dict) -> dict:
    res = {}
    for s, t in totals.items():
        a = t[t.called >= cvl.FLOOR_CALLED]
        var = {k: float(a[k].var()) for k in ("FRM", "BLK", "THR", "CV2")}
        fg = fg_catcher(s)
        th = savant_col("throwing", s, "catcher_stealing_runs")
        bl = savant_col("blocking", s, "catcher_blocking_runs")

        def r_with(col, ref):
            j = [(a.loc[i, col], ref[int(i)]) for i in a.index if int(i) in ref]
            return (cvl.pearson([x for x, _ in j], [y for _, y in j]), len(j)) if len(j) > 2 else (None, len(j))
        r_fg = r_with("CV2", {k: v[0] for k, v in fg.items()})
        r_th = r_with("THR", th)
        r_bl = r_with("BLK", bl)
        res[str(s)] = {"catchers_at_floor": int(len(a)),
                       "sd_runs": {k: float(a[k].std()) for k in ("FRM", "BLK", "THR", "CV2")},
                       "sd_per_1000_pitches": float(a["rate"].std()),
                       "variance_share_of_parts": {k: (var[k] / var["CV2"] if var["CV2"] else None)
                                                   for k in ("FRM", "BLK", "THR")},
                       "r_cv2_vs_fangraphs_catcher_runs": r_fg[0], "n_fg": r_fg[1],
                       "r_thr_vs_savant_stealing_runs": r_th[0], "n_savant_throwing": r_th[1],
                       "r_blk_vs_savant_blocking_runs": r_bl[0], "n_savant_blocking": r_bl[1]}
    return res


def eabs_beside(t26) -> dict:
    f = ROOT / "data" / "eabs_leaderboards.json"
    if not f.exists():
        return {}
    board = json.loads(f.read_text(encoding="utf-8")).get("boards", {}).get("catchers") or []
    a = t26[t26.called >= cvl.FLOOR_CALLED]
    raw = {int(r["mlbam"]): r.get("raw") for r in board}
    j = [(a.loc[i, "CV2"], raw[int(i)]) for i in a.index if int(i) in raw and raw[int(i)] is not None]
    vals = [y for _, y in j]
    return {"catchers_joined": len(j), "eabs_raw_median": float(np.median(vals)) if vals else None,
            "eabs_raw_share_under_2_runs": float(np.mean(np.abs(vals) < 2)) if vals else None,
            "r_cv2_vs_eabs_raw": cvl.pearson([x for x, _ in j], vals) if len(j) > 2 else None,
            "eabs_inside_cv2": False}


# --------------------------------------------------------------------------
# the fixture (dry run and tests)
# --------------------------------------------------------------------------
def fixture(planted: bool, seed: int = 7):
    """Synthetic catcher totals (two seasons) and V-S observations with nulls."""
    import pandas as pd
    rng = np.random.default_rng(seed)
    n = 60
    talent = rng.normal(0, 1.0, n) if planted else np.zeros(n)
    ids = np.arange(1000, 1000 + n).astype(float)

    def tot():
        r = talent + rng.normal(0, 0.6, n)
        return pd.DataFrame({"called": 3000, "rate": r, "CV2": r * 10, "FRM": r * 8, "BLK": r, "THR": r}, index=ids)
    t0, t1 = tot(), tot()
    t0.loc[ids[0], "rate"] = np.nan          # a null
    t0 = t0.dropna()
    rows = []
    for s in (2018, 2019):
        for k in range(n // 2):
            for c in (2 * k, 2 * k + 1):
                for h in (0, 1):
                    rows.append({"season": s, "team": k, "catcher": ids[c], "h": h,
                                 "cv2": talent[c] + rng.normal(0, 0.5), "frm": 0.0, "blk": 0.0, "thr": 0.0,
                                 "wowy": 0.8 * talent[c] + rng.normal(0, 0.5), "fg": None})
    obs = pd.DataFrame(rows)
    for (s, k, h), ix in obs.groupby(["season", "team", "h"]).groups.items():
        obs.loc[ix, "cv2"] -= obs.loc[ix, "cv2"].mean()
        obs.loc[ix, "wowy"] -= obs.loc[ix, "wowy"].mean()
    obs.loc[obs.index[0], "wowy"] = np.nan
    obs = obs.dropna(subset=["wowy"])
    return t0, t1, obs


def dry_run(log=print) -> dict:
    res = {}
    for planted in (True, False):
        t0, t1, obs = fixture(planted)
        a = v_p(t0, t1, B=300)
        b = v_s(obs, B=300)
        res["planted" if planted else "null"] = {"v_p_pass": a["pass"], "v_s_pass": b["pass"],
                                                 "rho": a["rho"], "r": b["r"]}
    ok = (res["planted"]["v_p_pass"] and res["planted"]["v_s_pass"]
          and not res["null"]["v_p_pass"] and not res["null"]["v_s_pass"])
    res["dry_run_pass"] = bool(ok)
    log(json.dumps(res, indent=1))
    return res


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------
def run(log=print) -> dict:
    import pandas as pd
    t_start = time.time()
    dr = dry_run(log=lambda *a: None)
    if not dr["dry_run_pass"]:
        raise SystemExit("dry run failed: nothing is read")
    sigma = dict(pl.SIGMA)
    totals = {}
    for s in CENSUS_SEASONS:
        st = load(s)
        totals[s] = cvl.catcher_totals(st)
        log(f"  census {s}: {int((totals[s].called >= cvl.FLOOR_CALLED).sum())} catchers at the floor")
    cen = census(totals)
    eb = eabs_beside(totals[2026])
    CACHE.mkdir(parents=True, exist_ok=True)
    for s, t in totals.items():
        t.to_csv(CACHE / f"totals_{s}.csv")
    # V-P
    fg = {s: fg_catcher(s) for s in DEV}
    fg_rate = {s: {k: 1000.0 * v[0] / v[1] for k, v in fg[s].items() if v[1] > 0} for s in DEV}
    vp = v_p(totals[2018], totals[2019], fg_rate[2018], fg_rate[2019])
    log(f"  V-P: n {vp['n_pairs']}, boot sd {vp['boot_sd']:.4f}, MDE95 {vp['mde95']:.4f}")
    log(f"  V-P: rho {vp['rho']:.4f} [{vp['lo95']:.4f}, {vp['hi95']:.4f}], twin {vp['twin_rho']:.4f} "
        f"[{vp['twin_lo95']:.4f}, {vp['twin_hi95']:.4f}] -> {'pass' if vp['pass'] else 'fail'}")
    # V-S: planted recovery and null on a simulated copy of 2018 first
    starts = game_starts(DEV)
    units, steps_by = {}, {}
    for s in DEV:
        st = load(s)
        hv = halves(st, starts[str(s)])
        steps_by[s] = (st, hv)
    log("  V-S planted recovery on a simulated copy of 2018:")
    st18, hv18 = steps_by[2018]
    sim = simulate_vs(st18, hv18, sigma, log)
    if not sim["pass"]:
        out = {"stopped": "V-S planted recovery or null failed on the simulated copy", "simulation": sim}
        _write(out)
        raise SystemExit("V-S simulation failed: the real read does not run")
    for s in DEV:
        st, hv = steps_by[s]
        log(f"  V-S {s}:")
        units[s] = half_units(st, hv, sigma, log)
        units[s].to_csv(CACHE / f"vs_units_{s}.csv", index=False)
    fgr = {(s, k): v for s in DEV for k, v in ({kk: (fg[s][kk][0] / fg[s][kk][1]) for kk in fg[s] if fg[s][kk][1] > 0}).items()}
    obs = v_s_observations(units, fgr)
    obs.to_csv(CACHE / "vs_observations.csv", index=False)
    vs = v_s(obs)
    log(f"  V-S: obs {vs['n_obs']}, catchers {vs['n_catchers']}, boot sd {vs['boot_sd']:.4f}, MDE95 {vs['mde95']:.4f}")
    log(f"  V-S: r {vs['r']:.4f} [{vs['lo95']:.4f}, {vs['hi95']:.4f}], twin {vs['twin_r']:.4f} "
        f"[{vs['twin_lo95']:.4f}, {vs['twin_hi95']:.4f}] -> {'pass' if vs['pass'] else 'fail'}")
    verdict = "DEV PASS" if (vp["pass"] and vs["pass"]) else "NOT VALIDATED"
    if (vp["lo95"] is not None and vp["twin_lo95"] is not None and vp["twin_lo95"] > 0) or \
       (vs["lo95"] is not None and vs["twin_lo95"] is not None and vs["twin_lo95"] > 0):
        verdict = "VOID"
    out = {"schema": 1, "version": cvl.CATCHER_VALUE_VERSION, "gate_doc": cvl.GATE_DOC, "generated_at": _now(),
           "sigma": sigma, "seed": cvl.SEED, "boot": cvl.BOOT, "dry_run": dr, "census": cen,
           "eabs_beside_2026": eb, "v_p": vp, "v_s_simulation": sim, "v_s": vs, "verdict": verdict,
           "seconds": round(time.time() - t_start, 1)}
    _write(out)
    log(f"  verdict: {verdict}")
    return out


def simulate_vs(st, hv, sigma, log=print) -> dict:
    """Gate 3.2's planted recovery: catcher identities on the outcome side shuffled within
    (team, half) for the null; the null plus each catcher's season CV2 per PA for the plant."""
    import pandas as pd
    u = half_units(st, hv, sigma, log=lambda *a: None)
    tot = cvl.catcher_totals(st)
    rate_pa = (tot["CV2"] / tot["pa"].where(tot["pa"] > 0)).to_dict()
    pa = cvl.pa_table(st).merge(hv, on=["fld_team_id", "game_pk"], how="left")
    rng = np.random.default_rng(cvl.SEED)
    res = {}
    for label in ("null", "planted"):
        p2 = pa.copy()
        # null: shuffle the outcome within (team, half, pitcher) so catcher carries no signal
        p2["saved"] = p2.groupby(["fld_team_id", "half", "pitcher_id"])["saved"].transform(
            lambda x: x.sample(frac=1.0, random_state=int(rng.integers(1 << 30))).to_numpy())
        if label == "planted":
            p2["saved"] = p2["saved"] + p2["catcher_id"].map(rate_pa).fillna(0.0) * 5.0
        uu = u.copy()
        w = []
        for _, r in uu.iterrows():
            ph = p2[p2["half"] == r["half"]]
            w.append(cvl.wowy(ph, r["catcher"], r["team"])[0])
        uu["wowy"] = w
        obs = v_s_observations({2018: uu})
        res[label] = v_s(obs, B=500)
        log(f"    {label}: r {res[label]['r']:.4f} [{res[label]['lo95']:.4f}, {res[label]['hi95']:.4f}] "
            f"pass {res[label]['pass']}")
    res["pass"] = bool(res["planted"]["pass"] and not res["null"]["pass"])
    res["plant"] = "outcome = shuffled runs saved + 5 x the catcher's season CV2 per PA"
    return res


def _write(obj) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True, default=float) + "\n", encoding="utf-8")
    tmp.replace(OUT)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.dry_run:
        r = dry_run()
        return 0 if r["dry_run_pass"] else 2
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

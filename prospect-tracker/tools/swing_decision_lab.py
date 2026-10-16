#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""swing_decision_lab - swing-decision value: its census and test X.

docs/ewar/SWING_DECISION_GATE.md. Reads the pitch ledger (.cache/ewar_innovate_ledger/ledger),
the corpus plays (bunt flags), data/count_value.json, the cached Savant expected statistics and
StatsAPI season lines. Writes data/_labs/ewar_innovate/swing_decision_eval.json (and the K_SD
fit log), per-batter values under .cache/ewar_innovate_ledger/swing_decision/.

  --fit-k     the one 2018 fit of K_SD (gate part 2.5); writes its log only
  --dry-run   test X's reporting path on a synthetic fixture with nulls
  (default)   the census (part 3) and test X (part 4) once; test E (part 5) is not run
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import io
import json
import math
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

import pitch_ledger as pl  # noqa: E402
import swing_decision as sd  # noqa: E402

LEDGER = ROOT / ".cache" / "ewar_innovate_ledger" / "ledger"
CORPUS = ROOT / ".cache" / "pbp_corpus"
CACHE_DIR = ROOT / ".cache"
OUT_CACHE = ROOT / ".cache" / "ewar_innovate_ledger" / "swing_decision"
OUT = ROOT / "data" / "_labs" / "ewar_innovate" / "swing_decision_eval.json"
K_LOG = ROOT / "data" / "_labs" / "ewar_innovate" / "swing_decision_k_fit.json"
COUNT_VALUE = ROOT / "data" / "count_value.json"
CENSUS_SEASONS = (2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)
SEED = 20261016
BOOT = 2000
K_UBB = 120.0
COLS = ["game_pk", "at_bat_index", "kind", "call_code", "pitch_type", "plate_x", "plate_z", "sz_top",
        "sz_bot", "bat_side", "pitch_hand", "b0", "s0c", "bits0", "o0", "batter_id", "x_x", "dre",
        "v_before", "called", "modelled", "s1_call"]


class LabStop(RuntimeError):
    pass


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True, default=float) + "\n", encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------
# the measure over one season
# --------------------------------------------------------------------------
def season_frame(season: int, doc: dict):
    """Every decision of the season with DV (gate parts 2.1 to 2.4)."""
    import pandas as pd
    from build_pitch_ledger import ball_strike_values, tables
    st = pd.read_parquet(LEDGER / f"{season}.parquet", columns=COLS)
    bunt = pd.read_parquet(CORPUS / "plays" / str(season) / f"plays-{season}.parquet",
                           columns=["game_pk", "at_bat_index", "bunted"])
    st = st.merge(bunt, on=["game_pk", "at_bat_index"], how="left")
    st["bunted"] = st["bunted"].fillna(False).astype(bool)
    code = st["call_code"].astype(object).to_numpy()
    p = st[(st.kind == "p") & (st.b0 < 4) & (st.s0c < 3) & (st.o0 < 3)].copy()
    code = p["call_code"].astype(object).to_numpy()
    xm = pl.mirrored_x(p.plate_x.to_numpy(), p.bat_side.astype(object).to_numpy())
    zn = pl.zone_height(p.plate_z.to_numpy(), p.sz_bot.to_numpy(), p.sz_top.to_numpy())
    has = np.isfinite(xm) & np.isfinite(zn)
    is_take = np.array([c in sd.TAKES for c in code])
    is_swing = np.array([c in sd.SWINGS for c in code])
    inplay = np.array([c in sd.IN_PLAY for c in code])
    keep = has & (is_take | is_swing) & ~(inplay & p["bunted"].to_numpy())
    p = p[keep].copy()
    p["xm"], p["zn"] = xm[keep], zn[keep]
    p["take"] = is_take[keep]
    code = p["call_code"].astype(object).to_numpy()
    p["w"] = np.array([c in sd.WHIFF for c in code], dtype=float)
    p["f"] = np.array([c in sd.FOUL for c in code], dtype=float)
    p["ip"] = np.array([c in sd.IN_PLAY for c in code], dtype=float)
    # league called-strike model p0 (the ledger's part 4.1), refitted on the same rows
    hand = np.array([pl.hand_key(b, q) for b, q in zip(p.bat_side.astype(object), p.pitch_hand.astype(object))])
    cg = np.array([pl.count_group(int(b), int(s)) for b, s in zip(p.b0, p.s0c)])
    cm = (p["called"] & p["modelled"]).to_numpy()
    lm = pl.fit_league(p.xm.to_numpy()[cm], p.zn.to_numpy()[cm], hand[cm], cg[cm], p.s1_call.to_numpy()[cm])
    p["p0"] = lm.predict(p.xm.to_numpy(), p.zn.to_numpy(), hand, cg)
    # state values
    t288, re24 = tables(doc, season)
    VB, VS = ball_strike_values(t288, re24)
    b, s, bt, o = (p[c].to_numpy().astype(int) for c in ("b0", "s0c", "bits0", "o0"))
    p["v_ball"] = VB[b, s, bt, o]
    p["v_strike"] = VS[b, s, bt, o]
    # m_bo and r on balls in play (the ledger's 5.1)
    ipm = p["ip"].to_numpy() == 1
    m_bo = p[ipm].groupby(["bits0", "o0"])["dre"].mean()
    p["m_bo"] = [m_bo.get((x, y), 0.0) for x, y in zip(p.bits0, p.o0)]
    p["r_ip"] = np.where(ipm, p["x_x"].to_numpy() - p["m_bo"].to_numpy(), 0.0)
    # cells (gate 2.3): swings only
    pg = np.array([pl.pitch_group(t) for t in p.pitch_type.astype(object)])
    p["loc"] = sd.loc_bins(p.xm, p.zn)
    p["parent"] = p["loc"] * 100 + pg * 10 + p["s0c"]
    p["cell"] = p["loc"] * 10000 + pg * 1000 + p["b0"] * 10 + p["s0c"]
    sw = p[~p["take"]].copy()
    sw["one"] = 1.0
    rates = sd.shrunk_rates(sw, ["w", "f", "ip"], "one", "loc", "parent", "cell")
    ipsw = sw[sw["ip"] == 1].copy()
    ipsw["one"] = 1.0
    rr = sd.shrunk_rates(ipsw, ["r_ip"], "one", "loc", "parent", "cell")
    cell_rates = {}
    for c in ("w", "f", "ip"):
        cell_rates[c] = dict(zip(sw["cell"], rates[c]))
        # fall back to the parent, then the location, for take-only cells
        cell_rates[c + "_par"] = sw.assign(v=rates[c]).groupby("parent")["v"].mean().to_dict()
        cell_rates[c + "_loc"] = sw.assign(v=rates[c]).groupby("loc")["v"].mean().to_dict()
    r_cell = dict(zip(ipsw["cell"], rr["r_ip"]))
    r_par = ipsw.assign(v=rr["r_ip"]).groupby("parent")["v"].mean().to_dict()
    r_loc = ipsw.assign(v=rr["r_ip"]).groupby("loc")["v"].mean().to_dict()

    def look(c, par, loc, dc, dp, dl, default):
        if c in dc:
            return dc[c]
        if par in dp:
            return dp[par]
        return dl.get(loc, default)
    cells, pars, locs = p["cell"].to_numpy(), p["parent"].to_numpy(), p["loc"].to_numpy()
    shares = {}
    for c in ("w", "f", "ip"):
        shares[c] = np.array([look(a, b_, l_, cell_rates[c], cell_rates[c + "_par"], cell_rates[c + "_loc"], np.nan)
                              for a, b_, l_ in zip(cells, pars, locs)])
    tot = shares["w"] + shares["f"] + shares["ip"]
    for c in shares:
        shares[c] = np.where(np.isfinite(tot) & (tot > 0), shares[c] / np.where(tot > 0, tot, 1), np.nan)
    rl = np.array([look(a, b_, l_, r_cell, r_par, r_loc, 0.0) for a, b_, l_ in zip(cells, pars, locs)])
    dv, vt, vs = sd.decision_values(p.v_before, p.v_ball, p.v_strike, p.s0c, p.p0.to_numpy(),
                                    shares["w"], shares["f"], shares["ip"], p.m_bo.to_numpy(), rl,
                                    p["take"].to_numpy())
    p["dv"] = dv
    p["vt"], p["vs"] = vt, vs
    p = p[np.isfinite(p["dv"].to_numpy())]
    return p


def batter_order(p):
    """Each batter's plate-appearance sequence number (game_pk, at_bat_index order)."""
    pa = p[["batter_id", "game_pk", "at_bat_index"]].drop_duplicates().sort_values(["batter_id", "game_pk", "at_bat_index"])
    pa["seq"] = pa.groupby("batter_id").cumcount()
    return p.merge(pa, on=["batter_id", "game_pk", "at_bat_index"], how="left")


# --------------------------------------------------------------------------
# StatsAPI and Savant
# --------------------------------------------------------------------------
def _num(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) else 0.0


def load_lines(year: int) -> dict:
    doc = json.loads((CACHE_DIR / f"fa_statsapi_hitting_{int(year)}.json").read_text(encoding="utf-8"))
    out = {}
    for s in (doc.get("stats") or [{}])[0].get("splits") or []:
        st = s.get("stat") or {}
        try:
            pid = int(s["player"]["id"])
        except (TypeError, ValueError, KeyError):
            continue
        row = {"pa": _num(st.get("plateAppearances")), "pitches": _num(st.get("numberOfPitches")),
               "ab": _num(st.get("atBats")), "bb": _num(st.get("baseOnBalls")),
               "ibb": _num(st.get("intentionalWalks")), "hbp": _num(st.get("hitByPitch")),
               "sf": _num(st.get("sacFlies")), "so": _num(st.get("strikeOuts")),
               "pos": (s.get("position") or {}).get("abbreviation")}
        if pid not in out or row["pa"] > out[pid]["pa"]:
            out[pid] = row
    return out


def load_savant(year: int) -> dict:
    path = CACHE_DIR / "savant_mlb" / f"expected_batter_{int(year)}.csv"
    out = {}
    for r in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig", errors="replace"))):
        try:
            out[int(r["player_id"])] = (float(r["woba"]), float(r["est_woba"]), float(r["pa"]))
        except (TypeError, ValueError, KeyError):
            continue
    return out


def ubb(ln):
    return max(0.0, ln["bb"] - ln["ibb"])


def denom(ln):
    return ln["ab"] + ln["bb"] - ln["ibb"] + ln["sf"] + ln["hbp"]


def line_ok(ln):
    return bool(ln) and ln["pa"] > 0 and denom(ln) > 0


# --------------------------------------------------------------------------
# K_SD (gate 2.5)
# --------------------------------------------------------------------------
def fit_k(doc: dict, log=print) -> dict:
    p = season_frame(2018, doc)
    lines = load_lines(2018)
    p = p[[(lines.get(int(b)) or {}).get("pos") != "P" for b in p.batter_id]]
    dvbar = float(p["dv"].mean())
    p = batter_order(p)
    tot = sd.batter_totals(p.batter_id.to_numpy(), p.dv.to_numpy(), dvbar)
    q = tot[tot.decisions >= sd.SPLIT_FLOOR]
    halves = {}
    for h in (0, 1):
        ph = p[(p["seq"] % 2) == h]
        halves[h] = sd.batter_totals(ph.batter_id.to_numpy(), ph.dv.to_numpy(), dvbar)
    ids = [i for i in q.index if i in halves[0].index and i in halves[1].index]
    res = sd.split_half_k(halves[0].loc[ids, "SD100"], halves[1].loc[ids, "SD100"], q.loc[ids, "decisions"])
    res.update({"season": 2018, "rule": "gate part 2.5", "dvbar": dvbar, "generated_at": _now()})
    _write(K_LOG, res)
    log(json.dumps(res, indent=1))
    return res


# --------------------------------------------------------------------------
# test X (gate part 4)
# --------------------------------------------------------------------------
def spearman(x, y) -> float:
    from scipy.stats import rankdata
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    return float(np.corrcoef(rankdata(x), rankdata(y))[0, 1])


def boot_gaps(arms: dict, tgt, B: int, seed: int) -> dict:
    """iid pair bootstrap; one pair per player, so the player-clustered draw is the same."""
    rng = random.Random(seed)
    n = len(tgt)
    tgt = np.asarray(tgt, dtype=float)
    keys = [k for k in arms if k != "N"]
    draws = {k: [] for k in keys}
    for _ in range(B):
        ix = np.array([rng.randrange(n) for _ in range(n)])
        rn = spearman(arms["N"][ix], tgt[ix])
        for k in keys:
            draws[k].append(spearman(arms[k][ix], tgt[ix]) - rn)
    out = {}
    for k in keys:
        v = np.asarray(draws[k])
        out[k] = {"gap": spearman(arms[k], tgt) - spearman(arms["N"], tgt),
                  "lo95": float(np.percentile(v, 2.5)), "hi95": float(np.percentile(v, 97.5)),
                  "sd": float(v.std(ddof=1)), "mde95": float(1.645 * v.std(ddof=1)),
                  "share_at_or_below_0": float((v <= 0).mean())}
    return out


def arms_for(pool: dict, lines: dict, sdt: dict, b: float, lgbb: float, w_ubb: float, gain: float,
             perm: dict | None = None, b_override: float | None = None):
    """xHEM+ per served-pool hitter for one arm (gate 4.2)."""
    bb = b if b_override is None else b_override
    xw = {}
    for mid, (wo, ew, pa) in pool.items():
        ln = lines.get(mid)
        if not line_ok(ln):
            xw[mid] = ew
            continue
        s = (perm or sdt).get(mid, 0.0)
        r_raw = ubb(ln) / denom(ln)
        T = max(0.0, lgbb + bb * s)
        r_shr = (ubb(ln) + K_UBB * T) / (denom(ln) + K_UBB)
        xw[mid] = ew + w_ubb * (r_shr - r_raw)
    tot = sum(pool[m][2] for m in pool)
    poolm = sum(xw[m] * pool[m][2] for m in pool) / tot
    return {m: 100.0 + gain * (100.0 * xw[m] / poolm - 100.0) for m in pool}


def test_x(sav0, sav1, lines, sdt, lgbb, w_ubb, b, gain, B=BOOT, seed=SEED) -> dict:
    pool = {m: v for m, v in sav0.items() if v[2] >= 100 and v[1] > 0}
    # the twin: SD~ permuted across served-pool hitters with a valid line, by MLBAM order
    order = sorted(m for m in pool if line_ok(lines.get(m)))
    vals = [sdt.get(m, 0.0) for m in order]
    rng = random.Random(seed)
    rng.shuffle(vals)
    perm = dict(zip(order, vals))
    N = {m: 100.0 + gain * (100.0 * pool[m][1] / (sum(pool[k][1] * pool[k][2] for k in pool)
                                                    / sum(pool[k][2] for k in pool)) - 100.0) for m in pool}
    V = arms_for(pool, lines, sdt, b, lgbb, w_ubb, gain)
    P = arms_for(pool, lines, sdt, b, lgbb, w_ubb, gain, perm=perm)
    M = arms_for(pool, lines, sdt, b, lgbb, w_ubb, gain, b_override=0.0)
    pairs = [m for m in pool if pool[m][2] >= 200 and m in sav1 and sav1[m][2] >= 200
             and line_ok(lines.get(m)) and m in sdt]
    pairs.sort()
    tgt = np.array([sav1[m][0] for m in pairs])
    arms = {k: np.array([a[m] for m in pairs]) for k, a in (("N", N), ("V", V), ("P", P), ("M", M))}
    rho = {k: spearman(v, tgt) for k, v in arms.items()}
    g = boot_gaps(arms, tgt, B, seed)
    out = {"n_pairs": len(pairs), "rho": rho, "gaps_v1": g,
           "gaps_v2": g, "v2_note": "one outcome season and one pair per player: v2 equals v1"}
    vok = g["V"]["lo95"] > 0
    pok = g["P"]["lo95"] <= 0
    out["verdict"] = "DEV PASS" if (vok and pok) else ("VOID" if (vok and not pok) else "NOT VALIDATED")
    return out


def fit_b(lines: dict, sdt: dict) -> dict:
    xs, ys = [], []
    for mid, ln in lines.items():
        if ln.get("pos") == "P" or ln["pa"] < 300 or not line_ok(ln) or mid not in sdt:
            continue
        xs.append(sdt[mid])
        ys.append(ubb(ln) / denom(ln))
    if len(xs) < 200:
        raise LabStop(f"b fit: {len(xs)} hitters, under 200")
    x, y = np.asarray(xs), np.asarray(ys)
    b = float(((x - x.mean()) * (y - y.mean())).sum() / ((x - x.mean()) ** 2).sum())
    if not math.isfinite(b):
        raise LabStop("b is not finite")
    return {"b": b, "n": len(xs)}


# --------------------------------------------------------------------------
# fixture (dry run and tests)
# --------------------------------------------------------------------------
def fixture(planted: bool, seed: int = 11):
    """Walk talent tied to the measure (planted) or not (null); the observed walk rate is
    noisy, the next season's wOBA carries the walk talent."""
    rng = np.random.default_rng(seed)
    n = 320
    ids = list(range(500000, 500000 + n))
    skill = rng.normal(0, 1, n)
    sdt = {m: 0.004 * skill[i] for i, m in enumerate(ids)}
    lines, sav0, sav1 = {}, {}, {}
    for i, m in enumerate(ids):
        pa = float(rng.integers(300, 420))
        talent_bb = 0.085 + (0.03 * skill[i] if planted else 0.0)
        bb = max(1.0, rng.binomial(int(pa), min(max(talent_bb, 0.01), 0.3)) + 0.0)
        lines[m] = {"pa": pa, "pitches": pa * 3.9, "ab": pa - bb - 7.0, "bb": bb + 1.0, "ibb": 1.0,
                    "hbp": 3.0, "sf": 3.0, "so": pa * 0.22, "pos": "SS"}
        base = 0.320 + rng.normal(0, 0.02)
        ew = base + 0.69 * (bb / pa - 0.085)
        sav0[m] = (ew, ew, pa)
        nxt = 0.5 * base + 0.16 + 0.69 * (talent_bb - 0.085) + rng.normal(0, 0.012)
        sav1[m] = (nxt, nxt, pa)
    sav0[ids[0]] = (float("nan"), 0.0, 120.0)      # a null that the pair floor drops
    return sav0, sav1, lines, sdt


def dry_run(log=print) -> dict:
    res = {}
    for planted in (True, False):
        sav0, sav1, lines, sdt = fixture(planted)
        lg = sum(ubb(l) for l in lines.values()) / sum(denom(l) for l in lines.values())
        b = fit_b(lines, sdt)["b"]
        r = test_x(sav0, sav1, lines, sdt, lg, 0.69, b, 2.28, B=300)
        res["planted" if planted else "null"] = {"verdict": r["verdict"], "gap": r["gaps_v1"]["V"]["gap"],
                                                 "twin_lo95": r["gaps_v1"]["P"]["lo95"]}
    res["dry_run_pass"] = bool(res["planted"]["verdict"] == "DEV PASS" and res["null"]["verdict"] != "DEV PASS")
    log(json.dumps(res, indent=1))
    return res


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------
def census(doc: dict, log=print) -> tuple[dict, dict]:
    import pandas as pd
    res, by_season = {}, {}
    for s in CENSUS_SEASONS:
        p = season_frame(s, doc)
        lines = load_lines(s)
        p = p[[(lines.get(int(b)) or {}).get("pos") != "P" for b in p.batter_id]]
        dvbar = float(p["dv"].mean())
        tot = sd.batter_totals(p.batter_id.to_numpy(), p.dv.to_numpy(), dvbar)
        z = pl.rulebook_strike(p.xm.to_numpy(), p.plate_z.to_numpy(), p.sz_bot.to_numpy(), p.sz_top.to_numpy())
        out_zone = z == 0
        ch = pd.DataFrame({"b": p.batter_id.to_numpy(), "oz": out_zone, "sw": ~p["take"].to_numpy()})
        chase = ch[ch.oz].groupby("b")["sw"].mean()
        q = tot[tot.decisions >= sd.SPLIT_FLOOR].copy()
        q["bb"] = [(ubb(lines[int(i)]) / lines[int(i)]["pa"]) if int(i) in lines and lines[int(i)]["pa"] else np.nan for i in q.index]
        q["k"] = [(lines[int(i)]["so"] / lines[int(i)]["pa"]) if int(i) in lines and lines[int(i)]["pa"] else np.nan for i in q.index]
        q["ppa"] = [(lines[int(i)]["pitches"] / lines[int(i)]["pa"]) if int(i) in lines and lines[int(i)]["pa"] else np.nan for i in q.index]
        q["chase"] = chase.reindex(q.index).to_numpy()
        qq = q.dropna()
        res[str(s)] = {"decisions": int(len(p)), "dvbar_runs_per_decision": dvbar,
                       "take_share": float(p["take"].mean()),
                       "batters_at_1000": int(len(q)), "sd_SD100": float(q["SD100"].std()),
                       "sd_SD_runs": float(q["SD"].std()),
                       "spearman_with": {c: spearman(qq["SD100"], qq[c]) for c in ("bb", "k", "chase", "ppa")}}
        OUT_CACHE.mkdir(parents=True, exist_ok=True)
        tot.sort_values("SD100").to_csv(OUT_CACHE / f"batters_{s}.csv")
        by_season[s] = tot
        log(f"  census {s}: {len(p):,} decisions, {len(q)} batters at 1,000, sd SD100 {res[str(s)]['sd_SD100']:.3f}")
    return res, by_season


def run(log=print) -> dict:
    import hem_plus
    import league_constants as lc
    t0 = time.time()
    if sd.K_SD is None:
        raise LabStop("K_SD is not frozen: run --fit-k first")
    dr = dry_run(log=lambda *a: None)
    if not dr["dry_run_pass"]:
        raise LabStop("dry run failed")
    doc = json.loads(COUNT_VALUE.read_text(encoding="utf-8"))
    cen, by = census(doc, log)
    # test X, 2018 to 2019
    t18 = by[2018]
    sdt = {int(i): float(v) for i, v in zip(t18.index, sd.shrunk(t18["SD"], t18["decisions"], sd.K_SD))}
    lines = load_lines(2018)
    lg = (sum(ubb(l) for l in lines.values() if l["pa"] > 0)
          / sum(denom(l) for l in lines.values() if l["pa"] > 0))
    c = lc.constants(2018) or {}
    if c.get("season") != 2018:
        raise LabStop("league constants for 2018 are not that season's own")
    w_ubb = float(c["woba_weights"]["ubb"])
    bfit = fit_b(lines, sdt)
    log(f"  b = {bfit['b']:.4f} on {bfit['n']} hitters (2018, same season, no outcome)")
    sav0, sav1 = load_savant(2018), load_savant(2019)
    tx = test_x(sav0, sav1, lines, sdt, lg, w_ubb, bfit["b"], hem_plus.HEM_SPREAD_GAIN)
    g = tx["gaps_v1"]
    log(f"  test X: {tx['n_pairs']} pairs; MDE95 V-N {g['V']['mde95']:.4f}")
    log(f"  test X: V-N {g['V']['gap']:+.4f} [{g['V']['lo95']:+.4f}, {g['V']['hi95']:+.4f}]; "
        f"P-N {g['P']['gap']:+.4f} [{g['P']['lo95']:+.4f}, {g['P']['hi95']:+.4f}]; "
        f"M-N {g['M']['gap']:+.4f} -> {tx['verdict']}")
    out = {"schema": 1, "version": sd.SWING_DECISION_VERSION, "gate_doc": sd.GATE_DOC, "generated_at": _now(),
           "K_SD": sd.K_SD, "seed": SEED, "boot": BOOT, "dry_run": dr, "census": cen,
           "test_x": {"b_fit": bfit, "lgBB_2018": lg, "w_ubb_2018": w_ubb, **tx},
           "test_e": {"status": "not run: waits for a second AAA season with a resolved label (gate part 5)",
                      "earliest": "after the 2027 season (S = 2024 reach3)"},
           "seconds": round(time.time() - t0, 1)}
    _write(OUT, out)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit-k", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.dry_run:
        return 0 if dry_run()["dry_run_pass"] else 2
    doc = json.loads(COUNT_VALUE.read_text(encoding="utf-8"))
    if a.fit_k:
        fit_k(doc)
        return 0
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

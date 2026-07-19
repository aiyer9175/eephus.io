# T1-10 pHEM+ Marcel-lite lab (wave 3, pre-registered 2026-07-15)
#
# CANDIDATE (pHEM+ Marcel-lite, hitters primary):
#   Pool raw wOBA-component COUNTS over y-2..y with decayed weights (grid
#   {5/4/3, 6/3/1, flat}, normalized so year-y weight = 1), ONE EB shrink on
#   the pooled sample using the hem_plus constants (K_UBB..K_HR) against the
#   YEAR-y pool component means, re-index vs the year-y pool anchor
#   (100 * shrunk_wOBA / pool.mean_woba), plus an age delta:
#   score + beta * max(0, age_{y+1} - 30), beta fit by OLS
#   (target ~ a + b*score + c*hinge, beta = c/b) on TRAIN only.
#
# HYPERPARAMETER PROTOCOL: decay grid AND the hinge beta are fit ONLY on
# predictor years <= 2018 (per side), frozen, then gated on the holdout.
# Interpretation of "gated on 2019+ outcomes (complete only)": the gate set is
# predictor years >= 2019 (outcome seasons 2020, 2022, 2023, 2024, 2025 -- all
# complete past Nov 15; outcome 2019 belongs to the predictor-2018 TRAIN pairs
# and is excluded from the gate to keep the holdout leak-free).
#
# MANDATORY ARMS (hitters):
#   1. 1yr HEM+          (hem_plus_raw year y)                   [incumbent]
#   2. flat-3yr HEM+     (X-H2 PA-weighted trailing 3yr)         [incumbent]
#   3. textbook Marcel on wOBA (5/4/3 unnormalized, +1200 PA of the year-y
#      pool wOBA, Tango age multiplier at age 29)                [candidate]
#   4. fa_projection projected wOBA (repo Marcel engine, point-in-time
#      fitted_models(max_season=y) caches -- fully offline)      [candidate]
#   5. pHEM+ Marcel-lite (the registered candidate)              [candidate]
#
# GATE (v1 convention, seed 20260715, 2000 reps): winner = best candidate arm
# by gate Spearman vs raw wOBA(Y+1); SHIP iff paired iid-bootstrap
# lo95(winner - BEST incumbent arm) >= 0. pass_under_v2 (within-outcome-season
# z target + player-clustered season-stratified bootstrap) reported alongside.
#
# PAIR SET: replicates the X-H2 construction EXACTLY (tools/hem_plus_lab.py):
# SEASONS 2012..2024 ex-2020, MIN_PA 150/150, 3yr window su>=2 & PA>=600, only
# seasons present in by_season enter windows (2010/2011/2020 never loaded, as
# in the incumbent lab). Pairs additionally require every arm defined (age +
# fa-projection availability); drops counted.
#
# PITCHERS (pre-declared secondary, likely provisional): same design on the
# SEM+ family (sem_plus constants, TBF shrink exposure, year-y starter pool),
# target -RA9(Y+1), seasons 2012..2024 ex-2020, MIN_IP 50/40, window su>=2 &
# IP>=120. Textbook Marcel arm uses Tango's pitcher convention (3/2/1,
# +1220 TBF of the year-y pool runs/TBF). Arm 4 = -fip_proj.
#
# Offline: cached StatsAPI splits (.cache/fa_statsapi_*), fa_corpus.pkl,
# fa_fits_{y}_2000.pkl, xstats.pkl. No repo writes; artifacts go to the
# workspace. All stochastic steps seeded (20260715).
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("EEPHUS_ROOT")
            or r"C:/Users/noah/baseball-projects/BaseballR/prospect-tracker")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import numpy as np  # noqa: E402

import hem_plus  # noqa: E402
import hitter_export as he  # noqa: E402
import sem_plus  # noqa: E402
import fa_sources  # noqa: E402
import fa_projection as fap  # noqa: E402
import plus_lab_harness as plh  # noqa: E402
from rem_plus_backtest import _spearman  # noqa: E402
from bullpen_export import ip_to_float  # noqa: E402
import starter_export as se  # noqa: E402

SEED = 20260715
BOOT = 2000
SEASONS_HIT = [2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024]
SEASONS_PIT = list(SEASONS_HIT)
TRAIN_MAX_PRED_YEAR = 2018
MIN_PA_Y, MIN_PA_NEXT = 150.0, 150.0
MIN_IP_Y, MIN_IP_NEXT = 50.0, 40.0
TAG_MIN_SEASONS = 2
TAG_MIN_PA = 600.0          # hitters, X-H2 bar
TAG_MIN_IP = 120.0          # pitchers, X-S2 bar

# decay grid: (w_y, w_{y-1}, w_{y-2}) normalized so the year-y weight is 1
DECAY_GRID = {"5/4/3": (1.0, 0.8, 0.6),
              "6/3/1": (1.0, 0.5, 1.0 / 6.0),
              "flat":  (1.0, 1.0, 1.0)}

MARCEL_HIT_W = (5.0, 4.0, 3.0)      # textbook, unnormalized
MARCEL_HIT_REG = 1200.0             # PA of league average
MARCEL_PIT_W = (3.0, 2.0, 1.0)      # Tango pitcher convention
MARCEL_PIT_REG = 1220.0             # TBF of league average


def _r4(v):
    return None if v is None else round(v, 4)


# --------------------------------------------------------------------------- #
# season loading -- hitters (replicates hem_plus_lab.load_season + counts + age)
# --------------------------------------------------------------------------- #
def _split_ages(season: int, group: str) -> dict:
    ages = {}
    for r in fa_sources.fetch_statsapi_season_stats(season, group):
        pid = (r.get("player") or {}).get("id")
        a = (r.get("stat") or {}).get("age")
        if pid and a:
            try:
                ages[int(pid)] = int(a)
            except (TypeError, ValueError):
                pass
    return ages


def load_hit_season(y: int) -> tuple[dict, "hem_plus.Pool"]:
    rows = he.load_season_hitting(y)
    if not rows:
        return {}, None
    ages = _split_ages(y, "hitting")
    hitters = he.build_hitters(rows)
    pool_input = [h for h in hitters if hem_plus._woba_denom(h) > 0]
    for h in pool_input:
        hem_plus.derive_rates(h)
    pool = hem_plus.build_pool(pool_input)
    out = {}
    for h in pool_input:
        hem_plus.hem_plus(h, pool)
        if h.hem_plus_raw is None or h.woba_raw is None:
            continue
        d = hem_plus._woba_denom(h)
        out[h.mlbam] = {
            "name": h.name, "hem_plus_raw": h.hem_plus_raw,
            "woba_raw": h.woba_raw, "ops": h.rates.get("ops"),
            "avg": h.rates.get("avg"), "pa": h.pa, "age": ages.get(h.mlbam),
            # raw wOBA-component counts for the Marcel-lite pooling
            "cnt": {"ubb": max(0.0, (h.bb or 0) - (h.ibb or 0)), "hbp": h.hbp or 0.0,
                    "s1": hem_plus._singles(h), "s2": h.doub or 0.0,
                    "s3": h.trip or 0.0, "hr": h.hr or 0.0, "d": d},
        }
    return out, pool


def _hem3(by_season, mid, y):
    num = den = 0.0
    su = 0
    for yy in (y - 2, y - 1, y):
        rec = (by_season.get(yy) or {}).get(mid)
        if rec and rec.get("hem_plus_raw") is not None and rec.get("pa"):
            num += rec["hem_plus_raw"] * rec["pa"]; den += rec["pa"]; su += 1
    return (num / den if den else None), su, den


def phem_pool_score(by_season, pools, mid, y, w3) -> float | None:
    """pHEM+ Marcel-lite core (pre-hinge): decayed pooled counts -> ONE EB
    shrink (hem_plus constants, year-y pool means) -> re-index vs year-y pool."""
    wmap = {y: w3[0], y - 1: w3[1], y - 2: w3[2]}
    tot = {k: 0.0 for k in ("ubb", "hbp", "s1", "s2", "s3", "hr", "d")}
    used = 0
    for yy in (y - 2, y - 1, y):
        rec = (by_season.get(yy) or {}).get(mid)
        if not rec:
            continue
        c = rec["cnt"]
        if c["d"] <= 0:
            continue
        w = wmap[yy]
        for k in tot:
            tot[k] += w * c[k]
        used += 1
    D = tot["d"]
    if D <= 0 or not used:
        return None
    pool = pools[y]
    sh = {
        "ubb": hem_plus._shrink(tot["ubb"] / D, D, hem_plus.K_UBB, pool.mean_ubb),
        "hbp": hem_plus._shrink(tot["hbp"] / D, D, hem_plus.K_HBP, pool.mean_hbp),
        "s1": hem_plus._shrink(tot["s1"] / D, D, hem_plus.K_1B, pool.mean_1b),
        "s2": hem_plus._shrink(tot["s2"] / D, D, hem_plus.K_2B, pool.mean_2b),
        "s3": hem_plus._shrink(tot["s3"] / D, D, hem_plus.K_3B, pool.mean_3b),
        "hr": hem_plus._shrink(tot["hr"] / D, D, hem_plus.K_HR, pool.mean_hr),
    }
    w = (hem_plus.W_UBB * sh["ubb"] + hem_plus.W_HBP * sh["hbp"]
         + hem_plus.W_1B * sh["s1"] + hem_plus.W_2B * sh["s2"]
         + hem_plus.W_3B * sh["s3"] + hem_plus.W_HR * sh["hr"])
    if pool.mean_woba <= 0:
        return None
    ratio = 100.0 * w / pool.mean_woba
    return 100.0 + hem_plus.HEM_SPREAD_GAIN * (ratio - 100.0)   # monotone display parity


def marcel_woba(by_season, pools, mid, y, age_next) -> float | None:
    """Textbook Marcel on wOBA: 5/4/3 unnormalized count weights, +1200 PA of
    the year-y pool wOBA, Tango age multiplier around 29 (age in the projected
    season)."""
    wmap = {y: MARCEL_HIT_W[0], y - 1: MARCEL_HIT_W[1], y - 2: MARCEL_HIT_W[2]}
    num = den = 0.0
    for yy in (y - 2, y - 1, y):
        rec = (by_season.get(yy) or {}).get(mid)
        if not rec or rec["cnt"]["d"] <= 0:
            continue
        w = wmap[yy]
        num += w * rec["cnt"]["d"] * rec["woba_raw"]
        den += w * rec["cnt"]["d"]
    if den <= 0:
        return None
    lg = pools[y].pool_woba
    proj = (num + MARCEL_HIT_REG * lg) / (den + MARCEL_HIT_REG)
    if age_next is not None:
        adj = (29 - age_next) * (0.006 if age_next < 29 else 0.003)
        proj *= (1.0 + adj)
    return proj


# --------------------------------------------------------------------------- #
# arm 4 -- fa_projection point-in-time projected wOBA / FIP
# --------------------------------------------------------------------------- #
class FaEngine:
    def __init__(self):
        self.corpus = fap.build_corpus()
        self.league = self.corpus["league"]
        self.hist_hit = {}
        self.hist_pit = {}
        for r in self.corpus["hit"]:
            if r.get("mlbam") is not None:
                self.hist_hit.setdefault(int(r["mlbam"]), []).append(r)
        for r in self.corpus["pit"]:
            if r.get("mlbam") is not None:
                self.hist_pit.setdefault(int(r["mlbam"]), []).append(r)
        self._fits = {}

    def curves(self, max_season: int):
        if max_season not in self._fits:
            self._fits[max_season] = fap.fitted_models(self.corpus, max_season)[0]
        return self._fits[max_season]

    def proj(self, side: str, mid: int, y: int, age_next) -> dict | None:
        hist = (self.hist_hit if side == "hit" else self.hist_pit).get(mid)
        if not hist:
            return None
        rows = [h for h in hist if 0 < (y + 1) - h["season"] <= 3]
        if not rows:
            return None
        if age_next is None:
            r0 = max(rows, key=lambda h: h["season"])
            age_next = (r0["age"] + (y + 1 - r0["season"])) if r0.get("age") else None
        try:
            return fap.project_player(rows, side, y + 1, self.curves(y),
                                      self.league, age_next)
        except Exception:
            return None


# --------------------------------------------------------------------------- #
# season loading -- pitchers (SEM+ family, offline via fa_sources cache)
# --------------------------------------------------------------------------- #
def load_pit_season(y: int) -> tuple[dict, "sem_plus.Pool"]:
    splits = fa_sources.fetch_statsapi_season_stats(y, "pitching")
    if not splits:
        return {}, None
    rows = []
    ages = {}
    for s in splits:
        st = s.get("stat") or {}
        pl = s.get("player") or {}
        pid = pl.get("id")
        if not pid:
            continue
        pos = (s.get("position") or {}).get("abbreviation")
        if pos and pos != "P":
            continue
        if st.get("age"):
            try:
                ages[int(pid)] = int(st["age"])
            except (TypeError, ValueError):
                pass
        rows.append({
            "mlbam": int(pid), "name": pl.get("fullName", ""), "team": "",
            "G": st.get("gamesPitched"), "GS": st.get("gamesStarted"),
            "IP": st.get("inningsPitched"), "ER": st.get("earnedRuns"),
            "R": st.get("runs"), "BB": st.get("baseOnBalls"),
            "SO": st.get("strikeOuts"), "HR": st.get("homeRuns"),
            "HBP": st.get("hitByPitch"), "BF": st.get("battersFaced"),
            "CG": st.get("completeGames"), "GO": st.get("groundOuts"),
            "AO": st.get("airOuts"),
        })
    starters = se.build_starters(rows, None)
    pool_in = [s for s in starters if sem_plus.is_true_starter(s)]
    for s in pool_in:
        sem_plus.derive_rates(s)
    pool = sem_plus.build_pool(pool_in, gb_adjust=False)
    out = {}
    for s in pool_in:
        v = sem_plus.sem_plus(s, pool, gb_adjust=False)
        if v is None or s.rates.get("ra9") is None:
            continue
        out[s.mlbam] = {
            "name": s.name, "sem_plus_raw": s.sem_plus_raw,
            "ra9": s.rates["ra9"], "era": s.rates.get("era"),
            "ip": s.ip, "tbf": s.tbf, "r": s.r, "age": ages.get(s.mlbam),
            "cnt": {"so": s.so, "bb": s.bb, "hbp": s.hbp, "hr": s.hr,
                    "tbf": s.tbf, "ip": s.ip},
        }
    return out, pool


def _sem3(by_season, mid, y):
    num = den = 0.0
    su = 0
    for yy in (y - 2, y - 1, y):
        rec = (by_season.get(yy) or {}).get(mid)
        if rec and rec.get("sem_plus_raw") is not None and rec.get("ip"):
            num += rec["sem_plus_raw"] * rec["ip"]; den += rec["ip"]; su += 1
    return (num / den if den else None), su, den


def psem_pool_score(by_season, pools, mid, y, w3) -> float | None:
    """Pitcher Marcel-lite core: decayed pooled FIP-component counts -> ONE EB
    shrink (sem_plus/rem_plus constants, year-y starter pool) -> re-index."""
    wmap = {y: w3[0], y - 1: w3[1], y - 2: w3[2]}
    tot = {k: 0.0 for k in ("so", "bb", "hbp", "hr", "tbf", "ip")}
    used = 0
    for yy in (y - 2, y - 1, y):
        rec = (by_season.get(yy) or {}).get(mid)
        if not rec or rec["cnt"]["tbf"] <= 0 or rec["cnt"]["ip"] <= 0:
            continue
        w = wmap[yy]
        for k in tot:
            tot[k] += w * rec["cnt"][k]
        used += 1
    T, I = tot["tbf"], tot["ip"]
    if T <= 0 or I <= 0 or not used:
        return None
    pool = pools[y]
    k = sem_plus._shrink(tot["so"] / T, T, sem_plus.K_STRIKEOUT, pool.mean_k_pct)
    bb = sem_plus._shrink(tot["bb"] / T, T, sem_plus.K_WALK, pool.mean_bb_pct)
    hbp = sem_plus._shrink(tot["hbp"] / T, T, sem_plus.K_HBP, pool.mean_hbp_pct)
    hr = sem_plus._shrink(tot["hr"] / T, T, sem_plus.K_HOMERUN, pool.mean_hr_rate)
    fip = (sem_plus.FIP_HR * hr * T + sem_plus.FIP_BBHBP * (bb + hbp) * T
           - sem_plus.FIP_K * k * T) / I + pool.cfip
    fip = max(fip, 1.0)
    return 100.0 * pool.mean_fip / fip


def marcel_ra(by_season, pools_runrate, mid, y, age_next) -> float | None:
    """Textbook pitcher Marcel on runs-per-TBF (target-aligned with RA9):
    3/2/1 unnormalized, +1220 TBF of the year-y pool runs/TBF, Tango age
    multiplier (sign flipped: higher rate is WORSE). Returns -proj (so higher
    = better, aligned with -RA9 target)."""
    wmap = {y: MARCEL_PIT_W[0], y - 1: MARCEL_PIT_W[1], y - 2: MARCEL_PIT_W[2]}
    num = den = 0.0
    for yy in (y - 2, y - 1, y):
        rec = (by_season.get(yy) or {}).get(mid)
        if not rec or rec["cnt"]["tbf"] <= 0:
            continue
        w = wmap[yy]
        num += w * rec["r"]
        den += w * rec["cnt"]["tbf"]
    if den <= 0:
        return None
    lg = pools_runrate[y]
    proj = (num + MARCEL_PIT_REG * lg) / (den + MARCEL_PIT_REG)
    if age_next is not None:
        adj = (29 - age_next) * (0.006 if age_next < 29 else 0.003)
        proj *= (1.0 - adj)          # improvement lowers the run rate
    return -proj


# --------------------------------------------------------------------------- #
# hyperparameter fit (TRAIN only) + dual-convention gate
# --------------------------------------------------------------------------- #
def fit_hinge(score, hinge, tgt):
    """OLS tgt ~ a + b*score + c*hinge -> beta = c/b (score points per year
    over 30). Guard b>0 (score is positively oriented on both sides)."""
    X = np.column_stack([np.ones(len(score)), np.asarray(score), np.asarray(hinge)])
    coef, *_ = np.linalg.lstsq(X, np.asarray(tgt), rcond=None)
    a, b, c = coef.tolist()
    if b <= 0:
        return 0.0, (a, b, c)
    return c / b, (a, b, c)


def dual_gate(primary_name, arms: dict, tgt_raw, mids, pys, oys, seed=SEED):
    """rhos for every arm + iid (v1) and clustered (v2) gap CIs of the primary
    vs every other arm, under both target conventions."""
    tgt_v2 = plh.zscore_within(oys, tgt_raw)
    primary = arms[primary_name]
    baselines = {k: v for k, v in arms.items() if k != primary_name}
    out = {}
    for conv, tgt in (("v1", tgt_raw), ("v2", tgt_v2)):
        rhos = {k: _r4(_spearman(v, tgt)) for k, v in arms.items()}
        if conv == "v1":
            gaps = plh.iid_boot_gaps(primary, baselines, tgt, BOOT, seed)
        else:
            gaps = plh.cluster_boot_gaps(primary, baselines, tgt, mids, pys, BOOT, seed)
        out[conv] = {"rhos": rhos, "gap_ci_primary_minus": gaps}
    out["v2"]["cluster"] = plh.cluster_summary(mids, pys)
    return out


def run_side(side: str, eng: FaEngine) -> dict:
    t0 = time.time()
    seasons = SEASONS_HIT if side == "hit" else SEASONS_PIT
    by_season, pools, runrate = {}, {}, {}
    for y in sorted(set(seasons + [max(seasons) + 1])):
        if side == "hit":
            s, p = load_hit_season(y)
        else:
            s, p = load_pit_season(y)
        if s:
            by_season[y] = s
            pools[y] = p
            if side == "pit":
                tbf = sum(r["cnt"]["tbf"] for r in s.values())
                runs = sum(r["r"] for r in s.values())
                runrate[y] = runs / tbf if tbf else None
        print(f"  {side} {y}: {len(s)} scored")

    # ---- pair construction (X-H2 / X-S2 class), all arms required ---------- #
    pairs = []
    drops = {"partial_outcome": 0, "window": 0, "age_missing": 0, "fa_proj_missing": 0}
    for y in seasons:
        cur, nxt = by_season.get(y), by_season.get(y + 1)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if side == "hit":
                if not b or (a["pa"] or 0) < MIN_PA_Y or (b["pa"] or 0) < MIN_PA_NEXT:
                    continue
                if a["ops"] is None or a["avg"] is None or b["woba_raw"] is None:
                    continue
            else:
                if not b or (a["ip"] or 0) < MIN_IP_Y or (b["ip"] or 0) < MIN_IP_NEXT:
                    continue
                if b["ra9"] is None:
                    continue
            if not plh.season_complete(y + 1):
                drops["partial_outcome"] += 1
                continue
            if side == "hit":
                m3, su, x3 = _hem3(by_season, mid, y)
                if m3 is None or su < TAG_MIN_SEASONS or x3 < TAG_MIN_PA:
                    drops["window"] += 1
                    continue
                tgt = b["woba_raw"]
                one = a["hem_plus_raw"]
            else:
                m3, su, x3 = _sem3(by_season, mid, y)
                if m3 is None or su < TAG_MIN_SEASONS or x3 < TAG_MIN_IP:
                    drops["window"] += 1
                    continue
                tgt = -b["ra9"]
                one = a["sem_plus_raw"]
            age = a.get("age")
            if age is None:
                drops["age_missing"] += 1
                continue
            age_next = age + 1
            pr = eng.proj(side, int(mid), y, age_next)
            if side == "hit":
                fa_val = pr.get("woba_proj") if pr else None
            else:
                fa_val = (-pr["fip_proj"]) if (pr and pr.get("fip_proj") is not None) else None
            if fa_val is None:
                drops["fa_proj_missing"] += 1
                continue
            if side == "hit":
                mv = marcel_woba(by_season, pools, mid, y, age_next)
            else:
                mv = marcel_ra(by_season, runrate, mid, y, age_next)
            if mv is None:
                drops["window"] += 1
                continue
            pooled = {name: (phem_pool_score(by_season, pools, mid, y, w3) if side == "hit"
                             else psem_pool_score(by_season, pools, mid, y, w3))
                      for name, w3 in DECAY_GRID.items()}
            if any(v is None for v in pooled.values()):
                drops["window"] += 1
                continue
            pairs.append({"mid": mid, "y": y, "oy": y + 1, "tgt": tgt,
                          "one": one, "three": m3, "marcel": mv, "fa": fa_val,
                          "hinge": max(0.0, age_next - 30.0), "pooled": pooled})
    n = len(pairs)
    train = [p for p in pairs if p["y"] <= TRAIN_MAX_PRED_YEAR]
    gate = [p for p in pairs if p["y"] > TRAIN_MAX_PRED_YEAR]
    print(f"  {side}: pairs={n} train={len(train)} gate={len(gate)} drops={drops}")

    # ---- hyperparameter fit on TRAIN only ---------------------------------- #
    fit_report = {}
    best = None
    for name in DECAY_GRID:
        sc = [p["pooled"][name] for p in train]
        hg = [p["hinge"] for p in train]
        tg = [p["tgt"] for p in train]
        beta, coef = fit_hinge(sc, hg, tg)
        adj = [s + beta * h for s, h in zip(sc, hg)]
        rho_adj = _spearman(adj, tg)
        rho_noage = _spearman(sc, tg)
        fit_report[name] = {"beta_hinge": round(beta, 4),
                            "ols_coef_a_b_c": [round(x, 6) for x in coef],
                            "train_rho_age_adj": _r4(rho_adj),
                            "train_rho_no_age": _r4(rho_noage)}
        if best is None or (rho_adj or -9) > best[1]:
            best = (name, rho_adj, beta)
    decay_star, train_rho_star, beta_star = best
    frozen = {"decay": decay_star, "weights": DECAY_GRID[decay_star],
              "beta_hinge": round(beta_star, 4), "hinge": "max(0, age_{y+1} - 30)",
              "train_pred_years": f"<= {TRAIN_MAX_PRED_YEAR}",
              "train_n": len(train), "train_rho": _r4(train_rho_star),
              "grid_report": fit_report}
    print(f"  {side} frozen: decay={decay_star} beta={beta_star:.4f} "
          f"train_rho={train_rho_star:.4f}")

    # ---- gate --------------------------------------------------------------- #
    def _arms(subset):
        cand = [p["pooled"][decay_star] + beta_star * p["hinge"] for p in subset]
        return {
            "incumbent_1yr": [p["one"] for p in subset],
            "incumbent_3yr_flat": [p["three"] for p in subset],
            "marcel_textbook": [p["marcel"] for p in subset],
            "fa_projection": [p["fa"] for p in subset],
            "phem_marcel_lite": cand,
        }
    arms_g = _arms(gate)
    tgt_g = [p["tgt"] for p in gate]
    mids_g = [p["mid"] for p in gate]
    pys_g = [p["y"] for p in gate]
    oys_g = [p["oy"] for p in gate]

    rhos_v1 = {k: _spearman(v, tgt_g) for k, v in arms_g.items()}
    incumbents = ("incumbent_1yr", "incumbent_3yr_flat")
    candidates = ("marcel_textbook", "fa_projection", "phem_marcel_lite")
    best_inc = max(incumbents, key=lambda k: rhos_v1[k] if rhos_v1[k] is not None else -9)
    winner = max(candidates, key=lambda k: rhos_v1[k] if rhos_v1[k] is not None else -9)
    res = dual_gate(winner, arms_g, tgt_g, mids_g, pys_g, oys_g)
    gap_v1 = res["v1"]["gap_ci_primary_minus"].get(best_inc)
    gap_v2 = res["v2"]["gap_ci_primary_minus"].get(best_inc)
    pass_v1 = bool(gap_v1 and gap_v1["lo95"] >= 0)
    pass_v2 = bool(gap_v2 and gap_v2["lo95"] >= 0)

    # candidate-vs-best-incumbent CIs for the registered candidate too (if it
    # is not the winner, its own gap is diagnostic, not the gate)
    diag = None
    if winner != "phem_marcel_lite":
        diag = dual_gate("phem_marcel_lite", arms_g, tgt_g, mids_g, pys_g, oys_g)

    # context: full-set rhos + X-H2 parity anchors
    arms_all = _arms(pairs)
    tgt_all = [p["tgt"] for p in pairs]
    rhos_all = {k: _r4(_spearman(v, tgt_all)) for k, v in arms_all.items()}

    out = {
        "side": side, "n_pairs_total": n, "n_train": len(train), "n_gate": len(gate),
        "drops": drops, "seasons": seasons,
        "gate_pred_years": sorted({p["y"] for p in gate}),
        "gate_outcome_years": sorted({p["oy"] for p in gate}),
        "frozen_hyperparams": frozen,
        "gate_rhos_v1": {k: _r4(v) for k, v in rhos_v1.items()},
        "best_incumbent": best_inc, "winner_candidate": winner,
        "results": res,
        "gate": {
            "bar": ("winner candidate paired-bootstrap lo95(winner - best incumbent) >= 0; "
                    "v1 convention (raw Y+1 target, iid bootstrap), seed 20260715, 2000 reps"),
            "convention": "v1",
            "gap_ci_winner_minus_best_incumbent_v1": gap_v1,
            "gap_ci_winner_minus_best_incumbent_v2": gap_v2,
            "pass": pass_v1, "pass_under_v2": pass_v2,
        },
        "registered_candidate_diagnostic": diag,
        "full_set_rhos_v1": rhos_all,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    return out


def main():
    t0 = time.time()
    eng = FaEngine()
    print(f"fa corpus loaded: hit={len(eng.hist_hit)} pit={len(eng.hist_pit)} players")
    hit = run_side("hit", eng)
    pit = run_side("pit", eng)
    pit["note"] = ("pre-declared SECONDARY; provisional regardless of pass when "
                   "n_gate < 700 (thin starter 3yr-window sample)")
    pit["provisional"] = pit["n_gate"] < 700
    payload = {
        "experiment": "T1-10 pHEM+ Marcel-lite (wave 3)",
        "generated_at": date.today().isoformat(), "seed": SEED, "boot": BOOT,
        "harness": plh.convention_meta(
            "wOBA(Y+1) raw pooled (hit) / -RA9(Y+1) raw pooled (pit)",
            "wOBA(Y+1) (hit) / -RA9(Y+1) (pit)"),
        "protocol": {
            "candidate": ("pHEM+ Marcel-lite: decayed pooled wOBA-component counts "
                          "(y-2..y), ONE EB shrink (hem_plus constants) vs the year-y "
                          "pool, re-indexed vs the year-y pool anchor, + age hinge at 30"),
            "hyperparams_fit": f"predictor years <= {TRAIN_MAX_PRED_YEAR} ONLY, frozen",
            "gate_set": "predictor years >= 2019 (outcome seasons 2020, 2022-2025; complete only)",
            "gate_rule": ("winner candidate (best gate rho among marcel_textbook / "
                          "fa_projection / phem_marcel_lite) vs BEST incumbent "
                          "(1yr HEM+ or flat-3yr HEM+): iid paired bootstrap lo95 >= 0 (v1)"),
            "decay_grid": {k: list(v) for k, v in DECAY_GRID.items()},
        },
        "hitters": hit, "pitchers": pit,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    out = WORKSPACE / "results.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote {out} in {payload['runtime_seconds']}s")
    print(json.dumps({
        "hit": {"n_gate": hit["n_gate"], "rhos": hit["gate_rhos_v1"],
                "winner": hit["winner_candidate"], "best_inc": hit["best_incumbent"],
                "gap_v1": hit["gate"]["gap_ci_winner_minus_best_incumbent_v1"],
                "pass": hit["gate"]["pass"], "pass_v2": hit["gate"]["pass_under_v2"]},
        "pit": {"n_gate": pit["n_gate"], "rhos": pit["gate_rhos_v1"],
                "winner": pit["winner_candidate"], "best_inc": pit["best_incumbent"],
                "gap_v1": pit["gate"]["gap_ci_winner_minus_best_incumbent_v1"],
                "pass": pit["gate"]["pass"], "pass_v2": pit["gate"]["pass_under_v2"]},
    }, indent=1))


if __name__ == "__main__":
    main()

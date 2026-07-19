# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Wave-3 lane labs: X-R5 (REM+ FB-conditioned HR prior, the named xFIP-lite
deferral, T1-9) + X-S5 (SEM+ analog, pre-declared long-shot secondary) + X-R1b
(multi-year CSW%-implied xK shrink TARGET, the SwStr loss-ledger's sanctioned
retry, T1-11).

Feeds on tools/win_prob_walker.py's per-pitcher-season table (CSW / trajectory
fly-ball counts from the cached winProbability playEvents). Pair construction
mirrors tools/rem_plus_lab.py X-R1 (true relievers ex-openers, TBF>=100 pred /
TBF>=60 outcome, complete outcome seasons only) and tools/sem_plus_lab.py X-S1
(IP>=50 / IP>=40) so the gates run on the same sets those labs report.

PRE-REGISTERED GATES (convention v1: raw -RA9(Y+1) target, iid pair bootstrap,
complete-outcome pairs; 2000 reps, seed 20260715; pass_under_v2 reported
alongside per the harness-v2 transition rule):

  X-R5  candidate HR shrink target = lgHR/FB(Y) * FB_rate_shrunk(pitcher,Y)
        [FB per TBF, fly_ball only; popup arm = fly+popup as sensitivity;
        lgHR/FB from year Y only; EB shrink K_FB=80 batted balls; arms with
        <20 known-trajectory batted balls (or no walker row) fall back to the
        incumbent pool-mean target]. K_HOMERUN=400 and all other components
        unchanged. SHIP iff gap lo95 >= 0 AND mean > 0 vs the incumbent on the
        identical pair set; PROVISIONAL iff mean > 0 with lo95 in (-0.005, 0).

  X-S5  same candidate HR target on the SEM+ starter core. Pre-declared
        LONG-SHOT SECONDARY (starter batted-ball samples are big enough that
        observed HR rate is already strong): same bar shape, but a pass only
        flags to the owner, never auto-ships.

  X-R1b candidate K shrink TARGET = multi-year CSW%-implied xK: csw_multi(Y) =
        pitch-count-weighted blend of CSW(Y) and 0.6-weighted CSW(Y-1); xK from
        a contemporaneous TBF-weighted OLS of K% on csw_multi over year-Y pool
        arms (>=30 arms else flat pool-mean fallback; xK clamped [0.10,0.45]);
        K_STRIKEOUT=70 unchanged; everything else unchanged; arms without CSW
        coverage keep the incumbent pool-mean target. KNOWN DILUTION: no
        2017/2020 cache -> 2018/2021 predictors are single-year CSW. GATE:
        incumbent re-baselined in the SAME run, gap lo95 >= 0. SECONDARY:
        rho(xk_multi, K% Y+1) vs rho(K% Y, K% Y+1) + the TBF 100-150 band.
        A FAIL CLOSES THE K-PRIOR LANE PERMANENTLY.

Repo READ-ONLY: writes artifacts to the OUT_DIR passed on the command line.
Run: python w3_fbhr_csw_labs.py OUT_DIR WALKER_TABLE

W3B RERUN NOTES (2026-07-15, lane w3b-fbhr-csw):
- The first attempt stalled in mlb_leverage.fetch_season_leverage (live
  schedule walk + thousands of per-game winProbability fetches with 404 noise).
  Leverage is NOT part of any gate here; the ONLY load-bearing leverage field
  is entry_inning (rem_plus._is_opener needs it to drop openers from the
  true-reliever pool). This rerun reads per-season leverage dicts prebuilt
  OFFLINE from the same .cache/win_prob payloads by offline_leverage.py
  (identical pure fold: mlb_leverage._fold_game/_finalize), so the pool
  composition - including the opener drop - matches the network path exactly
  for every cached game, with ZERO live fetches. Missing artifact = hard error
  (never a silent empty dict, never a fetch).
- Per-season loads checkpoint to OUT_DIR/season_ckpt/*.pkl so the run can be
  resumed across synchronous foreground calls.
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("EEPHUS_ROOT")
            or r"C:/Users/noah/baseball-projects/BaseballR/prospect-tracker")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE))

import rem_plus  # noqa: E402
import sem_plus  # noqa: E402
import bullpen_export as be  # noqa: E402
import starter_export as se  # noqa: E402
import plus_lab_harness as plh  # noqa: E402
import win_prob_walker as wpw  # noqa: E402
from rem_plus_backtest import _spearman, SEASONS as BT_SEASONS  # noqa: E402

# NOTE: mlb_leverage is deliberately NOT imported - the only leverage consumer
# here is the offline artifact below (see W3B RERUN NOTES in the docstring).
LEV_DIR = Path(os.environ.get("W3B_LEV_DIR")
               or Path(__file__).resolve().parent.parent.parent / "lev")


def _offline_leverage(y: int) -> dict:
    """Per-season leverage prebuilt by offline_leverage.py (same fold as
    mlb_leverage, zero network). Hard error if absent - a silent empty dict
    would drop the opener filter and quietly change the pool."""
    p = LEV_DIR / f"leverage_{y}.json"
    if not p.exists():
        raise FileNotFoundError(
            f"offline leverage artifact missing: {p} - run offline_leverage.py first")
    return {int(k): v
            for k, v in json.loads(p.read_text(encoding="utf-8")).items()}

SEASONS = list(BT_SEASONS)          # 2018,2019,2021..2025 (ex-2020)
MIN_TBF_Y, MIN_TBF_NEXT = 100, 60   # reliever pair bars (rem_plus_lab)
MIN_IP_Y, MIN_IP_NEXT = 50.0, 40.0  # starter pair bars (sem_plus_lab)
BOOT = 2000
SEED = 20260715

K_FB = 80.0            # EB shrink constant for the FB rate (batted balls)
MIN_BB_COVER = 20      # below this many known-trajectory batted balls -> fallback
CSW_CARRY = 0.6        # Y-1 carry-in weight (pitch-count-weighted blend)
XK_CLAMP = (0.10, 0.45)
TBF_BAND = (100, 150)  # the pre-registered small-sample band for X-R1b

TARGET_V1 = "-RA9 in year Y+1 (raw, pooled across seasons)"
TARGET_V2 = "-RA9 in year Y+1"


def _r4(v):
    return None if v is None else round(v, 4)


# --------------------------------------------------------------------------- #
# candidate cores
# --------------------------------------------------------------------------- #
def _fb_pool_stats(pool, wtab, season, *, popup=False) -> dict | None:
    """Year-Y pool FB constants over covered arms: lg_fb_rate (FB per statline
    TBF) + lg_hr_per_fb (statline HR per walker FB)."""
    fb_key = "fly_balls"
    fb_sum = hr_sum = tbf_sum = 0.0
    n = 0
    for r in pool:
        w = wtab.get((season, r.mlbam))
        if not w or (w["batted_balls"] or 0) < MIN_BB_COVER or r.tbf <= 0:
            continue
        fb = w[fb_key] + (w["popups"] if popup else 0)
        fb_sum += fb
        hr_sum += r.hr
        tbf_sum += r.tbf
        n += 1
    if n < 30 or fb_sum <= 0 or tbf_sum <= 0:
        return None
    return {"lg_fb_rate": fb_sum / tbf_sum, "lg_hr_per_fb": hr_sum / fb_sum,
            "n_covered": n}


def _fbhr_target(r, w, fbst, pool_mean_hr, *, popup=False) -> tuple[float, bool]:
    """(hr shrink target, used_candidate_flag) for one arm."""
    if fbst is None or not w or (w["batted_balls"] or 0) < MIN_BB_COVER or r.tbf <= 0:
        return pool_mean_hr, False
    fb = w["fly_balls"] + (w["popups"] if popup else 0)
    n_bb = float(w["batted_balls"])
    fb_rate = fb / r.tbf
    fb_shrunk = (n_bb * fb_rate + K_FB * fbst["lg_fb_rate"]) / (n_bb + K_FB)
    return fbst["lg_hr_per_fb"] * fb_shrunk, True


def _rel_fip(r, p, *, hr_target=None, xk=None) -> float | None:
    """rem_plus.fip_skill with an optionally swapped HR shrink target and/or K
    shrink target. hr_target/xk None -> incumbent pool-mean behavior."""
    if r.ip <= 0 or r.tbf <= 0:
        return None
    if not r.rates:
        rem_plus.derive_rates(r)
    k = rem_plus._shrink(r.rates["k_pct"], r.tbf, rem_plus.K_STRIKEOUT,
                         p.mean_k_pct if xk is None else xk)
    bb = rem_plus._shrink(r.rates["bb_pct"], r.tbf, rem_plus.K_WALK, p.mean_bb_pct)
    hbp = rem_plus._shrink(r.rates["hbp_pct"], r.tbf, rem_plus.K_HBP, p.mean_hbp_pct)
    hr = rem_plus._shrink(r.rates["hr_rate"], r.tbf, rem_plus.K_HOMERUN,
                          p.mean_hr_rate if hr_target is None else hr_target)
    k_c, bb_c, hbp_c, hr_c = k * r.tbf, bb * r.tbf, hbp * r.tbf, hr * r.tbf
    fip = (rem_plus.FIP_HR * hr_c + rem_plus.FIP_BBHBP * (bb_c + hbp_c)
           - rem_plus.FIP_K * k_c) / r.ip + p.cfip
    return max(fip, 1.0)


def _starter_fip(s, p, *, hr_target=None) -> float | None:
    """sem_plus.fip_skill (plain core) with an optionally swapped HR target."""
    if s.ip <= 0 or s.tbf <= 0:
        return None
    if not s.rates:
        sem_plus.derive_rates(s)
    k = rem_plus._shrink(s.rates["k_pct"], s.tbf, rem_plus.K_STRIKEOUT, p.mean_k_pct)
    bb = rem_plus._shrink(s.rates["bb_pct"], s.tbf, rem_plus.K_WALK, p.mean_bb_pct)
    hbp = rem_plus._shrink(s.rates["hbp_pct"], s.tbf, rem_plus.K_HBP, p.mean_hbp_pct)
    hr = rem_plus._shrink(s.rates["hr_rate"], s.tbf, rem_plus.K_HOMERUN,
                          p.mean_hr_rate if hr_target is None else hr_target)
    k_c, bb_c, hbp_c, hr_c = k * s.tbf, bb * s.tbf, hbp * s.tbf, hr * s.tbf
    fip = (rem_plus.FIP_HR * hr_c + rem_plus.FIP_BBHBP * (bb_c + hbp_c)
           - rem_plus.FIP_K * k_c) / s.ip + p.cfip
    return max(fip, 1.0)


def _csw_multi(wtab, season, mlbam) -> tuple[float | None, int]:
    """Pitch-count-weighted CSW blend of year Y and 0.6*carry Y-1.
    Returns (csw_multi, n_years_used)."""
    cur = wtab.get((season, mlbam))
    prev = wtab.get((season - 1, mlbam))
    num = den = 0.0
    used = 0
    if cur and (cur["pitches"] or 0) > 0:
        num += cur["pitches"] * (cur["csw"] / cur["pitches"])
        den += cur["pitches"]
        used += 1
    if prev and (prev["pitches"] or 0) > 0:
        w = CSW_CARRY * prev["pitches"]
        num += w * (prev["csw"] / prev["pitches"])
        den += w
        used += 1
    if not den:
        return None, 0
    return num / den, used


def _fit_xk_csw(pool, csw_of) -> tuple[float, float]:
    """TBF-weighted OLS of K% on csw_multi over year-Y pool arms (mirrors
    rem_plus_lab._fit_xk; contemporaneous, no future leakage)."""
    xs, ys, ws = [], [], []
    for r in pool:
        c = csw_of.get(r.mlbam)
        k = r.rates.get("k_pct")
        if c is None or k is None or r.tbf <= 0:
            continue
        xs.append(c); ys.append(k); ws.append(r.tbf)
    if len(xs) < 30:
        km = [r.rates.get("k_pct") for r in pool if r.rates.get("k_pct") is not None]
        return ((sum(km) / len(km)) if km else 0.22, 0.0)
    xb = sum(w * x for w, x in zip(ws, xs)) / sum(ws)
    yb = sum(w * y for w, y in zip(ws, ys)) / sum(ws)
    cov = sum(w * (x - xb) * (y - yb) for w, x, y in zip(ws, xs, ys))
    var = sum(w * (x - xb) ** 2 for w, x in zip(ws, xs))
    slope = cov / var if var else 0.0
    return (yb - slope * xb, slope)


# --------------------------------------------------------------------------- #
# per-season loads
# --------------------------------------------------------------------------- #
def load_reliever_season(y: int, wtab: dict) -> tuple[dict, dict]:
    """MLBAM -> record for season Y's true-reliever pool (ex-openers), carrying
    incumbent REM+ raw, the three candidate scores, and outcome RA9."""
    rows = be.load_season_pitching(y)
    if not rows:
        return {}, {}
    leverage = _offline_leverage(y)  # w3b: offline artifact, never a live walk
    rels = be.build_relievers(rows, leverage, {})
    true_rels = [r for r in rels if rem_plus.is_true_reliever(r)]
    pool = [r for r in true_rels if not rem_plus._is_opener(r)]
    n_openers = len(true_rels) - len(pool)
    n_entry = sum(1 for r in true_rels if r.entry_inning is not None)
    for r in pool:
        rem_plus.derive_rates(r)
    p = rem_plus.build_pool(pool)

    fbst = _fb_pool_stats(pool, wtab, y, popup=False)
    fbst_pu = _fb_pool_stats(pool, wtab, y, popup=True)
    csw_of = {}
    for r in pool:
        c, _u = _csw_multi(wtab, y, r.mlbam)
        if c is not None:
            csw_of[r.mlbam] = c
    xk_fit = _fit_xk_csw(pool, csw_of)

    def _anchor(fips):
        num = den = 0.0
        for r, f in fips:
            if f is not None:
                num += f * r.ip; den += r.ip
        return (num / den) if den else p.pool_era

    cand_fips = {}
    for r in pool:
        w = wtab.get((y, r.mlbam))
        t_fb, cov_fb = _fbhr_target(r, w, fbst, p.mean_hr_rate, popup=False)
        t_pu, _ = _fbhr_target(r, w, fbst_pu, p.mean_hr_rate, popup=True)
        c = csw_of.get(r.mlbam)
        xk = None
        if c is not None and xk_fit[1]:
            xk = max(XK_CLAMP[0], min(XK_CLAMP[1], xk_fit[0] + xk_fit[1] * c))
        cand_fips[r.mlbam] = {
            "fb": _rel_fip(r, p, hr_target=t_fb),
            "pu": _rel_fip(r, p, hr_target=t_pu),
            "csw": _rel_fip(r, p, xk=xk),
            "fb_covered": cov_fb, "csw_covered": c is not None, "xk": xk,
        }
    anch = {k: _anchor([(r, cand_fips[r.mlbam][k]) for r in pool])
            for k in ("fb", "pu", "csw")}

    out = {}
    for r in pool:
        rem_plus.rem_plus(r, p)
        if r.rem_plus is None:
            continue
        cf = cand_fips[r.mlbam]
        out[r.mlbam] = {
            "name": r.name,
            "rem_plus_raw": r.rem_plus_raw,
            "cand_fb": (100.0 * anch["fb"] / cf["fb"]) if cf["fb"] else None,
            "cand_pu": (100.0 * anch["pu"] / cf["pu"]) if cf["pu"] else None,
            "cand_csw": (100.0 * anch["csw"] / cf["csw"]) if cf["csw"] else None,
            "fb_covered": cf["fb_covered"], "csw_covered": cf["csw_covered"],
            "xk_multi": cf["xk"], "k_pct": r.rates.get("k_pct"),
            "raw_fip": ((rem_plus.FIP_HR * r.hr + rem_plus.FIP_BBHBP * (r.bb + r.hbp)
                         - rem_plus.FIP_K * r.so) / r.ip) if r.ip > 0 else None,
            "era": r.rates.get("era"), "ra9": r.rates.get("ra9"),
            "tbf": r.tbf, "ip": r.ip,
        }
    meta = {"n_scored": len(out), "fb_pool": fbst, "fb_pool_popup": fbst_pu,
            "xk_fit": {"intercept": _r4(xk_fit[0]), "slope": _r4(xk_fit[1])},
            "n_csw_covered": len(csw_of),
            "pool_mean_hr_rate": _r4(p.mean_hr_rate),
            "n_true_relievers": len(true_rels), "n_openers_dropped": n_openers,
            "n_entry_inning_covered": n_entry}
    print(f"  REL {y}: {len(out)} scored | openers dropped {n_openers} "
          f"(entry-inning cover {n_entry}/{len(true_rels)}) "
          f"| fb_pool={None if not fbst else _r4(fbst['lg_hr_per_fb'])} "
          f"| xk slope={_r4(xk_fit[1])} | csw cov {len(csw_of)}")
    return out, meta


def load_starter_season(y: int, wtab: dict) -> tuple[dict, dict]:
    rows = be.load_season_pitching(y)
    if not rows:
        return {}, {}
    starters = se.build_starters(rows, {})
    pool = [s for s in starters if sem_plus.is_true_starter(s)]
    for s in pool:
        sem_plus.derive_rates(s)
    p = sem_plus.build_pool(pool, gb_adjust=False)
    fbst = _fb_pool_stats(pool, wtab, y, popup=False)
    fbst_pu = _fb_pool_stats(pool, wtab, y, popup=True)

    cand_fips = {}
    for s in pool:
        w = wtab.get((y, s.mlbam))
        t_fb, cov = _fbhr_target(s, w, fbst, p.mean_hr_rate, popup=False)
        t_pu, _ = _fbhr_target(s, w, fbst_pu, p.mean_hr_rate, popup=True)
        cand_fips[s.mlbam] = {"fb": _starter_fip(s, p, hr_target=t_fb),
                              "pu": _starter_fip(s, p, hr_target=t_pu),
                              "fb_covered": cov}

    def _anchor(key):
        num = den = 0.0
        for s in pool:
            f = cand_fips[s.mlbam][key]
            if f is not None:
                num += f * s.ip; den += s.ip
        return (num / den) if den else p.pool_era

    anch = {k: _anchor(k) for k in ("fb", "pu")}
    out = {}
    for s in pool:
        plain = sem_plus.sem_plus(s, p, gb_adjust=False)
        if plain is None:
            continue
        cf = cand_fips[s.mlbam]
        out[s.mlbam] = {
            "name": s.name, "sem_plus_raw": s.sem_plus_raw,
            "cand_fb": (100.0 * anch["fb"] / cf["fb"]) if cf["fb"] else None,
            "cand_pu": (100.0 * anch["pu"] / cf["pu"]) if cf["pu"] else None,
            "fb_covered": cf["fb_covered"],
            "raw_fip": ((sem_plus.FIP_HR * s.hr + sem_plus.FIP_BBHBP * (s.bb + s.hbp)
                         - sem_plus.FIP_K * s.so) / s.ip) if s.ip > 0 else None,
            "era": s.rates.get("era"), "ra9": s.rates.get("ra9"),
            "ip": s.ip, "tbf": s.tbf,
        }
    meta = {"n_scored": len(out), "fb_pool": fbst, "fb_pool_popup": fbst_pu,
            "pool_mean_hr_rate": _r4(p.mean_hr_rate)}
    print(f"  STR {y}: {len(out)} scored")
    return out, meta


# --------------------------------------------------------------------------- #
# dual-convention comparison (identical shape to rem_plus_lab._dual)
# --------------------------------------------------------------------------- #
def dual(primary, baselines: dict, tgt_raw, players, pred_seasons, out_seasons,
         seed=SEED):
    tgt_v2 = plh.zscore_within(out_seasons, tgt_raw)
    rp1 = _spearman(primary, tgt_raw)
    rb1 = {k: _spearman(s, tgt_raw) for k, s in baselines.items()}
    rp2 = _spearman(primary, tgt_v2)
    rb2 = {k: _spearman(s, tgt_v2) for k, s in baselines.items()}
    return {
        "v1": {"rho_primary": _r4(rp1),
               "rho_baselines": {k: _r4(v) for k, v in rb1.items()},
               "gap_ci": plh.iid_boot_gaps(primary, baselines, tgt_raw, BOOT, seed)},
        "v2": {"rho_primary": _r4(rp2),
               "rho_baselines": {k: _r4(v) for k, v in rb2.items()},
               "gap_ci": plh.cluster_boot_gaps(primary, baselines, tgt_v2, players,
                                               pred_seasons, BOOT, seed),
               "cluster": plh.cluster_summary(players, pred_seasons)},
    }


def _gate_fbhr(res) -> tuple[str, bool]:
    """X-R5 bar: SHIP iff lo95>=0 AND mean>0; PROVISIONAL iff mean>0 and
    lo95 in (-0.005, 0); else FAIL. On convention v1."""
    ci = res["v1"]["gap_ci"]["vs_incumbent"]
    if not ci:
        return "FAIL", False
    if ci["lo95"] >= 0 and ci["mean"] > 0:
        return "SHIP", True
    if ci["mean"] > 0 and -0.005 < ci["lo95"] < 0:
        return "PROVISIONAL", False
    return "FAIL", False


def _pass_v2(res, key="vs_incumbent") -> bool:
    ci = res["v2"]["gap_ci"].get(key)
    return bool(ci and ci["lo95"] >= 0 and ci["mean"] > 0)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def run(out_dir: Path, walker_table: Path) -> dict:
    t0 = time.time()
    wtab = wpw.load_table(walker_table)
    print(f"walker table: {len(wtab)} pitcher-seasons")

    ck = out_dir / "season_ckpt"
    ck.mkdir(parents=True, exist_ok=True)
    rel, rel_meta, st, st_meta = {}, {}, {}, {}
    for y in SEASONS:
        f = ck / f"s{y}.pkl"
        if f.exists():
            with open(f, "rb") as fh:
                rel[y], rel_meta[y], st[y], st_meta[y] = pickle.load(fh)
            print(f"  {y}: from checkpoint ({len(rel[y])} rel / {len(st[y])} st)")
        else:
            rel[y], rel_meta[y] = load_reliever_season(y, wtab)
            st[y], st_meta[y] = load_starter_season(y, wtab)
            with open(f, "wb") as fh:
                pickle.dump((rel[y], rel_meta[y], st[y], st_meta[y]), fh)
    print(f"loaded {len(rel)} seasons in {round(time.time() - t0, 1)}s")

    # ---- reliever forward pairs (X-R5 + X-R1b share this set) ---- #
    P = {k: [] for k in ("inc", "fb", "pu", "csw", "tgt", "mid", "py", "oy",
                         "tbf", "k_y", "k_next", "xk", "csw_cov", "fb_cov")}
    for y in SEASONS:
        ny = y + 1
        cur, nxt = rel.get(y), rel.get(ny)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["tbf"] or 0) < MIN_TBF_Y or (b["tbf"] or 0) < MIN_TBF_NEXT:
                continue
            if a["cand_fb"] is None or a["cand_pu"] is None or a["cand_csw"] is None \
                    or a["raw_fip"] is None or a["era"] is None or b["ra9"] is None:
                continue
            if not plh.season_complete(ny):
                continue
            P["inc"].append(a["rem_plus_raw"]); P["fb"].append(a["cand_fb"])
            P["pu"].append(a["cand_pu"]); P["csw"].append(a["cand_csw"])
            P["tgt"].append(-b["ra9"])
            P["mid"].append(mid); P["py"].append(y); P["oy"].append(ny)
            P["tbf"].append(a["tbf"])
            P["k_y"].append(a["k_pct"]); P["k_next"].append(b["k_pct"])
            P["xk"].append(a["xk_multi"])
            P["csw_cov"].append(a["csw_covered"]); P["fb_cov"].append(a["fb_covered"])
    n = len(P["inc"])
    print(f"reliever pairs: {n} (fb covered {sum(P['fb_cov'])}, csw covered {sum(P['csw_cov'])})")

    # ---- X-R5 gate ---- #
    xr5 = dual(P["fb"], {"vs_incumbent": P["inc"]}, P["tgt"], P["mid"], P["py"], P["oy"])
    xr5_pu = dual(P["pu"], {"vs_incumbent": P["inc"]}, P["tgt"], P["mid"], P["py"], P["oy"])
    xr5_verdict, xr5_ship = _gate_fbhr(xr5)
    xr5_pu_verdict, _ = _gate_fbhr(xr5_pu)

    # ---- X-R1b gate ---- #
    xr1b = dual(P["csw"], {"vs_incumbent": P["inc"]}, P["tgt"], P["mid"], P["py"], P["oy"])
    ci1b = xr1b["v1"]["gap_ci"]["vs_incumbent"]
    xr1b_pass = bool(ci1b and ci1b["lo95"] >= 0)
    # secondary A: does the multi-year CSW xK predict next-year K% better than K% itself?
    idx = [i for i in range(n) if P["xk"][i] is not None and P["k_y"][i] is not None
           and P["k_next"][i] is not None]
    rho_xk_knext = _spearman([P["xk"][i] for i in idx], [P["k_next"][i] for i in idx])
    rho_k_knext = _spearman([P["k_y"][i] for i in idx], [P["k_next"][i] for i in idx])
    # secondary B: the TBF 100-150 band (where a faster-stabilizing prior should help most)
    band = [i for i in range(n) if TBF_BAND[0] <= P["tbf"][i] <= TBF_BAND[1]]
    xr1b_band = None
    if len(band) >= 30:
        xr1b_band = dual([P["csw"][i] for i in band],
                         {"vs_incumbent": [P["inc"][i] for i in band]},
                         [P["tgt"][i] for i in band], [P["mid"][i] for i in band],
                         [P["py"][i] for i in band], [P["oy"][i] for i in band])

    # ---- X-S5 starter pairs (long-shot secondary) ---- #
    S = {k: [] for k in ("inc", "fb", "pu", "tgt", "mid", "py", "oy", "fb_cov")}
    for y in SEASONS:
        ny = y + 1
        cur, nxt = st.get(y), st.get(ny)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["ip"] or 0) < MIN_IP_Y or (b["ip"] or 0) < MIN_IP_NEXT:
                continue
            if a["cand_fb"] is None or a["cand_pu"] is None or a["raw_fip"] is None \
                    or a["era"] is None or b["ra9"] is None:
                continue
            if not plh.season_complete(ny):
                continue
            S["inc"].append(a["sem_plus_raw"]); S["fb"].append(a["cand_fb"])
            S["pu"].append(a["cand_pu"]); S["tgt"].append(-b["ra9"])
            S["mid"].append(mid); S["py"].append(y); S["oy"].append(ny)
            S["fb_cov"].append(a["fb_covered"])
    ns = len(S["inc"])
    print(f"starter pairs: {ns} (fb covered {sum(S['fb_cov'])})")
    xs5 = dual(S["fb"], {"vs_incumbent": S["inc"]}, S["tgt"], S["mid"], S["py"], S["oy"])
    xs5_pu = dual(S["pu"], {"vs_incumbent": S["inc"]}, S["tgt"], S["mid"], S["py"], S["oy"])
    xs5_verdict, _ = _gate_fbhr(xs5)
    xs5_pu_verdict, _ = _gate_fbhr(xs5_pu)

    dur = round(time.time() - t0, 1)
    common = {"generated_at": date.today().isoformat(), "seasons": SEASONS,
              "seed": SEED, "boot": BOOT, "runtime_seconds": dur,
              "walker_table": str(walker_table),
              "leverage_source": ("offline per-season rebuild from .cache/win_prob "
                                  "(offline_leverage.py; same _fold_game/_finalize "
                                  "as mlb_leverage; zero live fetches). Only "
                                  "entry_inning is load-bearing (opener drop)."),
              "reliever_pool_composition": {
                  str(y): {k: rel_meta[y].get(k) for k in
                           ("n_scored", "n_true_relievers", "n_openers_dropped",
                            "n_entry_inning_covered")}
                  for y in SEASONS},
              "harness": plh.convention_meta(TARGET_V1, TARGET_V2),
              "gate_convention": ("v1 (raw -RA9(Y+1) target, iid pair bootstrap, "
                                  "complete-outcome pairs) as pre-registered; "
                                  "pass_under_v2 reported alongside")}

    payload = {
        **common,
        "X-R5": {
            "experiment": "T1-9 X-R5: REM+ FB-conditioned HR prior (xFIP-lite)",
            "candidate": ("HR shrink target = lgHR/FB(Y) * EB-shrunk FB-per-TBF "
                          f"(fly_ball only; K_FB={int(K_FB)} batted balls; "
                          f"<{MIN_BB_COVER} batted balls -> incumbent pool-mean target); "
                          "K_HOMERUN=400 and all other components unchanged"),
            "n_pairs": n, "n_fb_covered": sum(P["fb_cov"]),
            "per_season_pool": {str(y): {"fb_pool": rel_meta[y].get("fb_pool"),
                                         "pool_mean_hr_rate": rel_meta[y].get("pool_mean_hr_rate")}
                                for y in SEASONS},
            "results_by_convention": xr5,
            "gate": {"bar": "ship iff gap lo95 >= 0 AND mean > 0; provisional iff "
                            "mean > 0 with lo95 in (-0.005, 0)",
                     "verdict": xr5_verdict, "pass": xr5_ship,
                     "pass_under_v2": _pass_v2(xr5)},
            "popup_sensitivity_arm": {
                "candidate": "FB = fly_ball + popup (same shrink, same constants)",
                "results_by_convention": xr5_pu, "verdict_same_bar": xr5_pu_verdict},
        },
        "X-S5": {
            "experiment": "X-S5: SEM+ FB-conditioned HR prior (pre-declared long-shot secondary)",
            "n_pairs": ns, "n_fb_covered": sum(S["fb_cov"]),
            "results_by_convention": xs5,
            "gate": {"bar": "same bar shape as X-R5 but SECONDARY: a pass flags to "
                            "the owner, never auto-ships",
                     "verdict": xs5_verdict, "pass_under_v2": _pass_v2(xs5)},
            "popup_sensitivity_arm": {"results_by_convention": xs5_pu,
                                      "verdict_same_bar": xs5_pu_verdict},
        },
        "X-R1b": {
            "experiment": ("T1-11 X-R1b: multi-year CSW%-implied xK shrink target "
                           "(the SwStr loss-ledger's sanctioned retry)"),
            "candidate": (f"csw_multi(Y) = pitch-weighted CSW(Y) + {CSW_CARRY}*pitch-"
                          "weighted CSW(Y-1); xK = year-Y TBF-weighted OLS(K% ~ "
                          f"csw_multi), clamp {XK_CLAMP}; K_STRIKEOUT=70 unchanged; "
                          "no-coverage arms keep the incumbent pool-mean target"),
            "known_dilution": ("no 2017/2020 winProbability cache -> 2018 and 2021 "
                               "predictors are single-year CSW (no carry-in)"),
            "n_pairs": n, "n_csw_covered": sum(P["csw_cov"]),
            "per_season_fit": {str(y): {"xk_fit": rel_meta[y].get("xk_fit"),
                                        "n_csw_covered": rel_meta[y].get("n_csw_covered")}
                               for y in SEASONS},
            "results_by_convention": xr1b,
            "gate": {"bar": "incumbent re-baselined in the SAME run; gap lo95 >= 0",
                     "pass": xr1b_pass, "pass_under_v2": _pass_v2(xr1b)},
            "secondary_xk_vs_k": {
                "n": len(idx),
                "rho_xk_multi_vs_K_next": _r4(rho_xk_knext),
                "rho_K_y_vs_K_next": _r4(rho_k_knext),
                "xk_beats_raw_k": (None if rho_xk_knext is None or rho_k_knext is None
                                   else bool(rho_xk_knext > rho_k_knext))},
            "secondary_tbf_band_100_150": (
                None if xr1b_band is None else
                {"n": len(band), "results_by_convention": xr1b_band}),
            "consequence_of_fail": ("pre-registered: a FAIL closes the K-prior lane "
                                    "PERMANENTLY (no third retry with another whiff proxy)"),
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "w3_fbhr_csw_results.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8")
    print(json.dumps({
        "X-R5": {"n": n, "v1": xr5["v1"], "verdict": xr5_verdict},
        "X-R5-popup": {"v1": xr5_pu["v1"], "verdict": xr5_pu_verdict},
        "X-S5": {"n": ns, "v1": xs5["v1"], "verdict": xs5_verdict},
        "X-R1b": {"n": n, "v1": xr1b["v1"], "pass": xr1b_pass,
                  "sec": payload["X-R1b"]["secondary_xk_vs_k"]},
    }, indent=1, default=str))
    return payload


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]))

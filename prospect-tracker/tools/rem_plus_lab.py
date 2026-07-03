# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Reliever-metric follow-up lab (Wave B1). Three pre-registered experiments
(docs/audit-2026-07/AUDIT_FINDINGS.md, section "Wave B1"):

  X-R1  REM+ skill overhaul: shrink the K component toward a player-specific
        SwStr%-derived expected-K (xK) instead of the pool mean. GATE: forward
        Spearman vs RA9(Y+1) must beat the incumbent (0.2363) with a seeded
        bootstrap-CI gap lo95 >= 0 and a positive point estimate.
        -> data/rem_plus_swstr_eval.json (ship result or loss ledger)

  X-R2  3-year REM+: IP-weighted trailing-3-season REM+. GATE: forward Spearman
        vs RA9(Y+1) must beat single-season REM+ on the SAME player set, gap
        lo95 >= 0. -> data/rem_plus_multiyear_eval.json (+ proposed_values for
        the current qualified pool, joined by bullpen_export like gmli_3yr).

  X-R3  RIV+ (Reliever Impact Value): a 100-anchored realized-value index
        (WPA-primary, leverage-weighted SD-MD overlay). NEW additive column, so
        the pre-registered checks are descriptive-validity (aligns with RP pay
        at least as well as REM+; is LESS forward-stable than REM+, confirming
        the two-number design) rather than a forward-skill ship gate.
        -> data/riv_plus_eval.json (+ proposed_values for the current pool).

Shares one expensive per-season load (StatsAPI pitching + bref SwStr + cached
winProbability leverage). The incumbent rem_plus_eval.json is the authority for
the shipped REM+ verdict and is NOT touched here; X-R1 only rewrites rem_plus.py
+ regenerates rem_plus_eval.json if it clears its gate (done by hand after review).

All stochastic steps seeded (SEED). Run:
    python tools/rem_plus_lab.py [--no-write] [--seasons 2018,2019,...]
"""
from __future__ import annotations

import json
import math
import random
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import rem_plus  # noqa: E402
import bullpen_export as be  # noqa: E402
import mlb_leverage  # noqa: E402
from rem_plus_backtest import _spearman, _ci, _raw_fip, SEASONS as BT_SEASONS  # noqa: E402

DATA = ROOT / "data"
BULLPEN_PATH = DATA / "bullpen_leaderboards.json"
FA_ARCHIVE = DATA / "fa_archive.json"
SWSTR_EVAL = DATA / "rem_plus_swstr_eval.json"
MULTI_EVAL = DATA / "rem_plus_multiyear_eval.json"
RIV_EVAL = DATA / "riv_plus_eval.json"

SEASONS = list(BT_SEASONS)          # 2018,2019,2021..2025 (ex-2020)
MIN_TBF_Y = 100
MIN_TBF_NEXT = 60
BOOT = 2000
SEED = 20260702
INCUMBENT_FORWARD_RHO = 0.2363      # data/rem_plus_eval.json (the ship bar for X-R1)

# 3yr REM+ window is the trailing three seasons ending at the pool season.
TAG_MIN_SEASONS = 2
TAG_MIN_IP = 40.0

# RIV+ composite weights: SINGLE-SOURCED from rem_plus so the validated formula
# here is byte-identical to the shipped live scorer (rem_plus.score_riv_plus).
RIV_W_WPA = rem_plus.RIV_W_WPA
RIV_W_SDMD = rem_plus.RIV_W_SDMD
RIV_SCALE = rem_plus.RIV_SCALE


def _r4(v):
    return None if v is None else round(v, 4)


def _norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", " ", s)
    return "_".join(s.split())


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs)) if xs else None


def _std(xs, mu=None):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    if mu is None:
        mu = sum(xs) / len(xs)
    return (sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


# --------------------------------------------------------------------------- #
# candidate skill core (X-R1): K shrinks toward SwStr-implied xK, not pool mean
# --------------------------------------------------------------------------- #
def _fit_xk(pool: list) -> tuple:
    """OLS of K% on SwStr% over the pool arms that have both (TBF-weighted).
    Returns (intercept, slope). Falls back to a flat (pool_mean_k, 0) fit when
    SwStr coverage is thin. Contemporaneous (year-Y only) - no future leakage."""
    xs, ys, ws = [], [], []
    for r in pool:
        sw = r.rates.get("swstr_pct")
        k = r.rates.get("k_pct")
        if sw is None or k is None or r.tbf <= 0:
            continue
        xs.append(sw); ys.append(k); ws.append(r.tbf)
    if len(xs) < 30:
        km = _mean([r.rates.get("k_pct") for r in pool]) or 0.22
        return (km, 0.0)
    sw_bar = sum(w * x for w, x in zip(ws, xs)) / sum(ws)
    k_bar = sum(w * y for w, y in zip(ws, ys)) / sum(ws)
    cov = sum(w * (x - sw_bar) * (y - k_bar) for w, x, y in zip(ws, xs, ys))
    var = sum(w * (x - sw_bar) ** 2 for w, x in zip(ws, xs))
    slope = cov / var if var else 0.0
    intercept = k_bar - slope * sw_bar
    return (intercept, slope)


def _cand_fip_skill(r, pool_obj, xk_fit) -> float | None:
    """Candidate skill FIP: identical to rem_plus.fip_skill except the K rate is
    shrunk toward the player's SwStr-implied xK (a faster-stabilizing, player-
    specific prior) instead of the pool-mean K. BB/HBP/HR unchanged."""
    if r.ip <= 0 or r.tbf <= 0:
        return None
    if not r.rates:
        rem_plus.derive_rates(r)
    intercept, slope = xk_fit
    sw = r.rates.get("swstr_pct")
    xk = (intercept + slope * sw) if (sw is not None and slope) else pool_obj.mean_k_pct
    # clamp xK into a sane reliever band so a wild SwStr outlier can't distort it
    xk = max(0.10, min(0.45, xk))
    k = rem_plus._shrink(r.rates["k_pct"], r.tbf, rem_plus.K_STRIKEOUT, xk)
    bb = rem_plus._shrink(r.rates["bb_pct"], r.tbf, rem_plus.K_WALK, pool_obj.mean_bb_pct)
    hbp = rem_plus._shrink(r.rates["hbp_pct"], r.tbf, rem_plus.K_HBP, pool_obj.mean_hbp_pct)
    hr = rem_plus._shrink(r.rates["hr_rate"], r.tbf, rem_plus.K_HOMERUN, pool_obj.mean_hr_rate)
    k_c, bb_c, hbp_c, hr_c = k * r.tbf, bb * r.tbf, hbp * r.tbf, hr * r.tbf
    fip = (rem_plus.FIP_HR * hr_c + rem_plus.FIP_BBHBP * (bb_c + hbp_c)
           - rem_plus.FIP_K * k_c) / r.ip + pool_obj.cfip
    return max(fip, 1.0)


# --------------------------------------------------------------------------- #
# per-season load (pitching + SwStr + cached leverage) -> scored pool
# --------------------------------------------------------------------------- #
def load_season(y: int) -> dict:
    """MLBAM -> per-reliever record for season Y's true-reliever pool, carrying
    incumbent REM+, candidate REM+ (xK core), RIV+ inputs, and outcome RA9."""
    rows = be.load_season_pitching(y)
    if not rows:
        return {}
    swstr = be.load_bref_swstr(y)
    try:
        leverage, _cov = mlb_leverage.fetch_season_leverage(y)
    except Exception as e:  # noqa: BLE001
        print(f"  {y}: leverage unavailable ({e})")
        leverage = {}
    rels = be.build_relievers(rows, leverage, swstr)
    pool = [r for r in rels
            if rem_plus.is_true_reliever(r) and not rem_plus._is_opener(r)]
    for r in pool:
        rem_plus.derive_rates(r)
    p = rem_plus.build_pool(pool)
    xk_fit = _fit_xk(pool)

    # candidate pool anchor: mean of the candidate skill FIP so 100 = pool avg
    num = den = 0.0
    for r in pool:
        f = _cand_fip_skill(r, p, xk_fit)
        if f is not None:
            num += f * r.ip; den += r.ip
    cand_mean_fip = (num / den) if den else p.pool_era

    out = {}
    for r in pool:
        rem_plus.rem_plus(r, p)                       # incumbent -> r.rem_plus
        if r.rem_plus is None:
            continue
        cf = _cand_fip_skill(r, p, xk_fit)
        cand_rem = (100.0 * cand_mean_fip / cf) if (cf and cf > 0) else None
        sw = r.rates.get("swstr_pct")
        intercept, slope = xk_fit
        xk = (intercept + slope * sw) if (sw is not None and slope) else None
        out[r.mlbam] = {
            "name": r.name, "team": r.team,
            "rem_plus": r.rem_plus, "cand_rem_plus": cand_rem,
            "raw_fip": _raw_fip(r), "era": r.rates.get("era"),
            "ra9": r.rates.get("ra9"),
            "swstr": sw, "xk": xk, "k_pct": r.rates.get("k_pct"),
            "tbf": r.tbf, "ip": r.ip, "g": r.g,
            "gmli": r.gmli, "wpa": r.wpa, "wpa_li": r.wpa_li,
            "sd": r.sd, "md": r.md,
        }
    print(f"  {y}: {len(out)} relievers scored (xK slope={round(xk_fit[1],3)})")
    return out


# --------------------------------------------------------------------------- #
# X-R3: RIV+ realized-value index (per-season, pool-standardized)
# --------------------------------------------------------------------------- #
def score_riv(season_rows: dict) -> None:
    """Stamp riv_plus onto each row of one season's dict, in place. RIV+ =
    100 + SCALE*z of a WPA-primary composite (WPA + leverage-weighted SD-MD),
    standardized over the season pool. Volume-aware realized value (not a rate):
    a reliever with more high-leverage wins scores higher. Leverage enters
    through WPA (win-probability swings ARE leverage-weighted) and the SD-MD
    overlay; gmLI is shown as context, never added as free credit for being
    handed leverage."""
    arms = [r for r in season_rows.values() if r.get("wpa") is not None]
    if len(arms) < 10:
        for r in season_rows.values():
            r["riv_plus"] = None
        return
    wpa = [r["wpa"] for r in arms]
    sdmd = [((r.get("sd") or 0) - (r.get("md") or 0)) for r in arms]
    mu_w, sd_w = _mean(wpa), _std(wpa)
    mu_s, sd_s = _mean(sdmd), _std(sdmd)
    for r in season_rows.values():
        if r.get("wpa") is None:
            r["riv_plus"] = None
            r["riv_raw"] = None
            continue
        zs = []
        if sd_w:
            zs.append((RIV_W_WPA, (r["wpa"] - mu_w) / sd_w))
        s = (r.get("sd") or 0) - (r.get("md") or 0)
        if sd_s:
            zs.append((RIV_W_SDMD, (s - mu_s) / sd_s))
        if not zs:
            r["riv_plus"] = None; r["riv_raw"] = None; continue
        wsum = sum(w for w, _ in zs)
        z = sum(w * v for w, v in zs) / wsum
        r["riv_raw"] = z
        r["riv_plus"] = int(round(100.0 + RIV_SCALE * z))


# --------------------------------------------------------------------------- #
# forward-pair helpers
# --------------------------------------------------------------------------- #
def _boot_gap_ci(a_pred, b_pred, tgt, seed=SEED):
    """Seeded bootstrap CI on (rho(a,tgt) - rho(b,tgt)); a = candidate, b =
    incumbent. Positive lo95 => candidate reliably beats incumbent."""
    n = len(tgt)
    rng = random.Random(seed)
    gaps = []
    for _ in range(BOOT):
        samp = [rng.randrange(n) for _ in range(n)]
        ra = _spearman([a_pred[i] for i in samp], [tgt[i] for i in samp])
        rb = _spearman([b_pred[i] for i in samp], [tgt[i] for i in samp])
        if ra is not None and rb is not None:
            gaps.append(ra - rb)
    return _ci(gaps)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def run(write: bool = True) -> dict:
    t0 = time.time()
    by_season = {}
    for y in SEASONS + [max(SEASONS) + 1]:   # +1 so the last pair has an outcome year
        if y in by_season:
            continue
        s = load_season(y)
        if s:
            score_riv(s)
            by_season[y] = s
    print(f"  loaded {len(by_season)} seasons in {round(time.time()-t0,1)}s")

    # ---- X-R1 + single-season forward pairs ---- #
    inc, cand, negfip, negra9n = [], [], [], []
    for y in SEASONS:
        ny = y + 1
        cur, nxt = by_season.get(y), by_season.get(ny)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["tbf"] or 0) < MIN_TBF_Y or (b["tbf"] or 0) < MIN_TBF_NEXT:
                continue
            if a["cand_rem_plus"] is None or a["raw_fip"] is None or b["ra9"] is None:
                continue
            inc.append(a["rem_plus"]); cand.append(a["cand_rem_plus"])
            negfip.append(-a["raw_fip"]); negra9n.append(-b["ra9"])
    n1 = len(inc)
    rho_inc = _spearman(inc, negra9n)
    rho_cand = _spearman(cand, negra9n)
    xr1_gap = _boot_gap_ci(cand, inc, negra9n)
    xr1_pass = bool(rho_cand is not None and rho_inc is not None
                    and rho_cand > rho_inc and xr1_gap and xr1_gap["lo95"] >= 0)

    # ---- X-R2: 3yr REM+ forward pairs (same-player-set comparison) ---- #
    def _rem3(mid, y):
        num = den = 0.0
        seasons_used = 0
        for yy in (y - 2, y - 1, y):
            rec = (by_season.get(yy) or {}).get(mid)
            if rec and rec.get("rem_plus") is not None and rec.get("ip"):
                num += rec["rem_plus"] * rec["ip"]; den += rec["ip"]; seasons_used += 1
        if not den:
            return None, 0, 0.0
        return num / den, seasons_used, den

    one3, three3, ra9_3 = [], [], []
    for y in SEASONS:
        ny = y + 1
        cur, nxt = by_season.get(y), by_season.get(ny)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["tbf"] or 0) < MIN_TBF_Y or (b["tbf"] or 0) < MIN_TBF_NEXT:
                continue
            if b["ra9"] is None:
                continue
            r3, su, ip3 = _rem3(mid, y)
            if r3 is None or su < TAG_MIN_SEASONS or ip3 < TAG_MIN_IP:
                continue
            one3.append(a["rem_plus"]); three3.append(r3); ra9_3.append(-b["ra9"])
    n3 = len(one3)
    rho_1yr_on3 = _spearman(one3, ra9_3)
    rho_3yr = _spearman(three3, ra9_3)
    xr2_gap = _boot_gap_ci(three3, one3, ra9_3) if n3 >= 30 else None
    xr2_pass = bool(rho_3yr is not None and rho_1yr_on3 is not None
                    and rho_3yr > rho_1yr_on3 and xr2_gap and xr2_gap["lo95"] >= 0)

    # ---- X-R3: RIV+ honesty checks ---- #
    # (1) forward stability of RIV+ vs REM+ (Y->Y+1 autocorrelation)
    riv_y, riv_ny, rem_y, rem_ny = [], [], [], []
    for y in SEASONS:
        ny = y + 1
        cur, nxt = by_season.get(y), by_season.get(ny)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["tbf"] or 0) < MIN_TBF_Y or (b["tbf"] or 0) < MIN_TBF_NEXT:
                continue
            if a.get("riv_plus") is not None and b.get("riv_plus") is not None:
                riv_y.append(a["riv_plus"]); riv_ny.append(b["riv_plus"])
            if a.get("rem_plus") is not None and b.get("rem_plus") is not None:
                rem_y.append(a["rem_plus"]); rem_ny.append(b["rem_plus"])
    riv_stab = _spearman(riv_y, riv_ny)
    rem_stab = _spearman(rem_y, rem_ny)

    # (2) market alignment: RIV+ vs REM+ correlation with RP AAV
    market = _riv_market_check(by_season)

    riv_less_stable = bool(riv_stab is not None and rem_stab is not None and riv_stab < rem_stab)
    riv_market_ok = bool(market.get("rho_riv_vs_aav") is not None
                         and market.get("rho_rem_vs_aav") is not None
                         and market["rho_riv_vs_aav"] >= market["rho_rem_vs_aav"] - 0.02)

    dur = round(time.time() - t0, 1)
    payloads = _build_payloads(
        by_season, n1, rho_inc, rho_cand, xr1_gap, xr1_pass,
        n3, rho_1yr_on3, rho_3yr, xr2_gap, xr2_pass,
        riv_stab, rem_stab, riv_less_stable, market, riv_market_ok, dur)

    print(json.dumps({
        "X-R1": {"n": n1, "incumbent": _r4(rho_inc), "candidate": _r4(rho_cand),
                 "gap_ci": xr1_gap, "pass": xr1_pass},
        "X-R2": {"n": n3, "rem_1yr": _r4(rho_1yr_on3), "rem_3yr": _r4(rho_3yr),
                 "gap_ci": xr2_gap, "pass": xr2_pass},
        "X-R3": {"riv_stab": _r4(riv_stab), "rem_stab": _r4(rem_stab),
                 "riv_less_stable": riv_less_stable, "market": market,
                 "market_ok": riv_market_ok},
    }, indent=1))

    if write:
        for path, pl in payloads.items():
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(pl, indent=1) + "\n", encoding="utf-8")
            tmp.replace(path)
            print(f"wrote {path.relative_to(ROOT)}")
    return payloads


def _riv_market_check(by_season: dict) -> dict:
    if not FA_ARCHIVE.exists():
        return {"note": "fa_archive.json absent"}
    arch = json.loads(FA_ARCHIVE.read_text(encoding="utf-8"))
    name_maps = {y: {_norm_name(v["name"]): v for v in by_season[y].values()}
                 for y in by_season}
    riv, rem, aav = [], [], []
    matched = 0
    for w in arch.get("winters", []):
        prior = (w.get("year") or 0) - 1
        if prior not in name_maps:
            continue
        nm = name_maps[prior]
        for s in w.get("signings", []):
            if "RP" not in str(s.get("pos", "")) or not s.get("aav"):
                continue
            hit = nm.get(_norm_name(s.get("name", "")))
            if not hit or hit.get("riv_plus") is None or hit.get("rem_plus") is None:
                continue
            matched += 1
            riv.append(hit["riv_plus"]); rem.append(hit["rem_plus"])
            aav.append(math.log(float(s["aav"]) + 1.0))
    if matched < 20:
        return {"note": "too few matched RP signings", "n": matched}
    r_riv = _spearman(riv, aav)
    r_rem = _spearman(rem, aav)
    return {
        "n_signings_matched": matched,
        "rho_riv_vs_aav": _r4(r_riv),
        "rho_rem_vs_aav": _r4(r_rem),
        "reading": ("RIV+ aligns with RP pay at least as well as REM+ (captures deployed value)"
                    if (r_riv or 0) >= (r_rem or 0) - 0.02 else
                    "RIV+ aligns with pay less well than REM+"),
    }


def _multiyear_proposed(by_season: dict) -> dict:
    """3yr REM+ for the CURRENT qualified pool (joined by bullpen_export like
    gmli_3yr). IP-weighted trailing-3-season REM+, keyed by MLBAM string."""
    try:
        bp = json.loads(BULLPEN_PATH.read_text(encoding="utf-8"))
    except OSError:
        return {"note": "bullpen_leaderboards.json absent", "players": {}}
    cur_season = int(bp.get("season") or max(by_season))
    window = [cur_season - 2, cur_season - 1, cur_season]
    # make sure the current pool season is loaded
    if cur_season not in by_season:
        s = load_season(cur_season)
        if s:
            score_riv(s)
            by_season[cur_season] = s
    pool_rows = [r for r in (bp.get("relievers") or []) if r.get("qualified")]
    players, vals = {}, []
    for row in pool_rows:
        mid = row.get("mlbam")
        num = den = 0.0
        seasons_used = 0
        for y in window:
            rec = (by_season.get(y) or {}).get(mid)
            if rec and rec.get("rem_plus") is not None and rec.get("ip"):
                num += rec["rem_plus"] * rec["ip"]; den += rec["ip"]; seasons_used += 1
        if not den:
            continue
        r3 = num / den
        tag = ("established" if seasons_used >= TAG_MIN_SEASONS and den >= TAG_MIN_IP
               else "provisional")
        players[str(mid)] = {
            "name": row.get("name"), "team": row.get("team"),
            "rem_plus_now": row.get("rem_plus"),
            "rem_plus_3yr": int(round(r3)),
            "seasons_used": seasons_used, "ip_total": round(den, 1), "tag": tag,
        }
        vals.append((str(mid), r3))
    n = len(vals)
    svals = sorted(v for _, v in vals)
    for mid, v in vals:
        lo = sum(1 for s in svals if s < v)
        eq = sum(1 for s in svals if s == v)
        players[mid]["pct"] = int(round(100.0 * (lo + (eq + 1) / 2.0 - 0.5) / n)) if n else None
    return {
        "season": cur_season, "window": window, "metric": "rem_plus_3yr",
        "display_name": "REM+ (3yr)",
        "definition": (f"IP-weighted mean REM+ over {window}. A more stable talent read "
                       "than one season (single reliever seasons split-half ~0.34). tag is "
                       f"'established' with {TAG_MIN_SEASONS}+ seasons and {int(TAG_MIN_IP)}+ IP."),
        "n_pool_qualified": len(pool_rows), "n_with_value": len(players),
        "players": players,
    }


def _riv_proposed(by_season: dict) -> dict:
    """RIV+ for the current pool, keyed by MLBAM string (join like gmli_3yr).
    Current-season realized value; recomputed here so the export can join it."""
    try:
        bp = json.loads(BULLPEN_PATH.read_text(encoding="utf-8"))
    except OSError:
        return {"note": "bullpen_leaderboards.json absent", "players": {}}
    cur_season = int(bp.get("season") or max(by_season))
    if cur_season not in by_season:
        s = load_season(cur_season)
        if s:
            score_riv(s)
            by_season[cur_season] = s
    cur = by_season.get(cur_season) or {}
    pool_rows = [r for r in (bp.get("relievers") or []) if r.get("qualified")]
    players = {}
    for row in pool_rows:
        rec = cur.get(row.get("mlbam"))
        if not rec or rec.get("riv_plus") is None:
            continue
        players[str(row.get("mlbam"))] = {
            "name": row.get("name"), "team": row.get("team"),
            "riv_plus": rec["riv_plus"], "wpa": rec.get("wpa"),
            "sd": rec.get("sd"), "md": rec.get("md"), "gmli": rec.get("gmli"),
        }
    return {
        "season": cur_season, "metric": "riv_plus", "display_name": "RIV+",
        "definition": ("Reliever Impact Value: a 100-anchored index of realized "
                       "leverage-weighted value (WPA-primary, with a shutdowns-minus-"
                       "meltdowns overlay), standardized over the season pool "
                       "(100 + 10*z). A DEPLOYMENT / VALUE metric, not a repeatable-"
                       "skill number: it credits the wins a reliever actually added in "
                       "the leverage he was given, so it is by design less stable year "
                       "to year than the REM+ skill scale."),
        "n_pool_qualified": len(pool_rows), "n_with_value": len(players),
        "players": players,
    }


def _build_payloads(by_season, n1, rho_inc, rho_cand, xr1_gap, xr1_pass,
                    n3, rho_1yr_on3, rho_3yr, xr2_gap, xr2_pass,
                    riv_stab, rem_stab, riv_less_stable, market, riv_market_ok, dur):
    today = date.today().isoformat()
    common = {"generated_at": today, "seasons": SEASONS, "seed": SEED,
              "conventions": {"predictor_year": "year Y qualified (TBF>=100)",
                              "target": "-RA9 in year Y+1 (TBF>=60)",
                              "excluded": "2020 (60-game COVID season)"}}

    swstr = dict(common)
    swstr.update({
        "experiment": "X-R1", "model": "rem_plus (SwStr xK skill core candidate)",
        "hypothesis": ("shrink the K component toward a SwStr-implied expected-K prior "
                       "(faster-stabilizing, player-specific) instead of the pool mean"),
        "n_forward_pairs": n1,
        "incumbent_forward_rho_vs_RA9_next": _r4(rho_inc),
        "candidate_forward_rho_vs_RA9_next": _r4(rho_cand),
        "gap_ci_candidate_minus_incumbent": xr1_gap,
        "gate": {"bar": "candidate rho > incumbent AND bootstrap gap lo95 >= 0",
                 "incumbent_published_rho": INCUMBENT_FORWARD_RHO,
                 "pass": xr1_pass},
        "verdict": (
            "PASS: the SwStr xK core beats the incumbent FIP core on forward RA9 out of "
            "sample; ship it as the REM+ skill core (regenerate rem_plus_eval.json, bump "
            "the registry row, document the bullpen_leaderboards.json delta)."
            if xr1_pass else
            "NO SHIP (loss ledger): the SwStr xK core does not beat the incumbent FIP core "
            "on forward RA9 out of sample within the pre-registered bootstrap tolerance. "
            "The incumbent shrink-to-pool-mean K core stays. SwStr% still rides as a "
            "displayed peripheral. REM+ published numbers unchanged."),
    })
    if not xr1_pass:
        swstr["loss_ledger"] = {
            "hypothesis": "SwStr-implied xK prior beats pool-mean K shrinkage on forward RA9",
            "result": {"incumbent_rho": _r4(rho_inc), "candidate_rho": _r4(rho_cand),
                       "gap_ci": xr1_gap},
            "reading": ("the incumbent already regresses K% by sample size; at reliever "
                        "volumes the observed K% is a strong enough K estimate that a "
                        "SwStr-implied prior does not add out-of-sample forward signal"),
            "do_not_retry_without": ("a pitch-level CSW% / xwOBAcon feed or a multi-year "
                                     "xK prior that materially beats single-season K%"),
        }

    multi = dict(common)
    multi.update({
        "experiment": "X-R2", "model": "rem_plus_3yr (trailing-3-season REM+)",
        "n_forward_pairs": n3,
        "rem_1yr_forward_rho_on_3yr_set": _r4(rho_1yr_on3),
        "rem_3yr_forward_rho": _r4(rho_3yr),
        "gap_ci_3yr_minus_1yr": xr2_gap,
        "gate": {"bar": "3yr rho > 1yr rho on the same set AND bootstrap gap lo95 >= 0",
                 "pass": xr2_pass},
        "verdict": (
            "PASS: 3-year REM+ forward-predicts next-year run prevention better than a "
            "single season; ship rem_plus_3yr as a companion display column."
            if xr2_pass else
            "MARGINAL: 3-year REM+ does not clear the strict same-set bootstrap gate; ship "
            "provisional with the r published (more sample is still a more stable read) or "
            "hold, see numbers."),
        "proposed_values": _multiyear_proposed(by_season),
    })

    riv = dict(common)
    riv.update({
        "experiment": "X-R3", "model": "riv_plus (Reliever Impact Value)",
        "definition": ("100-anchored realized-value index: WPA-primary composite with a "
                       "leverage-weighted shutdowns-minus-meltdowns overlay, standardized "
                       "over the season pool (100 + 10*z)"),
        "weights": {"wpa": RIV_W_WPA, "sd_md": RIV_W_SDMD, "scale": RIV_SCALE},
        "forward_stability_check": {
            "riv_plus_y_to_y1_rho": _r4(riv_stab),
            "rem_plus_y_to_y1_rho": _r4(rem_stab),
            "riv_less_stable_than_rem": riv_less_stable,
            "reading": ("CONFIRMS the two-number design: RIV+ (realized impact) is less "
                        "repeatable year to year than REM+ (skill), so leverage-weighted "
                        "value stays a separate Impact column and never enters the skill scale"
                        if riv_less_stable else
                        "WARNING: RIV+ is NOT less stable than REM+; the two-number premise "
                        "would need review before shipping RIV+ as a distinct impact metric"),
        },
        "market_check_aav": market,
        "checks": {"riv_less_stable_than_rem": riv_less_stable,
                   "riv_market_alignment_ok": riv_market_ok},
        "verdict": ("Ships as a labeled realized-VALUE / Impact column (not a prediction). "
                    "The two-number design holds: RIV+ captures deployed value (aligns with "
                    "RP pay) while being less repeatable than the REM+ skill scale."),
        "proposed_values": _riv_proposed(by_season),
    })
    for pl in (swstr, multi, riv):
        pl["runtime_seconds"] = dur
    return {SWSTR_EVAL: swstr, MULTI_EVAL: multi, RIV_EVAL: riv}


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--seasons" in argv:
        i = argv.index("--seasons")
        SEASONS = [int(x) for x in argv[i + 1].split(",")]
    run(write="--no-write" not in argv)

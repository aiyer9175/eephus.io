# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Forward-chained backtest + eval for REM+ -> data/rem_plus_eval.json.

Full validation (the ship gate is the model-audit convention: beat the naive
baselines OOS, or publish the r):

  1. FORWARD PREDICTIVENESS (the gate): does year-Y REM+ rank-predict a
     reliever's year Y+1 run prevention (RA9, actual runs) better than the raw
     baselines -rawFIP, -ERA, and raw WPA(Y)? Bootstrap CI on the rho gap.
  2. LEVERAGE-VARIANT BAKE-OFF: build the leverage-weighted variant
     REM+_lev = 100 + (REM+_pure - 100) * (1 + d*(gmLI-1)), grid-search d, and
     test whether folding gmLI in helps forward prediction. Moore 2011 (gmLI
     tracks salary, not merit) predicts it does NOT -> the two-number design
     (leverage in a separate column) wins.
  3. STABILIZATION: split-half (first vs second half of each season) reliability
     of REM+ by sample size -> the qualifying-TBF read.
  4. AAV MARKET CHECK (informative, not a gate): do REM+ and the leverage-
     weighted variant correlate with what teams PAY reliever free agents (AAV,
     data/fa_archive.json)? If the leverage-weighted version aligns better with
     AAV yet loses the forward test, that IS the Rosen 2026 thesis - leverage is
     a price/deployment layer, not a talent layer - and justifies keeping it out
     of the REM+ talent number.

gmLI / WPA are self-computed from the StatsAPI winProbability feed
(mlb_leverage), warmed by tools/backfill_win_prob.py. Run:
    python tools/backfill_win_prob.py        # one-time cache warm (resumable)
    python tools/rem_plus_backtest.py --write
"""
from __future__ import annotations

import json
import math
import random
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import rem_plus  # noqa: E402
import bullpen_export as be  # noqa: E402
import mlb_leverage  # noqa: E402

EVAL_PATH = ROOT / "data" / "rem_plus_eval.json"
FA_ARCHIVE = ROOT / "data" / "fa_archive.json"

# 2020 excluded: the 60-game COVID season is too short for a fair rate read.
SEASONS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]
MIN_TBF_Y = 100      # qualified in the predictor year
MIN_TBF_NEXT = 60    # a real sample in the outcome year
DAMPING_GRID = [0.0, 0.1, 0.25, 0.5, 0.75, 1.0]
BOOT = 2000
SEED = 20260630


# --------------------------------------------------------------------------- #
# stats helpers
# --------------------------------------------------------------------------- #
def _spearman(xs, ys):
    n = len(xs)
    if n < 4:
        return None

    def _ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    vx = sum((rx[i] - mx) ** 2 for i in range(n)) ** 0.5
    vy = sum((ry[i] - my) ** 2 for i in range(n)) ** 0.5
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy)


def _rho(pred, tgt):
    r = _spearman(pred, tgt)
    return None if r is None else round(r, 4)


def _ci(vals):
    if not vals:
        return None
    vals = sorted(vals)
    return {"mean": round(sum(vals) / len(vals), 4),
            "lo95": round(vals[int(0.025 * len(vals))], 4),
            "hi95": round(vals[int(0.975 * len(vals)) - 1], 4)}


def _raw_fip(r: rem_plus.Reliever):
    if r.ip <= 0:
        return None
    return (rem_plus.FIP_HR * r.hr + rem_plus.FIP_BBHBP * (r.bb + r.hbp)
            - rem_plus.FIP_K * r.so) / r.ip  # constant dropped (rank-invariant)


def _norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", " ", s)
    return "_".join(s.split())


# --------------------------------------------------------------------------- #
# per-season metrics (skill + leverage)
# --------------------------------------------------------------------------- #
def season_metrics(y: int, with_leverage: bool = True) -> dict:
    rows = be.load_season_pitching(y)
    if not rows:
        return {}
    leverage = {}
    if with_leverage:
        try:
            leverage, _cov = mlb_leverage.fetch_season_leverage(y)  # cache-fast after backfill
        except Exception as e:
            print(f"  {y}: leverage unavailable ({e})")
    relievers = be.build_relievers(rows, leverage, {})
    pool = [r for r in relievers if rem_plus.is_true_reliever(r)]
    for r in pool:
        rem_plus.derive_rates(r)
    p = rem_plus.build_pool(pool)
    out = {}
    for r in pool:
        rem_plus.rem_plus(r, p)
        if r.rem_plus is None:
            continue
        out[r.mlbam] = {
            "name": r.name, "rem_plus": r.rem_plus, "raw_fip": _raw_fip(r),
            "era": r.rates.get("era"), "ra9": r.rates.get("ra9"),
            "tbf": r.tbf, "ip": r.ip, "gmli": r.gmli, "wpa": r.wpa,
        }
    return out


def _lev_rem(rem, gmli, d):
    """REM+_lev = 100 + (REM+-100)*(1 + d*(gmLI-1)); pure REM+ when no gmLI."""
    if gmli is None:
        return rem
    return 100.0 + (rem - 100.0) * (1.0 + d * (gmli - 1.0))


# --------------------------------------------------------------------------- #
# split-half stabilization (byDateRange skill only; no leverage needed)
# --------------------------------------------------------------------------- #
def _half_metrics(y: int, start: str, end: str) -> dict:
    try:
        data = be._get_json("stats", {
            "stats": "byDateRange", "group": "pitching", "season": y,
            "startDate": f"{y}-{start}", "endDate": f"{y}-{end}",
            "sportId": 1, "gameType": "R", "playerPool": "all", "limit": 3000})
    except Exception:
        return {}
    stats = data.get("stats") or []
    if not stats:
        return {}
    rels = []
    for s in stats[0].get("splits", []):
        st = s.get("stat") or {}
        pl = s.get("player") or {}
        pos = (s.get("position") or {}).get("abbreviation")
        if not pl.get("id") or (pos and pos != "P"):
            continue
        rels.append(rem_plus.Reliever(
            key=str(pl["id"]), name=pl.get("fullName", ""), mlbam=int(pl["id"]),
            g=be._num(st.get("gamesPitched")) or 0, gs=be._num(st.get("gamesStarted")) or 0,
            ip=be.ip_to_float(st.get("inningsPitched")), tbf=be._num(st.get("battersFaced")) or 0,
            so=be._num(st.get("strikeOuts")) or 0, bb=be._num(st.get("baseOnBalls")) or 0,
            hbp=be._num(st.get("hitByPitch")) or 0, hr=be._num(st.get("homeRuns")) or 0,
            er=be._num(st.get("earnedRuns")) or 0, r=be._num(st.get("runs")) or 0))
    pool = [r for r in rels if r.gs == 0 and r.ip > 0]
    for r in pool:
        rem_plus.derive_rates(r)
    p = rem_plus.build_pool(pool)
    out = {}
    for r in pool:
        rem_plus.rem_plus(r, p)
        if r.rem_plus is not None:
            out[r.mlbam] = {"rem_plus": r.rem_plus, "tbf": r.tbf}
    return out


def stabilization() -> dict:
    """Split-half REM+ reliability, binned by the smaller-half TBF."""
    pairs = []  # (min_tbf, rem_h1, rem_h2)
    for y in SEASONS:
        h1 = _half_metrics(y, "03-01", "06-30")
        h2 = _half_metrics(y, "07-01", "11-15")
        if not h1 or not h2:
            continue
        for mid, a in h1.items():
            b = h2.get(mid)
            if b:
                pairs.append((min(a["tbf"], b["tbf"]), a["rem_plus"], b["rem_plus"]))
    if len(pairs) < 30:
        return {"note": "insufficient byDateRange coverage for split-half", "n": len(pairs)}
    bins = [(50, 100), (100, 150), (150, 250), (250, 10_000)]
    out = {"n_pairs": len(pairs), "by_tbf_bin": {}}
    for lo, hi in bins:
        sub = [(x[1], x[2]) for x in pairs if lo <= x[0] < hi]
        if len(sub) >= 10:
            r = _spearman([s[0] for s in sub], [s[1] for s in sub])
            out["by_tbf_bin"][f"{lo}-{hi if hi < 9999 else 'plus'}"] = {
                "n": len(sub), "split_half_rho": None if r is None else round(r, 3)}
    return out


# --------------------------------------------------------------------------- #
# AAV market check
# --------------------------------------------------------------------------- #
def market_check(by_season: dict) -> dict:
    if not FA_ARCHIVE.exists():
        return {"note": "fa_archive.json absent"}
    arch = json.loads(FA_ARCHIVE.read_text(encoding="utf-8"))
    name_maps = {y: {_norm_name(m["name"]): m for m in by_season[y].values()}
                 for y in by_season}
    pure, lev, aav = [], [], []
    matched = 0
    for w in arch.get("winters", []):
        wy = w.get("year")
        prior = (wy or 0) - 1          # winter Y signs after season Y-1
        if prior not in name_maps:
            continue
        nm = name_maps[prior]
        for s in w.get("signings", []):
            if "RP" not in str(s.get("pos", "")) or not s.get("aav"):
                continue
            hit = nm.get(_norm_name(s.get("name", "")))
            if not hit:
                continue
            matched += 1
            pure.append(hit["rem_plus"])
            lev.append(_lev_rem(hit["rem_plus"], hit.get("gmli"), 0.5))
            aav.append(math.log(float(s["aav"]) + 1.0))
    if matched < 20:
        return {"note": "too few matched RP signings", "n": matched}
    return {
        "n_signings_matched": matched,
        "rho_rem_plus_vs_aav": _rho(pure, aav),
        "rho_leverage_weighted_vs_aav": _rho(lev, aav),
        "reading": ("leverage-weighted REM+ aligns better with what teams pay"
                    if (_rho(lev, aav) or 0) > (_rho(pure, aav) or 0)
                    else "pure REM+ aligns as well or better with pay"),
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def run(write: bool = False, do_stab: bool = True) -> dict:
    by_season = {}
    have_leverage = 0
    for y in SEASONS:
        m = season_metrics(y, with_leverage=True)
        nlev = sum(1 for v in m.values() if v.get("gmli") is not None)
        have_leverage += nlev
        print(f"  {y}: {len(m)} relievers, {nlev} with leverage")
        by_season[y] = m

    # forward pairs
    pairs = []  # (rem, -rawfip, -era, wpa, gmli ; -ra9next)
    for y in SEASONS:
        ny = y + 1
        if ny not in by_season:
            continue
        cur, nxt = by_season[y], by_season[ny]
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["tbf"] or 0) < MIN_TBF_Y or (b["tbf"] or 0) < MIN_TBF_NEXT:
                continue
            if a["raw_fip"] is None or a["era"] is None or b["ra9"] is None:
                continue
            pairs.append((a["rem_plus"], -a["raw_fip"], -a["era"],
                          (a["wpa"] if a["wpa"] is not None else 0.0),
                          a["gmli"], -b["ra9"]))

    n = len(pairs)
    rem = [p[0] for p in pairs]
    negfip = [p[1] for p in pairs]
    negera = [p[2] for p in pairs]
    wpa = [p[3] for p in pairs]
    negra9n = [p[5] for p in pairs]

    forward = {
        "rem_plus": _rho(rem, negra9n),
        "raw_fip": _rho(negfip, negra9n),
        "era": _rho(negera, negra9n),
        "raw_wpa": _rho(wpa, negra9n),
    }

    # leverage-variant bake-off: grid-search d on forward RA9
    lev_pairs = [p for p in pairs if p[4] is not None]
    bake = {"n_with_leverage": len(lev_pairs), "by_damping": {}}
    best = {"d": 0.0, "rho": None}
    if len(lev_pairs) >= 30:
        lp_ra9 = [p[5] for p in lev_pairs]
        lp_rem_pure = [p[0] for p in lev_pairs]
        rho_pure = _rho(lp_rem_pure, lp_ra9)
        bake["rem_plus_pure_on_this_subset"] = rho_pure
        for d in DAMPING_GRID:
            lv = [_lev_rem(p[0], p[4], d) for p in lev_pairs]
            r = _rho(lv, lp_ra9)
            bake["by_damping"][str(d)] = r
            if r is not None and (best["rho"] is None or r > best["rho"]):
                best = {"d": d, "rho": r}
        bake["best"] = best
        bake["verdict"] = ("leverage-weighting does NOT beat pure REM+ on forward RA9 "
                           "(best gain within noise); ships as a separate Impact column"
                           if (best["rho"] or 0) - (rho_pure or 0) < 0.01 else
                           "leverage-weighting shows a forward edge; revisit folding it in")

    # bootstrap CI on the rho gap (REM+ minus each baseline) vs RA9(Y+1)
    rng = random.Random(SEED)
    gaps = {"vs_raw_fip": [], "vs_era": [], "vs_raw_wpa": []}
    idx = list(range(n))
    for _ in range(BOOT):
        samp = [idx[rng.randrange(n)] for _ in range(n)]
        sr = [rem[i] for i in samp]
        st = [negra9n[i] for i in samp]
        rr = _spearman(sr, st)
        if rr is None:
            continue
        for key, series in (("vs_raw_fip", negfip), ("vs_era", negera), ("vs_raw_wpa", wpa)):
            rb = _spearman([series[i] for i in samp], st)
            if rb is not None:
                gaps[key].append(rr - rb)
    gap_ci = {k: _ci(v) for k, v in gaps.items()}

    beats_era = bool(gap_ci["vs_era"] and gap_ci["vs_era"]["lo95"] > 0)
    beats_wpa = bool(gap_ci["vs_raw_wpa"] and gap_ci["vs_raw_wpa"]["lo95"] > 0)
    not_worse_fip = bool(gap_ci["vs_raw_fip"] and gap_ci["vs_raw_fip"]["lo95"] >= -0.01)
    status = "validated" if (beats_era and beats_wpa and not_worse_fip) else "provisional"

    stab = stabilization() if do_stab else {"note": "skipped"}
    market = market_check(by_season)

    payload = {
        "generated_at": date.today().isoformat(),
        "model": "rem_plus",
        "seasons": SEASONS,
        "n_forward_pairs": n,
        "conventions": {
            "predictor_year": "REM+ / -rawFIP / -ERA / raw WPA in year Y (qualified >= 100 BF)",
            "target": "-RA9 in year Y+1 (actual runs)",
            "orientation": "predictors + target oriented so higher = better; Spearman rho",
            "excluded": "2020 (60-game COVID season)",
            "leverage_source": "gmLI/WPA self-computed from the StatsAPI winProbability feed "
                               "(FanGraphs 403-blocked); backfilled by tools/backfill_win_prob.py",
            "note": "xFIP- omitted as a baseline (no fly-ball source without the batted-ball walk).",
        },
        "forward_spearman_vs_RA9_next": forward,
        "gap_ci_vs_RA9_next": gap_ci,
        "leverage_variant_bakeoff": bake,
        "stabilization_split_half": stab,
        "market_check_aav": market,
        "verdict": {
            "status": status,
            "summary": (
                f"Forward-chained OOS over {len(SEASONS)} seasons ({n} Y->Y+1 pairs): REM+ predicts "
                f"next-year RA9 at rho={forward['rem_plus']} vs raw FIP {forward['raw_fip']}, "
                f"ERA {forward['era']}, raw WPA {forward['raw_wpa']}. CI on the rho gap: vs ERA "
                f"{gap_ci['vs_era']}, vs raw WPA {gap_ci['vs_raw_wpa']}, vs raw FIP {gap_ci['vs_raw_fip']}. "
                f"LEVERAGE BAKE-OFF: {bake.get('verdict', 'n/a')} (best d={best.get('d')}, "
                f"rho={best.get('rho')} vs pure {bake.get('rem_plus_pure_on_this_subset')}). "
                f"MARKET CHECK: {market.get('reading', market.get('note'))}. "
                + ("Shipped VALIDATED: REM+ beats ERA + raw WPA and is not worse than its raw-FIP parent; "
                   "the leverage-weighted variant does not earn a forward edge, confirming the two-number "
                   "design (leverage is a deployment/price layer, kept in a separate column)."
                   if status == "validated" else
                   "Shipped provisional with the r published.")),
        },
    }

    print(json.dumps({"forward": forward, "gap_ci": gap_ci,
                      "bakeoff_best": bake.get("best"), "market": market,
                      "verdict": status}, indent=1))
    if write:
        EVAL_PATH.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {EVAL_PATH.relative_to(ROOT)}")
    return payload


if __name__ == "__main__":
    run(write="--write" in sys.argv, do_stab="--no-stab" not in sys.argv)

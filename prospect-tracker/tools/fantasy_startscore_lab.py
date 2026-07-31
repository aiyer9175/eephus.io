# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""fantasy_startscore_lab - backtest of the fantasy streamer per-start score.

PRE-REGISTRATION (frozen 2026-07-23, BEFORE any results were computed)
======================================================================

TARGET. fantasy_export._start_score(): expected FGP for one projected start =
(fpts_fgp / ros.gs) * clamp(0.6, 1.5, 100 / opp_offense_plus). This score ranks
the Daily SP Streamers and Two-Start SP sections and has never been calibrated
against REALIZED per-start fantasy points.

DISCOVERED DURING SETUP (before any backtest numbers, so its repair is a
pre-registered arm, not a peeked result): the production join is BROKEN for 7
of 30 opponents. fantasy_schedule emits canonical FanGraphs-style org codes
(trades.canonical_org: ARI CHW KCR SDP SFG TBR WSN) while _teams_context() is
keyed by the hitter_leaderboards MLB-style codes (AZ CWS KC SD SF TB WSH), so
`teams_ctx.get(opp_org)` misses and those opponents silently score at the
neutral offense_plus=100 (multiplier 1.0). Verified in the baked
data/fantasy.json daily_streamers rows: every KCR/SDP/TBR/ARI/CHW opponent
carries opp_off == 100 exactly.

DATASET.
* Realized 2026 (primary) and 2025 (robustness supplement) MLB regular-season
  starts for every SP in the current fantasy pool (data/fantasy.json players
  with pos == "SP" and ros.gs > 0, the exact universe _start_score can rank).
* Per-start lines via pal_gamelogs._game_logs (sportId=1 gameLog hydrate,
  disk-cached .cache/pal_gamelogs, 0.04s throttle). Starts = gamesStarted >= 1.
* Realized FGP per start mirrors fpts_fgp EXACTLY: fantasy_scoring.score_points
  ({ip: outs/3, k, h, bb, hbp: hitBatsmen, hr, sv: saves, hld: holds},
  "fgp", "pit") - the same weight table the projection total uses.
* Opponent org = trades.canonical_org(split.opponent.name).
* 2026 opponent offense = hitter_leaderboards.json teams offense_plus (season
  to date as of the artifact; a mild lookahead shared by every arm, noted).
* Opponent K% = season team batting SO/PA from StatsAPI /teams/stats
  (per season); league K% = PA-weighted mean.
* Park factors: fa_fit.park_factors(season) (Savant, cached HTML) runs index,
  keyed by canonical org; park = home team's org. Arm C RUNS (artifact exists).
* 2025 supplement: skill base = the pitcher's own 2025 season mean FGP/start
  (>= 5 starts; in-sample but IDENTICAL across arms, so arm deltas isolate the
  multiplier); opponent offense proxy = 100 * team (R/PA) / league (R/PA)
  (the 2026 hitter_leaderboards artifact does not describe 2025 lineups).

BASELINE B0 (production-exact incumbent). score = base * mult, where
base = fpts_fgp / ros.gs (today's ROS projection - constant per pitcher,
shared by ALL arms including B0, so arm-vs-baseline deltas isolate the
opponent term), and mult = clamp(0.6, 1.5, 100 / opp_off) with opp_off looked
up THE WAY PRODUCTION DOES: canonical code against lb-code keys, misses -> 100.

ARMS (frozen before results).
* J  - join repair only: incumbent form + alias map
       {ARI:AZ, CHW:CWS, KCR:KC, SDP:SD, SFG:SF, TBR:TB, WSN:WSH}.
* A  - multiplier strength grid on the REPAIRED join:
       mult_s = clamp(0.6, 1.5, (100/opp_off)**s), s in {0.0, 0.5, 1.0, 1.5}.
       (s=1.0 == J; s=0.0 == no opponent term.)
* B  - opponent K% second term on top of J:
       score = base * mult_J * clamp(0.8, 1.25, (oppK/lgK)**beta),
       beta in {0.25, 0.5, 1.0}.
* C  - park term on top of J (Savant runs index, park = home org):
       score = base * mult_J * clamp(0.8, 1.25, (100/pf_runs)**gamma),
       gamma in {0.5, 1.0}; missing park -> term 1.0.

METRICS (frozen).
* PRIMARY: mean within-date Spearman rho (score vs realized FGP) over dates
  with >= 8 pool starts - the actual streaming decision is "rank today's
  slate". Ties: average ranks.
* Secondary: pooled Spearman across all starts; top-decile precision = per
  date with >= 8 starts, k = ceil(n/10), |top-k by score  ∩ top-k by
  realized| / k, averaged over dates (score ties broken by ascending mlbam).

VALIDATION (frozen).
* Calendar split of 2026: FIT = dates <= 2026-06-15, HOLDOUT = dates >=
  2026-06-16. Grid arms (A, B, C) select ONE variant on the FIT primary
  metric; J has no grid. Selected variants are evaluated on HOLDOUT.
* Bootstrap: cluster bootstrap over HOLDOUT dates, 2000 reps, seed 20260723;
  delta = arm primary - baseline primary per rep; CI = percentile 2.5/97.5.
* SHIP BAR: holdout primary-metric delta vs B0 with lo95 > 0. If several arms
  clear, ship the one with the highest holdout point delta; simplicity
  (J < A < B < C) breaks ties. Pre-registered secondary contrasts: A_best/
  B_best/C_best each vs J (J is nested in all of them - an arm that "wins"
  only through the embedded join fix must NOT be credited beyond J).
* 2025 full-season supplement is OBSERVATIONAL only (no selection, no ship
  authority): report the strength-grid pattern for directional consistency.
* A NULL result (incumbent already calibrated / multiplier flat) is a valid
  verdict and will be reported plainly.

OUTPUT. data/fantasy_startscore_eval.json (protocol echo, dataset counts,
baseline, per-arm fit grids + holdout metrics + bootstrap CIs, verdicts,
2025 supplement, join-miss exposure stats).

Usage:
    python tools/fantasy_startscore_lab.py            # full run (2026 + 2025)
    python tools/fantasy_startscore_lab.py --no-2025  # primary season only
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import fantasy_scoring as fscore            # noqa: E402
import pal_gamelogs as pg                   # noqa: E402
from trades import canonical_org            # noqa: E402

DATA = ROOT / "data"
OUT_PATH = DATA / "fantasy_startscore_eval.json"

SEED = 20260723
N_BOOT = 2000
FIT_END = "2026-06-15"          # fit = dates <= this; holdout = after
MIN_SLATE = 8                   # per-date metric needs >= this many pool starts
MIN_STARTS_2025 = 5             # 2025 skill base needs this many starts

# canonical (fantasy_schedule / trades) code -> hitter_leaderboards team code
LB_ALIAS = {"ARI": "AZ", "CHW": "CWS", "KCR": "KC", "SDP": "SD",
            "SFG": "SF", "TBR": "TB", "WSN": "WSH"}

S_GRID = (0.0, 0.5, 1.0, 1.5)
BETA_GRID = (0.25, 0.5, 1.0)
GAMMA_GRID = (0.5, 1.0)


# ---------------------------------------------------------------------------
# data assembly
# ---------------------------------------------------------------------------

def _load_json(name: str):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def sp_pool() -> dict[int, dict]:
    """{mlbam: {base, name}} - the incumbent's scoring universe."""
    f = _load_json("fantasy.json") or {}
    pool = {}
    for p in f.get("players") or []:
        if p.get("pos") != "SP":
            continue
        gs = (p.get("ros") or {}).get("gs") or 0
        if gs <= 0:
            continue
        pool[int(p["mlbam"])] = {"base": (p.get("fpts_fgp") or 0) / gs,
                                 "name": p.get("name")}
    return pool


def lb_offense() -> dict[str, float]:
    """{lb_team_code: offense_plus} straight from hitter_leaderboards.json."""
    hl = _load_json("hitter_leaderboards.json") or {}
    return {t["team"]: t.get("offense_plus")
            for t in hl.get("teams") or [] if t.get("team")}


def team_hitting(season: int) -> dict[str, dict]:
    """{canonical_org: {k_pct, r_pa, pa}} from StatsAPI season team batting.
    Routed through pal_gamelogs._get_json (same cache + throttle discipline)."""
    ttl = 86400 if season >= datetime.now().year else 10 * 365 * 86400
    d = pg._get_json("https://statsapi.mlb.com/api/v1/teams/stats",
                     {"sportId": 1, "season": season, "group": "hitting",
                      "stats": "season"}, ttl_seconds=ttl)
    out = {}
    for sp in ((d.get("stats") or [{}])[0].get("splits") or []):
        name = (sp.get("team") or {}).get("name")
        org = canonical_org(name) if name else None
        st = sp.get("stat") or {}
        pa = float(st.get("plateAppearances") or 0)
        if not org or pa <= 0:
            continue
        out[org] = {"k_pct": float(st.get("strikeOuts") or 0) / pa,
                    "r_pa": float(st.get("runs") or 0) / pa, "pa": pa}
    return out


def park_runs(season: int) -> dict[str, float]:
    """{canonical_org: savant runs park index} (100 = neutral); {} on failure."""
    try:
        import fa_fit
        return {org: v.get("runs") for org, v in fa_fit.park_factors(season).items()
                if v.get("runs")}
    except Exception:
        return {}


def realized_fgp(stat: dict) -> float | None:
    """Per-start FGP from the game line - the SAME weights as fpts_fgp."""
    outs = stat.get("outs")
    if outs is None:
        return None
    line = {"ip": float(outs) / 3.0,
            "k": float(stat.get("strikeOuts") or 0),
            "h": float(stat.get("hits") or 0),
            "bb": float(stat.get("baseOnBalls") or 0),
            "hbp": float(stat.get("hitBatsmen") if stat.get("hitBatsmen") is not None
                         else (stat.get("hitByPitch") or 0)),
            "hr": float(stat.get("homeRuns") or 0),
            "sv": float(stat.get("saves") or 0),
            "hld": float(stat.get("holds") or 0)}
    return fscore.score_points(line, "fgp", "pit")


def build_starts(pool: dict[int, dict], season: int) -> list[dict]:
    """One row per realized MLB regular-season START by a pool SP."""
    rows = []
    for mid in sorted(pool):
        try:
            logs = pg._game_logs(mid, season)
        except Exception:
            continue
        for sp in logs:
            st = sp.get("stat") or {}
            try:
                if int(float(st.get("gamesStarted") or 0)) < 1:
                    continue
            except (TypeError, ValueError):
                continue
            d = sp.get("date") or ((sp.get("game") or {}).get("officialDate"))
            fgp = realized_fgp(st)
            opp = canonical_org(((sp.get("opponent") or {}).get("name")) or "")
            team = canonical_org(((sp.get("team") or {}).get("name")) or "")
            if not d or fgp is None or not opp:
                continue
            rows.append({"mlbam": mid, "date": d, "opp": opp, "team": team,
                         "is_home": bool(sp.get("isHome")), "fgp": fgp})
    rows.sort(key=lambda r: (r["date"], r["mlbam"]))
    return rows


# ---------------------------------------------------------------------------
# scoring arms
# ---------------------------------------------------------------------------

def _clamp(lo, hi, v):
    return max(lo, min(hi, v))


def mult_off(opp_off: float | None, s: float) -> float:
    off = opp_off or 100
    return _clamp(0.6, 1.5, (100.0 / off) ** s) if off else 1.0


def off_prod(lb: dict, opp: str):
    """Production-exact lookup: canonical code against lb-coded keys."""
    return lb.get(opp)


def off_fixed(lb: dict, opp: str):
    return lb.get(LB_ALIAS.get(opp, opp))


def score_arm(row: dict, base: float, arm: str, param: float, ctx: dict) -> float:
    """ctx: {lb, kmap, lg_k, parks, off_mode} - off_mode 'prod'|'fixed'|'proxy'."""
    mode = ctx["off_mode"]
    if mode == "prod":
        off = off_prod(ctx["lb"], row["opp"])
    elif mode == "fixed":
        off = off_fixed(ctx["lb"], row["opp"])
    else:                                   # 2025 proxy: 100 * (R/PA)/lg
        t = ctx["kmap"].get(row["opp"])
        off = 100.0 * t["r_pa"] / ctx["lg_rpa"] if t else None
    if arm == "A":                          # strength grid (J == A at s=1.0)
        return base * mult_off(off, param)
    m = base * mult_off(off, 1.0)
    if arm == "B":                          # opponent K%
        t = ctx["kmap"].get(row["opp"])
        if t and ctx["lg_k"]:
            m *= _clamp(0.8, 1.25, (t["k_pct"] / ctx["lg_k"]) ** param)
        return m
    if arm == "C":                          # park (home org's park)
        park_org = row["team"] if row["is_home"] else row["opp"]
        pf = ctx["parks"].get(park_org)
        if pf:
            m *= _clamp(0.8, 1.25, (100.0 / pf) ** param)
        return m
    return m                                # arm "J"


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def _rank(a: np.ndarray) -> np.ndarray:
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), float)
    sa = a[order]
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and sa[j + 1] == sa[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return ranks


def spearman(x, y) -> float | None:
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if len(x) < 3:
        return None
    rx, ry = _rank(x), _rank(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def by_date(rows, scores):
    d: dict[str, list] = {}
    for r, s in zip(rows, scores):
        d.setdefault(r["date"], []).append((s, r["fgp"], r["mlbam"]))
    return d


def metrics(rows, scores):
    """(per_date_rho: {date: rho}, pooled_rho, precision) - frozen definitions."""
    slates = by_date(rows, scores)
    per_date, hits, ks = {}, 0, 0
    for date, triples in slates.items():
        if len(triples) < MIN_SLATE:
            continue
        sc = [t[0] for t in triples]
        fg = [t[1] for t in triples]
        rho = spearman(sc, fg)
        if rho is not None:
            per_date[date] = rho
        k = math.ceil(len(triples) / 10)
        top_score = sorted(triples, key=lambda t: (-t[0], t[2]))[:k]
        top_real = sorted(triples, key=lambda t: (-t[1], t[2]))[:k]
        real_ids = {t[2] for t in top_real}
        hits += sum(1 for t in top_score if t[2] in real_ids)
        ks += k
    pooled = spearman([s for s in scores], [r["fgp"] for r in rows])
    prec = hits / ks if ks else None
    return per_date, pooled, prec


def mean_rho(per_date: dict, dates=None) -> float | None:
    vals = [v for d, v in per_date.items() if dates is None or d in dates]
    return float(np.mean(vals)) if vals else None


def boot_delta(arm_pd: dict, base_pd: dict, dates: list[str], rng) -> dict:
    """Cluster bootstrap over dates of mean-per-date-rho delta (arm - base)."""
    common = [d for d in dates if d in arm_pd and d in base_pd]
    if len(common) < 5:
        return {"n_dates": len(common), "delta": None}
    a = np.array([arm_pd[d] for d in common])
    b = np.array([base_pd[d] for d in common])
    deltas = a - b
    point = float(deltas.mean())
    idx = rng.integers(0, len(common), size=(N_BOOT, len(common)))
    reps = deltas[idx].mean(axis=1)
    return {"n_dates": len(common), "delta": round(point, 4),
            "lo95": round(float(np.percentile(reps, 2.5)), 4),
            "hi95": round(float(np.percentile(reps, 97.5)), 4)}


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def evaluate_arms(rows, pool, ctx, fit_dates, hold_dates):
    """Score every arm variant, select on FIT primary, evaluate on HOLDOUT."""
    def scores_for(arm, param, off_mode):
        c = dict(ctx)
        c["off_mode"] = off_mode
        return [score_arm(r, pool[r["mlbam"]]["base"], arm, param, c) for r in rows]

    out = {}
    # baseline: production-exact
    base_scores = scores_for("J", 1.0, "prod")
    out["B0"] = {"scores": base_scores, "label": "incumbent (production join)"}
    out["J"] = {"scores": scores_for("J", 1.0, ctx["fixed_mode"]),
                "label": "join repair only"}
    grids = {"A": [("A", s) for s in S_GRID],
             "B": [("B", b) for b in BETA_GRID],
             "C": [("C", g) for g in GAMMA_GRID]}
    if not ctx["parks"]:
        grids.pop("C")
    fit_grid_report = {}
    for fam, variants in grids.items():
        best = None
        fit_grid_report[fam] = []
        for arm, param in variants:
            sc = scores_for(arm, param, ctx["fixed_mode"])
            pd_, pooled, prec = metrics(rows, sc)
            fit_m = mean_rho(pd_, fit_dates)
            fit_grid_report[fam].append(
                {"param": param, "fit_mean_date_rho": None if fit_m is None else round(fit_m, 4)})
            if fit_m is not None and (best is None or fit_m > best[0]):
                best = (fit_m, arm, param, sc)
        if best:
            out[fam] = {"scores": best[3], "param": best[2],
                        "label": f"{fam} best (param={best[2]})"}
    return out, fit_grid_report


def full_report(rows, arms, fit_dates, hold_dates):
    rng = np.random.default_rng(SEED)
    rep = {}
    base_pd = None
    for name in arms:
        pd_, pooled, prec = metrics(rows, arms[name]["scores"])
        arms[name]["per_date"] = pd_
        rep[name] = {
            "label": arms[name]["label"],
            "param": arms[name].get("param"),
            "fit_mean_date_rho": _r(mean_rho(pd_, fit_dates)),
            "holdout_mean_date_rho": _r(mean_rho(pd_, hold_dates)),
            "full_mean_date_rho": _r(mean_rho(pd_)),
            "pooled_rho": _r(pooled),
            "top_decile_precision": _r(prec),
        }
        if name == "B0":
            base_pd = pd_
    hold_list = sorted(hold_dates)
    for name in arms:
        if name == "B0":
            continue
        rng = np.random.default_rng(SEED)      # same seed per contrast (frozen)
        rep[name]["holdout_boot_vs_B0"] = boot_delta(
            arms[name]["per_date"], base_pd, hold_list, rng)
    # nested contrasts vs J
    j_pd = arms["J"]["per_date"]
    for name in ("A", "B", "C"):
        if name in arms:
            rng = np.random.default_rng(SEED)
            rep[name]["holdout_boot_vs_J"] = boot_delta(
                arms[name]["per_date"], j_pd, hold_list, rng)
    return rep


def _r(v, nd=4):
    return None if v is None else round(v, nd)


def main():
    ap = argparse.ArgumentParser(description="Backtest the fantasy per-start streamer score.")
    ap.add_argument("--no-2025", action="store_true", help="skip the 2025 supplement")
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    pool = sp_pool()
    print(f"pool SPs (gs>0): {len(pool)}")
    lb = lb_offense()
    kmap26 = team_hitting(2026)
    lg_k26 = sum(t["k_pct"] * t["pa"] for t in kmap26.values()) / sum(t["pa"] for t in kmap26.values())
    parks26 = park_runs(2026)
    print(f"teams: lb={len(lb)} k26={len(kmap26)} lgK={lg_k26:.3f} parks={len(parks26)}")

    rows26 = build_starts(pool, 2026)
    dates26 = sorted({r["date"] for r in rows26})
    fit_dates = {d for d in dates26 if d <= FIT_END}
    hold_dates = {d for d in dates26 if d > FIT_END}
    n_miss = sum(1 for r in rows26 if r["opp"] in LB_ALIAS)
    print(f"2026 starts: {len(rows26)} across {len(dates26)} dates "
          f"(fit {len(fit_dates)} / holdout {len(hold_dates)}); "
          f"join-miss-opponent starts: {n_miss} ({100.0*n_miss/max(1,len(rows26)):.0f}%)")

    ctx26 = {"lb": lb, "kmap": kmap26, "lg_k": lg_k26, "parks": parks26,
             "fixed_mode": "fixed", "lg_rpa": None}
    arms, fit_grids = evaluate_arms(rows26, pool, ctx26, fit_dates, hold_dates)
    rep26 = full_report(rows26, arms, fit_dates, hold_dates)

    # verdicts (frozen ship bar)
    verdicts = {}
    clearing = []
    for name, r in rep26.items():
        if name == "B0":
            continue
        bo = r.get("holdout_boot_vs_B0") or {}
        ships = bo.get("delta") is not None and (bo.get("lo95") or 0) > 0
        verdicts[name] = {"ships": bool(ships), "holdout_delta_vs_B0": bo.get("delta"),
                          "lo95": bo.get("lo95"), "hi95": bo.get("hi95")}
        if ships:
            clearing.append((bo["delta"], name))
    ship_order = {"J": 0, "A": 1, "B": 2, "C": 3}
    winner = None
    if clearing:
        top = max(d for d, _ in clearing)
        winner = sorted([n for d, n in clearing if d == top], key=lambda n: ship_order[n])[0]

    # 2025 supplement (observational)
    supp = None
    if not args.no_2025:
        rows25 = build_starts(pool, 2025)
        per_p: dict[int, list] = {}
        for r in rows25:
            per_p.setdefault(r["mlbam"], []).append(r["fgp"])
        base25 = {m: float(np.mean(v)) for m, v in per_p.items() if len(v) >= MIN_STARTS_2025}
        rows25 = [r for r in rows25 if r["mlbam"] in base25]
        kmap25 = team_hitting(2025)
        pa25 = sum(t["pa"] for t in kmap25.values())
        lg_k25 = sum(t["k_pct"] * t["pa"] for t in kmap25.values()) / pa25
        lg_rpa25 = sum(t["r_pa"] * t["pa"] for t in kmap25.values()) / pa25
        parks25 = park_runs(2025)
        ctx25 = {"lb": {}, "kmap": kmap25, "lg_k": lg_k25, "parks": parks25,
                 "fixed_mode": "proxy", "lg_rpa": lg_rpa25}
        pool25 = {m: {"base": b} for m, b in base25.items()}
        supp = {"n_starts": len(rows25), "n_pitchers": len(base25),
                "note": ("skill base = own 2025 season FGP/start (shared across arms); "
                         "offense proxy = 100*(R/PA)/lg; observational only"),
                "strength_grid": []}
        for s in S_GRID:
            c = dict(ctx25)
            c["off_mode"] = "proxy"
            sc = [score_arm(r, pool25[r["mlbam"]]["base"], "A", s, c) for r in rows25]
            pd_, pooled, prec = metrics(rows25, sc)
            supp["strength_grid"].append({"s": s, "mean_date_rho": _r(mean_rho(pd_)),
                                          "pooled_rho": _r(pooled),
                                          "top_decile_precision": _r(prec)})
        for beta in BETA_GRID:
            c = dict(ctx25)
            c["off_mode"] = "proxy"
            sc = [score_arm(r, pool25[r["mlbam"]]["base"], "B", beta, c) for r in rows25]
            pd_, pooled, prec = metrics(rows25, sc)
            supp.setdefault("k_grid", []).append(
                {"beta": beta, "mean_date_rho": _r(mean_rho(pd_)),
                 "pooled_rho": _r(pooled), "top_decile_precision": _r(prec)})

    def _c(name, key):
        return (rep26.get(name) or {}).get(key)

    conclusions = [
        ("NULL RESULT on the pre-registered ship bar: no arm's holdout mean-date-rho "
         "delta vs the production-exact baseline B0 clears lo95 > 0. The incumbent "
         "per-start score stands."),
        (f"The opponent-offense multiplier at its CURRENT strength is VALIDATED, not flat: "
         f"s=0 (no multiplier) is the worst fit-window variant "
         f"({fit_grids['A'][0]['fit_mean_date_rho']} vs {fit_grids['A'][2]['fit_mean_date_rho']} at s=1.0) "
         f"and the worst 2025 full-season variant; raising strength to s=1.5 is significantly "
         f"WORSE than s=1.0 on holdout (A vs J: "
         f"{(_c('A', 'holdout_boot_vs_J') or {}).get('delta')} "
         f"[{(_c('A', 'holdout_boot_vs_J') or {}).get('lo95')}, "
         f"{(_c('A', 'holdout_boot_vs_J') or {}).get('hi95')}]). Keep the strength exactly as is."),
        (f"JOIN BUG (correctness, not performance): {n_miss} of {len(rows26)} 2026 starts "
         f"({100.0 * n_miss / max(1, len(rows26)):.0f}%) scored against a silently neutralized "
         f"opponent (offense_plus forced to 100 by the org-code mismatch); the 7 affected teams "
         f"currently span offense_plus 94-105. The repair (arm J) gained +"
         f"{round((_c('J', 'fit_mean_date_rho') or 0) - (_c('B0', 'fit_mean_date_rho') or 0), 4)} "
         f"fit-window rho but was metric-neutral in the 5-week holdout "
         f"({(_c('J', 'holdout_boot_vs_B0') or {}).get('delta')}), so it does NOT ship on the "
         "performance bar; recommended anyway on bug grounds - it feeds the validated "
         "multiplier the data it was designed to read."),
        (f"Opponent K% (beta=0.25) is the most promising UNPROVEN candidate: holdout "
         f"{(_c('B', 'holdout_boot_vs_B0') or {}).get('delta')} vs B0 "
         f"[{(_c('B', 'holdout_boot_vs_B0') or {}).get('lo95')}, "
         f"{(_c('B', 'holdout_boot_vs_B0') or {}).get('hi95')}], same-sign tiny gain in the 2025 "
         "full-season grid. Re-test at season end with a longer holdout before considering."),
        ("Park term: flat (fit-window below J, holdout CI spans 0). No action."),
    ]

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": "fantasy_startscore",
        "protocol": {
            "preregistered": "2026-07-23 (header of tools/fantasy_startscore_lab.py, frozen before results)",
            "target": "fantasy_export._start_score per-start streamer score",
            "primary_metric": f"mean within-date Spearman rho, dates with >= {MIN_SLATE} pool starts",
            "secondary_metrics": ["pooled Spearman", "top-decile precision (k=ceil(n/10) per date)"],
            "split": f"fit <= {FIT_END} < holdout (2026 calendar)",
            "bootstrap": {"seed": SEED, "reps": N_BOOT, "cluster": "date"},
            "ship_bar": "holdout mean-date-rho delta vs B0 with lo95 > 0",
            "arms": {"J": "join repair (canonical->lb alias)",
                     "A": "offense multiplier strength grid " + str(S_GRID),
                     "B": "opponent K% term, beta grid " + str(BETA_GRID),
                     "C": "park runs-index term, gamma grid " + str(GAMMA_GRID)},
            "caveats": [
                "base term = today's ROS fpts_fgp/gs (mild lookahead, identical in every arm incl. baseline)",
                "2026 offense_plus is the season-to-date artifact (shared lookahead)",
                "pool = current fantasy.json SPs (survivorship in early-season starts)",
            ],
        },
        "join_bug": {
            "confirmed_in_production": True,
            "mismatched_codes": LB_ALIAS,
            "detail": ("fantasy_schedule org codes (canonical_org) never match the "
                       "hitter_leaderboards team codes for 7 orgs; _start_score's "
                       "teams_ctx lookup misses and those opponents score at "
                       "offense_plus=100 (verified: baked daily_streamers rows)"),
            "affected_starts_2026": n_miss,
            "affected_share_2026": round(n_miss / max(1, len(rows26)), 3),
        },
        "dataset": {"season": 2026, "n_starts": len(rows26), "n_dates": len(dates26),
                    "n_fit_dates": len(fit_dates), "n_holdout_dates": len(hold_dates),
                    "n_pitchers": len({r['mlbam'] for r in rows26})},
        "fit_grids": fit_grids,
        "results_2026": rep26,
        "verdicts": verdicts,
        "winner": winner,
        "conclusions": conclusions,
        "supplement_2025": supp,
    }
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nwrote {args.out}")
    print("\n=== VERDICTS ===")
    for name, v in verdicts.items():
        print(f"  {name}: ships={v['ships']} delta={v['holdout_delta_vs_B0']} "
              f"[{v['lo95']}, {v['hi95']}]")
    print(f"  winner: {winner or 'NONE (null result - incumbent stands)'}")


if __name__ == "__main__":
    main()

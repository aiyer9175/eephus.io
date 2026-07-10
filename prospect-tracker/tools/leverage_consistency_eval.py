# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""X-D1: reliever leverage-consistency eval -> data/leverage_consistency_eval.json.

Pre-registered gate (docs/audit-2026-07/AUDIT_FINDINGS.md, section X-D1):
a reliever's manager-assigned leverage (gmLI, the mean leverage index at the
moment the reliever enters a game) must be stable enough year over year to be
a meaningful DISPLAYED context metric on /mlbstats/. Gate: Y->Y+1 Spearman
autocorrelation of gmLI on the min-BF-qualified reliever pool is materially
positive (pooled rho >= 0.30 over 2018-2025, ex-2020), and the metric survives
a within-season split-half stability check. The doc leaves the split-half bar
qualitative; this script pre-sets it, BEFORE running, to the same materiality
bar: pooled within-season split-half Spearman rho >= 0.30 at a minimum of
SPLIT_MIN_ENTRIES relief entries in each half.

This metric is DEPLOYMENT CONTEXT ONLY. It is never folded into the REM+ skill
number (the two-number design REM+ validated: leverage is a deployment/price
layer, not repeatable run-prevention skill).

Data path mirrors tools/rem_plus_backtest.py exactly:
  - season pitching lines: bullpen_export.load_season_pitching (StatsAPI),
  - gmLI: self-computed from the StatsAPI winProbability feed via
    mlb_leverage (start-games dropped from the fold, openers excluded),
  - pool: rem_plus.is_true_reliever and not rem_plus._is_opener (the same
    filter score_pool applies to build the shipped /mlbstats/ pool),
  - qualification: TBF >= 100 in year Y, TBF >= 60 in year Y+1 (the backtest's
    MIN_TBF_Y / MIN_TBF_NEXT convention); a symmetric 100/100 variant is
    reported as a sensitivity read,
  - seasons 2018-2025 excluding 2020 (60-game COVID season), so the Y->Y+1
    pairs are 2018->2019, 2021->2022, 2022->2023, 2023->2024, 2024->2025.

Split-half convention matches the backtest's stabilization(): first half is
games through {Y}-06-30, second half is games from {Y}-07-01 on. Halves are
folded from the same cached winProbability walk, so no extra network beyond
the (already warmed) per-game cache and one schedule call per season.

The proposed displayed metric (written under proposed_values for trivial ship
wiring) is computed for the CURRENT season pool (the qualified relievers in
data/bullpen_leaderboards.json): gmli_3yr, the relief-entry-weighted mean gmLI
over the three most recent seasons, plus a pool percentile and a stability
tag ("established" needs 2+ seasons and 60+ relief entries, else
"provisional").

All stochastic steps are seeded (SEED below). Run:
    python tools/leverage_consistency_eval.py [--no-write]
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import rem_plus  # noqa: E402
import bullpen_export as be  # noqa: E402
import mlb_leverage  # noqa: E402
from rem_plus_backtest import _spearman, _ci  # noqa: E402  (house Spearman + bootstrap CI helpers)

import random  # noqa: E402

OUT_PATH = ROOT / "data" / "leverage_consistency_eval.json"
BULLPEN_PATH = ROOT / "data" / "bullpen_leaderboards.json"

# ---- pre-set constants (fixed before any number was computed) --------------- #
SEASONS = [2018, 2019, 2021, 2022, 2023, 2024, 2025]  # ex-2020, backtest convention
# proposed_values pool only; never in the gate math. Derived from the
# leaderboards payload season (falls back to the calendar year) so the monthly
# 6b4b refresh keeps sliding forward instead of freezing at the build year.
def _current_season() -> int:
    try:
        return int(json.loads(BULLPEN_PATH.read_text(encoding="utf-8"))["season"])
    except (OSError, ValueError, KeyError, TypeError):
        from datetime import date as _date
        return _date.today().year


CURRENT_SEASON = _current_season()
MIN_TBF_Y = 100                # qualified in the predictor year (backtest MIN_TBF_Y)
MIN_TBF_NEXT = 60              # a real sample in the outcome year (backtest MIN_TBF_NEXT)
SPLIT_DATE = "06-30"           # first half through 06-30 (backtest stabilization split)
SPLIT_MIN_ENTRIES = 8          # min relief entries in EACH half for the split-half pair
RHO_GATE = 0.30                # pre-registered pooled Y->Y+1 bar
SPLIT_GATE = 0.30              # pre-set split-half bar (same materiality, set before run)
BOOT = 2000                    # bootstrap resamples for the pooled-rho CI
SEED = 20260701                # fixed seed for the bootstrap
# gmli_3yr window: the trailing 3 seasons ending at the current pool season,
# so the monthly refresh slides forward with the leaderboards.
MULTI_YEAR_SEASONS = [CURRENT_SEASON - 2, CURRENT_SEASON - 1, CURRENT_SEASON]
TAG_MIN_SEASONS = 2            # "established" needs 2+ seasons ...
TAG_MIN_ENTRIES = 60           # ... and 60+ total relief entries


def _pearson(xs, ys):
    n = len(xs)
    if n < 4:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    vx = sum((x - mx) ** 2 for x in xs) ** 0.5
    vy = sum((y - my) ** 2 for y in ys) ** 0.5
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy)


def _r4(v):
    return None if v is None else round(v, 4)


# --------------------------------------------------------------------------- #
# season walks: full-season + split-half leverage from the cached wp feed
# --------------------------------------------------------------------------- #
def season_leverage(y: int, want_halves: bool = True):
    """One cached walk of season Y's final games -> (full, half1, half2, cov).
    Each of full/half1/half2 is the mlb_leverage._finalize dict keyed by MLBAM
    (gmli, appearances, ...). Start-games are dropped inside _fold_game, so
    everything here is RELIEF deployment. Best effort: a game whose feed fails
    is skipped and counted."""
    pks = mlb_leverage.season_game_pks(y)
    split = f"{y}-{SPLIT_DATE}"
    acc_full: dict = {}
    acc_h1: dict = {}
    acc_h2: dict = {}
    used = failed = 0
    for pk, gd in pks:
        try:
            plays = mlb_leverage.get_win_probability(pk, game_date=gd)
        except Exception:
            failed += 1
            continue
        mlb_leverage._fold_game(acc_full, plays)
        if want_halves and gd:
            mlb_leverage._fold_game(acc_h1 if gd <= split else acc_h2, plays)
        used += 1
    cov = {"games": used, "games_total": len(pks), "failed": failed}
    return (mlb_leverage._finalize(acc_full),
            mlb_leverage._finalize(acc_h1),
            mlb_leverage._finalize(acc_h2),
            cov)


def season_pool(y: int, leverage_full: dict) -> dict:
    """MLBAM -> Reliever for season Y's true-reliever pool (score_pool parity:
    is_true_reliever and not opener)."""
    rows = be.load_season_pitching(y)
    rels = be.build_relievers(rows, leverage_full)
    pool = [r for r in rels
            if rem_plus.is_true_reliever(r) and not rem_plus._is_opener(r)]
    return {r.mlbam: r for r in pool}


# --------------------------------------------------------------------------- #
# eval pieces
# --------------------------------------------------------------------------- #
def autocorrelation(pools: dict) -> dict:
    """Y->Y+1 gmLI pairs on the qualified pool, per season pair + pooled, with
    a seeded bootstrap CI on the pooled Spearman rho."""
    by_pair = {}
    pooled = []          # (gmli_y, gmli_y1) at the 100/60 convention
    pooled_sym = []      # symmetric 100/100 sensitivity
    for y in SEASONS:
        ny = y + 1
        if ny not in pools:
            continue
        cur, nxt = pools[y], pools[ny]
        pts, pts_sym = [], []
        for mid, a in cur.items():
            b = nxt.get(mid)
            if b is None or a.gmli is None or b.gmli is None:
                continue
            if a.tbf >= MIN_TBF_Y and b.tbf >= MIN_TBF_NEXT:
                pts.append((a.gmli, b.gmli))
            if a.tbf >= MIN_TBF_Y and b.tbf >= MIN_TBF_Y:
                pts_sym.append((a.gmli, b.gmli))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        by_pair[f"{y}->{ny}"] = {
            "n": len(pts),
            "spearman_rho": _r4(_spearman(xs, ys)),
            "pearson_r": _r4(_pearson(xs, ys)),
        }
        pooled.extend(pts)
        pooled_sym.extend(pts_sym)

    xs = [p[0] for p in pooled]
    ys = [p[1] for p in pooled]
    rho = _spearman(xs, ys)

    rng = random.Random(SEED)
    n = len(pooled)
    boots = []
    for _ in range(BOOT):
        samp = [rng.randrange(n) for _ in range(n)]
        r = _spearman([xs[i] for i in samp], [ys[i] for i in samp])
        if r is not None:
            boots.append(r)

    xs2 = [p[0] for p in pooled_sym]
    ys2 = [p[1] for p in pooled_sym]
    return {
        "by_pair": by_pair,
        "pooled": {
            "n": n,
            "spearman_rho": _r4(rho),
            "pearson_r": _r4(_pearson(xs, ys)),
            "bootstrap_ci": _ci(boots),
            "bootstrap": {"resamples": BOOT, "seed": SEED},
        },
        "sensitivity_symmetric_qualification": {
            "note": f"both years TBF >= {MIN_TBF_Y}",
            "n": len(pooled_sym),
            "spearman_rho": _r4(_spearman(xs2, ys2)),
        },
    }


def split_half(pools: dict, halves: dict) -> dict:
    """Within-season split-half gmLI stability on the qualified pool."""
    by_season = {}
    pooled = []  # (gmli_h1, gmli_h2, min_half_entries)
    for y in SEASONS:
        h1, h2 = halves[y]
        pts = []
        for mid, r in pools[y].items():
            if r.tbf < MIN_TBF_Y or r.gmli is None:
                continue
            a, b = h1.get(mid), h2.get(mid)
            if not a or not b or a["gmli"] is None or b["gmli"] is None:
                continue
            if a["appearances"] < SPLIT_MIN_ENTRIES or b["appearances"] < SPLIT_MIN_ENTRIES:
                continue
            pts.append((a["gmli"], b["gmli"], min(a["appearances"], b["appearances"])))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        by_season[str(y)] = {"n": len(pts), "spearman_rho": _r4(_spearman(xs, ys))}
        pooled.extend(pts)

    xs, ys = [p[0] for p in pooled], [p[1] for p in pooled]
    out = {
        "convention": (f"halves split at {SPLIT_DATE}; both halves need >= "
                       f"{SPLIT_MIN_ENTRIES} relief entries; pool = season-qualified "
                       f"(TBF >= {MIN_TBF_Y}) true relievers"),
        "by_season": by_season,
        "pooled": {"n": len(pooled), "spearman_rho": _r4(_spearman(xs, ys))},
        "by_min_half_entries": {},
    }
    for lo, hi in ((SPLIT_MIN_ENTRIES, 15), (15, 25), (25, 10_000)):
        sub = [(p[0], p[1]) for p in pooled if lo <= p[2] < hi]
        if len(sub) >= 10:
            out["by_min_half_entries"][f"{lo}-{hi if hi < 9999 else 'plus'}"] = {
                "n": len(sub),
                "spearman_rho": _r4(_spearman([s[0] for s in sub], [s[1] for s in sub])),
            }
    return out


def proposed_values(full_by_season: dict) -> dict:
    """The displayed metric for the CURRENT qualified pool: gmli_3yr (relief-
    entry-weighted mean gmLI over the three most recent seasons) + pool
    percentile + stability tag. Keyed by MLBAM string so bullpen_export can
    join it in one dict lookup."""
    bp = json.loads(BULLPEN_PATH.read_text(encoding="utf-8"))
    pool_rows = [r for r in (bp.get("relievers") or []) if r.get("qualified")]

    players = {}
    vals = []
    for row in pool_rows:
        mid = row.get("mlbam")
        num = den = 0.0
        seasons_used = 0
        for y in MULTI_YEAR_SEASONS:
            lev = (full_by_season.get(y) or {}).get(mid)
            if not lev or lev.get("gmli") is None or not lev.get("appearances"):
                continue
            num += lev["gmli"] * lev["appearances"]
            den += lev["appearances"]
            seasons_used += 1
        if not den:
            continue
        g3 = num / den
        entries = int(den)
        tag = ("established"
               if seasons_used >= TAG_MIN_SEASONS and entries >= TAG_MIN_ENTRIES
               else "provisional")
        players[str(mid)] = {
            "name": row.get("name"), "team": row.get("team"),
            "gmli_now": row.get("gmli"),
            "gmli_3yr": round(g3, 2),
            "seasons_used": seasons_used,
            "entries_total": entries,
            "tag": tag,
        }
        vals.append((str(mid), g3))

    # mean-rank percentile within the qualified pool (0-100, nearest int:
    # context metric, "+"-family rounding)
    n = len(vals)
    svals = sorted(v for _, v in vals)
    for mid, v in vals:
        lo = sum(1 for s in svals if s < v)
        eq = sum(1 for s in svals if s == v)
        rank_avg = lo + (eq + 1) / 2.0
        players[mid]["pct"] = int(round(100.0 * (rank_avg - 0.5) / n)) if n else None

    return {
        "season": CURRENT_SEASON,
        "metric": "gmli_3yr",
        "display_name": "Deployment gmLI (3yr)",
        "definition": (f"Relief-entry-weighted mean gmLI over {MULTI_YEAR_SEASONS} "
                       "(start games excluded from the fold). pct is the percentile "
                       "within the current qualified pool. tag is 'established' with "
                       f"{TAG_MIN_SEASONS}+ seasons and {TAG_MIN_ENTRIES}+ relief "
                       "entries, else 'provisional'."),
        "pool": (f"qualified relievers in data/bullpen_leaderboards.json "
                 f"(season {bp.get('season')}, as_of {bp.get('as_of')})"),
        "n_pool_qualified": len(pool_rows),
        "n_with_value": len(players),
        "never_in_rem_plus": ("deployment context only; by design this number is never "
                              "folded into the REM+ skill scale"),
        "players": players,
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def run(write: bool = True) -> dict:
    t0 = time.time()
    pools = {}
    halves = {}
    full_by_season = {}
    coverage = {}
    for y in SEASONS:
        full, h1, h2, cov = season_leverage(y, want_halves=True)
        full_by_season[y] = full
        halves[y] = (h1, h2)
        coverage[str(y)] = cov
        pools[y] = season_pool(y, full)
        nq = sum(1 for r in pools[y].values() if r.tbf >= MIN_TBF_Y and r.gmli is not None)
        print(f"  {y}: {cov['games']}/{cov['games_total']} games walked, "
              f"{len(pools[y])} true relievers, {nq} qualified w/ gmLI "
              f"({round(time.time() - t0, 1)}s)")

    # current season for proposed_values (full walk only; partial season is fine,
    # the display already carries the coverage note in bullpen_leaderboards.json)
    full_cur, _, _, cov_cur = season_leverage(CURRENT_SEASON, want_halves=False)
    full_by_season[CURRENT_SEASON] = full_cur
    coverage[str(CURRENT_SEASON)] = cov_cur
    print(f"  {CURRENT_SEASON}: {cov_cur['games']}/{cov_cur['games_total']} games walked "
          f"(current, proposed_values only)")

    ac = autocorrelation(pools)
    sh = split_half(pools, halves)
    pv = proposed_values(full_by_season)

    pooled_rho = ac["pooled"]["spearman_rho"]
    split_rho = sh["pooled"]["spearman_rho"]
    ac_pass = pooled_rho is not None and pooled_rho >= RHO_GATE
    sh_pass = split_rho is not None and split_rho >= SPLIT_GATE
    gate_pass = bool(ac_pass and sh_pass)

    pool_sizes = {str(y): {
        "true_relievers": len(pools[y]),
        "qualified_with_gmli": sum(1 for r in pools[y].values()
                                   if r.tbf >= MIN_TBF_Y and r.gmli is not None),
    } for y in SEASONS}

    payload = {
        "generated_at": date.today().isoformat(),
        "experiment": "X-D1",
        "model": "leverage_consistency (multi-year gmLI deployment stability)",
        "seed": SEED,
        "method": {
            "gmli": ("mean leverage index at the reliever's game-entry play, self-computed "
                     "from the StatsAPI winProbability feed (mlb_leverage); start games are "
                     "dropped from the fold, openers excluded from the pool"),
            "pool": ("bullpen_export.load_season_pitching rows -> rem_plus.is_true_reliever "
                     "and not _is_opener (score_pool parity)"),
            "qualification": (f"Y->Y+1 pairs: TBF >= {MIN_TBF_Y} in year Y and TBF >= "
                              f"{MIN_TBF_NEXT} in year Y+1, gmLI present both years "
                              "(rem_plus_backtest convention)"),
            "seasons": SEASONS,
            "season_pairs": [f"{y}->{y + 1}" for y in SEASONS if (y + 1) in pools],
            "excluded": "2020 (60-game COVID season), so no 2019->2020 or 2020->2021 pair",
            "pooling": ("season-pair samples pooled directly; gmLI is centered near 1.0 "
                        "every season by construction, so cross-season pooling does not "
                        "need re-centering"),
            "split_half": sh["convention"],
            "gate": (f"pre-registered: pooled Y->Y+1 Spearman rho >= {RHO_GATE}; split-half "
                     f"bar pre-set to pooled within-season rho >= {SPLIT_GATE} before the "
                     "run (the registered gate left it qualitative)"),
            "role": ("DEPLOYMENT CONTEXT metric; never folded into REM+ (two-number design "
                     "validated in data/rem_plus_eval.json)"),
        },
        "coverage": coverage,
        "pool_sizes": pool_sizes,
        "autocorrelation_gmli_y_to_y1": ac,
        "split_half_within_season": sh,
        "gate": {
            "pooled_rho_threshold": RHO_GATE,
            "split_half_threshold": SPLIT_GATE,
            "pooled_rho": pooled_rho,
            "pooled_rho_ci": ac["pooled"]["bootstrap_ci"],
            "split_half_pooled_rho": split_rho,
            "autocorrelation_pass": ac_pass,
            "split_half_pass": sh_pass,
            "pass": gate_pass,
            "verdict": (
                f"PASS: gmLI is a stable deployment trait (pooled Y->Y+1 rho {pooled_rho} "
                f">= {RHO_GATE}, split-half rho {split_rho} >= {SPLIT_GATE}); ship as a "
                "context column per the registered ship path"
                if gate_pass else
                f"FAIL: gate not met (pooled Y->Y+1 rho {pooled_rho} vs {RHO_GATE}, "
                f"split-half rho {split_rho} vs {SPLIT_GATE}); no ship, see loss_ledger"
            ),
        },
        "proposed_values": pv,
    }
    if not gate_pass:
        payload["loss_ledger"] = {
            "hypothesis": ("manager-assigned leverage (gmLI) is stable enough year over "
                           "year to display as a deployment-context metric"),
            "result": {"pooled_y_to_y1_rho": pooled_rho, "split_half_rho": split_rho,
                       "thresholds": {"autocorrelation": RHO_GATE, "split_half": SPLIT_GATE}},
            "reading": ("gmLI reshuffles too much (role churn, injuries, team changes) to "
                        "present as a persistent trait; keep the single-season gmLI column "
                        "as is and do not add a multi-year stability framing"),
            "do_not_retry_without": ("a role-conditioned design (e.g. same-team same-role "
                                     "subsample) or a longer weighting window justified by "
                                     "new evidence"),
        }

    print(json.dumps({"gate": payload["gate"],
                      "by_pair": {k: v["spearman_rho"] for k, v in ac["by_pair"].items()},
                      "split_by_season": {k: v["spearman_rho"] for k, v in sh["by_season"].items()},
                      "proposed_n": pv["n_with_value"]}, indent=1))
    if write:
        # Atomic write (tmp + replace), matching bullpen_export: a crash
        # mid-write must never leave malformed JSON for the export join.
        tmp = OUT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        tmp.replace(OUT_PATH)
        print(f"wrote {OUT_PATH.relative_to(ROOT)} in {round(time.time() - t0, 1)}s")
    return payload


if __name__ == "__main__":
    run(write="--no-write" not in sys.argv)

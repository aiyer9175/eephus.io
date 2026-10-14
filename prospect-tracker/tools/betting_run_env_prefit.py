"""betting_run_env_prefit: section 5k's pre-2026 fit, deterministic, reads no 2026 game.

docs/diamond-betting.md section 5k ("Run environment: trailing league scoring and a
calendar-month offset"). This fits the constants the 5k members price with, on the 2018,
2019 and 2021 to 2025 regular-season finals and on nothing else:

  k_14, k_30   5k-A's pass-throughs: pooled over the seven seasons, no intercept,
               weighted by team-games on D,
                   x(D) = R_w(D) - mu_s,  y(D) = L(D) - mu_s,
                   k_w = sum n_D x y / sum n_D x^2
  o(m)         5k-B's six calendar-bin offsets, normal-normal empirical Bayes toward
               zero by the method of moments:
                   A = max(0, mean_m [dbar(m)^2 - V(m)/7]),  o(m) = A / (A + V(m)/7) dbar(m)

and reports what the Fitted block carries: per-season slopes (descriptive), the
season-block bootstrap (1,000 resamples of the seven seasons, default_rng(20260911)), the
2023-2025 slope beside the pooled one (never substituted), every count and drop, and the
power figures (RMS_T, sigma_T; t* is evaluated at the read, once n_eval is fixed).

THE FINALS. betting_model.fetch_finals, one StatsAPI schedule request per season, stored
under .cache/betting/regular_finals/<season>.json (the same pull tools/intensity_fetch.py
made for the 5o and 7i lanes; the file is reused when present and fetched through that
tool's code when absent). Never data/.

THE CENSUS CHECK, before any slope. Each season's kept game_pk count is compared with the
B-CORPUS census entry and its game_pk list with the play corpus's own list (the game_pk
column alone, .cache/pbp_corpus). A difference that is not explained refuses the fit.

THE ROW RULES are betting_model.run_env_qualifying's, one definition with the 2026 lab:
dedupe game_pk, drop another season, drop innings missing or below 9, drop every RESUMED
game (a game_pk the schedule lists on two dates; a game it lists once is not resumed).

Usage (from prospect-tracker/):
  python tools/betting_run_env_prefit.py            # fit, write .cache/betting/run_env/prefit.json
  python tools/betting_run_env_prefit.py --print    # also print the RUN_ENV_PRE2026 literal
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import betting_model as bm  # noqa: E402

FINALS_DIR = ROOT / ".cache" / "betting" / "regular_finals"
OUT_DIR = ROOT / ".cache" / "betting" / "run_env"
CORPUS_DIR = ROOT / ".cache" / "pbp_corpus"


def load_season(season: str, *, finals_dir: Path | None = None, fetch: bool = True) -> dict:
    """The season's schedule-finals document ({rows, listed_more_than_once, ...})."""
    fdir = Path(finals_dir or FINALS_DIR)
    p = fdir / f"{season}.json"
    if not p.exists() and fetch:
        from tools import intensity_fetch as itf
        itf.fetch_regular_season(int(season), pacer=itf.Pacer(), finals_dir=fdir)
    doc = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("rows"), list):
        raise bm.RunEnvStop(f"prefit: {p} is not a finals document")
    return doc


def listings_from_doc(doc: dict) -> dict:
    """{game_pk: schedule listings} for every kept row: 1, or the number of listings
    listed_more_than_once records for it. A suspended game is listed on each day it was
    played and keeps its original official date on every listing, so the listing COUNT,
    not the set of official dates, is what says "listed on two schedule dates". Reads
    no runs field."""
    multi = {int(k): len(v) for k, v in (doc.get("listed_more_than_once") or {}).items()}
    out = {}
    for r in doc["rows"]:
        pk = int(r["game_pk"])
        out[pk] = multi.get(pk, 1)
    return out


def corpus_pks(season: str, corpus_dir: Path | None = None) -> set | None:
    p = Path(corpus_dir or CORPUS_DIR) / "plays" / str(season) / f"plays-{season}.parquet"
    if not p.exists():
        return None
    import pyarrow.parquet as pq
    col = pq.read_table(p, columns=["game_pk"]).column("game_pk").to_pylist()
    return {int(x) for x in col if x is not None}


def census(season: str, doc: dict, corpus: set | None) -> dict:
    """Game_pk lists alone: the kept count against the census entry, and the
    differences against the play corpus. `explained` is False only when a
    difference exists and nothing explains it."""
    pks = {int(r["game_pk"]) for r in doc["rows"]}
    out = {"season": season, "n_schedule_kept": len(pks),
           "census": bm.RUN_ENV_CENSUS.get(season),
           "equals_census": len(pks) == bm.RUN_ENV_CENSUS.get(season),
           "n_schedule_returned": doc.get("n_returned"),
           "schedule_drops": doc.get("drops") or {}}
    if corpus is None:
        out.update(n_corpus=None, only_in_schedule=None, only_in_corpus=None)
    else:
        out.update(n_corpus=len(corpus), only_in_schedule=sorted(pks - corpus),
                   only_in_corpus=sorted(corpus - pks))
    diff = (not out["equals_census"]) or bool(out.get("only_in_schedule")) \
        or bool(out.get("only_in_corpus"))
    out["difference"] = diff
    out["explained"] = not diff
    out["resolution"] = ("none needed: the schedule list equals the census count and "
                         "the play corpus game for game") if not diff else None
    return out


def _slope(points) -> float | None:
    sxy = sum(n * x * y for n, x, y in points)
    sxx = sum(n * x * x for n, x, _ in points)
    return sxy / sxx if sxx else None


def season_points(daily: dict, w: int) -> tuple[list, dict]:
    """[(n_D, x, y)] for one season and window, with its counts."""
    mu = bm.run_env_season_mean(daily)
    pts, n_floor = [], 0
    for d in sorted(daily):
        runs, games = daily[d]
        if not games:
            continue
        win = bm.run_env_window(daily, d, w)
        if win["value"] is None:
            n_floor += 1
            continue
        pts.append((2.0 * games, win["value"] - mu, runs / (2.0 * games) - mu))
    return pts, {"dates_with_final": sum(1 for c in daily.values() if c[1]),
                 "dates_used": len(pts), "dates_below_floor": n_floor}


def fit(seasons=None, *, finals_dir=None, corpus_dir=None, fetch: bool = True) -> dict:
    import numpy as np

    seasons = tuple(seasons or bm.RUN_ENV_PREFIT_SEASONS)
    per = {}
    census_rows = []
    for s in seasons:
        doc = load_season(s, finals_dir=finals_dir, fetch=fetch)
        cz = census(s, doc, corpus_pks(s, corpus_dir))
        census_rows.append(cz)
        if not cz["explained"]:
            raise bm.RunEnvStop(f"prefit: census difference for {s} is unexplained: {cz}")
        kept, drops = bm.run_env_qualifying(doc["rows"], s, listings=listings_from_doc(doc))
        per[s] = {"finals": kept, "drops": drops, "daily": bm.run_env_daily(kept)}

    out = {"seasons": list(seasons), "census": census_rows,
           "row_rules": {s: {"n_schedule_kept": len(load_season(s, finals_dir=finals_dir,
                                                                 fetch=False)["rows"]),
                             "n_qualifying": len(per[s]["finals"]), **per[s]["drops"]}
                         for s in seasons}}
    mus = {s: bm.run_env_season_mean(per[s]["daily"]) for s in seasons}

    # --- 5k-A ---------------------------------------------------------------
    arm_a = {}
    rng = np.random.default_rng(bm.RUN_ENV_BOOT_SEED)
    idxs = [rng.choice(len(seasons), size=len(seasons), replace=True)
            for _ in range(bm.RUN_ENV_BOOT_N)]
    for w in bm.RUN_ENV_WINDOWS:
        pts_by = {}
        counts = {}
        for s in seasons:
            pts_by[s], counts[s] = season_points(per[s]["daily"], w)
        pooled = _slope([p for s in seasons for p in pts_by[s]])
        recent = _slope([p for s in ("2023", "2024", "2025") if s in pts_by
                         for p in pts_by[s]])
        boots = []
        for ix in idxs:
            b = _slope([p for i in ix for p in pts_by[seasons[int(i)]]])
            if b is not None:
                boots.append(b)
        boots_a = np.asarray(boots, dtype=float)
        arm_a[str(w)] = {
            "k": pooled,
            "floor": bm.RUN_ENV_WINDOW_FLOORS[w],
            "per_season_slope": {s: _slope(pts_by[s]) for s in seasons},
            "slope_2023_2025": recent,
            "bootstrap": {"n": len(boots), "seed": bm.RUN_ENV_BOOT_SEED,
                          "p2_5": float(np.percentile(boots_a, 2.5)),
                          "p50": float(np.percentile(boots_a, 50)),
                          "p97_5": float(np.percentile(boots_a, 97.5)),
                          "mean": float(boots_a.mean()),
                          "share_at_or_below_0": float((boots_a <= 0).mean())},
            "counts": counts,
            "n_dates": sum(c["dates_used"] for c in counts.values()),
            "n_team_games": sum(p[0] for s in seasons for p in pts_by[s]),
            "null_by_construction": bool(pooled is None or pooled <= 0),
        }

    # --- 5k-B ---------------------------------------------------------------
    d_tab = {s: {} for s in seasons}
    for s in seasons:
        acc = {m: [0, 0] for m in bm.RUN_ENV_MONTH_BINS}
        for d, (runs, games) in per[s]["daily"].items():
            c = acc[bm.run_env_month_bin(d)]
            c[0] += runs
            c[1] += games
        for m, (runs, games) in acc.items():
            d_tab[s][m] = (runs / (2.0 * games) - mus[s]) if games else None
    k = len(seasons)
    dbar, V = {}, {}
    for m in bm.RUN_ENV_MONTH_BINS:
        vals = [d_tab[s][m] for s in seasons if d_tab[s][m] is not None]
        if len(vals) != k:
            raise bm.RunEnvStop(f"prefit: bin {m} is missing in some season")
        dbar[m] = sum(vals) / k
        V[m] = sum((v - dbar[m]) ** 2 for v in vals) / (k - 1)
    A = max(0.0, sum(dbar[m] ** 2 - V[m] / k for m in bm.RUN_ENV_MONTH_BINS)
            / len(bm.RUN_ENV_MONTH_BINS))
    offset = {m: (A / (A + V[m] / k) * dbar[m]) if (A + V[m] / k) > 0 else 0.0
              for m in bm.RUN_ENV_MONTH_BINS}
    arm_b = {"A": A, "dbar": dbar, "V": V, "offset": offset, "d_by_season": d_tab,
             "games_by_bin": {m: sum(g for s in seasons for d, (_, g) in per[s]["daily"].items()
                                     if bm.run_env_month_bin(d) == m)
                              for m in bm.RUN_ENV_MONTH_BINS},
             "null_by_construction": A <= 0}

    # --- power, on 2018-2025 only --------------------------------------------
    sq_tot, n_tot = 0.0, 0
    for s in seasons:
        for r in per[s]["finals"]:
            t = int(r["home_runs"]) + int(r["away_runs"])
            sq_tot += (t - 2.0 * mus[s]) ** 2
            n_tot += 1
    sigma_T = math.sqrt(sq_tot / n_tot)
    rms = {}
    for w in bm.RUN_ENV_WINDOWS:
        kw = arm_a[str(w)]["k"]
        sq, n = 0.0, 0
        for s in seasons:
            vals = []
            for r in per[s]["finals"]:
                win = bm.run_env_window(per[s]["daily"], r["date"], w)
                if win["value"] is not None:
                    vals.append(2.0 * kw * win["value"])
            if not vals:
                continue
            m0 = sum(vals) / len(vals)
            sq += sum((v - m0) ** 2 for v in vals)
            n += len(vals)
        rms[f"5k-A{w}"] = {"RMS_T": math.sqrt(sq / n) if n else None, "n_games": n}
    sq, n = 0.0, 0
    for s in seasons:
        vals = [2.0 * offset[bm.run_env_month_bin(r["date"])] for r in per[s]["finals"]]
        m0 = sum(vals) / len(vals)
        sq += sum((v - m0) ** 2 for v in vals)
        n += len(vals)
    rms["5k-B"] = {"RMS_T": math.sqrt(sq / n), "n_games": n}
    power = {"sigma_T": sigma_T, "n_games": n_tot, "members": rms,
             "t_star_formula": "sqrt(n_eval) x RMS_T / (sigma_T x sqrt(2 pi)), "
                               "evaluated at each split's n_eval at the read"}

    out.update({"mu_s": mus, "arm_a": arm_a, "arm_b": arm_b, "power": power})
    out["literal"] = literal(out)
    return out


def literal(fitted: dict) -> dict:
    """The RUN_ENV_PRE2026 literal, rounded to 8 places, with a digest of itself."""
    lit = {
        "seasons": list(fitted["seasons"]),
        "k": {w: round(fitted["arm_a"][w]["k"], 8) for w in fitted["arm_a"]},
        "month": {"A": round(fitted["arm_b"]["A"], 8),
                  "offset": {m: round(v, 8) for m, v in fitted["arm_b"]["offset"].items()}},
        "power": {"sigma_T": round(fitted["power"]["sigma_T"], 6),
                  "RMS_T": {m: (round(v["RMS_T"], 6) if v["RMS_T"] is not None else None)
                            for m, v in fitted["power"]["members"].items()}},
    }
    lit["digest"] = hashlib.sha256(json.dumps(lit, sort_keys=True).encode()).hexdigest()[:16]
    return lit


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--print", action="store_true", help="print the literal")
    ap.add_argument("--out", default=str(OUT_DIR / "prefit.json"))
    args = ap.parse_args(argv)
    res = fit()
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(res, indent=1, sort_keys=True), encoding="utf-8")
    print(f"prefit: wrote {outp}")
    if args.print:
        print(json.dumps(res["literal"], indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

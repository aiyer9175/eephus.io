# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""AAA Stuff+ - the platform's first IN-HOUSE pitch-quality model for
prospects (the tjStuff+ gap-filler the registry has carried since
Phase 4b: external Stuff+ can't score pre-debut pitchers; this can).

  DATA       Savant minors per-pitch detail (statcast-search-minors,
             pitchers_lookup, full param skeleton + minors=true), AAA
             2023+. Each pitch carries kinematics AND delta_run_exp -
             everything a stuff model needs, verified 2026-06-11.
  FEATURES   physics only (no pitch-type identity, no results):
             release_speed, spin, extension, pfx_x (arm-side signed),
             pfx_z, release_pos_x (signed), release_pos_z, arm_angle,
             velo_delta_vs_primary (the off-speed separation signal).
  LABEL      delta_run_exp per pitch (negative = good for the pitcher).
  MODEL      LightGBM regressor, deterministic; trained on season-pairs
             and validated SEASON-OUT (train 2023+2024 -> validate 2025
             OOS) before the shipping fit uses all complete seasons.
  SCORE      pitcher-season mean predicted RV, reliability-shrunk toward
             the pool mean below 300 pitches, scaled to 100 + 10z
             (higher = better stuff; z vs the qualified AAA pool).
  VALIDATION data/stuff_plus_aaa_eval.json: (a) season-out pitch-level
             RV correlation; (b) the forward gate - graduates' final-AAA
             Stuff+ vs first-MLB ERA/K% (the arkmetric_forward_eval
             pattern). Published whatever it says. The tjStuff+
             agreement check is DEFERRED until per-season MLB Stf+ rows
             accumulate (began persisting 2026; documented in registry).

Sidecar: data/stuff_plus_aaa.json {mlbam: {stuff_plus, n_pitches,
season}}. Surfaces: PROSPX pitcher cards (an in-house pill beside the
external Stf+), MLB player pages for recent graduates.

Run: python stuff_plus_aaa.py --fetch    (per-pitcher cache, hours cold)
     python stuff_plus_aaa.py --train    (season-out eval + shipping fit)
     python stuff_plus_aaa.py --score    (write the sidecar + eval)
     python stuff_plus_aaa.py --all
"""

from __future__ import annotations

import csv
import io
import json
import logging
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "stuff_plus_aaa.json"
EVAL_PATH = DATA_DIR / "stuff_plus_aaa_eval.json"
MODEL_PATH = ROOT / "model" / "stuff_plus_aaa.joblib"
CACHE_DIR = ROOT / ".cache" / "aaa_pitches"

SEASONS = (2023, 2024, 2025, 2026)
TRAIN_SEASONS = (2023, 2024)
VALID_SEASON = 2025
MIN_POOL_PITCHES = 300
SHRINK_K = 300
THROTTLE_S = 1.2
SEED = 20260611
CURRENT_TTL_DAYS = 14   # closed seasons immutable; current season refreshes

SEARCH = ("https://baseballsavant.mlb.com/statcast-search-minors/csv?all=true"
          "&hfPT=&hfAB=&hfBBT=&hfPR=&hfZ=&stadium=&hfBBL=&hfNewZones="
          "&hfGT=R%7C&hfC=&hfSea={season}%7C&hfSit=&player_type=pitcher"
          "&hfOuts=&opponent=&pitcher_throws=&batter_stands=&hfSA="
          "&game_date_gt=&game_date_lt=&hfInfield=&team=&position="
          "&hfOutfield=&hfRO=&home_road=&hfFlag=&hfPull=&metric_1=&hfInn="
          "&min_pitches=0&min_results=0&group_by=&sort_col=pitches"
          "&player_event_sort=api_p_release_speed&sort_order=desc&min_pas=0"
          "&type=details&minors=true&pitchers_lookup%5B%5D={mlbam}")

_KEEP = ("pitch_type", "release_speed", "release_spin_rate",
         "release_extension", "pfx_x", "pfx_z", "release_pos_x",
         "release_pos_z", "arm_angle", "p_throws", "delta_run_exp")
_last = 0.0


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _throttle():
    global _last
    dt = time.time() - _last
    if dt < THROTTLE_S:
        time.sleep(THROTTLE_S - dt)
    _last = time.time()


def fetch_pitcher_season(mlbam: int, season: int, fetch: bool = True) -> Path | None:
    """Cached per-(pitcher, season) AAA pitch CSV (lean columns)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{mlbam}_{season}.csv"
    if path.exists():
        fresh = (season < date.today().year
                 or time.time() - path.stat().st_mtime < CURRENT_TTL_DAYS * 86400)
        if fresh or not fetch:
            return path
    elif not fetch:
        return None
    _throttle()
    url = SEARCH.format(season=season, mlbam=mlbam)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            text = r.read().decode("utf-8-sig", "replace")
    except Exception as e:                                    # noqa: BLE001
        log.warning("aaa pitch fetch failed %s/%s: %s", mlbam, season, e)
        return path if path.exists() else None    # stale beats nothing
    rows = list(csv.DictReader(io.StringIO(text)))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_KEEP)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in _KEEP})
    path.write_text(buf.getvalue(), encoding="utf-8")
    return path


def pool_mlbams(season: int) -> list[int]:
    """Qualified AAA pitchers that season (the cached Savant aggregate +
    AAA-roster restriction used by the SC+ eval)."""
    import arkmetric_forward_eval as af
    rows = af.savant_rows(season, "pitcher")
    aaa = af._aaa_mlbams(season)
    out = []
    for r in rows:
        mid = _f(r.get("player_id"))
        if mid and int(mid) in aaa and (_f(r.get("pa")) or 0) >= 50:
            out.append(int(mid))
    return sorted(set(out))


def fetch_all(seasons=SEASONS) -> int:
    n = 0
    for season in seasons:
        mids = pool_mlbams(season)
        log.info("aaa stuff pool %d: %d pitchers", season, len(mids))
        for mid in mids:
            if fetch_pitcher_season(mid, season) is not None:
                n += 1
    return n


def _featurize(r: dict, primary_velo: float | None):
    velo = _f(r.get("release_speed"))
    if velo is None:
        return None
    lab = _f(r.get("delta_run_exp"))
    if lab is None:
        return None
    throws_r = 1.0 if (r.get("p_throws") or "R") == "R" else 0.0
    sign = 1.0 if throws_r else -1.0          # arm-side normalization
    pfx_x = _f(r.get("pfx_x"))
    rpx = _f(r.get("release_pos_x"))
    return ([velo,
             _f(r.get("release_spin_rate")) or 0.0,
             _f(r.get("release_extension")) or 6.0,
             (pfx_x or 0.0) * sign,
             _f(r.get("pfx_z")) or 0.0,
             (rpx or 0.0) * sign,
             _f(r.get("release_pos_z")) or 5.5,
             _f(r.get("arm_angle")) or 30.0,
             (primary_velo - velo) if primary_velo is not None else 0.0,
             throws_r],
            lab)


FEATURES = ["velo", "spin", "extension", "pfx_x_arm", "pfx_z",
            "release_x_arm", "release_z", "arm_angle",
            "velo_delta_vs_primary", "throws_r"]


def _load_season(mlbam: int, season: int):
    path = CACHE_DIR / f"{mlbam}_{season}.csv"
    if not path.exists():
        return [], []
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
    velos = [v for v in (_f(r.get("release_speed")) for r in rows) if v is not None]
    primary = max(velos) if velos else None    # proxy: top velo = primary FB
    X, y = [], []
    for r in rows:
        fx = _featurize(r, primary)
        if fx is not None:
            X.append(fx[0])
            y.append(fx[1])
    return X, y


def train(persist: bool = True) -> dict:
    import numpy as np
    from lightgbm import LGBMRegressor
    Xtr, ytr, Xva, yva = [], [], [], []
    for season in TRAIN_SEASONS + (VALID_SEASON,):
        for path in CACHE_DIR.glob(f"*_{season}.csv"):
            mid = int(path.stem.split("_")[0])
            X, y = _load_season(mid, season)
            if season in TRAIN_SEASONS:
                Xtr.extend(X); ytr.extend(y)
            else:
                Xva.extend(X); yva.extend(y)
    Xtr, ytr = np.asarray(Xtr), np.asarray(ytr)
    Xva, yva = np.asarray(Xva), np.asarray(yva)
    log.info("train pitches %d | valid pitches %d", len(ytr), len(yva))
    params = dict(n_estimators=500, learning_rate=0.05, num_leaves=63,
                  min_child_samples=200, subsample=0.9, subsample_freq=1,
                  colsample_bytree=0.9, reg_lambda=2.0,
                  random_state=SEED, deterministic=True,
                  force_row_wise=True, n_jobs=4, verbose=-1)
    m = LGBMRegressor(**params)
    m.fit(Xtr, ytr)
    r = None
    if len(yva) > 100:
        r = float(np.corrcoef(m.predict(Xva), yva)[0, 1])
    # pitcher-level season-out check: mean predicted RV vs mean actual RV
    per = {}
    for path in CACHE_DIR.glob(f"*_{VALID_SEASON}.csv"):
        mid = int(path.stem.split("_")[0])
        X, y = _load_season(mid, VALID_SEASON)
        if len(y) >= MIN_POOL_PITCHES:
            per[mid] = (float(np.mean(m.predict(np.asarray(X)))),
                        float(np.mean(y)), len(y))
    pl_r = None
    if len(per) >= 20:
        a = [v[0] for v in per.values()]
        b = [v[1] for v in per.values()]
        pl_r = float(np.corrcoef(a, b)[0, 1])
    meta = {"trained_at": date.today().isoformat(),
            "train_seasons": list(TRAIN_SEASONS), "valid_season": VALID_SEASON,
            "n_train_pitches": int(len(ytr)), "n_valid_pitches": int(len(yva)),
            "pitch_level_r_oos": round(r, 4) if r is not None else None,
            "pitcher_level_r_oos": round(pl_r, 4) if pl_r is not None else None,
            "n_valid_pitchers": len(per), "features": FEATURES,
            "params": params}
    if persist:
        import joblib
        # shipping fit: all complete seasons (incl. the validation year)
        Xall = np.concatenate([Xtr, Xva]) if len(yva) else Xtr
        yall = np.concatenate([ytr, yva]) if len(yva) else ytr
        m_final = LGBMRegressor(**params)
        m_final.fit(Xall, yall)
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": m_final, "meta": meta}, MODEL_PATH, compress=3)
        log.info("saved %s", MODEL_PATH)
    return meta


def score(persist: bool = True) -> dict:
    import joblib
    import numpy as np
    bundle = joblib.load(MODEL_PATH)
    m = bundle["model"]
    # pool stats from the most recent COMPLETE season; current season
    # scores ride the same scale (vs last complete pool - documented)
    by_pitcher: dict[int, dict] = {}
    pool_rvs = []
    for season in SEASONS:
        for path in CACHE_DIR.glob(f"*_{season}.csv"):
            mid = int(path.stem.split("_")[0])
            X, y = _load_season(mid, season)
            if len(X) < 50:
                continue
            rv = float(np.mean(m.predict(np.asarray(X))))
            cur = by_pitcher.get(mid)
            if cur is None or season > cur["season"]:
                by_pitcher[mid] = {"rv": rv, "n": len(X), "season": season}
            if season == VALID_SEASON and len(X) >= MIN_POOL_PITCHES:
                pool_rvs.append(rv)
    if not pool_rvs:
        raise RuntimeError("no qualified pool season cached - run --fetch first")
    mu = float(np.mean(pool_rvs))
    sd = float(np.std(pool_rvs)) or 1.0
    players = {}
    for mid, r in by_pitcher.items():
        shrunk = (r["rv"] * r["n"] + mu * SHRINK_K) / (r["n"] + SHRINK_K)
        z = (mu - shrunk) / sd                    # lower RV = better stuff
        players[str(mid)] = {"stuff_plus": round(100 + 10 * z, 1),
                             "n_pitches": r["n"], "season": r["season"]}
    payload = {"generated_at": date.today().isoformat(),
               "model": "stuff_plus_aaa v1 (in-house LightGBM on AAA "
                        "per-pitch kinematics -> delta_run_exp)",
               "pool": f"AAA {VALID_SEASON} qualified ({len(pool_rvs)}), "
                       f"shrink k={SHRINK_K}",
               "n_scored": len(players), "players": players}
    if persist and players:
        OUT_PATH.write_text(json.dumps(payload, separators=(",", ":")),
                            encoding="utf-8")
        log.info("wrote %s (%d pitchers)", OUT_PATH, len(players))
    return payload


def refresh() -> dict:
    """run_monthly hook: incremental current-season fetch (closed seasons
    immutable in cache, current season on the TTL) + re-score + restamp
    the forward eval. Never retrains - the shipping fit is hand-run with
    its season-out eval."""
    if not MODEL_PATH.exists():
        log.info("aaa stuff+: no model artifact yet - skipping refresh")
        return {}
    fetch_all((date.today().year,))
    payload = score()
    forward_eval()
    return payload


def forward_eval(persist: bool = True) -> dict:
    """The honest gate: graduates' final-AAA Stuff+ vs first-MLB
    outcomes + agreement with external tjStuff+ where both exist."""
    import numpy as np
    import milb_history as mh
    sp = json.loads(OUT_PATH.read_text(encoding="utf-8"))["players"]
    debuts = json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8"))
    pairs_era, pairs_k = [], []
    for d in debuts:
        mid = d.get("mlbam_id")
        dd = d.get("debut_date") or ""
        if not mid or not dd[:4].isdigit():
            continue
        y = int(dd[:4])
        if y < 2024:
            continue
        row = sp.get(str(mid))
        if not row or row["season"] >= y:          # strictly pre-debut
            continue
        mlb = [r for r in (mh.player_index(y, "pitching").get(int(mid)) or [])
               if r.get("level") == "MLB"]
        if not mlb:
            continue
        r = mlb[0]
        era, bf = (float(r["era"]) if r.get("era") else None,
                   float(r["bf"]) if r.get("bf") else 0)
        so = float(r["so"]) if r.get("so") else None
        if era is not None and bf >= 100:
            pairs_era.append((row["stuff_plus"], -era))
            if so is not None:
                pairs_k.append((row["stuff_plus"], so / bf))

    def _r(pairs):
        if len(pairs) < 8:
            return None
        a = np.array([p for p, _ in pairs])
        b = np.array([q for _, q in pairs])
        return round(float(np.corrcoef(a, b)[0, 1]), 4)

    import joblib
    meta = joblib.load(MODEL_PATH)["meta"]
    out = {"generated_at": date.today().isoformat(),
           "season_out_validation": {
               "pitch_level_r": meta["pitch_level_r_oos"],
               "pitcher_level_r": meta["pitcher_level_r_oos"],
               "n_valid_pitchers": meta["n_valid_pitchers"]},
           "forward_gate": {
               "n_era": len(pairs_era), "r_vs_mlb_era_inv": _r(pairs_era),
               "n_k": len(pairs_k), "r_vs_mlb_kpct": _r(pairs_k)},
           "conventions": {
               "model": "physics-only features, label = delta_run_exp",
               "cohort": "graduates 2024+ with a strictly pre-debut AAA "
                         "Stuff+ season and >=100 MLB BF in the debut year",
               "scale": "100 + 10z vs the qualified AAA pool, shrink k=300"}}
    if persist:
        EVAL_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s", EVAL_PATH)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    do_all = "--all" in sys.argv
    if do_all or "--fetch" in sys.argv:
        print("fetched:", fetch_all())
    if do_all or "--train" in sys.argv:
        print(json.dumps(train(), default=str)[:400])
    if do_all or "--score" in sys.argv:
        print("scored:", score()["n_scored"])
        print(json.dumps(forward_eval(), indent=1))

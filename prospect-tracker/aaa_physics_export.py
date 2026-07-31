# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""AAA pitcher physics sidecar: data/aaa_physics.json (Phase 3a, NO GATE).

Registration pointer: docs/efv-2026-07-24/GATES.md, section W-SCREEN
(this sidecar is the descriptive Phase-3a companion; it feeds NO served
model number - display/context data only, plus the W-SCREEN lab's
feature source).

Source: the existing .cache/aaa_pitches per-pitcher-season CSVs
(Savant statcast-search-minors detail, fetched and maintained by
stuff_plus_aaa.py; seasons split per file year suffix, 2023-2026;
2026 is the in-progress season and is flagged partial).

Per pitcher-season (>= 50 usable pitches, the stuff_plus_aaa score()
floor) and per pitch type (>= 10 pitches for a by_type row):

  velo       mean release_speed (mph)
  ivb        mean pfx_z * 12 (inches, induced vertical break convention
             as stored by Savant pfx_z)
  hb_abs     mean |pfx_x| * 12 (inches, unsigned horizontal break -
             handedness-neutral)
  spin       mean release_spin_rate (rpm)
  ext        mean release_extension (ft)
  rel_ht     mean release_pos_z (ft)
  arm_angle  mean arm_angle (deg)
  usage      per-type pitch share over TYPED pitches (by_type only)
  n_pitches  rows with a parseable release_speed

Pitcher-season extras:
  mix_entropy   Shannon entropy (bits, log2) over usage shares of ALL
                typed pitches (not just by_type-qualified types)
  stuff_spread  population SD of per-type aStuff+ across types with
                >= 10 pitches (needs >= 2 qualifying types, else null)
  velo_adj_ivb  pitcher-season ivb residual on velo: ivb - (b0 + b1*velo),
                pooled OLS fit over qualified arms (n_pitches >= 100,
                complete seasons 2023-2025); coefficients in meta
  astuff_pool   per-season pooled aStuff+ scored with the SHIPPED
                model/stuff_plus_aaa.joblib bundle under score()'s exact
                conventions (mu/sd from the qualified AAA 2025 pool,
                shrink k=300, 100+10z scale). For each pitcher's selected
                season this reproduces data/stuff_plus_aaa.json (the
                agreement check is recorded in meta). Per-type astuff
                rides inside by_type on the same scale.

All means are over rows where the field parses (no imputation - this is
descriptive display data, unlike the model featurizer which imputes).

Compare-before-write (the statcast_alevel_export.py idiom).

Run: python aaa_physics_export.py
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "aaa_physics.json"
CACHE_DIR = ROOT / ".cache" / "aaa_pitches"
STUFF_JSON = DATA_DIR / "stuff_plus_aaa.json"

SEASONS = (2023, 2024, 2025, 2026)
COMPLETE_SEASONS = (2023, 2024, 2025)   # velo_adj_ivb fit pool
CURRENT_PARTIAL = 2026
MIN_ROW_PITCHES = 50      # pitcher-season inclusion (stuff_plus_aaa score floor)
MIN_TYPE_PITCHES = 10     # by_type row floor
MIN_FIT_PITCHES = 100     # velo_adj_ivb pooled-fit qualification


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return (sum(vals) / len(vals)) if vals else None


def _rnd(v, nd):
    return round(v, nd) if v is not None else None


def _parse_season(path: Path) -> dict | None:
    """Physics aggregates for one cached pitcher-season CSV (no model)."""
    try:
        rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
    except OSError:
        return None
    acc = {"velo": [], "ivb": [], "hb_abs": [], "spin": [], "ext": [],
           "rel_ht": [], "arm_angle": []}
    per_type: dict[str, dict[str, list]] = {}
    n = 0
    for r in rows:
        velo = _f(r.get("release_speed"))
        if velo is None:
            continue
        n += 1
        pfx_x = _f(r.get("pfx_x"))
        pfx_z = _f(r.get("pfx_z"))
        vals = {"velo": velo,
                "ivb": pfx_z * 12.0 if pfx_z is not None else None,
                "hb_abs": abs(pfx_x) * 12.0 if pfx_x is not None else None,
                "spin": _f(r.get("release_spin_rate")),
                "ext": _f(r.get("release_extension")),
                "rel_ht": _f(r.get("release_pos_z")),
                "arm_angle": _f(r.get("arm_angle"))}
        for k, v in vals.items():
            if v is not None:
                acc[k].append(v)
        pt = (r.get("pitch_type") or "").strip()
        if pt:
            tacc = per_type.setdefault(pt, {k: [] for k in acc})
            for k, v in vals.items():
                if v is not None:
                    tacc[k].append(v)
    if n < MIN_ROW_PITCHES:
        return None
    typed_n = {pt: len(t["velo"]) for pt, t in per_type.items()}
    total_typed = sum(typed_n.values())
    # Shannon entropy in bits over ALL typed usage shares
    ent = None
    if total_typed:
        ent = -sum((c / total_typed) * math.log2(c / total_typed)
                   for c in typed_n.values() if c)
    by_type = {}
    for pt, t in sorted(per_type.items()):
        nt = typed_n[pt]
        if nt < MIN_TYPE_PITCHES:
            continue
        by_type[pt] = {"velo": _rnd(_mean(t["velo"]), 1),
                       "ivb": _rnd(_mean(t["ivb"]), 1),
                       "hb_abs": _rnd(_mean(t["hb_abs"]), 1),
                       "spin": _rnd(_mean(t["spin"]), 0),
                       "ext": _rnd(_mean(t["ext"]), 2),
                       "rel_ht": _rnd(_mean(t["rel_ht"]), 2),
                       "arm_angle": _rnd(_mean(t["arm_angle"]), 1),
                       "usage": round(nt / total_typed, 3),
                       "n_pitches": nt}
    return {"n_pitches": n,
            "velo": _rnd(_mean(acc["velo"]), 1),
            "ivb": _rnd(_mean(acc["ivb"]), 1),
            "hb_abs": _rnd(_mean(acc["hb_abs"]), 1),
            "spin": _rnd(_mean(acc["spin"]), 0),
            "ext": _rnd(_mean(acc["ext"]), 2),
            "rel_ht": _rnd(_mean(acc["rel_ht"]), 2),
            "arm_angle": _rnd(_mean(acc["arm_angle"]), 1),
            "mix_entropy": _rnd(ent, 3),
            "by_type": by_type}


def _score_astuff():
    """{(mlbam, season): (pooled_stuff, {pitch_type: stuff})} via the shipped
    stuff_plus_aaa model bundle under score()'s exact conventions. Read-only
    reuse of that module's loaders; nothing in it is modified."""
    import joblib
    import numpy as np
    import stuff_plus_aaa as spa
    bundle = joblib.load(spa.MODEL_PATH)
    m = bundle["model"]
    rv_by = {}          # (mid, season) -> (rv, n, {pt: (rv_t, n_t)})
    pool_rvs = []
    for season in SEASONS:
        for path in CACHE_DIR.glob(f"*_{season}.csv"):
            mid = int(path.stem.split("_")[0])
            X, y, types = spa._load_season_typed(mid, season)
            if len(X) < MIN_ROW_PITCHES:
                continue
            preds = m.predict(np.asarray(X))
            rv = float(np.mean(preds))
            tacc: dict[str, list] = {}
            for p, pt in zip(preds, types):
                if pt:
                    a = tacc.setdefault(pt, [0.0, 0])
                    a[0] += float(p)
                    a[1] += 1
            rv_by[(mid, season)] = (rv, len(X),
                                    {pt: (s / c, c) for pt, (s, c) in tacc.items()})
            if season == spa.VALID_SEASON and len(X) >= spa.MIN_POOL_PITCHES:
                pool_rvs.append(rv)
    mu = float(np.mean(pool_rvs))
    sd = float(np.std(pool_rvs)) or 1.0
    k = spa.SHRINK_K
    out = {}
    for (mid, season), (rv, n, tmap) in rv_by.items():
        shrunk = (rv * n + mu * k) / (n + k)
        pooled = 100 + 10 * (mu - shrunk) / sd
        by_type = {}
        for pt, (rv_t, n_t) in tmap.items():
            shrunk_t = (rv_t * n_t + mu * k) / (n_t + k)
            by_type[pt] = 100 + 10 * (mu - shrunk_t) / sd
        out[(mid, season)] = (pooled, by_type)
    return out, mu, sd, len(pool_rvs)


def run(persist: bool = True) -> dict:
    # pass 1: physics aggregates per pitcher-season
    blocks: dict[int, dict[int, dict]] = {}
    for season in SEASONS:
        for path in sorted(CACHE_DIR.glob(f"*_{season}.csv")):
            mid = int(path.stem.split("_")[0])
            b = _parse_season(path)
            if b is not None:
                blocks.setdefault(mid, {})[season] = b

    # pass 2: per-season aStuff+ (pooled + per-type) from the shipped model
    astuff, mu, sd, pool_n = _score_astuff()
    for mid, seasons in blocks.items():
        for season, b in seasons.items():
            got = astuff.get((mid, season))
            if not got:
                b["astuff_pool"] = None
                b["stuff_spread"] = None
                continue
            pooled, by_type_stuff = got
            b["astuff_pool"] = round(pooled, 1)
            qual = [round(v, 1) for pt, v in by_type_stuff.items()
                    if (b["by_type"].get(pt) or {}).get("n_pitches", 0)
                    >= MIN_TYPE_PITCHES]
            for pt, row in b["by_type"].items():
                if pt in by_type_stuff:
                    row["astuff"] = round(by_type_stuff[pt], 1)
            if len(qual) >= 2:
                m_ = sum(qual) / len(qual)
                b["stuff_spread"] = round(
                    (sum((v - m_) ** 2 for v in qual) / len(qual)) ** 0.5, 1)
            else:
                b["stuff_spread"] = None

    # pass 3: velo_adj_ivb - pooled OLS ivb ~ velo over qualified arms,
    # complete seasons only; residual applied to every pitcher-season
    xs, ys = [], []
    for mid, seasons in blocks.items():
        for season, b in seasons.items():
            if (season in COMPLETE_SEASONS and b["n_pitches"] >= MIN_FIT_PITCHES
                    and b["velo"] is not None and b["ivb"] is not None):
                xs.append(b["velo"])
                ys.append(b["ivb"])
    slope = intercept = None
    if len(xs) >= 30:
        n = len(xs)
        mx = sum(xs) / n
        my = sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        slope = sxy / sxx if sxx else 0.0
        intercept = my - slope * mx
    for mid, seasons in blocks.items():
        for season, b in seasons.items():
            if (slope is not None and b["velo"] is not None
                    and b["ivb"] is not None):
                b["velo_adj_ivb"] = round(
                    b["ivb"] - (intercept + slope * b["velo"]), 1)
            else:
                b["velo_adj_ivb"] = None

    # served-json agreement check (each pitcher's selected season)
    agree_n = 0
    max_diff = 0.0
    try:
        served = json.loads(STUFF_JSON.read_text(encoding="utf-8"))["players"]
    except (OSError, KeyError, json.JSONDecodeError):
        served = {}
    for smid, row in served.items():
        got = astuff.get((int(smid), int(row.get("season") or 0)))
        if got and row.get("stuff_plus") is not None:
            agree_n += 1
            max_diff = max(max_diff, abs(round(got[0], 1) - row["stuff_plus"]))

    players = {str(mid): {str(season): seasons[season]
                          for season in sorted(seasons)}
               for mid, seasons in sorted(blocks.items())}
    n_type_rows = sum(len(b["by_type"])
                      for s in blocks.values() for b in s.values())
    out = {
        "generated_at": date.today().isoformat(),
        "registration": "docs/efv-2026-07-24/GATES.md W-SCREEN (Phase 3a "
                        "descriptive sidecar; display/context only, no "
                        "served model number)",
        "source": ".cache/aaa_pitches per-pitcher-season CSVs (Savant "
                  "statcast-search-minors, maintained by stuff_plus_aaa.py)",
        "meta": {
            "units": {"velo": "mph", "ivb": "in (pfx_z*12)",
                      "hb_abs": "in (|pfx_x|*12)", "spin": "rpm",
                      "ext": "ft", "rel_ht": "ft (release_pos_z)",
                      "arm_angle": "deg", "mix_entropy": "bits (log2)",
                      "usage": "share of typed pitches"},
            "floors": {"pitcher_season": MIN_ROW_PITCHES,
                       "by_type_row": MIN_TYPE_PITCHES,
                       "velo_adj_ivb_fit": MIN_FIT_PITCHES},
            "velo_adj_ivb_fit": {
                "intercept": round(intercept, 4) if intercept is not None else None,
                "slope": round(slope, 4) if slope is not None else None,
                "n_pitcher_seasons": len(xs),
                "pool": "n_pitches >= 100, complete seasons 2023-2025"},
            "astuff_scale": {
                "convention": "stuff_plus_aaa score(): 100+10z vs qualified "
                              "AAA 2025 pool, shrink k=300 (pooled and "
                              "per-type), shipped model bundle",
                "pool_mu_rv": round(mu, 6), "pool_sd_rv": round(sd, 6),
                "pool_n": pool_n},
            "served_json_agreement": {
                "checked": agree_n, "max_abs_diff": round(max_diff, 2),
                "note": "each pitcher's data/stuff_plus_aaa.json selected "
                        "season vs this exporter's same-season pooled score"},
            "current_season_partial": CURRENT_PARTIAL,
            "n_pitchers": len(players),
            "n_pitcher_seasons": sum(len(s) for s in blocks.values()),
            "n_type_rows": n_type_rows,
        },
        "players": players,
    }
    if persist:
        text = json.dumps(out, separators=(",", ":")) + "\n"
        if not OUT_PATH.exists() or OUT_PATH.read_text(encoding="utf-8") != text:
            OUT_PATH.write_text(text, encoding="utf-8")
            log.info("wrote %s (%d pitchers)", OUT_PATH, len(players))
        else:
            log.info("%s unchanged (%d pitchers)", OUT_PATH, len(players))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    m = rep["meta"]
    print(json.dumps({
        "n_pitchers": m["n_pitchers"],
        "n_pitcher_seasons": m["n_pitcher_seasons"],
        "n_type_rows": m["n_type_rows"],
        "velo_adj_ivb_fit": m["velo_adj_ivb_fit"],
        "served_json_agreement": m["served_json_agreement"],
    }, indent=1))

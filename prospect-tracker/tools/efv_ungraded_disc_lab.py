# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""W-DISC gate lab (pre-registered: docs/efv-2026-07-24/GATES.md, section
"W-DISC (Phase 2b): swing-decision components -> xfv_ungraded ONLY").

Swing-decision components from OUR cached A/CPX/AAA game feeds (2023+, call
codes) for the UNGRADED provisional model (efv_ungraded.py) ONLY. The
flagship matrix lane stays closed. WDISC-SENTINEL-20260724.

EVERYTHING BELOW IS FROZEN IN THIS HEADER BEFORE ANY FEATURE COMPUTATION RAN
(file written 2026-07-24, prior to the first `extract` invocation; the only
pre-freeze data contact was availability recon: cache census by sport/season,
zone-field presence counts, matrix decision-year counts - no feature values,
no feature-outcome statistic was computed before this freeze).

FROZEN PITCH UNIVERSE (per pitch event, cached feeds read-only, no network):
  - Only playEvents with isPitch=True are walked. Batter = play-level
    matchup.batter (same convention as tools/efv_statcast_line2_lab.py).
  - SWING = details.code in zone_metrics.SWING_CODES
    ({S, W, F, T, L, M, X, D, E}).
  - TAKE  = details.code in {"B", "*B", "C"} (called ball, blocked ball,
    called strike). "I" (intentional ball), "H" (HBP), pitchouts, automatic
    and no-pitch codes are NOT decisions and are excluded from every
    numerator and denominator.
  - seen = swings + takes. All other codes are ignored entirely.
  - Pre-pitch strike count: reconstructed sequentially inside each play.
    prev_strikes starts at 0; each event carrying a "count" dict (pitch or
    non-pitch, so automatic balls/strikes update state) sets prev_strikes
    AFTER the current pitch is classified with the PRIOR value. A pitch with
    prev_strikes == 2 is a two-strike pitch.
  - Pixel zone: pitchData.zone where present; in_zone = zone in 1..9,
    out_zone = zone in 11..14. Zone presence is tracked-park-only (recon:
    ~30 percent of A pitches, ~5 percent of CPX), so the call-code
    approximation is the primary substrate exactly as the registration
    anticipates ("from pixel zones where present else call-code
    approximation").

FROZEN SCOPE: sportId 11 (AAA), 14 (A), 16 (CPX; home-league name containing
"Dominican" = DSL is excluded), season >= 2023, every feed present in
.cache/game_feeds at run time. Cache recon: A + CPX feeds exist 2023-2026,
AAA feeds exist 2026 only; absent level-seasons are COVERAGE, never fetched.

FROZEN FEATURES (per batter-season; per batter-season-level first, then the
n-weighted mean across in-scope levels for that season, weights = each
level's own n for the feature; reliability shrink w = n / (n + K), K = 200,
a-priori, applied to the deviation from the level-season mean - the exact
_season_rates convention w * (stat - level_norm), NOT a z-score; level-season
means are pooled ratios, sum(numerator) / sum(denominator), across ALL
batters extracted at that level-season):
  take_share_rel  stat = takes / seen;                 n = seen.
  zone_rec_proxy  PRIMARY (batter-season-level with z_seen >= 30 AND
                  o_seen >= 30 zoned decision pitches):
                    stat = (z_takes / z_seen) - (o_takes / o_seen)
                    (z-take minus o-take; higher = worse recognition),
                    n = z_seen + o_seen, level mean = pooled zoned ratio.
                  ELSE call-code approximation (takes >= 1):
                    stat = called_strikes / takes (share of takes that were
                    strikes; higher = worse recognition), n = takes,
                    level mean = pooled cs / takes at the level-season.
                  Both variants are deviations in take-rate units, centered
                  per level-season, sign-aligned (higher = worse), and emit
                  under the single key zone_rec_proxy; source recorded.
  twoK_take_rel   stat = two-strike called strikes taken / two-strike seen
                  (prev_strikes == 2); n = two-strike seen.

FROZEN HARNESS (the xfv_ungraded OOS protocol, mirrored from
efv_ungraded.evaluate; hit side only):
  - Pool: hitter matrix rows with a milb block, not (bust and bust_recent),
    target_censored present; feats via efv_model._vec; identical _prep.
  - Forward chain: train decision_year < Y, test decision_year == Y, train
    >= 60 and test >= 15 (its thresholds), _fit_ridge on the frozen key list
    + _fit_linear_calibration + efv_ungraded._war (clip 6) - all reused, not
    reimplemented. Chain years FROZEN as (2019, 2020, 2021, 2022, 2023,
    2024): the eval's own (2019..2023) extended by 2024, the newest labeled
    decision year in the 2026-07-24 regenerated matrix and the ONLY fold
    whose test rows (milb_season 2023) can reach feed coverage (2023+).
    Recorded a-priori: the matrix has NO labeled row whose milb block sits
    in 2023+ at any TRAIN position of any fold (dy 2023 rows carry
    milb_season 2022; dy 2024 rows carry milb_season 2023 and only ever
    appear as test rows), so the forward-chained fit cannot place weight on
    the new features this cycle; if the run confirms that, the honest
    verdict is COVERAGE-STARVED, not evidence about the features.
  - Baseline keys: efv_ungraded._NOFV_HIT (same-run). Variant keys:
    _NOFV_HIT + [take_share_rel, zone_rec_proxy, twoK_take_rel].
  - Join: matrix row -> (mlbam_id, milb.milb_season) against the extracted
    batter-season features (A/CPX/AAA pooled for that season).
  - Imputation (the _TOOL_IMPUTE lesson): per fold and per feature, missing
    values impute at the OBSERVED TRAIN MEAN over covered train rows; if a
    fold has ZERO covered train rows the fallback is 0.0 (the features are
    level-relative deviations centered at 0 by construction); fallback use
    is recorded per fold.
  - GATE COHORT: low minors = milb_level in {DSL, CPX, A} and (age is None
    or age <= 21), pooled across the chain (the protocol's own cohort).
  - GATE STAT: pooled low-minors Spearman(variant preds, target) minus
    Spearman(baseline preds, target). Bootstrap: 2000 reps, seed 20260724,
    player-clustered (= row resampling; every pooled row is a distinct
    player_key, verified 886/886), percentile CI. BAR: lo95 > 0. One
    attempt. Marginal = FAIL.
  - Descriptive only (never gating): all-levels delta, covered-subset
    reads, per-feature Spearman vs target on the covered dy-2024 low-minors
    rows, coverage tables.

SHIP RULE (on PASS only): ungraded feature-list wiring in efv_ungraded.py,
default-OFF (env flag), provisional-cohort regen note; flip is wave D's.
Artifact: data/xfv_ungraded_disc_eval.json.

Commands (from prospect-tracker/):
  python -m tools.efv_ungraded_disc_lab extract    # walk cached feeds (read-only)
  python -m tools.efv_ungraded_disc_lab features   # build frozen features
  python -m tools.efv_ungraded_disc_lab run        # harness + gate + artifact
  python -m tools.efv_ungraded_disc_lab all
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time
from datetime import date, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

import numpy as np

SEED = 20260724
REPS = 2000
K_SHRINK = 200.0
ZONE_QUAL = 30          # zoned in-zone AND out-zone seen floors for the primary variant
CHAIN_YEARS = (2019, 2020, 2021, 2022, 2023, 2024)
TRAIN_MIN, TEST_MIN = 60, 15
LOW_LEVELS = {"DSL", "CPX", "A"}
MAX_AGE = 21
SEASON_MIN = 2023
SPORT_LEVEL = {11: "AAA", 14: "A", 16: "CPX"}
TAKE_CODES = {"B", "*B", "C"}
DISC_KEYS = ("take_share_rel", "zone_rec_proxy", "twoK_take_rel")

SCRATCH = Path(os.environ.get(
    "WDISC_SCRATCH",
    r"C:\Users\noah\AppData\Local\Temp\claude\c--Users-noah-baseball-projects-BaseballR"
    r"\79ede335-9198-4f14-a494-1a24428ec19f\scratchpad"))
SCRATCH.mkdir(parents=True, exist_ok=True)
ACC_PATH = SCRATCH / "wdisc_acc.pkl"
FEAT_PATH = SCRATCH / "wdisc_features.json"
EVAL_PATH = _ROOT / "data" / "xfv_ungraded_disc_eval.json"

REGISTRATION_ECHO = {
    "source": "docs/efv-2026-07-24/GATES.md :: 'W-DISC (Phase 2b): "
              "swing-decision components -> xfv_ungraded ONLY'",
    "seed": SEED, "bootstrap_reps": REPS, "clustering": "player (rows unique)",
    "features": list(DISC_KEYS), "shrink": "w = n/(n+200), a-priori",
    "harness": "xfv_ungraded OOS protocol, hit side, low-minors gate cohort, "
               "forward chain (2019..2024); 2024 appended a-priori (newest "
               "labeled decision year in the regenerated matrix; the only "
               "fold reaching 2023+ feed coverage)",
    "bar": "low-minors pooled Spearman delta lo95 > 0; one attempt; "
           "marginal = FAIL",
    "ship": "efv_ungraded.py feature-list wiring default-OFF + provisional "
            "regen note; flip reserved to wave D",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ extract
def _new_cell() -> dict:
    return {"seen": 0, "takes": 0, "cs": 0, "swings": 0,
            "z_seen": 0, "z_takes": 0, "o_seen": 0, "o_takes": 0,
            "k2_seen": 0, "k2_cs": 0}


def cmd_extract() -> None:
    """Walk every cached feed (READ-ONLY, json.load on existing files; never
    a fetch) and accumulate the frozen counters per (batter, season, level)."""
    import zone_metrics as zm
    cache = _ROOT / ".cache" / "game_feeds"
    files = sorted(cache.glob("*.json"))
    acc: dict[tuple, dict] = {}
    census: dict[str, int] = {}
    errors = 0
    t0 = time.monotonic()
    for i, fp in enumerate(files, 1):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            errors += 1
            continue
        gd = data.get("gameData") or {}
        home = (gd.get("teams") or {}).get("home") or {}
        sport = (home.get("sport") or {}).get("id")
        try:
            season = int((gd.get("game") or {}).get("season") or 0)
        except (TypeError, ValueError):
            season = 0
        level = SPORT_LEVEL.get(sport)
        if level is None or season < SEASON_MIN:
            continue
        if sport == 16 and "Dominican" in ((home.get("league") or {}).get("name") or ""):
            continue                                    # DSL out of frozen scope
        census[f"{level}_{season}"] = census.get(f"{level}_{season}", 0) + 1
        for play in (data.get("liveData") or {}).get("plays", {}).get("allPlays", []):
            batter = int(((play.get("matchup") or {}).get("batter") or {}).get("id") or 0)
            if not batter:
                continue
            cell = None
            prev_strikes = 0
            for ev in play.get("playEvents", []):
                if ev.get("isPitch"):
                    code = (ev.get("details") or {}).get("code") or ""
                    is_swing = code in zm.SWING_CODES
                    is_take = code in TAKE_CODES
                    if is_swing or is_take:
                        if cell is None:
                            cell = acc.setdefault((batter, season, level), _new_cell())
                        cell["seen"] += 1
                        if is_take:
                            cell["takes"] += 1
                            if code == "C":
                                cell["cs"] += 1
                        else:
                            cell["swings"] += 1
                        zone = (ev.get("pitchData") or {}).get("zone")
                        if isinstance(zone, int) and 1 <= zone <= 14:
                            if zone <= 9:
                                cell["z_seen"] += 1
                                if is_take:
                                    cell["z_takes"] += 1
                            else:
                                cell["o_seen"] += 1
                                if is_take:
                                    cell["o_takes"] += 1
                        if prev_strikes == 2:
                            cell["k2_seen"] += 1
                            if code == "C":
                                cell["k2_cs"] += 1
                cnt = ev.get("count")
                if isinstance(cnt, dict) and cnt.get("strikes") is not None:
                    prev_strikes = int(cnt.get("strikes") or 0)
        if i % 2000 == 0:
            print(f"[extract] {i}/{len(files)} feeds, {len(acc)} batter-season-level "
                  f"cells, {time.monotonic()-t0:.0f}s", flush=True)
    out = {"acc": acc, "census": census, "errors": errors,
           "feeds_walked": len(files), "finished": _now()}
    with ACC_PATH.open("wb") as fh:
        pickle.dump(out, fh, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[extract] DONE {len(files)} feeds -> {len(acc)} cells, census "
          f"{json.dumps(census, sort_keys=True)}, errors {errors}, "
          f"{time.monotonic()-t0:.0f}s", flush=True)


# ----------------------------------------------------------------- features
def _stat_maps(acc: dict) -> dict:
    """Frozen feature build: per-level rel values then n-weighted season pool."""
    # level-season pooled means (sum num / sum den over ALL extracted batters)
    pool: dict[tuple, dict] = {}
    for (b, season, level), c in acc.items():
        p = pool.setdefault((season, level), {k: 0 for k in
                            ("seen", "takes", "cs", "z_seen", "z_takes",
                             "o_seen", "o_takes", "k2_seen", "k2_cs")})
        for k in p:
            p[k] += c[k]
    means: dict[tuple, dict] = {}
    for key, p in pool.items():
        means[key] = {
            "take_share": p["takes"] / p["seen"] if p["seen"] else None,
            "zr_primary": ((p["z_takes"] / p["z_seen"]) - (p["o_takes"] / p["o_seen"]))
                          if p["z_seen"] and p["o_seen"] else None,
            "zr_cc": p["cs"] / p["takes"] if p["takes"] else None,
            "twoK": p["k2_cs"] / p["k2_seen"] if p["k2_seen"] else None,
        }

    def shrunk(stat, mean, n):
        if stat is None or mean is None or not n:
            return None, 0.0
        w = n / (n + K_SHRINK)
        return w * (stat - mean), float(n)

    # per batter-season-level rel values
    per_lvl: dict[tuple, dict] = {}
    zr_source: dict[tuple, str] = {}
    for (b, season, level), c in acc.items():
        m = means[(season, level)]
        rel: dict[str, tuple] = {}
        rel["take_share_rel"] = shrunk(
            c["takes"] / c["seen"] if c["seen"] else None, m["take_share"], c["seen"])
        if c["z_seen"] >= ZONE_QUAL and c["o_seen"] >= ZONE_QUAL and m["zr_primary"] is not None:
            rel["zone_rec_proxy"] = shrunk(
                (c["z_takes"] / c["z_seen"]) - (c["o_takes"] / c["o_seen"]),
                m["zr_primary"], c["z_seen"] + c["o_seen"])
            zr_source[(b, season, level)] = "primary_zoned"
        else:
            rel["zone_rec_proxy"] = shrunk(
                c["cs"] / c["takes"] if c["takes"] else None, m["zr_cc"], c["takes"])
            zr_source[(b, season, level)] = "call_code"
        rel["twoK_take_rel"] = shrunk(
            c["k2_cs"] / c["k2_seen"] if c["k2_seen"] else None, m["twoK"], c["k2_seen"])
        per_lvl[(b, season, level)] = rel

    # n-weighted pool across levels -> per (batter, season)
    by_bs: dict[tuple, dict] = {}
    for (b, season, level), rel in per_lvl.items():
        d = by_bs.setdefault((b, season), {k: [0.0, 0.0] for k in DISC_KEYS})
        for k in DISC_KEYS:
            v, n = rel[k]
            if v is not None and n > 0:
                d[k][0] += v * n
                d[k][1] += n
    feats: dict[str, dict] = {}
    for (b, season), d in by_bs.items():
        row = {}
        for k in DISC_KEYS:
            num, den = d[k]
            row[k] = (num / den) if den > 0 else None
        row["_srcs"] = sorted({zr_source[(bb, ss, ll)] for (bb, ss, ll) in per_lvl
                               if bb == b and ss == season})
        feats[f"{b}_{season}"] = row
    return {"features": feats, "level_season_means": {f"{s}_{l}": v for (s, l), v in means.items()}}


def cmd_features() -> None:
    with ACC_PATH.open("rb") as fh:
        ext = pickle.load(fh)
    built = _stat_maps(ext["acc"])
    built["census"] = ext["census"]
    built["generated_at"] = _now()
    FEAT_PATH.write_text(json.dumps(built), encoding="utf-8")
    n = len(built["features"])
    src = {}
    for r in built["features"].values():
        for s in r["_srcs"]:
            src[s] = src.get(s, 0) + 1
    print(f"[features] {n} batter-seasons; zone_rec sources {src}; "
          f"level-seasons {sorted(built['level_season_means'])}", flush=True)


# ---------------------------------------------------------------------- run
def cmd_run() -> None:
    from efv_dataset import matrix_path
    from efv_model import _vec
    from efv_ungraded import _prep, _NOFV_HIT, _war
    from prospect_path import _fit_ridge, _predict, _fit_linear_calibration, _spearman

    feats_all = json.loads(FEAT_PATH.read_text(encoding="utf-8"))["features"]
    rows = json.loads(matrix_path("hit").read_text(encoding="utf-8"))
    data = _prep([r for r in rows
                  if not bool(r.get("is_pitcher")) and r.get("milb")
                  and not (r.get("kind") == "bust" and r.get("bust_recent"))], "hit")
    # carry mlbam + season + cohort tags alongside (the matrix rows in _prep order)
    src_rows = [r for r in rows
                if not bool(r.get("is_pitcher")) and r.get("milb")
                and not (r.get("kind") == "bust" and r.get("bust_recent"))
                and r.get("target_censored") is not None]
    assert len(src_rows) == len(data)
    for d, r in zip(data, src_rows):
        d["mlbam_id"] = r.get("mlbam_id")
        m = r.get("milb") or {}
        d["milb_level"] = m.get("milb_level")
        d["age"] = m.get("age")
        d["milb_season"] = m.get("milb_season")
        d["disc"] = feats_all.get(f"{r.get('mlbam_id')}_{m.get('milb_season')}")

    def covered(d):
        return d["disc"] is not None and any(d["disc"].get(k) is not None for k in DISC_KEYS)

    n_cov = sum(1 for d in data if covered(d))
    base_keys = list(_NOFV_HIT)
    var_keys = base_keys + list(DISC_KEYS)

    def low_minors(d):
        return d["milb_level"] in LOW_LEVELS and (d["age"] is None or d["age"] <= MAX_AGE)

    pooled = []          # (player_key, low_minors?, base_pred, var_pred, target, covered?, year)
    fold_log = []
    for yr in CHAIN_YEARS:
        tr = [d for d in data if d["decision_year"] < yr]
        te = [d for d in data if d["decision_year"] == yr]
        if len(tr) < TRAIN_MIN or len(te) < TEST_MIN:
            fold_log.append({"year": yr, "skipped": True, "n_train": len(tr), "n_test": len(te)})
            continue
        # frozen imputation: observed train mean per feature; 0.0 when no covered train rows
        imput = {}
        n_cov_tr = 0
        for k in DISC_KEYS:
            vals = [d["disc"][k] for d in tr if d["disc"] and d["disc"].get(k) is not None]
            imput[k] = float(np.mean(vals)) if vals else 0.0
            n_cov_tr = max(n_cov_tr, len(vals))

        def feat_of(d, keys, with_disc):
            f = dict(d["feats"])
            if with_disc:
                for k in DISC_KEYS:
                    v = d["disc"].get(k) if d["disc"] else None
                    f[k] = v if v is not None else imput[k]
            return f

        tr_b = [{"feats": feat_of(d, base_keys, False), "target": d["target"],
                 "weight": d["weight"]} for d in tr]
        tr_v = [{"feats": feat_of(d, var_keys, True), "target": d["target"],
                 "weight": d["weight"]} for d in tr]
        rg_b = _fit_ridge(tr_b, base_keys)
        rg_v = _fit_ridge(tr_v, var_keys)
        if rg_b is None or rg_v is None:
            fold_log.append({"year": yr, "skipped": True, "reason": "fit_none"})
            continue
        cal_b = _fit_linear_calibration([(_predict(rg_b, r["feats"]), r["target"]) for r in tr_b])
        cal_v = _fit_linear_calibration([(_predict(rg_v, r["feats"]), r["target"]) for r in tr_v])
        ab, bb_ = (cal_b["a"], cal_b["b"]) if cal_b else (0.0, 1.0)
        av, bv = (cal_v["a"], cal_v["b"]) if cal_v else (0.0, 1.0)
        n_cov_te = 0
        for d in te:
            pb = _war(rg_b, ab, bb_, feat_of(d, base_keys, False))
            pv = _war(rg_v, av, bv, feat_of(d, var_keys, True))
            cv = covered(d)
            n_cov_te += 1 if cv else 0
            pooled.append((d["player_key"], low_minors(d), pb, pv, d["target"], cv, yr))
        dw = [round(float(w), 4) for w in
              (rg_v["w"][-len(DISC_KEYS):] if rg_v else [])]
        fold_log.append({"year": yr, "n_train": len(tr), "n_test": len(te),
                         "n_covered_train": n_cov_tr, "n_covered_test": n_cov_te,
                         "impute_fallback_zero": n_cov_tr == 0,
                         "disc_ridge_weights": dict(zip(DISC_KEYS, dw))})

    lm = [p for p in pooled if p[1]]
    P_b = [p[2] for p in lm]
    P_v = [p[3] for p in lm]
    T = [p[4] for p in lm]
    sp_b = _spearman(P_b, T)
    sp_v = _spearman(P_v, T)
    delta = (sp_v - sp_b) if (sp_b is not None and sp_v is not None) else None

    rng = np.random.default_rng(SEED)
    n = len(lm)
    deltas = []
    Pb, Pv, Tt = map(np.asarray, (P_b, P_v, T))
    for _ in range(REPS):
        idx = rng.integers(0, n, size=n)
        sb = _spearman(list(Pb[idx]), list(Tt[idx]))
        sv = _spearman(list(Pv[idx]), list(Tt[idx]))
        if sb is not None and sv is not None:
            deltas.append(sv - sb)
    lo95 = float(np.percentile(deltas, 2.5)) if len(deltas) >= REPS * 0.9 else None
    hi95 = float(np.percentile(deltas, 97.5)) if len(deltas) >= REPS * 0.9 else None

    # descriptive reads (never gating)
    al_b = _spearman([p[2] for p in pooled], [p[4] for p in pooled])
    al_v = _spearman([p[3] for p in pooled], [p[4] for p in pooled])
    cov_lm = [p for p in lm if p[5]]
    desc = {
        "all_levels_delta": round(al_v - al_b, 4) if al_b is not None and al_v is not None else None,
        "low_minors_covered_subset_n": len(cov_lm),
        "low_minors_covered_subset_delta": None,
    }
    if len(cov_lm) >= 8:
        cb = _spearman([p[2] for p in cov_lm], [p[4] for p in cov_lm])
        cvv = _spearman([p[3] for p in cov_lm], [p[4] for p in cov_lm])
        if cb is not None and cvv is not None:
            desc["low_minors_covered_subset_delta"] = round(cvv - cb, 4)
    # raw per-feature forward reads on covered dy-2024 low-minors rows
    per_feat = {}
    cov24 = [d for d in data if d["decision_year"] == 2024 and covered(d)
             and low_minors(d)]
    for k in DISC_KEYS:
        xs = [(d["disc"].get(k), d["target"]) for d in cov24 if d["disc"].get(k) is not None]
        if len(xs) >= 8:
            per_feat[k] = {"n": len(xs),
                           "spearman_vs_target": _spearman([a for a, _ in xs], [b for _, b in xs])}
        else:
            per_feat[k] = {"n": len(xs), "spearman_vs_target": None}
    desc["per_feature_dy2024_covered_low_minors"] = per_feat

    gate_pass = lo95 is not None and lo95 > 0
    if gate_pass:
        verdict = "PASS"
    elif all(f.get("n_covered_train", 0) == 0 for f in fold_log if not f.get("skipped")):
        verdict = "COVERAGE-STARVED"
    else:
        verdict = "FAIL"

    artifact = {
        "generated_at": date.today().isoformat(),
        "experiment": "W-DISC (docs/efv-2026-07-24/GATES.md, Phase 2b)",
        "tool": "tools/efv_ungraded_disc_lab.py",
        "registration_echo": REGISTRATION_ECHO,
        "coverage": {
            "feed_census_in_scope": json.loads(FEAT_PATH.read_text(encoding="utf-8"))["census"],
            "batter_seasons_with_features": len(feats_all),
            "matrix_hit_rows_in_pool": len(data),
            "pool_rows_covered": n_cov,
            "low_minors_pooled_n": n,
            "low_minors_pooled_covered": len(cov_lm),
        },
        "folds": fold_log,
        "gate": {
            "cohort": "low minors (DSL/CPX/A, age <= 21), pooled 2019-2024 chain",
            "spearman_baseline": sp_b, "spearman_variant": sp_v,
            "delta": round(delta, 4) if delta is not None else None,
            "lo95": round(lo95, 4) if lo95 is not None else None,
            "hi95": round(hi95, 4) if hi95 is not None else None,
            "bar": "lo95 > 0", "pass": gate_pass,
        },
        "descriptive_not_gating": desc,
        "verdict": verdict,
    }
    if verdict == "COVERAGE-STARVED":
        artifact["structural_note"] = (
            "Forward-chained coverage is structurally zero on the TRAIN side of "
            "every fold: the swing-decision features exist 2023+ (feed cache), "
            "but every labeled row whose milb_season reaches 2023 sits at "
            "decision year 2024 (test-only position). With zero covered train "
            "rows the ridge cannot place weight on the new columns (constant "
            "imputed column -> exact zero weight), so the gate delta is forced "
            "to ~0 regardless of feature quality. This is a coverage verdict, "
            "not evidence against swing-decision signal.")
        artifact["revival"] = (
            "Re-register after a matrix regeneration labels decision-year-2025 "
            "rows (2025 debuts / cutoff-2024 busts with observed seasons): the "
            "dy-2024 rows (milb_season 2023, covered) then become TRAIN rows "
            "for the dy-2025 fold and the same frozen protocol becomes "
            "expressible. Expected earliest: the 2027 cycle. The extraction + "
            "frozen feature build in this tool are reusable as-is; "
            "per-feature descriptive reads on the covered dy-2024 cohort are "
            "recorded above for that ledger.")
    EVAL_PATH.write_text(json.dumps(artifact, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(artifact["gate"], indent=1), flush=True)
    print("verdict:", verdict, "->", EVAL_PATH, flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("extract", "all"):
        cmd_extract()
    if cmd in ("features", "all"):
        cmd_features()
    if cmd in ("run", "all"):
        cmd_run()

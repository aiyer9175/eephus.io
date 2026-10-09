# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Multi-horizon WAR-path evaluation — the measurement Gate 1 doesn't do.

Gate 1 scores NEXT-season projections; the contract/projection surfaces
price seasons 2-5+ through the aging decay, which until this harness had
no backtest at all (the 2031-tail-compression bug shipped because nothing
measured horizon 5). Forward-chained like the gates: for each base season
B, models fit on data <= B-1 project horizons h = 1..5 (seasons B..B+4),
scored against actual bWAR (absent seasons = 0, both sides).

Metrics per horizon:
  mae        pooled |pred - actual|
  mae_star   the star slice (actual >= 4 WAR in the base-year season B) —
             the population the compression bug hurts most
  tail_pred / tail_act   players predicted vs observed at >= 3 WAR — the
             calibration the owner's "only 6 players > 2.8 in 2031"
             complaint is about. A healthy model keeps the RATIO near 1.
  coverage   v2 — empirical P10-P90 band coverage per horizon (the bands
             gate-checked at h1 only were never measured beyond it), both
             POOLED (absent seasons = 0 actual, which a wide band catches
             trivially) and SURVIVED-ONLY (the player actually played the
             target season — the honest read).
  pinball    v2 — quantile (pinball) loss at q10/q90 per horizon: the
             scoring rule a quantile challenger must beat, not just hit
             coverage on.

v2 also makes the model PLUGGABLE: pass ``predict_fn`` building a path
dict ({war_by_year, war_by_year_p10, war_by_year_p90}) from listing-time
inputs, and champion/challenger share this one harness. Default = the
incumbent fa_market.contract_war_path.

Run: python proj_eval.py [--bases 2017-2021] [--rowmatch]
Persists data/proj_horizon_eval.json (rendered nowhere yet — a model-dev
artifact with the same honesty rules as the gates). --rowmatch adds the
row-matched champion-vs-proj_lgbm_v1 block (identical rows, both models,
one n per cell): the challenger_blocks ride different base sets than the
champion cells, and cross-base MAE reads invite false win claims.

HOLDOUT DISCIPLINE: bases 2017-2021 are the DEV loop (they overlap Gate 1
targets). Bases 2022-2024 (h1-h3 resolvable) are the touched-once
confirmation holdout for champion/challenger ship decisions — never use
them to tune."""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import fa_market as fm
import fa_projection as fp

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
HORIZONS = 5


def _utc_stamp() -> str:
    """UTC timestamp for the artifact's generated_at (the freshness bar ages
    undated artifacts by mtime, which the deploy box rewrites nightly)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _assemble(corpus: dict):
    """(league, by_player, war_actual) from the corpus.

    war_actual is {(mlbam, season): TOTAL player WAR}, built by
    fa_projection.war_actual_map - the SAME function proj_ml
    .build_training_frame calls, so what this harness scores and what the
    frame trains on cannot drift apart.

    It used to be accumulated here by adding r["war"] across sides. The corpus
    wrote the whole-player total onto the hitter row AND the pitcher row, so
    that sum doubled every player-season carrying a row on both sides, and it
    doubled them on BOTH sides of the comparison: the harness scored against
    the same doubled truth the frame trained on, so the error cancelled in
    every published receipt and surfaced only as a level. Repaired
    2026-09-18; see fa_projection._side_war_age_maps."""
    league = corpus["league"]
    by_player: dict[str, dict[int, dict[int, dict]]] = {
        "hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
    return league, by_player, fp.war_actual_map(corpus)


def _pinball(q: float, actual: float, pred_q: float) -> float:
    """Quantile (pinball) loss — the proper scoring rule for a quantile."""
    d = actual - pred_q
    return q * d if d >= 0 else (q - 1.0) * d


def default_predict_fn(hist, side, base, age, curves, war_map, league):
    """The incumbent champion: Marcel year-1 + regressed-rate aging decay
    with Gate-1 quantile bands. use_ml=False PINS the champion — this
    baseline must stay the champion even after an ML bundle ships."""
    # aging="v2" EXPLICITLY (docs/AGING_V3_GATE.md section 2): the eval scores
    # the incumbent engine; the aging v3 lab scores its arms through its own
    # predict_fn.
    return fm.contract_war_path(hist, side, base, HORIZONS, age,
                                curves, war_map, league, use_ml=False,
                                aging="v2")


def run(bases: list[int], persist: bool = True, predict_fn=None,
        model_label: str = "marcel_decay_v2") -> dict:
    predict_fn = predict_fn or default_predict_fn
    corpus = fp.build_corpus()
    league, by_player, war_actual = _assemble(corpus)

    stats = {h: {"pairs": [], "star_pairs": [], "tail_pred": 0, "tail_act": 0,
                 "cov_hit": 0, "cov_n": 0, "cov_hit_sv": 0, "cov_n_sv": 0,
                 "pin10": [], "pin90": []}
             for h in range(1, HORIZONS + 1)}
    n_players = 0
    for B in bases:
        curves, war_map = fp.fitted_models(corpus, B - 1, aging="v2")
        for side in ("hit", "pit"):
            for mlbam, seasons in by_player[side].items():
                hist = [seasons[t] for t in (B - 1, B - 2, B - 3) if t in seasons]
                if not hist:
                    continue
                # Anchor the age offset to the row that supplied the age (hist[0]
                # can have WAR but a null age while an older row carries the age).
                age_row = next((h for h in hist if h.get("age")), None)
                if age_row is None:
                    continue
                age = age_row["age"] + (B - age_row["season"])
                path = predict_fn(hist, side, B, age, curves, war_map, league)
                if path is None:
                    continue
                n_players += 1
                base_actual = war_actual.get((mlbam, B - 1))
                is_star = base_actual is not None and base_actual >= 4.0
                p10s = path.get("war_by_year_p10")
                p90s = path.get("war_by_year_p90")
                for h in range(1, HORIZONS + 1):
                    target = B + h - 1
                    if target > corpus["last"] - 1:        # complete seasons only
                        continue
                    pred = path["war_by_year"][h - 1]
                    survived = (mlbam, target) in war_actual
                    act = war_actual.get((mlbam, target), 0.0)
                    s = stats[h]
                    s["pairs"].append((pred, act))
                    if is_star:
                        s["star_pairs"].append((pred, act))
                    if pred >= 3.0:
                        s["tail_pred"] += 1
                    if act >= 3.0:
                        s["tail_act"] += 1
                    # v2 — band coverage + pinball, where the model ships bands
                    if p10s and p90s and h - 1 < len(p10s):
                        lo, hi = p10s[h - 1], p90s[h - 1]
                        inside = lo <= act <= hi
                        s["cov_n"] += 1
                        s["cov_hit"] += 1 if inside else 0
                        if survived:
                            s["cov_n_sv"] += 1
                            s["cov_hit_sv"] += 1 if inside else 0
                        s["pin10"].append(_pinball(0.10, act, lo))
                        s["pin90"].append(_pinball(0.90, act, hi))

    out = {"model": model_label, "bases": bases, "n_players": n_players,
           "horizons": {}}
    for h, s in stats.items():
        if not s["pairs"]:
            continue
        mae = sum(abs(p - a) for p, a in s["pairs"]) / len(s["pairs"])
        bias = sum(p - a for p, a in s["pairs"]) / len(s["pairs"])
        star = (sum(abs(p - a) for p, a in s["star_pairs"]) / len(s["star_pairs"])
                if s["star_pairs"] else None)
        star_bias = (sum(p - a for p, a in s["star_pairs"]) / len(s["star_pairs"])
                     if s["star_pairs"] else None)
        out["horizons"][h] = {
            "n": len(s["pairs"]), "mae": round(mae, 4), "bias": round(bias, 4),
            "n_star": len(s["star_pairs"]),
            "mae_star": round(star, 4) if star is not None else None,
            "bias_star": round(star_bias, 4) if star_bias is not None else None,
            "tail_pred_ge3": s["tail_pred"], "tail_act_ge3": s["tail_act"],
            "tail_ratio": round(s["tail_pred"] / s["tail_act"], 3) if s["tail_act"] else None,
            "coverage": round(s["cov_hit"] / s["cov_n"], 4) if s["cov_n"] else None,
            "coverage_survived": (round(s["cov_hit_sv"] / s["cov_n_sv"], 4)
                                  if s["cov_n_sv"] else None),
            "n_survived": s["cov_n_sv"],
            "pinball_q10": (round(sum(s["pin10"]) / len(s["pin10"]), 4)
                            if s["pin10"] else None),
            "pinball_q90": (round(sum(s["pin90"]) / len(s["pin90"]), 4)
                            if s["pin90"] else None),
        }
    return out


def run_rowmatch(bases: list[int]) -> dict:
    """Row-matched champion-vs-challenger cut. MEASUREMENT ONLY: no ship
    decision rides on this block; it exists so nobody reads a win off
    mismatched bases.

    The challenger_blocks sit on DIFFERENT base sets than the champion
    top-level cells (gate1_targets h1 MAE 0.5569 pools 10 bases against the
    champion's 0.647 on 4, which invites a false win claim). This cut scores
    BOTH models on the identical (player, horizon) rows: a row enters a cell
    only when the champion AND the challenger each produce a path for it, so
    both models carry the same n in every cell by construction.

    Champion: marcel_decay_v2 via default_predict_fn (use_ml=False pinned).
    Challenger: proj_lgbm_v1 point-in-time bundles (proj_ml.train_cached,
    labels <= B-1, full quantile set, no blend lambdas in bundle meta), the
    same raw forward-chained basis as challenger_blocks.dev; the point
    prediction is the monotone-sorted q50. The champion path rides into the
    challenger features via champ= (no recomputation, no recursion)."""
    import proj_ml
    corpus = fp.build_corpus()
    league, by_player, war_actual = _assemble(corpus)
    cells = {h: {"pairs_c": [], "pairs_x": [], "star_c": [], "star_x": [],
                 "tp_c": 0, "tp_x": 0, "ta": 0}
             for h in range(1, HORIZONS + 1)}
    n_matched = 0
    for B in bases:
        curves, war_map = fp.fitted_models(corpus, B - 1, aging="v2")
        bundle = proj_ml.train_cached(corpus, B - 1, quantiles=proj_ml.QUANTILES)
        for side in ("hit", "pit"):
            for mlbam, seasons in by_player[side].items():
                hist = [seasons[t] for t in (B - 1, B - 2, B - 3) if t in seasons]
                if not hist:
                    continue
                age = proj_ml.age_from_history(hist, B)
                if age is None:
                    continue
                champ = default_predict_fn(hist, side, B, age, curves,
                                           war_map, league)
                if champ is None:
                    continue
                feats = proj_ml.build_features(hist, side, B, age, curves,
                                               war_map, league, champ=champ)
                chal = (proj_ml.predict_path(bundle, feats, side)
                        if feats is not None else None)
                if chal is None:
                    continue                     # row must be scoreable by BOTH
                n_matched += 1
                base_actual = war_actual.get((mlbam, B - 1))
                is_star = base_actual is not None and base_actual >= 4.0
                for h in range(1, HORIZONS + 1):
                    target = B + h - 1
                    if target > corpus["last"] - 1:        # complete seasons only
                        continue
                    act = war_actual.get((mlbam, target), 0.0)
                    pc = champ["war_by_year"][h - 1]
                    px = chal["war_by_year"][h - 1]
                    s = cells[h]
                    s["pairs_c"].append((pc, act))
                    s["pairs_x"].append((px, act))
                    if is_star:
                        s["star_c"].append((pc, act))
                        s["star_x"].append((px, act))
                    if pc >= 3.0:
                        s["tp_c"] += 1
                    if px >= 3.0:
                        s["tp_x"] += 1
                    if act >= 3.0:
                        s["ta"] += 1

    def _mae(pairs):
        return (round(sum(abs(p - a) for p, a in pairs) / len(pairs), 4)
                if pairs else None)

    out = {
        "generated_at": _utc_stamp(),
        "champion_model": "marcel_decay_v2",
        "challenger_model": "proj_lgbm_v1",
        "basis": ("row-matched: identical (player, horizon) rows scored by both "
                  "models; challenger = forward-chained point-in-time bundles "
                  "(labels <= B-1, full quantiles, no blend lambdas), champion = "
                  "use_ml=False decay path; measurement only, no ship decision"),
        "bases": bases, "n_players_matched": n_matched, "horizons": {}}
    for h, s in cells.items():
        n = len(s["pairs_c"])
        if not n:
            continue
        # row-matched by construction; a mismatch here is a harness bug
        if n != len(s["pairs_x"]):
            raise AssertionError(f"rowmatch h{h}: champion n {n} != "
                                 f"challenger n {len(s['pairs_x'])}")
        ta = s["ta"]
        out["horizons"][h] = {
            "n": n, "tail_act_ge3": ta,
            "champion": {
                "n": n, "mae": _mae(s["pairs_c"]),
                "n_star": len(s["star_c"]), "mae_star": _mae(s["star_c"]),
                "tail_pred_ge3": s["tp_c"],
                "tail_ratio": round(s["tp_c"] / ta, 3) if ta else None},
            "challenger": {
                "n": n, "mae": _mae(s["pairs_x"]),
                "n_star": len(s["star_x"]), "mae_star": _mae(s["star_x"]),
                "tail_pred_ge3": s["tp_x"],
                "tail_ratio": round(s["tp_x"] / ta, 3) if ta else None},
        }
    return out


# ---------------------------------------------------------------------------
# PJ-C: the component scorer (docs/PROJ_COMPONENTS_GATE.md sections 3 to 5)
# ---------------------------------------------------------------------------
# New code only. run() and run_rowmatch() above are pinned byte-identical by
# test_proj_eval.py. The scorer reads a frame it is handed (PJ_2 builds it),
# calls each predictor and comparator only on rows inside the cells it is
# asked to score, and writes nothing: PJ_4 writes the `dev` block and PJ_5 the
# `holdout` block of the component eval artifact (COMPONENTS_EVAL_NAME).

COMPONENTS_EVAL_NAME = "proj_components_eval.json"
COMPONENT_DEV_LAST_LABEL = 2021           # DEV: label seasons <= 2021
COMPONENT_LOOK_LABEL_CEILING = 2026       # never read: label season 2026 or later
COMPONENT_EXCLUDED_LABELS = (2020,)       # excluded as Gate 1 excludes it
# component -> (side, kind). "rate": scored as an exposure-weighted rate MAE
# on survived rows; "exposure": the H0 / P0 exposure test (section 4.3).
COMPONENT_SPECS = {
    "bsr": ("hit", "rate"),             # H3 baserunning runs (verdict)
    "fld_pos": ("hit", "rate"),         # H4 + H5 fielding plus positional runs (verdict)
    "batting": ("hit", "rate"),         # H2 batting runs (receipt)
    "league": ("hit", "rate"),          # H6 league runs (receipt)
    "replacement": ("hit", "rate"),     # H7 replacement runs (receipt)
    "gmli_relief": ("pit", "rate"),     # P4 through the relief runs it multiplies (verdict)
    "ra9_gap": ("pit", "rate"),         # P5 the RA9 gap in runs (verdict)
    "pa": ("hit", "exposure"),          # H0 exposure test
    "ip": ("pit", "exposure"),          # P0 exposure test
}
COMPONENT_RATE_SCALE = {"hit": 600.0, "pit": 100.0}
COMPONENT_RATE_UNIT = {"hit": "runs per 600 PA", "pit": "runs per 100 IP"}
COMPONENT_EXPOSURE_UNIT = {"hit": "PA", "pit": "IP"}
COMPONENT_STAR_BASE = {"hit": 500.0, "pit": 120.0}  # PA or IP in season B - 1
Z_ONE_SIDED_95 = 1.645


def _hist_value(hist, season: int):
    """A season's exposure from an exposure_hist map keyed by int or str."""
    if not isinstance(hist, dict):
        return None
    v = hist.get(season)
    if v is None:
        v = hist.get(str(season))
    return v


def _exposure_prior_season(row: dict):
    """Exposure comparator: the prior-season (B - 1) PA or IP. A player whose
    history is known but who has no B - 1 season carries 0; a row with no
    exposure_hist at all returns None (not scoreable)."""
    hist = row.get("exposure_hist")
    if not isinstance(hist, dict):
        return None
    v = _hist_value(hist, int(row["base"]) - 1)
    return float(v) if v is not None else 0.0


def _exposure_543(row: dict):
    """Exposure comparator: the 5/4/3 weighted three-season PA or IP over the
    seasons present in B - 1 to B - 3, the Gate 1 naive form
    (fa_backtest._baseline). None when no season is present."""
    hist = row.get("exposure_hist")
    num = den = 0.0
    for lag, w in ((1, 5.0), (2, 4.0), (3, 3.0)):
        v = _hist_value(hist, int(row["base"]) - lag)
        if v is None:
            continue
        num += w * float(v)
        den += w
    return num / den if den else None


EXPOSURE_COMPARATORS = {"prior_season": _exposure_prior_season,
                        "w543": _exposure_543}


def _paired_cluster_bootstrap(deltas_by_player: dict, B: int, seed: int) -> dict:
    """Paired bootstrap clustered on player.

    deltas_by_player maps a player to his paired row deltas, each a float
    (weight 1) or a (delta, weight) pair. The statistic is the weighted mean
    delta, sum(w * d) / sum(w); each of the B draws resamples PLAYERS with
    replacement and keeps every row of a drawn player, so the rows one player
    supplies (horizons, bases) are never treated as independent. Returns the
    point statistic, the sd of the B draws (ddof 1) and the counts; point is
    None with no scoreable player, and sd is None with fewer than two players
    (one cluster has no spread to measure, and a zero sd would read as
    certainty). The same seed gives the same draws. No VIF is applied here:
    the caller multiplies the sd."""
    import numpy as np

    num: list[float] = []
    den: list[float] = []
    n_rows = 0
    for key in sorted(deltas_by_player, key=str):
        nk = dk = 0.0
        for item in deltas_by_player[key] or ():
            if isinstance(item, (tuple, list)):
                d, w = item
            else:
                d, w = item, 1.0
            if d is None or w is None:
                continue
            d, w = float(d), float(w)
            if not (np.isfinite(d) and np.isfinite(w)) or w <= 0:
                continue
            nk += w * d
            dk += w
            n_rows += 1
        if dk > 0:
            num.append(nk)
            den.append(dk)
    out = {"B": int(B), "seed": int(seed), "n_players": len(num),
           "n_rows": n_rows, "point": None, "sd": None}
    if not num:
        return out
    num_a = np.asarray(num, dtype=float)
    den_a = np.asarray(den, dtype=float)
    out["point"] = float(num_a.sum() / den_a.sum())
    if B < 2 or len(num_a) < 2:
        return out
    rng = np.random.default_rng(seed)
    n = len(num_a)
    stats = np.empty(int(B), dtype=float)
    chunk = 50
    for start in range(0, int(B), chunk):
        stop = min(int(B), start + chunk)
        idx = rng.integers(0, n, size=(stop - start, n))
        stats[start:stop] = num_a[idx].sum(axis=1) / den_a[idx].sum(axis=1)
    out["sd"] = float(stats.std(ddof=1))
    return out


def _component_value(out, field: str):
    """The scored number from a predictor or comparator return: None, a plain
    number, or a dict carrying `field` ("rate" or "exposure")."""
    if out is None:
        return None
    if isinstance(out, dict):
        v = out.get(field)
    else:
        v = out
    return None if v is None else float(v)


def _refuse_war_key(out, who: str) -> None:
    """The scorer never computes a WAR residual: a predictor or comparator
    that returns a key named war raises, so no report can carry one."""
    if isinstance(out, dict) and any(str(k).strip().lower() == "war" for k in out):
        raise ValueError(f"{who} returned a key named war; the component scorer "
                         "computes no WAR residual (PROJ_COMPONENTS_GATE.md section 3)")


def _components_guard(cells, look: bool) -> list[tuple[int, int]]:
    """Validate the cells and the frame rules before any row is read."""
    out = []
    for c in cells:
        base, h = int(c[0]), int(c[1])
        if not 1 <= h <= HORIZONS:
            raise ValueError(f"cell ({base}, {h}): horizon outside 1..{HORIZONS}")
        label = base + h - 1
        if label in COMPONENT_EXCLUDED_LABELS:
            raise ValueError(f"cell ({base}, h{h}): label season {label} is excluded")
        if not look and label > COMPONENT_DEV_LAST_LABEL:
            raise ValueError(f"cell ({base}, h{h}): label season {label} is above "
                             f"{COMPONENT_DEV_LAST_LABEL}; only the one look "
                             "(look=True) may read it")
        if look and label >= COMPONENT_LOOK_LABEL_CEILING:
            raise ValueError(f"cell ({base}, h{h}): label season {label} is never "
                             "read by this gate")
        out.append((base, h))
    if look:
        path = DATA_DIR / COMPONENTS_EVAL_NAME
        if path.exists():
            try:
                art = json.loads(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise ValueError(f"{path.name} is unparseable; the one-look "
                                 "check cannot be made") from exc
            if isinstance(art, dict) and "holdout" in art:
                raise ValueError(f"{path.name} already carries a 'holdout' block: "
                                 "the PJ-C look runs once")
    return sorted(set(out))


def run_components(frame_rows, predictors, comparators, cells, seed,
                   B=1000, vif=1.8, look=False) -> dict:
    """Score component heads on a forward-chained frame (PJ-C, section 4 of
    docs/PROJ_COMPONENTS_GATE.md). Nothing is written.

    frame_rows: dicts with
      mlbam          the player (the bootstrap cluster)
      side           "hit" or "pit"
      base, h        the cell; label_season, when present, must be base + h - 1
      exposure       actual PA (hit) or IP (pit) in the label season; None or
                     0 means the player did not play it (an absent season)
      exposures      optional {component: actual exposure} override (P4 is
                     weighted by relief IP)
      exposure_base  PA or IP in season B - 1 (the star slice: >= 500 PA or
                     >= 120 IP)
      exposure_hist  optional {season: PA or IP} for B - 3 to B - 1 (the
                     exposure comparators)
      labels         {component: realized season runs}; None when unknown
    predictors: {component: fn(row)}; a component is a COMPONENT_SPECS key.
      fn returns None (not projected), a number (the rate, or for "pa"/"ip"
      the exposure) or a dict with "rate" (runs per 600 PA or per 100 IP),
      "exposure" (projected PA or IP) and optional "p10"/"p90" (the 80% range
      of the season's runs, or of the exposure for "pa"/"ip").
    comparators: {component: {name: fn(row)}}, same return shapes. "pa" and
      "ip" default to EXPOSURE_COMPARATORS (prior season and 5/4/3).
    cells: (base, h) pairs. Rows outside them are never passed to a predictor.

    Row matching: a row enters a component's cell only when the candidate and
    EVERY comparator return a value, so all comparators are judged on
    identical rows; dropped rows are counted by reason. Primary statistic:
    exposure-weighted rate MAE on survived rows (for "pa"/"ip", exposure MAE
    on survived rows). Pooled metrics count an absent season as 0 runs (or 0
    exposure). Per comparator: the paired delta (candidate minus comparator)
    with a player-clustered bootstrap, sd multiplied by vif, one-sided 95%
    upper bound delta + 1.645 sd vif and MDE95 1.645 sd vif, also on the star
    slice."""
    cell_list = _components_guard(cells, look)
    cell_set = set(cell_list)
    preds = dict(predictors or {})
    if not preds:
        raise ValueError("no predictors")
    comps_in = dict(comparators or {})
    for comp in preds:
        if str(comp).strip().lower() == "war":
            raise ValueError("a component named war is a WAR residual; refused")
        if comp not in COMPONENT_SPECS:
            raise ValueError(f"unknown component {comp!r}; known: "
                             f"{sorted(COMPONENT_SPECS)}")
        kind = COMPONENT_SPECS[comp][1]
        if not comps_in.get(comp):
            if kind == "exposure":
                comps_in[comp] = dict(EXPOSURE_COMPARATORS)
            else:
                raise ValueError(f"component {comp!r} has no comparator")
    horizons = sorted({h for _b, h in cell_list})
    rows_in = []
    for r in frame_rows or ():
        base, h = int(r["base"]), int(r["h"])
        ls = r.get("label_season")
        if ls is not None and int(ls) != base + h - 1:
            raise ValueError(f"row {r.get('mlbam')} ({base}, h{h}): label_season "
                             f"{ls} is not base + h - 1")
        if (base, h) in cell_set:
            rows_in.append(r)

    report = {
        "scorer": "proj_eval.run_components",
        "look": bool(look), "seed": int(seed), "B": int(B), "vif": float(vif),
        "cells": [list(c) for c in cell_list],
        "label_seasons": sorted({b + h - 1 for b, h in cell_list}),
        "n_rows_in_cells": len(rows_in),
        "components": {},
    }
    for comp, fn in preds.items():
        side, kind = COMPONENT_SPECS[comp]
        field = "rate" if kind == "rate" else "exposure"
        scale = COMPONENT_RATE_SCALE[side]
        star_floor = COMPONENT_STAR_BASE[side]
        cmp_fns = comps_in[comp]
        per_h = {h: {"rows": [], "drop": defaultdict(int)} for h in horizons}
        for r in rows_in:
            if r.get("side") != side:
                continue
            cell = per_h[int(r["h"])]
            out = fn(r)
            _refuse_war_key(out, f"predictor {comp}")
            pv = _component_value(out, field)
            if pv is None:
                cell["drop"]["no_candidate"] += 1
                continue
            cvals = {}
            for name, cfn in cmp_fns.items():
                cout = cfn(r)
                _refuse_war_key(cout, f"comparator {name} for {comp}")
                cvals[name] = _component_value(cout, field)
            missing = [n for n, v in cvals.items() if v is None]
            if missing:
                for n in missing:
                    cell["drop"][f"comparator:{n}"] += 1
                continue
            act_exp = (r.get("exposures") or {}).get(comp, r.get("exposure"))
            act_exp = float(act_exp) if act_exp is not None else 0.0
            if kind == "rate":
                label = (r.get("labels") or {}).get(comp)
                if act_exp > 0 and label is None:
                    cell["drop"]["no_label"] += 1
                    continue
                survived = act_exp > 0
                act_runs = float(label) if survived else 0.0
                act_rate = act_runs / act_exp * scale if survived else None
                proj_exp = out.get("exposure") if isinstance(out, dict) else None
                pred_runs = (pv * float(proj_exp) / scale
                             if proj_exp is not None else None)
                actual_pooled = act_runs
                actual_scored = act_rate
                weight = act_exp
            else:
                survived = act_exp > 0
                pred_runs = None
                actual_pooled = act_exp
                actual_scored = act_exp if survived else None
                weight = 1.0
            base_exp = r.get("exposure_base")
            star = base_exp is not None and float(base_exp) >= star_floor
            p10 = out.get("p10") if isinstance(out, dict) else None
            p90 = out.get("p90") if isinstance(out, dict) else None
            cell["rows"].append({
                "player": r.get("mlbam"), "pred": pv, "cmp": cvals,
                "survived": survived, "star": star, "w": weight,
                "actual": actual_scored, "actual_pooled": actual_pooled,
                "pred_runs": pred_runs, "p10": p10, "p90": p90})
        report["components"][comp] = {
            "side": side, "kind": kind,
            "unit": (COMPONENT_RATE_UNIT[side] if kind == "rate"
                     else COMPONENT_EXPOSURE_UNIT[side]),
            "statistic": ("exposure-weighted rate MAE on survived rows"
                          if kind == "rate" else "exposure MAE on survived rows"),
            "comparators": sorted(cmp_fns),
            "horizons": {h: _component_cell(per_h[h], sorted(cmp_fns), kind,
                                            seed, B, vif)
                         for h in horizons},
        }
    return report


def _component_cell(cell: dict, cmp_names: list, kind: str, seed, B, vif) -> dict:
    """Metrics of one (component, horizon) cell from its matched rows."""
    rows = cell["rows"]
    sv = [x for x in rows if x["survived"]]
    star = [x for x in sv if x["star"]]

    def wmae(xs, key=None):
        den = sum(x["w"] for x in xs)
        if not xs or den <= 0:
            return None
        pick = (lambda x: x["pred"]) if key is None else (lambda x: x["cmp"][key])
        return round(sum(x["w"] * abs(pick(x) - x["actual"]) for x in xs) / den, 4)

    def wbias(xs):
        den = sum(x["w"] for x in xs)
        if not xs or den <= 0:
            return None
        return round(sum(x["w"] * (x["pred"] - x["actual"]) for x in xs) / den, 4)

    runs = [x for x in rows if x["pred_runs"] is not None]
    runs_sv = [x for x in runs if x["survived"]]
    cov = [x for x in rows if x["p10"] is not None and x["p90"] is not None]
    cov_sv = [x for x in cov if x["survived"]]

    def inside(x):
        return float(x["p10"]) <= x["actual_pooled"] <= float(x["p90"])

    out = {
        "n": len(rows), "n_survived": len(sv), "n_star": len(star),
        "n_dropped": dict(sorted(cell["drop"].items())),
        "mae": wmae(sv), "bias": wbias(sv),
        "mae_star": wmae(star), "bias_star": wbias(star),
        "coverage": (round(sum(1 for x in cov if inside(x)) / len(cov), 4)
                     if cov else None),
        "coverage_survived": (round(sum(1 for x in cov_sv if inside(x)) / len(cov_sv), 4)
                              if cov_sv else None),
        "n_coverage": len(cov), "n_coverage_survived": len(cov_sv),
        "pinball_q10": (round(sum(_pinball(0.10, x["actual_pooled"], float(x["p10"]))
                                  for x in cov) / len(cov), 4) if cov else None),
        "pinball_q90": (round(sum(_pinball(0.90, x["actual_pooled"], float(x["p90"]))
                                  for x in cov) / len(cov), 4) if cov else None),
        "comparators": {},
    }
    if kind == "rate":
        out["n_runs"] = len(runs)
        out["runs_mae"] = (round(sum(abs(x["pred_runs"] - x["actual_pooled"])
                                     for x in runs) / len(runs), 4) if runs else None)
        out["runs_mae_survived"] = (round(sum(abs(x["pred_runs"] - x["actual_pooled"])
                                              for x in runs_sv) / len(runs_sv), 4)
                                    if runs_sv else None)
    for name in cmp_names:
        out["comparators"][name] = {
            "mae": wmae(sv, name), "mae_star": wmae(star, name),
            "pooled": _paired_block(sv, name, seed, B, vif),
            "star": _paired_block(star, name, seed, B, vif),
        }
    return out


def _paired_block(xs: list, name: str, seed, B, vif) -> dict:
    """Paired delta (candidate minus comparator, weighted MAE) with its
    one-sided 95% upper bound and MDE95, sd from the clustered bootstrap
    multiplied by vif."""
    by_player: dict = defaultdict(list)
    for x in xs:
        d = abs(x["pred"] - x["actual"]) - abs(x["cmp"][name] - x["actual"])
        by_player[x["player"]].append((d, x["w"]))
    bs = _paired_cluster_bootstrap(by_player, B, seed)
    sd = bs["sd"]
    mde = Z_ONE_SIDED_95 * sd * float(vif) if sd is not None else None
    point = bs["point"]
    return {
        "n_players": bs["n_players"], "n_rows": bs["n_rows"],
        "delta": round(point, 4) if point is not None else None,
        "sd": round(sd, 6) if sd is not None else None,
        "ub95": (round(point + mde, 4)
                 if point is not None and mde is not None else None),
        "mde95": round(mde, 4) if mde is not None else None,
    }


def format_components_report(report: dict) -> str:
    """Plain-text report of run_components. A cell or slice with no rows
    prints 'n/a (n=0)'; a missing number prints 'n/a'. Never raises on
    nulls."""
    def num(v, n=None):
        if n == 0:
            return "n/a (n=0)"
        return "n/a" if v is None else f"{v:.3f}"

    lines = [f"PJ-C component scorer (look={report.get('look')}, seed "
             f"{report.get('seed')}, B {report.get('B')}, VIF {report.get('vif')}, "
             f"label seasons {report.get('label_seasons')})"]
    for comp, blk in (report.get("components") or {}).items():
        lines.append(f"{comp} [{blk.get('side')}, {blk.get('unit')}; "
                     f"{blk.get('statistic')}]")
        for h, c in (blk.get("horizons") or {}).items():
            if not c.get("n"):
                lines.append(f"  h{h}  n/a (n=0)  dropped {c.get('n_dropped') or {}}")
                continue
            ns, nst = c.get("n_survived"), c.get("n_star")
            runs = (f"  runs MAE {num(c.get('runs_mae'), c.get('n_runs'))}"
                    if blk.get("kind") == "rate" else "")
            lines.append(
                f"  h{h}  n {c['n']}  survived {ns}  MAE {num(c.get('mae'), ns)}  "
                f"bias {num(c.get('bias'), ns)}  star n {nst} MAE "
                f"{num(c.get('mae_star'), nst)}{runs}  cov "
                f"{num(c.get('coverage'), c.get('n_coverage'))} / "
                f"{num(c.get('coverage_survived'), c.get('n_coverage_survived'))}  "
                f"pinball {num(c.get('pinball_q10'), c.get('n_coverage'))} / "
                f"{num(c.get('pinball_q90'), c.get('n_coverage'))}")
            for name, k in (c.get("comparators") or {}).items():
                p, s = k.get("pooled") or {}, k.get("star") or {}
                lines.append(
                    f"      vs {name}: MAE {num(k.get('mae'), ns)}  delta "
                    f"{num(p.get('delta'), p.get('n_players'))}  ub95 "
                    f"{num(p.get('ub95'), p.get('n_players'))}  MDE95 "
                    f"{num(p.get('mde95'), p.get('n_players'))}  star delta "
                    f"{num(s.get('delta'), s.get('n_players'))}  star ub95 "
                    f"{num(s.get('ub95'), s.get('n_players'))}")
    return "\n".join(lines)


def _parse_bases(spec: str) -> list[int]:
    """Expand a --bases spec into an explicit, sorted, de-duplicated season
    list. A 'lo-hi' token is an INCLUSIVE range: '2017-2021' -> [2017, 2018,
    2019, 2020, 2021]. (The prior endpoint-only parse silently dropped the
    interior cohorts 2018-2020, biasing the champion/challenger ship decision
    on the documented '2022-2024' holdout.) Plain comma tokens parse as
    literals, so the dashless default keeps its deliberate 2020-COVID gap."""
    out: set[int] = set()
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok:
            continue
        if "-" in tok:
            lo_s, hi_s = tok.split("-", 1)
            lo, hi = int(lo_s), int(hi_s)
            if hi < lo:
                lo, hi = hi, lo
            out.update(range(lo, hi + 1))
        else:
            out.add(int(tok))
    return sorted(out)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--bases", default="2017,2018,2019,2021")
    ap.add_argument("--no-persist", action="store_true")
    ap.add_argument("--rowmatch", action="store_true",
                    help="also score the row-matched champion-vs-proj_lgbm_v1 "
                         "cut on the same bases (identical rows, both models)")
    args = ap.parse_args()
    bases = _parse_bases(args.bases)
    res = run(bases, persist=not args.no_persist)
    print(f"\n==== Multi-horizon WAR-path eval (bases {bases}) — {res['model']} ====")
    print(f"{'h':>2} {'n':>6} {'MAE':>7} {'bias':>7} {'starMAE':>8} {'starBias':>9} "
          f"{'tail p/a':>10} {'ratio':>6} {'cov':>6} {'covSv':>6} {'pin10':>6} {'pin90':>6}")
    for h, s in res["horizons"].items():
        print(f"{h:>2} {s['n']:>6} {s['mae']:>7.3f} {s['bias']:>7.3f} "
              f"{s['mae_star'] if s['mae_star'] is not None else float('nan'):>8.3f} "
              f"{s['bias_star'] if s['bias_star'] is not None else float('nan'):>9.3f} "
              f"{s['tail_pred_ge3']:>4}/{s['tail_act_ge3']:<5} {s['tail_ratio'] or 0:>6.3f} "
              f"{s['coverage'] if s['coverage'] is not None else float('nan'):>6.3f} "
              f"{s['coverage_survived'] if s['coverage_survived'] is not None else float('nan'):>6.3f} "
              f"{s['pinball_q10'] if s['pinball_q10'] is not None else float('nan'):>6.3f} "
              f"{s['pinball_q90'] if s['pinball_q90'] is not None else float('nan'):>6.3f}")
    rm = None
    if args.rowmatch:
        rm = run_rowmatch(bases)
        print(f"\n==== ROW-MATCHED {rm['champion_model']} vs "
              f"{rm['challenger_model']} (bases {bases}, "
              f"n_matched {rm['n_players_matched']}) ====")
        print(f"{'h':>2} {'n':>6} {'cMAE':>7} {'xMAE':>7} {'n*':>4} "
              f"{'cMAE*':>7} {'xMAE*':>7} {'tailAct':>8} {'cRatio':>7} {'xRatio':>7}")
        for h, s in rm["horizons"].items():
            c, x = s["champion"], s["challenger"]
            print(f"{h:>2} {s['n']:>6} {c['mae']:>7.3f} {x['mae']:>7.3f} "
                  f"{c['n_star']:>4} "
                  f"{c['mae_star'] if c['mae_star'] is not None else float('nan'):>7.3f} "
                  f"{x['mae_star'] if x['mae_star'] is not None else float('nan'):>7.3f} "
                  f"{s['tail_act_ge3']:>8} {c['tail_ratio'] or 0:>7.3f} "
                  f"{x['tail_ratio'] or 0:>7.3f}")
    if not args.no_persist:
        # Read-modify-write. run() computes only the champion top-level keys
        # (model/bases/n_players/horizons); the artifact also carries a
        # top-level challenger_blocks owned by other tools (train_proj_models /
        # *_backtest, via setdefault-merge). A verbatim overwrite would destroy
        # those committed governance receipts and empty the /projections/
        # accountability 'Veteran WAR paths' card, so preserve every existing
        # key and update only the ones this run produced (mirrors
        # proj_export._write_team_outlook_eval's retro_backtest preservation).
        path = DATA_DIR / "proj_horizon_eval.json"
        try:
            merged = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            merged = {}
        merged.update(res)
        if rm is not None:
            merged["rowmatch_champion_vs_challenger"] = rm
        # top-level date stamp: the freshness map ages undated artifacts by
        # mtime, which the deploy box's nightly checkout rewrites
        merged["generated_at"] = _utc_stamp()
        path.write_text(json.dumps(merged, indent=1), encoding="utf-8")
        print("wrote data/proj_horizon_eval.json")


if __name__ == "__main__":
    main()

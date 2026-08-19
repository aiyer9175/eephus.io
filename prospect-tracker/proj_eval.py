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
    """(league, by_player, war_actual) from the corpus. war_actual sums WAR
    across sides per (mlbam, season), matching the label the harness scores."""
    league = corpus["league"]
    by_player: dict[str, dict[int, dict[int, dict]]] = {
        "hit": defaultdict(dict), "pit": defaultdict(dict)}
    war_actual: dict[tuple, float] = {}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
                if r.get("war") is not None:
                    key = (r["mlbam"], r["season"])
                    war_actual[key] = war_actual.get(key, 0.0) + r["war"]
    return league, by_player, war_actual


def _pinball(q: float, actual: float, pred_q: float) -> float:
    """Quantile (pinball) loss — the proper scoring rule for a quantile."""
    d = actual - pred_q
    return q * d if d >= 0 else (q - 1.0) * d


def default_predict_fn(hist, side, base, age, curves, war_map, league):
    """The incumbent champion: Marcel year-1 + regressed-rate aging decay
    with Gate-1 quantile bands. use_ml=False PINS the champion — this
    baseline must stay the champion even after an ML bundle ships."""
    return fm.contract_war_path(hist, side, base, HORIZONS, age,
                                curves, war_map, league, use_ml=False)


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
        curves, war_map = fp.fitted_models(corpus, B - 1)
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
        curves, war_map = fp.fitted_models(corpus, B - 1)
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

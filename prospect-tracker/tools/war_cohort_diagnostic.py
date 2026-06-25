# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""WAR-engine per-player, cohort-stratified diagnostic (deferred-queue item).

Generalizes proj_eval's single star-slice to MANY cohort axes: it reuses
proj_eval's EXACT forward-chained, leakage-clean loop (fit/train on labels <=
B-1, score complete seasons only) but tags every (predicted, realized) bWAR pair
with the player's cohort coordinates and aggregates per cohort cell - surfacing
WHERE the WAR engine systematically over/under-predicts.

Cohort axes (reachable from the MLB-only projection corpus): side (hit/pit),
role (SP/RP for pitchers, C/non-C for hitters), age band, base-year WAR tier
(star/solid/fringe/replacement), predicted-WAR bucket, and horizon. NOT reachable
for this engine and documented as such: MiLB level (corpus is MLB-only) + FV tier
(prospect-side, not joined).

Per cell: n, mean_resid (pred-act; +=over-predicts), mae, mean_pred, mean_act,
spearman + calib_slope (n>=50 only), survived_mean_resid (wash-outs excluded).
Cells with n<30 collapse to {n, thin:true} so noise can't masquerade as signal.

Default audits the CHAMPION (marcel_decay_v2, no training, fully leakage-free).
--ml additionally trains a point-in-time proj_lgbm per base (NEVER the live
bundle - that would leak) and audits it alongside, so the diagnostic can locate
which model owns a cohort's miss.

Run:  python tools/war_cohort_diagnostic.py [--bases 2017,2018,2019,2021] [--ml] [--no-persist]
Writes data/war_cohort_eval.json. Measurement-only; verdict hand-committed.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import fa_projection as fp                                    # noqa: E402
import proj_eval                                              # noqa: E402
from source_backtest import _spearman                         # noqa: E402

log = logging.getLogger(__name__)
ARTIFACT = ROOT / "data" / "war_cohort_eval.json"
DEV_BASES = [2017, 2018, 2019, 2021]
HORIZONS = proj_eval.HORIZONS
THIN_N = 30          # cells below this are noise -> reported as a stub only
RANK_MIN_N = 50      # spearman / calibration slope only above this


def _age_band(age):
    if age is None:
        return "unk"
    if age <= 24:
        return "<=24"
    if age <= 29:
        return "25-29"
    if age <= 32:
        return "30-32"
    return "33+"


def _war_tier(w):
    if w is None:
        return "unk"
    if w >= 4.0:
        return "star_4+"
    if w >= 2.0:
        return "solid_2-4"
    if w >= 0.5:
        return "fringe_.5-2"
    return "repl_<.5"


def _pred_bucket(p):
    if p < 0:
        return "neg"
    if p < 1:
        return "0-1"
    if p < 2:
        return "1-2"
    if p < 3:
        return "2-3"
    if p < 4:
        return "3-4"
    return "4+"


def _role_of(side, hist):
    """Most-recent role tag in the player's history. Pitchers: SP/RP. Hitters:
    C vs non-C (the only positional split the corpus carries)."""
    for h in reversed(hist):
        r = h.get("role")
        if r:
            return r
    return "?"


def _cell_metrics(pairs):
    n = len(pairs)
    if n < THIN_N:
        return {"n": n, "thin": True}
    preds = [p for p, _ in pairs]
    acts = [a for _, a in pairs]
    mp = sum(preds) / n
    ma = sum(acts) / n
    mae = sum(abs(p - a) for p, a in pairs) / n
    out = {"n": n, "mean_pred": round(mp, 3), "mean_act": round(ma, 3),
           "mean_resid": round(mp - ma, 3), "mae": round(mae, 3)}
    if n >= RANK_MIN_N:
        out["spearman"] = round(_spearman(preds, acts), 4) if _spearman(preds, acts) is not None else None
        # calibration slope: regress act on pred (slope<1 => over-spread at top)
        var = sum((p - mp) ** 2 for p in preds)
        cov = sum((p - mp) * (a - ma) for p, a in pairs)
        out["calib_slope"] = round(cov / var, 3) if var else None
    return out


def _aggregate(tagged):
    """tagged = list of dicts {pred, act, survived, side, role, age_band,
    war_tier, pred_bucket, h}. Returns the per-axis cohort maps (x horizon)."""
    def by(axis_keys):
        cells = defaultdict(lambda: defaultdict(list))      # key -> h -> pairs
        surv = defaultdict(lambda: defaultdict(list))
        for t in tagged:
            key = axis_keys(t)
            cells[key][t["h"]].append((t["pred"], t["act"]))
            if t["survived"]:
                surv[key][t["h"]].append((t["pred"], t["act"]))
        out = {}
        for key, hmap in cells.items():
            out[key] = {}
            for h, pairs in sorted(hmap.items()):
                m = _cell_metrics(pairs)
                sv = surv[key].get(h, [])
                if len(sv) >= THIN_N:
                    msp = sum(p for p, _ in sv) / len(sv)
                    msa = sum(a for _, a in sv) / len(sv)
                    m["survived_mean_resid"] = round(msp - msa, 3)
                    m["survived_n"] = len(sv)
                out[key][f"h{h}"] = m
        return out
    return {
        "by_pred_bucket": by(lambda t: t["pred_bucket"]),
        "by_age_band": by(lambda t: t["age_band"]),
        "by_role": by(lambda t: f'{t["side"]}:{t["role"]}'),
        "by_base_war_tier": by(lambda t: t["war_tier"]),
        "side_x_war_tier": by(lambda t: f'{t["side"]}:{t["war_tier"]}'),
    }


def _collect(bases, predict_fn):
    """Mirror proj_eval.run's forward-chained loop, tagging each pair w/ cohort."""
    corpus = fp.build_corpus()
    league = corpus["league"]
    by_player = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    war_actual = {}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
                if r.get("war") is not None:
                    k = (r["mlbam"], r["season"])
                    war_actual[k] = war_actual.get(k, 0.0) + r["war"]
    tagged = []
    n_players = 0
    for B in bases:
        curves, war_map = fp.fitted_models(corpus, B - 1)
        for side in ("hit", "pit"):
            for mlbam, seasons in by_player[side].items():
                hist = [seasons[t] for t in (B - 1, B - 2, B - 3) if t in seasons]
                if not hist:
                    continue
                age_prev = next((h.get("age") for h in hist if h.get("age")), None)
                if age_prev is None:
                    continue
                age = age_prev + (B - hist[0]["season"])
                path = predict_fn(hist, side, B, age, curves, war_map, league)
                if path is None:
                    continue
                n_players += 1
                base_actual = war_actual.get((mlbam, B - 1))
                war_tier = _war_tier(base_actual)
                age_band = _age_band(age)
                role = _role_of(side, hist)
                for h in range(1, HORIZONS + 1):
                    target = B + h - 1
                    if target > corpus["last"] - 1:
                        continue
                    pred = path["war_by_year"][h - 1]
                    tagged.append({
                        "pred": pred, "act": war_actual.get((mlbam, target), 0.0),
                        "survived": (mlbam, target) in war_actual,
                        "side": side, "role": role, "age_band": age_band,
                        "war_tier": war_tier, "pred_bucket": _pred_bucket(pred), "h": h,
                    })
    return tagged, n_players


def run(bases=None, with_ml=False, persist=True):
    bases = bases or DEV_BASES
    champ_tagged, champ_n = _collect(bases, proj_eval.default_predict_fn)
    artifact = {
        "generated_at": "",       # stamped by caller / run_monthly (Date.now banned in lib)
        "model": "proj_lgbm_v1 (live engine; champion marcel_decay_v2 audited here)",
        "bases": bases,
        "conventions": {
            "actual": "bWAR (fa_projection corpus); absent target season = 0 on both sides",
            "residual": "mean_resid = mean_pred - mean_act  (POSITIVE = engine over-predicts)",
            "thin_cell_n": THIN_N, "rank_min_n": RANK_MIN_N,
            "protocol": "forward-chained: fit/train on labels <= B-1, score complete seasons only",
            "unreachable_cohorts": "MiLB level (corpus is MLB-only); FV tier (prospect-side, not joined)",
        },
        "champion": {"label": "marcel_decay_v2", "n_players": champ_n,
                     "cohorts": _aggregate(champ_tagged)},
    }
    if with_ml:
        import proj_ml

        def ml_fn(hist, side, base, age, curves, war_map, league):
            models = proj_ml.train_cached(fp.build_corpus(), base - 1)
            feats = proj_ml.build_features(hist, side, base, age, curves, war_map, league)
            if feats is None:
                return None
            return proj_ml.predict_path(models, feats, side)
        ml_tagged, ml_n = _collect(bases, ml_fn)
        artifact["proj_lgbm"] = {"label": "proj_lgbm_v1 (point-in-time per base; NOT the live bundle)",
                                 "n_players": ml_n, "cohorts": _aggregate(ml_tagged)}
    if persist:
        ARTIFACT.write_text(json.dumps(artifact, indent=1), encoding="utf-8")
        log.info("war_cohort_diagnostic: champion n=%d%s -> %s", champ_n,
                 (f", proj_lgbm n={artifact['proj_lgbm']['n_players']}" if with_ml else ""), ARTIFACT.name)
    return artifact


def _print_highlights(artifact):
    for mk in ("champion", "proj_lgbm"):
        if mk not in artifact:
            continue
        print(f"\n=== {mk}: {artifact[mk]['label']}  (n_players={artifact[mk]['n_players']}) ===")
        wt = artifact[mk]["cohorts"]["side_x_war_tier"]
        print("  side x base-WAR-tier  (mean_resid = pred-act; + = over-predicts):")
        for key in sorted(wt):
            row = wt[key]
            cells = " ".join(f"{h}:{c.get('mean_resid', 'thin')}" for h, c in row.items()
                             if not c.get("thin"))
            if cells:
                print(f"    {key:>16}: {cells}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--bases", default="2017,2018,2019,2021")
    ap.add_argument("--ml", action="store_true", help="also audit point-in-time proj_lgbm (slow)")
    ap.add_argument("--no-persist", action="store_true")
    args = ap.parse_args()
    bases = [int(b) for b in args.bases.replace("-", ",").split(",")]
    art = run(bases, with_ml=args.ml, persist=not args.no_persist)
    _print_highlights(art)
    if not args.no_persist:
        print(f"\nwrote {ARTIFACT.name}")


if __name__ == "__main__":
    main()

# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Independent re-measurement of the GLOBAL mean-blend recenter.

data/proj_mean_blend.json was fitted + holdout-confirmed on 2026-06-13 and
the model registry records it as SHIPPED - but the live bundle
model/proj_lgbm/meta.json carries no `mean_blend` key, so
proj_ml.predict_path's recenter has been INERT in production the whole
time (P-MBLEND). Before stamping it back in, re-measure it here from
scratch, forward-chained, on point-in-time bundles this lane trains
itself, so the ship rests on evidence produced now rather than on a
receipt for an artifact that was never deployed.

Protocol (docs/EFV_GATE_STANDARD.md):
  * >= 4 independent time splits: one full-quantile bundle per base,
    trained on labels <= base-1 (no lookahead), scored on base..base+h-1.
  * paired cluster bootstrap over PLAYERS. DISCLOSED DEVIATION: the LGBM
    heads are NOT refit per draw (69s x 4 bases x B draws is not
    affordable), so the reported sd is a TEST-ONLY sd and is inflated by
    the standard's own 1.8x understatement factor before any call.
  * zero-information control: the same lift-only recenter driven by a
    ROW-PERMUTED implied-mean gap (identical marginal shift distribution,
    no information about which row is skewed).
  * permutation null band from that control's draw distribution.

Run: python tools/proj_meanblend_lab.py --bases 2019,2020,2021,2022
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import pickle
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fa_market as fm            # noqa: E402
import fa_projection as fp        # noqa: E402
import proj_ml                    # noqa: E402

log = logging.getLogger("meanblend_lab")
H = proj_ml.HORIZONS


def _bundle(corpus, max_label_season: int, cache_dir: Path):
    import joblib
    p = cache_dir / f"mblab_full_{max_label_season}.joblib"
    if p.exists():
        return joblib.load(p)
    t = time.time()
    m = proj_ml.train(corpus, max_label_season, quantiles=proj_ml.QUANTILES)
    log.info("trained <=%d in %.0fs", max_label_season, time.time() - t)
    joblib.dump(m, p, compress=3)
    return m


def collect(corpus, bases, cache_dir: Path):
    """Per (base, side, player, horizon): the five quantile predictions and
    the actual WAR. Computing the quantiles once lets every recenter
    variant be evaluated as pure arithmetic on the same rows."""
    league = corpus["league"]
    by_player = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    war_actual = fp.war_actual_map(corpus)  # the ONE label (809902c6); never sum r['war'] across sides
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
    rows = []
    for B in bases:
        ck = cache_dir / f"mblab_rows_base{B}.pkl"
        if ck.exists():
            import pickle as _pk
            rows.extend(_pk.load(open(ck, "rb")))
            log.info("base %d loaded from checkpoint (%d rows)", B, len(rows))
            continue
        n0 = len(rows)
        models = _bundle(corpus, B - 1, cache_dir)
        curves, war_map = fp.fitted_models(corpus, B - 1)
        for side in ("hit", "pit"):
            for mlbam, seasons in by_player[side].items():
                hist = [seasons[t] for t in (B - 1, B - 2, B - 3) if t in seasons]
                if not hist:
                    continue
                ar = next((h for h in hist if h.get("age")), None)
                if ar is None:
                    continue
                age = ar["age"] + (B - ar["season"])
                feats = proj_ml.build_features(hist, side, B, age, curves,
                                               war_map, league)
                if feats is None:
                    continue
                x = __import__("numpy").asarray(feats, dtype=float).reshape(1, -1)
                star = feats[proj_ml._STAR_FLAG_IDX] >= 1.0
                for h in range(1, H + 1):
                    target = B + h - 1
                    if target > corpus["last"] - 1:
                        continue
                    heads = models[side].get(h)
                    if not heads:
                        continue
                    qs = sorted(proj_ml._predict1(heads[q], x)
                                for q in proj_ml.QUANTILES)
                    rows.append({"B": B, "side": side, "m": mlbam, "h": h,
                                 "q": qs, "star": bool(star),
                                 "act": war_actual.get((mlbam, target), 0.0)})
        import pickle as _pk
        _pk.dump(rows[n0:], open(ck, "wb"))
        log.info("base %d collected (%d rows so far)", B, len(rows))
    return rows


def point(rows, lam: dict, star_lam: dict | None = None,
          permuted_gap: dict | None = None) -> list[float]:
    """Recentered q50 per row. ``permuted_gap`` maps row index -> a gap
    borrowed from ANOTHER row (the zero-information control)."""
    out = []
    for i, r in enumerate(rows):
        q10, q25, q50, q75, q90 = r["q"]
        v = q50
        gap = (permuted_gap[i] if permuted_gap is not None
               else proj_ml._implied_mean(q10, q25, q50, q75, q90) - q50)
        l = float(lam.get(str(r["h"]), 0.0))
        if l > 0:
            shift = l * gap
            if shift > 0:
                v = v + shift
        if star_lam and r["star"]:
            ls = float(star_lam.get(str(r["h"]), 0.0))
            if ls > 0:
                v = v + ls * (proj_ml._implied_mean(q10, q25, v, q75, q90) - v)
        out.append(v)
    return out


def metrics(rows, preds, sel=None):
    idx = range(len(rows)) if sel is None else sel
    idx = [i for i in idx]
    if not idx:
        return None
    n = len(idx)
    mae = sum(abs(preds[i] - rows[i]["act"]) for i in idx) / n
    bias = sum(preds[i] - rows[i]["act"] for i in idx) / n
    return {"n": n, "mae": mae, "bias": bias}


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--bases", default="2019,2020,2021,2022")
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20260724)
    ap.add_argument("--cache", default=os.environ.get("PROJ_LAB_SCRATCH") or str(ROOT / ".cache"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    bases = [int(b) for b in args.bases.split(",")]
    cache_dir = Path(args.cache); cache_dir.mkdir(parents=True, exist_ok=True)
    corpus = (pickle.load(open(args.corpus, "rb")) if args.corpus
              else fp.build_corpus())

    rows_p = cache_dir / ("mblab_rows_" + "_".join(map(str, bases)) + ".pkl")
    if rows_p.exists():
        rows = pickle.load(open(rows_p, "rb"))
    else:
        rows = collect(corpus, bases, cache_dir)
        pickle.dump(rows, open(rows_p, "wb"))
    log.info("rows %d", len(rows))

    lam = json.loads((ROOT / "data" / "proj_mean_blend.json")
                     .read_text(encoding="utf-8"))["lambda_by_horizon"]
    slam = json.loads((ROOT / "data" / "proj_star_blend.json")
                      .read_text(encoding="utf-8"))["lambda_by_horizon"]
    slam = {str(k): v for k, v in slam.items()}
    lam = {str(k): v for k, v in lam.items()}

    off = point(rows, {}, slam)          # SHIPPED today: star blend only
    on = point(rows, lam, slam)          # with the registered global recenter

    # zero-information control: permute the implied-mean GAP across rows
    # WITHIN (base, side, horizon) so the marginal shift distribution is
    # identical and the row-level information is destroyed.
    gaps = [proj_ml._implied_mean(*r["q"]) - r["q"][2] for r in rows]
    buckets = defaultdict(list)
    for i, r in enumerate(rows):
        buckets[(r["B"], r["side"], r["h"])].append(i)
    rng = random.Random(args.seed)
    perm = list(gaps)
    for key, idxs in buckets.items():
        vals = [gaps[i] for i in idxs]
        rng.shuffle(vals)
        for i, v in zip(idxs, vals):
            perm[i] = v
    ctl = point(rows, lam, slam, permuted_gap=perm)

    res = {"bases": bases, "n_rows": len(rows), "lambda": lam, "star_lambda": slam,
           "disclosed_deviation": "LGBM heads not refit per bootstrap draw; "
                                  "sd is TEST-ONLY and is reported x1.8 per "
                                  "docs/EFV_GATE_STANDARD.md section 2.1",
           "by_horizon": {}, "by_split": {}}
    for h in range(1, H + 1):
        sel = [i for i, r in enumerate(rows) if r["h"] == h]
        if not sel:
            continue
        res["by_horizon"][h] = {
            "off": {k: round(v, 5) for k, v in metrics(rows, off, sel).items()},
            "on": {k: round(v, 5) for k, v in metrics(rows, on, sel).items()},
            "control": {k: round(v, 5) for k, v in metrics(rows, ctl, sel).items()},
        }
        for side in ("hit", "pit"):
            s2 = [i for i in sel if rows[i]["side"] == side]
            if s2:
                res["by_horizon"][h][side] = {
                    "off": {k: round(v, 5) for k, v in metrics(rows, off, s2).items()},
                    "on": {k: round(v, 5) for k, v in metrics(rows, on, s2).items()}}
        s3 = [i for i in sel if rows[i]["star"]]
        if s3:
            res["by_horizon"][h]["star"] = {
                "off": {k: round(v, 5) for k, v in metrics(rows, off, s3).items()},
                "on": {k: round(v, 5) for k, v in metrics(rows, on, s3).items()}}
    for B in bases:
        blk = {}
        for h in range(1, H + 1):
            sel = [i for i, r in enumerate(rows) if r["B"] == B and r["h"] == h]
            if not sel:
                continue
            mo = metrics(rows, off, sel); mn = metrics(rows, on, sel)
            blk[h] = {"n": mo["n"], "d_mae": round(mn["mae"] - mo["mae"], 5),
                      "d_absbias": round(abs(mn["bias"]) - abs(mo["bias"]), 5)}
        res["by_split"][B] = blk

    # ---- paired cluster bootstrap over players ------------------------------
    players = sorted({r["m"] for r in rows})
    by_pl = defaultdict(list)
    for i, r in enumerate(rows):
        by_pl[r["m"]].append(i)
    rng2 = random.Random(args.seed + 1)
    draws = defaultdict(list)
    for _ in range(args.draws):
        pick = [players[rng2.randrange(len(players))] for _ in range(len(players))]
        idx_all = [i for p in pick for i in by_pl[p]]
        by_h = defaultdict(list)
        for i in idx_all:
            by_h[rows[i]["h"]].append(i)
        for h, sel in by_h.items():
            mo = metrics(rows, off, sel); mn = metrics(rows, on, sel)
            mc = metrics(rows, ctl, sel)
            draws[f"h{h}:d_mae"].append(mn["mae"] - mo["mae"])
            draws[f"h{h}:d_absbias"].append(abs(mn["bias"]) - abs(mo["bias"]))
            draws[f"h{h}:ctl_d_mae"].append(mc["mae"] - mo["mae"])
            draws[f"h{h}:ctl_d_absbias"].append(abs(mc["bias"]) - abs(mo["bias"]))
    boot = {}
    for k, v in draws.items():
        v = sorted(v); n = len(v); mu = sum(v) / n
        sd = (sum((x - mu) ** 2 for x in v) / max(n - 1, 1)) ** 0.5
        boot[k] = {"mean": round(mu, 5),
                   "ci95": [round(v[int(0.025 * (n - 1))], 5),
                            round(v[int(0.975 * (n - 1))], 5)],
                   "sd_test_only": round(sd, 5),
                   "mde95_inflated_1p8x": round(1.96 * sd * 1.8, 5)}
    res["bootstrap"] = boot
    out = json.dumps(res, indent=1)
    print(out)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()

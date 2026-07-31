# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""SWEEP LANE calibration -- (b) population-conditional calibration, gated.

Same paired bootstrap (resample train AND test, refit per draw) + zero-information
control (row-permuted grade twin) + permutation null (row-permuted outcome) as the
main gate, applied to the LEVEL / AGE-BAND / ACQUISITION slices.

Writes data/xfv_level_calibration_slices.json.
"""
from __future__ import annotations
import json, statistics, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import importlib.util as _ilu        # noqa: E402
_spec = _ilu.spec_from_file_location("_sweep_calib_gate", str(HERE / "_sweep_calib_gate.py"))
G = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(G)
import efv_model as M                # noqa: E402

B = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
ART = ROOT / "data" / "xfv_level_calibration_slices.json"
LEVELS = ("A", "A+", "AA", "AAA")
AGEB = ("<19", "19-20", "21-22", "23-24", "25+")
ACQ = ("IFA", "college", "HS", "unknown")


def ageband(a):
    if a is None:
        return None
    a = float(a)
    return "<19" if a < 19 else "19-20" if a < 21 else "21-22" if a < 23 else "23-24" if a < 25 else "25+"


def slice_stats(scored):
    s = {}
    for name, keyfn, vals in (("level", lambda r: r["level"], LEVELS),
                              ("age", lambda r: ageband(r["age"]), AGEB),
                              ("acq", lambda r: r["acq"], ACQ)):
        by = defaultdict(list)
        for r in scored:
            k = keyfn(r)
            if k in vals:
                by[k].append(r)
        for v in vals:
            g = by.get(v) or []
            if len(g) < 8:
                s[f"{name}_{v}_bias"] = None
                s[f"{name}_{v}_cov"] = None
                s[f"{name}_{v}_pbustgap"] = None
                s[f"{name}_{v}_n"] = len(g)
                continue
            s[f"{name}_{v}_n"] = len(g)
            s[f"{name}_{v}_bias"] = statistics.mean(r["war"] - G._implied(r["g_disp"]) for r in g)
            cov = []
            for r in g:
                q10, q90 = G._war_band(r["g_disp"], r.get("_is_pit", False))
                cov.append(1 if q10 <= r["war"] <= q90 else 0)
            s[f"{name}_{v}_cov"] = statistics.mean(cov)
            s[f"{name}_{v}_pbustgap"] = (
                statistics.mean(G._pb(r["g_raw"], r.get("_is_pit", False))[0] for r in g)
                - sum(1 for r in g if r["war"] < G.BUST_SUM) / len(g))
    return s


def run_once(data_by_side, lams, keys, permute_grade=False, permute_war=False, rng=None,
             only_milb=True):
    out = {}
    for side in ("hit", "pit"):
        sc = G.score_folds(data_by_side[side], side, lams[side], keys[side],
                           permute_grade=permute_grade, permute_war=permute_war, rng=rng)
        for r in sc:
            r["_is_pit"] = side == "pit"
        if only_milb:
            sc = [r for r in sc if r["has_milb"]]
        out[side] = slice_stats(sc)
    return out


def main():
    import random
    lams, lam_src = M._sf_live_lambdas()
    data = {s: G.load_side(s) for s in ("hit", "pit")}
    keys = {s: M._feature_spec(s)[0] for s in ("hit", "pit")}
    point = run_once(data, lams, keys)
    per_fold = {}
    for side in ("hit", "pit"):
        per_fold[side] = {}
        for yr in G.FOLDS:
            sc = G.score_folds(data[side], side, lams[side], keys[side], folds=(yr,))
            for r in sc:
                r["_is_pit"] = side == "pit"
            per_fold[side][str(yr)] = slice_stats([r for r in sc if r["has_milb"]])
    rng = random.Random(G.SEED)
    npr = np.random.RandomState(G.SEED)
    draws = {s: defaultdict(list) for s in ("hit", "pit")}
    ctrl = {s: defaultdict(list) for s in ("hit", "pit")}
    perm = {s: defaultdict(list) for s in ("hit", "pit")}
    for it in range(B):
        boot = {}
        for side in ("hit", "pit"):
            d = data[side]
            idx = npr.randint(0, len(d), len(d))
            boot[side] = [d[i] for i in idx]
        r1 = run_once(boot, lams, keys)
        r2 = run_once(boot, lams, keys, permute_grade=True, rng=rng)
        r3 = run_once(boot, lams, keys, permute_war=True, rng=rng)
        for side in ("hit", "pit"):
            for k, v in r1[side].items():
                draws[side][k].append(v)
            for k, v in r2[side].items():
                ctrl[side][k].append(v)
            for k, v in r3[side].items():
                perm[side][k].append(v)
        if (it + 1) % 100 == 0:
            print(f"  slice boot {it+1}/{B}", flush=True)
    art = {
        "generated_at": __import__("datetime").date.today().isoformat(),
        "lane": "calibration -- population-conditional level calibration",
        "scope": ("LIVE-COMPARABLE rows only (a MiLB track record present), the population "
                  "the served board actually contains -- xfv.json meta: eFV abstains on "
                  "players with no MiLB production"),
        "folds": list(G.FOLDS), "lambda": lams, "lambda_source": lam_src,
        "bust_threshold": G.BUST_SUM,
        "bootstrap": {"B": B, "seed": G.SEED,
                      "scheme": "resample whole side pool (train AND test), refit per draw"},
        "point": point, "per_fold": per_fold,
        "boot_ci95": {s: {k: G._ci(v) for k, v in draws[s].items()} for s in ("hit", "pit")},
        "zero_info_control_permuted_grade_ci95": {
            s: {k: G._ci(v) for k, v in ctrl[s].items()} for s in ("hit", "pit")},
        "permutation_null_permuted_outcome_ci95": {
            s: {k: G._ci(v) for k, v in perm[s].items()} for s in ("hit", "pit")},
    }
    ART.write_text(json.dumps(art, indent=1), encoding="utf-8")
    print("wrote", ART)


if __name__ == "__main__":
    main()

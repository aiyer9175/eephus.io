# B4+B5 experiment driver (docs/efv-sb-athleticism-2026-08-05/PREREG.md).
# Reuses the SHIPPED efv_lab_runner protocol; the three declared deviations
# (feats augmentation, in-memory sb_rate_rel recompute, MAE collection) are in
# PREREG.md section 5, each with an equivalence check enforced here.
# NOT a pytest module; run: python docs/efv-sb-athleticism-2026-08-05/run_lab.py
from __future__ import annotations

import json
import math
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import os

os.chdir(ROOT)

import efv_dataset as DS
import efv_lab_runner as LAB
from efv_model import _feature_spec, _fit_ols_fv, _pred_ols, blend_lambda
from prospect_path import _fit_ridge, _predict, _spearman

SEED = 20260805

# Pre-registered pool z constants (PREREG.md section 3).
TOOL_Z = {
    "tool_speed": (47.79, 12.23),
    "tool_field": (51.00, 6.58),
    "tool_throw": (53.96, 7.12),
}


def augment():
    """Deviations 1+2: recompute sb_rate_rel via the production code path and
    attach the raw-tool z composites + permuted controls to the runner's own
    cached rows. Returns (rows, report_dict)."""
    rows = LAB.data_for("hit")
    matrix = {r["player_key"]: r
              for r in json.loads(DS.matrix_path("hit").read_text(encoding="utf-8"))
              if r["kind"] == "debuted"}
    checked = mismatch = 0
    sb_vals = []
    raw = {}
    t0 = time.time()
    for r in rows:
        m = matrix[r["player_key"]]
        blk = None
        if m.get("mlbam_id"):
            blk = DS._milb_features(m["mlbam_id"], m["debut_year"],
                                    m.get("birth_date"), "hit",
                                    cutoff=m.get("cutoff"))
        stored = m.get("milb")
        if stored and blk:
            checked += 1
            for k in ("k_rel", "obp_rel", "level_rank"):
                if abs((blk.get(k) or 0.0) - (stored.get(k) or 0.0)) > 1e-9:
                    mismatch += 1
                    break
        sb = float(blk.get("sb_rate_rel", 0.0)) if blk else None
        raw[r["player_key"]] = {"sb": sb,
                                "tools": {k: m.get(k) for k in TOOL_Z}}
        if sb is not None:
            sb_vals.append(sb)
    recompute_s = time.time() - t0
    sb_mu = statistics.mean(sb_vals)
    sb_sd = statistics.pstdev(sb_vals)

    def z_tool(v, key):
        mu, sd = TOOL_Z[key]
        return (float(v) - mu) / sd if v is not None else 0.0

    def z_sb(v):
        return (v - sb_mu) / sb_sd if v is not None else 0.0

    for r in rows:
        d = raw[r["player_key"]]
        zs = z_tool(d["tools"]["tool_speed"], "tool_speed")
        zf = z_tool(d["tools"]["tool_field"], "tool_field")
        zt = z_tool(d["tools"]["tool_throw"], "tool_throw")
        zb = z_sb(d["sb"])
        f = r["feats"]
        f["sb_rate_rel"] = d["sb"] if d["sb"] is not None else 0.0
        f["spd_sb_50"] = 0.5 * zs + 0.5 * zb
        f["spd_sb_70"] = 0.7 * zs + 0.3 * zb
        f["athl3"] = (zs + zf + zt) / 3.0
        f["athl_sf"] = (zs + zf) / 2.0
        f["athl_st"] = (zs + zt) / 2.0

    # Zero-information controls: each candidate column row-permuted, kept in set.
    import numpy as np
    rng = np.random.default_rng(SEED)
    cols = ["sb_rate_rel", "spd_sb_50", "spd_sb_70", "athl3", "athl_sf", "athl_st"]
    perm = rng.permutation(len(rows))
    for c in cols:
        vals = [rows[i]["feats"][c] for i in range(len(rows))]
        for i, r in enumerate(rows):
            r["feats"][f"{c}__perm"] = vals[perm[i]]

    return rows, {
        "n_rows": len(rows), "milb_recompute_checked": checked,
        "milb_recompute_mismatch": mismatch,
        "milb_recompute_wallclock_s": round(recompute_s, 1),
        "sb_observed_n": len(sb_vals),
        "sb_mu": round(sb_mu, 4), "sb_sd": round(sb_sd, 4),
    }


def run_variant_ext(v):
    """Deviation 3: line-copy of efv_lab_runner.run_variant with pooled +
    per-fold MAE added. No fitting logic changed."""
    side = v.get("side", "hit")
    target = v.get("target", "censored")
    tkey = {"censored": "target_censored", "resolved": "target_resolved",
            "war_per_year": "wpy"}[target]
    extra_keys = v.get("extra_keys") or []
    cohort = v.get("cohort")
    keys = _feature_spec(side)[0] + extra_keys

    rows = [r for r in LAB.data_for(side) if r.get(tkey) is not None]
    if cohort:
        rows = [r for r in rows if r["cohort"] == cohort]
    base_lam = blend_lambda(side)

    pooled, per_year = [], defaultdict(list)
    for yr in LAB.SCORED_YEARS:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        trf = [{"feats": r["feats"], "target": r[tkey], "weight": r["weight"],
                "fv": r["fv"]} for r in tr]
        olst = [{"fv": r["fv"], "target": r[tkey]} for r in tr]
        ols = _fit_ols_fv(olst)
        ridge = _fit_ridge(trf, keys)
        if not (ols and ridge):
            continue
        for r in te:
            rp = _predict(ridge, r["feats"])
            cw = max(0.0, _pred_ols(ols, r["fv"]))
            blend = (1 - base_lam) * cw + base_lam * rp
            pooled.append((blend, r[tkey], r["fv"], r["cohort"], r["weight"]))
            per_year[yr].append((blend, r[tkey]))

    if len(pooled) < 30:
        return {"id": v.get("id"), "n": len(pooled), "error": "too few rows"}

    sp = _spearman([a for a, *_ in pooled], [b for _, b, *_ in pooled])
    mae = sum(abs(a - b) for a, b, *_ in pooled) / len(pooled)
    wsum = sum(w for *_, w in pooled)
    wmae = sum(w * abs(a - b) for a, b, _, _, w in pooled) / wsum
    pyr_rho = {yr: _spearman([a for a, _ in g], [b for _, b in g])
               for yr, g in per_year.items() if len(g) >= 12}
    pyr_mae = {yr: round(sum(abs(a - b) for a, b in g) / len(g), 4)
               for yr, g in per_year.items()}
    byt = defaultdict(list)
    for pr, t, fv, *_ in pooled:
        byt[round(fv / 5) * 5].append((pr, t))
    ws = wn = 0
    t45 = None
    for tk, grp in byt.items():
        if len(grp) < 15:
            continue
        rho = _spearman([a for a, _ in grp], [b for _, b in grp])
        if rho is None:
            continue
        ws += rho * len(grp)
        wn += len(grp)
        if tk == 45:
            t45 = round(rho, 4)
    return {"id": v.get("id"), "n": len(pooled),
            "spearman": round(sp, 4), "mae": round(mae, 4),
            "wmae": round(wmae, 4),
            "within_tier_wm": round(ws / wn, 4) if wn else None, "t45": t45,
            "per_year_rho": {y: (None if r is None else round(r, 4))
                             for y, r in pyr_rho.items()},
            "per_year_mae": pyr_mae}


VARIANTS = [
    ("b4_sb", ["sb_rate_rel"]),
    ("b4_blend50", ["spd_sb_50"]),
    ("b4_blend70", ["spd_sb_70"]),
    ("b5_athl3", ["athl3"]),
    ("b5_sf", ["athl_sf"]),
    ("b5_st", ["athl_st"]),
]


def main():
    out = {"seed": SEED, "prereg": "PREREG.md", "runs": {}}
    t0 = time.time()
    rows, aug = augment()
    out["augment"] = aug
    assert aug["milb_recompute_mismatch"] <= 0.01 * max(1, aug["milb_recompute_checked"]), \
        "recompute equivalence check failed (>1% mismatch): blocked per PREREG 5.2"

    # Equivalence check 5.1: stock runner baseline vs extended baseline.
    t = time.time()
    stock = LAB.run_variant({"id": "STOCK_BASELINE", "side": "hit"})
    out["runs"]["stock_baseline"] = {"spearman": stock["spearman"],
                                     "wallclock_s": round(time.time() - t, 1)}
    t = time.time()
    base = run_variant_ext({"id": "BASELINE", "side": "hit"})
    base["wallclock_s"] = round(time.time() - t, 1)
    out["runs"]["baseline"] = base
    assert base["spearman"] == stock["spearman"], \
        f"driver baseline {base['spearman']} != stock runner {stock['spearman']}"

    for vid, cols in VARIANTS:
        for suffix in ("", "__perm"):
            rid = vid + ("_CTRL" if suffix else "")
            t = time.time()
            res = run_variant_ext({"id": rid, "side": "hit",
                                   "extra_keys": [c + suffix for c in cols]})
            res["wallclock_s"] = round(time.time() - t, 1)
            res["margin_rho"] = round(res["spearman"] - base["spearman"], 4)
            res["margin_mae"] = round(base["mae"] - res["mae"], 4)
            res["fold_rho_wins"] = sum(
                1 for y, r in res["per_year_rho"].items()
                if r is not None and base["per_year_rho"].get(y) is not None
                and r > base["per_year_rho"][y])
            out["runs"][rid] = res

    out["total_wallclock_s"] = round(time.time() - t0, 1)
    (HERE / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()

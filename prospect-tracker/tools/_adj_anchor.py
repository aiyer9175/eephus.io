"""ADJUDICATION probe: the FV -> 6yr-avg-WAR ANCHOR is fit on RAW cross-source FV.

value_framework.py:635-636 serves `_fitted()["empirical_anchors"]["anchors"]` whenever
anchor_calibration.use_empirical is true (it is). Those anchors come from
empirical_anchors._cohort, which does

    SELECT player_key, fv, position FROM snapshots WHERE snapshot_date BETWEEN ...

and pools by plain MEAN across every source and every snapshot in the window: no
grade normalization, no alias dedupe, no source weights. Production then evaluates
that curve at the GRADE-NORMALIZED consensus. This probe re-derives the anchors on
the SAME cohort with the SAME policy, once on the raw FV the module actually uses and
once with each snapshot's FV pushed through the shipped remapper, and reports the gap.

Read-only. Writes nothing.
"""
from __future__ import annotations
import json
import sqlite3
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import empirical_anchors as ea  # noqa: E402
import value_framework as vf  # noqa: E402
import consensus as C  # noqa: E402
from grade_normalization import build_remapper  # noqa: E402

DB = ROOT / "prospects.db"
remap = build_remapper(aliases=getattr(C, "SOURCE_ALIASES", None))


def cohort(y0, y1, normalize: bool):
    con = sqlite3.connect(str(DB))
    fvs = defaultdict(list)
    pos = defaultdict(list)
    try:
        q = ("SELECT player_key, fv, position, source, snapshot_date FROM snapshots "
             "WHERE snapshot_date BETWEEN ? AND ? AND fv IS NOT NULL")
        for k, fv, p, src, d in con.execute(q, (f"{y0}-01-01", f"{y1}-12-31")):
            v = float(fv)
            if normalize:
                nv = remap(v, src, p, int(str(d)[:4]))
                if nv is not None:
                    v = float(nv)
            fvs[k].append(v)
            pos[k].append((p or "").upper())
        war = {}
        for k, pj in con.execute("SELECT player_key, payload_json FROM career_war"):
            seasons = sorted((int(y), float(w))
                             for y, w in (json.loads(pj).get("seasons") or {}).items())
            war[k] = sum(w for _, w in seasons[:6])
    finally:
        con.close()
    return {k: {"fv": st.mean(v), "is_pit": ea._is_pitcher_positions(pos[k]),
                "realized_war": war.get(k, 0.0)} for k, v in fvs.items()}


def anchors_from(coh, policy):
    tiers = [int(t) for t in policy["tiers"]]
    ref = {int(k): float(v) for k, v in policy["public_reference"].items()}
    min_n = int(policy["min_n_robust"])
    w_base = float(policy["blend_weight_public"])
    w_thin = float(policy["blend_thin_extra"])
    by = defaultdict(list)
    for r in coh.values():
        by[int(round(r["fv"] / 5) * 5)].append(r["realized_war"] / 6.0)
    out, diag = {}, {}
    for t in tiers:
        ws = by.get(t, [])
        n = len(ws)
        rt = ref.get(t) or max((ref[k] for k in ref if k <= t), default=0.0)
        if n == 0:
            out[t] = rt
            diag[t] = {"n": 0, "emp": None, "w_pub": 1.0}
            continue
        emp = st.mean(ws)
        w = w_base + (w_thin * max(0.0, 1.0 - n / min_n))
        w = min(1.0, w)
        out[t] = round((1 - w) * emp + w * rt, 3)
        diag[t] = {"n": n, "emp": round(emp, 3), "w_pub": round(w, 2)}
    return out, diag


if __name__ == "__main__":
    pol = vf._config()["anchor_calibration"]
    y0, y1 = 2026 - int(pol["resolved_lag_max"]), 2026 - int(pol["resolved_lag_min"])
    print(f"cohort window [{y0}, {y1}]  (the shipped fitted file says "
          f"{json.loads((ROOT/'data'/'value_framework_fitted.json').read_text())['empirical_anchors']['cohort_window']})")
    raw = cohort(y0, y1, normalize=False)
    nrm = cohort(y0, y1, normalize=True)
    print(f"n_cohort raw {len(raw)}  normalized {len(nrm)}")
    dmean = st.mean(nrm[k]["fv"] - raw[k]["fv"] for k in raw)
    print(f"mean per-player FV shift (normalized - raw): {dmean:+.3f}")
    moved = sum(1 for k in raw
                if int(round(nrm[k]["fv"] / 5) * 5) != int(round(raw[k]["fv"] / 5) * 5))
    print(f"players whose ANCHOR TIER changes: {moved} of {len(raw)} = {moved/len(raw):.2%}")
    a_raw, d_raw = anchors_from(raw, pol)
    a_nrm, d_nrm = anchors_from(nrm, pol)
    shipped = json.loads((ROOT / "data" / "value_framework_fitted.json").read_text(
        encoding="utf-8"))["empirical_anchors"]["anchors"]
    print("\ntier | shipped | re-derived RAW (n, emp) | re-derived NORMALIZED (n, emp)")
    for t in sorted(a_raw):
        print(f" {t:3d} | {float(shipped.get(str(t), float('nan'))):7.3f} | "
              f"{a_raw[t]:7.3f} (n={d_raw[t]['n']:5d}, emp={d_raw[t]['emp']}) | "
              f"{a_nrm[t]:7.3f} (n={d_nrm[t]['n']:5d}, emp={d_nrm[t]['emp']})")

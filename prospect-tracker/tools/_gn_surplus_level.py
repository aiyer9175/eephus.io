# SCRATCH LAB (lane: blastradius) -- Step 3: what the LEVEL shift does to eFV surplus $.
#
# Mechanism under test (read from efv_score.run_live): the served headline
# `xfv_grade_display` is a rank-preserving quantile map of the eFV ranking onto
# `target = sorted(consensus_fv of the live pool)`. Surplus dollars are then priced
# on that DISPLAYED grade (_reprice_surplus_on_display -> vf.expected_surplus_usd
# -> vf.apply_calibration). So a LEVEL shift in consensus FV moves every served
# grade and every served surplus dollar, even though the eFV ORDER is untouched.
#
# This isolates CHANNEL 1 (level/shape of the target distribution). The eFV ORDER
# is held fixed at the shipped ranking, so any reordering from the changed `fv`
# feature is NOT included here and is reported separately.
import json
import os
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))
os.chdir(_HERE)
OUT = _HERE / "data" / "_gn_lab"

modes = json.loads((OUT / "consensus_modes.json").read_text(encoding="utf-8"))
new, old = modes["new"], modes["old"]

import efv_score as es              # noqa: E402
import value_framework as vf        # noqa: E402


def _disp_map(order_keys, target):
    """Replicate efv_score.run_live's smooth quantile map exactly."""
    m = len(order_keys)
    out = {}
    for rank_pos, k in enumerate(order_keys):
        p = (rank_pos / (m - 1)) if m > 1 else 0.0
        pos = p * (m - 1)
        lo = int(pos); hi = min(m - 1, lo + 1); frac = pos - lo
        out[k] = target[lo] * (1 - frac) + target[hi] * frac
    return out


def run_side(side):
    is_pit = side == "pit"
    fn = "xfv_scored_live_pitcher.json" if is_pit else "xfv_scored_live.json"
    rows = json.loads((_HERE / "data" / fn).read_text(encoding="utf-8"))
    mx = json.loads((_HERE / "data" /
                     f"xfv_live_{'pitcher' if is_pit else 'hitter'}_matrix.json"
                     ).read_text(encoding="utf-8"))
    mrows = mx if isinstance(mx, list) else (mx.get("rows") or [])
    ctx = {r["player_key"]: (r.get("age_now"), r.get("eta_years")) for r in mrows}

    rows = [r for r in rows if r.get("consensus_fv") is not None
            and r.get("rank_war") is not None and r["player_key"] in new
            and new[r["player_key"]][1] is not None and old[r["player_key"]][1] is not None]
    keys = [r["player_key"] for r in rows]
    by = {r["player_key"]: r for r in rows}

    # Served consensus_fv is the NEW scale (verified in _gn_trainserve).
    cfv_new = {k: float(by[k]["consensus_fv"]) for k in keys}
    delta = {k: old[k][1] - new[k][1] for k in keys}          # what OLD would have been
    cfv_old = {k: cfv_new[k] + delta[k] for k in keys}

    order = sorted(keys, key=lambda k: (by[k]["rank_war"], k))   # eFV order HELD FIXED
    d_new = _disp_map(order, sorted(cfv_new.values()))
    d_old = _disp_map(order, sorted(cfv_old.values()))

    gd = np.array([round(d_new[k], 1) - round(d_old[k], 1) for k in keys])
    print(f"\n=== {side} live pool n={len(keys)} ===")
    print(f"displayed-grade delta (new - old): mean {gd.mean():+.3f}  median "
          f"{np.median(gd):+.3f}  p05 {np.percentile(gd,5):+.2f}  p95 "
          f"{np.percentile(gd,95):+.2f}  min {gd.min():+.2f}  max {gd.max():+.2f}")
    print(f"  players whose DISPLAYED grade moves: "
          f"{int((np.abs(gd)>0.05).sum())} ({100*(np.abs(gd)>0.05).mean():.1f}%)")

    ds, dn_, rel = [], [], []
    for k in keys:
        age, eta = ctx.get(k, (None, None))
        if eta is None:
            eta = es.PROSPECT_ETA_FALLBACK_YEARS
        pos = by[k].get("position")
        out = {}
        for lbl, g in (("new", round(d_new[k], 1)), ("old", round(d_old[k], 1))):
            kw = {}
            if age is not None:
                kw["age"] = age
            kw["eta_years"] = eta
            sq = vf.expected_surplus_usd(g, is_pit, pos, **kw)
            out[lbl] = None if sq is None else es._cal_mm(sq / 1e6, g, is_pit)
        if out["new"] is None or out["old"] is None:
            continue
        ds.append(out["new"] - out["old"])
        dn_.append(out["new"])
        if abs(out["old"]) > 1e-9:
            rel.append((out["new"] - out["old"]) / abs(out["old"]))
    ds, dn_ = np.array(ds), np.array(dn_)
    print(f"  surplus delta $M/prospect: mean {ds.mean():+.3f}  median "
          f"{np.median(ds):+.3f}  p05 {np.percentile(ds,5):+.2f}  p95 "
          f"{np.percentile(ds,95):+.2f}  min {ds.min():+.2f}  max {ds.max():+.2f}")
    print(f"  TOTAL board surplus: new ${dn_.sum():,.0f}M  "
          f"old ${(dn_-ds).sum():,.0f}M  delta ${ds.sum():,.0f}M "
          f"({100*ds.sum()/max(1e-9,(dn_-ds).sum()):+.2f}%)")
    top = sorted(keys, key=lambda k: -d_new[k])[:10]
    print("  top-10 by displayed grade (grade old->new, surplus $M old->new):")
    for k in top:
        age, eta = ctx.get(k, (None, es.PROSPECT_ETA_FALLBACK_YEARS))
        eta = eta if eta is not None else es.PROSPECT_ETA_FALLBACK_YEARS
        pos = by[k].get("position")
        vals = {}
        for lbl, g in (("new", round(d_new[k], 1)), ("old", round(d_old[k], 1))):
            kw = {"eta_years": eta}
            if age is not None:
                kw["age"] = age
            sq = vf.expected_surplus_usd(g, is_pit, pos, **kw)
            vals[lbl] = None if sq is None else es._cal_mm(sq / 1e6, g, is_pit)
        print(f"    {k:26s} {round(d_old[k],1):5.1f} -> {round(d_new[k],1):5.1f}   "
              f"${vals['old']:8.1f}M -> ${vals['new']:8.1f}M")
    return ds


allds = []
for s in ("hit", "pit"):
    allds.append(run_side(s))
allds = np.concatenate(allds)
print(f"\nBOTH SIDES: n={len(allds)} mean surplus delta {allds.mean():+.3f} $M/prospect, "
      f"total {allds.sum():+,.0f} $M")

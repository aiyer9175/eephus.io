"""Scratch lab: archetype AXIS CENSUS + DSL-encoding defect quantification.

Read-only. Does not import or mutate any shipped artifact.
Run:  python tools/_arch_axes.py <cmd>
"""
from __future__ import annotations
import json, math, sys, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

import efv_model as EM  # noqa: E402


def _load(p):
    return json.loads((DATA / p).read_text(encoding="utf-8"))


def pools(side="hit"):
    """Return (fit_rows, served_rows) exactly as production defines them."""
    mp = "xfv_hitter_matrix.json" if side == "hit" else "xfv_pitcher_matrix.json"
    lp = "xfv_live_hitter_matrix.json" if side == "hit" else "xfv_live_pitcher_matrix.json"
    is_pit = side == "pit"
    rows = _load(mp)
    # efv_model.fit_production_stack pool filter + _prep drops
    fit = [r for r in rows
           if bool(r.get("is_pitcher")) == is_pit
           and not (r.get("kind") == "bust" and r.get("bust_recent"))
           and r.get("target_censored") is not None
           and r.get("consensus_fv_raw") is not None]
    live = _load(lp)
    # efv_score.run_live gate: needs a float consensus + a milb block
    served = []
    for r in live:
        try:
            float(r.get("consensus_fv_raw"))
        except (TypeError, ValueError):
            continue
        if not r.get("milb"):
            continue
        served.append(r)
    return fit, served


def moments(vals):
    n = len(vals)
    if n == 0:
        return (0, None, None)
    mu = sum(vals) / n
    sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / n)
    return (n, mu, sd)


def cmd_defect(side="hit"):
    fit, served = pools(side)
    keys, _ = EM._feature_spec(side)
    tr = [r for r in fit if r.get("milb")]
    nom = [r for r in fit if not r.get("milb")]
    print(f"== side={side}  FIT n={len(fit)}  track-record n={len(tr)}  "
          f"NO-MiLB n={len(nom)} ({100*len(nom)/len(fit):.2f}%)")
    print(f"   of the no-MiLB rows, milb_unavailable={sum(1 for r in nom if r.get('milb_unavailable'))}")
    print(f"   SERVED n={len(served)} (100% track-record by construction)")
    vf = {k: [] for k in keys}
    vt = {k: [] for k in keys}
    vs = {k: [] for k in keys}
    for r in fit:
        f = EM._vec(r, side)
        for k in keys:
            vf[k].append(f[k])
    for r in tr:
        f = EM._vec(r, side)
        for k in keys:
            vt[k].append(f[k])
    for r in served:
        f = EM._vec(r, side)
        for k in keys:
            vs[k].append(f[k])
    hdr = (f"{'feature':16s} {'FITmu':>9s} {'FITsd':>8s} {'TRmu':>9s} {'TRsd':>8s} "
           f"{'SRVmu':>9s} {'SRVsd':>8s} {'z(SRVmu|FIT)':>13s} {'z(SRVmu|TR)':>12s} {'dz':>7s}")
    print(hdr)
    out = {}
    for k in keys:
        nF, muF, sdF = moments(vf[k])
        nT, muT, sdT = moments(vt[k])
        nS, muS, sdS = moments(vs[k])
        zF = (muS - muF) / sdF if sdF else 0.0
        zT = (muS - muT) / sdT if sdT else 0.0
        print(f"{k:16s} {muF:9.4f} {sdF:8.4f} {muT:9.4f} {sdT:8.4f} {muS:9.4f} {sdS:8.4f} "
              f"{zF:13.3f} {zT:12.3f} {zF-zT:7.3f}")
        out[k] = dict(muF=muF, sdF=sdF, muT=muT, sdT=sdT, muS=muS, sdS=sdS, zF=zF, zT=zT)
    return out


def cmd_player(name_sub, side="hit"):
    """z of one served player's features under FIT vs TRACK-RECORD standardization."""
    fit, served = pools(side)
    keys, _ = EM._feature_spec(side)
    tr = [r for r in fit if r.get("milb")]
    hits = [r for r in served if name_sub.lower() in (r.get("player_key") or "").lower()]
    if not hits:
        print("no served row matching", name_sub)
        return
    for r in hits:
        f = EM._vec(r, side)
        print("=== ", r["player_key"], "cons", r.get("consensus_fv_raw"),
              "lvl", (r.get("milb") or {}).get("milb_level"),
              "age", (r.get("milb") or {}).get("age"))
        print(f"{'feature':16s} {'raw':>9s} {'z_FIT':>8s} {'z_TR':>8s} {'delta':>8s}")
        for k in keys:
            nF, muF, sdF = moments([EM._vec(x, side)[k] for x in fit])
            nT, muT, sdT = moments([EM._vec(x, side)[k] for x in tr])
            zF = (f[k] - muF) / sdF if sdF else 0.0
            zT = (f[k] - muT) / sdT if sdT else 0.0
            print(f"{k:16s} {f[k]:9.4f} {zF:8.3f} {zT:8.3f} {zF-zT:8.3f}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "defect"
    if cmd == "defect":
        cmd_defect(sys.argv[2] if len(sys.argv) > 2 else "hit")
    elif cmd == "player":
        cmd_player(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "hit")

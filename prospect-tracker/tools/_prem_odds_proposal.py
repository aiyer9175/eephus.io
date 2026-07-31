# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""ODDS LANE: the PROPOSAL, gated, plus its live served impact.

DIAGNOSIS. vf.p_bucket_given_fv is a curve fitted over the CONSENSUS-FV published-list
population (sd of consensus_fv_raw on the served-comparable frame = 6.57 FV). Production
reads it at xfv_grade = vf.realized_implied_fv(...), a WAR-inversion grade whose sd on the
same rows is 15.54 FV -- 2.37x wider. A probability curve read at 2.4x its fitted
dispersion returns log-odds that are far too steep, which is exactly the measured
reliability signature (predicted 0.036 -> observed 0.266 at the bottom decile; predicted
0.987 -> observed 0.862 at the top). The forward-chained Platt slope on logit(p_inc) is
b = 0.37 (per-fold 0.28-0.47, always << 1), i.e. 1/b = 2.7x too steep -- the dispersion
ratio, recovered independently from the outcomes.

PROPOSAL A (the ship candidate): a MEAN-PRESERVING dispersion correction

    logit(p') = m + B_HIT_PIT * (logit(p_inc) - m)

with m pinned so the served board's MEAN p_bust is unchanged. This fixes the
over-sharpness WITHOUT importing the population LEVEL shift, which belongs to the
"recalibrate the bucket curve toward the bustier resolved pool" line CLOSED by the
2026-07-15 BUCKET-AGE-HEAD lane. Strictly monotone => RESOLUTION IS PRESERVED EXACTLY
and every rank on the board is untouched.

PROPOSAL B (measured, NOT proposed): the full Platt including the intercept, which would
additionally correct the +0.13 level error. That is the closed line; it needs owner
authorization and is reported here only so the size of what is being left on the table
is on the record.
Read-only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools._prem_odds import bust_label, resolved                       # noqa: E402
from tools._prem_odds_gate import (FOLDS, SEED, EPS, logit, sigmoid,    # noqa: E402
                                   brier, logloss, murphy, labels)
from tools._prem_odds_decomp import fit_platt, fit_offset               # noqa: E402

POOL = ROOT / "tools" / "_prem_odds_pool.json"
DATA = ROOT / "data"


def fit_slope_mean_preserving(train):
    """Platt slope, with the intercept forced so the TRAIN mean p is unchanged."""
    w = fit_platt(train)
    b = float(w[1])
    z = logit([r["p_bust_inc"] for r in train])
    target = float(sigmoid(z).mean())
    lo, hi = -10.0, 10.0
    for _ in range(200):
        m = (lo + hi) / 2
        if float(sigmoid(m + b * (z - m)).mean()) > target:
            hi = m
        else:
            lo = m
    return b, (lo + hi) / 2


def chain(rows, rng=None, resample=False):
    kinds = ("INC", "A", "B")
    out = {k: ([], []) for k in kinds}
    for Y in FOLDS:
        tr = [r for r in rows if r["fold"] < Y]
        te = [r for r in rows if r["fold"] == Y]
        if len(tr) < 25 or len(te) < 10:
            continue
        if resample and rng is not None:
            tr = [tr[i] for i in rng.integers(0, len(tr), len(tr))]
            te = [te[i] for i in rng.integers(0, len(te), len(te))]
        zte = logit([r["p_bust_inc"] for r in te])
        yte = labels(te)
        b, m = fit_slope_mean_preserving(tr)
        w = fit_platt(tr)
        out["INC"][0].append(np.clip(sigmoid(zte), EPS, 1 - EPS))
        out["A"][0].append(np.clip(sigmoid(m + b * (zte - m)), EPS, 1 - EPS))
        out["B"][0].append(np.clip(sigmoid(w[0] + w[1] * zte), EPS, 1 - EPS))
        for k in kinds:
            out[k][1].append(yte)
    return {k: (np.concatenate(v[0]), np.concatenate(v[1])) for k, v in out.items()}


def main():
    allrows = resolved(json.loads(POOL.read_text(encoding="utf-8")))
    served = [r for r in allrows if r["has_track"]]

    print("GATE: PROPOSAL A (mean-preserving dispersion correction) vs the incumbent")
    print(f"served-comparable frame n={len(served)}, folds {FOLDS}\n")
    pt = chain(served)
    print(f"  {'model':<5s} {'Brier':>9s} {'logloss':>9s} {'reliab':>9s} {'resol':>9s} {'mean p':>8s}")
    for k in ("INC", "A", "B"):
        p, y = pt[k]
        m = murphy(p, y)
        print(f"  {k:<5s} {brier(p,y):9.5f} {logloss(p,y):9.5f} {m['reliability']:9.5f} "
              f"{m['resolution']:9.5f} {p.mean():8.4f}")
    print(f"  observed {pt['INC'][1].mean():.4f}")

    B = 500
    d = {k: {"b": [], "l": [], "rel": [], "res": []} for k in ("INC", "A", "B")}
    for i in range(B):
        rng = np.random.default_rng(SEED + 9000 + i)
        r = chain(served, rng=rng, resample=True)
        for k in d:
            p, y = r[k]
            mm = murphy(p, y)
            d[k]["b"].append(brier(p, y))
            d[k]["l"].append(logloss(p, y))
            d[k]["rel"].append(mm["reliability"])
            d[k]["res"].append(mm["resolution"])

    print(f"\n  PAIRED BOOTSTRAP B={B} (train+test resampled, refit per draw)")
    for a, c in (("INC", "A"), ("INC", "B"), ("A", "B")):
        for met, lab in (("b", "Brier"), ("l", "logloss"), ("rel", "reliability")):
            dd = np.asarray(d[a][met]) - np.asarray(d[c][met])
            print(f"  {a:>3s} - {c:<3s} {lab:<12s} {dd.mean():+9.5f} "
                  f"[{np.percentile(dd,2.5):+.5f},{np.percentile(dd,97.5):+.5f}] "
                  f"P(>0)={float((dd>0).mean()):.3f}")
        print()

    # resolution preservation check on a SINGLE global transform
    p0 = pt["INC"][0]
    y0 = pt["INC"][1]
    b_g, m_g = fit_slope_mean_preserving(served)
    pg = sigmoid(m_g + b_g * (logit(p0) - m_g))
    print(f"  RESOLUTION under ONE global transform (b={b_g:.4f}, m={m_g:.4f}): "
          f"{murphy(p0,y0)['resolution']:.5f} -> {murphy(pg,y0)['resolution']:.5f}  "
          f"(strictly monotone => preserved)")
    print(f"  reliability {murphy(p0,y0)['reliability']:.5f} -> {murphy(pg,y0)['reliability']:.5f}")

    # per-side slopes
    print("\n  PER-SIDE forward-chained slopes (full frame):")
    for side, sel in (("hit", [r for r in served if not r["is_pit"]]),
                      ("pit", [r for r in served if r["is_pit"]])):
        bb, mm = fit_slope_mean_preserving(sel)
        w = fit_platt(sel)
        print(f"    {side}: n={len(sel):4d}  mean-preserving b={bb:.4f} m={mm:+.4f}   "
              f"full Platt a={w[0]:+.4f} b={w[1]:.4f}")

    # ------------------------------------------------------------------
    # LIVE IMPACT
    # ------------------------------------------------------------------
    print("\n" + "=" * 90)
    print("LIVE SERVED IMPACT")
    xfv = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    live = [(k, v) for k, v in xfv.items()
            if isinstance(v.get("p_bust"), (int, float))
            and v.get("kind") == "active"]
    print(f"  active served rows carrying a p_bust: {len(live)}")
    b_g, m_g = fit_slope_mean_preserving(served)
    moved = 0
    deltas = []
    for k, v in live:
        p = float(v["p_bust"])
        pn = float(sigmoid(m_g + b_g * (logit(p) - m_g)))
        deltas.append((k, p, pn, pn - p))
        if abs(pn - p) >= 0.10:
            moved += 1
    print(f"  rows whose p_bust moves by >= 0.10 : {moved}  ({moved/len(live):.1%})")
    print(f"  mean p_bust before {np.mean([d[1] for d in deltas]):.4f} "
          f"after {np.mean([d[2] for d in deltas]):.4f}  "
          f"(mean-preserving anchor is fitted on the RESOLVED frame, so the live mean "
          f"moves only by distribution shape)")
    br = xfv.get("enrique_bradfield_jr")
    if br:
        p = float(br["p_bust"])
        pn = float(sigmoid(m_g + b_g * (logit(p) - m_g)))
        print(f"\n  BRADFIELD: xfv_grade {br.get('xfv_grade')}  "
              f"display {br.get('xfv_grade_display')}  consensus {br.get('consensus_fv')}")
        print(f"    p_bust {p:.4f}  ->  {pn:.4f}   (delta {pn-p:+.4f})")
    ups = sorted(deltas, key=lambda t: -t[3])[:8]
    dns = sorted(deltas, key=lambda t: t[3])[:8]
    print("\n  largest INCREASES in p_bust:")
    for k, p, pn, dd in ups:
        print(f"    {k:<32s} {p:.3f} -> {pn:.3f}  {dd:+.3f}")
    print("  largest DECREASES in p_bust:")
    for k, p, pn, dd in dns:
        print(f"    {k:<32s} {p:.3f} -> {pn:.3f}  {dd:+.3f}")


if __name__ == "__main__":
    raise SystemExit(main())

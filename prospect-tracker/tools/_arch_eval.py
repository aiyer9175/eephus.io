# scratch lab (lane: discover) -- the decisive test.
#
# Q: does archetype membership carry information ABOUT REALIZED OUTCOME that the
#    shipped features do not already price?
# A: measured as incremental explanatory power on the shipped model's OUT-OF-FOLD
#    residual, against a zero-information twin (same label vector, row-permuted:
#    identical marginal group sizes, pairing destroyed) and a permutation null band.
#
# Everything is computed on year-block-centred quantities so decision-year
# composition (MiLB-block coverage rises steeply with vintage, and 2021-2024
# resolved rows are ~all busts) cannot masquerade as archetype signal.
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _arch_discover as A  # noqa: E402


def _center_by(rows, field, w_field="weight", block="year"):
    out = np.zeros(len(rows))
    idx = {}
    for i, r in enumerate(rows):
        idx.setdefault(r[block], []).append(i)
    v = np.array([r[field] for r in rows], dtype=float)
    w = np.array([r[w_field] for r in rows], dtype=float)
    for _b, ii in idx.items():
        ii = np.array(ii)
        m = np.average(v[ii], weights=w[ii]) if w[ii].sum() > 0 else v[ii].mean()
        out[ii] = v[ii] - m
    return out


def eta2_w(labels, y, w):
    gm = np.average(y, weights=w)
    sst = float(np.sum(w * (y - gm) ** 2))
    if sst <= 0:
        return 0.0
    ssb = 0.0
    for g in np.unique(labels):
        i = labels == g
        ww = w[i].sum()
        if ww <= 0:
            continue
        ssb += ww * (float(np.average(y[i], weights=w[i])) - gm) ** 2
    return ssb / sst


def test_scheme(rows, label_field, value_field, B=4000, seed=17, block="year"):
    """Returns observed eta^2 plus the row-permuted zero-information band.
    Permutation is WITHIN year block so the control preserves the same year
    composition the observed statistic is exposed to."""
    y = _center_by(rows, value_field, block=block)
    w = np.array([r["weight"] for r in rows], dtype=float)
    lab = np.array([r[label_field] for r in rows])
    obs = eta2_w(lab, y, w)
    rng = np.random.default_rng(seed)
    blocks = {}
    for i, r in enumerate(rows):
        blocks.setdefault(r[block], []).append(i)
    null = np.empty(B)
    for b in range(B):
        pl = lab.copy()
        for _k, ii in blocks.items():
            ii = np.array(ii)
            pl[ii] = rng.permutation(lab[ii])
        null[b] = eta2_w(pl, y, w)
    return {"obs": obs, "null_mean": float(null.mean()),
            "null_p95": float(np.percentile(null, 95)),
            "null_p99": float(np.percentile(null, 99)),
            "p": float((null >= obs).mean()), "n": len(rows),
            "k": int(len(np.unique(lab)))}


def group_table(rows, label_field, value_field="target_resolved", B=4000, seed=23):
    """Per-archetype realized outcome + shipped-residual table with bootstrap CI."""
    rng = np.random.default_rng(seed)
    out = []
    for g in sorted({r[label_field] for r in rows}):
        sub = [r for r in rows if r[label_field] == g]
        vals = np.array([r[value_field] for r in sub if r[value_field] is not None], dtype=float)
        res = np.array([r["resid"] for r in sub], dtype=float)
        w = np.array([r["weight"] for r in sub], dtype=float)
        n = len(sub)
        def ci(x, ww=None):
            if len(x) == 0:
                return (float("nan"),) * 2
            m = np.empty(B)
            for b in range(B):
                j = rng.integers(0, len(x), len(x))
                if ww is None:
                    m[b] = x[j].mean()
                else:
                    m[b] = np.average(x[j], weights=np.clip(ww[j], 1e-6, None))
            return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))
        rlo, rhi = ci(res, w)
        vlo, vhi = ci(vals)
        out.append({
            "arch": g, "n": n,
            "n_resolved": int(sum(1 for r in sub if not r["censored"])),
            "mean_war": float(vals.mean()) if len(vals) else float("nan"),
            "war_ci": (vlo, vhi),
            "median_war": float(np.median(vals)) if len(vals) else float("nan"),
            "bust_rate": float(np.mean(vals <= 0.5)) if len(vals) else float("nan"),
            "mean_fv": float(np.mean([r["fv"] for r in sub])),
            "mean_pred": float(np.mean([r["pred"] for r in sub])),
            "mean_resid": float(np.average(res, weights=np.clip(w, 1e-6, None))),
            "resid_ci": (rlo, rhi),
        })
    return out

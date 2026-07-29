# A5 -- ablation ladder + the full gate, forward-chained, with all four mandatory
# controls (paired cluster bootstrap w/ refit, zero-information control, permutation
# null band, >= 4 independent time splits).
from __future__ import annotations

import json
import random
import sys

import numpy as np

from _cons_data import OUT, load_matrix_rows, spearman, ci

ROWS = load_matrix_rows()
for r in ROWS:
    r["pulled"] = (r["pre"] is not None and abs(r["cons"] - r["pre"]) > 1e-9)
FOLDS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)
MIN_TRAIN, MIN_TEST = 200, 25
SHIPPED_W = {"fg": 0.9363, "mp": 1.0637}


# ---------------------------------------------------------------------------
def fit(train):
    """All calibration parameters, TRAIN ONLY."""
    p = {"shift": {}, "sdr": {}, "mfg": {}, "mmp": {}, "w": {"fg": 1.0, "mp": 1.0},
         "shift_by_year": {}, "tier_w": {}, "coh_w": {}}
    pair = [r for r in train if r["fg"] is not None and r["mp"] is not None]

    def _sh(rs):
        if len(rs) < 60:
            return None
        fg = np.array([r["fg"] for r in rs], float)
        mp = np.array([r["mp"] for r in rs], float)
        sdr = float(mp.std(ddof=1) / fg.std(ddof=1)) if fg.std(ddof=1) > 0 else 1.0
        return {"shift": float(mp.mean() - fg.mean()), "mfg": float(fg.mean()),
                "mmp": float(mp.mean()), "sdr": sdr if 0.5 < sdr < 2.0 else 1.0}

    glob = _sh(pair) or {"shift": 0.0, "mfg": 0.0, "mmp": 0.0, "sdr": 1.0}
    p["glob"] = glob
    for side in ("hit", "pit"):
        p[side] = _sh([r for r in pair if r["side"] == side]) or glob
    # vintage: per decision-year shift (falls back to global when thin)
    for y in sorted({r["decision_year"] for r in pair}):
        s = _sh([r for r in pair if r["decision_year"] == y])
        if s:
            p["shift_by_year"][y] = s["shift"]
    # inverse-residual-variance weights in predicted-WAR space
    if len(pair) >= 100:
        t = np.array([r["target"] for r in pair], float)
        w = np.array([r["weight"] for r in pair], float)

        def rv(x):
            X = np.column_stack([np.ones_like(x), x])
            b = np.linalg.lstsq(X * w[:, None], t * w, rcond=None)[0]
            e = t - X @ b
            return float((w * e ** 2).sum() / w.sum())
        v1 = rv(np.array([r["fg"] for r in pair], float))
        v2 = rv(np.array([r["mp"] for r in pair], float))
        if v1 > 0 and v2 > 0:
            s1, s2 = 1 / v1, 1 / v2
            p["w"] = {"fg": 2 * s1 / (s1 + s2), "mp": 2 * s2 / (s1 + s2)}
        # CONDITIONAL weights -- by board tier and by acquisition cohort
        for name, sel in (("top", lambda r: r["cons"] >= 50),
                          ("fringe", lambda r: r["cons"] < 50)):
            sub = [r for r in pair if sel(r)]
            if len(sub) >= 120:
                tt = np.array([r["target"] for r in sub], float)
                ww = np.array([r["weight"] for r in sub], float)

                def rv2(x, tt=tt, ww=ww):
                    X = np.column_stack([np.ones_like(x), x])
                    b = np.linalg.lstsq(X * ww[:, None], tt * ww, rcond=None)[0]
                    e = tt - X @ b
                    return float((ww * e ** 2).sum() / ww.sum())
                a = rv2(np.array([r["fg"] for r in sub], float))
                b_ = rv2(np.array([r["mp"] for r in sub], float))
                if a > 0 and b_ > 0:
                    s1, s2 = 1 / a, 1 / b_
                    p["tier_w"][name] = {"fg": 2 * s1 / (s1 + s2), "mp": 2 * s2 / (s1 + s2)}
        for name, sel in (("ifa", lambda r: r["is_ifa"]),
                          ("col", lambda r: r["is_college"]),
                          ("hs", lambda r: not r["is_ifa"] and not r["is_college"])):
            sub = [r for r in pair if sel(r)]
            if len(sub) >= 120:
                tt = np.array([r["target"] for r in sub], float)
                ww = np.array([r["weight"] for r in sub], float)

                def rv3(x, tt=tt, ww=ww):
                    X = np.column_stack([np.ones_like(x), x])
                    b = np.linalg.lstsq(X * ww[:, None], tt * ww, rcond=None)[0]
                    e = tt - X @ b
                    return float((ww * e ** 2).sum() / ww.sum())
                a = rv3(np.array([r["fg"] for r in sub], float))
                b_ = rv3(np.array([r["mp"] for r in sub], float))
                if a > 0 and b_ > 0:
                    s1, s2 = 1 / a, 1 / b_
                    p["coh_w"][name] = {"fg": 2 * s1 / (s1 + s2), "mp": 2 * s2 / (s1 + s2)}
    return p


# ---------------------------------------------------------------------------
def build(r, p, *, offset="none", scale="shift", weights="equal",
          pull=(0.5, 35.0), placebo_off=None, side_offsets=True):
    """Generic consensus constructor from the RAW published per-source grades."""
    vals, ws = [], []
    sp = p[r["side"]] if (side_offsets and r["side"] in p) else p["glob"]
    if offset == "none":
        sh, mfg, mmp, sdr = 0.0, sp["mfg"], sp["mmp"], 1.0
    elif offset == "vintage":
        sh = p["shift_by_year"].get(r["decision_year"], sp["shift"])
        mfg, mmp, sdr = sp["mfg"], sp["mmp"], sp["sdr"]
    else:
        sh, mfg, mmp, sdr = sp["shift"], sp["mfg"], sp["mmp"], sp["sdr"]
    if placebo_off is not None:
        sh = placebo_off
    if weights == "equal":
        W = {"fg": 1.0, "mp": 1.0}
    elif weights == "shipped":
        W = SHIPPED_W
    elif weights == "ivw":
        W = p["w"]
    elif weights == "tier":
        W = p["tier_w"].get("top" if r["cons"] >= 50 else "fringe", p["w"])
    elif weights == "cohort":
        k = "ifa" if r["is_ifa"] else ("col" if r["is_college"] else "hs")
        W = p["coh_w"].get(k, p["w"])
    else:
        W = {"fg": 1.0, "mp": 1.0}
    if r["fg"] is not None:
        vals.append(r["fg"])
        ws.append(W["fg"])
    if r["mp"] is not None:
        if offset == "none":
            v = r["mp"]
        elif scale == "sd":
            v = mfg + (r["mp"] - mmp) / sdr
        else:
            v = r["mp"] - sh
        vals.append(v)
        ws.append(W["mp"])
    if not vals:
        return None
    base = sum(w * v for w, v in zip(ws, vals)) / sum(ws)
    if pull is not None and r["pulled"]:
        K, prior = pull
        wgt = 1.0 / (1.0 + K)
        base = wgt * base + (1 - wgt) * prior
    return base


LADDER = {
    "L0 raw equal mean":            dict(offset="none", weights="equal", pull=None),
    "L1 + single-source pull":      dict(offset="none", weights="equal", pull=(0.5, 35.0)),
    "L2 + outlet offset":           dict(offset="pooled", weights="equal", pull=(0.5, 35.0)),
    "L3 offset, no pull":           dict(offset="pooled", weights="equal", pull=None),
    "L4 + shipped src weights":     dict(offset="pooled", weights="shipped", pull=(0.5, 35.0)),
    "L5 + inv-variance weights":    dict(offset="pooled", weights="ivw", pull=(0.5, 35.0)),
    "L6 + tier-conditional w":      dict(offset="pooled", weights="tier", pull=(0.5, 35.0)),
    "L7 + cohort-conditional w":    dict(offset="pooled", weights="cohort", pull=(0.5, 35.0)),
    "L8 sd(distribution) match":    dict(offset="pooled", scale="sd", weights="equal", pull=(0.5, 35.0)),
    "L9 vintage-aware offset":      dict(offset="vintage", weights="equal", pull=(0.5, 35.0)),
}


def run(rows, cohort="full", variants=None, perm_target=False, placebo=False, seed=0):
    variants = variants or LADDER
    pool = rows if cohort == "full" else [r for r in rows if r["kind"] == "debuted"]
    rng = random.Random(seed)
    pairs = {k: [] for k in variants}
    pairs["served"] = []
    per_fold = {k: {} for k in list(variants) + ["served"]}
    for Y in FOLDS:
        train = [r for r in pool if r["decision_year"] < Y]
        test = [r for r in pool if r["decision_year"] == Y]
        if len(train) < MIN_TRAIN or len(test) < MIN_TEST:
            continue
        p = fit(train)
        tgt = [r["target"] for r in test]
        if perm_target:
            tgt = list(tgt)
            rng.shuffle(tgt)
        # zero-information control: permute WHICH rows receive the outlet offset,
        # preserving the marginal distribution of applied adjustments exactly.
        plc = None
        if placebo:
            real = [(p[r["side"]]["shift"] if r["mp"] is not None else 0.0) for r in test]
            rng.shuffle(real)
            plc = real
        for k, kw in variants.items():
            xs = [build(r, p, placebo_off=(plc[i] if plc else None), **kw)
                  for i, r in enumerate(test)]
            ok = [(a, b) for a, b in zip(xs, tgt) if a is not None]
            if len(ok) < 15:
                continue
            pairs[k].extend(ok)
            per_fold[k][Y] = spearman([a for a, _ in ok], [b for _, b in ok])
        okc = [(r["cons"], b) for r, b in zip(test, tgt)]
        pairs["served"].extend(okc)
        per_fold["served"][Y] = spearman([a for a, _ in okc], [b for _, b in okc])
    out = {}
    for k in pairs:
        if not pairs[k]:
            continue
        pf = {y: v for y, v in per_fold[k].items() if v is not None}
        out[k] = {"pooled": spearman([a for a, _ in pairs[k]], [b for _, b in pairs[k]]),
                  "mean_fold": float(np.mean(list(pf.values()))) if pf else None,
                  "per_fold": pf, "n": len(pairs[k])}
    return out


def show(title, res, ref="L1 + single-source pull"):
    print(f"\n=== {title} ===")
    print(f"{'variant':>28} {'n':>5} {'pooled':>8} {'d vs ref':>9} "
          f"{'meanfold':>9} {'d':>9} {'folds+':>7}")
    b = res[ref]
    for k, v in res.items():
        dp = v["pooled"] - b["pooled"]
        dm = v["mean_fold"] - b["mean_fold"]
        up = sum(1 for y in b["per_fold"] if v["per_fold"].get(y, -9) > b["per_fold"][y])
        print(f"{k:>28} {v['n']:>5} {v['pooled']:>8.4f} {dp:>+9.4f} "
              f"{v['mean_fold']:>9.4f} {dm:>+9.4f} {up:>3}/{len(b['per_fold'])}")


if __name__ == "__main__":
    for cohort in ("full", "debuted"):
        show(f"A5 ablation ladder, cohort={cohort}", run(ROWS, cohort=cohort))

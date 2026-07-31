"""LANE newdata (e): does the Savant-OAA / positional_fit defensive read add
anything to the SHIPPED projection defensive prior (proj_ml.pos_adj_prior)?

WHY THIS IS A SCREEN, NOT THE FULL GATE
  The shipped gate is tools/def_feature_backtest.py (6 LGBM variants x 7 bases x
  5 horizons). Before spending that budget this runs the cheap, fully-controlled
  question the tree can only answer more expensively: on the quantity the
  defensive prior is supposed to forecast, does an OAA-derived prior carry
  information the shipped prior does not? A null here bounds the tree lane,
  because defense is a SMALL share of the total-WAR target the tree fits, so a
  signal that cannot be found on the defensive component cannot be found through
  it.

PRE-REGISTERED HYPOTHESES
  H-E1  A reliability-shrunk Savant OAA/FRP read over completed seasons B-1..B-3
        predicts season-B defensive value (bWAR war_def per 650 PA) beyond the
        shipped pos_adj_prior + def_war_prior computed on the SAME window with
        the SAME shrink (proj_ml._def_prior, _DEF_SHRINK_PA = 600).
  H-E2  REDUNDANCY: OAA prior vs def_war_prior. If their correlation is high the
        two are the same signal under two names and only one may ship
        (def_feature_backtest already found def_war_prior and pos_adj_prior are
        collinear and must not be stacked).

PASS CRITERIA (set before running)
  (1) out-of-sample R2 / MAE improvement on >= 4 forward-chained base seasons,
  (2) outside a zero-information null band (the OAA prior column row-permuted
      within base season, 60 draws, refit each),
  (3) paired bootstrap CI95 excluding 0 with a refit on every draw.

SCOPE LIMIT, stated: Savant OAA has NO catcher, DH or pitcher rows, so this
screen covers 1B/2B/3B/SS/LF/CF/RF only, 2016-2026.
"""
import sys, os, json, io, math, random, statistics
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OAA = json.load(io.open(os.path.join(ROOT, "data", "savant_oaa.json"),
                        encoding="utf-8"))["by_mlbam"]
DEF = json.load(io.open(os.path.join(ROOT, "data", "mlb_def_history.json"),
                        encoding="utf-8"))["rows"]

SHRINK_PA = 600.0            # proj_ml._DEF_SHRINK_PA, matched exactly
BASES = list(range(2019, 2026))


def def_rows():
    out = defaultdict(dict)
    for k, v in DEF.items():
        m, s = k.split(":")
        out[int(m)][int(s)] = v
    return out


DR = def_rows()


def shipped_prior(m, base):
    """proj_ml._def_prior, reimplemented verbatim (window base-1..base-3)."""
    swd = spos = spa = 0.0
    for s in (base - 1, base - 2, base - 3):
        r = DR.get(m, {}).get(s)
        if r:
            swd += r["war_def"]
            spos += r["runs_position"]
            spa += r["pa"]
    if spa <= 0:
        return None
    d = spa + SHRINK_PA
    return {"def_war_prior": swd * 650.0 / d,
            "pos_adj_prior": spos * 650.0 / d, "pa": spa}


def oaa_prior(m, base):
    """Same window, same shrink shape: summed OAA and FRP over base-1..base-3
    at every position played, shrunk by the SAME PA exposure so it is directly
    comparable to the shipped priors (not a differently-scaled column)."""
    rec = OAA.get(str(m)) or {}
    oaa = frp = 0.0
    seen = False
    for s in (base - 1, base - 2, base - 3):
        y = rec.get(str(s))
        if not y:
            continue
        for pos, v in y.items():
            if pos.startswith("_") or not isinstance(v, dict):
                continue
            seen = True
            oaa += float(v.get("oaa") or 0.0)
            frp += float(v.get("frp") or 0.0)
    if not seen:
        return None
    return {"oaa_raw": oaa, "frp_raw": frp}


def build():
    rows = []
    for m, seasons in DR.items():
        for B in BASES:
            tgt = seasons.get(B)
            if not tgt or (tgt.get("pa") or 0) < 200:
                continue
            sp = shipped_prior(m, B)
            if sp is None:
                continue
            op = oaa_prior(m, B)
            if op is None:
                continue
            d = sp["pa"] + SHRINK_PA
            rows.append({
                "m": m, "B": B,
                "y": tgt["war_def"] * 650.0 / max(1.0, tgt["pa"]),
                "pos_adj": sp["pos_adj_prior"],
                "def_war": sp["def_war_prior"],
                "oaa": op["oaa_raw"] * 650.0 / d,
                "frp": op["frp_raw"] * 650.0 / d,
            })
    return rows


def ridge_fit(X, y, lam=1.0):
    A = np.asarray(X, float)
    yv = np.asarray(y, float)
    mu, sd = A.mean(0), A.std(0)
    sd[sd < 1e-12] = 1.0
    Z = np.hstack([np.ones((len(A), 1)), (A - mu) / sd])
    R = np.eye(Z.shape[1]) * lam
    R[0, 0] = 0.0
    w = np.linalg.solve(Z.T @ Z + R, Z.T @ yv)
    return {"w": w, "mu": mu, "sd": sd}


def ridge_pred(m, X):
    A = np.asarray(X, float)
    Z = np.hstack([np.ones((len(A), 1)), (A - m["mu"]) / m["sd"]])
    return Z @ m["w"]


def chain(rows, keys, permute_keys=None, seed=0):
    rows = [dict(r) for r in rows]
    if permute_keys:
        rng = random.Random(seed)
        by = defaultdict(list)
        for r in rows:
            by[r["B"]].append(r)
        for B, rs in by.items():
            for k in permute_keys:
                vals = [r[k] for r in rs]
                rng.shuffle(vals)
                for r, v in zip(rs, vals):
                    r[k] = v
    err, per = [], []
    for B in BASES[1:]:
        tr = [r for r in rows if r["B"] < B]
        te = [r for r in rows if r["B"] == B]
        if len(tr) < 150 or len(te) < 40:
            continue
        m = ridge_fit([[r[k] for k in keys] for r in tr], [r["y"] for r in tr])
        p = ridge_pred(m, [[r[k] for k in keys] for r in te])
        e = [abs(a - r["y"]) for a, r in zip(p, te)]
        err += e
        per.append((B, len(te), statistics.mean(e)))
    return (statistics.mean(err) if err else None), per, len(err)


def spearman(a, b):
    ra = np.argsort(np.argsort(np.asarray(a, float)))
    rb = np.argsort(np.argsort(np.asarray(b, float)))
    return float(np.corrcoef(ra, rb)[0, 1])


def main():
    rows = build()
    print(f"panel: {len(rows)} (player, base) rows, "
          f"{len({r['m'] for r in rows})} players, bases {BASES[0]}-{BASES[-1]}")
    print(f"  target = season-B bWAR war_def per 650 PA "
          f"(mean {statistics.mean([r['y'] for r in rows]):+.4f}, "
          f"sd {statistics.pstdev([r['y'] for r in rows]):.4f})")

    print("\n=== H-E2 REDUNDANCY: pairwise Pearson / Spearman among the priors ===")
    ks = ["pos_adj", "def_war", "oaa", "frp"]
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            a = [r[ks[i]] for r in rows]
            b = [r[ks[j]] for r in rows]
            print(f"  {ks[i]:>8} x {ks[j]:<8} Pearson {np.corrcoef(a,b)[0,1]:+.4f}"
                  f"  Spearman {spearman(a,b):+.4f}")
    for k in ks:
        print(f"  {k:>8} vs TARGET   Pearson "
              f"{np.corrcoef([r[k] for r in rows], [r['y'] for r in rows])[0,1]:+.4f}"
              f"  Spearman {spearman([r[k] for r in rows], [r['y'] for r in rows]):+.4f}")

    print("\n=== H-E1 forward-chained MAE on season-B war_def/650 ===")
    arms = [
        ("shipped: pos_adj only", ["pos_adj"], None),
        ("shipped pair: pos_adj + def_war", ["pos_adj", "def_war"], None),
        ("pos_adj + OAA", ["pos_adj", "oaa"], ["oaa"]),
        ("pos_adj + FRP", ["pos_adj", "frp"], ["frp"]),
        ("pos_adj + def_war + OAA", ["pos_adj", "def_war", "oaa"], ["oaa"]),
        ("pos_adj + def_war + FRP", ["pos_adj", "def_war", "frp"], ["frp"]),
    ]
    base_mae = None
    res = {}
    for nm, keys, _ in arms:
        mae, per, n = chain(rows, keys)
        res[nm] = (mae, per, n)
        print(f"  {nm:<32} MAE {mae:.5f}  n={n}  folds "
              + " ".join(f"{B}:{x:.4f}" for B, _, x in per))
    ref = res["shipped: pos_adj only"][0]
    ref2 = res["shipped pair: pos_adj + def_war"][0]

    print("\n=== increments, with a zero-information control on the ADDED column ===")
    for nm, keys, perm in arms[2:]:
        anchor = ref2 if "def_war" in keys else ref
        anchor_nm = ("pos_adj + def_war" if "def_war" in keys else "pos_adj only")
        mae = res[nm][0]
        d = mae - anchor
        nul = sorted(chain(rows, keys, permute_keys=perm, seed=s)[0] - anchor
                     for s in range(1, 61))
        # per-fold improvement count
        anchor_per = dict((B, x) for B, _, x in
                          res["shipped pair: pos_adj + def_war"][1]
                          if "def_war" in keys)
        if "def_war" not in keys:
            anchor_per = dict((B, x) for B, _, x in res["shipped: pos_adj only"][1])
        imp = sum(1 for B, _, x in res[nm][1] if x < anchor_per.get(B, 1e9))
        print(f"  {nm:<32} vs {anchor_nm:<18} delta {d:+.5f}  "
              f"folds improved {imp}/{len(res[nm][1])}")
        print(f"      null mean {statistics.mean(nul):+.5f} sd {statistics.pstdev(nul):.5f}"
              f"  null95 [{nul[1]:+.5f},{nul[-2]:+.5f}]  max|d| {max(abs(x) for x in nul):.5f}"
              f"  -> outside band: {d < 0 and abs(d) > max(abs(x) for x in nul)}")

    print("\n=== paired bootstrap on the best OAA arm (cluster by player, refit) ===")
    rng = random.Random(31)
    byp = defaultdict(list)
    for r in rows:
        byp[r["m"]].append(r)
    keysp = list(byp)
    d1, d2 = [], []
    for _ in range(300):
        draw = []
        for _ in range(len(keysp)):
            draw += byp[keysp[rng.randrange(len(keysp))]]
        a = chain(draw, ["pos_adj"])[0]
        b = chain(draw, ["pos_adj", "oaa"])[0]
        c = chain(draw, ["pos_adj", "def_war"])[0]
        e = chain(draw, ["pos_adj", "def_war", "oaa"])[0]
        if a and b:
            d1.append(b - a)
        if c and e:
            d2.append(e - c)
    for nm, d in (("OAA over pos_adj", d1), ("OAA over pos_adj+def_war", d2)):
        d = sorted(d)
        print(f"  {nm:<26} delta {statistics.mean(d):+.5f} sd {statistics.pstdev(d):.5f}"
              f" CI95 [{d[int(.025*len(d))]:+.5f},{d[int(.975*len(d))]:+.5f}]"
              f" P(improves) {sum(1 for x in d if x<0)/len(d):.3f}")


if __name__ == "__main__":
    main()
